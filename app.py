from tracemalloc import start
from urllib.parse import urlencode
import logging
import streamlit as st
import streamlit_authenticator as stauth
from ui.style import style_main
from config import MIN_CASH, ACCESS, SECRET, DEFAULT_STRATEGY_TYPE
from services.db import get_user, save_user
from engine.params import load_active_strategy
import yaml
from yaml.loader import SafeLoader
from services.init_db import init_db_if_needed
from services.health_monitor import start_health_monitoring
from utils.smoke_test import render_db_smoke_test

from services.upbit_api import validate_upbit_keys, get_server_public_ip

logger = logging.getLogger(__name__)


def _mask(s: str, head=4, tail=4):
    if not s:
        return ""
    if len(s) <= head + tail:
        return "*" * len(s)
    return f"{s[:head]}{'*' * (len(s) - head - tail)}{s[-tail:]}"


def _extract_krw_balance(accounts) -> list:
    """
    validate_upbit_keys 가 반환한 잔고 리스트(data)에서
    KRW 잔고를 찾아 float 형태로 리턴.
    못 찾으면 0.0
    """
    if not accounts:
        return 0.0
    
    for acc in accounts:
        if acc.get("currency") == "KRW":
            balance_str = acc.get("balance", "0")
            try:
                return float(balance_str)
            except ValueError:
                return 0.0
    return 0.0


def _has_any_coin_position(accounts) -> bool:
    """
    Upbit balances(list[dict])에서
    KRW 이외 코인 중 '실제 보유 중인 포지션'이 있는지 체크.
    - balance > 0 이고 avg_buy_price > 0 인 경우만 포지션으로 본다.
    """
    if not accounts:
        return False
    
    for acc in accounts:
        cur = str(acc.get("currency", "")).upper()
        if cur == "KRW":
            continue
        try:
            bal = float(acc.get("balance") or 0.0)
            avg_price = float(acc.get("avg_buy_price") or 0.0)
        except ValueError:
            continue
        if bal > 0 and avg_price > 0:
            return True
    return False


# 모드/검증 상태 기본값
st.session_state.setdefault("mode", "TEST")
st.session_state.setdefault("_last_mode", "TEST")          # 마지막 모드 기억
st.session_state.setdefault("upbit_verified", False)       # 검증 결과
st.session_state.setdefault("upbit_accounts", [])          # 잔고 캐시
st.session_state.setdefault("upbit_verify_error", "")      # 에러 메시지
st.session_state.setdefault("_auto_checked_in_live", False)# 이번 LIVE 세션 자동검증 여부
st.session_state.setdefault("live_krw_balance", 0.0) # Upbit KRW 잔고
st.session_state.setdefault("live_capital_set", False) # LIVE 운용자산 설정 여부


# Setup page
st.set_page_config(page_title="Upbit Trade Bot v1", page_icon="🤖", layout="wide")
st.markdown(style_main, unsafe_allow_html=True)

