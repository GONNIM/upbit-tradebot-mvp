"""
2차 T13 (결정 D9, 요청서 5절): 「저장만 하기」·「이 설정으로 동작」 — 신버전 쪽 시험.

- 「저장만 하기」는 저장본·v2hist 만 쓴다. 적용본·신버전 읽기(종목·봉·봉 경계 창·미리 받기)는 바뀌지 않는다.
- PULLBACK 운용 중 신버전 읽기 4곳은 적용본 기준(v2.db.active_params). 저장본은 백테스터 입력 채움(GET current)에만.
- 저장은 이전 저장본의 선택 4키(거래 시간)를 보존한다. 응답에 저장본 해시(엔진 적용 요청용).
- 적용 요청(POST /v2/api/control kind apply_params)은 마지막 저장이 업비트 출처일 때만(아니면 400).
- 엔진 결과가 done 이면 POST /v2/api/params/applied 가 v2hist 그 행 applied_at 을 결과 시각으로 1회 채운다.

실행:
    python3 -m unittest tests.regressions.test_r_2026_10_29_p4_t13_v2 -v
"""
import hashlib
import json
import os
import sys
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from v2 import api_write, candles, control, db, params_schema  # noqa: E402
from tests.v2.test_api_write import VALID, WriteBase  # noqa: E402

UPBIT = dict(VALID, symbol="KRW-ZRO", src="1m")
APPLIED = {"ticker": "KRW-ZRO", "interval": "minute3", "maType": "ema", "ma60p": 60, "ma200p": 200,
           "pullbackP": 60, "slopeLB": 20, "minSlope": 0, "slopeDrop": 0, "buyOnGoldenCross": True,
           "maxSplits": 5, "maxPullbackBuys": 5, "tp": 1.0, "sl": 1.5, "deadcross": True, "compounding": False,
           "capital": 10000, "fee": 0.05}
CONTROL_URL = "/v2/api/control"
APPLIED_URL = "/v2/api/params/applied"


class Base(WriteBase):
    def pullback_active(self, applied=None):
        (self.root / f"{self.USER}_active_strategy.txt").write_text("PULLBACK\n", encoding="utf-8")
        self.applied = db.applied_params_path(self.USER)
        self.applied.write_text(json.dumps(applied or APPLIED), encoding="utf-8")
        os.chmod(self.applied, 0o600)

    def save(self, params=None, source="upbit"):
        r = self.post_json({"params": params or UPBIT, "source": source})
        self.assertEqual(r.code, 200, r.body)
        return self.body(r)

    def post_any(self, url, body):
        return self.fetch(url, method="POST", body=json.dumps(body), headers=self.headers())


