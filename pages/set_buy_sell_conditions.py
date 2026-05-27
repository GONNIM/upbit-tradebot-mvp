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
from engine.params import load_params, save_params, load_active_strategy  # ✅ 파라미터 로드/저장용


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
# ✅ FIX: session_state에 user_id 저장 (다른 페이지에서 참조 가능하도록)
st.session_state["user_id"] = user_id


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

# ✅ FIX: session_state에 virtual_krw 저장 (다른 페이지에서 참조 가능하도록)
st.session_state["virtual_krw"] = virtual_krw

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
# 전략별 조건 목록 정의 - 전략과 필터로 구분
# ============================================================

# ★ MACD 전략
MACD_BUY_STRATEGY = {
    "golden_cross": "🟢  Golden Cross",
    "macd_positive": "✳️  MACD > threshold",
    "signal_positive": "➕  Signal > threshold",
    "bullish_candle": "📈  Bullish Candle",
    "macd_trending_up": "🔼  MACD Trending Up",
    "above_ma20": "🧮  Above MA20",
    "above_ma60": "🧮  Above MA60",
}

MACD_BUY_FILTERS = {}  # MACD는 매수 필터 없음

MACD_SELL_STRATEGY = {
    "stop_loss": "🔻  Stop Loss",
    "take_profit": "💰  Take Profit",
    "trailing_stop": "🧮  Trailing Stop",
    "dead_cross": "🔴  Dead Cross",
    "macd_negative": "📉  MACD < threshold",
    "signal_negative": "➖  Signal < threshold",
}

MACD_SELL_FILTERS = {}  # MACD는 매도 필터 없음

# ★ EMA 전략
EMA_BUY_STRATEGY = {
    "ema_gc": "🟢 EMA Golden Cross",
    "above_base_ema": "📈 Price > Base EMA",
    "bullish_candle": "📈 Bullish Candle",
}

EMA_BUY_FILTERS = {
    "surge_filter_enabled": "🚫 급등 차단 필터 (Slow EMA 대비 급등 시 매수 차단)",
}

EMA_SELL_STRATEGY = {
    "stop_loss": "🔻 Stop Loss",
    "take_profit": "💰 Take Profit",
    "trailing_stop": "🧮 Trailing Stop",
    "ema_dc": "🔴 EMA Dead Cross",
}

EMA_SELL_FILTERS = {
    "stale_position_check": "💤 정체 포지션 강제매도",
}

# 전략별 선택
if strategy_tag == "EMA":
    BUY_STRATEGY = EMA_BUY_STRATEGY
    BUY_FILTERS = EMA_BUY_FILTERS
    SELL_STRATEGY = EMA_SELL_STRATEGY
    SELL_FILTERS = EMA_SELL_FILTERS
else:
    # 기본은 MACD
    BUY_STRATEGY = MACD_BUY_STRATEGY
    BUY_FILTERS = MACD_BUY_FILTERS
    SELL_STRATEGY = MACD_SELL_STRATEGY
    SELL_FILTERS = MACD_SELL_FILTERS

