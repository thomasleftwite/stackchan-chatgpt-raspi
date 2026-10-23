"""Private-LAN/USB coordinator. Only allowlisted status/numbers leave this process."""
import argparse
from collections import deque
import json
from pathlib import Path
import queue
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
import serial
from run_lan_probe import choose_host

ROOT = Path(__file__).resolve().parents[1]
READY = 'GEM READY v=2 input=16000 output=24000 mono=1 bits=16'
STATUS = re.compile(r'GEM (?:BUILD enrollment=[3-7]|ENROLL (?:STEP (?:none|record[1-3]?|verify|check|save|retry)|AUDIO (?:NONE|samples=\d{1,5} voiced=\d{1,5} ms=\d{1,6})|CAL (?:NONE|rms=\d{1,5} threshold=\d{1,5} ms=\d{1,6} gap=\d{1,6})|result=(?:NONE|SAVED|CANCEL|NOISY|SHORT|LONG|NO_SPEECH|CLIPPED|MISMATCH|IO|SAVE_FAIL|UNAVAILABLE|TIMEOUT))|LINK (?:TLS|USB)|PAIR (?:READY|REQUIRED|SAVED|FAIL)|LOCAL BUSY|WAKE (?:available=[01]|MATCH)|UI stage=[123] mode=\d{1,2} asleep=[01] mic=[01]|READY v=2 input=16000 output=24000 mono=1 bits=16|STATE configured=[01] wifi=[01] pc=[01]|START BLOCKED reason=(?:setup|wifi|pc|button)|PC OFFLINE|CONFIG OK|WIFI (?:CONNECTED|FAIL|SETUP|AP_JOIN|AP_LEAVE|AP_STOP)|MEMORY FAIL|CAPTURE (?:TIMING (?:NONE|prep=\d{1,6} gap=\d{1,6})|NONE|FAIL|EMPTY(?: ms=\d{1,6} captured=\d{1,6})?|CANCEL|NOISY|DONE samples=\d{1,5} ms=\d{1,6} rms=\d{1,5} peak=\d{1,5} clipped=\d{1,5}(?: captured=\d{1,6} end=(?:silence|limit))?)|VAD CALIBRATED rms=\d{1,5} threshold=\d{1,5}|VADTEST (?:PASS samples=\d{1,5}|FAIL)|RESULT (?:NONE|(?:PASS|FAIL) gen=\d{1,10} input=\d{1,5} output=\d{1,6} frames=\d{1,3} ms=\d{1,6} played=[01])|FAULT code=\d{1,2})')


class SessionFailure(Exception):
    """Only fixed internal reason codes may escape to status output."""
    def __init__(self, reason):
        self.reason = reason


class SerialLines:
    """Read bounded USB bursts, preserving every complete or partial line."""
    def __init__(self, device):
        self.device = device
        self.pending = bytearray()
        self.discarding = False
        self.ready = deque(maxlen=512)

    def read(self):
        if self.ready:
            return self.ready.popleft()
        # read_until performs a Windows driver call per byte. Drain a bounded
        # available burst instead, then keep remaining complete lines locally.
        chunk = self.device.read(min(max(self.device.in_waiting, 1), 512))
        for value in chunk:
            if value == 10:
                if not self.discarding:
                    self.ready.append(self.pending.decode('ascii', errors='replace').strip())
                self.pending.clear()
                self.discarding = False
            elif not self.discarding:
                self.pending.append(value)
                if len(self.pending) > 512:
                    self.pending.clear()
                    self.discarding = True
        return self.ready.popleft() if self.ready else ''


