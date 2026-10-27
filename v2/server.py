"""신버전 대시보드 tornado 서버 (127.0.0.1:8502, nginx 뒤 /v2/).

실행: 저장소 루트에서 `python3 -m v2.server`
"""
import asyncio
from pathlib import Path
from typing import Optional

import tornado.web
from tornado.log import access_log

from v2 import api_read, api_write, auth, candles
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
             allowed_origin: str = DEFAULT_ORIGIN,
             cookie_secure: bool = True) -> tornado.web.Application:
    static_dir = Path(static_dir) if static_dir else Path(__file__).resolve().parent / "static"
    routes = [
        (r"/v2/?", EntryHandler),
        (r"/v2/static/(.*)", StaticHandler, {"path": str(static_dir)}),
        *api_read.ROUTES,
        *api_write.ROUTES,
    ]
    return tornado.web.Application(
        routes,
        static_dir=str(static_dir),
        allowed_origin=allowed_origin,
        cookie_secure=cookie_secure,
        nonce_store=auth.NonceStore(),
        log_function=log_request,
        compress_response=True,               # 캔들 응답(1분·30일 수 MB) gzip
        candles=candles.Collector(),          # 서버 전체에서 하나(수집 동시 1건)
    )


async def _serve():
    app = make_app()
    app.listen(PORT, address=HOST)
    # 업비트 시세 미리 받기(기동 300초 뒤부터 600초마다). 개발용 로컬 서버는 _serve 를 쓰지 않아 로컬에서는 돌지 않는다.
    prefetch = asyncio.ensure_future(app.settings["candles"].prefetch_loop())
    try:
        await asyncio.Event().wait()
    finally:
        prefetch.cancel()


def main():
    asyncio.run(_serve())


if __name__ == "__main__":
    main()
