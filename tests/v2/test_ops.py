"""2차 T14: 운용 탭 신버전 쪽 시험 — GET /v2/api/ops·/v2/api/control/state 예약, POST /v2/api/control ops_settings.

- 예약은 입장 모드로 거른 strategy_switch RESERVED 전환·복귀 1행(읽기만). PARAMS 행은 예약이 아니다.
- 복귀 대상 = 마지막 DONE SWITCH 의 전략 + 그 전략 설정 파일의 종목·봉(엔진 복귀와 같은 값).
- 회당 금액 = floor(배분 기준 / 한도): 회차 > 0 이면 pullback_state.sizing_base_krw, 아니면 users.virtual_krw(복리면 + 실현 손익).
- ops_settings: 4키 형식이 맞을 때만 요청을 쓰고, 그 뒤 저장본의 같은 4키만 맞춰 쓴다(다른 키·이력 그대로).
"""
import hashlib
import json

from v2 import control
from v2.server import DEFAULT_ORIGIN
from tests.v2 import test_api_read as base

# 1029-09: 「시간 밖에도 익절」(allow_sell_during_off_hours) 도 바꿀 수 있다(형식은 참/거짓)
KEYS = {"enable_trading_hours": True, "trading_start_time": "10:00", "trading_end_time": "23:00",
        "allow_sell_during_off_hours": True}
SAVED = {"ticker": "KRW-ZRO", "interval": "minute3", "maType": "ema", "ma60p": 60, "ma200p": 200, "pullbackP": 20,
         "slopeLB": 10, "minSlope": 0, "slopeDrop": 0, "buyOnGoldenCross": False, "maxSplits": 5,
         "maxPullbackBuys": 3, "tp": 5, "sl": 3, "deadcross": True, "compounding": False, "capital": 1000000,
         "fee": 0.05}

DDL = [
    "CREATE TABLE IF NOT EXISTS strategy_switch (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, mode TEXT, "
    "kind TEXT, from_strategy TEXT, from_ticker TEXT, from_interval TEXT, to_strategy TEXT, to_ticker TEXT, "
    "to_interval TEXT, params_sha256 TEXT, state TEXT, requested_at TEXT, request_id TEXT, note TEXT, done_at TEXT)",
    "CREATE TABLE IF NOT EXISTS pullback_state (user_id TEXT, mode TEXT, ticker TEXT, interval TEXT, "
    "entry_count INTEGER DEFAULT 0, sizing_base_krw REAL, realized_pnl_krw REAL DEFAULT 0, "
    "PRIMARY KEY (user_id, mode))",
]


