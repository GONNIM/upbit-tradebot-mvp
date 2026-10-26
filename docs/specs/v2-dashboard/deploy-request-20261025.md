# 신버전 대시보드 1차 공개(P1·P2) 배포 승인 요청서 (2026-10-25, 배포 대상 12ddb4f — 종목 접두 결함 수정 포함)

**한 줄:** 서버를 `156b351`(v1.2026.10.20.1711)에서 `12ddb4f`(v1.2026.10.25.1611)로 올립니다. 신버전 서비스 `tradebot-v2` 를 설치·기동하고 `/v2/` 를 엽니다. 엔진(`tradebot`)은 **1회 재시작**합니다(입장 버튼 반영, spec E1).
**배포 대상 HEAD:** `12ddb4f`로 고정합니다. 이 요청서는 배포가 끝날 때까지 커밋하지 않고, 배포 완료 보고와 함께 버전을 갱신해 커밋합니다(verifier 결정 1 a).
**근거:**
- 구현 완료 보고 `docs/specs/v2-dashboard/impl-report-20261025.md`(5d4be71 기준, tests/v2 187 OK).
- 12ddb4f 기준 게이트(커밋 직전 재실행, 커밋 메시지에 기록): exit 0, tests/v2 190 OK, v2 JS 시험 통과, 회귀 350/350.
- plan 배포 절, `docs/operations/v2-runbook.md`.

**실행:**
- 사용자 승인 뒤 PO(Claude)가 SSH 로 실행합니다. tradebot 재시작이 들어 있으므로 저장소 폴더에서 새 세션으로 하기를 권합니다.
- `deploy-tradebot`(서버 `/root/deploy.sh`)은 쓰지 않습니다. 이 스크립트는 `git pull` 직후 조건 없이 재시작해서 E1 재시작 조건(확정 봉 직후·미체결 0·경계 60초 전)을 지킬 수 없습니다. 그래서 수동으로 실행합니다.

**배포 전 결함 수정 (12ddb4f):**
- 요청서를 검증하던 중 서버 읽기 전용 확인에서 결함을 찾았습니다. 서버 params 의 종목이 `JTO`(KRW- 접두 없음)로 저장돼 있었습니다.
- 수정 전 v2 는 이 원값을 그대로 써서 다음이 깨졌을 것입니다.
  - 홈 조회가 비어 「판단 불가」로 보임
  - 차트가 market=JTO 로 요청해 실패
  - 저장이 409 로 거절
- 12ddb4f 에서 엔진과 같은 규칙으로 `KRW-JTO` 로 바꾸도록 고쳤습니다(`v2/db.py` normalize_ticker).
- verifier 승인을 받았습니다(엔진 규칙과 30,026 입력 비교 차이 0). 사용자 승인으로 커밋·push 했습니다(1025-08·09).
- 운영자 확인(2-9)에서 다음을 직접 봅니다.
  - 홈 종목이 `KRW-JTO` 인지
  - 엔진 동작이 「판단 불가」가 아닌지
  - 차트가 그려지는지

## 1. 승인받을 항목
| # | 항목 | 서버에서 바뀌는 것 | 되돌리기 |
|---|---|---|---|
| D1 | `git pull --ff-only` (156b351 → 12ddb4f) | 저장소 파일 138개(엔진 코드 0, app.py +3, 동결 2 신규, 버전 줄) | 2-10 |
| D2 | 선행 파일 2개 | `.v2_secret`(32바이트 난수, 600), 0바이트 `mcmax33_latest_params_PULLBACK.json`(600) | v2 정지 뒤 삭제 |
| D3 | `tradebot` 1회 재시작(E1) | 엔진 프로세스 재기동(새 app.py 반영 — 허용 목록이 아직 없어 버튼은 안 보임) | 같은 조건으로 다시 재시작 |
| D4 | `tradebot-v2` 유닛 설치·enable·start | `/etc/systemd/system/tradebot-v2.service`, 127.0.0.1:8502 | `disable --now` → 유닛 삭제 → `daemon-reload` |
| D5 | 점검 실행 | 임시 유닛(끝나면 사라짐), `services/data/.v2probe_*` 생성 즉시 삭제. 실매매 DB ro 연결이 `-wal`·`-shm` 을 만들 수 있음(본 DB 와 같은 권한, 엔진이 정리) | 없음 |
| D6 | nginx `location /v2/` 추가 | `/etc/nginx/sites-available/tradebot`(sites-enabled 의 링크 대상) 443 블록 | 백업으로 제자리 복원 → `nginx -t` → reload |
| D7 | `.v2_allowlist`(`mcmax33`, 600) 생성 — **nginx 확인 뒤** | 투자자 화면에 입장 버튼이 나타남(재시작 불필요 — 호출마다 읽음) | `: > .v2_allowlist`(즉시 숨김) |
| D8 | root crontab 한 줄 | 매주 일 11:30 v2hist 백업 | 백업한 crontab 으로 되돌림 |
| D9 | 투자자 통보 문안 A 발송 | (운영자가 직접 — 외부 발송) | 불가 |

