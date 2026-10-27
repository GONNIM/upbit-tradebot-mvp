# 신버전 대시보드 배포 승인 요청서 (2026-10-27, 1차 화면 — 승인 요청서 그림과 같게 · 대상 = 1027-09 커밋(1d0466a + IP 차단 방지 4-0b + 문서))

**한 줄:** 서버를 `627b136`(v1.2026.10.26.1209)에서 **1027-09 커밋**(1d0466a 위에 IP 차단 방지 Task 4-0b 코드·시험과 이 요청서 등 문서를 더한 커밋, 버전은 그 커밋에서 갱신)으로 올리고 `tradebot-v2` 만 재시작합니다. **엔진(`tradebot`)은 재시작하지 않습니다.** 이번 배포부터 **v2 서버가 서버 IP 로 업비트 공개 캔들을 부릅니다**(결정 1026-23 2 가 — 상한·멈춤 조건 포함). 계좌·주문 API 는 부르지 않습니다.
**근거:** 결정 1026-19·1026-23·1026-24·1027-01·1027-03(그대로), 계획 `plan-proposal-match-20261026.md`, 구현 보고 `impl-report-20261026-proposal-match.md`(11절 = 배포 관찰 체크리스트), Fable `docs/fable/2026-10-27-proposal-match-impl-1.md` 「진행」. 결정 1027-05(배포 승인, 4 = IP 차단 방지)·1027-07(구현 시작)·1027-10(A — 창 −2~+20초 그대로), 계획 Task 4-0b, 구현 보고 §14, Fable `docs/fable/2026-10-27-ip-block-guard-plan-1.md`·`2026-10-27-ip-block-guard-time-decision-1.md`.
**실행:** 사용자 승인 뒤 PO(Claude)가 SSH 로 실행합니다. 순서: 2-0 재측정 → 실행 직전 Fable 질의 1회(「진행」일 때만) → 2-1~2-6. `deploy-tradebot` 은 쓰지 않습니다(`/root/deploy.sh` 가 `git pull`·`systemctl restart tradebot` 을 조건 없이 실행).

## 1. 승인받을 항목
| # | 항목 | 서버에서 바뀌는 것 | 되돌리기 |
|---|---|---|---|
| P1 | `git pull --ff-only` (627b136 → 1027-09 커밋) | 1d0466a 까지의 49개 + 1027-09 커밋 파일(`v2/candles.py`·`tests/v2/test_candles.py`·문서·`pages/dashboard.py` 버전 줄). 2-0 에서 실제 개수를 다시 센다. 엔진 매매 경로·부팅 스크립트·유닛 0 | 3절 |
| P2 | `tradebot-v2` 재시작 | 새 화면·새 경로 `/v2/api/candles`. 기동 5분 뒤부터 엔진 종목 캔들 미리 받기 — 서버 엔진은 KRW-JTO **3분봉**(EMA 설정 `interval: minute3`)이라 30일 = 14,400봉 = **72회, 1회/초 약 1.2~1.6분**(창 1회 대기 포함), 파일 `KRW-JTO_3.json`. 그 뒤 10분마다 새 봉 1회 | 같은 명령 / 3절 |
| P3 | 점검 | 쓰기 탐침(BEGIN IMMEDIATE→ROLLBACK), `services/data/v2_candles/` 생김(700, 파일 600) | 폴더는 지워도 다시 받음 |
| P4 | 운영자 PC·휴대폰 확인(강력 새로고침) | 없음 | — |
| P5 | 관찰: 30분 + 24시간(엔진 시세 실패 표지 8종 + 처리한 봉 수 전후 비교) | 없음 | 늘거나 봉이 줄면 tradebot-v2 정지 |

