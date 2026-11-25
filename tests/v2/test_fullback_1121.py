"""1121-03 투자자 수정 요청 시험 (계획 docs/plans/2026-11-21-fullback-requests/plan.md 2절).

- L2: 「설정 적용」 줄의 적용 뒤 6값 역추적(시작 조건 sha · switch 멈춤 · 사슬 검사 · 모드 섞임 · 옛 키 · 서버 모양 재현)
- L1: 평단 대비 0.5% 단계 줄(한 봉 여러 단계 · 평단 변경 · 40줄 상한 · 창 조건 · via_tentative · 같은 bar_time)
- O1·O2: 운용(ops settings_text)·홈(status pullback_settings) 6값 한 줄 — 같은 함수(control.settings_summary_text)
- A1: GET /v2/api/params/last-saved (이력 DB 없음 · 다른 사용자 · 깨짐 · 출처 없음 · differs) + SQL 상수 LIMIT·사용자 조건
바깥 연결 없음(임시 폴더 · 가짜 DB).
"""
import hashlib
import json
import sqlite3
import unittest

from tests.v2.test_api_read_pullback import PB_APPLIED, PbBase
from tests.v2.test_api_write import VALID, WriteBase
from v2 import api_read, control, db

T0 = "2026-11-20T10:00:00+09:00"


def ts(minute):
    """2026-11-20 10:00 + minute 분 (KST ISO)."""
    h, m = divmod(600 + minute, 60)
    return "2026-11-20T%02d:%02d:00+09:00" % (h, m)


def prow(rid, changed, apply="next_bar", mode="TEST", sha=None, user="alice"):
    return {"id": rid, "user_id": user, "mode": mode, "kind": "PARAMS", "params_sha256": sha,
            "note": json.dumps({"changed": changed, "apply": apply})}


# ================================================================ 6값 한 줄
class TestSettingsSummary(unittest.TestCase):
    def test_off_and_on(self):
        p = {"tp": 1.5, "sl": 5, "maxSplits": 1, "ma60MinSlope": 0.6, "ma60SlopeDrop": 0.2,
             "invest_ratio_pct_test": 100, "invest_ratio_pct_live": 10}
        self.assertEqual(control.settings_summary_text(p, "TEST"),
                         "익절 1.50 / 추적 손절 끔 / 손절 5.00 / 분할 1 / 기울기 0.60 / 둔화 0.20 / 투자비율 100%")
        self.assertTrue(control.settings_summary_text(p, "LIVE").endswith("투자비율 10%"))
        p.update(ts_on=True, ts_mode="fixed", ts_pct=30.0, sl=1.5)
        self.assertEqual(control.settings_summary_text(p, "TEST"),
                         "익절 1.50 / 추적 손절 켬 · 고정폭 · 손절폭 30% / 손절 1.50 / 분할 1 / 기울기 0.60 / 둔화 0.20 / 투자비율 100%")
        p["ts_mode"] = "ratio"
        self.assertIn("추적 손절 켬 · 비율 · 손절폭 30%", control.settings_summary_text(p, "TEST"))

    def test_effective_splits_and_missing(self):
        # 골든크로스만(maxSplits 0 + buyOnGoldenCross) = 실제 한도 1 · 투자비율 없음 = 「—」
        p = {"tp": 1, "sl": 2, "maxSplits": 0, "buyOnGoldenCross": True, "ma60MinSlope": 0, "ma60SlopeDrop": 0}
        self.assertEqual(control.settings_summary_text(p, "TEST"),
                         "익절 1.00 / 추적 손절 끔 / 손절 2.00 / 분할 1 / 기울기 0.00 / 둔화 0.00 / 투자비율 —")
        self.assertIsNone(control.settings_summary_text({}, "TEST"))
        self.assertIsNone(control.settings_summary_text(None, "TEST"))


