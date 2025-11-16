from __future__ import annotations
import streamlit as st
from urllib.parse import urlencode
from datetime import datetime

from config import MIN_CASH, PARAMS_JSON_FILENAME
from engine.params import load_params, save_params
from ui.sidebar import make_sidebar
from services.db import (
    get_account,
    create_or_init_account,
    set_engine_status,
    set_thread_status,
    delete_old_logs,
)

from utils.logging_util import init_log_file


# --- 기본 설정 ---
st.set_page_config(page_title="Upbit Trade Bot v1", page_icon="🤖", layout="wide")

# --- URL 파라미터 확인 ---
params = st.query_params
user_id = params.get("user_id", "")
virtual_krw = int(params.get("virtual_krw", 0))

mode = params.get("mode", "TEST").upper()
st.session_state["mode"] = mode 

if virtual_krw < MIN_CASH:
    st.switch_page("app.py")

# --- 계정 생성 또는 조회 ---
if get_account(user_id) is None:
    create_or_init_account(user_id, virtual_krw)

# --- 세션 변수 초기화 ---
if "virtual_amount" not in st.session_state:
    st.session_state.virtual_amount = virtual_krw
if "order_ratio" not in st.session_state:
    st.session_state.order_ratio = 1
if "order_amount" not in st.session_state:
    st.session_state.order_amount = virtual_krw


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

# --- 제목 ---
st.title(f"🤖 Upbit Trade Bot v1 ({mode}) - {user_id}")

# --- 전략 파라미터 입력 폼 ---
params = make_sidebar(user_id)
start_trading = None

if params:
    try:
        json_path = f"{user_id}_{PARAMS_JSON_FILENAME}"
        exist_params = load_params(json_path)
        save_params(params, json_path)
        set_engine_status(user_id, False)
        set_thread_status(user_id, False)
        if exist_params:
            st.success("✅ 전략 파라미터 수정 저장 완료!!!")
            st.caption(
                f"🕒 수정 저장 시각: {datetime.now().isoformat(timespec='seconds')}"
            )
        else:
            st.success("✅ 전략 파라미터 최초 저장 완료!!!")
            st.caption(
                f"🕒 최초 저장 시각: {datetime.now().isoformat(timespec='seconds')}"
            )

        exist_params = load_params(json_path)
        st.write(exist_params)
        start_trading = st.button(
            f"Upbit Trade Bot v1 ({mode}) - Go Dashboard", use_container_width=True
        )
    except Exception as e:
        st.error(f"❌ 파라미터 저장 실패: {e}")
        st.stop()
else:
    json_path = f"{user_id}_{PARAMS_JSON_FILENAME}"
    exist_params = load_params(json_path)
    if exist_params:
        st.write(exist_params)

        if mode == "LIVE":
            if st.session_state.get("upbit_verified") and st.session_state.get("upbit_accounts"):
                start_trading = st.button(
                    f"Upbit Trade Bot v1 ({mode}) - Go Dashboard", use_container_width=True
                )
            else:
                go_back = st.button(
                    f"Upbit Trade Bot v1 ({mode}) - Go Back", use_container_width=True
                )
        else:
            start_trading = st.button(
                f"Upbit Trade Bot v1 ({mode}) - Go Dashboard", use_container_width=True
            )
    else:
        st.info("⚙️ 왼쪽 사이드바에서 전략 파라미터를 먼저 설정하세요.")
        st.info("🧪 파라미터 설정 완료하신 후 파라미터를 저장하세요.")


# --- 엔진 실행 및 페이지 전환 ---
if start_trading:
    init_log_file(user_id)
    delete_old_logs(user_id)

    # 🔁 페이지 이동 처리
    next_page = "dashboard"
    params = urlencode({"virtual_krw": virtual_krw, "user_id": user_id})
    st.markdown(
        f'<meta http-equiv="refresh" content="0; url=./{next_page}?{params}">',
        unsafe_allow_html=True,
    )
    st.stop()

if go_back:
    next_page = ""
    st.markdown(
        f'<meta http-equiv="refresh" content="0; url=./{next_page}">',
        unsafe_allow_html=True,
    )
    st.stop()
