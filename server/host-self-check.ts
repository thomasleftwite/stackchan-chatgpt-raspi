// Packaged offline test: no Gemini connection, microphone, or USB open.
import {once} from 'node:events';
import {randomBytes} from 'node:crypto';
import assert from 'node:assert/strict';
import {createGeminiServer} from './gemini-server.js';
import {runGeminiProtocolProbe} from './gemini-probe-client.js';
import {runIsolatedTurn} from './gemini-isolated.js';
import {GeminiFailure} from './gemini-turn.js';

const token = randomBytes(32).toString('hex');
let calls = 0;
const reply = Buffer.alloc(12001*2);
const app = createGeminiServer({deviceToken:token, runTurn:async input => {
  assert.equal(input.length, 1280); ++calls;
  return {pcm:Buffer.from(reply),sampleRate:24000,chunks:1,elapsedMs:0};
}});
try {
  app.server.listen(0,'127.0.0.1'); await once(app.server,'listening');
  const address=app.server.address(); if (!address || typeof address==='string') throw new Error();
  const http=`http://127.0.0.1:${address.port}`;
  assert.equal((await fetch(http+'/healthz')).status,200);
  assert.equal((await fetch(http+'/live')).status,404);
  const result=await runGeminiProtocolProbe(http.replace('http:','ws:')+'/live',token,Buffer.alloc(1280));
  assert.equal(result.pcm.length,reply.length); assert.equal(calls,1);
  // Invalid audio is rejected before SDK connection; this also verifies that
  // the packaged Node can fork its bundled worker and import the SDK offline.
  let isolated=false;
  try { await runIsolatedTurn({config:{apiKey:'packaging-test-key-unused',model:'gemini-3.8-live'},input:{pcm:Buffer.alloc(0)}}); }
  catch(error) { isolated=error instanceof GeminiFailure && error.code==='CONFIG'; }
  assert(isolated);
  console.info(JSON.stringify({status:'PASS',loopback:true,pcmSamples:12001,worker:true,apiCalls:0}));
} catch { console.info(JSON.stringify({status:'FAIL',apiCalls:0})); process.exitCode=1; }
finally { await app.close(); }
