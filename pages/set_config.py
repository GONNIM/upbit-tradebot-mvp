# FINAL CODE
# pages/set_config.py

from __future__ import annotations
import streamlit as st
from urllib.parse import urlencode
from datetime import datetime
import json
import os

from config import MIN_CASH, PARAMS_JSON_FILENAME
from engine.params import load_params, save_params, get_params_manager, LiveParams, TradingMode, StrategyType
from engine.global_state import get_global_state_manager
from services.health_monitor import get_health_status
from services.trading_control import get_trading_control_manager
from services.db import (
    get_account,
    create_or_init_account,
    set_engine_status,
    set_thread_status,
    delete_old_logs,
    get_db_manager,
)
from ui.sidebar import make_sidebar
from ui.style import style_main
from utils.logging_util import init_log_file

# --- 기본 설정 ---
st.set_page_config(page_title="Upbit Trade Bot v2 - 설정", page_icon="⚙️", layout="wide")
st.markdown(style_main, unsafe_allow_html=True)

# --- URL 파라미터 확인 ---
params = st.query_params
user_id = params.get("user_id", "")
virtual_krw = int(params.get("virtual_krw", 0))

if virtual_krw < MIN_CASH:
    st.switch_page("app.py")

# --- 계정 생성 또는 조회 ---
if get_account(user_id) is None:
    create_or_init_account(user_id, virtual_krw)

# --- 세션 변수 초기화 ---
st.session_state.setdefault("virtual_amount", virtual_krw)
st.session_state.setdefault("order_ratio", 1.0)
st.session_state.setdefault("order_amount", virtual_krw)

