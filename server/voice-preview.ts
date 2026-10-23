// Stopped-host audition: bounded single request over stdin; no audio files/logs.
import {once} from 'node:events';
import {createInterface} from 'node:readline';
import {loadGeminiConfig} from './private-config.js';
import {VoiceControl} from './voice-control.js';
import {runIsolatedTurn} from './gemini-isolated.js';
import {failureDetails} from './gemini-turn.js';
const input=createInterface({input:process.stdin});
const deadline=setTimeout(()=>process.exit(1),50000);
let voices:VoiceControl|undefined;
try {
  const [line]=await once(input,'line');
  if(line.length>1024) throw new Error();
  const request=JSON.parse(line) as {id:number;voice:string};
  voices=new VoiceControl(await loadGeminiConfig(),runIsolatedTurn);
  const result=await voices.preview(request.id,request.voice);
  console.info(JSON.stringify({event:'preview-audio',id:request.id,voice:request.voice,pcm:result.pcm.toString('base64')}));result.pcm.fill(0);
} catch(error) {console.info(JSON.stringify({event:'preview-failed',...failureDetails(error)}));process.exitCode=1;}
finally {voices?.close();clearTimeout(deadline);input.close();}
