"""Registro de ocorrências: o que aconteceu, quando, com qual DAC."""
from __future__ import annotations

from dataclasses import dataclass

from .health import Level, Message


@dataclass(frozen=True)
class Event:
    seq: int
    at: float
    kind: str            # encontrada · voltou · offline · estado · ip_mudou · comando · nome · esquecida · escuta
    mac: str | None
    message: Message
    level: Level = Level.OFF
    alert: bool = False  # pede atenção do operador (DAC caiu, entrou em E-stop)
