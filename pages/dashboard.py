import json
from operator import is_
import streamlit as st
import pandas as pd
import time
import logging
from urllib.parse import urlencode
from streamlit_autorefresh import st_autorefresh

from engine.engine_manager import engine_manager
from engine.params import load_params, load_active_strategy

from services.db import (
    get_account,
    get_coin_balance,
    get_initial_krw,
    fetch_recent_orders,
    fetch_latest_order_by_ticker,
    fetch_logs,
    insert_log,
    get_last_status_log_from_db,
    fetch_latest_log_signal,
    fetch_latest_log_signal_ema,
    fetch_latest_buy_eval,
    fetch_latest_sell_eval,
    fetch_latest_trade_audit,
    get_db,
    get_last_open_buy_order
)

from config import (
    PARAMS_JSON_FILENAME,
    REFRESH_INTERVAL,
    CONDITIONS_JSON_FILENAME,
    DEFAULT_STRATEGY_TYPE
)
from ui.style import style_main

from core.trader import UpbitTrader
from services.trading_control import force_liquidate, force_buy_in

from pathlib import Path

import pyupbit.request_api as rq

upbit_logger = logging.getLogger("pyupbit.http")

_original_send_post = rq._send_post_request

def debug_send_post(url, headers=None, data=None):
    upbit_logger.info(f"[HTTP-POST] url={url} data={data} headers={headers}")
    res = _original_send_post(url, headers=headers, data=data)
    upbit_logger.info(f"[HTTP-POST] result={repr(res)[:500]}")
    return res

rq._send_post_request = debug_send_post


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ✅ 쿼리 파라미터 처리
qp = st.query_params

def _get_param(qp, key, default=None):
    v = qp.get(key, default)
    if isinstance(v, list):
        return v[0]
    return v

user_id = _get_param(qp, "user_id", st.session_state.get("user_id", ""))
raw_vk = _get_param(qp, "virtual_krw", st.session_state.get("virtual_krw", 0))

try:
    virtual_krw = int(raw_vk)
except (TypeError, ValueError):
    virtual_krw = int(st.session_state.get("virtual_krw", 0) or 0)

raw_mode = _get_param(qp, "mode", st.session_state.get("mode", "TEST"))
mode = str(raw_mode).upper()
st.session_state["mode"] = mode
is_live = (mode == "LIVE")

verified_param = _get_param(qp, "verified", "0")
capital_param = _get_param(qp, "capital_set", "0")

upbit_ok = str(verified_param) == "1"
capital_ok = str(capital_param) == "1"

if is_live:
    if "upbit_verified" in st.session_state:
        upbit_ok = upbit_ok or bool(st.session_state["upbit_verified"])
    if "live_capital_set" in st.session_state:
        capital_ok = capital_ok or bool(st.session_state["live_capital_set"])


def get_current_balances(user_id: str, params_obj, is_live: bool, force_refresh: bool = False):
    """
    자산 현황용 현재 잔고 조회.
    - TEST 모드: DB(virtual_krw, account_positions) 기준
    - LIVE 모드:
      * force_refresh=False (기본): DB 캐시 사용 (Reconciler가 2초마다 업데이트, 빠름!)
      * force_refresh=True: Upbit API 실시간 조회 (강제매도/매수 직후만 사용)
    """
    ticker = getattr(params_obj, "upbit_ticker", None) or params_obj.ticker

    if is_live and force_refresh:
        # ✅ 실시간 API 조회 (강제매도/매수 직후에만)
        trader_view = UpbitTrader(
            user_id,
            risk_pct=getattr(params_obj, "order_ratio", 1.0),
            test_mode=False,
        )
        try:
            krw_live = float(trader_view._krw_balance())
            coin_live = float(trader_view._coin_balance(ticker))
            logger.info(f"[DASH] 실시간 API 조회: KRW={krw_live:,.0f}, COIN={coin_live:.6f}")
            return krw_live, coin_live
        except Exception as e:
            logger.warning(f"[DASH] API 조회 실패, DB 폴백: {e}")

    # ✅ DB 캐시 사용 (TEST 모드 + LIVE 일반 모니터링)
    # Reconciler가 주문 체결 시 실시간 업데이트하므로 충분히 정확함
    acc = get_account(user_id) or 0.0
    coin = get_coin_balance(user_id, ticker) or 0.0
    return float(acc), float(coin)


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

