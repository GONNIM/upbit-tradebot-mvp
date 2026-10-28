"""
2차 T8: 감사 로그 칸·체결 행 회차·평단, 용어, 텔레그램 문구.

계획 `docs/specs/v2-dashboard/plan-phase2.md` 「### T8:」 + 앞 Task 넘김(T3·T4·T5·T6·T7 의 「T8」 항목):
- audit_buy_eval.checks 모양(스키마 변경 없음 — X10), failed_keys 값, macd/signal 칸 비움.
- audit_sell_eval trigger_key ∈ Take Profit|Stop Loss|Dead Cross.
- 체결 행(audit_trades) meta 에 회차·눌림목 회차·평단(체결 뒤), entry_price = 체결 뒤 평단.
  TEST = trader `_audit_trade`, LIVE = reconciler `_finalize_order`. 매도 행 = 판정가·판정 사유·체결가.
- EMA·MACD 경로는 2차 T7 커밋(2749080) 원본과 같은 호출(바이트 단위)인지 원본 파일을 불러 비교한다.
- 용어, 텔레그램 문구(끝맺음 「투자자님이 따로 하실 일은 없습니다.」, 할 일이 있으면 할 일), dedupe.
임시 DB·대역만 쓴다(서버 DB·실 텔레그램에 닿지 않는다).

실행:
    TELEGRAM_BOT_TOKEN= TELEGRAM_CHAT_ID= python3 -m unittest tests.regressions.test_r_2026_10_28_p3_t8_pullback_audit -v
"""
from __future__ import annotations

import importlib.util
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402,F401
from core import strategy_engine as se  # noqa: E402
from core import strategy_pullback as sp  # noqa: E402
from core.strategy_action import Action  # noqa: E402
from tests.regressions.test_r_2026_10_28_p3_t4_pullback_rules import V, ts_at  # noqa: E402
from tests.regressions.test_r_2026_10_28_p3_t5_pullback_engine import (  # noqa: E402
    CALM, DIP, EngineCase, FakeTrader, TICKER, USER, bar,
)

# EMA 경로 비교 기준 — 2차 T10: 기준 해시는 baseline_commits 한 곳에서만 정한다(올리는 규칙도 그 파일)
from tests.regressions.baseline_commits import EMA_BASELINE_COMMIT as BASE_COMMIT  # noqa: E402
NO_ACTION = "투자자님이 따로 하실 일은 없습니다."
# 투자자 알림에 넣지 않는 내부 표기(영문 태그·표 이름·작업 번호)
INTERNAL = re.compile(r"PULLBACK|\[[A-Z_-]+\]|audit_|pullback_state|split_|\bT\d+\b|\bF\d+\b|_SYNC|DESYNC")


def _load_base(rel: str, name: str):
    """BASE_COMMIT 의 원본 파일을 별도 모듈로 불러온다(없으면 None — git 없는 환경은 건너뜀)."""
    try:
        src = subprocess.run(["git", "-C", str(ROOT), "show", f"{BASE_COMMIT}:{rel}"],
                             capture_output=True, check=True, text=True).stdout
    except Exception:
        return None
    path = Path(tempfile.mkdtemp(prefix="p3t8_base_")) / (name + ".py")
    path.write_text(src, encoding="utf-8")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _norm_call(c):
    return (tuple(c.args), dict(c.kwargs))


class T8EngineCase(EngineCase):
    """T5 EngineCase + 체결 감사 행 기록 대역(동기화 감사 행이 실 DB 에 닿지 않게)."""

    def setUp(self):
        super().setUp()
        missing = os.path.join(tempfile.mkdtemp(prefix="p3t8_"), "none.db")   # 없는 파일 — 분할 상태 저장은 쓰기 0
        for p in (mock.patch("services.db.insert_trade_audit", mock.MagicMock()),
                  mock.patch("services.db.get_db_path", return_value=missing)):
            p.start()
            self.addCleanup(p.stop)


