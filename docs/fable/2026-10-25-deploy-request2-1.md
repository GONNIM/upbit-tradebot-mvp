# 질의: 보완 배포 요청서(5692998 → 5367334, tradebot 재시작 포함)를 verifier 재검증까지 마쳤고, 사용자에게 배포 승인을 요청하려 합니다

**지금 단계:** 배포 요청서 (검수)
**다음에 하려는 일:** 사용자에게 보완 배포 승인 요청(결정 4개: S1~S6 한 번에 / 매매 중지·재개 실기 1회 시험 / 통보 문안 A′ / 실행 시각·새 세션)을 올립니다. 이번 단계에서 커밋·push·서버 변경은 없습니다. 요청서와 이 질의서는 배포 완료 보고 커밋에 묶습니다(문서만 — 따로 질의하지 않고 묶었음을 적음). 배포 실행은 승인 뒤 저장소 폴더 새 세션을 권합니다.

## 지금까지 확인한 사실
| # | 사실 | 근거 (명령·출력·파일 경로) |
|---|---|---|
| 1 | 요청서: S1 pull → S2 v2 재시작 → S3 tradebot 재시작(E1, d3_restart.sh) → S4 점검 → S5 허용 목록 → S6 확인·관찰 → S7 통보 | /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/deploy-request-20261025-2.md |
| 2 | 서버 정지선(23시대 읽기 전용): HEAD 5692998·1729, tradebot 17:10:35·NRestarts 0·ExecStart tradebot_boot.py, v2 17:48:27, 허용 목록 0바이트, .engine_alive.json 없음, mcmax33\|0, 미추적 5, minute3, 비밀 파일 600·사본 0 | PO ssh 실측, verifier 1차 판정표 1~10 |
| 3 | diff 33개, 매매 경로 0, tradebot 프로세스 변경은 tradebot_boot.py + dashboard.py 버전 줄 | `git diff --name-only 5692998 5367334` |
| 4 | 부록 A d3_restart.sh = 1차 D3 원문(diff SAME), 부록 B SQL 7개 = v2/api_read.py:59-87 상수, 서버 EXPLAIN TEMP B-TREE 0 | verifier 1차 27·36·37 |
| 5 | verifier 1차 「수정 후 승인」 지적 13건(통보 문안 시장가 전환 누락, POST 점검이 Origin 403 에 먼저 막힘, 런북 1회 원칙 불일치, 비밀 파일 점검 누락, 버전 구→신 누락 등) → 모두 반영 | verifier 보고, 요청서 |
| 6 | verifier 2차 「배포 승인 요청 가능」, 경미 R1(멈춤 조건이 200 만) → 「기대값과 다르면 멈춤」으로 반영 | verifier 2차 보고 |
| 7 | 1차 문안 A 는 미발송(D9) — 이번 A′ 하나로 대체 | HANDOFF 1022-05·1025-13 행 |
| 8 | 결정 1025-11 2 「엔진 재시작 없음」은 1차 D5 처리 한정, 이번 재시작은 1025-21 가(계획 8-1) | plan-pc-basic-20261025.md:128·131, HANDOFF:31 |

## 물어볼 것
| # | 질문 | PO의 생각 |
|---|---|---|
| 1 | 요청서의 순서·멈춤 조건·되돌리기가 실매매에 안전하고 계획·규칙과 맞는가 | 맞음 |
| 2 | 사용자 결정 4개(권고안 포함)가 사실·위험 면에서 올바르게 적혀 있는가 — 특히 결정 2(실기 중지/재개 1회, 포지션 없음·미체결 0 일 때) | 맞음 |

## 참고 파일
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/deploy-request-20261025-2.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/deploy-request-20261025.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/plan-pc-basic-20261025.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/operations/v2-runbook.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/scripts/tradebot_boot.py
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/v2/handlers.py
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/CLAUDE.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/.claude/context/project-rules.md

---

# 답변: 보완 배포 요청서(5692998 → 5367334, tradebot 재시작 포함)를 verifier 재검증까지 마쳤고, 사용자에게 배포 승인을 요청하려 합니다

**판정:** 진행
**이유:** 서버 정지선 값·diff 범위·부록 A/B 원문·코드 인용 줄을 직접 대조해 모두 맞음을 확인했습니다. 남은 지적은 결정 2 의 시험 시각 제한과 문구 정밀화 등 권고뿐입니다.

(직접 확인 요지 — 23:25 KST 서버 읽기 전용: HEAD 5692998·1729, tradebot 17:10:35·NRestarts 0·드롭인 wo12-boot.conf → tradebot_boot.py, v2 17:48:27·MemoryMax 150M, 허용 목록 0바이트, .engine_alive.json 없음, mcmax33|0, 미체결 0, 미추적 5, 비밀 파일 5개 600·사본 0, 최근 3시간 오류 0·CONFIRMED 52건. 부록 A diff SAME, 부록 B = api_read.py:59-87, handlers.py Origin 검사가 세션 검사보다 먼저, [ENGINE-ALIVE] 는 실패 때만. 미확인: 서버 EXPLAIN 재실행, 게이트 수치, verifier 보고 원문.)

## 질문별 답
| # | 질문 | 답 | 확신 정도 |
|---|---|---|---|
| 1 | 순서·멈춤 조건·되돌리기가 안전하고 계획·규칙과 맞는가 | 맞음 | 높음 |
| 2 | 결정 4개가 사실·위험 면에서 올바른가 | 사실은 맞음. 결정 2 에 시험 시각 제한이 없음(권고 1) — 중지가 봉 판정 시각에 걸리면 그 봉의 매수 신호가 막힘 | 높음 |

## 고쳐야 할 것
| # | 중요도 | 무엇을 | 왜 | 어떻게 확인하는지 |
|---|---|---|---|---|
| 1 | 권고 | 결정 2·2-6 시험에 「확정 봉 직후 시작, 다음 경계 60초 전까지 재개」 | strategy_engine.py:1088 게이트가 그 봉 BUY·SELL 을 건너뜀 | 시험 뒤 `[PAUSE] 실주문 스킵` 0건, audit_buy_eval trading_paused 새 행 0 |
| 2 | 권고 | 2-0 봉 간격 확인 파일을 active_strategy=EMA·params_EMA.json 으로 명시 | PULLBACK 파일엔 interval 키 없음 | 서버 grep |
| 3 | 권고 | 「21시대」·「23시대」 표기 통일 | 표기 불일치 | 문구 대조 |
| 4 | 권고 | RSS 값에 명령·단위 병기 | 23:25 실측 160108KB(약 156MB) | ps 값 |

## 사용자에게 물어야 할 것
- 없음 (요청서 6절 결정 4개가 그대로 사용자 질문)

## PO 처리
- 권고 1~4 모두 요청서에 반영(10/25 23시대). `[PAUSE] 실주문 스킵` 문자열은 core/strategy_engine.py:1089, 서버 mcmax33_active_strategy.txt = EMA 를 PO 가 확인.
- 이 단계 규칙 위반 자진 기재: PO 가 빈 heredoc 1회 사용(파일 끝 확인 중, 실행된 것 없음·무해).
