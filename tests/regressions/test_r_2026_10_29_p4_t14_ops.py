"""
2차 T14 (요청서 2-마, 결정 D6·D11): 운용 탭 단추 — 엔진 쪽 시험.

- ops_settings(운용 설정 저장 — 거래 시간 4키): 엔진은 지금 적용본에 이 4키만 합쳐 새 적용본(600)을 쓴다(저장본의 다른 키는
  적용하지 않음 — 결정 13-6 권고 가). 엔진이 돌면 엔진 제어 큐(OPS_KIND)에서 cfg 교체·_pullback_params_sha 갱신, 멈췄으면 적용본만.
  거절 순서는 T13 apply_params 와 같다(실계좌 → 다른 모드 엔진 → 형식 → 예약 중 → 활성 PULLBACK 아님).
- R1 변경 기록의 전환 부분(T13 fix 1 넘김, PO 결정): 전환(EMA·MACD → PULLBACK) DONE 뒤 strategy_switch PARAMS·DONE 1행
  (note.apply = "switch", from_strategy = 전환 전 전략). 복귀·실패 전환은 쓰지 않는다.

실행:
    TELEGRAM_BOT_TOKEN= TELEGRAM_CHAT_ID= TELEGRAM_CHAT_ID_OPERATOR= \
        python3 -m unittest tests.regressions.test_r_2026_10_29_p4_t14_ops -v
"""
from __future__ import annotations

import json
import os
import re
import stat
import sys
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from core import engine_control as ec  # noqa: E402
from engine import control_requests as cr  # noqa: E402
from engine import params as eparams  # noqa: E402
from engine import pullback_apply as pa  # noqa: E402
from engine import pullback_params as pbp  # noqa: E402
from engine import strategy_switch as ss  # noqa: E402
from tests.regressions import baseline_commits as bc  # noqa: E402
from tests.regressions.test_r_2026_10_28_p3_t5_pullback_engine import CFG, USER  # noqa: E402
from tests.regressions.test_r_2026_10_29_p4_t13_apply import FIXED_FILES, T13Case  # noqa: E402
from v2 import control as v2control  # noqa: E402

# fix 2: 「시간 밖에도 매도」는 바꿀 수 없다 — 적용본 값(기본 true) 그대로 보낸다
KEYS_ON = {"enable_trading_hours": True, "trading_start_time": "10:00", "trading_end_time": "23:00",
           "allow_sell_during_off_hours": True}
MOVABLE = {k for k in KEYS_ON if k != "allow_sell_during_off_hours"}


class OpsCase(T13Case):
    def setUp(self):
        super().setUp()
        p = mock.patch.dict(cr._EXTRA_HANDLERS, {"ops_settings": pa.handle_ops})
        p.start()
        self.addCleanup(p.stop)

    def ops(self, keys=None, mode="TEST", payload=None):
        return self.ctl.execute(self.req("ops_settings", mode, payload if payload is not None else
                                         {"keys": dict(keys or KEYS_ON)}))