## 2. 실행 순서와 멈춤 조건

**경로 규칙:** SSH 호출마다 새 셸이 열리고 시작 위치는 `/root` 이다. 그래서 아래의 모든 서버 명령은 `cd /root/upbit-tradebot-mvp && ` 를 앞에 붙여 한 호출로 실행한다(블록 안 명령도 같다). 허용 목록·비밀 파일처럼 틀리면 위험한 경로는 절대 경로로 적었다.

### 2-0. 착수 전 정지선 (읽기 전용)
- 로컬 HEAD = `origin/main` = 배포 대상 HEAD. 미추적은 기존 13개, 이 요청서, 질의서(`docs/fable/2026-10-25-deploy-request-*.md`)뿐이어야 한다. 추적 파일 변경은 `M docs/specs/v2-dashboard/HANDOFF.md`(7판 보완 — 배포 승인 기록) 1건만 정상이다.
- 서버 봉 간격: `grep -n '"interval"' /root/upbit-tradebot-mvp/mcmax33_latest_params_EMA.json` 이 `minute3` 이어야 하고, `journalctl -u tradebot --since "2026-10-20 17:40" --no-pager | grep -m1 '\[CLOCK\] Initialized'` 가 `timeframe=minute3` 이어야 한다(10-25 PO 확인: 둘 다 minute3). 다르면 멈추고 D3 시각 규칙을 다시 정한다.
- 서버 종목 표기: 같은 파일의 `"ticker"` 는 `JTO`(접두 없음, 10-25 확인)이고, 엔진은 이를 `KRW-JTO` 로 바꿔 쓴다. 배포 대상 코드는 v2 도 같은 변환을 해야 한다(아래 「배포 전 결함 수정」).
- nginx 사전 확인: `grep -c 'listen 443' /etc/nginx/sites-available/tradebot` → 1 이상, `grep -c '^    location / {$' /etc/nginx/sites-available/tradebot` → 1(10-25 확인: 1·1). `grep -n 'listen 443' …` 원문 줄이 주석이 아닌 지시문(`listen 443 ssl;`) 하나뿐인지 본다. `ss -ltn | grep -c ':8502 '` → 0, `services/data/backups` 폴더 있음(10-25 확인).
- 서버 상태:
  - HEAD `156b351`, `dashboard.py:495` v1.2026.10.20.1711
  - `tradebot` active, ExecMainStartTimestamp `Tue 2026-10-20 17:40:51 KST`
  - `tradebot-v2` 없음, `.v2_*`·PULLBACK 파일 없음
  - 미추적 5건 그대로(check_* 3, sync_balances.py, mcmax33.sqlite3)
- `git diff --name-only 156b351 12ddb4f` 의 경로가 허용 목록 안이어야 한다.
  - 허용 목록: `v2/`·`deploy/`·`scripts/v2/`·`ui/v2_entry.py`·`utils/v2_entry_token.py`·`app.py`·`pages/dashboard.py`·`scripts/regression_gate.sh`·`tests/`·`docs/`·`.gitignore`·`.claude/`·`CLAUDE.md`. 이 가운데 `scripts/v2/` 는 이 요청서에서 plan 목록에 더한 것이다.
  - `core/`·`engine/`·`services/`·`config.py` 는 0이어야 한다.
- 감사 로그 백업 최신 1개가 있어야 한다(10-25 11:00 `tradebot_mcmax33.db.backup_20261025_110001` 확인됨).
- 기준선을 기록한다(비교용):
  - `curl -s -o /dev/null -w '%{http_code}\n' https://orionhunter7.cafe24.com/`
  - 최근 24시간 `journalctl -u tradebot` 의 `database is locked`·Traceback·ERROR·CRITICAL 수
