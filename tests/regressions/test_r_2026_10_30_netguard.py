"""
1030-09 (2026-10-30): 시험 중 업비트·바깥 호출 차단 장치(tests/_netguard/sitecustomize.py) 회귀 시험.

배경: 10/29 23:16~10/30 00:19 T15 개발 중 시험이 validate_upbit_keys 를 patch 하지 않아 로컬 .env 의
실계좌 키로 업비트 잔고 조회를 보냈다(전부 401, 투자자에게 「등록되지 않은 IP」 알림).

고정:
  - 게이트와 같은 환경(NETGUARD=1 + PYTHONPATH 앞 tests/_netguard)으로 띄운 하위 프로세스에서
    api.upbit.com·외부 IP 조회·텔레그램·바깥 IP 숫자 연결이 막히고 [NETGUARD] 줄이 남는다.
  - 막힘은 getaddrinfo(이름 풀이) 단계에서 끝난다 — 실제 이름 풀이·패킷이 나가지 않는다.
  - requests·services.upbit_api 경로도 막힌다(get_server_public_ip 는 맨 except 로 삼키지만 줄은 남는다).
  - localhost·127.0.0.1·유닉스 소켓은 막지 않는다.
  - NETGUARD=1 이 없으면(서버 엔진처럼) 아무것도 바꾸지 않는다.
  - 하위 프로세스의 하위 프로세스에도 환경 변수로 전파된다.

이 시험은 하위 프로세스마다 자기 NETGUARD_LOG 를 줘서 게이트 전체의 NETGUARD_LOG 를 더럽히지 않는다.

실행:
    python3 -m unittest tests.regressions.test_r_2026_10_30_netguard -v
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
GUARD_DIR = ROOT / "tests" / "_netguard"
MARK = "[" + "NETGUARD" + "]"  # 이 파일 글 자체가 게이트 grep 에 걸리지 않게(출력에 찍히지 않음)

CHILD_RESOLVE = r"""
import socket, sys
fake_calls = []
import _socket
real = _socket.getaddrinfo
def spy(*a, **k):
    fake_calls.append(a[0])
    raise AssertionError('real getaddrinfo reached')
_socket.getaddrinfo = spy  # 차단이 진짜 이름 풀이 앞에서 끝나는지 확인
for host in sys.argv[1:]:
    try:
        socket.getaddrinfo(host, 443)
        print('ALLOWED', host)
    except Exception as e:
        print('BLOCKED', host, type(e).__name__)
print('REAL_CALLS', len(fake_calls))
"""

CHILD_PATHS = r"""
import socket, sys
sys.path.insert(0, sys.argv[1])
out = []
def t(name, fn):
    try:
        fn()
        out.append(f'{name}=ALLOWED')
    except Exception as e:
        out.append(f'{name}=BLOCKED:{type(e).__name__}')
import requests
t('requests_upbit', lambda: requests.get('https://api.upbit.com/v1/accounts', timeout=2))
t('create_conn_upbit', lambda: socket.create_connection(('api.upbit.com', 443), timeout=2))
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
t('connect_ip', lambda: s.connect(('203.0.113.7', 443)))  # TEST-NET-3, 바깥 IP 숫자
s.close()
import services.upbit_api as ua
out.append('server_ip=' + str(ua.get_server_public_ip()))
t('validate_keys', lambda: ua.validate_upbit_keys('dummy-access', 'dummy-secret', timeout=2))
print('\n'.join(out))
"""

CHILD_LOCAL = r"""
import os, socket, tempfile, threading
srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
srv.bind(('127.0.0.1', 0)); srv.listen(2)
port = srv.getsockname()[1]
def acc():
    for _ in range(2):
        c, _a = srv.accept(); c.sendall(b'ok'); c.close()
threading.Thread(target=acc, daemon=True).start()
a = socket.create_connection(('localhost', port), timeout=3); print('localhost', a.recv(2).decode()); a.close()
b = socket.create_connection(('127.0.0.1', port), timeout=3); print('loopback', b.recv(2).decode()); b.close()
p, q = socket.socketpair(); p.sendall(b'ok'); print('socketpair', q.recv(2).decode())
path = os.path.join(tempfile.mkdtemp(), 's.sock')
u = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); u.bind(path); u.listen(1)
v = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); v.connect(path); print('unix ok')
print('installed', getattr(socket, '_netguard_installed', False))
"""

CHILD_NESTED = r"""
import subprocess, sys
r = subprocess.run([sys.executable, '-c', "import socket; print(getattr(socket, '_netguard_installed', False))"],
                   capture_output=True, text=True, timeout=60)
