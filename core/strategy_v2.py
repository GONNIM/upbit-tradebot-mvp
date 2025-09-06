# FINAL CODE
# core/strategy_v2.py

import pandas as pd
import numpy as np
import logging
import threading
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple, Union
from dataclasses import dataclass, field
from enum import Enum
import json

from services.logger import get_logger
from services.db import get_db_manager, insert_log
from engine.params import get_params_manager, LiveParams, StrategyType, MACDParams
from config import DEFAULT_USER_ID
from utils.logging_util import log_to_file

# 로거 설정
logger = get_logger(__name__)

# 신호 타입 열거형
class SignalType(Enum):
    LOG = "LOG"
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    WARNING = "WARNING"

# 크로스 타입 열거형
class CrossType(Enum):
    GOLDEN = "Golden"
    DEAD = "Dead"
    PENDING = "Pending"
    NEUTRAL = "Neutral"

# 시그널 데이터 클래스
@dataclass
class SignalData:
    timestamp: float
    signal_type: SignalType
    ticker: str
    price: float
    reason: str
    confidence: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'timestamp': datetime.fromtimestamp(self.timestamp).isoformat(),
            'signal_type': self.signal_type.value,
            'ticker': self.ticker,
            'price': self.price,
            'reason': self.reason,
            'confidence': self.confidence,
            'metadata': self.metadata
        }

# 전략 설정 데이터 클래스
@dataclass
class StrategyConfig:
    user_id: str
    ticker: str
    entry_delay_bars: int = 3
    min_holding_period: int = 5
    volatility_window: int = 20
    atr_period: int = 14
    ma_period: int = 20
    enable_ma_filter: bool = True
    enable_volatility_adjustment: bool = True
    enable_signal_confirmation: bool = True
    risk_per_trade: float = 0.02
    max_position_size: float = 1.0
    signal_threshold: float = 0.6
    
    # 동적 파라미터
    tp_multiplier: float = 2.0
    sl_multiplier: float = 1.0
    volatility_multiplier: float = 1.5

# 전략 결과 데이터 클래스
@dataclass
class StrategyResult:
    signals: List[SignalData] = field(default_factory=list)
    performance_metrics: Dict[str, float] = field(default_factory=dict)
    current_position: Optional[str] = None
    entry_price: Optional[float] = None
    entry_time: Optional[float] = None
    highest_price: Optional[float] = None
    trailing_stop: Optional[float] = None
    bars_held: int = 0
    
    def add_signal(self, signal: SignalData):
        self.signals.append(signal)
        
    def get_latest_signal(self) -> Optional[SignalData]:
        return self.signals[-1] if self.signals else None

