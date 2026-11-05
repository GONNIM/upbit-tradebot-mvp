#!/usr/bin/env python3
"""
Page Navigation Hardening — SP-NAV-1~5 검증.

Streamlit runtime 실체 없이 검증 가능한 것:
- _get_param 순수 함수 (list/scalar/missing/default)
- _normalize_value 순수 함수 (mode 대문자화)
- navigate_to 의 필터 로직 (None/빈 문자열 제외, 0 유지)
- bootstrap_page_context 의 세션 이중 저장 흐름 (session_state / query_params mock)

Streamlit UI 실체가 필요한 검증(위젯·switch_page):
- Phase D walkthrough 문서 참조 (docs/plans/page-navigation-hardening/walkthrough.md)

실행:
    python3 -m unittest tests.test_page_navigation -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))


class _FakeQP(dict):
    """st.query_params dict-like 대체."""
    def get(self, key, default=None):
        return dict.get(self, key, default)


class TestGetParam(unittest.TestCase):
    """_get_param — URL query_params 값 획득."""

    def test_returns_scalar(self):
        from services.page_context import _get_param
        qp = _FakeQP(user_id="mcmax33")
        self.assertEqual(_get_param(qp, "user_id"), "mcmax33")

    def test_returns_default_when_missing(self):
        from services.page_context import _get_param
        qp = _FakeQP()
        self.assertEqual(_get_param(qp, "user_id", "fallback"), "fallback")

    def test_extracts_first_from_list(self):
        """Streamlit 이전 버전이 list 반환하는 케이스 방어 (교훈 #13)."""
        from services.page_context import _get_param
        qp = _FakeQP(mode=["LIVE"])
        self.assertEqual(_get_param(qp, "mode"), "LIVE")

    def test_empty_list_returns_default(self):
        from services.page_context import _get_param
        qp = _FakeQP(mode=[])
        self.assertEqual(_get_param(qp, "mode", "TEST"), "TEST")


class TestNormalizeValue(unittest.TestCase):
    """_normalize_value — 도메인 정규화."""

    def test_mode_uppercased(self):
        from services.page_context import _normalize_value
        self.assertEqual(_normalize_value("mode", "live"), "LIVE")
        self.assertEqual(_normalize_value("mode", "TEST"), "TEST")

    def test_mode_empty_pass_through(self):
        from services.page_context import _normalize_value
        # 빈 값은 그대로 (bootstrap 이 required 검증)
        self.assertEqual(_normalize_value("mode", ""), "")

    def test_non_mode_key_unchanged(self):
        from services.page_context import _normalize_value
        self.assertEqual(_normalize_value("user_id", "MCmax33"), "MCmax33")
        self.assertEqual(_normalize_value("virtual_krw", 500000), 500000)


class TestNavigateToFilter(unittest.TestCase):
    """navigate_to 의 필터 로직 — None/빈 제외, 0 유지."""

    def test_navigate_to_ignores_none_and_empty(self):
        """None 및 빈 문자열은 제외, 0 은 유지."""
        # Streamlit mock
        with patch("services.page_context.st") as mock_st:
            mock_st.session_state = {}
            mock_st.query_params = MagicMock()

            from services.page_context import navigate_to
            navigate_to(
                "pages/dashboard.py",
                user_id="mcmax33",
                mode="LIVE",
                virtual_krw=0,          # ← 0 은 유지
                empty_val="",           # ← 빈 문자열 제외
                none_val=None,          # ← None 제외
                strategy_type="EMA",
            )

            # session_state 이중 저장 검증
            self.assertEqual(mock_st.session_state["user_id"], "mcmax33")
            self.assertEqual(mock_st.session_state["mode"], "LIVE")
            self.assertEqual(mock_st.session_state["virtual_krw"], "0")
            self.assertNotIn("empty_val", mock_st.session_state)
            self.assertNotIn("none_val", mock_st.session_state)

            # query_params.update 호출 인자 검증
            mock_st.query_params.update.assert_called_once()
            update_arg = mock_st.query_params.update.call_args.args[0]
            self.assertEqual(update_arg["user_id"], "mcmax33")
            self.assertEqual(update_arg["virtual_krw"], "0")
            self.assertNotIn("empty_val", update_arg)
            self.assertNotIn("none_val", update_arg)

            # switch_page 호출 검증
            mock_st.switch_page.assert_called_once_with("pages/dashboard.py")


class TestBootstrapPageContext(unittest.TestCase):
    """bootstrap_page_context — 필수 검증 + 이중 저장."""

    def test_bootstrap_success_when_session_has_user_id(self):
        """session_state 에 user_id 있으면 정상 반환."""
        with patch("services.page_context.st") as mock_st:
            mock_st.session_state = {"user_id": "mcmax33", "mode": "LIVE"}
            mock_st.query_params = _FakeQP()

            from services.page_context import bootstrap_page_context
            ctx = bootstrap_page_context()

            self.assertEqual(ctx["user_id"], "mcmax33")
            self.assertEqual(ctx["mode"], "LIVE")
            # 이중 저장 확인
            self.assertEqual(mock_st.session_state["user_id"], "mcmax33")
            self.assertEqual(mock_st.session_state["mode"], "LIVE")
            # switch_page 호출 안 됨 (정상 진입)
            mock_st.switch_page.assert_not_called()

    def test_bootstrap_url_priority_over_session(self):
        """URL query_params 가 session_state 보다 우선."""
        with patch("services.page_context.st") as mock_st:
            mock_st.session_state = {"user_id": "session_user"}
            mock_st.query_params = _FakeQP(user_id="url_user", mode="LIVE")

            from services.page_context import bootstrap_page_context
            ctx = bootstrap_page_context()

            self.assertEqual(ctx["user_id"], "url_user")
            self.assertEqual(ctx["mode"], "LIVE")

    def test_bootstrap_redirects_when_user_id_missing(self):
        """user_id 부재 시 switch_page 호출 + st.stop."""
        with patch("services.page_context.st") as mock_st:
            mock_st.session_state = {}
            mock_st.query_params = _FakeQP()

            from services.page_context import bootstrap_page_context
            bootstrap_page_context()

            # 로그인 리다이렉트
            mock_st.warning.assert_called_once()
            mock_st.switch_page.assert_called_once_with("app.py")
            mock_st.stop.assert_called_once()

    def test_bootstrap_mode_normalized_uppercase(self):
        """mode 는 대문자로 정규화."""
        with patch("services.page_context.st") as mock_st:
            mock_st.session_state = {"user_id": "mcmax33"}
            mock_st.query_params = _FakeQP(mode="live")

            from services.page_context import bootstrap_page_context
            ctx = bootstrap_page_context()

            self.assertEqual(ctx["mode"], "LIVE")


class TestBuildContextParams(unittest.TestCase):
    """build_context_params — 세션 컨텍스트를 dict 로 추출."""

    def test_extracts_standard_keys(self):
        with patch("services.page_context.st") as mock_st:
            mock_st.session_state = {
                "user_id": "mcmax33",
                "mode": "LIVE",
                "strategy_type": "EMA",
                "virtual_krw": 500000,
                "verified": "1",
                "unrelated_key": "ignored",
            }
            from services.page_context import build_context_params
            result = build_context_params()

            self.assertEqual(result["user_id"], "mcmax33")
            self.assertEqual(result["mode"], "LIVE")
            self.assertEqual(result["strategy_type"], "EMA")
            self.assertEqual(result["virtual_krw"], 500000)
            self.assertNotIn("unrelated_key", result)

    def test_excludes_empty_but_keeps_zero(self):
        with patch("services.page_context.st") as mock_st:
            mock_st.session_state = {
                "user_id": "mcmax33",
                "mode": "",           # 빈 문자열 제외
                "virtual_krw": 0,     # 0 은 유지
                "strategy_type": None,  # None 제외
            }
            from services.page_context import build_context_params
            result = build_context_params()

            self.assertIn("user_id", result)
            self.assertIn("virtual_krw", result)
            self.assertNotIn("mode", result)
            self.assertNotIn("strategy_type", result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
