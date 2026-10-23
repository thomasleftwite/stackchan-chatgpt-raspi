import {once} from 'node:events';
import {randomBytes} from 'node:crypto';
import {loadGeminiConfig} from './private-config.js';
import {runIsolatedTurn} from './gemini-isolated.js';
import {classifyFailure} from './gemini-turn.js';
import {createGeminiServer} from './gemini-server.js';
import {runGeminiProtocolProbe} from './gemini-probe-client.js';

let app: ReturnType<typeof createGeminiServer> | undefined;
let seed: Buffer | undefined, input: Buffer | undefined;
try {
  const config = await loadGeminiConfig();
  const voice = await runIsolatedTurn({config, input:{text:'「こんにちは」とだけ日本語で言ってください。'}, maxPcmBytes:240_000});
  seed = voice.pcm;
  const count = Math.floor(seed.length / 2 * 2 / 3);
  input = Buffer.alloc(Math.ceil(count / 320) * 640);
  // Diagnostic-only 24->16kHz interpolation of generated speech, no human recording.
  for (let i = 0; i < count; ++i) {
    const at = i * 1.5, left = Math.floor(at), right = Math.min(left + 1, seed.length / 2 - 1);
    input.writeInt16LE(Math.round(seed.readInt16LE(left * 2) * (1 - (at - left)) + seed.readInt16LE(right * 2) * (at - left)), i * 2);
  }
  const token = randomBytes(32).toString('hex');
  app = createGeminiServer({deviceToken:token, runTurn:pcm => runIsolatedTurn({config, input:{pcm}})});
  app.server.listen(0, '127.0.0.1'); await once(app.server, 'listening');
  const address = app.server.address();
  if (!address || typeof address === 'string') throw new Error();
  const result = await runGeminiProtocolProbe(`ws://127.0.0.1:${address.port}/live`, token, input);
  console.info(JSON.stringify({stage:'pc-audio-roundtrip', status:'PASS', model:config.model,
    inputRate:16000, inputSamples:input.length / 2, outputRate:24000, outputSamples:result.pcm.length / 2,
    frames:result.frames, inputSource:'generated-test-speech', playbackAck:'simulated'}));
  result.pcm.fill(0);
} catch (error) {
  const safe = classifyFailure(error);
  console.error(JSON.stringify({stage:'pc-audio-roundtrip', status:'FAIL', code:safe.code, httpStatus:safe.status})); process.exitCode = 1;
} finally { seed?.fill(0); input?.fill(0); if (app) await app.close(); }