# ======================================================================== 감사 칸
class TestEvalAudit(T8EngineCase):
    def buy_rows(self):
        return [c.kwargs for c in se.insert_buy_eval.call_args_list]

    def sell_rows(self):
        return [c.kwargs for c in se.insert_sell_eval.call_args_list]

    def test_buy_eval_checks_pullback_fields(self):
        self.make()
        self.feed(bar(0, **CALM))                      # 감시 구간·눌림 없음 → 눌림 대기
        self.feed(bar(1, **DIP))                       # 눌림 → 재돌파 1회차 매수
        rows = self.buy_rows()
        self.assertEqual(len(rows), 2)
        keys = {"strategy", "round", "pullback_round", "armed", "active", "inactive_reason", "maTrend",
                "ma200", "maPullback", "slope200", "buy_reason", "golden_event"}
        for r in rows:
            self.assertTrue(keys <= set(r["checks"]), keys - set(r["checks"]))
            self.assertEqual(r["checks"]["strategy"], "PULLBACK")
            self.assertIsNone(r["macd"])               # T5 넘김: macd/signal 칸에 maTrend/ma200 을 넣지 않음
            self.assertIsNone(r["signal"])
            self.assertIn(r["checks"]["armed"], (0, 1))
            self.assertIn(r["checks"]["active"], (0, 1))
            self.assertIn(r["checks"]["golden_event"], (0, 1))
        wait, buy = rows
        self.assertEqual(wait["failed_keys"], ["WAIT_PULLBACK"])
        self.assertEqual((wait["checks"]["round"], wait["checks"]["buy_reason"]), (0, None))
        self.assertEqual(buy["failed_keys"], [])
        self.assertEqual((buy["checks"]["round"], buy["checks"]["pullback_round"], buy["checks"]["buy_reason"]),
                         (1, 1, "PULLBACK"))
        self.assertEqual(buy["checks"]["maTrend"], 11.0)
        self.assertIsNone(buy["checks"]["inactive_reason"])

    def test_failed_keys_not_active_with_reason(self):
        self.make([V(t=9.0, m=10.0), V(s=-1.0), V(s=0.5, slb=2.0)], slopeDrop=1.0)
        self.feed(bar(0, **DIP), bar(1, **DIP), bar(2, **DIP))
        got = [(r["failed_keys"], r["checks"]["inactive_reason"]) for r in self.buy_rows()]
        self.assertEqual(got, [(["NOT_ACTIVE"], "not_golden"), (["NOT_ACTIVE"], "slope_low"),
                               (["NOT_ACTIVE"], "slope_drop")])

    def test_failed_keys_caps(self):
        self.make(maxSplits=1)
        self.feed(bar(0, **DIP), bar(1, **CALM), bar(2, **DIP))    # 1회차 → 체결 → 회차 다 참
        self.assertEqual(self.sell_rows()[-1]["checks"]["failed_keys"], ["SPLITS_FULL"])
        self.make(maxPullbackBuys=1)
        self.feed(bar(0, **DIP), bar(1, **CALM), bar(2, **DIP))
        self.assertEqual(self.sell_rows()[-1]["checks"]["failed_keys"], ["PULLBACK_CAP"])

    def test_failed_keys_desync_label(self):
        self.make()
        self.eng.position.open_position(1000.0, 54.0, 0, ts_at(0))   # 앱 매수(판정 회차 0), TP 56.7 > 고가 56
        self.trader.coin = 1000.0
        self.feed(bar(1, **DIP))
        self.assertEqual(self.sell_rows()[-1]["checks"]["failed_keys"], ["DESYNC"])

    def test_holding_buy_writes_buy_eval_and_sell_trigger_keys(self):
        self.make()
        self.feed(bar(0, **DIP), bar(1, **CALM))
        n_buy = len(self.buy_rows())
        self.feed(bar(2, **DIP))                       # 보유 중 2회차
        self.assertEqual(len(self.buy_rows()), n_buy + 1)
        r = self.buy_rows()[-1]
        self.assertTrue(r["have_position"])
        self.assertTrue(r["overall_ok"])
        self.assertEqual(r["checks"]["round"], 2)
        s = self.sell_rows()[-1]
        self.assertIsNone(s["trigger_key"])
        self.assertIsNone(s["macd"])
        tp_bar = dict(o=55, h=60, l=54, c=58)          # 평단 55 × 1.05 = 57.75 ≤ 60
        self.feed(bar(3, **tp_bar))
        s = self.sell_rows()[-1]
        self.assertEqual((s["trigger_key"], s["triggered"]), ("Take Profit", True))
        self.assertAlmostEqual(s["tp_price"], 55 * 1.05)
        self.assertAlmostEqual(s["sl_price"], 55 * (1 - 0.90))

    def test_sell_trigger_key_mapping(self):
        self.assertEqual(se.PULLBACK_SELL_TRIGGER_KEY, {"TP": "Take Profit", "SL": "Stop Loss",
                                                        "DEADCROSS": "Dead Cross"})

    def test_warmup_audit_failed_key(self):
        self.make()
        self.eng.record_warmup_log(bar(0, **CALM), "(지표 10/24)")
        r = self.buy_rows()[-1]
        self.assertEqual(r["failed_keys"], ["WARMUP"])
        self.assertEqual(r["checks"]["status"], "WARMUP")   # WO-19 자리표시자 판정 키 그대로

    def test_warmup_audit_ema_unchanged(self):
        self.make(strategy_type="EMA")
        self.eng.record_warmup_log(bar(0, **CALM), "(10/200)")
        self.assertEqual(self.buy_rows()[-1]["failed_keys"], ["WARMUP_IN_PROGRESS"])


class TestPosDesyncLogOnce(T8EngineCase):
    def test_pos_desync_warning_once_per_state(self):
        self.make()
        self.eng.position.open_position(1000.0, 54.0, 0, ts_at(0))
        self.trader.coin = 1000.0
        with self.assertLogs("core.strategy_pullback", level="WARNING") as lg:
            self.feed(bar(1, **CALM), bar(2, **CALM), bar(3, **CALM))
        n = sum("POS_DESYNC" in m for m in lg.output)
        self.assertEqual(n, 1)


# ======================================================================== 체결 행
def _patch_trader(test, *, test_mode=True):
    from core.trader import UpbitTrader
    audit = mock.MagicMock()
    ps = [
        mock.patch("core.trader.pyupbit.Upbit"),
        mock.patch("core.trader.insert_trade_audit", audit),
        mock.patch("core.trader.insert_log"),
        mock.patch("core.trader.insert_order"),
        mock.patch("core.trader.get_account", return_value={"virtual_krw": 1}),   # 실 DB 를 열지 않음
        mock.patch("core.trader.create_or_init_account"),
        mock.patch.object(UpbitTrader, "_get_settings_history_id", return_value=None),
    ]
    for p in ps:
        p.start()
        test.addCleanup(p.stop)
    return audit


PB_BUY_META = {"bar": 7, "reason": "PULLBACK", "bar_time": "2026-10-28T09:00:00+09:00", "interval_sec": 180,
               "split_round": 2, "pullback_round": 2, "sizing_base": 3_000_000, "per_buy": 600_000,
               "strategy_type": "PULLBACK", "base_qty": 600.0, "base_cost": 600_000.0}
EMA_BUY_META = {"bar": 7, "reason": "EMA_GC", "bar_time": "2026-10-28T09:00:00+09:00", "interval": 180,
                "macd": 10.5, "signal": 10.1, "entry_price": None, "audit_note": None}
EMA_SELL_META = {"bar": 9, "reason": "TAKE_PROFIT", "bar_time": "2026-10-28T09:06:00+09:00", "entry_bar": 7,
                 "entry_price": 1000.0, "bars_held": 2, "pnl_pct": 0.03, "macd": 10.0, "signal": 9.0}


