"""
✅ 회귀: UI 접힘 화이트리스트 원칙 (2026-08-05)

원 결함:
- f0c291a (2026-07-27) "dashboard-mobile-ux: 5개 정보 섹션 디폴트 접기" 커밋 시
  사용자가 자주 쓰는 액션 버튼(감사로그 뷰어 열기)까지 접힘 처리 → 사용자 관점 사라짐

봉쇄 원칙: 자주 쓰는 액션 버튼·상태 카드는 top-level 유지, 접힘 대상에서 제외.

본 회귀는 화이트리스트 (감사 뷰어 버튼, 설정 이동 버튼, 동기화 상태 카드, 헬스 배지)
가 대시보드 top-level 에 유지되는지 lint.

실행:
    python3 -m unittest tests.regressions.test_r_2026_08_05_ui_whitelist -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))


class TestTopLevelActionWhitelist(unittest.TestCase):
    """대시보드 자주 쓰는 액션이 top-level 노출 상태 유지되는지."""

    DASHBOARD = ROOT / "pages" / "dashboard.py"

    def test_audit_viewer_button_present(self):
        """감사 뷰어 열기 버튼: 화이트리스트."""
        src = self.DASHBOARD.read_text(encoding="utf-8")
        self.assertIn("🔍 감사로그 뷰어 열기", src, "감사 뷰어 버튼 사라짐")

    def test_settings_button_present(self):
        """설정 페이지 이동 버튼: 화이트리스트 (매매 설정 섹션 헤더 우측)."""
        src = self.DASHBOARD.read_text(encoding="utf-8")
        # dashboard.py 에서 "🛠️ 설정" 버튼 (매매 설정 헤더 우측)
        self.assertIn('key="btn_settings"', src, "매매 설정 이동 버튼 사라짐")

    def test_sync_status_card_present(self):
        """동기화 상태 카드: 옵션 C v2 항상 표시 유지."""
        src = self.DASHBOARD.read_text(encoding="utf-8")
        self.assertIn("🔄 동기화 상태", src, "동기화 상태 카드 사라짐")

    def test_health_badge_present(self):
        """시스템 헬스 배지: 사용자 실측 필수 지점."""
        src = self.DASHBOARD.read_text(encoding="utf-8")
        self.assertIn("헬스", src, "헬스 배지 관련 코드 사라짐 (매우 광범위 검색)")

    def test_engine_state_subheader_present(self):
        """🔧 엔진 상태 (실시간 운영 conditions) 헤더 top-level 유지."""
        src = self.DASHBOARD.read_text(encoding="utf-8")
        self.assertIn(
            'st.subheader("🔧 엔진 상태 (실시간 운영 conditions)")',
            src,
            "엔진 상태 top-level 헤더 사라짐 (expander 안으로 이동됐을 위험)",
        )


class TestExpanderPolicyLint(unittest.TestCase):
    """접힘 정책 lint — 자주 쓰는 액션이 expander 안에 직접 들어가지 않도록 감시.

    구체 lint: '🔍 감사로그 뷰어 열기' 버튼과 '🛠️ 설정' 버튼이 각각
    직전 컨텍스트에 st.columns / _audit_hdr_col / _settings_col 등이 있어야 함.
    """

    DASHBOARD = ROOT / "pages" / "dashboard.py"

    def _find_line(self, needle):
        for i, line in enumerate(self.DASHBOARD.read_text(encoding="utf-8").split("\n"), start=1):
            if needle in line:
                return i, line
        return None, None

    def test_audit_button_in_column_not_expander(self):
        """감사 뷰어 버튼 직전 컨텍스트에 헤더 컬럼(_audit_hdr_col) 필수."""
        src_lines = self.DASHBOARD.read_text(encoding="utf-8").split("\n")
        btn_line = None
        for i, line in enumerate(src_lines, start=1):
            if 'key="btn_audit_log"' in line:
                btn_line = i
                break
        self.assertIsNotNone(btn_line, "감사 버튼 라인 못 찾음")
        ctx = "\n".join(src_lines[max(0, btn_line - 10):btn_line])
        self.assertIn(
            "_audit_hdr_col",
            ctx,
            "감사 버튼이 헤더 컬럼 밖에 있음 — 접힘 위험 (f0c291a 유형 재발)",
        )

    def test_settings_button_in_column_not_expander(self):
        """설정 이동 버튼 직전 컨텍스트에 st.columns 유사 패턴 필수."""
        src_lines = self.DASHBOARD.read_text(encoding="utf-8").split("\n")
        btn_line = None
        for i, line in enumerate(src_lines, start=1):
            if 'key="btn_settings"' in line:
                btn_line = i
                break
        self.assertIsNotNone(btn_line, "설정 버튼 라인 못 찾음")
        ctx = "\n".join(src_lines[max(0, btn_line - 10):btn_line])
        # _settings_col2 or col2 등 columns 컨텍스트
        self.assertTrue(
            "_settings_col" in ctx or "col2:" in ctx,
            "설정 버튼이 columns 컨텍스트 밖에 있음 (접힘 위험)",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
