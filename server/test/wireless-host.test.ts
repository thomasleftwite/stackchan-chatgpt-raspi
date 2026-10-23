import {test, type TestContext} from 'node:test';
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {once} from 'node:events';
import {createServer} from 'node:net';
import {createInterface} from 'node:readline';
import {setTimeout as delay} from 'node:timers/promises';
import {fileURLToPath} from 'node:url';
import {WebSocket} from 'ws';
import {runGeminiProtocolProbe} from '../gemini-probe-client.js';
import {encodePcm} from '../protocol.js';

const host = '127.0.0.1';
const subnet = '127.0.0.1/32';

async function reservePort() {
  const server = createServer();
  server.listen(0, host); await once(server, 'listening');
  const address = server.address(); assert(address && typeof address !== 'string');
  return {port: address.port, close: () => new Promise<void>(resolve => server.close(() => resolve()))};
}

function launch(t: TestContext, raw: string) {
  // Never inherit API credentials, NODE_OPTIONS, or a private configuration path.
  const child = spawn(process.execPath, [fileURLToPath(new URL('../wireless-host.js', import.meta.url))], {
    env: {PATH: process.env.PATH ?? '', ...(process.env.SystemRoot ? {SystemRoot: process.env.SystemRoot} : {})},
    stdio: ['pipe', 'pipe', 'pipe'],
  });
  const closed = once(child, 'close');
  const events: Array<{event: string}> = [];
  let stderr = '';
  child.stderr.on('data', data => {stderr += String(data);});
  child.stdin.on('error', () => {});
  createInterface({input: child.stdout}).on('line', line => {events.push(JSON.parse(line));});
  t.after(async () => {
    if (child.exitCode === null && child.signalCode === null) child.kill('SIGKILL');
    await closed;
  });
  child.stdin.write(raw + '\n');
  return {child, closed, events, stderr: () => stderr, ready: async () => {
    const deadline = Date.now() + 3000;
    while (!events.some(event => event.event === 'ready')) {
      assert.equal(child.exitCode, null, 'Host exited before ready');
      assert(Date.now() < deadline, 'Host readiness deadline exceeded');
      await delay(10);
    }
  }};
}

async function fixture(t: TestContext, port: number) {
  const app = launch(t, JSON.stringify({host, port, subnet, fixture: true}));
  await app.ready(); return app;
}

test('fixture process serves health and 16kHz/24kHz PCM, stops on stdin EOF, and reuses port', async t => {
  const reservation = await reservePort(); const port = reservation.port; await reservation.close();
  for (let cycle = 0; cycle < 2; ++cycle) {
    const app = await fixture(t, port);
    const response = await fetch(`http://${host}:${port}/healthz`);
    assert.equal(response.status, 200);
    assert.deepEqual(await response.json(), {status: 'ok', mode: 'gemini-live', protocolVersion: 2});
    const output = await runGeminiProtocolProbe(`ws://${host}:${port}/live`, '', Buffer.alloc(640));
    assert.equal(output.pcm.length, 1922); assert.equal(output.frames, 3);
    assert.deepEqual(output.pcm, Buffer.alloc(1922));
    app.child.stdin.end();
    assert.deepEqual(await app.closed, [0, null]);
    assert.equal(app.stderr(), '');
  }
});

for (const signal of ['SIGTERM', 'SIGINT'] as const) {
  test(`fixture stops on ${signal} with an active websocket and releases port`, {skip: process.platform === 'win32'}, async t => {
    const reservation = await reservePort(); const port = reservation.port; await reservation.close();
    const app = await fixture(t, port);
    const ws = new WebSocket(`ws://${host}:${port}/live`);
    ws.on('error', () => {}); t.after(() => ws.terminate());
    await once(ws, 'message');
    const disconnected = once(ws, 'close');
    app.child.kill(signal);
    assert.deepEqual(await app.closed, [0, null]); await disconnected;
    const restarted = await fixture(t, port);
    restarted.child.stdin.end(); assert.deepEqual(await restarted.closed, [0, null]);
    assert.equal(app.stderr(), ''); assert.equal(restarted.stderr(), '');
  });
}

test('occupied port fails safely without stopping the original host', async t => {
  const reservation = await reservePort(); await reservation.close();
  const first = await fixture(t, reservation.port);
  const second = launch(t, JSON.stringify({host, port: reservation.port, subnet, fixture: true}));
  assert.deepEqual(await second.closed, [1, null]);
  assert.deepEqual(second.events, [{event: 'failed'}]); assert.equal(second.stderr(), '');
  assert.equal((await fetch(`http://${host}:${reservation.port}/healthz`)).status, 200);
  first.child.stdin.end(); assert.deepEqual(await first.closed, [0, null]);
});

test('loopback requires an explicit boolean fixture and exact /32 boundary; unsafe inputs fail', async t => {
  for (const input of [
    {host, port: 48443, subnet},
    {host, port: 48443, subnet, fixture: false},
    {host, port: 48443, subnet, fixture: 'true'},
    {host, port: 48443, subnet: '127.0.0.0/24', fixture: true},
    {host: '0.0.0.0', port: 48443, subnet, fixture: true},
    {host: '8.8.8.8', port: 48443, subnet: '8.8.8.8/32', fixture: true},
    {host, port: 80, subnet, fixture: true},
    null,
  ]) {
    const app = launch(t, JSON.stringify(input));
    assert.deepEqual(await app.closed, [1, null]);
    assert.deepEqual(app.events, [{event: 'failed'}]); assert.equal(app.stderr(), '');
  }
  const malformed = launch(t, '{invalid');
  assert.deepEqual(await malformed.closed, [1, null]);
  assert.deepEqual(malformed.events, [{event: 'failed'}]); assert.equal(malformed.stderr(), '');
});

