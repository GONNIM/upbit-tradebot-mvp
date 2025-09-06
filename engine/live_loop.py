# FINAL CODE
# engine/live_loop.py

import asyncio
import logging
import time
import threading
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
import queue
import backoff
from circuitbreaker import circuit

import pandas as pd
import numpy as np

from services.db import (
    get_db_manager, 
    insert_log, 
    insert_order, 
    insert_signal, 
    insert_trade,
    fetch_latest_price,
    update_account_balance,
    get_account_balance
)
from services.logger import get_logger
from services.trading_control import TradingController, RiskManager
from core.trader import UpbitTrader
from core.strategy import Strategy
from core.feed import FeedManager
from engine.global_state import update_engine_status, update_event_time
from config import MIN_FEE_RATIO, DEFAULT_USER_ID
from utils.logging_util import log_to_file

# 로거 설정
logger = get_logger(__name__)

# 데이터 클래스 정의
@dataclass
class LiveLoopConfig:
    user_id: str
    ticker: str
    interval: str
    test_mode: bool = True
    max_retry_attempts: int = 3
    retry_delay: float = 1.0
    health_check_interval: float = 30.0
    circuit_breaker_timeout: float = 60.0
    rate_limit_requests: int = 10
    rate_limit_window: float = 1.0
    slippage_tolerance: float = 0.001  # 0.1%
    execution_delay: float = 0.5  # 500ms

@dataclass
class MarketData:
    timestamp: float
    open: float
    high: float
    low: float
    close: float
    volume: float
    ticker: str
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'timestamp': self.timestamp,
            'open': self.open,
            'high': self.high,
            'low': self.low,
            'close': self.close,
            'volume': self.volume,
            'ticker': self.ticker
        }

