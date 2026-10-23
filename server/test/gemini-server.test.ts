import {test} from 'node:test';
import assert from 'node:assert/strict';
import {once} from 'node:events';
import {WebSocket} from 'ws';
import {createGeminiServer} from '../gemini-server.js';
import {runGeminiProtocolProbe} from '../gemini-probe-client.js';
import {encodePcm} from '../protocol.js';
import type {TurnResult} from '../gemini-turn.js';

const token = 'test-device-'.padEnd(64, 'x');
async function fixture(t: {after: (fn: () => Promise<void>) => void}, runTurn: (pcm:Buffer) => Promise<TurnResult>, sessionMs?:number) {
  const app = createGeminiServer({deviceToken:token, runTurn, sessionMs});
  app.server.listen(0, '127.0.0.1'); await once(app.server, 'listening');
  const address = app.server.address(); assert(address && typeof address !== 'string');
  t.after(() => app.close());
  return {app, url:`ws://127.0.0.1:${address.port}/live`};
}
const response = (pcm:Buffer): TurnResult => ({pcm,sampleRate:24000,chunks:1,elapsedMs:1});

test('PC Gemini service accepts ordered PCM and returns variable-length audio through explicit credits/drain', async t => {
  const output = Buffer.alloc(1922);
  output.writeInt16LE(-32768, 0); output.writeInt16LE(32767, 1920);
  const {url} = await fixture(t, async input => {
    assert.equal(input.length, 1280); assert.equal(input.readInt16LE(0), -1234);
    return response(Buffer.from(output));
  });
  const input = Buffer.alloc(1280); input.writeInt16LE(-1234, 0);
  const result = await runGeminiProtocolProbe(url, token, input);
  assert.equal(result.frames, 3); assert.deepEqual(result.pcm, output);
});
test('PC Gemini service rejects unauthorized clients before any API work', async t => {
  let calls = 0;
  const {url} = await fixture(t, async () => { ++calls; return response(Buffer.alloc(2)); });
  for (const headers of [{}, {Authorization:'Bearer wrong'}]) {
    const ws = new WebSocket(url, {headers}); ws.on('error', () => {});
    const [, res] = await once(ws, 'unexpected-response'); assert.equal(res.statusCode, 401);
    res.resume(); ws.terminate();
  }
  assert.equal(calls, 0);
});

test('PC Gemini service accepts a complete five-second variable utterance at the input bound', async t => {
  let calls = 0;
  const {url} = await fixture(t, async input => {
    ++calls; assert.equal(input.length, 160000);
    assert.equal(input.readInt16LE(0), -1234); assert.equal(input.readInt16LE(159998), 2345);
    return response(Buffer.from([1, 0]));
  });
  const pcm = Buffer.alloc(160000); pcm.writeInt16LE(-1234, 0); pcm.writeInt16LE(2345, 159998);
  const result = await runGeminiProtocolProbe(url, token, pcm);
  assert.equal(calls, 1); assert.equal(result.frames, 1); assert.deepEqual(result.pcm, Buffer.from([1, 0]));
});
test('PC Gemini service rejects wrong sequence and premature playback claims', async t => {
  const {url} = await fixture(t, async () => response(Buffer.alloc(2)));
  for (const kind of ['sequence','played']) {
    const ws = new WebSocket(url, {headers:{Authorization:`Bearer ${token}`}}); ws.on('error', () => {});
    await once(ws, 'message');
    ws.send(kind === 'sequence' ? encodePcm(1, 1, Buffer.alloc(640)) : JSON.stringify({type:'played',generation:1,samples:1}));
    const [code] = await once(ws, 'close'); assert.equal(code, 1003);
  }
});
test('PC Gemini service expires a connection and releases its listener', async t => {
  const {url} = await fixture(t, async () => response(Buffer.alloc(2)), 150);
  const ws = new WebSocket(url, {headers:{Authorization:`Bearer ${token}`}}); ws.on('error', () => {});
  await once(ws, 'message');
  const [code] = await once(ws, 'close'); assert.equal(code, 1008);
});

test('disconnected client cannot create overlapping API turns; retained input is wiped', async t => {
  let complete!: (value:TurnResult) => void;
  let captured: Buffer | undefined;
  let notify!: () => void;
  const started = new Promise<void>(resolve => { notify = resolve; });
  const {url} = await fixture(t, input => {
    captured = input; notify();
    return new Promise(resolve => { complete = resolve; });
  });
  const ws = new WebSocket(url, {headers:{Authorization:`Bearer ${token}`}}); ws.on('error', () => {});
  await once(ws, 'message');
  const ack = once(ws, 'message');
  ws.send(encodePcm(1, 0, Buffer.alloc(640, 1))); await ack;
  ws.send(JSON.stringify({type:'input_end', generation:1})); await started;
  ws.terminate(); await once(ws, 'close');
  const second = new WebSocket(url, {headers:{Authorization:`Bearer ${token}`}}); second.on('error', () => {});
  const [, res] = await once(second, 'unexpected-response'); assert.equal(res.statusCode, 429); res.resume(); second.terminate();
  const out = Buffer.alloc(2, 1); complete(response(out));
  await new Promise(resolve => setTimeout(resolve, 20));
  assert(captured!.every(value => value === 0)); assert(out.every(value => value === 0));
});
