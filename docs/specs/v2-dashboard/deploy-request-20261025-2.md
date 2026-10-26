# 신버전 대시보드 보완 배포 승인 요청서 (2026-10-25 2차, 배포 대상 5367334 — PC 화면·기본 기능 블록·매매 중지/재개·엔진 생존 감시)

**한 줄:** 서버를 `5692998`(v1.2026.10.25.1729)에서 `5367334`(v1.2026.10.25.2058)로 올립니다. `tradebot-v2` 를 재시작하고, 엔진(`tradebot`)도 **1회 재시작**합니다(감시 스레드 반영, E1 조건). 확인이 끝나면 허용 목록을 다시 채워 입장 버튼을 엽니다.
**배포 대상 HEAD:** `5367334`로 고정합니다. 이 요청서는 배포가 끝날 때까지 커밋하지 않고, 1차 요청서·배포 질의서와 함께 배포 완료 보고 커밋에 넣습니다.
**근거:**
- 계획 `docs/specs/v2-dashboard/plan-pc-basic-20261025.md`(6절 배포, 8-1 감시 스레드 — 사용자 결정 1025-21 가).
- 구현 커밋 5367334 게이트: exit 0, tests/v2 259 OK, JS 66/66, 회귀 350/350(push 훅 350/350). Fable `docs/fable/2026-10-25-pc-impl-1.md` 「진행」.
- 1차 요청서 `docs/specs/v2-dashboard/deploy-request-20261025.md`(D1~D8 실행 완료, D7 허용 목록은 10/25 18:41:55 비움 — 1025-14).
- 결정 1025-11 2 「엔진 재시작 없음」은 1차 배포의 D5 처리에 한한 것이고, 이번 재시작은 1025-21 가(계획 8-1 「배포 때 tradebot 1회 재시작」)에 따른 것입니다.

**실행:**
- 사용자 승인 뒤 PO(Claude)가 SSH 로 실행합니다. tradebot 재시작이 들어 있으므로 저장소 폴더에서 새 세션으로 하기를 권합니다.
- `deploy-tradebot` 은 쓰지 않습니다(조건 없이 재시작 — 1차 요청서와 같은 이유).

## 1. 승인받을 항목
| # | 항목 | 서버에서 바뀌는 것 | 되돌리기 |
|---|---|---|---|
| S1 | `git pull --ff-only` (5692998 → 5367334) | 저장소 파일 33개(엔진 매매 경로 0, 부팅 스크립트 1, v2·시험·문서·버전 줄) | 3절 |
| S2 | `tradebot-v2` 재시작 | 새 정적 파일·API 반영(ETag 캐시 때문에 필수) | 같은 명령 |
| S3 | `tradebot` 1회 재시작(E1) | 감시 스레드가 `services/data/.engine_alive.json` 을 5초마다 씀 | 같은 조건으로 다시 재시작 |
| S4 | 점검 | 임시 유닛, 쓰기 탐침(`BEGIN IMMEDIATE` → `ROLLBACK`, 데이터 안 바뀜) | 없음 |
| S5 | `.v2_allowlist`(`mcmax33`, 600) 다시 채움 — **S2~S4 통과 뒤** | 투자자 화면에 입장 버튼이 다시 나타남 | `: > .v2_allowlist`(즉시 숨김) |
| S6 | 운영자 PC·휴대폰 확인 | 없음(매매 중지/재개 1회 시험은 결정 2) | — |
| S7 | 투자자 통보 문안 A′ 발송 | (운영자가 직접 — 외부 발송) | 불가 |

- 유닛 파일(`deploy/tradebot-v2.service`)·nginx·cron 은 이번 diff 에 없어 바꾸지 않습니다. 그래서 `a3_memory_probe.sh`(유닛 메모리 상한 점검)는 다시 하지 않습니다.

## 2. 실행 순서와 멈춤 조건

**경로 규칙:** 1차 요청서와 같습니다. 모든 서버 명령은 `cd /root/upbit-tradebot-mvp && ` 를 앞에 붙여 한 호출로 실행합니다.

