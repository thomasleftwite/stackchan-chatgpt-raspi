import {test} from 'node:test';
import assert from 'node:assert/strict';
import {once} from 'node:events';
import {setTimeout as delay} from 'node:timers/promises';
import {WebSocket} from 'ws';
import {createEchoServer} from '../echo.js';
import {encodePcm, decodePcm} from '../protocol.js';
import {resampleProbeFrame} from '../probe-resample.js';

const token = 'test-only-'.padEnd(64, 'x');
async function fixture(t: {after: (fn: () => Promise<void>) => void}) {
  const app = createEchoServer({deviceToken:token, mode:'pcm-loopback'});
  app.server.listen(0, '127.0.0.1');
  await once(app.server, 'listening');
  const address = app.server.address();
  assert(address && typeof address !== 'string');
  t.after(() => app.close());
  return `ws://127.0.0.1:${address.port}/live`;
}
async function client(url: string) {
  const ws = new WebSocket(url, {headers:{Authorization:`Bearer ${token}`}});
  ws.on('error', () => {});
  const [ready] = await once(ws, 'message');
  assert.equal(JSON.parse(String(ready)).outputRate, 24000);
  return ws;
}

test('PCM probe transforms full 150-frame input to bounded ordered 24kHz output', async t => {
  const ws = await client(await fixture(t));
  let total = 0;
  for (let sequence = 0; sequence < 150; ++sequence) {
    const pcm = Buffer.alloc(640);
    for (let i = 0; i < 320; ++i) pcm.writeInt16LE(i % 2 ? 32767 : -32768, i * 2);
    const pending = once(ws, 'message');
    ws.send(encodePcm(7, sequence, pcm));
    const [raw, binary] = await pending;
    assert.equal(binary, true);
    const frame = decodePcm(raw, 960);
    assert.equal(frame.generation, 7);
    assert.equal(frame.sequence, sequence);
    assert.equal(frame.pcm.length, 960);
    assert.equal(frame.pcm.readInt16LE(0), -32768);
    assert.equal(frame.pcm.readInt16LE(2), 10922);
    assert.equal(frame.pcm.readInt16LE(4), 10922);
    total += frame.pcm.length / 2;
    await delay(20);
  }
  assert.equal(total, 72000);
  ws.send(JSON.stringify({type:'stop'}));
  const [code] = await once(ws, 'close');
  assert.equal(code, 1000);
});

test('PCM probe rejects short frames, order violations and excess frames', async t => {
  const url = await fixture(t);
  for (const kind of ['short', 'sequence', 'generation', 'excess']) {
    const ws = await client(url);
    const pcm = Buffer.alloc(640);
    const accepted = kind === 'generation' ? 1 : kind === 'excess' ? 150 : 0;
    for (let i = 0; i < accepted; ++i) {
      const pending = once(ws, 'message');
      ws.send(encodePcm(1, i, pcm)); await pending; await delay(20);
    }
    ws.send(encodePcm(kind === 'generation' ? 2 : 1, kind === 'sequence' ? 1 : accepted,
      kind === 'short' ? Buffer.alloc(4) : pcm));
    const [code] = await once(ws, 'close');
    assert.equal(code, 1003);
  }
});

test('probe interpolation preserves DC and rejects non-20ms input', () => {
  const pcm = Buffer.alloc(640);
  for (let i = 0; i < 320; ++i) pcm.writeInt16LE(-1234, i * 2);
  const out = resampleProbeFrame(pcm);
  for (let i = 0; i < 480; ++i) assert.equal(out.readInt16LE(i * 2), -1234);
  assert.throws(() => resampleProbeFrame(Buffer.alloc(638)));
});
