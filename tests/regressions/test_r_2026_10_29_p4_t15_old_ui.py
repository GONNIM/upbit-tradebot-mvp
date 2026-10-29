"""
2차 T15 (2026-10-29): 구버전 화면 — 새 전략(PULLBACK) 표시 경로·배지·잠금·강제 매수/매도·D10.

결정: D7·D10, 사용자 결정 1029-10(C2 나·C3 ①+②), PO 결정 C1-a·C1-b·C4, Fable 권고 5·7
(docs/fable/2026-10-29-phase2-t15-decision-1.md). 계획 plan-phase2.md §T15.

핵심 고정:
  - 잠기지 않은 EMA 화면(예약 없는 EMA 사용자)은 8464b58 원본 dashboard·set_config·조건 화면과 같다(AppTest 비교).
  - 새 전략 운용·예약 중에는 설정 저장·전략 변경·수동 엔진 시작·초기화·복원이 잠기고, 강제 매수·매도·엔진 정지·
    설정 화면 이동·감사 로그 뷰어·자동 재개는 열려 있다.
  - D10·C1-a: 새 전략 보유(TEST 행)·예약 중에는 운용자산·TEST 현금을 덮어쓰지 않는다.

실행:
    python3 -m unittest tests.regressions.test_r_2026_10_29_p4_t15_old_ui -v
"""
from __future__ import annotations

import ast
import json
import os
import shutil
import re
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from tests.regressions.baseline_commits import OLD_UI_BASE_COMMIT as BASE_COMMIT  # T14 커밋 — T15 직전 원본
USER = "t15user"

APPLIED = {"ticker": "KRW-ZRO", "interval": "minute3", "maType": "ema", "ma60p": 60, "ma200p": 200,
           "pullbackP": 20, "slopeLB": 10, "minSlope": 0, "slopeDrop": 0, "buyOnGoldenCross": False,
           "maxSplits": 5, "maxPullbackBuys": 3, "tp": 5, "sl": 3, "deadcross": True, "compounding": False,
           "capital": 1000000, "fee": 0.05}
EMA_PARAMS = {"ticker": "JTO", "interval": "minute1", "fast_period": 7, "slow_period": 25, "signal_period": 9,
              "take_profit": 0.05, "stop_loss": 0.03, "cash": 1000000, "commission": 0.0005,
              "order_ratio": 0.1, "strategy_type": "EMA"}


def _git_show(rel: str) -> str:
    from tests.regressions.baseline_commits import git_show
    src = git_show(rel, BASE_COMMIT)
    if src is None:
        raise unittest.SkipTest("git 이력 없음 — 기준 커밋 원본을 읽지 못함")
    return src


