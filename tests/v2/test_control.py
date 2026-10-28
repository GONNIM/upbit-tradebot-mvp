"""2차 T11: 신버전 쪽 엔진 제어 요청(v2/control.py)·API 시험. 임시 폴더만 쓴다.

- 요청 파일: services/data/v2_control/<user>/req-<id>.json (600, 폴더 700), 본문 {"v","id","user_id","mode","kind",
  "payload","created_at","expires_at"} — expires_at = created_at + 60초.
- POST /v2/api/control → 202 {"id"}, 진행 중이면 409 busy. GET /v2/api/control/result·/state.
- 신버전 프로세스에는 엔진 모듈·엔진 스레드가 없다(A11). 입장·화면 읽기만으로 요청 파일 0(A8).
"""
import hashlib
import json
import os
import stat
import subprocess
import sys
import threading
from datetime import datetime, timedelta
from pathlib import Path

from v2 import control, db
from v2.server import DEFAULT_ORIGIN
from tests.v2 import test_api_read as base

ROOT = Path(__file__).resolve().parents[2]
CONTROL_URL = "/v2/api/control"


class ControlFileTest(base.ApiBase):
    def test_write_request_file_format_and_modes(self):
        old = os.umask(0o022)
        try:
            rid = control.write_request("alice", "TEST", "engine_start", {})
        finally:
            os.umask(old)
        d = self.data / "v2_control" / "alice"
        p = d / f"req-{rid}.json"
        self.assertEqual(stat.S_IMODE(p.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(d.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(d.parent.stat().st_mode), 0o700)
        body = json.loads(p.read_text(encoding="utf-8"))
        self.assertEqual(set(body), {"v", "id", "user_id", "mode", "kind", "payload", "created_at", "expires_at"})
        self.assertEqual((body["v"], body["id"], body["user_id"], body["mode"], body["kind"]),
                         (1, rid, "alice", "TEST", "engine_start"))
        c, e = datetime.fromisoformat(body["created_at"]), datetime.fromisoformat(body["expires_at"])
        self.assertEqual(e - c, timedelta(seconds=60))
        self.assertTrue(body["created_at"].endswith("+09:00"))
        self.assertRegex(rid, r"^[0-9]{14}-[0-9a-f]{8}$")
        self.assertEqual(rid[:14], c.strftime("%Y%m%d%H%M%S"))
        self.assertEqual(sorted(x.name for x in d.iterdir()), [f"req-{rid}.json"])   # 임시 파일 남지 않음

    def test_rejects_bad_kind_user_mode_payload(self):
        for args in (("alice", "TEST", "rm", {}), ("../x", "TEST", "engine_start", {}),
                     ("alice", "PROD", "engine_start", {}), ("alice", "TEST", "force_buy", {"krw": 1}),
                     ("alice", "TEST", "engine_start", "x")):
            with self.assertRaises(ValueError, msg=args):
                control.write_request(*args)
        self.assertFalse((self.data / "v2_control").exists())

    def test_busy_while_pending_then_free_after_result_or_expiry(self):
        rid = control.write_request("alice", "TEST", "engine_start", {})
        with self.assertRaises(control.Busy) as cm:
            control.write_request("alice", "TEST", "engine_stop", {})
        self.assertEqual(cm.exception.pending, rid)
        self.assertEqual(control.pending_id("alice"), rid)
        d = self.data / "v2_control" / "alice"
        (d / f"res-{rid}.json").write_text(json.dumps({"id": rid, "status": "done"}))
        self.assertIsNone(control.pending_id("alice"))
        # 결과 없이 만료가 지나면 진행 중으로 보지 않는다(엔진이 꺼져 있어도 영구히 막히지 않게)
        rid2 = control.write_request("alice", "TEST", "engine_stop", {})
        later = datetime.now(db.KST) + timedelta(seconds=61)
        self.assertIsNone(control.pending_id("alice", now=later))
        self.assertEqual(control.pending_id("alice"), rid2)

    def test_read_result(self):
        rid = control.write_request("alice", "TEST", "engine_start", {})
        self.assertEqual(control.read_result("alice", rid)["status"], "pending")
        later = datetime.now(db.KST) + timedelta(seconds=61)
        self.assertTrue(control.read_result("alice", rid, now=later)["overdue"])
        d = self.data / "v2_control" / "alice"
        (d / f"req-{rid}.json").unlink()
        (d / f"res-{rid}.json").write_text(json.dumps({"id": rid, "status": "rejected", "code": "mode_conflict"}))
        self.assertEqual(control.read_result("alice", rid)["code"], "mode_conflict")
        self.assertIsNone(control.read_result("alice", "20261028000000-deadbeef"))
        with self.assertRaises(ValueError):
            control.read_result("alice", "../../etc")

    def test_symlink_dir_refused(self):
        """수정 1회차: 사용자 폴더가 바깥을 가리키는 링크면 쓰지 않는다(바깥 폴더 권한·파일 무변경)."""
        outside = self.data.parent / "outside_dir"
        outside.mkdir(mode=0o755)
        os.chmod(outside, 0o755)
        (self.data / "v2_control").mkdir(mode=0o700)
        os.symlink(outside, self.data / "v2_control" / "alice")
        with self.assertRaises(OSError):
            control.write_request("alice", "TEST", "engine_start", {})
        self.assertEqual(stat.S_IMODE(outside.stat().st_mode), 0o755)
        self.assertEqual(list(outside.iterdir()), [])

    def test_force_reason_label(self):
        """수정 1회차: 새 전략 강제 매수 사유 FORCE 의 화면 용어(서버 표 — labels.js 와 같음은 정적 시험이 대조)."""
        from v2 import api_read
        self.assertEqual(api_read.REASON_LABELS["FORCE"], "강제 매수")


class ControlApiTest(base.ApiBase):
    def setUp(self):
        super().setUp()
        self.make_live_db()
        self.set_strategy("EMA", "KRW-ZRO", "minute3")

    def post(self, body, mode="TEST", origin=DEFAULT_ORIGIN):
        h = dict(self.cookie(mode=mode))
        h["Content-Type"] = "application/json"
        if origin:
            h["Origin"] = origin
        return self.fetch(CONTROL_URL, method="POST", body=json.dumps(body), headers=h)

    def test_post_202_then_409_busy_and_result_pending(self):
        r = self.post({"kind": "engine_start", "payload": {}}, mode="LIVE")
        self.assertEqual(r.code, 202)
        rid = json.loads(r.body)["id"]
        body = json.loads((self.data / "v2_control" / "alice" / f"req-{rid}.json").read_text())
        self.assertEqual((body["user_id"], body["mode"]), ("alice", "LIVE"))   # 세션 user·입장 모드
        r2 = self.post({"kind": "force_sell", "payload": {}})
        self.assertEqual(r2.code, 409)
        self.assertEqual(json.loads(r2.body), {"error": "busy", "pending": rid})
        code, res = self.get_json(f"{CONTROL_URL}/result?id={rid}")
        self.assertEqual((code, res["status"]), (200, "pending"))
        code, st = self.get_json(f"{CONTROL_URL}/state")
        self.assertEqual((code, st), (200, {"pending": rid, "reservation": None}))

    def test_post_rejects_bad_body_origin_session(self):
        self.assertEqual(self.post({"kind": "nope", "payload": {}}).code, 400)
        self.assertEqual(self.post({"kind": "force_buy", "payload": {"krw": 100}}).code, 400)
        self.assertEqual(self.post({"kind": "engine_start"}, origin="https://evil.example").code, 403)
        r = self.fetch(CONTROL_URL, method="POST", body="{}",
                       headers={"Origin": DEFAULT_ORIGIN, "Content-Type": "application/json"})
        self.assertEqual(r.code, 401)
        self.assertFalse((self.data / "v2_control").exists())

    def test_result_bad_id_400_unknown_404(self):
        self.assertEqual(self.get_json(f"{CONTROL_URL}/result?id=../x")[0], 400)
        self.assertEqual(self.get_json(f"{CONTROL_URL}/result?id=20261028000000-deadbeef")[0], 404)

    def test_entry_does_not_switch(self):
        """A8: 입장·홈·운용 탭 읽기 API 만 부름 → 요청 파일 0, 활성 전략 파일 바이트 불변."""
        active = self.root / "alice_active_strategy.txt"
        before = hashlib.sha256(active.read_bytes()).hexdigest()
        for path in ("/v2/api/basic", "/v2/api/status", "/v2/api/assets", "/v2/api/trades", "/v2/api/signals",
                     "/v2/api/logs", "/v2/api/markers", f"{CONTROL_URL}/state", "/v2/api/params/current"):
            for mode in ("TEST", "LIVE"):
                self.fetch(path, headers=self.cookie(mode=mode))
        self.assertFalse((self.data / "v2_control").exists())
        self.assertEqual(hashlib.sha256(active.read_bytes()).hexdigest(), before)


class ImportGraphTest(base.ApiBase):
    def test_v2_has_no_engine_import_and_no_engine_thread(self):
        """A11: v2.control 을 포함한 신버전 모듈 import·요청 쓰기 뒤에도 엔진·core·services 모듈 0, 엔진 스레드 0."""
        code = (
            "import sys, threading, tempfile, pathlib, v2.server, v2.control, v2.api_write, v2.api_read; "
            "from v2 import db, control; d = pathlib.Path(tempfile.mkdtemp()); db.DATA_DIR = d; "
            "control.write_request('alice', 'TEST', 'force_buy', {}); "
            "bad = sorted(m for m in sys.modules if m.split('.')[0] in "
            "('config','streamlit','pyupbit','services','engine','core')); "
            "th = sorted(t.name for t in threading.enumerate() if t is not threading.main_thread()); "
            "print('BAD:' + ','.join(bad)); print('THREADS:' + ','.join(th))")
        r = subprocess.run([sys.executable, "-c", code], cwd=str(ROOT), capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        lines = r.stdout.strip().splitlines()
        self.assertEqual(lines[0], "BAD:")
        self.assertEqual(lines[1], "THREADS:")
        for t in threading.enumerate():
            self.assertNotRegex(t.name, r"engine_runner|run_live_loop|v2_control")
