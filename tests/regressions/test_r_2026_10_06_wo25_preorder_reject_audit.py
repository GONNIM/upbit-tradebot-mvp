"""
✅ WO-25 회귀: BUY 평가 통과 뒤 주문 요청 전 봇 안 차단 → audit_trades BUY_REJECTED (2026-10-06)

근거 (docs/plans/2026-10-05-wo24-unfilled-buy-audit/deploy-report.md "창 뒤 사건" 2):
- 10-06 05:37 KRW-JTO BUY 평가 통과(overall_ok=1, id 77602) → 현재가 매수 진입 →
  `[BUY-LIMIT] 활성 KRW 부족: 가용=1 계산=0 (최소 5,000 미만)` → 알림만, audit_trades 0행.
  감사 로그 페이지에는 🟢 BUY 평가만 보이고 왜 안 샀는지가 없었다.
처방 (판정식·필터·발주 무변경):
- 평가 통과 뒤 [UPBIT-ORDER] 요청 전의 모든 차단 분기에서 audit_trades type='BUY_REJECTED' 1행.
  note = 사람이 읽는 사유 (감사 로그 '거절 사유' 열), meta.stage='pre_order', meta.error_name=분기 코드.

실행:
    python3 -m unittest tests.regressions.test_r_2026_10_06_wo25_preorder_reject_audit -v
"""
from __future__ import annotations

import json
import shutil
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

U = "test_r_2026_10_06_wo25"
T = "KRW-JTO"
META = {"bar": 709, "reason": "EMA_GC", "bar_time": "2026-10-06T05:36:00+09:00",
        "macd": None, "signal": None, "ema_fast": 770.28, "ema_slow": 770.16, "fixed_price_buy": True, "wait_bars": 5}
BAR_TS = datetime(2026, 10, 5, 20, 36, tzinfo=timezone.utc)  # = 10-06 05:36 KST


def _ok_call(uuid="u-ok"):
    return {"ok": True, "status": 201, "data": {"uuid": uuid}, "error_name": None, "error_message": None,
            "exception": None, "body": None}


class _DbCase(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="wo25_"))
        self.db_path = str(self.tmpdir / f"tradebot_{U}.db")
        self._patchers = [
            patch("services.init_db.get_db_path", return_value=self.db_path),
            patch("services.db.get_db_path", return_value=self.db_path),
            patch("services.notifier.send", MagicMock(return_value=True)),
            # 시험은 네트워크·실주문에 의존하지 않는다: 바뀌지 않은 발주가 불리면 실패
            patch("core.trader._upbit_buy_limit", MagicMock(side_effect=AssertionError("시험 중 실제 지정가 주문 금지"))),
            patch("core.trader._upbit_buy_market", MagicMock(side_effect=AssertionError("시험 중 실제 시장가 주문 금지"))),
        ]
        for p in self._patchers:
            p.start()
        from services.init_db import initialize_db, ensure_all_schemas
        from services.db import ensure_schema
        initialize_db(U)
        ensure_all_schemas(U)
        ensure_schema(U)

    def tearDown(self):
        for p in self._patchers:
            p.stop()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _rows(self, where="type='BUY_REJECTED'"):
        with sqlite3.connect(self.db_path) as c:
            c.row_factory = sqlite3.Row
            return [dict(r) for r in c.execute(f"SELECT * FROM audit_trades WHERE {where} ORDER BY id").fetchall()]

    def _one(self, code):
        rows = self._rows()
        self.assertEqual(len(rows), 1, f"BUY_REJECTED 1행이어야 함 (code={code})")
        r = rows[0]
        m = json.loads(r["meta"])
        self.assertEqual(m.get("stage"), "pre_order")
        self.assertEqual(m.get("error_name"), code)
        self.assertEqual(r["ticker"], T)
        return r, m

    def _trader(self):
        from core.trader import UpbitTrader
        with patch("core.trader.pyupbit.Upbit", MagicMock()):
            tr = UpbitTrader(U, risk_pct=0.5, test_mode=False)
        tr._get_settings_history_id = lambda: None
        return tr

    def _engine(self, *, paused=False, pending=False, polluted=False, holding=False):
        """execute()·_execute_buy()·_audit_wo2_resolution() 에 필요한 최소 속성만 갖춘 엔진."""
        from core.strategy_engine import StrategyEngine
        eng = object.__new__(StrategyEngine)
        eng.user_id, eng.ticker, eng.bar_count, eng.interval_sec = U, T, 709, 60
        eng.strategy_type = "EMA"
        eng.strategy = SimpleNamespace(last_buy_reason="EMA_GC", buy_conditions={"fixed_price_buy_enabled": True})
        eng.trader = self._trader()
        eng.position = SimpleNamespace(pending_order=pending, has_position=holding,
                                       set_pending=MagicMock(), open_position=MagicMock())
        eng.indicators = SimpleNamespace(state_polluted=polluted)
        eng._pending_buy_uuid = "u-prev" if pending else None
        eng._paused = paused
        return eng

    def _bar(self, close=779.0):
        from core.strategy_engine import Bar
        return Bar(ts=BAR_TS, open=close, high=close, low=close, close=close, volume=1.0,
                   is_closed=True, is_confirmed=True, source="TEST")


