"""
✅ 회귀: 감사 뷰어 버튼 접근성 회귀 봉쇄 (2026-08-05)

원 결함:
- 커밋 f0c291a (2026-07-27) "dashboard-mobile-ux: 5개 정보 섹션 디폴트 접기"
  에서 감사로그 뷰어 열기 버튼이 `st.expander(expanded=False)` 안으로 들어감.
- 사용자 관점: expander 접혀있으면 버튼 안 보임 → "감사 뷰어 사라졌다"
- 개발자 관점: 소스에 st.button 여전히 존재 → 회귀 아니라 방어

봉쇄:
- pages/dashboard.py 재구성: 버튼은 헤더 우측 열에 항상 표시,
  필터 옵션(Only failed/Rows/Default Tab)만 별도 expander 접힘 유지.

본 회귀는 (1) 감사로그 버튼 문자열 존재, (2) 버튼이 필터 expander 밖에 있는지 lint.

실행:
    python3 -m unittest tests.regressions.test_r_2026_08_05_audit_viewer_accessibility -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))


class TestAuditViewerAccessibility(unittest.TestCase):
    DASHBOARD = ROOT / "pages" / "dashboard.py"

    def _button_line_and_expander_line(self):
        """감사 뷰어 버튼 라인 번호 + 그 이전 마지막 open expander 라인 번호."""
        src_lines = self.DASHBOARD.read_text(encoding="utf-8").split("\n")
        btn_line = None
        for i, line in enumerate(src_lines, start=1):
            if 'key="btn_audit_log"' in line:
                btn_line = i
                break
        return src_lines, btn_line

    def test_button_string_present(self):
        src = self.DASHBOARD.read_text(encoding="utf-8")
        self.assertIn(
            "🔍 감사로그 뷰어 열기",
            src,
            "감사 뷰어 버튼 문자열 사라짐 — 회귀",
        )

    def test_button_key_present(self):
        src = self.DASHBOARD.read_text(encoding="utf-8")
        self.assertIn(
            'key="btn_audit_log"',
            src,
            "감사 뷰어 버튼 key 사라짐 — 회귀",
        )

    def test_button_in_header_column_context(self):
        """버튼이 헤더 우측 컬럼(_audit_hdr_col2) 안에 있는지 검증 (접힘 expander 안이 아님).

        f0c291a 유형 재발 방지: 버튼을 expander 안에 넣어 사용자 관점 사라짐 방지.
        헤더 우측 컬럼 구조 유지 강제 — 후속 리팩터가 이 변수명을 유지해야 함.
        """
        src_lines = self.DASHBOARD.read_text(encoding="utf-8").split("\n")
        for i, line in enumerate(src_lines):
            if 'key="btn_audit_log"' in line:
                context_before = "\n".join(src_lines[max(0, i - 10):i])
                self.assertIn(
                    "_audit_hdr_col2",
                    context_before,
                    "감사 뷰어 버튼 직전 컨텍스트에 헤더 우측 컬럼(_audit_hdr_col2) 없음 "
                    "— f0c291a 유형 회귀 (expander 안으로 이동됐을 위험)",
                )
                return
        self.fail("감사 뷰어 버튼 라인 찾지 못함 — 버튼 자체 제거 회귀")

    def test_audit_viewer_page_exists(self):
        """네비게이션 타겟 pages/audit_viewer.py 존재 확인."""
        self.assertTrue(
            (ROOT / "pages" / "audit_viewer.py").exists(),
            "네비게이션 타겟 페이지 사라짐",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
