"""1109 눌림목 실계좌 열기 — 작업 C(배분 기준)·D(지갑 읽기 실패는 청산이 아니다)·E(불확실 주문은 재주문 안 함).

엔진: T5·T6 시험의 EngineCase·T6Case(임시 DB)·LiveFakeTrader 를 쓴다. 업비트·텔레그램에 닿지 않는다(가짜 trader·알림 대역).
실제 UpbitTrader 시험은 pyupbit.Upbit 와 주문 호출을 대역으로 바꾼다.
"""
from __future__ import annotations

import json
import time as _time
import unittest
from datetime import timedelta
from types import SimpleNamespace
from unittest import mock

from config import MIN_FEE_RATIO
from core import strategy_engine as se
from engine.pullback_params import invest_ratio_for as REAL_INVEST_RATIO_FOR   # EngineCase 가 바꾸기 전 원본
from core.position_state import PositionState
from tests.regressions.test_r_2026_10_28_p3_t5_pullback_engine import (
    CALM, DIP, TICKER, USER, bar, cfg,
)
from tests.regressions.test_r_2026_10_28_p3_t6_split_position import (
    B1000, B950, C1000, C950, P990, LiveFakeTrader, T6Case, need_store,
)


class LiveWalletTrader(LiveFakeTrader):
    """실계좌 가짜: 지갑·원화 조회 성공/실패/지연을 시험이 정한다."""

    def __init__(self, **k):
        super().__init__(**k)
        self.wallet_fail = False          # True 면 coin_balance_checked 실패 + _coin_balance 는 0.0(실제 trader 처럼)
        self.legacy_fail = False          # True 면 _coin_balance 만 0.0 (checked 는 성공)
        self.fail_script = None           # [True, False, ...] 호출마다 소비(앞이 True 면 그 호출 실패)
        self.checked_reads = 0
        self.legacy_reads = 0
        self.krw_fail = False
        self.krw_delay = 0.0
        self.buy_mode = "ok"              # ok | uncertain
        self.upbit = SimpleNamespace(get_balances=self._balances)

    def coin_balance_checked(self, ticker, timeout=8.0):
        self.checked_reads += 1
        failing = self.wallet_fail
        if self.fail_script:
            failing = self.fail_script.pop(0)
        return (0.0, False) if failing else (float(self.coin), True)

    def _coin_balance(self, ticker):
        self.legacy_reads += 1
        return 0.0 if (self.wallet_fail or self.legacy_fail) else self.coin

    def krw_balance_checked(self):
        if self.krw_delay:
            _time.sleep(self.krw_delay)
        if self.krw_fail:
            return 0.0, False
        return float(self.avail), True

    def buy_market(self, price, ticker, ts=None, meta=None, krw_amount=None, strict_amount=False):
        if self.buy_mode == "uncertain":
            self.buy_calls.append({"price": price, "ticker": ticker, "ts": ts, "meta": dict(meta or {}),
                                   "krw_amount": krw_amount, "strict_amount": strict_amount})
            return {"uncertain": True, "time": ts, "side": "BUY", "qty": 0.0, "price": float(price),
                    "uuid": None, "used_krw": krw_amount, "status": 503, "reason": "network_exception"}
        return super().buy_market(price, ticker, ts=ts, meta=meta, krw_amount=krw_amount, strict_amount=strict_amount)


class LiveCase(T6Case):
    def live(self, values=None, **over):
        tr = LiveWalletTrader()
        self.make(values=values or P990, trader=tr, **over)
        return tr

    def criticals(self):
        return [c for c in self.notify.call_args_list if c.args[0] == "CRITICAL"]

    def codes(self, tr):
        return [r["code"] for r in tr.rejects]

    def fill(self, tr, uuid="L1", qty=100.0, price=1000.0, i=0, wallet_avg=None):
        tr.coin = (tr.coin or 0.0) + qty
        tr.wallet_avg = wallet_avg if wallet_avg is not None else price
        self.eng._on_limit_fill(uuid=uuid, executed_price=price, executed_qty=qty,
                                executed_ts=self.kst(i) + timedelta(seconds=2), state="FILLED")

    def hold(self, tr, qty=100.0):
        """1회차 매수 → 체결 반영 → 보유 100개 @1000."""
        self.feed(bar(0, **B1000))
        self.fill(tr, qty=qty)
        self.assertTrue(self.eng.position.has_position)


