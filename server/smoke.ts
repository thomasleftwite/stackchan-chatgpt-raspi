import {WebSocket} from 'ws';
import {pathToFileURL} from 'node:url';
import {encodePcm} from './protocol.js';

/** Synthetic audio only. Token and response bodies must never reach logs. */
export async function runSmoke(target: string, token: string): Promise<void> {
  const url = new URL(target);
  const local = ['127.0.0.1', '[::1]', 'localhost'].includes(url.hostname);
  if ((url.protocol !== 'wss:' && !(url.protocol === 'ws:' && local)) ||
      url.pathname !== '/live' || url.search || url.hash || url.username || url.password)
    throw new Error('Use a WSS /live URL without credentials or query parameters');
  if (!/^[\x21-\x7e]{32,256}$/.test(token)) throw new Error('DEVICE_TOKEN is missing or invalid');
  const pcm = Buffer.alloc(640);
  pcm.writeInt16LE(-32768, 0);
  pcm.writeInt16LE(32767, 2);
  const expected = encodePcm(1, 0, pcm);
  await new Promise<void>((resolve, reject) => {
    const ws = new WebSocket(url, {headers:{Authorization:`Bearer ${token}`}, maxPayload:1024, perMessageDeflate:false});
    let phase: 'ready' | 'echo' | 'closing' = 'ready';
    let settled = false;
    const finish = (error?: Error) => {
      if (settled) return;
      settled = true;
      clearTimeout(deadline);
      if (error) { ws.terminate(); reject(error); }
      else resolve();
    };
    const deadline = setTimeout(() => finish(new Error('Probe timeout')), 20_000);
    ws.on('error', () => finish(new Error('Probe transport failed')));
    ws.on('unexpected-response', (_request, response) => {
      response.resume();
      finish(new Error('Probe upgrade rejected'));
    });
    ws.on('message', (data, binary) => {
      try {
        const packet = Array.isArray(data) ? Buffer.concat(data) : Buffer.isBuffer(data) ? data : Buffer.from(data);
        if (phase === 'ready' && !binary) {
          const ready = JSON.parse(packet.toString()) as Record<string, unknown>;
          if (ready.type !== 'ready' || ready.mode !== 'echo' || ready.protocolVersion !== 1)
            throw new Error('Unexpected probe mode');
          phase = 'echo'; ws.send(expected); return;
        }
        if (phase !== 'echo' || !binary || !packet.equals(expected)) throw new Error('PCM echo mismatch');
        phase = 'closing'; ws.send(JSON.stringify({type:'stop'}));
      } catch { finish(new Error('Invalid probe response')); }
    });
    ws.on('close', code => finish(phase === 'closing' && code === 1000 ? undefined : new Error('Probe closed before completion')));
  });
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  void runSmoke(process.env.PROBE_URL ?? '', process.env.DEVICE_TOKEN ?? '')
    .then(() => console.info('PASS: authenticated WSS/WS, known PCM echo, normal close'))
    .catch(() => { console.error('FAIL: probe did not complete (details suppressed)'); process.exitCode = 1; });
}
