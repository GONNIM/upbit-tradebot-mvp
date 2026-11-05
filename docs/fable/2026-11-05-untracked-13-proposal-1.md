# 질의: git 미관리 13항목 조사를 마쳤고, 항목별 권고안을 사용자에게 올리려 합니다

**지금 단계:** 요구 정리 (사용자 결정 요청 직전)
**다음에 하려는 일:** 아래 4개 항목별 권고안(㉠~㉣)을 「정해 주실 것」으로 사용자에게 올립니다. 이번에는 파일을 고치거나 커밋하지 않습니다. 이 질의 파일 자체는 다음 커밋 때 함께 올립니다(작은 문서, 묶음).

## 지금까지 확인한 사실
| # | 사실 | 확인/추정 | 근거 |
|---|---|---|---|
| 1 | `git status --short` 13줄 전부 `??`(미관리), `M` 0줄. 로컬=원격 4dee9dc | 확인 11/05 12시 | 명령 출력 |
| 2 | 저장소는 PUBLIC. 커밋·push = 공개 | 확인 11/04 | `gh repo view --json visibility` |
| 3 | `.superpowers/` 11MB, png 등 약 215개(bt-check 8·proposal 13·sdd 하위). 10/26~27 제안서·화면 실측 작업 산출물. 운영 서버 화면 캡처(prod-*-nologin.png) 포함 | 확인 | `find .superpowers -type f`, `du -sh` |
| 4 | `.superpowers/` 는 superpowers 플러그인의 작업 폴더라 저장소 관리 대상이 아님 | 추정 | 플러그인 문서를 보면 확인됨 |
| 5 | 6/23 JTO 분석 md 2개(20K·16K) + pdf 2개(940K·900K). 자격증명 시그니처·이메일·전화 0건 | 확인 | grep 결과 0 |
| 6 | 같은 폴더의 6/21 진단 md 는 이미 커밋돼 공개 중(사용자 mcmax33·손익률 포함). 그 폴더에 커밋된 pdf 는 없음 | 확인 | `git ls-files docs/analysis/trading-performance` |
| 7 | tests 7개는 게이트(regression_gate.sh: tests/regressions·tests/v2 만 discover)에 들지 않음 | 확인 | scripts/regression_gate.sh:193·225 |
| 8 | netguard 아래 실행: candle_validator 23 OK, page_navigation 14 OK, mode_lock 모듈 불러오기 실패, position_integrity 15개 중 6 오류 — 모두 config.py:21 「UPBIT_ACCESS/SECRET 없음」 | 확인 11/05 | `PYTHONPATH=tests/_netguard python3 -m unittest tests.<이름>` |
| 9 | order_ratio_verification 은 unittest 아닌 스크립트형, initialize_db·create_or_init_account 로 DB 를 씀. sell_filter_execution·tp_sl_integration 도 스크립트형(json·strategy 직접). 이 3개는 실행하지 않음 | 확인(형태) / 실행 결과 미확인 | 파일 앞부분 |
| 10 | 로컬 키는 10/30 비웠고 시험은 바깥 연결 없이 돌려야 함 | 확인 | 메모 feedback_tests_no_real_network |
| 11 | `docs/new-version/` 오늘 12:33~38 생성(사용자). Ver2 백테스터 html 74K·png 2·txt 2.4K·.DS_Store. txt 는 전역 `*.txt`, .DS_Store 는 `.gitignore:2` 로 이미 무시됨 | 확인 | `git check-ignore -v` |
| 12 | 앞선 원본 백테스터 `docs/specs/MA60_200_GoldenCross_Pullback_Backtester_2610201820.html` 이 이미 커밋돼 있음(선례) | 확인 | `git ls-files` |
| 13 | txt 속 파일명(…2610221843.html)과 실제 파일명(…2611051030(Ver2).html) 다름. Ver2 를 신버전에 반영할지는 미정 | 확인 | 파일 내용 |

## 물어볼 것
| # | 질문 | PO의 생각 |
|---|---|---|
| 1 | ㉠ `.superpowers/` 를 `.gitignore` 에 넣는 권고가 맞는가 | 작업 산출물·운영 화면 캡처·11MB 라 공개 저장소에 올리지 않음. 지우지 않으므로 되돌릴 수 있음 |
| 2 | ㉡ 6/23 md 2개만 커밋, pdf 2개는 `docs/analysis/trading-performance/*.pdf` 무시 규칙 — 맞는가 | 6/21 md 선례와 같게. pdf 는 md 와 내용 중복·1.8MB |
| 3 | ㉢ 시험 7개: 통과 2개(candle_validator·page_navigation)만 커밋(게이트는 그대로), 나머지 5개는 `.gitignore` 에 파일별로 넣어 보관 — 맞는가. 삭제는 권하지 않음(미관리 파일이라 지우면 되살릴 수 없음) | 키 필요 2개는 키를 다시 넣지 않는 한 못 돌림. 스크립트형 3개는 DB 를 쓸 수 있어 돌리지 않음 |
| 4 | ㉣ docs/new-version 의 html·png 2·txt 를 그 자리 그대로 커밋(txt 는 `git add -f`) — 맞는가. 반영 여부 결정은 별개 | 원본 백테스터 선례. 사용자가 저장소 안에 둔 자료 |
| 5 | 모두 문서·무시 규칙·시험 파일뿐이라 dashboard.py 버전 갱신·서버 pull 불필요 — 맞는가 | 메모 feedback_version_bump_scope |

