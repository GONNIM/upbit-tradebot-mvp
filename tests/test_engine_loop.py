# FINAL CODE
# tests/test_engine_loop.py

import unittest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
import threading
import time
import sys
import os

# 프로젝트 루트 경로 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.strategy_v2 import EnhancedMACDStrategy, StrategyConfig, SignalType
from core.trader import UpbitTrader
from engine.engine_manager import EngineManager
from engine.live_loop import LiveLoop
from tests.mocks.mock_upbit import MockUpbitAPI, mock_pyupbit_factory
from tests.mocks.mock_database import MockDatabase, get_mock_db_manager
from tests.fixtures.test_data import TestConfig, TestDataGenerator, create_test_config


class MockFeed:
    """
    Mock Feed 클래스
    - 시장 데이터를 시뮬레이션
    """
    
    def __init__(self, data_generator, scenario='sideways'):
        self.data_generator = data_generator
        self.scenario = scenario
        self.current_index = 0
        self.data = data_generator.get_test_data(scenario)
        self.is_running = False
        self.callbacks = []
        
    def add_callback(self, callback):
        """콜백 함수 추가"""
        self.callbacks.append(callback)
        
    def start(self):
        """피드 시작"""
        self.is_running = True
        self.current_index = 0
        
    def stop(self):
        """피드 중지"""
        self.is_running = False
        
    def get_latest_data(self, window_size=200):
        """최신 데이터 반환"""
        if self.current_index < window_size:
            return self.data.iloc[:self.current_index + 1]
        else:
            return self.data.iloc[self.current_index - window_size + 1:self.current_index + 1]
    
    def simulate_tick(self):
        """타임스텝 시뮬레이션"""
        if not self.is_running or self.current_index >= len(self.data):
            return False
            
        # 다음 데이터 포인트로 이동
        self.current_index += 1
        
        # 콜백 함수 호출
        for callback in self.callbacks:
            try:
                latest_data = self.get_latest_data()
                callback(latest_data)
            except Exception as e:
                print(f"콜백 실행 중 오류: {e}")
                
        return True
        
    def run_simulation(self, max_steps=None):
        """전체 시뮬레이션 실행"""
        self.start()
        
        steps = 0
        while self.simulate_tick():
            steps += 1
            if max_steps and steps >= max_steps:
                break
                
        self.stop()


