import streamlit as st
import json
from pathlib import Path
from urllib.parse import urlencode

from ui.style import style_main
from config import (
    CONDITIONS_JSON_FILENAME,
    STRATEGY_TYPES,         # ✅ 전략 리스트 (예: ["MACD", "EMA"])
    DEFAULT_STRATEGY_TYPE,  # ✅ 기본 전략 타입
    PARAMS_JSON_FILENAME,   # ✅ 파라미터 파일명
)
from engine.params import load_params, load_active_strategy  # ✅ 파라미터 로드용


# --- 페이지 설정 ---
st.set_page_config(page_title="Upbit Trade Bot v1", page_icon="🤖", layout="wide")
st.markdown(style_main, unsafe_allow_html=True)

qp = st.query_params


def _get_param(qp, key, default=None):
    v = qp.get(key, default)
    if isinstance(v, list):
        return v[0]
    return v


user_id = _get_param(qp, "user_id", st.session_state.get("user_id", ""))


def _strategy_tag_from_qs() -> str:
    """
    ✅ active_strategy.txt 파일에서 실제 전략을 읽어서 MACD / EMA 반환.
    파일이 없으면 URL / 세션 / 기본값 순서로 폴백.
    """
    # ✅ 1순위: active_strategy.txt 파일에서 읽기
    file_strategy = load_active_strategy(user_id)
    if file_strategy:
        st.session_state["strategy_type"] = file_strategy
        return file_strategy

    # ✅ 2순위: URL 파라미터
    raw = _get_param(qp, "strategy", st.session_state.get("strategy_type", DEFAULT_STRATEGY_TYPE))
    if not raw:
        return DEFAULT_STRATEGY_TYPE.upper()

    tag = str(raw).upper().strip()
    allowed = [s.upper() for s in STRATEGY_TYPES]
    if tag not in allowed:
        # 이상한 값이 들어오면 디폴트로 폴백
        tag = DEFAULT_STRATEGY_TYPE.upper()

    # 세션에도 동일하게 박아두기 (다른 페이지에서 재사용)
    st.session_state["strategy_type"] = tag
    return tag
raw_v = _get_param(qp, "virtual_krw", st.session_state.get("virtual_krw", 0))

try:
    virtual_krw = int(raw_v)
except (TypeError, ValueError):
    virtual_krw = int(st.session_state.get("virtual_krw", 0) or 0)

raw_mode = _get_param(qp, "mode", st.session_state.get("mode", "TEST"))
mode = str(raw_mode).upper()
st.session_state["mode"] = mode

if user_id == "":
    st.switch_page("app.py")

# ============================================================
# 🧠 전략 타입 결정 (MACD / EMA)
#   - URL ?strategy=MACD / EMA 를 우선
#   - 없으면 세션 / DEFAULT_STRATEGY_TYPE
# ============================================================
strategy_tag = _strategy_tag_from_qs()  # "MACD" or "EMA"

# --- 사용자 설정 저장 경로 ---
# ✅ 엔진의 load_trade_conditions 와 동일 규칙:
#     {user_id}_{STRATEGY}_{CONDITIONS_JSON_FILENAME}
#     예) mcmax33_MACD_buy_sell_conditions.json
target_filename = f"{user_id}_{strategy_tag}_{CONDITIONS_JSON_FILENAME}"
SAVE_PATH = Path(target_filename)

# ============================================================
# 전략별 조건 목록 정의
#   - MACD 전용 조건 (기존 그대로)
#   - EMA 전용 조건 (예시)
# ============================================================
MACD_BUY_CONDITIONS = {
    "golden_cross": "🟢  Golden Cross",
    "macd_positive": "✳️  MACD > threshold",
    "signal_positive": "➕  Signal > threshold",
    "bullish_candle": "📈  Bullish Candle",
    "macd_trending_up": "🔼  MACD Trending Up",
    "above_ma20": "🧮  Above MA20",
    "above_ma60": "🧮  Above MA60",
}

