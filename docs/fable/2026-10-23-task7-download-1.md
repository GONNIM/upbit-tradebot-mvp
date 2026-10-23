# 질의: Task 7 Step 1(Binance 고정 입력 3세트 내려받기) 승인을 사용자에게 요청하려 합니다

**지금 단계:** 구현 (Task 6 커밋·push 완료 → Task 7 착수 전 사용자 결정 요청)
**다음에 하려는 일:** 사용자에게 「Binance 공개 시세 klines 를 한 번 내려받아 시험 고정 입력 3세트로 저장」하는 것의 승인을 요청합니다. 승인을 받으면 PO 가 로컬에서 내려받기 스크립트(scratchpad, 저장소 밖)를 실행해 `tests/v2/js/fixtures/klines_{a,b,c}.json` 을 만들고 `.gitignore` 에 `!tests/v2/js/fixtures/*.json` 예외를 더합니다. 커밋은 Task 7 끝에 따로 승인을 받습니다. Task 7 의 지시서·Step 2 이후는 이 질의 범위 밖입니다(착수 질의를 따로 합니다).

## 지금까지 확인한 사실
| # | 사실 | 근거 |
|---|---|---|
| 1 | Task 6 커밋 23569db, push 완료(194a134..23569db), 원격과 같음 | git log, progress.md |
| 2 | 계획서 Task 7 Step 1 은 「사용자 확인 후 — 외부 내려받기」로 원본 기본값 1세트 + 심볼·기간 다른 2세트, 받은 시각 기록 | plan.md:198 |
| 3 | 원본은 `data-api.binance.vision/api/v3/klines` 를 먼저, 실패 때 `api.binance.com` 을 부르고, 키 없음, limit=1000 으로 반복 | MA60_200_…_2610201820.html:154-180 |
| 4 | 원본은 x[0]~x[4](시각·시가·고가·저가·종가)만 읽음 → 6번째 이후 열은 결과에 영향 없음 | 같은 파일:176 (답변 1 권고로 175→176 정정) |
| 5 | 원본 기본 입력: 심볼 JTOUSDT, 원본 봉 3분, 기간 30일 | 같은 파일:58·62·63 (답변 1 권고로 61→62 정정) |
| 6 | 원본 기간 계산이 `Date.now()` 를 씀 → harness 는 받은 시각을 고정 Date.now 로 써야 요청 수·봉 수가 같음 | 같은 파일:157, plan.md:197 |
| 7 | `.gitignore` 34행 `*.json` 이라 예외 줄이 없으면 고정 입력이 커밋되지 않음 | .gitignore:34 |
| 8 | 저장소는 공개. Binance 공개 시세 데이터만 담기고 키·계정 정보 없음 | gh repo view (세션 앞부분) |

## 제안 3세트 (사용자에게 올릴 안)
| 세트 | 심볼 | 봉 | 기간 | 예상 봉 수 / 요청 수 |
|---|---|---|---|---|
| a | JTOUSDT | 3m | 30일 (원본 기본) | 약 14,400 / 15 |
| b | BTCUSDT | 5m | 60일 | 약 17,280 / 18 |
| c | ETHUSDT | 1m | 7일 | 약 10,080 / 11 |

- 저장은 받은 응답의 앞 5열만(사실 4), 파일당 약 0.6~0.9MB 예상, 3개 합 3MB 이내. 각 파일에 `fetched_at_ms`(받은 시각)·요청 URL 목록을 함께 둡니다.
- 외부 요청은 Binance 공개 엔드포인트 약 44회, 1회 실행. 실매매·서버·DB 영향 없음.

## 물어볼 것
| # | 질문 | PO의 생각 |
|---|---|---|
| 1 | 사실 3~7 이 맞고, 3세트 안이 계획서(plan.md:198)·spec A6(같은 입력 3세트)에 맞는가 | 맞음 |
| 2 | 앞 5열만 저장해도 원본·이식본 비교(CSV·요청 수·봉 수)가 성립하는가 | 성립 |
| 3 | 공개 저장소에 3MB 이내 시세 데이터를 커밋하는 위험이 사용자에게 알릴 만큼 있는가 | 낮음, 승인 요청에 한 줄로 알림 |
| 4 | 사용자에게 내려받기 승인을 요청해도 되는가 | 예 |

## 참고 파일
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/plan.md (190-206행)
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/spec.md (141-144행, 223행)
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/MA60_200_GoldenCross_Pullback_Backtester_2610201820.html
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/.gitignore
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/.superpowers/sdd/plan/progress.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/CLAUDE.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/.claude/context/project-rules.md

---

# 답변 1

**판정:** 멈춤
**이유:** 사실 3~7 과 3세트 안은 원본 HTML·plan.md:198·spec A6 와 맞고 「막음」은 없습니다. 남은 일은 계획서가 「사용자 확인 후」로 정한 외부 내려받기 승인뿐이라 사용자에게 물은 뒤 진행합니다.

## 질문별 답
| # | 질문 | 답 | 확신 정도 |
|---|---|---|---|
| 1 | 사실 3~7·3세트 안이 plan.md:198·spec A6 에 맞는가 | 맞음. 행 번호 두 곳(176·62)만 한 줄씩 어긋남. `.gitignore:34` 확인, 상위 폴더 제외 없어 예외 줄 유효. 예상 봉 수·요청 수 계산 맞음. 사실 8 은 네트워크 금지로 미확인 | 높음 (사실 8 만 미확인) |
| 2 | 앞 5열만 저장해도 비교가 성립하는가 | 성립. 원본은 x[0]~x[4] 와 마지막 행 0번 열만 씀. 요청 수는 가짜 fetch 구현(Step 2) 몫 | 높음 |
| 3 | 공개 저장소에 시세 데이터를 커밋하는 위험 | 낮음. 다만 이력에 영구히 남고, 원문 문자열 저장이면 합 약 3.6MB 라 「약 4MB 이내」가 정확 | 보통 |
| 4 | 사용자에게 승인을 요청해도 되는가 | 예 | 높음 |

## 고쳐야 할 것
| # | 중요도 | 무엇을 |
|---|---|---|
| 1 | 권고 | 사실 4 행 번호 175→176, 사실 5 61→62 |
| 2 | 권고 | 용량 「약 4MB 이내」, 「git 이력에 영구 보관」 한 마디 |
| 3 | 권고 | 파일에 symbol·interval·days·fetched_at_ms 명시, 봉은 응답 문자열 그대로 앞 5열 |
| 4 | 권고 | 내려받기는 원본 154~183행 반복 그대로(end 는 세트당 한 번), 요청 URL 목록 저장 |
| 5 | 권고 | 스크립트는 Write 로 scratchpad 에 쓰고 python3 로 실행, heredoc 금지 |
| 6 | 권고 | 사실 8 은 PO 가 gh repo view 로 다시 확인 |

## 사용자에게 물어야 할 것
- Binance 공개 klines 1회 내려받기(요청 약 44회, 키 없음) → fixtures 3개(합 약 4MB 이내) 저장과 `.gitignore` 예외 추가 승인. 커밋은 Task 7 끝에 따로.

## PO 반영 (10/23)
- 권고 1: 12·13행 정정. 권고 6: `gh repo view` 결과 PUBLIC 재확인. 권고 2: 승인 요청문에 반영. 권고 3~5: 승인 뒤 내려받기 때 반영.
