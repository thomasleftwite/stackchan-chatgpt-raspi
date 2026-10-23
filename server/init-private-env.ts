import {randomBytes} from 'node:crypto';
import {writeFile} from 'node:fs/promises';

try {
  await writeFile(new URL('../.env', import.meta.url),
    `# Local private settings. Gemini key is read from ../data/secrets.json.\nDEVICE_TOKEN=${randomBytes(32).toString('hex')}\nHOST=127.0.0.1\nPORT=8080\n`,
    {flag:'wx', mode:0o600});
  console.info('Private device configuration created; values hidden');
} catch (error) {
  if (error && typeof error === 'object' && 'code' in error && error.code === 'EEXIST')
    console.info('Existing private configuration preserved');
  else { console.error('Private configuration could not be created'); process.exitCode = 1; }
}