# 향상된 전략 클래스
class EnhancedMACDStrategy:
    """향상된 MACD 전략 시스템"""
    
    def __init__(self, config: StrategyConfig, params: LiveParams):
        self.config = config
        self.params = params
        self.user_id = config.user_id
        self.ticker = config.ticker
        
        # 상태 관리
        self._lock = threading.RLock()
        self._result = StrategyResult()
        self._last_cross_type = CrossType.NEUTRAL
        self._golden_cross_pending = False
        self._entry_delay_count = 0
        self._signal_history = []
        
        # 파라미터 매니저
        self._params_manager = get_params_manager()
        
        logger.info(f"향상된 MACD 전략 초기화: {self.user_id}, {self.ticker}")
    
    def analyze(self, data: pd.DataFrame) -> Optional[SignalData]:
        """데이터 분석 및 신호 생성"""
        try:
            with self._lock:
                # 데이터 유효성 검사
                if len(data) < max(self.config.ma_period, self.params.strategy.macd.slow_period):
                    return None
                
                # 지표 계산
                indicators = self._calculate_indicators(data)
                if not indicators:
                    return None
                
                # 현재 상태 확인
                current_state = self._get_current_state(data, indicators)
                
                # 크로스 상태 업데이트
                self._update_cross_state(current_state)
                
                # 신호 분석
                signal = self._analyze_signals(current_state, indicators)
                
                # 결과 업데이트
                if signal:
                    self._result.add_signal(signal)
                    self._update_position_state(signal, current_state)
                
                # 성능 메트릭 업데이트
                self._update_performance_metrics(current_state)
                
                return signal
                
        except Exception as e:
            logger.error(f"전략 분석 실패: {e}")
            return None
    
    def _calculate_indicators(self, data: pd.DataFrame) -> Optional[Dict[str, Any]]:
        """모든 지표 계산"""
        try:
            close = data['close'].values
            high = data['high'].values
            low = data['low'].values
            
            # MACD 지표
            macd_params = self.params.strategy.macd
            if not macd_params:
                return None
                
            macd_line = self._calculate_macd(close, macd_params.fast_period, macd_params.slow_period)
            signal_line = self._calculate_signal(macd_line, macd_params.signal_period)
            histogram = macd_line - signal_line
            
            # 이동평균
            ma_line = self._calculate_sma(close, self.config.ma_period)
            
            # 변동성 지표
            atr = self._calculate_atr(high, low, close, self.config.atr_period)
            volatility = self._calculate_volatility(close, self.config.volatility_window)
            
            # 추세 지표
            rsi = self._calculate_rsi(close, 14)
            
            return {
                'macd_line': macd_line,
                'signal_line': signal_line,
                'histogram': histogram,
                'ma_line': ma_line,
                'atr': atr,
                'volatility': volatility,
                'rsi': rsi,
                'close': close,
                'high': high,
                'low': low
            }
            
        except Exception as e:
            logger.error(f"지표 계산 실패: {e}")
            return None
    
    def _calculate_macd(self, series: np.ndarray, fast: int, slow: int) -> np.ndarray:
        """MACD 계산"""
        fast_ema = pd.Series(series).ewm(span=fast).mean().values
        slow_ema = pd.Series(series).ewm(span=slow).mean().values
        return fast_ema - slow_ema
    
    def _calculate_signal(self, macd: np.ndarray, period: int) -> np.ndarray:
        """MACD 신호선 계산"""
        return pd.Series(macd).ewm(span=period).mean().values
    
    def _calculate_sma(self, series: np.ndarray, period: int) -> np.ndarray:
        """단순 이동평균 계산"""
        return pd.Series(series).rolling(window=period).mean().values
    
    def _calculate_atr(self, high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int) -> np.ndarray:
        """ATR 계산"""
        high_low = high - low
        high_close = np.abs(high - np.roll(close, 1))
        low_close = np.abs(low - np.roll(close, 1))
        
        tr = np.maximum(high_low, np.maximum(high_close, low_close))
        return pd.Series(tr).rolling(window=period).mean().values
    
    def _calculate_volatility(self, series: np.ndarray, period: int) -> np.ndarray:
        """변동성 계산 (표준편차)"""
        returns = np.log(series / np.roll(series, 1))[1:]
        volatility = pd.Series(returns).rolling(window=period).std().values
        return np.concatenate([[np.nan], volatility])
    
    def _calculate_rsi(self, series: np.ndarray, period: int) -> np.ndarray:
        """RSI 계산"""
        delta = np.diff(series)
        gain = np.where(delta > 0, delta, 0)
        loss = np.where(delta < 0, -delta, 0)
        
        avg_gain = pd.Series(gain).rolling(window=period).mean().values
        avg_loss = pd.Series(loss).rolling(window=period).mean().values
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return np.concatenate([[np.nan], rsi])
    
    def _get_current_state(self, data: pd.DataFrame, indicators: Dict[str, Any]) -> Dict[str, Any]:
        """현재 상태 정보"""
        idx = -1
        current_price = indicators['close'][idx]
        current_time = data.index[idx] if hasattr(data, 'index') else datetime.now()
        
        return {
            'index': idx,
            'timestamp': current_time.timestamp() if hasattr(current_time, 'timestamp') else time.time(),
            'price': current_price,
            'macd': indicators['macd_line'][idx],
            'signal': indicators['signal_line'][idx],
            'histogram': indicators['histogram'][idx],
            'ma': indicators['ma_line'][idx],
            'atr': indicators['atr'][idx],
            'volatility': indicators['volatility'][idx],
            'rsi': indicators['rsi'][idx],
            'is_bullish_candle': indicators['close'][idx] > indicators['open'][idx] if 'open' in indicators else True,
            'bars_since_entry': self._result.bars_held,
            'current_position': self._result.current_position
        }
    
    def _update_cross_state(self, state: Dict[str, Any]):
        """크로스 상태 업데이트"""
        if len(self._signal_history) < 2:
            return
        
        prev_state = self._signal_history[-2]
        curr_state = state
        
        # 골든크로스 확인
        if (prev_state['macd'] <= prev_state['signal'] and 
            curr_state['macd'] > curr_state['signal']):
            self._last_cross_type = CrossType.GOLDEN
            self._golden_cross_pending = True
            self._entry_delay_count = 0
            
        # 데드크로스 확인
        elif (prev_state['macd'] >= prev_state['signal'] and 
              curr_state['macd'] < curr_state['signal']):
            self._last_cross_type = CrossType.DEAD
            self._golden_cross_pending = False
            
        # 중립 상태
        elif not self._golden_cross_pending:
            self._last_cross_type = CrossType.NEUTRAL
    
    def _analyze_signals(self, state: Dict[str, Any], indicators: Dict[str, Any]) -> Optional[SignalData]:
        """신호 분석"""
        # 로그 신호 (항상 생성)
        log_signal = self._create_log_signal(state)
        if log_signal:
            return log_signal
        
        # 매도 신호 확인
        if self._result.current_position == 'LONG':
            sell_signal = self._analyze_sell_signals(state, indicators)
            if sell_signal:
                return sell_signal
        
        # 매수 신호 확인
        if self._result.current_position != 'LONG':
            buy_signal = self._analyze_buy_signals(state, indicators)
            if buy_signal:
                return buy_signal
        
        # 보유 신호
        if self._result.current_position == 'LONG':
            hold_signal = self._create_hold_signal(state)
            if hold_signal:
                return hold_signal
        
        return None
    
    def _analyze_buy_signals(self, state: Dict[str, Any], indicators: Dict[str, Any]) -> Optional[SignalData]:
        """매수 신호 분석"""
        # 골든크로스 후 진입 지연
        if self._last_cross_type != CrossType.GOLDEN:
            return None
        
        if self._entry_delay_count < self.config.entry_delay_bars:
            self._entry_delay_count += 1
            return self._create_delay_signal(state)
        
        # 기본 조건 확인
        if not self._check_basic_buy_conditions(state):
            return None
        
        # 추가 필터 확인
        if not self._check_buy_filters(state, indicators):
            return None
        
        # 신호 강도 계산
        signal_strength = self._calculate_buy_signal_strength(state, indicators)
        
        if signal_strength >= self.config.signal_threshold:
            return self._create_buy_signal(state, signal_strength)
        
        return None
    
    def _check_basic_buy_conditions(self, state: Dict[str, Any]) -> bool:
        """기본 매수 조건 확인"""
        # MACD > 0
        if state['macd'] <= 0:
            return False
        
        # Signal > 0
        if state['signal'] <= 0:
            return False
        
        # 상승 캔들
        if not state['is_bullish_candle']:
            return False
        
        return True
    
    def _check_buy_filters(self, state: Dict[str, Any], indicators: Dict[str, Any]) -> bool:
        """추가 매수 필터 확인"""
        # MA 필터
        if self.config.enable_ma_filter and state['price'] <= state['ma']:
            return False
        
        # RSI 필터
        if state['rsi'] > 70:  # 과매수 상태
            return False
        
        # 변동성 필터
        if self.config.enable_volatility_adjustment:
            avg_volatility = np.nanmean(indicators['volatility'])
            if state['volatility'] > avg_volatility * self.config.volatility_multiplier:
                return False
        
        return True
    
    def _calculate_buy_signal_strength(self, state: Dict[str, Any], indicators: Dict[str, Any]) -> float:
        """매수 신호 강도 계산"""
        strength = 0.0
        
        # MACD 강도 (0-0.3)
        macd_strength = min(0.3, abs(state['macd']) / 0.1)
        strength += macd_strength
        
        # 히스토그램 강도 (0-0.2)
        hist_strength = min(0.2, abs(state['histogram']) / 0.05)
        strength += hist_strength
        
        # MA 거리 강도 (0-0.2)
        if self.config.enable_ma_filter:
            ma_distance = (state['price'] - state['ma']) / state['ma']
            ma_strength = min(0.2, abs(ma_distance) / 0.02)
            strength += ma_strength
        
        # RSI 강도 (0-0.15)
        rsi_strength = 0.15 if 30 <= state['rsi'] <= 60 else 0
        strength += rsi_strength
        
        # 변동성 강도 (0-0.15)
        if self.config.enable_volatility_adjustment:
            vol_strength = 0.15 if state['volatility'] < np.nanmean(indicators['volatility']) else 0
            strength += vol_strength
        
        return min(1.0, strength)
    
    def _analyze_sell_signals(self, state: Dict[str, Any], indicators: Dict[str, Any]) -> Optional[SignalData]:
        """매도 신호 분석"""
        if self._result.current_position != 'LONG' or self._result.entry_price is None:
            return None
        
        # 최소 보유 기간 확인
        if self._result.bars_held < self.config.min_holding_period:
            return None
        
        # 동적 TP/SL 계산
        tp_price, sl_price = self._calculate_dynamic_tp_sl(state, indicators)
        
        # Take Profit 확인
        if state['price'] >= tp_price:
            return self._create_sell_signal(state, "Take Profit", tp_price)
        
        # Stop Loss 확인
        if state['price'] <= sl_price:
            return self._create_sell_signal(state, "Stop Loss", sl_price)
        
        # MACD 데드크로스 확인
        if self._last_cross_type == CrossType.DEAD:
            return self._create_sell_signal(state, "MACD Dead Cross", state['price'])
        
        # 트레일링 스톱 확인
        if self._check_trailing_stop(state):
            return self._create_sell_signal(state, "Trailing Stop", self._result.trailing_stop)
        
        return None
    
    def _calculate_dynamic_tp_sl(self, state: Dict[str, Any], indicators: Dict[str, Any]) -> Tuple[float, float]:
        """동적 TP/SL 계산"""
        entry_price = self._result.entry_price
        current_atr = state['atr']
        current_volatility = state['volatility']
        
        # ATR 기반 TP/SL
        atr_tp = entry_price + (current_atr * self.config.tp_multiplier)
        atr_sl = entry_price - (current_atr * self.config.sl_multiplier)
        
        # 변동성 기반 TP/SL
        vol_tp = entry_price * (1 + current_volatility * self.config.tp_multiplier)
        vol_sl = entry_price * (1 - current_volatility * self.config.sl_multiplier)
        
        # 최종 TP/SL (보수적인 선택)
        tp_price = max(atr_tp, vol_tp)
        sl_price = min(atr_sl, vol_sl)
        
        # 최소 TP/SL 보장
        min_tp = entry_price * 1.02  # 최소 2% 수익
        max_sl = entry_price * 0.98  # 최대 2% 손실
        
        tp_price = max(tp_price, min_tp)
        sl_price = min(sl_price, max_sl)
        
        return tp_price, sl_price
    
    def _check_trailing_stop(self, state: Dict[str, Any]) -> bool:
        """트레일링 스톱 확인"""
        if self._result.highest_price is None or state['price'] > self._result.highest_price:
            self._result.highest_price = state['price']
            
            # 트레일링 스톱 업데이트
            trail_distance = (self._result.highest_price - self._result.entry_price) * 0.5
            self._result.trailing_stop = self._result.highest_price - trail_distance
        
        return state['price'] <= self._result.trailing_stop
    
    def _create_log_signal(self, state: Dict[str, Any]) -> SignalData:
        """로그 신호 생성"""
        metadata = {
            'cross_type': self._last_cross_type.value,
            'macd': state['macd'],
            'signal': state['signal'],
            'histogram': state['histogram'],
            'ma': state['ma'],
            'atr': state['atr'],
            'volatility': state['volatility'],
            'rsi': state['rsi'],
            'entry_delay': self._entry_delay_count,
            'bars_held': self._result.bars_held
        }
        
        return SignalData(
            timestamp=state['timestamp'],
            signal_type=SignalType.LOG,
            ticker=self.ticker,
            price=state['price'],
            reason=f"상태 업데이트: {self._last_cross_type.value} 크로스",
            confidence=0.5,
            metadata=metadata
        )
    
    def _create_buy_signal(self, state: Dict[str, Any], strength: float) -> SignalData:
        """매수 신호 생성"""
        metadata = {
            'signal_strength': strength,
            'entry_delay': self._entry_delay_count,
            'macd': state['macd'],
            'signal': state['signal'],
            'volatility': state['volatility'],
            'atr': state['atr']
        }
        
        return SignalData(
            timestamp=state['timestamp'],
            signal_type=SignalType.BUY,
            ticker=self.ticker,
            price=state['price'],
            reason=f"골든크로스 매수 신호 (강도: {strength:.2f})",
            confidence=strength,
            metadata=metadata
        )
    
    def _create_sell_signal(self, state: Dict[str, Any], reason: str, price: float) -> SignalData:
        """매도 신호 생성"""
        metadata = {
            'sell_reason': reason,
            'entry_price': self._result.entry_price,
            'bars_held': self._result.bars_held,
            'pnl_pct': ((price - self._result.entry_price) / self._result.entry_price) * 100
        }
        
        return SignalData(
            timestamp=state['timestamp'],
            signal_type=SignalType.SELL,
            ticker=self.ticker,
            price=price,
            reason=f"매도 신호: {reason}",
            confidence=0.8,
            metadata=metadata
        )
    
    def _create_hold_signal(self, state: Dict[str, Any]) -> SignalData:
        """보유 신호 생성"""
        if self._result.entry_price is None:
            return None
        
        current_pnl = ((state['price'] - self._result.entry_price) / self._result.entry_price) * 100
        tp_price, sl_price = self._calculate_dynamic_tp_sl(state, {'atr': state['atr']})
        
        metadata = {
            'current_pnl': current_pnl,
            'bars_held': self._result.bars_held,
            'tp_price': tp_price,
            'sl_price': sl_price,
            'highest_price': self._result.highest_price
        }
        
        return SignalData(
            timestamp=state['timestamp'],
            signal_type=SignalType.HOLD,
            ticker=self.ticker,
            price=state['price'],
            reason=f"포지션 보유 (수익률: {current_pnl:.2f}%)",
            confidence=0.6,
            metadata=metadata
        )
    
    def _create_delay_signal(self, state: Dict[str, Any]) -> SignalData:
        """지연 신호 생성"""
        remaining_delay = self.config.entry_delay_bars - self._entry_delay_count
        
        metadata = {
            'remaining_delay': remaining_delay,
            'total_delay': self.config.entry_delay_bars,
            'cross_type': self._last_cross_type.value
        }
        
        return SignalData(
            timestamp=state['timestamp'],
            signal_type=SignalType.WARNING,
            ticker=self.ticker,
            price=state['price'],
            reason=f"진입 지연: {remaining_delay}바 남음",
            confidence=0.3,
            metadata=metadata
        )
    
    def _update_position_state(self, signal: SignalData, state: Dict[str, Any]):
        """포지션 상태 업데이트"""
        if signal.signal_type == SignalType.BUY:
            self._result.current_position = 'LONG'
            self._result.entry_price = state['price']
            self._result.entry_time = state['timestamp']
            self._result.bars_held = 0
            self._result.highest_price = state['price']
            self._result.trailing_stop = None
            
        elif signal.signal_type == SignalType.SELL:
            self._result.current_position = None
            self._result.entry_price = None
            self._result.entry_time = None
            self._result.bars_held = 0
            self._result.highest_price = None
            self._result.trailing_stop = None
            
        elif signal.signal_type == SignalType.HOLD:
            self._result.bars_held += 1
    
    def _update_performance_metrics(self, state: Dict[str, Any]):
        """성능 메트릭 업데이트"""
        # TODO: 성능 메트릭 계산 로직 구현
        pass
    
    def get_result(self) -> StrategyResult:
        """전략 결과 반환"""
        return self._result
    
    def reset(self):
        """전략 상태 초기화"""
        with self._lock:
            self._result = StrategyResult()
            self._last_cross_type = CrossType.NEUTRAL
            self._golden_cross_pending = False
            self._entry_delay_count = 0
            self._signal_history.clear()
    
    def update_params(self, params: LiveParams):
        """파라미터 업데이트"""
        with self._lock:
            self.params = params
            logger.info(f"전략 파라미터 업데이트: {self.user_id}")

