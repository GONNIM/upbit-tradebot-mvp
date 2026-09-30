"""
✅ WO-9 (e)(a)(b)(d) 회귀: 발주 거절 가시화 (2026-09-30 KRW-JTO 클레임)

원 결함:
- 외부 지정가 매도 주문이 수량을 묶어 봇 매도 2회 거절 (insufficient_funds_ask).
  알림은 원인을 가리키지 않았고, 기록은 logs 테이블에만 있어 감사 로그 페이지에서 보이지 않았다.
- 시장가 매수 실패는 type='BUY'(reason=BUY_FAILED_API)로 기록돼 BUY 집계에 섞였다.
- 전량 묶임 시 대시보드에 매도 불가 표시가 없고 WO-7 배지가 사라졌다.
- 감사 행의 sl_price/trigger_reason 이 엔진 생성 시점 임계(1.5%)로 남았다 (실제 필터 3.0%).

왕복 4단계 (e):
  1) 모의 거래소 응답 400 insufficient_funds_ask
  2) audit_trades type=SELL_REJECTED 행 생성 (reason=신호 사유, qty, note 한글, meta 거절 코드)
  3) 감사 로그 페이지(pages/audit_viewer.py) 실제 렌더에 ⛔ + 한글 설명 표시, "거절" 필터
  4) 손익·BUY 집계 미포함

실행:
    python3 -m unittest tests.regressions.test_r_2026_09_30_wo9_reject_audit_roundtrip -v
"""
from __future__ import annotations

import json
import shutil
import sqlite3
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

TICKER = "KRW-JTO"
QTY = 2097.5170824
MUST_GUIDE = "업비트 앱에서 직접 넣은 지정가 매도 주문이 있는지 확인하세요."
MUST_NOTE = "주문 가능 수량 부족 — " + MUST_GUIDE  # WO-11 확정 문구


def _reject_call(name="insufficient_funds_ask", msg="주문 가능한 금액(JTO)이 부족합니다."):
    return {
        "ok": False, "status": 400,
        "body": {"error": {"name": name, "message": msg}},
        "error_name": name, "error_message": msg, "exception": None, "data": None,
    }


class _TempDbCase(unittest.TestCase):
    USER = "test_r_2026_09_30_wo9e"

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="wo9e_"))
        self.db_path = str(self.tmpdir / f"tradebot_{self.USER}.db")
        # ⚠️ 실 Telegram 발송 차단 (기본값). 개별 테스트는 필요 시 자체 patch 로 덮어써 호출을 검사.
        self._patchers = [
            patch("services.init_db.get_db_path", return_value=self.db_path),
            patch("services.db.get_db_path", return_value=self.db_path),
            patch("services.notifier.send", MagicMock(return_value=True)),
        ]
        for p in self._patchers:
            p.start()
        from services.init_db import initialize_db, ensure_all_schemas
        from services.db import ensure_schema
        initialize_db(self.USER)
        ensure_all_schemas(self.USER)
        ensure_schema(self.USER)

    def tearDown(self):
        for p in self._patchers:
            p.stop()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _rows(self, sql, params=()):
        with sqlite3.connect(self.db_path) as c:
            c.row_factory = sqlite3.Row
            return [dict(r) for r in c.execute(sql, params).fetchall()]

    def _live_trader(self):
        from core.trader import UpbitTrader
        with patch("core.trader.pyupbit.Upbit", MagicMock()):
            return UpbitTrader(self.USER, risk_pct=0.1, test_mode=False)


