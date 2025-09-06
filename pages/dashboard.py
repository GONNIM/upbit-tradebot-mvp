# FINAL CODE
# pages/dashboard.py

import json
import streamlit as st
import pandas as pd
import time
import logging
from urllib.parse import urlencode
from streamlit_autorefresh import st_autorefresh
from datetime import datetime, timedelta

from engine.engine_manager import engine_manager
from engine.params import load_params, get_params_manager
from engine.global_state import get_global_state_manager
from services.health_monitor import get_health_status

from services.db import (
    get_account,
    get_coin_balance,
    get_initial_krw,
    fetch_recent_orders,
    fetch_logs,
    insert_log,
    get_last_status_log_from_db,
    fetch_latest_log_signal,
    get_db_manager,
)

from config import PARAMS_JSON_FILENAME, REFRESH_INTERVAL, CONDITIONS_JSON_FILENAME
from ui.style import style_main

from core.trader import UpbitTrader
from services.trading_control import force_liquidate, force_buy_in

from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ✅ 쿼리 파라미터 처리
params = st.query_params
user_id = params.get("user_id", "")
virtual_krw = int(params.get("virtual_krw", 0))

# ✅ 페이지 설정
st.set_page_config(page_title="Upbit Trade Bot v2 - Dashboard", page_icon="📊", layout="wide")
st.markdown(style_main, unsafe_allow_html=True)
st.session_state.setdefault("user_id", user_id)
st.session_state.setdefault("virtual_krw", virtual_krw)

if "engine_started" not in st.session_state:
    st.session_state.engine_started = False

# ✅ 전역 상태 관리자 초기화
global_state_manager = get_global_state_manager()

