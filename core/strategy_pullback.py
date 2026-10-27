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
- 2차 T4: IncrementalPullbackStrategy — 원본 simulate() 296-363 평가 순서. 위 세 훅을 채운다.
  실시간 확정 봉은 on_bar(지표·판정·링 기록이 feed_confirmed_bar 와 같은 _feed_bar 경로),
  워밍업·BACKFILL 재생은 replay_bar(주문·Action 없음).
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
    strategy = getattr(engine, "strategy", None)
    replay = getattr(strategy, "replay_bar", None) if strategy is not None else None
    values, _ = _feed_bar(engine.pullback_indicators, engine.pullback_ring, strategy, bar,
                          replay if callable(replay) else None)
    return values


def _feed_bar(ind, ring, strategy, bar, step: Optional[Callable]):
    """지표 1봉 증분 → step(bar, values) → 링 기록. 워밍업·BACKFILL 재생(replay_bar)과
    실시간 판정(on_bar)이 같은 경로를 쓴다. step 예외에도 링은 기록하고 오염 표식 뒤 전파한다."""
    values = ind.update(bar.close)
    out = None
    try:
        if step is not None:
            out = step(bar, values)
    except Exception:
        ind.state_polluted = True
        raise
    finally:
        if ring is not None:
            ring.record(bar.ts, ind, strategy)
    return values, out


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


# ---------------------------------------------------------------- 전략 (2차 T4)
_RULE_TAG = "[PULLBACK-RULE]"
_SPLIT_DEFAULTS = {
    "entry_count": 0, "pullback_count": 0, "first_entry_ts": None, "first_entry_reason": None,
    "armed": False, "prev_golden": False, "pending_fill": False, "fill_n": 0, "inv_sum": 0.0,
    "last_ts": None,
    "trade_origin": None,  # "live" 실시간 판정이 연 거래 | "replay" 워밍업·BACKFILL 재생이 만든 가상 거래
}
_TS_KEYS = ("first_entry_ts", "last_ts")


def _to_ts(v):
    """T6 저장 형식(KST ISO 문자열) 등 → tz 있는 pd.Timestamp. 시간대 없는 값은 KST 로 본다(Issue #2)."""
    if v is None or (isinstance(v, pd.Timestamp) and v.tzinfo is not None):
        return v
    t = pd.Timestamp(v)
    return t.tz_localize(_KST) if t.tzinfo is None else t


def _yes(v) -> bool:
    """bool 또는 원본 cfg 의 "yes"/"no" 문자열."""
    if isinstance(v, str):
        return v.strip().lower() in ("yes", "true", "1", "y")
    return bool(v)


