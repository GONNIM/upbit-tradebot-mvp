"""B7 마이그레이션 무손실 시험 — 운영 DB 「사본」에 엔진 기동 마이그레이션을 2회 돌려 전후를 비교한다.

2차 배포 요청서 2-1 3 · 계획 plan-phase2.md 8절 B7.
엔진 기동(engine/boot_resume.py 1단계)과 같게 ensure_all_schemas + close_strategy_revert_gap 을 부른다.
사본만 연다: 저장소 services/data 아래 파일은 거부한다(운영·로컬 실 DB 보호). 바깥 연결 없음.

판정(모두 맞아야 종료 코드 0):
  - 기존 테이블: 행 수·MAX(rowid) 전후 같음, 기존 칸 그대로(새 칸 추가만)
  - 새 테이블 pullback_state·strategy_switch·schema_marks 생김
  - 새 칸 audit_trades.strategy_type·orders.strategy_type 생김, 모두 NULL
  - schema_marks '<표>.strategy_type.legacy_max_id' = 마이그레이션 전 MAX(id)
  - PRAGMA integrity_check = ok, foreign_key_check 0행 (전후)
  - 2회째 실행은 스키마·행 수·표식을 바꾸지 않음
출력은 테이블 이름·숫자뿐이다(행 값·경로 값 없음).

사용: python3 scripts/v2/migration_dryrun.py <사본 파일 tradebot_<user>.db>
종료 코드: 0 통과 · 1 판정 실패 · 2 사용법·경로 거부
"""
from __future__ import annotations

import os
import re
import sqlite3
import sys
from unittest import mock

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

NEW_TABLES = ("pullback_state", "strategy_switch", "schema_marks")
NEW_COLUMNS = (("audit_trades", "strategy_type"), ("orders", "strategy_type"))


def _q(path, sql, args=()):
    conn = sqlite3.connect(path)
    try:
        return conn.execute(sql, args).fetchall()
    finally:
        conn.close()


def snapshot(path):
    """{표: (칸 이름 목록, 행 수, MAX(rowid))} + integrity·fk."""
    tables = {}
    for (name,) in _q(path, "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
        cols = [r[1] for r in _q(path, f'PRAGMA table_info("{name}")')]
        n = _q(path, f'SELECT COUNT(*) FROM "{name}"')[0][0]
        try:
            mx = _q(path, f'SELECT MAX(rowid) FROM "{name}"')[0][0]
        except sqlite3.OperationalError:  # WITHOUT ROWID
            mx = None
        tables[name] = (cols, n, mx)
    integrity = _q(path, "PRAGMA integrity_check")[0][0]
    fk = len(_q(path, "PRAGMA foreign_key_check"))
    marks = {}
    if "schema_marks" in tables:
        marks = dict(_q(path, "SELECT name, value FROM schema_marks"))
    return tables, integrity, fk, marks


def run_boot_migration(path, user_id):
    with mock.patch("services.init_db.get_db_path", return_value=path), \
         mock.patch("services.db.get_db_path", return_value=path):
        from services.init_db import ensure_all_schemas, close_strategy_revert_gap
        ensure_all_schemas(user_id)
        close_strategy_revert_gap(user_id)


def check(path, user_id, out=print):
    fails = []
    before, integ0, fk0, _ = snapshot(path)
    out(f"before tables={len(before)} integrity={integ0} fk={fk0}")
    if integ0 != "ok" or fk0:
        fails.append("before_integrity")

    run_boot_migration(path, user_id)
    after1, integ1, fk1, marks1 = snapshot(path)
    run_boot_migration(path, user_id)
    after2, integ2, fk2, marks2 = snapshot(path)

    for name, (cols, n, mx) in sorted(before.items()):
        a = after1.get(name)
        if a is None:
            fails.append(f"{name}:missing")
            out(f"FAIL {name} missing after")
            continue
        added = [c for c in a[0] if c not in cols]
        same = a[0][:len(cols)] == cols and a[1] == n and a[2] == mx
        out(f"{'ok  ' if same else 'FAIL'} {name} rows={n}->{a[1]} max={mx}->{a[2]} added={','.join(added) or '-'}")
        if not same:
            fails.append(f"{name}:changed")

    for t in NEW_TABLES:
        ok = t in after1
        out(f"{'ok  ' if ok else 'FAIL'} new table {t} {'present' if ok else 'absent'}"
            f"{' (already before)' if t in before else ''}")
        if not ok:
            fails.append(f"{t}:absent")

    for t, c in NEW_COLUMNS:
        if t not in after1 or c not in after1[t][0]:
            fails.append(f"{t}.{c}:absent")
            out(f"FAIL {t}.{c} absent")
            continue
        nn = _q(path, f'SELECT COUNT(*) FROM "{t}" WHERE "{c}" IS NOT NULL')[0][0]
        mark = marks1.get(f"{t}.{c}.legacy_max_id")
        expect = before[t][2] or 0 if t in before else 0
        had_col = t in before and c in before[t][0]
        ok = nn == 0 and (had_col or mark == expect)
        out(f"{'ok  ' if ok else 'FAIL'} {t}.{c} not_null={nn} legacy_max_id={mark} expect={expect}"
            f"{' (column existed before)' if had_col else ''}")
        if not ok:
            fails.append(f"{t}.{c}:mark")

    out(f"after integrity={integ1}/{integ2} fk={fk1}/{fk2}")
    if (integ1, integ2) != ("ok", "ok") or fk1 or fk2:
        fails.append("after_integrity")

    same2 = after1 == after2 and marks1 == marks2
    out(f"{'ok  ' if same2 else 'FAIL'} second run changes nothing")
    if not same2:
        fails.append("second_run")

    out("RESULT " + ("PASS" if not fails else "FAIL " + " ".join(fails)))
    return not fails


def _prepare_env():
    """services 를 불러오기 전에: 바깥 연결 차단(tests/_netguard), 업비트 키 자리 값, 텔레그램 끔.

    로컬 .env 의 UPBIT 키는 비워 두므로(1030-09) config.py 가 EnvironmentError 로 멈추지 않게
    빈 값일 때만 자리 값을 넣는다. load_dotenv 는 이미 있는 환경 변수를 덮지 않는다.
    """
    from tests._netguard import activate
    activate()
    for k in ("UPBIT_ACCESS", "UPBIT_SECRET"):
        if not os.environ.get(k):
            os.environ[k] = "dryrun-placeholder"
    for k in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "TELEGRAM_CHAT_ID_OPERATOR"):
        os.environ[k] = ""


def main(argv):
    if len(argv) != 2:
        print(__doc__.strip().splitlines()[-2])
        return 2
    path = os.path.abspath(argv[1])
    m = re.fullmatch(r"tradebot_([A-Za-z0-9_]+)\.db", os.path.basename(path))
    if not m or not os.path.isfile(path):
        print("refuse: file must exist and be named tradebot_<user>.db")
        return 2
    real_dir = os.path.realpath(os.path.join(ROOT, "services", "data"))
    if os.path.realpath(path).startswith(real_dir + os.sep):
        print("refuse: copy must be outside services/data")
        return 2
    _prepare_env()
    return 0 if check(path, m.group(1)) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
