import {createEchoServer} from './echo.js';

const port = Number(process.env.PORT ?? '8080');
if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Error('Invalid PORT');
const probe = createEchoServer({deviceToken:process.env.DEVICE_TOKEN ?? ''});
probe.server.listen(port, '0.0.0.0', () => console.info('Stackchan echo service listening'));
probe.server.on('error', () => { console.error('Server start failed'); process.exitCode = 1; });
let closing = false;
function shutdown() {
  if (closing) return;
  closing = true;
  const deadline = setTimeout(() => process.exit(1), 5000);
  deadline.unref();
  void probe.close().then(() => clearTimeout(deadline)).catch(() => { process.exitCode = 1; });
}
process.on('SIGTERM', shutdown);
process.on('SIGINT', shutdown);
