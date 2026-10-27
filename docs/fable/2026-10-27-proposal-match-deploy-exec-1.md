# 질의: 1차 배포(1027-06) 2-0 정지선을 마쳤고, ERROR 판정 기준 1곳을 고쳐 2-1~2-6 을 실행하려 함

**지금 단계:** 배포 실행 직전 (요청서 2-0 정지선 끝)
**다음에 하려는 일:** 요청서 `deploy-request-20261027-proposal-match.md` 2-1(pull 627b136 → 1747fcc)·2-2(tradebot-v2 재시작만)·2-3 점검·2-4 운영자 확인·2-5 30분 관찰·2-6 완료 보고를 한 번에 실행한다(결정 1027-05 1 「한 번에」). 엔진(tradebot) 재시작 없음, `deploy-tradebot` 쓰지 않음. 이때 2-0·2-3·2-5 의 엔진 ERROR 판정만 「`insufficient_funds_ask` 가 든 줄을 뺀 `ERROR|Traceback|CRITICAL|database is locked` 수 = 0」으로 바꾸고(결정 1027-12 가), 뺀 줄 수는 따로 적는다. 묶음(작은 문서 변경): HANDOFF 0-1 표에 1027-06 상태·1027-12 결정 행을 적는다(미커밋, 배포 완료 보고 문서 커밋에 함께 넣음 — 커밋은 승인 별도).

## 지금까지 확인한 사실
| # | 사실 | 근거 (명령·출력·파일 경로) |
|---|---|---|
| 1 | 로컬 HEAD = origin/main = 1747fcc, dashboard.py:495 v1.2026.10.27.1522. 추적 변경은 HANDOFF `M` 1건뿐(시작 지시가 정상이라고 적음) | `git rev-parse HEAD origin/main`, `git status --short` |
| 2 | `git diff --name-only 1d0466a HEAD` = docs 9·pages/dashboard.py(버전 줄 1줄)·tests/v2/test_candles.py·v2/candles.py. `627b136..HEAD` 53파일, v2/tests/docs 밖은 pages/dashboard.py·ui/v2_entry.py 둘, 엔진 경로 0 | 로컬 git diff |
| 3 | 서버: HEAD 627b136, 파일 버전 1209, tradebot active·00:25:22·NRestarts 0, tradebot-v2 active·17:34:30·NRestarts 0, 허용 목록 8B, 미추적 5건, tornado 6.5.1, fileWatcherType none, 여유 20G, v2_candles 없음, TLSv1.3 tls-ok, users `mcmax33\|0`, 비밀 파일 5개 600 root, 사본 0 | scratchpad `stopline.sh` (10/27 16:38:24 실행, 읽기 전용) |
| 4 | 엔진 시세 실패 표지 24시간: 요청서 2-0 의 11개 문자열 모두 0 | 같은 스크립트 |
| 5 | 처리한 봉 24시간: 봉 처리 완료 333 + CONFIRMED-NO-TRADE 152 = 485, 고유 ts 480 (기준 486 / 약 480) | 같은 스크립트 |
| 6 | **다른 1건:** 엔진 최근 1시간 `ERROR\|Traceback\|CRITICAL\|database is locked` = 15 (기대 0). 15건 = `[SELL-LIVE] FAILURE … insufficient_funds_ask` ERROR 9줄 + `[NOTIFY] sent kind=CRITICAL dedupe=sell_reject:KRW-JTO:insufficient_funds_ask` INFO 6줄. 모두 `insufficient_funds_ask` 를 포함 | `journalctl -u tradebot --since '1 hour ago' \| grep -E …` |
| 7 | 원인: 09:22:14 `[HTS-DETECT] HTS_BUY` JTO 411.943546 @581(앱 매수) → 09:48:21 `[LOCKED-QTY] 매도 불가 — 앱 지정가 매도 주문으로 수량 묶임` 가용 0·묶임 411.94 → 10:30:11 부터 3분봉마다 STALE_POSITION 시장가 매도 시도 → 400 insufficient_funds_ask. 10:00 이후 `[AUDIT-REJECT] SELL_REJECTED` 78건(전부 reason=STALE_POSITION), 알림 50건 | journalctl grep `JTO`·`LOCKED-QTY`·`AUDIT-REJECT` |
| 8 | 24시간 그 밖의 ERROR 계열: `database is locked` WARNING 2줄(SETTINGS-SNAPSHOT, INVARIANT_MONITOR 「무해」 표기). WARNING 이라 `ERROR` 에는 안 걸리지만 `database is locked` 문자열로는 걸림 — 시각은 최근 1시간 밖 | 24h uniq 집계 |
| 9 | 이 거절은 외부(앱) 주문 공존 규칙(project-rules 2026-09-30)대로 알림·감사 로그로 가시화돼 있고, v2 배포와 경로가 겹치지 않음(v2 는 공개 캔들만, 계좌·주문 0 — 요청서 4절) | project-rules.md 「외부 주문 공존」, 요청서 4절 |
| 10 | 사용자 결정 1027-12 「가」: 배포 계속, 판정에서 JTO 거절 줄을 따로 셈. 사용자에게 「앱 지정가 매도를 취소하면 엔진이 다음 봉에 전량 시장가 매도」를 알림 | 이 세션 보고 |

