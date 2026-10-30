"""
1029-09 「시간 밖 손절 허용」 (사용자 결정 1029-08 「권고대로」, Fable 2026-10-30-1029-09-decision-1).

새 전략(PULLBACK) 「시간 밖에도 익절」(allow_sell_during_off_hours) 이 꺼져 있고 거래 시간 밖인 봉:
- 익절(TP) 만 막는다 — 거래 정리 안 함(보유·회차 그대로) → 열린 첫 봉에서 다시 평가. 감사 blocked_signal="SELL:TP".
- 손절(SL)·데드크로스(DEADCROSS) 는 늘 판다.
- 같은 봉에서 TP·SL 이 둘 다 닿으면 TP 는 막고 SL 로 판다(PO 결정 1). blocked_signal="SELL:TP" 는 남기고(권고 4)
  [PULLBACK-HOURS] 로그는 「익절 막음 → 손절로 매도」.
- 재생(워밍업·BACKFILL)도 같은 _step — 판정 상태 = 실시간 경로.
- 잠금 해제: 화면·서버·엔진 어디에도 sell_off_locked 가 없다.
- 고정 파일 core/strategy_pullback.py: 바이트 비교 대신 PULLBACK_RULES_BASE_COMMIT(8464b58) AST 비교(Fable 막음 1).

시험 봉 시각: ts_at(i) = 09:00 KST + 3i 분, 판정 시각(봉 마감) = 09:03 + 3i 분 (KST).

실행:
    TELEGRAM_BOT_TOKEN= TELEGRAM_CHAT_ID= TELEGRAM_CHAT_ID_OPERATOR= \
        python3 -m unittest tests.regressions.test_r_2026_10_30_1029_09_off_hours_tp -v
"""
from __future__ import annotations

import ast
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402,F401
from core import strategy_engine as se  # noqa: E402
from core.strategy_action import Action  # noqa: E402
from tests.regressions import baseline_commits as bc  # noqa: E402
from tests.regressions.test_r_2026_10_28_p3_t4_pullback_rules import DEAD, V, make_strategy, ts_at  # noqa: E402
from tests.regressions.test_r_2026_10_28_p3_t4_pullback_rules import bar as sbar  # noqa: E402
from tests.regressions.test_r_2026_10_28_p3_t5_pullback_engine import CALM, DIP, EngineCase, bar  # noqa: E402

PULLBACK_REL = "core/strategy_pullback.py"


def hours(start, end, allow_sell):
    return {"enable_trading_hours": True, "trading_start_time": start, "trading_end_time": end,
            "allow_sell_during_off_hours": allow_sell}


# 봉 0~8(마감 09:03~09:27) 시간 밖, 봉 9(마감 09:30)부터 안
OFF_UNTIL_0930 = dict(start="09:30", end="02:00")
# 보유 상태(평단 100 — tp 5% → 105, sl 3% → 97), 첫 체결 봉 = 봉 0 → 봉 1 부터 TP/SL 평가
HOLDING = {"entry_count": 1, "pullback_count": 1, "first_entry_ts": ts_at(0), "first_entry_reason": "PULLBACK",
           "fill_n": 1, "inv_sum": 1 / 100.0, "trade_origin": "replay", "prev_golden": True, "last_ts": ts_at(0)}
TP_BAR = dict(o=104, h=106, l=103, c=105)      # high 106 ≥ 105, low 103 > 97
SL_BAR = dict(o=99, h=99, l=96, c=98)          # low 96 ≤ 97, high 99 < 105
BOTH_BAR = dict(o=100, h=106, l=96, c=100)     # 둘 다 닿음


def holding_strategy(values, allow_sell, *, enable=True, **window):
    w = dict(OFF_UNTIL_0930, **window)
    over = hours(w["start"], w["end"], allow_sell)
    over["enable_trading_hours"] = enable
    st = make_strategy(values, **over)
    st.restore_split_state(dict(HOLDING))
    return st


