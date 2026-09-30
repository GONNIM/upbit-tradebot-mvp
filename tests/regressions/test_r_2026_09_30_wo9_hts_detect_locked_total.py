"""
✅ WO-9 (c) 회귀: 외부 미체결 매도 주문 취소(묶임 해제)를 HTS 매수로 오기록 (2026-09-30)

원 결함: engine/order_reconciler.py 의 HTS 매수 감지가 DB 가용 수량(virtual_coin)과
Upbit 가용 수량(balance)만 비교했다. 외부 지정가 매도 주문을 걸면 가용이 묶임(locked)으로
이동하고, 주문을 취소하면 가용이 되돌아온다. 이 "되돌아옴"이 잔고 증가로 잡혀
- 가용 0 에서 회복 → HTS_BUY 오기록 (KRW-JTO audit_trades id=1158, 2026-09-30 06:23:15)
- 가용 일부에서 회복 → HTS_BUY_ADD 오기록 → strategy_engine._on_hts_detect 가
  Trailing 상태(highest/armed/fixed_amount)를 리셋 → Trailing 보호 장치가 조용히 해제

봉쇄: 비교 기준을 가용+묶임 합계로 바꾼다 (services.db.get_position_total_qty).

실행:
    python3 -m unittest tests.regressions.test_r_2026_09_30_wo9_hts_detect_locked_total -v
"""
from __future__ import annotations

import shutil
import sqlite3
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

USER = "test_r_2026_09_30_wo9c"
TICKER = "KRW-JTO"
QTY = 2097.5170824


def _bal(avail: float, locked: float = 0.0, avg: float = 767.0) -> list[dict]:
    """Upbit get_balances() 응답 형식 (문자열 값)."""
    return [
        {"currency": "KRW", "balance": "100000", "locked": "0", "avg_buy_price": "0"},
        {"currency": "JTO", "balance": str(avail), "locked": str(locked), "avg_buy_price": str(avg)},
    ]


class _FakeEngine:
    """StrategyEngine._on_hts_detect 를 실제 코드로 돌리기 위한 최소 self."""

    def __init__(self):
        from core.position_state import PositionState
        self.position = PositionState()
        self._execution_lock = threading.Lock()
        self.bar_count = 100
        self.ticker = TICKER


