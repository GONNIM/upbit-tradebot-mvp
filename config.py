# FINAL CODE
# config.py

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

# ─────────────────────────────────────────────────────
# 📊 로깅 및 알림 설정
# ─────────────────────────────────────────────────────

# 알림 웹훅 URL 설정 (선택적)
# .env 또는 secrets.toml에 ALERT_WEBHOOK_URL로 설정
try:
    ALERT_WEBHOOK_URL = st.secrets.get("ALERT_WEBHOOK_URL") or os.getenv("ALERT_WEBHOOK_URL")
except:
    ALERT_WEBHOOK_URL = None

# 로깅 레벨
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# 로그 디렉토리
LOG_DIR = "logs"

# 로그 파일 최대 크기 (10MB)
LOG_MAX_FILE_SIZE = 10 * 1024 * 1024

# 로그 백업 개수
LOG_BACKUP_COUNT = 5

# 비동기 로그 배치 크기
LOG_BATCH_SIZE = 10

# 비동기 로그 플러시 간격 (초)
LOG_FLUSH_INTERVAL = 5.0

# ─────────────────────────────────────────────────────
# 💰 기본 거래 설정
# ─────────────────────────────────────────────────────

MIN_CASH = 10_000
MIN_FEE_RATIO = 0.0005

PARAMS_JSON_FILENAME = "latest_params.json"
CONDITIONS_JSON_FILENAME = "buy_sell_conditions.json"
DEFAULT_USER_ID = "gon1972"

# 리프레시 간격 (초)
REFRESH_INTERVAL = 5

# ─────────────────────────────────────────────────────
# 🎯 전략 설정
# ─────────────────────────────────────────────────────

MIN_HOLDING_PERIOD = 5
VOLATILITY_WINDOW = 20
TRAILING_STOP_PERCENT = 0.1

MACD_EXIT_ENABLED = True  # TP/SL 도달 전 매도 될 가능성
SIGNAL_CONFIRM_ENABLED = False  # (Golden Cross) + (MACD >= 기준값) + (Signal >= 기준값)

MACD_POSITIVE_ENABLED = False
SIGNAL_POSITIVE_ENABLED = False
BULLISH_CANDLE_ENABLED = False
MACD_TRENDING_UP_ENABLED = False
ABOVE_MA_20_ENABLED = False
ABOVE_MA_60_ENABLED = False

# ─────────────────────────────────────────────────────
# 📈 시장 데이터 설정
# ─────────────────────────────────────────────────────

# 지원되는 차트 간격
SUPPORTED_INTERVALS = {
    "1분": "minute1",
    "3분": "minute3",
    "5분": "minute5",
    "10분": "minute10",
    "15분": "minute15",
    "30분": "minute30",
    "1시간": "minute60",
    "4시간": "minute240",
    "일봉": "day"
}

# 기본 차트 간격
DEFAULT_INTERVAL = "minute5"

# ─────────────────────────────────────────────────────
# 🔒 리스크 관리 설정
# ─────────────────────────────────────────────────────

# 기본 리스크 설정
DEFAULT_MAX_POSITION_SIZE = 1.0  # 100%
DEFAULT_MAX_DRAWDOWN = 0.2  # 20%
DEFAULT_STOP_LOSS = 0.05  # 5%
DEFAULT_TAKE_PROFIT = 0.1  # 10%
DEFAULT_RISK_PER_TRADE = 0.02  # 2%

# ─────────────────────────────────────────────────────
# 🚦 실행 설정
# ─────────────────────────────────────────────────────

# 기본 실행 설정
DEFAULT_MAX_SLIPPAGE = 0.001  # 0.1%
DEFAULT_EXECUTION_DELAY = 0.5  # 0.5초
DEFAULT_RETRY_ATTEMPTS = 3
DEFAULT_RETRY_DELAY = 1.0  # 1초

# ─────────────────────────────────────────────────────
# 📊 모니터링 설정
# ─────────────────────────────────────────────────────

# 기본 모니터링 설정
DEFAULT_HEALTH_CHECK_INTERVAL = 30  # 30초
DEFAULT_ENABLE_HEALTH_CHECK = True
DEFAULT_ENABLE_PERFORMANCE_TRACKING = True

