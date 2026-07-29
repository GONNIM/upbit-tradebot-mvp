"""
✅ [Phase 3-D] System Health Dashboard — 실시간 invariant / 봇 헬스 모니터링.

목적:
- 사용자가 봇 상태를 대시보드 한 페이지에서 즉시 확인.
- invariant 위반, wallet vs memory 정합성, 최근 CRITICAL 이력.
- 사건 감지 시간 (최대 2.5일) → (수 분) 단축.

원칙:
- 순수 조회 페이지. DB 쓰기 없음.
- 실패 시 페이지 자체 crash 금지 (모든 조회 try/except).
"""
from __future__ import annotations

import streamlit as st
from datetime import datetime
from zoneinfo import ZoneInfo

from services.page_context import bootstrap_page_context, navigate_to  # noqa: E402
from ui.style import style_main


# --- 페이지 설정 ---
st.set_page_config(page_title="System Health — Tradebot", page_icon="🩺", layout="wide")
st.markdown(style_main, unsafe_allow_html=True)

# ✅ 세션 컨텍스트 로드
bootstrap_page_context(required=("user_id",))

qp = st.query_params


def _get_param(qp, key, default=None):
    v = qp.get(key, default)
    if isinstance(v, list):
        return v[0]
    return v


user_id = _get_param(qp, "user_id", st.session_state.get("user_id", ""))
ticker = _get_param(qp, "ticker", st.session_state.get("ticker", "KRW-JTO"))

st.session_state["user_id"] = user_id


# --- 페이지 제목 ---
st.markdown(f"# 🩺 System Health — `{user_id}` / `{ticker}`")
st.caption(
    "실시간 봇 상태 모니터링. 매 봉마다 invariant 스냅샷 기록. "
    "위반 발생 시 텔레그램 CRITICAL 알림 및 이 페이지에 이력 표시."
)


# ============================================================
# 헬스 배지 (상단 헤더)
# ============================================================
try:
    from services.invariant_monitor import (
        get_health_status, get_latest_snapshot, get_recent_violations,
    )

    health = get_health_status(user_id, ticker)

    color_emoji = {
        "green": "🟢",
        "yellow": "🟡",
        "red": "🔴",
        "gray": "⚪",
    }.get(health["color"], "⚪")

    _hcol1, _hcol2, _hcol3 = st.columns([1, 3, 2])
    with _hcol1:
        st.markdown(f"## {color_emoji}")
        st.caption(f"**{health['status'].upper()}**")
    with _hcol2:
        st.info(f"**사유**: {health['reason']}")
    with _hcol3:
        st.metric("최근 1시간 위반", f"{health['violation_count_1h']}건")
        if health["latest_snapshot_ts"]:
            st.caption(f"🕐 마지막 스냅샷: {health['latest_snapshot_ts'][:19]}")
except Exception as e:
    st.error(f"헬스 판정 실패: {e}")


st.divider()


# ============================================================
# 최신 스냅샷 상세 (wallet vs memory)
# ============================================================
try:
    st.subheader("📊 최신 상태 스냅샷 (wallet vs memory)")

    snapshot = get_latest_snapshot(user_id, ticker)
    if snapshot is None:
        st.info("아직 스냅샷 기록 없음. 봇 실행 후 봉 처리 시 자동 기록됩니다.")
    else:
        _sc1, _sc2, _sc3 = st.columns(3)

        with _sc1:
            st.markdown("**Memory (봇 인식)**")
            st.metric("has_position", "✅ TRUE" if snapshot["has_position"] else "❌ FALSE")
            st.metric("qty", f"{snapshot['qty'] or 0:.6f}")
            st.metric("avg_price", f"₩{snapshot['avg_price'] or 0:,.2f}")
            st.metric("entry_ts", str(snapshot["entry_ts"] or "-")[:19])

        with _sc2:
            st.markdown("**Wallet (Upbit 실측)**")
            wallet_qty = snapshot.get("wallet_qty")
            wallet_avg = snapshot.get("wallet_avg")
            st.metric(
                "wallet_qty",
                f"{wallet_qty or 0:.6f}" if wallet_qty is not None else "N/A",
            )
            st.metric(
                "wallet_avg_buy_price",
                f"₩{wallet_avg or 0:,.2f}" if wallet_avg is not None else "N/A",
            )
            # 정합성 판정
            mem_qty = snapshot["qty"] or 0
            if wallet_qty is not None:
                divergence = abs(mem_qty - wallet_qty)
                if divergence > 1e-6:
                    st.warning(f"⚠️ 수량 불일치: {divergence:.6f}")
                else:
                    st.success("✅ 수량 일치")

        with _sc3:
            st.markdown("**Trailing / Highest**")
            st.metric(
                "trailing_armed",
                "✅ ON" if snapshot["trailing_armed"] else "❌ OFF",
            )
            hp = snapshot["highest_price"]
            st.metric("highest_price", f"₩{hp or 0:,.2f}" if hp else "-")
            # 위반 있으면 표시
            if snapshot["violation_code"]:
                st.error(
                    f"🚨 {snapshot['violation_code']}\n\n{snapshot['violation_msg']}"
                )
            else:
                st.success("✅ 이번 스냅샷 위반 없음")
except Exception as e:
    st.error(f"스냅샷 조회 실패: {e}")


st.divider()


# ============================================================
# 최근 CRITICAL 이력
# ============================================================
try:
    st.subheader("🚨 최근 CRITICAL 이력 (invariant 위반)")

    hours = st.slider("조회 기간 (시간)", min_value=1, max_value=168, value=24, step=1)
    violations = get_recent_violations(user_id, ticker, hours=hours, limit=100)

    if not violations:
        st.success(f"✅ 최근 {hours}시간 내 invariant 위반 없음")
    else:
        st.warning(f"⚠️ {len(violations)}건 위반 감지 (최근 {hours}시간)")
        import pandas as _pd
        df = _pd.DataFrame(violations)
        # timestamp 축약
        if "timestamp" in df.columns:
            df["timestamp"] = df["timestamp"].astype(str).str[:19]
        st.dataframe(df, use_container_width=True, hide_index=True)
except Exception as e:
    st.error(f"위반 이력 조회 실패: {e}")


st.divider()


# ============================================================
# Audit Log 파일 위치 안내
# ============================================================
st.subheader("📝 Audit Log 파일")
st.caption(
    "매매 이벤트가 JSONL 로 기록됨. rotation 20 × 10MB (총 200MB 상한). "
    "grep/awk 로 사후 분석 편의."
)
st.code(f"tail -f /root/upbit-tradebot-mvp/{user_id}_audit.log", language="bash")
st.code(
    f'grep -E \'"code": "SL_TRIG"\' /root/upbit-tradebot-mvp/{user_id}_audit.log | tail -20',
    language="bash",
)


st.divider()


# ============================================================
# 뒤로 가기
# ============================================================
if st.button("↩️ 대시보드로 돌아가기", use_container_width=True):
    navigate_to("pages/dashboard.py", user_id=user_id)
