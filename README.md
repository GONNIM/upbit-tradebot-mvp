# Upbit TradeBot MVP

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.46.0-red.svg)](https://streamlit.io/)
[![License](https://img.shields.io/badge/License-Private-lightgrey.svg)]()

업비트(Upbit) 거래소 자동 암호화폐 트레이딩 봇. MACD 기반 전략 + Streamlit 웹 대시보드.

---

## 개요

| 항목 | 내용 |
|------|------|
| **거래소** | Upbit |
| **전략** | MACD Golden Cross |
| **기본 TP/SL** | 3% / 1% |
| **실행 주기** | 5초 |
| **운영 모드** | TEST (가상) / LIVE (실거래) |

### 주요 기능

- **자동 트레이딩**: MACD 골든크로스 기반 매수/매도 자동 실행
- **웹 대시보드**: 실시간 포지션, 수익률, 차트 모니터링
- **멀티유저**: 사용자별 독립 DB 및 엔진 인스턴스
- **감사 로그**: 모든 매매 신호 및 주문 내역 기록

---

## 프로젝트 구조

```
upbit-tradebot-mvp/
├── app.py                    # 메인 엔트리포인트 (Streamlit)
├── config.py                 # 전역 설정
├── requirements.txt          # 의존성 (76개 패키지)
├── credentials.yaml          # 사용자 인증 정보
├── .env                      # API 키 (Git 제외)
│
├── core/                     # 핵심 트레이딩 로직
│   ├── data_feed.py         # Upbit OHLCV 데이터 수집
│   ├── strategy_v2.py       # MACD 전략 (backtesting.py 호환)
│   └── trader.py            # 주문 실행 엔진
│
├── engine/                   # 실시간 트레이딩 루프
│   ├── engine_manager.py    # 멀티유저 엔진 관리
│   ├── live_loop.py         # 5초 주기 트레이딩 루프
│   └── params.py            # 파라미터 관리 (Pydantic)
│
├── services/                 # 서비스 레이어
│   ├── db.py                # SQLite 데이터베이스
│   ├── upbit_api.py         # Upbit API 래퍼
│   └── health_monitor.py    # 헬스 체크
│
├── pages/                    # Streamlit 페이지
│   ├── dashboard.py         # 트레이딩 대시보드
│   ├── set_config.py        # 파라미터 설정
│   └── audit_viewer.py      # 감사 로그 뷰어
│
└── ui/                       # UI 컴포넌트
    ├── charts.py            # 차트 렌더링
    └── sidebar.py           # 네비게이션
```

---

## Quick Start

### 1. 저장소 클론 및 가상환경 설정

```bash
git clone <repository-url>
cd upbit-tradebot-mvp

# 가상환경 생성
python -m venv venv
source venv/bin/activate    # macOS/Linux
# venv\Scripts\activate     # Windows

# 의존성 설치
pip install -r requirements.txt
```

### 2. 환경 변수 설정

```bash
# .env 파일 생성
cat > .env << EOF
UPBIT_ACCESS=your_upbit_access_key
UPBIT_SECRET=your_upbit_secret_key
OPENAI_API_KEY=sk-...  # 선택사항
EOF
```

### 3. 사용자 인증 정보 생성

```bash
python utils/make_credentials.py
```

### 4. 앱 실행

```bash
streamlit run app.py
# 브라우저: http://localhost:8501
```

---

## 환경 변수

### 필수 (`.env`)

| 변수 | 설명 | 예시 |
|------|------|------|
| `UPBIT_ACCESS` | Upbit API Access Key | `axlWUcK2Ei...` |
| `UPBIT_SECRET` | Upbit API Secret Key | `rBCS8kuaoV...` |

### 선택

| 변수 | 설명 | 예시 |
|------|------|------|
| `OPENAI_API_KEY` | OpenAI API Key (AI 기능) | `sk-...` |

### Upbit API 키 발급

1. [업비트](https://upbit.com/) 로그인
2. 마이페이지 → Open API 관리
3. 권한: **자산 조회 + 주문 조회 + 주문하기**
4. IP 주소 등록 (LIVE 모드 필수)

---

## 로컬 실행 방법

### 개발 모드

```bash
streamlit run app.py
```

1. `credentials.yaml` 계정으로 로그인
2. **TEST 모드** 선택 (가상 계좌로 안전하게 테스트)
3. 운용 자본 설정 (예: 1,000,000원)
4. 대시보드에서 **Start Engine** 클릭

### 프로덕션 (24/7 실행)

```bash
# tmux 사용
tmux new -s tradebot
streamlit run app.py
# 세션 종료: Ctrl+B → D
# 재접속: tmux attach -t tradebot
```

### Docker 실행

```bash
# 이미지 빌드
docker build -t upbit-tradebot .

# 컨테이너 실행
docker run -d -p 8501:8501 --env-file .env upbit-tradebot
```

---

## 트레이딩 전략

### MACD 설정

| 파라미터 | 기본값 |
|----------|--------|
| Fast EMA | 12 |
| Slow EMA | 26 |
| Signal | 9 |
| Take Profit | 3% |
| Stop Loss | 1% |
| Min Holding | 5 bars |

### 매수 조건

- **Golden Cross**: MACD > Signal (상향 돌파)
- 선택적 필터: MACD > 0, Signal > 0, 양봉, MA20/MA60 위치

### 매도 조건

- **Take Profit**: 수익률 ≥ 3%
- **Stop Loss**: 손실률 ≤ -1%
- **MACD Exit**: MACD < 0 전환 (설정 시)
- **Trailing Stop**: 최고가 대비 하락 (설정 시)

---

## 데이터베이스

사용자별 독립 SQLite: `services/data/tradebot_{username}.db`

| 테이블 | 용도 |
|--------|------|
| `users` | 사용자 프로필 |
| `account` | 계좌 잔고 |
| `coin_position` | 현재 보유 코인 |
| `orders` | 주문 내역 |
| `buy_eval` | 매수 신호 로그 |
| `sell_eval` | 매도 신호 로그 |
| `trade_audit` | 거래 감사 로그 |

---

## 면책 조항

**이 소프트웨어는 교육 및 연구 목적으로 제공됩니다.**

- 암호화폐 거래는 높은 리스크를 수반합니다.
- 실제 거래 전 충분한 테스트를 수행하세요.
- 투자 결정은 본인의 책임입니다.

---

**Version**: 1.0.0 | **Last Updated**: 2025-11-22
