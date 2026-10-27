"""
2차 T2: PULLBACK 전용 로더 (결정 D9) 시험.

경우별 표 12줄(기동 때 적용본 x 사본 x 보유)과 적용·읽기 규칙을 실제 함수 호출과
파일 결과(권한 600, .tmp 잔여 없음, 바이트 불변)로 단언한다. 임시 폴더에서만 돈다.

실행:
    python3 -m unittest tests.regressions.test_r_2026_10_28_p3_t2_pullback_loader -v
"""
from __future__ import annotations

import ast
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from engine import pullback_params as pp  # noqa: E402

USER = "tuser"
SAVED = f"{USER}_latest_params_PULLBACK.json"
APPLIED = f"{USER}_applied_params_PULLBACK.json"
LAST_GOOD = f"{USER}_applied_params_PULLBACK.last_good.json"


def good(**over):
    d = {
        "ticker": "KRW-JTO", "interval": "minute3", "maType": "ema",
        "ma60p": 60, "ma200p": 200, "pullbackP": 20, "slopeLB": 5,
        "minSlope": 0.0, "slopeDrop": 0.5, "buyOnGoldenCross": True,
        "maxSplits": 5, "maxPullbackBuys": 2, "tp": 5.0, "sl": 3.0,
        "deadcross": True, "compounding": False, "capital": 3000000, "fee": 0.05,
    }
    d.update(over)
    return d


def put(name, obj_or_bytes):
    data = obj_or_bytes if isinstance(obj_or_bytes, bytes) else json.dumps(obj_or_bytes).encode()
    with open(name, "wb") as f:
        f.write(data)
    os.chmod(name, 0o600)


def mode(name):
    return stat.S_IMODE(os.stat(name).st_mode)


class Base(unittest.TestCase):
    def setUp(self):
        self._cwd = os.getcwd()
        self._tmp = tempfile.TemporaryDirectory()
        os.chdir(self._tmp.name)
        p = patch.object(pp, "_notify_critical")
        self.notify = p.start()
        self.addCleanup(p.stop)

    def tearDown(self):
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def leftovers(self):
        return [n for n in os.listdir(".") if n.endswith(".tmp")]