# ================================================================ C: 배분 기준
class TestSizing(LiveCase):
    def test_live_base_is_avail_times_ratio_over_fee(self):
        self.ratios["LIVE"] = 10.0
        tr = self.live()
        tr.avail = 1_000_000
        self.feed(bar(0, **B1000))
        call = tr.buy_calls[0]
        self.assertEqual(call["meta"]["sizing_base"], 99950)         # floor(1,000,000 × 10% ÷ 1.0005)
        self.assertEqual(call["krw_amount"], 19990)                  # 99,950 ÷ 5회
        self.assertTrue(call["strict_amount"])

    def test_ratio_100_single_split_places_order(self):
        self.ratios["LIVE"] = 100.0
        tr = self.live(maxSplits=1)
        tr.avail = 1_000_000
        self.feed(bar(0, **B1000))
        self.assertEqual(len(tr.buy_calls), 1)                        # 수수료 몫 때문에 영원히 「잔고 부족」이 되지 않는다
        self.assertEqual(tr.buy_calls[0]["krw_amount"], 999_500)
        self.assertLessEqual(tr.buy_calls[0]["krw_amount"] * (1 + MIN_FEE_RATIO), 1_000_000)
        self.assertNotIn("split_krw_short", self.codes(tr))

    def test_below_5000_skips_with_audit(self):
        self.ratios["LIVE"] = 1.0
        tr = self.live()
        tr.avail = 100_000                                            # 100,000 × 1% = 1,000 → 1회 199원
        self.feed(bar(0, **B1000))
        self.assertEqual(tr.buy_calls, [])
        self.assertEqual(self.codes(tr), ["split_below_min"])

    def test_balance_query_fail_skips_no_order(self):
        tr = self.live()
        tr.krw_fail = True
        self.feed(bar(0, **B1000))
        self.assertEqual(tr.buy_calls, [])
        self.assertEqual(self.codes(tr), ["split_krw_unknown"])

    def test_balance_timeout_skips_round(self):
        tr = self.live()
        tr.krw_delay = 1.5
        with mock.patch.object(se, "PULLBACK_QUERY_TIMEOUT_S", 0.2):
            t0 = _time.monotonic()
            self.feed(bar(0, **B1000))
            self.assertLess(_time.monotonic() - t0, 1.0)             # 상한 안에서 돌아온다(락 안에서 끝없이 기다리지 않음)
        self.assertEqual(tr.buy_calls, [])
        self.assertEqual(self.codes(tr), ["split_krw_timeout"])

    def test_zero_avail_skips(self):
        tr = self.live()
        tr.avail = 0
        self.feed(bar(0, **B1000))
        self.assertEqual(tr.buy_calls, [])
        self.assertEqual(self.codes(tr), ["split_no_capital"])

    def test_no_ratio_live_skips_with_audit_code(self):
        self.ratios["LIVE"] = None
        tr = self.live()
        self.feed(bar(0, **B1000))
        self.assertEqual(tr.buy_calls, [])
        self.assertEqual(self.codes(tr), ["split_no_ratio"])
        self.assertEqual(tr.checked_reads, 1)                         # 비율이 없으면 잔고를 묻기 전에 멈춤은 아님(지갑 대조 1회)

    def test_base_fixed_through_trade_and_ratio_change_ignored(self):
        self.ratios["LIVE"] = 10.0
        tr = self.live()
        tr.avail = 1_000_000
        self.hold(tr)
        self.ratios["LIVE"] = 50.0                                    # 보유 중 비율 변경 → 다음 거래부터
        tr.avail = 5_000_000
        self.feed(bar(1, **C1000), bar(2, **B950))
        self.assertEqual(len(tr.buy_calls), 2)
        self.assertEqual(tr.buy_calls[1]["meta"]["sizing_base"], 99950)
        self.assertEqual(tr.buy_calls[1]["krw_amount"], 19990)

    def test_live_no_compounding_even_if_cfg_true(self):
        self.ratios["LIVE"] = 10.0
        tr = self.live(compounding=True)
        tr.avail = 1_000_000
        self.eng._pullback_realized_pnl = 500_000.0                    # 이익이 났어도
        self.feed(bar(0, **B1000))
        self.assertEqual(tr.buy_calls[0]["meta"]["sizing_base"], 99950)

    def test_test_mode_base_uses_virtual_krw_times_ratio(self):
        self.ratios["TEST"] = 50.0
        self.make()                                                   # 모의(FakeTrader), 운용자산 3,000,000
        self.feed(bar(0, **DIP))
        self.assertEqual(self.trader.buy_calls[0]["krw_amount"], 300_000)     # 3,000,000 × 50% ÷ 5
        self.assertEqual(self.trader.buy_calls[0]["meta"]["sizing_base"], 1_500_000)

    def test_test_mode_no_ratio_is_100pct(self):
        self.ratios["TEST"] = None
        self.make()
        self.feed(bar(0, **DIP))
        self.assertEqual(self.trader.buy_calls[0]["krw_amount"], 600_000)

    def test_force_buy_uses_split_round_path(self):
        self.ratios["LIVE"] = 10.0
        tr = self.live()
        tr.avail = 1_000_000
        self.feed(bar(0, **C1000))
        r = self.eng._pullback_force_buy()
        self.assertEqual((r["status"], r["code"]), ("done", "ok"), r)
        self.assertEqual(tr.buy_calls[0]["meta"]["split_round"], 1)
        self.assertEqual(tr.buy_calls[0]["krw_amount"], 19990)
        self.assertEqual(self.strat.entry_count, 1)

    def test_live_restart_restores_saved_base(self):
        self.ratios["LIVE"] = 10.0
        tr = self.live()
        tr.avail = 1_000_000
        self.hold(tr)
        self.assertEqual(need_store(self).load(USER, "LIVE")["sizing_base_krw"], 99950)
        tr2 = self.live()
        tr2.coin, tr2.wallet_avg = 100.0, 1000.0
        self.eng.pullback_restore_on_boot(None, None)
        self.assertEqual(self.eng._pullback_sizing_base, 99950)
        self.assertFalse(self.eng._pullback_desync)

    def test_live_restart_without_base_halts_adds(self):
        self.ratios["LIVE"] = 10.0
        tr = self.live()
        tr.avail = 1_000_000
        self.hold(tr)
        self.eng._pullback_sizing_base = None                          # 저장된 배분 기준이 없는 상태
        self.eng._pullback_persist()
        tr2 = self.live()
        tr2.coin, tr2.wallet_avg = 100.0, 1000.0
        self.notify.reset_mock()
        self.eng.pullback_restore_on_boot(None, None)
        self.assertTrue(self.eng._pullback_desync)                    # 추가 매수 멈춤
        self.assertEqual(len(self.criticals()), 1)                    # 알림 1회
        self.assertIsNone(self.eng._pullback_sizing_base)             # 「지금 잔액으로 다시 계산」하지 않음
        self.assertTrue(self.eng.position.has_position)               # 매도 판정은 계속

    def test_halted_live_round_without_base_is_skipped_not_recomputed(self):
        self.ratios["LIVE"] = 10.0
        tr = self.live()
        tr.avail = 1_000_000
        self.hold(tr)
        self.eng._pullback_sizing_base = None
        tr.avail = 9_000_000
        self.feed(bar(1, **C1000), bar(2, **B950))
        self.assertEqual(len(tr.buy_calls), 1)                        # 2회차는 나가지 않음

    def test_old_ratio_none_on_test_still_works_without_file(self):
        """invest_ratio_for 실제 함수: 파일이 없으면 None(모의 100%)."""
        import os
        import tempfile
        cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as d:
            os.chdir(d)
            try:
                self.assertIsNone(REAL_INVEST_RATIO_FOR("nobody", "TEST"))
                self.assertIsNone(REAL_INVEST_RATIO_FOR("nobody", "LIVE"))
            finally:
                os.chdir(cwd)