# ================================================================ 1. ops_settings — 4키만 적용
class TestOpsSettings(OpsCase):
    def test_ops_settings_applies_only_4_keys(self):
        """계획: 저장본에 TP 4 를 「저장만」 → 운용 설정 저장 → 적용본 TP 는 그대로 5, 4키만 새 값
        (「저장만 한 값은 운용 설정 저장 뒤에도 적용본에 없음」)."""
        self.save_new(tp=4)                                   # 저장만(적용 요청 없음)
        before = self.applied()
        r = self.ops()
        self.assertEqual((r["status"], r["code"]), ("done", "ok"), r)
        after = self.applied()
        self.assertEqual(after["tp"], 5)
        for k, v in KEYS_ON.items():
            self.assertEqual(after[k], v, k)
        self.assertEqual({k: v for k, v in after.items() if k not in KEYS_ON},
                         {k: v for k, v in before.items() if k not in KEYS_ON})
        self.assertEqual(json.loads(Path(pbp.saved_path(USER)).read_text())["tp"], 4)   # 저장본은 엔진이 안 건드림
        self.assertEqual(r["detail"]["engine"], "stopped")
        rows = self.params_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(set(self.note(rows[0])["changed"]), MOVABLE)
        self.assertEqual(self.note(rows[0])["apply"], "next_bar")
        self.assertEqual(rows[0]["params_sha256"], pbp.sha256_of(pbp.applied_path(USER)))

    def test_ops_engine_running_swaps_cfg_without_restart(self):
        eng = self.pb_engine()
        self.assertFalse(eng.strategy.cfg["enable_trading_hours"])
        r = self.ops()
        self.assertEqual((r["status"], r["code"]), ("done", "ok"), r)
        self.assertNotIn("engine", r["detail"])               # 엔진 안에서 처리
        for k, v in KEYS_ON.items():
            self.assertEqual(eng.strategy.cfg[k], v, k)
        self.assertEqual(eng._pullback_params_sha, pbp.sha256_of(pbp.applied_path(USER)))
        self.assertEqual([c for c in self.mgr.calls if c[0] in ("start", "stop")], [])     # 재시작 없음
        # 새 cfg 로 거래 시간 판정: 03:00 봉(판정 03:03) = 시간 밖, 12:00 봉 = 시간 안
        self.assertTrue(eng.strategy._off_hours(pd.Timestamp("2026-10-29 03:00", tz="Asia/Seoul")))
        self.assertFalse(eng.strategy._off_hours(pd.Timestamp("2026-10-29 12:00", tz="Asia/Seoul")))
        # 다른 키(분할 한도·MA) 그대로
        self.assertEqual(eng.strategy.cfg["eff_max_splits"], CFG["maxSplits"])
        self.assertEqual(len(self.params_rows()), 1)

    def test_ops_sell_off_change_rejected_no_touch(self):
        """fix 2: 「시간 밖에도 매도」를 적용본 값(없으면 true)과 다르게 보내면 감시 스레드·엔진 스레드 모두 거절, 아무것도 안 씀."""
        before = self.applied_bytes()
        cur = self.applied().get("allow_sell_during_off_hours", True)
        bad = dict(KEYS_ON, allow_sell_during_off_hours=not cur)
        r = self.ops(keys=bad)
        self.assertEqual((r["status"], r["code"]), ("rejected", "sell_off_locked"), r)
        self.assertEqual(self.applied_bytes(), before)
        self.assertEqual(self.params_rows(), [])
        self.assertIn("아직 바꿀 수 없어", cr.CODE_TEXT["sell_off_locked"])
        eng = self.pb_engine()
        cfg_before = dict(eng.strategy.cfg)
        e = pa.engine_ops(eng, {"keys": bad, "mode": "TEST", "request_id": None})
        self.assertEqual((e["status"], e["code"]), ("rejected", "sell_off_locked"), e)
        self.assertEqual(self.applied_bytes(), before)
        self.assertEqual(eng.strategy.cfg, cfg_before)
        self.assertEqual(self.params_rows(), [])

    def test_ops_engine_cfg_equals_constructor_cfg(self):
        """엔진 안 교체 cfg = 새 적용본으로 생성자를 다시 부른 cfg(파생 키 포함)."""
        eng = self.pb_engine()
        self.ops()
        self.assertEqual(eng.strategy.cfg, pa.build_cfg(USER, self.applied(), eng.strategy.interval_min))

    def test_ops_applied_600_and_last_good_same_bytes(self):
        self.ops()
        a = Path(pbp.applied_path(USER))
        self.assertEqual(stat.S_IMODE(a.stat().st_mode), 0o600)
        self.assertEqual(Path(pbp.last_good_path(USER)).read_bytes(), a.read_bytes())
        self.assertEqual([p for p in os.listdir(".") if p.endswith(".tmp")], [])
        pbp.validate(json.loads(a.read_bytes()))

    def test_ops_live_rejected_no_touch(self):
        before = self.applied_bytes()
        r = self.ops(mode="LIVE")
        self.assertEqual((r["status"], r["code"]), ("rejected", "apply_live_not_supported"))
        self.assertEqual(self.applied_bytes(), before)
        self.assertEqual(self.params_rows(), [])

    def test_ops_mode_conflict(self):
        self.mgr.mode = "LIVE"
        before = self.applied_bytes()
        r = self.ops()
        self.assertEqual((r["status"], r["code"]), ("rejected", "mode_conflict"))
        self.assertEqual(self.applied_bytes(), before)

    def test_ops_rejected_while_reserved(self):
        self.add_row(kind="REVERT", from_strategy="PULLBACK", to_strategy="EMA")
        before = self.applied_bytes()
        r = self.ops()
        self.assertEqual((r["status"], r["code"]), ("rejected", "already_reserved"))
        self.assertEqual(self.applied_bytes(), before)

    def test_ops_not_pullback(self):
        eparams.save_active_strategy(USER, "EMA")
        r = self.ops()
        self.assertEqual((r["status"], r["code"]), ("rejected", "apply_not_pullback"))

    def test_ops_bad_keys_rejected(self):
        before = self.applied_bytes()
        bad = [dict(KEYS_ON, tp=4), {k: v for k, v in KEYS_ON.items() if k != "trading_end_time"},
               dict(KEYS_ON, trading_start_time="9:00"), dict(KEYS_ON, enable_trading_hours="on"),
               dict(KEYS_ON, trading_end_time="24:00")]
        for keys in bad:
            r = self.ops(keys=keys)
            self.assertEqual((r["status"], r["code"]), ("rejected", "bad_request"), keys)
        self.assertEqual(self.ops(payload={})["code"], "bad_request")
        self.assertEqual(self.applied_bytes(), before)
        self.assertEqual(self.params_rows(), [])

    def test_ops_unchanged_no_write_no_record(self):
        keys = {k: pbp.validate(self.applied())[k] for k in KEYS_ON}
        before = os.stat(pbp.applied_path(USER)).st_ino
        r = self.ops(keys=keys)
        self.assertEqual((r["status"], r["code"]), ("done", "ok"))
        self.assertTrue(r["detail"]["unchanged"])
        self.assertEqual(os.stat(pbp.applied_path(USER)).st_ino, before)
        self.assertEqual(self.params_rows(), [])

    def test_ops_applied_missing_rejected(self):
        os.remove(pbp.applied_path(USER))
        r = self.ops()
        self.assertEqual((r["status"], r["code"]), ("rejected", "params_missing"))
        self.assertFalse(os.path.exists(pbp.applied_path(USER)))

    def test_ops_engine_rejects_bad_keys_in_engine_too(self):
        """감시 스레드를 지나지 않고 엔진 큐에 바로 들어온 항목도 4키 형식을 다시 본다."""
        eng = self.pb_engine()
        before = self.applied_bytes()
        r = pa.engine_ops(eng, {"keys": dict(KEYS_ON, tp=1), "mode": "TEST"})
        self.assertEqual(r["code"], "bad_request")
        self.assertEqual(self.applied_bytes(), before)

    def test_apply_ops_keys_rejects_non_4_keys(self):
        with self.assertRaises(pbp.PullbackParamsError):
            pbp.apply_ops_keys(USER, dict(KEYS_ON, tp=1))
        with self.assertRaises(pbp.PullbackParamsError):
            pbp.apply_ops_keys(USER, dict(KEYS_ON, trading_start_time="25:00"))

    def test_ops_counts_in_other_group(self):
        """운용 설정은 요청 묶음 other(1시간 상한)에 든다 — 적용 실패(apply_failed)만 시도로 센다."""
        self.assertEqual(cr._group_of("ops_settings"), "other")
        self.assertEqual(cr.KIND_LABEL["ops_settings"], "운용 설정 저장")


