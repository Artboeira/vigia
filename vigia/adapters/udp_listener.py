"""Escuta os anúncios UDP 7654 das Ether Dream."""
from __future__ import annotations

import logging
import socket
import struct
import sys
import threading
from typing import Callable

from ..domain.network import Interface
from ..domain.protocol import BROADCAST_PORT, BROADCAST_SIZE

log = logging.getLogger(__name__)

IP_RECVIF = 20                                   # macOS <netinet/in.h>; o módulo socket não exporta
IP_PKTINFO = getattr(socket, "IP_PKTINFO", 8)    # Linux

# sink(dados, ip_da_dac, via_ip, placa)
Sink = Callable[[bytes, str, "str | None", "str | None"], None]


def recvif_device(ancdata) -> str | None:
    """Nome da placa (en0, eth0) a partir dos dados auxiliares do recvmsg."""
    for level, kind, data in ancdata:
        try:
            if level == socket.IPPROTO_IP and kind == IP_RECVIF and sys.platform == "darwin" and len(data) >= 4:
                return socket.if_indextoname(struct.unpack_from("=H", data, 2)[0])  # sockaddr_dl.sdl_index
            if level == socket.IPPROTO_IP and kind == IP_PKTINFO and sys.platform.startswith("linux"):
                return socket.if_indextoname(struct.unpack_from("=i", data, 0)[0])  # in_pktinfo.ipi_ifindex
        except OSError:
            return None
    return None


class UdpListener:
    """Windows: um socket por placa, preso ao IP dela (o socket diz a placa; Windows não tem recvmsg).
    macOS/Linux: socket preso a IP de placa não recebe broadcast, então um socket só em 0.0.0.0
    e o kernel informa a placa de cada pacote."""

    def __init__(self, sink: Sink, port: int = BROADCAST_PORT):
        self.sink, self.port = sink, port
        self.per_interface = sys.platform == "win32"
        self._socks: dict[str, socket.socket] = {}

    def sync(self, interfaces: dict[str, Interface]) -> bool:
        """Abre/fecha sockets conforme as placas. True se há ao menos um socket escutando."""
        wanted = set(interfaces) if self.per_interface else {""}
        for ip in [ip for ip in self._socks if ip not in wanted]:
            self._socks.pop(ip).close()
        for ip in wanted - set(self._socks):
            sock = self._open(ip)
            if sock:
                self._socks[ip] = sock
                threading.Thread(target=self._listen, args=(sock, ip or None), daemon=True,
                                 name="udp-%s" % (ip or "todas")).start()
        return bool(self._socks)

    def _open(self, ip: str) -> socket.socket | None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # convive com MadMapper, LaserOS, Beyond
        if hasattr(socket, "SO_REUSEPORT"):
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except OSError:
                pass
        if not self.per_interface:
            try:
                sock.setsockopt(socket.IPPROTO_IP, IP_RECVIF if sys.platform == "darwin" else IP_PKTINFO, 1)
            except OSError:
                pass
        try:
            sock.bind((ip, self.port))
        except OSError as e:
            log.warning("porta UDP %d em %s: %s", self.port, ip or "0.0.0.0", e)
            sock.close()
            return None
        return sock

    def _listen(self, sock: socket.socket, via: str | None):
        while True:
            try:
                if via is None:
                    data, anc, _flags, addr = sock.recvmsg(2048, 256)
                    device = recvif_device(anc)
                else:
                    (data, addr), device = sock.recvfrom(2048), None
            except OSError:  # datagrama estranho (WinError 10040/10054) ou socket fechado
                if sock.fileno() < 0:
                    return
                continue
            if len(data) == BROADCAST_SIZE:
                try:
                    self.sink(data, addr[0], via, device)
                except Exception:
                    log.exception("anúncio de %s", addr[0])

    def close(self):
        for sock in self._socks.values():
            sock.close()
        self._socks.clear()