# ================================================================ 1. 전략 판정 — 익절만 막음
class TestOffHoursSellRules(unittest.TestCase):
    def test_sl_sells_off_hours_when_setting_off(self):
        st = holding_strategy([V()], False)
        self.assertTrue(st._off_hours(ts_at(1)))
        self.assertIs(st.on_bar(sbar(1, **SL_BAR), {}, None, 0), Action.SELL)
        self.assertEqual(st.last_sell_reason, "SL")
        self.assertEqual(st.entry_count, 0)                         # 거래 정리
        self.assertIsNone(st.last_eval["blocked_signal"])
        self.assertEqual(st.last_eval["failed_keys"], [])
        self.assertEqual(st.last_eval["exit_round"], 1)

    def test_deadcross_sells_off_hours_when_setting_off(self):
        st = holding_strategy([V(**DEAD)], False)
        self.assertIs(st.on_bar(sbar(1, o=100, h=101, l=99, c=100), {}, None, 0), Action.SELL)
        self.assertEqual(st.last_sell_reason, "DEADCROSS")
        self.assertEqual(st.entry_count, 0)
        self.assertIsNone(st.last_eval["blocked_signal"])

    def test_deadcross_with_tp_bar_still_deadcross(self):
        """데드크로스가 TP 보다 먼저(원본 순서) — 시간 밖·꺼짐이어도 DEADCROSS 로 판다(익절 막음과 무관)."""
        st = holding_strategy([V(**DEAD)], False)
        self.assertIs(st.on_bar(sbar(1, **TP_BAR), {}, None, 0), Action.SELL)
        self.assertEqual(st.last_sell_reason, "DEADCROSS")
        self.assertIsNone(st.last_eval["blocked_signal"])

    def test_tp_blocked_off_hours_keeps_trade_then_sells_when_open(self):
        st = holding_strategy([V(), V()], False)
        with self.assertLogs("core.strategy_pullback", level="INFO") as cm:
            a = st.on_bar(sbar(1, **TP_BAR), {}, None, 0)
        self.assertIsNot(a, Action.SELL)
        self.assertEqual(st.entry_count, 1)                         # 정리 안 함
        self.assertEqual(st.pullback_count, 1)
        self.assertEqual(st.last_eval["failed_keys"], ["OFF_HOURS"])
        self.assertEqual(st.last_eval["blocked_signal"], "SELL:TP")
        self.assertNotIn("exit_round", st.last_eval)
        hours_logs = [m for m in cm.output if "[PULLBACK-HOURS]" in m]
        self.assertEqual(len(hours_logs), 1)
        self.assertIn("SELL:TP 주문 막음", hours_logs[0])
        self.assertNotIn("손절로 매도", hours_logs[0])
        failed, checks = st.audit_view()
        self.assertEqual(failed, ["OFF_HOURS"])
        self.assertEqual(checks["blocked_signal"], "SELL:TP")
        self.assertIsNone(checks["sell_reason"])
        # 봉 9(마감 09:30) = 시간 안 → 익절
        self.assertFalse(st._off_hours(ts_at(9)))
        self.assertIs(st.on_bar(sbar(9, **TP_BAR), {}, None, 0), Action.SELL)
        self.assertEqual(st.last_sell_reason, "TP")

    def test_tp_and_sl_same_bar_sells_sl_keeps_tp_mark(self):
        """PO 결정 1 + 권고 4: 같은 봉 TP·SL → TP 막고 SL 로 매도, blocked_signal="SELL:TP", 로그 「익절 막음 → 손절로 매도」."""
        st = holding_strategy([V()], False)
        with self.assertLogs("core.strategy_pullback", level="INFO") as cm:
            a = st.on_bar(sbar(1, **BOTH_BAR), {}, None, 0)
        self.assertIs(a, Action.SELL)
        self.assertEqual(st.last_sell_reason, "SL")
        self.assertEqual(st.entry_count, 0)                         # 손절 매도 = 거래 정리
        ev = st.last_eval
        self.assertEqual((ev["signal"], ev["reason"]), ("SELL", "SL"))
        self.assertEqual(ev["blocked_signal"], "SELL:TP")
        self.assertEqual(ev["failed_keys"], [])
        self.assertEqual(ev["exit_round"], 1)
        hours_logs = [m for m in cm.output if "[PULLBACK-HOURS]" in m]
        self.assertEqual(len(hours_logs), 1)
        self.assertIn("SELL:TP 익절 막음 → 손절로 매도", hours_logs[0])
        failed, checks = st.audit_view()
        self.assertEqual(failed, [])
        self.assertEqual((checks["sell_reason"], checks["blocked_signal"]), ("SL", "SELL:TP"))

    def test_setting_on_unchanged(self):
        """켜짐(기본): 시간 밖에도 TP 매도, 같은 봉 TP·SL 은 원본대로 TP."""
        for b, reason in ((TP_BAR, "TP"), (BOTH_BAR, "TP"), (SL_BAR, "SL")):
            with self.subTest(reason=reason, bar=b):
                st = holding_strategy([V()], True)
                self.assertIs(st.on_bar(sbar(1, **b), {}, None, 0), Action.SELL)
                self.assertEqual(st.last_sell_reason, reason)
                self.assertIsNone(st.last_eval["blocked_signal"])

    def test_in_hours_unchanged_when_setting_off(self):
        """꺼짐이어도 시간 안 봉은 그대로: 같은 봉 TP·SL → TP."""
        st = holding_strategy([V()], False)
        st.restore_split_state(dict(HOLDING, first_entry_ts=ts_at(8), last_ts=ts_at(8)))
        self.assertIs(st.on_bar(sbar(9, **BOTH_BAR), {}, None, 0), Action.SELL)
        self.assertEqual(st.last_sell_reason, "TP")
        self.assertIsNone(st.last_eval["blocked_signal"])

    def test_hours_disabled_ignores_setting(self):
        """거래 시간 제한 꺼짐이면 「시간 밖에도 익절」 값과 무관 — TP 매도."""
        st = holding_strategy([V()], False, enable=False)
        self.assertFalse(st._off_hours(ts_at(1)))
        self.assertIs(st.on_bar(sbar(1, **TP_BAR), {}, None, 0), Action.SELL)
        self.assertEqual(st.last_sell_reason, "TP")


