"""
✅ WO-24 회귀: 현재가 매수 미체결 취소 감사 기록 + 미체결 시 시장가 전환 옵션 + 알림 성공 로그 (2026-10-05)

근거 (docs/plans/2026-10-05-urgent-buy-not-executed/report.md):
- 10-04 14:15 봉 BUY 평가 통과(overall_ok=1) → 현재가 매수 763 지정가 → 대기 5봉(295초) 미체결 → 자동 취소 (orders 559).
- 감사 로그 페이지에는 🟢 BUY 평가만 보이고 거래 기록이 없어 "신호는 떴는데 안 샀다" 로 보였다.
처방:
- 취소 확정 때 audit_trades type='BUY_CANCELED' ("⏱ 매수 미체결 취소") 1행 — 주문가·주문 수량·체결 수량·대기·사유·uuid.
- 옵션 "미체결 시 시장가 전환"(기본 끔): 현재가 ≤ 주문가 × (1 + 허용 %) 이면 남은 수량을 기존 시장가 매수로, apply_entry 등록.
- notifier 발송 성공 시 "[NOTIFY] sent | kind=… dedupe=…" 1줄.

실행:
    python3 -m unittest tests.regressions.test_r_2026_10_05_wo24_unfilled_buy_audit -v
"""
from __future__ import annotations

import json
import shutil
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

U = "test_r_2026_10_05_wo24"
T = "KRW-JTO"
ORDER_QTY = "1063.46564595"
META = {"bar": 332, "reason": "EMA_GC", "bar_time": "2026-10-04T14:15:00+09:00", "fixed_price_buy": True,
        "is_fixed_price_buy": True, "interval_sec": 300, "limit_price": 763.0, "wait_bars": 5}


class _DbCase(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="wo24_"))
        self.db_path = str(self.tmpdir / f"tradebot_{U}.db")
        self._patchers = [
            patch("services.init_db.get_db_path", return_value=self.db_path),
            patch("services.db.get_db_path", return_value=self.db_path),
            patch("services.notifier.send", MagicMock(return_value=True)),
            # 시험은 네트워크에 의존하지 않는다: 실제 현재가 조회가 불리면 실패
            patch("services.trading_control.get_current_price_from_upbit",
                  MagicMock(side_effect=AssertionError("시험 중 실제 현재가 조회 금지"))),
        ]
        for p in self._patchers:
            p.start()
        from services.init_db import initialize_db, ensure_all_schemas
        from services.db import ensure_schema
        initialize_db(U)
        ensure_all_schemas(U)
        ensure_schema(U)
        import core.strategy_engine as se
        self.se = se
        self._saved_engines = dict(se._active_engines)
        se._active_engines.clear()

    def tearDown(self):
        self.se._active_engines.clear()
        self.se._active_engines.update(self._saved_engines)
        for p in self._patchers:
            p.stop()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _sql(self, q, args=()):
        con = sqlite3.connect(self.db_path)
        r = con.execute(q, args).fetchall()
        con.close()
        return r

    def _orc(self, uuid="u-559"):
        from engine.order_reconciler import OrderReconciler
        upbit = MagicMock()
        upbit.get_balances.return_value = []
        upbit.cancel_order.return_value = {"uuid": uuid, "state": "wait"}
        orc = OrderReconciler(upbit)
        con = sqlite3.connect(self.db_path)
        con.execute("INSERT INTO orders (user_id, timestamp, ticker, side, price, volume, status, provider_uuid, state, requested_at, meta) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (U, "2026-10-04T14:16:12+09:00", T, "BUY", 763.0, 0, "requested", uuid, "REQUESTED",
                     "2026-10-04T14:16:12+09:00", json.dumps(META)))
        con.commit()
        con.close()
        orc._pending[uuid] = {"user_id": U, "ticker": T, "side": "BUY", "meta": dict(META), "enqueued_at": time.time() - 296.4}
        return orc

    def _engine(self, enabled, gap_pct=0.3):
        from core.position_state import PositionState
        eng = SimpleNamespace()
        eng.strategy = SimpleNamespace(buy_conditions={"fixed_price_buy_enabled": True, "fixed_price_buy_wait_bars": 5,
                                                       "fixed_price_unfilled_to_market": enabled,
                                                       "fixed_price_convert_max_gap_pct": gap_pct})
        eng._execution_lock = threading.Lock()
        eng.position = PositionState()
        eng.trader = MagicMock()
        eng.trader.buy_market = MagicMock(side_effect=lambda price, ticker, ts=None, meta=None, krw_amount=None:
                                          {"qty": round(krw_amount / price, 8), "price": price, "uuid": "m-conv"})
        eng.bar_count = 337
        eng._pending_buy_uuid, eng._pending_buy_bar, eng._pending_buy_wait_bars = "u-559", 332, 5
        self.se._active_engines[(U, T)] = eng
        return eng

    def _timeout_then_cancel(self, orc, uuid="u-559", exec_vol="0", trades=None, avg="0"):
        orc._maybe_cancel_fixed_price_buy(uuid)
        orc._handle(uuid, {"state": "cancel", "volume": ORDER_QTY, "executed_volume": exec_vol, "avg_price": avg,
                           "paid_fee": "0", "price": "763", "trades": trades or []})

    def _canceled_rows(self):
        return self._sql("SELECT type, reason, price, qty, note, meta, bar_time FROM audit_trades WHERE type='BUY_CANCELED'")


