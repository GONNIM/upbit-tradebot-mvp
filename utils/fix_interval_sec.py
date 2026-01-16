#!/usr/bin/env python3
"""
interval_sec 컬럼의 문자열 데이터를 정수로 변환하는 마이그레이션 스크립트

문제:
- 기존 DB에 interval_sec가 "minute1", "minute3" 등 문자열로 저장됨
- 새 코드는 60, 180 등 정수를 저장
- DataFrame Arrow 변환 시 타입 충돌 발생

해결:
- 모든 사용자 DB의 interval_sec 컬럼을 정수로 변환
"""

import sqlite3
from pathlib import Path
import sys

# 프로젝트 루트를 sys.path에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from services.init_db import get_db_path


def convert_interval_to_sec(interval_str: str) -> int:
    """interval 문자열을 초(sec) 단위로 변환"""
    if isinstance(interval_str, int):
        return interval_str  # 이미 정수면 그대로 반환

    interval_map = {
        "minute1": 60,
        "minute3": 180,
        "minute5": 300,
        "minute10": 600,
        "minute15": 900,
        "minute30": 1800,
        "minute60": 3600,
        "day": 86400,
    }

    if isinstance(interval_str, str):
        return interval_map.get(interval_str.lower(), 60)

    return 60  # 기본값


def fix_audit_trades(db_path: Path):
    """audit_trades 테이블의 interval_sec 수정"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # interval_sec가 문자열인 행 조회
        cursor.execute("""
            SELECT id, interval_sec FROM audit_trades
            WHERE typeof(interval_sec) = 'text'
        """)
        rows = cursor.fetchall()

        if not rows:
            print(f"  ✅ audit_trades: 수정 필요 없음")
            return

        print(f"  🔧 audit_trades: {len(rows)}개 행 수정 중...")

        # 각 행을 정수로 변환
        for row_id, interval_str in rows:
            interval_int = convert_interval_to_sec(interval_str)
            cursor.execute("""
                UPDATE audit_trades
                SET interval_sec = ?
                WHERE id = ?
            """, (interval_int, row_id))

        conn.commit()
        print(f"  ✅ audit_trades: {len(rows)}개 행 수정 완료")

    except sqlite3.OperationalError as e:
        if "no such table" in str(e):
            print(f"  ⚠️ audit_trades: 테이블 없음 (스킵)")
        else:
            raise
    finally:
        conn.close()


def fix_audit_buy_eval(db_path: Path):
    """audit_buy_eval 테이블의 interval_sec 수정"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT id, interval_sec FROM audit_buy_eval
            WHERE typeof(interval_sec) = 'text'
        """)
        rows = cursor.fetchall()

        if not rows:
            print(f"  ✅ audit_buy_eval: 수정 필요 없음")
            return

        print(f"  🔧 audit_buy_eval: {len(rows)}개 행 수정 중...")

        for row_id, interval_str in rows:
            interval_int = convert_interval_to_sec(interval_str)
            cursor.execute("""
                UPDATE audit_buy_eval
                SET interval_sec = ?
                WHERE id = ?
            """, (interval_int, row_id))

        conn.commit()
        print(f"  ✅ audit_buy_eval: {len(rows)}개 행 수정 완료")

    except sqlite3.OperationalError as e:
        if "no such table" in str(e):
            print(f"  ⚠️ audit_buy_eval: 테이블 없음 (스킵)")
        else:
            raise
    finally:
        conn.close()


def fix_audit_sell_eval(db_path: Path):
    """audit_sell_eval 테이블의 interval_sec 수정"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT id, interval_sec FROM audit_sell_eval
            WHERE typeof(interval_sec) = 'text'
        """)
        rows = cursor.fetchall()

        if not rows:
            print(f"  ✅ audit_sell_eval: 수정 필요 없음")
            return

        print(f"  🔧 audit_sell_eval: {len(rows)}개 행 수정 중...")

        for row_id, interval_str in rows:
            interval_int = convert_interval_to_sec(interval_str)
            cursor.execute("""
                UPDATE audit_sell_eval
                SET interval_sec = ?
                WHERE id = ?
            """, (interval_int, row_id))

        conn.commit()
        print(f"  ✅ audit_sell_eval: {len(rows)}개 행 수정 완료")

    except sqlite3.OperationalError as e:
        if "no such table" in str(e):
            print(f"  ⚠️ audit_sell_eval: 테이블 없음 (스킵)")
        else:
            raise
    finally:
        conn.close()


def fix_audit_settings(db_path: Path):
    """audit_settings 테이블의 interval_sec 수정"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT id, interval_sec FROM audit_settings
            WHERE typeof(interval_sec) = 'text'
        """)
        rows = cursor.fetchall()

        if not rows:
            print(f"  ✅ audit_settings: 수정 필요 없음")
            return

        print(f"  🔧 audit_settings: {len(rows)}개 행 수정 중...")

        for row_id, interval_str in rows:
            interval_int = convert_interval_to_sec(interval_str)
            cursor.execute("""
                UPDATE audit_settings
                SET interval_sec = ?
                WHERE id = ?
            """, (interval_int, row_id))

        conn.commit()
        print(f"  ✅ audit_settings: {len(rows)}개 행 수정 완료")

    except sqlite3.OperationalError as e:
        if "no such table" in str(e):
            print(f"  ⚠️ audit_settings: 테이블 없음 (스킵)")
        else:
            raise
    finally:
        conn.close()


def main():
    """모든 사용자 DB의 interval_sec를 정수로 변환"""
    # services/data 폴더에서 DB 찾기
    db_dir = Path("./services/data")

    if not db_dir.exists():
        print("❌ services/data 폴더를 찾을 수 없습니다.")
        print(f"현재 경로: {Path.cwd()}")
        return

    # 모든 DB 파일 찾기 (tradebot_*.db)
    db_files = list(db_dir.glob("tradebot_*.db"))

    if not db_files:
        print("⚠️ DB 파일이 없습니다.")
        return

    print(f"🔍 {len(db_files)}개 DB 파일 발견")
    print()

    for db_file in db_files:
        print(f"📁 {db_file.name}")

        fix_audit_trades(db_file)
        fix_audit_buy_eval(db_file)
        fix_audit_sell_eval(db_file)
        fix_audit_settings(db_file)

        print()

    print("✅ 모든 DB 마이그레이션 완료!")


if __name__ == "__main__":
    main()