print('nested', r.stdout.strip())
"""


class TestNetguard(unittest.TestCase):
    def setUp(self):
        fd, self.log = tempfile.mkstemp(prefix="netguard_test_")
        os.close(fd)
        self.addCleanup(os.remove, self.log)

    def env(self, guard: bool = True) -> dict:
        e = dict(os.environ, TELEGRAM_BOT_TOKEN="", TELEGRAM_CHAT_ID="", TELEGRAM_CHAT_ID_OPERATOR="")
        e["NETGUARD_LOG"] = self.log  # 게이트 전체 로그와 분리
        pp = [p for p in e.get("PYTHONPATH", "").split(os.pathsep) if p and Path(p).resolve() != GUARD_DIR]
        if guard:
            e["NETGUARD"] = "1"
            e["PYTHONPATH"] = os.pathsep.join([str(GUARD_DIR), *pp])
        else:
            e.pop("NETGUARD", None)
            e["PYTHONPATH"] = os.pathsep.join(pp)
        return e

    def run_child(self, code: str, *args: str, guard: bool = True) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, "-c", code, *args], cwd=str(ROOT), env=self.env(guard),
                              capture_output=True, text=True, timeout=90)

    def log_lines(self) -> list:
        return [ln for ln in Path(self.log).read_text(encoding="utf-8").splitlines() if ln.startswith(MARK)]

    def test_blocks_external_hosts_before_real_resolution(self):
        hosts = ["api.upbit.com", "UPBIT.COM.", "sg-api.upbit.com", "api.ipify.org", "ifconfig.me",
                 "icanhazip.com", "api.telegram.org", "example.org"]
        r = self.run_child(CHILD_RESOLVE, *hosts)
        self.assertEqual(r.returncode, 0, r.stderr[-1500:])
        for h in hosts:
            self.assertIn(f"BLOCKED {h} NetguardBlocked", r.stdout)
        self.assertIn("REAL_CALLS 0", r.stdout)  # 진짜 이름 풀이까지 가지 않음 = 바깥으로 나가지 않음
        cats = [ln.split()[2] for ln in self.log_lines()]
        self.assertEqual(cats, ["upbit", "upbit", "upbit", "ip-lookup", "ip-lookup", "ip-lookup",
                                "telegram", "external"])
        self.assertEqual(r.stderr.count(MARK), len(hosts))
        self.assertNotIn("dummy", r.stderr)

    def test_blocks_requests_and_upbit_api_paths(self):
        r = self.run_child(CHILD_PATHS, str(ROOT))
        self.assertEqual(r.returncode, 0, r.stderr[-1500:])
        out = r.stdout
        self.assertIn("requests_upbit=BLOCKED:NetguardBlocked", out)
        self.assertIn("create_conn_upbit=BLOCKED:NetguardBlocked", out)
        self.assertIn("connect_ip=BLOCKED:NetguardBlocked", out)
        self.assertIn("server_ip=IP 확인 실패", out)  # 맨 except 로 삼켜도
        self.assertIn("validate_keys=BLOCKED:NetguardBlocked", out)
        lines = self.log_lines()
        hosts = {ln.split()[3] for ln in lines}
        self.assertTrue({"host=api.upbit.com", "host=203.0.113.7", "host=api.ipify.org", "host=ifconfig.me",
                         "host=icanhazip.com"} <= hosts, lines)  # 삼켜진 IP 조회도 줄은 남음
        for ln in lines:
            self.assertNotIn("dummy", ln)
            self.assertNotIn("Bearer", ln)

    def test_allows_loopback_and_unix_sockets(self):
        r = self.run_child(CHILD_LOCAL)
        self.assertEqual(r.returncode, 0, r.stderr[-1500:])
        for s in ("localhost ok", "loopback ok", "socketpair ok", "unix ok", "installed True"):
            self.assertIn(s, r.stdout)
        self.assertEqual(self.log_lines(), [])
        self.assertNotIn(MARK, r.stderr)

    def test_inactive_without_env_flag(self):
        """서버 엔진처럼 NETGUARD=1·PYTHONPATH 가 없으면 아무것도 바꾸지 않는다."""
        r = self.run_child("import socket; print(getattr(socket, '_netguard_installed', False))", guard=False)
        self.assertEqual(r.returncode, 0, r.stderr[-1500:])
        self.assertEqual(r.stdout.strip(), "False")
        e = self.env(guard=True)
        e.pop("NETGUARD")
        r2 = subprocess.run([sys.executable, "-c", "import socket; print(getattr(socket, '_netguard_installed', False))"],
                            cwd=str(ROOT), env=e, capture_output=True, text=True, timeout=60)
        self.assertEqual(r2.stdout.strip(), "False")

    def test_propagates_to_grandchild(self):
        r = self.run_child(CHILD_NESTED)
        self.assertEqual(r.returncode, 0, r.stderr[-1500:])
        self.assertIn("nested True", r.stdout)

    def test_gate_wires_guard(self):
        """게이트가 장치를 켜고 차단 표식 줄로 실패시키는 배선이 남아 있다(-v 출력에 표식이 찍히지 않게 글자 그대로 쓰지 않음)."""
        src = (ROOT / "scripts" / "regression_gate.sh").read_text(encoding="utf-8")
        self.assertIn('export NETGUARD=1 NETGUARD_LOG NETGUARD_GATE_INNER=1', src)
        self.assertIn('export PYTHONPATH="$PROJECT_ROOT/tests/_netguard${PYTHONPATH:+:$PYTHONPATH}"', src)
        self.assertIn("unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy", src)
        self.assertLess(src.index("unset HTTP_PROXY"), src.index('bash "$SCRIPT_DIR/regression_gate.sh"'))
        self.assertIn("grep -h '\\[NETGUARD\\]'", src)
        first_py = re.search(r"^[^#\n]*python3", src, re.M).start()  # 주석 아닌 첫 python 단계
        self.assertLess(src.index("NETGUARD_GATE_INNER:-"), first_py)  # 모든 python 단계보다 앞
        self.assertTrue((GUARD_DIR / "sitecustomize.py").is_file())


CHILD_PKG_NOLOG = r"""
import os, socket, sys
assert 'NETGUARD_LOG' not in os.environ and 'NETGUARD' not in os.environ
import tests.regressions
print('installed', getattr(socket, '_netguard_installed', False))
print('keys', os.environ.get('UPBIT_ACCESS'), os.environ.get('UPBIT_SECRET'))
import tests.v2  # 두 패키지를 함께 불러와도 두 번 감싸지 않음
g = sys.modules['_tradebot_netguard_guard']
print('reinstall', g.install())
from tests._netguard import expected_blocks
with expected_blocks():  # 허용된 3곳 중 하나 — 일부러 막히는지 보는 자리
    try:
        socket.getaddrinfo('api.upbit.com', 443)
        print('ALLOWED')
    except Exception as e:
        print('BLOCKED', type(e).__name__)