- `ui/v2_entry.py`(구버전 「신버전 대시보드 입장」 한 번 누르기)는 엔진 프로세스 안 파일이다. 서버 `.streamlit/config.toml` 이 `fileWatcherType = "none"` 이라 **다음 엔진 재시작 때 반영**된다(결정 1026-19 4 가). 그 전까지 구버전 화면은 지금 동작(두 번 누르기)과 **화면 버전 2058** 그대로다(엔진 기동 10/26 00:25:22 뒤 627b136 pull 은 화면에 반영되지 않았음 — 서버 reflog). 엔진은 `Restart=always` 라 예정 밖 재시작에도 반영되므로, 다음 엔진 재시작 직후 운영자 브라우저 확인과 체감 변경 통보 한 줄을 후속 항목(1027-04)으로 둔다.
- 배포 전 체크리스트: 회귀 게이트 `bash scripts/regression_gate.sh` 350/350(10/27 verifier 실행), 엔진·DB 구조 변경 없음(이번 배포는 실매매 DB 를 읽기만 함)이라 별도 DB 백업은 하지 않고 주간 자동 백업 `services/data/backups/tradebot_mcmax33.db.backup_20261025_110001` 을 기준으로 둔다.

## 2. 실행 순서와 멈춤 조건
모든 서버 명령은 `cd /root/upbit-tradebot-mvp && ` 를 앞에 붙인다. 여러 줄 스크립트는 로컬 파일로 만들어 `ssh … 'bash -s' < 파일` 로 보낸다(셸 heredoc 금지).

### 2-0. 정지선 (읽기 전용) — 10/27 09:4x PO 확인값과 같아야 함
- 로컬 HEAD = origin/main = 1027-09 커밋(그 뒤 커밋이 더 있으면 멈추고 보고), 추적 변경 0. `git diff --name-only 1d0466a HEAD` 는 `v2/candles.py`·`tests/v2/`·`docs/`·`pages/dashboard.py`(버전 줄)만이어야 한다.
- 서버 HEAD `627b136`, `dashboard.py:495` v1.2026.10.26.1209, tradebot active·ExecMainStartTimestamp `Mon 2026-10-26 00:25:22 KST`·NRestarts 0, tradebot-v2 active `Mon 2026-10-26 17:34:30 KST`, `.v2_allowlist` 8바이트, 서버 미추적 5건, tornado 6.5.1, `.streamlit/config.toml` `fileWatcherType = "none"`, 디스크 여유 ≥ 5G, `services/data/v2_candles` 없음.
- `git diff --name-only 627b136 <대상>` 에서 `v2/ tests/ docs/` 밖은 `pages/dashboard.py`·`ui/v2_entry.py` 둘뿐, 엔진 경로(`core/ engine/ services/ config.py app.py deploy/ scripts/tradebot_boot.py utils/`) 0.
- 서버 TLS: `venv/bin/python` 으로 `api.upbit.com:443` TLS 연결만(HTTP 요청 없음) → `tls-ok`(10/27 09:4x TLSv1.3 확인).
- `sqlite3 -readonly services/data/tradebot_mcmax33.db "SELECT username, trading_paused FROM users"` → `mcmax33|0`.
- 비밀 파일 권한(값 미출력): `ls -l .env .streamlit/secrets.toml .v2_secret .v2_allowlist mcmax33_latest_params_PULLBACK.json` → 모두 600 root, `ls -a | grep -E '\.(bak|old|orig)$|~$'` → 0줄.
- 기준선(배포 전 24시간, `journalctl -u tradebot -o cat`) — 이 목록을 「엔진 시세 실패 표지」라 부른다:
  - 「응답 없음」 4종: `[REST] Batch … 응답 없음`·`[실시간 API] 응답 없음`·`[백필] API 응답 없음`·`[SYNC-FILL] API 응답 없음`(10/27 09:48: 모두 0)
  - 429 의 첫 증상(pyupbit 가 429 를 삼켜 None → 재시도로 회복되면 위 4종에 안 잡힘): `연결 실패`·`[실시간 API] 예외`·`[백필 실패]`·`[SYNC-FILL] API 예외`(10/27 09:5x: 모두 0, 10/07 이후 0), 그리고 엔진 REST 경로의 `[RECONCILE] 예외 발생`·`[REST-SAFE] 예외`·`[REST-SAFE] 빈 응답`(Fable 24시간 0 확인) — 엔진 쪽 429 는 v2 로그에 남지 않고 이 표지로만 보인다
  - 처리한 봉 수: `봉 처리 완료` + `CONFIRMED-NO-TRADE` 합계(10/27 09:5x: 359 + 127 = 486, 3분봉 하루 480 과 맞음) — 「놓친 확정 봉」 판정 기준
  - 최근 1시간 `ERROR|Traceback|CRITICAL|database is locked` 수(09:4x: 0), `journalctl -u tradebot-v2` ERROR·Traceback 수.
