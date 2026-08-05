"""
✅ 회귀: 설정 저장 필드가 요약 섹션·대시보드 두 곳 모두에 표시되는지 lint 검증
   (2026-08-05, 커밋 [pending])

원 결함:
- `use_fixed_trailing` (Trailing Stop 방식 — Peak-based vs Fixed/Profit-based)
- `fixed_price_buy_wait_bars` (고정가 매수 대기 봉수, 기본 3)
두 필드 모두 conditions JSON 에 저장은 되지만, 설정 페이지 "⚙️ 현재 설정 요약"
섹션과 대시보드 어디에도 표시되지 않아 사용자가 활성 방식/timeout 을 UI 에서
확인할 수 없었음. 특히 use_fixed_trailing 은 Issue #7 관련 매도 로직 스위치.

봉쇄:
- pages/set_buy_sell_conditions.py 요약 섹션(col2 trailing_stop 캡션) 에 방식 표시
- pages/dashboard.py 매도 expander 아래 st.info 로 방식/임계값 표시
- pages/dashboard.py 매수 expander 아래 st.info 로 wait_bars 표시
- pages/dashboard.py 파라미터 metric 패널에도 두 필드 노출

본 테스트는 두 소스 모두에서 두 필드 문자열이 실제 참조되는지 lint 로 검증.
UI 렌더 정확성은 lint 로 커버 못 함 (브라우저 실측 필수, [[ui-render-measurement]]).

실행:
    python3 -m unittest tests.regressions.test_r_2026_08_05_ui_field_visibility -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))


class TestUIFieldVisibility(unittest.TestCase):
    """두 필드가 요약 섹션(set_buy_sell_conditions) + 대시보드 두 곳에서 참조되는지 검증."""

    SETTINGS_PAGE = ROOT / "pages" / "set_buy_sell_conditions.py"
    DASHBOARD = ROOT / "pages" / "dashboard.py"

    FIELDS = ("use_fixed_trailing", "fixed_price_buy_wait_bars")

    def test_settings_page_references_both_fields(self):
        src = self.SETTINGS_PAGE.read_text(encoding="utf-8")
        for field in self.FIELDS:
            self.assertIn(
                field,
                src,
                f"{self.SETTINGS_PAGE.name} 에서 '{field}' 참조 사라짐 — 요약 섹션 표시 회귀 의심",
            )

    def test_dashboard_references_both_fields(self):
        src = self.DASHBOARD.read_text(encoding="utf-8")
        for field in self.FIELDS:
            self.assertIn(
                field,
                src,
                f"{self.DASHBOARD.name} 에서 '{field}' 참조 사라짐 — 대시보드 표시 회귀 의심",
            )

    def test_settings_summary_references_ts_mode_label(self):
        """요약 섹션에 TS 방식 라벨(Fixed/Profit-based, Peak-based) 참조 검증."""
        src = self.SETTINGS_PAGE.read_text(encoding="utf-8")
        self.assertIn("Fixed/Profit-based", src, "요약 섹션 TS 방식 라벨 사라짐")
        self.assertIn("Peak-based", src, "요약 섹션 TS 방식 라벨 사라짐")

    def test_dashboard_references_ts_mode_label(self):
        """대시보드에 TS 방식 라벨 참조 검증."""
        src = self.DASHBOARD.read_text(encoding="utf-8")
        self.assertIn("Fixed/Profit-based", src, "대시보드 TS 방식 라벨 사라짐")
        self.assertIn("Peak-based", src, "대시보드 TS 방식 라벨 사라짐")

    def test_settings_summary_shows_sl_tp_ts_thresholds(self):
        """요약 섹션에 SL/TP/TS 임계값 캡션 병기가 남아있는지 검증."""
        src = self.SETTINGS_PAGE.read_text(encoding="utf-8")
        # SL/TP/TS 임계값 캡션 세션 키
        for k in ("stop_loss_pct", "take_profit_pct", "trailing_stop_threshold_pct"):
            self.assertIn(
                k,
                src,
                f"요약 섹션 임계값 표시용 세션 키 '{k}' 참조 사라짐",
            )


class TestConditionsLoadSaveSymmetry(unittest.TestCase):
    """
    ✅ 2026-08-05 오후 발견 결함:
    save_conditions() 가 저장하는 조건부 파라미터를 load_conditions() 가 세션에
    로드하지 않아, 파일값(5) vs 세션값(3) 이 어긋난 상태로 사용자에게 3봉으로
    표시되던 결함(원인: fixed_price_buy_wait_bars 세션 로드 누락).

    본 회귀는 save 되는 모든 조건부 파라미터가 load_conditions 함수 소스 내에서
    세션 assignment 또는 setdefault 로 반드시 로드되는지 lint.
    """

    SETTINGS_PAGE = ROOT / "pages" / "set_buy_sell_conditions.py"

    # save_conditions() 가 conditions JSON 에 넣는 조건부/필수 파라미터.
    # (BUY_CONDITIONS/SELL_CONDITIONS bool 키는 for-loop 로 일괄 처리되므로 제외.)
    CONDITIONAL_PARAMS = (
        "surge_threshold_pct",
        "fixed_price_buy_wait_bars",
        "stale_hours",
        "stale_threshold_pct",
        "stop_loss_pct",
        "take_profit_pct",
        "trailing_stop_threshold_pct",
        "use_fixed_trailing",
    )

    def _extract_function_source(self, src: str, func_name: str) -> str:
        """단순 파이썬 함수 소스 슬라이스 — def 부터 다음 top-level 정의 직전까지."""
        lines = src.split("\n")
        start = None
        for i, line in enumerate(lines):
            if line.startswith(f"def {func_name}("):
                start = i
                break
        if start is None:
            raise AssertionError(f"{func_name} 함수를 소스에서 찾지 못함")
        end = len(lines)
        for i in range(start + 1, len(lines)):
            line = lines[i]
            if line and not line[0].isspace() and (
                line.startswith("def ") or line.startswith("class ") or not line.startswith("#")
            ):
                end = i
                break
        return "\n".join(lines[start:end])

    def test_all_save_params_are_loaded_into_session(self):
        """save_conditions 가 저장하는 조건부 파라미터가 load_conditions 안에서 세션에 로드되는지."""
        src = self.SETTINGS_PAGE.read_text(encoding="utf-8")
        load_src = self._extract_function_source(src, "load_conditions")
        missing = []
        for key in self.CONDITIONAL_PARAMS:
            # 세션 assignment 또는 setdefault 형태로 등장하는지 검사
            patterns = (
                f'st.session_state["{key}"]',
                f"st.session_state['{key}']",
                f'setdefault("{key}"',
                f"setdefault('{key}'",
            )
            if not any(p in load_src for p in patterns):
                missing.append(key)
        self.assertEqual(
            missing,
            [],
            "load_conditions() 에서 세션 로드 누락 (파일값과 세션값 stale 위험): "
            + ", ".join(missing),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
