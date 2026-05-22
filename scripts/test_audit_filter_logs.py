"""
테스트용 감사 로그 생성 스크립트

목적: 필터 정보가 포함된 BUY/SELL 평가 로그를 DB에 생성하여
      audit_viewer.py에서 필터 컬럼이 올바르게 표시되는지 확인
"""
import sys
from pathlib import Path

# 프로젝트 루트 경로 추가
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from services.db import insert_buy_eval, insert_sell_eval
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import json

# 테스트 대상 사용자
USER_ID = "mcmax33"
TICKER = "KRW-ZRO"
INTERVAL_SEC = 60  # 1분봉

def generate_test_buy_logs():
    """BUY 평가 로그 생성 (필터 정보 포함)"""
    print("\n=== BUY 평가 로그 생성 ===")

    base_time = datetime.now(tz=ZoneInfo("Asia/Seoul"))

    # 케이스 1: SlowEmaSurgeFilter 차단 (급등 감지)
    print("1. SlowEmaSurgeFilter 차단 케이스")
    checks_1 = {
        "reason": "NO_BUY_SIGNAL",
        "ema_fast": 1950.5,
        "ema_slow": 1920.0,
        "price": 1950.0,
        "strategy_mode": "EMA",
        "cross_status": "Golden",
        # ✅ 필터 정보 추가
        "filter_blocked": True,
        "filter_reason": "SURGE_FILTER",
        "filter_details": "Price surge detected: 1.56% above Slow EMA (threshold: 1.2%)",
        "filter_metadata": {
            "surge_pct": 0.0156,      # 1.56%
            "threshold_pct": 0.012,   # 1.2%
            "price": 1950.0,
            "ema_slow": 1920.0
        }
    }

    insert_buy_eval(
        user_id=USER_ID,
        ticker=TICKER,
        interval_sec=INTERVAL_SEC,
        bar=1001,
        price=1950.0,
        macd=1950.5,
        signal=1920.0,
        have_position=False,
        overall_ok=False,
        failed_keys=["SURGE_FILTER"],  # ✅ 필터로 차단
        checks=checks_1,
        notes="Surge Filter 차단 - 1.56% 급등",
        bar_time=(base_time - timedelta(minutes=10)).isoformat()
    )
    print(f"   ✅ Surge 차단: 1.56% (임계값 1.2%)")

    # 케이스 2: SlowEmaSurgeFilter 통과 (정상)
    print("2. SlowEmaSurgeFilter 통과 케이스")
    checks_2 = {
        "reason": "NO_BUY_SIGNAL",
        "ema_fast": 1925.0,
        "ema_slow": 1920.0,
        "price": 1925.0,
        "strategy_mode": "EMA",
        "cross_status": "Golden",
        # ✅ 필터 정보 추가
        "filter_blocked": False,
        "filter_reason": "SURGE_OK",
        "filter_details": "Surge check passed: 0.26%",
        "filter_metadata": {
            "surge_pct": 0.0026,      # 0.26%
            "threshold_pct": 0.012,   # 1.2%
            "price": 1925.0,
            "ema_slow": 1920.0
        }
    }

    insert_buy_eval(
        user_id=USER_ID,
        ticker=TICKER,
        interval_sec=INTERVAL_SEC,
        bar=1002,
        price=1925.0,
        macd=1925.0,
        signal=1920.0,
        have_position=False,
        overall_ok=False,
        failed_keys=["NO_SIGNAL"],
        checks=checks_2,
        notes="Surge Filter 통과 - 0.26%",
        bar_time=(base_time - timedelta(minutes=9)).isoformat()
    )
    print(f"   ✅ Surge 통과: 0.26% (임계값 1.2%)")

    # 케이스 3: BUY 신호 발생 (필터 통과)
    print("3. BUY 신호 발생 케이스")
    checks_3 = {
        "reason": "BUY_SIGNAL",
        "ema_fast": 1930.0,
        "ema_slow": 1920.0,
        "price": 1930.0,
        "strategy_mode": "EMA",
        "cross_status": "Golden",
        # ✅ 필터 정보 추가
        "filter_blocked": False,
        "filter_reason": "SURGE_OK",
        "filter_details": "Surge check passed: 0.52%",
        "filter_metadata": {
            "surge_pct": 0.0052,      # 0.52%
            "threshold_pct": 0.012,   # 1.2%
            "price": 1930.0,
            "ema_slow": 1920.0
        }
    }

    insert_buy_eval(
        user_id=USER_ID,
        ticker=TICKER,
        interval_sec=INTERVAL_SEC,
        bar=1003,
        price=1930.0,
        macd=1930.0,
        signal=1920.0,
        have_position=False,
        overall_ok=True,
        failed_keys=[],
        checks=checks_3,
        notes="🟢 BUY | Golden | bar=1003",
        bar_time=(base_time - timedelta(minutes=8)).isoformat()
    )
    print(f"   ✅ BUY 신호 - 필터 통과")

    # 케이스 4: 극단적 급등 차단
    print("4. 극단적 급등 차단 케이스")
    checks_4 = {
        "reason": "NO_BUY_SIGNAL",
        "ema_fast": 1980.0,
        "ema_slow": 1920.0,
        "price": 1980.0,
        "strategy_mode": "EMA",
        "cross_status": "Golden",
        # ✅ 필터 정보 추가
        "filter_blocked": True,
        "filter_reason": "SURGE_FILTER",
        "filter_details": "Price surge detected: 3.13% above Slow EMA (threshold: 1.2%)",
        "filter_metadata": {
            "surge_pct": 0.0313,      # 3.13%
            "threshold_pct": 0.012,   # 1.2%
            "price": 1980.0,
            "ema_slow": 1920.0
        }
    }

    insert_buy_eval(
        user_id=USER_ID,
        ticker=TICKER,
        interval_sec=INTERVAL_SEC,
        bar=1004,
        price=1980.0,
        macd=1980.0,
        signal=1920.0,
        have_position=False,
        overall_ok=False,
        failed_keys=["SURGE_FILTER"],
        checks=checks_4,
        notes="Surge Filter 차단 - 3.13% 극단적 급등",
        bar_time=(base_time - timedelta(minutes=7)).isoformat()
    )
    print(f"   ✅ 극단적 급등 차단: 3.13% (임계값 1.2%)")