# 버튼 색상 커스터마이징
st.markdown(
    """
    <style>
    /* 계정 검증 - 보라색 */
    div[class*="st-key-btn_verify"] button {
        background: linear-gradient(180deg, #8b5cf6 0%, #7c3aed 100%) !important;
        color: white !important;
        border: 2px solid #7c3aed !important;
        font-weight: 700 !important;
    }

    /* LIVE 운용자산 저장 - 파란색 */
    div[class*="st-key-btn_save_capital"] button {
        background: linear-gradient(180deg, #3b82f6 0%, #2563eb 100%) !important;
        color: white !important;
        border: 2px solid #2563eb !important;
        font-weight: 700 !important;
    }

    /* 입장하기 버튼 - 초록색 */
    div[class*="st-key-btn_start_trading"] button {
        background: linear-gradient(180deg, #22c55e 0%, #16a34a 100%) !important;
        color: white !important;
        border: 2px solid #16a34a !important;
        font-weight: 700 !important;
    }

    /* 파라미터 설정하기 - 파란색 */
    div[class*="st-key-btn_start_setting"] button {
        background: linear-gradient(180deg, #3b82f6 0%, #2563eb 100%) !important;
        color: white !important;
        border: 2px solid #2563eb !important;
        font-weight: 700 !important;
    }

    /* 로그아웃 - 회색 */
    div[class*="st-key-btn_logout"] button {
        background: linear-gradient(180deg, #6b7280 0%, #4b5563 100%) !important;
        color: white !important;
        border: 2px solid #4b5563 !important;
        font-weight: 700 !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

IS_CLOUD = st.secrets.get("environment") == "cloud"
# 환경별 인증 정보 로딩
if IS_CLOUD:
    # Streamlit Cloud 환경: secrets.toml 사용
    config = {
        "cookie": {
            "expiry_days": st.secrets.cookie_expiry_days,
            "key": st.secrets.cookie_key,
            "name": st.secrets.cookie_name,
        },
        "credentials": {
            # 💥 deepcopy 사용하지 말고 dict로 명시적으로 재구성
            "usernames": {k: dict(v) for k, v in st.secrets.usernames.items()}
        },
    }
else:
    # 로컬 환경: credentials.yaml 사용
    with open("credentials.yaml") as file:
        raw_config = yaml.load(file, Loader=SafeLoader)
        config = {
            "cookie": {
                "expiry_days": raw_config["cookie"]["expiry_days"],
                "key": raw_config["cookie"]["key"],
                "name": raw_config["cookie"]["name"],
            },
            "credentials": {"usernames": dict(raw_config["credentials"]["usernames"])},
        }

authenticator = stauth.Authenticate(
    config["credentials"],
    config["cookie"]["name"],
    config["cookie"]["key"],
    config["cookie"]["expiry_days"],
)

st.session_state.setdefault("mode", "TEST")

# 로그인 UI
login_placeholder = st.empty()
with login_placeholder.container():
    authenticator.login(
        "main",
        fields={
            "Form name": "로그인",
            "Username": "아이디",
            "Password": "비밀번호",
            "Login": "로그인",
        },
    )

    # 세션 상태 초기화 (토글 렌더링 전)
    if "live_mode_toggle" not in st.session_state:
        st.session_state["live_mode_toggle"] = True  # 기본값 LIVE

    _has_toggle = hasattr(st, "toggle")
    if _has_toggle:
        st.toggle(
            "LIVE 모드",
            key="live_mode_toggle",
            help="OFF면 TEST, ON이면 LIVE로 동작합니다.",
        )
        st.session_state["mode"] = "LIVE" if st.session_state["live_mode_toggle"] else "TEST"
    else:
        _mode_choice = st.radio(
            "운용 모드 선택",
            ["TEST", "LIVE"],
            index=1,
            horizontal=True,
            help="기본값은 LIVE입니다.",
        )
        st.session_state["mode"] = _mode_choice

    # 모드 변경 감지
    current_mode = st.session_state.get("mode", "LIVE")
    mode_changed = current_mode != st.session_state.get("_last_mode", "LIVE")
    if mode_changed:
        # 모드가 바뀌면 LIVE 자동검증 플래그 초기화
        st.session_state["_auto_checked_in_live"] = False
        st.session_state["_last_mode"] = current_mode


authentication_status = st.session_state.get("authentication_status")
name = st.session_state.get("name")
username = st.session_state.get("username")

# 로그인 분기 처리
if authentication_status is False:
    st.error("아이디 또는 비밀번호가 올바르지 않습니다.")
elif authentication_status is None:
    st.warning("아이디와 비밀번호를 입력해 주세요.")
elif authentication_status:
    login_placeholder.empty()
    
    _mode = st.session_state.get("mode", "TEST")
    mode_suffix = "LIVE" if _mode == "LIVE" else "TEST"
    
    st.success(f"환영합니다, {name}님!  (모드: {mode_suffix})")

    # 2025-08-04 DB 분리
    init_db_if_needed(username)
    
    # 🏥 24시간 운영: 헬스 모니터링 자동 시작
    start_health_monitoring()

    # 초기 세션 설정
    st.session_state.setdefault("user_id", username)
    st.session_state.setdefault("virtual_krw", 0)
    st.session_state.setdefault("virtual_over", False)

    # ✅ FIX: 기존 사용자 DB 로드 (LIVE/TEST 공통)
    #    - 세션 초기화 시 virtual_krw를 DB에서 복원
    #    - TEST 모드(L437-443)와 동일한 로직을 LIVE 모드에도 적용
    #    - 파라미터 설정하기 버튼 클릭 시 virtual_krw=0 오류 방지
    if st.session_state.virtual_krw == 0:
        user_info = get_user(username)
        if user_info:
            _, db_virtual_krw, _ = user_info
            if db_virtual_krw and db_virtual_krw > 0:
                st.session_state.virtual_krw = db_virtual_krw
                st.session_state.virtual_over = True
                logger.info(f"[DB-LOAD] virtual_krw 복원: {db_virtual_krw:,.0f} KRW (user={username}, mode={_mode})")

    # ✅ WO-2026-002: LIVE 모드 자동 계좌검증 + 운용자산 설정
    if _mode == "LIVE" and not st.session_state.get("_auto_checked_in_live"):
        ak, sk = ACCESS, SECRET
        if ak and sk:
            with st.spinner("🔄 LIVE 모드 자동 계좌검증 중..."):
                ok, data = validate_upbit_keys(ak, sk)

            if ok:
                # 1. 계좌검증 상태 저장
                st.session_state.upbit_verified = True
                st.session_state.upbit_accounts = data or []

                # 2. KRW 잔고 추출
                krw_balance = _extract_krw_balance(data)
                st.session_state.live_krw_balance = krw_balance

                # 3. ✅ 운용자산 자동 설정 (전체 잔고 사용)
                st.session_state.virtual_krw = krw_balance
                st.session_state.live_capital_set = True
                st.session_state.virtual_over = True

                # 4. DB 저장
                save_user(username, name, krw_balance)

                # 5. DB 잔고 동기화
                try:
                    from services.db import update_account_from_balances, update_position_from_balances
                    update_account_from_balances(username, data)
                    # 모든 코인 포지션도 동기화
                    for bal in (data or []):
                        currency = bal.get("currency", "").upper()
                        if currency and currency != "KRW":
                            ticker = f"KRW-{currency}"
                            update_position_from_balances(username, ticker, data)
                    logger.info(f"✅ [AUTO-VERIFY] DB 잔고 동기화 완료: user={username}")
                except Exception as e:
                    logger.error(f"⚠️ [AUTO-VERIFY] DB 잔고 동기화 실패: {e}")

                # 6. 자동검증 플래그 설정
                st.session_state["_auto_checked_in_live"] = True

                # 7. 성공 메시지
                st.success(
                    f"✅ 자동 계좌검증 완료\n\n"
                    f"- KRW 잔고: {krw_balance:,.0f} KRW\n"
                    f"- 운용자산: {krw_balance:,.0f} KRW (자동 설정)\n"
                    f"- DB 동기화: 완료",
                    icon="✅"
                )
            else:
                # 검증 실패
                st.session_state.upbit_verified = False
                st.session_state.upbit_accounts = []
                st.session_state.live_krw_balance = 0.0
                st.session_state.live_capital_set = False
                st.error(
                    f"❌ 자동 계좌검증 실패: {data}\n\n"
                    "API 키를 확인하거나 수동으로 '계정 검증 실행' 버튼을 클릭하세요.",
                    icon="❌"
                )

    if _mode == "LIVE":
        with st.container(border=True):
            st.subheader("🔐 Upbit 계정 검증 (LIVE 전용)")
            ak, sk = ACCESS, SECRET
            if not ak or not sk:
                st.error("config 또는 secrets에서 ACCESS/SECRET을 찾을 수 없습니다.")
            else:
                st.caption(f"ACCESS: {_mask(ak)} / SECRET: {_mask(sk)}")
                col1, col2 = st.columns([1,1])
                with col1:
                    do_verify = st.button("계정 검증 실행", key="btn_verify", use_container_width=True)
                with col2:
                    with st.expander("🔍 서버 정보"):
                        server_ip = get_server_public_ip()
                        st.code(f"서버 공인 IP: {server_ip}")
                        st.caption("이 IP를 Upbit API 설정에 등록해야 합니다.")

                    # ✅ WO-2026-002: 자동검증 상태 표시
                    if st.session_state.get("_auto_checked_in_live"):
                        st.info("✅ 자동 검증 완료됨 (재검증이 필요하면 아래 버튼 클릭)", icon="ℹ️")

                    if st.session_state.get("upbit_verified"):
                        krw = st.session_state.get("live_krw_balance", 0.0)
                        st.success(
                            f"검증 성공 ✅ (KRW 잔고: {krw:,.0f} KRW)", icon="✅"
                        )
                    else:
                        st.info("검증이 필요합니다.", icon="ℹ️")
                    
                if do_verify:
                    with st.spinner("Upbit 키 검증 중..."):
                        ok, data = validate_upbit_keys(ak, sk)

                    if ok:
                        st.session_state.upbit_verified = True
                        st.session_state.upbit_accounts = data or []

                        krw_balance = _extract_krw_balance(st.session_state.upbit_accounts)
                        st.session_state.live_krw_balance = krw_balance
                        st.session_state.live_capital_set = True

                        # ✅ WO-2026-002: 수동 검증 시에도 운용자산 자동 설정
                        st.session_state.virtual_krw = krw_balance
                        st.session_state.virtual_over = True
                        save_user(username, name, krw_balance)

                        # ✅ 계정 검증 성공 시 즉시 DB 잔고 동기화
                        from services.db import update_account_from_balances, update_position_from_balances
                        try:
                            update_account_from_balances(username, data)
                            # 모든 코인 포지션도 동기화
                            for bal in (data or []):
                                currency = bal.get("currency", "").upper()
                                if currency and currency != "KRW":
                                    ticker = f"KRW-{currency}"
                                    update_position_from_balances(username, ticker, data)
                            logger.info(f"✅ [VERIFY] DB 잔고 동기화 완료: user={username}")
                        except Exception as e:
                            logger.error(f"⚠️ [VERIFY] DB 잔고 동기화 실패: {e}")

                        st.success("Upbit 계정 검증 성공! 잔고 정보를 표로 표시합니다.")
                        if st.session_state.upbit_accounts:
                            st.dataframe(
                                st.session_state.upbit_accounts,
                                use_container_width=True,
                                hide_index=True
                            )
                        else:
                            st.error("잔고가 비어있거나 0원으로 조회되었습니다.")
                    else:
                        st.session_state.upbit_verified = False
                        st.session_state.upbit_accounts = []
                        st.session_state.live_krw_balance = 0.0
                        st.session_state.live_capital_set = False
                        st.error(f"Upbit 계정 검증 실패: {data}")


    st.title(f"🤖 Upbit Trade Bot v1 ({mode_suffix})")
    start_trading = None

    disabled_live_gate = (_mode == "LIVE" and not st.session_state.get("upbit_verified"))

    if _mode == "LIVE":
        krw_balance = st.session_state.get("live_krw_balance", 0.0)
        accounts = st.session_state.get("upbit_accounts", [])
        has_coin_pos = _has_any_coin_position(accounts)

        if not st.session_state.get("upbit_verified"):
            st.warning("LIVE 입장 전 Upbit 계정 검증이 필요합니다.")
            start_trading = None
        elif krw_balance <= 0 and not has_coin_pos:
            st.error("Upbit 계정의 KRW 잔고가 0원이고, 보유 중인 코인 포지션도 없습니다.")
            start_trading = None
        elif krw_balance < MIN_CASH and not has_coin_pos:
            st.error(
                f"Upbit 계정의 KRW 잔고({krw_balance:,.0f} KRW)가 "
                f"최소 주문 가능 금액({MIN_CASH} KRW)보다 작고, 보유 코인 포지션이 없습니다."
            )
            start_trading = None
        else:
            # ✅ WO-2026-002: LIVE 운용자산 자동 설정 (간단한 표시만)
            st.subheader("💰 LIVE 운용자산 (자동 설정됨)")

            current_virtual_krw = st.session_state.get("virtual_krw", 0)

            if has_coin_pos and krw_balance < MIN_CASH:
                # 코인 보유 케이스
                st.info(
                    f"**현재 운용자산**: {current_virtual_krw:,.0f} KRW\n\n"
                    f"KRW 잔고: {krw_balance:,.0f} KRW (코인 포지션 보유 중)\n\n"
                    "계좌검증 시 자동으로 설정되었습니다.\n"
                    "운용자산 변경을 원하시면 파라미터 설정 페이지를 이용하세요.",
                    icon="💰"
                )
            else:
                # 일반 케이스
                st.info(
                    f"**현재 운용자산**: {current_virtual_krw:,.0f} KRW\n\n"
                    f"KRW 잔고: {krw_balance:,.0f} KRW\n\n"
                    "계좌검증 시 Upbit KRW 잔고로 자동 설정되었습니다.\n"
                    "운용자산 변경을 원하시면 파라미터 설정 페이지를 이용하세요.",
                    icon="💰"
                )

            # ✅ WO-2026-002: 입장하기 버튼 (중복 표시 제거)
            start_trading = None
            if st.session_state.get("live_capital_set"):
                start_trading = st.button(
                    f"Upbit Trade Bot v1 ({mode_suffix}) 입장하기",
                    key="btn_start_trading_live",
                    use_container_width=True,
                )
    else:
        user_info = get_user(username)
        st.write(f"{username} / {user_info}")

        if user_info:
            _, virtual_krw, _ = user_info
            st.balloons()
            st.session_state.virtual_krw = virtual_krw

            start_trading = st.button(
                f"Upbit Trade Bot v1 ({mode_suffix}) 입장하기", key="btn_start_trading_test", use_container_width=True
            )
        else:
            st.subheader("🔧 운용자산 설정")
            with st.form("input_form"):
                cash = st.number_input(
                    "운용자산(KRW)",
                    10_000,
                    100_000_000_000,
                    1_000_000,
                    10_000
                )
                submitted = st.form_submit_button(
                    f"🧪 {mode_suffix} 운용자산 설정하기",
                    use_container_width=True,
                    disabled=disabled_live_gate,
                )

            if submitted:
                if MIN_CASH > cash:
                    st.error(
                        f"설정한 운용자산이 최소주문가능금액({MIN_CASH} KRW)보다 작습니다."
                    )
                    st.stop()

                st.session_state.virtual_krw = cash
                st.session_state.virtual_over = True

            if st.session_state.virtual_over:
                save_user(
                    st.session_state.user_id,
                    st.session_state.name,
                    st.session_state.virtual_krw,
                )
                st.subheader("운용자산")
                st.info(f"{st.session_state.virtual_krw:.0f} KRW")

                start_trading = st.button(
                    f"Upbit Trade Bot v1 ({mode_suffix}) 입장하기",
                    key="btn_start_trading",
                    use_container_width=True,
                    disabled=disabled_live_gate,
                )

    # 페이지 이동 처리
    if start_trading:
        next_page = "dashboard"
        # ✅ 활성 전략 파일에서 strategy_type 로드
        strategy_type = load_active_strategy(username) or DEFAULT_STRATEGY_TYPE
        params = urlencode({
            "user_id": st.session_state.user_id,
            "virtual_krw": st.session_state.virtual_krw,
            "mode": st.session_state.get("mode", "TEST"),
            "verified": int(bool(st.session_state.get("upbit_verified"))),
            "capital_set": int(bool(st.session_state.get("live_capital_set"))),
            "strategy_type": strategy_type,
        })
        st.markdown(
            f'<meta http-equiv="refresh" content="0; url=./{next_page}?{params}">',
            unsafe_allow_html=True,
        )
        st.stop()

    live_ready = bool(st.session_state.get("upbit_verified")) and bool(st.session_state.get("live_capital_set"))

    start_setting = st.button(
        f"Upbit Trade Bot v1 ({mode_suffix}) 파라미터 설정하기",
        key="btn_start_setting",
        use_container_width=True,
        disabled=(_mode == "LIVE" and not live_ready)
    )

    if start_setting:
        next_page = "set_config"
        # ✅ 활성 전략 파일에서 strategy_type 로드
        strategy_type = load_active_strategy(username) or DEFAULT_STRATEGY_TYPE
        params = urlencode({
            "virtual_krw": st.session_state.virtual_krw,
            "user_id": st.session_state.user_id,
            "mode": st.session_state.get("mode", "TEST"),
            "verified": int(bool(st.session_state.get("upbit_verified"))),
            "capital_set": int(bool(st.session_state.get("live_capital_set"))),
            "strategy_type": strategy_type,
        })
        st.markdown(
            f'<meta http-equiv="refresh" content="0; url=./{next_page}?{params}">',
            unsafe_allow_html=True,
        )
        st.stop()

    # render_db_smoke_test(user_id=username, ticker="KRW-BTC", interval_sec=60)

    logout = st.button("로그아웃하기", key="btn_logout", use_container_width=True)
    if logout:
        st.markdown(
            f'<meta http-equiv="refresh" content="0; url=/?redirected=1">',
            unsafe_allow_html=True,
        )
