"""Wireless host lifecycle and DPAPI-protected device enrollment. No USB imports."""
import base64
import json
import hashlib
import shutil
import os
from pathlib import Path
import queue
import re
import subprocess
import threading
from settings import crypt

PORT=48443

FAILURE_CODES=frozenset(('AUTH','QUOTA','MODEL','PERMISSION','CONFIG','SERVER','TRANSPORT','TIMEOUT',
    'INVALID_AUDIO','EMPTY_AUDIO','OUTPUT_LIMIT','INTERRUPTED','EARLY_CLOSE'))

def wireless_status(event):
    if not isinstance(event,dict): return None
    kind=event.get('event')
    if kind not in ('ready','device-online','turn-complete','turn-failed','failed'): return None
    if kind=='turn-failed' and isinstance(event.get('code'),str) and event['code'] in FAILURE_CODES:
        status=event.get('status')
        status=status if type(status) is int and 100<=status<=599 else 0
        return f"WIRELESS turn-failed {event['code']} {status}"
    return 'WIRELESS '+kind

def normalize_code(value):
    value=re.sub(r'\s','',value).lower()
    if not re.fullmatch('[0-9a-f]{32}',value): raise ValueError('INVALID_PAIR_CODE')
    return value

def save_pairing(path,code):
    code=normalize_code(code);path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    data={'version':1,'protectedDeviceKey':base64.b64encode(crypt(code.encode())).decode('ascii')}
    temp=path.with_suffix('.new');temp.write_text(json.dumps(data),encoding='utf-8');os.replace(temp,path)

def load_pairing(path):
    path=Path(path)
    if not path.exists(): return ''
    if path.stat().st_size>4096: raise ValueError('PAIRING_TOO_LARGE')
    data=json.loads(path.read_text(encoding='utf-8'))
    if data.get('version')!=1: raise ValueError('INVALID_PAIRING')
    return normalize_code(crypt(base64.b64decode(data['protectedDeviceKey'],validate=True),True).decode('ascii'))

def runtime_node(runtime, destination=None):
    # A stable, verified executable path lets the firewall restrict this runtime
    # across one-file EXE extractions. Do not reuse other installations' node.exe.
    source=Path(runtime)/'node.exe'
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    root=Path(destination) if destination else Path(os.environ['LOCALAPPDATA'])/'StackchanHost'/'runtime'
    target=root/digest/'node.exe';target.parent.mkdir(parents=True,exist_ok=True)
    if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest()!=digest:
        temp=target.with_suffix('.new');shutil.copyfile(source,temp);os.replace(temp,target)
    return target

def run_wireless(runtime,node,host,env,stop_event,on_status,commands=None,on_event=None):
    # Wi-Fi membership is the trust boundary selected by the user.
    from network import hotspot_networks
    networks=hotspot_networks()
    if host not in networks:
        on_status('WIRELESS hotspot_required');return 1
    child=subprocess.Popen([str(node),str(Path(runtime)/'server/dist/wireless-host.js')],cwd=Path(runtime)/'server',
        stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,env=env,
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    events=queue.Queue(maxsize=64)
    def read():
        for line in child.stdout:
            try: events.put_nowait(line)
            except queue.Full: pass
    threading.Thread(target=read,daemon=True).start()
    try:
        child.stdin.write(json.dumps({'host':host,'port':PORT,'subnet':networks[host]})+'\n');child.stdin.flush()
        ready=False
        while not stop_event.wait(.1):
            if commands is not None:
                while True:
                    try: command=commands.get_nowait()
                    except queue.Empty: break
                    child.stdin.write(json.dumps(command)+'\n');child.stdin.flush()
            if child.poll() is not None:
                on_status('WIRELESS failed');return 1
            try: event=json.loads(events.get(timeout=.1))
            except queue.Empty: continue
            except (ValueError,TypeError): continue
            kind=event.get('event') if isinstance(event,dict) else None
            if on_event and kind in ('voice-selected','voice-failed','session-busy','session-idle',
                    'preview-audio','preview-failed','preview-stopped','preview-conflict','turn-complete','voice-played'):
                on_event(event)
            status=wireless_status(event)
            if status:
                on_status(status)
                if kind=='failed':return 1
                if kind=='ready':ready=True
        return 0 if ready else 1
    finally:
        if child.poll() is None:
            try:child.stdin.close();child.wait(timeout=5)
            except (OSError,subprocess.TimeoutExpired):child.terminate();child.wait(timeout=5)
        on_status('WIRELESS stopped')
