"""구버전 화면의 신버전 대시보드 입장 버튼.

2026-10-27 결정 1026-19 4 가로 한 번 누르기 이동으로 바꿨다(이전: 버튼 → 링크 단추 두 단계).
구버전 프로세스(tradebot) 안 코드라 바뀐 동작은 엔진 재시작 때만 화면에 반영된다.
v2 패키지를 import 하지 않는다.
토큰 모듈은 모듈 속성으로 접근한다(시험 패치 반영).
"""
import logging

import streamlit as st

import utils.v2_entry_token as et

logger = logging.getLogger(__name__)


def render_v2_entry(user_id: str, mode: str) -> None:
    try:
        if not et.is_allowed(user_id):
            return
        et.read_secret()  # 키가 없거나 깨졌으면 TokenUnavailable -> 버튼 숨김
        # 한 번 누르기: 누른 그 순간 토큰을 만들어 바로 이동한다(app.py 의 페이지 이동과 같은 방식)
        if st.button(f"신버전 대시보드 입장 ({mode})", key="btn_v2_entry",
                     use_container_width=True):
            token = et.make_token(user_id, mode)
            st.markdown(
                f'<meta http-equiv="refresh" content="0; url=/v2/?t={token}">',
                unsafe_allow_html=True,
            )
            st.stop()
    except Exception as e:  # noqa: BLE001
        logger.warning("[V2-ENTRY] hidden: %s", type(e).__name__)
