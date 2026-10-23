import {test,type TestContext} from 'node:test';
import assert from 'node:assert/strict';
import {once} from 'node:events';
import {spawn} from 'node:child_process';
import {createInterface} from 'node:readline';
import {fileURLToPath} from 'node:url';
import {setTimeout as delay} from 'node:timers/promises';
import {createServer} from 'node:net';
import {WebSocket} from 'ws';
import {DevicePreview} from '../device-preview.js';
import {createGeminiServer} from '../gemini-server.js';
import {sampleText} from '../voice-control.js';
import {GeminiFailure} from '../gemini-turn.js';
import {runGeminiProtocolProbe} from '../gemini-probe-client.js';
import {encodePcm} from '../protocol.js';

const config={apiKey:'fixture-only-unused-key',model:'gemini-3.8-live',voice:'Kore'};
const result=()=>({pcm:Buffer.alloc(1922),sampleRate:24000 as const,chunks:1,elapsedMs:0});

test('device audition discards trigger PCM and submits fixed text with the candidate voice only',async()=>{
  const events:object[]=[];let calls=0;
  const preview=new DevicePreview(5,config,async options=>{
    ++calls;assert.deepEqual(options.input,{text:sampleText});assert.equal(options.purpose,'preview');
    assert.equal(options.config.voice,'Kore');return result();
  },(event,fields)=>events.push({event,...fields}));
  assert(preview.available);preview.onPlayed();assert.equal(events.length,0);
  preview.session(true);assert(!preview.available);
  const input=Buffer.alloc(640,17);await preview.run(input);
  assert.deepEqual(input,Buffer.alloc(640));assert.equal(calls,1);
  assert.deepEqual(events,[{event:'preview-generating',id:5},{event:'preview-output',id:5}]);
  preview.onPlayed();preview.onPlayed();preview.session(false);preview.close();
  assert.deepEqual(events.at(-1),{event:'preview-played',id:5});assert.equal(events.length,3);
});

test('disconnect while generating aborts and wipes late audio without claiming playback',async()=>{
  let release!:(value:ReturnType<typeof result>)=>void;let signal:AbortSignal|undefined;
  const events:object[]=[];
  const preview=new DevicePreview(2,config,async(_options,s)=>{signal=s;return new Promise(resolve=>{release=resolve;});},
    (event,fields)=>events.push({event,...fields}));
  preview.session(true);const pending=preview.run(Buffer.alloc(640));
  preview.session(false);assert(signal?.aborted);
  const pcm=Buffer.alloc(10,123);release({...result(),pcm});
  await assert.rejects(pending,{code:'INTERRUPTED'});assert.deepEqual(pcm,Buffer.alloc(10));
  preview.onPlayed();assert.deepEqual(events,[{event:'preview-generating',id:2},{event:'preview-failed',id:2,code:'INTERRUPTED',status:0}]);
});

test('invalid id or voice fails before provider and provider failures expose fixed classification only',async()=>{
  let calls=0;const runner=async()=>{++calls;throw new GeminiFailure('AUTH',401);};
  for(const id of [0,-1,2**53]) assert.throws(()=>new DevicePreview(id,config,runner,()=>{}));
  assert.throws(()=>new DevicePreview(1,{...config,voice:'Unknown'},runner,()=>{}));assert.equal(calls,0);
  const events:object[]=[];const preview=new DevicePreview(1,config,runner,(event,fields)=>events.push({event,...fields}));
  preview.session(true);await assert.rejects(preview.run(Buffer.alloc(640)),{code:'AUTH'});
  assert.deepEqual(events.at(-1),{event:'preview-failed',id:1,code:'AUTH',status:401});
  preview.onPlayed();assert.equal(events.length,2);
});

async function waitFor(check:()=>boolean) {
  const end=Date.now()+3000;
  while(!check()) {assert(Date.now()<end,'Missing preview event');await delay(10);}
}
async function port() {
  const s=createServer();s.listen(0,'127.0.0.1');await once(s,'listening');
  const a=s.address();assert(a&&typeof a!=='string');await new Promise<void>(resolve=>s.close(()=>resolve()));return a.port;
}
function launch(t:TestContext,value:unknown) {
  const child=spawn(process.execPath,[fileURLToPath(new URL('../device-preview-host.js',import.meta.url))],{
    env:{PATH:process.env.PATH??'',...(process.env.SystemRoot?{SystemRoot:process.env.SystemRoot}:{})},stdio:['pipe','pipe','pipe']});
  const closed=once(child,'close');const events:Array<{event:string;id?:number;code?:string}>=[];let stderr='';
  createInterface({input:child.stdout}).on('line',line=>events.push(JSON.parse(line)));
  child.stderr.on('data',data=>{stderr+=String(data);});child.stdin.on('error',()=>{});
  t.after(async()=>{if(child.exitCode===null&&child.signalCode===null)child.kill('SIGKILL');await closed;});
  child.stdin.write(JSON.stringify(value)+'\n');
  return {child,closed,events,stderr:()=>stderr,ready:()=>waitFor(()=>events.some(e=>e.event==='ready'))};
}

