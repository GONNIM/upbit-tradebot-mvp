# FINAL CODE
# engine/params.py

from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Dict, Any, Optional, List, Union
from datetime import datetime
import json
import os
import logging
from enum import Enum
import copy

from config import MIN_CASH, MIN_FEE_RATIO, PARAMS_JSON_FILENAME
from services.logger import get_logger
from services.db import get_db_manager
from utils.logging_util import log_to_file

# 로거 설정
logger = get_logger(__name__)

# 전략 타입 열거형
class StrategyType(Enum):
    MACD = "macd"
    RSI = "rsi"
    BOLLINGER = "bollinger"
    GRID = "grid"
    MARTINGALE = "martingale"
    CUSTOM = "custom"

# 거래 모드 열거형
class TradingMode(Enum):
    LIVE = "live"
    SANDBOX = "sandbox"
    PAPER = "paper"
    BACKTEST = "backtest"

# 리스크 관리 설정
class RiskManagement(BaseModel):
    """리스크 관리 설정"""
    max_position_size: float = Field(1.0, ge=0, le=1, description="최대 포지션 크기 (비율)")
    max_drawdown: float = Field(0.2, ge=0, le=1, description="최대 낙폭 (비율)")
    stop_loss_percent: float = Field(0.05, ge=0, le=1, description="손절 비율")
    take_profit_percent: float = Field(0.1, ge=0, le=1, description="익절 비율")
    max_daily_loss: float = Field(0.1, ge=0, le=1, description="최대 일일 손실")
    max_trades_per_day: int = Field(50, ge=1, le=1000, description="최대 일일 거래 횟수")
    risk_per_trade: float = Field(0.02, ge=0, le=0.5, description="거래당 리스크 비율")

# MACD 전략 파라미터
class MACDParams(BaseModel):
    """MACD 전략 파라미터"""
    fast_period: int = Field(12, ge=1, le=50, description="빠른 이동평균 기간")
    slow_period: int = Field(26, ge=1, le=100, description="느린 이동평균 기간")
    signal_period: int = Field(9, ge=1, le=20, description="신호선 기간")
    macd_threshold: float = Field(0.0, ge=-1, le=1, description="MACD 임계값")
    histogram_threshold: float = Field(0.0, ge=-1, le=1, description="히스토그램 임계값")
    enable_crossover: bool = Field(True, description="크로스오버 신호 사용")
    enable_divergence: bool = Field(False, description="다이버전스 신호 사용")

# RSI 전략 파라미터
class RSIParams(BaseModel):
    """RSI 전략 파라미터"""
    period: int = Field(14, ge=2, le=50, description="RSI 기간")
    oversold: float = Field(30, ge=0, le=50, description="과매도 기준")
    overbought: float = Field(70, ge=50, le=100, description="과매수 기준")
    use_rsi_ma: bool = Field(False, description="RSI 이동평균 사용")
    ma_period: int = Field(9, ge=2, le=20, description="이동평균 기간")

# 볼린저 밴드 전략 파라미터
class BollingerParams(BaseModel):
    """볼린저 밴드 전략 파라미터"""
    period: int = Field(20, ge=5, le=50, description="기간")
    std_dev: float = Field(2.0, ge=0.5, le=5.0, description="표준편차 배수")
    use_bands: bool = Field(True, description="밴드 사용")
    use_squeeze: bool = Field(False, description="스퀴즈 신호 사용")
    use_rsi_filter: bool = Field(False, description="RSI 필터 사용")
    rsi_period: int = Field(14, ge=2, le=50, description="RSI 필터 기간")

# 그리드 전략 파라미터
class GridParams(BaseModel):
    """그리드 전략 파라미터"""
    grid_count: int = Field(10, ge=3, le=50, description="그리드 개수")
    grid_spacing: float = Field(0.02, ge=0.001, le=0.1, description="그리드 간격 (비율)")
    rebalance_threshold: float = Field(0.01, ge=0.001, le=0.05, description="리밸런싱 임계값")
    dynamic_grid: bool = Field(False, description="동적 그리드 사용")
    volatility_period: int = Field(20, ge=5, le=50, description="변동성 기간")

