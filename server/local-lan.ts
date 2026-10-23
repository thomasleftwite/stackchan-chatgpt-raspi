import {createInterface} from 'node:readline';
import {once} from 'node:events';
import {isIPv4} from 'node:net';
import assert from 'node:assert/strict';
import {WebSocket} from 'ws';
import {createEchoServer} from './echo.js';
import {encodePcm, decodePcm} from './protocol.js';

const report = (event: string, extra = {}) => console.info(JSON.stringify({event, ...extra}));
const lines = createInterface({input:process.stdin});
const configDeadline = setTimeout(() => { report('config-timeout'); process.exit(1); }, 5000);
let stop: (() => Promise<void>) | undefined;
try {
  const [line] = await once(lines, 'line');
  clearTimeout(configDeadline);
  const config = JSON.parse(line) as {host: string; token: string};
  const octets = typeof config.host === 'string' ? config.host.split('.').map(Number) : [];
  if (!isIPv4(config.host) || !(octets[0] === 10 ||
      (octets[0] === 172 && octets[1]! >= 16 && octets[1]! <= 31) ||
      (octets[0] === 192 && octets[1] === 168))) throw new Error('Private interface required');
  const notices: {stage: string; value: number}[] = [];
  const app = createEchoServer({deviceToken:config.token, mode:'pcm-loopback',
    onProbeNotice: (stage, value) => { if (notices.length < 20) notices.push({stage, value}); }});
  stop = app.close;
  app.server.listen(0, config.host);
  await once(app.server, 'listening');
  const address = app.server.address();
  assert(address && typeof address !== 'string');
  const url = `ws://${config.host}:${address.port}/live`;
  const unauthenticated = new WebSocket(url, {handshakeTimeout:2000});
  unauthenticated.on('error', () => {});
  const [, rejected] = await once(unauthenticated, 'unexpected-response');
  assert.equal(rejected.statusCode, 401); rejected.resume(); unauthenticated.terminate();
  const wrong = new WebSocket(url, {headers:{Authorization:'Bearer wrong'}, handshakeTimeout:2000});
  wrong.on('error', () => {});
  const [, rejectedWrong] = await once(wrong, 'unexpected-response');
  assert.equal(rejectedWrong.statusCode, 401); rejectedWrong.resume(); wrong.terminate();
  const ws = new WebSocket(url, {headers:{Authorization:`Bearer ${config.token}`}, handshakeTimeout:2000});
  ws.on('error', () => {});
  const [greeting] = await once(ws, 'message');
  assert.equal(JSON.parse(String(greeting)).mode, 'pcm-loopback');
  const pending = once(ws, 'message');
  ws.send(encodePcm(1, 0, Buffer.alloc(640)));
  const [raw, binary] = await pending;
  assert.equal(binary, true);
  const frame = decodePcm(raw, 960);
  assert.equal(frame.pcm.length, 960); assert(frame.pcm.equals(Buffer.alloc(960)));
  ws.send(JSON.stringify({type:'stop'}));
  const [code] = await once(ws, 'close'); assert.equal(code, 1000);
  report('ready', {port:address.port, preflight:true});
  notices.length = 0;
  const noticeTimer = setInterval(() => { for (const notice of notices.splice(0)) report('notice', notice); }, 100);
  noticeTimer.unref();
  let closing = false;
  const shutdown = async () => {
    if (closing) return;
    closing = true;
    clearInterval(noticeTimer);
    lines.close();
    await app.close();
    process.exit(0);
  };
  process.once('SIGTERM', () => void shutdown());
  process.once('SIGINT', () => void shutdown());
  lines.once('close', () => { void shutdown(); });
  setTimeout(() => void shutdown(), 10 * 60_000).unref();
} catch {
  clearTimeout(configDeadline);
  report('failed');
  lines.close();
  if (stop) await stop().catch(() => {});
  process.exitCode = 1;
}
