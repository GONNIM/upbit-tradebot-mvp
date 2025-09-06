# FINAL CODE
# pages/set_buy_sell_conditions.py

import streamlit as st
import json
import pandas as pd
from pathlib import Path
from datetime import datetime
from urllib.parse import urlencode

from ui.style import style_main
from config import CONDITIONS_JSON_FILENAME, PARAMS_JSON_FILENAME
from engine.params import load_params, get_params_manager, StrategyType, MACDParams, RSIParams, BollingerParams, GridParams
from engine.global_state import get_global_state_manager
from services.health_monitor import get_health_status

# --- 페이지 설정 ---
st.set_page_config(page_title="Upbit Trade Bot v2 - 전략 설정", page_icon="🎯", layout="wide")
st.markdown(style_main, unsafe_allow_html=True)

params = st.query_params
user_id = params.get("user_id", "")
virtual_krw = int(params.get("virtual_krw", 0))

if user_id == "":
    st.switch_page("app.py")

# --- 전역 상태 관리자 초기화 ---
global_state_manager = get_global_state_manager()
params_manager = get_params_manager()

# --- 사용자 설정 저장 경로 ---
target_filename = f"{user_id}_{CONDITIONS_JSON_FILENAME}"
SAVE_PATH = Path(target_filename)

# --- 기존 파라미터 로드 ---
json_path = f"{user_id}_{PARAMS_JSON_FILENAME}"
existing_params = load_params(json_path)

# --- UI 스타일 ---
st.markdown(
    """
    <style>
    /* 헤더와 본문 사이 간격 제거 */
    div.block-container {
        padding-top: 1rem;
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
    /* 전략 카드 스타일 */
    .strategy-card {
        background-color: #f0f2f6;
        border-radius: 0.5rem;
        padding: 1.5rem;
        margin: 1rem 0;
        border: 1px solid #e1e4e8;
    }
    /* 파라미터 그룹 스타일 */
    .param-group {
        background-color: #ffffff;
        border-radius: 0.5rem;
        padding: 1rem;
        margin: 0.5rem 0;
        border: 1px solid #e1e4e8;
    }
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
    </style>
    """,
    unsafe_allow_html=True,
)

# --- 제목 ---
st.title(f"🎯 전략 설정 - {user_id}")

# 🏥 헬스 상태 표시
col1, col2, col3 = st.columns(3)
with col1:
    health_status = get_health_status()
    if health_status.get('status') == 'healthy':
        st.success("✅ 시스템 정상")
    else:
        st.error("⚠️ 시스템 경고")
with col2:
    cpu_usage = health_status.get('cpu_usage_percent', 0)
    st.info(f"🖥️ CPU: {cpu_usage:.1f}%")
with col3:
    memory_mb = health_status.get('memory_usage_mb', 0)
    st.info(f"💾 메모리: {memory_mb:.1f}MB")

# --- 전략 타입 선택 ---
st.subheader("📊 전략 타입 선택")

strategy_type = st.selectbox(
    "전략 선택",
    [stype.value for stype in StrategyType],
    index=0,
    help="사용할 거래 전략을 선택하세요"
)

# --- 전략별 파라미터 설정 ---
st.subheader("⚙️ 전략 파라미터 설정")

