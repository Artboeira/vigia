"""Dublês das portas: relógio controlado, execução síncrona, porta de controle programável."""
from vigia.application.ports import ControlError
from vigia.domain.dac import Control
from vigia.domain.protocol import ClearOutcome, ClearReply, DacStatus, build_announcement


class FakeClock:
    def __init__(self, t=1000.0):
        self.t = t

    def now(self):
        return self.t

    def advance(self, dt):
        self.t += dt


class SyncExecutor:
    def submit(self, fn):
        fn()


class FakeControl:
    def __init__(self, firmware="ed4-354-0d43ec7", clear=ClearReply(ClearOutcome.CLEARED), error=None):
        self.firmware, self.clear, self.error = firmware, clear, error
        self.calls = []

    def read_firmware(self, ip):
        self.calls.append(("v", ip))
        if self.error:
            raise ControlError(self.error)
        return self.firmware

    def clear_estop(self, ip):
        self.calls.append(("c", ip))
        if self.error:
            raise ControlError(self.error)
        return self.clear


def packet(mac="8a9e36988cce", **status):
    return build_announcement(mac, 30, 3, 3839, 100000, DacStatus(**status))


__all__ = ["FakeClock", "SyncExecutor", "FakeControl", "packet", "Control"]
