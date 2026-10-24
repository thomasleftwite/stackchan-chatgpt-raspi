"""Install and run the real bundle in isolation, without API/device/user settings."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import selectors
import socket
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True


def check(bundle):
    spec = importlib.util.spec_from_file_location('bundle_install', bundle/'install.py')
    installer = importlib.util.module_from_spec(spec); spec.loader.exec_module(installer)
    installer.verify(bundle)
    with tempfile.TemporaryDirectory(prefix='stackchan-clean-install-') as directory:
        root = Path(directory); prefix = root/'application'
        installer.install(bundle, prefix)
        release = (prefix/'current').resolve()
        env = {'PATH': '/usr/bin:/bin', 'XDG_CONFIG_HOME': str(root/'config'), 'XDG_DATA_HOME': str(root/'data')}
        subprocess.run([str(release/'bin/stackchan-raspi'), '--diagnose'], env=env, cwd=root,
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
        node = release/'runtime/node/bin/node'
        with socket.socket() as reserved: reserved.bind(('127.0.0.1', 0)); port = reserved.getsockname()[1]
        host = subprocess.Popen([str(node), str(release/'server/dist/device-preview-host.js')], cwd=root,
            env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        try:
            host.stdin.write(json.dumps({'host': '127.0.0.1', 'subnet': '127.0.0.1/32', 'port': port, 'fixture': True, 'id': 1})+'\n'); host.stdin.flush()
            with selectors.DefaultSelector() as selector:
                selector.register(host.stdout, selectors.EVENT_READ)
                if not selector.select(10): raise ValueError('BUNDLE_START_TIMEOUT')
                if json.loads(host.stdout.readline()).get('event') != 'ready': raise ValueError('BUNDLE_START_FAILED')
            program = """import {pathToFileURL} from 'node:url';
const {runGeminiProtocolProbe}=await import(pathToFileURL(process.argv[1]).href);
const result=await runGeminiProtocolProbe(process.argv[2],'',Buffer.alloc(640));
if(result.pcm.length!==1922 || result.frames!==3) process.exit(1);
"""
            subprocess.run([str(node), '--input-type=module', '-e', program,
                str(release/'server/dist/gemini-probe-client.js'), f'ws://127.0.0.1:{port}/live'],
                env=env, cwd=root, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
            host.stdin.close(); host.wait(timeout=10)
            if host.returncode: raise ValueError('BUNDLE_STOP_FAILED')
        finally:
            if host.poll() is None: host.terminate()
            try: host.wait(timeout=5)
            except subprocess.TimeoutExpired: host.kill(); host.wait(timeout=5)
            host.stdout.close()
        if (root/'config').exists() or (root/'data').exists(): raise ValueError('BUNDLE_READ_PRIVATE_SETTINGS')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('bundle', type=Path); args = parser.parse_args()
    try: check(args.bundle.absolute()); print('BUNDLE_SMOKE_PASS')
    except Exception: print('BUNDLE_SMOKE_FAILED'); raise SystemExit(1)
