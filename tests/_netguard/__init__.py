"""시험 패키지용 바깥 연결 차단 켜기 (1030-09) — 본체는 guard.py.

tests/regressions/__init__.py · tests/v2/__init__.py 가 activate() 를 불러 게이트 밖 단독 실행
(`python3 -m unittest tests.regressions.X`, `discover -s tests/v2 -t .` 등)에서도 차단을 켠다.
NETGUARD 환경 변수와 무관하게 켜며, 끄는 탈출구는 두지 않는다(결정 1030-09).
시험은 python3 -m unittest 로만 돌린다(파일 직접 실행 `python3 tests/.../test_x.py` 금지 — 패키지를 안 거쳐 차단이 안 켜질 수 있다).
"""
import contextlib
import importlib.util
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_MOD = "_tradebot_netguard_guard"  # sitecustomize.py 와 같은 이름 — 한 프로세스에서 한 번만 읽음

PLACEHOLDER = "netguard-placeholder"


def _load_guard():
    mod = sys.modules.get(_MOD)
    if mod is None:
        spec = importlib.util.spec_from_file_location(_MOD, os.path.join(_HERE, "guard.py"))
        mod = importlib.util.module_from_spec(spec)
        sys.modules[_MOD] = mod
        spec.loader.exec_module(mod)
    return mod


@contextlib.contextmanager
def expected_blocks():
    """일부러 차단을 확인하는 시험 3곳 전용 — guard.expected_blocks 참고(다른 시험에서 쓰면 정적 시험이 실패)."""
    with _load_guard().expected_blocks():
        yield


def activate() -> None:
    """차단을 켜고(이미 켜져 있으면 그대로) 업비트 키를 자리표시 값으로 덮어쓴다.

    덮어쓰기: config.py 의 load_dotenv() 는 이미 있는 환경 변수를 바꾸지 않으므로, 여기서 넣으면
    .env 의 실키가 시험 프로세스에 읽히지 않는다. 실키가 환경에 이미 있어도 시험 패키지에서는 덮어쓴다.
    단 config.py 는 st.secrets(.streamlit/secrets.toml)를 먼저 읽으므로 그 파일에 키가 있으면 그 값이
    쓰인다 — 그 경우에도 연결은 차단 장치가 막는다.
    """
    g = _load_guard()
    g.install()
    g.register_exit_check()  # 차단이 있었으면 끝날 때 요약 줄 + 종료 코드 1 (결정 1030-09)
    os.environ["UPBIT_ACCESS"] = PLACEHOLDER
    os.environ["UPBIT_SECRET"] = PLACEHOLDER
    # 시험이 띄우는 하위 프로세스(env=dict(os.environ) 등)도 sitecustomize 경로로 막히게 전파한다.
    # NETGUARD_LOG 는 만들지 않는다(없으면 stderr 만). 하위 프로세스 판정은 게이트 줄 판정 규칙 그대로.
    os.environ["NETGUARD"] = "1"
    parts = [p for p in os.environ.get("PYTHONPATH", "").split(os.pathsep) if p]
    if not any(os.path.realpath(p) == os.path.realpath(_HERE) for p in parts):
        os.environ["PYTHONPATH"] = os.pathsep.join([_HERE, *parts])