class IncrementalPullbackStrategy:
    """
    눌림목 분할매수 판정. 원본 simulate() 296-363행과 같은 순서로 봉 하나를 평가한다.
      1. golden·justCrossed·prev_golden 갱신(어느 경로로 빠지든 먼저)
      2. 보유 + deadcross + not golden → SELL DEADCROSS
      3. 보유 + 첫 체결 봉 뒤 → high ≥ TP 이면 TP, 아니면 low ≤ SL 이면 SL
      4. buyOnGoldenCross + justCrossed + 회차 0 + 감시 구간 → BUY GOLDEN (이 봉 끝)
      5. 눌림목: low < maPullback 이면 armed, armed + close > maPullback 이면 BUY PULLBACK
         그 밖(감시 밖·goldenOnly·눌림목 한도) armed 해제, 전체 회차가 찬 경우는 armed 그대로
      6. 감시 구간 = 원본 isFilterActive 229-240
    체결: 신호 봉 i 의 체결은 다음 봉 i+1 시가(원본 bars[i+1].o), first_entry_ts = i+1 봉 시각
          → TP/SL 은 i+2 봉부터.
    on_bar  : 실시간 확정 봉(is_closed·is_confirmed) — 지표·판정·링 기록, Action 을 돌려준다.
              형성 중·잠정 봉(결정 13-5 가)은 지표·판정에 넣지 않고 NOOP.
    replay_bar : 워밍업·BACKFILL 재생 — 판정 상태만 갱신, Action·주문 없음(가상 보유로 판정).
    """

    def __init__(self, user_id: str, ticker: str, params: dict, interval_min: int):
        self.user_id = user_id
        self.ticker = ticker
        self.interval_min = int(interval_min)
        p = params
        golden_only = _yes(p["buyOnGoldenCross"]) and int(p["maxSplits"]) == 0
        self.cfg = {
            "maType": str(p["maType"]).lower(),
            "ma60p": int(p["ma60p"]), "ma200p": int(p["ma200p"]),
            "pullbackP": int(p["pullbackP"]), "slopeLB": int(p["slopeLB"]),
            "minSlope": float(p["minSlope"]), "slopeDrop": float(p["slopeDrop"]),
            "buyOnGoldenCross": _yes(p["buyOnGoldenCross"]),
            "maxSplits": int(p["maxSplits"]), "maxPullbackBuys": int(p["maxPullbackBuys"]),
            "tp": float(p["tp"]), "sl": float(p["sl"]),
            "deadcross": _yes(p["deadcross"]),
            "golden_only": golden_only,
            "eff_max_splits": 1 if golden_only else int(p["maxSplits"]),
        }
        c = self.cfg
        self.indicators = PullbackIndicators(c["ma60p"], c["ma200p"], c["pullbackP"], c["slopeLB"], c["maType"])
        self.ring: Optional[PullbackSnapshotRing] = PullbackSnapshotRing(RING_CAPACITY)
        self.restore_split_state(dict(_SPLIT_DEFAULTS))
        self.last_action = None
        self.last_buy_reason: Optional[str] = None
        self.last_sell_reason: Optional[str] = None
        self.last_eval: dict = {}

    # ------------------------------------------------ 공용 인터페이스
    def bind(self, indicators, ring) -> None:
        """엔진이 만든 지표·링을 같이 쓴다(engine.pullback_indicators·pullback_ring)."""
        self.indicators = indicators
        self.ring = ring

    def reload_conditions(self, buy_conditions: dict, sell_conditions: dict) -> dict:
        """PULLBACK 은 조건 파일을 쓰지 않는다(F13)."""
        return {}

    def set_interval_min(self, interval_min: int) -> None:
        self.interval_min = int(interval_min)

    def export_split_state(self) -> dict:
        return {k: getattr(self, k) for k in _SPLIT_DEFAULTS}

    def restore_split_state(self, d: dict) -> None:
        for k, default in _SPLIT_DEFAULTS.items():
            v = d.get(k, default)
            setattr(self, k, _to_ts(v) if k in _TS_KEYS else v)

    def _guarded_step(self, bar, values, *, live: bool, position):
        """판정 중 예외 → 판정 상태를 봉 전으로 되돌리고 last_ts 만 이 봉으로 둔다(지표는 이미 이 봉을 받음 —
        같은 봉 재투입 시 이중 반영 방지). 오염 표식은 _feed_bar 가 켠다."""
        before = self.export_split_state()
        try:
            return self._step(bar, values, live=live, position=position)
        except Exception:
            self.restore_split_state(before)
            self.last_ts = bar.ts
            raise

    def on_bar(self, bar, ind_snapshot, position, bar_count):
        """실시간 확정 봉 판정. ind_snapshot 은 감사용(쓰지 않음). position=None 이면 가상 보유로 판정."""
        from core.strategy_action import Action
        closed = bool(getattr(bar, "is_closed", False))
        confirmed = bool(getattr(bar, "is_confirmed", False))
        if not (closed and confirmed):
            tentative = closed and "TENTATIVE" in str(getattr(bar, "source", "")).upper()
            key = "TENTATIVE" if tentative else "UNCONFIRMED"
            self.last_eval = {"strategy": "PULLBACK", "mode": "live", "bar_ts": _kst_iso(bar.ts),
                              "failed_keys": [key],
                              "note": "잠정 봉 — 지표·판정에 넣지 않음(결정 13-5 가)" if tentative
                              else "확정 봉 아님 — 판정 안 함"}
            self.last_action = Action.NOOP
            return Action.NOOP
        if self.last_ts is not None and not (bar.ts > self.last_ts):
            self.last_eval = {"strategy": "PULLBACK", "mode": "live", "bar_ts": _kst_iso(bar.ts),
                              "failed_keys": ["DUPLICATE"], "note": "이미 넣은 봉 이하 — 판정 안 함"}
            self.last_action = Action.NOOP
            return Action.NOOP
        _, signal = _feed_bar(self.indicators, self.ring, self, bar,
                              lambda b, v: self._guarded_step(b, v, live=True, position=position))
        if signal is None:
            action = Action.NOOP if "STATE_POLLUTED" in self.last_eval.get("failed_keys", []) else Action.HOLD
        elif signal[0] == "BUY":
            action = Action.BUY
            self.last_buy_reason = signal[1]
        else:
            action = Action.SELL
            self.last_sell_reason = signal[1]
        self.last_action = action
        return action

    def replay_bar(self, bar, values: dict) -> None:
        """워밍업·BACKFILL 재생: 판정 상태만 갱신한다. Action 도 주문도 없다(T3 조건)."""
        self._guarded_step(bar, values, live=False, position=None)
        return None

    # ------------------------------------------------ 판정
    def _reset_trade(self) -> None:
        """원본 closePosition 의 상태 초기화(armed 포함). prev_golden 은 그대로."""
        self.entry_count = 0
        self.pullback_count = 0
        self.first_entry_ts = None
        self.first_entry_reason = None
        self.pending_fill = False
        self.fill_n = 0
        self.inv_sum = 0.0
        self.armed = False
        self.trade_origin = None

    def _is_active(self, v: dict) -> bool:
        """원본 isFilterActive 229-240."""
        t, m, s, s_lb = v.get("maTrend"), v.get("ma200"), v.get("slope200"), v.get("slope200_lb")
        if t is None or m is None or s is None:
            return False
        if not (t > m):
            return False
        if s < self.cfg["minSlope"]:
            return False
        if self.cfg["slopeDrop"] > 0 and s_lb is not None:
            if (s_lb - s) > self.cfg["slopeDrop"]:
                return False
        return True

    def _step(self, bar, v: dict, *, live: bool, position):
        c = self.cfg
        # 0) 직전 봉 신호의 체결 = 이 봉 시가(원본 bars[i+1].o · firstEntryTime = bars[i+1].t)
        just_filled = self.pending_fill
        if self.pending_fill:
            px = float(bar.open) if float(bar.open) > 0 else float(bar.close)
            self.fill_n += 1
            self.inv_sum += 1.0 / px  # 회당 같은 금액 → 평단 = n / Σ(1/px) (원본 cost/qty)
            if self.first_entry_ts is None:
                self.first_entry_ts = bar.ts
            self.pending_fill = False

        # 보유: 실시간은 실제 포지션, 재생(또는 position 없음)은 가상 보유(원본 qty>0)
        desync = False
        deferred = False
        if live and position is not None:
            holding = bool(getattr(position, "has_position", False))
            if not holding and self.entry_count > 0:
                if just_filled and self.trade_origin == "live":
                    # 체결 지연: 신호 봉 다음 봉에 실보유가 아직 안 보임 → 정리를 다음 봉으로 미룸.
                    # 미룸 봉에서는 매수를 막는다(새 신호가 pending_fill 을 다시 켜 미룸이 이어지지 않게 — 최대 1봉).
                    deferred = True
                    logger.info(f"{_RULE_TAG} 체결 대기 봉 — 실보유 미반영, 회차 {self.entry_count} 유지 "
                                f"| ts={format_kst(bar.ts)}")
                else:
                    keep_armed = self.trade_origin == "replay"  # 워밍업·재생 가상 거래만 armed 유지(13-4 가)
                    armed = self.armed
                    logger.warning(
                        f"{_RULE_TAG} 실보유 없음 + 판정 회차 {self.entry_count} (origin={self.trade_origin}) "
                        f"→ 회차 0 으로 맞춤, armed {'유지' if keep_armed else '해제'} | ts={format_kst(bar.ts)}")
                    self._reset_trade()
                    self.armed = armed if keep_armed else False
            elif holding and self.entry_count == 0:
                # 이 전략이 연 거래가 아님(앱 매수·매도 거절) → 매수 신호를 내지 않음
                desync = True
                logger.warning(f"{_RULE_TAG} 실보유 + 판정 회차 0 (POS_DESYNC) → 매수 신호 안 냄 "
                               f"| ts={format_kst(bar.ts)}")
        else:
            holding = self.entry_count > 0
        polluted = live and bool(getattr(self.indicators, "state_polluted", False))
        buy_block = [k for k, on in (("POS_DESYNC", desync), ("PENDING_FILL", deferred),
                                     ("STATE_POLLUTED", polluted)) if on]

        t, m, pm = v.get("maTrend"), v.get("ma200"), v.get("maPullback")
        active = self._is_active(v)
        was_golden = self.prev_golden
        golden = t is not None and m is not None and t > m
        self.prev_golden = golden  # 1) 어느 경로로 빠지든 먼저 갱신
        just_crossed = golden and not was_golden

        avg = None
        if holding:
            p_avg = getattr(position, "avg_price", None) if (live and position is not None) else None
            if p_avg is not None and float(p_avg) > 0:
                avg = float(p_avg)
            elif self.fill_n > 0:
                avg = self.fill_n / self.inv_sum
        tp_price = avg * (1 + c["tp"] / 100) if avg is not None else None
        sl_price = avg * (1 - c["sl"] / 100) if avg is not None else None

        signal = None
        split_round = None
        # 2) 데드크로스 강제청산
        if holding and c["deadcross"] and t is not None and m is not None and not (t > m):
            signal = ("SELL", "DEADCROSS")
        # 3) TP/SL — 첫 체결 봉은 평가하지 않음. 실보유인데 첫 체결 시각이 없으면(앱 매수·재시작) 바로 평가.
        elif holding and avg is not None and (
                (self.first_entry_ts is not None and bar.ts > self.first_entry_ts)
                or (live and position is not None and self.first_entry_ts is None)):
            if bar.high >= tp_price:
                signal = ("SELL", "TP")
            elif bar.low <= sl_price:
                signal = ("SELL", "SL")

        origin = "live" if live else "replay"
        if signal is not None:
            self._reset_trade()
        elif buy_block:
            pass  # 매수 판정(4·5) 건너뜀 — armed 도 그대로
        # 4) 골든크로스 1차 매수
        elif (c["buyOnGoldenCross"] and just_crossed and self.entry_count == 0 and not holding
              and active and self.entry_count < c["eff_max_splits"]):
            self.entry_count += 1
            self.first_entry_reason = "GOLDEN"
            self.trade_origin = origin
            self.pending_fill = True
            self.armed = False
            signal = ("BUY", "GOLDEN")
            split_round = self.entry_count
        else:
            # 5) 눌림목 → 재돌파
            capped = self.pullback_count >= c["maxPullbackBuys"]
            if not c["golden_only"] and not capped and active and self.entry_count < c["eff_max_splits"]:
                if pm is not None and bar.low < pm:
                    self.armed = True
                if self.armed and pm is not None and bar.close > pm:
                    if self.entry_count == 0:
                        self.first_entry_reason = "PULLBACK"
                    self.entry_count += 1
                    self.pullback_count += 1
                    if live:
                        self.trade_origin = "live"  # 재생 거래에 실시간 회차가 더해지면 실거래로 봄
                    elif self.trade_origin is None:
                        self.trade_origin = "replay"
                    self.pending_fill = True
                    self.armed = False
                    signal = ("BUY", "PULLBACK")
                    split_round = self.entry_count
            elif not active or c["golden_only"] or capped:
                self.armed = False
            # 전체 회차가 찬 경우(entry_count ≥ eff_max_splits)는 armed 그대로

        self.last_ts = bar.ts
        ev = {
            "strategy": "PULLBACK", "mode": "live" if live else "replay", "bar_ts": _kst_iso(bar.ts),
            **{k: v.get(k) for k in ("maTrend", "ma200", "maPullback", "slope200", "slope200_lb")},
            "active": active, "golden": golden, "just_crossed": just_crossed, "armed": self.armed,
            "holding": holding, "avg": avg, "tp_price": tp_price, "sl_price": sl_price,
            "entry_count": self.entry_count, "pullback_count": self.pullback_count,
            "max_splits": c["eff_max_splits"], "max_pullback_buys": c["maxPullbackBuys"],
            "signal": signal[0] if signal else None, "reason": signal[1] if signal else None,
            "split_round": split_round,
            "failed_keys": ([] if (signal and live) else (["REPLAY"] if not live else
                            (list(buy_block) if buy_block else ["NO_SIGNAL"]))),
        }
        if not live:
            ev["replay_signal"] = f"{signal[0]}:{signal[1]}" if signal else None
        self.last_eval = ev
        return signal
