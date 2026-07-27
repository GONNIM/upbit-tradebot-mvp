"""
✅ [Phase 2] F3 회귀: set_buy_sell_conditions 세션 stale state (커밋 43eecb1, 2026-07-24)

원 결함: 사용자가 과거 세션에서 100% 버튼 클릭 → st.session_state["order_ratio_quick"]=1.0
잔존. 나중에 다른 세션/UI 에서 params.order_ratio=0.01 로 변경. 원 세션 A로 돌아와
TP/SL/ticker 만 저장 시 save_conditions 가 `abs(0.01 - 1.0) > eps` 감지 → order_ratio 를
1.0 으로 덮어씀. 다음 매수 hot-reload 100% 매수 재발 (실측 07-22 21:50).

봉쇄 방식:
1) 주문 비율 버튼 클릭 시 즉시 save_params() (통합 폼과 분리).
2) save_conditions() 에서 order_ratio 처리 로직 완전 제거.

실행:
    python3 -m unittest tests.regressions.test_r_2026_07_24_conditions_stale_state -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


SETPAGE_PATH = Path(__file__).parent.parent.parent / "pages" / "set_buy_sell_conditions.py"


class TestConditionsStaleState(unittest.TestCase):
    """F3: 통합 저장 폼에서 order_ratio 처리 로직 제거 검증."""

    @classmethod
    def setUpClass(cls):
        with open(SETPAGE_PATH, "r", encoding="utf-8") as f:
            cls.source = f.read()

    def test_save_conditions_does_not_process_order_ratio(self):
        """save_conditions() 함수 안에서 order_ratio 필드 처리 완전 제거."""
        # save_conditions 함수 범위 추출
        start = self.source.find("def save_conditions()")
        self.assertGreater(start, -1, "save_conditions 함수 없음")
        # 다음 def 또는 최상위 코드까지
        end = self.source.find("\ndef ", start + 1)
        if end == -1:
            end = self.source.find("\n# ---", start + 1)
        block = self.source[start:end]

        # save_conditions 안에서 params_obj.order_ratio = 하는 코드 없어야 함
        # (버튼 콜백은 별도 함수/블록으로 분리됨)
        forbidden = "params_obj.order_ratio = new_ratio"
        self.assertNotIn(
            forbidden, block,
            f"'{forbidden}' 발견 → F3 재발. save_conditions 에서 order_ratio 처리 금지."
        )

    def test_ratio_changed_flag_removed_from_save_condition(self):
        """save 조건에 ratio_changed 포함되지 않아야 함 (order_ratio 저장 트리거 분리)."""
        # 이전 (버그) 코드: if ticker_changed or tp_changed or sl_changed or ratio_changed:
        # 새 코드: if ticker_changed or tp_changed or sl_changed:
        start = self.source.find("def save_conditions()")
        end = self.source.find("\ndef ", start + 1)
        if end == -1:
            end = self.source.find("\n# ---", start + 1)
        block = self.source[start:end]

        self.assertNotIn(
            "or ratio_changed", block,
            "save_conditions 저장 조건에 ratio_changed 있음 → F3 재발."
        )

    def test_ratio_button_click_saves_immediately(self):
        """
        주문 비율 버튼 클릭 시 즉시 save_params() 호출 로직 존재.
        (통합 폼 저장과 분리하여 stale 세션 개입 원천 봉쇄)
        """
        # 버튼 콜백에서 save_params 직접 호출 or _p_now.order_ratio 세팅
        # 실제 코드: save_params(_p_now, params_file, ...)
        # 하이라이트 기준: RATIO_OPTIONS 순회 + button 클릭 → save_params
        self.assertIn("RATIO_OPTIONS", self.source,
                     "RATIO_OPTIONS 정의 없음. 주문 비율 버튼 로직 실종 의심.")
        # 클릭 콜백에서 즉시 저장
        self.assertIn("save_params", self.source,
                     "save_params 호출 없음. 버튼 클릭 즉시 저장 로직 실종.")

    def test_saved_ratio_uses_disk_value_for_highlight(self):
        """하이라이트 기준이 세션값이 아닌 디스크(saved_ratio) 값 사용."""
        # 이전 (버그) 코드: current_ratio = st.session_state.get("order_ratio_quick", ...)
        # 새 코드: saved_ratio = params_obj.order_ratio; is_selected = abs(saved_ratio - value)
        # 소스에 "abs(saved_ratio - value)" 있어야 함
        self.assertIn(
            "abs(saved_ratio - value)", self.source,
            "하이라이트 기준이 saved_ratio (disk) 사용해야 함. 세션값 사용 시 F3 재발."
        )

    def test_default_ratio_fallback_is_safe(self):
        """order_ratio getattr fallback default 가 안전값 (0.1 이하)."""
        # 이전 (버그) 코드: getattr(params_obj, "order_ratio", 1.0) or 1.0
        # 새 코드: getattr(params_obj, "order_ratio", 0.1) or 0.1
        # `or 1.0` 패턴 검사
        # (1.0 은 100% 매수 위험, 신규 사용자 default 로 부적절)
        self.assertNotIn(
            'getattr(params_obj, "order_ratio", 1.0)', self.source,
            "getattr fallback default 1.0 발견 → F3 재발 + 사용자 100% 매수 위험."
        )


if __name__ == "__main__":
    unittest.main()