class OpsApiTest(base.ApiBase):
    def setUp(self):
        super().setUp()
        self.make_live_db()
        for s in DDL:
            self.conn.execute(s)
        self.conn.execute("INSERT INTO users (username, virtual_krw) VALUES ('alice', 3000000)")
        self.conn.commit()

    def pullback(self, applied=None, saved=None):
        (self.root / "alice_active_strategy.txt").write_text("PULLBACK\n", encoding="utf-8")
        a = dict(SAVED, **(applied or {}))
        (self.root / "alice_applied_params_PULLBACK.json").write_text(json.dumps(a), encoding="utf-8")
        (self.root / "alice_latest_params_PULLBACK.json").write_text(json.dumps(dict(SAVED, **(saved or {}))),
                                                                       encoding="utf-8")

    def row(self, **kw):
        d = dict(user_id="alice", mode="TEST", kind="SWITCH", from_strategy="EMA", to_strategy="PULLBACK",
                 state="RESERVED", note=None, from_ticker="KRW-OLD", from_interval="minute1")
        d.update(kw)
        cols = ",".join(d)
        self.conn.execute(f"INSERT INTO strategy_switch ({cols}) VALUES ({','.join('?' * len(d))})", tuple(d.values()))
        self.conn.commit()

    def post(self, body, mode="TEST"):
        h = dict(self.cookie(mode=mode))
        h["Content-Type"] = "application/json"
        h["Origin"] = DEFAULT_ORIGIN
        return self.fetch("/v2/api/control", method="POST", body=json.dumps(body), headers=h)

    # ---------------------------------------------------------------- 읽기
    def test_ops_ema_saved_ok_sha_and_order_ratio(self):
        self.set_strategy("EMA", "KRW-ZRO", "minute3")
        (self.root / "alice_latest_params_EMA.json").write_text(
            json.dumps({"ticker": "KRW-ZRO", "interval": "minute3", "order_ratio": 0.3}), encoding="utf-8")
        raw = json.dumps(SAVED).encode()
        (self.root / "alice_latest_params_PULLBACK.json").write_bytes(raw)
        code, d = self.get_json("/v2/api/ops")
        self.assertEqual(code, 200)
        self.assertEqual(d["strategy"], "EMA")
        self.assertEqual(d["saved"], {"ok": True, "sha256": hashlib.sha256(raw).hexdigest()})
        self.assertEqual(d["order_ratio"], 0.3)
        self.assertIsNone(d["reservation"])
        self.assertFalse(d["reservation_error"])
        self.assertIsNone(d["round"])

    def test_ops_saved_broken_not_ok(self):
        self.set_strategy("EMA")
        (self.root / "alice_latest_params_PULLBACK.json").write_text("{", encoding="utf-8")
        self.assertEqual(self.get_json("/v2/api/ops")[1]["saved"], {"ok": False, "sha256": None})
        (self.root / "alice_latest_params_PULLBACK.json").write_text(json.dumps({"ticker": "KRW-ZRO"}), encoding="utf-8")
        self.assertFalse(self.get_json("/v2/api/ops")[1]["saved"]["ok"])

    def test_reservation_filtered_by_mode_and_kind(self):
        self.set_strategy("EMA")
        self.row(kind="PARAMS", state="DONE")
        self.row(mode="LIVE")
        self.assertIsNone(self.get_json("/v2/api/ops", mode="TEST")[1]["reservation"])
        self.row(kind="REVERT", from_strategy="PULLBACK", to_strategy="EMA")
        res = self.get_json("/v2/api/ops", mode="TEST")[1]["reservation"]
        self.assertEqual((res["kind"], res["switching"]), ("REVERT", False))
        code, st = self.get_json("/v2/api/control/state", mode="TEST")
        self.assertEqual(st["reservation"]["kind"], "REVERT")
        self.assertEqual(self.get_json("/v2/api/control/state", mode="LIVE")[1]["reservation"]["kind"], "SWITCH")

    def test_reservation_table_missing_is_error_flag(self):
        self.set_strategy("EMA")
        self.conn.execute("DROP TABLE strategy_switch")
        self.conn.commit()
        d = self.get_json("/v2/api/ops")[1]
        self.assertTrue(d["reservation_error"])
        self.assertIsNone(d["reservation"])
        self.assertEqual(self.get_json("/v2/api/control/state")[1]["reservation"], None)

    def test_pullback_round_per_buy_hours_revert_target(self):
        self.pullback(applied=dict(KEYS))
        (self.root / "alice_latest_params_EMA.json").write_text(
            json.dumps({"ticker": "ZRO", "interval": "minute5"}), encoding="utf-8")
        self.row(state="DONE", from_strategy="EMA", from_ticker="KRW-OLD", from_interval="minute1")
        d = self.get_json("/v2/api/ops")[1]
        self.assertEqual(d["round"], {"entry": 0, "max": 5})
        self.assertEqual(d["per_buy"], 600000)                     # 3,000,000 / 5 (미보유 = 운용자산)
        self.assertEqual(d["hours"], KEYS)
        # 복귀 대상 = 기록의 전략 + 그 전략 설정 파일의 종목·봉(엔진과 같은 값)
        self.assertEqual(d["revert_target"], {"strategy": "EMA", "ticker": "KRW-ZRO", "interval": "minute5"})

    def test_per_buy_uses_fixed_sizing_base_while_holding_and_compounding(self):
        self.pullback(applied={"compounding": True})
        self.conn.execute("INSERT INTO pullback_state (user_id, mode, ticker, interval, entry_count, sizing_base_krw, "
                          "realized_pnl_krw) VALUES ('alice','TEST','KRW-ZRO','minute3',2,2000000,500000)")
        self.conn.commit()
        d = self.get_json("/v2/api/ops")[1]
        self.assertEqual((d["round"], d["per_buy"]), ({"entry": 2, "max": 5}, 400000))   # 고정 기준 2,000,000 / 5
        self.conn.execute("UPDATE pullback_state SET entry_count=0")
        self.conn.commit()
        self.assertEqual(self.get_json("/v2/api/ops")[1]["per_buy"], 700000)            # (3,000,000 + 500,000) / 5

    def test_golden_only_max_is_one(self):
        self.pullback(applied={"maxSplits": 0, "buyOnGoldenCross": True})
        self.assertEqual(self.get_json("/v2/api/ops")[1]["round"], {"entry": 0, "max": 1})

    def test_no_revert_target_without_record(self):
        self.pullback()
        self.assertIsNone(self.get_json("/v2/api/ops")[1]["revert_target"])

    def test_ops_requires_session(self):
        self.assertEqual(self.fetch("/v2/api/ops").code, 401)

    # ---------------------------------------------------------------- ops_settings 요청
    def test_ops_settings_writes_request_and_syncs_saved_4_keys_only(self):
        self.pullback(saved={"tp": 4})
        hist_before = self.data.joinpath("v2hist_alice.db").exists()
        r = self.post({"kind": "ops_settings", "payload": {"keys": KEYS}})
        self.assertEqual(r.code, 202, r.body)
        body = json.loads(r.body)
        self.assertTrue(body["saved_synced"])
        req = json.loads((self.data / "v2_control" / "alice" / f"req-{body['id']}.json").read_text())
        self.assertEqual((req["kind"], req["payload"]), ("ops_settings", {"keys": KEYS}))
        saved = json.loads((self.root / "alice_latest_params_PULLBACK.json").read_text())
        self.assertEqual(saved, dict(SAVED, tp=4, **KEYS))                    # 다른 키(tp 4) 그대로, 4키만 새 값
        self.assertEqual(self.data.joinpath("v2hist_alice.db").exists(), hist_before)   # 이력 행 없음

    def test_ops_settings_bad_payload_400_no_request_no_saved_change(self):
        self.pullback()
        before = (self.root / "alice_latest_params_PULLBACK.json").read_bytes()
        for payload in ({"keys": dict(KEYS, tp=1)}, {"keys": dict(KEYS, trading_start_time="9:00")},
                        {"keys": KEYS, "x": 1}, {}, "x"):
            self.assertEqual(self.post({"kind": "ops_settings", "payload": payload}).code, 400, payload)
        self.assertFalse((self.data / "v2_control").exists())
        self.assertEqual((self.root / "alice_latest_params_PULLBACK.json").read_bytes(), before)

    def test_ops_settings_busy_does_not_touch_saved(self):
        self.pullback()
        self.assertEqual(self.post({"kind": "engine_start", "payload": {}}).code, 202)
        before = (self.root / "alice_latest_params_PULLBACK.json").read_bytes()
        self.assertEqual(self.post({"kind": "ops_settings", "payload": {"keys": KEYS}}).code, 409)
        self.assertEqual((self.root / "alice_latest_params_PULLBACK.json").read_bytes(), before)

    def test_ops_settings_saved_missing_still_sends(self):
        self.pullback()
        (self.root / "alice_latest_params_PULLBACK.json").unlink()
        r = self.post({"kind": "ops_settings", "payload": {"keys": KEYS}})
        self.assertEqual(r.code, 202)
        self.assertFalse(json.loads(r.body)["saved_synced"])
        self.assertFalse((self.root / "alice_latest_params_PULLBACK.json").exists())   # 만들지 않음

    # ---------------------------------------------------------------- T14 fix 1
    def test_ops_scope_ignores_query_user_and_mode(self):
        """GET /v2/api/ops?user_id=bob&mode=LIVE 이어도 세션(alice·TEST) 값만 (V06b)."""
        self.set_strategy("EMA")
        (self.root / "bob_active_strategy.txt").write_text("MACD\n", encoding="utf-8")
        self.row(mode="LIVE")
        code, d = self.get_json("/v2/api/ops?user_id=bob&mode=LIVE")
        self.assertEqual(code, 200)
        self.assertEqual((d["strategy"], d["mode"]), ("EMA", "TEST"))
        self.assertIsNone(d["reservation"])

    def test_ops_live_session_sees_only_live_reservation(self):
        """실계좌 입장은 실계좌 예약만, 모의 입장은 모의 예약만 (V06c)."""
        self.set_strategy("EMA")
        self.row(mode="TEST", kind="SWITCH")
        self.row(mode="LIVE", kind="REVERT", from_strategy="PULLBACK", to_strategy="EMA")
        live = self.get_json("/v2/api/ops", mode="LIVE")[1]
        self.assertEqual((live["mode"], live["reservation"]["kind"]), ("LIVE", "REVERT"))
        self.assertEqual(self.get_json("/v2/api/ops", mode="TEST")[1]["reservation"]["kind"], "SWITCH")

    def test_revert_target_only_from_switch_rows(self):
        """복귀 대상은 kind='SWITCH' DONE 행만 — 뒤에 온 PARAMS 행(from MACD)은 보지 않는다 (V16)."""
        self.pullback()
        (self.root / "alice_latest_params_EMA.json").write_text(
            json.dumps({"ticker": "KRW-ZRO", "interval": "minute3"}), encoding="utf-8")
        (self.root / "alice_latest_params_MACD.json").write_text(
            json.dumps({"ticker": "KRW-BTC", "interval": "minute5"}), encoding="utf-8")
        self.row(state="DONE", from_strategy="EMA")
        self.row(state="DONE", kind="PARAMS", from_strategy="MACD", to_strategy="PULLBACK")
        self.assertEqual(self.get_json("/v2/api/ops")[1]["revert_target"]["strategy"], "EMA")

    def _no_request_saved_same(self, before):
        self.assertFalse((self.data / "v2_control").exists())
        self.assertEqual((self.root / "alice_latest_params_PULLBACK.json").read_bytes(), before)

    def test_ops_settings_rejected_when_not_pullback(self):
        """새 전략 운용 중이 아니면 요청도 저장본 맞춤도 없다 (PO 결정 2)."""
        self.pullback()
        self.set_strategy("EMA")
        before = (self.root / "alice_latest_params_PULLBACK.json").read_bytes()
        r = self.post({"kind": "ops_settings", "payload": {"keys": KEYS}})
        self.assertEqual((r.code, json.loads(r.body)["error"]), (409, "not_pullback"))
        self._no_request_saved_same(before)

    def test_ops_settings_rejected_while_reserved_in_that_mode(self):
        """그 모드에 예약이 있으면 거절. 다른 모드 예약·PARAMS 행은 막지 않는다 (PO 결정 2)."""
        self.pullback()
        before = (self.root / "alice_latest_params_PULLBACK.json").read_bytes()
        self.row(kind="REVERT", from_strategy="PULLBACK", to_strategy="EMA")
        r = self.post({"kind": "ops_settings", "payload": {"keys": KEYS}})
        self.assertEqual((r.code, json.loads(r.body)["error"]), (409, "reserved"))
        self._no_request_saved_same(before)
        self.conn.execute("UPDATE strategy_switch SET mode='LIVE'")
        self.conn.commit()
        self.row(kind="PARAMS", state="DONE", from_strategy="PULLBACK")
        self.assertEqual(self.post({"kind": "ops_settings", "payload": {"keys": KEYS}}).code, 202)

    def test_ops_settings_reservation_unreadable_503(self):
        self.pullback()
        before = (self.root / "alice_latest_params_PULLBACK.json").read_bytes()
        self.conn.execute("DROP TABLE strategy_switch")
        self.conn.commit()
        r = self.post({"kind": "ops_settings", "payload": {"keys": KEYS}})
        self.assertEqual((r.code, json.loads(r.body)["error"]), (503, "reservation_unknown"))
        self._no_request_saved_same(before)

    def test_ops_settings_rejected_in_live(self):
        """실계좌 입장은 엔진이 거절하므로 저장본도 바꾸지 않는다 (PO 결정 3)."""
        self.pullback()
        before = (self.root / "alice_latest_params_PULLBACK.json").read_bytes()
        r = self.post({"kind": "ops_settings", "payload": {"keys": KEYS}}, mode="LIVE")
        self.assertEqual((r.code, json.loads(r.body)["error"]), (409, "live_not_supported"))
        self._no_request_saved_same(before)

    def test_ops_settings_sell_off_changeable_1029_09(self):
        """1029-09: 「시간 밖에도 익절」 잠금 풂 — 적용본 값과 달라도 202, 요청·저장본에 바꾼 값. 형식(참/거짓)은 그대로 검사."""
        self.pullback()                                          # 적용본에 키 없음 → 지금 값 true
        off = dict(KEYS, allow_sell_during_off_hours=False)
        r = self.post({"kind": "ops_settings", "payload": {"keys": off}})
        self.assertEqual(r.code, 202, r.body)
        body = json.loads(r.body)
        self.assertTrue(body["saved_synced"])
        req = json.loads((self.data / "v2_control" / "alice" / f"req-{body['id']}.json").read_text())
        self.assertEqual(req["payload"], {"keys": off})
        saved = json.loads((self.root / "alice_latest_params_PULLBACK.json").read_text())
        self.assertIs(saved["allow_sell_during_off_hours"], False)
        # 형식 밖(참/거짓 아님)은 계속 400, 요청 없음
        self.pullback(applied={"allow_sell_during_off_hours": False})
        before = (self.root / "alice_latest_params_PULLBACK.json").read_bytes()
        for bad in (1, "false", None):
            r = self.post({"kind": "ops_settings", "payload": {"keys": dict(KEYS, allow_sell_during_off_hours=bad)}})
            self.assertEqual((r.code, json.loads(r.body)["error"]), (400, "bad_request"), bad)
        self.assertEqual((self.root / "alice_latest_params_PULLBACK.json").read_bytes(), before)

    def test_ops_settings_bad_origin_403_no_request(self):
        """다른 Origin 이면 403, 요청·저장본 그대로 (V07)."""
        self.pullback()
        before = (self.root / "alice_latest_params_PULLBACK.json").read_bytes()
        h = dict(self.cookie())
        h["Content-Type"] = "application/json"
        h["Origin"] = "https://evil.example"
        r = self.fetch("/v2/api/control", method="POST", body=json.dumps({"kind": "ops_settings",
                                                                          "payload": {"keys": KEYS}}), headers=h)
        self.assertEqual(r.code, 403)
        self._no_request_saved_same(before)

    def test_v2_control_rules(self):
        self.assertIsNone(control.ops_keys_or_none(dict(KEYS, enable_trading_hours=1)))
        self.assertEqual(control.ops_keys_or_none(KEYS), KEYS)
