# PLAN_tradebot_v2.md — 업비트 트레이드봇 MVP 개선 및 안정화 계획

## 1. 문제 정의

### 1.1 현재 상태
- Streamlit 기반 트레이드봇 MVP 개발 완료
- MACD 기반 자동매매 전략 구현
- 다중 사용자 지원 (SQLite 분리)
- 테스트/실거래 모드 지원

### 1.2 주요 문제점

#### 🔴 치명적 문제 (Priority 1)
1. **보안 취약점**
   - `credentials.yaml`에 평문 저장된 해시 비밀번호 노출
   - 환경변수 미설정 시 서비스 크래시 (`config.py:21`)

2. **코드 품질 이슈**
   - 부동소수점 연산 정밀도 문제 (`trader.py:78-80`)
   - 무한 재시도 가능성 (`data_feed.py:92-100`)
   - 레이스 컨디션 위험 (`live_loop.py:116-135`)

3. **수익성 저하**
   - 비효율적인 Risk/Reward 비율 (1:3)
   - 과도한 매수 조건으로 거래 기회 제한
   - 최소 보유기간 부족 (5봉)

#### 🟡 중요 문제 (Priority 2)
1. **성능 및 리소스**
   - 메모리 누수 가능성 (`data_feed.py:110`)
   - DB 연결 풀링 없음
   - 로그 파일 자동 정리 미흡

2. **아키텍처 개선**
   - 엔진 상태 불일치 (`engine_manager.py:147-152`)
   - 구조화된 예외 처리 부재
   - 모니터링 및 알림 시스템 부재

## 2. 요구사항

### 2.1 기능 요구사항
- [ ] **안정적인 매매 실행**
  - 예외 처리 및 자동 복구 메커니즘
  - 레이스 컨디션 방지
  - 무한 루프 방지

- [ ] **수익성 최적화**
  - 개선된 Risk/Reward 비율 (1:3.33)
  - 적응형 매수 조건
  - 동적 손익 관리

- [ ] **보안 강화**
  - API 키/시크릿 안전한 관리
  - 접근 로그 및 감사 추적
  - 환경변수 검증 로직

### 2.2 비기능 요구사항
- [ ] **안정성**: 99.9% 가동률
- [ ] **성능**: 100ms 미만 응답 시간
- [ ] **보안**: OWASP Top 10 준수
- [ ] **모니터링**: 실시간 상태 모니터링
- [ ] **테스트**: 80% 이상 코드 커버리지

## 3. 설계

### 3.1 아키텍처 개선

#### 3.1.1 엔진 아키텍처
```
📁 engine/
├── engine_manager.py      # 엔진 관리 (개선)
├── live_loop.py           # 실시간 루프 (개선)
├── params.py              # 파라미터 관리
├── health_monitor.py      # 신규: 헬스 모니터
├── recovery_manager.py    # 신규: 복구 관리
└── circuit_breaker.py     # 신규: 서킷 브레이커
```

#### 3.1.2 전략 아키텍처
```
📁 strategies/
├── base_strategy.py       # 신규: 기본 전략 클래스
├── macd_strategy.py       # 기존: MACD 전략 (개선)
├── risk_manager.py        # 신규: 리스크 관리
├── position_sizer.py      # 신규: 포지션 사이징
└── backtest_engine.py     # 신규: 백테스팅 엔진
```

#### 3.1.3 트레이더 아키텍처
```
📁 core/
├── trader.py              # 트레이더 (개선)
├── data_feed.py           # 데이터 피드 (개선)
├── order_manager.py       # 신규: 주문 관리
├── balance_manager.py     # 신규: 잔고 관리
└── fee_calculator.py      # 신규: 수수료 계산
```

#### 3.1.4 DB 아키텍처
```
📁 db/
├── connection_pool.py     # 신규: 연결 풀
├── migrations/            # 신규: 마이그레이션
├── models/                # 신규: 데이터 모델
├── repositories/          # 신규: 리포지토리
└── audit_logger.py         # 신규: 감사 로그
```

### 3.2 핵심 컴포넌트 설계

