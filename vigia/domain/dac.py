"""Entidade DAC: o que sabemos de cada Ether Dream ao longo do tempo."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import Enum

from .network import NetIssue
from .protocol import PB_IDLE, PB_PLAYING, Announcement


class Control(str, Enum):
    """Resultado da última conexão TCP na porta de controle."""
    UNTESTED = "nao_testada"
    FREE = "livre"
    REFUSED = "recusada"
    NO_ANSWER = "sem_resposta"
    FAILED = "falha"


class FirmwareNote(str, Enum):
    OLD = "antigo"          # sw_rev < 2: sem consulta de versão
    NO_VERSION = "sem_v"    # firmware não conhece o comando 'v'


@dataclass(frozen=True)
class Timing:
    offline_after: float = 5.0       # sem anúncio por esse tempo = offline (a DAC anuncia 1x/s)
    firmware_retry: float = 5.0      # nova tentativa de ler o firmware
    control_ttl: float = 30.0        # resultado da última conexão TCP vale por esse tempo
    firmware_fresh: float = 1.5      # só conecta se o último anúncio for mais novo que isso
    firmware_idle_streak: int = 2    # ... e se a DAC estiver parada há esse número de anúncios
    confirm_stale: float = 2.0       # Clear E-Stop pede confirmação com anúncio mais velho que isso
    signal_window: float = 30.0      # janela da qualidade de sinal
    signal_min_window: float = 5.0
    announce_interval: float = 1.0
    rate_history: int = 120          # amostras de pps guardadas (1 por tick de 0,5 s = 60 s)


def mac_text(mac: str) -> str:
    return ":".join(mac[i:i + 2] for i in range(0, 12, 2))


class Dac:
    def __init__(self, ann: Announcement, via: str, now: float, timing: Timing = Timing()):
        self.ann = ann
        self.via = via
        self.first_seen = now
        self.firmware: str | None = None
        self.firmware_note: FirmwareNote | None = None
        self.control = Control.UNTESTED
        self.control_at = 0.0
        self.next_firmware_try = 0.0
        self.busy = False                     # há conexão TCP em andamento
        self.net_issue: NetIssue | None = None
        self.idle_streak = 0                  # anúncios seguidos com playback parado
        self.dropouts = 0                     # vezes que ficou offline desde que o Vigia abriu
        self.state: str | None = None         # último estado (para detectar transições)
        self.state_since = now
        self.arrivals: deque[float] = deque()
        self.rates: deque[tuple[float, int]] = deque(maxlen=timing.rate_history)
        self._track(ann)

    @property
    def mac(self) -> str:
        return self.ann.mac

    def age(self, now: float) -> float:
        return now - self.ann.received_at

    def online(self, now: float, timing: Timing) -> bool:
        return self.age(now) <= timing.offline_after

    @property
    def firmware_known(self) -> bool:
        return self.firmware is not None or self.firmware_note is not None

    def absorb(self, ann: Announcement, via: str, timing: Timing) -> bool:
        """Novo anúncio. True se a DAC voltou depois de ficar offline (pode ter trocado firmware ou IP)."""
        returned = ann.received_at - self.ann.received_at > timing.offline_after
        if returned:
            self.firmware = self.firmware_note = None
            self.control, self.next_firmware_try, self.idle_streak = Control.UNTESTED, 0.0, 0
        self.idle_streak = self.idle_streak + 1 if ann.status.playback == PB_IDLE else 0
        self.ann, self.via = ann, via
        self._track(ann)
        return returned

    def _track(self, ann: Announcement):
        self.arrivals.append(ann.received_at)

    def sample_rate(self, now: float, timing: Timing):
        st = self.ann.status
        playing = self.online(now, timing) and st.playback == PB_PLAYING
        self.rates.append((now, st.point_rate if playing else 0))

    def signal_quality(self, now: float, timing: Timing) -> tuple[float, float] | None:
        """(fração de anúncios recebidos, janela em s). None enquanto a janela é curta demais.
        Revela Wi-Fi ruim ou switch descartando broadcast antes da DAC cair."""
        window = min(timing.signal_window, now - self.first_seen)
        if window < timing.signal_min_window:
            return None
        while self.arrivals and self.arrivals[0] < now - window:
            self.arrivals.popleft()
        expected = window / timing.announce_interval
        return min(1.0, len(self.arrivals) / expected), window
