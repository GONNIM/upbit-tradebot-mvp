"""신버전 대시보드 tornado 서버 (127.0.0.1:8502, nginx 뒤 /v2/).

실행: 저장소 루트에서 `python3 -m v2.server`
"""
import asyncio
from pathlib import Path
from typing import Optional

import tornado.web
from tornado.log import access_log

from v2 import api_read, auth
from v2.handlers import EntryHandler, StaticHandler

HOST = "127.0.0.1"
PORT = 8502
DEFAULT_ORIGIN = "https://orionhunter7.cafe24.com"


def log_request(handler) -> None:
    """tornado 기본 접근 로그와 비슷한 형식. 쿼리 문자열이 있으면 통째로 가린다(`path?***`)."""
    status = handler.get_status()
    if status < 400:
        log_method = access_log.info
    elif status < 500:
        log_method = access_log.warning
    else:
        log_method = access_log.error
    req = handler.request
    path, sep, _q = req.uri.partition("?")
    uri = path + "?***" if sep else path
    log_method("%d %s %s (%s) %.2fms", status, req.method, uri,
               req.remote_ip, 1000.0 * req.request_time())


def make_app(static_dir: Optional[Path] = None,
             allowed_origin: str = DEFAULT_ORIGIN) -> tornado.web.Application:
    static_dir = Path(static_dir) if static_dir else Path(__file__).resolve().parent / "static"
    routes = [
        (r"/v2/?", EntryHandler),
        (r"/v2/static/(.*)", StaticHandler, {"path": str(static_dir)}),
        *api_read.ROUTES,
        # Task 8: v2.api_write 라우트가 여기에 추가된다.
    ]
    return tornado.web.Application(
        routes,
        static_dir=str(static_dir),
        allowed_origin=allowed_origin,
        nonce_store=auth.NonceStore(),
        log_function=log_request,
    )


async def _serve():
    app = make_app()
    app.listen(PORT, address=HOST)
    await asyncio.Event().wait()


def main():
    asyncio.run(_serve())


if __name__ == "__main__":
    main()
