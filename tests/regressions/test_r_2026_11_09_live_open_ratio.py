"""1109 눌림목 실계좌 열기 — 작업 C(엔진 쪽): 투자 비율(%) 선택 키의 검증·읽기·변환·「비율 없음」 거절.

저장 API 쪽은 tests/v2/test_live_open_ratio_save.py. 여기서는 engine/pullback_params 와 기동 변환을 본다.
"""
from __future__ import annotations

import ast
import json
import os
import tempfile
import unittest
from unittest import mock

import config  # noqa: F401  (st.secrets 는 작업 폴더 기준이라 chdir 전에 읽는다)
from engine import engine_manager, pullback_apply as pa, pullback_params as pbp
from tests.regressions import baseline_commits as bc
from tests.regressions.test_r_2026_10_28_p3_t5_pullback_engine import CFG, USER


def live_cfg(**over):
    d = dict(CFG)
    d["invest_ratio_pct_live"] = 10.0
    d.update(over)
    return d


class InTmp(unittest.TestCase):
    def setUp(self):
        self._cwd = os.getcwd()
        self._d = tempfile.TemporaryDirectory()
        os.chdir(self._d.name)
        self.addCleanup(self._d.cleanup)
        self.addCleanup(os.chdir, self._cwd)


class TestValidate(unittest.TestCase):
    def test_ratio_keys_are_optional_and_old_files_still_validate(self):
        v = pbp.validate(dict(CFG))
        self.assertNotIn("invest_ratio_pct_live", v)
        self.assertNotIn("invest_ratio_pct_test", v)
        self.assertEqual(len(pbp.PULLBACK_KEYS), 24)

    def test_ratio_valid_values_roundtrip_in_order(self):
        v = pbp.validate(live_cfg(invest_ratio_pct_test=0.1))
        self.assertEqual(v["invest_ratio_pct_live"], 10.0)
        self.assertEqual(v["invest_ratio_pct_test"], 0.1)
        self.assertEqual(list(v)[-2:], ["invest_ratio_pct_live", "invest_ratio_pct_test"])
        self.assertEqual(pbp.validate(live_cfg(invest_ratio_pct_live=100))["invest_ratio_pct_live"], 100.0)

    def test_ratio_none_is_absent(self):
        self.assertNotIn("invest_ratio_pct_live", pbp.validate(live_cfg(invest_ratio_pct_live=None)))

    def test_ratio_out_of_range_rejected(self):
        for bad in (0, 0.05, 100.1, -1, "abc", float("nan"), float("inf"), 5.25, True, [1]):
            with self.subTest(bad=bad):
                with self.assertRaises(pbp.PullbackParamsError) as cm:
                    pbp.validate(live_cfg(invest_ratio_pct_live=bad))
                self.assertEqual(cm.exception.field, "invest_ratio_pct_live")

    def test_ratio_rules_match_v2_schema(self):
        from v2 import params_schema as ps
        self.assertEqual(pbp.RATIO_KEYS, ps.RATIO_KEYS)
        for v in (None, 0, 0.05, 0.1, 5.25, 5.5, 99.9, 100, 100.1, -1, "x", True, float("nan")):
            def engine_side():
                try:
                    return pbp.valid_ratio(v)
                except ValueError:
                    return "bad"

            def v2_side():
                try:
                    return ps.valid_ratio(v)
                except ValueError:
                    return "bad"
            self.assertEqual(engine_side(), v2_side(), v)

    def test_unknown_extra_key_still_rejected(self):
        with self.assertRaises(pbp.PullbackParamsError):
            pbp.validate(live_cfg(invest_ratio_pct_other=1))

    def test_diff_records_ratio_change_as_hot(self):
        prev = pbp.validate(live_cfg())
        new = pbp.validate(live_cfg(invest_ratio_pct_live=20.0))
        ch = pa.diff(prev, new)
        self.assertEqual(ch, {"invest_ratio_pct_live": [10.0, 20.0]})
        self.assertEqual(pa.classify(ch, prev), "hot")

    def test_ops_keys_merge_preserves_ratio_keys(self):
        cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as d:
            os.chdir(d)
            try:
                with open(pbp.applied_path(USER), "w", encoding="utf-8") as f:
                    json.dump(pbp.validate(live_cfg()), f)
                res = pbp.apply_ops_keys(USER, {"enable_trading_hours": True, "trading_start_time": "09:00",
                                                "trading_end_time": "02:00", "allow_sell_during_off_hours": True})
                self.assertEqual(res["params"]["invest_ratio_pct_live"], 10.0)
            finally:
                os.chdir(cwd)


class TestInvestRatioFor(InTmp):
    def test_reads_mode_key_from_applied_then_saved(self):
        with open(pbp.saved_path(USER), "w", encoding="utf-8") as f:
            json.dump(live_cfg(invest_ratio_pct_live=5.0, invest_ratio_pct_test=7.0), f)
        self.assertEqual(pbp.invest_ratio_for(USER, "LIVE"), 5.0)          # 적용본이 없으면 저장본
        self.assertEqual(pbp.invest_ratio_for(USER, "TEST"), 7.0)
        with open(pbp.applied_path(USER), "w", encoding="utf-8") as f:
            json.dump(live_cfg(invest_ratio_pct_live=9.0), f)
        self.assertEqual(pbp.invest_ratio_for(USER, "LIVE"), 9.0)          # 적용본 우선
        self.assertIsNone(pbp.invest_ratio_for(USER, "TEST"))              # 모의에 넣은 값이 실계좌에 새지 않고 그 반대도 아님

    def test_none_when_absent_or_broken(self):
        self.assertIsNone(pbp.invest_ratio_for(USER, "LIVE"))
        with open(pbp.applied_path(USER), "w", encoding="utf-8") as f:
            f.write("{broken")
        self.assertIsNone(pbp.invest_ratio_for(USER, "LIVE"))

    def test_ratio_reaches_engine_through_real_strategy_constructor_unaffected(self):
        """비율은 전략 cfg 에 싣지 않는다(적용 때 cfg 가 통째로 교체되므로) — 실제 생성자의 cfg 에 비율 키가 없다."""
        from core.strategy_pullback import IncrementalPullbackStrategy
        s = IncrementalPullbackStrategy(USER, CFG["ticker"], pbp.validate(live_cfg()), 3)
        self.assertFalse([k for k in s.cfg if "ratio" in k.lower() and "invest" in k.lower()])


