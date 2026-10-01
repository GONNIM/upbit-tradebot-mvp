"""
✅ WO-16 (W) 회귀: 워밍업 마지막 봉을 시각으로 판정 (2026-10-01)

원 결함 (WO-15):
- 워밍업은 받은 봉 수 > min_hist 일 때만 마지막 봉을 제거. REST to 결함으로 늘 200(=min_hist)만 받아
  형성 중 봉이 지표 시드에 들어감 (journal 워밍업 13회 중 7회, 10-01 11:40 봉 729 → 확정 733).

처방: 마지막 봉 시각 + 봉 간격 > 지금 이면 형성 중으로 보고 제거, 확정 봉은 유지.
안전장치(F2): 제거하면 min_hist 미만이면 제거하지 않고 경고 (R 없이도 기동 오류 없음).

실행:
    python3 -m unittest tests.regressions.test_r_2026_10_01_wo16w_warmup_forming_trim -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from engine.live_loop import _warmup_trim_forming  # noqa: E402

MIN_HIST = 200


def _df(last_utc: str, n: int) -> pd.DataFrame:
    idx = pd.date_range(end=pd.Timestamp(last_utc, tz="UTC"), periods=n, freq="5min")
    return pd.DataFrame({"Close": range(n)}, index=idx)


class TestWarmupTrim(unittest.TestCase):

    def test_1_201_forming_dropped_to_200(self):
        """① 201 수신 + 마지막 봉 형성 중(시작 128초 뒤) → 제거 → 200."""
        df = _df("2026-10-01 02:40", 201)
        now = pd.Timestamp("2026-10-01 02:42:08", tz="UTC")
        out, action, last, elapsed = _warmup_trim_forming(df, 300, now, MIN_HIST)
        self.assertEqual(action, "dropped")
        self.assertEqual(len(out), 200)
        self.assertEqual(out.index[-1], df.index[-2])
        self.assertEqual(last, df.index[-1])
        self.assertEqual(elapsed, 128)

    def test_2_201_confirmed_kept(self):
        """② 201 수신 + 마지막 봉 확정(현재 봉 거래 없음, 봉 간격 이상 경과) → 201 유지."""
        df = _df("2026-10-01 02:40", 201)
        for now in ("2026-10-01 02:45:00", "2026-10-01 02:46:56"):       # 경계(정확히 봉 간격) 포함
            out, action, _, _ = _warmup_trim_forming(df, 300, pd.Timestamp(now, tz="UTC"), MIN_HIST)
            self.assertEqual(action, "kept_confirmed", now)
            self.assertEqual(len(out), 201)

    def test_3_200_forming_kept_with_warning_no_crash(self):
        """③ 200 수신(= R 없음) + 형성 중 → 제거하지 않음(기동 오류 없음, F2)."""
        df = _df("2026-10-01 02:40", 200)
        out, action, _, _ = _warmup_trim_forming(df, 300, pd.Timestamp("2026-10-01 02:42:08", tz="UTC"), MIN_HIST)
        self.assertEqual(action, "kept_insufficient")
        self.assertEqual(len(out), 200)

    def test_4_call_site_and_logs(self):
        """run_live_loop 워밍업이 헬퍼를 쓰고 세 가지 로그를 남기며, 옛 '여유분 없음' 분기는 사라짐."""
        src = (ROOT / "engine" / "live_loop.py").read_text(encoding="utf-8")
        self.assertIn("initial_df, _wu_action, _wu_last, _wu_elapsed = _warmup_trim_forming(", src)
        for s in ("[WARMUP] 형성 중 봉 제거 |", "[WARMUP] 마지막 봉 확정 (유지) |", "[WARMUP] 형성 중 봉 유지 (봉 수 부족) |"):
            self.assertIn(s, src)
        self.assertNotIn("마지막 봉 유지 (여유분 없음)", src)
        i_trim = src.index("_warmup_trim_forming(\n")
        self.assertLess(i_trim, src.index("indicators.seed_from_closes(closes)"))


if __name__ == "__main__":
    unittest.main()
