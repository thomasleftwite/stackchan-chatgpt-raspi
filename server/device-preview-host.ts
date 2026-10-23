// Dedicated one-shot host. Existing device PCM protocol, no firmware or audio logs.
import {createInterface} from 'node:readline';
import {once} from 'node:events';
import {createGeminiServer} from './gemini-server.js';
import {hostBoundary} from './host-boundary.js';
import {loadGeminiConfig} from './private-config.js';
import {runIsolatedTurn} from './gemini-isolated.js';
import {DevicePreview} from './device-preview.js';
import {GeminiFailure} from './gemini-turn.js';

const lines=createInterface({input:process.stdin});
const report=(event:string,more={})=>console.info(JSON.stringify({event,...more}));
let close:(()=>Promise<void>)|undefined;
let preview:DevicePreview|undefined;
let deadline:ReturnType<typeof setTimeout>|undefined;
const inputDeadline=setTimeout(()=>process.exit(1),10000);
try {
  const [raw]=await once(lines,'line');clearTimeout(inputDeadline);
  const value=JSON.parse(raw) as {id:number};const boundary=hostBoundary(value);
  const config=boundary.fixture ? {apiKey:'fixture-only-unused-key',model:'gemini-3.8-live',voice:'Kore'} : await loadGeminiConfig();
  const runner=boundary.fixture ? async()=>({pcm:Buffer.alloc(1922),sampleRate:24000 as const,chunks:1,elapsedMs:0}) : runIsolatedTurn;
  preview=new DevicePreview(value.id,config,runner,report);
  const app=createGeminiServer({deviceToken:'',trustedSubnet:boundary.subnet,
    canStart:()=>preview!.available,
    onHealth:()=>report('device-online'),
    onDisconnect:()=>preview!.session(false),
    onSessionState:active=>{preview!.session(active);report(active?'session-busy':'session-idle');},
    onPlayed:()=>{clearTimeout(deadline);preview!.onPlayed();},
    runTurn:pcm=>preview!.run(pcm)});
  let closing:Promise<void>|undefined;
  const closeOnce=()=>closing ??= app.close();
  close=closeOnce;
  app.server.listen(boundary.port,boundary.host);await once(app.server,'listening');report('ready');
  // No provider request until the terminal sends its explicit trigger recording.
  deadline=setTimeout(()=>{preview!.fail(new GeminiFailure('TIMEOUT'));void closeOnce().catch(()=>{});},120000);
  let stopping=false;
  const stop=async()=>{
    if(stopping)return;stopping=true;clearTimeout(deadline);preview!.close();await closeOnce();process.exit(0);
  };
  lines.once('close',()=>void stop());process.once('SIGTERM',()=>void stop());process.once('SIGINT',()=>void stop());
} catch {
  clearTimeout(inputDeadline);clearTimeout(deadline);preview?.close();report('failed');lines.close();
  if(close)await close().catch(()=>{});process.exitCode=1;
}
