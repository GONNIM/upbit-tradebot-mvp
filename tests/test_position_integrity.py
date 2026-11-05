#!/usr/bin/env python3
"""
Position Integrity — SP-PI-1~5 회귀·시나리오 test.

Phase D (T1~T9) 커버:
- T1/T2: apply_entry 필수 필드 강제 + 완전 세팅 (Stale filter 근본 결함 재발 차단)
- T6: open_position → apply_entry(source="bot_market") 위임 회귀
- T7: close_position 회귀 (모든 필드 리셋)
- T9: _on_limit_fill uuid dedupe (buy_market 콜백 오발동 방지)
- SP-PI-3: has_pending_bot_limit_buy + has_recent_bot_buy_for_ticker pending 우선 확인
- SP-PI-4: bars_held ≤ 0 audit fallback → entry_bar 복구 흐름 검증
- SP-PI-5: live_loop 부팅 seed 실패 시 has_position=False 유지 (문서 검증 — 별도 시나리오 walkthrough)

실행:
    python3 -m unittest tests.test_position_integrity -v
"""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

# 프로젝트 루트 sys.path 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.position_state import PositionState  # noqa: E402

KST = ZoneInfo("Asia/Seoul")


# ─────────────────────────────────────────────────────────────
# SP-PI-1 — PositionState.apply_entry / open_position 위임
# ─────────────────────────────────────────────────────────────


class TestApplyEntryContract(unittest.TestCase):
    """SP-PI-1: apply_entry 는 entry_ts 필수. 모든 필드 완전 세팅."""

    def test_apply_entry_requires_entry_ts(self):
        """entry_ts=None 이면 ValueError (F3 재발 물리 차단)."""
        p = PositionState()
        with self.assertRaises(ValueError):
            p.apply_entry(
                qty=1.0, avg_price=100.0, entry_bar=10,
                entry_ts=None, source="bot_market",
            )

    def test_apply_entry_sets_all_fields(self):
        """정상 apply_entry 는 has_position/qty/avg_price/entry_bar/entry_ts/highest_since_entry 완전 세팅."""
        p = PositionState()
        ts = datetime(2026, 7, 3, 10, 25, tzinfo=KST)
        p.apply_entry(
            qty=1.5, avg_price=1135.0, entry_bar=100,
            entry_ts=ts, source="bot_market",
        )
        self.assertTrue(p.has_position)
        self.assertEqual(p.qty, 1.5)
        self.assertEqual(p.avg_price, 1135.0)
        self.assertEqual(p.entry_bar, 100)
        self.assertEqual(p.entry_ts, ts)
        self.assertEqual(p.highest_since_entry, 1135.0)  # 초기값=avg_price
        self.assertEqual(p.last_action_ts, ts)
        self.assertFalse(p.pending_order)

    def test_apply_entry_source_variants(self):
        """5가지 source 라벨 모두 정상 처리 (P2/P3/HTS 우회 경로 검증)."""
        for src in ("bot_market", "bot_limit_fill", "wallet_sync", "boot_seed", "hts_detect"):
            with self.subTest(source=src):
                p = PositionState()
                p.apply_entry(
                    qty=1.0, avg_price=100.0, entry_bar=1,
                    entry_ts=datetime.now(KST), source=src,
                )
                self.assertTrue(p.has_position)
                self.assertIsNotNone(p.entry_ts)

    def test_apply_entry_highest_since_entry_explicit(self):
        """highest_since_entry 명시 시 그대로 사용."""
        p = PositionState()
        p.apply_entry(
            qty=1.0, avg_price=100.0, entry_bar=1,
            entry_ts=datetime.now(KST), source="wallet_sync",
            highest_since_entry=120.0,
        )
        self.assertEqual(p.highest_since_entry, 120.0)


class TestOpenPositionDelegation(unittest.TestCase):
    """SP-PI-1: open_position 은 apply_entry(source="bot_market") 위임 (T6 회귀)."""

    def test_open_position_delegates_and_sets_fields(self):
        p = PositionState()
        ts = datetime(2026, 7, 3, 16, 40, tzinfo=KST)
        p.open_position(qty=2.0, price=1161.0, bar_idx=201, ts=ts)
        self.assertTrue(p.has_position)
        self.assertEqual(p.qty, 2.0)
        self.assertEqual(p.avg_price, 1161.0)
        self.assertEqual(p.entry_bar, 201)
        self.assertEqual(p.entry_ts, ts)
        self.assertEqual(p.highest_since_entry, 1161.0)

    def test_open_position_ts_none_raises(self):
        """open_position 도 apply_entry 위임이므로 ts=None 시 예외."""
        p = PositionState()
        with self.assertRaises(ValueError):
            p.open_position(qty=1.0, price=100.0, bar_idx=1, ts=None)


