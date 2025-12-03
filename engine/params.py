from pydantic import BaseModel, Field, field_validator
from config import (
    MIN_CASH,
    MIN_FEE_RATIO,
    PARAMS_JSON_FILENAME,
    STRATEGY_TYPES,
    DEFAULT_STRATEGY_TYPE,
)
import json
import os


class LiveParams(BaseModel):
    ticker: str = Field(..., description="KRW‑BTC 형식 혹은 BTC")
    interval: str = Field(..., description="Upbit candle interval id")

    fast_period: int = Field(12, ge=1, le=50)
    slow_period: int = Field(26, ge=1, le=100)
    signal_period: int = Field(7, ge=1, le=20)

    macd_threshold: float = 0.0
    take_profit: float = Field(0.05, gt=0)
    stop_loss: float = Field(0.01, gt=0)

    cash: int = Field(MIN_CASH, ge=MIN_CASH)
    commission: float = Field(MIN_FEE_RATIO, ge=MIN_FEE_RATIO)

    min_holding_period: int = 1
    macd_crossover_threshold: float = 0.0

    macd_exit_enabled: bool = True
    signal_confirm_enabled: bool = False

    order_ratio: float = 1.0

    # =====================================================
    # 🧠 전략 타입 (MACD / EMA)
    #  - 기본값: DEFAULT_STRATEGY_TYPE (현재 "MACD")
    #  - UI(set_config.py)에서 선택한 값을 저장/로드
    # =====================================================
    strategy_type: str = Field(
        DEFAULT_STRATEGY_TYPE,
        description="전략 타입 (예: MACD, EMA)",
    )

    # --------------------
    # Validators
    # --------------------
    @field_validator("ticker")
    def _validate_ticker(cls, v: str) -> str:  # noqa: N805
        v = v.upper().strip()
        if "-" in v:
            base, quote = v.split("-", 1)
            if base != "KRW" or not quote.isalpha():
                raise ValueError("Format must be KRW-XXX or simply XXX")
            return v
        if not v.isalpha():
            raise ValueError("Ticker must be alphabetic, e.g. BTC, ETH")
        return v

    @field_validator("strategy_type")
    def _validate_strategy_type(cls, v: str) -> str:  # noqa: N805
        """
        - 대소문자 무시하고 STRATEGY_TYPES 안에 있는지만 체크
        - 내부적으로는 항상 대문자로 저장
        """
        if not v:
            return DEFAULT_STRATEGY_TYPE
        v_norm = v.upper().strip()
        allowed = [s.upper() for s in STRATEGY_TYPES]
        if v_norm not in allowed:
            raise ValueError(f"strategy_type must be one of {allowed} (got {v!r})")
        return v_norm
    
    # --------------------
    # Convenience
    # --------------------
    @property
    def upbit_ticker(self) -> str:
        return self.ticker if "-" in self.ticker else f"KRW-{self.ticker}"

    @property
    def is_macd(self) -> bool:
        return self.strategy_type == "MACD"

    @property
    def is_ema(self) -> bool:
        return self.strategy_type == "EMA"
    

def load_params(path: str) -> LiveParams | None:
    """
    latest_params.json → LiveParams 로드
    - 기존 파일에 strategy_type이 없어도 기본값(DEFAULT_STRATEGY_TYPE)으로 채워짐
    """
    if not os.path.exists(path):
        return None
    with open(path) as f:
        data = json.load(f)
        return LiveParams(**data)


def save_params(params: LiveParams, path: str = PARAMS_JSON_FILENAME):
    with open(path, "w") as f:
        json.dump(params.model_dump(), f, indent=2, ensure_ascii=False)


def delete_params(path: str = PARAMS_JSON_FILENAME):
    """설정 파라미터 JSON 파일 삭제"""
    if os.path.exists(path):
        os.remove(path)
