import os
from datetime import datetime
from services.db import fetch_logs


LOG_FILE_PATH = "engine_debug.log"


def init_log_file(user_id: str):
    path = f"{user_id}_{LOG_FILE_PATH}"

    if os.path.exists(path):
        os.remove(path)  # 파일 삭제


def log_to_file(msg, user_id: str):
    path = f"{user_id}_{LOG_FILE_PATH}"

    with open(path, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now().isoformat()}] {msg}\n")


def get_last_status_log(user_id: str) -> str:
    """
    사용자 로그 중 상태 관련(이모지 기반) 로그의 마지막 항목 반환
    예: 🚀, 🔌, 🛑, ✅, ⚠️ 등으로 시작하는 로그만 필터링
    """
    path = f"{user_id}_{LOG_FILE_PATH}"
    if not os.path.exists(path):
        return "❌ 로그 파일이 존재하지 않음"

    status_emoji_prefixes = ("🚀", "🔌", "🛑", "✅", "⚠️", "📡", "🔄")
    last_status_line = None

    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                msg = line.strip().split("] ", 1)[-1]  # 로그 메시지 부분만 추출
                if any(msg.startswith(prefix) for prefix in status_emoji_prefixes):
                    last_status_line = line.strip()
        return last_status_line or "❌ 상태 관련 로그 없음"
    except Exception as e:
        return f"❌ 로그 읽기 오류: {e}"


def get_last_status_log_from_db(user_id: str) -> str:
    """
    logs 테이블에서 가장 최근의 INFO 레벨 상태 관련 로그를 반환
    순차적으로 조회하면서 가장 마지막 상태 로그를 저장하여 반환
    """
    status_emoji_prefixes = ("🚀", "🔌", "🛑", "✅", "⚠️", "📡", "🔄", "❌", "🚨")
    last_status_log = None

    try:
        logs = fetch_logs(
            user_id, level="INFO", limit=1000
        )  # 오래된 순서로 반환된다고 가정
        for timestamp, level, message in logs:
            if any(message.startswith(prefix) for prefix in status_emoji_prefixes):
                # 사람이 읽기 쉬운 형식으로 시간 변환
                if isinstance(timestamp, str):
                    ts = datetime.fromisoformat(timestamp)
                else:
                    ts = timestamp
                formatted_ts = ts.strftime("%Y-%m-%d %H:%M:%S")
                last_status_log = f"[{formatted_ts}] {message}"

        return last_status_log or "❌ 상태 관련 INFO 로그 없음"
    except Exception as e:
        return f"❌ DB 로그 조회 오류: {e}"
