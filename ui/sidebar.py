import streamlit as st
from engine.params import LiveParams
from typing import Optional


INTERVAL_OPTIONS: dict[str, str] = {
    "1분봉": "minute1",
    "3분봉": "minute3",
    "5분봉": "minute5",
    "10분봉": "minute10",
    "15분봉": "minute15",
    "30분봉": "minute30",
    "60분봉": "minute60",
    "일봉": "day",
}

CASH_OPTIONS = {
    "10-percent": {
        "button": "10%",
        "ratio": 0.1,
    },
    "25-percent": {
        "button": "25%",
        "ratio": 0.25,
    },
    "50-percent": {
        "button": "50%",
        "ratio": 0.5,
    },
    "100-percent": {
        "button": "100%",
        "ratio": 1,
    },
}


def make_sidebar() -> Optional[LiveParams]:
    """Render sidebar form and return validated params (or None)."""
    with st.sidebar:
        st.header("⚙️ 파라미터 설정")
        with st.form("input_form"):
            ticker = st.text_input("거래 종목", value="DOGE")
            interval_name = st.selectbox(
                "차트 단위", list(INTERVAL_OPTIONS.keys()), index=0
            )

            fast = st.number_input("단기 EMA", 5, 50, 12)
            slow = st.number_input("장기 EMA", 20, 100, 26)
            signal = st.number_input("신호선 기간", 5, 20, 7)
            macd_threshold = st.number_input("MACD 기준값", -10.0, 10.0, 0.0, 0.01)

            tp = st.number_input("Take Profit (%)", 0.1, 50.0, 5.0, 0.1) / 100
            sl = st.number_input("Stop Loss (%)", 0.1, 50.0, 1.0, 0.1) / 100

            macd_exit_enabled = st.checkbox(
                "📌 매도 전략: MACD EXIT",
                help="TP/SL 도달 전 Dead Cross + MACD 기준 초과 시 매도합니다.",
            )

            signal_confirm_enabled = st.checkbox(
                "📌 옵션 전략: MACD 기준선 통과 매매 타점",
                help="기본 전략(Golden Cross + MACD 기준 초과) 이후, Signal 선까지 MACD 기준 초과 시 매수합니다.",
            )

            st.write("주문총액 (KRW)")
            st.info(f"{st.session_state.order_amount:,.0f}")
            cash = st.session_state.order_amount

            st.subheader("파라미터 저장")
            str_submitted = "🧪 파라미터 저장하기 !!!"
            submitted = st.form_submit_button(str_submitted, use_container_width=True)

        st.write("")

        columns = st.columns(4)
        for i, (name, info) in enumerate(CASH_OPTIONS.items()):
            if columns[i].button(info["button"], key=name, use_container_width=True):
                st.session_state.order_ratio = info["ratio"]
                st.session_state.order_amount = (
                    st.session_state.virtual_amount * st.session_state.order_ratio
                )
                st.rerun()

        st.subheader("가상 보유자산")
        st.info(f"{st.session_state.virtual_amount:,.0f} KRW")

        if not submitted:
            return None

    try:
        return LiveParams(
            ticker=ticker,
            interval=INTERVAL_OPTIONS[interval_name],
            fast_period=int(fast),
            slow_period=int(slow),
            signal_period=int(signal),
            macd_threshold=macd_threshold,
            take_profit=tp,
            stop_loss=sl,
            cash=int(cash),
            order_ratio=st.session_state.order_ratio,
            macd_exit_enabled=macd_exit_enabled,
            signal_confirm_enabled=signal_confirm_enabled,
        )
    except Exception as exc:  # pylint: disable=broad-except
        st.error(f"❌ 파라미터 오류: {exc}")
        return None
