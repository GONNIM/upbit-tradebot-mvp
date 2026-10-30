"""2차 T16: 신버전 화면 2차 채움 — 읽기 API 시험(새 전략 회차·익절/손절·로그 문구·전환 기록·표식).

- 기본 픽스처(tests.v2.test_api_read.create_schema) = 새 표(pullback_state·strategy_switch)가 없는 DB(배포 전 서버와 같음).
- TestEmaUnchangedVsBase: 기준 커밋(tests/regressions/baseline_commits.V2_READ_BASE_COMMIT)의 v2/api_read.py 를
  git show 로 읽어 같은 앱에 /old 접두로 올리고, EMA 사용자 응답이 글자 하나까지 같은지 본다.
"""
import importlib.util
import json
import sqlite3
import sys
import types
import unittest
from unittest import mock

from tests.regressions.baseline_commits import V2_READ_BASE_COMMIT, git_show
from tests.v2.test_api_read import ApiBase, create_pb_schema
from v2 import api_read, control
from v2.server import make_app

PB_APPLIED = {"ticker": "KRW-ZRO", "interval": "minute1", "maType": "ema", "ma60p": 60, "ma200p": 200,
              "pullbackP": 60, "slopeLB": 20, "minSlope": 0, "slopeDrop": 0, "buyOnGoldenCross": True,
              "maxSplits": 5, "maxPullbackBuys": 5, "tp": 5, "sl": 3, "deadcross": True, "compounding": False,
              "capital": 1000000, "fee": 0.05}


def _load_base_module():
    src = git_show("v2/api_read.py", V2_READ_BASE_COMMIT)
    if src is None:
        return None
    mod = types.ModuleType("v2._api_read_base_t16")
    mod.__file__ = "v2/api_read.py@" + V2_READ_BASE_COMMIT
    exec(compile(src, mod.__file__, "exec"), mod.__dict__)
    return mod


BASE = _load_base_module()


def _drawn(markers):
    """화면이 그리는 표식 행 — bar_time 이 없는 행은 chart.js toMarkers 가 버린다(time NaN, 4e86afb 와 같음)."""
    return [m for m in markers if m.get("bar_time")]


