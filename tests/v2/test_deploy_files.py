"""v2 배포 자료(Task 9) 정적 시험 — 서비스 유닛·nginx·cron·점검 스크립트·runbook.

서버 명령(systemctl·systemd-run·nginx·crontab)은 실행하지 않는다. 파일 내용 검사와 `bash -n` 문법 검사만 한다.
"""
import ast
import re
import subprocess
import unittest
from pathlib import Path

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
        self.assertIn("EXPECTED_PROBE_LINES=9", t)
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
            if "PULLBACK" in args:
                self.assertEqual(mode, "r+", s)
            else:
                self.assertIn(mode, ("r", "rb"), f"읽기 전용이 아닌 open: {s}")
            if re.search(r"EMA|MACD|ACTIVE_STRATEGY|active_strategy", args):
                self.assertIn(mode, ("r", "rb"), s)
        self.assertNotIn(".write(", code)
        self.assertNotRegex(code, r"EMA|MACD")
        self.assertIsNone(re.search(r"os\.open\([^)]*(ACTIVE_STRATEGY|PULLBACK)[^)]*O_(WRONLY|RDWR)", code))

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
        self.assertEqual(len(re.findall(r"^    check_\w+\(", code, re.M)), 9)

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
