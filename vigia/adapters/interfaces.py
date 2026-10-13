"""Placas IPv4 ativas do computador, por sistema operacional."""
from __future__ import annotations

import ctypes
import re
import socket
import struct
import subprocess
import sys

from ..domain.network import Interface


def _run(*cmd: str) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=3).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def parse_ifconfig(ifconfig: str, ports: str = "") -> dict[str, Interface]:
    """macOS: saídas de `ifconfig` e `networksetup -listallhardwareports`."""
    names = {dev: port for port, dev in re.findall(r"Hardware Port: (.+)\nDevice: (\S+)", ports)}
    nets, dev = {}, None
    for line in ifconfig.splitlines():
        m = re.match(r"(\w+): flags=", line)
        if m:
            dev = m.group(1)
        m = re.match(r"\s+inet (\S+) netmask 0x([0-9a-f]{8})", line)
        if m and dev and not m.group(1).startswith("127."):
            nets[m.group(1)] = Interface(m.group(1), socket.inet_ntoa(bytes.fromhex(m.group(2))),
                                         names.get(dev, ""), dev)
    return nets


def parse_ip_addr(output: str) -> dict[str, Interface]:
    """Linux: saída de `ip -o -4 addr show`."""
    nets = {}
    for m in re.finditer(r"^\d+:\s+(\S+)\s+inet (\d+\.\d+\.\d+\.\d+)/(\d+)", output, re.M):
        dev, ip, bits = m.group(1), m.group(2), int(m.group(3))
        if ip.startswith("127."):
            continue
        mask = socket.inet_ntoa(struct.pack(">I", (0xFFFFFFFF << (32 - bits)) & 0xFFFFFFFF))
        nets[ip] = Interface(ip, mask, "", dev)
    return nets


class MacInterfaces:
    def interfaces(self) -> dict[str, Interface]:
        return parse_ifconfig(_run("/sbin/ifconfig"), _run("/usr/sbin/networksetup", "-listallhardwareports"))


class LinuxInterfaces:
    def interfaces(self) -> dict[str, Interface]:
        return parse_ip_addr(_run("ip", "-o", "-4", "addr", "show"))


class WindowsInterfaces:
    """iphlpapi: GetIpAddrTable + alias da placa."""

    def interfaces(self) -> dict[str, Interface]:
        iph = ctypes.windll.iphlpapi  # type: ignore[attr-defined]
        size = ctypes.c_ulong(0)
        iph.GetIpAddrTable(None, ctypes.byref(size), False)
        buf = ctypes.create_string_buffer(max(size.value, 4))
        if iph.GetIpAddrTable(buf, ctypes.byref(size), False):
            return {}
        nets = {}
        for i in range(struct.unpack_from("<I", buf)[0]):
            addr, index, mask, _bcast, _reasm, _unused, kind = struct.unpack_from("<IIIIIHH", buf, 4 + 24 * i)
            if kind & 0x48:  # MIB_IPADDR_DISCONNECTED | MIB_IPADDR_DELETED
                continue
            ip = socket.inet_ntoa(struct.pack("<I", addr))
            if ip.startswith("127."):
                continue
            luid, alias = ctypes.c_uint64(), ctypes.create_unicode_buffer(257)
            named = (iph.ConvertInterfaceIndexToLuid(index, ctypes.byref(luid)) == 0
                     and iph.ConvertInterfaceLuidToAlias(ctypes.byref(luid), alias, 257) == 0)
            nets[ip] = Interface(ip, socket.inet_ntoa(struct.pack("<I", mask)), alias.value if named else "")
        return nets


def platform_interfaces():
    if sys.platform == "darwin":
        return MacInterfaces()
    if sys.platform == "win32":
        return WindowsInterfaces()
    return LinuxInterfaces()
