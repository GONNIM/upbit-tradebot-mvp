# WO-17 (S) 완결 뒤 세션 시작 정기 점검 + WO-17 (S2) 후속 작업 보고 (2026-10-02)

- 점검 시각: 2026-10-02 08:14:09 KST (서버 시계)
- 로그 출처: 로거 줄은 `journalctl -u tradebot`, `mcmax33_engine_debug.log` 는 보조(봉 요약 `cross=` 줄)
- 서버 작업: 읽기만. 포지션·주문·서비스 상태 변경 없음. 투자자 안내 없음
- 결론: **A 1~5 모두 "이전 기동과 같음" 또는 정상 → B 진행.** 다만 A 에서 기존 동작이지만 짚어 둘 사항 2건을 §A6 에 적었다(결함 판정은 운영자 몫)
- 첨부: `journal_excerpt.txt`, `a5_compare.csv`, `test_results.txt`, `project_rules_diff.txt`, `commands.txt`, `git_log.txt`

## A. 세션 시작 정기 점검 (읽기 전용)

### A1. 서버 상태

| 항목 | 값 | 판정 |
|---|---|---|
| `systemctl status tradebot` | active (running) since 2026-10-01 20:10:55 KST (12시간) | 정상 |
| `git rev-parse --short HEAD` | `962bb46` | 기대값 일치 |
| `pages/dashboard.py` 버전 | v1.2026.10.01.1955 | 유지 |

### A2. 기동 이력 (20:10:55 이후)

| 시각 | 줄 |
|---|---|
| 20:10:55 | systemd `Started Upbit Tradebot MVP v1` (재시작 1회, 이후 재기동 없음) |
| 20:10:59 / 20:11:01 | `[BOOT-RESUME] start` / `success user=mcmax33 mode=LIVE elapsed=6.4s` |
| 20:11:02 | `[WARMUP] 시드 방식=long_history bars=800 ema_fast=734.9141 ema_slow=736.1272 ema_base=736.1272 \| 마지막 봉=20:05` |

- 기동 1회, `long_history bars=800` 1줄.
- 검색 문자열 코드 존재 확인(서버 `engine/live_loop.py`): `:1119` `시드 방식=long_history`, `:1126` `긴 이력 시드 실패`, `:1127` `시드 방식=sma200` → journal 건수 `긴 이력 시드 실패` **0**, `sma200` **0**.

### A3. 야간 운영 (2026-10-01 20:40:55 ~ 2026-10-02 08:14:09)

| 항목 | 수치 |
|---|---|
| Bar# 진행 | Bar#206(20:45, 봉 20:40) → Bar#332(08:10, 봉 08:05), 127줄. 조정 138회 전부 `total=400`, 무거래 봉 건너뜀(`CONFIRMED-NO-TRADE`) 11회, BACKFILL 0 |
| cross 상태 변화 (engine_debug.log `cross=`) | 20:40 봉 Dead 시작 → **Dead→Golden 03:35 봉(로그 03:40:12) ema_fast=732.32 ema_slow=732.11** → Golden→Dead 07:45 봉(07:50:10) 732.48 / 732.49 → **Dead→Golden 07:55 봉(08:00:11) 732.53 / 732.50** |
| 매수 신호 (`EMA Buy Signal`) | 2 (03:40:11, 08:00:10) |
| 주문 (`[UPBIT-ORDER]` 줄) | 6줄 = 주문 3건(→·← 쌍): 03:40 지정가 매수 747 × 343.4534 체결, 03:55 시장가 매도(손절 −1.20%, 평균 739) 체결, 08:00 지정가 매수 734 × 318.0181 체결 |
| `action=BUY` / `action=SELL` | 2 / 1 |
| 현재 KRW-JTO 보유 | 318.01810267 (08:00 봉 매수분, 그대로 둠) |
| SELL_REJECTED · BUY_REJECTED | **0 · 0** (감사 행 BUY 5, SELL 1 — 그중 외부 매수 감지 3) |
| ERROR | 0 |
| Traceback | **3줄 = 1건(연쇄 예외 1개)** — 08:06:45 Streamlit 미디어 파일 요청 `.env` 거부(§A6-2). 엔진 무관 |
| `[POS-DESYNC] class=` | 0 |
| VERIFY 경고·불일치·실패 | 0 · 0 · 0 |
| `database is locked` / CRITICAL / POLLUTED / ON CONFLICT | 0 / 0 / 0 / 0 |

### A4. 사후 확인 1~6 (`docs/operations/wo8-force-buy-verification-guide.md`)