- 하나라도 다르면 멈추고 보고한다.

### 2-1. P1 pull
- `git pull --ff-only` → HEAD 대상 커밋, `grep -n v1.2026 pages/dashboard.py` → 1027-09 커밋의 버전. 충돌하면 멈춘다.
- `git diff --name-only 627b136 HEAD` 가 2-0 과 같은지 다시 확인. 다르면 멈춘다.

### 2-2. P2 tradebot-v2 재시작 (pull 바로 뒤)
```
systemctl restart tradebot-v2
systemctl is-active tradebot-v2
journalctl -u tradebot-v2 -n 30 --no-pager            # Traceback 0
systemctl show tradebot -p ExecMainStartTimestamp     # 00:25:22 그대로
date '+%F %T'                                         # 재시작 시각 기록(미리 받기 = +5분)
```
- 기동 실패 시 journal 을 보고 멈춘다(엔진 영향 없음). 3절 1 로 버튼부터 숨긴다.

### 2-3. P3 점검
- `bash scripts/v2/check_v2_unit.sh mcmax33` → FAIL 0(직전 배포와 같은 기준: `live-db-write-lock` 만 FAIL 이면 `✅ [CONFIRMED] 봉 처리 완료` 직후 1회 재실행, 두 번 다 FAIL 이면 멈춤; RESIDUAL `proc-environ-readable` 은 기록만). 뒤에 `sqlite3 -readonly … "SELECT username, trading_paused FROM users"` → `mcmax33|0`.
- 응답 머리: `curl -sI https://orionhunter7.cafe24.com/v2/static/bt_ui.js` → 200·`Cache-Control: no-cache`.
- 세션 없는 API: `/v2/api/basic`·`/v2/api/candles?market=KRW-BTC&unit=1&days=1`·`/v2/api/candles/progress` → 모두 401(세션 없이는 업비트를 부르지 않음). POST `/v2/api/pause` Origin 없음 403 `forbidden_origin`, Origin 있음 401.
- 미리 받기(재시작 +5분 ~ +8분):
  - `journalctl -u tradebot-v2 --since "<재시작 시각>"` 의 `[V2-CANDLES]` 줄 — **0줄 기대**(정상 수집은 로그를 남기지 않음; 429·418·오류일 때만 찍힘).
  - 재시작 약 7~8분 뒤 `ls -l --time-style=+%T services/data/v2_candles/` → `KRW-JTO_3.json` 1개(크기·수정 시각 기록 = 미리 받기 성공 근거), `-rw-------` root, 폴더 `drwx------`, `.tmp`·`.halt.json` 없음.
  - 이 구간에 엔진 시세 실패 표지(2-0) 모두 0.
