"""
✅ WO-17 (S) 회귀: 워밍업 긴 이력 증분 시드 (2026-10-01)

원 결함 (WO-15 §1.5, G4 측정 docs/plans/2026-10-01-wo17-recompute-seed/g4-report.md):
- 워밍업 200봉으로 각 EMA 를 마지막 p개 SMA 로 시드 → 기동 시점 (fast−slow) 간격이 장기 기준과 최대 9.3원 차이,
  기동 13회 중 3회 부호 반대, 기동 1(09-02)은 거짓 교차 5건 → 실매매 2왕복 손실(−0.95%, −1.02%).

처방 (S): 워밍업에서 800봉을 받아(WO-16 UTC to, 형성 중 봉은 (W) 로 제거) 첫 200봉 SMA 로 시작해 나머지 증분.
조회 실패·800봉 미만이면 200봉 SMA 폴백 + WARN + 알림 1회. 버퍼·local_series 는 최근 200봉.

실행:
    python3 -m unittest tests.regressions.test_r_2026_10_01_wo17s_long_history_seed -v
"""
from __future__ import annotations

import csv
import random
import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from core.indicator_state import IndicatorState  # noqa: E402
from engine.live_loop import LONG_SEED_BARS, _seed_warmup_indicators, _warmup_trim_forming  # noqa: E402

FIELDS = ("ema_fast", "ema_slow", "ema_base", "ema_fast_buy", "ema_slow_buy", "ema_fast_sell", "ema_slow_sell",
          "ema_macd_fast", "ema_macd_slow", "macd", "signal")


def _ind():
    return IndicatorState(ema_fast=60, ema_slow=200, base_ema=200, use_separate_ema=True,
                          ema_fast_buy=60, ema_slow_buy=200, ema_fast_sell=60, ema_slow_sell=200)


def _walk(n, seed=17, start=700.0):
    rnd = random.Random(seed)
    out, p = [], start
    for _ in range(n):
        p = max(1.0, p + rnd.choice((-3, -2, -1, 0, 1, 2, 3)) + rnd.random() - 0.5)
        out.append(round(p, 2))
    return out


def _state(ind):
    return {f: getattr(ind, f) for f in FIELDS}


def _df(closes, last_utc="2026-10-01 03:40"):
    idx = pd.date_range(end=pd.Timestamp(last_utc, tz="UTC"), periods=len(closes), freq="5min")
    return pd.DataFrame({"Open": closes, "High": closes, "Low": closes, "Close": closes, "Volume": 1.0}, index=idx)


def _long_baseline(closes):
    """장기 기준: 전체 이력의 가장 오래된 200봉 SMA 로 시작해 끝까지 증분 (G4 의 C 와 같은 방식)."""
    ind = _ind()
    assert ind.seed_long_history(closes, base_len=200)
    return ind