# --- 전역 상태 관리자 초기화 ---
global_state_manager = get_global_state_manager()
trading_control = get_trading_control_manager()
params_manager = get_params_manager()

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
    /* 설정 카드 스타일 */
    .config-card {
        background-color: #f0f2f6;
        border-radius: 0.5rem;
        padding: 1.5rem;
        margin: 1rem 0;
        border: 1px solid #e1e4e8;
    }
    /* 설정 그룹 스타일 */
    .config-group {
        background-color: #ffffff;
        border-radius: 0.5rem;
        padding: 1rem;
        margin: 0.5rem 0;
        border: 1px solid #e1e4e8;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# --- 제목 ---
st.title(f"⚙️ 시스템 설정 - {user_id}")

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

# --- 기존 파라미터 로드 ---
json_path = f"{user_id}_{PARAMS_JSON_FILENAME}"
existing_params = load_params(json_path)

# --- 설정 섹션 ---
st.subheader("🔧 시스템 설정")

# 📊 거래 모드 설정
with st.expander("🔄 거래 모드 설정", expanded=True):
    trading_mode = st.selectbox(
        "거래 모드",
        [mode.value for mode in TradingMode],
        index=0,
        help="실제 거래, 샌드박스, 테스트 모드 선택"
    )
    
    enable_circuit_breaker = st.checkbox(
        "서킷 브레이커 활성화",
        value=True,
        help="시스템 오류 시 자동으로 거래 중지"
    )
    
    auto_restart = st.checkbox(
        "엔진 자동 재시작",
        value=False,
        help="엔진 비정상 종료 시 자동으로 재시작"
    )

# ⚠️ 위험 관리 설정
with st.expander("⚠️ 위험 관리 설정", expanded=True):
    risk_cols = st.columns(2)
    
    with risk_cols[0]:
        max_position_size = st.slider(
            "최대 포지션 크기 (%)",
            10, 100, 100, 5,
            help="전체 자산 대비 최대 포지션 비율"
        ) / 100
        
        max_drawdown = st.slider(
            "최대 낙폭 (%)",
            5, 50, 20, 1,
            help="허용 가능한 최대 손실률"
        ) / 100
        
        stop_loss_percent = st.slider(
            "손절 비율 (%)",
            1, 20, 5, 1,
            help="개별 거래 손절 비율"
        ) / 100
    
    with risk_cols[1]:
        take_profit_percent = st.slider(
            "익절 비율 (%)",
            1, 50, 10, 1,
            help="개별 거래 익절 비율"
        ) / 100
        
        max_daily_loss = st.slider(
            "최대 일일 손실 (%)",
            1, 30, 10, 1,
            help="하루 최대 손실 한도"
        ) / 100
        
        risk_per_trade = st.slider(
            "거래당 리스크 (%)",
            1, 20, 2, 1,
            help="개별 거래당 리스크 비율"
        ) / 100

# 🚦 실행 설정
with st.expander("🚦 실행 설정", expanded=True):
    exec_cols = st.columns(2)
    
    with exec_cols[0]:
        max_slippage = st.slider(
            "최대 슬리피지 (%)",
            0.1, 2.0, 0.1, 0.1,
            help="허용 가능한 최대 슬리피지"
        ) / 100
        
        execution_delay = st.slider(
            "실행 지연 (초)",
            0.1, 5.0, 0.5, 0.1,
            help="주문 실행 지연 시간"
        )
    
    with exec_cols[1]:
        retry_attempts = st.slider(
            "재시도 횟수",
            1, 10, 3, 1,
            help="실패 시 재시도 횟수"
        )
        
        retry_delay = st.slider(
            "재시도 지연 (초)",
            0.1, 10.0, 1.0, 0.1,
            help="재시도 간 지연 시간"
        )

# 📊 모니터링 설정
with st.expander("📊 모니터링 설정", expanded=True):
    monitor_cols = st.columns(2)
    
    with monitor_cols[0]:
        enable_health_check = st.checkbox(
            "건강 체크 활성화",
            value=True,
            help="시스템 건강 상태 모니터링"
        )
        
        health_check_interval = st.slider(
            "건강 체크 간격 (초)",
            10, 300, 30, 10,
            help="건강 체크 주기"
        )
    
    with monitor_cols[1]:
        enable_performance_tracking = st.checkbox(
            "성능 추적 활성화",
            value=True,
            help="시스템 성능 데이터 추적"
        )
        
        log_level = st.selectbox(
            "로그 레벨",
            ["DEBUG", "INFO", "WARNING", "ERROR"],
            index=1,
            help="로그 출력 레벨"
        )

# 📈 레이트 리밋 설정
with st.expander("📈 레이트 리밋 설정", expanded=True):
    rate_cols = st.columns(2)
    
    with rate_cols[0]:
        max_requests_per_minute = st.slider(
            "분당 최대 요청 수",
            10, 1000, 60, 10,
            help="API 분당 최대 요청 수"
        )
        
        max_orders_per_minute = st.slider(
            "분당 최대 주문 수",
            1, 100, 10, 1,
            help="분당 최대 주문 수"
        )
    
    with rate_cols[1]:
        max_trades_per_day = st.slider(
            "일일 최대 거래 수",
            1, 1000, 50, 10,
            help="하루 최대 거래 수"
        )
        
        cooldown_period = st.slider(
            "쿨다운 기간 (초)",
            1, 60, 5, 1,
            help="거래 후 쿨다운 시간"
        )

# 💰 종목 관리
with st.expander("💰 종목 관리", expanded=True):
    # 기존 파라미터에서 종목 정보 가져오기
    default_ticker = existing_params.ticker if existing_params else "BTC"
    default_interval = existing_params.interval if existing_params else "minute5"
    
    ticker_cols = st.columns(2)
    
    with ticker_cols[0]:
        ticker = st.text_input(
            "거래 종목",
            value=default_ticker,
            help="거래할 암호화폐 심볼 (예: BTC, ETH)"
        ).upper()
    
    with ticker_cols[1]:
        interval_options = {
            "1분": "minute1",
            "3분": "minute3", 
            "5분": "minute5",
            "10분": "minute10",
            "15분": "minute15",
            "30분": "minute30",
            "1시간": "minute60",
            "일봉": "day"
        }
        
        interval = st.selectbox(
            "차트 간격",
            list(interval_options.keys()),
            index=list(interval_options.keys()).index("5분"),
            help="사용할 차트 시간 간격"
        )
        interval_value = interval_options[interval]

# 💾 저장 및 적용 버튼
st.markdown("---")

action_cols = st.columns([1, 1, 2])

with action_cols[0]:
    if st.button("💾 설정 저장", use_container_width=True):
        try:
            # 파라미터 객체 생성 또는 업데이트
            if existing_params:
                # 기존 파라미터 업데이트
                updates = {
                    "execution": {
                        "trading_mode": trading_mode,
                        "max_slippage": max_slippage,
                        "execution_delay": execution_delay,
                        "retry_attempts": retry_attempts,
                        "retry_delay": retry_delay,
                        "enable_circuit_breaker": enable_circuit_breaker
                    },
                    "risk_management": {
                        "max_position_size": max_position_size,
                        "max_drawdown": max_drawdown,
                        "stop_loss_percent": stop_loss_percent,
                        "take_profit_percent": take_profit_percent,
                        "max_daily_loss": max_daily_loss,
                        "risk_per_trade": risk_per_trade,
                        "max_trades_per_day": max_trades_per_day
                    },
                    "monitoring": {
                        "enable_health_check": enable_health_check,
                        "health_check_interval": health_check_interval,
                        "enable_performance_tracking": enable_performance_tracking,
                        "log_level": log_level,
                        "max_requests_per_minute": max_requests_per_minute,
                        "cooldown_period": cooldown_period
                    },
                    "ticker": ticker,
                    "interval": interval_value
                }
                
                success = params_manager.update_params(user_id, updates)
            else:
                # 새 파라미터 생성
                from engine.params import create_params_from_template
                
                new_params = create_params_from_template(
                    user_id=user_id,
                    strategy_type=StrategyType.MACD,
                    ticker=ticker,
                    interval=interval_value
                )
                
                # 추가 설정 적용
                new_params.execution.trading_mode = TradingMode(trading_mode)
                new_params.execution.max_slippage = max_slippage
                new_params.execution.execution_delay = execution_delay
                new_params.execution.retry_attempts = retry_attempts
                new_params.execution.retry_delay = retry_delay
                new_params.execution.enable_circuit_breaker = enable_circuit_breaker
                
                new_params.risk_management.max_position_size = max_position_size
                new_params.risk_management.max_drawdown = max_drawdown
                new_params.risk_management.stop_loss_percent = stop_loss_percent
                new_params.risk_management.take_profit_percent = take_profit_percent
                new_params.risk_management.max_daily_loss = max_daily_loss
                new_params.risk_management.risk_per_trade = risk_per_trade
                new_params.risk_management.max_trades_per_day = max_trades_per_day
                
                new_params.monitoring.enable_health_check = enable_health_check
                new_params.monitoring.health_check_interval = health_check_interval
                new_params.monitoring.enable_performance_tracking = enable_performance_tracking
                new_params.monitoring.log_level = log_level
                
                success = params_manager.save_params(new_params)
            
            if success:
                st.success("✅ 설정이 저장되었습니다!")
                st.caption(f"🕒 저장 시각: {datetime.now().isoformat(timespec='seconds')}")
                
                # 트레이딩 컨트롤에 설정 적용
                trading_control.update_rate_limits(
                    max_requests_per_minute=max_requests_per_minute,
                    max_orders_per_minute=max_orders_per_minute,
                    cooldown_period=cooldown_period
                )
                
            else:
                st.error("❌ 설정 저장 실패")
                
        except Exception as e:
            st.error(f"❌ 설정 저장 중 오류 발생: {e}")

with action_cols[1]:
    if st.button("🔄 기본값으로 초기화", use_container_width=True):
        if st.warning("정말로 기본값으로 초기화하시겠습니까?"):
            try:
                # 기본 파라미터 생성
                from engine.params import create_params_from_template
                
                default_params = create_params_from_template(
                    user_id=user_id,
                    strategy_type=StrategyType.MACD,
                    ticker="BTC",
                    interval="minute5"
                )
                
                success = params_manager.save_params(default_params)
                
                if success:
                    st.success("✅ 기본값으로 초기화 완료")
                    st.rerun()
                else:
                    st.error("❌ 초기화 실패")
                    
            except Exception as e:
                st.error(f"❌ 초기화 중 오류 발생: {e}")

# --- 설정 미리보기 ---
if existing_params:
    st.subheader("📋 현재 설정 미리보기")
    
    config_info = {
        "거래 모드": existing_params.execution.trading_mode.value,
        "종목": existing_params.ticker,
        "간격": existing_params.interval,
        "최대 포지션": f"{existing_params.risk_management.max_position_size * 100:.0f}%",
        "손절": f"{existing_params.risk_management.stop_loss_percent * 100:.1f}%",
        "익절": f"{existing_params.risk_management.take_profit_percent * 100:.1f}%",
        "최대 낙폭": f"{existing_params.risk_management.max_drawdown * 100:.1f}%",
        "서킷 브레이커": "활성" if existing_params.execution.enable_circuit_breaker else "비활성",
        "로그 레벨": existing_params.monitoring.log_level
    }
    
    # 2열로 표시
    col1, col2 = st.columns(2)
    
    with col1:
        for i, (key, value) in enumerate(list(config_info.items())[:len(config_info)//2]):
            st.markdown(f"**{key}**: {value}")
    
    with col2:
        for i, (key, value) in enumerate(list(config_info.items())[len(config_info)//2:]):
            st.markdown(f"**{key}**: {value}")

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
    if st.button("🎯 전략 설정", use_container_width=True):
        next_page = "set_buy_sell_conditions"
        params = urlencode({"virtual_krw": virtual_krw, "user_id": user_id})
        st.markdown(
            f'<meta http-equiv="refresh" content="0; url=./{next_page}?{params}">',
            unsafe_allow_html=True,
        )
        st.switch_page(next_page)