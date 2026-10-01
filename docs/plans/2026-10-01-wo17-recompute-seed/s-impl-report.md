# WO-17 (S) 구현 보고 — 워밍업 긴 이력(800봉) 증분 시드 (로컬 완료, 배포 대기)

- 작성일: 2026-10-01
- 승인: [WO-17 (S) 구현 승인] — 판정 근거: 기동 13회 중 3회 현행 시드 fast−slow 부호가 장기 기준과 반대, 거짓 교차 실매매 손실 2왕복, B 는 C 와 0.02원 이내. **투자자 통보 대상 아님(지표 설계 정정, 운영자 판정).** 범위 계획서 §2 (S), G3 확정값(800봉)
- 상태: **로컬 커밋만, push·배포 안 함**
- 근거 파일: `s-impl-test_results.txt`(테스트 결과), `wo17s_boot9_compare.csv`(기동 9 재현 비교표), `commands.txt`(명령·스크립트 원문, (S) 구현 절)

버전: v1.2026.10.01.1740 → v1.2026.10.01.1955

## 1. 커밋

| 해시 | 내용 | 테스트 | 게이트 |
|---|---|---|---|
| `bc8bbf1` | 워밍업 긴 이력(800봉) 증분 시드 + 200봉 SMA 폴백 | 신규 6건 + 기존 1건 개정 | 269/269 |

## 2. 변경

| 위치 | 내용 |
|---|---|
| `core/indicator_state.py` `seed_long_history(closes, base_len=200)` (신설) | 처음 200봉으로 `seed_from_closes`(각 EMA = SMA 시작) → 나머지 봉을 `update_incremental` 로 순서대로 반영(실시간 증분과 같은 식). 끝에 `prev_*` = None, `bar_count` = 0 으로 맞춰 시드 직후 상태 모양을 기존과 같게 함. 봉이 부족하면 False |
| `core/indicator_state.py` `seed_from_closes(..., quiet=False)` | 긴 이력 시드의 중간 단계에서 `Indicator seeded` 로그를 남기지 않도록 인자 1개 추가(기본값으로 기존 동작 그대로) |
| `engine/live_loop.py` `LONG_SEED_BARS = 800`, `_seed_warmup_indicators()` (신설) | 확정 봉 800 이상 → 긴 이력 시드. 부족 → `seed_from_closes`(현행 200봉 SMA). 버퍼·`local_series` 는 최근 200봉(WO-14 (b) 로컬 시작 연동). 폴백이면서 받은 봉이 201 이하면 받은 그대로(현행과 완전 동일) |
| `engine/live_loop.py` 워밍업 | 첫 시도 `800+1` 봉 요청(WO-16 UTC `to` 조회), 실패하면 이후 시도는 현행 `200+1`(폴백 사유 `fetch_failed`). (W) 형성 중 봉 제거는 그대로 시드 앞에서 |
| 로그 | 성공: `[WARMUP] 시드 방식=long_history bars=800 ema_fast=… ema_slow=… ema_base=… \| 마지막 봉=…` 1줄. 폴백: WARN `[WARMUP] 긴 이력 시드 실패 → 200봉 SMA 폴백 \| 사유=…` + `[WARMUP] 시드 방식=sma200 bars=…` + 텔레그램 WARNING 1회(dedupe 1시간) |
| 무변경 | 매수·매도 판정 조건, 필터, 발주, 실시간 증분, BACKFILL·조정 경로 |

- 첫 200봉 SMA 의 뜻: EMA200 은 첫 200봉 SMA, EMA60 은 첫 200봉 중 마지막 60봉 SMA 에서 시작한다(`seed_from_closes` 그대로). G4 의 B(각 EMA 를 첫 p봉 SMA 로 시작)와 EMA60 시작점이 다르지만 이후 600봉 증분으로 차이는 10⁻⁹ 수준이다(§4 재현에서 소수 4자리까지 일치).
- 워밍업 감사 기록(`record_warmup_log`)은 지금처럼 버퍼 200봉에만 남긴다(800봉 전부를 기록하지 않음).

## 3. 재현 테스트 (`test_r_2026_10_01_wo17s_long_history_seed`)

| 번호 | 내용 | 결과 |
|---|---|---|
| (1) | 800봉 시드의 EMA200 이 1,200봉 장기 기준과 0.3% 이내 (EMA60 은 10⁻⁶ 이내) | 통과 |
| (2) | 801봉 시드 = 800봉 시드 + 마지막 봉 `update_incremental` (같은 시작점, 모든 EMA·MACD·signal 소수 9자리 일치). 시드 직후 `prev` None·`bar_count` 0 | 통과 |
| (3) | (W) 와 함께: 801봉 수신 + 마지막 형성 중 → 제거 800 → `long_history`, 버퍼 df = 그 앞 200봉 | 통과 |
| (4) | 650봉(부분 수신) → `sma200` 폴백, 사유 `insufficient_bars(650<800)`, 지표 = 200봉 SMA. live_loop 에 WARN·시드 방식 로그·폴백 요청(`fetch_failed`)·알림 dedupe 경로 존재 | 통과 |
| (5) | **G4 기동 9(09-30 16:33:06) 직전 확정 800봉 실데이터**(고정 자료 `tests/regressions/fixtures/wo17s_boot9_m5_800.csv`, 09-27 18:15 ~ 09-30 16:20) → `756.8929 / 757.5385` = G4 B 값, 역배열(fast < slow) | 통과 |
| (6) | 폴백은 현행과 완전 동일: 200·201봉 수신이면 지표 상태·버퍼 df 모두 옛 `seed_from_closes` 경로와 같음 | 통과 |