st.markdown(
    f"""
    <div style="position:sticky;top:0;z-index:999;background:#0b0b0b;padding:8px 12px;border-bottom:1px solid #222;">
      <span style="background:{('#22c55e' if is_live else '#64748b')};color:white;padding:4px 10px;border-radius:999px;font-weight:700;">
        {mode}
      </span>
      <span style="color:#bbb;margin-left:8px">운용 중</span>
      {"<span style='color:#fca5a5;margin-left:12px'>⚠️ LIVE 모드: 실거래 주의</span>" if is_live else ""}
    </div>
    """,
    unsafe_allow_html=True
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
st.markdown(f"### 📊 Dashboard ({mode}) : `{user_id}`님 --- v1.2026.02.01.2148")
st.markdown(f"🕒 현재 시각: {time.strftime('%Y-%m-%d %H:%M:%S')}")

col1, col2 = st.columns([4, 1])
with col1:
    st.info("Upbit Trade Bot v1 상태 모니터링 페이지입니다.")

    # ✅ 데이터 수집 상태 확인 및 표시
    from services.db import get_data_collection_status
    data_status = get_data_collection_status(user_id)

    if data_status and data_status.get("is_collecting"):
        # 데이터 수집 중
        collected = data_status.get("collected", 0)
        target = data_status.get("target", 0)
        progress = data_status.get("progress", 0.0)
        est_time = data_status.get("estimated_time", 0.0)
        message = data_status.get("message", "")

        st.warning(f"🔄 **데이터 수집 중... 엔진이 곧 시작됩니다**")
        st.progress(progress, text=f"진행: {collected}/{target}개 ({progress*100:.1f}%)")
        if est_time > 0:
            st.caption(f"⏱️ 예상 남은 시간: 약 {est_time:.1f}초")
        if message:
            st.caption(f"상태: {message}")
    else:
        # 데이터 수집 완료 또는 수집 전
        # ✅ 최종 로그 표시
        last_log = get_last_status_log_from_db(user_id)
        st.info(last_log)

with col2:
    status_color = "🟢" if engine_status else "🔴"
    st.metric(
        "트레이딩 엔진 상태", "Running" if engine_status else "Stopped", status_color
    )

style_metric_cards()

# ✅ strategy_tag 변수를 먼저 정의 (버튼에서 사용하기 위해)
# 우선순위: URL → 세션 → 활성 전략 파일 → 기본값
json_path = f"{user_id}_{PARAMS_JSON_FILENAME}"
strategy_from_url = _get_param(qp, "strategy_type", None)
strategy_from_session = st.session_state.get("strategy_type", None)
strategy_from_file = load_active_strategy(user_id)
strategy_tag = (strategy_from_url or strategy_from_session or strategy_from_file or DEFAULT_STRATEGY_TYPE)
strategy_tag = str(strategy_tag).upper().strip()
st.session_state["strategy_type"] = strategy_tag

col10, col20, col30 = st.columns([1, 1, 1])
with col10:
    # ✅ 실행되지 않았을 경우: 실행 버튼 표시
    if not engine_status:
        start_trading = st.button(
            f"Upbit Trade Bot v1 ({mode}) 엔진 실행하기", use_container_width=True
        )
        if start_trading:
            if not st.session_state.get("engine_started", False):
                if not engine_manager.is_running(user_id):  # ✅ 유저별 엔진 실행 여부 확인
                    st.write("🔄 엔진 실행을 시작합니다...")
                    success = engine_manager.start_engine(user_id, test_mode=(not is_live))
                    if success:
                        insert_log(user_id, "INFO", f"✅ 트레이딩 엔진 실행됨 ({mode})")
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
        f"Upbit Trade Bot v1 ({mode}) 파라미터 설정하기", use_container_width=True
    )
    if start_setting:
        if engine_status:
            st.warning("⚠️ 먼저 트레이딩 엔진 종료해주세요.")
            st.stop()

        next_page = "set_config"
        params = urlencode({
            "virtual_krw": st.session_state.virtual_krw,
            "user_id": st.session_state.user_id,
            "mode": mode,
            "verified": upbit_ok,
            "capital_set": capital_ok,
            "strategy_type": strategy_tag,  # ✅ 현재 전략 타입 전달
        })
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

from services.init_db import init_db_if_needed, get_db_path
init_db_if_needed(user_id)
st.caption(f"DB file: `{get_db_path(user_id)}`")

# ✅ 전략 타입을 전달해서 전략별 params를 로드
params_obj = load_params(json_path, strategy_type=strategy_tag)

# ✅ 해당 전략 파일이 아직 없을 수 있으므로(최초 진입 등) 공용/디폴트로 한 번 더 폴백
if params_obj is None:
    # 1) 공용 파일(기존 방식) 시도 → 혹시 남아있는 레거시가 있다면 살림
    params_obj = load_params(json_path, strategy_type=strategy_tag)
    # 2) 그것도 없으면 치명적이므로 안내 후 중단
    if params_obj is None:
        st.error("❌ 파라미터가 없습니다. 먼저 '파라미터 설정하기'에서 저장해 주세요.")
        st.stop()

# 🔍 디버그: 실제로 대시보드가 읽은 파라미터 확인
# st.code(f"[DEBUG] json_path={json_path}", language="text")
# st.json(params_obj.model_dump())
# st.write("strategy_type from params_obj:", params_obj.strategy_type)

# ✅ 강제매도/매수 후 즉시 API 조회 여부 확인
force_api_refresh = st.session_state.pop("needs_balance_refresh", False)

# account_krw = get_account(user_id) or 0
# st.write(account_krw)
# coin_balance = get_coin_balance(user_id, params_obj.upbit_ticker) or 0.0
account_krw, coin_balance = get_current_balances(
    user_id, params_obj, is_live, force_refresh=force_api_refresh
)

# ★ 현재 전략 태그 (MACD / EMA) – LiveParams에서 이미 대문자로 보장됨
raw_strategy = getattr(params_obj, "strategy_type", None) or DEFAULT_STRATEGY_TYPE
strategy_tag = str(raw_strategy).upper()
is_macd = (strategy_tag == "MACD")
is_ema = (strategy_tag == "EMA")

# ===================== 🔧 PATCH: 자산 현황(항상 ROI 표시) START =====================
st.subheader("💰 자산 현황")

# ── 0) 안전한 값 정리
cash = float(account_krw or 0.0)                # 보유 KRW (0원이어도 정상 처리)
qty  = float(coin_balance or 0.0)               # 보유 코인 수량
init_krw = float(get_initial_krw(user_id) or 0) # 기존 초기 KRW (DB)

