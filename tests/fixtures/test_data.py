# FINAL CODE
# tests/fixtures/test_data.py

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Any


class TestDataGenerator:
    """
    테스트 데이터 생성기
    - 다양한 시나리오에 맞는 테스트 데이터를 생성
    """
    
    @staticmethod
    def generate_ohlcv_data(
        start_price: float = 50000,
        periods: int = 200,
        trend: str = 'sideways',
        volatility: float = 0.02,
        noise_level: float = 0.01
    ) -> pd.DataFrame:
        """
        OHLCV 데이터 생성
        
        Args:
            start_price: 시작 가격
            periods: 데이터 기간
            trend: 추세 ('up', 'down', 'sideways')
            volatility: 변동성
            noise_level: 노이즈 수준
        """
        np.random.seed(42)  # 재현성을 위한 시드
        
        # 추세 설정
        if trend == 'up':
            trend_factor = 0.001
        elif trend == 'down':
            trend_factor = -0.001
        else:  # sideways
            trend_factor = 0
        
        # 가격 시계열 생성
        prices = [start_price]
        for i in range(1, periods):
            # 추세 + 변동성 + 노이즈
            price_change = trend_factor + np.random.normal(0, volatility)
            new_price = prices[-1] * (1 + price_change)
            prices.append(max(new_price, start_price * 0.1))  # 최소 가격 제한
        
        # OHLCV 생성
        data = []
        for i in range(len(prices)):
            base_price = prices[i]
            
            # 일일 변동성
            daily_volatility = volatility * base_price
            
            open_price = base_price
            close_price = base_price * (1 + np.random.normal(0, noise_level))
            high_price = max(open_price, close_price) * (1 + abs(np.random.normal(0, noise_level)))
            low_price = min(open_price, close_price) * (1 - abs(np.random.normal(0, noise_level)))
            
            volume = np.random.uniform(100, 1000)
            
            data.append({
                'open': open_price,
                'high': high_price,
                'low': low_price,
                'close': close_price,
                'volume': volume
            })
        
        df = pd.DataFrame(data)
        return df
    
    @staticmethod
    def generate_golden_cross_data() -> pd.DataFrame:
        """골든크로스가 발생하는 데이터 생성"""
        np.random.seed(42)
        
        # 초기 가격 설정
        base_price = 50000
        prices = [base_price]
        
        # 하락 추세 생성
        for i in range(50):
            change = np.random.normal(-0.005, 0.02)
            new_price = prices[-1] * (1 + change)
            prices.append(max(new_price, base_price * 0.7))
        
        # 상승 추세 생성 (골든크로스 유발)
        for i in range(50):
            change = np.random.normal(0.005, 0.015)
            new_price = prices[-1] * (1 + change)
            prices.append(new_price)
        
        # OHLCV 생성
        data = []
        for i in range(len(prices)):
            base_price = prices[i]
            
            open_price = base_price
            close_price = base_price * (1 + np.random.normal(0, 0.01))
            high_price = max(open_price, close_price) * (1 + abs(np.random.normal(0, 0.005)))
            low_price = min(open_price, close_price) * (1 - abs(np.random.normal(0, 0.005)))
            volume = np.random.uniform(100, 1000)
            
            data.append({
                'open': open_price,
                'high': high_price,
                'low': low_price,
                'close': close_price,
                'volume': volume
            })
        
        return pd.DataFrame(data)
    
    @staticmethod
    def generate_dead_cross_data() -> pd.DataFrame:
        """데드크로스가 발생하는 데이터 생성"""
        np.random.seed(42)
        
        # 초기 가격 설정
        base_price = 50000
        prices = [base_price]
        
        # 상승 추세 생성
        for i in range(50):
            change = np.random.normal(0.005, 0.02)
            new_price = prices[-1] * (1 + change)
            prices.append(new_price)
        
        # 하락 추세 생성 (데드크로스 유발)
        for i in range(50):
            change = np.random.normal(-0.005, 0.015)
            new_price = prices[-1] * (1 + change)
            prices.append(max(new_price, base_price * 0.7))
        
        # OHLCV 생성
        data = []
        for i in range(len(prices)):
            base_price = prices[i]
            
            open_price = base_price
            close_price = base_price * (1 + np.random.normal(0, 0.01))
            high_price = max(open_price, close_price) * (1 + abs(np.random.normal(0, 0.005)))
            low_price = min(open_price, close_price) * (1 - abs(np.random.normal(0, 0.005)))
            volume = np.random.uniform(100, 1000)
            
            data.append({
                'open': open_price,
                'high': high_price,
                'low': low_price,
                'close': close_price,
                'volume': volume
            })
        
        return pd.DataFrame(data)
    
    @staticmethod
    def generate_volatility_spike_data() -> pd.DataFrame:
        """변동성 급증 데이터 생성"""
        np.random.seed(42)
        
        # 일반적인 데이터 생성
        normal_data = TestDataGenerator.generate_ohlcv_data(
            start_price=50000,
            periods=80,
            trend='sideways',
            volatility=0.02
        )
        
        # 변동성 급증 구간 추가
        spike_prices = []
        last_price = normal_data.iloc[-1]['close']
        
        for i in range(20):
            # 높은 변동성
            change = np.random.normal(0, 0.05)  # 5% 변동성
            new_price = last_price * (1 + change)
            spike_prices.append(max(new_price, last_price * 0.8))
            last_price = new_price
        
        # 스파이크 데이터 OHLCV 생성
        spike_data = []
        for price in spike_prices:
            open_price = price
            close_price = price * (1 + np.random.normal(0, 0.03))
            high_price = max(open_price, close_price) * (1 + abs(np.random.normal(0, 0.02)))
            low_price = min(open_price, close_price) * (1 - abs(np.random.normal(0, 0.02)))
            volume = np.random.uniform(500, 2000)  # 거래량 증가
            
            spike_data.append({
                'open': open_price,
                'high': high_price,
                'low': low_price,
                'close': close_price,
                'volume': volume
            })
        
        # 데이터 결합
        combined_data = pd.concat([normal_data, pd.DataFrame(spike_data)], ignore_index=True)
        return combined_data
    
    @staticmethod
    def generate_whipsaw_data() -> pd.DataFrame:
        """휩소우(급변동) 데이터 생성"""
        np.random.seed(42)
        
        prices = [50000]
        
        # 급변동 시장 시뮬레이션
        for i in range(100):
            # 30% 확률로 큰 변동, 70% 확률로 작은 변동
            if np.random.random() < 0.3:
                change = np.random.normal(0, 0.04)  # 4% 큰 변동
            else:
                change = np.random.normal(0, 0.01)  # 1% 작은 변동
            
            new_price = prices[-1] * (1 + change)
            prices.append(max(new_price, 30000))
        
        # OHLCV 생성
        data = []
        for i in range(len(prices)):
            base_price = prices[i]
            
            open_price = base_price
            close_price = base_price * (1 + np.random.normal(0, 0.015))
            high_price = max(open_price, close_price) * (1 + abs(np.random.normal(0, 0.01)))
            low_price = min(open_price, close_price) * (1 - abs(np.random.normal(0, 0.01)))
            volume = np.random.uniform(100, 1500)
            
            data.append({
                'open': open_price,
                'high': high_price,
                'low': low_price,
                'close': close_price,
                'volume': volume
            })
        
        return pd.DataFrame(data)
    
    @staticmethod
    def get_test_scenarios() -> Dict[str, pd.DataFrame]:
        """다양한 테스트 시나리오 데이터 반환"""
        return {
            'sideways': TestDataGenerator.generate_ohlcv_data(trend='sideways'),
            'uptrend': TestDataGenerator.generate_ohlcv_data(trend='up'),
            'downtrend': TestDataGenerator.generate_ohlcv_data(trend='down'),
            'golden_cross': TestDataGenerator.generate_golden_cross_data(),
            'dead_cross': TestDataGenerator.generate_dead_cross_data(),
            'volatility_spike': TestDataGenerator.generate_volatility_spike_data(),
            'whipsaw': TestDataGenerator.generate_whipsaw_data()
        }


