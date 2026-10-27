# 신버전 대시보드 배포 완료 보고 (2026-10-27, 1차 화면 — 승인 요청서 그림과 같게 + IP 차단 방지 4-0b)

**한 줄:** 서버를 `627b136`(v1.2026.10.26.1209)에서 `1747fcc`(v1.2026.10.27.1522)로 올리고 `tradebot-v2` 만 16:47:19 에 재시작했습니다. 엔진(`tradebot`)은 재시작하지 않았습니다(기동 10/26 00:25:22 그대로). 2-0~2-5 30분 관찰·운영자 확인·최악 경우 메모리 1회를 모두 마쳤고, 24시간 확인(1026-06)만 남았습니다.

**근거:** 요청서 `deploy-request-20261027-proposal-match.md`, 결정 1027-05(한 번에·새 세션·문안대로·IP 차단 방지·문서 커밋 포함)·1027-12(가 — JTO 거절 줄 따로 셈)·1027-13(운영자 확인함)·1026-04(A″ 보냄)·1027-15(이 보고 커밋 승인). 실행 직전 Fable `docs/fable/2026-10-27-proposal-match-deploy-exec-1.md` 「진행」(권고 5건 반영).

버전: v1.2026.10.26.1209 → v1.2026.10.27.1522 (서버 파일 기준, 구버전 화면 2058·입장 단추는 다음 엔진 재시작 때)

**서버 실행본 = `1747fcc`(v1.2026.10.27.1522).** 이 보고를 넣은 문서 커밋 뒤에는 GitHub HEAD 가 서버보다 1커밋 앞서고, 파일 버전은 GitHub `v1.2026.10.27.1752` / 서버 `v1.2026.10.27.1522` 로 다릅니다. 문서만 바뀐 커밋이라 서버 pull 은 하지 않습니다(의도된 불일치 — 다음 세션 정지선에서 멈추지 않음).

## 1. 3점 일치 (10/27 17:4x KST)
| 점 | 값 | 근거 |
|---|---|---|
| 로컬 | HEAD `1747fcc`(배포 시점), `pages/dashboard.py:495` v1.2026.10.27.1522 | `git rev-parse HEAD`, origin/main 같음 |
| 서버 | HEAD `1747fcc`, 파일 버전 v1.2026.10.27.1522, 구버전 화면 버전 2058 | SSH `git rev-parse HEAD`, `grep -n v1.2026` |
| 엔진 | `tradebot` ExecMainStartTimestamp `Mon 2026-10-26 00:25:22 KST`, NRestarts 0 | `systemctl show tradebot` (17:41 재확인) |

`tradebot-v2` 는 active, ExecMainStartTimestamp `Tue 2026-10-27 16:47:19 KST`, NRestarts 0.

- 1026-17(PC 차트 배포 완료 보고, 10/26)은 이 보고에 합칩니다: 그 배포의 3점은 서버 `627b136`·파일 버전 1209 / 화면 2058 / tradebot 00:25:22 였고, tradebot-v2 재시작 10/26 17:34:30, 30분 관찰(~18:05) v2 오류 0·RSS 30,132KB·엔진 오류·한도 0 (HANDOFF 0절 10/26 18시 기록).

## 2. 실행 결과
| 단계 | 결과 | 시각 |
|---|---|---|
| 2-0 정지선 | 2건 외 모두 기대값과 같음 — ERROR 류 1건(결정 1027-12), 추적 변경 HANDOFF 1건(시작 지시로 예외) (아래 2-1절) | 16:38:24 |
| 실행 직전 Fable | 「진행」, 권고 5건 | 16:4x |
| 2-1 pull | 627b136 → 1747fcc, `--ff-only`, 파일 53개(2-0 과 같음), v2/tests/docs 밖은 `pages/dashboard.py`·`ui/v2_entry.py` 둘, 엔진 경로 0, 서버 미추적 5건 그대로 | 16:47 |
| 2-2 v2 재시작 | active, journal Traceback·ERROR 0, tradebot 00:25:22 그대로 | 16:47:19 |
| 2-3 점검 | `check_v2_unit.sh mcmax33` PASS 13 (FAIL 0, `live-db-write-lock`·`proc-environ-blocked` 포함 PASS), `mcmax33\|0` | 16:47:40 |
| 2-3 응답 머리 | `/v2/static/bt_ui.js` 200·`Cache-Control: no-cache` | 16:4x |
| 2-3 세션 없는 API | `/v2/api/basic`·`/v2/api/candles?…`·`/v2/api/candles/progress` 401, POST `/v2/api/pause` Origin 없음 403 `forbidden_origin`, Origin 있음 401 | 16:4x |
| 2-3 미리 받기 | 16:52:2x 시작 → 16:53:20 `KRW-JTO_3.json` 486,478B `-rw-------` root, 폴더 `drwx------`, `.tmp`·`.halt.json` 없음, `[V2-CANDLES]` 0줄. 그 뒤 10분마다 갱신(17:13:20·17:23:20·17:33:21) | 16:53:20 |
| 2-3 메모리(미리 받기) | anon 18.8 MiB → 최고 22.7 MiB, 끝난 뒤 22.4 MiB / file 7.7 → 7.5 → 8.1 MiB (MemoryCurrent 28.1 → 32.3 MB), 15초 간격 | 16:47~16:54 |
| 2-4 운영자 확인 | 사용자 「1027-13 확인함, 백테스트 1초 미만」 (엔진 종목 3분봉 30일) | 17:2x |
| 2-5 30분 관찰 | 아래 2-2절 | 16:47:19~17:16:47 |
| 최악 메모리 1회 | 아래 2-3절 | 17:30:51~17:40:53 |
| 통보 A″ | 사용자 「1026-04 보냄」, `investor-notice-log.md` #6 | 17시대 |

