# FINAL CODE
# tests/test_trader_sandbox.py

import unittest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# 프로젝트 루트 경로 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.trader import UpbitTrader
from tests.mocks.mock_upbit import MockUpbitAPI, mock_pyupbit_factory
from tests.mocks.mock_database import MockDatabase, get_mock_db_manager
from tests.fixtures.test_data import TestConfig, TestDataGenerator


class TestTraderSandbox(unittest.TestCase):
    """
    트레이더 샌드박스 테스트 클래스
    - 주문/취소/잔고/체결 흐름 테스트
    """
    
    def setUp(self):
        """테스트 설정"""
        self.user_id = TestConfig.DEFAULT_USER_ID
        self.ticker = TestConfig.DEFAULT_TICKER
        self.test_mode = True
        self.risk_pct = 0.1
        
        # Mock API 설정
        self.mock_upbit = MockUpbitAPI()
        
        # Mock DB 설정
        self.mock_db = MockDatabase()
        
        # 트레이더 인스턴스
        self.trader = UpbitTrader(
            user_id=self.user_id,
            risk_pct=self.risk_pct,
            test_mode=self.test_mode
        )
        
        # 트레이더에 Mock 주입
        self.trader.upbit = self.mock_upbit
        
        # Mock DB 함수 패치
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
        
    def test_initialization(self):
        """트레이더 초기화 테스트"""
        # 트레이더 속성 검증
        self.assertEqual(self.trader.user_id, self.user_id)
        self.assertEqual(self.trader.risk_pct, self.risk_pct)
        self.assertTrue(self.trader.test_mode)
        self.assertIsNone(self.trader.upbit)
        
        # Mock API 주입 테스트
        self.trader.upbit = self.mock_upbit
        self.assertIsNotNone(self.trader.upbit)
        
    def test_krw_balance(self):
        """KRW 잔고 조회 테스트"""
        # 테스트 모드에서의 잔고 조회
        balance = self.trader._krw_balance()
        
        # 결과 검증
        self.assertIsInstance(balance, float)
        self.assertGreaterEqual(balance, 0)
        
        # Mock DB 잔고와 일치하는지 확인
        expected_balance = self.mock_db.get_account(self.user_id)['krw_balance']
        self.assertEqual(balance, expected_balance)
        
    def test_coin_balance(self):
        """코인 잔고 조회 테스트"""
        # 테스트 코인 잔고 조회
        balance = self.trader._coin_balance(self.ticker)
        
        # 결과 검증
        self.assertIsInstance(balance, float)
        self.assertGreaterEqual(balance, 0)
        
        # Mock DB 코인 잔고와 일치하는지 확인
        expected_balance = self.mock_db.get_coin_balance(self.user_id, self.ticker)
        self.assertEqual(balance, expected_balance)
        
        # 존재하지 않는 코인 조회
        unknown_balance = self.trader._coin_balance('KRW-UNKNOWN')
        self.assertEqual(unknown_balance, 0.0)
        
    def test_buy_market_order_calculation(self):
        """매수 주문 계산 테스트"""
        # 테스트 설정
        price = 50000
        expected_krw = 1000000  # 100만 원
        
        # 수수료 계산
        fee_ratio = 0.0005
        expected_qty = expected_krw / (price * (1 + fee_ratio))
        
        # Mock 잔고 설정
        self.mock_db.accounts[self.user_id]['krw_balance'] = 2000000  # 200만 원
        
        # 매수 주문 실행
        result = self.trader.buy_market(price, self.ticker)
        
        # 결과 검증
        self.assertIsInstance(result, dict)
        self.assertIn('side', result)
        self.assertEqual(result['side'], 'BUY')
        self.assertIn('qty', result)
        self.assertIn('price', result)
        
        # 수량 계산 검증
        actual_qty = result['qty']
        self.assertAlmostEqual(actual_qty, expected_qty, places=6)
        self.assertGreater(actual_qty, 0)
        
        # 잔고 업데이트 확인
        updated_balance = self.mock_db.get_account(self.user_id)['krw_balance']
        expected_spent = actual_qty * price * (1 + fee_ratio)
        self.assertAlmostEqual(updated_balance, 2000000 - expected_spent, places=2)
        
    def test_sell_market_order_calculation(self):
        """매도 주문 계산 테스트"""
        # 테스트 설정
        price = 50000
        initial_qty = 0.1  # 0.1 BTC
        
        # 초기 코인 잔고 설정
        self.mock_db.update_coin_position(self.user_id, self.ticker, initial_qty, price)
        
        # 매도 주문 실행
        result = self.trader.sell_market(price, self.ticker)
        
        # 결과 검증
        self.assertIsInstance(result, dict)
        self.assertIn('side', result)
        self.assertEqual(result['side'], 'SELL')
        self.assertIn('qty', result)
        self.assertIn('price', result)
        
        # 수량 검증
        actual_qty = result['qty']
        self.assertEqual(actual_qty, initial_qty)
        
        # 잔고 업데이트 확인
        updated_coin_balance = self.mock_db.get_coin_balance(self.user_id, self.ticker)
        self.assertEqual(updated_coin_balance, 0.0)
        
        # KRW 잔고 증가 확인
        fee_ratio = 0.0005
        expected_received = actual_qty * price * (1 - fee_ratio)
        updated_krw_balance = self.mock_db.get_account(self.user_id)['krw_balance']
        self.assertGreater(updated_krw_balance, 0)
        
    def test_insufficient_balance_handling(self):
        """잔고 부족 처리 테스트"""
        # KRW 잔고 부족
        self.mock_db.accounts[self.user_id]['krw_balance'] = 1000  # 1,000원
        
        # 매수 주문 시도
        result = self.trader.buy_market(50000, self.ticker)
        
        # 결과 검증
        self.assertIsInstance(result, dict)
        self.assertEqual(result, {})
        
        # 코인 잔고 부족
        result = self.trader.sell_market(50000, self.ticker)
        
        # 결과 검증
        self.assertIsInstance(result, dict)
        self.assertEqual(result, {})
        
    def test_zero_quantity_handling(self):
        """0 수량 처리 테스트"""
        # 매우 높은 가격 설정 (수량이 0이 되는 경우)
        result = self.trader.buy_market(100000000, self.ticker)
        
        # 결과 검증
        self.assertIsInstance(result, dict)
        self.assertEqual(result, {})
        
    def test_order_flow_simulation(self):
        """주문 흐름 시뮬레이션 테스트"""
        # 초기 상태
        initial_krw = self.mock_db.get_account(self.user_id)['krw_balance']
        initial_coin = self.mock_db.get_coin_balance(self.user_id, self.ticker)
        
        # 매수 주문
        buy_price = 50000
        buy_result = self.trader.buy_market(buy_price, self.ticker)
        
        # 매수 결과 검증
        self.assertEqual(buy_result['side'], 'BUY')
        self.assertGreater(buy_result['qty'], 0)
        
        # 매수 후 잔고 확인
        after_buy_krw = self.mock_db.get_account(self.user_id)['krw_balance']
        after_buy_coin = self.mock_db.get_coin_balance(self.user_id, self.ticker)
        
        self.assertLess(after_buy_krw, initial_krw)
        self.assertGreater(after_buy_coin, initial_coin)
        
        # 매도 주문
        sell_price = 51000  # 1,000원 상승
        sell_result = self.trader.sell_market(sell_price, self.ticker)
        
        # 매도 결과 검증
        self.assertEqual(sell_result['side'], 'SELL')
        self.assertEqual(sell_result['qty'], buy_result['qty'])
        
        # 매도 후 잔고 확인
        after_sell_krw = self.mock_db.get_account(self.user_id)['krw_balance']
        after_sell_coin = self.mock_db.get_coin_balance(self.user_id, self.ticker)
        
        self.assertGreater(after_sell_krw, after_buy_krw)
        self.assertEqual(after_sell_coin, 0.0)
        
        # 수익 계산
        profit = after_sell_krw - initial_krw
        self.assertGreater(profit, 0)
        
    def test_multiple_trades_simulation(self):
        """다중 거래 시뮬레이션 테스트"""
        # 초기 잔고
        initial_balance = self.mock_db.get_account(self.user_id)['krw_balance']
        
        # 여러 번의 거래 시뮬레이션
        trades = [
            {'side': 'buy', 'price': 50000},
            {'side': 'sell', 'price': 51000},
            {'side': 'buy', 'price': 50500},
            {'side': 'sell', 'price': 51500},
            {'side': 'buy', 'price': 52000},
            {'side': 'sell', 'price': 53000}
        ]
        
        for i, trade in enumerate(trades):
            if trade['side'] == 'buy':
                result = self.trader.buy_market(trade['price'], self.ticker)
                self.assertEqual(result['side'], 'BUY')
            else:
                result = self.trader.sell_market(trade['price'], self.ticker)
                self.assertEqual(result['side'], 'SELL')
        
        # 최종 잔고 확인
        final_balance = self.mock_db.get_account(self.user_id)['krw_balance']
        final_coin_balance = self.mock_db.get_coin_balance(self.user_id, self.ticker)
        
        # 최종적으로 코인 잔고는 0이어야 함
        self.assertEqual(final_coin_balance, 0.0)
        
        # 총 수익/손실 계산
        total_pnl = final_balance - initial_balance
        self.assertIsInstance(total_pnl, float)
        
    def test_order_history_tracking(self):
        """주문 내역 추적 테스트"""
        # 주문 실행
        buy_result = self.trader.buy_market(50000, self.ticker)
        sell_result = self.trader.sell_market(51000, self.ticker)
        
        # 주문 내역 조회
        orders = self.mock_db.get_orders(self.user_id, limit=10)
        
        # 결과 검증
        self.assertGreaterEqual(len(orders), 2)
        
        # 주문 상세 정보 검증
        buy_order = next((o for o in orders if o['side'] == 'BUY'), None)
        sell_order = next((o for o in orders if o['side'] == 'SELL'), None)
        
        self.assertIsNotNone(buy_order)
        self.assertIsNotNone(sell_order)
        
        # 주문 정보 검증
        self.assertEqual(buy_order['ticker'], self.ticker)
        self.assertEqual(sell_order['ticker'], self.ticker)
        self.assertEqual(buy_order['status'], 'completed')
        self.assertEqual(sell_order['status'], 'completed')
        
    def test_position_tracking(self):
        """포지션 추적 테스트"""
        # 초기 포지션 확인
        initial_position = self.mock_db.get_coin_balance(self.user_id, self.ticker)
        self.assertEqual(initial_position, 0.0)
        
        # 매수 후 포지션 확인
        buy_result = self.trader.buy_market(50000, self.ticker)
        after_buy_position = self.mock_db.get_coin_balance(self.user_id, self.ticker)
        
        self.assertGreater(after_buy_position, 0.0)
        self.assertEqual(after_buy_position, buy_result['qty'])
        
        # 매도 후 포지션 확인
        sell_result = self.trader.sell_market(51000, self.ticker)
        after_sell_position = self.mock_db.get_coin_balance(self.user_id, self.ticker)
        
        self.assertEqual(after_sell_position, 0.0)
        
    def test_risk_percentage_application(self):
        """리스크 퍼센트 적용 테스트"""
        # 다른 리스크 퍼센트로 트레이더 생성
        high_risk_trader = UpbitTrader(
            user_id=self.user_id,
            risk_pct=0.5,  # 50% 리스크
            test_mode=True
        )
        
        # Mock 주입
        high_risk_trader.upbit = self.mock_upbit
        
        # 초기 잔고 설정
        initial_balance = 1000000
        self.mock_db.accounts[self.user_id]['krw_balance'] = initial_balance
        
        # 고위험 트레이더 매수
        high_risk_result = high_risk_trader.buy_market(50000, self.ticker)
        
        # 저위험 트레이더 매수
        low_risk_result = self.trader.buy_market(50000, self.ticker)
        
        # 결과 비교
        high_risk_qty = high_risk_result['qty']
        low_risk_qty = low_risk_result['qty']
        
        # 고위험 트레이더가 더 많은 수량을 매수해야 함
        self.assertGreater(high_risk_qty, low_risk_qty)
        
        # 리스크 비율 검증
        expected_high_risk_amount = initial_balance * 0.5
        expected_low_risk_amount = initial_balance * 0.1
        
        actual_high_risk_amount = high_risk_qty * 50000 * 1.0005
        actual_low_risk_amount = low_risk_qty * 50000 * 1.0005
        
        self.assertAlmostEqual(actual_high_risk_amount, expected_high_risk_amount, places=2)
        self.assertAlmostEqual(actual_low_risk_amount, expected_low_risk_amount, places=2)
        
    def test_fee_calculation(self):
        """수수료 계산 테스트"""
        # 초기 잔고 설정
        initial_balance = 1000000
        self.mock_db.accounts[self.user_id]['krw_balance'] = initial_balance
        
        # 매수 주문
        buy_price = 50000
        buy_result = self.trader.buy_market(buy_price, self.ticker)
        
        # 수수료 계산
        fee_ratio = 0.0005
        expected_fee = buy_result['qty'] * buy_price * fee_ratio
        
        # 실제 수수료 확인
        actual_spent = initial_balance - self.mock_db.get_account(self.user_id)['krw_balance']
        expected_spent = buy_result['qty'] * buy_price * (1 + fee_ratio)
        
        self.assertAlmostEqual(actual_spent, expected_spent, places=2)
        
        # 매도 주문
        sell_price = 51000
        sell_result = self.trader.sell_market(sell_price, self.ticker)
        
        # 매도 수수료 계산
        sell_expected_fee = sell_result['qty'] * sell_price * fee_ratio
        sell_expected_received = sell_result['qty'] * sell_price * (1 - fee_ratio)
        
        # 실제 수익 확인
        final_balance = self.mock_db.get_account(self.user_id)['krw_balance']
        actual_received = final_balance - (initial_balance - actual_spent)
        
        self.assertAlmostEqual(actual_received, sell_expected_received, places=2)
        
    def test_error_handling(self):
        """에러 처리 테스트"""
        # 잘못된 티커
        with self.assertRaises(Exception):
            self.trader.buy_market(50000, 'INVALID-TICKER')
            
        # 음수 가격
        result = self.trader.buy_market(-50000, self.ticker)
        self.assertEqual(result, {})
        
        # 0 가격
        result = self.trader.buy_market(0, self.ticker)
        self.assertEqual(result, {})
        
    def test_concurrent_trading(self):
        """동시 거래 테스트"""
        # 여러 트레이더 인스턴스 생성
        traders = [
            UpbitTrader(user_id=f'user_{i}', test_mode=True)
            for i in range(3)
        ]
        
        # 각 트레이더에게 Mock 주입
        for trader in traders:
            trader.upbit = self.mock_upbit
        
        # 동시에 주문 실행
        results = []
        for trader in traders:
            # 사용자별 계정 생성
            self.mock_db.create_or_init_account(trader.user_id, 1000000)
            
            # 주문 실행
            result = trader.buy_market(50000, self.ticker)
            results.append(result)
        
        # 모든 주문이 성공했는지 확인
        for result in results:
            self.assertIsInstance(result, dict)
            self.assertIn('side', result)
            self.assertEqual(result['side'], 'BUY')
            self.assertGreater(result['qty'], 0)
        
        # 각 사용자의 잔고가 업데이트되었는지 확인
        for trader in traders:
            balance = self.mock_db.get_account(trader.user_id)['krw_balance']
            self.assertLess(balance, 1000000)
            
    def test_database_integration(self):
        """데이터베이스 통합 테스트"""
        # Mock DB 함수 호출 확인
        with patch.object(self.mock_db, 'insert_order') as mock_insert:
            with patch.object(self.mock_db, 'update_account') as mock_update:
                with patch.object(self.mock_db, 'update_coin_position') as mock_position:
                    # 주문 실행
                    result = self.trader.buy_market(50000, self.ticker)
                    
                    # DB 함수 호출 확인
                    mock_insert.assert_called_once()
                    mock_update.assert_called()
                    mock_position.assert_called_once()
                    
                    # 함수 호출 인자 검증
                    insert_call_args = mock_insert.call_args
                    self.assertEqual(insert_call_args[1]['side'], 'BUY')
                    self.assertEqual(insert_call_args[1]['ticker'], self.ticker)
                    
    def test_performance_metrics(self):
        """성능 메트릭 테스트"""
        import time
        
        # 성능 테스트를 위한 다중 거래
        start_time = time.time()
        
        num_trades = 10
        for i in range(num_trades):
            if i % 2 == 0:
                self.trader.buy_market(50000 + i * 100, self.ticker)
            else:
                self.trader.sell_market(51000 + i * 100, self.ticker)
        
        end_time = time.time()
        execution_time = end_time - start_time
        
        # 성능 메트릭
        avg_time_per_trade = execution_time / num_trades
        
        # 결과 검증
        self.assertLess(execution_time, 5.0)  # 5초 이내 완료
        self.assertLess(avg_time_per_trade, 0.5)  # 거래당 0.5초 이내
        
        # 주문 내역 확인
        orders = self.mock_db.get_orders(self.user_id, limit=20)
        self.assertGreaterEqual(len(orders), num_trades)
        

if __name__ == '__main__':
    # 테스트 실행
    unittest.main(verbosity=2)