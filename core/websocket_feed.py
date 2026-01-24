"""
Phase 2: WebSocket 실시간 데이터 수신 레이어
- pyupbit WebSocketManager를 사용하여 실시간 틱 데이터 수신
- 분봉 집계 및 Redis 캐싱
- REST API 지연 보완용
"""
from __future__ import annotations
import pyupbit
import pandas as pd
import time
import logging
import threading
from datetime import datetime, timedelta
from typing import Optional, Dict, Callable
from collections import defaultdict
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)


class WebSocketCandleAggregator:
    """
    WebSocket 틱 데이터를 받아서 분봉으로 집계하는 클래스
    - 실시간 틱 데이터 수신
    - 분 단위 OHLCV 집계
    - Redis 캐싱 연동
    """

    def __init__(self, ticker: str, redis_cache=None):
        """
        초기화

        Args:
            ticker: 티커 (예: "KRW-SUI")
            redis_cache: RedisCandleCache 인스턴스 (선택)
        """
        self.ticker = ticker
        self.redis_cache = redis_cache
        self.running = False
        self.thread = None
        self.ws = None

        # 분봉 집계 버퍼 {minute_timestamp: {"Open": float, "High": float, "Low": float, "Close": float, "Volume": float, "trade_count": int}}
        self.candle_buffer: Dict[datetime, dict] = {}
        self.lock = threading.Lock()

        # 최신 완성 봉 타임스탬프
        self.latest_completed_candle: Optional[datetime] = None

        logger.info(f"[WS-INIT] WebSocket 집계기 초기화: {ticker}")

    def _floor_to_minute(self, dt: datetime) -> datetime:
        """초와 마이크로초를 제거하여 분 단위로 내림"""
        return dt.replace(second=0, microsecond=0)

    def _process_tick(self, data: dict):
        """
        틱 데이터 처리 및 분봉 집계

        Args:
            data: WebSocket에서 받은 틱 데이터
                {
                    "type": "trade",
                    "code": "KRW-BTC",
                    "timestamp": 1234567890123,  # ms
                    "trade_price": 50000000.0,
                    "trade_volume": 0.1,
                    ...
                }
        """
        try:
            if data.get("type") != "trade":
                return

            # 타임스탬프 파싱 (ms → KST naive datetime)
            ts_ms = data.get("timestamp", 0)
            dt_kst = datetime.fromtimestamp(ts_ms / 1000, tz=ZoneInfo("Asia/Seoul")).replace(tzinfo=None)
            minute_ts = self._floor_to_minute(dt_kst)

            price = float(data.get("trade_price", 0))
            volume = float(data.get("trade_volume", 0))

            if price == 0 or volume == 0:
                return

            with self.lock:
                if minute_ts not in self.candle_buffer:
                    # 새 분봉 시작
                    self.candle_buffer[minute_ts] = {
                        "Open": price,
                        "High": price,
                        "Low": price,
                        "Close": price,
                        "Volume": volume,
                        "trade_count": 1,
                    }
                    logger.debug(f"[WS-TICK] 새 분봉 시작: {minute_ts} | O={price:.0f}")
                else:
                    # 기존 분봉 업데이트
                    candle = self.candle_buffer[minute_ts]
                    candle["High"] = max(candle["High"], price)
                    candle["Low"] = min(candle["Low"], price)
                    candle["Close"] = price  # 마지막 체결가
                    candle["Volume"] += volume
                    candle["trade_count"] += 1

        except Exception as e:
            logger.warning(f"⚠️ [WS-TICK] 틱 처리 실패: {e}")

    def _finalize_candles(self):
        """
        완성된 분봉을 Redis에 저장하고 버퍼에서 제거
        - 현재 시각 기준 이전 분들은 모두 완성으로 간주
        """
        try:
            now_kst = datetime.now(ZoneInfo("Asia/Seoul")).replace(tzinfo=None)
            current_minute = self._floor_to_minute(now_kst)

            with self.lock:
                completed_timestamps = [ts for ts in self.candle_buffer.keys() if ts < current_minute]

                for ts in completed_timestamps:
                    candle = self.candle_buffer.pop(ts)

                    # Redis에 저장 (minute1만 저장, 다른 간격은 집계 필요 시 추가)
                    if self.redis_cache and self.redis_cache.enabled:
                        self.redis_cache.save_candle(
                            ticker=self.ticker,
                            interval="minute1",
                            timestamp=ts,
                            ohlcv=candle,
                            ttl=3600,  # 1시간
                        )

                    # 최신 완성 봉 업데이트
                    if self.latest_completed_candle is None or ts > self.latest_completed_candle:
                        self.latest_completed_candle = ts

                    logger.info(
                        f"✅ [WS-CANDLE] 분봉 완성: {ts} | "
                        f"O={candle['Open']:.0f} H={candle['High']:.0f} "
                        f"L={candle['Low']:.0f} C={candle['Close']:.0f} "
                        f"V={candle['Volume']:.4f} (체결:{candle['trade_count']}회)"
                    )

        except Exception as e:
            logger.warning(f"⚠️ [WS-FINALIZE] 봉 완성 처리 실패: {e}")

    def _ws_loop(self):
        """WebSocket 수신 루프"""
        logger.info(f"[WS-LOOP] WebSocket 루프 시작: {self.ticker}")

        try:
            # pyupbit WebSocketManager 시작
            self.ws = pyupbit.WebSocketManager("trade", [self.ticker])

            last_finalize = time.time()
            finalize_interval = 10  # 10초마다 완성 봉 처리

            while self.running:
                try:
                    # WebSocket 데이터 수신
                    data = self.ws.get()

                    if data:
                        self._process_tick(data)

                    # 주기적으로 완성 봉 처리
                    if time.time() - last_finalize > finalize_interval:
                        self._finalize_candles()
                        last_finalize = time.time()

                except Exception as e:
                    if self.running:
                        logger.warning(f"⚠️ [WS-LOOP] 데이터 수신 오류: {e}")
                        time.sleep(1)

        except Exception as e:
            logger.error(f"❌ [WS-LOOP] WebSocket 루프 실패: {e}")
        finally:
            if self.ws:
                try:
                    self.ws.terminate()
                except:
                    pass
            logger.info(f"[WS-LOOP] WebSocket 루프 종료: {self.ticker}")

    def start(self):
        """WebSocket 수신 시작 (백그라운드 스레드)"""
        if self.running:
            logger.warning(f"[WS-START] 이미 실행 중: {self.ticker}")
            return

        self.running = True
        self.thread = threading.Thread(target=self._ws_loop, daemon=True)
        self.thread.start()
        logger.info(f"✅ [WS-START] WebSocket 시작: {self.ticker}")

    def stop(self):
        """WebSocket 수신 중지"""
        if not self.running:
            return

        logger.info(f"[WS-STOP] WebSocket 중지 요청: {self.ticker}")
        self.running = False

        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=5)

        # 남은 봉 강제 완성
        self._finalize_candles()

        logger.info(f"✅ [WS-STOP] WebSocket 중지 완료: {self.ticker}")

    def get_latest_candle(self) -> Optional[datetime]:
        """최신 완성 봉 타임스탬프 반환"""
        return self.latest_completed_candle

    def get_current_candle(self) -> Optional[dict]:
        """
        현재 진행 중인 분봉 반환 (미완성)

        Returns:
            {"timestamp": datetime, "Open": float, ...} 또는 None
        """
        now_kst = datetime.now(ZoneInfo("Asia/Seoul")).replace(tzinfo=None)
        current_minute = self._floor_to_minute(now_kst)

        with self.lock:
            candle = self.candle_buffer.get(current_minute)
            if candle:
                return {
                    "timestamp": current_minute,
                    **candle,
                }
        return None


# 전역 WebSocket 집계기 관리
_ws_aggregators: Dict[str, WebSocketCandleAggregator] = {}
_ws_lock = threading.Lock()


def get_websocket_aggregator(ticker: str, redis_cache=None) -> WebSocketCandleAggregator:
    """
    WebSocket 집계기 가져오기 (싱글톤 패턴, 티커별)

    Args:
        ticker: 티커
        redis_cache: RedisCandleCache 인스턴스

    Returns:
        WebSocketCandleAggregator 인스턴스
    """
    global _ws_aggregators

    with _ws_lock:
        if ticker not in _ws_aggregators:
            aggregator = WebSocketCandleAggregator(ticker, redis_cache)
            aggregator.start()  # 자동 시작
            _ws_aggregators[ticker] = aggregator

        return _ws_aggregators[ticker]


def stop_all_websockets():
    """모든 WebSocket 집계기 중지"""
    global _ws_aggregators

    with _ws_lock:
        for ticker, aggregator in _ws_aggregators.items():
            aggregator.stop()

        _ws_aggregators.clear()
        logger.info("✅ [WS-ALL-STOP] 모든 WebSocket 중지 완료")
