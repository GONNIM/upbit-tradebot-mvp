# 인수인계 — 신버전 대시보드 · PULLBACK 전략 (7판)

- 작성: 2026-10-21 · 개정: 2026-10-22 (2~6판), **2026-10-25 (7판 — plan Task 0~10 구현 완료, 구현 완료 보고, 다음은 배포 승인 요청서)**
- 기준: 7판 커밋(이 파일을 바꾼 커밋, `git log -1 -- docs/specs/v2-dashboard/HANDOFF.md`). 직전 코드 커밋 `007ee7f`(Task 9). 서버는 여전히 `156b351`, `dashboard.py` v1.2026.10.20.1711, tradebot 기동 2026-10-20 17:40:51 KST(2026-10-25 verifier SSH 읽기 전용 확인).
- 새 세션은 `git log -1 -- docs/specs/v2-dashboard/HANDOFF.md`·`git status --short` 로 7판 커밋·push 여부를 먼저 확인한다.
- **7판 0절(아래)이 우선한다.** 2절의 6판 이전 결정은 기록으로 남기고, 3절 [3] 의 6판 작업 순서는 종료했다.

## 0. 7판 요약 (2026-10-25)

- **(7판 보완 10/26 1시) 보완 배포 완료 — 이 항목이 0절 안에서 가장 우선한다.**
  - 서버 실행본 `5367334`(v1.2026.10.25.2058), tradebot 기동 10/26 00:25:22, tradebot-v2 00:24:59, 허용 목록 `mcmax33`(버튼 보임), trading_paused 0.
  - 배포 완료 보고 커밋은 문서·버전 줄이라 서버에 pull 하지 않는다. 그래서 GitHub HEAD 가 서버보다 1커밋 앞서고 버전 줄도 다르다(의도된 불일치 — 다음 세션 정지선에서 멈추지 않는다).
  - 보고: `docs/specs/v2-dashboard/deploy-report-20261026.md`. 남은 일: A′ 발송(1026-04, 운영자), 24시간 journal(1026-06), CLOCK-CLOSE 중복 조사(1026-07, 백로그).
- (7판 보완 10/26 0시, 기록) 보완 배포 승인 완료 — 새 세션이 실행했다.
  - 요청서: `docs/specs/v2-dashboard/deploy-request-20261025-2.md`(미커밋). verifier 2회 「승인 요청 가능」, Fable `docs/fable/2026-10-25-deploy-request2-1.md`(미커밋) 「진행」.
  - 배포 대상 HEAD `5367334`(v1.2026.10.25.2058). 서버 현재 `5692998`(1729), tradebot 기동 10/25 17:10:35, tradebot-v2 17:48:27, `.v2_allowlist` 0바이트(버튼 숨김), trading_paused 0.
  - **사용자 결정 1025-24(10/26): 1 한 번에(S1~S6, 멈춤 조건이 없으면 끝까지), 2 매매 중지/재개 실기 1회 시험(포지션 없음·미체결 0, 확정 봉 직후~다음 경계 60초 전 창), 3 통보 문안 A′ 초안대로 배포 확인 뒤 당일 운영자 발송, 4 E1 조건이 맞는 가장 가까운 시각·저장소 폴더 새 세션.**
  - 새 세션 순서: 시작 점검 → 요청서 2-0 정지선(이 HANDOFF 와 미추적 배포 문서가 보이는 것은 정상) → S1~S6. 부록 A(`d3_restart.sh`)·B(`explain7.sql`)는 새 세션 scratchpad 에 Write 도구로 옮겨 쓴다.
  - 끝나면 배포 완료 보고(1차+2차): deploy-report + Fable 번들 zip, 런북 쓰기 탐침 문구·계획서 6절 주석 수정, HANDOFF·요청서 2개·배포 질의서와 함께 커밋 승인(버전 갱신).
  - 이 세션 PO 규칙 위반: 10/25 빈 heredoc 2회(무해) — 질의서에 기재.