# ─────────────────────────────────────────────────────────────
# (e) 왕복 4단계 + (a) 알림 문구
# ─────────────────────────────────────────────────────────────
class TestSellRejectRoundTrip(_TempDbCase):

    SELL_META = {
        "bar": 1458, "reason": "EMA_DC", "bar_time": "2026-09-30T01:05:00+09:00",
        "entry_bar": 1389, "entry_price": 767.0, "bars_held": 69, "pnl_pct": -0.0209,
        "macd": 0.16, "signal": 0.31,
    }

    def _sell_rejected(self):
        trader = self._live_trader()
        sent = []
        with patch("core.trader._upbit_sell_market", return_value=_reject_call()), \
             patch("services.notifier.send", side_effect=lambda *a, **k: sent.append((a, k)) or True):
            res = trader.sell_market(QTY, TICKER, 751.0, meta=dict(self.SELL_META))
        return res, sent

    def test_step1_2_reject_row_created(self):
        res, _ = self._sell_rejected()
        self.assertEqual(res, {}, "거절 시 반환값은 기존대로 빈 dict (판정·흐름 무변경)")
        rows = self._rows("SELECT * FROM audit_trades WHERE ticker=?", (TICKER,))
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(r["type"], "SELL_REJECTED")
        self.assertEqual(r["reason"], "EMA_DC", "reason 은 신호 사유")
        self.assertAlmostEqual(r["price"], 751.0)
        self.assertAlmostEqual(r["qty"], QTY)
        self.assertAlmostEqual(r["entry_price"], 767.0)
        self.assertEqual(r["bars_held"], 69)
        self.assertEqual(r["bar_time"], "2026-09-30T01:05:00+09:00")
        self.assertEqual(r["note"], MUST_NOTE, "WO-11 확정 문구 그대로")
        self.assertIn(MUST_GUIDE, r["note"], "A2: 필수 안내 문구 포함")
        meta = json.loads(r["meta"])
        self.assertEqual(meta["error_name"], "insufficient_funds_ask")
        self.assertEqual(meta["http_status"], 400)
        self.assertIn("부족", meta["error_message"])
        # 기존 logs ERROR 기록 유지
        logs = self._rows("SELECT level, message FROM logs WHERE level='ERROR'")
        self.assertTrue(any("insufficient_funds_ask" in l["message"] for l in logs))
        # orders 에는 거절 행을 만들지 않음 (대시보드 최근 거래 손익 보호)
        self.assertEqual(self._rows("SELECT * FROM orders WHERE side='SELL'"), [])

    def test_a_alert_text_and_dedupe(self):
        _, sent = self._sell_rejected()
        crit = [(a, k) for a, k in sent if a[0] == "CRITICAL" and "매도 거절" in a[1]]
        self.assertEqual(len(crit), 1)
        (level, title, body), kw = crit[0]
        self.assertIn(TICKER, title)
        self.assertIn(MUST_GUIDE, body, "A2: insufficient_funds_ask 필수 문구")
        self.assertIn("EMA_DC", body, "신호 사유 표기")
        self.assertEqual(kw["dedupe_key"], f"sell_reject:{TICKER}:insufficient_funds_ask", "A1: 거절 코드 단위")
        self.assertEqual(kw["dedupe_ttl"], 300, "A1: TTL 300s")

    def test_step3_page_render_shows_reject(self):
        """감사 로그 페이지를 실제로 렌더 (Streamlit AppTest) — ⛔·한글 설명·거절 필터."""
        self._sell_rejected()
        from services.db import insert_trade_audit
        insert_trade_audit(self.USER, TICKER, 300, 1389, "BUY", "EMA_GC", 767.0, None, None,
                           None, None, None, None, None, None, None, None)
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(ROOT / "pages" / "audit_viewer.py"), default_timeout=60)
        at.query_params["user_id"] = self.USER
        at.query_params["tab"] = "trades"
        at.query_params["mode"] = "LIVE"
        at.query_params["ticker"] = "JTO"
        at.session_state["user_id"] = self.USER
        at.run()
        self.assertEqual([e.value for e in at.exception], [], "렌더 예외 없어야 함")
        self.assertTrue(any("⛔ 발주 거절 1건" in w.value for w in at.warning))
        df = at.dataframe[0].value
        self.assertIn("거절 사유", df.columns)
        rej = df[df["type"] == "⛔ 매도 거절"]
        self.assertEqual(len(rej), 1, "거절 행이 ⛔ 매도 거절 로 표시")
        self.assertIn(MUST_GUIDE, rej.iloc[0]["거절 사유"], "한글 설명이 화면에 그대로")
        self.assertIn("BUY", df["type"].tolist())
        # "거절" 필터만 선택 → 거절 행만 남음
        flt = next(m for m in at.multiselect if m.label == "유형 필터")
        self.assertIn("거절", flt.options)
        flt.set_value(["거절"]).run()
        self.assertEqual([e.value for e in at.exception], [])
        df2 = at.dataframe[0].value
        self.assertEqual(df2["type"].tolist(), ["⛔ 매도 거절"])
        # "매수"만 → 거절 행 사라짐
        next(m for m in at.multiselect if m.label == "유형 필터").set_value(["매수"]).run()
        self.assertEqual(at.dataframe[0].value["type"].tolist(), ["BUY"])

    def test_step4_excluded_from_pnl_and_buy_aggregates(self):
        from services.db import (
            insert_trade_audit, has_recent_bot_buy_for_ticker, get_position_entry_source,
            fetch_latest_trade_audit,
        )
        from services.settings_history import compute_pnl_for_snapshot
        with sqlite3.connect(self.db_path) as c:
            cur = c.execute(
                "INSERT INTO settings_history (user_id, saved_at, source_page, strategy_type, params_json, conditions_json) "
                "VALUES (?, ?, 'set_buy_sell_conditions', 'EMA', '{}', '{}')",
                (self.USER, "2026-01-01T00:00:00+09:00"),
            )
            sid = cur.lastrowid
        insert_trade_audit(self.USER, TICKER, 300, 1, "BUY", "EMA_GC", 767.0, None, None, None, None, None,
                           None, None, None, None, None, timestamp="2026-09-29T19:27:09+09:00", settings_history_id=sid)
        insert_trade_audit(self.USER, TICKER, 300, 2, "SELL", "EMA_DC", 756.0, None, None, 767.0, 1, 139,
                           None, None, None, None, None, timestamp="2026-09-30T07:20:13+09:00", settings_history_id=sid)
        before = compute_pnl_for_snapshot(self.USER, sid)
        # 거절 행 추가 (SELL/BUY 모두) — 같은 스냅샷 라벨
        trader = self._live_trader()
        with patch.object(trader, "_get_settings_history_id", return_value=sid), \
             patch("services.notifier.send", return_value=True), \
             patch("core.trader._upbit_sell_market", return_value=_reject_call()):
            trader.sell_market(QTY, TICKER, 751.0, meta=dict(self.SELL_META))
        after = compute_pnl_for_snapshot(self.USER, sid)
        self.assertEqual(before, after, "거절 행은 스냅샷 손익·통계에 포함되면 안 됨")
        # BUY 집계 함수는 거절 행 무시
        self.assertFalse(
            any(r["type"] == "BUY" for r in self._rows("SELECT type FROM audit_trades WHERE type LIKE '%REJECTED'"))
        )
        self.assertEqual(get_position_entry_source(self.USER, TICKER), "🤖 봇 매수")
        # 대시보드 최근 신호 카드 (A3): 거절 행 + note 반환
        latest = fetch_latest_trade_audit(self.USER, TICKER)
        self.assertEqual(latest["type"], "SELL_REJECTED")
        self.assertIn(MUST_GUIDE, latest["note"])