class TestLongHistorySeed(unittest.TestCase):

    def test_1_800_within_0_3pct_of_1200_baseline(self):
        """(1) 800봉 시드가 장기 기준과 가깝다 — 합성 데이터(0.3%) + 실데이터 기동 9(0.1원)."""
        # [합성 데이터용] 무작위 걸음 1,200봉: 800봉 시드 EMA200 이 1,200봉 기준과 0.3% 이내, EMA60 은 사실상 같음
        closes = _walk(1200)
        s800 = _ind()
        self.assertTrue(s800.seed_long_history(closes[-800:], base_len=200))
        base = _long_baseline(closes)
        rel = abs(s800.ema_slow_buy - base.ema_slow_buy) / base.ema_slow_buy
        self.assertLess(rel, 0.003, rel)
        self.assertLess(abs(s800.ema_fast_buy - base.ema_fast_buy), 1e-6)

        # [실데이터용] ✅ WO-17 (S2): 기동 9(2026-09-30 16:33:06) 직전 확정 800봉 시드 vs 10,011봉 장기 기준(G4 의 C)
        # 기준값 출처: docs/plans/2026-10-01-wo17-recompute-seed/wo17s_boot9_compare.csv "C G4 장기 기준 (10,011봉)" 행
        cmp_path = ROOT / "docs" / "plans" / "2026-10-01-wo17-recompute-seed" / "wo17s_boot9_compare.csv"
        c_row = next(r for r in csv.reader(open(cmp_path, encoding="utf-8")) if r and r[0].startswith("C G4 장기 기준"))
        c_fast, c_slow = float(c_row[1]), float(c_row[2])
        fx = ROOT / "tests" / "regressions" / "fixtures" / "wo17s_boot9_m5_800.csv"
        real = [float(r["close"]) for r in csv.DictReader(open(fx))]
        ind = _ind()
        _seed_warmup_indicators(ind, _df(real), LONG_SEED_BARS, 200)
        self.assertLess(abs(ind.ema_fast_buy - c_fast), 0.1, (ind.ema_fast_buy, c_fast))
        self.assertLess(abs(ind.ema_slow_buy - c_slow), 0.1, (ind.ema_slow_buy, c_slow))
        # (대조) 옛 방식(200봉 SMA, seed_from_closes)은 같은 자료에서 0.1원을 넘는다 — 실데이터 단언이 결함을 잡는다는 증거
        old = _ind()
        old.seed_from_closes(real[-200:])
        self.assertGreater(max(abs(old.ema_fast_buy - c_fast), abs(old.ema_slow_buy - c_slow)), 0.1)

    def test_2_one_more_bar_equals_incremental(self):
        """(2) 801봉 시드 = 800봉 시드 + 마지막 봉 증분 (같은 시작점) — 시드 계산이 실시간 증분과 같은 식."""
        closes = _walk(801)
        a = _ind()
        a.seed_long_history(closes, base_len=200)
        b = _ind()
        b.seed_long_history(closes[:800], base_len=200)
        b.update_incremental(closes[800])
        sa, sb = _state(a), _state(b)
        for f in FIELDS:
            self.assertAlmostEqual(sa[f], sb[f], places=9, msg=f)
        self.assertIsNone(a.prev_ema_fast_buy)      # 시드 직후 상태 모양 = seed_from_closes
        self.assertEqual(a.bar_count, 0)

    def test_3_with_forming_bar_trim(self):
        """(3) (W) 와 함께: 801봉 수신 + 마지막 형성 중 → 제거 800 → long_history, 버퍼 df = 그 앞 200봉."""
        closes = _walk(801)
        df = _df(closes)
        now = pd.Timestamp("2026-10-01 03:42:08", tz="UTC")
        trimmed, action, _, _ = _warmup_trim_forming(df, 300, now, 200)
        self.assertEqual(action, "dropped")
        self.assertEqual(len(trimmed), 800)
        ind = _ind()
        ok, mode, reason, buf = _seed_warmup_indicators(ind, trimmed, LONG_SEED_BARS, 200)
        self.assertEqual((ok, mode, reason), (True, "long_history", ""))
        self.assertEqual(len(buf), 200)
        self.assertEqual(buf.index[-1], df.index[-2])
        ref = _ind()
        ref.seed_long_history(closes[:800], base_len=200)
        self.assertEqual(_state(ind), _state(ref))

    def test_4_fallback_insufficient_and_lint(self):
        """(4) 800봉 미만(부분 수신) → 200봉 SMA 폴백 + 사유. live_loop 는 WARN·알림·폴백 요청 경로를 가짐."""
        closes = _walk(650)
        ind = _ind()
        ok, mode, reason, buf = _seed_warmup_indicators(ind, _df(closes), LONG_SEED_BARS, 200)
        self.assertEqual((ok, mode), (True, "sma200"))
        self.assertEqual(reason, "insufficient_bars(650<800)")
        self.assertEqual(len(buf), 200)
        ref = _ind()
        ref.seed_from_closes(closes[-200:])
        self.assertEqual(_state(ind), _state(ref))
        src = (ROOT / "engine" / "live_loop.py").read_text(encoding="utf-8")
        self.assertIn('f"[WARMUP] 긴 이력 시드 실패 → 200봉 SMA 폴백 | 사유={_why}"', src)
        self.assertIn('f"[WARMUP] 시드 방식=sma200 bars={len(initial_df)}"', src)
        self.assertIn('f"[WARMUP] 시드 방식=long_history bars={_long_bars} "', src)
        self.assertIn('warmup_request = (_long_bars + 1) if attempt == 1 else (min_hist + 1)', src)
        self.assertIn('_seed_fallback_reason = "fetch_failed"', src)
        self.assertIn('dedupe_key=f"warmup_seed_fallback:{user_id}:{params.upbit_ticker}"', src)

    def test_5_g4_boot9_reproduces_B(self):
        """(5) G4 기동 9(2026-09-30 16:33:06) 직전 확정 800봉으로 재현 → G4 B 값 756.8929 / 757.5385 와 일치."""
        path = ROOT / "tests" / "regressions" / "fixtures" / "wo17s_boot9_m5_800.csv"
        closes = [float(r["close"]) for r in csv.DictReader(open(path))]
        self.assertEqual(len(closes), 800)
        ind = _ind()
        ok, mode, _, _ = _seed_warmup_indicators(ind, _df(closes), LONG_SEED_BARS, 200)
        self.assertEqual(mode, "long_history")
        self.assertEqual(round(ind.ema_fast_buy, 4), 756.8929)
        self.assertEqual(round(ind.ema_slow_buy, 4), 757.5385)
        self.assertLess(ind.ema_fast_buy - ind.ema_slow_buy, 0)   # 장기 기준과 같은 역배열 (현행 A 는 +3.26 정배열)

    def test_6_fallback_identical_to_old(self):
        """(6) 폴백은 현행과 완전 동일: 200·201봉 수신이면 지표·버퍼 df 모두 옛 seed_from_closes 경로와 같음."""
        for n in (200, 201):
            closes = _walk(n, seed=n)
            df = _df(closes)
            ind = _ind()
            ok, mode, _, buf = _seed_warmup_indicators(ind, df, LONG_SEED_BARS, 200)
            old = _ind()
            old.seed_from_closes(closes)
            self.assertEqual(mode, "sma200")
            self.assertEqual(_state(ind), _state(old))
            self.assertIs(buf, df)


if __name__ == "__main__":
    unittest.main()
