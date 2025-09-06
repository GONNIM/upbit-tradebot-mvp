# FINAL CODE
# app.py

from urllib.parse import urlencode
import streamlit as st
import streamlit_authenticator as stauth
from ui.style import style_main
from config import MIN_CASH
from services.db import get_user, save_user
from services.init_db import reset_db
import os
import yaml
from yaml.loader import SafeLoader
from services.init_db import init_db_if_needed
from services.health_monitor import start_health_monitoring, get_health_status
from engine.global_state import get_global_state_manager
from ui.sidebar import make_sidebar
from engine.params import get_params_manager
import threading
import time

# Setup page
st.set_page_config(page_title="Upbit Trade Bot v2", page_icon="🤖", layout="wide")
st.markdown(style_main, unsafe_allow_html=True)

IS_CLOUD = st.secrets.get("environment") == "cloud"

# 환경별 인증 정보 로딩
if IS_CLOUD:
    # Streamlit Cloud 환경: secrets.toml 사용
    config = {
        "cookie": {
            "expiry_days": st.secrets.cookie_expiry_days,
            "key": st.secrets.cookie_key,
            "name": st.secrets.cookie_name,
        },
        "credentials": {
            # 💥 deepcopy 사용하지 말고 dict로 명시적으로 재구성
            "usernames": {k: dict(v) for k, v in st.secrets.usernames.items()}
        },
    }
else:
    # 로컬 환경: credentials.yaml 사용
    with open("credentials.yaml") as file:
        raw_config = yaml.load(file, Loader=SafeLoader)
        config = {
            "cookie": {
                "expiry_days": raw_config["cookie"]["expiry_days"],
                "key": raw_config["cookie"]["key"],
                "name": raw_config["cookie"]["name"],
            },
            "credentials": {"usernames": dict(raw_config["credentials"]["usernames"])},
        }

authenticator = stauth.Authenticate(
    config["credentials"],
    config["cookie"]["name"],
    config["cookie"]["key"],
    config["cookie"]["expiry_days"],
)

# 로그인 UI
login_placeholder = st.empty()
with login_placeholder.container():
    authenticator.login(
        "main",
        fields={
            "Form name": "로그인",
            "Username": "아이디",
            "Password": "비밀번호",
            "Login": "로그인",
        },
    )

authentication_status = st.session_state.get("authentication_status")
name = st.session_state.get("name")
username = st.session_state.get("username")

# 로그인 분기 처리
if authentication_status is False:
    st.error("아이디 또는 비밀번호가 올바르지 않습니다.")
elif authentication_status is None:
    st.warning("아이디와 비밀번호를 입력해 주세요.")
