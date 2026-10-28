"""
2차 T10: 새 전략(PULLBACK) 원본 일치 시험 — 업비트 확정 봉 3세트 × 조합 9개 = 27건.

계획 `docs/specs/v2-dashboard/plan-phase2.md` 「### T10:」 「일치 시험 설계」:
- 기준값: 원본 백테스터 스크립트(HTML 143~938행)를 그대로 돌린 출력을 `tests/fixtures/pullback/expected/` 에 고정
  (`node tests/v2/js/pullback_reference.mjs --write-expected`, 고정 확인은 `tests/v2/js/pullback_reference.test.mjs`).
- 비교: 같은 봉 배열을 IncrementalPullbackStrategy 에 첫 봉부터 한 봉씩(실시간 경로 on_bar + 실제 보유 객체) 넣는다.
  가짜 체결은 신호 다음 봉 시가로 notional/px 만큼 채운다(원본 px = nb.o, notional = 배분 기준/분할 수,
  평단 = cost/qty, 복리 = 원본 closePosition 의 손익 식). 매수·매도 목록(봉 시각·회차·사유)이 완전히 같아야 한다.
- 빼는 것(차이 기록만): 체결가·수수료·최소 주문금액·잔고 부족 건너뜀(가짜 체결엔 없음), 마지막 봉의 매수 신호
  (원본은 i+1 < bars.length 일 때만 삼 — 원본 325·348행).
- 빈 봉(무거래 봉)은 채우지 않는다(F6) — 엔진·원본 모두 받은 배열 그대로.
- 거래 시간 제한은 꺼짐(기본, T9 넘김).
- node 가 없어도 돈다(고정 파일만 읽음).

실행:
    TELEGRAM_BOT_TOKEN= TELEGRAM_CHAT_ID= python3 -m unittest tests.regressions.test_r_2026_10_28_p3_t10_parity -v
"""
from __future__ import annotations

import json
import logging
import re
import subprocess
import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from core.candle_buffer import Bar  # noqa: E402
from core.strategy_action import Action  # noqa: E402
from core import strategy_pullback as sp  # noqa: E402
from tests.regressions import baseline_commits as bc  # noqa: E402

PB_DIR = ROOT / "tests" / "fixtures" / "pullback"
FIXTURES = ("upbit_a", "upbit_b", "upbit_c")
CFG_NAMES = ("base", "golden_no", "golden_only", "pb_lt_splits", "slope_drop",
             "deadcross_no", "compounding_yes", "sma", "splits_full_armed")

_cache: dict = {}


def load_fixture(name: str) -> dict:
    if name not in _cache:
        _cache[name] = json.loads((PB_DIR / f"{name}.json").read_text(encoding="utf-8"))
    return _cache[name]


def load_cfgs() -> dict:
    return json.loads((PB_DIR / "cfgs.json").read_text(encoding="utf-8"))


def load_expected(fixture: str, cfg: str) -> dict:
    return json.loads((PB_DIR / "expected" / f"{fixture}__{cfg}.json").read_text(encoding="utf-8"))


def js_cfg(name: str, cfgs: dict | None = None) -> dict:
    cfgs = cfgs or load_cfgs()
    return {**cfgs["base"], **cfgs["cfgs"][name]}


def py_params(js: dict, fixture: dict) -> dict:
    """원본 cfg 모양 → 전략 적용본 모양(18키, deadcross·compounding bool)."""
    meta = fixture["meta"]
    p = {k: js[k] for k in ("maType", "ma60p", "ma200p", "pullbackP", "slopeLB", "minSlope", "slopeDrop",
                            "buyOnGoldenCross", "maxSplits", "maxPullbackBuys", "tp", "sl", "capital", "fee")}
    p["deadcross"] = js["deadcross"] == "yes"
    p["compounding"] = js["compounding"] == "yes"
    p["ticker"] = meta["market"]
    p["interval"] = f"minute{int(meta['unit_min'])}"
    return p


def bars_of(fixture: dict) -> list:
    """업비트 확정 봉(t = 봉 시작 UTC ms) → 엔진 Bar(ts UTC, 확정)."""
    out = []
    for b in fixture["bars"]:
        out.append(Bar(ts=pd.Timestamp(int(b["t"]), unit="ms", tz="UTC"), open=float(b["o"]), high=float(b["h"]),
                       low=float(b["l"]), close=float(b["c"]), volume=float(b.get("v", 1.0)),
                       is_closed=True, is_confirmed=True, source="REST_RECONCILED"))
    return out


