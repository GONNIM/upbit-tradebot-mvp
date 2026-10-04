#!/bin/bash
# 1분봉 전환 점검 A6 (서버, 읽기 전용): 비밀 파일 권한 · Streamlit 정적 제공 설정 · 최근 7일 외부 스캐너 요청
R=/root/upbit-tradebot-mvp
echo "== 파일 권한"
ls -l "$R/.env" "$R/.env.bak" "$R/.streamlit/secrets.toml" 2>&1
ls -ld "$R" "$R/.streamlit" 2>&1
echo "== Streamlit 설정 파일"
ls -l "$R/.streamlit/config.toml" /root/.streamlit/config.toml 2>&1
for f in "$R/.streamlit/config.toml" /root/.streamlit/config.toml; do
  [ -f "$f" ] && { echo "-- $f"; grep -nE "enableStaticServing|^\[server\]|address|port|headless|enableCORS|enableXsrfProtection|fileWatcherType" "$f"; }
done
echo "== 실행 중 Streamlit 설정 값 (설정 미지정 시 기본값)"
"$R/venv/bin/python" -c "
import streamlit, streamlit.config as c
print('streamlit', streamlit.__version__)
for k in ('server.enableStaticServing','server.address','server.port','server.enableCORS','server.enableXsrfProtection','server.headless'):
    print(k, '=', c.get_option(k))
" 2>&1 | grep -v Warning
echo "== 정적 폴더 존재 여부 (enableStaticServing 이 켜지면 이 폴더만 제공)"
ls -ld "$R/static" 2>&1
echo "== 최근 7일 외부 스캐너 요청 (journal)"
SINCE="$(date -d '7 days ago' '+%F %T')"
J=$(journalctl -u tradebot --since "$SINCE" --no-pager 2>/dev/null)
echo "   기간: $SINCE ~ $(date '+%F %T')"
echo "   MediaFileHandler: Missing file 줄: $(echo "$J" | grep -cF 'MediaFileHandler: Missing file')"
echo "   MediaFileStorageError(Bad filename) 줄: $(echo "$J" | grep -cF 'MediaFileStorageError')"
echo "   Traceback 줄: $(echo "$J" | grep -cF 'Traceback')"
echo "   요청 경로별 (Missing file):"
echo "$J" | grep -F 'MediaFileHandler: Missing file' | sed -E 's/.*Missing file //' | sort | uniq -c | sort -rn | head -20
echo "   날짜별:"
echo "$J" | grep -F 'MediaFileHandler: Missing file' | awk '{print $1, $2}' | sort | uniq -c
echo "   Missing file 이 아닌 Traceback 묶음(엔진 쪽 여부 확인용) 첫 줄 이후 마지막 예외 줄:"
echo "$J" | grep -A14 -F 'Traceback' | grep -E '^[A-Z][a-z]{2} [0-9]+ .*(Error|Exception):' | sed -E 's/^.*\]: //' | sort | uniq -c | head -10
