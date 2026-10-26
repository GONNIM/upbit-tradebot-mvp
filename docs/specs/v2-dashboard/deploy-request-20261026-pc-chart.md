# 신버전 대시보드 배포 승인 요청서 (2026-10-26, PC 차트 확대 — 대상 627b136)

**한 줄:** 서버를 `5367334`(v1.2026.10.25.2058)에서 `627b136`(v1.2026.10.26.1209)로 올리고 `tradebot-v2` 만 재시작합니다. **엔진(`tradebot`)은 재시작하지 않습니다.**
**근거:** 결정 1026-08·1026-10·1026-12, 계획 `plan-pc-chart-20261026.md`, 구현 보고 `impl-report-20261026-pc-chart.md`, Fable `docs/fable/2026-10-26-pc-chart-impl-1.md` 「진행」.
**실행:** 사용자 승인 뒤 PO(Claude)가 SSH 로 실행합니다. 순서: 2-0 재측정 → 실행 직전 Fable 질의 1회(「진행」일 때만) → 2-1~2-5. 실행 세션은 6절 3 에서 정합니다. `deploy-tradebot` 은 쓰지 않습니다(`/root/deploy.sh` 가 `git pull`·`systemctl restart tradebot` 을 조건 없이 실행).

## 1. 승인받을 항목
| # | 항목 | 서버에서 바뀌는 것 | 되돌리기 |
|---|---|---|---|
| P1 | `git pull --ff-only` (5367334 → 627b136) | 파일 32개(v2·시험·문서 + dashboard.py 버전 줄). 엔진 매매 경로·부팅 스크립트·유닛 0 | 3절 |
| P2 | `tradebot-v2` 재시작 | 새 화면 파일·Cache-Control 반영 | 같은 명령 |
| P3 | 점검 | 쓰기 탐침(BEGIN IMMEDIATE→ROLLBACK, 데이터 안 바뀜) | 없음 |
| P4 | 운영자 PC·휴대폰 확인(강력 새로고침) | 없음 | — |

## 2. 실행 순서와 멈춤 조건
모든 서버 명령은 `cd /root/upbit-tradebot-mvp && ` 를 앞에 붙인다.

### 2-0. 정지선 (읽기 전용) — 10/26 12:1x PO 확인값과 같아야 함
- 로컬 HEAD = origin/main = `627b136`, 추적 변경 0.
- 서버 HEAD `5367334`, `dashboard.py:495` v1.2026.10.25.2058, tradebot active·ExecMainStartTimestamp `Mon 2026-10-26 00:25:22 KST`·NRestarts 0, tradebot-v2 active `00:24:59`, `.v2_allowlist` 8바이트, 미추적 5건, 서버 tornado 6.5.1, `trading_paused` 0.
- `git diff --name-only 5367334 627b136` 32개, 엔진 경로(`core/ engine/ services/ config.py app.py deploy/ scripts/tradebot_boot.py ui/v2_entry.py utils/v2_entry_token.py`) 0, v2·tests·docs 밖은 `pages/dashboard.py`(버전 줄) 하나.
- `sqlite3 -readonly services/data/tradebot_mcmax33.db "SELECT username, trading_paused FROM users"` → `mcmax33|0`.
- 비밀 파일 권한(값 미출력): `ls -l .env .streamlit/secrets.toml .v2_secret .v2_allowlist mcmax33_latest_params_PULLBACK.json` → 모두 600 root, `ls -a | grep -E '\.(bak|old|orig)$|~$'` → 0줄.
- 기준선: `https://orionhunter7.cafe24.com/` 200·`/v2/` 401, 최근 1시간 `journalctl -u tradebot` `grep -cE "ERROR|Traceback|CRITICAL|database is locked|\b429\b|\b418\b"` 수(글자 그대로 `locked` 는 INFO `locked=0` 줄에 걸리므로 쓰지 않음), `journalctl -u tradebot-v2` ERROR·Traceback 수.
- 하나라도 다르면 멈추고 보고한다.

### 2-1. P1 pull
- `git pull --ff-only` → HEAD `627b136`, `grep -n v1.2026 pages/dashboard.py` → v1.2026.10.26.1209. 충돌하면 멈춘다.
- `git diff --name-only 5367334 HEAD` 가 2-0 과 같은지 다시 확인. 다르면 멈춘다.
- 구버전 화면은 Streamlit 파일 감시가 꺼져 있어 버전 줄이 다음 tradebot 재시작 때 반영된다(화면 버전 2058 유지 — 보고에 따로 적음).