### 2-0. 착수 전 정지선 (읽기 전용)
- 로컬: HEAD = `origin/main` = `5367334`. 추적 파일 변경은 `M docs/specs/v2-dashboard/HANDOFF.md` 1건만 정상이다(배포 문서 묶음은 미추적).
- 서버(10/25 23시대 PO·verifier·Fable 읽기 전용 확인값과 같아야 함):
  - HEAD `5692998`, `dashboard.py:495` v1.2026.10.25.1729
  - `tradebot` active, ExecMainStartTimestamp `Sun 2026-10-25 17:10:35 KST`, NRestarts 0, ExecStart 가 `scripts/tradebot_boot.py`(드롭인)
  - `tradebot-v2` active(ActiveEnterTimestamp `Sun 2026-10-25 17:48:27 KST`)
  - `wc -c .v2_allowlist` → 0, `services/data/.engine_alive.json` 없음
  - `sqlite3 -readonly services/data/tradebot_mcmax33.db "SELECT username, trading_paused FROM users"` → `mcmax33|0`
  - 미추적 5건 그대로(check_* 3, sync_balances.py, mcmax33.sqlite3)
  - 봉 간격: `mcmax33_active_strategy.txt` = EMA, `grep -n '"interval"' mcmax33_latest_params_EMA.json` → `"interval": "minute3"`(PULLBACK 파일에는 interval 키가 없으니 보지 않는다)
- 로컬 `git diff --name-only 5692998 5367334` → 33개(배포 전 verifier 확인), `core/`·`engine/`·`services/`·`config.py`·`app.py`·`deploy/`·동결 2개(`ui/v2_entry.py`·`utils/v2_entry_token.py`) 0. tradebot 프로세스에서 바뀌는 것은 `scripts/tradebot_boot.py` 와 `pages/dashboard.py` 버전 줄 1줄뿐이어야 한다(매매 경로 0). 서버에서는 fetch 하지 않고 S1 뒤 `git diff --name-only 5692998 HEAD` 로 다시 확인한다.
- 감사 로그 백업 최신 1개 확인(`ls -t services/data/backups | head -3`).
- 비밀 파일 권한(값 미출력): `ls -l .env .streamlit/secrets.toml .v2_secret .v2_allowlist mcmax33_latest_params_PULLBACK.json` → 모두 600 root, `ls -a | grep -E '\.(bak|old|orig)$|~$'` → 0줄(사본 없음).
- 기준선 기록: `https://orionhunter7.cafe24.com/` 와 `/v2/` 의 HTTP 코드(1차 결과 200·401), 최근 3시간 `journalctl -u tradebot` 의 `database is locked`·Traceback·ERROR·CRITICAL 수.
- **하나라도 다르면 멈추고 보고한다.**

### 2-1. S1 git pull
- `git pull --ff-only` → HEAD `5367334`, `grep -n v1.2026 pages/dashboard.py` → v1.2026.10.25.2058. 충돌하면 멈춘다.
- `git diff --name-only 5692998 HEAD | wc -l` → 33, 같은 목록에 `core/`·`engine/`·`services/`·`config.py`·`app.py`·`deploy/`·`ui/v2_entry.py`·`utils/v2_entry_token.py` 0줄. 다르면 S2 로 가지 않고 멈춘다(되돌리기: `git reset --hard 5692998` 은 사용자 승인 뒤).
- pull 뒤에도 엔진은 S3 재시작 전까지 옛 부팅 스크립트로 돈다(이미 실행 중인 프로세스). 구버전 화면도 옛 코드 그대로다(Streamlit 파일 감시 꺼짐 — 바뀐 구버전 파일은 버전 줄 하나).

### 2-2. S2 tradebot-v2 재시작 (pull 바로 뒤)
- 이유: pull 직후 디스크의 새 정적 파일과 메모리의 옛 API 가 섞인다. 허용 목록이 비어 있어 아무도 들어오지 못하지만 짧게 끝낸다.
```
systemctl restart tradebot-v2
systemctl is-active tradebot-v2                       # active
journalctl -u tradebot-v2 -n 20 --no-pager            # Traceback 0
systemctl show tradebot -p ExecMainStartTimestamp     # 17:10:35 그대로(A2 — v2 재시작이 엔진을 건드리지 않음)
```
- 기동이 실패하면 journal 을 보고 멈춘다(엔진 영향 없음). 이 시점에서 신버전 블록은 「Stopped 🔴」로 보이는 것이 정상이다(S3 전, 아무도 못 봄).

