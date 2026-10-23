import {createInterface} from 'node:readline';
import {isIPv4} from 'node:net';
import {once} from 'node:events';
import {createGeminiServer,hotspotPeerAllowed} from './gemini-server.js';
import {loadGeminiConfig} from './private-config.js';
import {runIsolatedTurn} from './gemini-isolated.js';
import {failureDetails} from './gemini-turn.js';
import {VoiceControl} from './voice-control.js';

// Only parent stdin supplies pairing credentials. Never write them to stdout.
const lines=createInterface({input:process.stdin});
const report=(event:string, more={})=>console.info(JSON.stringify({event,...more}));
let close:(()=>Promise<void>)|undefined;
const timer=setTimeout(()=>process.exit(1),10000);
try {
  const [raw]=await once(lines,'line'); clearTimeout(timer);
  const value=JSON.parse(raw) as {host:string;port:number;subnet:string;fixture?:boolean};
  const ip=value.host?.split('.').map(Number);
  if(!isIPv4(value.host) || !(ip[0]===10 || (ip[0]===172 && ip[1]!>=16 && ip[1]!<=31) || (ip[0]===192 && ip[1]===168)) ||
     !Number.isInteger(value.port) || value.port<1024 || value.port>65535 || !value.subnet) throw new Error();
  if(!hotspotPeerAllowed(value.host,value.subnet)) throw new Error();
  const config=value.fixture ? undefined : await loadGeminiConfig();
  const voices=config ? new VoiceControl(config,runIsolatedTurn) : undefined;
  if(config?.voice) voices!.select(config.voice);
  lines.on('line',line=>{
    if(!voices || line.length>1024) return;
    try {
      const cmd=JSON.parse(line) as {type:string;id:number;voice:string};
      if(!Number.isSafeInteger(cmd.id) || cmd.id<=0) return;
      if(cmd.type==='voice') {voices.select(cmd.voice);report('voice-selected',{id:cmd.id,voice:voices.selected});}
      else if(cmd.type==='preview-stop' || cmd.type==='preview-done') {voices.finishPreview(cmd.id);report('preview-stopped',{id:cmd.id});}
      else if(cmd.type==='preview') {
        void voices.preview(cmd.id,cmd.voice).then(result=>{
          report('preview-audio',{id:cmd.id,voice:cmd.voice,pcm:result.pcm.toString('base64')});result.pcm.fill(0);
        }).catch(error=>report('preview-failed',{id:cmd.id,...failureDetails(error)}));
      }
    } catch {report('voice-failed');}
  });
  let lastHealth=0;
  const app=createGeminiServer({deviceToken:'',trustedSubnet:value.subnet,
    canStart:()=>!voices?.busy,
    onBusy:()=>report('preview-conflict'),
    onPlayed:()=>report('voice-played',{voice:voices?.activeVoice ?? '',model:config?.model ?? ''}),
    onSessionState:active=>{
      if(active) {voices?.beginTurn();report('session-busy',{voice:voices?.activeVoice ?? ''});}
      else {voices?.endTurn();report('session-idle');}
    },
    onHealth:()=>{if(Date.now()-lastHealth>10000){lastHealth=Date.now();report('device-online');}},
    runTurn:async pcm=>{
      if(!config) return {pcm:Buffer.alloc(1922),sampleRate:24000,chunks:1,elapsedMs:0};
      try {const voice=voices!.activeVoice;const result=await voices!.run(pcm);report('turn-complete',{voice,model:config.model});return result;}
      catch (error) {report('turn-failed',failureDetails(error));throw new Error('TURN_FAILED');}
    }});
  close=app.close;
  app.server.listen(value.port,value.host);await once(app.server,'listening');report('ready');
  let stopping=false;
  const stop=async()=>{if(stopping)return;stopping=true;voices?.close();await app.close();process.exit(0);};
  lines.once('close',()=>void stop());process.once('SIGTERM',()=>void stop());process.once('SIGINT',()=>void stop());
} catch {clearTimeout(timer);report('failed');lines.close();if(close)await close().catch(()=>{});process.exitCode=1;}
