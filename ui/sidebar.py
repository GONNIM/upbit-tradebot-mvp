import streamlit as st
from engine.params import LiveParams
from typing import Optional
from config import (
    PARAMS_JSON_FILENAME,
    STRATEGY_TYPES,
    DEFAULT_STRATEGY_TYPE,
    ENGINE_EXEC_MODE,
)
from engine.params import load_params

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
    "10-percent": { "button": "10%", "ratio": 0.1 },
    "25-percent": { "button": "25%", "ratio": 0.25 },
    "50-percent": { "button": "50%", "ratio": 0.5 },
    "100-percent": { "button": "100%", "ratio": 1 },
}


def make_sidebar(user_id: str, strategy_type: str) -> Optional[LiveParams]:
    json_path = f"{user_id}_{PARAMS_JSON_FILENAME}"
    # ✅ 전략별 파라미터를 로드하도록 strategy_type 전달
    #    -> MACD / EMA 각각 다른 fast/slow 값을 유지할 수 있음
    load_params_obj = load_params(json_path, strategy_type=strategy_type)

    # 파일에서 읽어온 마지막 저장값 (공통 기본값)
    DEFAULT_PARAMS = load_params_obj.dict() if load_params_obj else {}

    # ---------- 전략 타입 / 엔진 모드 ----------
    allowed_strategies = [s.upper() for s in STRATEGY_TYPES]

    # 1) set_config.py 에서 넘어온 strategy_type 을 최우선 사용
    current_strategy_raw = strategy_type or DEFAULT_PARAMS.get("strategy_type") or DEFAULT_STRATEGY_TYPE
    current_strategy = str(current_strategy_raw).upper().strip()

    # 방어: 이상한 값이면 그냥 DEFAULT_STRATEGY_TYPE 로
    if current_strategy not in allowed_strategies:
        current_strategy = str(DEFAULT_STRATEGY_TYPE).upper().strip()

    is_macd = (current_strategy == "MACD")
    is_ema = (current_strategy == "EMA")

    current_mode = (
        DEFAULT_PARAMS.get("engine_exec_mode") or "REPLAY"
    ).upper().strip()
    if current_mode not in ("BACKTEST", "REPLAY"):
        current_mode = "BACKTEST"
    current_mode = ENGINE_EXEC_MODE

    # 🔑 전략별 UI 기본값을 세션에 따로 보관하기 위한 키
    strategy_key = f"ui_defaults_{current_strategy}"

    # 이 전략에 대해 이미 사용자가 한 번 저장한 값이 있다면 → 그걸 우선 사용
    # 없다면 → 파일에서 불러온 DEFAULT_PARAMS 사용
    STRATEGY_DEFAULTS = st.session_state.get(strategy_key, DEFAULT_PARAMS)
    
    """Render sidebar form and return validated params (or None)."""
    with st.sidebar:
        st.header("⚙️ 파라미터 설정")
        st.markdown(
            f"**전략:** `{current_strategy}` &nbsp;&nbsp; "
            f"**엔진 모드:** `{current_mode}`"
        )

        # ========== 🔧 버그 수정 1: 체크박스를 폼 밖으로 이동하여 즉시 반영 ==========
        # EMA 전략일 때만 매수/매도 별도 설정 옵션 표시
        if is_ema:
            st.divider()
            # 세션 스테이트 초기화
            if "use_separate_ema_ui" not in st.session_state:
                st.session_state.use_separate_ema_ui = STRATEGY_DEFAULTS.get("use_separate_ema", True)

            use_separate = st.checkbox(
                "📌 매수/매도 EMA 별도 설정",
                value=st.session_state.use_separate_ema_ui,
                key="use_separate_ema_checkbox",
                help="체크 시 매수와 매도에 각각 다른 EMA 쌍을 사용합니다."
            )
            # 세션에 저장
            st.session_state.use_separate_ema_ui = use_separate
        else:
            use_separate = False

        with st.form("input_form"):
            ticker = st.text_input(
                "거래 종목", value=DEFAULT_PARAMS.get("ticker", "PEPE")
            )

            interval_default = [
                k
                for k, v in INTERVAL_OPTIONS.items()
                if v == DEFAULT_PARAMS.get("interval", "minute15")
            ]
            interval_name = st.selectbox(
                "차트 단위",
                list(INTERVAL_OPTIONS.keys()),
                index=(
                    0
                    if not interval_default
                    else list(INTERVAL_OPTIONS.keys()).index(interval_default[0])
                ),
            )

            # ---------- EMA / MACD 별 기본값 분기 ----------
            if is_ema:
                st.divider()
                st.subheader("📊 EMA 설정")

                # ✅ 이동평균 계산 방식 선택
                ma_type = st.selectbox(
                    "이동평균 계산 방식",
                    ["SMA", "EMA", "WMA"],
                    index=["SMA", "EMA", "WMA"].index(
                        DEFAULT_PARAMS.get("ma_type", "SMA").upper()
                    ),
                    help=(
                        "**SMA**: 단순이동평균 (모든 가격 동일 가중)\n\n"
                        "**EMA**: 지수이동평균 (최근 가격에 높은 가중)\n\n"
                        "**WMA**: 가중이동평균 (선형 가중)"
                    )
                )

                # 계산 방식 요약 표시
                if ma_type == "SMA":
                    st.info("📌 **SMA** (단순이동평균): 모든 가격에 동일한 가중치 적용")
                elif ma_type == "EMA":
                    st.info("📌 **EMA** (지수이동평균): 최근 가격에 더 높은 가중치 적용")
                elif ma_type == "WMA":
                    st.info("📌 **WMA** (가중이동평균): 선형적으로 가중치 부여")

                st.divider()
                st.subheader("📊 EMA 매수/매도 설정")

                if use_separate:
                    # 별도 설정 모드
                    col1, col2 = st.columns(2)

                    with col1:
                        st.markdown("**🟢 매수 EMA**")
                        fast_buy = st.number_input(
                            "Fast (매수)",
                            min_value=1,
                            max_value=500,
                            value=DEFAULT_PARAMS.get("fast_buy") or DEFAULT_PARAMS.get("fast_period") or 60,
                            help="매수 판단용 단기 EMA"
                        )
                        slow_buy = st.number_input(
                            "Slow (매수)",
                            min_value=1,
                            max_value=500,
                            value=DEFAULT_PARAMS.get("slow_buy") or DEFAULT_PARAMS.get("slow_period") or 200,
                            help="매수 판단용 장기 EMA"
                        )

                    with col2:
                        st.markdown("**🔴 매도 EMA**")
                        fast_sell = st.number_input(
                            "Fast (매도)",
                            min_value=1,
                            max_value=500,
                            value=DEFAULT_PARAMS.get("fast_sell") or DEFAULT_PARAMS.get("fast_period") or 20,
                            help="매도 판단용 단기 EMA"
                        )
                        slow_sell = st.number_input(
                            "Slow (매도)",
                            min_value=1,
                            max_value=500,
                            value=DEFAULT_PARAMS.get("slow_sell") or DEFAULT_PARAMS.get("slow_period") or 60,
                            help="매도 판단용 장기 EMA"
                        )

                    st.info(f"매수: {fast_buy}/{slow_buy} GC | 매도: {fast_sell}/{slow_sell} DC")
                else:
                    # 공통 설정 모드 (기존)
                    st.markdown("**공통 EMA (매수/매도 동일)**")
                    fast = st.number_input("단기 EMA", 1, 500, value=DEFAULT_PARAMS.get("fast_period", 20))
                    slow = st.number_input("장기 EMA", 1, 500, value=DEFAULT_PARAMS.get("slow_period", 200))

                    # 내부적으로 매수/매도 동일하게 설정
                    fast_buy = fast_sell = fast
                    slow_buy = slow_sell = slow

                base_ema_default = DEFAULT_PARAMS.get("base_ema_period", 200)

                # Base EMA GAP 전략 설정
                st.divider()
                st.subheader("📊 Base EMA GAP 전략")

                base_ema_gap_enabled = st.checkbox(
                    "Base EMA GAP 전략 사용",
                    value=DEFAULT_PARAMS.get("base_ema_gap_enabled", False),
                    help="종가가 Base EMA(200일선) 대비 급락 시 매수 (역추세 전략)",
                    key="base_ema_gap_enabled_checkbox"
                )

                gap_diff_default = DEFAULT_PARAMS.get("base_ema_gap_diff", -0.005) * 100
                gap_diff = (
                    st.number_input(
                        "Base EMA GAP 임계값 (%)",
                        min_value=-2.0,
                        max_value=0.0,
                        value=gap_diff_default,
                        step=0.1,
                        help="종가가 Base EMA(200일선)보다 이 값 이하로 떨어지면 매수 (예: -0.5%)"
                    )
                    / 100
                )
                st.info(f"현재가가 Base EMA 대비 {gap_diff*100:.1f}% 이하일 때 매수")

                # ✅ 매수 필터(급등 차단)는 매수/매도 조건 설정 페이지에서 관리
                # (buy_sell_conditions.json)
                # params.json에는 기본값만 유지 (backward compatibility)
                ema_surge_filter_enabled = DEFAULT_PARAMS.get("ema_surge_filter_enabled", False)
                ema_surge_threshold_pct = DEFAULT_PARAMS.get("ema_surge_threshold_pct", 0.01)

                # EMA는 signal_period를 UI로 안 받되 값은 필요하므로 그대로 유지
                signal_val = int(DEFAULT_PARAMS.get("signal_period", 9))
            else:
                # MACD 전략은 기존 로직 유지
                # MACD는 항상 EMA 사용 (표준 MACD 정의)
                ma_type = "EMA"
                use_separate = False
                fast = st.number_input("단기 EMA", 1, 100, value=DEFAULT_PARAMS.get("fast_period", 12))
                slow = st.number_input("장기 EMA", 1, 240, value=DEFAULT_PARAMS.get("slow_period", 26))
                fast_buy = fast_sell = fast
                slow_buy = slow_sell = slow
                base_ema_default = DEFAULT_PARAMS.get("base_ema_period", 200)
                # MACD에서는 Base EMA GAP 전략 미사용 (기본값 유지)
                base_ema_gap_enabled = False
                gap_diff = DEFAULT_PARAMS.get("base_ema_gap_diff", -0.005)
                # ✅ 매수 필터는 buy_sell_conditions.json에서 관리 (기본값만 유지)
                ema_surge_filter_enabled = DEFAULT_PARAMS.get("ema_surge_filter_enabled", False)
                ema_surge_threshold_pct = DEFAULT_PARAMS.get("ema_surge_threshold_pct", 0.01)
                signal_val = st.number_input(
                    "신호선 기간", 1, 50, value=DEFAULT_PARAMS.get("signal_period", 9)
                )

            # # Base EMA: EMA일 때만 UI에 노출
            # if is_ema:
            #     base_ema_period = st.number_input(
            #         "Base EMA",
            #         1,
            #         500,
            #         value=base_ema_default,
            #     )
            # else:
            #     # MACD에서는 내부적으로만 유지
            #     base_ema_period = base_ema_default
            base_ema_period = base_ema_default
            
            # ---------- MACD 전용 threshold ----------
            if is_macd:
                macd_threshold = st.number_input(
                    "MACD 기준값",
                    -100.0,
                    100.0,
                    value=DEFAULT_PARAMS.get("macd_threshold", 0.0),
                    step=1.0,
                )
            else:
                # EMA에서는 threshold 사용 안 함
                macd_threshold = DEFAULT_PARAMS.get("macd_threshold", 0.0)

            tp_default = DEFAULT_PARAMS.get("take_profit", 0.03) * 100
            tp = (
                st.number_input(
                    "Take Profit (%)",
                    0.1,
                    50.0,
                    value=tp_default,
                    step=0.1,
                )
                / 100
            )
            sl_default = DEFAULT_PARAMS.get("stop_loss", 0.01) * 100
            sl = (
                st.number_input(
                    "Stop Loss (%)",
                    0.1,
                    50.0,
                    value=sl_default,
                    step=0.1,
                )
                / 100
            )

            # ========== 거래 시간 제한 ==========
            st.divider()
            st.subheader("⏰ 거래 시간 제한")

            # 1️⃣ 시간 입력 UI (항상 표시)
            col_start, col_end = st.columns(2)

            with col_start:
                from datetime import datetime
                start_time_str = DEFAULT_PARAMS.get("trading_start_time", "09:00")
                try:
                    start_time_obj = datetime.strptime(start_time_str, "%H:%M").time()
                except Exception:
                    start_time_obj = datetime.strptime("09:00", "%H:%M").time()

                trading_start_time = st.time_input(
                    "거래 시작 시간",
                    value=start_time_obj,
                    help="매일 이 시간부터 거래 시작 (KST)"
                ).strftime("%H:%M")

            with col_end:
                end_time_str = DEFAULT_PARAMS.get("trading_end_time", "02:00")
                try:
                    end_time_obj = datetime.strptime(end_time_str, "%H:%M").time()
                except Exception:
                    end_time_obj = datetime.strptime("02:00", "%H:%M").time()

                trading_end_time = st.time_input(
                    "거래 종료 시간",
                    value=end_time_obj,
                    help="매일 이 시간에 거래 중지 (KST)"
                ).strftime("%H:%M")

            # 2️⃣ 기능 활성화 체크박스
            enable_trading_hours = st.checkbox(
                "✅ 거래 시간 제한 활성화",
                value=DEFAULT_PARAMS.get("enable_trading_hours", False),
                help="체크 시 위 시간대에만 거래합니다 (새벽 슬리피지 방지)"
            )

            # 3️⃣ 포지션 보호 옵션
            allow_sell_during_off_hours = st.checkbox(
                "⭐ 포지션 보유 시 거래 쉬는시간에도 매도 허용 (권장)",
                value=DEFAULT_PARAMS.get("allow_sell_during_off_hours", True),
                help="체크 권장: 포지션 보호를 위해 TP/SL/TS는 항상 작동해야 함"
            )

            # 4️⃣ 설정 요약 표시
            st.info(
                f"**{'🟢 활성화' if enable_trading_hours else '⚪ 비활성화'}**\n\n"
                f"**거래 시간**: {trading_start_time} ~ {trading_end_time} (KST)\n\n"
                f"**휴식 시간**: {trading_end_time} ~ {trading_start_time}\n\n"
                f"{'✅ 포지션 보유 시 매도는 항상 허용됨' if allow_sell_during_off_hours else '⚠️ 포지션 보유 시에도 매도 차단 (비권장)'}"
            )

            # MACD 전용 옵션 (EMA에서는 강제 False)
            if is_macd:
                macd_exit_enabled = st.checkbox(
                    "📌 매도 전략: MACD EXIT",
                    help="TP/SL 도달 전 Dead Cross + MACD 기준 초과 시 매도합니다.",
                    value=DEFAULT_PARAMS.get("macd_exit_enabled", True),
                    disabled=True,
                )
                signal_confirm_enabled = st.checkbox(
                    "📌 옵션 전략: MACD 기준선 통과 매매 타점",
                    help="기본 전략(Golden Cross + MACD 기준 초과) 이후, Signal 선까지 MACD 기준 초과 시 매수합니다.",
                    value=DEFAULT_PARAMS.get("signal_confirm_enabled", False),
                    disabled=True,
                )
            else:
                macd_exit_enabled = False
                signal_confirm_enabled = False

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

        # ✅ 저장 안내 메시지 추가
        saved_ratio = load_params_obj.order_ratio if load_params_obj else 1.0
        current_ratio = st.session_state.order_ratio

        if abs(saved_ratio - current_ratio) > 0.001:
            st.warning(
                f"⚠️ **주문 비율이 변경되었습니다!**\n\n"
                f"- 💾 저장된 비율: **{saved_ratio * 100:.0f}%**\n"
                f"- 🎯 현재 선택: **{current_ratio * 100:.0f}%**\n\n"
                f"**반드시 '파라미터 저장하기' 버튼을 클릭하세요!**",
                icon="⚠️"
            )
        else:
            st.info(
                f"💾 저장된 주문 비율: **{saved_ratio * 100:.0f}%**",
                icon="✅"
            )

        st.subheader("운용자산")
        st.info(f"{st.session_state.virtual_amount:,.0f} KRW")

        if not submitted:
            return None

    try:
        # ========== 🔧 버그 수정 2 & 3: EMA 파라미터 올바르게 저장 ==========
        # fast_period, slow_period는 전략에서 폴백값으로 사용되므로 올바른 값 저장 필수
        if is_ema:
            if use_separate:
                # 별도 설정 모드: 매수용 EMA를 기본값으로 사용
                # (전략 코드에서 fast_period를 폴백으로 사용할 때 매수용이 기준)
                final_fast = int(fast_buy)
                final_slow = int(slow_buy)
            else:
                # 공통 설정 모드: 공통 EMA 값 사용
                final_fast = int(fast)
                final_slow = int(slow)
        else:
            # MACD는 fast/slow 변수 사용
            final_fast = int(fast)
            final_slow = int(slow)

        params = LiveParams(
            ticker=ticker,
            interval=INTERVAL_OPTIONS[interval_name],
            # 기존 공통 파라미터
            fast_period=final_fast,
            slow_period=final_slow,
            signal_period=int(signal_val),
            macd_threshold=macd_threshold,
            take_profit=tp,
            stop_loss=sl,
            cash=int(cash),
            order_ratio=st.session_state.order_ratio,
            macd_exit_enabled=macd_exit_enabled,
            signal_confirm_enabled=signal_confirm_enabled,
            base_ema_period=int(base_ema_period),
            base_ema_gap_enabled=base_ema_gap_enabled if is_ema else False,
            base_ema_gap_diff=float(gap_diff),
            ma_type=ma_type,
            # ✅ 매수 필터 (buy_sell_conditions.json에서 관리, 여기는 backward compatibility용 기본값만 저장)
            ema_surge_filter_enabled=ema_surge_filter_enabled if is_ema else False,
            ema_surge_threshold_pct=float(ema_surge_threshold_pct) if is_ema else 0.01,
            strategy_type=current_strategy,
            engine_exec_mode=current_mode,
            # 거래 시간 제한
            enable_trading_hours=enable_trading_hours,
            trading_start_time=trading_start_time,
            trading_end_time=trading_end_time,
            allow_sell_during_off_hours=allow_sell_during_off_hours,
            # EMA 매수/매도 별도 설정
            use_separate_ema=use_separate if is_ema else False,
            # 🔧 버그 수정: 공통 모드일 때도 실제 값 저장 (None 대신)
            # - 공통 모드: fast_buy = fast, slow_buy = slow 등으로 저장
            # - 별도 모드: 각각의 입력값 저장
            # - MACD: None 저장
            fast_buy=int(fast_buy) if is_ema else None,
            slow_buy=int(slow_buy) if is_ema else None,
            fast_sell=int(fast_sell) if is_ema else None,
            slow_sell=int(slow_sell) if is_ema else None,
        )

        # 🔁 이 전략 타입에 대한 마지막 입력값을 세션에 따로 저장
        st.session_state[strategy_key] = params.dict()

        return params
    except Exception as exc:  # pylint: disable=broad-except
        st.error(f"❌ 파라미터 오류: {exc}")
        return None
