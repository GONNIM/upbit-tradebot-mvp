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

## 과거 사고 기록

### 2026-08-22 배포 (WO-1 옵션 B, v1.2026.08.22.1002)

- `systemctl restart tradebot`: 10:25:33 KST
- Streamlit 웹 서버 준비: 10:25:34
- **엔진 세션 개시**: 11:16:42 (`Warmup 완료` + `CLOCK-LOOP 시작`)
- **트레이딩 공백**: 약 **51분** (10:25:33 ~ 11:16:42)
- 원인: Streamlit 프로세스는 기동됐으나 트레이딩 엔진(live_loop)이 dashboard 세션/AUTO-RESUME 트리거를 기다림. 배포 완결을 systemd `active` 상태로만 판정하면 공백을 놓친다.
- 재발 방지: 본 체크리스트의 7단계 로그 시퀀스 확인 의무화.

---

## 운영 위험 기록

### 2026-08-25 지정가→시장가 전환 + F5 결합 위험 (조치는 운영자 결정 대기)

2026-08-21 19:52에 대시보드에서 고정가 매수가 해제되어 시장가 모드로 전환됨.
현재 서버(WO-1)는 F5 결함(미확정 종가 기반 매수 판정)이 있는 버전이므로,
시장가 모드와 결합 시 가짜 신호가 즉시 실체결로 이어질 수 있음. WO-6 완료
전까지 지정가 복원이 권고되며, 복원 여부는 운영자와 사용자의 결정 사항.

### WO-6 배포 이후 감사 시각 표시 변화 예고 (운영 주석)

WO-6이 배포되면 `candle_clock.get_closed_ts`의 반환값 의미가 재정의되어,
감사 로그(`audit_buy_eval`, `audit_trades`)와 대시보드에 표시되는 봉 시각
(`bar_time`)이 개편 이전보다 60초 앞당겨 보이게 됨. 이는 실제 시장 마감
시각(Upbit 봉 시작 시각)에 맞춘 정상 표기이며, 매매 판단이나 발주 시점
자체가 앞당겨지는 것은 아님. 배포 시점을 기준으로 이 표시 변화를 운영자와
사용자에게 사전 안내할 것.

### 2026-08-29 WO-6 배포 (v1.2026.08.29.1926)

- 커밋: WO-6 시각 표기 통일 + 봉당 매매 판단 1회 강제 + 케이스 재배치
  + NO_TRADE 표지 + F1/F1b/F2 보완.
- 서버 롤백용 해시: `1404c1c`.
- 24시간 실측 롤백 조건:
  - 실시간 판단 커버리지 70% 미만 → 즉시 롤백.
  - 총 지표 반영 커버리지 90% 미만 → 즉시 롤백.
  - 봉당 판단 위반 1건 → 즉시 롤백.
  - 지표 이탈이 시드 오차 상한의 3배 초과 → 즉시 롤백 (fast_period=20,
    시드 60봉 이상 이전 기준).
  - 저유동성 시간대 실시간 커버리지 50% 미만 → 관찰 강화 (롤백 아님).
  - 거짓 CRITICAL 1건(무거래 원인) → F1b 결함으로 즉시 보고.
- 커버리지 산식: 모집단 = Upbit 원본 `/candles/minutes/1` 응답, 실시간
  판단 커버리지 = `audit_buy_eval.price IS NOT NULL` 봉 수 / 모집단.

---

## 관련 문서

- `docs/analysis/20260821-01-JTO-GC-Miss-Analysis.md` — WO-1 배포 사이클 진단·수정 리포트 (부록 C 단계 배포 정책)
- `.claude/context/project-rules.md` — 커밋/배포 표준 절차
