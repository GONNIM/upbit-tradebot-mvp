# 질의: Ver2 배포 승인 요청서를 다 썼고, 사용자에게 push 승인·배포 승인을 요청하려 합니다

**지금 단계:** 배포 요청서 작성 끝 (사용자 승인 요청 직전)
**다음에 하려는 일:**
- 사용자에게 요청서 6절의 두 가지를 요청합니다. 하나는 push 승인, 다른 하나는 배포 실행 승인입니다.
- push 승인을 받으면 다음 순서로 진행합니다.
  1. 요청서·HANDOFF·이 질의 파일을 문서 커밋 C 로 묶습니다. 커밋 전에 `git diff --staged` 로 비밀값을 검사하고, 메시지는 `git commit -F` 로 넣습니다.
  2. 84ba2e1 · b9e91ed · C 를 push 합니다. push 전 자동 검사가 돕니다.
  3. scratchpad 에 있는 run.sh 의 `NEW=__NEW__` 자리에 C 의 전체 해시를 넣습니다.
  4. 업로드·드라이런 한 줄을 사용자에게 드립니다.
- 사용자 결정 ㉠ ① · ㉡ ② 를 반영한 커밋 b9e91ed(알림 문장 1줄 · 시험 1개 · 버전)는 지난 질의 뒤에 생겼습니다. 이 질의에 묶습니다.
- 배포 실행(재시작)은 사용자가 업로드·드라이런 한 줄과 본 띄우기 한 줄을 직접 실행할 때만 일어납니다. 그 직전에는 드라이런 결과를 읽고 사용자에게 권할지만 정합니다.
- 프로젝트 규칙: 배포는 사용자 승인 뒤에만 합니다(Issue #16).

**검증 이력:**
- verifier 1회째 「수정 후 승인」: 지적 10건이었습니다.
  - 그중 1건은 「반박됨」으로, 배포 대상 커밋 목록이 4개로 잘못 적혀 있었습니다(실제 9개). 고쳤습니다.
  - 나머지 8건도 고쳤습니다.
  - precheck 의 여러 줄 `python -c` 는 이미 실행한 읽기 전용 점검이라 고치지 않았습니다. 다음 점검부터 파일로 실행합니다.
- verifier 2회째 「승인 가능」: 남은 문장 1곳(재시도 「+ 1회」)을 고쳤습니다.

## 지금까지 확인한 사실
| # | 사실 | 확인/추정 | 근거 |
|---|---|---|---|
| 1 | 서버(11/05 21시): HEAD eff249a · v1.2026.11.03.2304 · tradebot 11/04 10:42:16 기동 · NRestarts 0 · v2 11/01 14:21:31 기동 · 미추적 5 · 전략 3개 EMA · 비밀 파일 600 · 디스크 16G · 사용 가능 메모리 1,411MB | 확인(사용자 지시로 읽기 전용 SSH 점검, 11/05 21시) | scratchpad deploy-1106/precheck.sh 출력(요청서 머리말에 옮김) |
| 2 | 엔진 기동 뒤 오류 매치는 11/04 14:38:05 의 `WARNING [SETTINGS-SNAPSHOT] database is locked` 1줄뿐이다. 그래서 정지선 기준 시각 T_BASE 를 11/05 21:00 으로 둔다 | 확인 | 같은 점검의 journal grep |
| 3 | 서버 새 전략 설정 파일은 1개(mcmax33 저장본 18키, 옛 2키 있음)이고 적용본은 0개다. 옛 설정 알림은 전환(적용) 때만 1회 간다 | 확인(서버 값 + 코드) | verifier 1회째 #8 |
| 4 | 알림 받는 곳: 서버 .env 에 등급별 채팅 키가 없고, 기본 채팅이 운영자 채팅과 같다. 투자자에게 가지 않는다 | 확인(서버 값 같음/다름만) · 코드 notifier.py:70-77 | precheck 출력 |
| 5 | 사용자 DB 4개 가운데 기동 마이그레이션 대상은 3개다(이름 없는 DB 는 빠짐). 기대 `[migrate] added pullback_state.*` 는 18줄이다 | 확인(코드), 서버 DB 수 확인 | boot_resume.py list_known_users |
| 6 | 배포 대상은 eff249a..b9e91ed 11개 + C 이고 fast-forward 다. 런타임 커밋은 3개(f4a370f · c0559e3 · b9e91ed)다 | 확인 | verifier 2회째 |
| 7 | v2 재시작이 필요하다(v2 파이썬 4파일 변경). tradebot 기동·마이그레이션 확인 뒤에 재시작한다 | 확인 | run.sh, verifier #24·#25 |
| 8 | 되돌리기: 6칸이 붙은 DB 에서 eff249a 코드의 읽기·저장·청산 초기화가 된다. 새 칸 값은 남는다 | 확인(로컬 시험 2회, verifier 다시 실행) | scratchpad deploy-1106/revert_check.py |
| 9 | 되돌리기 시험의 기준(REVERT_OLD_CODE_COMMIT)을 eff249a 로 올리면 시험 2개가 실패한다. 이 시험은 「2차 배포 전 코드」 전용이다. 11/03 결정(1101-08)대로 1747fcc 를 둔다. 대신 #8 의 직접 점검으로 갈음했다 | 확인 | 이번 시도, HANDOFF 1101-08 |
| 10 | 시험: 회귀 1271/1271 · v2 450 · JS 181 · NETGUARD 0 | 확인(verifier 가 게이트를 다시 실행) | verifier 1회째 #27 |
| 11 | 투자자 PDF 2절 표와 달라진 곳은 없다. 강제 매수 중 중단 표시는 홈 배지와 엔진 기록으로 보인다(결정 ㉠ ①) | 확인(verifier #10) | investor-ver2-result-20261105.html |
| 12 | 서버 MemoryPeak 칸은 비어 있다(systemd 판). 그래서 관찰 중 v2 메모리는 1분마다 MemoryCurrent 를 읽어 최대값을 남긴다 | 확인 | precheck 출력 `mem_peak=` |
| 13 | 1분봉 90일 백테스트 v2 메모리는 로컬 최악 96.7MB 다. 서버 값은 배포 뒤 다시 잰다 | 로컬은 확인, 서버는 추정 | 1단계 measure_worst_mem.json |

## 물어볼 것
| # | 질문 | PO의 생각 |
|---|---|---|
| 1 | 요청서와 run.sh 로 배포 승인을 요청해도 되는가. 정지선·대기 조건·되돌리기에 빠진 것이 있는가 | 된다. 배포 ② 스크립트에서 값만 바꿨고, v2 재시작·되돌리기·표식·마이그레이션 줄 수를 더했다 |
| 2 | v2 재시작 뒤 30초 안에 active 이고 ERROR 가 0 이면 통과로 보는 기준이 충분한가 | 충분하다. 1시간 관찰에서 v2 비활성이면 되돌리고, check_v2_unit 도 돈다 |
| 3 | 재시작 직후 5분 로그인 자제와 1시간 동안 새 전략 설정 저장 금지를 사용자 행동 규칙으로 두는 것으로 충분한가. 아니면 코드로 막아야 하는가 | 행동 규칙으로 충분하다. 로그인 경합은 드물고, 생기면 거짓 되돌리기일 뿐 데이터 손실이 없다 |
| 4 | push 승인과 배포 승인을 한 번에 받아도 되는가 | 된다. 배포 ②와 같이 push 뒤 드라이런 한 줄 실행을 승인으로 본다 |
| 5 | 빠진 위험이 있는가 | 없다고 본다. 업비트 IP 한도 축은 verifier 지적으로 넣었다 |

## 참고 파일
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/deploy-request-20261106-ver2.md
- /private/tmp/claude-501/-Users-gonnim-Project-MVP-Source-upbit-tradebot-mvp/ea6e1d09-ef96-4ae5-a466-dade40d251db/scratchpad/deploy-1106/run.sh (helper.py · notify.py 는 deploy-1104 와 같음, patch_run.py · patch_req.py 가 바꾼 방법)
- /private/tmp/claude-501/-Users-gonnim-Project-MVP-Source-upbit-tradebot-mvp/98f63d2d-b8df-4e31-8e0c-2c80d63b11d2/scratchpad/deploy-1104/run.sh (지난 배포 ②)
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/deploy-report-20261104-bundle2.md
- /private/tmp/claude-501/-Users-gonnim-Project-MVP-Source-upbit-tradebot-mvp/ea6e1d09-ef96-4ae5-a466-dade40d251db/scratchpad/deploy-1106/revert_check.py
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/plans/2026-11-05-ver2-backtester/plan.md (4절 · 8절)
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/fable/2026-11-05-ver2-stage2-1.md

---

# 답변: Ver2 배포 승인 요청서를 다 썼고, 사용자에게 push 승인·배포 승인을 요청하려 합니다

**판정:** 진행
**이유:** 질의서의 사실 13개 가운데 저장소·시험으로 볼 수 있는 것은 모두 직접 확인했고 어긋난 곳이 없습니다. run.sh 는 지난 배포 ② run.sh 에서 값과 v2 재시작·6칸 확인 단계만 더한 것이 diff 로 확인되고, 되돌리기 점검도 제가 다시 돌려 같은 결과를 얻었습니다. 남은 지적은 모두 권고입니다.

직접 확인한 것(11/05 밤, 로컬 저장소에서만 실행 · 서버 접속 없음):
- `git log eff249a..HEAD` 11개 · fast-forward(`merge-base --is-ancestor` 통과) · HEAD b9e91ed · 미추적은 질의서·요청서 2개뿐.
- 런타임 파일을 바꾼 커밋은 f4a370f · c0559e3 · b9e91ed 셋뿐. 35f14e5 는 .gitignore 13줄과 시험 파일, 8329271 은 시험만. .gitignore 새 패턴(.superpowers/ · trading-performance/*.pdf · tests/test_mode_lock.py 등 4개 · !docs/new-version/*.txt)은 서버 미추적 5건 이름과 겹치지 않음.
- v2 파이썬 변경 4파일(api_read · candles · control · params_schema) — 사실 7 과 같음. `pages/dashboard.py:524` 버전 v1.2026.11.05.2039.
- EMA 경로 AST: eff249a 대비 HEAD 에서 바뀐·더해진 함수는 core/strategy_engine.py 12개 · engine/live_loop.py 1개이고 모두 이름에 pullback 이 있음(스크립트 /private/tmp/claude-501/-Users-gonnim-Project-MVP-Source-upbit-tradebot-mvp/ea6e1d09-ef96-4ae5-a466-dade40d251db/scratchpad/fable_ast_cmp.py).
- 시험(NETGUARD 접두 사용): tests/regressions 1271 OK · tests/v2 450 OK · node 181 통과 0 실패 · NETGUARD 출력 0건.
- 되돌리기 점검: eff249a 의 services/ 를 `git archive` 로 scratchpad 에 꺼내 revert_check.py 를 돌림 → new_cols 30 · 옛 코드 load/save/reset 모두 True · 청산 초기화 뒤 새 6칸 값(sl_streak 2 · pause 시각 · episode_idx 3 · trade_episode_idx 3 · trade_tp_pct 2.5)이 그대로 남음 · integrity ok. 요청서 3절 2·3 과 같음.
- 마이그레이션: `services/init_db.py:1044-1049` 가 `_ensure_column` 6번 → `[migrate] added pullback_state.<칸> (<형>)` INFO 1줄씩. `engine/boot_resume.py:126-135` 가 `list_known_users()`(이름 비었거나 크기 0 제외) 전부에 `ensure_all_schemas` 를 돌리고 예외는 사용자별로 잡아 `[BOOT-RESUME] 마이그레이션 실패` ERROR 1줄. run.sh boot_check 의 `마이그레이션 실패|\[migrate\].*실패` 와 ERR_RE 둘 다에 걸려 되돌리기로 이어짐 — 요청서 3절 1 과 같음.
- 옛 설정 알림: `validate(..., user_id=)` 는 load_for_boot · reload_applied · apply_saved 에서만 user_id 를 받음. v2 서버는 engine.pullback_params.validate 를 부르지 않음(v2/*.py 검색 0건). EMA 활성이면 기동 때 load_for_boot 가 불리지 않으므로 「기동 때 알림 없음 · 전환 때 1회」가 맞음. 수신 채널 규칙 `services/notifier.py:70-77`(등급별 키 없으면 TELEGRAM_CHAT_ID) — 사실 4 와 같음.
- run.sh ↔ deploy-1104 run.sh diff: 값(OLD·NEW·마감·기동 시각·T_BASE·버전) · v2 재시작 블록 · rollback 의 v2 재시작 · 표식 4개 · migrate 줄 수 · DB 마다 칸 수 · 1시간 관찰의 v2 active·메모리 최대값만 다름. helper.py · notify.py 바이트 같음. 표식 4개는 로컬 HEAD 에서 5 · 1 · 1 · 3 으로 모두 1 이상. scripts/v2/check_v2_unit.sh 있음.
- 1101-08 결정(HANDOFF.md:155)에 「REVERT_OLD_CODE_COMMIT 은 2차 스키마 되돌리기 전용 시험이라 1747fcc 유지」가 적혀 있음 — 사실 9 와 같음. `baseline_commits.py:74` 1747fcc.
- 투자자 HTML(investor-ver2-result-20261105.html)에 60선 기울기·상승폭·연속 손절·구간·데드크로스·10/15/30분·90일·매수 중단 낱말이 모두 있음(2절 표 전체 대조는 verifier 결과를 따름).

확인하지 못한 것: 서버 값(사실 1·2·3 의 서버 부분·4 의 .env·5 의 DB 수·12·13 서버 메모리)은 사용자가 실행한 precheck.sh 출력이 근거이고 제가 다시 보지 못했습니다. 다만 run.sh 정지선이 같은 항목을 실행 때 다시 재고 어긋나면 아무것도 바꾸지 않고 끝나므로, 값이 틀려도 손해로 이어지지 않습니다. verifier 보고 원문은 참고 파일에 없어 질의서의 요약을 그대로 받았습니다.

## 질문별 답
| # | 질문 | 답 | 확신 정도 |
|---|---|---|---|
| 1 | 요청서·run.sh 로 승인 요청 가능한가. 정지선·대기·되돌리기에 빠진 것 | 가능합니다. 정지선 20여 항목 · 대기 조건(보유 0 · 묶임 0 · 미체결 0 · 갱신 120초 · 새 BUY 없음 · minute3 · 5분 ERROR 0) · 백업·무결성 · 다음 봉 재확인 · 경계 60초 · ff-only · 기동 확인 · v2 확인 · 표식 · 되돌리기(두 서비스) · 1시간 관찰이 모두 스크립트에 있고 지난 배포 ②에서 쓴 틀과 같습니다. 빠진 것은 없고, 아래 권고 1·3 을 요청서 글에 더하시면 됩니다. | 높음 |
| 2 | v2 재시작 뒤 30초 active + ERROR 0 기준이 충분한가 | 충분합니다. 11/04 배포 ② 관찰에서 v2 journal ERROR 는 1시간 0건이었고(deploy-report-20261104-bundle2.md:16), 1시간 관찰이 1분마다 v2 active 를 다시 보며 끝에 v2_err 를 셉니다. check_v2_unit 은 유닛 속성 점검이라 화면 응답은 보지 않으므로, 화면 응답은 5절 「화면 확인」이 맡습니다. 스크립트에 더 넣지 않아도 됩니다. | 높음 |
| 3 | 5분 로그인 자제·1시간 설정 저장 금지를 행동 규칙으로 두면 충분한가 | 이번 배포는 행동 규칙으로 충분합니다. 경합은 구버전 로그인(app.py:281 → init_db_if_needed → ensure_all_schemas)과 기동 스레드(기동 3초 뒤 시작) 사이에서만 생기고, 신버전(v2) 로그인은 마이그레이션을 부르지 않습니다. 생겨도 결과는 거짓 되돌리기(EMA 워밍업 1회 더)일 뿐 DB 손실이 없습니다. `_ensure_column` 에 「duplicate column」 예외 흡수를 넣는 것은 런타임 변경이라 다시 검증·버전 갱신이 필요하므로 이번에는 넣지 말고 백로그로 두시길 권합니다. | 높음 |
| 4 | push 승인과 배포 승인을 한 번에 받아도 되는가 | 됩니다. 배포 ②와 같은 방식이고, 실제 재시작은 사용자가 드라이런·본 띄우기 두 줄을 직접 실행할 때만 일어납니다. 다만 6절 1·2 를 각각 「가/아니오」로 답하실 수 있게 두 줄로 묻는 지금 모양을 유지하십시오. | 높음 |
| 5 | 빠진 위험 | 되돌리기 어려운 새 위험은 없습니다. 작은 것 셋: (가) 정지선 ERR_RE 에 `database is locked` 가 있어 11/04 와 같은 SETTINGS-SNAPSHOT 경고가 11/05 21:00 뒤 한 번만 나도 「정지선 불일치」로 끝납니다 — 안전한 쪽이지만 그때 T_BASE 를 어떻게 다시 정할지 요청서에 한 줄 있으면 좋습니다. (나) `[migrate] added` 줄 수 18 은 기록만 하고 판정에 쓰지 않으므로, 줄 수가 0 이고 칸 수가 30 이면 로그 전달 문제이지 마이그레이션 실패가 아닙니다 — 판정 기준은 「칸 수 30」임을 요청서에 적으십시오. (다) 옛 코드 reset_after_exit 는 trade_episode_idx · trade_tp_pct 를 지우지 않습니다(제 실행에서 확인) — 3절 3 에 이미 적혀 있으니 그대로 두면 됩니다. | 높음 |

## 고쳐야 할 것
| # | 중요도 | 무엇을 | 왜 | 어떻게 확인하는지 |
|---|---|---|---|---|
| 1 | 권고 | 요청서 2절 7 의 까닭을 「구버전 화면 로그인 경로(app.py 의 init_db_if_needed)가 같은 표 칸 추가를 돌림」으로 좁히고, 신버전 로그인은 마이그레이션을 부르지 않는다고 적기(규칙 자체는 두 화면 모두 자제로 두어도 됨) | 지금 글은 두 화면 모두 경합 원인처럼 읽히는데, v2/*.py 에는 init_db 호출이 없음 | `grep -rn "init_db\|ensure_all_schemas" v2/` 0건 · `app.py:281` |
| 2 | 권고 | 커밋 C 의 HANDOFF 1105-09 행(HANDOFF.md:143)에서 「REVERT_OLD_CODE_COMMIT 을 서버 실행본으로 올려 T10 재실행」을 「1101-08 결정대로 1747fcc 유지, revert_check.py 직접 점검으로 갈음」으로 바꾸기 | HANDOFF 143 과 1101-08(HANDOFF.md:155)·요청서 사실 9 가 서로 다름 | 두 줄을 나란히 읽어 같은 결정인지 보기 |
| 3 | 권고 | 요청서 2절 3 또는 3절 1 에 「판정은 DB 마다 pullback_state 칸 수 30(tradebot_.db 0) · `[migrate] added` 18줄은 참고」와 「정지선이 `database is locked` 1줄로 끝나면 T_BASE 를 그 시각 뒤로 옮겨 다시 띄울지 사용자에게 묻는다」 두 줄 넣기 | 질문별 답 5 (가)(나) | run.sh 295-296 행이 줄 수는 log 만 하고 칸 수는 DB 마다 찍는 것 확인 |
| 4 | 권고 | 백로그에 「`services/init_db._ensure_column` 의 duplicate column 예외 흡수(로그인·기동 경합)」 1건 적기 — 이번 배포에는 넣지 않음 | 질문별 답 3 | 백로그 표에 행이 있는지 보기 |
| 5 | 권고 | 보고 글에서 「시험: 회귀 1271/1271 · v2 450 · JS 181 · NETGUARD 0」은 Fable 이 11/05 밤 다시 돌려 같은 값임을 덧붙여도 됨 | 사용자가 두 번 확인된 값으로 읽을 수 있음 | 이 답변서의 「직접 확인한 것」 |

## 사용자에게 물어야 할 것
- 없음 (요청서 6절의 push 승인 · 배포 실행 승인 두 가지가 그대로 사용자가 정할 일입니다. Fable 쪽에서 더할 질문은 없습니다.)

## PO 반영 (11/05)
- 권고 1 · 3: 요청서 2절 7 까닭을 구버전 로그인 경로로 좁힘, 2절 9(칸 수 판정) · 10(DB 잠김 경고 때 다시 묻기) 더함.
- 권고 2: HANDOFF 1105-09 행의 되돌리기 시험 문구를 1101-08 결정과 맞춤.
- 권고 4: docs/plans/backlog.md 에 칸 중복 예외 흡수 1건 등록(이번 배포 밖).
- 권고 5: 사용자 보고에 「Fable 이 시험을 다시 돌려 같은 값」을 적음.
