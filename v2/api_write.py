"""신버전 대시보드 쓰기 API: 「저장만 하기」 (POST /v2/api/params/save, GET /v2/api/params/current),
매매 중지/재개 (POST /v2/api/pause), 로그아웃 (POST /v2/api/logout).

- 매매 중지/재개는 v2.db.set_paused 한 함수만 실매매 DB 에 쓴다(users.trading_paused 한 칸 + logs 한 줄).
  로그아웃은 신버전 세션 쿠키(v2s)만 지운다.
- 「저장만 하기」가 쓰는 곳은 PULLBACK 파라미터 파일 하나(제자리 덮어쓰기)와 신버전 이력 DB(v2hist)뿐이다.
  실매매 DB 와 EMA·MACD 파라미터 파일, active_strategy 파일은 건드리지 않는다.
- 임시 파일+rename 은 쓰지 않는다(E18: 서비스 유닛이 그 파일 하나만 쓰기 허용).
- 6단계(파일 쓰기)와 7단계(이력) 사이에 프로세스가 죽으면 파일은 새 값·이력은 없는 틈이 남는다
  (알려진 틈: 복구는 GET current 와 v2hist 마지막 행 대조).
- 오류 응답 본문에는 파일 내용·경로·예외 문자열을 넣지 않는다.
"""
import hashlib
import json
import logging
import os
import re
import sqlite3
from datetime import datetime

from v2 import auth, control, db, params_schema
from v2.handlers import ApiHandler

log = logging.getLogger(__name__)

MAX_BODY_BYTES = 64 * 1024
_TICKER_RE = re.compile(r"^KRW-[A-Z]{1,15}$")   # 2차 T13: 엔진 로더와 같게(영문 대문자만)
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
        source = req.get("source") if isinstance(req, dict) else None
        if source not in ("binance", "upbit"):   # 시험한 데이터 출처(이력 메모에 남김)
            return self.send_json({"error": "bad_request"}, 400)

        # 2. 검증
        try:
            params = params_schema.validate_params(req.get("params"), source)
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
        try:   # 2차 T13: 이전 저장본의 선택 4키(거래 시간)는 지우지 않는다(깨진 이전 파일이면 보존할 것 없음)
            file_dict = params_schema.keep_optional(file_dict, json.loads(old))
        except ValueError:
            pass
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
            history_id = db.insert_history(user, params_json, "source=" + source)
        except Exception:
            if self._restore(user, path, old):
                return self.send_json({"error": "history_failed"}, 500)
            return self.send_json({"error": "file_changed"}, 500)

        # 8. 응답 (saved_at 조회 실패는 저장 실패가 아니다)
        # 2차 T13: 「이 설정으로 동작」이 엔진에 넘길 저장본 해시(파일에 쓴 바이트 그대로)
        self.send_json({"ok": True, "history_id": history_id,
                        "saved_at": self._saved_at(user, history_id),
                        "ticker": ticker, "interval": file_dict["interval"],
                        "saved_sha256": hashlib.sha256(new_text.encode("utf-8")).hexdigest()})

    @staticmethod
    def _engine_ticker(user):
        value, _mtime = db.active_strategy(user)
        if not value:
            return None
        try:
            sp = db.active_params(user, value)   # 2차 T13: PULLBACK 운용 중이면 적용본 종목
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


class PauseHandler(ApiHandler):
    """POST /v2/api/pause {"paused": true|false} — Origin·세션·허용 목록은 ApiHandler 가 확인."""

    def post(self):
        raw = self.request.body or b""
        if len(raw) > 1024:
            return self.send_json({"error": "bad_request"}, 400)
        try:
            req = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError, RecursionError):
            return self.send_json({"error": "bad_request"}, 400)
        if not isinstance(req, dict) or not isinstance(req.get("paused"), bool):
            return self.send_json({"error": "bad_request"}, 400)
        user = self.current_user["user_id"]
        try:
            db.set_paused(user, req["paused"])
        except FileNotFoundError:
            return self.send_json({"error": "no_data"}, 404)
        except sqlite3.Error:
            return self.send_json({"error": "db_unavailable"}, 503)
        self.send_json({"ok": True, "paused": req["paused"]})


