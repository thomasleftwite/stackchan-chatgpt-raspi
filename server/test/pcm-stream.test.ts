import {test} from 'node:test';
import assert from 'node:assert/strict';
import {once} from 'node:events';
import {randomBytes} from 'node:crypto';
import {setTimeout as delay} from 'node:timers/promises';
import {WebSocket} from 'ws';
import {createEchoServer} from '../echo.js';
import {encodePcm, decodePcm} from '../protocol.js';

test('loopback streams 100 paced 16kHz PCM frames with byte-exact ordered echo', async () => {
  const token = randomBytes(32).toString('hex'); // Ephemeral, never persisted or logged.
  const app = createEchoServer({deviceToken:token});
  let ws: WebSocket | undefined;
  try {
    app.server.listen(0, '127.0.0.1');
    await once(app.server, 'listening');
    const address = app.server.address();
    assert(address && typeof address !== 'string');
    ws = new WebSocket(`ws://127.0.0.1:${address.port}/live`, {
      headers:{Authorization:`Bearer ${token}`}, handshakeTimeout:2000,
      maxPayload:1024, perMessageDeflate:false,
    });
    ws.on('error', () => {});
    const [ready] = await once(ws, 'message');
    assert.equal(JSON.parse(String(ready)).maxPcmBytes, 640);
    const started = performance.now();
    let samples = 0;
    for (let sequence = 0; sequence < 100; ++sequence) {
      const pcm = Buffer.alloc(640);
      for (let i = 0; i < 320; ++i)
        pcm.writeInt16LE(Math.round(2000 * Math.sin(2 * Math.PI * 1000 * (sequence * 320 + i) / 16000)), i * 2);
      const packet = encodePcm(1, sequence, pcm);
      const received: Promise<[Buffer, boolean]> = once(ws, 'message') as Promise<[Buffer, boolean]>;
      ws.send(packet, {binary:true});
      const [raw, binary] = await received;
      assert.equal(binary, true);
      assert.deepEqual(raw, packet);
      const frame = decodePcm(raw as Buffer, 640);
      assert.equal(frame.sequence, sequence);
      samples += frame.pcm.length / 2;
      await delay(Math.max(0, started + (sequence + 1) * 20 - performance.now()));
    }
    assert.equal(samples, 32000);
    ws.send(JSON.stringify({type:'stop'}));
    const [code] = await once(ws, 'close');
    assert.equal(code, 1000);
  } finally {
    ws?.terminate();
    await app.close();
  }
});
