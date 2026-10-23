"""NetworkManager transaction: AP -> temporary device client -> original AP."""
import json
import subprocess
import time
import uuid

from raspi.provision import Credentials, ProvisionError


class NetworkManagerSetup:
    def __init__(self):
        import dbus
        self.dbus = dbus
        self.bus = dbus.SystemBus()
        self.manager = dbus.Interface(self.bus.get_object('org.freedesktop.NetworkManager',
            '/org/freedesktop/NetworkManager'), 'org.freedesktop.NetworkManager')
        self.settings = dbus.Interface(self.bus.get_object('org.freedesktop.NetworkManager',
            '/org/freedesktop/NetworkManager/Settings'), 'org.freedesktop.NetworkManager.Settings')
        self.temporary = None

    def _connection(self, path):
        return self.dbus.Interface(self.bus.get_object('org.freedesktop.NetworkManager', path),
            'org.freedesktop.NetworkManager.Settings.Connection')

    @staticmethod
    def _run(args):
        result = subprocess.run(args, capture_output=True, text=True, timeout=25)
        if result.returncode: raise ProvisionError('SETUP_FAILED')
        return result.stdout.strip()

    def _wired(self):
        routes = json.loads(self._run(['ip', '-j', '-4', 'route', 'show', 'default']))
        if not routes or any(route.get('dev') != 'eth0' for route in routes):
            raise ProvisionError('WIRED_REQUIRED')
        self._run(['curl', '--interface', 'eth0', '--fail', '--silent', '--show-error',
            '--max-time', '15', '--output', '/dev/null', 'https://github.com/'])

    def prepare(self):
        self._wired()
        self.device = self.manager.GetDeviceByIpIface('wlan0')
        current = self._run(['nmcli', '-g', 'GENERAL.CON-UUID', 'device', 'show', 'wlan0'])
        for path in self.settings.ListConnections():
            connection = self._connection(path); values = connection.GetSettings()
            if str(values.get('connection', {}).get('uuid')) == current:
                wifi = values.get('802-11-wireless', {})
                if wifi.get('mode') != 'ap': raise ProvisionError('AP_REQUIRED')
                secrets = connection.GetSecrets('802-11-wireless-security')
                target = Credentials(bytes(wifi['ssid']).decode(),
                    str(secrets['802-11-wireless-security']['psk']))
                target.validate(); self.original = path; self.original_uuid = current
                break
        else: raise ProvisionError('AP_REQUIRED')
        try:
            # Rollback restores only wlan0; eth0 remains the permanent upstream.
            # No global "delete new connections" flag: unrelated profiles are untouched.
            self.checkpoint = self.manager.CheckpointCreate([self.device], 180, 0)
        except Exception:
            raise ProvisionError('CHECKPOINT_FAILED') from None
        return target

    def _wait(self, expected_uuid):
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            current = self._run(['nmcli', '-g', 'GENERAL.CON-UUID', 'device', 'show', 'wlan0'])
            state = self._run(['nmcli', '-g', 'GENERAL.STATE', 'device', 'show', 'wlan0'])
            if current == expected_uuid and state.startswith('100 '): return
            time.sleep(.5)
        raise ProvisionError('SETUP_CONNECT_FAILED')

    def connect_setup(self, setup):
        dbus = self.dbus; identity = str(uuid.uuid4())
        values = {
            'connection': {'id': 'stackchan-device-setup-temporary', 'uuid': identity,
                'type': '802-11-wireless', 'interface-name': 'wlan0', 'autoconnect': dbus.Boolean(False)},
            '802-11-wireless': {'ssid': dbus.ByteArray(setup.ssid.encode()), 'mode': 'infrastructure'},
            '802-11-wireless-security': {'key-mgmt': 'wpa-psk', 'psk': setup.password},
            'ipv4': {'method': 'auto', 'never-default': dbus.Boolean(True), 'ignore-auto-dns': dbus.Boolean(True)},
            'ipv6': {'method': 'disabled', 'never-default': dbus.Boolean(True)},
        }
        self.temporary = self.settings.AddConnectionUnsaved(dbus.Dictionary(
            {key: dbus.Dictionary(value, signature='sv') for key, value in values.items()}, signature='sa{sv}'))
        try:
            self.manager.ActivateConnection(self.temporary, self.device, '/')
            self._wait(identity)
        except Exception:
            raise ProvisionError('SETUP_CONNECT_FAILED') from None

    def check_setup_route(self):
        self._wired()
        routes = json.loads(self._run(['ip', '-j', '-4', 'route', 'get', '192.168.4.1']))
        if not routes or any(route.get('dev') != 'wlan0' for route in routes):
            raise ProvisionError('SETUP_ROUTE_FAILED')

    def restore_ap(self):
        try:
            self.manager.ActivateConnection(self.original, self.device, '/')
            self._wait(self.original_uuid)
            if self.temporary is not None: self._connection(self.temporary).Delete()
            self._wired()
            self.manager.CheckpointDestroy(self.checkpoint)
        except Exception:
            if self.temporary is not None:
                try: self._connection(self.temporary).Delete()
                except Exception: pass
            try: self.manager.CheckpointRollback(self.checkpoint)
            except Exception: pass
            raise ProvisionError('AP_RESTORE_FAILED') from None