### 2-1. 2-0 정지선에서 다른 2건 (결정 1027-12 가 · 시작 지시 예외)
| 항목 | 기대 | 실측 |
|---|---|---|
| 엔진 최근 1시간 `ERROR\|Traceback\|CRITICAL\|database is locked` | 0 | 15 (16:38), Fable 재확인 17 (16:44) — 전부 `insufficient_funds_ask` 포함, 뺀 뒤 0 |
| 추적 변경 | 0 | HANDOFF `M` 1건 (시작 지시가 정상으로 적음) |

- 원인: 09:22:14 앱 매수 `[HTS-DETECT] HTS_BUY` KRW-JTO 411.943546 @581 → 09:48:21 `[LOCKED-QTY]` 앱 지정가 매도 주문으로 전량 묶임(가용 0) → 10:30:11 부터 STALE_POSITION 시장가 매도가 매 판정마다 400 `insufficient_funds_ask`. 감사 로그 `SELL_REJECTED`·CRITICAL 알림으로 가시화됨(외부 주문 공존 규칙). v2 는 계좌·주문을 부르지 않아 배포와 경로가 겹치지 않음.
- 판정 기준(2-0·2-3·2-5): `insufficient_funds_ask` 가 든 줄을 뺀 수 = 0, 뺀 줄은 모양을 숫자 가려 `uniq -c` 로 적고 두 가지 모양일 때만 통과(Fable 권고 1).
- 10/27 0시~17:33 뺀 줄 모양: `[SELL-LIVE] FAILURE → Upbit error [insufficient_funds_ask]` ERROR 80, `[NOTIFY] sent | kind=CRITICAL dedupe=sell_reject:KRW-JTO:insufficient_funds_ask` INFO 51. 거절 코드는 `insufficient_funds_ask` 하나(80건, 전부 reason=STALE_POSITION). 매도 체결 0.
- 거절 알림이 계속 나간다(24시간 50건, Fable 권고 5). 앱 지정가 매도를 취소하면 STALE_POSITION 조건(보유 1시간 이상·최고 수익률 0.30% 미만)이 그대로일 때 엔진이 다음 3분봉에 전량(411.94) 시장가 매도한다(Fable 권고 3, `core/filters/sell_filters.py`, `core/trader.py:352~357`).

### 2-2. 30분 관찰 (16:47:19~17:16:47)
| 항목 | 기준 | 결과 |
|---|---|---|
| 엔진 시세 실패 표지 11개 문자열 | 0 | 0 |
| 엔진 ERROR 류(JTO 거절 뺀 뒤) | 0 | 1 — 17:11:03 `[SETTINGS-SNAPSHOT] ❌ Failed: database is locked` (WARNING) |
| 처리한 봉 | 30분에 10개 안팎 | 봉 처리 완료 6 + CONFIRMED-NO-TRADE 4, 고유 10 |
| v2 ERROR·Traceback / `[V2-CANDLES]` | 0 / 0 | 0 / 0 |
| tradebot 기동 시각 | 00:25:22 | 00:25:22, NRestarts 0 |