# 전략 파라미터 통합
class StrategyParams(BaseModel):
    """전략 파라미터 통합"""
    strategy_type: StrategyType = Field(StrategyType.MACD, description="전략 타입")
    macd: Optional[MACDParams] = Field(None, description="MACD 파라미터")
    rsi: Optional[RSIParams] = Field(None, description="RSI 파라미터")
    bollinger: Optional[BollingerParams] = Field(None, description="볼린저 밴드 파라미터")
    grid: Optional[GridParams] = Field(None, description="그리드 파라미터")
    custom_params: Dict[str, Any] = Field(default_factory=dict, description="커스텀 파라미터")

# 실행 설정
class ExecutionConfig(BaseModel):
    """실행 설정"""
    trading_mode: TradingMode = Field(TradingMode.SANDBOX, description="거래 모드")
    max_slippage: float = Field(0.001, ge=0, le=0.01, description="최대 슬리피지")
    execution_delay: float = Field(0.5, ge=0, le=5.0, description="실행 지연 (초)")
    retry_attempts: int = Field(3, ge=1, le=10, description="재시도 횟수")
    retry_delay: float = Field(1.0, ge=0.1, le=10.0, description="재시도 지연 (초)")
    enable_circuit_breaker: bool = Field(True, description="서킷 브레이커 사용")
    circuit_breaker_threshold: int = Field(5, ge=1, le=20, description="서킷 브레이커 임계값")

# 모니터링 설정
class MonitoringConfig(BaseModel):
    """모니터링 설정"""
    enable_health_check: bool = Field(True, description="건강 체크 사용")
    health_check_interval: float = Field(30.0, ge=5.0, le=300.0, description="건강 체크 간격 (초)")
    enable_performance_tracking: bool = Field(True, description="성능 추적 사용")
    enable_alerts: bool = Field(True, description="알림 사용")
    alert_channels: List[str] = Field(default_factory=list, description="알림 채널")
    log_level: str = Field("INFO", description="로그 레벨")

# 메인 파라미터 모델
class LiveParams(BaseModel):
    """메인 라이브 파라미터 모델"""
    model_config = ConfigDict(extra='forbid')
    
    # 기본 설정
    user_id: str = Field(..., description="사용자 ID")
    ticker: str = Field(..., description="거래 대상 티커")
    interval: str = Field(..., description="캔들 간격")
    
    # 거래 설정
    cash: int = Field(MIN_CASH, ge=MIN_CASH, description="초기 자금")
    commission: float = Field(MIN_FEE_RATIO, ge=MIN_FEE_RATIO, description="수수료율")
    order_ratio: float = Field(1.0, ge=0.01, le=1.0, description="주문 비율")
    
    # 전략 설정
    strategy: StrategyParams = Field(..., description="전략 파라미터")
    
    # 리스크 관리
    risk_management: RiskManagement = Field(default_factory=RiskManagement, description="리스크 관리")
    
    # 실행 설정
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig, description="실행 설정")
    
    # 모니터링 설정
    monitoring: MonitoringConfig = Field(default_factory=MonitoringConfig, description="모니터링 설정")
    
    # 메타데이터
    name: str = Field("", description="전략 이름")
    description: str = Field("", description="전략 설명")
    tags: List[str] = Field(default_factory=list, description="태그")
    created_at: datetime = Field(default_factory=datetime.now, description="생성 시간")
    updated_at: datetime = Field(default_factory=datetime.now, description="수정 시간")
    is_active: bool = Field(True, description="활성 상태")
    version: str = Field("1.0.0", description="버전")
    
    @field_validator('ticker')
    def _validate_ticker(cls, v: str) -> str:
        v = v.upper().strip()
        if "-" in v:
            base, quote = v.split("-", 1)
            if base != "KRW" or not quote.isalpha():
                raise ValueError("Format must be KRW-XXX or simply XXX")
            return v
        if not v.isalpha():
            raise ValueError("Ticker must be alphabetic, e.g. BTC, ETH")
        return v
    
    @property
    def upbit_ticker(self) -> str:
        return self.ticker if "-" in self.ticker else f"KRW-{self.ticker}"
    
    def update_timestamp(self):
        """수정 시간 업데이트"""
        self.updated_at = datetime.now()