def _fake_ohlcv(ticker, interval, count=2, **kw):
    import pandas as pd
    idx = pd.date_range("2026-10-29 09:00", periods=max(int(count or 2), 2), freq="min", tz="Asia/Seoul")
    return pd.DataFrame({"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.0, "Volume": 1.0}, index=idx)


class _Base(unittest.TestCase):
    def setUp(self):
        import config  # noqa: F401  — .env/secrets 로드 후 cwd 이동
        import services.db  # noqa: F401
        import services.init_db  # noqa: F401
        import engine.params  # noqa: F401
        self._cwd = os.getcwd()
        self.tmpdir = Path(tempfile.mkdtemp(prefix="t15_"))
        self.db_path = str(self.tmpdir / f"tradebot_{USER}.db")
        self.notify = MagicMock(return_value=True)
        self._patchers = [
            patch("services.init_db.get_db_path", return_value=self.db_path),
            patch("services.db.get_db_path", return_value=self.db_path),
            patch("services.notifier.send", self.notify),
            patch("core.data_feed.get_ohlcv_once", side_effect=_fake_ohlcv),
        ]
        for p in self._patchers:
            p.start()
        from services.init_db import initialize_db, ensure_all_schemas, ensure_pullback_tables
        from services.db import ensure_schema
        initialize_db(USER)
        ensure_all_schemas(USER)
        ensure_schema(USER)
        ensure_pullback_tables(USER)
        os.chdir(self.tmpdir)

    def tearDown(self):
        os.chdir(self._cwd)
        for p in self._patchers:
            p.stop()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    # ---------------------------------------------------------------- 준비
    def sql(self, q, args=()):
        conn = sqlite3.connect(self.db_path)
        try:
            cur = conn.execute(q, args)
            conn.commit()
            return cur.fetchall()
        finally:
            conn.close()

    def set_capital(self, krw=1_000_000):
        self.sql("INSERT OR REPLACE INTO users (username, display_name, virtual_krw, updated_at) "
                 "VALUES (?, ?, ?, '2026-10-29T00:00:00+09:00')", (USER, "옛이름", krw))

    @staticmethod
    def cash(krw):
        """TEST 가상 현금(accounts.virtual_krw) — 행을 만든 뒤 값."""
        from services.db import create_or_init_account, update_account
        create_or_init_account(USER, krw)
        update_account(USER, krw)

    def ema(self):
        (self.tmpdir / f"{USER}_active_strategy.txt").write_text("EMA")
        (self.tmpdir / f"{USER}_latest_params_EMA.json").write_text(json.dumps(EMA_PARAMS))
        self.set_capital()

    def pullback(self, entry=0, qty=0.0, pending=0, applied=None):
        (self.tmpdir / f"{USER}_active_strategy.txt").write_text("PULLBACK")
        (self.tmpdir / f"{USER}_applied_params_PULLBACK.json").write_text(json.dumps(dict(APPLIED, **(applied or {}))))
        self.set_capital()
        self.state_row("TEST", entry=entry, qty=qty, pending=pending)

    def state_row(self, mode, entry=0, qty=0.0, pending=0):
        self.sql("INSERT OR REPLACE INTO pullback_state (user_id, mode, ticker, interval, entry_count, qty, pending_fill, "
                 "updated_at) VALUES (?, ?, 'KRW-ZRO', 'minute3', ?, ?, ?, '2026-10-29T00:00:00+09:00')",
                 (USER, mode, entry, qty, pending))

    def reserve(self, mode="TEST", kind="SWITCH"):
        self.sql("INSERT INTO strategy_switch (user_id, mode, kind, from_strategy, to_strategy, state, requested_at) "
                 "VALUES (?, ?, ?, 'EMA', 'PULLBACK', 'RESERVED', '2026-10-29T00:00:00+09:00')", (USER, mode, kind))

    def page(self, rel, src=None, **qp):
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(src or str(ROOT / rel), default_timeout=120)
        for k, v in qp.items():
            at.query_params[k] = v
        at.session_state["user_id"] = USER
        at.run()
        self.assertEqual([e.value for e in at.exception], [], f"{rel} 렌더 예외")
        return at

    def original(self, rel) -> str:
        p = self.tmpdir / ("orig_" + rel.replace("/", "_"))
        p.write_text(_git_show(rel), encoding="utf-8")
        return str(p)

    def dash(self, src=None, **qp):
        q = dict(user_id=USER, mode="TEST", virtual_krw="1000000")
        q.update(qp)
        return self.page("pages/dashboard.py", src=src, **q)

    @staticmethod
    def btn(at, key):
        for b in at.button:
            if b.key == key:
                return b
        return None

    @staticmethod
    def texts(at, kinds=("info", "warning", "error", "success", "caption", "markdown")):
        out = []
        for k in kinds:
            out += [str(getattr(e, "value", "")) for e in getattr(at, k)]
        return out

    @staticmethod
    def stable_view(at):
        """시각·임시 경로·배포 버전 문자열처럼 렌더마다(커밋마다) 바뀌는 글자를 뺀 화면 요약."""
        def ok(s):
            return not any(t in s for t in ("현재 시각", "DB file", "저장 시각", "updated_at"))

        def norm(s):
            # 커밋마다 올리는 dashboard 버전(v1.YYYY.MM.DD.HHMM)은 비교에서 뺀다
            return re.sub(r"v1\.\d{4}\.\d{2}\.\d{2}\.\d{4}", "v1.<ver>", s)
        return {
            "buttons": [(b.label, b.key, b.disabled) for b in at.button],
            "expanders": [e.label for e in at.expander],
            "metrics": [(m.label, m.value) for m in at.metric],
            "selectbox": [(s.label, s.disabled) for s in at.selectbox],
            "texts": [norm(t) for t in _Base.texts(at) if ok(t)],
        }


# ==================================================================== EMA 화면 = 원본
class TestEmaUnchanged(_Base):
    def test_ema_dashboard_render_same_as_base(self):
        self.ema()
        new = self.stable_view(self.dash())
        old = self.stable_view(self.dash(src=self.original("pages/dashboard.py")))
        self.assertEqual(new, old)
        self.assertFalse(any("새 전략" in t or "전환 예약" in t for t in new["texts"]))

    def test_ema_dashboard_live_render_same_as_base(self):
        self.ema()
        new = self.stable_view(self.dash(mode="LIVE"))
        old = self.stable_view(self.dash(src=self.original("pages/dashboard.py"), mode="LIVE"))
        self.assertEqual(new, old)

    def _force_calls(self, src, key, fn_name):
        import core.trader
        import services.trading_control as tc
        trader_cls = MagicMock(name="UpbitTrader")
        fn = MagicMock(return_value="[TEST] ok")
        with patch.object(core.trader, "UpbitTrader", trader_cls), patch.object(tc, fn_name, fn):
            at = self.dash(src=src)
            at.button(key=key).click().run()
        return trader_cls.call_args_list, fn.call_args_list

    def test_ema_force_buy_call_same_as_base(self):
        self.ema()
        new = self._force_calls(None, "btn_force_buy", "force_buy_in")
        old = self._force_calls(self.original("pages/dashboard.py"), "btn_force_buy", "force_buy_in")
        self.assertEqual(len(new[1]), 1)
        self.assertEqual([c.kwargs for c in new[0]], [c.kwargs for c in old[0]])
        self.assertEqual([(c.args[2:], {k: v for k, v in c.kwargs.items()}) for c in new[1]],
                         [(c.args[2:], {k: v for k, v in c.kwargs.items()}) for c in old[1]])
        self.assertEqual(new[1][0].kwargs["strategy_type"], "EMA")

    def test_ema_force_sell_call_same_as_base(self):
        self.ema()
        from services.db import update_coin_position
        update_coin_position(USER, "KRW-JTO", 100.0)
        new = self._force_calls(None, "btn_force_sell", "force_liquidate")
        old = self._force_calls(self.original("pages/dashboard.py"), "btn_force_sell", "force_liquidate")
        self.assertEqual(len(new[1]), 1)
        self.assertEqual([c.kwargs for c in new[0]], [c.kwargs for c in old[0]])
        self.assertEqual([c.args[2:] for c in new[1]], [c.args[2:] for c in old[1]])

    def test_ema_test_account_sync_unchanged(self):
        """예약 없는 EMA TEST: 지금처럼 URL 운용자산으로 TEST 현금을 맞춘다(C1-a 는 잠김일 때만)."""
        self.ema()
        from services.db import update_account, get_account
        self.cash(700_000)
        self.dash()
        self.assertEqual(get_account(USER), 1_000_000)

    def test_ema_set_config_same_as_base(self):
        self.ema()
        q = dict(user_id=USER, mode="TEST", virtual_krw="1000000", strategy_type="EMA")
        # 첫 렌더는 `from pages.audit_viewer import query` 가 감사 뷰어를 한 번 그린다(모듈 캐시 전) — 데운 뒤 비교
        self.page("pages/set_config.py", **q)
        old = self.stable_view(self.page("pages/set_config.py", src=self.original("pages/set_config.py"), **q))
        new = self.stable_view(self.page("pages/set_config.py", **q))
        self.assertEqual(new, old)

    def test_ema_conditions_page_same_as_base(self):
        self.ema()
        q = dict(user_id=USER, mode="TEST", virtual_krw="1000000", strategy="EMA")
        rel = "pages/set_buy_sell_conditions.py"
        new = self.stable_view(self.page(rel, **q))
        old = self.stable_view(self.page(rel, src=self.original(rel), **q))
        self.assertEqual(new, old)

    def test_url_strategy_pullback_ignored(self):
        """T5·T11 넘김: 활성 파일이 PULLBACK 이 아니면 URL·세션의 PULLBACK 값은 받지 않는다(기본 전략으로)."""
        (self.tmpdir / f"{USER}_latest_params_MACD.json").write_text(json.dumps(dict(EMA_PARAMS, strategy_type="MACD")))
        (self.tmpdir / f"{USER}_latest_params_PULLBACK.json").write_text(json.dumps(dict(EMA_PARAMS, ticker="ZRO")))
        self.set_capital()
        at = self.dash(strategy_type="PULLBACK")
        m = dict((x.label, x.value) for x in at.metric)
        self.assertEqual(m["전략 타입"], "MACD")
        self.assertEqual(m["🎯 거래 종목"], "KRW-JTO")
        self.assertFalse(any(i.value.startswith("새 전략") for i in at.info))

    def test_ema_unlocked_buttons_enabled(self):
        self.ema()
        at = self.dash()
        for key in ("btn_start_engine", "btn_config", "btn_reset_system", "btn_force_buy", "btn_force_sell"):
            self.assertFalse(self.btn(at, key).disabled, key)


# ==================================================================== 새 전략 표시 경로
class TestPullbackDashboard(_Base):
    def test_old_dashboard_no_stop_on_pullback(self):
        """활성 PULLBACK·EMA/MACD 파일 없음 → st.stop 없이 끝까지 그린다(감사 로그 단추까지)."""
        self.pullback()
        at = self.dash()
        self.assertIsNotNone(self.btn(at, "btn_audit_log"))
        self.assertFalse(any("파라미터가 없습니다" in t for t in self.texts(at)))

    def test_old_dashboard_badge_pullback(self):
        self.pullback()
        at = self.dash()
        self.assertIn("새 전략(눌림목 분할매수) 운용 중 — 설정은 신버전에서 관리합니다", [i.value for i in at.info])

    def test_old_dashboard_status_round(self):
        self.pullback(entry=2, qty=10.0)
        at = self.dash()
        cap = [c.value for c in at.caption if c.value.startswith("상태 (보기만)")]
        self.assertEqual(len(cap), 1)
        self.assertIn("눌림목 분할매수", cap[0])
        self.assertIn("2 / 5회", cap[0])
        self.assertIn("KRW-ZRO", cap[0])

    def test_pullback_shows_applied_values(self):
        self.pullback(applied={"tp": 4, "sl": 2})
        at = self.dash()
        m = dict((x.label, x.value) for x in at.metric)
        self.assertEqual(m["🎯 거래 종목"], "KRW-ZRO")
        self.assertEqual(m["💰 Take Profit"], "+4.00%")
        self.assertEqual(m["🔻 Stop Loss"], "-2.00%")
        self.assertEqual(m["💰 주문 비율"], "20%")
        self.assertEqual(m["전략 타입"], "눌림목 분할매수")   # 지적 5: v2 표시 이름

    def test_pullback_cash_equals_engine_capital(self):
        """주문 총액 = 엔진 기동과 같은 운용자산(users.virtual_krw — engine_manager._pullback_boot_params)."""
        self.pullback()
        self.set_capital(2_345_678)
        at = self.dash()
        m = dict((x.label, x.value) for x in at.metric)
        self.assertEqual(m["주문 총액 (KRW)"], "2,345,678")

    def test_pullback_tables_replaced_c4(self):
        self.pullback()
        at = self.dash()
        labels = [e.label for e in at.expander]
        for lab in ("📈 이동평균 (EMA / MACD 기간)", "🔧 MACD 옵션 (MACD 전략 전용)",
                    "📈 매수 설정 (Strategy: 눌림목 분할매수)", "📉 매도 설정 (Strategy: 눌림목 분할매수)",
                    "⏰ 거래 시간 제한", "🎯 전략 핵심 설정", "⚙️ 파라미터 설정"):
            self.assertIn(lab, labels)
        self.assertEqual([c.value for c in at.caption].count("새 전략 조건은 신버전에서 확인합니다"), 4)
        metric_labels = [x.label for x in at.metric]
        for gone in ("Fast Period", "MACD Threshold", "MA Type"):
            self.assertNotIn(gone, metric_labels)
        self.assertFalse(any("strategy-table" in t for t in self.texts(at, ("markdown",))
                             if "<table" in t))

    def test_pullback_expander_collapse_state_same_as_macd(self):
        """사라짐·접힘 0: 새 전략 화면의 접힘 칸 목록 = MACD 사용자 화면(같은 분기)의 목록(전략 이름만 다름)."""
        self.pullback()
        pb = [e.label.replace("눌림목 분할매수", "X") for e in self.dash().expander]
        (self.tmpdir / f"{USER}_active_strategy.txt").write_text("MACD")
        (self.tmpdir / f"{USER}_latest_params_MACD.json").write_text(json.dumps(dict(EMA_PARAMS, strategy_type="MACD")))
        macd = [e.label.replace("MACD)", "X)") for e in self.dash().expander]
        self.assertEqual(pb, macd)

    def test_old_ui_locks_dashboard_engine_start(self):
        self.pullback()
        b = self.btn(self.dash(), "btn_start_engine")
        self.assertTrue(b.disabled)
        self.assertEqual(b.label, "🚀 엔진 시작 (잠김)")

    def test_old_ui_locks_dashboard_param_setting(self):
        self.pullback()
        b = self.btn(self.dash(), "btn_config")
        self.assertTrue(b.disabled)
        self.assertEqual(b.label, "⚙️ 파라미터 설정 (잠김)")

    def test_old_ui_locks_system_reset(self):
        self.pullback()
        self.assertTrue(self.btn(self.dash(), "btn_reset_system").disabled)
        at = self.page("pages/confirm_init_db.py", user_id=USER, mode="TEST", virtual_krw="1000000")
        go = [b for b in at.button if b.label == "💥 초기화 진행"]
        self.assertEqual(len(go), 1)
        self.assertTrue(go[0].disabled)

    def test_old_settings_nav_open(self):
        self.pullback()
        at = self.dash()
        for key in ("btn_settings", "btn_settings_history", "btn_audit_log"):
            self.assertFalse(self.btn(at, key).disabled, key)

    def test_old_engine_stop_open(self):
        self.pullback()
        from engine.engine_manager import engine_manager
        stop = MagicMock()
        with patch.object(engine_manager, "stop_engine", stop):
            at = self.dash()
            self.assertFalse(self.btn(at, "btn_stop_engine").disabled)
            at.button(key="btn_stop_engine").click().run()
        stop.assert_called_once_with(USER)

    def test_old_ui_dashboard_auto_resume_open_when_locked(self):
        """C2 (나), D7 예외(사용자 결정 1029-10): 잠김이어도 자동 재개는 TEST 엔진을 다시 띄운다."""
        self.pullback(entry=1, qty=5.0)
        from services.db import set_engine_status
        set_engine_status(USER, True, last_mode="TEST")
        from engine.engine_manager import engine_manager
        start = MagicMock(return_value=True)
        with patch.object(engine_manager, "start_engine", start):
            self.dash()
        start.assert_called_once_with(USER, test_mode=True)

    def _force(self, key, fn_name):
        import core.trader
        import services.trading_control as tc
        trader_cls = MagicMock(name="UpbitTrader")
        fn = MagicMock(return_value="[TEST] ok")
        with patch.object(core.trader, "UpbitTrader", trader_cls), patch.object(tc, fn_name, fn):
            at = self.dash()
            self.assertFalse(self.btn(at, key).disabled)
            at.button(key=key).click().run()
        return trader_cls, fn

    def test_old_force_buy_pullback_ticker(self):
        self.pullback()
        trader_cls, fn = self._force("btn_force_buy", "force_buy_in")
        self.assertEqual(fn.call_count, 1)
        args, kw = fn.call_args
        self.assertEqual(args[2], "KRW-ZRO")
        self.assertIsNone(kw["strategy_type"])           # 옛 공용 조건 파일을 읽지 않음 → 시장가
        self.assertEqual(kw["interval_sec"], 180)
        tkw = trader_cls.call_args.kwargs
        self.assertAlmostEqual(tkw["risk_pct"], 0.2)     # 1 / maxSplits 5
        self.assertEqual(tkw["strategy_type"], "PULLBACK")
        self.assertTrue(tkw["test_mode"])
        from services.trading_control import _load_force_buy_conditions
        self.assertEqual(_load_force_buy_conditions(USER, None), {})   # buy_limit 경로 0 (fixed_price 거짓)

    def test_force_buy_fixed_price_hint_uses_none_on_pullback(self):
        self.pullback()
        import services.trading_control as tc
        probe = MagicMock(return_value=(False, 3))
        with patch.object(tc, "is_force_buy_fixed_price_active", probe):
            self.dash()
        self.assertEqual(probe.call_args.args, (USER, None))

    def test_old_force_buy_caption_pullback(self):
        self.pullback()
        self.assertIn("구버전 강제 매수는 새 전략 회차 밖 매수입니다(추가 분할매수가 멈춥니다).",
                      [c.value for c in self.dash().caption])

    def test_old_force_sell_pullback_ticker(self):
        self.pullback(entry=1, qty=100.0)
        from services.db import update_coin_position
        update_coin_position(USER, "KRW-ZRO", 100.0)
        trader_cls, fn = self._force("btn_force_sell", "force_liquidate")
        self.assertEqual(fn.call_count, 1)
        self.assertEqual(fn.call_args.args[2], "KRW-ZRO")
        self.assertEqual(trader_cls.call_args.kwargs["strategy_type"], "PULLBACK")

    def test_audit_viewer_button_top_level_pullback(self):
        self.pullback()
        at = self.dash()
        self.assertFalse(self.btn(at, "btn_audit_log").disabled)
        src = (ROOT / "pages" / "dashboard.py").read_text(encoding="utf-8").split("\n")
        i = next(n for n, line in enumerate(src) if 'key="btn_audit_log"' in line)
        self.assertIn("_audit_hdr_col2", "\n".join(src[max(0, i - 10):i]))

    def test_whitelist_buttons_top_level(self):
        """1-B: 강제 매수·매도·감사로그 뷰어·설정 이동·파라미터 설정·엔진 시작 단추가 st.expander 안에 없다."""
        tree = ast.parse((ROOT / "pages" / "dashboard.py").read_text(encoding="utf-8"))
        keys = {"btn_force_buy", "btn_force_sell", "btn_audit_log", "btn_settings", "btn_config", "btn_start_engine",
                "btn_stop_engine"}
        found = set()

        def walk(node, in_exp):
            for ch in ast.iter_child_nodes(node):
                exp = in_exp
                if isinstance(ch, ast.With):
                    for it in ch.items:
                        c = it.context_expr
                        if isinstance(c, ast.Call) and getattr(c.func, "attr", "") == "expander":
                            exp = True
                if isinstance(ch, ast.Call) and getattr(ch.func, "attr", "") == "button":
                    for kw in ch.keywords:
                        if kw.arg == "key" and isinstance(kw.value, ast.Constant) and kw.value.value in keys:
                            self.assertFalse(exp, kw.value.value)
                            found.add(kw.value.value)
                walk(ch, exp)
        walk(tree, False)
        self.assertEqual(found, keys)

    def test_applied_missing_shows_error_not_other_ticker(self):
        """적용본도 사본도 없으면 다른 전략 종목으로 그리지 않고 멈춘다(강제 매매가 엉뚱한 종목으로 나가지 않게)."""
        self.pullback()
        (self.tmpdir / f"{USER}_applied_params_PULLBACK.json").unlink()
        (self.tmpdir / f"{USER}_latest_params_MACD.json").write_text(json.dumps(dict(EMA_PARAMS, strategy_type="MACD")))
        at = self.dash()
        self.assertTrue(any("새 전략 적용 설정을 읽지 못했습니다" in e.value for e in at.error))
        self.assertIsNone(self.btn(at, "btn_force_buy"))


# ==================================================================== 예약 중(활성 EMA)
class TestReservedEma(_Base):
    def test_old_ui_locked_while_reserved(self):
        self.ema()
        self.reserve("TEST")
        at = self.dash()
        self.assertIn("전환 예약 중 — 설정은 신버전에서 관리합니다", [i.value for i in at.info])
        self.assertTrue(self.btn(at, "btn_start_engine").disabled)
        self.assertTrue(self.btn(at, "btn_config").disabled)
        self.assertTrue(self.btn(at, "btn_reset_system").disabled)
        self.assertFalse(self.btn(at, "btn_force_buy").disabled)
        self.assertIn("전환 예약은 그대로이며 이번 매수분을 지금 전략이 판 뒤 바뀝니다.", [c.value for c in at.caption])
        m = dict((x.label, x.value) for x in at.metric)
        self.assertEqual(m["🎯 거래 종목"], "KRW-JTO")   # 1029-03-3: 활성 전략 params 종목

    def test_reserved_force_buy_uses_active_ema(self):
        self.ema()
        self.reserve("TEST")
        import core.trader
        import services.trading_control as tc
        fn = MagicMock(return_value="[TEST] ok")
        with patch.object(core.trader, "UpbitTrader", MagicMock()), patch.object(tc, "force_buy_in", fn):
            at = self.dash()
            at.button(key="btn_force_buy").click().run()
        self.assertEqual(fn.call_args.args[2], "KRW-JTO")
        self.assertEqual(fn.call_args.kwargs["strategy_type"], "EMA")

    def _live_b(self, at):
        """사용자 결정 1029-11 B (나): 실계좌 화면 — 수동 시작·파라미터 설정 이동은 열림, 초기화는 잠김."""
        b = self.btn(at, "btn_start_engine")
        self.assertFalse(b.disabled)
        self.assertEqual(b.label, "🚀 엔진 실행하기")
        c = self.btn(at, "btn_config")
        self.assertFalse(c.disabled)
        self.assertEqual(c.label, "⚙️ 파라미터 설정")
        self.assertTrue(self.btn(at, "btn_reset_system").disabled)

    def test_live_reservation_locks_too(self):
        """C3 ①: 예약은 모든 모드를 본다 — TEST 예약이면 LIVE 화면도 잠김(배지·초기화).
        단 1029-11 B (나, 1029-10 C2 의 실계좌 화면 예외): 수동 시작·파라미터 설정 이동은 열림."""
        self.ema()
        self.reserve("TEST")
        at = self.dash(mode="LIVE")
        self.assertIn("전환 예약 중 — 설정은 신버전에서 관리합니다", [i.value for i in at.info])
        self._live_b(at)

    def test_live_reservation_unknown_opens_start(self):
        self.ema()
        import ui.pullback_lock as pl
        with patch.object(pl, "reservation_any_mode", side_effect=pl.ReservationReadError("OperationalError")):
            at = self.dash(mode="LIVE")
            self.assertIn("전환 예약 상태를 확인하지 못해 설정 저장을 잠시 막습니다", [i.value for i in at.info])
            self._live_b(at)

    def test_live_reservation_start_click_starts_live(self):
        self.ema()
        self.reserve("TEST")
        from engine.engine_manager import engine_manager
        start = MagicMock(return_value=False)
        with patch.object(engine_manager, "start_engine", start), patch.object(engine_manager, "is_running",
                                                                                return_value=False):
            at = self.dash(mode="LIVE")
            at.button(key="btn_start_engine").click().run()
        start.assert_called_once_with(USER, test_mode=False)

    def test_live_reservation_set_config_still_locked(self):
        """B (나): 설정 화면으로 들어가도 저장·전략 선택은 잠김(Fable 권고 3)."""
        self.ema()
        self.reserve("TEST")
        # 검증 완료로 들어가 set_config 자동 계좌검증(바깥 Upbit 요청)을 타지 않게 한다(Fable impl-1 권고 1)
        import services.upbit_api as ua
        with patch.object(ua, "validate_upbit_keys", MagicMock(side_effect=AssertionError("외부 요청 금지"))):
            at = self.page("pages/set_config.py", user_id=USER, mode="LIVE", virtual_krw="1000000",
                           strategy_type="EMA", verified="1", capital_set="1")
        sel = [s for s in at.selectbox if s.label == "전략 타입 (Strategy Type)"]
        self.assertEqual(len(sel), 1)
        self.assertTrue(sel[0].disabled)
        self.assertTrue(any(b.label == "🧪 파라미터 저장하기 (잠김)" and b.disabled for b in at.button))

    def test_test_reservation_start_locked(self):
        """모의 화면은 지금처럼 수동 시작도 잠김."""
        self.ema()
        self.reserve("TEST")
        at = self.dash()
        self.assertTrue(self.btn(at, "btn_start_engine").disabled)
        self.assertTrue(self.btn(at, "btn_config").disabled)

    def test_reservation_unknown_fail_closed(self):
        self.ema()
        import ui.pullback_lock as pl
        with patch.object(pl, "reservation_any_mode", side_effect=pl.ReservationReadError("OperationalError")):
            at = self.dash()
        self.assertIn("전환 예약 상태를 확인하지 못해 설정 저장을 잠시 막습니다", [i.value for i in at.info])
        self.assertTrue(self.btn(at, "btn_start_engine").disabled)
        self.assertFalse(self.btn(at, "btn_force_buy").disabled)
        self.assertFalse(self.btn(at, "btn_force_sell").disabled)


# ==================================================================== C1-a: TEST 현금 덮어쓰기
class TestTestCashKept(_Base):
    def test_c1a_skip_account_overwrite_when_pullback_holding(self):
        self.pullback(entry=1, qty=5.0)
        from services.db import update_account, get_account
        self.cash(800_000)
        self.dash()
        self.assertEqual(get_account(USER), 800_000)

    def test_c1a_skip_account_overwrite_when_pending_fill(self):
        self.pullback(entry=0, qty=0.0, pending=1)
        from services.db import update_account, get_account
        self.cash(800_000)
        self.dash()
        self.assertEqual(get_account(USER), 800_000)

    def test_c1a_skip_when_reserved_ema_test(self):
        self.ema()
        self.reserve("TEST")
        from services.db import update_account, get_account
        self.cash(900_000)
        self.dash()
        self.assertEqual(get_account(USER), 900_000)

    def test_c1a_overwrite_when_pullback_flat(self):
        self.pullback(entry=0, qty=0.0)
        from services.db import update_account, get_account
        self.cash(800_000)
        self.dash()
        self.assertEqual(get_account(USER), 1_000_000)

    def test_c1a_account_created_when_missing(self):
        self.pullback(entry=1, qty=5.0)
        self.sql("DELETE FROM accounts WHERE user_id=?", (USER,))
        self.dash()
        from services.db import get_account
        self.assertEqual(get_account(USER), 1_000_000)


# ==================================================================== 다른 화면 잠금
class TestOtherPagesLocked(_Base):
    def conf(self, **kw):
        q = dict(user_id=USER, mode="TEST", virtual_krw="1000000", strategy_type="EMA")
        q.update(kw)
        return self.page("pages/set_config.py", **q)

    def test_old_ui_locks_set_config_strategy_select(self):
        self.pullback()
        (self.tmpdir / f"{USER}_latest_params_EMA.json").write_text(json.dumps(EMA_PARAMS))
        at = self.conf()
        sel = [s for s in at.selectbox if s.label == "전략 타입 (Strategy Type)"]
        self.assertEqual(len(sel), 1)
        self.assertTrue(sel[0].disabled)
        self.assertIn("새 전략(눌림목 분할매수) 운용 중 — 설정은 신버전에서 관리합니다", [i.value for i in at.info])

    def test_old_ui_locks_set_config_save(self):
        self.pullback(entry=1, qty=5.0)
        p = self.tmpdir / f"{USER}_latest_params_EMA.json"
        p.write_text(json.dumps(EMA_PARAMS))
        before_params = p.read_bytes()
        from services.db import update_account, get_account, update_coin_position
        self.cash(800_000)
        update_coin_position(USER, "KRW-ZRO", 5.0)
        at = self.conf()
        self.assertTrue(any("(잠김)" in b.label and b.disabled for b in at.button))
        # 잠긴 단추를 우회해도(세션에서 제출) 함수 진입에서 막힌다: make_sidebar 가 값을 돌려줘도 저장 없음
        import ui.sidebar
        fake = MagicMock()
        fake.cash = 123
        with patch.object(ui.sidebar, "make_sidebar", MagicMock(return_value=fake)):
            self.conf()
        self.assertEqual(p.read_bytes(), before_params)
        self.assertEqual((self.tmpdir / f"{USER}_active_strategy.txt").read_text(), "PULLBACK")
        self.assertEqual(get_account(USER), 800_000)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM account_positions WHERE user_id=?", (USER,))[0][0], 1)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM settings_history")[0][0], 0)

    def test_set_config_go_dashboard_open(self):
        """C1-b: 「Go Dashboard」는 화면 이동이라 잠김 중에도 열림 — 그 전략 파일이 없어도 보인다."""
        self.pullback()
        at = self.conf(strategy_type="MACD")
        go = [b for b in at.button if b.label.endswith("Go Dashboard")]
        self.assertEqual(len(go), 1)
        self.assertFalse(go[0].disabled)

    def test_old_ui_locks_conditions_save(self):
        self.pullback()
        (self.tmpdir / f"{USER}_latest_params_MACD.json").write_text(json.dumps(dict(EMA_PARAMS, strategy_type="MACD")))
        at = self.page("pages/set_buy_sell_conditions.py", user_id=USER, mode="TEST", virtual_krw="1000000",
                       strategy="MACD")
        save = self.btn(at, "btn_save_settings")
        self.assertTrue(save.disabled)
        self.assertEqual(save.label, "💾 설정 저장 (잠김)")
        ratio = [b for b in at.button if (b.key or "").startswith("quick_ratio_")]
        self.assertEqual(len(ratio), 5)
        self.assertTrue(all(b.disabled for b in ratio))
        self.assertFalse(self.btn(at, "btn_cancel_settings").disabled)
        self.assertIn("새 전략(눌림목 분할매수) 운용 중 — 설정은 신버전에서 관리합니다", [i.value for i in at.info])

    def test_conditions_save_function_guard(self):
        """함수 진입 잠금: save_conditions 를 불러도 조건 파일을 쓰지 않는다(소스 단언)."""
        tree = ast.parse((ROOT / "pages" / "set_buy_sell_conditions.py").read_text(encoding="utf-8"))
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "save_conditions")
        first = fn.body[0]
        self.assertIsInstance(first, ast.If)
        self.assertEqual(ast.unparse(first.test), "_pb_locked")
        self.assertIsInstance(first.body[-1], ast.Return)

    def test_old_ui_locks_history_restore(self):
        self.ema()
        from services.settings_history import record_snapshot
        record_snapshot(USER, "set_config", "EMA")
        self.reserve("TEST")
        at = self.page("pages/settings_history.py", user_id=USER, mode="TEST", strategy_type="EMA")
        b = self.btn(at, "sh_do_restore")
        self.assertIsNotNone(b)
        self.assertTrue(b.disabled)

    def test_history_restore_open_for_ema(self):
        self.ema()
        from services.settings_history import record_snapshot
        record_snapshot(USER, "set_config", "EMA")
        at = self.page("pages/settings_history.py", user_id=USER, mode="TEST", strategy_type="EMA")
        self.assertFalse(self.btn(at, "sh_do_restore").disabled)


