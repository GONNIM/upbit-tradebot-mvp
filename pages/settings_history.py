"""
설정 정보 History 뷰어 (P2).

대시보드의 "📜 설정 History 보기" 버튼 → st.switch_page 로 진입.
사용자가 명시 저장한 설정 스냅샷의 시계열 조회 + 행 펼치기.

P3 복원 / P4 PnL / P5 부가 기능은 같은 페이지에서 단계적으로 확장된다.
상세: docs/plans/settings-history/{plan.md, module-contract.md}
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from services.settings_history import (
    RestoreError,
    diff_against_previous,
    fetch_history,
    fetch_snapshot,
    restore_snapshot,
)

# ============================================================
# 기본 설정 & 사이드바 숨김 (audit_viewer 패턴)
# ============================================================
st.set_page_config(page_title="Settings History", page_icon="📜", layout="wide")
st.markdown(
    "<style>[data-testid='stSidebar']{display:none !important;}</style>",
    unsafe_allow_html=True,
)
st.markdown(
    """
    <style>
    div.block-container { padding-top: 1rem; }
    h1 { margin-top: 0 !important; }
    [data-testid="stSidebarHeader"],
    [data-testid="stSidebarNavItems"],
    [data-testid="stSidebarNavSeparator"] { display: none !important; }
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# URL / session_state 파라미터 수집
# ============================================================
qp = st.query_params


def _get_param(qp, key, default=None):
    v = qp.get(key, default)
    if isinstance(v, list):
        return v[0]
    return v


user_id = _get_param(qp, "user_id", st.session_state.get("user_id", ""))
mode = str(_get_param(qp, "mode", st.session_state.get("mode", "TEST"))).upper()
strategy_from_url = _get_param(qp, "strategy_type", None)
strategy_from_session = st.session_state.get("strategy_type", None)
active_strategy = (strategy_from_url or strategy_from_session or "EMA").upper()

# session_state 동기화 (Issue #14 패턴)
st.session_state["user_id"] = user_id
st.session_state["mode"] = mode
st.session_state["strategy_type"] = active_strategy


# ============================================================
# 헤더
# ============================================================
header_col_l, header_col_r = st.columns([5, 1])
with header_col_l:
    st.markdown(f"### 📜 설정 정보 History · `{user_id}` · {mode}")
with header_col_r:
    if st.button("⬅ 대시보드", use_container_width=True):
        st.switch_page("pages/dashboard.py")

if not user_id:
    st.error("user_id 가 비어있습니다. 대시보드에서 다시 진입해 주세요.")
    st.stop()


# ============================================================
# 필터바
# ============================================================
f1, f2, f3, f4 = st.columns([1, 1, 1, 1])

with f1:
    strategy_filter = st.selectbox(
        "전략",
        options=["All", "MACD", "EMA"],
        index=(["All", "MACD", "EMA"].index(active_strategy)
               if active_strategy in ("MACD", "EMA") else 0),
        key="sh_strategy_filter",
    )

with f2:
    page_options = [
        "All",
        "set_config",
        "set_buy_sell_conditions",
        "initial_seed",
        "restore",
        "auto_pre_restore",
    ]
    page_filter = st.selectbox(
        "기록 위치 (source_page)",
        options=page_options,
        index=0,
        key="sh_page_filter",
    )

with f3:
    period_label = st.selectbox(
        "기간",
        options=["전체", "최근 7일", "최근 30일"],
        index=0,
        key="sh_period_filter",
    )

with f4:
    limit = st.selectbox(
        "표시 행수",
        options=[50, 100, 200],
        index=1,
        key="sh_limit",
    )


# 필터 → fetch_history 인자
def _since_ts(period_label: str):
    if period_label == "최근 7일":
        return (datetime.now(ZoneInfo("Asia/Seoul")) - timedelta(days=7)).isoformat()
    if period_label == "최근 30일":
        return (datetime.now(ZoneInfo("Asia/Seoul")) - timedelta(days=30)).isoformat()
    return None


