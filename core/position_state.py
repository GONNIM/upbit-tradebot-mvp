"""
실거래 포지션 상태 관리
Backtesting 라이브러리의 self.position과 완전히 분리
"""
from typing import Optional, TYPE_CHECKING
import logging

if TYPE_CHECKING:
    from core.trader import UpbitTrader

logger = logging.getLogger(__name__)


class PositionState:
    """
    실거래 포지션 상태
    - Backtesting 라이브러리와 무관
    - 실제 지갑 잔고 기반으로 관리

    ✅ Issue #10: Audit vs Execution Mismatch 수정
    - has_position을 내부 플래그가 아닌 실제 지갑/DB 잔고로 판단
    - sync_from_wallet() 메서드로 명시적 동기화
    """

    def __init__(self, trader: Optional["UpbitTrader"] = None, ticker: Optional[str] = None):
        """
        Args:
            trader: UpbitTrader 인스턴스 (실제 잔고 조회용)
            ticker: 거래 ticker (예: "KRW-ZRO")
        """
        self.trader = trader
        self.ticker = ticker

        # ✅ 내부 상태 (캐시용)
        self._has_position: bool = False           # 포지션 보유 여부 (캐시)
        self.qty: float = 0.0                     # 보유 수량
        self.avg_price: Optional[float] = None    # 평균 단가
        self.entry_bar: Optional[int] = None      # 진입 시점 bar index
        self.entry_ts = None                       # 진입 시점 타임스탬프
        self.pending_order: bool = False           # 주문 진행 중 여부
        self.last_action_ts = None                 # 마지막 액션 타임스탬프

        # 추가: Trailing Stop / Highest Price 추적용
        self.highest_price: Optional[float] = None
        self.trailing_armed: bool = False

        # ✅ 고정폭 Trailing Stop용 (활성화 시점 고정 금액)
        self.trailing_fixed_amount: Optional[float] = None
        self.trailing_activation_price: Optional[float] = None

        # ✅ Stale Position Check용 (진입 이후 최고가)
        self.highest_since_entry: Optional[float] = None

        # ✅ Issue #17: HTS 매수 감지용 메타데이터
        self.metadata: dict = {}  # {"hts_buy": True, "src": "manual", ...}

    @property
    def has_position(self) -> bool:
        """
        ✅ 포지션 보유 여부 (실제 잔고 기반)
        - trader가 설정되지 않았으면 내부 캐시 사용
        - trader가 있으면 실제 잔고 조회 (호출 시마다 최신 상태)

        주의: 매번 API/DB 호출하므로 성능 고려 필요
        대신 sync_from_wallet() 메서드 사용 권장
        """
        return self._has_position

    @has_position.setter
    def has_position(self, value: bool):
        """내부 캐시 설정 (open_position, close_position에서 사용)"""
        self._has_position = value

    def sync_from_wallet(self) -> bool:
        """
        ✅ 실제 지갑/DB 잔고로부터 포지션 상태 동기화
        ✅ Issue #17: metadata (hts_buy 플래그) 포함
        ✅ Policy P-1: TEST 모드는 지갑 조회 금지 (가상 거래만)

        Returns:
            bool: 동기화된 has_position 값
        """
        if self.trader is None or self.ticker is None:
            logger.warning("[POS-SYNC] trader 또는 ticker 미설정 → 동기화 스킵")
            return self._has_position

        # ✅ Policy P-1: TEST 모드는 지갑/실잔고를 보지 않는다 (가상 상태 유지)
        if getattr(self.trader, "test_mode", False):
            logger.debug(
                f"[POS-SYNC] TEST 모드 → 지갑 동기화 스킵 (가상 상태 유지) | ticker={self.ticker}"
            )
            return self._has_position

        try:
            # trader._coin_balance()는 test_mode에 따라 DB 또는 Upbit API 호출
            actual_balance = float(self.trader._coin_balance(self.ticker))
            actual_has_position = actual_balance >= 1e-6

            # ✅ 내부 캐시 업데이트
            old_state = self._has_position
            self._has_position = actual_has_position
            self.qty = actual_balance

            # ✅ [Fix 1] avg_price 복구 (HTS 매수 미인식 결함 근본 방지)
            # wallet 잔고는 있는데 avg_price 가 None/0 이면 다음 매도 필터가 pnl=None
            # 조기 return 으로 SL/TP/TS/Stale 전량 무력화됨 (2026-07-24 사건).
            # 우선순위: 1) DB 캐시(Reconciler HTS-DETECT 반영) → 2) Upbit avg_buy_price 직접 조회.
            if actual_has_position and (self.avg_price is None or self.avg_price <= 0):
                recovered_price = None
                recovery_src = None

                # 1순위: DB 캐시 (account_positions.entry_price, Reconciler 업데이트)
                try:
                    if hasattr(self.trader, 'user_id'):
                        from services.db import get_position_entry_price
                        cached = get_position_entry_price(self.trader.user_id, self.ticker)
                        if cached is not None and cached > 0:
                            recovered_price = float(cached)
                            recovery_src = "db_cache"
                except Exception as _e:
                    logger.debug(f"[POS-SYNC] DB 캐시 조회 실패: {_e}")

                # 2순위: Upbit API 직접 조회 (LIVE 모드만, DB 캐시 미반영 시 즉시 실측)
                if recovered_price is None and not getattr(self.trader, "test_mode", True):
                    try:
                        symbol = self.ticker.split("-")[-1].strip().upper() if self.ticker else self.ticker
                        for b in (self.trader.upbit.get_balances() or []):
                            if str(b.get("currency", "")).upper() == symbol:
                                api_avg = float(b.get("avg_buy_price") or 0.0)
                                if api_avg > 0:
                                    recovered_price = api_avg
                                    recovery_src = "upbit_api"
                                break
                    except Exception as _e:
                        logger.warning(f"[POS-SYNC] Upbit avg_buy_price 조회 실패: {_e}")

                if recovered_price is not None:
                    self.avg_price = recovered_price
                    logger.warning(
                        f"✅ [POS-SYNC] avg_price 복구 성공 | source={recovery_src} | "
                        f"avg_price={recovered_price:.6f} | qty={actual_balance:.6f} | ticker={self.ticker}"
                    )
                else:
                    # 복구 실패: has_position=True + avg_price=None invariant 위반 상태
                    # (Fix 2 의 SELL 스킵 로직이 이를 감지)
                    logger.error(
                        f"❌ [POS-SYNC] avg_price 복구 실패 (DB 캐시 부재 + Upbit API 실패) | "
                        f"has_position=True + avg_price=None invariant 위반 상태. "
                        f"SELL 필터 전량 스킵 위험 → Fix 2 로직이 방어. | ticker={self.ticker}"
                    )

            # ✅ Issue #17: metadata 동기화 (hts_buy 플래그)
            if hasattr(self.trader, 'user_id'):
                from services.db import get_position_meta
                self.metadata = get_position_meta(self.trader.user_id, self.ticker)
                logger.debug(
                    f"[POS-SYNC] metadata 로드 완료 | ticker={self.ticker} | meta={self.metadata}"
                )

            if old_state != actual_has_position:
                logger.warning(
                    f"🔄 [POS-SYNC] 포지션 상태 변경 감지 | "
                    f"old={old_state} → new={actual_has_position} | "
                    f"qty={actual_balance:.6f} | ticker={self.ticker}"
                )
            else:
                logger.debug(
                    f"[POS-SYNC] 상태 일치 | has_pos={actual_has_position} | "
                    f"qty={actual_balance:.6f} | ticker={self.ticker}"
                )

            return self._has_position

        except Exception as e:
            logger.error(f"[POS-SYNC] 동기화 실패: {e} → 기존 상태 유지")
            return self._has_position

    def apply_entry(
        self,
        qty: float,
        avg_price: float,
        entry_bar: int,
        entry_ts,
        source: str,
        highest_since_entry: Optional[float] = None,
    ) -> None:
        """
        ✅ SP-PI-1: 통합 진입 API — 모든 P1/P2/P3/HTS 경로가 반드시 이 API 호출.
        entry_ts 는 필수 (None 이면 예외) — Stale filter 결함 재발 물리적 차단.

        Args:
            qty: 보유 수량
            avg_price: 평균 매수가
            entry_bar: 진입 시점 bar_count
            entry_ts: 진입 시점 timezone-aware datetime (필수)
            source: 진입 경로 라벨 — "bot_market" / "bot_limit_fill" /
                    "wallet_sync" / "boot_seed" / "hts_detect"
            highest_since_entry: Stale Check 초기값 (None 이면 avg_price)
        """
        if entry_ts is None:
            raise ValueError(f"entry_ts is required (source={source})")

        self.has_position = True
        self.qty = qty
        self.avg_price = avg_price
        self.entry_bar = entry_bar
        self.entry_ts = entry_ts
        self.last_action_ts = entry_ts
        self.pending_order = False

        # Trailing Stop 초기화
        self.highest_price = avg_price
        self.trailing_armed = False
        self.trailing_fixed_amount = None
        self.trailing_activation_price = None

        # ✅ Stale Position Check 초기화
        self.highest_since_entry = (
            highest_since_entry if highest_since_entry is not None else avg_price
        )

        ts_iso = entry_ts.isoformat() if hasattr(entry_ts, "isoformat") else str(entry_ts)
        logger.info(
            f"✅ [POSITION-APPLY] source={source} qty={qty:.6f} "
            f"entry={avg_price:.2f} bar={entry_bar} ts={ts_iso}"
        )

    def open_position(self, qty: float, price: float, bar_idx: int, ts):
        """
        봇 마켓 매수 완료 (기존 시그니처 유지, apply_entry 위임).

        Args:
            qty: 매수 수량
            price: 매수 단가
            bar_idx: 진입 bar index
            ts: 진입 타임스탬프
        """
        self.apply_entry(
            qty=qty,
            avg_price=price,
            entry_bar=bar_idx,
            entry_ts=ts,
            source="bot_market",
        )

    def close_position(self, ts):
        """
        매도 완료 (포지션 청산)

        Args:
            ts: 청산 타임스탬프
        """
        logger.info(
            f"✅ Position CLOSE | qty={self.qty:.6f} entry={self.avg_price:.2f}"
        )

        self.has_position = False
        self.qty = 0.0
        self.avg_price = None
        self.entry_bar = None
        self.entry_ts = None
        self.last_action_ts = ts
        self.pending_order = False

        # Trailing Stop 초기화
        self.highest_price = None
        self.trailing_armed = False
        self.trailing_fixed_amount = None
        self.trailing_activation_price = None

        # ✅ Stale Position Check 초기화
        self.highest_since_entry = None

    def set_pending(self, pending: bool):
        """
        주문 진행 중 플래그 설정

        Args:
            pending: True면 주문 진행 중, False면 완료/취소
        """
        self.pending_order = pending
        if pending:
            logger.debug("⏳ Order pending...")
        else:
            logger.debug("✅ Order completed/cancelled")

    def update_highest_price(self, current_price: float):
        """
        Trailing Stop용 최고가 갱신

        ✅ 변경: trailing_armed == True일 때만 갱신

        Args:
            current_price: 현재 가격
        """
        if not self.has_position:
            return

        # ✅ trailing_armed 상태일 때만 최고가 추적
        if not self.trailing_armed:
            return

        if self.highest_price is None or current_price > self.highest_price:
            self.highest_price = current_price

    def arm_trailing_stop(self, threshold_pct: float, current_price: float) -> bool:
        """
        Trailing Stop 발동 조건 체크 (수익 기반)

        ✅ 변경: 수익 금액 대비 하락률 계산
        profit_drop_pct = (최고가 - 현재가) / (최고가 - 진입가)

        Args:
            threshold_pct: 수익 손실률 임계값 (예: 0.10 = 10%)
            current_price: 현재 가격

        Returns:
            bool: Trailing Stop 발동 여부
        """
        # trailing_armed 상태 체크
        if not self.trailing_armed:
            return False

        if not self.has_position or self.highest_price is None or self.avg_price is None:
            return False

        # ✅ 수익 기반 하락률 계산
        max_profit = self.highest_price - self.avg_price  # 최대 수익

        # 수익이 0 이하면 Trailing Stop 미작동 (방어 로직)
        if max_profit <= 0:
            return False

        profit_drop = self.highest_price - current_price  # 수익 손실 금액
        profit_drop_pct = profit_drop / max_profit  # 수익 손실률

        if profit_drop_pct >= threshold_pct:
            logger.warning(
                f"🚨 Trailing Stop TRIGGERED (Profit-based) | "
                f"entry={self.avg_price:.2f} highest={self.highest_price:.2f} curr={current_price:.2f} | "
                f"max_profit={max_profit:.2f} profit_drop={profit_drop:.2f} ({profit_drop_pct:.2%}) "
                f"threshold={threshold_pct:.2%}"
            )
            return True

        return False

    def activate_trailing_stop(self, current_price: float):
        """
        ✅ NEW: Trailing Stop 활성화 (Take Profit 도달 시 호출)

        Args:
            current_price: 현재 가격 (최고가 초기값으로 사용)
        """
        if not self.has_position:
            return

        self.trailing_armed = True
        self.highest_price = current_price  # 현재가를 최고가 초기값으로

        logger.info(
            f"🔓 Trailing Stop ACTIVATED | "
            f"entry=₩{self.avg_price:,.0f} initial_highest=₩{current_price:,.0f}"
        )

    def get_pnl_pct(self, current_price: float) -> Optional[float]:
        """
        현재 손익률 계산

        Args:
            current_price: 현재 가격

        Returns:
            float or None: 손익률 (예: 0.05 = 5%)
        """
        if not self.has_position or self.avg_price is None:
            return None

        return (current_price - self.avg_price) / self.avg_price

    def get_bars_held(self, current_bar: int) -> int:
        """
        보유 기간 (bar 수)

        Args:
            current_bar: 현재 bar index

        Returns:
            int: 보유한 bar 수
        """
        if not self.has_position or self.entry_bar is None:
            return 0

        return current_bar - self.entry_bar

    def update_highest_since_entry(self, current_price: float):
        """
        진입 이후 최고가 갱신 (Stale Position Check용)

        Args:
            current_price: 현재 가격
        """
        if not self.has_position:
            return

        if self.highest_since_entry is None or current_price > self.highest_since_entry:
            self.highest_since_entry = current_price

    def get_max_gain_from_entry(self) -> Optional[float]:
        """
        진입가 대비 최고 수익률 계산

        Returns:
            float or None: 최고 수익률 (예: 0.015 = 1.5%)
        """
        if not self.has_position or self.avg_price is None or self.highest_since_entry is None:
            return None

        return (self.highest_since_entry - self.avg_price) / self.avg_price

    def __repr__(self):
        return (
            f"PositionState(has_pos={self.has_position}, qty={self.qty:.6f}, "
            f"avg={self.avg_price}, pending={self.pending_order})"
        )
