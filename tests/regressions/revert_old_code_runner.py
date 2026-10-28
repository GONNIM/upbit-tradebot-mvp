"""
2차 T10 되돌리기 무해성 시험(test_r_2026_10_28_p3_t10_revert.py)이 별도 프로세스로 부르는 옛 코드 실행기.

사용: python3 revert_old_code_runner.py <old_dir> <db_dir> <user> <phase> <round> <out_json>
  old_dir : `git show <옛 커밋>:services/<파일>` 로 꺼낸 옛 services/ 가 있는 폴더(sys.path 맨 앞).
            services 는 이름공간 패키지라 옛 폴더에 없는 모듈(notifier 등)은 저장소 것을 쓴다.
  db_dir  : 시험용 DB 폴더(옛 init_db.DB_DIR 를 이리로 바꿈). 운영 DB 는 열지 않는다.
  phase   : init — 옛 initialize_db + ensure_all_schemas + ensure_schema(옛 스키마 DB 만들기)
            ops  — 옛 insert_order·insert_trade_audit·fetch_trades_for_snapshot·compute_pnl_for_snapshot 를 돌리고
                   결과·표 내용을 out_json 에 쓴다(예외는 목록으로 — 시험이 0 인지 본다).
  round   : 같은 DB 에 여러 번 돌릴 때 행 값을 구분하는 번호(1, 2 …).
시각은 고정 값으로 바꿔(now_kst) 두 DB 의 결과를 그대로 비교할 수 있게 한다.
"""
from __future__ import annotations

import json
import sys
import traceback

old_dir, db_dir, user, phase, rnd, out_json = sys.argv[1:7]
ROOT = __import__("pathlib").Path(__file__).resolve().parent.parent.parent
sys.path[:0] = [old_dir]
sys.path.append(str(ROOT))   # services 밖 모듈(옛 코드는 지연 import 로만 씀)


