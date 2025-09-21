import json
import streamlit as st
import pandas as pd
import time
import logging
from urllib.parse import urlencode
from streamlit_autorefresh import st_autorefresh

from engine.engine_manager import engine_manager
from engine.params import load_params

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

# ✅ 자동 새로고침
st_autorefresh(interval=REFRESH_INTERVAL * 1000, key="dashboard_autorefresh")

# ✅ 현재 엔진 상태
engine_status = engine_manager.is_running(user_id)
# logger.info(f"engine_manager.is_running {engine_status}")
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

col10, col20, col30 = st.columns([1, 1, 1])
with col10:
    # ✅ 실행되지 않았을 경우: 실행 버튼 표시
    if not engine_status:
        start_trading = st.button(
            "Upbit Trade Bot v1 (TEST) 엔진 실행하기", use_container_width=True
        )
        if start_trading:
            if not st.session_state.get("engine_started", False):
                if not engine_manager.is_running(user_id):  # ✅ 유저별 엔진 실행 여부 확인
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
with col20:
    start_setting = st.button(
        "Upbit Trade Bot v1 (TEST) 파라미터 설정하기", use_container_width=True
    )
    if start_setting:
        if engine_status:
            st.warning("⚠️ 먼저 트레이딩 엔진 종료해주세요.")
            st.stop()

        next_page = "set_config"

        params = urlencode(
            {
                "virtual_krw": st.session_state.virtual_krw,
                "user_id": st.session_state.user_id,
            }
        )

        st.markdown(
            f'<meta http-equiv="refresh" content="0; url=./{next_page}?{params}">',
            unsafe_allow_html=True,
        )
        st.switch_page(next_page)
with col30:
    logout = st.button("로그아웃하기", use_container_width=True)
    if logout:
        st.markdown(
            f'<meta http-equiv="refresh" content="0; url=/?redirected=1">',
            unsafe_allow_html=True,
        )

st.divider()

json_path = f"{user_id}_{PARAMS_JSON_FILENAME}"
params_obj = load_params(json_path)
account_krw = get_account(user_id) or 0
# st.write(account_krw)
coin_balance = get_coin_balance(user_id, params_obj.upbit_ticker) or 0.0


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

st.divider()

