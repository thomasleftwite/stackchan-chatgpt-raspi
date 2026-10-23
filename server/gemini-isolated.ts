import {fork} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {GeminiFailure, type TurnOptions, type TurnResult} from './gemini-turn.js';

/** SDK setup cannot reliably be aborted in 2.30.0: isolate each bounded turn. */
export function runIsolatedTurn(options: Omit<TurnOptions, 'connector'>, signal?:AbortSignal): Promise<TurnResult> {
  return new Promise((resolve, reject) => {
    if(signal?.aborted) {reject(new GeminiFailure('INTERRUPTED'));return;}
    const worker = fork(fileURLToPath(new URL('./gemini-worker.js', import.meta.url)), [], {
      stdio:['ignore', 'ignore', 'ignore', 'ipc'], windowsHide:true,
    });
    let settled = false;
    const finish = (error?: GeminiFailure, value?: TurnResult) => {
      if (settled) return;
      settled = true; clearTimeout(timer);signal?.removeEventListener('abort',cancel);
      worker.kill(); // Only this turn's child process; also closes half-open SDK sockets.
      if (error) reject(error); else resolve(value!);
    };
    const timer = setTimeout(() => finish(new GeminiFailure('TIMEOUT')), (options.timeoutMs ?? 30_000) + 2000);
    const cancel=()=>finish(new GeminiFailure('INTERRUPTED'));
    signal?.addEventListener('abort',cancel,{once:true});
    worker.on('error', () => finish(new GeminiFailure('TRANSPORT')));
    worker.on('exit', () => { if (!settled) finish(new GeminiFailure('EARLY_CLOSE')); });
    worker.on('message', (message: unknown) => {
      try {
        if (!message || typeof message !== 'object' || !('ok' in message)) throw new Error();
        if (message.ok === false && 'code' in message && typeof message.code === 'string') {
          const allowed = ['AUTH','QUOTA','MODEL','PERMISSION','CONFIG','SERVER','TRANSPORT','TIMEOUT',
            'INVALID_AUDIO','EMPTY_AUDIO','OUTPUT_LIMIT','INTERRUPTED','EARLY_CLOSE'];
          if (!allowed.includes(message.code)) throw new Error();
          const status = 'status' in message && typeof message.status === 'number' &&
            Number.isInteger(message.status) && message.status >= 100 && message.status <= 599 ? message.status : 0;
          finish(new GeminiFailure(message.code as GeminiFailure['code'], status)); return;
        }
        if (!('pcm' in message) || typeof message.pcm !== 'string' || message.pcm.length > 1_920_000 ||
            !('chunks' in message) || typeof message.chunks !== 'number' ||
            !('elapsedMs' in message) || typeof message.elapsedMs !== 'number') throw new Error();
        const pcm = Buffer.from(message.pcm, 'base64');
        if (!pcm.length || pcm.length % 2 || pcm.length > (options.maxPcmBytes ?? 480_000)) throw new Error();
        const tokens = 'totalTokens' in message && typeof message.totalTokens === 'number' ? message.totalTokens : undefined;
        finish(undefined, {pcm, sampleRate:24000, chunks:message.chunks, elapsedMs:message.elapsedMs,
          ...(tokens === undefined ? {} : {totalTokens:tokens})});
      } catch { finish(new GeminiFailure('INVALID_AUDIO')); }
    });
    worker.send({...options, input:'pcm' in options.input ? {pcm:options.input.pcm.toString('base64')} : options.input});
  });
}
