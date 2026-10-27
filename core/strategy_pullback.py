"""
PULLBACK(눌림목 분할매수) 전략 — 2차 T3: 증분 지표 상태 + BACKFILL 링 버퍼.

- 지표는 봉 하나씩 증분으로만 갱신한다(전체 재계산 함수 없음 — CLAUDE.md 금지 사항).
  식은 원본 백테스터(docs/specs/MA60_200_GoldenCross_Pullback_Backtester_2610201820.html)
  computeSMA 186-195 · computeEMA 199-212 · computeSlope 218-227 과 같은 연산 순서다.
- 링 버퍼는 봉마다 「그 봉을 넣은 뒤」 상태(지표 스칼라 · SMA 합계 · 분할 판정 상태)를 담는다.
  SMA 창·ma200·slope 이력은 지표 객체의 긴 이력(최대 기간 + 링 용량)에서 되살린다.
- 분할 판정 상태(armed · prev_golden · 가상 회차)는 T4 전략 객체가 아래 훅을 가지면 담는다.
    replay_bar(bar, values)      — 주문 없이 판정 상태만 갱신
    export_split_state() -> dict
    restore_split_state(dict)
  훅이 없으면 그 자리는 None 이다.
- BACKFILL 재생(pullback_backfill)은 주문을 내지 않는다(Issue #9). 감사 행은 바뀐 봉만
  services.db.insert_buy_eval(is_backfill=True) 로 backfill_* 칸을 쓴다(새 스키마 없음).
"""
from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Optional
from zoneinfo import ZoneInfo

import pandas as pd

from config import RECONCILE_LOOKBACK_BARS
from core.time_utils import format_kst

logger = logging.getLogger(__name__)

_TAG = "[PULLBACK-BACKFILL]"
RING_CAPACITY = RECONCILE_LOOKBACK_BARS + 1  # 400 → 401 (계획 T3)
_KST = ZoneInfo("Asia/Seoul")


# ---------------------------------------------------------------- 이동평균 1개 (증분)
class _IncEMA:
    """첫 period 종가 단순평균으로 시드, 그 뒤 c*k + prev*(1-k) (원본 computeEMA 와 같은 순서)."""

    def __init__(self, period: int):
        self.period = int(period)
        self.k = 2 / (self.period + 1)
        self.count = 0
        self.seed_sum = 0.0
        self.value: Optional[float] = None

    def update(self, c: float) -> Optional[float]:
        self.count += 1
        if self.count < self.period:
            self.seed_sum += c
            return None
        if self.count == self.period:
            self.seed_sum += c
            self.value = self.seed_sum / self.period
            return self.value
        self.value = c * self.k + self.value * (1 - self.k)
        return self.value

    def export(self) -> tuple:
        return (self.count, self.seed_sum, self.value)

    def restore(self, st: tuple, _closes=None) -> None:
        self.count, self.seed_sum, self.value = st


class _IncSMA:
    """합계에 더한 뒤 period 전 종가를 뺀다(원본 computeSMA 와 같은 순서)."""

    def __init__(self, period: int):
        self.period = int(period)
        self.count = 0
        self.sum = 0.0
        self.window: deque = deque(maxlen=self.period)
        self.value: Optional[float] = None

    def update(self, c: float) -> Optional[float]:
        self.sum += c
        if self.count >= self.period:
            self.sum -= self.window[0]
        self.window.append(c)
        self.count += 1
        self.value = self.sum / self.period if self.count >= self.period else None
        return self.value

    def export(self) -> tuple:
        return (self.count, self.sum, self.value)

    def restore(self, st: tuple, closes: deque) -> None:
        self.count, self.sum, self.value = st
        need = min(self.count, self.period)
        self.window = deque(list(closes)[len(closes) - need:] if need else [], maxlen=self.period)