class TestTradeRows(unittest.TestCase):
    def setUp(self):
        self.audit = _patch_trader(self)
        from core.trader import UpbitTrader
        self.UpbitTrader = UpbitTrader

    def _trader(self, strategy_type="PULLBACK"):
        return self.UpbitTrader(USER, risk_pct=0.2, test_mode=True, strategy_type=strategy_type, params_file=None)

    def _call(self, t, side, price, qty, meta):
        t._audit_trade(side=side, ticker=TICKER, price=price, qty=qty, status_note="x", meta=dict(meta),
                       balances_before=(1.0, 0.0), balances_after=(0.0, 1.0), fee_ratio=0.0005, risk_pct=0.2)
        return self.audit.call_args

    def test_trade_row_round_and_avg(self):
        """TEST trader 경로: 발주 meta 의 회차 → 체결 행 meta, entry_price = 체결 뒤 평단."""
        c = self._call(self._trader(), "BUY", 950.0, 600.0, PB_BUY_META)
        meta = json.loads(c.kwargs["meta"])
        avg = (600_000.0 + 600.0 * 950.0) / 1200.0
        self.assertEqual((meta["split_round"], meta["pullback_round"]), (2, 2))
        self.assertAlmostEqual(meta["avg_after"], avg)
        self.assertAlmostEqual(c.args[9], avg)               # entry_price 칸(위치 인자 10번째)
        self.assertEqual(c.kwargs["strategy_type"], "PULLBACK")

    def test_trade_row_first_round_avg_is_fill_price(self):
        m = dict(PB_BUY_META, split_round=1, pullback_round=1, base_qty=0.0, base_cost=0.0)
        c = self._call(self._trader(), "BUY", 1000.0, 600.0, m)
        self.assertAlmostEqual(json.loads(c.kwargs["meta"])["avg_after"], 1000.0)

    def test_sell_row_has_judged_and_fill_price(self):
        m = {"bar": 9, "reason": "TP", "bar_time": "2026-10-28T09:06:00+09:00", "entry_bar": 7,
             "entry_price": 974.36, "bars_held": 2, "pnl_pct": 0.05, "macd": None, "signal": None,
             "strategy_type": "PULLBACK", "split_round": 2, "pullback_round": 2,
             "judged_reason": "TP", "judged_price": 1023.08}
        c = self._call(self._trader(), "SELL", 1020.0, 1200.0, m)
        meta = json.loads(c.kwargs["meta"])
        self.assertEqual((meta["judged_reason"], meta["judged_price"], meta["fill_price"]), ("TP", 1023.08, 1020.0))
        self.assertEqual(meta["split_round"], 2)
        self.assertAlmostEqual(c.args[9], 974.36)            # 매도 행 entry_price = 매도 전 평단(지금과 같음)

    def test_ema_trade_row_call_same_as_base(self):
        """EMA·MACD 체결 행: insert_trade_audit 호출이 T7 원본과 같다(meta 칸 없음, entry_price = meta 값)."""
        base = _load_base("core/trader.py", "trader_base_t8")
        if base is None:
            self.skipTest("git 원본 없음")
        for st, side, meta in (("EMA", "BUY", EMA_BUY_META), ("EMA", "SELL", EMA_SELL_META),
                               ("MACD", "SELL", EMA_SELL_META)):
            new = self._call(self._trader(st), side, 1000.0, 3.0, meta)
            with mock.patch.object(base, "insert_trade_audit") as old_a, \
                    mock.patch.object(base, "pyupbit"), \
                    mock.patch.object(base, "get_account", return_value={"virtual_krw": 1}), \
                    mock.patch.object(base.UpbitTrader, "_get_settings_history_id", return_value=None):
                t = base.UpbitTrader(USER, risk_pct=0.2, test_mode=True, strategy_type=st, params_file=None)
                t._audit_trade(side=side, ticker=TICKER, price=1000.0, qty=3.0, status_note="x", meta=dict(meta),
                               balances_before=(1.0, 0.0), balances_after=(0.0, 1.0), fee_ratio=0.0005,
                               risk_pct=0.2)
            a, b = _norm_call(new), _norm_call(old_a.call_args)
            a[1].pop("timestamp", None), b[1].pop("timestamp", None)
            self.assertEqual(a, b, (st, side))
            self.assertNotIn("meta", new.kwargs)


class TestLiveFillRows(unittest.TestCase):
    def _finalize(self, mod, meta, side="BUY", vol=600.0, px=1002.0, st="PULLBACK"):
        r = mod.OrderReconciler(mock.MagicMock())
        r.upbit.get_balances.return_value = []
        r._pending["u1"] = {"user_id": USER, "ticker": TICKER, "side": side, "meta": dict(meta)}
        with mock.patch.object(mod, "insert_trade_audit") as ita, \
                mock.patch.object(mod, "update_order_completed"), \
                mock.patch.object(mod, "update_account_from_balances"), \
                mock.patch.object(mod, "update_position_from_balances"), \
                mock.patch.object(mod.OrderReconciler, "_order_strategy_type", return_value=st):
            r._finalize_order("u1", USER, TICKER, side, vol, px, 0.3, "FILLED")
        return ita.call_args

    def test_live_fill_row_round_and_avg(self):
        import engine.order_reconciler as orm
        c = self._finalize(orm, PB_BUY_META)
        meta = json.loads(c.kwargs["meta"])
        avg = (600_000.0 + 600.0 * 1002.0) / 1200.0
        self.assertEqual((meta["split_round"], meta["pullback_round"]), (2, 2))
        self.assertAlmostEqual(meta["avg_after"], avg)
        self.assertAlmostEqual(c.kwargs["entry_price"], avg)

    def test_live_sell_row_judged_and_fill(self):
        import engine.order_reconciler as orm
        m = {"bar": 9, "reason": "SL", "entry_price": 1000.0, "strategy_type": "PULLBACK", "split_round": 1,
             "pullback_round": 0, "judged_reason": "SL", "judged_price": 970.0}
        c = self._finalize(orm, m, side="SELL", vol=600.0, px=968.5)
        meta = json.loads(c.kwargs["meta"])
        self.assertEqual((meta["judged_reason"], meta["judged_price"], meta["fill_price"]), ("SL", 970.0, 968.5))
        self.assertEqual(c.kwargs["entry_price"], 1000.0)

    def test_live_fill_ema_call_same_as_base(self):
        """EMA LIVE 체결 행: T7 원본 reconciler 와 같은 insert_trade_audit 인자(meta 없음)."""
        import engine.order_reconciler as orm
        base = _load_base("engine/order_reconciler.py", "reconciler_base_t8")
        if base is None:
            self.skipTest("git 원본 없음")
        for side, meta in (("BUY", EMA_BUY_META), ("SELL", EMA_SELL_META),
                           ("BUY", dict(EMA_BUY_META, split_round=1))):   # 전략이 EMA 면 회차 키가 있어도 옮기지 않음
            new = self._finalize(orm, meta, side=side, st="EMA")
            old = self._finalize(base, meta, side=side, st="EMA")
            self.assertEqual(_norm_call(new), _norm_call(old), side)
            self.assertNotIn("meta", new.kwargs)


