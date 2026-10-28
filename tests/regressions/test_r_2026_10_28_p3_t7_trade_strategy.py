"""
2차 T7: 설정 이력 — 거래 행 전략 칸 (결정 D2, ⚠ 스키마 변경 — 배포 승인 대상).

계획 `docs/specs/v2-dashboard/plan-phase2.md` 「### T7:」:
- `audit_trades.strategy_type`·`orders.strategy_type` 칸 + `schema_marks`(옛 행 표식) 신설.
- 먼저 읽기(D1): 다 된 DB 에서는 쓰기 0·`BEGIN IMMEDIATE` 0.
- 표식 복구(D3), 되돌림 구간(D2, `scripts/v2/mark_revert.py`).
- 구버전 설정 이력(`fetch_trades_for_snapshot`·`compute_pnl_for_snapshot`)에서 PULLBACK·분류 불명 행을 뺀다.
- 기록 경로 전부(trader·reconciler·HTS·HTS_SELL·구버전 강제 매매)가 전략을 적는다.
임시 DB 만 쓴다(서버 DB·로컬 실 DB 를 열지 않는다).

실행:
    TELEGRAM_BOT_TOKEN= TELEGRAM_CHAT_ID= python3 -m unittest tests.regressions.test_r_2026_10_28_p3_t7_trade_strategy -v
"""
from __future__ import annotations

import ast
import importlib.util
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402,F401

U = "p3t7strat"
T = "KRW-JTO"
OLD_TS = "2026-10-01T10:00:00+09:00"   # 옛 행 시각 (스냅샷 시작 뒤)
SNAP_TS = "2026-09-01T00:00:00+09:00"  # 구버전 설정 스냅샷 시각


def _ok_call(uuid):
    return {"ok": True, "status": 201, "body": None, "error_name": None, "error_message": None,
            "exception": None, "data": {"uuid": uuid}}


def _reject_call(name="insufficient_funds_ask", msg="주문 가능한 금액(JTO)이 부족합니다."):
    return {"ok": False, "status": 400, "body": {"error": {"name": name, "message": msg}},
            "error_name": name, "error_message": msg, "exception": None, "data": None}


