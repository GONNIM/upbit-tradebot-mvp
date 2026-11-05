// v2/static/backtester.js 를 Ver2 기준 파일 + 정해진 차이 2곳으로 다시 만든다 (1105-09).
// 사용: node scripts/build_backtester_js.mjs
import fs from "node:fs";
import path from "node:path";
import { ROOT, patchedScript } from "../tests/v2/js/ver2_source.mjs";

const out = path.join(ROOT, "v2/static/backtester.js");
const s = patchedScript();
fs.writeFileSync(out, s);
console.log(`wrote ${out} (${Buffer.byteLength(s)} bytes, ${s.split("\n").length - 1} lines)`);