class TestBuyRejectRecords(_TempDbCase):
    """A7: 시장가 매수 실패 type BUY → BUY_REJECTED, 지정가 매수 거절도 기록."""

    def test_market_buy_reject_type(self):
        from services.db import has_recent_bot_buy_for_ticker
        trader = self._live_trader()
        with patch.object(trader, "_krw_balance", return_value=1_000_000.0), \
             patch.object(trader, "_current_risk_pct", return_value=0.1), \
             patch("core.trader._upbit_buy_market",
                   return_value=_reject_call("insufficient_funds_bid", "주문 가능한 금액(KRW)이 부족합니다.")), \
             patch("services.notifier.send", return_value=True):
            res = trader.buy_market(767.0, TICKER, meta={"reason": "EMA_GC", "bar": 10})
        self.assertEqual(res, {})
        rows = self._rows("SELECT type, reason, note, meta FROM audit_trades")
        self.assertEqual([(r["type"], r["reason"]) for r in rows], [("BUY_REJECTED", "EMA_GC")])
        self.assertIn("지정가 매수 주문", rows[0]["note"])
        self.assertEqual(json.loads(rows[0]["meta"])["order_type"], "market")
        self.assertFalse(has_recent_bot_buy_for_ticker(self.USER, TICKER, within_seconds=30),
                         "거절 행은 '최근 봇 매수'가 아님 (HTS 감지 제외 오작동 방지)")
        # orders FAILED 기록은 기존대로 유지
        self.assertEqual([r["state"] for r in self._rows("SELECT state FROM orders")], ["FAILED"])

    def test_limit_buy_reject_recorded(self):
        trader = self._live_trader()
        with patch.object(trader, "_krw_balance", return_value=1_000_000.0), \
             patch.object(trader, "_current_risk_pct", return_value=0.1), \
             patch("core.trader._upbit_buy_limit",
                   return_value=_reject_call("insufficient_funds_bid", "주문 가능한 금액(KRW)이 부족합니다.")), \
             patch("services.notifier.send", return_value=True):
            res = trader.buy_limit(767.0, TICKER, meta={"reason": "force_buy", "bar": 10})
        self.assertEqual(res, {})
        rows = self._rows("SELECT type, reason, qty, meta FROM audit_trades")
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["type"], rows[0]["reason"]), ("BUY_REJECTED", "force_buy"))
        self.assertGreater(rows[0]["qty"], 0)
        self.assertEqual(json.loads(rows[0]["meta"])["order_type"], "limit")


