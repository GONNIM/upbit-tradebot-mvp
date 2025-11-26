import time
from urllib.parse import urlencode
import streamlit as st
from engine.engine_runner import is_engine_running
from services.db import insert_log
from services.init_db import reset_db
from engine.engine_manager import engine_manager

from config import MIN_CASH

from ui.style import style_main

# --- 기본 설정 ---
st.set_page_config(page_title="Upbit Trade Bot v1", page_icon="🤖", layout="wide")
st.markdown(style_main, unsafe_allow_html=True)

# ✅ 쿼리 파라미터 처리
qp = st.query_params

def _get_param(qp, key, default=None):
    v = qp.get(key, default)
    if isinstance(v, list):
        return v[0]
    return v

user_id = _get_param(qp, "user_id", st.session_state.get("user_id", ""))
raw_v = _get_param(qp, "virtual_krw", st.session_state.get("virtual_krw", 0))

try:
    virtual_krw = int(raw_v)
except (TypeError, ValueError):
    virtual_krw = int(st.session_state.get("virtual_krw", 0) or 0)

raw_mode = _get_param(qp, "mode", st.session_state.get("mode", "TEST"))
mode = str(raw_mode).upper()
st.session_state["mode"] = mode


if virtual_krw < MIN_CASH:
    st.switch_page("app.py")


# 시스템 초기화 함수
def initialize_confirm():
    if engine_manager.is_running(user_id):
        engine_manager.stop_engine(user_id)
        insert_log(user_id, "INFO", "🛑 시스템 초기화로 엔진 종료됨")
    else:
        insert_log(user_id, "INFO", "ℹ️ 엔진이 실행 중이 아님")

    time.sleep(1)  # 종료 대기
    reset_db(user_id)

    # st.session_state.engine_started = False  # ✅ 캐시 초기화
    st.session_state.pop("engine_started", None)
    st.success("DB 초기화 완료")

    # 페이지 리프레시
    params = urlencode({"virtual_krw": virtual_krw, "user_id": user_id})
    st.markdown(
        f'<meta http-equiv="refresh" content="0; url=./set_config?{params}">',
        unsafe_allow_html=True,
    )


def initialize_cancel():
    next_page = "dashboard"
    params = urlencode({
        "user_id": user_id,
        "virtual_krw": virtual_krw,
        "mode": mode,
    })
    st.markdown(
        f'<meta http-equiv="refresh" content="0; url=./dashboard?{params}">',
        unsafe_allow_html=True,
    )
    st.switch_page(next_page)


# --- UI 스타일 ---
st.markdown(
    """
    <style>
    /* 헤더와 본문 사이 간격 제거 */
    div.block-container {
        padding-top: 1rem;  /* 기본값은 3rem */
    }

    /* 제목 상단 마진 제거 */
    h1 {
        margin-top: 0 !important;
    }

    [data-testid="stSidebarHeader"],
    [data-testid="stSidebarNavItems"],
    [data-testid="stSidebarNavSeparator"] { display: none !important; }
    div.stButton > button, div.stForm > form > button {
        height: 60px !important;
        font-size: 30px !important;
        font-weight: 900 !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


if "init_busy" not in st.session_state:
    st.session_state.init_busy = False

btn_col1, btn_col2 = st.columns([1, 1])
with btn_col1:
    if st.button("💥 초기화 취소", use_container_width=True):
        initialize_cancel()

with btn_col2:
    if st.button("💥 초기화 진행", use_container_width=True):
        st.session_state.init_busy = True
        initialize_confirm()