- 구현 완료 보고: `docs/specs/v2-dashboard/impl-report-20261025.md`(배포 diff 범위·버전·UI 브리핑·수용 기준 현황·배포 첫 실행 확인 항목·알려진 틈). Fable 번들 zip `docs/specs/v2-dashboard/v2-impl-report-20261025.zip`(git 무시, `.gitignore` `docs/specs/*/*.zip`).
- 진행 기록(전 과정): `.superpowers/sdd/plan/progress.md`(git 무시). Task 별 지시서·보고서·verifier 요약도 같은 폴더.
- 실측: `docs/specs/v2-dashboard/measure-20261023.md`(Task 0·7·8·10 절). 운영 문서: `docs/operations/v2-runbook.md`.
- 커밋(서버 156b351 이후 코드): dec2774(Task 1)·c6d4860(2)·02c3e0e(3)·9f6e2db(4)·194a134(5)·23569db(6)·3d985bb(7)·cfbdc3f(8)·007ee7f(9) — 모두 push 완료. 7판 커밋은 Task 10 문서.
- 사용자 결정(10/23~25): 1023-01 가·나·나(개발 서버·signals 병합·UNKNOWN 기준), 1023-05 나(게이트 node 단계 — Task 9 에서 넣음), 1023-09 가(속도 측정 방식), 1024-01 나(PULLBACK 파일 P3 4.2 18키·이력 화면 입력 19개), 1024-03 가(서버만 tp·sl·capital>0, fee≥0), 1025-04 가(로컬 실측 가짜 계정), 1025-05 「기록만 하시오. 해당 사안은 크리티컬하지 않다」(로컬 실측 중 실제 계정 값 자동 입력 사건 — impl-report §5-1 기록으로 종결), 1025-06 Task 10 문서 커밋 승인. 셸 편집 차단 훅(1023-02)은 「나중에」.
- 사용자 요구(10/24): 「로직이 정확하게 돌고 시스템 및 서비스, 로직에 문제가 없어야 한다」 — 실패 경로 시험과 브라우저 실측을 꼼꼼히.
- **(7판 보완 10/25 16시) 배포 승인 완료 — 새 세션이 실행한다.**
  - 배포 승인 요청서: `docs/specs/v2-dashboard/deploy-request-20261025.md`(미커밋). verifier 3회 「승인 가능」, Fable `docs/fable/2026-10-25-deploy-request-1.md`(미커밋) 2회째 「진행」.
  - 배포 대상 HEAD: `12ddb4f`(v1.2026.10.25.1611). 배포 전 결함(서버 params ticker "JTO" 접두 없음) 수정이 포함돼 있다.
  - **사용자 결정 1025-10(10/25): 1 가(D1~D8 한 번에 승인 — 멈춤 조건이 없으면 끝까지), 2 가(저장소 폴더 새 세션에서 실행), 3 가(재시작 조건이 맞는 가장 가까운 시각), 4 가(30분 무접속 + 운영자 1회 접속 뒤 24시간 journal), 5 가(통보 문안 A 초안대로 배포 완료 확인 뒤 당일 운영자 발송).**
  - 새 세션 순서: 시작 점검 → 요청서 2-0 정지선(이 HANDOFF 수정 1건이 미커밋 `M` 으로 보이는 것은 정상) → D1~D8 순서대로 실행. nginx 편집 스크립트(`scratchpad/deploy/nginx_add_v2.py` — 새 세션 scratchpad 에는 없으니 요청서 2-6 명세대로 다시 만든다)는 실행 전에 원문을 사용자에게 보이고 verifier 에게 검증받는다.
  - 끝나면 배포 완료 보고: deploy-report + Fable 번들 zip. 요청서·질의서·HANDOFF 를 함께 커밋 승인받는다(버전 갱신).
  - 이 세션의 PO 규칙 위반 1회(10/25 빈 heredoc, 무해)는 progress.md 에 기록했다.
- 배포 첫 실행에서 확인할 것: `systemctl show` 의 ReadWritePaths `-` 접두 유지, 빈 CapabilityBoundingSet 표기, systemd-run OOM 문구, 서버 SQLite 3.37.2 에서 -wal·-shm 없는 WAL DB ro 열기, 운영 DB EXPLAIN QUERY PLAN 7개, nginx 같은 출처 링크 클릭·https 쿠키·실제 계정·실기기 412px.