### 2-3. S3 tradebot 1회 재시작 (E1) — 조건을 모두 만족할 때만
- 부록 A 의 `d3_restart.sh`(1차 D3 에서 쓴 것과 같은 원문)를 `ssh root@orionhunter7.cafe24.com "bash -s" < d3_restart.sh` 로 실행한다. 서버에 파일을 남기지 않는다. 스크립트는 다음을 모두 만족할 때만 재시작한다.
  1. 현재 3분 경계 뒤 `✅ [CONFIRMED] 봉 처리 완료` 또는 `[CONFIRMED-NO-TRADE]` 가 찍힘
  2. 미체결(`REQUESTED`·`PARTIALLY_FILLED`) 0 — 숫자 한 줄이 아니면 멈춤
  3. 다음 경계까지 60초 이상
- `STOP …` 이 나오면 다음 경계에서 다시 실행한다. 3회 연속 STOP 이면 멈추고 보고한다.
- 재시작 뒤 5분 안에 확인한다(출처 `journalctl -u tradebot`).
  - `[BOOT-RESUME] success` 1회, `[BOOT] run_live_loop start` 1회
  - 다음 확정 봉 `✅ [CONFIRMED] 봉 처리 완료` 가 정상 시각(경계 약 11초 뒤)
  - WO-12 결함 태그 0(`docs/plans/2026-09-30-wo12-boot-auto-resume/plan.md:285`)
  - ERROR·Traceback·CRITICAL·`database is locked` 0, **`[ENGINE-ALIVE]` 0**(이 태그는 실패 때만 찍힘 — `scripts/tradebot_boot.py:98·107·117·147`)
  - `ls -l services/data/.engine_alive.json` → `-rw-------` root
  - 감시 파일 내용(비밀 값 없음 — pid·시각·계정별 true/false 뿐): `cat services/data/.engine_alive.json` 을 10초 간격 2회 → `at` 이 바뀌고, `running.mcmax33` 가 `true`, `pid` 가 `systemctl show -p MainPID --value tradebot` 과 같음
  - `systemctl show tradebot -p ExecMainStartTimestamp -p NRestarts` 기록
- **BOOT-RESUME 실패·결함 태그·`[ENGINE-ALIVE]` 오류·`running.mcmax33` false 가 하나라도 있으면 S5 로 가지 않고 멈춘다.** 감시 스레드 문제는 표시만의 문제라 엔진은 그대로 두고 보고한다.

### 2-4. S4 점검
- `bash scripts/v2/check_v2_unit.sh mcmax33` → FAIL 0, 탐침 10줄(`probe-line-count` 없음). RESIDUAL `proc-environ-readable` 은 기록(알려진 항목).
  - `live-db-write-lock` 만 FAIL 이면 1회 다시 실행한다(탐침 timeout 5초 동안 엔진 쓰기와 우연히 겹친 경우 — Fable 권고). 두 번 다 FAIL 이면 멈춘다(매매 중지/재개가 503 이 됨). 이는 런북 「배포 점검 때 한 번만 실행」의 예외이며, 배포 완료 커밋에서 런북 문구를 「한 번(우연 FAIL 때 1회 재실행 허용)」으로 고친다.
  - 쓰기 탐침은 실매매 DB 를 바꾸지 않는다. 뒤에 `SELECT username, trading_paused FROM users` 가 `mcmax33|0` 그대로인지 본다.