# 전략 팩토리
class StrategyFactory:
    """전략 팩토리 클래스"""
    
    @staticmethod
    def create_strategy(strategy_type: StrategyType, config: StrategyConfig, params: LiveParams) -> EnhancedMACDStrategy:
        """전략 생성"""
        if strategy_type == StrategyType.MACD:
            return EnhancedMACDStrategy(config, params)
        else:
            raise ValueError(f"지원하지 않는 전략 타입: {strategy_type}")
    
    @staticmethod
    def create_config_from_params(params: LiveParams) -> StrategyConfig:
        """파라미터에서 설정 생성"""
        return StrategyConfig(
            user_id=params.user_id,
            ticker=params.ticker,
            entry_delay_bars=params.strategy.macd.fast_period if params.strategy.macd else 3,
            min_holding_period=params.risk_management.max_trades_per_day // 10,
            volatility_window=20,
            enable_ma_filter=True,
            enable_volatility_adjustment=True,
            risk_per_trade=params.risk_management.risk_per_trade,
            max_position_size=params.risk_management.max_position_size
        )

# 유틸리티 함수
def create_strategy_from_user_params(user_id: str) -> Optional[EnhancedMACDStrategy]:
    """사용자 파라미터로 전략 생성"""
    try:
        params_manager = get_params_manager()
        params = params_manager.get_params(user_id)
        
        if not params:
            logger.warning(f"사용자 파라미터 없음: {user_id}")
            return None
        
        config = StrategyFactory.create_config_from_params(params)
        strategy = StrategyFactory.create_strategy(StrategyType.MACD, config, params)
        
        return strategy
        
    except Exception as e:
        logger.error(f"전략 생성 실패: {e}")
        return None