- 메모리(impl-report 11절 (d), 계획 Task 9 Step 6 (d)): 미리 받기 중·끝난 뒤 `systemctl show tradebot-v2 -p MemoryCurrent` 와 `/sys/fs/cgroup/system.slice/tradebot-v2.service/memory.stat`(cgroup2, 확인됨) 의 `anon`·`file` 을 따로 기록. **최악 경우 1회(2-5 의 30분 관찰을 마친 뒤 실행)**: 30분 관찰에서 엔진 시세 실패 표지가 0 일 때만, `✅ [CONFIRMED] 봉 처리 완료` 직후에 운영자 브라우저로 엔진 종목이 아닌 종목(KRW-BTC) 1분·30일 수집(서버 IP 216회, 4회/초 — 로컬 실측 엔진 경계 창을 안 만나면 약 57초, 3분 창 1번 만나면 약 81초, Task 4-0b)을 누르고, 그 사이 엔진 종목 백테스트를 한 번 더 누른다. 이 동안 PO 가 1초마다 `anon` 을 읽어 최대값을 기록한다. **anon 최대 75 MiB 이하가 기준**(계획 수용 기준). 넘으면 기록하고 보고한다(MemoryMax 150M·별도 유닛이라 엔진 영향은 없으나 기준 반박이므로 다음 수정 대상). 끝난 뒤 엔진 시세 실패 표지 다시 0 확인.
- `[V2-CANDLES] status=429` 1건 이상이면 보고, `status=429 HALT` 또는 418 1건이면 즉시 **`systemctl stop tradebot-v2`**. 그 밖에 하나라도 기대값과 다르면(특히 엔진 시세 실패 표지 1건 이상) **`systemctl stop tradebot-v2`** 후 보고한다(엔진 영향 없음, 3절).

### 2-4. P4 운영자 확인 (강력 새로고침 Cmd+Shift+R / 휴대폰 새로고침)
- 구버전 로그인 → 「📱 신버전 대시보드 (베타)」 → 「신버전 열기」(엔진 재시작 전이라 두 번 누르기 그대로).
- 홈: 그림 2-가 배치, 배지 줄 바로 아래 「⏸️ 매매 중지」, 자산 카드 아래 원화 잠김/코인 잠김·기록 시각·현재가 줄, 머리 막대 「이름님 · 구버전으로 · 로그아웃」.
- 차트·로그(감사 로그·엔진·오류 전환)·운용(단추 모두 비활성) 확인.
- 백테스터: 업비트 · 엔진 종목 · 엔진 봉 단위 · 30일 그대로 「데이터 가져오기 + 백테스트」 → **미리 받기가 끝난 뒤라면 데이터 수 초 안에 결과**(11절 (c)). 운영자 브라우저 네트워크 기록이 있으면 `/v2/api/candles` 응답 시간을 적는다. 다른 종목은 시험하지 않는다(서버 IP 216회 — 메모리 측정 1회만 2-3 에서).
- 「설정 저장」은 누르지 않고 확인 창만 열어 문구·「이 설정으로 동작」 비활성 확인 후 「취소」.
- PC 와 휴대폰 모두 가운데 휴대폰 폭.

### 2-5. 관찰
- 30분: `journalctl -u tradebot-v2` ERROR·Traceback 0, `[V2-CANDLES]` 0줄, `journalctl -u tradebot` ERROR·Traceback·CRITICAL·`database is locked`·결함 태그 0, 엔진 시세 실패 표지(2-0) 모두 0, 처리한 봉 수가 30분에 10개 안팎(3분봉), ExecMainStartTimestamp 00:25:22 그대로. 끝나면 2-3 의 최악 경우 메모리 측정 1회.
- 24시간(별도 확인, 1026-06 과 함께): 엔진 시세 실패 표지 8종 배포 뒤 24시간 건수와 처리한 봉 수 합계(`봉 처리 완료` + `CONFIRMED-NO-TRADE`)와 고유 봉 시각 수(`grep -E "봉 처리 완료|CONFIRMED-NO-TRADE" | grep -oE "ts=[0-9: -]+" | sort -u | wc -l`, 기대 480 — 합계에는 중복 약 6건이 섞여 있음, 1026-07)를 2-0 기준(실패 표지 0, 합계 486, 고유 약 480)과 비교. 고유 수가 478 미만이면 놓친 봉으로 본다. **실패 표지가 1건이라도 늘거나 처리한 봉 수가 기준보다 6개(약 1.2%) 넘게 적으면(486 − 6 = 480 = 24시간 고유 봉 수; 일별 합계 10/22~26 은 481~483 으로 안정 — verifier 확인) `systemctl stop tradebot-v2` 하고 보고**(엔진 보호 우선).

