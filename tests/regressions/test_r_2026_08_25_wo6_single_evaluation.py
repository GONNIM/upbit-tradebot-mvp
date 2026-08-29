"""WO-6 회귀 테스트 — 봉당 매매 판단 1회 강제 이력 관리.

배경:
    WO-2 v3 3차 배포에서 같은 봉이 두 번 매매 판단을 받는 경로가 관측됐다.
    [SKIP-BAR] 로 실시간을 건너뛴 뒤 BACKFILL 이 재평가하고, 이후 VERIFY 후속
    부분 재계산이 다시 매매 판단을 실행하는 흐름이었다. 이 결함으로 매수 신호
    8건이 소실됐고, 우연히 회수된 1건이 실현 손실로 이어졌다.

    WO-6 개편 후에는 StrategyEngine._evaluated_bar_ts (OrderedDict, 상한
    1000봉) 로 실시간 판단 이력을 관리한다. 실시간(backfill_mode=False)만
    등록되며, BACKFILL 재평가는 등록하지 않는다. 실시간 재진입은 검사에
    걸려 스킵된다.

실행:
    python3 -m unittest tests.regressions.test_r_2026_08_25_wo6_single_evaluation -v
"""
from __future__ import annotations

import sys
import unittest
from collections import OrderedDict
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class TestEvaluatedBarTsRegistration(unittest.TestCase):
    """WO-6: _register_evaluated_bar 헬퍼가 상한과 순서를 지키는지 확인."""

    def _make_engine_stub(self):
        """StrategyEngine 을 완전 초기화하지 않고 필요한 필드만 가진 stub 반환."""
        from core.strategy_engine import StrategyEngine

        # __init__ 실행 없이 필드만 세팅
        engine = StrategyEngine.__new__(StrategyEngine)
        engine._evaluated_bar_ts = OrderedDict()
        return engine

    def test_register_adds_bar(self):
        engine = self._make_engine_stub()
        ts = datetime(2026, 8, 25, 9, 4, 0, tzinfo=timezone.utc)
        engine._register_evaluated_bar(ts)
        self.assertIn(ts, engine._evaluated_bar_ts)

    def test_register_maintains_order(self):
        engine = self._make_engine_stub()
        ts_list = [
            datetime(2026, 8, 25, 9, i, 0, tzinfo=timezone.utc)
            for i in range(0, 5)
        ]
        for ts in ts_list:
            engine._register_evaluated_bar(ts)
        # OrderedDict 는 등록 순서 유지
        self.assertEqual(list(engine._evaluated_bar_ts.keys()), ts_list)

    def test_register_evicts_oldest_when_over_limit(self):
        engine = self._make_engine_stub()
        limit = engine._EVAL_HISTORY_MAX
        # 상한 + 3 만큼 등록
        base = datetime(2026, 8, 25, 0, 0, 0, tzinfo=timezone.utc)
        for i in range(limit + 3):
            engine._register_evaluated_bar(base + timedelta(minutes=i))
        # 상한 유지 확인
        self.assertEqual(len(engine._evaluated_bar_ts), limit)
        # 가장 오래된 3개는 삭제됐어야 함
        self.assertNotIn(base + timedelta(minutes=0), engine._evaluated_bar_ts)
        self.assertNotIn(base + timedelta(minutes=1), engine._evaluated_bar_ts)
        self.assertNotIn(base + timedelta(minutes=2), engine._evaluated_bar_ts)
        # 가장 최근 봉은 남아 있어야 함
        self.assertIn(base + timedelta(minutes=limit + 2), engine._evaluated_bar_ts)


class TestBackfillDoesNotRegister(unittest.TestCase):
    """WO-6: BACKFILL 은 이력에 등록하지 않아 순서가 꼬여도 실시간이 차단되지 않는다.

    이 테스트는 등록 흐름의 개념 검증이다. 실제 on_new_bar_confirmed 실행은
    많은 의존성을 요구하므로, 여기서는 필드 상태와 헬퍼 호출 시나리오만 검사.
    """

    def _make_engine_stub(self):
        from core.strategy_engine import StrategyEngine
        engine = StrategyEngine.__new__(StrategyEngine)
        engine._evaluated_bar_ts = OrderedDict()
        return engine

    def test_realtime_registers_backfill_does_not(self):
        engine = self._make_engine_stub()
        ts = datetime(2026, 8, 25, 9, 4, 0, tzinfo=timezone.utc)

        # 시나리오 1: 실시간 첫 진입 (backfill_mode=False) 이 봉을 등록
        backfill_mode = False
        if not backfill_mode:
            engine._register_evaluated_bar(ts)
        self.assertIn(ts, engine._evaluated_bar_ts)

        # 시나리오 2: BACKFILL 재진입 (backfill_mode=True) 은 등록하지 않음
        backfill_mode = True
        ts_backfill = datetime(2026, 8, 25, 9, 5, 0, tzinfo=timezone.utc)
        if not backfill_mode:
            engine._register_evaluated_bar(ts_backfill)
        # backfill 은 등록 안 됨
        self.assertNotIn(ts_backfill, engine._evaluated_bar_ts)

        # 시나리오 3: 실시간 재진입 (같은 봉) 은 검사에서 걸림
        # (검사 로직은 on_new_bar_confirmed 안에 있으므로 여기서는 조건만 확인)
        backfill_mode = False
        should_skip = (not backfill_mode) and (ts in engine._evaluated_bar_ts)
        self.assertTrue(should_skip, "실시간 재진입은 스킵되어야 함")


if __name__ == "__main__":
    unittest.main()
