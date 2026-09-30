"""
✅ WO-11 회귀: 사용자 노출 용어 통일 (2026-09-30)

확정 용어 (docs/operations/terminology.md):
- 매수 방식: "시장가 매수" / "현재가 매수"
- 매도 방식: "시장가 매도" (옵션 없음) — 화면에 "매도는 항상 시장가로 체결됩니다" 명시
- 앱 주문: "앱 지정가 주문"
- 폐기: "고정가", 봇 옵션명으로서의 "지정가"

봉쇄 3층:
  1) 소스: 사용자 노출 코드의 문자열 상수(AST)에서 폐기 용어 0건 (logger 호출·docstring 제외)
  2) 표시층: 과거 DB 행의 옛 문구 → 새 문구 변환 (services.terminology)
  3) 렌더: 감사 로그 페이지·설정 페이지를 Streamlit AppTest 로 실제 렌더 → 화면 텍스트 폐기 용어 0건

실행:
    python3 -m unittest tests.regressions.test_r_2026_09_30_wo11_terminology -v
"""
from __future__ import annotations

import ast
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from services.terminology import display_text, display_rows, find_deprecated  # noqa: E402

# 사용자 노출 문자열을 만드는 파일 (화면·알림·logs 테이블)
USER_FACING_FILES = [
    "pages/dashboard.py",
    "pages/audit_viewer.py",
    "pages/set_buy_sell_conditions.py",
    "pages/settings_history.py",
    "core/trader.py",
    "engine/order_reconciler.py",
    "services/error_messages.py",
    "services/trading_control.py",
    "ui/sidebar.py",
]


