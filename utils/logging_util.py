# FINAL CODE
# utils/logging_util.py

import os
import logging
import logging.handlers
import json
import threading
import queue
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
import sqlite3

from services.logger import LogManager, JSONFormatter, AsyncLogHandler, WebhookAlertHandler
from config import ALERT_WEBHOOK_URL

# 로깅 설정
LOG_DIR = "logs"
LOG_FILE_PATH = "engine_debug.log"
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
BACKUP_COUNT = 5

# 모듈별 로거 캐시
_module_loggers = {}

def init_log_system(log_level: str = "INFO", webhook_url: Optional[str] = None):
    """
    🚀 로깅 시스템 초기화
    """
    LogManager.setup_logging(
        log_level=log_level,
        log_dir=LOG_DIR,
        max_file_size=MAX_FILE_SIZE,
        backup_count=BACKUP_COUNT,
        webhook_url=webhook_url
    )

def get_module_logger(module_name: str, submodule: Optional[str] = None) -> logging.Logger:
    """
    📝 모듈별 로거 반환
    """
    global _module_loggers
    
    if submodule:
        logger_key = f"{module_name}.{submodule}"
    else:
        logger_key = module_name
    
    if logger_key not in _module_loggers:
        # 모듈별 로거 팩토리 호출
        if module_name == "engine":
            _module_loggers[logger_key] = LogManager.get_engine_logger(submodule or "main")
        elif module_name == "strategy":
            _module_loggers[logger_key] = LogManager.get_strategy_logger(submodule or "main")
        elif module_name == "trader":
            _module_loggers[logger_key] = LogManager.get_trader_logger(submodule or "main")
        elif module_name == "feed":
            _module_loggers[logger_key] = LogManager.get_feed_logger(submodule or "main")
        elif module_name == "db":
            _module_loggers[logger_key] = LogManager.get_db_logger(submodule or "main")
        elif module_name == "ui":
            _module_loggers[logger_key] = LogManager.get_ui_logger(submodule or "main")
        elif module_name == "alert":
            _module_loggers[logger_key] = LogManager.get_alert_logger(submodule or "main")
        else:
            _module_loggers[logger_key] = LogManager.get_logger(logger_key)
    
    return _module_loggers[logger_key]

def init_log_file(user_id: str):
    """
    📂 사용자별 로그 파일 초기화
    """
    if not LogManager._configured:
        init_log_system()
    
    path = f"{user_id}_{LOG_FILE_PATH}"
    
    if os.path.exists(path):
        os.remove(path)  # 파일 삭제
    
    # 모듈별 로거로 초기화 로그
    logger = get_module_logger("util")
    logger.info(f"사용자 {user_id} 로그 파일 초기화 완료", extra={"user_id": user_id})

def log_to_file(msg: str, user_id: str, level: str = "INFO", **kwargs):
    """
    📝 파일에 로그 기록 (향상된 버전)
    """
    if not LogManager._configured:
        init_log_system()
    
    logger = get_module_logger("util")
    log_level = getattr(logging, level.upper())
    
    # 추가 데이터 설정
    extra = {"user_id": user_id, "message": msg}
    for key, value in kwargs.items():
        extra[key] = value
    
    logger.log(log_level, msg, extra=extra)
    
    # 기존 파일 로깅 호환성 유지
    path = f"{user_id}_{LOG_FILE_PATH}"
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().isoformat()}] {msg}\n")
    except Exception as e:
        logger.error(f"파일 로깅 실패: {e}", extra={"user_id": user_id, "error": str(e)})

def log_trade_event(
    user_id: str, 
    event_type: str, 
    symbol: str, 
    message: str, 
    **kwargs
):
    """
    💰 거래 이벤트 로깅
    """
    logger = get_module_logger("trader")
    
    extra = {
        "user_id": user_id,
        "symbol": symbol,
        "event_type": event_type,
        "trade_id": kwargs.get("trade_id"),
        "order_id": kwargs.get("order_id"),
        "price": kwargs.get("price"),
        "quantity": kwargs.get("quantity"),
        "side": kwargs.get("side")
    }
    
    logger.info(f"[{event_type}] {symbol}: {message}", extra=extra)

def log_strategy_event(
    user_id: str,
    strategy_name: str,
    symbol: str,
    signal_type: str,
    message: str,
    **kwargs
):
    """
    🎯 전략 이벤트 로깅
    """
    logger = get_module_logger("strategy")
    
    extra = {
        "user_id": user_id,
        "symbol": symbol,
        "strategy_name": strategy_name,
        "signal_type": signal_type,
        "indicators": kwargs.get("indicators", {}),
        "strength": kwargs.get("strength"),
        "price": kwargs.get("price")
    }
    
    logger.info(f"[{strategy_name}] {signal_type}: {message}", extra=extra)

def log_system_event(
    user_id: str,
    component: str,
    event_type: str,
    message: str,
    **kwargs
):
    """
    🔧 시스템 이벤트 로깅
    """
    logger = get_module_logger("system")
    
    extra = {
        "user_id": user_id,
        "component": component,
        "event_type": event_type,
        "extra_data": kwargs
    }
    
    if event_type in ["ERROR", "CRITICAL"]:
        logger.error(f"[{component}] {event_type}: {message}", extra=extra)
    elif event_type == "WARNING":
        logger.warning(f"[{component}] {event_type}: {message}", extra=extra)
    else:
        logger.info(f"[{component}] {event_type}: {message}", extra=extra)