class TestSwitchCheckAndLiveParams(InTmp):
    def test_check_saved_for_switch_live_needs_ratio(self):
        with open(pbp.saved_path(USER), "w", encoding="utf-8") as f:
            json.dump(CFG, f)
        self.assertEqual(len(pbp.check_saved_for_switch(USER)), 64)                # 기존 호출 그대로
        self.assertEqual(len(pbp.check_saved_for_switch(USER, "TEST")), 64)
        with self.assertRaises(pbp.PullbackParamsError) as cm:
            pbp.check_saved_for_switch(USER, "LIVE")
        self.assertEqual(cm.exception.field, "invest_ratio_pct_live")
        with open(pbp.saved_path(USER), "w", encoding="utf-8") as f:
            json.dump(live_cfg(), f)
        self.assertEqual(len(pbp.check_saved_for_switch(USER, "LIVE")), 64)

    def test_to_live_params_live_requires_ratio_and_ignores_capital(self):
        d = pbp.validate(dict(CFG))
        with self.assertRaises(pbp.PullbackParamsError) as cm:
            pbp.to_live_params(d, 1_000_000, mode="LIVE")
        self.assertEqual(cm.exception.field, "invest_ratio_pct_live")
        d = pbp.validate(live_cfg())
        for capital in (None, 0, -1, 0.0):
            p = pbp.to_live_params(d, capital, mode="LIVE")                          # 운용자산 칸을 보지 않는다(D12)
            self.assertEqual(p.cash, config.MIN_CASH)
        with self.assertRaises(pbp.PullbackParamsError):
            pbp.to_live_params(d, None)                                              # 모드 없이는 지금 규칙(운용자산 필요)

    def test_to_live_params_default_mode_unchanged(self):
        p = pbp.to_live_params(pbp.validate(dict(CFG)), 3_000_000)
        self.assertEqual(p.cash, 3_000_000)


class TestBootParams(InTmp):
    def write_applied(self, d):
        with open(pbp.applied_path(USER), "w", encoding="utf-8") as f:
            json.dump(d, f)

    def test_live_boot_refused_without_ratio(self):
        self.write_applied(CFG)
        with mock.patch.object(pbp, "_notify_critical") as crit:
            params, cfg = engine_manager._pullback_boot_params(USER, "LIVE")
        self.assertEqual((params, cfg), (None, None))
        self.assertEqual(crit.call_count, 1)
        self.assertIn("실계좌 투자 비율이 정해지지 않아 새 전략을 시작하지 않았습니다", crit.call_args.args[0])

    def test_live_boot_with_ratio_ok_even_with_zero_krw_while_holding(self):
        self.write_applied(live_cfg())
        with mock.patch("services.db.get_initial_krw", return_value=0), \
                mock.patch.object(engine_manager, "_pullback_holding_hint", return_value=True):
            params, cfg = engine_manager._pullback_boot_params(USER, "LIVE")
        self.assertIsNotNone(params)
        self.assertEqual(params.cash, config.MIN_CASH)

    def test_live_boot_does_not_read_virtual_krw(self):
        self.write_applied(live_cfg())
        with mock.patch("services.db.get_initial_krw", side_effect=AssertionError("실계좌는 운용자산을 읽지 않는다")):
            params, _ = engine_manager._pullback_boot_params(USER, "LIVE")
        self.assertIsNotNone(params)

    def test_test_mode_boot_ok_without_ratio(self):
        self.write_applied(CFG)
        with mock.patch("services.db.get_initial_krw", return_value=3_000_000):
            params, _ = engine_manager._pullback_boot_params(USER, "TEST")
        self.assertIsNotNone(params)
        self.assertEqual(params.cash, 3_000_000)

    def test_default_mode_argument_is_test(self):
        self.write_applied(CFG)
        with mock.patch("services.db.get_initial_krw", return_value=3_000_000):
            params, _ = engine_manager._pullback_boot_params(USER)
        self.assertIsNotNone(params)


class TestOldCodeRevertSafety(unittest.TestCase):
    """되돌리기: 기준 커밋(옛 코드)의 validate 는 비율 키가 든 파일을 거부한다 → 되돌리기 전에 두 키를 지워야 한다(문서 절차)."""

    def test_old_loader_rejects_ratio_keys_until_stripped(self):
        src = bc.git_show("engine/pullback_params.py", "158c5fc")
        if src is None:
            self.skipTest("기준 커밋 158c5fc 를 읽지 못함")
        ns: dict = {"__name__": "pbp_old"}
        exec(compile(ast.parse(src), "pbp_old.py", "exec"), ns)
        validate_old = ns["validate"]
        old_err = ns["PullbackParamsError"]
        with_ratio = live_cfg(invest_ratio_pct_test=5.0)
        with self.assertRaises(old_err):
            validate_old(with_ratio)
        stripped = {k: v for k, v in with_ratio.items() if k not in pbp.RATIO_KEYS}
        self.assertIsInstance(validate_old(stripped), dict)


if __name__ == "__main__":
    unittest.main()
