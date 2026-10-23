import {GoogleGenAI, Modality, type LiveConnectParameters, type Session} from '@google/genai';
import {setTimeout as delay} from 'node:timers/promises';
import type {GeminiConfig} from './private-config.js';

export type LiveSession = Pick<Session, 'sendClientContent' | 'sendRealtimeInput' | 'close'>;
export type LiveConnector = (params: LiveConnectParameters) => Promise<LiveSession>;
export type FailureCode = 'AUTH' | 'QUOTA' | 'MODEL' | 'PERMISSION' | 'CONFIG' | 'SERVER' |
  'TRANSPORT' | 'TIMEOUT' | 'INVALID_AUDIO' | 'EMPTY_AUDIO' | 'OUTPUT_LIMIT' | 'INTERRUPTED' | 'EARLY_CLOSE';
export class GeminiFailure extends Error {
  constructor(public readonly code: FailureCode, public readonly status = 0) { super(code); }
}
/** Error bodies/reasons may contain secrets or user content: classify, never expose. */
export function classifyFailure(error: unknown): GeminiFailure {
  if (error instanceof GeminiFailure) return error;
  const status = error && typeof error === 'object' && 'status' in error && typeof error.status === 'number' ? error.status : 0;
  const message = error instanceof Error ? error.message : typeof error === 'string' ? error : '';
  const code: FailureCode = status === 429 || /quota|resource.exhausted/i.test(message) ? 'QUOTA' :
    status === 401 || /api key not valid|unauthenticated/i.test(message) ? 'AUTH' :
    status === 403 || /permission.denied/i.test(message) ? 'PERMISSION' :
    status === 404 || /model.*not found|not found.*model/i.test(message) ? 'MODEL' :
    status === 400 || /invalid.argument|not supported|unsupported|unknown field/i.test(message) ? 'CONFIG' :
    status >= 500 ? 'SERVER' : 'TRANSPORT';
  return new GeminiFailure(code, Number.isInteger(status) && status >= 100 && status <= 599 ? status : 0);
}

/** Public diagnostics contain classifications only, never provider text. */
export function failureDetails(error: unknown): {code: FailureCode; status: number} {
  const failure = classifyFailure(error);
  const code = ['AUTH','QUOTA','MODEL','PERMISSION','CONFIG','SERVER','TRANSPORT','TIMEOUT',
    'INVALID_AUDIO','EMPTY_AUDIO','OUTPUT_LIMIT','INTERRUPTED','EARLY_CLOSE'].includes(failure.code) ? failure.code : 'TRANSPORT';
  const status = Number.isInteger(failure.status) && failure.status >= 100 && failure.status <= 599 ? failure.status : 0;
  return {code, status};
}

export interface TurnResult {pcm: Buffer; sampleRate: 24000; chunks: number; elapsedMs: number; totalTokens?: number}
export interface TurnOptions {
  config: GeminiConfig;
  input: {text: string} | {pcm: Buffer};
  connector?: LiveConnector;
  timeoutMs?: number;
  maxPcmBytes?: number;
  purpose?: 'preview';
}

