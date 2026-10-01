"""
✅ WO-17 (C) 회귀: 범위 밖 주석 2곳 정정 — 실행 코드 무변경 고정 (2026-10-01)

정정 대상 (주석·docstring 만):
- core/rest_reconcile.py fetch_confirmed_candle docstring·본문 주석 "to 없음 → Upbit가 확정한 최신 봉만 반환"
- core/data_feed.py stream_candles 주석 "항상 최신 확정 봉만 조회"
실제로는 to 없음 = 형성 중 봉 포함(WO-15/16 실측). 확정 판정은 fetch_confirmed_candle 의 다음 봉 존재·재시도(Issue #8).

실행 코드 무변경 증명: 함수 AST(docstring 제거, 주석은 AST 에 없음) 해시를 정정 **전** 코드에서 계산해 고정.
이 해시가 바뀌면 Issue #8 함수(또는 stream_candles)의 실행 코드가 바뀐 것이다 — 의도한 변경이면 별도 승인 후 갱신.
G1(2026-10-01 승인): core/data_feed.py 로그 문자열 "(최신 확정 봉)" 은 바꾸지 않는다.

실행:
    python3 -m unittest tests.regressions.test_r_2026_10_01_wo17c_comment_only -v
"""
from __future__ import annotations

import ast
import hashlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

# 정정 전 코드(8bf7944)에서 계산한 실행 코드 해시
PINNED = {
    ("core/rest_reconcile.py", "fetch_confirmed_candle"): "2c47d11bc88dd0884e7b7c52306343bcfe8554453d07aac45fc2effde9f0d125",
    ("core/data_feed.py", "stream_candles"): "6cc132e6a60f900c37b1ab80203f5811f0efa6eb87cc987e899fdcca788c1d6f",
}


def _exec_hash(path: Path, name: str) -> str | None:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            for n in ast.walk(node):
                body = getattr(n, "body", None)
                if isinstance(body, list) and body and isinstance(body[0], ast.Expr) \
                        and isinstance(getattr(body[0], "value", None), ast.Constant) \
                        and isinstance(body[0].value.value, str):
                    body.pop(0)
            return hashlib.sha256(ast.dump(node, include_attributes=False).encode()).hexdigest()
    return None


class TestCommentOnly(unittest.TestCase):

    def test_1_exec_code_unchanged(self):
        """두 함수의 실행 코드(AST, docstring 제외)가 정정 전과 같음."""
        for (rel, name), h in PINNED.items():
            self.assertEqual(_exec_hash(ROOT / rel, name), h, f"{rel}:{name} 실행 코드가 바뀜")

    def test_2_wording(self):
        """옛 오해 문구 제거, 새 문구 존재, G1 로그 문자열은 유지."""
        rr = (ROOT / "core" / "rest_reconcile.py").read_text(encoding="utf-8")
        df = (ROOT / "core" / "data_feed.py").read_text(encoding="utf-8")
        self.assertNotIn("Upbit가 확정한 최신 봉만 반환", rr)
        self.assertNotIn("항상 최신 확정 봉만 조회", df)
        self.assertIn("형성 중 봉 포함 최신 봉 반환", rr)
        self.assertIn("형성 중 봉 포함 가능 (확정 판정은 호출부 책임", df)
        self.assertIn('f"count={need} (최신 확정 봉)"', df)   # G1: 로그 문자열 미변경


if __name__ == "__main__":
    unittest.main()