# ================================================================ D: 지갑 읽기
class TestTraderCoinBalanceChecked(unittest.TestCase):
    def setUp(self):
        from core.trader import UpbitTrader
        ps = [mock.patch("core.trader.pyupbit.Upbit"), mock.patch("core.trader.insert_order"),
              mock.patch("core.trader.insert_log"),
              mock.patch.object(UpbitTrader, "_get_settings_history_id", return_value=None)]
        for p in ps:
            p.start()
            self.addCleanup(p.stop)
        self.t = UpbitTrader(USER, risk_pct=1.0, test_mode=False, strategy_type="PULLBACK", params_file=None)

    def test_exception_none_nonlist_and_empty_list_are_failure(self):
        for bad in (RuntimeError("down"), None, {"error": "x"}, [], "oops"):
            with self.subTest(bad=bad):
                self.t.__dict__.pop("_coin_query_guard", None)
                if isinstance(bad, Exception):
                    self.t.upbit.get_balances.side_effect = bad
                else:
                    self.t.upbit.get_balances.side_effect = None
                    self.t.upbit.get_balances.return_value = bad
                self.assertEqual(self.t.coin_balance_checked("KRW-TEST"), (0.0, False))

    def test_coin_absent_with_krw_listed_is_true_zero(self):
        self.t.upbit.get_balances.return_value = [{"currency": "KRW", "balance": "1000", "locked": "0"}]
        self.assertEqual(self.t.coin_balance_checked("KRW-TEST"), (0.0, True))

    def test_returns_free_plus_locked(self):
        self.t.upbit.get_balances.return_value = [
            {"currency": "KRW", "balance": "1000", "locked": "0"},
            {"currency": "TEST", "balance": "1.5", "locked": "0.25"}]
        self.assertEqual(self.t.coin_balance_checked("KRW-TEST"), (1.75, True))

    def test_timeout_returns_failure_quickly_and_does_not_pile_up_threads(self):
        calls = []

        def slow():
            calls.append(1)
            _time.sleep(1.0)
            return [{"currency": "KRW", "balance": "1", "locked": "0"}]
        self.t.upbit.get_balances.side_effect = slow
        t0 = _time.monotonic()
        self.assertEqual(self.t.coin_balance_checked("KRW-TEST", timeout=0.1), (0.0, False))
        self.assertLess(_time.monotonic() - t0, 0.6)
        self.assertEqual(self.t.coin_balance_checked("KRW-TEST", timeout=0.1), (0.0, False))   # 앞 조회가 아직 진행 중
        self.assertEqual(len(calls), 1)                                # 새 스레드를 만들지 않았다

    def test_test_mode_reads_db_and_failure_is_false(self):
        from core.trader import UpbitTrader
        with mock.patch("core.trader.pyupbit.Upbit"), mock.patch("core.trader.get_account", return_value=1.0):
            t = UpbitTrader(USER, risk_pct=1.0, test_mode=True, strategy_type="PULLBACK", params_file=None)
        with mock.patch("core.trader.get_coin_balance", return_value=2.5):
            self.assertEqual(t.coin_balance_checked("KRW-TEST"), (2.5, True))
        with mock.patch("core.trader.get_coin_balance", side_effect=RuntimeError("db")):
            self.assertEqual(t.coin_balance_checked("KRW-TEST"), (0.0, False))

    def test_legacy_coin_balance_unchanged_returns_zero_on_failure(self):
        """EMA 공용 _coin_balance 는 그대로(읽기 실패 → 0.0). 눌림목만 coin_balance_checked 로 구분한다."""
        self.t.upbit.get_balances.side_effect = RuntimeError("down")
        self.assertEqual(self.t._coin_balance("KRW-TEST"), 0.0)