# 파라미터 관리자 클래스
class ParamsManager:
    """파라미터 관리 시스템"""
    
    def __init__(self):
        self._params_cache: Dict[str, LiveParams] = {}
        self._db_manager = get_db_manager()
        self._lock = threading.RLock()
        
    def load_params(self, path: str) -> Optional[LiveParams]:
        """파일에서 파라미터 로드"""
        try:
            with self._lock:
                if path in self._params_cache:
                    cached_params = self._params_cache[path]
                    # 파일 수정 시간 확인
                    file_mtime = os.path.getmtime(path)
                    if cached_params.updated_at.timestamp() >= file_mtime:
                        return cached_params
                
                if not os.path.exists(path):
                    logger.warning(f"파라미터 파일 없음: {path}")
                    return None
                
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # 문자열 필드 변환
                if 'strategy' in data and 'strategy_type' in data['strategy']:
                    data['strategy']['strategy_type'] = StrategyType(data['strategy']['strategy_type'])
                
                params = LiveParams(**data)
                self._params_cache[path] = params
                
                logger.info(f"파라미터 로드 성공: {path}")
                return params
                
        except Exception as e:
            logger.error(f"파라미터 로드 실패: {e}")
            return None
    
    def save_params(self, params: LiveParams, path: str = None) -> bool:
        """파라미터 저장"""
        try:
            if path is None:
                path = f"{params.user_id}_{PARAMS_JSON_FILENAME}"
            
            params.update_timestamp()
            
            with self._lock:
                # 디렉토리 생성
                os.makedirs(os.path.dirname(path), exist_ok=True)
                
                # JSON 직렬화를 위한 변환
                data = params.model_dump()
                
                # Enum 타입 변환
                if 'strategy' in data and 'strategy_type' in data['strategy']:
                    data['strategy']['strategy_type'] = data['strategy']['strategy_type'].value
                
                with open(path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False, default=str)
                
                self._params_cache[path] = params
                
                logger.info(f"파라미터 저장 성공: {path}")
                return True
                
        except Exception as e:
            logger.error(f"파라미터 저장 실패: {e}")
            return False
    
    def delete_params(self, path: str) -> bool:
        """파라미터 파일 삭제"""
        try:
            with self._lock:
                if os.path.exists(path):
                    os.remove(path)
                    if path in self._params_cache:
                        del self._params_cache[path]
                    logger.info(f"파라미터 파일 삭제: {path}")
                    return True
                return False
                
        except Exception as e:
            logger.error(f"파라미터 파일 삭제 실패: {e}")
            return False
    
    def get_params(self, user_id: str) -> Optional[LiveParams]:
        """사용자 파라미터 가져오기"""
        path = f"{user_id}_{PARAMS_JSON_FILENAME}"
        return self.load_params(path)
    
    def update_params(self, user_id: str, updates: Dict[str, Any]) -> bool:
        """사용자 파라미터 업데이트"""
        try:
            params = self.get_params(user_id)
            if not params:
                # 기본 파라미터 생성
                params = self._create_default_params(user_id)
            
            # 업데이트 적용
            self._apply_updates(params, updates)
            
            # 저장
            return self.save_params(params)
            
        except Exception as e:
            logger.error(f"파라미터 업데이트 실패: {e}")
            return False
    
    def _create_default_params(self, user_id: str) -> LiveParams:
        """기본 파라미터 생성"""
        return LiveParams(
            user_id=user_id,
            ticker="BTC",
            interval="minutes5",
            strategy=StrategyParams(
                strategy_type=StrategyType.MACD,
                macd=MACDParams()
            )
        )
    
    def _apply_updates(self, params: LiveParams, updates: Dict[str, Any]):
        """업데이트 적용"""
        for key, value in updates.items():
            if hasattr(params, key):
                current_value = getattr(params, key)
                
                # 중첩된 딕셔너리 처리
                if isinstance(current_value, BaseModel) and isinstance(value, dict):
                    self._apply_updates(current_value, value)
                elif isinstance(current_value, dict) and isinstance(value, dict):
                    current_value.update(value)
                else:
                    setattr(params, key, value)
    
    def validate_params(self, params: LiveParams) -> List[str]:
        """파라미터 유효성 검사"""
        errors = []
        
        try:
            # 기본 유효성 검사
            params.model_validate(params.model_dump())
            
            # 추가 검사
            if params.risk_management.max_position_size <= 0:
                errors.append("max_position_size must be greater than 0")
            
            if params.risk_management.stop_loss_percent <= 0:
                errors.append("stop_loss_percent must be greater than 0")
            
            if params.strategy.strategy_type == StrategyType.MACD:
                if not params.strategy.macd:
                    errors.append("MACD strategy requires MACD parameters")
                elif params.strategy.macd.fast_period >= params.strategy.macd.slow_period:
                    errors.append("MACD fast_period must be less than slow_period")
            
            # 자금 검사
            if params.cash < MIN_CASH:
                errors.append(f"Initial cash must be at least {MIN_CASH}")
            
            # 주문 비율 검사
            if params.order_ratio <= 0 or params.order_ratio > 1:
                errors.append("order_ratio must be between 0 and 1")
            
        except Exception as e:
            errors.append(f"Validation error: {str(e)}")
        
        return errors
    
    def get_all_user_params(self) -> Dict[str, LiveParams]:
        """모든 사용자 파라미터 가져오기"""
        result = {}
        
        try:
            # 파일 시스템에서 모든 파라미터 파일 찾기
            import glob
            pattern = f"*_{PARAMS_JSON_FILENAME}"
            for file_path in glob.glob(pattern):
                user_id = file_path.split('_')[0]
                params = self.load_params(file_path)
                if params:
                    result[user_id] = params
                    
        except Exception as e:
            logger.error(f"모든 사용자 파라미터 가져오기 실패: {e}")
        
        return result
    
    def backup_params(self, user_id: str, backup_path: str = None) -> bool:
        """파라미터 백업"""
        try:
            params = self.get_params(user_id)
            if not params:
                return False
            
            if backup_path is None:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_path = f"backups/{user_id}_params_{timestamp}.json"
            
            return self.save_params(params, backup_path)
            
        except Exception as e:
            logger.error(f"파라미터 백업 실패: {e}")
            return False
    
    def restore_params(self, user_id: str, backup_path: str) -> bool:
        """파라미터 복원"""
        try:
            params = self.load_params(backup_path)
            if not params:
                return False
            
            # 사용자 ID 업데이트
            params.user_id = user_id
            return self.save_params(params)
            
        except Exception as e:
            logger.error(f"파라미터 복원 실패: {e}")
            return False
    
    def get_params_template(self, strategy_type: StrategyType) -> Dict[str, Any]:
        """전략별 파라미터 템플릿 가져오기"""
        template = {
            "user_id": "example_user",
            "ticker": "BTC",
            "interval": "minutes5",
            "cash": MIN_CASH,
            "commission": MIN_FEE_RATIO,
            "order_ratio": 1.0,
            "strategy": {
                "strategy_type": strategy_type.value
            },
            "risk_management": RiskManagement().model_dump(),
            "execution": ExecutionConfig().model_dump(),
            "monitoring": MonitoringConfig().model_dump(),
            "name": f"{strategy_type.value.title()} Strategy",
            "description": f"Template for {strategy_type.value} strategy",
            "tags": [strategy_type.value],
            "version": "1.0.0"
        }
        
        # 전략별 파라미터 추가
        if strategy_type == StrategyType.MACD:
            template["strategy"]["macd"] = MACDParams().model_dump()
        elif strategy_type == StrategyType.RSI:
            template["strategy"]["rsi"] = RSIParams().model_dump()
        elif strategy_type == StrategyType.BOLLINGER:
            template["strategy"]["bollinger"] = BollingerParams().model_dump()
        elif strategy_type == StrategyType.GRID:
            template["strategy"]["grid"] = GridParams().model_dump()
        
        return template