### 2-2. P2 tradebot-v2 재시작 (pull 바로 뒤)
```
systemctl restart tradebot-v2
systemctl is-active tradebot-v2
journalctl -u tradebot-v2 -n 20 --no-pager            # Traceback 0
systemctl show tradebot -p ExecMainStartTimestamp     # 00:25:22 그대로
```
- 기동 실패 시 journal 을 보고 멈춘다(엔진 영향 없음). 3절 1 로 버튼부터 숨긴다.

### 2-3. P3 점검
- `bash scripts/v2/check_v2_unit.sh mcmax33` → FAIL 0, 탐침 10줄(`probe-line-count` 없음), RESIDUAL `proc-environ-readable` 은 나오면 기록만(알려진 항목). `live-db-write-lock` 만 FAIL 이면 1회 재실행, 두 번 다 FAIL 이면 멈춤. 쓰기 탐침은 `✅ [CONFIRMED] 봉 처리 완료` 직후에 실행한다(엔진 쓰기와 겹침 줄임). 뒤에 `sqlite3 -readonly … "SELECT username, trading_paused FROM users"` → `mcmax33|0`.
- RSS: `ps -o rss= -p $(systemctl show -p MainPID --value tradebot-v2)` ≤ 102400.
- 응답 머리:
  - `curl -sI https://orionhunter7.cafe24.com/v2/static/style.css` → 200·`Cache-Control: no-cache`, ETag 기록
  - `curl -sI -H 'If-None-Match: "<위 ETag>"' https://orionhunter7.cafe24.com/v2/static/style.css` → 304·`Cache-Control: no-cache`
  - `curl -sI https://orionhunter7.cafe24.com/v2/static/backtester.html` → 200·no-cache
- 세션 없는 API:
  - `curl -s -o /dev/null -w '%{http_code}\n' https://orionhunter7.cafe24.com/v2/api/basic` → 401
  - `curl -s -w '\n%{http_code}\n' -X POST -H 'Content-Type: application/json' -d '{"paused":true}' https://orionhunter7.cafe24.com/v2/api/pause` → 403 `forbidden_origin`
  - 같은 명령에 `-H 'Origin: https://orionhunter7.cafe24.com'` → 401 `unauthorized`
- 넘김 스크립트 없음: 서버 파일 `grep -c '__v2toPC' v2/static/index.html v2/static/app.js v2/static/basic.js` → 모두 0.
- 하나라도 기대값과 다르면 멈추고 3절 1(버튼 숨김) 후 보고한다.

### 2-4. P4 운영자 확인 (브라우저 강력 새로고침 Cmd+Shift+R — 이번 배포만 필요, 옛 CSS 캐시 때문)
- PC: 로그인 → 「📱 신버전 대시보드 (베타)」 → 「신버전 열기」 → 홈(가운데 휴대폰 폭, 맨 위 기본 블록·자산 1열) → 「차트」 탭에서 차트가 창 전체 폭·높이, 페이지 스크롤 없음 → 「로그」·「운용」 가운데 폭 → 「백테스터」 링크로 백테스터(위에 기본 블록) → 뒤로가기.
- 휴대폰: 지금 화면과 같음(바뀐 것 없음).
- 구버전 화면 그대로.

### 2-5. 30분 관찰
- `journalctl -u tradebot-v2` ERROR·Traceback 0, RSS 1회 기록(≤102400).
- `journalctl -u tradebot` 은 이번 배포와 무관하나 같은 창에서 ERROR·Traceback·CRITICAL·`database is locked`·429·418·결함 태그 0 확인(엔진 재시작 없음 확인 겸 ExecMainStartTimestamp 00:25:22 그대로).

### 2-6. 완료 보고
- 3점: 로컬 HEAD·버전(627b136·1209) / 서버 HEAD·파일 버전(627b136·1209)·화면 버전(2058 — 엔진 재시작 전) / tradebot ExecMainStartTimestamp(00:25:22).
- `버전: v1.2026.10.25.2058 → v1.2026.10.26.1209 (서버 파일 기준, 구버전 화면은 다음 엔진 재시작 때)`.
- 보고 문서·HANDOFF 갱신은 다음 문서 커밋(승인 별도).

## 3. 되돌리기
1. **버튼만 숨기기:** 먼저 `sqlite3 -readonly services/data/tradebot_mcmax33.db "SELECT trading_paused FROM users WHERE username='mcmax33'"` → 1 이면 사용자에게 알리고 구버전 「▶️ 매매 재개」로 풀게 한다. 그다음 `: > /root/upbit-tradebot-mvp/.v2_allowlist` → `wc -c` 0 (재시작 불필요, 다음 요청부터 403).
2. **코드 되돌리기:** 서버에서 부분 checkout 은 하지 않는다. 로컬에서 `v2/`·`tests/v2/` 만 5367334 상태로 되돌리는 새 커밋을 만든다(버전 갱신, 사용자 승인 — spec·계획·HANDOFF 결정 기록은 그대로 둠) → push → 서버 pull → `systemctl restart tradebot-v2`. 엔진 재시작 불필요.

