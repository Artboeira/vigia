"""Caso de uso central: acompanhar as DACs da rede, ler firmware com segurança e executar comandos.

O estado vem só dos anúncios UDP (passivo). A única conexão automática é a leitura do firmware,
e só com a DAC comprovadamente parada: na ED4 qualquer conexão TCP nova interrompe o stream.
"""
from __future__ import annotations

import logging
import threading
from collections import deque
from dataclasses import dataclass
from enum import Enum

from ..domain.dac import Control, Dac, FirmwareNote, Timing
from ..domain.events import Event
from ..domain.health import Health, Level, Message, Reading, assess, readings
from ..domain.network import Interface, IpPlan, NetIssue, net_issue, resolve_via, suggest_dac_ip, suggest_pc_ip
from ..domain.protocol import BROADCAST_SIZE, PB_IDLE, Announcement, ClearOutcome, ClearReply
from .ports import Clock, ControlChannel, ControlError, Executor, NameStore

log = logging.getLogger(__name__)

NAME_MAX = 24
DEFAULT_PLAN = IpPlan("192.168.0.50", "255.255.255.0", "192.168.0.1")


class CommandResult(str, Enum):
    STARTED = "iniciado"
    NEEDS_CONFIRMATION = "confirmar"
    BUSY = "ocupada"
    NOT_FOUND = "nao_encontrada"


@dataclass(frozen=True)
class IpGuide:
    pc_ip: str | None        # placa do PC usada como referência
    pc_label: str
    dac_plan: IpPlan         # valores para o ip.txt da ED4
    pc_plan: IpPlan | None   # IP fixo sugerido para o PC na faixa da DAC


@dataclass(frozen=True)
class DacSnapshot:
    mac: str
    name: str | None
    label: str
    ip: str
    online: bool
    busy: bool
    health: Health
    readings: list[tuple[str, list[Reading]]]
    banner: Message | None
    guide: IpGuide
    dropouts: int
    first_seen: float
    state_since: float
    rates: tuple[tuple[float, int], ...]


@dataclass(frozen=True)
class FleetSnapshot:
    at: float
    dacs: list[DacSnapshot]
    interfaces: list[Interface]
    events: list[Event]
    listening: bool | None
    guide: IpGuide


