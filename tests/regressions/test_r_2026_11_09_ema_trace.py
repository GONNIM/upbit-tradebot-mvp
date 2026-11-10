"""1109 눌림목 실계좌 열기 — EMA·MACD 실매매 경로 불변을 「호출 흔적」으로 확인한다(축소안 F).

공용 함수 3개를 EMA 방식으로 불러, trader·DB·알림·잠자기 호출 흔적이 기준 커밋(158c5fc)에서 뽑은 값(ema_trace_golden.GOLDEN)과
같은지 본다. 그리고 공용 파일 5개의 EMA 경로 구문(AST)이 기준과 같은지(ema_path_compare 규칙) 한 번 더 본다.
"""
from __future__ import annotations

import unittest

import config  # noqa: F401
from tests.regressions import ema_path_compare as epc
from tests.regressions import ema_trace_scenarios as scen
from tests.regressions.ema_trace_golden import BASE_COMMIT, GOLDEN


class TestEmaTrace(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.now = scen.run_all()

    def test_buy_market_ema_path_trace_same_as_base(self):
        self.assertEqual(sorted(self.now["trader"]), sorted(GOLDEN["trader"]))
        for name in GOLDEN["trader"]:
            with self.subTest(case=name):
                self.assertEqual(self.now["trader"][name], GOLDEN["trader"][name])

    def test_ema_buy_retries_are_untouched_for_uncertain_responses(self):
        """불확실 응답(네트워크 예외·5xx·uuid 없음)도 EMA 는 지금처럼 재시도한다 — 눌림목(strict_amount)만 재주문을 멈춘다."""
        t = self.now["trader"]
        self.assertEqual(len(t["network_all_fail"]["buy_calls"]), 3)                   # LIVE_BUY_MAX_RETRIES(3)만큼 재시도
        self.assertEqual(len(t["network_then_success"]["buy_calls"]), 2)
        self.assertEqual(len(t["5xx_then_success"]["buy_calls"]), 2)
        self.assertEqual(len(t["no_uuid_then_success"]["buy_calls"]), 2)

    def test_sync_from_wallet_default_trace_same_as_base(self):
        for name in GOLDEN["sync"]:
            with self.subTest(case=name):
                self.assertEqual(self.now["sync"][name], GOLDEN["sync"][name])

    def test_reconcile_position_with_wallet_default_trace_same_as_base(self):
        for name in GOLDEN["reconcile"]:
            with self.subTest(case=name):
                self.assertEqual(self.now["reconcile"][name], GOLDEN["reconcile"][name])

    def test_ast_rule_holds_for_the_five_shared_files(self):
        for rel in sorted(epc.LIVE_OPEN_FILES):
            with self.subTest(rel=rel):
                base = epc.git_show(rel, BASE_COMMIT)
                if base is None:
                    self.skipTest("기준 커밋 158c5fc 를 읽지 못함")
                now = (epc.ROOT / rel).read_text(encoding="utf-8")
                self.assertEqual(epc.ema_path_diff(rel, base, now), [])

    def test_strip_if_keeps_else_branch_and_ignores_mixed_tests(self):
        """PULLBACK if 의 body 만 지운다. else(EMA 길)와 혼합 조건의 변경은 위반으로 잡힌다(verifier 지적 3)."""
        rel = "engine/live_loop.py"
        fn = "def run_live_loop(t, x):\n"
        base = fn + "    if t == 'PULLBACK':\n        a = 1\n    else:\n        a = 2\n    return a\n"
        body_changed = fn + "    if t == 'PULLBACK':\n        a = 9\n    else:\n        a = 2\n    return a\n"
        else_changed = fn + "    if t == 'PULLBACK':\n        a = 1\n    else:\n        a = 3\n    return a\n"
        self.assertEqual(epc.ema_path_diff(rel, base, body_changed), [])                  # PULLBACK 쪽 변경은 허용
        self.assertTrue(epc.ema_path_diff(rel, base, else_changed))                        # EMA 쪽(else) 변경은 위반
        mixed = fn + "    if t == 'PULLBACK' or x:\n        a = 1\n    else:\n        a = 2\n    return a\n"
        mixed2 = fn + "    if t == 'PULLBACK' or x:\n        a = 5\n    else:\n        a = 2\n    return a\n"
        self.assertTrue(epc.ema_path_diff(rel, mixed, mixed2))                             # 혼합(or) 조건은 지우지 않는다
        andc = fn + "    if t == 'PULLBACK' and x:\n        a = 1\n    return a\n"
        andc2 = fn + "    if t == 'PULLBACK' and not x:\n        a = 7\n    return a\n"
        self.assertEqual(epc.ema_path_diff(rel, andc, andc2), [])                          # and 묶음은 body·조건 변경 허용(orelse 없음)

    def test_ast_rule_catches_a_changed_ema_function(self):
        """규칙이 정말 막는지: EMA 함수 하나를 바꾼 가짜 원본은 위반으로 잡힌다."""
        base = "class A:\n    def execute(self):\n        return 1\n"
        changed = "class A:\n    def execute(self):\n        return 2\n"
        self.assertEqual(epc.ema_path_diff("core/other.py", base, base), [])
        self.assertTrue(epc.ema_path_diff("core/other.py", base, changed))
        added = base + "    def helper(self):\n        return 3\n"
        self.assertTrue(epc.ema_path_diff("core/other.py", base, added))                # 새 함수는 pullback 이름이어야 한다
        added_pb = base + "    def _pullback_helper(self):\n        return 3\n"
        self.assertEqual(epc.ema_path_diff("core/other.py", base, added_pb), [])


if __name__ == "__main__":
    unittest.main()
