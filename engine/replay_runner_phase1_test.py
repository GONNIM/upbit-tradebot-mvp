"""
Phase 1 백테스트 스크립트
- 현재 설정 vs Phase 1 설정 비교
- 3월 1일 ~ 3월 21일 (21일간) 데이터 사용
"""
import pyupbit
import pandas as pd
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from engine.params import load_params
from engine.live_loop import run_replay_on_dataframe

USER_ID = "mcmax33"

def run_backtest(params_file: str, conditions_file: str, label: str):
    """백테스트 실행"""
    print(f"\n{'='*80}")
    print(f"📊 백테스트 시작: {label}")
    print(f"{'='*80}")

    # 파라미터 로드
    params = load_params(params_file, conditions_file)

    # 데이터 기간 설정 (3월 1일 ~ 3월 21일, 21일간)
    # count = 21일 * 24시간 * 60분 = 30,240개 (1분봉)
    # pyupbit 최대 200개 제한이 있으므로 여러 번 호출 필요
    ticker = f"KRW-{params.ticker}"

    print(f"📈 데이터 조회: {ticker}, interval={params.interval}")

    # 3월 21일 10:00 (현재)부터 역순으로 데이터 수집
    end_time = datetime(2026, 3, 21, 10, 0, 0, tzinfo=ZoneInfo("Asia/Seoul"))
    start_time = datetime(2026, 3, 1, 0, 0, 0, tzinfo=ZoneInfo("Asia/Seoul"))

    # 1분봉 데이터 수집
    all_data = []
    current_time = end_time

    while current_time > start_time:
        try:
            df_chunk = pyupbit.get_ohlcv(
                ticker=ticker,
                interval=params.interval,
                to=current_time.strftime("%Y-%m-%d %H:%M:%S"),
                count=200  # pyupbit 최대값
            )

            if df_chunk is None or df_chunk.empty:
                break

            all_data.append(df_chunk)
            print(f"  ✅ 수집: {df_chunk.index[0]} ~ {df_chunk.index[-1]} ({len(df_chunk)}개)")

            # 다음 조회 시작점
            current_time = df_chunk.index[0] - timedelta(minutes=1)

            # start_time 이전 데이터는 제거
            if df_chunk.index[0] < start_time:
                break

        except Exception as e:
            print(f"  ❌ 데이터 조회 실패: {e}")
            break

    if not all_data:
        print("❌ 데이터 수집 실패")
        return None

    # 데이터 병합 및 정렬
    df = pd.concat(all_data)
    df = df[~df.index.duplicated(keep='first')]  # 중복 제거
    df = df.sort_index()

    # start_time 이후 데이터만 필터링
    df = df[df.index >= start_time]

    print(f"✅ 전체 데이터: {df.index[0]} ~ {df.index[-1]} ({len(df)}개 봉)")

    # 백테스트 실행
    print(f"\n🚀 백테스트 실행 중...")
    result = run_replay_on_dataframe(
        params=params,
        df=df,
        user_id=USER_ID,
        strategy_type=params.strategy_type,
    )

    trade_events = result["trade_events"]
    df_bt = result["df_bt"]

    # 결과 분석
    print(f"\n{'='*80}")
    print(f"📊 백테스트 결과: {label}")
    print(f"{'='*80}")

    buys = [e for e in trade_events if e["type"] == "BUY"]
    sells = [e for e in trade_events if e["type"] == "SELL"]

    print(f"총 매수: {len(buys)}회")
    print(f"총 매도: {len(sells)}회")

    # 수익률 계산
    profits = []
    losses = []

    for i, sell_event in enumerate(sells):
        # 해당 매도 이전의 마지막 매수 찾기
        buy_candidates = [b for b in buys if b["bar"] < sell_event["bar"]]
        if buy_candidates:
            buy_event = buy_candidates[-1]
            buy_price = buy_event["price"]
            sell_price = sell_event["price"]
            pnl_pct = (sell_price - buy_price) / buy_price

            if pnl_pct >= 0:
                profits.append(pnl_pct)
            else:
                losses.append(pnl_pct)

    if profits or losses:
        total_trades = len(profits) + len(losses)
        win_rate = len(profits) / total_trades if total_trades > 0 else 0
        avg_profit = sum(profits) / len(profits) if profits else 0
        avg_loss = sum(losses) / len(losses) if losses else 0
        total_return = sum(profits) + sum(losses)

        print(f"\n승률: {win_rate:.1%} ({len(profits)}/{total_trades})")
        print(f"평균 수익: {avg_profit:.2%}")
        print(f"평균 손실: {avg_loss:.2%}")
        print(f"총 수익률: {total_return:.2%}")
        print(f"Whipsaw 횟수 추정: {len(sells) - len(profits)}회")
    else:
        print("\n매매 완료 건수: 0")

    # 상세 매매 내역
    print(f"\n{'='*80}")
    print(f"📝 매매 상세 내역")
    print(f"{'='*80}")

    for i, evt in enumerate(trade_events[:20]):  # 최대 20개만 출력
        ts = df_bt.index[evt["bar"]]
        reason = evt.get("reason", "N/A")
        price = evt.get("price", 0)

        print(f"{ts} | {evt['type']:4s} | {price:8.0f}원 | {reason}")

    if len(trade_events) > 20:
        print(f"... (총 {len(trade_events)}개 이벤트)")

    return {
        "label": label,
        "buys": len(buys),
        "sells": len(sells),
        "win_rate": win_rate if (profits or losses) else 0,
        "avg_profit": avg_profit if (profits or losses) else 0,
        "avg_loss": avg_loss if (losses or losses) else 0,
        "total_return": total_return if (profits or losses) else 0,
        "whipsaw_count": len(sells) - len(profits) if (profits or losses) else 0,
        "trade_events": trade_events,
    }