class TestWalletRead(LiveCase):
    def setUp(self):
        super().setUp()
        self.ratios["LIVE"] = 10.0

    def holding(self):
        tr = self.live()
        tr.avail = 1_000_000
        self.hold(tr)
        self.feed(bar(1, **C1000))                                     # 정상 봉 1개 지나감
        return tr

    def test_wallet_read_failure_is_not_exit(self):
        tr = self.holding()
        tr.wallet_fail = True
        with mock.patch.object(self.eng, "_pullback_on_exit", wraps=self.eng._pullback_on_exit) as on_exit, \
                mock.patch.object(self.eng, "_record_external_sell") as ext, \
                mock.patch.object(self.eng.position, "close_position", wraps=self.eng.position.close_position) as cp:
            self.feed(bar(2, **C1000), bar(3, **C1000))
        on_exit.assert_not_called()
        ext.assert_not_called()
        cp.assert_not_called()
        self.assertTrue(self.eng.position.has_position)
        self.assertAlmostEqual(self.eng._pb_qty, 100.0)
        self.assertEqual(self.strat.entry_count, 1)                    # 분할 상태 그대로
        self.assertAlmostEqual(self.row("LIVE")["qty"], 100.0)        # 저장 행도 그대로

    def test_wallet_read_recovers_next_bar_and_resumes_normal_check(self):
        tr = self.holding()
        tr.wallet_fail = True
        self.feed(bar(2, **C1000))
        tr.wallet_fail = False
        tr.coin = 0.0                                                  # 이번엔 진짜 0(앱 매도)
        with mock.patch.object(self.eng, "_pullback_on_exit", wraps=self.eng._pullback_on_exit) as on_exit:
            self.feed(bar(3, **C1000))
        self.assertEqual(on_exit.call_count, 1)                        # 진짜 0 은 지금처럼 청산 처리
        self.assertEqual(on_exit.call_args.kwargs["reason"], "wallet_zero")

    def test_real_zero_wallet_still_liquidates_state(self):
        tr = self.holding()
        tr.coin = 0.0
        self.feed(bar(2, **C1000))
        self.assertEqual(self.eng._pb_qty, 0.0)
        self.assertFalse(self.eng.position.has_position)

    def test_wallet_read_once_per_bar_and_reused_by_bar_branches(self):
        tr = self.holding()
        before_checked, before_legacy = tr.checked_reads, tr.legacy_reads
        self.feed(bar(2, **C1000))
        self.assertEqual(tr.checked_reads - before_checked, 1)         # 봉당 1회
        self.assertEqual(tr.legacy_reads - before_legacy, 0)           # 동기화가 _coin_balance 를 다시 부르지 않음

    def test_sync_from_wallet_second_read_failure_cannot_flip_has_position(self):
        tr = self.holding()
        tr.legacy_fail = True                                          # 옛 읽기(_coin_balance)만 실패(0.0)
        self.feed(bar(2, **C1000))
        self.assertTrue(self.eng.position.has_position)
        self.assertEqual(self.strat.entry_count, 1)

    def test_sync_from_wallet_default_path_unchanged_for_ema(self):
        tr = LiveWalletTrader()
        tr.coin = 3.0
        pos = PositionState(trader=tr, ticker=TICKER)
        pos.sync_from_wallet()
        self.assertEqual(tr.legacy_reads, 1)                           # wallet_qty 를 안 주면 지금처럼 _coin_balance
        self.assertTrue(pos.has_position)
        pos.sync_from_wallet(wallet_qty=0.0)
        self.assertFalse(pos.has_position)
        self.assertEqual(tr.legacy_reads, 1)                           # 값을 주면 다시 읽지 않는다

    def test_third_consecutive_failed_bar_alerts_once_critical_with_sell_hint(self):
        tr = self.holding()
        tr.wallet_fail = True
        self.notify.reset_mock()
        self.feed(bar(2, **C1000), bar(3, **C1000))
        self.assertEqual(self.criticals(), [])                         # 2봉까지는 알림 없음
        self.feed(bar(4, **C1000))
        crit = self.criticals()
        self.assertEqual(len(crit), 1)
        text = crit[0].args[1] + crit[0].args[2]
        self.assertIn("메모리 수량으로 계속", text)
        self.assertIn("업비트 앱에서 직접 매도", text)
        self.feed(bar(5, **C1000))
        self.assertEqual(len(self.criticals()), 1)                     # 같은 실패 연속은 1회만
        tr.wallet_fail = False
        self.feed(bar(6, **C1000))
        self.assertEqual(self.eng._pb_wallet_fail_bars, 0)

    def test_wallet_read_failure_sell_decision_continues_from_memory_qty(self):
        tr = self.holding()
        tr.wallet_fail = True
        up = dict(o=1000, h=1100, l=1000, c=1100)                      # 익절(tp 5%) 조건
        self.feed(bar(2, **up))
        self.assertEqual(len(tr.sell_calls), 1)                        # 읽기 실패 봉에서도 매도 요청이 나간다
        self.assertAlmostEqual(tr.sell_calls[0]["qty"], 100.0)

    def test_force_buy_after_force_sell_in_same_minute_reads_wallet_fresh(self):
        tr = self.holding()
        tr.coin = 0.0                                                  # 강제 매도(엔진 밖 체결)로 지갑 0
        before = tr.checked_reads
        r = self.eng._pullback_force_buy()
        self.assertGreater(tr.checked_reads, before)                   # 지난 봉 캐시(보유)가 아니라 새로 읽음
        self.assertEqual((r["status"], r["code"]), ("done", "ok"), r)
        self.assertEqual(tr.buy_calls[-1]["meta"]["split_round"], 1)   # 옛 회차(1)가 정리된 뒤 새 1회차

    def test_force_buy_wallet_read_failure_rejects_without_order(self):
        tr = self.holding()
        n = len(tr.buy_calls)
        tr.wallet_fail = True
        r = self.eng._pullback_force_buy()
        self.assertEqual((r["status"], r["code"]), ("rejected", "wallet_unknown"))
        self.assertEqual(len(tr.buy_calls), n)

    def test_fill_callback_invalidates_bar_wallet_cache(self):
        tr = self.live()
        tr.avail = 1_000_000
        self.feed(bar(0, **B1000))
        self.assertIsNotNone(self.eng._pb_wallet_cache)
        self.fill(tr)
        self.assertIsNone(self.eng._pb_wallet_cache)

    def test_ema_engine_does_not_use_checked_read(self):
        """EMA 엔진은 _pullback_* 지갑 도우미를 거치지 않는다(경로 무변경은 EMA 호출 흔적 시험이 따로 본다)."""
        tr = LiveWalletTrader()
        pos = PositionState(trader=tr, ticker=TICKER)
        pos.sync_from_wallet()
        self.assertEqual(tr.checked_reads, 0)


