"""Converte o retrato da frota em JSON para a interface. Textos continuam como códigos + argumentos."""
from __future__ import annotations

from ..application.monitor import DacSnapshot, FleetSnapshot, IpGuide
from ..domain.dac import mac_text
from ..domain.health import Message


def message(m: Message | None):
    return None if m is None else {"c": m.code, "a": list(m.args)}


def guide_json(g: IpGuide) -> dict:
    return {
        "pc_ip": g.pc_ip, "pc_placa": g.pc_label,
        "dac": {"ip": g.dac_plan.ip, "mascara": g.dac_plan.mask, "gateway": g.dac_plan.gateway},
        "pc": {"ip": g.pc_plan.ip, "mascara": g.pc_plan.mask} if g.pc_plan else None,
    }


def dac_json(d: DacSnapshot) -> dict:
    return {
        "mac": d.mac, "mac_texto": mac_text(d.mac).upper(), "nome": d.name, "rotulo": d.label, "ip": d.ip,
        "online": d.online, "ocupada": d.busy,
        "nivel": d.health.level.value, "estado": d.health.state, "motivo": message(d.health.reason),
        "grupos": [{"id": gid, "itens": [{"k": r.key, "nivel": r.level.value, "v": message(r.value), "barra": r.meter}
                                         for r in items]} for gid, items in d.readings],
        "aviso": message(d.banner), "guia": guide_json(d.guide), "quedas": d.dropouts,
        "visto_desde": d.first_seen, "estado_desde": d.state_since,
        "taxa": [[round(t, 1), pps] for t, pps in d.rates],
    }


def snapshot_json(s: FleetSnapshot) -> dict:
    return {
        "agora": s.at,
        "escutando": s.listening,
        "placas": [{"ip": i.ip, "mascara": i.mask, "nome": i.label, "rede": str(i.network)} for i in s.interfaces],
        "guia": guide_json(s.guide),
        "dacs": [dac_json(d) for d in s.dacs],
        "eventos": [{"seq": e.seq, "em": e.at, "tipo": e.kind, "mac": e.mac, "msg": message(e.message),
                     "nivel": e.level.value, "alerta": e.alert} for e in s.events],
    }