# ---------------------------------------------------------------- 지표 묶음
class PullbackIndicators:
    """maTrend(ma60p) · ma200(ma200p) · maPullback(pullbackP) · slope200(slopeLB) 증분 상태."""

    def __init__(self, ma60p: int, ma200p: int, pullbackP: int, slopeLB: int, maType: str,
                 *, history_extra: int = RING_CAPACITY):
        self.ma60p, self.ma200p, self.pullbackP = int(ma60p), int(ma200p), int(pullbackP)
        self.slopeLB = int(slopeLB)
        self.maType = str(maType).lower()
        cls = _IncSMA if self.maType == "sma" else _IncEMA
        self._trend = cls(self.ma60p)
        self._ma200 = cls(self.ma200p)
        self._pull = cls(self.pullbackP)
        # 긴 이력: SMA 창 · ma200[-LB] · slope200[-LB] 를 링 버퍼 범위 안에서 되살리는 데 쓴다.
        self.history_len = max(self.ma60p, self.ma200p, self.pullbackP, self.slopeLB + 1) + int(history_extra)
        self._h_close: deque = deque(maxlen=self.history_len)
        self._h_ma200: deque = deque(maxlen=self.history_len)
        self._h_slope: deque = deque(maxlen=self.history_len)
        self.n = 0              # 넣은 봉 수
        self.update_count = 0   # 갱신 횟수 계측(되살려도 줄지 않음)
        self.last_values: dict = self._values(None, None, None, None, None)
        self.state_polluted = False

    @staticmethod
    def _values(t, m, p, s, s_lb) -> dict:
        return {"maTrend": t, "ma200": m, "maPullback": p, "slope200": s, "slope200_lb": s_lb}

    def update(self, close: float) -> dict:
        c = float(close)
        t = self._trend.update(c)
        m = self._ma200.update(c)
        p = self._pull.update(c)
        self._h_close.append(c)
        self._h_ma200.append(m)
        lb = self.slopeLB
        s = None
        if len(self._h_ma200) >= lb + 1:
            prev = self._h_ma200[-(lb + 1)]
            if prev is not None and m is not None and prev != 0:
                s = (m - prev) / abs(prev) * 100
        self._h_slope.append(s)
        s_lb = self._h_slope[-(lb + 1)] if len(self._h_slope) >= lb + 1 else None
        self.n += 1
        self.update_count += 1
        self.last_values = self._values(t, m, p, s, s_lb)
        return dict(self.last_values)

    def export_state(self) -> dict:
        return {
            "n": self.n,
            "trend": self._trend.export(),
            "ma200": self._ma200.export(),
            "pull": self._pull.export(),
            "last_values": dict(self.last_values),
        }

    def check_restorable(self, st: dict) -> None:
        """되살릴 수 있는지 미리 본다. 안 되면 RingRestoreRejected (상태는 바뀌지 않음)."""
        drop = self.n - int(st["n"])
        need = min(int(st["n"]), max(self.ma60p, self.ma200p, self.pullbackP, self.slopeLB + 1))
        if drop < 0 or len(self._h_close) - drop < need:
            raise RingRestoreRejected(f"{_TAG} restore out of history (n={self.n} → {st['n']})")

    def restore_state(self, st: dict) -> None:
        self.check_restorable(st)
        drop = self.n - int(st["n"])
        for _ in range(drop):
            self._h_close.pop()
            self._h_ma200.pop()
            self._h_slope.pop()
        self._trend.restore(st["trend"], self._h_close)
        self._ma200.restore(st["ma200"], self._h_close)
        self._pull.restore(st["pull"], self._h_close)
        self.n = int(st["n"])
        self.last_values = dict(st["last_values"])


# ---------------------------------------------------------------- 링 버퍼
class RingRestoreRejected(ValueError):
    """되살리기 전 검사 실패 — 지표·링·전략 상태는 바뀌지 않았다."""


@dataclass(frozen=True)
class Snapshot:
    bar_ts: Any
    ind_state: dict
    split_state: Optional[dict]


def _export_split(strategy) -> Optional[dict]:
    fn = getattr(strategy, "export_split_state", None) if strategy is not None else None
    return fn() if callable(fn) else None


