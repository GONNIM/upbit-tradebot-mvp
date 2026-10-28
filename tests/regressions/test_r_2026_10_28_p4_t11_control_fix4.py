"""
2차 T11 수정 4회차: verifier 4차 지적 반영 시험.

1. 강제 매도만으로도 묶음 수가 차 강제 매수가 멈춤(매도를 셈에서 빼는 변이 m7 을 잡음).
   멈춤이 풀린 직후에도 지난 1시간 매도 때문에 다시 멈춤. 결과 message 는 묶음별 문구(공용 문구로 되돌리는 변이 m8 을 잡음).
2. 시도가 아닌 거절 알림은 (사용자, 종류, code) 60초에 1회(같은 종류·다른 code 는 따로 — m12). 시도한 결과는 요청마다.
3. 넘친 파일·깨진 파일 경고 로그는 같은 폴더·같은 사유 60초에 1줄.

실행:
    TELEGRAM_BOT_TOKEN= TELEGRAM_CHAT_ID= python3 -m unittest tests.regressions.test_r_2026_10_28_p4_t11_control_fix4 -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from engine import control_requests as cr  # noqa: E402
from tests.regressions import test_r_2026_10_28_p4_t11_control as t11  # noqa: E402


def _result_notes(notify, text):
    return [c for c in notify.call_args_list
            if str(c.kwargs.get("dedupe_key", "")).startswith("v2_control:") and text in str(c.args)]


class TestSellsFillOrderCap(t11.CtlCase):
    def _sell(self):
        self.req("force_sell")
        self.ctl.scan_once()
        self.clock.sleep(cr.MIN_INTERVAL_SEC + 1)

    def test_sells_only_then_buy_suspended_and_resuspended(self):
        for _ in range(cr.HOURLY_CAP + 1):
            self._sell()
        self.assertEqual(len(self.forced), cr.HOURLY_CAP + 1)                         # 매도는 멈춤 중에도 실행
        rid = self.req("force_buy")
        self.ctl.scan_once()
        res = self.result(rid)
        self.assertEqual(res["code"], "control_suspended")
        self.assertEqual(res["message"], cr.CODE_TEXT["control_suspended_order"])
        self.assertNotEqual(res["message"], cr.CODE_TEXT["control_suspended"])
        self.assertEqual(res["detail"].get("group"), "order")
        # 멈춤 동안 매도를 계속 넣음 → 풀린 직후에도 지난 1시간 매도가 6건 넘어 다시 멈춤
        until = self.ctl._suspended[("alice", "order")]
        while self.clock.mono() < until:
            self._sell()
        rid = self.req("force_buy")
        self.ctl.scan_once()
        self.assertEqual(self.result(rid)["code"], "control_suspended")
        self.assertGreater(self.ctl._suspended[("alice", "order")], until)            # 새 멈춤
        self.assertEqual([f for f in self.forced if f[0] == "buy"], [])


class TestEngineGroupMessage(t11.CtlCase):
    def test_engine_group_message(self):
        self.mgr.mode = None
        for i in range(cr.HOURLY_CAP):
            self.req("engine_start" if i % 2 == 0 else "engine_stop")
            self.ctl.scan_once()
            self.clock.sleep(cr.MIN_INTERVAL_SEC + 1)
        self.mgr.mode = None
        rid = self.req("engine_start")
        self.ctl.scan_once()
        res = self.result(rid)
        self.assertEqual(res["code"], "control_suspended")
        self.assertEqual(res["message"], cr.CODE_TEXT["control_suspended_engine"])


class TestRejectNotifyDedupe(t11.CtlCase):
    def test_same_reject_10_then_after_60s(self):
        text = cr.CODE_TEXT["not_ready"]
        for _ in range(10):
            self.req("apply_params")
            self.ctl.scan_once()
            self.clock.sleep(1)
        self.assertEqual(len(_result_notes(self.notify, text)), 1)
        self.clock.sleep(cr.REJECT_NOTIFY_SEC + 1)
        self.req("apply_params")
        self.ctl.scan_once()
        self.assertEqual(len(_result_notes(self.notify, text)), 2)

    def test_same_kind_other_code_notifies(self):
        # verifier 5차: dedupe 키에 code 가 들어 있어야 같은 종류의 다른 거절도 알림(변이 m12 를 잡음)
        self.req("apply_params")
        self.ctl.scan_once()
        self.clock.sleep(1)
        self.req("apply_params", created=self.clock.t - 120)
        self.ctl.scan_once()
        self.assertEqual(len(_result_notes(self.notify, cr.CODE_TEXT["not_ready"])), 1)
        self.assertEqual(len(_result_notes(self.notify, cr.CODE_TEXT["expired"])), 1)

    def test_attempted_results_notify_each(self):
        for _ in range(3):
            self.req("force_sell")
            self.ctl.scan_once()
            self.clock.sleep(cr.MIN_INTERVAL_SEC + 1)
        self.assertEqual(len(_result_notes(self.notify, cr.CODE_TEXT["ok"])), 3)


class TestWarnLogThrottle(t11.CtlCase):
    def _broken(self):
        d = self.base / "alice"
        d.mkdir(mode=0o700, exist_ok=True)
        self._n += 1
        (d / f"req-broken{self._n}.json").write_text("{not json")

    def _count(self, logs, word):
        return sum(1 for line in logs.output if word in line)

    def test_broken_warning_once_per_60s(self):
        with self.assertLogs("engine.control_requests", level="WARNING") as logs:
            for _ in range(5):
                self._broken()
                self.ctl.scan_once()
                self.clock.sleep(2)
            self.assertEqual(self._count(logs, "형식 오류"), 1)
            self.clock.sleep(cr.WARN_LOG_SEC + 1)
            self._broken()
            self.ctl.scan_once()
        self.assertEqual(self._count(logs, "형식 오류"), 2)

    def test_too_many_warning_once_per_60s(self):
        with self.assertLogs("engine.control_requests", level="WARNING") as logs:
            for _ in range(3):
                for _ in range(cr.MAX_REQ_FILES + 3):
                    self.req("apply_params")
                self.ctl.scan_once()
                self.clock.sleep(2)
        self.assertEqual(self._count(logs, "넘친"), 1)


if __name__ == "__main__":
    unittest.main()