# ================================================================ D: 부팅 때 지갑 실패
class TestBootWallet(LiveCase):
    def setUp(self):
        super().setUp()
        self.ratios["LIVE"] = 10.0
        patcher = mock.patch.object(se, "PULLBACK_BOOT_WALLET_RETRY_SEC", 0.0)
        patcher.start()
        self.addCleanup(patcher.stop)

    def saved_hold(self):
        tr = self.live()
        tr.avail = 1_000_000
        self.hold(tr)
        self.assertEqual(self.row("LIVE")["entry_count"], 1)
        return tr

    def test_boot_wallet_failure_starts_from_saved_qty_desync_and_critical(self):
        self.saved_hold()
        tr2 = self.live()
        tr2.wallet_fail = True
        self.notify.reset_mock()
        self.eng.pullback_restore_on_boot(None, None)
        self.assertEqual(tr2.checked_reads, 1 + se.PULLBACK_BOOT_WALLET_RETRIES)      # 첫 시도 + 재시도
        self.assertTrue(self.eng._pullback_desync)                                     # 추가 매수 멈춤
        self.assertTrue(self.eng.position.has_position)
        self.assertAlmostEqual(self.eng.position.qty, 100.0)
        self.assertAlmostEqual(self.eng.position.avg_price, 1000.0)
        self.assertEqual(len(self.criticals()), 1)
        self.assertAlmostEqual(self.row("LIVE")["qty"], 100.0)                         # 저장 행을 지우지 않음
        self.assertEqual(self.row("LIVE")["entry_count"], 1)

    def test_boot_wallet_retry_succeeds_on_second_try_restores_normally(self):
        self.saved_hold()
        tr2 = self.live()
        tr2.coin, tr2.wallet_avg = 100.0, 1000.0
        tr2.fail_script = [True, False]
        self.notify.reset_mock()
        self.eng.pullback_restore_on_boot(None, None)
        self.assertEqual(tr2.checked_reads, 2)
        self.assertFalse(self.eng._pullback_desync)
        self.assertEqual(self.criticals(), [])
        self.assertAlmostEqual(self.eng.position.qty, 100.0)

    def test_boot_wallet_read_failure_does_not_reset_row(self):
        self.saved_hold()
        tr2 = self.live()
        tr2.wallet_fail = True
        self.eng.pullback_restore_on_boot(None, None)
        self.assertEqual(self.row("LIVE")["entry_count"], 1)

    def test_boot_wallet_failure_without_saved_avg_refuses_to_start(self):
        self.saved_hold()
        store = need_store(self)
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        conn.execute("UPDATE pullback_state SET avg_price=NULL, cost_krw=0 WHERE user_id=?", (USER,))
        conn.commit()
        conn.close()
        tr2 = self.live()
        tr2.wallet_fail = True
        self.notify.reset_mock()
        with self.assertRaises(se.PullbackBootWalletUnknown):
            self.eng.pullback_restore_on_boot(None, None)
        self.assertEqual(len(self.criticals()), 1)
        self.assertEqual(store.load(USER, "LIVE")["entry_count"], 1)                   # 행 그대로

    def test_live_loop_marks_not_ready_and_stops_when_wallet_unknown(self):
        import threading
        import engine.live_loop as live_loop
        eng = SimpleNamespace(pullback_restore_on_boot=mock.Mock(side_effect=se.PullbackBootWalletUnknown("x")),
                              _pullback_block_persist=mock.Mock(), _control_stop_event=threading.Event(),
                              _control_ready_event=SimpleNamespace())
        live_loop._pullback_restore_split_state(eng, USER, None, None)
        self.assertFalse(eng._pullback_restore_ok)
        self.assertTrue(eng._control_stop_event.is_set())
        self.assertEqual(eng.fail_reason, "wallet_unknown")
        self.assertEqual(eng._control_ready_event.fail_reason, "wallet_unknown")

    def test_boot_unknown_start_then_next_bar_reads_wallet_and_aligns(self):
        """부팅 실패로 저장 수량(100)으로 시작했는데 실제 지갑은 60 → 다음 봉의 지갑 대조가 맞춘다(desync 유지). 매도 거절 자체는 흉내 내지 않는다."""
        self.saved_hold()
        tr2 = self.live()
        tr2.wallet_fail = True
        self.eng.pullback_restore_on_boot(None, None)
        tr2.wallet_fail = False
        tr2.coin, tr2.wallet_avg = 60.0, 1000.0
        self.feed(bar(5, **C1000))
        self.assertAlmostEqual(self.eng._pb_qty, 60.0)
        self.assertAlmostEqual(self.eng.position.qty, 60.0)
        self.assertTrue(self.eng._pullback_desync)