# ======================================================================== 용어
class TestTerminology(unittest.TestCase):
    def test_terminology_has_pullback_terms(self):
        from services import terminology as tm
        terms = ["눌림목 분할매수", "눌림목 매수", "골든크로스 매수", "분할 n회차", "눌림 대기", "전환 예약",
                 "전환 완료", "복귀", "회차 건너뜀"]
        self.assertEqual(list(tm.PULLBACK_TERMS.values()), terms)
        self.assertEqual(tm.split_round_text(3), "분할 3회차")
        doc = (ROOT / "docs/operations/terminology.md").read_text(encoding="utf-8")
        for t in terms:
            self.assertIn(t, doc)
        for t in terms:                                   # 폐기 용어 검사에 걸리지 않음
            self.assertEqual(tm.find_deprecated(t), [])

    def test_eval_state_text(self):
        from services import terminology as tm
        self.assertEqual(tm.pullback_eval_text(["WAIT_PULLBACK"], {"round": 1}), "눌림 대기 — 2회차 준비")
        self.assertEqual(tm.pullback_eval_text([], {"round": 2, "buy_reason": "PULLBACK"}), "분할 2회차 · 눌림목 매수")
        self.assertEqual(tm.pullback_eval_text(["DESYNC"], {}), "보유 수량 어긋남 — 추가 매수 멈춤")

    def test_viewer_columns_only_with_pullback_rows(self):
        from services import terminology as tm
        ema = pd.DataFrame({"checks": [{"strategy_mode": "EMA"}], "failed_keys": [[]], "macd": [1.0]})
        self.assertIs(tm.add_pullback_eval_columns(ema), ema)    # EMA 만 있으면 그대로(칸 추가 없음)
        mix = pd.DataFrame({"checks": [{"strategy_mode": "EMA"}, {"strategy": "PULLBACK", "round": 1,
                                                                    "golden": 1}],
                            "failed_keys": [[], ["WAIT_PULLBACK"]]})
        out = tm.add_pullback_eval_columns(mix)
        self.assertEqual(list(out["strategy_label"]), ["", "새 전략"])
        self.assertEqual(list(out["pullback_state"]), ["", "눌림 대기 — 2회차 준비"])

    def test_viewer_trade_columns_classify(self):
        from services import terminology as tm
        df = pd.DataFrame({"type": ["BUY", "SELL", "BUY", "PULLBACK_SYNC"],
                           "reason": ["EMA_GC", "TP", "PULLBACK", "wallet_more"],
                           "meta": [None, json.dumps({"split_round": 2, "judged_reason": "TP", "judged_price": 1050.0,
                                                      "fill_price": 1048.0}),
                                    json.dumps({"split_round": 2, "pullback_round": 2, "avg_after": 974.3}), None],
                           "_class": ["LEGACY", "PULLBACK", "PULLBACK", "PULLBACK"]})
        out = tm.add_pullback_trade_columns(df, df["_class"].tolist())
        self.assertEqual(list(out["strategy_label"]), ["옛 기록(EMA/MACD)", "새 전략", "새 전략", "새 전략"])
        self.assertEqual(out["pullback_detail"][2], "분할 2회차 · 눌림목 매수 · 평단 974.3원")
        self.assertIn("익절 판정 1,050원", out["pullback_detail"][1])
        self.assertIn("체결 1,048원", out["pullback_detail"][1])
        self.assertIn("수량 맞춤", out["pullback_detail"][3])
        only_ema = df.iloc[:1].copy()
        self.assertIs(tm.add_pullback_trade_columns(only_ema, ["EMA"]), only_ema)
        self.assertEqual(tm.strategy_class_label("UNKNOWN"), "-")       # 분류 불명은 화면 경고 없음(1028-06)

    def test_pullback_sync_type_display(self):
        from services.db import trade_type_display
        self.assertEqual(trade_type_display("PULLBACK_SYNC"), "🔄 새 전략 수량 맞춤")
        self.assertEqual(trade_type_display("BUY"), "BUY")              # 기존 유형 그대로


# ======================================================================== 텔레그램 문구
class NotifyCase(T8EngineCase):
    def sent(self, pred=lambda c: True):
        return [c for c in self.notify.call_args_list if pred(c)]

    def assert_investor_text(self, c, ending=NO_ACTION):
        title, body = c.args[1], c.args[2]
        self.assertTrue(body.rstrip().endswith(ending), body)
        self.assertIsNone(INTERNAL.search(title + "\n" + body), title + "\n" + body)