def log_alert_event(
    user_id: str,
    alert_type: str,
    severity: str,
    message: str,
    **kwargs
):
    """
    🚨 알림 이벤트 로깅 (웹훅 트리거)
    """
    logger = get_module_logger("alert")
    
    extra = {
        "user_id": user_id,
        "alert_type": alert_type,
        "severity": severity,
        "extra_data": kwargs
    }
    
    # 크리티컬/청산/주문 실패 등 ERROR 레벨로 로깅하여 웹훅 트리거
    if severity in ["CRITICAL", "HIGH"]:
        logger.error(f"[{alert_type}] {severity}: {message}", extra=extra)
    else:
        logger.warning(f"[{alert_type}] {severity}: {message}", extra=extra)

def get_last_status_log(user_id: str) -> str:
    """
    📋 사용자 로그 중 상태 관련(이모지 기반) 로그의 마지막 항목 반환
    """
    path = f"{user_id}_{LOG_FILE_PATH}"
    if not os.path.exists(path):
        return "❌ 로그 파일이 존재하지 않음"

    status_emoji_prefixes = ("🚀", "🔌", "🛑", "✅", "⚠️", "📡", "🔄", "❌", "🚨", "📊", "💰", "🎯")
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
    🗄️ logs 테이블에서 가장 최근의 상태 관련 로그를 반환
    """
    from services.db import fetch_logs
    
    status_emoji_prefixes = ("🚀", "🔌", "🛑", "✅", "⚠️", "📡", "🔄", "❌", "🚨", "📊", "💰", "🎯")
    last_status_log = None

    try:
        logs = fetch_logs(user_id, level="INFO", limit=1000)
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

def get_user_logs(
    user_id: str,
    level: Optional[str] = None,
    limit: int = 100,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None
) -> List[Tuple]:
    """
    📊 사용자 로그 조회 (향상된 버전)
    """
    from services.db import fetch_logs
    
    try:
        return fetch_logs(
            user_id=user_id,
            level=level,
            limit=limit,
            start_time=start_time,
            end_time=end_time
        )
    except Exception as e:
        logger = get_module_logger("util")
        logger.error(f"사용자 로그 조회 실패: {e}", extra={"user_id": user_id})
        return []

def get_trade_logs(
    user_id: str,
    symbol: Optional[str] = None,
    limit: int = 50
) -> List[Tuple]:
    """
    💰 거래 관련 로그 조회
    """
    from services.db import fetch_logs
    
    try:
        # 모든 로그를 가져와서 필터링
        all_logs = fetch_logs(user_id=user_id, level="INFO", limit=1000)
        
        trade_logs = []
        for timestamp, level, message, logger_name, module, line, user_id_field, trade_id, order_id, symbol_field, extra_data in all_logs:
            if logger_name and logger_name.startswith("trader"):
                if symbol is None or symbol_field == symbol:
                    trade_logs.append((timestamp, level, message, logger_name))
                    if len(trade_logs) >= limit:
                        break
        
        return trade_logs
    except Exception as e:
        logger = get_module_logger("util")
        logger.error(f"거래 로그 조회 실패: {e}", extra={"user_id": user_id})
        return []

def get_error_logs(
    user_id: str,
    limit: int = 50
) -> List[Tuple]:
    """
    ❌ 에러 로그 조회
    """
    from services.db import fetch_logs
    
    try:
        return fetch_logs(user_id=user_id, level="ERROR", limit=limit)
    except Exception as e:
        logger = get_module_logger("util")
        logger.error(f"에러 로그 조회 실패: {e}", extra={"user_id": user_id})
        return []

def cleanup_old_logs(days: int = 30):
    """
    🧹 오래된 로그 정리
    """
    logger = get_module_logger("util")
    
    try:
        cutoff_date = datetime.now() - timedelta(days=days)
        
        # DB에서 오래된 로그 삭제
        conn = sqlite3.connect("tradebot.db")
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM logs WHERE timestamp < ?",
            (cutoff_date.isoformat(),)
        )
        deleted_count = cur.rowcount
        conn.commit()
        conn.close()
        
        # 로그 파일 정리
        logs_dir = Path(LOG_DIR)
        if logs_dir.exists():
            for log_file in logs_dir.glob("*.log.*"):
                if log_file.stat().st_mtime < cutoff_date.timestamp():
                    log_file.unlink()
        
        logger.info(f"오래된 로그 정리 완료: {deleted_count}개 DB 레코드 삭제")
        
    except Exception as e:
        logger.error(f"로그 정리 실패: {e}")

def shutdown_logging():
    """
    🔒 로깅 시스템 안전 종료
    """
    LogManager.shutdown()

# 초기화
if __name__ == "__main__":
    init_log_system()
    logger = get_module_logger("test")
    logger.info("로깅 유틸리티 테스트", extra={"user_id": "test_user", "symbol": "BTC"})
    
    # 테스트: 거래 이벤트 로깅
    log_trade_event("test_user", "BUY", "BTC", "매수 주문 실행", price=50000000, quantity=0.001)
    
    # 테스트: 전략 이벤트 로깅
    log_strategy_event("test_user", "MACD", "BTC", "BUY", "골든크로스 발생", strength=0.8)
    
    # 테스트: 알림 이벤트 로깅
    log_alert_event("test_user", "SYSTEM", "HIGH", "시스템 경고 발생")