# ================================================================ E: 불확실 주문
class TestUncertainClassification(unittest.TestCase):
    def test_classification_table(self):
        from core.trader import _upbit_order_uncertain as u
        mk = lambda **k: dict(dict(ok=False, status=None, body=None, error_name=None, exception=None), **k)  # noqa: E731
        self.assertTrue(u(mk(exception="Timeout", status=None, error_name="network_exception")))
        self.assertTrue(u(mk(status=503, body={"error": {"name": "x"}}, error_name="x")))
        self.assertTrue(u(mk(status=502, body="<html>")))
        self.assertTrue(u(mk(status=201, body="")))                    # 비JSON
        self.assertTrue(u(mk(status=201, body={"market": "KRW-X"})))   # uuid 없음
        self.assertFalse(u(mk(status=400, body={"error": {"name": "insufficient_funds_bid", "message": "m"}},
                              error_name="insufficient_funds_bid")))   # 확정 실패
        self.assertFalse(u(mk(status=429, body={"error": {"name": "too_many_request", "message": "m"}},
                              error_name="too_many_request")))
        self.assertFalse(u(mk(ok=True, status=201, body={"uuid": "u"})))


class TestTraderUncertainBuy(unittest.TestCase):
    def setUp(self):
        from core.trader import UpbitTrader
        ps = [mock.patch("core.trader.pyupbit.Upbit"), mock.patch("core.trader.insert_order"),
              mock.patch("core.trader.insert_log"), mock.patch("core.trader._time.sleep"),
              mock.patch("services.notifier.send", mock.MagicMock(return_value=True)),
              mock.patch.object(UpbitTrader, "_get_settings_history_id", return_value=None),
              mock.patch("engine.reconciler_singleton.get_reconciler", return_value=mock.MagicMock())]
        for p in ps:
            p.start()
            self.addCleanup(p.stop)
        self.t = UpbitTrader(USER, risk_pct=1.0, test_mode=False, strategy_type="PULLBACK", params_file=None)
        self.t.upbit.get_balance.return_value = 10_000_000
        self.unc = {"ok": False, "status": None, "body": None, "error_name": "network_exception",
                    "error_message": "Timeout", "exception": "ReadTimeout: x", "data": None}
        self.rej = {"ok": False, "status": 400, "body": {"error": {"name": "insufficient_funds_bid", "message": "m"}},
                    "error_name": "insufficient_funds_bid", "error_message": "m", "exception": None, "data": None}

    def test_strict_uncertain_response_is_not_retried(self):
        with mock.patch("core.trader._upbit_buy_market", return_value=self.unc) as up:
            r = self.t.buy_market(1000.0, "KRW-TEST", meta={"reason": "PULLBACK"}, krw_amount=600_000,
                                  strict_amount=True)
        self.assertEqual(up.call_count, 1)                              # 재주문 없음
        self.assertTrue(r.get("uncertain"))
        self.assertIsNone(r.get("uuid"))

    def test_strict_5xx_nonjson_and_no_uuid_are_uncertain(self):
        for call in ({"ok": False, "status": 503, "body": {"error": {"name": "x"}}, "error_name": "x",
                      "error_message": "m", "exception": None, "data": None},
                     {"ok": False, "status": 502, "body": "<html>", "error_name": None, "error_message": None,
                      "exception": None, "data": None},
                     {"ok": False, "status": 201, "body": {"market": "KRW-TEST"}, "error_name": None,
                      "error_message": None, "exception": None, "data": None}):
            with self.subTest(status=call["status"]):
                with mock.patch("core.trader._upbit_buy_market", return_value=call) as up:
                    r = self.t.buy_market(1000.0, "KRW-TEST", meta={}, krw_amount=600_000, strict_amount=True)
                self.assertEqual(up.call_count, 1)
                self.assertTrue(r.get("uncertain"))

    def test_strict_certain_rejection_still_returns_empty(self):
        with mock.patch("core.trader._upbit_buy_market", return_value=self.rej):
            r = self.t.buy_market(1000.0, "KRW-TEST", meta={}, krw_amount=600_000, strict_amount=True)
        self.assertEqual(r, {})

    def test_ema_path_retry_unchanged_on_uncertain_response(self):
        """EMA·MACD(strict_amount=False)는 지금처럼 불확실 응답도 재시도한다 — 재시도 경로 무변경."""
        from core.trader import LIVE_BUY_MAX_RETRIES
        with mock.patch("core.trader._upbit_buy_market", return_value=self.unc) as up:
            r = self.t.buy_market(1000.0, "KRW-TEST", meta={})
        self.assertEqual(up.call_count, LIVE_BUY_MAX_RETRIES)
        self.assertEqual(r, {})