class TestSaveOnly(Base):
    def test_save_only_does_not_change_applied(self):
        self.pullback_active()
        before = (self.applied.read_bytes(), self.applied.stat().st_mtime_ns, self.applied.stat().st_ino)
        self.save(dict(UPBIT, tp=4.0))
        after = (self.applied.read_bytes(), self.applied.stat().st_mtime_ns, self.applied.stat().st_ino)
        self.assertEqual(after, before)
        self.assertFalse(control.control_dir(self.USER).exists())      # 엔진 요청도 없음(엔진 값 불변)
        self.assertEqual(json.loads(self.pb.read_text(encoding="utf-8"))["tp"], 4.0)

    def test_save_only_does_not_change_v2_reads(self):
        """PULLBACK 운용 중 저장본만 봉 단위가 바뀜(1분) → 상태 API·봉 경계 창·미리 받기 대상은 적용본(3분)."""
        self.pullback_active()
        self.save(dict(UPBIT, src="1m"))
        self.assertEqual(json.loads(self.pb.read_text(encoding="utf-8"))["interval"], "minute1")
        code, st = self.get_json("/v2/api/status")
        self.assertEqual(code, 200)
        self.assertEqual((st["ticker"], st["interval"]), ("KRW-ZRO", "minute3"))
        c = candles.Collector(fetch=mock.MagicMock(), data_dir_fn=lambda: self.data)
        self.assertEqual(c._engine_units({"running": {self.USER: True}}), {3})
        self.assertEqual(c._targets(), {("KRW-ZRO", 3): [self.USER]})

    def test_saved_file_is_backtester_input_only(self):
        self.pullback_active()
        self.save(dict(UPBIT, tp=4.0))
        code, cur = self.get_json("/v2/api/params/current")
        self.assertEqual(cur["params"]["tp"], 4.0)                       # 백테스터 입력 채움 = 저장본
        self.assertEqual(db.active_params(self.USER)["tp"], 1.0)        # 엔진 기준 읽기 = 적용본

    def test_active_params_missing_applied_is_empty(self):
        (self.root / f"{self.USER}_active_strategy.txt").write_text("PULLBACK\n", encoding="utf-8")
        self.assertEqual(db.active_params(self.USER), {})
        self.assertEqual(db.active_params(self.USER, "EMA"), {"ticker": "KRW-ZRO", "interval": "minute3"})

    def test_engine_ticker_from_applied_when_pullback(self):
        self.pullback_active(dict(APPLIED, ticker="KRW-ABC"))
        self.pb.write_text(json.dumps(dict(APPLIED, ticker="KRW-OLD")), encoding="utf-8")
        body = self.save(dict(UPBIT, symbol="KRW-ABC"))
        self.assertEqual(body["ticker"], "KRW-ABC")
        self.assertEqual(json.loads(self.pb.read_text(encoding="utf-8"))["ticker"], "KRW-ABC")

    def test_save_response_has_saved_sha256(self):
        body = self.save()
        self.assertEqual(body["saved_sha256"], hashlib.sha256(self.pb.read_bytes()).hexdigest())

    def test_save_keeps_trading_hours_keys(self):
        old = dict(APPLIED, enable_trading_hours=True, trading_start_time="10:00", trading_end_time="22:30",
                   allow_sell_during_off_hours=False)
        self.pb.write_text(json.dumps(old), encoding="utf-8")
        self.save(dict(UPBIT, tp=4.0))
        d = json.loads(self.pb.read_text(encoding="utf-8"))
        self.assertEqual(list(d)[-4:], list(params_schema.OPTIONAL_KEYS))
        self.assertEqual((d["enable_trading_hours"], d["trading_start_time"], d["trading_end_time"],
                          d["allow_sell_during_off_hours"], d["tp"]), (True, "10:00", "22:30", False, 4.0))
        # 형식이 틀린 이전 값은 옮기지 않는다
        self.pb.write_text(json.dumps(dict(APPLIED, trading_start_time="25:00", enable_trading_hours="yes")),
                           encoding="utf-8")
        self.save()
        d = json.loads(self.pb.read_text(encoding="utf-8"))
        self.assertNotIn("trading_start_time", d)
        self.assertNotIn("enable_trading_hours", d)

    def test_ticker_regex_letters_only(self):
        r = self.post_json({"params": dict(UPBIT, symbol="KRW-1INCH"), "source": "upbit"})
        self.assertEqual(r.code, 400)
        self.assertEqual(self.body(r), {"error": "invalid_param", "field": "symbol"})
        self.assertIsNone(api_write._TICKER_RE.fullmatch("KRW-1INCH"))
        self.assertIsNotNone(api_write._TICKER_RE.fullmatch("KRW-JTO"))
        from engine import pullback_params as pbp
        self.assertEqual(params_schema._UPBIT_SYMBOL_RE.pattern, pbp._TICKER_RE.pattern)
        self.assertEqual(params_schema.OPTIONAL_KEYS, tuple(pbp.OPTIONAL_KEYS))


