# FINAL CODE
# tests/conftest.py

import pytest
import sys
import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# 프로젝트 루트 경로 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.mocks.mock_upbit import MockUpbitAPI, mock_pyupbit_factory
from tests.mocks.mock_database import MockDatabase, get_mock_db_manager
from tests.fixtures.test_data import TestDataGenerator, TestConfig, create_test_config, get_test_data


@pytest.fixture(scope="session")
def test_config():
    """테스트 설정 fixture"""
    return TestConfig


@pytest.fixture(scope="session")
def data_generator():
    """데이터 생성기 fixture"""
    return TestDataGenerator()


@pytest.fixture(scope="session")
def test_scenarios(data_generator):
    """테스트 시나리오 fixture"""
    return data_generator.get_test_scenarios()


@pytest.fixture(scope="function")
def mock_upbit():
    """Mock Upbit API fixture"""
    mock_api = MockUpbitAPI()
    yield mock_api
    mock_api.reset()


@pytest.fixture(scope="function")
def mock_database():
    """Mock Database fixture"""
    mock_db = MockDatabase()
    yield mock_db
    mock_db.reset()


@pytest.fixture(scope="function")
def mock_db_manager(mock_database):
    """Mock DB Manager fixture"""
    return get_mock_db_manager()


@pytest.fixture(scope="function")
def sample_data():
    """샘플 데이터 fixture"""
    return get_test_data('sideways')


@pytest.fixture(scope="function")
def golden_cross_data():
    """골든크로스 데이터 fixture"""
    return get_test_data('golden_cross')


@pytest.fixture(scope="function")
def dead_cross_data():
    """데드크로스 데이터 fixture"""
    return get_test_data('dead_cross')


@pytest.fixture(scope="function")
def volatility_spike_data():
    """변동성 급증 데이터 fixture"""
    return get_test_data('volatility_spike')


@pytest.fixture(scope="function")
def whipsaw_data():
    """휩소우 데이터 fixture"""
    return get_test_data('whipsaw')


@pytest.fixture(scope="function")
def strategy_config():
    """전략 설정 fixture"""
    from core.strategy_v2 import StrategyConfig
    
    return StrategyConfig(
        user_id=TestConfig.DEFAULT_USER_ID,
        ticker=TestConfig.DEFAULT_TICKER,
        entry_delay_bars=3,
        min_holding_period=5,
        volatility_window=20,
        atr_period=14,
        ma_period=20,
        enable_ma_filter=True,
        enable_volatility_adjustment=True,
        enable_signal_confirmation=True,
        risk_per_trade=0.02,
        max_position_size=1.0,
        signal_threshold=0.6,
        tp_multiplier=2.0,
        sl_multiplier=1.0,
        volatility_multiplier=1.5
    )


@pytest.fixture(scope="function")
def trader_config():
    """트레이더 설정 fixture"""
    return {
        'user_id': TestConfig.DEFAULT_USER_ID,
        'risk_pct': TestConfig.DEFAULT_RISK_PCT,
        'test_mode': TestConfig.DEFAULT_TEST_MODE
    }


@pytest.fixture(scope="function")
def engine_config():
    """엔진 설정 fixture"""
    return {
        'user_id': TestConfig.DEFAULT_USER_ID,
        'max_position_size': 1.0,
        'max_daily_loss': 0.1,
        'enable_risk_management': True,
        'enable_performance_tracking': True
    }


# pytest 커스텀 마커
def pytest_configure(config):
    """pytest 설정"""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests"
    )
    config.addinivalue_line(
        "markers", "unit: marks tests as unit tests"
    )
    config.addinivalue_line(
        "markers", "performance: marks tests as performance tests"
    )


# 테스트 데이터 생성 헬퍼 함수
@pytest.fixture(scope="function")
def create_custom_data():
    """커스텀 데이터 생성 헬퍼"""
    def _create_data(start_price=50000, periods=100, trend='sideways', volatility=0.02):
        return TestDataGenerator.generate_ohlcv_data(
            start_price=start_price,
            periods=periods,
            trend=trend,
            volatility=volatility
        )
    return _create_data


# Mock 설정 헬퍼 함수
@pytest.fixture(scope="function")
def setup_mocks():
    """Mock 설정 헬퍼"""
    def _setup_mocks(user_id='test_user', initial_balance=10000000):
        mock_db = MockDatabase()
        mock_db.create_or_init_account(user_id, initial_balance)
        
        mock_upbit = MockUpbitAPI()
        
        return {
            'mock_db': mock_db,
            'mock_upbit': mock_upbit,
            'user_id': user_id,
            'initial_balance': initial_balance
        }
    return _setup_mocks


# 테스트 결과 검증 헬퍼 함수
@pytest.fixture(scope="function")
def validate_results():
    """결과 검증 헬퍼"""
    def _validate(results, expected_keys=None, expected_types=None):
        if expected_keys:
            for key in expected_keys:
                assert key in results, f"Expected key '{key}' not found in results"
        
        if expected_types:
            for key, expected_type in expected_types.items():
                if key in results:
                    assert isinstance(results[key], expected_type), \
                        f"Expected type {expected_type} for key '{key}', got {type(results[key])}"
    
    return _validate


# 성능 측정 헬퍼 함수
@pytest.fixture(scope="function")
def measure_performance():
    """성능 측정 헬퍼"""
    import time
    import psutil
    import os
    
    def _measure(func, *args, **kwargs):
        # 시작 시간 및 메모리
        start_time = time.time()
        process = psutil.Process(os.getpid())
        start_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # 함수 실행
        result = func(*args, **kwargs)
        
        # 종료 시간 및 메모리
        end_time = time.time()
        end_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # 성능 메트릭
        execution_time = end_time - start_time
        memory_usage = end_memory - start_memory
        
        return {
            'result': result,
            'execution_time': execution_time,
            'memory_usage': memory_usage,
            'start_time': start_time,
            'end_time': end_time
        }
    
    return _measure


# 예외 처리 테스트 헬퍼 함수
@pytest.fixture(scope="function")
def expect_exception():
    """예외 처리 테스트 헬퍼"""
    def _expect(func, exception_type, *args, **kwargs):
        try:
            func(*args, **kwargs)
            return False, None  # 예외가 발생하지 않음
        except exception_type as e:
            return True, e  # 예외가 발생함
        except Exception as e:
            return False, e  # 다른 타입의 예외가 발생함
    
    return _expect


# 데이터베이스 상태 검증 헬퍼 함수
@pytest.fixture(scope="function")
def validate_db_state():
    """DB 상태 검증 헬퍼"""
    def _validate(mock_db, user_id, expected_balance=None, expected_orders=None):
        # 계정 상태 검증
        account = mock_db.get_account(user_id)
        assert account is not None, f"Account not found for user {user_id}"
        
        if expected_balance is not None:
            assert account['krw_balance'] == expected_balance, \
                f"Expected balance {expected_balance}, got {account['krw_balance']}"
        
        # 주문 내역 검증
        orders = mock_db.get_orders(user_id)
        if expected_orders is not None:
            assert len(orders) == expected_orders, \
                f"Expected {expected_orders} orders, got {len(orders)}"
        
        return {
            'account': account,
            'orders': orders,
            'signals': mock_db.get_signals(user_id),
            'logs': mock_db.get_logs(user_id)
        }
    
    return _validate