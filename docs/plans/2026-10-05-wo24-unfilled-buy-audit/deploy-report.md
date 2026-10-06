버전: v1.2026.10.05.1145 → v1.2026.10.05.1526

# WO-24 배포 완료 보고 — 현재가 매수 미체결 취소 감사 기록 + 미체결 시 시장가 전환 옵션 + 알림 성공 로그

- 작성: 2026-10-06 (KST)
- 배포 대상: `4ad8bf3` (코드 `147efea`, 문서 `5cf88ad`·`3b01141`·`4ad8bf3`)
- 서버 HEAD: `3850794` → `4ad8bf3`
- 재시작: 명령 2026-10-05 16:44:46, `ExecMainStartTimestamp=Mon 2026-10-05 16:44:46 KST`, NRestarts=0
- 관찰 로그 출처: `journalctl -u tradebot`
- 서버에서는 pull 과 restart 만 했고 나머지는 읽기만 했다. 투자자 포지션·주문·설정은 바꾸지 않았다.
- **판정 (Fable): 0~3 전 항목 통과. 147efea 를 되돌리지 않는다.**
- **기준 정정 사유: 기동마다 strategy_init 1행 기록은 기존 동작.** 2(b)·3 의 settings_history 기준은 배포 전 운영자 결정으로 정정했다 (아래 2(b)·3).

## 3점 일치

| | HEAD | dashboard.py 버전 | 기동 |
|---|---|---|---|
| 로컬 (배포 시점 origin/main) | `4ad8bf3` | v1.2026.10.05.1526 | — |
| 서버 | `4ad8bf3` | v1.2026.10.05.1526 | 2026-10-05 16:44:46 KST |
| 화면 (운영자 육안, 10-06 13:04) | — | v1.2026.10.05.1526 | — |

## 0. 배포 전 확인 (`deploy/pre-check.txt`)

| 항목 | 결과 | 판정 |
|---|---|---|
| KRW-JTO 포지션: account_positions | virtual_coin 0.0, locked 0.0 (16:34 와 16:44 두 번 확인) | 통과 |
| KRW-JTO 포지션: Upbit /v1/accounts | http 200, JTO 행 없음 = 0 (두 번 확인) | 통과 |
| origin/main / 서버 HEAD | `4ad8bf3` / `3850794` | 통과 |
| config 상수 (`config.py:71-72`) | `UNFILLED_TO_MARKET_DEFAULT = False`, `UNFILLED_TO_MARKET_MAX_GAP_PCT_DEFAULT = 0.3` (로컬 파일과 origin/main 모두 같음) | 통과 |
| settings_history | 192행, 마지막 id 192 (10-05 15:18:51, strategy_init). 출처 분포: set_buy_sell_conditions 102, strategy_init 78, set_config 11, initial_seed 1 | 기록 |
| 운영 설정 파일 `mcmax33_EMA_buy_sell_conditions.json` | sha256 `693d982be7e095937a993bab7f821954bf4f12f36d03923211739e69d45c46b6`, mtime 2026-10-04 19:15:41, 510 bytes. WO-24 키 2개 없음 (grep 0) | 기록 |
| 15:18:44 이후 매매 | orders 0건. audit_trades 는 다른 종목 앱 매수 감지 4건 (BIRB 2, SUI 1, UP2 1) | 기록 |

## 1. 서버 배포 (`deploy/deploy.txt`)

| 항목 | 결과 |
|---|---|
| `git pull` 뒤 HEAD | `4ad8bf3`, `147efea 포함` (merge-base 확인) |
| 재시작 | 16:44:46 명령, 16:44:46 active (running) |
| 서버 버전 | `v1.2026.10.05.1526` |

## 2. 30분 무접속 관찰 (16:44:46 ~ 17:14:47, `deploy/observation-30min.txt`)

