from tracemalloc import start
from urllib.parse import urlencode
import streamlit as st
import streamlit_authenticator as stauth
from ui.style import style_main
from config import MIN_CASH, ACCESS, SECRET
from services.db import get_user, save_user
import yaml
from yaml.loader import SafeLoader
from services.init_db import init_db_if_needed
from services.health_monitor import start_health_monitoring
from utils.smoke_test import render_db_smoke_test

from services.upbit_api import validate_upbit_keys, get_server_public_ip


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

    _has_toggle = hasattr(st, "toggle")
    if _has_toggle:
        live_on = st.toggle(
            "LIVE 모드",
            value=(st.session_state.get("mode") == "LIVE"),
            help="OFF면 TEST, ON이면 LIVE로 동작합니다.",
        )
        st.session_state["mode"] = "LIVE" if live_on else "TEST"
    else:
        _mode_choice = st.radio(
            "운용 모드 선택",
            ["TEST", "LIVE"],
            index=0,
            horizontal=True,
            help="기본값은 TEST입니다.",
        )
        st.session_state["mode"] = _mode_choice

    # 모드 변경 감지
    current_mode = st.session_state.get("mode", "TEST")
    mode_changed = current_mode != st.session_state.get("_last_mode", "TEST")
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
                    do_verify = st.button("계정 검증 실행", use_container_width=True)
                with col2:
                    with st.expander("🔍 서버 정보"):
                        server_ip = get_server_public_ip()
                        st.code(f"서버 공인 IP: {server_ip}")
                        st.caption("이 IP를 Upbit API 설정에 등록해야 합니다.")

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

        if not st.session_state.get("upbit_verified"):
            st.warning("LIVE 입장 전 Upbit 계정 검증이 필요합니다.")
            start_trading = None
        elif krw_balance <= 0:
            st.error("Upbit 계정의 KRW 잔고가 0원입니다. 잔고를 충전한 후 다시 시도하세요.")
            start_trading = None
        elif krw_balance < MIN_CASH:
            st.error(
                f"Upbit 계정의 KRW 잔고({krw_balance:,.0f} KRW)가 "
                f"최소 주문 가능 금액({MIN_CASH} KRW)보다 작습니다."
            )
            start_trading = None
        else:
            user_info = get_user(username)

            if user_info:
                _, virtual_krw, _ = user_info
            else:
                virtual_krw = 0

            st.subheader("💰 LIVE 운용자산 설정 (Upbit KRW 기반)")
            st.caption(
                f"현재 Upbit 계정 KRW 잔고: **{krw_balance:,.0f} KRW**\n\n"
                "이 범위 내에서만 LIVE 운용자산을 설정할 수 있습니다."
            )
            
            default_value = min(virtual_krw, krw_balance) if virtual_krw > 0 else krw_balance

            live_capital = st.number_input(
                "LIVE 운용자산(KRW)",
                min_value=int(MIN_CASH),
                max_value=int(krw_balance),
                value=int(default_value),
                step=10_000,
            )

            save_live_capital = st.button("LIVE 운용자산 저장하기", use_container_width=True)

            if save_live_capital:
                if live_capital > krw_balance:
                    st.error("설정한 운용자산이 KRW 잔고보다 클 수 없습니다.")
                else:
                    st.session_state.virtual_krw = live_capital
                    st.session_state.virtual_over = True
                    st.session_state.live_capital_set = True

                    save_user(
                        st.session_state.user_id,
                        st.session_state.name,
                        live_capital,
                    )

                    st.success(f"LIVE 운용자산이 {live_capital:,.0f} KRW 로 설정되었습니다.")

            start_trading = None
            if st.session_state.get("live_capital_set"):
                st.subheader("운용자산")
                st.info(f"{st.session_state['virtual_krw']:.0f} KRW")

                start_trading = st.button(
                    f"Upbit Trade Bot v1 ({mode_suffix}) 입장하기",
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
                f"Upbit Trade Bot v1 ({mode_suffix}) 입장하기", use_container_width=True
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
                    use_container_width=True,
                    disabled=disabled_live_gate,
                )

    # 페이지 이동 처리
    if start_trading:
        next_page = "dashboard"
        params = urlencode(
            {
                "virtual_krw": st.session_state.virtual_krw,
                "user_id": st.session_state.user_id,
                "mode": st.session_state.get("mode", "TEST"),
            }
        )
        st.markdown(
            f'<meta http-equiv="refresh" content="0; url=./{next_page}?{params}">',
            unsafe_allow_html=True,
        )
        st.stop()

    live_ready = bool(st.session_state.get("upbit_verified")) and bool(st.session_state.get("live_capital_set"))

    start_setting = st.button(
        f"Upbit Trade Bot v1 ({mode_suffix}) 파라미터 설정하기",
        use_container_width=True,
        disabled=(_mode == "LIVE" and not live_ready)
    )

    if start_setting:
        next_page = "set_config"
        params = urlencode(
            {
                "virtual_krw": st.session_state.virtual_krw,
                "user_id": st.session_state.user_id,
                "mode": st.session_state.get("mode", "TEST"),
                "verified": int(bool(st.session_state.get("upbit_verified"))),
                "capital_set": int(bool(st.session_state.get("live_capital_set"))),
            }
        )
        st.markdown(
            f'<meta http-equiv="refresh" content="0; url=./{next_page}?{params}">',
            unsafe_allow_html=True,
        )
        st.stop()

    # render_db_smoke_test(user_id=username, ticker="KRW-BTC", interval_sec=60)
