"""v2 배포 자료(Task 9) 정적 시험 — 서비스 유닛·nginx·cron·점검 스크립트·runbook.

서버 명령(systemctl·systemd-run·nginx·crontab)은 실행하지 않는다. 파일 내용 검사와 `bash -n` 문법 검사가 기본이고,
2차 T18 부터 탐침 새 항목을 임시 폴더 가짜 루트에서 실제로 돌리고(ProbeFakeRootTest), 셸 ReadWritePaths 판정 함수를
bash 로 돌린다(RwPathsTest). 둘 다 서버·실파일을 건드리지 않는다.
"""
import ast
import contextlib
import importlib.util
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
UNIT = ROOT / "deploy" / "tradebot-v2.service"
NGINX = ROOT / "deploy" / "nginx-v2-location.conf"
CRON = ROOT / "deploy" / "v2hist-backup.cron"
CHECK_SH = ROOT / "scripts" / "v2" / "check_v2_unit.sh"
PROBE_PY = ROOT / "scripts" / "v2" / "check_v2_unit_probe.py"
A3_SH = ROOT / "scripts" / "v2" / "a3_memory_probe.sh"
RUNBOOK = ROOT / "docs" / "operations" / "v2-runbook.md"
GATE = ROOT / "scripts" / "regression_gate.sh"

SHELLS = [CHECK_SH, A3_SH]