async function waitFor(check: () => boolean, label: string) {
  const deadline = Date.now() + 3000;
  while (!check()) {
    assert(Date.now() < deadline, label);
    await delay(10);
  }
}

async function peer(t: TestContext, port: number) {
  const ws = new WebSocket(`ws://${host}:${port}/live`);
  const messages: Array<{type: string}> = [];
  let frames = 0;
  ws.on('error', () => {});
  ws.on('message', (raw, binary) => {
    if (binary) ++frames;
    else messages.push(JSON.parse(raw.toString()));
  });
  t.after(() => ws.terminate());
  const received = (type: string) => waitFor(() => messages.some(message => message.type === type), `Missing ${type}`);
  await received('ready');
  const receivedFrames = (count: number) => waitFor(() => frames === count, 'Missing output PCM frame');
  return {ws, received, receivedFrames};
}

const countEvent = (events: Array<{event: string}>, kind: string) => events.filter(event => event.event === kind).length;

async function reusableHost(t: TestContext) {
  const reservation = await reservePort(); await reservation.close();
  const app = await fixture(t, reservation.port);
  return {...app, port: reservation.port};
}

async function completeTurn(port: number) {
  const result = await runGeminiProtocolProbe(`ws://${host}:${port}/live`, '', Buffer.alloc(640));
  assert.equal(result.frames, 3);
  assert.deepEqual(result.pcm, Buffer.alloc(1922));
}

test('one fixture process completes repeated questions and returns to idle after each playback', async t => {
  const app = await reusableHost(t);
  for (let turn = 1; turn <= 3; ++turn) {
    await completeTurn(app.port);
    await waitFor(() => countEvent(app.events, 'session-idle') === turn, 'Host did not return to idle');
    assert.equal(countEvent(app.events, 'session-busy'), turn);
    assert.equal(countEvent(app.events, 'voice-played'), turn);
    assert.equal(app.child.exitCode, null);
  }
  app.child.stdin.end(); assert.deepEqual(await app.closed, [0, null]);
  assert.equal(app.stderr(), '');
});

test('input transport loss releases the fixture session without claiming playback and accepts a fresh question', async t => {
  const app = await reusableHost(t);
  const client = await peer(t, app.port);
  client.ws.send(encodePcm(1, 0, Buffer.alloc(640, 1)));
  await client.received('input_ack');
  const disconnected = once(client.ws, 'close');
  client.ws.terminate(); await disconnected;
  await waitFor(() => countEvent(app.events, 'session-idle') === 1, 'Input disconnect did not release session');
  assert.equal(countEvent(app.events, 'voice-played'), 0);
  await completeTurn(app.port);
  await waitFor(() => countEvent(app.events, 'session-idle') === 2, 'Fresh question did not finish');
  assert.equal(countEvent(app.events, 'voice-played'), 1);
  assert.equal(countEvent(app.events, 'session-busy'), 2);
  app.child.stdin.end(); assert.deepEqual(await app.closed, [0, null]);
  assert.equal(app.stderr(), '');
});

for (const interruption of ['transport-loss', 'stop'] as const) {
  test(`output ${interruption} discards the unfinished fixture reply and permits reconnection`, async t => {
    const app = await reusableHost(t);
    const client = await peer(t, app.port);
    client.ws.send(encodePcm(1, 0, Buffer.alloc(640)));
    await client.received('input_ack');
    client.ws.send(JSON.stringify({type:'input_end', generation:1}));
    await client.received('output_start');
    client.ws.send(JSON.stringify({type:'next', generation:1, sequence:0}));
    await client.receivedFrames(1);
    const disconnected = once(client.ws, 'close');
    if (interruption === 'stop') client.ws.send(JSON.stringify({type:'stop', generation:1}));
    else client.ws.terminate();
    const [code] = await disconnected;
    assert.equal(code, interruption === 'stop' ? 1000 : 1006);
    await waitFor(() => countEvent(app.events, 'session-idle') === 1, 'Output interruption did not release session');
    assert.equal(countEvent(app.events, 'voice-played'), 0);
    await completeTurn(app.port);
    await waitFor(() => countEvent(app.events, 'session-idle') === 2, 'Reconnected question did not finish');
    assert.equal(countEvent(app.events, 'session-busy'), 2);
    assert.equal(countEvent(app.events, 'voice-played'), 1);
    app.child.stdin.end(); assert.deepEqual(await app.closed, [0, null]);
    assert.equal(app.stderr(), '');
  });
}

test('fixture process crash during output releases the port for a fresh host and question', {skip: process.platform === 'win32'}, async t => {
  const app = await reusableHost(t);
  const client = await peer(t, app.port);
  client.ws.send(encodePcm(1, 0, Buffer.alloc(640)));
  await client.received('input_ack');
  client.ws.send(JSON.stringify({type:'input_end', generation:1}));
  await client.received('output_start');
  client.ws.send(JSON.stringify({type:'next', generation:1, sequence:0}));
  await client.receivedFrames(1);
  const disconnected = once(client.ws, 'close');
  app.child.kill('SIGKILL');
  assert.deepEqual(await app.closed, [null, 'SIGKILL']);
  assert.equal((await disconnected)[0], 1006);
  assert.equal(countEvent(app.events, 'voice-played'), 0);
  const restarted = await fixture(t, app.port);
  await completeTurn(app.port);
  await waitFor(() => countEvent(restarted.events, 'session-idle') === 1, 'Restarted host did not finish');
  assert.equal(countEvent(restarted.events, 'voice-played'), 1);
  restarted.child.stdin.end(); assert.deepEqual(await restarted.closed, [0, null]);
  assert.equal(app.stderr(), ''); assert.equal(restarted.stderr(), '');
});
