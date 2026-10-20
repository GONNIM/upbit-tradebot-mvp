"""
✅ WO-26 회귀: 약매수 차단 필터 (2026-10-20)

근거 (docs/plans/2026-10-20-wo26-weak-entry-filter/report.md · prd.md):
- KRW-JTO 30일 G/C 44건 중 직전 D/C 2시간 안 12건. 봇 실매수 평균 −0.64%(2/8 이익), 익절 0.3~1.5% 모의 모두 음수.
- Fable 결정: 기본 "매수 안 함"(block) · 2시간 · 축소 익절 0.5%, D/C 기준선 = 매도 EMA 쌍,
  직전 D/C 를 모르면 일반 매수 + [WARMUP] "직전 D/C 알 수 없음".
시험 (1)~(12) 은 WO-26 지시 G 항목 번호와 같다.

실행:
    python3 -m unittest tests.regressions.test_r_2026_10_20_wo26_weak_entry_filter -v
"""
from __future__ import annotations

import csv
import json
import shutil
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

U = "test_r_2026_10_20_wo26"
T = "KRW-JTO"
KST = ZoneInfo("Asia/Seoul")
GC_TS = datetime(2026, 10, 12, 7, 37, tzinfo=timezone.utc)  # = 10-12 16:37 KST (측정 G/C)
FIXTURE = ROOT / "tests" / "regressions" / "fixtures" / "wo26_m1_1000.csv"
OUTCOMES = ROOT / "docs" / "plans" / "2026-10-20-wo26-weak-entry-filter" / "wo26_gc_outcomes.csv"

BUY_COND = {"ema_gc": True, "above_base_ema": False, "bullish_candle": False, "surge_filter_enabled": False,
            "fixed_price_buy_enabled": False}
SELL_COND = {"stop_loss": True, "take_profit": True, "trailing_stop": True, "ema_dc": True,
             "stale_position_check": False, "stop_loss_pct": 1.0, "take_profit_pct": 1.0,
             "trailing_stop_threshold_pct": 30.0, "use_fixed_trailing": True}


def _strategy(**weak):
    from core.strategy_incremental import IncrementalEMAStrategy
    bc = dict(BUY_COND, **weak)
    return IncrementalEMAStrategy(user_id=U, ticker=T, take_profit=0.01, stop_loss=0.01,
                                  buy_conditions=bc, sell_conditions=dict(SELL_COND))


def _bar(ts=GC_TS, close=778.0, open_=776.0):
    from core.candle_buffer import Bar
    return Bar(ts=ts, open=open_, high=close, low=open_, close=close, volume=1.0, is_closed=True)


def _gc_indicators(last_dc):
    return {"ema_fast": 770.42, "ema_slow": 770.41, "ema_base": 770.41, "prev_ema_fast": 770.39,
            "prev_ema_slow": 770.40, "macd": 0.0, "signal": 0.0, "bar_count": 10,
            "last_dead_cross_ts": last_dc, "use_separate_ema": True,
            "ema_fast_buy": 770.42, "ema_slow_buy": 770.41, "ema_fast_sell": 770.42, "ema_slow_sell": 770.41}


def _ind(fast=60, slow=200):
    from core.indicator_state import IndicatorState
    return IndicatorState(macd_fast=fast, macd_slow=slow, macd_signal=9, ema_fast=fast, ema_slow=slow, base_ema=200,
                          use_separate_ema=True, ema_fast_buy=fast, ema_slow_buy=slow,
                          ema_fast_sell=fast, ema_slow_sell=slow)


def _fixture():
    rows = list(csv.DictReader(open(FIXTURE)))
    ts = [pd.Timestamp(r["ts_kst"]).tz_localize(KST).tz_convert("UTC") for r in rows]
    return ts, [float(r["close"]) for r in rows]