# MACD 전략 파라미터
if strategy_type == StrategyType.MACD.value:
    with st.expander("📈 MACD 전략 파라미터", expanded=True):
        # 기존 MACD 파라미터 가져오기
        default_macd = MACDParams()
        if existing_params and existing_params.strategy.macd:
            default_macd = existing_params.strategy.macd
        
        macd_cols = st.columns(3)
        
        with macd_cols[0]:
            fast_period = st.number_input(
                "빠른 이동평균 기간",
                1, 50, default_macd.fast_period,
                help="MACD 빠른 선 기간"
            )
            
            signal_period = st.number_input(
                "신호선 기간",
                1, 50, default_macd.signal_period,
                help="MACD 신호선 기간"
            )
            
            enable_crossover = st.checkbox(
                "크로스오버 신호 사용",
                value=default_macd.enable_crossover,
                help="골든/데드 크로스 신호 사용"
            )
        
        with macd_cols[1]:
            slow_period = st.number_input(
                "느린 이동평균 기간",
                1, 100, default_macd.slow_period,
                help="MACD 느린 선 기간"
            )
            
            macd_threshold = st.number_input(
                "MACD 임계값",
                -1.0, 1.0, default_macd.macd_threshold,
                step=0.1,
                help="MACD 신호 임계값"
            )
            
            enable_divergence = st.checkbox(
                "다이버전스 신호 사용",
                value=default_macd.enable_divergence,
                help="MACD 다이버전스 신호 사용"
            )
        
        with macd_cols[2]:
            histogram_threshold = st.number_input(
                "히스토그램 임계값",
                -1.0, 1.0, default_macd.histogram_threshold,
                step=0.1,
                help="MACD 히스토그램 임계값"
            )

# RSI 전략 파라미터
elif strategy_type == StrategyType.RSI.value:
    with st.expander("📊 RSI 전략 파라미터", expanded=True):
        default_rsi = RSIParams()
        if existing_params and existing_params.strategy.rsi:
            default_rsi = existing_params.strategy.rsi
        
        rsi_cols = st.columns(2)
        
        with rsi_cols[0]:
            period = st.number_input(
                "RSI 기간",
                2, 50, default_rsi.period,
                help="RSI 계산 기간"
            )
            
            oversold = st.number_input(
                "과매도 기준",
                0, 50, default_rsi.oversold,
                help="과매도 판단 기준"
            )
        
        with rsi_cols[1]:
            overbought = st.number_input(
                "과매수 기준",
                50, 100, default_rsi.overbought,
                help="과매수 판단 기준"
            )
            
            use_rsi_ma = st.checkbox(
                "RSI 이동평균 사용",
                value=default_rsi.use_rsi_ma,
                help="RSI 이동평균 필터 사용"
            )
            
            if use_rsi_ma:
                ma_period = st.number_input(
                    "이동평균 기간",
                    2, 20, default_rsi.ma_period,
                    help="RSI 이동평균 기간"
                )

# 볼린저 밴드 전략 파라미터
elif strategy_type == StrategyType.BOLLINGER.value:
    with st.expander("📊 볼린저 밴드 전략 파라미터", expanded=True):
        default_bollinger = BollingerParams()
        if existing_params and existing_params.strategy.bollinger:
            default_bollinger = existing_params.strategy.bollinger
        
        bollinger_cols = st.columns(2)
        
        with bollinger_cols[0]:
            period = st.number_input(
                "기간",
                5, 50, default_bollinger.period,
                help="볼린저 밴드 기간"
            )
            
            std_dev = st.number_input(
                "표준편차 배수",
                0.5, 5.0, default_bollinger.std_dev,
                step=0.1,
                help="표준편차 배수"
            )
            
            use_bands = st.checkbox(
                "밴드 사용",
                value=default_bollinger.use_bands,
                help="볼린저 밴드 신호 사용"
            )
        
        with bollinger_cols[1]:
            use_squeeze = st.checkbox(
                "스퀴즈 신호 사용",
                value=default_bollinger.use_squeeze,
                help="볼린저 스퀴즈 신호 사용"
            )
            
            use_rsi_filter = st.checkbox(
                "RSI 필터 사용",
                value=default_bollinger.use_rsi_filter,
                help="RSI 필터 추가 사용"
            )
            
            if use_rsi_filter:
                rsi_period = st.number_input(
                    "RSI 필터 기간",
                    2, 50, default_bollinger.rsi_period,
                    help="RSI 필터 기간"
                )

