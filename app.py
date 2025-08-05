from urllib.parse import urlencode
import streamlit as st
import streamlit_authenticator as stauth
from ui.style import style_main
from config import MIN_CASH
from services.db import get_user, save_user
from services.init_db import reset_db
import os
import yaml
from yaml.loader import SafeLoader
from services.init_db import init_db_if_needed


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
    st.success(f"환영합니다, {name}님!")

    # 2025-08-04 DB 분리
    init_db_if_needed(username)

    # 초기 세션 설정
    st.session_state.setdefault("user_id", username)
    st.session_state.setdefault("virtual_krw", 0)
    st.session_state.setdefault("virtual_over", False)

    st.title("🤖 Upbit Trade Bot v1 (TEST)")
    start_trading = None
    user_info = get_user(username)
    st.write(f"{username} / {user_info}")

    if user_info:
        _, virtual_krw, _ = user_info
        st.balloons()
        st.session_state.virtual_krw = virtual_krw
        start_trading = st.button(
            "Upbit Trade Bot v1 (TEST) 입장하기", use_container_width=True
        )
    else:
        st.subheader("🔧 가상 보유자산 설정")
        with st.form("input_form"):
            cash = st.number_input(
                "가상 보유자산(KRW)", 10_000, 100_000_000_000, 1_000_000, 10_000
            )
            submitted = st.form_submit_button(
                "🧪 TEST 가상 보유자산 설정하기", use_container_width=True
            )

        if submitted:
            if MIN_CASH > cash:
                st.error(
                    f"설정한 가상 보유자산이 최소주문가능금액({MIN_CASH} KRW)보다 작습니다."
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
            st.subheader("가상 보유자산")
            st.info(f"{st.session_state.virtual_krw:.0f} KRW")

            start_trading = st.button(
                "Upbit Trade Bot v1 (TEST) 입장하기", use_container_width=True
            )

    # 페이지 이동 처리
    if start_trading:
        next_page = "dashboard"

        params = urlencode(
            {
                "virtual_krw": st.session_state.virtual_krw,
                "user_id": st.session_state.user_id,
            }
        )

        st.markdown(
            f'<meta http-equiv="refresh" content="0; url=./{next_page}?{params}">',
            unsafe_allow_html=True,
        )
        st.switch_page(next_page)

    start_setting = st.button(
        "Upbit Trade Bot v1 (TEST) 파라미터 설정하기", use_container_width=True
    )
    if start_setting:
        next_page = "set_config"

        params = urlencode(
            {
                "virtual_krw": st.session_state.virtual_krw,
                "user_id": st.session_state.user_id,
            }
        )

        st.markdown(
            f'<meta http-equiv="refresh" content="0; url=./{next_page}?{params}">',
            unsafe_allow_html=True,
        )
        st.switch_page(next_page)
