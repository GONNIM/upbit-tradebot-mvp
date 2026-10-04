# 1분봉 전환 점검 (읽기 전용) + 검증 스크립트 정비

- 작성: 2026-10-04 (KST)
- 서버: 읽기만 했다 (HEAD `e97dec6`, 기동 2026-10-04 10:22:33 그대로). 포지션·주문·설정 무변경. 투자자 안내 없음.
- 로그 출처: `journalctl -u tradebot`.
- 저장소: 엔진 코드 무변경. 바꾼 것은 `scripts/wo17s_verify_seed.py` 와 운영 가이드뿐이다. 버전 변경 없음.

## 결론

- **1분봉 전환에 결함은 없다.** 운영자가 설정 페이지에서 엔진을 멈춘 뒤 간격을 바꾸고 다시 켰다. 엔진은 1분봉 801개로 처음부터 다시 워밍업했다. 5분봉 지표 상태에 1분봉이 이어 들어간 일은 없다. 그래서 B 를 진행했다.
- 관찰 사항 3가지 (결함 아님):
  1. 1분봉에서는 거래 없는 봉이 약 30~38% 다 (5분봉 4.5%). 그 봉은 지표에 반영하지 않고 건너뛴다(기존 설계).
  2. 거래 없는 봉의 일부(1분봉 799봉 중 16봉)에서 봉 확정이 두 번 기록된다. 두 번 모두 "거래 없음"으로 끝나 지표 이중 갱신은 0건이다.
  3. 서버의 `.env.bak` 이 `644`(모두 읽기 가능)이고 실제 키 값이 들어 있다. `/root` 가 `700` 이고 일반 사용자 계정이 없어 지금 다른 계정이 읽을 경로는 없다. Streamlit 정적 제공은 꺼져 있고 외부 스캐너 요청 7건은 모두 거부됐다. 권한 정리(예: `chmod 600` 또는 삭제)는 운영자 결정 사항으로 남긴다.

## A1. 전환 기록 (`evidence/a1-settings-history.txt`)

| id | 저장 시각 | 출처 | 바뀐 항목 (직전 행 대비) |
|---|---|---|---|
| 185 | 10-02 10:03:25 | strategy_init (WO-19 기동) | — |
| 186 | 10-03 21:02:29 | **set_buy_sell_conditions** (매매 조건 페이지 저장) | `buy.surge_filter_enabled` False → **True**, `buy.surge_threshold_pct` (없음) → **0.015**, `params.order_ratio` 0.1 → **0.5** |
| 187 | 10-03 21:03:34 | **set_config** (설정 페이지 저장) | `params.interval` minute5 → **minute1**, `params.cash` 2,124,203 → 2,982,143 |
| 188 | 10-03 21:03:47 | strategy_init (엔진 재시작) | 없음 (186·187 반영본 기록) |
| 189 | 10-04 10:22:41 | strategy_init (WO-20 기동) | 없음 |

**interval 과 함께 바뀐 항목**: 1분 앞서 급등 차단 필터 켬(1.5%)과 주문 비율 0.1 → 0.5, 같은 저장에서 cash. 변경 주체는 로그로 확인했다: `[settings_history] recorded id=186 … source_page=set_buy_sell_conditions`(21:02:29), `[LiveParams] saved params to mcmax33_latest_params_EMA.json` + `recorded id=187 … source_page=set_config`(21:03:34). 둘 다 설정 페이지 저장이다.

## A2. 전환 시점 엔진 동작 (`evidence/a2-journal-2102-2110.txt`, 21:02:00 ~ 21:10:00)

