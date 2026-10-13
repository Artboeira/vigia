"""Frota simulada para demonstração e desenvolvimento sem DACs: `python -m vigia --demo`.

Seis cenários reais de montagem: uma tocando pelo MadMapper (flag de rede), uma parada com
firmware antigo, uma em E-stop por interlock, uma em faixa errada, uma em Wi-Fi ruim que cai
de vez em quando e uma que aparece com IP duplicado.
"""
from __future__ import annotations

import math
import random
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

from ..application.ports import ControlError
from ..domain.dac import Control, FirmwareNote
from ..domain.network import Interface
from ..domain.protocol import (LE_ESTOP, LE_READY, LEF_INTERLOCK_OPEN, LEF_INTERLOCK_TRIPPED, LEF_NETWORK_CMD,
                               PB_IDLE, PB_PLAYING, ClearOutcome, ClearReply, DacStatus, build_announcement)

DEMO_INTERFACES = {
    "192.168.0.10": Interface("192.168.0.10", "255.255.255.0", "Ethernet", "en7"),
    "192.168.1.20": Interface("192.168.1.20", "255.255.255.0", "Wi-Fi", "en0"),
}

DEMO_NAMES = {"8a9e36988c01": "PALCO ESQ", "8a9e36988c02": "PALCO DIR", "8a9e36988c04": "TORRE",
              "8a9e36988c05": "FUNDO"}


@dataclass
class SimDac:
    mac: str
    ip: str
    device: str
    firmware: str | FirmwareNote
    status: Callable[[float, "SimDac"], DacStatus]
    loss: float = 0.0                          # fração de anúncios perdidos
    present: Callable[[float], bool] = lambda t: True
    reachable: bool = True
    cleared: bool = False
    extra: dict = field(default_factory=dict)


def _playing_madmapper(t, d):
    fullness = int(2600 + 900 * math.sin(t / 3))
    return DacStatus(light_engine=LE_ESTOP, le_flags=1 << LEF_NETWORK_CMD, playback=PB_PLAYING,
                     fullness=fullness, point_rate=30000 + int(2000 * math.sin(t / 11)))


def _idle(t, d):
    return DacStatus()


def _interlock(t, d):
    if d.cleared:
        return DacStatus()
    if t < 25:  # interlock aberto nos primeiros 25 s, depois fica só o registro de que disparou
        return DacStatus(light_engine=LE_ESTOP, le_flags=1 << LEF_INTERLOCK_OPEN | 1 << LEF_INTERLOCK_TRIPPED)
    return DacStatus(light_engine=LE_ESTOP, le_flags=1 << LEF_INTERLOCK_TRIPPED)


def _wifi(t, d):
    playing = int(t) % 40 < 25
    return DacStatus(light_engine=LE_READY, playback=PB_PLAYING if playing else PB_IDLE,
                     fullness=1700 if playing else 0, point_rate=20000 if playing else 0)


def demo_fleet() -> list[SimDac]:
    return [
        SimDac("8a9e36988c01", "192.168.0.80", "en7", "ed4-354-0d43ec7", _playing_madmapper),
        SimDac("8a9e36988c02", "192.168.0.81", "en7", "ed4-152-33b3cef", _idle),
        SimDac("8a9e36988c03", "192.168.0.82", "en7", "ed4-354-0d43ec7", _interlock),
        SimDac("8a9e36988c04", "10.0.0.5", "en7", "ed4-354-0d43ec7", _idle, reachable=False),
        SimDac("8a9e36988c05", "192.168.1.90", "en0", "ed3v80-1a2b3c", _wifi, loss=0.22,
               present=lambda t: int(t) % 75 < 63),
        SimDac("8a9e36988c06", "192.168.0.81", "en7", "ed4-354-0d43ec7", _idle, present=lambda t: 45 < t < 110),
    ]


class DemoFleet:
    """Envia anúncios simulados direto para o Monitor, 1x por segundo por DAC (com jitter)."""

    def __init__(self, receive, dacs: list[SimDac] | None = None, seed: int = 7):
        self.receive = receive
        self.dacs = dacs or demo_fleet()
        self.start_time = time.time()
        self._rng = random.Random(seed)

    def elapsed(self) -> float:
        return time.time() - self.start_time

    def start(self):
        threading.Thread(target=self._loop, daemon=True, name="demo").start()

    def _loop(self):
        while True:
            t = self.elapsed()
            for d in self.dacs:
                if not d.present(t) or self._rng.random() < d.loss:
                    continue
                data = build_announcement(d.mac, 30, 3, 3839, 100000, d.status(t, d))
                self.receive(data, d.ip, None, d.device)
            time.sleep(1.0 + self._rng.uniform(-0.05, 0.05))

    def find(self, ip: str) -> SimDac | None:
        t = self.elapsed()
        return next((d for d in self.dacs if d.ip == ip and d.present(t)), None)


class DemoControl:
    """Porta de controle simulada, ligada à frota simulada."""

    def __init__(self, fleet: DemoFleet):
        self.fleet = fleet

    def _dac(self, ip: str) -> SimDac:
        time.sleep(0.25)
        d = self.fleet.find(ip)
        if d is None or not d.reachable:
            raise ControlError(Control.NO_ANSWER)
        return d

    def read_firmware(self, ip: str):
        return self._dac(ip).firmware

    def clear_estop(self, ip: str) -> ClearReply:
        d = self._dac(ip)
        st = d.status(self.fleet.elapsed(), d)
        if st.light_engine != LE_ESTOP or st.le_flags == 1 << LEF_NETWORK_CMD:
            return ClearReply(ClearOutcome.NOT_IN_ESTOP)
        if st.le_flag(LEF_INTERLOCK_OPEN):
            return ClearReply(ClearOutcome.NAK_ACTIVE, b"!")
        d.cleared = True
        return ClearReply(ClearOutcome.CLEARED)


class StaticInterfaces:
    def __init__(self, interfaces: dict[str, Interface]):
        self._interfaces = interfaces

    def interfaces(self) -> dict[str, Interface]:
        return dict(self._interfaces)
