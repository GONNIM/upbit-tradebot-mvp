# 서버 비밀 파일 정리 1 (서버, 읽기 전용): .env 와 .env.bak 의 키 이름·값 비교. 값은 출력하지 않는다.
import os
R = "/root/upbit-tradebot-mvp"


def load(p):
    d, order, other = {}, [], 0
    for line in open(p, encoding="utf-8"):
        s = line.rstrip("\n")
        if not s.strip() or s.lstrip().startswith("#"):
            continue
        if "=" not in s:
            other += 1
            continue
        k, v = s.split("=", 1)
        k = k.strip()
        d[k] = v
        order.append(k)
    return d, order, other


a, ao, a_other = load(os.path.join(R, ".env"))
b, bo, b_other = load(os.path.join(R, ".env.bak"))
print(f".env 키 {len(ao)}개 (= 없는 줄 {a_other}) / .env.bak 키 {len(bo)}개 (= 없는 줄 {b_other})")
print(f"키 순서 같음: {ao == bo}")
print(f"{'키 이름':24s} {'.env':6s} {'.env.bak':9s} 값")
diff = []
for k in sorted(set(a) | set(b)):
    ina, inb = k in a, k in b
    if ina and inb:
        same = a[k] == b[k]
        if not same and a[k].strip().strip('"').strip("'") == b[k].strip().strip('"').strip("'"):
            res = "다름(따옴표·공백만 다름)"
        else:
            res = "같음" if same else "다름"
    else:
        res = "한쪽에만 있음"
    if res != "같음":
        diff.append(k)
    print(f"{k:24s} {'있음' if ina else '없음':6s} {'있음' if inb else '없음':9s} {res}")
print(f"\n다른 키: {diff if diff else '없음'}")
print("판정:", "모든 키 이름·값 같음 → 삭제 대상" if not diff else "다른 키 있음 → 삭제하지 않고 chmod 600 만")