class TestWo24(_DbCase):

    def test_1_timeout_cancel_records_buy_canceled(self):
        """(1) timeout 취소 확정 → BUY_CANCELED 1행: 주문가 763·주문 수량·체결 0·대기 5봉·사유·uuid."""
        orc = self._orc()
        self._timeout_then_cancel(orc)
        rows = self._canceled_rows()
        self.assertEqual(len(rows), 1)
        typ, reason, price, qty, note, meta, bt = rows[0]
        self.assertEqual((typ, reason, price, bt), ("BUY_CANCELED", "BUY_CANCELED", 763.0, "2026-10-04T14:15:00+09:00"))
        self.assertAlmostEqual(qty, float(ORDER_QTY))
        self.assertTrue(note.startswith("대기 5봉 내 체결 없음"), note)
        m = json.loads(meta)
        self.assertEqual((m["uuid"], m["executed_qty"], m["wait_bars"]), ("u-559", 0.0, 5))
        self.assertGreaterEqual(m["waited_sec"], 295)
        self.assertEqual(self._sql("SELECT state FROM orders WHERE provider_uuid='u-559'")[0][0], "CANCELED")

    def test_2_partial_fill_then_cancel_records_executed_qty(self):
        """(2) 부분 체결 300개 뒤 취소 → BUY_CANCELED 에 체결 수량 300, 사유 '일부만 체결'."""
        orc = self._orc()
        self._timeout_then_cancel(orc, exec_vol="300", avg="763",
                                  trades=[{"created_at": "2026-10-04T14:18:00+09:00", "volume": "300", "funds": "228900", "fee": "0"}])
        rows = self._canceled_rows()
        self.assertEqual(len(rows), 1)
        m = json.loads(rows[0][5])
        self.assertEqual(m["executed_qty"], 300.0)
        self.assertAlmostEqual(m["remaining_qty"], float(ORDER_QTY) - 300.0)
        self.assertIn("일부만 체결", rows[0][4])

    def test_3_option_off_cancel_only(self):
        """(3) 옵션 끔 → 시장가 매수 없음, 취소만 (사유 '미체결 시 시장가 전환 꺼짐')."""
        eng = self._engine(enabled=False)
        orc = self._orc()
        self._timeout_then_cancel(orc)
        eng.trader.buy_market.assert_not_called()
        self.assertFalse(eng.position.has_position)
        self.assertIn("→ 취소 (미체결 시 시장가 전환 꺼짐)", self._canceled_rows()[0][4])

    def test_4_option_on_small_gap_converts_once(self):
        """(4) 옵션 켬·가격 차이 0.1% → 시장가 전환 1회 (KRW = 남은 수량 × 현재가), apply_entry 등록, pending 해제."""
        eng = self._engine(enabled=True, gap_pct=0.3)
        cur = 763.0 * 1.001
        orc = self._orc()
        with patch("services.trading_control.get_current_price_from_upbit", MagicMock(return_value=cur)), \
                self.assertLogs("core.position_state", level="INFO") as cm:
            self._timeout_then_cancel(orc)
        eng.trader.buy_market.assert_called_once()
        kw = eng.trader.buy_market.call_args.kwargs
        self.assertAlmostEqual(kw["krw_amount"], float(ORDER_QTY) * cur, places=4)
        self.assertTrue(kw["meta"]["unfilled_convert"])
        self.assertEqual(kw["meta"]["converted_from"], "u-559")
        self.assertTrue(eng.position.has_position)
        self.assertAlmostEqual(eng.position.avg_price, cur)
        self.assertTrue(any("[POSITION-APPLY] source=bot_market_convert" in m for m in cm.output))
        self.assertIsNone(eng._pending_buy_uuid)
        self.assertIn("→ 시장가 전환", self._canceled_rows()[0][4])

    def test_5_option_on_large_gap_no_convert(self):
        """(5) 옵션 켬·가격 차이 0.5% > 허용 0.3% → 전환 안 함, 사유 '가격 차이 0.50% > 허용 0.30%'."""
        eng = self._engine(enabled=True, gap_pct=0.3)
        orc = self._orc()
        with patch("services.trading_control.get_current_price_from_upbit", MagicMock(return_value=763.0 * 1.005)):
            self._timeout_then_cancel(orc)
        eng.trader.buy_market.assert_not_called()
        self.assertFalse(eng.position.has_position)
        self.assertIn("가격 차이 0.50% > 허용 0.30%", self._canceled_rows()[0][4])

    def test_6_audit_view_maps_new_type(self):
        """(6) 감사 로그 표시 함수: BUY_CANCELED → '⏱ 매수 미체결 취소', 유형 필터 '미체결 취소' (거절과 구분)."""
        from services.db import trade_type_display, trade_kind, is_reject_type
        self.assertEqual(trade_type_display("BUY_CANCELED"), "⏱ 매수 미체결 취소")
        self.assertEqual(trade_kind("BUY_CANCELED"), "미체결 취소")
        self.assertFalse(is_reject_type("BUY_CANCELED"))
        src = (ROOT / "pages" / "audit_viewer.py").read_text(encoding="utf-8")
        self.assertIn('_kind_options = ["매수", "매도", "거절", "미체결 취소"]', src)

    def test_7_notifier_success_log(self):
        """(7) notifier 발송 성공 → '[NOTIFY] sent | kind=… dedupe=…' INFO 1줄, 토큰·채팅 ID 미기록."""
        for p in list(self._patchers):
            if getattr(p, "attribute", "") == "send":
                p.stop()                       # 실제 send 를 시험 (네트워크·자격증명은 아래에서 패치)
                self._patchers.remove(p)
        import services.notifier as nt
        resp = MagicMock(status_code=200, text="ok")
        with patch.object(nt, "_get_credentials", return_value=("TOKEN-SECRET-123", "CHAT-999")), \
                patch.object(nt, "_requests", MagicMock(post=MagicMock(return_value=resp))), \
                patch.object(nt, "_should_skip_by_dedupe", return_value=False), \
                self.assertLogs("services.notifier", level="INFO") as cm:
            self.assertTrue(nt.send("WARNING", "제목", "본문", dedupe_key="fixed_buy_timeout:u-559"))
        sent = [m for m in cm.output if "[NOTIFY] sent" in m]
        self.assertEqual(len(sent), 1)
        self.assertIn("[NOTIFY] sent | kind=WARNING dedupe=fixed_buy_timeout:u-559", sent[0])
        self.assertNotIn("TOKEN-SECRET-123", "\n".join(cm.output))
        self.assertNotIn("CHAT-999", "\n".join(cm.output))


if __name__ == "__main__":
    unittest.main()