- 17:11:03 잠김 대조(Fable 권고 2): 17:10:40~17:11:10 사이 tradebot-v2 journal 은 「No entries」, 탐침(`check_v2_unit.sh`)은 16:47:40. 배포 뒤 v2 요청은 모두 401·403(세션 없음 → DB 열지 않음). 같은 시각 엔진 로그에 구버전 화면의 `[migrate] ensure_settings_history_schema OK` 가 1초마다 찍혀 구버전 화면이 열려 있었다. 엔진 프로세스 안 다툼으로 판정, v2 영향 아님. `database is locked` 는 배포 전에도 있었다: 배포 전 7일 3건 — 10/23 05:53:07 `engine.order_reconciler [OR] periodic sync failed` **ERROR** 1건, 10/26 17:33:06 SETTINGS-SNAPSHOT·10/27 03:18:13 INVARIANT_MONITOR **WARNING** 2건(이 2건이 배포 전 24시간). 배포 뒤는 17:11:03 1건(verifier 10/27 17:54 재집계). 요청서 2-5 의 기대값 「`database is locked` 0」과 글자로 다르나 이 대조로 멈추지 않았다.
- 관찰 중 v2 `/v2/api/status`·`/v2/api/assets` 401 각 20회, `basic` 10(탐침 1 포함)·`signals` 11·`trades` 11 — 재시작 전부터 열려 있던 신버전 탭이 세션 없이 조회한 것으로 보임(2-4 재입장 뒤 해소 기대, 미확인).

### 2-3. 최악 경우 메모리 1회 (17:30:51~17:40:53, 1초 간격 600회)
- 조건: 30분 관찰 실패 표지 0, 17:30:13 `✅ [CONFIRMED] 봉 처리 완료` 직후 시작.
- 운영자: KRW-BTC 1분·30일 「데이터 가져오기 + 백테스트」 1회 + 그 사이 엔진 종목 백테스트 1회. 체감 「10초 이상」(사용자).
- 결과: `KRW-BTC_1.json` 2,744,910B 17:32:36 생성. anon 최고 **36.4 MiB**(37,260 KiB, 17:31:16) — 기준 75 MiB 이하. 끝난 뒤 33.5 MiB, MemoryCurrent 44.1 MB(MemoryMax 150M). 이 구간의 `file` 값은 1초 기록 스크립트가 anon 만 읽어 미기록(17:33:38 단발 1회: anon 33.5 MiB·file 8.2 MiB).
- 걸린 시간(추정): anon 최고 시각 17:31:16 ~ 파일 생성 17:32:36 ≈ 80초. 로컬 실측(창 1번 만남 81.3초)과 맞는다. v2 접근 로그는 2xx 를 남기지 않아 요청 시각 원문은 없음(미확인).
- 이 구간 `[V2-CANDLES]` 0줄(429·418 0), 엔진 시세 실패 표지 0, 엔진 ERROR 류(JTO 거절 뺀 뒤) 0, v2 ERROR 0, tradebot 00:25:22·NRestarts 0.
- 통보 문안 A″ 의 「처음 받는 종목은 1분~1분 30초」는 이 값과 맞아 고치지 않았다(요청서 5절 단서).

## 3. 남은 것
| # | 할 일 | 조건 |
|---|---|---|
| 1026-06 | 24시간 확인: 실패 표지 8종 배포 뒤 24시간 0, 처리 봉 합계 ≥ 480·고유 ≥ 478 | 10/28 16:47 이후 (요청서 2-5) |
| 1027-04 | 다음 엔진 재시작 직후 입장 단추 한 번 누르기·화면 버전 확인, 투자자 한 줄 통보 | 엔진 재시작 뒤 |
| 1026-22 | 2차 계획(새 전략 실매매·전환) | 사용자 신호 |

## 4. 관찰 방법 메모
- PO 관찰 스크립트(scratchpad `engine_check.sh`)는 서버 `/tmp` 에 `mktemp` 임시 파일을 만들고 지웠다(무해, 「읽기 전용」 원칙과 글자로 다름 — verifier). 1026-06 24시간 확인은 파이프로만 집계한다.

## 5. 이 세션 규칙 위반
- 10/27 17:4x 빈 셸 heredoc 1회(`python3 - <<'PYEOF'` 빈 본문, HANDOFF 편집 준비 중). 실행된 것 없음, 무해. 곧바로 파일 도구로 편집했다.
- 10/27 17:5x Fable 커밋 질의 답변 작성 중 Fable 이 비교 스크립트(`cmp.py`)를 셸 heredoc 으로 1회 씀(무해, 저장소·서버 변경 없음 — Fable 답변서 권고 4).