# 전체 조건 목록 (하위 호환성)
BUY_CONDITIONS = {**BUY_STRATEGY, **BUY_FILTERS}
SELL_CONDITIONS = {**SELL_STRATEGY, **SELL_FILTERS}


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
    # ✅ params 파일에서 기본값 로드 (sidebar와 연동)
    params_file = f"{user_id}_{PARAMS_JSON_FILENAME}"
    params_obj = load_params(params_file, strategy_type=strategy_tag)

    # params에서 Ticker/TP/SL 기본값 추출
    default_ticker = "ZRO"  # 기본값
    default_tp_pct = 3.0  # 기본값
    default_sl_pct = 1.0  # 기본값
    default_ts_threshold = 10.0  # 기본값

    if params_obj:
        default_ticker = params_obj.ticker  # 종목
        default_tp_pct = params_obj.take_profit * 100.0  # 0.05 -> 5.0%
        default_sl_pct = params_obj.stop_loss * 100.0    # 0.01 -> 1.0%
        # trailing_stop은 params에 없으므로 기본값 사용

    if SAVE_PATH.exists():
        with SAVE_PATH.open("r", encoding="utf-8") as f:
            saved = json.load(f)
            buy_saved = saved.get("buy", {})
            sell_saved = saved.get("sell", {})
            for key in BUY_CONDITIONS:
                st.session_state[key] = buy_saved.get(key, False)
            for key in SELL_CONDITIONS:
                st.session_state[key] = sell_saved.get(key, False)

            # ✅ Surge Filter 파라미터 로드 (EMA 전략만)
            st.session_state["surge_threshold_pct"] = buy_saved.get("surge_threshold_pct", 0.01)

            # ✅ Stale Position 파라미터 로드
            st.session_state["stale_hours"] = sell_saved.get("stale_hours", 1.0)
            st.session_state["stale_threshold_pct"] = sell_saved.get("stale_threshold_pct", 0.01)

            # ✅ Ticker/TP/SL 파라미터 로드 (conditions 우선, 없으면 params 기본값)
            st.session_state["ticker_input"] = default_ticker  # Ticker는 항상 params에서
            st.session_state["take_profit_pct"] = sell_saved.get("take_profit_pct", default_tp_pct)
            st.session_state["stop_loss_pct"] = sell_saved.get("stop_loss_pct", default_sl_pct)
            st.session_state["trailing_stop_threshold_pct"] = sell_saved.get("trailing_stop_threshold_pct", default_ts_threshold)
            st.session_state["use_fixed_trailing"] = sell_saved.get("use_fixed_trailing", False)  # ✅ 고정폭 모드

        st.info(f"✅ [{strategy_tag}] 저장된 매수/매도 전략 Condition 설정을 불러왔습니다.")
    else:
        for key in BUY_CONDITIONS:
            st.session_state.setdefault(key, False)
        for key in SELL_CONDITIONS:
            st.session_state.setdefault(key, False)

        # ✅ 기본값 설정 (params 연동)
        st.session_state.setdefault("ticker_input", default_ticker)
        st.session_state.setdefault("surge_threshold_pct", 0.01)
        st.session_state.setdefault("stale_hours", 1.0)
        st.session_state.setdefault("stale_threshold_pct", 0.01)
        st.session_state.setdefault("take_profit_pct", default_tp_pct)
        st.session_state.setdefault("stop_loss_pct", default_sl_pct)
        st.session_state.setdefault("trailing_stop_threshold_pct", default_ts_threshold)
        st.session_state.setdefault("use_fixed_trailing", False)  # ✅ 고정폭 모드 기본값