#### 3.2.1 보안 관리자
```python
# services/security_manager.py
class SecurityManager:
    def __init__(self):
        self.encryption_key = self._load_or_generate_key()
        self.access_log = []
    
    def encrypt_credentials(self, credentials: dict) -> str:
        """자격 증명 암호화"""
        pass
    
    def validate_environment(self) -> bool:
        """환경변수 검증"""
        pass
    
    def log_access(self, user_id: str, action: str):
        """접근 로그 기록"""
        pass
```

#### 3.2.2 회로 차단기
```python
# engine/circuit_breaker.py
class CircuitBreaker:
    def __init__(self, failure_threshold=5, recovery_timeout=60):
        self.failure_count = 0
        self.last_failure_time = 0
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
    
    def call(self, func, *args, **kwargs):
        """회로 차단기로 함수 실행"""
        if self.state == "OPEN":
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = "HALF_OPEN"
            else:
                raise CircuitBreakerOpenError()
        
        try:
            result = func(*args, **kwargs)
            self.on_success()
            return result
        except Exception as e:
            self.on_failure()
            raise
```

#### 3.2.3 개선된 전략
```python
# strategies/macd_strategy.py
class MACDStrategyV2:
    def __init__(self, params):
        self.take_profit = 0.05      # 5% 익절
        self.stop_loss = 0.015       # 1.5% 손절
        self.min_holding_period = 10 # 10봉 최소 보유
        self.volatility_threshold = 0.02
        
    def adaptive_buy_conditions(self, market_data):
        """적응형 매수 조건"""
        volatility = self._calculate_volatility(market_data)
        required_conditions = 3 if volatility > self.volatility_threshold else 4
        
        # 골든크로스 확인
        if not self._is_golden_cross(market_data):
            return False
            
        # 변동성에 따른 조건 수 조정
        satisfied_conditions = 0
        if self._check_volume_condition(market_data):
            satisfied_conditions += 1
        if self._check_ma_trend(market_data):
            satisfied_conditions += 1
        # ... 추가 조건 확인
        
        return satisfied_conditions >= required_conditions
    
    def dynamic_exit_strategy(self, position_data):
        """동적 손익 관리"""
        profit_rate = self._calculate_profit_rate(position_data)
        bars_held = position_data['bars_held']
        
        # 최소 보유기간 확인
        if bars_held < self.min_holding_period:
            if profit_rate <= -self.stop_loss:
                return "SELL"  # 손절만 허용
        
        # 수익 구간별 차등 익절
        if profit_rate >= 0.08:
            self.trailing_stop = True
            self.trailing_stop_rate = 0.05
        
        return self._check_exit_conditions(position_data)
```

## 4. 구현 단계

### 4.1 Phase 1: 안정화 (1-2주)
- [ ] **치명적 보안 이슈 수정**
  - `config.py` 환경변수 검증 로직 강화
  - `credentials.yaml` 암호화 적용
  - 보안 관리자 구현

- [ ] **코드 품질 개선**
  - `trader.py` 부동소수점 정밀도 문제 수정
  - `data_feed.py` 무한 재시도 방지
  - `live_loop.py` 레이스 컨디션 해결

- [ ] **예외 처리 체계**
  - 커스텀 예외 클래스 정의
  - 구조화된 예외 처리 구현
  - 로깅 시스템 개선

### 4.2 Phase 2: 수익성 최적화 (2-3주)
- [ ] **전략 파라미터 최적화**
  - `gon1972_latest_params.json` 업데이트
  - Risk/Reward 비율 1:3.33로 조정
  - 최소 보유기간 10봉으로 증가

- [ ] **매수 조건 개선**
  - 적응형 매수 조건 구현
  - 변동성 기반 조건 완화
  - 골든크로스 신호 강도 계산

- [ ] **동적 손익 관리**
  - 트레일링 스톱 구현
  - 수익 구간별 차등 익절
  - 변동성 기반 손절 조정

### 4.3 Phase 3: 아키텍처 고도화 (3-4주)
- [ ] **엔진 안정성**
  - 회로 차단기 구현
  - 자동 복구 메커니즘
  - 헬스 모니터링 시스템

- [ ] **성능 최적화**
  - DB 연결 풀링 구현
  - 메모리 관리 개선
  - 캐싱 시스템 도입

- [ ] **모니터링 및 알림**
  - 실시간 모니터링 대시보드
  - 알림 시스템 (Slack/Email)
  - 성능 메트릭 수집