## 참고 파일
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/.gitignore
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/scripts/regression_gate.sh
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/new-version/20261105-ver2.txt
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/analysis/trading-performance/2026-06-23-krw-jto-action-recommendation-v2.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/tests/test_position_integrity.py
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/tests/test_order_ratio_verification.py
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/CLAUDE.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/.claude/context/project-rules.md

---

# 답변 (1회째): git 미관리 13항목 조사를 마쳤고, 항목별 권고안을 사용자에게 올리려 합니다

**판정:** 수정 후 진행
**이유:** 공개하면 안 되는 내용은 표본에서 없음. ㉠·㉡·㉣ 그대로 가능. ㉢ 전제 「키 없어 2개 못 돌림」이 틀림 — 자리표시 키로 position_integrity 15/15 통과, mode_lock 7개 중 1 실패.

요지(원문은 세션 기록):
- 질문 1 맞음(높음). sdd 는 `.superpowers/sdd/.gitignore`(`*`)로 이미 무시, 미관리는 bt-check 8 + proposal 13 = png 21개(5.4MB). 표본 7장에 실명·키·호스트 없음(운영 캡처 2장은 로그인 전 백테스터, after-run 은 TEST devuser 가짜 값).
- 질문 2 맞음(높음). md·pdf 본문에 자격증명·이메일·전화·호스트·IP 0건. mcmax33 은 이미 공개 중. pdf 는 md 와 같은 내용.
- 질문 3 절반(높음). 커밋 후보 3(candle_validator·page_navigation·position_integrity), 보관 후보 4(mode_lock 실패 1, 스크립트형 3 미실행). `NETGUARD=1` 없이는 차단이 켜지지 않음.
- 질문 4 맞음(높음). html 바깥 주소는 Binance 공개 klines 3개뿐. txt 는 `!docs/new-version/*.txt` 예외 줄 권고.
- 질문 5 맞음(높음).
- 막음 1: 사실 8·㉢ 다시 쓰기. 막음 2: 「netguard 아래 실행」 표현 고치고 NETGUARD=1 로 다시 돌리기. 권고 3~7: 수치 정정, 사실 4 근거, txt 예외 줄, 보관 4개 선택지(숨김·삭제·그대로), mode_lock 실패 원인 한 줄(추정).

---

# 다시 묻기 (2회째): 막음 2건을 고쳤습니다

**고친 것 (PO 가 직접 다시 확인, 11/05):**
| # | 사실 | 확인/추정 | 근거 |
|---|---|---|---|
| 8′ | `UPBIT_ACCESS=netguard-placeholder UPBIT_SECRET=netguard-placeholder NETGUARD=1 PYTHONPATH=tests/_netguard python3 -m unittest tests.<이름>` (차단 켜짐): candle_validator 23 OK · page_navigation 14 OK · position_integrity 15 OK · mode_lock 7 중 1 FAIL(test_mode_match_proceeds_past_guard) | 확인 | 명령 출력 |
| 8″ | 1회째의 첫 실행은 NETGUARD=1 없이 돌아 차단이 꺼져 있었음(두 시험 모두 바깥 연결을 쓰지 않음) | 확인 | tests/_netguard/sitecustomize.py 끝 3줄 |
| 3′ | 미관리로 잡히는 `.superpowers` 파일은 png 21개(5.4MB). sdd 는 자체 `.gitignore`(`*`)로 이미 무시 | 확인 | `git status --short -uall .superpowers` 21줄 |
| 14 | mode_lock 실패는 engine_manager.py:398-403 「이미 같은 모드로 실행 중이면 False」(WO-12) 분기가 시험보다 뒤에 들어간 것으로 보임. 운영 코드 결함 아님 | 추정 | 코드 주석 「WO-12」, 시험 98~113줄 |

**고친 권고안:**
- ㉠ `.gitignore` 에 `.superpowers/` 추가(파일은 지우지 않음).
- ㉡ 6/23 md 2개 커밋, `docs/analysis/trading-performance/*.pdf` 무시.
- ㉢ 시험 3개(candle_validator·page_navigation·position_integrity) 그 자리 커밋, 게이트는 그대로. 남은 4개(mode_lock·order_ratio_verification·sell_filter_execution·tp_sl_integration)는 사용자 선택: 무시로 숨김(권고) / 삭제 / 그대로 둠.
- ㉣ `.gitignore` 에 `!docs/new-version/*.txt` 추가 후 docs/new-version 의 html·png 2·txt 커밋. Ver2 반영 여부는 별개.
- 모두 문서·무시 규칙·시험 파일 — 버전 갱신·서버 pull 없음.

**물어볼 것:** 고친 사실과 권고안으로 사용자에게 올려도 되는가.

---

# 답변 (2회째)

**판정:** 진행
**이유:** 8′·8″·3′ 는 Fable 실측과 같음. 사실 14 는 확인으로 올릴 수 있음 — `git log -L398,403:engine/engine_manager.py` → 0c8e729(2026-09-30, WO-12), 시험 수정 시각 2026-07-03, `docs/plans/2026-10-28-engine-recovery-fix/plan.md:465` 에 같은 판단 기록(PO 재확인 11/05).
- 권고 1: 사실 14 를 확인으로(반영). 권고 2: 보관 4개의 이유를 mode_lock(실패 1, 오래된 시험)과 스크립트형 3개(미실행, 결과 미확인)로 나눠 적기(반영).
- 사용자에게 물어야 할 것: 없음.