# ================================================================ L2 역추적 (순수 함수)
class TestParamsAfterValues(unittest.TestCase):
    APPLIED = {"tp": 1.5, "sl": 5, "maxSplits": 1, "ma60MinSlope": 0.6, "ma60SlopeDrop": 0.2,
               "invest_ratio_pct_test": 100}

    def test_sha_mismatch_no_values(self):
        rows = [prow(3, {"tp": [1.0, 1.5]}, sha="other")]
        self.assertEqual(api_read.params_after_values(rows, self.APPLIED, "sha"), {})
        self.assertEqual(api_read.params_after_values(rows, None, None), {})

    def test_chain_reverts_older_values(self):
        rows = [prow(3, {"tp": [1.0, 1.5]}, sha="s"), prow(2, {"tp": [2.0, 1.0], "sl": [3, 5]})]
        out = api_read.params_after_values(rows, self.APPLIED, "s")
        self.assertEqual(out[3]["tp"], 1.5)
        self.assertEqual((out[2]["tp"], out[2]["sl"]), (1.0, 5))

    def test_switch_row_stops_even_partial(self):
        rows = [prow(4, {"tp": [1.0, 1.5]}, sha="s"), prow(3, {"tp": [2.0, 1.0]}, apply="switch"),
                prow(2, {"sl": [9, 5]})]
        out = api_read.params_after_values(rows, self.APPLIED, "s")
        self.assertEqual(sorted(out), [3, 4])
        self.assertEqual(out[3]["tp"], 1.0)

    def test_all_old_none_row_does_not_stop(self):
        # 서버 6행 모양: 추적 손절만 켬(키가 없다가 생김 — 구 값 모두 None). 여기서 멈추면 옛 행 값이 빠진다(F11)
        applied = dict(self.APPLIED, ts_on=True, ts_mode="fixed", ts_pct=30.0)
        rows = [prow(6, {"ts_on": [None, True], "ts_mode": [None, "fixed"], "ts_pct": [None, 30.0]}, sha="s"),
                prow(5, {"tp": [2.0, 1.5]})]
        out = api_read.params_after_values(rows, applied, "s")
        self.assertEqual(sorted(out), [5, 6])
        self.assertNotIn("ts_on", out[5])     # 그 전엔 추적 손절 끔(키 없음)
        self.assertEqual(out[5]["tp"], 1.5)

    def test_chain_break_blanks_that_row_and_older(self):
        rows = [prow(4, {"tp": [1.0, 1.5]}, sha="s"), prow(3, {"tp": [2.0, 9.9]}), prow(2, {"sl": [9, 5]})]
        out = api_read.params_after_values(rows, self.APPLIED, "s")
        self.assertEqual(sorted(out), [4])

    def test_modes_mixed_one_chain(self):
        # 적용본은 사용자당 1개 — TEST→LIVE→TEST 행을 모드 상관없이 한 사슬로 따라간다
        rows = [prow(4, {"tp": [1.0, 1.5]}, mode="TEST", sha="s"), prow(3, {"sl": [3, 5]}, mode="LIVE"),
                prow(2, {"tp": [2.0, 1.0]}, mode="TEST")]
        out = api_read.params_after_values(rows, self.APPLIED, "s")
        self.assertEqual(sorted(out), [2, 3, 4])
        self.assertEqual((out[2]["tp"], out[2]["sl"]), (1.0, 3))

    def test_type_change_is_break(self):
        # 엔진 diff 는 타입이 다르면 바뀐 것으로 본다 — 신 값 1(int) 인데 지금 값 1.5 가 아니면 끊김
        rows = [prow(3, {"tp": [1, 1.5]}, sha="s"), prow(2, {"tp": [2, "1"]})]
        out = api_read.params_after_values(rows, self.APPLIED, "s")
        self.assertEqual(sorted(out), [3])

    def test_server_shape_rows_2_to_8(self):
        """서버 모양(계획 F10~F12): 2 switch 전체 · 3 비율 10→100 · 4 ma200p 등 · 5 비율 100→10 · 6 추적 손절만 켬 ·
        7 비율 10→100 · 8 tp 등(가장 새, sha 일치). 6행에서 멈추지 않고 2행까지 값이 나온다."""
        full = {"tp": 2.0, "sl": 3, "maxSplits": 1, "ma60MinSlope": 0.5, "ma60SlopeDrop": 0.1, "ma200p": 200}
        applied = {"tp": 1.5, "sl": 1.5, "maxSplits": 1, "ma60MinSlope": 0.6, "ma60SlopeDrop": 0.2, "ma200p": 200,
                   "invest_ratio_pct_test": 100, "ts_on": True, "ts_mode": "fixed", "ts_pct": 30.0}
        rows = [
            prow(8, {"tp": [2.0, 1.5], "sl": [3, 1.5], "ma60MinSlope": [0.5, 0.6], "ma60SlopeDrop": [0.1, 0.2]}, sha="s"),
            prow(7, {"invest_ratio_pct_test": [10, 100]}),
            prow(6, {"ts_on": [None, True], "ts_mode": [None, "fixed"], "ts_pct": [None, 30.0]}),
            prow(5, {"invest_ratio_pct_test": [100, 10], "ma200p": [201, 200]}),
            prow(4, {"ma200p": [200, 201]}),
            prow(3, {"invest_ratio_pct_test": [10, 100]}),
            prow(2, {k: [None, v] for k, v in dict(full, invest_ratio_pct_test=10).items()}, apply="switch"),
        ]
        out = api_read.params_after_values(rows, applied, "s")
        self.assertEqual(sorted(out), [2, 3, 4, 5, 6, 7, 8])
        self.assertEqual(out[4]["ma200p"], 201)
        self.assertEqual(out[3]["invest_ratio_pct_test"], 100)
        self.assertEqual(out[2]["invest_ratio_pct_test"], 10)
        self.assertNotIn("ts_on", out[5])
        self.assertEqual(control.settings_summary_text(out[2], "TEST"),
                         "익절 2.00 / 추적 손절 끔 / 손절 3.00 / 분할 1 / 기울기 0.50 / 둔화 0.10 / 투자비율 10%")


