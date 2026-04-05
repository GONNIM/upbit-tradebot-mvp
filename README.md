# Upbit Tradebot MVP

> **자동화된 암호화폐 트레이딩 봇 - EMA/MACD 전략 기반**

---

## 📖 프로젝트 개요

Upbit API를 활용한 자동매매 봇으로, EMA(지수이동평균)와 MACD 지표를 기반으로 한 체계적인 매매 전략을 실행합니다.

**핵심 기능:**
- ✅ **REST Reconcile** - REST API와 로컬 데이터의 정합성 보장
- ✅ **증분 지표 계산** - EMA, MACD 실시간 업데이트 (전체 재계산 불필요)
- ✅ **Golden/Dead Cross 감지** - 빠른 추세 전환 포착
- ✅ **다층 필터 시스템** - Take Profit, Trailing Stop, Stale Position 등
- ✅ **BACKFILL** - 누락/변경 봉 자동 재평가 (지표 상태 보존)

**지원 전략:**
- **EMA Strategy** - 빠른 EMA와 느린 EMA의 크로스 기반 매매
- **MACD Strategy** - MACD 라인과 Signal 라인의 크로스 기반 매매

---

## 🚀 빠른 시작

### 1. 로컬 설치

```bash
# Python 3.9 이상 필요
pip install -r requirements.txt

# 환경 변수 설정 (.env 파일)
UPBIT_ACCESS_KEY=your_access_key
UPBIT_SECRET_KEY=your_secret_key
```

### 2. 전략 파라미터 설정

```bash
# EMA 전략 파라미터 (JSON 파일)
cat mcmax33_latest_params_EMA.json
{
  "ticker": "KRW-ZRO",
  "interval": "minute1",
  "ema_fast": 7,
  "ema_slow": 25,
  "take_profit": 0.05,      // 5% 수익 시 매도
  "trailing_stop_threshold": 0.10  // 수익 10% 하락 시 매도
}
```

### 3. 봇 실행

```bash
# 서버 배포 (squad-tradebot.sh 사용)
./squad-tradebot.sh

# 또는 직접 실행
python -m engine.live_loop --ticker KRW-ZRO --strategy EMA
```

---

## 📚 문서 네비게이션

### 빠른 시작
- [설치 가이드](docs/setup/installation.md) - 로컬 환경 설정
- [배포 가이드](docs/setup/deployment.md) - 서버 배포 방법
- [전략 파라미터 설정](docs/operations/strategy-params.md) ⭐ - EMA/MACD 파라미터 수정

### 시스템 아키텍처
- [전체 구조](docs/architecture/overview.md) ⭐ - 엔진, 전략, 필터 구조
- [REST Reconcile](docs/architecture/rest-reconcile.md) - 데이터 정합성 검증 시스템
- [지표 계산](docs/architecture/indicators.md) - EMA/MACD 증분 계산 로직

### 운영 및 모니터링
- [모니터링 가이드](docs/operations/monitoring.md) - 로그 확인 및 성능 추적

### 분석 및 작업 지시서
- [종가 분석](docs/analysis/close-price-analysis.md) - 미확정 종가 문제 분석
- [WO-2026-001](docs/work-orders/2026-001-confirmed-candle.md) - 확정 봉 검증 구현

### AI 어시스턴트 (개발용)
- [Claude Code 가이드](.claude/README.md) - AI 사용법
- [프로젝트 규칙](.claude/context/project-rules.md) ⭐ - Issue #1~#11 교훈

### 설계 문서
- [BACKFILL Golden Cross 수정](thoughts/20260325-01-BACKFILL-Golden-Cross-Fix.md)
- [Post-Exit Reentry 전략](thoughts/20260326-01-Post-Exit-Reentry-Strategy.md)

### 전체 문서 인덱스
- [📄 docs/README.md](docs/README.md) ← **모든 문서 목록**

---

## 🎯 주요 기능 상세

### 1. REST Reconcile 시스템

**문제**: REST API 미확정 종가 반환, 봉 누락/변경
**해결**:
- 매 분봉마다 REST API와 로컬 시계열 비교
- 변경 감지 시 BACKFILL로 재평가
- Progressive Retry로 확정 봉 검증

**자세히**: [docs/architecture/rest-reconcile.md](docs/architecture/rest-reconcile.md)

### 2. 증분 지표 계산

**문제**: 매 봉마다 전체 400개 재계산 → 느림, 부정확
**해결**:
- EMA: 이전 EMA 값 + 현재 종가로 증분 업데이트
- MACD: EMA 증분 업데이트 기반 계산
- 크로스 감지: `prev` 값 추적으로 정확한 타이밍 포착