class ControlHandler(ApiHandler):
    """POST /v2/api/control {"kind","payload"} (2차 T11) — 세션 user·입장 모드로 엔진 제어 요청 파일을 쓴다.
    진행 중 요청이 있으면 409 busy. 실행은 엔진 프로세스가 한다(이 프로세스는 엔진 모듈이 없다)."""

    def post(self):
        raw = self.request.body or b""
        if len(raw) > 8 * 1024:
            return self.send_json({"error": "bad_request"}, 400)
        try:
            req = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError, RecursionError):
            return self.send_json({"error": "bad_request"}, 400)
        if not isinstance(req, dict):
            return self.send_json({"error": "bad_request"}, 400)
        u = self.current_user
        if req.get("kind") == "apply_params":
            # 2차 T13: 「이 설정으로 동작」은 업비트 데이터로 시험한 마지막 저장만(바이낸스 결과는 참고용 — 엔진도 다시 본다)
            try:
                _hid, source = db.last_history(u["user_id"])
            except (sqlite3.Error, OSError, ValueError):
                return self.send_json({"error": "db_unavailable"}, 503)
            if source != "upbit":
                return self.send_json({"error": "source_not_upbit"}, 400)
        try:
            rid = control.write_request(u["user_id"], u["mode"], req.get("kind"), req.get("payload", {}))
        except control.Busy as e:
            return self.send_json({"error": "busy", "pending": e.pending}, 409)
        except ValueError:
            return self.send_json({"error": "bad_request"}, 400)
        except OSError:
            return self.send_json({"error": "file_write_failed"}, 500)
        self.send_json({"id": rid}, 202)


class AppliedHandler(ApiHandler):
    """POST /v2/api/params/applied {"history_id", "request_id"} (2차 T13) — 엔진 적용 결과가 done 이고 그 행이 마지막 저장이면
    v2hist 그 행 applied_at 을 결과 시각(KST ISO)으로 1회 채운다. 결과 파일은 읽기만(엔진이 쓴 것)."""

    def post(self):
        raw = self.request.body or b""
        if len(raw) > 1024:
            return self.send_json({"error": "bad_request"}, 400)
        try:
            req = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError, RecursionError):
            return self.send_json({"error": "bad_request"}, 400)
        if not isinstance(req, dict):
            return self.send_json({"error": "bad_request"}, 400)
        hid, rid = req.get("history_id"), req.get("request_id")
        if isinstance(hid, bool) or not isinstance(hid, int) or not isinstance(rid, str):
            return self.send_json({"error": "bad_request"}, 400)
        user = self.current_user["user_id"]
        try:
            res = control.read_result(user, rid)
        except ValueError:
            return self.send_json({"error": "bad_request"}, 400)
        detail = (res or {}).get("detail") if isinstance(res, dict) else None
        if not res or res.get("status") != "done" or not isinstance(detail, dict) \
                or not isinstance(detail.get("applied_sha256"), str):
            return self.send_json({"error": "not_applied"}, 409)
        try:
            last_id, _source = db.last_history(user)
            if last_id != hid:
                return self.send_json({"error": "not_latest"}, 409)
            # fix 1: 그 결과가 이 저장을 적용한 것이어야 한다(옛 request_id 결과로 새 저장 행을 채우지 않음).
            # 이력 행에는 해시 칸이 없고, 마지막 저장 행의 저장본 = 지금 저장본 파일이라 그 바이트 해시와 비교한다.
            try:
                saved_sha = hashlib.sha256(db.pullback_params_path(user).read_bytes()).hexdigest()
            except OSError:
                return self.send_json({"error": "not_applied"}, 409)
            if detail["applied_sha256"] != saved_sha:
                return self.send_json({"error": "stale_result"}, 409)
            at = res.get("at") if isinstance(res.get("at"), str) else db.now_kst_iso()
            changed = db.set_applied_at(user, hid, at)
        except FileNotFoundError:
            return self.send_json({"error": "no_data"}, 404)
        except sqlite3.Error:
            return self.send_json({"error": "db_unavailable"}, 503)
        self.send_json({"ok": True, "applied_at": at, "changed": changed})


class LogoutHandler(ApiHandler):
    """POST /v2/api/logout — 이 브라우저의 신버전 세션 쿠키만 지운다(서버 폐기 없음)."""

    def post(self):
        self.clear_cookie(auth.SESSION_COOKIE, path="/v2/")
        self.send_json({"ok": True, "redirect": "/"})


ROUTES = [
    (r"/v2/api/pause", PauseHandler),
    (r"/v2/api/control", ControlHandler),
    (r"/v2/api/logout", LogoutHandler),
    (r"/v2/api/params/save", SaveHandler),
    (r"/v2/api/params/current", CurrentHandler),
    (r"/v2/api/params/applied", AppliedHandler),
]
