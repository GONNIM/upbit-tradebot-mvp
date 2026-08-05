"""
✅ 회귀: params 파일 규칙 불일치로 인한 100% 매수 결함 (2026-08-05)

원 결함:
- UI 저장: `save_params(..., strategy_type="EMA")` → `_scoped_path` 적용
    → `mcmax33_latest_params_EMA.json` 에 order_ratio 저장 (예: 0.1)
- 엔진 hot-reload: `engine_manager` 가 `Trader(params_file=base_path)` 로 전달
    → base 파일 `mcmax33_latest_params.json` 을 매수마다 재로드
    → base 파일에 남아있던 8개월 전 값 (order_ratio=1.0) 로 KRW 잔고 100% 매수

실사고 (2026-08-05 KRW-JTO):
    [BUY-LIMIT] plan close=730.0 rounded=730.0 krw_to_use=3,204,831 qty=4387.98545933
    → 사용자 UI 설정 10% 였으나 실 실행은 100% (약 320만원 전액 투입, uuid b099dcb0...)

봉쇄:
1) engine.params.scoped_params_path public helper 노출
2) engine_manager.py / engine_runner.py 에서 trader.params_file 에 scoped 적용
3) UI 저장 시 engine.params.sync_order_ratio_to_base 로 base 파일 order_ratio 동기화

실행:
    python3 -m unittest tests.regressions.test_r_2026_08_05_params_file_split -v
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from engine.params import scoped_params_path, sync_order_ratio_to_base  # noqa: E402
from core.trader import UpbitTrader  # noqa: E402


class TestScopedParamsPath(unittest.TestCase):
    """scoped_params_path: 전략 접미사 규칙 검증."""

    def test_ema_suffix(self):
        self.assertEqual(
            scoped_params_path("mcmax33_latest_params.json", "EMA"),
            "mcmax33_latest_params_EMA.json",
        )

    def test_macd_suffix(self):
        self.assertEqual(
            scoped_params_path("user_latest_params.json", "MACD"),
            "user_latest_params_MACD.json",
        )

    def test_none_strategy_returns_base(self):
        self.assertEqual(
            scoped_params_path("mcmax33_latest_params.json", None),
            "mcmax33_latest_params.json",
        )

    def test_lowercase_normalized(self):
        self.assertEqual(
            scoped_params_path("u_latest_params.json", "ema"),
            "u_latest_params_EMA.json",
        )


class TestSyncOrderRatioToBase(unittest.TestCase):
    """sync_order_ratio_to_base: base 파일 order_ratio 동기화 검증."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="base_sync_")
        self.base = str(Path(self.tmp) / "user_latest_params.json")

    def test_sync_updates_value(self):
        Path(self.base).write_text(
            json.dumps({"order_ratio": 1.0, "ticker": "X"}), encoding="utf-8"
        )
        changed = sync_order_ratio_to_base(self.base, 0.1)
        self.assertTrue(changed)
        with open(self.base) as f:
            self.assertAlmostEqual(json.load(f)["order_ratio"], 0.1)

    def test_no_change_when_equal(self):
        Path(self.base).write_text(
            json.dumps({"order_ratio": 0.1, "ticker": "X"}), encoding="utf-8"
        )
        changed = sync_order_ratio_to_base(self.base, 0.1)
        self.assertFalse(changed)

    def test_skip_when_missing(self):
        missing = str(Path(self.tmp) / "does_not_exist.json")
        self.assertFalse(sync_order_ratio_to_base(missing, 0.1))

    def test_skip_invalid_value(self):
        Path(self.base).write_text(
            json.dumps({"order_ratio": 0.1}), encoding="utf-8"
        )
        self.assertFalse(sync_order_ratio_to_base(self.base, 0.0))
        self.assertFalse(sync_order_ratio_to_base(self.base, 1.5))
        self.assertFalse(sync_order_ratio_to_base(self.base, -0.5))
        with open(self.base) as f:
            self.assertAlmostEqual(json.load(f)["order_ratio"], 0.1)

    def test_preserves_other_fields(self):
        Path(self.base).write_text(
            json.dumps({"order_ratio": 1.0, "ticker": "KRW-JTO", "take_profit": 0.007}),
            encoding="utf-8",
        )
        sync_order_ratio_to_base(self.base, 0.1)
        with open(self.base) as f:
            data = json.load(f)
        self.assertEqual(data["ticker"], "KRW-JTO")
        self.assertAlmostEqual(data["take_profit"], 0.007)


class TestTraderReadsScopedFile(unittest.TestCase):
    """Trader hot-reload 가 scoped 파일을 읽는지 e2e 검증 (사고 재현·봉쇄 확인)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="trader_split_")
        self.base = str(Path(self.tmp) / "u_latest_params.json")
        self.ema = str(Path(self.tmp) / "u_latest_params_EMA.json")

    def _make_trader(self, params_file: str, initial: float = 0.1) -> UpbitTrader:
        t = UpbitTrader.__new__(UpbitTrader)
        t.user_id = "u"
        t.risk_pct = initial
        t.test_mode = True
        t.strategy_type = "EMA"
        t.upbit = None
        t.last_buy_error = None
        t.last_sell_error = None
        t._strategy_ref = None
        t._params_file = params_file
        t._last_ratio_reload_ts = 0.0
        return t

    def test_trader_reads_ema_file_when_scoped_path_used(self):
        """수정된 engine_manager 처럼 scoped 경로를 trader 에 넘기면 EMA 파일값이 반영."""
        Path(self.base).write_text(json.dumps({"order_ratio": 1.0}), encoding="utf-8")
        Path(self.ema).write_text(json.dumps({"order_ratio": 0.1}), encoding="utf-8")
        scoped = scoped_params_path(self.base, "EMA")
        self.assertEqual(scoped, self.ema)
        t = self._make_trader(scoped, initial=0.1)
        self.assertAlmostEqual(t._current_risk_pct(), 0.1)

    def test_reproduces_bug_when_base_path_used(self):
        """버그 재현: trader 에 base 경로 넘기면 base 파일 값(1.0) 이 로드됨."""
        Path(self.base).write_text(json.dumps({"order_ratio": 1.0}), encoding="utf-8")
        Path(self.ema).write_text(json.dumps({"order_ratio": 0.1}), encoding="utf-8")
        t = self._make_trader(self.base, initial=0.1)
        self.assertAlmostEqual(t._current_risk_pct(), 1.0)

    def test_base_sync_makes_paths_agree(self):
        """UI 저장 후 base 동기화되면 trader 가 base 를 읽어도 최신값 획득."""
        Path(self.base).write_text(json.dumps({"order_ratio": 1.0}), encoding="utf-8")
        Path(self.ema).write_text(json.dumps({"order_ratio": 0.1}), encoding="utf-8")
        sync_order_ratio_to_base(self.base, 0.1)
        t = self._make_trader(self.base, initial=0.1)
        self.assertAlmostEqual(t._current_risk_pct(), 0.1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
