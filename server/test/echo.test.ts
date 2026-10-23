import {test} from 'node:test';
import assert from 'node:assert/strict';
import {once} from 'node:events';
import {WebSocket} from 'ws';
import {createEchoServer} from '../echo.js';
import {encodePcm} from '../protocol.js';
import {runSmoke} from '../smoke.js';

const token = 'test-only-'.padEnd(64, 'x');
async function fixture(t: {after: (fn: () => Promise<void>) => void}, options = {}) {
  const app = createEchoServer({deviceToken: token, ...options});
  app.server.listen(0, '127.0.0.1');
  await once(app.server, 'listening');
  const address = app.server.address();
  assert(address && typeof address !== 'string');
  const http = `http://127.0.0.1:${address.port}`;
  t.after(() => app.close());
  return {app, http, url: http.replace('http:', 'ws:') + '/live'};
}

test('health reveals only mode; missing and incorrect auth are rejected before upgrade', async t => {
  const {http, url} = await fixture(t);
  assert.deepEqual(await (await fetch(http + '/healthz')).json(), {status:'ok', mode:'echo'});
  for (const value of [undefined, 'Bearer wrong']) {
    const ws = new WebSocket(url, {headers: value ? {Authorization:value} : {}});
    ws.on('error', () => {});
    const [, response] = await once(ws, 'unexpected-response');
    assert.equal(response.statusCode, 401);
    response.resume();
    ws.terminate();
  }
});

test('authenticated client receives echo mode and byte-exact PCM, and can stop', async t => {
  const {url} = await fixture(t);
  const ws = new WebSocket(url, {headers: {Authorization:`Bearer ${token}`}});
  ws.on('error', () => {});
  const [ready] = await once(ws, 'message');
  assert.equal(JSON.parse(String(ready)).mode, 'echo');
  const packet = encodePcm(1, 0, Buffer.from([0,128,255,127]));
  ws.send(packet);
  const [echo, binary] = await once(ws, 'message');
  assert.equal(binary, true);
  assert.deepEqual(echo, packet);
  ws.send(JSON.stringify({type:'stop'}));
  const [code] = await once(ws, 'close');
  assert.equal(code, 1000);
});

test('malformed PCM closes connection rather than returning corrupted audio', async t => {
  const {url} = await fixture(t);
  const ws = new WebSocket(url, {headers: {Authorization:`Bearer ${token}`}});
  ws.on('error', () => {});
  await once(ws, 'message');
  ws.send(Buffer.from([1,2,3]));
  const [code] = await once(ws, 'close');
  assert.equal(code, 1003);
});

test('echo has a bounded lifetime even while connected', async t => {
  const {url} = await fixture(t, {sessionMs:150});
  const ws = new WebSocket(url, {headers: {Authorization:`Bearer ${token}`}});
  ws.on('error', () => {});
  await once(ws, 'message');
  const [code] = await once(ws, 'close');
  assert.equal(code, 1000);
});

test('a second connection is refused and capacity is reusable after close', async t => {
  const {url} = await fixture(t);
  const ws = new WebSocket(url, {headers: {Authorization:`Bearer ${token}`}});
  ws.on('error', () => {});
  await once(ws, 'message');
  const second = new WebSocket(url, {headers: {Authorization:`Bearer ${token}`}});
  second.on('error', () => {});
  const [, response] = await once(second, 'unexpected-response');
  assert.equal(response.statusCode, 429);
  response.resume();
  second.terminate();
  ws.close();
  await once(ws, 'close');
  const third = new WebSocket(url, {headers: {Authorization:`Bearer ${token}`}});
  third.on('error', () => {});
  await once(third, 'message');
  third.close();
  await once(third, 'close');
});

test('wrong path and credentials in query strings do not authenticate', async t => {
  const {url} = await fixture(t);
  for (const target of [url.replace('/live', '/other'), url + '?token=' + token]) {
    const ws = new WebSocket(target, {headers:{Authorization:`Bearer ${token}`}});
    ws.on('error', () => {});
    const [, response] = await once(ws, 'unexpected-response');
    assert.equal(response.statusCode, 404);
    response.resume();
    ws.terminate();
  }
});

test('oversized websocket input is rejected with a size error', async t => {
  const {url} = await fixture(t);
  const ws = new WebSocket(url, {headers:{Authorization:`Bearer ${token}`}});
  ws.on('error', () => {});
  await once(ws, 'message');
  ws.send(Buffer.alloc(2048));
  const [code] = await once(ws, 'close');
  assert.equal(code, 1009);
});

test('missing or weak device tokens fail before listening', () => {
  assert.throws(() => createEchoServer({deviceToken:''}), /DEVICE_TOKEN/);
  assert.throws(() => createEchoServer({deviceToken:'short'}), /DEVICE_TOKEN/);
});

test('deployment probe checks known samples end-to-end without a model', async t => {
  const {url} = await fixture(t);
  await runSmoke(url, token);
  await assert.rejects(() => runSmoke(url, token.replace('test', 'bad')));
});