class TestNotifyTexts(NotifyCase):
    def test_notify_text_no_action_needed(self):
        self.make()
        self.feed(bar(0, **DIP))
        buys = self.sent(lambda c: "새 전략 매수" in c.args[1])
        self.assertEqual(len(buys), 1)
        c = buys[0]
        self.assertEqual(c.args[0], "INFO")
        self.assertEqual(c.args[1], f"🟢 새 전략 매수 1회차 · 눌림목 매수 — {TICKER} 평단 55원")
        self.assert_investor_text(c)
        self.assertEqual(c.kwargs["dedupe_key"], f"pullback_buy:{USER}:u1")

    def test_golden_buy_text(self):
        self.make([V(t=9.0, m=10.0), V()], buyOnGoldenCross=True)
        self.feed(bar(0, **DIP), bar(1, **CALM))
        buys = self.sent(lambda c: "새 전략 매수" in c.args[1])
        self.assertEqual(buys[0].args[1], f"🟢 새 전략 매수 1회차 · 골든크로스 매수 — {TICKER} 평단 55원")

    def test_skip_notify_tells_what_to_check(self):
        self.make(trader=FakeTrader(avail=100_000))
        self.feed(bar(0, **DIP))
        c = self.sent(lambda c: "건너뜀" in c.args[1])[0]
        self.assertEqual(c.args[1], "⚠️ 새 전략 1회차 건너뜀 — 원화 잔고 부족")
        self.assert_investor_text(c, ending="업비트 앱의 미체결 주문·출금을 확인해 주세요.")
        self.assertNotIn(NO_ACTION, c.args[2])

    def test_skip_below_min_no_action(self):
        self.capital = 20_000
        self.make()
        self.feed(bar(0, **DIP))
        c = self.sent(lambda c: "건너뜀" in c.args[1])[0]
        self.assertEqual(c.args[1], "⚠️ 새 전략 1회차 건너뜀 — 최소 주문금액 미만")
        self.assert_investor_text(c)

    def test_skip_notify_dedupe(self):
        self.make(trader=FakeTrader(avail=100_000))
        self.feed(bar(0, **DIP), bar(1, **DIP), bar(2, **DIP))
        keys = [c.kwargs["dedupe_key"] for c in self.sent(lambda c: "건너뜀" in c.args[1])]
        self.assertEqual(len(keys), 3)
        self.assertEqual(set(keys), {f"pullback_skip:{USER}:flat:split_krw_short"})
        self.assertTrue(all(c.kwargs["dedupe_ttl"] == 3600 for c in self.sent(lambda c: "건너뜀" in c.args[1])))

    def test_cooldown_notice_uses_bar_close_time(self):
        """T5 넘김: 「HH:MM 봉부터」 는 봉 시작 시각이었다 — 주문은 그 봉 마감 때 나간다."""
        self.make(trader=FakeTrader(buy_ok=False))
        self.feed(bar(0, **DIP))
        c = self.sent(lambda c: "쉽니다" in (c.args[2] or ""))[0]
        n = se.PULLBACK_BUY_FAIL_COOLDOWN_BARS
        close_kst = (ts_at(0) + pd.Timedelta(minutes=3 * (n + 1))).tz_convert("Asia/Seoul").strftime("%m/%d %H:%M")
        start_kst = (ts_at(0) + pd.Timedelta(minutes=3 * n)).tz_convert("Asia/Seoul").strftime("%m/%d %H:%M")
        self.assertIn(f"{close_kst} 봉 마감 때부터 다시 주문합니다", c.args[2])
        self.assertNotIn(f"{start_kst} 봉부터", c.args[2])
        self.assertIn("(거래소 응답: under_maintenance)", c.args[2])   # 수정 1회차: 코드만(원문은 로그에만)
        self.assertNotIn("Upbit error", c.args[2])
        self.assertNotIn("split_", c.args[2])
        self.assertTrue(c.args[2].rstrip().endswith("확인해 주세요."))

    def test_sync_notify_once(self):
        self.make()
        self.feed(bar(0, **DIP), bar(1, **CALM))
        self.trader.coin *= 2                                   # 앱 매수
        self.feed(bar(2, **CALM), bar(3, **CALM))
        s = self.sent(lambda c: "수량" in c.args[1] and "새 전략" in c.args[1])
        self.assertEqual(len(s), 1)
        self.assertEqual(s[0].args[0], "WARNING")
        self.assert_investor_text(s[0])
        self.assertEqual(s[0].kwargs["dedupe_key"], f"pullback_sync:{USER}:{TICKER}:wallet_more")

    def test_persist_block_critical_once(self):
        """T6 LIVE 거부 해제 전 조건 8: 저장 막음을 시작할 때 CRITICAL 1회."""
        self.make()
        self.eng._pullback_block_persist("복원 읽기 오류(boom)", kind="read_error")
        self.eng._pullback_block_persist("again", kind="read_error")
        self.eng._pullback_block_persist("restore_exception")
        crit = self.sent(lambda c: c.args[0] == "CRITICAL" and "저장" in c.args[1])
        self.assertEqual(len(crit), 1)
        self.assert_investor_text(crit[0])
        self.assertNotIn("boom", crit[0].args[2])

    def test_existing_pullback_texts_investor_safe(self):
        self.make()
        self.eng.pullback_indicators.state_polluted = True
        self.eng._pullback_notify_polluted()
        with mock.patch("services.pullback_state.save", return_value=False), \
                mock.patch("os.path.exists", return_value=True):
            self.eng._pullback_persist()
        crit = self.sent(lambda c: c.args[0] == "CRITICAL")
        self.assertGreaterEqual(len(crit), 2)                   # 지표 오염 + 저장 실패 (빈 목록 통과 방지)
        for c in crit:
            self.assert_investor_text(c)


class TestSellRejectText(unittest.TestCase):
    def _run(self, strategy_type):
        from core.trader import UpbitTrader
        notify = mock.MagicMock(return_value=True)
        ps = [
            mock.patch("core.trader.pyupbit.Upbit"),
            mock.patch("core.trader.insert_trade_audit"),
            mock.patch("core.trader.insert_log"),
            mock.patch("core.trader.insert_order"),
            mock.patch("services.notifier.send", notify),
            mock.patch.object(UpbitTrader, "_get_settings_history_id", return_value=None),
            mock.patch.object(UpbitTrader, "_coin_balance", return_value=1000.0),
            mock.patch("core.trader._upbit_sell_market", return_value={
                "ok": False, "status": 400, "error_name": "insufficient_funds_ask",
                "error_message": "주문가능한 금액(KRW-TEST)이 부족합니다.", "exception": None, "body": "",
                "data": None}),
        ]
        for p in ps:
            p.start()
        try:
            t = UpbitTrader(USER, risk_pct=0.2, test_mode=False, strategy_type=strategy_type, params_file=None)
            t.sell_market(1000.0, TICKER, 100.0, meta={"reason": "TP" if strategy_type == "PULLBACK" else "EMA_DC"})
        finally:
            for p in ps:
                p.stop()
        return [c for c in notify.call_args_list if "매도 거절" in c.args[1]]

    def test_pullback_sell_reject_text(self):
        c = self._run("PULLBACK")[0]
        body = c.args[2]
        self.assertIn("외부 미체결 매도 주문을 확인해 주세요", body)
        self.assertIn("insufficient_funds_ask", body)            # 거절 코드(외부 주문 공존 규칙)
        self.assertIn("익절", body)
        self.assertEqual(c.kwargs["dedupe_key"], f"sell_reject:{TICKER}:insufficient_funds_ask")
        self.assertNotIn("PULLBACK", c.args[1] + body)
        self.assertTrue(body.rstrip().endswith("봇 매도가 거절됩니다."))

    def test_ema_sell_reject_text_unchanged(self):
        c = self._run("EMA")[0]
        self.assertEqual(c.args[1], f"❌ 매도 거절 — {TICKER}")
        self.assertIn("💡 업비트 앱에서 직접 넣은 지정가 매도 주문이 있는지 확인하세요.", c.args[2])
        self.assertIn("신호: EMA_DC", c.args[2])