| 항목 | 기대 | 실측 | 판정 |
|---|---|---|---|
| (a) 기동 줄 3종 | BOOT-RESUME success, 시드 1줄, 감사 행 보존 1줄 | 16:44:52 `[BOOT-RESUME] success` (5.6s), `timeframe=minute1`. 16:44:53 `시드 방식=long_history bars=800 ema_fast=775.1452 ema_slow=771.5786` 1줄. `감사 행 보존 \| kept=200 inserted=0 updated_placeholder=0` 1줄 | 통과 |
| (b) 새 설정 키 값 | False / 0.3 으로 읽힘. settings_history 는 strategy_init 1행만 늘어 193. 다른 출처 0. 설정 파일 해시·mtime 불변 | **읽기 전용 실행으로 증명** (`deploy/wo24d_cond_eval.py` → `deploy/cond-eval-2b.txt`): 아래 2(b) 상세 | 통과 |
| (c) `[NOTIFY] sent` | 알림이 있으면 1줄 이상 | 코드 존재: 서버 `services/notifier.py:170` `[NOTIFY] sent \| kind={level} dedupe={dedupe_key}`. 실측 1줄: `16:44:53 [NOTIFY] sent \| kind=INFO dedupe=boot_resume:mcmax33:success`. 토큰 형식(`bot[0-9]{6,}:`) 0, `chat_id=` 0 | 통과 |
| (d) 상설 1:1 대조 | 표 | BUY 평가 통과 0, SELL 평가 발동 0, 창 안 orders 0 (아래 표). 미체결 취소 없음: `LIMIT BUY timeout` 0, BUY_CANCELED 기록 0, `[UNFILLED-CONVERT]` 0. 코드 존재: 서버 `engine/order_reconciler.py:415`, `core/strategy_engine.py:192·208·224` | 통과 (해당 사건 없음) |
| (e) 결함 태그 / Bar# / 조정 / BACKFILL / 사후 확인 7 | 0 / 5 이상 / 400 / 0 / 0.1원 이내 | ` ERROR `, Traceback, `[POS-DESYNC] class=`, `Upbit에 없는 timestamp`, `불일치 발견`, `과거 봉 검증 실패`, `database is locked`, `[LOCKED-QTY]`, CRITICAL, VERIFY WARNING 모두 0. Bar#201 (16:45:11) → Bar#225 (17:14:11), 25봉. 1분봉 30개 중 거래 없는 봉 5. 조정 400봉 수신 30회. BACKFILL 0. 시드 검증: 800봉 재현 +0.0000 / +0.0000, 1200봉 기준 +0.0000 / **+0.0064** (`deploy/verify-seed.txt`) | 통과 |
| (f) 사후 확인 11 준비 | JTO 포지션이 생기면 `[POSITION-SYNC] entry_price=… (출처: …)` | 코드 존재: 서버 `core/strategy_engine.py:699`. 실측 0건. **해당 사건 없음** (창 안 JTO 포지션 없음) | — |

### 2(b) 상세 — 읽기 전용 실행으로 증명

1. **계산** (`deploy/cond-eval-2b.txt`)
   - 서버에서 운영 설정 파일을 `open('rb')` 로 읽기만 했다.
   - config.py 는 import 하지 않고 ast 로 상수만 읽었다.
   - 엔진과 같은 식으로 계산했다: `bool(buy.get("fixed_price_unfilled_to_market", UNFILLED_TO_MARKET_DEFAULT))`, `float(buy.get("fixed_price_convert_max_gap_pct", UNFILLED_TO_MARKET_MAX_GAP_PCT_DEFAULT))`.
   - 결과는 **미체결 시 시장가 전환 = False, 전환 허용 가격 차이 % = 0.3**, `기대값 일치: True` 이다.
   - 실행 전후 파일의 sha256 과 mtime 은 같다.
