import {createInterface} from 'node:readline';
import {once} from 'node:events';
import {isIPv4} from 'node:net';
import {createGeminiServer} from './gemini-server.js';
import {loadGeminiConfig} from './private-config.js';
import {runIsolatedTurn} from './gemini-isolated.js';
import {WebSocket} from 'ws';

// USB coordinator supplies only RAM host/token/mode via stdin. Never log values.
const lines = createInterface({input:process.stdin});
const report = (event:string, extra = {}) => console.info(JSON.stringify({event, ...extra}));
const deadline = setTimeout(() => process.exit(1), 5000);
let close: (() => Promise<void>) | undefined;
try {
  const [line] = await once(lines, 'line'); clearTimeout(deadline);
  const value = JSON.parse(line) as {host:string; token:string; mode:string};
  const ip = typeof value.host === 'string' ? value.host.split('.').map(Number) : [];
  if (!isIPv4(value.host) || !(ip[0] === 10 || (ip[0] === 172 && ip[1]! >= 16 && ip[1]! <= 31) ||
      (ip[0] === 192 && ip[1] === 168)) || !['fixture','gemini'].includes(value.mode)) throw new Error();
  const config = value.mode === 'gemini' ? await loadGeminiConfig() : undefined;
  const app = createGeminiServer({deviceToken:value.token, runTurn:async pcm => {
    if (config) {
      try {
        const result = await runIsolatedTurn({config, input:{pcm}});
        report('api-result', {status:'PASS', inputSamples:pcm.length / 2, outputSamples:result.pcm.length / 2, elapsedMs:result.elapsedMs});
        return result;
      } catch { report('api-result', {status:'FAIL'}); throw new Error('GEMINI_FAILED'); }
    }
    // A short tone with a one-sample final packet tests variable-length playback.
    const audio = Buffer.alloc(12001 * 2);
    for (let i = 0; i < 12001; ++i) audio.writeInt16LE(Math.round(2000 * Math.sin(2 * Math.PI * 700 * i / 24000)), i * 2);
    return {pcm:audio, sampleRate:24000, chunks:1, elapsedMs:0};
  }});
  close = app.close;
  app.server.listen(0, value.host); await once(app.server, 'listening');
  const address = app.server.address(); if (!address || typeof address === 'string') throw new Error();
  const url = `ws://${value.host}:${address.port}/live`;
  for (const headers of [{}, {Authorization:'Bearer wrong'}]) {
    const socket = new WebSocket(url, {headers, handshakeTimeout:2000}); socket.on('error', () => {});
    const [, response] = await once(socket, 'unexpected-response');
    if (response.statusCode !== 401) throw new Error(); response.resume(); socket.terminate();
  }
  report('ready', {port:address.port, preflight:true, mode:value.mode});
  let closing = false;
  const shutdown = async () => {
    if (closing) return; closing = true; lines.close(); await app.close(); process.exit(0);
  };
  lines.once('close', () => void shutdown());
  process.once('SIGINT', () => void shutdown()); process.once('SIGTERM', () => void shutdown());
  setTimeout(() => void shutdown(), 10 * 60_000).unref();
} catch {
  clearTimeout(deadline); report('failed'); lines.close();
  if (close) await close().catch(() => {}); process.exitCode = 1;
}