"""

# 단독 실행(게이트 밖)에서 패키지를 불러온 뒤 t10_revert 유형으로 env=dict(os.environ) 하위 프로세스를 띄운다
CHILD_STANDALONE_GRANDCHILD = r"""
import os, subprocess, sys
import tests.regressions
import tests.v2  # 두 번 불러도 PYTHONPATH 에 중복으로 붙지 않음
here = os.path.realpath(os.path.join(os.getcwd(), 'tests', '_netguard'))
parts = [os.path.realpath(p) for p in os.environ.get('PYTHONPATH', '').split(os.pathsep) if p]
print('env NETGUARD=' + os.environ.get('NETGUARD', ''), 'guard_dir_once=' + str(parts.count(here) == 1))
code = ("import os, socket\n"
        "print('grandchild installed=' + str(getattr(socket, '_netguard_installed', False)))\n"
        "print('grandchild_log_absent=' + str('NETGUARD_LOG' not in os.environ))\n"
        "try:\n"
        "    socket.getaddrinfo('api.upbit.com', 443)\n"
        "    print('grandchild ALLOWED')\n"
        "except Exception as e:\n"
        "    print('grandchild BLOCKED', type(e).__name__)\n")
env = dict(os.environ, TELEGRAM_BOT_TOKEN='', TELEGRAM_CHAT_ID='')
p = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, timeout=60, env=env)
sys.stdout.write(p.stdout)
print('grandchild rc=' + str(p.returncode))
"""

# 4e86afb 이전 T15 결함 흉내: 패키지 시험 안에서 바깥 호출을 하고 예외를 삼킨다 → 종료 코드 1 이어야 함
CHILD_SWALLOW = r"""
import tests.regressions
import services.upbit_api as ua
try:
    ua.validate_upbit_keys('dummy-access', 'dummy-secret', timeout=2)
