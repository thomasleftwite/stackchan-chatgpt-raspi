import {loadGeminiConfig} from './private-config.js';
import {classifyFailure} from './gemini-turn.js';
import {runIsolatedTurn} from './gemini-isolated.js';

try {
  const config = await loadGeminiConfig();
  const response = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${config.model}`, {
    headers:{'x-goog-api-key':config.apiKey}, signal:AbortSignal.timeout(10_000), redirect:'error',
  });
  console.info(JSON.stringify({stage:'model-metadata', model:config.model, status:response.status}));
  if (!response.ok) {
    const payload = await response.json().catch(() => ({})) as {error?:{message?:string}};
    throw classifyFailure(Object.assign(new Error(payload.error?.message ?? ''), {status:response.status}));
  }
  await response.body?.cancel();
  const turn = await runIsolatedTurn({config, input:{text:'接続テストです。「こんにちは」とだけ日本語で答えてください。'}});
  console.info(JSON.stringify({stage:'live-response', status:'PASS', model:config.model,
    sampleRate:turn.sampleRate, samples:turn.pcm.length / 2, chunks:turn.chunks, elapsedMs:turn.elapsedMs,
    ...(turn.totalTokens === undefined ? {} : {totalTokens:turn.totalTokens})}));
  turn.pcm.fill(0);
} catch (error) {
  const safe = classifyFailure(error);
  console.error(JSON.stringify({stage:'gemini-check', status:'FAIL', code:safe.code, httpStatus:safe.status}));
  process.exitCode = 1;
}
