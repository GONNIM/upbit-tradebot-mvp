"""게이트 전용 시작 훅 (1030-09) — 본체는 guard.py.

scripts/regression_gate.sh 가 PYTHONPATH 앞에 이 폴더를 붙이고 NETGUARD=1 을 주면 python 이 시작할 때
이 파일을 읽어 바깥 연결 차단을 켠다. 이 파일이 가린 원래 sitecustomize(배포판 것 등)는 이어서 읽는다.
"""
import importlib.machinery
import importlib.util
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_MOD = "_tradebot_netguard_guard"


def _load_guard():
    mod = sys.modules.get(_MOD)
    if mod is None:
        spec = importlib.util.spec_from_file_location(_MOD, os.path.join(_HERE, "guard.py"))
        mod = importlib.util.module_from_spec(spec)
        sys.modules[_MOD] = mod
        spec.loader.exec_module(mod)
    return mod


def _chain_next_sitecustomize():
    rest = [p for p in sys.path if os.path.abspath(p or ".") != _HERE]
    spec = importlib.machinery.PathFinder.find_spec("sitecustomize", rest)
    if spec is None or spec.loader is None:
        return
    try:
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    except Exception as e:  # 원래 동작과 같게 실패는 경고만
        sys.stderr.write(f"[netguard] chained sitecustomize failed: {type(e).__name__}\n")


if os.environ.get("NETGUARD") == "1":
    _load_guard().install()
_chain_next_sitecustomize()
