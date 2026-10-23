import {test} from 'node:test';
import assert from 'node:assert/strict';
import {VoiceControl,sampleText} from '../voice-control.js';
import {runGeminiTurn,type LiveConnector} from '../gemini-turn.js';
import type {LiveServerMessage} from '@google/genai';
import {createGeminiServer} from '../gemini-server.js';
import {runGeminiProtocolProbe} from '../gemini-probe-client.js';
import {once} from 'node:events';
import {WebSocket} from 'ws';
const config={apiKey:'test-only-unused-credential',model:'gemini-3.8-live',voice:'Kore'};
const reply=()=>({pcm:Buffer.alloc(4),sampleRate:24000 as const,chunks:1,elapsedMs:0});
test('active voice is immutable while next-question choice changes',async()=>{
  const seen:string[]=[];const voice=new VoiceControl(config,async options=>{seen.push(options.config.voice!);return reply();});
  assert(voice.beginTurn());voice.select('Puck');await voice.run(Buffer.alloc(640));
  assert.equal(voice.activeVoice,'Kore');voice.endTurn();assert(voice.beginTurn());await voice.run(Buffer.alloc(640));voice.endTurn();
  assert.deepEqual(seen,['Kore','Puck']);assert.equal(config.voice,'Kore');
});
test('preview reserves host through playback, rejects concurrent conversation, and releases by matching id',async()=>{
  let text='';const voice=new VoiceControl(config,async options=>{text='text' in options.input?options.input.text:'';return reply();});
  const result=await voice.preview(1,'Kore');assert.equal(text,sampleText);assert.equal(result.pcm.length,4);
  assert.equal(voice.beginTurn(),false);voice.finishPreview(2);assert.equal(voice.busy,true);
  voice.finishPreview(1);assert.equal(voice.busy,false);assert(voice.beginTurn());
  await assert.rejects(voice.preview(3,'Kore'));voice.close();
});
test('invalid voices never call a provider and cancelled preview discards late audio',async()=>{
  let calls=0;let release!:(value:ReturnType<typeof reply>)=>void;
  const voice=new VoiceControl(config,async()=>{++calls;return new Promise(resolve=>{release=resolve;});});
  assert.throws(()=>voice.select('Unknown'));await assert.rejects(voice.preview(1,'Unknown'));assert.equal(calls,0);
  const pending=voice.preview(2,'Kore');voice.finishPreview(2);const pcm=Buffer.from([1,2,3,4]);release({...reply(),pcm});
  await assert.rejects(pending,{code:'INTERRUPTED'});assert.deepEqual(pcm,Buffer.alloc(4));assert.equal(voice.busy,false);
});
test('Live connector receives the explicit voice and preview uses a recitation instruction',async()=>{
  let voice='';let instruction='';
  const connector:LiveConnector=async params=>{
    voice=params.config!.speechConfig!.voiceConfig!.prebuiltVoiceConfig!.voiceName!;
    instruction=String(params.config!.systemInstruction);
    return {close(){},sendRealtimeInput(){},sendClientContent(){params.callbacks.onmessage({serverContent:{modelTurn:{parts:[{inlineData:{mimeType:'audio/pcm;rate=24000',data:Buffer.alloc(4).toString('base64')}}]},turnComplete:true}} as LiveServerMessage);}};
  };
  await runGeminiTurn({config,input:{text:sampleText},purpose:'preview',connector});
  assert.equal(voice,'Kore');assert.match(instruction,/そのまま読み上げ/);
});
test('real device protocol snapshots voices, acknowledges playback, and rejects while preview is reserved',async t=>{
  const seen:string[]=[];let played=0;
  const voice=new VoiceControl(config,async options=>{seen.push(options.config.voice!);return reply();});
  const app=createGeminiServer({deviceToken:'',trustedSubnet:'127.0.0.1/32',canStart:()=>!voice.busy,
    onSessionState:active=>{if(active){voice.beginTurn();voice.select('Puck');}else voice.endTurn();},
    onPlayed:()=>{++played;},runTurn:pcm=>voice.run(pcm)});
  app.server.listen(0,'127.0.0.1');await once(app.server,'listening');t.after(async()=>{voice.close();await app.close();});
  const address=app.server.address();assert(address&&typeof address!=='string');const url=`ws://127.0.0.1:${address.port}/live`;
  await runGeminiProtocolProbe(url,'',Buffer.alloc(640));
  await new Promise(resolve=>setTimeout(resolve,10));
  await runGeminiProtocolProbe(url,'',Buffer.alloc(640));
  await new Promise(resolve=>setTimeout(resolve,10));
  assert.deepEqual(seen,['Kore','Puck']);assert.equal(played,2);
  await voice.preview(11,'Kore');const ws=new WebSocket(url);ws.on('error',()=>{});
  const [,response]=await once(ws,'unexpected-response');assert.equal(response.statusCode,429);response.resume();ws.terminate();voice.finishPreview(11);
});
