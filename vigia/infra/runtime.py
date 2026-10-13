"""Relógio do app: tick do Monitor 2x por segundo e releitura das placas de rede a cada 5 s."""
from __future__ import annotations

import logging
import threading
import time

from ..application.monitor import Monitor
from ..application.ports import InterfaceSource

log = logging.getLogger(__name__)


class Runtime:
    def __init__(self, monitor: Monitor, interfaces: InterfaceSource, listener=None,
                 tick: float = 0.5, network_every: int = 10):
        self.monitor, self.source, self.listener = monitor, interfaces, listener
        self.tick, self.network_every = tick, network_every

    def refresh_network(self):
        nets = self.source.interfaces()
        self.monitor.set_interfaces(nets)
        if self.listener is not None:
            self.monitor.set_listening(self.listener.sync(nets))

    def start(self):
        self.refresh_network()
        threading.Thread(target=self._loop, daemon=True, name="tick").start()

    def _loop(self):
        n = 0
        while True:
            time.sleep(self.tick)
            n += 1
            try:  # um erro aqui não pode parar o relógio
                self.monitor.tick()
                if n % self.network_every == 0:
                    self.refresh_network()
            except Exception:
                log.exception("tick")