def _text(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _code_lines(p: Path):
    """주석(#)·빈 줄을 뺀 줄 목록(양끝 공백 제거)."""
    out = []
    for ln in _text(p).splitlines():
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        out.append(s)
    return out


def _sections(p: Path):
    """유닛 파일을 {섹션: [줄]} 로 파싱."""
    sec, res = None, {}
    for s in _code_lines(p):
        if s.startswith("[") and s.endswith("]"):
            sec = s
            res[sec] = []
        elif sec is not None:
            res[sec].append(s)
    return res


class UnitFileTest(unittest.TestCase):
    def test_unit_has_required_directives(self):
        secs = _sections(UNIT)
        service = secs["[Service]"]
        required = [
            "User=root",
            "WorkingDirectory=/root/upbit-tradebot-mvp",
            "ExecStart=/root/upbit-tradebot-mvp/venv/bin/python -m v2.server",
            "ProtectSystem=strict",
            "ProtectHome=read-only",
            "ReadWritePaths=-/root/upbit-tradebot-mvp/services/data "
            "-/root/upbit-tradebot-mvp/mcmax33_latest_params_PULLBACK.json",
            "InaccessiblePaths=-/root/upbit-tradebot-mvp/.env "
            "-/root/upbit-tradebot-mvp/.streamlit/secrets.toml "
            "-/root/upbit-tradebot-mvp/credentials.yaml",
            "NoNewPrivileges=yes",
            "UMask=0077",
            "CapabilityBoundingSet=",
            "AmbientCapabilities=",
            "MemoryMax=150M",
            "MemorySwapMax=0",
            "OOMScoreAdjust=500",
            "Nice=10",
            "CPUWeight=50",
            "Restart=on-failure",
            "RestartSec=5",
            "PrivateTmp=yes",
            "Type=simple",
        ]
        for line in required:
            self.assertIn(line, service, f"[Service] 에 없음: {line}")
        # 같은 지시어가 두 번 나오면 systemd 는 뒤의 값을 쓴다(예: ProtectHome=read-only 뒤 ProtectHome=no)
        keys = [x.split("=", 1)[0] for x in service]
        self.assertEqual(sorted(k for k in set(keys) if keys.count(k) > 1), [], "[Service] 지시어 중복")
        unit = secs["[Unit]"]
        self.assertIn("StartLimitIntervalSec=300", unit)
        self.assertIn("StartLimitBurst=5", unit)
        self.assertIn("After=network.target", unit)
        self.assertTrue(any(x.startswith("Description=") for x in unit))
        self.assertIn("WantedBy=multi-user.target", secs["[Install]"])

    def test_unit_has_no_environmentfile(self):
        lines = _code_lines(UNIT)
        self.assertEqual([x for x in lines if x.startswith("EnvironmentFile")], [])
        env = [x for x in lines if x.startswith("Environment=")]
        self.assertEqual(env, ["Environment=PYTHONUNBUFFERED=1"])

    def test_unit_header_comment_mentions_account_add(self):
        head = _text(UNIT)
        self.assertIn("ReadWritePaths", head.split("[Unit]")[0])
        self.assertIn("daemon-reload", head.split("[Unit]")[0])


class NginxFileTest(unittest.TestCase):
    def test_nginx_location_only_v2(self):
        lines = _code_lines(NGINX)
        locs = [x for x in lines if x.startswith("location")]
        self.assertEqual(locs, ["location /v2/ {"])
        self.assertIn("proxy_pass http://127.0.0.1:8502;", lines)
        self.assertIn("client_max_body_size 64k;", lines)
        self.assertIn("proxy_set_header Host $host;", lines)
        self.assertIn("proxy_set_header X-Forwarded-Proto $scheme;", lines)


class CronFileTest(unittest.TestCase):
    def test_cron_guards_missing_file(self):
        lines = _code_lines(CRON)
        self.assertEqual(len(lines), 1, "cron 항목은 한 줄")
        ln = lines[0]
        self.assertTrue(ln.startswith("30 11 * * 0 "))
        self.assertIn("umask 077;", ln)
        self.assertEqual(ln.count("$(date"), 1, "날짜는 한 번만 구한다")
        self.assertIn("D=$(date +\\%Y\\%m\\%d);", ln)
        self.assertEqual(ln.count("${D}"), 2)
        self.assertIn("[ -f /root/upbit-tradebot-mvp/services/data/v2hist_mcmax33.db ] &&", ln)
        self.assertIn('sqlite3 -cmd ".timeout 5000" /root/upbit-tradebot-mvp/services/data/v2hist_mcmax33.db ".backup ', ln)
        self.assertIn("&& chmod 600 ", ln)
        self.assertIn("\\%", ln)
        self.assertIsNone(re.search(r"(?<!\\)%", ln), "이스케이프 안 된 % 가 있음")
        self.assertIn("/services/data/backups/v2hist_mcmax33_", ln)
        self.assertNotIn("tradebot_mcmax33.db.backup_", ln)


class ShellScriptTest(unittest.TestCase):
    def test_systemctl_show_one_property_per_call(self):
        n = 0
        for p in SHELLS:
            for ln in _code_lines(p):
                if "systemctl show" not in ln:
                    continue
                n += 1
                self.assertEqual(len(re.findall(r"(?<!\S)-p\s", ln)), 1, f"-p 는 정확히 하나: {ln}")
                self.assertIsNone(re.search(r"-p\s+\S*,", ln), f"-p 콤마 목록 금지: {ln}")
        self.assertGreaterEqual(n, 8)

    def test_check_script_reads_all_unit_properties(self):
        t = _text(CHECK_SH)
        for prop in ["ProtectSystem", "ProtectHome", "ReadWritePaths", "InaccessiblePaths", "NoNewPrivileges",
                     "UMask", "CapabilityBoundingSet", "PrivateTmp"]:
            self.assertRegex(t, rf"systemctl show -p {prop} --value tradebot-v2")
        self.assertIn('-p "ProtectHome=$PROP_PROTECT_HOME"', t)
        self.assertIn('[ "$PROP_PROTECT_HOME" = "read-only" ]', t)
        self.assertIn("set -u", t)
        self.assertIn("set -o pipefail", t)
        self.assertNotRegex("\n".join(_code_lines(CHECK_SH)), r"(?m)^set -[a-zA-Z]*e")
        self.assertIn("FAIL tradebot-v2-not-active", t)
        self.assertIn("FAIL probe-run-failed", t)
        self.assertIn("FAIL probe-line-count=", t)
        self.assertIn("EXPECTED_PROBE_LINES=15", t)
        self.assertIn('USER_ID="${1:-mcmax33}"', t)
        self.assertIn("^[A-Za-z0-9_]{1,32}$", t)
        self.assertIn("FAIL bad-user-argument", t)
        self.assertIn('"$PROBE" "$TRADEBOT_PID" "$USER_ID"', t)
        self.assertIn('stat -Lc %i "/proc/$V2_PID/root$REPO/$PULLBACK_REL"', t)
        self.assertIn('stat -Lc %i "$REPO/$PULLBACK_REL"', t)
        self.assertIn("PASS pullback-inode-match", t)
        self.assertIn("FAIL pullback-inode-mismatch", t)
        self.assertIn("PASS no-upbit-env", t)
        self.assertIn("FAIL upbit-env-count=", t)
        self.assertIn("systemd-run --wait --pipe --collect --quiet", t)

    def test_a3_oom_judged_by_string(self):
        t = _text(A3_SH)
        self.assertIn("oom-kill", t)
        self.assertIn("oom-kill|killed by the OOM killer", t)
        self.assertRegex(t, r'grep -qE "\$OOM_PATTERN" <<< "\$RUN_OUT"')
        self.assertRegex(t, r'grep -qE "\$OOM_PATTERN" <<< "\$JOURNAL_OUT"')
        # journalctl 은 파이프 없이 변수로 받는다(pipefail·SIGPIPE 거짓 방지)
        for ln in _code_lines(A3_SH):
            if "journalctl" in ln:
                self.assertNotIn("|", ln.replace("|| true", ""), ln)
        self.assertIn("journalctl -u", t)
        self.assertIn("PASS probe-oom-killed", t)
        self.assertIn("FAIL probe-not-oom(", t)
        self.assertIn("PASS swap-unchanged(", t)
        self.assertIn("PASS tradebot-not-restarted", t)
        self.assertIn("-p MemoryMax=150M", t)
        self.assertIn("-p MemorySwapMax=0", t)
        runs = [ln for ln in _code_lines(A3_SH) if "systemd-run" in ln]
        self.assertTrue(runs)
        self.assertNotIn("--quiet", t)
        self.assertIn("--unit=v2-a3-probe-$$", t)
        # MemoryError 를 잡아 종료 코드만 바꾸는 구현 금지
        self.assertNotIn("MemoryError", t)

    def test_check_script_outputs_status_only(self):
        status = re.compile(r'^echo "(PASS|FAIL|RESIDUAL) [A-Za-z0-9_.()=+<>${}-]+"$')
        for p in SHELLS:
            t = _text(p)
            self.assertIsNone(re.search(r"\bcat\s", "\n".join(_code_lines(p))), f"{p.name}: cat 금지")
            self.assertNotIn("print(open(", t)
            for ln in _code_lines(p):
                if re.match(r"^echo\b", ln):
                    self.assertRegex(ln, status, f"{p.name}: 상태 줄 형식이 아님: {ln}")
                if re.match(r"^printf\b", ln):
                    ok = "| grep" in ln or ln == "printf '%s\\n' \"$FILTERED\""
                    self.assertTrue(ok, f"{p.name}: 필터 없는 printf: {ln}")
            self.assertNotRegex(t, r"\.env\b[^\n]*(<|cat|head|tail|less)")
        # environ 은 이름만 센다
        c = _text(CHECK_SH)
        self.assertIn("tr '\\0' '\\n'", c)
        self.assertIn("cut -d= -f1", c)
        self.assertIn("grep -c '^UPBIT_'", c)
        # 탐침(py)
        code = _text(PROBE_PY)
        self.assertNotIn("print(open(", code)
        self.assertIsNone(re.search(r"\.read\(\s*\)", code), "인자 없는 read() 금지")
        for m in re.finditer(r"\.read\((\d+)\)", code):
            self.assertEqual(m.group(1), "1")
        reads = [ln for ln in code.splitlines() if ".read(1)" in ln]
        self.assertTrue(reads)
        for ln in code.splitlines():
            s = ln.strip()
            if s.startswith("print("):
                self.assertRegex(s, r'^print\("(PASS|FAIL|RESIDUAL) [A-Za-z0-9_.()=-]+"\)$', f"탐침 출력 형식: {s}")
        self.assertNotIn("traceback", code)
        self.assertNotRegex(code, r"print\([^\"]")

    def test_check_script_never_opens_strategy_params_for_write(self):
        code = _text(PROBE_PY)
        for ln in code.splitlines():
            s = ln.strip()
            if s.startswith("#"):
                continue
            m = re.search(r"(?<![\w.])open\((.*)\)", s)
            if not m:
                continue
            args = m.group(1)
            mode = re.search(r'"([rwax+bt]+)"', args)
            self.assertIsNotNone(mode, f"모드를 명시하지 않은 open: {s}")
            mode = mode.group(1)
            # 저장본(PULLBACK)·적용본 변수(2차 T18 applied-not-writable-by-v2 — 열기 실패를 기대) 인자만 r+
            if "PULLBACK" in args or re.search(r"\bAPPLIED_\w+|\bapplied_path\b", args):
                self.assertEqual(mode, "r+", s)
            else:
                self.assertIn(mode, ("r", "rb"), f"읽기 전용이 아닌 open: {s}")
            if re.search(r"EMA|MACD|ACTIVE_STRATEGY|active_strategy", args):
                self.assertIn(mode, ("r", "rb"), s)
        self.assertNotIn(".write(", code)
        self.assertNotIn(".truncate(", code)
        self.assertNotRegex(code, r"EMA|MACD")
        self.assertIsNone(re.search(
            r"os\.open\([^)]*(ACTIVE_STRATEGY|PULLBACK|APPLIED|applied)[^)]*O_(WRONLY|RDWR)", code))
        self.assertNotIn("os.O_RDWR", code)
        self.assertNotIn("os.O_TRUNC", code)

    def test_probe_checks_all_inaccessible_paths(self):
        code = _text(PROBE_PY)
        for name in ["env", "secrets", "credentials"]:
            self.assertIn(f'print("PASS {name}-inaccessible")', code)
            self.assertIn(f'print("PASS {name}-inaccessible(placeholder)")', code)
            self.assertRegex(code, rf'print\("FAIL {name}-(readable)"\)')
            self.assertRegex(code, rf'print\("FAIL {name}-not-found\(cannot-verify\)"\)')
        self.assertIn('".streamlit", "secrets.toml"', code)
        self.assertIn('"credentials.yaml"', code)
        # main() 이 부르는 검사 수 = 탐침 출력 줄 수
        self.assertEqual(len(re.findall(r"^    check_\w+\(", code, re.M)), 15)
        # 실매매 DB 쓰기 탐침: BEGIN IMMEDIATE → ROLLBACK 뿐(데이터를 바꾸는 문장·COMMIT 없음)
        m = re.search(r"def check_live_db_write_lock\(\):(.*?)\ndef ", code, re.S)
        self.assertIsNotNone(m)
        fn = m.group(1)
        self.assertIn("BEGIN IMMEDIATE", fn)
        self.assertIn("ROLLBACK", fn)
        self.assertIn("mode=rw", fn)
        self.assertIsNone(re.search(r"(?i)\b(insert|update|delete|replace|create|drop|alter|commit)\b", fn.split('"""')[2]))
        self.assertIn('print("PASS live-db-write-lock")', fn)
        self.assertIn('print("FAIL live-db-write-lock")', fn)

    def test_probe_stdlib_only(self):
        tree = ast.parse(_text(PROBE_PY))
        allowed = {"os", "sqlite3", "sys", "re", "errno", "stat"}
        mods = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                mods |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                mods.add((node.module or "").split(".")[0])
        self.assertTrue(mods <= allowed, f"표준 라이브러리 밖 import: {mods - allowed}")

    def test_probe_cleans_up_created_files(self):
        lines = _text(PROBE_PY).splitlines()
        idx = [i for i, ln in enumerate(lines) if "O_EXCL" in ln and "os.open(" in ln]
        self.assertGreaterEqual(len(idx), 2, "탐침 파일을 만드는 곳이 두 군데(데이터 폴더·저장소 루트)")
        for i in idx:
            window = "\n".join(lines[i:i + 14])
            self.assertRegex(window, r"os\.(unlink|remove)\(", f"{i + 1}행 뒤에 삭제가 없음")

    def test_scripts_never_restart_services(self):
        pat = re.compile(r"systemctl\s+(restart|stop|start|reload|disable|enable|kill|daemon-reload|mask)")
        for p in SHELLS:
            code = "\n".join(_code_lines(p))
            self.assertIsNone(pat.search(code), f"{p.name}: 서비스 조작 명령 금지")
            self.assertNotRegex(code, r"(?<![\w-])(pkill|kill|reboot|shutdown)(?![\w-])")
            for m in re.finditer(r"systemctl\s+(\S+)", code):
                self.assertIn(m.group(1), ("is-active", "show"))

    def test_scripts_bash_syntax(self):
        for p in SHELLS + [GATE]:
            r = subprocess.run(["bash", "-n", str(p)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, f"{p.name}: {r.stderr}")

    def test_check_script_has_phase2_items(self):
        """2차 T18: 탐침 5항목 + 셸 unit-rw-paths-unchanged. 없으면 (absent), lstat, 내용 안 엶, 적용본 r+ 실패 기대."""
        code = _text(PROBE_PY)
        items = ["v2-control-dir-700", "v2-control-files-600", "applied-600", "applied-not-writable-by-v2",
                 "v2-control-results-readable"]
        for name in items:
            self.assertIn(f'print("PASS {name}")', code, name)
            self.assertIn(f'print("PASS {name}(absent)")', code, name)
            self.assertRegex(code, rf'print\("FAIL {re.escape(name)}(\(absent\))?"\)', name)
        # main(): 기존 10개 뒤에 새 5개가 이 순서로
        calls = re.findall(r"^    (check_\w+)\(", code, re.M)
        self.assertEqual(calls[-6:], ["check_pullback_open", "check_v2_control_dir_700", "check_v2_control_files_600",
                                      "check_applied_600", "check_applied_not_writable_by_v2",
                                      "check_v2_control_results_readable"])
        self.assertIn('os.path.join(DATA_DIR, "v2_control")', code)
        self.assertIn('"%s_applied_params_PULLBACK.json" % USER_ID', code)
        self.assertIn('"%s_applied_params_PULLBACK.last_good.json" % USER_ID', code)
        self.assertIn("ROOT_UID = 0", code)
        # 새 항목 구간: 링크를 따라가지 않는 lstat 만(os.stat·os.path.exists·isdir 금지)
        seg = code[code.index("# ---------------------------------------------------------------- 2차 T18"):
                   code.index("def main():")] + "\ndef "
        self.assertIn("os.lstat(", seg)
        self.assertIsNone(re.search(r"os\.stat\(|os\.path\.(exists|isdir|isfile|islink)\(", seg))
        self.assertIn("stat.S_IMODE(st.st_mode) == 0o700", seg)
        self.assertIn("stat.S_IMODE(st.st_mode) == 0o600", seg)
        self.assertEqual(seg.count("st.st_uid == ROOT_UID"), 2)
        # 적용본: 없으면 루트 쓰기 불가만, 있으면 os.access 거짓 + r+ 실패(EROFS·EACCES). 열리면 닫기만 하고 FAIL.
        fn = re.search(r"def _applied_write_refused\(applied_path\):(.*?)\ndef ", seg, re.S).group(1)
        self.assertIn("os.access(applied_path, os.W_OK)", fn)
        self.assertIn('open(applied_path, "r+")', fn)
        self.assertIn("errno.EROFS", fn)
        self.assertIn("errno.EACCES", fn)
        self.assertIn("f.close()", fn)
        self.assertTrue(fn.rstrip().endswith("f.close()\n    return False"), "열리면 닫고 거짓(FAIL)")
        self.assertNotIn("with open", fn)
        fn = re.search(r"def check_applied_not_writable_by_v2\(\):(.*?)\ndef ", seg, re.S).group(1)
        self.assertIn("os.access(ROOT, os.W_OK)", fn)
        # 결과 읽기: 사용자 폴더 res-*.json 이름순 첫 1개, rb 로 1바이트
        self.assertIn('n.startswith("res-") and n.endswith(".json")', seg)
        self.assertIn('n.startswith("req-") and n.endswith(".json")', seg)
        fn = re.search(r"def check_v2_control_results_readable\(\):(.*?)\ndef ", seg, re.S).group(1)
        self.assertIn("listed[1][0]", fn)
        self.assertIn('open(path, "rb")', fn)
        self.assertIn("f.read(1)", fn)
        # 셸: unit-rw-paths-unchanged
        sh = _text(CHECK_SH)
        self.assertIn('RW_PULLBACK_RE="^${REPO}/[A-Za-z0-9_]{1,32}_latest_params_PULLBACK\\\\.json\\$"', sh)
        self.assertIn('p="${tok#-}"', sh)
        self.assertIn('read -r -a toks <<< "$1"', sh)
        self.assertIn('if rw_paths_ok "$PROP_RW_PATHS" "$PULLBACK_REL"; then', sh)
        i = sh.index('if rw_paths_ok "$PROP_RW_PATHS"')
        block = sh[i:sh.index("fi", i)]
        self.assertIn('echo "PASS unit-rw-paths-unchanged"', block)
        self.assertIn('echo "FAIL unit-rw-paths-unchanged"', block)
        self.assertIn("FAILS=1", block)
        # runbook
        rb = _text(RUNBOOK)
        for name in items + ["unit-rw-paths-unchanged", "saved-writable-by-v2"]:
            self.assertIn(f"`{name}", rb, name)
        self.assertIn("탐침 15항목", rb)
        self.assertIn("탐침 출력 줄 수가 15가 아님", rb)
        self.assertIn("첫 모의 전환 입회 뒤", rb)


def _load_probe(root: Path, user: str = "alice"):
    """탐침을 가짜 저장소 루트(root/scripts/v2/)로 복사해 불러온다. ROOT 는 파일 위치로 정해진다. 기대 소유자 = 지금 사용자."""
    dst = root / "scripts" / "v2" / "check_v2_unit_probe.py"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(PROBE_PY, dst)
    spec = importlib.util.spec_from_file_location(f"_probe_copy_{abs(hash(str(root)))}", dst)
    mod = importlib.util.module_from_spec(spec)
    with mock.patch.object(sys, "argv", [str(dst), "", user]):
        spec.loader.exec_module(mod)
    mod.ROOT_UID = os.geteuid()
    return mod


def _run_probe(mod, fn: str):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        getattr(mod, fn)()
    return buf.getvalue().splitlines()


@unittest.skipIf(os.geteuid() == 0, "root 는 권한 비트를 무시해 거부 경우를 만들 수 없다")
class ProbeFakeRootTest(unittest.TestCase):
    """2차 T18 탐침 5항목을 임시 폴더 가짜 루트에서 실제로 돌린다(absent·PASS·FAIL). 서버의 EROFS 는 권한 비트(EACCES)로 흉내."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "repo"
        (self.root / "services" / "data").mkdir(parents=True)
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self._unlock)
        self.mod = _load_probe(self.root)
        self.base = self.root / "services" / "data" / "v2_control"
        self.user = self.base / "alice"
        self.applied = self.root / "alice_applied_params_PULLBACK.json"
        self.last_good = self.root / "alice_applied_params_PULLBACK.last_good.json"

    def _unlock(self):
        for p in [self.root] + list(self.root.rglob("*")):
            if not p.is_symlink():
                try:
                    os.chmod(p, 0o700)
                except OSError:
                    pass

    def one(self, fn):
        lines = _run_probe(self.mod, fn)
        self.assertEqual(len(lines), 1, lines)
        return lines[0]

    def make_control(self):
        self.base.mkdir(mode=0o700)
        os.chmod(self.base, 0o700)
        self.user.mkdir(mode=0o700)
        os.chmod(self.user, 0o700)

    def put(self, path: Path, mode: int, text: str = "{}"):
        path.write_text(text, encoding="utf-8")
        os.chmod(path, mode)

    def test_all_absent(self):
        self.assertEqual(self.one("check_v2_control_dir_700"), "PASS v2-control-dir-700(absent)")
        self.assertEqual(self.one("check_v2_control_files_600"), "PASS v2-control-files-600(absent)")
        self.assertEqual(self.one("check_applied_600"), "PASS applied-600(absent)")
        self.assertEqual(self.one("check_v2_control_results_readable"), "PASS v2-control-results-readable(absent)")
        # 루트에 쓸 수 있으면(유닛 밖) 없음이라도 FAIL, 쓸 수 없으면 PASS(absent). 파일은 만들지 않는다.
        self.assertEqual(self.one("check_applied_not_writable_by_v2"), "FAIL applied-not-writable-by-v2(absent)")
        os.chmod(self.root, 0o500)
        self.assertEqual(self.one("check_applied_not_writable_by_v2"), "PASS applied-not-writable-by-v2(absent)")
        self.assertFalse(self.applied.exists())
        self.assertFalse(self.last_good.exists())
        # 공용 폴더만 있고 계정 폴더가 없어도 없음
        self.base.mkdir(mode=0o700)
        os.chmod(self.base, 0o700)
        self.assertEqual(self.one("check_v2_control_dir_700"), "PASS v2-control-dir-700(absent)")

    def test_control_ok(self):
        self.make_control()
        self.put(self.user / "req-20261030120000-0000000a.json", 0o600)
        self.put(self.user / "res-20261030110000-0000000b.json", 0o600)
        self.put(self.user / "res-20261030120000-0000000c.json", 0o600)
        self.put(self.user / ".req-20261030120001-0000000d.tmp", 0o644)   # 임시 파일은 대상 아님
        self.assertEqual(self.one("check_v2_control_dir_700"), "PASS v2-control-dir-700")
        self.assertEqual(self.one("check_v2_control_files_600"), "PASS v2-control-files-600")
        self.assertEqual(self.one("check_v2_control_results_readable"), "PASS v2-control-results-readable")

    def test_control_only_request_no_result(self):
        self.make_control()
        self.put(self.user / "req-20261030120000-0000000a.json", 0o600)
        self.put(self.user / ".req-20261030120001-0000000d.tmp", 0o600)
        self.assertEqual(self.one("check_v2_control_files_600"), "PASS v2-control-files-600")
        self.assertEqual(self.one("check_v2_control_results_readable"), "PASS v2-control-results-readable(absent)")

    def test_control_bad(self):
        self.make_control()
        os.chmod(self.user, 0o755)
        self.assertEqual(self.one("check_v2_control_dir_700"), "FAIL v2-control-dir-700")
        os.chmod(self.user, 0o700)
        os.chmod(self.base, 0o750)
        self.assertEqual(self.one("check_v2_control_dir_700"), "FAIL v2-control-dir-700")
        os.chmod(self.base, 0o700)
        self.put(self.user / "res-20261030110000-0000000b.json", 0o644)
        self.assertEqual(self.one("check_v2_control_files_600"), "FAIL v2-control-files-600")
        os.chmod(self.user / "res-20261030110000-0000000b.json", 0o600)
        self.put(self.user / "req-20261030110000-0000000e.json", 0o640)
        self.assertEqual(self.one("check_v2_control_files_600"), "FAIL v2-control-files-600")
        os.chmod(self.user / "req-20261030110000-0000000e.json", 0o600)
        self.assertEqual(self.one("check_v2_control_files_600"), "PASS v2-control-files-600")
        # 소유자가 다르면 FAIL
        self.mod.ROOT_UID = os.geteuid() + 1
        self.assertEqual(self.one("check_v2_control_dir_700"), "FAIL v2-control-dir-700")
        self.assertEqual(self.one("check_v2_control_files_600"), "FAIL v2-control-files-600")
        self.mod.ROOT_UID = os.geteuid()
        # 결과 파일을 읽을 수 없으면 FAIL
        os.chmod(self.user / "res-20261030110000-0000000b.json", 0o200)
        self.assertEqual(self.one("check_v2_control_results_readable"), "FAIL v2-control-results-readable")

    def test_control_symlinks(self):
        real = self.root / "elsewhere"
        real.mkdir(mode=0o700)
        os.chmod(real, 0o700)
        (real / "alice").mkdir(mode=0o700)
        os.chmod(real / "alice", 0o700)
        os.symlink(real, self.base)
        self.assertEqual(self.one("check_v2_control_dir_700"), "FAIL v2-control-dir-700")
        os.unlink(self.base)
        self.make_control()
        target = self.root / "outside.json"
        self.put(target, 0o600)
        os.symlink(target, self.user / "res-20261030100000-0000000f.json")
        self.assertEqual(self.one("check_v2_control_files_600"), "FAIL v2-control-files-600")
        self.assertEqual(self.one("check_v2_control_results_readable"), "FAIL v2-control-results-readable")

    def test_applied(self):
        self.put(self.applied, 0o600, '{"x": 1}')
        self.assertEqual(self.one("check_applied_600"), "PASS applied-600")
        before = (self.applied.read_bytes(), os.stat(self.applied).st_mtime_ns)
        # 쓸 수 있으면 FAIL(열려도 쓰지 않음 — 내용·mtime 그대로)
        self.assertEqual(self.one("check_applied_not_writable_by_v2"), "FAIL applied-not-writable-by-v2")
        self.assertEqual((self.applied.read_bytes(), os.stat(self.applied).st_mtime_ns), before)
        # 쓰기 거부(서버는 EROFS, 여기서는 EACCES)면 PASS
        os.chmod(self.applied, 0o400)
        os.chmod(self.root, 0o500)
        self.assertEqual(self.one("check_applied_not_writable_by_v2"), "PASS applied-not-writable-by-v2")
        self.assertEqual(self.one("check_applied_600"), "FAIL applied-600")
        os.chmod(self.root, 0o700)
        os.chmod(self.applied, 0o600)
        self.put(self.last_good, 0o644)
        self.assertEqual(self.one("check_applied_600"), "FAIL applied-600")
        # 사본만 쓸 수 있어도 FAIL
        os.chmod(self.applied, 0o400)
        self.assertEqual(self.one("check_applied_not_writable_by_v2"), "FAIL applied-not-writable-by-v2")
        os.unlink(self.last_good)
        os.chmod(self.applied, 0o600)
        self.mod.ROOT_UID = os.geteuid() + 1
        self.assertEqual(self.one("check_applied_600"), "FAIL applied-600")
        self.mod.ROOT_UID = os.geteuid()
        os.unlink(self.applied)
        os.symlink(self.root / "nowhere.json", self.applied)
        self.assertEqual(self.one("check_applied_600"), "FAIL applied-600")
        # 끊긴 링크: os.access 는 거짓이지만 r+ 실패가 ENOENT(EROFS·EACCES 아님) → FAIL, 대상 파일도 만들지 않는다
        self.assertEqual(self.one("check_applied_not_writable_by_v2"), "FAIL applied-not-writable-by-v2")
        self.assertFalse((self.root / "nowhere.json").exists())

    def test_main_prints_expected_line_count(self):
        lines = _run_probe(self.mod, "main")
        n = int(re.search(r"^EXPECTED_PROBE_LINES=(\d+)$", _text(CHECK_SH), re.M).group(1))
        self.assertEqual(len(lines), n, lines)
        for ln in lines:
            self.assertRegex(ln, r"^(PASS|FAIL|RESIDUAL) [A-Za-z0-9_().=-]+$")


class RwPathsTest(unittest.TestCase):
    """셸 rw_paths_ok(unit-rw-paths-unchanged)를 실제 bash 로 돌린다(set -u — 서버 스크립트와 같게)."""

    @classmethod
    def setUpClass(cls):
        sh = _text(CHECK_SH)
        repo = re.search(r"^REPO=.*$", sh, re.M).group(0)
        rx = re.search(r"^RW_PULLBACK_RE=.*$", sh, re.M).group(0)
        fn = re.search(r"^rw_paths_ok\(\) \{\n.*?^\}$", sh, re.M | re.S).group(0)
        cls.src = "\n".join(["set -u", "set -o pipefail", repo, rx, fn, 'rw_paths_ok "$1" "$2"'])

    def ok(self, value, rel="mcmax33_latest_params_PULLBACK.json"):
        r = subprocess.run(["bash", "-c", self.src, "bash", value, rel], capture_output=True, text=True)
        self.assertEqual(r.stderr, "")
        return r.returncode == 0

    def test_rw_paths(self):
        R = "/root/upbit-tradebot-mvp"
        unit = [x for x in _code_lines(UNIT) if x.startswith("ReadWritePaths=")][0].split("=", 1)[1]
        self.assertTrue(self.ok(unit))
        self.assertTrue(self.ok(f"{R}/services/data {R}/mcmax33_latest_params_PULLBACK.json"))
        self.assertTrue(self.ok(f"-{R}/services/data -{R}/mcmax33_latest_params_PULLBACK.json "
                                f"-{R}/bob_2_latest_params_PULLBACK.json"))
        self.assertTrue(self.ok(f"-{R}/services/data -{R}/bob_latest_params_PULLBACK.json",
                                rel="bob_latest_params_PULLBACK.json"))
        self.assertFalse(self.ok(""))
        self.assertFalse(self.ok(f"-{R}/services/data"))
        self.assertFalse(self.ok(f"-{R}/mcmax33_latest_params_PULLBACK.json"))
        self.assertFalse(self.ok(f"-{R}/services/data -{R}/bob_latest_params_PULLBACK.json"))
        self.assertFalse(self.ok(f"{unit} -{R}/mcmax33_applied_params_PULLBACK.json"))
        self.assertFalse(self.ok(f"{unit} -{R}/mcmax33_applied_params_PULLBACK.last_good.json"))
        self.assertFalse(self.ok(f"{unit} -{R}"))
        self.assertFalse(self.ok(f"{unit} -/etc"))
        self.assertFalse(self.ok(f"{unit} -{R}/*"))
        self.assertFalse(self.ok(f"{unit} -{R}/services/data/../.."))
        self.assertFalse(self.ok(f"{unit} -{R}/x/mcmax33_latest_params_PULLBACK.json"))
        self.assertFalse(self.ok(f"{unit} -{R}/{'a' * 33}_latest_params_PULLBACK.json"))
        self.assertFalse(self.ok(f"{unit} -{R}/mcmax33_latest_params_PULLBACKxjson"))


class GateAndRunbookTest(unittest.TestCase):
    def test_gate_node_step(self):
        t = _text(GATE)
        self.assertIn("command -v node", t)
        self.assertIn("node --test tests/v2/js/*.test.mjs", t)
        self.assertNotIn("node --test 'tests/v2/js", t)
        self.assertIn("node 없음 — v2 JS 시험 건너뜀 (서버 환경)", t)
        self.assertIn("v2 JS 시험 통과", t)
        i_node = t.index("command -v node")
        self.assertGreater(i_node, t.index("✅ v2 시험 통과"))
        self.assertLess(i_node, t.index("▶ 회귀 테스트 스위트 실행"))

    def test_runbook_has_required_sections_and_no_secret_commands(self):
        t = _text(RUNBOOK)
        heads = [ln for ln in t.splitlines() if ln.startswith("## ")]
        joined = "\n".join(heads)
        for name in ["서비스 개요", "설치", "즉시 닫기", "계정 추가", "비밀·권한 점검", "동결 파일",
                     "점검 스크립트", "로그 출처", "알려진 틈"]:
            self.assertIn(name, joined, f"절 없음: {name}")
        self.assertIsNone(re.search(r"\bcat\s+\S*(\.env|\.v2_secret|secrets\.toml|credentials)", t))
        self.assertIsNone(re.search(r"\b(xxd|od|strings|base64)\s+\S*\.v2_secret", t))
        self.assertIn("umask 077; : > ", t)
        self.assertIn("0바이트", t)
        self.assertIn("지우거나 새로 만들지", t)
        self.assertIn("journalctl -u tradebot-v2", t)
        self.assertIn("systemctl disable --now tradebot-v2", t)
        self.assertIn("ui/v2_entry.py", t)
        self.assertIn("utils/v2_entry_token.py", t)
        self.assertIn("32바이트 이상", t)
        self.assertIn("두 번 다 FAIL 이면 멈추고 보고", t)
        self.assertIn("killed by the OOM killer", t)
        self.assertIn("RESIDUAL", t)
        self.assertIn("probe-run-failed", t)


if __name__ == "__main__":
    unittest.main()
