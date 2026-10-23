import {VoiceControl, type VoiceRunner} from './voice-control.js';
import {failureDetails, GeminiFailure} from './gemini-turn.js';
import type {GeminiConfig} from './private-config.js';

/** One terminal-initiated turn, fixed recitation only; never submit its recording. */
export class DevicePreview {
  private voices:VoiceControl;
  private connected=false;
  private done=false;
  private played=false;
  private outputReady=false;
  constructor(private id:number,config:GeminiConfig,runner:VoiceRunner,
      private report:(event:string,more:{id:number;code?:string;status?:number})=>void) {
    if(!Number.isSafeInteger(id) || id<=0 || !config.voice) throw new GeminiFailure('CONFIG');
    this.voices=new VoiceControl(config,runner);this.voices.select(config.voice);
  }
  get available() {return !this.connected && !this.done;}
  session(active:boolean) {
    if(active) this.connected=true;
    else if(this.connected && !this.done) this.fail(new GeminiFailure('INTERRUPTED'));
  }
  async run(input:Buffer) {
    input.fill(0);
    if(this.done || !this.connected) throw new GeminiFailure('INTERRUPTED');
    this.report('preview-generating',{id:this.id});
    try {
      const result=await this.voices.preview(this.id,this.voices.selected);
      if(this.done) {result.pcm.fill(0);throw new GeminiFailure('INTERRUPTED');}
      this.outputReady=true;
      this.report('preview-output',{id:this.id});return result;
    } catch(error) {this.fail(error);throw error;}
  }
  onPlayed() {
    if(this.done || this.played || !this.outputReady) return;
    this.played=true;this.done=true;this.voices.finishPreview(this.id);
    this.report('preview-played',{id:this.id});
  }
  fail(error:unknown) {
    if(this.done) return;
    this.done=true;this.voices.close();
    this.report('preview-failed',{id:this.id,...failureDetails(error)});
  }
  close() {this.done=true;this.voices.close();}
}
