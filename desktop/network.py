"""Private adapter selection without CIM or SSID/account enumeration."""
import ipaddress
import json
import os
from pathlib import Path
import subprocess

PRIVATE = tuple(ipaddress.ip_network(n) for n in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16'))

def is_lan(value):
    try: return any(ipaddress.ip_address(value) in net for net in PRIVATE)
    except ValueError: return False

def local_addresses():
    script = """[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new();
$result=@([System.Net.NetworkInformation.NetworkInterface]::GetAllNetworkInterfaces() |
 Where-Object {$_.OperationalStatus -eq 'Up'} | ForEach-Object {
 $n=$_.GetIPProperties();
 $n.UnicastAddresses | Where-Object {$_.Address.AddressFamily -eq 'InterNetwork'} |
 ForEach-Object {$_.Address.IPAddressToString}}); ConvertTo-Json -Compress -InputObject $result"""
    shell = Path(os.environ.get('SystemRoot', 'C:/Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    result = subprocess.run([str(shell),'-NoProfile','-NonInteractive','-Command',script],
        capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=15,
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0), check=True)
    values = json.loads(result.stdout)
    return sorted({v for v in values if isinstance(v,str) and is_lan(v)})

def hotspot_networks():
    """Only active Windows mobile-hotspot adapters, never the upstream Wi-Fi."""
    script="""[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new();
$result=@([System.Net.NetworkInformation.NetworkInterface]::GetAllNetworkInterfaces() |
 Where-Object {$_.OperationalStatus -eq 'Up' -and $_.Description -like '*Wi-Fi Direct*'} |
 ForEach-Object {$_.GetIPProperties().UnicastAddresses |
 Where-Object {$_.Address.AddressFamily -eq 'InterNetwork'} |
 ForEach-Object {@{address=$_.Address.IPAddressToString;mask=$_.IPv4Mask.IPAddressToString}}});
ConvertTo-Json -Compress -InputObject $result"""
    shell=Path(os.environ.get('SystemRoot','C:/Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'
    result=subprocess.run([str(shell),'-NoProfile','-NonInteractive','-Command',script],capture_output=True,
        text=True,encoding='utf-8',errors='replace',timeout=15,
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),check=True)
    networks={}
    for item in json.loads(result.stdout):
        try:
            address=item['address']; interface=ipaddress.ip_interface(address+'/'+item['mask'])
            if is_lan(address) and 16<=interface.network.prefixlen<=30:
                networks[address]=str(interface.network)
        except (KeyError,TypeError,ValueError): continue
    return networks
