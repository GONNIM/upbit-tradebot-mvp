import sqlite3
import json
import pandas as pd
import streamlit as st

from services.init_db import get_db_path
from services.db import fetch_buy_eval, fetch_trades_audit  # 기존 제공 함수 재사용

from services.db import fetch_buy_eval, fetch_trades_audit, get_account
from engine.params import load_active_strategy_with_conditions, load_params
from urllib.parse import urlencode
from pathlib import Path

from streamlit_autorefresh import st_autorefresh
from config import REFRESH_INTERVAL, CONDITIONS_JSON_FILENAME

import time

# -------------------
# 기본 설정 & 사이드바 네비 숨기기
# -------------------
st.set_page_config(page_title="Audit Viewer", page_icon="📑", layout="wide")
st.markdown("<style>[data-testid='stSidebar']{display:none !important;}</style>", unsafe_allow_html=True)
st.markdown(
    """
    <style>
    /* 헤더와 본문 사이 간격 제거 */
    div.block-container {
        padding-top: 1rem;  /* 기본값은 3rem */
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
    </style>
    """,
    unsafe_allow_html=True,
)

# ✅ 자동 새로고침
st_autorefresh(interval=REFRESH_INTERVAL * 1000, key="dashboard_autorefresh")

# ✅ 쿼리 파라미터 처리
qp = st.query_params

def _get_param(qp, key, default=None):
    v = qp.get(key, default)
    if isinstance(v, list):
        return v[0]
    return v

user_id = _get_param(qp, "user_id", st.session_state.get("user_id", ""))
ticker_raw = _get_param(qp, "ticker", st.session_state.get("ticker", ""))
# ✅ ticker 정규화: "ETH" → "KRW-ETH" (DB 형식 매칭)
ticker = f"KRW-{ticker_raw}" if ticker_raw and not ticker_raw.startswith("KRW-") else ticker_raw
rows = int(_get_param(qp, "rows", st.session_state.get("rows", 2000)))
only_failed = str(_get_param(qp, "only_failed", st.session_state.get("only_failed", ""))) in ("1", "true", "True")
default_tab = _get_param(qp, "tab", st.session_state.get("tab", "buy"))  # buy|sell|trades|settings

raw_mode = _get_param(qp, "mode", st.session_state.get("mode", "TEST"))
mode = str(raw_mode).upper()
st.session_state["mode"] = mode
is_live = (mode == "LIVE")

# ✅ strategy_type 읽기 (URL → 활성 전략 파일(conditions 고려) → 세션 → 디폴트)
from config import DEFAULT_STRATEGY_TYPE
strategy_from_url = _get_param(qp, "strategy", None) or _get_param(qp, "strategy_type", None)
strategy_from_session = st.session_state.get("strategy_type", None)
# ✅ buy_sell_conditions.json까지 고려한 실제 전략 판정
strategy_from_file = load_active_strategy_with_conditions(user_id)
strategy_tag = (strategy_from_url or strategy_from_file or strategy_from_session or DEFAULT_STRATEGY_TYPE)
strategy_tag = str(strategy_tag).upper().strip()
st.session_state["strategy_type"] = strategy_tag

# 🔍 DEBUG: 전략 판정 과정 로깅
import logging
logger = logging.getLogger(__name__)
logger.info(f"[AuditViewer] Strategy detection: url={strategy_from_url}, file={strategy_from_file}, session={strategy_from_session}, final={strategy_tag}")

# ✅ params 로딩 (Base EMA GAP 전략 판정용)
params_strategy = "EMA" if strategy_tag == "BASE_EMA_GAP" else strategy_tag
from config import PARAMS_JSON_FILENAME
json_path = f"{user_id}_{PARAMS_JSON_FILENAME}"
params_obj = load_params(json_path, strategy_type=params_strategy)

