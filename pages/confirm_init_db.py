import time
from urllib.parse import urlencode
import streamlit as st
from engine.engine_runner import is_engine_running
from services.db import insert_log
from services.init_db import reset_db
from engine.engine_manager import engine_manager

from config import MIN_CASH

from ui.style import style_main
from services.page_context import bootstrap_page_context, navigate_to  # ✅ SP-NAV-5

# --- 기본 설정 ---
st.set_page_config(page_title="Upbit Trade Bot v1", page_icon="🤖", layout="wide")
st.markdown(style_main, unsafe_allow_html=True)

# ✅ SP-NAV-5: 페이지 진입 컨텍스트 표준 로드 (세션 유실 시 자동 로그인 리다이렉트)
bootstrap_page_context(required=("user_id",))

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


# ✅ MIN_CASH 검사는 TEST 모드에만 적용 (LIVE는 매수 후 KRW=0 정상 상황 존재).
if mode == "TEST" and virtual_krw < MIN_CASH:
    st.switch_page("app.py")


# 시스템 초기화 함수
def initialize_confirm():
    if engine_manager.is_running(user_id):
        engine_manager.stop_engine(user_id)
        insert_log(user_id, "INFO", "🛑 시스템 초기화로 엔진 종료됨")
        # Critical 신규: 시스템 초기화로 인한 엔진 종료 알림 (v2 — 친화 표현)
        try:
            from services.notifier import send as _notify, LEVEL_CRITICAL
            _notify(
                LEVEL_CRITICAL,
                f"💥 엔진 강제 종료 — {user_id}",
                (
                    "사유: 시스템 초기화 실행\n\n"
                    "⚠️ DB 및 포지션 데이터 초기화됨"
                ),
                dedupe_key=f"engine_reset:{user_id}",
                dedupe_ttl=30,
            )
        except Exception:
            pass

        # ✅ 엔진이 실제로 종료될 때까지 폴링 (최대 5초)
        max_wait = 5.0
        waited = 0.0
        while engine_manager.is_running(user_id) and waited < max_wait:
            time.sleep(0.1)  # 100ms마다 체크
            waited += 0.1

        if waited >= max_wait:
            insert_log(user_id, "WARNING", f"⚠️ 엔진 종료 타임아웃 ({max_wait}초)")
        else:
            insert_log(user_id, "INFO", f"✅ 엔진 종료 완료 ({waited:.1f}초)")
    else:
        insert_log(user_id, "INFO", "ℹ️ 엔진이 실행 중이 아님")

    reset_db(user_id)

    # st.session_state.engine_started = False  # ✅ 캐시 초기화
    st.session_state.pop("engine_started", None)
    st.success("DB 초기화 완료")

    # ✅ SP-NAV-5: navigate_to 표준화
    navigate_to(
        "pages/set_config.py",
        virtual_krw=virtual_krw,
        user_id=user_id,
    )


def initialize_cancel():
    # ✅ SP-NAV-5: navigate_to 표준화
    navigate_to(
        "pages/dashboard.py",
        user_id=user_id,
        virtual_krw=virtual_krw,
        mode=mode,
    )


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
