# FINAL CODE
# tests/README.md

# 트레이드봇 MVP 테스트 스위트

## 📋 개요

이 테스트 스위트는 트레이드봇 MVP의 핵심 컴포넌트들을 체계적으로 테스트하기 위해 설계되었습니다. 실제 API 키나 URL을 사용하지 않고 모든 의존성을 Mock으로 대체하여 안전하게 테스트할 수 있습니다.

## 🏗️ 테스트 구조

```
tests/
├── __init__.py                 # 테스트 패키지 초기화
├── conftest.py                 # pytest 설정 및 공통 fixture
├── test_runner.py              # 통합 테스트 실행기
├── test_strategy_v2.py         # 전략 테스트
├── test_trader_sandbox.py      # 트레이더 샌드박스 테스트
├── test_engine_loop.py         # 엔진 루프 테스트
├── mocks/                      # Mock 객체들
│   ├── __init__.py
│   ├── mock_upbit.py          # Upbit API Mock
│   └── mock_database.py       # 데이터베이스 Mock
└── fixtures/                   # 테스트 데이터 및 설정
    ├── __init__.py
    └── test_data.py           # 테스트 데이터 생성기
```

## 🎯 테스트 컴포넌트

### 1. 전략 테스트 (`test_strategy_v2.py`)

**테스트 항목:**
- ✅ MACD 계산 정확성
- ✅ 골든크로스/데드크로스 감지
- ✅ ATR(평균 진폭) 계산
- ✅ 이동평균 필터 적용
- ✅ 변동성 조정 기능
- ✅ 신호 확인 메커니즘
- ✅ 진입 지연 설정
- ✅ 최소 보유 기간
- ✅ 익절/손절 로직
- ✅ 통합 필터 시스템
- ✅ 다양한 시장 시나리오
- ✅ 엣지 케이스 처리
- ✅ 성능 메트릭 계산
- ✅ 데이터베이스 통합

### 2. 트레이더 샌드박스 테스트 (`test_trader_sandbox.py`)

**테스트 항목:**
- ✅ 초기화 및 설정
- ✅ KRW 잔고 조회
- ✅ 코인 잔고 조회
- ✅ 매수 주문 계산
- ✅ 매도 주문 계산
- ✅ 잔고 부족 처리
- ✅ 0 수량 처리
- ✅ 주문 흐름 시뮬레이션
- ✅ 다중 거래 시뮬레이션
- ✅ 주문 내역 추적
- ✅ 포지션 추적
- ✅ 리스크 퍼센트 적용
- ✅ 수수료 계산
- ✅ 에러 처리
- ✅ 동시 거래 처리
- ✅ 데이터베이스 통합
- ✅ 성능 메트릭

### 3. 엔진 루프 테스트 (`test_engine_loop.py`)

**테스트 항목:**
- ✅ 엔진 초기화
- ✅ 피드 통합
- ✅ 전략 시그널 처리
- ✅ 거래 실행
- ✅ 시장 데이터 처리
- ✅ 리스크 관리
- ✅ 성능 추적
- ✅ 에러 처리
- ✅ 동시 처리
- ✅ 데이터베이스 일관성
- ✅ 시나리오 테스트
- ✅ 통합 워크플로우
- ✅ 메모리 사용량
- ✅ 실시간 시뮬레이션

## 🧪 실행 방법

### 1. 전체 테스트 실행

```bash
# 테스트 러너 사용
python tests/test_runner.py

# 상세 출력 모드
python tests/test_runner.py --verbose

# 보고서 생성
python tests/test_runner.py --report test_report.md
```

### 2. 특정 테스트만 실행

```bash
# 전략 테스트만 실행
python tests/test_runner.py --test strategy

# 트레이더 테스트만 실행
python tests/test_runner.py --test trader

# 엔진 테스트만 실행
python tests/test_runner.py --test engine
```

### 3. unittest 직접 실행

```bash
# 전략 테스트
python -m unittest tests.test_strategy_v2 -v

# 트레이더 테스트
python -m unittest tests.test_trader_sandbox -v

# 엔진 테스트
python -m unittest tests.test_engine_loop -v
```

### 4. pytest 사용 (설치된 경우)

```bash
# pytest 설치
pip install pytest pytest-cov

# 전체 테스트 실행
pytest tests/ -v

# 커버리지 보고서
pytest tests/ --cov=tests --cov-report=html

# 특정 마커로 테스트
pytest tests/ -v -m unit      # 단위 테스트만
pytest tests/ -v -m integration # 통합 테스트만
```

## 📊 테스트 데이터

