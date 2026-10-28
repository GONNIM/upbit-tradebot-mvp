"""
2차 T11 수정 3회차: verifier 3차 지적 반영 시험.

1. 실행 예외도 30초 창·시간당 묶음에 센다(엔진 없을 때 force_liquidate 가 주문 뒤 insert_log 에서 실패할 수 있음).
2. 요청 파일 수·크기 상한: 사용자당 한 번에 이름순 앞 10개만 보고 나머지는 지움(운영자 알림 1회), 1개 8KB.
3. 멈춤 중에도 강제 매도는 실행(30초 창은 유지).
4. 묶음 밖 종류도 기본 묶음(other)에 들어감 — switch·revert 는 engine 묶음.
5. 소유자 다름 거부(가짜 uid), result_unknown 뒤 too_frequent.
6. 멈춤 문구는 묶음별.

실행:
    TELEGRAM_BOT_TOKEN= TELEGRAM_CHAT_ID= python3 -m unittest tests.regressions.test_r_2026_10_28_p4_t11_control_fix3 -v
"""
from __future__ import annotations

import json
import os
import resource
import sys
import time as _time
import tracemalloc
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from core import engine_control as ec  # noqa: E402
from core import safe_file  # noqa: E402
from engine import control_requests as cr  # noqa: E402
from tests.regressions import test_r_2026_10_28_p4_t11_control as t11  # noqa: E402


def _alerts(notify, prefix):
    return [c for c in notify.call_args_list if c.args and c.args[0] == "CRITICAL"
            and str(c.kwargs.get("dedupe_key", "")).startswith(prefix)]


class TestExceptionCounted(t11.CtlCase):
    def boom_ctl(self):
        calls = []

        def boom(u, trader, ticker, **k):
            calls.append(1)
            raise RuntimeError("after order (insert_log failed)")
        return self.make(force_sell_fn=boom, force_buy_fn=boom), calls

    def test_exception_then_immediate_retry_too_frequent(self):
        ctl, calls = self.boom_ctl()
        r1 = self.req("force_sell")
        ctl.scan_once()
        self.assertEqual(self.result(r1)["code"], "exception")
        r2 = self.req("force_sell")
        ctl.scan_once()
        self.assertEqual(self.result(r2)["code"], "too_frequent")
        self.assertEqual(len(calls), 1)

    def test_six_exceptions_suspend_buys(self):
        ctl, calls = self.boom_ctl()
        for _ in range(cr.HOURLY_CAP):
            self.req("force_buy")
            ctl.scan_once()
            self.clock.sleep(cr.MIN_INTERVAL_SEC + 1)
        rid = self.req("force_buy")
        ctl.scan_once()
        self.assertEqual(self.result(rid)["code"], "control_suspended")
        self.assertEqual(len(calls), cr.HOURLY_CAP)
        self.assertEqual(len(_alerts(self.notify, "v2_control_suspend:")), 1)


class TestRequestFloodLimits(t11.CtlCase):
    def test_only_first_10_per_scan_rest_deleted_alert_once(self):
        rids = [self.req("apply_params", created=self.clock.t - 100 + i) for i in range(25)]
        d = self.base / "alice"
        names = sorted(p.name for p in d.glob("req-*.json"))
        self.ctl.scan_once()
        left = sorted(p.name for p in d.glob("req-*.json"))
        self.assertEqual(left, names[1:cr.MAX_REQ_FILES])                               # 앞 10개 중 1건 처리, 9개 남음
        self.assertEqual(len(_alerts(self.notify, "v2_control_bad:alice")), 1)
        self.assertIsNotNone(self.result(rids[0]))
        self.ctl.scan_once()
        self.assertEqual(len(_alerts(self.notify, "v2_control_bad:alice")), 1)

    def test_over_8kb_is_broken(self):
        self.assertEqual(cr.MAX_REQ_BYTES, 8 * 1024)
        rid = self.req("apply_params", payload={"pad": "x" * (9 * 1024)})
        self.ctl.scan_once()
        self.assertIsNone(self.result(rid))
        self.assertFalse((self.base / "alice" / f"req-{rid}.json").exists())

    def test_v2_writer_limit_fits_engine_limit(self):
        """신버전이 쓸 수 있는 가장 큰 요청(값 4096바이트, 한글 포함)도 엔진 상한 8KB 안."""
        from v2 import control as v2ctl
        self.assertLessEqual(v2ctl.MAX_PAYLOAD_BYTES + 1024, cr.MAX_REQ_BYTES)
        with self.assertRaises(ValueError):                                             # 한글 2000자 = 6000바이트
            v2ctl._validate("alice", "TEST", "apply_params", {"memo": "가" * 2000})

    def test_flood_2000_files_8kb_fast_and_small(self):
        d = self.base / "alice"
        d.mkdir(mode=0o700)
        os.chmod(d, 0o700)
        raw = json.dumps({"v": 1, "id": "20261028120000-0000abcd", "user_id": "alice",
                          "pad": "x" * (8 * 1024 - 120)})
        self.assertLessEqual(len(raw.encode()), 8 * 1024)
        for i in range(2000):
            (d / f"req-{i:06d}.json").write_text(raw)
        tracemalloc.start()
        t = _time.perf_counter()
        self.ctl.scan_once()
        dt = _time.perf_counter() - t
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        self.assertLess(dt, 1.0)
        self.assertLess(peak, 5 * 1024 * 1024)                                          # 실측 뒤 정한 상한(보고)
        self.assertLessEqual(len(os.listdir(d)), cr.MAX_REQ_FILES)
        print(f"\n[flood] 2000×8KB scan {dt:.3f}s peak {peak / 1024:.0f}KB "
              f"maxrss {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}", file=sys.stderr)


