from __future__ import annotations
import pandas as pd
import altair as alt
import streamlit as st

__all__ = [
    "compute_macd",
    "compute_ema",
    "prep_for_chart",
    "macd_altair_chart",
    "ema_altair_chart",
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

def compute_ema(
    df: pd.DataFrame,
    close_col: str = "Close",
    use_separate: bool = True,
    fast_buy: int = 60,
    slow_buy: int = 200,
    fast_sell: int = 20,
    slow_sell: int = 60,
    base: int = 200,
    ma_type: str = "EMA",
) -> pd.DataFrame:
    """
    이동평균 라인 계산 (매수/매도 별도 or 공통).

    Args:
        df: OHLCV 데이터프레임
        close_col: 종가 컬럼명
        use_separate: True=매수/매도 별도, False=공통
        fast_buy: 매수용 Fast 기간
        slow_buy: 매수용 Slow 기간
        fast_sell: 매도용 Fast 기간
        slow_sell: 매도용 Slow 기간
        base: 기준 MA 기간
        ma_type: 이동평균 계산 방식 ("SMA" | "EMA" | "WMA")

    Returns:
        MA 지표가 추가된 데이터프레임
    """
    import numpy as np

    out = df.copy()
    ma_type = ma_type.upper().strip()

    # ========== MA 계산 함수 (strategy_v2.py와 동일한 로직) ==========
    def _calculate_ma(series, period: int):
        """
        이동평균 계산 통합 함수

        Args:
            series: 가격 데이터 (Close)
            period: 기간

        Returns:
            pandas Series
        """
        s = pd.Series(series)

        if ma_type == "SMA":
            # ✅ 단순이동평균 (Simple Moving Average)
            # 공식: (P₁ + P₂ + ... + Pₙ) / n
            return s.rolling(window=period).mean()

        elif ma_type == "EMA":
            # ✅ 지수이동평균 (Exponential Moving Average)
            # 공식: EMA(t) = α × P(t) + (1-α) × EMA(t-1)
            # where α = 2 / (period + 1)
            return s.ewm(span=period, adjust=False).mean()

        elif ma_type == "WMA":
            # ✅ 가중이동평균 (Weighted Moving Average)
            # 공식: WMA = (n×P₁ + (n-1)×P₂ + ... + 1×Pₙ) / (n×(n+1)/2)
            def wma(x):
                if len(x) < period:
                    return np.nan
                weights = np.arange(1, period + 1)
                return np.dot(x[-period:], weights) / weights.sum()

            return s.rolling(window=period).apply(wma, raw=True)

        else:
            # 폴백: EMA (기존 동작 유지)
            return s.ewm(span=period, adjust=False).mean()

    # ========== MA 계산 (기존 로직 유지, 계산 함수만 변경) ==========
    if use_separate:
        # 매수/매도 별도 MA
        out["EMA_Fast_Buy"] = _calculate_ma(out[close_col], fast_buy)
        out["EMA_Slow_Buy"] = _calculate_ma(out[close_col], slow_buy)
        out["EMA_Fast_Sell"] = _calculate_ma(out[close_col], fast_sell)
        out["EMA_Slow_Sell"] = _calculate_ma(out[close_col], slow_sell)
    else:
        # 공통 MA (fast_sell, slow_sell 사용)
        out["EMA_Fast"] = _calculate_ma(out[close_col], fast_sell)
        out["EMA_Slow"] = _calculate_ma(out[close_col], slow_sell)

    # 기준 MA
    out["EMA_Base"] = _calculate_ma(out[close_col], base)

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

# ✅ [DEPRECATED] 이전에는 data_feed.py의 9시간 오프셋 문제를 보정하기 위해 사용
# ✅ [2025-12-29] data_feed.py 수정으로 pyupbit이 KST로 반환하는 것을 올바르게 처리
# ✅ 이제 이 함수는 불필요하므로 no-op으로 변경 (호환성 유지)
def _minus_9h_index(df: pd.DataFrame) -> pd.DataFrame:
    # 더 이상 9시간 보정이 필요 없음 - 그대로 반환
    return df

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
    df = _minus_9h_index(df)

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
    macd_line = base.mark_line(strokeWidth=1, color="green").encode(y=alt.Y("MACD:Q", title="MACD / Signal"))
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

def ema_altair_chart(
    df_raw: pd.DataFrame,
    *,
    use_separate: bool = True,
    fast_buy: int = 60,
    slow_buy: int = 200,
    fast_sell: int = 20,
    slow_sell: int = 60,
    base: int = 200,
    ma_type: str = "EMA",
    max_bars: int = 500,
    show_price: bool = True,
    height_price: int = 400,
    height_ema: int = 150,
    use_container_width: bool = True,
    source_tz: str = "UTC",
    target_tz: str = "Asia/Seoul",
) -> None:
    """
    Altair EMA 차트 렌더링.

    Args:
        df_raw: 컬럼에 Open/High/Low/Close 포함, DatetimeIndex(UTC 권장)
        use_separate: True=매수/매도 별도, False=공통
        fast_buy: 매수용 Fast 기간
        slow_buy: 매수용 Slow 기간
        fast_sell: 매도용 Fast 기간
        slow_sell: 매도용 Slow 기간
        base: 기준 MA 기간
        ma_type: 이동평균 계산 방식 ("SMA" | "EMA" | "WMA")
        max_bars: 표시할 최대 봉 개수
        show_price: 가격 차트 표시 여부
        height_price: 가격 차트 높이
        height_ema: EMA 차트 높이
        use_container_width: 컨테이너 너비에 맞춤
        source_tz: 입력 데이터 시간대
        target_tz: 표시 시간대
    """
    if df_raw is None or df_raw.empty:
        st.info("차트 표시할 데이터가 없습니다.")
        return

    df = df_raw.tail(max_bars)
    df = compute_ema(
        df,
        use_separate=use_separate,
        fast_buy=fast_buy,
        slow_buy=slow_buy,
        fast_sell=fast_sell,
        slow_sell=slow_sell,
        base=base,
        ma_type=ma_type,
    )
    df = _minus_9h_index(df)

    df_plot = df.reset_index().rename(columns={"index": "Time"})
    base_chart = alt.Chart(df_plot).encode(x=alt.X("Time:T", axis=alt.Axis(format="%H:%M")))

    # 가격 차트 레이어들
    price_layers = []

    if show_price:
        # 캔들 차트: 고저선
        rule = base_chart.mark_rule().encode(
            y=alt.Y("Low:Q", scale=alt.Scale(zero=False), title="Price"),
            y2="High:Q",
        )
        # 캔들 차트: 몸통
        body = base_chart.mark_bar().encode(
            y="Open:Q",
            y2="Close:Q",
            color=alt.condition("datum.Close >= datum.Open", alt.value("#26a69a"), alt.value("#ef5350")),
        )
        price_layers.extend([rule, body])

    # EMA 라인들을 가격 차트와 같은 Y축에 추가
    if use_separate:
        # 매수/매도 별도 EMA
        ema_fast_buy_line = base_chart.mark_line(strokeWidth=2, color="#4caf50").encode(
            y="EMA_Fast_Buy:Q",
        )
        ema_slow_buy_line = base_chart.mark_line(strokeWidth=2, color="#1b5e20").encode(
            y="EMA_Slow_Buy:Q",
        )
        ema_fast_sell_line = base_chart.mark_line(strokeWidth=2, color="#ff9800").encode(
            y="EMA_Fast_Sell:Q",
        )
        ema_slow_sell_line = base_chart.mark_line(strokeWidth=2, color="#d32f2f").encode(
            y="EMA_Slow_Sell:Q",
        )
        ema_base_line = base_chart.mark_line(strokeWidth=2.5, color="#2196f3", strokeDash=[5, 5]).encode(
            y="EMA_Base:Q",
        )

        # Tooltip
        tooltip_chart = base_chart.mark_rule(opacity=0).encode(
            tooltip=[
                alt.Tooltip("Time:T", title="Time", format="%Y-%m-%d %H:%M"),
                alt.Tooltip("Close:Q", title="Close", format=".2f"),
                alt.Tooltip("EMA_Fast_Buy:Q", title="Fast Buy", format=".2f"),
                alt.Tooltip("EMA_Slow_Buy:Q", title="Slow Buy", format=".2f"),
                alt.Tooltip("EMA_Fast_Sell:Q", title="Fast Sell", format=".2f"),
                alt.Tooltip("EMA_Slow_Sell:Q", title="Slow Sell", format=".2f"),
                alt.Tooltip("EMA_Base:Q", title="Base", format=".2f"),
            ],
        )

        price_layers.extend([
            ema_fast_buy_line,
            ema_slow_buy_line,
            ema_fast_sell_line,
            ema_slow_sell_line,
            ema_base_line,
            tooltip_chart,
        ])
    else:
        # 공통 EMA
        ema_fast_line = base_chart.mark_line(strokeWidth=2, color="#4caf50").encode(
            y="EMA_Fast:Q",
        )
        ema_slow_line = base_chart.mark_line(strokeWidth=2, color="#d32f2f").encode(
            y="EMA_Slow:Q",
        )
        ema_base_line = base_chart.mark_line(strokeWidth=2.5, color="#2196f3", strokeDash=[5, 5]).encode(
            y="EMA_Base:Q",
        )

        # Tooltip
        tooltip_chart = base_chart.mark_rule(opacity=0).encode(
            tooltip=[
                alt.Tooltip("Time:T", title="Time", format="%Y-%m-%d %H:%M"),
                alt.Tooltip("Close:Q", title="Close", format=".2f"),
                alt.Tooltip("EMA_Fast:Q", title="Fast", format=".2f"),
                alt.Tooltip("EMA_Slow:Q", title="Slow", format=".2f"),
                alt.Tooltip("EMA_Base:Q", title="Base", format=".2f"),
            ],
        )

        price_layers.extend([
            ema_fast_line,
            ema_slow_line,
            ema_base_line,
            tooltip_chart,
        ])

    # 모든 레이어를 하나의 차트로 결합
    chart = alt.layer(*price_layers).properties(height=height_price)
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
    df = _minus_9h_index(df)

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
