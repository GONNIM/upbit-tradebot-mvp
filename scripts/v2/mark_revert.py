"""되돌리기(코드 revert) 직전에 거래 행 표의 MAX(id) 를 schema_marks 의 '<표>.strategy_type.revert_from' 로 기록한다.

2차 T7 (결정 D2) · 배포 절 7 ③. ⚠ 운영 DB 쓰기 1회(schema_marks 행) — 되돌리기 승인 범위에 적고 사용자 확인 뒤 실행.
순서: tradebot 정지 → DB 백업(배포 절 2 와 같은 명령) → 이 스크립트 → 코드 git revert → tradebot 시작.
재배포(tradebot 재시작) 때 엔진 기동 마이그레이션(close_strategy_revert_gap)만 그때 MAX(id) 를 revert_to 로 적고,
구간(revert_from < id ≤ revert_to)의 전략 없는 행을 옛 EMA/MACD 로 본다. 로그인·대시보드 경로는 구간을 닫지 않는다.

구간은 1개만 지원한다. 이전 구간(revert_from·revert_to 둘 다 있음)이 있으면:
  - 합칠 수 있으면(표식 뒤 ~ revert_from 사이 전략 없는 행 0 — 표식을 올려도 분류가 바뀌는 행이 없음)
    표식(legacy_max_id)을 revert_to 로 올리고 이전 구간을 지운 뒤 새 revert_from 을 적는다.
    전략 칸이 있는 행(EMA·MACD·PULLBACK)은 표식과 무관하게 분류가 그대로다.
  - 못 합치면 아무것도 쓰지 않고 종료 코드 4 — 운영자 확인(되돌리기 진행 전 PO 에 보고, 절차는 plan-phase2.md T7 메모).
revert_from 만 있고 revert_to 가 없으면(재배포 기록 없음) 쓰지 않고 종료 코드 3.

출력은 표 이름·숫자뿐이다(키·경로 값 없음).
사용: python3 scripts/v2/mark_revert.py <user_id>
종료 코드: 0 기록함 · 2 DB 없음/마이그레이션 전 · 3 이미 되돌림 기록 있음 · 4 구간 합칠 수 없음 · 1 그 밖 오류
"""
from __future__ import annotations

import os
import re
import sqlite3
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _marks(conn, table, name_fn):
    out = {}
    for kind in ("legacy_max_id", "revert_from", "revert_to"):
        r = conn.execute("SELECT value FROM schema_marks WHERE name=?", (name_fn(table, kind),)).fetchone()
        out[kind] = r[0] if r else None
    return out


def mark_revert(user_id: str) -> int:
    from services.init_db import get_db_path, strategy_mark_name, STRATEGY_MARK_TABLES, STRATEGY_COLUMN

    db_path = get_db_path(user_id)
    if not os.path.exists(db_path):
        print("STOP db-missing")
        return 2
    conn = None
    try:
        conn = sqlite3.connect(db_path, timeout=30, isolation_level=None)  # 연결 실패도 아래 except (경로 출력 없음)
        conn.execute("PRAGMA busy_timeout=3000;")
        conn.execute("BEGIN IMMEDIATE")
        try:
            has_marks = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_marks'").fetchone()
            if not has_marks:
                conn.execute("ROLLBACK")
                print("STOP not-migrated schema_marks")
                return 2
            plan = []
            for t in STRATEGY_MARK_TABLES:
                cols = [r[1] for r in conn.execute(f"PRAGMA table_info({t})").fetchall()]
                m = _marks(conn, t, strategy_mark_name)
                if STRATEGY_COLUMN not in cols or m["legacy_max_id"] is None:
                    conn.execute("ROLLBACK")
                    print(f"STOP not-migrated {t}")
                    return 2
                if m["revert_from"] is not None and m["revert_to"] is None:
                    conn.execute("ROLLBACK")
                    print(f"STOP already-marked {t} revert_from={m['revert_from']}")
                    return 3
                merge_to = None
                if m["revert_from"] is not None and m["revert_to"] is not None:
                    mark, rv_from, rv_to = m["legacy_max_id"], m["revert_from"], m["revert_to"]
                    null_between = conn.execute(
                        f"SELECT COUNT(*) FROM {t} WHERE {STRATEGY_COLUMN} IS NULL AND id > ? AND id <= ?",
                        (mark, rv_from)).fetchone()[0]
                    if null_between != 0:
                        conn.execute("ROLLBACK")
                        print(f"STOP cannot-merge {t} legacy_max_id={mark} revert_from={rv_from} revert_to={rv_to} "
                              f"null_between={null_between}")
                        return 4
                    merge_to = rv_to
                max_id = conn.execute(f"SELECT COALESCE(MAX(id), 0) FROM {t}").fetchone()[0]
                plan.append((t, merge_to, max_id))
            now_iso = datetime.now(ZoneInfo("Asia/Seoul")).isoformat()
            for t, merge_to, max_id in plan:
                if merge_to is not None:
                    conn.execute("UPDATE schema_marks SET value=?, at=? WHERE name=?",
                                 (merge_to, now_iso, strategy_mark_name(t, "legacy_max_id")))
                    conn.execute("DELETE FROM schema_marks WHERE name IN (?, ?)",
                                 (strategy_mark_name(t, "revert_from"), strategy_mark_name(t, "revert_to")))
                    print(f"MERGED {t} legacy_max_id={merge_to}")
                conn.execute("INSERT INTO schema_marks(name, value, at) VALUES (?, ?, ?)",
                             (strategy_mark_name(t, "revert_from"), max_id, now_iso))
                print(f"MARKED {t} revert_from={max_id}")
            conn.execute("COMMIT")
            return 0
        except Exception:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            raise
    except Exception as e:
        print(f"ERROR {type(e).__name__}")
        return 1
    finally:
        if conn is not None:
            conn.close()


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 1 or not re.fullmatch(r"[A-Za-z0-9_]{1,32}", argv[0]):
        print("usage: python3 scripts/v2/mark_revert.py <user_id>")
        return 1
    return mark_revert(argv[0])


if __name__ == "__main__":
    sys.exit(main())