elif authentication_status:
    login_placeholder.empty()
    st.success(f"환영합니다, {name}님!")

    # 2025-08-04 DB 분리
    init_db_if_needed(username)
    
    # 🏥 24시간 운영: 헬스 모니터링 자동 시작
    start_health_monitoring()

    # 초기 세션 설정
    st.session_state.setdefault("user_id", username)
    st.session_state.setdefault("virtual_krw", 0)
    st.session_state.setdefault("virtual_over", False)
    st.session_state.setdefault("order_ratio", 1.0)
    st.session_state.setdefault("order_amount", 0)
    st.session_state.setdefault("virtual_amount", 0)
    
    # 전역 상태 관리자 초기화
    global_state_manager = get_global_state_manager()
    
    # 🔧 세션 상태 초기화
    if "virtual_amount" not in st.session_state:
        st.session_state.virtual_amount = 0
    
    # 사이드바 렌더링 및 파라미터 로드
    sidebar_params = make_sidebar(username)
    
    # 🏥 헬스 상태 표시 (상단 바)
    col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
    
    with col1:
        st.title(f"🤖 Upbit Trade Bot v2 - {name}")
    
    with col2:
        health_status = get_health_status()
        if health_status.get('status') == 'healthy':
            st.success("✅ 시스템 정상")
        else:
            st.error("⚠️ 시스템 경고")
    
    with col3:
        cpu_usage = health_status.get('cpu_usage_percent', 0)
        st.info(f"🖥️ CPU: {cpu_usage:.1f}%")
    
    with col4:
        memory_mb = health_status.get('memory_usage_mb', 0)
        st.info(f"💾 메모리: {memory_mb:.1f}MB")
    
    # 🔍 엔진 상태 정보 표시
    with st.expander("🔧 엔진 상태 정보", expanded=False):
        try:
            engine_threads = global_state_manager.get_engine_threads()
            active_engines = len([t for t in engine_threads.values() 
                                if t.get('thread', {}).is_alive()])
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("활성 엔진", active_engines)
            with col2:
                st.metric("전체 엔진", len(engine_threads))
            with col3:
                uptime_hours = health_status.get('uptime_hours', 0)
                st.metric("가동 시간", f"{uptime_hours:.1f}h")
            
            # 사용자별 상태 정보
            if username in engine_threads:
                user_engine = engine_threads[username]
                st.subheader(f"👤 {username} 엔진 상태")
                
                status_cols = st.columns(4)
                with status_cols[0]:
                    status = user_engine.get('status', 'unknown')
                    if status == 'running':
                        st.success("상태: 실행 중")
                    elif status == 'stopped':
                        st.error("상태: 중지")
                    else:
                        st.warning(f"상태: {status}")
                
                with status_cols[1]:
                    last_update = user_engine.get('last_update', 'N/A')
                    st.info(f"마지막 업데이트: {last_update}")
                
                with status_cols[2]:
                    strategy = user_engine.get('strategy', 'N/A')
                    st.info(f"전략: {strategy}")
                
                with status_cols[3]:
                    symbol = user_engine.get('symbol', 'N/A')
                    st.info(f"종목: {symbol}")
                
                # 포지션 및 주문 정보
                positions = user_engine.get('positions', {})
                orders = user_engine.get('orders', {})
                
                if positions:
                    st.subheader("📊 포지션 정보")
                    for symbol, pos_data in positions.items():
                        pos_cols = st.columns(3)
                        with pos_cols[0]:
                            st.write(f"**{symbol}**")
                        with pos_cols[1]:
                            st.write(f"수량: {pos_data.get('quantity', 0)}")
                        with pos_cols[2]:
                            st.write(f"평균가: {pos_data.get('avg_price', 0):,.0f}")
                
                if orders:
                    st.subheader("📋 주문 정보")
                    for order_id, order_data in orders.items():
                        order_cols = st.columns(4)
                        with order_cols[0]:
                            st.write(f"**{order_id[:8]}...**")
                        with order_cols[1]:
                            st.write(f"{order_data.get('side', 'N/A')}")
                        with order_cols[2]:
                            st.write(f"{order_data.get('quantity', 0)}")
                        with order_cols[3]:
                            status = order_data.get('status', 'N/A')
                            if status == 'filled':
                                st.success("체결")
                            else:
                                st.info(status)
                
            else:
                st.info(f"👤 {username} - 엔진 실행 중이 아님")
                
        except Exception as e:
            st.error(f"엔진 상태 조회 오류: {e}")
    
    # 📊 사용자 정보 및 자산 현황
    user_info = get_user(username)
    
    st.subheader("👤 사용자 정보")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.write(f"**사용자 ID**: {username}")
    
    with col2:
        if user_info:
            _, virtual_krw, _ = user_info
            st.write(f"**가상 자산**: {virtual_krw:,.0f} KRW")
            st.session_state.virtual_amount = virtual_krw
        else:
            st.write("**가상 자산**: 미설정")
    
    with col3:
        st.write(f"**주문 비율**: {st.session_state.order_ratio * 100:.0f}%")
        st.session_state.order_amount = st.session_state.virtual_amount * st.session_state.order_ratio
        st.write(f"**주문 금액**: {st.session_state.order_amount:,.0f} KRW")
    
    # 🎯 액션 버튼
    st.markdown("---")
    
    action_cols = st.columns(3)
    
    with action_cols[0]:
        if st.button("📊 대시보드", use_container_width=True):
            next_page = "dashboard"
            params = urlencode({
                "virtual_krw": st.session_state.virtual_krw,
                "user_id": st.session_state.user_id,
            })
            st.markdown(
                f'<meta http-equiv="refresh" content="0; url=./{next_page}?{params}">',
                unsafe_allow_html=True,
            )
            st.switch_page(next_page)
    
    with action_cols[1]:
        if st.button("⚙️ 시스템 설정", use_container_width=True):
            next_page = "set_config"
            params = urlencode({
                "virtual_krw": st.session_state.virtual_krw,
                "user_id": st.session_state.user_id,
            })
            st.markdown(
                f'<meta http-equiv="refresh" content="0; url=./{next_page}?{params}">',
                unsafe_allow_html=True,
            )
            st.switch_page(next_page)
    
    with action_cols[2]:
        if st.button("🎯 전략 설정", use_container_width=True):
            next_page = "set_buy_sell_conditions"
            params = urlencode({
                "virtual_krw": st.session_state.virtual_krw,
                "user_id": st.session_state.user_id,
            })
            st.markdown(
                f'<meta http-equiv="refresh" content="0; url=./{next_page}?{params}">',
                unsafe_allow_html=True,
            )
            st.switch_page(next_page)
    
    # 📋 최근 활동 로그
    st.subheader("📋 최근 활동")
    try:
        recent_logs = global_state_manager.get_user_logs(username, limit=10)
        if recent_logs:
            for log in recent_logs:
                log_cols = st.columns([2, 1, 3])
                with log_cols[0]:
                    st.write(f"**{log.get('timestamp', 'N/A')}**")
                with log_cols[1]:
                    level = log.get('level', 'INFO')
                    if level == 'ERROR':
                        st.error(level)
                    elif level == 'WARNING':
                        st.warning(level)
                    else:
                        st.info(level)
                with log_cols[2]:
                    st.write(log.get('message', 'N/A'))
        else:
            st.info("최근 활동 내역이 없습니다.")
    except Exception as e:
        st.error(f"로그 조회 오류: {e}")
    
    # 🔧 시스템 제어 (관리자용)
    if st.checkbox("🔧 고급 설정 (관리자)", key="admin_settings"):
        st.warning("⚠️ 관리자 전용 기능입니다. 주의해서 사용하세요.")
        
        admin_cols = st.columns(2)
        
        with admin_cols[0]:
            if st.button("🔄 DB 초기화", use_container_width=True):
                if st.warning("정말로 DB를 초기화하시겠습니까? 모든 데이터가 삭제됩니다."):
                    if reset_db():
                        st.success("DB 초기화 완료")
                    else:
                        st.error("DB 초기화 실패")
        
        with admin_cols[1]:
            if st.button("🔄 파라미터 초기화", use_container_width=True):
                params_manager = get_params_manager()
                if params_manager.delete_params(f"{username}_params.json"):
                    st.success("파라미터 초기화 완료")
                else:
                    st.error("파라미터 초기화 실패")