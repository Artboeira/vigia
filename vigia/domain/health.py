"""Leitura do estado de cada DAC. Devolve códigos (não textos): a interface traduz."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from . import protocol as p
from .dac import Control, Dac, FirmwareNote, Timing, mac_text
from .firmware import update_available
from .network import Interface, NetIssue


class Level(str, Enum):
    OK = "ok"          # pronta
    ACTIVE = "ativo"   # tocando ou preparada (LED branco na ED4)
    WARN = "alerta"
    ERROR = "erro"
    OFF = "off"        # sem dado / offline / informativo


@dataclass(frozen=True)
class Message:
    """Texto a traduzir: código do dicionário + argumentos. code 'raw' = dado literal."""
    code: str
    args: tuple = ()


def raw(text) -> Message:
    return Message("raw", (str(text),))


@dataclass(frozen=True)
class Health:
    level: Level
    state: str        # operacional · tocando · preparada · estop · faixa · duplicado · ocupada · sem_controle · offline
    reason: Message


@dataclass(frozen=True)
class Reading:
    key: str
    level: Level
    value: Message
    meter: float | None = None   # 0–1: a interface desenha uma barra


# ordem em que as causas de E-stop aparecem (a atual antes da travada)
ESTOP_CAUSES = ((p.LEF_INTERLOCK_OPEN, "interlock_aberto"), (p.LEF_OVER_TEMP, "temperatura_alta"),
                (p.LEF_INTERLOCK_TRIPPED, "disparado_interlock"), (p.LEF_TEMP_TRIPPED, "disparado_temperatura"),
                (p.LEF_LINK_LOST, "link_caiu"), (p.LEF_NETWORK_CMD, "comando_rede"))

CONTROL_LEVEL = {Control.FREE: Level.OK, Control.REFUSED: Level.WARN, Control.NO_ANSWER: Level.WARN,
                 Control.FAILED: Level.WARN}


def assess(dac: Dac, now: float, timing: Timing = Timing()) -> Health:
    age = dac.age(now)
    if age > timing.offline_after:
        return Health(Level.OFF, "offline", Message("sem_sinal", (int(age),)))
    st = dac.ann.status
    if st.estop and not st.network_flag_only:
        causes = tuple(code for bit, code in ESTOP_CAUSES if st.le_flag(bit))
        return Health(Level.ERROR, "estop", Message("laser_bloqueado", causes))
    if st.network_flag_only and st.playback != p.PB_PLAYING:
        return Health(Level.WARN, "estop", Message("estop_software"))
    if dac.net_issue == NetIssue.WRONG_SUBNET:
        return Health(Level.WARN, "faixa", Message("faixa_errada"))
    if dac.net_issue == NetIssue.DUPLICATE_IP:
        return Health(Level.WARN, "duplicado", Message("ip_duplicado"))
    if st.playback == p.PB_IDLE and now - dac.control_at < timing.control_ttl:
        if dac.control == Control.REFUSED:
            return Health(Level.WARN, "ocupada", Message("outro_software"))
        if dac.control == Control.NO_ANSWER:
            return Health(Level.WARN, "sem_controle", Message("tcp_sem_resposta", (p.CONTROL_PORT,)))
    if st.playback == p.PB_PLAYING:
        return Health(Level.ACTIVE, "tocando", Message("transmitindo", (st.point_rate,)))
    if st.playback == p.PB_PREPARED:
        return Health(Level.ACTIVE, "preparada", Message("conectado_sem_stream"))
    return Health(Level.OK, "operacional", Message("pronta"))


def readings(dac: Dac, now: float, interfaces: dict[str, Interface],
             timing: Timing = Timing()) -> list[tuple[str, list[Reading]]]:
    """Parâmetros da DAC em quatro grupos: rede, laser, saída, dispositivo."""
    return [("rede", _network(dac, now, interfaces, timing)), ("laser", _laser(dac)),
            ("saida", _output(dac)), ("dispositivo", _device(dac))]


def _network(dac, now, interfaces, timing):
    ann, age = dac.ann, dac.age(now)
    iface = interfaces.get(dac.via)
    if iface:
        place = Reading("placa_pc", Level.OK, raw("%s · %s" % (iface.label, dac.via) if iface.label != dac.via
                                                 else dac.via))
        net = str(iface.network)
        rng = (Reading("faixa", Level.WARN, Message("fora_faixa", (net,))) if dac.net_issue == NetIssue.WRONG_SUBNET
               else Reading("faixa", Level.OK, Message("na_faixa", (net,))))
    else:
        place, rng = Reading("placa_pc", Level.OFF, raw("—")), Reading("faixa", Level.OFF, raw("—"))

    q = dac.signal_quality(now, timing)
    if q is None:
        signal = Reading("sinal", Level.OFF, Message("medindo"))
    else:
        frac, window = q
        lvl = Level.OK if frac >= 0.9 else Level.WARN if frac >= 0.6 else Level.ERROR
        signal = Reading("sinal", lvl, Message("sinal_pct", (round(frac * 100), round(window))), frac)

    fresh = now - dac.control_at < timing.control_ttl
    return [
        Reading("ip", Level.WARN if dac.net_issue == NetIssue.DUPLICATE_IP else Level.OK, raw(ann.ip)),
        Reading("ultimo_sinal", Level.OK if age < 2.5 else Level.WARN if age <= timing.offline_after else Level.ERROR,
                Message("segundos", (round(age, 1),))),
        signal,
        place,
        rng,
        Reading("conexao_tcp", CONTROL_LEVEL.get(dac.control, Level.OFF) if fresh else Level.OFF,
                Message(dac.control.value)),
    ]


def _laser(dac):
    st = dac.ann.status
    if st.network_flag_only:
        laser = (Reading("laser", Level.OK, Message("liberado_flag")) if st.playback == p.PB_PLAYING
                 else Reading("laser", Level.WARN, Message("estop_software_curto")))
    else:
        laser = (Reading("laser", Level.ERROR, Message("estop")) if st.estop
                 else Reading("laser", Level.OK, Message("liberado")))
    if st.le_flag(p.LEF_INTERLOCK_OPEN):
        interlock = Reading("interlock", Level.ERROR, Message("aberto"))
    elif st.le_flag(p.LEF_INTERLOCK_TRIPPED):
        interlock = Reading("interlock", Level.WARN, Message("disparou_fechado"))
    else:
        interlock = Reading("interlock", Level.OK, Message("fechado"))
    if st.le_flag(p.LEF_OVER_TEMP):
        temp = Reading("temperatura", Level.ERROR, Message("alta"))
    elif st.le_flag(p.LEF_TEMP_TRIPPED):
        temp = Reading("temperatura", Level.WARN, Message("disparou_normal"))
    else:
        temp = Reading("temperatura", Level.OK, Message("normal"))
    link = (Reading("link_ethernet", Level.WARN, Message("caiu_stream")) if st.le_flag(p.LEF_LINK_LOST)
            else Reading("link_ethernet", Level.OK, Message("ok")))
    return [laser, interlock, temp, link]


def _output(dac):
    ann, st = dac.ann, dac.ann.status
    if st.playback == p.PB_PLAYING:
        out = Reading("saida", Level.ACTIVE, Message("tocando_pps", (st.point_rate,)))
    elif st.playback == p.PB_PREPARED:
        out = Reading("saida", Level.ACTIVE, Message("preparada"))
    else:
        out = Reading("saida", Level.OFF, Message("ociosa"))
    cap = max(ann.buffer_capacity, 1)
    buffer = Reading("buffer", Level.OFF, Message("buffer", (st.fullness, ann.buffer_capacity, 100 * st.fullness // cap)),
                     min(1.0, st.fullness / cap))
    if st.pb_flag(p.PBF_ESTOP):
        last = Reading("ultimo_stream", Level.WARN, Message("parou_estop"))
    elif st.pb_flag(p.PBF_UNDERFLOW):
        last = Reading("ultimo_stream", Level.OFF, Message("underflow"))
    else:
        last = Reading("ultimo_stream", Level.OFF, Message("normal"))
    source = (Message("fonte_" + p.SOURCES[st.source]) if st.source in p.SOURCES
              else Message("fonte_n", (st.source,)))
    return [out, buffer, last, Reading("fonte", Level.OFF, source),
            Reading("taxa_maxima", Level.OFF, Message("pps", (ann.max_point_rate,)))]


def _device(dac):
    ann, st = dac.ann, dac.ann.status
    if dac.firmware:
        fw = Reading("firmware", Level.OK, raw(dac.firmware))
    elif dac.firmware_note:
        fw = Reading("firmware", Level.OFF, Message("fw_" + dac.firmware_note.value))
    elif dac.control not in (Control.UNTESTED, Control.FREE):
        fw = Reading("firmware", Level.OFF, Message("nao_lido", (dac.control.value,)))
    elif dac.net_issue:
        fw = Reading("firmware", Level.OFF, raw("—"))
    elif st.playback != p.PB_IDLE:
        fw = Reading("firmware", Level.OFF, Message("aguardando_parada"))
    else:
        fw = Reading("firmware", Level.OFF, Message("consultando"))

    newer = update_available(dac.firmware or "")
    if newer:
        upd = Reading("atualizacao", Level.WARN, Message("disponivel", (newer,)))
    elif dac.firmware:
        upd = Reading("atualizacao", Level.OK, Message("em_dia"))
    elif dac.firmware_note == FirmwareNote.OLD:
        upd = Reading("atualizacao", Level.WARN, Message("provavel_desatualizado"))
    else:
        upd = Reading("atualizacao", Level.OFF, raw("—"))
    return [fw, upd, Reading("hardware", Level.OFF, Message("hw_sw", (ann.hw_rev, ann.sw_rev))),
            Reading("mac", Level.OFF, raw(mac_text(ann.mac)))]