class TestHtsDetectLockedTotal(unittest.TestCase):

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="wo9c_"))
        self.db_path = str(self.tmpdir / f"tradebot_{USER}.db")
        # ⚠️ 실 Telegram 발송 차단 — config 가 .env 를 로드하므로 자격증명이 살아 있음
        self.notify = MagicMock(return_value=True)
        self._patchers = [
            patch("services.init_db.get_db_path", return_value=self.db_path),
            patch("services.db.get_db_path", return_value=self.db_path),
            patch("services.notifier.send", self.notify),
        ]
        for p in self._patchers:
            p.start()
        from services.init_db import initialize_db, ensure_all_schemas
        initialize_db(USER)
        ensure_all_schemas(USER)

        from engine.order_reconciler import OrderReconciler
        self.upbit = MagicMock()
        self.or_ = OrderReconciler(self.upbit, balance_sync_interval=0.0)
        self.or_._live_user_ids.add(USER)

        # 엔진 포지션: 봇 매수 767, Trailing 무장 상태
        from core.strategy_engine import StrategyEngine
        self.engine = _FakeEngine()
        pos = self.engine.position
        pos.avg_price = 767.0
        pos.qty = QTY
        pos.entry_bar = 50
        pos.highest_price = 800.0
        pos.highest_since_entry = 800.0
        pos.trailing_armed = True
        pos.trailing_fixed_amount = 5.0
        pos.trailing_activation_price = 790.0

        self.callback_calls: list[dict] = []

        def _cb(**kw):
            self.callback_calls.append(kw)
            StrategyEngine._on_hts_detect(self.engine, **kw)

        self.or_.register_hts_detect_callback(USER, TICKER, _cb)

    def tearDown(self):
        for p in self._patchers:
            p.stop()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    # ── helpers ──
    def _seed(self, avail: float, locked: float = 0.0, entry_price: float = 767.0):
        from services.db import update_coin_position
        update_coin_position(USER, TICKER, avail, locked, entry_price=entry_price)

    def _sync(self, avail: float, locked: float = 0.0, avg: float = 767.0):
        self.upbit.get_balances.return_value = _bal(avail, locked, avg)
        self.or_._last_balance_sync = 0.0
        self.or_._periodic_balance_sync()

    def _hts_rows(self) -> list[tuple]:
        with sqlite3.connect(self.db_path) as c:
            return c.execute(
                "SELECT reason, price FROM audit_trades "
                "WHERE ticker=? AND type='BUY' AND reason IN ('HTS_BUY','HTS_BUY_ADD') ORDER BY id",
                (TICKER,),
            ).fetchall()

    def _assert_trailing_intact(self):
        pos = self.engine.position
        self.assertTrue(pos.trailing_armed, "Trailing 무장 상태가 유지돼야 함")
        self.assertEqual(pos.highest_price, 800.0)
        self.assertEqual(pos.highest_since_entry, 800.0)
        self.assertEqual(pos.trailing_fixed_amount, 5.0)
        self.assertEqual(pos.trailing_activation_price, 790.0)

    # ── 1. 이번 사례 재현: 전량 묶임 → 해제 ──
    def test_full_lock_release_not_detected(self):
        """KRW-JTO 09-29 22:31 전량 묶임 → 09-30 06:23 해제: HTS 미감지."""
        self._seed(QTY, 0.0)
        self._sync(0.0, QTY)      # 외부 지정가 매도 주문: 가용 2097→0, 묶임 0→2097
        self._sync(QTY, 0.0)      # 외부 주문 취소: 가용 0→2097, 묶임 2097→0
        self.assertEqual(self._hts_rows(), [], "묶임 해제를 HTS_BUY 로 기록하면 안 됨 (id=1158 유형)")
        self.assertEqual(self.callback_calls, [])
        self._assert_trailing_intact()
        from services.db import get_position_meta
        self.assertFalse((get_position_meta(USER, TICKER) or {}).get("hts_buy", False),
                         "봇 매수 포지션에 hts_buy 플래그가 붙으면 안 됨")

    # ── 2. 부분 묶임 해제: HTS_BUY_ADD 미감지 + Trailing 유지 ──
    def test_partial_lock_release_keeps_trailing(self):
        self._seed(QTY, 0.0)
        self._sync(QTY - 1000.0, 1000.0)   # 일부만 외부 매도 주문에 묶임
        self._sync(QTY, 0.0)               # 취소 → 가용 일부 회복
        self.assertEqual(self._hts_rows(), [], "부분 묶임 해제를 HTS_BUY_ADD 로 기록하면 안 됨")
        self.assertEqual(self.callback_calls, [], "콜백이 불리면 Trailing 리셋 경로 진입")
        self._assert_trailing_intact()

    # ── 3. 진짜 HTS 매수: 합계 증가 → 감지 ──
    def test_genuine_new_hts_buy_detected(self):
        self._seed(0.0, 0.0, entry_price=0.0)
        self._sync(100.0, 0.0, avg=770.0)
        self.assertEqual(self._hts_rows(), [("HTS_BUY", 770.0)])
        self.assertEqual(len(self.callback_calls), 1)
        self.assertEqual(self.callback_calls[0]["reason"], "HTS_BUY")

    def test_genuine_add_while_locked_detected(self):
        """묶인 상태에서 외부 추가 매수 → 합계 증가 → HTS_BUY_ADD (구 로직은 HTS_BUY 로 오분류)."""
        self._seed(0.0, QTY)
        self._sync(500.0, QTY, avg=765.0)
        self.assertEqual(self._hts_rows(), [("HTS_BUY_ADD", 765.0)])
        self.assertEqual(self.callback_calls[0]["reason"], "HTS_BUY_ADD")
        self.assertEqual(self.callback_calls[0]["qty"], 500.0, "콜백 qty 는 가용 수량 (의미 무변경)")

    def test_genuine_add_resets_trailing_as_before(self):
        """진짜 추가 매수의 Trailing 리셋은 기존 동작 그대로 유지 (판정 로직 무변경)."""
        self._seed(QTY, 0.0)
        self._sync(QTY + 500.0, 0.0, avg=766.0)
        self.assertEqual(self._hts_rows(), [("HTS_BUY_ADD", 766.0)])
        self.assertFalse(self.engine.position.trailing_armed)
        self.assertIsNone(self.engine.position.highest_price)

    # ── 4. 헬퍼 단위 ──
    def test_get_position_total_qty_sums_locked(self):
        from services.db import get_position_total_qty, get_position_qty
        self._seed(10.0, 5.0)
        self.assertEqual(get_position_qty(USER, TICKER), 10.0)
        self.assertEqual(get_position_total_qty(USER, TICKER), 15.0)
        self.assertEqual(get_position_total_qty(USER, "KRW-NONE"), 0.0)


if __name__ == "__main__":
    unittest.main()