# ==================================================================== lock_state 규칙
class TestLockState(_Base):
    def ls(self):
        from ui.pullback_lock import lock_state
        return lock_state(USER)

    def test_ema_no_reservation_unlocked(self):
        self.ema()
        s = self.ls()
        self.assertFalse(s["locked"])
        self.assertIsNone(s["why"])

    def test_live_reservation_seen(self):
        self.ema()
        self.reserve("LIVE", kind="REVERT")
        s = self.ls()
        self.assertTrue(s["locked"])
        self.assertEqual(s["why"], "reserved")
        self.assertEqual(s["reservation"]["mode"], "LIVE")

    def test_params_row_is_not_reservation(self):
        self.ema()
        self.sql("INSERT INTO strategy_switch (user_id, mode, kind, from_strategy, to_strategy, state, requested_at) "
                 "VALUES (?, 'TEST', 'PARAMS', 'PULLBACK', 'PULLBACK', 'DONE', 'x')", (USER,))
        self.assertFalse(self.ls()["locked"])

    def test_table_missing_is_no_reservation_no_alert(self):
        self.ema()
        self.sql("DROP TABLE strategy_switch")
        s = self.ls()
        self.assertFalse(s["locked"])
        self.assertFalse(s["reservation_error"])
        self.notify.assert_not_called()

    def test_read_error_fail_closed(self):
        self.ema()
        with patch("ui.pullback_lock._connect_ro", side_effect=sqlite3.OperationalError("locked")):
            s = self.ls()
        self.assertTrue(s["locked"])
        self.assertEqual(s["why"], "unknown")
        self.assertTrue(s["holding"])   # 보유 판정도 읽기 실패 = 보유(fail closed)

    def test_holding_reads_test_row_only(self):
        self.ema()
        self.state_row("LIVE", entry=2, qty=3.0)
        self.assertFalse(self.ls()["holding"])
        self.state_row("TEST", entry=1, qty=1.0)
        self.assertTrue(self.ls()["holding"])

    def test_db_missing_not_created(self):
        os.unlink(self.db_path)
        s = self.ls()
        self.assertFalse(s["locked"])
        self.assertFalse(os.path.exists(self.db_path))

    def test_read_only_connection(self):
        self.ema()
        from ui.pullback_lock import _connect_ro
        conn = _connect_ro(USER)
        try:
            with self.assertRaises(sqlite3.OperationalError):
                conn.execute("DELETE FROM strategy_switch")
        finally:
            conn.close()

    def test_label_same_as_engine(self):
        from ui.pullback_lock import PULLBACK_LABEL
        from engine.strategy_switch import PULLBACK_LABEL as ENGINE_LABEL
        self.assertEqual(PULLBACK_LABEL, ENGINE_LABEL)


