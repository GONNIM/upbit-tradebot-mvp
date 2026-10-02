# WO-20 (6) 포지션 보유 중 재시작 재현 — 서버 DB 복사본(orders·account_positions 두 테이블, scratchpad) 사용.
# 사용: python3 wo20_restart_repro.py <저장소 루트(worktree)> <복사본 DB> <변형: as_is | exec_set>
#  - 복사본을 다시 복사해 작업용 DB 를 만들고, 09:30 매도(id 556)·14:15 매도(id 557)를 지워 "보유 중(08:00~09:30)" 상태를 만든다.
#  - as_is   : orders.executed_at 전부 NULL (지금 서버 데이터 그대로)
#  - exec_set: 주문 555 의 executed_at 을 Upbit 실제 체결 시각(08:00:12)으로 채움 (WO-20 이후 기록될 값)
#  - 가짜 지갑: JTO 318.01810267, Upbit avg_buy_price 734. 업비트·텔레그램 호출 없음 (더미 키, notifier 패치).
import logging
import shutil
import sqlite3
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

root, src_db, variant = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, root)
work = Path(src_db).with_name(f"work_{variant}_{Path(root).name}.db")
shutil.copy(src_db, work)
con = sqlite3.connect(work)
con.execute("DELETE FROM orders WHERE id IN (556, 557)")  # 09:30 매도·14:15 매도 제거 → 08:00~09:30 보유 상태
con.execute("UPDATE account_positions SET virtual_coin = 318.01810267 WHERE ticker = 'KRW-JTO'")
if variant == "exec_set":
    con.execute("UPDATE orders SET executed_at = '2026-10-02T08:00:12+09:00' WHERE id = 555")
con.commit()
con.close()

records = []


class _H(logging.Handler):
    def emit(self, r):
        records.append(f"{r.levelname} {r.name} | {r.getMessage()}")


logging.getLogger().addHandler(_H())
logging.getLogger().setLevel(logging.INFO)

with patch("services.db.get_db_path", return_value=str(work)), \
        patch("services.init_db.get_db_path", return_value=str(work)), \
        patch("services.notifier.send", MagicMock(return_value=True)):
    from core.position_state import PositionState
    from engine import live_loop
    trader = MagicMock()
    trader.user_id = "mcmax33"
    trader.test_mode = False
    trader._coin_balance.return_value = 318.01810267
    trader.upbit.get_balances.return_value = [{"currency": "JTO", "balance": "318.01810267", "avg_buy_price": "734"}]
    p = PositionState(trader=trader, ticker="KRW-JTO")
    p.sync_from_wallet()
    print(f"[1] sync_from_wallet → has_position={p.has_position} avg_price={p.avg_price} entry_ts={p.entry_ts}")
    r = live_loop._seed_entry_price_from_db("KRW-JTO", "mcmax33")
    print(f"[2] _seed_entry_price_from_db → {r}")
    if hasattr(live_loop, "_apply_boot_seed"):
        applied = live_loop._apply_boot_seed(p, r, 318.01810267)
        print(f"[3] _apply_boot_seed → applied={applied}")
    else:
        cond = bool(r) and r.get("price") is not None and r.get("entry_ts_iso") is not None
        print(f"[3] (옛 코드) live_loop.py:714 조건 = {cond} → "
              + ("apply_entry(source=boot_seed)" if cond else "ERROR 분기 'P3 boot seed 시각 복원 실패' (apply_entry 미호출)"))
    print(f"[4] 결과 → has_position={p.has_position} avg_price={p.avg_price} entry_bar={p.entry_bar} entry_ts={p.entry_ts}")

print("== 로그 판정")
print("   [POSITION-APPLY] source=boot_seed:", sum("[POSITION-APPLY] source=boot_seed" in m for m in records))
print("   [BOOT-SEED] WARNING:", sum("[BOOT-SEED]" in m and m.startswith("WARNING") for m in records))
print("   P3 boot seed 시각 복원 실패:", sum("P3 boot seed 시각 복원 실패" in m for m in records))
for m in records:
    if any(k in m for k in ("POSITION-APPLY", "BOOT-SEED", "Position recovered", "POS-SYNC] avg_price", "entry_ts 도 함께")):
        print("   ", m[:260])
