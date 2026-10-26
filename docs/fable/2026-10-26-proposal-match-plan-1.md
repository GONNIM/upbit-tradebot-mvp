# 질의: 신버전 1차 화면을 승인 요청서 v2 그림과 같게 만드는 계획서 — 사용자 승인 요청 전

**지금 단계:** 계획 (사용자 승인 요청 직전)
**다음에 하려는 일:** 계획서를 사용자에게 올려 승인을 받습니다. 승인되면 Task 1~9 를 구현·검증하고 보고합니다(커밋·배포는 각각 따로 승인). 이번 단계의 파일 쓰기는 계획서·이 질의서뿐이며, 둘 다 다음 문서 커밋에 묶습니다(작은 문서 변경 묶음). 저장소에 `.claude/hooks/` 가 없어 훅 차단 대상 명령은 없습니다.

## 지금까지 확인한 사실
| # | 사실 | 근거 |
|---|---|---|
| 1 | 사용자 지시: 승인 요청서 v2 와 똑같이 모바일·PC, 기존 요구 모두 폐기, 요청서 내용(1차+2차)은 구현되어야 함. 결정 1026-19: 1 가·2 가·3 가·4 가·5 나 | 이 세션 사용자 메시지, docs/fable/2026-10-26-proposal-match-scope-1.md |
| 2 | 계획서는 1차 화면(그림 1-나·2-가~2-마·5-가·5-나)만 다루고 2차는 다음 계획 | 계획서 Spec 줄 |
| 3 | verifier 1회째 「승인 요청 불가」(반박 5·누락 8) → 모두 반영 → 2회째 「승인 요청 가능」, 개선 3건(매수 대기 묶기·네트워크 오류 1회 재시도·대문자) 반영 | verifier 보고 2회(이 세션) |
| 4 | 그림 속 숫자는 예시 값(요청서 0절) → 개수·종목·봉 단위는 실제 값 | approval html:131 |
| 5 | 엔진 경로 변경 0, 서버 업비트 호출 0, 구버전 쪽 변경은 ui/v2_entry.py 하나(다음 tradebot 재시작 때 반영) | 계획서 Global Constraints, verifier 영향 표 |
| 6 | backtester.js 바이트 동일 유지, 함수는 window 로 감싸고 let 전역은 맨이름 | backtester.js:1-2·12·399, verifier 확인 |

## 물어볼 것
| # | 질문 | PO의 생각 |
|---|---|---|
| 1 | 계획서가 승인 요청서 그림과 결정 1026-19 를 빠짐없이, 사실대로 옮겼는가 | 그렇다 |
| 2 | 실매매·서비스 위험이 남아 있는가(업비트 브라우저 제한·로그 읽기 부하 포함) | 없다. 업비트 제한은 투자자 IP 만, 로그는 LIMIT 1200 묶음 |
| 3 | 사용자에게 승인받을 때 따로 물어야 할 것이 있는가 | 없다(요청서에 적힌 것은 묻지 않기 — 사용자 지시) |

## 참고 파일
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/plan-proposal-match-20261026.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/investor-approval-20261021-v2.html (렌더 /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/.superpowers/proposal/p-01.png ~ p-12.png)
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/fable/2026-10-26-proposal-match-scope-1.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/CLAUDE.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/.claude/context/project-rules.md

---

# 답변 1회째 (Fable)

**판정:** 수정 후 진행
**이유:** 배치·문구·순서·결정 5건은 그림과 맞고 엔진 경로 변경 0·서버 업비트 호출 0 확인. Task 6 쪽 수 SQL 이 v2/db.py LIMIT 검사에 거부되는 형태, 사유·거래 유형 표가 서버 실제 값 약 67% 를 덮지 못함.

