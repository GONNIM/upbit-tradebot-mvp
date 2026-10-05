# WO-21 보조 (로컬, .env 없는 worktree 에서 실행): 같은 실데이터 A·C 재시작을 "구 코드 동작"으로 재현.
# 구 코드는 재계산 함수가 없으므로 재시작 복원(apply_entry) 직후 상태가 그대로 첫 매도 평가에 들어간다.
# 사용: python3 wo21_old_restart_sim.py <저장소 루트>
import sys
from datetime import datetime
sys.path.insert(0, sys.argv[1])
from core.position_state import PositionState

for name, avg, src, expect in (("A 10-02 09:20:11 (09:10 봉까지)", 734.0, "boot_seed", (True, 747.0, 3.9, 747.0)),
                               ("A 10-02 09:30:11 (09:20 봉까지)", 734.0, "boot_seed", (True, 747.0, 3.9, 747.0)),
                               ("C 10-03 19:00:11 (18:50 봉까지)", 710.0, "wallet_sync", (True, 722.0, 3.6, 722.0)),
                               ("C 10-03 20:05:11 (19:55 봉까지)", 710.0, "wallet_sync", (True, 734.0, 3.6, 722.0))):
    p = PositionState()
    p.apply_entry(qty=100.0, avg_price=avg, entry_bar=330, entry_ts=datetime.fromisoformat("2026-10-02T08:00:14+09:00"), source=src)
    got = (p.trailing_armed, p.highest_price, p.trailing_fixed_amount, p.trailing_activation_price)
    print(f"{name}: 재시작 직후 상태 {got} | 재시작 전 실제(스냅샷) {expect} | {'같음' if got == expect else '다름 → 무장 상태 소실'}")