class TestApplyRequest(Base):
    def test_control_apply_binance_400_no_request(self):
        self.pullback_active()
        self.save(VALID, source="binance")
        r = self.post_any(CONTROL_URL, {"kind": "apply_params", "payload": {"saved_sha256": "0" * 64}})
        self.assertEqual(r.code, 400)
        self.assertEqual(self.body(r), {"error": "source_not_upbit"})
        d = control.control_dir(self.USER)
        self.assertEqual(sorted(p.name for p in d.iterdir()) if d.exists() else [], [])

    def test_control_apply_upbit_202(self):
        self.pullback_active()
        body = self.save()
        r = self.post_any(CONTROL_URL, {"kind": "apply_params", "payload": {"saved_sha256": body["saved_sha256"]}})
        self.assertEqual(r.code, 202, r.body)
        rid = self.body(r)["id"]
        req = json.loads((control.control_dir(self.USER) / f"req-{rid}.json").read_text(encoding="utf-8"))
        self.assertEqual((req["kind"], req["payload"]), ("apply_params", {"saved_sha256": body["saved_sha256"]}))

    def test_control_apply_without_history_400(self):
        r = self.post_any(CONTROL_URL, {"kind": "apply_params", "payload": {"saved_sha256": "0" * 64}})
        self.assertEqual(r.code, 400)

    def _result(self, status="done", detail=None, rid="20261029120000-0000abcd"):
        d = control.control_dir(self.USER)
        control._ensure_dir(d)
        (d / f"res-{rid}.json").write_text(json.dumps({
            "id": rid, "status": status, "code": "ok", "message": "요청대로 처리했습니다.",
            "at": "2026-10-29T12:00:05+09:00",
            "detail": detail if detail is not None else
            {"applied_sha256": hashlib.sha256(self.pb.read_bytes()).hexdigest()}}), encoding="utf-8")
        return rid

    def hist_applied(self):
        return [r["applied_at"] for r in self.hist_rows()]

    def test_v2hist_applied_at_set(self):
        body = self.save()
        rid = self._result()
        r = self.post_any(APPLIED_URL, {"history_id": body["history_id"], "request_id": rid})
        self.assertEqual(r.code, 200, r.body)
        self.assertEqual(self.hist_applied(), ["2026-10-29T12:00:05+09:00"])
        r = self.post_any(APPLIED_URL, {"history_id": body["history_id"], "request_id": rid})
        self.assertEqual(self.body(r)["changed"], False)                 # 1회만

    def test_applied_at_not_set_when_not_done_or_not_latest(self):
        a = self.save()
        rid_bad = self._result(status="rejected", rid="20261029120000-0000aaaa")
        self.assertEqual(self.post_any(APPLIED_URL, {"history_id": a["history_id"], "request_id": rid_bad}).code, 409)
        rid_nosha = self._result(detail={}, rid="20261029120000-0000bbbb")
        self.assertEqual(self.post_any(APPLIED_URL, {"history_id": a["history_id"], "request_id": rid_nosha}).code, 409)
        self.save(dict(UPBIT, tp=2.0))                                   # 그 뒤 다른 저장
        rid = self._result()
        self.assertEqual(self.post_any(APPLIED_URL, {"history_id": a["history_id"], "request_id": rid}).code, 409)
        self.assertEqual(self.hist_applied(), [None, None])
        for bad in ({"history_id": "1", "request_id": rid}, {"history_id": 1, "request_id": "x"}, []):
            self.assertEqual(self.post_any(APPLIED_URL, bad).code, 400, bad)

    def test_applied_at_not_set_for_stale_result(self):
        """fix 1: 옛 저장을 적용한 결과(옛 request_id)로 새 저장 행을 채우지 않는다 — 결과 해시 ≠ 지금 저장본."""
        self.save()
        old_rid = self._result(rid="20261029120000-0000cccc")         # 첫 저장을 적용한 결과
        b = self.save(dict(UPBIT, tp=2.0))                               # 그 뒤 다른 저장(마지막 행)
        r = self.post_any(APPLIED_URL, {"history_id": b["history_id"], "request_id": old_rid})
        self.assertEqual((r.code, self.body(r)), (409, {"error": "stale_result"}))
        self.assertEqual(self.hist_applied(), [None, None])
        new_rid = self._result(rid="20261029120000-0000dddd")           # 지금 저장을 적용한 결과
        self.assertEqual(self.post_any(APPLIED_URL, {"history_id": b["history_id"], "request_id": new_rid}).code, 200)
        self.assertEqual(self.hist_applied(), [None, "2026-10-29T12:00:05+09:00"])

    def test_applied_requires_origin(self):
        a = self.save()
        rid = self._result()
        r = self.fetch(APPLIED_URL, method="POST", body=json.dumps({"history_id": a["history_id"], "request_id": rid}),
                       headers=self.headers(origin=None))
        self.assertEqual(r.code, 403)
        self.assertEqual(self.hist_applied(), [None])


if __name__ == "__main__":
    import unittest
    unittest.main()