class PullbackSnapshotRing:
    """봉마다 그 봉을 넣은 뒤 상태를 담는다. 용량 = RECONCILE_LOOKBACK_BARS + 1."""

    def __init__(self, capacity: int = RING_CAPACITY):
        self.capacity = int(capacity)
        self._q: deque = deque(maxlen=self.capacity)

    def __len__(self) -> int:
        return len(self._q)

    def record(self, bar_ts, indicators: PullbackIndicators, strategy=None) -> None:
        self._q.append(Snapshot(bar_ts, indicators.export_state(), _export_split(strategy)))

    def snapshot_before(self, ts) -> Optional[Snapshot]:
        """ts 봉을 넣기 직전 상태 = ts 보다 앞선 마지막 기록. 링 맨 앞보다 이르면 None(링 밖)."""
        if not self._q or not (self._q[0].bar_ts < ts):
            return None
        found = None
        for snap in self._q:
            if snap.bar_ts < ts:
                found = snap
            else:
                break
        return found

    def restore(self, snapshot: Snapshot, indicators: PullbackIndicators, strategy=None) -> None:
        """링 뒤쪽 기록 수와 지표 n 이 맞는지 먼저 본다(어긋나면 RingRestoreRejected, 상태 불변)."""
        after = sum(1 for s in self._q if s.bar_ts > snapshot.bar_ts)
        last_n = self._q[-1].ind_state["n"] if self._q else None
        if last_n != indicators.n or indicators.n - int(snapshot.ind_state["n"]) != after:
            raise RingRestoreRejected(
                f"{_TAG} ring/n mismatch (n={indicators.n} ring_last_n={last_n} "
                f"snap_n={snapshot.ind_state['n']} after={after})")
        indicators.check_restorable(snapshot.ind_state)
        indicators.restore_state(snapshot.ind_state)
        fn = getattr(strategy, "restore_split_state", None) if strategy is not None else None
        if callable(fn) and snapshot.split_state is not None:
            fn(dict(snapshot.split_state))
        while self._q and self._q[-1].bar_ts > snapshot.bar_ts:
            self._q.pop()


# ---------------------------------------------------------------- 봉 넣기 · BACKFILL 재생
def bar_from_row(ts, row, source: str = "REST_BACKFILL"):
    from core.candle_buffer import Bar
    return Bar(ts=ts, open=row["Open"], high=row["High"], low=row["Low"], close=row["Close"],
               volume=row["Volume"], is_closed=True, is_confirmed=True, source=source)


def iter_valid_rows(df: pd.DataFrame, validator=None, tag: str = _TAG):
    """워밍업 시드와 BACKFILL 재생이 같은 규칙으로 봉을 거른다(F6 — 거래량 0 등 validator 거부 봉 제외).
    validator 가 None 이면 둘 다 거르지 않는다."""
    for ts, row in df.iterrows():
        if validator is not None:
            ok, why = validator.validate(row)
            if not ok:
                logger.warning(f"{tag} 봉 검증 실패 → 건너뜀 | ts={format_kst(ts)} | {why}")
                continue
        yield ts, row


def feed_confirmed_bar(engine, bar) -> dict:
    """확정 봉 1개를 지표 → (전략 훅 replay_bar) → 링 기록 순으로 넣는다. 주문은 내지 않는다.
    replay_bar 가 예외를 내도 링 기록은 남겨 지표 n 과 링이 어긋나지 않게 하고, 오염 표식 뒤 예외를 전파한다."""
    ind: PullbackIndicators = engine.pullback_indicators
    values = ind.update(bar.close)
    strategy = getattr(engine, "strategy", None)
    replay = getattr(strategy, "replay_bar", None) if strategy is not None else None
    try:
        if callable(replay):
            replay(bar, values)
    except Exception:
        ind.state_polluted = True
        raise
    finally:
        engine.pullback_ring.record(bar.ts, ind, strategy)
    return values


def _kst_iso(ts) -> str:
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        t = t.tz_localize("UTC")  # 엔진 봉 시각은 UTC (Issue #2: 시간대 명시)
    return t.tz_convert(_KST).isoformat()