MACD_SELL_CONDITIONS = {
    "trailing_stop": "🧮 Trailing Stop - Peak (-10%)",
    "take_profit": "💰  Take Profit",
    "stop_loss": "🔻  Stop Loss",
    "macd_negative": "📉  MACD < threshold",
    "signal_negative": "➖  Signal < threshold",
    "dead_cross": "🔴  Dead Cross",
}

EMA_BUY_CONDITIONS = {
    "ema_gc": "🟢 EMA Golden Cross",
    "above_base_ema": "📈 Price > Base EMA",
    "bullish_candle": "📈 Bullish Candle",
}

EMA_SELL_CONDITIONS = {
    "ema_dc": "🔴 EMA Dead Cross",
    "trailing_stop": "🧮 Trailing Stop",
    "take_profit": "💰 Take Profit",
    "stop_loss": "🔻 Stop Loss",
    "stale_position_check": "💤 정체 포지션 강제매도 (1시간 내 1% 미상승)",
}

if strategy_tag == "EMA":
    BUY_CONDITIONS = EMA_BUY_CONDITIONS
    SELL_CONDITIONS = EMA_SELL_CONDITIONS
else:
    # 기본은 MACD
    BUY_CONDITIONS = MACD_BUY_CONDITIONS
    SELL_CONDITIONS = MACD_SELL_CONDITIONS


# --- 상태 불러오기 ---
def load_conditions():
    """
    현재 strategy_tag 에 대응하는 파일에서 조건 로드.
    파일 구조:
        {
            "buy": {condition_key: bool, ...},
            "sell": {condition_key: bool, ...}
        }
    """
    if SAVE_PATH.exists():
        with SAVE_PATH.open("r", encoding="utf-8") as f:
            saved = json.load(f)
            buy_saved = saved.get("buy", {})
            sell_saved = saved.get("sell", {})
            for key in BUY_CONDITIONS:
                st.session_state[key] = buy_saved.get(key, False)
            for key in SELL_CONDITIONS:
                st.session_state[key] = sell_saved.get(key, False)

            # ✅ Stale Position 파라미터 로드
            st.session_state["stale_hours"] = sell_saved.get("stale_hours", 1.0)
            st.session_state["stale_threshold_pct"] = sell_saved.get("stale_threshold_pct", 0.01)

        st.info(f"✅ [{strategy_tag}] 저장된 매수/매도 전략 Condition 설정을 불러왔습니다.")
    else:
        for key in BUY_CONDITIONS:
            st.session_state.setdefault(key, False)
        for key in SELL_CONDITIONS:
            st.session_state.setdefault(key, False)

        # ✅ 기본값 설정
        st.session_state.setdefault("stale_hours", 1.0)
        st.session_state.setdefault("stale_threshold_pct", 0.01)


# --- 상태 저장하기 ---
def save_conditions():
    conditions = {
        "buy": {key: st.session_state[key] for key in BUY_CONDITIONS},
        "sell": {key: st.session_state[key] for key in SELL_CONDITIONS},
    }

    # ✅ Stale Position 파라미터 추가 저장 (EMA 전략만)
    if strategy_tag == "EMA" and st.session_state.get("stale_position_check", False):
        conditions["sell"]["stale_hours"] = st.session_state.get("stale_hours", 1.0)
        conditions["sell"]["stale_threshold_pct"] = st.session_state.get("stale_threshold_pct", 0.01)

    with SAVE_PATH.open("w", encoding="utf-8") as f:
        json.dump(conditions, f, indent=2, ensure_ascii=False)
    st.success(f"✅ [{strategy_tag}] 매수/매도 전략 Condition 설정이 저장되었습니다.")


def go_dashboard():
    next_page = "dashboard"
    params = urlencode({
        "user_id": user_id,
        "virtual_krw": virtual_krw,
        "mode": mode,
        "strategy": strategy_tag,
    })
    st.markdown(
        f'<meta http-equiv="refresh" content="0; url=./dashboard?{params}">',
        unsafe_allow_html=True,
    )
    st.switch_page(next_page)


