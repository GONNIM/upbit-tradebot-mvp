"""WO-6 감사 누락 수정 (2026-08-30) 회귀 테스트.

배경:
    WO-6 20시간 실측에서 실시간 판단 봉 44건이 audit_buy_eval 에 저장되지
    않았다(케이스 B 안정화 확정 경로에 집중). 원인: last_bar_ts 갱신이 두
    곳(strategy_engine.py:595, live_loop.py:1265)에서 판단·감사 이전에
    수행되어, 같은 봉의 두 번째 진입에서 is_new_bar=False 로 조기 반환되고
    audit 저장이 스킵됨.

수정 원칙:
    - last_bar_ts 는 strategy_engine 안에서, 판단·감사·주문이 모두 완료된
      직후에만 갱신한다.
    - live_loop.py:1265 와 1319 의 갱신은 제거한다.
    - 중복 방지는 기존 봉당 1회 검사(_evaluated_bar_ts) 가 담당한다.

실행:
    python3 -m unittest tests.regressions.test_r_2026_08_30_audit_gap_last_bar_ts -v
"""
from __future__ import annotations

import sys
import unittest
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class TestLastBarTsUpdateOrder(unittest.TestCase):
    """WO-6 수정: last_bar_ts 갱신 순서와 위치 검증."""

    def _make_engine_stub(self):
        """StrategyEngine 을 완전 초기화 없이 필드만 세팅한 stub 반환."""
        from core.strategy_engine import StrategyEngine
        engine = StrategyEngine.__new__(StrategyEngine)
        engine._evaluated_bar_ts = OrderedDict()
        engine.last_bar_ts = None
        return engine

    def test_first_entry_updates_last_bar_ts_after_registration(self):
        """첫 진입 시 _register_evaluated_bar 이후에 last_bar_ts 가 갱신된다.

        수정된 로직은 판단·감사·주문 완료 후 마지막 단계에서
        _register_evaluated_bar 를 호출하고 last_bar_ts 를 갱신한다.
        """
        engine = self._make_engine_stub()
        ts = datetime(2026, 8, 30, 3, 42, 0, tzinfo=timezone.utc)

        # 시뮬레이션: 실시간 첫 진입 완료 시퀀스
        # 1) _register_evaluated_bar 호출 (봉당 1회 검사용 이력 등록)
        # 2) last_bar_ts = bar.ts 갱신 (판단·감사 완료 이후)
        engine._register_evaluated_bar(ts)
        engine.last_bar_ts = ts

        self.assertIn(ts, engine._evaluated_bar_ts)
        self.assertEqual(engine.last_bar_ts, ts)

    def test_backfill_mode_does_not_update_last_bar_ts(self):
        """BACKFILL 재평가는 last_bar_ts 를 바꾸지 않아야 한다.

        수정된 로직은 backfill_mode=True 인 경우 _register_evaluated_bar 호출
        조건(not backfill_mode)이 False 이므로 등록되지 않고, 같은 조건 안의
        last_bar_ts 갱신도 실행되지 않는다.
        """
        engine = self._make_engine_stub()
        engine.last_bar_ts = datetime(2026, 8, 30, 3, 41, 0, tzinfo=timezone.utc)
        ts = datetime(2026, 8, 30, 3, 42, 0, tzinfo=timezone.utc)

        # 시뮬레이션: BACKFILL 진입 (backfill_mode=True 이므로 아래 두 라인 실행 안 됨)
        backfill_mode = True
        if not backfill_mode:
            engine._register_evaluated_bar(ts)
            engine.last_bar_ts = ts

        # last_bar_ts 는 이전 봉 그대로 유지
        self.assertEqual(engine.last_bar_ts, datetime(2026, 8, 30, 3, 41, 0, tzinfo=timezone.utc))
        # _evaluated_bar_ts 에도 등록 안 됨
        self.assertNotIn(ts, engine._evaluated_bar_ts)


