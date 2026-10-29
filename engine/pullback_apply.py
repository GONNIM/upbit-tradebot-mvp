"""
2차 T13 (결정 D9, 요청서 5절): 「이 설정으로 동작」 — 새 전략(PULLBACK) 저장본을 적용본으로 (엔진 프로세스 쪽).

사용자 결정 1029-05(「권고대로」)·PO 결정 (계획 T13 「구현 메모」):
A. apply_params 요청(감시 스레드, 전역 잠금 안)
   - T12 _guard: 실계좌 → live_not_supported(엔진 무접촉), 다른 모드 엔진 → mode_conflict. 예약(전환·복귀) 중 → already_reserved.
   - 마지막 저장(v2hist 마지막 행 note)이 업비트 출처가 아니면 거절(바이낸스 결과는 참고용). 못 읽으면 거절(fail closed).
   - 이전 적용본·사본 바이트는 apply_saved 전에 호출자가 읽어 둔다(되돌리기용).
   - 바뀐 키에 따라 세 갈래:
       hot     : MA·종목·봉 단위가 그대로. 엔진이 돌면 엔진 제어 큐(core.engine_control APPLY_KIND)로 엔진 스레드에서
                 apply_saved → 생성자와 같은 방식의 새 cfg 로 교체 → engine._pullback_params_sha 갱신 → PARAMS 행.
                 반영은 다음 확정 봉부터(익절·손절·데드크로스도 봉 마감에서 판정). 엔진이 멈췄으면 apply_saved + PARAMS 행만.
       reseed  : MA 기간·방식(ma60p·ma200p·pullbackP·slopeLB·maType) 변경 → apply_saved 뒤 Controller.restart_engine
                 (기동 워밍업이 새 MA 로 다시 시드, 분할 상태는 T6 복원, 그동안 매수 없음).
       restart : 봉 단위(또는 옛 행에서 온 종목) 변경 → 보유가 없을 때만. restart_engine 의 before_start(옛 스레드가 끝난 뒤·
                 시작 앞)에서 pullback_state 행을 다시 읽어 회차 0·수량 0 이면 종목·봉 단위를 새 값으로, 쉼·골든·마지막 봉
                 칸은 비우고, 실현 손익 누적은 그대로. 진행 중이면 손대지 않고 실패로 끝냄.
     재시작이 실패하면 이전 적용본·사본 바이트와 (바꿨으면) 행의 종목·봉 단위를 되돌리고 1회 다시 띄운 뒤 운영자 CRITICAL.
B. 보유 중 봉 단위 변경 거절, C. 보유 중 분할 한도 늘림 거절(줄임은 즉시 — cfg 교체만으로 새 한도 ≤ 지금 회차면 추가 매수 멈춤).
변경 기록: strategy_switch kind PARAMS·state DONE 1행(note = {"changed": {키: [구, 신]}, "apply": next_bar|immediate|reseed|restart}).
live_loop·strategy_engine 은 바꾸지 않는다(적용본 감시 없음 — 적용본은 요청·기동 때만 읽는다).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sqlite3
from typing import Any, Dict, Optional

from engine import pullback_params as pbp
from engine import strategy_switch as ss

logger = logging.getLogger(__name__)

TAG = "[PULLBACK-APPLY]"
MA_KEYS = ("ma60p", "ma200p", "pullbackP", "slopeLB", "maType")
MARKET_KEYS = ("ticker", "interval")
IMMEDIATE_KEYS = ("tp", "sl", "deadcross")
ALL_KEYS = (*pbp.PULLBACK_KEYS, *pbp.OPTIONAL_KEYS)
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")

APPLY_FAILED_TITLE = "🚨 [운영자] 새 전략 설정 적용 실패 — 이전 설정으로 되돌림"
APPLY_FAILED_BODY = ("설정 적용 재시작이 실패했습니다(user={user} why={why}). 적용본·사본을 이전 바이트로 되돌렸고"
                     "{row_note} 이전 설정으로 엔진을 1회 다시 띄웠습니다(결과 {again}). 엔진 상태를 확인해 주세요.")


def _r(status: str, code: str, detail: Optional[dict] = None) -> Dict[str, Any]:
    return {"status": status, "code": code, "detail": dict(detail or {})}


# ================================================================ 파일·값
def _read_or_none(path: str) -> Optional[bytes]:
    try:
        with open(path, "rb") as f:
            return f.read()
    except FileNotFoundError:
        return None


def files_snapshot(user: str) -> Dict[str, Optional[bytes]]:
    """apply_saved 전에 읽어 두는 이전 적용본·사본 바이트(없으면 None)."""
    return {"applied": _read_or_none(pbp.applied_path(user)), "last_good": _read_or_none(pbp.last_good_path(user))}


def restore_files(user: str, snap: Dict[str, Optional[bytes]]) -> bool:
    ok = True
    for key, path in (("applied", pbp.applied_path(user)), ("last_good", pbp.last_good_path(user))):
        data = snap.get(key)
        try:
            if data is None:
                if os.path.exists(path):
                    os.remove(path)
            else:
                pbp._atomic_write(path, data)
        except OSError as e:
            ok = False
            logger.critical(f"{TAG} 이전 {key} 되돌리기 실패 | user={user} | {type(e).__name__}")
    return ok


def _valid_or_none(data: Optional[bytes]) -> Optional[dict]:
    if data is None:
        return None
    try:
        return pbp.validate(pbp._parse_bytes(data))
    except pbp.PullbackParamsError:
        return None


def diff(prev: Optional[dict], new: dict) -> Dict[str, list]:
    """바뀐 키 → [구, 신]. 이전 적용본이 없거나 깨졌으면 모든 키를 바뀐 것으로 본다(구 = None)."""
    out = {}
    for k in ALL_KEYS:
        old = None if prev is None else prev.get(k)
        if prev is None or old != new.get(k) or type(old) is not type(new.get(k)):
            out[k] = [old, new.get(k)]
    return out


def classify(changed: Dict[str, list], prev: Optional[dict]) -> str:
    if prev is None:
        return "reseed"
    if any(k in changed for k in MARKET_KEYS):
        return "restart"
    if any(k in changed for k in MA_KEYS):
        return "reseed"
    return "hot"


def _interval_min(interval: str) -> int:
    return int(str(interval).replace("minute", "") or 1)


def build_cfg(user: str, params: dict, interval_min: Optional[int] = None) -> dict:
    """생성자와 같은 방식으로 새 cfg (파생 키 golden_only·eff_max_splits, 거래 시간 형식 검사)."""
    from core.strategy_pullback import IncrementalPullbackStrategy
    im = _interval_min(params["interval"]) if interval_min is None else int(interval_min)
    return IncrementalPullbackStrategy(user, params["ticker"], params, im).cfg


def eff_of(params: Optional[dict]) -> int:
    if params is None:
        return 0
    return int(build_cfg("x", params)["eff_max_splits"])


def _map_params_error(e: Exception) -> Dict[str, Any]:
    field = getattr(e, "field", "")
    if field == "sha_mismatch":
        return _r("rejected", "sha_mismatch")
    if field == "ticker":
        return _r("rejected", "invalid_ticker")
    return _r("rejected", "saved_invalid")


def read_saved(user: str, sha: str):
    """(new dict, 바이트) 또는 거절 결과. 해시와 검증이 같은 바이트를 본다(apply_saved 와 같은 규칙 + LiveParams 시험)."""
    try:
        data = pbp._read_bytes(pbp.saved_path(user))
    except pbp.PullbackParamsError:
        return None, None, _r("rejected", "saved_invalid")
    if hashlib.sha256(data).hexdigest() != sha:
        return None, None, _r("rejected", "sha_mismatch")
    try:
        new = pbp.validate(pbp._parse_bytes(data))
        from config import MIN_CASH
        pbp.to_live_params(new, MIN_CASH)
    except pbp.PullbackParamsError as e:
        return None, None, _map_params_error(e)
    return new, data, None


# ================================================================ v2hist 마지막 저장 출처
def v2hist_path(user: str) -> str:
    return os.path.join(os.path.dirname(os.path.abspath(ss._db_path(user))), f"v2hist_{user}.db")


def last_source(user: str) -> Optional[str]:
    """v2hist 마지막 행 note 「source=…」의 값. 파일·표·행이 없거나 읽기 실패 → None(호출자가 거절)."""
    path = v2hist_path(user)
    if not os.path.exists(path):
        return None
    try:
        conn = sqlite3.connect(path, timeout=3)
        try:
            conn.execute("PRAGMA query_only=ON;")
            r = conn.execute("SELECT note FROM v2_settings_history WHERE user_id=? ORDER BY id DESC LIMIT 1",
                             (user,)).fetchone()
        finally:
            conn.close()
    except sqlite3.Error as e:
        logger.warning(f"{TAG} 저장 출처 읽기 실패 → 거절 | user={user} | {type(e).__name__}")
        return None
    note = r[0] if r else None
    if not isinstance(note, str) or not note.startswith("source="):
        return None
    return note[len("source="):]


# ================================================================ pullback_state 행 (종목·봉 단위 정리)
_ROW_CLEAR = ("buy_fail_bar_ts", "prev_golden", "last_bar_ts")


def row_holding(row: Optional[dict]) -> bool:
    if not row:
        return False
    return (int(row.get("entry_count") or 0) > 0 or float(row.get("qty") or 0.0) > 0
            or bool(row.get("pending_fill")))


def _load_row(user: str, mode: str) -> Optional[dict]:
    from services import pullback_state as ps
    return ps.load(user, mode)   # 읽기 실패는 PullbackStateReadError(호출자가 안전 쪽)


def rewrite_row_market(user: str, mode: str, ticker: str, interval: str):
    """회차 0·수량 0 인 행의 종목·봉 단위를 새 값으로, 쉼·골든·마지막 봉 칸은 비움(실현 손익 누적 유지).
    돌려주는 값: ("none"|"same"|"rewritten"|"holding", 되돌리기용 이전 칸 dict 또는 None)."""
    row = _load_row(user, mode)
    if row is None:
        return "none", None
    if (row.get("ticker"), row.get("interval")) == (ticker, interval):
        return "same", None
    if row_holding(row):
        return "holding", None
    prev = {k: row.get(k) for k in (*MARKET_KEYS, *_ROW_CLEAR)}
    from services.pullback_state import now_kst_iso
    conn = ss._connect_rw(user)
    try:
        cur = conn.execute(
            "UPDATE pullback_state SET ticker=?, interval=?, buy_fail_bar_ts=NULL, prev_golden=NULL, "
            "last_bar_ts=NULL, updated_at=? WHERE user_id=? AND mode=? AND entry_count=0 AND qty=0 "
            "AND pending_fill=0", (ticker, interval, now_kst_iso(), user, mode))
        conn.commit()
        if cur.rowcount != 1:
            return "holding", None
    finally:
        conn.close()
    logger.warning(f"{TAG} 분할 상태 행 종목·봉 단위 정리 | user={user} mode={mode} "
                   f"{prev['ticker']}/{prev['interval']} → {ticker}/{interval}")
    return "rewritten", prev


def restore_row_market(user: str, mode: str, prev: dict) -> bool:
    """정리한 행의 종목·봉 단위를 되돌린다. fix 1: 그사이 회차·수량·체결 대기가 생긴 행은 덮지 않는다(False)."""
    try:
        conn = ss._connect_rw(user)
        try:
            cur = conn.execute(
                "UPDATE pullback_state SET ticker=?, interval=?, buy_fail_bar_ts=?, prev_golden=?, "
                "last_bar_ts=? WHERE user_id=? AND mode=? AND entry_count=0 AND qty=0 AND pending_fill=0",
                (prev["ticker"], prev["interval"], prev["buy_fail_bar_ts"], prev["prev_golden"],
                 prev["last_bar_ts"], user, mode))
            conn.commit()
            done = cur.rowcount == 1
        finally:
            conn.close()
        if not done:
            logger.critical(f"{TAG} 분할 상태 행 되돌리기 안 함(진행 중이거나 행 없음) | user={user} mode={mode}")
        return done
    except Exception as e:
        logger.critical(f"{TAG} 분할 상태 행 되돌리기 실패 | user={user} | {type(e).__name__}: {e}")
        return False


def cleanup_stale_row(user: str, mode: str, ticker, interval) -> str:
    """EMA→PULLBACK 전환 직전(strategy_switch.execute_switch): 다른 종목·봉 단위의 옛 행 정리.
    진행 중(회차·수량 있음) 옛 행은 손대지 않는다(추측하지 않음 — 지금처럼 저장 막음, 계획 메모의 남은 일)."""
    if not ticker or not interval:
        return "none"
    state, _prev = rewrite_row_market(user, mode, ticker, interval)
    if state == "holding":
        logger.warning(f"{TAG} 전환 대상과 다른 종목·봉 단위의 진행 중 분할 상태 행 → 손대지 않음 | user={user} "
                       f"mode={mode} 대상={ticker}/{interval}")
    return state


# ================================================================ PARAMS 기록
def record_params(user: str, mode: str, prev: Optional[dict], new: dict, sha: str, changed: dict, apply: str,
                  request_id=None) -> bool:
    now = ss.kst_iso()
    note = json.dumps({"changed": changed, "apply": apply}, ensure_ascii=False, separators=(",", ":"))
    try:
        ss.insert_row(user, mode=mode, kind="PARAMS", from_strategy="PULLBACK", to_strategy="PULLBACK",
                      from_ticker=(prev or {}).get("ticker"), from_interval=(prev or {}).get("interval"),
                      to_ticker=new.get("ticker"), to_interval=new.get("interval"), params_sha256=sha,
                      state="DONE", request_id=request_id, note=note, requested_at=now, done_at=now)
        return True
    except Exception as e:
        logger.error(f"{TAG} 변경 기록(PARAMS) 실패(적용은 됨) | user={user} | {type(e).__name__}: {e}")
        return False


def _apply_label(changed: dict, holding: bool) -> str:
    return "immediate" if holding and any(k in changed for k in IMMEDIATE_KEYS) else "next_bar"


def _done(sha, changed, apply, recorded, **extra) -> Dict[str, Any]:
    d = {"applied_sha256": sha, "changed": changed, "apply": apply, "record": bool(recorded)}
    d.update(extra)
    return _r("done", "ok", d)


# ================================================================ 엔진 스레드 (core.engine_control APPLY_KIND)
def engine_holding(engine) -> bool:
    st = getattr(engine, "strategy", None)
    pos = getattr(engine, "position", None)
    return (bool(getattr(pos, "has_position", False)) or int(getattr(st, "entry_count", 0) or 0) > 0
            or getattr(engine, "_pending_split", None) is not None)


def engine_apply(engine, payload: dict) -> Dict[str, Any]:
    """엔진 스레드(봉 처리 사이): 해시·바뀐 키 재확인 → 새 cfg → (보유 중 늘림 거절) → apply_saved → cfg 교체 →
    _pullback_params_sha 갱신 → PARAMS 행. 반영은 다음 확정 봉부터."""
    user = engine.user_id
    mode = str(payload.get("mode") or "TEST")
    sha = payload.get("saved_sha256")
    st = getattr(engine, "strategy", None)
    if getattr(engine, "strategy_type", "") != "PULLBACK" or not isinstance(getattr(st, "cfg", None), dict):
        return _r("rejected", "apply_not_pullback")
    if not isinstance(sha, str) or not _SHA_RE.fullmatch(sha):
        return _r("rejected", "bad_request")
    new, _data, rej = read_saved(user, sha)
    if rej is not None:
        return rej
    prev = _valid_or_none(_read_or_none(pbp.applied_path(user)))
    changed = diff(prev, new)
    if classify(changed, prev) != "hot":
        return _r("rejected", "sha_mismatch")     # 감시 스레드가 본 뒤 적용본이 바뀜 — 다시 저장·적용
    try:
        new_cfg = build_cfg(user, new, getattr(st, "interval_min", None))
    except Exception:
        return _r("rejected", "saved_invalid")
    holding = engine_holding(engine)
    if holding and int(new_cfg["eff_max_splits"]) > int(st.cfg.get("eff_max_splits") or 0):
        return _r("rejected", "holding_splits_increase")
    try:
        res = pbp.apply_saved(user, sha)
    except pbp.PullbackParamsError as e:
        return _map_params_error(e)
    except OSError as e:
        logger.error(f"{TAG} 적용본 쓰기 실패 | user={user} | {type(e).__name__}")
        return _r("error", "apply_failed", {"why": "write"})
    st.cfg = new_cfg                                  # 1. cfg 교체(한 번에)
    engine._pullback_params_sha = res["sha"]          # 2. 교체 뒤 해시 갱신(분할 상태 저장 행에 새 해시)
    if hasattr(engine, "take_profit"):
        engine.take_profit = new["tp"] / 100          # 감사 기본값(전략 객체가 우선)
    if hasattr(engine, "stop_loss"):
        engine.stop_loss = new["sl"] / 100
    apply = _apply_label(changed, holding)
    recorded = record_params(user, mode, prev, new, res["sha"], changed, apply, payload.get("request_id"))
    logger.info(f"{TAG} 적용(엔진 안) | user={user} keys={sorted(changed)} apply={apply} sha={res['sha'][:12]}")
    return _done(res["sha"], changed, apply, recorded)


# ================================================================ 감시 스레드 요청 처리
def _holding(ctl, user: str, mode: str, ticker) -> bool:
    """보유 판정(조회 실패 = 보유 중): 지갑·미체결 매수·엔진 포지션(T12 flat_state) + pullback_state 행."""
    st = ss.flat_state(ctl, user, mode, "PULLBACK", ticker)
    if st is None or not st.get("flat"):
        return True
    try:
        return row_holding(_load_row(user, mode))
    except Exception:
        return True


def handle_apply(ctl, req) -> Dict[str, Any]:
    """신버전 「이 설정으로 동작」(지금 전략 PULLBACK) — payload {"saved_sha256"}."""
    g = ss._guard(ctl, req)
    if g is not None:
        if g.get("code") == "live_not_supported":     # fix 1: 적용 전용 문구(T12 문구는 전환·복귀를 말함)
            return _r("rejected", "apply_live_not_supported")
        return g
    user, mode, rid = req["user_id"], req["mode"], req.get("id")
    sha = (req.get("payload") or {}).get("saved_sha256")
    if not isinstance(sha, str) or not _SHA_RE.fullmatch(sha):
        return _r("rejected", "bad_request")
    row, rej = ss._reservation_or_result(user, mode)
    if rej is not None:
        return rej
    if row is not None:
        return _r("rejected", "already_reserved", {"reservation_id": row["id"], "kind": row["kind"]})
    if ss._active(user) != "PULLBACK" or ss._active_file(user) != "PULLBACK":
        return _r("rejected", "apply_not_pullback")
    if last_source(user) != "upbit":
        return _r("rejected", "source_not_upbit")
    new, data, rej = read_saved(user, sha)
    if rej is not None:
        return rej
    snap = files_snapshot(user)                       # 이전 적용본·사본 바이트(apply_saved 전에)
    prev = _valid_or_none(snap["applied"])
    changed = diff(prev, new)
    if not changed and snap["applied"] == data:
        return _done(sha, {}, "unchanged", False, unchanged=True)
    kind = classify(changed, prev)
    from core import engine_control as ec
    running = ctl.manager.get_running_mode(user)      # _guard 뒤라 None 또는 요청 mode

    if kind == "hot" and running is not None:
        engine = ec.running_engine(user)
        if engine is None:
            return _r("error", "engine_busy")
        r = ctl._through_engine(engine, ec.APPLY_KIND,
                                {"id": rid, "payload": {"saved_sha256": sha, "mode": mode, "request_id": rid}})
        return r

    prev_ticker = (prev or {}).get("ticker") or new["ticker"]
    eff_up = prev is not None and eff_of(new) > eff_of(prev)
    if kind == "restart" or eff_up:
        holding = _holding(ctl, user, mode, prev_ticker)
        if holding and kind == "restart":
            return _r("rejected", "holding_interval_change")
        if holding and eff_up:
            return _r("rejected", "holding_splits_increase")

    try:
        res = pbp.apply_saved(user, sha)
    except pbp.PullbackParamsError as e:
        return _map_params_error(e)
    except OSError as e:
        logger.error(f"{TAG} 적용본 쓰기 실패 | user={user} | {type(e).__name__}")
        return _r("error", "apply_failed", {"why": "write"})

    if running is None:
        # 엔진 멈춤: 적용본만(다음 기동이 읽음). 봉 단위 변경이면 행도 지금 정리(엔진이 없어 덮어쓸 쪽 없음).
        apply = "next_bar" if kind == "hot" else kind
        if kind == "restart":
            try:
                state, _p = rewrite_row_market(user, mode, new["ticker"], new["interval"])
            except Exception as e:
                logger.error(f"{TAG} 분할 상태 행 정리 실패 → 되돌림 | user={user} | {type(e).__name__}")
                state = "error"
            if state in ("holding", "error"):
                restore_files(user, snap)
                return _r("rejected", "holding_interval_change") if state == "holding" else \
                    _r("error", "apply_failed", {"why": "row"})
        recorded = record_params(user, mode, prev, new, res["sha"], changed, apply, rid)
        return _done(res["sha"], changed, apply, recorded, engine="stopped")

    # reseed·restart: 엔진 재시작(워밍업이 새 값으로). 행 정리는 옛 스레드가 끝난 뒤(시작 앞)에서만.
    box: Dict[str, Any] = {"prev_row": None}

    def before_start():
        if kind != "restart":
            return None
        try:
            state, prev_row = rewrite_row_market(user, mode, new["ticker"], new["interval"])
        except Exception as e:
            logger.error(f"{TAG} 분할 상태 행 다시 읽기 실패 → 시작 안 함 | user={user} | {type(e).__name__}")
            return _r("error", "apply_failed", {"why": "row_read"})
        if state == "holding":
            box["hook_holding"] = True
            return _r("rejected", "holding_interval_change")
        box["prev_row"] = prev_row
        return None

    r = ctl.restart_engine(user, mode, "PULLBACK", before_start=before_start)
    if r.get("status") == "done":
        recorded = record_params(user, mode, prev, new, res["sha"], changed, kind, rid)
        logger.info(f"{TAG} 적용(재시작) | user={user} keys={sorted(changed)} apply={kind}")
        return _done(res["sha"], changed, kind, recorded)
    if box.get("hook_holding"):
        return _hook_holding(ctl, user, mode, snap)
    return _rollback(ctl, user, mode, snap, box.get("prev_row"), r)


def _hook_holding(ctl, user, mode, snap) -> Dict[str, Any]:
    """fix 1: 정지 뒤 다시 읽은 행이 보유 중 = 보통 거절(재시작 실패 아님). 적용본 되돌림 + WARNING.
    운영자 CRITICAL 「재시작 실패」는 보내지 않는다. 엔진은 정지 단계에서 이미 멈췄으므로 이전 설정으로 다시 띄운다
    (보유분을 관리할 엔진이 없으면 안 되기 때문). 그 기동이 실패할 때만 진짜 재시작 실패로 CRITICAL."""
    files_ok = restore_files(user, snap)
    logger.warning(f"{TAG} 정지 뒤 분할 상태 행이 보유 중 → 봉 단위 변경 거절, 이전 설정으로 | user={user} "
                   f"mode={mode} files_ok={files_ok}")
    again = "건너뜀"
    running = ctl.manager.get_running_mode(user)
    if running is None or running == mode:
        rr = ctl.restart_engine(user, mode, "PULLBACK")
        again = f"{rr.get('status')}/{rr.get('code')}"
        if rr.get("status") != "done":
            logger.critical(f"{TAG} 보유 중 거절 뒤 이전 설정 기동 실패 | user={user} again={again}")
            try:
                ss._notify_operator("CRITICAL", APPLY_FAILED_TITLE,
                                    APPLY_FAILED_BODY.format(user=user, why="holding_restart", row_note="",
                                                             again=again),
                                    dedupe_key=f"pullback_apply_failed:{user}", dedupe_ttl=600)
            except Exception:
                pass
    return _r("rejected", "holding_interval_change", {"restarted": again})


def _rollback(ctl, user, mode, snap, prev_row, r) -> Dict[str, Any]:
    """재시작 실패: 이전 적용본·사본 바이트 + (바꿨으면) 행의 종목·봉 단위를 되돌리고 이전 설정으로 1회 다시 띄움 + 운영자 CRITICAL."""
    why = r.get("code") or "start_failed"
    files_ok = restore_files(user, snap)
    row_note = ""
    if prev_row is not None:
        row_ok = restore_row_market(user, mode, prev_row)
        row_note = " 분할 상태 행의 종목·봉 단위도 되돌렸고" if row_ok else " 분할 상태 행 되돌리기는 실패했고"
    again = "건너뜀"
    running = ctl.manager.get_running_mode(user)
    if running is None or running == mode:
        rr = ctl.restart_engine(user, mode, "PULLBACK")
        again = f"{rr.get('status')}/{rr.get('code')}"
    logger.critical(f"{TAG} 설정 적용 재시작 실패 → 이전 설정으로 | user={user} why={why} files_ok={files_ok} again={again}")
    try:
        ss._notify_operator("CRITICAL", APPLY_FAILED_TITLE,
                            APPLY_FAILED_BODY.format(user=user, why=why, row_note=row_note, again=again),
                            dedupe_key=f"pullback_apply_failed:{user}", dedupe_ttl=600)
    except Exception:
        pass
    if why in ("holding_interval_change",):
        return _r("rejected", why, {"restarted": again})
    return _r("error", "apply_failed", {"why": str(why)[:64], "restarted": again})


# ================================================================ 설치 (scripts/tradebot_boot._control_thread 가 1회)
_INSTALLED = {"done": False}


def install() -> None:
    from engine import control_requests as cr
    if _INSTALLED["done"]:
        return
    cr.register_handler("apply_params", handle_apply)
    _INSTALLED["done"] = True
    logger.info(f"{TAG} 설정 적용 처리 설치")
