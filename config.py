import streamlit as st
import os


DB_PATH = "tradebot.db"


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
DEFAULT_USER_ID = "gon1972"

# 리프레시 간격 (초)
REFRESH_INTERVAL = 5
