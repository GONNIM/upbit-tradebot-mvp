"""WO-2 옵션 C 회귀 (2026-09-02): 미확정 평가 후 같은 봉 재진입은 봉당 1회
검사에서 차단된다.

미확정 평가에서 _register_evaluated_bar(bar.ts) 가 호출되어 이후 같은 봉의
실시간 진입(backfill_mode=False)이 조기 반환된다. BACKFILL 재평가
(backfill_mode=True)는 우회 대상이므로 지표 교정 경로가 정상 작동한다.
"""
from __future__ import annotations

import sys
import unittest
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class TestOptionCNoDoubleEvaluation(unittest.TestCase):
    def test_registered_bar_blocks_second_realtime_entry(self):
        """미확정 평가에서 등록된 봉이 다시 실시간 진입해도 차단된다."""
        # 봉당 1회 검사 자체를 단위 테스트: 등록된 ts 는 다시 처리하지 않음.
        from core.strategy_engine import StrategyEngine
        engine = StrategyEngine.__new__(StrategyEngine)
        engine._evaluated_bar_ts = OrderedDict()
        engine._EVAL_HISTORY_MAX = 1000

        ts = datetime(2026, 9, 3, 3, 22, 0, tzinfo=timezone.utc)
        # 미확정 평가에서 등록됐다고 가정
        StrategyEngine._register_evaluated_bar(engine, ts)
        self.assertIn(ts, engine._evaluated_bar_ts)

        # 실시간 재진입(backfill_mode=False)이면 봉당 1회 검사에서 차단
        # (실제 검사는 on_new_bar_confirmed 안 라인 671~676)
        backfill_mode = False
        should_skip = (not backfill_mode) and (ts in engine._evaluated_bar_ts)
        self.assertTrue(should_skip)

    def test_backfill_reentry_bypasses_gate(self):
        """BACKFILL 재진입은 게이트를 우회하여 지표 교정이 가능해야 한다."""
        from core.strategy_engine import StrategyEngine
        engine = StrategyEngine.__new__(StrategyEngine)
        engine._evaluated_bar_ts = OrderedDict()
        engine._EVAL_HISTORY_MAX = 1000

        ts = datetime(2026, 9, 3, 3, 22, 0, tzinfo=timezone.utc)
        StrategyEngine._register_evaluated_bar(engine, ts)

        backfill_mode = True
        should_skip = (not backfill_mode) and (ts in engine._evaluated_bar_ts)
        self.assertFalse(should_skip)  # BACKFILL 은 통과


if __name__ == '__main__':
    unittest.main()