| 시각 | 로그 | 의미 |
|---|---|---|
| 21:02:29 | `🔄 [HOT-RELOAD] strategy 갱신 완료 \| ema_surge_filter_enabled: False→True, ema_surge_threshold_pct: 0.01→0.015` | 조건 저장 → 핫리로드 |
| 21:02:34 | `🧹 run_live_loop 종료 (LIVE) → stop_event set`, 21:02:35 `[OR] stopped` | 엔진 정지 (운영자) |
| 21:03:23 | `⚠️ 활성 엔진 없음 - 매매 중단 상태` (health_monitor) | 정지 중 |
| 21:03:34 | `[LiveParams] saved params …`, settings_history id=187 | 간격 저장 |
| 21:03:46 | `[OR] started`, `engine_runner 시작 → user_id=mcmax33, mode=LIVE` | 엔진 시작 (운영자) |
| 21:03:47 | `[EMA Strategy] interval_min=1 전달 완료`, `[CLOCK] Initialized \| timeframe=minute1 interval=60sec` | 1분봉으로 기동 |
| 21:03:47 | `[REST] 다중 호출 시작 \| market=KRW-JTO timeframe=minute1 total_count=801` | **재워밍업 (1분봉)** |
| 21:03:48 | `[WARMUP] 형성 중 봉 제거 \| … 최종 봉 수=800 \| 최종 마지막 봉=2026-10-03 21:01:00` | |
| 21:03:48 | `[WARMUP] 시드 방식=long_history bars=800 ema_fast=726.8085 ema_slow=721.4056` | 1분봉 800봉 증분 시드 |
| 21:03:52 | `[WARMUP] 감사 행 보존 \| kept=9 inserted=191 updated_placeholder=0` | 5분봉 실판정 행과 시각이 겹친 9행 보존 |
| 21:04:10 | `📊 Bar#201 \| ts=… 12:03:00+00:00 \| … action=HOLD` | 1분봉 정상 진행 |

재워밍업이 있었고 1분봉 기준으로 시드했다. 결함이 아니므로 21:03:47 ~ 10-04 10:22:33 의 신호·주문 전수 나열은 하지 않았다. 참고로 이 구간 KRW-JTO 주문은 없다 (WO-20 배포 0단계: 10-02 14:15 이후 주문은 10-03 20:05 매도 1건뿐, 전환 전).

## A3. 거래 없음 비율 (`evidence/a3-ratio.txt`, `evidence/a3-duplicate-close.txt`)

검색어 코드 존재: `engine/live_loop.py:1254` `[CLOCK-CLOSE] 봉 확정 감지`, `:1293` `[CONFIRMED-NO-TRADE]`, `core/strategy_engine.py:1372·1378` `📊 Bar#`.

| 구간 | 고유 봉 | Bar# (평가) | 거래 없음 건너뜀 (고유) | 봉 확정 중복 기록 | Bar# 이중 |
|---|---|---|---|---|---|
| 1분봉, WO-20 기동 이후 (10-04 10:22:33 ~ 11:10:06) | 48 | 29 (60.4%) | 18 (37.5%) | 0 | 0 |
| 1분봉, 전환 ~ WO-20 재시작 (10-03 21:03:46 ~ 10-04 10:22:33) | 799 | 559 (70.0%) | 240 (30.0%) | 16 | 0 |
| 5분봉, WO-19 기동 ~ 전환 직전 정지 (10-02 10:03:18 ~ 10-03 21:02:34) | 420 | 401 (95.5%) | 19 (4.5%) | 1 | 0 |

- 첫 행의 나머지 1봉은 집계 시각에 처리 중이던 봉이다.
- 원시 집계(중복 포함)는 1분봉 전환 구간 815 = Bar# 559 + 건너뜀 256, 5분봉 421 = 401 + 20.
- **봉 확정 중복**: 거래 없는 봉에서 `[CLOCK] 봉 확정` 이 약 5초 뒤 한 번 더 발화해 같은 봉을 다시 "거래 없음"으로 판정한다 (예: 10-03 22:26:00 과 22:26:05). 17건 모두 거래 없음 봉이었고 `Bar#` 이중 처리는 0건이라 지표가 두 번 갱신된 일은 없다. 불필요한 REST 조회 1회가 더해질 뿐이다.