class _DbCase(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="wo26_"))
        self.db_path = str(self.tmpdir / f"tradebot_{U}.db")
        self._patchers = [
            patch("services.init_db.get_db_path", return_value=self.db_path),
            patch("services.db.get_db_path", return_value=self.db_path),
            patch("services.notifier.send", MagicMock(return_value=True)),
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

    def _sql(self, q, args=()):
        con = sqlite3.connect(self.db_path)
        rows = con.execute(q, args).fetchall()
        con.commit()
        con.close()
        return rows

    def _order(self, uuid, ts="2026-10-12T16:38:05+09:00"):
        self._sql("INSERT INTO orders (user_id, timestamp, ticker, side, price, volume, status, provider_uuid, state, "
                  "requested_at, executed_at, executed_volume, avg_price, updated_at, entry_bar) "
                  "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  (U, ts, T, "BUY", 778.0, 0, "requested", uuid, "FILLED", ts, ts, 10.0, 778.0, ts, 100))

    def _meta(self):
        r = self._sql("SELECT meta FROM account_positions WHERE user_id=? AND ticker=?", (U, T))
        return json.loads(r[0][0]) if r and r[0][0] else {}

    def _position(self):
        from core.position_state import PositionState
        trader = MagicMock()
        trader.user_id = U
        trader.test_mode = True
        return PositionState(trader=trader, ticker=T)


class _MiniEngine:
    """StrategyEngine 의 메서드를 그대로 붙인 최소 엔진."""

    def __init__(self, strategy, position, trader=None):
        from core.strategy_engine import StrategyEngine
        self.strategy, self.position = strategy, position
        self.strategy_type, self.user_id, self.ticker = "EMA", U, T
        self.bar_count, self.interval_sec, self.q = 100, 60, None
        self.take_profit, self.stop_loss = 0.01, 0.01
        self.trader = trader or MagicMock()
        self._pending_buy_uuid = self._pending_buy_bar = None
        self._pending_buy_wait_bars, self._pending_buy_weak = 3, None
        import threading
        self._execution_lock = threading.RLock()
        for name in ("_record_audit_log", "_execute_buy", "_execute_sell", "_on_limit_fill", "_on_hts_detect",
                     "_audit_buy_blocked"):
            fn = getattr(StrategyEngine, name, None)
            if fn is not None:
                setattr(self, name, fn.__get__(self))


class TestWo26(_DbCase):

    # (1) D/C 뒤 1.5h G/C + block → HOLD · 감사 사유
    def test_01_block_within_window(self):
        from core.strategy_action import Action
        from core.position_state import PositionState
        st = _strategy(weak_entry_filter_enabled=True, weak_entry_window_hours=2.0, weak_entry_mode="block")
        pos = PositionState()
        ind = _gc_indicators(GC_TS - timedelta(minutes=90))
        act = st.on_bar(_bar(), ind, pos, 100)
        self.assertEqual(act, Action.HOLD)
        self.assertEqual(st.last_buy_filter_result.reason, "WEAK_ENTRY_FILTER")
        self.assertEqual(st.last_buy_filter_result.details, "약매수 차단 (D/C 뒤 90분, 기준 2시간)")
        eng = _MiniEngine(st, pos)
        eng._record_audit_log(_bar(), ind, act)
        fk, notes = self._sql("SELECT failed_keys, notes FROM audit_buy_eval ORDER BY id DESC LIMIT 1")[0]
        self.assertEqual(json.loads(fk), ["WEAK_ENTRY_FILTER"])
        self.assertIn("약매수 차단 (D/C 뒤 90분, 기준 2시간)", notes)

    # (2) 2.5h → 일반 매수
    def test_02_outside_window_buys(self):
        from core.strategy_action import Action
        from core.position_state import PositionState
        st = _strategy(weak_entry_filter_enabled=True, weak_entry_window_hours=2.0, weak_entry_mode="block")
        act = st.on_bar(_bar(), _gc_indicators(GC_TS - timedelta(minutes=150)), PositionState(), 100)
        self.assertEqual(act, Action.BUY)
        self.assertIsNone(st.last_weak_entry)
        # 끔 · 0시간 · 직전 D/C 모름 → 일반 매수
        for kw, last in (({"weak_entry_filter_enabled": False}, GC_TS - timedelta(minutes=30)),
                         ({"weak_entry_filter_enabled": True, "weak_entry_window_hours": 0.0}, GC_TS - timedelta(minutes=30)),
                         ({"weak_entry_filter_enabled": True}, None)):
            self.assertEqual(_strategy(**kw).on_bar(_bar(), _gc_indicators(last), PositionState(), 100), Action.BUY, kw)

    # (3) reduce_tp → 매수 · override 0.5% · meta 기록 (시장가 · 지정가 체결)
    def test_03_reduce_tp_records_override_and_meta(self):
        from core.strategy_action import Action
        st = _strategy(weak_entry_filter_enabled=True, weak_entry_window_hours=2.0, weak_entry_mode="reduce_tp",
                       weak_entry_tp_pct=0.005)
        pos = self._position()
        ind = _gc_indicators(GC_TS - timedelta(minutes=84))
        self.assertEqual(st.on_bar(_bar(), ind, pos, 100), Action.BUY)
        self.assertEqual(st.last_weak_entry, {"tp": 0.005, "elapsed_min": 84, "window_h": 2.0})
        trader = MagicMock()
        trader.test_mode = True
        trader.buy_market = MagicMock(return_value={"qty": 10.0, "price": 778.0, "uuid": "u-w1"})
        eng = _MiniEngine(st, pos, trader)
        eng._execute_buy(_bar(), ind)
        sent_meta = trader.buy_market.call_args.kwargs["meta"]  # → live 경로 orders.meta (core/trader.py insert_order meta=meta_json)
        self.assertEqual(sent_meta["weak_entry"], {"tp": 0.005, "elapsed_min": 84, "window_h": 2.0})
        self.assertEqual(sent_meta["audit_note"], "약매수 진입 · 익절 0.5%")
        self.assertEqual(pos.take_profit_override, 0.005)
        m = self._meta()["weak_entry"]
        self.assertEqual((m["tp"], m["elapsed_min"], m["window_h"], m["order_uuid"]), (0.005, 84, 2.0, "u-w1"))
        self.assertEqual(m["bar_time"], "2026-10-12T16:37:00+09:00")

        # 지정가 체결 경로: 주문 대기 → _on_limit_fill(uuid 일치) → override·meta
        st2 = _strategy(weak_entry_filter_enabled=True, weak_entry_mode="reduce_tp", weak_entry_tp_pct=0.007)
        pos2 = self._position()
        st2.on_bar(_bar(), ind, pos2, 100)
        trader2 = MagicMock()
        trader2.test_mode = False
        trader2.buy_limit = MagicMock(return_value={"limit_pending": True, "uuid": "u-lim", "price": 778.0})
        st2.buy_conditions = dict(st2.buy_conditions, fixed_price_buy_enabled=True)
        eng2 = _MiniEngine(st2, pos2, trader2)
        eng2._execute_buy(_bar(), ind)
        self.assertIsNone(pos2.take_profit_override, "체결 전에는 설정하지 않음")
        eng2._on_limit_fill(uuid="u-lim", executed_price=778.0, executed_qty=10.0,
                            executed_ts=datetime(2026, 10, 12, 16, 38, tzinfo=KST))
        self.assertEqual(pos2.take_profit_override, 0.007)
        self.assertEqual(self._meta()["weak_entry"]["order_uuid"], "u-lim")

    def test_03b_buy_eval_note(self):
        from core.strategy_action import Action
        from core.position_state import PositionState
        st = _strategy(weak_entry_filter_enabled=True, weak_entry_mode="reduce_tp", weak_entry_tp_pct=0.005)
        pos = PositionState()
        ind = _gc_indicators(GC_TS - timedelta(minutes=30))
        self.assertEqual(st.on_bar(_bar(), ind, pos, 100), Action.BUY)
        _MiniEngine(st, pos)._record_audit_log(_bar(), ind, Action.BUY)
        ok, notes, checks = self._sql("SELECT overall_ok, notes, checks FROM audit_buy_eval ORDER BY id DESC LIMIT 1")[0]
        self.assertEqual(ok, 1)
        self.assertIn("약매수 진입 · 익절 0.5%", notes)
        from core.weak_entry import weak_entry_display
        self.assertEqual(weak_entry_display([], json.loads(checks)), "🐢 약매수 진입 · 익절 0.5%")
        self.assertEqual(weak_entry_display(["WEAK_ENTRY_FILTER"], {"filter_details": "약매수 차단 (D/C 뒤 5분, 기준 2시간)"}),
                         "🐢 약매수 차단 (D/C 뒤 5분, 기준 2시간)")

    # (4) override 포지션에서 TP 필터 0.5% 발동
    def test_04_take_profit_uses_override(self):
        from core.filters.sell_filters import TakeProfitFilter
        from core.position_state import PositionState
        pos = PositionState()
        pos.apply_entry(qty=10.0, avg_price=600.0, entry_bar=1, entry_ts=datetime(2026, 10, 20, tzinfo=KST), source="bot_market")
        f = TakeProfitFilter(take_profit_pct=0.01)
        self.assertFalse(f.evaluate(position=pos, current_price=603.0).should_block, "override 없음 → 1% 기준")
        pos.take_profit_override = 0.005
        r = f.evaluate(position=pos, current_price=603.0)
        self.assertTrue(r.should_block)
        self.assertEqual((r.reason, r.metadata["threshold"]), ("TAKE_PROFIT", 0.005))
        self.assertFalse(f.evaluate(position=pos, current_price=602.9).should_block)

    def test_04b_sell_row_note(self):
        """매도 행 비고 "약매수 포지션 · 기준 0.5%" (주문 meta.audit_note → audit_trades.note)."""
        pos = self._position()
        pos.apply_entry(qty=10.0, avg_price=600.0, entry_bar=1, entry_ts=datetime(2026, 10, 20, tzinfo=KST), source="bot_market")
        pos.take_profit_override = 0.005
        st = _strategy()
        st.last_sell_reason = "TAKE_PROFIT"
        trader = MagicMock()
        trader.sell_market = MagicMock(return_value={"qty": 10.0, "price": 603.0})
        eng = _MiniEngine(st, pos, trader)
        eng._execute_sell(_bar(close=603.0), _gc_indicators(None))
        self.assertEqual(trader.sell_market.call_args.kwargs["meta"]["audit_note"], "약매수 포지션 · 기준 0.5%")
        self.assertIsNone(pos.take_profit_override, "청산 뒤 덮어쓰기 해제")

    # (5) override 포지션에서 트레일링 무장 0.5% (실시간 · 재시작 재계산)
    def test_05_trailing_arms_at_override(self):
        from core.filters.sell_filters import TrailingStopFilter
        from core.position_state import PositionState
        from core.trailing_restore import replay_trailing
        f = TrailingStopFilter(trailing_stop_pct=0.3, take_profit_pct=0.01, use_fixed_mode=True)
        pos = PositionState()
        pos.apply_entry(qty=10.0, avg_price=600.0, entry_bar=1, entry_ts=datetime(2026, 10, 20, tzinfo=KST), source="bot_market")
        f.advance_state(pos, 603.0, log=False)
        self.assertFalse(pos.trailing_armed, "override 없음 → 1% 전 무장 안 함")
        pos.take_profit_override = 0.005
        f.advance_state(pos, 603.0, log=False)
        self.assertTrue(pos.trailing_armed)
        self.assertAlmostEqual(pos.trailing_fixed_amount, 0.9)  # (603−600)×30%
        pos2 = PositionState()
        pos2.apply_entry(qty=10.0, avg_price=600.0, entry_bar=1, entry_ts=datetime(2026, 10, 20, tzinfo=KST), source="boot_seed")
        pos2.take_profit_override = 0.005
        replay_trailing(pos2, f, [(None, 601.0), (None, 603.0), (None, 604.0)], min_holding_period=0)
        self.assertTrue(pos2.trailing_armed, "재시작 재계산도 축소 기준에서 무장")

    # (6) 재시작 복원: uuid 일치 → 복원, 불일치 → 삭제·WARNING
    def test_06_restore_match_and_mismatch(self):
        from services.db import set_position_weak_entry
        from engine.live_loop import _apply_boot_seed
        self._order("u-w1")
        set_position_weak_entry(U, T, {"tp": 0.005, "elapsed_min": 84, "window_h": 2.0, "order_uuid": "u-w1",
                                       "bar_time": "2026-10-12T16:37:00+09:00"})
        pos = self._position()
        pos.avg_price = 778.0
        _apply_boot_seed(pos, {"price": 778.0, "entry_bar": 100, "entry_ts_iso": "2026-10-12T16:38:05+09:00"}, 10.0)
        self.assertEqual(pos.take_profit_override, 0.005)
        self.assertIn("weak_entry", self._meta())

        set_position_weak_entry(U, T, {"tp": 0.005, "elapsed_min": 84, "window_h": 2.0, "order_uuid": "u-old",
                                       "bar_time": "2026-10-11T10:00:00+09:00"})
        pos2 = self._position()
        pos2.avg_price = 778.0
        with self.assertLogs("core.weak_entry", level="WARNING") as cm:
            _apply_boot_seed(pos2, {"price": 778.0, "entry_bar": 100, "entry_ts_iso": "2026-10-12T16:38:05+09:00"}, 10.0)
        self.assertIsNone(pos2.take_profit_override)
        self.assertNotIn("weak_entry", self._meta())
        self.assertTrue(any("표식이 마지막 봇 BUY 와 다름 → 삭제" in m and "meta_uuid=u-old" in m for m in cm.output))

    def test_06b_wallet_sync_restore(self):
        from services.db import set_position_weak_entry
        from core.strategy_engine import StrategyEngine
        self._order("u-w1")
        set_position_weak_entry(U, T, {"tp": 0.006, "elapsed_min": 10, "window_h": 2.0, "order_uuid": "u-w1",
                                       "bar_time": "2026-10-12T16:37:00+09:00"})
        eng = _MiniEngine(_strategy(), self._position())
        eng.trader = MagicMock()
        eng.trader.test_mode = False
        eng.trader._coin_balance = MagicMock(return_value=10.0)
        eng.trader.upbit.get_balances = MagicMock(return_value=[{"currency": "JTO", "balance": "10", "avg_buy_price": "778"}])
        for name in ("_reconcile_position_with_wallet", "_fetch_upbit_avg_buy_price", "_record_external_sell"):
            setattr(eng, name, getattr(StrategyEngine, name).__get__(eng))
        eng._reconcile_position_with_wallet()
        self.assertTrue(eng.position.has_position)
        self.assertEqual(eng.position.take_profit_override, 0.006)

    # (7) HTS_BUY_ADD → override 삭제 (+ 청산 · 기동 정합 검사)
    def test_07_hts_buy_add_and_close_clear(self):
        from core.weak_entry import record_weak_entry
        from services.db import clear_stale_weak_entries, set_position_weak_entry
        pos = self._position()
        pos.apply_entry(qty=10.0, avg_price=778.0, entry_bar=1, entry_ts=datetime(2026, 10, 12, 16, 38, tzinfo=KST), source="bot_market")
        record_weak_entry(pos, {"tp": 0.005, "elapsed_min": 84, "window_h": 2.0}, "u-w1", "2026-10-12T16:37:00+09:00")
        eng = _MiniEngine(_strategy(), pos)
        eng._on_hts_detect(avg_price=777.5, qty=12.0, reason="HTS_BUY_ADD")
        self.assertIsNone(pos.take_profit_override)
        self.assertNotIn("weak_entry", self._meta())

        record_weak_entry(pos, {"tp": 0.005, "elapsed_min": 84, "window_h": 2.0}, "u-w2", None)
        pos.close_position(ts=None, reason="bot_sell")
        self.assertIsNone(pos.take_profit_override)
        self.assertNotIn("weak_entry", self._meta())

        set_position_weak_entry(U, T, {"tp": 0.005, "order_uuid": "u-x"})  # 보유 0 (virtual_coin 0) 잔존
        self.assertEqual(clear_stale_weak_entries(U), 1)
        self.assertNotIn("weak_entry", self._meta())

    # (8) 800봉 시드의 last_dead_cross_ts = 실시간 재생 (측정 사건 목록 D/C 10-12 15:13 과 일치)
    def test_08_seed_long_history_last_dc_matches_realtime(self):
        ts, closes = _fixture()
        expect = pd.Timestamp("2026-10-12T15:13:00").tz_localize(KST).tz_convert("UTC")
        a = _ind()
        self.assertTrue(a.seed_long_history(closes[-800:], base_len=200, timestamps=ts[-800:]))
        self.assertEqual(a.last_dead_cross_ts, expect)
        # 실시간 재생: 앞 800봉으로 시드 → 나머지 200봉 update_incremental(close, ts)
        b = _ind()
        self.assertTrue(b.seed_long_history(closes[:800], base_len=200, timestamps=ts[:800]))
        for t, c in zip(ts[800:], closes[800:]):
            b.update_incremental(c, t)
        self.assertEqual(b.last_dead_cross_ts, expect)
        # 전략과 같은 식(매도 스냅샷)으로 재생해 찾은 마지막 D/C 와도 같다
        c_ = _ind()
        c_.seed_from_closes(closes[:200], quiet=True)
        last = None
        for t, cl in zip(ts[200:], closes[200:]):
            c_.update_incremental(cl)
            s = c_.get_snapshot(is_buy_eval=False)
            if s["prev_ema_fast"] is not None and s["prev_ema_fast"] >= s["prev_ema_slow"] and s["ema_fast"] < s["ema_slow"]:
                last = t
        self.assertEqual(last, expect)
        # 시드 직후 상태 모양 유지 (prev_* None, bar_count 0) — WO-17 (S) 와 같음
        self.assertIsNone(a.prev_ema_fast_sell)
        self.assertEqual(a.bar_count, 0)
        self.assertEqual(a.get_snapshot()["last_dead_cross_ts"], expect)

    # (9) BACKFILL 전후 last_dead_cross_ts 보존
    def test_09_backfill_preserves_last_dc(self):
        from engine.live_loop import _backup_dead_cross_ts, _restore_dead_cross_ts
        ts, closes = _fixture()
        ind = _ind()
        ind.seed_long_history(closes[-800:], base_len=200, timestamps=ts[-800:])
        before = ind.last_dead_cross_ts
        saved = {"ema_fast": ind.ema_fast}
        saved.update(_backup_dead_cross_ts(ind))
        # 재평가 봉이 G/C 뒤 데드크로스를 만든다고 가정 (급등 봉 → 급락 봉)
        fake = ts[-1] + timedelta(minutes=1)
        for i, px in enumerate([900.0] * 40 + [600.0] * 80):
            ind.update_incremental(px, fake + timedelta(minutes=i))
        self.assertNotEqual(ind.last_dead_cross_ts, before, "재평가 중 D/C 기록됨")
        _restore_dead_cross_ts(ind, saved)
        self.assertEqual(ind.last_dead_cross_ts, before)
        # live_loop BACKFILL 블록이 백업 dict·복원 try 안에서 두 함수를 부른다
        src = (ROOT / "engine" / "live_loop.py").read_text(encoding="utf-8")
        self.assertIn("saved_indicators.update(_backup_dead_cross_ts(engine.indicators))", src)
        self.assertIn("_restore_dead_cross_ts(engine.indicators, saved_indicators)", src)
        i_restore = src.index("_restore_dead_cross_ts(engine.indicators, saved_indicators)")
        i_try = src.rfind("engine.indicators.ema_fast = saved_indicators['ema_fast']", 0, i_restore)
        i_except = src.find("except Exception as _restore_exc", i_restore)
        self.assertTrue(0 < i_try < i_restore < i_except, "지표 복원 try 블록 안")

    # (10) 폴백 기동 → None · 로그
    def test_10_fallback_seed_unknown(self):
        from engine.live_loop import _seed_warmup_indicators
        ts, closes = _fixture()
        idx = pd.DatetimeIndex(ts[-300:])
        df = pd.DataFrame({"Open": closes[-300:], "High": closes[-300:], "Low": closes[-300:], "Close": closes[-300:],
                           "Volume": [1.0] * 300}, index=idx)
        ind = _ind()
        ok, mode, reason, _ = _seed_warmup_indicators(ind, df, 800, 200)
        self.assertEqual((ok, mode), (True, "sma200"))
        self.assertIsNone(ind.last_dead_cross_ts)
        src = (ROOT / "engine" / "live_loop.py").read_text(encoding="utf-8")
        self.assertIn("직전 D/C 알 수 없음 → 약매수 판정 안 함(일반 매수)", src)
        # long_history 기동은 직전 D/C 를 찾는다
        idx8 = pd.DatetimeIndex(ts)
        df8 = pd.DataFrame({"Open": closes, "High": closes, "Low": closes, "Close": closes, "Volume": [1.0] * 1000}, index=idx8)
        ind8 = _ind()
        ok, mode, _, _ = _seed_warmup_indicators(ind8, df8, 800, 200)
        self.assertEqual(mode, "long_history")
        self.assertEqual(ind8.last_dead_cross_ts, pd.Timestamp("2026-10-12T15:13:00").tz_localize(KST).tz_convert("UTC"))

    # (11) 설정 저장·적재 왕복 + hot reload + 기동 적용값 로그
    def test_11_settings_roundtrip_and_reload(self):
        from core.weak_entry import dump_weak_entry_settings, load_weak_entry_settings, weak_entry_summary
        from engine.live_loop import _config_applied_line
        self.assertEqual(load_weak_entry_settings({}), {"weak_entry_filter_enabled": False, "weak_entry_window_hours": 2.0,
                                                         "weak_entry_mode": "block", "weak_entry_tp_pct": 0.005})
        state = {"weak_entry_filter_enabled": True, "weak_entry_window_hours": 1.7, "weak_entry_mode": "reduce_tp",
                 "weak_entry_tp_pct": 0.0072}
        saved = json.loads(json.dumps({"buy": dump_weak_entry_settings(state)}))["buy"]
        self.assertEqual(saved, {"weak_entry_filter_enabled": True, "weak_entry_window_hours": 1.5,
                                 "weak_entry_mode": "reduce_tp", "weak_entry_tp_pct": 0.007})
        self.assertEqual(load_weak_entry_settings(saved), saved)
        self.assertEqual(weak_entry_summary(saved), "1.5시간 · 익절 0.7%")
        self.assertEqual(dump_weak_entry_settings({"weak_entry_window_hours": 9, "weak_entry_mode": "x",
                                                   "weak_entry_tp_pct": 0.1})["weak_entry_window_hours"], 6.0)
        st = _strategy(**saved)
        f = st.weak_entry_filter
        self.assertEqual((f.is_enabled(), f.window_hours, f.mode, f.weak_tp_pct), (True, 1.5, "reduce_tp", 0.007))
        # hot reload (SP5 reload_conditions): 새 필터 값 반영 + 변경 항목 보고, 보유 포지션의 override 는 그대로
        res = st.reload_conditions(dict(BUY_COND, weak_entry_filter_enabled=True, weak_entry_window_hours=3.0,
                                        weak_entry_mode="block"), dict(SELL_COND))
        self.assertEqual((st.weak_entry_filter.window_hours, st.weak_entry_filter.mode), (3.0, "block"))
        self.assertIn("weak_entry_window_hours", res["changed"])
        # B7 경로(_maybe_reload_params)도 약매수 필터를 다시 만든다
        src = (ROOT / "engine" / "live_loop.py").read_text(encoding="utf-8")
        self.assertIn("strategy._apply_weak_entry_conditions(buy_c)", src)
        line = _config_applied_line({"surge_filter_enabled": True}, {"stop_loss_pct": 1.0})
        for frag in ("weak_entry_filter_enabled=False*", "weak_entry_mode=block*", "weak_entry_window_hours=2.0*",
                     "weak_entry_tp_pct=0.005*", "fixed_price_unfilled_to_market=False*", "surge_filter_enabled=True ",
                     "sell: stop_loss_pct=1.0"):
            self.assertIn(frag, line + " ")

    # (12) 실데이터: 측정 csv 의 2시간 안 G/C 12건 block, 밖 32건 통과
    def test_12_measured_gc_list(self):
        from core.filters.buy_filters import WeakEntryFilter
        f = WeakEntryFilter(window_hours=2.0, mode="block", weak_tp_pct=0.005)
        f.set_enabled(True)
        blocked = passed = 0
        for r in csv.DictReader(open(OUTCOMES, encoding="utf-8")):
            gc = pd.Timestamp(r["gc_ts"]).tz_localize(KST).tz_convert("UTC")
            dc = pd.Timestamp(r["prev_dc_ts"]).tz_localize(KST).tz_convert("UTC")
            res = f.evaluate(bar_ts=gc, last_dead_cross_ts=dc)
            within = float(r["elapsed_h"]) <= 2.0
            self.assertEqual(res.should_block, within, r["gc_ts"])
            blocked += res.should_block
            passed += not res.should_block
        self.assertEqual((blocked, passed), (12, 32))


class TestWo26Render(unittest.TestCase):
    """UI 1-A: 설정 페이지·감사 로그 페이지 실제 렌더 (Streamlit AppTest)."""
    USER = U

    def setUp(self):
        import os
        import config  # noqa: F401  — .env/secrets 로드 후 cwd 이동
        import services.db  # noqa: F401
        import services.init_db  # noqa: F401
        import engine.params  # noqa: F401
        self._cwd = os.getcwd()
        self.tmpdir = Path(tempfile.mkdtemp(prefix="wo26r_"))
        self.db_path = str(self.tmpdir / f"tradebot_{self.USER}.db")
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
        os.chdir(self.tmpdir)

    def tearDown(self):
        import os
        os.chdir(self._cwd)
        for p in self._patchers:
            p.stop()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _settings(self, buy):
        (self.tmpdir / f"{self.USER}_EMA_buy_sell_conditions.json").write_text(json.dumps({
            "buy": dict({"ema_gc": True}, **buy), "sell": {"stop_loss": True, "ema_dc": True, "stop_loss_pct": 1.0},
        }), encoding="utf-8")
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(ROOT / "pages" / "set_buy_sell_conditions.py"), default_timeout=60)
        for k, v in dict(user_id=self.USER, mode="LIVE", strategy="EMA").items():
            at.query_params[k] = v
        at.session_state["user_id"] = self.USER
        at.run()
        self.assertEqual([e.value for e in at.exception], [])
        return at

    def test_r1_settings_block_rendered_and_saved(self):
        at = self._settings({"weak_entry_filter_enabled": True, "weak_entry_window_hours": 2.0,
                             "weak_entry_mode": "reduce_tp", "weak_entry_tp_pct": 0.005})
        labels = [t.label for t in at.toggle]
        self.assertIn("🐢 약매수 차단 필터 (데드크로스 직후 골든크로스 매수 제한)", labels)
        ni = {n.label: n for n in at.number_input}
        self.assertEqual(ni["D/C 뒤 G/C 허용 시간 (시간)"].value, 2.0)
        self.assertAlmostEqual(ni["축소 익절 기준 (%)"].value, 0.5)
        self.assertFalse(ni["축소 익절 기준 (%)"].disabled)
        radio = next(r for r in at.radio if r.label == "약매수 처리")
        self.assertEqual(radio.value, "reduce_tp")
        captions = "\n".join(c.value for c in at.caption)
        self.assertIn("수익 추적 매도는 이 경우 고정폭이 매우 작아 사실상 즉시 매도에 가깝습니다", captions)
        self.assertIn("└─ 2시간 · 익절 0.5%", [c.value.strip() for c in at.caption])
        # 처리 방식 → 매수 안 함 으로 바꾸고 저장 → 파일 왕복
        radio.set_value("block").run()
        ni = {n.label: n for n in at.number_input}
        self.assertTrue(ni["축소 익절 기준 (%)"].disabled, "매수 안 함이면 익절 칸 비활성")
        # 저장 뒤 대시보드 이동(st.switch_page)은 AppTest 단독 페이지 실행에서 페이지를 찾지 못하므로 막는다
        with patch("services.page_context.navigate_to", MagicMock()):
            at.button(key="btn_save_settings").click().run()
        self.assertEqual([e.value for e in at.exception], [])
        saved = json.loads((self.tmpdir / f"{self.USER}_EMA_buy_sell_conditions.json").read_text(encoding="utf-8"))["buy"]
        self.assertEqual({k: saved[k] for k in ("weak_entry_filter_enabled", "weak_entry_window_hours",
                                                "weak_entry_mode", "weak_entry_tp_pct")},
                         {"weak_entry_filter_enabled": True, "weak_entry_window_hours": 2.0,
                          "weak_entry_mode": "block", "weak_entry_tp_pct": 0.005})

    def test_r2_settings_old_file_defaults(self):
        at = self._settings({})  # 약매수 키가 없는 옛 파일 → 토글 끔, 파라미터 블록 없음
        tg = next(t for t in at.toggle if t.label.startswith("🐢 약매수 차단 필터"))
        self.assertFalse(tg.value)
        self.assertNotIn("D/C 뒤 G/C 허용 시간 (시간)", [n.label for n in at.number_input])

    def test_r3_audit_viewer_weak_columns(self):
        from services.db import insert_buy_eval, insert_trade_audit
        insert_buy_eval(user_id=self.USER, ticker=T, interval_sec=180, bar=10, price=778.0, macd=770.42, signal=770.41,
                        have_position=False, overall_ok=False, failed_keys=["WEAK_ENTRY_FILTER"],
                        checks={"filter_blocked": True, "filter_reason": "WEAK_ENTRY_FILTER",
                                "filter_details": "약매수 차단 (D/C 뒤 84분, 기준 2시간)",
                                "filter_metadata": {"weak_entry": True, "elapsed_min": 84, "window_h": 2.0}},
                        notes="Golden | 약매수 차단 (D/C 뒤 84분, 기준 2시간) | bar=10",
                        bar_time="2026-10-12T16:37:00+09:00")
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(ROOT / "pages" / "audit_viewer.py"), default_timeout=60)
        for k, v in dict(user_id=self.USER, tab="buy", mode="LIVE", ticker="JTO").items():
            at.query_params[k] = v
        at.session_state["user_id"] = self.USER
        at.run()
        self.assertEqual([e.value for e in at.exception], [])
        df = at.dataframe[0].value
        self.assertIn("약매수", df.columns)
        self.assertEqual(df.iloc[0]["약매수"], "🐢 약매수 차단 (D/C 뒤 84분, 기준 2시간)")
        self.assertEqual(df.iloc[0]["surge_actual"], "-", "약매수 metadata 를 급등 칸으로 오해하지 않음")

        insert_trade_audit(self.USER, T, 180, 10, "BUY", "EMA_GC", 778.0, None, None, None, None, None, None, None,
                           None, None, None, bar_time="2026-10-12T16:37:00+09:00", note="약매수 진입 · 익절 0.5%")
        at2 = AppTest.from_file(str(ROOT / "pages" / "audit_viewer.py"), default_timeout=60)
        for k, v in dict(user_id=self.USER, tab="trades", mode="LIVE", ticker="JTO").items():
            at2.query_params[k] = v
        at2.session_state["user_id"] = self.USER
        at2.run()
        self.assertEqual([e.value for e in at2.exception], [])
        df2 = at2.dataframe[0].value
        row = df2[df2["reason"] == "EMA_GC"].iloc[0]
        self.assertEqual(row["비고"], "약매수 진입 · 익절 0.5%")
        self.assertTrue(row["거절 사유"] is None or str(row["거절 사유"]) in ("None", "nan", ""), "매수 행은 거절 사유 칸 비움")


if __name__ == "__main__":
    unittest.main()
