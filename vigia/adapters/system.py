"""Relógio, execução em segundo plano, pastas do app e atalhos do sistema operacional."""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
import time
import webbrowser

log = logging.getLogger(__name__)


class SystemClock:
    def now(self) -> float:
        return time.time()


class ThreadExecutor:
    def submit(self, fn) -> None:
        threading.Thread(target=fn, daemon=True, name="comando-dac").start()


def app_dirs() -> tuple[str, str]:
    """(pasta de dados, pasta de logs) do usuário. Nada é gravado ao lado do executável."""
    home = os.path.expanduser("~")
    if sys.platform == "darwin":
        return (os.path.join(home, "Library", "Application Support", "Vigia"),
                os.path.join(home, "Library", "Logs", "Vigia"))
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or home
        local = os.environ.get("LOCALAPPDATA") or base
        return os.path.join(base, "Vigia"), os.path.join(local, "Vigia", "logs")
    config = os.environ.get("XDG_CONFIG_HOME") or os.path.join(home, ".config")
    state = os.environ.get("XDG_STATE_HOME") or os.path.join(home, ".local", "state")
    return os.path.join(config, "vigia"), os.path.join(state, "vigia")


def legacy_name_files() -> tuple[str, ...]:
    """Onde o Ether Dream Sitter (Feitiçaria Industrial) guardava os nomes, para importar."""
    if sys.platform == "darwin":
        return (os.path.expanduser("~/Library/Application Support/EtherDreamSitterFI/etherdream_nomes.json"),)
    return ()


class DesktopActions:
    def open_network_settings(self) -> bool:
        try:
            if sys.platform == "darwin":
                r = subprocess.run(["/usr/bin/open", "x-apple.systempreferences:com.apple.Network-Settings.extension"])
                if r.returncode:
                    subprocess.Popen(["/usr/bin/open", "/System/Library/PreferencePanes/Network.prefPane"])
            elif sys.platform == "win32":
                os.startfile("ncpa.cpl")  # type: ignore[attr-defined]
            else:
                for cmd in (["nm-connection-editor"], ["gnome-control-center", "network"]):
                    try:
                        subprocess.Popen(cmd)
                        break
                    except OSError:
                        continue
                else:
                    return False
            return True
        except OSError as e:
            log.warning("abrir ajustes de rede: %s", e)
            return False

    def open_url(self, url: str) -> bool:
        try:
            return webbrowser.open(url)
        except webbrowser.Error:
            return False


class NoActions:
    def open_network_settings(self) -> bool:
        return False

    def open_url(self, url: str) -> bool:
        return False