| 번호 | 항목 | 결과 |
|---|---|---|
| 1 | 강제 매수 원자 경로 (WO-8b) | **해당 사건 없음** — 기준(09-30 16:33:05) 이후 `[FIXED-PRICE][FORCE]` 0, `force_buy` 감사 행 0. (봇 현재가 매수의 `[LIMIT-FILL] apply_entry` 는 3회 정상: 10-01 14:16:52, 10-02 03:40:15, 08:00:14) |
| 2 | HTS 승격 가드 (WO-8) | **해당 사건 없음(새 사건)** — 엔진 종목 KRW-JTO 의 외부 매수는 09-30 16:47:09 뒤 없음. 기존 관측(16:50:05 차단 1회 → 16:50:07 streak 리셋)만 |
| 3 | WO-9 (c)(b)(e) | ① **확인** — HTS 매수 감지가 가용+묶임 합계 기준으로 동작(예: KRW-SNT 10-01 22:19:27 `total 18589.07 → 19227.75, 가용=638.68 묶임=18589.07`). ② 기존 확인(09-30 16:49:10 `⛔ [LOCKED-QTY]`, 23:24:26 해제) — 새 사건 없음. ③ **해당 사건 없음** — `SELL_REJECTED` 0 |
| 4 | WO-14 (a) 미확정 봉 제외 | 기준(10-01 11:42:01) 이후 6건, 모두 WO-16 배포(13:24:41) 이전. 이후 0 — 조정 첫 배치가 확정 대상 봉까지만 받아 형성 중 봉이 오지 않음(발생 조건 소멸) |
| 5 | WO-14 E1 trailing 복원 | **해당 사건 없음** — 기준 이후 BACKFILL 1회(10-01 11:50, 미보유) 뿐, `trailing 상태 복원` 0 |
| 6 | WO-18 hts_buy 해제 사이클 | **외부 매도 경로 2회 확인** — KRW-SNT(HTS_BUY_ADD 22:19·22:20 → 10-02 00:18:50 `[HTS-FLAG] cleared \| reason=sync_all_positions_cleared`), KRW-QKC(HTS_BUY 06:31:44 → 07:58:50 같은 사유). 봇 매수(JTO 03:40) SELL 평가 `hts_buy=False` 5/5. 잔존 SQL 0, 보유 중 플래그 FOLD·PYUSD 유지. 봇 매도 해제 경로(`bot_sell`)는 **해당 사건 없음**(JTO 외부 매수 없음) |

### A5. Fable 추가 확인 2건

**(a) 기동 직후 `[AUDIT-UPDATE] BUY 실시간 재판정` (a5_compare.csv)**

| 기동 | 코드 | 건수 |
|---|---|---|
| 10-01 09:55:59 | 0c8e729 계열 | 172 |
| 10-01 11:42:01 | 52286af | 199 |
| 10-01 13:24:41 | dda1ec6 | 200 |
| 10-01 18:10:24 | 83f48ba | 185 |
| **10-01 20:10:55** | **bc8bbf1** | **200** |

→ **기존 동작.** 동작 설명: 워밍업이 버퍼를 채우며 봉마다 `StrategyEngine.record_warmup_log`(`core/strategy_engine.py:1422~`)를 부르고, 이것이 `services/db.insert_buy_eval`(`services/db.py:1002~`)의 실시간 경로로 들어간다. 같은 `(ticker, bar_time)` 의 `audit_buy_eval` 행이 이미 있으면 "실시간 재판정" 분기(`:1126~1145`)가 그 행의 **`timestamp, interval_sec, bar, price, macd, signal, have_position, overall_ok, failed_keys, checks, notes`** 를 워밍업 값으로 덮어쓴다(`overall_ok=0`, `checks={"status":"WARMUP","reason":"WARMUP_IN_PROGRESS",…}`, `notes="⏳ WARMUP 진행 중 (완료 n/200)"`, `macd`·`signal`=NULL). `backfill_*` 열은 건드리지 않는다. 건수는 워밍업 200봉 중 이미 감사 행이 있던 봉 수다. 감사 로그 페이지(`pages/audit_viewer.py:279~280` "🟢 BUY 평가 (audit_buy_eval)")가 이 표를 그대로 보여 주므로, **투자자에게는 기동 직전 약 200봉(약 16.7시간)의 BUY 평가 행이 원래 판정 대신 "⏳ WARMUP 진행 중"·실패(overall_ok=0) 로 보인다.** 실측 예: 10-01 14:10 봉(그 봉의 골든크로스로 14:15 봇 매수가 체결된 봉)의 행 id 74864 가 20:11:03 에 `WARMUP (완료 129/200)` 으로 덮였다. 매매 기록(`audit_trades`)은 그대로다.

**(b) `[REST-RECONCILE] 1개 봉 변경 감지 (지표는 증분만)`**

