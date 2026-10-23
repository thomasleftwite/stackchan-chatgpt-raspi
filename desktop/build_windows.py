"""Explicit-allowlist Windows x64 one-file build. Never stage project data/.env."""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import urllib.request
import uuid

ROOT=Path(__file__).resolve().parents[1]
BUILD=ROOT/'.packaging'
STAGE=BUILD/'stage/runtime'
from settings import VERSION
OUT=ROOT/'releases'/f'StackchanHost-{VERSION}-win-x64'
JS=['local-gemini','gemini-pc','gemini-server','gemini-isolated','gemini-worker',
    'wireless-host','gemini-turn','private-config','protocol','gemini-probe-client','host-self-check','voice-control','voice-preview']
FLAGS=getattr(subprocess,'CREATE_NO_WINDOW',0)

def run(args,**kwargs):
    result=subprocess.run([str(x) for x in args],creationflags=FLAGS,capture_output=True,text=True,encoding='utf-8',errors='replace',**kwargs)
    if result.returncode:
        print((result.stdout+result.stderr)[-10000:])
        raise SystemExit(result.returncode)

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def fresh_stage(stage, build):
    stage, build = Path(stage).resolve(), Path(build).resolve()
    if stage == build or not stage.is_relative_to(build):
        raise ValueError('Stage must be inside the build folder')
    if stage.exists():
        prior = build / 'prior-stages'
        prior.mkdir(parents=True, exist_ok=True)
        stage.rename(prior / uuid.uuid4().hex)
    stage.mkdir(parents=True, exist_ok=True)

def main():
    if os.name!='nt' or sys.maxsize<2**32: raise SystemExit('Windows x64 required')
    OUT.mkdir(parents=True,exist_ok=True); fresh_stage(STAGE,BUILD)
    parser=argparse.ArgumentParser();parser.add_argument('--node',type=Path)
    args=parser.parse_args()
    node=args.node.resolve() if args.node else Path(shutil.which('node') or '')
    version=subprocess.check_output([str(node),'--version'],text=True,creationflags=FLAGS).strip()
    if version!='v24.15.0': raise SystemExit('Review the pinned Node runtime version first')
    run(['npm.cmd','run','build'],cwd=ROOT/'server')
    target=STAGE/'server'; (target/'dist').mkdir(parents=True,exist_ok=True)
    shutil.copy2(node,STAGE/'node.exe')
    for name in ('package.json','package-lock.json'): shutil.copy2(ROOT/'server'/name,target/name)
    shutil.copy2(ROOT/'server/voice-catalog.json',target/'voice-catalog.json')
    for name in JS: shutil.copy2(ROOT/'server/dist'/f'{name}.js',target/'dist'/f'{name}.js')
    # Restore exactly the production closure from lockfile; no install scripts.
    run(['npm.cmd','ci','--omit=dev','--ignore-scripts','--no-audit','--no-fund',
         '--cache',str(BUILD/'npm-cache')],cwd=target)
    shutil.copy2(ROOT/'desktop/README.ja.md',STAGE/'README.ja.md')
    notices=['StackchanHost '+VERSION+'\n\n'+(ROOT/'LICENSE').read_text(encoding='utf-8')]
    downloads=BUILD/'downloads'; downloads.mkdir(exist_ok=True)
    node_license=downloads/'NODE-LICENSE-v24.15.0.txt'
    if not node_license.exists():
        urllib.request.urlretrieve('https://raw.githubusercontent.com/nodejs/node/v24.15.0/LICENSE',node_license)
    notices.append('NODE.JS 24.15.0\n'+node_license.read_text(encoding='utf-8'))
    for path in [Path(sys.base_prefix)/'LICENSE.txt',Path(sys.base_prefix)/'tcl/tcl8.6/license.terms',
                 Path(sys.base_prefix)/'tcl/tk8.6/license.terms']:
        if path.is_file(): notices.append(path.name+'\n'+path.read_text(encoding='utf-8',errors='replace'))
    for path in sorted((target/'node_modules').rglob('*')):
        if path.is_file() and re.match(r'^(license|licence|copying|notice)',path.name,re.I):
            notices.append(str(path.relative_to(target))+'\n'+path.read_text(encoding='utf-8',errors='replace'))
    for name in ('pyserial','pyinstaller'):
        dist=importlib.metadata.distribution(name)
        for part in dist.files or []:
            if re.search(r'(license|copying)',str(part),re.I) and dist.locate_file(part).is_file():
                notices.append(str(part)+'\n'+dist.locate_file(part).read_text(encoding='utf-8',errors='replace'))
    (STAGE/'THIRD_PARTY_NOTICES.txt').write_text('\n\n'.join(notices),encoding='utf-8')
    # Audit the exact inputs, including comparison against locally held real keys.
    private=[]
    secrets_file=ROOT/'data/secrets.json'
    if secrets_file.is_file():
        private=[x.encode() for x in json.loads(secrets_file.read_text(encoding='utf-8')).values() if isinstance(x,str) and len(x)>=20]
    files=[]
    for path in sorted(STAGE.rglob('*')):
        if not path.is_file(): continue
        if path.name.lower() in ('.env','secrets.json','bridge.local.json','settings.json','pairing.json'):
            raise SystemExit('Private filename in staged payload')
        data=path.read_bytes()
        if any(value in data for value in private): raise SystemExit('Private value in staged payload')
        files.append({'path':str(path.relative_to(STAGE)).replace('\\','/'),'size':len(data),'sha256':hashlib.sha256(data).hexdigest()})
    manifest={'version':VERSION,'node':version,'python':sys.version.split()[0],
        'serverLockSha256':sha(ROOT/'server/package-lock.json'),'payload':files,
        'launcherSources':{name:sha(ROOT/name) for name in ('desktop/host_app.py','desktop/settings.py','desktop/network.py','desktop/wireless.py','desktop/voices.py','desktop/voice_preview.py','tools/run_gemini_device.py','tools/run_lan_probe.py')},
        'privateValueMatches':0,'firmwareIncluded':False,'driverInstallerIncluded':False}
    (STAGE/'build-manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    run([sys.executable,'-m','PyInstaller','--noconfirm','--onefile','--windowed','--noupx',
         '--name','StackchanHost','--paths',str(ROOT/'tools'),'--paths',str(ROOT/'desktop'),
         '--add-data',str(STAGE)+';runtime','--distpath',str(OUT),
         '--workpath',str(BUILD/'work'),'--specpath',str(BUILD),
         str(ROOT/'desktop/host_app.py')],cwd=ROOT)
    shutil.copy2(ROOT/'desktop/README.ja.md',OUT/'README.ja.md')
    shutil.copy2(STAGE/'THIRD_PARTY_NOTICES.txt',OUT/'THIRD_PARTY_NOTICES.txt')
    shutil.copy2(STAGE/'build-manifest.json',OUT/'build-manifest.json')
    (OUT/'SHA256SUMS.txt').write_text(sha(OUT/'StackchanHost.exe')+'  StackchanHost.exe\n',encoding='ascii')
    print(json.dumps({'exe':str(OUT/'StackchanHost.exe'),'size':(OUT/'StackchanHost.exe').stat().st_size,'sha256':sha(OUT/'StackchanHost.exe'),'stagedFiles':len(files),'privateValueMatches':0}))

if __name__=='__main__': main()
