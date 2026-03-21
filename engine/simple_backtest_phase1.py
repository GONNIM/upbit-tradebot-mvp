"""
Phase 1 간단 백테스트 스크립트
- DB에 저장된 실제 매매 기록 분석
- 3월 1일 ~ 3월 21일 기간
"""
import sqlite3
import json
from datetime import datetime
from collections import defaultdict

USER_ID = "mcmax33"
DB_PATH = "services/data/tradebot_mcmax33.db"

def analyze_trades(start_date='2026-03-01', end_date='2026-03-22'):
    """DB에서 실제 매매 기록 분석"""

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("\n" + "="*80)
    print(f"📊 실제 매매 기록 분석")
    print("="*80)
    print(f"기간: {start_date} ~ {end_date}")
    print("="*80)

    # 매수 기록 조회
    cursor.execute("""
        SELECT
            timestamp,
            bar_time,
            bar,
            price,
            notes
        FROM audit_buy_eval
        WHERE overall_ok = 1
          AND date(bar_time) >= ?
          AND date(bar_time) < ?
        ORDER BY timestamp
    """, (start_date, end_date))

    buys = cursor.fetchall()
    print(f"\n✅ 매수 실행: {len(buys)}회")

    for buy in buys:
        timestamp, bar_time, bar, price, notes = buy
        print(f"  {bar_time} | {price:8.0f}원 | bar={bar}")

    # 매도 기록 조회
    cursor.execute("""
        SELECT
            timestamp,
            bar_time,
            bar,
            price,
            trigger_key,
            notes
        FROM audit_sell_eval
        WHERE triggered = 1
          AND date(bar_time) >= ?
          AND date(bar_time) < ?
        ORDER BY timestamp
    """, (start_date, end_date))

    sells = cursor.fetchall()
    print(f"\n✅ 매도 실행: {len(sells)}회")

    # 매도 사유별 분류
    sell_reasons = defaultdict(int)
    for sell in sells:
        timestamp, bar_time, bar, price, trigger_key, notes = sell
        sell_reasons[trigger_key] += 1
        print(f"  {bar_time} | {price:8.0f}원 | {trigger_key:15s} | bar={bar}")

    print(f"\n📊 매도 사유 분석:")
    for reason, count in sell_reasons.items():
        print(f"  {reason:20s}: {count}회")

    # Whipsaw 패턴 감지 (1시간 이내 매수-매도-재매수)
    print(f"\n⚠️  Whipsaw 패턴 분석:")

    whipsaw_count = 0
    if len(buys) > 1:
        for i in range(len(buys) - 1):
            buy1_time = datetime.fromisoformat(buys[i][1].replace('+09:00', ''))
            buy2_time = datetime.fromisoformat(buys[i+1][1].replace('+09:00', ''))

            time_diff = (buy2_time - buy1_time).total_seconds() / 60  # 분 단위

            if time_diff <= 60:  # 1시간 이내 재매수
                whipsaw_count += 1
                print(f"  {buys[i][1]} → {buys[i+1][1]} ({time_diff:.0f}분 간격)")

    print(f"\n  총 Whipsaw 발생: {whipsaw_count}회")

    # 수익률 계산 (매수-매도 페어링)
    print(f"\n💰 수익률 분석:")

    profits = []
    losses = []

    # 간단한 페어링: 각 매도에 대해 직전 매수 찾기
    for sell in sells:
        sell_time = datetime.fromisoformat(sell[1].replace('+09:00', ''))
        sell_price = sell[3]

        # 해당 매도 이전의 마지막 매수 찾기
        buy_candidates = [b for b in buys if datetime.fromisoformat(b[1].replace('+09:00', '')) < sell_time]

        if buy_candidates:
            last_buy = buy_candidates[-1]
            buy_price = last_buy[3]

            pnl = sell_price - buy_price
            pnl_pct = (pnl / buy_price) * 100

            if pnl >= 0:
                profits.append(pnl_pct)
                print(f"  ✅ {last_buy[1]} → {sell[1]}: {pnl_pct:+.2f}% ({buy_price:.0f}원 → {sell_price:.0f}원)")
            else:
                losses.append(pnl_pct)
                print(f"  ❌ {last_buy[1]} → {sell[1]}: {pnl_pct:+.2f}% ({buy_price:.0f}원 → {sell_price:.0f}원)")

    # 통계
    total_trades = len(profits) + len(losses)
    if total_trades > 0:
        win_rate = (len(profits) / total_trades) * 100
        avg_profit = sum(profits) / len(profits) if profits else 0
        avg_loss = sum(losses) / len(losses) if losses else 0
        total_return = sum(profits) + sum(losses)

        print(f"\n📈 통계 요약:")
        print(f"  총 매매: {total_trades}회")
        print(f"  승: {len(profits)}회 | 패: {len(losses)}회")
        print(f"  승률: {win_rate:.1f}%")
        print(f"  평균 수익: {avg_profit:.2f}%")
        print(f"  평균 손실: {avg_loss:.2f}%")
        print(f"  총 수익률: {total_return:.2f}%")

    conn.close()

    return {
        "buys": len(buys),
        "sells": len(sells),
        "sell_reasons": dict(sell_reasons),
        "whipsaw_count": whipsaw_count,
        "win_rate": win_rate if total_trades > 0 else 0,
        "avg_profit": avg_profit if total_trades > 0 else 0,
        "avg_loss": avg_loss if total_trades > 0 else 0,
        "total_return": total_return if total_trades > 0 else 0,
    }


