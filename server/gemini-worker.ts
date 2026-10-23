import {classifyFailure, runGeminiTurn, type TurnOptions} from './gemini-turn.js';

// Internal IPC only. No stdout/stderr, transcripts, audio files, or credential logs.
const deadline = setTimeout(() => process.exit(1), 65_000);
process.once('disconnect', () => process.exit(1));
process.once('message', async (raw: TurnOptions & {input: {text:string} | {pcm:string}}) => {
  try {
    const input = 'pcm' in raw.input ? {pcm:Buffer.from(raw.input.pcm as unknown as string, 'base64')} : raw.input;
    const result = await runGeminiTurn({...raw, input});
    process.send?.({ok:true, pcm:result.pcm.toString('base64'), chunks:result.chunks,
      elapsedMs:result.elapsedMs, totalTokens:result.totalTokens}, () => {
      result.pcm.fill(0); if ('pcm' in input) input.pcm.fill(0);
      clearTimeout(deadline); process.exit(0);
    });
  } catch (error) {
    const safe = classifyFailure(error);
    process.send?.({ok:false, code:safe.code, status:safe.status}, () => process.exit(1));
  }
});
