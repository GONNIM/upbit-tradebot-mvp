import streamlit as st
import pandas as pd
import time
import threading
import logging
from urllib.parse import urlencode
from streamlit_autorefresh import st_autorefresh

from engine.engine_runner import stop_engine, engine_runner_main
from engine.global_state import (
    is_engine_really_running,
    add_engine_thread,
    get_engine_threads,
)
from services.db import (
    get_account,
    get_coin_balance,
    get_initial_krw,
    fetch_recent_orders,
    fetch_logs,
    insert_log,
    get_last_status_log_from_db,
    fetch_latest_log_signal,
)
from engine.params import load_params
from services.init_db import reset_db
from config import PARAMS_JSON_FILENAME, REFRESH_INTERVAL
from ui.style import style_main

from core.trader import UpbitTrader
from services.trading_control import force_liquidate, force_buy_in


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
st.set_page_config(page_title="Upbit Trade Bot v1", page_icon="🤖", layout="wide")
st.markdown(style_main, unsafe_allow_html=True)
st.session_state.setdefault("user_id", user_id)
st.session_state.setdefault("virtual_krw", virtual_krw)

if "engine_started" not in st.session_state:
    st.session_state.engine_started = False


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
    </style>
    """,
    unsafe_allow_html=True,
)

_engine_lock = threading.Lock()

# ✅ 자동 새로고침
st_autorefresh(interval=REFRESH_INTERVAL * 1000, key="dashboard_autorefresh")

# ✅ 현재 엔진 상태
engine_status = is_engine_really_running(user_id)
# logger.info(f"is_engine_really_running {engine_status}")
if not engine_status:
    engine_status = st.session_state.engine_started
    # logger.info(f"st.session_state.engine_started {engine_status}")


# ✅ 상단 정보
st.markdown(f"### 📊 Dashboard - `{user_id}`")
st.markdown(f"🕒 현재 시각: {time.strftime('%Y-%m-%d %H:%M:%S')}")

col1, col2 = st.columns([4, 1])
with col1:
    st.info("Upbit Trade Bot v1 상태 모니터링 페이지입니다.")
    # ✅ 최종 로그 표시
    last_log = get_last_status_log_from_db(user_id)
    # st.markdown("### 🧾 최종 트레이딩 로그")
    # st.code(last_log, language="text")
    st.info(last_log)
with col2:
    status_color = "🟢" if engine_status else "🔴"
    st.metric(
        "트레이딩 엔진 상태", "Running" if engine_status else "Stopped", status_color
    )

style_metric_cards()

logout = st.button("로그아웃하기", use_container_width=True)
if logout:
    st.markdown(
        f'<meta http-equiv="refresh" content="0; url=/?redirected=1">',
        unsafe_allow_html=True,
    )

# ✅ 실행되지 않았을 경우: 실행 버튼 표시
if not engine_status:
    start_trading = st.button(
        "Upbit Trade Bot v1 (TEST) 엔진 실행하기", use_container_width=True
    )
    if start_trading:
        if not st.session_state.get("engine_started", False):
            if not is_engine_really_running(user_id):
                with _engine_lock:
                    if not is_engine_really_running(user_id):
                        st.write("🔄 엔진 실행을 시작합니다...")
                        stop_event = threading.Event()
                        thread = threading.Thread(
                            target=engine_runner_main,
                            kwargs={"user_id": user_id, "stop_event": stop_event},
                            daemon=True,
                        )
                        thread.start()
                        add_engine_thread(user_id, thread, stop_event)
                        insert_log(user_id, "INFO", "✅ 트레이딩 엔진 실행됨")
                        st.session_state.engine_started = True
                        st.success("🟢 트레이딩 엔진 실행됨, 새로고침 합니다...")
                        st.rerun()
            else:
                st.info("📡 트레이딩 엔진이 이미 실행 중입니다.")
        else:
            st.info("📡 트레이딩 엔진이 이미 실행 중입니다.")
    st.stop()

st.divider()

json_path = f"{user_id}_{PARAMS_JSON_FILENAME}"
params_obj = load_params(json_path)
account_krw = get_account(user_id) or 0
# st.write(account_krw)
coin_balance = get_coin_balance(user_id, params_obj.upbit_ticker) or 0.0

# ✅ 실행된 경우: 제어 및 모니터링 UI 출력
# ✅ 제어 버튼
btn_col1, btn_col2, btn_col3, btn_col4 = st.columns([1, 1, 1, 1])
with btn_col1:
    if st.button("🛑 강제매수하기", use_container_width=True):
        if account_krw > 0 and coin_balance == 0:
            trader = UpbitTrader(
                user_id, risk_pct=params_obj.order_ratio, test_mode=True
            )
            msg = force_buy_in(user_id, trader, params_obj.upbit_ticker)
            st.success(msg)
with btn_col2:
    if st.button("🛑 강제매도하기", use_container_width=True):
        if account_krw == 0 and coin_balance > 0:
            trader = UpbitTrader(
                user_id, risk_pct=params_obj.order_ratio, test_mode=True
            )
            msg = force_liquidate(user_id, trader, params_obj.upbit_ticker)
            st.success(msg)
with btn_col3:
    if st.button("🛑 트레이딩 엔진 종료", use_container_width=True):
        stop_engine(user_id)
        st.session_state.engine_started = False  # ✅ 수동 초기화
        time.sleep(0.2)
        st.rerun()
with btn_col4:
    if st.button("💥 시스템 초기화", use_container_width=True):
        active_threads = get_engine_threads()
        for uid in list(active_threads.keys()):
            stop_engine(uid)  # ✅ 정상 종료 처리
            insert_log(uid, "INFO", "🛑 시스템 초기화로 엔진 종료됨")

        time.sleep(1)  # 종료 대기
        reset_db()

        st.session_state.engine_started = False  # ✅ 캐시 초기화
        st.success("DB 초기화 완료")

        params = urlencode({"virtual_krw": virtual_krw, "user_id": user_id})
        st.markdown(
            f'<meta http-equiv="refresh" content="0; url=./set_config?{params}">',
            unsafe_allow_html=True,
        )


# ✅ params 요약 상단 카드 표시
st.subheader("⚙️ 파라미터 설정값")
from ui.sidebar import INTERVAL_OPTIONS


def get_interval_label(interval_code: str) -> str:
    """
    내부 interval 코드(minute1 등) → 한글 라벨(1분봉 등) 반환
    예: "minute1" → "1분봉"
    """
    for label, code in INTERVAL_OPTIONS.items():
        if code == interval_code:
            return label
    return "알 수 없음"


def get_signal_confirm_enabled() -> str:
    if params_obj.signal_confirm_enabled:
        return "사용"
    return "미사용"


st.markdown(
    f"""
    <div style="padding: 1em; border-radius: 0.5em; background-color: #f0f2f6; color: #111; border: 1px solid #ccc; font-size: 16px; font-weight: 500">
        <b>Ticker:</b> {params_obj.ticker} &nbsp;|&nbsp;
        <b>Interval:</b> {get_interval_label(params_obj.interval)} &nbsp;|&nbsp;
        <b>MACD:</b> Fast={params_obj.fast_period}, Slow={params_obj.slow_period}, Signal={params_obj.signal_period}, 기준값={params_obj.macd_threshold} &nbsp;|&nbsp;
        <b>TP/SL:</b> {params_obj.take_profit*100:.1f}% / {params_obj.stop_loss*100:.1f}% &nbsp;|&nbsp;
        <b>Order 비율:</b> {params_obj.order_ratio*100:.0f}% &nbsp;|&nbsp;
        <b>최소 진입 Bar:</b> {params_obj.min_holding_period} &nbsp;|&nbsp;
        <b>Cross Over:</b> {params_obj.macd_crossover_threshold}
    </div>
    <div style="margin-top: .2rem; padding: 1em; border-radius: 0.5em; background-color: #f0f2f6; color: #111; border: 1px solid #ccc; font-size: 16px; font-weight: 500">
        <b>MACD 기준선 통과 매매 타점:</b> < {get_signal_confirm_enabled()} >
    </div>
    """,
    unsafe_allow_html=True,
)
st.write("")


# ✅ 자산 현황
st.subheader("💰 자산 현황")
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


# ✅ 최근 거래 내역
st.subheader("📝 최근 거래 내역")
orders = fetch_recent_orders(user_id, limit=10)
if orders:
    df_orders = pd.DataFrame(
        orders, columns=["시간", "코인", "매매", "가격", "수량", "상태"]
    )
    df_orders["시간"] = pd.to_datetime(df_orders["시간"]).dt.strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    st.dataframe(df_orders, use_container_width=True, hide_index=True)
else:
    st.info("최근 거래 내역이 없습니다.")

buy_logs = fetch_logs(user_id, level="BUY", limit=10)
if buy_logs:
    st.subheader("🚨 매수 로그")
    df_buy = pd.DataFrame(buy_logs, columns=["시간", "레벨", "메시지"])
    df_buy["시간"] = pd.to_datetime(df_buy["시간"]).dt.strftime("%Y-%m-%d %H:%M:%S")
    st.dataframe(
        # df_buy[::-1],  # 최신 순
        df_buy,
        use_container_width=True,
        hide_index=True,
        column_config={
            "시간": st.column_config.Column(width="small"),
            "레벨": st.column_config.Column(width="small"),
            "메시지": st.column_config.Column(width="large"),
        },
    )

sell_logs = fetch_logs(user_id, level="SELL", limit=10)
if sell_logs:
    st.subheader("🚨 매도 로그")
    df_sell = pd.DataFrame(sell_logs, columns=["시간", "레벨", "메시지"])
    df_sell["시간"] = pd.to_datetime(df_sell["시간"]).dt.strftime("%Y-%m-%d %H:%M:%S")
    st.dataframe(
        # df_sell[::-1],  # 최신 순
        df_sell,
        use_container_width=True,
        hide_index=True,
        column_config={
            "시간": st.column_config.Column(width="small"),
            "레벨": st.column_config.Column(width="small"),
            "메시지": st.column_config.Column(width="large"),
        },
    )


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
else:
    st.info("📭 아직 유효한 LOG 시그널이 없습니다.")


# ✅ 로그 기록
st.subheader("📚 트레이딩 엔진 로그")
logs = fetch_logs(user_id, limit=10)
if logs:
    df_logs = pd.DataFrame(logs, columns=["시간", "레벨", "메시지"])
    df_logs["시간"] = pd.to_datetime(df_logs["시간"]).dt.strftime("%Y-%m-%d %H:%M:%S")
    st.dataframe(
        # df_logs[::-1],  # 최신 순
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
    st.info("아직 기록된 로그가 없습니다.")

error_logs = fetch_logs(user_id, level="ERROR", limit=10)
if error_logs:
    st.subheader("🚨 에러 로그")
    df_error = pd.DataFrame(error_logs, columns=["시간", "레벨", "메시지"])
    df_error["시간"] = pd.to_datetime(df_error["시간"]).dt.strftime("%Y-%m-%d %H:%M:%S")
    st.dataframe(
        # df_error[::-1],  # 최신 순
        df_error,
        use_container_width=True,
        hide_index=True,
        column_config={
            "시간": st.column_config.Column(width="small"),
            "레벨": st.column_config.Column(width="small"),
            "메시지": st.column_config.Column(width="large"),
        },
    )