def main(argv=None, *, runtime_root=None, node_path=None, stop_event=None, on_status=None, child_env=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', required=True)
    parser.add_argument('--mode', choices=['fixture', 'gemini'], default='fixture')
    parser.add_argument('--host')
    parser.add_argument('--seconds', type=int, default=580)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args(argv)
    runtime = Path(runtime_root) if runtime_root is not None else ROOT

    def emit(value):
        if on_status is not None: on_status(value)
        else: print(value, flush=True)
    report = args.report.resolve() if args.report else None
    if report and (not report.is_relative_to((ROOT / '.pio').resolve()) or report.exists()):
        raise ValueError('New report under .pio required')
    started = time.monotonic()
    stage, reason, code = 'lan', 'internal_error', 1
    failure_stage = None
    child = None
    child_code = None
    device_stop = False
    serial_detail = None
    statuses = []
    timeline = []
    events, controls = queue.Queue(maxsize=64), queue.Queue()

    def elapsed():
        return max(0, round((time.monotonic() - started) * 1000))

    def save_status(line):
        # Keep transitions/repeats while bounding the in-memory report.
        if len(statuses) < 2000:
            statuses.append(line)
            timeline.append({'elapsedMs':elapsed(), 'status':line})

    def read_server():
        for line in child.stdout:
            # Never let stdout noise strand a blocked reader at shutdown.
            try: events.put_nowait(line)
            except queue.Full: pass

    def read_control():
        for line in sys.stdin:
            if line.strip() == 'stop':
                controls.put('user_stop')
        controls.put('stdin_closed')

    def stop_device(device, lines):
        nonlocal device_stop, stop_attempted
        stop_attempted = True
        device.write(b'GEM STOP\n')
        stopped_until = time.monotonic() + 2
        while time.monotonic() < stopped_until:
            line = lines.read()
            if STATUS.fullmatch(line): save_status(line)
            if line == 'GEM PC OFFLINE':
                emit(line); device_stop = True; break

    try:
        host, token = choose_host(args.host), secrets.token_hex(32)
        node = str(node_path) if node_path is not None else shutil.which('node')
        if not node:
            raise SessionFailure('node_missing')
        stage = 'server_spawn'
        child = subprocess.Popen([node, str(runtime / 'server/dist/local-gemini.js')], cwd=runtime / 'server',
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                 text=True, bufsize=1, env=child_env,
                                 creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        threading.Thread(target=read_server, daemon=True).start()
        if stop_event is None and sys.stdin is not None:
            threading.Thread(target=read_control, daemon=True).start()
        stage = 'server_ready'
        child.stdin.write(json.dumps({'host':host, 'token':token, 'mode':args.mode}) + '\n'); child.stdin.flush()
        state = json.loads(events.get(timeout=20))
        if not isinstance(state, dict) or state.get('event') != 'ready' or state.get('preflight') is not True:
            raise SessionFailure('server_not_ready')
        port = state.get('port')
        if type(port) is not int or not 1 <= port <= 65535:
            raise SessionFailure('invalid_server_port')
        emit(f'Gemini device server ready; mode={args.mode}; missing/wrong auth rejected')
        stage = 'serial_open'
        with serial.Serial(args.port, 115200, timeout=0.2, write_timeout=2) as device:
            config_sent = stop_attempted = False
            try:
                lines = SerialLines(device)
                stage = 'firmware_ready'
                device.reset_input_buffer(); device.write(b'GEM INFO\n')
                deadline = time.monotonic() + 8
                next_info = time.monotonic() + 2
                while time.monotonic() < deadline:
                    line = lines.read()
                    if STATUS.fullmatch(line): save_status(line)
                    if line == READY: break
                    if time.monotonic() >= next_info:
                        device.write(b'GEM INFO\n'); next_info = time.monotonic() + 2
                else:
                    raise SessionFailure('firmware_no_response')
                stage = 'configure'
                device.write(f'GEM CONFIG {host} {port} {token}\n'.encode('ascii'))
                config_sent = True
                deadline = time.monotonic() + min(max(args.seconds, 30), 580)
                configured, synthetic_sent, seen = False, False, set()
                queried = time.monotonic()
                stage = 'monitor'
                while time.monotonic() < deadline:
                    if stop_event is not None and stop_event.is_set():
                        reason = 'user_stop'
                        break
                    if not controls.empty():
                        reason = controls.get_nowait()
                        break
                    child_code = child.poll()
                    if child_code is not None:
                        raise SessionFailure('server_exit')
                    while not events.empty():
                        event = json.loads(events.get_nowait())
                        if not isinstance(event, dict): raise SessionFailure('invalid_server_event')
                        if event.get('event') == 'api-result' and event.get('status') in ('PASS', 'FAIL'):
                            safe = {k:v for k,v in event.items() if k in ('inputSamples','outputSamples','elapsedMs') and type(v) is int and 0 <= v <= 1000000}
                            safe.update(event='api-result', status=event['status']); emit(json.dumps(safe))
                            save_status(safe)
                    line = lines.read()
                    if STATUS.fullmatch(line):
                        save_status(line)
                        if line == 'GEM CONFIG OK': configured = True
                        if configured and line not in seen:
                            emit(line); seen.add(line)
                        if line == 'GEM WIFI FAIL': raise SessionFailure('wifi_failed')
                        if line == 'GEM WIFI CONNECTED' and args.mode == 'fixture' and not synthetic_sent:
                            device.write(b'GEM PROBE\n'); synthetic_sent = True
                        if line == 'GEM WIFI CONNECTED' and args.mode == 'gemini':
                            emit('Ready: click to wake; stage 2 accepts the registered call, or hold/release for manual ask. About 10 minutes; stop to finish')
                    if time.monotonic() - queried > 5:
                        device.write(b'GEM PING\n'); queried = time.monotonic()
                else:
                    reason = 'duration_limit'
                stage = 'device_stop'
                stop_device(device, lines)
                if not device_stop: raise SessionFailure('device_stop_unconfirmed')
                code = 0
            except BaseException:
                # Notify before __exit__ closes the USB handle, also on Ctrl+C.
                # Preserve the original failure if the USB link is already lost.
                if config_sent and not stop_attempted:
                    try: stop_device(device, lines)
                    except (OSError, ValueError): pass
                raise
    except KeyboardInterrupt:
        reason = 'keyboard_interrupt'
        code = 0 if device_stop else 1
        failure_stage = None if device_stop else stage
    except SessionFailure as error:
        reason = error.reason
        failure_stage = stage
    except serial.SerialException as error:
        reason, failure_stage = 'serial_error', stage
        # Inspect locally, emit only fixed classifications (never exception text).
        serial_detail = 'timeout' if isinstance(error, serial.SerialTimeoutException) else 'other'
        for marker, label in [('could not open port', 'open'), ('ClearCommError', 'status'),
                              ('ReadFile', 'read'), ('GetOverlappedResult', 'overlapped'),
                              ('WriteFile', 'write')]:
            if marker in str(error): serial_detail = label; break
    except queue.Empty:
        reason, failure_stage = 'server_ready_timeout', stage
    except json.JSONDecodeError:
        reason, failure_stage = 'invalid_server_event', stage
    except (OSError, ValueError, subprocess.SubprocessError):
        reason, failure_stage = 'operation_error', stage
    finally:
        # Cleanup failures must not erase the primary failure diagnosis.
        if child is not None:
            try:
                if child.poll() is None:
                    try: child.stdin.close()
                    except (OSError, ValueError): pass
                    try: child.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        child.terminate(); child.wait(timeout=5)
                child_code = child.poll()
                if code == 0 and child_code != 0:
                    reason, failure_stage, code = 'server_shutdown_error', 'server_stop', 1
            except (OSError, subprocess.SubprocessError):
                if code == 0:
                    reason, failure_stage, code = 'server_cleanup_error', 'server_stop', 1
        result = {'reason':reason, 'stage':failure_stage or 'complete', 'elapsedMs':elapsed(),
                  'code':code, 'serverCode':child_code, 'deviceStopConfirmed':device_stop, 'serialDetail':serial_detail}
        if report:
            report.parent.mkdir(parents=True, exist_ok=True)
            with report.open('x', encoding='utf-8') as output:
                json.dump({'version':2, 'mode':args.mode, 'statuses':statuses, 'timeline':timeline, 'exit':result}, output, indent=2)
        emit('Gemini device session exit ' + json.dumps(result))
        emit('Temporary Gemini device server stopped; no audio/token saved')
    return code


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError):
        print('Gemini device arguments/report failed; details suppressed', flush=True)
        raise SystemExit(1)
