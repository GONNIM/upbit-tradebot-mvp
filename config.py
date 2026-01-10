import streamlit as st
import os


DB_PREFIX = "tradebot"


# Streamlit Cloud에서 secrets.toml 값 읽기
try:
    ACCESS = st.secrets["UPBIT_ACCESS"]
    SECRET = st.secrets["UPBIT_SECRET"]
except KeyError:
    # 로컬 개발 환경용 대체 코드
    from dotenv import load_dotenv

    load_dotenv()
    ACCESS = os.getenv("UPBIT_ACCESS")
    SECRET = os.getenv("UPBIT_SECRET")

if not (ACCESS and SECRET):
    raise EnvironmentError("UPBIT_ACCESS / UPBIT_SECRET 값이 설정되지 않았습니다")

MIN_CASH = 10_000
MIN_FEE_RATIO = 0.0005

PARAMS_JSON_FILENAME = "latest_params.json"
CONDITIONS_JSON_FILENAME = "buy_sell_conditions.json"
DEFAULT_USER_ID = "mcmax33"

# 리프레시 간격 (초)
REFRESH_INTERVAL = 5

# ============================================================
# 🧠 Strategy 공통 설정
#  - 여기서부터는 "어떤 전략을 쓸지"에 대한 전역 상수만 정의
# ============================================================
# ✅ 현재 지원하는 전략 목록
STRATEGY_TYPES = ["MACD", "EMA"]
# ✅ 기본 전략 타입 (로그인/최초 진입 시 기본값)
DEFAULT_STRATEGY_TYPE = "MACD"

# Strategy
MIN_HOLDING_PERIOD = 1
VOLATILITY_WINDOW = 20
TRAILING_STOP_PERCENT = 0.1

MACD_EXIT_ENABLED = True  # TP/SL 도달 전 매도 될 가능성
SIGNAL_CONFIRM_ENABLED = False  # (Golden Cross) + (MACD >= 기준값) + (Signal >= 기준값)

TP_WITH_TS = False

MACD_POSITIVE_ENABLED = False
SIGNAL_POSITIVE_ENABLED = False
BULLISH_CANDLE_ENABLED = False
MACD_TRENDING_UP_ENABLED = False
ABOVE_MA_20_ENABLED = False
ABOVE_MA_60_ENABLED = False

AUDIT_LOG_SKIP_POS = False        # ← 기본 False: BUY_SKIP_POS는 DB에 남기지 않음
AUDIT_SKIP_POS_SAMPLE_N = 0       # 0이면 샘플링 안함(=완전 비활성), n>0이면 n bar마다 1회
AUDIT_DEDUP_PER_BAR = True        # 같은 bar 중복 적재 방지

# 감사 로그 튜닝 파라미터
AUDIT_BUY_SAMPLE_N = 1          # 동일 상태가 지속되어도 N bar마다 1회 기록
AUDIT_BUY_COOLDOWN_BARS = 15     # 동일 상태에서 최소 대기 bar 수
AUDIT_SELL_SAMPLE_N = 60         # (SELL 평가 샘플링 간격; 필요 시)
AUDIT_SELL_COOLDOWN_BARS = 10    # SELL 평가 쿨다운

# 엔진 실행 모드: 
# - "BACKTEST" : 지금처럼 _run_backtest_once만 사용
# - "REPLAY"   : run_replay_on_dataframe(...) 기반으로 동작
ENGINE_EXEC_MODE = "BACKTEST"  # 또는 "BACKTEST"