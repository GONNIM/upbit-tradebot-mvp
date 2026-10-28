"""
2차 T11 수정 2회차: verifier 2차 지적 N1~N7 반영 시험.

- N1·N3 누적 상한: 강제 주문(매수·매도 합)·엔진 시작/정지(합) 각각 사용자당 1시간 6건. 넘으면 그 묶음 1시간 멈춤
  (control_suspended, 운영자 CRITICAL 1회). 엔진 정지는 멈춤 중에도 실행(매매를 멈추는 안전한 쪽). 상태는 프로세스 메모리.
- N2: 폴더 권한이 700 이 아니면 자동 chmod 없이 거부·알림. 폴더를 연 뒤 링크로 바꿔치기해도 바깥을 건드리지 않음
  (폴더 fd 기준 읽기·쓰기).
- N4: read_nofollow 단위 시험.
- N5: 30초 창은 실제로 주문을 시도한 결과에만 기록(잔고 없음 거절 뒤 바로 다시 → 실행). 문구에 「30초 뒤 다시 눌러 주세요」.
- N7: 기동 때 생존 파일·쉼 표식 폴더의 10분 넘은 임시 파일 정리(링크는 건너뜀).

실행:
    TELEGRAM_BOT_TOKEN= TELEGRAM_CHAT_ID= python3 -m unittest tests.regressions.test_r_2026_10_28_p4_t11_control_fix2 -v
"""
from __future__ import annotations

import json
import os
import stat
import sys
import time as _time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from core import safe_file  # noqa: E402
from engine import control_requests as cr  # noqa: E402
from tests.regressions import test_r_2026_10_28_p4_t11_control as t11  # noqa: E402


def _suspend_alerts(notify):
    return [c for c in notify.call_args_list if c.args and c.args[0] == "CRITICAL"
            and str(c.kwargs.get("dedupe_key", "")).startswith("v2_control_suspend:")]


