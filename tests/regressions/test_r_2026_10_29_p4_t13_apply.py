"""
2차 T13 (결정 D9, 요청서 5절): 「이 설정으로 동작」 — 엔진 쪽 시험 (engine/pullback_apply.py).

사용자 결정 1029-05(「권고대로」)·PO 결정 (계획 T13 「구현 메모」):
- A: apply_params 는 T12 _guard(실계좌 거절·다른 모드 엔진 mode_conflict)·예약 중 already_reserved·업비트 출처만.
     엔진이 돌면 엔진 제어 큐에서 apply_saved → 생성자와 같은 새 cfg 교체 → _pullback_params_sha 갱신 → PARAMS 행.
     MA 변경은 재시작(실패면 이전 적용본 바이트 되돌림 + 1회 재기동 + 운영자 CRITICAL).
- B: 봉 단위 변경은 보유가 없을 때만, restart_engine 의 before_start(옛 스레드가 끝난 뒤)에서 pullback_state 행 정리.
     재시작 실패면 행의 종목·봉 단위도 되돌림. EMA→PULLBACK 전환 때도 옛 행(회차 0) 정리.
- C: 보유 중 분할 한도 늘림 거절, 줄임은 즉시(cfg 교체만으로 추가 매수 멈춤).
계획 시험 `test_apply_interval_change_is_reserved_switch` 는 결정 B 로 `test_interval_change_flat_restarts_and_cleans_row`·
`test_interval_change_while_holding_rejected` 로 바꿨다(예약 전환 아님).

실행:
    TELEGRAM_BOT_TOKEN= TELEGRAM_CHAT_ID= TELEGRAM_CHAT_ID_OPERATOR= \
        python3 -m unittest tests.regressions.test_r_2026_10_29_p4_t13_apply -v
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import threading
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from core import engine_control as ec  # noqa: E402
from core.strategy_action import Action  # noqa: E402
from engine import control_requests as cr  # noqa: E402
from engine import params as eparams  # noqa: E402
from engine import pullback_apply as pa  # noqa: E402
from engine import pullback_params as pbp  # noqa: E402
from engine import strategy_switch as ss  # noqa: E402
from services import pullback_state as ps  # noqa: E402
from tests.regressions import baseline_commits as bc  # noqa: E402
from tests.regressions.test_r_2026_10_28_p3_t5_pullback_engine import CALM, CFG, DIP, TICKER, USER, bar  # noqa: E402
from tests.regressions.test_r_2026_10_28_p4_t11_control import FakeThread  # noqa: E402
from tests.regressions.test_r_2026_10_29_p4_t12_switch import SwitchCase, SwitchMgr  # noqa: E402

FIXED_FILES = ("core/strategy_engine.py", "core/strategy_incremental.py", "engine/params.py", "engine/live_loop.py",
               "engine/boot_resume.py", "services/trading_control.py", "engine/engine_manager.py", "services/db.py")


class T13Mgr(SwitchMgr):
    """fail_next 번만 준비 신호를 세우지 않는다(그다음 시작은 정상). stop_delay: 정지 뒤 옛 스레드가 살아 있는 시간."""

    def __init__(self, clock):
        super().__init__(clock)
        self.fail_next = 0
        self.stop_delay = 0.0

    def start_engine(self, u, *, mode, strategy=None):
        ok = super().start_engine(u, mode=mode, strategy=strategy)
        if self.fail_next > 0:
            self.fail_next -= 1
            self._ready[u] = threading.Event()      # 세우지 않음 → start_not_ready
        return ok

    def stop_engine(self, u, *, mode=None):
        th = self._threads.get(u)
        super().stop_engine(u, mode=mode)
        if th is not None:
            th.dies_at = self.clock.t + self.stop_delay


class T13Case(SwitchCase):
    def setUp(self):
        super().setUp()
        self.mgr = T13Mgr(self.clock)
        self.ctl._manager = self.mgr
        self.ctl.ready_wait = 2.0
        p = mock.patch.dict(cr._EXTRA_HANDLERS, {"apply_params": pa.handle_apply})
        p.start()
        self.addCleanup(p.stop)
        # 지금 적용본 = CFG, 활성 전략 = PULLBACK, 마지막 저장 = 업비트
        pbp.apply_saved(USER, self.sha)
        self.applied_sha = self.sha
        eparams.save_active_strategy(USER, "PULLBACK")
        self.hist("upbit")

    # ------------------------------------------------------------ 도우미
    def hist(self, source):
        conn = sqlite3.connect(pa.v2hist_path(USER))
        try:
            conn.execute("CREATE TABLE IF NOT EXISTS v2_settings_history(id INTEGER PRIMARY KEY AUTOINCREMENT, "
                         "user_id TEXT NOT NULL, note TEXT, applied_at TEXT)")
            conn.execute("INSERT INTO v2_settings_history(user_id, note) VALUES (?, ?)", (USER, f"source={source}"))
            conn.commit()
        finally:
            conn.close()

    def save_new(self, **over):
        d = dict(CFG)
        d.update(over)
        self.write_saved(d)
        return self.sha

    def apply(self, mode="TEST", sha=None):
        return self.ctl.execute(self.req("apply_params", mode, {"saved_sha256": sha or self.sha}))

    def applied_bytes(self):
        return Path(pbp.applied_path(USER)).read_bytes()

    def applied(self):
        return json.loads(self.applied_bytes())

    def pb_engine(self):
        """실제 PULLBACK StrategyEngine 을 TEST 로 붙이고, 가짜 시계가 잘 때마다 제어 큐를 비운다(엔진 스레드 흉내)."""
        eng = self.make()
        ec.attach(eng, USER, threading.Event())
        self.mgr.mode = "TEST"
        self.mgr._threads[USER] = FakeThread(self.clock, None)
        self.clock.hooks.append(lambda t: ec.drain_control_queue(eng))
        return eng

    def params_rows(self):
        return self.rows("PARAMS")

    def note(self, row):
        return json.loads(row["note"])

    def put_row(self, **kw):
        d = dict(ticker=TICKER, interval="minute3", entry_count=0, qty=0.0, realized_pnl_krw=1234.0,
                 prev_golden=True, buy_fail_bar_ts="2026-10-29T10:00:00+09:00",
                 last_bar_ts="2026-10-29T10:03:00+09:00")
        d.update(kw)
        self.assertTrue(ps.save(USER, "TEST", d))

    def row(self):
        return ps.load(USER, "TEST")

    def op_crit(self):
        return [c for c in self.notify.call_args_list if c.args[0] == "CRITICAL" and c.kwargs.get("audience") == "operator"]


# ================================================================ A. 엔진 동작 중 — 제어 큐로 cfg 교체
class TestHotApply(T13Case):
    def test_apply_next_bar(self):
        eng = self.pb_engine()
        new = self.save_new(minSlope=0.5)
        r = self.apply()
        self.assertEqual((r["status"], r["code"]), ("done", "ok"), r)
        self.assertEqual(r["detail"]["apply"], "next_bar")
        self.assertEqual(eng.strategy.cfg["minSlope"], 0.5)
        self.assertEqual(pbp.sha256_of(pbp.applied_path(USER)), new)
        self.assertEqual([c for c in self.mgr.calls if c[0] in ("start", "stop")], [])   # 재시작 없음
        rows = self.params_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["state"], rows[0]["params_sha256"]), ("DONE", new))
        self.assertEqual(self.note(rows[0]), {"changed": {"minSlope": [0, 0.5]}, "apply": "next_bar"})
        self.assertIsNotNone(rows[0]["done_at"])

    def test_apply_writes_params_record(self):
        """계획: TP 5→4 (보유 중) → PARAMS 1행, changed.tp == [5,4], apply immediate. audit_settings 에 changed 0."""
        eng = self.pb_engine()
        self.feed(bar(0, **DIP))                                  # 1회차 매수 → 보유
        self.assertTrue(eng.position.has_position)
        self.save_new(tp=4)
        r = self.apply()
        self.assertEqual(r["code"], "ok", r)
        rows = self.params_rows()
        self.assertEqual(len(rows), 1)
        n = self.note(rows[0])
        self.assertEqual(n["changed"]["tp"], [5, 4])
        self.assertEqual(n["apply"], "immediate")
        self.assertEqual(eng.strategy.take_profit, 0.04)
        conn = sqlite3.connect(self.db_path)
        try:
            bad = conn.execute("SELECT COUNT(*) FROM audit_settings WHERE buy_json LIKE '%changed%' "
                               "OR sell_json LIKE '%changed%'").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(bad, 0)

    def test_params_record_not_in_old_ui_conditions(self):
        self.pb_engine()
        self.save_new(tp=4)
        self.assertEqual(self.apply()["code"], "ok")
        from services import db as sdb
        latest = sdb.fetch_latest_audit_settings(USER)
        self.assertNotIn("changed", json.dumps(latest, ensure_ascii=False, default=str))

    def test_sha_updated_after_swap(self):
        eng = self.pb_engine()
        seen = []

        class Rec(type(eng)):
            def __setattr__(s, k, v):
                if k == "_pullback_params_sha":
                    seen.append((s.strategy.cfg["tp"], v))
                super().__setattr__(k, v)
        eng.__class__ = Rec
        new = self.save_new(tp=4)
        self.assertEqual(self.apply()["code"], "ok")
        self.assertEqual(seen, [(4, new)])                          # 교체 뒤에 해시 갱신
        self.assertEqual(eng._pullback_params_sha, new)

    def test_eff_max_splits_recomputed(self):
        eng = self.pb_engine()
        self.save_new(maxSplits=3)
        self.assertEqual(self.apply()["code"], "ok")
        self.assertEqual((eng.strategy.cfg["maxSplits"], eng.strategy.cfg["eff_max_splits"]), (3, 3))
        self.save_new(maxSplits=0, buyOnGoldenCross=True)
        self.assertEqual(self.apply()["code"], "ok")
        c = eng.strategy.cfg
        self.assertEqual((c["golden_only"], c["eff_max_splits"]), (True, 1))
        # 생성자와 같은 cfg (파생 키 포함)
        from core.strategy_pullback import IncrementalPullbackStrategy
        ref = IncrementalPullbackStrategy(USER, TICKER, pbp.validate(dict(CFG, maxSplits=0, buyOnGoldenCross=True)), 3).cfg
        self.assertEqual(c, ref)

    def test_trading_hours_validated_like_constructor(self):
        eng = self.pb_engine()
        self.save_new(enable_trading_hours=True, trading_start_time="10:00", trading_end_time="22:00")
        self.assertEqual(self.apply()["code"], "ok")
        self.assertEqual((eng.strategy.cfg["enable_trading_hours"], eng.strategy.cfg["trading_start_time"]),
                         (True, "10:00"))

    def test_apply_tp_sl_immediate_while_holding(self):
        eng = self.pb_engine()
        self.feed(bar(0, **DIP))
        self.save_new(tp=1, sl=2)
        r = self.apply()
        self.assertEqual(r["detail"]["apply"], "immediate")
        self.feed(bar(1, **CALM))
        self.feed(bar(2, o=55, h=56, l=55, c=56))                  # high 56 ≥ 평단 55 × 1.01 → 익절
        self.assertEqual(len(self.trader.sell_calls), 1)
        self.assertEqual(self.trader.sell_calls[0]["meta"].get("reason"), "TP")

    def test_apply_fewer_splits_stops_adds_only(self):
        """줄임은 보유 중에도 즉시: 새 한도 ≤ 지금 회차 → 추가 매수 멈춤, 파는 일 없음."""
        seq = [bar(0, **DIP), bar(1, **DIP), bar(2, **CALM), bar(3, **DIP), bar(4, **CALM)]
        self.make()                                              # 대조: 그대로 두면 2회차 이상 산다
        self.feed(*seq)
        control = len(self.trader.buy_calls)
        self.assertGreater(control, 1)
        ec._RUNNING.clear()
        self.clock.hooks.clear()
        eng = self.pb_engine()
        self.feed(seq[0])
        self.assertEqual(eng.strategy.entry_count, 1)
        self.save_new(maxSplits=1)
        r = self.apply()
        self.assertEqual((r["code"], r["detail"]["apply"]), ("ok", "next_bar"), r)
        self.feed(*seq[1:])
        self.assertEqual(len(self.trader.buy_calls), 1)
        self.assertEqual(self.trader.sell_calls, [])

    def test_increase_while_holding_rejected(self):
        eng = self.pb_engine()
        self.feed(bar(0, **DIP))
        before = self.applied_bytes()
        self.save_new(maxSplits=7)
        r = self.apply()
        self.assertEqual((r["status"], r["code"]), ("rejected", "holding_splits_increase"))
        self.assertEqual(self.applied_bytes(), before)
        self.assertEqual(eng.strategy.cfg["maxSplits"], 5)
        self.assertEqual(self.params_rows(), [])

    def test_increase_while_flat_applied(self):
        eng = self.pb_engine()
        self.save_new(maxSplits=7)
        self.assertEqual(self.apply()["code"], "ok")
        self.assertEqual(eng.strategy.cfg["eff_max_splits"], 7)

    def test_engine_busy_cancels_without_apply(self):
        self.pb_engine()
        self.clock.hooks.clear()                                 # 엔진 스레드가 큐를 비우지 않음
        before = self.applied_bytes()
        self.save_new(tp=4)
        r = self.apply()
        self.assertEqual(r["code"], "engine_busy")
        self.assertEqual(self.applied_bytes(), before)
        self.assertEqual(self.params_rows(), [])

    def test_unchanged_no_record(self):
        self.pb_engine()
        r = self.apply(sha=self.applied_sha)
        self.assertEqual((r["code"], r["detail"].get("unchanged")), ("ok", True))
        self.assertEqual(self.params_rows(), [])


# ================================================================ A. 엔진 멈춤 — 적용본만
class TestStoppedApply(T13Case):
    def test_stopped_writes_applied_and_record_only(self):
        new = self.save_new(tp=4)
        r = self.apply()
        self.assertEqual((r["code"], r["detail"]["engine"]), ("ok", "stopped"))
        self.assertEqual(pbp.sha256_of(pbp.applied_path(USER)), new)
        self.assertEqual(self.mgr.calls, [])
        self.assertEqual(len(self.params_rows()), 1)

    def test_applied_written_600_by_rename(self):
        ino = os.stat(pbp.applied_path(USER)).st_ino
        self.save_new(tp=4)
        self.assertEqual(self.apply()["code"], "ok")
        st = os.stat(pbp.applied_path(USER))
        self.assertEqual(st.st_mode & 0o777, 0o600)
        self.assertEqual(os.stat(pbp.last_good_path(USER)).st_mode & 0o777, 0o600)
        self.assertNotEqual(st.st_ino, ino)
        self.assertEqual([n for n in os.listdir(".") if n.endswith(".tmp")], [])

    def test_stopped_increase_while_row_holding_rejected(self):
        self.put_row(entry_count=2, qty=1.0)
        before = self.applied_bytes()
        self.save_new(maxSplits=7)
        self.assertEqual(self.apply()["code"], "holding_splits_increase")
        self.assertEqual(self.applied_bytes(), before)

    def test_stopped_interval_change_cleans_row(self):
        self.put_row()
        self.save_new(interval="minute5")
        r = self.apply()
        self.assertEqual((r["code"], r["detail"]["apply"]), ("ok", "restart"), r)
        row = self.row()
        self.assertEqual((row["ticker"], row["interval"]), (TICKER, "minute5"))
        self.assertEqual((row["buy_fail_bar_ts"], row["prev_golden"], row["last_bar_ts"]), (None, None, None))
        self.assertEqual(row["realized_pnl_krw"], 1234.0)
        self.assertEqual(self.mgr.calls, [])


# ================================================================ 거절 규칙
class TestRejects(T13Case):
    def assertUntouched(self, before):
        self.assertEqual(self.applied_bytes(), before)
        self.assertEqual(self.params_rows(), [])
        self.assertEqual([c for c in self.mgr.calls if c[0] in ("start", "stop")], [])

    def test_apply_rejects_binance_source(self):
        before = self.applied_bytes()
        self.hist("binance")
        self.save_new(tp=4)
        self.assertEqual(self.apply()["code"], "source_not_upbit")
        self.assertUntouched(before)
        self.assertEqual(cr.CODE_TEXT["source_not_upbit"].count("참고용"), 1)

    def test_apply_rejects_without_history(self):
        os.remove(pa.v2hist_path(USER))
        self.save_new(tp=4)
        self.assertEqual(self.apply()["code"], "source_not_upbit")

    def test_live_rejected(self):
        before = self.applied_bytes()
        self.save_new(tp=4)
        r = self.apply(mode="LIVE")
        self.assertEqual((r["status"], r["code"]), ("rejected", "apply_live_not_supported"))   # fix 1: 적용 전용 코드
        t = cr.CODE_TEXT["apply_live_not_supported"]
        self.assertEqual(t, "새 전략 설정 적용은 아직 실계좌(LIVE)에서 할 수 없습니다. 모의(TEST)에서만 할 수 있습니다.")
        self.assertNotIn("전환", t)
        self.assertUntouched(before)

    def test_mode_conflict(self):
        before = self.applied_bytes()
        self.mgr.mode = "LIVE"
        self.save_new(tp=4)
        r = self.apply(mode="TEST")
        self.assertEqual((r["code"], r["detail"]["running"]), ("mode_conflict", "LIVE"))
        self.assertUntouched(before)

    def test_revert_reservation_rejected(self):
        before = self.applied_bytes()
        rid = self.add_row(kind="REVERT", from_strategy="PULLBACK", to_strategy="EMA")
        self.save_new(tp=4)
        r = self.apply()
        self.assertEqual((r["code"], r["detail"]["reservation_id"]), ("already_reserved", rid))
        self.assertUntouched(before)

    def test_not_pullback_rejected(self):
        eparams.save_active_strategy(USER, "EMA")
        self.save_new(tp=4)
        self.assertEqual(self.apply()["code"], "apply_not_pullback")

    def test_apply_sha_mismatch_rejected(self):
        before = self.applied_bytes()
        old = self.save_new(tp=4)
        self.save_new(tp=3)                                      # 요청 뒤 다른 저장
        self.assertEqual(self.apply(sha=old)["code"], "sha_mismatch")
        self.assertUntouched(before)

    def test_apply_liveparams_invalid_rejected(self):
        """X9: 숫자 섞인 종목 → invalid_ticker, 적용본 불변."""
        before = self.applied_bytes()
        self.save_new(ticker="KRW-1INCH")
        self.assertEqual(self.apply()["code"], "invalid_ticker")
        self.assertUntouched(before)

    def test_bad_sha_format(self):
        self.assertEqual(self.ctl.execute(self.req("apply_params", "TEST", {"saved_sha256": "x"}))["code"],
                         "bad_request")

    def test_investor_texts_have_no_internal_names(self):
        import re as _re
        for c in ("holding_interval_change", "holding_splits_increase", "source_not_upbit", "apply_not_pullback",
                  "invalid_ticker", "apply_failed", "apply_live_not_supported"):
            t = cr.CODE_TEXT[c]
            self.assertIsNone(_re.search(r"[a-z]+_[a-z_]+|strategy_switch|PULLBACK|sha256|\bsha\b|pullback_state", t), t)
        self.assertEqual(cr.CODE_TEXT["holding_interval_change"],
                         "보유 중에는 봉 단위를 바꿀 수 없습니다 — 매도 뒤 다시 적용해 주세요")
        self.assertIn("apply_failed", cr.ATTEMPTED_CODES)


# ================================================================ A. MA 변경 = 재시작
class TestReseed(T13Case):
    def test_apply_ma_change_reseeds_no_buy(self):
        self.pb_engine()
        new = self.save_new(ma60p=4)
        r = self.apply()
        self.assertEqual((r["code"], r["detail"]["apply"]), ("ok", "reseed"), r)
        self.assertEqual([c[0] for c in self.mgr.calls], ["stop", "start"])
        self.assertEqual(self.starts("PULLBACK")[0][2], "TEST")
        self.assertEqual(pbp.sha256_of(pbp.applied_path(USER)), new)   # 기동이 새 MA 로 시드
        self.assertEqual(self.note(self.params_rows()[0])["apply"], "reseed")
        self.assertEqual(self.trader.buy_calls, [])

    def test_reseed_while_holding_allowed(self):
        self.pb_engine()
        self.feed(bar(0, **DIP))
        self.save_new(maType="sma")
        self.assertEqual(self.apply()["detail"]["apply"], "reseed")

    def test_restart_failure_restores_bytes_and_restarts_once(self):
        self.pb_engine()
        before_a = self.applied_bytes()
        before_lg = Path(pbp.last_good_path(USER)).read_bytes()
        self.mgr.fail_next = 1
        self.save_new(ma60p=4)
        r = self.apply()
        self.assertEqual((r["status"], r["code"]), ("error", "apply_failed"), r)
        self.assertEqual(self.applied_bytes(), before_a)
        self.assertEqual(Path(pbp.last_good_path(USER)).read_bytes(), before_lg)
        self.assertEqual(len(self.starts("PULLBACK")), 2)          # 새 설정 1 + 이전 설정 1회 다시
        self.assertEqual(r["detail"]["restarted"], "done/ok")
        self.assertEqual(len(self.op_crit()), 1)
        self.assertEqual(self.params_rows(), [])


# ================================================================ B. 봉 단위 변경
class TestIntervalChange(T13Case):
    def test_interval_change_flat_restarts_and_cleans_row(self):
        """(계획 test_apply_interval_change_is_reserved_switch 를 결정 B 로 바꿈) 미보유 → 재시작 + 행 정리."""
        self.pb_engine()
        self.put_row()
        new = self.save_new(interval="minute5")
        r = self.apply()
        self.assertEqual((r["code"], r["detail"]["apply"]), ("ok", "restart"), r)
        self.assertEqual([c[0] for c in self.mgr.calls], ["stop", "start"])
        row = self.row()
        self.assertEqual((row["interval"], row["buy_fail_bar_ts"], row["prev_golden"], row["last_bar_ts"]),
                         ("minute5", None, None, None))
        self.assertEqual(row["realized_pnl_krw"], 1234.0)
        self.assertEqual(pbp.sha256_of(pbp.applied_path(USER)), new)
        self.assertIsNone(ss.reservation(USER, "TEST"))            # 예약 전환이 아님

    def test_interval_change_while_holding_rejected(self):
        self.pb_engine()
        self.wallet = 1.5
        before = self.applied_bytes()
        self.save_new(interval="minute5")
        r = self.apply()
        self.assertEqual((r["status"], r["code"]), ("rejected", "holding_interval_change"))
        self.assertEqual(self.applied_bytes(), before)
        self.assertEqual(self.mgr.calls, [])
        self.assertEqual(r["detail"], {})

    def test_interval_change_row_holding_rejected_before_stop(self):
        self.pb_engine()
        self.put_row(entry_count=1, qty=0.5)
        self.save_new(interval="minute5")
        self.assertEqual(self.apply()["code"], "holding_interval_change")
        self.assertEqual(self.mgr.calls, [])

    def test_hook_sees_round_after_stop_keeps_row_and_restores(self):
        """정지 뒤 다시 읽은 행에 회차가 있으면 손대지 않고 적용본을 되돌린 뒤 이전 설정으로 1회 다시 띄움."""
        self.pb_engine()
        self.put_row()
        before = self.applied_bytes()
        self.mgr.on_stop = lambda u, m: self.put_row(entry_count=1, qty=0.5)
        self.save_new(interval="minute5")
        with self.assertLogs("engine.pullback_apply", level="WARNING") as lg:
            r = self.apply()
        self.assertEqual((r["status"], r["code"]), ("rejected", "holding_interval_change"))
        row = self.row()
        self.assertEqual((row["interval"], row["entry_count"]), ("minute3", 1))
        self.assertEqual(self.applied_bytes(), before)
        self.assertEqual(len(self.starts("PULLBACK")), 1)          # 이전 설정으로 1회(보유분을 관리할 엔진)
        self.assertEqual(self.params_rows(), [])
        # fix 1: 보통 거절 — 「재시작 실패」 운영자 CRITICAL 없음, WARNING 만
        self.assertEqual(self.op_crit(), [])
        self.assertEqual([x for x in lg.records if x.levelname == "CRITICAL"], [])
        self.assertTrue(any("보유 중" in x.getMessage() and x.levelname == "WARNING" for x in lg.records))

    def test_hook_holding_then_restart_fails_is_critical(self):
        """보유 중 거절 뒤 이전 설정 기동마저 실패하면 그때만 진짜 재시작 실패 CRITICAL."""
        self.pb_engine()
        self.put_row()
        before = self.applied_bytes()
        self.mgr.on_stop = lambda u, m: self.put_row(entry_count=1, qty=0.5)
        self.mgr.fail_next = 1
        self.save_new(interval="minute5")
        r = self.apply()
        self.assertEqual(r["code"], "holding_interval_change")
        self.assertEqual(self.applied_bytes(), before)
        self.assertEqual(len(self.op_crit()), 1)

    def test_flat_state_none_rejects_interval_change(self):
        """V15: 보유 판정 못 함(엔진 바쁨 → flat_state None) + 행은 미보유 → 봉 단위 변경 거절(fail closed)."""
        self.pb_engine()
        self.put_row()
        before = self.applied_bytes()
        self.save_new(interval="minute5")
        with mock.patch.object(ss, "flat_state", return_value=None):
            r = self.apply()
        self.assertEqual((r["status"], r["code"]), ("rejected", "holding_interval_change"))
        self.assertEqual(self.applied_bytes(), before)
        self.assertEqual(self.mgr.calls, [])
        self.assertEqual(self.row()["interval"], "minute3")


class TestFix1Stopped(T13Case):
    def test_flat_state_none_rejects_increase(self):
        """V15: 엔진 멈춤 + 판정 못 함(None) + 행 미보유 → 늘림 거절(fail closed)."""
        self.put_row()
        before = self.applied_bytes()
        self.save_new(maxSplits=7)
        with mock.patch.object(ss, "flat_state", return_value=None):
            r = self.apply()
        self.assertEqual((r["status"], r["code"]), ("rejected", "holding_splits_increase"))
        self.assertEqual(self.applied_bytes(), before)
        self.assertEqual(self.params_rows(), [])

    def test_stopped_row_cleanup_error_restores_applied(self):
        """V14: 엔진 멈춤 경로의 행 정리에서 예외(state=="error") → 적용본·사본 바이트 되돌림, 기록 없음."""
        self.put_row()
        before = self.applied_bytes()
        lg_before = Path(pbp.last_good_path(USER)).read_bytes()
        self.save_new(interval="minute5")
        with mock.patch.object(pa, "rewrite_row_market", side_effect=sqlite3.OperationalError("locked")):
            r = self.apply()
        self.assertEqual((r["status"], r["code"]), ("error", "apply_failed"))
        self.assertEqual(self.applied_bytes(), before)
        self.assertEqual(Path(pbp.last_good_path(USER)).read_bytes(), lg_before)
        self.assertEqual(self.params_rows(), [])
        self.assertEqual(self.row()["interval"], "minute3")

    def test_restore_row_market_skips_holding_row(self):
        """fix 1: 되돌리기도 미보유 조건으로만 — 그사이 회차가 생긴 행은 덮지 않는다."""
        prev = dict(ticker=TICKER, interval="minute3", buy_fail_bar_ts=None, prev_golden=None, last_bar_ts=None)
        self.put_row(interval="minute5", entry_count=1, qty=0.5)
        self.assertFalse(pa.restore_row_market(USER, "TEST", prev))
        self.assertEqual((self.row()["interval"], self.row()["entry_count"]), ("minute5", 1))
        self.put_row(interval="minute5")
        self.assertTrue(pa.restore_row_market(USER, "TEST", prev))
        self.assertEqual(self.row()["interval"], "minute3")

    def test_restart_failure_reverts_row_and_applied(self):
        self.pb_engine()
        self.put_row()
        before = self.applied_bytes()
        self.mgr.fail_next = 1
        self.save_new(interval="minute5")
        r = self.apply()
        self.assertEqual(r["code"], "apply_failed")
        row = self.row()
        self.assertEqual((row["ticker"], row["interval"]), (TICKER, "minute3"))
        self.assertEqual((row["prev_golden"], row["buy_fail_bar_ts"] is not None, row["last_bar_ts"] is not None),
                         (1, True, True))
        self.assertEqual(self.applied_bytes(), before)
        self.assertEqual(len(self.starts("PULLBACK")), 2)
        self.assertEqual(len(self.op_crit()), 1)

    def test_row_modified_only_after_old_thread_ends(self):
        """정지 뒤 옛 엔진 스레드가 1초 더 살며 봉마다 행을 저장(UPSERT)해도, 정리는 그 뒤라 새 봉 단위가 남는다."""
        self.pb_engine()
        self.put_row()
        old_th = self.mgr._threads[USER]
        self.mgr.stop_delay = 1.0
        persists = []

        def old_engine_persist(t):
            if old_th.is_alive() and self.mgr.mode is None:     # 정지 신호 뒤에도 도는 옛 엔진
                persists.append(t)
                ps.save(USER, "TEST", dict(ticker=TICKER, interval="minute3", realized_pnl_krw=1234.0))
        self.clock.hooks.append(old_engine_persist)
        seen = []
        real = pa.rewrite_row_market

        def spy(*a, **k):
            seen.append(old_th.is_alive())
            return real(*a, **k)
        self.save_new(interval="minute5")
        with mock.patch.object(pa, "rewrite_row_market", side_effect=spy):
            r = self.apply()
        self.assertEqual(r["code"], "ok", r)
        self.assertTrue(persists)                                   # 옛 엔진이 실제로 덮어쓰기를 했다
        self.assertEqual(seen, [False])                             # 정리는 옛 스레드가 끝난 뒤 1회
        self.assertEqual(self.row()["interval"], "minute5")


# ================================================================ B. EMA→PULLBACK 전환 때 옛 행 정리
class TestSwitchCleansStaleRow(SwitchCase):
    def setUp(self):
        super().setUp()
        self.db_conn = None

    def test_switch_cleans_flat_stale_row(self):
        ps.save(USER, "TEST", dict(ticker="KRW-OLD", interval="minute1", realized_pnl_krw=777.0, prev_golden=True,
                                   last_bar_ts="2026-10-29T10:00:00+09:00"))
        r = self.switch()
        self.assertEqual(r["code"], "ok", r)
        row = ps.load(USER, "TEST")
        self.assertEqual((row["ticker"], row["interval"]), (TICKER, "minute3"))
        self.assertEqual((row["prev_golden"], row["last_bar_ts"], row["realized_pnl_krw"]), (None, None, 777.0))

    def test_switch_keeps_open_stale_row(self):
        """옛 행에 회차가 있으면 손대지 않는다(추측하지 않음 — 계획 메모의 남은 일). 전환은 계속."""
        ps.save(USER, "TEST", dict(ticker="KRW-OLD", interval="minute1", entry_count=2, qty=3.0))
        with self.assertLogs("engine.pullback_apply", "WARNING"):
            r = self.switch()
        self.assertEqual(r["code"], "ok", r)
        row = ps.load(USER, "TEST")
        self.assertEqual((row["ticker"], row["entry_count"]), ("KRW-OLD", 2))

    def test_switch_without_row_unchanged(self):
        self.assertEqual(self.switch()["code"], "ok")
        self.assertIsNone(ps.load(USER, "TEST"))


# ================================================================ 설치·고정 파일
class TestInstallAndFixed(unittest.TestCase):
    def test_install_registers_apply_params(self):
        with mock.patch.dict(cr._EXTRA_HANDLERS, {}, clear=True), mock.patch.dict(pa._INSTALLED, {"done": False}):
            pa.install()
            pa.install()
            self.assertEqual(cr._EXTRA_HANDLERS, {"apply_params": pa.handle_apply})

    def test_boot_installs_apply_before_control_loop(self):
        src = (ROOT / "scripts" / "tradebot_boot.py").read_text(encoding="utf-8")
        body = src.split("def _control_thread")[1].split("\ndef ")[0]
        self.assertLess(body.index("_install_apply()"), body.index("control_loop()"))

    def test_engine_queue_kind_routes_to_apply(self):
        self.assertEqual(ec.APPLY_KIND, "pullback_apply")
        item = ec.ControlItem(ec.APPLY_KIND, {"saved_sha256": "0" * 64})
        with mock.patch.object(pa, "engine_apply", return_value={"status": "done", "code": "ok", "detail": {}}) as m:
            self.assertEqual(ec._execute(object(), item)["code"], "ok")
        m.assert_called_once()

    def test_fixed_files_unchanged_since_t12(self):
        """실계좌 EMA 경로 고정 8개는 T12 커밋과 바이트가 같다(적용본 감시를 live_loop 에 넣지 않음)."""
        for rel in FIXED_FILES:
            base = bc.git_show(rel, bc.FIXED_FILES_COMMIT)
            if base is None:
                self.skipTest("git 기준 원본 없음")
            self.assertEqual((ROOT / rel).read_text(encoding="utf-8"), base, rel)

    def test_no_applied_mtime_watch(self):
        """적용본은 요청·기동 때만 읽는다(감시 함수 없음)."""
        for rel in ("engine/live_loop.py", "engine/pullback_apply.py", "core/engine_control.py"):
            self.assertNotIn("_maybe_reload_pullback", (ROOT / rel).read_text(encoding="utf-8"))

    def test_restart_engine_before_start_runs_between_stop_and_start(self):
        from tests.regressions.test_r_2026_10_28_p4_t11_control import FakeClock
        clock = FakeClock()
        mgr = T13Mgr(clock)
        mgr.mode = "TEST"
        mgr._threads[USER] = FakeThread(clock, None)
        mgr.stop_delay = 0.5
        import tempfile
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        ctl = cr.Controller(base_dir=Path(tmp.name), alive_dir=Path(tmp.name), manager=mgr, now=clock.now,
                            monotonic=clock.mono, sleep=clock.sleep, notify=mock.MagicMock())
        order = []
        th = mgr._threads[USER]
        r = ctl.restart_engine(USER, "TEST", "PULLBACK",
                               before_start=lambda: order.append(("hook", th.is_alive(), list(mgr.calls))) or None)
        self.assertEqual(r["code"], "ok")
        self.assertEqual(order, [("hook", False, [("stop", USER, "TEST")])])
        # 결과를 돌려주면 시작하지 않는다
        mgr._threads[USER] = FakeThread(clock, None)
        mgr.mode = "TEST"
        mgr.calls.clear()
        r = ctl.restart_engine(USER, "TEST", "PULLBACK", before_start=lambda: {"status": "rejected", "code": "x",
                                                                                 "detail": {}})
        self.assertEqual(r["code"], "x")
        self.assertEqual([c[0] for c in mgr.calls], ["stop"])


if __name__ == "__main__":
    unittest.main()
