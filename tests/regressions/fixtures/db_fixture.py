"""
✅ [Phase 2] 임시 SQLite DB fixture — 회귀 테스트용.

정상 DB 파일 위치를 tempdir 로 강제 이동하여 테스트 격리.
services.db 의 get_db 는 config.DB_PATH 를 참조하므로 monkeypatch 필요.
"""
import os
import tempfile
import shutil
from pathlib import Path
from typing import Callable
import unittest.mock as mock


class TempDBContext:
    """
    with TempDBContext() as ctx:
        ctx.user_id, ctx.db_path 사용

    - services.data/ 를 tempdir 에 격리
    - 종료 시 tempdir 삭제
    """

    def __init__(self, user_id: str = "test_regression"):
        self.user_id = user_id
        self.tmpdir: Path | None = None
        self.db_path: Path | None = None
        self._patcher = None
        self._orig_cwd = None

    def __enter__(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="tradebot_test_"))
        (self.tmpdir / "services" / "data").mkdir(parents=True, exist_ok=True)
        self.db_path = self.tmpdir / "services" / "data" / f"tradebot_{self.user_id}.db"
        # services.db 는 상대 경로 사용 — cwd 를 tmpdir 로 변경
        self._orig_cwd = os.getcwd()
        os.chdir(str(self.tmpdir))
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        os.chdir(self._orig_cwd)
        if self.tmpdir and self.tmpdir.exists():
            shutil.rmtree(self.tmpdir, ignore_errors=True)
        return False