### 생성 가능한 시나리오:
- **sideways**: 횡보장 시뮬레이션
- **uptrend**: 상승장 시뮬레이션
- **downtrend**: 하락장 시뮬레이션
- **golden_cross**: 골든크로스 발생 시나리오
- **dead_cross**: 데드크로스 발생 시나리오
- **volatility_spike**: 변동성 급증 시나리오
- **whipsaw**: 휩소우(급변동) 시나리오

### Mock 데이터:
- **Upbit API Mock**: 실제 API 호출 없이 가상의 가격, 잔고, 주문 데이터 제공
- **Database Mock**: SQLite 없이 메모리 내에서 데이터베이스 작업 시뮬레이션

## 🔧 설정 및 환경

### 테스트 설정 파일:
- `tests/conftest.py`: pytest 설정 및 공통 fixture
- `tests/fixtures/test_data.py`: 테스트 데이터 생성기
- `tests/mocks/`: Mock 객체 구현

### 환경 변수:
```bash
# 테스트 모드 설정
export TEST_MODE=True

# 로깅 레벨 설정
export LOG_LEVEL=DEBUG

# 테스트 데이터 경로
export TEST_DATA_PATH=./tests/data/
```

## 📈 테스트 결과 예시

```
🧪 트레이드봇 MVP 테스트 스위트 실행
============================================================

📋 전략 테스트 실행 중...
✅ 전략 테스트 완료: 15개 테스트, 0개 실패, 0개 에러

📋 트레이더 샌드박스 테스트 실행 중...
✅ 트레이더 샌드박스 테스트 완료: 20개 테스트, 0개 실패, 0개 에러

📋 엔진 루프 테스트 실행 중...
✅ 엔진 루프 테스트 완료: 18개 테스트, 0개 실패, 0개 에러

============================================================
📊 테스트 실행 결과 요약
============================================================
⏱️  총 실행 시간: 12.34초
🧪 총 테스트 수: 53
✅ 성공: 53
❌ 실패: 0
🚨 에러: 0

📈 성공률: 100.0%

🎉 모든 테스트가 성공적으로 통과했습니다!
```

## 🐛 디버깅 팁

### 1. 개별 테스트 디버깅
```python
# 특정 테스트 메서드만 실행
python -m unittest tests.test_strategy_v2.TestStrategyV2.test_macd_calculation -v
```

### 2. Mock 상태 확인
```python
# 테스트 중 Mock 상태 출력
print(f"Mock DB 상태: {mock_db.accounts}")
print(f"Mock Upbit 상태: {mock_upbit.mock_balances}")
```

### 3. 성능 문제 분석
```bash
# 성능 테스트 마커로 실행
pytest tests/ -v -m performance
```

## 🔄 CI/CD 통합

### GitHub Actions 예시:
```yaml
name: TradeBot Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v2
    - name: Set up Python
      uses: actions/setup-python@v2
      with:
        python-version: 3.9
    - name: Install dependencies
      run: |
        pip install -r requirements.txt
        pip install pytest pytest-cov
    - name: Run tests
      run: |
        python tests/test_runner.py --report test_report.md
    - name: Upload coverage
      uses: codecov/codecov-action@v1
```

## 📝 커스터마이징

### 새로운 테스트 시나리오 추가:
```python
# tests/fixtures/test_data.py에 추가
def generate_custom_scenario():
    # 커스텀 시나리오 데이터 생성 로직
    pass
```

### 새로운 Mock 객체 추가:
```python
# tests/mocks/에 새로운 Mock 클래스 추가
class MockCustomAPI:
    def __init__(self):
        # Mock 초기화
        pass
```

## 🚨 주의사항

1. **실제 키 사용 금지**: 모든 테스트는 Mock 객체를 사용하며, 실제 API 키나 URL을 사용하지 않습니다.
2. **테스트 격리**: 각 테스트는 독립적으로 실행되어야 하며, 다른 테스트에 영향을 주지 않아야 합니다.
3. **리소스 정리**: 테스트 후에는 반드시 Mock 상태를 초기화하여 다음 테스트에 영향을 주지 않도록 합니다.
4. **성능 고려**: 너무 많은 데이터나 긴 실행 시간은 CI/CD 파이프라인에 부담을 줄 수 있습니다.

## 📞 지원

테스트 실행 중 문제가 발생하면 다음을 확인하세요:
1. Python 버전 (3.7+ 권장)
2. 필요한 패키지 설치 여부
3. 테스트 데이터 파일 존재 여부
4. Mock 객체 초기화 상태

---

이 테스트 스위트는 트레이드봇 MVP의 안정성과 신뢰성을 보장하기 위해 설계되었습니다.