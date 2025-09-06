# FINAL CODE
# tests/mocks/mock_database.py

import sqlite3
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from unittest.mock import Mock, patch


class MockDatabase:
    """
    데이터베이스 Mock 클래스
    - 실제 DB 연결 없이 테스트용 가상 데이터를 제공
    """
    
    def __init__(self):
        self.accounts = {}
        self.positions = {}
        self.orders = []
        self.trades = []
        self.signals = []
        self.logs = []
        self.params = []
        
        # 기본 계정 생성
        self.create_or_init_account('test_user', 10000000)
        
    def create_or_init_account(self, user_id: str, initial_balance: float = 10000000):
        """계정 생성 또는 초기화"""
        self.accounts[user_id] = {
            'user_id': user_id,
            'krw_balance': initial_balance,
            'total_balance': initial_balance,
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        }
        
    def get_account(self, user_id: str) -> Optional[Dict]:
        """계정 정보 조회"""
        return self.accounts.get(user_id)
    
    def update_account(self, user_id: str, balance_change: float):
        """계정 잔고 업데이트"""
        if user_id in self.accounts:
            self.accounts[user_id]['krw_balance'] += balance_change
            self.accounts[user_id]['total_balance'] += balance_change
            self.accounts[user_id]['updated_at'] = datetime.now().isoformat()
    
    def get_coin_balance(self, user_id: str, ticker: str) -> float:
        """코인 잔고 조회"""
        key = f"{user_id}_{ticker}"
        return self.positions.get(key, {}).get('quantity', 0)
    
    def update_coin_position(self, user_id: str, ticker: str, quantity: float, price: float):
        """코인 포지션 업데이트"""
        key = f"{user_id}_{ticker}"
        
        if key not in self.positions:
            self.positions[key] = {
                'user_id': user_id,
                'ticker': ticker,
                'quantity': 0,
                'avg_price': 0,
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat()
            }
        
        # 평균 가격 계산
        if quantity > 0:  # 매수
            current_qty = self.positions[key]['quantity']
            current_avg = self.positions[key]['avg_price']
            
            if current_qty > 0:
                total_cost = current_qty * current_avg + quantity * price
                total_qty = current_qty + quantity
                new_avg = total_cost / total_qty
            else:
                new_avg = price
            
            self.positions[key]['avg_price'] = new_avg
        
        self.positions[key]['quantity'] += quantity
        self.positions[key]['updated_at'] = datetime.now().isoformat()
    
    def insert_order(self, user_id: str, ticker: str, side: str, price: float, 
                    quantity: float, status: str, **kwargs):
        """주문 기록 삽입"""
        order = {
            'uuid': f'order_{len(self.orders)}',
            'user_id': user_id,
            'ticker': ticker,
            'side': side,
            'price': price,
            'quantity': quantity,
            'status': status,
            'created_at': datetime.now().isoformat(),
            **kwargs
        }
        self.orders.append(order)
        return order
    
    def get_orders(self, user_id: str, limit: int = 50) -> List[Dict]:
        """주문 목록 조회"""
        user_orders = [order for order in self.orders if order['user_id'] == user_id]
        return user_orders[-limit:]
    
    def insert_signal(self, user_id: str, ticker: str, signal_type: str, 
                     confidence: float, metadata: Dict):
        """시그널 기록 삽입"""
        signal = {
            'id': f'signal_{len(self.signals)}',
            'user_id': user_id,
            'ticker': ticker,
            'signal_type': signal_type,
            'confidence': confidence,
            'metadata': json.dumps(metadata),
            'created_at': datetime.now().isoformat()
        }
        self.signals.append(signal)
        return signal
    
    def get_signals(self, user_id: str, limit: int = 100) -> List[Dict]:
        """시그널 목록 조회"""
        user_signals = [signal for signal in self.signals if signal['user_id'] == user_id]
        return user_signals[-limit:]
    
    def insert_log(self, user_id: str, level: str, message: str, **kwargs):
        """로그 기록 삽입"""
        log = {
            'id': f'log_{len(self.logs)}',
            'user_id': user_id,
            'level': level,
            'message': message,
            'created_at': datetime.now().isoformat(),
            **kwargs
        }
        self.logs.append(log)
        return log
    
    def get_logs(self, user_id: str, level: str = None, limit: int = 100) -> List[Dict]:
        """로그 목록 조회"""
        user_logs = [log for log in self.logs if log['user_id'] == user_id]
        if level:
            user_logs = [log for log in user_logs if log['level'] == level]
        return user_logs[-limit:]
    
    def get_latest_params(self, user_id: str, ticker: str) -> Optional[Dict]:
        """최신 파라미터 조회"""
        for param in reversed(self.params):
            if param['user_id'] == user_id and param['ticker'] == ticker:
                return param
        return None
    
    def update_params(self, user_id: str, ticker: str, params_data: Dict):
        """파라미터 업데이트"""
        param = {
            'id': f'param_{len(self.params)}',
            'user_id': user_id,
            'ticker': ticker,
            'params_data': json.dumps(params_data),
            'created_at': datetime.now().isoformat()
        }
        self.params.append(param)
        return param
    
    def get_position_history(self, user_id: str, limit: int = 50) -> List[Dict]:
        """포지션 히스토리 조회"""
        # 테스트용 간단한 히스토리 생성
        history = []
        for key, position in self.positions.items():
            if position['user_id'] == user_id:
                history.append({
                    'id': f'pos_hist_{len(history)}',
                    'user_id': user_id,
                    'ticker': position['ticker'],
                    'quantity': position['quantity'],
                    'avg_price': position['avg_price'],
                    'created_at': position['created_at']
                })
        return history[-limit:]
    
    def insert_account_history(self, user_id: str, balance: float, type: str):
        """계정 히스토리 삽입"""
        history = {
            'id': f'acc_hist_{len(self.logs)}',
            'user_id': user_id,
            'balance': balance,
            'type': type,
            'created_at': datetime.now().isoformat()
        }
        self.logs.append(history)
        return history
    
    def insert_position_history(self, user_id: str, ticker: str, quantity: float, 
                               price: float, type: str):
        """포지션 히스토리 삽입"""
        history = {
            'id': f'pos_hist_{len(self.logs)}',
            'user_id': user_id,
            'ticker': ticker,
            'quantity': quantity,
            'price': price,
            'type': type,
            'created_at': datetime.now().isoformat()
        }
        self.logs.append(history)
        return history
    
    def reset(self):
        """Mock 상태 초기화"""
        self.accounts = {}
        self.positions = {}
        self.orders = []
        self.trades = []
        self.signals = []
        self.logs = []
        self.params = []
        self.create_or_init_account('test_user', 10000000)


