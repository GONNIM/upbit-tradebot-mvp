# FINAL CODE
# services/logger.py

import logging
import logging.handlers
import json
import os
import threading
import queue
import time
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path
import requests
import sqlite3

from config import ALERT_WEBHOOK_URL

class JSONFormatter(logging.Formatter):
    """
    📝 JSON 포매터: 구조화된 로그 형식 지원
    """
    
    def format(self, record):
        log_entry = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "thread": threading.current_thread().name,
            "process": os.getpid()
        }
        
        # 예외 정보 추가
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        
        # 사용자 정의 필드 추가
        if hasattr(record, 'user_id'):
            log_entry["user_id"] = record.user_id
        
        if hasattr(record, 'trade_id'):
            log_entry["trade_id"] = record.trade_id
        
        if hasattr(record, 'order_id'):
            log_entry["order_id"] = record.order_id
        
        if hasattr(record, 'symbol'):
            log_entry["symbol"] = record.symbol
        
        if hasattr(record, 'extra_data'):
            log_entry["extra_data"] = record.extra_data
        
        return json.dumps(log_entry, ensure_ascii=False, default=str)

class AsyncLogHandler(logging.Handler):
    """
    🚀 비동기 로그 핸들러: DB 적재를 위한 큐 기반 처리
    """
    
    def __init__(self, db_path: str = "tradebot.db", batch_size: int = 10, flush_interval: float = 5.0):
        super().__init__()
        self.db_path = db_path
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.log_queue = queue.Queue()
        self.batch_buffer = []
        self.last_flush = time.time()
        self.running = False
        self.worker_thread = None
        self._lock = threading.Lock()
        
        # 워커 스레드 시작
        self.start_worker()
    
    def start_worker(self):
        """워커 스레드 시작"""
        if not self.running:
            self.running = True
            self.worker_thread = threading.Thread(
                target=self._worker_loop,
                name="log_worker",
                daemon=True
            )
            self.worker_thread.start()
    
    def stop_worker(self):
        """워커 스레드 정지"""
        self.running = False
        if self.worker_thread:
            self.worker_thread.join(timeout=5)
    
    def _worker_loop(self):
        """워커 메인 루프"""
        while self.running or not self.log_queue.empty():
            try:
                # 배치 또는 시간 기반 플러시
                current_time = time.time()
                should_flush = (
                    len(self.batch_buffer) >= self.batch_size or
                    current_time - self.last_flush >= self.flush_interval
                )
                
                if should_flush and self.batch_buffer:
                    self._flush_batch()
                
                # 큐에서 메시지 가져오기
                try:
                    record = self.log_queue.get(timeout=0.1)
                    self.batch_buffer.append(record)
                except queue.Empty:
                    continue
                
            except Exception as e:
                print(f"[ERROR] 로그 워커 오류: {e}")
                time.sleep(1)
    
    def _flush_batch(self):
        """배치 DB 적재"""
        if not self.batch_buffer:
            return
        
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            
            # 배치 인서트
            log_data = []
            for record in self.batch_buffer:
                log_entry = {
                    "timestamp": datetime.fromtimestamp(record.created).isoformat(),
                    "level": record.levelname,
                    "message": record.getMessage(),
                    "logger": record.name,
                    "module": record.module,
                    "line": record.lineno,
                    "user_id": getattr(record, 'user_id', None),
                    "trade_id": getattr(record, 'trade_id', None),
                    "order_id": getattr(record, 'order_id', None),
                    "symbol": getattr(record, 'symbol', None),
                    "extra_data": json.dumps(getattr(record, 'extra_data', {}), ensure_ascii=False, default=str)
                }
                log_data.append(log_entry)
            
            # 벌크 인서트
            cur.executemany(
                """
                INSERT INTO logs (
                    timestamp, level, message, logger, module, line,
                    user_id, trade_id, order_id, symbol, extra_data
                ) VALUES (
                    :timestamp, :level, :message, :logger, :module, :line,
                    :user_id, :trade_id, :order_id, :symbol, :extra_data
                )
                """,
                log_data
            )
            
            conn.commit()
            conn.close()
            
            # 버퍼 클리어
            self.batch_buffer.clear()
            self.last_flush = time.time()
            
        except Exception as e:
            print(f"[ERROR] 배치 로그 적재 실패: {e}")
    
    def emit(self, record):
        """로그 레코드 큐에 추가"""
        try:
            self.log_queue.put(record)
        except Exception as e:
            print(f"[ERROR] 로그 큐 추가 실패: {e}")

