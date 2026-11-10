"""
1109 눌림목 실계좌 열기 — EMA·MACD 경로 불변을 「호출 흔적」으로 지키는 시나리오 모음.

공용 함수 3개(UpbitTrader.buy_market · PositionState.sync_from_wallet · StrategyEngine._reconcile_position_with_wallet)를
EMA 방식(눌림목 인자 없음)으로 불러 trader·DB·알림·잠자기 호출 흔적을 JSON 으로 돌려준다. 이 흔적을 기준 커밋(158c5fc)의
같은 코드에서 뽑은 값(GOLDEN, test_r_2026_11_09_ema_trace.py)과 지금 코드의 값을 비교한다. 업비트·텔레그램에 닿지 않는다(전부 대역).

이 파일은 저장소 상태에 의존하지 않는다 — 어느 트리(기준 커밋 추출본 · 지금 작업 사본)의 `core`·`services` 를 쓰는지는
호출하는 쪽의 sys.path 가 정한다(기준값을 뽑을 때 기준 트리를 앞에 놓고 이 파일을 경로로 불러온다).
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest import mock


_T0 = __import__("datetime").datetime(2026, 11, 9, 10, 0, tzinfo=__import__("zoneinfo").ZoneInfo("Asia/Seoul"))


def _jsonable(o):
    try:
        return json.loads(json.dumps(o, default=repr))
    except Exception:
        return repr(o)


# ------------------------------------------------------------------ buy_market (EMA 경로)
def _trader_trace(responses, krw_values=None):
    from core import trader as T
    rec = {"buy_calls": [], "sleeps": [], "orders": [], "logs": [], "notify": [], "krw_reads": 0}
    it = iter(responses)

    def fake_buy(market, krw):
        rec["buy_calls"].append([market, krw])
        return next(it)

    def fake_order(*a, **k):
        k.pop("requested_at", None)
        rec["orders"].append(_jsonable([list(a), sorted(k.items())]))

    def fake_log(user, level, msg):
        rec["logs"].append([level, msg[:60]])

    def fake_send(level, title, body, **k):
        rec["notify"].append([level, title])
        return True

    ps = [mock.patch("core.trader.pyupbit.Upbit"), mock.patch("core.trader._upbit_buy_market", side_effect=fake_buy),
          mock.patch("core.trader.insert_order", side_effect=fake_order),
          mock.patch("core.trader.insert_log", side_effect=fake_log),
          mock.patch("core.trader._time.sleep", side_effect=lambda s: rec["sleeps"].append(s)),
          mock.patch("services.notifier.send", side_effect=fake_send),
          mock.patch.object(T.UpbitTrader, "_get_settings_history_id", return_value=None),
          mock.patch("engine.reconciler_singleton.get_reconciler", return_value=mock.MagicMock())]
    for p in ps:
        p.start()
    try:
        t = T.UpbitTrader("tracer", risk_pct=0.5, test_mode=False, strategy_type="EMA", params_file=None)
        vals = list(krw_values or [10_000_000] * 8)

        def krw():
            rec["krw_reads"] += 1
            return float(vals.pop(0) if vals else 10_000_000)
        t._krw_balance = krw
        res = t.buy_market(1000.0, "KRW-TRACE", ts="T", meta={"reason": "EMA_GC", "bar": 7})
        rec["result"] = _jsonable({k: v for k, v in (res or {}).items() if k != "raw"})
        rec["last_buy_error"] = getattr(t, "last_buy_error", None)
    finally:
        for p in reversed(ps):
            p.stop()
    return rec


def _call(ok=False, status=None, body=None, error_name=None, error_message=None, exception=None, data=None):
    return {"ok": ok, "status": status, "body": body, "error_name": error_name, "error_message": error_message,
            "exception": exception, "data": data}


def trader_scenarios():
    ok = _call(ok=True, status=201, body={"uuid": "u-1"}, data={"uuid": "u-1"})
    nonret = _call(status=400, body={"error": {"name": "insufficient_funds_bid", "message": "m"}},
                   error_name="insufficient_funds_bid", error_message="m")
    ret = _call(status=429, body={"error": {"name": "too_many_request", "message": "m"}},
                error_name="too_many_request", error_message="m")
    net = _call(exception="ReadTimeout: x", error_name="network_exception", error_message="x")
    s5xx = _call(status=503, body="<html>")
    nouuid = _call(status=201, body={"market": "KRW-TRACE"})
    out = {}
    out["success"] = _trader_trace([ok])
    out["non_retriable"] = _trader_trace([nonret])
    out["retriable_all_fail"] = _trader_trace([ret, ret, ret, ret, ret])
    out["network_then_success"] = _trader_trace([net, ok])
    out["network_all_fail"] = _trader_trace([net] * 6)
    out["5xx_then_success"] = _trader_trace([s5xx, ok])
    out["no_uuid_then_success"] = _trader_trace([nouuid, ok])
    out["balance_shrinks_between_attempts"] = _trader_trace([ret, ok], krw_values=[10_000_000, 3_000_000, 3_000_000])
    return out


# ------------------------------------------------------------------ PositionState.sync_from_wallet (EMA 경로)
class _FakeTrader:
    def __init__(self, qty, test_mode=False, avg=0.0, raise_on_coin=False):
        self.qty, self.test_mode, self.avg, self.raise_on_coin = qty, test_mode, avg, raise_on_coin
        self.user_id = "tracer"
        self.calls = []
        self.upbit = SimpleNamespace(get_balances=self._balances)

    def _balances(self):
        self.calls.append("get_balances")
        return [{"currency": "KRW", "balance": "1", "locked": "0", "avg_buy_price": "0"},
                {"currency": "TRACE", "balance": str(self.qty), "locked": "0", "avg_buy_price": str(self.avg)}]

    def _coin_balance(self, ticker):
        self.calls.append(("coin_balance", ticker))
        if self.raise_on_coin:
            raise RuntimeError("boom")
        return self.qty


def sync_scenarios():
    from core.position_state import PositionState
    out = {}
    for name, qty, avg, prep in (
            ("wallet_zero_flat", 0.0, 0.0, None), ("wallet_has_coin_no_avg", 2.5, 0.0, None),
            ("wallet_has_coin_with_avg", 2.5, 1000.0, None), ("wallet_zero_but_memory_pos", 0.0, 0.0, "pos"),
            ("raises", 1.0, 0.0, "raise")):
        tr = _FakeTrader(qty, avg=avg, raise_on_coin=(prep == "raise"))
        with mock.patch("services.db.get_position_entry_price", return_value=None, create=True):
            p = PositionState(trader=tr, ticker="KRW-TRACE")
            if prep == "pos":
                p.apply_entry(qty=1.0, avg_price=100.0, entry_bar=1, entry_ts=_T0, source="x")
            r = p.sync_from_wallet()
        out[name] = {"ret": r, "calls": _jsonable(tr.calls), "has": p.has_position, "qty": p.qty,
                     "avg": p.avg_price}
    tr = _FakeTrader(3.0, test_mode=True)
    p = PositionState(trader=tr, ticker="KRW-TRACE")
    out["test_mode_skips"] = {"ret": p.sync_from_wallet(), "calls": tr.calls}
    return out


# ------------------------------------------------------------------ StrategyEngine._reconcile_position_with_wallet (EMA 경로)
def reconcile_scenarios():
    from core import strategy_engine as se
    from core.position_state import PositionState
    out = {}
    cases = (("zero_wallet_memory_pos", 0.0, 0.0, True), ("coin_wallet_no_memory_with_avg", 4.0, 1000.0, False),
             ("coin_wallet_no_memory_no_avg", 4.0, 0.0, False), ("both_flat", 0.0, 0.0, False),
             ("both_holding", 4.0, 1000.0, True))
    for name, qty, avg, holding in cases:
        tr = _FakeTrader(qty, avg=avg)
        rec = {"audit": [], "db": []}
        ps = [mock.patch("services.db.insert_trade_audit",
                         side_effect=lambda **k: rec["audit"].append(sorted((a, repr(b)) for a, b in k.items()
                                                                           if a not in ("meta",)))),
              mock.patch("services.db.get_position_entry_price", side_effect=lambda *a, **k: rec["db"].append("entry_price") or None),
              mock.patch("services.db.get_last_open_buy_order", side_effect=lambda *a, **k: rec["db"].append("last_buy") or None)]
        for p in ps:
            p.start()
        try:
            eng = se.StrategyEngine.__new__(se.StrategyEngine)
            eng.trader = tr
            eng.ticker = "KRW-TRACE"
            eng.user_id = "tracer"
            eng.bar_count = 5
            eng.interval_sec = 60
            eng.strategy_type = "EMA"
            eng._boot_seed_verify = None
            eng.position = PositionState(trader=tr, ticker="KRW-TRACE")
            if holding:
                eng.position.apply_entry(qty=4.0, avg_price=1000.0, entry_bar=2, entry_ts=_T0, source="x")
            ret = eng._reconcile_position_with_wallet()
        finally:
            for p in reversed(ps):
                p.stop()
        out[name] = {"ret": ret, "calls": _jsonable(tr.calls), "has": eng.position.has_position,
                     "qty": eng.position.qty, "avg": eng.position.avg_price, "audit": rec["audit"], "db": rec["db"]}
    return out


def run_all():
    return _jsonable({"trader": trader_scenarios(), "sync": sync_scenarios(), "reconcile": reconcile_scenarios()})


if __name__ == "__main__":
    print(json.dumps(run_all(), sort_keys=True, ensure_ascii=False, indent=1))