class Monitor:
    def __init__(self, clock: Clock, control: ControlChannel, names: NameStore, executor: Executor,
                 timing: Timing = Timing(), event_limit: int = 500):
        self._clock, self._control, self._store, self._executor = clock, control, names, executor
        self.timing = timing
        self._lock = threading.RLock()
        self._dacs: dict[str, Dac] = {}
        self._order: list[str] = []
        self._interfaces: dict[str, Interface] = {}
        self._names = names.load()
        self._events: deque[Event] = deque(maxlen=event_limit)
        self._seq = 0
        self._listening: bool | None = None

    # --- entrada --------------------------------------------------------------
    def set_interfaces(self, interfaces: dict[str, Interface]):
        with self._lock:
            self._interfaces = dict(interfaces)

    def set_listening(self, ok: bool):
        with self._lock:
            if ok != self._listening:
                self._emit("escuta", None, Message("escutando" if ok else "porta_indisponivel"),
                           Level.OK if ok else Level.WARN, alert=not ok)
            self._listening = ok

    def receive(self, data: bytes, ip: str, via_ip: str | None = None, device: str | None = None):
        """Anúncio UDP vindo de qualquer placa. Ignora o que não for Ether Dream."""
        if len(data) != BROADCAST_SIZE:
            return
        now = self._clock.now()
        with self._lock:
            ann = Announcement.parse(data, ip, now)
            via = resolve_via(ip, self._interfaces, device, via_ip)
            dac = self._dacs.get(ann.mac)
            if dac is None:
                dac = self._dacs[ann.mac] = Dac(ann, via, now, self.timing)
                self._order.append(ann.mac)
                self._emit("encontrada", ann.mac, Message("ev_encontrada", (self._label(ann.mac), ip)), Level.OK)
                return
            old_ip = dac.ann.ip
            if dac.absorb(ann, via, self.timing):
                self._emit("voltou", ann.mac, Message("ev_voltou", (self._label(ann.mac), ip)), Level.OK)
            if old_ip != ip:
                self._emit("ip_mudou", ann.mac, Message("ev_ip_mudou", (self._label(ann.mac), old_ip, ip)), Level.WARN)

    def tick(self):
        """2x por segundo: rede, transições de estado e a leitura de firmware (quando segura)."""
        now = self._clock.now()
        with self._lock:
            dacs = list(self._dacs.values())
            for dac in dacs:
                others = [o.ann.ip for o in dacs if o is not dac and o.online(now, self.timing)]
                dac.net_issue = net_issue(dac.ann.ip, dac.via, self._interfaces, others)
                dac.sample_rate(now, self.timing)
                self._track_state(dac, assess(dac, now, self.timing), now)
            for dac in dacs:
                if self._firmware_due(dac, now):
                    dac.next_firmware_try = now + self.timing.firmware_retry
                    if dac.ann.sw_rev < 2:
                        dac.firmware_note = FirmwareNote.OLD
                    else:
                        self._run(dac, self._control.read_firmware, self._got_firmware)

    def _firmware_due(self, dac: Dac, now: float) -> bool:
        return not (dac.firmware_known or dac.busy or now < dac.next_firmware_try or dac.net_issue
                    or dac.age(now) > self.timing.firmware_fresh
                    or dac.idle_streak < self.timing.firmware_idle_streak)

    def _got_firmware(self, dac: Dac, result, control: Control):
        if isinstance(result, FirmwareNote):
            dac.firmware_note = result
        elif result:
            dac.firmware = result

    def _track_state(self, dac: Dac, health: Health, now: float):
        old = dac.state
        if health.state == old:
            return
        dac.state, dac.state_since = health.state, now
        if old is None:
            return
        label = self._label(dac.mac)
        if health.state == "offline":
            dac.dropouts += 1
            self._emit("offline", dac.mac, Message("ev_offline", (label,)), Level.OFF, alert=True)
        elif old != "offline":  # a volta já é registrada por receive()
            self._emit("estado", dac.mac, Message("ev_estado", (label, old, health.state)), health.level,
                       alert=health.level == Level.ERROR)

    # --- comandos -------------------------------------------------------------
    def clear_estop(self, mac: str, confirmed: bool = False) -> CommandResult:
        with self._lock:
            dac = self._dacs.get(mac)
            if dac is None:
                return CommandResult.NOT_FOUND
            if dac.busy:
                return CommandResult.BUSY
            now = self._clock.now()
            risky = dac.age(now) > self.timing.confirm_stale or dac.ann.status.playback != PB_IDLE
            if risky and not confirmed:
                return CommandResult.NEEDS_CONFIRMATION
            self._emit("comando", mac, Message("ev_enviando_clear", (self._label(mac), dac.ann.ip)), Level.OFF)
            self._run(dac, self._control.clear_estop, self._cleared)
            return CommandResult.STARTED

    def _cleared(self, dac: Dac, reply: ClearReply | None, control: Control):
        label = self._label(dac.mac)
        if reply is None:
            self._emit("comando", dac.mac, Message("ev_clear_falhou", (label, control.value)), Level.WARN)
            return
        good = reply.outcome in (ClearOutcome.CLEARED, ClearOutcome.NOT_IN_ESTOP)
        args = (label, reply.code.hex()) if reply.outcome == ClearOutcome.UNKNOWN else (label,)
        self._emit("comando", dac.mac, Message("clear_" + reply.outcome.value, args),
                   Level.OK if good else Level.WARN)

    def rename(self, mac: str, name: str) -> bool:
        """Nome dado pelo operador, guardado no computador (não na DAC). Vazio = volta ao padrão."""
        name = " ".join(str(name).split())[:NAME_MAX]
        with self._lock:
            if mac not in self._dacs:
                return False
            old = self._label(mac)
            names = dict(self._names)
            if name:
                names[mac] = name
            else:
                names.pop(mac, None)
            if names == self._names:
                return True
            self._store.save(names)  # NameStoreError sobe para a interface
            self._names = names
            self._emit("nome", mac, Message("ev_nome", (old, self._label(mac))), Level.OFF)
            return True

    def forget(self, mac: str) -> bool:
        """Tira da lista uma DAC offline (o nome fica guardado para quando ela voltar)."""
        with self._lock:
            dac = self._dacs.get(mac)
            if dac is None or dac.online(self._clock.now(), self.timing) or dac.busy:
                return False
            del self._dacs[mac]
            self._order.remove(mac)
            self._emit("esquecida", mac, Message("ev_esquecida", (self._label(mac),)), Level.OFF)
            return True

    # --- execução em segundo plano --------------------------------------------
    def _run(self, dac: Dac, call, on_result):
        dac.busy = True
        ip = dac.ann.ip

        def work():
            result, control = None, Control.FAILED
            try:
                result, control = call(ip), Control.FREE
            except ControlError as e:
                control = e.control
            except Exception:
                log.exception("comando TCP para %s", ip)
            with self._lock:
                dac.busy = False
                dac.control, dac.control_at = control, self._clock.now()
                on_result(dac, result, control)
        self._executor.submit(work)

    # --- saída ----------------------------------------------------------------
    def snapshot(self, event_limit: int = 200) -> FleetSnapshot:
        now = self._clock.now()
        with self._lock:
            used = {d.ann.ip for d in self._dacs.values()}
            dacs = [self._dac_snapshot(self._dacs[m], now, used) for m in self._order]
            events = list(self._events)[-event_limit:]
            return FleetSnapshot(now, dacs, list(self._interfaces.values()), events, self._listening,
                                 self._guide(None, used))

    def _dac_snapshot(self, dac: Dac, now: float, used: set[str]) -> DacSnapshot:
        health = assess(dac, now, self.timing)
        online = health.state != "offline"
        banner = None
        if online and dac.net_issue == NetIssue.WRONG_SUBNET:
            iface = self._interfaces[dac.via]
            banner = Message("banner_faixa", (dac.ann.ip, iface.label, str(iface.network)))
        elif online and dac.net_issue == NetIssue.DUPLICATE_IP:
            banner = Message("banner_duplicado", (dac.ann.ip,))
        return DacSnapshot(
            mac=dac.mac, name=self._names.get(dac.mac), label=self._label(dac.mac), ip=dac.ann.ip,
            online=online, busy=dac.busy, health=health, readings=readings(dac, now, self._interfaces, self.timing),
            banner=banner, guide=self._guide(dac, used), dropouts=dac.dropouts, first_seen=dac.first_seen,
            state_since=dac.state_since, rates=tuple(dac.rates))

    def _guide(self, dac: Dac | None, used: set[str]) -> IpGuide:
        pcs = [ip for ip in self._interfaces if not ip.startswith(("127.", "0."))]
        pc = dac.via if dac and dac.via in self._interfaces else (pcs[0] if pcs else None)
        iface = self._interfaces.get(pc) if pc else None
        plan = suggest_dac_ip(pc, iface.mask, used) if iface else None
        pc_plan = suggest_pc_ip(dac.ann.ip, used | set(self._interfaces)) if dac else None
        return IpGuide(pc, iface.label if iface else "", plan or DEFAULT_PLAN, pc_plan)

    def _label(self, mac: str) -> str:
        return self._names.get(mac) or mac[6:].upper()

    def _emit(self, kind: str, mac: str | None, message: Message, level: Level, alert: bool = False):
        self._seq += 1
        self._events.append(Event(self._seq, self._clock.now(), kind, mac, message, level, alert))