**자세히**: [docs/architecture/indicators.md](docs/architecture/indicators.md)

### 3. Golden/Dead Cross 감지

**Golden Cross (매수 신호)**:
```
이전: ema_fast <= ema_slow (Dead)
현재: ema_fast > ema_slow (Golden)
→ 매수 발생!
```

**Dead Cross (매도 신호)**:
```
이전: ema_fast >= ema_slow (Golden)
현재: ema_fast < ema_slow (Dead)
→ 매도 발생!
```

**Issue #11 해결**: BACKFILL이 `prev` 값을 오염시키지 않도록 백업/복원

### 4. 다층 필터 시스템

**매수 필터**:
- Cooldown Filter - 매도 후 N분 대기
- Position Limit - 최대 1개 포지션

**매도 필터**:
- Take Profit - N% 수익 시 매도 (예: 5%)
- Trailing Stop - 수익의 N% 하락 시 매도 (Profit-based)
- Stale Position - N시간 동안 수익 M% 미만 시 강제 매도 (시간 기반)
- Stop Loss - N% 손실 시 매도 (예: -3%)

**자세히**: [docs/operations/strategy-params.md](docs/operations/strategy-params.md)

---

## 🐛 트러블슈팅

### Golden Cross 발생했는데 매수 안 됨

**증상**: 로그에 `Golden | NO_SIGNAL`

**원인 (Issue #11)**:
- BACKFILL이 `prev_ema_fast`, `prev_ema_slow` 값을 덮어씀
- 실시간 봉에서 크로스 감지 실패

**해결**:
1. `.claude/context/project-rules.md` Issue #11 확인
2. `thoughts/20260325-01-BACKFILL-Golden-Cross-Fix.md` 참조
3. 로그에서 "지표 상태 백업/복원" 확인

### REST API 미확정 종가 문제

**증상**: DB 종가와 Upbit 차트 종가 불일치 (±0.3%)

**원인 (Issue #8)**:
- Upbit REST API가 봉 확정 후에도 ~1분간 미확정 데이터 반환

**해결**:
1. `docs/analysis/close-price-analysis.md` 참조
2. `fetch_confirmed_candle` 함수 사용 (Progressive Retry)
3. 봉 일관성 검증 (open[n] ≈ close[n-1])

### 더 많은 교훈

**`.claude/context/project-rules.md`에서 Issue #1~#11 확인**:
- Issue #1: pyupbit 컬럼명 대소문자
- Issue #2: bar_time 9시간 오프셋
- Issue #7: Trailing Stop Peak-based → Profit-based
- Issue #10: Enum 속성 접근 오류
- ...

---

## 📊 프로젝트 구조

```
upbit-tradebot-mvp/
├── core/                   # 핵심 엔진
│   ├── strategy_engine.py      # 전략 엔진 (메인)
│   ├── strategy_incremental.py # EMA/MACD 전략
│   ├── position_state.py       # 포지션 관리
│   ├── indicator_state.py      # 지표 상태 (증분 계산)
│   ├── rest_reconcile.py       # REST 정합성 검증
│   └── filters/                # 매수/매도 필터
│
├── engine/                 # 실행 엔진
│   └── live_loop.py            # 메인 루프 (WebSocket + REST)
│
├── services/               # 외부 서비스
│   ├── db.py                   # SQLite 감사 로그
│   └── upbit_api.py            # Upbit API 래퍼
│
├── docs/                   # 📚 문서
├── thoughts/               # 💭 설계 문서
└── claude-docs/            # 📦 역사적 아카이브
```

---

## 🔧 기술 스택

- **Language**: Python 3.9+
- **Exchange API**: pyupbit (Upbit REST/WebSocket)
- **Database**: SQLite (감사 로그)
- **Indicators**: pandas, numpy (EMA, MACD)
- **Deployment**: systemd, SSH

---

## 📝 라이선스

이 프로젝트는 개인 학습 및 연구 목적으로 제작되었습니다.

---

## 🤝 기여

**문서 개선 제안**:
- GitHub Issue 등록
- `.claude/context/project-rules.md`의 교훈 참조

**버그 리포트**:
- 로그 파일 첨부 (`mcmax33_engine_debug.log`)
- 재현 단계 상세히 기술

---

## 📞 연락처

**CTO**: [프로젝트 관리자]

**AI Assistant**: Claude Code (`.claude/README.md` 참조)

---

**최종 업데이트**: 2026-04-05
**버전**: 1.0
**문서 재구성**: 완료 (DOCS_REORGANIZATION_COMPLETED.md 참조)
