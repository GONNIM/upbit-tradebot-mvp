# 배포 체크리스트 (systemctl restart 기반)

**목적**: `systemctl restart tradebot` 후 배포가 완결됐다고 판단하는 기준을 명시.
과거 사고 재발 방지용 최소 체크리스트.

---

## 배포 완결 기준

`systemctl restart tradebot` 만으로는 배포 완결이 아니다. **엔진 세션 개시 확인까지가 배포 완결**이다.

Streamlit 서비스는 재시작 후 웹 서버만 대기 상태로 들어가고, 실제 트레이딩 엔진(`engine/live_loop.py`)은 세션 진입(대시보드 접속 또는 `[AUTO-RESUME]` 트리거) 시에만 시작된다. 서비스가 `active (running)`이어도 엔진이 시작되지 않으면 트레이딩 공백이 발생한다.

### 배포 완결 확인 로그 시퀀스

`journalctl -u tradebot` 에서 다음 로그가 **모두 출현**해야 배포 완결:

1. `🚀 [UPBIT_MATCH] Clock-based REST Reconcile 모드 시작`
2. `✅ CandleClock 초기화 | interval=minute1 | interval_sec=60`
3. `✅ [WARMUP] REST 데이터 로드 완료 | bars=200`
4. `✅ Indicator seeded (separate EMA) | BUY: ... | SELL: ... | base=...`
5. `✅ Warmup 완료 | bars=200`
6. `🚀 [CLOCK-LOOP] 시작 - 1초마다 폴링, 봉 확정 시 REST Reconcile`
7. 이후 봉 확정 시각에 `⏰ [CLOCK-CLOSE] 봉 확정 감지` + `✅ [CONFIRMED] 봉 처리 완료`

7번까지 확인되어야 실제 트레이딩이 재개된 것.

### 오류 부재 확인

같은 구간(`--since '<restart_ts>'`)에 다음 로그 **부재** 필수:
- `Traceback` / `Error` / `Exception`
- `OperationalError` / `no such column`
- `CRITICAL` / `POLLUTED`

### 24h 실측 타이머 기점

기점 = **엔진 세션 개시 시각** (위 5번 `Warmup 완료` 또는 6번 `CLOCK-LOOP 시작` 시각). systemd `Started` 시각이 아님.

---

## 신규 확정 판정 로직 배포 규칙

**신규 확정 판정 로직 (fetch_confirmed_candle 계열)은 저유동성 실환경 스모크 통과 전 배포 금지**.
- **케이스 L (라벨 검증)**: v3 함수에 봇의 실 `get_closed_ts()` 결과를 넣고 반환 bar close 를 해당 upbit_ts 분의 ticks API 마지막 체결가와 대조. **불일치 시 구현 불합격**. JTO 실환경 1봉 + BTC 1봉 최소.
- **케이스 M (저유동성 실환경)**: JTO 활성 시간대 3봉 + 저유동성 시간대 3봉 최소. FAST/SLOW/I2/fallback 각 최소 1건 관찰.
- **하네스 라벨 주입 스모크만으로는 라벨 결함 검증 불가** — 2026-08-23 WO-2 1차 배포 실패 사례 (스모크 A가 KRW-BTC + 하네스 계산 라벨로 우연히 성공 → 봇 실전에서 오프바이원 즉시 폭발).

관련 설계안: `docs/plans/2026-08-23-wo2-fetch-confirmed-hardening.md` (개정 2.1판) §7.

---

## 과거 사고 기록

### 2026-08-22 배포 (WO-1 옵션 B, v1.2026.08.22.1002)