- RSS: `ps -o rss= -p $(systemctl show -p MainPID --value tradebot-v2)` ≤ 102400(KB).
- 새 SQL 7개 EXPLAIN(부록 B, 저장소 밖 로컬 파일을 `ssh … "sqlite3 -readonly /root/upbit-tradebot-mvp/services/data/tradebot_mcmax33.db" < explain7.sql` 로 넘김, 서버에 파일 안 만듦) → `USE TEMP B-TREE` 0. 나오면 기록하고 사용자에게 알린다(응답 속도 문제, 엔진 영향 없음).
- 세션 없는 API 확인(허용 목록이 아직 비어 있음):
  - `curl -s -o /dev/null -w '%{http_code}\n' https://orionhunter7.cafe24.com/v2/api/basic` → 401
  - Origin 없는 POST: `curl -s -w '\n%{http_code}\n' -X POST -H 'Content-Type: application/json' -d '{"paused":true}' https://orionhunter7.cafe24.com/v2/api/pause` → 403 `forbidden_origin`(Origin 검사가 먼저 — `v2/handlers.py:30-35`).
  - Origin 있는 POST: 같은 명령에 `-H 'Origin: https://orionhunter7.cafe24.com'` 을 더함 → 401 `unauthorized`(세션 검사 — `v2/handlers.py:72-81`).
  - 이 절의 네 확인(basic 401 · Origin 없음 403 · Origin 있음 401 · backtester 200) 가운데 하나라도 기대값과 다르면(200·404·502 등) 멈춘다. 뒤에 `trading_paused` 0 그대로인지 본다.
  - `https://orionhunter7.cafe24.com/v2/static/backtester.html` → 200(세션 없이 열리는 페이지 — 블록은 「구버전에서 다시 들어와 주세요」)

### 2-5. S5 허용 목록 (이 순간부터 투자자에게 버튼이 보임)
```
( umask 077; printf 'mcmax33\n' > /root/upbit-tradebot-mvp/.v2_allowlist ); ls -l /root/upbit-tradebot-mvp/.v2_allowlist     # 600 root, 8바이트
cd /root/upbit-tradebot-mvp && git status --short     # 미추적 5건 그대로(허용 목록 안 보임)
```

### 2-6. S6 3점 일치·운영자 확인·관찰
- 3점 일치: 로컬·서버 HEAD `5367334`·버전 v1.2026.10.25.2058, tradebot ExecMainStartTimestamp(S3 값), tradebot-v2 active.
- 운영자 확인(1차의 1025-13 을 이어서 함 — 브라우저 **강력 새로고침**):
  - PC: 로그인 → 「📱 신버전 대시보드 (베타)」 → 「신버전 열기」 → 백테스터 페이지로 넘어감. 맨 위 블록에 제목(LIVE·mcmax33·v1.2026.10.25.2058)·LIVE 안내·현재 시각(1초 갱신)·안내 문구·최종 상태 로그·**트레이딩 엔진 상태 Running 🟢**·매매 중지·로그아웃·자산 현황 3칸, 그 아래 원본 백테스터 구역. 가로 스크롤 없음.
  - 휴대폰: 같은 입장 → 홈 맨 위에 같은 블록, 그 아래 기존 홈(종목 KRW-JTO·엔진 동작 「정상」/「지연」·차트). 백테스터 화면은 지금 그대로.
  - 블록 값이 구버전 대시보드와 같은지 나란히 본다: 보유 KRW, KRW-JTO 보유량·평가, 💹 칸(포지션 없으면 「최근 거래 … (실현)」), 엔진 상태.
  - 매매 중지/재개 1회 시험: 결정 2 를 따른다. 시험하면 `✅ [CONFIRMED] 봉 처리 완료` 직후 시작해 다음 3분 경계 60초 전까지 재개를 끝낸다(E1 과 같은 창 — 중지가 봉 판정 시각에 걸리면 그 봉의 매수·매도가 건너뛰어짐, `core/strategy_engine.py:1088`). 시험 뒤 `journalctl -u tradebot` 의 `[PAUSE] 실주문 스킵` 0건, `audit_buy_eval` 의 `trading_paused` 새 행 0건, `trading_paused` 0 을 확인한다.
  - 사용 뒤 RSS 를 다시 잰다.
- 30분 관찰(`journalctl -u tradebot` — S3 재시작 시각부터):
  - Bar# 증가, 놓친 확정 봉 0(NO-TRADE 제외), 429·418 0, 결함 태그 0, ERROR·Traceback 0
  - `[ENGINE-ALIVE]` 0, `.engine_alive.json` 의 `at` 이 관찰 끝에도 15초 이내
  - `journalctl -u tradebot-v2` ERROR·Traceback 0