- **옛 코드 대조**: 6건 모두 실패(ImportError — `LONG_SEED_BARS`·헬퍼 없음).
- **기존 테스트 개정 1건**: `test_r_2026_10_01_wo16w_warmup_forming_trim` test_4 는 "트림이 시드보다 앞" 을 파일 전체에서 `indicators.seed_from_closes(closes)` 첫 등장 위치로 비교했다. 새 헬퍼가 `run_live_loop` 보다 위에 정의되어 첫 등장 위치가 바뀌었다(게이트 첫 실행 1건 실패). 검사 취지는 그대로 두고 `run_live_loop` 본문 안에서 트림 → 시드(`_seed_warmup_indicators(` 또는 옛 호출) 순서를 보도록 고쳤다. 옛·새 코드 모두 통과.

## 4. 기동 9 재현 비교표 (`wo17s_boot9_compare.csv`)

| 계열 | EMA60 | EMA200 | gap (fast−slow) |
|---|---|---|---|
| A 현행 200봉 SMA (journal `Indicator seeded`) | 759.75 | 756.49 | **+3.26** (정배열) |
| B G4 800봉 증분 | 756.8929 | 757.5385 | −0.6456 |
| C G4 장기 기준 (10,011봉) | 756.8929 | 757.5204 | −0.6275 |
| **구현 `seed_long_history`** | **756.892933** | **757.538524** | **−0.6456** (역배열) |

- 구현 = B (소수 4자리 일치). C 와 EMA200 차이 0.018원.
- 배포 검증 스크립트(`commands.txt` 첨부 `wo17s_verify_seed.py`) 시험 실행: 기동 9 시각 기준 Upbit 공개 API 로 1,200봉 장기 기준 재계산 → 800봉 재현 차이 0.0000 / 0.0000, 1,200봉 기준 차이 0.0000 / −0.0181.

## 5. 단독 revert 실측 (임시 worktree, 더미 키)

| 되돌린 커밋 | 충돌 | py_compile | 게이트 |
|---|---|---|---|
| `bc8bbf1` | 없음 | OK | 263/263 |

## 6. 배포 절차 초안 (실행은 별도 지시)

1. `git status` → push (코드 `bc8bbf1`, 목표 HEAD = 이 문서 커밋) → 서버 `git pull --ff-only` → `systemctl restart tradebot` → `is-active`. 서버 HEAD·버전 v1.2026.10.01.1955 인용, "버전: v1.2026.10.01.1740 → v1.2026.10.01.1955".
2. 접속 없이 30분 관측

| 항목 | 기대 |
|---|---|
| (S) 시드 | `[REST] 다중 호출 시작 … total_count=801` → `다중 호출 완료 \| total=801`(또는 형성 중 없으면 801 그대로), `[WARMUP] 시드 방식=long_history bars=800 ema_fast=… ema_slow=…` 1줄, 폴백 WARN 0, `시드 방식=sma200` 0 |
| 시드 값 검증 | 로컬에서 `python3 wo17s_verify_seed.py "<기동 [WARMUP] 시각>" <로그 fast> <로그 slow> 1200` → 1,200봉 장기 기준과 차이 **0.1원 이내** 인용, 800봉 재현 차이 0 |
| 버퍼·로컬 | `Buffer seeded \| buffer_len=200`, 첫 조정 `[RECONCILE] 로컬 시작 이전 봉 제외 \| n≈200`(로컬 200봉 유지 증거) |
| WO-16/18 유지 | 조정 `total=400`, VERIFY `없는 timestamp`·실패·불일치 0, 잔존 플래그 SQL 0 (`[HTS-FLAG] 기동 정합 검사 완료 \| cleared=0`) |
| 공통 | 결함 태그(`pos_desync_promoted`·`integrity_gap`·`POLLUTED`·Traceback) 0, `database is locked` 0, Bar# 5봉 |

3. 30분 통과 뒤 운영자 접속 1회: `[AUTO-RESUME] skip` 1줄, 엔진 스레드 1개.
4. 이상 시 `bc8bbf1` 단독 revert (충돌 없음 확인).
5. 투자자 통보: 하지 않음(운영자 판정). `investor-notice-log.md` "통보 대상 아님" 표에 WO-17 (S) 한 줄을 이번 문서 커밋에서 추가했다. 참고: 새 텔레그램 알림 "⚠️ 지표 시드 폴백" 은 워밍업 폴백 때만 나가는 운영 알림이다(정상 기동에서는 나가지 않음).