def simulate_phase1_filters():
    """Phase 1 필터 적용 시뮬레이션"""

    print("\n\n" + "="*80)
    print("🔬 Phase 1 필터 적용 시뮬레이션")
    print("="*80)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 모든 매수 평가 기록 조회 (필터링 전)
    cursor.execute("""
        SELECT
            timestamp,
            bar_time,
            bar,
            price,
            macd,
            signal,
            overall_ok,
            checks
        FROM audit_buy_eval
        WHERE date(bar_time) >= '2026-03-01'
          AND date(bar_time) < '2026-03-22'
        ORDER BY timestamp
    """)

    all_buy_evals = cursor.fetchall()

    print(f"\n📊 전체 매수 평가: {len(all_buy_evals)}개 봉")

    # 현재 설정: Golden Cross만
    current_buys = [e for e in all_buy_evals if e[6] == 1]  # overall_ok = 1
    print(f"✅ 현재 설정 매수: {len(current_buys)}회")

    # Phase 1 필터 적용: macd_positive + bullish_candle
    phase1_buys = []

    for eval_record in all_buy_evals:
        timestamp, bar_time, bar, price, macd, signal, overall_ok, checks_json = eval_record

        if overall_ok != 1:
            continue  # Golden Cross 아님

        try:
            checks = json.loads(checks_json)
        except:
            checks = {}

        # Phase 1 필터 체크
        # macd_positive: MACD > 0
        if macd is not None and macd <= 0:
            print(f"  ❌ 필터 차단: {bar_time} | MACD={macd:.6f} <= 0")
            continue

        # bullish_candle: 양봉 체크 (checks에서 확인)
        # 여기서는 간단히 MACD >= 0인 경우만 체크

        phase1_buys.append(eval_record)

    print(f"✅ Phase 1 필터 매수: {len(phase1_buys)}회")
    print(f"🔽 필터로 차단: {len(current_buys) - len(phase1_buys)}회 ({((len(current_buys) - len(phase1_buys)) / len(current_buys) * 100):.1f}%)")

    conn.close()

    return {
        "current_buys": len(current_buys),
        "phase1_buys": len(phase1_buys),
        "filtered_out": len(current_buys) - len(phase1_buys),
    }


if __name__ == "__main__":
    print("\n" + "="*80)
    print("🔬 Phase 1 백테스트 분석")
    print("="*80)

    # 1. 실제 매매 기록 분석
    result_actual = analyze_trades(
        start_date='2026-03-01',
        end_date='2026-03-22'
    )

    # 2. Phase 1 필터 시뮬레이션
    result_simulation = simulate_phase1_filters()

    # 3. 종합 분석
    print("\n\n" + "="*80)
    print("📊 종합 분석 결과")
    print("="*80)

    print(f"\n📈 현재 설정 (실제 데이터):")
    print(f"  매수: {result_actual['buys']}회")
    print(f"  매도: {result_actual['sells']}회")
    print(f"  Whipsaw: {result_actual['whipsaw_count']}회")
    print(f"  승률: {result_actual['win_rate']:.1f}%")
    print(f"  평균 수익: {result_actual['avg_profit']:.2f}%")
    print(f"  평균 손실: {result_actual['avg_loss']:.2f}%")
    print(f"  총 수익률: {result_actual['total_return']:.2f}%")

    print(f"\n🔬 Phase 1 필터 적용 시 (시뮬레이션):")
    print(f"  예상 매수: {result_simulation['phase1_buys']}회")
    print(f"  필터 차단: {result_simulation['filtered_out']}회")

    if result_simulation['current_buys'] > 0:
        reduction_pct = (result_simulation['filtered_out'] / result_simulation['current_buys']) * 100
        print(f"  Whipsaw 감소 예상: {reduction_pct:.1f}%")

    print("\n" + "="*80)
    print("✅ 분석 완료")
    print("="*80)

    # 결과 요약
    print(f"\n💡 핵심 인사이트:")
    print(f"  1. Whipsaw 발생: {result_actual['whipsaw_count']}회 (매수 {result_actual['buys']}회 중)")
    print(f"  2. Phase 1 필터로 {result_simulation['filtered_out']}회 매수 차단 예상")
    print(f"  3. 손실 거래: {result_actual['sells'] - int(result_actual['sells'] * result_actual['win_rate'] / 100)}회")
    print(f"  4. 평균 손실 폭: {result_actual['avg_loss']:.2f}% (Stop Loss 0.5% 적용 시 개선 가능)")