# ─────────────────────────────────────────────────────
# 📈 레이트 리밋 설정
# ─────────────────────────────────────────────────────

# 기본 레이트 리밋 설정
DEFAULT_MAX_REQUESTS_PER_MINUTE = 60
DEFAULT_MAX_ORDERS_PER_MINUTE = 10
DEFAULT_MAX_TRADES_PER_DAY = 50
DEFAULT_COOLDOWN_PERIOD = 5  # 5초

# ─────────────────────────────────────────────────────
# 🏥 헬스 모니터링 설정
# ─────────────────────────────────────────────────────

# 헬스 체크 설정
HEALTH_CHECK_INTERVAL = 30  # 30초
MEMORY_WARNING_THRESHOLD = 500  # 500MB
CPU_WARNING_THRESHOLD = 80  # 80%

# ─────────────────────────────────────────────────────
# 🗄️ 데이터베이스 설정
# ─────────────────────────────────────────────────────

DB_PATH = "tradebot.db"

# 로그 정리 설정
LOG_CLEANUP_DAYS = 30  # 30일 이전 로그 정리

# ─────────────────────────────────────────────────────
# 🌐 API 설정
# ─────────────────────────────────────────────────────

# API 타임아웃 설정
API_TIMEOUT = 10  # 10초

# API 재시도 설정
API_MAX_RETRIES = 3
API_RETRY_DELAY = 1  # 1초

# ─────────────────────────────────────────────────────
# 🔧 디버그 설정
# ─────────────────────────────────────────────────────

# 디버그 모드
DEBUG_MODE = os.getenv("DEBUG_MODE", "False").lower() == "true"

# 테스트 모드
TEST_MODE = os.getenv("TEST_MODE", "True").lower() == "true"

# ─────────────────────────────────────────────────────
# 📱 UI 설정
# ─────────────────────────────────────────────────────

# UI 테마
UI_THEME = os.getenv("UI_THEME", "auto")  # auto, light, dark

# UI 언어
UI_LANGUAGE = os.getenv("UI_LANGUAGE", "ko")  # ko, en

# ─────────────────────────────────────────────────────
# 🚨 알림 설정
# ─────────────────────────────────────────────────────

# 알림 유형
NOTIFICATION_TYPES = [
    "TRADE_EXECUTED",    # 거래 실행
    "ORDER_FAILED",      # 주문 실패
    "LIQUIDATION",       # 청산
    "SYSTEM_ERROR",      # 시스템 오류
    "CRITICAL_ALERT",    # 크리티컬 알림
    "HEALTH_WARNING",    # 건강 경고
    "STRATEGY_SIGNAL"    # 전략 시그널
]

# 알림 심각도 레벨
ALERT_SEVERITY_LEVELS = [
    "LOW",      # 낮음
    "MEDIUM",   # 중간
    "HIGH",     # 높음
    "CRITICAL"  # 치명적
]

# 크리티컬 알림 키워드
CRITICAL_ALERT_KEYWORDS = [
    "CRITICAL",
    "청산",
    "liquidation",
    "주문 실패",
    "order failed",
    "시스템 오류",
    "system error",
    "force liquidate",
    "강제 청산"
]

# ─────────────────────────────────────────────────────
# 📊 성능 모니터링 설정
# ─────────────────────────────────────────────────────

# 성능 메트릭 수집 간격
PERFORMANCE_METRICS_INTERVAL = 60  # 60초

# 성능 경고 임계값
PERFORMANCE_WARNING_THRESHOLDS = {
    "cpu_usage": 80,          # CPU 사용량 80%
    "memory_usage": 80,       # 메모리 사용량 80%
    "disk_usage": 90,         # 디스크 사용량 90%
    "response_time": 5.0,     # 응답 시간 5초
    "error_rate": 0.05        # 에러율 5%
}

# ─────────────────────────────────────────────────────
# 🔐 보안 설정
# ─────────────────────────────────────────────────────

# 세션 타임아웃 (분)
SESSION_TIMEOUT = 30

# 최대 로그인 시도 횟수
MAX_LOGIN_ATTEMPTS = 5

# 계정 잠금 시간 (분)
ACCOUNT_LOCKOUT_DURATION = 15