- **하나라도 다르면 멈추고 보고한다.**

### 2-1. D1 git pull
- `cd /root/upbit-tradebot-mvp && git pull --ff-only` 를 실행한다.
  - 확인: HEAD `12ddb4f`, `grep -n v1.2026 pages/dashboard.py` → v1.2026.10.25.1611.
  - 충돌하면 멈춘다.
- pull 뒤 D3 까지 구버전은 옛 코드로 돈다. Streamlit 바이트코드 캐시는 파일 감시가 꺼져(fileWatcherType none) 비워지지 않기 때문이다(verifier 확인). 새 import 는 재시작 뒤에만 일어난다.
- pull 로 `.gitignore` 가 12ddb4f 판이 되어야 D2 파일이 무시된다. 그래서 D1 을 반드시 D2 보다 먼저 한다.

### 2-2. D2 선행 파일 (값 출력 금지, umask 는 서브셸 안에서만)
```
cd /root/upbit-tradebot-mvp
( umask 077; venv/bin/python -c "import secrets; open('.v2_secret','wb').write(secrets.token_bytes(32))" )
ls -l .v2_secret; wc -c .v2_secret          # -rw------- root, 32
( umask 077; : > mcmax33_latest_params_PULLBACK.json ); ls -l mcmax33_latest_params_PULLBACK.json   # 0바이트 600
git status --short                          # 두 파일이 보이지 않아야 함(.gitignore)
```
- 사본(.bak 등)은 만들지 않는다. `.v2_allowlist` 는 D7 에서 만든다.

### 2-3. D3 tradebot 1회 재시작 (E1) — 조건을 모두 만족할 때만
1. `journalctl -u tradebot --since "-3 min" --no-pager | grep -E "✅ \[CONFIRMED\] 봉 처리 완료|\[CONFIRMED-NO-TRADE\]"` 로 현재 봉 확정 처리를 확인한다. 2-0 에서 확인한 간격(minute3) 기준이며, 경계 약 11초 뒤에 찍힌다.
2. 미체결 주문 확인: `sqlite3 -readonly services/data/tradebot_mcmax33.db "SELECT COUNT(*) FROM orders WHERE state IN ('REQUESTED','PARTIALLY_FILLED');"` → 0. 출력이 숫자 한 줄이 아니면(오류 문구 — 예: 열 이름이 다름) 0 으로 읽지 않고 멈춘다. ro 연결이 `-wal`·`-shm` 을 만들 수 있다(엔진이 정리).
3. 다음 봉 경계까지 60초 이상 남았을 때 `systemctl restart tradebot` → `systemctl is-active tradebot` active.
4. 재시작 뒤 5분 안에 다음을 확인한다.
   - `[BOOT-RESUME] success`(`engine/boot_resume.py:170`)
   - `[BOOT] run_live_loop start` 1회(`engine/live_loop.py:753`)
   - 다음 확정 봉의 `✅ [CONFIRMED] 봉 처리 완료` 가 정상 시각에 찍힘
   - WO-12 결함 태그 0(`docs/plans/2026-09-30-wo12-boot-auto-resume/plan.md:285`)
   - ERROR·Traceback·CRITICAL·`database is locked` 0
   - `systemctl show tradebot -p ExecMainStartTimestamp` 값을 기록한다.
- **결함 태그가 있거나 BOOT-RESUME 이 실패하면 멈추고 보고한다**(2-10).

### 2-4. D4 유닛 설치·기동
```
cp deploy/tradebot-v2.service /etc/systemd/system/tradebot-v2.service
systemctl daemon-reload
systemctl enable tradebot-v2          # --now 없이
systemctl start tradebot-v2
systemctl is-active tradebot-v2       # active
journalctl -u tradebot-v2 -n 20 --no-pager
```
- 기동이 실패하면 journal 을 확인한 뒤 멈춘다(엔진 영향 없음).

