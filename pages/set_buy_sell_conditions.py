import streamlit as st
import json
from pathlib import Path
from ui.style import style_main
from config import CONDITIONS_JSON_FILENAME
from urllib.parse import urlencode


# --- 페이지 설정 ---
st.set_page_config(page_title="Upbit Trade Bot v1", page_icon="🤖", layout="wide")
st.markdown(style_main, unsafe_allow_html=True)

params = st.query_params
user_id = params.get("user_id", "")

if user_id == "":
    st.switch_page("app.py")

# --- 사용자 설정 저장 경로 ---
target_filename = f"{user_id}_{CONDITIONS_JSON_FILENAME}"
SAVE_PATH = Path(target_filename)


# --- 조건 목록 ---
BUY_CONDITIONS = {
    "golden_cross": "🟢  Golden Cross",
    "macd_positive": "✳️  MACD > threshold",
    "signal_positive": "➕  Signal > threshold",
    "bullish_candle": "📈  Bullish Candle",
    "macd_trending_up": "🔼  MACD Trending Up",
    "above_ma20": "🧮  Above MA20",
    "above_ma60": "🧮  Above MA60",
}

SELL_CONDITIONS = {
    "trailing_stop": "🧮 Trailing Stop - Peak (-10%)",
    "take_profit": "💰  Take Profit",
    "stop_loss": "🔻  Stop Loss",
    "macd_negative": "📉  MACD < threshold",
    "dead_cross": "🔴  Dead Cross",
}


# --- 상태 불러오기 ---
def load_conditions():
    if SAVE_PATH.exists():
        with SAVE_PATH.open("r", encoding="utf-8") as f:
            saved = json.load(f)
            buy_saved = saved.get("buy", {})
            sell_saved = saved.get("sell", {})
            for key in BUY_CONDITIONS:
                st.session_state[key] = buy_saved.get(key, False)
            for key in SELL_CONDITIONS:
                st.session_state[key] = sell_saved.get(key, False)
        st.info("✅ 저장된 매수/매도 전략 Condition 설정을 불러왔습니다.")
    else:
        for key in BUY_CONDITIONS:
            st.session_state.setdefault(key, False)
        for key in SELL_CONDITIONS:
            st.session_state.setdefault(key, False)


# --- 상태 저장하기 ---
def save_conditions():
    conditions = {
        "buy": {key: st.session_state[key] for key in BUY_CONDITIONS},
        "sell": {key: st.session_state[key] for key in SELL_CONDITIONS},
    }
    with SAVE_PATH.open("w", encoding="utf-8") as f:
        json.dump(conditions, f, indent=2, ensure_ascii=False)
    st.success("✅ 매수/매도 전략 Condition 설정이 저장되었습니다.")


def go_dashboard():
    next_page = "dashboard"

    params = urlencode({"user_id": user_id})

    st.markdown(
        f'<meta http-equiv="refresh" content="0; url=./dashboard?{params}">',
        unsafe_allow_html=True,
    )
    st.switch_page(next_page)


# --- 최초 로딩 시 상태 불러오기 ---
if "loaded" not in st.session_state:
    load_conditions()
    st.session_state["loaded"] = True

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
st.markdown("### 📊 매수 전략 Condition 설정")
st.subheader("📋 매수 전략 Option 선택")
for key, label in BUY_CONDITIONS.items():
    st.session_state[key] = st.toggle(
        label, value=st.session_state.get(key, False), key=f"toggle_{key}"
    )

st.divider()

st.markdown("### 📉 매도 전략 Condition 설정")
st.subheader("📋 매도 전략 Option 선택")
for key, label in SELL_CONDITIONS.items():
    st.session_state[key] = st.toggle(
        label, value=st.session_state.get(key, False), key=f"toggle_{key}"
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