## A4. 설정 페이지 안내 문구 (`evidence/a4-a5-code-quotes.txt`)

**현재 간격을 읽어 계산한다. 5분봉 고정 문구가 아니다.** (서버 파일과 로컬 HEAD 가 같음: md5 `d45f366a…`)

| 위치 | 문구 | 계산 근거 |
|---|---|---|
| `pages/set_buy_sell_conditions.py:629~641` (현재가 매수 대기 봉 수 입력 도움말) | `현재 {_h_min:g}분봉 기준: 3봉 ≈ {3*_h_min:g}분, 5봉 ≈ {5*_h_min:g}분.` | `load_params(...).interval_sec` (`engine/params.py:272~290`, minute1 → 60) |
| `:873~890` (요약 섹션) | `└─ 대기 봉수: {wait_bars}봉 (약 {wait_bars*interval_sec/60:g}분)` | 같음 |
| `:597~602` (매수 방식 캡션) | `신호 봉의 마감가로 주문을 걸고 {_wb}봉 기다립니다.` | 봉 수만 표시 (시간 없음) |
| `:665~669` (LIVE 안내) | `{wait_bars}봉 기다립니다 … Timeout: {wait_bars}봉 대기 후 미체결 시 자동 취소` | 봉 수만 표시 |

지금(1분봉, 대기 5봉) 투자자 화면에 계산되어 보이는 문구: 도움말 "현재 1분봉 기준: 3봉 ≈ 3분, 5봉 ≈ 5분.", 요약 "└─ 대기 봉수: 5봉 (약 5분)".

## A5. 1분봉에서 실제 시간 (현재 설정, 서버 파일 읽기)

| 설정 | 값 | 단위 | 5분봉일 때 | 1분봉 지금 | 근거 |
|---|---|---|---|---|---|
| 현재가 매수 대기 봉 수 `fixed_price_buy_wait_bars` | 5 | 봉 | 25분 (취소 1,495초) | **5분 (취소 295초)** | `core/strategy_engine.py:1225~1227` `interval_sec × wait_bars`, `engine/order_reconciler.py` `timeout_sec = max(5, interval_sec - 5)` |
| 정체 포지션 기준 `stale_hours` | 1.0 | **시간** | 1시간 | 1시간 (봉 수 아님, 간격 무관) | `core/filters/sell_filters.py:456~463`. 현재 `stale_position_check=false` 로 꺼짐 |
| 최소 보유 `min_holding_period` | 1 | 봉 | 5분 | 1분 | params |
| EMA 빠른선 `fast_period` | 60 | 봉 | 5시간 | **1시간** | params |
| EMA 느린선(기준선) `slow_period` | 200 | 봉 | 약 16.7시간 | **약 3.3시간** | params |
| 워밍업 / 긴 이력 시드 | 200 / 800 | 봉 | 16.7시간 / 66.7시간 | 3.3시간 / 13.3시간 | `engine/live_loop.py` |
| 손절·익절·trailing | 1.0% / 1.5% / 30% | 비율 | — | 간격 무관 | conditions |

EMA 기간이 봉 수 기준이라 1분봉 전환으로 지표가 보는 시간 폭이 1/5 로 줄었다. 운영자 설정 선택이며 결함은 아니다.

## A6. 서버 보안 점검 (`evidence/a6-security.txt`)