# ================================================================ L1 0.5% 단계 (순수 함수)
def buy(rid, minute, rnd=1):
    return {"id": rid, "timestamp": ts(minute), "type": "BUY", "meta": json.dumps({"split_round": rnd})}


def hts_buy(rid, minute, reason):
    """엔진이 남기는 외부 매수 행 모양(type BUY · reason HTS_BUY|HTS_BUY_ADD · meta 없음)."""
    return {"id": rid, "timestamp": ts(minute), "type": "BUY", "reason": reason, "meta": None}


def sell_trade(rid, minute, typ="SELL"):
    return {"id": rid, "timestamp": ts(minute), "type": typ, "meta": None}


def ev(rid, minute, price, avg=1000.0, tentative=False, bar=None):
    ck = {"strategy": "PULLBACK", "price": price, "avg": avg, "via_tentative": tentative}
    return {"id": rid, "timestamp": ts(minute), "bar_time": bar or ts(minute), "checks": json.dumps(ck)}


def texts(items):
    return [it[3]["text"] for it in sorted(items, key=lambda it: (it[0], it[1], it[2]))]


class TestParamsChangeLabels(unittest.TestCase):
    """1121-03 ㉠ (11/25 승인): 「설정 적용」 줄에 날 키 이름(ts_ 등)이 보이지 않는다."""

    def test_trailing_keys_korean(self):
        note = {"changed": {"ts_on": [False, True], "ts_mode": [None, "fixed"], "ts_pct": [None, 30]},
                "apply": "next_bar"}
        t = api_read.params_change_text(json.dumps(note))
        self.assertEqual(t, "설정 적용 · 추적 손절 끔→켬 · 추적 손절 방식 고정폭 · 손절폭 30% · 다음 봉부터")
        self.assertNotIn("ts_", t)
        t2 = api_read.params_change_text(json.dumps(
            {"changed": {"ts_on": [True, False], "ts_mode": ["fixed", "ratio"], "ts_pct": [30.0, 12.5]}}))
        self.assertEqual(t2, "설정 적용 · 추적 손절 켬→끔 · 추적 손절 방식 고정폭→비율 · 손절폭 30→12.5%")

    def test_trailing_missing_key_is_off_and_never_hidden(self):
        # 1121-03 ㉠ (11/25 화면 확인 뒤 승인): 서버 11/24 05:05 · 05:08 줄과 같은 모양(칸 없음 → 생김/없어짐)
        off = {"changed": {"slStreakCooldownHours": [6, 6.5], "invest_ratio_pct_live": [10, 100],
                           "ts_on": [True, None], "ts_mode": ["fixed", None], "ts_pct": [30.0, None]},
               "apply": "next_bar"}
        self.assertEqual(api_read.params_change_text(json.dumps(off)),
                         "설정 적용 · 연속 SL 중단 지속시간(시간) 6→6.5 · 투자비율(실계좌) 10→100% · "
                         "추적 손절 켬→끔 · 다음 봉부터")
        on = {"changed": {"slStreakCooldownHours": [6.5, 6], "ts_on": [None, True], "ts_mode": [None, "fixed"],
                          "ts_pct": [None, 30.0]}, "apply": "next_bar"}
        self.assertEqual(api_read.params_change_text(json.dumps(on)),
                         "설정 적용 · 연속 SL 중단 지속시간(시간) 6.5→6 · 추적 손절 끔→켬 · "
                         "추적 손절 방식 고정폭 · 손절폭 30% · 다음 봉부터")
        # 다른 키가 3개 넘어도 추적 손절 3키는 숨기지 않고, 「외 n개」는 다른 키만 센다
        many = {"changed": {"tp": [5, 4], "sl": [3, 2], "ma60p": [60, 50], "fee": [0.05, 0.1],
                            "ts_on": [False, True], "ts_mode": [None, "ratio"], "ts_pct": [None, 50]}}
        t = api_read.params_change_text(json.dumps(many))
        self.assertEqual(t, "설정 적용 · 익절 TP 5→4% · 손절 SL 3→2% · 60선 기간 60→50 · "
                            "추적 손절 끔→켬 · 추적 손절 방식 비율 · 손절폭 50% · 외 1개")
        self.assertNotIn("없음", t)
        # 칸 없음 ↔ 끔 은 바뀐 것이 아니다
        self.assertEqual(api_read.params_change_text(json.dumps({"changed": {"ts_on": [None, False]}})),
                         "설정 적용")

    def test_mode_words_same_as_six_value_line(self):
        six = control.settings_summary_text({"ts_on": True, "ts_mode": "fixed", "ts_pct": 30}, "TEST")
        self.assertIn("추적 손절 켬 · 고정폭 · 손절폭 30%", six)
        self.assertIn(api_read._fmt_param("ts_mode", "fixed"), six)

    def test_ratio_keys_korean(self):
        t = api_read.params_change_text(json.dumps({"changed": {"invest_ratio_pct_test": [100.0, 50.0]}}))
        self.assertEqual(t, "설정 적용 · 투자비율(모의) 100→50%")

    def test_every_engine_key_has_label(self):
        # 엔진이 변경 기록(changed)에 쓰는 모든 키(engine/pullback_apply ALL_KEYS = 24키·거래 시간·투자 비율·추적 손절)
        # + 옛 기록의 200선 기울기 2키에 한국어 이름이 있다
        from engine import pullback_params as pbp
        keys = (*pbp.PULLBACK_KEYS, *pbp.OPTIONAL_KEYS, *pbp.RATIO_KEYS, *pbp.TRAILING_KEYS, *pbp.LEGACY_KEYS)
        missing = [k for k in keys if k not in api_read.PARAM_KEY_LABELS]
        self.assertEqual(missing, [])


