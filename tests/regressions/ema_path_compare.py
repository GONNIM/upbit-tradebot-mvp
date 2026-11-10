"""
1109 눌림목 실계좌 열기 — 「EMA·MACD 실매매 경로 불변」 바이트 고정 시험의 새 기준 (축소안 F).

지금까지는 `git show <기준 커밋>:<파일>` 과 바이트가 같은지로 고정했다. 눌림목 실계좌를 열려면 공용 파일 5개
(core/strategy_engine.py · core/trader.py · core/position_state.py · engine/live_loop.py · engine/engine_manager.py)를
PULLBACK 분기 안에서 고쳐야 한다. 커밋 없이는 기준 커밋을 옮길 수 없으므로(이 변경은 아직 커밋 전), 이 5개만 바이트 비교 대신
아래 규칙의 AST(구문 트리) 비교로 바꾼다. 나머지 파일은 지금처럼 바이트 비교 그대로다.

규칙 — 기준 원본과 지금 파일을 비교해서 아래 밖의 차이가 하나라도 있으면 실패:
  1. 함수·메서드 이름(클래스 경로 포함)에 「pullback」 이 들어가면 비교에서 뺀다(눌림목 전용 — 지금까지의 시험과 같은 규칙).
  2. SHARED: EMA·MACD 도 타는 공용 함수 중 일부러 고친 것. 모두 선택 인자·눌림목 전용 분기만 더했고, 기본 호출(EMA)의 동작이
     같다는 것은 test_r_2026_11_09_ema_trace(호출 흔적 비교)가 따로 본다.
       core/strategy_engine.StrategyEngine._reconcile_position_with_wallet : 선택 인자 wallet_qty(기본 None = 옛 읽기)
       core/position_state.PositionState.sync_from_wallet                   : 선택 인자 wallet_qty(기본 None = 옛 읽기)
       core/trader.UpbitTrader.buy_market                                    : strict_amount(눌림목) 분기 안에 불확실 응답 처리 1블록
  3. STRIP_IF: 함수 안의 `x == "PULLBACK"`(또는 그것으로 시작하는 `and` 묶음) if 의 **body 만** 양쪽에서 빼고 else 는 남겨 비교한다
     (엔진 관리자 _engine_runner · 매매 루프 run_live_loop). 혼합 조건(or 등)은 지우지 않는다 — verifier 지적 3 으로 고침.
  4. 새 함수는 pullback 이름이거나 NEW_OK(core/trader.UpbitTrader.coin_balance_checked · core/trader._upbit_order_uncertain)뿐.
  5. 함수 밖 문장(모듈·클래스 수준)은 「pullback」·「_pb_」 가 들어간 것을 빼고 그대로여야 한다.
"""
from __future__ import annotations

import ast
import subprocess
from pathlib import Path
from typing import Dict, List, Set

ROOT = Path(__file__).resolve().parent.parent.parent

LIVE_OPEN_FILES = {
    "core/strategy_engine.py", "core/trader.py", "core/position_state.py", "engine/live_loop.py",
    "engine/engine_manager.py",
}
SHARED = {
    "core/strategy_engine.py": {"StrategyEngine._reconcile_position_with_wallet"},
    "core/position_state.py": {"PositionState.sync_from_wallet"},
    "core/trader.py": {"UpbitTrader.buy_market"},
}
STRIP_IF = {
    "engine/engine_manager.py": {"EngineManager._engine_runner"},
    "engine/live_loop.py": {"run_live_loop"},
}
NEW_OK = {
    "core/trader.py": {"UpbitTrader.coin_balance_checked", "_upbit_order_uncertain"},
}


def _is_pullback_name(q: str) -> bool:
    low = q.lower()
    return "pullback" in low or "_pb_" in low


