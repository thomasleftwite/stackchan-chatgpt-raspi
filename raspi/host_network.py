"""Read-only discovery of the dedicated NetworkManager AP boundary."""
from dataclasses import dataclass
import ipaddress
import json
import re
import subprocess


class HostError(Exception):
    pass


@dataclass(frozen=True)
class Endpoint:
    host: str
    subnet: str


def parse_ap(mode, method, addresses):
    if mode != 'ap' or method != 'shared': raise HostError('AP_REQUIRED')
    candidates = [item for device in addresses for item in device.get('addr_info', []) if item.get('family') == 'inet']
    if len(candidates) != 1: raise HostError('AP_ADDRESS_REQUIRED')
    item = candidates[0]
    try: address = ipaddress.IPv4Interface(f"{item['local']}/{item['prefixlen']}")
    except (ValueError, KeyError): raise HostError('AP_ADDRESS_REQUIRED') from None
    allowed = ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16')
    if not 16 <= address.network.prefixlen <= 30 or not any(address.ip in ipaddress.ip_network(net) for net in allowed):
        raise HostError('AP_ADDRESS_REQUIRED')
    if address.ip in (address.network.network_address, address.network.broadcast_address):
        raise HostError('AP_ADDRESS_REQUIRED')
    return Endpoint(str(address.ip), str(address.network))


def discover_ap(interface='wlan0'):
    if not re.fullmatch(r'[A-Za-z0-9_.:-]{1,32}', interface): raise HostError('AP_REQUIRED')
    def read(args):
        result = subprocess.run(args, capture_output=True, text=True, timeout=10)
        if result.returncode: raise HostError('AP_REQUIRED')
        return result.stdout.strip()
    try:
        identity = read(['nmcli', '-g', 'GENERAL.CON-UUID', 'device', 'show', interface])
        values = read(['nmcli', '-g', '802-11-wireless.mode,ipv4.method', 'connection', 'show', 'uuid', identity]).splitlines()
        if len(values) != 2: raise HostError('AP_REQUIRED')
        addresses = json.loads(read(['ip', '-j', '-4', 'address', 'show', 'dev', interface]))
        return parse_ap(*values, addresses)
    except HostError: raise
    except Exception: raise HostError('AP_REQUIRED') from None