def ms(ts) -> int:
    return int(pd.Timestamp(ts).value // 1_000_000)


class SimPosition:
    """원본 simulate 의 qty·cost 를 그대로 따라가는 실제 보유 대역(on_bar position 인자)."""

    def __init__(self):
        self.qty = 0.0
        self.cost = 0.0
        self.entry_fees = 0.0

    @property
    def has_position(self) -> bool:
        return self.qty > 0

    @property
    def avg_price(self):
        return self.cost / self.qty if self.qty > 0 else None


class SimFill:
    """가짜 trader: 신호 봉 i 의 매수는 봉 i+1 시가로 채움(원본 nb.o). 매도는 원본 closePosition 가격·손익."""

    def __init__(self, params: dict):
        self.p = params
        golden_only = params["buyOnGoldenCross"] and int(params["maxSplits"]) == 0
        self.sum_w = 1 if golden_only else int(params["maxSplits"])
        self.equity = float(params["capital"])
        self.pos = SimPosition()
        self.pending = None   # 다음 봉 시가에 채울 notional

    def before_bar(self, bar) -> None:
        if self.pending is not None:
            notional = self.pending
            self.pos.qty += notional / bar.open
            self.pos.cost += notional
            self.pos.entry_fees += notional * self.p["fee"] / 100
            self.pending = None

    def buy(self) -> None:
        base = self.equity if self.p["compounding"] else float(self.p["capital"])
        self.pending = base / self.sum_w

    def sell(self, bar, reason: str) -> None:
        pos = self.pos
        avg = pos.cost / pos.qty
        price = {"TP": avg * (1 + self.p["tp"] / 100), "SL": avg * (1 - self.p["sl"] / 100)}.get(reason, bar.close)
        gross = pos.qty * price
        self.equity += gross - pos.cost - pos.entry_fees - gross * self.p["fee"] / 100
        pos.qty = pos.cost = pos.entry_fees = 0.0


def run_strategy(params: dict, bars: list, *, st=None, fill=None, start: int = 0, stop: int | None = None,
                 interval_min: int = 3):
    """봉 배열을 실시간 경로(on_bar + 실제 보유)로 넣는다. 반환 (buys, sells, st, fill).
    buys = [(signal_bar_t, fill_bar_t, round, trigger)] (마지막 봉 신호 제외), sells = [(bar_t, type, entries)]."""
    st = st or sp.IncrementalPullbackStrategy("t10", params["ticker"], params, interval_min)
    fill = fill or SimFill(params)
    n = len(bars)
    stop = n if stop is None else stop
    buys, sells = [], []
    for i in range(start, stop):
        b = bars[i]
        fill.before_bar(b)
        a = st.on_bar(b, {}, fill.pos, i)
        if a is Action.BUY:
            if i + 1 < n:
                buys.append((ms(b.ts), ms(bars[i + 1].ts), st.last_eval["split_round"], st.last_buy_reason))
                fill.buy()
        elif a is Action.SELL:
            sells.append((ms(b.ts), st.last_sell_reason, st.last_eval["exit_round"]))
            fill.sell(b, st.last_sell_reason)
    return buys, sells, st, fill


def expected_lists(exp: dict):
    buys = [(x["signal_bar_t"], x["fill_bar_t"], x["round"], x["trigger"]) for x in exp["buys"]]
    sells = [(x["bar_t"], x["type"], x["entries"]) for x in exp["sells"]]
    return buys, sells


def first_diff(a: list, b: list):
    for k, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return k, x, y
    if len(a) != len(b):
        k = min(len(a), len(b))
        return k, (a[k] if k < len(a) else None), (b[k] if k < len(b) else None)
    return None


class _Quiet:
    def __enter__(self):
        self._lv = logging.root.manager.disable
        logging.disable(logging.WARNING)
        return self

    def __exit__(self, *a):
        logging.disable(self._lv)


class TestParity(unittest.TestCase):
    """test_parity_<fixture>_<cfg> 27개 (아래에서 만든다)."""

    def check(self, fixture: str, cfg: str):
        fx = load_fixture(fixture)
        exp = load_expected(fixture, cfg)
        self.assertEqual(exp["meta"]["bar_count"], len(fx["bars"]))
        params = py_params(js_cfg(cfg), fx)
        with _Quiet():
            buys, sells, _, _ = run_strategy(params, bars_of(fx), interval_min=int(fx["meta"]["unit_min"]))
        eb, es = expected_lists(exp)
        self.assertGreaterEqual(len(eb), 1, "기준값 매수 0 — fixture 다시 고르기")
        self.assertGreaterEqual(len(es), 1, "기준값 매도 0 — fixture 다시 고르기")
        self.assertEqual(buys, eb, f"매수 첫 차이 {first_diff(buys, eb)}")
        self.assertEqual(sells, es, f"매도 첫 차이 {first_diff(sells, es)}")


def _make(fixture, cfg):
    def t(self):
        self.check(fixture, cfg)
    t.__doc__ = f"{fixture} × {cfg}: 매수(신호 봉·체결 봉·회차·사유)·매도(봉·사유·회차) 원본과 완전 일치"
    return t


for _f in FIXTURES:
    for _c in CFG_NAMES:
        setattr(TestParity, f"test_parity_{_f.replace('upbit_', '')}_{_c}", _make(_f, _c))


class TestFixtures(unittest.TestCase):
    def test_cfgs_nine_and_fixtures_three(self):
        cfgs = load_cfgs()
        self.assertEqual(tuple(cfgs["cfgs"]), CFG_NAMES)
        self.assertEqual(tuple(cfgs["meta"]["fixtures"]), FIXTURES)
        for f in FIXTURES:
            for c in CFG_NAMES:
                self.assertTrue((PB_DIR / "expected" / f"{f}__{c}.json").is_file(), (f, c))

    def test_event_counts_base(self):
        """각 경우 사건 수: base 세 세트 모두 GOLDEN ≥ 1, PULLBACK ≥ 1, 매도 ≥ 1. 27건 모두 매수·매도 ≥ 1."""
        for f in FIXTURES:
            exp = load_expected(f, "base")
            trig = [b["trigger"] for b in exp["buys"]]
            self.assertGreaterEqual(trig.count("GOLDEN"), 1, f)
            self.assertGreaterEqual(trig.count("PULLBACK"), 1, f)
            self.assertGreaterEqual(len(exp["sells"]), 1, f)
            for c in CFG_NAMES:
                e = load_expected(f, c)
                self.assertGreaterEqual(len(e["buys"]), 1, (f, c))
                self.assertGreaterEqual(len(e["sells"]), 1, (f, c))
            # 조합이 뜻대로 걸렸는지: golden_no 는 GOLDEN 0, golden_only 는 PULLBACK 0
            self.assertNotIn("GOLDEN", [b["trigger"] for b in load_expected(f, "golden_no")["buys"]], f)
            self.assertNotIn("PULLBACK", [b["trigger"] for b in load_expected(f, "golden_only")["buys"]], f)

    def test_expected_script_sha_matches_cfgs(self):
        """고정 파일 27개가 cfgs.json 의 원본 스크립트 sha 로 만들어졌다(원본 sha 자체는 node 시험이 본다)."""
        sha = load_cfgs()["meta"]["original_script_sha256"]
        self.assertRegex(sha, r"^[0-9a-f]{64}$")
        for f in FIXTURES:
            for c in CFG_NAMES:
                self.assertEqual(load_expected(f, c)["meta"]["script_sha256"], sha, (f, c))

    def test_fixture_bars_confirmed_shape(self):
        """t = 봉 시작 UTC ms, 오름차순·중복 없음, 간격은 봉 단위의 배수(빈 봉은 채우지 않음)."""
        for f in FIXTURES:
            fx = load_fixture(f)
            unit = int(fx["meta"]["unit_min"]) * 60_000
            ts = [b["t"] for b in fx["bars"]]
            self.assertEqual(len(ts), fx["meta"]["bar_count"], f)
            self.assertEqual(len(set(ts)), len(ts), f)
            self.assertTrue(all(b > a and (b - a) % unit == 0 for a, b in zip(ts, ts[1:])), f)


T5_MOD = "tests.regressions.test_r_2026_10_28_p3_t5_pullback_engine"
T5_RECALL = (   # 계획 T10 「회차 건너뜀·시장가 고정: T5 시험을 이 묶음에서 다시 부른다」
    "TestSplitBuy.test_split_amount_is_capital_div_splits",
    "TestSplitBuy.test_split_skip_below_min",
    "TestSplitBuy.test_split_skip_krw_short_audit",
    "TestSplitBuy.test_skip_clears_armed_like_buy",
    "TestSplitBuy.test_pullback_always_market",
    "TestSplitBuy.test_pullback_skips_pending_queue",
    "TestStrictAmount.test_split_never_shrinks_amount",
    "TestStrictAmount.test_strict_exact_amount_and_retry_loop_no_shrink",
)


class TestT5Recall(unittest.TestCase):
    def test_t5_skip_and_market_recalled(self):
        import io
        suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(f"{T5_MOD}.{n}") for n in T5_RECALL)
        res = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(suite)
        self.assertEqual(res.testsRun, len(T5_RECALL))
        self.assertEqual((len(res.failures), len(res.errors), len(res.skipped)), (0, 0, 0),
                         [str(t) for t, _ in res.failures + res.errors])