### 2-5. D5 점검
- 선행 조건: D3 재시작 뒤 5분 확인(2-3 4항)이 모두 끝난 다음에만 시작한다(메모리 시험이 BOOT-RESUME 관찰과 겹치지 않게).
- `bash scripts/v2/check_v2_unit.sh mcmax33` → FAIL 이 0 이어야 한다. RESIDUAL 은 기록한다. 첫 실행에서 `probe-run-failed` 가 나오면 `-` 접두 처리부터 본다.
- A17 대응:
  - 「EMA·MACD 설정 파일 쓰기 실패」는 `root-readonly`(ProtectSystem=strict + ProtectHome=read-only 아래 저장소 루트에 새 파일 생성 실패)로 갈음한다. (배포 중 정정 10/25: 첫 실행에서 strict 만으로는 /root 가 쓰기 가능해 FAIL root-writable → 5692998 에서 ProtectHome=read-only 추가, 사용자 결정 1025-11·12.)
  - 「v2hist·-journal 600」은 운영자가 처음 저장한 뒤(2-9) `ls -l services/data/v2hist_mcmax33.db*` 로 확인한다.
- `bash scripts/v2/a3_memory_probe.sh` → `probe-oom-killed`·`swap-unchanged`·`tradebot-not-restarted` 가 PASS 여야 한다. FAIL 이면 1회 다시 실행하고, 두 번 다 FAIL 이면 멈춘다.
- RSS(A12): `ps -o rss= -p $(systemctl show -p MainPID --value tradebot-v2)` 가 102400(KB) 이하여야 한다. 대기 상태에서 1회, 운영자 사용 뒤 1회 잰다.
- A2: `systemctl restart tradebot-v2` 뒤 tradebot ExecMainStartTimestamp 가 D3 기록값과 같아야 한다.
- EXPLAIN QUERY PLAN 8개(결정 3):
  - 저장소 밖 로컬 파일 `explain8.sql`(아래 원문)을 `ssh … "sqlite3 -readonly /root/upbit-tradebot-mvp/services/data/tradebot_mcmax33.db" < explain8.sql` 로 넘긴다. 서버에 파일을 만들지 않는다.
  - 판정: 출력에 `USE TEMP B-TREE` 가 0이어야 한다.
  - `?` 자리에는 `<T>` = `KRW-JTO`(서버 params 원값 `JTO` 에 normalize_ticker 를 적용한 값 — DB 행 표기와 같음), 고정 `mcmax33`, 숫자 20·0 을 넣는다.
```
EXPLAIN QUERY PLAN SELECT timestamp, price FROM audit_buy_eval WHERE ticker='<T>' ORDER BY timestamp DESC, id DESC LIMIT 1;
EXPLAIN QUERY PLAN SELECT timestamp, price, tp_price, sl_price FROM audit_sell_eval WHERE ticker='<T>' ORDER BY timestamp DESC, id DESC LIMIT 1;
EXPLAIN QUERY PLAN SELECT timestamp FROM audit_trades WHERE ticker='<T>' AND type='BUY' ORDER BY timestamp DESC, id DESC LIMIT 1;
EXPLAIN QUERY PLAN SELECT id, timestamp, bar_time, ticker, type, reason, price, qty, entry_price, note FROM audit_trades WHERE ticker='<T>' ORDER BY timestamp DESC, id DESC LIMIT 20;
EXPLAIN QUERY PLAN SELECT id, timestamp, bar_time, ticker, price, macd, signal, have_position, overall_ok, failed_keys FROM audit_buy_eval WHERE ticker='<T>' ORDER BY timestamp DESC, id DESC LIMIT 20;
EXPLAIN QUERY PLAN SELECT id, timestamp, level, message FROM logs WHERE user_id='mcmax33' ORDER BY timestamp DESC, id DESC LIMIT 50 OFFSET 0;
EXPLAIN QUERY PLAN SELECT type, price, bar_time FROM audit_trades WHERE ticker='<T>' ORDER BY timestamp DESC, id DESC LIMIT 200;
EXPLAIN QUERY PLAN SELECT id, timestamp, bar_time, ticker, price, macd, signal, triggered, trigger_key FROM audit_sell_eval WHERE ticker='<T>' ORDER BY timestamp DESC, id DESC LIMIT 20;
```
  (SQL 원문은 `v2/api_read.py:25-53` 과 같다. 바꾼 것은 자리표뿐이다. 8번째 줄 SIGNALS_SELL_TICKER 도 실행 경로(`:271`)에서 쓰므로 더했다. `*_ALL` 은 id 순 조회라 뺐다.) `USE TEMP B-TREE` 가 나오면 기록하고 사용자에게 알린다. v2 응답 속도 문제일 뿐이며 엔진 영향은 없다.

