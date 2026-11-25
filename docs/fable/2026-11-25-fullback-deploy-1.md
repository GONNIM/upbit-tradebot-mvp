# Fable 질의 — 1121-03 배포 승인 요청 전 (1회째)

## 질의서

- 단계: 커밋 끝 → 사용자 배포 승인 요청 직전. 배포는 되돌리기 어려운 일이라 따로 묻는다. 사실·실현 가능성·위험만.
- 계획: docs/plans/2026-11-21-fullback-requests/plan.md (3절 7단계 배포 · 7절 실제 파일 목록 · 4절 위험)
- 배포 대상: main b97b7eb (e86aae3 + 안내 문구 정정). 서버 HEAD c3e5d80.
- 안내 초안: docs/new-version/claim/ver9/investor-notice-1121-03.md
- 규칙: CLAUDE.md, .claude/context/project-rules.md (배포 승인 · 버전 「구 → 신」 · 3점 일치 · 관찰 로그 출처 journalctl)

### 받은 사용자 결정
| # | 결정 | 근거 |
|---|---|---|
| 1 | 계획 승인 · 남는 위험 받아들임 | 「1121-03 ㉠㉡ 권고대로」 11/24 |
| 2 | 커밋 승인 · ㉠(추적 손절 이름표) 적용 | 「1121-03 커밋 승인 · ㉠ 적용」 11/25 |
| 3 | 1122-01 배포 순서(권고 화면 먼저)는 답 없음 — 1122-01 은 커밋 안 됨(작업 폴더에만) | 사용자 답 대기 |

### 지금까지 확인한 사실
| # | 사실 | 확인/추정 | 근거 |
|---|---|---|---|
| 1 | 서버(11/25 사용자 `!` 읽기): HEAD c3e5d80 · tradebot 기동 11/19 13:06:12 · 매도 판단 2960행 · 1200행 창 11/07 04:57~11/24 18:03 · 잠정 봉 행 0(전체 0) · 같은 봉 여러 행 0 · avg 있는 행 953 · PULLBACK_SYNC 는 wallet_more 1행뿐(wallet_zero 0) · HTS_SELL 10행(마지막 11/11) · 마지막 체결 11/24 18:03 SELL(보유 없음 추정) | 확인 | scratchpad/fullback_read3.sh 출력 |
| 2 | c3e5d80..b97b7eb 바뀐 파일 20개 = 12be97c(docs: investor-notice-log.md·HANDOFF) + 1121-03 18개. engine·core·services·scripts 0. 계획 7절 목록(v2 8 · 시험 6 · 문서 · pages/dashboard.py · 연락 기록·HANDOFF·Fable)과 일치 | 확인 | `git diff --name-only c3e5d80 b97b7eb` |
| 3 | 화면 안내 문구 「약 60시간」이 틀려(행은 보유 중에만 쌓여 창이 약 17일) b97b7eb 로 고침. 게이트 v2 558·JS 235·회귀 1472·NETGUARD 0 | 확인 | scratchpad/gate_1121g.log |
| 4 | 버전: v1.2026.11.22.1721(서버) → v1.2026.11.24.2342 | 확인 | pages/dashboard.py:527 |
| 5 | verifier 4회(최종 승인) · 구현 Fable 2회(최종 진행). b97b7eb 문구 정정은 verifier 안 거침(문구 1줄·버전·계획 메모) | 확인 | docs/fable/2026-11-25-fullback-impl-1.md |
| 6 | pages/dashboard.py 는 옛 Streamlit 화면 파일 — 버전 줄만 바뀌고 tradebot(엔진) 재시작 없이 둔다(c3e5d80 배포 때와 같은 방식) | 추정(11/22 배포 보고 기록) | 12be97c 커밋 메시지 「v2 17:38:21 · 엔진 그대로」 |
| 7 | 작업 폴더(main 체크아웃)는 12be97c 에 1122-01 고침이 커밋 안 된 채 있음 — 서버 배포와 무관 | 확인 | git status |

### 다음에 하려는 일 (배포 승인 받으면)
1. 사용자 `!` 로 배포 직전 읽기: 서버 HEAD c3e5d80 확인 · `git -C /root/upbit-tradebot-mvp fetch` 뒤 `git diff --name-only HEAD origin/main` 이 사실 2 목록과 같은지 · `git status --short` 비었는지 · 적용본 sha · tradebot-v2 기동 시각.
2. 같으면 `git pull --ff-only` → `systemctl restart tradebot-v2` 만 → 3점 일치(로컬·서버 HEAD b97b7eb · 버전 2342 · tradebot ExecMainStartTimestamp 11/19 13:06:12 그대로 · tradebot-v2 새 기동 시각) · `systemctl show tradebot-v2 -p MemoryCurrent` · `journalctl -u tradebot-v2 --since` 오류 확인. SSH 명령은 사용자 `!` 로 실행(읽기·배포 스크립트 파일로).
3. 사용자 화면 확인 5항목 → 안내 발송(사용자) → 연락 기록 #21 → 1시간 관찰.

### 물음
- 배포에 사실 오류·빠진 위험(반쪽 배포·엔진 영향·투자자 오해·되돌리기)이 있는가? b97b7eb 문구 정정을 verifier 없이 배포에 넣어도 되는가? 안내 초안에 틀린 말이 있는가? 사용자에게 물어야 할 것은?

## 답변

### 1회째 답 (요지)
- 판정: 진행 — 엔진 읽는 파일 0(20개 직접 확인) · 안내 초안 1~9 코드와 대조해 틀린 말 없음 · b97b7eb 은 문구 1줄·버전·메모뿐이라 verifier 없이 됨 · 정적 파일 no-cache · 되돌리기 가능(DB·파일 쓰기 없음)
- 권고 6(반영): 안내 5번 종목·봉 단위·출처(반영) · 8번 기록 범위 밖 보유(반영) · 되돌리기 절차를 승인 요청에(scratchpad/rollback_1121.sh) · 배포 직전 origin/main=b97b7eb 확인(deploy_1121.sh 에 넣음)·문서 커밋은 배포 뒤 · 화면 확인에 백테스트 1회·적용 뒤 줄 수·단계 줄 수 · 사실 6 확인으로
- 사용자에게: 배포 승인(b97b7eb · v2 만 · 버전 1721→2342) · 사용자 `!` 실행 · 배포 뒤 화면 확인과 안내 발송 · 1122-01 순서는 계획 기본(화면 먼저)대로
