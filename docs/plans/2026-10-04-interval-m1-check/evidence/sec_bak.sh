#!/bin/bash
# 서버 비밀 파일 정리 2 (서버, 읽기 전용): ls -la 결과에서 .bak/.old/.orig/~ 로 끝나는 이름 목록.
# 와일드카드 미사용 — ls -la 출력을 awk 로 접미사 비교. 내용은 열지 않고, 비밀 후보만 grep -c 로 KEY/TOKEN 줄 수.
R=/root/upbit-tradebot-mvp
OUT=$(mktemp -p /dev/shm)
scan() {  # $1 = 디렉터리
  ls -la "$1" 2>/dev/null | awk -v d="$1" 'NR>1 && $9 != "." && $9 != ".." {
      n=$9; for (i=10;i<=NF;i++) n=n" "$i
      if (n ~ /\.bak$/ || n ~ /\.old$/ || n ~ /\.orig$/ || n ~ /~$/) print d "\t" n "\t" $1 "\t" $5 "\t" $6" "$7" "$8 }'
}
DIRS="/root $R"
for sub in $(ls -la "$R" | awk 'NR>1 && $1 ~ /^d/ && $9 != "." && $9 != ".." {print $9}'); do
  DIRS="$DIRS $R/$sub"
done
echo "== 훑은 디렉터리 ($(echo $DIRS | wc -w)개)"
echo "$DIRS" | tr ' ' '\n'
for d in $DIRS; do scan "$d"; done > "$OUT"
echo
echo "== 접미사 .bak/.old/.orig/~ 항목: $(wc -l < "$OUT")개"
printf "%s\t%s\t%s\t%s\t%s\n" "디렉터리" "이름" "권한" "크기" "수정 시각"
cat "$OUT"
echo
echo "== 비밀 값 가능성 후보 (이름에 env·secret·key·token·cred·pass 포함) — 내용 미열람, grep -c 만"
while IFS=$'\t' read -r d n perm size mt; do
  if echo "$n" | grep -qiE 'env|secret|key|token|cred|pass'; then
    f="$d/$n"
    if [ -f "$f" ]; then
      echo "$f | $perm | KEY 포함 줄: $(grep -c 'KEY' "$f") | TOKEN 포함 줄: $(grep -c 'TOKEN' "$f")"
    else
      echo "$f | $perm | 파일 아님(디렉터리 등) — 세지 않음"
    fi
  fi
done < "$OUT"
rm -f "$OUT"