# ─────────────────────────────────────────────────────────────
# 지시 (1)~(4)
# ─────────────────────────────────────────────────────────────
class TestWo25Core(_DbCase):

    def test_1_krw_shortage_limit_buy_records_reject(self):
        """(1) 10-06 05:37 재현: 현재가 매수, 가용 1원 → BUY_REJECTED 1행·사유 문자열."""
        tr = self._trader()
        with patch.object(tr, "_krw_balance", return_value=1.0), patch.object(tr, "_current_risk_pct", return_value=0.5):
            self.assertEqual(tr.buy_limit(779.0, T, meta=dict(META), interval_sec=300), {})
        r, m = self._one("krw_below_min")
        self.assertIn("매수 가능 KRW 부족 (가용 1원", r["note"])
        self.assertIn("< 최소 5,000원", r["note"])
        self.assertEqual(r["reason"], "EMA_GC")
        self.assertEqual(r["bar_time"], "2026-10-06T05:36:00+09:00")
        self.assertAlmostEqual(r["price"], 779.0)
        self.assertEqual(m.get("avail_krw"), 1.0)
        self.assertEqual(m.get("order_type"), "limit")

    def test_2_surge_block_is_evaluation_stage_no_reject_row(self):
        """(2) 급등 차단은 평가 단계(overall_ok=0, failed_keys=SURGE_FILTER) — 평가 통과 뒤 분기가 아님.
        조사 A: strategy_incremental.py on_bar 에서 필터가 막으면 Action.HOLD → execute 조기 반환.
        → BUY_REJECTED 행을 만들지 않는다 (감사 로그 BUY 평가 행의 failed_keys 로 이미 보임)."""
        from core.filters.buy_filters import SlowEmaSurgeFilter
        from core.strategy_engine import Action
        f = SlowEmaSurgeFilter(threshold_pct=0.015)
        f.set_enabled(True)
        res = f.evaluate(bar=SimpleNamespace(close=800.0, ts=BAR_TS), ema_slow=770.0)  # +3.9% > 1.5%
        self.assertTrue(res.should_block)
        self.assertEqual(res.reason, "SURGE_FILTER")
        eng = self._engine()
        with patch("core.strategy_engine.get_trading_paused", return_value=False):
            eng.execute(Action.HOLD, self._bar(), dict(META))
        self.assertEqual(self._rows(), [], "급등 차단(HOLD)은 BUY_REJECTED 를 만들지 않음")

    def test_3_normal_order_path_no_reject_row(self):
        """(3) 정상 주문 경로(지정가·시장가)에는 BUY_REJECTED 행 없음."""
        tr = self._trader()
        with patch.object(tr, "_krw_balance", return_value=1_000_000.0), \
             patch.object(tr, "_current_risk_pct", return_value=0.5), \
             patch("core.trader._upbit_buy_limit", return_value=_ok_call("u-limit")), \
             patch("core.trader._upbit_buy_market", return_value=_ok_call("u-market")), \
             patch("engine.reconciler_singleton.get_reconciler", return_value=MagicMock()):
            r1 = tr.buy_limit(779.0, T, meta=dict(META), interval_sec=300)
            r2 = tr.buy_market(779.0, T, meta=dict(META))
        self.assertTrue(r1.get("limit_pending"))
        self.assertEqual(r2.get("uuid"), "u-market")
        self.assertEqual(self._rows(), [], "정상 발주에는 거절 행 없음")

    def test_4_audit_page_shows_preorder_reject(self):
        """(4) 감사 로그 페이지 표시 매핑: ⛔ 매수 거절 + '거절 사유' 열에 note 그대로 + 거절 필터."""
        tr = self._trader()
        with patch.object(tr, "_krw_balance", return_value=1.0), patch.object(tr, "_current_risk_pct", return_value=0.5):
            tr.buy_limit(779.0, T, meta=dict(META), interval_sec=300)
        from services.db import trade_type_display, trade_kind, is_reject_type
        self.assertEqual(trade_type_display("BUY_REJECTED"), "⛔ 매수 거절")
        self.assertEqual(trade_kind("BUY_REJECTED"), "거절")
        self.assertTrue(is_reject_type("BUY_REJECTED"))
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(ROOT / "pages" / "audit_viewer.py"), default_timeout=60)
        at.query_params["user_id"] = U
        at.query_params["tab"] = "trades"
        at.query_params["mode"] = "LIVE"
        at.query_params["ticker"] = "JTO"
        at.session_state["user_id"] = U
        at.run()
        self.assertEqual([e.value for e in at.exception], [], "렌더 예외 없어야 함")
        df = at.dataframe[0].value
        rej = df[df["type"] == "⛔ 매수 거절"]
        self.assertEqual(len(rej), 1)
        self.assertIn("매수 가능 KRW 부족 (가용 1원", rej.iloc[0]["거절 사유"])
        flt = next(m for m in at.multiselect if m.label == "유형 필터")
        flt.set_value(["거절"]).run()
        self.assertEqual(at.dataframe[0].value["type"].tolist(), ["⛔ 매수 거절"])