2. **키 부재** (`deploy/journal-boot.txt`)
   - 기동 로그 `16:44:52 [전략 초기화] Loaded buy conditions: {'ema_gc': True, 'above_base_ema': False, 'bullish_candle': False, 'surge_filter_enabled': True, 'fixed_price_buy_enabled': True, 'surge_threshold_pct': 0.015, 'fixed_price_buy_wait_bars': 5}` 에 두 키가 없다.
   - 따라서 config 기본값 경로를 탄다.
3. **코드 위치**
   - 기본값: `config.py:71` `UNFILLED_TO_MARKET_DEFAULT = False`, `config.py:72` `UNFILLED_TO_MARKET_MAX_GAP_PCT_DEFAULT = 0.3`
   - 읽는 곳: `core/strategy_engine.py:175-176` (`convert_unfilled_limit_buy`)
   - `buy_conditions` 적재: `engine/live_loop.py:803` (기동), `:536` (설정 파일 변경 시 다시 읽기), `:599` `_load_trade_conditions`
4. **settings_history** (`deploy/settings-history-2b.txt`, 16:45:45 조회)
   - 193행, 늘어난 행은 id 193 `strategy_init` 1행뿐이다 (16:44:52, app_version v1.2026.10.05.1526). 다른 출처는 0행이다.
   - 설정 파일 sha256 은 `693d982b…` 그대로이고 mtime 도 10-04 19:15:41 그대로다.
5. 백로그에 "기동 시 설정 키·적용값 로그 1줄" 을 등록했다 (다음 설정 관련 WO 에 포함).

### 상설 항목 — BUY/SELL 평가 통과 행 대 실제 체결 1:1 대조 (`deploy/match-1to1.txt`)

| 구간 | 종류 | 통과/발동 | 체결 | 취소 | 미요청 | 창 안 orders |
|---|---|---|---|---|---|---|
| 16:44:46 ~ 17:14:47 (관찰 창) | BUY 평가 통과 | 0 | 0 | 0 | 0 | 0건 |
| | SELL 평가 발동 | 0 | 0 | 0 | 0 | |
| 17:14:47 ~ 10-06 13:05:38 (창 뒤 ~ 접속, 참고) | BUY 평가 통과 | **1** (id 77602, 05:36 봉, Golden) | 0 | 0 | **1** | 0건 |
| | SELL 평가 발동 | 0 | 0 | 0 | 0 | |

미요청 1건의 원인은 매수 가능 KRW 1원이다 (아래 "창 뒤 사건" 2).

## 3. 대시보드 1회 접속 (운영자 접속, 2026-10-06 13:04)

| 항목 | 기대 | 실측 | 판정 |
|---|---|---|---|
| `[AUTO-RESUME] skip` | 1줄 | 13:04:55 1줄 (boot_resume_at 10-05 16:44:52). 그 전 07:43:24·07:48:33 에도 각 1줄 (투자자 추정 접속) | 통과 |
| 엔진 스레드 | 1개 | 16:44:46 이후 `run_live_loop start` 1회 (기동 때). NRestarts=0, 기동 시각 16:44:46 그대로 | 통과 |
| 화면 버전 | v1.2026.10.05.1526 | 운영자 육안 확인 "v1.2026.10.05.1526" | 통과 |
| 설정 페이지 표시 | (지시) 체크박스 꺼짐, 0.3 비활성, 1분봉 대기 시간 안내 | **체크박스 켜짐, 0.3 활성 (투자자 저장 뒤 상태).** 기대값 불일치가 아니라 07:49 투자자 저장으로 설정이 바뀐 결과다 (아래 근거) | 통과 (Fable 판정) |
| settings_history·설정 파일 (정정 기준: 운영자 접속 전후 불변) | 운영자 접속 뒤 그대로 | 13:05:49 조회: **195행, 설정 파일 sha256 `286db8b9…`, mtime 2026-10-06 07:52:22**. 운영자 접속(13:04:55) 전의 마지막 저장(07:52:22)과 같다. 페이지 열기만으로는 저장되지 않았다 (`deploy/access-settings.txt`) | 통과 (Fable 판정) |
| 감사 로그 페이지 "미체결 취소" 필터 | 보임 | 운영자 접속 회신은 화면 버전만 있었다. 필터 표시를 따로 확인한 기록은 없다 | 기록 |