def _user_facing_strings(path: Path) -> list[tuple[int, str]]:
    """파일의 문자열 상수 중 docstring·logger.* 호출 인자를 뺀 것 (줄번호, 값)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    skip: set[int] = set()
    for node in ast.walk(tree):
        # docstring
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant) \
                    and isinstance(body[0].value.value, str):
                skip.add(id(body[0].value))
        # logger.xxx(...) — 서버 로그(journal), 사용자 비노출
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and isinstance(node.func.value, ast.Name) and node.func.value.id in ("logger", "logging", "_logger"):
            for sub in ast.walk(node):
                skip.add(id(sub))
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in skip:
            out.append((node.lineno, node.value))
    return out


class TestSourceHasNoDeprecatedTerms(unittest.TestCase):

    def test_user_facing_strings(self):
        hits = []
        for rel in USER_FACING_FILES:
            for lineno, s in _user_facing_strings(ROOT / rel):
                for term in find_deprecated(s):
                    hits.append(f"{rel}:{lineno} [{term}] {s[:80]!r}")
        self.assertEqual(hits, [], "사용자 노출 문자열에 폐기 용어 잔존:\n" + "\n".join(hits))

    def test_required_guidance_present(self):
        settings = (ROOT / "pages" / "set_buy_sell_conditions.py").read_text(encoding="utf-8")
        self.assertIn("매도는 항상 시장가로 체결됩니다", settings)
        self.assertIn("신호 봉의 마감가로 주문을 걸고", settings)
        self.assertIn("시장가 매수", settings)
        dash = (ROOT / "pages" / "dashboard.py").read_text(encoding="utf-8")
        self.assertIn("현재가 매수 활성 상태. 강제 매수도 현재가로 발주되며", dash, "WO-8 caption 교체")
        # (WO-9 ⛔ 배지 문구는 WO-9 테스트가 검증 — 커밋별 단독 revert 가능하도록 분리)

    def test_code_keys_and_log_tags_kept(self):
        """코드 키·로그 태그는 유지 (문구만 교체)."""
        trader = (ROOT / "core" / "trader.py").read_text(encoding="utf-8")
        self.assertIn("[BUY-LIMIT]", trader)
        settings = (ROOT / "pages" / "set_buy_sell_conditions.py").read_text(encoding="utf-8")
        self.assertIn('"fixed_price_buy_enabled"', settings)
        tc = (ROOT / "services" / "trading_control.py").read_text(encoding="utf-8")
        self.assertIn("[FIXED-PRICE][FORCE]", tc)


class TestDisplayLayerMapping(unittest.TestCase):

    def test_old_log_rows_mapped(self):
        # 2026-09-30 운영 DB logs.message 9행과 같은 형식
        old = "🎯 [LIVE 고정가] 지정가 매수 요청: KRW-JTO price=767.0 qty=2097.5170824 uuid=4a848702"
        new = display_text(old)
        self.assertEqual(new, "🎯 [LIVE] 현재가 매수 주문 요청: KRW-JTO price=767.0 qty=2097.5170824 uuid=4a848702")
        self.assertEqual(find_deprecated(new), [])
        self.assertEqual(display_text("⏱ [FORCE] 강제 매수 지정가 미체결 → 자동 취소"),
                         "⏱ [FORCE] 강제 매수(현재가) 미체결 → 자동 취소")
        self.assertEqual(display_text("❌ 고정가 매수 거부 (KRW-JTO): x"), "❌ 현재가 매수 거부 (KRW-JTO): x")

    def test_app_limit_order_wording_untouched(self):
        for s in ("주문 가능 수량 부족 — 업비트 앱에서 직접 넣은 지정가 매도 주문이 있는지 확인하세요.",
                  "⛔ 매도 불가 — 앱 지정가 매도 주문으로 수량 묶임 (10.000000개)",
                  "업비트 앱에서 직접 넣은 지정가 매수 주문이 있는지"):
            self.assertEqual(display_text(s), s)
            self.assertEqual(find_deprecated(s), [])

    def test_display_rows(self):
        rows = [("2026-09-29T19:25:12", "INFO", "🎯 [LIVE 고정가] 지정가 매수 요청: KRW-JTO")]
        self.assertEqual(display_rows(rows)[0][2], "🎯 [LIVE] 현재가 매수 주문 요청: KRW-JTO")
        self.assertEqual(display_rows(None), [])


class _RenderCase(unittest.TestCase):
    USER = "test_r_2026_09_30_wo11"

    def setUp(self):
        import config  # noqa: F401  — .env/secrets 로드 후 cwd 이동
        import services.db  # noqa: F401
        import services.init_db  # noqa: F401
        import engine.params  # noqa: F401
        self._cwd = os.getcwd()
        self.tmpdir = Path(tempfile.mkdtemp(prefix="wo11_"))
        self.db_path = str(self.tmpdir / f"tradebot_{self.USER}.db")
        self._patchers = [
            patch("services.init_db.get_db_path", return_value=self.db_path),
            patch("services.db.get_db_path", return_value=self.db_path),
            patch("services.notifier.send", MagicMock(return_value=True)),
        ]
        for p in self._patchers:
            p.start()
        from services.init_db import initialize_db, ensure_all_schemas
        from services.db import ensure_schema
        initialize_db(self.USER)
        ensure_all_schemas(self.USER)
        ensure_schema(self.USER)
        os.chdir(self.tmpdir)

    def tearDown(self):
        os.chdir(self._cwd)
        for p in self._patchers:
            p.stop()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    @staticmethod
    def _all_text(at) -> str:
        texts = []
        for name in ("markdown", "caption", "info", "warning", "error", "success",
                     "title", "header", "subheader", "text"):
            texts += [str(getattr(e, "value", "")) for e in getattr(at, name)]
        for name in ("toggle", "number_input", "button", "checkbox", "selectbox",
                     "text_input", "expander", "multiselect", "radio"):
            texts += [str(getattr(e, "label", "")) for e in getattr(at, name)]
        for df in at.dataframe:
            v = df.value
            texts.append(" ".join(map(str, getattr(v, "columns", []))))
            texts.append(v.to_string() if hasattr(v, "to_string") else str(v))
        return "\n".join(texts)


class TestRenderedPagesHaveNoDeprecatedTerms(_RenderCase):

    def test_settings_page(self):
        (self.tmpdir / f"{self.USER}_EMA_buy_sell_conditions.json").write_text(json.dumps({
            "buy": {"ema_gc": True, "fixed_price_buy_enabled": True, "fixed_price_buy_wait_bars": 5},
            "sell": {"stop_loss": True, "ema_dc": True, "stop_loss_pct": 3.0},
        }), encoding="utf-8")
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(ROOT / "pages" / "set_buy_sell_conditions.py"), default_timeout=60)
        for k, v in dict(user_id=self.USER, mode="LIVE", strategy="EMA").items():
            at.query_params[k] = v
        at.session_state["user_id"] = self.USER
        at.run()
        self.assertEqual([e.value for e in at.exception], [])
        blob = self._all_text(at)
        self.assertEqual(find_deprecated(blob), [], "설정 페이지 렌더에 폐기 용어")
        for must in ("현재가 매수", "시장가 매수", "매도는 항상 시장가로 체결됩니다",
                     "신호 봉의 마감가로 주문을 걸고 5봉 기다립니다", "미체결이면 자동 취소됩니다"):
            self.assertIn(must, blob)

    def test_settings_summary_wait_minutes_from_interval(self):
        """요약 칸 대기 시간 = 봉 수 × interval_sec/60 (minute5·5봉 → 약 25분). ×60 하드코딩 금지."""
        from config import PARAMS_JSON_FILENAME
        (self.tmpdir / f"{self.USER}_EMA_buy_sell_conditions.json").write_text(json.dumps({
            "buy": {"ema_gc": True, "fixed_price_buy_enabled": True, "fixed_price_buy_wait_bars": 5},
            "sell": {"stop_loss": True, "ema_dc": True, "stop_loss_pct": 3.0},
        }), encoding="utf-8")
        from engine.params import _scoped_path  # 운영과 같은 전략별 파일명 (예: mcmax33_latest_params_EMA.json)
        (self.tmpdir / _scoped_path(f"{self.USER}_{PARAMS_JSON_FILENAME}", "EMA")).write_text(json.dumps({
            "ticker": "JTO", "interval": "minute5", "fast_period": 60, "slow_period": 200,
            "signal_period": 9, "take_profit": 0.05, "stop_loss": 0.03, "cash": 1000000,
            "commission": 0.0005, "order_ratio": 0.1, "strategy_type": "EMA",
        }), encoding="utf-8")
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(ROOT / "pages" / "set_buy_sell_conditions.py"), default_timeout=60)
        for k, v in dict(user_id=self.USER, mode="LIVE", strategy="EMA").items():
            at.query_params[k] = v
        at.session_state["user_id"] = self.USER
        at.run()
        self.assertEqual([e.value for e in at.exception], [])
        captions = [c.value for c in at.caption]
        self.assertIn("└─ 대기 봉수: 5봉 (약 25분)", [c.strip() for c in captions])
        self.assertFalse(any("300초" in c or "(약 5분)" in c for c in captions), "1분봉 가정 표기 잔존")

    def test_audit_viewer_trades(self):
        from services.db import insert_trade_audit
        # 과거 행 옛 문구 (표시층 변환 확인용) — WO-9 기능(거절 행·신규 열)에 의존하지 않음
        insert_trade_audit(self.USER, "KRW-JTO", 300, 1389, "BUY", "고정가 매수", 767.0, None, None,
                           None, None, None, None, None, None, None, None)
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(ROOT / "pages" / "audit_viewer.py"), default_timeout=60)
        for k, v in dict(user_id=self.USER, tab="trades", mode="LIVE", ticker="JTO").items():
            at.query_params[k] = v
        at.session_state["user_id"] = self.USER
        at.run()
        self.assertEqual([e.value for e in at.exception], [])
        blob = self._all_text(at)
        self.assertEqual(find_deprecated(blob), [], "감사 로그 페이지 렌더에 폐기 용어")
        self.assertIn("현재가 매수", blob, "옛 문구 '고정가 매수' → 새 문구로 표시")


if __name__ == "__main__":
    unittest.main()
