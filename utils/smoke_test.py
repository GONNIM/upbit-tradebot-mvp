# --- utils/smoke_test.py (예: 이 파일로 분리하거나, 현재 페이지 상단에 배치) ---
import sqlite3
import traceback
import streamlit as st

from services.init_db import init_db_if_needed, get_db_path
from services.db import (
    insert_settings_snapshot,
    insert_buy_eval,
    insert_sell_eval,
    insert_trade_audit,
)


def render_db_smoke_test(user_id: str, ticker: str = "KRW-BTC", interval_sec: int = 60):
    """
    Streamlit용 DB 스모크 테스트 위젯 렌더링:
      - 🧪 Audit 4종 insert (settings/buy/sell/trades)
      - 📊 Audit 테이블 건수 조회
    """
    if not user_id:
        st.warning("user_id가 비어 있어 스모크 테스트를 진행할 수 없습니다.")
        return

    # 스키마 보장 + 현재 사용하는 DB 경로 표시
    init_db_if_needed(user_id)
    db_path = get_db_path(user_id)
    st.caption(f"🗄️ DB file: `{db_path}`")

    col1, col2 = st.columns(2)

    with col1:
        if st.button("🧪 DB 스모크 테스트 (Audit 4종 Insert)", use_container_width=True):
            try:
                # 1) settings
                insert_settings_snapshot(
                    user_id=user_id, ticker=ticker, interval_sec=interval_sec,
                    tp=0.03, sl=0.01, ts_pct=0.02,
                    signal_gate=True, threshold=0.0,
                    buy_dict={"golden_cross": True, "signal_positive": True},
                    sell_dict={"take_profit": True, "trailing_stop": True}
                )
                # 2) buy_eval
                insert_buy_eval(
                    user_id=user_id, ticker=ticker, interval_sec=interval_sec, bar=100,
                    price=100.0, macd=0.01, signal=0.02,
                    have_position=False, overall_ok=True,
                    failed_keys=[], checks={"signal_positive": {"enabled":1, "pass":1}},
                    notes="SMOKE"
                )
                # 3) sell_eval
                insert_sell_eval(
                    user_id=user_id, ticker=ticker, interval_sec=interval_sec, bar=110,
                    price=103.0, macd=-0.01, signal=-0.02,
                    tp_price=103.0, sl_price=99.0, highest=104.0,
                    ts_pct=0.02, ts_armed=True, bars_held=7,
                    checks={"take_profit": {"enabled":1, "pass":1}},
                    triggered=True, trigger_key="Take Profit", notes="SMOKE"
                )
                # 4) trades
                insert_trade_audit(
                    user_id=user_id, ticker=ticker, interval_sec=interval_sec, bar=110,
                    kind="SELL", reason="Take Profit", price=103.0, macd=-0.01, signal=-0.02,
                    entry_price=100.0, entry_bar=100, bars_held=10,
                    tp=103.0, sl=99.0, highest=104.0, ts_pct=0.02, ts_armed=True
                )

                st.success("✅ Audit 4종 insert 성공")
            except Exception as e:
                st.error(f"❌ Audit insert 실패: {e}")
                st.code(traceback.format_exc())

    with col2:
        if st.button("📊 Audit 테이블 건수 보기", use_container_width=True):
            try:
                conn = sqlite3.connect(db_path)
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM audit_settings"); a = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM audit_buy_eval"); b = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM audit_sell_eval"); c = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM audit_trades"); d = cur.fetchone()[0]
                conn.close()

                st.info(f"settings={a}, buy_eval={b}, sell_eval={c}, trades={d}")
            except Exception as e:
                st.error(f"❌ Count 실패: {e}")
                st.code(traceback.format_exc())
