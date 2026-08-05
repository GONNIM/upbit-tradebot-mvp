"""
✅ 회귀: BACKFILL 재평가 격리 봉쇄 (2026-08-05, Issue #9/#11 강화)

원 결함 (2026-03 시절 최초 발생):
- Issue #9: BACKFILL 재평가가 중복 봉으로 판정되어 스킵됨 → audit UPDATE 안 됨
- Issue #11: BACKFILL 처리 중 실시간 지표(EMA/MACD/prev_*)가 오염 → Golden Cross 놓침

봉쇄 (기존 코드):
- engine/live_loop.py — BACKFILL 처리 전 12개 지표 필드 백업, 처리 후 복원
- core/strategy_engine.py — backfill_mode=True 시 execute() 스킵, bar_count 미증가

본 회귀는 위 봉쇄가 향후 리팩터로 깨지지 않도록 lint. 실제 함수 실행이 아닌
소스 문자열 기반이지만, 핵심 문자열이 사라지면 pre-push 게이트가 차단.

실행:
    python3 -m unittest tests.regressions.test_r_2026_08_05_backfill_isolation -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))


class TestBackfillExecutionIsolation(unittest.TestCase):
    """V2 격리: backfill_mode=True 시 실주문 스킵 + bar_count 격리."""

    STRATEGY_ENGINE = ROOT / "core" / "strategy_engine.py"

    def _read(self) -> str:
        return self.STRATEGY_ENGINE.read_text(encoding="utf-8")

    def test_backfill_mode_extracted_from_diff_summary(self):
        """diff_summary.get('backfill_mode', False) 추출 코드 존재."""
        src = self._read()
        self.assertIn(
            'backfill_mode = diff_summary.get("backfill_mode", False)',
            src,
            "backfill_mode 추출 코드 사라짐 — 격리 로직 붕괴 위험",
        )

    def test_backfill_skips_bar_count_increment(self):
        """`if not backfill_mode:` 안에서만 bar_count 증가 (버퍼 격리)."""
        src = self._read()
        self.assertIn(
            "if not backfill_mode:\n            self.buffer.append(bar)",
            src,
            "BACKFILL 시 버퍼 추가/bar_count 증가 격리 로직 사라짐 (Issue #9 재발 위험)",
        )
        # 3라인 뒤에 self.bar_count += 1 있어야
        self.assertIn(
            "self.bar_count += 1",
            src,
            "bar_count 증가 코드 자체 사라짐",
        )

    def test_backfill_skips_actual_execution(self):
        """`if not backfill_mode:` 안에서만 execute() 호출."""
        src = self._read()
        # execute 호출 조건 확인
        self.assertIn(
            "if not backfill_mode:",
            src,
            "backfill_mode 격리 if 문 사라짐",
        )
        self.assertIn(
            "self.execute(action, bar, ind_snapshot)",
            src,
            "execute 호출 자체 사라짐",
        )
        # BACKFILL 스킵 로그 마커
        self.assertIn(
            "[BACKFILL] 실제 주문 건너뜀",
            src,
            "BACKFILL 실주문 스킵 로그 사라짐 — 격리 붕괴 위험",
        )

    def test_backfill_audit_marks_via_backfill_flag(self):
        """_record_audit_log 호출 시 is_backfill=backfill_mode 전달."""
        src = self._read()
        self.assertIn(
            "self._record_audit_log(bar, ind_snapshot, action, is_backfill=backfill_mode)",
            src,
            "audit 로그 via_backfill 마킹 사라짐 — 재평가 구분 불가",
        )


class TestBackfillIndicatorSnapshot(unittest.TestCase):
    """V3 지표 복원 (Issue #11): 12개 필드 백업/복원 완결성."""

    LIVE_LOOP = ROOT / "engine" / "live_loop.py"

    # BACKFILL 백업/복원 대상 12개 지표 필드 (Issue #11 원본 봉쇄)
    REQUIRED_FIELDS = (
        "ema_fast",
        "ema_slow",
        "ema_base",
        "prev_ema_fast",
        "prev_ema_slow",
        "macd",
        "signal",
        "hist",
        "prev_macd",
        "prev_signal",
    )

    # 매수/매도 별도 EMA (use_separate_ema=True 시) 추가 8개
    SEPARATE_EMA_FIELDS = (
        "ema_fast_buy",
        "ema_slow_buy",
        "ema_fast_sell",
        "ema_slow_sell",
        "prev_ema_fast_buy",
        "prev_ema_slow_buy",
        "prev_ema_fast_sell",
        "prev_ema_slow_sell",
    )

    def _read(self) -> str:
        return self.LIVE_LOOP.read_text(encoding="utf-8")

    def test_backup_dict_contains_all_required_fields(self):
        """saved_indicators dict 에 12개 필드 백업 코드 존재."""
        src = self._read()
        # 백업 블록: `saved_indicators = { ... }` 안에 각 필드 참조
        for field in self.REQUIRED_FIELDS:
            self.assertIn(
                f"'{field}': engine.indicators.{field}",
                src,
                f"[Issue #11 회귀] 지표 백업 필드 '{field}' 사라짐 → BACKFILL 오염 위험",
            )

    def test_separate_ema_fields_backup_present(self):
        """use_separate_ema=True 분기에서 8개 추가 필드 백업."""
        src = self._read()
        for field in self.SEPARATE_EMA_FIELDS:
            self.assertIn(
                f"'{field}': engine.indicators.{field}",
                src,
                f"[Issue #11 회귀] 매수/매도 별도 EMA 백업 '{field}' 사라짐",
            )

    def test_restore_all_required_fields(self):
        """saved_indicators 복원 코드에 12개 필드 존재."""
        src = self._read()
        for field in self.REQUIRED_FIELDS:
            self.assertIn(
                f"engine.indicators.{field} = saved_indicators['{field}']",
                src,
                f"[Issue #11 회귀] 지표 복원 '{field}' 사라짐 → BACKFILL 후 실시간 지표 오염",
            )

    def test_separate_ema_fields_restore_present(self):
        """use_separate_ema=True 분기 복원 8개 필드."""
        src = self._read()
        for field in self.SEPARATE_EMA_FIELDS:
            self.assertIn(
                f"engine.indicators.{field} = saved_indicators['{field}']",
                src,
                f"[Issue #11 회귀] 매수/매도 별도 EMA 복원 '{field}' 사라짐",
            )

    def test_backfill_current_bar_excluded(self):
        """현재 봉(closed_ts) 은 backfill_ts_list 에서 제외."""
        src = self._read()
        self.assertIn(
            "backfill_ts_list = [ts for ts in changed_ts_list if ts != closed_ts]",
            src,
            "현재 봉 제외 로직 사라짐 — 실시간 봉이 BACKFILL 재평가 대상 되면 실주문 중복 위험",
        )

    def test_backfill_source_marker(self):
        """BACKFILL 로 생성된 Bar 는 source='REST_BACKFILL' 마킹."""
        src = self._read()
        self.assertIn(
            'source="REST_BACKFILL"',
            src,
            "REST_BACKFILL 소스 마커 사라짐 — 관찰성 저하",
        )

    def test_backfill_diff_summary_isolation_flag(self):
        """on_new_bar_confirmed 호출 시 backfill_mode=True 플래그 명시 전달."""
        src = self._read()
        self.assertIn(
            '"backfill_mode": True',
            src,
            "BACKFILL diff_summary 격리 플래그 사라짐 — strategy_engine 격리 붕괴",
        )


class TestBackfillAuditFieldRecording(unittest.TestCase):
    """V4 audit UPDATE: via_backfill 필드가 checks 에 저장되는지."""

    STRATEGY_ENGINE = ROOT / "core" / "strategy_engine.py"

    def test_via_backfill_in_all_checks_paths(self):
        """MACD/EMA/BASE_EMA_GAP 3개 경로 모두 via_backfill 저장 (2개 문법 패턴)."""
        src = self.STRATEGY_ENGINE.read_text(encoding="utf-8")
        # 2개 저장 문법:
        #   (a) dict literal:     "via_backfill": bool(is_backfill),
        #   (b) dict assignment:  buy_checks["via_backfill"] = bool(is_backfill)
        count_literal = src.count('"via_backfill": bool(is_backfill)')
        count_assign = src.count('["via_backfill"] = bool(is_backfill)')
        total = count_literal + count_assign
        self.assertGreaterEqual(
            total,
            3,
            f"via_backfill 저장 지점이 3개 미만 (literal {count_literal} + assign {count_assign} = {total}) "
            "— MACD/EMA/BASE_EMA_GAP 중 일부 경로 누락",
        )


class TestAuditViewerBackfillDisplay(unittest.TestCase):
    """audit_viewer 의 🔄 표시 로직이 유지되는지."""

    AUDIT_VIEWER = ROOT / "pages" / "audit_viewer.py"

    def test_via_backfill_extractor_present(self):
        """checks.get('via_backfill') 로 🔄 표시 로직 유지 (default 인자 유무 무관)."""
        src = self.AUDIT_VIEWER.read_text(encoding="utf-8")
        self.assertTrue(
            "checks.get('via_backfill')" in src or "checks.get('via_backfill', False)" in src,
            "via_backfill 추출 함수 사라짐 — 🔄 표시 회귀",
        )
        self.assertIn(
            "🔄",
            src,
            "🔄 마커 사라짐",
        )

    def test_backfill_caption_present(self):
        """감사 뷰어 상단 캡션에 BACKFILL 설명 유지."""
        src = self.AUDIT_VIEWER.read_text(encoding="utf-8")
        self.assertIn(
            "BACKFILL 재평가 경로",
            src,
            "BACKFILL 캡션 사라짐 — 사용자 이해 저하",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
