버전: v1.2026.10.01.1740 → v1.2026.10.01.1955

# WO-17 (S) 배포 완료 보고 — 워밍업 긴 이력(800봉) 증분 시드 (2026-10-01)

- 결과: **배포 완료, 2(a)~(k)·3 전 항목 통과.** 되돌림 없음.
- 배포 대상: 코드 `bc8bbf1`, 문서 `962bb46` (push 대상 2건 확인 뒤 push)
- 서버: HEAD `962bb46`, `pages/dashboard.py` v1.2026.10.01.1955, 재시작 **2026-10-01 20:10:55 KST** (`systemctl restart tradebot`, active)
- 관찰: 20:10:55 ~ 20:40:55 무접속, 이후 운영자 대시보드 1회 접속(20:58:41)
- 투자자 안내: 없음(운영자 판정, `docs/operations/investor-notice-log.md` "통보 대상 아님" 표 기재). 서버 작업 중 포지션·주문 조작 없음
- 첨부: `server_log_excerpt.txt`(기동~관찰 종료·접속 확인), `verify_seed_output.txt`, `judgment_table.csv`, `wo16w_test_diff.txt`, `commands.txt`, `git_log.txt`

## 0. 배포 전 확인 (로컬)

| 확인 | 결과 |
|---|---|
| `git status` 추적되지 않은 변경 | 이번 변경 경로에는 없음. 저장소에 미추적 파일 13개(06-23 분석 문서 4개, `tests/test_*.py` 7개, `__pycache__` 2곳)가 있으나 **이 세션 시작 전부터 있던 파일**이며 이번 변경과 무관(세션 시작 git status 와 동일 목록) |
| `.gitignore` 해당 파일 포함 | `commands.txt`·`s-impl-test_results.txt` 는 `git add -f` 로 추적 중. params JSON 변경 없음. 무시된 것은 번들 zip 2개뿐(규칙상 제외) |
| 버전 문자열 | `pages/dashboard.py:495` `v1.2026.10.01.1955` |
| push 대상 | `git log origin/main..HEAD` = `962bb46`, `bc8bbf1` 2건 |

## 1. 판정표 (2(a)~(k), 3)

| 항목 | 기준 | 실측 | 판정 |
|---|---|---|---|
| (a) | 기동 티커마다 `[WARMUP] 시드 방식=long_history bars=800` 정확히 1줄 | KRW-JTO 1줄 (20:11:02 `ema_fast=734.9141 ema_slow=736.1272 ema_base=736.1272 \| 마지막 봉=20:05`). 기동 티커는 KRW-JTO 1개(`total_count=801` 요청 1건) | 통과 |
| (b) | `긴 이력 시드 실패` 0건 (코드 존재 먼저 확인) | 코드 `engine/live_loop.py:1126` 존재 확인 → journal 0, engine_debug.log 0, `시드 방식=sma200` 0 | 통과 |
| (c) | 텔레그램 `⚠️ 지표 시드 폴백` 0건 | 코드 `:1132` 존재 확인. 알림은 폴백 분기에서만 호출되며 그 분기 진입 0(b), `[NOTIFY]` 경고 0. notifier 는 성공 시 로그를 남기지 않으므로 "분기 미진입" 으로 판정 | 통과 |
| (d) | 로그 시드 값 vs 1,200봉 장기 기준: EMA60·EMA200 차이 0.1원 이내, fast−slow 부호 같음 | 800봉 재현 차이 −0.0000 / +0.0000, 1,200봉 기준 차이 **EMA60 −0.0000, EMA200 −0.0002**. fast−slow: 로그 −1.2131, 기준 −1.2129 (둘 다 음수) | 통과 |
| (e) | 버퍼·local_series 길이 200 | `✅ Buffer seeded \| buffer_len=200 \| bar_count=200`. local_series 시작 `local_start=2026-10-01 03:15:00`(첫 조정 로그) = 버퍼 200봉의 첫 봉(03:15 ~ 20:05) | 통과 |
| (f) | 첫 정합성 검증에서 로컬 시작 이전 약 200봉 제외, BACKFILL 대량(10건 이상)이면 결함 | 20:15:11 `로컬 시작 이전 봉 제외 \| n=199`, 20:20:11 n=198 … **BACKFILL 0건**(`누락 봉 평가 시작` 0) | 통과 |
| (g) | WO-16 (W): 미확정 봉이 시드·버퍼에 없음 | `다중 호출 완료 \| total=801` → `[WARMUP] 형성 중 봉 제거 \| ts=20:10 elapsed=62s \| 최종 봉 수=800 \| 최종 마지막 봉=20:05`. 시드·버퍼 마지막 봉 20:05(확정) | 통과 |
| (h) | WO-18: hts_buy 잔존 0 | 잔존 SQL 0, `[HTS-FLAG] 기동 정합 검사 완료 \| cleared=0` | 통과 |
| (i) | 결함 태그 0 | ` ERROR ` 0, Traceback 0, `[POS-DESYNC] class=` 0, VERIFY(`Upbit에 없는 timestamp`·`불일치 발견`·`과거 봉 검증 실패`) 0, POLLUTED 0, `database is locked` 0, `ON CONFLICT` 0, CRITICAL 0. WO-16 유지: 조정 6회 전부 `total=400`, VERIFY 범위 역전 0 | 통과 |
| (j) | Bar# 5 이상 진행 | Bar#201(20:15) → 202 → 203(20:25) → 204(20:35) → 205(20:40). 20:30 주기는 20:25 봉 무거래(Upbit 봉 없음) → 29회 재시도 뒤 `F1b ticks 체결 0건 → NO_TRADE`, `[CONFIRMED-NO-TRADE] … 봉 건너뜀`(기존 WO-6 동작) | 통과 |
| (k) | WO-12: systemd 기동으로 자동 재개 | `[BOOT-RESUME] start` 20:10:59 → `success … elapsed=6.4s` 20:11:01 → `[BOOT] run_live_loop start` 20:11:02. 관찰 창 `[AUTO-RESUME]` 0(접속 없음) | 통과 |
| 3 | 접속 1회: `[AUTO-RESUME] skip`, 엔진 스레드 1개, 화면 버전 1955 | 20:58:41 `[AUTO-RESUME] skip (boot-resume 로 이미 실행 중)` 1줄, 재시작 이후 `run_live_loop start` 1·`engine_runner 시작` 1, 접속 뒤 잠금·오류 0. **화면 버전 v1.2026.10.01.1955 — 운영자 육안 확인** | 통과 |

