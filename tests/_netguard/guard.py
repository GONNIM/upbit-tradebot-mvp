"""시험 중 바깥 네트워크 차단 장치 본체 (1030-09).

켜는 길 두 가지 (둘 다 같은 이 파일을 모듈 이름 `_tradebot_netguard_guard` 로 한 번만 읽는다):
  1. 게이트: scripts/regression_gate.sh 가 PYTHONPATH 앞에 tests/_netguard 를 붙이고 NETGUARD=1 을
     주면 sitecustomize.py 가 모든 python 프로세스(하위 프로세스 포함) 시작 때 켠다.
  2. 단독 실행: tests/regressions·tests/v2 패키지 __init__ 가 tests._netguard.activate() 로 켠다
     (`python3 -m unittest tests.regressions.X` 등 게이트 밖 실행). 끄는 탈출구는 없다.
서버 엔진(systemd) 프로세스는 이 둘 어느 것도 거치지 않으므로 영향이 없다.

막는 것: 루프백(localhost·127.x·::1)과 유닉스 소켓을 뺀 모든 연결.
  - 업비트(*.upbit.com) · 외부 IP 조회(api.ipify.org · ifconfig.me · icanhazip.com) ·
    텔레그램(api.telegram.org) 을 포함해 이름이든 IP 숫자든 바깥이면 막는다.
  - 이름은 getaddrinfo(이름 풀이) 단계에서 막으므로 패킷이 나가기 전에 끝난다.
막으면: stderr 에 `[NETGUARD] blocked <분류> host=<호스트>` 한 줄을 찍고(키·헤더는 찍지 않음),
NETGUARD_LOG 가 있으면 그 파일에도 한 줄 덧붙인 뒤 NetguardBlocked 를 던진다.
예외가 시험 안에서 삼켜져도 게이트가 로그 파일·출력의 [NETGUARD] 줄로 실패시킨다.
"""
import atexit
import contextlib
import ipaddress
import os
import socket
import sys

_UPBIT_SUFFIX = "upbit.com"
_IP_LOOKUP_HOSTS = {"api.ipify.org", "ifconfig.me", "icanhazip.com"}
_TELEGRAM_HOSTS = {"api.telegram.org"}
_LOCAL_NAMES = {"localhost", "localhost.localdomain", "ip6-localhost", "ip6-loopback"}


class NetguardBlocked(RuntimeError):
    """시험 중 바깥 연결 시도 (OSError 가 아니어서 requests 가 네트워크 오류로 감추지 못한다)."""


def _norm(host):
    if isinstance(host, bytes):
        host = host.decode("ascii", "replace")
    return str(host).strip().rstrip(".").lower()


def _is_local(host) -> bool:
    if host is None:
        return True  # getaddrinfo(None, port) = 루프백·바인드용
    h = _norm(host)
    if h == "" or h in _LOCAL_NAMES or h.endswith(".localhost"):
        return True
    try:
        ip = ipaddress.ip_address(h.split("%", 1)[0])
    except ValueError:
        return False
    return ip.is_loopback or ip.is_unspecified


def _category(h: str) -> str:
    if h == _UPBIT_SUFFIX or h.endswith("." + _UPBIT_SUFFIX):
        return "upbit"
    if h in _IP_LOOKUP_HOSTS:
        return "ip-lookup"
    if h in _TELEGRAM_HOSTS:
        return "telegram"
    return "external"


_BLOCKED = []  # 이 프로세스에서 막은 줄 (종료 판정용)
_EXIT_HOOK = []  # atexit 등록 여부 (한 번만)


def blocked_lines() -> list:
    return list(_BLOCKED)


@contextlib.contextmanager
def expected_blocks():
    """일부러 차단을 확인하는 시험 전용: 블록 안에서 생긴 차단 기록을 끝날 때 되돌린다.

    정적 시험(test_r_2026_10_30_netguard.TestExpectedBlocksUsage)이 허용된 시험 3곳 밖의 사용을 막는다.
    stderr·NETGUARD_LOG 의 줄은 되돌리지 않는다(게이트용 로그는 호출한 시험이 따로 돌린다).
    """
    n = len(_BLOCKED)
    try:
        yield
    finally:
        del _BLOCKED[n:]


def _exit_if_blocked():
    if not _BLOCKED:
        return
    try:
        sys.stdout.flush()
        sys.stderr.write(f"[NETGUARD] summary: {len(_BLOCKED)} blocked connection attempt(s) in pid={os.getpid()}"
                         " — process exits 1 (1030-09)\n")
        for ln in sorted(set(_BLOCKED)):
            sys.stderr.write("  " + ln + "\n")
        sys.stderr.flush()
    finally:
        os._exit(1)


def register_exit_check() -> None:
    """프로세스가 끝날 때 차단이 한 번이라도 있었으면 요약 줄을 찍고 종료 코드 1로 끝낸다(삼킨 예외 대비)."""
    if not _EXIT_HOOK:
        atexit.register(_exit_if_blocked)
        _EXIT_HOOK.append(True)


def _block(host, where: str):
    h = _norm(host)
    line = f"[NETGUARD] blocked {_category(h)} host={h} via={where} pid={os.getpid()}"
    _BLOCKED.append(line)
    try:
        sys.stderr.write(line + "\n")
        sys.stderr.flush()
    except Exception:
        pass
    log = os.environ.get("NETGUARD_LOG")
    if log:
        try:
            with open(log, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass
    raise NetguardBlocked(line)


def install() -> bool:
    """바깥 연결 차단을 켠다. 이미 켜져 있으면(같은 프로세스) 두 번 감싸지 않는다. 새로 켰으면 True."""
    if getattr(socket, "_netguard_installed", False):
        return False
    real_getaddrinfo = socket.getaddrinfo
    real_gethostbyname = socket.gethostbyname
    real_gethostbyname_ex = socket.gethostbyname_ex
    real_create_connection = socket.create_connection
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex

    def getaddrinfo(host, *args, **kwargs):
        if not _is_local(host):
            _block(host, "getaddrinfo")
        return real_getaddrinfo(host, *args, **kwargs)

    def gethostbyname(host):
        if not _is_local(host):
            _block(host, "gethostbyname")
        return real_gethostbyname(host)

    def gethostbyname_ex(host):
        if not _is_local(host):
            _block(host, "gethostbyname_ex")
        return real_gethostbyname_ex(host)

    def create_connection(address, *args, **kwargs):
        if isinstance(address, tuple) and address and not _is_local(address[0]):
            _block(address[0], "create_connection")
        return real_create_connection(address, *args, **kwargs)

    def _check_sock(sock, address, where):
        if sock.family in (socket.AF_INET, socket.AF_INET6) and isinstance(address, tuple) and address:
            if not _is_local(address[0]):
                _block(address[0], where)

    def connect(self, address):
        _check_sock(self, address, "connect")
        return real_connect(self, address)

    def connect_ex(self, address):
        _check_sock(self, address, "connect_ex")
        return real_connect_ex(self, address)

    socket.getaddrinfo = getaddrinfo
    socket.gethostbyname = gethostbyname
    socket.gethostbyname_ex = gethostbyname_ex
    socket.create_connection = create_connection
    socket.socket.connect = connect
    socket.socket.connect_ex = connect_ex
    socket._netguard_installed = True
    return True


