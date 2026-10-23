"""구버전 화면의 신버전 대시보드 입장 버튼.

1차 배포 뒤 동결 파일. v2 패키지를 import 하지 않는다.
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
        if st.button("📱 신버전 대시보드 (베타)", key="btn_v2_entry"):
            token = et.make_token(user_id, mode)
            st.link_button("신버전 열기 (60초 안에 눌러 주세요)", f"/v2/?t={token}")
            st.caption("구버전으로 돌아올 때는 다시 로그인해야 합니다")
    except Exception as e:  # noqa: BLE001
        logger.warning("[V2-ENTRY] hidden: %s", type(e).__name__)