class _EngineStub:
    """reconciler HTS 콜백 주인(엔진) 대역 — strategy_type 만 본다."""

    def __init__(self, strategy_type):
        self.strategy_type = strategy_type
        self.calls = []

    def _on_hts_detect(self, *, avg_price, qty, reason):
        self.calls.append((avg_price, qty, reason))


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="p3t7_")
        self.addCleanup(shutil.rmtree, self.tmpdir, True)
        self.db_path = os.path.join(self.tmpdir, f"tradebot_{U}.db")
        self.active_path = os.path.join(self.tmpdir, f"{U}_active_strategy.txt")
        patches = [
            mock.patch("services.init_db.get_db_path", return_value=self.db_path),
            mock.patch("services.db.get_db_path", return_value=self.db_path),
            mock.patch("services.notifier.send", mock.MagicMock(return_value=True)),
            mock.patch("engine.params._get_active_strategy_path", return_value=self.active_path),
            mock.patch("engine.reconciler_singleton.get_reconciler", return_value=mock.MagicMock()),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        import services.init_db as idb
        self.idb = idb

    # ---- 공통 도우미 ----
    def q(self, sql, args=()):
        conn = sqlite3.connect(self.db_path)
        try:
            return conn.execute(sql, args).fetchall()
        finally:
            conn.close()

    def exec(self, sql, args=()):
        conn = sqlite3.connect(self.db_path)
        try:
            cur = conn.execute(sql, args)
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()

    def cols(self, table):
        return [r[1] for r in self.q(f"PRAGMA table_info({table})")]

    def marks(self):
        try:
            return dict(self.q("SELECT name, value FROM schema_marks"))
        except sqlite3.OperationalError:
            return None

    def set_active(self, s):
        with open(self.active_path, "w") as f:
            f.write(s)

    def old_db(self, n_rows=5):
        """T7 전 코드가 만든 DB: 지금 스키마에서 strategy_type 칸·schema_marks 만 없는 DB + 행 n 개씩."""
        self.idb.initialize_db(U)
        with mock.patch.object(self.idb, "ensure_trade_strategy_columns", lambda uid: None, create=True):
            self.idb.ensure_all_schemas(U)
            from services.db import ensure_schema
            ensure_schema(U)  # settings_history 등 (DB 호출 경로 보강)
        self.assertNotIn("strategy_type", self.cols("audit_trades"))
        self.assertNotIn("strategy_type", self.cols("orders"))
        self.exec("INSERT INTO settings_history (user_id, saved_at, source_page, strategy_type, params_json, "
                  "conditions_json) VALUES (?, ?, 'set_config', 'EMA', '{}', '{}')", (U, SNAP_TS))
        for i in range(n_rows):
            self.exec("INSERT INTO audit_trades (timestamp, ticker, interval_sec, bar, type, reason, price, entry_price, "
                      "bars_held) VALUES (?, ?, 180, ?, ?, ?, ?, ?, ?)",
                      (OLD_TS, T, i, "BUY" if i % 2 == 0 else "SELL", "EMA_GC" if i % 2 == 0 else "EMA_DC",
                       100.0 + i, None if i % 2 == 0 else 100.0, None if i % 2 == 0 else 3))
            self.exec("INSERT INTO orders (user_id, timestamp, ticker, side, price, volume, status, state, "
                      "executed_volume, avg_price, paid_fee, executed_at) VALUES (?, ?, ?, ?, ?, ?, 'completed', "
                      "'FILLED', ?, ?, ?, ?)",
                      (U, OLD_TS, T, "BUY" if i % 2 == 0 else "SELL", 100.0 + i, 1.0, 1.0, 100.0 + i, 0.05, OLD_TS))

    def migrate(self):
        self.idb.ensure_trade_strategy_columns(U)

    def snapshot_id(self):
        return self.q("SELECT id FROM settings_history ORDER BY id LIMIT 1")[0][0]

    def history(self):
        from services import settings_history as sh
        sid = self.snapshot_id()
        trades = sh.fetch_trades_for_snapshot(U, sid)
        pnl = sh.compute_pnl_for_snapshot(U, sid)
        snaps = sh.fetch_history(U)
        return trades, pnl, snaps

    def history_ids(self):
        return sorted(t["id"] for t in self.history()[0])

    def live_trader(self, strategy_type):
        from core.trader import UpbitTrader
        with mock.patch("core.trader.pyupbit.Upbit", mock.MagicMock()):
            tr = UpbitTrader(U, risk_pct=0.1, test_mode=False, strategy_type=strategy_type)
        tr._krw_balance = lambda: 1_000_000.0
        tr._coin_balance = lambda ticker: 10.0
        return tr

    def make_test_trader(self, strategy_type):
        from core.trader import UpbitTrader
        from services.db import create_or_init_account
        create_or_init_account(U, 1_000_000)
        return UpbitTrader(U, risk_pct=0.1, test_mode=True, strategy_type=strategy_type)

    def reconciler(self):
        from engine.order_reconciler import OrderReconciler
        upbit = mock.MagicMock()
        upbit.get_balances.return_value = []
        return OrderReconciler(upbit)

    def finalize(self, orc, uuid, side="BUY", vol=10.0, px=700.0):
        orc._pending[uuid] = {"user_id": U, "ticker": T, "side": side,
                              "meta": {"reason": "EMA_GC", "bar": 1}, "enqueued_at": time.time()}
        orc._finalize_order(uuid, U, T, side, vol, px, 1.0, "FILLED")

    def hts_detect(self, owner_strategy):
        orc = self.reconciler()
        if owner_strategy is not None:
            orc.register_hts_detect_callback(U, T, _EngineStub(owner_strategy)._on_hts_detect)
        orc._live_user_ids = {U}
        orc._last_balance_sync = 0
        orc.upbit.get_balances.return_value = [
            {"currency": "KRW", "balance": "1000", "locked": "0", "avg_buy_price": "0"},
            {"currency": "JTO", "balance": "100", "locked": "0", "avg_buy_price": "700"},
        ]
        orc._hts_delta_krw = lambda ticker, qd, avg: (70_000.0, "avg")
        with mock.patch("services.db.has_recent_bot_buy_for_ticker", return_value=False), \
             mock.patch("services.db.get_position_total_qty", return_value=0.0):
            orc._periodic_balance_sync()

    def hts_sell(self, strategy_type):
        from core.strategy_engine import StrategyEngine
        stub = SimpleNamespace(user_id=U, ticker=T, interval_sec=180, bar_count=7, strategy_type=strategy_type,
                               position=SimpleNamespace(entry_bar=3))
        StrategyEngine._record_external_sell(stub, 10.0, 700.0)


# ─────────────────────────────────────────────────────────────
# 마이그레이션
# ─────────────────────────────────────────────────────────────
class TestMigration(_Base):
    def test_migration_marks_and_columns(self):
        """기존 행 5개 DB → 표식 5, 칸 추가, 기존 행 값 불변, 2회 실행 무변경, integrity ok."""
        self.old_db(5)
        before_at = self.q("SELECT * FROM audit_trades ORDER BY id")
        before_or = self.q("SELECT * FROM orders ORDER BY id")
        self.migrate()
        self.assertIn("strategy_type", self.cols("audit_trades"))
        self.assertIn("strategy_type", self.cols("orders"))
        m = self.marks()
        self.assertEqual(m["audit_trades.strategy_type.legacy_max_id"], 5)
        self.assertEqual(m["orders.strategy_type.legacy_max_id"], 5)
        at = self.q("SELECT name, at FROM schema_marks")
        self.assertTrue(all(a.endswith("+09:00") for _, a in at), at)  # KST ISO
        after_at = self.q("SELECT * FROM audit_trades ORDER BY id")
        after_or = self.q("SELECT * FROM orders ORDER BY id")
        self.assertEqual([r[:-1] for r in after_at], before_at)  # 기존 칸 값 불변, 새 칸만 끝에
        self.assertEqual([r[:-1] for r in after_or], before_or)
        self.assertTrue(all(r[-1] is None for r in after_at + after_or))
        snap = (self.q("SELECT * FROM schema_marks ORDER BY name"), after_at, after_or,
                self.cols("audit_trades"), self.cols("orders"))
        self.migrate()
        self.idb.ensure_all_schemas(U)
        self.assertEqual((self.q("SELECT * FROM schema_marks ORDER BY name"),
                          self.q("SELECT * FROM audit_trades ORDER BY id"), self.q("SELECT * FROM orders ORDER BY id"),
                          self.cols("audit_trades"), self.cols("orders")), snap)
        self.assertEqual(self.q("PRAGMA integrity_check")[0][0], "ok")
        self.assertEqual(self.q("PRAGMA foreign_key_check"), [])

    def test_new_db_marks_zero(self):
        """새 DB: ensure_all_schemas 2회 → 칸 2개, 표식 0 두 개, 오류 0."""
        self.idb.initialize_db(U)
        self.idb.ensure_all_schemas(U)
        self.idb.ensure_all_schemas(U)
        self.assertEqual(self.marks(), {"audit_trades.strategy_type.legacy_max_id": 0,
                                        "orders.strategy_type.legacy_max_id": 0})
        self.assertIn("strategy_type", self.cols("audit_trades"))
        self.assertIn("strategy_type", self.cols("orders"))

    def test_registered_last_in_ensure_all_schemas(self):
        src = (ROOT / "services/init_db.py").read_text(encoding="utf-8")
        fn = next(n for n in ast.walk(ast.parse(src))
                  if isinstance(n, ast.FunctionDef) and n.name == "ensure_all_schemas")
        self.assertEqual(ast.unparse(fn.body[-1]).strip(), "ensure_trade_strategy_columns(user_id)")

    def test_migration_no_write_when_done(self):
        """다 된 DB 에서 함수 호출 → total_changes 0, BEGIN IMMEDIATE 0, 쓰기 문장 0 (연결 trace)."""
        self.old_db(3)
        self.migrate()
        stmts, changes = [], []
        orig = self.idb._connect

        class _Traced:
            """연결 대역: 문장을 모으고, 닫기 직전 total_changes 를 남긴다."""

            def __init__(self, c):
                self._c = c

            def __getattr__(self, name):
                return getattr(self._c, name)

            def close(self):
                changes.append(self._c.total_changes)
                self._c.close()

        def traced(uid):
            c = orig(uid)
            c.set_trace_callback(stmts.append)
            return _Traced(c)

        with mock.patch.object(self.idb, "_connect", traced):
            self.idb.ensure_trade_strategy_columns(U)
        joined = "\n".join(stmts).upper()
        self.assertNotIn("BEGIN", joined)
        for kw in ("INSERT", "UPDATE", "DELETE", "ALTER", "CREATE", "DROP"):
            self.assertNotIn(kw, joined, kw)
        self.assertEqual(changes, [0])
        self.assertTrue(stmts, "읽기 문장은 있어야 함(PRAGMA table_info 등)")

    def test_migration_failure_does_not_raise(self):
        """잠금 등으로 실패해도 예외를 올리지 않는다(로그인·대시보드·기동 계속). 기존 행 그대로."""
        self.old_db(2)

        def boom(uid):
            raise sqlite3.OperationalError("database is locked")

        with mock.patch.object(self.idb, "_connect", boom), self.assertLogs("services.init_db", "ERROR"):
            self.idb.ensure_trade_strategy_columns(U)
        self.assertNotIn("strategy_type", self.cols("audit_trades"))
        self.assertEqual(self.q("SELECT COUNT(*) FROM audit_trades")[0][0], 2)

    def test_mark_repair_definition(self):
        """칸은 있고 표식이 없음 → 표식 = 전략이 처음 기록된 행 바로 앞, 없으면 MAX(id), 빈 표는 0. WARNING."""
        self.old_db(5)  # audit_trades id 1..5, orders id 1..5 (NULL)
        self.migrate()
        self.exec("UPDATE audit_trades SET strategy_type='EMA' WHERE id IN (3, 4)")
        self.exec("DELETE FROM schema_marks")
        with self.assertLogs("services.init_db", "WARNING") as cm:
            self.migrate()
        self.assertTrue(any("strategy mark repaired" in m for m in cm.output), cm.output)
        m = self.marks()
        self.assertEqual(m["audit_trades.strategy_type.legacy_max_id"], 2)  # MIN(3) - 1
        self.assertEqual(m["orders.strategy_type.legacy_max_id"], 5)        # 전략 행 없음 → MAX(id)
        # 빈 표
        self.exec("DELETE FROM schema_marks")
        self.exec("DELETE FROM orders")
        self.migrate()
        self.assertEqual(self.marks()["orders.strategy_type.legacy_max_id"], 0)


# ─────────────────────────────────────────────────────────────
# 되돌림 구간 (D2)
# ─────────────────────────────────────────────────────────────
def _load_mark_revert():
    path = ROOT / "scripts/v2/mark_revert.py"
    spec = importlib.util.spec_from_file_location("p3t7_mark_revert", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestRevert(_Base):
    def _old_code_rows(self, n):
        """옛 코드(T7 전)가 쓰는 행 = strategy_type 을 넘기지 않는 insert."""
        from services.db import insert_trade_audit
        for i in range(n):
            insert_trade_audit(U, T, 180, 100 + i, "BUY", "EMA_GC", 700.0, None, None, None, None, None,
                               None, None, None, None, None, timestamp=OLD_TS)

    def _new_code_rows(self, n, st="EMA"):
        from services.db import insert_trade_audit
        for i in range(n):
            insert_trade_audit(U, T, 180, 200 + i, "BUY", "EMA_GC", 700.0, None, None, None, None, None,
                               None, None, None, None, None, timestamp=OLD_TS, strategy_type=st)

    def redeploy(self):
        """재배포 = tradebot 재시작 → 엔진 기동 마이그레이션(boot_resume) 경로."""
        from engine import boot_resume
        boot_resume.boot_resume_all(users=[U], verify=lambda: (True, "ok", 1.0), start=lambda uid: True)

    def render(self):
        """로그인·대시보드 렌더 경로(init_db_if_needed → ensure_all_schemas)."""
        self.idb.init_db_if_needed(U)
        self.idb.ensure_all_schemas(U)

    def test_redeploy_after_revert_marks_gap(self):
        """되돌림 구간 NULL 행 3개 → 재배포 뒤 구버전 이력에 3개 보임, 구간 밖 표식 뒤 NULL 은 분류 불명."""
        self.old_db(5)
        self.migrate()                       # 표식 5
        self._new_code_rows(2)               # id 6, 7 (EMA)
        mr = _load_mark_revert()
        self.assertEqual(mr.main([U]), 0)    # revert_from = 7
        self.assertEqual(self.marks()["audit_trades.strategy_type.revert_from"], 7)
        self.assertEqual(self.marks()["orders.strategy_type.revert_from"], 5)
        self._old_code_rows(3)               # id 8, 9, 10 (NULL — 되돌린 동안)
        self.redeploy()                      # 재배포 → revert_to = 10
        m = self.marks()
        self.assertEqual(m["audit_trades.strategy_type.revert_to"], 10)
        self.assertEqual(m["orders.strategy_type.revert_to"], 5)
        self._old_code_rows(1)               # id 11 (NULL — 표식 뒤, 구간 밖)
        ids = self.history_ids()
        self.assertEqual(ids, [1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
        from services.trade_strategy import count_unknown_rows
        self.assertEqual(count_unknown_rows(U), 1)
        # 재배포 마이그레이션은 한 번만: 다시 돌려도 revert_to 그대로
        self.redeploy()
        self.render()
        self.assertEqual(self.marks()["audit_trades.strategy_type.revert_to"], 10)

    def test_render_after_mark_revert_does_not_close_gap(self):
        """mark_revert 직후 init_db_if_needed / ensure_all_schemas 를 불러도 revert_to 가 생기지 않는다(쓰기 0)."""
        self.old_db(3)
        self.migrate()
        self._new_code_rows(1)
        mr = _load_mark_revert()
        self.assertEqual(mr.main([U]), 0)
        before = self.marks()
        self.render()
        self.idb.ensure_trade_strategy_columns(U)
        self.assertEqual(self.marks(), before)
        self.assertNotIn("audit_trades.strategy_type.revert_to", self.marks())

    def test_rv_sequence_render_during_revert_then_redeploy_no_unknown(self):
        """rv.py 순서: 새 코드 행 → mark_revert → (재시작 전) 화면 렌더 → 옛 코드 행 3 → 재배포 → 분류 불명 0."""
        self.old_db(0)
        self.migrate()
        self._new_code_rows(2)
        mr = _load_mark_revert()
        self.assertEqual(mr.main([U]), 0)
        self.render()                         # 정지 전 마지막 화면 렌더 (지적 1 재현 지점)
        self._old_code_rows(3)
        self.redeploy()
        from services.trade_strategy import count_unknown_rows
        self.assertEqual(count_unknown_rows(U), 0)
        self.assertEqual(self.history_ids(), [1, 2, 3, 4, 5])

    def test_revert_from_boundary_row(self):
        """revert_from 과 같은 id 의 NULL 행은 구간 밖(구간 = revert_from < id ≤ revert_to) → 분류 불명."""
        self.old_db(2)
        self.migrate()                        # 표식 2
        self._old_code_rows(1)                # id 3 NULL (표식 뒤 — 분류 불명)
        mr = _load_mark_revert()
        self.assertEqual(mr.main([U]), 0)     # revert_from = 3
        self._old_code_rows(1)                # id 4 NULL (구간 안)
        self.redeploy()                       # revert_to = 4
        self.assertEqual(self.history_ids(), [1, 2, 4])
        from services.trade_strategy import count_unknown_rows
        self.assertEqual(count_unknown_rows(U), 1)

    def test_mark_revert_refuses_before_migration_and_twice(self):
        self.old_db(2)
        mr = _load_mark_revert()
        self.assertNotEqual(mr.main([U]), 0)      # 마이그레이션 전 DB — 쓰지 않음
        self.assertIsNone(self.marks())
        self.migrate()
        self.assertEqual(mr.main([U]), 0)
        before = self.marks()
        self.assertNotEqual(mr.main([U]), 0)      # 재배포 기록 없이 또 → 멈춤
        self.assertEqual(self.marks(), before)

    def test_mark_revert_missing_db_does_not_create(self):
        mr = _load_mark_revert()
        self.assertNotEqual(mr.main([U]), 0)
        self.assertFalse(os.path.exists(self.db_path))

    def test_mark_revert_connect_error_no_traceback(self):
        """연결 실패도 try 안 — 종료 코드 1, 출력은 'ERROR <예외 이름>' 한 줄(경로 없음)."""
        self.old_db(0)
        self.migrate()
        mr = _load_mark_revert()
        import io
        import contextlib
        buf = io.StringIO()
        with mock.patch.object(mr.sqlite3, "connect", side_effect=sqlite3.OperationalError(self.db_path)), \
                contextlib.redirect_stdout(buf):
            rc = mr.main([U])
        self.assertEqual(rc, 1)
        self.assertEqual(buf.getvalue().strip(), "ERROR OperationalError")
        self.assertNotIn(self.tmpdir, buf.getvalue())

    def test_second_revert_merges_or_stops(self):
        """두 번째 되돌림: 합칠 수 있으면 표식을 revert_to 로 올리고 새 revert_from."""
        self.old_db(5)
        self.migrate()                     # 표식 5
        self._new_code_rows(2)             # 6, 7 EMA
        mr = _load_mark_revert()
        self.assertEqual(mr.main([U]), 0)  # from 7
        self._old_code_rows(2)             # 8, 9 NULL
        self.redeploy()                    # to 9
        self._new_code_rows(1)             # 10 EMA
        self.assertEqual(mr.main([U]), 0)  # 합침: 표식 9, from 10, to 없음
        m = self.marks()
        self.assertEqual(m["audit_trades.strategy_type.legacy_max_id"], 9)
        self.assertEqual(m["audit_trades.strategy_type.revert_from"], 10)
        self.assertNotIn("audit_trades.strategy_type.revert_to", m)
        self._old_code_rows(1)             # 11 NULL
        self.redeploy()                    # to 11
        self.assertEqual(self.history_ids(), list(range(1, 12)))

    def test_second_revert_merges_with_pullback_before_gap(self):
        """수정 1회차: 「첫 PULLBACK 행보다 앞섬」 조건 삭제 — PULLBACK 행이 구간 앞에 있어도 null_between 0 이면 합침.
        PULLBACK 행(전략 칸 있음)은 표식을 올려도 분류가 그대로다."""
        self.old_db(5)
        self.migrate()
        self._new_code_rows(1, st="PULLBACK")  # 6 PULLBACK
        mr = _load_mark_revert()
        self.assertEqual(mr.main([U]), 0)      # from 6
        self._old_code_rows(2)                 # 7, 8 NULL
        self.redeploy()                        # to 8
        self.assertEqual(mr.main([U]), 0)      # 합침
        m = self.marks()
        self.assertEqual(m["audit_trades.strategy_type.legacy_max_id"], 8)
        self.assertEqual(m["audit_trades.strategy_type.revert_from"], 8)
        self.assertEqual(self.history_ids(), [1, 2, 3, 4, 5, 7, 8])  # PULLBACK 6 은 계속 빠짐

    def test_second_revert_stops_when_unknown_rows_before_gap(self):
        """표식 뒤 ~ revert_from 사이에 분류 불명(NULL) 행이 있으면 합칠 수 없음 → 종료 코드 4, 쓰기 0."""
        self.old_db(5)
        self.migrate()
        self._old_code_rows(1)                 # 6 NULL (분류 불명)
        self._new_code_rows(1)                 # 7 EMA
        mr = _load_mark_revert()
        self.assertEqual(mr.main([U]), 0)      # from 7
        self._old_code_rows(2)                 # 8, 9 NULL
        self.redeploy()                        # to 9
        before = self.marks()
        self.assertEqual(mr.main([U]), 4)
        self.assertEqual(self.marks(), before)


# ─────────────────────────────────────────────────────────────
# 기록 경로 · 구버전 이력
# ─────────────────────────────────────────────────────────────
class TestPaths(_Base):
    def setUp(self):
        super().setUp()
        self.old_db(2)
        self.migrate()

    def _all_strategy(self, table):
        return [r[0] for r in self.q(f"SELECT strategy_type FROM {table} WHERE id > 2 ORDER BY id")]

    def test_ema_rows_tagged_all_paths(self):
        """배포 뒤 EMA 운용 중 모든 기록 경로 → 모든 행 strategy_type='EMA', 구버전 이력에 보임."""
        self.set_active("EMA")
        import core.trader as tr_mod
        tr = self.live_trader("EMA")
        meta = {"reason": "EMA_GC", "bar": 5, "bar_time": "2026-10-28T10:00:00+09:00"}
        # (1) LIVE 시장가 매수 요청
        with mock.patch.object(tr_mod, "_upbit_buy_market", return_value=_ok_call("u-mkt")):
            self.assertEqual(tr.buy_market(700.0, T, meta=dict(meta)).get("uuid"), "u-mkt")
        # (2) LIVE 지정가 매수 요청
        with mock.patch.object(tr_mod, "_upbit_buy_limit", return_value=_ok_call("u-lim")):
            self.assertEqual(tr.buy_limit(700.0, T, meta=dict(meta), interval_sec=180).get("uuid"), "u-lim")
        # (3) 거래소 거절 (매도)
        with mock.patch.object(tr_mod, "_upbit_sell_market", return_value=_reject_call()):
            self.assertEqual(tr.sell_market(10.0, T, 700.0, meta=dict(meta, reason="EMA_DC")), {})
        # (4) 주문 전 차단 (잔고 0)
        tr0 = self.live_trader("EMA")
        tr0._krw_balance = lambda: 0.0
        self.assertEqual(tr0.buy_market(700.0, T, meta=dict(meta)), {})
        # (5) reconciler 체결 감사 (시장가 주문)
        orc = self.reconciler()
        self.finalize(orc, "u-mkt")
        # (6) 미체결 취소 (지정가 주문)
        orc._on_timeout_cancel_final("u-lim", U, T, {"volume": "10", "price": "700"}, 0.0, 0.0,
                                     {"meta": {"reason": "force_buy", "limit_price": 700.0}})
        # (7) HTS 매수 감지 (엔진 활성 전략 EMA)
        self.hts_detect("EMA")
        # (8) HTS_SELL (엔진 전략)
        self.hts_sell("EMA")
        # (9)(10) 구버전 강제 매수·매도 (대시보드가 넘긴 전략) — TEST 모드
        from services.trade_strategy import force_trade_strategy_type
        st = force_trade_strategy_type(U, "EMA")
        self.assertEqual(st, "EMA")
        ttr = self.make_test_trader(st)
        from services.db import update_account
        update_account(U, 1_000_000)  # (7) 잔고 동기화가 원화를 1,000 으로 바꿔 둠 — TEST 매수용으로 되돌림
        self.assertTrue(ttr.buy_market(700.0, T, meta={"reason": "force_buy"}).get("qty"))
        self.assertTrue(ttr.sell_market(1.0, T, 710.0, meta={"reason": "force_sell"}).get("qty"))

        at_types = [r[0] for r in self.q("SELECT type FROM audit_trades WHERE id > 2 ORDER BY id")]
        for kind in ("SELL_REJECTED", "BUY_REJECTED", "BUY", "BUY_CANCELED", "HTS_SELL", "SELL"):
            self.assertIn(kind, at_types)
        self.assertIn("HTS_BUY", [r[0] for r in self.q("SELECT reason FROM audit_trades")])
        self.assertTrue(at_types and all(s == "EMA" for s in self._all_strategy("audit_trades")),
                        list(zip(at_types, self._all_strategy("audit_trades"))))
        or_rows = self._all_strategy("orders")
        self.assertGreaterEqual(len(or_rows), 4)  # 시장가·지정가·강제 매수·강제 매도
        self.assertTrue(all(s == "EMA" for s in or_rows), or_rows)
        # 구버전 이력에 전부 보임
        all_ids = sorted(r[0] for r in self.q("SELECT id FROM audit_trades"))
        self.assertEqual(self.history_ids(), all_ids)
        from services.trade_strategy import count_unknown_rows
        self.assertEqual(count_unknown_rows(U), 0)

    def test_old_history_excludes_pullback_rows(self):
        """PULLBACK 운용 중 LIVE 체결(reconciler)·앱 매도(HTS_SELL)·구버전 강제 매도 행 → 구버전 이력 0건."""
        before_trades, before_pnl, _ = self.history()
        self.set_active("PULLBACK")
        import core.trader as tr_mod
        tr = self.live_trader("PULLBACK")
        with mock.patch.object(tr_mod, "_upbit_buy_market", return_value=_ok_call("u-pb")):
            tr.buy_market(700.0, T, meta={"reason": "PB_GOLDEN", "bar": 9})
        self.finalize(self.reconciler(), "u-pb")
        self.hts_sell("PULLBACK")
        from services.trade_strategy import force_trade_strategy_type
        st = force_trade_strategy_type(U, "EMA")   # 대시보드 params 는 EMA 여도 PULLBACK 운용 중이면 PULLBACK
        self.assertEqual(st, "PULLBACK")
        ttr = self.make_test_trader(st)
        ttr.buy_market(700.0, T, meta={"reason": "force_buy"})
        ttr.sell_market(1.0, T, 710.0, meta={"reason": "force_sell"})
        new_at = self._all_strategy("audit_trades")
        self.assertTrue(new_at and all(s == "PULLBACK" for s in new_at), new_at)
        self.assertTrue(all(s == "PULLBACK" for s in self._all_strategy("orders")))
        after_trades, after_pnl, _ = self.history()
        self.assertEqual(after_trades, before_trades)
        self.assertEqual(after_pnl, before_pnl)
        self.assertFalse([t for t in after_trades if t["id"] > 2])

    def test_late_fill_keeps_order_strategy(self):
        """EMA 로 발주 → 전환(활성 PULLBACK) → 체결 기록 → EMA."""
        self.set_active("EMA")
        import core.trader as tr_mod
        tr = self.live_trader("EMA")
        with mock.patch.object(tr_mod, "_upbit_buy_market", return_value=_ok_call("u-late")):
            tr.buy_market(700.0, T, meta={"reason": "EMA_GC", "bar": 5})
        self.set_active("PULLBACK")
        orc = self.reconciler()
        orc.register_hts_detect_callback(U, T, _EngineStub("PULLBACK")._on_hts_detect)
        self.finalize(orc, "u-late")
        row = self.q("SELECT type, strategy_type FROM audit_trades WHERE id > 2")
        self.assertEqual(row, [("BUY", "EMA")])

    def test_hts_detect_uses_engine_strategy(self):
        self.set_active("EMA")
        self.hts_detect("PULLBACK")   # 엔진(콜백 주인)이 PULLBACK
        self.assertEqual(self.q("SELECT reason, strategy_type FROM audit_trades WHERE id > 2"),
                         [("HTS_BUY", "PULLBACK")])

    def test_hts_detect_without_engine_uses_active_file(self):
        self.set_active("EMA")
        self.hts_detect(None)         # 엔진 콜백 없음 → 활성 전략 파일
        self.assertEqual(self.q("SELECT reason, strategy_type FROM audit_trades WHERE id > 2"),
                         [("HTS_BUY", "EMA")])

    def test_pullback_sync_row_tagged(self):
        from core.strategy_engine import StrategyEngine
        stub = SimpleNamespace(user_id=U, ticker=T, interval_sec=180, bar_count=7, strategy_type="PULLBACK",
                               position=SimpleNamespace(entry_bar=3, avg_price=700.0))
        StrategyEngine._pullback_record_sync(stub, wallet=10.0, state_qty=9.0, cls="wallet_more", note="n")
        self.assertEqual(self.q("SELECT type, strategy_type FROM audit_trades WHERE id > 2"),
                         [("PULLBACK_SYNC", "PULLBACK")])

    def test_null_after_mark_is_unknown(self):
        """표식 뒤 NULL 행 → 구버전 이력 0, 분류 불명 1 (알림은 TestFix2 — 화면 경고 없음, 결정 1028-06)."""
        from services.db import insert_trade_audit
        insert_trade_audit(U, T, 180, 9, "SELL", "EMA_DC", 700.0, None, None, 690.0, 1, 3, None, None, None,
                           None, None, timestamp=OLD_TS)
        self.assertEqual(self.history_ids(), [1, 2])
        from services.trade_strategy import count_unknown_rows
        self.assertEqual(count_unknown_rows(U), 1)
        self.assertEqual(count_unknown_rows(U, "orders"), 0)

    def test_pnl_orders_query_excludes_pullback_orders(self):
        """compute_pnl_for_snapshot 의 orders 조회도 같은 조건: 같은 시각 PULLBACK 매도 주문은 짝으로 안 씀."""
        from services.db import insert_order, insert_trade_audit
        ts = "2026-10-02T10:00:00+09:00"
        insert_trade_audit(U, T, 180, 9, "SELL", "EMA_DC", 110.0, None, None, 100.0, 1, 3, None, None, None,
                           None, None, timestamp=ts, strategy_type="EMA")
        self.exec("INSERT INTO orders (user_id, timestamp, ticker, side, price, volume, status, state, "
                  "executed_volume, avg_price, paid_fee, executed_at, strategy_type) VALUES (?, ?, ?, 'SELL', 110, "
                  "5, 'completed', 'FILLED', 5, 110, 0, ?, 'PULLBACK')", (U, ts, T, ts))
        from services import settings_history as sh
        pnl_pb_only = sh.compute_pnl_for_snapshot(U, self.snapshot_id())
        insert_order(U, T, "SELL", 110.0, 2.0, "completed", strategy_type="EMA",
                     state="FILLED", executed_volume=2.0, avg_price=110.0, paid_fee=0.0, executed_at=ts)
        pnl_both = sh.compute_pnl_for_snapshot(U, self.snapshot_id())
        old_sells_pnl = pnl_pb_only["realized_pnl_krw"] or 0.0
        self.assertAlmostEqual((pnl_both["realized_pnl_krw"] or 0.0) - old_sells_pnl, (110.0 - 100.0) * 2.0)


class TestInsertCompat(_Base):
    def test_insert_without_column_still_writes(self):
        """마이그레이션이 안 된 DB(칸 없음)에서 전략을 넘겨도 EMA 기록은 계속된다(칸만 빠짐, WARNING)."""
        self.old_db(0)
        from services.db import insert_order, insert_trade_audit
        with self.assertLogs("services.db", "WARNING"):
            insert_order(U, T, "BUY", 700.0, 1.0, "completed", strategy_type="EMA")
            insert_trade_audit(U, T, 180, 1, "BUY", "EMA_GC", 700.0, None, None, None, None, None, None, None,
                               None, None, None, strategy_type="EMA")
        self.assertEqual(self.q("SELECT COUNT(*) FROM orders")[0][0], 1)
        self.assertEqual(self.q("SELECT COUNT(*) FROM audit_trades")[0][0], 1)

    def test_old_call_signature_unchanged(self):
        """전략 인자 없는 기존 호출: 행 1개씩, 새 칸 NULL, 반환값 None(지금과 같음) — 되돌린 옛 코드와 같은 행."""
        self.old_db(0)
        self.migrate()
        from services.db import insert_order, insert_trade_audit
        self.assertIsNone(insert_order(U, T, "BUY", 700.0, 1.0, "completed"))
        self.assertIsNone(insert_trade_audit(U, T, 180, 1, "BUY", "EMA_GC", 700.0, None, None, None, None, None,
                                             None, None, None, None, None))
        self.assertEqual(self.q("SELECT strategy_type FROM orders"), [(None,)])
        self.assertEqual(self.q("SELECT strategy_type FROM audit_trades"), [(None,)])

    def test_strategy_normalized_upper(self):
        self.old_db(0)
        self.migrate()
        from services.db import insert_order
        insert_order(U, T, "BUY", 700.0, 1.0, "completed", strategy_type=" ema ")
        self.assertEqual(self.q("SELECT strategy_type FROM orders"), [("EMA",)])

    def test_dashboard_force_traders_pass_strategy(self):
        """구버전 강제 매수·매도 UpbitTrader(...) 두 곳 모두 strategy_type= 를 넘긴다(X5)."""
        src = (ROOT / "pages/dashboard.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
                 and getattr(n.func, "id", None) == "UpbitTrader"]
        force = [c for c in calls if not any(k.arg == "test_mode" and isinstance(k.value, ast.Constant)
                                             and k.value.value is False for k in c.keywords)]
        self.assertEqual(len(force), 2, [ast.unparse(c) for c in calls])
        for c in force:
            kw = {k.arg: ast.unparse(k.value) for k in c.keywords}
            self.assertIn("strategy_type", kw, ast.unparse(c))
            self.assertIn("force_trade_strategy_type", kw["strategy_type"])


class TestFix1(_Base):
    """수정 1회차 추가 시험."""

    def test_unrelated_operational_error_reraised_no_retry(self):
        """strategy_type 과 무관한 OperationalError(locked·표 없음)는 다시 넣지 않고 그대로 던진다."""
        import services.db as sdb
        for msg in ("database is locked", "no such table: orders"):
            calls = []

            class _Cur:
                def execute(self, sql, vals):
                    calls.append(sql)
                    raise sqlite3.OperationalError(msg)

            with self.assertRaises(sqlite3.OperationalError):
                sdb._insert_with_strategy(_Cur(), "orders", ["user_id"], [U], "EMA")
            self.assertEqual(len(calls), 1, msg)

    def test_missing_column_warning_once(self):
        """칸 없음 경고는 표·프로세스당 1회 — 두 번 넣어도 WARNING 1줄, 행은 2개."""
        self.old_db(0)
        import services.db as sdb
        sdb._STRATEGY_COL_MISSING_WARNED.discard("orders")
        with self.assertLogs("services.db", "WARNING") as cm:
            sdb.insert_order(U, T, "BUY", 700.0, 1.0, "completed", strategy_type="EMA")
            sdb.insert_order(U, T, "BUY", 700.0, 1.0, "completed", strategy_type="EMA")
            sdb.logger.warning("sentinel")
        self.assertEqual(len([m for m in cm.output if "[STRATEGY-COL]" in m]), 1, cm.output)
        self.assertEqual(self.q("SELECT COUNT(*) FROM orders")[0][0], 2)

    def test_recheck_after_begin_finds_nothing(self):
        """BEGIN IMMEDIATE 뒤 다시 읽었더니 할 일이 없으면(다른 프로세스가 먼저 함) 쓰기 없이 잠금만 놓는다."""
        self.old_db(2)
        self.migrate()
        before = self.marks()
        stmts = []
        orig = self.idb._connect

        def traced(uid):
            c = orig(uid)
            c.set_trace_callback(stmts.append)
            return c

        with mock.patch.object(self.idb, "_connect", traced), \
                mock.patch.object(self.idb, "_trade_strategy_work",
                                  side_effect=[[("audit_trades", "add_column")], []]):
            self.assertTrue(self.idb.ensure_trade_strategy_columns(U))
        joined = "\n".join(stmts).upper()
        self.assertIn("BEGIN IMMEDIATE", joined)
        for kw in ("INSERT", "ALTER", "CREATE", "UPDATE", "DELETE"):
            self.assertNotIn(kw, joined, kw)
        self.assertEqual(self.marks(), before)
        # 잠금이 남지 않았는지: 다른 연결이 바로 쓰기 잠금을 잡을 수 있음
        c = sqlite3.connect(self.db_path, timeout=0.1)
        try:
            c.execute("BEGIN IMMEDIATE")
            c.execute("ROLLBACK")
        finally:
            c.close()

    def test_read_bounds_d3_when_marks_missing_warns_once(self):
        """읽기 경로: 표식이 없으면 D3 정의로 계산만(쓰기 0), WARNING 은 (DB, 표) 당 1회."""
        self.old_db(5)
        self.migrate()
        self.exec("UPDATE audit_trades SET strategy_type='EMA' WHERE id IN (3, 4)")
        self.exec("DELETE FROM schema_marks")
        import services.trade_strategy as ts
        ts._MARK_MISSING_WARNED.clear()
        conn = sqlite3.connect(self.db_path)
        try:
            with self.assertLogs("services.trade_strategy", "WARNING") as cm:
                b1 = ts.read_bounds(conn, "audit_trades")
                b2 = ts.read_bounds(conn, "audit_trades")
                ts.logger.warning("sentinel")
            self.assertEqual(conn.total_changes, 0)
        finally:
            conn.close()
        self.assertEqual(b1, {"mark": 2, "rv_from": None, "rv_to": None})
        self.assertEqual(b2, b1)
        self.assertEqual(len([m for m in cm.output if "표식 없음" in m]), 1, cm.output)
        self.assertEqual(self.marks(), {})  # 읽기 경로는 쓰지 않음

    def test_macd_rows_tagged_and_visible(self):
        """MACD 운용: trader 시장가 요청 → reconciler 체결 → 두 행 모두 MACD, 구버전 이력에 보임."""
        self.old_db(2)
        self.migrate()
        self.set_active("MACD")
        import core.trader as tr_mod
        tr = self.live_trader("MACD")
        with mock.patch.object(tr_mod, "_upbit_buy_market", return_value=_ok_call("u-macd")):
            tr.buy_market(700.0, T, meta={"reason": "GOLDEN_CROSS", "bar": 3})
        self.finalize(self.reconciler(), "u-macd")
        self.assertEqual(self.q("SELECT strategy_type FROM orders WHERE id > 2"), [("MACD",)])
        self.assertEqual(self.q("SELECT type, strategy_type FROM audit_trades WHERE id > 2"), [("BUY", "MACD")])
        self.assertIn(3, self.history_ids())

    def test_live_sell_success_order_tagged(self):
        """LIVE 매도 성공 → orders SELL REQUESTED 행에 전략."""
        self.old_db(0)
        self.migrate()
        import core.trader as tr_mod
        tr = self.live_trader("EMA")
        with mock.patch.object(tr_mod, "_upbit_sell_market", return_value=_ok_call("u-sell")):
            res = tr.sell_market(10.0, T, 700.0, meta={"reason": "EMA_DC", "bar": 9})
        self.assertEqual(res.get("uuid"), "u-sell")
        self.assertEqual(self.q("SELECT side, state, provider_uuid, strategy_type FROM orders"),
                         [("SELL", "REQUESTED", "u-sell", "EMA")])


class TestFix2(_Base):
    """수정 2·3회차: 분류 불명은 화면이 아니라 운영 로그·텔레그램으로(결정 1028-06), 재개 뒤 알림, 빈 되돌림 구간 경고."""

    FORBIDDEN = ("T7", "D2", "D3", "PULLBACK", "audit_trades", "orders", "[STRATEGY", "[migrate]", U)

    def _boot(self, sent, users=None, start=None):
        from engine import boot_resume
        with mock.patch("services.notifier.send", side_effect=lambda *a, **k: sent.append((a, k)) or True):
            return boot_resume.boot_resume_all(users=users or [U], verify=lambda: (True, "ok", 1.0),
                                               start=start or (lambda uid: True))

    def _unknown_db(self):
        self.old_db(2)
        self.migrate()
        from services.db import insert_trade_audit, insert_order
        for i in range(2):
            insert_trade_audit(U, T, 180, 9 + i, "BUY", "EMA_GC", 700.0, None, None, None, None, None, None, None,
                               None, None, None, timestamp=OLD_TS)
        insert_order(U, T, "BUY", 700.0, 1.0, "completed")

    def _strategy_sends(self, sent):
        return [(a, k) for a, k in sent if str(k.get("dedupe_key", "")).startswith("strategy_unknown:")]

    def test_no_unknown_warning_on_screen(self):
        """감사 화면에 분류 불명 경고 함수·행 수 조회·경고 문구가 없다(결정 1028-06).
        2차 T8 수정 1회차: 범위를 경고로 좁힘 — 화면의 「전략」 칸은 classify_rows 를 직접 import 해도 된다."""
        src = (ROOT / "pages/audit_viewer.py").read_text(encoding="utf-8")
        for banned in ("분류 불명", "전략 구분 확인 필요", "전략 구분이 비어",
                       "count_unknown_rows", "report_unknown_rows", "unknown_warning_text"):
            self.assertNotIn(banned, src, banned)
        names = {n.id for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Name)}
        names |= {a.name for n in ast.walk(ast.parse(src)) if isinstance(n, ast.ImportFrom) for a in n.names}
        self.assertFalse(names & {"unknown_warning_text", "count_unknown_rows", "report_unknown_rows"})

    def test_unknown_rows_logged_and_notified_once(self):
        """n>0: WARNING [STRATEGY-UNKNOWN] user=… audit_trades=n orders=m(로그에만) + 쉬운 말 알림 1회(dedupe 24시간)."""
        self._unknown_db()
        sent = []
        with self.assertLogs("services.trade_strategy", "WARNING") as cm:
            self._boot(sent)
        lines = [m for m in cm.output if "[STRATEGY-UNKNOWN]" in m]
        self.assertEqual(len(lines), 1, cm.output)
        self.assertIn(f"user={U} audit_trades=2 orders=1", lines[0])
        mine = self._strategy_sends(sent)
        self.assertEqual(len(mine), 1)
        (level, title, body), kw = mine[0]
        self.assertEqual(level, "WARNING")
        self.assertEqual(kw, {"dedupe_key": f"strategy_unknown:{U}", "dedupe_ttl": 86400})
        self.assertIn("3건", body)  # 체결 기록 2 + 주문 1
        self.assertIn("투자자님이 따로 하실 일은 없습니다", body)
        for code in self.FORBIDDEN:
            self.assertNotIn(code, title + body, code)

    def test_no_unknown_rows_no_log_no_notify(self):
        self.old_db(2)
        self.migrate()
        sent = []
        import logging
        records = []

        class _H(logging.Handler):
            def emit(self, r):
                records.append(r.getMessage())

        h = _H()
        lg = logging.getLogger("services.trade_strategy")
        lg.addHandler(h)
        try:
            self._boot(sent)
        finally:
            lg.removeHandler(h)
        self.assertFalse([m for m in records if "[STRATEGY-UNKNOWN]" in m])
        self.assertEqual(self._strategy_sends(sent), [])

    def _set_live_target(self):
        from services.db import set_engine_status
        set_engine_status(U, True, last_mode="LIVE")

    def test_slow_notify_does_not_delay_resume(self):
        """알림이 오래 걸려도(가짜 send 0.5초) 엔진 재개(start)가 먼저 불린다.
        2차 T8 수정 1회차: 절대 시간 단언(0.4초, 부하에 흔들림)을 빼고 send 안에서 「start 가 이미 불렸음」을 단언."""
        self._unknown_db()
        self._set_live_target()
        events = []
        started_before_send = []

        def slow_send(level, title, body="", dedupe_key=None, dedupe_ttl=None):
            if str(dedupe_key or "").startswith("strategy_unknown:"):
                started_before_send.append("start" in events)   # 표식: 알림 시작 때 재개가 이미 끝났는가
                events.append("send_begin")
                time.sleep(0.5)
            return True

        def start(uid):
            events.append("start")
            return True

        from engine import boot_resume
        with mock.patch("services.notifier.send", side_effect=slow_send):
            res = boot_resume.boot_resume_all(users=[U], verify=lambda: (True, "ok", 1.0), start=start)
        self.assertEqual(res, {U: "success"})
        self.assertEqual(events, ["start", "send_begin"])
        self.assertEqual(started_before_send, [True])  # 재개는 느린 알림을 기다리지 않음

    def test_report_exception_does_not_affect_other_users(self):
        """report 예외(첫 사용자)여도 모든 사용자 재개는 그대로, 다음 사용자 report 는 불림."""
        self._unknown_db()
        self._set_live_target()
        U2 = U + "b"
        from services.db import set_engine_status
        set_engine_status(U2, True, last_mode="LIVE")  # 같은 임시 DB 의 두 번째 사용자 행
        started, reported = [], []

        def boom(uid):
            reported.append(uid)
            if uid == U:
                raise RuntimeError("x")
            return (0, 0)

        with mock.patch("services.trade_strategy.report_unknown_rows", side_effect=boom):
            res = self._boot([], users=[U, U2], start=lambda uid: started.append(uid) or True)
        self.assertEqual(started, [U, U2])  # 같은 임시 DB 라 둘 다 대상
        self.assertEqual(res, {U: "success", U2: "success"})
        self.assertEqual(reported, [U, U2])

    def test_report_runs_when_no_resume_targets(self):
        self._unknown_db()
        sent = []
        self._boot(sent)  # 재개 대상 없음
        self.assertEqual(len(self._strategy_sends(sent)), 1)

    def test_empty_revert_gap_warns_distinctly(self):
        """mark_revert 뒤 새 코드인 채 재시작 → 두 표 모두 빈 구간 → 구분되는 WARNING 1줄(두 표 함께)."""
        self.old_db(3)
        self.migrate()
        mr = _load_mark_revert()
        self.assertEqual(mr.main([U]), 0)
        with self.assertLogs("services.init_db", "WARNING") as cm:
            self.idb.close_strategy_revert_gap(U)
        empty = [m for m in cm.output if "strategy revert gap EMPTY" in m]
        self.assertEqual(len(empty), 1, cm.output)
        self.assertIn("mark_revert 뒤 새 코드로 재시작했는지 확인", empty[0])
        self.assertIn("audit_trades", empty[0])
        self.assertIn("orders", empty[0])
        m = self.marks()
        self.assertEqual(m["audit_trades.strategy_type.revert_to"], m["audit_trades.strategy_type.revert_from"])

    def test_nonempty_revert_gap_no_empty_warning(self):
        """두 표 모두 행이 생김 → EMPTY 없음, 표마다 gap closed."""
        self.old_db(3)
        self.migrate()
        mr = _load_mark_revert()
        self.assertEqual(mr.main([U]), 0)
        from services.db import insert_trade_audit, insert_order
        insert_trade_audit(U, T, 180, 9, "BUY", "EMA_GC", 700.0, None, None, None, None, None, None, None,
                           None, None, None, timestamp=OLD_TS)
        insert_order(U, T, "BUY", 700.0, 1.0, "completed")
        with self.assertLogs("services.init_db", "WARNING") as cm:
            self.idb.close_strategy_revert_gap(U)
        self.assertEqual([m for m in cm.output if "gap EMPTY" in m], [])
        for t in ("audit_trades", "orders"):
            self.assertTrue(any(f"strategy revert gap closed | table={t}" in m for m in cm.output), cm.output)

    def test_one_side_empty_gap_no_empty_warning(self):
        """audit_trades 만 행이 생김(orders 는 빈 구간) → EMPTY 없음, 두 표 모두 일반 gap closed."""
        self.old_db(3)
        self.migrate()
        mr = _load_mark_revert()
        self.assertEqual(mr.main([U]), 0)
        from services.db import insert_trade_audit
        insert_trade_audit(U, T, 180, 9, "BUY", "EMA_GC", 700.0, None, None, None, None, None, None, None,
                           None, None, None, timestamp=OLD_TS)
        with self.assertLogs("services.init_db", "WARNING") as cm:
            self.idb.close_strategy_revert_gap(U)
        self.assertEqual([m for m in cm.output if "gap EMPTY" in m], [])
        for t in ("audit_trades", "orders"):
            self.assertTrue(any(f"strategy revert gap closed | table={t}" in m for m in cm.output), cm.output)


class TestA18(_Base):
    def test_a18_history_same_before_after(self):
        """기존 행만 있는 DB 의 이력 화면 결과(스냅샷 목록·거래·손익)가 마이그레이션 전후·PULLBACK 거래 추가 전후로 같음."""
        self.old_db(6)
        # 두 번째 스냅샷(구간 경계 확인)
        self.exec("INSERT INTO settings_history (user_id, saved_at, source_page, strategy_type, params_json, "
                  "conditions_json) VALUES (?, '2026-10-05T00:00:00+09:00', 'set_config', 'EMA', '{}', '{}')", (U,))
        before = self.history()
        self.migrate()
        self.assertEqual(self.history(), before)
        from services.db import insert_trade_audit, insert_order
        insert_trade_audit(U, T, 180, 50, "SELL", "PB_TP", 120.0, None, None, 100.0, 1, 3, None, None, None,
                           None, None, timestamp=OLD_TS, strategy_type="PULLBACK")
        insert_order(U, T, "SELL", 120.0, 3.0, "completed", strategy_type="PULLBACK", state="FILLED",
                     executed_volume=3.0, avg_price=120.0, paid_fee=0.0, executed_at=OLD_TS)
        self.assertEqual(self.history(), before)


if __name__ == "__main__":
    unittest.main()
