"""1110-01 눌림목 추적 손절 — 신버전 저장 API 의 선택 필드 trailing({ts_on, ts_mode, ts_pct}).

- 켬이면 적용본에 3키(ts_on·ts_mode·ts_pct)를 쓴다. 끔이면 3키를 지운다(옛 코드로 되돌리기 쉬움).
- 요청에 trailing 이 없으면(옛 화면) 기존 저장값을 그대로 둔다.
- 틀린 값은 400 invalid_param field=trailing, 파일은 그대로.
- 서버(v2/params_schema)와 엔진(engine/pullback_params)의 검사 규칙이 같다.
"""
import json
import unittest

from engine import pullback_params as pbp
from v2 import params_schema
from tests.v2.test_api_write import SAVE_URL, VALID, WriteBase

ON = {"ts_on": True, "ts_mode": "fixed", "ts_pct": 90}
OFF = {"ts_on": False, "ts_mode": "ratio", "ts_pct": 50}


class TrailBase(WriteBase):
    def post_ts(self, trailing="__absent__", mode="TEST"):
        body = {"params": VALID, "source": "binance"}
        if trailing != "__absent__":
            body["trailing"] = trailing
        return self.fetch(SAVE_URL, method="POST", body=json.dumps(body), headers=self.headers(mode=mode))

    def saved(self):
        return json.loads(self.pb.read_text(encoding="utf-8"))


class TestTrailingSave(TrailBase):
    def test_param_fields_still_25(self):
        self.assertEqual(len(params_schema.PARAM_FIELDS), 25)
        self.assertEqual(params_schema.TRAILING_KEYS, pbp.TRAILING_KEYS)
        self.assertEqual((params_schema.TS_MODES, params_schema.TS_PCT_MIN, params_schema.TS_PCT_MAX),
                         (pbp.TS_MODES, pbp.TS_PCT_MIN, pbp.TS_PCT_MAX))

    def test_on_writes_three_keys_and_engine_accepts(self):
        self.assertEqual(self.post_ts(ON).code, 200)
        d = self.saved()
        self.assertEqual({k: d[k] for k in pbp.TRAILING_KEYS}, {"ts_on": True, "ts_mode": "fixed", "ts_pct": 90.0})
        v = pbp.validate(d)
        self.assertEqual((v["ts_on"], v["ts_mode"], v["ts_pct"]), (True, "fixed", 90.0))

    def test_off_removes_keys(self):
        self.post_ts(ON)
        self.assertEqual(self.post_ts(OFF).code, 200)
        d = self.saved()
        for k in pbp.TRAILING_KEYS:
            self.assertNotIn(k, d)
        self.assertNotIn("ts_on", pbp.validate(d))   # 엔진 결과에도 없음 = 옛 모양

    def test_absent_preserves_saved(self):
        self.post_ts(ON)
        self.assertEqual(self.post_ts().code, 200)
        self.assertEqual(self.saved()["ts_mode"], "fixed")

    def test_bad_rejected_file_untouched(self):
        self.post_ts(ON)
        before = self.snap()
        bads = [None, {}, {"ts_on": True}, {**ON, "ts_pct": 0.5}, {**ON, "ts_pct": 100.5}, {**ON, "ts_pct": 5.25},
                {**ON, "ts_pct": True}, {**ON, "ts_pct": "50"}, {**ON, "ts_mode": "peak"}, {**ON, "ts_on": "yes"},
                [1], "on"]
        for bad in bads:
            with self.subTest(bad=bad):
                r = self.post_ts(bad)
                self.assertEqual(r.code, 400, bad)
                self.assertEqual(json.loads(r.body)["field"], "trailing")
                self.assertEqual(self.snap(), before)


class TestSameRules(unittest.TestCase):
    """서버·엔진 검사 규칙이 같은 입력에서 같은 결과(통과 값 또는 실패)."""

    CASES = [ON, OFF, {"ts_on": True, "ts_mode": "ratio", "ts_pct": 1}, {"ts_on": True, "ts_mode": "ratio", "ts_pct": 100},
             {"ts_on": True, "ts_mode": "ratio", "ts_pct": 33.3}, {"ts_on": True, "ts_mode": "ratio", "ts_pct": 0.9},
             {"ts_on": True, "ts_mode": "ratio", "ts_pct": 33.33}, {"ts_on": 1, "ts_mode": "ratio", "ts_pct": 50},
             {"ts_on": True, "ts_mode": "x", "ts_pct": 50}, {"ts_on": True, "ts_mode": "ratio"},
             {"ts_on": True, "ts_mode": "ratio", "ts_pct": float("nan")}, {}]

    def test_same(self):
        for c in self.CASES:
            with self.subTest(c=c):
                def run(f):
                    try:
                        return ("ok", f(dict(c)))
                    except ValueError:
                        return ("err", None)
                self.assertEqual(run(params_schema.valid_trailing), run(pbp.valid_trailing))


if __name__ == "__main__":
    unittest.main()