### 3단계 판정과 근거 (Fable)

- **07:49·07:52 설정 저장 주체는 "투자자(추정)"** 으로 기록한다. 설계상 허용된 선택이며 되돌리거나 바꾸지 않는다.
  - 근거: 07:43:24 `[AUTO-RESUME] skip` 다음 07:43:50~07:47:37 감사 로그 페이지 접속 4회, 07:48:33 `[AUTO-RESUME] skip`. 이 시간대 접속 주체는 로그로 구분되지 않는다.
- **3단계는 통과다.** 기준의 목적(페이지 열기만으로 저장되지 않음)은 충족됐다. 원인은 저장 버튼 2회이고, 13:04 운영자 접속 뒤에도 195 와 07:52 가 그대로다. 147efea 를 되돌리지 않는다.

설정 저장 2건 (`deploy/settings-saves-0749-0752.txt`):

| id | 시각 | 출처 | 바뀐 것 (직전 id 193 대비) | 엔진 반영 |
|---|---|---|---|---|
| 194 | 2026-10-06 07:49:19 | set_buy_sell_conditions | buy `fixed_price_unfilled_to_market: true`, `fixed_price_convert_max_gap_pct: 0.3` 추가 (**미체결 시 시장가 전환 켬**) | 07:50:00 `[PARAMS-RELOAD] 조건 파일 변경 반영 완료` |
| 195 | 2026-10-06 07:52:22 | set_buy_sell_conditions | sell `ema_dc: true → false` (데드크로스 매도 끔), `stale_position_check: false → true`, `stale_hours 1.0`, `stale_threshold_pct 0.01` (정체 포지션 매도 켬) | 07:53:00 `[PARAMS-RELOAD]` |

## 창 뒤 ~ 접속 구간의 사건 (17:14:47 ~ 10-06 13:05:38, `deploy/after-window-to-access.txt`)

| # | 사건 | 근거 | 판정 |
|---|---|---|---|
| 1 | 설정 저장 2건 (위 표) | settings_history 194·195, journal | 투자자(추정) 선택, 손대지 않음 |
| 2 | **05:37 BUY 평가 통과 뒤 매수 미실행** | `05:37:11 🔔 EMA Buy Signal \| fast=770.28 slow=770.16` → `Bar#709 … action=BUY pos=False` → `🎯 [FIXED-PRICE] 고정가 매수 모드 진입 \| close=779.0 … wait_bars=5` → `05:37:12 WARNING core.trader \| [BUY-LIMIT] 활성 KRW 부족: 가용=1 계산=0 (최소 5,000 미만)` → `05:37:13 [NOTIFY] sent \| kind=WARNING dedupe=fixed_buy_balance:KRW-JTO` → `❌ BUY 실패`. orders 0건, audit_trades JTO 0행 (`deploy/event-0537-and-0349.txt`) | **결함 아님** (매수 가능 KRW 1원. 같은 기간 10-05 20:48~22:18 앱 매수 감지 BLEND·TOKAMAK 이 있었다). 감사 기록에 남지 않는 것은 **WO-25** 에서 고친다 |
| 3 | 03:49:14 `ERROR [OR] periodic sync failed for user=mcmax33: database is locked` | 바로 다음 주기 **03:50:13 `[OR] periodic sync: user=mcmax33 updated`** 성공. 03:51·03:52·03:53 도 성공. `periodic sync failed` 는 10-01 이후 전체에서 이 1건, `database is locked` 는 16:44:46 이후 1건 | 일회성. 실패가 이어지지 않음 |
| 4 | 다른 종목 앱 매수 감지 9건 (BLEND, TOKAMAK, BIRB) | `[HTS-DETECT]` | 기존 동작. JTO 영향 없음 |
| 5 | `[NOTIFY] sent` 2줄 (05:37 `ema_gc:KRW-JTO`, `fixed_buy_balance:KRW-JTO`) | journal | 알림 성공 로그 동작 확인 (C 항목) |