### 2-6. 완료 보고
- 3점: 로컬 HEAD·버전 / 서버 HEAD·파일 버전(1027-09 커밋의 버전)·화면 버전(**2058** — 엔진 재시작 전) / tradebot ExecMainStartTimestamp(00:25:22).
- `버전: v1.2026.10.26.1209 → <대상 커밋 버전> (서버 파일 기준, 구버전 화면 2058·입장 단추는 다음 엔진 재시작 때)`.
- 2-3 미리 받기·메모리 수치, 2-4 백테스트 체감 시간.
- 보고 문서·HANDOFF 갱신은 다음 문서 커밋(승인 별도, 버전 갱신 포함).

## 3. 되돌리기
1. **업비트 호출만 멈추기(가장 빠름):** `systemctl stop tradebot-v2` — 신버전 전체가 멈추고 업비트 호출 0. 엔진·구버전 영향 없음. 구버전의 입장 버튼은 보이지만 눌러도 신버전이 열리지 않으므로 이어서 2번.
2. **버튼만 숨기기:** 먼저 `sqlite3 -readonly services/data/tradebot_mcmax33.db "SELECT trading_paused FROM users WHERE username='mcmax33'"` → 1 이면 사용자에게 알리고 구버전 「▶️ 매매 재개」로 풀게 한다. 그다음 `: > /root/upbit-tradebot-mvp/.v2_allowlist` → `wc -c` 0(재시작 불필요).
3. **418 정지 또는 429 정지가 걸렸을 때:** 운영 문서 `v2-runbook.md` 「418 정지 해제」 절차 — 원인 확인 → 엔진 시세 조회 정상 확인 → `services/data/v2_candles/.halt.json` 삭제 → `systemctl restart tradebot-v2`. 429 정지 = 24시간 안 두 번째 429(`journalctl -u tradebot-v2` 의 `status=429 HALT`, 정지 파일 `"status": 429`)로, 418 과 같은 절차로 푼다. 첫 429 의 10분 멈춤은 저절로 풀리므로 할 일 없음(`.cooldown.json` 은 지우지 않는다).
4. **코드 되돌리기:** 서버에서 부분 checkout 은 하지 않는다. 로컬에서 `v2/`·`tests/v2/` 를 627b136 상태로 되돌리는 새 커밋(버전 갱신, 사용자 승인) → push → 서버 pull → `systemctl restart tradebot-v2`. `ui/v2_entry.py` 는 엔진 재시작 전까지 옛 코드가 돌므로 되돌림 대상에서 서두르지 않는다. `services/data/v2_candles/` 는 지워도 된다.