class TestUncertainEngine(LiveCase):
    def setUp(self):
        super().setUp()
        self.ratios["LIVE"] = 10.0

    def uncertain_round1(self):
        tr = self.live()
        tr.avail = 1_000_000
        tr.buy_mode = "uncertain"
        self.notify.reset_mock()
        self.feed(bar(0, **B1000))
        return tr

    def test_uncertain_buy_sets_pending_critical_once_and_audit_row(self):
        tr = self.uncertain_round1()
        sp = self.eng._pending_split
        self.assertIsNotNone(sp)
        self.assertIsNone(sp["uuid"])
        self.assertTrue(sp.get("uncertain"))
        self.assertEqual(len(tr.buy_calls), 1)
        self.assertEqual(len(self.criticals()), 1)
        self.assertEqual(self.codes(tr), ["split_order_uncertain"])               # 감사 BUY_REJECTED 1행
        self.assertIn("체결 여부 불명", tr.rejects[0]["note"])
        self.assertIn("3봉 뒤 지갑 기준 맞춤", tr.rejects[0]["note"])
        self.assertEqual(self.strat.entry_count, 1)                               # 회차는 유지(체결됐을 수 있음)
        self.assertTrue(self.eng.position.pending_order)

    def test_no_second_buy_while_ambiguous_pending(self):
        tr = self.uncertain_round1()
        tr.buy_mode = "ok"
        self.feed(bar(1, **B950), bar(2, **B950), bar(3, **B950))                 # 눌림 신호가 계속 와도
        self.assertEqual(len(tr.buy_calls), 1)                                    # 같은 회차를 다시 사지 않는다

    def test_execute_pullback_buy_guard_blocks_when_pending(self):
        tr = self.uncertain_round1()
        n = len(tr.buy_calls)
        self.eng._execute_pullback_buy(bar(9, **B950), {})
        self.assertEqual(len(tr.buy_calls), n)

    def test_first_round_ambiguous_filled_sets_position_not_app_buy(self):
        """3봉 뒤 지갑에 코인이 있으면(체결됨) 업비트 평단으로 포지션을 세운다 — 앱 매수로 오인하지 않는다."""
        tr = self.uncertain_round1()
        tr.coin, tr.wallet_avg = 20.0, 1001.0
        self.feed(bar(1, **C1000), bar(2, **C1000), bar(3, **C1000))
        self.assertIsNotNone(self.eng._pending_split)                             # 3봉까지는 기다림
        self.feed(bar(4, **C1000))
        self.assertIsNone(self.eng._pending_split)
        p = self.eng.position
        self.assertTrue(p.has_position)
        self.assertAlmostEqual(p.qty, 20.0)
        self.assertAlmostEqual(p.avg_price, 1001.0)
        self.assertFalse(p.pending_order)
        self.assertAlmostEqual(self.eng._pb_qty, 20.0)
        self.assertFalse(self.eng._pullback_desync)

    def test_ambiguous_filled_without_avg_goes_desync(self):
        tr = self.uncertain_round1()
        tr.coin, tr.wallet_avg = 20.0, 0.0                                       # 평단을 못 읽음
        self.feed(bar(1, **C1000), bar(2, **C1000), bar(3, **C1000), bar(4, **C1000))
        self.assertIsNone(self.eng._pending_split)
        self.assertTrue(self.eng._pullback_desync)                                # 추가 매수 멈춤(평단 없이 포지션을 세우지 않음)
        self.assertEqual(len(tr.buy_calls), 1)

    def test_expired_pending_without_position_and_wallet_coin_applies_entry(self):
        """Fable 권고 1: has_position 거짓 + 지갑 > 0 이면 업비트 평단으로 포지션을 세운다(직접 대조 호출)."""
        tr = self.uncertain_round1()
        tr.coin, tr.wallet_avg = 20.0, 1001.0
        self.assertFalse(self.eng.position.has_position)               # 한 봉만 지나 아직 포지션이 없다
        self.eng._pb_wallet_cache = None
        self.eng.bar_count += 10                                       # 대기 봉 수를 넘김
        self.eng._pullback_wallet_check(bar(30, **C1000))
        p = self.eng.position
        self.assertTrue(p.has_position)
        self.assertAlmostEqual(p.qty, 20.0)
        self.assertAlmostEqual(p.avg_price, 1001.0)
        self.assertIsNone(self.eng._pending_split)

    def test_ambiguous_not_filled_clears_pending_without_position(self):
        tr = self.uncertain_round1()
        tr.coin = 0.0
        self.feed(bar(1, **CALM), bar(2, **CALM), bar(3, **CALM), bar(4, **CALM))
        self.assertIsNone(self.eng._pending_split)
        self.assertFalse(self.eng.position.pending_order)
        self.assertFalse(self.eng.position.has_position)
        self.assertEqual(len(tr.buy_calls), 1)

    def test_wallet_zero_during_ambiguous_wait_does_not_take_liquidation_branch(self):
        tr = self.uncertain_round1()
        tr.coin = 0.0
        with mock.patch.object(self.eng, "_pullback_on_exit", wraps=self.eng._pullback_on_exit) as on_exit:
            self.feed(bar(1, **CALM), bar(2, **CALM))
        on_exit.assert_not_called()                                               # 대기 중 지갑 0 은 청산으로 안 감

    def test_ema_buy_path_never_returns_uncertain_marker_handling(self):
        """EMA 엔진 _execute_buy 는 결과의 uncertain 키를 해석하지 않는다(눌림목 분기에서만 본다)."""
        import inspect
        src = inspect.getsource(se.StrategyEngine._execute_buy)
        self.assertNotIn("uncertain", src)


if __name__ == "__main__":
    unittest.main()
