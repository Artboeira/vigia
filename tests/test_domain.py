"""Regras puras: protocolo, saúde, leituras, rede e firmware. Sem rede, sem threads."""
import unittest

from vigia.domain import protocol as p
from vigia.domain.dac import Control, Dac, FirmwareNote, Timing
from vigia.domain.firmware import update_available
from vigia.domain.health import Level, Message, assess, readings
from vigia.domain.network import (Interface, IpPlan, NetIssue, net_issue, resolve_via, suggest_dac_ip,
                                  suggest_pc_ip)

NOW = 1000.0
NETS = {"192.168.0.132": Interface("192.168.0.132", "255.255.255.0", "Wi-Fi", "en0")}


def make(age=0.0, ctrl=Control.FREE, fw="ed4-354-x", ip="192.168.0.80", via="192.168.0.132",
         mac="8a9e36988cce", **status):
    data = p.build_announcement(mac, 30, 3, 3839, 100000, p.DacStatus(**status))
    dac = Dac(p.Announcement.parse(data, ip, NOW - age), via, NOW - age)
    dac.control, dac.control_at, dac.firmware = ctrl, NOW, fw
    return dac


def values(dac, nets=None):
    return {r.key: r for _g, items in readings(dac, NOW, nets or {}) for r in items}


class Protocol(unittest.TestCase):
    def test_roundtrip(self):
        st = p.DacStatus(light_engine=3, playback=2, le_flags=5, fullness=100, point_rate=30000)
        ann = p.Announcement.parse(p.build_announcement("8a9e36988cce", 30, 3, 3839, 100000, st), "1.2.3.4", 5.0)
        self.assertEqual((ann.mac, ann.hw_rev, ann.sw_rev, ann.buffer_capacity, ann.status), ("8a9e36988cce", 30, 3, 3839, st))

    def test_wrong_size(self):
        with self.assertRaises(ValueError):
            p.Announcement.parse(b"x" * 35, "1.2.3.4", 0)

    def test_clear_outcome(self):
        hello_estop = p.build_response(b"a", b"?", p.DacStatus(light_engine=3))
        hello_ok = p.build_response(b"a", b"?", p.DacStatus())
        ack_ok = p.build_response(b"a", b"c", p.DacStatus())
        ack_estop = p.build_response(b"a", b"c", p.DacStatus(light_engine=3))
        self.assertEqual(p.clear_outcome(hello_estop, ack_ok).outcome, p.ClearOutcome.CLEARED)
        self.assertEqual(p.clear_outcome(hello_ok, ack_ok).outcome, p.ClearOutcome.NOT_IN_ESTOP)  # ED4 dá ACK sempre
        self.assertEqual(p.clear_outcome(hello_estop, ack_estop).outcome, p.ClearOutcome.STILL_ESTOP)
        self.assertEqual(p.clear_outcome(hello_estop, b"!c" + ack_estop[2:]).outcome, p.ClearOutcome.NAK_ACTIVE)
        self.assertEqual(p.clear_outcome(hello_estop, b"\xffc" + ack_estop[2:]), p.ClearReply(p.ClearOutcome.UNKNOWN, b"\xff"))

    def test_version(self):
        self.assertTrue(p.version_unsupported(b"Iv" + bytes(20)))
        self.assertFalse(p.version_unsupported(b"ed4-354-0d43ec7" + bytes(7)))
        self.assertEqual(p.decode_version(b"ed4-354-0d43ec7" + bytes(17)), "ed4-354-0d43ec7")


class Health(unittest.TestCase):
    def test_states(self):
        self.assertEqual(assess(make(), NOW).state, "operacional")
        self.assertEqual(assess(make(age=10), NOW).level, Level.OFF)
        h = assess(make(light_engine=3, le_flags=0b10110), NOW)  # interlock aberto + travas
        self.assertEqual((h.level, h.state), (Level.ERROR, "estop"))
        self.assertLess(h.reason.args.index("interlock_aberto"), h.reason.args.index("disparado_interlock"))
        self.assertEqual(assess(make(ctrl=Control.REFUSED), NOW).state, "ocupada")
        self.assertEqual(assess(make(ctrl=Control.NO_ANSWER), NOW).state, "sem_controle")
        self.assertEqual(assess(make(ctrl=Control.NO_ANSWER, playback=2), NOW).state, "tocando")
        self.assertEqual(assess(make(playback=2, point_rate=30000), NOW).level, Level.ACTIVE)
        self.assertEqual(assess(make(playback=1), NOW).state, "preparada")

    def test_old_tcp_result_expires(self):
        dac = make(ctrl=Control.NO_ANSWER)
        dac.control_at -= Timing().control_ttl + 1
        self.assertEqual(assess(dac, NOW).state, "operacional")

    def test_madmapper_network_flag(self):
        self.assertEqual(assess(make(light_engine=3, le_flags=1, playback=2, point_rate=20000), NOW).state, "tocando")
        self.assertEqual(assess(make(light_engine=3, le_flags=1), NOW).level, Level.WARN)
        self.assertEqual(assess(make(light_engine=3, le_flags=5, playback=2), NOW).level, Level.ERROR)
        self.assertEqual(assess(make(light_engine=3, le_flags=0), NOW).level, Level.ERROR)
        laser = values(make(light_engine=3, le_flags=1, playback=2))["laser"]
        self.assertEqual((laser.value.code, laser.level), ("liberado_flag", Level.OK))

    def test_wrong_subnet_state(self):
        dac = make(ip="10.0.0.5")
        dac.net_issue = NetIssue.WRONG_SUBNET
        self.assertEqual(assess(dac, NOW).state, "faixa")
        self.assertEqual(values(dac, NETS)["faixa"].value.code, "fora_faixa")


