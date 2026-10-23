import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp, mkdir, writeFile, unlink, rmdir} from 'node:fs/promises';
import {join} from 'node:path';
import {pathToFileURL, fileURLToPath} from 'node:url';
import {loadGeminiConfig} from '../private-config.js';

test('Gemini config reads a designated private file without requiring OpenAI', async () => {
  const base = fileURLToPath(new URL('../../../.pio/host-tests/', import.meta.url));
  await mkdir(base, {recursive:true});
  const folder = await mkdtemp(join(base, 'config-test-'));
  const path = join(folder, 'test-settings.json');
  try {
    await writeFile(path, JSON.stringify({gemini_api_key:'test-only-key-not-a-credential'}));
    const config = await loadGeminiConfig({}, pathToFileURL(path));
    assert.equal(config.model, 'gemini-3.8-live');
    assert.equal(config.apiKey, 'test-only-key-not-a-credential');
    await writeFile(path, JSON.stringify({gemini_api_key:'hidden\nheader'}));
    await assert.rejects(loadGeminiConfig({}, pathToFileURL(path)), {message:'GEMINI_KEY_INVALID'});
    await assert.rejects(loadGeminiConfig({GEMINI_API_KEY:'test-only-key-not-a-credential',GEMINI_MODEL:'bad?key=hidden'}), {message:'GEMINI_MODEL_INVALID'});
  } finally { await unlink(path); await rmdir(folder); }
});
