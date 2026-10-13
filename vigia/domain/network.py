"""Regras de rede: faixa, IP duplicado, placa que recebeu, sugestões de IP."""
from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from enum import Enum
from typing import Iterable


@dataclass(frozen=True)
class Interface:
    """Placa IPv4 ativa do computador."""
    ip: str
    mask: str
    name: str = ""     # nome amigável: Wi-Fi, Ethernet
    device: str = ""   # nome do sistema: en0, eth0

    @property
    def network(self) -> ipaddress.IPv4Network:
        return subnet(self.ip, self.mask)

    @property
    def label(self) -> str:
        return self.name or self.device or self.ip


class NetIssue(str, Enum):
    WRONG_SUBNET = "faixa"
    DUPLICATE_IP = "duplicado"


@dataclass(frozen=True)
class IpPlan:
    ip: str
    mask: str
    gateway: str


def subnet(ip: str, mask: str) -> ipaddress.IPv4Network:
    return ipaddress.ip_interface("%s/%s" % (ip, mask)).network


def resolve_via(dac_ip: str, interfaces: dict[str, Interface], device: str | None = None,
                via_ip: str | None = None) -> str:
    """IP da placa do PC que recebeu o anúncio: a do socket (Windows), a placa informada pelo
    kernel (macOS IP_RECVIF, Linux IP_PKTINFO), a que tem a DAC na faixa, a única ativa, ou ''."""
    if via_ip:
        return via_ip
    if device:
        for ip, iface in interfaces.items():
            if iface.device == device:
                return ip
    addr = ipaddress.ip_address(dac_ip)
    for ip, iface in interfaces.items():
        if addr in iface.network:
            return ip
    return next(iter(interfaces)) if len(interfaces) == 1 else ""


def net_issue(dac_ip: str, via: str, interfaces: dict[str, Interface],
              other_online_ips: Iterable[str]) -> NetIssue | None:
    """Faixa errada (DAC fora da rede da placa que a recebe) ou IP duplicado (outra DAC online)."""
    iface = interfaces.get(via)
    if iface and ipaddress.ip_address(dac_ip) not in iface.network:
        return NetIssue.WRONG_SUBNET
    if dac_ip in set(other_online_ips):
        return NetIssue.DUPLICATE_IP
    return None


def suggest_dac_ip(pc_ip: str, mask: str, used: Iterable[str]) -> IpPlan | None:
    """IP livre para a DAC na rede da placa do PC, a partir do host .50 (valores do ip.txt da ED4)."""
    net, taken = subnet(pc_ip, mask), set(used) | {pc_ip}
    for k in range(50, net.num_addresses - 1):
        ip = str(net.network_address + k)
        if ip not in taken:
            return IpPlan(ip, mask, str(net.network_address + 1))
    return None


def suggest_pc_ip(dac_ip: str, used: Iterable[str] = ()) -> IpPlan:
    """IP fixo para o PC na faixa da DAC. Rede de show costuma ser /24; link-local (169.254) é /16.
    Começa no host .10 e pula a própria DAC e os IPs em uso."""
    link_local = ipaddress.ip_address(dac_ip).is_link_local
    mask = "255.255.0.0" if link_local else "255.255.255.0"
    base = dac_ip.rsplit(".", 1)[0]
    taken = set(used) | {dac_ip}
    for last in range(10, 255):
        ip = "%s.%d" % (base, last)
        if ip not in taken:
            return IpPlan(ip, mask, "")
    return IpPlan("%s.10" % base, mask, "")
