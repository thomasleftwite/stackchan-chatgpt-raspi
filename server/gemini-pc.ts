import {isIPv4} from 'node:net';
import {loadGeminiConfig} from './private-config.js';
import {createGeminiServer} from './gemini-server.js';
import {runIsolatedTurn} from './gemini-isolated.js';

try {
  const config = await loadGeminiConfig();
  const host = process.env.HOST || '127.0.0.1';
  const octets = host.split('.').map(Number);
  if (!isIPv4(host) || !(host === '127.0.0.1' || octets[0] === 10 ||
      (octets[0] === 172 && octets[1]! >= 16 && octets[1]! <= 31) ||
      (octets[0] === 192 && octets[1] === 168))) throw new Error();
  const port = Number(process.env.PORT || '8080');
  if (!Number.isInteger(port) || port < 1024 || port > 65535) throw new Error();
  const app = createGeminiServer({deviceToken:process.env.DEVICE_TOKEN || '',
    runTurn:pcm => runIsolatedTurn({config, input:{pcm}})});
  app.server.on('error', () => { console.error('Gemini PC service failed (details suppressed)'); process.exit(1); });
  app.server.listen(port, host, () => console.info('Gemini PC service ready; protocol=2; credentials hidden'));
  let closing = false;
  const stop = async () => {
    if (closing) return; closing = true;
    const deadline = setTimeout(() => process.exit(1), 5000); deadline.unref();
    await app.close(); clearTimeout(deadline); process.exit(0);
  };
  process.once('SIGINT', () => void stop()); process.once('SIGTERM', () => void stop());
} catch {
  console.error('Gemini PC service configuration failed (details suppressed)'); process.exitCode = 1;
}