class TestSellMetaFromEngine(T8EngineCase):
    def test_engine_sell_meta_has_judged_fields(self):
        self.make()
        self.feed(bar(0, **DIP), bar(1, **CALM))
        self.feed(bar(2, o=55, h=60, l=54, c=58))               # TP
        m = self.trader.sell_calls[-1]["meta"]
        self.assertEqual((m["judged_reason"], m["strategy_type"], m["split_round"], m["pullback_round"]),
                         ("TP", "PULLBACK", 1, 1))
        self.assertAlmostEqual(m["judged_price"], 55 * 1.05)

    def test_engine_sell_meta_deadcross_judged_close(self):
        from tests.regressions.test_r_2026_10_28_p3_t4_pullback_rules import DEAD
        self.make([V(), V(), V(**DEAD)])
        self.feed(bar(0, **DIP), bar(1, **CALM), bar(2, o=55, h=56, l=54, c=54.5))
        m = self.trader.sell_calls[-1]["meta"]
        self.assertEqual((m["judged_reason"], m["judged_price"]), ("DEADCROSS", 54.5))

    def test_engine_buy_meta_has_base(self):
        self.make()
        self.feed(bar(0, **DIP), bar(1, **CALM), bar(2, **DIP))
        m1, m2 = (c["meta"] for c in self.trader.buy_calls)
        self.assertEqual((m1["base_qty"], m1["base_cost"]), (0.0, 0.0))
        self.assertAlmostEqual(m2["base_qty"], 600_000 / 55.0)
        self.assertAlmostEqual(m2["base_cost"], 600_000.0)


# ======================================================================== 감사 화면 (AppTest, 임시 DB)
VU = "p3t8view"
VT = "KRW-JTO"


