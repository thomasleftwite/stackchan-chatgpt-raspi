import {createServer, type IncomingMessage, type ServerResponse} from 'node:http';
import {createServer as createSecureServer} from 'node:https';
import {createHash, timingSafeEqual} from 'node:crypto';
import {BlockList, isIPv4} from 'node:net';
import {WebSocketServer, WebSocket} from 'ws';
import {decodePcm, encodePcm} from './protocol.js';
import type {TurnResult} from './gemini-turn.js';

export interface GeminiServerOptions {
  deviceToken: string;
  runTurn: (pcm: Buffer) => Promise<TurnResult>;
  sessionMs?: number;
  tlsPsk?: {identity:string; keyHex:string};
  onHealth?: () => void;
  trustedSubnet?: string;
  canStart?:()=>boolean;
  onSessionState?:(active:boolean)=>void;
  onBusy?:()=>void;
  onPlayed?:()=>void;
}

function hotspotBoundary(subnet: string): BlockList {
  const parts=subnet.split('/'), prefix=Number(parts[1]), ip=parts[0];
  const octets=ip?.split('.').map(Number);
  const privateIp=octets && (octets[0]===10 || (octets[0]===172 && octets[1]!>=16 && octets[1]!<=31) || (octets[0]===192 && octets[1]===168));
  const loopback=ip?.startsWith('127.') && prefix===32;
  if(parts.length!==2 || !ip || !isIPv4(ip) || !Number.isInteger(prefix) ||
    !((privateIp && prefix>=16 && prefix<=30) || loopback)) throw new Error('Invalid hotspot boundary');
  const boundary=new BlockList();boundary.addSubnet(ip,prefix,'ipv4');return boundary;
}
export function hotspotPeerAllowed(peer:string|undefined,subnet:string):boolean {
  const boundary=hotspotBoundary(subnet);
  const ip=peer?.startsWith('::ffff:') ? peer.slice(7) : peer;
  return !!ip && isIPv4(ip) && boundary.check(ip,'ipv4');
}