test('real terminal disconnect aborts generation before deferred session-idle',async t=>{
  let signal:AbortSignal|undefined;const events:object[]=[];
  const preview=new DevicePreview(6,config,async(_options,s)=>{
    signal=s;return new Promise((_resolve,reject)=>s!.addEventListener('abort',()=>reject(new GeminiFailure('INTERRUPTED')),{once:true}));
  },(event,fields)=>events.push({event,...fields}));
  const options={deviceToken:'',trustedSubnet:'127.0.0.1/32',canStart:()=>preview.available,
    onSessionState:(active:boolean)=>preview.session(active),onDisconnect:()=>preview.session(false),
    onPlayed:()=>preview.onPlayed(),runTurn:(input:Buffer)=>preview.run(input)};
  const app=createGeminiServer(options);app.server.listen(0,'127.0.0.1');await once(app.server,'listening');
  t.after(async()=>{preview.close();await app.close();});
  const a=app.server.address();assert(a&&typeof a!=='string');
  const ws=new WebSocket(`ws://127.0.0.1:${a.port}/live`);ws.on('error',()=>{});t.after(()=>ws.terminate());
  const messages:Array<{type:string}>=[];ws.on('message',(raw,binary)=>{if(!binary)messages.push(JSON.parse(raw.toString()));});
  await waitFor(()=>messages.some(m=>m.type==='ready'));
  ws.send(encodePcm(1,0,Buffer.alloc(640)));await waitFor(()=>messages.some(m=>m.type==='input_ack'));
  ws.send(JSON.stringify({type:'input_end',generation:1}));await waitFor(()=>!!signal);
  const closed=once(ws,'close');ws.terminate();await closed;
  await waitFor(()=>!!signal?.aborted);
  assert.deepEqual(events,[{event:'preview-generating',id:6},{event:'preview-failed',id:6,code:'INTERRUPTED',status:0}]);
});

test('dedicated fixture uses existing terminal protocol and reports success only after played; one turn only',async t=>{
  const p=await port();const app=launch(t,{host:'127.0.0.1',subnet:'127.0.0.1/32',port:p,fixture:true,id:7});await app.ready();
  assert(!app.events.some(e=>e.event==='preview-generating'));
  const output=await runGeminiProtocolProbe(`ws://127.0.0.1:${p}/live`,'',Buffer.alloc(640,13));
  assert.deepEqual(output.pcm,Buffer.alloc(1922));
  await waitFor(()=>app.events.some(e=>e.event==='session-idle'));
  assert.deepEqual(app.events.filter(e=>e.event.startsWith('preview-')),[
    {event:'preview-generating',id:7},{event:'preview-output',id:7},{event:'preview-played',id:7}]);
  const ws=new WebSocket(`ws://127.0.0.1:${p}/live`);ws.on('error',()=>{});
  const [,response]=await once(ws,'unexpected-response');assert.equal(response.statusCode,429);response.resume();ws.terminate();
  app.child.stdin.end();assert.deepEqual(await app.closed,[0,null]);assert.equal(app.stderr(),'');
  assert(!JSON.stringify(app.events).includes('pcm'));assert(!JSON.stringify(app.events).includes(config.voice));
});

test('interrupted output never reports audition success and the port is reusable',async t=>{
  const p=await port();const options={host:'127.0.0.1',subnet:'127.0.0.1/32',port:p,fixture:true,id:8};
  const app=launch(t,options);await app.ready();
  const ws=new WebSocket(`ws://127.0.0.1:${p}/live`);ws.on('error',()=>{});
  const messages:Array<{type:string}>=[];ws.on('message',(raw,binary)=>{if(!binary)messages.push(JSON.parse(raw.toString()));});
  await waitFor(()=>messages.some(m=>m.type==='ready'));
  ws.send(encodePcm(1,0,Buffer.alloc(640)));await waitFor(()=>messages.some(m=>m.type==='input_ack'));
  ws.send(JSON.stringify({type:'input_end',generation:1}));await waitFor(()=>messages.some(m=>m.type==='output_start'));
  const closed=once(ws,'close');ws.terminate();await closed;
  await waitFor(()=>app.events.some(e=>e.event==='preview-failed'));
  assert(!app.events.some(e=>e.event==='preview-played'));
  app.child.stdin.end();assert.deepEqual(await app.closed,[0,null]);
  const restarted=launch(t,options);await restarted.ready();restarted.child.stdin.end();assert.deepEqual(await restarted.closed,[0,null]);
});

test('dedicated audition rejects unsafe boundaries and missing or invalid request ids',async t=>{
  for(const change of [{fixture:false},{subnet:'127.0.0.0/24'},{host:'0.0.0.0'},{id:0},{id:true},{id:null}]) {
    const app=launch(t,{host:'127.0.0.1',subnet:'127.0.0.1/32',port:48443,fixture:true,id:1,...change});
    assert.deepEqual(await app.closed,[1,null]);assert.deepEqual(app.events,[{event:'failed'}]);assert.equal(app.stderr(),'');
  }
});