# ── 1) 현재가 확보: get_ohlcv_once를 "짧게" 호출해 마지막 종가를 사용
#     - 외부 API 추가 없이, 이미 프로젝트에 있는 데이터피드만 이용
def _infer_last_close(df) -> float | None:
    if df is None or len(df) == 0:
        return None
    for col in ("close", "Close", "c", "price"):
        if col in df.columns:
            try:
                return float(df[col].iloc[-1])
            except Exception:
                pass
    # 컬럼명이 달라도 마지막 숫자형 한 칸이라도 잡아보는 최후의 시도
    try:
        last_row = df.iloc[-1]
        for v in last_row.tolist()[::-1]:
            if isinstance(v, (int, float)) and pd.notna(v):
                return float(v)
    except Exception:
        return None
    return None

def get_last_price_local(ticker: str, interval_code: str) -> float | None:
    try:
        # 가벼운 2개 봉만 요청 → 마지막 종가 사용
        from core.data_feed import get_ohlcv_once
        _df = get_ohlcv_once(ticker, interval_code, count=2)
        return _infer_last_close(_df)
    except Exception:
        return None

_ticker = getattr(params_obj, "upbit_ticker", None) or params_obj.ticker
_interval = getattr(params_obj, "interval", params_obj.interval)

last_price = get_last_price_local(_ticker, _interval)

# 가격이 None이면 직전 성공값 사용(세션 캐시) → 화면 깜빡임/일시적 실패 방지
if last_price is None:
    last_price = st.session_state.get("last_price")
else:
    st.session_state["last_price"] = last_price  # 캐시 갱신

# ── 2) 포트폴리오 평가 (NAV = 현금 + 코인평가액)
coin_val = (qty * float(last_price)) if (last_price is not None) else 0.0
portfolio_value = cash + coin_val  # ★ 항상 계산 (현금 0원/코인만 있어도 OK)

# ── 3) 기준선(baseline) 결정 로직
#     - 우선순위: DB 초기 KRW(init_krw) > 세션 baseline > (없으면) 최초 1회 현재 NAV로 자동 스냅샷
baseline = init_krw
if baseline <= 0:
    baseline = float(st.session_state.get("baseline_nav", 0.0))
    if baseline <= 0 and portfolio_value > 0:
        # 초기 KRW가 없더라도 화면 최초 진입 시점의 NAV를 기준선으로 자동 고정
        baseline = portfolio_value
        st.session_state["baseline_nav"] = baseline

# ── 4) ROI 계산 (항상 수치 반환)
#     - baseline이 0이라면 나눗셈 불가 → "0.00%"로 표시해 미정/N/A 방지
roi = ((portfolio_value - baseline) / baseline) * 100.0 if baseline > 0 else 0.0
roi_msg = f"{roi:.2f} %"

# ── 5) 메트릭 표시
_nbsp = "\u00A0"  # NBSP(공백) → delta 줄만 확보, 내용/화살표 없음

col_krw, col_coin, col_pnl = st.columns(3)
with col_krw:
    st.metric("보유 KRW", f"{cash:,.0f} KRW", delta=_nbsp, delta_color="off")
with col_coin:
    # delta에 코인 평가액을 유지 (정보성 OK)
    st.metric(f"{_ticker} 보유량", f"{qty:,.6f}", delta=f"평가 {coin_val:,.0f} KRW", delta_color="off")
with col_pnl:
    # ✅ 포지션 보유 여부에 따라 분기
    if qty > 0:
        # === 미실현 수익률 (현재 포지션) ===
        last_buy = get_last_open_buy_order(_ticker, user_id)
        if last_buy and last_price:
            entry_price = last_buy["price"]
            unrealized_pnl_pct = ((last_price - entry_price) / entry_price) * 100.0
            metric_label = "💹 현재 포지션"
            metric_value = f"{unrealized_pnl_pct:+.2f}%"

            if unrealized_pnl_pct > 0:
                delta_str = f"+{unrealized_pnl_pct:.2f}% (미실현)"
                delta_color = "normal"
            elif unrealized_pnl_pct < 0:
                delta_str = f"{unrealized_pnl_pct:.2f}% (미실현)"
                delta_color = "normal"
            else:
                delta_str = "보합 (미실현)"
                delta_color = "off"
        else:
            metric_label = "💹 현재 포지션"
            metric_value = "N/A"
            delta_str = "정보 없음"
            delta_color = "off"
    else:
        # === 최근 거래 수익률 (마지막 SELL) ===
        recent_orders = fetch_recent_orders(user_id, limit=50)

        last_sell_return = None

        # 리스트를 순회하면서 가장 최근 SELL 찾기 (이미 최신순 DESC)
        for i, order in enumerate(recent_orders):
            timestamp, ticker, side, price, volume, status, _, _ = order

            if ticker != _ticker or side != "SELL":
                continue

            # 가장 최근 SELL 발견
            sell_price = float(price)

            # 이 SELL 이후의 BUY 찾기 (더 뒤 인덱스 = 더 오래된 주문)
            for j in range(i + 1, len(recent_orders)):
                _, ticker2, side2, price2, _, _, _, _ = recent_orders[j]
                if ticker2 == _ticker and side2 == "BUY":
                    buy_price = float(price2)
                    last_sell_return = ((sell_price - buy_price) / buy_price) * 100.0
                    break

            break  # 첫 번째 SELL만 처리

        if last_sell_return is not None:
            metric_label = "💹 최근 거래"
            metric_value = f"{last_sell_return:+.2f}%"

            if last_sell_return > 0:
                delta_str = f"+{last_sell_return:.2f}% (실현)"
                delta_color = "normal"
            elif last_sell_return < 0:
                delta_str = f"{last_sell_return:.2f}% (실현)"
                delta_color = "normal"
            else:
                delta_str = "보합 (실현)"
                delta_color = "off"
        else:
            metric_label = "💹 최근 거래"
            metric_value = "N/A"
            delta_str = "거래 없음"
            delta_color = "off"

    st.metric(metric_label, metric_value, delta=delta_str, delta_color=delta_color)