| 창 (2시간) | 코드 | 건수 / 봉 확정 / 무거래 | 간격 | 분류 | 변경 봉 = 확정 대상 봉 |
|---|---|---|---|---|---|
| 10-01 18:10:24 ~ 20:10:24 (이전 기동) | 83f48ba | 24 / 24 / 0 | 5분 ×23 | `changed=1 inserted=1` ×24 | 24/24 |
| 10-01 20:10:55 ~ 22:10:55 (이번 기동) | bc8bbf1 | 23 / 24 / 1 | 5분 ×21, 10분 ×1(무거래 봉) | `changed=1 inserted=1` ×23 | 23/23 |

→ **기존 동작.** 예시 20:15:11: `[RECONCILE] 변경 감지! | changed=1 inserted=1 | 범위: 20:10 ~ 20:10` — 변경 봉은 방금 확정된 20:10 봉. **로컬 값: 없음**(inserted — WO-16 뒤 조정·워밍업이 형성 중 봉을 미리 받지 않으므로 새로 확정된 봉은 로컬에 처음 들어온다), **REST 값**: `[REST] 첫 배치 마지막 봉 (end_ts 기준) | ts=20:10 | close=734 | high=734 | low=731 | volume=2493.12`. 값이 바뀐 봉이 아니라 새로 추가된 봉이 "변경 1개" 로 세어지는 것이다.

### A6. 기존 동작이지만 짚어 둘 사항 (결함 판정은 운영자 몫, B 진행에 영향 없음)

1. **기동마다 직전 약 200봉의 BUY 평가 감사 행이 WARMUP 값으로 덮인다**(A5 (a)). 하루 기동이 잦으면(10-01 4회) 그날 BUY 평가 기록 대부분이 실제 판정 대신 "WARMUP" 으로 남는다. 투자자 클레임 조사 시 BUY 평가 근거가 사라질 수 있다. 처방 여부·방식(예: 이미 실시간 행이 있으면 건너뜀)은 별도 판단 필요.
2. **외부 스캐너의 비밀 파일 요청**: Traceback 1건은 08:06:45 Streamlit 미디어 경로로 들어온 `.env` 요청이 "Missing file" 로 거부된 것이다. 08-31 이후 같은 유형 64건(`.env`·`.env.bak`·`.git/config`·`.ssh/authorized_keys` 등, 09-16·17·20·24·28, 10-02) 모두 거부. 엔진과 무관하나 서버가 공개 스캔 대상임을 기록한다.

## B. WO-17 (S2) 후속 작업 (로컬, 엔진 실행 코드 무변경)

| 번호 | 작업 | 결과 |
|---|---|---|
| B1 | `scripts/wo17s_verify_seed.py` 저장소 추가 | `commands.txt` 첨부 원문(작업본과 동일 — 끝 빈 줄 1개 차이뿐) + 머리 주석 3줄(인자, 실행 예, 판정 기준 0.1원). `py_compile` OK |
| B2 | 시험 강화 | `test_r_2026_10_01_wo17s_long_history_seed` (1)에 실데이터 단언 추가 — 기동 9 고정 자료 800봉 시드 vs `wo17s_boot9_compare.csv` "C G4 장기 기준 (10,011봉)" 행(756.8929 / 757.5204), EMA60·EMA200 차이 모두 **0.1원 이내**. 기존 0.3% 단언은 "[합성 데이터용]" 주석으로 구분. 대조 단언: 같은 자료로 옛 200봉 SMA 는 0.1원 초과. **구 방식 실패 실측**: 시드 함수를 옛 동작으로 바꿔 실행 → `AssertionError: 3.0904 not less than 0.1 : (759.98, 756.8929)`. 구 코드 파일(a7d40b2)로는 ImportError |
| B3 | 사후 확인 7 추가 | `wo8-force-buy-verification-guide.md` "사후 확증 7번" — 기동마다 `long_history bars=800` 1줄, 폴백 0, `scripts/wo17s_verify_seed.py` 차이 0.1원 이내, 부호 같음 + 조회 명령. 사후 확증 6번 아래에 10-02 점검 기록 한 줄 추가 |
| B4 | `project-rules.md` v2.12 → v2.13 | "관찰 판정의 로그 출처는 `journalctl -u tradebot`, `mcmax33_engine_debug.log` 는 보조, 관찰 지시에 두 출처 구분" 추가 (`project_rules_diff.txt`) |
| B5 | 관문 (.env 격리) | **269/269 통과**. 추가 단언은 기존 시험 (1) 안에 들어가 시험 수는 그대로(269), (1) 의 단언 3개(실데이터 2 + 대조 1) 증가 |
| B6 | 커밋 1건 | 엔진 실행 코드 무변경 → 대시보드 버전 그대로(v1.2026.10.01.1955), 서버 pull·재시작 없음. 커밋 해시는 보고 본문에 적음 |