# ================================================================ 2. 재생 = 실시간 (꺼짐)
class TestReplayParityOffHoursTp(unittest.TestCase):
    def test_replay_matches_live_with_tp_block_and_sl(self):
        vals = [V()] * 6
        bars = [sbar(1, **TP_BAR), sbar(2, o=100, h=101, l=99, c=100), sbar(3, **BOTH_BAR),
                sbar(4, o=100, h=101, l=99, c=100), sbar(5, **SL_BAR), sbar(6)]
        live = holding_strategy(vals, False)
        rep = holding_strategy(vals, False)
        keys = ("armed", "prev_golden", "entry_count", "pullback_count", "first_entry_reason", "pending_fill",
                "fill_n", "inv_sum")
        live_signals = []
        for b in bars:
            live.on_bar(b, {}, None, 0)
            rep.replay_bar(b, rep.indicators.update(b.close))
            self.assertEqual({k: getattr(live, k) for k in keys}, {k: getattr(rep, k) for k in keys}, b.ts)
            sig = f"{live.last_eval['signal']}:{live.last_eval['reason']}" if live.last_eval.get("signal") else None
            self.assertEqual(rep.last_eval.get("replay_signal"), sig, b.ts)
            self.assertEqual(rep.last_eval.get("blocked_signal"), live.last_eval.get("blocked_signal"), b.ts)
            live_signals.append((sig, live.last_eval.get("blocked_signal")))
        # 봉 1 TP 막힘(보유 유지) → 봉 3 같은 봉 TP·SL → SL 매도(TP 표식) → 그 뒤 보유 없음
        self.assertEqual(live_signals[0], (None, "SELL:TP"))
        self.assertEqual(live_signals[2], ("SELL:SL", "SELL:TP"))
        self.assertEqual(rep.last_eval["failed_keys"], ["REPLAY"])


