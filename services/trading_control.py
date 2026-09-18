from services.db import fetch_logs, insert_log, fetch_latest_log_signal, fetch_latest_log_signal_ema, fetch_latest_sell_eval, fetch_latest_buy_eval
from datetime import datetime
from typing import Optional
from core.trader import UpbitTrader
from engine.reconciler_singleton import get_reconciler
import logging

logger = logging.getLogger(__name__)


# ============================================================
# WO-8 (2026-09-12): 강제 매수 지정가 이식 헬퍼
# 정상 크로스 매수 경로(core/strategy_engine.py:1080-1102)의 판정식·조건 조회를
# 글자 그대로 재사용한다. dashboard 안내 문구도 이 헬퍼로 조회한다.
# ============================================================
def _load_force_buy_conditions(user_id: str, strategy_type: Optional[str]) -> dict:
    """
    강제 매수용 buy_sell_conditions 로드. strategy_type이 None이면 빈 dict.
    engine.live_loop._load_trade_conditions와 동일 로직을 재사용한다.
    """
    if not strategy_type:
        return {}
    try:
        from engine.live_loop import _load_trade_conditions
        return _load_trade_conditions(user_id, strategy_type) or {}
    except Exception as e:
        logger.warning(f"[FORCE-BUY] conditions 로드 실패: {e}")
        return {}


def is_force_buy_fixed_price_active(user_id: str, strategy_type: Optional[str]) -> tuple[bool, int]:
    """
    강제 매수 시 지정가가 적용될지 판단 (대시보드 안내 문구용).
    Returns: (활성 여부, 대기 봉 수)
    """
    conds = _load_force_buy_conditions(user_id, strategy_type)
    buy = (conds.get("buy") or {})
    enabled = bool(buy.get("fixed_price_buy_enabled", False))
    wait_bars = int(buy.get("fixed_price_buy_wait_bars", 3) or 3)
    wait_bars = max(1, min(5, wait_bars))
    return enabled, wait_bars


def get_current_price_from_upbit(ticker: str) -> float | None:
    """
    Upbit API로 실시간 현재가 조회
    - 가장 안전하고 정확한 방법
    - 로그 파싱 실패 시 대체용
    """
    try:
        import pyupbit
        current = pyupbit.get_current_price(ticker)
        if current and current > 0:
            logger.info(f"[PRICE] Upbit API 조회 성공: {ticker} = {current:,.2f}")
            return float(current)
        logger.warning(f"[PRICE] Upbit API 응답 이상: {ticker} = {current}")
    except Exception as e:
        logger.warning(f"[PRICE] Upbit API 조회 실패: {e}")
    return None


def get_last_price_from_logs(user_id: str) -> float:
    """
    로그 테이블에서 가장 최근 가격을 추출 (price=... 포함된 로그 메시지에서 추출)
    예시 로그 메시지: '2025-06-30 18:00:00 | price=225.3 | cross=Neutral | macd=...'
    """
    logs = fetch_logs(user_id, limit=30)
    for log in logs:
        msg = log[2]
        if "price=" in msg:
            try:
                # 'price=' 다음 숫자만 추출
                price_part = msg.split("price=")[1].split("|")[0].strip()
                return float(price_part.replace(",", ""))
            except Exception:
                continue
    return 0.0 # fallback


