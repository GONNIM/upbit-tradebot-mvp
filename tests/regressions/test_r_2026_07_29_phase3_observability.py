"""
✅ [Phase 3] Observability 계층 회귀 테스트.

대상:
- services/invariant_monitor.py — 스냅샷 기록 + 조회 + 헬스 판정 + cleanup
- services/audit_logger.py — JSONL rotating file
- services/notifier.py — 3-tier 채널 라우팅

원칙:
- 매매 로직 절대 불변 (관찰 계층만 검증)
- 실패 시 매매 흐름 방해 X 검증 (try/except 원칙)

실행:
    python3 -m unittest tests.regressions.test_r_2026_07_29_phase3_observability -v
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

KST = ZoneInfo("Asia/Seoul")


# ─────────────────────────────────────────────────────────────
# invariant_monitor
# ─────────────────────────────────────────────────────────────

class TestInvariantMonitor(unittest.TestCase):
    """Phase 3-A: invariant_monitor — 스냅샷 기록 + 조회 + 헬스 판정."""

    def setUp(self):
        # DB_PATH 를 tempdir 로 mock (init_db.get_db_path 패치)
        self.tmpdir = Path(tempfile.mkdtemp(prefix="phase3_test_"))
        self.test_user = f"test_r_2026_07_29_{id(self)}"
        # 격리된 tempdir DB 경로
        self._db_path = str(self.tmpdir / f"tradebot_{self.test_user}.db")

        # init_db.get_db_path 를 tempdir 로 리다이렉트
        # ⚠️ services.db 도 자체 namespace 에 import 함 — 양쪽 모두 패치 필요
        self._patcher1 = patch(
            "services.init_db.get_db_path",
            return_value=self._db_path,
        )
        self._patcher2 = patch(
            "services.db.get_db_path",
            return_value=self._db_path,
        )
        self._patcher1.start()
        self._patcher2.start()

        # 스키마 캐시 리셋
        import services.invariant_monitor as im
        im._SCHEMA_ENSURED_USERS.clear()
        self.im = im
        # PositionState import
        from core.position_state import PositionState
        self.PositionState = PositionState

    def tearDown(self):
        self._patcher1.stop()
        self._patcher2.stop()
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _make_position(self, has_pos=True, avg=100, qty=10, entry_ts=None):
        p = self.PositionState()
        p._has_position = has_pos
        p.avg_price = avg
        p.qty = qty
        p.entry_ts = entry_ts or datetime(2026, 7, 29, tzinfo=KST)
        return p

    def test_record_snapshot_no_exception_on_success(self):
        """정상 케이스: 스냅샷 기록 예외 없이 완료."""
        p = self._make_position()
        # 예외 없이 통과
        self.im.record_snapshot(
            p, user_id=self.test_user, ticker="KRW-TEST",
            wallet_qty=10.0, wallet_avg=100.0,
        )

    def test_record_snapshot_swallows_exception(self):
        """실패 시 예외 절대 상위 전파 안 함 (매매 흐름 보호)."""
        p = self._make_position()
        with patch("services.db.get_db", side_effect=RuntimeError("db down")):
            # 예외 전파되면 fail
            try:
                self.im.record_snapshot(p, user_id="test", ticker="KRW-X")
            except Exception as e:
                self.fail(f"record_snapshot 이 예외 전파: {e}")

    def test_get_latest_snapshot_returns_none_when_empty(self):
        """스냅샷 없으면 None."""
        result = self.im.get_latest_snapshot("no_such_user", "KRW-X")
        self.assertIsNone(result)

    def test_snapshot_roundtrip(self):
        """기록 후 조회 시 값 일치."""
        p = self._make_position(avg=915.47, qty=3660)
        self.im.record_snapshot(
            p, user_id=self.test_user, ticker="KRW-JTO",
            wallet_qty=3660.0, wallet_avg=915.47,
        )
        snap = self.im.get_latest_snapshot(self.test_user, "KRW-JTO")
        self.assertIsNotNone(snap)
        self.assertEqual(snap["has_position"], 1)
        self.assertAlmostEqual(snap["avg_price"], 915.47, places=2)
        self.assertAlmostEqual(snap["qty"], 3660.0, places=2)

    def test_snapshot_with_violation(self):
        """violation 있으면 code/msg 저장."""
        p = self._make_position()
        self.im.record_snapshot(
            p, user_id=self.test_user, ticker="KRW-TEST",
            violation_code="I1_AVG_PRICE_MISSING",
            violation_msg="has_position=True 인데 avg_price=None",
        )
        violations = self.im.get_recent_violations(self.test_user, "KRW-TEST", hours=1)
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0]["violation_code"], "I1_AVG_PRICE_MISSING")

    def test_health_status_healthy_when_no_violations(self):
        """위반 0건 → green."""
        p = self._make_position()
        self.im.record_snapshot(p, user_id=self.test_user, ticker="KRW-X")
        health = self.im.get_health_status(self.test_user, "KRW-X")
        self.assertEqual(health["status"], "healthy")
        self.assertEqual(health["color"], "green")

    def test_health_status_critical_when_many_violations(self):
        """위반 4건 이상 → red (DEGRADED_MAX=3 초과)."""
        p = self._make_position()
        for i in range(5):
            self.im.record_snapshot(
                p, user_id=self.test_user, ticker="KRW-X",
                violation_code="I1_AVG_PRICE_MISSING", violation_msg="test",
            )
        health = self.im.get_health_status(self.test_user, "KRW-X")
        self.assertEqual(health["status"], "critical")
        self.assertEqual(health["color"], "red")
        self.assertGreaterEqual(health["violation_count_1h"], 5)


# ─────────────────────────────────────────────────────────────
# audit_logger
# ─────────────────────────────────────────────────────────────

class TestAuditLogger(unittest.TestCase):
    """Phase 3-B: audit_logger — JSONL rotating file."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="audit_test_"))
        self.orig_cwd = os.getcwd()
        os.chdir(str(self.tmpdir))
        self.test_user = f"audit_test_{id(self)}"
        import services.audit_logger as al
        # handler 캐시 리셋 (테스트 격리)
        for k in list(al._HANDLERS.keys()):
            for h in al._HANDLERS[k].handlers[:]:
                h.close()
                al._HANDLERS[k].removeHandler(h)
        al._HANDLERS.clear()
        self.al = al

    def tearDown(self):
        # handler close 후 tempdir 정리
        for k in list(self.al._HANDLERS.keys()):
            for h in self.al._HANDLERS[k].handlers[:]:
                h.close()
                self.al._HANDLERS[k].removeHandler(h)
        self.al._HANDLERS.clear()
        os.chdir(self.orig_cwd)
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _read_log(self, user_id: str) -> list[dict]:
        """audit log 파일 읽어서 JSONL parse."""
        path = self.tmpdir / f"{user_id}_audit.log"
        if not path.exists():
            return []
        lines = path.read_text(encoding="utf-8").strip().split("\n")
        return [json.loads(l) for l in lines if l]

    def test_event_writes_jsonl(self):
        """event() 호출 시 JSONL 라인 1개 기록."""
        self.al.event(self.test_user, "TEST_EVENT", ticker="KRW-X",
                     level="INFO", value=42)
        events = self._read_log(self.test_user)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["code"], "TEST_EVENT")
        self.assertEqual(events[0]["ticker"], "KRW-X")
        self.assertEqual(events[0]["value"], 42)
        self.assertEqual(events[0]["level"], "INFO")

    def test_event_swallows_exception(self):
        """event() 실패 시 예외 절대 상위 전파 안 함."""
        with patch("services.audit_logger._get_audit_logger",
                   side_effect=RuntimeError("logger down")):
            try:
                self.al.event("test", "X")
            except Exception as e:
                self.fail(f"event() 가 예외 전파: {e}")

    def test_sell_triggered_helper(self):
        """sell_triggered 헬퍼가 SELL_TRIGGERED 코드로 기록."""
        self.al.sell_triggered("u1", "KRW-JTO", reason="STOP_LOSS",
                              pnl_pct=-0.045, avg_price=915, current_price=872)
        events = self._read_log("u1")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["code"], "SELL_TRIGGERED")
        self.assertEqual(events[0]["reason"], "STOP_LOSS")

    def test_invariant_violation_helper_uses_critical_level(self):
        """invariant_violation 헬퍼는 CRITICAL 레벨."""
        self.al.invariant_violation("u1", "KRW-X", "I1_AVG_PRICE_MISSING",
                                    "test msg", extra_field="ok")
        events = self._read_log("u1")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["level"], "CRITICAL")
        self.assertEqual(events[0]["code"], "INVARIANT_I1_AVG_PRICE_MISSING")

    def test_datetime_serialized_iso(self):
        """datetime 필드 자동 ISO 문자열 변환."""
        ts = datetime(2026, 7, 29, 12, 34, tzinfo=KST)
        self.al.event("u1", "TS_TEST", when=ts)
        events = self._read_log("u1")
        self.assertIn("2026-07-29", events[0]["when"])