# (선택) 기준선 힌트: 어떤 기준으로 계산 중인지 투명하게 표기하고 싶다면 주석 해제
# st.caption(f"기준선: {'초기 KRW' if init_krw > 0 else '세션 스냅샷'} = {baseline:,.0f} KRW · 현재 NAV = {portfolio_value:,.0f} KRW")

st.divider()
# ===================== 🔧 PATCH: 자산 현황(항상 ROI 표시) END =====================

# ✅ 최근 거래 내역
st.subheader("📝 최근 거래 내역")
# ✅ 컬럼: 시간, 코인, 매매, 가격, 수량, 상태, 현재금액, 보유코인
orders = fetch_recent_orders(user_id, limit=200)
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

info_logs = fetch_logs(user_id, level="INFO", limit=200)
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

# st.markdown("---")
# st.subheader("💹 거래 로그 (BUY / SELL)")
# show_trade = st.toggle("💹 거래 로그 보기", value=False)
# if show_trade:
    # trade_logs = (fetch_logs(user_id, level="BUY", limit=100) or []) + \
                    # (fetch_logs(user_id, level="SELL", limit=100) or [])
    # if trade_logs:
        # df_trade = pd.DataFrame(trade_logs, columns=["시간", "레벨", "메시지"])

        # df_trade["시간_dt"] = pd.to_datetime(df_trade["시간"], errors="coerce")
        # df_trade.sort_values("시간_dt", ascending=False, inplace=True)

        # df_trade["시간"] = df_trade["시간_dt"].dt.strftime("%Y-%m-%d %H:%M:%S")
        # df_trade.drop(columns=["시간_dt"], inplace=True)
        
        # st.dataframe(
            # df_trade, use_container_width=True, hide_index=True
        # )
    # else:
        # st.info("표시할 BUY/SELL 로그가 없습니다.")

st.divider()

import pandas as pd

# 화면 표시용 로컬 타임존 (원하면 설정에서 끌어와도 됨)
LOCAL_TZ = "Asia/Seoul"

def _parse_dt(s: str) -> pd.Timestamp | None:
    """
    입력 문자열을 'UTC 기준 tz-aware Timestamp' 로 통일.
    - tz가 붙은 문자열이면 UTC로 변환
    - tz가 없는 문자열(naive)이면 UTC로 간주해서 tz를 붙임
    """
    if s is None:
        return None
    try:
        ts = pd.to_datetime(s, errors="coerce", utc=True)  # <- 핵심: utc=True
        return ts  # ✅ Timestamp 객체를 반환
    except Exception:
        return None

def _fmt_dt(ts: pd.Timestamp | None, tz: str = LOCAL_TZ) -> str:
    if ts is None or pd.isna(ts):
        return ""
    try:
        # tz 정보가 없으면 UTC로 로컬라이즈 후 변환
        if getattr(ts, "tzinfo", None) is None:
            ts = ts.tz_localize("UTC")
        return ts.tz_convert(tz).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        # 최후의 보루: 강제 변환
        ts2 = pd.to_datetime(ts, errors="coerce", utc=True)
        if ts2 is None or pd.isna(ts2):
            return ""
        return ts2.tz_convert(tz).strftime("%Y-%m-%d %H:%M:%S")

def get_latest_any_signal(user_id: str, ticker: str, strategy_tag: str = "MACD") -> dict | None:
    """
    BUY 평가(audit_buy_eval), SELL 평가(audit_sell_eval), 체결(audit_trades) 중
    timestamp가 가장 최신인 항목을 반환.
    """
    # 1) BUY 평가 감사로그
    buy_row = fetch_latest_buy_eval(user_id, ticker)
    buy_dt = _parse_dt(buy_row["timestamp"]) if buy_row else None

    # 2) SELL 평가 감사로그
    sell_row = fetch_latest_sell_eval(user_id, ticker)
    sell_dt = _parse_dt(sell_row["timestamp"]) if sell_row else None

    # 3) TRADE 체결 감사로그
    trade_row = fetch_latest_trade_audit(user_id, ticker)
    trade_dt = _parse_dt(trade_row["timestamp"]) if trade_row else None

    # 모두 None이면 반환할 데이터 없음
    if (buy_dt is None) and (sell_dt is None) and (trade_dt is None):
        return None

    # 가장 최신 데이터 선택
    candidates = []
    if buy_dt is not None:
        candidates.append(("BUY", buy_dt, buy_row))
    if sell_dt is not None:
        candidates.append(("SELL", sell_dt, sell_row))
    if trade_dt is not None:
        candidates.append(("TRADE", trade_dt, trade_row))

    # timestamp 기준 내림차순 정렬 후 최신 선택
    candidates.sort(key=lambda x: x[1], reverse=True)
    source, latest_dt, latest_row = candidates[0]

    # 공통 필드 계산
    macd = latest_row.get("macd")
    signal = latest_row.get("signal")
    delta = None
    if macd is not None and signal is not None:
        try:
            delta = float(macd) - float(signal)
        except (ValueError, TypeError):
            delta = None

    # Source별 반환 데이터 구성
    if source == "BUY":
        return {
            "source": "BUY",
            "strategy": strategy_tag,
            "timestamp": latest_row["timestamp"],
            "ticker": latest_row["ticker"],
            "bar": latest_row["bar"],
            "price": latest_row["price"],
            "macd": macd,  # EMA 전략: ema_fast
            "signal": signal,  # EMA 전략: ema_slow
            "delta": delta,
            "overall_ok": latest_row["overall_ok"],
            "failed_keys": latest_row["failed_keys"],
            "notes": latest_row["notes"],
        }
    elif source == "SELL":
        return {
            "source": "SELL",
            "strategy": strategy_tag,
            "timestamp": latest_row["timestamp"],
            "ticker": latest_row["ticker"],
            "bar": latest_row["bar"],
            "price": latest_row["price"],
            "macd": macd,  # EMA 전략: ema_fast
            "signal": signal,  # EMA 전략: ema_slow
            "delta": delta,
            "triggered": latest_row["triggered"],
            "trigger_key": latest_row["trigger_key"],
            "tp_price": latest_row["tp_price"],
            "sl_price": latest_row["sl_price"],
            "bars_held": latest_row["bars_held"],
            "notes": latest_row["notes"],
        }
    else:  # TRADE
        return {
            "source": "TRADE",
            "strategy": strategy_tag,
            "timestamp": latest_row["timestamp"],
            "ticker": latest_row["ticker"],
            "bar": latest_row["bar"],
            "type": latest_row["type"],  # BUY / SELL
            "reason": latest_row["reason"],
            "price": latest_row["price"],
            "macd": macd,  # EMA 전략: ema_fast
            "signal": signal,  # EMA 전략: ema_slow
            "delta": delta,
            "entry_price": latest_row.get("entry_price"),
            "bars_held": latest_row.get("bars_held"),
        }

