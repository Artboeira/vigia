"""Portas: o que os casos de uso precisam do mundo externo. Implementações ficam em adapters/."""
from __future__ import annotations

from typing import Callable, Protocol

from ..domain.dac import Control, FirmwareNote
from ..domain.network import Interface
from ..domain.protocol import ClearReply


class Clock(Protocol):
    def now(self) -> float: ...


class ControlError(Exception):
    """A porta de controle não atendeu: recusada, sem resposta ou falha."""
    def __init__(self, control: Control):
        super().__init__(control.value)
        self.control = control


class ControlChannel(Protocol):
    """Porta TCP 7765. ATENÇÃO: na ED4 uma conexão nova interrompe o stream em andamento."""
    def read_firmware(self, ip: str) -> str | FirmwareNote: ...
    def clear_estop(self, ip: str) -> ClearReply: ...


class Executor(Protocol):
    def submit(self, fn: Callable[[], None]) -> None: ...


class NameStoreError(Exception):
    pass


class NameStore(Protocol):
    def load(self) -> dict[str, str]: ...
    def save(self, names: dict[str, str]) -> None: ...   # levanta NameStoreError


class InterfaceSource(Protocol):
    def interfaces(self) -> dict[str, Interface]: ...


class SystemActions(Protocol):
    def open_network_settings(self) -> bool: ...
    def open_url(self, url: str) -> bool: ...
