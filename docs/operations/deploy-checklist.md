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

## 관련 문서

- `docs/analysis/20260821-01-JTO-GC-Miss-Analysis.md` — WO-1 배포 사이클 진단·수정 리포트 (부록 C 단계 배포 정책)
- `.claude/context/project-rules.md` — 커밋/배포 표준 절차