class TestBootCases(Base):
    """경우별 표 12줄."""

    def _boot(self, holding):
        with self.assertLogs(pp.logger, level="DEBUG") as cm:
            res = pp.load_for_boot(USER, holding=holding)
        return res, "\n".join(cm.output)

    def _applied_ok(self, **kw):
        put(APPLIED, good(**kw))

    def test_boot_case_01(self):  # 정상, 사본 있음, 미보유
        self._applied_ok(tp=5.0)
        put(LAST_GOOD, good(tp=1.0))
        (params, src), log = self._boot(False)
        self.assertEqual((src, params["tp"]), ("applied", 5.0))
        self.assertIn("[PULLBACK-PARAMS] source=applied", log)
        self.notify.assert_not_called()

    def test_boot_case_02(self):  # 정상, 사본 있음, 보유
        self._applied_ok()
        put(LAST_GOOD, good(tp=1.0))
        (params, src), log = self._boot(True)
        self.assertEqual(src, "applied")
        self.assertIn("source=applied", log)
        self.notify.assert_not_called()

    def test_boot_case_03(self):  # 정상, 사본 없음, 미보유
        self._applied_ok()
        (params, src), log = self._boot(False)
        self.assertEqual(src, "applied")
        self.assertIn("[PULLBACK-PARAMS] source=applied", log)
        self.notify.assert_not_called()

    def test_boot_case_04(self):  # 정상, 사본 없음, 보유
        self._applied_ok()
        (params, src), log = self._boot(True)
        self.assertEqual(src, "applied")
        self.assertIsNotNone(params)
        self.assertIn("[PULLBACK-PARAMS] source=applied", log)
        self.notify.assert_not_called()

    def test_boot_case_10_applied_empty_last_good_corrupt(self):
        put(APPLIED, b"")
        put(LAST_GOOD, b"{bad")
        with self.assertLogs(pp.logger, level="ERROR") as cm:
            res = pp.load_for_boot(USER, holding=True)
        self.assertEqual(res, (None, "none"))
        self.assertTrue(any("[PULLBACK-PARAMS]" in m for m in cm.output))
        self.assertIn("보유 중 새 전략 설정 없음", str(self.notify.call_args))

    def test_boot_case_05(self):  # 없음/0바이트, 사본 정상, 미보유
        put(LAST_GOOD, good(tp=1.0))
        (params, src), log = self._boot(False)
        self.assertEqual((src, params["tp"]), ("last_good", 1.0))
        self.assertIn("[PULLBACK-PARAMS] fallback reason=missing", log)
        self.notify.assert_called()
        # 0바이트도 같은 결과
        put(APPLIED, b"")
        (params, src), log = self._boot(False)
        self.assertEqual(src, "last_good")
        self.assertIn("reason=missing", log)

    def test_boot_holding_corrupt_applied_uses_last_good(self):  # 6
        put(APPLIED, b"")
        put(LAST_GOOD, good(tp=1.0))
        (params, src), log = self._boot(True)
        self.assertEqual((src, params["tp"]), ("last_good", 1.0))
        self.assertIn("fallback reason=missing", log)
        self.notify.assert_called()

    def test_boot_case_07(self):  # 깨짐, 사본 정상, 미보유
        put(APPLIED, b'{"ticker": "KRW-J')
        put(LAST_GOOD, good(tp=1.0))
        (params, src), log = self._boot(False)
        self.assertEqual(src, "last_good")
        self.assertIn("fallback reason=json", log)
        self.notify.assert_called()
        # type / field 사유
        put(APPLIED, b"[1, 2]")
        _, log = self._boot(False)
        self.assertIn("reason=type", log)
        put(APPLIED, good(tp=-1))
        _, log = self._boot(False)
        self.assertIn("reason=field", log)

    def test_boot_case_08(self):  # 깨짐, 사본 정상, 보유
        put(APPLIED, b"not json")
        put(LAST_GOOD, good(tp=1.0))
        (params, src), log = self._boot(True)
        self.assertEqual(src, "last_good")
        self.assertIn("fallback reason=json", log)
        self.notify.assert_called()

    def test_boot_case_09(self):  # 둘 다 없음/깨짐, 미보유 -> 기동 거부
        for applied, last in ((None, None), (b"x{", b""), (None, b"zzz")):
            for n in (APPLIED, LAST_GOOD):
                if os.path.exists(n):
                    os.remove(n)
            if applied is not None:
                put(APPLIED, applied)
            if last is not None:
                put(LAST_GOOD, last)
            self.notify.reset_mock()
            with self.assertLogs(pp.logger, level="ERROR") as cm:
                params, src = pp.load_for_boot(USER, holding=False)
            self.assertEqual((params, src), (None, "none"))
            self.assertTrue(any("[PULLBACK-PARAMS]" in m for m in cm.output))
            self.notify.assert_called()
            self.assertIn("새 전략 설정이 없습니다", str(self.notify.call_args))

    def test_boot_case_10(self):  # 둘 다 없음/깨짐, 보유 -> 거부 + 운영자 확인
        put(APPLIED, b"{")
        with self.assertLogs(pp.logger, level="ERROR") as cm:
            params, src = pp.load_for_boot(USER, holding=True)
        self.assertEqual((params, src), (None, "none"))
        self.assertTrue(any("[PULLBACK-PARAMS]" in m for m in cm.output))
        self.assertIn("보유 중 새 전략 설정 없음", str(self.notify.call_args))

    def test_boot_case_11(self):  # 정상, 사본 깨짐 -> 적용본 기동 + WARNING
        self._applied_ok()
        put(LAST_GOOD, b"broken")
        before = Path(LAST_GOOD).read_bytes()
        for holding in (False, True):
            with self.assertLogs(pp.logger, level="WARNING") as cm:
                params, src = pp.load_for_boot(USER, holding=holding)
            self.assertEqual(src, "applied")
            self.assertTrue(any("last_good invalid" in m for m in cm.output))
        self.assertEqual(Path(LAST_GOOD).read_bytes(), before)

    def test_boot_case_12(self):  # 운용 중 적용본이 깨짐 -> 이전 값 유지
        cur = good(tp=7.0)
        put(APPLIED, b'{"ticker"')
        with self.assertLogs(pp.logger, level="WARNING") as cm:
            out = pp.reload_applied(USER, cur)
        self.assertIs(out, cur)
        self.assertTrue(any("reload rejected" in m for m in cm.output))
        # 정상으로 고치면 새 값
        put(APPLIED, good(tp=9.0))
        self.assertEqual(pp.reload_applied(USER, cur)["tp"], 9.0)