- 24시간 journal 확인(1차 결정 1025-10 4 가와 같음).
- 30분 관찰 때 tradebot RSS 를 1회 기록한다(`/root/monitor_tradebot_memory.sh` 가 1400MB 초과 시 조건 없이 재시작 — 기존 위험, 10/25 23:25 `ps -o rss= -p $(systemctl show -p MainPID --value tradebot)` → 160108KB, 약 156MB).
- 배포 완료 보고: 1차·2차 요청서 결과로 `deploy-report` 를 쓰고 Fable 번들 zip 을 만든 뒤, HANDOFF·요청서 2개·배포 질의서와 함께 버전을 갱신해 커밋 승인을 요청한다(문서만이라 서버 pull 은 하지 않는다).
  - 보고 본문에 `버전: v1.2026.10.25.1729 → v1.2026.10.25.2058` 과 3점(로컬 HEAD·버전 / 서버 HEAD·버전 / ExecMainStartTimestamp)을 인용하고, 「서버 실행본 = 5367334(2058)」를 고정 기재한다(문서 커밋 뒤 GitHub HEAD 버전과 달라지므로).
  - 같은 커밋에서 런북 쓰기 탐침 문구(2-4)와 계획서 6절(「엔진 재시작 없음」 → 「8-1 채택으로 tradebot 1회 재시작」 주석)을 고친다.

## 3. 되돌리기 (가벼운 순서)
0. **먼저 중지 상태 확인**: `cd /root/upbit-tradebot-mvp && sqlite3 -readonly services/data/tradebot_mcmax33.db "SELECT trading_paused FROM users WHERE username='mcmax33'"` → 1 이면 사용자에게 알리고 구버전 「▶️ 매매 재개」로 풀게 한다(허용 목록을 비우면 신버전에서는 재개를 누를 수 없음).
1. **버튼만 즉시 숨기기**: `: > /root/upbit-tradebot-mvp/.v2_allowlist` → `wc -c` 0. 재시작 불필요, 신버전 API 도 403.
2. **감시 스레드만 문제**(오류 로그 반복 등, 매매 정상): 엔진은 그대로 두고 1 로 숨긴 뒤 보고한다. 감시 스레드는 예외를 잡아 로그만 남기므로 매매에 닿지 않는다.
3. **코드 되돌리기**: 로컬에서 `git revert 5367334`(버전 갱신, 사용자 승인) → push → 서버 pull → `systemctl restart tradebot-v2` → tradebot 재시작(S3 와 같은 조건·점검). `.engine_alive.json` 은 남아도 무해하며 엔진 재시작 뒤 지운다. 실매매 DB 에서 바뀌는 것은 사용자가 누른 `trading_paused`·logs 한 줄뿐이라 데이터 복구는 없다.
4. **신버전 전체 닫기**: 1차 요청서 2-10 의 2(runbook 「즉시 닫기」).

## 4. 투자자 통보 문안 A′ (초안 — 발송은 운영자, S7)
1차 배포의 문안 A 는 화면 재작업으로 보내지 않았습니다(D9 미발송). 이번 배포 확인 뒤 A 를 고친 A′ 하나만 보냅니다.
> 신버전 대시보드(베타)를 열었습니다. 로그인 뒤 첫 화면의 「📱 신버전 대시보드 (베타)」를 누르고, 이어 나오는 「신버전 열기」를 60초 안에 누르면 다시 로그인하지 않고 신버전으로 들어갑니다. 휴대폰에서는 홈·차트·로그와 백테스터를, PC 에서는 기본 정보와 백테스터를 한 화면에서 볼 수 있습니다. 두 화면 모두 맨 위에 구버전과 같은 기본 정보(모드·현재 시각·엔진 상태·자산 현황)와 「매매 중지/재개」·「로그아웃」 단추가 있습니다. 「매매 중지」를 누르면 엔진이 새 매수·매도 주문을 내지 않으며 손절·익절도 멈춥니다. 이미 걸려 있는 주문은 취소되지 않고, 체결되지 않은 지정가 매수가 시장가로 바뀌는 처리는 중지 중에도 계속될 수 있습니다. 매매 규칙과 엔진 동작은 바뀌지 않았습니다. 백테스터의 업비트 데이터는 준비 중이며 2차 공개 전에 엽니다. 그때까지는 바이낸스 데이터로 시험하고 저장만 할 수 있습니다. 휴대폰의 「구버전으로」나 「로그아웃」을 누르면 구버전에 다시 로그인해야 합니다. 화면이 이상하게 보이면 새로고침해 주세요.
- spec 6절 필수 문장(업비트 데이터 준비 중)을 그대로 넣었다. 보낸 뒤 `docs/operations/investor-notice-log.md` 에 한 줄 기록한다.