latest = get_latest_any_signal(
    user_id, getattr(params_obj, "upbit_ticker", None) or params_obj.ticker, strategy_tag
)

st.subheader("📌 최종 시그널 정보 (가장 최신)")
if latest:
    # ✅ 시간 포맷팅
    timestamp_raw = latest.get('timestamp')
    if timestamp_raw:
        try:
            from datetime import datetime
            if isinstance(timestamp_raw, str):
                dt = datetime.fromisoformat(timestamp_raw)
                timestamp_str = dt.strftime("%Y-%m-%d %H:%M:%S")
            else:
                timestamp_str = str(timestamp_raw)
        except Exception:
            timestamp_str = str(timestamp_raw)
    else:
        timestamp_str = '-'

    # 공통 필드
    ticker = latest.get('ticker', '-')
    bar = latest.get('bar', '-')
    price = latest.get('price', '-')
    if price != '-':
        try:
            price = f"{float(price):.2f}"
        except (ValueError, TypeError):
            pass

    # 전략별 지표명
    indicator_fast = "EMA Fast" if strategy_tag == "EMA" else "MACD"
    indicator_slow = "EMA Slow" if strategy_tag == "EMA" else "Signal"

    macd_val = latest.get('macd', '-')
    signal_val = latest.get('signal', '-')
    delta_val = latest.get('delta', '-')

    # 값 포맷팅
    if macd_val != '-':
        try:
            macd_val = f"{float(macd_val):.2f}"
        except (ValueError, TypeError):
            pass
    if signal_val != '-':
        try:
            signal_val = f"{float(signal_val):.2f}"
        except (ValueError, TypeError):
            pass
    if delta_val != '-':
        try:
            delta_val = f"{float(delta_val):.2f}"
        except (ValueError, TypeError):
            pass

    source = latest["source"]

    # SELL 평가 정보
    # ✅ checks JSON에서 cross_status 추출
    checks_raw = latest.get('checks', '{}')
    try:
        import json
        checks = json.loads(checks_raw) if isinstance(checks_raw, str) else checks_raw
        cross_status = checks.get('cross_status', 'Neutral')
    except Exception:
        cross_status = 'Neutral'

    # ✅ 상태 표시: triggered > cross_status 순으로 우선순위
    if latest.get('triggered'):
        triggered = "🔴 TRIGGERED"
    elif cross_status == "Dead":
        triggered = "🔴 Dead (대기)"
    elif cross_status == "Golden":
        triggered = "🟢 Golden"
    else:
        triggered = "⚪ Neutral"

    if source == "BUY":
        # BUY 평가 정보
        overall_ok = "✅ PASS" if latest.get('overall_ok') else "❌ FAIL"
        failed_keys = latest.get('failed_keys', '')
        if failed_keys and failed_keys != '-':
            try:
                import json
                failed_list = json.loads(failed_keys) if isinstance(failed_keys, str) else failed_keys
                failed_str = ", ".join(failed_list) if failed_list else "-"
            except Exception:
                failed_str = str(failed_keys)
        else:
            failed_str = "-"

        cols1 = st.columns(5)
        cols1[0].markdown(f"**시간**<br>{timestamp_str}", unsafe_allow_html=True)
        cols1[1].markdown(f"**Ticker**<br>{ticker}", unsafe_allow_html=True)
        cols1[2].markdown(f"**Bar**<br>{bar}", unsafe_allow_html=True)
        cols1[3].markdown(f"**Price**<br>{price} KRW", unsafe_allow_html=True)
        cols1[4].markdown(f"**상태**<br>{triggered}", unsafe_allow_html=True)

        cols2 = st.columns(5)
        cols2[0].markdown(f"**Delta**<br>{delta_val}", unsafe_allow_html=True)
        cols2[1].markdown(f"**{indicator_fast}**<br>{macd_val}", unsafe_allow_html=True)
        cols2[2].markdown(f"**{indicator_slow}**<br>{signal_val}", unsafe_allow_html=True)
        cols2[3].markdown(f"**실패 조건**<br>{failed_str}", unsafe_allow_html=True)
        cols2[4].markdown(f"**평가**<br>{overall_ok}", unsafe_allow_html=True)

        st.caption(f"Source: **BUY** (매수 평가 감사로그)")

    elif source == "SELL":
        trigger_key = latest.get('trigger_key', '-')
        tp_price = latest.get('tp_price', '-')
        sl_price = latest.get('sl_price', '-')
        bars_held = latest.get('bars_held', '-')

        if tp_price != '-':
            try:
                tp_price = f"{float(tp_price):.2f}"
            except (ValueError, TypeError):
                pass
        if sl_price != '-':
            try:
                sl_price = f"{float(sl_price):.2f}"
            except (ValueError, TypeError):
                pass

        cols1 = st.columns(5)
        cols1[0].markdown(f"**시간**<br>{timestamp_str}", unsafe_allow_html=True)
        cols1[1].markdown(f"**Ticker**<br>{ticker}", unsafe_allow_html=True)
        cols1[2].markdown(f"**Bar**<br>{bar}", unsafe_allow_html=True)
        cols1[3].markdown(f"**Price**<br>{price} KRW", unsafe_allow_html=True)
        cols1[4].markdown(f"**상태**<br>{triggered}", unsafe_allow_html=True)

        cols2 = st.columns(5)
        cols2[0].markdown(f"**Delta**<br>{delta_val}", unsafe_allow_html=True)
        cols2[1].markdown(f"**{indicator_fast}**<br>{macd_val}", unsafe_allow_html=True)
        cols2[2].markdown(f"**{indicator_slow}**<br>{signal_val}", unsafe_allow_html=True)
        cols2[3].markdown(f"**트리거**<br>{trigger_key}", unsafe_allow_html=True)
        cols2[4].markdown(f"**TP/SL**<br>{tp_price}/{sl_price}", unsafe_allow_html=True)

        st.caption(f"Source: **SELL** (매도 평가 감사로그)")

    else:  # TRADE
        # 체결 정보
        trade_type = latest.get('type', '-')
        reason = latest.get('reason', '-')
        entry_price = latest.get('entry_price', '-')
        bars_held = latest.get('bars_held', '-')

        if entry_price != '-' and entry_price is not None:
            try:
                entry_price = f"{float(entry_price):.2f}"
            except (ValueError, TypeError):
                pass

        cols1 = st.columns(5)
        cols1[0].markdown(f"**시간**<br>{timestamp_str}", unsafe_allow_html=True)
        cols1[1].markdown(f"**Ticker**<br>{ticker}", unsafe_allow_html=True)
        cols1[2].markdown(f"**Bar**<br>{bar}", unsafe_allow_html=True)
        cols1[3].markdown(f"**Type**<br>{trade_type}", unsafe_allow_html=True)
        cols1[4].markdown(f"**Price**<br>{price}", unsafe_allow_html=True)

        cols2 = st.columns(5)
        cols2[0].markdown(f"**Delta**<br>{delta_val}", unsafe_allow_html=True)
        cols2[1].markdown(f"**{indicator_fast}**<br>{macd_val}", unsafe_allow_html=True)
        cols2[2].markdown(f"**{indicator_slow}**<br>{signal_val}", unsafe_allow_html=True)
        cols2[3].markdown(f"**Reason**<br>{reason}", unsafe_allow_html=True)
        cols2[4].markdown(f"**Entry@Bars**<br>{entry_price}@{bars_held}", unsafe_allow_html=True)

        st.caption(f"Source: **TRADE** (체결 감사로그)")