- `systemctl restart tradebot`: 10:25:33 KST
- Streamlit 웹 서버 준비: 10:25:34
- **엔진 세션 개시**: 11:16:42 (`Warmup 완료` + `CLOCK-LOOP 시작`)
- **트레이딩 공백**: 약 **51분** (10:25:33 ~ 11:16:42)
- 원인: Streamlit 프로세스는 기동됐으나 트레이딩 엔진(live_loop)이 dashboard 세션/AUTO-RESUME 트리거를 기다림. 배포 완결을 systemd `active` 상태로만 판정하면 공백을 놓친다.
- 재발 방지: 본 체크리스트의 7단계 로그 시퀀스 확인 의무화.

### 2026-08-23 배포 (WO-2 2차, v3 + P0 옵션 A, v1.2026.08.23.1849) — **롤백 (29분)**

- `systemctl restart tradebot`: 18:52:28 KST → 엔진 시작 18:53:47
- **29분 만에 audit 라벨 이중화 확정 (LV1 4쌍)** + dashboard AttributeError (LV3 트립와이어)
- 롤백 restart: 19:22:50 (약 29분 트레이딩 공백)
- 근본 원인 (LV2): v3 라벨 복원 (`row.name = closed_ts`) + `live_loop.py:971 rest_df.loc[closed_ts] = confirmed_row` — 봇 라벨 위치를 upbit T 데이터로 덮어쓰기 → 동일 upbit 캔들이 두 라벨(upbit T + 봇 T+1)로 이중 존재
- 트립와이어: `dashboard.py:1396 AttributeError` (매매 무관, missing_bar 방어 부재)
- **오염 구간**: 18:53:51 ~ 19:22:50 audit_buy_eval 이중 행 존재 (삭제 없이 기록 보존)
- 재발 방지: 아래 "라벨 정합 검증 관문" (스모크 Q) + AD1 dashboard 방어 가드.

### 신규 관문: 라벨 정합 검증 (스모크 Q 실전판)

**배포 직후 30분 내 다음 SQL 실행 필수. 결과 1행 이상 시 즉시 롤백**:

```sql
-- 실시간 T+1 price == 백필 T backfill_close 이중화 쌍 (0행 필수)
SELECT r.bar_time AS realtime_ts, r.price, b.bar_time AS backfill_ts, b.backfill_close
FROM audit_buy_eval r JOIN audit_buy_eval b
  ON r.ticker = b.ticker
  AND datetime(r.bar_time, '-1 minute') = datetime(b.bar_time)
  AND r.price = b.backfill_close
  AND r.price IS NOT NULL AND b.backfill_close IS NOT NULL
WHERE r.ticker = '<TICKER>'
  AND r.bar_time >= '<배포 엔진 시작 시각>';
```

### 2026-08-23 배포 (WO-2 1차, 옵션 6 단독, v1.2026.08.23.1713) — **롤백**

- `systemctl restart tradebot`: 17:17:57 KST → 엔진 시작 17:19:25
- **5분 만에 5봉 연속 fallback + CRITICAL 알림 발동** (17:20~17:24 각 fallback, 17:24:36 CRITICAL)
- 롤백 restart: 17:31:36 (12분 트레이딩 공백)
- 1차 원인 (D2): `candle_clock.py:82 get_closed_ts` 오프바이원 (진행 중 봉 시작 시각을 확정 봉 라벨로 반환). 옵션 6 has_next 판정이 실질적으로 "다음다음 봉 존재" 조건이 됨.
- 2차 원인 (D3): JTO 저유동성 (다음 봉 존재율 72.5%). 오프바이원과 결합해 100% 실패로 증폭.
- 스모크 결함: 케이스 A가 KRW-BTC + 하네스 계산 라벨로 우연히 성공 → 봇 실전 라벨을 검증 못함.
- 재발 방지: 위 "신규 확정 판정 로직 배포 규칙" (케이스 L + M 필수화).

---

## 관련 문서

- `docs/analysis/20260821-01-JTO-GC-Miss-Analysis.md` — WO-1 배포 사이클 진단·수정 리포트 (부록 C 단계 배포 정책)
- `.claude/context/project-rules.md` — 커밋/배포 표준 절차