# ─────────────────────────────────────────────────────────────
# 조사 A 의 분기마다 1건 — 트레이더 (주문 전)
# ─────────────────────────────────────────────────────────────
class TestWo25TraderBranches(_DbCase):

    def test_limit_krw_zero(self):
        tr = self._trader()
        with patch.object(tr, "_krw_balance", return_value=0.0):
            self.assertEqual(tr.buy_limit(779.0, T, meta=dict(META)), {})
        r, _ = self._one("krw_zero")
        self.assertIn("매수 가능 KRW 없음 (가용 0원)", r["note"])

    def test_limit_tick_out_of_range(self):
        tr = self._trader()
        with patch("core.trader._round_price_to_tick", return_value=800.0):  # 779 → 800 (+2.7%)
            self.assertEqual(tr.buy_limit(779.0, T, meta=dict(META)), {})
        r, m = self._one("tick_out_of_range")
        self.assertIn("주문가 호가 단위 이탈", r["note"])
        self.assertEqual(m.get("rounded_price"), 800.0)

    def test_limit_tick_round_error(self):
        tr = self._trader()
        with patch("core.trader._round_price_to_tick", side_effect=ValueError("tick")):
            self.assertEqual(tr.buy_limit(779.0, T, meta=dict(META)), {})
        r, _ = self._one("tick_round_error")
        self.assertIn("주문가 호가 단위 계산 실패", r["note"])

    def test_limit_qty_zero(self):
        tr = self._trader()
        with patch("core.trader._round_price_to_tick", side_effect=lambda p: p), \
             patch.object(tr, "_krw_balance", return_value=1_000_000.0), \
             patch.object(tr, "_current_risk_pct", return_value=0.5):
            self.assertEqual(tr.buy_limit(1e14, T, meta=dict(META)), {})
        r, _ = self._one("qty_zero")
        self.assertIn("주문 수량 계산 결과 0", r["note"])

    def test_market_krw_zero(self):
        tr = self._trader()
        with patch.object(tr, "_krw_balance", return_value=0.0):
            self.assertEqual(tr.buy_market(779.0, T, meta=dict(META)), {})
        r, m = self._one("krw_zero")
        self.assertIn("시장가 매수 주문 전 차단", r["note"])
        self.assertEqual(m.get("order_type"), "market")

    def test_market_krw_below_min(self):
        tr = self._trader()
        with patch.object(tr, "_krw_balance", return_value=6_000.0), patch.object(tr, "_current_risk_pct", return_value=0.5):
            self.assertEqual(tr.buy_market(779.0, T, meta=dict(META)), {})
        r, _ = self._one("krw_below_min")
        self.assertIn("매수 가능 KRW 부족 (가용 6,000원, 주문 비율 적용 주문액 2,998원", r["note"])