def generate_test_sell_logs():
    """SELL 평가 로그 생성 (필터 정보 포함)"""
    print("\n=== SELL 평가 로그 생성 ===")

    base_time = datetime.now(tz=ZoneInfo("Asia/Seoul"))

    # 케이스 1: TRAILING_STOP 트리거
    print("1. TrailingStop 트리거 케이스")
    checks_1 = {
        "reason": "SELL_SIGNAL",
        "entry_price": 1930.0,
        "pnl_pct": 0.015,  # 1.5% 수익
        "cross_status": "Golden",
        "tp_hit": 0,
        "sl_hit": 0,
        "bars_held": 15,
        "trigger_reason": "TRAILING_STOP",
        "ema_dc_detected": 0,
        # ✅ 필터 정보 추가
        "filter_evaluated": True,
        "filter_triggered": True,
        "filter_reason": "TRAILING_STOP",
        "filter_details": "Profit drop detected: 2.27% from peak (threshold: 10.0%)",
        "filter_metadata": {
            "profit_drop_pct": 0.0227,
            "current_price": 1960.0,
            "highest_price": 2005.0,
            "threshold_pct": 0.10
        }
    }

    insert_sell_eval(
        user_id=USER_ID,
        ticker=TICKER,
        interval_sec=INTERVAL_SEC,
        bar=1016,
        price=1960.0,
        macd=1960.0,
        signal=1950.0,
        tp_price=1989.0,
        sl_price=1910.0,
        highest=2005.0,
        ts_pct=0.10,
        ts_armed=True,
        bars_held=15,
        checks=checks_1,
        triggered=True,
        trigger_key="TRAILING_STOP",
        notes="🔴 SELL | TRAILING_STOP | Golden | PNL=1.50% | bar=1016",
        bar_time=(base_time - timedelta(minutes=5)).isoformat()
    )
    print(f"   ✅ TrailingStop 트리거: 2.27% 하락 (임계값 10%)")

    # 케이스 2: TAKE_PROFIT 트리거
    print("2. TakeProfit 트리거 케이스")
    checks_2 = {
        "reason": "SELL_SIGNAL",
        "entry_price": 1930.0,
        "pnl_pct": 0.035,  # 3.5% 수익
        "cross_status": "Golden",
        "tp_hit": 1,
        "sl_hit": 0,
        "bars_held": 20,
        "trigger_reason": "TAKE_PROFIT",
        "ema_dc_detected": 0,
        # ✅ 필터 정보 추가
        "filter_evaluated": True,
        "filter_triggered": True,
        "filter_reason": "TAKE_PROFIT",
        "filter_details": "Take profit triggered: 3.5% >= 3.0%",
        "filter_metadata": {
            "current_pnl_pct": 0.035,
            "take_profit_pct": 0.03,
            "entry_price": 1930.0,
            "current_price": 1997.5
        }
    }

    insert_sell_eval(
        user_id=USER_ID,
        ticker=TICKER,
        interval_sec=INTERVAL_SEC,
        bar=1021,
        price=1997.5,
        macd=1997.5,
        signal=1990.0,
        tp_price=1989.0,
        sl_price=1910.0,
        highest=2000.0,
        ts_pct=0.10,
        ts_armed=False,
        bars_held=20,
        checks=checks_2,
        triggered=True,
        trigger_key="TAKE_PROFIT",
        notes="🔴 SELL | TAKE_PROFIT | Golden | PNL=3.50% | bar=1021",
        bar_time=(base_time - timedelta(minutes=4)).isoformat()
    )
    print(f"   ✅ TakeProfit 트리거: 3.5% 수익 (목표 3.0%)")

    # 케이스 3: HOLD 케이스 (매도 신호 없음)
    print("3. HOLD 케이스 (매도 신호 없음)")
    checks_3 = {
        "entry_price": 1930.0,
        "pnl_pct": 0.015,  # 1.5% 수익
        "cross_status": "Golden",
        "tp_hit": 0,
        "sl_hit": 0,
        "bars_held": 10,
        "ema_dc_detected": 0,
        # ✅ 필터 정보 추가
        "filter_evaluated": True,
        "filter_reason": "NO_TRIGGER",
        "filter_details": "All filters checked, no sell signal"
    }

    insert_sell_eval(
        user_id=USER_ID,
        ticker=TICKER,
        interval_sec=INTERVAL_SEC,
        bar=1011,
        price=1958.95,
        macd=1958.95,
        signal=1950.0,
        tp_price=1989.0,
        sl_price=1910.0,
        highest=1960.0,
        ts_pct=0.10,
        ts_armed=False,
        bars_held=10,
        checks=checks_3,
        triggered=False,
        trigger_key=None,
        notes="Golden | PNL=1.50% | bar=1011",
        bar_time=(base_time - timedelta(minutes=3)).isoformat()
    )
    print(f"   ✅ HOLD - 매도 신호 없음")

    # 케이스 4: STOP_LOSS 트리거
    print("4. StopLoss 트리거 케이스")
    checks_4 = {
        "reason": "SELL_SIGNAL",
        "entry_price": 1930.0,
        "pnl_pct": -0.015,  # -1.5% 손실
        "cross_status": "Dead",
        "tp_hit": 0,
        "sl_hit": 1,
        "bars_held": 8,
        "trigger_reason": "STOP_LOSS",
        "ema_dc_detected": 1,
        # ✅ 필터 정보 추가
        "filter_evaluated": True,
        "filter_triggered": True,
        "filter_reason": "STOP_LOSS",
        "filter_details": "Stop loss triggered: -1.5% <= -1.0%",
        "filter_metadata": {
            "current_pnl_pct": -0.015,
            "stop_loss_pct": 0.01,
            "entry_price": 1930.0,
            "current_price": 1901.05
        }
    }

    insert_sell_eval(
        user_id=USER_ID,
        ticker=TICKER,
        interval_sec=INTERVAL_SEC,
        bar=1009,
        price=1901.05,
        macd=1901.05,
        signal=1910.0,
        tp_price=1989.0,
        sl_price=1910.7,
        highest=1935.0,
        ts_pct=0.10,
        ts_armed=False,
        bars_held=8,
        checks=checks_4,
        triggered=True,
        trigger_key="STOP_LOSS",
        notes="🔴 SELL | STOP_LOSS | Dead | PNL=-1.50% | bar=1009",
        bar_time=(base_time - timedelta(minutes=2)).isoformat()
    )
    print(f"   ✅ StopLoss 트리거: -1.5% 손실 (임계값 -1.0%)")

