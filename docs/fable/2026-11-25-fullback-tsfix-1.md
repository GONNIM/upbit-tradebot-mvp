# Fable 질의 — 1121-03 ㉠ 추적 손절 기록 글 고침: 커밋·배포 직전 (1회째)

## 질의서

- 단계: 구현·verifier 끝 → 커밋·push → tradebot-v2 재배포 직전. 배포는 되돌리기 어려운 일이라 이 질의에 묶어 묻는다. 사실·실현 가능성·위험만.
- 작업 폴더: worktree wt-1121-03 (HEAD 8cd5285 = origin/main = 서버 b97b7eb + 문서 1커밋)
- 규칙: CLAUDE.md, .claude/context/project-rules.md

### 받은 사용자 결정
| # | 결정 | 근거 |
|---|---|---|
| 1 | 1121-03 배포 승인 | 11/25 「진행」 → 11:41:59 배포함(b97b7eb · v2 만) |
| 2 | 화면 확인을 Aside 로 · 항목별 보고 | 11/25 사용자 지시 |
| 3 | ㉠ 코드 고침(칸 없음=끔, 추적 손절 3키는 「외 n개」에 안 넣음) + 대시보드 재배포 | 11/25 「1121-03 ㉠ 권고대로」 |

### 지금까지 확인한 사실
| # | 사실 | 확인/추정 | 근거 |
|---|---|---|---|
| 1 | Aside 화면 확인: 요청 10개 중 9개 맞음, ㉣ 「켬→없음」·「외 1개」 다름 | 확인 | docs/new-version/claim/ver9/screen-check-1121-03-20261125.md |
| 2 | 변경: v2/api_read.py(TS_KEYS · params_change_text) · 시험 1개 · dashboard.py:527 2342→1217 | 확인 | git diff (3파일 +45/−4) |
| 3 | 서버 실제 PARAMS 7줄을 새 코드로: 05:05 「… 추적 손절 켬→끔 · 다음 봉부터」 · 05:08 「… 끔→켬 · 추적 손절 방식 고정폭 · 손절폭 30% · 다음 봉부터」 · 11/21 16:09 「끔→켬 …」 · 나머지 4줄 그대로 | 확인 | scratchpad params_notes.jsonl(서버 읽기 전용) · render_notes.py |
| 4 | 엔진: ts_on 없음=끔(core/strategy_pullback.py:509) · 3키는 모두 있거나 모두 없음(params_schema 118-124, pullback_params valid_trailing) | 확인 | verifier |
| 5 | 게이트 v2 559 OK · JS 235 · NETGUARD 0 · engine/core/services 변경 0 · 엔진은 v2.api_read 를 가져오지 않음 | 확인 | scratchpad/gate_1121i.log · verifier |
| 6 | verifier: 주장 8/8 확인 · 지적 = 옛 Streamlit 버전 표시는 엔진 재시작 없으면 2342 로 남을 수 있음(파일 기준 3점 일치), 배포 뒤 화면 확인 필요 | 확인 | verifier 보고 |
| 7 | 서버 지금: HEAD b97b7eb · v2 11:41:59 · 엔진 11/19 13:06:12 · 오류 0 | 확인(11:4x) | deploy·post 출력 |
| 8 | 안내 초안 9번 예시가 새 글과 같음 · 안내는 아직 안 보냄 | 확인 | investor-notice-1121-03.md:24 |

### 다음에 하려는 일
1. 커밋(api_read.py · 시험 · dashboard.py · screen-check 보고서 · 이 질의 파일) → push(pre-push 게이트) → origin/main = 새 커밋.
2. deploy 스크립트를 FROM=b97b7eb(서버)·TO=새 커밋·EXPECT=바뀐 파일 목록으로 바꿔 Claude 가 ssh 직접 실행: 점검(HEAD·깨끗함·origin/main·파일 목록) → pull --ff-only → tradebot-v2 만 재시작 → 엔진 기동 시각 그대로·v2 상태·오류 확인. 되돌리기: b97b7eb 로 reset·v2 재시작.
3. 서버 감사 로그 글을 서버 코드로 다시 만들어 05:05·05:08 줄 확인 → Aside 로 화면 한 번 더(로그 탭만) → 사용자에게 안내 발송 요청.

### 물음
- 배포·고침에 사실 오류나 빠진 위험(반쪽 배포·엔진 영향·투자자 오해·되돌리기)이 있는가? 사용자에게 물어야 할 것은?

## 답변

### 1회째 답 (요지)
- 판정: 진행 — 서버 7줄을 직접 다시 만들어 사실 3 확인 · diff 3파일 · 엔진이 v2.api_read 를 가져오지 않음 · 단위 시험 42 OK · 게이트 1472/1472 · DB·파일 쓰기 없음 · 되돌리기 가능
- 권고(반영): ① deploy 스크립트 FROM/TO/EXPECT 새 값(8cd5285 문서 2개 포함) ② rollback 대상 c3e5d80 → b97b7eb ③ 버전 「구 → 신」 · 옛 Streamlit 표시는 엔진 재시작 없어 2342 로 남을 수 있음(파일 기준 3점 일치) ④ 안내 2번 CSV 단추 문장을 화면대로 · 근거 커밋 줄 ⑤ 화면 확인 보고서에 사용자 결정 줄 ⑥ 배포 뒤 7줄 모두 대조 ⑦ 「새 설정 n개」에 추적 손절이 가려질 수 있음(범위 밖, 기록만)
- 사용자에게: 없음(결정 3 원문 인용)
