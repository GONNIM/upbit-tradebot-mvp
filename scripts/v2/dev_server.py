"""신버전 대시보드 개발용 로컬 서버 (배포·서비스 유닛에 넣지 않는다).

가짜 저장소 루트(임시 폴더)에 예시 DB·설정·서명 키·허용 목록을 만들고,
v2 모듈의 경로 전역을 그곳으로 돌려 로컬 브라우저로 화면을 본다.
실제 저장소 루트의 비밀 파일·DB·설정 파일은 열지도 쓰지도 않는다.

로컬 개발 전용 — 운영 서버에서 실행하지 말 것(tradebot-v2 는 8502 를 쓴다). 기본 포트는 8512.

실행(어느 폴더에서나): python3 <저장소>/scripts/v2/dev_server.py [--port 8512]
"""
import sys
from pathlib import Path

# scripts/v2 에 __init__.py 가 없어 sys.path[0] 이 scripts/v2 가 된다. 저장소 루트를 앞에 넣는다.
_ROOT = str(Path(__file__).resolve().parents[2])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import argparse  # noqa: E402
import os  # noqa: E402
import secrets  # noqa: E402
import shutil  # noqa: E402
import sqlite3  # noqa: E402
import tempfile  # noqa: E402
from datetime import datetime, timedelta  # noqa: E402

from tests.v2.test_api_read import create_schema  # noqa: E402
from utils import v2_entry_token as et  # noqa: E402
from v2 import db  # noqa: E402

USER = "devuser"


