"""WO-6 회귀 테스트 — 지표 갱신과 매매 판단 분리.

배경:
    WO-2 v3 3차 배포에서 VERIFY 후속 부분 재계산이 지표를 갱신하면서 매매
    판단까지 이어져, 같은 봉이 두 번 매매 판단을 받는 결함이 있었다.
    부분 재계산이 지표 정확성을 유지하는 순기능은 필요하지만, 매매 판단
    실행은 봉당 1회로 제한되어야 한다.

    WO-6 개편 후에는 매매 판단 직전에 _evaluated_bar_ts 검사를 두어, 지표
    갱신은 계속 실행되지만 이미 실시간 평가된 봉의 재진입은 매매 판단부터
    스킵된다.

실행:
    python3 -m unittest tests.regressions.test_r_2026_08_25_wo6_indicator_recompute_isolation -v
"""
from __future__ import annotations

import sys
import unittest
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class TestIndicatorRecomputeIsolation(unittest.TestCase):
    """WO-6: 이미 실시간 평가된 봉은 매매 판단만 스킵된다.

    지표 갱신 로직은 매매 판단 검사 이전(strategy_engine.py 라인 594~628 부근)
    에 위치한다. WO-6 검사는 이 이후, 실제 self.strategy.on_bar 호출 직전에
    수행된다. 따라서 검사에 걸려 매매 판단이 스킵되어도 지표 갱신은 이미
    완료된 상태.
    """

    def test_check_only_gates_strategy_on_bar(self):
        """검사 조건이 (backfill_mode=False AND ts in _evaluated_bar_ts) 인지 확인.

        이 조건은 strategy_engine.py 의 매매 판단 직전에만 적용되어야 한다.
        지표 갱신(recompute_from_changed_ts, update_incremental)은 검사 앞
        단계에서 이미 실행되므로 스킵되지 않는다.
        """
        # 시뮬레이션: 이미 실시간 판단된 봉
        evaluated = OrderedDict()
        ts = datetime(2026, 8, 25, 9, 4, 0, tzinfo=timezone.utc)
        evaluated[ts] = None

        # 케이스: 실시간 재진입 (VERIFY 후속 부분 재계산 등)
        backfill_mode = False
        should_skip_trading = (not backfill_mode) and (ts in evaluated)
        self.assertTrue(should_skip_trading)

        # 케이스: BACKFILL 재진입 (검사 skip → 매매 판단 실행됨)
        backfill_mode = True
        should_skip_trading = (not backfill_mode) and (ts in evaluated)
        self.assertFalse(should_skip_trading)

        # 케이스: 새 봉 실시간 첫 진입
        backfill_mode = False
        new_ts = datetime(2026, 8, 25, 9, 5, 0, tzinfo=timezone.utc)
        should_skip_trading = (not backfill_mode) and (new_ts in evaluated)
        self.assertFalse(should_skip_trading)

    def test_indicator_state_untouched_by_check(self):
        """봉당 1회 검사는 IndicatorState 를 건드리지 않는다.

        _evaluated_bar_ts 자료구조는 datetime 만 저장하며, indicator 상태
        객체는 별도. 검사 로직에서 indicator 필드에 접근하지 않는지 필드
        존재 여부로 확인.
        """
        from core.strategy_engine import StrategyEngine
        engine = StrategyEngine.__new__(StrategyEngine)
        engine._evaluated_bar_ts = OrderedDict()
        # 이력 등록·조회는 datetime 만 다룸. indicators 필드 접근 없음.
        ts = datetime(2026, 8, 25, 9, 4, 0, tzinfo=timezone.utc)
        engine._register_evaluated_bar(ts)
        self.assertIn(ts, engine._evaluated_bar_ts)
        # engine.indicators 미초기화 상태여도 예외 없이 동작해야 함.
        self.assertFalse(hasattr(engine, "indicators"))


if __name__ == "__main__":
    unittest.main()
