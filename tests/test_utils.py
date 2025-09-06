# FINAL CODE
# tests/test_utils.py

import pandas as pd
import numpy as np
from typing import Dict, Any, Tuple, Union


def calculate_atr(data: pd.DataFrame, period: int = 14) -> float:
    """
    ATR (Average True Range) 계산
    
    Args:
        data: OHLCV 데이터
        period: ATR 기간
        
    Returns:
        ATR 값
    """
    if len(data) < period:
        return 0.0
    
    high = data['high'].values
    low = data['low'].values
    close = data['close'].values
    
    # True Range 계산
    tr1 = high[1:] - low[1:]
    tr2 = abs(high[1:] - close[:-1])
    tr3 = abs(low[1:] - close[:-1])
    
    tr = np.maximum(np.maximum(tr1, tr2), tr3)
    
    # ATR 계산
    atr = np.mean(tr[-period:]) if len(tr) >= period else np.mean(tr)
    
    return float(atr)


def calculate_macd(
    data: pd.DataFrame, 
    fast: int = 12, 
    slow: int = 26, 
    signal: int = 9
) -> Dict[str, np.ndarray]:
    """
    MACD 계산
    
    Args:
        data: OHLCV 데이터
        fast: 빠른 이동평균 기간
        slow: 느린 이동평균 기간
        signal: 신호선 기간
        
    Returns:
        MACD 데이터 딕셔너리
    """
    close = data['close'].values
    
    # EMA 계산
    def ema(data, period):
        alpha = 2 / (period + 1)
        ema_values = np.zeros_like(data)
        ema_values[0] = data[0]
        
        for i in range(1, len(data)):
            ema_values[i] = alpha * data[i] + (1 - alpha) * ema_values[i-1]
        
        return ema_values
    
    # MACD 라인 계산
    ema_fast = ema(close, fast)
    ema_slow = ema(close, slow)
    macd_line = ema_fast - ema_slow
    
    # 신호선 계산
    signal_line = ema(macd_line, signal)
    
    # 히스토그램 계산
    histogram = macd_line - signal_line
    
    return {
        'macd': macd_line,
        'signal': signal_line,
        'histogram': histogram
    }


def detect_cross(macd_data: Dict[str, np.ndarray]) -> str:
    """
    MACD 크로스 감지
    
    Args:
        macd_data: MACD 데이터
        
    Returns:
        크로스 타입
    """
    macd = macd_data['macd']
    signal = macd_data['signal']
    
    if len(macd) < 2:
        return 'NEUTRAL'
    
    # 직전 상태 확인
    prev_macd_above = macd[-2] > signal[-2]
    curr_macd_above = macd[-1] > signal[-1]
    
    # 골든크로스 (MACD가 신호선을 상향 돌파)
    if not prev_macd_above and curr_macd_above:
        return 'GOLDEN'
    
    # 데드크로스 (MACD가 신호선을 하향 돌파)
    if prev_macd_above and not curr_macd_above:
        return 'DEAD'
    
    return 'NEUTRAL'


def apply_ma_filter(data: pd.DataFrame, ma_period: int = 20) -> pd.DataFrame:
    """
    이동평균 필터 적용
    
    Args:
        data: OHLCV 데이터
        ma_period: 이동평균 기간
        
    Returns:
        이동평균이 추가된 데이터
    """
    result = data.copy()
    result[f'ma_{ma_period}'] = data['close'].rolling(window=ma_period).mean()
    return result


def apply_volatility_adjustment(
    base_confidence: float,
    data: pd.DataFrame,
    volatility_window: int = 20,
    volatility_multiplier: float = 1.5
) -> float:
    """
    변동성 조정 적용
    
    Args:
        base_confidence: 기본 신뢰도
        data: 가격 데이터
        volatility_window: 변동성 계산 기간
        volatility_multiplier: 변동성 승수
        
    Returns:
        조정된 신뢰도
    """
    if len(data) < volatility_window:
        return base_confidence
    
    # 변동성 계산
    returns = data['close'].pct_change().dropna()
    volatility = returns.tail(volatility_window).std()
    
    # 변동성이 높을수록 신뢰도 감소
    adjustment_factor = 1 / (1 + volatility * volatility_multiplier)
    
    adjusted_confidence = base_confidence * adjustment_factor
    
    # 신뢰도 범위 제한
    return max(0.0, min(1.0, adjusted_confidence))


def confirm_signal(
    signal_data: Dict[str, Any],
    threshold: float = 0.6,
    enable_ma_filter: bool = True,
    enable_volatility_filter: bool = True
) -> bool:
    """
    신호 확인
    
    Args:
        signal_data: 신호 데이터
        threshold: 신뢰도 임계값
        enable_ma_filter: MA 필터 활성화
        enable_volatility_filter: 변동성 필터 활성화
        
    Returns:
        신호 확인 결과
    """
    # 기본 신호 강도 확인
    macd_strength = abs(signal_data.get('macd', 0))
    base_confidence = min(macd_strength * 2, 1.0)  # 0-1 사이로 정규화
    
    if base_confidence < threshold:
        return False
    
    # MA 필터 확인
    if enable_ma_filter and not signal_data.get('above_ma', True):
        return False
    
    # 변동성 필터 확인
    if enable_volatility_filter and not signal_data.get('volatility_ok', True):
        return False
    
    return True