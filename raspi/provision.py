"""Configure the device through WiFiManager, keeping wired internet intact."""
from dataclasses import dataclass, field
from html.parser import HTMLParser
import json
import sys
import urllib.parse
import urllib.request


class ProvisionError(Exception):
    """Only fixed error codes may reach the UI or logs."""


@dataclass(repr=False)
class Credentials:
    ssid: str
    password: str = field(repr=False)

    def validate(self):
        if not isinstance(self.ssid, str) or not 1 <= len(self.ssid.encode()) <= 32:
            raise ProvisionError('INVALID_SSID')
        if any(c in self.ssid for c in '\r\n\0'):
            raise ProvisionError('INVALID_SSID')
        if not isinstance(self.password, str) or not 8 <= len(self.password) <= 63:
            raise ProvisionError('INVALID_PASSWORD')
        if not all(32 <= ord(c) <= 126 for c in self.password):
            raise ProvisionError('INVALID_PASSWORD')


class _Forms(HTMLParser):
    def __init__(self):
        super().__init__(); self.current = None; self.valid = False

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == 'form':
            self.current = set() if values.get('action') in ('/wifisave', 'wifisave') else None
        if tag == 'input' and self.current is not None:
            self.current.add(values.get('name'))

    def handle_endtag(self, tag):
        if tag == 'form':
            if self.current is not None and {'s', 'p'} <= self.current:
                self.valid = True
            self.current = None


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class WifiManagerPortal:
    URL = 'http://192.168.4.1'

    def __init__(self, opener=None):
        self.opener = opener or urllib.request.build_opener(
            urllib.request.ProxyHandler({}), _NoRedirect())

    def save(self, target):
        target.validate()
        try:
            with self.opener.open(self.URL + '/0wifi', timeout=8) as response:
                if response.status != 200: raise ProvisionError('PORTAL_UNAVAILABLE')
                page = response.read(65537)
            if len(page) > 65536: raise ProvisionError('PORTAL_UNAVAILABLE')
            parser = _Forms(); parser.feed(page.decode('utf-8', errors='replace'))
            if not parser.valid: raise ProvisionError('PORTAL_FORM_MISMATCH')
            payload = urllib.parse.urlencode({'s': target.ssid, 'p': target.password}).encode()
            request = urllib.request.Request(self.URL + '/wifisave', data=payload,
                headers={'Content-Type': 'application/x-www-form-urlencoded'}, method='POST')
            with self.opener.open(request, timeout=8) as response:
                if response.status != 200: raise ProvisionError('SAVE_NOT_CONFIRMED')
                # Do not log, save, or parse a response that might echo credentials.
                response.read(65536)
        except ProvisionError:
            raise
        except Exception:
            raise ProvisionError('PORTAL_REQUEST_FAILED') from None


def provision(network, setup, portal=None):
    setup.validate()
    target = network.prepare()
    try:
        network.connect_setup(setup)
        network.check_setup_route()
        (portal or WifiManagerPortal()).save(target)
    except ProvisionError:
        raise
    except Exception:
        raise ProvisionError('SETUP_FAILED') from None
    finally:
        network.restore_ap()
    return {'event': 'complete', 'saved': True, 'apRestored': True}


def main():
    if sys.argv[1:] == ['--gui']:
        from raspi.provision_ui import main as gui
        gui(); return 0
    if sys.argv[1:] != ['--execute-stdin']:
        print('Usage: python3 -m raspi.provision --gui'); return 2
    try:
        value = json.loads(sys.stdin.read(4097))
        setup = Credentials(value['ssid'], value['password'])
        from raspi.provision_network import NetworkManagerSetup
        result = provision(NetworkManagerSetup(), setup)
    except Exception as error:
        codes = {'INVALID_SSID', 'INVALID_PASSWORD', 'WIRED_REQUIRED', 'AP_REQUIRED',
            'CHECKPOINT_FAILED', 'SETUP_CONNECT_FAILED', 'SETUP_ROUTE_FAILED',
            'PORTAL_UNAVAILABLE', 'PORTAL_FORM_MISMATCH', 'SAVE_NOT_CONFIRMED',
            'PORTAL_REQUEST_FAILED', 'SETUP_FAILED', 'AP_RESTORE_FAILED'}
        code = str(error) if isinstance(error, ProvisionError) and str(error) in codes else 'SETUP_FAILED'
        print(json.dumps({'event': 'failed', 'code': code})); return 1
    print(json.dumps(result)); return 0


if __name__ == '__main__':
    # Keep exception identities consistent with the backend's package imports.
    from raspi.provision import main as run_main
    raise SystemExit(run_main())
