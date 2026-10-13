"""Protocolo Ether Dream (ED2, ED3, ED4): bytes entram, valores saem. Nenhum I/O aqui.

Referência: https://ether-dream.com/protocol.html
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import Enum

BROADCAST_PORT = 7654
CONTROL_PORT = 7765
BROADCAST_SIZE = 36   # anúncio UDP: MAC(6) + cabeçalho(10) + dac_status(20)
STATUS_SIZE = 20
RESPONSE_SIZE = 22    # resposta TCP padrão: código, comando, dac_status
VERSION_SIZE = 32     # resposta do comando 'v' (versão do firmware)

_STATUS = struct.Struct("<BBBBHHHHII")
_HEADER = struct.Struct("<HHHI")

# light_engine_state
LE_READY, LE_WARMUP, LE_COOLDOWN, LE_ESTOP = 0, 1, 2, 3
# playback_state
PB_IDLE, PB_PREPARED, PB_PLAYING = 0, 1, 2

# bits de light_engine_flags
LEF_NETWORK_CMD = 0        # E-stop pedido por comando de rede
LEF_INTERLOCK_TRIPPED = 1  # interlock abriu em algum momento (travado)
LEF_INTERLOCK_OPEN = 2     # interlock aberto agora
LEF_TEMP_TRIPPED = 3       # sobretemperatura em algum momento (travado)
LEF_OVER_TEMP = 4          # sobretemperatura agora
LEF_LINK_LOST = 5          # link Ethernet caiu durante o stream

# bits de playback_flags
PBF_SHUTTER = 0
PBF_UNDERFLOW = 1
PBF_ESTOP = 2

SOURCES = {0: "rede", 1: "cartao", 2: "gerador"}


def has_bit(value: int, n: int) -> bool:
    return value >> n & 1 == 1


@dataclass(frozen=True)
class DacStatus:
    """struct dac_status (20 bytes)."""
    protocol: int = 0
    light_engine: int = LE_READY
    playback: int = PB_IDLE
    source: int = 0
    le_flags: int = 0
    playback_flags: int = 0
    source_flags: int = 0
    fullness: int = 0
    point_rate: int = 0
    point_count: int = 0

    @classmethod
    def parse(cls, data: bytes) -> "DacStatus":
        return cls(*_STATUS.unpack(data[:STATUS_SIZE]))

    def pack(self) -> bytes:
        return _STATUS.pack(self.protocol, self.light_engine, self.playback, self.source, self.le_flags,
                            self.playback_flags, self.source_flags, self.fullness, self.point_rate,
                            self.point_count)

    @property
    def estop(self) -> bool:
        return self.light_engine == LE_ESTOP

    def le_flag(self, n: int) -> bool:
        return has_bit(self.le_flags, n)

    def pb_flag(self, n: int) -> bool:
        return has_bit(self.playback_flags, n)

    @property
    def network_flag_only(self) -> bool:
        """E-stop só com o flag 'comando de rede'. Na ED4 o MadMapper deixa esse flag ligado e o stream
        segue tocando (observado pelo autor do sitter original em 2026-10-12): não é falha física."""
        return self.estop and self.le_flags == 1 << LEF_NETWORK_CMD


@dataclass(frozen=True)
class Announcement:
    """Pacote de anúncio UDP, já decodificado. received_at vem do relógio de quem recebeu."""
    mac: str               # 12 dígitos hex minúsculos
    hw_rev: int
    sw_rev: int
    buffer_capacity: int
    max_point_rate: int
    status: DacStatus
    ip: str
    received_at: float

    @classmethod
    def parse(cls, data: bytes, ip: str, received_at: float) -> "Announcement":
        if len(data) != BROADCAST_SIZE:
            raise ValueError("anúncio Ether Dream tem %d bytes, recebi %d" % (BROADCAST_SIZE, len(data)))
        hw, sw, capacity, max_rate = _HEADER.unpack(data[6:16])
        return cls(data[:6].hex(), hw, sw, capacity, max_rate, DacStatus.parse(data[16:]), ip, received_at)


def build_announcement(mac: str, hw_rev: int, sw_rev: int, capacity: int, max_rate: int,
                       status: DacStatus) -> bytes:
    """Monta um anúncio (simulador e testes)."""
    return bytes.fromhex(mac) + _HEADER.pack(hw_rev, sw_rev, capacity, max_rate) + status.pack()


def build_response(code: bytes, command: bytes, status: DacStatus) -> bytes:
    """Monta uma resposta TCP de 22 bytes (simulador e testes)."""
    return code + command + status.pack()


class ClearOutcome(str, Enum):
    CLEARED = "limpo"
    NOT_IN_ESTOP = "nao_estava"
    STILL_ESTOP = "continua"
    NAK_ACTIVE = "nak_causa_ativa"
    NAK_INVALID = "nak_invalido"
    NAK_FULL = "nak_buffer"
    UNKNOWN = "desconhecida"


@dataclass(frozen=True)
class ClearReply:
    outcome: ClearOutcome
    code: bytes = b""


def clear_outcome(hello: bytes, resp: bytes) -> ClearReply:
    """Resposta do Clear E-Stop. A ED4 dá ACK mesmo sem E-stop, então comparamos o
    light_engine_state (byte 3) da saudação com o da resposta."""
    code = resp[0:1]
    if code == b"a":
        if hello[3] != LE_ESTOP:
            return ClearReply(ClearOutcome.NOT_IN_ESTOP)
        return ClearReply(ClearOutcome.STILL_ESTOP if resp[3] == LE_ESTOP else ClearOutcome.CLEARED)
    naks = {b"!": ClearOutcome.NAK_ACTIVE, b"I": ClearOutcome.NAK_INVALID, b"F": ClearOutcome.NAK_FULL}
    return ClearReply(naks.get(code, ClearOutcome.UNKNOWN), code)


def version_unsupported(resp: bytes) -> bool:
    """Firmware antigo responde NAK ao comando 'v'."""
    return resp[0:1] in (b"I", b"!", b"F") and resp[1:2] == b"v"


def decode_version(raw: bytes) -> str:
    return raw.replace(b"\0", b" ").decode("ascii", "replace").strip()
