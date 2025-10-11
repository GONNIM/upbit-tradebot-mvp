from __future__ import annotations
import pandas as pd
import altair as alt
import streamlit as st

__all__ = [
    "compute_macd",
    "prep_for_chart",
    "macd_altair_chart",
    "macd_mpl_chart",
]

def compute_macd(
    df: pd.DataFrame,
    close_col: str = "Close",
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> pd.DataFrame:
    """EMA 기반 MACD/Signal/Histogram 계산."""
    out = df.copy()
    ema_fast = out[close_col].ewm(span=fast, adjust=False).mean()
    ema_slow = out[close_col].ewm(span=slow, adjust=False).mean()
    out["MACD"] = ema_fast - ema_slow
    out["Signal"] = out["MACD"].ewm(span=signal, adjust=False).mean()
    out["Hist"] = out["MACD"] - out["Signal"]
    return out

def prep_for_chart(df: pd.DataFrame, local_tz: str = "Asia/Seoul") -> pd.DataFrame:
    """표시용 타임존/정렬 보정(UTC→로컬). DatetimeIndex만 처리."""
    _df = df.copy()
    if isinstance(_df.index, pd.DatetimeIndex):
        if _df.index.tz is None:
            _df.index = _df.index.tz_localize("UTC").tz_convert(local_tz)
        else:
            _df.index = _df.index.tz_convert(local_tz)
        _df = _df.sort_index()
    return _df

def macd_altair_chart(
    df_raw: pd.DataFrame,
    *,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
    max_bars: int = 500,
    show_price: bool = True,
    height_price: int = 250,
    height_macd: int = 150,
    use_container_width: bool = True,
    dark_bg: bool = False
) -> None:
    """
    Altair MACD/Signal/Histogram 차트 렌더링.
    df_raw: 컬럼에 Open/High/Low/Close 포함, DatetimeIndex(UTC 권장).
    """
    if df_raw is None or df_raw.empty:
        st.info("차트 표시할 데이터가 없습니다.")
        return

    df = df_raw.tail(max_bars)
    df = compute_macd(df, fast=fast, slow=slow, signal=signal)
    df = prep_for_chart(df)

    df_plot = df.reset_index().rename(columns={"index": "Time"})
    base = alt.Chart(df_plot).encode(x="Time:T")

    layers = []

    if show_price:
        # 윗패널: 캔들 + 고저선
        rule = base.mark_rule().encode(
            y="Low:Q",
            y2="High:Q",
            tooltip=[
                alt.Tooltip("Time:T"),
                alt.Tooltip("Open:Q", format=".2f"),
                alt.Tooltip("High:Q", format=".2f"),
                alt.Tooltip("Low:Q", format=".2f"),
                alt.Tooltip("Close:Q", format=".2f"),
            ],
        )
        body = base.mark_bar().encode(
            y="Open:Q",
            y2="Close:Q",
            color=alt.condition("datum.Close >= datum.Open", alt.value("#26a69a"), alt.value("#ef5350")),
        )
        price_layer = (rule + body).properties(height=height_price)
        layers.append(price_layer)

    # 아랫패널: MACD/Signal + 히스토그램
    macd_line = base.mark_line(strokeWidth=1, color="white").encode(y=alt.Y("MACD:Q", title="MACD / Signal"))
    signal_line = base.mark_line(strokeWidth=1, color="red").encode(y="Signal:Q")
    hist = base.mark_bar().encode(
        y="Hist:Q",
        color=alt.condition("datum.Hist >= 0", alt.value("#26a69a"), alt.value("#ef5350")),
        tooltip=[
            alt.Tooltip("Time:T"),
            alt.Tooltip("MACD:Q", format=".5f"),
            alt.Tooltip("Signal:Q", format=".5f"),
            alt.Tooltip("Hist:Q", format=".5f"),
        ],
    ).properties(height=height_macd)

    macd_panel = alt.layer(hist, macd_line, signal_line)
    layers.append(macd_panel)

    chart = alt.vconcat(*layers).resolve_scale(x="shared")
    st.altair_chart(chart.interactive(), use_container_width=use_container_width)

def macd_mpl_chart(
    df_raw: pd.DataFrame,
    *,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
    max_bars: int = 500,
) -> None:
    """Matplotlib 간단 버전(정적)."""
    import matplotlib.pyplot as plt

    if df_raw is None or df_raw.empty:
        st.info("차트 표시할 데이터가 없습니다.")
        return

    df = df_raw.tail(max_bars)
    df = compute_macd(df, fast=fast, slow=slow, signal=signal)
    df = prep_for_chart(df)

    times = df.index

    # 1) Price
    fig1, ax1 = plt.subplots(figsize=(10, 3))
    ax1.plot(times, df["Close"])
    ax1.set_title("Price")
    ax1.grid(True, alpha=0.3)
    st.pyplot(fig1)

    # 2) MACD / Signal + Histogram
    fig2, ax2 = plt.subplots(figsize=(10, 3))
    ax2.plot(times, df["MACD"], label="MACD")
    ax2.plot(times, df["Signal"], label="Signal")
    ax2.bar(times, df["Hist"])
    ax2.legend()
    ax2.set_title("MACD / Signal / Histogram")
    ax2.grid(True, alpha=0.3)
    st.pyplot(fig2)