# ─────────────────────────────────────────────────────────────
# (b) 묶임 상태 WARNING 1회 + 대시보드 배지
# ─────────────────────────────────────────────────────────────
class TestLockedStateWarning(_TempDbCase):

    def _or(self, register=True):
        from engine.order_reconciler import OrderReconciler
        o = OrderReconciler(MagicMock(), balance_sync_interval=0.0)
        if register:
            o.register_hts_detect_callback(self.USER, TICKER, lambda **kw: None)
        return o

    def _warns(self, sent):
        return [a for a, k in sent if a[0] == "WARNING" and "매도 불가" in a[1]]

    def test_warn_once_then_clear(self):
        from services.db import get_position_meta, update_coin_position
        update_coin_position(self.USER, TICKER, QTY, 0.0, entry_price=767.0)
        o = self._or()
        sent = []
        with patch("services.notifier.send", side_effect=lambda *a, **k: sent.append((a, k)) or True):
            o._check_locked_state(self.USER, TICKER, QTY, 0.0)       # 정상
            o._check_locked_state(self.USER, TICKER, 0.0, QTY)       # 전량 묶임 → WARN
            o._check_locked_state(self.USER, TICKER, 0.0, QTY)       # 지속 → 재발송 없음
            self.assertEqual(len(self._warns(sent)), 1)
            self.assertIn(MUST_GUIDE, self._warns(sent)[0][2])
            self.assertTrue(get_position_meta(self.USER, TICKER).get("locked_warned"))
            o._check_locked_state(self.USER, TICKER, QTY, 0.0)       # 해제 → 표식 삭제
            self.assertFalse(get_position_meta(self.USER, TICKER).get("locked_warned"))
            o._check_locked_state(self.USER, TICKER, 0.0, QTY)       # 다시 묶임 → 다시 WARN
        self.assertEqual(len(self._warns(sent)), 2)

    def test_periodic_sync_call_site(self):
        """주기 잔고 동기화 경로에서 실제로 _check_locked_state 가 불려 WARNING 1회."""
        from services.db import update_coin_position
        update_coin_position(self.USER, TICKER, QTY, 0.0, entry_price=767.0)
        o = self._or()
        o._live_user_ids.add(self.USER)
        o.upbit.get_balances.return_value = [
            {"currency": "KRW", "balance": "0", "locked": "0", "avg_buy_price": "0"},
            {"currency": "JTO", "balance": "0", "locked": str(QTY), "avg_buy_price": "767"},
        ]
        sent = []
        with patch("services.notifier.send", side_effect=lambda *a, **k: sent.append((a, k)) or True):
            o._last_balance_sync = 0.0
            o._periodic_balance_sync()
            o._last_balance_sync = 0.0
            o._periodic_balance_sync()
        self.assertEqual(len(self._warns(sent)), 1)

    def test_unwatched_ticker_and_bot_pending_sell_skipped(self):
        sent = []
        with patch("services.notifier.send", side_effect=lambda *a, **k: sent.append((a, k)) or True):
            self._or(register=False)._check_locked_state(self.USER, TICKER, 0.0, QTY)
            o = self._or()
            o.enqueue("uuid-bot-sell", user_id=self.USER, ticker=TICKER, side="SELL")
            o._check_locked_state(self.USER, TICKER, 0.0, QTY)
        self.assertEqual(self._warns(sent), [], "외부 전용 코인·봇 매도 체결 대기는 경고 대상 아님")

    def test_dashboard_badge_and_wo7_condition(self):
        src = (ROOT / "pages" / "dashboard.py").read_text(encoding="utf-8")
        i_metric = src.index('st.metric(f"{_ticker} 보유량"')
        i_badge = src.index("⛔ 매도 불가 — 앱 지정가 매도 주문으로 수량 묶임 ({locked_qty:,.6f}개)")
        i_wo7 = src.index("get_position_entry_source(user_id, _ticker)")
        self.assertLess(i_metric, i_badge)
        self.assertLess(i_badge, i_wo7, "표시 순서: metric → (b) 배지 → WO-7 배지")
        self.assertIn("if (qty + locked_qty) > 0:", src[i_badge:i_wo7], "A4: WO-7 조건 가용+묶임 합계")


