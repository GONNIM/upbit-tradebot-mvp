"""
✅ [Phase 2] F1 회귀: order_ratio hot-reload (커밋 7ff9b10, 2026-07-20)

원 결함: 사용자가 설정 페이지에서 order_ratio 를 변경 저장해도 엔진 재시작
전까지 UpbitTrader.risk_pct 는 초기값 유지 → "10% 저장했는데 100% 매수" 오해.

봉쇄 방식: UpbitTrader._current_risk_pct() 가 매수 시점마다 params JSON 을
새로 읽어 최신값 반영. 이상값 (<=0, >1.0) / 파일 없음 / JSON 손상 시 self.risk_pct fallback.

실행:
    python3 -m unittest tests.regressions.test_r_2026_07_20_order_ratio_stale -v
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.trader import UpbitTrader  # noqa: E402


class TestOrderRatioHotReload(unittest.TestCase):
    """F1: hot-reload 로 order_ratio 변경 즉시 반영. 이상값 fallback."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="ratio_test_")
        self.params_file = str(Path(self.tmpdir) / "user_params.json")

    def _write_params(self, order_ratio):
        """params JSON 파일 저장."""
        with open(self.params_file, "w") as f:
            json.dump({"order_ratio": order_ratio, "ticker": "TEST"}, f)

    def _make_trader(self, initial_ratio: float = 0.1):
        """
        UpbitTrader 를 TEST 모드로 생성.
        get_account / create_or_init_account 를 mock 하여 DB 초기화 우회.
        """
        with patch("core.trader.get_account", return_value=1000000), \
             patch("core.trader.create_or_init_account"):
            trader = UpbitTrader(
                user_id="test_user",
                risk_pct=initial_ratio,
                test_mode=True,
                params_file=self.params_file,
            )
        return trader

    def test_hot_reload_reads_latest_value(self):
        """params.json 변경 시 _current_risk_pct() 즉시 갱신."""
        self._write_params(0.1)  # 10%
        trader = self._make_trader(initial_ratio=0.1)
        self.assertEqual(trader._current_risk_pct(), 0.1)

        # 사용자가 1%로 변경 저장
        self._write_params(0.01)
        self.assertEqual(trader._current_risk_pct(), 0.01)
        # self.risk_pct 도 갱신됐는지
        self.assertEqual(trader.risk_pct, 0.01)

    def test_hot_reload_falls_back_on_missing_file(self):
        """params 파일 없으면 self.risk_pct 유지."""
        trader = self._make_trader(initial_ratio=0.1)
        # 파일 미생성 상태
        self.assertEqual(trader._current_risk_pct(), 0.1)

    def test_hot_reload_falls_back_on_invalid_value(self):
        """이상값 (<=0, >1.0) 은 self.risk_pct fallback."""
        trader = self._make_trader(initial_ratio=0.1)

        # 0 → fallback
        self._write_params(0)
        self.assertEqual(trader._current_risk_pct(), 0.1)

        # 1.5 (150%) → fallback
        self._write_params(1.5)
        self.assertEqual(trader._current_risk_pct(), 0.1)

        # 정상값 복구
        self._write_params(0.25)
        self.assertEqual(trader._current_risk_pct(), 0.25)

    def test_hot_reload_falls_back_on_corrupt_json(self):
        """JSON 손상 시 self.risk_pct fallback."""
        trader = self._make_trader(initial_ratio=0.1)
        with open(self.params_file, "w") as f:
            f.write("{corrupt json")
        self.assertEqual(trader._current_risk_pct(), 0.1)

    def test_hot_reload_falls_back_on_missing_field(self):
        """order_ratio 필드 없으면 self.risk_pct fallback."""
        trader = self._make_trader(initial_ratio=0.1)
        with open(self.params_file, "w") as f:
            json.dump({"ticker": "TEST"}, f)  # order_ratio 없음
        self.assertEqual(trader._current_risk_pct(), 0.1)


if __name__ == "__main__":
    unittest.main()
