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

def normalize_time_index(
    df: pd.DataFrame,
    *,
    source_tz: str = "UTC",
    target_tz: str = "Asia/Seoul",
) -> pd.DataFrame:
    _df = df.copy()
    if not isinstance(_df.index, pd.DatetimeIndex):
        return _df
    if _df.index.tz is None:
        _df.index = _df.index.tz_localize(source_tz)
    _df.index = _df.index.tz_convert(target_tz)
    _df.index = _df.index.tz_localize(None)
    _df = _df.sort_index()
    return _df

def normalize_time_index_friendly(
    df: pd.DataFrame,
    *,
    mode: str = "as_is",           # "as_is" | "utc_to_kst"
    source_tz: str = "UTC",
    target_tz: str = "Asia/Seoul",
) -> pd.DataFrame:
    """
    mode="as_is": 시각을 '절대' 움직이지 않음.
      - tz-aware면 tz를 제거(naive)해서 브라우저/Altair가 재해석 못하게 함.
      - tz-naive면 그대로 둠.
    mode="utc_to_kst": 입력이 '진짜 UTC'일 때만 사용.
      - tz-naive면 source_tz로 localize → target_tz로 convert → tz 제거(naive).
      - tz-aware면 그대로 target_tz로 convert → tz 제거(naive).
    """
    _df = df.copy()
    if not isinstance(_df.index, pd.DatetimeIndex):
        return _df

    if mode == "as_is":
        # 값은 그대로 두되, tz가 있으면 떼버려서(naive) 재해석 방지
        if _df.index.tz is not None:
            _df.index = _df.index.tz_localize(None)
        # tz가 원래부터 없으면 그대로 사용
        return _df.sort_index()

    if mode == "utc_to_kst":
        if _df.index.tz is None:
            _df.index = _df.index.tz_localize(source_tz)
        _df.index = _df.index.tz_convert(target_tz)
        _df.index = _df.index.tz_localize(None)  # 재해석 방지
        return _df.sort_index()

    # 알 수 없는 모드면 안전하게 as_is
    if _df.index.tz is not None:
        _df.index = _df.index.tz_localize(None)
    return _df.sort_index()

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
    source_tz: str = "UTC",
    target_tz: str = "Asia/Seoul",
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
    df = normalize_time_index_friendly(df)

    df_plot = df.reset_index().rename(columns={"index": "Time"})
    base = alt.Chart(df_plot).encode(x=alt.X("Time:T", axis=alt.Axis(format="%H:%M")))

    layers = []

    if show_price:
        # 윗패널: 캔들 + 고저선
        rule = base.mark_rule().encode(
            y="Low:Q",
            y2="High:Q",
            tooltip=[
                alt.Tooltip("Time:T", title="Time", format="%Y-%m-%d %H:%M"),
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
            alt.Tooltip("Time:T", title="Time", format="%Y-%m-%d %H:%M"),
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
    source_tz: str = "UTC",
    target_tz: str = "Asia/Seoul",
) -> None:
    """Matplotlib 간단 버전(정적)."""
    import matplotlib.pyplot as plt

    if df_raw is None or df_raw.empty:
        st.info("차트 표시할 데이터가 없습니다.")
        return

    df = df_raw.tail(max_bars)
    df = compute_macd(df, fast=fast, slow=slow, signal=signal)
    df = normalize_time_index_friendly(df)

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

def debug_time_meta(df: pd.DataFrame, label: str = "df"):
    """Streamlit에 시간 인덱스 메타와 예시를 뿌려서 원천 데이터가 로컬인지 점검."""
    if not isinstance(df.index, pd.DatetimeIndex):
        st.info(f"[{label}] index type: {type(df.index)} (DatetimeIndex 아님)")
        return
    tzinfo = df.index.tz
    st.write(f"[{label}] tz: {tzinfo} | naive={tzinfo is None} | len={len(df)}")
    if len(df) > 0:
        st.write(f"[{label}] head 3:", [df.index[i].isoformat() for i in range(min(3, len(df)))])
        st.write(f"[{label}] tail 3:", [df.index[-i-1].isoformat() for i in range(min(3, len(df)))])