# ==================================================================== D10 (로그인 검증 2곳)
class TestD10(_Base):
    def verify(self):
        import config
        import services.upbit_api as ua
        accounts = [{"currency": "KRW", "balance": "5555555"}]
        with patch.object(config, "ACCESS", "a"), patch.object(config, "SECRET", "b"), \
                patch.object(ua, "validate_upbit_keys", MagicMock(return_value=(True, accounts))), \
                patch("services.db.update_account_from_balances"), patch("services.db.update_position_from_balances"):
            from services.auto_verify import run_live_auto_verify
            return run_live_auto_verify(USER, "새이름")

    def user_row(self):
        return self.sql("SELECT display_name, virtual_krw FROM users WHERE username=?", (USER,))[0]

    def test_auto_verify_keeps_capital_while_pullback_holding(self):
        self.pullback(entry=1, qty=5.0)
        r = self.verify()
        self.assertTrue(r["capital_kept"])
        self.assertEqual(r["capital_krw"], 1_000_000)
        self.assertEqual(self.user_row(), ("새이름", 1_000_000))

    def test_auto_verify_keeps_capital_while_reserved(self):
        self.ema()
        self.reserve("TEST")
        r = self.verify()
        self.assertTrue(r["capital_kept"])
        self.assertEqual(self.user_row(), ("새이름", 1_000_000))

    def test_auto_verify_updates_capital_when_flat(self):
        self.pullback(entry=0, qty=0.0)
        r = self.verify()
        self.assertFalse(r["capital_kept"])
        self.assertEqual(self.user_row(), ("새이름", 5555555))

    def test_auto_verify_ema_unchanged(self):
        self.ema()
        r = self.verify()
        self.assertFalse(r["capital_kept"])
        self.assertEqual(r["capital_krw"], 5555555)
        self.assertEqual(self.user_row(), ("새이름", 5555555))
        from services.auto_verify import apply_verify_to_session
        st = MagicMock()
        st.session_state = MagicMock()
        apply_verify_to_session(st, r)
        self.assertEqual(st.session_state.virtual_krw, 5555555.0)

    def test_apply_session_keeps_capital(self):
        from services.auto_verify import apply_verify_to_session
        st = MagicMock()
        st.session_state = MagicMock()
        apply_verify_to_session(st, {"ok": True, "krw_balance": 5555555, "capital_kept": True,
                                     "capital_krw": 1_000_000})
        self.assertEqual(st.session_state.virtual_krw, 1_000_000.0)

    def test_manual_verify_keeps_capital_while_pullback_holding(self):
        """app.py 수동 검증(394) 경로: keep_capital_on_verify 를 save_user 보다 먼저 보고, 지키면 save_user 를 부르지 않는다."""
        self.pullback(entry=1, qty=5.0)
        from services.auto_verify import keep_capital_on_verify
        self.assertEqual(keep_capital_on_verify(USER, "새이름"), (True, 1_000_000, "trading"))
        self.assertEqual(self.user_row(), ("새이름", 1_000_000))
        src = (ROOT / "app.py").read_text(encoding="utf-8")
        i_keep = src.index("_cap_kept, _cap_krw, _cap_reason = keep_capital_on_verify(username, name)")
        i_save = src.index("save_user(username, name, krw_balance)")
        self.assertLess(i_keep, i_save)
        block = src[i_keep:i_save]
        self.assertIn("if _cap_kept:", block)
        self.assertIn("else:", block)
        self.assertIn("capital_kept_text(_cap_krw, _cap_reason)", block)

    def test_keep_capital_without_user_row_falls_back(self):
        self.pullback(entry=1, qty=5.0)
        self.sql("DELETE FROM users")
        from services.auto_verify import keep_capital_on_verify
        self.assertEqual(keep_capital_on_verify(USER, "새이름"), (False, None, None))

    def test_login_routes_pullback_to_dashboard(self):
        src = (ROOT / "app.py").read_text(encoding="utf-8")
        i = src.index('next_page = "dashboard"')
        self.assertIn("load_active_strategy(username, include_engine_only=True)", src[i:i + 400])
        j = src.index('next_page = "set_config"')
        self.assertIn("load_active_strategy(username) or DEFAULT_STRATEGY_TYPE", src[j:j + 300])

    def test_investor_texts_no_internal_codes(self):
        import ui.pullback_lock as pl
        for name in ("BADGE_PULLBACK", "BADGE_RESERVED", "BADGE_UNKNOWN", "NEW_STRATEGY_TABLE_TEXT",
                     "FORCE_BUY_PULLBACK_TEXT", "FORCE_BUY_RESERVED_TEXT"):
            t = getattr(pl, name)
            for bad in ("PULLBACK", "strategy_switch", "pullback_state", "RESERVED", "_"):
                self.assertNotIn(bad, t, name)