class TestAuditViewerRender(unittest.TestCase):
    def setUp(self):
        import shutil
        self.tmpdir = tempfile.mkdtemp(prefix="p3t8v_")
        self.addCleanup(shutil.rmtree, self.tmpdir, True)
        self.db_path = os.path.join(self.tmpdir, f"tradebot_{VU}.db")
        for p in (mock.patch("services.init_db.get_db_path", return_value=self.db_path),
                  mock.patch("services.db.get_db_path", return_value=self.db_path),
                  mock.patch("services.notifier.send", mock.MagicMock(return_value=True)),
                  mock.patch("engine.params._get_active_strategy_path",
                             return_value=os.path.join(self.tmpdir, "active.txt"))):
            p.start()
            self.addCleanup(p.stop)
        from services.init_db import initialize_db, ensure_all_schemas
        from services.db import ensure_schema
        initialize_db(VU)
        ensure_all_schemas(VU)
        ensure_schema(VU)

    # ---- 자료
    def ema_rows(self):
        from services.db import insert_buy_eval, insert_sell_eval, insert_trade_audit
        insert_buy_eval(user_id=VU, ticker=VT, interval_sec=180, bar=1, price=700.0, macd=701.0, signal=699.0,
                        have_position=False, overall_ok=True, failed_keys=[], checks={"strategy_mode": "EMA"},
                        notes="EMA BUY", bar_time="2026-10-28T09:00:00+09:00")
        insert_sell_eval(user_id=VU, ticker=VT, interval_sec=180, bar=2, price=710.0, macd=705.0, signal=706.0,
                         tp_price=735.0, sl_price=680.0, highest=None, ts_pct=None, ts_armed=False, bars_held=1,
                         checks={"strategy_mode": "EMA"}, triggered=False, trigger_key=None, notes="EMA",
                         bar_time="2026-10-28T09:03:00+09:00")
        insert_trade_audit(VU, VT, 180, 1, "BUY", "EMA_GC", 700.0, 701.0, 699.0, None, 1, 0, None, None, None,
                           None, None, timestamp="2026-10-28T09:00:05+09:00", strategy_type="EMA")

    def pullback_rows(self):
        from services.db import insert_buy_eval, insert_trade_audit
        insert_buy_eval(user_id=VU, ticker=VT, interval_sec=180, bar=3, price=720.0, macd=None, signal=None,
                        have_position=False, overall_ok=False, failed_keys=["WAIT_PULLBACK"],
                        checks={"strategy": "PULLBACK", "strategy_mode": "PULLBACK", "round": 1, "golden": 1},
                        notes="새 전략 · 눌림 대기 — 2회차 준비", bar_time="2026-10-28T09:06:00+09:00")
        insert_trade_audit(VU, VT, 180, 3, "BUY", "PULLBACK", 720.0, None, None, 710.0, 3, 0, None, None, None,
                           None, None, timestamp="2026-10-28T09:06:05+09:00", strategy_type="PULLBACK",
                           meta=json.dumps({"split_round": 2, "pullback_round": 2, "avg_after": 710.0}))
        insert_trade_audit(VU, VT, 180, 4, "BUY", "EMA_GC", 700.0, 1.0, 2.0, None, 1, 0, None, None, None,
                           None, None, timestamp="2026-10-28T09:07:05+09:00")   # 표식 뒤 NULL = 분류 불명

    def render(self, page: Path, tab: str):
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(page), default_timeout=60)
        at.query_params["user_id"] = VU
        at.query_params["tab"] = tab
        at.query_params["mode"] = "TEST"
        at.query_params["ticker"] = "JTO"
        at.session_state["user_id"] = VU
        at.run()
        self.assertEqual([e.value for e in at.exception], [], "렌더 예외 없어야 함")
        return at

    def base_page(self):
        try:
            src = subprocess.run(["git", "-C", str(ROOT), "show", f"{BASE_COMMIT}:pages/audit_viewer.py"],
                                 capture_output=True, check=True, text=True).stdout
        except Exception:
            self.skipTest("git 원본 없음")
        p = Path(self.tmpdir) / "audit_viewer_base.py"
        p.write_text(src, encoding="utf-8")
        return p

    def test_ema_only_screen_same_as_base(self):
        """EMA 행만 있으면 BUY·SELL·체결 표의 칸·값이 T7 원본 화면과 같다(추가·사라짐·이동 없음)."""
        self.ema_rows()
        base = self.base_page()
        for tab in ("buy", "sell", "trades"):
            new = self.render(ROOT / "pages" / "audit_viewer.py", tab)
            old = self.render(base, tab)
            a = new.dataframe[0].value
            b = old.dataframe[0].value
            a = a.data if hasattr(a, "data") else a
            b = b.data if hasattr(b, "data") else b
            self.assertEqual(list(a.columns), list(b.columns), tab)
            for col in a.columns:
                if col in ("기록시각", "timestamp"):
                    continue
                self.assertEqual(a[col].astype(str).tolist(), b[col].astype(str).tolist(), (tab, col))
            self.assertEqual([w.value for w in new.warning], [w.value for w in old.warning], tab)
            self.assertEqual([b.label for b in new.button], [b.label for b in old.button], tab)

    def test_pullback_rows_labels(self):
        self.ema_rows()
        self.pullback_rows()
        at = self.render(ROOT / "pages" / "audit_viewer.py", "trades")
        df = at.dataframe[0].value
        df = df.data if hasattr(df, "data") else df
        self.assertIn("전략", df.columns)
        self.assertIn("새 전략 내용", df.columns)
        cols = list(df.columns)
        self.assertEqual(cols.index("전략"), cols.index("type") + 1)
        got = dict(zip(df["reason"], df["전략"]))
        self.assertEqual(got["PULLBACK"], "새 전략")
        self.assertEqual(df[df["reason"] == "PULLBACK"]["새 전략 내용"].iloc[0], "분할 2회차 · 눌림목 매수 · 평단 710원")
        self.assertIn("-", df["전략"].tolist())                            # 분류 불명 행 = 「-」
        texts = " ".join(str(w.value) for w in at.warning) + " ".join(str(i.value) for i in at.info)
        self.assertNotIn("분류 불명", texts)                               # 화면 경고 없음(1028-06)
        at = self.render(ROOT / "pages" / "audit_viewer.py", "buy")
        df = at.dataframe[0].value
        df = df.data if hasattr(df, "data") else df
        row = df[df["전략"] == "새 전략"].iloc[0]
        self.assertEqual(row["새 전략 상태"], "눌림 대기 — 2회차 준비")
        self.assertEqual(row["cross_type"], "🟢 Golden")

    def extra_pullback_rows(self):
        """수정 1회차: 수량 맞춤 행·주문 전 차단(원화 잔고 부족) 행·워밍업 평가 행(golden 없음)."""
        from services.db import insert_buy_eval, insert_trade_audit
        insert_trade_audit(user_id=VU, ticker=VT, interval_sec=180, bar=5, kind="PULLBACK_SYNC", reason="wallet_more",
                           price=None, macd=None, signal=None, entry_price=710.0, entry_bar=3, bars_held=None,
                           tp=None, sl=None, highest=None, ts_pct=None, ts_armed=None, qty=2400.0, note="sync",
                           timestamp="2026-10-28T09:08:05+09:00", strategy_type="PULLBACK",
                           meta=json.dumps({"wallet_qty": 2400.0, "state_qty": 1200.0, "class": "wallet_more",
                                            "strategy_type": "PULLBACK"}))
        insert_trade_audit(VU, VT, 180, 6, "BUY_REJECTED", "PULLBACK", 715.0, None, None, None, None, None,
                           None, None, None, None, None, timestamp="2026-10-28T09:09:05+09:00",
                           strategy_type="PULLBACK", note="원화 잔고 부족 — 줄여 사지 않음",
                           meta=json.dumps({"error_name": "split_krw_short", "stage": "pre_order",
                                            "krw_amount": 600000, "strict_amount": True}))
        insert_buy_eval(user_id=VU, ticker=VT, interval_sec=180, bar=7, price=716.0, macd=None, signal=None,
                        have_position=False, overall_ok=False, failed_keys=["WARMUP"],
                        checks={"strategy": "PULLBACK", "strategy_mode": "PULLBACK", "failed_keys": ["WARMUP"]},
                        notes="새 전략 · 준비 중(지표 계산) 10/400", bar_time="2026-10-28T09:12:00+09:00")

    def test_sync_and_preorder_rows_detail(self):
        """수정 1회차 막음: 화면 유형 문자열로 바꾼 뒤 판정해 「새 전략 내용」이 늘 비던 두 갈래."""
        self.ema_rows()
        self.pullback_rows()
        self.extra_pullback_rows()
        at = self.render(ROOT / "pages" / "audit_viewer.py", "trades")
        df = at.dataframe[0].value
        df = df.data if hasattr(df, "data") else df
        sync = df[df["type"] == "🔄 새 전략 수량 맞춤"].iloc[0]
        self.assertEqual(sync["새 전략 내용"], "보유 수량 맞춤(지갑 기준) — 지갑 수량이 더 많음 · 추가 분할 매수 멈춤")
        self.assertEqual(sync["reason"], "지갑 수량이 더 많음")              # 사유 코드 → 한글(표시층)
        self.assertIn("회차 건너뜀 — 원화 잔고 부족", df["새 전략 내용"].tolist())
        at = self.render(ROOT / "pages" / "audit_viewer.py", "buy")
        df = at.dataframe[0].value
        df = df.data if hasattr(df, "data") else df
        warm = df[df["새 전략 상태"] == "준비 중(지표 계산)"].iloc[0]
        self.assertEqual(warm["cross_type"], "⚪ Neutral")                 # golden 없음 → 기존 표시 그대로


