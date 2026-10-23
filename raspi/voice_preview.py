"""Bounded stopped-host audition and cancellable ALSA playback, entirely in memory."""
import base64
import json
import os
import selectors
import shutil
import signal
import subprocess
import time

from raspi.host import ROOT, child_environment, resolve_node, voice_candidates

MAX_PCM = 480000
FAILURES = frozenset(('AUTH', 'QUOTA', 'MODEL', 'CONFIG', 'PERMISSION', 'TIMEOUT',
    'EMPTY_AUDIO', 'OUTPUT_LIMIT', 'TRANSPORT', 'INVALID_AUDIO', 'CANCELLED', 'PC_AUDIO'))


def decode_audio(event, request_id):
    if not isinstance(event, dict): raise ValueError('INVALID_AUDIO')
    if event.get('event') != 'preview-audio':
        code = event.get('code')
        raise ValueError(code if isinstance(code, str) and code in FAILURES else 'TRANSPORT')
    value = event.get('pcm')
    if (type(event.get('id')) is not int or event['id'] != request_id
            or not isinstance(value, str) or len(value) > 640000): raise ValueError('INVALID_AUDIO')
    try: pcm = bytearray(base64.b64decode(value, validate=True))
    except (ValueError, TypeError): raise ValueError('INVALID_AUDIO') from None
    if not pcm or len(pcm)%2 or len(pcm) > MAX_PCM:
        pcm[:] = b'\0'*len(pcm); raise ValueError('INVALID_AUDIO')
    return pcm


def stop_child(child):
    if child.poll() is None:
        try: os.killpg(child.pid, signal.SIGTERM)
        except ProcessLookupError: pass
        try: child.wait(timeout=1)
        except subprocess.TimeoutExpired:
            try: os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError: pass
            child.wait(timeout=2)
    # The isolated Gemini worker must not outlive its parent.
    try: os.killpg(child.pid, signal.SIGKILL)
    except ProcessLookupError: pass
    for stream in (child.stdin, child.stdout):
        if stream is not None and not stream.closed: stream.close()


def generate_sample(key, model, voice, request_id, cancel, *, node=None):
    if cancel.is_set(): raise ValueError('CANCELLED')
    if voice not in voice_candidates(model) or type(request_id) is not int or not 0 < request_id <= 2**53-1:
        raise ValueError('CONFIG')
    node = resolve_node(node)
    env = child_environment(node, False, key, model, voice)
    child = None; output = bytearray()
    try:
        child = subprocess.Popen([str(node), str(ROOT/'server/dist/voice-preview.js')],
            cwd=ROOT/'server', env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, start_new_session=True)
        env.pop('GEMINI_API_KEY', None); key = ''
        child.stdin.write(json.dumps({'id': request_id, 'voice': voice}).encode()+b'\n')
        child.stdin.close()
        deadline = time.monotonic()+48
        with selectors.DefaultSelector() as selector:
            selector.register(child.stdout, selectors.EVENT_READ)
            while True:
                if cancel.is_set(): raise ValueError('CANCELLED')
                if time.monotonic() >= deadline: raise ValueError('TIMEOUT')
                if not selector.select(.05): continue
                chunk = os.read(child.stdout.fileno(), min(65536, 650001-len(output)))
                if not chunk: break
                output.extend(chunk)
                if len(output) > 650000: raise ValueError('INVALID_AUDIO')
        while child.poll() is None:
            if cancel.wait(.05): raise ValueError('CANCELLED')
            if time.monotonic() >= deadline: raise ValueError('TIMEOUT')
        try: event = json.loads(output)
        except (ValueError, UnicodeError): raise ValueError('INVALID_AUDIO') from None
        if child.returncode and isinstance(event, dict) and event.get('event') == 'preview-audio':
            raise ValueError('TRANSPORT')
        return decode_audio(event, request_id)
    finally:
        env.pop('GEMINI_API_KEY', None); key = ''; output[:] = b'\0'*len(output)
        if child is not None: stop_child(child)


def play_pcm(pcm, cancel):
    if not pcm or len(pcm)%2 or len(pcm) > MAX_PCM: raise ValueError('INVALID_AUDIO')
    if cancel.is_set(): return False
    player = shutil.which('aplay')
    if player is None: raise ValueError('PC_AUDIO')
    child = None
    try:
        child = subprocess.Popen([player, '-q', '-t', 'raw', '-f', 'S16_LE', '-c', '1', '-r', '24000'],
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        deadline = time.monotonic()+len(pcm)/48000+3
        first = True
        while True:
            if cancel.is_set(): return False
            if time.monotonic() >= deadline: raise ValueError('PC_AUDIO')
            try:
                child.communicate(input=pcm if first else None, timeout=.05)
                return child.returncode == 0 and not cancel.is_set()
            except subprocess.TimeoutExpired: first = False
    except (OSError, subprocess.SubprocessError): raise ValueError('PC_AUDIO') from None
    finally:
        if child is not None: stop_child(child)