class TestStepItems(unittest.TestCase):
    def test_steps_up_down_and_jump(self):
        trades = [buy(1, 0)]
        sells = [ev(100, -5, 990.0),                       # 이전 보유(창이 첫 매수보다 이름 — 창 조건 통과)
                 ev(1, 1, 1003), ev(2, 2, 1006), ev(3, 3, 1004), ev(4, 4, 1016), ev(5, 5, 994), ev(6, 6, 989)]
        out = api_read._step_items(trades, list(reversed(sells)))
        self.assertEqual(texts(out), ["평단 대비 +0.5% (종가 1,006)", "평단 대비 +1.0%→+1.5% (종가 1,016)",
                                      "평단 대비 -0.5% (종가 994)", "평단 대비 -1.0% (종가 989)"])

    def test_avg_change_restarts(self):
        trades = [buy(1, 0), buy(2, 3, rnd=2)]
        sells = [ev(100, -5, 990.0), ev(1, 1, 1006), ev(2, 4, 1006, avg=1010.0), ev(3, 5, 1016, avg=1010.0)]
        self.assertEqual(texts(api_read._step_items(trades, sells)),
                         ["평단 대비 +0.5% (종가 1,006)", "평단 변경 1,000 → 1,010", "평단 대비 +0.5% (종가 1,016)"])

    def test_tentative_skipped_and_same_bar_newest(self):
        trades = [buy(1, 0)]
        sells = [ev(100, -5, 990.0), ev(1, 1, 1020, tentative=True), ev(2, 2, 1003, bar=ts(2)),
                 ev(3, 2, 1011, bar=ts(2))]
        # 잠정 행(+2.0%)은 건너뛰고, 같은 봉은 가장 새 id(+1.1%) — 한 봉에 두 단계를 넘어 「+0.5%→+1.0%」
        self.assertEqual(texts(api_read._step_items(trades, sells)), ["평단 대비 +0.5%→+1.0% (종가 1,011)"])

    def test_window_starts_after_first_buy_no_lines(self):
        # 첫 매수 체결이 체결 창 안에 있어도 매도 판단 창이 그보다 늦게 시작하면(1200행이 다 참) 그 보유는 줄 0개
        trades = [buy(1, 0)]
        sells = [ev(i, 10 + i, 1000 + i) for i in range(1, api_read.LOGS_READ_MAX + 1)]
        self.assertEqual(api_read._step_items(trades, sells), [])

    def test_short_table_means_full_read(self):
        # 표에 30행뿐(1200 미만 = 전체 읽음) → 창 조건 통과
        trades = [buy(1, 0)]
        sells = [ev(i, i, 1000 + 6 * i) for i in range(1, 31)]
        self.assertTrue(len(api_read._step_items(trades, sells)) > 0)

    def test_external_buy_start_no_lines(self):
        # 첫 매수 체결을 체결 창에서 못 찾음(외부 매수로 시작) → 줄 0개 · 분할 2회차부터 보이는 보유도 0개
        sells = [ev(100, -5, 990.0), ev(1, 1, 1006)]
        self.assertEqual(api_read._step_items([], sells), [])
        self.assertEqual(api_read._step_items([buy(1, 0, rnd=2)], sells), [])

    def test_hts_buy_start_then_bot_buy_no_lines(self):
        # 엔진이 남기는 실제 모양: 외부 매수 = type 'BUY' · reason 'HTS_BUY'|'HTS_BUY_ADD' · meta 없음
        # (engine/order_reconciler.py insert_trade_audit(kind="BUY", reason=reason_str)).
        # 보유 없음에서 외부 매수로 시작 → 그 뒤 봇 매수(회차 1 또는 회차 없음)가 와도 다음 매도까지 줄 0개
        sells = [ev(100, -5, 990.0), ev(1, 3, 1006), ev(2, 4, 1016)]
        for hts in ("HTS_BUY", "HTS_BUY_ADD"):
            for bot in (buy(2, 2, rnd=1), {"id": 2, "timestamp": ts(2), "type": "BUY", "reason": None, "meta": None}):
                trades = [hts_buy(1, 0, hts), bot]
                self.assertEqual(api_read._step_items(trades, sells), [], (hts, bot["meta"]))
        # 매도로 끝난 뒤의 새 봇 보유는 다시 줄이 나온다
        trades = [hts_buy(1, 0, "HTS_BUY"), sell_trade(2, 1), buy(3, 2)]
        self.assertEqual(texts(api_read._step_items(trades, sells)),
                         ["평단 대비 +0.5% (종가 1,006)", "평단 대비 +1.0%→+1.5% (종가 1,016)"])

    def test_window_mid_holding_hts_buy_add_no_meta(self):
        # 창이 보유 중간에서 시작: 맨 앞 체결이 외부 추가 매수(HTS_BUY_ADD, meta 없음) → 그 뒤 봇 매수가 와도 줄 0개
        sells = [ev(100, -5, 990.0), ev(1, 3, 1006), ev(2, 4, 1016)]
        trades = [hts_buy(1, 0, "HTS_BUY_ADD"), buy(2, 2, rnd=1)]
        self.assertEqual(api_read._step_items(trades, sells), [])

    def test_force_buy_starts_holding(self):
        # 강제 매수(reason force_buy, 회차 없음)는 봇이 낸 매수 — 보유 시작으로 본다(11/24 PO 결정)
        sells = [ev(100, -5, 990.0), ev(1, 3, 1006)]
        trades = [{"id": 1, "timestamp": ts(0), "type": "BUY", "reason": "force_buy", "meta": None}]
        self.assertEqual(texts(api_read._step_items(trades, sells)), ["평단 대비 +0.5% (종가 1,006)"])

    def test_avg_change_sorts_below_steps_same_bar(self):
        # 같은 봉에서 평단 변경과 단계 줄이 함께 나면 최신순 화면(순서 값 작은 것 위)에서 단계 줄이 위
        trades = [buy(1, 0), buy(2, 2, rnd=2)]
        sells = [ev(100, -5, 990.0), ev(1, 1, 1001), ev(2, 2, 1020, avg=1010.0)]
        out = [it for it in api_read._step_items(trades, sells) if it[3]["timestamp"] == ts(2)]
        self.assertEqual(len(out), 2)
        step = [it for it in out if it[3]["text"].startswith("평단 대비")][0]
        avgc = [it for it in out if it[3]["text"].startswith("평단 변경")][0]
        self.assertLess(step[1], avgc[1])

    def test_holding_ends_at_sell(self):
        trades = [buy(1, 0), sell_trade(2, 3), buy(3, 10)]
        sells = [ev(100, -5, 990.0), ev(1, 1, 1006), ev(2, 11, 1012, avg=1010.0)]
        # 둘째 보유(10분 매수)는 새 평단 1,010 기준 +0.2% — 단계 아님. 첫 보유 줄만
        self.assertEqual(texts(api_read._step_items(trades, sells)), ["평단 대비 +0.5% (종가 1,006)"])

    def test_cap_40_keeps_latest(self):
        trades = [buy(1, 0)]
        sells = [ev(100, -5, 990.0)]
        # 위아래로 번갈아 새 단계를 넘는다: +0.5, -0.5, +1.0, -1.0 … → 50줄
        for i in range(1, 51):
            k = (i + 1) // 2
            price = 1000 * (1 + (0.005 * k + 0.0001) * (1 if i % 2 else -1))
            sells.append(ev(i, i, round(price, 4)))
        out = texts(api_read._step_items(trades, sells))
        self.assertEqual(len(out), 41)
        self.assertEqual(out[0], "평단 대비 단계 줄 앞 10줄 생략")
        self.assertTrue(out[-1].startswith("평단 대비 -12.5%"), out[-1])


