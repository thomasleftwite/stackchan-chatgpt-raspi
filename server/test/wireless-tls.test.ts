import test from 'node:test';
import assert from 'node:assert/strict';
import {once} from 'node:events';
import {connect} from 'node:tls';
import {WebSocket} from 'ws';
import {runGeminiProtocolProbe} from '../gemini-probe-client.js';
import {createGeminiServer} from '../gemini-server.js';
const key='1234567890abcdef1234567890abcdef';
const tlsOptions={minVersion:'TLSv1.2' as const,maxVersion:'TLSv1.2' as const,ciphers:'DHE-PSK-AES128-GCM-SHA256',
  rejectUnauthorized:false,
  pskCallback:()=>({identity:'stackchan-v1',psk:Buffer.from(key,'hex')})};
// With PSK the TLS Finished messages authenticate the peer, not an X.509 certificate.
test('wireless TLS authenticates PSK, enforces bearer token and completes existing PCM protocol',async t=>{
 const app=createGeminiServer({deviceToken:key,tlsPsk:{identity:'stackchan-v1',keyHex:key},runTurn:async()=>({pcm:Buffer.alloc(2),sampleRate:24000,chunks:1,elapsedMs:0})});
 app.server.listen(0,'127.0.0.1');await once(app.server,'listening');t.after(()=>app.close());
 const address=app.server.address();assert(address&&typeof address!=='string');
 const socket=connect({host:'127.0.0.1',port:address.port,...tlsOptions});await once(socket,'secureConnect');
 assert.equal(socket.getCipher().standardName,'TLS_DHE_PSK_WITH_AES_128_GCM_SHA256');socket.destroy();
 const wrong=connect({host:'127.0.0.1',port:address.port,...tlsOptions,pskCallback:()=>({identity:'stackchan-v1',psk:Buffer.alloc(16)})});
 await assert.rejects(once(wrong,'secureConnect'));wrong.destroy();
 const denied=new WebSocket(`wss://127.0.0.1:${address.port}/live`,tlsOptions);denied.on('error',()=>{});
 const [,res]=await once(denied,'unexpected-response');assert.equal(res.statusCode,401);res.resume();denied.terminate();
 const ws=new WebSocket(`wss://127.0.0.1:${address.port}/live`,{...tlsOptions,headers:{Authorization:`Bearer ${key}`}});
 const [raw]=await once(ws,'message');assert.equal(JSON.parse(raw.toString()).type,'ready');ws.terminate();
 await new Promise(resolve=>setTimeout(resolve,30));
 const result=await runGeminiProtocolProbe(`wss://127.0.0.1:${address.port}/live`,key,Buffer.alloc(640),key);assert.equal(result.pcm.length,2);
});
test('invalid or weak pairing credentials are rejected',()=>{
 assert.throws(()=>createGeminiServer({deviceToken:key,tlsPsk:{identity:'stackchan-v1',keyHex:'12345678'},runTurn:async()=>{throw new Error();}}));
});
