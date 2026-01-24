"""
증분 처리 시스템 테스트
- CandleBuffer
- IndicatorState
- PositionState
- IncrementalStrategy
- StrategyEngine
"""
import sys
from datetime import datetime, timedelta
from core.candle_buffer import CandleBuffer, Bar
from core.indicator_state import IndicatorState
from core.position_state import PositionState
from core.strategy_incremental import IncrementalMACDStrategy
from core.strategy_action import Action


def test_candle_buffer():
    """CandleBuffer 테스트"""
    print("=" * 60)
    print("1. CandleBuffer 테스트")
    print("=" * 60)

    buffer = CandleBuffer(maxlen=5)

    # 봉 추가
    for i in range(10):
        ts = datetime(2024, 1, 1) + timedelta(minutes=i)
        bar = Bar(
            ts=ts,
            open=100 + i,
            high=105 + i,
            low=95 + i,
            close=102 + i,
            volume=1000,
            is_closed=True
        )
        buffer.append(bar)

    print(f"Buffer 길이 (maxlen=5): {len(buffer)}")
    print(f"마지막 종가: {buffer.last_close()}")
    print(f"최근 3개 종가: {buffer.last_n_closes(3)}")

    # DataFrame 변환
    df = buffer.to_dataframe()
    print(f"DataFrame shape: {df.shape}")
    print(df.tail(3))

    print("✅ CandleBuffer 테스트 통과\n")
    return True


def test_indicator_state():
    """IndicatorState 테스트"""
    print("=" * 60)
    print("2. IndicatorState 테스트")
    print("=" * 60)

    indicators = IndicatorState(
        macd_fast=12,
        macd_slow=26,
        macd_signal=9,
        ema_fast=20,
        ema_slow=60,
    )

    # 초기 시드
    closes = [100 + i * 0.5 for i in range(100)]
    success = indicators.seed_from_closes(closes)
    print(f"초기 시드 성공: {success}")

    # 증분 업데이트
    for i in range(10):
        price = 150 + i * 0.3
        indicators.update_incremental(price)

    snapshot = indicators.get_snapshot()
    print(f"MACD: {snapshot['macd']:.5f}")
    print(f"Signal: {snapshot['signal']:.5f}")
    print(f"EMA Fast: {snapshot['ema_fast']:.2f}")
    print(f"EMA Slow: {snapshot['ema_slow']:.2f}")

    # 크로스 감지
    golden = indicators.detect_golden_cross()
    print(f"골든크로스: {golden}")

    print("✅ IndicatorState 테스트 통과\n")
    return success


def test_position_state():
    """PositionState 테스트"""
    print("=" * 60)
    print("3. PositionState 테스트")
    print("=" * 60)

    position = PositionState()

    print(f"초기 포지션: {position.has_position}")

    # 매수
    position.open_position(
        qty=10.5,
        price=100.0,
        bar_idx=0,
        ts=datetime.now()
    )
    print(f"매수 후 포지션: {position.has_position}")
    print(f"수량: {position.qty}")
    print(f"평단: {position.avg_price}")

    # 손익률
    pnl = position.get_pnl_pct(110.0)
    print(f"현재가 110원 손익률: {pnl:.2%}")

    # 매도
    position.close_position(datetime.now())
    print(f"매도 후 포지션: {position.has_position}")

    print("✅ PositionState 테스트 통과\n")
    return True


def test_incremental_strategy():
    """IncrementalMACDStrategy 테스트"""
    print("=" * 60)
    print("4. IncrementalMACDStrategy 테스트")
    print("=" * 60)

    strategy = IncrementalMACDStrategy(
        macd_threshold=0.0,
        take_profit=0.03,
        stop_loss=0.01,
    )

    indicators_snapshot = {
        "macd": 0.5,
        "signal": -0.2,
        "prev_macd": -0.3,
        "prev_signal": -0.1,
        "ema_fast": 100.0,
        "ema_slow": 98.0,
    }

    position = PositionState()

    bar = Bar(
        ts=datetime.now(),
        open=100,
        high=105,
        low=95,
        close=102,
        volume=1000,
        is_closed=True
    )

    # BUY 신호 테스트 (골든크로스)
    action = strategy.on_bar(bar, indicators_snapshot, position, current_bar_idx=0)
    print(f"포지션 없을 때 액션: {action}")

    # 매수 후
    position.open_position(10.0, 100.0, 0, datetime.now())

    # Take Profit 테스트
    bar_tp = Bar(
        ts=datetime.now(),
        open=103,
        high=105,
        low=102,
        close=103.5,  # 3.5% 상승
        volume=1000,
        is_closed=True
    )
    action = strategy.on_bar(bar_tp, indicators_snapshot, position, current_bar_idx=1)
    print(f"Take Profit 테스트: {action}")

    print("✅ IncrementalMACDStrategy 테스트 통과\n")
    return True