# ================================================================ 2. R1 전환 부분 — 전환 DONE 뒤 PARAMS 행
class TestSwitchParamsRecord(OpsCase):
    def setUp(self):
        super().setUp()
        eparams.save_active_strategy(USER, "EMA")      # T13Case 는 PULLBACK — 전환 시험은 EMA 에서 시작
        p = mock.patch.dict(cr._EXTRA_HANDLERS, {"switch": ss.handle_switch, "revert": ss.handle_revert})
        p.start()
        self.addCleanup(p.stop)

    def test_switch_writes_params_row_with_changed_keys(self):
        """적용본(TP 5)이 있는 채 저장본 TP 4 로 전환 → PARAMS·DONE 1행, changed = {tp: [5, 4]}, apply switch."""
        new = self.save_new(tp=4)
        r = self.switch(sha=new)
        self.assertEqual((r["status"], r["code"]), ("done", "ok"), r)
        rows = self.rows()
        self.assertEqual([(x["kind"], x["state"]) for x in rows], [("SWITCH", "DONE"), ("PARAMS", "DONE")])
        p = rows[1]
        self.assertEqual(self.note(p), {"changed": {"tp": [5, 4]}, "apply": "switch"})
        self.assertEqual((p["from_strategy"], p["to_strategy"]), ("EMA", "PULLBACK"))
        self.assertEqual(p["params_sha256"], new)
        self.assertEqual(p["request_id"], rows[0]["request_id"])
        self.assertIsNotNone(p["done_at"])

    def test_first_switch_without_applied_records_all_keys(self):
        for path in (pbp.applied_path(USER), pbp.last_good_path(USER)):
            os.remove(path)
        r = self.switch()
        self.assertEqual(r["code"], "ok", r)
        note = self.note(self.params_rows()[0])
        self.assertEqual(set(note["changed"]), set(pa.ALL_KEYS))
        self.assertTrue(all(v[0] is None for v in note["changed"].values()))

    def test_reserved_switch_completion_writes_params_row(self):
        from tests.regressions.test_r_2026_10_29_p4_t12_switch import tick
        self.run_engine("EMA")
        self.wallet = 1.0
        new = self.save_new(tp=4)
        r = self.switch(sha=new)
        self.assertEqual(r["code"], "reserved", r)
        self.assertEqual(self.params_rows(), [])                   # 예약만으로는 기록 없음
        self.wallet = 0.0
        tick(self)
        self.eng.last_bar_ts = "bar-B"
        self.assertEqual(tick(self), [["ok"]])
        rows = self.params_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(self.note(rows[0]), {"changed": {"tp": [5, 4]}, "apply": "switch"})

    def test_failed_switch_writes_no_params_row(self):
        self.mgr.fail_next = 1
        r = self.switch()
        self.assertEqual(r["code"], "switch_failed", r)
        self.assertEqual(self.params_rows(), [])

    def test_revert_writes_no_params_row(self):
        eparams.save_active_strategy(USER, "PULLBACK")
        r = self.ctl.execute(self.req("revert", "TEST", {"strategy": "EMA"}))
        self.assertEqual(r["code"], "ok", r)
        self.assertEqual(self.params_rows(), [])

    def test_params_row_does_not_change_reservation_or_revert_target(self):
        self.switch()
        self.assertIsNone(ss.reservation(USER, "TEST"))
        self.assertEqual(ss.last_done_switch(USER, "TEST")["kind"], "SWITCH")

    def test_record_failure_keeps_switch_result(self):
        with mock.patch.object(pa, "record_params", side_effect=RuntimeError("x")):
            r = self.switch()
        self.assertEqual((r["status"], r["code"]), ("done", "ok"))
        self.assertEqual(self.active(), "PULLBACK")