# ======================================================================== 수정 1회차
class TestFix1Terminology(unittest.TestCase):
    def test_trade_columns_use_raw_types(self):
        from services import terminology as tm
        df = pd.DataFrame({"type": ["🔄 새 전략 수량 맞춤", "⛔ 주문 전 차단", "⛔ 주문 전 차단"],
                           "reason": ["wallet_less", "PULLBACK", "PULLBACK"],
                           "meta": [json.dumps({"class": "wallet_less"}),
                                    json.dumps({"stage": "pre_order", "error_name": "split_below_min",
                                                "split_round": 3}),
                                    json.dumps({"stage": "pre_order", "error_name": "split_order_cooldown"})]})
        out = tm.add_pullback_trade_columns(df, ["PULLBACK"] * 3,
                                            raw_types=["PULLBACK_SYNC", "BUY_REJECTED", "BUY_REJECTED"])
        self.assertEqual(list(out["pullback_detail"]),
                         ["보유 수량 맞춤(지갑 기준) — 지갑 수량이 더 적음 · 추가 분할 매수 멈춤",
                          "분할 3회차 건너뜀 — 최소 주문금액 미만",
                          "매수 잠시 쉼(주문 실패 뒤)"])
        self.assertEqual(out["reason"][0], "지갑 수량이 더 적음")
        self.assertEqual(out["reason"][1], "PULLBACK")

    def test_sell_eval_state_from_checks(self):
        """SELL 평가 표는 failed_keys 칸이 없다 — checks.failed_keys 로 「새 전략 상태」를 채운다."""
        from services import terminology as tm
        df = pd.DataFrame({"checks": [{"strategy": "PULLBACK", "failed_keys": ["DESYNC"]},
                                      {"strategy": "PULLBACK", "failed_keys": [], "sell_reason": "TP"}]})
        out = tm.add_pullback_eval_columns(df)
        self.assertEqual(list(out["pullback_state"]), ["보유 수량 어긋남 — 추가 매수 멈춤", "매도 신호 · 익절"])

    def test_sell_reason_label_single_source(self):
        from core import pullback_audit as pa
        from services import terminology as tm
        self.assertFalse(hasattr(pa, "_SELL_REASON_TEXT"))
        t, b = pa.pullback_sell_reject_text(TICKER, "SL", 3, "수량 부족", "insufficient_funds_ask")
        self.assertTrue(b.startswith(tm.PULLBACK_REASON_LABEL["SL"] + " 매도 주문"))


class TestFix1Audit(unittest.TestCase):
    def test_split_audit_exception_still_records(self):
        """split_trade_audit 가 깨져도 체결 행은 남는다(TEST trader·LIVE reconciler 둘 다, meta 칸 없이)."""
        audit = _patch_trader(self)
        from core.trader import UpbitTrader
        t = UpbitTrader(USER, risk_pct=0.2, test_mode=True, strategy_type="PULLBACK", params_file=None)
        with mock.patch("core.trader.split_trade_audit", side_effect=RuntimeError("boom")):
            t._audit_trade(side="BUY", ticker=TICKER, price=950.0, qty=600.0, status_note="x",
                           meta=dict(PB_BUY_META), balances_before=(1.0, 0.0), balances_after=(0.0, 1.0),
                           fee_ratio=0.0005, risk_pct=0.2)
        self.assertEqual(audit.call_count, 1)
        self.assertNotIn("meta", audit.call_args.kwargs)
        import engine.order_reconciler as orm
        with mock.patch.object(orm, "split_trade_audit", side_effect=RuntimeError("boom")):
            c = TestLiveFillRows._finalize(None, orm, PB_BUY_META)
        self.assertIsNotNone(c)
        self.assertNotIn("meta", c.kwargs)

    def test_fetch_with_strategy_reraises_other_errors(self):
        import sqlite3
        from services import db

        class _Cur:
            def execute(self, *a):
                raise sqlite3.OperationalError("database is locked")

        class _Conn:
            def cursor(self):
                return _Cur()

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        with mock.patch.object(db, "get_db", return_value=_Conn()):
            with self.assertRaises(sqlite3.OperationalError):
                db.fetch_trades_audit_with_strategy(USER)


class DryRunTrader(FakeTrader):
    def buy_market(self, price, ticker, ts=None, meta=None, krw_amount=None, strict_amount=False):
        self.buy_calls.append({"price": price, "ticker": ticker, "ts": ts, "meta": dict(meta or {}),
                               "krw_amount": krw_amount, "strict_amount": strict_amount})
        return {"qty": 0.0, "price": price, "uuid": "DRY_RUN"}


class TestFix1Notify(NotifyCase):
    def test_dry_run_buy_notify_per_round(self):
        self.make(trader=DryRunTrader())
        self.feed(bar(0, **DIP), bar(1, **CALM), bar(2, **DIP))
        buys = self.sent(lambda c: "새 전략 매수" in c.args[1])
        self.assertEqual(len(buys), 2)
        keys = [c.kwargs["dedupe_key"] for c in buys]
        self.assertEqual(len(set(keys)), 2, keys)                      # 회차마다 다른 키
        self.assertTrue(all(k.startswith(f"pullback_buy:{USER}:DRY_RUN-") for k in keys), keys)
        for c in buys:
            self.assertNotIn("체결됐습니다", c.args[2])
            self.assertIn("모의 실행", c.args[2])
            self.assert_investor_text(c)

    def test_skip_text_without_per_buy(self):
        self.make()
        for code in ("split_krw_short", "split_below_min"):
            _t, body = self.eng._pullback_skip_text(code, {"split_round": 2, "per_buy": None})
            self.assertNotIn("회당 회당", body)
        self.eng._pullback_notify_buy(1, "PULLBACK", 55.0, None, "k")
        c = self.sent(lambda c: "새 전략 매수" in c.args[1])[-1]
        self.assertNotIn("회당", c.args[2])

    def test_restore_exception_one_critical(self):
        """복원 예외: 「저장 멈춤」·「복원 실패」 CRITICAL 2건 → 복원 실패 1건(본문에 저장 멈춤 사실)."""
        from engine import live_loop
        self.make()
        with mock.patch.object(self.eng, "pullback_restore_on_boot", side_effect=RuntimeError("boom")):
            live_loop._pullback_restore_split_state(self.eng, USER, pd.DataFrame(), None)
        crit = self.sent(lambda c: c.args[0] == "CRITICAL")
        self.assertEqual(len(crit), 1, [c.args[1] for c in crit])
        self.assertIn("복원 실패", crit[0].args[1])
        self.assertIn("기록 저장을 멈췄습니다", crit[0].args[2])
        self.assertNotIn("boom", crit[0].args[2])
        self.assert_investor_text(crit[0])
        self.assertTrue(self.eng._pullback_persist_blocked)

    def test_pullback_meta_interval_key(self):
        """PULLBACK 매수·매도 meta 에 trader·reconciler 가 읽는 interval 키(EMA meta 는 그대로)."""
        self.make()
        self.feed(bar(0, **DIP), bar(1, **CALM), bar(2, o=55, h=60, l=54, c=58))
        self.assertEqual(self.trader.buy_calls[0]["meta"]["interval"], 180)
        self.assertEqual(self.trader.sell_calls[-1]["meta"]["interval"], 180)


if __name__ == "__main__":
    unittest.main()
