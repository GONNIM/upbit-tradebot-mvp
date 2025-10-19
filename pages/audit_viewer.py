import sqlite3
import json
import pandas as pd
import streamlit as st

from services.init_db import get_db_path
from services.db import fetch_buy_eval, fetch_trades_audit  # 기존 제공 함수 재사용

from services.db import fetch_buy_eval, fetch_trades_audit, get_account
from urllib.parse import urlencode

from streamlit_autorefresh import st_autorefresh
from config import REFRESH_INTERVAL

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

# -------------------
# 쿼리 파라미터
# -------------------
params = st.query_params
user_id = params.get("user_id", "")
ticker  = params.get("ticker", "")
rows    = int(params.get("rows", 2000))
only_failed = str(params.get("only_failed", "0")) in ("1", "true", "True")
default_tab = params.get("tab", "buy")  # buy|sell|trades|settings

db_path = get_db_path(user_id)

st.title("📑 감사 로그 뷰어")
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
    <span class="badge">🗄 DB: <span class="code">{db_path}</span></span>
  </div>
</div>
""", unsafe_allow_html=True)

# 🔙 대시보드로 이동
col_go, _ = st.columns([1, 5])
with col_go:
    # dashboard는 user_id와 virtual_krw를 쿼리로 받음 → virtual_krw 없으면 계정 KRW로 대체
    virtual_krw = int(params.get("virtual_krw", 0) or 0)
    if virtual_krw == 0:
        try:
            virtual_krw = int(get_account(user_id) or 0)
        except Exception:
            virtual_krw = 0

    if st.button("⬅️ 대시보드로 가기", use_container_width=True):
        next_page = "dashboard"
        qs = urlencode({"user_id": user_id, "virtual_krw": virtual_krw})
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
# BUY 평가
# -------------------
if section == "buy":
    st.subheader("🟢 BUY 평가 (audit_buy_eval)")
    df_buy = fetch_buy_eval(user_id, ticker=ticker or None, only_failed=only_failed, limit=rows) or []
    if df_buy:
        if isinstance(df_buy, list):
            df_buy = pd.DataFrame(
                df_buy,
                columns=["timestamp","ticker","interval_sec","bar","price","macd","signal",
                         "have_position","overall_ok","failed_keys","checks","notes"]
            )
        def _j(x):
            try:
                return json.loads(x) if isinstance(x, str) and x else x
            except Exception:
                return x
        df_buy["failed_keys"] = df_buy["failed_keys"].apply(_j)
        df_buy["checks"] = df_buy["checks"].apply(_j)
        df_buy["timestamp"] = pd.to_datetime(df_buy["timestamp"]).dt.strftime("%Y-%m-%d %H:%M:%S")
        st.dataframe(df_buy, use_container_width=True, hide_index=True)
    else:
        st.info("데이터가 없습니다.")

# -------------------
# SELL 평가
# -------------------
elif section == "sell":
    st.subheader("🔴 SELL 평가 (audit_sell_eval)")
    q = """
        SELECT timestamp, ticker, interval_sec, bar, price, macd, signal,
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
        df_sell["timestamp"] = pd.to_datetime(df_sell["timestamp"]).dt.strftime("%Y-%m-%d %H:%M:%S")
        st.dataframe(df_sell, use_container_width=True, hide_index=True)
    else:
        st.info("데이터가 없습니다.")

# -------------------
# 체결(Trades)
# -------------------
elif section == "trades":
    st.subheader("💹 체결 (audit_trades)")
    df_tr = fetch_trades_audit(user_id, ticker=ticker or None, limit=rows) or []
    if df_tr:
        if isinstance(df_tr, list):
            df_tr = pd.DataFrame(
                df_tr,
                columns=["timestamp","ticker","interval_sec","bar","type","reason","price",
                         "macd","signal","entry_price","entry_bar","bars_held","tp","sl",
                         "highest","ts_pct","ts_armed"]
            )
        df_tr["timestamp"] = pd.to_datetime(df_tr["timestamp"]).dt.strftime("%Y-%m-%d %H:%M:%S")
        st.dataframe(df_tr, use_container_width=True, hide_index=True)
    else:
        st.info("데이터가 없습니다.")

# -------------------
# 설정 스냅샷
# -------------------
elif section == "settings":
    st.subheader("⚙️ 설정 스냅샷 (audit_settings)")
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
        df_set["timestamp"] = pd.to_datetime(df_set["timestamp"]).dt.strftime("%Y-%m-%d %H:%M:%S")
        st.dataframe(df_set, use_container_width=True, hide_index=True)
    else:
        st.info("데이터가 없습니다.")
