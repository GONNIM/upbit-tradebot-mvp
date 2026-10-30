"""
1030-09: 이 시험 프로세스 안에서 바깥 연결 차단이 켜져 있는지 확인한다(게이트 밖 단독 실행 포함).

파일 이름이 test_00 으로 시작하는 이유: `discover -s tests/v2`(-t 없음)는 모듈을 이름순으로
모두 불러온 뒤 시험을 돌리고, 이때 패키지 __init__ 은 누군가 `tests.v2` 를 불러와야 실행된다.
이 파일이 맨 먼저 불러와지며 `import tests.v2` 로 차단을 켜므로 어떤 시험보다 먼저 켜진다.

실행:
    python3 -m unittest tests.v2.test_00_netguard_active -v
"""
import contextlib
import io
import os
import socket
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tests.v2  # noqa: E402,F401 — 패키지 __init__ 이 차단을 켠다
from tests._netguard import PLACEHOLDER, activate, expected_blocks  # noqa: E402

MARK = "[" + "NETGUARD" + "]"


class TestNetguardActiveInProcess(unittest.TestCase):
    def test_installed_and_keys_placeholder(self):
        self.assertTrue(getattr(socket, "_netguard_installed", False))
        self.assertEqual(os.environ.get("UPBIT_ACCESS"), PLACEHOLDER)
        self.assertEqual(os.environ.get("UPBIT_SECRET"), PLACEHOLDER)
        self.assertEqual(os.environ.get("NETGUARD"), "1")  # 하위 프로세스로 전파

    def test_activate_twice_does_not_rewrap(self):
        guard = sys.modules["_tradebot_netguard_guard"]
        before = (socket.getaddrinfo, socket.create_connection, socket.socket.connect)
        activate()
        self.assertFalse(guard.install())
        self.assertEqual(before, (socket.getaddrinfo, socket.create_connection, socket.socket.connect))

    def test_blocks_upbit_in_process(self):
        fd, log = tempfile.mkstemp(prefix="netguard_inproc_")
        os.close(fd)
        self.addCleanup(os.remove, log)
        old = os.environ.get("NETGUARD_LOG")
        os.environ["NETGUARD_LOG"] = log  # 게이트 전체 로그를 더럽히지 않게
        err = io.StringIO()
        try:
            guard = sys.modules["_tradebot_netguard_guard"]
            before = len(guard.blocked_lines())
            with expected_blocks():  # 허용된 3곳 중 하나 — 끝날 때 차단 기록을 되돌려 종료 코드 1을 피함
                with contextlib.redirect_stderr(err):
                    with self.assertRaises(RuntimeError) as cm:
                        socket.getaddrinfo("api.upbit.com", 443)
                self.assertEqual(len(guard.blocked_lines()), before + 1)
            self.assertEqual(len(guard.blocked_lines()), before)
        finally:
            if old is None:
                os.environ.pop("NETGUARD_LOG", None)
            else:
                os.environ["NETGUARD_LOG"] = old
        self.assertEqual(type(cm.exception).__name__, "NetguardBlocked")
        self.assertIn(MARK + " blocked upbit host=api.upbit.com", err.getvalue())
        self.assertIn("host=api.upbit.com", Path(log).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