class PbBase(ApiBase):
    def set_pb(self, **over):
        p = dict(PB_APPLIED)
        p.update(over)
        (self.root / "alice_active_strategy.txt").write_text("PULLBACK\n", encoding="utf-8")
        (self.root / "alice_applied_params_PULLBACK.json").write_text(json.dumps(p), encoding="utf-8")
        return p

    def pb_db(self):
        c = self.make_live_db()
        create_pb_schema(c)
        return c

    def pb_state(self, mode="TEST", entry=2, qty=1.0, avg=1000.0, desync=0, user="alice"):
        self.conn.execute(
            "INSERT INTO pullback_state(user_id,mode,ticker,interval,entry_count,qty,avg_price,desync,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)", (user, mode, "KRW-ZRO", "minute1", entry, qty, avg, desync,
                                           "2026-10-30T10:00:00+09:00"))
        self.conn.commit()

    def holding(self, coin=1.0, entry=1000.0):
        self.conn.execute("INSERT INTO accounts(user_id,virtual_krw,virtual_krw_locked,updated_at) "
                          "VALUES ('alice',50000,0,'2026-10-30 10:00:00')")
        self.conn.execute("INSERT INTO account_positions(user_id,ticker,virtual_coin,virtual_coin_locked,"
                          "entry_price,updated_at) VALUES ('alice','KRW-ZRO',?,0,?,'2026-10-30 10:00:00')",
                          (coin, entry))
        self.conn.commit()

    def trade(self, ts, typ, reason=None, entry=None, meta=None, price=100.0, qty=1.0, bar=None, note=None,
              no_bar=False):
        # no_bar=True: 외부 매수·매도 행처럼 bar_time NULL(core/strategy_engine.py:670-678·order_reconciler.py:860-879)
        self.conn.execute(
            "INSERT INTO audit_trades(timestamp,bar_time,ticker,type,reason,price,qty,entry_price,note,meta) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (ts, None if no_bar else (bar or ts), "KRW-ZRO", typ, reason, price, qty, entry, note,
             json.dumps(meta, ensure_ascii=False) if isinstance(meta, dict) else meta))
        self.conn.commit()

    def pb_eval(self, table, ts, keys, ok=0, **ck):
        checks = {"strategy": "PULLBACK", "strategy_mode": "PULLBACK", "failed_keys": keys}
        checks.update(ck)
        if table == "audit_buy_eval":
            self.conn.execute(
                "INSERT INTO audit_buy_eval(timestamp,bar_time,ticker,price,have_position,overall_ok,failed_keys,checks) "
                "VALUES (?,?,?,?,?,?,?,?)", (ts, ts, "KRW-ZRO", 100.0, 0, ok, json.dumps(keys), json.dumps(checks)))
        else:
            self.conn.execute(
                "INSERT INTO audit_sell_eval(timestamp,bar_time,ticker,price,triggered,trigger_key,checks) "
                "VALUES (?,?,?,?,?,?,?)", (ts, ts, "KRW-ZRO", 100.0, 0, None,
                                           json.dumps(checks)))
        self.conn.commit()

    def switch(self, kind, state, req, done=None, note=None, mode="TEST", frm="EMA", to="PULLBACK",
               interval="minute1", user="alice"):
        self.conn.execute(
            "INSERT INTO strategy_switch(user_id,mode,kind,from_strategy,from_interval,to_strategy,to_interval,"
            "state,requested_at,done_at,note) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (user, mode, kind, frm, interval, to, interval, state, req, done, note))
        self.conn.commit()

    def audit_texts(self, mode="TEST"):
        code, b = self.get_json("/v2/api/logs?kind=audit", mode=mode)
        self.assertEqual(code, 200)
        return [r["text"] for r in b["rows"]]


@unittest.skipIf(BASE is None, "기준 커밋 원문을 읽지 못함(git 없음)")
class TestEmaUnchangedVsBase(PbBase):
    """새 표 없는 DB·빈 새 표 DB 모두에서 EMA 사용자 홈·로그·자산·차트 응답 = 기준 커밋과 같음."""

    PATHS = ["/v2/api/status", "/v2/api/assets", "/v2/api/basic", "/v2/api/trades?limit=10",
             "/v2/api/trades?limit=50", "/v2/api/signals?limit=1", "/v2/api/signals", "/v2/api/logs?kind=audit",
             "/v2/api/logs?kind=audit&page=2", "/v2/api/logs?kind=engine", "/v2/api/logs?kind=error",
             "/v2/api/markers"]

    def get_app(self):
        app = make_app(static_dir=self.static)
        app.add_handlers(r".*", [(r"/old" + pat, h) for pat, h in BASE.ROUTES])
        return app

    def _fixture(self, c):
        self.set_strategy("EMA", "KRW-ZRO", "minute3")
        self.holding()
        for i in range(30):
            self.ins_eval("audit_buy_eval", "KRW-ZRO", "2026-10-30 09:%02d:00" % i, 100.0 + i,
                          bar_time="2026-10-30 09:%02d:00" % i, overall_ok=0,
                          failed_keys='["NO_SIGNAL"]' if i % 7 else '["SURGE_FILTER"]',
                          checks='{"signal_positive": true}')
        for i in range(10):
            self.ins_eval("audit_sell_eval", "KRW-ZRO", "2026-10-30 09:%02d:30" % (30 + i), 130.0 + i,
                          bar_time="2026-10-30 09:%02d:30" % (30 + i), tp_price=150.0, sl_price=90.0,
                          triggered=1 if i == 9 else 0, trigger_key="STOP_LOSS" if i == 9 else None,
                          checks='{"take_profit": {"enabled": 1}}')
        self.trade("2026-10-30 09:05:00", "BUY", "EMA_GC", entry=100.0, meta='{"strategy_type": "EMA"}')
        self.trade("2026-10-30 09:39:30", "SELL", "STOP_LOSS", entry=100.0)
        self.trade("2026-10-30 09:10:00", "HTS_SELL", "HTS_SELL", price=None, note="외부 매도", no_bar=True)
        for i in range(20):
            c.execute("INSERT INTO logs(user_id,timestamp,level,message) VALUES (?,?,?,?)",
                      ("alice", "2026-10-30T09:%02d:00+09:00" % i, "WARNING" if i % 5 == 0 else "INFO",
                       "🚀 m%02d" % i))
        c.commit()

    def _compare(self, mode):
        for p in self.PATHS:
            new = self.get_json(p, mode=mode)
            old = self.get_json("/old" + p, mode=mode)
            self.assertEqual(new[0], 200, p)
            if p == "/v2/api/markers":
                # 응답 행: 지금은 외부 매도(bar_time NULL) 행을 SQL 에서 빼고, 기준 커밋은 bar_time null 로 내보냈다.
                # 화면에 그리는 행(bar_time 있음)은 같아야 한다(U2 — 화면 변화 0).
                self.assertEqual(old[0], 200, p)
                self.assertEqual(_drawn(new[1]["markers"]), _drawn(old[1]["markers"]), (mode, p))
                continue
            self.assertEqual(new, old, (mode, p))

    def test_no_new_tables_same_as_base(self):
        c = self.make_live_db()
        self._fixture(c)
        for mode in ("TEST", "LIVE"):
            self._compare(mode)

    def test_empty_new_tables_same_as_base(self):
        c = self.pb_db()
        self._fixture(c)
        for mode in ("TEST", "LIVE"):
            self._compare(mode)

    def test_markers_only_buy_sell_rows_u2(self):
        """결정 1030-02 U2: 표식은 BUY·SELL 만. 화면에서 사라지는 것은 거절·취소 행의 가짜 ▼ 뿐.
        외부 매수(type=BUY reason=HTS_BUY)·외부 매도(HTS_SELL)는 bar_time 이 없어 기준 커밋에서도 지금도 표식이 없다."""
        c = self.make_live_db()
        self._fixture(c)
        self.trade("2026-10-30 09:20:00", "BUY_REJECTED", note="잔고 부족", meta='{"error_name": "x"}')
        self.trade("2026-10-30 09:21:00", "BUY_CANCELED")
        self.trade("2026-10-30 09:22:00", "BUY", "HTS_BUY", no_bar=True)
        new = self.get_json("/v2/api/markers")[1]["markers"]
        old = self.get_json("/old/v2/api/markers")[1]["markers"]
        self.assertTrue({m["type"] for m in new} <= {"BUY", "SELL"})
        d_new, d_old = _drawn(new), _drawn(old)
        self.assertEqual([m for m in d_old if m["type"] in ("BUY", "SELL")], d_new)
        self.assertEqual(sorted(m["type"] for m in d_old if m not in d_new), ["BUY_CANCELED", "BUY_REJECTED"])
        # 외부 매수·매도 자리(09:10·09:22)는 기준 커밋·지금 모두 그리지 않는다
        for d in (d_new, d_old):
            self.assertFalse([m for m in d if m["bar_time"][11:16] in ("09:10", "09:22")])
        self.assertEqual([m["bar_time"][11:16] for m in d_new], ["09:39", "09:05"])


class TestEmaPathQueries(PbBase):
    def test_ema_user_never_reads_pullback_sql(self):
        """EMA 사용자 홈·로그·자산·신호는 새 전략 조회(눌림 상태·새 전략 판단 행)를 하지 않는다."""
        self.pb_db()
        self.set_strategy("EMA")
        self.holding()
        seen = []
        real = api_read.db.query

        def spy(user_id, sql, params=()):
            seen.append(sql)
            return real(user_id, sql, params)
        pb_sql = {api_read.SQL_PB_STATE, api_read.SQL_SIGNALS_PB_TICKER, api_read.SQL_SIGNALS_PB_SELL_TICKER,
                  api_read.SQL_LOGS_AUDIT_BUY_EVAL_PB, api_read.SQL_LOGS_AUDIT_SELL_EVAL_PB}
        with mock.patch.object(api_read.db, "query", spy):
            for p in ("/v2/api/status", "/v2/api/assets", "/v2/api/signals", "/v2/api/logs?kind=audit"):
                self.assertEqual(self.get_json(p)[0], 200, p)
        self.assertTrue(seen)
        self.assertFalse(pb_sql & set(seen))


class TestPullbackStatusAssets(PbBase):
    def test_status_pullback_config_only_for_pullback(self):
        self.pb_db()
        self.set_strategy("EMA")
        self.assertNotIn("pullback", self.get_json("/v2/api/status")[1])
        self.set_pb(ma60p=50, ma200p=150, pullbackP=40, maType="SMA")
        b = self.get_json("/v2/api/status")[1]
        self.assertEqual(b["pullback"], {"ma60p": 50, "ma200p": 150, "pullbackP": 40, "maType": "sma",
                                         "tp": 5.0, "sl": 3.0, "max_splits": 5})

    def test_assets_round_from_pullback_state(self):
        self.pb_db()
        self.set_pb()
        self.holding()
        self.pb_state(mode="TEST", entry=2)
        b = self.get_json("/v2/api/assets", mode="TEST")[1]
        self.assertEqual(b["round"], {"entry": 2, "max": 5, "desync": False})
        # 입장 모드 행만(LIVE 행 없음 → 회차 0)
        self.assertEqual(self.get_json("/v2/api/assets", mode="LIVE")[1]["round"], {"entry": 0, "max": 5, "desync": False})
        # 골든크로스만(maxSplits 0 + buyOnGoldenCross) = 한도 1 (control._eff_max_splits 와 같음)
        self.set_pb(maxSplits=0, buyOnGoldenCross=True)
        self.assertEqual(self.get_json("/v2/api/assets")[1]["round"]["max"], 1)

    def test_assets_tp_sl_from_pullback_params(self):
        self.pb_db()
        self.set_pb(tp=5, sl=3)
        self.holding()
        self.pb_state(entry=2, avg=1000.0)
        self.ins_eval("audit_sell_eval", "KRW-ZRO", "2026-10-30T10:00:00+09:00", 990.0, tp_price=999.0, sl_price=1.0)
        b = self.get_json("/v2/api/assets")[1]
        self.assertAlmostEqual(b["tp_price"], 1050.0)
        self.assertAlmostEqual(b["sl_price"], 970.0)
        self.assertEqual(set(b), {"krw", "krw_locked", "coin", "coin_locked", "entry_price", "price", "price_at",
                                  "pnl", "tp_price", "sl_price", "round", "updated_at"})

    def test_assets_tp_sl_desync_uses_engine_record(self):
        """어긋남(지갑 평단 기준으로 엔진이 관리) — 상태 평단이 아니라 엔진 판단 기록 값."""
        self.pb_db()
        self.set_pb()
        self.holding()
        self.pb_state(entry=2, avg=1000.0, desync=1)
        self.ins_eval("audit_sell_eval", "KRW-ZRO", "2026-10-30T10:00:00+09:00", 990.0, tp_price=1111.0, sl_price=888.0)
        b = self.get_json("/v2/api/assets")[1]
        self.assertEqual((b["tp_price"], b["sl_price"]), (1111.0, 888.0))
        self.assertTrue(b["round"]["desync"])

    def test_assets_pullback_without_tables_200(self):
        self.make_live_db()
        self.set_pb()
        self.holding()
        code, b = self.get_json("/v2/api/assets")
        self.assertEqual(code, 200)
        self.assertIsNone(b["round"])

    def test_assets_does_not_call_ops_info_helpers(self):
        """결정 5: 자산 처리 경로는 ops_info·저장본 해시·요청 파일 읽기를 부르지 않는다."""
        self.pb_db()
        self.set_pb()
        self.holding()
        self.pb_state(entry=1)
        boom = mock.Mock(side_effect=AssertionError("called"))
        with mock.patch.object(control, "_saved_state", boom), mock.patch.object(control, "pending_id", boom), \
                mock.patch.object(control, "ops_info", boom):
            code, b = self.get_json("/v2/api/assets")
        self.assertEqual(code, 200)
        self.assertEqual(b["round"]["entry"], 1)
        boom.assert_not_called()


class TestPullbackTradesMarkers(PbBase):
    def test_trades_include_round(self):
        self.pb_db()
        self.set_pb()
        self.trade("2026-10-30 09:31:00", "BUY", "GOLDEN", entry=1000.0, meta={"split_round": 1, "reason": "GOLDEN"})
        self.trade("2026-10-30 10:15:00", "BUY", "PULLBACK", entry=1000.0, meta={"split_round": 2, "reason": "PULLBACK"})
        self.trade("2026-10-30 10:20:00", "BUY_REJECTED", "PULLBACK", meta={"error_name": "split_krw_short"},
                   note="원화 잔고 부족 (가용 1원 < 회당 2원+수수료)")
        self.trade("2026-10-30 10:25:00", "BUY_REJECTED", "EMA_GC", meta={"error_name": "trading_paused"}, note="일시중지")
        t = self.get_json("/v2/api/trades")[1]["trades"]
        by = {r["timestamp"][11:16]: r for r in t}
        self.assertEqual(by["10:15"]["round"], 2)
        self.assertEqual(by["09:31"]["round"], 1)
        self.assertEqual(by["10:20"]["skip_reason"], "원화 잔고 부족")
        base = {"id", "timestamp", "bar_time", "ticker", "type", "reason", "price", "qty", "entry_price", "note"}
        self.assertEqual(set(by["10:25"]), base)            # 새 전략 원인이 아닌 거절은 1차와 같은 키
        for r in t:
            self.assertNotIn("meta", r)                    # meta 는 내보내지 않는다(결정 6)
            self.assertTrue(set(r) - base <= {"round", "skip_reason"})

    def test_markers_include_split_buys(self):
        self.pb_db()
        self.set_pb()
        self.trade("2026-10-30 09:31:00", "BUY", "GOLDEN", meta={"split_round": 1})
        self.trade("2026-10-30 10:15:00", "BUY", "PULLBACK", meta={"split_round": 2})
        self.trade("2026-10-30 10:20:00", "BUY_REJECTED", meta={"error_name": "split_krw_short"})
        self.trade("2026-10-30 11:00:00", "SELL", "TP")
        m = self.get_json("/v2/api/markers")[1]["markers"]
        self.assertEqual([x["type"] for x in m], ["SELL", "BUY", "BUY"])


class TestPullbackLogs(PbBase):
    def test_logs_pullback_wait_line(self):
        self.pb_db()
        self.set_pb()
        self.pb_eval("audit_buy_eval", "2026-10-30 10:40:00", ["WAIT_PULLBACK"], round=2, armed=0, active=1)
        self.pb_eval("audit_buy_eval", "2026-10-30 10:41:00", ["WAIT_PULLBACK"], round=2, armed=1, active=1)
        self.pb_eval("audit_buy_eval", "2026-10-30 10:42:00", ["WAIT_PULLBACK"], round=2, armed=1, active=1)
        t = self.audit_texts()
        self.assertEqual(t[0], "매수 대기 — 눌림 상태, 3회차 준비 (2회, 10:41~10:42)")
        self.assertEqual(t[1], "매수 대기 — 눌림 대기, 3회차 준비")

    def test_logs_not_active_uses_ma_periods(self):
        self.pb_db()
        self.set_pb(ma60p=50, ma200p=150)
        self.pb_eval("audit_buy_eval", "2026-10-30 10:40:00", ["NOT_ACTIVE"], round=0, inactive_reason="not_golden")
        self.assertEqual(self.audit_texts()[0], "매수 대기 — 감시 구간 밖(50선 ≤ 150선)")

    def test_logs_holding_armed_from_sell_eval(self):
        """보유 중 눌림 대기는 매도 판단 행 checks 에 있다(그림 2-라 10:42 줄). 미발동 비armed 행은 넣지 않는다."""
        self.pb_db()
        self.set_pb()
        self.pb_eval("audit_sell_eval", "2026-10-30 10:30:00", ["WAIT_PULLBACK"], round=2, armed=0, active=1)
        self.pb_eval("audit_sell_eval", "2026-10-30 10:42:00", ["WAIT_PULLBACK"], round=2, armed=1, active=1)
        t = self.audit_texts()
        self.assertEqual(t, ["매수 대기 — 눌림 상태, 3회차 준비"])

    def test_logs_split_buy_lines(self):
        self.pb_db()
        self.set_pb()
        self.trade("2026-10-30 09:31:00", "BUY", "GOLDEN", entry=1000.0, meta={"split_round": 1, "avg_after": 1000.0})
        self.trade("2026-10-30 10:15:00", "BUY", "PULLBACK", entry=1000.0, meta={"split_round": 2, "avg_after": 1000.0})
        self.trade("2026-10-30 10:16:00", "BUY", "FORCE", entry=990.0, meta={"split_round": 3})
        t = self.audit_texts()
        self.assertEqual(t, ["매수 체결 3회차 · 강제 매수 · 평단 990", "매수 체결 2회차 · 눌림목 · 평단 1,000",
                             "매수 체결 1회차 · 골든크로스"])

    def test_logs_golden_event_line(self):
        self.pb_db()
        self.set_pb()
        self.pb_eval("audit_buy_eval", "2026-10-30 09:30:00", ["WAIT_PULLBACK"], round=0, golden_event=1)
        self.pb_eval("audit_sell_eval", "2026-10-30 09:30:00", ["WAIT_PULLBACK"], round=0, golden_event=1)
        t = self.audit_texts()
        self.assertEqual(t.count("골든크로스 발생 (60선 > 200선)"), 1)   # 두 판단 표에 같은 봉 → 1줄
        self.set_pb(ma60p=50)
        self.assertIn("골든크로스 발생 (50선 > 200선)", self.audit_texts())

    def test_logs_skip_krw_short_line(self):
        self.pb_db()
        self.set_pb()
        self.trade("2026-10-30 10:20:00", "BUY_REJECTED", "PULLBACK", meta={"error_name": "split_krw_short"},
                   note="원화 잔고 부족 (가용 1원 < 회당 2원+수수료) — 줄여 사지 않음")
        self.trade("2026-10-30 10:21:00", "BUY_REJECTED", "PULLBACK", meta={"error_name": "split_below_min"}, note="x")
        self.assertEqual(self.audit_texts(), ["매수 건너뜀 — 최소 주문금액 미만", "매수 건너뜀 — 원화 잔고 부족"])

    def test_logs_sell_line(self):
        self.pb_db()
        self.set_pb()
        self.trade("2026-10-30 11:00:00", "SELL", "TP")
        self.assertEqual(self.audit_texts(), ["매도 체결 · 익절"])

    def test_logs_switch_done_line(self):
        self.pb_db()
        self.set_strategy("EMA")
        self.switch("SWITCH", "DONE", "2026-10-30T09:02:00+09:00", "2026-10-30T09:02:30+09:00")
        self.assertEqual(self.audit_texts(), ["전략 전환 완료 → 눌림목 분할매수"])

    def test_logs_switch_immediate_90s_no_reserved_line(self):
        """결정 9: 즉시 전환이 1분봉에서 완료까지 90초 → 하한 300초 안이라 예약 줄 없음."""
        self.pb_db()
        self.set_pb()
        self.switch("SWITCH", "DONE", "2026-10-30T09:00:00+09:00", "2026-10-30T09:01:30+09:00", interval="minute1")
        self.assertEqual(self.audit_texts(), ["전략 전환 완료 → 눌림목 분할매수"])

    def test_logs_switch_reserved_then_done_two_lines(self):
        self.pb_db()
        self.set_pb()
        self.switch("SWITCH", "DONE", "2026-10-30T09:00:00+09:00", "2026-10-30T09:10:00+09:00", interval="minute1")
        code, b = self.get_json("/v2/api/logs?kind=audit")
        rows = b["rows"]
        self.assertEqual([r["text"] for r in rows], ["전략 전환 완료 → 눌림목 분할매수", "전환 예약"])
        self.assertTrue(rows[1]["timestamp"].startswith("2026-10-30T09:00:00"))
        # 60분봉이면 1봉(3600초) 안이라 예약 줄 없음
        self.conn.execute("DELETE FROM strategy_switch")
        self.conn.commit()
        self.switch("SWITCH", "DONE", "2026-10-30T09:00:00+09:00", "2026-10-30T09:10:00+09:00", interval="minute60")
        self.assertEqual(self.audit_texts(), ["전략 전환 완료 → 눌림목 분할매수"])

    def test_logs_switch_kinds_states(self):
        self.pb_db()
        self.set_pb()
        cases = [
            ("SWITCH", "RESERVED", None, "전환 예약"),
            ("SWITCH", "RESERVED", "switching", "전략 전환 처리 중"),
            ("SWITCH", "CANCELED", None, "전환 예약 취소"),
            ("SWITCH", "CANCELED", "mode_conflict", "전환 요청 취소 — 다른 모드 엔진 실행 중"),
            ("SWITCH", "FAILED", "boot_not_ready", "전략 전환 실패 — 기존 전략으로 계속"),
            ("REVERT", "DONE", None, "기존 전략으로 복귀 → EMA"),
            ("REVERT", "RESERVED", None, "복귀 예약"),
            ("REVERT", "CANCELED", None, "복귀 예약 취소"),
            ("REVERT", "FAILED", None, "기존 전략으로 복귀 실패 — 새 전략으로 계속"),
        ]
        for kind, state, note, want in cases:
            self.conn.execute("DELETE FROM strategy_switch")
            self.conn.commit()
            frm, to = ("EMA", "PULLBACK") if kind == "SWITCH" else ("PULLBACK", "EMA")
            done = None if state == "RESERVED" else "2026-10-30T09:00:30+09:00"
            self.switch(kind, state, "2026-10-30T09:00:00+09:00", done, note=note, frm=frm, to=to)
            t = self.audit_texts()
            self.assertEqual(t, [want], (kind, state, note))
            for bad in ("RESERVED", "DONE", "SWITCH", "REVERT", "mode_conflict", "switching"):
                self.assertNotIn(bad, t[0])

    def test_logs_params_row_not_switch(self):
        self.pb_db()
        self.set_pb()
        self.switch("PARAMS", "DONE", "2026-10-30T09:00:00+09:00", "2026-10-30T09:00:01+09:00",
                    note=json.dumps({"changed": {"tp": [5, 4]}, "apply": "immediate"}), frm="PULLBACK")
        t = self.audit_texts()
        self.assertEqual(t, ["설정 적용 · 익절 TP 5→4% · 즉시"])
        self.assertNotIn("전략 전환 완료", " ".join(t))

    def test_logs_params_apply_labels(self):
        self.pb_db()
        self.set_pb()
        want = {"next_bar": "다음 봉부터", "immediate": "즉시", "reseed": "지표 다시 계산(그동안 매수 없음)",
                "switch": "전환과 함께 적용", "restart": "재시작 적용"}
        for apply, label in want.items():
            self.conn.execute("DELETE FROM strategy_switch")
            self.conn.commit()
            self.switch("PARAMS", "DONE", "2026-10-30T09:00:00+09:00", "2026-10-30T09:00:01+09:00",
                        note=json.dumps({"changed": {"ma60p": [60, 50], "maType": ["ema", "sma"]}, "apply": apply}))
            self.assertEqual(self.audit_texts(), ["설정 적용 · 60선 기간 60→50 · 이동평균 방식 ema→sma · " + label])
        # 결정 1030-02 U4: 「다시 시드」 글자는 화면 문구에 없다
        with open(api_read.__file__, encoding="utf-8") as f:
            self.assertNotIn("다시 시드", f.read())

    def test_logs_params_first_switch_all_new(self):
        self.pb_db()
        self.set_pb()
        changed = {k: [None, v] for k, v in PB_APPLIED.items()}
        self.switch("PARAMS", "DONE", "2026-10-30T09:00:00+09:00", "2026-10-30T09:00:01+09:00",
                    note=json.dumps({"changed": changed, "apply": "switch"}))
        self.assertEqual(self.audit_texts(), ["설정 적용 · 새 설정 %d개 · 전환과 함께 적용" % len(PB_APPLIED)])

    def test_logs_params_more_than_three(self):
        self.pb_db()
        self.set_pb()
        changed = {"tp": [5, 4], "sl": [3, 2], "ma60p": [60, 50], "ma200p": [200, 150], "pullbackP": [60, 40]}
        self.switch("PARAMS", "DONE", "2026-10-30T09:00:00+09:00", "2026-10-30T09:00:01+09:00",
                    note=json.dumps({"changed": changed, "apply": "next_bar"}))
        self.assertEqual(self.audit_texts(),
                         ["설정 적용 · 익절 TP 5→4% · 손절 SL 3→2% · 60선 기간 60→50 · 외 2개 · 다음 봉부터"])

    def test_logs_switch_mode_and_user_scope(self):
        self.pb_db()
        self.set_pb()
        self.switch("SWITCH", "DONE", "2026-10-30T09:00:00+09:00", "2026-10-30T09:00:10+09:00", mode="LIVE")
        self.switch("SWITCH", "DONE", "2026-10-30T09:01:00+09:00", "2026-10-30T09:01:10+09:00", user="bob")
        self.assertEqual(self.audit_texts(mode="TEST"), [])
        self.assertEqual(self.audit_texts(mode="LIVE"), ["전략 전환 완료 → 눌림목 분할매수"])

    def test_logs_pullback_without_tables_200(self):
        self.make_live_db()
        self.set_pb()
        self.pb_eval("audit_buy_eval", "2026-10-30 10:41:00", ["WAIT_PULLBACK"], round=0, armed=1)
        self.assertEqual(self.audit_texts(), ["매수 대기 — 눌림 상태, 1회차 준비"])


class TestPullbackSignals(PbBase):
    def test_signals_pb_field_only_for_pullback(self):
        self.pb_db()
        self.set_pb()
        self.pb_eval("audit_buy_eval", "2026-10-30 10:41:00", ["WAIT_PULLBACK"], round=2, armed=1, active=1)
        s = self.get_json("/v2/api/signals?limit=1")[1]["signals"][0]
        self.assertEqual(s["pb"], {"state": "WAIT_PULLBACK", "round": 2, "armed": 1, "active": 1, "holding": 0,
                                   "inactive_reason": None})
        self.set_strategy("EMA")
        s = self.get_json("/v2/api/signals?limit=1")[1]["signals"][0]
        self.assertNotIn("pb", s)

    def test_signals_holding_sell_eval_pb(self):
        self.pb_db()
        self.set_pb()
        self.pb_eval("audit_sell_eval", "2026-10-30 10:42:00", ["SPLITS_FULL"], round=5, armed=1, holding=1)
        s = self.get_json("/v2/api/signals?limit=1")[1]["signals"][0]
        self.assertEqual((s["kind"], s["pb"]["state"], s["pb"]["holding"]), ("sell", "SPLITS_FULL", 1))


class TestLabelTables(unittest.TestCase):
    def test_labels_match_terminology(self):
        from services import terminology as T
        for k, v in T.PULLBACK_STATE_LABEL.items():
            self.assertEqual(api_read.FAILED_KEY_LABELS[k], v, k)
        self.assertEqual(api_read.SKIP_CAUSE_LABELS, T.PULLBACK_SKIP_CAUSE)
        self.assertEqual(api_read.STRATEGY_TEXT["PULLBACK"], T.PULLBACK_TERMS["strategy"])

    def test_apply_labels_cover_engine_values(self):
        self.assertEqual({"next_bar", "immediate", "reseed", "switch", "restart"}, set(api_read.APPLY_LABELS))
        self.assertEqual(api_read.APPLY_LABELS["reseed"], "지표 다시 계산(그동안 매수 없음)")

    def test_param_labels_cover_engine_keys(self):
        keys = set(control.SAVED_KEYS) | set(control.OPS_KEYS)
        self.assertEqual(keys, set(api_read.PARAM_KEY_LABELS))


if __name__ == "__main__":
    unittest.main()
