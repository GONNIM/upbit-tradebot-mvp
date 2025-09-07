# FINAL CODE
# engine/global_state.py

import threading
import time
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Set
from dataclasses import dataclass, field, asdict
from enum import Enum
import json
import logging

from services.logger import get_logger
from services.db import (
    get_db_manager, 
    insert_log, 
    fetch_recent_orders, 
    get_coin_balance
)
from config import DEFAULT_USER_ID
from utils.logging_util import log_to_file

# 로거 설정
logger = get_logger(__name__)

# 상태 열거형
class EngineStatus(Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"
    RESTARTING = "restarting"

class TradingMode(Enum):
    LIVE = "live"
    SANDBOX = "sandbox"
    PAPER = "paper"
    BACKTEST = "backtest"

class PositionType(Enum):
    LONG = "long"
    SHORT = "short"
    NONE = "none"

# 데이터 클래스
@dataclass
class PositionState:
    """포지션 상태"""
    ticker: str
    position_type: PositionType
    quantity: float
    avg_price: float
    current_price: float
    unrealized_pnl: float
    realized_pnl: float
    timestamp: float
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'ticker': self.ticker,
            'position_type': self.position_type.value,
            'quantity': self.quantity,
            'avg_price': self.avg_price,
            'current_price': self.current_price,
            'unrealized_pnl': self.unrealized_pnl,
            'realized_pnl': self.realized_pnl,
            'timestamp': self.timestamp
        }

@dataclass
class OrderState:
    """주문 상태"""
    order_id: str
    ticker: str
    order_type: str  # BUY, SELL
    status: str
    quantity: float
    price: float
    filled_quantity: float
    avg_fill_price: float
    fee: float
    timestamp: float
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'order_id': self.order_id,
            'ticker': self.ticker,
            'order_type': self.order_type,
            'status': self.status,
            'quantity': self.quantity,
            'price': self.price,
            'filled_quantity': self.filled_quantity,
            'avg_fill_price': self.avg_fill_price,
            'fee': self.fee,
            'timestamp': self.timestamp
        }

@dataclass
class AccountState:
    """계정 상태"""
    user_id: str
    total_balance: float
    available_krw: float
    used_krw: float
    total_coin_value: float
    total_pnl: float
    daily_pnl: float
    trading_count: int
    win_rate: float
    timestamp: float
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'user_id': self.user_id,
            'total_balance': self.total_balance,
            'available_krw': self.available_krw,
            'used_krw': self.used_krw,
            'total_coin_value': self.total_coin_value,
            'total_pnl': self.total_pnl,
            'daily_pnl': self.daily_pnl,
            'trading_count': self.trading_count,
            'win_rate': self.win_rate,
            'timestamp': self.timestamp
        }

@dataclass
class EngineState:
    """엔진 상태"""
    user_id: str
    status: EngineStatus
    trading_mode: TradingMode
    start_time: float
    uptime: float
    last_heartbeat: float
    current_ticker: str
    current_interval: str
    tick_count: int
    signal_count: int
    trade_count: int
    error_count: int
    performance_metrics: Dict[str, float] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'user_id': self.user_id,
            'status': self.status.value,
            'trading_mode': self.trading_mode.value,
            'start_time': self.start_time,
            'uptime': self.uptime,
            'last_heartbeat': self.last_heartbeat,
            'current_ticker': self.current_ticker,
            'current_interval': self.current_interval,
            'tick_count': self.tick_count,
            'signal_count': self.signal_count,
            'trade_count': self.trade_count,
            'error_count': self.error_count,
            'performance_metrics': self.performance_metrics
        }

@dataclass
class UserState:
    """사용자 종합 상태"""
    user_id: str
    engine_state: EngineState
    account_state: AccountState
    positions: Dict[str, PositionState]
    orders: Dict[str, OrderState]
    last_update: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'user_id': self.user_id,
            'engine_state': self.engine_state.to_dict(),
            'account_state': self.account_state.to_dict(),
            'positions': {k: v.to_dict() for k, v in self.positions.items()},
            'orders': {k: v.to_dict() for k, v in self.orders.items()},
            'last_update': self.last_update,
            'metadata': self.metadata
        }