# ================================================================ N1·N3 누적 상한
class TestHourlyCap(t11.CtlCase):
    def test_alternating_buy_sell_capped_6_per_hour(self):
        """매수·매도를 2초마다 번갈아 1시간 → 강제 매수 실행 6건 이하, 그 뒤 매수 멈춤, 멈춤 뒤 풀림.
        수정 3회차: 강제 매도는 멈춤 중에도 실행(30초 창만) — 매도는 30초마다 1건 이하."""
        t_start = self.clock.t
        kinds = ("force_buy", "force_sell")
        i = 0
        while self.clock.t - t_start < 3600:
            self.req(kinds[i % 2])
            self.ctl.scan_once()
            i += 1
            self.clock.sleep(2)
        buys = [f for f in self.forced if f[0] == "buy"]
        sells = [f for f in self.forced if f[0] == "sell"]
        self.assertLessEqual(len(buys), cr.HOURLY_CAP)
        self.assertGreaterEqual(len(buys), 1)
        self.assertLessEqual(len(sells), int(3600 // cr.MIN_INTERVAL_SEC) + 1)
        first_hour = len(self.forced)
        alerts = _suspend_alerts(self.notify)
        self.assertEqual(len(alerts), 1)                                               # 운영자 CRITICAL 1회
        title, body = alerts[0].args[1], alerts[0].args[2]
        self.assertIn("1시간에 6번을 넘어 1시간 동안 강제 매수를 받지 않습니다", body)
        self.assertIn("강제 매도는 계속 할 수 있습니다", body)
        self.assertIn("직접 요청하신 것이 아니라면 운영자에게 바로 알려 주세요", body)
        for word in ("control_suspended", "T11", "force_", "engine_"):
            self.assertNotIn(word, title + body)
        codes = [json.loads(p.read_text())["code"] for p in (self.base / "alice").glob("res-*.json")]
        self.assertIn("control_suspended", codes)
        # 멈춤 중 요청은 투자자 결과 알림을 하나씩 보내지 않는다(운영자 1회로 갈음)
        susp_notes = [c for c in self.notify.call_args_list
                      if str(c.kwargs.get("dedupe_key", "")).startswith("v2_control:")
                      and cr.CODE_TEXT["control_suspended_order"] in str(c.args)]
        self.assertEqual(susp_notes, [])
        # 멈춤이 끝나고 지난 1시간 시도가 6건 미만이면 다시 받음(멈춤 중 매도도 시도로 센다 — 수정 3회차)
        until = self.ctl._suspended[("alice", "order")]
        self.clock.t = until + cr.CAP_WINDOW_SEC + 1
        self.req("force_buy")
        self.ctl.scan_once()
        self.assertEqual(len(self.forced), first_hour + 1)

    def test_engine_stop_runs_while_suspended(self):
        self.mgr.mode = None
        for i in range(cr.HOURLY_CAP):
            kind = "engine_start" if i % 2 == 0 else "engine_stop"
            self.req(kind)
            self.ctl.scan_once()
            self.clock.sleep(cr.MIN_INTERVAL_SEC + 1)
        self.assertEqual(len(self.mgr.calls), cr.HOURLY_CAP)
        rid = self.req("engine_start")                                                  # 7번째 → 멈춤
        self.ctl.scan_once()
        self.assertEqual(self.result(rid)["code"], "control_suspended")
        self.assertEqual(len(_suspend_alerts(self.notify)), 1)
        self.mgr.mode = "TEST"
        self.clock.sleep(cr.MIN_INTERVAL_SEC + 1)
        rid = self.req("engine_stop")                                                   # 정지는 멈춤 중에도 실행
        self.ctl.scan_once()
        self.assertEqual(self.result(rid)["code"], "stopped")
        self.assertEqual(self.mgr.calls[-1][0], "stop")
        rid = self.req("engine_start")
        self.ctl.scan_once()
        self.assertEqual(self.result(rid)["code"], "control_suspended")

    def test_groups_are_separate_and_state_in_memory(self):
        for _ in range(cr.HOURLY_CAP + 1):
            self.req("force_buy")
            self.ctl.scan_once()
            self.clock.sleep(cr.MIN_INTERVAL_SEC + 1)
        self.assertEqual(len(self.forced), cr.HOURLY_CAP)
        rid = self.req("engine_start")                                                  # 다른 묶음은 막지 않음
        self.ctl.scan_once()
        self.assertEqual(self.result(rid)["code"], "started")
        # 프로세스 메모리 상태: 새 감시기(엔진 재시작)는 비어 있음 — 계획 메모에 적음
        fresh = self.make()
        self.mgr.mode = None                                                            # 엔진 없음 경로로 강제 매수
        self.req("force_buy")
        fresh.scan_once()
        self.assertEqual(len(self.forced), cr.HOURLY_CAP + 1)


# ================================================================ N5 30초 창은 주문 시도에만
class TestIntervalOnlyAfterAttempt(t11.CtlCase):
    def test_no_balance_reject_then_immediate_retry_runs(self):
        msgs = ["⚠️ 강제매수 실패: 보유 KRW가 없습니다.", "[TEST] ok"]
        calls = []

        def fb(u, trader, ticker, **k):
            calls.append(1)
            return msgs[len(calls) - 1]
        ctl = self.make(force_buy_fn=fb)
        r1 = self.req("force_buy")
        ctl.scan_once()
        self.assertEqual(self.result(r1)["code"], "no_balance")
        r2 = self.req("force_buy")
        ctl.scan_once()
        self.assertEqual(self.result(r2)["code"], "ok")                                 # 바로 다시 → 실행됨
        r3 = self.req("force_buy")
        ctl.scan_once()
        res = self.result(r3)
        self.assertEqual(res["code"], "too_frequent")                                  # 주문 시도 뒤에는 30초 창
        self.assertIn("30초 뒤 다시 눌러 주세요", res["message"])
        self.assertEqual(len(calls), 2)

    def test_order_failed_counts_as_attempt(self):
        ctl = self.make(force_buy_fn=lambda u, t, tk, **k: "❌ 강제매수 실패: 주문 생성 실패")
        self.req("force_buy")
        ctl.scan_once()
        rid = self.req("force_buy")
        ctl.scan_once()
        self.assertEqual(self.result(rid)["code"], "too_frequent")


# ================================================================ N2 권한 자동 수정 없음·폴더 바꿔치기
class TestDirStrict(t11.CtlCase):
    def setUp(self):
        super().setUp()
        self.outside = Path(self.tmp.name) / "outside"
        self.outside.mkdir()

    def test_mode_not_700_rejected_unchanged(self):
        rid = self.req()
        os.chmod(self.base, 0o755)
        self.ctl.scan_once()
        self.assertIsNone(self.result(rid))
        self.assertEqual(stat.S_IMODE(self.base.lstat().st_mode), 0o755)
        self.assertEqual(self.mgr.calls, [])
        self.assertTrue(any(str(c.kwargs.get("dedupe_key", "")).startswith("v2_control_bad:")
                            for c in self.notify.call_args_list))

    def test_verifier_race_layout_outside_untouched(self):
        """verifier 재현(scratchpad v3/race) 모양: v2_control → 바깥 링크, 바깥에 사용자 이름 폴더(755)."""
        etc = self.outside / "etc"
        etc.mkdir()
        os.chmod(etc, 0o755)
        os.rmdir(self.base)
        os.symlink(self.outside, self.base)
        self.ctl.scan_once()
        self.assertEqual(stat.S_IMODE(etc.stat().st_mode), 0o755)
        self.assertEqual(list(etc.iterdir()), [])

    def test_swap_after_open_does_not_touch_outside(self):
        """감시가 폴더를 연(권한 확인) 직후 폴더를 바깥 링크로 바꿔치기 → 연 폴더 기준으로만 읽고 씀."""
        rid = self.req()
        out_alice = self.outside / "alice"
        out_alice.mkdir(mode=0o700)
        os.chmod(out_alice, 0o700)
        bait = out_alice / f"req-{rid}.json"
        bait.write_text((self.base / "alice" / f"req-{rid}.json").read_text())
        os.chmod(self.outside, 0o700)
        moved = Path(self.tmp.name) / "moved_v2_control"
        real = cr.check_dir_fd
        state = {"n": 0}

        def swap_after_first(fd):
            why = real(fd)
            state["n"] += 1
            if state["n"] == 1:                       # 바탕 폴더 확인 직후 바꿔치기
                os.rename(self.base, moved)
                os.symlink(self.outside, self.base)
            return why
        with mock.patch.object(cr, "check_dir_fd", side_effect=swap_after_first):
            self.ctl.scan_once()
        self.assertTrue(bait.exists())                                                  # 바깥 요청 안 지움
        self.assertEqual(sorted(p.name for p in out_alice.iterdir()), [bait.name])     # 바깥에 결과 안 씀
        self.assertTrue((moved / "alice" / f"res-{rid}.json").exists())                # 연 폴더에 결과
        self.assertEqual(stat.S_IMODE(self.outside.stat().st_mode), 0o700)


# ================================================================ N4 read_nofollow
class TestReadNoFollow(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.d = Path(self.tmp.name)
        self.secret = self.d / "outside_secret.txt"
        self.secret.write_text("SECRET-CONTENT")
        self.link = self.d / "req-link.json"
        os.symlink(self.secret, self.link)

    def test_symlink_path_returns_none(self):
        self.assertIsNone(safe_file.read_nofollow(self.link, 1024))

    def test_symlink_with_dir_fd_returns_none(self):
        fd = os.open(str(self.d), os.O_RDONLY)
        try:
            self.assertIsNone(safe_file.read_nofollow(self.link.name, 1024, dir_fd=fd))
            self.assertEqual(safe_file.read_nofollow(self.secret.name, 1024, dir_fd=fd), b"SECRET-CONTENT")
        finally:
            os.close(fd)

    def test_regular_dir_and_limit(self):
        self.assertEqual(safe_file.read_nofollow(self.secret, 1024), b"SECRET-CONTENT")
        self.assertIsNone(safe_file.read_nofollow(self.secret, 5))                       # 상한 초과
        self.assertIsNone(safe_file.read_nofollow(self.d, 1024))                         # 폴더
        self.assertIsNone(safe_file.read_nofollow(self.d / "missing", 1024))


# ================================================================ N7 오래된 임시 파일 정리
class TestStaleTmpCleanup(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.d = Path(self.tmp.name)

    def touch(self, name, age):
        p = self.d / name
        p.write_text("x")
        t = _time.time() - age
        os.utime(p, (t, t))
        return p

    def test_removes_old_ours_keeps_new_links_and_others(self):
        old1 = self.touch(".engine_alive.json.tmp", 700)                               # 옛 고정 이름
        old2 = self.touch(".engine_alive.json.ab12cd.tmp", 900)
        old3 = self.touch(".engine_restart.json.zz.tmp", 601)
        new = self.touch(".engine_alive.json.new1.tmp", 30)
        other = self.touch(".something_else.tmp", 3000)                                 # 다른 모듈 것은 건드리지 않음
        target = self.touch("victim.txt", 5000)
        link = self.d / ".engine_restart.json.link.tmp"
        os.symlink(target, link)
        t = _time.time() - 5000
        os.utime(link, (t, t), follow_symlinks=False)
        removed = safe_file.clean_stale_tmp(self.d, (".engine_alive.json", ".engine_restart.json"), 600)
        self.assertEqual(sorted(removed), sorted([old1.name, old2.name, old3.name]))
        for p in (old1, old2, old3):
            self.assertFalse(p.exists())
        self.assertTrue(new.exists())
        self.assertTrue(other.exists())
        self.assertTrue(link.is_symlink())                                              # 링크는 건너뜀
        self.assertEqual(target.read_text(), "x")

    def test_boot_main_cleans_before_threads(self):
        src = (ROOT / "scripts" / "tradebot_boot.py").read_text(encoding="utf-8")
        body = src.split("def main()")[1]
        self.assertIn("_clean_stale_tmp()", body)
        self.assertLess(body.index("_clean_stale_tmp()"), body.index('name="engine_alive"'))
        self.assertRegex(body, r"try:\n\s+_clean_stale_tmp\(\)\n\s+except Exception")
        boot = t11.load_boot()
        old = self.touch(".engine_alive.json.q.tmp", 1200)
        with mock.patch.object(boot, "ENGINE_ALIVE_PATH", str(self.d / ".engine_alive.json")):
            boot._clean_stale_tmp()
        self.assertFalse(old.exists())


if __name__ == "__main__":
    unittest.main()