# ─────────────────────────────────────────────────────────────
# (d) 감사 임계·trigger_reason 정정 (기록만)
# ─────────────────────────────────────────────────────────────
class TestAuditThresholdSource(unittest.TestCase):

    def test_sell_audit_uses_strategy_thresholds_and_actual_reason(self):
        from core.strategy_engine import StrategyEngine
        from core.strategy_incremental import Action
        from core.position_state import PositionState

        pos = PositionState()
        pos._has_position = True
        pos.avg_price = 767.0
        pos.qty = QTY
        pos.entry_bar = 1389
        eng = MagicMock()
        eng.strategy_type = "EMA"
        eng.position = pos
        eng.user_id, eng.ticker, eng.interval_sec, eng.bar_count = "u", TICKER, 300, 1458
        eng.take_profit, eng.stop_loss, eng.trailing_stop_pct = 0.025, 0.015, 0.3  # 엔진 생성 시점 값
        eng.strategy = SimpleNamespace(stop_loss=0.03, take_profit=0.05,          # 실제 필터 값
                                       last_sell_reason="EMA_DC", last_filter_result=None)
        bar = SimpleNamespace(close=751.0, ts=datetime(2026, 9, 29, 16, 5, tzinfo=timezone.utc), is_confirmed=True)
        ind = {"ema_fast": 759.06, "ema_slow": 759.18, "ema_base": 759.18,
               "ema_fast_sell": 759.06, "ema_slow_sell": 759.18,
               "prev_ema_fast": 759.34, "prev_ema_slow": 759.26}
        captured = {}
        with patch("core.strategy_engine.insert_sell_eval", side_effect=lambda **kw: captured.update(kw)):
            StrategyEngine._record_audit_log(eng, bar, ind, Action.SELL)
        self.assertTrue(captured, "insert_sell_eval 호출돼야 함")
        self.assertAlmostEqual(captured["sl_price"], 767.0 * 0.97, places=6, msg="실제 필터 3.0% 기준")
        self.assertAlmostEqual(captured["tp_price"], 767.0 * 1.05, places=6)
        self.assertEqual(captured["trigger_key"], "EMA_DC", "실제 사유 우선 (sl 1.5% 오판 STOP_LOSS 아님)")
        self.assertEqual(captured["checks"]["trigger_reason"], "EMA_DC")
        self.assertEqual(captured["checks"]["sl_hit"], 0, "751 > 744.0 → 3.0% 기준 손절 아님")


if __name__ == "__main__":
    unittest.main()