rows = fetch_history(
    user_id,
    strategy_type=(None if strategy_filter == "All" else strategy_filter),
    source_page=(None if page_filter == "All" else page_filter),
    since_ts=_since_ts(period_label),
    limit=int(limit),
)


# ============================================================
# 본문 - 데이터프레임 + 행 펼치기
# ============================================================
if not rows:
    st.info("표시할 설정 History 가 없습니다. 설정 페이지에서 저장하면 이곳에 누적됩니다.")
    st.stop()


def _format_saved_at(s: str | None) -> str:
    if not s:
        return ""
    try:
        return datetime.fromisoformat(s).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return s


# ✅ P4 — 행 단위 PnL 계산 (구간 거래 집계). 표 컬럼에 노출.
from services.settings_history import compute_pnl_for_snapshot


def _format_pnl(pnl: dict) -> dict:
    """PnL dict → 표 컬럼 문자열."""
    real = pnl.get("realized_pnl_krw")
    real_s = ("-" if real is None else f"{real:+,.0f}원")
    bs = pnl.get("trades_bs", (0, 0))
    win = pnl.get("win", 0)
    loss = pnl.get("loss", 0)
    if (win + loss) == 0:
        winrate_s = "-"
    else:
        winrate_s = f"{(win / (win + loss)) * 100:.0f}% ({win}/{loss})"
    avg_hold = pnl.get("avg_bars_held")
    if avg_hold is None:
        avg_hold_s = "-"
    else:
        avg_hold_s = f"{avg_hold:.1f}봉"
    return {
        "실현 손익": real_s,
        "거래(B/S)": f"{bs[0]}/{bs[1]}",
        "승률 (수익/손해)": winrate_s,
        "평균 보유": avg_hold_s,
    }


# PnL 사전 계산 (한 번에 표시)
pnl_cache = {}
for r in rows:
    try:
        pnl_cache[r["id"]] = compute_pnl_for_snapshot(user_id, r["id"])
    except Exception:
        pnl_cache[r["id"]] = {
            "realized_pnl_krw": None,
            "trades_bs": (0, 0),
            "win": 0, "loss": 0, "flat": 0,
            "avg_bars_held": None,
            "interval_label": "-",
        }


# 표용 dict 리스트
table_rows = []
for r in rows:
    pnl = pnl_cache[r["id"]]
    pnl_disp = _format_pnl(pnl)
    # ✅ SP2 — 사용자 저장 → 엔진 적용 격차 계산
    _saved = r.get("saved_at") or ""
    _applied = r.get("applied_at") or ""
    if _saved and _applied:
        try:
            _delta = (datetime.fromisoformat(_applied) - datetime.fromisoformat(_saved)).total_seconds()
            if _delta < 60:
                _gap_disp = f"{int(_delta)}초"
            elif _delta < 3600:
                _gap_disp = f"{int(_delta // 60)}분 {int(_delta % 60)}초"
            else:
                _gap_disp = f"{int(_delta // 3600)}시간 {int((_delta % 3600) // 60)}분"
        except Exception:
            _gap_disp = "-"
    elif _applied:
        _gap_disp = "즉시"
    else:
        _gap_disp = "미적용"
    table_rows.append({
        "id": r["id"],
        "시간(KST)": _format_saved_at(r["saved_at"]),
        "전략": r["strategy_type"],
        "기록 위치": r["source_page"],
        "적용 시각": _format_saved_at(r.get("applied_at")) or "—",
        "적용 격차": _gap_disp,
        "유효 구간": pnl.get("interval_label", "-"),
        "실현 손익": pnl_disp["실현 손익"],
        "거래(B/S)": pnl_disp["거래(B/S)"],
        "승률 (수익/손해)": pnl_disp["승률 (수익/손해)"],
        "평균 보유": pnl_disp["평균 보유"],
        "앱 버전": r["app_version"] or "-",
        "비고": r["note"] or "",
    })