class Readings(unittest.TestCase):
    def test_laser_and_interlock(self):
        r = values(make(light_engine=3, le_flags=4 | 2))
        self.assertEqual((r["interlock"].value.code, r["interlock"].level), ("aberto", Level.ERROR))
        self.assertEqual((r["laser"].value.code, r["laser"].level), ("estop", Level.ERROR))

    def test_firmware(self):
        r = values(make(fw=None, ctrl=Control.REFUSED))
        self.assertEqual(r["firmware"].value, Message("nao_lido", ("recusada",)))
        r = values(make(fw="ed4-152-33b3cef"))
        self.assertEqual((r["atualizacao"].value.args, r["atualizacao"].level), (("ed4-354",), Level.WARN))
        dac = make(fw=None)
        dac.firmware_note = FirmwareNote.OLD
        self.assertEqual(values(dac)["atualizacao"].value.code, "provavel_desatualizado")  # o original dizia "em dia"

    def test_adapter_and_buffer(self):
        r = values(make(fullness=1919), NETS)
        self.assertEqual(r["placa_pc"].value.args, ("Wi-Fi · 192.168.0.132",))
        self.assertAlmostEqual(r["buffer"].meter, 1919 / 3839)

    def test_signal_quality(self):
        t = Timing()
        dac = make()
        self.assertIsNone(dac.signal_quality(NOW, t))  # cedo demais para medir
        for k in range(1, 21):  # 20 s, metade dos anúncios perdidos
            if k % 2 == 0:
                dac.absorb(p.Announcement.parse(p.build_announcement(dac.mac, 30, 3, 3839, 100000, p.DacStatus()),
                                                dac.ann.ip, NOW + k), dac.via, t)
        frac, window = dac.signal_quality(NOW + 20, t)
        self.assertEqual(window, 20)
        self.assertAlmostEqual(frac, 0.55, places=2)

    def test_every_group_has_values(self):
        self.assertEqual([g for g, _ in readings(make(), NOW, {})], ["rede", "laser", "saida", "dispositivo"])


class Network(unittest.TestCase):
    def test_issue(self):
        self.assertIsNone(net_issue("192.168.0.80", "192.168.0.132", NETS, []))
        self.assertEqual(net_issue("10.0.0.5", "192.168.0.132", NETS, []), NetIssue.WRONG_SUBNET)
        self.assertEqual(net_issue("192.168.0.80", "192.168.0.132", NETS, ["192.168.0.80"]), NetIssue.DUPLICATE_IP)

    def test_suggestions(self):
        self.assertEqual(suggest_dac_ip("192.168.0.132", "255.255.255.0", {"192.168.0.50"}),
                         IpPlan("192.168.0.51", "255.255.255.0", "192.168.0.1"))
        self.assertEqual(suggest_dac_ip("169.254.10.3", "255.255.0.0", set()).ip, "169.254.0.50")
        self.assertEqual(suggest_pc_ip("10.0.0.5"), IpPlan("10.0.0.10", "255.255.255.0", ""))
        self.assertEqual(suggest_pc_ip("10.0.0.10").ip, "10.0.0.11")
        self.assertEqual(suggest_pc_ip("10.0.0.5", {"10.0.0.10", "10.0.0.11"}).ip, "10.0.0.12")  # pula IPs em uso
        self.assertEqual(suggest_pc_ip("169.254.33.7").mask, "255.255.0.0")

    def test_resolve_via(self):
        nets = {"192.168.0.20": Interface("192.168.0.20", "255.255.255.0", "Wi-Fi", "en0"),
                "169.254.33.7": Interface("169.254.33.7", "255.255.0.0", "", "en7")}
        self.assertEqual(resolve_via("10.0.0.5", nets, "en7"), "169.254.33.7")      # placa do IP_RECVIF
        self.assertEqual(resolve_via("192.168.0.80", nets), "192.168.0.20")         # pela faixa
        self.assertEqual(resolve_via("10.0.0.5", nets), "")                         # duas placas, nenhuma na faixa
        self.assertEqual(resolve_via("10.0.0.5", {"192.168.0.20": nets["192.168.0.20"]}), "192.168.0.20")
        self.assertEqual(resolve_via("10.0.0.5", nets, via_ip="1.2.3.4"), "1.2.3.4")  # Windows: socket por placa


class Firmware(unittest.TestCase):
    def test_update(self):
        self.assertEqual(update_available("ed4-152-33b3cef"), "ed4-354")
        self.assertIsNone(update_available("ed4-354-0d43ec7"))
        self.assertEqual(update_available("ed3v80-abc"), "ed3v86")
        self.assertIsNone(update_available("r331-ed4bef5"))
        self.assertIsNone(update_available(""))


if __name__ == "__main__":
    unittest.main()