# ─────────────────────────────────────────────────────────────
# 조사 A 의 분기마다 1건 — 엔진 (평가 통과 뒤, 트레이더 호출 전)
# ─────────────────────────────────────────────────────────────
class TestWo25EngineBranches(_DbCase):

    def _exec_buy(self, eng, paused=False):
        from core.strategy_engine import Action
        with patch("core.strategy_engine.get_trading_paused", return_value=paused), \
             patch("core.strategy_engine.annotate_buy_eval_blocked", MagicMock()):
            eng.execute(Action.BUY, self._bar(), dict(META))

    def test_engine_trading_paused(self):
        self._exec_buy(self._engine(), paused=True)
        r, _ = self._one("trading_paused")
        self.assertIn("매매 일시중지", r["note"])
        self.assertEqual(r["bar_time"], "2026-10-06T05:36:00+09:00")

    def test_engine_paused_sell_not_recorded(self):
        """일시중지 중 SELL 액션은 BUY_REJECTED 를 만들지 않음 (매수 전용)."""
        from core.strategy_engine import Action
        eng = self._engine()
        with patch("core.strategy_engine.get_trading_paused", return_value=True):
            eng.execute(Action.SELL, self._bar(), dict(META))
        self.assertEqual(self._rows(), [])

    def test_engine_order_in_progress(self):
        self._exec_buy(self._engine(pending=True))
        r, m = self._one("order_in_progress")
        self.assertIn("앞선 매수 주문이 진행 중", r["note"])
        self.assertEqual(m.get("pending_buy_uuid"), "u-prev")

    def test_engine_state_polluted(self):
        self._exec_buy(self._engine(polluted=True))
        r, _ = self._one("state_polluted")
        self.assertIn("지표 오염 상태", r["note"])

    def test_engine_already_holding(self):
        eng = self._engine(holding=True)
        eng._execute_buy(self._bar(), dict(META))
        r, _ = self._one("already_holding")
        self.assertIn("이미 포지션 보유 중", r["note"])

    def test_engine_wo2_deferred_buy_not_ordered(self):
        """WO-2 지연 매수가 발주 없이 끝난 3사유 → 각 1행. 통과(1)는 행 없음."""
        eng = self._engine()
        now = datetime.now(timezone.utc)
        with patch("services.db.update_buy_eval_wo2_resolution", MagicMock()):
            eng._audit_wo2_resolution(BAR_TS, 1, None, 779.0, now)
            self.assertEqual(self._rows(), [], "유효성 통과는 거절 아님")
            for reason in ("SUPERSEDED", "MAX_WAIT_EXCEEDED", "SIGNAL_INVERTED"):
                eng._audit_wo2_resolution(BAR_TS, 0, reason, 779.0, now)
        rows = self._rows()
        self.assertEqual([json.loads(r["meta"])["error_name"] for r in rows],
                         ["wo2_superseded", "wo2_max_wait_exceeded", "wo2_signal_inverted"])
        self.assertIn("새 매수 신호로 교체", rows[0]["note"])
        self.assertIn("대기 시간 초과", rows[1]["note"])
        self.assertIn("매수 신호 불성립", rows[2]["note"])

    def test_reject_rows_excluded_from_buy_aggregates(self):
        """주문 전 거절 행은 type='BUY' 집계(최근 봇 매수 판정)에 섞이지 않음."""
        self._exec_buy(self._engine(pending=True))
        from services.db import has_recent_bot_buy_for_ticker
        self.assertEqual(len(self._rows("type='BUY'")), 0)
        self.assertFalse(has_recent_bot_buy_for_ticker(U, T))


if __name__ == "__main__":
    unittest.main()