def _config_stub():
    """옛 services 가 config 에서 읽는 상수 3개만 config.py 글에서 꺼낸다(실행하지 않음 — secrets 를 읽지 않게).
    이 상수 3개가 옛 커밋 값과 같은지는 시험 test_old_services_same_as_before_phase2_schema 가 본다."""
    import ast
    import types
    want = {"DEFAULT_USER_ID", "PARAMS_JSON_FILENAME", "CONDITIONS_JSON_FILENAME"}
    mod = types.ModuleType("config")
    for node in ast.parse((ROOT / "config.py").read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and getattr(node.targets[0], "id", None) in want:
            setattr(mod, node.targets[0].id, ast.literal_eval(node.value))
    assert want <= set(vars(mod)), vars(mod)
    sys.modules["config"] = mod


_config_stub()
import services.init_db as idb  # noqa: E402

assert idb.__file__.startswith(old_dir), idb.__file__
idb.DB_DIR = db_dir
import services.db as sdb  # noqa: E402
import services.settings_history as sh  # noqa: E402

assert sdb.__file__.startswith(old_dir) and sh.__file__.startswith(old_dir)

R = int(rnd)
FIXED = f"2026-10-2{R}T10:00:00+09:00"
sdb.now_kst = lambda: FIXED
errors: list = []
out: dict = {"errors": errors, "modules": [idb.__file__, sdb.__file__, sh.__file__]}


def step(name, fn, *a, **k):
    try:
        return fn(*a, **k)
    except Exception as e:  # 옛 코드 오류를 모두 모은다
        errors.append({"step": name, "error": f"{type(e).__name__}: {e}", "tb": traceback.format_exc()[-800:]})
        return None


if phase == "init":
    step("initialize_db", idb.initialize_db, user)
    step("ensure_all_schemas", idb.ensure_all_schemas, user)
    step("ensure_schema", sdb.ensure_schema, user)
elif phase == "ops":
    # 설정 스냅샷 2개(앞 것은 끝 시각이 있어 구간이 고정) — 옛 이력 화면이 읽는 settings_history 행
    def _snap():
        with sdb.get_db(user) as conn:
            ids = []
            for saved in (f"2026-10-2{R}T09:00:00+09:00", f"2026-10-2{R}T11:00:00+09:00"):
                cur = conn.execute(
                    "INSERT INTO settings_history (user_id, saved_at, source_page, strategy_type, params_json) "
                    "VALUES (?, ?, 'set_config', 'EMA', ?)", (user, saved, json.dumps({"round": R})))
                ids.append(cur.lastrowid)
            return ids
    sids = step("settings_history", _snap) or [None, None]
    sid = sids[0]
    # 옛 trader 가 부르는 모양 그대로(전략 인자 없음)
    step("insert_order.buy_requested", sdb.insert_order, user, "KRW-JTO", "BUY", 700.0 + R, 10.0, "REQUESTED",
         provider_uuid=f"u-buy-{R}", state="REQUESTED", meta=json.dumps({"r": R}), settings_history_id=sid)
    step("insert_order.sell_filled", sdb.insert_order, user, "KRW-JTO", "SELL", 710.0 + R, 10.0, "FILLED",
         1000.0, 0.0, 95.0, provider_uuid=f"u-sell-{R}", state="FILLED", executed_at=FIXED,
         executed_volume=10.0, avg_price=710.0 + R, paid_fee=3.5, entry_bar=5, settings_history_id=sid)
    step("insert_order.plain", sdb.insert_order, user, "KRW-JTO", "BUY", 690.0, 1.0, "FAILED")
    common = dict(user_id=user, ticker="KRW-JTO", interval_sec=180, macd=0.0, signal=0.0, entry_bar=5,
                  tp=0.01, sl=0.015, highest=None, ts_pct=None, ts_armed=False, timestamp=FIXED)
    step("insert_trade_audit.buy", sdb.insert_trade_audit, bar=10, kind="BUY", reason="EMA_GC", price=700.0 + R,
         entry_price=700.0 + R, bars_held=0, bar_time=FIXED, settings_history_id=sid, **common)
    step("insert_trade_audit.sell", sdb.insert_trade_audit, bar=20, kind="SELL", reason="TP", price=710.0 + R,
         entry_price=700.0 + R, bars_held=10, bar_time=FIXED, settings_history_id=sid, **common)
    step("insert_trade_audit.reject", sdb.insert_trade_audit, bar=21, kind="SELL", reason="REJECT", price=705.0,
         entry_price=None, bars_held=None, qty=10.0, note="거절", meta=json.dumps({"code": "x"}), **common)
    step("insert_trade_audit.unlabeled", sdb.insert_trade_audit, bar=22, kind="BUY", reason="EMA_GC", price=701.0,
         entry_price=701.0, bars_held=0, **common)
    res = {}
    for i, s in enumerate(sids):
        if s is None:
            continue
        res[f"trades_{i}"] = step(f"fetch_trades_for_snapshot.{i}", sh.fetch_trades_for_snapshot, user, s)
        pnl = step(f"compute_pnl_for_snapshot.{i}", sh.compute_pnl_for_snapshot, user, s)
        if isinstance(pnl, dict) and i == len(sids) - 1:
            pnl = {k: v for k, v in pnl.items() if k != "interval_label"}   # 활성 구간 길이는 지금 시각 기준
        res[f"pnl_{i}"] = pnl
    out["results"] = res
    out["sids"] = sids

    def _dump():
        tables = {}
        with sdb.get_db(user) as conn:
            for t in ("orders", "audit_trades", "settings_history"):
                cols = [r[1] for r in conn.execute(f"PRAGMA table_info({t})")]
                keep = [c for c in cols if c != "strategy_type"]    # 2차가 더한 칸만 빼고 비교
                rows = conn.execute(f"SELECT {', '.join(keep)} FROM {t} ORDER BY id").fetchall()
                tables[t] = {"cols": keep, "rows": rows,
                             "strategy_type": ([r[0] for r in conn.execute(f"SELECT strategy_type FROM {t} ORDER BY id")]
                                               if "strategy_type" in cols and t != "settings_history" else None)}
        return tables
    out["tables"] = step("dump", _dump)
else:
    errors.append({"step": "phase", "error": f"알 수 없는 phase {phase}"})

with open(out_json, "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, default=str)