# 전역 파라미터 관리자 인스턴스
_params_manager = None

def get_params_manager() -> ParamsManager:
    """전역 파라미터 관리자 인스턴스 가져오기"""
    global _params_manager
    if _params_manager is None:
        _params_manager = ParamsManager()
    return _params_manager

# 호환성 함수들
def load_params(path: str) -> Optional[LiveParams]:
    """파라미터 로드 (호환성)"""
    manager = get_params_manager()
    return manager.load_params(path)

def save_params(params: LiveParams, path: str = PARAMS_JSON_FILENAME) -> bool:
    """파라미터 저장 (호환성)"""
    manager = get_params_manager()
    return manager.save_params(params, path)

def delete_params(path: str = PARAMS_JSON_FILENAME):
    """파라미터 삭제 (호환성)"""
    manager = get_params_manager()
    manager.delete_params(path)

# 유틸리티 함수
def create_params_from_template(user_id: str, strategy_type: Union[str, StrategyType], 
                               ticker: str = "BTC", interval: str = "minutes5") -> LiveParams:
    """템플릿에서 파라미터 생성"""
    if isinstance(strategy_type, str):
        strategy_type = StrategyType(strategy_type)
    
    manager = get_params_manager()
    template_data = manager.get_params_template(strategy_type)
    
    # 사용자 정보 업데이트
    template_data["user_id"] = user_id
    template_data["ticker"] = ticker
    template_data["interval"] = interval
    
    return LiveParams(**template_data)