# 글로벌 상태 관리자
class GlobalStateManager:
    """글로벌 상태 관리 시스템"""
    
    def __init__(self):
        self._lock = threading.RLock()
        self._user_states: Dict[str, UserState] = {}
        self._engine_threads: Dict[str, Dict[str, Any]] = {}
        self._db_manager = get_db_manager()
        self._last_cleanup = time.time()
        self._cleanup_interval = 300  # 5분
        
        # 이벤트 핸들러
        self._event_handlers = {
            'engine_start': [],
            'engine_stop': [],
            'position_update': [],
            'order_update': [],
            'account_update': [],
            'error_occurred': []
        }
        
        logger.info("글로벌 상태 관리자 초기화 완료")
    
    def get_user_state(self, user_id: str) -> Optional[UserState]:
        """사용자 상태 가져오기"""
        with self._lock:
            return self._user_states.get(user_id)
    
    def update_user_state(self, user_id: str, state_update: Dict[str, Any]) -> bool:
        """사용자 상태 업데이트"""
        try:
            with self._lock:
                if user_id not in self._user_states:
                    self._initialize_user_state(user_id)
                
                user_state = self._user_states[user_id]
                
                # 엔진 상태 업데이트
                if 'engine_state' in state_update:
                    self._update_engine_state(user_state, state_update['engine_state'])
                
                # 계정 상태 업데이트
                if 'account_state' in state_update:
                    self._update_account_state(user_state, state_update['account_state'])
                
                # 포지션 업데이트
                if 'positions' in state_update:
                    self._update_positions(user_state, state_update['positions'])
                
                # 주문 업데이트
                if 'orders' in state_update:
                    self._update_orders(user_state, state_update['orders'])
                
                # 메타데이터 업데이트
                if 'metadata' in state_update:
                    user_state.metadata.update(state_update['metadata'])
                
                user_state.last_update = time.time()
                
                # 이벤트 발생
                self._trigger_event_handlers('state_update', user_id, user_state)
                
                return True
                
        except Exception as e:
            logger.error(f"사용자 상태 업데이트 실패: {e}")
            return False
    
    def _initialize_user_state(self, user_id: str):
        """사용자 상태 초기화"""
        current_time = time.time()
        
        engine_state = EngineState(
            user_id=user_id,
            status=EngineStatus.STOPPED,
            trading_mode=TradingMode.SANDBOX,
            start_time=current_time,
            uptime=0,
            last_heartbeat=current_time,
            current_ticker="",
            current_interval="",
            tick_count=0,
            signal_count=0,
            trade_count=0,
            error_count=0
        )
        
        account_state = AccountState(
            user_id=user_id,
            total_balance=0,
            available_krw=0,
            used_krw=0,
            total_coin_value=0,
            total_pnl=0,
            daily_pnl=0,
            trading_count=0,
            win_rate=0,
            timestamp=current_time
        )
        
        self._user_states[user_id] = UserState(
            user_id=user_id,
            engine_state=engine_state,
            account_state=account_state,
            positions={},
            orders={},
            last_update=current_time
        )
    
    def _update_engine_state(self, user_state: UserState, update: Dict[str, Any]):
        """엔진 상태 업데이트"""
        for key, value in update.items():
            if hasattr(user_state.engine_state, key):
                if key == 'status' and isinstance(value, str):
                    value = EngineStatus(value)
                elif key == 'trading_mode' and isinstance(value, str):
                    value = TradingMode(value)
                setattr(user_state.engine_state, key, value)
        
        # 업타임 계산
        if user_state.engine_state.status != EngineStatus.STOPPED:
            user_state.engine_state.uptime = time.time() - user_state.engine_state.start_time
    
    def _update_account_state(self, user_state: UserState, update: Dict[str, Any]):
        """계정 상태 업데이트"""
        for key, value in update.items():
            if hasattr(user_state.account_state, key):
                setattr(user_state.account_state, key, value)
        
        user_state.account_state.timestamp = time.time()
    
    def _update_positions(self, user_state: UserState, positions_update: Dict[str, Any]):
        """포지션 업데이트"""
        for ticker, pos_data in positions_update.items():
            if isinstance(pos_data, dict):
                position_state = PositionState(
                    ticker=ticker,
                    position_type=PositionType(pos_data.get('position_type', 'NONE')),
                    quantity=pos_data.get('quantity', 0),
                    avg_price=pos_data.get('avg_price', 0),
                    current_price=pos_data.get('current_price', 0),
                    unrealized_pnl=pos_data.get('unrealized_pnl', 0),
                    realized_pnl=pos_data.get('realized_pnl', 0),
                    timestamp=pos_data.get('timestamp', time.time())
                )
                user_state.positions[ticker] = position_state
    
    def _update_orders(self, user_state: UserState, orders_update: Dict[str, Any]):
        """주문 업데이트"""
        for order_id, order_data in orders_update.items():
            if isinstance(order_data, dict):
                order_state = OrderState(
                    order_id=order_id,
                    ticker=order_data.get('ticker', ''),
                    order_type=order_data.get('order_type', ''),
                    status=order_data.get('status', ''),
                    quantity=order_data.get('quantity', 0),
                    price=order_data.get('price', 0),
                    filled_quantity=order_data.get('filled_quantity', 0),
                    avg_fill_price=order_data.get('avg_fill_price', 0),
                    fee=order_data.get('fee', 0),
                    timestamp=order_data.get('timestamp', time.time())
                )
                user_state.orders[order_id] = order_state
    
    def get_all_user_states(self) -> Dict[str, Dict[str, Any]]:
        """모든 사용자 상태 가져오기"""
        with self._lock:
            return {uid: state.to_dict() for uid, state in self._user_states.items()}
    
    def get_active_users(self) -> List[str]:
        """활성 사용자 목록 가져오기"""
        with self._lock:
            active_users = []
            for user_id, state in self._user_states.items():
                if state.engine_state.status in [EngineStatus.RUNNING, EngineStatus.PAUSED]:
                    active_users.append(user_id)
            return active_users
    
    def remove_user_state(self, user_id: str) -> bool:
        """사용자 상태 제거"""
        try:
            with self._lock:
                if user_id in self._user_states:
                    del self._user_states[user_id]
                    logger.info(f"사용자 상태 제거: {user_id}")
                    return True
                return False
        except Exception as e:
            logger.error(f"사용자 상태 제거 실패: {e}")
            return False
    
    def cleanup_inactive_states(self):
        """비활성 상태 정리"""
        try:
            current_time = time.time()
            cleaned_count = 0
            
            with self._lock:
                inactive_users = []
                for user_id, state in self._user_states.items():
                    # 1시간 이상 비활성 사용자
                    if (current_time - state.last_update > 3600 and 
                        state.engine_state.status == EngineStatus.STOPPED):
                        inactive_users.append(user_id)
                
                for user_id in inactive_users:
                    del self._user_states[user_id]
                    cleaned_count += 1
            
            if cleaned_count > 0:
                logger.info(f"비활성 상태 정리: {cleaned_count}개 사용자 상태 제거")
                
            self._last_cleanup = current_time
            return cleaned_count
            
        except Exception as e:
            logger.error(f"비활성 상태 정리 실패: {e}")
            return 0
    
    def sync_with_database(self, user_id: str) -> bool:
        """데이터베이스와 상태 동기화"""
        try:
            # 계정 정보 동기화
            balance = get_coin_balance(user_id, 'KRW')
            if balance:
                account_update = {
                    'total_balance': balance.get('total_balance', 0),
                    'available_krw': balance.get('available_krw', 0),
                    'used_krw': balance.get('used_krw', 0),
                    'total_coin_value': balance.get('total_coin_value', 0)
                }
                self.update_user_state(user_id, {'account_state': account_update})
            
            # 주문 정보 동기화
            latest_orders = fetch_recent_orders(user_id, limit=50)
            if latest_orders:
                orders_update = {}
                for order in latest_orders:
                    orders_update[order['order_id']] = order
                self.update_user_state(user_id, {'orders': orders_update})
            
            return True
            
        except Exception as e:
            logger.error(f"데이터베이스 동기화 실패: {e}")
            return False
    
    def get_system_stats(self) -> Dict[str, Any]:
        """시스템 통계 정보"""
        with self._lock:
            total_users = len(self._user_states)
            active_users = len(self.get_active_users())
            total_positions = sum(len(state.positions) for state in self._user_states.values())
            total_orders = sum(len(state.orders) for state in self._user_states.values())
            
            # 엔진 상태별 통계
            status_counts = {}
            for state in self._user_states.values():
                status = state.engine_state.status.value
                status_counts[status] = status_counts.get(status, 0) + 1
            
            return {
                'total_users': total_users,
                'active_users': active_users,
                'total_positions': total_positions,
                'total_orders': total_orders,
                'status_distribution': status_counts,
                'last_cleanup': self._last_cleanup,
                'system_uptime': time.time() - min(
                    state.engine_state.start_time 
                    for state in self._user_states.values()
                ) if self._user_states else 0
            }
    
    def export_state(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        """상태 내보내기"""
        try:
            if user_id:
                user_state = self.get_user_state(user_id)
                return user_state.to_dict() if user_state else {}
            else:
                return self.get_all_user_states()
        except Exception as e:
            logger.error(f"상태 내보내기 실패: {e}")
            return {}
    
    def import_state(self, state_data: Dict[str, Any]) -> bool:
        """상태 가져오기"""
        try:
            with self._lock:
                for user_id, user_data in state_data.items():
                    if user_id not in self._user_states:
                        self._initialize_user_state(user_id)
                    
                    user_state = self._user_states[user_id]
                    
                    # 엔진 상태 복원
                    if 'engine_state' in user_data:
                        engine_data = user_data['engine_state']
                        for key, value in engine_data.items():
                            if hasattr(user_state.engine_state, key):
                                setattr(user_state.engine_state, key, value)
                    
                    # 계정 상태 복원
                    if 'account_state' in user_data:
                        account_data = user_data['account_state']
                        for key, value in account_data.items():
                            if hasattr(user_state.account_state, key):
                                setattr(user_state.account_state, key, value)
                    
                    # 포지션 복원
                    if 'positions' in user_data:
                        self._update_positions(user_state, user_data['positions'])
                    
                    # 주문 복원
                    if 'orders' in user_data:
                        self._update_orders(user_state, user_data['orders'])
                    
                    # 메타데이터 복원
                    if 'metadata' in user_data:
                        user_state.metadata.update(user_data['metadata'])
                    
                    user_state.last_update = time.time()
                
                logger.info("상태 가져오기 완료")
                return True
                
        except Exception as e:
            logger.error(f"상태 가져오기 실패: {e}")
            return False
    
    def add_event_handler(self, event_type: str, handler):
        """이벤트 핸들러 추가"""
        if event_type in self._event_handlers:
            self._event_handlers[event_type].append(handler)
    
    def _trigger_event_handlers(self, event_type: str, user_id: str, data: Any):
        """이벤트 핸들러 트리거"""
        if event_type in self._event_handlers:
            for handler in self._event_handlers[event_type]:
                try:
                    handler(user_id, data)
                except Exception as e:
                    logger.error(f"이벤트 핸들러 실행 실패: {e}")

# 전역 상태 관리자 인스턴스
_global_state_manager = None

def get_global_state_manager() -> GlobalStateManager:
    """전역 상태 관리자 인스턴스 가져오기"""
    global _global_state_manager
    if _global_state_manager is None:
        _global_state_manager = GlobalStateManager()
    return _global_state_manager

# 호환성 함수들
def update_engine_status(user_id: str, status: str, note: Optional[str] = None):
    """엔진 상태 업데이트 (호환성)"""
    manager = get_global_state_manager()
    try:
        engine_status = EngineStatus(status)
        manager.update_user_state(user_id, {
            'engine_state': {
                'status': engine_status,
                'last_heartbeat': time.time()
            }
        })
        
        if note:
            manager.update_user_state(user_id, {
                'metadata': {'note': note}
            })
            
    except Exception as e:
        logger.error(f"엔진 상태 업데이트 실패: {e}")

def update_event_time(user_id: str):
    """이벤트 시간 업데이트 (호환성)"""
    manager = get_global_state_manager()
    manager.update_user_state(user_id, {
        'engine_state': {
            'last_heartbeat': time.time()
        }
    })

def get_engine_threads() -> Dict[str, Dict[str, Any]]:
    """엔진 스레드 정보 가져오기 (호환성)"""
    manager = get_global_state_manager()
    # TODO: 스레드 레지스트리와 통합 필요
    return {}

def add_engine_thread(user_id: str, thread, stop_event):
    """엔진 스레드 추가 (호환성)"""
    # TODO: 스레드 레지스트리와 통합 필요
    pass

def remove_engine_thread(user_id: str):
    """엔진 스레드 제거 (호환성)"""
    # TODO: 스레드 레지스트리와 통합 필요
    pass

def is_engine_really_running(user_id: str) -> bool:
    """엔진 실제 실행 상태 확인 (호환성)"""
    manager = get_global_state_manager()
    user_state = manager.get_user_state(user_id)
    return (user_state is not None and 
            user_state.engine_state.status == EngineStatus.RUNNING)

def stop_all_engines():
    """모든 엔진 중지 (호환성)"""
    manager = get_global_state_manager()
    active_users = manager.get_active_users()
    for user_id in active_users:
        update_engine_status(user_id, "stopped")
        manager.remove_user_state(user_id)

# 유틸리티 함수
def get_user_summary(user_id: str) -> Dict[str, Any]:
    """사용자 요약 정보 가져오기"""
    manager = get_global_state_manager()
    user_state = manager.get_user_state(user_id)
    
    if not user_state:
        return {}
    
    return {
        'user_id': user_id,
        'status': user_state.engine_state.status.value,
        'trading_mode': user_state.engine_state.trading_mode.value,
        'uptime': user_state.engine_state.uptime,
        'total_balance': user_state.account_state.total_balance,
        'available_krw': user_state.account_state.available_krw,
        'total_pnl': user_state.account_state.total_pnl,
        'position_count': len(user_state.positions),
        'open_orders': len([o for o in user_state.orders.values() if o.status in ['pending', 'partially_filled']]),
        'tick_count': user_state.engine_state.tick_count,
        'trade_count': user_state.engine_state.trade_count,
        'last_update': user_state.last_update
    }

def get_system_health() -> Dict[str, Any]:
    """시스템 건강 상태 확인"""
    manager = get_global_state_manager()
    stats = manager.get_system_stats()
    
    # 오류율 계산
    total_ticks = sum(state.engine_state.tick_count for state in manager._user_states.values())
    total_errors = sum(state.engine_state.error_count for state in manager._user_states.values())
    error_rate = (total_errors / total_ticks * 100) if total_ticks > 0 else 0
    
    return {
        'system_status': 'healthy' if error_rate < 5 else 'warning',
        'total_users': stats['total_users'],
        'active_users': stats['active_users'],
        'error_rate': error_rate,
        'avg_uptime': stats['system_uptime'] / max(stats['active_users'], 1),
        'last_cleanup': stats['last_cleanup'],
        'performance_score': max(0, 100 - error_rate * 10)
    }