## 4. 영향
| 축 | 영향 | 막는 것 |
|---|---|---|
| 매매·엔진 | 엔진 코드·재시작 없음 | 2-0 diff 범위, ExecMainStartTimestamp |
| 업비트 한도(서버 IP) | **새로 생김.** 미리 받기 1회/초(기동 5분 뒤 72회 약 1.2~1.6분, 그 뒤 10분마다 1회), 사용자 백테스트 최대 4회/초(Task 4-0b, 결정 1027-05 4 — 이전 상한은 초당 5회). 엔진 캔들 조회와 IP 초당 10회 한도를 나눔 — 엔진은 봉이 보이는 눈금에서 확정 조회 1회 + `[REST] 다중 호출` 2회 × 배치 2 = 5회를 0.4초 안에 보내고(서버 journal 10/27 10시대, 24시간 「다중 호출 시작」 오프셋 5~11초 740건·15~16초 8건·20~92초 224건), 그 1초에 v2 4회가 겹치면 관측 기준 9 ≤ 10 (관측값 기준이며 코드 상한이 아니다 — 구버전 화면 새로고침(캔들 3회)·엔진 기동(801봉, 5회 이상)·여러 엔진 동시 묶음이 같은 1초에 겹치면 10 을 넘을 수 있어, 보장이 아니라 창·쉼·429 멈춤으로 겹침을 줄이는 장치다. verifier 2026-10-27). 또 v2 는 엔진 봉 경계 −2초 ~ +20초 창(서버에서 실행 중인 모든 엔진의 봉 단위 기준, 못 읽으면 1분)에서는 부르지 않아 엔진 묶음의 약 77%(관측, +20초 창 기준) 와 아예 겹치지 않는다. `sec≤4 → 1초 쉼` 도 그대로. **최악의 경우:** 429 가 쌓여 업비트가 418 로 서버 IP(문서상 「IP 또는 계정」)를 일시 차단하면, 그동안 엔진의 확정 봉 조회도 실패해 봉 누락·매수·손절·익절 지연이 생길 수 있다. 막는 장치는 모두 그 전에 줄이거나 바로 멈추는 것이고, 418 자체를 되돌리지는 못한다. 418 은 429 뒤 요청이 이어질 때 생기므로 v2 는 첫 429 에 10분 멈추고 24시간 안 두 번째 429 에 정지한다(엔진 요청에 떨어진 429 는 v2 가 모른다 — 그래서 상한·창으로 겹침 자체를 줄인다) | 동시 1건, 4회/초, 엔진 경계 창, sec≤4 쉼, 첫 429 → 10분 멈춤(재시작에도 유지)·24시간 안 두 번째 429 → 정지 파일, 418 정지 파일, 엔진 pid 바뀌면 5분 쉼, 2-3·2-5 엔진 시세 실패 표지 8종 감시·1건이면 즉시 정지. 로컬 실측 429 0(216회 3번 + Task 4-0b 뒤 3번) |
| 업비트 한도(계좌·주문) | 없음(경로 0, 시험 고정) | test_basic_pause·test_server |
| v2 서버 | 로컬 측정 최고 61.3 MiB(MemoryMax 150M) | 2-3 메모리 기록 |
| 디스크 | `v2_candles/` 최대 4파일·30MB | 상한 코드, 여유 20G |
| 투자자 화면 | 홈·차트·백테스터·로그·운용 배치가 그림대로 바뀜(사라지는 것 = impl-report 4절). 배포 직후 새로고침 필요 | 5절 통보 |

## 5. 투자자 통보 문안 A″ (1026-04 대체 — 배포 확인 뒤 운영자 발송)
> 신버전 대시보드(베타) 화면을 승인 요청서에 보여 드린 그림과 같게 바꿨습니다. 홈·차트·백테스터·로그·운용 5개 메뉴가 화면 아래에 있고, PC 와 휴대폰 모두 같은 화면입니다. 홈 위쪽 배지 아래에 「매매 중지」 단추, 오른쪽 위에 「로그아웃」이 있습니다. 「매매 중지」를 누르면 엔진이 새 매수·매도 주문을 내지 않으며 손절·익절도 멈춥니다. 이미 걸려 있는 주문은 취소되지 않고, 체결되지 않은 지정가 매수가 시장가로 바뀌는 처리는 중지 중에도 계속될 수 있습니다. 백테스터에서 이제 업비트 데이터로도 시험할 수 있습니다(1분봉 30일 기준, 처음 받는 종목은 1분~1분 30초 정도, 그 뒤는 몇 초). 시험 결과는 1차에서는 「저장만 하기」만 됩니다. 운용 메뉴의 단추들은 2차 공개 때 열립니다. 매매 규칙과 엔진 동작은 바뀌지 않았습니다. 화면이 이상하게 보이면 새로고침(PC 는 Ctrl+Shift+R 또는 Cmd+Shift+R)해 주세요.
- 로컬 실측(4회/초·창 적용): 창을 안 만나면 57.2초, 한 번 만나면 81.3초(3분봉에서 약 44%), 1분 폴백 93.7초. 2-4 서버 체감 측정값이 크게 다르면 그 값에 맞춰 고친 뒤 보낸다.
- 보낸 뒤 `docs/operations/investor-notice-log.md` 에 한 줄 기록한다(투자자 연락 원칙).
- 입장 단추 한 번 누르기는 다음 엔진 재시작 뒤 바뀌므로 문안에 넣지 않았다(바뀐 뒤 체감 변경 통보 대상 — 그때 한 줄).

