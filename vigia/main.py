"""Raiz de composição: liga domínio, casos de uso, adaptadores e interface."""
from __future__ import annotations

import argparse
import faulthandler
import logging
import os
import secrets
import sys
import threading
import webbrowser
from logging.handlers import RotatingFileHandler

from . import __version__
from .adapters.control_tcp import TcpControlChannel
from .adapters.interfaces import platform_interfaces
from .adapters.name_store import JsonNameStore, MemoryNameStore
from .adapters.simulator import DEMO_INTERFACES, DEMO_NAMES, DemoControl, DemoFleet, StaticInterfaces
from .adapters.system import DesktopActions, SystemClock, ThreadExecutor, app_dirs, legacy_name_files
from .adapters.udp_listener import UdpListener
from .application.monitor import Monitor
from .infra.runtime import Runtime
from .infra.web.api import Api
from .infra.web.server import start_server

log = logging.getLogger("vigia")
DEFAULT_PORT = 7680


def parse_args(argv):
    ap = argparse.ArgumentParser(prog="vigia", description="Monitor de DACs Ether Dream na rede local.")
    ap.add_argument("--demo", action="store_true", help="frota simulada, sem rede (demonstração)")
    ap.add_argument("--porta", type=int, default=DEFAULT_PORT, help="porta da interface (padrão %d)" % DEFAULT_PORT)
    ap.add_argument("--rede", action="store_true",
                    help="libera a interface para outros aparelhos da rede (somente leitura; comandos só daqui)")
    ap.add_argument("--navegador", action="store_true", help="abre no navegador mesmo com pywebview instalado")
    ap.add_argument("--sem-janela", action="store_true", help="só o servidor (máquina de show, acesso remoto)")
    return ap.parse_args(argv)


def setup_logging(log_dir: str):
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    try:
        os.makedirs(log_dir, exist_ok=True)
        handlers.append(RotatingFileHandler(os.path.join(log_dir, "vigia.log"), maxBytes=1_000_000, backupCount=2,
                                            encoding="utf-8"))
        faulthandler.enable(open(os.path.join(log_dir, "falha.log"), "a"))
    except OSError:
        pass
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        handlers=handlers)
    threading.excepthook = lambda a: log.error("thread %s", a.thread, exc_info=(a.exc_type, a.exc_value,
                                                                                a.exc_traceback))


def build(args) -> tuple[Monitor, Runtime, Api]:
    clock, executor = SystemClock(), ThreadExecutor()
    if args.demo:
        fleet = DemoFleet(receive=None)
        monitor = Monitor(clock, DemoControl(fleet), MemoryNameStore(DEMO_NAMES), executor)
        fleet.receive = monitor.receive
        runtime = Runtime(monitor, StaticInterfaces(DEMO_INTERFACES))
        monitor.set_interfaces(DEMO_INTERFACES)  # antes do primeiro anúncio
        monitor.set_listening(True)
        fleet.start()
    else:
        data_dir, _logs = app_dirs()
        names = JsonNameStore(os.path.join(data_dir, "nomes.json"), legacy_name_files())
        monitor = Monitor(clock, TcpControlChannel(), names, executor)
        runtime = Runtime(monitor, platform_interfaces(), UdpListener(monitor.receive))
    info = {"versao": __version__, "demo": bool(args.demo), "rede": bool(args.rede), "plataforma": sys.platform}
    return monitor, runtime, Api(monitor, DesktopActions(), info)


def open_window(url: str, args):
    if args.sem_janela:
        return threading.Event().wait()
    if not args.navegador:
        try:
            import webview  # opcional: pip install pywebview
        except ImportError:
            webview = None
        if webview is not None:
            try:
                webview.settings["ALLOW_DOWNLOADS"] = True
            except (AttributeError, TypeError):
                pass
            webview.create_window("Vigia", url, width=1400, height=900, min_size=(1080, 700),
                                  background_color="#222223")
            return webview.start()
    webbrowser.open(url)
    threading.Event().wait()


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)
    setup_logging(app_dirs()[1])
    monitor, runtime, api = build(args)
    runtime.start()
    token = secrets.token_urlsafe(24)
    server = start_server(api, token, "0.0.0.0" if args.rede else "127.0.0.1", args.porta, args.rede)
    api.info["porta"] = server.port
    threading.Thread(target=server.serve_forever, daemon=True, name="http").start()
    url = "http://127.0.0.1:%d/" % server.port
    log.info("Vigia %s em %s%s", __version__, url, " (demo)" if args.demo else "")
    if args.rede:
        log.info("acesso pela rede liberado na porta %d (somente leitura)", server.port)
    try:
        open_window(url, args)
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