def force_liquidate(user_id: str, trader: UpbitTrader, ticker: str, interval_sec: int = 60) -> str:
    """
    보유 코인을 강제청산 (시장가 매도).
    - TEST: 즉시 체결
    - LIVE: 주문만 보내고, 실제 체결/수량/평단은 Reconciler가 orders 테이블에 반영
    """
    qty = trader._coin_balance(ticker)
    if qty <= 0:
        msg = f"⚠️ 강제청산 실패: 보유 코인이 없습니다. (ticker={ticker})"
        insert_log(user_id, "INFO", msg)
        return msg

    # ✅ 가격 조회 우선순위:
    # 1) MACD 로그 → 2) EMA 로그 → 3) 일반 로그 파싱 → 4) Upbit API 실시간 조회
    price = None

    # 1. MACD 로그 시도
    log_summary = fetch_latest_log_signal(user_id, ticker)
    if log_summary:
        try:
            price = float(log_summary.get("price"))
            logger.info(f"[PRICE] MACD 로그에서 조회: {price:,.2f}")
        except (TypeError, ValueError):
            pass

    # 2. EMA 로그 시도
    if price is None or price <= 0:
        log_summary_ema = fetch_latest_log_signal_ema(user_id, ticker)
        if log_summary_ema:
            try:
                price = float(log_summary_ema.get("price"))
                logger.info(f"[PRICE] EMA 로그에서 조회: {price:,.2f}")
            except (TypeError, ValueError):
                pass

    # 3. 일반 로그 파싱 시도
    if price is None or price <= 0:
        price = get_last_price_from_logs(user_id)
        if price > 0:
            logger.info(f"[PRICE] 일반 로그 파싱에서 조회: {price:,.2f}")

    # 4. Upbit API 실시간 조회 (최후의 수단)
    if price is None or price <= 0:
        price = get_current_price_from_upbit(ticker)

    # 모든 방법 실패
    if price is None or price <= 0:
        msg = f"❌ 강제청산 실패: 모든 가격 조회 실패 (MACD 로그, EMA 로그, 일반 로그, Upbit API 모두 실패)"
        insert_log(user_id, "ERROR", msg)
        return msg

    ts = datetime.now()
    meta = {
        "interval": interval_sec,  # ✅ interval_sec 전달
        "reason": "force_liquidate",
        "src": "manual",
        "price_ref": price,
        "bar_time": None,  # ✅ 강제 청산은 봉 시각 없음
    }

    result = trader.sell_market(qty, ticker, price, ts=ts, meta=meta)
    if not result:
        reason = getattr(trader, "last_sell_error", None)
        if reason:
            msg = f"❌ 강제청산 실패: {reason}"
        else:
            msg = "❌ 강제청산 실패: 거래 처리 중 오류 발생 (사유 불명 — 로그 확인 필요)"
        insert_log(user_id, "ERROR", msg)
        return msg

    if trader.test_mode:
        insert_log(
            user_id,
            "SELL",
            f"🚨 [TEST] 강제청산 실행됨: {result['qty']:.6f} {ticker} @ {result['price']:,f} KRW",
        )
        return f"[TEST] {ticker} 강제청산 완료: {result['qty']:.6f} @ {result['price']:,f}"

    uuid = result.get("uuid")
    if not uuid:
        msg = (
            f"❌ [LIVE] 강제청산 요청 실패: Upbit 응답에 uuid가 없습니다. "
            f"(qty≈{qty:.6f}, raw={result.get('raw')})"
        )
        insert_log(user_id, "ERROR", msg)
        return msg
    
    msg = (
        f"🚨 [LIVE] 강제청산 요청 전송: {ticker} 시장가, "
        f"예상가≈{price:,.2f} KRW, 수량≈{qty:.6f} (uuid={uuid})"
    )
    insert_log(user_id, "SELL", msg)

    try:
        get_reconciler().enqueue(uuid, user_id=user_id, ticker=ticker, side="SELL", meta=meta)
    except Exception as e:
        insert_log(user_id, "ERROR", f"⚠️ 강제청산 reconciler enqueue 실패: {e}")

    return f"[LIVE] {ticker} 강제청산 요청 완료 (uuid={uuid})"