## 물어볼 것
| # | 질문 | PO의 생각 |
|---|---|---|
| 1 | 2-0 의 다른 1건(사실 6)을 위 기준 변경으로 통과로 보고 2-1 로 가도 되는가 | 된다. 원인이 외부 주문으로 확정됐고 엔진 시세·봉 처리 지표는 기준과 같다 |
| 2 | 기준 변경 문구: 「`grep -E 'ERROR\|Traceback\|CRITICAL\|database is locked' \| grep -vc insufficient_funds_ask` = 0, 뺀 줄 수 따로 기록」을 2-0·2-3·2-5 에 쓰는 것이 충분한가 | 충분. 단 관찰 중 운영자가 앱 주문을 취소해 엔진 매도가 체결되면 그것은 이상이 아니라 정상 매매로 기록만 한다 |
| 3 | 관찰 중 `insufficient_funds_ask` 말고 다른 매도·매수 거절 코드가 나오면 멈춤으로 보는가 | 멈춤(tradebot-v2 stop 후 보고)으로 본다 — 원래 기준 그대로 |
| 4 | HANDOFF 표 갱신을 지금 미커밋으로 해 두고 배포 완료 보고 문서 커밋에 묶는 것이 괜찮은가 | 괜찮다(시작 지시와 같은 방식) |

## 참고 파일
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/deploy-request-20261027-proposal-match.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/HANDOFF.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/.claude/context/project-rules.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/CLAUDE.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/fable/2026-10-27-proposal-match-deploy-request-1.md
- /private/tmp/claude-501/-Users-gonnim-Project-MVP-Source-upbit-tradebot-mvp/dd150dcc-cae1-4eb6-8c9b-349ec16c8d7b/scratchpad/stopline.sh

---

## Fable 답변서 전문 (10/27 16:4x, Agent model fable)

# 답변: 1차 배포(1027-06) 2-0 정지선을 마쳤고, ERROR 판정 기준 1곳을 고쳐 2-1~2-6 을 실행하려 함

**판정:** 진행
**이유:** 로컬·서버 정지선 값과 「다른 1건」의 원인(앱 지정가 매도 주문으로 수량 묶임 → STALE_POSITION 매도 거절 반복)을 SSH 읽기 전용으로 직접 재확인했고 질의서 사실과 모두 맞습니다. 거절은 엔진 계좌 경로의 일이고 이번 배포(v2 공개 캔들만)와 겹치지 않으며, 고칠 것은 모두 권고입니다.

