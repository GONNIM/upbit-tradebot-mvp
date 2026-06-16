# Tradebot 알림 시스템 운영 매뉴얼

**작성일**: 2026-06-16
**작성자**: CTO Assistant (Claude Code)
**버전**: 1.0
**적용 서버**: orionhunter7.cafe24.com
**대상**: 운영자·온콜 엔지니어

---

## 📋 목차

1. [전체 구조](#1-전체-구조)
2. [채널 A — Python 인-프로세스 (19 이벤트)](#2-채널-a--python-인-프로세스-19-이벤트)
3. [채널 B — 서버 cron 워치독 (7 이벤트)](#3-채널-b--서버-cron-워치독-7-이벤트)
4. [운영자 대응 체크리스트](#4-운영자-대응-체크리스트)
5. [트러블슈팅](#5-트러블슈팅)
6. [관련 문서·스크립트](#6-관련-문서스크립트)
7. [변경 이력](#7-변경-이력)

---

## 1. 전체 구조

### 1.1 두 채널 동일 chat 송신

알림은 **서로 다른 코드베이스**의 두 채널이 **같은 Telegram chat**으로 송신:

```
                  ┌─────────────────────────────────────┐
                  │ Telegram chat (TELEGRAM_CHAT_ID)    │
                  └──────────────▲──────────────────────┘
                                 │
            ┌────────────────────┴────────────────────┐
            │                                         │
   ┌────────┴────────┐                       ┌───────┴─────────┐
   │ 채널 A — Python │                       │ 채널 B — Shell  │
   │ services/       │                       │ /root/*.sh      │
   │  notifier.py    │                       │ /root/notify_   │
   │ (in-process)    │                       │  telegram.sh    │
   │ 22 호출지점      │                       │ cron 기반        │
   │ 19 이벤트       │                       │ 7 이벤트          │
   └─────────────────┘                       └─────────────────┘
            ▲                                         ▲
            │ env / streamlit.secrets                 │ /root/upbit-tradebot-mvp/.env
            └────────────┬────────────────────────────┘
                         │
          TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID
```

### 1.2 메시지 포맷 (양 채널 동일)

```
<b>{prefix} {title}</b>
<pre>{body}</pre>
```

- HTML parse mode
- `{prefix}` — 채널 A: `🚨`(CRITICAL) / `⚠️`(WARNING) / `ℹ️`(INFO). 채널 B: 제목에 직접 임베드
- 본문 5초 타임아웃, 실패 시 silent (본업 비차단)

### 1.3 Dedupe 정책 비교

| 채널 | 메커니즘 | 저장소 | 기본 TTL |
|---|---|---|---|
| A (Python) | 메모리 dict `_dedupe_state` (notifier.py:48) | 프로세스 내 | 300s |
| B (Shell, watchdog만) | `/var/run/tradebot_stale.lock` mtime | tmpfs (재부팅 자동 정리) | 3600s |
| B (Shell, 그 외) | 없음 (cron 빈도로 자연 제한) | — | — |

### 1.4 총괄 통계

| 분류 | 채널 A | 채널 B | 합계 |
|---|---:|---:|---:|
| CRITICAL (거래/엔진 운영) | 14 | 0 | 14 |
| WARNING (신호/시스템 경고) | 5 | 4 | 9 |
| INFO (정기 다이제스트/정리) | 0 | 3 | 3 |
| **총 고유 이벤트** | **19** | **7** | **26** |

---

## 2. 채널 A — Python 인-프로세스 (19 이벤트)

진입점: `services/notifier.py::send(level, title, body, dedupe_key, dedupe_ttl)`

### 2.1 거래 이벤트 — CRITICAL (`core/trader.py`)

| # | 제목 | 본문 키 | dedupe | 위치 |
|---|---|---|---|---|
| 1 | 🟢 `[LIVE BUY 요청] {ticker}` | 예상가/사용 KRW/uuid | `buy_req:{uuid}` / 60s | trader.py:637 |
| 2 | 🔴 `[LIVE SELL 요청] {ticker}` | 예상가/수량/uuid | `sell_req:{uuid}` / 60s | trader.py:1088 |
| 3 | ❌ `[LIVE BUY 실패] {ticker}` | attempts/non_retriable/err | `buy_fail:{ticker}:{err}` / 60s | trader.py:512 |
| 4 | ❌ `[LIVE SELL 실패] {ticker}` | qty/err | `sell_fail:{ticker}:{err}` / 60s | trader.py:1005 |
| 5 | 🔑 `Upbit API 인증 실패` | err_summary | `api_auth:{err}` / 600s | trader.py:525, 1019 |
| 6 | ❌ `[LIVE 고정가 매수 거부] {ticker}` (호가) | 원가/조정가 | `fixed_buy_tick:{ticker}` / 60s | trader.py:703 |
| 7 | ❌ `[LIVE 고정가 매수 거부] {ticker}` (주문) | price/qty/err | `fixed_buy_fail:{ticker}:{err[:80]}` / 60s | trader.py:798 |
| 8 | 🎯 `[LIVE 고정가 매수 요청] {ticker}` | 지정가/수량/timeout/uuid | `fixed_buy_req:{uuid}` / 60s | trader.py:862 |

### 2.2 거래 이벤트 — WARNING (`core/trader.py`)

| # | 제목 | 본문 키 | dedupe | 위치 |
|---|---|---|---|---|
| 9 | ❌ `[LIVE 고정가 매수 잔고 부족] {ticker}` | 가용 KRW=0 / 주문 불가 | `fixed_buy_balance_zero:{ticker}` / 60s | trader.py:728 |
| 10 | ❌ `[LIVE 고정가 매수 잔고 부족] {ticker}` | 가용 KRW=N / 필요≥5,000 | `fixed_buy_balance:{ticker}` / 60s | trader.py:751 |

### 2.3 전략 신호 — WARNING (`core/strategy_incremental.py`)

| # | 제목 | 본문 키 | dedupe | 위치 |
|---|---|---|---|---|
| 11 | 🔔 `[MACD Golden Cross] {ticker}` | macd/signal/threshold | `macd_gc:{ticker}` / 180s | strategy_incremental.py:263 |
| 12 | 🔻 `[MACD Dead Cross] {ticker}` | macd/signal | `macd_dc:{ticker}` / 180s | strategy_incremental.py:421 |
| 13 | 🔔 `[EMA Golden Cross] {ticker}` | ema_fast/ema_slow | `ema_gc:{ticker}` / 180s | strategy_incremental.py:811 |

### 2.4 시스템 경고 — WARNING (`engine/`)

| # | 제목 | 본문 키 | dedupe | 위치 |
|---|---|---|---|---|
| 14 | ⏱ `[LIVE 고정가 매수 미체결 취소] {ticker}` | 지정가/elapsed/uuid | `fixed_buy_timeout:{uuid}` / 60s | order_reconciler.py:355 |
| 15 | ⚠️ `[REST API 연속 실패]` | closed_ts/시도수/대기 | `rest_retry_exhausted` / 300s | live_loop.py:1126 |

### 2.5 엔진 운영 — CRITICAL (`pages/`)

| # | 제목 | 본문 키 | dedupe | 위치 |
|---|---|---|---|---|
| 16 | ▶️ `[엔진 시작] {user_id} ({mode})` | dashboard 클릭 | `engine_start:{user_id}` / 30s | dashboard.py:542 |
| 17 | ❌ `[엔진 시작 실패] {user_id} ({mode})` | start_engine returned False | `engine_start_fail:{user_id}` / 60s | dashboard.py:559 |
| 18 | ⏸️ `[엔진 자동 종료] {user_id} ({mode})` | 파라미터 설정 진입 | `engine_auto_stop_params:{user_id}` / 30s | dashboard.py:584 |
| 19 | ⏹️ `[엔진 수동 종료] {user_id} ({mode})` | dashboard 클릭 | `engine_stop:{user_id}` / 30s | dashboard.py:1948 |
| 20 | 💥 `[엔진 종료 — 시스템 초기화] {user_id}` | 시스템 초기화 실행 | `engine_reset:{user_id}` / 30s | confirm_init_db.py:51 |
| 21 | ⚠️ `[AUTO-RESUME 실패] {user_id}` | verified/capital_set | `auto_resume_fail:{user_id}` / 600s | dashboard.py:410 |

---

## 3. 채널 B — 서버 cron 워치독 (7 이벤트)

진입점: `/root/notify_telegram.sh "<TITLE>" "<BODY>"`
저장소 미러: `scripts/server/*.sh`

### 3.1 엔진 정체 감시 (`watchdog_tradebot_engine.sh`)

**스케줄**: `*/5 * * * *` (5분마다)
**데이터 소스**: `journalctl -u tradebot --since "30 min ago" | grep "Bar#"`
**Dedupe**: `/var/run/tradebot_stale.lock` mtime + TTL 3600s (2026-06-16 도입)

| # | 트리거 | 제목 | 본문 |
|---|---|---|---|
| 22 | 최근 30분간 `Bar#` 로그 0건 | ⚠️ `[STALE] tradebot 엔진` | `최근 30분간 Bar# 평가 로그 없음 (엔진 정체 가능성)` |
| 23 | 마지막 `Bar#` > 600초 경과 | ⚠️ `[STALE] tradebot 엔진 정체` | `last Bar# was {gap}s ago (threshold 600s)`<br>`last_line: {원본}` |
| 24 | stale 상태 → 정상 전환 | ✅ `[RECOVERED] tradebot 엔진` | `Bar# 평가 정상화 (gap={N}s)`<br>`last_line: {원본}` |

→ 로그: `/var/log/tradebot_engine_stale.log`

### 3.2 메모리 감시 + 자동 재시작 (`monitor_tradebot_memory.sh`)

**스케줄**: `*/10 * * * *` (10분마다)
**임계**: `MAX_MEMORY_MB=1400` (1.4GB, 시스템 1.9GB의 70%)
**Dedupe**: 없음 (자동 재시작으로 자연 해소)

| # | 트리거 | 제목 | 본문 | 부수 효과 |
|---|---|---|---|---|
| 25 | RSS > 1400MB | ⚠️ `[MEMORY] 임계값 초과` | `현재: {N}MB / 임계: 1400MB → 재시작 시도` | — |
| 26 | systemctl restart 완료 | 🔄 `[SYSTEM] tradebot 재시작` | `사유: 메모리 임계 초과 (현재 {N}MB)` | 5초 sleep 후 발화 |

→ 로그: `/var/log/tradebot_memory_monitor.log` (10분마다 INFO 누적)

### 3.3 주간 DB 정리 (`cleanup_tradebot_db.sh`)

**스케줄**: `0 11 * * 0` (매주 일요일 11:00)
**방식**: 무중단 v2 — WAL checkpoint(TRUNCATE), systemctl restart 미실행

| # | 트리거 | 제목 | 본문 |
|---|---|---|---|
| 27 | 정리 완료 (1주 1회) | 🧹 `[DB 정리 완료]` | `삭제: buy=N sell=N logs=N`<br>`체크포인트: {result}`<br>`DB 크기: {size}` |

→ 로그: `/var/log/tradebot_cleanup.log`. 30일 이전 audit/logs DELETE + 7일 이전 .backup 삭제.

### 3.4 일일 요약 (`daily_digest_tradebot.sh`)

**스케줄**: `0 9 * * *` (매일 09:00 KST)
**데이터 소스**: SQLite `tradebot_mcmax33.db`

| # | 트리거 | 제목 | 본문 |
|---|---|---|---|
| 28 | 매일 09:00 | 📊 `[일일 요약] tradebot` | 기간 24h / BUY 평가 / SELL 평가 / 로그 / 주문 4-tuple / KRW 잔고 |

### 3.5 주간 요약 (`weekly_digest_tradebot.sh`)

**스케줄**: `0 9 * * 1` (매주 월요일 09:00 KST)

| # | 트리거 | 제목 | 본문 |
|---|---|---|---|
| 29 | 매주 월 09:00 | 📈 `[주간 요약] tradebot` | 기간 7d / BUY-SELL 평가 / 체결 BUY-SELL / 실패 주문 / KRW 잔고 |

> 이벤트 번호 #22~#29는 7건. RECOVERED(#24)는 분기 A·B 공통 복구 알림이므로 stale 알림 2종(#22, #23)에 종속.

---

## 4. 운영자 대응 체크리스트

### 4.1 거래 알림 (#1~#10)

| 신호 | 즉시 확인 | 권장 조치 |
|---|---|---|
| 🟢 BUY 요청 / 🔴 SELL 요청 | 정상 거래 흐름 — Dashboard `LIVE` 모드 + 최근 시그널 일치? | 무조치 (수분 내 체결 reconciler 처리) |
| ❌ BUY/SELL 실패 | err_summary의 Upbit 에러 코드 확인 | 5분 내 자동 재시도. 3회 후 FAILURE 시 운영자 개입 |
| 🔑 API 인증 실패 | JWT/IP 화이트리스트 확인 | Upbit 콘솔에서 API 키·IP 재확인 (Issue #6 참조) |
| ❌ 고정가 잔고 부족 | KRW 잔고 > 5,000원? | 입금 또는 risk_pct 조정 |
| 🎯 고정가 매수 요청 | 지정가 = 봉 종가? | timeout(다음 봉) 내 체결 대기 |

### 4.2 시스템 알림 (#14~#15, #22~#26)

| 신호 | 즉시 확인 | 권장 조치 |
|---|---|---|
| ⚠️ STALE tradebot 엔진 (#22) | `systemctl status tradebot` 확인 | active=running 이면 journalctl로 Python 예외 추적. dead면 systemctl restart |
| ⚠️ STALE tradebot 엔진 정체 (#23) | journalctl 마지막 Bar# 시각 확인 | 600s 초과는 보통 일시적 API 지연 — 60분 내 RECOVERED 안 오면 개입 |
| ✅ RECOVERED tradebot 엔진 (#24) | — | 무조치 (정상화 확인) |
| ⚠️ MEMORY 임계값 초과 (#25) | `🔄 [SYSTEM] tradebot 재시작` 후속 알림 도착? | 도착 시 정상 자동 복구. 미도착 시 systemctl 수동 개입 |
| 🔄 tradebot 재시작 (#26) | 메모리 사용량 정상화 확인 | Dashboard 새로고침으로 엔진 재개 확인 |
| ⏱ 고정가 미체결 취소 (#14) | 봉 간격 내 미체결 → 자연 취소 | 무조치 (다음 봉 재평가) |
| ⚠️ REST API 연속 실패 (#15) | Upbit API status 확인 | 5분 dedupe — 1회 알림이 봉 다수 스킵 의미 |

### 4.3 엔진 운영 알림 (#16~#21)

| 신호 | 의미 |
|---|---|
| ▶️ 엔진 시작 (#16) | 운영자가 직접 시작 — 정상 |
| ❌ 엔진 시작 실패 (#17) | start_engine() False — `mcmax33_engine_debug.log` 즉시 확인 |
| ⏸️ 자동 종료 (#18) | 파라미터 설정 페이지 진입 — 정상 |
| ⏹️ 수동 종료 (#19) | 운영자가 직접 종료 — 정상 |
| 💥 시스템 초기화 종료 (#20) | DB 초기화 실행 — **데이터 손실 주의** |
| ⚠️ AUTO-RESUME 실패 (#21) | 재부팅 후 자동 재개 실패 — Dashboard 수동 시작 필요 |

### 4.4 다이제스트 알림 (#27~#29)

- 📊 일일 요약 (#28) — 매일 09:00 자동 도착. **미도착이면 cron 또는 sqlite 이슈** 의심
- 📈 주간 요약 (#29) — 매주 월 09:00 자동 도착
- 🧹 DB 정리 완료 (#27) — 매주 일 11:00 자동 도착

---

## 5. 트러블슈팅

### 5.1 알림 폭주 (동일 알림 분당 N건)

```
[원인 분기]
  채널 A (Python)   → dedupe_ttl 검토 (notifier.py 호출처)
  채널 B (watchdog) → /var/run/tradebot_stale.lock 상태 확인
                      stat -c %Y /var/run/tradebot_stale.lock
                      DEDUPE_TTL=3600 변경 시 scripts/server/watchdog_tradebot_engine.sh
  채널 B (memory)   → 실제 메모리 누수 — psutil 분석
  채널 B (cleanup)  → 비정상 (cron 0 11 일요일에만 발화)
```

### 5.2 알림 미도착

```
[확인 순서]
  1) Telegram chat ID·BOT_TOKEN 환경변수 / .env / streamlit.secrets 동기?
  2) /root/notify_telegram.sh 실행 권한 (-rwxr-xr-x)
  3) Telegram Bot API 응답 — curl 직접 테스트 가능
  4) network/outbound 차단 여부 (방화벽)
  5) Python 측: services/notifier.py logger.warning 로그 확인
```

### 5.3 STALE 알림이 떴지만 엔진은 살아 있어 보임

- journalctl 출력에 Bar# 로그가 grep 매치 안 되는 경우. `strategy_engine.py:666,672` 로깅 정상인지 확인
- systemd journal rotate로 30분 윈도우 데이터 손실 가능성 — `journalctl --since "30 min ago" -u tradebot | head` 로 직접 확인
- watchdog의 `date -d` 파싱 실패 시 silent exit — `/var/log/tradebot_engine_stale.log` 의 `시각 파싱 실패` 라인 확인

### 5.4 [RECOVERED] 알림이 안 옴

- LOCK_FILE이 없으면 RECOVERED 발화 안 함 (정상)
- 시각 파싱 실패 분기로 빠지면 LOCK_FILE 유지된 채 silent — 다음 cron에서 정상 처리 시 RECOVERED 발화
- 수동 정리: `rm /var/run/tradebot_stale.lock`

### 5.5 운영자 호출 우선순위 (페이저용)

| 우선순위 | 알림 |
|---|---|
| P0 (즉시) | ❌ BUY/SELL 실패, 🔑 API 인증 실패, 💥 시스템 초기화, ❌ 엔진 시작 실패, ⚠️ AUTO-RESUME 실패 |
| P1 (1시간 내) | ⚠️ STALE tradebot 엔진/정체, ⚠️ MEMORY 임계 초과, ⚠️ REST API 연속 실패 |
| P2 (영업일) | 🧹 DB 정리 부재, 📊 일일 요약 부재, 📈 주간 요약 부재 |
| INFO (참고) | 🟢/🔴 거래 요청, 🔔 Golden/Dead Cross, ▶️/⏹️ 엔진 시작·종료, ✅ RECOVERED |

---

## 6. 관련 문서·스크립트

### 6.1 코드 진입점

- `services/notifier.py` — Python 채널 진입점 (`send()` 함수)
- `scripts/server/notify_telegram.sh` — Shell 채널 진입점 (.env 토큰 로드)
- `scripts/server/watchdog_tradebot_engine.sh` — STALE 감시 + dedupe
- `scripts/server/monitor_tradebot_memory.sh` — 메모리 감시
- `scripts/server/cleanup_tradebot_db.sh` — DB 정리
- `scripts/server/daily_digest_tradebot.sh` — 일일 다이제스트
- `scripts/server/weekly_digest_tradebot.sh` — 주간 다이제스트

### 6.2 서버 cron 등록 위치

```
/var/spool/cron/crontabs/root
0 3 * * *      certbot renew --quiet
*/10 * * * *   /root/monitor_tradebot_memory.sh
0 11 * * 0     /root/cleanup_tradebot_db.sh
*/5 * * * *    /root/watchdog_tradebot_engine.sh
0 9 * * *      /root/daily_digest_tradebot.sh
0 9 * * 1      /root/weekly_digest_tradebot.sh
```

### 6.3 로그 파일

| 로그 | 경로 | 회전 |
|---|---|---|
| Tradebot Python | journalctl -u tradebot | systemd 기본 |
| 엔진 stale 감시 | `/var/log/tradebot_engine_stale.log` | 수동 |
| 메모리 감시 | `/var/log/tradebot_memory_monitor.log` | 수동 |
| DB 정리 | `/var/log/tradebot_cleanup.log` | 수동 |
| 디버그 (engine) | `/root/upbit-tradebot-mvp/mcmax33_engine_debug.log` | 수동 |

### 6.4 자격증명 위치

- `/root/upbit-tradebot-mvp/.env` (600 권한, gitignore 13행) — Python·Shell 양 채널 공통
- `/root/upbit-tradebot-mvp/.streamlit/secrets.toml` (600 권한, gitignore 18행) — Streamlit fallback
- 두 채널이 같은 `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` 사용

---

## 7. 변경 이력

| 날짜 | 변경 | 커밋 |
|---|---|---|
| 2026-05-31 | Critical/중요/다이제스트 13건 + 엔진 시작/종료 4종 Python 알림 통합 | 7a6042c, 4810402 |
| 2026-06-15 | 고정가 매수 Telegram 4종 + 잔고 0원 경고 | f6300ee, b444fa2 |
| 2026-06-16 | 서버 cron 스크립트 6종 저장소 편입 | 92dad32 |
| 2026-06-16 | STALE dedupe (TTL 3600s) + RECOVERED 알림 추가 | 372ccd1 |
| 2026-06-16 | credentials.yaml / secrets.toml 권한 644→600 | (수동 chmod) |
| 2026-06-16 | 본 문서 작성 (운영 매뉴얼 v1.0) | (이 커밋) |