# ================================================================ 3. 엔진 경로 — 실제 매도 주문
class TestEngineOffHoursSell(EngineCase):
    """t9 test_sell_allowed_off_hours 와 같은 틀: 봉 0 시간 안 매수, 봉 1·2 시간 밖(09:12~09:06), 봉 3 부터 안.
    엔진 CFG sl 90% → 평단 55 의 손절가 5.5."""

    def _buy_then(self, b2):
        self.make(**hours("09:12", "09:06", False))
        self.assertIs(self.feed(bar(0, **DIP)), Action.BUY)
        self.feed(bar(1, **CALM))                                   # 체결 봉(시간 밖)
        return self.feed(bar(2, **b2))                              # 시간 밖

    def test_engine_sl_sells_off_hours(self):
        a = self._buy_then(dict(o=55, h=56, l=5, c=50))
        self.assertIs(a, Action.SELL)
        self.assertEqual(len(self.trader.sell_calls), 1)
        self.assertEqual(self.strat.last_sell_reason, "SL")
        kw = se.insert_sell_eval.call_args_list[-1].kwargs
        self.assertTrue(kw["triggered"])
        self.assertIsNone(kw["checks"]["blocked_signal"])

    def test_engine_tp_and_sl_same_bar_sells_sl(self):
        a = self._buy_then(dict(o=55, h=60, l=5, c=58))
        self.assertIs(a, Action.SELL)
        self.assertEqual(len(self.trader.sell_calls), 1)
        self.assertEqual(self.strat.last_sell_reason, "SL")
        kw = se.insert_sell_eval.call_args_list[-1].kwargs
        self.assertTrue(kw["triggered"])
        self.assertEqual(kw["checks"]["blocked_signal"], "SELL:TP")
        self.assertEqual(kw["checks"]["sell_reason"], "SL")

    def test_engine_tp_blocked_no_order(self):
        a = self._buy_then(dict(o=55, h=60, l=54, c=58))
        self.assertIsNot(a, Action.SELL)
        self.assertEqual(self.trader.sell_calls, [])
        self.assertTrue(self.eng.position.has_position)


# ================================================================ 4. 잠금 해제 — 남은 막음 0곳
class TestUnlocked(unittest.TestCase):
    def test_no_sell_off_lock_left(self):
        """sell_off_locked·SELL_OFF_NOTE·sell_off_changed·「시간 밖에도 매도」 가 운영 코드 어디에도 없다."""
        needles = ("sell_off_locked", "SELL_OFF_NOTE", "sell_off_changed", "시간 밖에도 매도",
                   "시간 밖 손절 처리 결정 뒤")
        hits = []
        for d in ("core", "engine", "services", "v2", "pages", "ui", "scripts"):
            for p in (ROOT / d).rglob("*"):
                if not p.is_file() or p.suffix not in (".py", ".js", ".html", ".mjs", ".sh"):
                    continue
                text = p.read_text(encoding="utf-8", errors="ignore")
                hits += [(p.relative_to(ROOT).as_posix(), n) for n in needles if n in text]
        self.assertEqual(hits, [])

    def test_html_sell_off_input_editable_like_other_inputs(self):
        html = (ROOT / "v2/static/index.html").read_text(encoding="utf-8")
        tag = re.search(r"<input\b[^>]*data-sell-off\b[^>]*>", html).group(0)
        self.assertIn('x-model="opsForm.sellOff"', tag)
        self.assertIn('@change="opsDirty = true"', tag)
        self.assertIn(':disabled="!opsView.opsSave.enabled"', tag)
        self.assertNotRegex(tag, r"\sdisabled(\s|>|$)")
        self.assertIn("<span>시간 밖에도 익절</span>", html)
        self.assertIn("손절·데드크로스는 시간 밖에도 늘 팝니다", html)

    def test_read_label_renamed(self):
        from v2 import api_read
        labels = [v for k, v in vars(api_read).items() if isinstance(v, dict) and "allow_sell_during_off_hours" in v]
        self.assertTrue(labels)
        for d in labels:
            self.assertEqual(d["allow_sell_during_off_hours"], "시간 밖에도 익절")


# ================================================================ 5. 고정 파일 — AST 비교 (Fable 막음 1)
def _strip_docstrings(tree):
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) \
                    and isinstance(first.value.value, str):
                node.body[0] = ast.Pass()
    return tree


def _step_node(tree):
    cls = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "IncrementalPullbackStrategy"]
    assert len(cls) == 1, "IncrementalPullbackStrategy 클래스 1개"
    steps = [n for n in cls[0].body if isinstance(n, ast.FunctionDef) and n.name == "_step"]
    assert len(steps) == 1, "_step 1개"
    return steps[0]


def _has_const(node, pred):
    return any(isinstance(n, ast.Constant) and isinstance(n.value, str) and pred(n.value) for n in ast.walk(node))


def _is_block_if(stmt):
    return isinstance(stmt, ast.If) and _has_const(stmt.test, lambda s: s == "allow_sell_during_off_hours")


def _is_log_if(stmt):
    return isinstance(stmt, ast.If) and _has_const(stmt, lambda s: "[PULLBACK-HOURS]" in s)


