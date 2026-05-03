from __future__ import annotations
import streamlit as st
from urllib.parse import urlencode
from datetime import datetime

from config import (
    MIN_CASH,
    PARAMS_JSON_FILENAME,
    STRATEGY_TYPES,         # ✅ 전략 선택용 (예: ["MACD", "EMA"])
    DEFAULT_STRATEGY_TYPE,  # ✅ 기본 전략 타입
)
from engine.params import load_params, save_params, save_active_strategy
from pages.audit_viewer import query
from ui.sidebar import make_sidebar
from services.db import (
    get_account,
    create_or_init_account,
    update_account,
    set_engine_status,
    set_thread_status,
    delete_old_logs,
    get_db,
)

from utils.logging_util import init_log_file


# --- 기본 설정 ---
st.set_page_config(page_title="Upbit Trade Bot v1", page_icon="🤖", layout="wide")

st.markdown(
    """
    <style>
    div.block-container { padding-top: 1rem; }
    h1 { margin-top: 0 !important; }
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

# --- URL 파라미터 확인 ---
qp = st.query_params


def _get_param(qp, key, default=None):
    v = qp.get(key, default)
    if isinstance(v, list):
        return v[0]
    return v


def _get_bool_param(qp, key, default: bool = False) -> bool:
    """
    ⚠️ 기존 버그 포인트:
        - URL에서 verified=True 로 들어오는데
        - 코드에서는 str(value) == "1" 만 True 로 인식했음.
        - 그래서 "True" / "true" / "1" 다 호환되게 파싱 필요.

    이 함수는 다음을 모두 True 로 취급:
        "1", "true", "t", "yes", "y", True (bool)
    나머지는 False.
    """
    v = _get_param(qp, key, None)
    if v is None:
        return default
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    return s in ("1", "true", "t", "yes", "y")


user_id = _get_param(qp, "user_id", st.session_state.get("user_id", ""))
raw_v = _get_param(qp, "virtual_krw", st.session_state.get("virtual_krw", 0))

try:
    virtual_krw = int(raw_v)
except (TypeError, ValueError):
    virtual_krw = int(st.session_state.get("virtual_krw", 0) or 0)

raw_mode = _get_param(qp, "mode", st.session_state.get("mode", "TEST"))
mode = str(raw_mode).upper()
st.session_state["mode"] = mode

verified_param = _get_bool_param(qp, "verified", default=False)
capital_param = _get_bool_param(qp, "capital_set", default=False)

upbit_ok = bool(verified_param)
capital_ok = bool(capital_param)

if "upbit_verified" in st.session_state:
    upbit_ok = upbit_ok or bool(st.session_state.get("upbit_verified"))
if "live_capital_set" in st.session_state:
    capital_ok = capital_ok or bool(st.session_state.get("live_capital_set"))

if virtual_krw < MIN_CASH:
    st.warning(
        f"현재 운용자산({virtual_krw} KRW)가 최소 주문 가능 금액({MIN_CASH} KRW)보다 작습니다.\n"
        "처음 화면(app.py)에서 운용자산을 다시 설정해 주세요."
    )
    if st.button("처음 화면으로 돌아가기"):
        st.switch_page("app.py")
    st.stop()

# ✅ WO-2026-002: LIVE 모드 진입 조건 완화 (경고만 표시, 진입 허용)
if mode == "LIVE":
    if not upbit_ok or not capital_ok:
        st.warning(
            "⚠️ LIVE 모드 진입 조건이 충족되지 않았습니다.\n\n"
            f"- upbit_verified: {upbit_ok}\n"
            f"- live_capital_set: {capital_ok}\n\n"
            "파라미터 설정은 가능하지만, 실제 LIVE 운용을 위해서는\n"
            "app.py에서 계좌검증을 먼저 완료해 주세요.",
            icon="⚠️"
        )
        # ✅ st.stop() 제거 → 진행 허용

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

# ============================================================
# 🧠 전략 타입 선택 (MACD / EMA)
#   - strategy_type 를 공통 파라미터로 승격
#   - 기존 latest_params.json 에 값이 있으면 그걸 기본값으로 사용
#   - 여기서 선택한 값은 최종 LiveParams.strategy_type 에 강제로 주입
# ============================================================
json_path = f"{user_id}_{PARAMS_JSON_FILENAME}"

# ✅ URL에서 전달받은 strategy_type을 우선 사용 (대시보드/감사로그에서 돌아올 때)
strategy_from_url = _get_param(qp, "strategy_type", None)
strategy_from_session = st.session_state.get("strategy_type", None)
initial_strategy = (strategy_from_url or strategy_from_session or DEFAULT_STRATEGY_TYPE)
initial_strategy = str(initial_strategy).upper().strip()

# ✅ 전략 선택 UI를 만들기 위한 기본값은
#    "전략별" params 파일에서 불러와야 한다.
#    그래야 MACD/EMA 각각 마지막 저장값이 복원된다.
exist_for_strategy = load_params(json_path, strategy_type=initial_strategy)

if exist_for_strategy:
    default_strategy = exist_for_strategy.strategy_type
else:
    default_strategy = initial_strategy

# STRATEGY_TYPES 는 ["MACD", "EMA"] 같은 형태라고 가정
# 대소문자 섞여 있어도 index 계산이 되도록 안전하게 처리
try:
    default_idx = [s.upper() for s in STRATEGY_TYPES].index(default_strategy.upper())
except ValueError:
    default_idx = 0

selected_strategy_type = st.sidebar.selectbox(
    "전략 타입 (Strategy Type)",
    STRATEGY_TYPES,
    index=default_idx,
    key="strategy_type_selector",  # key 변경 (세션 충돌 방지)
    help="MACD: 모멘텀 기반 / EMA: 추세 추종 실험 전략",
)
st.sidebar.caption(f"현재 선택된 전략: **{selected_strategy_type}**")

# ✅ 세션에 저장하여 다른 페이지에서도 사용 가능하도록
st.session_state["strategy_type"] = selected_strategy_type

# ✅ 선택된 전략의 파라미터를 전략별 파일에서 로드
#    - MACD/EMA 각각 다른 fast/slow 값을 유지하려면 반드시 필요
selected_params = load_params(json_path, strategy_type=selected_strategy_type)


# --- 전략 파라미터 입력 폼 ---
#  make_sidebar() 는 기존대로 ticker, 기간, MACD 파라미터 등만 그리고,
#  여기서 선택한 전략 타입은 아래에서 params.strategy_type 에 주입한다.
params = make_sidebar(user_id, selected_strategy_type)
start_trading = None
go_back = False

if params:
    try:
        # ✅ 여기서 최종적으로 전략 타입을 덮어쓴다.
        #   - make_sidebar 가 strategy_type 을 아직 모른다 해도 문제 없음
        #   - LiveParams.validator 가 알아서 MACD/EMA 이외 값은 막아준다.
        params.strategy_type = selected_strategy_type

        # ✅ 전략별 파일에서 로드/저장되도록 strategy_type을 같이 넘긴다.
        #    -> MACD 저장값과 EMA 저장값이 서로 덮어쓰지 않음
        exist_params = load_params(json_path, strategy_type=selected_strategy_type)
        save_params(params, json_path, strategy_type=selected_strategy_type)

        # ✅ TEST 모드일 때: 파라미터 저장 시 DB 잔고 및 포지션을 초기화
        if mode == "TEST":
            try:
                # 1. KRW 잔고를 초기자본으로 리셋
                update_account(user_id, params.cash)

                # 2. 모든 코인 포지션 삭제
                with get_db(user_id) as conn:
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM account_positions WHERE user_id = ?", (user_id,))
                    conn.commit()
                    deleted_positions = cursor.rowcount

                st.info(
                    f"💰 TEST 모드 초기화 완료:\n"
                    f"- KRW 잔고: {params.cash:,}원\n"
                    f"- 코인 포지션: {deleted_positions}개 삭제"
                )
            except Exception as e:
                st.warning(f"⚠️ DB 초기화 실패 (무시됨): {e}")

        # ✅ 활성 전략 파일 업데이트 (로그아웃/로그인 시에도 전략 유지)
        save_active_strategy(user_id, selected_strategy_type)

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

        # ✅ 저장한 "그 전략" 파일에서 다시 로드해서 보여준다.
        exist_params = load_params(json_path, strategy_type=selected_strategy_type)
        if exist_params:
            # Pydantic model 이라면 strategy_type 포함 전체 스냅샷 확인 가능
            # st.write(exist_params)
            st.json(exist_params.__dict__)

        start_trading = st.button(
            f"Upbit Trade Bot v1 ({mode}) - Go Dashboard", use_container_width=True
        )
    except Exception as e:
        st.error(f"❌ 파라미터 저장 실패: {e}")
        st.stop()
else:
    # ✅ 현재 선택된 전략 기준으로 로드해야 fast/slow가 전략별로 복원됨
    exist_params = load_params(json_path, strategy_type=selected_strategy_type)

    if exist_params:
        # st.write(exist_params)
        st.json(exist_params.__dict__)
        st.caption(f"현재 전략 타입: **{exist_params.strategy_type}**")

        if mode == "LIVE":
            if (upbit_ok and capital_ok):
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

    # ✅ URL 에도 strategy_type 을 태워서 넘겨두면
    #    dashboard 측에서 필요 시 바로 읽어 쓸 수 있음 (옵션)
    query_string = urlencode({
        "user_id": user_id,
        "virtual_krw": virtual_krw,
        "mode": mode,
        "verified": int(upbit_ok),
        "capital_set": int(capital_ok),
        # ✅ strategy_type으로 통일
        "strategy_type": selected_strategy_type,
    })

    st.markdown(
        f'<meta http-equiv="refresh" content="0; url=./{next_page}?{query_string}">',
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
