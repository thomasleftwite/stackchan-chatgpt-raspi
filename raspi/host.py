"""Linux host lifecycle; explicit live mode, session-only key, no raw logs."""
import argparse
import getpass
import json
import os
from pathlib import Path
import queue
import re
import shutil
import signal
import subprocess
import sys
import threading
import time

from raspi.host_network import Endpoint, HostError, discover_ap

ROOT = Path(__file__).resolve().parents[1]
EVENTS = frozenset(('ready', 'failed', 'device-online', 'turn-complete', 'turn-failed',
    'session-busy', 'session-idle', 'voice-played', 'voice-selected', 'voice-failed'))
FAILURES = frozenset(('AUTH', 'QUOTA', 'MODEL', 'PERMISSION', 'CONFIG', 'SERVER',
    'TRANSPORT', 'TIMEOUT', 'INVALID_AUDIO', 'EMPTY_AUDIO', 'OUTPUT_LIMIT', 'INTERRUPTED', 'EARLY_CLOSE'))


def public_event(value):
    if not isinstance(value, dict) or not isinstance(value.get('event'), str) or value['event'] not in EVENTS:
        return None
    event = {'event': value['event']}
    if value['event'] == 'turn-failed':
        code = value.get('code'); status = value.get('status')
        if isinstance(code, str) and code in FAILURES: event['code'] = code
        if type(status) is int and 100 <= status <= 599: event['status'] = status
    if value['event'] == 'voice-selected':
        request_id = value.get('id')
        if type(request_id) is not int or not 0 < request_id <= 2**53-1: return None
        event['id'] = request_id
    return event


def voice_candidates(model):
    # Reuse the same checked-in catalog as the Windows host and Node server.
    catalog = json.loads((ROOT/'server/voice-catalog.json').read_text(encoding='utf-8'))
    return tuple(catalog['voices']) if model in catalog['models'] else ()


def resolve_node(explicit=None):
    pinned = ROOT / '.runtime/node-v22.23.4-linux-arm64/bin/node'
    candidate = explicit or (str(pinned) if pinned.is_file() else shutil.which('node'))
    if not candidate: raise HostError('NODE_REQUIRED')
    try:
        path = Path(candidate).resolve()
        result = subprocess.run([str(path), '--version'], capture_output=True, text=True, timeout=5)
        match = re.fullmatch(r'v(\d+)\.(\d+)\.(\d+)\s*', result.stdout)
        if result.returncode or not match or tuple(map(int, match.groups())) < (22, 9, 0):
            raise HostError('NODE_REQUIRED')
        return path
    except Exception: raise HostError('NODE_REQUIRED') from None


def child_environment(node, fixture, key, model, voice=''):
    env = {'PATH': str(Path(node).parent) + os.pathsep + os.defpath}
    if not fixture:
        if not isinstance(key, str) or not re.fullmatch(r'[\x21-\x7e]{20,256}', key):
            raise HostError('KEY_REQUIRED')
        if not re.fullmatch(r'gemini-[a-z0-9.-]{1,100}', model): raise HostError('MODEL_INVALID')
        if voice and voice not in voice_candidates(model): raise HostError('VOICE_INVALID')
        env.update(GEMINI_API_KEY=key, GEMINI_MODEL=model)
        if voice: env['GEMINI_VOICE'] = voice
    return env


