"""
✅ WO-14 E1 회귀: BACKFILL 재평가가 Trailing 상태를 바꾸지 않음 (2026-10-01)

정책 (2026-10-01 확정):
  BACKFILL 재평가는 지표를 바로잡는 작업이며 포지션 상태를 바꾸지 않는다.
  과거 누락 봉의 가격은 실시간에 보지 못한 가격이므로 Trailing 고점에 반영하지 않는다.

원 결함 (WO-13 확인):
- BACKFILL 백업(engine/live_loop.py)은 지표 직전값만 보존. 매도 평가 경로의
  position.update_highest_price(current_price)(core/strategy_incremental.py on_bar)는 BACKFILL 에서도 실행되어,
  Trailing 무장 상태에서 재평가 봉 종가 > 기존 고점이면 고점이 올라가고 복원되지 않음.

처방: highest_price·highest_since_entry·trailing_armed·trailing_fixed_amount·trailing_activation_price
5개 필드 백업·복원 (`_backup_trailing_state` / `_restore_trailing_state`), 복원 시 INFO 1줄.

BACKFILL 루프는 run_live_loop 안 인라인 코드이므로, 본 테스트는 같은 순서(백업 → 재평가 → 복원)를
헬퍼 + 실제 PositionState 로 재현하고, 호출 위치(백업은 try 밖, 복원은 finally 안)는 소스 lint 로 고정한다.

실행:
    python3 -m unittest tests.regressions.test_r_2026_10_01_wo14e1_backfill_trailing_restore -v
"""
from __future__ import annotations

import logging
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from core.position_state import PositionState  # noqa: E402
from engine.live_loop import (  # noqa: E402
    _BACKFILL_TRAILING_FIELDS,
    _backup_trailing_state,
    _restore_trailing_state,
)


def _position(armed: bool) -> PositionState:
    p = PositionState()
    p.has_position = True
    p.avg_price = 2000.0
    p.quantity = 10.0
    p.trailing_armed = armed
    p.highest_price = 2100.0 if armed else None
    p.trailing_activation_price = 2080.0 if armed else None
    p.trailing_fixed_amount = 50.0 if armed else None
    p.highest_since_entry = 2100.0
    return p


def _snapshot(p):
    return {f: getattr(p, f) for f in _BACKFILL_TRAILING_FIELDS} | {"has_position": p.has_position}


def _run_backfill(position, closes, *, set_position=None):
    """run_live_loop BACKFILL 블록 순서 재현: 백업 → 봉마다 매도 평가 경로(update_highest_price) → 복원."""
    saved = _backup_trailing_state(position)
    try:
        for c in closes:
            position.update_highest_price(c)  # 매도 평가 경로가 부르는 메서드
            if position.highest_since_entry is not None and c > position.highest_since_entry:
                position.highest_since_entry = c
        if set_position is not None:
            set_position(position)
    finally:
        return _restore_trailing_state(position, saved)


class TestBackfillTrailingRestore(unittest.TestCase):

    def test_1_armed_backfill_high_close_restored(self):
        """Trailing 무장 + BACKFILL 종가 > 기존 고점 → 재평가 뒤 고점 원래 값 복원 + 바뀐 내역 반환."""
        p = _position(armed=True)
        before = _snapshot(p)
        changed = _run_backfill(p, [2050.0, 2500.0, 2300.0])
        self.assertEqual(_snapshot(p), before)
        self.assertEqual(p.highest_price, 2100.0)
        self.assertEqual(changed["highest_price"], (2500.0, 2100.0))

        # (대조) 복원 없으면 고점 2500 으로 남음 — 결함 재현
        q = _position(armed=True)
        for c in [2050.0, 2500.0, 2300.0]:
            q.update_highest_price(c)
        self.assertEqual(q.highest_price, 2500.0)

    def test_2_not_armed_no_change(self):
        """무장 전 → 5개 필드 변화 없음, 바뀐 내역 없음(복원 로그 없음)."""
        p = _position(armed=False)
        p.highest_since_entry = None
        before = _snapshot(p)
        changed = _run_backfill(p, [2050.0, 2500.0])
        self.assertEqual(_snapshot(p), before)
        self.assertEqual(changed, {})

    def test_3_realtime_bar_still_updates_high(self):
        """실시간 봉(BACKFILL 아님)은 백업·복원을 거치지 않으므로 고점 갱신 기존대로."""
        p = _position(armed=True)
        p.update_highest_price(2500.0)
        self.assertEqual(p.highest_price, 2500.0)
        # BACKFILL 뒤 실시간 봉도 정상 갱신
        _run_backfill(p, [2600.0])
        self.assertEqual(p.highest_price, 2500.0)
        p.update_highest_price(2550.0)
        self.assertEqual(p.highest_price, 2550.0)

    def test_4_no_position_and_position_change_safe(self):
        """포지션 없음 → 예외 없이 지나감. BACKFILL 중 보유 여부가 바뀌면 덮어쓰지 않고 None."""
        p = PositionState()
        changed = _run_backfill(p, [2500.0])
        self.assertEqual(changed, {})
        self.assertIsNone(p.highest_price)

        q = _position(armed=True)

        def _closed(pos):
            pos.has_position = False
            pos.highest_price = None
            pos.trailing_armed = False

        self.assertIsNone(_run_backfill(q, [2500.0], set_position=_closed))
        self.assertIsNone(q.highest_price)
        self.assertFalse(q.trailing_armed)


class TestCallSiteLint(unittest.TestCase):
    """백업은 try 밖(지표 백업과 같은 자리), 복원은 finally 안 + INFO 로그 문구."""

    def test_backup_outside_try_restore_in_finally(self):
        src = (ROOT / "engine" / "live_loop.py").read_text(encoding="utf-8")
        backup = "saved_trailing = _backup_trailing_state(engine.position)"
        restore = "_trail_changed = _restore_trailing_state(engine.position, saved_trailing)"
        self.assertIn(backup, src)
        self.assertIn(restore, src)
        self.assertIn('f"[BACKFILL] trailing 상태 복원 | {_head}"', src)
        self.assertIn('f"highest {_hp[0]}→{_hp[1]} 되돌림"', src)

        i_saved_ind = src.index("saved_indicators = {")
        i_backup = src.index(backup)
        i_loop = src.index("for ts in sorted(backfill_ts_list):")
        i_finally = src.index("finally:", i_loop)
        i_restore = src.index(restore)
        i_ind_restore = src.index("engine.indicators.ema_fast = saved_indicators['ema_fast']")
        self.assertLess(i_saved_ind, i_backup)
        self.assertLess(i_backup, i_loop)
        # 백업과 루프 사이의 try: 앞에 백업이 있어야 함 (try 밖)
        self.assertLess(i_backup, src.index("try:", i_backup))
        self.assertLess(i_finally, i_restore)
        self.assertLess(i_restore, i_ind_restore)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    unittest.main()