# --- 상태 저장하기 ---
def save_conditions():
    conditions = {
        "buy": {key: st.session_state[key] for key in BUY_CONDITIONS},
        "sell": {key: st.session_state[key] for key in SELL_CONDITIONS},
    }

    # ✅ Surge Filter 파라미터 추가 저장 (EMA 전략만)
    if strategy_tag == "EMA" and st.session_state.get("surge_filter_enabled", False):
        conditions["buy"]["surge_threshold_pct"] = st.session_state.get("surge_threshold_pct", 0.01)

    # ✅ Stale Position 파라미터 추가 저장 (EMA 전략만)
    if strategy_tag == "EMA" and st.session_state.get("stale_position_check", False):
        conditions["sell"]["stale_hours"] = st.session_state.get("stale_hours", 1.0)
        conditions["sell"]["stale_threshold_pct"] = st.session_state.get("stale_threshold_pct", 0.01)

    # ✅ TP/SL 파라미터 추가 저장 (활성화 시)
    if st.session_state.get("stop_loss", False):
        conditions["sell"]["stop_loss_pct"] = st.session_state.get("stop_loss_pct", 1.0)

    if st.session_state.get("take_profit", False):
        conditions["sell"]["take_profit_pct"] = st.session_state.get("take_profit_pct", 3.0)

    if st.session_state.get("trailing_stop", False):
        conditions["sell"]["trailing_stop_threshold_pct"] = st.session_state.get("trailing_stop_threshold_pct", 10.0)
        conditions["sell"]["use_fixed_trailing"] = st.session_state.get("use_fixed_trailing", False)

    with SAVE_PATH.open("w", encoding="utf-8") as f:
        json.dump(conditions, f, indent=2, ensure_ascii=False)

    # ✅ FIX: Ticker/TP/SL 값을 params 파일에도 반영 (대시보드 표시용)
    #    - 대시보드는 params.ticker, params.take_profit, params.stop_loss에서 값을 읽음
    #    - buy_sell_conditions에서 Ticker/TP/SL 수정 시 params도 함께 업데이트 필요
    params_file = f"{user_id}_{PARAMS_JSON_FILENAME}"
    params_obj = load_params(params_file, strategy_type=strategy_tag)

    if params_obj:
        # Ticker/TP/SL 값이 변경되었으면 params 업데이트
        ticker_changed = False
        tp_changed = False
        sl_changed = False

        # Ticker 변경 감지
        new_ticker = st.session_state.get("ticker_input", None)
        if new_ticker and new_ticker != params_obj.ticker:
            params_obj.ticker = new_ticker
            ticker_changed = True

        # Stop Loss 변경 감지
        if st.session_state.get("stop_loss", False):
            new_sl_pct = st.session_state.get("stop_loss_pct", 1.0) / 100.0
            if abs(params_obj.stop_loss - new_sl_pct) > 0.0001:
                params_obj.stop_loss = new_sl_pct
                sl_changed = True

        # Take Profit 변경 감지
        if st.session_state.get("take_profit", False):
            new_tp_pct = st.session_state.get("take_profit_pct", 3.0) / 100.0
            if abs(params_obj.take_profit - new_tp_pct) > 0.0001:
                params_obj.take_profit = new_tp_pct
                tp_changed = True

        # 변경사항이 있으면 params 파일 저장
        if ticker_changed or tp_changed or sl_changed:
            save_params(params_obj, params_file, strategy_type=strategy_tag)

            # 변경된 항목 표시
            changed_items = []
            if ticker_changed:
                changed_items.append("종목")
            if tp_changed:
                changed_items.append("TP")
            if sl_changed:
                changed_items.append("SL")

            st.info(f"📝 {'/'.join(changed_items)} 값이 파라미터 파일에도 반영되었습니다.")

    st.success(f"✅ [{strategy_tag}] 매수/매도 전략 Condition 설정이 저장되었습니다.")


def go_dashboard():
    # ✅ Streamlit 1.46.0: URL로 파라미터 전달 (meta refresh + st.stop)
    from urllib.parse import urlencode
    params = urlencode({
        "user_id": user_id,
        "virtual_krw": virtual_krw,
        "mode": mode,
        "strategy": strategy_tag,
    })
    st.markdown(f'<meta http-equiv="refresh" content="0; url=./dashboard?{params}">', unsafe_allow_html=True)
    st.stop()


# --- 최초 로딩 시 상태 불러오기 ---
# 전략이 바뀌어도 각 전략별로 다시 로딩되도록 key를 분리
loaded_key = f"loaded_{strategy_tag}"
if not st.session_state.get(loaded_key, False):
    load_conditions()
    st.session_state[loaded_key] = True