# --- 최초 로딩 시 상태 불러오기 ---
# 전략이 바뀌어도 각 전략별로 다시 로딩되도록 key를 분리
loaded_key = f"loaded_{strategy_tag}"
if not st.session_state.get(loaded_key, False):
    load_conditions()
    st.session_state[loaded_key] = True

# --- 토글 UI 스타일 추가 ---
st.markdown(
    """
    <style>
    /* 토글 라벨 크기 증가 */
    [data-testid="stToggle"] label {
        font-size: 1.2em;
        padding: 0.4em 0.8em;
    }

    /* 토글 배경색: 투명한 연두색 */
    [data-testid="stToggle"] div[role="switch"] {
        background-color: rgba(144, 238, 144, 0.35) !important;
        border: 1px solid #9edf9e;
        border-radius: 1.5em;
    }

    /* 토글 스위치 색 */
    [data-testid="stToggle"] div[role="switch"] > div {
        background-color: #76d275 !important;
    }

    /* 전체 버튼 스타일 */
    div.stButton > button {
        font-size: 1.1em;
        height: 3em;
        border-radius: 0.4em;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# --- 제목 및 UI ---
st.markdown(f"### 📊 [{strategy_tag}] 매수/매도 전략 Condition 설정")
st.subheader("📋 매수 전략 Option 선택")
for key, label in BUY_CONDITIONS.items():
    st.session_state[key] = st.toggle(
        label,
        value=st.session_state.get(key, False),
        key=f"toggle_{strategy_tag}_buy_{key}", 
    )

st.divider()

st.subheader("📋 매도 전략 Option 선택")
for key, label in SELL_CONDITIONS.items():
    st.session_state[key] = st.toggle(
        label,
        value=st.session_state.get(key, False),
        key=f"toggle_{strategy_tag}_sell_{key}",
    )

# ✅ Stale Position Check 파라미터 입력 UI (EMA 전략만)
if strategy_tag == "EMA" and st.session_state.get("stale_position_check", False):
    st.markdown("##### ⚙️ 정체 포지션 파라미터 설정")
    st.markdown("_설정한 시간 동안 진입가 대비 설정한 수익률 이상 상승하지 못하면 강제 매도_")

    col1, col2 = st.columns(2)
    with col1:
        stale_hours = st.number_input(
            "체크 시간 (시간)",
            min_value=0.5,
            max_value=24.0,
            step=0.5,
            value=st.session_state.get("stale_hours", 1.0),
            key=f"input_stale_hours_{strategy_tag}",
            help="포지션 보유 후 이 시간이 지나면 수익률 체크"
        )
        st.session_state["stale_hours"] = stale_hours

    with col2:
        stale_threshold_pct = st.number_input(
            "최소 상승률 (%)",
            min_value=0.1,
            max_value=10.0,
            step=0.1,
            value=st.session_state.get("stale_threshold_pct", 1.0),
            key=f"input_stale_threshold_{strategy_tag}",
            help="진입가 대비 이 수익률 미달 시 강제 매도"
        )
        st.session_state["stale_threshold_pct"] = stale_threshold_pct / 100.0

    st.info(
        f"💡 현재 설정: **{stale_hours}시간** 동안 진입가 대비 "
        f"**{stale_threshold_pct:.1f}%** 이상 상승하지 못하면 강제 매도"
    )

st.divider()

# --- 저장 버튼 ---
if st.button("💾 설정 저장", use_container_width=True):
    save_conditions()
    go_dashboard()

# --- 현재 상태 출력 ---
st.subheader("⚙️ 현재 매수/매도 전략 Option 상태")
st.markdown("**📈 매수 전략 상태**")
for key, label in BUY_CONDITIONS.items():
    st.write(f"{label}: {'✅ ON' if st.session_state[key] else '❌ OFF'}")
    
st.markdown("**📉 매도 전략 상태**")
for key, label in SELL_CONDITIONS.items():
    st.write(f"{label}: {'✅ ON' if st.session_state[key] else '❌ OFF'}")