except Exception:
    pass
print('swallowed')
"""


class TestStandaloneActivation(unittest.TestCase):
    """결정 1030-09 (가): 게이트 밖 단독 실행에서도 tests.regressions·tests.v2 를 불러오면 켜진다."""

    def env(self, log: bool = True) -> dict:
        e = {k: v for k, v in os.environ.items()
             if k not in ("NETGUARD", "NETGUARD_LOG", "PYTHONPATH", "NETGUARD_GATE_INNER")}
        e.update(TELEGRAM_BOT_TOKEN="", TELEGRAM_CHAT_ID="", TELEGRAM_CHAT_ID_OPERATOR="",
                 UPBIT_ACCESS="real-looking-access", UPBIT_SECRET="real-looking-secret")  # 실키가 환경에 있어도 덮어씀
        if log:
            fd, path = tempfile.mkstemp(prefix="netguard_sa_")
            os.close(fd)
            self.addCleanup(os.remove, path)
            e["NETGUARD_LOG"] = path
        return e

    def run_py(self, *args: str, log: bool = True) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, *args], cwd=str(ROOT), env=self.env(log), capture_output=True,
                              text=True, timeout=120)

    def test_package_import_activates_without_env_and_without_log(self):
        r = self.run_py("-c", CHILD_PKG_NOLOG, log=False)
        self.assertEqual(r.returncode, 0, r.stderr[-1500:])
        self.assertIn("installed True", r.stdout)
        self.assertIn("keys netguard-placeholder netguard-placeholder", r.stdout)
        self.assertIn("reinstall False", r.stdout)
        self.assertIn("BLOCKED NetguardBlocked", r.stdout)  # 로그 파일 없어도 예외는 그대로
        self.assertIn(MARK + " blocked upbit host=api.upbit.com", r.stderr)  # 로그 파일 없어도 stderr 에 남김
        self.assertNotIn("real-looking", r.stdout + r.stderr)

    def test_unittest_module_run(self):
        for mod in ("tests.regressions.test_00_netguard_active", "tests.v2.test_00_netguard_active"):
            r = self.run_py("-m", "unittest", mod)
            self.assertEqual(r.returncode, 0, mod + "\n" + r.stderr[-1500:])
            self.assertIn("OK", r.stderr)

    def test_unittest_discover_runs(self):
        for args in (("-s", "tests/regressions"), ("-s", "tests/v2", "-t", "."), ("-s", "tests/v2")):
            r = self.run_py("-m", "unittest", "discover", *args, "-p", "test_00_netguard_active.py")
            self.assertEqual(r.returncode, 0, " ".join(args) + "\n" + r.stderr[-1500:])
            self.assertIn("Ran 3 tests", r.stderr)

    def test_swallowed_block_exits_nonzero(self):
        """예외를 삼켜도 프로세스 종료 코드가 1 (출력을 버리고 종료 코드만 보는 실행 대비)."""
        r = self.run_py("-c", CHILD_SWALLOW, log=False)
        self.assertEqual(r.returncode, 1, r.stdout[-500:])
        self.assertIn("swallowed", r.stdout)
        self.assertIn(MARK + " summary: 4 blocked connection attempt(s)", r.stderr)
        self.assertNotIn("dummy", r.stderr)

    def test_unittest_run_with_swallowed_block_exits_nonzero(self):
        """unittest 가 OK 를 찍어도(시험 통과) 종료 코드는 1."""
        d = Path(tempfile.mkdtemp(prefix="netguard_ut_"))
        self.addCleanup(shutil.rmtree, d, True)
        (d / "test_swallow_probe.py").write_text(
            "import unittest\nimport tests.regressions\nimport services.upbit_api as ua\n\n"
            "class T(unittest.TestCase):\n    def test_it(self):\n        try:\n"
            "            ua.validate_upbit_keys('dummy-access', 'dummy-secret', timeout=2)\n"
            "        except Exception:\n            pass\n", encoding="utf-8")
        e = self.env(log=False)
        e["PYTHONPATH"] = str(ROOT)
        r = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", str(d)], cwd=str(ROOT), env=e,
                           capture_output=True, text=True, timeout=120)
        self.assertIn("OK", r.stderr)
        self.assertEqual(r.returncode, 1, r.stderr[-300:].replace("[", "("))

    def test_discover_loads_activator_first(self):
        """-t 없는 discover 는 이름순으로 불러온다 — 켜는 파일이 두 폴더에서 맨 앞이어야 한다."""
        for d in ("tests/regressions", "tests/v2"):
            names = sorted(p.name for p in (ROOT / d).glob("test*.py"))
            self.assertEqual(names[0], "test_00_netguard_active.py", d)
            # discover 는 sorted(os.listdir) 순서로 폴더도 들어간다 — 켜는 파일보다 앞 폴더에 시험·__init__ 코드 금지
            for entry in sorted(os.listdir(ROOT / d)):
                if entry >= "test_00_netguard_active.py":
                    break
                sub = ROOT / d / entry
                if not sub.is_dir() or entry == "__pycache__":
                    continue
                tests_inside = [p.relative_to(ROOT).as_posix() for p in sub.rglob("test*.py")]
                self.assertEqual(tests_inside, [], f"{d}/{entry}")
                for init in sub.rglob("__init__.py"):
                    self.assertEqual(init.read_text(encoding="utf-8", errors="replace").strip(), "",
                                     init.relative_to(ROOT).as_posix())

    def test_grandchild_of_standalone_run_is_blocked(self):
        """결정 1030-09 지적 3: 단독 실행 중 시험이 env=dict(os.environ) 로 띄운 하위 프로세스도 막힌다."""
        r = self.run_py("-c", CHILD_STANDALONE_GRANDCHILD, log=False)
        self.assertEqual(r.returncode, 0, r.stdout[-800:])
        self.assertIn("env NETGUARD=1 guard_dir_once=True", r.stdout)
        self.assertIn("grandchild installed=True", r.stdout)
        self.assertIn("grandchild BLOCKED NetguardBlocked", r.stdout)
        self.assertIn("grandchild rc=0", r.stdout)  # 하위 프로세스 판정은 게이트 줄 판정 규칙(종료 코드 바꾸지 않음)
        self.assertIn("grandchild_log_absent=True", r.stdout)


class TestExpectedBlocksUsage(unittest.TestCase):
    """차단 기록 되돌리기 헬퍼는 일부러 차단을 확인하는 시험 3곳에서만 쓴다(남용 시 종료 코드 판정이 무력해짐)."""

    ALLOWED = {"tests/regressions/test_00_netguard_active.py", "tests/v2/test_00_netguard_active.py",
               "tests/regressions/test_r_2026_10_30_netguard.py"}
    NAMES = ("expected_blocks", "_BLOCKED", "_EXIT_HOOK", "_exit_if_blocked")
    PAT = re.compile(r"\b(" + "|".join(NAMES) + r")\b")  # 단어 경계 — 비슷한 이름은 걸지 않음

    def test_only_allowed_files_use_reset_helper(self):
        users = set()
        for p in (ROOT / "tests").rglob("*.py"):
            rel = p.relative_to(ROOT).as_posix()
            if rel.startswith("tests/_netguard/") or "__pycache__" in rel:
                continue
            src = p.read_text(encoding="utf-8", errors="replace")
            if self.PAT.search(src):
                users.add(rel)
        self.assertEqual(users, self.ALLOWED)
        for p in (ROOT / "scripts").rglob("*"):
            if p.is_file() and p.suffix in (".py", ".sh"):
                src = p.read_text(encoding="utf-8", errors="replace")
                self.assertFalse(self.PAT.search(src), p.name)


if __name__ == "__main__":
    unittest.main()