## 5. 영향과 위험
| 축 | 영향 | 막는 것 |
|---|---|---|
| 매매 | 재시작 1회(S3) 동안 봉 처리가 멈춤(수 초~수십 초) | E1 조건(3분봉 여유 60초 이상), BOOT-RESUME·누락 봉 확인 |
| 매매 | 감시 스레드가 엔진 프로세스 안에서 돎 | 읽기·파일 쓰기만, 예외는 잡아 로그만, 시작 실패에도 `bootstrap.run` 호출(시험 고정) |
| 동시성 | 감시 스레드의 지연 import 가 boot_resume·Streamlit import 와 겹칠 가능성(낮음, 순환 없음) | BOOT_DELAY+2초 뒤 시작, S3 5분 확인·30분 관찰 |
| 데이터 | 신버전 첫 실매매 DB 쓰기(매매 중지/재개) | 함수 1개·SQL 2개(lint), `BEGIN IMMEDIATE`, busy_timeout 3000 |
| 데이터 | 쓰기 탐침이 밀리초 잠금을 잡음 | 바로 ROLLBACK, 점검 때 1회(+재실행 1회) |
| 매매 | 중지 중 손절·익절도 멈춤, 걸린 주문·시장가 전환은 계속 | 확인 창 문구, 중지 배너, 통보 문안(시장가 전환 문장 포함 — 확인 창 basic.js 와 같은 약속) |
| 업비트 한도 | v2 서버 호출 0. PC 는 7초마다 신버전 API 3개(업비트 아님) | spec D8 |
| 투자자 화면 | 버튼은 S5 이후에만 보임 | S5 순서 |
| 되돌리기 | 중지 상태가 남은 채 숨김 | 3절 0 |

## 6. 사용자 결정 (1025-24, 2026-10-26 0시대 — 확정)
- 원문: 「1025-24 1 한 번에, 2 시험, 3 초안대로, 4 새 세션」
- 1 한 번에: S1~S6 — 멈춤 조건이 없으면 끝까지(허용 목록은 S2~S4 통과 뒤).
- 2 시험: 매매 중지/재개 실기 1회(포지션 없음·미체결 0, 확정 봉 직후~다음 경계 60초 전 창, 시험 뒤 확인 3가지).
- 3 초안대로: 문안 A′ 를 배포 확인 뒤 당일 운영자 발송.
- 4 새 세션: E1 조건이 맞는 가장 가까운 시각, 저장소 폴더 새 세션.

### 결정 항목 (요청 당시)
1. S1~S6 실행 승인: 한 번에(권고 — 멈춤 조건이 없으면 끝까지, 허용 목록은 S2~S4 통과 뒤) / 단계별.
2. 매매 중지/재개 실기 1회 시험(S6): 운영자가 포지션 없음·미체결 0 일 때 확정 봉 처리 직후~다음 경계 60초 전 창 안에서 PC 로 중지 → 배너·구버전 화면 확인 → 바로 재개(권고 — 실제 쓰기 경로를 한 번 확인, 중지 시간 수십 초) / 생략(세션 없는 API 거절만 확인).
3. 투자자 통보 문안 A′: 초안대로 배포 확인 뒤 당일 운영자 발송(권고) / 고쳐서.
4. 실행 시각·세션: E1 조건이 맞는 가장 가까운 시각, 저장소 폴더 새 세션(권고) / 이 세션.