### 2-6. D6 nginx (심볼릭 링크 유지)
1. `readlink -f /etc/nginx/sites-enabled/tradebot` → `/etc/nginx/sites-available/tradebot` 인지 확인한다.
2. 백업은 sites-enabled 밖에 둔다: `cp /etc/nginx/sites-available/tradebot /root/nginx-tradebot.bak-20261025`
3. 편집: 저장소 밖 로컬 스크립트(파일 도구로 작성, **실행 전 원문을 보여 드림**)를 `ssh … "python3 -I -" < nginx_add_v2.py` 로 1회 실행한다. 서버에 파일은 남지 않는다. 스크립트가 하는 일은 다음과 같다.
   - `sites-available/tradebot` 를 읽는다.
   - `/v2/` 가 이미 있으면 바꾸지 않고 끝낸다.
   - `listen 443` 이 있는 server 블록에서 첫 `    location / {` 앞에 `deploy/nginx-v2-location.conf` 의 블록을 넣는다.
   - 같은 경로에 `open(...,'w')` 로 제자리 쓰기한다(링크·inode 유지).
4. `readlink` 결과가 그대로인지, `diff /root/nginx-tradebot.bak-20261025 /etc/nginx/sites-available/tradebot` 에 추가 6줄만 있는지 확인한다.
5. `nginx -t` 를 통과하면 `systemctl reload nginx` 한다. 실패하면 `cat /root/nginx-tradebot.bak-20261025 > /etc/nginx/sites-available/tradebot`(제자리) → `nginx -t` 로 되돌리고 멈춘다.
6. 확인(GET 기준 — HEAD 요청은 v2 가 405 를 낸다):
   - `curl -s -o /dev/null -w '%{http_code}\n' https://orionhunter7.cafe24.com/v2/` → **401**(세션 없음 안내)
   - `https://orionhunter7.cafe24.com/` → 2-0 기준선과 같은 코드

### 2-7. D7 허용 목록 (이 순간부터 투자자에게 버튼이 보임)
```
( umask 077; printf 'mcmax33\n' > /root/upbit-tradebot-mvp/.v2_allowlist ); ls -l /root/upbit-tradebot-mvp/.v2_allowlist     # 600 root
cd /root/upbit-tradebot-mvp && git status --short                           # 보이지 않아야 함
ls /root/.v2_allowlist 2>&1                                                 # No such file (잘못된 위치에 안 생겼는지)
```

### 2-8. D8 cron (비대화형, heredoc 없음)
```
crontab -l > /root/crontab.before-20261025
cp /root/crontab.before-20261025 /root/crontab.new-20261025
grep -v '^#' deploy/v2hist-backup.cron | grep -v '^$' >> /root/crontab.new-20261025
crontab /root/crontab.new-20261025
crontab -l | diff /root/crontab.before-20261025 -     # 추가 1줄만
rm /root/crontab.new-20261025                         # before 는 되돌리기용으로 남김(비밀 값 없음)
```

### 2-9. 3점 일치·관찰·운영자 확인
- 3점 일치: 로컬·서버 HEAD `12ddb4f`·버전 v1.2026.10.25.1611, tradebot ExecMainStartTimestamp(D3 값), tradebot-v2 active.
- 30분 무접속 관찰(`journalctl -u tradebot`):
  - Bar# 증가, 429·418 0, 놓친 확정 봉 0(NO-TRADE 제외), 결함 태그 0
  - `journalctl -u tradebot-v2` 의 ERROR 0
- 운영자 1회 접속(휴대폰):
  - 로그인 → 「📱 신버전 대시보드 (베타)」 → 「신버전 열기」 → 신버전 입장(A4 원형)
  - 실기기 412px(A5), 「구버전으로」 안내
  - 홈 표시: 종목 `KRW-JTO`, 봉 minute3, 엔진 동작 「정상」 또는 「지연」(「판단 불가」면 멈춤), 자산·포지션 값, 차트가 그려짐(업비트 시세 직접 호출)
  - 백테스터 열기(Binance 실호출 1회)
  - 「저장만 하기」 1회(엔진 영향 없음 — 엔진은 활성 전략 EMA 의 파일만 읽음). 저장 뒤 `ls -l services/data/v2hist_mcmax33.db*` 600 을 확인한다(A17).
  - 사용 뒤 RSS 를 다시 잰다.