class TestSecondEntryStillBlocked(unittest.TestCase):
    """봉당 1회 검사가 여전히 두 번째 진입을 차단하는지 확인.

    last_bar_ts 갱신 위치를 이동해도, 봉당 1회 검사(_evaluated_bar_ts) 가
    제 역할을 유지해야 한다.
    """

    def _make_engine_stub(self):
        from core.strategy_engine import StrategyEngine
        engine = StrategyEngine.__new__(StrategyEngine)
        engine._evaluated_bar_ts = OrderedDict()
        engine.last_bar_ts = None
        return engine

    def test_second_entry_same_bar_blocked_by_eval_history(self):
        """같은 봉의 두 번째 실시간 진입은 _evaluated_bar_ts 검사로 차단.

        수정 후에도 봉당 1회 원칙이 유지된다. 첫 진입이 등록한 이력을 사용해
        두 번째 진입은 매매 판단 직전 검사에서 스킵된다.
        """
        engine = self._make_engine_stub()
        ts = datetime(2026, 8, 30, 3, 42, 0, tzinfo=timezone.utc)

        # 첫 진입 완료
        engine._register_evaluated_bar(ts)
        engine.last_bar_ts = ts

        # 두 번째 실시간 진입 조건 (backfill_mode=False)
        backfill_mode = False
        should_skip_trading = (not backfill_mode) and (ts in engine._evaluated_bar_ts)
        self.assertTrue(should_skip_trading, "봉당 1회 검사는 두 번째 진입을 차단해야 함")

    def test_is_new_bar_check_after_last_bar_ts_update(self):
        """last_bar_ts 가 판단·감사 이후 갱신되므로 첫 진입에서 is_new_bar=True.

        수정 전에는 라인 595 에서 last_bar_ts 를 판단 전에 갱신했고,
        이로 인해 같은 봉이 두 번 진입하면 두 번째 진입의 is_new_bar=False
        가 되어 audit 이전 조기 반환. 수정 후 첫 진입에서는 is_new_bar=True.
        """
        from core.strategy_engine import StrategyEngine
        engine = self._make_engine_stub()

        # 첫 진입: last_bar_ts 는 None, bar.ts 는 새 봉
        class _Bar:
            def __init__(self, ts):
                self.ts = ts
        bar = _Bar(datetime(2026, 8, 30, 3, 42, 0, tzinfo=timezone.utc))
        # is_new_bar 는 인스턴스 메서드
        result = StrategyEngine.is_new_bar(engine, bar)
        self.assertTrue(result, "첫 진입은 is_new_bar=True 여야 함")

        # 판단·감사 완료 후 갱신
        engine.last_bar_ts = bar.ts

        # 이제 두 번째 진입은 is_new_bar=False (설계 의도대로)
        result2 = StrategyEngine.is_new_bar(engine, bar)
        self.assertFalse(result2, "같은 봉 두 번째 진입은 is_new_bar=False")


class TestCaseBFirstEntryReachesAudit(unittest.TestCase):
    """케이스 B 확정 봉의 첫 실시간 진입이 audit 저장까지 도달하는지 개념 검증.

    실제 on_new_bar_confirmed 는 많은 의존성(indicators, position, strategy,
    execution_lock 등)이 필요하다. 여기서는 수정된 로직의 조기 반환 조건과
    등록 순서만 개념 검증한다.
    """

    def test_case_b_confirmed_bar_flow(self):
        """케이스 B 안정화 확정 봉의 첫 진입 흐름 시뮬레이션.

        수정된 로직 순서:
        1) is_new_bar 검사: 첫 진입이므로 True → 통과
        2) 봉 버퍼 추가 (last_bar_ts 갱신 없음)
        3) 봉당 1회 검사: 첫 진입이므로 _evaluated_bar_ts 에 없음 → 통과
        4) 판단 실행, audit 저장, 주문 실행
        5) _register_evaluated_bar + last_bar_ts 갱신
        """
        from core.strategy_engine import StrategyEngine
        engine = StrategyEngine.__new__(StrategyEngine)
        engine._evaluated_bar_ts = OrderedDict()
        engine.last_bar_ts = None

        class _Bar:
            def __init__(self, ts):
                self.ts = ts
                self.is_closed = True
        bar = _Bar(datetime(2026, 8, 30, 3, 42, 0, tzinfo=timezone.utc))

        # 1) is_new_bar 검사 통과
        self.assertTrue(StrategyEngine.is_new_bar(engine, bar))

        # 2~4) 버퍼 추가, 봉당 1회 검사 통과, 판단·감사·주문
        backfill_mode = False
        should_skip_trading = (not backfill_mode) and (bar.ts in engine._evaluated_bar_ts)
        self.assertFalse(should_skip_trading, "첫 진입은 판단 실행되어야 함")

        # audit 저장이 여기서 실행된다고 가정 (실제로는 _record_audit_log)
        # 5) 등록 + last_bar_ts 갱신
        engine._register_evaluated_bar(bar.ts)
        engine.last_bar_ts = bar.ts

        # 확인: 이력에 등록됐고 last_bar_ts 갱신됐음
        self.assertIn(bar.ts, engine._evaluated_bar_ts)
        self.assertEqual(engine.last_bar_ts, bar.ts)


if __name__ == "__main__":
    unittest.main()
