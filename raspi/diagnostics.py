"""Fixed diagnostic codes only; never load keys, preferences or audio."""
import importlib.metadata
import importlib.util
import json
import platform
from pathlib import Path
import shutil
import subprocess
import sys


def checks(network=False):
    from raspi.host import ROOT, resolve_node
    profile = json.loads((Path(__file__).parent/'release-profile.json').read_text())
    result = {'linux': sys.platform == 'linux', 'arm64': platform.machine() in ('aarch64', 'arm64'),
        'python': f'{sys.version_info.major}.{sys.version_info.minor}' == profile['python'],
        'tkinter': importlib.util.find_spec('tkinter') is not None,
        'nmcli': shutil.which('nmcli') is not None, 'ip': shutil.which('ip') is not None,
        'dbus': importlib.util.find_spec('dbus') is not None,
        'server': all((ROOT/'server/dist'/name).is_file() for name in
            ('wireless-host.js', 'device-preview-host.js', 'voice-preview.js'))}
    try: result['cryptography'] = importlib.metadata.version('cryptography') == profile['cryptography']
    except importlib.metadata.PackageNotFoundError: result['cryptography'] = False
    try:
        node = resolve_node()
        result['node'] = subprocess.run([str(node), '--version'], capture_output=True,
            text=True, timeout=5).stdout.strip() == 'v'+profile['node']
    except Exception: result['node'] = False
    if network:
        from raspi.host_network import discover_ap
        try: discover_ap(); result['dedicated_ap'] = True
        except Exception: result['dedicated_ap'] = False
        try:
            command = subprocess.run(['ip', '-j', 'route', 'show', 'default'], capture_output=True, text=True, timeout=5)
            routes = json.loads(command.stdout)
            result['wired_default_only'] = command.returncode == 0 and bool(routes) and all(r.get('dev') == 'eth0' for r in routes)
        except Exception: result['wired_default_only'] = False
    return result


def main(network=False):
    try: result = checks(network)
    except Exception:
        print('DIAGNOSTIC_UNAVAILABLE'); return 1
    for code, ok in result.items(): print(code.upper()+': '+('PASS' if ok else 'FAIL'))
    return 0 if all(result.values()) else 1


if __name__ == '__main__': raise SystemExit(main(network='--network' in sys.argv))