class WebhookAlertHandler(logging.Handler):
    """
    🚨 웹훅 알림 핸들러: 크리티컬/청산/주문 실패 알림
    """
    
    def __init__(self, webhook_url: Optional[str] = None):
        super().__init__()
        self.webhook_url = webhook_url or ALERT_WEBHOOK_URL
        self.session = requests.Session()
        self.session.timeout = 10
        
    def emit(self, record):
        """웹훅 알림 발송"""
        if not self.webhook_url:
            return
        
        # 알림 조건 확인
        should_alert = (
            record.levelno >= logging.ERROR or  # ERROR 이상
            "CRITICAL" in record.getMessage() or  # 크리티컬 메시지
            "청산" in record.getMessage() or      # 청산 관련
            "주문 실패" in record.getMessage() or # 주문 실패
            "liquidation" in record.getMessage().lower() or
            "order failed" in record.getMessage().lower()
        )
        
        if not should_alert:
            return
        
        try:
            # 알림 메시지 생성
            payload = {
                "timestamp": datetime.fromtimestamp(record.created).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
                "module": record.module,
                "line": record.lineno,
                "user_id": getattr(record, 'user_id', None),
                "trade_id": getattr(record, 'trade_id', None),
                "order_id": getattr(record, 'order_id', None),
                "symbol": getattr(record, 'symbol', None)
            }
            
            # 웹훅 전송
            response = self.session.post(
                self.webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            
            if response.status_code != 200:
                print(f"[ERROR] 웹훅 알림 실패: {response.status_code} - {response.text}")
                
        except Exception as e:
            print(f"[ERROR] 웹훅 알림 전송 오류: {e}")

class LogManager:
    """
    📚 로그 관리자: 모듈별 로거 설정 및 관리
    """
    
    _loggers = {}
    _configured = False
    _async_handler = None
    
    @classmethod
    def setup_logging(
        cls,
        log_level: str = "INFO",
        log_dir: str = "logs",
        max_file_size: int = 10 * 1024 * 1024,  # 10MB
        backup_count: int = 5,
        db_path: str = "tradebot.db",
        webhook_url: Optional[str] = None
    ):
        """로깅 시스템 설정"""
        if cls._configured:
            return
        
        # 로그 디렉토리 생성
        log_dir_path = Path(log_dir)
        log_dir_path.mkdir(exist_ok=True)
        
        # 루트 로거 설정
        root_logger = logging.getLogger()
        root_logger.setLevel(getattr(logging, log_level.upper()))
        
        # 기존 핸들러 제거
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
        
        # JSON 포매터
        json_formatter = JSONFormatter()
        
        # 콘솔 핸들러
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)
        
        # 파일 핸들러 (롤링)
        file_handler = logging.handlers.RotatingFileHandler(
            filename=log_dir_path / "tradebot.log",
            maxBytes=max_file_size,
            backupCount=backup_count,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(json_formatter)
        root_logger.addHandler(file_handler)
        
        # 에러 파일 핸들러
        error_file_handler = logging.handlers.RotatingFileHandler(
            filename=log_dir_path / "error.log",
            maxBytes=max_file_size,
            backupCount=backup_count,
            encoding='utf-8'
        )
        error_file_handler.setLevel(logging.ERROR)
        error_file_handler.setFormatter(json_formatter)
        root_logger.addHandler(error_file_handler)
        
        # 비동기 DB 핸들러
        cls._async_handler = AsyncLogHandler(db_path=db_path)
        cls._async_handler.setLevel(logging.INFO)
        cls._async_handler.setFormatter(json_formatter)
        root_logger.addHandler(cls._async_handler)
        
        # 웹훅 알림 핸들러
        if webhook_url or ALERT_WEBHOOK_URL:
            webhook_handler = WebhookAlertHandler(webhook_url)
            webhook_handler.setLevel(logging.ERROR)
            webhook_handler.setFormatter(json_formatter)
            root_logger.addHandler(webhook_handler)
        
        cls._configured = True
        
        # 루트 로거로 설정 완료 로그
        root_logger.info("📚 로깅 시스템 초기화 완료")
    
    @classmethod
    def get_logger(cls, name: str) -> logging.Logger:
        """모듈별 로거 반환"""
        if not cls._configured:
            cls.setup_logging()
        
        if name not in cls._loggers:
            cls._loggers[name] = logging.getLogger(name)
        
        return cls._loggers[name]
    
    @classmethod
    def get_engine_logger(cls, name: str = "engine") -> logging.Logger:
        """엔진 모듈 로거"""
        return cls.get_logger(f"engine.{name}")
    
    @classmethod
    def get_strategy_logger(cls, name: str = "strategy") -> logging.Logger:
        """전략 모듈 로거"""
        return cls.get_logger(f"strategy.{name}")
    
    @classmethod
    def get_trader_logger(cls, name: str = "trader") -> logging.Logger:
        """트레이더 모듈 로거"""
        return cls.get_logger(f"trader.{name}")
    
    @classmethod
    def get_feed_logger(cls, name: str = "feed") -> logging.Logger:
        """피드 모듈 로거"""
        return cls.get_logger(f"feed.{name}")
    
    @classmethod
    def get_db_logger(cls, name: str = "db") -> logging.Logger:
        """DB 모듈 로거"""
        return cls.get_logger(f"db.{name}")
    
    @classmethod
    def get_ui_logger(cls, name: str = "ui") -> logging.Logger:
        """UI 모듈 로거"""
        return cls.get_logger(f"ui.{name}")
    
    @classmethod
    def get_alert_logger(cls, name: str = "alert") -> logging.Logger:
        """알림 모듈 로거"""
        return cls.get_logger(f"alert.{name}")
    
    @classmethod
    def shutdown(cls):
        """로깅 시스템 종료"""
        if cls._async_handler:
            cls._async_handler.stop_worker()
        
        # 모든 로거 플러시
        for logger in cls._loggers.values():
            for handler in logger.handlers:
                handler.flush()
        
        logging.shutdown()

# 모듈별 로거 팩토리 함수
def get_engine_logger(name: str = "engine") -> logging.Logger:
    """엔진 모듈 로거"""
    return LogManager.get_logger(f"engine.{name}")

def get_strategy_logger(name: str = "strategy") -> logging.Logger:
    """전략 모듈 로거"""
    return LogManager.get_logger(f"strategy.{name}")

def get_trader_logger(name: str = "trader") -> logging.Logger:
    """트레이더 모듈 로거"""
    return LogManager.get_logger(f"trader.{name}")

def get_feed_logger(name: str = "feed") -> logging.Logger:
    """피드 모듈 로거"""
    return LogManager.get_logger(f"feed.{name}")

def get_db_logger(name: str = "db") -> logging.Logger:
    """DB 모듈 로거"""
    return LogManager.get_logger(f"db.{name}")

def get_ui_logger(name: str = "ui") -> logging.Logger:
    """UI 모듈 로거"""
    return LogManager.get_logger(f"ui.{name}")

def get_alert_logger(name: str = "alert") -> logging.Logger:
    """알림 모듈 로거"""
    return LogManager.get_logger(f"alert.{name}")

# 일반적인 로거 접근 함수
def get_logger(name: str) -> logging.Logger:
    """일반적인 로거 접근 함수"""
    return LogManager.get_logger(name)

# 기존 호환성 함수
def log(level: str, message: str, **kwargs):
    """기존 로그 함수 호환성"""
    logger = LogManager.get_logger("legacy")
    log_level = getattr(logging, level.upper())
    
    # 추가 데이터 설정
    extra = {}
    for key, value in kwargs.items():
        extra[key] = value
    
    logger.log(log_level, message, extra=extra)

# 초기화
if __name__ == "__main__":
    LogManager.setup_logging()
    logger = LogManager.get_logger("test")
    logger.info("테스트 로그 메시지", extra={"user_id": "test_user", "symbol": "BTC"})
