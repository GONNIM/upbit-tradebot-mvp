# 질의: 투자자 수정 요청(11/21 PDF) 계획 초안을 마쳤고, 사용자에게 계획 승인 요청을 올리려 함

**지금 단계:** 계획
**다음에 하려는 일:** 계획(아래 초안)을 사용자에게 보고하고 정할 것 4개(㉠ 1% 뜻 · ㉡ 홈 보유 아래 · ㉢ 감사 로그 6값 범위 · ㉣ TS 뜻)와 계획 승인을 묻는다. 승인 전에는 구현·커밋·저장소 계획 문서 기록을 하지 않는다.

## 지금까지 확인한 사실
| # | 사실 | 확인/추정 | 근거 |
|---|---|---|---|
| 1 | PDF 는 3쪽이며 백테스터 5개·로그 2개·운용 1개 요청이다 | 확인 | /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/new-version/claim/ver9/Fullback_수정사항_261121.pdf (pdftotext + 110dpi 렌더 3장 직접 봄) |
| 2 | 지금 화면은 결과 요약 → 스윕 → 「자세한 결과」 접힘(summary·depth·weekly·monthly·sweepResult) 순서다 | 확인 | v2/static/backtester.html:180~229 (verifier 판정 1·3) |
| 3 | Ver9 은 status → summary → depth → weekly → monthly → 스윕 단추 → sweepResult 순서다 | 확인 | docs/new-version/ver9/MA_GC_Pullback_Backtester_2611161307(Ver9).html:132~165 |
| 4 | B4 5칸은 「설정 20개」 접힘 안이며 칸 id 로만 읽혀 옮겨도 계산·저장은 그대로다 | 확인 | backtester.html:134·135·151·153·154, backtester.js:570·589, save.js:86·547 |
| 5 | 보유 중 봉마다 audit_sell_eval 에 종가와 checks.avg 가 남고 v2 가 이미 checks 를 읽는다 | 확인 | core/strategy_engine.py:2099·1269, core/strategy_pullback.py:791~797·910·1018, v2/api_read.py:180~183 |
| 6 | 감사 로그 매도 판단 창은 최근 1200행이다 | 확인 | v2/api_read.py:180~183 |
| 7 | PARAMS 행 note.changed 는 TS 3키·투자비율 2키를 포함한 [구,신]을 담는다 | 확인(코드) · 실DB 모양은 추정 | engine/pullback_apply.py:42~43·94~101·297 — 서버 DB 는 이번에 보지 않음 |
| 8 | v2_settings_history.params_json 에는 TS·투자비율이 없다 | 확인 | v2/api_write.py:57·110~114·129 |
| 9 | ops API 는 6값을 내려 주지 않아 v2/control.py 확장이 필요하다 | 확인 | v2/control.py:253~320, v2/api_read.py:315~325 |
| 10 | 모든 변경은 v2/ 아래이고 엔진은 v2 를 import 하지 않아 tradebot-v2 만 재시작하면 된다 | 확인 | grep 0건(verifier 판정 15) |
| 11 | 「TS 1.50」이 TP(익절)를 뜻하는지 추적 손절 폭을 뜻하는지 알 수 없다 | 추정 | ts_pct 는 1~100(기본 50, params_schema.py:89·114), PDF 목록에 TP 없음 |
| 12 | 서버는 9f70dac·v1.2026.11.17.1407, 엔진 기동 11/19 13:06:12, 현재 보유 없음(15:54 restored=False reason=flat) | 확인 | 11/21 18:44 사용자 `!` 서버 읽기 출력 |
| 13 | verifier 1회째: 고친 뒤 승인 가능, 막음 3(L2 출처·ops API·시험 목록) 모두 초안 1-1절에 반영 | 확인 | 초안 1-1절 |