class TestBootExtra(unittest.TestCase):
    """_notify_critical 을 patch 하지 않고 notifier.send 가 터져도 반환값이 같다."""

    def setUp(self):
        self._cwd = os.getcwd()
        self._tmp = tempfile.TemporaryDirectory()
        os.chdir(self._tmp.name)

    def tearDown(self):
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def test_notifier_failure_does_not_change_result(self):
        with patch("services.notifier.send", side_effect=RuntimeError("down")):
            put(LAST_GOOD, good(tp=1.0))
            params, src = pp.load_for_boot(USER, holding=False)  # 경우 5
            self.assertEqual((src, params["tp"]), ("last_good", 1.0))
            os.remove(LAST_GOOD)
            self.assertEqual(pp.load_for_boot(USER, holding=False), (None, "none"))  # 경우 9
            self.assertEqual(pp.load_for_boot(USER, holding=True), (None, "none"))


class TestReadAndApply(Base):
    def test_read_empty_file_rejected(self):
        put(SAVED, b"")
        with self.assertRaises(pp.PullbackParamsError) as cm:
            pp.read_json_strict(SAVED)
        self.assertEqual(cm.exception.field, "empty")

    def test_read_half_written_rejected(self):
        put(SAVED, b'{"ticker": "KRW-J')
        with self.assertRaises(pp.PullbackParamsError) as cm:
            pp.read_json_strict(SAVED)
        self.assertEqual(cm.exception.field, "json")
        put(SAVED, b"[]")
        with self.assertRaises(pp.PullbackParamsError) as cm:
            pp.read_json_strict(SAVED)
        self.assertEqual(cm.exception.field, "type")

    def test_in_place_overwrite_read(self):
        put(SAVED, good(tp=5.0))
        ino = os.stat(SAVED).st_ino
        new = json.dumps(good(tp=8.0))
        with open(SAVED, "r+", encoding="utf-8", newline="") as f:  # v2.api_write._write_in_place 방식
            f.seek(0)
            f.write(new)
            f.truncate()
            f.flush()
            os.fsync(f.fileno())
        self.assertEqual(os.stat(SAVED).st_ino, ino)
        self.assertEqual(pp.read_json_strict(SAVED)["tp"], 8.0)

    def test_apply_saved_sha_mismatch(self):
        put(SAVED, good())
        put(APPLIED, good(tp=1.0))
        before = Path(APPLIED).read_bytes()
        with self.assertRaises(pp.PullbackParamsError) as cm:
            pp.apply_saved(USER, "0" * 64)
        self.assertEqual(cm.exception.field, "sha_mismatch")
        self.assertEqual(Path(APPLIED).read_bytes(), before)
        self.assertFalse(os.path.exists(LAST_GOOD))
        self.assertEqual(self.leftovers(), [])

    def test_apply_saved_writes_600_and_last_good(self):
        put(SAVED, good(tp=5.0))
        res = pp.apply_saved(USER, pp.sha256_of(SAVED))
        self.assertEqual(res["sha"], pp.sha256_of(APPLIED))
        self.assertEqual(res["params"]["tp"], 5.0)
        self.assertEqual(mode(APPLIED), 0o600)
        self.assertEqual(mode(LAST_GOOD), 0o600)
        self.assertEqual(Path(APPLIED).read_bytes(), Path(LAST_GOOD).read_bytes())
        self.assertEqual(self.leftovers(), [])
        # 2회째
        put(SAVED, good(tp=6.0))
        pp.apply_saved(USER, pp.sha256_of(SAVED))
        self.assertEqual(json.loads(Path(LAST_GOOD).read_text())["tp"], 6.0)
        self.assertEqual(Path(APPLIED).read_bytes(), Path(LAST_GOOD).read_bytes())
        # 검증 실패 흉내(저장본 범위 밖): 적용본·사본 불변
        a, lg = Path(APPLIED).read_bytes(), Path(LAST_GOOD).read_bytes()
        put(SAVED, good(tp=-3))
        with self.assertRaises(pp.PullbackParamsError):
            pp.apply_saved(USER, pp.sha256_of(SAVED))
        self.assertEqual(Path(APPLIED).read_bytes(), a)
        self.assertEqual(Path(LAST_GOOD).read_bytes(), lg)
        self.assertEqual(self.leftovers(), [])

    def test_apply_forces_600_over_existing_644(self):
        put(APPLIED, good(tp=1.0))
        put(LAST_GOOD, good(tp=1.0))
        os.chmod(APPLIED, 0o644)
        os.chmod(LAST_GOOD, 0o644)
        put(SAVED, good(tp=4.0))
        res = pp.apply_saved(USER, pp.sha256_of(SAVED))
        self.assertEqual(mode(APPLIED), 0o600)
        self.assertEqual(mode(LAST_GOOD), 0o600)
        self.assertTrue(res["last_good"])
        self.assertEqual(self.leftovers(), [])

    def test_apply_verify_mismatch_rolls_back(self):
        prev = json.dumps(good(tp=1.0)).encode()
        put(APPLIED, prev)
        put(LAST_GOOD, prev)
        put(SAVED, good(tp=2.0))
        real = pp._read_bytes
        applied_reads = {"n": 0}

        def fake(path):
            data = real(path)
            if path == APPLIED:
                applied_reads["n"] += 1
                if data != prev:  # 새 적용본을 다시 읽을 때만 다른 바이트가 보인다
                    return data + b" "
            return data

        with patch.object(pp, "_read_bytes", side_effect=fake):
            with self.assertRaises(pp.PullbackParamsError) as cm:
                pp.apply_saved(USER, pp.sha256_of(SAVED))
        self.assertEqual(cm.exception.field, "verify")
        self.assertEqual(Path(APPLIED).read_bytes(), prev)
        self.assertEqual(Path(LAST_GOOD).read_bytes(), prev)
        self.assertEqual(mode(APPLIED), 0o600)
        self.assertEqual(self.leftovers(), [])

    def test_apply_verify_mismatch_no_previous_removes_new(self):
        put(SAVED, good(tp=2.0))
        real = pp._read_bytes

        def fake(path):
            data = real(path)
            return data + b" " if path == APPLIED else data

        with patch.object(pp, "_read_bytes", side_effect=fake):
            with self.assertRaises(pp.PullbackParamsError):
                pp.apply_saved(USER, pp.sha256_of(SAVED))
        self.assertFalse(os.path.exists(APPLIED))
        self.assertFalse(os.path.exists(LAST_GOOD))
        self.assertEqual(self.leftovers(), [])

    def test_apply_replace_oserror_leaves_no_tmp_and_applied_unchanged(self):
        prev = json.dumps(good(tp=1.0)).encode()
        put(APPLIED, prev)
        put(SAVED, good(tp=2.0))
        with patch("os.replace", side_effect=OSError("boom")):
            with self.assertRaises(OSError):
                pp.apply_saved(USER, pp.sha256_of(SAVED))
        self.assertEqual(Path(APPLIED).read_bytes(), prev)
        self.assertEqual(self.leftovers(), [])
        with patch("os.fsync", side_effect=OSError("boom")):
            with self.assertRaises(OSError):
                pp.apply_saved(USER, pp.sha256_of(SAVED))
        self.assertEqual(Path(APPLIED).read_bytes(), prev)
        self.assertEqual(self.leftovers(), [])

    def test_apply_last_good_write_failure_is_warning_only(self):
        put(SAVED, good(tp=2.0))
        real = pp._atomic_write

        def fake(path, data):
            if path == LAST_GOOD:
                raise OSError("disk")
            return real(path, data)

        with patch.object(pp, "_atomic_write", side_effect=fake):
            with self.assertLogs(pp.logger, level="WARNING") as cm:
                res = pp.apply_saved(USER, pp.sha256_of(SAVED))
        self.assertIs(res["last_good"], False)
        self.assertEqual(json.loads(Path(APPLIED).read_text())["tp"], 2.0)
        self.assertTrue(any("[PULLBACK-PARAMS] last_good write failed" in m for m in cm.output))

    def test_apply_rejects_live_params_failure(self):
        put(SAVED, good())
        a = good(tp=1.0)
        put(APPLIED, a)
        before = Path(APPLIED).read_bytes()
        with patch.object(pp, "LiveParams", side_effect=ValueError("x")):
            with self.assertRaises(pp.PullbackParamsError) as cm:
                pp.apply_saved(USER, pp.sha256_of(SAVED))
        self.assertEqual(cm.exception.field, "live_params")
        self.assertEqual(Path(APPLIED).read_bytes(), before)

    def test_to_live_params_errors_wrapped(self):
        d = pp.validate(good())
        for bad in (float("nan"), float("inf"), 0, -5):
            with self.assertRaises(pp.PullbackParamsError) as cm:
                pp.to_live_params(d, bad)
            self.assertEqual(cm.exception.field, "capital_krw")
        with patch.object(pp, "LiveParams", side_effect=OverflowError("x")):
            with self.assertRaises(pp.PullbackParamsError) as cm:
                pp.to_live_params(d, 1_000_000)
        self.assertEqual(cm.exception.field, "live_params")

    def test_validate_extreme_numbers_and_ticker(self):
        for d in (good(tp=10 ** 400), good(capital=10 ** 400), good(tp=5e-324 * 0 - 1),
                  good(ticker="KRW-1INCH"), good(ticker="KRW-A1"), good(ticker="krw-btc")):
            with self.assertRaises(pp.PullbackParamsError, msg=str(d)):
                pp.validate(d)
        pp.validate(good(ticker="KRW-BTC"))
        # 5e-324 는 float 으로 유한하지만 LiveParams 쪽에서 막힌다 -> 적용 거절
        put(SAVED, good(tp=5e-324))
        with self.assertRaises(pp.PullbackParamsError):
            pp.apply_saved(USER, pp.sha256_of(SAVED))
        self.assertFalse(os.path.exists(APPLIED))

    def test_read_deep_nesting_is_json(self):
        put(SAVED, b"[" * 100000 + b"]" * 100000)
        with self.assertRaises(pp.PullbackParamsError) as cm:
            pp.read_json_strict(SAVED)
        self.assertEqual(cm.exception.field, "json")

    def test_read_permission_error_is_io(self):
        put(SAVED, good())
        with patch("builtins.open", side_effect=PermissionError("no")):
            with self.assertRaises(pp.PullbackParamsError) as cm:
                pp.read_json_strict(SAVED)
        self.assertEqual(cm.exception.field, "io")
        put(APPLIED, good())
        put(LAST_GOOD, good(tp=1.0))
        real = pp._read_bytes

        def fake(path):
            if path == APPLIED:
                raise pp.PullbackParamsError("io")
            return real(path)

        with patch.object(pp, "_read_bytes", side_effect=fake):
            with self.assertLogs(pp.logger, level="DEBUG") as cm:
                params, src = pp.load_for_boot(USER, holding=False)
        self.assertEqual(src, "last_good")
        self.assertIn("reason=io", "\n".join(cm.output))

    def test_switch_rejects_invalid_saved(self):
        put(SAVED, b"")
        with self.assertRaises(pp.PullbackParamsError) as cm:
            pp.check_saved_for_switch(USER)
        self.assertEqual(cm.exception.field, "saved_invalid")
        put(SAVED, b"{")
        with self.assertRaises(pp.PullbackParamsError) as cm:
            pp.check_saved_for_switch(USER)
        self.assertEqual(cm.exception.field, "saved_invalid")
        put(SAVED, good(sl=0))
        with self.assertRaises(pp.PullbackParamsError) as cm:
            pp.check_saved_for_switch(USER)
        self.assertEqual(cm.exception.field, "saved_invalid")
        put(SAVED, good())
        self.assertEqual(len(pp.check_saved_for_switch(USER)), 64)  # sha 반환, 적용본 없음은 정상