def analyze_market_data(user_id: str, data: pd.DataFrame) -> Optional[SignalData]:
    """시장 데이터 분석"""
    try:
        strategy = create_strategy_from_user_params(user_id)
        if not strategy:
            return None
        
        return strategy.analyze(data)
        
    except Exception as e:
        logger.error(f"시장 데이터 분석 실패: {e}")
        return None

# 사용 예제
if __name__ == "__main__":
    # 샘플 데이터 생성
    np.random.seed(42)
    dates = pd.date_range(start='2024-01-01', periods=100, freq='H')
    prices = 100 + np.cumsum(np.random.randn(100) * 0.1)
    
    sample_data = pd.DataFrame({
        'open': prices + np.random.randn(100) * 0.05,
        'high': prices + np.random.rand(100) * 0.1,
        'low': prices - np.random.rand(100) * 0.1,
        'close': prices,
        'volume': np.random.randint(1000, 10000, 100)
    }, index=dates)
    
    # 전략 생성 및 테스트
    config = StrategyConfig(user_id="test_user", ticker="BTC")
    params = create_params_from_template("test_user", StrategyType.MACD)
    
    strategy = StrategyFactory.create_strategy(StrategyType.MACD, config, params)
    
    # 분석 실행
    for i in range(50, len(sample_data)):
        data_slice = sample_data.iloc[:i+1]
        signal = strategy.analyze(data_slice)
        
        if signal and signal.signal_type in [SignalType.BUY, SignalType.SELL]:
            print(f"{signal.signal_type.value}: {signal.reason} at {signal.price}")
    
    # 결과 출력
    result = strategy.get_result()
    print(f"총 신호 수: {len(result.signals)}")
    print(f"현재 포지션: {result.current_position}")
    print(f"진입가: {result.entry_price}")