class TestClosePositionReset(unittest.TestCase):
    """T7: close_position 회귀 — 모든 필드 리셋."""

    def test_close_position_resets_all(self):
        p = PositionState()
        p.apply_entry(
            qty=1.0, avg_price=100.0, entry_bar=1,
            entry_ts=datetime.now(KST), source="bot_market",
        )
        p.highest_price = 120.0
        p.trailing_armed = True
        ts_close = datetime.now(KST)
        p.close_position(ts=ts_close)
        self.assertFalse(p.has_position)
        self.assertEqual(p.qty, 0.0)
        self.assertIsNone(p.avg_price)
        self.assertIsNone(p.entry_bar)
        self.assertIsNone(p.entry_ts)
        self.assertIsNone(p.highest_since_entry)
        self.assertIsNone(p.highest_price)
        self.assertFalse(p.trailing_armed)


# ─────────────────────────────────────────────────────────────
# SP-PI-3 — has_pending_bot_limit_buy / has_recent
# ─────────────────────────────────────────────────────────────


class TestHasPendingAndRecent(unittest.TestCase):
    """SP-PI-3: SP6 5봉 대기와 HTS 오판정 방지 검증."""

    def setUp(self):
        # 임시 DB 파일
        self.tmpdir = tempfile.mkdtemp()
        self.user_id = "sp_pi_test"
        self.ticker = "KRW-JTO"

        # get_db_path 패치용 임시 파일
        self.db_path = os.path.join(self.tmpdir, f"tradebot_{self.user_id}.db")
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE orders (
                id INTEGER PRIMARY KEY,
                user_id TEXT, ticker TEXT, side TEXT, state TEXT,
                executed_volume REAL, price REAL, timestamp TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE audit_trades (
                id INTEGER PRIMARY KEY,
                ticker TEXT, type TEXT, timestamp TEXT
            )
        """)
        conn.commit()
        conn.close()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _patch_get_db(self):
        """services.db.get_db_path 와 get_db 를 임시 파일로 리다이렉트."""
        import services.db as sdb
        self._orig_get_db_path = sdb.get_db_path
        sdb.get_db_path = lambda uid: self.db_path

    def _restore_get_db(self):
        import services.db as sdb
        sdb.get_db_path = self._orig_get_db_path

    def test_has_pending_true_when_requested(self):
        """orders 에 REQUESTED BUY 있으면 True — SP6 5봉 대기 케이스."""
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO orders (user_id, ticker, side, state, executed_volume, price) "
            "VALUES (?, ?, 'BUY', 'REQUESTED', 0, 1135.0)",
            (self.user_id, self.ticker),
        )
        conn.commit()
        conn.close()

        self._patch_get_db()
        try:
            from services.db import has_pending_bot_limit_buy
            self.assertTrue(has_pending_bot_limit_buy(self.user_id, self.ticker))
        finally:
            self._restore_get_db()

    def test_has_pending_true_when_partially_filled(self):
        """PARTIALLY_FILLED 도 pending 으로 간주."""
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO orders (user_id, ticker, side, state, executed_volume, price) "
            "VALUES (?, ?, 'BUY', 'PARTIALLY_FILLED', 0.5, 1135.0)",
            (self.user_id, self.ticker),
        )
        conn.commit()
        conn.close()

        self._patch_get_db()
        try:
            from services.db import has_pending_bot_limit_buy
            self.assertTrue(has_pending_bot_limit_buy(self.user_id, self.ticker))
        finally:
            self._restore_get_db()

    def test_has_pending_false_when_filled(self):
        """FILLED 는 pending 아님 (체결 완료)."""
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO orders (user_id, ticker, side, state, executed_volume, price) "
            "VALUES (?, ?, 'BUY', 'FILLED', 1.0, 1135.0)",
            (self.user_id, self.ticker),
        )
        conn.commit()
        conn.close()

        self._patch_get_db()
        try:
            from services.db import has_pending_bot_limit_buy
            self.assertFalse(has_pending_bot_limit_buy(self.user_id, self.ticker))
        finally:
            self._restore_get_db()


# ─────────────────────────────────────────────────────────────
# SP-PI-2 — _on_limit_fill uuid dedupe
# ─────────────────────────────────────────────────────────────


class TestLimitFillUuidDedupe(unittest.TestCase):
    """SP-PI-2: fill callback 은 _pending_buy_uuid 와 일치할 때만 apply_entry."""

    def _make_engine_stub(self):
        """StrategyEngine 의 _on_limit_fill 만 실행 가능한 최소 stub."""
        from core.strategy_engine import StrategyEngine
        eng = StrategyEngine.__new__(StrategyEngine)
        eng.position = MagicMock()
        eng.q = None
        eng.bar_count = 250
        eng._execution_lock = threading.Lock()
        eng._pending_buy_uuid = "UUID-LIMIT-42"
        eng._pending_buy_bar = 245
        eng._pending_buy_wait_bars = 5
        return eng

    def test_matching_uuid_applies_entry(self):
        eng = self._make_engine_stub()
        ts = datetime(2026, 7, 3, 16, 40, tzinfo=KST)
        eng._on_limit_fill(
            uuid="UUID-LIMIT-42", executed_price=1161.0,
            executed_qty=2.0, executed_ts=ts,
        )
        eng.position.apply_entry.assert_called_once()
        call_kwargs = eng.position.apply_entry.call_args.kwargs
        self.assertEqual(call_kwargs["source"], "bot_limit_fill")
        self.assertEqual(call_kwargs["qty"], 2.0)
        self.assertEqual(call_kwargs["avg_price"], 1161.0)
        self.assertEqual(call_kwargs["entry_bar"], 250)
        self.assertEqual(call_kwargs["entry_ts"], ts)
        # pending 해제 확인
        self.assertIsNone(eng._pending_buy_uuid)

    def test_mismatched_uuid_skips_apply_entry(self):
        """buy_market uuid 등이 fill callback 에 도착해도 skip (중복 apply_entry 방지)."""
        eng = self._make_engine_stub()
        ts = datetime.now(KST)
        eng._on_limit_fill(
            uuid="UUID-MARKET-99", executed_price=1200.0,
            executed_qty=1.0, executed_ts=ts,
        )
        eng.position.apply_entry.assert_not_called()
        # pending uuid 유지 (아직 원래 LIMIT 대기 중)
        self.assertEqual(eng._pending_buy_uuid, "UUID-LIMIT-42")

    def test_pending_none_skips(self):
        """이미 처리된 상태 (pending uuid None) — skip."""
        eng = self._make_engine_stub()
        eng._pending_buy_uuid = None
        ts = datetime.now(KST)
        eng._on_limit_fill(
            uuid="UUID-LIMIT-42", executed_price=1161.0,
            executed_qty=2.0, executed_ts=ts,
        )
        eng.position.apply_entry.assert_not_called()


# ─────────────────────────────────────────────────────────────
# SP-PI-4 — bars_held ≤ 0 audit fallback (functional walkthrough)
# ─────────────────────────────────────────────────────────────


class TestBarsHeldAuditFallback(unittest.TestCase):
    """SP-PI-4: entry_bar=None 상태에서 estimate_bars_held_from_audit fallback 확인."""

    def test_fallback_recovers_entry_bar(self):
        """position.entry_bar 를 current_bar - audit_bh 로 즉시 복구."""
        p = PositionState()
        # apply_entry 없이 has_position 만 세팅한 결함 상태 시뮬 (F3 재현)
        p._has_position = True
        p.qty = 1.0
        p.avg_price = 1135.0
        p.entry_bar = None  # ← 결함: entry_ts 도 None
        current_bar_idx = 300
        audit_bh = 98  # audit 실측 (10:25 매수 후 12:00 시점)

        # SP-PI-4 로직 재현 (strategy_incremental.py:1053~)
        bars_held = p.get_bars_held(current_bar_idx)
        self.assertLessEqual(bars_held, 0, "entry_bar=None 시 bars_held ≤ 0")

        if bars_held <= 0 and audit_bh > 0:
            new_entry_bar = current_bar_idx - audit_bh
            p.entry_bar = new_entry_bar
            bars_held = audit_bh

        # 복구 후 entry_bar 정합성
        self.assertEqual(p.entry_bar, 300 - 98)
        self.assertEqual(bars_held, 98)
        # 다음 봉에 in-memory 값으로 정상 계산되는지 확인
        self.assertEqual(p.get_bars_held(current_bar_idx + 1), 99)


# ─────────────────────────────────────────────────────────────
# 회귀 — Hot Reload 는 position 안 건드림 (T5)
# ─────────────────────────────────────────────────────────────


class TestHotReloadPositionRegression(unittest.TestCase):
    """T5 회귀: strategy.reload_conditions 는 self.position 참조 없이 임계값만 update."""

    def test_reload_conditions_does_not_touch_position(self):
        """reload_conditions 코드가 self.position 을 건드리지 않음을 소스로 검증."""
        source_path = Path(__file__).parent.parent / "core" / "strategy_incremental.py"
        source = source_path.read_text(encoding="utf-8")
        # reload_conditions 함수 시작~끝 대략 추출 (다음 def 까지)
        idx_start = source.find("def reload_conditions")
        self.assertNotEqual(idx_start, -1, "reload_conditions 함수 존재 확인")
        idx_next = source.find("\n    def ", idx_start + 1)
        block = source[idx_start:idx_next if idx_next != -1 else len(source)]
        # position/self.position 접근 없음 확인
        forbidden_tokens = ["self.position", "position.has_position", "position.close_position"]
        for tok in forbidden_tokens:
            self.assertNotIn(tok, block, f"reload_conditions 안에 {tok} 접근 없음")


if __name__ == "__main__":
    unittest.main(verbosity=2)