# --- UI 스타일 추가 ---
st.markdown(
    """
    <style>
    /* 페이지 제목 */
    h1 {
        font-size: 2.2rem !important;
        font-weight: 700 !important;
        margin-bottom: 1.5rem !important;
        padding-bottom: 0.5rem !important;
        border-bottom: 2px solid #4CAF50;
    }

    /* 섹션 제목 (매수/매도) */
    h2 {
        font-size: 1.6rem !important;
        font-weight: 600 !important;
        margin-top: 2rem !important;
        margin-bottom: 1rem !important;
        color: #2E7D32;
    }

    /* 서브 제목 */
    h4 {
        font-size: 1.1rem !important;
        font-weight: 600 !important;
        margin-top: 1rem !important;
        margin-bottom: 0.5rem !important;
        color: #555;
    }

    /* Expander 제목 크기 */
    details summary {
        font-size: 1.15rem !important;
        font-weight: 600 !important;
        padding: 0.8rem !important;
    }

    /* 토글 라벨 크기 */
    [data-testid="stToggle"] label {
        font-size: 1.05rem !important;
        padding: 0.3rem 0.6rem !important;
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

    /* 버튼 스타일 */
    div.stButton > button {
        font-size: 1.15rem !important;
        height: 3.5em !important;
        border-radius: 0.5em !important;
        font-weight: 600 !important;
    }

    /* Number input 라벨 */
    [data-testid="stNumberInput"] label {
        font-size: 1rem !important;
        font-weight: 500 !important;
    }

    /* 설명 텍스트 크기 통일 */
    .stMarkdown p, .stMarkdown li {
        font-size: 0.95rem !important;
        line-height: 1.6 !important;
    }

    /* Info box 폰트 */
    [data-testid="stAlert"] {
        font-size: 0.95rem !important;
    }

    /* Caption 크기 */
    .stCaption {
        font-size: 0.85rem !important;
        color: #666 !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# --- 페이지 제목 ---
st.markdown(f"# 📊 [{strategy_tag}] 매수/매도 전략 설정")

# ============================================================
# ⚙️ 전략 핵심 설정 (자주 변경하는 설정)
# ============================================================
st.markdown("## ⚙️ 전략 핵심 설정")

with st.expander("🎯 자주 변경하는 설정", expanded=True):
    st.caption("가장 많이 수정하는 설정을 한곳에 모았습니다")

    # 종목 입력 (params에서 로드)
    params_file = f"{user_id}_{PARAMS_JSON_FILENAME}"
    params_obj = load_params(params_file, strategy_type=strategy_tag)

    current_ticker = params_obj.ticker if params_obj else "ZRO"
    ticker_input = st.text_input(
        "🎯 거래 종목",
        value=st.session_state.get("ticker_input", current_ticker),
        key=f"quick_ticker_{strategy_tag}",
        help="거래할 암호화폐 심볼 (예: ZRO, BTC, ETH, PEPE)"
    )
    st.session_state["ticker_input"] = ticker_input

    # TP/SL 입력
    col1, col2 = st.columns(2)

    with col1:
        tp_pct_quick = st.number_input(
            "💰 Take Profit (%)",
            min_value=0.1,
            max_value=50.0,
            step=0.1,
            value=st.session_state.get("take_profit_pct", 3.0),
            key=f"quick_tp_{strategy_tag}",
            help="진입가 대비 이 비율 이상 상승 시 자동 매도"
        )
        st.session_state["take_profit_pct"] = tp_pct_quick

    with col2:
        sl_pct_quick = st.number_input(
            "🔻 Stop Loss (%)",
            min_value=0.1,
            max_value=50.0,
            step=0.1,
            value=st.session_state.get("stop_loss_pct", 1.0),
            key=f"quick_sl_{strategy_tag}",
            help="진입가 대비 이 비율 이상 하락 시 자동 매도"
        )
        st.session_state["stop_loss_pct"] = sl_pct_quick

    # 현재 설정 안내
    st.info(
        f"🎯 **{ticker_input}** | "
        f"💰 TP: **+{tp_pct_quick:.1f}%** | "
        f"🔻 SL: **-{sl_pct_quick:.1f}%**"
    )

st.divider()

# ============================================================
# 📈 매수 설정
# ============================================================
st.markdown("## 📈 매수 설정")

# --- 매수: 핵심 전략 조건 ---
with st.expander("⭐ 핵심 전략 조건", expanded=True):
    if len(BUY_STRATEGY) > 0:
        for key, label in BUY_STRATEGY.items():
            st.session_state[key] = st.toggle(
                label,
                value=st.session_state.get(key, False),
                key=f"toggle_{strategy_tag}_buy_strategy_{key}",
            )
    else:
        st.info("이 전략에는 매수 조건이 없습니다.")

# --- 매수: 필터 ---
if len(BUY_FILTERS) > 0:
    with st.expander("🔍 매수 필터", expanded=True):
        st.caption("매수를 차단하는 보조 필터 (리스크 관리용)")
        for key, label in BUY_FILTERS.items():
            st.session_state[key] = st.toggle(
                label,
                value=st.session_state.get(key, False),
                key=f"toggle_{strategy_tag}_buy_filter_{key}",
            )

        # ✅ Surge Filter 파라미터 입력 UI (EMA 전략 + 활성화 시)
        if strategy_tag == "EMA" and st.session_state.get("surge_filter_enabled", False):
            st.markdown("#### ⚙️ 급등 차단 필터 파라미터")
            st.caption("Slow EMA 대비 설정한 비율 이상 급등 시 매수를 차단합니다")

            surge_threshold_pct = st.number_input(
                "급등 임계값 (%)",
                min_value=0.1,
                max_value=10.0,
                step=0.1,
                value=st.session_state.get("surge_threshold_pct", 0.01) * 100.0,
                key=f"input_surge_threshold_{strategy_tag}",
                help="Slow EMA 대비 이 비율 이상 상승 시 매수 차단"
            )
            st.session_state["surge_threshold_pct"] = surge_threshold_pct / 100.0

            st.info(
                f"🚫 현재 설정: Slow EMA 대비 **{surge_threshold_pct:.1f}%** 이상 상승 시 매수 차단"
            )

st.divider()

# ============================================================
# 📉 매도 설정
# ============================================================
st.markdown("## 📉 매도 설정")

# --- 매도: 핵심 전략 조건 ---
with st.expander("⭐ 핵심 전략 조건", expanded=True):
    if len(SELL_STRATEGY) > 0:
        for key, label in SELL_STRATEGY.items():
            st.session_state[key] = st.toggle(
                label,
                value=st.session_state.get(key, False),
                key=f"toggle_{strategy_tag}_sell_strategy_{key}",
            )

            # ✅ Stop Loss 파라미터
            if key == "stop_loss" and st.session_state.get("stop_loss", False):
                st.markdown("#### ⚙️ Stop Loss 파라미터")
                st.caption("진입가 대비 손실 한도를 설정합니다")

                sl_pct = st.number_input(
                    "손실 한도 (%)",
                    min_value=0.1,
                    max_value=50.0,
                    step=0.1,
                    value=st.session_state.get("stop_loss_pct", 1.0),
                    key=f"input_stop_loss_pct_{strategy_tag}",
                    help="진입가 대비 이 비율 이상 하락 시 자동 매도"
                )
                st.session_state["stop_loss_pct"] = sl_pct
                st.info(f"🔻 현재 설정: 진입가 대비 **-{sl_pct:.1f}%** 하락 시 자동 매도")

            # ✅ Take Profit 파라미터
            if key == "take_profit" and st.session_state.get("take_profit", False):
                st.markdown("#### ⚙️ Take Profit 파라미터")
                st.caption("진입가 대비 수익 목표를 설정합니다")

                tp_pct = st.number_input(
                    "수익 목표 (%)",
                    min_value=0.1,
                    max_value=50.0,
                    step=0.1,
                    value=st.session_state.get("take_profit_pct", 3.0),
                    key=f"input_take_profit_pct_{strategy_tag}",
                    help="진입가 대비 이 비율 이상 상승 시 자동 매도"
                )
                st.session_state["take_profit_pct"] = tp_pct
                st.info(f"💰 현재 설정: 진입가 대비 **+{tp_pct:.1f}%** 상승 시 자동 매도")

            # ✅ Trailing Stop 파라미터
            if key == "trailing_stop" and st.session_state.get("trailing_stop", False):
                st.markdown("#### ⚙️ Trailing Stop 파라미터")
                st.caption("수익 보호를 위한 추적 매도 설정")

                # ✅ 기존 값을 10의 배수로 자동 반올림 (범위: 10~90)
                current_ts = st.session_state.get("trailing_stop_threshold_pct", 10.0)
                adjusted_ts = float(max(10.0, min(90.0, round(current_ts / 10) * 10)))

                ts_threshold = st.number_input(
                    "수익 하락 허용 (%)",
                    min_value=10.0,
                    max_value=90.0,
                    step=10.0,
                    value=adjusted_ts,
                    key=f"input_trailing_threshold_{strategy_tag}",
                    help="신고가 대비 이 비율만큼 하락 시 매도 (10%, 20%, 30%, ..., 90%)"
                )
                st.session_state["trailing_stop_threshold_pct"] = ts_threshold

                # ✅ 고정폭 모드 체크박스
                use_fixed_trailing = st.checkbox(
                    "☑️ 고정폭 모드",
                    value=st.session_state.get("use_fixed_trailing", False),
                    key=f"checkbox_use_fixed_trailing_{strategy_tag}",
                    help="체크: 활성화 시점 수익의 N% 고정폭 하락 시 매도\n"
                         "해제: 신고가 대비 수익의 N% 하락 시 매도 (기존 방식)"
                )
                st.session_state["use_fixed_trailing"] = use_fixed_trailing

                # ✅ Take Profit 값 참조 (활성화 조건)
                tp_pct = st.session_state.get("take_profit_pct", 3.0)

                # ✅ 동적 설명 문구 (모드별 분기)
                if use_fixed_trailing:
                    explanation = (
                        f"🧮 현재 설정: Take Profit **+{tp_pct:.1f}%** 초과 시 신고가 추적 → "
                        f"**활성화 시점 수익의 {ts_threshold:.0f}% 고정폭** 하락 시 매도"
                    )
                else:
                    explanation = (
                        f"🧮 현재 설정: Take Profit **+{tp_pct:.1f}%** 초과 시 신고가 추적 → "
                        f"**신고가 대비 수익의 {ts_threshold:.0f}% 하락 시 매도**"
                    )
                st.info(explanation)
    else:
        st.info("이 전략에는 매도 조건이 없습니다.")

# --- 매도: 필터 ---
if len(SELL_FILTERS) > 0:
    with st.expander("🔍 매도 필터", expanded=True):
        st.caption("매도를 트리거하는 보조 필터 (손실 방지용)")
        for key, label in SELL_FILTERS.items():
            st.session_state[key] = st.toggle(
                label,
                value=st.session_state.get(key, False),
                key=f"toggle_{strategy_tag}_sell_filter_{key}",
            )

        # ✅ Stale Position 파라미터 입력 UI (EMA 전략 + 활성화 시)
        if strategy_tag == "EMA" and st.session_state.get("stale_position_check", False):
            st.markdown("#### ⚙️ 정체 포지션 필터 파라미터")
            st.caption("설정한 시간 동안 목표 수익률을 달성하지 못하면 강제 매도합니다")

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
                    "최소 수익률 목표 (%)",
                    min_value=0.1,
                    max_value=10.0,
                    step=0.1,
                    value=st.session_state.get("stale_threshold_pct", 0.01) * 100.0,
                    key=f"input_stale_threshold_{strategy_tag}",
                    help="진입 후 최고가 기준 이 수익률 미달 시 강제 매도"
                )
                st.session_state["stale_threshold_pct"] = stale_threshold_pct / 100.0

            st.info(
                f"💤 현재 설정: **{stale_hours}시간** 동안 진입가 대비 최고 수익률이 "
                f"**{stale_threshold_pct:.1f}%** 미만이면 강제 매도"
            )

st.divider()

# --- 저장 버튼 ---
if st.button("💾 설정 저장", use_container_width=True):
    save_conditions()
    go_dashboard()

# --- 현재 상태 출력 ---
st.subheader("⚙️ 현재 설정 요약")

col1, col2 = st.columns(2)

with col1:
    st.markdown("**📈 매수 설정**")
    if len(BUY_STRATEGY) > 0:
        st.markdown("_핵심 전략:_")
        for key, label in BUY_STRATEGY.items():
            st.write(f"{'✅' if st.session_state[key] else '❌'} {label}")
    if len(BUY_FILTERS) > 0:
        st.markdown("_매수 필터:_")
        for key, label in BUY_FILTERS.items():
            st.write(f"{'✅' if st.session_state[key] else '❌'} {label}")
            if key == "surge_filter_enabled" and st.session_state.get(key, False):
                surge_pct = st.session_state.get("surge_threshold_pct", 0.01) * 100
                st.caption(f"   └─ 임계값: {surge_pct:.1f}%")

with col2:
    st.markdown("**📉 매도 설정**")
    if len(SELL_STRATEGY) > 0:
        st.markdown("_핵심 전략:_")
        for key, label in SELL_STRATEGY.items():
            st.write(f"{'✅' if st.session_state[key] else '❌'} {label}")
    if len(SELL_FILTERS) > 0:
        st.markdown("_매도 필터:_")
        for key, label in SELL_FILTERS.items():
            st.write(f"{'✅' if st.session_state[key] else '❌'} {label}")
            if key == "stale_position_check" and st.session_state.get(key, False):
                hours = st.session_state.get("stale_hours", 1.0)
                threshold = st.session_state.get("stale_threshold_pct", 0.01) * 100
                st.caption(f"   └─ {hours}h, {threshold:.1f}%")
