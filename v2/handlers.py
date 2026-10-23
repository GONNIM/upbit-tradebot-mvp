"""신버전 대시보드 공통 핸들러 (기반 핸들러·ApiHandler·입장·정적).

api_read·api_write 는 이 모듈만 import 한다(server.py 와의 순환 방지).
"""
import json
from pathlib import Path

import tornado.web

from utils import v2_entry_token as et
from v2 import auth

GUIDE_TEXT = "구버전 입장 화면에서 『신버전 대시보드』를 다시 눌러 주세요"
_GUIDE_HTML = (
    "<!doctype html><html lang=\"ko\"><head><meta charset=\"utf-8\">"
    "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
    "<title>입장 필요</title></head><body>"
    "<p>" + GUIDE_TEXT + "</p></body></html>"
)
_UNSAFE_METHODS = ("POST", "PUT", "PATCH", "DELETE")


class BaseHandler(tornado.web.RequestHandler):
    """모든 응답에 보안 헤더를 넣고, 변경 요청은 Origin 을 확인한다."""

    def set_default_headers(self):
        self.set_header("Referrer-Policy", "no-referrer")
        self.set_header("X-Content-Type-Options", "nosniff")

    def prepare(self):
        if self.request.method in _UNSAFE_METHODS:
            origin = self.request.headers.get("Origin")
            if origin != self.application.settings["allowed_origin"]:
                self.send_json({"error": "forbidden_origin"}, 403)
                self.finish()

    def send_json(self, obj, status=200):
        self.set_status(status)
        self.set_header("Content-Type", "application/json; charset=UTF-8")
        self.write(json.dumps(obj, ensure_ascii=False))

    def session_user(self):
        """세션 쿠키가 유효하면 {"user_id","mode"}, 아니면 None(허용 목록 무관)."""
        value = self.get_cookie(auth.SESSION_COOKIE)
        if not value:
            return None
        s = auth.read_session(value)
        if s is None:
            return None
        return {"user_id": s["user_id"], "mode": s["mode"]}

    def guide_401(self):
        self.set_status(401)
        self.set_header("Content-Type", "text/html; charset=UTF-8")
        self.set_header("Cache-Control", "no-store")
        self.write(_GUIDE_HTML)


class ApiHandler(BaseHandler):
    """/v2/api/* 기반. 세션 없음 401, 허용 목록 밖 403(매 요청 재확인)."""

    def set_default_headers(self):
        super().set_default_headers()
        self.set_header("Cache-Control", "no-store")

    def get_current_user(self):
        u = self.session_user()
        if u is None or not et.is_allowed(u["user_id"]):
            return None
        return u

    def prepare(self):
        super().prepare()
        if self._finished:
            return
        if self.current_user is None:
            if self.session_user() is None:
                self.send_json({"error": "unauthorized"}, 401)
            else:
                self.send_json({"error": "forbidden"}, 403)
            self.finish()

    def write_error(self, status_code, **kwargs):
        self.send_json({"error": "http_%d" % status_code}, status_code)


class EntryHandler(BaseHandler):
    """GET /v2/ — 토큰 교환(?t=) 또는 세션 확인 뒤 index.html."""

    def get(self):
        token = self.get_argument("t", None)
        if token is not None:
            self._exchange(token)
            return
        u = self.session_user()
        if u is None or not et.is_allowed(u["user_id"]):
            self.guide_401()
            return
        index = Path(self.application.settings["static_dir"]) / "index.html"
        try:
            data = index.read_bytes()
        except OSError:
            raise tornado.web.HTTPError(404)
        self.set_header("Content-Type", "text/html; charset=UTF-8")
        self.set_header("Cache-Control", "no-store")
        self.write(data)

    def _exchange(self, token):
        try:
            p = et.verify_token(token)
        except (et.TokenInvalid, et.TokenUnavailable):
            self.guide_401()
            return
        if not et.is_allowed(p["user_id"]):
            self.guide_401()
            return
        if not self.application.settings["nonce_store"].consume(
                p["nonce"], p["exp"]):
            self.guide_401()
            return
        self.set_cookie(auth.SESSION_COOKIE,
                        auth.make_session(p["user_id"], p["mode"]),
                        path="/v2/", secure=True, httponly=True,
                        samesite="Lax", max_age=auth.SESSION_TTL_SEC)
        self.set_header("Cache-Control", "no-store")
        self.redirect("/v2/")


class StaticHandler(tornado.web.StaticFileHandler):
    """/v2/static/* — index.html 은 정적 경로로 보내지 않는다."""

    def set_default_headers(self):
        self.set_header("Referrer-Policy", "no-referrer")
        self.set_header("X-Content-Type-Options", "nosniff")

    @classmethod
    def get_absolute_path(cls, root, path):
        if Path(path).name.lower() == "index.html":
            raise tornado.web.HTTPError(404)
        return super().get_absolute_path(root, path)
