"""
Phase 2 통합 테스트
- Redis 연결 확인
- WebSocket 데이터 수신 확인
- 다중 소스 조회 확인
"""
import os
import sys
import time
import logging

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_redis_connection():
    """Redis 연결 테스트"""
    logger.info("=" * 60)
    logger.info("테스트 1: Redis 연결 확인")
    logger.info("=" * 60)

    try:
        from core.redis_cache import get_redis_cache
        from config import REDIS_ENABLED, REDIS_HOST, REDIS_PORT, REDIS_DB

        if not REDIS_ENABLED:
            logger.warning("⚠️ REDIS_ENABLED=false (환경변수 확인)")
            logger.info("💡 Redis를 활성화하려면: export REDIS_ENABLED=true")
            return False

        cache = get_redis_cache(REDIS_HOST, REDIS_PORT, REDIS_DB)

        if cache.enabled:
            logger.info(f"✅ Redis 연결 성공: {REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}")
            return True
        else:
            logger.error("❌ Redis 연결 실패 (Redis 서버가 실행 중인지 확인)")
            logger.info("💡 로컬 Redis 시작: redis-server")
            return False
    except Exception as e:
        logger.error(f"❌ Redis 테스트 실패: {e}")
        return False


def test_websocket_feed():
    """WebSocket 데이터 수신 테스트"""
    logger.info("\n" + "=" * 60)
    logger.info("테스트 2: WebSocket 데이터 수신 확인")
    logger.info("=" * 60)

    try:
        from core.websocket_feed import get_websocket_aggregator
        from core.redis_cache import get_redis_cache
        from config import WEBSOCKET_ENABLED, REDIS_ENABLED, REDIS_HOST, REDIS_PORT, REDIS_DB

        if not WEBSOCKET_ENABLED:
            logger.warning("⚠️ WEBSOCKET_ENABLED=false (환경변수 확인)")
            return False

        # Redis 캐시 (선택)
        redis_cache = None
        if REDIS_ENABLED:
            redis_cache = get_redis_cache(REDIS_HOST, REDIS_PORT, REDIS_DB)

        # WebSocket 시작
        ticker = "KRW-BTC"
        logger.info(f"WebSocket 시작: {ticker} (10초간 데이터 수신 테스트)")

        aggregator = get_websocket_aggregator(ticker, redis_cache)

        # 10초 대기
        time.sleep(10)

        # 현재 봉 확인
        current_candle = aggregator.get_current_candle()
        if current_candle:
            logger.info(f"✅ WebSocket 데이터 수신 성공:")
            logger.info(f"   시각: {current_candle['timestamp']}")
            logger.info(f"   가격: O={current_candle['Open']:.0f} H={current_candle['High']:.0f} "
                       f"L={current_candle['Low']:.0f} C={current_candle['Close']:.0f}")
            logger.info(f"   거래량: {current_candle['Volume']:.4f}")
            logger.info(f"   체결횟수: {current_candle['trade_count']}")
            return True
        else:
            logger.warning("⚠️ WebSocket 데이터 없음 (Upbit 시장 시간 확인)")
            return False

    except Exception as e:
        logger.error(f"❌ WebSocket 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_multi_source_fetch():
    """다중 소스 조회 테스트"""
    logger.info("\n" + "=" * 60)
    logger.info("테스트 3: 다중 소스 조회 (Redis → REST API)")
    logger.info("=" * 60)

    try:
        import pandas as pd
        from datetime import datetime
        from core.redis_cache import get_redis_cache
        from config import REDIS_ENABLED, REDIS_HOST, REDIS_PORT, REDIS_DB, REDIS_PASSWORD
        import pyupbit

        ticker = "KRW-BTC"
        interval = "minute1"

        # 1단계: REST API로 최신 봉 가져오기
        logger.info(f"[1/3] REST API 호출: {ticker}/{interval}")
        df = pyupbit.get_ohlcv(ticker, interval=interval, count=5)

        if df is None or df.empty:
            logger.error("❌ REST API 응답 없음")
            return False

        latest_candle = df.iloc[-1]
        latest_ts = df.index[-1]
        logger.info(f"✅ REST API 응답: {latest_ts} | C={latest_candle['close']:.0f}")

        # 2단계: Redis에 저장 (Redis 활성화된 경우)
        if REDIS_ENABLED:
            logger.info(f"[2/3] Redis에 저장")
            cache = get_redis_cache(REDIS_HOST, REDIS_PORT, REDIS_DB, REDIS_PASSWORD)

            if cache.enabled:
                # DataFrame 표준화
                df_std = df.rename(columns={
                    "open": "Open",
                    "high": "High",
                    "low": "Low",
                    "close": "Close",
                    "volume": "Volume"
                })

                cache.save_candles_bulk(ticker, interval, df_std, ttl=300)
                logger.info(f"✅ Redis 저장 완료: {len(df_std)}개 봉")

                # 3단계: Redis에서 조회
                logger.info(f"[3/3] Redis에서 조회")
                cached_data = cache.get_candle(ticker, interval, latest_ts)

                if cached_data:
                    logger.info(f"✅ Redis 캐시 히트: {latest_ts}")
                    logger.info(f"   원본: C={latest_candle['close']:.0f}")
                    logger.info(f"   캐시: C={cached_data['Close']:.0f}")

                    # 데이터 일치 확인
                    if abs(cached_data['Close'] - latest_candle['close']) < 0.01:
                        logger.info("✅ 데이터 일치 확인 성공")
                        return True
                    else:
                        logger.error("❌ 데이터 불일치")
                        return False
                else:
                    logger.error("❌ Redis 캐시 미스 (저장 실패?)")
                    return False
            else:
                logger.warning("⚠️ Redis 비활성화 (REST API만 사용)")
                return True
        else:
            logger.info("[2/3] Redis 비활성화 (스킵)")
            logger.info("✅ REST API 단독 동작 확인")
            return True

    except Exception as e:
        logger.error(f"❌ 다중 소스 조회 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """메인 테스트 실행"""
    logger.info("=" * 60)
    logger.info("Phase 2 통합 테스트 시작")
    logger.info("=" * 60)

    results = {
        "Redis 연결": test_redis_connection(),
        "WebSocket 수신": test_websocket_feed(),
        "다중 소스 조회": test_multi_source_fetch(),
    }

    # 결과 요약
    logger.info("\n" + "=" * 60)
    logger.info("테스트 결과 요약")
    logger.info("=" * 60)

    for test_name, result in results.items():
        status = "✅ 성공" if result else "❌ 실패"
        logger.info(f"{test_name:20s}: {status}")

    # WebSocket 정리
    try:
        from core.websocket_feed import stop_all_websockets
        stop_all_websockets()
    except:
        pass

    # 전체 결과
    all_passed = all(results.values())

    if all_passed:
        logger.info("\n🎉 모든 테스트 통과!")
        return 0
    else:
        logger.info("\n⚠️ 일부 테스트 실패 (설정 확인 필요)")
        logger.info("\n💡 Redis 활성화 방법:")
        logger.info("   1. Redis 설치: brew install redis (macOS)")
        logger.info("   2. Redis 시작: redis-server")
        logger.info("   3. 환경변수: export REDIS_ENABLED=true")
        return 1


if __name__ == "__main__":
    sys.exit(main())
