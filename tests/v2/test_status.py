import unittest
from datetime import datetime, timedelta

from v2 import db
from v2.status import (DELAY_FACTOR, UNKNOWN_SEC, engine_state, interval_sec,
                       mode_state)

NOW = datetime(2026, 10, 23, 12, 0, 0, tzinfo=db.KST)


def ago(sec):
    return NOW - timedelta(seconds=sec)


class TestEngineState(unittest.TestCase):
    def test_constants(self):
        self.assertEqual(DELAY_FACTOR, 3)
        self.assertEqual(UNKNOWN_SEC, 1800)

    def test_interval_sec(self):
        self.assertEqual(interval_sec("minute3"), 180)
        self.assertEqual(interval_sec("minute1"), 60)
        self.assertEqual(interval_sec("minute60"), 3600)
        self.assertEqual(interval_sec("day"), 86400)
        with self.assertRaises(ValueError):
            interval_sec("minute0")
        with self.assertRaises(ValueError):
            interval_sec("bogus")
        with self.assertRaises(ValueError):
            interval_sec(None)

    def test_engine_state_ok(self):
        r = engine_state(ago(60), None, "TEST", 180, NOW)
        self.assertEqual(r, {"level": "ok", "ago_sec": 60, "basis": "eval"})

    def test_engine_state_ok_boundary_is_exceeding(self):
        # delay_sec = 540: 540 은 ok, 541 은 delay (「초과」 비교)
        self.assertEqual(engine_state(ago(540), None, "TEST", 180, NOW)["level"], "ok")
        self.assertEqual(engine_state(ago(541), None, "TEST", 180, NOW)["level"], "delay")

    def test_engine_state_no_trade_gap_is_delay(self):
        r = engine_state(ago(24 * 60), None, "TEST", 180, NOW)
        self.assertEqual(r, {"level": "delay", "ago_sec": 1440, "basis": "eval"})

    def test_engine_state_delay_upper_boundary(self):
        self.assertEqual(engine_state(ago(1800), None, "TEST", 180, NOW)["level"], "delay")
        self.assertEqual(engine_state(ago(1801), None, "TEST", 180, NOW)["level"], "unknown")

    def test_engine_state_unknown_when_none(self):
        r = engine_state(None, None, "LIVE", 180, NOW)
        self.assertEqual(r, {"level": "unknown", "ago_sec": None, "basis": "none"})
        r = engine_state(None, None, "TEST", 180, NOW)
        self.assertEqual(r, {"level": "unknown", "ago_sec": None, "basis": "none"})

    def test_engine_state_unknown_after_unknown_sec(self):
        r = engine_state(ago(1801), None, "LIVE", 180, NOW)
        self.assertEqual(r, {"level": "unknown", "ago_sec": 1801, "basis": "eval"})

    def test_live_uses_accounts_ts_as_secondary(self):
        r = engine_state(ago(2000), ago(300), "LIVE", 180, NOW)
        self.assertEqual(r, {"level": "delay", "ago_sec": 2000, "basis": "accounts"})

    def test_test_mode_ignores_accounts(self):
        r = engine_state(ago(2000), ago(300), "TEST", 180, NOW)
        self.assertEqual(r, {"level": "unknown", "ago_sec": 2000, "basis": "eval"})

    def test_live_no_eval_recent_accounts_delay(self):
        r = engine_state(None, ago(300), "LIVE", 180, NOW)
        self.assertEqual(r, {"level": "delay", "ago_sec": None, "basis": "accounts"})
        r = engine_state(None, ago(300), "TEST", 180, NOW)
        self.assertEqual(r["level"], "unknown")

    def test_live_never_ok_from_accounts(self):
        r = engine_state(None, ago(1), "LIVE", 180, NOW)
        self.assertEqual(r["level"], "delay")
        r = engine_state(ago(5000), ago(1), "LIVE", 180, NOW)
        self.assertEqual(r["level"], "delay")

    def test_live_stale_accounts_keeps_eval_basis(self):
        r = engine_state(ago(2000), ago(541), "LIVE", 180, NOW)
        self.assertEqual(r, {"level": "unknown", "ago_sec": 2000, "basis": "eval"})
        r = engine_state(None, ago(541), "LIVE", 180, NOW)
        self.assertEqual(r, {"level": "unknown", "ago_sec": None, "basis": "none"})

    def test_accounts_boundary_is_exceeding(self):
        r = engine_state(ago(2000), ago(540), "LIVE", 180, NOW)
        self.assertEqual(r["level"], "delay")

    def test_future_eval_ts_clamped(self):
        r = engine_state(NOW + timedelta(seconds=5), None, "TEST", 180, NOW)
        self.assertEqual(r, {"level": "ok", "ago_sec": 0, "basis": "eval"})

    def test_no_word_jeongji(self):
        import v2.status as s
        self.assertNotIn("정지", open(s.__file__, encoding="utf-8").read())


class TestModeState(unittest.TestCase):
    def test_mode_mismatch_warning(self):
        r = mode_state("LIVE", "TEST")
        self.assertEqual(r, {"mode_engine": "LIVE", "mode_entry": "TEST",
                             "mode_mismatch": True})
        r = mode_state("TEST", "TEST")
        self.assertFalse(r["mode_mismatch"])

    def test_mode_engine_none_or_empty(self):
        for v in (None, ""):
            r = mode_state(v, "LIVE")
            self.assertEqual(r, {"mode_engine": None, "mode_entry": "LIVE",
                                 "mode_mismatch": False})

    def test_mode_case_sensitive(self):
        self.assertTrue(mode_state("live", "LIVE")["mode_mismatch"])


if __name__ == "__main__":
    unittest.main()