class HostService:
    def __init__(self, endpoint, node, *, fixture=True, key='', model='gemini-3.8-live', voice='', port=48443):
        if type(port) is not int or not 1024 <= port <= 65535: raise HostError('PORT_INVALID')
        if endpoint.host == '127.0.0.1' and (not fixture or endpoint.subnet != '127.0.0.1/32'):
            raise HostError('AP_REQUIRED')
        self.endpoint = endpoint; self.node = node; self.fixture = fixture
        self.key = key; self.model = model; self.voice = voice; self.port = port; self.child = None; self.reader = None

    def _stop(self):
        child = self.child
        self.key = ''
        if child is None: return
        try:
            if child.poll() is None:
                try:
                    child.stdin.close(); child.wait(timeout=5)
                except (OSError, subprocess.TimeoutExpired):
                    try: os.killpg(child.pid, signal.SIGTERM)
                    except ProcessLookupError: pass
                    try: child.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        try: os.killpg(child.pid, signal.SIGKILL)
                        except ProcessLookupError: pass
                        child.wait(timeout=5)
            # A worker may outlive the Node parent: reap the private process group too.
            try: os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError: pass
        finally:
            if self.reader is not None: self.reader.join(timeout=1)
            for stream in (child.stdin, child.stdout):
                if stream is not None: stream.close()
            self.key = ''

    def run(self, stop, on_event, duration=None, *, commands=None):
        if duration is not None and (type(duration) not in (int, float) or not 0 < duration <= 3600):
            raise HostError('DURATION_INVALID')
        events = queue.Queue(maxsize=64)
        try:
            if stop.is_set(): return 0
            env = child_environment(self.node, self.fixture, self.key, self.model, self.voice)
            self.child = subprocess.Popen([str(self.node), str(ROOT/'server/dist/wireless-host.js')],
                cwd=ROOT/'server', env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, text=True, start_new_session=True)
            def read():
                while True:
                    line = self.child.stdout.readline(2049)
                    if not line: return
                    if len(line) > 2048: continue
                    try:
                        value = json.loads(line)
                        # Drop provider bodies, keys, PCM, model and voice fields.
                        event = public_event(value)
                        if event is None: continue
                        try: events.put_nowait(event)
                        except queue.Full: pass
                    except (ValueError, TypeError): pass
            self.reader = threading.Thread(target=read, daemon=True); self.reader.start()
            self.child.stdin.write(json.dumps({'host': self.endpoint.host, 'port': self.port,
                'subnet': self.endpoint.subnet, 'fixture': self.fixture})+'\n')
            self.child.stdin.flush()
            started = time.monotonic(); ready = False
            while not stop.is_set():
                if self.child.poll() is not None: raise HostError('HOST_EXITED')
                if not ready and time.monotonic()-started > 8: raise HostError('HOST_START_TIMEOUT')
                if ready and duration is not None and time.monotonic()-started >= duration: break
                if ready and commands is not None:
                    try: command = commands.get_nowait()
                    except queue.Empty: command = None
                    if command is not None:
                        request_id = command.get('id') if isinstance(command, dict) else None
                        voice = command.get('voice') if isinstance(command, dict) else None
                        if (not self.fixture and type(request_id) is int and 0 < request_id <= 2**53-1
                                and voice in voice_candidates(self.model)):
                            self.child.stdin.write(json.dumps({'type': 'voice', 'id': request_id, 'voice': voice})+'\n')
                            self.child.stdin.flush()
                        else: on_event({'event': 'voice-failed'})
                try: event = events.get(timeout=.1)
                except queue.Empty: continue
                if event['event'] == 'failed': raise HostError('HOST_START_FAILED')
                if event['event'] == 'ready': ready = True
                on_event(event)
            return 0 if ready or stop.is_set() else 1
        except HostError: raise
        except Exception: raise HostError('HOST_FAILED') from None
        finally:
            self._stop(); on_event({'event': 'stopped'})


def make_service(*, fixture, key='', model='gemini-3.8-live', voice='', node=None, interface='wlan0', port=48443):
    return HostService(discover_ap(interface), resolve_node(node), fixture=fixture, key=key, model=model, voice=voice, port=port)


def main():
    parser = argparse.ArgumentParser(description='Raspberry Pi Stackchan host')
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--fixture', action='store_true', help='API不要の接続確認')
    modes.add_argument('--live', action='store_true', help='Gemini接続を有効化（API利用あり）')
    modes.add_argument('--gui', action='store_true')
    parser.add_argument('--node'); parser.add_argument('--interface', default='wlan0')
    parser.add_argument('--model', default='gemini-3.8-live'); parser.add_argument('--port', type=int, default=48443)
    parser.add_argument('--voice', default=None, help='声カタログの声名（省略時は保存した採用済み選択、なければサービス既定）')
    parser.add_argument('--duration', type=float)
    args = parser.parse_args()
    if args.gui:
        from raspi.host_ui import main as gui
        gui(); return 0
    stop = threading.Event()
    prior = {}
    try:
        if args.live and not sys.stdin.isatty(): raise HostError('INTERACTIVE_KEY_REQUIRED')
        key = getpass.getpass('Gemini API key（今回のみ使用）: ') if args.live else ''
        voice = args.voice or ''
        if args.live and args.voice is None:
            from raspi.voice_settings import VoiceSettings
            voice = VoiceSettings().selected(args.model)
        service = make_service(fixture=args.fixture, key=key, model=args.model, voice=voice, node=args.node,
            interface=args.interface, port=args.port)
        key = ''
        prior = {sig: signal.signal(sig, lambda *_: stop.set()) for sig in (signal.SIGTERM, signal.SIGINT)}
        return service.run(stop, lambda event: print(json.dumps(event), flush=True), args.duration)
    except KeyboardInterrupt:
        return 130
    except Exception:
        print(json.dumps({'event': 'failed'})); return 1
    finally:
        for sig, handler in prior.items(): signal.signal(sig, handler)


if __name__ == '__main__':
    from raspi.host import main as run_main
    raise SystemExit(run_main())
