"""
지표 상태 관리 - 증분 계산 기반 EMA/MACD
Backtest 없이 새 봉 1개씩 증분 업데이트
"""
from typing import Optional, List, Dict, Any
import logging

logger = logging.getLogger(__name__)


class IndicatorState:
    """
    EMA/MACD 증분 계산 상태 관리
    - 이전 값을 저장하여 크로스 판정
    - 새 봉 1개 기준으로만 증분 갱신 (전체 재계산 없음)
    """

    def __init__(
        self,
        macd_fast: int = 12,
        macd_slow: int = 26,
        macd_signal: int = 9,
        ema_fast: int = 20,
        ema_slow: int = 60,
        base_ema: int = 60,  # EMA 전략용 기준선
        use_separate_ema: bool = True,  # 매수/매도 별도 EMA 사용 여부
        ema_fast_buy: Optional[int] = None,  # 매수용 fast EMA (None이면 ema_fast 사용)
        ema_slow_buy: Optional[int] = None,  # 매수용 slow EMA (None이면 ema_slow 사용)
        ema_fast_sell: Optional[int] = None,  # 매도용 fast EMA (None이면 ema_fast 사용)
        ema_slow_sell: Optional[int] = None,  # 매도용 slow EMA (None이면 ema_slow 사용)
    ):
        """
        Args:
            macd_fast: MACD fast EMA 기간
            macd_slow: MACD slow EMA 기간
            macd_signal: MACD signal 기간
            ema_fast: EMA 전략 fast 기간 (공통 또는 백워드 호환)
            ema_slow: EMA 전략 slow 기간 (공통 또는 백워드 호환)
            base_ema: EMA 전략 기준선 기간
            use_separate_ema: 매수/매도 별도 EMA 사용 여부
            ema_fast_buy: 매수용 fast EMA 기간
            ema_slow_buy: 매수용 slow EMA 기간
            ema_fast_sell: 매도용 fast EMA 기간
            ema_slow_sell: 매도용 slow EMA 기간
        """
        # 파라미터
        self.macd_fast_period = macd_fast
        self.macd_slow_period = macd_slow
        self.macd_signal_period = macd_signal
        self.ema_fast_period = ema_fast
        self.ema_slow_period = ema_slow
        self.base_ema_period = base_ema

        # 매수/매도 별도 EMA 설정
        self.use_separate_ema = use_separate_ema
        self.ema_fast_buy_period = ema_fast_buy if ema_fast_buy else ema_fast
        self.ema_slow_buy_period = ema_slow_buy if ema_slow_buy else ema_slow
        self.ema_fast_sell_period = ema_fast_sell if ema_fast_sell else ema_fast
        self.ema_slow_sell_period = ema_slow_sell if ema_slow_sell else ema_slow

        # 계산용 alpha (EMA 증분 공식: alpha = 2 / (period + 1))
        self.alpha_macd_fast = 2 / (macd_fast + 1)
        self.alpha_macd_slow = 2 / (macd_slow + 1)
        self.alpha_macd_signal = 2 / (macd_signal + 1)
        self.alpha_ema_fast = 2 / (ema_fast + 1)
        self.alpha_ema_slow = 2 / (ema_slow + 1)
        self.alpha_base_ema = 2 / (base_ema + 1)

        # 매수/매도용 alpha
        self.alpha_ema_fast_buy = 2 / (self.ema_fast_buy_period + 1)
        self.alpha_ema_slow_buy = 2 / (self.ema_slow_buy_period + 1)
        self.alpha_ema_fast_sell = 2 / (self.ema_fast_sell_period + 1)
        self.alpha_ema_slow_sell = 2 / (self.ema_slow_sell_period + 1)

        # 상태 (이전 값) - MACD 전략용
        self.ema_macd_fast: Optional[float] = None  # MACD용 fast EMA
        self.ema_macd_slow: Optional[float] = None  # MACD용 slow EMA
        self.ema_signal: Optional[float] = None     # Signal 라인 (MACD의 EMA)

        # 상태 (이전 값) - EMA 전략용 (공통 또는 백워드 호환)
        self.ema_fast: Optional[float] = None
        self.ema_slow: Optional[float] = None
        self.ema_base: Optional[float] = None

        # 매수/매도 별도 EMA 상태
        self.ema_fast_buy: Optional[float] = None
        self.ema_slow_buy: Optional[float] = None
        self.ema_fast_sell: Optional[float] = None
        self.ema_slow_sell: Optional[float] = None

        # 현재/이전 값 (크로스 판정용)
        self.macd: Optional[float] = None
        self.signal: Optional[float] = None
        self.hist: Optional[float] = None
        self.prev_macd: Optional[float] = None
        self.prev_signal: Optional[float] = None
        self.prev_ema_fast: Optional[float] = None
        self.prev_ema_slow: Optional[float] = None

        # 매수/매도용 이전 값
        self.prev_ema_fast_buy: Optional[float] = None
        self.prev_ema_slow_buy: Optional[float] = None
        self.prev_ema_fast_sell: Optional[float] = None
        self.prev_ema_slow_sell: Optional[float] = None

        self.initialized = False
        self.bar_count = 0

    def seed_from_closes(self, closes: List[float]) -> bool:
        """
        초기 시드 (SMA로 시작)

        Args:
            closes: 종가 리스트 (최소 max(macd_slow, ema_slow, base_ema, buy/sell EMA) 개 필요)

        Returns:
            bool: 시드 성공 여부
        """
        # 필요한 최소 데이터 개수 계산
        if self.use_separate_ema:
            required = max(
                self.macd_slow_period,
                self.ema_slow_period,
                self.base_ema_period,
                self.ema_slow_buy_period,
                self.ema_slow_sell_period,
            )
        else:
            required = max(self.macd_slow_period, self.ema_slow_period, self.base_ema_period)

        if len(closes) < required:
            logger.warning(f"⚠️ Not enough data for seed: {len(closes)} < {required}")
            return False

        # MACD용 EMA 시드 (SMA로 시작)
        self.ema_macd_fast = sum(closes[-self.macd_fast_period:]) / self.macd_fast_period
        self.ema_macd_slow = sum(closes[-self.macd_slow_period:]) / self.macd_slow_period

        # EMA 전략용 시드 (공통 또는 백워드 호환)
        self.ema_fast = sum(closes[-self.ema_fast_period:]) / self.ema_fast_period
        self.ema_slow = sum(closes[-self.ema_slow_period:]) / self.ema_slow_period
        self.ema_base = sum(closes[-self.base_ema_period:]) / self.base_ema_period

        # 매수/매도용 EMA 시드 (use_separate_ema일 때)
        if self.use_separate_ema:
            self.ema_fast_buy = sum(closes[-self.ema_fast_buy_period:]) / self.ema_fast_buy_period
            self.ema_slow_buy = sum(closes[-self.ema_slow_buy_period:]) / self.ema_slow_buy_period
            self.ema_fast_sell = sum(closes[-self.ema_fast_sell_period:]) / self.ema_fast_sell_period
            self.ema_slow_sell = sum(closes[-self.ema_slow_sell_period:]) / self.ema_slow_sell_period

        # MACD 계산
        self.macd = self.ema_macd_fast - self.ema_macd_slow
        self.signal = self.macd  # Signal은 MACD로 시작
        self.hist = 0.0

        # 이전 값 초기화 (크로스 판정용)
        self.prev_macd = None
        self.prev_signal = None
        self.prev_ema_fast = None
        self.prev_ema_slow = None
        self.prev_ema_fast_buy = None
        self.prev_ema_slow_buy = None
        self.prev_ema_fast_sell = None
        self.prev_ema_slow_sell = None

        self.initialized = True

        if self.use_separate_ema:
            logger.info(
                f"✅ Indicator seeded (separate EMA) | "
                f"BUY: fast={self.ema_fast_buy:.2f}, slow={self.ema_slow_buy:.2f} | "
                f"SELL: fast={self.ema_fast_sell:.2f}, slow={self.ema_slow_sell:.2f} | "
                f"base={self.ema_base:.2f} | macd={self.macd:.5f}, signal={self.signal:.5f}"
            )
        else:
            logger.info(
                f"✅ Indicator seeded (common EMA) | "
                f"ema_fast={self.ema_fast:.2f}, ema_slow={self.ema_slow:.2f}, ema_base={self.ema_base:.2f} | "
                f"macd={self.macd:.5f}, signal={self.signal:.5f}"
            )
        return True

    def update_incremental(self, close: float):
        """
        새 봉 1개 기준으로 증분 갱신
        ★ 핵심: 전체 재계산 없이 이전 값만 이용

        Args:
            close: 새 봉의 종가
        """
        if not self.initialized:
            logger.warning("⚠️ Indicator not initialized. Call seed_from_closes() first.")
            return

        # 이전 값 저장 (크로스 판정용)
        self.prev_macd = self.macd
        self.prev_signal = self.signal
        self.prev_ema_fast = self.ema_fast
        self.prev_ema_slow = self.ema_slow

        # 매수/매도용 이전 값 저장
        if self.use_separate_ema:
            self.prev_ema_fast_buy = self.ema_fast_buy
            self.prev_ema_slow_buy = self.ema_slow_buy
            self.prev_ema_fast_sell = self.ema_fast_sell
            self.prev_ema_slow_sell = self.ema_slow_sell

        # EMA 증분 계산: ema = alpha * price + (1 - alpha) * ema_prev
        self.ema_macd_fast = self.alpha_macd_fast * close + (1 - self.alpha_macd_fast) * self.ema_macd_fast
        self.ema_macd_slow = self.alpha_macd_slow * close + (1 - self.alpha_macd_slow) * self.ema_macd_slow
        self.ema_fast = self.alpha_ema_fast * close + (1 - self.alpha_ema_fast) * self.ema_fast
        self.ema_slow = self.alpha_ema_slow * close + (1 - self.alpha_ema_slow) * self.ema_slow
        self.ema_base = self.alpha_base_ema * close + (1 - self.alpha_base_ema) * self.ema_base

        # 매수/매도용 EMA 증분 계산
        if self.use_separate_ema:
            self.ema_fast_buy = self.alpha_ema_fast_buy * close + (1 - self.alpha_ema_fast_buy) * self.ema_fast_buy
            self.ema_slow_buy = self.alpha_ema_slow_buy * close + (1 - self.alpha_ema_slow_buy) * self.ema_slow_buy
            self.ema_fast_sell = self.alpha_ema_fast_sell * close + (1 - self.alpha_ema_fast_sell) * self.ema_fast_sell
            self.ema_slow_sell = self.alpha_ema_slow_sell * close + (1 - self.alpha_ema_slow_sell) * self.ema_slow_sell

        # MACD 계산
        self.macd = self.ema_macd_fast - self.ema_macd_slow
        self.signal = self.alpha_macd_signal * self.macd + (1 - self.alpha_macd_signal) * self.signal
        self.hist = self.macd - self.signal

        self.bar_count += 1

    def get_snapshot(self, is_buy_eval: bool = True) -> Dict[str, Any]:
        """
        현재 상태 스냅샷 (전략 평가용)

        Args:
            is_buy_eval: 매수 평가인지 여부 (True: 매수, False: 매도)

        Returns:
            dict: 모든 지표 값 (매수/매도 평가에 맞는 EMA 포함)
        """
        # use_separate_ema일 때 매수/매도에 따라 다른 EMA 반환
        if self.use_separate_ema:
            if is_buy_eval:
                ema_fast = self.ema_fast_buy
                ema_slow = self.ema_slow_buy
                prev_ema_fast = self.prev_ema_fast_buy
                prev_ema_slow = self.prev_ema_slow_buy
            else:
                ema_fast = self.ema_fast_sell
                ema_slow = self.ema_slow_sell
                prev_ema_fast = self.prev_ema_fast_sell
                prev_ema_slow = self.prev_ema_slow_sell
        else:
            # 공통 EMA 사용 (백워드 호환)
            ema_fast = self.ema_fast
            ema_slow = self.ema_slow
            prev_ema_fast = self.prev_ema_fast
            prev_ema_slow = self.prev_ema_slow

        return {
            # MACD 전략용
            "macd": self.macd,
            "signal": self.signal,
            "hist": self.hist,
            "prev_macd": self.prev_macd,
            "prev_signal": self.prev_signal,
            # EMA 전략용 (매수/매도 평가에 맞는 값)
            "ema_fast": ema_fast,
            "ema_slow": ema_slow,
            "ema_base": self.ema_base,
            "prev_ema_fast": prev_ema_fast,
            "prev_ema_slow": prev_ema_slow,
            # 메타
            "bar_count": self.bar_count,
            # 디버깅용: 매수/매도 별도 EMA 전체 노출
            "use_separate_ema": self.use_separate_ema,
            "ema_fast_buy": self.ema_fast_buy if self.use_separate_ema else None,
            "ema_slow_buy": self.ema_slow_buy if self.use_separate_ema else None,
            "ema_fast_sell": self.ema_fast_sell if self.use_separate_ema else None,
            "ema_slow_sell": self.ema_slow_sell if self.use_separate_ema else None,
        }

    def detect_golden_cross(self) -> bool:
        """
        MACD 골든크로스 판정
        - prev: macd <= signal
        - curr: macd > signal
        """
        if self.prev_macd is None or self.prev_signal is None:
            return False
        return self.prev_macd <= self.prev_signal and self.macd > self.signal

    def detect_dead_cross(self) -> bool:
        """
        MACD 데드크로스 판정
        - prev: macd >= signal
        - curr: macd < signal
        """
        if self.prev_macd is None or self.prev_signal is None:
            return False
        return self.prev_macd >= self.prev_signal and self.macd < self.signal

    def detect_ema_golden_cross(self) -> bool:
        """
        EMA 골든크로스 판정
        - prev: fast <= slow
        - curr: fast > slow
        """
        if self.prev_ema_fast is None or self.prev_ema_slow is None:
            return False
        return self.prev_ema_fast <= self.prev_ema_slow and self.ema_fast > self.ema_slow

    def detect_ema_dead_cross(self) -> bool:
        """
        EMA 데드크로스 판정
        - prev: fast >= slow
        - curr: fast < slow
        """
        if self.prev_ema_fast is None or self.prev_ema_slow is None:
            return False
        return self.prev_ema_fast >= self.prev_ema_slow and self.ema_fast < self.ema_slow
