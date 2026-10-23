"""Windows per-user key protection. Never write plaintext API keys."""
import base64
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import re

VERSION = '0.6.0-rc.1'

def valid_key(value):
    return isinstance(value, str) and bool(re.fullmatch(r'[\x21-\x7e]{20,256}', value))

def valid_model(value):
    return isinstance(value, str) and bool(re.fullmatch(r'gemini-[a-z0-9.-]{1,100}', value))

class Blob(ctypes.Structure):
    _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]

def crypt(value, decrypt=False):
    if os.name != 'nt': raise RuntimeError('WINDOWS_REQUIRED')
    source = ctypes.create_string_buffer(value)
    incoming = Blob(len(value), ctypes.cast(source, ctypes.POINTER(ctypes.c_ubyte)))
    outgoing = Blob()
    api = ctypes.WinDLL('crypt32', use_last_error=True)
    function = api.CryptUnprotectData if decrypt else api.CryptProtectData
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                         ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    function.restype = wintypes.BOOL
    release = ctypes.WinDLL('kernel32', use_last_error=True).LocalFree
    release.argtypes = [ctypes.c_void_p]; release.restype = ctypes.c_void_p
    if not function(ctypes.byref(incoming), None, None, None, None, 1, ctypes.byref(outgoing)):
        raise RuntimeError('KEY_PROTECTION_FAILED')
    try: return ctypes.string_at(outgoing.data, outgoing.size)
    finally:
        ctypes.memset(outgoing.data, 0, outgoing.size)
        release(outgoing.data)
        ctypes.memset(source, 0, len(value))

def settings_path():
    parent = os.environ.get('STACKCHAN_HOST_STATE_DIR')
    return Path(parent) / 'settings.json' if parent else Path(os.environ['LOCALAPPDATA']) / 'StackchanHost' / 'settings.json'

def save_settings(path, *, model, port, host, key='', remember=False, voice=''):
    if not valid_model(model) or (key and not valid_key(key)): raise ValueError('INVALID_SETTINGS')
    data = {'version':1, 'model':model, 'port':port, 'host':host}
    if voice:
        if not re.fullmatch('[A-Za-z]{1,32}',voice): raise ValueError('INVALID_VOICE')
        data['voice']=voice
    if remember and key: data['protectedKey'] = base64.b64encode(crypt(key.encode())).decode('ascii')
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.new')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temporary, path)

def load_settings(path):
    if not path.exists(): return {}
    if path.stat().st_size > 16384: raise ValueError('SETTINGS_TOO_LARGE')
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict) or data.get('version') != 1: raise ValueError('INVALID_SETTINGS')
    if 'protectedKey' in data:
        data['key'] = crypt(base64.b64decode(data['protectedKey'], validate=True), True).decode('utf-8')
        if not valid_key(data['key']): raise ValueError('INVALID_SETTINGS')
    return data

def save_voice_setting(path,voice):
    """Update only voice; never re-encrypt, remove, or expose a remembered key."""
    if not re.fullmatch('[A-Za-z]{1,32}',voice): raise ValueError('INVALID_VOICE')
    data=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'version':1}
    if data.get('version')!=1: raise ValueError('INVALID_SETTINGS')
    data['voice']=voice
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix('.new');temp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');os.replace(temp,path)