### 0-1. 지금 남은 일 (7판 기준, 모든 행)
| # | 우선순위 | 진행 여부 | 할 일 | 누가 | 언제 | 보실 곳·끝 기준 |
|---|---|---|---|---|---|---|
| 1026-06 | 3 (기다림) | 예정 (10/27 00:25 이후) | 24시간 journal 확인 | Claude | 1026-01 뒤 | 더 하실 일 없습니다 |
| 1026-07 | 3 (기다림) | 예정 (백로그) | CLOCK-CLOSE 중복 조사 | Claude | 1026-05 뒤 | 기존 동작(10/24~), 매매 영향 없음. 별도 승인 |
| 1026-02 | — | 완료 (10/26 00:55:20 중지 · 00:55:41 재개, 확인 3가지 0) | 매매 중지/재개 1회 시험 | 사용자 | 끝남 | — |
| 1026-01 | — | 완료 (10/26 · S1~S6 통과) | 보완 배포 실행 | Claude | 끝남 | — 서버 5367334·2058·tradebot 00:25:22 |
| 1026-03 | — | 완료 (10/26 00:55 · 전 항목 통과, 00:45 봉 CLOCK-CLOSE 2회는 기존 동작) | 30분 관찰 | Claude | 끝남 | 더 하실 일 없습니다 |
| 1026-13 | 2 (하는 중) | 진행 중 (10/26) | PC 차트 배포 요청서 | Claude | 1026-12 뒤 | verifier·Fable 뒤 배포 승인 요청(tradebot-v2 재시작만) |
| 1026-12 | — | 완료 (10/26 · 사용자 「1026-12 커밋·push 승인」) | PC 차트 커밋·push | Claude | 끝남 | — 버전 v1.2026.10.26.1209 |
| 1026-11 | — | 완료 (10/26 · 시험·실측·verifier 2회·Fable 진행) | PC 차트 구현·실측 | Claude | 끝남 | — impl-report-20261026-pc-chart.md |
| 1026-10 | — | 완료 (10/26 · 사용자 「1026-10 계획 승인」) | PC 차트 계획 승인 | 사용자 | 끝남 | — docs/specs/v2-dashboard/plan-pc-chart-20261026.md |
| 1026-09 | — | 완료 (10/26 · verifier 2회·Fable 2회째 진행) | PC 차트 확대 계획서 | Claude | 끝남 | — scratchpad plan-pc-chart-20261026.md, docs/fable/2026-10-26-pc-chart-plan-1.md |
| 1026-04 | 3 (기다림) | 예정 (10/26 사용자 「보류」 — PC 변경 배포 뒤) | 통보 문안 A′ 발송 | 사용자 | 1026-11 뒤 | PC 문장을 고친 문안을 배포 뒤 한 번에 보냄 |
| 1026-08 | — | 완료 (10/26 · 1 가, 2 200, 3 같이 / 1026-04 보류) | PC 차트 확대 방안 결정 | 사용자 | 끝남 | — 근거 docs/fable/2026-10-26-pc-chart-proposal-1.md |
| 1026-05 | — | 완료 (10/26 · 사용자 「1026-05 커밋·push 승인」) | 배포 완료 보고 커밋·push | Claude | 끝남 | — |
| 1025-13 | — | 완료 (10/26 00시대 · 사용자 「1025-13 확인함」) | 운영자 PC·휴대폰 확인 | 사용자 | 끝남 | — 사용 뒤 v2 RSS 31,380KB, v2 오류 0 |
| 1025-24 | — | 완료 (10/26 · 1 한 번에, 2 시험, 3 초안대로, 4 새 세션) | 보완 배포 승인 | 사용자 | 끝남 | — |
| 1025-23 | — | 완료 (10/25 · verifier 2회·Fable 진행) | 보완 배포 요청서 | Claude | 끝남 | — deploy-request-20261025-2.md, docs/fable/2026-10-25-deploy-request2-1.md |
| 1025-22 | — | 완료 (10/25 · 5367334 push) | PC 화면 구현 커밋·push | 사용자 | 끝남 | — 버전 1729 → 2058 |
| 1025-15 | — | 완료 (10/25 · 구현·실측·verifier·Fable) | 신버전 PC 화면 재구현 | Claude | 끝남 | — |
| 1025-21 | — | 완료 (10/25 · 가) | 엔진 상태 판정 방식 | 사용자 | 끝남 | — 감시 스레드, 배포 때 tradebot 재시작 1회 |
| 1025-20 | — | 완료 (10/25 · 1 승인, 2 「구버전과 같은 동작 정확히 — 다시 제안」) | 계획 승인·엔진 상태 | 사용자 | 끝남 | — |
| 1025-19 | — | 완료 (10/25 · 1 가, 2 나) | 매매 중지 방식·모바일 | 사용자 | 끝남 | — |
| 1025-18 | — | 완료 (10/25 · 최종 정정: 모바일 그대로, PC 는 원본 구역 + 기본 기능) | PC 구역 범위 | 사용자 | 끝남 | — |
| 1025-16 | — | 완료 (10/25 · 사용자 정정으로 취소, 반영 없음) | 가운데 480px 안 | 사용자 | 끝남 | — 로컬 수정 되돌림 |
| 1025-17 | — | 완료 (10/26 · 1026-08 3 「같이」, 1026-11 에 포함 — 배포 전) | 정적 파일 Cache-Control | Claude | 끝남 | — v2/handlers.py StaticHandler no-cache |
| 1025-14 | — | 완료 (10/25 · 1 숨김, 2 그림, 3 가운데 폭, 범위 PC 만) | 화면 불일치 처리 결정 | 사용자 | 끝남 | — 서버 허용 목록 18:41:55 비움(재배포 때 D7 다시 수행) |
| 1022-05 | 2 (하는 중) | 진행 중 (10/26 · 2차 배포 끝, 완료 보고는 1026-05) | 배포 실행·완료 보고 | Claude | 1026-05 뒤 | — |
| 1025-12 | — | 완료 (10/25 · 5692998 push·서버 반영) | ProtectHome 수정 커밋·반영 | 사용자 | 끝남 | — |
| 1025-11 | — | 완료 (10/25 · 1 가, 2 가) | D5 FAIL 처리 방법 | 사용자 | 끝남 | — (가: ProtectHome=read-only 수정 뒤 이어서 배포, 엔진 재시작 없음) |
| 1023-02 | 3 (기다림) | 예정 (사용자 답: 나중에) | 셸 편집 차단 훅 | 사용자 | 1022-05 뒤 | — |
| 1025-10 | — | 완료 (10/25 · 1~5 가) | 배포 승인 | 사용자 | 끝남 | — |
| 1025-09 | — | 완료 (10/25 · 12ddb4f push) | 결함 수정 push | Claude | 끝남 | — |
| 1025-08 | — | 완료 (10/25 · 12ddb4f) | 결함 수정 커밋 | Claude | 끝남 | — |
| 1025-07 | — | 완료 (10/25 · 5d4be71 push) | Task 10 문서 push | Claude | 끝남 | — |
| 1025-06 | — | 완료 (10/25 · 7판 커밋) | Task 10 문서 커밋 | Claude | 끝남 | — |
| 1025-05 | — | 완료 (10/25 · 기록만) | 실측 사건 처리 | 사용자 | 끝남 | — |
| 1025-04 | — | 완료 (10/25 · 가) | 로컬 실측 진행 방식 | 사용자 | 끝남 | — |
| 1025-03 | — | 완료 (10/25 · 007ee7f push) | Task 9 push | Claude | 끝남 | — |
| 1025-02 | — | 완료 (10/25 · 007ee7f) | Task 9 커밋 | Claude | 끝남 | — |
| 1025-01 | — | 완료 (10/25 · cfbdc3f push) | Task 8 push | Claude | 끝남 | — |
| 1024-01·02·03 | — | 완료 (10/24~25) | 저장 형식·Task 8 커밋·하한 | 사용자 | 끝남 | — |
| 1023-01·03~10 | — | 완료 (10/23) | Task 5~7 결정·커밋·push | — | 끝남 | — |
| 1022-01~04·06 | — | 완료 (10/22) | 계획·실측 | — | 끝남 | — |