# verifier 지적 1 (PO 결정 가): 비교에서 뺀 두 If 는 「지금 모양」 그대로여야 한다 — 기대 소스 조각을 시험에 글로 두고
# ast.parse 해 dump 비교(주석은 AST 에 없음). 두 If 안에 부작용(armed·회차 바꾸기 등)을 넣으면 여기서 잡힌다.
EXPECTED_BLOCK_IF = '''
if signal == ("SELL", "TP") and off and not c["allow_sell_during_off_hours"]:
    blocked = signal
    signal = None
    if bar.low <= sl_price:
        signal = ("SELL", "SL")
'''
EXPECTED_LOG_IF = '''
if blocked is not None and live:
    logger.info(f"[PULLBACK-HOURS] 거래 시간 밖 — {blocked[0]}:{blocked[1]} "
                f"{'익절 막음 → 손절로 매도' if signal is not None else '주문 막음'} "
                f"(armed={self.armed} 회차={self.entry_count}) | 판정 시각(봉 마감 KST)="
                f"{format_kst(pd.Timestamp(bar.ts) + pd.Timedelta(minutes=self.interval_min))} "
                f"| 거래 시간 {c['trading_start_time']}~{c['trading_end_time']}")
'''


def _expected_if(src: str) -> ast.If:
    body = ast.parse(src).body
    assert len(body) == 1 and isinstance(body[0], ast.If)
    return body[0]


def check_excluded_ifs(now_src: str) -> list:
    """지금 파일 _step 의 막음 If·로그 If 가 기대 모양과 같은지. 다른 점 목록(비면 같음)."""
    diffs = []
    step = _step_node(ast.parse(now_src))
    blocks = [s for s in step.body if _is_block_if(s)]
    logs = [s for s in step.body if _is_log_if(s)]
    if len(blocks) != 1 or len(logs) != 1:
        return [f"_step 의 막음 If {len(blocks)}개·로그 If {len(logs)}개 (각 1개여야 함)"]
    exp_b, exp_l = _expected_if(EXPECTED_BLOCK_IF), _expected_if(EXPECTED_LOG_IF)
    if ast.dump(blocks[0].test) != ast.dump(exp_b.test):
        diffs.append("막음 If 조건식이 기대와 다르다")
    if [ast.dump(s) for s in blocks[0].body] != [ast.dump(s) for s in exp_b.body] or blocks[0].orelse:
        diffs.append("막음 If 몸통이 기대와 다르다")
    if ast.dump(logs[0].test) != ast.dump(exp_l.test):
        diffs.append("로그 If 조건식이 기대와 다르다")
    lb = logs[0].body
    fn = lb[0].value.func if (len(lb) == 1 and isinstance(lb[0], ast.Expr) and isinstance(lb[0].value, ast.Call)) \
        else None
    if not (isinstance(fn, ast.Attribute) and fn.attr == "info"
            and isinstance(fn.value, ast.Name) and fn.value.id == "logger"):
        diffs.append("로그 If 몸통이 logger.info 호출 하나가 아니다")
    if [ast.dump(s) for s in lb] != [ast.dump(s) for s in exp_l.body] or logs[0].orelse:
        diffs.append("로그 If 몸통(인자 포함)이 기대와 다르다")
    return diffs


def compare_pullback_ast(base_src: str, now_src: str) -> list:
    """다른 점 목록(비면 같음). (1) 모듈 전체(docstring 제외, _step 몸통만 Pass) (2) _step 은 시간 밖 막음 If·
    [PULLBACK-HOURS] 로그 If 를 뺀 문장 목록 — 각 1개씩 있어야 함 (3) 뺀 두 If 는 기대 모양 그대로(check_excluded_ifs)."""
    diffs = list(check_excluded_ifs(now_src))
    trees = []
    for src in (base_src, now_src):
        t = _strip_docstrings(ast.parse(src))
        step = _step_node(t)
        body = list(step.body)
        blocks = [s for s in body if _is_block_if(s)]
        logs = [s for s in body if _is_log_if(s)]
        if len(blocks) != 1 or len(logs) != 1:
            diffs.append(f"_step 의 막음 If {len(blocks)}개·로그 If {len(logs)}개 (각 1개여야 함)")
        rest = [ast.dump(s) for s in body if not (_is_block_if(s) or _is_log_if(s))]
        step.body = [ast.Pass()]
        trees.append((ast.dump(t), rest))
    if trees[0][0] != trees[1][0]:
        diffs.append("모듈(_step 몸통 밖)이 기준과 다르다")
    if trees[0][1] != trees[1][1]:
        diffs.append("_step 의 막음·로그 If 밖 문장이 기준과 다르다")
    return diffs


