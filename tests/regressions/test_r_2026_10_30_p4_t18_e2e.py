"""
2차 T18 (결정 1030-06 B (라)): 제어 요청 통로 끝에서 끝까지 — 실제 파일로 잇는 통합 시험.

`v2.control.write_request`(신버전 쓰기) → 임시 폴더의 실제 요청 파일 → 엔진 `engine.control_requests.Controller.scan_once`
(감시 스레드 한 회차) → 실제 결과 파일 → `v2.control.read_result`(신버전 읽기). 단위 시험(tests/v2/test_control.py,
T11 시험)은 구간을 따로 보고, 이 시험은 한 프로세스 안에서 두 쪽을 같은 폴더로 잇는다(계획 T18 Step 6 의 로컬 흐름 실측 갈음).

- 엔진 관리자·시계는 T11 시험의 가짜(FakeClock·FakeThread·FakeMgr)를 그 파일에서 클래스 정의만 꺼내 쓴다.
  T11 시험 모듈을 import 하면 `config` 가 import 되어 로컬 .env·secrets 를 읽기 때문이다(config.py:9-16).
  거래기·강제 매매 함수도 T11 CtlCase.make 와 같은 가짜를 넘긴다(이 시험의 요청 종류는 부르지 않는다 — 단언).
- 업비트·텔레그램 호출 0: 소켓 연결·주소 조회를 막고(불리면 실패) 엔진 기본 알림·거래기·강제 매매·관리자 함수를 막아
  불리지 않았음을 단언한다. 알림은 가짜(notify)로 받아 내용만 본다.
- 요청 종류: 엔진 시작(이미 도는 중 → rejected already_running), 엔진 정지(done stopped), 한 번에 하나(Busy).

실행:
    TELEGRAM_BOT_TOKEN= TELEGRAM_CHAT_ID= TELEGRAM_CHAT_ID_OPERATOR= \
        python3 -m unittest tests.regressions.test_r_2026_10_30_p4_t18_e2e -v
"""
from __future__ import annotations

import ast
import json
import os
import socket
import stat
import sys
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

_CONFIG_PRELOADED = "config" in sys.modules

from engine import control_requests as cr  # noqa: E402
from v2 import control as v2control  # noqa: E402
from v2 import db as v2db  # noqa: E402

KST = ZoneInfo("Asia/Seoul")
T11_PATH = ROOT / "tests" / "regressions" / "test_r_2026_10_28_p4_t11_control.py"
FAKE_NAMES = ("FakeClock", "FakeThread", "FakeMgr")


def _load_t11_fakes() -> dict:
    """T11 시험 파일에서 가짜 클래스 정의만 꺼내 실행한다(표준 라이브러리만 쓰는 클래스 — 모듈 import 없음)."""
    tree = ast.parse(T11_PATH.read_text(encoding="utf-8"))
    keep = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name in FAKE_NAMES]
    if sorted(n.name for n in keep) != sorted(FAKE_NAMES):
        raise RuntimeError("T11 가짜 클래스를 찾지 못함")
    ns = {"T0": 1_800_000_000.0, "__name__": "t11_fakes"}
    exec(compile(ast.Module(body=keep, type_ignores=[]), str(T11_PATH), "exec"), ns)
    return {k: ns[k] for k in FAKE_NAMES}


_FAKES = _load_t11_fakes()
FakeClock, FakeMgr = _FAKES["FakeClock"], _FAKES["FakeMgr"]
USER = "alice"


def _mode(p: Path) -> int:
    return stat.S_IMODE(os.lstat(p).st_mode)


