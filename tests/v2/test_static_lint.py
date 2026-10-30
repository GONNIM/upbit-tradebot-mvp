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
OWN = ["index.html", "app.js", "chart.js", "style.css", "basic.js", "basic.css", "labels.js", "bt_ui.js", "ops.js"]


def _read(name):
    return (STATIC / name).read_text(encoding="utf-8")


def _hosts(name):
    return set(URL_RE.findall(_read(name)))


class StaticLintTest(unittest.TestCase):
    def test_external_hosts_allowlisted(self):
        for name in OWN:
            self.assertTrue((STATIC / name).exists(), name)
            # bt_ui.js 는 서버 경로(/v2/api/candles)만 부른다 — 외부 주소 허용 없음
            allowed = set() if name in ("bt_ui.js", "ops.js") else {"api.upbit.com"}
            self.assertLessEqual(_hosts(name), allowed, name)
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

    def test_operation_buttons_wired(self):
        """2차 T14 (요청서 2-마): 1차 「2차 공개 때 열립니다」 안내는 지우고 「매매 중지/재개는 홈 화면 위 단추로 합니다.」는 남긴다.
        운용 단추는 고정 disabled 가 아니라 판정(opsView.<이름>.enabled)에 묶이고, 누르면 opsAct('<이름>') 를 부른다."""
        html = _read("index.html")
        self.assertNotIn("2차 공개 때 열립니다", html)
        self.assertEqual(html.count("매매 중지/재개는 홈 화면 위 단추로 합니다."), 1)
        marker = "data-ops"
        self.assertIn(marker, html)
        start = html.index(marker)
        end = html.index("</main>", start)
        block = html[start:end]
        ops = re.findall(r'<button\b[^>]*\bdata-op="([A-Za-z]+)"[^>]*>', block)
        self.assertEqual(ops, ["switch", "revert", "cancel", "pause", "stop", "start", "forceBuy", "forceSell",
                               "opsSave"])
        for tag in re.findall(r'<button\b[^>]*\bdata-op="[A-Za-z]+"[^>]*>', block):
            name = re.search(r'data-op="([A-Za-z]+)"', tag).group(1)
            self.assertNotRegex(tag, r"\sdisabled(\s|>)", name)                  # 고정 비활성 없음
            self.assertIn(f':disabled="!opsView.{name}.enabled"', tag, name)
            self.assertIn(f"@click=\"opsAct('{name}')\"", tag, name)
        self.assertIn('<script src="/v2/static/ops.js"></script>', html)
        self.assertLess(html.index("/v2/static/ops.js"), html.index("/v2/static/app.js"))

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

    def test_chart_matches_figure_2_na(self):
        """그림 2-나: 단추 4칸·범례·카드 문구, 공유 10초 문, 차트 높이 300px (E4 폐기 — 200선 포함)."""
        html, js, css = _read("index.html"), _read("app.js"), _read("style.css")
        for s in ("최근 200봉", "확대 +", "축소 −", "60선", "200선", "▲", "▼",
                  "이 화면에서 보는 것",
                  "캔들, 60선·200선(눌림목 기준선), 봇이 실제로 사고판 자리. 손가락으로 확대·이동합니다."):
            self.assertIn(s, html, s)
        self.assertIn("createSharedRateGate(10000", js)
        self.assertNotIn("createRateGate(", js)
        # 2차 T16: 1차 고정 글자(60선·200선 범례·안내 문장)는 새 전략이 아닐 때만 보이고,
        # 새 전략은 적용본 기간 범례·안내 문장·EMA 안내 한 줄로 바꿔 보인다(같은 자리).
        self.assertIn('<p class="chart-legend" x-show="!chartSpec.legend">', html)
        self.assertIn('id="chart-legend-pb" x-show="!!chartSpec.legend"', html)
        self.assertIn('<p class="sentence" x-show="!chartSpec.caption">캔들, 60선·200선', html)
        self.assertIn('id="chart-caption-pb" x-show="!!chartSpec.caption" x-text="chartSpec.caption"', html)
        self.assertIn('id="chart-ema-note" x-show="!!chartSpec.note" x-text="chartSpec.note"', html)
        self.assertIn("get chartSpec() { return chartLines(this.status); }", js)
        self.assertIn(".chart-legend .mapull", css)
        self.assertRegex(css, r"\.chart\s*\{[^}]*height:\s*300px")

    def test_no_stop_word_in_engine_badge(self):
        """엔진 동작 배지에만 적용(운용 버튼의 「엔진 정지」·「일시정지」는 spec 낱말).
        대상: app.js 의 engineBadge 함수 본문. 글자와 색이 한 함수에서 정해진다."""
        js = _read("app.js")
        m = re.search(r"function engineBadge\(.*?\n\}\n", js, re.S)
        self.assertIsNotNone(m, "app.js engineBadge 추출 실패")
        body = m.group(0)
        self.assertNotIn("정지", body)
        for needle in ("엔진 동작 중", "판단 지연", "판단 보류", "엔진 멈춤", "엔진 확인 중"):
            self.assertIn(needle, body)
        # 옛 level 전용 도우미는 없다(멈춘 엔진이 초록으로 보이던 원인)
        for old in ("get engineClass", "get engineIcon", "get engineText"):
            self.assertNotIn(old, js)
        self.assertIn("home.badges", _read("index.html"))

    def test_labels_match_server(self):
        """labels.js 의 두 표 == v2.api_read 의 REASON_LABELS·FAILED_KEY_LABELS."""
        import json
        from v2 import api_read
        js = _read("labels.js")
        for const, server in (("REASON_LABELS", api_read.REASON_LABELS),
                              ("FAILED_KEY_LABELS", api_read.FAILED_KEY_LABELS)):
            m = re.search(r"export const " + const + r" = (\{.*?\n\});", js, re.S)
            self.assertIsNotNone(m, const)
            self.assertEqual(json.loads(m.group(1)), server, const)

    def test_backtester_menu_link(self):
        html = _read("index.html")
        nav = html[html.index('<nav class="bottom"'):html.index("</nav>")]
        self.assertRegex(nav, r'<a\b[^>]*href="/v2/static/backtester\.html"[^>]*>백테스터</a>')

    def test_pc_is_phone_width(self):
        css = _read("style.css")
        self.assertNotIn("min-width: 641px", css)
        self.assertNotIn("tab-chart", css)
        self.assertRegex(css, r"body\s*\{[^}]*max-width:\s*480px")

    def test_home_signal_is_single_card(self):
        """홈 최신 신호는 1건 카드(그림 2-가). 목록(x-for signals)이 아니므로 kind-id 키가 필요 없다."""
        html, js = _read("index.html"), _read("app.js")
        self.assertIn("/v2/api/signals?limit=1", js)
        self.assertNotRegex(html, r'x-for="[^"]*\bin signals\b')
        self.assertIn("signalCard.title", html)

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
