// Ver2 기준 파일에서 백테스터 스크립트를 만든다: 원문 인라인 스크립트 + 정해진 차이(fixtures/ver2_patches.json).
// parity 시험과 scripts/build_backtester_js.mjs 가 같은 함수를 쓴다.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
export const ROOT = path.resolve(here, "../../..");
export const PATCHES = JSON.parse(fs.readFileSync(path.join(here, "fixtures/ver2_patches.json"), "utf8"));
export const VER2_HTML_PATH = path.join(ROOT, PATCHES.source);

export function ver2Html() {
  return fs.readFileSync(VER2_HTML_PATH, "utf8");
}

// 원문 인라인 스크립트(줄 끝 \n 포함)
export function ver2Script() {
  const [from, to] = PATCHES.script_lines;
  return ver2Html().split("\n").slice(from - 1, to).join("\n") + "\n";
}

export function countOf(text, needle) {
  let n = 0;
  let i = text.indexOf(needle);
  while (i !== -1) { n++; i = text.indexOf(needle, i + needle.length); }
  return n;
}

// 원문 + 차이 2곳. find 가 정확히 1번 나오지 않으면 오류.
export function patchedScript() {
  let s = ver2Script();
  for (const p of PATCHES.patches) {
    const n = countOf(s, p.find);
    if (n !== 1) throw new Error(`ver2 patch find 가 ${n}번 나옴: ${p.why}`);
    s = s.replace(p.find, () => p.replace);
  }
  return s;
}
