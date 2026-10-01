"""
✅ WO-18 회귀: hts_buy 플래그 잔존 (2026-10-01)

원 결함:
- KRW-JTO account_positions.meta.hts_buy 가 2026-09-30 16:47:09 HTS 매수 감지 때 켜진 뒤,
  09-30 23:40 전량 매도로 보유 0 이 된 뒤에도 남음.
- 2026-10-01 14:15 봇이 직접 산 포지션의 매도 평가에 hts_buy=True 가 찍힘(14:20 ~ 15:35 STOP_LOSS_CHECK).
- 현재 매도 판정은 hts_buy 를 쓰지 않으나(Policy P-3, a192d31), WO-8 알림 등급(WARN 강등)·대시보드
  진입 출처 표시가 이 값을 읽음.

처방: 보유 0 이 되는 경로(봇 매도 close_position, 지갑 0 강제 청산 close_position, sync_all_positions cleared)
에서 DB meta 와 position.metadata 의 hts_buy 를 함께 지우고 [HTS-FLAG] cleared 로그 1줄. 기동 시 정합 검사로
보유 0 + hts_buy 잔존 행 정리(최근 HTS 매수 감사 행이 있으면 건너뜀).

실행:
    python3 -m unittest tests.regressions.test_r_2026_10_01_wo18_hts_flag_clear -v
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

U = "test_r_2026_10_01_wo18"
T = "KRW-JTO"
_NOW = datetime(2026, 10, 1, 14, 16, 51, tzinfo=ZoneInfo("Asia/Seoul"))   # 진입 시각 (open_position 필수)


class _DbCase(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="wo18_"))
        self.db_path = str(self.tmpdir / f"tradebot_{U}.db")
        self._patchers = [
            patch("services.init_db.get_db_path", return_value=self.db_path),
            patch("services.db.get_db_path", return_value=self.db_path),
            patch("services.notifier.send", MagicMock(return_value=True)),
        ]
        for p in self._patchers:
            p.start()
        from services.init_db import initialize_db, ensure_all_schemas
        from services.db import ensure_schema
        initialize_db(U)
        ensure_all_schemas(U)
        ensure_schema(U)
        import services.db as db
        self.db = db

    def tearDown(self):
        for p in self._patchers:
            p.stop()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    # ── 도우미 ──────────────────────────────────────────────
    def _hts_buy(self, qty=1340.43626806, price=761.0, audit=True):
        """order_reconciler HTS 감지와 같은 순서: 플래그 설정 → 감사 행 → 다음 동기화에서 수량 반영."""
        self.db.mark_position_as_hts_buy(U, T)
        if audit:
            self.db.insert_trade_audit(
                user_id=U, ticker=T, interval_sec=60, bar=0, kind="BUY", reason="HTS_BUY",
                price=price, macd=None, signal=None, entry_price=price, entry_bar=None, bars_held=None,
                tp=None, sl=None, highest=None, ts_pct=None, ts_armed=None, timestamp=None, bar_time=None,
            )
        self.db.update_coin_position(U, T, qty, 0.0, entry_price=price)

    def _position(self):
        from core.position_state import PositionState
        p = PositionState(trader=SimpleNamespace(user_id=U, test_mode=False), ticker=T)
        p.metadata = self.db.get_position_meta(U, T)   # sync_from_wallet 의 metadata 로드와 같음
        return p

    def _stop_loss_hts_log(self, position, price):
        from core.filters.sell_filters import StopLossFilter
        with self.assertLogs("core.filters.sell_filters", level="INFO") as cm:
            StopLossFilter(0.01).evaluate(position=position, current_price=price)
        line = [m for m in cm.output if "STOP_LOSS_CHECK" in m][0]
        return line.split("hts_buy=")[-1].strip()


class TestHtsFlagClear(_DbCase):

    def test_1_bot_sell_clears_flag_next_bot_buy_false(self):
        """HTS 매수 → 플래그 → 봇 매도 전량(close_position) → 플래그 해제 → 다음 봇 매수 SELL 평가 hts_buy=False."""
        self._hts_buy()
        p = self._position()
        p.open_position(qty=1340.43626806, price=761.0, bar_idx=1, ts=_NOW)
        self.assertTrue(p.metadata.get("hts_buy"))
        self.assertEqual(self._stop_loss_hts_log(p, 760.0), "True")

        with self.assertLogs("core.position_state", level="INFO") as cm:
            p.close_position(ts=None, reason="bot_sell")
        self.assertTrue(any("[HTS-FLAG] cleared | reason=bot_sell | ticker=KRW-JTO" in m for m in cm.output), cm.output)
        self.assertNotIn("hts_buy", p.metadata)
        self.assertNotIn("hts_buy", self.db.get_position_meta(U, T))
        self.db.update_coin_position(U, T, 0.0, 0.0, entry_price=0.0)

        # 다음 봇 매수 (WO-16 관측 2026-10-01 14:15 와 같은 상황)
        p2 = self._position()
        p2.open_position(qty=308.4559189, price=749.0, bar_idx=211, ts=_NOW)
        self.assertEqual(self._stop_loss_hts_log(p2, 749.0), "False")

    def test_2_hts_sell_sync_all_positions_clears_flag(self):
        """HTS 매도 감지 경로: 지갑에서 사라짐 → sync_all_positions cleared → 플래그 해제 + 로그."""
        self._hts_buy()
        with self.assertLogs("services.db", level="INFO") as cm:
            self.db.sync_all_positions_from_balances(U, [])
        self.assertTrue(any("[HTS-FLAG] cleared | reason=sync_all_positions_cleared | ticker=KRW-JTO" in m for m in cm.output), cm.output)
        self.assertNotIn("hts_buy", self.db.get_position_meta(U, T))
        p = self._position()
        p.open_position(qty=10.0, price=749.0, bar_idx=1, ts=_NOW)
        self.assertEqual(self._stop_loss_hts_log(p, 749.0), "False")

    def test_3_wallet_zero_forced_close_clears_flag(self):
        """지갑 0 강제 청산 경로(POSITION-SYNC Case 1 의 close_position)도 해제."""
        self._hts_buy()
        p = self._position()
        p.open_position(qty=1.0, price=761.0, bar_idx=1, ts=_NOW)
        with self.assertLogs("core.position_state", level="INFO") as cm:
            p.close_position(ts=None, reason="position_sync_wallet_zero")
        self.assertTrue(any("reason=position_sync_wallet_zero" in m for m in cm.output))
        self.assertNotIn("hts_buy", self.db.get_position_meta(U, T))

    def test_4_no_flag_no_log(self):
        """플래그가 없으면 [HTS-FLAG] 로그 없음 (봇 매수·매도만 있는 평상시)."""
        p = self._position()
        p.open_position(qty=1.0, price=749.0, bar_idx=1, ts=_NOW)
        with self.assertLogs("core.position_state", level="INFO") as cm:
            p.close_position(ts=None, reason="bot_sell")
        self.assertFalse(any("[HTS-FLAG]" in m for m in cm.output))

    def test_5_boot_reconcile_clears_stale_only(self):
        """기동 정합 검사: 보유 0 + hts_buy 잔존(오래된 HTS 감사) → 해제, 보유 중 → 유지, 최근 HTS 감지 직후 → 건너뜀."""
        # (가) 잔존: 보유 0, 플래그 true, HTS 감사 행 없음(오래전) — 2026-10-01 JTO 상태
        self.db.update_coin_position(U, T, 0.0, 0.0, entry_price=0.0)
        self.db.update_position_meta(U, T, {"hts_buy": True})
        # (나) 보유 중 HTS 포지션
        self.db.update_coin_position(U, "KRW-MON", 13801.39, 0.0, entry_price=36.9)
        self.db.update_position_meta(U, "KRW-MON", {"hts_buy": True})
        # (다) 막 감지됨: 플래그·감사 행은 있고 수량은 아직 0 (다음 동기화 전)
        self.db.mark_position_as_hts_buy(U, "KRW-ABC")
        self.db.insert_trade_audit(
            user_id=U, ticker="KRW-ABC", interval_sec=60, bar=0, kind="BUY", reason="HTS_BUY",
            price=10.0, macd=None, signal=None, entry_price=10.0, entry_bar=None, bars_held=None,
            tp=None, sl=None, highest=None, ts_pct=None, ts_armed=None, timestamp=None, bar_time=None,
        )
        with self.assertLogs("services.db", level="INFO") as cm:
            n = self.db.clear_stale_hts_flags(U)
        self.assertEqual(n, 1)
        self.assertTrue(any("[HTS-FLAG] cleared | reason=boot_reconcile | ticker=KRW-JTO" in m for m in cm.output))
        self.assertNotIn("hts_buy", self.db.get_position_meta(U, T))
        self.assertTrue(self.db.get_position_meta(U, "KRW-MON").get("hts_buy"))
        self.assertTrue(self.db.get_position_meta(U, "KRW-ABC").get("hts_buy"))
        self.assertTrue(any("건너뜀" in m and "KRW-ABC" in m for m in cm.output))


class TestCallSites(unittest.TestCase):

    def test_reasons_and_boot_hook(self):
        se = (ROOT / "core" / "strategy_engine.py").read_text(encoding="utf-8")
        self.assertIn('self.position.close_position(bar.ts, reason="bot_sell")', se)
        self.assertIn('self.position.close_position(ts=None, reason="position_sync_wallet_zero")', se)
        ll = (ROOT / "engine" / "live_loop.py").read_text(encoding="utf-8")
        self.assertIn("_hts_cleared = clear_stale_hts_flags(user_id)", ll)
        db = (ROOT / "services" / "db.py").read_text(encoding="utf-8")
        self.assertIn('clear_position_hts_flag(user_id, ticker, reason="sync_all_positions_cleared")', db)


if __name__ == "__main__":
    unittest.main()