## 물어볼 것
| # | 질문 | PO의 생각 |
|---|---|---|
| 1 | L2 를 PARAMS changed 역추적으로 만드는 방식이 맞는가(옛 행·거래 시간 적용 행 포함) | 맞다. 지금 적용본에서 거꾸로 되돌리면 실DB 하나만 읽는다. 역추적 중 키가 빠지면 그 값만 「—」 |
| 2 | L1 을 엔진이 아닌 읽기 쪽(봉 종가)으로 만드는 것이 요청 뜻에 맞는가 | 엔진 재시작 없이 되므로 권고. 봉 안 순간 움직임은 안 보임을 안내 |
| 3 | 투자자 답이 필요한 해석 4개(㉠~㉣)를 사용자에게 묻고, 답이 없으면 권고대로 가정해 구현 후 커밋 전에 다시 확인하는 순서가 맞는가 | 11/17 Ver9 때와 같은 방식 |
| 4 | 빠진 위험 | 1200행 창 성능(역추적은 PARAMS 행 수만큼), 화면 순서 변경 시 휴대폰 길이 |

## 참고 파일
- /private/tmp/claude-501/-Users-gonnim-Project-MVP-Source-upbit-tradebot-mvp/c37bfe27-a876-4cd2-9521-ec445719cefb/scratchpad/fullback-plan-draft.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/new-version/claim/ver9/Fullback_수정사항_261121.pdf
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/CLAUDE.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/.claude/context/project-rules.md


---

# 답변 1회째 요지 (Fable · 11/21)

- 판정: 수정 후 진행. 막음 5: (1) 역추적은 모드 상관없이 모든 PARAMS 행 (2) 시작 조건 = 가장 새 행 params_sha256 과 적용본 sha 일치, 전체 기록 행에서 멈춤 (3) 1105-09 이전 행 기울기·둔화 「—」 (4) 실DB PARAMS 행 실측 단계 추가 (5) 초안 본문과 1-1절 합치기. 권고 5: 분할 = 실제 한도, 「지금 설정」 밝힘, 「투자자 답」→「사용자 결정」·㉣ 추가, L1 줄 상한 숫자, 뒤 일감(note 에 6값 남기기).
- 반영: 계획 2판 /private/tmp/claude-501/-Users-gonnim-Project-MVP-Source-upbit-tradebot-mvp/c37bfe27-a876-4cd2-9521-ec445719cefb/scratchpad/fullback-plan-draft.md (1-1절 역추적 6단계, 3절 2번 실측, 옛 내용 grep 0건), 실측 스크립트 /private/tmp/claude-501/-Users-gonnim-Project-MVP-Source-upbit-tradebot-mvp/c37bfe27-a876-4cd2-9521-ec445719cefb/scratchpad/params_rows_read.sh

# 질의 2회째: 막음 5개를 반영한 계획 2판을 사용자에게 올려도 되는가

**지금 단계:** 계획
**다음에 하려는 일:** 2판과 정할 것 ㉠~㉣, 실측 스크립트 실행 요청을 사용자에게 보고한다.

## 물어볼 것
| # | 질문 | PO의 생각 |
|---|---|---|
| 1 | 막음 1~5 가 2판에 빠짐없이 반영되었는가 | 1-1절 1·2·4·5, 3절 2번, 본문 합침 |
| 2 | 실측 스크립트가 읽기 전용이고 비밀값을 출력하지 않는가 | sqlite ro 모드, 설정 값·sha 만 |


# 답변 2회째 요지 (Fable · 11/21)

- 판정: 수정 후 진행. 계획 2판에 막음 1~5 모두 반영 확인. 막음 2(실측 스크립트): DB 경로를 services/data/tradebot_mcmax33.db 로, 옛 키 행 수를 json_type 조건으로. 권고: ? 인자, note 2000자, 전환 기록 실패도 셈, ro 실패 시 엔진 확인 머리말.
- 반영: params_rows.py(scratchpad) 로 모두 고침 · 시험 DB 로 돌려 옛 키 행 1·전체 기록 행 id 1 맞게 나옴 · params_rows_read.sh 에 base64 로 넣음.
- 한 단계 2회 한도라 사용자에게 올림(계획 승인·정할 것 ㉠~㉣).