# 그리드 전략 파라미터
elif strategy_type == StrategyType.GRID.value:
    with st.expander("📊 그리드 전략 파라미터", expanded=True):
        default_grid = GridParams()
        if existing_params and existing_params.strategy.grid:
            default_grid = existing_params.strategy.grid
        
        grid_cols = st.columns(2)
        
        with grid_cols[0]:
            grid_count = st.number_input(
                "그리드 개수",
                3, 50, default_grid.grid_count,
                help="그리드 라인 수"
            )
            
            grid_spacing = st.number_input(
                "그리드 간격 (%)",
                0.1, 10.0, default_grid.grid_spacing,
                step=0.1,
                help="그리드 간격 (비율)"
            )
        
        with grid_cols[1]:
            rebalance_threshold = st.number_input(
                "리밸런싱 임계값 (%)",
                0.1, 5.0, default_grid.rebalance_threshold,
                step=0.1,
                help="리밸런싱 임계값 (비율)"
            )
            
            dynamic_grid = st.checkbox(
                "동적 그리드 사용",
                value=default_grid.dynamic_grid,
                help="변동성 기반 동적 그리드"
            )
            
            if dynamic_grid:
                volatility_period = st.number_input(
                    "변동성 기간",
                    5, 50, default_grid.volatility_period,
                    help="변동성 계산 기간"
                )

# --- 진입/청산 조건 설정 ---
st.subheader("🎯 진입/청산 조건 설정")

# --- 조건 목록 ---
BUY_CONDITIONS = {
    "macd_positive": "✳️ MACD > threshold",
    "signal_positive": "➕ Signal > threshold", 
    "bullish_candle": "📈 Bullish Candle",
    "macd_trending_up": "🔼 MACD Trending Up",
    "above_ma20": "🧮 Above MA20",
    "above_ma60": "🧮 Above MA60",
    "entry_delay": "⏱️ 진입 지연 (N봉 후)",
    "min_holding_period": "📅 최소 보유 기간 (N봉 이상)"
}