class TestAlwaysRunSell(t11.CtlCase):
    def test_force_sell_runs_while_order_group_suspended(self):
        for _ in range(cr.HOURLY_CAP):
            self.req("force_buy")
            self.ctl.scan_once()
            self.clock.sleep(cr.MIN_INTERVAL_SEC + 1)
        rid = self.req("force_buy")
        self.ctl.scan_once()
        self.assertEqual(self.result(rid)["code"], "control_suspended")
        rid = self.req("force_sell")
        self.ctl.scan_once()
        self.assertEqual(self.result(rid)["code"], "ok")
        self.assertEqual(self.forced[-1][0], "sell")
        rid = self.req("force_sell")                                                    # 30초 창은 그대로
        self.ctl.scan_once()
        self.assertEqual(self.result(rid)["code"], "too_frequent")
        self.assertIn("force_sell", cr.ALWAYS_RUN_KINDS)


class TestDefaultGroup(t11.CtlCase):
    def test_every_kind_has_group(self):
        for kind in cr.KINDS:
            self.assertIn(cr._group_of(kind), ("order", "engine", "other"), kind)
        self.assertEqual(cr._group_of("switch"), "engine")
        self.assertEqual(cr._group_of("revert"), "engine")
        self.assertEqual(cr._group_of("apply_params"), "other")

    def test_registered_handler_capped(self):
        calls = []
        with mock.patch.dict(cr._EXTRA_HANDLERS,
                             {"ops_settings": lambda ctl, req: calls.append(1) or cr._result("done", "ok")}):
            for _ in range(cr.HOURLY_CAP + 2):
                self.req("ops_settings")
                self.ctl.scan_once()
                self.clock.sleep(1)
        self.assertEqual(len(calls), cr.HOURLY_CAP)
        alerts = _alerts(self.notify, "v2_control_suspend:alice:other")
        self.assertEqual(len(alerts), 1)


class TestOwnerAndUnknown(t11.CtlCase):
    def test_other_owner_rejected(self):
        rid = self.req()
        real = os.geteuid()
        with mock.patch.object(safe_file.os, "geteuid", return_value=real + 4242):
            self.ctl.scan_once()
        self.assertIsNone(self.result(rid))
        self.assertEqual(self.mgr.calls, [])
        self.assertEqual(len(_alerts(self.notify, "v2_control_bad:")), 1)
        fd = os.open(str(self.base), os.O_RDONLY)
        try:
            with mock.patch.object(safe_file.os, "fstat",
                                   return_value=SimpleNamespace(st_mode=0o40700, st_uid=real + 1)):
                self.assertEqual(safe_file.check_dir_fd(fd), "owner")
        finally:
            os.close(fd)

    def test_result_unknown_then_too_frequent(self):
        class StartQ:
            def put(self_q, item):
                with item.lock:
                    item.started = True
        eng = SimpleNamespace(control_queue=StartQ())
        self.mgr.mode = "TEST"
        with mock.patch.object(ec, "running_engine", return_value=eng):
            r1 = self.req("force_buy")
            self.ctl.scan_once()
            r2 = self.req("force_buy")
            self.ctl.scan_once()
        self.assertEqual(self.result(r1)["code"], "result_unknown")
        self.assertEqual(self.result(r2)["code"], "too_frequent")


class TestSuspendTexts(unittest.TestCase):
    def test_texts_per_group(self):
        order, engine, other = (cr.SUSPEND_BODY[g] for g in ("order", "engine", "other"))
        self.assertIn("강제 매도는 계속 할 수 있습니다", order)
        self.assertIn("엔진 정지는 계속 할 수 있습니다", engine)
        for body in (order, engine, other):
            self.assertIn("직접 요청하신 것이 아니라면 운영자에게 바로 알려 주세요", body)
            for word in ("control_suspended", "T11", "force_", "engine_", "switch"):
                self.assertNotIn(word, body)
        for g in ("order", "engine", "other"):
            self.assertIn(f"control_suspended_{g}", cr.CODE_TEXT)


if __name__ == "__main__":
    unittest.main()