# ================================================================ 3. 설치·고정·문구·v2 표 대조
class TestInstallFixedTexts(unittest.TestCase):
    def test_install_registers_ops_settings(self):
        with mock.patch.dict(cr._EXTRA_HANDLERS, {}, clear=True), mock.patch.dict(pa._INSTALLED, {"done": False}):
            pa.install()
            self.assertIs(cr._EXTRA_HANDLERS["ops_settings"], pa.handle_ops)

    def test_engine_control_dispatches_ops_kind(self):
        self.assertEqual(ec.OPS_KIND, "pullback_ops")
        item = ec.ControlItem(ec.OPS_KIND, {"keys": KEYS_ON})
        with mock.patch.object(pa, "engine_ops", return_value={"status": "done", "code": "ok", "detail": {}}) as m:
            r = ec._execute(object(), item)
        self.assertEqual(r["code"], "ok")
        self.assertEqual(m.call_count, 1)

    def test_fixed_files_unchanged_since_t12(self):
        """바이트 고정 8개 + 이번 Task 의 core/strategy_pullback.py 는 T12 커밋과 같다."""
        for rel in (*FIXED_FILES, "core/strategy_pullback.py"):
            base = bc.git_show(rel, bc.FIXED_FILES_COMMIT)
            self.assertEqual((ROOT / rel).read_text(encoding="utf-8"), base, rel)

    def test_applied_writers_allowlist(self):
        """적용본을 쓰는 함수(apply_saved·apply_ops_keys)를 부르는 곳은 정해진 파일만."""
        allowed = {"apply_saved(": {"engine/pullback_params.py", "engine/strategy_switch.py", "engine/pullback_apply.py"},
                   "apply_ops_keys(": {"engine/pullback_params.py", "engine/pullback_apply.py"}}
        offenders = []
        for p in ROOT.rglob("*.py"):
            rel = p.relative_to(ROOT).as_posix()
            if rel.startswith(("tests/", ".venv", "venv/", ".superpowers")) or "/site-packages/" in rel:
                continue
            text = p.read_text(encoding="utf-8", errors="ignore")
            for needle, ok in allowed.items():
                if needle in text and rel not in ok:
                    offenders.append((rel, needle))
        self.assertEqual(offenders, [])

    def test_v2_tables_match_engine(self):
        """신버전(v2/control.py — 엔진 모듈 import 없음)의 4키 기본값·18키 = 엔진 표."""
        self.assertEqual(v2control.OPS_DEFAULTS, pbp.OPTIONAL_KEYS)
        self.assertEqual(v2control.OPS_KEYS, tuple(pbp.OPTIONAL_KEYS))
        self.assertEqual(v2control.SAVED_KEYS, pbp.PULLBACK_KEYS)
        self.assertEqual(pa.OPS_KEYS, tuple(pbp.OPTIONAL_KEYS))

    def test_v2_and_engine_ops_key_rules_agree(self):
        cases = [KEYS_ON, dict(KEYS_ON, tp=1), dict(KEYS_ON, trading_start_time="9:00"),
                 dict(KEYS_ON, allow_sell_during_off_hours=1), {}, None, dict(KEYS_ON, trading_end_time="23:59")]
        for c in cases:
            self.assertEqual(v2control.ops_keys_or_none(c), pa.ops_keys_or_none(c), c)

    def test_v2_eff_max_splits_matches_strategy(self):
        for over in ({"maxSplits": 5}, {"maxSplits": 0, "buyOnGoldenCross": True}, {"maxSplits": 3}):
            d = dict(CFG)
            d.update(over)
            self.assertEqual(v2control._eff_max_splits(d), pa.build_cfg("x", pbp.validate(d))["eff_max_splits"], over)

    def test_investor_texts_have_no_internal_names(self):
        """이번에 쓰는 결과 문구(엔진 CODE_TEXT)에 내부 코드·표 이름이 없다."""
        for code in ("apply_live_not_supported", "already_reserved", "apply_not_pullback", "params_missing",
                     "bad_request", "mode_conflict", "apply_failed"):
            text = cr.CODE_TEXT[code]
            self.assertIsNone(re.search(r"[A-Za-z_]{4,}", text.replace("LIVE", "").replace("TEST", "")), (code, text))


if __name__ == "__main__":
    unittest.main()