def style_metric_cards():
    st.markdown(
        """
        <style>
        /* metric 카드 배경/글자색 다크모드/라이트모드 대응 */
        [data-testid="stMetric"] {
            background-color: var(--background-color);
            border-radius: 0.5em;
            padding: 1em;
            margin: 0.5em 0;
            color: var(--text-color);
            border: 1px solid #44444422;
        }
        /* 라이트모드 */
        @media (prefers-color-scheme: light) {
          [data-testid="stMetric"] {
            background-color: #f7f7f7;
            color: #222;
          }
        }
        /* 다크모드 */
        @media (prefers-color-scheme: dark) {
          [data-testid="stMetric"] {
            background-color: #22272b;
            color: #f7f7f7;
          }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

# --- UI 스타일 ---
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
    /* 실시간 업데이트 애니메이션 */
    @keyframes pulse {
        0% { opacity: 1; }
        50% { opacity: 0.7; }
        100% { opacity: 1; }
    }
    .live-indicator {
        animation: pulse 2s infinite;
        color: #00ff00;
        font-weight: bold;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ✅ 자동 새로고침
st_autorefresh(interval=REFRESH_INTERVAL * 1000, key="dashboard_autorefresh")

# ✅ 현재 엔진 상태
engine_status = engine_manager.is_running(user_id)

# ✅ 상단 정보
st.markdown(f"### 📊 Dashboard - `{user_id}`")
st.markdown(f"🕒 현재 시각: {time.strftime('%Y-%m-%d %H:%M:%S')}")

# 🏥 헬스 상태 표시
col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
with col1:
    st.info("Upbit Trade Bot v2 상태 모니터링 페이지입니다.")
    
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

# ✅ 최종 로그 표시
last_log = get_last_status_log_from_db(user_id)
st.info(last_log)

# 엔진 상태 메트릭
status_color = "🟢" if engine_status else "🔴"
st.metric(
    "트레이딩 엔진 상태", "Running" if engine_status else "Stopped", status_color
)

style_metric_cards()

# 로그아웃 버튼
logout = st.button("로그아웃하기", use_container_width=True)
if logout:
    st.markdown(
        f'<meta http-equiv="refresh" content="0; url=/?redirected=1">',
        unsafe_allow_html=True,
    )

# ✅ 실행되지 않았을 경우: 실행 버튼 표시
if not engine_status:
    start_trading = st.button(
        "🚀 트레이딩 엔진 시작", use_container_width=True
    )
    if start_trading:
        if not st.session_state.get("engine_started", False):
            if not engine_manager.is_running(user_id):
                st.write("🔄 엔진 실행을 시작합니다...")
                success = engine_manager.start_engine(user_id, test_mode=True)
                if success:
                    insert_log(user_id, "INFO", "✅ 트레이딩 엔진 실행됨")
                    st.session_state.engine_started = True
                    st.success("🟢 트레이딩 엔진 실행됨, 새로고침 합니다...")
                    st.rerun()
                else:
                    st.warning("⚠️ 트레이딩 엔진 실행 실패")
            else:
                st.info("📡 트레이딩 엔진이 이미 실행 중입니다.")
        else:
            st.info("📡 트레이딩 엔진이 이미 실행 중입니다.")
    st.stop()

st.divider()

# 📊 포지션 및 잔고 정보 표시
st.subheader("💰 포지션 및 잔고 현황")

try:
    # 전역 상태에서 실시간 정보 가져오기
    user_state = global_state_manager.get_user_state(user_id)
    
    if user_state:
        positions = user_state.get('positions', {})
        account = user_state.get('account', {})
        
        # 포지션 정보
        if positions:
            for symbol, pos_data in positions.items():
                pos_cols = st.columns(4)
                with pos_cols[0]:
                    st.metric(f"📈 {symbol}", f"{pos_data.get('quantity', 0):.6f}")
                with pos_cols[1]:
                    avg_price = pos_data.get('avg_price', 0)
                    st.metric("평균 단가", f"{avg_price:,.0f} KRW")
                with pos_cols[2]:
                    current_price = pos_data.get('current_price', 0)
                    if current_price > 0:
                        pnl = (current_price - avg_price) * pos_data.get('quantity', 0)
                        st.metric("평가 손익", f"{pnl:,.0f} KRW")
                    else:
                        st.metric("평가 손익", "N/A")
                with pos_cols[3]:
                    unrealized_pnl_pct = pos_data.get('unrealized_pnl_pct', 0)
                    st.metric("수익률", f"{unrealized_pnl_pct:.2f}%")
        else:
            st.info("보유 포지션이 없습니다.")
        
        # 계좌 정보
        if account:
            account_cols = st.columns(3)
            with account_cols[0]:
                krw_balance = account.get('krw_balance', 0)
                st.metric("KRW 잔고", f"{krw_balance:,.0f} KRW")
            with account_cols[1]:
                total_balance = account.get('total_balance', 0)
                initial_balance = account.get('initial_balance', 0)
                if initial_balance > 0:
                    total_return = ((total_balance - initial_balance) / initial_balance) * 100
                    st.metric("총 자산", f"{total_balance:,.0f} KRW", f"{total_return:.2f}%")
                else:
                    st.metric("총 자산", f"{total_balance:,.0f} KRW")
            with account_cols[2]:
                available_margin = account.get('available_margin', 0)
                st.metric("가용 마진", f"{available_margin:,.0f} KRW")
    
except Exception as e:
    st.error(f"포지션 정보 조회 오류: {e}")

st.divider()

# ✅ 파라미터 로드
json_path = f"{user_id}_{PARAMS_JSON_FILENAME}"
params_obj = load_params(json_path)
if not params_obj:
    st.error("파라미터 설정을 찾을 수 없습니다.")
    st.stop()

account_krw = get_account(user_id) or 0
coin_balance = get_coin_balance(user_id, params_obj.upbit_ticker) or 0.0

# ✅ 자산 현황 (기존 방식과 통합)
st.subheader("📊 자산 현황")
initial_krw = get_initial_krw(user_id) or 0
if account_krw:
    total_value = account_krw
    roi = ((total_value - initial_krw) / initial_krw) * 100 if initial_krw else 0.0
    roi_msg = f"{roi:.2f} %"
else:
    roi_msg = "미정"

col_krw, col_coin, col_pnl = st.columns(3)
with col_krw:
    st.metric("보유 KRW", f"{account_krw:,.0f} KRW")
with col_coin:
    st.metric(f"{params_obj.upbit_ticker} 보유량", f"{coin_balance:,.6f}")
with col_pnl:
    st.metric("📈 누적 수익률", roi_msg)

st.divider()

# ✅ 주문 및 체결 내역
st.subheader("📋 주문 및 체결 내역")

try:
    # 전역 상태에서 주문 정보 가져오기
    orders = user_state.get('orders', {}) if user_state else {}
    
    if orders:
        # 활성 주문
        active_orders = {k: v for k, v in orders.items() if v.get('status') in ['pending', 'open']}
        if active_orders:
            st.subheader("🔄 활성 주문")
            for order_id, order_data in active_orders.items():
                order_cols = st.columns(5)
                with order_cols[0]:
                    st.write(f"**{order_id[:8]}...**")
                with order_cols[1]:
                    side = order_data.get('side', 'N/A')
                    if side == 'buy':
                        st.success("매수")
                    else:
                        st.error("매도")
                with order_cols[2]:
                    st.write(f"{order_data.get('quantity', 0):.6f}")
                with order_cols[3]:
                    st.write(f"{order_data.get('price', 0):,.0f} KRW")
                with order_cols[4]:
                    st.write(order_data.get('status', 'N/A'))
        else:
            st.info("활성 주문이 없습니다.")
    
except Exception as e:
    st.error(f"주문 정보 조회 오류: {e}")

# ✅ 최근 거래 내역 (DB에서)
st.subheader("📝 최근 거래 내역")
recent_orders = fetch_recent_orders(user_id, limit=50)
if recent_orders:
    show_orders = st.toggle("📝 최근 거래 내역 보기", value=False)
    if show_orders:
        df_orders = pd.DataFrame(
            recent_orders,
            columns=["시간", "코인", "매매", "가격", "수량", "상태", "현재금액", "보유코인"],
        )

        # 시간 포맷
        df_orders["시간"] = pd.to_datetime(df_orders["시간"]).dt.strftime("%Y-%m-%d %H:%M:%S")

        # 현재금액 숫자 변환
        df_orders["_현재금액_숫자"] = (
            df_orders["현재금액"]
            .astype(str)
            .str.replace(",", "")
            .str.replace(" KRW", "")
            .replace("", "0")
            .astype(float)
        )
        df_orders["_가격_숫자"] = df_orders["가격"].astype(float)

        # 손익 / 수익률 계산
        def calc_profit(row):
            if row["매매"] == "BUY":
                return "-", "-"
            elif row["매매"] == "SELL":
                current_amount = row["_현재금액_숫자"]
                profit = current_amount - initial_krw
                try:
                    profit_rate = (profit / initial_krw) * 100
                except ZeroDivisionError:
                    profit_rate = 0
                return profit, profit_rate
            else:
                return "-", "-"

        df_orders[["손익", "수익률(%)"]] = df_orders.apply(
            lambda row: pd.Series(calc_profit(row)), axis=1
        )

        df_orders["가격"] = df_orders["_가격_숫자"].map(lambda x: f"{x:,.0f} KRW")
        df_orders["현재금액"] = df_orders["_현재금액_숫자"].map(lambda x: f"{x:,.0f} KRW")
        df_orders["보유코인"] = df_orders["보유코인"].map(lambda x: f"{float(x):.6f}")
        df_orders["손익"] = df_orders["손익"].apply(
            lambda x: f"{x:,.0f} KRW" if isinstance(x, (int, float)) else x
        )
        df_orders["수익률(%)"] = df_orders["수익률(%)"].apply(
            lambda x: f"{x:.2f}%" if isinstance(x, (int, float)) else x
        )

        # 불필요 컬럼 제거
        df_orders = df_orders.drop(columns=["_가격_숫자", "_현재금액_숫자"])

        st.dataframe(df_orders, use_container_width=True, hide_index=True)
else:
    st.info("최근 거래 내역이 없습니다.")

st.divider()

# ✅ 시그널 타임라인
st.subheader("📈 시그널 타임라인")

try:
    # 전역 상태에서 시그널 정보 가져오기
    signals = user_state.get('signals', []) if user_state else []
    
    if signals:
        # 최신 시그널 10개 표시
        recent_signals = signals[-10:]
        
        for signal in recent_signals:
            signal_cols = st.columns([2, 1, 1, 2])
            with signal_cols[0]:
                timestamp = signal.get('timestamp', 'N/A')
                if isinstance(timestamp, datetime):
                    timestamp = timestamp.strftime("%Y-%m-%d %H:%M:%S")
                st.write(f"**{timestamp}**")
            with signal_cols[1]:
                signal_type = signal.get('signal_type', 'N/A')
                if signal_type == 'BUY':
                    st.success(signal_type)
                elif signal_type == 'SELL':
                    st.error(signal_type)
                else:
                    st.info(signal_type)
            with signal_cols[2]:
                st.write(signal.get('symbol', 'N/A'))
            with signal_cols[3]:
                reason = signal.get('reason', 'N/A')
                strength = signal.get('strength', 0)
                st.write(f"{reason} (강도: {strength:.2f})")
    else:
        st.info("최근 시그널이 없습니다.")
    
except Exception as e:
    st.error(f"시그널 정보 조회 오류: {e}")

# ✅ 최종 시그널 정보 (기존 방식)
log_summary = fetch_latest_log_signal(user_id, params_obj.upbit_ticker)
if log_summary:
    st.subheader("📌 최종 시그널 정보")
    cols = st.columns(6)
    cols[0].markdown(f"**시간**<br>{log_summary['시간']}", unsafe_allow_html=True)
    cols[1].markdown(f"**Ticker**<br>{log_summary['Ticker']}", unsafe_allow_html=True)
    cols[2].markdown(f"**Price**<br>{log_summary['price']}", unsafe_allow_html=True)
    cols[3].markdown(f"**Cross**<br>{log_summary['cross']}", unsafe_allow_html=True)
    cols[4].markdown(f"**MACD**<br>{log_summary['macd']}", unsafe_allow_html=True)
    cols[5].markdown(f"**Signal**<br>{log_summary['signal']}", unsafe_allow_html=True)

st.divider()

# ✅ 엔진 상태 상세 정보
st.subheader("🔧 엔진 상태 상세 정보")

try:
    engine_threads = global_state_manager.get_engine_threads()
    if user_id in engine_threads:
        user_engine = engine_threads[user_id]
        
        engine_cols = st.columns(4)
        with engine_cols[0]:
            status = user_engine.get('status', 'unknown')
            if status == 'running':
                st.success(f"상태: {status}")
            else:
                st.error(f"상태: {status}")
        
        with engine_cols[1]:
            last_update = user_engine.get('last_update', 'N/A')
            if isinstance(last_update, datetime):
                last_update = last_update.strftime("%Y-%m-%d %H:%M:%S")
            st.info(f"마지막 업데이트: {last_update}")
        
        with engine_cols[2]:
            strategy = user_engine.get('strategy', 'N/A')
            st.info(f"전략: {strategy}")
        
        with engine_cols[3]:
            symbol = user_engine.get('symbol', 'N/A')
            st.info(f"종목: {symbol}")
        
        # 성능 메트릭
        performance = user_engine.get('performance', {})
        if performance:
            st.subheader("📊 성능 메트릭")
            perf_cols = st.columns(4)
            with perf_cols[0]:
                total_trades = performance.get('total_trades', 0)
                st.metric("총 거래 수", total_trades)
            with perf_cols[1]:
                win_rate = performance.get('win_rate', 0)
                st.metric("승률", f"{win_rate:.1f}%")
            with perf_cols[2]:
                total_pnl = performance.get('total_pnl', 0)
                st.metric("총 손익", f"{total_pnl:,.0f} KRW")
            with perf_cols[3]:
                sharpe_ratio = performance.get('sharpe_ratio', 0)
                st.metric("샤프 비율", f"{sharpe_ratio:.2f}")
    
    else:
        st.info("엔진 실행 중이 아님")
        
except Exception as e:
    st.error(f"엔진 상태 조회 오류: {e}")

st.divider()

# ✅ 로그 뷰
st.subheader("📚 로그 뷰")

# 로그 필터링 옵션
log_filter = st.selectbox("로그 레벨 필터", ["ALL", "INFO", "BUY", "SELL", "ERROR", "WARNING"], key="log_filter")

# 로그 조회
if log_filter == "ALL":
    logs = fetch_logs(user_id, limit=100)
else:
    logs = fetch_logs(user_id, level=log_filter, limit=100)

if logs:
    # 이모지 처리 함수
    def emoji_cross(msg: str):
        if "cross=Golden" in msg:
            return "🟢 " + msg
        elif "cross=Dead" in msg:
            return "🔴 " + msg
        elif "cross=Up" in msg or "cross=Pending" in msg:
            return "🔵 " + msg
        elif "cross=Down" in msg:
            return "🟣 " + msg
        elif "cross=Neutral" in msg:
            return "⚪ " + msg
        return msg
    
    df_logs = pd.DataFrame(logs, columns=["시간", "레벨", "메시지"])
    df_logs["시간"] = pd.to_datetime(df_logs["시간"]).dt.strftime("%Y-%m-%d %H:%M:%S")
    df_logs["메시지"] = df_logs["메시지"].apply(emoji_cross)
    
    show_logs = st.toggle(f"📚 {log_filter} 로그 보기", value=log_filter == "ERROR")
    if show_logs:
        st.dataframe(
            df_logs,
            use_container_width=True,
            hide_index=True,
            column_config={
                "시간": st.column_config.Column(width="small"),
                "레벨": st.column_config.Column(width="small"),
                "메시지": st.column_config.Column(width="large"),
            },
        )
else:
    st.info(f"{log_filter} 로그가 없습니다.")

st.divider()

# ✅ 제어 기능
st.subheader("⚙️ 제어 기능")

btn_col1, btn_col2, btn_col3, btn_col4 = st.columns([1, 1, 1, 1])
with btn_col1:
    if st.button("🛑 강제매수", use_container_width=True):
        if account_krw > 0 and coin_balance == 0:
            trader = UpbitTrader(
                user_id, risk_pct=params_obj.order_ratio, test_mode=True
            )
            msg = force_buy_in(user_id, trader, params_obj.upbit_ticker)
            st.success(msg)
        else:
            st.warning("매수 조건 불충족")
with btn_col2:
    if st.button("🛑 강제매도", use_container_width=True):
        if account_krw == 0 and coin_balance > 0:
            trader = UpbitTrader(
                user_id, risk_pct=params_obj.order_ratio, test_mode=True
            )
            msg = force_liquidate(user_id, trader, params_obj.upbit_ticker)
            st.success(msg)
        else:
            st.warning("매도 조건 불충족")
with btn_col3:
    if st.button("🛑 엔진 종료", use_container_width=True):
        engine_manager.stop_engine(user_id)
        insert_log(user_id, "INFO", "🛑 트레이딩 엔진 수동 종료됨")
        st.session_state.engine_started = False
        time.sleep(0.2)
        st.rerun()
with btn_col4:
    if st.button("💥 시스템 초기화", use_container_width=True):
        params = urlencode({"virtual_krw": virtual_krw, "user_id": user_id})
        st.markdown(
            f'<meta http-equiv="refresh" content="0; url=./confirm_init_db?{params}">',
            unsafe_allow_html=True,
        )

st.divider()

# ✅ 파라미터 설정값
st.subheader("⚙️ 파라미터 설정값")
from ui.sidebar import INTERVAL_OPTIONS

def get_interval_label(interval_code: str) -> str:
    for label, code in INTERVAL_OPTIONS.items():
        if code == interval_code:
            return label
    return "알 수 없음"

st.markdown(
    f"""
    <div style="padding: 1em; border-radius: 0.5em; background-color: #f0f2f6; color: #111; border: 1px solid #ccc; font-size: 16px; font-weight: 500">
        <b>Ticker:</b> {params_obj.ticker} &nbsp;|&nbsp;
        <b>Interval:</b> {get_interval_label(params_obj.interval)} &nbsp;|&nbsp;
        <b>Strategy:</b> {params_obj.strategy.strategy_type.value} &nbsp;|&nbsp;
        <b>Order 비율:</b> {params_obj.order_ratio*100:.0f}% &nbsp;|&nbsp;
        <b>Cash:</b> {params_obj.cash:,.0f} KRW
    </div>
    """,
    unsafe_allow_html=True,
)