/** Initial half-duplex protocol v2: one bounded utterance/response per connection. */
export function createGeminiServer(options: GeminiServerOptions) {
  const boundary=options.trustedSubnet ? hotspotBoundary(options.trustedSubnet) : undefined;
  if(boundary && options.tlsPsk) throw new Error('Select one trust mode');
  if (!boundary && !/^[\x21-\x7e]{32,256}$/.test(options.deviceToken)) throw new Error('Invalid device token');
  const admitted=(peer:string|undefined)=>{
    const ip=peer?.startsWith('::ffff:') ? peer.slice(7) : peer;
    return !!boundary && !!ip && isIPv4(ip) && boundary.check(ip,'ipv4');
  };
  const sessionMs = options.sessionMs ?? 90_000;
  if (!Number.isFinite(sessionMs) || sessionMs < 100 || sessionMs > 90_000) throw new Error('Invalid deadline');
  const digest = (value: string) => createHash('sha256').update(value).digest();
  const expected = digest(options.deviceToken);
  if (options.tlsPsk && (!/^[0-9a-f]{32}$/.test(options.tlsPsk.keyHex) || options.tlsPsk.identity !== 'stackchan-v1')) throw new Error('Invalid TLS identity');
  const handler = (req:IncomingMessage, res:ServerResponse) => {
    if(boundary && !admitted(req.socket.remoteAddress)) {res.writeHead(403);res.end();return;}
    if (options.tlsPsk && req.headers.authorization !== `Bearer ${options.deviceToken}`) {
      res.writeHead(401); res.end(); return;
    }
    if (req.url === '/healthz') options.onHealth?.();
    res.setHeader('Content-Type', 'application/json');
    res.writeHead(req.url === '/healthz' ? 200 : 404);
    res.end(JSON.stringify(req.url === '/healthz' ? {status:'ok', mode:'gemini-live', protocolVersion:2} : {error:'not-found'}));
  };
  const server = options.tlsPsk ? createSecureServer({
    maxHeaderSize:8192, minVersion:'TLSv1.2', maxVersion:'TLSv1.2',
    ciphers:'DHE-PSK-AES128-GCM-SHA256', dhparam:'auto',
    pskCallback:(_socket, identity) => identity === options.tlsPsk!.identity ? Buffer.from(options.tlsPsk!.keyHex,'hex') : null,
    handshakeTimeout:5000,
  }, handler) : createServer({maxHeaderSize:8192}, handler);
  server.headersTimeout = 5000; server.requestTimeout = 10_000;
  const wss = new WebSocketServer({noServer:true, maxPayload:1024, perMessageDeflate:false});
  let busy = false;
  server.on('upgrade', (req, socket, head) => {
    socket.on('error', () => {});
    const reject = (code: number) => socket.end(`HTTP/1.1 ${code} Rejected\r\nConnection: close\r\nContent-Length: 0\r\n\r\n`);
    if(boundary && !admitted(req.socket.remoteAddress)) {reject(403);return;}
    if (req.url !== '/live') { reject(404); return; }
    const auth = req.headers.authorization;
    if (!boundary && (typeof auth !== 'string' || !auth.startsWith('Bearer ') || auth.length > 263 ||
        !timingSafeEqual(digest(auth.slice(7)), expected))) { reject(401); return; }
    if (wss.clients.size || busy) { reject(429); return; }
    if(options.canStart && !options.canStart()) {options.onBusy?.();reject(429);return;}
    wss.handleUpgrade(req, socket, head, ws => wss.emit('connection', ws));
  });
  wss.on('connection', ws => {
    options.onSessionState?.(true);
    let phase: 'input' | 'generating' | 'output' | 'draining' | 'closed' = 'input';
    let generation = 0, inputSequence = 0, inputBytes = 0, outputSequence = 0, outputSamples = 0;
    let output: Buffer | undefined;
    const input: Buffer[] = [];
    let activity = Date.now(), windowStart = activity, windowBytes = 0;
    const started = activity;
    let hardClose: ReturnType<typeof setTimeout> | undefined;
    const clearAudio = () => { for (const pcm of input) pcm.fill(0); input.length = 0; output?.fill(0); output = undefined; };
    const stop = (code: number, reason: string) => {
      if (phase === 'closed') return;
      phase = 'closed'; clearAudio(); ws.close(code, reason);
      hardClose = setTimeout(() => ws.terminate(), 1000); hardClose.unref();
    };
    const json = (value: object) => { if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(value)); };
    const timer = setInterval(() => {
      if (Date.now() - started >= sessionMs || (phase === 'input' && Date.now() - activity > 10_000)) stop(1008, 'Session deadline');
    }, 100);
    timer.unref();
    ws.on('error', () => stop(1011, 'Transport failure'));
    ws.on('close', () => { phase = 'closed'; clearInterval(timer); clearTimeout(hardClose); clearAudio();if(!busy)options.onSessionState?.(false); });
    ws.on('message', (raw, binary) => {
      if (phase === 'closed') return;
      const packet = Array.isArray(raw) ? Buffer.concat(raw) : Buffer.isBuffer(raw) ? raw : Buffer.from(raw);
      activity = Date.now();
      if (activity - windowStart >= 1000) { windowStart = activity; windowBytes = 0; }
      windowBytes += packet.length;
      if (windowBytes > 65_536 || ws.bufferedAmount > 32_768) { stop(1008, 'Capacity exceeded'); return; }
      try {
        if (binary) {
          if (phase !== 'input') throw new Error();
          const frame = decodePcm(packet, 640);
          if (inputSequence >= 250 || frame.sequence !== inputSequence || (generation && generation !== frame.generation) || inputBytes + frame.pcm.length > 160_000) throw new Error();
          generation = frame.generation; ++inputSequence; inputBytes += frame.pcm.length;
          input.push(Buffer.from(frame.pcm));
          json({type:'input_ack', generation, sequence:frame.sequence});
          return;
        }
        const control: unknown = JSON.parse(packet.toString('utf8'));
        if (!control || typeof control !== 'object' || !('type' in control)) throw new Error();
        if (control.type === 'stop') { stop(1000, 'Stopped'); return; }
        if (!('generation' in control) || control.generation !== generation) throw new Error();
        if (control.type === 'input_end' && phase === 'input' && inputBytes) {
          phase = 'generating'; busy = true;
          const pcm = Buffer.concat(input);
          for (const chunk of input) chunk.fill(0); input.length = 0;
          json({type:'thinking', generation});
          void Promise.resolve().then(() => options.runTurn(pcm)).then(result => {
            if (phase === 'closed') { result.pcm.fill(0); return; }
            if (result.sampleRate !== 24000 || !result.pcm.length || result.pcm.length % 2 || result.pcm.length > 480_000) {
              result.pcm.fill(0); stop(1011, 'Invalid provider audio'); return;
            }
            output = result.pcm; outputSamples = output.length / 2; phase = 'output';
            json({type:'output_start', generation, sampleRate:24000, samples:outputSamples, frames:Math.ceil(output.length / 960)});
          }).catch(() => { if (phase !== 'closed') { json({type:'error', code:'GEMINI_FAILED'}); stop(1011, 'Gemini failed'); } })
            .finally(() => { pcm.fill(0); busy = false;if(phase==='closed')options.onSessionState?.(false); });
          return;
        }
        if (control.type === 'next' && phase === 'output' && 'sequence' in control && control.sequence === outputSequence && output) {
          const offset = outputSequence * 960;
          const frame = encodePcm(generation, outputSequence++, output.subarray(offset, offset + 960));
          output.fill(0, offset, Math.min(offset + 960, output.length));
          const last = outputSequence * 960 >= output.length;
          if (last) phase = 'draining';
          ws.send(frame, {binary:true}, error => {
            frame.fill(0);
            if (error) { stop(1011, 'Transport failure'); return; }
            if (last && phase !== 'closed') json({type:'output_end', generation, samples:outputSamples});
          });
          return;
        }
        if (control.type === 'played' && phase === 'draining' && 'samples' in control && control.samples === outputSamples) {
          options.onPlayed?.();
          json({type:'complete', generation}); stop(1000, 'Turn complete'); return;
        }
        throw new Error();
      } catch { stop(1003, 'Invalid protocol'); }
    });
    json({type:'ready', mode:'gemini-live', protocolVersion:2, inputRate:16000, outputRate:24000,
      maxInputSamples:80_000, maxOutputSamples:240_000});
  });
  return {server, close: async () => {
    for (const ws of wss.clients) ws.terminate();
    await new Promise<void>(resolve => wss.close(() => resolve()));
    await new Promise<void>(resolve => server.close(() => resolve()));
  }};
}