# ==================================================================== C2: 자동 재개 뒤 매수 차단 래퍼
class TestAutoResumeGate(unittest.TestCase):
    def test_all_starts_attach_buy_gate(self):
        """live_loop 의 엔진 생성 뒤 _control_attach → core.engine_control.attach → install_buy_gate (모든 시작 경로)."""
        src = (ROOT / "engine" / "live_loop.py").read_text(encoding="utf-8")
        self.assertEqual(src.count("_control_attach(engine, user_id, stop_event)"), 1)
        ec_src = (ROOT / "core" / "engine_control.py").read_text(encoding="utf-8")
        tree = ast.parse(ec_src)
        attach = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "attach")
        self.assertIn("install_buy_gate(engine, user_id)", ast.unparse(attach))

    def test_attach_installs_gate_on_test_engine(self):
        import core.engine_control as ec

        class Eng:
            strategy_type = "EMA"

            def execute(self, a, b, i):
                return "orig"

            def _execute_buy(self, b, i):
                return "orig"

        e = Eng()
        e.trader = MagicMock(test_mode=True)
        ev = threading.Event()
        try:
            ec.attach(e, "t15gate", ev)
            self.assertIn("execute", e.__dict__)
            self.assertIn("_execute_buy", e.__dict__)
        finally:
            ec.detach("t15gate", ev)