# ✅ 최근 거래 내역
st.subheader("📝 최근 거래 내역")
# ✅ 컬럼: 시간, 코인, 매매, 가격, 수량, 상태, 현재금액, 보유코인
orders = fetch_recent_orders(user_id, limit=10000)
if orders:
    show_logs = st.toggle("📝 최근 거래 내역 보기", value=False)
    if show_logs:
        df_orders = pd.DataFrame(
            orders,
            columns=[
                "시간",
                "코인",
                "매매",
                "가격",
                "수량",
                "상태",
                "현재금액",
                "보유코인",
            ],
        )

        # 시간: 원본 datetime 보존용 컬럼 추가(정렬/계산에 사용)
        df_orders["시간_dt"] = pd.to_datetime(df_orders["시간"], errors="coerce")  # ★ 추가
        # 표시용 문자열은 맨 끝에서 처리

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

        # -------------------------------
        # 손익 / 수익률 계산 (정확히 동작)
        # SELL - 직전 BUY (코인별, 시간 오름차순 기준)
        # -------------------------------
        import numpy as np  # ★ 추가

        # 코인/시간 오름차순 정렬로 "최근 매수"를 이후 행으로 전달 가능
        df_orders.sort_values(["코인", "시간_dt"], inplace=True)  # ★ 추가

        # 매수 가격만 남긴 임시열 → ffill 로 최근 매수가를 전달
        df_orders["_buy_price_tmp"] = df_orders["_가격_숫자"].where(df_orders["매매"] == "BUY")  # ★ 추가
        df_orders["_last_buy_price"] = df_orders.groupby("코인")["_buy_price_tmp"].ffill()      # ★ 추가

        # SELL 행에서만 손익/수익률 계산, 그 외는 NaN
        df_orders["손익"] = np.where(
            (df_orders["매매"] == "SELL") & df_orders["_last_buy_price"].notna(),
            df_orders["_가격_숫자"] - df_orders["_last_buy_price"],
            np.nan,
        )  # ★ 추가
        df_orders["수익률(%)"] = np.where(
            df_orders["손익"].notna(),
            (df_orders["손익"] / df_orders["_last_buy_price"]) * 100,
            np.nan,
        )  # ★ 추가

        # 다시 최신순(내림차순)으로 돌려서 보기 좋게
        df_orders.sort_values("시간_dt", ascending=False, inplace=True)  # ★ 추가

        # 표시용 시간 문자열 최종 변환
        df_orders["시간"] = df_orders["시간_dt"].dt.strftime("%Y-%m-%d %H:%M:%S")  # ★ 변경(표시 시점 이동)

        # 표시 포맷팅
        df_orders["가격"] = df_orders["_가격_숫자"].map(lambda x: f"{x:,.0f} KRW")
        df_orders["현재금액"] = df_orders["_현재금액_숫자"].map(lambda x: f"{x:,.0f} KRW")
        df_orders["보유코인"] = df_orders["보유코인"].map(lambda x: f"{float(x):.6f}")
        df_orders["손익"] = df_orders["손익"].apply(
            lambda x: f"{x:,.0f} KRW" if pd.notna(x) else "-"
        )
        df_orders["수익률(%)"] = df_orders["수익률(%)"].apply(
            lambda x: f"{x:.2f}%" if pd.notna(x) else "-"
        )

        # 불필요 컬럼 제거
        df_orders = df_orders.drop(columns=["_가격_숫자", "_현재금액_숫자", "_buy_price_tmp", "_last_buy_price", "시간_dt"])

        # ▶ 컬럼 순서 조정(모바일 가독성): 상태, 현재금액, 보유코인을 맨 뒤로
        cols_to_tail = ["상태", "현재금액", "보유코인"]
        tail = [c for c in cols_to_tail if c in df_orders.columns]
        front = [c for c in df_orders.columns if c not in tail]
        df_orders = df_orders[front + tail]

        st.dataframe(df_orders, use_container_width=True, hide_index=True)
else:
    st.info("최근 거래 내역이 없습니다.")

st.divider()

buy_logs = fetch_logs(user_id, level="BUY", limit=10)
buy_logs = None
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
sell_logs = None
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

info_logs = fetch_logs(user_id, level="INFO", limit=10000)
if info_logs:
    st.subheader("🚨 상태 로그")

    show_logs = st.toggle("🚨 상태 로그 보기", value=False)
    if show_logs:
        df_info = pd.DataFrame(info_logs, columns=["시간", "레벨", "메시지"])
        df_info["시간"] = pd.to_datetime(df_info["시간"]).dt.strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        st.dataframe(
            # df_info[::-1],  # 최신 순
            df_info,
            use_container_width=True,
            hide_index=True,
            # column_config={
            #     "시간": st.column_config.Column(width="small"),
            #     "레벨": st.column_config.Column(width="small"),
            #     "메시지": st.column_config.Column(width="large"),
            # },
        )

st.markdown("---")
st.subheader("💹 거래 로그 (BUY / SELL)")
show_trade = st.toggle("💹 거래 로그 보기", value=False)
if show_trade:
    trade_logs = (fetch_logs(user_id, level="BUY", limit=10000) or []) + \
                    (fetch_logs(user_id, level="SELL", limit=10000) or [])
    if trade_logs:
        df_trade = pd.DataFrame(trade_logs, columns=["시간", "레벨", "메시지"])

        df_trade["시간_dt"] = pd.to_datetime(df_trade["시간"], errors="coerce")
        df_trade.sort_values("시간_dt", ascending=False, inplace=True)

        df_trade["시간"] = df_trade["시간_dt"].dt.strftime("%Y-%m-%d %H:%M:%S")
        df_trade.drop(columns=["시간_dt"], inplace=True)
        
        st.dataframe(
            df_trade, use_container_width=True, hide_index=True
        )
    else:
        st.info("표시할 BUY/SELL 로그가 없습니다.")

