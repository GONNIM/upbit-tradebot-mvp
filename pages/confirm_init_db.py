# FINAL CODE
# pages/confirm_init_db.py

from urllib.parse import urlencode
import streamlit as st
from datetime import datetime
import os
import shutil
import sqlite3
from pathlib import Path
import time

from config import MIN_CASH
from ui.style import style_main
from services.db import get_db_manager, reset_db, insert_log
from services.init_db import init_db_if_needed
from engine.params import get_params_manager
from services.health_monitor import get_health_status
from engine.engine_manager import engine_manager

# --- 기본 설정 ---
st.set_page_config(page_title="DB 초기화 확인", page_icon="⚠️", layout="centered")
st.markdown(style_main, unsafe_allow_html=True)

# --- URL 파라미터 확인 ---
params = st.query_params
user_id = params.get("user_id", "")
virtual_krw = int(params.get("virtual_krw", 0))

if virtual_krw < MIN_CASH or not user_id:
    st.switch_page("app.py")

# --- UI 스타일 ---
st.markdown(
    """
    <style>
    div.block-container {
        padding-top: 2rem;
        max-width: 800px;
        margin: 0 auto;
    }
    h1 {
        margin-top: 0 !important;
        color: #dc3545;
    }
    .warning-box {
        background-color: #fff3cd;
        border: 1px solid #ffeaa7;
        border-radius: 0.5rem;
        padding: 1.5rem;
        margin: 1rem 0;
    }
    .danger-box {
        background-color: #f8d7da;
        border: 1px solid #f5c6cb;
        border-radius: 0.5rem;
        padding: 1.5rem;
        margin: 1rem 0;
    }
    .success-box {
        background-color: #d4edda;
        border: 1px solid #c3e6cb;
        border-radius: 0.5rem;
        padding: 1.5rem;
        margin: 1rem 0;
    }
    .status-card {
        background-color: #f8f9fa;
        border-radius: 0.5rem;
        padding: 1rem;
        margin: 0.5rem 0;
        border: 1px solid #dee2e6;
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
st.title("⚠️ DB 초기화 확인")
st.markdown(f"**사용자**: {user_id} | **가상 자산**: {virtual_krw:,.0f} KRW")

# --- 시스템 상태 확인 ---
st.subheader("🏥 현재 시스템 상태")

try:
    # 헬스 상태
    health_status = get_health_status()
    col1, col2, col3 = st.columns(3)
    
    with col1:
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

    # DB 상태 확인
    db_manager = get_db_manager()
    db_status = db_manager.get_db_status()
    
    st.subheader("🗄️ 데이터베이스 상태")
    
    with st.expander("📊 DB 상세 정보", expanded=True):
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown(f"""
            <div class="status-card">
                <strong>DB 파일 경로:</strong><br>
                {db_status.get('db_path', 'N/A')}
            </div>
            """, unsafe_allow_html=True)
        
        with col2:
            st.markdown(f"""
            <div class="status-card">
                <strong>DB 파일 크기:</strong><br>
                {db_status.get('file_size', 'N/A')}
            </div>
            """, unsafe_allow_html=True)
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown(f"""
            <div class="status-card">
                <strong>사용자 수:</strong><br>
                {db_status.get('user_count', 0)}명
            </div>
            """, unsafe_allow_html=True)
        
        with col2:
            st.markdown(f"""
            <div class="status-card">
                <strong>마지막 백업:</strong><br>
                {db_status.get('last_backup', '없음')}
            </div>
            """, unsafe_allow_html=True)

except Exception as e:
    st.error(f"시스템 상태 조회 오류: {e}")

# --- 파라미터 상태 확인 ---
st.subheader("⚙️ 파라미터 상태")

try:
    params_manager = get_params_manager()
    user_params_path = f"{user_id}_params.json"
    
    if os.path.exists(user_params_path):
        file_size = os.path.getsize(user_params_path)
        mod_time = datetime.fromtimestamp(os.path.getmtime(user_params_path))
        
        st.success(f"✅ 사용자 파라미터 파일 존재")
        st.markdown(f"""
        <div class="status-card">
            <strong>파일 경로:</strong> {user_params_path}<br>
            <strong>파일 크기:</strong> {file_size:,} bytes<br>
            <strong>마지막 수정:</strong> {mod_time.strftime('%Y-%m-%d %H:%M:%S')}
        </div>
        """, unsafe_allow_html=True)
    else:
        st.warning("⚠️ 사용자 파라미터 파일 없음")
    
    # 모든 파라미터 파일 확인
    params_files = list(Path(".").glob("*_params.json"))
    if params_files:
        st.info(f"📁 총 {len(params_files)}개의 파라미터 파일 발견")
        with st.expander("📋 파라미터 파일 목록"):
            for param_file in params_files:
                file_size = param_file.stat().st_size
                mod_time = datetime.fromtimestamp(param_file.stat().st_mtime)
                st.write(f"- {param_file.name} ({file_size:,} bytes, {mod_time.strftime('%Y-%m-%d %H:%M:%S')})")

except Exception as e:
    st.error(f"파라미터 상태 조회 오류: {e}")

# --- 위험 경고 ---
st.markdown("---")
st.markdown("""
<div class="danger-box">
    <h3>🚨 심각한 경고</h3>
    <p>DB 초기화는 <strong>모든 데이터를 영구적으로 삭제</strong>하는 작업입니다.</p>
    <ul>
        <li>📊 모든 거래 내역이 삭제됩니다</li>
        <li>💰 모든 잔고 정보가 초기화됩니다</li>
        <li>⚙️ 모든 설정값이 초기화됩니다</li>
        <li>📈 모든 시그널 기록이 삭제됩니다</li>
    </ul>
    <p><strong>이 작업은 되돌릴 수 없습니다!</strong></p>
</div>
""", unsafe_allow_html=True)

# --- 안전 확인 절차 ---
st.subheader("🔒 안전 확인 절차")

# 1단계: 사용자 확인
step1_confirmed = st.checkbox(
    "1. DB 초기화의 위험성을 이해하고 모든 데이터가 삭제될 것을 확인합니다.",
    value=False,
    key="step1_confirm"
)

# 2단계: 사용자 ID 확인
step2_input = st.text_input(
    "2. 삭제할 사용자 ID를 정확하게 입력하세요:",
    placeholder="사용자 ID 입력",
    key="step2_input"
)
step2_confirmed = step2_input == user_id

# 3단계: 최종 확인
step3_confirmed = st.checkbox(
    "3. 최종 확인: 정말로 모든 데이터를 삭제하시겠습니까?",
    value=False,
    key="step3_confirm",
    disabled=not (step1_confirmed and step2_confirmed)
)

# --- 초기화 버튼 ---
st.markdown("---")

if step1_confirmed and step2_confirmed and step3_confirmed:
    st.error("🔴 모든 안전 확인이 완료되었습니다. 아래 버튼을 누르면 DB가 초기화됩니다.")
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        if st.button("🗑️ DB 초기화 실행", type="primary", use_container_width=True):
            try:
                with st.spinner("DB 초기화 진행 중..."):
                    # 1. 엔진 정지
                    for uid in engine_manager.get_active_user_ids():
                        engine_manager.stop_engine(uid)
                        insert_log(uid, "INFO", "🛑 시스템 초기화로 엔진 종료됨")
                    
                    time.sleep(1)  # 종료 대기
                    
                    # 2. DB 백업 시도
                    backup_success = db_manager.backup_db()
                    
                    # 3. 사용자 파라미터 백업
                    param_backup_path = None
                    if os.path.exists(user_params_path):
                        param_backup_path = f"{user_params_path}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                        shutil.copy2(user_params_path, param_backup_path)
                    
                    # 4. DB 초기화
                    reset_success = reset_db()
                    
                    # 5. 사용자 파라미터 삭제
                    if os.path.exists(user_params_path):
                        os.remove(user_params_path)
                    
                    if reset_success:
                        st.success("✅ DB 초기화 완료")
                        
                        if backup_success:
                            st.info(f"📦 DB 백업 완료: {db_manager.get_last_backup_path()}")
                        
                        if param_backup_path:
                            st.info(f"📦 파라미터 백업 완료: {param_backup_path}")
                        
                        # 6. 재초기화
                        init_db_if_needed(user_id)
                        
                        st.success("🔄 시스템 재초기화 완료")
                        
                        # 7. 세션 상태 초기화
                        st.session_state.engine_started = False
                        
                        # 8. 메인 페이지로 이동
                        params = urlencode({"virtual_krw": virtual_krw, "user_id": user_id})
                        st.markdown(
                            f'<meta http-equiv="refresh" content="3; url=./app.py?{params}">',
                            unsafe_allow_html=True,
                        )
                        st.info("3초 후 메인 페이지로 이동합니다...")
                    else:
                        st.error("❌ DB 초기화 실패")
                        
            except Exception as e:
                st.error(f"❌ 초기화 중 오류 발생: {e}")
                st.info("시스템 관리자에게 문의하세요.")
    
    with col2:
        st.info("💡 팁: 초기화 후 모든 설정을 다시 구성해야 합니다.")
else:
    st.info("🔒 안전 확인 절차를 모두 완료해야 초기화 버튼이 활성화됩니다.")

# --- 취소 버튼 ---
st.markdown("---")
if st.button("❌ 취소하고 메인으로 돌아가기", use_container_width=True):
    params = urlencode({"virtual_krw": virtual_krw, "user_id": user_id})
    st.markdown(
        f'<meta http-equiv="refresh" content="0; url=./app.py?{params}">',
        unsafe_allow_html=True,
    )

# --- 도움말 ---
with st.expander("📖 도움말"):
    st.markdown("""
    ### DB 초기화란?
    DB 초기화는 모든 사용자 데이터를 삭제하고 시스템을 처음 상태로 되돌리는 작업입니다.
    
    ### 언제 필요한가요?
    - 시스템에 심각한 문제가 발생했을 때
    - 모든 데이터를 완전히 삭제하고 새로 시작하고 싶을 때
    - 테스트 후 깨끗한 상태로 복원하고 싶을 때
    
    ### 주의사항
    - 이 작업은 되돌릴 수 없습니다
    - 초기화 전에 중요한 데이터는 반드시 백업하세요
    - 모든 설정과 거래 내역이 삭제됩니다
    """)