def _default_audit(engine, bar, values: dict) -> None:
    """바뀐 봉의 감사 행 backfill_* 칸 UPDATE(없으면 missing_bar INSERT) — 기존 함수 그대로 사용."""
    from services.db import insert_buy_eval
    position = getattr(engine, "position", None)
    insert_buy_eval(
        user_id=engine.user_id,
        ticker=engine.ticker,
        interval_sec=getattr(engine, "interval_sec", 60),
        bar=getattr(engine, "bar_count", 0),
        price=float(bar.close),
        macd=0.0,
        signal=0.0,
        have_position=bool(getattr(position, "has_position", False)),
        overall_ok=False,
        failed_keys=["BACKFILL"],
        checks={"strategy": "PULLBACK", "reason": "PULLBACK_BACKFILL_REPLAY", "via_backfill": True, **values},
        notes="PULLBACK BACKFILL 재생 (주문 없음)",
        bar_time=_kst_iso(bar.ts),
        is_backfill=True,
    )


def pullback_backfill(engine, *, first_ts, series: pd.DataFrame, until_ts,
                      changed_ts: Iterable = (), audit_fn: Optional[Callable] = None,
                      validator=None) -> dict:
    """
    링 버퍼에서 first_ts 직전 상태를 되살리고, series 에서 그 뒤 봉부터 until_ts 까지
    (바뀐 봉·안 바뀐 봉 모두) 한 번씩 다시 넣는다. 주문은 내지 않는다.
    반환: {"restored": bool, "replayed": int, "audited": int, "reason": str}
      reason: "" 정상 | "out_of_ring" 링 밖 | "restore_rejected" 되살리기 전 실패(상태 불변, 오염 아님)
              | "restore_failed"·"replay_failed" 되살리는 중·재생 중 실패(state_polluted = True)
    """
    ind = engine.pullback_indicators
    ring = engine.pullback_ring
    strategy = getattr(engine, "strategy", None)
    audit = audit_fn or _default_audit
    changed = set(changed_ts)

    # 1) 되살리기 전 — 실패해도 상태는 바뀌지 않는다(오염 표식 없음).
    try:
        snap = ring.snapshot_before(first_ts)  # 시간대가 섞인 비교 예외(TypeError 등)도 여기서 잡는다
    except Exception as e:
        logger.error(f"{_TAG} 스냅샷 조회 실패(상태 불변) | {type(e).__name__}: {e}")
        return {"restored": False, "replayed": 0, "audited": 0, "reason": "restore_rejected"}
    if snap is None:
        logger.warning(f"{_TAG} out of ring | first_ts={format_kst(first_ts)} ring={len(ring)} → 지표 지금 값 유지")
        return {"restored": False, "replayed": 0, "audited": 0, "reason": "out_of_ring"}
    try:
        ring.restore(snap, ind, strategy)
    except RingRestoreRejected as e:
        logger.error(f"{_TAG} 되살리기 거부(상태 불변) | {e}")
        return {"restored": False, "replayed": 0, "audited": 0, "reason": "restore_rejected"}
    except Exception as e:
        ind.state_polluted = True
        logger.error(f"{_TAG} 되살리는 중 실패 = 지표 오염 상태 | {e}", exc_info=True)
        return {"restored": False, "replayed": 0, "audited": 0, "reason": "restore_failed"}

    # 2) 재생 — 실패하면 오염 표식.
    replayed = audited = 0
    try:
        rows = series[(series.index > snap.bar_ts) & (series.index <= until_ts)]
        for ts, row in iter_valid_rows(rows, validator):
            bar = bar_from_row(ts, row)
            values = feed_confirmed_bar(engine, bar)
            replayed += 1
            if ts in changed:
                try:
                    audit(engine, bar, values)
                    audited += 1
                except Exception as e:  # 감사 실패는 재생을 멈추지 않는다
                    logger.error(f"{_TAG} 감사 기록 실패 | ts={format_kst(ts)} | {e}")
    except Exception as e:
        ind.state_polluted = True
        logger.error(f"{_TAG} 재생 실패 = 지표 오염 상태 | {e}", exc_info=True)
        return {"restored": True, "replayed": replayed, "audited": audited, "reason": "replay_failed"}

    return {"restored": True, "replayed": replayed, "audited": audited, "reason": "",
            "from_ts": snap.bar_ts}