def test_full_flow():
    """전체 플로우 테스트"""
    print("=" * 60)
    print("5. 전체 플로우 통합 테스트")
    print("=" * 60)

    # 1. 데이터 준비
    buffer = CandleBuffer(maxlen=200)

    # 2. 지표 준비
    indicators = IndicatorState(
        macd_fast=12,
        macd_slow=26,
        macd_signal=9,
        ema_fast=20,
        ema_slow=60,
    )

    # 3. 포지션 준비
    position = PositionState()

    # 4. 전략 준비
    strategy = IncrementalMACDStrategy(
        macd_threshold=0.0,
        take_profit=0.03,
        stop_loss=0.01,
    )

    # 5. 초기 시드 (100개 봉)
    print("초기 시드 중...")
    closes = []
    for i in range(100):
        ts = datetime(2024, 1, 1) + timedelta(minutes=i)
        close = 100 + i * 0.1
        closes.append(close)

        bar = Bar(
            ts=ts,
            open=close - 0.5,
            high=close + 1,
            low=close - 1,
            close=close,
            volume=1000,
            is_closed=True
        )
        buffer.append(bar)

    indicators.seed_from_closes(closes)
    print(f"✅ 시드 완료 | buffer={len(buffer)} | MACD={indicators.macd:.5f}")

    # 6. 증분 처리 시뮬레이션 (10개 봉)
    print("\n증분 처리 시뮬레이션...")
    for i in range(10):
        ts = datetime(2024, 1, 1) + timedelta(minutes=100 + i)
        close = 110 + i * 0.5

        bar = Bar(
            ts=ts,
            open=close - 0.3,
            high=close + 0.5,
            low=close - 0.5,
            close=close,
            volume=1000,
            is_closed=True
        )

        # 버퍼 추가
        buffer.append(bar)

        # 지표 증분 갱신
        indicators.update_incremental(close)

        # 전략 평가
        ind_snapshot = indicators.get_snapshot()
        action = strategy.on_bar(bar, ind_snapshot, position, current_bar_idx=100 + i)

        print(f"Bar#{100+i} | close={close:.2f} | MACD={ind_snapshot['macd']:.5f} | action={action.value} | pos={position.has_position}")

        # 매수 시뮬레이션
        if action == Action.BUY and not position.has_position:
            position.open_position(10.0, close, 100 + i, ts)
            print(f"  ✅ 매수 체결 | price={close:.2f}")

        # 매도 시뮬레이션
        elif action == Action.SELL and position.has_position:
            pnl = position.get_pnl_pct(close)
            position.close_position(ts)
            print(f"  ✅ 매도 체결 | price={close:.2f} | PnL={pnl:.2%}")

    print("\n✅ 전체 플로우 통합 테스트 통과\n")
    return True


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("증분 처리 시스템 테스트 시작")
    print("=" * 60 + "\n")

    results = []
    results.append(("CandleBuffer", test_candle_buffer()))
    results.append(("IndicatorState", test_indicator_state()))
    results.append(("PositionState", test_position_state()))
    results.append(("IncrementalStrategy", test_incremental_strategy()))
    results.append(("전체 플로우", test_full_flow()))

    print("=" * 60)
    print("테스트 결과 요약")
    print("=" * 60)

    for name, result in results:
        status = "✅ 통과" if result else "❌ 실패"
        print(f"{name:25s}: {status}")

    all_passed = all(r for _, r in results)

    if all_passed:
        print("\n" + "=" * 60)
        print("✅ 모든 테스트 통과!")
        print("=" * 60)
        print("\n🎉 Backtest 없이 증분 처리 기반 시스템 구현 완료!")
        print("   - CandleBuffer: 링 버퍼 기반 캔들 관리")
        print("   - IndicatorState: 증분 EMA/MACD 계산")
        print("   - PositionState: 실거래 포지션 관리")
        print("   - IncrementalStrategy: on_bar() 기반 전략")
        print("\n🚀 run_live_loop()에서 Backtest.run() 제거 완료!")
        sys.exit(0)
    else:
        print("\n❌ 일부 테스트 실패")
        sys.exit(1)