# ─────────────────────────────────────────────────────────────
# notifier 3-tier
# ─────────────────────────────────────────────────────────────

class TestNotifierTierRouting(unittest.TestCase):
    """Phase 3-C: notifier — level 별 채널 라우팅 (backward compatible)."""

    def _clear_env(self):
        for k in [
            "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID",
            "TELEGRAM_CHAT_ID_CRITICAL", "TELEGRAM_CHAT_ID_WARNING",
            "TELEGRAM_CHAT_ID_INFO",
        ]:
            os.environ.pop(k, None)

    def setUp(self):
        self._clear_env()

    def tearDown(self):
        self._clear_env()

    def test_default_chat_when_tier_not_set(self):
        """tier 별 env 없으면 기본 TELEGRAM_CHAT_ID 사용."""
        os.environ["TELEGRAM_BOT_TOKEN"] = "tk"
        os.environ["TELEGRAM_CHAT_ID"] = "default_chat"
        from services.notifier import _get_credentials
        token, chat = _get_credentials(level="CRITICAL")
        self.assertEqual(token, "tk")
        self.assertEqual(chat, "default_chat")

    def test_critical_tier_uses_specific_chat(self):
        """TELEGRAM_CHAT_ID_CRITICAL 설정 시 CRITICAL 은 그 채널."""
        os.environ["TELEGRAM_BOT_TOKEN"] = "tk"
        os.environ["TELEGRAM_CHAT_ID"] = "default_chat"
        os.environ["TELEGRAM_CHAT_ID_CRITICAL"] = "personal_chat"
        from services.notifier import _get_credentials
        # CRITICAL → 개인 채널
        token, chat = _get_credentials(level="CRITICAL")
        self.assertEqual(chat, "personal_chat")
        # WARNING → default fallback
        token, chat = _get_credentials(level="WARNING")
        self.assertEqual(chat, "default_chat")

    def test_backward_compatibility_no_level(self):
        """level 인자 안 주면 기존 동작 유지."""
        os.environ["TELEGRAM_BOT_TOKEN"] = "tk"
        os.environ["TELEGRAM_CHAT_ID"] = "default_chat"
        from services.notifier import _get_credentials
        token, chat = _get_credentials()
        self.assertEqual(chat, "default_chat")

    def test_returns_none_when_no_credentials(self):
        """자격 증명 없으면 (None, None)."""
        from services.notifier import _get_credentials
        token, chat = _get_credentials(level="CRITICAL")
        # streamlit secrets 시도할 수 있으니 None이 아닐 수도. 하지만 env 없으면 없어야 정상.
        # test 환경에는 secrets.toml 없으므로 None 예상
        self.assertIsNone(token)


if __name__ == "__main__":
    unittest.main()
