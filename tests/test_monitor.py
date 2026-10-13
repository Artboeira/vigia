"""Caso de uso Monitor com dublês: sem rede, sem threads, relógio controlado."""
import json
import unittest

from tests.fakes import FakeClock, FakeControl, SyncExecutor, packet
from vigia.adapters.name_store import MemoryNameStore
from vigia.adapters.presenter import snapshot_json
from vigia.application.monitor import CommandResult, Monitor
from vigia.domain.dac import Control
from vigia.domain.network import Interface
from vigia.domain.protocol import ClearOutcome, ClearReply

NETS = {"192.168.0.10": Interface("192.168.0.10", "255.255.255.0", "Ethernet", "en7")}


def setup(control=None, names=None):
    clock = FakeClock()
    control = control or FakeControl()
    store = MemoryNameStore(names)
    m = Monitor(clock, control, store, SyncExecutor())
    m.set_interfaces(NETS)
    return m, clock, control, store


def feed(m, clock, seconds, ip="192.168.0.80", mac="8a9e36988cce", **status):
    for _ in range(int(seconds * 2)):
        if clock.t % 1 == 0:
            m.receive(packet(mac, **status), ip, device="en7")
        m.tick()
        clock.advance(0.5)


def dac(m, mac="8a9e36988cce"):
    return next(d for d in m.snapshot().dacs if d.mac == mac)


class Firmware(unittest.TestCase):
    def test_reads_only_when_idle(self):
        m, clock, control, _ = setup()
        feed(m, clock, 5, playback=2, point_rate=30000)
        self.assertEqual(control.calls, [])                       # tocando: nunca conecta
        feed(m, clock, 3)
        self.assertEqual(control.calls, [("v", "192.168.0.80")])  # parada há 2 anúncios: lê uma vez
        feed(m, clock, 10)
        self.assertEqual(len(control.calls), 1)

    def test_never_reads_wrong_subnet(self):
        m, clock, control, _ = setup()
        feed(m, clock, 5, ip="10.0.0.5")
        self.assertEqual(control.calls, [])
        self.assertEqual(dac(m).health.state, "faixa")

    def test_refused_is_reported(self):
        m, clock, _c, _ = setup(FakeControl(error=Control.REFUSED))
        feed(m, clock, 4)
        self.assertEqual(dac(m).health.state, "ocupada")


class States(unittest.TestCase):
    def test_offline_and_back(self):
        m, clock, _c, _ = setup()
        feed(m, clock, 3)
        for _ in range(14):
            m.tick()
            clock.advance(0.5)
        self.assertEqual(dac(m).health.state, "offline")
        feed(m, clock, 2)
        kinds = [e.kind for e in m.snapshot().events]
        self.assertEqual(kinds, ["encontrada", "offline", "voltou"])
        self.assertTrue(m.snapshot().events[1].alert)
        self.assertEqual(dac(m).dropouts, 1)

    def test_estop_transition_alerts(self):
        m, clock, _c, _ = setup()
        feed(m, clock, 3)
        feed(m, clock, 2, light_engine=3, le_flags=4)
        ev = m.snapshot().events[-1]
        self.assertEqual((ev.kind, ev.message.args[1:], ev.alert), ("estado", ("operacional", "estop"), True))

    def test_duplicate_ip(self):
        m, clock, _c, _ = setup()
        for _ in range(4):
            m.receive(packet("000000000001"), "192.168.0.80", device="en7")
            m.receive(packet("000000000002"), "192.168.0.80", device="en7")
            m.tick()
            clock.advance(1)
        snap = m.snapshot()
        self.assertEqual([d.health.state for d in snap.dacs], ["duplicado", "duplicado"])
        self.assertEqual(snap.dacs[0].banner.code, "banner_duplicado")

    def test_ip_change_is_logged(self):
        m, clock, _c, _ = setup()
        feed(m, clock, 2)
        feed(m, clock, 2, ip="192.168.0.99")
        self.assertIn("ip_mudou", [e.kind for e in m.snapshot().events])


class Commands(unittest.TestCase):
    def test_clear_needs_confirmation_while_playing(self):
        m, clock, control, _ = setup()
        feed(m, clock, 3, playback=2, point_rate=30000)
        self.assertEqual(m.clear_estop("8a9e36988cce"), CommandResult.NEEDS_CONFIRMATION)
        self.assertEqual(control.calls, [])
        self.assertEqual(m.clear_estop("8a9e36988cce", confirmed=True), CommandResult.STARTED)
        self.assertEqual(control.calls, [("c", "192.168.0.80")])

    def test_clear_outcome_logged(self):
        m, clock, _c, _ = setup(FakeControl(clear=ClearReply(ClearOutcome.NAK_ACTIVE, b"!")))
        feed(m, clock, 3, light_engine=3, le_flags=4)
        self.assertEqual(m.clear_estop("8a9e36988cce"), CommandResult.STARTED)
        self.assertEqual(m.snapshot().events[-1].message.code, "clear_nak_causa_ativa")
        self.assertEqual(m.clear_estop("ffffffffffff"), CommandResult.NOT_FOUND)

    def test_rename_and_forget(self):
        m, clock, _c, store = setup(names={"8a9e36988cce": "PALCO ESQ"})
        feed(m, clock, 2)
        self.assertEqual(dac(m).label, "PALCO ESQ")
        self.assertTrue(m.rename("8a9e36988cce", "  torre   esquerda  "))
        self.assertEqual(store.names, {"8a9e36988cce": "torre esquerda"})
        self.assertTrue(m.rename("8a9e36988cce", ""))
        self.assertEqual(dac(m).label, "988CCE")
        self.assertFalse(m.forget("8a9e36988cce"))  # online: não esquece
        clock.advance(10)
        self.assertTrue(m.forget("8a9e36988cce"))
        self.assertEqual(m.snapshot().dacs, [])


class Presenter(unittest.TestCase):
    def test_snapshot_is_json(self):
        m, clock, _c, _ = setup()
        feed(m, clock, 6, playback=2, point_rate=30000)
        data = json.loads(json.dumps(snapshot_json(m.snapshot())))
        d = data["dacs"][0]
        self.assertEqual((d["estado"], d["nivel"], d["mac_texto"]), ("tocando", "ativo", "8A:9E:36:98:8C:CE"))
        self.assertEqual([g["id"] for g in d["grupos"]], ["rede", "laser", "saida", "dispositivo"])
        self.assertEqual(d["taxa"][-1][1], 30000)


if __name__ == "__main__":
    unittest.main()