- A15 관찰 기간은 결정 3 을 따른다. 출처는 `journalctl -u tradebot` 이다.
- 배포 완료 보고: 이 요청서 + 결과로 `deploy-report` 를 쓰고, Fable 번들 zip 을 만든 뒤, 버전을 갱신해 커밋 승인을 요청한다.

### 2-10. 되돌리기 (가벼운 순서)
1. **버튼만 즉시 숨기기**: `: > /root/upbit-tradebot-mvp/.v2_allowlist` → `wc -c /root/upbit-tradebot-mvp/.v2_allowlist` 가 0 인지 확인한다. 재시작은 필요 없다. 신버전 API 도 이때부터 403 이다.
2. **신버전 닫기**(runbook 「즉시 닫기」):
   - `systemctl disable --now tradebot-v2`
   - nginx: 백업을 제자리로 덮어쓴다(`cat 백업 > sites-available/tradebot`, 링크 유지) → `nginx -t` → reload
   - cron: `crontab /root/crontab.before-20261025`
   - 유닛 파일 삭제 → `systemctl daemon-reload`
   - v2 가 멈춘 뒤 `.v2_secret`·`.v2_allowlist`·PULLBACK 파일을 지운다(v2hist 는 남김 — 이력).
   - 엔진 영향은 없다.
3. **전체 되돌리기**: 위 + 로컬에서 `git revert`(입장 버튼 제거) 커밋. 이 커밋도 버전을 갱신해야 하며 사용자 승인이 필요하다. → push → 서버 pull → tradebot 재시작(D3 와 같은 조건·점검). 실매매 DB 는 바뀌지 않았으므로 데이터 복구는 없다.

## 3. 투자자 통보 문안 A (초안 — 발송은 운영자, D9)
> 신버전 대시보드(베타)를 열었습니다. 로그인 뒤 첫 화면의 「📱 신버전 대시보드 (베타)」를 누르고, 이어 나오는 「신버전 열기」를 60초 안에 누르면 다시 로그인하지 않고 휴대폰용 화면으로 들어갑니다. 신버전에서는 홈·차트·로그와 백테스터를 볼 수 있습니다. 매매 규칙과 엔진 동작은 바뀌지 않았습니다. 백테스터의 업비트 데이터는 준비 중이며 2차 공개 전에 엽니다. 그때까지는 바이낸스 데이터로 시험하고 저장만 할 수 있습니다. 「구버전으로」를 누르면 구버전에 다시 로그인해야 합니다.
- 필수 문장(spec 211행)을 그대로 넣었다. 보낸 뒤 `docs/operations/investor-notice-log.md` 에 #6 으로 기록한다.

## 4. 영향과 위험
| 축 | 영향 | 막는 것 |
|---|---|---|
| 매매 | 재시작 1회(D3) 동안 봉 처리가 멈춤(수 초~수십 초) | 재시작 조건(확정 봉 직후·미체결 0·경계 60초 전, 3분봉 여유 약 169초), BOOT-RESUME·누락 봉 확인 |
| 업비트 한도 | v2 서버 호출 0. 차트·백테스터는 사용자 휴대폰에서 직접 호출 | spec D8 import 검사, A15 관찰. 시세 한도는 IP 단위, 거래 한도는 포켓 단위(업비트 공식 문서) |
| 메모리 | v2 상한 150M, 스왑 금지, OOM 때 v2 먼저 종료 | a3 실측(cgroup v2 확인됨) |
| 자격증명 | v2 는 .env·secrets·credentials 를 못 열고(InaccessiblePaths), 환경변수가 없음 | check 스크립트. 남는 위험: /proc environ(RESIDUAL 여부 실측), /etc/shadow 읽기 가능(알려진 틈) |
| 데이터 | 실매매 DB 는 코드에서 읽기 전용(`mode=ro`)으로 연다. 파일 시스템 수준에서는 `services/data` 가 ReadWritePaths 라 쓰기가 막혀 있지 않다(spec E18 남는 위험 2). 쓰기는 v2hist·PULLBACK 파일뿐 | 시험·check·EXPLAIN |
| 투자자 화면 | 버튼은 D7 이후에만 보임(nginx 확인 뒤) | D7 순서 |
| 알려진 틈 | nginx access.log 에 `/v2/?t=` 토큰이 남음. 60초·1회용이지만 v2 재시작으로 nonce 저장소가 비면 60초 안 재사용 가능. 8501 이 외부에 열려 있고 ufw 비활성(기존 상태) | 다음 판에서 access_log 마스킹 검토(백로그) |

