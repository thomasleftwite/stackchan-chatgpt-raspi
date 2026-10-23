import test from 'node:test';
import assert from 'node:assert/strict';
import {once} from 'node:events';
import {WebSocket} from 'ws';
import {createGeminiServer, hotspotPeerAllowed} from '../gemini-server.js';
import {runGeminiProtocolProbe} from '../gemini-probe-client.js';

test('hotspot trust accepts only its subnet, never the upstream or mapped outsiders',()=>{
 assert(hotspotPeerAllowed('192.168.137.23','192.168.137.0/24'));
 assert(hotspotPeerAllowed('::ffff:192.168.137.23','192.168.137.0/24'));
 assert(!hotspotPeerAllowed('192.168.18.27','192.168.137.0/24'));
 assert(!hotspotPeerAllowed('::ffff:192.168.18.27','192.168.137.0/24'));
 assert(!hotspotPeerAllowed('::1','192.168.137.0/24'));
 for(const subnet of ['0.0.0.0/0','8.8.8.0/24','192.168.137.0/8','invalid'])
  assert.throws(()=>hotspotPeerAllowed('192.168.137.23',subnet));
});
test('trusted hotspot completes PCM without a device code or bearer token',async t=>{
 const app=createGeminiServer({deviceToken:'',trustedSubnet:'127.0.0.1/32',runTurn:async()=>({pcm:Buffer.alloc(2),sampleRate:24000,chunks:1,elapsedMs:0})});
 app.server.listen(0,'127.0.0.1');await once(app.server,'listening');t.after(()=>app.close());
 const address=app.server.address();assert(address&&typeof address!=='string');
 const http=`http://127.0.0.1:${address.port}`;
 assert.equal((await fetch(http+'/healthz')).status,200);
 const result=await runGeminiProtocolProbe(http.replace('http:','ws:')+'/live','',Buffer.alloc(640));
 assert.equal(result.pcm.length,2);
});
test('outside peers cannot reach health or websocket even with a bearer token',async t=>{
 const app=createGeminiServer({deviceToken:'',trustedSubnet:'127.0.0.2/32',runTurn:async()=>{throw new Error('must not run');}});
 app.server.listen(0,'127.0.0.1');await once(app.server,'listening');t.after(()=>app.close());
 const address=app.server.address();assert(address&&typeof address!=='string');
 assert.equal((await fetch(`http://127.0.0.1:${address.port}/healthz`)).status,403);
 const ws=new WebSocket(`ws://127.0.0.1:${address.port}/live`,{headers:{Authorization:'Bearer '+'x'.repeat(32)}});ws.on('error',()=>{});
 const [,response]=await once(ws,'unexpected-response');assert.equal(response.statusCode,403);response.resume();ws.terminate();
});
