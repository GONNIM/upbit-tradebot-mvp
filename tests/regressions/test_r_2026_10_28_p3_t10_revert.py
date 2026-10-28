"""
2차 T10: 되돌리기 무해성 정식 시험 (계획 8절 `test_revert_old_code_ignores_new_schema`, T7 넘김 ⑨).

마이그레이션한 시험용 DB(시험 안에서 만듦 — 운영 DB 아님)에서 「옛 코드」를 돌린다.
- 옛 코드 = baseline_commits.REVERT_OLD_CODE_COMMIT(1747fcc, 지금 서버 실행본 — 12ec5a4 배포 완료 보고).
  services/ 는 2차 스키마 변경 직전 커밋 0b04570 과 같다(아래 시험이 확인). `git show <커밋>:services/<파일>` 로
  임시 폴더에 꺼내 별도 프로세스(revert_old_code_runner.py)에서 import 한다(지금 프로세스의 services 와 섞이지 않게).
- 순서: 옛 코드로 DB 생성·행 기록(1회차) → 사본 2개 → 한쪽만 지금 코드로 마이그레이션(ensure_all_schemas +
  services.db.ensure_schema = 기동 경로) → 두 DB 에 옛 코드로 같은 작업(2회차: insert_order·insert_trade_audit·
  fetch_trades_for_snapshot·compute_pnl_for_snapshot).
- 기대: 옛 코드 오류 0, 결과(반환값·표 내용 — 2차가 더한 strategy_type 칸만 빼고)가 마이그레이션 안 한 DB 와 같다.
  옛 코드가 쓴 새 행의 strategy_type 은 NULL(배포 절차 ④ — 되돌림 구간 기록 대상), 표식·pullback_state 는 그대로.
- B7(운영 DB 사본) 은 범위 밖(배포 전 따로 승인).

실행:
    TELEGRAM_BOT_TOKEN= TELEGRAM_CHAT_ID= python3 -m unittest tests.regressions.test_r_2026_10_28_p3_t10_revert -v
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from tests.regressions import baseline_commits as bc  # noqa: E402

OLD = bc.REVERT_OLD_CODE_COMMIT
OLD_FILES = ("services/db.py", "services/init_db.py", "services/settings_history.py")
RUNNER = Path(__file__).with_name("revert_old_code_runner.py")
USER = "t10rv"
RUNNER_CONSTS = ("DEFAULT_USER_ID", "PARAMS_JSON_FILENAME", "CONDITIONS_JSON_FILENAME")  # 실행기 _config_stub 과 같음


def runner_consts(src: str) -> dict:
    """config.py 글에서 실행기가 쓰는 상수 3개(실행하지 않음)."""
    import ast
    out = {}
    for node in ast.parse(src).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                and getattr(node.targets[0], "id", None) in RUNNER_CONSTS:
            out[node.targets[0].id] = ast.literal_eval(node.value)
    assert set(out) == set(RUNNER_CONSTS), out
    return out


class TestRevertOldCode(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="p3t10rv_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.old = self.tmp / "old"
        (self.old / "services").mkdir(parents=True)
        for rel in OLD_FILES:
            src = bc.git_show(rel, OLD)
            if src is None:
                self.skipTest(f"git 원본 없음 {OLD}:{rel}")
            (self.old / rel).write_text(src, encoding="utf-8")

    def run_old(self, db_dir: Path, phase: str, rnd: int) -> dict:
        out = self.tmp / f"out_{db_dir.name}_{phase}_{rnd}.json"
        env = dict(os.environ, TELEGRAM_BOT_TOKEN="", TELEGRAM_CHAT_ID="")
        p = subprocess.run([sys.executable, str(RUNNER), str(self.old), str(db_dir), USER, phase, str(rnd), str(out)],
                           capture_output=True, text=True, timeout=120, env=env, cwd=str(self.tmp))
        self.assertEqual(p.returncode, 0, p.stderr[-2000:])
        d = json.loads(out.read_text(encoding="utf-8"))
        self.assertTrue(all(m.startswith(str(self.old)) for m in d["modules"]), d["modules"])
        return d

    def migrate_now(self, db_path: Path) -> None:
        """지금 코드의 기동 마이그레이션(엔진 boot_resume·로그인과 같은 함수)."""
        with mock.patch("services.init_db.get_db_path", return_value=str(db_path)), \
                mock.patch("services.db.get_db_path", return_value=str(db_path)):
            from services.init_db import ensure_all_schemas
            from services.db import ensure_schema
            ensure_all_schemas(USER)
            ensure_schema(USER)

    @staticmethod
    def cols(db: Path, table: str) -> list:
        conn = sqlite3.connect(db)
        try:
            return [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
        finally:
            conn.close()

    @staticmethod
    def one(db: Path, sql: str):
        conn = sqlite3.connect(db)
        try:
            return conn.execute(sql).fetchall()
        finally:
            conn.close()

    def test_old_services_same_as_before_phase2_schema(self):
        """옛 코드 근거: 서버 실행본 1747fcc 의 services/ 는 2차 스키마 변경(T6 51c62f5) 직전 0b04570 과 같다."""
        r = subprocess.run(["git", "-C", str(ROOT), "diff", "--stat", OLD, "0b04570", "--", "services/", "config.py"],
                           capture_output=True, text=True)
        if r.returncode != 0:
            self.skipTest("git 이력 없음")
        self.assertEqual(r.stdout.strip(), "")   # 고정 이력끼리 비교 — 앞으로의 정당한 수정에 막히지 않음
        # 수정 1회차: 실행기가 지금 config.py 에서 꺼내는 상수 3개만 옛 값과 같은지 본다(파일 전체 비교는 하지 않음 —
        # config.py 를 정당하게 고치면 게이트가 영구히 막히므로).
        old_src = bc.git_show("config.py", OLD)
        self.assertIsNotNone(old_src)
        now_src = (ROOT / "config.py").read_text(encoding="utf-8")
        self.assertEqual(runner_consts(now_src), runner_consts(old_src))

    def test_revert_old_code_ignores_new_schema(self):
        pre, mig = self.tmp / "pre", self.tmp / "mig"
        pre.mkdir()
        # 1) 옛 코드로 DB 생성 + 기존 이력(1회차)
        d = self.run_old(pre, "init", 0)
        self.assertEqual(d["errors"], [])
        d1 = self.run_old(pre, "ops", 1)
        self.assertEqual(d1["errors"], [])
        db_name = f"tradebot_{USER}.db"
        self.assertNotIn("strategy_type", self.cols(pre / db_name, "orders"))
        shutil.copytree(pre, mig)
        # 2) 한쪽만 지금 코드로 마이그레이션
        self.migrate_now(mig / db_name)
        self.assertIn("strategy_type", self.cols(mig / db_name, "orders"))
        self.assertIn("strategy_type", self.cols(mig / db_name, "audit_trades"))
        marks = dict(self.one(mig / db_name, "SELECT name, value FROM schema_marks"))
        self.assertEqual(marks, {"audit_trades.strategy_type.legacy_max_id": 4,
                                 "orders.strategy_type.legacy_max_id": 3})
        self.assertEqual(self.one(mig / db_name, "SELECT COUNT(*) FROM pullback_state"), [(0,)])
        # 3) 두 DB 에 옛 코드로 같은 작업(되돌린 뒤 운영)
        a = self.run_old(pre, "ops", 2)
        b = self.run_old(mig, "ops", 2)
        self.assertEqual(a["errors"], [], a["errors"])
        self.assertEqual(b["errors"], [], b["errors"])
        self.assertTrue(a["results"]["trades_0"])           # 비교 대상이 비어 있지 않음
        self.assertEqual(b["results"], a["results"])
        for t in ("orders", "audit_trades", "settings_history"):
            self.assertEqual(b["tables"][t]["cols"], a["tables"][t]["cols"], t)
            self.assertEqual(b["tables"][t]["rows"], a["tables"][t]["rows"], t)
        # 옛 코드가 쓴 행은 strategy_type NULL(새 칸 무시), 마이그레이션 전 행도 NULL
        self.assertEqual(set(b["tables"]["orders"]["strategy_type"]), {None})
        self.assertEqual(set(b["tables"]["audit_trades"]["strategy_type"]), {None})
        self.assertEqual(len(b["tables"]["orders"]["rows"]), 6)
        self.assertEqual(len(b["tables"]["audit_trades"]["rows"]), 8)
        # 표식·새 테이블은 옛 코드가 건드리지 않음, 무결성 그대로
        self.assertEqual(dict(self.one(mig / db_name, "SELECT name, value FROM schema_marks")), marks)
        self.assertEqual(self.one(mig / db_name, "PRAGMA integrity_check"), [("ok",)])
        self.assertEqual(self.one(mig / db_name, "PRAGMA foreign_key_check"), [])


if __name__ == "__main__":
    unittest.main()