## 4. 실패 시 조치

해당 없음. 147efea 를 되돌리지 않았다.

## 5. 문서

- 운영 가이드 `docs/operations/wo8-force-buy-verification-guide.md`
  - 사후 확인 11 (WO-22 진입가 출처 `upbit_avg` 우선, 앱 전량 매도 시 HTS_SELL 행)
  - 사후 확인 12 (첫 미체결 취소 시 BUY_CANCELED 행과 감사 로그 표시)
  - 사후 확인 13 (미체결 시 시장가 전환이 켜진 상태의 첫 timeout: `[UNFILLED-CONVERT]`, 시장가 주문·`apply_entry` 등록, BUY_CANCELED note "→ 시장가 전환")
  - 정기 점검 목록을 1~13 으로 바꿨다.
  - 배포 관찰 기준을 "settings_history·설정 파일은 운영자 접속 전후 불변 (투자자 저장은 별도 기록)" 으로 정정했다.
- `docs/operations/investor-notice-log.md` #3: "WO-22·WO-24 통보 예정 (운영자 발송)". 비고에 투자자의 07:49 옵션 켬과 07:52 매도 조건 변경을 적었다. **문안은 "Fable 보고 인용문 그대로" 지시였으나 이 세션에 원문이 전달되지 않아 미기재로 표시했다.**
- `docs/plans/backlog.md`: "기동 시 설정 키·적용값 로그" 1행

## 6. 규칙 준수와 정정

| # | 내용 | 영향 |
|---|---|---|
| 1 | **와일드카드 패턴 1회 위반.** 배포 전 조사 중 `grep -n 'strategy_init' -r --include=*.py .` 를 썼다. zsh 가 `no matches found` 로 실행 전에 막아 실행되지 않았다. | 없음 |
| 2 | 중간 보고에서 config 상수 위치를 "72·73행" 이라고 적었다. 실제는 **71·72행**이다. | 이 문서에서 정정 |
| 3 | 관찰 종료 대기용 백그라운드 ssh (`sleep 1790`) 는 서버 쪽에서 연결이 끊겨 종료 시각을 출력하지 못했다 (`Connection … closed by remote host`). 관찰 판정은 창을 `16:44:46 ~ 17:14:47` 로 고정해 10-06 13:05 에 실행했으므로 영향이 없다. | 없음 |
| 4 | heredoc 은 쓰지 않았다. 서버 쓰기는 pull 과 restart 뿐이다. 키 값은 출력하지 않았다. | — |

## 7. 묶음

- `report.md` (이 문서), `commands.txt`, `git-log.txt`
- `deploy/pre-check.txt` (0단계: 포지션·이력·settings_history·설정 파일 해시, 두 번 확인), `deploy/deploy.txt`
- `deploy/observation-30min.txt`, `deploy/journal-boot.txt`, `deploy/verify-seed.txt`
- `deploy/cond-eval-2b.txt`, `deploy/settings-history-2b.txt` (2(b) 증명과 전후 행 수)
- `deploy/match-1to1.txt` (상설 1:1 대조: 관찰 창과 창 뒤 구간)
- `deploy/after-window-to-access.txt`, `deploy/access-settings.txt` (3단계: settings_history 195·설정 파일 해시, 접속 표식)
- `deploy/settings-saves-0749-0752.txt` (설정 저장 2건 journal·settings_history 발췌)
- `deploy/event-0537-and-0349.txt` (05:37 매수 미실행 journal 발췌, 03:47~03:53 periodic sync)
- 스크립트: `deploy/wo24d_pre.py`, `deploy/wo24d_obs.sh`, `deploy/wo24d_cond_eval.py`, `deploy/wo22d_match.py`