def force_buy_in(
    user_id: str,
    trader: UpbitTrader,
    ticker: str,
    interval_sec: int = 60,
    strategy_type: Optional[str] = None,
) -> str:
    """
    강제매수. 정상 크로스 매수 경로의 지정가 정책(fixed_price_buy)에 순응한다.

    - TEST: 즉시 체결 (buy_limit 내부에서 buy_market으로 자동 폴백)
    - LIVE:
        · fixed_price_buy_enabled=True → trader.buy_limit() (WO-8 이식)
        · 그 외 → trader.buy_market() (기존 동작)
    - 실제 주문금액은 UpbitTrader.risk_pct * 현재 KRW 잔고
    - strategy_type: buy_sell_conditions 로드용. None이면 시장가 폴백.
    """
    krw = trader._krw_balance()
    if krw <= 0:
        msg = "⚠️ 강제매수 실패: 보유 KRW가 없습니다."
        insert_log(user_id, "INFO", msg)
        return msg

    # ✅ 가격 조회 우선순위:
    # 1) MACD 로그 → 2) EMA 로그 → 3) 일반 로그 파싱 → 4) Upbit API 실시간 조회
    price = None

    # 1. MACD 로그 시도
    log_summary = fetch_latest_log_signal(user_id, ticker)
    if log_summary:
        try:
            price = float(log_summary.get("price"))
            logger.info(f"[PRICE] MACD 로그에서 조회: {price:,.2f}")
        except (TypeError, ValueError):
            pass

    # 2. EMA 로그 시도
    if price is None or price <= 0:
        log_summary_ema = fetch_latest_log_signal_ema(user_id, ticker)
        if log_summary_ema:
            try:
                price = float(log_summary_ema.get("price"))
                logger.info(f"[PRICE] EMA 로그에서 조회: {price:,.2f}")
            except (TypeError, ValueError):
                pass

    # 3. 일반 로그 파싱 시도
    if price is None or price <= 0:
        price = get_last_price_from_logs(user_id)
        if price > 0:
            logger.info(f"[PRICE] 일반 로그 파싱에서 조회: {price:,.2f}")

    # 4. Upbit API 실시간 조회 (최후의 수단)
    if price is None or price <= 0:
        price = get_current_price_from_upbit(ticker)

    # 모든 방법 실패
    if price is None or price <= 0:
        msg = f"❌ 강제매수 실패: 모든 가격 조회 실패 (MACD 로그, EMA 로그, 일반 로그, Upbit API 모두 실패)"
        insert_log(user_id, "ERROR", msg)
        return msg

    # ✅ 최신 bar 조회 및 시간 기반 보정 (엔진 미실행 시 대비)
    current_bar = None
    last_eval_time = None

    # 1. SELL 평가에서 bar 조회 (포지션 있을 때 우선)
    sell_eval = fetch_latest_sell_eval(user_id, ticker)
    if sell_eval and sell_eval.get("bar") is not None:
        current_bar = int(sell_eval.get("bar"))
        last_eval_time = sell_eval.get("timestamp")
        logger.info(f"[BAR] SELL 평가에서 조회: bar={current_bar}, timestamp={last_eval_time}")
    else:
        # 2. BUY 평가에서 bar 조회 (포지션 없을 때)
        buy_eval = fetch_latest_buy_eval(user_id, ticker)
        if buy_eval and buy_eval.get("bar") is not None:
            current_bar = int(buy_eval.get("bar"))
            last_eval_time = buy_eval.get("timestamp")
            logger.info(f"[BAR] BUY 평가에서 조회: bar={current_bar}, timestamp={last_eval_time}")

    # 3. 시간 차이로 bar 보정 (엔진이 꺼져있어도 정확한 bar 계산)
    if current_bar is not None and last_eval_time:
        try:
            from dateutil import parser
            last_time = parser.parse(last_eval_time)
            now = datetime.now(last_time.tzinfo)  # 같은 timezone 사용
            time_diff_sec = (now - last_time).total_seconds()
            bars_elapsed = int(time_diff_sec / interval_sec)

            if bars_elapsed > 0:
                current_bar += bars_elapsed
                logger.info(f"[BAR] 시간 보정: +{bars_elapsed}봉 ({time_diff_sec:.0f}초 경과) → bar={current_bar}")
        except Exception as e:
            logger.warning(f"[BAR] 시간 보정 실패: {e}")

    ts = datetime.now()
    meta = {
        "interval": interval_sec,  # ✅ interval_sec 전달
        "reason": "force_buy",
        "src": "manual",
        "price_ref": price,
        "bar_time": None,  # ✅ 강제 매수는 봉 시각 없음
        "bar": current_bar,  # ✅ bars_held 추적용
    }

    # ✅ WO-8 (2026-09-12): 정상 크로스 경로(strategy_engine.py:1080-1102) 판정식 글자 그대로 재사용
    _conds = _load_force_buy_conditions(user_id, strategy_type)
    _buy_cond = (_conds.get("buy") or {})
    fixed_price_mode = (
        (not trader.test_mode)
        and bool(_buy_cond.get("fixed_price_buy_enabled", False))
    )

    if fixed_price_mode:
        meta["fixed_price_buy"] = True
        wait_bars = int(_buy_cond.get("fixed_price_buy_wait_bars", 3) or 3)
        wait_bars = max(1, min(5, wait_bars))
        effective_interval_sec = interval_sec * wait_bars
        logger.info(
            f"🎯 [FIXED-PRICE][FORCE] 고정가 강제 매수 진입 | "
            f"price={price:.2f} ticker={ticker} "
            f"wait_bars={wait_bars} effective_timeout≈{effective_interval_sec-5}s"
        )
        # ✅ WO-8b 원자화 (2026-09-18): 발주-등록 경합 봉쇄.
        # buy_limit + _pending_buy_uuid 등록을 engine._execution_lock 아래에서 원자적으로 수행.
        # reconciler 순회의 fill callback 은 이 락 획득까지 대기 → uuid 매칭 성공 보장.
        try:
            from core.strategy_engine import execute_force_buy_limit_atomic
            result = execute_force_buy_limit_atomic(
                user_id=user_id, ticker=ticker, trader=trader,
                price=price, ts=ts, meta=meta,
                interval_sec=effective_interval_sec, wait_bars=wait_bars,
            )
        except Exception as e:
            logger.warning(f"[FORCE-BUY-ATOMIC] 원자화 헬퍼 실패 → 폴백 buy_limit: {e}")
            result = trader.buy_limit(
                price, ticker,
                ts=ts, meta=meta,
                interval_sec=effective_interval_sec,
            )
    else:
        result = trader.buy_market(price, ticker, ts=ts, meta=meta)
    if not result:
        reason = getattr(trader, "last_buy_error", None)
        if reason:
            msg = f"❌ 강제매수 실패: {reason}"
        else:
            msg = "❌ 강제매수 실패: 주문 생성 실패 (사유 불명 — 로그 확인 필요)"
        insert_log(user_id, "ERROR", msg)
        return msg

    used_krw = result.get("used_krw")
    # 🔹 방어 로직: used_krw가 없으면 현재 잔고 * risk_pct로 추정
    if used_krw is None:
        try:
            used_krw = trader._krw_balance() * trader.risk_pct
        except Exception:
            used_krw = 0.0

    if trader.test_mode:
        insert_log(
            user_id,
            "BUY",
            f"🚨 [TEST] 강제매수 실행됨: {result['qty']:.6f} {ticker} @ {result['price']:,f} KRW "
            f"(사용 KRW ≈ {used_krw:,.0f})",
        )
        return f"[TEST] {ticker} 강제매수 완료: {result['qty']:.6f} @ {result['price']:,f}"

    uuid = result.get("uuid")
    if not uuid:
        msg = (
            f"❌ [LIVE] 강제매수 요청 실패: Upbit 응답에 uuid가 없습니다. "
            f"(사용 KRW ≈ {used_krw:,.0f}, raw={result.get('raw')})"
        )
        insert_log(user_id, "ERROR", msg)
        return msg

    insert_log(
        user_id,
        "BUY",
        f"🚨 [LIVE] 강제매수 요청 전송: {ticker} 시장가, 예상가≈{price:,.2f} KRW "
        f"(사용 KRW ≈ {used_krw:,.0f}, uuid={uuid})",
    )

    try:
        get_reconciler().enqueue(uuid, user_id=user_id, ticker=ticker, side="BUY", meta=meta)
    except Exception as e:
        insert_log(user_id, "ERROR", f"⚠️ 강제매수 reconciler enqueue 실패: {e}")

    return f"[LIVE] {ticker} 강제매수 요청 완료 (uuid={uuid})"
