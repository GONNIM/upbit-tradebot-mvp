"""
✅ WO-17 (P) 회귀: 부분 재계산(recompute_from_changed_ts) 경로 제거 (2026-10-01)

원 결함:
- 조정 변경이 있으면 strategy_engine 이 recompute_from_changed_ts(full_series, changed_ts) → 바뀐 봉 이후 꼬리로
  seed_from_closes 시도. 꼬리는 늘 1~3봉이라 "Not enough data for seed: N < 200" 실패(journal 보존분 8,199건,
  성공 0건, WO-16 뒤에도 매 주기)인데 "[INDICATORS] 부분 재계산 완료" 가 찍힘.
- 잠재 위험: 꼬리 ≥ 200 이면 꼬리 SMA 로 재시드(현재 봉 포함) 뒤 update_incremental(현재 봉) 을 또 해서
  현재 봉 이중 반영 + EMA 연속성 단절 + prev_ema 초기화.

처방 P1: 호출 제거, 조정 변경 시 update_incremental 1회만. 로그 정정.

실행:
    python3 -m unittest tests.regressions.test_r_2026_10_01_wo17p_no_partial_recompute -v
"""
from __future__ import annotations

import sys
import unittest
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from core.indicator_state import IndicatorState  # noqa: E402


def _closes(n, base=730.0):
    return [base + ((i * 7) % 13) - 6 for i in range(n)]


def _indicators(seed):
    ind = IndicatorState(ema_fast=60, ema_slow=200, base_ema=200, use_separate_ema=True,
                         ema_fast_buy=60, ema_slow_buy=200, ema_fast_sell=60, ema_slow_sell=200)
    assert ind.seed_from_closes(seed)
    return ind


def _engine(indicators):
    from core.strategy_engine import StrategyEngine
    from core.pending_order import PendingOrderQueue
    e = StrategyEngine.__new__(StrategyEngine)
    e.user_id, e.ticker, e.strategy_type = "stub", "KRW-JTO", "EMA"
    e.bar_count, e.interval_sec, e.last_bar_ts = 200, 300, None
    e._evaluated_bar_ts = OrderedDict()
    e._pending_orders = PendingOrderQueue()
    e._execution_lock = MagicMock()
    e._execution_lock.__enter__ = MagicMock(return_value=None)
    e._execution_lock.__exit__ = MagicMock(return_value=False)
    e.buffer = []
    e.indicators = indicators
    e.position = MagicMock(has_position=False, pending_order=False)
    e.strategy = MagicMock()
    e.strategy.on_bar = MagicMock(return_value=None)
    e.strategy.enable_base_ema_gap = False
    e.strategy.last_buy_reason = None
    e.strategy.gap_details = None
    for name in ("_reconcile_position_with_wallet", "_maybe_release_limit_pending", "_record_invariant_snapshot",
                 "_log_bar_evaluation", "_send_log_event", "_record_audit_log", "_resolve_pending_buy", "execute"):
        setattr(e, name, MagicMock())
    e.q = None
    return e


def _bar(ts, close):
    from core.strategy_engine import Bar
    return Bar(ts=ts, open=close, high=close, low=close, close=close, volume=1.0,
               is_closed=True, is_confirmed=True, source="REST_RECONCILED")


def _state(ind):
    return (round(ind.ema_fast_buy, 9), round(ind.ema_slow_buy, 9), round(ind.ema_base, 9))


class TestNoPartialRecompute(unittest.TestCase):

    def setUp(self):
        self.seed = _closes(200)
        self.t0 = datetime(2026, 10, 1, 4, 20, tzinfo=timezone.utc)

    def _run(self, tail_len):
        ind = _indicators(self.seed)
        expected = _indicators(self.seed)
        expected.update_incremental(751.0)                     # 정답: 증분 1회
        idx = [self.t0 - timedelta(minutes=5 * k) for k in range(tail_len - 1, -1, -1)]
        full = pd.DataFrame({"Close": _closes(tail_len - 1) + [751.0]}, index=idx)
        diff = {"rest_failed": False, "changed_count": tail_len, "changed_ts": list(idx), "backfill_mode": False}
        from core.strategy_engine import StrategyEngine
        with self.assertLogs("core.strategy_engine", level="INFO") as cm:
            StrategyEngine.on_new_bar_confirmed(_engine(ind), _bar(self.t0, 751.0), full, diff)
        return ind, expected, cm.output

    def test_1_small_tail_single_increment(self):
        """꼬리 1봉(평상시 매 주기) → 지표 = 증분 1회, 정정 로그."""
        ind, expected, logs = self._run(1)
        self.assertEqual(_state(ind), _state(expected))
        self.assertTrue(any("Reconcile 변경 감지 (지표는 증분만, 재시드 없음)" in m for m in logs), logs)

    def test_2_long_tail_no_reseed_no_double(self):
        """꼬리 250봉(옛 코드라면 재시드 성공 조건) → 여전히 증분 1회, prev_ema 유지."""
        ind, expected, _ = self._run(250)
        self.assertEqual(_state(ind), _state(expected))
        self.assertIsNotNone(ind.prev_ema_fast_buy)

    def test_3_old_path_double_application_contrast(self):
        """(대조) 옛 경로를 같은 입력으로 흉내 내면(꼬리 SMA 재시드 + 현재 봉 증분) 정답과 달라지고 prev_ema 가 사라짐."""
        tail = _closes(249) + [751.0]
        old = _indicators(self.seed)
        old.seed_from_closes(tail)          # 옛 recompute_from_changed_ts 의 핵심 동작 (현재 봉 포함)
        old.update_incremental(751.0)       # 옛 strategy_engine 의 "재계산 후 현재 봉 반영"
        expected = _indicators(self.seed)
        expected.update_incremental(751.0)
        self.assertNotEqual(_state(old), _state(expected))

    def test_4_path_removed(self):
        """경로·오기 로그 소멸."""
        self.assertFalse(hasattr(IndicatorState, "recompute_from_changed_ts"))
        for rel in ("core/indicator_state.py", "core/strategy_engine.py", "engine/live_loop.py"):
            src = (ROOT / rel).read_text(encoding="utf-8")
            self.assertNotIn("부분 재계산 완료", src, rel)
            self.assertNotIn("indicators.recompute_from_changed_ts(", src, rel)
        ll = (ROOT / "engine" / "live_loop.py").read_text(encoding="utf-8")
        self.assertIn("개 봉 변경 감지 (지표는 증분만)", ll)


if __name__ == "__main__":
    unittest.main()
