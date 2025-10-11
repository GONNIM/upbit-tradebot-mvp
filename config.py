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
DEFAULT_USER_ID = "gon1972"

# 리프레시 간격 (초)
REFRESH_INTERVAL = 5

# Strategy
MIN_HOLDING_PERIOD = 5
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
