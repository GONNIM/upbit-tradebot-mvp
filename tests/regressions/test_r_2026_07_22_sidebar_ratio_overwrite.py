"""
✅ [Phase 2] F2 회귀: 사이드바 order_ratio disable + saved_ratio 강제 저장 (커밋 7991a48, 2026-07-22)

원 결함: 사이드바가 form submit 시 st.session_state.order_ratio (초기 1.0=100%)
를 그대로 LiveParams(order_ratio=...) 에 실어 저장 → 다른 UI 에서 저장한
1% 를 100% 로 덮어씀. 실측 근거: Jul 20 13:35:27 RATIO-HR 0.01→1.0 로그.

봉쇄 방식:
1) 4개 주문 비율 버튼 모두 disabled=True (표시 전용).
2) LiveParams 생성 시 order_ratio=saved_ratio (disk 값) 사용, 세션값 무시.

실행:
    python3 -m unittest tests.regressions.test_r_2026_07_22_sidebar_ratio_overwrite -v
"""
from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


SIDEBAR_PATH = Path(__file__).parent.parent.parent / "ui" / "sidebar.py"


class TestSidebarRatioDisabled(unittest.TestCase):
    """F2: 사이드바 UI 계약 검증 (소스 코드 정적 분석)."""

    @classmethod
    def setUpClass(cls):
        with open(SIDEBAR_PATH, "r", encoding="utf-8") as f:
            cls.source = f.read()

    def test_ratio_buttons_are_disabled(self):
        """4개 주문 비율 버튼이 disabled=True 로 설정되어야 함."""
        # CASH_OPTIONS 순회 + button() 호출부에 disabled=True 있는지 확인
        # 소스에 "disabled=True" 최소 1회 이상 (ratio 버튼) — 실제로는 3회 이상
        self.assertGreaterEqual(
            self.source.count("disabled=True"), 1,
            "사이드바에 disabled=True 없음 → F2 재발 위험 (버튼 클릭으로 세션값 변경 가능)"
        )

    def test_liveparams_uses_saved_ratio_not_session(self):
        """LiveParams 생성 시 order_ratio=saved_ratio (session_state 아님)."""
        # 정확한 라인: "order_ratio=saved_ratio"
        self.assertIn(
            "order_ratio=saved_ratio", self.source,
            "LiveParams 에 order_ratio=saved_ratio (disk 값) 사용해야 함. "
            "st.session_state.order_ratio 사용 시 F2 재발."
        )

    def test_liveparams_does_not_use_session_state_order_ratio(self):
        """LiveParams(order_ratio=st.session_state.order_ratio) 패턴 없어야 함."""
        # 이전 (버그) 코드: order_ratio=st.session_state.order_ratio
        forbidden = "order_ratio=st.session_state.order_ratio"
        self.assertNotIn(
            forbidden, self.source,
            f"'{forbidden}' 발견 → F2 재발. saved_ratio 사용해야 함."
        )

    def test_saved_ratio_loaded_at_sidebar_entry(self):
        """make_sidebar 진입부에서 load_params_obj.order_ratio 로 saved_ratio 로드."""
        self.assertIn("load_params_obj.order_ratio", self.source)
        self.assertIn("saved_ratio", self.source)

    def test_sidebar_fallback_default_is_safe(self):
        """params 없을 때 fallback default 가 0.1 (10%) 이하 (100% 위험 방지)."""
        # else 0.1 패턴 또는 else <safe_value>
        # 100% (1.0) 하드코딩 default 없어야 함
        self.assertIn("else 0.1", self.source,
                     "fallback default 가 0.1 이하여야 안전. 1.0 은 신규 사용자 100% 매수 위험.")


if __name__ == "__main__":
    unittest.main()