def _ts(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def build_fake_root(root: Path, user: str = USER) -> dict:
    root = Path(root)
    data = root / "services" / "data"
    data.mkdir(parents=True, exist_ok=True)
    (root / "pages").mkdir(parents=True, exist_ok=True)

    db_path = data / f"tradebot_{user}.db"
    now = datetime.now(db.KST).replace(microsecond=0)
    ticker = "KRW-ZRO"
    conn = sqlite3.connect(db_path)
    try:
        create_schema(conn)
        conn.execute("INSERT INTO users(username, display_name, virtual_krw, trading_paused) "
                     "VALUES (?,?,?,0)", (user, "Dev User", 1000000))
        conn.execute("INSERT INTO engine_status(user_id, is_running, last_mode) "
                     "VALUES (?,1,'TEST')", (user,))
        conn.execute("INSERT INTO accounts(user_id, virtual_krw, virtual_krw_locked, updated_at) "
                     "VALUES (?,?,?,?)", (user, 800000, 0, _ts(now)))
        conn.execute("INSERT INTO account_positions(user_id, ticker, virtual_coin, "
                     "virtual_coin_locked, entry_price, updated_at) VALUES (?,?,?,?,?,?)",
                     (user, ticker, 1000.0, 0.0, 400.0, _ts(now)))
        for i in range(6):  # 매수 판단 (최근 3분 간격)
            t = now - timedelta(minutes=3 * (i + 1) + 1)
            conn.execute(
                "INSERT INTO audit_buy_eval(timestamp, bar_time, ticker, price, macd, signal, "
                "have_position, overall_ok, failed_keys) VALUES (?,?,?,?,?,?,?,?,?)",
                (t.isoformat(), _ts(t), ticker, 405.0 - i, 0.5, 0.4, 1, 0, '["cooldown"]'))
        for i in range(6):  # 매도 판단 (triggered 0 과 1 이 섞임)
            t = now - timedelta(minutes=3 * i)
            trig = 1 if i == 3 else 0
            conn.execute(
                "INSERT INTO audit_sell_eval(timestamp, bar_time, ticker, price, macd, signal, "
                "tp_price, sl_price, triggered, trigger_key) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (_ts(t), _ts(t), ticker, 410.0 - i, 0.5, 0.4, 440.0, 380.0, trig,
                 "Stop Loss" if trig else None))
        t = now - timedelta(hours=2)
        conn.execute("INSERT INTO audit_trades(timestamp, bar_time, ticker, type, reason, "
                     "price, qty, entry_price) VALUES (?,?,?,?,?,?,?,?)",
                     (_ts(t), _ts(t), ticker, "BUY", "EMA_GC", 400.0, 1000.0, 400.0))
        t = now - timedelta(hours=1)
        conn.execute("INSERT INTO audit_trades(timestamp, bar_time, ticker, type, reason, "
                     "price, qty, entry_price) VALUES (?,?,?,?,?,?,?,?)",
                     (_ts(t), _ts(t), ticker, "SELL", "TAKE_PROFIT", 420.0, 500.0, 400.0))
        # 기본 기능 블록 확인용 orders: 닫힌 거래(BUY 395 → SELL 410) 뒤 열린 BUY(400)
        for k, (hours, side, price) in enumerate(((5, "BUY", 395.0), (4, "SELL", 410.0), (2, "BUY", 400.0))):
            t = now - timedelta(hours=hours)
            conn.execute(
                "INSERT INTO orders(user_id, timestamp, ticker, side, price, volume, status, state, "
                "avg_price, executed_volume, executed_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (user, _ts(t), ticker, side, price, 1000.0, "completed", "completed",
                 price, 1000.0, t.isoformat(), t.isoformat()))
        for i in range(60):  # 2쪽 확인용 (가장 최신 1줄은 기본 기능 블록의 「최종 상태 로그」용 이모지 접두)
            t = now - timedelta(seconds=30 * i)
            msg = "✅ 엔진 정상 동작 (dev)" if i == 0 else "dev log %d" % i
            conn.execute("INSERT INTO logs(user_id, timestamp, level, message) "
                         "VALUES (?,?,?,?)", (user, _ts(t), "INFO", msg))
        conn.commit()
    finally:
        conn.close()

    secret = root / ".v2_secret"
    fd = os.open(secret, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(secrets.token_bytes(32))
    os.chmod(secret, 0o600)

    allow = root / ".v2_allowlist"
    allow.write_text(user + "\n", encoding="utf-8")
    active = root / f"{user}_active_strategy.txt"
    active.write_text("EMA\n", encoding="utf-8")
    params = root / f"{user}_latest_params_EMA.json"
    params.write_text('{"ticker":"KRW-ZRO","interval":"minute3"}', encoding="utf-8")
    dash = root / "pages" / "dashboard.py"
    dash.write_text('st.markdown("v1.2026.10.23.0000")\n', encoding="utf-8")
    return {"db": db_path, "secret": secret, "allowlist": allow, "active": active,
            "params": params, "dashboard": dash, "data_dir": data}


def write_engine_alive(data_dir: Path, user: str = USER) -> None:
    """엔진 프로세스가 5초마다 쓰는 .engine_alive.json 흉내(개발 전용). 임시 파일 → replace."""
    import json
    path = Path(data_dir) / ".engine_alive.json"
    tmp = path.with_name(path.name + ".tmp")
    body = {"pid": os.getpid(), "at": datetime.now(db.KST).isoformat(), "running": {user: True}}
    tmp.write_text(json.dumps(body), encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def point_modules_to(root: Path) -> None:
    """v2·utils 의 경로 전역을 root 아래로 돌린다.

    찾은 전역: v2.db.REPO_ROOT, v2.db.DATA_DIR, utils.v2_entry_token.REPO_ROOT,
    utils.v2_entry_token.SECRET_PATH, utils.v2_entry_token.ALLOWLIST_PATH.
    (v2.server 의 static_dir 은 저장소 안 v2/static 읽기 전용이라 그대로 둔다.)
    """
    root = Path(root)
    db.REPO_ROOT = root
    db.DATA_DIR = root / "services" / "data"
    et.REPO_ROOT = root
    et.SECRET_PATH = root / ".v2_secret"
    et.ALLOWLIST_PATH = root / ".v2_allowlist"


def main() -> None:
    import asyncio

    from v2.server import make_app

    ap = argparse.ArgumentParser(description="v2 개발용 로컬 서버")
    ap.add_argument("--port", type=int, default=8512)
    ap.add_argument("--host-origin", default="localhost",
                    help="입장 URL·허용 Origin 의 호스트(기본 localhost)")
    ap.add_argument("--insecure-cookie", action="store_true",
                    help="쿠키 Secure 속성 끄기(http 로컬 확인용)")
    args = ap.parse_args()

    import signal

    def _stop(_sig, _frm):  # kill(TERM)·백그라운드 INT 에서도 임시 폴더를 지운다
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    tmp = Path(tempfile.mkdtemp(prefix="v2dev_"))

    async def _run():
        build_fake_root(tmp)
        point_modules_to(tmp)
        app = make_app(allowed_origin=f"http://{args.host_origin}:{args.port}",
                       cookie_secure=not args.insecure_cookie)
        app.listen(args.port, address="127.0.0.1")

        async def _alive_loop():
            while True:
                write_engine_alive(tmp / "services" / "data")
                await asyncio.sleep(5)

        asyncio.get_running_loop().create_task(_alive_loop())
        token = et.make_token(USER, "TEST")
        print("입장 URL (60초 안에 1회): http://%s:%d/v2/?t=%s"
              % (args.host_origin, args.port, token))
        print("localhost 연결이 거부되면 --host-origin 127.0.0.1 로 다시 실행하십시오.")
        if not args.insecure_cookie:
            print("쿠키 Secure 가 켜져 있어 http 에서는 세션이 유지되지 않을 수 있습니다"
                  " (필요하면 --insecure-cookie).")
        print("로컬 개발 전용 — 운영 서버에서 실행하지 말 것(tradebot-v2 는 8502).")
        print("종료: Ctrl+C. 새 입장 URL 이 필요하면 다시 실행하십시오.")
        sys.stdout.flush()
        await asyncio.Event().wait()

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        pass
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