else:
    st.info("📭 아직 표시할 최신 시그널/체결 정보가 없습니다.")
st.divider()

# ✅ 로그 기록
st.subheader("📚 트레이딩 엔진 로그")
st.markdown(
    """
    🟢 **Golden** &nbsp;&nbsp; 🔴 **Dead** &nbsp;&nbsp; 🔵 **Pending** &nbsp;&nbsp; ⚪ **Neutral**
"""
)
logs = fetch_logs(user_id, limit=200)
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
                "시간": st.column_config.Column(width="medium", label="기록시각(DB)"),
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
        # ✅ 코인이 거의 없을 때 (5000원 이하는 무시)
        coin_value = coin_balance * last_price if last_price else 0
        if coin_value < 5000:
            trader = UpbitTrader(
                user_id, risk_pct=params_obj.order_ratio, test_mode=(not is_live)
            )
            msg = force_buy_in(user_id, trader, params_obj.upbit_ticker, interval_sec=params_obj.interval_sec)
            if msg.startswith("❌"):
                st.error(msg, icon="⚠️")
            elif msg.startswith("[TEST]"):
                st.success(msg, icon="✅")
            else:
                st.info(msg, icon="📡")

            # ✅ LIVE 모드: 주문 후 잔고 즉시 새로고침
            if is_live and not msg.startswith("❌"):
                time.sleep(2)  # Reconciler가 처리할 시간 제공
                st.session_state["needs_balance_refresh"] = True
                st.rerun()
        else:
            st.warning(f"⚠️ 강제매수 불가: 코인 보유 중 ({coin_value:,.0f}원 상당)")
