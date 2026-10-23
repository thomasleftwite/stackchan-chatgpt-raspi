import {WebSocket} from 'ws';
import {encodePcm, decodePcm} from './protocol.js';

/** Synthetic protocol peer. Playback acknowledgement is simulated, not acoustic proof. */
export function runGeminiProtocolProbe(target: string, token: string, pcm: Buffer, tlsKey?:string): Promise<{pcm:Buffer;frames:number}> {
  const url = new URL(target);
  if (url.protocol !== (tlsKey ? 'wss:' : 'ws:') || url.hostname !== '127.0.0.1' || url.pathname !== '/live' || url.search || url.username || url.password ||
      !pcm.length || pcm.length % 2 || pcm.length > 160_000 || (token!=='' && !/^[\x21-\x7e]{32,256}$/.test(token)))
    throw new Error('Invalid local probe options');
  if(tlsKey && !/^[0-9a-f]{32}$/.test(tlsKey)) throw new Error('Invalid TLS options');
  return new Promise((resolve, reject) => {
    const secure=tlsKey ? {minVersion:'TLSv1.2' as const,maxVersion:'TLSv1.2' as const,ciphers:'DHE-PSK-AES128-GCM-SHA256',rejectUnauthorized:false,pskCallback:()=>({identity:'stackchan-v1',psk:Buffer.from(tlsKey,'hex')})} : {};
    const ws = new WebSocket(url, {...secure,headers:token ? {Authorization:`Bearer ${token}`} : {}, maxPayload:1024, perMessageDeflate:false, handshakeTimeout:2000});
    let state: 'ready'|'upload'|'waiting'|'output'|'draining'|'complete' = 'ready';
    let sent = 0, received = 0, samples = 0, expectedSamples = 0, expectedFrames = 0, settled = false;
    const chunks: Buffer[] = [];
    let pacing: ReturnType<typeof setTimeout> | undefined;
    const finish = (error?: Error) => {
      if (settled) return; settled = true; clearTimeout(deadline); clearTimeout(pacing);
      if (error) { ws.terminate(); reject(new Error('Gemini protocol probe failed')); }
      else resolve({pcm:Buffer.concat(chunks), frames:received});
      for (const chunk of chunks) chunk.fill(0);
    };
    const deadline = setTimeout(() => finish(new Error()), 60_000);
    const control = (type: string, extra = {}) => ws.send(JSON.stringify({type,generation:1,...extra}));
    const upload = () => {
      if (settled) return;
      if (sent * 640 >= pcm.length) { state = 'waiting'; control('input_end'); return; }
      const offset = sent * 640; const packet = encodePcm(1, sent++, pcm.subarray(offset, offset + 640));
      ws.send(packet, {binary:true}, () => packet.fill(0));
    };
    ws.on('error', () => finish(new Error()));
    ws.on('unexpected-response', (_req, res) => { res.resume(); finish(new Error()); });
    ws.on('message', (raw, binary) => {
      try {
        const packet = Array.isArray(raw) ? Buffer.concat(raw) : Buffer.isBuffer(raw) ? raw : Buffer.from(raw);
        if (binary) {
          if (state !== 'output' || received >= expectedFrames) throw new Error();
          const frame = decodePcm(packet, 960);
          if (frame.generation !== 1 || frame.sequence !== received || samples + frame.pcm.length / 2 > expectedSamples) throw new Error();
          chunks.push(Buffer.from(frame.pcm)); samples += frame.pcm.length / 2; ++received;
          if (received < expectedFrames) control('next', {sequence:received});
          else state = 'draining';
          return;
        }
        const message = JSON.parse(packet.toString()) as Record<string, unknown>;
        if (message.type === 'ready' && state === 'ready' && message.protocolVersion === 2 && message.mode === 'gemini-live') {
          state = 'upload'; upload(); return;
        }
        if (message.generation !== 1) throw new Error();
        if (message.type === 'input_ack' && state === 'upload' && message.sequence === sent - 1) {
          pacing = setTimeout(upload, 20); return;
        }
        if (message.type === 'thinking' && state === 'waiting') return;
        if (message.type === 'output_start' && state === 'waiting' && message.sampleRate === 24000 &&
            Number.isInteger(message.samples) && Number.isInteger(message.frames)) {
          expectedSamples = message.samples as number; expectedFrames = message.frames as number;
          if (expectedSamples < 1 || expectedSamples > 240_000 || expectedFrames !== Math.ceil(expectedSamples * 2 / 960)) throw new Error();
          state = 'output'; control('next', {sequence:0}); return;
        }
        if (message.type === 'output_end' && state === 'draining' && message.samples === samples && samples === expectedSamples && received === expectedFrames) {
          control('played', {samples}); return;
        }
        if (message.type === 'complete' && state === 'draining') { state = 'complete'; return; }
        throw new Error();
      } catch { finish(new Error()); }
    });
    ws.on('close', code => finish(state === 'complete' && code === 1000 ? undefined : new Error()));
  });
}
