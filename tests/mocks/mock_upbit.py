# FINAL CODE
# tests/mocks/mock_upbit.py

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from unittest.mock import Mock, patch


class MockUpbitAPI:
    """
    Upbit API Mock 클래스
    - 실제 API 호출 없이 테스트용 가상 데이터를 제공
    """
    
    def __init__(self):
        self.mock_prices = {
            'KRW-BTC': 50000000,
            'KRW-ETH': 3000000,
            'KRW-XRP': 500,
            'KRW-ADA': 400,
            'KRW-DOGE': 100
        }
        
        self.mock_balances = {
            'KRW': 10000000,
            'BTC': 0.1,
            'ETH': 1.0,
            'XRP': 100,
            'ADA': 200,
            'DOGE': 1000
        }
        
        self.mock_orders = []
        self.mock_trades = []
        
    def get_current_price(self, ticker: str) -> float:
        """현재 가격 반환"""
        if ticker not in self.mock_prices:
            raise ValueError(f"지원하지 않는 티커: {ticker}")
        return self.mock_prices[ticker]
    
    def get_ohlcv(self, ticker: str, interval: str = 'minute5', count: int = 200) -> pd.DataFrame:
        """OHLCV 데이터 반환"""
        if ticker not in self.mock_prices:
            raise ValueError(f"지원하지 않는 티커: {ticker}")
        
        base_price = self.mock_prices[ticker]
        
        # 가상 데이터 생성
        now = datetime.now()
        data = []
        
        for i in range(count):
            timestamp = now - timedelta(minutes=i * 5)
            
            # 가격 변동성 추가
            volatility = 0.02  # 2% 변동성
            price_change = np.random.normal(0, volatility)
            
            open_price = base_price * (1 + price_change)
            close_price = open_price * (1 + np.random.normal(0, volatility * 0.5))
            high_price = max(open_price, close_price) * (1 + abs(np.random.normal(0, volatility * 0.3)))
            low_price = min(open_price, close_price) * (1 - abs(np.random.normal(0, volatility * 0.3)))
            
            volume = np.random.uniform(100, 1000)
            
            data.append({
                'open': open_price,
                'high': high_price,
                'low': low_price,
                'close': close_price,
                'volume': volume
            })
            
            base_price = close_price
        
        df = pd.DataFrame(data[::-1])  # 시간순 정렬
        return df
    
    def get_balance(self, ticker: str = None) -> Dict:
        """잔고 정보 반환"""
        if ticker is None:
            # 전체 잔고 반환
            return [
                {
                    'currency': currency,
                    'balance': str(balance),
                    'avg_buy_price': '0' if balance == 0 else str(self.mock_prices.get(f'KRW-{currency}', 0))
                }
                for currency, balance in self.mock_balances.items()
            ]
        else:
            # 특정 통화 잔고 반환
            if ticker == 'KRW':
                return str(self.mock_balances['KRW'])
            else:
                currency = ticker.split('-')[1]
                return str(self.mock_balances.get(currency, 0))
    
    def get_balances(self) -> List[Dict]:
        """전체 잔고 정보 반환"""
        return self.get_balance()
    
    def buy_market_order(self, ticker: str, volume: float) -> Dict:
        """매수 주문 실행"""
        price = self.get_current_price(ticker)
        total = price * volume
        
        if total > self.mock_balances['KRW']:
            return {'error': 'Insufficient balance'}
        
        # 잔고 업데이트
        self.mock_balances['KRW'] -= total
        
        currency = ticker.split('-')[1]
        self.mock_balances[currency] = self.mock_balances.get(currency, 0) + volume
        
        order = {
            'uuid': f'order_{len(self.mock_orders)}',
            'side': 'bid',
            'ord_type': 'market',
            'market': ticker,
            'volume': str(volume),
            'price': str(price),
            'state': 'done',
            'created_at': datetime.now().isoformat()
        }
        
        self.mock_orders.append(order)
        
        trade = {
            'uuid': f'trade_{len(self.mock_trades)}',
            'order_uuid': order['uuid'],
            'side': 'bid',
            'market': ticker,
            'volume': str(volume),
            'price': str(price),
            'created_at': datetime.now().isoformat()
        }
        
        self.mock_trades.append(trade)
        
        return order
    
    def sell_market_order(self, ticker: str, volume: float) -> Dict:
        """매도 주문 실행"""
        currency = ticker.split('-')[1]
        
        if self.mock_balances.get(currency, 0) < volume:
            return {'error': 'Insufficient balance'}
        
        price = self.get_current_price(ticker)
        total = price * volume
        
        # 잔고 업데이트
        self.mock_balances[currency] -= volume
        self.mock_balances['KRW'] += total
        
        order = {
            'uuid': f'order_{len(self.mock_orders)}',
            'side': 'ask',
            'ord_type': 'market',
            'market': ticker,
            'volume': str(volume),
            'price': str(price),
            'state': 'done',
            'created_at': datetime.now().isoformat()
        }
        
        self.mock_orders.append(order)
        
        trade = {
            'uuid': f'trade_{len(self.mock_trades)}',
            'order_uuid': order['uuid'],
            'side': 'ask',
            'market': ticker,
            'volume': str(volume),
            'price': str(price),
            'created_at': datetime.now().isoformat()
        }
        
        self.mock_trades.append(trade)
        
        return order
    
    def get_order(self, uuid: str) -> Optional[Dict]:
        """주문 정보 조회"""
        for order in self.mock_orders:
            if order['uuid'] == uuid:
                return order
        return None
    
    def get_orders(self, state: str = 'done') -> List[Dict]:
        """주문 목록 조회"""
        return [order for order in self.mock_orders if order['state'] == state]
    
    def get_trades(self, ticker: str = None) -> List[Dict]:
        """체결 내역 조회"""
        if ticker:
            return [trade for trade in self.mock_trades if trade['market'] == ticker]
        return self.mock_trades
    
    def reset(self):
        """Mock 상태 초기화"""
        self.mock_balances = {
            'KRW': 10000000,
            'BTC': 0.1,
            'ETH': 1.0,
            'XRP': 100,
            'ADA': 200,
            'DOGE': 1000
        }
        self.mock_orders = []
        self.mock_trades = []


def mock_pyupbit_factory():
    """PyUpbit Mock 객체 생성 팩토리"""
    mock_upbit = MockUpbitAPI()
    
    # Mock 객체 생성
    mock = Mock()
    
    # Mock 메서드 설정
    mock.get_current_price = mock_upbit.get_current_price
    mock.get_ohlcv = mock_upbit.get_ohlcv
    mock.get_balance = mock_upbit.get_balance
    mock.get_balances = mock_upbit.get_balances
    mock.buy_market_order = mock_upbit.buy_market_order
    mock.sell_market_order = mock_upbit.sell_market_order
    mock.get_order = mock_upbit.get_order
    mock.get_orders = mock_upbit.get_orders
    mock.get_trades = mock_upbit.get_trades
    mock.reset = mock_upbit.reset
    
    return mock