"""v2 정적 화면 문자열 검사 (Task 6 묶음 B)."""
import hashlib
import re
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / "v2" / "static"
VENDOR = STATIC / "vendor"
URL_RE = re.compile(r"https?://([A-Za-z0-9.\-]+)")
OWN = ["index.html", "app.js", "chart.js", "style.css"]


def _read(name):
    return (STATIC / name).read_text(encoding="utf-8")


def _hosts(name):
    return set(URL_RE.findall(_read(name)))


class StaticLintTest(unittest.TestCase):
    def test_external_hosts_allowlisted(self):
        for name in OWN:
            self.assertTrue((STATIC / name).exists(), name)
            self.assertLessEqual(_hosts(name), {"api.upbit.com"}, name)
        bt = [n for n in ("backtester.html", "backtester.js") if (STATIC / n).exists()]
        if not bt:
            self.skipTest("Task 7 전")
        for name in bt:
            self.assertLessEqual(_hosts(name),
                                 {"data-api.binance.vision", "api.binance.com"}, name)

    def test_vendor_sha256_matches_versions_txt(self):
        """VERSIONS.txt 형식: `#` 으로 시작하지 않는 비어 있지 않은 줄은
        `<sha256 64자 hex>  <파일명>` (shasum -a 256 출력 형식).
        각 줄의 파일을 sha256 해 같아야 하고, vendor/ 의 .js 는 모두 목록에 있어야 한다."""
        listed = {}
        for line in (VENDOR / "VERSIONS.txt").read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            m = re.fullmatch(r"([0-9a-f]{64})  (\S+)", s)
            self.assertIsNotNone(m, line)
            listed[m.group(2)] = m.group(1)
        self.assertTrue(listed)
        for fname, digest in listed.items():
            actual = hashlib.sha256((VENDOR / fname).read_bytes()).hexdigest()
            self.assertEqual(actual, digest, fname)
        for p in VENDOR.glob("*.js"):
            self.assertIn(p.name, listed)

    def test_operation_buttons_disabled(self):
        html = _read("index.html")
        self.assertIn("2차 공개 때 열림", html)
        marker = "data-ops"
        self.assertIn(marker, html)
        start = html.index(marker)
        end = html.find("</section>", start)
        block = html[start:end]
        buttons = re.findall(r"<button\b[^>]*>", block)
        for b in buttons:
            self.assertRegex(b, r"\bdisabled\b")
        for name in ("전략 전환", "기존 전략 복귀", "엔진 시작", "엔진 정지",
                     "일시정지·재개", "강제 매수", "강제 매도", "운용 설정"):
            self.assertRegex(block, r"<button\b[^>]*disabled[^>]*>\s*" + re.escape(name))
        self.assertEqual(len(buttons), 8)

    def test_index_loads_both_vendor_scripts(self):
        html = _read("index.html")
        srcs = re.findall(r'<script\b[^>]*\bsrc="([^"]+)"', html)
        for p in VENDOR.glob("*.js"):
            self.assertIn("/v2/static/vendor/" + p.name, srcs)
        lw = [i for i, s in enumerate(srcs) if "lightweight-charts" in s][0]
        mod = html.index('type="module"')
        self.assertLess(html.index(srcs[lw]), mod)

    def test_app_has_no_identity_compare_on_reactive_chart_state(self):
        js = _read("app.js")
        for bad in ("this._poller", "this._chartView", "this._cache", "this._gate"):
            self.assertNotIn(bad, js)
        self.assertNotRegex(js, r"[!=]==\s*poller\b")

    def test_no_double_init(self):
        self.assertNotIn('x-init="init()"', _read("index.html"))

    def test_no_ma200(self):
        for name in ("index.html", "app.js", "chart.js"):
            self.assertNotRegex(_read(name), r"(?i)ma\s*200|sma\(\s*[\w.]+\s*,\s*200")

    def test_no_stop_word_in_engine_badge(self):
        """엔진 동작 배지에만 적용(운용 버튼의 「엔진 정지」·「일시정지」는 spec 낱말).
        대상: app.js 의 engineText getter 본문 + index.html 의 id="engine-badge" 줄."""
        js = _read("app.js")
        m = re.search(r"get engineText\(\)(.*?)get engineClass\(\)", js, re.S)
        self.assertIsNotNone(m, "app.js engineText 추출 실패")
        body = m.group(1)
        lines = [l for l in _read("index.html").splitlines() if 'id="engine-badge"' in l]
        self.assertEqual(len(lines), 1, "index.html engine-badge 요소 없음")
        for text in (body, lines[0]):
            self.assertNotIn("정지", text)
        for needle in ("정상", "지연 · 마지막 판단", "판단 불가"):
            self.assertIn(needle, body)
        self.assertIn("engineText", lines[0])

    def test_backtester_menu_link(self):
        self.assertIn("/v2/static/backtester.html", _read("index.html"))

    def test_signal_key_uses_kind(self):
        text = _read("index.html") + _read("app.js")
        self.assertRegex(text, r"row\.kind\s*\+\s*'-'\s*\+\s*row\.id")

    def test_no_top_level_browser_globals_in_chart(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node 없음")
        r = subprocess.run(
            [node, "-e", "import('./v2/static/chart.js').then(()=>{},e=>{console.error(e);process.exit(1)})"],
            cwd=str(ROOT), capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main()
