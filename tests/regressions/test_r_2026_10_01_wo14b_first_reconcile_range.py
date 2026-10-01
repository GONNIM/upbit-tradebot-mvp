"""
✅ WO-14 (b) 회귀: 첫 조정 조회 범위 정합 (2026-10-01)

원 결함 (WO-13 (b)):
- 기동 때 로컬 시계열은 워밍업 200봉(2026-09-30 00:35~18:00 KST)인데 첫 조정은 400봉 요청·298봉 수신
  (2026-09-29 16:30~). 로컬 시작 이전 98봉이 reconcile_series 에서 inserted → 97봉 BACKFILL
  (2026-09-30 18:10:11). 기동마다 92~116봉 재평가, 부팅 복원 직후 "보유" 상태로 재평가되어
  미보유 구간 audit_sell_eval 35행 생성.

처방 b-2: reconcile_series 호출 직전에 rest_df 를 로컬 시작 시각 이후로 자름
(engine/live_loop.py `_trim_rest_before_local_start`).

BACKFILL 대상 선정은 run_live_loop 안 인라인 코드이므로, 본 테스트는 헬퍼 + 실제 reconcile_series 로
같은 순서(자름 → reconcile → closed_ts 제외)를 재현하고, 호출 위치는 소스 lint 로 고정한다.

실행:
    python3 -m unittest tests.regressions.test_r_2026_10_01_wo14b_first_reconcile_range -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from core.rest_reconcile import reconcile_series  # noqa: E402
from engine.live_loop import _trim_rest_before_local_start  # noqa: E402

KST = "Asia/Seoul"


def _bars(start_kst: str, n: int, base: float = 2000.0) -> pd.DataFrame:
    idx = pd.date_range(pd.Timestamp(start_kst, tz=KST), periods=n, freq="5min").tz_convert("UTC")
    # 같은 시각이면 같은 종가 (로컬·REST 겹치는 봉은 변경 없음)
    close = [base + (int(ts.timestamp()) // 300) % 7 for ts in idx]
    return pd.DataFrame(
        {"Open": close, "High": [c + 3 for c in close], "Low": [c - 3 for c in close],
         "Close": close, "Volume": [100.0] * n},
        index=idx,
    )


def _ts(kst: str) -> pd.Timestamp:
    return pd.Timestamp(kst, tz=KST).tz_convert("UTC")


def _select_backfill(local: pd.DataFrame, rest: pd.DataFrame, closed_ts, trim: bool = True):
    """run_live_loop 조정 블록 순서 재현: (b) 자름 → reconcile_series → closed_ts 제외 (live_loop.py)."""
    n_cut = 0
    if trim:
        rest, n_cut = _trim_rest_before_local_start(local, rest)
    merged, diff = reconcile_series(local, rest)
    targets = [ts for ts in diff.get("changed_ts", []) if ts != closed_ts]
    return merged, targets, n_cut


class TestFirstReconcileRange(unittest.TestCase):

    def setUp(self):
        # 2026-09-30 18:02 기동 범위 성질 재현: 로컬 워밍업 200봉(시작 00:35, 연속 5분봉),
        # 마지막 로컬 봉 바로 다음 봉이 확정 대상 봉(closed_ts).
        # (실측 로컬은 00:35~18:00 이며 무거래 봉이 빠져 있어 끝 시각이 다르다)
        self.local = _bars("2026-09-30 00:35", 200)
        last_local = self.local.index[-1]
        self.closed_ts = last_local + pd.Timedelta(minutes=5)
        # REST 298봉: 전날 16:30 부터 확정 대상 봉(closed_ts)까지
        n_rest = int((self.closed_ts - _ts("2026-09-29 16:30")) / pd.Timedelta(minutes=5)) + 1
        self.rest = _bars("2026-09-29 16:30", n_rest)
        assert self.rest.index[-1] == self.closed_ts

    def test_0_old_behavior_reproduced_without_trim(self):
        """(대조) 자르지 않으면 로컬 시작 이전 봉이 전부 BACKFILL 대상 — 결함 재현."""
        _, targets, _ = _select_backfill(self.local, self.rest, self.closed_ts, trim=False)
        n_before = int((self.rest.index < self.local.index[0]).sum())
        self.assertGreater(n_before, 90)
        self.assertEqual(len(targets), n_before)

    def test_1_first_reconcile_backfill_zero(self):
        """로컬 200봉 + REST(전날 16:30~) → BACKFILL 대상 0 (새 봉은 확정 대상 봉이라 제외).
        이어지는 두 번째 조정(다시 넓게 조회)도 0 — b-1 이 아닌 b-2 를 고른 이유."""
        merged, targets, n_cut = _select_backfill(self.local, self.rest, self.closed_ts)
        self.assertEqual(targets, [])
        self.assertEqual(n_cut, int((self.rest.index < self.local.index[0]).sum()))
        self.assertEqual(merged.index[0], self.local.index[0])

        closed2 = self.closed_ts + pd.Timedelta(minutes=5)
        n_rest2 = int((closed2 - _ts("2026-09-29 16:35")) / pd.Timedelta(minutes=5)) + 1
        rest2 = _bars("2026-09-29 16:35", n_rest2)
        _, targets2, _ = _select_backfill(merged, rest2, closed2)
        self.assertEqual(targets2, [])

    def test_2_held_position_no_eval_before_local_start(self):
        """부팅 복원 직후 보유 상태 — 로컬 시작 이전 봉에 대한 BACKFILL 평가 호출 0.
        audit_sell_eval 의 backfill 행은 이 평가 호출(on_new_bar_confirmed backfill_mode=True)에서만
        생기므로 평가 호출 0 = 보유 전 구간 신규 행 0."""
        evaluated = []

        class _Pos:
            has_position = True  # 부팅 복원 직후

        class _StubEngine:
            position = _Pos()

            def on_new_bar_confirmed(self, bar_ts, series, diff):
                evaluated.append((bar_ts, diff.get("backfill_mode"), self.position.has_position))

        eng = _StubEngine()
        merged, targets, _ = _select_backfill(self.local, self.rest, self.closed_ts)
        for ts in sorted(targets):
            eng.on_new_bar_confirmed(ts, merged, {"backfill_mode": True})
        before_start = [e for e in evaluated if e[0] < self.local.index[0]]
        self.assertEqual(before_start, [])
        self.assertEqual(evaluated, [])

    def test_3_real_missing_bar_inside_local_range_still_backfilled(self):
        """로컬 범위 안의 진짜 누락 봉(한 봉 제거)은 그대로 BACKFILL 1."""
        missing = self.local.index[100]
        local = self.local.drop(index=missing)
        _, targets, _ = _select_backfill(local, self.rest, self.closed_ts)
        self.assertEqual(targets, [missing])

    def test_4_empty_local_not_trimmed(self):
        """로컬이 빈 경우 자르지 않음 (기존 동작)."""
        empty = pd.DataFrame(columns=self.rest.columns)
        kept, n_cut = _trim_rest_before_local_start(empty, self.rest)
        self.assertIs(kept, self.rest)
        self.assertEqual(n_cut, 0)
        kept_none, n_none = _trim_rest_before_local_start(self.local, None)
        self.assertIsNone(kept_none)
        self.assertEqual(n_none, 0)


class TestCallSiteLint(unittest.TestCase):
    """run_live_loop 안에서 reconcile_series 직전에 자르고, 자른 경우 INFO 1줄을 남기는지."""

    def test_trim_called_right_before_reconcile(self):
        src = (ROOT / "engine" / "live_loop.py").read_text(encoding="utf-8")
        call = "rest_df, _n_before_local = _trim_rest_before_local_start(local_series, rest_df)"
        rec = "merged, diff_summary = reconcile_series(local_series, rest_df)"
        self.assertIn(call, src)
        self.assertIn('f"[RECONCILE] 로컬 시작 이전 봉 제외 | n={_n_before_local} "', src)
        i_call, i_rec = src.index(call), src.index(rec)
        self.assertLess(i_call, i_rec)
        self.assertLess(i_rec - i_call, 600, "자름과 reconcile_series 호출 사이가 멀어짐")


if __name__ == "__main__":
    unittest.main()