## 1. 세션 시작 방법

일반 터미널에서 실행한다. 반드시 프로젝트 폴더에서 시작한다(핸드북 규칙 1).

```
cd "/Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp" && claude-thetak
```

첫 메시지로 아래 한 줄을 보낸다.

```
docs/specs/v2-dashboard/HANDOFF.md 를 읽고 그대로 시작하라.
```

## 2. 지금까지 확정된 것

### 2026-10-21
- 투자자 승인 완료: 승인 요청서 v2 PDF, 5개 항목 전부 승인, 의견 없음 (`docs/operations/investor-notice-log.md` #5, 커밋 `bfeae37`)
- spec 결정 D1~D7 (spec 3절)

### 2026-10-22 운영자 결정 (2판, spec 반영 완료)
- R4: 신버전은 별도 systemd 서비스 `tradebot-v2`.
- R7: 1차(P1·P2) 백테스터 데이터는 Binance만. 업비트 칸은 「준비 중」.
- D8: 신버전은 서버에서 업비트 API(시세·계좌)를 부르지 않는다.
- 차트는 투자자 브라우저가 업비트 공개 시세를 직접 호출(30초 갱신). 잔고·포지션은 DB 기록 + 기록 시각.
- 검증 역할 `.claude/agents/verifier.md` 신설.

### 2026-10-22 사용자 결정 (3판, spec 3.1절 E1~E14 반영 — 미커밋)
| # | 결정 |
|---|---|
| 결정 1 → E1 | 1차 배포 때 입장 버튼과 함께 `tradebot` 1회 재시작 + `journalctl -u tradebot` 봉 누락 확인 |
| 결정 2 → E2 | v2 전용 경량 DB·설정 모듈(config·streamlit·pyupbit import 없음, 키 미로드) |
| 결정 3 → E3 | 「엔진 동작」 = `audit_buy_eval` 최신 시각·`accounts.updated_at`(LIVE) 경과 시간 |
| 결정 4 → E4 | 차트 MA200 1차 제외 |
| 결정 5 → E5 | 평가손익 현재가 = 엔진 기록 가격 + 기록 시각 |
| 결정 6 | spec 옛 문구 정리·P4 엔진 제어 재설계(4.7: 신버전은 요청 기록만, 엔진 프로세스가 실행) — 완료(미커밋) |
| 결정 7 | `CLAUDE.md` 「에이전트 운용」·「축적된 규칙」 절 추가 — 완료(미커밋) |
| Q1 → E6 | 60초 1회용 서명 토큰. 「구버전으로」는 재로그인 |
| Q2 → E12 | 빈 봉 규칙 정정은 P3 spec·계획에서 |
| Q3 → E7 | 설정 파일 `{user}_latest_params_PULLBACK.json` (pullback spec 4.2 도 같이 고침) |
| Q4 → E8 | settings_history 허용 목록 확장 + 구버전 이력 화면 회귀 시험 |
| Q5 → E9 | 「저장만 하기」 TEST/LIVE 구분 없음 |
| Q6 → E10 | 1차 운용 메뉴는 **표시만**(버튼 비활성 「2차 공개 때 열림」, 상태 읽기). 사용자가 한때 「1차부터 실제 동작」을 골랐다가 「너무 복잡해진다」며 권고안으로 되돌림 |
| Q7 → E11 | tornado (서버 설치 6.5.1) |
| W2 → E13 | Binance 결과는 「저장만」 유지. P3 엔진 봉 기록은 워밍업 확정 봉도 기록하는 안으로 설계. 전환 여는 기준은 P3 계획에서 |
| 사용자 요구 → E14 | **백테스트 실행은 원본 HTML처럼 빠르게 끝나야 한다.** A6 에 실행 시간 측정 추가 (PO 해석. 사용자가 다른 뜻이라고 하면 고친다) |

### 2026-10-22 사용자 결정 (4판, spec 3.2절 E15~E19 반영)
| # | 결정 |
|---|---|
| 결정 1 (c2) → E15 | 1차 신버전 이력은 별도 파일 `services/data/v2hist_<user>.db`. 실매매 DB 는 읽기만, 구조 변경 없음. 기존 `settings_history`·허용 목록·CHECK 는 1차에서 바꾸지 않음 |
| 결정 B (a) → E15 | `v2hist` 는 별도 cron 줄로 백업(기존 `/root/cleanup_tradebot_db.sh` 무변경, 백업본 600) |
| 결정 3 → E16 | 구·신 이력은 따로 관리, 각 대시보드는 자기 이력으로 전략 추정. 화면 현재 전략 배지는 `{user}_active_strategy.txt`. **P3 선행 조건:** 엔진 PULLBACK 기동 시 이력 기록 위치(지금 코드는 `_validate` 에서 거부 → 경고만, 거래 이력 id NULL) |
| 결정 2 (a) + 결정 A (a) → E17 | 「엔진 동작」= 매수·매도 판단 기록 최신 `timestamp`(+ LIVE 잔고 기록 보조). 무거래 봉은 기록이 없으므로 임계는 1단계 실측 뒤 계획서에서. 화면은 「마지막 판단 N분 전」 + 정상·지연·판단 불가 |
| 결정 4 (a) → E18 | 신버전 root 실행 + `ProtectSystem=strict`·`ReadWritePaths=-`(`services/data/`, PULLBACK params)·`InaccessiblePaths=-`(키 파일 3개)·`NoNewPrivileges`·`UMask=0077`, 후보 `CapabilityBoundingSet=`. 남는 위험 2건(엔진 환경변수, 실DB 파일 쓰기)은 코드로 막고 A17 실측 |
| 결정 5 (a) → E19 | 백테스트 속도는 계산 시간 중앙값 +20% 이내, 데이터 받기는 요청 수·봉 수 동일 |

### 2026-10-22 사용자 결정 (6판)
| # | 결정 |
|---|---|
| 1 = 가 | plan.md 대로 구현 시작 승인 |
| 2 = 가 | 실행 방식 **subagent-driven** (Task 마다 실행 에이전트, PO 검수. 실행 에이전트에 plan.md 머리 「금지 행위」 그대로 전달) |
| 3 = 가 | Task 0 Step 2 서버 점검 스크립트 실행 승인. 단 PO 가 「실행 전 원문을 먼저 보여 드린다」고 약속했으므로, 새 세션은 실행 직전 스크립트 요지를 보여 주고 「실행」 답을 받은 뒤 돌린다 |
| 지시 | 「새로운 세션에서 실행할 수 있도록 준비 후 보고」 → 이 6판 |

### 2026-10-22 Task 0 실측 결과 (6판, 읽기 전용 — 예외 1건: 서버 `/dev/shm/x` 생성 후 즉시 삭제, measure 「journal 건수」 절)
- 기록: `docs/specs/v2-dashboard/measure-20261023.md`(Step 1~6 기록 완료, Step 7 커밋 대기). Step 1 정지선 일치, Step 3 import RSS 28,568 KB(`MemoryMax` 150M 유지), Step 4 권한(DB·params·active_strategy 모두 644 root, `/root` 700), Step 6 cron `0 11 * * 0 /root/cleanup_tradebot_db.sh`, journal 7일 `CONFIRMED-NO-TRADE` 759·`봉 처리 완료` 2,521(21:48 무렵 창, Step 2 와 같은 창 재집계 770·2,510 은 measure).
- 관찰: 측정 시점에 실매매 DB `tradebot_mcmax33.db` 의 `-wal`·`-shm` 이 없었다. 엔진은 연결마다 WAL 로 열고 닫으므로(`services/db.py:39-42`) 마지막 연결이 닫히면 두 파일이 사라지는 정상 상태다. WAL 에서 읽기는 엔진 쓰기를 막지 않는다. (6판 초안의 저널 모드 오기를 Fable 지적으로 정정함 — `docs/fable/2026-10-22-handoff6-1.md`.)
- Step 2 스크립트: `scripts/v2/v1_probe.py`(2026-10-22 22:58 실행, 결과는 measure Step 2 절). plan Task 0 Step 2 는 scratchpad 보관이었으나 세션 교대로 새 세션이 볼 수 있게 저장소에 둔다(`scripts/v2/` 는 plan Task 9 가 정한 위치).

### 2026-10-22 보고·진행 방식 (사용자 지시)
- 이후 모든 보고는 claude-studio 규칙의 양식을 따른다: `/Users/gonnim/GON-Dev/claude-studio/agents/po.md` 「보고 양식」(결론 / 한 것·확인한 것·남은 것 / 결정해 주실 것 / 산출물), Fable 질의서·답변서는 po.md 「질의서 양식」·`fable-advisor.md` 「답변 양식」.
- Fable 질의 규칙(세션 시작 훅이 넣음)을 지킨다. 파일 쓰기·커밋·결정 요청·단계 넘김 직전마다 Fable 판정 「진행」을 받는다. 같은 단계 재질의 2회 뒤에도 「진행」이 아니면 멈추고 사용자에게 묻는다.
- Fable 호출: 프로젝트에 fable-advisor 역할이 없으므로 Agent 도구 `model: "fable"` + `fable-advisor.md` 본문을 프롬프트 앞에 붙인다. 질의·답변은 `docs/fable/YYYY-MM-DD-<단계>-<번호>.md`(po.md 23행·세션 시작 훅 규칙의 경로). po.md 22행은 fable-advisor 역할이 없으면 멈추라고 하지만, Agent `model: "fable"` 방식은 세션 시작 훅 규칙 [3]이 정한 대안이고 2026-10-22 세션에서 이 방식으로 진행했다. 프로젝트에 역할 배치는 백로그.
- 같은 지시를 `CLAUDE.md` 「축적된 규칙」에도 적었다. 메모리 저장은 사용자 허용 전이라 하지 않았다(핸드북 규칙 3).

## 3. 새 세션이 할 일

핸드북(`/Users/gonnim/Downloads/Bot/GONNIM 에이전트 운용 핸드북 · 모든 프로젝트 공통 인수인계서.md`)을 숙지한 뒤 시작한다.

### [0] 세션 시작 체크리스트 + 정지선

`.claude/context/project-rules.md`의 「세션 재개 표준 정지선」을 따른다. 결과는 표 하나로 보고한다.

- `pwd`가 git 최상위 폴더와 같은지, `CLAUDE_CONFIG_DIR`이 `~/.claude-thetak`인지.
- 로컬: HEAD 와 커밋 여부. 6판 기대값은 둘 중 하나다.
  - (가) 6판이 커밋·push 됨: HEAD = `origin/main` = 6판 커밋(`git log -1 -- docs/specs/v2-dashboard/HANDOFF.md`, 부모 `0e72cf5`), 추적 파일 미커밋 0건.
  - (나) 6판 미커밋: HEAD = `origin/main` = `0e72cf5`, 변경 — `M docs/specs/v2-dashboard/HANDOFF.md`, `?? docs/specs/v2-dashboard/measure-20261023.md`, `?? scripts/v2/`(`v1_probe.py`), `?? docs/fable/2026-10-22-handoff6-1.md`, `?? docs/fable/2026-10-22-handoff6-2.md`, 보완으로 `?? docs/fable/2026-10-22-step2-run-1.md`(그 뒤 Step 7 질의 파일도 추가). 이 파일들은 지우지 말고 Task 0 Step 7 커밋에 함께 넣는다(커밋은 승인 뒤).
  - 커밋됐는데 push 가 안 됐으면 HEAD 가 origin 보다 1커밋 앞선다.
- 서버(SSH 읽기 전용): HEAD `156b351`, `dashboard.py` v1.2026.10.20.1711, `tradebot` active, 기동 2026-10-20 17:40:51, `tradebot-v2` 없음, `.env`·`.streamlit/secrets.toml` 600, 사본 없음. 서버 미추적 5건(`check_all_balances.py`, `check_balance.py`, `check_pepe.py`, `sync_balances.py`, `mcmax33.sqlite3`)은 손대지 않는다.
- `verifier` 에이전트가 사용 가능한 목록에 보이는지.
- 로컬 미추적 13건은 건드리지 않는다: JTO 분석 문서 4개, `tests/test_*.py` 7개, `__pycache__` 2개.
- 기대값과 하나라도 다르면 STOP.

### [1] 읽을 파일

- `docs/specs/v2-dashboard/spec.md` — 3.1절 E1~E14, 3.2절 E15~E19 반영본
- `docs/specs/v2-dashboard/plan.md` — 구현 계획서(Task 0~10, 배포 절, 수용 기준 표) ⭐ 시작점
- `docs/specs/v2-dashboard/review-20261022-plan-draft.md` — 계획서 검증 보고(verifier 4회)
- `docs/specs/v2-dashboard/plan-outline-v3.md` — 목차 3판(2026-10-22 사용자 승인, C1~C5 대응표)
- `docs/specs/v2-dashboard/review-20261022-outline-v3-draft.md`, `review-20261022-outline-v3-recheck.md` — 3판 검증 보고
- `docs/specs/v2-dashboard/review-20261022-outline-v2.md` — 2판 검증 보고(지적 1~16)
- `docs/specs/pullback-strategy/spec.md` — P3
- `docs/fable/2026-10-22-*.md` — 이번 결정 과정의 Fable 질의서·답변서(각 파일 끝 「Fable 답변서 전문」 절)
- `.claude/agents/verifier.md`, `/Users/gonnim/GON-Dev/claude-studio/agents/po.md`, `/Users/gonnim/GON-Dev/claude-studio/agents/fable-advisor.md`
- 필요할 때만: 원본 백테스터 `docs/specs/MA60_200_GoldenCross_Pullback_Backtester_2610201820.html`의 `simulate()`(246~383행)

### [2] 결정 대기

없음. (결정 1~7·Q1~Q7·3차 결정 1~5·A·B 확정. 목차 3판 승인과 아래 [3]의 각 단계 승인은 따로 받는다.)

### [3] 이번 세션 작업 순서

1~4. (2026-10-22 완료) 미커밋 커밋 `ee6efc4`·push, review 2판 4절 「결정 완료」, 목차 3판 작성·verifier 3회·Fable, 3차 결정 반영(spec 3.2).
5~6. (2026-10-22 완료) 목차 3판 사용자 승인·커밋 `0ae470c`, plan.md 작성·verifier 4회·Fable.
7. (2026-10-22 완료) plan.md 실행 승인, 실행 방식 subagent-driven, Task 0 Step 2 실행 승인.
8. Task 0 이어서:
   - 8-1. (2026-10-22 22:45 완료) 정지선 재실행([0]) — 기대값과 모두 같음.
   - 8-2. (2026-10-22 22:58 완료) Step 2: 사용자 지시로 서버에 복사하지 않고 `ssh root@orionhunter7.cafe24.com '/root/upbit-tradebot-mvp/venv/bin/python -I -' < scripts/v2/v1_probe.py` 로 1회 실행했다(exit=0). Fable 진행(`docs/fable/2026-10-22-step2-run-1.md`).
   - 8-3. (2026-10-22 완료) 결과 표와 `DELAY_FACTOR` 3·`UNKNOWN_SEC` 1800 제안(계획 기본값 유지)을 `measure-20261023.md` Step 2 절에 적었다.
   - 8-4. verifier → Fable 질의 → 사용자에게 Step 7 커밋(문서·점검 스크립트, 버전 유지) 승인 요청. (나) 상태면 6판 5건과 `docs/fable/2026-10-22-step2-run-1.md`·Step 7 질의 파일도 이 커밋에 넣는다. LIVE 판단 기록·잔고 시각 결합 규칙은 미정이며 Task 4 착수 전 결정 항목이다(measure Step 2 관찰). `scripts/v2/v1_probe.py` 는 코드가 아닌 점검 스크립트라 엔진이 읽지 않는다 — 버전 갱신 대상인지 질의서에 적는다.
9. Task 1 부터 subagent-driven(superpowers:subagent-driven-development)으로 진행한다. 「사용자 확인 후」 Step(`pip install`, 외부 내려받기)과 모든 커밋은 각각 승인받는다. 실행 에이전트에게는 plan.md 머리의 「금지 행위」를 그대로 전달한다.
10. PO 결정(2026-10-22, spec 범위 안 구현 선택 — 사용자가 바꾸라면 바꾼다): 토큰은 버튼을 누를 때 발급(E6 60초 유지), Python v2 시험을 회귀 게이트 단계로, 로그 API `WHERE user_id=? ORDER BY timestamp DESC`.

### [4] 금지와 주의

- 파일을 쓰기 전에 목록과 요지를 보여 준다. 기존 파일은 diff를 먼저 보여 준다.
- 커밋, push, 배포, 서버 설정 변경은 각각 따로 승인받는다.
- 여러 줄 텍스트는 파일 도구(Write·Edit)로만 쓴다. 셸 heredoc 은 빈 것도 쓰지 않는다 (2026-10-22 세션에서 4회 위반, 모두 무해. 3판 세션의 1회는 `python3 - <<'X'` 빈 본문, 6판 보완 세션의 1회는 질의서 문자열 고침을 `python3 - <<'X'` 로 실행).
- 커밋마다 `dashboard.py` 버전을 갱신한다(project-rules 커밋 전 2단계 — 문서 예외 없음, 2026-10-26 Fable deploy-report-1 정정). 문서 커밋을 서버에 pull 하지 않으면 보고에 서버 실행본 버전을 따로 적는다.
- 키 값은 대화에도 문서에도 적지 않는다.
- 확인하지 못한 것은 「미확인」으로 적는다. 검증 보고의 「반박됨」을 고치지 않은 채 사용자에게 올리지 않는다.
- 사용자 답이 템플릿 그대로이거나 두 가지로 읽히면 확정하지 않고 다시 묻는다(Q6 사례).
- Fable 판정 「진행」 전에는 파일을 쓰지 않는다. 「수정 후 진행」은 고친 뒤 다시 질의해 「진행」을 받는다 (2026-10-22 1회 위반: CLAUDE.md 1줄, 무해).

## 4. 넘겨받는 백로그

- (7판 추가) 알려진 틈·이월 — 상세는 impl-report §7: v2 root 라 /etc/shadow·/root/.ssh 읽기 가능(InaccessiblePaths 다음 판 검토), A3 「기동 예외 주입」·A18 이력 화면 회귀 시험 없음, P3 PULLBACK 로더(깨진 JSON·flock·tp 등 값 검증), pullback spec 107행·4.2 100행 정정, `.gitignore:80` 이 __pycache__ 무시를 되돌림, 구버전 「로그아웃하기」 뒤 쿠키 재로그인(기존 동작)

- 엔진에 업비트 429·418 처리가 없다(`core`·`engine`·`services` grep 0건, 시세 호출 지점 27곳). v2와 무관한 기존 잠재 결함
- 8501이 외부에 평문 HTTP로 열려 있다(nginx 우회 가능, ufw 비활성)
- `docs/operations/server-optimization.md:35` candle_cache 기재 정정 — 서버 DB 4개 모두 테이블 없음
- 서버 `services/data/tradebot_.db`(빈 user_id DB) 출처 조사 — `engine/boot_resume.py:54` glob 대상
- 서버 미추적 5건(`check_*.py` 3, `sync_balances.py`, `mcmax33.sqlite3`) 출처 조사 (2026-10-22 신규)
- 휴대폰 브라우저 업비트 직접 호출(1단계 V2), 승인 요청서 PDF 휴대폰 렌더 — 미확인
- 핸드북 「알려진 함정」 추가 제안 1건(2026-10-21 운영자 계정 오지정). 핸드북 원본 위치를 먼저 정해야 한다
- 프로젝트에 po·fable-advisor 역할 배치(`/project-intake`) 제안 — 승인 전 만들지 않음
- 서버 `/root/upbit-tradebot-mvp/_active_strategy.txt`(빈 사용자 이름) 출처 조사 — `tradebot_.db` 와 같은 유형 (2026-10-22 신규)
- P3 선행 조건: 엔진 PULLBACK 기동 시 이력 기록 위치(E16), 엔진 주기 기록(heartbeat) 검토(E17), 허용 목록·CHECK 확장 여부(선례 `services/init_db.py:508-545`)
- 서버 감시 스크립트 `/root/watchdog_tradebot_engine.sh` 도 journal `Bar#` 600초 기준이라 무거래 봉에 같은 약점 (2026-10-22 verifier 관찰)
- 세션 중 DB 를 여는 조회(`sqlite3 -readonly` 포함)는 서버 `-wal`·`-shm` 을 만든다. 검증 역할에는 「서버 DB 열기 금지」를 기본으로 적는다
- 서버 DB·params·active_strategy 파일이 644 다. 비밀 파일 규칙(600) 대상은 아니나 거래 기록이 들어 있다. `/root` 700 이라 다른 계정 접근 경로는 없다 (2026-10-22 신규 관찰, 조치 여부는 운영자 결정)

## 5. 시작 후 확인할 점

| 시점 | 확인할 것 |
|---|---|
| 첫 보고 | 정지선 표, 미커밋 변경 목록, 보고 양식이 po.md 「보고 양식」인지 |
| 기대값이 다를 때 | STOP 하고 묻는지 |
| 파일 쓰기·결정 요청 전 | Fable 판정 「진행」을 받았는지, 질의 파일 경로를 「확인한 것」에 적는지 |
| 목차 3판 | 사용자에게 올리기 전에 `verifier` 재검증과 Fable 질의를 거치는지 |