# ✅ Base EMA GAP 모드 확인 (params.base_ema_gap_enabled 사용)
is_gap_mode = False
if params_obj and params_strategy == "EMA":
    is_gap_mode = getattr(params_obj, "base_ema_gap_enabled", False)
    logger.info(f"[AuditViewer] base_ema_gap_enabled={is_gap_mode}")

st.toast(f"🔍 Audit Viewer: Strategy={strategy_tag}, GAP mode={is_gap_mode}", icon="🔍")

db_path = get_db_path(user_id)

st.markdown(f"### 📑 감사 로그 뷰어")
st.markdown(f"🕒 현재 시각: {time.strftime('%Y-%m-%d %H:%M:%S')}")
# --- Context bar (sticky) ---
st.markdown("""
<style>
  .ctx { position: sticky; top: 0; z-index: 999; }
  .ctx .card {
    border: 1px solid #44444433;
    border-radius: 10px;
    padding: 10px 14px;
    margin: 6px 0 12px 0;
    background: linear-gradient(180deg, rgba(64,145,255,0.18), rgba(64,145,255,0.06));
    backdrop-filter: blur(4px);
  }
  .badge {
    display: inline-block; margin-right: 8px; margin-bottom: 4px;
    padding: 4px 10px; border-radius: 999px; font-weight: 700; font-size: 0.95rem;
    background: #1f6feb22; border: 1px solid #1f6feb55;
  }
  .code {
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    background: #00000022; padding: 2px 6px; border-radius: 6px;
  }
  /* 라이트 모드 튜닝 */
  @media (prefers-color-scheme: light) {
    .ctx .card { background: linear-gradient(180deg, #eaf2ff, #f6f9ff); }
    .badge { background: #eef3ff; border-color: #c7d8ff; }
    .code  { background: #eef2f7; }
  }
</style>
""", unsafe_allow_html=True)

st.markdown(f"""
<div class="ctx">
  <div class="card">
    <span class="badge">👤 user: <b>{user_id or '-'}</b></span>
    <span class="badge">🎯 ticker: <b>{ticker or '-'}</b></span>
    <span class="badge">📊 전략: <b>{strategy_tag}</b></span>
    <span class="badge">🗄 DB: <span class="code">{db_path}</span></span>
  </div>
</div>
""", unsafe_allow_html=True)

# 🔙 대시보드로 이동
col_go, _ = st.columns([1, 5])
with col_go:
    # dashboard는 user_id와 virtual_krw를 쿼리로 받음 → virtual_krw 없으면 계정 KRW로 대체
    raw_vk = _get_param(qp, "virtual_krw", st.session_state.get("virtual_krw", 0))

    try:
        virtual_krw = int(raw_vk)
    except (TypeError, ValueError):
        virtual_krw = int(st.session_state.get("virtual_krw", 0) or 0)

    if virtual_krw == 0:
        try:
            virtual_krw = int(get_account(user_id) or 0)
        except Exception:
            virtual_krw = 0

    if st.button("⬅️ 대시보드로 가기", use_container_width=True):
        next_page = "dashboard"
        qs = urlencode({
            "user_id": user_id,
            "virtual_krw": virtual_krw,
            "mode": mode,
            "strategy_type": strategy_tag,  # ✅ 현재 전략 타입 전달
        })
        st.markdown(f'<meta http-equiv="refresh" content="0; url=./{next_page}?{qs}">', unsafe_allow_html=True)
        st.switch_page(next_page)

# -------------------
# 로컬 쿼리 헬퍼 (매도평가/설정스냅샷)
# -------------------
def query(sql, params=()):
    con = sqlite3.connect(db_path)
    try:
        return pd.read_sql_query(sql, con, params=params)
    finally:
        con.close()

# --- 섹션 선택 (default_tab 반영) ---
label_map = [("🟢 BUY 평가", "buy"), ("🔴 SELL 평가", "sell"), ("💹 체결", "trades"), ("⚙️ 설정 스냅샷", "settings")]
labels = [l for l,_ in label_map]
key_from_label = {l:k for l,k in label_map}
default_idx = next((i for i,(_,k) in enumerate(label_map) if k == default_tab), 0)