## 6. 결정 항목
1. P1~P5 실행: 한 번에(권고 — 멈춤 조건이 없으면 2-5 30분 관찰까지) / 단계별.
2. 실행 세션: 저장소 폴더 새 세션(권고 — 직전 배포들과 같은 방식, 이 세션은 구현 맥락이 길어 압축 위험) / 이 세션.
3. A″ 문안: 위 문안대로 배포 확인 뒤 운영자 발송(권고) / 고쳐서.
4. 4절 업비트 한도 「최악의 경우」(418 시 엔진 시세 조회도 막힘)를 알고 진행: 진행(권고 — 상한·쉼·즉시 정지로 실제 가능성은 낮음, 로컬 429 0) / 상한을 더 낮춰 다시(예: 사용자 3회/초 — 다른 종목 첫 실행이 약 75초로 늘어 「1분 이내」를 못 지킴). → **사용자 결정 1027-05 4 「IP 차단 발생하지 않는 방법으로 진행」, 1027-10 「A」(2026-10-27): 상한 초당 4회 + 엔진 봉 경계 −2~+20초 창 + 429 1회 10분·24시간 안 2회째 정지. 다른 종목 첫 실행 57초(창 안 만남) 또는 81초(만남, 3분봉 약 44%), 로컬 실측.**

5. 배포 전 문서 커밋: 이 요청서·Fable 질의 파일·HANDOFF·impl-report 정정(3분봉 72회)을 문서 커밋 1개(`pages/dashboard.py` 버전 갱신 포함)로 커밋·push 하고 그 커밋을 배포 대상으로 함(권고 — **이번부터 새 방식**: 직전 두 배포는 요청서를 미커밋으로 두고 기능 커밋을 배포, 문서 커밋은 배포 뒤 서버 미반영이었다. 새 방식은 서버 HEAD = GitHub HEAD 라 3점 보고가 한 값이 되고, 새 세션이 요청서를 저장소에서 읽는다) / 직전 방식대로 1d0466a 배포. (1027-07·1027-10 뒤: IP 차단 방지 4-0b 코드·시험도 같은 커밋에 넣는다 — 그래서 대상은 「1027-09 커밋」)

### 사용자 결정 1027-05 (2026-10-27 10시대)
- 원문: 「1027-05 승인: 1 한 번에, 2 새 세션, 3 문안대로, 4 IP 차단 발생하지 않는 방법으로 진행하시오. , 5 문서 커밋 포함」 (직전 메시지 「4 IP 차단 우회하시오」는 사용자가 이 문장으로 고침)
- 4 의 반영: 배포 전에 v2 업비트 수집에 (0) 상한 초당 4회, (가) 엔진 봉 경계 −2초~+20초 창에서는 부르지 않기, (나) 429 1회 → 10분 멈춤, 24시간 안 2회째 429 → 정지 파일(418 과 같은 수동 해제)을 더한다(계획서 Task 4-0b). 구현·검수·verifier·Fable 뒤 이 요청서를 고치고, 코드 커밋은 사용자 승인을 다시 받는다.

## 7. 후속 항목
- 1027-04: 다음 엔진(tradebot) 재시작 직후(예정 밖 재시작 포함 — `Restart=always`) 운영자 브라우저로 구버전 「신버전 대시보드 입장 (모드)」 한 번 누르기 확인, 화면 버전이 대상 커밋 버전으로 바뀐 것 확인, 투자자 체감 변경 통보 한 줄.
