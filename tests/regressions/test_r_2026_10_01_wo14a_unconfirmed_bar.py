"""
✅ WO-14 (a) 회귀: 미확정(형성 중) 봉 BACKFILL 제외 (2026-10-01)

원 결함 (WO-13 (a)):
- 조정 조회 첫 배치가 end_ts 없이 조회(core/rest_reconcile.py 첫 배치 to 없음)해 아직 닫히지 않은 봉을 받아 옴.
- 그 봉이 reconcile_series 에서 inserted → BACKFILL 필터는 closed_ts 만 빼므로 미확정 종가로 평가
  (2026-09-30 16:50:05 16:50 봉, 20:10:05). 발주는 BACKFILL 분기로 막혔지만 감사 행이 남고,
  매도 평가 경로의 update_highest_price 로 Trailing 고점이 갱신될 수 있음.

처방 a-1: BACKFILL 대상에서 closed_ts 보다 늦은 봉 제외 (engine/live_loop.py `_drop_unconfirmed_backfill_ts`).

BACKFILL 대상 선정은 run_live_loop 안 인라인 코드이므로, 본 테스트는 헬퍼 + 실제 reconcile_series 로
같은 순서를 재현하고, 호출 위치는 소스 lint 로 고정한다. 평가 경로는 실제 PositionState 의
update_highest_price 를 호출하는 스텁 엔진으로 대신한다(매도 평가 경로가 부르는 것과 같은 메서드).

실행:
    python3 -m unittest tests.regressions.test_r_2026_10_01_wo14a_unconfirmed_bar -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from core.position_state import PositionState  # noqa: E402
from core.rest_reconcile import reconcile_series  # noqa: E402
from engine.live_loop import _drop_unconfirmed_backfill_ts  # noqa: E402

KST = "Asia/Seoul"


def _bars(start_kst: str, n: int, base: float = 2000.0) -> pd.DataFrame:
    idx = pd.date_range(pd.Timestamp(start_kst, tz=KST), periods=n, freq="5min").tz_convert("UTC")
    close = [base + (int(ts.timestamp()) // 300) % 7 for ts in idx]
    return pd.DataFrame(
        {"Open": close, "High": [c + 3 for c in close], "Low": [c - 3 for c in close],
         "Close": close, "Volume": [100.0] * n},
        index=idx,
    )


def _select_backfill(local, rest, closed_ts, drop_unconfirmed: bool = True):
    """run_live_loop 순서 재현: reconcile_series → closed_ts 제외 → (a) 미확정 제외."""
    merged, diff = reconcile_series(local, rest)
    targets = [ts for ts in diff.get("changed_ts", []) if ts != closed_ts]
    dropped = []
    if drop_unconfirmed:
        targets, dropped = _drop_unconfirmed_backfill_ts(targets, closed_ts)
    return merged, targets, dropped


class _StubEngine:
    """BACKFILL 평가 호출 기록 + 매도 평가 경로처럼 position.update_highest_price(close) 호출."""

    def __init__(self, position):
        self.position = position
        self.evaluated = []

    def on_new_bar_confirmed(self, ts, close, diff):
        self.evaluated.append((ts, diff.get("backfill_mode")))
        self.position.update_highest_price(close)


class TestUnconfirmedBarExcluded(unittest.TestCase):

    def setUp(self):
        # 2026-09-30 16:50:05 재현: 확정 대상 16:45, REST 응답 마지막에 형성 중 16:50 봉 포함
        self.closed_ts = pd.Timestamp("2026-09-30 16:45", tz=KST).tz_convert("UTC")
        self.forming_ts = self.closed_ts + pd.Timedelta(minutes=5)
        # 로컬: 00:35 ~ 16:45(확정 대상 봉 포함)
        self.local = _bars("2026-09-30 00:35", 196)
        self.local = self.local[self.local.index <= self.closed_ts]
        self.rest = _bars("2026-09-30 00:35", len(self.local) + 1)
        assert self.rest.index[-1] == self.forming_ts
        # 형성 중 봉 종가를 기존 고점보다 높게
        self.rest.loc[self.forming_ts, ["Close", "High"]] = [2500.0, 2501.0]

    def _armed_position(self):
        p = PositionState()
        p.has_position = True
        p.avg_price = 2000.0
        p.quantity = 10.0
        p.trailing_armed = True
        p.highest_price = 2100.0
        return p

    def test_0_old_behavior_reproduced(self):
        """(대조) 제외하지 않으면 형성 중 봉이 BACKFILL 대상 — 결함 재현."""
        _, targets, _ = _select_backfill(self.local, self.rest, self.closed_ts, drop_unconfirmed=False)
        self.assertEqual(targets, [self.forming_ts])

    def test_1_forming_bar_not_backfilled(self):
        """REST 응답에 형성 중 봉(closed_ts + 5분)이 있어도 BACKFILL 대상 0, 제외 목록에 그 봉."""
        _, targets, dropped = _select_backfill(self.local, self.rest, self.closed_ts)
        self.assertEqual(targets, [])
        self.assertEqual(dropped, [self.forming_ts])

    def test_2_highest_not_updated_by_forming_close(self):
        """Trailing 무장 + 형성 중 종가 > 기존 고점 → 평가 없음 → highest_price 미갱신."""
        pos = self._armed_position()
        eng = _StubEngine(pos)
        merged, targets, _ = _select_backfill(self.local, self.rest, self.closed_ts)
        for ts in sorted(targets):
            eng.on_new_bar_confirmed(ts, float(merged.loc[ts, "Close"]), {"backfill_mode": True})
        self.assertEqual(pos.highest_price, 2100.0)

        # (대조) 옛 동작이면 고점이 2500 으로 올라감
        pos_old = self._armed_position()
        eng_old = _StubEngine(pos_old)
        merged, targets_old, _ = _select_backfill(self.local, self.rest, self.closed_ts, drop_unconfirmed=False)
        for ts in sorted(targets_old):
            eng_old.on_new_bar_confirmed(ts, float(merged.loc[ts, "Close"]), {"backfill_mode": True})
        self.assertEqual(pos_old.highest_price, 2500.0)

    def test_3_no_eval_call_for_forming_bar(self):
        """형성 중 봉 평가 호출 0 → audit_sell_eval/audit_buy_eval backfill 신규 행·갱신 0
        (backfill_* 기록은 이 평가 호출에서만 생김)."""
        eng = _StubEngine(self._armed_position())
        merged, targets, _ = _select_backfill(self.local, self.rest, self.closed_ts)
        for ts in sorted(targets):
            eng.on_new_bar_confirmed(ts, float(merged.loc[ts, "Close"]), {"backfill_mode": True})
        self.assertEqual([e for e in eng.evaluated if e[0] == self.forming_ts], [])

    def test_4_real_missing_bar_before_closed_still_backfilled(self):
        """확정 대상 봉보다 이른 진짜 누락 봉은 그대로 BACKFILL (기존 동작 유지)."""
        missing = self.local.index[150]
        local = self.local.drop(index=missing)
        _, targets, dropped = _select_backfill(local, self.rest, self.closed_ts)
        self.assertEqual(targets, [missing])
        self.assertEqual(dropped, [self.forming_ts])


class TestCallSiteLint(unittest.TestCase):

    def test_drop_called_right_after_closed_ts_filter(self):
        src = (ROOT / "engine" / "live_loop.py").read_text(encoding="utf-8")
        base = "backfill_ts_list = [ts for ts in changed_ts_list if ts != closed_ts]"
        call = "backfill_ts_list, _unconfirmed_ts = _drop_unconfirmed_backfill_ts(backfill_ts_list, closed_ts)"
        self.assertIn(call, src)
        self.assertIn('f"[BACKFILL] 미확정 봉 제외 | ts={format_kst(_uts)} "', src)
        i_base, i_call = src.index(base), src.index(call)
        self.assertLess(i_base, i_call)
        self.assertLess(i_call - i_base, 300)
        self.assertLess(i_call, src.index("if backfill_ts_list:"))


if __name__ == "__main__":
    unittest.main()
