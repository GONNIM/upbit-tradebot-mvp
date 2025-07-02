import sqlite3
from datetime import datetime


DB_PATH = "tradebot.db"


def log(level: str, message: str):
    print(f"[{level}] {message}")
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO logs (timestamp, level, message)
            VALUES (?, ?, ?)
        """,
            (datetime.now().isoformat(), level.upper(), message),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[ERROR] 로그 저장 실패: {e}")