# ================================================================ API
class TestFullbackApi(PbBase):
    def setup_pb(self, **over):
        self.pb_db()
        p = self.set_pb(**over)
        raw = (self.root / "alice_applied_params_PULLBACK.json").read_bytes()
        return p, hashlib.sha256(raw).hexdigest()

    def params_row(self, changed, sha=None, apply="next_bar", mode="TEST", at="2026-11-20T09:00:00+09:00"):
        self.conn.execute(
            "INSERT INTO strategy_switch(user_id,mode,kind,from_strategy,to_strategy,params_sha256,state,"
            "requested_at,done_at,note) VALUES ('alice',?,'PARAMS','PULLBACK','PULLBACK',?,'DONE',?,?,?)",
            (mode, sha, at, at, json.dumps({"changed": changed, "apply": apply})))
        self.conn.commit()

    def test_logs_params_line_with_after_values(self):
        p, sha = self.setup_pb(ma60MinSlope=0.6, ma60SlopeDrop=0.2, invest_ratio_pct_test=100)
        self.params_row({"tp": [4, 5]}, apply="immediate", at="2026-11-20T08:00:00+09:00")
        self.params_row({"tp": [5, 6]}, at="2026-11-20T09:00:00+09:00")
        self.params_row({"tp": [6, 5]}, sha=sha, at="2026-11-20T10:00:00+09:00")
        t = self.audit_texts()
        self.assertEqual(t[0], "설정 적용 · 익절 TP 6→5% · 다음 봉부터 — 적용 뒤: 익절 5.00 / 추적 손절 끔 / 손절 3.00 / "
                               "분할 5 / 기울기 0.60 / 둔화 0.20 / 투자비율 100%")
        self.assertIn("적용 뒤: 익절 6.00", t[1])
        self.assertIn("적용 뒤: 익절 5.00", t[2])

    def test_logs_params_no_values_when_sha_differs(self):
        self.setup_pb()
        self.params_row({"tp": [6, 5]}, sha="nope")
        self.assertEqual(self.audit_texts(), ["설정 적용 · 익절 TP 6→5% · 다음 봉부터"])

    def test_logs_entry_mode_only_ratio_by_row_mode(self):
        p, sha = self.setup_pb(invest_ratio_pct_test=100, invest_ratio_pct_live=10, ma60MinSlope=0, ma60SlopeDrop=0)
        self.params_row({"sl": [2, 3]}, mode="LIVE", at="2026-11-20T08:00:00+09:00")
        self.params_row({"tp": [4, 5]}, sha=sha, mode="TEST", at="2026-11-20T09:00:00+09:00")
        t_test, t_live = self.audit_texts("TEST"), self.audit_texts("LIVE")
        self.assertEqual(len(t_test), 1)
        self.assertTrue(t_test[0].endswith("투자비율 100%"))
        self.assertEqual(len(t_live), 1)
        self.assertTrue(t_live[0].endswith("투자비율 10%"), t_live[0])

    def test_logs_old_key_row_slope_dash(self):
        p, sha = self.setup_pb(ma60MinSlope=0.6, ma60SlopeDrop=0.2, minSlope=0.2)
        self.params_row({"minSlope": [0.1, 0.2]}, sha=sha)
        self.assertIn("기울기 — / 둔화 —", self.audit_texts()[0])

    def test_logs_step_lines(self):
        self.setup_pb()
        self.trade("2026-11-20T10:00:00+09:00", "BUY", meta={"split_round": 1}, entry=1000.0)
        for i, price in enumerate((1003.0, 1006.0, 994.0), start=1):
            at = "2026-11-20T10:%02d:00+09:00" % (i * 3)
            self.pb_eval("audit_sell_eval", at, ["WAIT_PULLBACK"], price=price, avg=1000.0, via_tentative=False)
        t = self.audit_texts()
        self.assertIn("평단 대비 +0.5% (종가 1,006)", t)
        self.assertIn("평단 대비 -0.5% (종가 994)", t)

    def test_ops_and_status_same_line(self):
        self.setup_pb(ma60MinSlope=0.6, ma60SlopeDrop=0.2, invest_ratio_pct_test=100, ts_on=True, ts_mode="fixed",
                      ts_pct=30.0)
        want = "익절 5.00 / 추적 손절 켬 · 고정폭 · 손절폭 30% / 손절 3.00 / 분할 5 / 기울기 0.60 / 둔화 0.20 / 투자비율 100%"
        code, st = self.get_json("/v2/api/status")
        self.assertEqual(code, 200)
        self.assertEqual(st["pullback_settings"], want)
        code, ops = self.get_json("/v2/api/ops")
        self.assertEqual(code, 200)
        self.assertEqual(ops["settings_text"], want)

    def test_status_ema_has_no_settings_key(self):
        self.make_live_db()
        self.set_strategy("EMA")
        code, st = self.get_json("/v2/api/status")
        self.assertNotIn("pullback_settings", st)