## 5. 테스트 전략

### 5.1 테스트 종류
- [ ] **단위 테스트** (Unit Tests)
  - 전략 로직 테스트
  - 보안 관리자 테스트
  - 수수료 계산 테스트

- [ ] **통합 테스트** (Integration Tests)
  - DB CRUD 테스트
  - API 연동 테스트
  - 엔진 라이프사이클 테스트

- [ ] **모의 테스트** (Mock Tests)
  - Upbit API 모의 테스트
  - 시장 상황 시뮬레이션
  - 장애 상황 복구 테스트

- [ ] **부하 테스트** (Load Tests)
  - 동시 사용자 테스트
  - 장기 실행 안정성 테스트
  - 메모리 누수 테스트

### 5.2 테스트 데이터
- [ ] **백테스팅 데이터**: 1년간 일봉/분봉 데이터
- [ ] **시나리오 테스트**: 급등락, 횡보, 추세 시장
- [ ] **장애 시나리오**: API 장애, 네트워크 단절, DB 장애

## 6. 리스크 관리

### 6.1 기술적 리스크
- [ ] **API 장애**: 회로 차단기 및 재시도 정책
- [ ] **DB 장애**: 자동 복구 및 데이터 일관성
- [ ] **메모리 누수**: 모니터링 및 자동 재시작
- [ ] **네트워크 문제**: 오프라인 모드 및 큐잉

### 6.2 거래 리스크
- [ ] **잔고 오차**: 실시간 잔고 동기화
- [ ] **수수료 오차**: 정확한 수수료 계산
- [ ] **시장 변동성**: 동적 손절 및 익절
- [ ] **유동성 부족**: 최소 거래량 확인

### 6.3 운영 리스크
- [ ] **잘못된 설정**: 설정 검증 및 롤백
- [ ] **데이터 손실**: 정기 백업 및 복구
- [ ] **보안 침해**: 접근 제어 및 감사 로그

## 7. 완료 기준

### 7.1 기능적 기준
- [ ] 모든 Priority 1 이슈 해결
- [ ] 수익성 150% 개선 (월 3-5% 수익률)
- [ ] 안정성 99.9% 달성
- [ ] 80% 이상 테스트 커버리지

### 7.2 성능 기준
- [ ] 응답 시간 100ms 미만
- [ ] 메모리 사용량 512MB 미만
- [ ] 동시 사용자 100명 지원
- [ ] 장애 복구 시간 5분 미만

### 7.3 보안 기준
- [ ] OWASP Top 10 준수
- [ ] API 키 암호화 완료
- [ ] 접근 로그 100% 기록
- [ ] 취약성 스캔 통과

## 8. 롤백 계획

### 8.1 롤백 트리거
- [ ] 수익률 20% 이상 하락
- [ ] 장애 발생 빈도 10% 이상 증가
- [ ] 사용자 불만 5건 이상 접수
- [ ] 보안 사고 발생

### 8.2 롤백 절차
1. 현재 버전 백업
2. 이전 버전으로 복원
3. 데이터 마이그레이션
4. 정상 동작 확인
5. 롤백 원인 분석

## 9. 일정

### 9.1 전체 일정: 8-10주
- **Phase 1**: 1-2주 (안정화)
- **Phase 2**: 2-3주 (수익성 최적화)
- **Phase 3**: 3-4주 (아키텍처 고도화)
- **테스트 및 안정화**: 2주

### 9.2 주별 마일스톤
- **Week 1**: 보안 이슈 수정, 예외 처리 구현
- **Week 2**: 전략 파라미터 최적화, 매수 조건 개선
- **Week 3**: 동적 손익 관리, 트레일링 스톱 구현
- **Week 4**: 엔진 안정성, 회로 차단기 구현
- **Week 5**: 성능 최적화, 모니터링 시스템
- **Week 6**: 테스트 수행, 버그 수정
- **Week 7**: 통합 테스트, 성능 테스트
- **Week 8**: 배포 준비, 문서화

---

**작성일**: 2025-09-06  
**작성자**: AI Agent  
**문서 버전**: v1.0  
**다음 단계**: 본 PLAN 검토 및 구현 시작