## 2. 지시와 다르게 처리한 점 (기록)

1. **로그 출처**: 지시의 로그 파일 `/root/upbit-tradebot-mvp/mcmax33_engine_debug.log` 에는 `[WARMUP]`·`[HTS-FLAG]`·`[RECONCILE]` 등 logger 줄이 기록되지 않는다(이 파일은 `log_to_file` 이벤트 — 엔진 시작, 조정 변경 감지, 봉 평가 요약 — 만 기록, `WARMUP` 0건). 판정은 systemd journal(`journalctl -u tradebot`)로 했고, 두 출처의 같은 구간을 모두 발췌에 넣었다.
2. **검증 스크립트 위치**: `wo17s_verify_seed.py` 는 저장소 `scripts/` 가 아니라 작업 폴더(scratchpad)에 있다(push 대상을 2건으로 묶기 위해 저장소에 추가하지 않음). 원문은 `commands.txt` 에 첨부했다.
3. **관찰 창 안 1분 주기 줄**: `ensure_settings_history_schema OK` 가 분당 약 7줄, `sync_all_positions cleared` 가 분당 약 89줄 나온다. 같은 줄이 배포 전 같은 길이 창(17:40~18:10)에도 180줄 있었고 `[AUTO-RESUME]` 은 0 이라, 대시보드 접속이 아니라 1분 주기 잔고 동기화의 정상 동작으로 판단했다.

## 3. 관찰 중 확인된 변경 효과

- 배포 직전 엔진(18:10 기동, 200봉 SMA 시드)은 20:05 봉에서 `cross=Golden | ema_fast=737.13 | ema_slow=732.09`(정배열) 상태였다(engine_debug.log 20:05:11).
- 새 시드는 같은 20:05 봉 기준 `ema_fast=734.9141 < ema_slow=736.1272`(역배열)이며, 1,200봉 장기 기준(734.9141 / 736.1270)과 일치했다. 이후 봉도 `cross=Dead` 로 이어졌다(20:45 734.32 / 735.87 …).
- G4 측정의 "현행 시드 부호가 장기 기준과 반대" 사례가 배포 순간에 그대로 재현되고 바로잡혔다. 관찰 창 안 주문·매수 신호 0건.

## 4. WO-16 (W) 시험 수정 전후 (`wo16w_test_diff.txt`)

`test_r_2026_10_01_wo16w_warmup_forming_trim` test_4 — 파일 전체에서 `indicators.seed_from_closes(closes)` 첫 등장 위치와 비교하던 것을, `run_live_loop` 본문 안에서 트림 → 시드(`_seed_warmup_indicators(` 또는 옛 호출) 순서를 보도록 바꿨다. 새 헬퍼가 `run_live_loop` 위에 정의되어 생긴 위치 차이 때문이며, 검사 취지(트림이 시드보다 먼저)는 같다. 옛·새 코드 모두 통과.

## 5. 실패 시 조치 (해당 없음)

- 조치 기준: `bc8bbf1` 단독 `git revert`(충돌 없음 사전 확인), `962bb46` 은 유지하고 문서에 "배포 보류" 기재 → push → 서버 pull → restart → status.
- 이번 배포는 전 항목 통과로 되돌리지 않았다.

## 6. 남은 일

- 투자자 통보 없음(확정). backlog·계획서 상태를 "완결" 로 갱신(이 문서 커밋).
- 사후 확인 거리: 다음 기동에서도 `시드 방식=long_history bars=800` 1줄·폴백 0 이 유지되는지 세션 시작 점검 때 본다.
