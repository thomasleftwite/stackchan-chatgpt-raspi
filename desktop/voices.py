"""Japanese voice admission records. No audio, API keys, or transcripts on disk."""
import json
import os
from pathlib import Path
import sys
import shutil
import uuid
from datetime import datetime,timezone,timedelta
REVIEW_REASONS={'approved':('発音・読み・明瞭さが適切',),
    'excluded':('発音が不自然','数字や文章の読みが不正確','聞き取りにくい','声が不安定')}

def catalog_path():
    root=Path(sys._MEIPASS)/'runtime/server' if getattr(sys,'frozen',False) else Path(__file__).resolve().parents[1]/'server'
    return root/'voice-catalog.json'

def load_catalog():
    data=json.loads(catalog_path().read_text(encoding='utf-8'))
    return data

class VoiceReviews:
    def __init__(self,path,*,catalog=None):
        self.path=Path(path);self.catalog=catalog or load_catalog();self.records={};self.load_error=False
        if self.path.exists():
            try:
                if self.path.stat().st_size>65536: raise ValueError('VOICE_REVIEW_TOO_LARGE')
                data=json.loads(self.path.read_text(encoding='utf-8'))
                if not isinstance(data,dict) or data.get('version')!=1 or not isinstance(data.get('records'),dict): raise ValueError('INVALID_VOICE_REVIEW')
                for name,item in data['records'].items():
                    if not isinstance(name,str) or not isinstance(item,dict) or item.get('status') not in REVIEW_REASONS:
                        raise ValueError('INVALID_VOICE_REVIEW')
                    if item.get('reason') not in REVIEW_REASONS[item['status']] or not isinstance(item.get('revision'),str):
                        raise ValueError('INVALID_VOICE_REVIEW')
                self.records=data['records']
            except (ValueError,OSError,UnicodeError,TypeError): self.load_error=True
    def candidates(self,model):
        return list(self.catalog['voices']) if model in self.catalog['models'] else []
    def approved(self,model):
        return [v for v in self.candidates(model) if self.records.get(model+':'+v,{}).get('status')=='approved'
                and self.records[model+':'+v].get('revision')==self.catalog['revision']
                and self.records[model+':'+v].get('pcJapanese') is True]
    def decide(self,model,voice,approved,*,pc_confirmed=False,device_confirmed=False,app_version='',reason='発音・読み・明瞭さが適切'):
        if voice not in self.candidates(model): raise ValueError('INVALID_VOICE')
        if approved and not pc_confirmed: raise ValueError('JAPANESE_REVIEW_REQUIRED')
        status='approved' if approved else 'excluded'
        if reason not in REVIEW_REASONS[status]: raise ValueError('REVIEW_REASON_REQUIRED')
        records=dict(self.records)
        records[model+':'+voice]={'status':status,'reason':reason,
            'revision':self.catalog['revision'],'date':datetime.now(timezone(timedelta(hours=9))).date().isoformat(),'appVersion':app_version,
            'pcJapanese':pc_confirmed,'deviceJapanese':device_confirmed}
        self.path.parent.mkdir(parents=True,exist_ok=True)
        if self.load_error and self.path.exists():
            backup=self.path.with_name(self.path.name+'.invalid-'+uuid.uuid4().hex)
            shutil.copy2(self.path,backup) # Preserve the original before an explicit new review replaces it.
        temp=self.path.with_suffix('.new');temp.write_text(json.dumps({'version':1,'records':records},ensure_ascii=False,indent=2),encoding='utf-8')
        os.replace(temp,self.path)
        self.records=records
        self.load_error=False