LAST_URL = "/v2/api/params/last-saved"


class TestLastSaved(WriteBase):
    def get(self, user="alice"):
        r = self.fetch(LAST_URL, headers=self.cookie(user=user))
        return r.code, json.loads(r.body.decode())

    def add_hist(self, params, note="source=binance", user="alice", saved_at="2026-11-24T05:08:27.123+09:00"):
        conn = db.open_v2hist(user)
        try:
            conn.execute("INSERT INTO v2_settings_history(user_id,saved_at,source_page,strategy_type,params_json,"
                         "note) VALUES (?,?,?,?,?,?)",
                         (user, saved_at, "v2_backtester", "PULLBACK",
                          params if isinstance(params, str) else json.dumps(params), note))
            conn.commit()
        finally:
            conn.close()

    def write_applied(self, d):
        db.applied_params_path(self.USER).write_text(d if isinstance(d, str) else json.dumps(d), encoding="utf-8")

    def test_no_history_db_not_created(self):
        code, b = self.get()
        self.assertEqual((code, b), (200, {"exists": False}))
        self.assertFalse(db.v2hist_path(self.USER).exists())

    def test_after_save_roundtrip(self):
        self.assertEqual(self.post(VALID).code, 200)
        code, b = self.get()
        self.assertEqual(code, 200)
        self.assertTrue(b["exists"])
        self.assertEqual(b["source"], "binance")
        self.assertEqual(b["params"]["symbol"], "JTOUSDT")
        self.assertEqual(b["params"]["tp"], 1.0)
        self.assertEqual(b["trailing"], {"ts_on": False})
        self.assertRegex(b["saved_at_text"], r"^\d\d\.\d\d\.\d\d \d\d:\d\d$")
        self.assertIsNone(b["differs_from_applied"])        # 적용본 없음 → null

    def test_other_user_rows_not_read(self):
        self.add_hist(dict(VALID, tp=2.5), user="alice")
        conn = db.open_v2hist(self.USER)
        try:   # 같은 파일에 다른 사용자 행이 더 새로 있어도 읽지 않는다
            conn.execute("INSERT INTO v2_settings_history(user_id,saved_at,source_page,strategy_type,params_json,note) "
                         "VALUES ('bob','2026-11-25T00:00:00+09:00','v2_backtester','PULLBACK',?,'source=binance')",
                         (json.dumps(dict(VALID, tp=9.0)),))
            conn.commit()
        finally:
            conn.close()
        code, b = self.get()
        self.assertEqual(b["params"]["tp"], 2.5)

    def test_broken_rows(self):
        for params, note in (("{oops", "source=binance"), ({"tp": 1}, "source=binance"),
                             (VALID, None), (VALID, "source=kraken"), (dict(VALID, symbol="KRW-JTO"), "source=binance")):
            db.v2hist_path(self.USER).unlink(missing_ok=True)
            self.add_hist(params, note=note)
            code, b = self.get()
            self.assertEqual((code, b), (200, {"exists": False, "broken": True}), (params, note))

    def test_upbit_history(self):
        self.add_hist(dict(VALID, symbol="krw-jto"), note="source=upbit")
        code, b = self.get()
        self.assertEqual((b["source"], b["params"]["symbol"]), ("upbit", "KRW-JTO"))
        self.assertEqual(b["saved_at_text"], "26.11.24 05:08")

    def test_differs(self):
        from v2 import params_schema
        self.add_hist(VALID)
        eng = params_schema.to_engine_file(params_schema.validate_params(VALID, "binance"), "KRW-ZRO")
        # 같음(종목은 비교하지 않음 · 투자비율만 다름도 같음)
        self.write_applied(dict(eng, ticker="KRW-ABC", invest_ratio_pct_test=10))
        self.assertIs(self.get()[1]["differs_from_applied"], False)
        # 화면 값 하나 다름
        self.write_applied(dict(eng, tp=9.0))
        self.assertIs(self.get()[1]["differs_from_applied"], True)
        # 추적 손절만 저장하고 적용 안 함 → 다름
        self.pb.write_text(json.dumps(dict(eng, ts_on=True, ts_mode="ratio", ts_pct=50.0)), encoding="utf-8")
        self.write_applied(eng)
        code, b = self.get()
        self.assertEqual(b["trailing"], {"ts_on": True, "ts_mode": "ratio", "ts_pct": 50.0})
        self.assertIs(b["differs_from_applied"], True)
        # 적용본 깨짐 → null
        self.write_applied("{oops")
        self.assertIsNone(self.get()[1]["differs_from_applied"])

    def test_needs_login(self):
        r = self.fetch(LAST_URL)
        self.assertIn(r.code, (401, 403))

    def test_sql_const_limit_and_user(self):
        self.assertRegex(db.SQL_LAST_HISTORY_FULL, db._LIMIT_RE)
        self.assertIn("WHERE user_id=?", db.SQL_LAST_HISTORY_FULL)
        self.assertNotIn(db.SQL_LAST_HISTORY_FULL, api_read.ALL_SQL)


if __name__ == "__main__":
    unittest.main()