# 라이브 루프 클래스
class LiveLoop:
    def __init__(self, config: LiveLoopConfig):
        self.config = config
        self.user_id = config.user_id
        self.ticker = config.ticker
        self.interval = config.interval
        self.test_mode = config.test_mode
        
        # 컴포넌트 초기화
        self.db_manager = get_db_manager()
        self.trading_controller = TradingController(self.user_id)
        self.risk_manager = RiskManager(self.user_id)
        self.feed_manager = FeedManager()
        
        # 상태 관리
        self.is_running = False
        self.last_tick_time = 0
        self.tick_count = 0
        self.error_count = 0
        self.max_errors = 10
        
        # 피드 데이터 큐
        self.data_queue = queue.Queue(maxsize=1000)
        
        # 성능 모니터링
        self.performance_stats = {
            'total_ticks': 0,
            'processed_ticks': 0,
            'failed_ticks': 0,
            'avg_processing_time': 0.0,
            'last_signal_time': None,
            'last_trade_time': None,
            'success_rate': 0.0
        }
        
        # 레이트 리미터
        self.rate_limiter = RateLimiter(
            config.rate_limit_requests, 
            config.rate_limit_window
        )
        
        logger.info(f"라이브 루프 초기화 완료: user_id={self.user_id}, ticker={self.ticker}")

    def start(self, params: Dict[str, Any], trader: UpbitTrader, 
              stop_event: threading.Event, event_queue: queue.Queue) -> bool:
        """라이브 루프 시작"""
        try:
            if self.is_running:
                logger.warning(f"라이브 루프 이미 실행 중: {self.user_id}")
                return False
                
            self.is_running = True
            self.params = params
            self.trader = trader
            self.stop_event = stop_event
            self.event_queue = event_queue
            
            # 전략 초기화
            self.strategy = Strategy(
                fast_period=params.fast_period,
                slow_period=params.slow_period,
                signal_period=params.signal_period,
                macd_threshold=params.macd_threshold,
                take_profit=params.take_profit,
                stop_loss=params.stop_loss
            )
            
            # 시작 로그
            msg = f"🚀 라이브 루프 시작: ticker={self.ticker}, interval={self.interval}"
            logger.info(msg)
            insert_log(self.user_id, "INFO", msg)
            log_to_file(msg, self.user_id)
            
            # 메인 루프 실행
            self._run_main_loop()
            
            return True
            
        except Exception as e:
            msg = f"❌ 라이브 루프 시작 실패: {e}"
            logger.error(msg, exc_info=True)
            insert_log(self.user_id, "ERROR", msg)
            self.is_running = False
            return False

    def stop(self):
        """라이브 루프 정지"""
        try:
            self.is_running = False
            
            # 정리 작업
            if hasattr(self, 'feed_manager'):
                self.feed_manager.stop()
            
            msg = f"🛑 라이브 루프 종료: ticker={self.ticker}"
            logger.info(msg)
            insert_log(self.user_id, "INFO", msg)
            log_to_file(msg, self.user_id)
            
        except Exception as e:
            msg = f"❌ 라이브 루프 종료 실패: {e}"
            logger.error(msg, exc_info=True)
            insert_log(self.user_id, "ERROR", msg)

    def _run_main_loop(self):
        """메인 루프 실행"""
        logger.info(f"메인 루프 시작: {self.user_id}")
        
        while self.is_running and not self.stop_event.is_set():
            try:
                # 레이트 리밋 체크
                if not self.rate_limiter.can_proceed():
                    time.sleep(0.1)
                    continue
                
                # 틱 실행
                start_time = time.time()
                success = self._execute_tick()
                processing_time = time.time() - start_time
                
                # 성능 통계 업데이트
                self._update_performance_stats(success, processing_time)
                
                # 간격 조정
                interval_ms = self._parse_interval_to_ms(self.interval)
                sleep_time = max(0, (interval_ms / 1000) - processing_time)
                time.sleep(sleep_time)
                
            except Exception as e:
                self._handle_tick_error(e)
                
                # 에러 카운트 체크
                if self.error_count >= self.max_errors:
                    logger.critical(f"최대 에러 도달 - 라이브 루프 중지: {self.user_id}")
                    self.stop()
                    break
                    
                time.sleep(self.config.retry_delay)

    def _execute_tick(self) -> bool:
        """단일 틱 실행"""
        try:
            self.tick_count += 1
            
            # 1. 피드 데이터 수집
            market_data = self._collect_market_data()
            if not market_data:
                return False
                
            # 2. 전략 분석
            signal = self._analyze_strategy(market_data)
            if not signal:
                return True  # 신호 없음도 정상 처리
                
            # 3. 신호 처리
            self._process_signal(signal, market_data)
            
            # 4. 리스크 관리
            self._check_risk_management()
            
            # 5. 상태 업데이트
            self._update_loop_status()
            
            return True
            
        except Exception as e:
            self._handle_tick_error(e)
            return False

    def _collect_market_data(self) -> Optional[MarketData]:
        """시장 데이터 수집"""
        try:
            # 피드 매니저로부터 데이터 가져오기
            data = self.feed_manager.get_latest_data(self.ticker, self.interval)
            if not data:
                return None
                
            # MarketData 객체 변환
            market_data = MarketData(
                timestamp=data['timestamp'],
                open=data['open'],
                high=data['high'],
                low=data['low'],
                close=data['close'],
                volume=data['volume'],
                ticker=self.ticker
            )
            
            # 데이터 큐에 저장
            self.data_queue.put(market_data)
            
            # DB에 저장
            self._save_market_data(market_data)
            
            return market_data
            
        except Exception as e:
            logger.error(f"시장 데이터 수집 실패: {e}")
            return None

    def _analyze_strategy(self, market_data: MarketData) -> Optional[Dict[str, Any]]:
        """전략 분석 및 신호 생성"""
        try:
            # 최근 데이터 가져오기
            recent_data = self._get_recent_data_for_analysis()
            if len(recent_data) < self.strategy.slow_period:
                return None
                
            # DataFrame으로 변환
            df = pd.DataFrame([d.to_dict() for d in recent_data])
            
            # 전략 분석
            signal_data = self.strategy.analyze(df)
            if not signal_data:
                return None
                
            # 신호 검증
            if not self._validate_signal(signal_data):
                return None
                
            return signal_data
            
        except Exception as e:
            logger.error(f"전략 분석 실패: {e}")
            return None

    def _process_signal(self, signal: Dict[str, Any], market_data: MarketData):
        """신호 처리 및 거래 실행"""
        try:
            signal_type = signal.get('signal', '')
            if signal_type not in ['BUY', 'SELL']:
                return
                
            # 이벤트 큐에 신호 전송
            event_data = (
                market_data.timestamp,
                signal_type,
                signal.get('quantity', 0),
                market_data.close,
                signal.get('cross', ''),
                signal.get('macd', 0),
                signal.get('signal_line', 0)
            )
            self.event_queue.put(event_data)
            
            # 신호 DB 저장
            self._save_signal(signal, market_data)
            
            # 거래 실행
            if self._should_execute_trade(signal_type):
                self._execute_trade(signal, market_data)
                
            # 로그 기록
            self._log_signal(signal, market_data)
            
        except Exception as e:
            logger.error(f"신호 처리 실패: {e}")
            self.event_queue.put((
                market_data.timestamp,
                'EXCEPTION',
                type(e),
                e,
                None
            ))

    def _execute_trade(self, signal: Dict[str, Any], market_data: MarketData):
        """거래 실행"""
        try:
            signal_type = signal.get('signal', '')
            quantity = signal.get('quantity', 0)
            price = market_data.close
            
            # 슬리피지 적용
            if signal_type == 'BUY':
                price = price * (1 + self.config.slippage_tolerance)
            elif signal_type == 'SELL':
                price = price * (1 - self.config.slippage_tolerance)
                
            # 체결 지연 고려
            time.sleep(self.config.execution_delay)
            
            # 거래 실행
            if signal_type == 'BUY':
                result = self.trader.buy_market(price, self.ticker)
            elif signal_type == 'SELL':
                result = self.trader.sell_market(quantity, self.ticker, price)
            else:
                return
                
            if result:
                # 거래 DB 저장
                self._save_trade(result, signal_type, market_data)
                
                # 계정 잔고 업데이트
                self._update_account_balance(result)
                
                # 성능 통계 업데이트
                self.performance_stats['last_trade_time'] = datetime.now()
                
        except Exception as e:
            logger.error(f"거래 실행 실패: {e}")
            self.event_queue.put((
                market_data.timestamp,
                'EXCEPTION',
                type(e),
                e,
                None
            ))

    def _check_risk_management(self):
        """리스크 관리 체크"""
        try:
            # 리스크 한도 체크
            if not self.risk_manager.check_risk_limits():
                logger.warning(f"리스크 한도 초과: {self.user_id}")
                self.trading_controller.pause_trading()
                
            # 계정 상태 체크
            balance = get_account_balance(self.user_id)
            if balance and balance.get('available_krw', 0) < 10000:
                logger.warning(f"잔고 부족: {self.user_id}")
                self.trading_controller.pause_trading()
                
        except Exception as e:
            logger.error(f"리스크 관리 체크 실패: {e}")

    def _update_loop_status(self):
        """루프 상태 업데이트"""
        try:
            update_engine_status(self.user_id, "running")
            update_event_time(self.user_id)
            self.last_tick_time = time.time()
            
        except Exception as e:
            logger.error(f"상태 업데이트 실패: {e}")

    def _handle_tick_error(self, error: Exception):
        """틱 에러 처리"""
        self.error_count += 1
        self.performance_stats['failed_ticks'] += 1
        
        error_msg = f"틱 실행 에러: {error}"
        logger.error(error_msg, exc_info=True)
        insert_log(self.user_id, "ERROR", error_msg)
        
        # 이벤트 큐에 에러 전송
        self.event_queue.put((
            time.time(),
            'EXCEPTION',
            type(error),
            error,
            None
        ))

    def _update_performance_stats(self, success: bool, processing_time: float):
        """성능 통계 업데이트"""
        self.performance_stats['total_ticks'] += 1
        
        if success:
            self.performance_stats['processed_ticks'] += 1
        else:
            self.performance_stats['failed_ticks'] += 1
            
        # 평균 처리 시간 업데이트
        total = self.performance_stats['total_ticks']
        current_avg = self.performance_stats['avg_processing_time']
        self.performance_stats['avg_processing_time'] = (
            (current_avg * (total - 1) + processing_time) / total
        )
        
        # 성공률 업데이트
        self.performance_stats['success_rate'] = (
            self.performance_stats['processed_ticks'] / total * 100
        )

    def _get_recent_data_for_analysis(self) -> List[MarketData]:
        """분석을 위한 최근 데이터 가져오기"""
        try:
            # 데이터 큐에서 최근 데이터 가져오기
            recent_data = []
            queue_size = self.data_queue.qsize()
            
            for _ in range(min(queue_size, 100)):  # 최대 100개 데이터
                try:
                    data = self.data_queue.get_nowait()
                    recent_data.append(data)
                    self.data_queue.put(data)  # 다시 큐에 넣기
                except queue.Empty:
                    break
                    
            return sorted(recent_data, key=lambda x: x.timestamp)
            
        except Exception as e:
            logger.error(f"최근 데이터 가져오기 실패: {e}")
            return []

    def _validate_signal(self, signal: Dict[str, Any]) -> bool:
        """신호 검증"""
        try:
            signal_type = signal.get('signal', '')
            if signal_type not in ['BUY', 'SELL']:
                return False
                
            # 리스크 관리자로 신호 검증
            if not self.risk_manager.validate_signal(signal):
                return False
                
            # 트레이딩 컨트롤러로 신호 검증
            if not self.trading_controller.validate_signal(signal):
                return False
                
            return True
            
        except Exception as e:
            logger.error(f"신호 검증 실패: {e}")
            return False

    def _should_execute_trade(self, signal_type: str) -> bool:
        """거래 실행 여부 결정"""
        try:
            # 트레이딩 컨트롤러 상태 체크
            if not self.trading_controller.is_trading_enabled():
                return False
                
            # 테스트 모드 체크
            if self.test_mode:
                return True
                
            # 실제 거래 모드에서만 추가 검증
            return self.risk_manager.can_execute_trade(signal_type)
            
        except Exception as e:
            logger.error(f"거래 실행 여부 결정 실패: {e}")
            return False

    def _save_market_data(self, market_data: MarketData):
        """시장 데이터 DB 저장"""
        try:
            # 캔들 데이터 저장 로직
            # TODO: 캔들 테이블이 있는 경우 저장
            pass
            
        except Exception as e:
            logger.error(f"시장 데이터 저장 실패: {e}")

    def _save_signal(self, signal: Dict[str, Any], market_data: MarketData):
        """신호 DB 저장"""
        try:
            signal_data = {
                'user_id': self.user_id,
                'ticker': self.ticker,
                'signal_type': signal.get('signal', ''),
                'signal_strength': signal.get('strength', 0),
                'price': market_data.close,
                'timestamp': datetime.fromtimestamp(market_data.timestamp),
                'macd': signal.get('macd', 0),
                'signal_line': signal.get('signal_line', 0),
                'cross_type': signal.get('cross', ''),
                'confidence': signal.get('confidence', 0)
            }
            
            insert_signal(signal_data)
            
        except Exception as e:
            logger.error(f"신호 저장 실패: {e}")

    def _save_trade(self, result: Dict[str, Any], signal_type: str, market_data: MarketData):
        """거래 DB 저장"""
        try:
            trade_data = {
                'user_id': self.user_id,
                'ticker': self.ticker,
                'order_type': signal_type,
                'quantity': result.get('qty', 0),
                'price': result.get('price', 0),
                'amount': result.get('qty', 0) * result.get('price', 0),
                'fee': result.get('fee', 0),
                'timestamp': datetime.now(),
                'signal_timestamp': datetime.fromtimestamp(market_data.timestamp),
                'execution_delay': (datetime.now() - datetime.fromtimestamp(market_data.timestamp)).total_seconds()
            }
            
            insert_trade(trade_data)
            
        except Exception as e:
            logger.error(f"거래 저장 실패: {e}")

    def _update_account_balance(self, result: Dict[str, Any]):
        """계정 잔고 업데이트"""
        try:
            # 잔고 업데이트 로직
            # TODO: 실제 잔고 업데이트 로직 구현
            pass
            
        except Exception as e:
            logger.error(f"잔고 업데이트 실패: {e}")

    def _log_signal(self, signal: Dict[str, Any], market_data: MarketData):
        """신호 로그 기록"""
        try:
            signal_type = signal.get('signal', '')
            quantity = signal.get('quantity', 0)
            price = market_data.close
            amount = quantity * price
            fee = amount * MIN_FEE_RATIO
            
            log_msg = (
                f"{signal_type} signal: {quantity:.6f} @ {price:,.2f} = {amount:,.2f} "
                f"(fee={fee:,.2f}) | cross={signal.get('cross', '')} "
                f"macd={signal.get('macd', 0):.6f} signal={signal.get('signal_line', 0):.6f}"
            )
            
            insert_log(self.user_id, signal_type, log_msg)
            log_to_file(log_msg, self.user_id)
            
            # 성능 통계 업데이트
            self.performance_stats['last_signal_time'] = datetime.now()
            
        except Exception as e:
            logger.error(f"신호 로그 기록 실패: {e}")

    def _parse_interval_to_ms(self, interval: str) -> int:
        """인터벌을 밀리초로 변환"""
        interval_map = {
            'minutes1': 60 * 1000,
            'minutes3': 3 * 60 * 1000,
            'minutes5': 5 * 60 * 1000,
            'minutes10': 10 * 60 * 1000,
            'minutes15': 15 * 60 * 1000,
            'minutes30': 30 * 60 * 1000,
            'minutes60': 60 * 60 * 1000,
            'minutes240': 4 * 60 * 60 * 1000,
            'day': 24 * 60 * 60 * 1000
        }
        
        return interval_map.get(interval, 60 * 1000)

    def get_performance_stats(self) -> Dict[str, Any]:
        """성능 통계 정보 반환"""
        uptime = time.time() - (self.last_tick_time or time.time())
        return {
            'user_id': self.user_id,
            'ticker': self.ticker,
            'interval': self.interval,
            'uptime': uptime,
            'total_ticks': self.performance_stats['total_ticks'],
            'processed_ticks': self.performance_stats['processed_ticks'],
            'failed_ticks': self.performance_stats['failed_ticks'],
            'avg_processing_time': self.performance_stats['avg_processing_time'],
            'success_rate': self.performance_stats['success_rate'],
            'last_signal_time': self.performance_stats['last_signal_time'],
            'last_trade_time': self.performance_stats['last_trade_time'],
            'is_running': self.is_running,
            'error_count': self.error_count
        }

