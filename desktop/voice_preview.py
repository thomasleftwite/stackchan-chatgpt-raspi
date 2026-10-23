"""Bounded Live audition and cancellable Windows PCM playback, without files."""
import base64
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import subprocess
import time

def decode_audio(event):
    value=event.get('pcm')
    if not isinstance(value,str) or len(value)>640000: raise ValueError('INVALID_AUDIO')
    pcm=bytearray(base64.b64decode(value,validate=True))
    if not pcm or len(pcm)%2 or len(pcm)>480000: raise ValueError('INVALID_AUDIO')
    return pcm

def generate_sample(runtime,node,env,voice,request_id,cancel):
    child=subprocess.Popen([str(node),str(Path(runtime)/'server/dist/voice-preview.js')],
        cwd=Path(runtime)/'server',env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
        text=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    try:
        child.stdin.write(json.dumps({'id':request_id,'voice':voice})+'\n');child.stdin.close();child.stdin=None
        deadline=time.monotonic()+48
        while True:
            if cancel.is_set(): raise ValueError('CANCELLED')
            if time.monotonic()>deadline: raise ValueError('TIMEOUT')
            try: output,_=child.communicate(timeout=.1);break
            except subprocess.TimeoutExpired: pass
        if len(output)>650000: raise ValueError('INVALID_AUDIO')
        event=json.loads(output)
        if child.returncode or event.get('event')!='preview-audio':
            code=event.get('code');raise ValueError(code if code in ('AUTH','QUOTA','MODEL','CONFIG','PERMISSION','TIMEOUT','EMPTY_AUDIO','OUTPUT_LIMIT','TRANSPORT') else 'TRANSPORT')
        return decode_audio(event)
    finally:
        if child.poll() is None: child.terminate();child.wait(timeout=5)

class WaveFormat(ctypes.Structure):
    _pack_=1
    _fields_=[('format',wintypes.WORD),('channels',wintypes.WORD),('rate',wintypes.DWORD),
        ('bytes_per_second',wintypes.DWORD),('block',wintypes.WORD),('bits',wintypes.WORD),('extra',wintypes.WORD)]
class WaveHeader(ctypes.Structure):
    _fields_=[('data',ctypes.c_void_p),('length',wintypes.DWORD),('recorded',wintypes.DWORD),
        ('user',ctypes.c_size_t),('flags',wintypes.DWORD),('loops',wintypes.DWORD),
        ('next',ctypes.c_void_p),('reserved',ctypes.c_size_t)]

def play_pcm(pcm,cancel):
    if os.name!='nt': raise ValueError('PC_AUDIO')
    if not pcm or len(pcm)%2 or len(pcm)>480000: raise ValueError('INVALID_AUDIO')
    if cancel.is_set(): return False
    api=ctypes.WinDLL('winmm');handle=ctypes.c_void_p()
    api.waveOutOpen.argtypes=[ctypes.POINTER(ctypes.c_void_p),wintypes.UINT,ctypes.POINTER(WaveFormat),ctypes.c_size_t,ctypes.c_size_t,wintypes.DWORD]
    for name in ('waveOutPrepareHeader','waveOutWrite','waveOutUnprepareHeader'):
        getattr(api,name).argtypes=[ctypes.c_void_p,ctypes.POINTER(WaveHeader),wintypes.UINT]
    api.waveOutReset.argtypes=[ctypes.c_void_p];api.waveOutClose.argtypes=[ctypes.c_void_p]
    fmt=WaveFormat(1,1,24000,48000,2,16,0)
    if api.waveOutOpen(ctypes.byref(handle),0xFFFFFFFF,ctypes.byref(fmt),0,0,0): raise ValueError('PC_AUDIO')
    buffer=(ctypes.c_char*len(pcm)).from_buffer(pcm)
    header=WaveHeader(ctypes.addressof(buffer),len(pcm),0,0,0,0,None,0);prepared=False
    try:
        if api.waveOutPrepareHeader(handle,ctypes.byref(header),ctypes.sizeof(header)): raise ValueError('PC_AUDIO')
        prepared=True
        if cancel.is_set(): return False
        if api.waveOutWrite(handle,ctypes.byref(header),ctypes.sizeof(header)): raise ValueError('PC_AUDIO')
        deadline=time.monotonic()+len(pcm)/48000+3
        while not header.flags&1:
            if cancel.wait(.02): return False
            if time.monotonic()>deadline: raise ValueError('PC_AUDIO')
        return True
    finally:
        api.waveOutReset(handle)
        if prepared: api.waveOutUnprepareHeader(handle,ctypes.byref(header),ctypes.sizeof(header))
        api.waveOutClose(handle)
