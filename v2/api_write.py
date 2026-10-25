"""신버전 대시보드 쓰기 API: 「저장만 하기」 (POST /v2/api/params/save, GET /v2/api/params/current).

- 쓰는 곳은 PULLBACK 파라미터 파일 하나(제자리 덮어쓰기)와 신버전 이력 DB(v2hist)뿐이다.
  실매매 DB 와 EMA·MACD 파라미터 파일, active_strategy 파일은 건드리지 않는다.
- 임시 파일+rename 은 쓰지 않는다(E18: 서비스 유닛이 그 파일 하나만 쓰기 허용).
- 6단계(파일 쓰기)와 7단계(이력) 사이에 프로세스가 죽으면 파일은 새 값·이력은 없는 틈이 남는다
  (알려진 틈: 복구는 GET current 와 v2hist 마지막 행 대조).
- 오류 응답 본문에는 파일 내용·경로·예외 문자열을 넣지 않는다.
"""
import json
import logging
import os
import re
from datetime import datetime

from v2 import db, params_schema
from v2.handlers import ApiHandler

log = logging.getLogger(__name__)

MAX_BODY_BYTES = 64 * 1024
_TICKER_RE = re.compile(r"^KRW-[A-Z0-9]{1,20}$")
SQL_SAVED_AT = "SELECT saved_at FROM v2_settings_history WHERE id=? LIMIT 1"


def _write_in_place(path, text):
    """파일을 열린 그대로(inode 유지) 덮어쓴다. 새 내용·되쓰기가 같은 함수를 쓴다."""
    with open(path, "r+", encoding="utf-8", newline="") as f:
        f.seek(0)
        f.write(text)
        f.truncate()
        f.flush()
        os.fsync(f.fileno())


class SaveHandler(ApiHandler):
    def post(self):
        user = self.current_user["user_id"]

        # 1. 본문
        raw = self.request.body or b""
        if len(raw) > MAX_BODY_BYTES:
            return self.send_json({"error": "bad_request"}, 400)
        try:
            req = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError, RecursionError):
            return self.send_json({"error": "bad_request"}, 400)
        if not isinstance(req, dict) or req.get("source") != "binance":
            return self.send_json({"error": "bad_request"}, 400)

        # 2. 검증
        try:
            params = params_schema.validate_params(req.get("params"))
        except ValueError as e:
            return self.send_json({"error": "invalid_param", "field": str(e)}, 400)

        # 3. 엔진 종목
        ticker = self._engine_ticker(user)
        if ticker is None:
            return self.send_json({"error": "engine_ticker_unknown"}, 409)

        # 4. 실매매 DB 가 없으면 이력 DB 를 만들 수 없다
        if not db.live_db_path(user).exists():
            return self.send_json({"error": "no_data"}, 404)

        # 5·6. 파일 읽기(없으면 500, 만들지 않음)
        path = db.pullback_params_path(user)
        try:
            with open(path, "r+", encoding="utf-8", newline="") as f:
                old = f.read()
        except FileNotFoundError:
            return self.send_json({"error": "pullback_file_missing",
                                   "message": "배포 설정 누락"}, 500)
        except (OSError, UnicodeDecodeError):
            return self.send_json({"error": "file_write_failed"}, 500)

        file_dict = params_schema.to_engine_file(params, ticker)
        new_text = json.dumps(file_dict, ensure_ascii=False, indent=2) + "\n"
        try:
            _write_in_place(path, new_text)
        except FileNotFoundError:
            # 읽은 뒤 파일이 지워짐: open 단계 실패라 쓴 것이 없다. 되쓰기·생성 없이 종료.
            return self.send_json({"error": "pullback_file_missing",
                                   "message": "배포 설정 누락"}, 500)
        except Exception:
            if self._restore(user, path, old):
                return self.send_json({"error": "file_write_failed"}, 500)
            return self.send_json({"error": "file_changed"}, 500)

        # 7. 이력
        params_json = json.dumps(params, ensure_ascii=False)
        try:
            history_id = db.insert_history(user, params_json, "source=binance")
        except Exception:
            if self._restore(user, path, old):
                return self.send_json({"error": "history_failed"}, 500)
            return self.send_json({"error": "file_changed"}, 500)

        # 8. 응답 (saved_at 조회 실패는 저장 실패가 아니다)
        self.send_json({"ok": True, "history_id": history_id,
                        "saved_at": self._saved_at(user, history_id),
                        "ticker": ticker, "interval": file_dict["interval"]})

    @staticmethod
    def _engine_ticker(user):
        value, _mtime = db.active_strategy(user)
        if not value:
            return None
        try:
            sp = db.strategy_params(user, value)
        except ValueError:
            return None
        t = db.normalize_ticker(sp.get("ticker"))   # 'JTO' → 'KRW-JTO'
        if t is not None and _TICKER_RE.fullmatch(t):
            return t
        return None

    @staticmethod
    def _restore(user, path, old):
        """old 로 제자리 되쓰기. 성공 True, 실패면 경고 1줄 남기고 False."""
        try:
            _write_in_place(path, old)
            return True
        except Exception:
            log.warning("pullback params file may be changed: user=%s path=%s",
                        user, path)
            return False

    @staticmethod
    def _saved_at(user, history_id):
        try:
            conn = db.open_v2hist(user)
            try:
                row = conn.execute(SQL_SAVED_AT, (history_id,)).fetchone()
            finally:
                conn.close()
            return row[0] if row else None
        except Exception:
            return None


class CurrentHandler(ApiHandler):
    def get(self):
        user = self.current_user["user_id"]
        path = db.pullback_params_path(user)
        try:
            st = path.stat()
        except OSError:
            return self.send_json({"exists": False, "params": None,
                                   "mtime": None, "broken": False})
        mtime = datetime.fromtimestamp(st.st_mtime, db.KST).isoformat()
        params, broken = None, False
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                params = data
            else:
                broken = True
        except (OSError, ValueError):
            broken = True
        self.send_json({"exists": True, "params": params,
                        "mtime": mtime, "broken": broken})


ROUTES = [
    (r"/v2/api/params/save", SaveHandler),
    (r"/v2/api/params/current", CurrentHandler),
]