st.divider()

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

def emoji_cross(msg: str):
    if "cross=Golden" in msg:
        return "🟢 " + msg
    elif "cross=Dead" in msg:
        return "🔴 " + msg
    elif "cross=Up" in msg:
        return "🔵 " + msg
    elif "cross=Down" in msg:
        return "🟣 " + msg
    elif "cross=Neutral" in msg:
        return "⚪ " + msg
    return msg

st.divider()

# ✅ 로그 기록
st.subheader("📚 트레이딩 엔진 로그")
st.markdown(
    """
    🟢 **Golden** &nbsp;&nbsp; 🔴 **Dead** &nbsp;&nbsp; 🔵 **Pending** &nbsp;&nbsp; ⚪ **Neutral**
"""
)
logs = fetch_logs(user_id, limit=10000)
if logs:
    df_logs = pd.DataFrame(logs, columns=["시간", "레벨", "메시지"])

    # ★ LOG SYNC: 기록 시각(로그 저장 시각) 표준 포맷
    df_logs["시간"] = pd.to_datetime(df_logs["시간"]).dt.strftime("%Y-%m-%d %H:%M:%S")  # 기록된 DB 시간

    # 🟡 cross 상태 시각화 이모지 (기존 유지)
    def emoji_cross(msg: str):
        if "cross=Golden" in msg:
            return "🟢 " + msg
        elif "cross=Dead" in msg:
            return "🔴 " + msg
        elif "cross=Pending" in msg or "cross=Up" in msg:
            return "🔵 " + msg
        elif "cross=Down" in msg:
            return "🟣 " + msg
        elif "cross=Neutral" in msg:
            return "⚪ " + msg
        return msg

    # ★ LOG SYNC: 경계 동기화 메시지에서 bar_open/bar_close 추출
    import re
    re_last = re.compile(r"last_closed_open=([0-9:\- ]+)\s*\|\s*last_closed_close=([0-9:\- ]+)")
    re_bar  = re.compile(r"run_at=([0-9:\- ]+)\s*\|\s*bar_open=([0-9:\- ]+)\s*\|\s*bar_close=([0-9:\- ]+)")

    def parse_sync_fields(msg: str):
        """
        ⏱ last_closed_open=... | last_closed_close=...
        또는
        ⏱ run_at=... | bar_open=... | bar_close=...
        형태를 파싱해 컬럼으로 반환.
        """
        m1 = re_last.search(msg)
        if m1:
            return {
                "bar_open": m1.group(1).strip(),
                "bar_close": m1.group(2).strip(),
                "run_at": None,  # 이 형태엔 run_at 없음
            }
        m2 = re_bar.search(msg)
        if m2:
            return {
                "run_at": m2.group(1).strip(),
                "bar_open": m2.group(2).strip(),
                "bar_close": m2.group(3).strip(),
            }
        return {"run_at": None, "bar_open": None, "bar_close": None}

    parsed = df_logs["메시지"].apply(parse_sync_fields)  # ★ LOG SYNC

    # ★ LOG SYNC: 새 컬럼 추가(사용자 오해 방지용)
    df_logs["실행시각(run_at)"] = parsed.apply(lambda d: d["run_at"])        # 메시지 내부의 run_at(있으면)
    df_logs["바오픈(bar_open)"]  = parsed.apply(lambda d: d["bar_open"])
    df_logs["바클로즈(bar_close)"] = parsed.apply(lambda d: d["bar_close"])

    # ★ LOG SYNC: 가독성을 위해 원문 메시지에 이모지 적용 (기존 유지)
    df_logs["메시지"] = df_logs["메시지"].apply(emoji_cross)

    # 최근 순 정렬(기록 시각 기준)
    # df_logs = df_logs.iloc[::-1]  # 필요시 사용
    show_logs = st.toggle("📚 트레이딩 엔진 로그 보기", value=False)
    if show_logs:
        st.dataframe(
            df_logs,
            use_container_width=True,
            hide_index=True,
            column_config={
                "시간": st.column_config.Column(width="small", label="기록시각(DB)"),
                "실행시각(run_at)": st.column_config.Column(width="small"),
                "바오픈(bar_open)": st.column_config.Column(width="small"),
                "바클로즈(bar_close)": st.column_config.Column(width="small"),
                "레벨": st.column_config.Column(width="small"),
                "메시지": st.column_config.Column(width="large"),
            },
        )