class TestRules(Base):
    def test_ranges_match_v2_schema(self):
        src = (ROOT / "v2" / "params_schema.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        consts = {}
        for node in tree.body:
            if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
                if node.targets[0].id in ("PARAM_FIELDS", "SERVER_EXTRA_LIMITS", "INTEGER_FIELDS"):
                    consts[node.targets[0].id] = ast.literal_eval(node.value)
        fields, extra, ints = consts["PARAM_FIELDS"], consts["SERVER_EXTRA_LIMITS"], consts["INTEGER_FIELDS"]
        for name, spec in fields.items():
            if name in ("symbol", "src", "days"):
                continue
            if spec["type"] == "number":
                lo, hi = pp.RANGES.get(name, (None, None))
                self.assertEqual(lo, spec.get("min"), name)
                self.assertEqual(hi, spec.get("max"), name)
            else:
                if name == "maType":
                    self.assertEqual(sorted(pp.MA_TYPES), sorted(spec["options"]))
                else:
                    self.assertIn(name, pp.BOOL_KEYS, name)
                    self.assertEqual(sorted(spec["options"]), ["no", "yes"])
        v2_numbers = {n for n, s in fields.items() if s["type"] == "number"} - {"days"}
        self.assertEqual(set(pp.NUMBER_KEYS), v2_numbers)
        for name, lim in extra.items():
            self.assertEqual(tuple(pp.EXTRA_LIMITS[name]), tuple(lim), name)
        self.assertEqual(set(pp.EXTRA_LIMITS), set(extra))
        self.assertEqual(set(pp.INTEGER_KEYS), set(ints) - {"days"})
        # interval 4종은 v2 _INTERVAL 값과 같다
        iv = None
        for node in tree.body:
            if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) \
                    and node.targets[0].id == "_INTERVAL":
                iv = ast.literal_eval(node.value)
        self.assertEqual(set(pp.INTERVALS), set(iv.values()))
        # 18키 순서: to_engine_file 의 반환 dict 키 순서
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "to_engine_file":
                ret = [n for n in ast.walk(node) if isinstance(n, ast.Return)][0].value
                keys = tuple(k.value for k in ret.keys)
                self.assertEqual(keys, pp.PULLBACK_KEYS)

    def test_no_v2_import_in_engine_module(self):
        tree = ast.parse((ROOT / "engine" / "pullback_params.py").read_text(encoding="utf-8"))
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                for a in n.names:
                    self.assertNotEqual(a.name.split(".")[0], "v2")
            elif isinstance(n, ast.ImportFrom):
                self.assertNotEqual((n.module or "").split(".")[0], "v2")

    def test_golden_only_zero_splits_rule(self):
        with self.assertRaises(pp.PullbackParamsError):
            pp.validate(good(maxSplits=0, buyOnGoldenCross=False))
        out = pp.validate(good(maxSplits=0, buyOnGoldenCross=True))
        self.assertEqual(pp.to_live_params(out, 3_000_000).order_ratio, 1.0)  # effMaxSplits 1

    def test_validate_strict(self):
        pp.validate(good())
        bad = [
            good(buyOnGoldenCross="yes"), good(deadcross=1), good(compounding=None),
            good(interval="minute10"), good(ma60p=1), good(ma200p=1001), good(tp=0),
            good(fee=-0.1), good(capital=0), good(maxPullbackBuys=6), good(ma60p=True),
            good(tp=float("nan")), good(maType="wma"), good(ticker="BTC"),
            good(ma60p=60.5),
        ]
        for d in bad:
            with self.assertRaises(pp.PullbackParamsError, msg=str(d)):
                pp.validate(d)
        d = good()
        del d["fee"]
        with self.assertRaises(pp.PullbackParamsError):
            pp.validate(d)
        with self.assertRaises(pp.PullbackParamsError):
            pp.validate(good(extra=1))
        # 선택 4키
        out = pp.validate(good(enable_trading_hours=True, trading_start_time="09:30"))
        self.assertEqual(out["trading_end_time"], "02:00")
        with self.assertRaises(pp.PullbackParamsError):
            pp.validate(good(trading_start_time="25:00"))
        with self.assertRaises(pp.PullbackParamsError):
            pp.validate(good(enable_trading_hours="yes"))

    def test_to_live_params_fill(self):
        lp = pp.to_live_params(pp.validate(good(tp=5, sl=3, maxSplits=5)), 3_000_000)
        self.assertEqual(lp.strategy_type, "PULLBACK")
        self.assertAlmostEqual(lp.take_profit, 0.05)
        self.assertAlmostEqual(lp.stop_loss, 0.03)
        self.assertEqual(lp.cash, 3_000_000)
        self.assertAlmostEqual(lp.order_ratio, 0.2)
        self.assertEqual(lp.commission, 0.0005)
        self.assertEqual((lp.ticker, lp.interval), ("KRW-JTO", "minute3"))
        # 운용자산이 최소보다 작으면 MIN_CASH
        self.assertEqual(pp.to_live_params(pp.validate(good()), 100).cash, 10_000)
        # 선택 4키 반영
        lp = pp.to_live_params(pp.validate(good(enable_trading_hours=True, allow_sell_during_off_hours=False)), 50_000)
        self.assertTrue(lp.enable_trading_hours)
        self.assertFalse(lp.allow_sell_during_off_hours)

    def test_required_bars_max(self):
        self.assertEqual(pp.required_bars({"ma60p": 60, "ma200p": 1000, "pullbackP": 20, "slopeLB": 500}), 2010)
        self.assertEqual(pp.required_bars({"ma60p": 60, "ma200p": 200, "pullbackP": 20, "slopeLB": 5}), 220)


if __name__ == "__main__":
    unittest.main()
