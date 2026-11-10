"""1109 눌림목 실계좌 열기 — 작업 C(저장 쪽): 신버전 저장 API 의 「투자 비율(%)」 칸.

- 요청 최상위 선택 필드 investRatioPct. 입장 모드(세션)에 맞는 키(invest_ratio_pct_live / _test)에만 쓰고 다른 키는 보존.
- 요청에 칸이 없으면 기존 저장값 보존, null 이면 그 모드의 값만 지움. 범위 0.1~100(소수 첫째 자리) 밖은 400 invest_ratio_pct.
- PARAM_FIELDS 25개는 그대로(비율은 별도 선택 키).
"""
import json
import unittest

from v2 import params_schema
from tests.v2.test_api_write import SAVE_URL, VALID, WriteBase


class RatioBase(WriteBase):
    def post_ratio(self, ratio="__absent__", mode="TEST", params=None):
        body = {"params": params or VALID, "source": "binance"}
        if ratio != "__absent__":
            body["investRatioPct"] = ratio
        return self.fetch(SAVE_URL, method="POST", body=json.dumps(body), headers=self.headers(mode=mode))

    def saved(self):
        return json.loads(self.pb.read_text(encoding="utf-8"))


class TestRatioSave(RatioBase):
    def test_param_fields_still_25(self):
        self.assertEqual(len(params_schema.PARAM_FIELDS), 25)
        self.assertEqual(params_schema.RATIO_KEYS, ("invest_ratio_pct_live", "invest_ratio_pct_test"))

    def test_ratio_saved_under_session_mode_key_only(self):
        self.assertEqual(self.post_ratio(12.5, mode="LIVE").code, 200)
        d = self.saved()
        self.assertEqual(d["invest_ratio_pct_live"], 12.5)
        self.assertNotIn("invest_ratio_pct_test", d)
        self.assertEqual(self.post_ratio(30, mode="TEST").code, 200)
        d = self.saved()
        self.assertEqual((d["invest_ratio_pct_live"], d["invest_ratio_pct_test"]), (12.5, 30.0))

    def test_ratio_absent_in_request_preserves_saved(self):
        self.post_ratio(10, mode="LIVE")
        self.assertEqual(self.post_ratio(mode="LIVE").code, 200)
        self.assertEqual(self.saved()["invest_ratio_pct_live"], 10.0)
        self.assertEqual(self.post_ratio(mode="TEST").code, 200)           # 다른 모드로 저장해도 보존
        self.assertEqual(self.saved()["invest_ratio_pct_live"], 10.0)

    def test_ratio_null_clears_only_that_mode(self):
        self.post_ratio(10, mode="LIVE")
        self.post_ratio(40, mode="TEST")
        self.assertEqual(self.post_ratio(None, mode="TEST").code, 200)
        d = self.saved()
        self.assertNotIn("invest_ratio_pct_test", d)
        self.assertEqual(d["invest_ratio_pct_live"], 10.0)

    def test_ratio_out_of_range_rejected_and_file_untouched(self):
        self.post_ratio(10, mode="LIVE")
        before = self.snap()
        for bad in (0, 0.05, 100.1, -1, "abc", 5.25, True, [1], {"a": 1}):
            with self.subTest(bad=bad):
                r = self.post_ratio(bad, mode="LIVE")
                self.assertEqual(r.code, 400, bad)
                self.assertEqual(json.loads(r.body.decode()), {"error": "invest_ratio_pct"})
                self.assertEqual(self.snap(), before)
        for ok in (0.1, 100, 99.9, 1):
            with self.subTest(ok=ok):
                self.assertEqual(self.post_ratio(ok, mode="LIVE").code, 200)

    def test_nan_rejected(self):
        before = self.snap()
        r = self.fetch(SAVE_URL, method="POST", headers=self.headers(),
                       body='{"params": %s, "source": "binance", "investRatioPct": NaN}' % json.dumps(VALID))
        self.assertEqual(r.code, 400)
        self.assertEqual(self.snap(), before)

    def test_saved_file_with_ratio_passes_engine_validate(self):
        from engine import pullback_params as pbp
        self.post_ratio(7.5, mode="LIVE")
        v = pbp.validate(self.saved())
        self.assertEqual(v["invest_ratio_pct_live"], 7.5)

if __name__ == "__main__":
    unittest.main()