choice = st.radio("보기", labels, index=default_idx, horizontal=True, key="audit_section")
section = key_from_label[choice]

st.divider()

# -------------------
# 전략별 칼럼명 매핑
# -------------------
# ✅ BASE_EMA_GAP는 EMA 기반 전략이므로 EMA와 동일하게 처리
if strategy_tag == "EMA" or strategy_tag == "BASE_EMA_GAP":
    INDICATOR_COL_RENAME = {
        "macd": "ema_fast",
        "signal": "ema_slow"
    }
    INDICATOR_DISPLAY_NAME = "BASE EMA GAP" if strategy_tag == "BASE_EMA_GAP" else "EMA"
else:  # MACD or others
    INDICATOR_COL_RENAME = {}
    INDICATOR_DISPLAY_NAME = "MACD"

# -------------------
# BUY 평가
# -------------------
if section == "buy":
    st.subheader(f"🟢 BUY 평가 (audit_buy_eval) - {INDICATOR_DISPLAY_NAME} 전략")
    df_buy = fetch_buy_eval(user_id, ticker=ticker or None, only_failed=only_failed, limit=rows) or []
    if df_buy:
        if isinstance(df_buy, list):
            df_buy = pd.DataFrame(
                df_buy,
                columns=["timestamp","bar_time","ticker","interval_sec","bar","price","macd","signal",
                         "have_position","overall_ok","failed_keys","checks","notes"]
            )
        def _j(x):
            try:
                return json.loads(x) if isinstance(x, str) and x else x
            except Exception:
                return x
        df_buy["failed_keys"] = df_buy["failed_keys"].apply(_j)
        df_buy["checks"] = df_buy["checks"].apply(_j)

        # ✅ bar_time이 NULL인 경우에만 계산 (하위 호환성)
        if "bar_time" in df_buy.columns and df_buy["bar_time"].isna().any():
            def _calc_bar_time(row):
                try:
                    ts = pd.to_datetime(row["timestamp"], format="ISO8601")
                    interval_min = int(row["interval_sec"]) // 60
                    if interval_min > 0:
                        minute = (ts.minute // interval_min) * interval_min
                        return ts.replace(minute=minute, second=0, microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
                    else:
                        return ts.strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    try:
                        return pd.to_datetime(row["timestamp"], format="ISO8601").strftime("%Y-%m-%d %H:%M:%S")
                    except Exception:
                        return str(row["timestamp"])
            # NULL인 row만 계산하여 채움
            mask = df_buy["bar_time"].isna()
            df_buy.loc[mask, "bar_time"] = df_buy[mask].apply(_calc_bar_time, axis=1)

        # ✅ timestamp 포맷팅 (안전한 개별 파싱)
        def _format_timestamp(ts):
            try:
                return pd.to_datetime(ts, format="ISO8601").strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                return str(ts)
        df_buy["timestamp"] = df_buy["timestamp"].apply(_format_timestamp)

        # ✅ bar_time 포맷팅 (DB에서 온 ISO 형식 → 읽기 쉬운 형식)
        if "bar_time" in df_buy.columns:
            df_buy["bar_time"] = df_buy["bar_time"].apply(_format_timestamp)

        # ✅ strategy_mode 추출 (checks에서)
        def _get_strategy_mode(checks):
            if isinstance(checks, dict):
                return checks.get('strategy_mode', None)
            return None

        df_buy["strategy_mode"] = df_buy["checks"].apply(_get_strategy_mode)

        # ✅ is_gap_strategy 컬럼 추가
        df_buy["is_gap_strategy"] = df_buy["strategy_mode"] == "BASE_EMA_GAP"

        # ⚠️ 데이터 필터링 제거 - 모든 데이터 표시, 테이블 구조만 is_gap_mode로 결정
        # (Base EMA GAP 전략 선택 시에도 기존 EMA 데이터를 볼 수 있어야 함)

        if df_buy.empty:
            st.info(f"BUY 평가 데이터가 없습니다.")
        else:
            # ✅ params.base_ema_gap_enabled로 판단 (dashboard 차트와 동일한 조건 사용)
            if is_gap_mode:
                # ✅ Base EMA GAP 전략: 특화 컬럼 추가
                def _extract_gap_info(row):
                    checks = row.get("checks", {})
                    if isinstance(checks, dict) and checks.get('strategy_mode') == 'BASE_EMA_GAP':
                        return pd.Series({
                            "gap_pct": checks.get("gap_pct", 0),
                            "gap_threshold": checks.get("gap_threshold", 0),
                            "gap_to_target": checks.get("gap_to_target", 0),
                            "price_needed": checks.get("price_needed", 0),
                            "condition_met": checks.get("condition_met", False),
                            "base_ema": checks.get("base_ema", 0),
                            "gap_status": checks.get("cross_status", "")
                        })
                    else:
                        return pd.Series({
                            "gap_pct": None,
                            "gap_threshold": None,
                            "gap_to_target": None,
                            "price_needed": None,
                            "condition_met": None,
                            "base_ema": None,
                            "gap_status": None
                        })

                gap_info = df_buy.apply(_extract_gap_info, axis=1)
                df_buy = pd.concat([df_buy, gap_info], axis=1)

                # GAP 상태 표시
                df_buy["gap_display"] = df_buy.apply(
                    lambda row: (
                        f"{row['gap_pct']:.2%}" if pd.notna(row['gap_pct']) else "-"
                    ), axis=1
                )
                df_buy["gap_diff_display"] = df_buy.apply(
                    lambda row: (
                        f"{'초과' if row['condition_met'] else '부족'} {abs(row['gap_to_target']):.2%}p"
                        if pd.notna(row['gap_to_target']) else "-"
                    ), axis=1
                )
                # ✅ 목표GAP % 변환
                df_buy["gap_threshold_display"] = df_buy.apply(
                    lambda row: (
                        f"{row['gap_threshold']:.2%}" if pd.notna(row['gap_threshold']) else "-"
                    ), axis=1
                )

                # 전략별 칼럼명 변경
                df_buy_display = df_buy.rename(columns=INDICATOR_COL_RENAME)

                # ✅ Base EMA GAP 전략 전용 컬럼 순서
                column_order = [
                    "timestamp", "bar_time", "ticker", "bar", "price",
                    "gap_status", "gap_display", "gap_threshold_display", "gap_diff_display",
                    "price_needed", "base_ema",
                    "overall_ok", "notes"
                ]
                column_order = [col for col in column_order if col in df_buy_display.columns]
                df_buy_display = df_buy_display[column_order]

                # 컬럼명 한글화
                df_buy_display = df_buy_display.rename(columns={
                    "timestamp": "기록시각",
                    "bar_time": "봉시각",
                    "ticker": "티커",
                    "bar": "BAR",
                    "price": "가격",
                    "gap_status": "GAP상태",
                    "gap_display": "현재GAP",
                    "gap_threshold_display": "목표GAP",
                    "gap_diff_display": "차이",
                    "price_needed": "매수가",
                    "base_ema": "Base EMA",
                    "overall_ok": "조건충족",
                    "notes": "메모"
                })

                st.info("📉 Base EMA GAP 전략 모드 - GAP 전용 컬럼 표시")
            else:
                # ✅ 일반 EMA/MACD 전략: 기존 로직
                df_buy["delta"] = df_buy["macd"] - df_buy["signal"]

                def _cross_type(delta):
                    if delta > 0:
                        return "🟢 Golden"
                    elif delta < 0:
                        return "🔴 Dead"
                    else:
                        return "⚪ Neutral"
                df_buy["cross_type"] = df_buy["delta"].apply(_cross_type)

                # 전략별 칼럼명 변경
                df_buy_display = df_buy.rename(columns=INDICATOR_COL_RENAME)

                # ✅ 컬럼 순서 재배치
                column_order = [
                    "timestamp", "bar_time", "ticker", "bar", "price", "delta", "cross_type",
                    "ema_fast" if (strategy_tag == "EMA" or strategy_tag == "BASE_EMA_GAP") else "macd",
                    "ema_slow" if (strategy_tag == "EMA" or strategy_tag == "BASE_EMA_GAP") else "signal",
                    "have_position", "overall_ok", "failed_keys", "checks", "notes", "interval_sec"
                ]
                column_order = [col for col in column_order if col in df_buy_display.columns]
                df_buy_display = df_buy_display[column_order]

            # ✅ Arrow 직렬화를 위해 dict/list 타입 컬럼을 문자열로 변환
            if "checks" in df_buy_display.columns:
                df_buy_display["checks"] = df_buy_display["checks"].apply(
                    lambda x: json.dumps(x, ensure_ascii=False) if isinstance(x, (dict, list)) else str(x) if x is not None else ""
                )
            if "failed_keys" in df_buy_display.columns:
                df_buy_display["failed_keys"] = df_buy_display["failed_keys"].apply(
                    lambda x: json.dumps(x, ensure_ascii=False) if isinstance(x, (dict, list)) else str(x) if x is not None else ""
                )

            st.dataframe(df_buy_display, use_container_width=True, hide_index=True)
    else:
        st.info("데이터가 없습니다.")

# -------------------
# SELL 평가
# -------------------
elif section == "sell":
    st.subheader(f"🔴 SELL 평가 (audit_sell_eval) - {INDICATOR_DISPLAY_NAME} 전략")
    q = """
        SELECT timestamp, bar_time, ticker, interval_sec, bar, price, macd, signal,
               tp_price, sl_price, highest, ts_pct, ts_armed, bars_held,
               checks, triggered, trigger_key, notes
        FROM audit_sell_eval
        WHERE 1=1
    """
    ps = []
    if ticker:
        q += " AND ticker = ?"; ps.append(ticker)
    q += " ORDER BY timestamp DESC LIMIT ?"; ps.append(rows)
    df_sell = query(q, tuple(ps))
    if not df_sell.empty:
        def _j(x):
            try:
                return json.loads(x) if isinstance(x, str) and x else x
            except Exception:
                return x
        df_sell["checks"] = df_sell["checks"].apply(_j)

        # ✅ bar_time이 NULL인 경우에만 계산 (하위 호환성)
        if "bar_time" in df_sell.columns and df_sell["bar_time"].isna().any():
            def _calc_bar_time(row):
                try:
                    ts = pd.to_datetime(row["timestamp"], format="ISO8601")
                    interval_min = int(row["interval_sec"]) // 60
                    if interval_min > 0:
                        minute = (ts.minute // interval_min) * interval_min
                        return ts.replace(minute=minute, second=0, microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
                    else:
                        return ts.strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    try:
                        return pd.to_datetime(row["timestamp"], format="ISO8601").strftime("%Y-%m-%d %H:%M:%S")
                    except Exception:
                        return str(row["timestamp"])
            # NULL인 row만 계산하여 채움
            mask = df_sell["bar_time"].isna()
            df_sell.loc[mask, "bar_time"] = df_sell[mask].apply(_calc_bar_time, axis=1)

        # ✅ timestamp 포맷팅 (안전한 개별 파싱)
        def _format_timestamp(ts):
            try:
                return pd.to_datetime(ts, format="ISO8601").strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                return str(ts)
        df_sell["timestamp"] = df_sell["timestamp"].apply(_format_timestamp)

        # ✅ bar_time 포맷팅 (DB에서 온 ISO 형식 → 읽기 쉬운 형식)
        if "bar_time" in df_sell.columns:
            df_sell["bar_time"] = df_sell["bar_time"].apply(_format_timestamp)

        # ✅ strategy_mode 추출 (checks에서)
        def _get_strategy_mode(checks):
            if isinstance(checks, dict):
                return checks.get('strategy_mode', None)
            return None

        df_sell["strategy_mode"] = df_sell["checks"].apply(_get_strategy_mode)

        # ✅ is_gap_strategy 컬럼 추가
        df_sell["is_gap_strategy"] = df_sell["strategy_mode"] == "BASE_EMA_GAP"

        # ⚠️ 데이터 필터링 제거 - 모든 데이터 표시, 테이블 구조만 is_gap_mode로 결정
        # (Base EMA GAP 전략 선택 시에도 기존 EMA 데이터를 볼 수 있어야 함)

        if df_sell.empty:
            st.info(f"SELL 평가 데이터가 없습니다.")
        else:
            # ✅ params.base_ema_gap_enabled로 판단 (dashboard 차트와 동일한 조건 사용)
            if is_gap_mode:
                # ✅ Base EMA GAP 전략: SELL 특화 컬럼 추가
                def _extract_sell_gap_info(row):
                    checks = row.get("checks", {})
                    if isinstance(checks, dict) and checks.get('strategy_mode') == 'BASE_EMA_GAP':
                        pnl_pct = checks.get("pnl_pct", 0)
                        entry_price = checks.get("entry_price", 0)
                        base_ema = checks.get("ema_base", 0)

                        return pd.Series({
                            "pnl_pct": pnl_pct,
                            "pnl_display": f"{pnl_pct:.2%}" if pnl_pct is not None else "-",
                            "entry_price": entry_price,
                            "base_ema": base_ema,
                            "trigger_reason": checks.get("trigger_reason", checks.get("reason", "-"))
                        })
                    else:
                        return pd.Series({
                            "pnl_pct": None,
                            "pnl_display": "-",
                            "entry_price": None,
                            "base_ema": None,
                            "trigger_reason": "-"
                        })

                sell_gap_info = df_sell.apply(_extract_sell_gap_info, axis=1)
                df_sell = pd.concat([df_sell, sell_gap_info], axis=1)

                # 전략별 칼럼명 변경
                df_sell_display = df_sell.rename(columns=INDICATOR_COL_RENAME)

                # ✅ Base EMA GAP 전략 SELL 전용 컬럼 순서
                column_order = [
                    "timestamp", "bar_time", "ticker", "bar", "price",
                    "pnl_display", "tp_price", "sl_price", "highest", "base_ema",
                    "bars_held", "triggered", "trigger_reason", "notes"
                ]
                column_order = [col for col in column_order if col in df_sell_display.columns]
                df_sell_display = df_sell_display[column_order]

                # 컬럼명 한글화
                df_sell_display = df_sell_display.rename(columns={
                    "timestamp": "기록시각",
                    "bar_time": "봉시각",
                    "ticker": "티커",
                    "bar": "BAR",
                    "price": "현재가",
                    "pnl_display": "수익률",
                    "tp_price": "목표가",
                    "sl_price": "손절가",
                    "highest": "최고가",
                    "base_ema": "Base EMA",
                    "bars_held": "보유봉",
                    "triggered": "트리거",
                    "trigger_reason": "사유",
                    "notes": "메모"
                })

                st.info("📈 Base EMA GAP 전략 모드 - SELL 평가 전용 테이블")
            else:
                # ✅ 일반 EMA/MACD 전략: 기존 로직
                # ✅ delta 계산: macd - signal (전략별 칼럼명 변경 전에 계산)
                df_sell["delta"] = df_sell["macd"] - df_sell["signal"]

                # ✅ cross_type 계산: Golden / Dead / Neutral
                def _cross_type(delta):
                    if delta > 0:
                        return "🟢 Golden"
                    elif delta < 0:
                        return "🔴 Dead"
                    else:
                        return "⚪ Neutral"
                df_sell["cross_type"] = df_sell["delta"].apply(_cross_type)

                # 전략별 칼럼명 변경
                df_sell_display = df_sell.rename(columns=INDICATOR_COL_RENAME)

                # ✅ 컬럼 순서 재배치: bar_time을 timestamp 바로 뒤에, delta 다음에 cross_type 추가
                column_order = [
                    "timestamp", "bar_time", "ticker", "bar", "price", "tp_price", "sl_price", "highest", "delta", "cross_type",
                    "ema_fast" if (strategy_tag == "EMA" or strategy_tag == "BASE_EMA_GAP") else "macd",
                    "ema_slow" if (strategy_tag == "EMA" or strategy_tag == "BASE_EMA_GAP") else "signal",
                    "ts_pct", "ts_armed", "bars_held", "checks", "triggered", "trigger_key", "notes", "interval_sec"
                ]
                # 존재하는 컬럼만 필터링
                column_order = [col for col in column_order if col in df_sell_display.columns]
                df_sell_display = df_sell_display[column_order]

            # ✅ Arrow 직렬화를 위해 dict/list 타입 컬럼을 문자열로 변환
            if "checks" in df_sell_display.columns:
                df_sell_display["checks"] = df_sell_display["checks"].apply(
                    lambda x: json.dumps(x, ensure_ascii=False) if isinstance(x, (dict, list)) else str(x) if x is not None else ""
                )

            st.dataframe(df_sell_display, use_container_width=True, hide_index=True)
    else:
        st.info("데이터가 없습니다.")

# -------------------
# 체결(Trades)
# -------------------
elif section == "trades":
    st.subheader(f"💹 체결 (audit_trades) - {INDICATOR_DISPLAY_NAME} 전략")
    df_tr = fetch_trades_audit(user_id, ticker=ticker or None, limit=rows) or []
    if df_tr:
        if isinstance(df_tr, list):
            df_tr = pd.DataFrame(
                df_tr,
                columns=["timestamp","bar_time","ticker","interval_sec","bar","type","reason","price",
                         "macd","signal","entry_price","entry_bar","bars_held","tp","sl",
                         "highest","ts_pct","ts_armed"]
            )

        # ✅ bar_time이 NULL인 경우에만 계산 (하위 호환성)
        if "bar_time" in df_tr.columns and df_tr["bar_time"].isna().any():
            def _calc_bar_time(row):
                try:
                    ts = pd.to_datetime(row["timestamp"], format="ISO8601")
                    interval_min = int(row["interval_sec"]) // 60
                    if interval_min > 0:
                        minute = (ts.minute // interval_min) * interval_min
                        return ts.replace(minute=minute, second=0, microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
                    else:
                        return ts.strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    try:
                        return pd.to_datetime(row["timestamp"], format="ISO8601").strftime("%Y-%m-%d %H:%M:%S")
                    except Exception:
                        return str(row["timestamp"])
            # NULL인 row만 계산하여 채움
            mask = df_tr["bar_time"].isna()
            df_tr.loc[mask, "bar_time"] = df_tr[mask].apply(_calc_bar_time, axis=1)

        # ✅ timestamp 포맷팅 (안전한 개별 파싱)
        def _format_timestamp(ts):
            try:
                return pd.to_datetime(ts, format="ISO8601").strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                return str(ts)
        df_tr["timestamp"] = df_tr["timestamp"].apply(_format_timestamp)

        # ✅ bar_time 포맷팅 (DB에서 온 ISO 형식 → 읽기 쉬운 형식)
        if "bar_time" in df_tr.columns:
            df_tr["bar_time"] = df_tr["bar_time"].apply(_format_timestamp)

        # ✅ params.base_ema_gap_enabled로 판단 (dashboard 차트와 동일한 조건 사용)
        if is_gap_mode:
            # ✅ Base EMA GAP 전략: 간소화된 체결 테이블
            # 전략별 칼럼명 변경
            df_tr_display = df_tr.rename(columns=INDICATOR_COL_RENAME)

            # ✅ Base EMA GAP 전용 컬럼 순서 (delta 제거, 핵심 정보만)
            column_order = [
                "timestamp", "bar_time", "ticker", "bar", "type", "reason", "price",
                "entry_price", "bars_held", "tp", "sl", "highest"
            ]
            column_order = [col for col in column_order if col in df_tr_display.columns]
            df_tr_display = df_tr_display[column_order]

            # 컬럼명 한글화
            df_tr_display = df_tr_display.rename(columns={
                "timestamp": "체결시각",
                "bar_time": "봉시각",
                "ticker": "티커",
                "bar": "BAR",
                "type": "유형",
                "reason": "사유",
                "price": "체결가",
                "entry_price": "진입가",
                "bars_held": "보유봉",
                "tp": "목표가",
                "sl": "손절가",
                "highest": "최고가"
            })

            st.info("📊 Base EMA GAP 전략 모드 - 체결 내역")
        else:
            # ✅ 일반 EMA/MACD 전략: 기존 로직
            # ✅ delta 계산: macd - signal (전략별 칼럼명 변경 전에 계산)
            df_tr["delta"] = df_tr["macd"] - df_tr["signal"]

            # 전략별 칼럼명 변경
            df_tr_display = df_tr.rename(columns=INDICATOR_COL_RENAME)

            # ✅ 컬럼 순서 재배치: bar_time을 timestamp 바로 뒤에
            column_order = [
                "timestamp", "bar_time", "ticker", "bar", "type", "reason", "price", "delta",
                "ema_fast" if (strategy_tag == "EMA" or strategy_tag == "BASE_EMA_GAP") else "macd",
                "ema_slow" if (strategy_tag == "EMA" or strategy_tag == "BASE_EMA_GAP") else "signal",
                "entry_price", "entry_bar", "bars_held", "tp", "sl", "highest", "ts_pct", "ts_armed", "interval_sec"
            ]
            # 존재하는 컬럼만 필터링
            column_order = [col for col in column_order if col in df_tr_display.columns]
            df_tr_display = df_tr_display[column_order]

        st.dataframe(df_tr_display, use_container_width=True, hide_index=True)
    else:
        st.info("데이터가 없습니다.")

# -------------------
# 설정 스냅샷
# -------------------
elif section == "settings":
    st.subheader(f"⚙️ 설정 스냅샷 (audit_settings) - {INDICATOR_DISPLAY_NAME} 전략")
    q = """
        SELECT timestamp, ticker, interval_sec, tp, sl, ts_pct,
               signal_gate, threshold, buy_json, sell_json
        FROM audit_settings
        WHERE 1=1
    """
    ps = []
    if ticker:
        q += " AND ticker = ?"; ps.append(ticker)
    q += " ORDER BY timestamp DESC LIMIT ?"; ps.append(rows)
    df_set = query(q, tuple(ps))
    if not df_set.empty:
        def _j(x):
            try:
                return json.loads(x) if isinstance(x, str) and x else x
            except Exception:
                return x
        df_set["buy_json"] = df_set["buy_json"].apply(_j)
        df_set["sell_json"] = df_set["sell_json"].apply(_j)
        df_set["signal_gate"] = df_set["signal_gate"].map({0:"OFF",1:"ON"})
        df_set["timestamp"] = pd.to_datetime(df_set["timestamp"], format="ISO8601").dt.strftime("%Y-%m-%d %H:%M:%S")
        st.dataframe(df_set, use_container_width=True, hide_index=True)
    else:
        st.info("데이터가 없습니다.")