/** Bounded single-turn audio response. No transcripts, input or API errors are logged. */
export async function runGeminiTurn(options: TurnOptions): Promise<TurnResult> {
  const {config, input, timeoutMs = 30_000, maxPcmBytes = 480_000} = options;
  if (!Number.isFinite(timeoutMs) || timeoutMs < 20 || timeoutMs > 60_000 ||
      !Number.isInteger(maxPcmBytes) || maxPcmBytes < 2 || maxPcmBytes > 1_440_000)
    throw new GeminiFailure('CONFIG');
  if ('pcm' in input && (!input.pcm.length || input.pcm.length % 2 || input.pcm.length > 160_000))
    throw new GeminiFailure('CONFIG');
  if ('text' in input && (!input.text || input.text.length > 512)) throw new GeminiFailure('CONFIG');
  const controller = new AbortController();
  const started = Date.now();
  let session: LiveSession | undefined, done = false, submitted = false, bytes = 0, totalTokens: number | undefined;
  const chunks: Buffer[] = [];
  const connect = options.connector ?? ((params: LiveConnectParameters) =>
    new GoogleGenAI({apiKey:config.apiKey, vertexai:false, httpOptions:{apiVersion:'v1beta', timeout:10_000, retryOptions:{attempts:1}}}).live.connect(params));
  let finish!: (error?: GeminiFailure) => void;
  const result = new Promise<TurnResult>((resolve, reject) => {
    finish = (error?: GeminiFailure) => {
      if (done) return;
      done = true;
      if (error) reject(error);
      else if (!bytes || bytes % 2) reject(new GeminiFailure(bytes ? 'INVALID_AUDIO' : 'EMPTY_AUDIO'));
      else resolve({pcm:Buffer.concat(chunks), sampleRate:24000, chunks:chunks.length, elapsedMs:Date.now() - started,
        ...(totalTokens === undefined ? {} : {totalTokens})});
    };
  });
  const deadline = setTimeout(() => { controller.abort(); finish(new GeminiFailure('TIMEOUT')); }, timeoutMs);
  void Promise.resolve().then(() => connect({
    model:config.model,
    config:{responseModalities:[Modality.AUDIO], maxOutputTokens:1024,
      ...(config.voice ? {speechConfig:{voiceConfig:{prebuiltVoiceConfig:{voiceName:config.voice}}}} : {}),
      systemInstruction:options.purpose==='preview' ? '音声確認です。入力された日本語の文章だけを、一字も省略・追加せずそのまま読み上げてください。前置きや説明をしないでください。' : 'あなたはスタックちゃんです。日本語で短く1文で答えてください。',
      realtimeInputConfig:{automaticActivityDetection:{disabled:true}}, abortSignal:controller.signal},
    callbacks:{
      onmessage: message => {
        if (done) return;
        try {
          const content = message.serverContent;
          if (message.toolCall || message.goAway) throw new GeminiFailure('EARLY_CLOSE');
          if (content?.interrupted) throw new GeminiFailure('INTERRUPTED');
          const tokens = message.usageMetadata?.totalTokenCount;
          if (tokens !== undefined && Number.isSafeInteger(tokens) && tokens >= 0) totalTokens = tokens;
          for (const part of content?.modelTurn?.parts ?? []) {
            const data = part.inlineData;
            if (!data) continue;
            if (data.mimeType !== 'audio/pcm;rate=24000' || typeof data.data !== 'string' ||
                data.data.length > Math.ceil(maxPcmBytes / 3) * 4 ||
                data.data.length % 4 || !/^[A-Za-z0-9+/]*={0,2}$/.test(data.data))
              throw new GeminiFailure('INVALID_AUDIO');
            const pcm = Buffer.from(data.data, 'base64');
            if (pcm.toString('base64') !== data.data) throw new GeminiFailure('INVALID_AUDIO');
            if (bytes + pcm.length > maxPcmBytes) { pcm.fill(0); throw new GeminiFailure('OUTPUT_LIMIT'); }
            chunks.push(pcm); bytes += pcm.length;
          }
          // Process every part before honoring completion, including a final audio part.
          if (content?.turnComplete) {
            if (!submitted) throw new GeminiFailure('EARLY_CLOSE');
            finish();
          }
        } catch (error) { finish(classifyFailure(error)); }
      },
      onerror: () => finish(new GeminiFailure('TRANSPORT')),
      onclose: event => { if (!done) finish(classifyFailure(new Error(event.reason || 'EARLY_CLOSE'))); },
    },
  })).then(async connection => {
    session = connection;
    if (done) { connection.close(); return; }
    if ('text' in input) {
      submitted = true;
      connection.sendClientContent({turns:[{role:'user', parts:[{text:input.text}]}], turnComplete:true});
    }
    else {
      connection.sendRealtimeInput({activityStart:{}});
      for (let offset = 0; offset < input.pcm.length && !done; offset += 640) {
        connection.sendRealtimeInput({audio:{data:input.pcm.subarray(offset, offset + 640).toString('base64'), mimeType:'audio/pcm;rate=16000'}});
        await delay(20, undefined, {signal:controller.signal});
      }
      if (!done) { submitted = true; connection.sendRealtimeInput({activityEnd:{}}); }
    }
  }).catch(error => { if (!done) finish(classifyFailure(error)); });
  try { return await result; }
  finally {
    clearTimeout(deadline); controller.abort();
    try { session?.close(); } catch { /* Cleanup never reveals provider errors. */ }
    for (const chunk of chunks) chunk.fill(0);
  }
}