df = pd.DataFrame(table_rows)
st.dataframe(
    df,
    use_container_width=True,
    hide_index=True,
    column_config={
        "id": st.column_config.NumberColumn("id", width="small"),
        # ✅ UX: 시간 컬럼은 ISO 형식이 짧아서 small 로 축소
        "시간(KST)": st.column_config.Column(width="small"),
        "전략": st.column_config.Column(width="small"),
        "기록 위치": st.column_config.Column(width="medium"),
        "적용 시각": st.column_config.Column(width="small"),
        "적용 격차": st.column_config.Column(width="small"),
        "유효 구간": st.column_config.Column(width="small"),
        "실현 손익": st.column_config.Column(width="small"),
        "거래(B/S)": st.column_config.Column(width="small"),
        "승률 (수익/손해)": st.column_config.Column(width="small"),
        "평균 보유": st.column_config.Column(width="small"),
        # ✅ UX: 앱 버전 'v1.2026.06.16.1655' 형식이 길어 medium 으로 확대
        "앱 버전": st.column_config.Column(width="medium"),
        "비고": st.column_config.Column(width="medium"),
    },
)

st.divider()

# ============================================================
# 스냅샷 상세 보기 — 토글 (디폴트 숨김)
# ============================================================
# ✅ UX: 스냅샷 상세/거래/복원/다운로드를 한 expander 로 묶어 디폴트 숨김.
# 사용자가 펼침 버튼 한 번으로 전체 상세 영역을 열고 닫을 수 있다.
with st.expander("🔎 스냅샷 상세 보기 (펼치기 / 숨기기)", expanded=False):

    selected_id = st.selectbox(
        "조회할 스냅샷 id",
        options=[r["id"] for r in rows],
        format_func=lambda i: f"id={i} · {_format_saved_at(next(r['saved_at'] for r in rows if r['id'] == i))}",
        key="sh_detail_id",
    )

    snap = fetch_snapshot(user_id, int(selected_id))
    if snap is None:
        st.warning("선택한 스냅샷을 찾을 수 없습니다.")
        st.stop()


    def _pretty_json(s: str | None) -> str:
        if not s:
            return "(없음)"
        try:
            return json.dumps(json.loads(s), ensure_ascii=False, indent=2)
        except Exception:
            return s


    detail_l, detail_r = st.columns(2)
    with detail_l:
        st.markdown("**📦 params snapshot**")
        st.code(_pretty_json(snap["params_json"]), language="json")
    with detail_r:
        st.markdown("**🛠 conditions snapshot**")
        st.code(_pretty_json(snap["conditions_json"]), language="json")


    # diff
    st.markdown("**🆚 직전 동일 (user, strategy) 스냅샷 대비 변경분**")
    try:
        diff = diff_against_previous(user_id, int(selected_id))
        if diff["no_previous"]:
            st.info("이 스냅샷은 같은 전략 내 첫 row 입니다 (직전 비교 없음).")
        else:
            diff_l, diff_r = st.columns(2)

            def _render_diff(d: dict, title: str):
                if not d:
                    st.caption(f"{title}: 변경 없음")
                    return
                data = []
                for k in sorted(d.keys()):
                    data.append({"key": k,
                                 "before": json.dumps(d[k]["before"], ensure_ascii=False),
                                 "after": json.dumps(d[k]["after"], ensure_ascii=False)})
                st.markdown(f"**{title} ({len(d)}건)**")
                st.dataframe(pd.DataFrame(data), use_container_width=True, hide_index=True)

            with diff_l:
                _render_diff(diff["params"], "params")
            with diff_r:
                _render_diff(diff["conditions"], "conditions")
    except Exception as e:
        st.warning(f"diff 계산 실패: {e}")


    # ============================================================
    # P4 — 구간 거래 리스트
    # ============================================================
    st.divider()
    st.markdown("### 📈 이 스냅샷의 구간 거래")

    from services.settings_history import fetch_trades_for_snapshot

    trades = fetch_trades_for_snapshot(user_id, int(selected_id))
    if not trades:
        st.caption("이 구간에 발생한 거래가 없습니다.")
    else:
        trades_df = pd.DataFrame(trades)
        # ✅ timestamp 포맷: YYYY-MM-DD HH:mm:ss.xxx (밀리초 3자리, T 구분자 제거)
        if "timestamp" in trades_df.columns:
            trades_df["timestamp"] = (
                pd.to_datetime(trades_df["timestamp"])
                  .dt.strftime("%Y-%m-%d %H:%M:%S.%f")
                  .str[:-3]
            )
        st.dataframe(
            trades_df,
            use_container_width=True,
            hide_index=True,
        )
        if user_id:
            from urllib.parse import urlencode as _urlencode
            qs = _urlencode({"user_id": user_id, "mode": mode, "tab": "trades"})
            st.markdown(f"[📑 audit_viewer 에서 전체 거래 보기](./audit_viewer?{qs})")


    # ============================================================
    # P3 — 이 설정 불러오기 (Restore) — 사용자 친화 안내 (압축 가독성)
    # ============================================================
    st.divider()
    st.markdown("### 📥 이 설정 불러오기 (복원)")

    # ✅ UX: 안내 3문항을 단일 info 박스 + 압축 HTML 로 묶어 행간 축소.
    # 다크 모드에서도 글자가 보이도록 박스 글자색 명시 (color:#1a1a1a),
    # 강조용 <code> 는 흰색 배경 + 짙은 글자로 명시.
    st.markdown(
        f"""
<div style="background:#eaf4ff;border-left:4px solid #1f77b4;
            padding:10px 14px;border-radius:4px;line-height:1.45;
            color:#1a1a1a;">
  <p style="margin:0 0 0.35rem 0;color:#1a1a1a;"><b>📌 무엇을 하나요?</b><br>
    선택한 스냅샷 <b>id={selected_id}</b>
    (<code style="background:#ffffff;color:#0b3d91;padding:1px 5px;border-radius:3px;">{snap['strategy_type']}</code>
    · <code style="background:#ffffff;color:#0b3d91;padding:1px 5px;border-radius:3px;">{snap['source_page']}</code>
    · <code style="background:#ffffff;color:#0b3d91;padding:1px 5px;border-radius:3px;">{_format_saved_at(snap['saved_at'])}</code>)
    의 <b>전략 파라미터 / 매수·매도 조건</b>을 <b>현재 설정 파일에 덮어씁니다.</b>
    즉, 그 시점의 설정으로 봇을 운영하게 됩니다.</p>
  <p style="margin:0 0 0.35rem 0;color:#1a1a1a;"><b>↩️ 되돌릴 수 있나요?</b><br>
    네. 복원 직전에 <b>"지금 설정"을 자동으로 사전 스냅샷(<code style="background:#ffffff;color:#0b3d91;padding:1px 5px;border-radius:3px;">auto_pre_restore</code>)으로 저장</b>합니다.
    잘못 복원했다면 그 사전 스냅샷을 다시 불러오기로 즉시 되돌릴 수 있습니다.</p>
  <p style="margin:0;color:#1a1a1a;"><b>📈 복원 후 거래는 어떻게 되나요?</b><br>
    이후 발생하는 매수·매도 거래에는 <b>새로 생긴 복원 이벤트 row(active id)</b>가 자동 라벨링되어
    "이 설정으로 얼마나 벌었나" 가 자연스럽게 누적 집계됩니다.</p>
</div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("")  # 박스와 안전장치 사이 단일 간격
    st.markdown("#### ⚠️ 진행 전 안전 장치 확인")
    st.caption("아래 두 가지 경우 기본은 **차단**입니다. 의도적으로 진행하려면 체크박스를 켜 주세요.")

    cb_strategy_col, cb_position_col = st.columns(2)

    with cb_strategy_col:
        # ✅ UX: 항목 ①을 단일 warning 박스로 묶어 시각적 구분 + 행간 압축
        # 다크 모드 대응: color 명시 + code 태그 배경/글자색 강제
        st.markdown(
            f"""
<div style="background:#fff7e6;border-left:4px solid #d97706;
            padding:10px 14px;border-radius:4px;line-height:1.45;
            color:#1a1a1a;">
  <p style="margin:0 0 0.35rem 0;color:#1a1a1a;"><b>① 전략 타입이 다른 스냅샷도 복원할까요?</b></p>
  <p style="margin:0;color:#1a1a1a;">이 스냅샷은 <b>{snap['strategy_type']}</b> 전략입니다.
    현재 봇이 다른 전략(예: 반대 전략)으로 운영 중이라면, 복원 시
    <b>봇의 전략이 <code style="background:#ffffff;color:#7c2d12;padding:1px 5px;border-radius:3px;">{snap['strategy_type']}</code> 로 전환됩니다.</b>
    의도하지 않은 전략 전환은 큰 영향이 있을 수 있어요.</p>
</div>
            """,
            unsafe_allow_html=True,
        )
        confirm_strategy = st.checkbox(
            f"확인했습니다 — `{snap['strategy_type']}` 로 전환되어도 진행합니다",
            value=False,
            key="sh_restore_strategy_ok",
        )

    with cb_position_col:
        # ✅ UX: 항목 ②도 동일 패턴 (다크 모드 글자색 명시)
        st.markdown(
            """
<div style="background:#fff7e6;border-left:4px solid #d97706;
            padding:10px 14px;border-radius:4px;line-height:1.45;
            color:#1a1a1a;">
  <p style="margin:0 0 0.35rem 0;color:#1a1a1a;"><b>② 코인을 보유한 상태에서도 복원할까요?</b></p>
  <p style="margin:0;color:#1a1a1a;">현재 매수해서 들고 있는 코인이 있을 수 있어요.
    복원하면 <b>익절(TP) / 손절(SL) 값이 즉시 새 설정으로 바뀝니다.</b>
    그 결과 보유 중인 코인이 <b>즉시 매도</b>되거나 <b>의도하지 않은 시점에 매도</b>될 수 있어요.</p>
</div>
            """,
            unsafe_allow_html=True,
        )
        confirm_position = st.checkbox(
            "확인했습니다 — 보유 코인이 즉시 영향 받아도 진행합니다",
            value=False,
            key="sh_restore_position_ok",
        )

    st.markdown("")
    do_restore = st.button(
        f"🔄 id={selected_id} 스냅샷으로 복원 실행",
        type="primary",
        use_container_width=True,
        key="sh_do_restore",
    )

    if do_restore:
        try:
            result = restore_snapshot(
                int(selected_id),
                user_id=user_id,
                actor="user",
                require_strategy_match=(not confirm_strategy),
                require_no_open_position=(not confirm_position),
            )
            st.success(
                f"✅ 복원 완료\n\n"
                f"- 사전 스냅샷 id = {result['pre_snapshot_id']} "
                f"(되돌리려면 이 id 를 다시 불러오기)\n"
                f"- 복원 source id = {result['restored_from_id']}\n"
                f"- 새 active id = {result['new_active_id']}\n"
                f"- 변경 항목 수: params {len(result['diff']['params'])}건, "
                f"conditions {len(result['diff']['conditions'])}건"
            )
            if result["warnings"]:
                for w in result["warnings"]:
                    st.warning(w)
            st.button("🔁 페이지 새로고침", on_click=st.rerun)
        except RestoreError as e:
            st.error(f"❌ 복원 실패: {e}")
        except Exception as e:
            st.error(f"❌ 복원 예외: {e}")


# ============================================================
# P5 — 다운로드
# ============================================================
st.divider()
st.markdown("### 📥 다운로드")

dl_l, dl_r = st.columns(2)

with dl_l:
    csv_bytes = df.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "📥 표 CSV 다운로드",
        data=csv_bytes,
        file_name=f"settings_history_{user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv",
        use_container_width=True,
    )

with dl_r:
    full_json = json.dumps(rows, ensure_ascii=False, indent=2, default=str)
    st.download_button(
        "📥 전체 행 JSON 다운로드",
        data=full_json.encode("utf-8"),
        file_name=f"settings_history_{user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
        mime="application/json",
        use_container_width=True,
    )
