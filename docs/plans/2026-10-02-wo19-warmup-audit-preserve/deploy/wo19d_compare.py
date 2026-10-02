# WO-19 배포 2(c): 기동 전후 스냅샷 대조 (로컬 실행, TSV 두 개 비교)
import sys
S = "/private/tmp/claude-501/-Users-gonnim-Project-MVP-Source-upbit-tradebot-mvp/9339ae21-5ead-4004-a49c-c5714e34e251/scratchpad"
BOOT = "2026-10-02T10:03:17"


def load(p):
    d = {}
    for line in open(p, encoding="utf-8"):
        f = line.rstrip("\n").split("\t")
        if len(f) >= 7:
            d[(f[0], f[2])] = f
    return d


b, a = load(f"{S}/wo19d_snap_before.tsv"), load(f"{S}/wo19d_snap_after.tsv")
cnt = {}
real_to_warmup, changed_real, new_rows = [], [], []
for k, fa in sorted(a.items()):
    fb = b.get(k)
    if fb is None:
        cls = "new_" + ("warmup" if fa[5] == "WARMUP" else "realtime")
        new_rows.append(fa)
    elif fb == fa:
        cls = "unchanged_" + ("warmup" if fa[5] == "WARMUP" else "real")
    elif fb[5] == "WARMUP" and fa[5] == "WARMUP":
        cls = "warmup_placeholder_updated"
    elif fb[5] != "WARMUP" and fa[5] == "WARMUP":
        cls = "REAL_TO_WARMUP"
        real_to_warmup.append((fb, fa))
    else:
        cls = "changed_other"
        changed_real.append((fb, fa))
    cnt[cls] = cnt.get(cls, 0) + 1
print("before rows", len(b), "/ after rows", len(a), "/ missing after", len(set(b) - set(a)))
for k in sorted(cnt):
    print(f"  {k}: {cnt[k]}")
ts_after_boot_warmup = sum(1 for f in a.values() if f[3] >= BOOT and f[5] == "WARMUP")
ts_after_boot_warmup_was_real = sum(1 for (fb, fa) in real_to_warmup if fa[3] >= BOOT)
print(f"기동 후 timestamp 갱신 행 중 status=WARMUP: {ts_after_boot_warmup} (그중 기동 전 실제 판정이던 행: {ts_after_boot_warmup_was_real})")
for fb, fa in real_to_warmup[:10]:
    print("  REAL_TO_WARMUP", fb, "->", fa)
for fb, fa in changed_real[:10]:
    print("  changed_other", fb, "->", fa)
print("새 행 bar_time:", ", ".join(f"{x[0][6:9]}:{x[2][5:16]}:{x[5]}" for x in new_rows))
for rid in ("75021", "75063"):
    for f in a.values():
        if f[1] == rid:
            print("기준 행 after:", f, "| 동일" if b.get((f[0], f[2])) == f else "| 변경됨")
