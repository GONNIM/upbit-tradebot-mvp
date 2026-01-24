"""
Phase 2: Redis 캐시 레이어
- WebSocket 실시간 데이터를 Redis에 캐싱
- REST API 실패 시 캐시 데이터 활용
- TTL 설정으로 stale 데이터 방지
"""
from __future__ import annotations
import redis
import pandas as pd
import json
import logging
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class RedisCandleCache:
    """Redis를 사용한 캔들 데이터 캐시"""

    def __init__(self, host: str = "localhost", port: int = 6379, db: int = 0, password: Optional[str] = None):
        """
        Redis 연결 초기화

        Args:
            host: Redis 호스트
            port: Redis 포트
            db: Redis DB 번호
            password: Redis 비밀번호 (선택)
        """
        self.enabled = False
        self.client = None

        try:
            self.client = redis.Redis(
                host=host,
                port=port,
                db=db,
                password=password,
                decode_responses=False,  # bytes로 받아서 직접 처리
                socket_connect_timeout=5,
                socket_timeout=5,
            )
            # 연결 테스트
            self.client.ping()
            self.enabled = True
            logger.info(f"✅ [REDIS] 연결 성공: {host}:{port}/{db}")
        except redis.ConnectionError as e:
            logger.warning(f"⚠️ [REDIS] 연결 실패 (캐시 비활성화): {e}")
            self.enabled = False
        except Exception as e:
            logger.error(f"❌ [REDIS] 초기화 실패 (캐시 비활성화): {e}")
            self.enabled = False

    def _make_key(self, ticker: str, interval: str, timestamp: datetime) -> str:
        """캐시 키 생성"""
        ts_str = timestamp.strftime("%Y%m%d%H%M%S")
        return f"candle:{ticker}:{interval}:{ts_str}"

    def _make_latest_key(self, ticker: str, interval: str) -> str:
        """최신 봉 타임스탬프 키 생성"""
        return f"candle:latest:{ticker}:{interval}"

    def save_candle(self, ticker: str, interval: str, timestamp: datetime, ohlcv: dict, ttl: int = 3600):
        """
        단일 캔들 저장

        Args:
            ticker: 티커 (예: "KRW-SUI")
            interval: 봉 간격 (예: "minute3")
            timestamp: 봉 시각 (KST naive)
            ohlcv: {"Open": float, "High": float, "Low": float, "Close": float, "Volume": float}
            ttl: 캐시 유효 시간 (초)
        """
        if not self.enabled:
            return

        try:
            key = self._make_key(ticker, interval, timestamp)
            value = json.dumps({
                "timestamp": timestamp.isoformat(),
                "Open": float(ohlcv.get("Open", 0)),
                "High": float(ohlcv.get("High", 0)),
                "Low": float(ohlcv.get("Low", 0)),
                "Close": float(ohlcv.get("Close", 0)),
                "Volume": float(ohlcv.get("Volume", 0)),
            })

            # 캔들 데이터 저장
            self.client.setex(key, ttl, value)

            # 최신 타임스탬프 업데이트
            latest_key = self._make_latest_key(ticker, interval)
            self.client.set(latest_key, timestamp.isoformat())

            logger.debug(f"[REDIS-SAVE] {key}")
        except Exception as e:
            logger.warning(f"⚠️ [REDIS-SAVE] 저장 실패: {e}")

    def save_candles_bulk(self, ticker: str, interval: str, df: pd.DataFrame, ttl: int = 3600):
        """
        여러 캔들 일괄 저장

        Args:
            ticker: 티커
            interval: 봉 간격
            df: DataFrame (index=datetime, columns=[Open, High, Low, Close, Volume])
            ttl: 캐시 유효 시간 (초)
        """
        if not self.enabled or df is None or df.empty:
            return

        try:
            pipeline = self.client.pipeline()
            count = 0

            for idx, row in df.iterrows():
                key = self._make_key(ticker, interval, idx)
                value = json.dumps({
                    "timestamp": idx.isoformat(),
                    "Open": float(row.get("Open", 0)),
                    "High": float(row.get("High", 0)),
                    "Low": float(row.get("Low", 0)),
                    "Close": float(row.get("Close", 0)),
                    "Volume": float(row.get("Volume", 0)),
                })
                pipeline.setex(key, ttl, value)
                count += 1

            # 최신 타임스탬프 업데이트
            latest_ts = df.index[-1]
            latest_key = self._make_latest_key(ticker, interval)
            pipeline.set(latest_key, latest_ts.isoformat())

            pipeline.execute()
            logger.info(f"✅ [REDIS-BULK-SAVE] {count}개 캔들 저장: {ticker}/{interval}")
        except Exception as e:
            logger.warning(f"⚠️ [REDIS-BULK-SAVE] 저장 실패: {e}")

    def get_candle(self, ticker: str, interval: str, timestamp: datetime) -> Optional[dict]:
        """
        단일 캔들 조회

        Args:
            ticker: 티커
            interval: 봉 간격
            timestamp: 봉 시각

        Returns:
            {"timestamp": str, "Open": float, ...} 또는 None
        """
        if not self.enabled:
            return None

        try:
            key = self._make_key(ticker, interval, timestamp)
            value = self.client.get(key)

            if value:
                data = json.loads(value)
                logger.debug(f"[REDIS-HIT] {key}")
                return data
            else:
                logger.debug(f"[REDIS-MISS] {key}")
                return None
        except Exception as e:
            logger.warning(f"⚠️ [REDIS-GET] 조회 실패: {e}")
            return None

    def get_latest_timestamp(self, ticker: str, interval: str) -> Optional[datetime]:
        """
        최신 봉 타임스탬프 조회

        Returns:
            datetime 또는 None
        """
        if not self.enabled:
            return None

        try:
            latest_key = self._make_latest_key(ticker, interval)
            value = self.client.get(latest_key)

            if value:
                ts_str = value.decode('utf-8') if isinstance(value, bytes) else value
                return datetime.fromisoformat(ts_str)
            return None
        except Exception as e:
            logger.warning(f"⚠️ [REDIS-LATEST] 조회 실패: {e}")
            return None

    def clear_ticker(self, ticker: str, interval: str):
        """특정 티커/간격의 모든 캐시 삭제"""
        if not self.enabled:
            return

        try:
            pattern = f"candle:{ticker}:{interval}:*"
            keys = self.client.keys(pattern)

            if keys:
                self.client.delete(*keys)
                logger.info(f"✅ [REDIS-CLEAR] {len(keys)}개 키 삭제: {ticker}/{interval}")

            # 최신 타임스탬프도 삭제
            latest_key = self._make_latest_key(ticker, interval)
            self.client.delete(latest_key)
        except Exception as e:
            logger.warning(f"⚠️ [REDIS-CLEAR] 삭제 실패: {e}")

    def close(self):
        """Redis 연결 종료"""
        if self.client:
            try:
                self.client.close()
                logger.info("✅ [REDIS] 연결 종료")
            except Exception as e:
                logger.warning(f"⚠️ [REDIS] 종료 실패: {e}")


# 전역 캐시 인스턴스 (lazy initialization)
_cache_instance: Optional[RedisCandleCache] = None


def get_redis_cache(host: str = "localhost", port: int = 6379, db: int = 0, password: Optional[str] = None) -> RedisCandleCache:
    """
    Redis 캐시 인스턴스 가져오기 (싱글톤 패턴)

    Args:
        host: Redis 호스트
        port: Redis 포트
        db: Redis DB 번호
        password: Redis 비밀번호

    Returns:
        RedisCandleCache 인스턴스
    """
    global _cache_instance

    if _cache_instance is None:
        _cache_instance = RedisCandleCache(host, port, db, password)

    return _cache_instance