SELL_CONDITIONS = {
    "trailing_stop": "🧮 Trailing Stop - Peak (-10%)",
    "take_profit": "💰 Take Profit",
    "stop_loss": "🔻 Stop Loss", 
    "macd_exit": "📉 MACD Exit - Dead Cross or MACD < threshold",
    "volatility_based": "📊 변동성 기반 TP/SL",
    "atr_based": "📏 ATR 기반 손익 결정"
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

# --- 최초 로딩 시 상태 불러오기 ---
if "loaded" not in st.session_state:
    load_conditions()
    st.session_state["loaded"] = True

# --- 진입 조건 설정 ---
with st.expander("📈 진입 조건 설정", expanded=True):
    entry_cols = st.columns(2)
    
    with entry_cols[0]:
        st.markdown("#### MACD 조건")
        st.session_state["macd_positive"] = st.checkbox(
            "MACD > threshold", value=st.session_state.get("macd_positive", False)
        )
        st.session_state["signal_positive"] = st.checkbox(
            "Signal > threshold", value=st.session_state.get("signal_positive", False)
        )
        st.session_state["macd_trending_up"] = st.checkbox(
            "MACD Trending Up", value=st.session_state.get("macd_trending_up", False)
        )
    
    with entry_cols[1]:
        st.markdown("#### 캔들/추세 조건")
        st.session_state["bullish_candle"] = st.checkbox(
            "Bullish Candle", value=st.session_state.get("bullish_candle", False)
        )
        st.session_state["above_ma20"] = st.checkbox(
            "Above MA20", value=st.session_state.get("above_ma20", False)
        )
        st.session_state["above_ma60"] = st.checkbox(
            "Above MA60", value=st.session_state.get("above_ma60", False)
        )

# --- 진입 파라미터 ---
st.markdown("#### 진입 파라미터")
param_cols = st.columns(2)

with param_cols[0]:
    entry_delay = st.number_input(
        "진입 지연 (봉 수)",
        0, 20, 0,
        help="골든 크로스 후 진입까지 지연할 봉 수"
    )
    st.session_state["entry_delay"] = entry_delay > 0

with param_cols[1]:
    min_holding_period = st.number_input(
        "최소 보유 기간 (봉 수)",
        1, 100, 1,
        help="최소 보유해야 할 봉 수"
    )
    st.session_state["min_holding_period"] = min_holding_period > 0

# --- 청산 조건 설정 ---
with st.expander("📉 청산 조건 설정", expanded=True):
    exit_cols = st.columns(2)
    
    with exit_cols[0]:
        st.markdown("#### 기본 조건")
        st.session_state["take_profit"] = st.checkbox(
            "Take Profit", value=st.session_state.get("take_profit", True)
        )
        st.session_state["stop_loss"] = st.checkbox(
            "Stop Loss", value=st.session_state.get("stop_loss", True)
        )
        st.session_state["macd_exit"] = st.checkbox(
            "MACD Exit", value=st.session_state.get("macd_exit", False)
        )
    
    with exit_cols[1]:
        st.markdown("#### 고급 조건")
        st.session_state["trailing_stop"] = st.checkbox(
            "Trailing Stop", value=st.session_state.get("trailing_stop", False)
        )
        st.session_state["volatility_based"] = st.checkbox(
            "변동성 기반 TP/SL", value=st.session_state.get("volatility_based", False)
        )
        st.session_state["atr_based"] = st.checkbox(
            "ATR 기반 손익 결정", value=st.session_state.get("atr_based", False)
        )

# --- 동적 TP/SL 설정 ---
if st.session_state.get("volatility_based", False) or st.session_state.get("atr_based", False):
    st.markdown("#### 동적 손익 설정")
    dynamic_cols = st.columns(3)
    
    with dynamic_cols[0]:
        volatility_multiplier = st.number_input(
            "변동성 배수",
            0.5, 5.0, 2.0,
            step=0.1,
            help="변동성에 곱해줄 배수"
        )
    
    with dynamic_cols[1]:
        atr_period = st.number_input(
            "ATR 기간",
            5, 50, 14,
            help="ATR 계산 기간"
        )
    
    with dynamic_cols[2]:
        use_standard_deviation = st.checkbox(
            "표준편차 사용",
            value=False,
            help="ATR 대신 표준편차 사용"
        )

# --- 저장 및 적용 ---
st.markdown("---")

action_cols = st.columns([1, 1, 2])

with action_cols[0]:
    if st.button("💾 전략 저장", use_container_width=True):
        try:
            # 파라미터 업데이트
            strategy_params = {}
            
            if strategy_type == StrategyType.MACD.value:
                strategy_params["macd"] = {
                    "fast_period": fast_period,
                    "slow_period": slow_period,
                    "signal_period": signal_period,
                    "macd_threshold": macd_threshold,
                    "histogram_threshold": histogram_threshold,
                    "enable_crossover": enable_crossover,
                    "enable_divergence": enable_divergence
                }
            elif strategy_type == StrategyType.RSI.value:
                strategy_params["rsi"] = {
                    "period": period,
                    "oversold": oversold,
                    "overbought": overbought,
                    "use_rsi_ma": use_rsi_ma,
                    "ma_period": ma_period if use_rsi_ma else 9
                }
            elif strategy_type == StrategyType.BOLLINGER.value:
                strategy_params["bollinger"] = {
                    "period": period,
                    "std_dev": std_dev,
                    "use_bands": use_bands,
                    "use_squeeze": use_squeeze,
                    "use_rsi_filter": use_rsi_filter,
                    "rsi_period": rsi_period if use_rsi_filter else 14
                }
            elif strategy_type == StrategyType.GRID.value:
                strategy_params["grid"] = {
                    "grid_count": grid_count,
                    "grid_spacing": grid_spacing,
                    "rebalance_threshold": rebalance_threshold,
                    "dynamic_grid": dynamic_grid,
                    "volatility_period": volatility_period if dynamic_grid else 20
                }
            
            # 진입/청산 조건 저장
            save_conditions()
            
            # 파라미터 업데이트
            updates = {
                "strategy": {
                    "strategy_type": strategy_type,
                    **strategy_params
                },
                "custom_params": {
                    "entry_delay": entry_delay,
                    "min_holding_period": min_holding_period,
                    "volatility_multiplier": volatility_multiplier if st.session_state.get("volatility_based", False) else 2.0,
                    "atr_period": atr_period if st.session_state.get("atr_based", False) else 14,
                    "use_standard_deviation": use_standard_deviation if st.session_state.get("volatility_based", False) else False
                }
            }
            
            success = params_manager.update_params(user_id, updates)
            
            if success:
                st.success("✅ 전략 설정이 저장되었습니다!")
                st.caption(f"🕒 저장 시각: {datetime.now().isoformat(timespec='seconds')}")
            else:
                st.error("❌ 전략 설정 저장 실패")
                
        except Exception as e:
            st.error(f"❌ 전략 설정 저장 중 오류 발생: {e}")

with action_cols[1]:
    if st.button("🔄 기본값으로 초기화", use_container_width=True):
        if st.warning("정말로 기본값으로 초기화하시겠습니까?"):
            try:
                # 기본 조건으로 초기화
                for key in BUY_CONDITIONS:
                    st.session_state[key] = False
                for key in SELL_CONDITIONS:
                    st.session_state[key] = False
                
                # 필수 조건만 활성화
                st.session_state["take_profit"] = True
                st.session_state["stop_loss"] = True
                
                save_conditions()
                st.success("✅ 기본값으로 초기화 완료")
                st.rerun()
                
            except Exception as e:
                st.error(f"❌ 초기화 중 오류 발생: {e}")

# --- 현재 설정 미리보기 ---
st.subheader("📋 현재 전략 설정")

# 전략 요약
strategy_summary = {
    "전략 타입": strategy_type,
    "진입 지연": f"{entry_delay}봉" if entry_delay > 0 else "없음",
    "최소 보유": f"{min_holding_period}봉",
    "변동성 기반": "사용" if st.session_state.get("volatility_based", False) else "미사용",
    "ATR 기반": "사용" if st.session_state.get("atr_based", False) else "미사용"
}

summary_cols = st.columns(3)
with summary_cols[0]:
    for key, value in list(strategy_summary.items())[:2]:
        st.markdown(f"**{key}**: {value}")
with summary_cols[1]:
    for key, value in list(strategy_summary.items())[2:4]:
        st.markdown(f"**{key}**: {value}")
with summary_cols[2]:
    for key, value in list(strategy_summary.items())[4:]:
        st.markdown(f"**{key}**: {value}")

# 진입 조건 상태
st.markdown("#### 📈 진입 조건")
active_buy = [label for key, label in BUY_CONDITIONS.items() if st.session_state.get(key, False)]
if active_buy:
    for condition in active_buy:
        st.success(f"✅ {condition}")
else:
    st.info("활성화된 진입 조건이 없습니다.")

# 청산 조건 상태
st.markdown("#### 📉 청산 조건")
active_sell = [label for key, label in SELL_CONDITIONS.items() if st.session_state.get(key, False)]
if active_sell:
    for condition in active_sell:
        st.error(f"✅ {condition}")
else:
    st.info("활성화된 청산 조건이 없습니다.")

# --- 이동 버튼 ---
st.markdown("---")

nav_cols = st.columns(2)

with nav_cols[0]:
    if st.button("📊 대시보드", use_container_width=True):
        next_page = "dashboard"
        params = urlencode({"virtual_krw": virtual_krw, "user_id": user_id})
        st.markdown(
            f'<meta http-equiv="refresh" content="0; url=./{next_page}?{params}">',
            unsafe_allow_html=True,
        )
        st.switch_page(next_page)

with nav_cols[1]:
    if st.button("⚙️ 시스템 설정", use_container_width=True):
        next_page = "set_config"
        params = urlencode({"virtual_krw": virtual_krw, "user_id": user_id})
        st.markdown(
            f'<meta http-equiv="refresh" content="0; url=./{next_page}?{params}">',
            unsafe_allow_html=True,
        )
        st.switch_page(next_page)