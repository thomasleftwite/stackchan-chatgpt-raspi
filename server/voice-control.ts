import {readFileSync} from 'node:fs';
import type {GeminiConfig} from './private-config.js';
import type {TurnOptions, TurnResult} from './gemini-turn.js';
import {GeminiFailure} from './gemini-turn.js';

export const catalog = JSON.parse(readFileSync(new URL('../voice-catalog.json',import.meta.url),'utf8')) as {
  revision:string; models:string[]; voices:string[];
};
export const sampleText='こんにちは、スタックちゃんです。今日は十月二十一日、水曜日です。';
export function validVoice(model:string,voice:unknown):voice is string {
  return typeof voice==='string' && catalog.models.includes(model) && catalog.voices.includes(voice);
}
export type VoiceRunner=(options:Omit<TurnOptions,'connector'>,signal?:AbortSignal)=>Promise<TurnResult>;

// One session owns its immutable voice snapshot; changes apply to the next one.
export class VoiceControl {
  private active:GeminiConfig|undefined;
  private previewId=0;
  private abort:AbortController|undefined;
  private expiry:ReturnType<typeof setTimeout>|undefined;
  constructor(private config:GeminiConfig, private runner:VoiceRunner) {}
  get busy() {return !!this.active || !!this.previewId;}
  get selected() {return this.config.voice ?? '';}
  select(voice:string) {
    if(!validVoice(this.config.model,voice)) throw new GeminiFailure('CONFIG');
    this.config={...this.config,voice};
  }
  beginTurn() {
    if(this.busy) return false;
    this.active={...this.config};return true;
  }
  endTurn() {this.active=undefined;}
  get activeVoice() {return this.active?.voice ?? '';}
  async run(pcm:Buffer) {
    if(!this.active) throw new GeminiFailure('CONFIG');
    return this.runner({config:{...this.active},input:{pcm}});
  }
  async preview(id:number,voice:string) {
    if(this.busy || !Number.isSafeInteger(id) || id<=0) throw new GeminiFailure('CONFIG');
    if(!validVoice(this.config.model,voice)) throw new GeminiFailure('CONFIG');
    this.previewId=id;this.abort=new AbortController();
    this.expiry=setTimeout(()=>this.finishPreview(id),55000);this.expiry.unref();
    try {
      const result=await this.runner({config:{...this.config,voice},input:{text:sampleText},purpose:'preview'},this.abort.signal);
      if(this.previewId!==id) {result.pcm.fill(0);throw new GeminiFailure('INTERRUPTED');}
      return result;
    } catch(error) {this.finishPreview(id);throw error;}
  }
  finishPreview(id:number) {
    if(id!==this.previewId) return;
    this.abort?.abort();clearTimeout(this.expiry);this.previewId=0;this.abort=undefined;
  }
  close() {this.finishPreview(this.previewId);this.endTurn();}
}