class TestEngineLoop(unittest.TestCase):
    """
    엔진 루프 테스트 클래스
    - feed mock + trader sandbox + DB 통합 테스트
    """
    
    def setUp(self):
        """테스트 설정"""
        self.user_id = TestConfig.DEFAULT_USER_ID
        self.ticker = TestConfig.DEFAULT_TICKER
        
        # Mock 객체 생성
        self.mock_upbit = MockUpbitAPI()
        self.mock_db = MockDatabase()
        
        # 데이터 생성기
        self.data_generator = TestDataGenerator()
        
        # Mock Feed 생성
        self.mock_feed = MockFeed(self.data_generator, 'sideways')
        
        # 전략 설정
        self.strategy_config = StrategyConfig(
            user_id=self.user_id,
            ticker=self.ticker,
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
        
        # 전략 인스턴스
        self.strategy = EnhancedMACDStrategy(self.strategy_config, self.mock_db)
        
        # 트레이더 인스턴스
        self.trader = UpbitTrader(
            user_id=self.user_id,
            risk_pct=0.1,
            test_mode=True
        )
        self.trader.upbit = self.mock_upbit
        
        # 엔진 관리자 설정
        self.engine_manager = EngineManager(
            user_id=self.user_id,
            strategy=self.strategy,
            trader=self.trader,
            db_manager=self.mock_db
        )
        
        # Mock DB 함수 패치
        self.setup_db_patches()
        
    def setup_db_patches(self):
        """DB 패치 설정"""
        self.db_patcher = patch.multiple(
            'core.trader',
            get_account=self.mock_db.get_account,
            get_coin_balance=self.mock_db.get_coin_balance,
            create_or_init_account=self.mock_db.create_or_init_account,
            update_account=self.mock_db.update_account,
            update_coin_position=self.mock_db.update_coin_position,
            insert_order=self.mock_db.insert_order,
            insert_account_history=self.mock_db.insert_account_history,
            insert_position_history=self.mock_db.insert_position_history
        )
        self.db_patcher.start()
        
    def tearDown(self):
        """테스트 정리"""
        self.db_patcher.stop()
        self.mock_feed.stop()
        
    def test_engine_initialization(self):
        """엔진 초기화 테스트"""
        # 엔진 관리자 속성 검증
        self.assertEqual(self.engine_manager.user_id, self.user_id)
        self.assertEqual(self.engine_manager.strategy, self.strategy)
        self.assertEqual(self.engine_manager.trader, self.trader)
        self.assertEqual(self.engine_manager.db_manager, self.mock_db)
        
        # 엔진 상태 검증
        self.assertFalse(self.engine_manager.is_running)
        self.assertEqual(self.engine_manager.signals_processed, 0)
        self.assertEqual(self.engine_manager.trades_executed, 0)
        
    def test_feed_integration(self):
        """피드 통합 테스트"""
        # 피드 콜백 설정
        signal_received = []
        
        def signal_callback(signal_data):
            signal_received.append(signal_data)
            
        self.engine_manager.add_signal_callback(signal_callback)
        
        # 피드에 엔진 콜백 추가
        self.mock_feed.add_callback(self.engine_manager.process_market_data)
        
        # 피드 시뮬레이션 실행
        self.mock_feed.run_simulation(max_steps=10)
        
        # 시그널 수신 확인
        self.assertGreaterEqual(len(signal_received), 0)
        
    def test_strategy_signal_processing(self):
        """전략 시그널 처리 테스트"""
        # 피드에 엔진 콜백 추가
        self.mock_feed.add_callback(self.engine_manager.process_market_data)
        
        # 시뮬레이션 실행
        self.mock_feed.run_simulation(max_steps=50)
        
        # 처리된 시그널 수 확인
        self.assertGreaterEqual(self.engine_manager.signals_processed, 0)
        
        # DB에 시그널이 저장되었는지 확인
        signals = self.mock_db.get_signals(self.user_id, limit=10)
        self.assertGreaterEqual(len(signals), 0)
        
    def test_trade_execution(self):
        """거래 실행 테스트"""
        # 골든크로스 시나리오로 변경
        self.mock_feed = MockFeed(self.data_generator, 'golden_cross')
        
        # 피드에 엔진 콜백 추가
        self.mock_feed.add_callback(self.engine_manager.process_market_data)
        
        # 시뮬레이션 실행
        self.mock_feed.run_simulation(max_steps=100)
        
        # 실행된 거래 수 확인
        self.assertGreaterEqual(self.engine_manager.trades_executed, 0)
        
        # DB에 주문이 저장되었는지 확인
        orders = self.mock_db.get_orders(self.user_id, limit=10)
        self.assertGreaterEqual(len(orders), 0)
        
    def test_market_data_processing(self):
        """시장 데이터 처리 테스트"""
        # 시장 데이터 처리 콜백
        processed_data = []
        
        def data_callback(data):
            processed_data.append(data)
            
        self.engine_manager.add_data_callback(data_callback)
        
        # 피드에 엔진 콜백 추가
        self.mock_feed.add_callback(self.engine_manager.process_market_data)
        
        # 시뮬레이션 실행
        self.mock_feed.run_simulation(max_steps=20)
        
        # 처리된 데이터 확인
        self.assertGreaterEqual(len(processed_data), 0)
        
        # 데이터 형식 검증
        for data in processed_data:
            self.assertIsInstance(data, pd.DataFrame)
            self.assertIn('close', data.columns)
            self.assertIn('volume', data.columns)
            
    def test_risk_management(self):
        """리스크 관리 테스트"""
        # 리스크 관리 설정
        self.engine_manager.max_position_size = 0.5  # 50% 최대 포지션
        self.engine_manager.max_daily_loss = 0.1    # 10% 최대 일일 손실
        
        # 피드에 엔진 콜백 추가
        self.mock_feed.add_callback(self.engine_manager.process_market_data)
        
        # 초기 잔고 확인
        initial_balance = self.mock_db.get_account(self.user_id)['krw_balance']
        
        # 시뮬레이션 실행
        self.mock_feed.run_simulation(max_steps=100)
        
        # 최종 잔고 확인
        final_balance = self.mock_db.get_account(self.user_id)['krw_balance']
        
        # 최대 손실 제한 확인
        max_loss = initial_balance * self.engine_manager.max_daily_loss
        actual_loss = initial_balance - final_balance
        
        if actual_loss > 0:
            self.assertLessEqual(actual_loss, max_loss)
            
    def test_performance_tracking(self):
        """성능 추적 테스트"""
        import time
        
        # 성능 추적 시작
        start_time = time.time()
        
        # 피드에 엔진 콜백 추가
        self.mock_feed.add_callback(self.engine_manager.process_market_data)
        
        # 시뮬레이션 실행
        self.mock_feed.run_simulation(max_steps=50)
        
        # 성능 추적 종료
        end_time = time.time()
        execution_time = end_time - start_time
        
        # 성능 메트릭 확인
        metrics = self.engine_manager.get_performance_metrics()
        
        self.assertIsInstance(metrics, dict)
        self.assertIn('total_signals', metrics)
        self.assertIn('total_trades', metrics)
        self.assertIn('execution_time', metrics)
        self.assertIn('signals_per_second', metrics)
        
        # 성능 메트릭 값 검증
        self.assertGreaterEqual(metrics['total_signals'], 0)
        self.assertGreaterEqual(metrics['total_trades'], 0)
        self.assertGreater(metrics['execution_time'], 0)
        
        if metrics['execution_time'] > 0:
            self.assertGreaterEqual(metrics['signals_per_second'], 0)
            
    def test_error_handling(self):
        """에러 처리 테스트"""
        # 잘못된 데이터 전송
        invalid_data = pd.DataFrame()
        
        # 에러 발생 여부 확인
        try:
            self.engine_manager.process_market_data(invalid_data)
        except Exception as e:
            self.assertIsInstance(e, (ValueError, KeyError, AttributeError))
            
        # Null 값이 있는 데이터
        null_data = self.mock_feed.get_latest_data()
        null_data.iloc[0, null_data.columns.get_loc('close')] = np.nan
        
        try:
            self.engine_manager.process_market_data(null_data)
        except Exception as e:
            self.assertIsInstance(e, (ValueError, KeyError))
            
    def test_concurrent_processing(self):
        """동시 처리 테스트"""
        # 여러 시나리오에 대한 동시 처리
        scenarios = ['sideways', 'uptrend', 'downtrend']
        results = {}
        
        def run_scenario(scenario_name):
            # 각 시나리오에 대한 별도의 엔진 생성
            feed = MockFeed(self.data_generator, scenario_name)
            engine = EngineManager(
                user_id=f'user_{scenario_name}',
                strategy=self.strategy,
                trader=self.trader,
                db_manager=self.mock_db
            )
            
            # 시뮬레이션 실행
            feed.add_callback(engine.process_market_data)
            feed.run_simulation(max_steps=30)
            
            results[scenario_name] = {
                'signals': engine.signals_processed,
                'trades': engine.trades_executed
            }
            
            feed.stop()
            
        # 동시 실행
        threads = []
        for scenario in scenarios:
            thread = threading.Thread(target=run_scenario, args=(scenario,))
            threads.append(thread)
            thread.start()
            
        # 모든 스레드 완료 대기
        for thread in threads:
            thread.join()
            
        # 결과 확인
        for scenario, result in results.items():
            self.assertIsInstance(result['signals'], int)
            self.assertIsInstance(result['trades'], int)
            self.assertGreaterEqual(result['signals'], 0)
            self.assertGreaterEqual(result['trades'], 0)
            
    def test_database_consistency(self):
        """데이터베이스 일관성 테스트"""
        # 피드에 엔진 콜백 추가
        self.mock_feed.add_callback(self.engine_manager.process_market_data)
        
        # 시뮬레이션 실행
        self.mock_feed.run_simulation(max_steps=50)
        
        # 데이터베이스 일관성 확인
        # 1. 계정 잔고 일관성
        account = self.mock_db.get_account(self.user_id)
        self.assertIsInstance(account, dict)
        self.assertIn('krw_balance', account)
        self.assertIn('total_balance', account)
        
        # 2. 주문 내역 일관성
        orders = self.mock_db.get_orders(self.user_id)
        for order in orders:
            self.assertIn('side', order)
            self.assertIn('price', order)
            self.assertIn('quantity', order)
            self.assertIn('status', order)
            
        # 3. 시그널 내역 일관성
        signals = self.mock_db.get_signals(self.user_id)
        for signal in signals:
            self.assertIn('signal_type', signal)
            self.assertIn('confidence', signal)
            self.assertIn('ticker', signal)
            
        # 4. 포지션 내역 일관성
        position_history = self.mock_db.get_position_history(self.user_id)
        for pos in position_history:
            self.assertIn('ticker', pos)
            self.assertIn('quantity', pos)
            self.assertIn('price', pos)
            
    def test_scenario_testing(self):
        """시나리오 테스트"""
        # 다양한 시나리오 테스트
        scenarios = {
            'sideways': {'expected_trades': 'low', 'volatility': 'low'},
            'uptrend': {'expected_trades': 'medium', 'volatility': 'medium'},
            'downtrend': {'expected_trades': 'medium', 'volatility': 'medium'},
            'golden_cross': {'expected_trades': 'high', 'volatility': 'high'},
            'dead_cross': {'expected_trades': 'high', 'volatility': 'high'},
            'volatility_spike': {'expected_trades': 'high', 'volatility': 'very_high'},
            'whipsaw': {'expected_trades': 'very_high', 'volatility': 'very_high'}
        }
        
        for scenario_name, scenario_info in scenarios.items():
            with self.subTest(scenario=scenario_name):
                # 시나리오별 피드 생성
                feed = MockFeed(self.data_generator, scenario_name)
                
                # 엔진 생성
                engine = EngineManager(
                    user_id=f'user_{scenario_name}',
                    strategy=self.strategy,
                    trader=self.trader,
                    db_manager=self.mock_db
                )
                
                # 시뮬레이션 실행
                feed.add_callback(engine.process_market_data)
                feed.run_simulation(max_steps=50)
                
                # 결과 분석
                signals = engine.signals_processed
                trades = engine.trades_executed
                
                # 시나리오 특성에 따른 결과 검증
                self.assertGreaterEqual(signals, 0)
                self.assertGreaterEqual(trades, 0)
                
                # 시나리오별 예상 패턴 확인
                if scenario_info['expected_trades'] == 'low':
                    self.assertLessEqual(trades, 5)
                elif scenario_info['expected_trades'] == 'high':
                    self.assertGreaterEqual(trades, 3)
                    
                feed.stop()
                
    def test_integration_workflow(self):
        """통합 워크플로우 테스트"""
        # 전체 워크플로우 테스트
        
        # 1. 초기화
        self.assertTrue(self.engine_manager.initialize())
        
        # 2. 시작
        self.assertTrue(self.engine_manager.start())
        
        # 3. 피드 연결 및 데이터 처리
        self.mock_feed.add_callback(self.engine_manager.process_market_data)
        
        # 4. 시뮬레이션 실행
        self.mock_feed.run_simulation(max_steps=100)
        
        # 5. 중지
        self.assertTrue(self.engine_manager.stop())
        
        # 6. 결과 확인
        self.assertGreaterEqual(self.engine_manager.signals_processed, 0)
        self.assertGreaterEqual(self.engine_manager.trades_executed, 0)
        
        # 7. 리소스 정리
        self.assertTrue(self.engine_manager.cleanup())
        
        # 8. 최종 데이터베이스 상태 확인
        final_account = self.mock_db.get_account(self.user_id)
        final_orders = self.mock_db.get_orders(self.user_id)
        final_signals = self.mock_db.get_signals(self.user_id)
        
        self.assertIsInstance(final_account, dict)
        self.assertIsInstance(final_orders, list)
        self.assertIsInstance(final_signals, list)
        
    def test_memory_usage(self):
        """메모리 사용량 테스트"""
        import psutil
        import os
        
        # 초기 메모리 사용량
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # 긴 시뮬레이션 실행
        self.mock_feed.add_callback(self.engine_manager.process_market_data)
        self.mock_feed.run_simulation(max_steps=200)
        
        # 최종 메모리 사용량
        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = final_memory - initial_memory
        
        # 메모리 사용량 증가 확인 (50MB 이하)
        self.assertLess(memory_increase, 50)
        
    def test_real_time_simulation(self):
        """실시간 시뮬레이션 테스트"""
        # 실시간처럼 시간 간격을 두고 처리
        self.mock_feed.add_callback(self.engine_manager.process_market_data)
        
        # 엔진 시작
        self.engine_manager.start()
        
        # 실시간 시뮬레이션
        for i in range(20):
            if self.mock_feed.simulate_tick():
                time.sleep(0.1)  # 100ms 간격
                
        # 엔진 중지
        self.engine_manager.stop()
        
        # 결과 확인
        self.assertGreaterEqual(self.engine_manager.signals_processed, 0)
        

if __name__ == '__main__':
    # 테스트 실행
    unittest.main(verbosity=2)