# 기준(8464b58) 파일의 줄 번호 — 바뀌어도 되는 곳: 막음 블록 주석·If(724-731), 로그 문구(800), audit_view 주석(842)
ALLOWED_OLD_RANGES = ((724, 731), (800, 800), (842, 842))
NEW_LINES_CAP = {(724, 731): 6, (800, 800): 2, (842, 842): 1}


class TestPullbackRulesFixed(unittest.TestCase):
    def base_src(self):
        src = bc.git_show(PULLBACK_REL, bc.PULLBACK_RULES_BASE_COMMIT)
        self.assertIsNotNone(src, f"git show {bc.PULLBACK_RULES_BASE_COMMIT}:{PULLBACK_REL} 실패")
        return src

    def test_pullback_ast_same_except_off_hours_block(self):
        now = (ROOT / PULLBACK_REL).read_text(encoding="utf-8")
        self.assertEqual(compare_pullback_ast(self.base_src(), now), [])

    def test_git_diff_hunks_inside_allowed_lines(self):
        out = subprocess.run(["git", "-C", str(ROOT), "diff", "-U0", bc.PULLBACK_RULES_BASE_COMMIT, "--", PULLBACK_REL],
                             capture_output=True, check=True, text=True).stdout
        hunks = re.findall(r"^@@ -(\d+)(?:,(\d+))? \+\d+(?:,(\d+))? @@", out, re.M)
        bad = []
        new_lines = {w: 0 for w in ALLOWED_OLD_RANGES}
        for start, count, new_count in hunks:
            a = int(start)
            n = 1 if count == "" else int(count)
            lo, hi = (a, a) if n == 0 else (a, a + n - 1)       # n == 0: a 줄 뒤에 넣음
            win = [w for w in ALLOWED_OLD_RANGES if w[0] <= lo and hi <= w[1]]
            if not win:
                bad.append((lo, hi))
                continue
            new_lines[win[0]] += 1 if new_count == "" else int(new_count)
        self.assertEqual(bad, [], out)
        # verifier 지적 1-2: 새 쪽 줄 수 상한(지금 실제 값, 여유 없음) — 막음 블록 6·로그 2·audit_view 주석 1
        over = {w: n for w, n in new_lines.items() if n > NEW_LINES_CAP[w]}
        self.assertEqual(over, {}, out)

    def test_ast_guard_catches_mutations(self):
        """변이 2건(Fable 막음 1): 모듈 수준 _SPLIT_DEFAULTS 값, 같은 이름 __init__ 중 PullbackSnapshotRing.__init__ 한 줄."""
        now = (ROOT / PULLBACK_REL).read_text(encoding="utf-8")
        base = self.base_src()
        muts = {
            "split_defaults": ('"armed": False, "prev_golden": False,', '"armed": True, "prev_golden": False,'),
            "ring_init": ("        self._q: deque = deque(maxlen=self.capacity)",
                          "        self._q: deque = deque(maxlen=self.capacity + 1)"),
            "step_other_stmt": ("        tp_price = avg * (1 + c[\"tp\"] / 100) if avg is not None else None",
                                "        tp_price = avg * (1 + c[\"tp\"] / 99) if avg is not None else None"),
            # verifier 지적 1-3: 비교에서 뺀 두 If 안 부작용 주입
            "block_if_side_effect": ("            signal = None\n", "            signal = None; self.armed = False\n"),
            "log_if_side_effect": ("{c['trading_start_time']}~{c['trading_end_time']}\")\n",
                                   "{c['trading_start_time']}~{c['trading_end_time']}\"); self.pullback_count = 0\n"),
            "block_if_cond": ('if signal == ("SELL", "TP") and off and not',
                              'if signal == ("SELL", "TP") and off and live and not'),
            "log_if_cond": ("        if blocked is not None and live:\n", "        if blocked is not None:\n"),
        }
        for name, (old, new) in muts.items():
            with self.subTest(name):
                self.assertEqual(now.count(old), 1, name)
                self.assertNotEqual(compare_pullback_ast(base, now.replace(old, new)), [], name)


if __name__ == "__main__":
    unittest.main()