# ==================================================================== 사용자 결정 1029-11 A (나): 실계좌 + 새 전략 → 멈춤
class TestLivePullbackStop(_Base):
    STOP = ("새 전략은 모의 투자에서만 씁니다. 모의 투자로 들어오시거나 신버전에서 전략을 되돌려 주세요. "
            "모의 엔진이 실행 중이면 모의 투자로 들어오세요.")

    def test_live_pullback_stops_without_order_buttons(self):
        import logging
        import core.trader
        import services.trading_control as tc
        from engine.engine_manager import engine_manager
        from services.db import set_engine_status
        self.pullback(entry=1, qty=5.0)
        set_engine_status(USER, True, last_mode="LIVE")      # 자동 재개가 걸릴 상태
        records = []

        class H(logging.Handler):
            def emit(self, r):
                records.append(r.getMessage())

        h = H(level=logging.DEBUG)
        root = logging.getLogger()
        root.addHandler(h)
        trader_cls, buy, sell = MagicMock(), MagicMock(), MagicMock()
        start = MagicMock(return_value=True)
        try:
            with patch.object(core.trader, "UpbitTrader", trader_cls), patch.object(tc, "force_buy_in", buy), \
                    patch.object(tc, "force_liquidate", sell), \
                    patch.object(engine_manager, "start_engine", start):
                at = self.dash(mode="LIVE", verified="1", capital_set="1")
        finally:
            root.removeHandler(h)
        for key in ("btn_start_engine", "btn_force_buy", "btn_force_sell", "btn_config", "btn_reset_system"):
            self.assertIsNone(self.btn(at, key), key)
        self.assertEqual([w.value for w in at.warning], [self.STOP])
        start.assert_not_called()
        self.assertFalse(any("LIVE 자동 재개 시도" in m for m in records))
        trader_cls.assert_not_called()
        buy.assert_not_called()
        sell.assert_not_called()
        self.assertEqual(len(at.metric), 0)

    def test_stop_text_constant(self):
        from ui.pullback_lock import LIVE_PULLBACK_STOP_TEXT
        self.assertEqual(LIVE_PULLBACK_STOP_TEXT, self.STOP)
        for bad in ("PULLBACK", "LIVE", "TEST", "_"):
            self.assertNotIn(bad, LIVE_PULLBACK_STOP_TEXT)

    def test_test_pullback_still_shown(self):
        self.pullback(entry=1, qty=5.0)
        at = self.dash()
        self.assertNotIn(self.STOP, [w.value for w in at.warning])
        self.assertIsNotNone(self.btn(at, "btn_force_buy"))
        self.assertIsNotNone(self.btn(at, "btn_force_sell"))
        self.assertTrue(self.btn(at, "btn_start_engine").disabled)
        m = dict((x.label, x.value) for x in at.metric)
        self.assertEqual(m["전략 타입"], "눌림목 분할매수")

    def test_live_ema_not_stopped(self):
        self.ema()
        at = self.dash(mode="LIVE")
        self.assertNotIn(self.STOP, [w.value for w in at.warning])
        self.assertIsNotNone(self.btn(at, "btn_force_buy"))


