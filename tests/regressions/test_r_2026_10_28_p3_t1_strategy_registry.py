"""P3 T1 (결정 D1): 전략 등록 — 엔진 전용 PULLBACK, 구버전 목록 불변."""
import ast
import os
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# config 가 import 때 st.secrets 를 읽으므로 cwd 를 바꾸기 전에 미리 import 한다.
import config  # noqa: E402
import engine.engine_manager as engine_manager  # noqa: E402
import engine.params as params_mod  # noqa: E402


def _parse(rel):
    return ast.parse((REPO / rel).read_text(encoding="utf-8"))


class InTmpCwd(unittest.TestCase):
    def setUp(self):
        self._cwd = os.getcwd()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        os.chdir(self.tmp.name)
        self.addCleanup(os.chdir, self._cwd)

    def write_active(self, user, text):
        Path(f"{user}_active_strategy.txt").write_text(text)


class StrategyRegistryTests(InTmpCwd):
    def test_strategy_types_unchanged(self):
        self.assertEqual(config.STRATEGY_TYPES, ["MACD", "EMA"])
        self.assertEqual(config.DEFAULT_STRATEGY_TYPE, "MACD")

    def test_load_active_strategy_default_hides_pullback(self):
        load_active_strategy = params_mod.load_active_strategy

        self.write_active("u1", "PULLBACK")
        self.assertIsNone(load_active_strategy("u1"))
        # 기존 값은 그대로
        self.write_active("u1", "EMA")
        self.assertEqual(load_active_strategy("u1"), "EMA")
        self.write_active("u1", "MACD")
        self.assertEqual(load_active_strategy("u1"), "MACD")

    def test_load_active_strategy_engine_only(self):
        load_active_strategy = params_mod.load_active_strategy

        self.write_active("u1", "PULLBACK")
        self.assertEqual(load_active_strategy("u1", include_engine_only=True), "PULLBACK")
        self.write_active("u1", "EMA")
        self.assertEqual(load_active_strategy("u1", include_engine_only=True), "EMA")
        self.write_active("u1", "XYZ")
        self.assertIsNone(load_active_strategy("u1", include_engine_only=True))

    def test_live_params_accepts_pullback(self):
        ENGINE_STRATEGY_TYPES, LiveParams = params_mod.ENGINE_STRATEGY_TYPES, params_mod.LiveParams

        self.assertEqual(ENGINE_STRATEGY_TYPES, ("MACD", "EMA", "PULLBACK"))
        p = LiveParams(ticker="KRW-JTO", interval="minute3", strategy_type="PULLBACK")
        self.assertEqual(p.strategy_type, "PULLBACK")
        p = LiveParams(ticker="KRW-JTO", interval="minute3", strategy_type="XYZ")
        self.assertEqual(p.strategy_type, "MACD")
        p = LiveParams(ticker="KRW-JTO", interval="minute3", strategy_type="ema")
        self.assertEqual(p.strategy_type, "EMA")

    def test_engine_manager_prefers_file_for_pullback(self):
        decide = engine_manager._decide_strategy_type

        # 활성 파일 PULLBACK → 세션(EMA)보다 먼저
        self.write_active("u1", "PULLBACK")
        self.assertEqual(decide("u1", "EMA"), "PULLBACK")
        self.assertEqual(decide("u1", None), "PULLBACK")
        # 활성 파일 EMA·세션 MACD → 지금처럼 세션 우선
        self.write_active("u1", "EMA")
        self.assertEqual(decide("u1", "MACD"), "MACD")
        # 세션 없음 → 활성 파일
        self.assertEqual(decide("u1", None), "EMA")
        # 세션·활성 파일 없음 → mtime, 그것도 없으면 기본값
        self.assertEqual(decide("nobody", None), "MACD")
        Path("nobody_latest_params_EMA.json").write_text("{}")
        self.assertEqual(decide("nobody", None), "EMA")

    def test_engine_runner_pullback_refuses_before_load_params(self):
        import threading
        from unittest import mock

        self.write_active("u1", "PULLBACK")
        lock = threading.Lock()
        stop_event = threading.Event()
        load_params = mock.MagicMock(name="load_params")
        trader_cls = mock.MagicMock(name="UpbitTrader")
        insert_log = mock.MagicMock(name="insert_log")
        patches = [
            mock.patch.object(engine_manager, "st", mock.MagicMock(session_state={"strategy_type": "EMA"})),
            mock.patch.object(engine_manager, "load_params", load_params),
            mock.patch.object(engine_manager, "UpbitTrader", trader_cls),
            mock.patch.object(engine_manager, "get_user_lock", return_value=lock),
            mock.patch.object(engine_manager, "insert_log", insert_log),
            mock.patch.object(engine_manager, "log_to_file"),
            mock.patch.object(engine_manager, "update_engine_status"),
            mock.patch.object(engine_manager, "set_engine_status"),
            mock.patch.object(engine_manager, "set_thread_status"),
            mock.patch.object(engine_manager, "remove_engine_thread"),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

        # 결함이 다시 들어오면 runner 가 엔진 루프에서 멈추므로, 별도 스레드로 돌려 시간 안에 끝나는지 본다.
        runner = threading.Thread(
            target=engine_manager.EngineManager()._engine_runner,
            args=("u1", stop_event, False, "LIVE"),
            daemon=True,
        )
        runner.start()
        runner.join(timeout=5)
        if runner.is_alive():
            stop_event.set()
            runner.join(timeout=2)
            self.fail("_engine_runner 가 PULLBACK 에서 5초 안에 끝나지 않음(기동 거부 없음)")

        load_params.assert_not_called()  # 신버전 저장 형식을 MACD 기본값으로 읽지 않음
        trader_cls.assert_not_called()   # 실제 키로 trader 를 만들지 않음
        self.assertTrue(stop_event.is_set())
        self.assertFalse(lock.locked())  # 잠금 해제(좀비 「실행 중」 없음)
        errors = [c.args[2] for c in insert_log.call_args_list if c.args[1] == "ERROR"]
        self.assertTrue(any("[PULLBACK-PARAMS]" in m for m in errors))

    def test_live_loop_no_strategy_init_for_pullback(self):
        tree = _parse("engine/live_loop.py")
        fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "run_live_loop")

        def calls_init(node):
            return any(
                isinstance(c, ast.Call)
                and isinstance(c.func, ast.Name)
                and c.func.id in ("record_strategy_init", "seed_initial_snapshot")
                for c in ast.walk(node)
            )

        guarded = 0
        for node in ast.walk(fn):
            if isinstance(node, ast.If) and calls_init(node):
                test_src = ast.unparse(node.test)
                if "PULLBACK" in test_src and "!=" in test_src:
                    guarded += 1
        self.assertGreaterEqual(guarded, 1)
        # 가드 밖에서 부르는 곳이 없어야 한다: 모든 호출이 가드 If 의 body 안
        all_calls = [
            c for c in ast.walk(fn)
            if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
            and c.func.id in ("record_strategy_init", "seed_initial_snapshot")
        ]
        inside = set()
        for node in ast.walk(fn):
            if isinstance(node, ast.If) and "PULLBACK" in ast.unparse(node.test) and "!=" in ast.unparse(node.test):
                for c in ast.walk(node):
                    inside.add(id(c))
        for c in all_calls:
            self.assertIn(id(c), inside)

    def test_live_loop_pullback_refuses_start_with_error_log(self):
        import queue
        import threading
        from unittest import mock
        import engine.live_loop as live_loop

        params = params_mod.LiveParams(ticker="KRW-JTO", interval="minute3", strategy_type="PULLBACK")
        trader = mock.MagicMock(name="trader")
        stop_event = threading.Event()
        with mock.patch.object(live_loop, "get_reconciler") as get_rec, \
                mock.patch("services.db.clear_stale_hts_flags") as hts, \
                self.assertLogs(live_loop.logger, level="ERROR") as logs:
            live_loop.run_live_loop(params, queue.Queue(), trader, stop_event, False, "u1")

        self.assertTrue(stop_event.is_set())   # 엔진 관리 스레드가 정리로 내려감
        get_rec.assert_not_called()            # reconciler 등록 전에 거부
        hts.assert_not_called()                # 기동 정합 검사(DB 쓰기) 전에 거부
        self.assertEqual(trader.mock_calls, [])
        self.assertTrue(any("[PULLBACK-PARAMS]" in m for m in logs.output))

    def test_set_config_selectbox_has_no_pullback(self):
        tree = _parse("pages/set_config.py")
        found = False
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "selectbox"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and "Strategy Type" in str(node.args[0].value)
            ):
                found = True
                self.assertIsInstance(node.args[1], ast.Name)
                self.assertEqual(node.args[1].id, "STRATEGY_TYPES")
        self.assertTrue(found)


if __name__ == "__main__":
    unittest.main()
