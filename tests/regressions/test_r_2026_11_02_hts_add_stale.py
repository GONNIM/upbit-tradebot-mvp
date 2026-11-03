"""
✅ 1102-01 회귀: 앱 추가매수(HTS_BUY_ADD) 직후 정체 매도 (2026-11-01 13:12 KRW-JTO audit 1470)

사고: 00:51 봇 매수(509) 뒤 최고 511 로 정체 목표(0.30%)를 이미 넘긴 보유에 13:11:39 앱 추가매수가 들어오자
`_on_hts_detect` 가 정체용 최고가만 지우고 진입 시각(00:51)은 그대로 둬, 다음 봉(12.3h 경과)에
새 평단 507.57 기준 최고 수익 −0.31% 로 전량 정체 매도됐다.

고침 (계획 docs/plans/2026-11-02-hts-add-stale/plan.md 방향 (나)):
- HTS_BUY_ADD 감지 때 정체 시계를 새 진입처럼 다시 시작(entry_ts = 감지 시각, highest_since_entry = 새 평단).
- 재시작(boot_seed)도 같은 뜻: 마지막 봇 매수 뒤 청산 없이 남은 마지막 BUY 가 HTS_BUY_ADD 면 그 시각부터.
트레일링 리셋·약매수 해제·HTS_BUY(신규)·PULLBACK 분할 대기 무시 갈래는 그대로.

실행 (게이트 안에서): python3 -m unittest tests.regressions.test_r_2026_11_02_hts_add_stale -v
바깥 연결 없음.
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

KST = ZoneInfo("Asia/Seoul")
USER = "test_r_2026_11_02_stale"
TICKER = "KRW-JTO"
STALE_H, STALE_PCT = 3.0, 0.003


class _FakeEngine:
    def __init__(self, strategy_type="EMA"):
        from core.position_state import PositionState
        self.position = PositionState()
        self._execution_lock = threading.Lock()
        self.bar_count = 300
        self.ticker = TICKER
        self.strategy_type = strategy_type
        self._pending_split = None


def _bot_entry_position(eng, entry_ts, avg=509.0, highest=511.0, qty=508.10):
    """00:51 봇 매수 뒤, 최고 511 까지 오른 보유 (트레일링 무장 상태 포함)."""
    pos = eng.position
    pos.apply_entry(qty=qty, avg_price=avg, entry_bar=100, entry_ts=entry_ts, source="bot_market")
    pos.highest_since_entry = highest
    pos.highest_price = highest
    pos.trailing_armed, pos.trailing_fixed_amount, pos.trailing_activation_price = True, 2.0, 510.0
    return pos


def _stale(pos, price, at):
    from core.filters.sell_filters import StalePositionFilter
    return StalePositionFilter(stale_hours=STALE_H, stale_threshold_pct=STALE_PCT).evaluate(
        position=pos, current_price=price, current_time=at)


def _detect(eng, reason="HTS_BUY_ADD", avg=507.57, qty=968.587):
    from core.strategy_engine import StrategyEngine
    before = datetime.now(KST)
    StrategyEngine._on_hts_detect(eng, avg_price=avg, qty=qty, reason=reason)
    return before, datetime.now(KST)


class TestHtsAddStaleClock(unittest.TestCase):

    def test_r1_incident_no_stale_sell_right_after_add(self):
        """R1: 12.3h 지난 보유에 앱 추가매수 → 다음 봉(봉 시작 < 감지 시각) 정체 매도 아님. 옛 동작은 매도(재현)."""
        eng = _FakeEngine()
        now = datetime.now(KST)
        pos = _bot_entry_position(eng, entry_ts=now - timedelta(hours=12, minutes=20))

        # 재현: 옛 코드 상태(정체용 최고가만 지우고 시계 유지) → 같은 봉에서 STALE_POSITION
        old = _FakeEngine()
        old_pos = _bot_entry_position(old, entry_ts=pos.entry_ts)
        old_pos.avg_price, old_pos.qty, old_pos.highest_since_entry = 507.57, 968.587, None
        self.assertEqual(_stale(old_pos, 506.0, now - timedelta(minutes=2)).reason, "STALE_POSITION")

        before, after = _detect(eng)
        self.assertTrue(before <= pos.entry_ts <= after)
        self.assertEqual(pos.highest_since_entry, 507.57)
        self.assertEqual(pos.avg_price, 507.57)
        bar_start = pos.entry_ts - timedelta(minutes=2, seconds=39)   # 13:09 봉 시작 < 13:11:39 감지
        r = _stale(pos, 506.0, bar_start)
        self.assertNotEqual(r.reason, "STALE_POSITION")
        self.assertEqual(_stale(pos, 506.0, pos.entry_ts + timedelta(minutes=3)).reason, "STALE_OK")

    def test_r1b_add_raising_avg_not_sold_right_after(self):
        """R1b: 최고 511 뒤 530 에 더 사 평단 520 으로 올라도 감지 직후 정체 매도 아님."""
        eng = _FakeEngine()
        pos = _bot_entry_position(eng, entry_ts=datetime.now(KST) - timedelta(hours=5))
        _detect(eng, avg=520.0, qty=1000.0)
        self.assertEqual(pos.highest_since_entry, 520.0)
        self.assertNotEqual(_stale(pos, 519.0, pos.entry_ts + timedelta(minutes=1)).reason, "STALE_POSITION")

    def test_r2_stale_still_works_after_restart_window(self):
        """R2: 감지 + 3h 지난 봉에서 최고 수익 < 0.30% 면 정체 매도 (기능 유지)."""
        eng = _FakeEngine()
        pos = _bot_entry_position(eng, entry_ts=datetime.now(KST) - timedelta(hours=12))
        _detect(eng)
        for m in (3, 60, 120):
            self.assertEqual(_stale(pos, 507.0, pos.entry_ts + timedelta(minutes=m)).reason, "STALE_OK")
        r = _stale(pos, 507.5, pos.entry_ts + timedelta(hours=3, minutes=1))
        self.assertEqual(r.reason, "STALE_POSITION")

    def test_r3_target_reached_within_window_no_stale(self):
        """R3: 감지 뒤 3h 안에 0.30% 넘게 오르면 그 뒤 정체 매도 없음 (기존 뜻)."""
        eng = _FakeEngine()
        pos = _bot_entry_position(eng, entry_ts=datetime.now(KST) - timedelta(hours=12))
        _detect(eng)
        _stale(pos, 509.5, pos.entry_ts + timedelta(hours=1))   # (509.5−507.57)/507.57 = 0.38%
        r = _stale(pos, 505.0, pos.entry_ts + timedelta(hours=4))
        self.assertEqual(r.reason, "STALE_OK")

    def test_r4_trailing_reset_and_weak_entry_cleared(self):
        """R4: 트레일링 리셋·약매수 해제는 그대로."""
        eng = _FakeEngine()
        pos = _bot_entry_position(eng, entry_ts=datetime.now(KST) - timedelta(hours=1))
        pos.clear_weak_entry = MagicMock()
        _detect(eng)
        self.assertIsNone(pos.highest_price)
        self.assertFalse(pos.trailing_armed)
        self.assertIsNone(pos.trailing_fixed_amount)
        self.assertIsNone(pos.trailing_activation_price)
        pos.clear_weak_entry.assert_called_once_with(reason="hts_buy_add")

    def test_r5_hts_buy_new_branch_unchanged(self):
        """R5: HTS_BUY(신규) — entry_ts 는 비어 있을 때만 세팅, 이미 있으면 유지, 정체용 최고가 그대로."""
        eng = _FakeEngine()
        t0 = datetime.now(KST) - timedelta(hours=4)
        pos = _bot_entry_position(eng, entry_ts=t0)
        _detect(eng, reason="HTS_BUY", avg=508.0, qty=600.0)
        self.assertEqual(pos.entry_ts, t0)
        self.assertEqual(pos.highest_since_entry, 511.0)
        self.assertTrue(pos.trailing_armed)

        eng2 = _FakeEngine()
        before, after = _detect(eng2, reason="HTS_BUY", avg=508.0, qty=600.0)
        self.assertTrue(before <= eng2.position.entry_ts <= after)
        self.assertIsNone(eng2.position.highest_since_entry)

    def test_r6_pullback_pending_split_ignored(self):
        """R6: PULLBACK 분할 체결 대기 중이면 감지 무시 — 시계·평단 무변경."""
        eng = _FakeEngine(strategy_type="PULLBACK")
        eng._pending_split = {"uuid": "u-1"}
        t0 = datetime.now(KST) - timedelta(hours=4)
        pos = _bot_entry_position(eng, entry_ts=t0)
        _detect(eng)
        self.assertEqual(pos.entry_ts, t0)
        self.assertEqual(pos.avg_price, 509.0)
        self.assertEqual(pos.highest_since_entry, 511.0)


class TestBootSeedStaleClock(unittest.TestCase):
    """R7: 재시작(boot_seed) 때 정체 시계."""

    BOT_TS = "2026-11-01T00:51:12+09:00"

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="hts_add_stale_"))
        self.db_path = str(self.tmpdir / f"tradebot_{USER}.db")
        self._patchers = [
            patch("services.init_db.get_db_path", return_value=self.db_path),
            patch("services.db.get_db_path", return_value=self.db_path),
            patch("services.notifier.send", MagicMock(return_value=True)),
        ]
        for p in self._patchers:
            p.start()
        from services.init_db import initialize_db, ensure_all_schemas
        from services.db import ensure_schema
        initialize_db(USER)
        ensure_all_schemas(USER)
        ensure_schema(USER)

    def tearDown(self):
        for p in self._patchers:
            p.stop()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _audit(self, kind, reason, ts, price=509.0):
        from services.db import insert_trade_audit
        insert_trade_audit(user_id=USER, ticker=TICKER, interval_sec=180, bar=0, kind=kind, reason=reason,
                           price=price, macd=None, signal=None, entry_price=price, entry_bar=None, bars_held=None,
                           tp=None, sl=None, highest=None, ts_pct=None, ts_armed=None, timestamp=ts)

    def _pos(self, trader=SimpleNamespace(user_id=USER), ticker=TICKER):
        from core.position_state import PositionState
        p = PositionState(trader=trader, ticker=ticker)
        p._has_position = True
        p.qty = 968.587
        p.avg_price = 507.57
        p.entry_ts = datetime(2026, 11, 2, 12, 0, tzinfo=KST)   # 기동 시각 (wallet_sync)
        return p

    def _seed(self, p, entry_ts_iso=BOT_TS):
        from engine import live_loop
        return live_loop._apply_boot_seed(p, {"price": 509.0, "entry_bar": 100, "entry_ts_iso": entry_ts_iso}, 968.587)

    def test_r7a_add_after_bot_buy_uses_add_time(self):
        self._audit("BUY", "EMA_GC", "2026-11-01T00:51:12.123456+09:00")
        self._audit("BUY", "HTS_BUY_ADD", "2026-11-01T13:11:39.654321+09:00", price=507.57)
        p = self._pos()
        with self.assertLogs("engine.live_loop", level="INFO") as cm:
            self.assertTrue(self._seed(p))
        self.assertEqual(p.entry_ts, datetime(2026, 11, 1, 13, 11, 39, 654321, tzinfo=KST))
        self.assertEqual(p.highest_since_entry, 507.57)
        self.assertTrue(any("[STALE-CLOCK]" in m for m in cm.output))
        self.assertFalse(any("[BOOT-SEED]" in m for m in cm.output))

    def test_r7b_no_add_keeps_bot_time(self):
        self._audit("BUY", "EMA_GC", "2026-11-01T00:51:12.123456+09:00")
        p = self._pos()
        self.assertTrue(self._seed(p))
        self.assertEqual(p.entry_ts, datetime.fromisoformat(self.BOT_TS))

    def test_r7c_sell_after_add_keeps_bot_time(self):
        self._audit("BUY", "EMA_GC", "2026-11-01T00:51:12+09:00")
        self._audit("BUY", "HTS_BUY_ADD", "2026-11-01T13:11:39+09:00")
        self._audit("SELL", "STALE_POSITION", "2026-11-01T13:12:05+09:00")
        p = self._pos()
        self.assertTrue(self._seed(p))
        self.assertEqual(p.entry_ts, datetime.fromisoformat(self.BOT_TS))

        self._audit("HTS_SELL", "HTS_SELL", "2026-11-01T13:12:06+09:00")
        p2 = self._pos()
        self.assertTrue(self._seed(p2))
        self.assertEqual(p2.entry_ts, datetime.fromisoformat(self.BOT_TS))

    def test_r7d_mixed_formats_and_older_add(self):
        """orders 쪽 시각이 공백 구분·tz 없음이고 audit 은 KST ISO 마이크로초 — datetime 으로 비교."""
        self._audit("BUY", "HTS_BUY_ADD", "2026-11-01T13:11:39.654321+09:00")
        p = self._pos()
        self.assertTrue(self._seed(p, entry_ts_iso="2026-11-01 00:51:12"))
        self.assertEqual(p.entry_ts, datetime(2026, 11, 1, 13, 11, 39, 654321, tzinfo=KST))

        # 봇 매수 시각이 더 늦으면(예: 추가매수 뒤 봇 매수) 봇 매수 시각 그대로
        p2 = self._pos()
        self.assertTrue(self._seed(p2, entry_ts_iso="2026-11-01 14:00:00"))
        self.assertEqual(p2.entry_ts, datetime(2026, 11, 1, 14, 0, tzinfo=KST))

    def test_r7e_lookup_failure_or_no_identity_keeps_bot_time(self):
        self._audit("BUY", "HTS_BUY_ADD", "2026-11-01T13:11:39+09:00")
        with patch("services.db.get_last_open_buy_trade", side_effect=RuntimeError("db down")):
            p = self._pos()
            self.assertTrue(self._seed(p))
            self.assertEqual(p.entry_ts, datetime.fromisoformat(self.BOT_TS))
        with patch("services.db.get_last_open_buy_trade",
                   return_value={"timestamp": "not-a-time", "reason": "HTS_BUY_ADD", "price": 1.0}):
            p = self._pos()
            self.assertTrue(self._seed(p))
            self.assertEqual(p.entry_ts, datetime.fromisoformat(self.BOT_TS))
        for trader, ticker in ((None, TICKER), (MagicMock(), TICKER), (SimpleNamespace(user_id=USER), None)):
            with patch("services.db.get_last_open_buy_trade") as m:
                p = self._pos(trader=trader, ticker=ticker)
                self.assertTrue(self._seed(p))
                self.assertEqual(p.entry_ts, datetime.fromisoformat(self.BOT_TS))
                m.assert_not_called()


if __name__ == "__main__":
    unittest.main()