| # | 중요도 | 무엇을 |
|---|---|---|
| 1 | 막음 | COUNT SQL 바깥에 `LIMIT 1` (v2/db.py:24-26 `_LIMIT_RE`) |
| 2 | 막음 | 사유·거래 유형 표를 서버 실제 값(TRAILING_STOP_FIXED·HTS_BUY·HTS_BUY_ADD·force_buy·force_liquidate·BUY_FAILED_API·HTS_SELL·BUY_CANCELED)에 맞추기 |
| 3 | 권고 | 백테스터 기본값 엔진 봉 단위(1분)·30일, 첫 실행 약 36분을 승인 요청에 적기 |
| 4 | 권고 | 엔진 배지 3단계 접는 방법, test_no_stop_word_in_engine_badge needle 교체 |
| 5 | 권고 | failed_keys 한글 표(NO_SIGNAL·SURGE_FILTER·WARMUP_IN_PROGRESS·WEAK_ENTRY_FILTER) |
| 6 | 권고 | 「구버전으로」 = 로그인 화면임을 표·보고에 |
| 7 | 권고 | 분할 회차 1차 「—」 고정 |
| 8 | 권고 | 네 표 SQL `ORDER BY timestamp DESC, id DESC LIMIT 1200` |
| 9 | 권고 | spec.md 폐기 결정 반영·ui/v2_entry.py docstring |
| 10 | 권고 | 그림 5-가 업비트 안내 문구 차이를 대조표에 |
사용자에게 물어야 할 것: 없음.

## 수정 (막음 1·2, 권고 3~10 모두 반영) — 다시 묻기
- 막음 1: Task 6 쪽 수 SQL `SELECT COUNT(*) AS n FROM (SELECT 1 FROM … LIMIT 1201) LIMIT 1`, 네 표 SQL 동점 정렬 포함.
- 막음 2: Task 2 구분(BUY·SELL·*_REJECTED·HTS_SELL·BUY_CANCELED)·사유 표(대소문자 무시, TRAILING_STOP* 접두, HTS_BUY·HTS_BUY_ADD·FORCE_BUY·FORCE_LIQUIDATE·BUY_FAILED_API·HTS_SELL), 가격 없으면 금액 「—」. 화면 표는 새 `v2/static/labels.js`, 서버 표는 `REASON_LABELS`·`FAILED_KEY_LABELS`, 두 표 같음 시험. 시험 (d) 확장.
- 권고 3·6: 「사라지거나 옮겨지는 것」 표에 두 줄. 권고 4·7: Task 2·Task 1 문구. 권고 5: FAILED_KEY_LABELS. 권고 9·10: Task 9 Step 4·5.

## 다시 묻는 것
| # | 질문 | PO의 생각 |
|---|---|---|
| 1 | 막음 1·2 가 해소됐는가 | 해소 |
| 2 | 새 파일 labels.js 와 서버 표를 같은 값으로 두는 방식에 위험이 있는가 | 두 표 같음 시험으로 막음 |

---

# 답변 2회째 (Fable)

**판정:** 진행
**이유:** 막음 1·2 와 권고 3~10 반영을 줄 단위로 확인. 남은 지적은 labels.js 배선과 문구 불일치로 모두 권고.

| # | 중요도 | 무엇을 |
|---|---|---|
| 1 | 권고 | labels.js 를 Task 2 Files·OWN·index.html 연결에 넣고, 두 표 같음 시험을 test_static_lint.py `test_labels_match_server` 로 정하기 |
| 2 | 권고 | 네 표 SQL 줄 하나에 `, id DESC` 빠짐 |
| 3 | 권고 | 감사 로그에 HTS_SELL·BUY_CANCELED 행 |
| 4 | 권고 | 엔진 배지 running true·level unknown 경우 |
사용자에게 물어야 할 것: 없음.

## PO 처리
- 권고 1~4 모두 계획서에 반영(Task 2 Files·Interfaces, Task 1 OWN, Task 6 목록·시험, 배지 문구). 다시 묻지 않음(권고뿐 — 규칙).