# ==================================================================== verifier 지적 5: 화면에 영문 전략 코드 0
class TestPullbackDisplayName(_Base):
    """새 전략 표시 경로의 화면 글자에 내부 코드 PULLBACK 이 보이지 않는다(v2 표시 이름 「눌림목 분할매수」)."""

    def visible(self, at):
        out = [b.label for b in at.button] + [e.label for e in at.expander]
        out += [f"{m.label} {m.value}" for m in at.metric]
        out += [s.label for s in at.selectbox]
        out += self.texts(at, ("info", "warning", "error", "success", "caption", "markdown",
                               "title", "header", "subheader"))
        return out

    def test_no_internal_code_on_pullback_screen(self):
        self.pullback(entry=2, qty=3.0)
        at = self.dash()
        shown = self.visible(at)
        self.assertTrue(shown)
        self.assertEqual([t for t in shown if "PULLBACK" in t], [])
        self.assertIn("눌림목 분할매수", " ".join(shown))

    def test_internal_strategy_value_kept(self):
        """화면 글자만 바뀌고 내부 전략 값(세션 strategy_type — 페이지 이동·엔진 시작이 읽음)은 PULLBACK 그대로."""
        self.pullback()
        at = self.dash()
        self.assertEqual(at.session_state["strategy_type"], "PULLBACK")

    def test_label_same_as_v2_static(self):
        """v2/static/app.js·ops.js 의 표시 이름 표와 같은 글자(신버전 화면과 같은 이름)."""
        import re
        from ui.pullback_lock import PULLBACK_LABEL
        for rel in ("v2/static/app.js", "v2/static/ops.js"):
            src = (ROOT / rel).read_text(encoding="utf-8")
            m = re.search(r'PULLBACK:\s*"([^"]+)"', src)
            self.assertIsNotNone(m, rel)
            self.assertEqual(m.group(1), PULLBACK_LABEL, rel)


