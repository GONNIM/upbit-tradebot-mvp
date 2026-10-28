// 2차 T10: 새 전략(PULLBACK) 기준값 고정 시험.
// - 「원본 스크립트 sha 같음」: 원본 HTML 143~938행이 cfgs.json 에 적은 sha256 과 같다(원본이 바뀌면 기준값도 다시 만들어야 함).
// - 「고정 파일과 같음」: 기준값 생성기(pullback_reference.mjs)를 지금 돌린 출력 == 커밋된 expected/*.json (3세트 × 9조합).
// - 사건 수: base 세 세트 모두 GOLDEN ≥ 1, PULLBACK ≥ 1, 매도 ≥ 1 (계획 T10 「각 경우 사건 수 확인」).
// node 없는 서버 게이트는 Python 쪽(tests/regressions/test_r_2026_10_28_p3_t10_parity.py)만 돈다.
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { PB_DIR, expectedPath, expectedText, loadCfgs, scriptSha256 } from "./pullback_reference.mjs";

const cfgs = loadCfgs();

test("원본 스크립트 sha 같음", () => {
  assert.match(cfgs.meta.original_script_sha256, /^[0-9a-f]{64}$/);
  assert.equal(scriptSha256(), cfgs.meta.original_script_sha256);
});

test("조합 9개·세트 3개", () => {
  assert.deepStrictEqual(Object.keys(cfgs.cfgs), [
    "base", "golden_no", "golden_only", "pb_lt_splits", "slope_drop",
    "deadcross_no", "compounding_yes", "sma", "splits_full_armed",
  ]);
  assert.deepStrictEqual(cfgs.meta.fixtures, ["upbit_a", "upbit_b", "upbit_c"]);
});

for (const f of cfgs.meta.fixtures) {
  test(`기준값 고정 파일과 같음 — ${f} 9조합`, async () => {
    const fx = JSON.parse(fs.readFileSync(path.join(PB_DIR, `${f}.json`), "utf8"));
    for (const c of Object.keys(cfgs.cfgs)) {
      const p = expectedPath(f, c);
      assert.ok(fs.existsSync(p), `고정 파일 없음: ${p}`);
      const now = await expectedText(f, c, cfgs, fx);
      assert.equal(now, fs.readFileSync(p, "utf8"), `${f}__${c}`);
      const body = JSON.parse(now);
      assert.equal(body.meta.bar_count, fx.bars.length);
      assert.ok(body.buys.length >= 1 && body.sells.length >= 1, `${f}__${c} 사건 0`);
    }
  });

  test(`사건 수 — ${f} base: GOLDEN·PULLBACK·매도 ≥ 1`, () => {
    const body = JSON.parse(fs.readFileSync(expectedPath(f, "base"), "utf8"));
    const n = (t) => body.buys.filter((b) => b.trigger === t).length;
    assert.ok(n("GOLDEN") >= 1, `${f} GOLDEN 0`);
    assert.ok(n("PULLBACK") >= 1, `${f} PULLBACK 0`);
    assert.ok(body.sells.length >= 1, `${f} 매도 0`);
  });
}
