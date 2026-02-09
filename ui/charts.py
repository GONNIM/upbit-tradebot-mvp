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

    # ✅ 전체 데이터로 MACD 계산 (충분한 워밍업 보장)
    df = compute_macd(df_raw, fast=fast, slow=slow, signal=signal)
    df = _minus_9h_index(df)

    # ✅ 표시용으로만 max_bars 제한 (MACD는 이미 전체 계산 완료)
    df_plot = df.tail(max_bars).reset_index().rename(columns={"index": "Time"})
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
    gap_mode: bool = False,
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

    # ========== 📊 1. 사용자 설정값 요약 & 범례 표시 ==========
    col1, col2 = st.columns(2)  # 1:1 비율

    with col1:
        # ✅ Base EMA GAP 전용 모드
        if gap_mode:
            setting_html = f'''
            <div style="background: linear-gradient(135deg, #1a237e 0%, #283593 100%);
                        padding: 12px;
                        border-radius: 8px;
                        border: 2px solid #3f51b5;
                        color: #ffffff;
                        box-shadow: 0 2px 8px rgba(0,0,0,0.3);">
                <div style="font-size: 15px; font-weight: bold; margin-bottom: 8px; color: #fff;">
                    📌 전략 설정
                </div>
                <div style="margin-top: 8px;">
                    <div style="margin: 6px 0; display: flex; align-items: center; background-color: rgba(255,255,255,0.1); padding: 4px 6px; border-radius: 4px;">
                        <span style="font-size: 14px; color: #fff; font-weight: 500;">
                            📊 <strong style="color: #ffd54f;">전략:</strong>
                        </span>
                        <span style="font-size: 14px; color: #fff; font-weight: 600; margin-left: 8px;">
                            Base EMA GAP (급락 매수)
                        </span>
                    </div>
                    <div style="margin: 6px 0; display: flex; align-items: center; background-color: rgba(255,255,255,0.1); padding: 4px 6px; border-radius: 4px;">
                        <span style="font-size: 14px; color: #fff; font-weight: 500;">
                            📊 <strong style="color: #ffd54f;">Base:</strong>
                        </span>
                        <span style="font-size: 14px; color: #fff; font-weight: 600; margin-left: 8px;">
                            {base}일선 ({ma_type})
                        </span>
                    </div>
                </div>
            </div>
            '''
        elif use_separate:
            setting_html = f'''
            <div style="background: linear-gradient(135deg, #1a237e 0%, #283593 100%);
                        padding: 12px;
                        border-radius: 8px;
                        border: 2px solid #3f51b5;
                        color: #ffffff;
                        box-shadow: 0 2px 8px rgba(0,0,0,0.3);">
                <div style="font-size: 15px; font-weight: bold; margin-bottom: 8px; color: #fff;">
                    📌 전략 설정
                </div>
                <div style="margin-top: 8px;">
                    <div style="margin: 6px 0; display: flex; align-items: center; background-color: rgba(255,255,255,0.1); padding: 4px 6px; border-radius: 4px;">
                        <span style="font-size: 14px; color: #fff; font-weight: 500;">
                            🟢 <strong style="color: #69f0ae;">매수:</strong>
                        </span>
                        <span style="font-size: 14px; color: #fff; font-weight: 600; margin-left: 8px;">
                            {fast_buy}일선 / {slow_buy}일선
                        </span>
                    </div>
                    <div style="margin: 6px 0; display: flex; align-items: center; background-color: rgba(255,255,255,0.1); padding: 4px 6px; border-radius: 4px;">
                        <span style="font-size: 14px; color: #fff; font-weight: 500;">
                            🔴 <strong style="color: #ff5252;">매도:</strong>
                        </span>
                        <span style="font-size: 14px; color: #fff; font-weight: 600; margin-left: 8px;">
                            {fast_sell}일선 / {slow_sell}일선
                        </span>
                    </div>
                    <div style="margin: 6px 0; display: flex; align-items: center; background-color: rgba(255,255,255,0.1); padding: 4px 6px; border-radius: 4px;">
                        <span style="font-size: 14px; color: #fff; font-weight: 500;">
                            📊 <strong style="color: #ffd54f;">Base:</strong>
                        </span>
                        <span style="font-size: 14px; color: #fff; font-weight: 600; margin-left: 8px;">
                            {base}일선
                        </span>
                        <span style="font-size: 14px; color: #fff; font-weight: 500; margin-left: 12px;">
                            · <strong style="color: #ffd54f;">MA타입:</strong>
                        </span>
                        <span style="font-size: 14px; color: #fff; font-weight: 600; margin-left: 6px;">
                            {ma_type}
                        </span>
                    </div>
                </div>
            </div>
            '''
        else:
            setting_html = f'''
            <div style="background: linear-gradient(135deg, #1a237e 0%, #283593 100%);
                        padding: 12px;
                        border-radius: 8px;
                        border: 2px solid #3f51b5;
                        color: #ffffff;
                        box-shadow: 0 2px 8px rgba(0,0,0,0.3);">
                <div style="font-size: 15px; font-weight: bold; margin-bottom: 8px; color: #fff;">
                    📌 전략 설정
                </div>
                <div style="margin-top: 8px;">
                    <div style="margin: 6px 0; display: flex; align-items: center; background-color: rgba(255,255,255,0.1); padding: 4px 6px; border-radius: 4px;">
                        <span style="font-size: 14px; color: #fff; font-weight: 500;">
                            📈 <strong style="color: #69f0ae;">공통:</strong>
                        </span>
                        <span style="font-size: 14px; color: #fff; font-weight: 600; margin-left: 8px;">
                            {fast_sell}일선 / {slow_sell}일선
                        </span>
                    </div>
                    <div style="margin: 6px 0; display: flex; align-items: center; background-color: rgba(255,255,255,0.1); padding: 4px 6px; border-radius: 4px;">
                        <span style="font-size: 14px; color: #fff; font-weight: 500;">
                            📊 <strong style="color: #ffd54f;">Base:</strong>
                        </span>
                        <span style="font-size: 14px; color: #fff; font-weight: 600; margin-left: 8px;">
                            {base}일선
                        </span>
                        <span style="font-size: 14px; color: #fff; font-weight: 500; margin-left: 12px;">
                            · <strong style="color: #ffd54f;">MA타입:</strong>
                        </span>
                        <span style="font-size: 14px; color: #fff; font-weight: 600; margin-left: 6px;">
                            {ma_type}
                        </span>
                    </div>
                </div>
            </div>
            '''
        st.markdown(setting_html, unsafe_allow_html=True)

    # ========== 🎨 2. 범례 정보 미리 생성 ==========
    # 기간별로 수집: {기간: [용도 라벨들]}
    period_labels = {}

    # ✅ Base EMA GAP 모드: Base만 표시
    if gap_mode:
        period_labels[base] = ["Base (GAP 기준선)"]
    elif use_separate:
        # 별도 모드: 매수/매도 각각의 기간 수집
        if fast_buy not in period_labels:
            period_labels[fast_buy] = []
        period_labels[fast_buy].append("Buy Fast")

        if slow_buy not in period_labels:
            period_labels[slow_buy] = []
        period_labels[slow_buy].append("Buy Slow")

        if fast_sell not in period_labels:
            period_labels[fast_sell] = []
        period_labels[fast_sell].append("Sell Fast")

        if slow_sell not in period_labels:
            period_labels[slow_sell] = []
        period_labels[slow_sell].append("Sell Slow")

        # Base는 별도 처리
        if base not in period_labels:
            period_labels[base] = []
        period_labels[base].append("Base")
    else:
        # 공통 모드: fast_sell, slow_sell 사용
        if fast_sell not in period_labels:
            period_labels[fast_sell] = []
        period_labels[fast_sell].append("Fast")

        if slow_sell not in period_labels:
            period_labels[slow_sell] = []
        period_labels[slow_sell].append("Slow")

        # Base는 별도 처리
        if base not in period_labels:
            period_labels[base] = []
        period_labels[base].append("Base")

    # 색상 팔레트 (기간별로 다른 색)
    color_palette = ["#4caf50", "#ff9800", "#d32f2f", "#9c27b0", "#2196f3", "#ff5722"]
    sorted_periods = sorted(period_labels.keys())

    # ========== 📋 범례 표시 (col2) ==========
    with col2:
        legend_html = '''
        <div style="background: linear-gradient(135deg, #e65100 0%, #ef6c00 100%);
                    padding: 12px;
                    border-radius: 8px;
                    border: 2px solid #ff9800;
                    color: #ffffff;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.3);">
            <div style="font-size: 15px; font-weight: bold; margin-bottom: 8px; color: #fff;">
                📋 차트 범례
            </div>
            <div style="margin-top: 8px;">
        '''

        for idx, period in enumerate(sorted_periods):
            labels = period_labels[period]
            label_str = " / ".join(labels)
            color = color_palette[idx % len(color_palette)]
            # ✅ "Base"를 포함하는 라벨이 있는지 확인 (GAP 모드: "Base (GAP 기준선)")
            has_base = any("Base" in label for label in labels)

            # HTML로 색상 라인 + 라벨 생성
            legend_html += f'<div style="margin: 6px 0; display: flex; align-items: center; background-color: rgba(255,255,255,0.1); padding: 4px 6px; border-radius: 4px;">'

            if has_base:
                # 점선 스타일 (SVG 사용 - 더 굵고 명확하게)
                legend_html += f'<svg width="40" height="12" style="margin-right: 10px;">'
                legend_html += f'<line x1="0" y1="6" x2="40" y2="6" stroke="{color}" stroke-width="4" stroke-dasharray="6,4"/>'
                legend_html += f'</svg>'
            else:
                # 실선 (더 굵고 명확하게)
                legend_html += f'<span style="display: inline-block; width: 40px; height: 4px; background-color: {color}; margin-right: 10px; border-radius: 2px;"></span>'

            legend_html += f'<span style="font-size: 14px; color: #fff; font-weight: 500;">{period}일선</span>'
            legend_html += f'<span style="font-size: 14px; color: #ffe0b2; margin-left: 6px;">({label_str})</span>'
            legend_html += f'</div>'

        legend_html += '</div></div>'
        st.markdown(legend_html, unsafe_allow_html=True)

    # ========== 📊 차트 데이터 준비 ==========
    # ✅ 전체 데이터로 MA 계산 (충분한 워밍업 보장)
    df = compute_ema(
        df_raw,
        use_separate=use_separate,
        fast_buy=fast_buy,
        slow_buy=slow_buy,
        fast_sell=fast_sell,
        slow_sell=slow_sell,
        base=base,
        ma_type=ma_type,
    )
    df = _minus_9h_index(df)

    # ✅ 표시용으로만 max_bars 제한 (MA는 이미 전체 계산 완료)
    df_plot = df.tail(max_bars).reset_index().rename(columns={"index": "Time"})
    base_chart = alt.Chart(df_plot).encode(x=alt.X("Time:T", axis=alt.Axis(format="%H:%M")))

    # 가격 차트 레이어들
    price_layers = []

    if show_price:
        if gap_mode:
            # ✅ GAP 모드: 종가를 실선으로 연결 (캔들 대신)
            close_line = base_chart.mark_line(
                strokeWidth=2,
                color="#2196f3",  # 파란색
            ).encode(
                y=alt.Y("Close:Q", scale=alt.Scale(zero=False), title="Price")
            )
            price_layers.append(close_line)
        else:
            # 일반 모드: 캔들 차트
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

    # MA 라인 추가 (중복 제거된 기간만)
    tooltip_fields = [
        alt.Tooltip("Time:T", title="Time", format="%Y-%m-%d %H:%M"),
        alt.Tooltip("Close:Q", title="Close", format=".2f"),
    ]

    for idx, period in enumerate(sorted_periods):
        labels = period_labels[period]
        label_str = " / ".join(labels)
        color = color_palette[idx % len(color_palette)]

        # Base가 포함된 경우 점선으로 구분 (Base 역할 강조)
        # ✅ "Base"를 포함하는 라벨이 있는지 확인 (GAP 모드: "Base (GAP 기준선)")
        has_base = any("Base" in label for label in labels)
        # ✅ GAP 모드일 때는 점선을 더 명확하게
        stroke_dash = [6, 4] if (has_base and gap_mode) else ([5, 5] if has_base else [])

        # 🔧 데이터프레임에서 해당 컬럼 찾기 (우선순위: Buy > Sell > Base)
        col_name = None
        if gap_mode:
            # ✅ GAP 모드: Base만 표시
            if period == base:
                col_name = "EMA_Base"
        elif use_separate:
            # 별도 모드: 우선순위에 따라 컬럼 선택
            if period == fast_buy:
                col_name = "EMA_Fast_Buy"
            elif period == slow_buy:
                col_name = "EMA_Slow_Buy"
            elif period == fast_sell:
                col_name = "EMA_Fast_Sell"
            elif period == slow_sell:
                col_name = "EMA_Slow_Sell"
            elif period == base:
                col_name = "EMA_Base"
        else:
            # 공통 모드
            if period == fast_sell:
                col_name = "EMA_Fast"
            elif period == slow_sell:
                col_name = "EMA_Slow"
            elif period == base:
                col_name = "EMA_Base"

        # 컬럼을 찾지 못하면 스킵
        if col_name is None:
            continue

        # 라인 추가 (Base 포함 시 약간 굵게, GAP 모드는 더 굵게)
        line_width = 3.0 if (has_base and gap_mode) else (2.5 if has_base else 2)
        line = base_chart.mark_line(
            strokeWidth=line_width,
            color=color,
            strokeDash=stroke_dash,
        ).encode(y=f"{col_name}:Q")

        price_layers.append(line)

        # 툴팁 필드 추가
        tooltip_fields.append(
            alt.Tooltip(f"{col_name}:Q", title=f"{ma_type}-{period} ({label_str})", format=".2f")
        )

    # Tooltip 추가
    tooltip_chart = base_chart.mark_rule(opacity=0).encode(tooltip=tooltip_fields)
    price_layers.append(tooltip_chart)

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