## 사실 대조 (직접 확인, 10/27 16:44~16:45 KST)
- 사실 1·2: 확인됨. 로컬 HEAD = origin/main = `1747fcc`, `pages/dashboard.py:495` v1.2026.10.27.1522, 추적 변경은 HANDOFF 1건(1027-06 행 1줄만 바뀜). `1d0466a..HEAD` 12파일, `627b136..HEAD` 에서 v2/tests/docs 밖은 `pages/dashboard.py`·`ui/v2_entry.py` 둘뿐.
- 사실 3: 확인됨(HEAD 627b136, 파일 버전 1209, tradebot active·00:25:22·NRestarts 0, tradebot-v2 active·17:34:30·NRestarts 0, 허용 목록 8B, 미추적 5, v2_candles 없음, 비밀 파일 5개 600 root, 사본 0). tornado·fileWatcherType·디스크·TLS·users 값은 다시 재지 않음 — 미확인.
- 사실 4: 확인됨(11개 표지 24시간 모두 0).
- 사실 5: 확인됨(16:45 기준 332 + 153 = 485, 고유 ts 480).
- 사실 6: 확인됨. 16:44 기준 최근 1시간 17건(16:38 기준 15건에서 2건 늘어남), `insufficient_funds_ask` 를 빼면 0. 줄 모양은 `[SELL-LIVE] FAILURE → Upbit error [insufficient_funds_ask]` ERROR 와 `[NOTIFY] sent | kind=CRITICAL dedupe=sell_reject:KRW-JTO:insufficient_funds_ask` INFO 두 가지뿐.
- 사실 7: 확인됨(09:22:14 HTS_BUY 411.943546 @581, 09:48:21 LOCKED-QTY 가용 0·묶임 411.94, 10:30:10 STALE_POSITION 첫 판정 → 10:30:11 첫 AUDIT-REJECT, 24시간 AUDIT-REJECT 78건 전부 reason=STALE_POSITION code=insufficient_funds_ask, sell_reject 알림 50건, 다른 거절 코드 0).
- 사실 8: 확인됨(`database is locked` 24시간 2건, 10/26 17:33:06 SETTINGS-SNAPSHOT·10/27 03:18:13 INVARIANT_MONITOR, 둘 다 WARNING, 최근 1시간 밖).
- 사실 9: 확인됨(`[AUDIT-REJECT] SELL_REJECTED 기록` 으로 감사 테이블, CRITICAL 알림. `core/trader.py:1333~1360`). v2 계좌·주문 0 은 요청서 4절 기재, 코드로 다시 보지 않음.
- 사실 10: 미확인(세션 메시지).
- 「앱 지정가 매도를 취소하면 엔진이 다음 봉에 전량 시장가 매도」: 조건부로 맞음. 수량은 가용+묶임 합계(`core/trader.py:352~357`). STALE_POSITION 은 「보유 1시간 이상 + 최대 수익률 0.30% 미만」(`core/filters/sell_filters.py:553` 근처)이라 취소 시점에 581 대비 0.3% 넘게 올라 있으면 그 봉에서는 안 팔 수 있음.

## 질문별 답
| # | 질문 | 답 | 확신 정도 |
|---|---|---|---|
| 1 | 기준 변경으로 통과 보고 2-1 진행 | 됩니다. 17건 전부 외부 주문 묶임 두 줄 모양, 표지 0·봉 485/480. v2 는 계좌·주문을 부르지 않아 배포가 이 상태를 바꾸지 않음 | 높음 |
| 2 | 기준 문구 충분한가 | 거의 충분. 뺀 줄 모양을 숫자 가리고 `sort \| uniq -c` 로 적어 두 가지뿐임을 함께 기록. 취소로 매도 체결되면 정상 매매로 기록만 | 높음 |
| 3 | 다른 거절 코드 → 멈춤 | 맞음. stop 은 안전 조치, 실제 할 일은 원인 보고. 24시간 다른 코드 0 | 높음 |
| 4 | HANDOFF 미커밋 묶음 | 괜찮음. 완료 보고에 「HANDOFF 1건 예외(시작 지시)」 기재 | 높음 |

## 고쳐야 할 것
| # | 중요도 | 무엇을 | 왜 | 어떻게 확인하는지 |
|---|---|---|---|---|
| 1 | 권고 | 뺀 줄 수 + 뺀 줄 모양 목록(숫자 가림 `uniq -c`), 모양이 두 가지뿐일 때만 통과 | 새 오류 줄이 수 안에 숨을 수 있음 | 출력 2줄 |
| 2 | 권고 | 30분 관찰에서 `database is locked` 가 나오면 탐침·`check_v2_unit.sh` 실행 시각과 대조 | v2 영향인지 가리기 | 두 시각 기재 |
| 3 | 권고 | 사용자 안내에 「STALE_POSITION 조건이 그대로일 때」 붙이기 | 0.3% 넘게 오르면 안 팔릴 수 있음 | sell_filters.py 조건 |
| 4 | 권고 | 완료 보고 2-0 에 「1시간 ERROR 류 17건(16:44) 전부 insufficient_funds_ask, 뺀 뒤 0」·「HANDOFF 1건 예외」 | 요청서 기준과 실측 차이 기록 | 완료 보고 2-0 표 |
| 5 | 권고 | 거절 알림이 계속 감(24시간 50건)을 한 줄 | 알림 소음은 별개 사항 | `grep -c 'dedupe=sell_reject'` |

## 사용자에게 물어야 할 것
- 없음