class TestBaselineSingleSource(unittest.TestCase):
    """T9 넘김: git 원본 비교 시험의 기준 커밋은 baseline_commits 한 곳에서만 정한다."""

    def test_no_literal_commit_in_regression_tests(self):
        pat = re.compile(r"""(?:_COMMIT\s*=\s*["'][0-9a-f]{7,40}["']|["']show["']\s*,\s*f?["'][0-9a-f]{7,40}:)""")
        bad = []
        for p in sorted((ROOT / "tests" / "regressions").glob("test_*.py")):
            if pat.search(p.read_text(encoding="utf-8")):
                bad.append(p.name)
        self.assertEqual(bad, [])

    def test_baselines_are_ancestors_of_head(self):
        sh = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--is-shallow-repository"],
                            capture_output=True, text=True)
        if sh.stdout.strip() == "true":
            self.skipTest("얕은 복제 — 기준 커밋 이력 없음(git fetch --unshallow 뒤 다시)")
        for c in (bc.EMA_BASELINE_COMMIT, bc.REVERT_OLD_CODE_COMMIT):
            r = subprocess.run(["git", "-C", str(ROOT), "merge-base", "--is-ancestor", c, "HEAD"],
                               capture_output=True)
            if r.returncode not in (0, 1):
                self.skipTest("git 이력 없음")
            self.assertEqual(r.returncode, 0, c)


if __name__ == "__main__":
    unittest.main()
