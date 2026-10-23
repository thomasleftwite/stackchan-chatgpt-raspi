import {readFile, stat} from 'node:fs/promises';

export interface GeminiConfig {apiKey: string; model: string; voice?:string}

/** Read the existing ignored setting, never copy it to another config or log. */
export async function loadGeminiConfig(
  env: NodeJS.ProcessEnv = process.env,
  source: URL = new URL('../../data/secrets.json', import.meta.url),
): Promise<GeminiConfig> {
  let apiKey = env.GEMINI_API_KEY;
  if (!apiKey) {
    try {
      if ((await stat(source)).size > 4096) throw new Error();
      const config: unknown = JSON.parse(await readFile(source, 'utf8'));
      if (config && typeof config === 'object' && 'gemini_api_key' in config && typeof config.gemini_api_key === 'string')
        apiKey = config.gemini_api_key;
    } catch { throw new Error('GEMINI_CONFIG_UNAVAILABLE'); }
  }
  if (!apiKey || !/^[\x21-\x7e]{20,256}$/.test(apiKey)) throw new Error('GEMINI_KEY_INVALID');
  const model = env.GEMINI_MODEL || 'gemini-3.8-live';
  if (!/^gemini-[a-z0-9.-]{1,100}$/.test(model)) throw new Error('GEMINI_MODEL_INVALID');
  const voice=env.GEMINI_VOICE;
  if(voice && !/^[A-Za-z]{1,32}$/.test(voice)) throw new Error('GEMINI_VOICE_INVALID');
  return {apiKey, model,...(voice?{voice}:{})};
}