with btn_col2:
    if st.button("🛑 강제매도하기", use_container_width=True):
        # ✅ 코인이 있을 때 (5000원 이상)
        coin_value = coin_balance * last_price if last_price else 0
        if coin_value >= 5000:
            trader = UpbitTrader(
                user_id, risk_pct=params_obj.order_ratio, test_mode=(not is_live)
            )
            msg = force_liquidate(user_id, trader, params_obj.upbit_ticker, interval_sec=params_obj.interval_sec)
            if msg.startswith("❌"):
                st.error(msg, icon="⚠️")
            elif msg.startswith("[TEST]"):
                st.success(msg, icon="✅")
            else:
                st.info(msg, icon="📡")

            # ✅ LIVE 모드: 주문 후 잔고 즉시 새로고침
            if is_live and not msg.startswith("❌"):
                time.sleep(2)  # Reconciler가 처리할 시간 제공
                st.session_state["needs_balance_refresh"] = True
                st.rerun()
        else:
            st.warning(f"⚠️ 강제매도 불가: 코인 보유량 부족 ({coin_value:,.0f}원 상당)")
with btn_col3:
    if st.button("🛑 트레이딩 엔진 종료", use_container_width=True):
        engine_manager.stop_engine(user_id)
        insert_log(user_id, "INFO", f"🛑 트레이딩 엔진 수동 종료됨 ({mode})")
        st.session_state.engine_started = False
        time.sleep(0.2)
        st.rerun()
with btn_col4:
    if st.button("💥 시스템 초기화", use_container_width=True):
        params = urlencode({"virtual_krw": virtual_krw, "user_id": user_id, "mode": mode})
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
    return "사용" if params_obj.macd_exit_enabled else "미사용"


def get_signal_confirm_enabled() -> str:
    return "사용" if params_obj.signal_confirm_enabled else "미사용"


# ★ 전략 요약 HTML 동적으로 구성
strategy_html_parts = [
    f"<b>Strategy:</b> {strategy_tag}",
    f"<b>Mode:</b> {mode}",
    f"<b>Ticker:</b> {params_obj.ticker}",
    f"<b>Interval:</b> {get_interval_label(params_obj.interval)}",
]

if is_macd:
    # MACD 전략일 때만 MACD 상세 파라미터 표시
    strategy_html_parts.append(
        f"<b>MACD:</b> Fast={params_obj.fast_period}, "
        f"Slow={params_obj.slow_period}, Signal={params_obj.signal_period}, "
        f"기준값={params_obj.macd_threshold}"
    )
    strategy_html_parts.append(
        f"<b>MACD Exit:</b> {get_macd_exit_enabled()}, Signal Confirm: {get_signal_confirm_enabled()}"
    )
elif is_ema:
    # EMA 전략: 별도 매수/매도 확인
    use_separate = getattr(params_obj, "use_separate_ema", True)
    base_ema = getattr(params_obj, "base_ema_period", 200)
    ma_type_raw = getattr(params_obj, "ma_type", "SMA")

    # ma_type 표시 매핑
    ma_type_display = {
        "SMA": "SMA(단순이동평균)",
        "EMA": "EMA(지수이동평균)",
        "WMA": "WMA(가중이동평균)"
    }.get(ma_type_raw, ma_type_raw)

    if use_separate:
        # 별도 매수/매도 EMA
        fast_buy = getattr(params_obj, "fast_buy", None) or params_obj.fast_period
        slow_buy = getattr(params_obj, "slow_buy", None) or params_obj.slow_period
        fast_sell = getattr(params_obj, "fast_sell", None) or params_obj.fast_period
        slow_sell = getattr(params_obj, "slow_sell", None) or params_obj.slow_period
        strategy_html_parts.append(
            f"<b>EMA (Separate):</b> Buy={fast_buy}/{slow_buy}, Sell={fast_sell}/{slow_sell}, MA계산={ma_type_display}"
        )
    else:
        # 공통 EMA
        strategy_html_parts.append(
            f"<b>EMA (Common):</b> Fast={params_obj.fast_period}, Slow={params_obj.slow_period}, MA계산={ma_type_display}"
        )

strategy_html_parts.append(
    f"<b>TP/SL:</b> {params_obj.take_profit*100:.1f}% / {params_obj.stop_loss*100:.1f}%"
)
strategy_html_parts.append(
    f"<b>Order 비율:</b> {params_obj.order_ratio*100:.0f}%"
)
strategy_html_parts.append(
    f"<b>최소 진입 Bar:</b> {params_obj.min_holding_period}"
)
strategy_html_parts.append(
    f"<b>Cross Over:</b> {params_obj.macd_crossover_threshold}"
)

st.markdown(
    "<div style=\"padding: 1em; border-radius: 0.5em; background-color: #f0f2f6; color: #111; border: 1px solid #ccc; font-size: 16px; font-weight: 500\">"
    + " &nbsp;|&nbsp; ".join(strategy_html_parts) +
    "</div>",
    unsafe_allow_html=True,
)
st.write("")

st.divider()

# ★ 전략별 Condition JSON 파일명:
#   - MACD: {user_id}_MACD_buy_sell_conditions.json
#   - EMA : {user_id}_EMA_buy_sell_conditions.json
target_filename = f"{user_id}_{strategy_tag}_{CONDITIONS_JSON_FILENAME}"
SAVE_PATH = Path(target_filename)

# ★ MACD용 조건 정의
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
}

# ★ 현재 전략에 맞는 조건 세트 선택
if is_ema:
    BUY_CONDITIONS = EMA_BUY_CONDITIONS
    SELL_CONDITIONS = EMA_SELL_CONDITIONS