| 항목 | 결과 |
|---|---|
| `.env` | `-rw------- root` (600) |
| `.streamlit/secrets.toml` | `-rw------- root` (600) |
| **`.env.bak`** | **`-rw-r--r-- root` (644)**, 키 이름 11개, `UPBIT_ACCESS`·`TELEGRAM_BOT_TOKEN` 값 있음. git 미추적(`.gitignore:31 *.bak`) |
| `/root` | `drwx------` (700). uid ≥ 1000 일반 계정 없음 → 다른 계정은 접근 경로 없음 |
| `server.enableStaticServing` | **False** (Streamlit 1.46.0 실행 설정, `.streamlit/config.toml` 에는 `fileWatcherType = "none"` 만). `static/` 폴더 없음 |
| 기타 | `enableXsrfProtection=True`, `headless=True`, 포트 8501 (systemd `--server.address=0.0.0.0`) |
| 최근 7일 외부 스캐너 요청 (09-27 11:07 ~ 10-04 11:07) | **7건 모두 거부**: `.git/config` 5, `.env` 1, `....//....//....//app/.streamlit/secrets.toml` 1. 각 요청이 `MediaFileHandler: Missing file` + `MediaFileStorageError: Bad filename … (No media file with id …)` 로 끝남 (Traceback 21줄 = 7건 × 3묶음). 날짜: 09-28 3, 10-02 2, 10-03 2 |

판단: 스캐너는 Streamlit 미디어 경로로 비밀 파일을 찾지만 미디어 저장소 ID 가 아니어서 모두 거부된다. Streamlit 은 성공 응답을 로그로 남기지 않으므로, "모두 거부"는 기록된 7건 각각이 거부 예외로 끝났다는 뜻이다. `.env.bak` 권한은 위생 문제로 보고만 한다 (서버 무변경 원칙).

## B. 검증 스크립트 정비

### B1. `scripts/wo17s_verify_seed.py` (`script.diff`)

- `--interval` 인자 (`minute1`·`minute5`·… 또는 분 숫자). 없으면 params JSON(기본 저장소 루트 `mcmax33_latest_params_EMA.json`, `--params` 로 변경)의 `interval` 을 읽는다.
- 출력 첫 줄: `봉 간격: minuteN (출처: --interval 인자 | params JSON <경로>)`.
- 캔들 URL 과 확정 봉 판정(`봉 시작 + 간격 ≤ 기동 시각`)이 간격을 따른다. 기존 위치 인자 4개는 그대로 받는다.
- 회귀 확인 (`evidence/b1-verify-minute5.txt`, `evidence/b1-verify-minute1.txt`):

| 실행 | 결과 | 기존 출력과 |
|---|---|---|
| WO-19 기동 값 `"2026-10-02 10:03:26" 736.1508 733.8483 --interval minute5` | 마지막 확정 봉 09:55, 800 재현 +0.0000 / +0.0000, 1200 기준 +0.0000 / +0.0040 | **같음** (WO-19 배포 때 5분봉 고정판 출력) |
| 같은 값 + 위치 인자 `1200 --interval minute5` | 같음 | 같음 |
| WO-20 기동 값 `"2026-10-04 10:22:41" 764.0099 767.5907 --interval 1` | 마지막 확정 봉 10:21, +0.0000 / +0.0000, +0.0000 / +0.0052 | **같음** (WO-20 배포 때 1분봉 사본 출력) |
| 인자 없음 | `봉 간격: minute1 (출처: params JSON …/mcmax33_latest_params_EMA.json)` | — |

### B2. 운영 가이드 사후 확증 7번

1분봉 주의 문단을 "간격 인자 사용" 안내로 바꿨다. 실행 예에 `--interval` 을 넣고, 출력 첫 줄의 간격이 그 기동의 journal `[CLOCK] Initialized | timeframe=minuteN` 과 같은지 먼저 보라고 적었다. 지난 기동은 그 기동의 간격(10-03 21:03:47 부터 minute1, 그 전 minute5)을 넣는다.

### B3. 커밋·푸시

커밋 1건 (스크립트 + 가이드 + 이 점검 문서). 버전 변경 없음. 서버 pull 없음. `commands.txt` 참조.

## 묶음

- `report.md` (이 문서), `commands.txt`, `git-log.txt`, `script.diff`
- `evidence/`: settings_history 조회, 21:02~21:10 journal, 기동 이후 journal, 비율·중복 집계, 보안 점검, 코드 인용, 스크립트 회귀 출력, 조회 스크립트