## 4. 영향
| 축 | 영향 | 막는 것 |
|---|---|---|
| 매매·엔진 | 없음(엔진 경로 0, 재시작 없음) | 2-0 diff 범위, ExecMainStartTimestamp 확인 |
| 업비트 한도 | 서버 IP 0 그대로. PC 브라우저가 차트 탭에서 투자자 IP 로 200봉·30초 | 실패해도 화면 「갱신 실패」만 |
| v2 서버 | PC 도 홈 API 7초 읽기(모바일과 같은 양), 정적 파일 304 확인 요청 | RSS·journal 관찰 |
| 투자자 화면 | PC 배치가 바뀜(UI 브리핑 3항, impl-report). 배포 직후 강력 새로고침 필요 | A′ 수정 문안에 새로고침 안내 포함 |

## 5. 투자자 통보 문안 A′ 수정본 (1026-04 — 배포 확인 뒤 운영자 발송)
> 신버전 대시보드(베타)를 열었습니다. 로그인 뒤 첫 화면의 「📱 신버전 대시보드 (베타)」를 누르고, 이어 나오는 「신버전 열기」를 60초 안에 누르면 다시 로그인하지 않고 신버전으로 들어갑니다. 휴대폰과 PC 모두 같은 화면(홈·차트·로그·운용·백테스터)이며, PC 에서는 차트 탭에서 차트를 화면 전체 크기로 볼 수 있습니다. 홈 맨 위에 구버전과 같은 기본 정보(모드·현재 시각·엔진 상태·자산 현황)와 「매매 중지/재개」·「로그아웃」 단추가 있습니다. 「매매 중지」를 누르면 엔진이 새 매수·매도 주문을 내지 않으며 손절·익절도 멈춥니다. 이미 걸려 있는 주문은 취소되지 않고, 체결되지 않은 지정가 매수가 시장가로 바뀌는 처리는 중지 중에도 계속될 수 있습니다. 매매 규칙과 엔진 동작은 바뀌지 않았습니다. 백테스터의 업비트 데이터는 준비 중이며 2차 공개 전에 엽니다. 그때까지는 바이낸스 데이터로 시험하고 저장만 할 수 있습니다. 「구버전으로」나 「로그아웃」을 누르면 구버전에 다시 로그인해야 합니다. 화면이 이상하게 보이면 새로고침(PC 는 Ctrl+Shift+R 또는 Cmd+Shift+R)해 주세요.
- 바뀐 곳(4): ① A′ 의 「휴대폰에서는 홈·차트·로그와 백테스터를, PC 에서는 기본 정보와 백테스터를 한 화면에서」 → 위 3번째 문장, ② 「두 화면 모두 맨 위에」 → 「홈 맨 위에」, ③ 「휴대폰의 「구버전으로」나」 → 「「구버전으로」나」(PC 에도 있음), ④ 새로고침 안내에 PC 키 추가. 나머지(spec 6절 필수 문장 「업비트 데이터 준비 중」, 시장가 전환 문장 포함)는 A′ 그대로.
- 보낸 뒤 `docs/operations/investor-notice-log.md` 에 한 줄 기록한다(투자자 연락 원칙).

## 6. 사용자 결정 (1026-14, 2026-10-26 12시대 — 확정)
- 원문: 「1026-14 1 한 번에, 2 초안대로, 3 새 세션」
- 1 한 번에: 2-0 재측정 → 실행 직전 Fable 질의 「진행」 → 2-1~2-5, 멈춤 조건이 없으면 끝까지(운영자 확인 2-4 는 사용자에게 요청).
- 2 초안대로: 5절 A′ 수정본을 배포 확인 뒤 운영자 발송, 보낸 뒤 investor-notice-log 기록.
- 3 새 세션: 저장소 폴더 새 세션에서 실행.

### 결정 항목 (요청 당시)
1. P1~P4 실행: 한 번에(권고 — 멈춤 조건이 없으면 끝까지) / 단계별.
2. A′ 수정본: 위 문안대로 배포 확인 뒤 운영자 발송(권고) / 고쳐서.
3. 실행 세션: 저장소 폴더 새 세션(규칙상 권고 — 배포는 새 세션) / 이 세션(PO 생각 — 엔진 재시작이 없어 위험이 늘지 않고, 이 세션에 실측·검증 맥락이 있음).
