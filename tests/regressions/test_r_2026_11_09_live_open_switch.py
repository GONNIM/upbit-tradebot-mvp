"""1109 눌림목 실계좌 열기 — 작업 B: 실계좌 전환·복귀·적용·운용 설정 열기(축소안).

축소안 확정 사항:
- 실계좌 전환·복귀는 「미보유 + 미체결 없음」일 때만 즉시 처리. 보유 중이면 거절(「매도 뒤 다시 눌러 주세요」), 예약 행을 만들지 않는다.
- 전환 때 모드 표식(LIVE)을 활성 파일보다 먼저 쓴다. 되돌림·복구 경로는 표식을 쓰지 않는다.
- 지갑 읽기 실패는 「보유 중」과 같이 거절(wallet_unknown).
- 실계좌 엔진(EMA)이 돌고 있어도 보유 확인은 엔진 큐로 간다(M5).
- 실계좌 처리 중 행의 기동 복구는 행 상태만 바꾸고 엔진 재시작·활성 파일 변경을 하지 않는다.
시험은 바깥 연결 없이 가짜 관리자·임시 폴더만 쓴다.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from engine import active_mode as am
from engine import control_requests as cr
from engine import params as eparams
from engine import pullback_params as pbp
from engine import strategy_switch as ss
from tests.regressions.test_r_2026_10_29_p4_t12_switch import (
    CFG, EMA_IV, EMA_TICKER, REAL_WALLET_QTY, SwitchCase, TICKER, USER, tick,
)


def live_cfg(**over):
    d = dict(CFG)
    d["invest_ratio_pct_live"] = 10.0
    d.update(over)
    return d


class LiveSwitchCase(SwitchCase):
    def setUp(self):
        super().setUp()
        self.write_saved(live_cfg())          # 실계좌 비율이 든 저장본


# ================================================================ 전환
class TestLiveSwitch(LiveSwitchCase):
    def test_live_switch_flat_runs_and_writes_marker_first(self):
        order = []
        real_marker = am.write_marker
        real_save = eparams.save_active_strategy

        def marker(u, m):
            order.append(("marker", m))
            return real_marker(u, m)

        def save(u, s):
            order.append(("active", s))
            return real_save(u, s)
        with mock.patch.object(am, "write_marker", side_effect=marker), \
                mock.patch("engine.params.save_active_strategy", side_effect=save):
            r = self.switch(mode="LIVE")
        self.assertEqual((r["status"], r["code"]), ("done", "ok"), r)
        self.assertEqual(order[:2], [("marker", "LIVE"), ("active", "PULLBACK")])
        self.assertEqual(am.read_marker(USER), "LIVE")
        self.assertEqual(self.active(), "PULLBACK")
        self.assertEqual(self.starts("PULLBACK"), [("start", USER, "LIVE", "PULLBACK")])
        self.assertEqual([(x["mode"], x["state"]) for x in self.rows("SWITCH")], [("LIVE", "DONE")])

    def test_live_switch_refused_when_holding_creates_no_reservation(self):
        self.wallet = 3.0
        r = self.switch(mode="LIVE")
        self.assertEqual((r["status"], r["code"]), ("rejected", "live_not_flat"))
        self.assertIn("매도 뒤 다시 눌러 주세요", cr.CODE_TEXT["live_not_flat"])
        self.assertEqual(self.rows(), [])                  # 예약 행 없음
        self.assertEqual(self.active(), "EMA")
        self.assertEqual(self.mgr.calls, [])
        self.assertFalse(os.path.exists(am.marker_path(USER)))
        self.assertFalse(os.path.exists(pbp.applied_path(USER)))

    def test_live_switch_refused_with_open_order(self):
        self.pending = True
        r = self.switch(mode="LIVE")
        self.assertEqual((r["status"], r["code"]), ("rejected", "live_not_flat"))
        self.assertEqual(self.rows(), [])

    def test_live_switch_refused_when_ratio_missing(self):
        self.write_saved(dict(CFG))                         # 실계좌 비율 없음
        r = self.switch(mode="LIVE")
        self.assertEqual((r["status"], r["code"]), ("rejected", "live_ratio_missing"))
        self.assertEqual(self.mgr.calls, [])
        self.assertEqual(self.rows(), [])
        self.assertIn("투자 비율", cr.CODE_TEXT["live_ratio_missing"])

    def test_test_switch_does_not_need_ratio(self):
        self.write_saved(dict(CFG))
        r = self.switch(mode="TEST")
        self.assertEqual((r["status"], r["code"]), ("done", "ok"))
        self.assertFalse(os.path.exists(am.marker_path(USER)) and am.read_marker(USER) == "LIVE")

    def test_switch_uses_saved_ratio_not_stale_applied_file(self):
        """옛 적용본에 비율이 없어도 저장본에 있으면 전환 허용."""
        Path(pbp.applied_path(USER)).write_text(json.dumps(dict(CFG)), encoding="utf-8")
        r = self.switch(mode="LIVE")
        self.assertEqual((r["status"], r["code"]), ("done", "ok"))

    def test_live_switch_wallet_unknown_is_refused(self):
        with mock.patch.object(ss, "flat_state", return_value=None):
            r = self.switch(mode="LIVE")
        self.assertEqual((r["status"], r["code"]), ("rejected", "wallet_unknown"))
        self.assertEqual(self.rows(), [])
        self.assertEqual(self.mgr.calls, [])

    def test_live_switch_recheck_fails_cancels_row_not_reserved(self):
        """M1: 활성 파일 쓰기 직전 재확인에서 보유가 보이면 행을 CANCELED 로 하고 거절(예약으로 남기지 않음)."""
        reads = {"n": 0}

        def wallet():
            reads["n"] += 1
            return 0.0 if reads["n"] <= 2 else 2.0        # 1·2번째 = 요청 판정(지금 종목·대상 종목), 3번째 = 재확인
        self.wallet = wallet
        r = self.switch(mode="LIVE")
        self.assertEqual((r["status"], r["code"]), ("rejected", "live_not_flat"), r)
        rows = self.rows("SWITCH")
        self.assertEqual([(x["state"], x["note"]) for x in rows], [("CANCELED", "live_not_flat")])
        self.assertEqual(self.active(), "EMA")
        self.assertEqual(self.starts(), [])
        self.assertFalse(os.path.exists(am.marker_path(USER)))

    def test_marker_write_failure_blocks_switch_and_keeps_active(self):
        with mock.patch.object(am, "write_marker", side_effect=OSError("disk")):
            r = self.switch(mode="LIVE")
        self.assertEqual(r["status"], "error")
        self.assertEqual(self.active(), "EMA")
        self.assertEqual(self.starts("PULLBACK"), [])

    def test_mode_conflict_still_rejected_for_live(self):
        self.mgr.mode = "TEST"
        r = self.switch(mode="LIVE")
        self.assertEqual((r["status"], r["code"]), ("rejected", "mode_conflict"))
        self.assertEqual(self.mgr.calls, [])


# ================================================================ 1109 지적 1: 대상 종목 확인 (먼지 허용은 되돌림)
class TestTargetTickerOnly(LiveSwitchCase):
    def test_switch_refused_when_target_ticker_held(self):
        """지금 종목(EMA)은 비었어도 대상 종목(새 전략 종목)을 앱에서 보유 중이면 전환하지 않는다(새 전략이 그 코인을 팔 수 있음)."""
        self.tickers_held = {EMA_TICKER: 0.0, TICKER: 5.0}
        r = self.switch(mode="LIVE")
        self.assertEqual((r["status"], r["code"]), ("rejected", "live_not_flat"))
        self.assertEqual(self.rows(), [])
        self.assertEqual(self.active(), "EMA")
        self.assertEqual(self.mgr.calls, [])

    def test_switch_recheck_also_looks_at_target_ticker(self):
        """활성 파일 쓰기 직전 재확인에서 대상 종목 보유가 보이면 행 CANCELED·거절."""
        state = {"n": 0}
        orig = ss.target_ticker_flat

        def flaky(ctl, user, mode, strategy, ticker):
            state["n"] += 1
            return True if state["n"] == 1 else False        # 요청 판정은 통과, 재확인에서 보유
        with mock.patch.object(ss, "target_ticker_flat", side_effect=flaky):
            r = self.switch(mode="LIVE")
        self.assertEqual((r["status"], r["code"]), ("rejected", "live_not_flat"))
        self.assertEqual([(x["state"], x["note"]) for x in self.rows("SWITCH")], [("CANCELED", "live_not_flat")])
        self.assertEqual(self.active(), "EMA")
        self.assertIsNotNone(orig)

    def test_target_ticker_read_failure_is_wallet_unknown(self):
        with mock.patch.object(ss, "target_ticker_flat", return_value=None):
            r = self.switch(mode="LIVE")
        self.assertEqual((r["status"], r["code"]), ("rejected", "wallet_unknown"))

    def test_target_ticker_open_order_blocks(self):
        calls = {"n": 0}

        def pending(u, t):
            calls["n"] += 1
            return t == TICKER
        with mock.patch.object(ss, "_pending_buy", side_effect=pending):
            r = self.switch(mode="LIVE")
        self.assertEqual((r["status"], r["code"]), ("rejected", "live_not_flat"))

    def test_revert_refused_when_target_ticker_held(self):
        eparams.save_active_strategy(USER, "PULLBACK")
        am.write_marker(USER, "LIVE")
        pbp.apply_saved(USER, self.sha)
        self.add_row(mode="LIVE", state="DONE")
        self.tickers_held = {TICKER: 0.0, EMA_TICKER: 3.0}   # 돌아갈 EMA 종목을 앱에서 보유 중
        r = self.ctl.execute(self.req("revert", "LIVE"))
        self.assertEqual((r["status"], r["code"]), ("rejected", "live_not_flat"))
        self.assertEqual(self.active(), "PULLBACK")

    def test_tiny_balance_still_counts_as_holding_flat_threshold_is_1e6(self):
        """먼지 허용은 되돌렸다 — 미보유 기준은 수량 1e-6 미만 그대로(작은 잔량도 보유 취급, 값어치로 판단하지 않는다)."""
        self.assertEqual(ss.FLAT_EPS, 1e-6)
        self.tickers_held = {EMA_TICKER: 0.0004, TICKER: 0.0}
        r = self.switch(mode="LIVE")
        self.assertEqual((r["status"], r["code"]), ("rejected", "live_not_flat"))
        self.assertFalse(hasattr(ss, "_is_dust"))
        self.assertFalse(hasattr(ss, "_market_price"))


# ================================================================ 보유 확인 경로
class TestFlatStateLive(LiveSwitchCase):
    def test_flat_check_runs_through_live_engine_queue(self):
        """M5: 실계좌 엔진(EMA)이 켜진 상태에서도 보유 확인이 엔진 큐로 간다."""
        self.run_engine("EMA")
        self.mgr.mode = "LIVE"
        st = ss.flat_state(self.ctl, USER, "LIVE", "EMA", EMA_TICKER)
        self.assertIsNotNone(st)
        self.assertTrue(st["flat"])
        self.assertEqual(self.wallet_reads, 1)        # 엔진 스레드(큐)에서 읽음
        self.wallet = 2.0
        self.assertFalse(ss.flat_state(self.ctl, USER, "LIVE", "EMA", EMA_TICKER)["flat"])

    def test_other_mode_engine_still_not_queued(self):
        self.run_engine("EMA")
        self.mgr.mode = "LIVE"
        self.assertIsNone(ss.flat_state(self.ctl, USER, "TEST", "EMA", EMA_TICKER))

    def test_flat_check_counts_pending_split_as_not_flat(self):
        self.run_engine("EMA")
        self.mgr.mode = "LIVE"
        self.eng._pending_split = {"uuid": None}
        self.assertFalse(ss.flat_state(self.ctl, USER, "LIVE", "EMA", EMA_TICKER)["flat"])

    def test_real_wallet_qty_live_uses_checked_read_and_failure_raises(self):
        class T:
            test_mode = False

            def __init__(self, ret):
                self.ret = ret

            def coin_balance_checked(self, ticker):
                return self.ret

            def _coin_balance(self, ticker):
                raise AssertionError("실계좌는 coin_balance_checked 를 써야 한다")
        self.assertEqual(REAL_WALLET_QTY(USER, EMA_TICKER, T((1.5, True))), 1.5)
        with self.assertRaises(ss.WalletUnknown):
            REAL_WALLET_QTY(USER, EMA_TICKER, T((0.0, False)))

    def test_engine_off_flat_check_wallet_read_failure_is_not_flat(self):
        """엔진이 꺼진 실계좌 판정: 지갑 읽기 실패 → None(보유 중으로 봄)."""
        with mock.patch.object(ss, "_wallet_qty", side_effect=ss.WalletUnknown("x")):
            self.assertIsNone(ss.flat_state(self.ctl, USER, "LIVE", "EMA", EMA_TICKER))


# ================================================================ 복귀
class TestLiveRevert(LiveSwitchCase):
    def _to_live_pullback(self):
        eparams.save_active_strategy(USER, "PULLBACK")
        am.write_marker(USER, "LIVE")
        pbp.apply_saved(USER, self.sha)
        self.add_row(mode="LIVE", state="DONE")

    def test_live_revert_flat_goes_back_and_keeps_marker_untouched(self):
        self._to_live_pullback()
        with mock.patch.object(am, "write_marker", side_effect=AssertionError("복귀는 표식을 쓰지 않는다")):
            r = self.ctl.execute(self.req("revert", "LIVE"))
        self.assertEqual((r["status"], r["code"]), ("done", "ok"), r)
        self.assertEqual(self.active(), "EMA")
        self.assertEqual(am.read_marker(USER), "LIVE")      # 남아도 활성이 EMA 면 무시

    def test_live_revert_refused_when_holding_no_row(self):
        self._to_live_pullback()
        before = len(self.rows())
        self.wallet = 1.0
        r = self.ctl.execute(self.req("revert", "LIVE"))
        self.assertEqual((r["status"], r["code"]), ("rejected", "live_not_flat"))
        self.assertEqual(len(self.rows()), before)
        self.assertEqual(self.active(), "PULLBACK")

    def test_test_session_cannot_revert_live_marker(self):
        self._to_live_pullback()
        r = self.ctl.execute(self.req("revert", "TEST"))
        self.assertEqual((r["status"], r["code"]), ("rejected", "mode_marker_mismatch"))
        self.assertEqual(self.mgr.calls, [])
        self.assertEqual(self.active(), "PULLBACK")

    def test_live_session_cannot_revert_test_pullback(self):
        eparams.save_active_strategy(USER, "PULLBACK")       # 표식 없음 = TEST
        r = self.ctl.execute(self.req("revert", "LIVE"))
        self.assertEqual((r["status"], r["code"]), ("rejected", "mode_marker_mismatch"))

    def test_revert_failure_rewrites_active_without_marker_write(self):
        """복귀 실패로 활성을 PULLBACK 으로 되돌릴 때 표식 쓰기에 막히지 않는다."""
        self._to_live_pullback()
        self.mgr.fail.add("EMA")
        with mock.patch.object(am, "write_marker", side_effect=OSError("disk")):
            r = self.ctl.execute(self.req("revert", "LIVE"))
        self.assertEqual(r["code"], "switch_failed")
        self.assertEqual(self.active(), "PULLBACK")


# ================================================================ 기동 복구(실계좌 처리 중 행)
class TestLiveRecovery(LiveSwitchCase):
    def _row(self, **kw):
        d = dict(mode="LIVE", state="RESERVED", note=ss.NOTE_SWITCHING)
        d.update(kw)
        return self.add_row(**d)

    def test_recover_all_includes_live_rows_and_never_restarts_engine(self):
        eparams.save_active_strategy(USER, "EMA")              # 전환 전에 죽음 → 활성 != 대상
        rid = self._row()
        done = ss.Monitor().recover_all(self.ctl, [USER])
        self.assertEqual(done, [(USER, rid, "aborted")])
        row = self.rows("SWITCH")[0]
        self.assertEqual((row["state"], row["note"]), ("FAILED", "aborted_before_switch"))
        self.assertEqual(self.mgr.calls, [])

    def test_live_row_not_ready_marks_failed_without_restart_or_active_rewrite(self):
        eparams.save_active_strategy(USER, "PULLBACK")
        am.write_marker(USER, "LIVE")
        rid = self._row()
        self.mgr.mode = None                                    # 엔진이 안 떠 있음
        res = ss.Monitor().recover_row(self.ctl, USER, ss.fetch_row(USER, rid))
        self.assertEqual(res, "failed")
        row = self.rows("SWITCH")[0]
        self.assertEqual((row["state"], row["note"]), ("FAILED", "boot_not_ready"))
        self.assertEqual(self.mgr.calls, [])                    # 엔진 재시작 없음
        self.assertEqual(self.active(), "PULLBACK")             # 활성 파일도 그대로(행 상태만 바꾼다)

    def test_live_row_ready_is_recovered_done(self):
        eparams.save_active_strategy(USER, "PULLBACK")
        rid = self._row()
        self.mgr.mode = "LIVE"
        ev = threading.Event()
        ev.set()
        self.mgr._ready[USER] = ev
        res = ss.Monitor().recover_row(self.ctl, USER, ss.fetch_row(USER, rid))
        self.assertEqual(res, "recovered")
        self.assertEqual(self.rows("SWITCH")[0]["state"], "DONE")

    def test_settle_switching_handles_live_row(self):
        """DONE 기록이 실패해 남은 실계좌 처리 중 행을 감시가 DONE 으로 정리."""
        eparams.save_active_strategy(USER, "PULLBACK")
        rid = self._row()
        self.run_engine("PULLBACK")
        self.mgr.mode = "LIVE"
        ev = threading.Event()
        ev.set()
        self.mgr._ready[USER] = ev
        out = ss.Monitor().settle_switching(self.ctl, USER)
        self.assertEqual(out, [rid])
        self.assertEqual(self.rows("SWITCH")[0]["state"], "DONE")

    def test_record_done_failure_path_leaves_row_for_settle(self):
        with mock.patch.object(ss, "update_row", side_effect=sqlite3.OperationalError("locked")):
            ok = ss._record_done(self.ctl, USER, 1, "PULLBACK", note=None)
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