else:
    BUY_CONDITIONS = MACD_BUY_CONDITIONS
    SELL_CONDITIONS = MACD_SELL_CONDITIONS


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
    # ★ 현재 전략 이름도 같이 표기
    st.subheader(f"⚙️ 매수 전략 (Strategy: {strategy_tag})")
with col2:
    if st.button("🛠️ 설정", use_container_width=True):
        params = urlencode({
            "virtual_krw": virtual_krw,
            "user_id": user_id,
            "mode": mode,
            # ★ set_buy_sell_conditions 쪽에서 전략 분기할 수 있도록 넘겨줌
            "strategy": strategy_tag,
        })
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

st.subheader(f"⚙️ 매도 전략 (Strategy: {strategy_tag})")
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

st.divider()

# ------------------------------------------------------------
# 📑 감사로그 뷰어 이동
# ------------------------------------------------------------
st.subheader("📑 감사 로그")

c1, c2, c3, c4 = st.columns([2, 2, 2, 2])

with c1:
    # 실패한 BUY 평가만 보기 (기본 True)
    audit_only_failed = st.toggle("Only failed(BUY)", value=True, key="audit_only_failed")

with c2:
    # 행 개수
    audit_rows = st.number_input("Rows", min_value=100, max_value=20000, value=2000, step=100, key="audit_rows")

with c3:
    # 기본 탭 선택 (buy|sell|trades|settings)
    default_tab = st.selectbox("Default Tab", ["buy", "sell", "trades", "settings"], index=0, key="audit_default_tab")

with c4:
    # 이동 버튼
    if st.button("🔍 감사로그 뷰어 열기", use_container_width=True):
        # ticker 파라미터는 둘 중 있는 값으로 (프로젝트에 따라 params_obj.upbit_ticker 또는 params_obj.ticker 사용)
        ticker_param = getattr(params_obj, "upbit_ticker", None) or getattr(params_obj, "ticker", "")

        audit_params = urlencode({
            "user_id": user_id,
            "ticker": ticker_param,
            "rows": int(audit_rows),
            "only_failed": int(bool(audit_only_failed)),
            "tab": default_tab,  # buy/sell/trades/settings 중 하나
            "mode": mode,
            # ★ 감사로그에서도 전략별 필터링을 하고 싶다면 strategy도 전달 (지금은 써도 되고 안 써도 됨)
            "strategy": strategy_tag,
        })

        next_page = "audit_viewer"  # 👈 pages/audit_viewer.py 파일명 기준 (아래 Step 2)
        # 메타 리프레시 + switch_page 병행 (현 코드 스타일과 통일)
        st.markdown(f'<meta http-equiv="refresh" content="0; url=./{next_page}?{audit_params}">', unsafe_allow_html=True)
        st.switch_page(next_page)

# 어디서든 임시 로그:
with get_db(user_id) as conn:
    ticker_param = getattr(params_obj, "upbit_ticker", None) or getattr(params_obj, "ticker", "")
    # print("orders cols:", [r[1] for r in conn.execute("PRAGMA table_info(orders)")])
    # print(conn.execute("SELECT COUNT(*) FROM orders WHERE user_id=? AND ticker=?", (user_id, ticker_param)).fetchone())

st.divider()

from ui.charts import macd_altair_chart, ema_altair_chart, debug_time_meta, _minus_9h_index
from core.data_feed import get_ohlcv_once

# ...
ticker = getattr(params_obj, "upbit_ticker", None) or params_obj.ticker
interval_code = getattr(params_obj, "interval", params_obj.interval)

df_live = get_ohlcv_once(ticker, interval_code, count=600)  # 최근 600봉

# ★ 차트 제목도 전략 표시 (MA 타입 포함)
if strategy_tag == "EMA":
    ma_type_display = getattr(params_obj, "ma_type", "EMA")
    st.markdown(f"### 📈 Price & Indicators ({mode}) : `{ticker}` · Strategy={strategy_tag} · MA={ma_type_display}")
else:
    st.markdown(f"### 📈 Price & Indicators ({mode}) : `{ticker}` · Strategy={strategy_tag}")

# 전략별 차트 렌더링
if strategy_tag == "EMA":
    # ✅ 사용자가 선택한 MA 타입 가져오기
    ma_type = getattr(params_obj, "ma_type", "EMA")

    # ✅ 로그 추가 (검증용)
    logger.info(f"[CHART] MA 타입={ma_type} | 전략과 동일하게 표시")

    ema_altair_chart(
        df_live,
        use_separate=getattr(params_obj, "use_separate_ema", True),
        fast_buy=getattr(params_obj, "fast_buy", None) or params_obj.fast_period,
        slow_buy=getattr(params_obj, "slow_buy", None) or params_obj.slow_period,
        fast_sell=getattr(params_obj, "fast_sell", None) or params_obj.fast_period,
        slow_sell=getattr(params_obj, "slow_sell", None) or params_obj.slow_period,
        base=getattr(params_obj, "base_ema_period", 200),
        ma_type=ma_type,  # ✅ ma_type 파라미터 전달
        max_bars=500,
    )
else:
    # MACD 전략 (기본)
    macd_altair_chart(
        df_live,
        fast=params_obj.fast_period,
        slow=params_obj.slow_period,
        signal=params_obj.signal_period,
        max_bars=500,
    )

# debug_time_meta(df_live, "raw")  # tz: None 이고 값이 이미 KST일 가능성
# debug_time_meta(_minus_9h_index(df_live), "kst-naive")  # tz: None이어야 정상

from services.db import fetch_order_statuses

rows = fetch_order_statuses(user_id, limit=10, ticker=ticker)
for r in rows:
    print(r)