# Mock 팩토리 함수
def mock_database_factory():
    """Mock 데이터베이스 객체 생성"""
    return MockDatabase()


# Mock 서비스 함수들
def get_mock_db_manager():
    """Mock DB 관리자 생성"""
    mock_db = MockDatabase()
    
    mock_manager = Mock()
    mock_manager.create_or_init_account = mock_db.create_or_init_account
    mock_manager.get_account = mock_db.get_account
    mock_manager.update_account = mock_db.update_account
    mock_manager.get_coin_balance = mock_db.get_coin_balance
    mock_manager.update_coin_position = mock_db.update_coin_position
    mock_manager.insert_order = mock_db.insert_order
    mock_manager.get_orders = mock_db.get_orders
    mock_manager.insert_signal = mock_db.insert_signal
    mock_manager.get_signals = mock_db.get_signals
    mock_manager.insert_log = mock_db.insert_log
    mock_manager.get_logs = mock_db.get_logs
    mock_manager.get_latest_params = mock_db.get_latest_params
    mock_manager.update_params = mock_db.update_params
    mock_manager.get_position_history = mock_db.get_position_history
    mock_manager.insert_account_history = mock_db.insert_account_history
    mock_manager.insert_position_history = mock_db.insert_position_history
    mock_manager.reset = mock_db.reset
    
    return mock_manager


# 기존 DB 함수 Mock 버전
def get_account(user_id: str):
    """계정 정보 조회 Mock"""
    mock_db = MockDatabase()
    return mock_db.get_account(user_id)


def get_coin_balance(user_id: str, ticker: str):
    """코인 잔고 조회 Mock"""
    mock_db = MockDatabase()
    return mock_db.get_coin_balance(user_id, ticker)


def create_or_init_account(user_id: str, initial_balance: float = 10000000):
    """계정 생성 Mock"""
    mock_db = MockDatabase()
    mock_db.create_or_init_account(user_id, initial_balance)


def update_account(user_id: str, balance_change: float):
    """계정 업데이트 Mock"""
    mock_db = MockDatabase()
    mock_db.update_account(user_id, balance_change)


def update_coin_position(user_id: str, ticker: str, quantity: float, price: float):
    """코인 포지션 업데이트 Mock"""
    mock_db = MockDatabase()
    mock_db.update_coin_position(user_id, ticker, quantity, price)


def insert_order(user_id: str, ticker: str, side: str, price: float, 
                quantity: float, status: str, **kwargs):
    """주문 삽입 Mock"""
    mock_db = MockDatabase()
    return mock_db.insert_order(user_id, ticker, side, price, quantity, status, **kwargs)


def insert_signal(user_id: str, ticker: str, signal_type: str, 
                 confidence: float, metadata: Dict):
    """시그널 삽입 Mock"""
    mock_db = MockDatabase()
    return mock_db.insert_signal(user_id, ticker, signal_type, confidence, metadata)


def insert_log(user_id: str, level: str, message: str, **kwargs):
    """로그 삽입 Mock"""
    mock_db = MockDatabase()
    return mock_db.insert_log(user_id, level, message, **kwargs)