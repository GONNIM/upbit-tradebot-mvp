"""
✅ WO-26 (2026-10-20): 약매수 포지션 표식 기록·복원.

- 기록(record_weak_entry): 봇 매수 체결 확정 3곳(시장가 · 지정가 체결 · 미체결 시장가 전환)에서
  apply_entry 뒤에 호출. position.take_profit_override 설정 + account_positions.meta.weak_entry 기록.
  orders.meta 의 weak_entry 는 주문 시점에 _execute_buy 가 meta 에 넣어 함께 저장된다.
- 복원(restore_weak_entry): boot_seed · wallet_sync 의 apply_entry 직후(restore_trailing_on_boot 보다 앞).
  meta.weak_entry.order_uuid 가 마지막 봇 BUY(orders.provider_uuid)와 같을 때만 override 복원,
  다르거나 대조할 수 없으면 표식을 지우고 WARNING 1줄.
- 삭제: PositionState.clear_weak_entry (청산 · 앱 추가 매수 · 복원 불일치).
"""
from typing import Any, Dict, Optional
import logging

logger = logging.getLogger(__name__)


WEAK_ENTRY_KEYS = ("weak_entry_filter_enabled", "weak_entry_window_hours", "weak_entry_mode", "weak_entry_tp_pct")
WEAK_ENTRY_MODE_LABELS = {"block": "매수 안 함", "reduce_tp": "익절 기준 축소"}


def load_weak_entry_settings(buy_saved: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """설정 파일 buy 블록 → 약매수 설정 4개 (없는 키는 config 기본값). 엔진(IncrementalEMAStrategy)과 같은 해석."""
    from core.strategy_incremental import IncrementalEMAStrategy
    return IncrementalEMAStrategy.weak_entry_settings(buy_saved)


def dump_weak_entry_settings(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    설정 페이지 값 → 저장할 buy 키 4개. 범위 보정: 시간 0~6(0.5 단위), 처리 방식 block/reduce_tp, 익절 0.3~1.5%(0.1% 단위).
    """
    cfg = load_weak_entry_settings(state)
    hours = min(6.0, max(0.0, round(float(cfg["weak_entry_window_hours"]) * 2) / 2))
    mode = cfg["weak_entry_mode"] if cfg["weak_entry_mode"] in WEAK_ENTRY_MODE_LABELS else "block"
    tp = min(0.015, max(0.003, round(float(cfg["weak_entry_tp_pct"]) * 1000) / 1000))
    return {
        "weak_entry_filter_enabled": bool(cfg["weak_entry_filter_enabled"]),
        "weak_entry_window_hours": hours,
        "weak_entry_mode": mode,
        "weak_entry_tp_pct": tp,
    }


def weak_entry_summary(cfg: Dict[str, Any]) -> str:
    """설정 요약 문구: "2시간 · 매수 안 함" / "2시간 · 익절 0.5%"."""
    h = f"{float(cfg['weak_entry_window_hours']):g}시간"
    if cfg.get("weak_entry_mode") == "reduce_tp":
        from core.filters.buy_filters import _pct_text
        return f"{h} · 익절 {_pct_text(cfg['weak_entry_tp_pct'])}"
    return f"{h} · 매수 안 함"


def weak_entry_display(failed_keys: Any, checks: Any) -> str:
    """
    감사 로그 BUY 평가 표 '약매수' 칸 문구. 차단 → "🐢 약매수 차단 (D/C 뒤 n분, 기준 h시간)",
    진입 → "🐢 약매수 진입 · 익절 x%", 해당 없음 → "".
    """
    from core.filters.buy_filters import WEAK_ENTRY_FILTER_REASON, weak_entry_note
    fk = failed_keys if isinstance(failed_keys, (list, tuple)) else []
    ck = checks if isinstance(checks, dict) else {}
    if WEAK_ENTRY_FILTER_REASON in fk:
        return "🐢 " + str(ck.get("filter_details") or "약매수 차단")
    we = ck.get("weak_entry")
    if isinstance(we, dict) and we.get("tp") is not None:
        return "🐢 " + weak_entry_note(we["tp"])
    return ""


def _user_id(position) -> Optional[str]:
    trader = getattr(position, "trader", None)
    return getattr(trader, "user_id", None) if trader is not None else None


def record_weak_entry(position, weak: Optional[Dict[str, Any]], order_uuid: Optional[str],
                      bar_time: Optional[str], user_id: Optional[str] = None,
                      ticker: Optional[str] = None) -> bool:
    """약매수 진입 확정 시 override 설정 + meta 기록. weak 가 없으면 아무것도 하지 않는다 (반환 False)."""
    if not weak or weak.get("tp") is None:
        return False
    rec = {
        "tp": float(weak["tp"]),
        "elapsed_min": weak.get("elapsed_min"),
        "window_h": weak.get("window_h"),
        "order_uuid": order_uuid,
        "bar_time": bar_time,
    }
    position.take_profit_override = rec["tp"]
    if isinstance(getattr(position, "metadata", None), dict):
        position.metadata["weak_entry"] = dict(rec)
    uid = user_id or _user_id(position)
    tk = ticker or getattr(position, "ticker", None)
    db_ok = False
    if uid and tk:
        from services.db import set_position_weak_entry
        db_ok = set_position_weak_entry(uid, tk, rec)
    logger.warning(
        f"🐢 [WEAK-ENTRY] recorded | ticker={tk} tp={rec['tp']:.4f} elapsed_min={rec['elapsed_min']} "
        f"window_h={rec['window_h']} order_uuid={order_uuid} bar_time={bar_time} db={db_ok}"
    )
    return True


def restore_weak_entry(position, source: str, user_id: Optional[str] = None,
                       ticker: Optional[str] = None) -> Optional[bool]:
    """
    재시작·지갑 동기화 복원. 반환: True = override 복원, False = 불일치로 삭제, None = 표식 없음/대조 불가 환경.
    """
    uid = user_id or _user_id(position)
    tk = ticker or getattr(position, "ticker", None)
    if not uid or not tk:
        return None
    from services.db import get_position_meta, get_last_open_buy_order
    meta = get_position_meta(uid, tk) or {}
    w = meta.get("weak_entry")
    if not w:
        return None
    last = get_last_open_buy_order(tk, uid) or {}
    last_uuid = last.get("provider_uuid")
    meta_uuid = w.get("order_uuid")
    if meta_uuid and last_uuid and meta_uuid == last_uuid and w.get("tp") is not None:
        position.take_profit_override = float(w["tp"])
        if isinstance(getattr(position, "metadata", None), dict):
            position.metadata["weak_entry"] = dict(w)
        logger.info(
            f"🐢 [WEAK-ENTRY] restored | source={source} ticker={tk} tp={float(w['tp']):.4f} order_uuid={meta_uuid}"
        )
        return True
    logger.warning(
        f"⚠️ [WEAK-ENTRY] 표식이 마지막 봇 BUY 와 다름 → 삭제 (일반 익절 기준) | source={source} ticker={tk} "
        f"meta_uuid={meta_uuid} last_buy_uuid={last_uuid}"
    )
    position.clear_weak_entry(reason=f"restore_mismatch:{source}")
    return False