## 5. 사용자 결정 (1025-10, 2026-10-25 16시대 — 확정)
- 원문: 「1025-10 1 가, 2 가, 3 가, 4 가, 5 가」
- 1 가: D1~D8 한 번에 승인 — 멈춤 조건이 없으면 끝까지 진행(nginx 편집 스크립트 원문은 실행 전에 보임).
- 2 가: 저장소 폴더 새 세션에서 실행.
- 3 가: tradebot 재시작 조건을 만족하는 가장 가까운 시각.
- 4 가: 30분 무접속 + 운영자 1회 접속 뒤 24시간 journal 확인.
- 5 가: 통보 문안 A 초안대로, 배포 완료 확인 뒤 당일 운영자 발송.

### 결정 항목 (요청 당시)
1. D1~D8 실행 승인(한 번에 / 단계별).
2. 실행 시각: tradebot 재시작 조건을 만족하는 가장 가까운 시각(권고) / 지정 시각.
3. A15 관찰 기간: 30분 무접속 + 운영자 1회 접속 뒤 24시간 journal 확인(권고) / 다른 기간.
4. D9 투자자 통보 문안 A 확정·발송 시점(배포 완료 확인 뒤 당일 운영자 발송 권고 — spec 211행 「배포하는 날」).
5. 실행 세션: 저장소 폴더 새 세션(권고 — tradebot 재시작 포함) / 이 세션.
- PO 가 정한 것(verifier 결정 1·2·3): 요청서는 배포 보고와 함께 커밋 / `.v2_allowlist` 는 nginx 확인 뒤(D7) / EXPLAIN 8개는 서버에서 `sqlite3 -readonly` 로 실행(파일 생성 없음).

## 부록 A. nginx 편집 스크립트 원문 (D6 — 새 세션은 이 원문을 scratchpad 의 `nginx_add_v2.py` 로 Write 도구로 옮겨 쓴다)
- 10/25 로컬 표본(443 블록 + 80 블록)으로 2회 실행해 확인했다: 1회째 `OK inserted lines=6`, 2회째 `SKIP already-has-v2`.
- 실행: `ssh root@orionhunter7.cafe24.com "python3 -I -" < nginx_add_v2.py`(서버에 파일 남지 않음). 실행 전 원문을 사용자에게 보이고 verifier 검증을 받는다.
```python
"""서버에서 stdin 으로 1회 실행: ssh root@... "python3 -I -" < nginx_add_v2.py
/etc/nginx/sites-available/tradebot 의 443 server 블록 첫 `    location / {` 앞에 /v2/ 블록을 넣는다.
제자리 쓰기(open 'w')로 심볼릭 링크·inode 를 유지한다. 이미 /v2/ 가 있으면 아무것도 바꾸지 않는다.
"""
import sys

PATH = "/etc/nginx/sites-available/tradebot"
BLOCK = (
    "    location /v2/ {\n"
    "        proxy_pass http://127.0.0.1:8502;\n"
    "        proxy_set_header Host $host;\n"
    "        proxy_set_header X-Forwarded-Proto $scheme;\n"
    "        client_max_body_size 64k;\n"
    "    }\n"
)
ANCHOR = "    location / {\n"

with open(PATH, encoding="utf-8") as f:
    text = f.read()

if "location /v2/" in text:
    print("SKIP already-has-v2")
    sys.exit(0)

# server 블록 경계로 나눠 listen 443 이 있는 블록만 찾는다
starts = [i for i in range(len(text)) if text.startswith("server {", i)]
target = None
for n, s in enumerate(starts):
    e = starts[n + 1] if n + 1 < len(starts) else len(text)
    if "listen 443" in text[s:e]:
        target = (s, e)
        break
if target is None:
    print("FAIL no-443-block")
    sys.exit(1)

s, e = target
pos = text.find(ANCHOR, s, e)
if pos < 0 or text.count(ANCHOR, s, e) != 1:
    print("FAIL anchor-not-unique-in-443")
    sys.exit(1)

new = text[:pos] + BLOCK + text[pos:]
with open(PATH, "w", encoding="utf-8") as f:  # 제자리 쓰기 — 링크·inode 유지
    f.write(new)
print("OK inserted lines=%d" % BLOCK.count("\n"))
```