class _StripPullbackIf(ast.NodeTransformer):
    """`x == "PULLBACK"` 단일 비교(또는 그것으로 시작하는 `and` 묶음)가 test 인 If 문의 **body 만** 지우고 orelse 는 남긴다.
    orelse 는 EMA·MACD 가 타는 길이라 비교에 남아야 한다. 그 밖의 모양(혼합 조건 등)은 건드리지 않는다."""

    @staticmethod
    def _is_eq_pullback(t) -> bool:
        return (isinstance(t, ast.Compare) and len(t.ops) == 1 and isinstance(t.ops[0], ast.Eq)
                and any(isinstance(n, ast.Constant) and n.value == "PULLBACK" for n in [t.left, *t.comparators]))

    def _single(self, test) -> bool:
        if self._is_eq_pullback(test):
            return True
        return (isinstance(test, ast.BoolOp) and isinstance(test.op, ast.And) and self._is_eq_pullback(test.values[0]))

    def visit_If(self, node):
        self.generic_visit(node)
        if self._single(node.test):
            return node.orelse or None          # body 만 지우고 orelse 는 그 자리에 남김
        return node


def _walk(body, prefix: str, funcs: Dict[str, ast.AST], stmts: List[str], rel: str) -> None:
    for ch in body:
        if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef)):
            funcs[prefix + ch.name] = ch
        elif isinstance(ch, ast.ClassDef):
            if _is_pullback_name(prefix + ch.name):
                continue
            _walk(ch.body, prefix + ch.name + ".", funcs, stmts, rel)
        elif isinstance(ch, ast.Expr) and isinstance(getattr(ch, "value", None), ast.Constant) \
                and isinstance(ch.value.value, str):
            continue                                   # 모듈·클래스 docstring
        else:
            text = ast.unparse(ch)
            if _is_pullback_name(text):
                continue
            stmts.append(prefix + ":" + ast.dump(ch))


def ema_path_diff(rel: str, base_src: str, now_src: str) -> List[str]:
    """규칙 위반 목록(비어 있으면 EMA 경로 구문이 같다)."""
    out: List[str] = []
    shared = SHARED.get(rel, set())
    strip = STRIP_IF.get(rel, set())
    new_ok = NEW_OK.get(rel, set())
    parsed = {}
    for tag, src in (("base", base_src), ("now", now_src)):
        funcs: Dict[str, ast.AST] = {}
        stmts: List[str] = []
        _walk(ast.parse(src).body, "", funcs, stmts, rel)
        parsed[tag] = (funcs, stmts)
    bf, bs = parsed["base"]
    nf, ns = parsed["now"]
    for q in sorted(set(bf) | set(nf)):
        if _is_pullback_name(q) or q in shared:
            continue
        if q not in nf:
            out.append(f"함수가 사라짐: {q}")
        elif q not in bf:
            if q not in new_ok:
                out.append(f"허용되지 않은 새 함수: {q}")
        else:
            a, b = bf[q], nf[q]
            if q in strip:
                a, b = _StripPullbackIf().visit(ast.parse(ast.unparse(a))), _StripPullbackIf().visit(ast.parse(ast.unparse(b)))
            if ast.dump(a) != ast.dump(b):
                out.append(f"EMA 공용 함수가 달라짐: {q}")
    for q in sorted(shared):
        if q not in bf or q not in nf:
            out.append(f"SHARED 함수를 찾지 못함: {q}")
    if sorted(bs) != sorted(ns):
        out.append("함수 밖 문장이 달라짐(pullback·_pb_ 가 든 것 제외)")
    return out


def git_show(rel: str, commit: str):
    try:
        return subprocess.run(["git", "-C", str(ROOT), "show", f"{commit}:{rel}"],
                              capture_output=True, check=True, text=True).stdout
    except Exception:
        return None


def assert_unchanged(case, rel: str, commit: str) -> None:
    """고정 파일 한 개 확인: 공용 파일 5개는 위 규칙, 나머지는 기준 커밋과 바이트 같음."""
    base = git_show(rel, commit)
    if base is None:
        case.skipTest("git 기준 원본 없음")
    now = (ROOT / rel).read_text(encoding="utf-8")
    if rel in LIVE_OPEN_FILES:
        case.assertEqual(ema_path_diff(rel, base, now), [], f"{rel} 의 EMA·MACD 경로가 {commit} 와 다르다")
    else:
        case.assertEqual(now, base, rel)
