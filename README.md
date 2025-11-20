# Upbit TradeBot MVP

[![Python](https://img.shields.io/badge/Python-3.x-blue.svg)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.46.0-red.svg)](https://streamlit.io/)
[![License](https://img.shields.io/badge/License-Private-lightgrey.svg)]()

업비트(Upbit) 거래소를 위한 자동 암호화폐 트레이딩 봇입니다. MACD 기반 전략을 사용하며, Streamlit 웹 인터페이스를 통해 실시간 모니터링 및 제어가 가능합니다.

## 목차
- [주요 기능](#주요-기능)
- [프로젝트 구조](#프로젝트-구조)
- [기술 스택](#기술-스택)
- [Quick Start](#quick-start)
- [환경 변수 설정](#환경-변수-설정)
- [로컬 실행 방법](#로컬-실행-방법)
- [사용 방법](#사용-방법)
- [트레이딩 전략](#트레이딩-전략)
- [데이터베이스 구조](#데이터베이스-구조)
- [보안 고려사항](#보안-고려사항)
- [알려진 이슈](#알려진-이슈)
- [라이선스](#라이선스)

---

## 주요 기능

### 자동 트레이딩
- **MACD 기반 전략**: MACD 골든 크로스를 활용한 진입 신호
- **리스크 관리**: 익절(TP) 3%, 손절(SL) 1% 자동 실행
- **멀티 인디케이터**: MACD, 이동평균선(MA20/MA60), 변동성 지표 결합
- **실시간 트레이딩**: 5초 간격으로 시장 데이터 분석 및 주문 실행

### 운영 모드
- **TEST 모드**: 가상 계좌로 전략 검증 (실제 주문 없음)
- **LIVE 모드**: 실제 업비트 API를 통한 실거래

### 웹 대시보드
- **실시간 모니터링**: 포지션, 수익률, 거래 내역 실시간 표시
- **차트 시각화**: Bokeh/Matplotlib 기반 OHLCV 및 지표 차트
- **감사 로그**: 모든 매매 신호 및 주문 내역 기록
- **파라미터 설정**: 웹 UI에서 전략 파라미터 실시간 조정

### 멀티유저 지원
- 사용자별 독립적인 데이터베이스
- 사용자별 트레이딩 엔진 인스턴스
- 세션 기반 인증 시스템

---

## 프로젝트 구조

```
upbit-tradebot-mvp/
├── app.py                          # 메인 엔트리포인트 (Streamlit 앱)
├── config.py                       # 전역 설정 및 환경변수
├── requirements.txt                # Python 패키지 의존성
├── credentials.yaml                # 사용자 인증 정보 (로컬 개발용)
├── .env                            # 환경 변수 (API 키 등, Git 제외)
│
├── core/                           # 핵심 트레이딩 로직
│   ├── data_feed.py               # 업비트 API 데이터 수집
│   ├── strategy_v2.py             # MACD 트레이딩 전략
│   └── trader.py                  # 주문 실행 엔진
│
├── engine/                         # 실시간 트레이딩 루프
│   ├── engine_manager.py          # 멀티유저 엔진 관리
│   ├── live_loop.py               # 실시간 트레이딩 루프 (5초 주기)
│   ├── params.py                  # 파라미터 관리
│   ├── lock_manager.py            # 스레드 동기화
│   ├── global_state.py            # 공유 상태 관리
│   └── order_reconciler.py        # 주문 상태 조정
│
├── services/                       # 서비스 레이어
│   ├── db.py                      # SQLite 데이터베이스 작업
│   ├── init_db.py                 # 데이터베이스 스키마 초기화
│   ├── upbit_api.py               # 업비트 API 래퍼
│   ├── health_monitor.py          # 백그라운드 헬스 체크
│   ├── trading_control.py         # 강제 청산/진입 명령
│   └── logger.py                  # 로깅 유틸리티
│
├── pages/                          # Streamlit 페이지
│   ├── dashboard.py               # 트레이딩 대시보드
│   ├── set_config.py              # 파라미터 설정 페이지
│   ├── set_buy_sell_conditions.py # 매매 조건 설정
│   ├── audit_viewer.py            # 감사 로그 뷰어
│   └── confirm_init_db.py         # DB 초기화 확인 페이지
│
├── ui/                             # UI 컴포넌트
│   ├── style.py                   # CSS 스타일링
│   ├── charts.py                  # 차트 렌더링
│   ├── sidebar.py                 # 사이드바 네비게이션
│   ├── metrics.py                 # 메트릭 카드
│   └── render_table.py            # 테이블 렌더링
│
└── utils/                          # 유틸리티
    ├── smoke_test.py              # DB 스모크 테스트
    ├── logging_util.py            # 로그 파일 관리
    ├── test_logic.py              # TEST 모드 로직
    └── make_credentials.py        # 인증 정보 생성
```

---

## 기술 스택

### 핵심 기술
| 기술 | 버전 | 용도 |
|------|------|------|
| **Python** | 3.x | 메인 개발 언어 |
| **Streamlit** | 1.46.0 | 웹 UI 프레임워크 |
| **pyupbit** | 0.2.34 | 업비트 거래소 API |
| **SQLite** | (내장) | 사용자 데이터 및 거래 로그 저장 |
| **pandas** | 2.3.0 | OHLCV 데이터 처리 |
| **numpy** | 2.3.1 | 수치 연산 |

### 주요 라이브러리
- **데이터 분석**: pandas, numpy
- **시각화**: matplotlib (3.10.7), bokeh (3.7.3)
- **백테스팅**: backtesting.py (0.6.4)
- **인증**: streamlit-authenticator (0.4.2), bcrypt (4.3.0)
- **보안**: cryptography (45.0.4), PyJWT (2.10.1)
- **유틸리티**: python-dotenv (1.1.0), PyYAML (6.0.2), tenacity (9.1.2)

---

## Quick Start

### 1. 저장소 클론
```bash
git clone <repository-url>
cd upbit-tradebot-mvp
```

### 2. Python 가상환경 생성 및 활성화
```bash
# macOS/Linux
python -m venv venv
source venv/bin/activate

# Windows
python -m venv venv
venv\Scripts\activate
```

### 3. 의존성 설치
```bash
pip install -r requirements.txt
```

### 4. 환경 변수 설정
`.env` 파일을 프로젝트 루트에 생성하고 다음 내용을 입력합니다:

```bash
UPBIT_ACCESS=your_upbit_access_key_here
UPBIT_SECRET=your_upbit_secret_key_here
OPENAI_API_KEY=your_openai_api_key_here  # (선택사항)
```

**업비트 API 키 발급 방법:**
1. [업비트](https://upbit.com/) 로그인
2. 마이페이지 → Open API 관리
3. API 키 발급 (자산 조회, 주문 조회, 주문하기 권한 필요)
4. IP 주소 등록 (LIVE 모드 사용 시 필수)

### 5. 사용자 인증 정보 생성
```bash
python utils/make_credentials.py
```

이 스크립트는 `credentials.yaml` 파일을 생성하며, 사용자 이름과 비밀번호를 설정할 수 있습니다.

### 6. 앱 실행
```bash
streamlit run app.py
```

브라우저에서 자동으로 `http://localhost:8501`이 열립니다.

---

## 환경 변수 설정

### 필수 환경 변수

#### `.env` 파일 (로컬 개발용)
```bash
# 업비트 API 키 (필수)
UPBIT_ACCESS=your_upbit_access_key
UPBIT_SECRET=your_upbit_secret_key

# OpenAI API 키 (선택사항 - AI 기능 사용 시)
OPENAI_API_KEY=sk-...
```

#### `credentials.yaml` (사용자 인증)
```yaml
cookie:
  expiry_days: 30
  key: some_random_signature_key_12345
  name: authentication

credentials:
  usernames:
    your_username:
      email: your_email@example.com
      name: Your Display Name
      password: $2b$12$...  # bcrypt 해시된 비밀번호
```

**비밀번호 해시 생성:**
```python
import bcrypt
password = "your_password"
hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
print(hashed)
```

### Streamlit Cloud 배포용 설정

Streamlit Cloud에 배포 시 `.streamlit/secrets.toml` 파일 생성:

```toml
UPBIT_ACCESS = "your_upbit_access_key"
UPBIT_SECRET = "your_upbit_secret_key"
OPENAI_API_KEY = "sk-..."
```

---

## 로컬 실행 방법

### 개발 모드 (TEST 모드 권장)

1. **앱 시작**
   ```bash
   streamlit run app.py
   ```

2. **로그인**
   - `credentials.yaml`에 등록된 사용자명/비밀번호 입력

3. **모드 선택**
   - **TEST 모드**: 가상 계좌로 안전하게 전략 테스트
   - **LIVE 모드**: 실제 거래 (API 키 검증 필요)

4. **운용 자본 설정**
   - 처음 실행 시 운용할 KRW 금액 입력 (예: 1,000,000원)

5. **대시보드 확인**
   - 실시간 포지션, 수익률, 거래 내역 모니터링
   - 차트에서 MACD, 이동평균선 등 지표 확인

### 프로덕션 모드 (24/7 실행)

#### 로컬 서버에서 백그라운드 실행
```bash
# tmux 또는 screen 사용
tmux new -s tradebot
streamlit run app.py

# 세션 종료 (detach): Ctrl+B → D
# 세션 재접속: tmux attach -t tradebot
```

#### Docker를 사용한 실행 (선택사항)
```bash
# Dockerfile 생성 (예시)
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8501
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]

# 이미지 빌드 및 실행
docker build -t upbit-tradebot .
docker run -d -p 8501:8501 --env-file .env upbit-tradebot
```

#### Streamlit Cloud 배포
1. GitHub 저장소에 코드 푸시
2. [Streamlit Cloud](https://streamlit.io/cloud) 로그인
3. "New app" → 저장소 선택
4. Settings → Secrets에 환경 변수 입력
5. Deploy 클릭

---

## 사용 방법

### 1. 대시보드 (Dashboard)

대시보드에서는 다음을 확인할 수 있습니다:

- **현재 포지션**: 보유 중인 코인 및 평균 매수가
- **계좌 잔고**: KRW 잔액 및 총 평가액
- **수익률**: 실현 손익 및 누적 수익률
- **최근 거래 내역**: 체결된 주문 리스트
- **차트**: OHLCV 캔들 + MACD 지표
- **신호 히스토리**: 매수/매도 신호 발생 이력

**엔진 제어:**
- **Start Engine**: 트레이딩 봇 시작
- **Stop Engine**: 트레이딩 봇 중지
- **Restart Engine**: 엔진 재시작

### 2. 파라미터 설정 (Set Config)

전략 파라미터를 조정할 수 있습니다:

| 파라미터 | 기본값 | 설명 |
|----------|--------|------|
| **Take Profit (TP)** | 3% | 익절 목표 수익률 |
| **Stop Loss (SL)** | 1% | 손절 기준 손실률 |
| **Trailing Stop** | 10% | 트레일링 스톱 비율 (선택사항) |
| **Min Holding Period** | 5 bars | 최소 보유 기간 (캔들 수) |
| **MACD Exit Enabled** | True | MACD 음전환 시 매도 여부 |

설정 변경 후 **Save Parameters** 클릭 시 JSON 파일로 저장됩니다.

### 3. 매매 조건 설정 (Buy/Sell Conditions)

#### 매수 조건 (Buy Conditions)
- **Golden Cross**: MACD 선이 시그널 선을 상향 돌파
- **MACD Positive**: MACD > 0
- **Signal Positive**: Signal > 0
- **Bullish Candle**: 양봉 패턴
- **MACD Trending Up**: MACD 상승 추세
- **Above MA20/MA60**: 가격이 이동평균선 위에 위치

#### 매도 조건 (Sell Conditions)
- **Take Profit**: 목표 수익률 도달
- **Stop Loss**: 손절선 도달
- **Trailing Stop**: 트레일링 스톱 발동
- **MACD Exit**: MACD < 0 전환

### 4. 감사 로그 (Audit Viewer)

모든 매매 신호 및 주문 실행 내역을 확인할 수 있습니다:

- **Buy Evaluation Log**: 매수 신호 평가 내역
- **Sell Evaluation Log**: 매도 신호 평가 내역
- **Trade Audit Log**: 체결된 거래 상세 내역 (진입가, 청산가, 수익률)

---

## 트레이딩 전략

### MACD 기반 전략 개요

이 봇은 **MACD (Moving Average Convergence Divergence)** 지표를 활용합니다.

#### MACD 계산
```python
MACD Line = EMA(12) - EMA(26)
Signal Line = EMA(MACD, 9)
Histogram = MACD Line - Signal Line
```

### 매수 신호 (Entry)
기본 조건: **골든 크로스 (Golden Cross)**
- `MACD Line > Signal Line` 이고
- 이전 캔들에서는 `MACD Line ≤ Signal Line` (상향 돌파)

추가 필터 (선택사항):
- MACD > 0
- Signal > 0
- 양봉 (Close > Open)
- MACD 상승 추세
- 가격이 MA20/MA60 위에 위치

### 매도 신호 (Exit)
다음 조건 중 하나라도 충족 시 매도:

1. **익절 (Take Profit)**: 수익률 ≥ 3%
2. **손절 (Stop Loss)**: 손실률 ≤ -1%
3. **MACD 음전환**: MACD < 0 (설정 시)
4. **트레일링 스톱**: 최고가 대비 10% 하락 (설정 시)

### 리스크 관리
- **손익비 (Risk:Reward)**: 1:3 (SL 1%, TP 3%)
- **최소 보유 기간**: 5 캔들 (급격한 진입/청산 방지)
- **포지션 사이즈**: 전체 운용 자금의 95% (수수료 고려)

### 트레이딩 루프 흐름도
```
[5초마다 반복]
    ↓
1. Upbit API에서 최신 OHLCV 데이터 가져오기
    ↓
2. MACD, Signal, Histogram 계산
    ↓
3. 매수/매도 조건 확인
    ↓
4. 조건 충족 시 주문 실행 (Trader)
    ↓
5. 데이터베이스에 거래 기록
    ↓
6. 대시보드 업데이트
```

---

## 데이터베이스 구조

각 사용자는 독립적인 SQLite 데이터베이스를 가집니다:
- **경로**: `services/data/tradebot_<username>.db`

### 주요 테이블

| 테이블 | 용도 |
|--------|------|
| **users** | 사용자 프로필 (username, display_name, virtual_krw) |
| **account** | 계좌 잔고 (krw_balance, updated_at) |
| **coin_position** | 현재 보유 코인 (coin_symbol, quantity, avg_price) |
| **orders** | 주문 내역 (side, ticker, price, volume, status) |
| **account_history** | 계좌 잔고 스냅샷 (timestamp, krw_amount) |
| **position_history** | 포지션 변경 이력 (coin, qty, price, timestamp) |
| **buy_eval** | 매수 신호 평가 로그 (signal, reason, timestamp, bar_index) |
| **sell_eval** | 매도 신호 평가 로그 (signal, reason, timestamp, exit_type) |
| **trade_audit** | 거래 감사 로그 (trade_id, entry_price, exit_price, profit) |

### 데이터베이스 초기화
```bash
# DB 초기화 (주의: 모든 데이터 삭제됨)
streamlit run pages/confirm_init_db.py
```

---

## 보안 고려사항

### 현재 보안 조치
- 비밀번호 bcrypt 해싱
- API 키 환경 변수 관리
- 사용자별 데이터 격리
- SQLite PRAGMA foreign_keys 활성화

### 주의 사항
1. **API 키 보호**: `.env` 파일을 Git에 커밋하지 마세요 (`.gitignore`에 포함됨)
2. **IP 화이트리스트**: 업비트 API 설정에서 서버 IP 등록 필수 (LIVE 모드)
3. **권한 제한**: API 키에 필요한 최소 권한만 부여 (자산 조회, 주문 조회, 주문하기)
4. **HTTPS 사용**: 프로덕션 배포 시 HTTPS 강제 적용
5. **로그 관리**: 민감한 정보가 로그에 남지 않도록 주의

### 권장 사항
- API 키 주기적 교체
- 시크릿 관리 도구 사용 (AWS Secrets Manager, HashiCorp Vault 등)
- 2단계 인증(2FA) 활성화
- 운용 자금 제한 (전체 자산의 일부만 트레이딩에 사용)

---

## 알려진 이슈

### Critical (우선순위 높음)
1. **부동소수점 정밀도 오류**: 잔고 계산 시 정밀도 문제로 주문 실패 가능
2. **API 실패 시 무한 루프**: 네트워크 오류 시 재시도 로직 미비
3. **환경 변수 검증 부족**: 잘못된 API 키로 시작 시 예외 처리 미흡

### High (개선 필요)
1. **Race Condition**: 잔고 확인과 주문 실행 사이 타이밍 이슈
2. **엔진 상태 불일치**: 예외 발생 시 엔진 상태 복구 실패
3. **메모리 누수**: DataFrame 누적으로 장기 실행 시 메모리 증가
4. **DB 연결 풀링 없음**: 동시 접근 시 성능 저하

### Medium (기능 개선)
1. **매수 조건 과다**: 6개 조건 충족 시 거래 기회 제한적 (월 2-3회)
2. **손익비 최적화 필요**: 1:3 비율 유지 시 75% 승률 필요 (비현실적)
3. **백테스팅 부족**: 전략 검증을 위한 체계적인 백테스트 미비
4. **레거시 코드 정리 필요**: `*_old.py` 파일들 정리 필요

자세한 내용은 다음 문서를 참고하세요:
- [DEBUG_ANALYSIS_REPORT.md](./DEBUG_ANALYSIS_REPORT.md)
- [STRATEGY_OPTIMIZATION_REPORT.md](./STRATEGY_OPTIMIZATION_REPORT.md)

---

## 향후 개선 계획

### 단기 (1-2주)
- [ ] 부동소수점 오류 수정 (Decimal 타입 사용)
- [ ] API 실패 시 재시도 로직 강화
- [ ] 환경 변수 검증 로직 추가
- [ ] 단위 테스트 추가

### 중기 (1-2개월)
- [ ] 연결 풀링 구현 (SQLAlchemy)
- [ ] 메모리 관리 개선 (DataFrame 크기 제한)
- [ ] 전략 파라미터 최적화 (TP 5%, SL 1.5%)
- [ ] 매수 조건 단순화 (3-4개로 축소)
- [ ] 모니터링 및 알림 시스템 추가 (텔레그램 봇)

### 장기 (3개월 이상)
- [ ] 멀티 코인 지원 (BTC, ETH, SOL 등)
- [ ] 멀티 전략 지원 (RSI, Bollinger Bands 등)
- [ ] AI 기반 신호 강화 (OpenAI API 활용)
- [ ] 포트폴리오 리밸런싱 기능
- [ ] REST API 제공 (외부 시스템 연동)

---

## 기여 가이드

이 프로젝트는 현재 프라이빗 저장소입니다. 기여를 원하시면 관리자에게 문의하세요.

---

## 문의 및 지원

- **이슈 리포트**: GitHub Issues
- **이메일**: [관리자 이메일]
- **문서**: `docs/` 디렉토리 (작성 중)

---

## 라이선스

이 프로젝트는 프라이빗 라이선스로 보호됩니다. 무단 배포 및 상업적 사용을 금합니다.

---

## 면책 조항

**이 소프트웨어는 교육 및 연구 목적으로 제공됩니다.**

- 암호화폐 거래는 높은 리스크를 수반합니다.
- 이 봇을 사용하여 발생하는 모든 손실에 대해 개발자는 책임지지 않습니다.
- 실제 거래 전 충분한 테스트를 수행하세요.
- 투자 결정은 본인의 책임 하에 이루어져야 합니다.
- 업비트 API 이용 약관을 준수하세요.

---

**Version**: 1.0.0
**Last Updated**: 2025-11-20
**Author**: Upbit TradeBot Team
