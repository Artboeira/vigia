"""Rotas da API, sem servidor: recebem método, caminho e corpo; devolvem status e JSON.

Regras de acesso também ficam aqui, como funções puras, para poderem ser testadas sem rede.
"""
from __future__ import annotations

import hmac
import ipaddress
import json
import re
from dataclasses import dataclass

from ...adapters.presenter import snapshot_json
from ...application.monitor import CommandResult, Monitor
from ...application.ports import NameStoreError, SystemActions

DAC_ROUTE = re.compile(r"^/api/dacs/([0-9a-f]{12})/(nome|limpar-estop|esquecer)$")
MAC = re.compile(r"^[0-9a-f]{12}$")


@dataclass(frozen=True)
class Response:
    status: int
    payload: dict

    def body(self) -> bytes:
        return json.dumps(self.payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def is_loopback(client_ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(client_ip)
    except ValueError:
        return False
    return addr.is_loopback or (getattr(addr, "ipv4_mapped", None) is not None and addr.ipv4_mapped.is_loopback)


def is_local_host(host_header: str | None, port: int) -> bool:
    """Cabeçalho Host de quem abriu a interface pelo próprio computador. Barra DNS rebinding."""
    return (host_header or "").lower() in {"127.0.0.1:%d" % port, "localhost:%d" % port, "[::1]:%d" % port}


def may_command(client_ip: str, host_header: str | None, token_header: str | None, token: str, port: int) -> bool:
    """Comandos (Clear E-Stop, renomear...) só do próprio computador, com Host local e o token da sessão.
    O token impede que uma página qualquer aberta no navegador dispare comandos no localhost."""
    return (is_loopback(client_ip) and is_local_host(host_header, port)
            and hmac.compare_digest((token_header or "").encode(), token.encode()))


class Api:
    def __init__(self, monitor: Monitor, actions: SystemActions, info: dict):
        self.monitor, self.actions, self.info = monitor, actions, info

    def state(self, read_only: bool) -> dict:
        data = snapshot_json(self.monitor.snapshot())
        data["app"] = dict(self.info, somente_leitura=read_only)
        return data

    def post(self, path: str, body: bytes) -> Response:
        try:
            data = json.loads(body or b"{}")
            if not isinstance(data, dict):
                raise ValueError
        except ValueError:
            return Response(400, {"erro": "json_invalido"})

        if path == "/api/sistema/abrir-rede":
            return Response(200, {"ok": self.actions.open_network_settings()})
        if path == "/api/sistema/abrir-etiquetas":  # a janela nativa não imprime: a folha abre no navegador
            macs = [m for m in data.get("macs", []) if isinstance(m, str) and MAC.match(m)]
            url = "http://127.0.0.1:%s/etiquetas.html?macs=%s" % (self.info.get("porta"), ",".join(macs))
            return Response(200, {"ok": self.actions.open_url(url)})

        m = DAC_ROUTE.match(path)
        if not m:
            return Response(404, {"erro": "rota_desconhecida"})
        mac, action = m.groups()

        if action == "limpar-estop":
            result = self.monitor.clear_estop(mac, bool(data.get("confirmado")))
            status = 404 if result == CommandResult.NOT_FOUND else 200
            return Response(status, {"resultado": result.value})
        if action == "nome":
            try:
                ok = self.monitor.rename(mac, str(data.get("nome", "")))
            except NameStoreError as e:
                return Response(500, {"erro": "salvar_nomes", "detalhe": str(e)})
            return Response(200 if ok else 404, {"ok": ok})
        ok = self.monitor.forget(mac)
        return Response(200 if ok else 409, {"ok": ok})
