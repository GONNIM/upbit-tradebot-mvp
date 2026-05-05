# Upbit Tradebot MVP

**자동화된 암호화폐 트레이딩 봇 - EMA/MACD 전략 기반**

---

## WHY (목적)

**핵심 미션**: Upbit 거래소에서 EMA/MACD 전략 기반 자동매매 실행

### 주요 기능
- **REST Reconcile** - REST API와 로컬 데이터 정합성 보장 (미확정 종가 문제 해결)
- **증분 지표 계산** - EMA, MACD 실시간 업데이트 (전체 재계산 불필요)
- **Golden/Dead Cross 감지** - 정확한 추세 전환 포착 및 매매
- **BACKFILL** - 누락/변경 봉 자동 재평가 (지표 상태 보존)
- **다층 필터 시스템** - Take Profit, Trailing Stop, Stale Position 등

### 지원 전략
- **EMA Strategy** - 빠른 EMA(7)와 느린 EMA(25)의 크로스 기반 매매
- **MACD Strategy** - MACD 라인과 Signal 라인의 크로스 기반 매매

### 핵심 문제 해결
1. **REST API 미확정 종가** → Progressive Retry로 확정 봉 검증 (Issue #8)
2. **BACKFILL 크로스 오염** → 지표 상태 백업/복원 (Issue #11)
3. **봉 누락/변경** → REST Reconcile로 정합성 검증
4. **느린 지표 계산** → 증분 업데이트로 실시간 처리

---

## WHAT (구조)

```
upbit-tradebot-mvp/
├── core/                   # 전략 엔진 (핵심)
│   ├── strategy_engine.py      # 메인 엔진 (봉 처리, BACKFILL)
│   ├── strategy_incremental.py # EMA/MACD 전략 (증분 계산)
│   ├── position_state.py       # 포지션 관리 (매수/매도 상태)
│   ├── indicator_state.py      # 지표 상태 (EMA, MACD, prev 값)
│   ├── rest_reconcile.py       # REST 정합성 검증 (봉 비교)
│   └── filters/                # 매수/매도 필터
│       ├── buy_filters.py          # Cooldown, Position Limit
│       └── sell_filters.py         # Take Profit, Trailing Stop, Stale Position
│
├── engine/                 # 실행 엔진
│   └── live_loop.py            # 메인 루프 (WebSocket + REST)
│
├── services/               # 외부 서비스
│   ├── db.py                   # SQLite 감사 로그 (매매 기록)
│   └── upbit_api.py            # Upbit API 래퍼 (REST/WebSocket)
│
├── docs/                   # 문서
│   ├── architecture/           # 시스템 아키텍처
│   ├── operations/             # 운영 가이드
│   └── analysis/               # 분석 보고서
│
├── scripts/                # 유틸리티 스크립트
└── .claude/                # Claude Code 설정
    └── context/
        └── project-rules.md    # Issue #1~#11 교훈 ⭐
```

### 핵심 모듈

**strategy_engine.py** (core/strategy_engine.py:1-500)
- 봉 처리 메인 로직
- BACKFILL 실행 (누락/변경 봉 재평가)
- 지표 상태 백업/복원 (Issue #11)

**strategy_incremental.py** (core/strategy_incremental.py:1-300)
- EMA/MACD 증분 계산
- Golden/Dead Cross 감지
- `prev_ema_fast`, `prev_ema_slow` 추적

**rest_reconcile.py** (core/rest_reconcile.py:1-200)
- REST API와 로컬 시계열 비교
- 봉 일관성 검증 (open[n] ≈ close[n-1])
- 변경 감지 시 BACKFILL 트리거

**live_loop.py** (engine/live_loop.py:1-400)
- WebSocket 실시간 체결가 수신
- REST API 봉 데이터 수집
- 전략 엔진 호출

---

## HOW (작업 방법)

### 로컬 실행

```bash
# 1. 환경 변수 설정 (.env 파일)
UPBIT_ACCESS_KEY=your_access_key
UPBIT_SECRET_KEY=your_secret_key

# 2. 의존성 설치
pip install -r requirements.txt

# 3. 전략 파라미터 확인
cat mcmax33_latest_params_EMA.json

# 4. 봇 실행 (EMA 전략)
python -m engine.live_loop --ticker KRW-ZRO --strategy EMA
```

### 서버 배포

```bash
# systemd deploy (권장)
./squad-tradebot.sh

# systemd 상태 확인
systemctl status upbit-tradebot

# 로그 확인
tail -f mcmax33_engine_debug.log
```

### 백테스팅

```bash
# 과거 데이터로 전략 테스트
python -m tests.backtest --ticker KRW-ZRO --strategy EMA --days 30
```

### 전략 파라미터 수정

```bash
# mcmax33_latest_params_EMA.json 편집
{
  "ticker": "KRW-ZRO",
  "interval": "minute1",
  "ema_fast": 7,          # 빠른 EMA 기간
  "ema_slow": 25,         # 느린 EMA 기간
  "take_profit": 0.05,    # 5% 수익 시 매도
  "trailing_stop_threshold": 0.10  # 수익 10% 하락 시 매도
}

# 파라미터 변경 후 재시작
./squad-tradebot.sh restart
```

---

## ⚠️ CRITICAL - 작업 원칙 및 금지 사항

### 필수 준수 사항

1. **Issue #1~#11 숙지 필수**
   - 상세: @.claude/context/project-rules.md
   - 실수 사례, 근본 원인, 교훈 포함

2. **REST Reconcile 항상 활성화**
   - 미확정 종가 문제 방지 (Issue #8)
   - Progressive Retry로 확정 봉 검증

3. **BACKFILL 시 지표 상태 보존**
   - `prev_ema_fast`, `prev_ema_slow` 백업/복원 (Issue #11)
   - Golden Cross 오염 방지

### 금지 사항

```python
# ❌ 절대 금지
pyupbit.get_ohlcv(..., count=400)  # 미확정 종가 반환 (Issue #8)
# ✅ 올바른 방법
fetch_confirmed_candle(..., retries=3)  # Progressive Retry

# ❌ 절대 금지
ema_fast = ta.EMA(close, timeperiod=7)  # 전체 재계산 (느림)
# ✅ 올바른 방법
ema_fast = prev_ema + alpha * (close - prev_ema)  # 증분 업데이트

# ❌ 절대 금지
bar_time = pd.Timestamp.now()  # Timezone 미지정 (Issue #2)
# ✅ 올바른 방법
bar_time = pd.Timestamp.now(tz='Asia/Seoul')  # KST 명시
```

### 트러블슈팅 우선순위

**Golden Cross 발생했는데 매수 안 됨**:
1. Issue #11 확인 (BACKFILL 크로스 오염)
2. `thoughts/20260325-01-BACKFILL-Golden-Cross-Fix.md` 참조
3. 로그에서 "지표 상태 백업/복원" 확인

**REST API 종가 불일치**:
1. Issue #8 확인 (미확정 종가 문제)
2. `docs/analysis/close-price-analysis.md` 참조
3. `fetch_confirmed_candle` 사용 확인

### 상세 문서

**Issue 참조**:
- @.claude/context/project-rules.md - Issue #1~#11 요약 ⭐

**기타 참조 문서** (필요 시 명시적으로 Read):
- `.claude/lessons-learned.md` - 교훈 상세 (project-rules.md와 내용 중복)
- `docs/issues/issue-01.md ~ issue-11.md` - Issue별 상세 분석
- `docs/analysis/close-price-analysis.md` - 미확정 종가 분석 (WO-2026-001 완료)
- `docs/work-orders/2026-001-confirmed-candle.md` - 확정 봉 검증 (완료)
- `thoughts/20260325-01-BACKFILL-Golden-Cross-Fix.md` - BACKFILL 지표 오염 해결
- `thoughts/20260326-01-Post-Exit-Reentry-Strategy.md` - 재진입 전략 (미구현)

---

**마지막 업데이트**: 2026-04-22
**버전**: 2.0 (Anthropic Best Practices 적용)