# 레이트 리미터 클래스
class RateLimiter:
    def __init__(self, max_requests: int, window_seconds: float):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = []
        self.lock = threading.Lock()

    def can_proceed(self) -> bool:
        """요청 가능 여부 확인"""
        with self.lock:
            now = time.time()
            # 윈도우 내 요청만 유지
            self.requests = [req_time for req_time in self.requests if now - req_time < self.window_seconds]
            
            if len(self.requests) >= self.max_requests:
                return False
            
            self.requests.append(now)
            return True

    def is_healthy(self) -> bool:
        """레이트 리미터 상태 확인"""
        with self.lock:
            now = time.time()
            recent_requests = [req_time for req_time in self.requests if now - req_time < self.window_seconds]
            return len(recent_requests) < self.max_requests

# 메인 함수
def run_live_loop(params: Dict[str, Any], q: queue.Queue, trader: UpbitTrader, 
                 stop_event: threading.Event, test_mode: bool = True, 
                 user_id: str = DEFAULT_USER_ID) -> None:
    """라이브 루프 실행"""
    try:
        # 설정 생성
        config = LiveLoopConfig(
            user_id=user_id,
            ticker=params.ticker,
            interval=params.interval,
            test_mode=test_mode
        )
        
        # 라이브 루프 생성 및 실행
        live_loop = LiveLoop(config)
        live_loop.start(params, trader, stop_event, q)
        
    except Exception as e:
        msg = f"❌ 라이브 루프 실행 실패: {e}"
        logger.error(msg, exc_info=True)
        insert_log(user_id, "ERROR", msg)
        log_to_file(msg, user_id)
        
        # 이벤트 큐에 에러 전송
        q.put((
            time.time(),
            'EXCEPTION',
            type(e),
            e,
            None
        ))