if __name__ == "__main__":
    print("\n" + "="*80)
    print("🔬 Phase 1 백테스트 비교 분석")
    print("="*80)
    print(f"기간: 2026-03-01 ~ 2026-03-21 (21일간)")
    print(f"티커: KRW-ZRO")
    print(f"봉 간격: 1분")
    print("="*80)

    # 1. 현재 설정 (기준선)
    result_current = run_backtest(
        params_file="mcmax33_latest_params.json",
        conditions_file="mcmax33_EMA_buy_sell_conditions.json",
        label="현재 설정 (기준선)"
    )

    # 2. Phase 1 설정 (개선안)
    result_phase1 = run_backtest(
        params_file="mcmax33_latest_params_phase1.json",
        conditions_file="mcmax33_EMA_buy_sell_conditions_phase1.json",
        label="Phase 1 (필터 강화)"
    )

    # 3. 비교 분석
    if result_current and result_phase1:
        print("\n" + "="*80)
        print("📊 비교 분석 결과")
        print("="*80)

        print(f"\n{'항목':<20} | {'현재 설정':>15} | {'Phase 1':>15} | {'개선율':>15}")
        print("-" * 80)

        metrics = [
            ("매수 횟수", "buys", "회"),
            ("매도 횟수", "sells", "회"),
            ("승률", "win_rate", "%"),
            ("평균 수익", "avg_profit", "%"),
            ("평균 손실", "avg_loss", "%"),
            ("총 수익률", "total_return", "%"),
            ("Whipsaw 횟수", "whipsaw_count", "회"),
        ]

        for name, key, unit in metrics:
            current_val = result_current.get(key, 0)
            phase1_val = result_phase1.get(key, 0)

            if unit == "%":
                current_str = f"{current_val:.2%}"
                phase1_str = f"{phase1_val:.2%}"

                if current_val != 0:
                    improvement = ((phase1_val - current_val) / abs(current_val)) * 100
                else:
                    improvement = 0
            else:
                current_str = f"{current_val}{unit}"
                phase1_str = f"{phase1_val}{unit}"

                if current_val != 0:
                    improvement = ((phase1_val - current_val) / current_val) * 100
                else:
                    improvement = 0

            improvement_str = f"{improvement:+.1f}%"
            print(f"{name:<20} | {current_str:>15} | {phase1_str:>15} | {improvement_str:>15}")

        print("\n" + "="*80)
        print("✅ 백테스트 완료")
        print("="*80)