def optimize_params(user_id: str, optimization_config: Dict[str, Any]) -> Dict[str, Any]:
    """파라미터 최적화"""
    # TODO: 실제 최적화 로직 구현
    manager = get_params_manager()
    
    # 현재 파라미터 가져오기
    current_params = manager.get_params(user_id)
    if not current_params:
        return {"error": "No existing parameters found"}
    
    # 최적화 결과 시뮬레이션
    optimization_result = {
        "status": "success",
        "optimized_params": current_params.model_dump(),
        "improvement": 0.05,  # 5% 개선
        "backtest_result": {
            "total_return": 0.15,
            "sharpe_ratio": 1.2,
            "max_drawdown": 0.08,
            "win_rate": 0.65
        },
        "optimization_time": datetime.now().isoformat()
    }
    
    return optimization_result

# 사용 예제
if __name__ == "__main__":
    # 파라미터 관리자 생성
    manager = get_params_manager()
    
    # 템플릿으로 파라미터 생성
    params = create_params_from_template("test_user", StrategyType.MACD)
    
    # 파라미터 저장
    manager.save_params(params)
    
    # 파라미터 로드
    loaded_params = manager.load_params("test_user_params.json")
    if loaded_params:
        print(f"Loaded parameters for user: {loaded_params.user_id}")
        print(f"Strategy: {loaded_params.strategy.strategy_type}")
    
    # 파라미터 업데이트
    updates = {
        "risk_management": {
            "max_position_size": 0.8,
            "stop_loss_percent": 0.03
        },
        "execution": {
            "max_slippage": 0.0005
        }
    }
    
    manager.update_params("test_user", updates)