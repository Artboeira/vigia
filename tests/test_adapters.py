"""Adaptadores sem rede: parsers de placas, arquivo de nomes, regras de acesso e rotas da API."""
import json
import os
import tempfile
import unittest

from tests.fakes import FakeClock, FakeControl, SyncExecutor, packet
from vigia.adapters.interfaces import parse_ifconfig, parse_ip_addr
from vigia.adapters.name_store import JsonNameStore, MemoryNameStore
from vigia.application.monitor import Monitor
from vigia.domain.network import Interface
from vigia.infra.web.api import Api, is_local_host, may_command

IFC = """lo0: flags=8049<UP,LOOPBACK,RUNNING,MULTICAST> mtu 16384
\tinet 127.0.0.1 netmask 0xff000000
en0: flags=8863<UP,BROADCAST,SMART,RUNNING,SIMPLEX,MULTICAST> mtu 1500
\tether 3c:22:fb:00:00:01
\tinet 192.168.0.20 netmask 0xffffff00 broadcast 192.168.0.255
en7: flags=8863<UP,BROADCAST,SMART,RUNNING,SIMPLEX,MULTICAST> mtu 1500
\tinet 169.254.33.7 netmask 0xffff0000 broadcast 169.254.255.255
"""
PORTS = "Hardware Port: Wi-Fi\nDevice: en0\nEthernet Address: 3c:22:fb:00:00:01\n"
IP_ADDR = """1: lo    inet 127.0.0.1/8 scope host lo\\       valid_lft forever preferred_lft forever
2: eth0    inet 192.168.0.5/24 brd 192.168.0.255 scope global dynamic eth0\\       valid_lft 86000sec
3: wlan0    inet 10.1.2.3/16 brd 10.1.255.255 scope global wlan0\\       valid_lft forever
"""


class Interfaces(unittest.TestCase):
    def test_mac(self):
        self.assertEqual(parse_ifconfig(IFC, PORTS), {
            "192.168.0.20": Interface("192.168.0.20", "255.255.255.0", "Wi-Fi", "en0"),
            "169.254.33.7": Interface("169.254.33.7", "255.255.0.0", "", "en7")})

    def test_linux(self):
        self.assertEqual(parse_ip_addr(IP_ADDR), {
            "192.168.0.5": Interface("192.168.0.5", "255.255.255.0", "", "eth0"),
            "10.1.2.3": Interface("10.1.2.3", "255.255.0.0", "", "wlan0")})


class Names(unittest.TestCase):
    def test_save_and_reload(self):
        folder = tempfile.mkdtemp()
        store = JsonNameStore(os.path.join(folder, "sub", "nomes.json"))
        self.assertEqual(store.load(), {})
        store.save({"8a9e36988cce": "PALCO ESQ"})
        self.assertEqual(store.load(), {"8a9e36988cce": "PALCO ESQ"})

    def test_imports_legacy_sitter_file(self):
        folder = tempfile.mkdtemp()
        legacy = os.path.join(folder, "etherdream_nomes.json")
        with open(legacy, "w", encoding="utf-8") as fh:
            json.dump({"8a9e36988cce": "TORRE"}, fh)
        store = JsonNameStore(os.path.join(folder, "nomes.json"), (legacy,))
        self.assertEqual(store.load(), {"8a9e36988cce": "TORRE"})


class Access(unittest.TestCase):
    def test_rules(self):
        self.assertTrue(is_local_host("127.0.0.1:7680", 7680))
        self.assertTrue(is_local_host("localhost:7680", 7680))
        self.assertFalse(is_local_host("evil.example:7680", 7680))   # DNS rebinding
        self.assertTrue(may_command("127.0.0.1", "127.0.0.1:7680", "tok", "tok", 7680))
        self.assertFalse(may_command("127.0.0.1", "127.0.0.1:7680", "x", "tok", 7680))    # sem token
        self.assertFalse(may_command("192.168.0.9", "127.0.0.1:7680", "tok", "tok", 7680))  # outro aparelho
        self.assertFalse(may_command("127.0.0.1", "evil.example:7680", "tok", "tok", 7680))


class Routes(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.monitor = Monitor(self.clock, FakeControl(), MemoryNameStore(), SyncExecutor())
        self.monitor.set_interfaces({"192.168.0.10": Interface("192.168.0.10", "255.255.255.0", "Ethernet", "en7")})
        self.monitor.receive(packet(), "192.168.0.80", device="en7")
        self.opened = []
        actions = type("A", (), {"open_network_settings": lambda s: True,
                                 "open_url": lambda s, url: self.opened.append(url) or True})()
        self.api = Api(self.monitor, actions, {"versao": "t", "porta": 7680})

    def test_rename(self):
        r = self.api.post("/api/dacs/8a9e36988cce/nome", b'{"nome": "PALCO"}')
        self.assertEqual((r.status, r.payload), (200, {"ok": True}))
        self.assertEqual(self.api.state(False)["dacs"][0]["rotulo"], "PALCO")

    def test_clear_and_errors(self):
        self.assertEqual(self.api.post("/api/dacs/8a9e36988cce/limpar-estop", b"{}").payload["resultado"], "iniciado")
        self.assertEqual(self.api.post("/api/dacs/8a9e36988cce/limpar-estop", b"[").status, 400)
        self.assertEqual(self.api.post("/api/dacs/../etc", b"{}").status, 404)
        self.assertEqual(self.api.post("/api/dacs/8a9e36988cce/esquecer", b"{}").status, 409)

    def test_labels_url_only_takes_macs(self):
        self.api.post("/api/sistema/abrir-etiquetas", b'{"macs": ["8a9e36988cce", "x&evil=1"]}')
        self.assertEqual(self.opened, ["http://127.0.0.1:7680/etiquetas.html?macs=8a9e36988cce"])

    def test_state_flags_read_only(self):
        self.assertTrue(self.api.state(True)["app"]["somente_leitura"])


if __name__ == "__main__":
    unittest.main()