def main():
    """메인 실행 함수"""
    print("=" * 60)
    print("테스트용 감사 로그 생성 시작")
    print("=" * 60)
    print(f"User ID: {USER_ID}")
    print(f"Ticker: {TICKER}")
    print(f"Interval: {INTERVAL_SEC}초 (1분봉)")

    try:
        # BUY 평가 로그 생성
        generate_test_buy_logs()

        # SELL 평가 로그 생성
        generate_test_sell_logs()

        print("\n" + "=" * 60)
        print("✅ 테스트 로그 생성 완료!")
        print("=" * 60)
        print("\n다음 명령어로 확인:")
        print(f"  streamlit run app.py")
        print(f"\n감사 로그 뷰어 URL:")
        print(f"  http://localhost:8501/audit_viewer?user_id={USER_ID}&ticker=ZRO&rows=2000&tab=buy&mode=TEST&strategy=EMA")
        print("\n확인 사항:")
        print("  1. BUY 평가 탭 - surge_actual, surge_threshold, surge_diff 컬럼 표시 확인")
        print("  2. SELL 평가 탭 - filter_reason, filter_details, filter_triggered 컬럼 표시 확인")
        print("  3. 필터 차단 케이스 - failed_keys = ['SURGE_FILTER'] 확인")

    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0

if __name__ == "__main__":
    exit(main())