class TestConfig:
    """
    테스트 설정 관리
    """
    
    # 기본 테스트 설정
    DEFAULT_USER_ID = 'test_user'
    DEFAULT_TICKER = 'KRW-BTC'
    DEFAULT_INTERVAL = 'minute5'
    DEFAULT_RISK_PCT = 0.1
    DEFAULT_TEST_MODE = True
    
    # 전략 파라미터
    STRATEGY_PARAMS = {
        'entry_delay_bars': 3,
        'min_holding_period': 5,
        'volatility_window': 20,
        'atr_period': 14,
        'ma_period': 20,
        'enable_ma_filter': True,
        'enable_volatility_adjustment': True,
        'enable_signal_confirmation': True,
        'risk_per_trade': 0.02,
        'max_position_size': 1.0,
        'signal_threshold': 0.6,
        'tp_multiplier': 2.0,
        'sl_multiplier': 1.0,
        'volatility_multiplier': 1.5
    }
    
    # 테스트 잔고 설정
    INITIAL_BALANCE = 10000000  # 1천만 원
    COIN_BALANCES = {
        'BTC': 0.0,
        'ETH': 0.0,
        'XRP': 0.0,
        'ADA': 0.0,
        'DOGE': 0.0
    }
    
    # 테스트 가격 설정
    TEST_PRICES = {
        'KRW-BTC': 50000000,
        'KRW-ETH': 3000000,
        'KRW-XRP': 500,
        'KRW-ADA': 400,
        'KRW-DOGE': 100
    }


# 유틸리티 함수
def create_test_config(**kwargs) -> Dict[str, Any]:
    """테스트 설정 생성"""
    config = TestConfig.STRATEGY_PARAMS.copy()
    config.update({
        'user_id': kwargs.get('user_id', TestConfig.DEFAULT_USER_ID),
        'ticker': kwargs.get('ticker', TestConfig.DEFAULT_TICKER),
        'interval': kwargs.get('interval', TestConfig.DEFAULT_INTERVAL),
        'risk_pct': kwargs.get('risk_pct', TestConfig.DEFAULT_RISK_PCT),
        'test_mode': kwargs.get('test_mode', TestConfig.DEFAULT_TEST_MODE)
    })
    return config


def get_test_data(scenario: str = 'sideways') -> pd.DataFrame:
    """특정 시나리오의 테스트 데이터 반환"""
    scenarios = TestDataGenerator.get_test_scenarios()
    return scenarios.get(scenario, scenarios['sideways'])


def setup_test_environment():
    """테스트 환경 설정"""
    # 테스트 데이터 생성
    test_scenarios = TestDataGenerator.get_test_scenarios()
    
    # 테스트 설정 생성
    config = create_test_config()
    
    return {
        'scenarios': test_scenarios,
        'config': config,
        'initial_balance': TestConfig.INITIAL_BALANCE,
        'test_prices': TestConfig.TEST_PRICES
    }