else:
    st.info("아직 기록된 로그가 없습니다.")

error_logs = fetch_logs(user_id, level="ERROR", limit=10)
error_logs = None
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
st.write()

st.divider()

st.subheader("⚙️ Option 기능")
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

# ✅ params 요약 카드 표시
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


def get_macd_exit_enabled() -> str:
    if params_obj.macd_exit_enabled:
        return "사용"
    return "미사용"


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
    """,
    unsafe_allow_html=True,
)
st.write("")


target_filename = f"{user_id}_{CONDITIONS_JSON_FILENAME}"
SAVE_PATH = Path(target_filename)

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
    "macd_exit": "📉  MACD Exit - Dead Cross or MACD < threshold",
}


# --- 상태 불러오기 ---
def load_conditions():
    if SAVE_PATH.exists():
        with SAVE_PATH.open("r", encoding="utf-8") as f:
            saved = json.load(f)
            buy_saved = saved.get("buy", {})
            sell_saved = saved.get("sell", {})
            return buy_saved, sell_saved
    else:
        return {}, {}


buy_state, sell_state = load_conditions()

st.markdown(
    """
    <style>
    .strategy-table {
        width: 100%;
        border-collapse: collapse;
    }
    .strategy-table colgroup col:first-child {
        width: 75%;  /* Condition 칼럼 */
    }
    .strategy-table colgroup col:last-child {
        width: 25%;  /* Status 칼럼 */
    }
    .strategy-table th, .strategy-table td {
        border: 1px solid #555;
        padding: 6px 10px;
        text-align: left;
    }
    .strategy-table th {
        background-color: #2c2c2c;
        color: white;  /* 다크모드 제목 */
    }
    .strategy-table td.on {
        color: #00ff00;
        font-weight: bold;
    }
    .strategy-table td.off {
        color: #ff3333;
        font-weight: bold;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

col1, col2 = st.columns([6, 1])
with col1:
    st.subheader("⚙️ 매수 전략")
with col2:
    if st.button("🛠️ 설정", use_container_width=True):
        params = urlencode({"user_id": user_id})
        st.markdown(
            f'<meta http-equiv="refresh" content="0; url=./set_buy_sell_conditions?{params}">',
            unsafe_allow_html=True,
        )
st.markdown(
    "<table class='strategy-table'>"
    "<colgroup><col><col></colgroup>"  # 칼럼 비율 고정
    "<tr><th>Condition</th><th>Status</th></tr>"
    + "".join(
        f"<tr><td>{label}</td><td class='{ 'on' if buy_state.get(key, False) else 'off' }'>{ '✅ ON' if buy_state.get(key, False) else '❌ OFF' }</td></tr>"
        for key, label in BUY_CONDITIONS.items()
    )
    + "</table>",
    unsafe_allow_html=True,
)
st.write("")

st.subheader("⚙️ 매도 전략")
st.markdown(
    "<table class='strategy-table'>"
    "<colgroup><col><col></colgroup>"  # 칼럼 비율 고정
    "<tr><th>Condition</th><th>Status</th></tr>"
    + "".join(
        f"<tr><td>{label}</td><td class='{ 'on' if sell_state.get(key, False) else 'off' }'>{ '✅ ON' if sell_state.get(key, False) else '❌ OFF' }</td></tr>"
        for key, label in SELL_CONDITIONS.items()
    )
    + "</table>",
    unsafe_allow_html=True,
)
st.write("")
