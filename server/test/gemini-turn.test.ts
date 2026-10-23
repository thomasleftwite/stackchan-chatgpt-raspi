import {test} from 'node:test';
import assert from 'node:assert/strict';
import {runGeminiTurn, GeminiFailure, classifyFailure, failureDetails, type LiveConnector} from '../gemini-turn.js';
import type {LiveConnectParameters, LiveServerMessage} from '@google/genai';

const config = {apiKey:'test-only-key-not-a-credential', model:'gemini-3.8-live'};
test('wireless failure details retain only fixed classification and HTTP status', () => {
  const error=Object.assign(new Error('PRIVATE_PROVIDER_TEXT PRIVATE_KEY'),{status:429});
  assert.deepEqual(failureDetails(error),{code:'QUOTA',status:429});
  assert.equal(JSON.stringify(failureDetails(error)).includes('PRIVATE'),false);
  assert.deepEqual(failureDetails(new GeminiFailure('TIMEOUT')),{code:'TIMEOUT',status:0});
  assert.deepEqual(failureDetails(Object.assign(new GeminiFailure('AUTH'),{code:'PRIVATE_KEY',status:NaN})),{code:'TRANSPORT',status:0});
});
function fake(emit: (p: LiveConnectParameters) => void) {
  let closed = 0;
  const input: unknown[] = [];
  const connector: LiveConnector = async p => ({
    sendClientContent: value => { input.push(value); queueMicrotask(() => emit(p)); },
    sendRealtimeInput: value => { input.push(value); if (value.activityEnd) queueMicrotask(() => emit(p)); },
    close: () => { ++closed; },
  });
  return {connector, input, closed: () => closed};
}
function audio(data: Buffer, extra = {}): LiveServerMessage {
  return {serverContent:{modelTurn:{parts:[{inlineData:{mimeType:'audio/pcm;rate=24000', data:data.toString('base64')}}]}, ...extra}} as LiveServerMessage;
}
test('Gemini collector preserves every audio part including the final part; closes session', async () => {
  const f = fake(p => {
    const first = audio(Buffer.from([0,128]));
    first.serverContent!.modelTurn!.parts!.push({text:'never exposed'}, {inlineData:{mimeType:'audio/pcm;rate=24000', data:Buffer.from([255,127]).toString('base64')}});
    p.callbacks.onmessage(first);
    p.callbacks.onmessage(audio(Buffer.from([1,0]), {turnComplete:true}));
  });
  const result = await runGeminiTurn({config, input:{text:'test'}, connector:f.connector});
  assert.deepEqual(result.pcm, Buffer.from([0,128,255,127,1,0]));
  assert.equal(result.chunks, 3); assert.equal(f.closed(), 1);
});
test('Gemini audio input uses manual activity markers and 16kHz PCM without a WAV header', async () => {
  const f = fake(p => p.callbacks.onmessage(audio(Buffer.alloc(2), {turnComplete:true})));
  await runGeminiTurn({config, input:{pcm:Buffer.alloc(1280)}, connector:f.connector});
  const messages = f.input as {activityStart?:object; activityEnd?:object; audio?:{mimeType:string;data:string}}[];
  assert.deepEqual(messages[0], {activityStart:{}});
  assert.deepEqual(messages.at(-1), {activityEnd:{}});
  assert.equal(messages.filter(m => m.audio).length, 2);
  assert.equal(messages[1]!.audio!.mimeType, 'audio/pcm;rate=16000');
  assert.equal(Buffer.from(messages[1]!.audio!.data, 'base64').length, 640);
});
test('Gemini collector fails closed on empty, wrong-format, oversized and interrupted output', async () => {
  for (const kind of ['empty','mime','limit','interrupted','base64']) {
    const f = fake(p => {
      const message = audio(Buffer.alloc(8), {turnComplete:true});
      if (kind === 'empty') message.serverContent!.modelTurn = {parts:[]};
      if (kind === 'mime') message.serverContent!.modelTurn!.parts![0]!.inlineData!.mimeType = 'audio/pcm;rate=16000';
      if (kind === 'interrupted') message.serverContent!.interrupted = true;
      if (kind === 'base64') message.serverContent!.modelTurn!.parts![0]!.inlineData!.data = '!!!!';
      p.callbacks.onmessage(message);
    });
    await assert.rejects(runGeminiTurn({config, input:{text:'test'}, connector:f.connector, maxPcmBytes:4}), GeminiFailure);
    assert.equal(f.closed(), 1);
  }
});
test('Gemini deadlines close late sessions and redact provider errors', async () => {
  let closed = 0;
  const connector: LiveConnector = () => new Promise(resolve => setTimeout(() => resolve({
    close: () => { ++closed; }, sendClientContent: () => {}, sendRealtimeInput: () => {},
  }), 45));
  await assert.rejects(runGeminiTurn({config, input:{text:'test'}, connector, timeoutMs:20}), {code:'TIMEOUT'});
  await new Promise(resolve => setTimeout(resolve, 60)); assert.equal(closed, 1);
  const error = classifyFailure(Object.assign(new Error('secret body quota exhausted'), {status:429}));
  assert.equal(error.code, 'QUOTA'); assert.equal(error.message, 'QUOTA');
});