## 부록 A. d3_restart.sh 원문 (S3 — 새 세션은 이 원문을 scratchpad 에 Write 도구로 옮겨 쓴다)
```bash
# 서버에서 stdin 으로 1회 실행: ssh root@... "bash -s" < d3_restart.sh
# E1 조건(현재 봉 확정 처리 완료 · 미체결 0 · 다음 경계까지 60초 이상)을 모두 만족할 때만 tradebot 을 재시작한다.
cd /root/upbit-tradebot-mvp || exit 9
now=$(date +%s)
boundary=$(( now - now % 180 ))
remain=$(( boundary + 180 - now ))
echo "now=$(date '+%F %T') boundary=$(date -d @$boundary '+%T') remain=${remain}s"

confirmed=$(journalctl -u tradebot --since "@$boundary" --no-pager | grep -E "✅ \[CONFIRMED\] 봉 처리 완료|\[CONFIRMED-NO-TRADE\]" | tail -1)
if [ -z "$confirmed" ]; then echo "STOP no-confirmed-since-boundary"; exit 1; fi
echo "confirmed: $(echo "$confirmed" | cut -c1-200)"

open=$(sqlite3 -readonly services/data/tradebot_mcmax33.db "SELECT COUNT(*) FROM orders WHERE state IN ('REQUESTED','PARTIALLY_FILLED');" 2>&1)
echo "open_orders=$open"
case "$open" in
  0) ;;
  *) echo "STOP open-orders-not-zero-or-error"; exit 1 ;;
esac

now2=$(date +%s)
remain2=$(( boundary + 180 - now2 ))
if [ "$remain2" -lt 60 ]; then echo "STOP remain=${remain2}s<60"; exit 1; fi

echo "RESTART at $(date '+%F %T') remain=${remain2}s"
systemctl restart tradebot
systemctl is-active tradebot
systemctl show tradebot -p ExecMainStartTimestamp
```
- 3분 경계(180초)는 2-0 에서 확인한 `minute3` 기준이다. 간격이 다르면 멈춘다.

## 부록 B. explain7.sql 원문 (S4 — `v2/api_read.py` 의 새 SQL 상수와 같고, 자리표만 값으로 바꿈)
```sql
.print '== SQL_LAST_STATUS_LOG'
EXPLAIN QUERY PLAN SELECT timestamp, message FROM logs WHERE user_id='mcmax33' AND level IN ('INFO','BUY','SELL') AND (message LIKE '🚀%' OR message LIKE '🔌%' OR message LIKE '🛑%' OR message LIKE '✅%' OR message LIKE '⚠️%' OR message LIKE '📡%' OR message LIKE '🔄%' OR message LIKE '❌%' OR message LIKE '🚨%') ORDER BY timestamp DESC LIMIT 1;
.print '== SQL_ORDERS_LAST_BUY_FILLED'
EXPLAIN QUERY PLAN SELECT id, COALESCE(avg_price, price) AS price, COALESCE(executed_at, updated_at) AS ts FROM orders WHERE user_id='mcmax33' AND ticker='KRW-JTO' AND side='BUY' AND (state IN ('completed','filled','FILLED') OR (state='CANCELED' AND executed_volume>0)) ORDER BY id DESC LIMIT 1;
.print '== SQL_ORDERS_LAST_BUY_ANY'
EXPLAIN QUERY PLAN SELECT id, COALESCE(avg_price, price) AS price, COALESCE(executed_at, updated_at) AS ts FROM orders WHERE user_id='mcmax33' AND ticker='KRW-JTO' AND side='BUY' ORDER BY id DESC LIMIT 1;
.print '== SQL_ORDERS_MAX_BUY_ID'
EXPLAIN QUERY PLAN SELECT MAX(id) AS m FROM orders WHERE user_id='mcmax33' AND ticker='KRW-JTO' AND side='BUY' AND state IN ('completed','filled','FILLED') LIMIT 1;
.print '== SQL_ORDERS_MAX_SELL_ID'
EXPLAIN QUERY PLAN SELECT MAX(id) AS m FROM orders WHERE user_id='mcmax33' AND ticker='KRW-JTO' AND side='SELL' AND state IN ('completed','filled','FILLED') LIMIT 1;
.print '== SQL_HTS_SELL_AFTER'
EXPLAIN QUERY PLAN SELECT id, timestamp FROM audit_trades WHERE ticker='KRW-JTO' AND type='HTS_SELL' AND timestamp > '2026-01-01' ORDER BY timestamp LIMIT 1;
.print '== SQL_ORDERS_RECENT'
EXPLAIN QUERY PLAN SELECT ticker, side, price FROM orders WHERE user_id='mcmax33' ORDER BY id DESC LIMIT 50;
```
- 실행 전 `v2/api_read.py` 의 상수 원문과 한 번 더 대조한다(verifier).
