"""Temporary LAN PCM probe. Secrets stay in RAM/USB; no raw logs/audio files."""
import argparse
import ipaddress
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

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = tuple(ipaddress.ip_network(n) for n in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16'))
STATUS = re.compile(r'LAN (?:READY v=1 input=16000 output=24000 mono=1 bits=16|CONFIG OK|WIFI (?:CONNECTED|FAIL)|MEMORY FAIL|CAPTURE (?:NONE|FAIL|DONE samples=48000 ms=\d{1,6} rms=\d{1,5} peak=\d{1,5} clipped=\d{1,5})|RESULT (?:NONE|(?:PASS|FAIL) gen=\d{1,10} frames=\d{1,3} input=\d{1,5} output=\d{1,5} ms=\d{1,6})|PLAYBACK (?:PASS samples=72000 rate=24000|FAIL))')


def private_host(value):
    address = ipaddress.ip_address(value)
    if not isinstance(address, ipaddress.IPv4Address) or not any(address in net for net in PRIVATE):
        raise ValueError('Private IPv4 interface required')
    return str(address)


def choose_host(explicit):
    if explicit:
        return private_host(explicit)
    # Read interface addresses only, never SSIDs/passwords/account details.
    script = '[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new(); Get-NetIPConfiguration | Where-Object {$_.IPv4DefaultGateway} | ForEach-Object {$_.IPv4Address.IPAddress}'
    result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
                            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=15, check=True)
    candidates = set()
    for value in result.stdout.splitlines():
        try:
            candidates.add(private_host(value.strip()))
        except ValueError:
            pass
    if len(candidates) != 1:
        raise ValueError('Choose one private LAN interface with --host')
    return candidates.pop()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', required=True)
    parser.add_argument('--host', help='Optional private IPv4 interface; never printed/saved')
    parser.add_argument('--seconds', type=int, default=600)
    parser.add_argument('--report', type=Path, help='New .pio path for approved numeric/status results only')
    args = parser.parse_args()
    report_path = args.report.resolve() if args.report else None
    if report_path and (not report_path.is_relative_to((ROOT / '.pio').resolve()) or report_path.exists()):
        raise ValueError('Choose a new report path under .pio')
    host = choose_host(args.host)
    node = shutil.which('node')
    if not node:
        raise ValueError('Node.js is required')
    token = secrets.token_hex(32)
    statuses, seen = [], set()
    child = subprocess.Popen([node, str(ROOT / 'server/dist/local-lan.js')], cwd=ROOT / 'server',
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                             text=True, bufsize=1)
    controls = queue.Queue()
    def control_reader():
        for line in sys.stdin:
            if line.strip() == 'stop':
                controls.put('stop')
    threading.Thread(target=control_reader, daemon=True).start()
    startup = queue.Queue(maxsize=64)
    def server_reader():
        for line in child.stdout:
            startup.put(line)
    threading.Thread(target=server_reader, daemon=True).start()
    try:
        child.stdin.write(json.dumps({'host': host, 'token': token}) + '\n')
        child.stdin.flush()
        state = json.loads(startup.get(timeout=20))
        if state.get('event') != 'ready' or state.get('preflight') is not True:
            raise ValueError('LAN server preflight failed')
        listen_port = state['port']
        if not isinstance(listen_port, int) or not 1 <= listen_port <= 65535:
            raise ValueError('Invalid listener port')
        print('LAN server ready; missing/wrong auth rejected; PCM preflight PASS', flush=True)
        with serial.Serial(args.port, 115200, timeout=0.2) as connection:
            connection.reset_input_buffer()
            connection.write(b'LAN INFO\n')
            ready_until = time.monotonic() + 8
            is_ready = False
            while time.monotonic() < ready_until:
                line = connection.read_until(b'\n', 200).decode('ascii', errors='replace').strip()
                if line == 'LAN READY v=1 input=16000 output=24000 mono=1 bits=16':
                    is_ready = True
                    break
            if not is_ready:
                raise ValueError('LAN probe firmware did not respond')
            # Ephemeral configuration: never echoed, logged, placed in argv or saved.
            connection.write(f'LAN CONFIG {host} {listen_port} {token}\n'.encode('ascii'))
            deadline = time.monotonic() + min(max(args.seconds, 30), 580)
            queried = time.monotonic()
            synthetic_sent = False
            config_acknowledged = False
            while time.monotonic() < deadline and controls.empty():
                if child.poll() is not None:
                    raise ValueError('LAN server stopped unexpectedly')
                while not startup.empty():
                    notice = json.loads(startup.get_nowait())
                    if notice.get('event') == 'notice' and notice.get('stage') in ('decode', 'order', 'resample', 'transport', 'closed') and isinstance(notice.get('value'), int):
                        print(f'Server probe notice: {notice["stage"]} value={notice["value"]}', flush=True)
                line = connection.read_until(b'\n', 200).decode('ascii', errors='replace').strip()
                if STATUS.fullmatch(line) or re.fullmatch(r'LAN FAULT code=\d{1,2}', line):
                    if line == 'LAN CONFIG OK':
                        config_acknowledged = True
                    if not config_acknowledged:
                        continue  # Ignore retained results from a previous run.
                    if line not in seen:
                        print(line, flush=True)
                        statuses.append(line)
                        seen.add(line)
                    if line == 'LAN WIFI FAIL':
                        raise ValueError('Saved Wi-Fi did not connect')
                    if line == 'LAN WIFI CONNECTED' and not synthetic_sent:
                        print('Starting synthetic PCM roundtrip (3-second tone, no microphone)', flush=True)
                        connection.write(b'LAN SYNTH\n')
                        synthetic_sent = True
                if time.monotonic() - queried > 5:
                    connection.write(b'LAN INFO\n')
                    queried = time.monotonic()
    finally:
        # Terminate only the child server created by this run.
        if child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=5)
        child.stdin.close()
        if report_path:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            with report_path.open('x', encoding='utf-8') as output:
                output.write(json.dumps({'version': 1, 'statuses': statuses}, indent=2) + '\n')
        print('Temporary LAN server stopped; no token/audio saved', flush=True)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError, queue.Empty, json.JSONDecodeError):
        print('LAN probe stopped: configuration, connectivity or device check failed (details suppressed)', flush=True)
        raise SystemExit(1)
