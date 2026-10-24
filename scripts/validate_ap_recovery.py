"""Explicit, checkpoint-protected AP interruption; never touch eth0 or credentials."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def cycle(driver, pause=time.sleep):
    driver.prepare()
    try:
        driver.disconnect(); pause(5)
    finally:
        try:
            driver.restore(); driver.check_wired(); driver.commit()
        except Exception:
            driver.rollback()
            raise


class NetworkManagerDriver:
    def __init__(self):
        import dbus
        self.dbus = dbus; self.bus = dbus.SystemBus()
        self.manager = dbus.Interface(self.bus.get_object('org.freedesktop.NetworkManager',
            '/org/freedesktop/NetworkManager'), 'org.freedesktop.NetworkManager')

    def properties(self, path):
        return self.dbus.Interface(self.bus.get_object('org.freedesktop.NetworkManager', path),
                                   'org.freedesktop.DBus.Properties')

    def check_wired(self):
        result = subprocess.run(['ip', '-j', '-4', 'route', 'show', 'default'], capture_output=True, text=True, timeout=5)
        routes = json.loads(result.stdout)
        if result.returncode or not routes or any(r.get('dev') != 'eth0' for r in routes): raise ValueError('WIRED_REQUIRED')
        result = subprocess.run(['curl', '--interface', 'eth0', '--fail', '--silent', '--show-error',
            '--max-time', '15', '--output', '/dev/null', 'https://github.com/'], capture_output=True, timeout=20)
        if result.returncode: raise ValueError('WIRED_REQUIRED')

    def prepare(self):
        from raspi.host_network import discover_ap
        discover_ap(); self.check_wired()
        self.device = self.manager.GetDeviceByIpIface('wlan0')
        self.active = self.properties(self.device).Get('org.freedesktop.NetworkManager.Device', 'ActiveConnection')
        self.original = self.properties(self.active).Get('org.freedesktop.NetworkManager.Connection.Active', 'Connection')
        self.checkpoint = self.manager.CheckpointCreate([self.device], 180, 0)

    def disconnect(self): self.manager.DeactivateConnection(self.active)

    def restore(self):
        self.manager.ActivateConnection(self.original, self.device, '/')
        deadline = time.monotonic()+45
        while time.monotonic() < deadline:
            current = self.properties(self.device).Get('org.freedesktop.NetworkManager.Device', 'ActiveConnection')
            state = self.properties(self.device).Get('org.freedesktop.NetworkManager.Device', 'State')
            if current != '/' and state == 100:
                connection = self.properties(current).Get('org.freedesktop.NetworkManager.Connection.Active', 'Connection')
                if connection == self.original: return
            time.sleep(.5)
        raise ValueError('AP_RESTORE_FAILED')

    def commit(self): self.manager.CheckpointDestroy(self.checkpoint)
    def rollback(self):
        try: self.manager.CheckpointRollback(self.checkpoint)
        except Exception: pass  # The daemon's 180s timeout remains the final recovery path.


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--execute', action='store_true'); args = parser.parse_args()
    if not args.execute:
        print('PLAN: checkpoint wlan0 for 180s; AP off 5s; restore original AP; eth0 unchanged.'); return 0
    try: cycle(NetworkManagerDriver()); print('AP_CYCLE_PASS'); return 0
    except Exception: print('AP_CYCLE_FAILED_CHECKPOINT_RECOVERY'); return 1


if __name__ == '__main__': raise SystemExit(main())