# ==================================================================== verifier 지적 4: 판정 실패 문구·금액 없음·재실행 없음
class TestD10Unknown(_Base):
    def test_reason_unknown_when_reservation_read_fails(self):
        self.ema()
        from ui.pullback_lock import ReservationReadError
        from services.auto_verify import keep_capital_on_verify, KEEP_UNKNOWN
        with patch("ui.pullback_lock.reservation_any_mode", side_effect=ReservationReadError("x")):
            r = keep_capital_on_verify(USER, "새이름")
        self.assertEqual(r, (True, 1_000_000, KEEP_UNKNOWN))
        self.assertEqual(self.sql("SELECT display_name, virtual_krw FROM users WHERE username=?", (USER,))[0],
                         ("새이름", 1_000_000))

    def test_reason_unknown_when_holding_read_fails(self):
        self.ema()
        from services.auto_verify import keep_capital_on_verify, KEEP_UNKNOWN
        with patch("ui.pullback_lock.pullback_test_row", side_effect=sqlite3.OperationalError("locked")):
            r = keep_capital_on_verify(USER, "새이름")
        self.assertEqual(r[0], True)
        self.assertEqual(r[2], KEEP_UNKNOWN)

    def test_reason_unknown_when_lock_state_raises(self):
        self.ema()
        from services.auto_verify import keep_capital_on_verify, KEEP_UNKNOWN
        with patch("ui.pullback_lock.lock_state", side_effect=RuntimeError("x")):
            r = keep_capital_on_verify(USER, "새이름")
        self.assertEqual(r, (True, 1_000_000, KEEP_UNKNOWN))
        self.assertEqual(self.sql("SELECT virtual_krw FROM users WHERE username=?", (USER,))[0][0], 1_000_000)

    def test_capital_rereads_db(self):
        """세션 값이 아니라 DB(users.virtual_krw)를 다시 읽은 금액."""
        self.pullback(entry=1, qty=5.0)
        self.set_capital(3_210_000)
        from services.auto_verify import keep_capital_on_verify
        self.assertEqual(keep_capital_on_verify(USER, "새이름")[1], 3_210_000)

    def test_capital_kept_text(self):
        from services.auto_verify import capital_kept_text, KEEP_TRADING, KEEP_UNKNOWN
        self.assertEqual(capital_kept_text(1_000_000, KEEP_TRADING),
                         "운용자산: 1,000,000 KRW (새 전략 거래 중이라 그대로 둡니다)")
        self.assertEqual(capital_kept_text(1_000_000, KEEP_UNKNOWN),
                         "운용자산: 1,000,000 KRW (상태를 확인하지 못해 운용자산을 바꾸지 않았습니다)")
        self.assertEqual(capital_kept_text(None, KEEP_UNKNOWN), "운용자산: 상태를 확인하지 못해 운용자산을 바꾸지 않았습니다")
        self.assertEqual(capital_kept_text(None, KEEP_TRADING), "운용자산: 새 전략 거래 중이라 그대로 둡니다")
        for t in (capital_kept_text(None, KEEP_UNKNOWN), capital_kept_text(5, KEEP_TRADING)):
            for bad in ("PULLBACK", "None", "_", "unknown", "trading"):
                self.assertNotIn(bad, t)

    def test_auto_verify_texts_use_reason(self):
        """app.py 자동 검증 성공 문구는 이유(capital_reason)를 넘긴다."""
        src = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn('capital_kept_text(_verify_result.get("capital_krw"), _verify_result.get("capital_reason"))', src)

    def test_apply_session_amount_unknown_sets_flag(self):
        from services.auto_verify import apply_verify_to_session
        st = MagicMock()
        st.session_state = {}
        ss = MagicMock()
        ss.get = lambda k, d=None: {}.get(k, d)
        st.session_state = ss
        apply_verify_to_session(st, {"ok": True, "krw_balance": 5555555, "capital_kept": True,
                                     "capital_krw": None, "capital_reason": "unknown"})
        self.assertEqual(ss.virtual_krw, 0.0)
        ss.__setitem__.assert_any_call("_capital_kept_in_live", True)

    def _need(self, session, vk):
        """app.py 의 need_auto_verify 식을 그대로 꺼내 가짜 세션으로 계산."""
        tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
        node = next(n for n in ast.walk(tree) if isinstance(n, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == "need_auto_verify" for t in n.targets))
        from types import SimpleNamespace
        return eval(compile(ast.Expression(node.value), "app.py", "eval"),
                    {"st": SimpleNamespace(session_state=dict(session)), "virtual_krw_check": vk})

    def test_need_auto_verify_not_repeated_when_kept_amount_unknown(self):
        self.assertFalse(self._need({"_auto_checked_in_live": True, "_capital_kept_in_live": True}, 0.0))
        self.assertFalse(self._need({"_auto_checked_in_live": True, "_capital_kept_in_live": True}, None))

    def test_need_auto_verify_original_rules_kept(self):
        self.assertTrue(self._need({}, 1000))
        self.assertTrue(self._need({"_auto_checked_in_live": True}, 0))
        self.assertTrue(self._need({"_auto_checked_in_live": True}, -1))
        self.assertFalse(self._need({"_auto_checked_in_live": True}, 1000))


# ==================================================================== verifier 지적 10: PRAGMA 실패 때 연결 닫기
class TestConnectRoClose(_Base):
    def test_connection_closed_when_pragma_fails(self):
        self.ema()
        import ui.pullback_lock as pl
        conn = MagicMock()
        conn.execute.side_effect = sqlite3.OperationalError("busy")
        with patch.object(pl.sqlite3, "connect", return_value=conn):
            with self.assertRaises(sqlite3.OperationalError):
                pl._connect_ro(USER)
        conn.close.assert_called_once()

    def test_pragma_failure_is_reservation_unknown(self):
        self.ema()
        import ui.pullback_lock as pl
        conn = MagicMock()
        conn.execute.side_effect = sqlite3.OperationalError("busy")
        with patch.object(pl.sqlite3, "connect", return_value=conn):
            s = pl.lock_state(USER)
        self.assertEqual(s["why"], "unknown")
        self.assertGreaterEqual(conn.close.call_count, 2)   # 예약·보유 두 번 열고 두 번 닫음


# ==================================================================== verifier 지적 7: 자동 재개 → 매수 차단 래퍼 통합
class TestAutoResumeGateIntegration(_Base):
    """구버전 dashboard 자동 재개 → 진짜 EngineManager.start_engine·_engine_runner → 가짜 run_live_loop 본문 안에서
    진짜 engine.live_loop._control_attach → core.engine_control.attach → install_buy_gate 까지 돈다.
    가짜: run_live_loop 본문(업비트 조회 없음)·trader·DB 상태 기록(Rig, test_r_2026_10_29_engine_exit_alert)."""

    def test_auto_resume_reaches_buy_gate(self):
        from tests.regressions.test_r_2026_10_29_engine_exit_alert import Rig, _wait
        import engine.engine_manager as em_mod
        import engine.live_loop as ll
        from core.strategy_action import Action
        from services.db import set_engine_status
        self.ema()
        self.reserve("TEST")                       # 잠김(reserved) — 수동 시작은 잠기고 자동 재개는 열림(C2 나)
        set_engine_status(USER, True, last_mode="TEST")
        seen = {}

        class FakeEngine:
            strategy_type = "EMA"

            def __init__(self, trader):
                self.trader = trader
                self.orig_calls = 0
                self._audit_buy_blocked = MagicMock()

            def execute(self, action, bar, indicators):
                self.orig_calls += 1
                return "orig"

            def _execute_buy(self, bar, indicators):
                self.orig_calls += 1
                return "orig"

        def fake_loop(params, q, trader, stop_event, test_mode, user_id, **kw):
            eng = FakeEngine(trader)
            ll._control_attach(eng, user_id, stop_event)          # 진짜 live_loop 의 붙이기 함수
            seen["engine"] = eng
            seen["test_mode"] = test_mode
            seen["buy"] = eng.execute(Action.BUY, MagicMock(ts=None, close=100.0), {})
            stop_event.wait(10)

        with Rig(strategy="EMA", real_run_live_loop=True) as rig, \
                patch.object(em_mod, "run_live_loop", side_effect=fake_loop), \
                patch.object(em_mod, "engine_manager", rig.em):
            at = self.dash()
            self.assertTrue(_wait(lambda: "buy" in seen, 10), "가짜 run_live_loop 에 닿지 않음")
            from ui.pullback_lock import lock_state
            self.assertEqual(lock_state(USER)["why"], "reserved")   # 잠김 상태에서 재개됨
            self.assertIsNotNone(self.btn(at, "btn_stop_engine"))  # 재개 뒤 정지 단추(열림)
            eng = seen["engine"]
            self.assertTrue(seen["test_mode"])
            self.assertTrue(eng.__dict__.get("_switch_gate_installed"))
            self.assertIn("execute", eng.__dict__)
            self.assertIsNone(seen["buy"])                 # 예약 중 → 봇 자동 매수 차단
            self.assertEqual(eng.orig_calls, 0)
            eng._audit_buy_blocked.assert_called_once()
            rig.em.stop_engine(USER)


class TestFixedFiles(unittest.TestCase):
    FIXED = ("core/strategy_engine.py", "core/strategy_incremental.py", "engine/params.py", "engine/live_loop.py",
             "engine/boot_resume.py", "services/trading_control.py", "engine/engine_manager.py", "services/db.py",
             "core/strategy_pullback.py")

    def test_fixed_files_unchanged_since_base(self):
        r = subprocess.run(["git", "-C", str(ROOT), "diff", "--quiet", BASE_COMMIT, "--", *self.FIXED])
        self.assertEqual(r.returncode, 0, "고정 파일 9개가 8464b58 와 다르다")


if __name__ == "__main__":
    unittest.main()