class TestT18ControlEndToEnd(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data = Path(self.tmp.name) / "services" / "data"
        self.data.mkdir(parents=True)
        # 신버전·엔진 둘 다 같은 임시 데이터 폴더를 보게 한다(신버전은 v2.db.DATA_DIR, 엔진은 base_dir 인자)
        self._patch(mock.patch.object(v2db, "DATA_DIR", self.data))
        # 다른 시험이 붙인 갈고리·처리기(T12 install 등)가 이 흐름에 끼지 않게
        self._patch(mock.patch.object(cr, "_POST_HOOKS", []))
        self._patch(mock.patch.dict(cr._EXTRA_HANDLERS, clear=True))
        # 네트워크 차단(업비트·텔레그램 모두 소켓을 거친다) — 불리면 실패
        self.net = mock.MagicMock(side_effect=OSError("network blocked in test"))
        self._patch(mock.patch.object(socket.socket, "connect", self.net))
        self._patch(mock.patch.object(socket, "create_connection", self.net))
        self._patch(mock.patch.object(socket, "getaddrinfo", self.net))
        # 엔진 기본 경로(실제 알림·UpbitTrader·강제 매매·engine_manager)는 불리면 안 된다
        self.defaults = {}
        for name in ("_default_notify", "_default_trader", "_default_force_sell", "_default_force_buy",
                     "_default_manager", "_active_strategy", "_ticker_and_interval"):
            m = mock.MagicMock(side_effect=AssertionError(f"{name} 호출됨"))
            self.defaults[name] = m
            self._patch(mock.patch.object(cr, name, m))
        self.dotenv = mock.MagicMock()
        try:
            import dotenv  # noqa: F401
            self._patch(mock.patch("dotenv.load_dotenv", self.dotenv))
        except ImportError:
            pass

        self.clock = FakeClock(time.time())
        self.mgr = FakeMgr(self.clock, mode="TEST")       # 모의 엔진이 도는 중
        self.notify = mock.MagicMock(return_value=True)
        self.forced = []
        self.ctl = cr.Controller(
            base_dir=self.data / "v2_control", alive_dir=self.data, manager=self.mgr, notify=self.notify,
            now=self.clock.now, monotonic=self.clock.mono, sleep=self.clock.sleep,
            trader_factory=lambda u, mode, strategy: SimpleNamespace(tag="standalone", user=u, mode=mode),
            force_sell_fn=lambda u, trader, ticker, **k: self.forced.append(("sell", trader)) or "[TEST] ok",
            force_buy_fn=lambda u, trader, ticker, **k: self.forced.append(("buy", trader)) or "[TEST] ok")

    def _patch(self, p):
        p.start()
        self.addCleanup(p.stop)

    def now_dt(self) -> datetime:
        return datetime.fromtimestamp(self.clock.t, KST)

    def user_dir(self) -> Path:
        return self.data / "v2_control" / USER

    def test_write_scan_read_roundtrip(self):
        base, d = self.data / "v2_control", self.user_dir()
        self.assertFalse(base.exists())

        # 1) 엔진 시작 요청 — 이미 모의 엔진이 돌고 있으므로 거절
        rid1 = v2control.write_request(USER, "TEST", "engine_start", {}, now=self.now_dt())
        self.assertEqual((_mode(base), _mode(d)), (0o700, 0o700))     # 신버전이 700 으로 만든다
        self.assertEqual(sorted(p.name for p in d.iterdir()), [f"req-{rid1}.json"])   # 임시 파일 남지 않음
        self.assertEqual(_mode(d / f"req-{rid1}.json"), 0o600)
        self.assertEqual(v2control.read_result(USER, rid1, now=self.now_dt()),
                         {"id": rid1, "status": "pending", "overdue": False})
        # 한 번에 하나: 결과가 없는 요청이 있으면 다음 요청은 Busy
        with self.assertRaises(v2control.Busy) as cm:
            v2control.write_request(USER, "TEST", "engine_stop", {}, now=self.now_dt())
        self.assertEqual(cm.exception.pending, rid1)

        out = self.ctl.scan_once()
        self.assertEqual([r["code"] for r in out], ["already_running"])
        self.assertEqual(sorted(p.name for p in d.iterdir()), [f"res-{rid1}.json"])   # 요청은 엔진이 지운다
        self.assertEqual(_mode(d / f"res-{rid1}.json"), 0o600)
        res1 = v2control.read_result(USER, rid1, now=self.now_dt())
        self.assertEqual((res1["id"], res1["status"], res1["code"]), (rid1, "rejected", "already_running"))
        self.assertEqual(res1["message"], cr.CODE_TEXT["already_running"])
        self.assertEqual(self.mgr.calls, [])                          # 시작 시도 없음

        # 2) 엔진 정지 요청 — 처리됨
        self.clock.sleep(1)
        rid2 = v2control.write_request(USER, "TEST", "engine_stop", {}, now=self.now_dt())
        self.assertNotEqual(rid1, rid2)
        self.assertEqual(v2control.read_result(USER, rid2, now=self.now_dt())["status"], "pending")
        out = self.ctl.scan_once()
        self.assertEqual([r["code"] for r in out], ["stopped"])
        res2 = v2control.read_result(USER, rid2, now=self.now_dt())
        self.assertEqual((res2["id"], res2["status"], res2["code"]), (rid2, "done", "stopped"))
        self.assertEqual(res2["message"], cr.CODE_TEXT["stopped"])
        self.assertEqual(self.mgr.calls, [("stop", USER, "TEST")])
        self.assertIsNone(self.mgr.mode)
        self.assertEqual(sorted(p.name for p in d.iterdir()), sorted([f"res-{rid1}.json", f"res-{rid2}.json"]))
        for p in d.iterdir():
            self.assertEqual(_mode(p), 0o600, p.name)
            self.assertEqual(json.loads(p.read_text(encoding="utf-8"))["id"], p.name[4:-5])
        # 결과가 남았으니 새 요청을 받을 수 있다(진행 중 없음)
        self.assertIsNone(v2control.pending_id(USER, now=self.now_dt()))

        # 3) 알림은 가짜로만, 요청마다 1회(dedupe = 요청 id)
        keys = [c.kwargs.get("dedupe_key") for c in self.notify.call_args_list]
        self.assertEqual(keys, [f"v2_control:{rid1}", f"v2_control:{rid2}"])

        # 4) 외부 호출 0
        self.net.assert_not_called()
        for name, m in self.defaults.items():
            self.assertEqual(m.call_count, 0, name)
        self.assertEqual(self.forced, [])
        self.dotenv.assert_not_called()
        if not _CONFIG_PRELOADED:
            self.assertNotIn("config", sys.modules)                   # 로컬 .env 를 읽는 config 를 불러오지 않음

    def test_expired_request_roundtrip(self):
        """60초가 지난 요청은 엔진이 실행하지 않고 expired 결과를 남긴다 — 신버전이 그대로 읽는다."""
        rid = v2control.write_request(USER, "TEST", "engine_stop", {}, now=self.now_dt())
        self.clock.sleep(61)
        self.assertTrue(v2control.read_result(USER, rid, now=self.now_dt())["overdue"])
        self.ctl.scan_once()
        res = v2control.read_result(USER, rid, now=self.now_dt())
        self.assertEqual((res["status"], res["code"]), ("expired", "expired"))
        self.assertEqual(self.mgr.calls, [])
        self.assertEqual(self.mgr.mode, "TEST")
        self.net.assert_not_called()


if __name__ == "__main__":
    unittest.main()
