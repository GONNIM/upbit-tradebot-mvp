from pydantic import BaseModel, Field, field_validator
from config import MIN_CASH, MIN_FEE_RATIO, PARAMS_JSON_FILENAME
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

    order_ratio: float = 1.0

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

    @property
    def upbit_ticker(self) -> str:
        return self.ticker if "-" in self.ticker else f"KRW-{self.ticker}"


def load_params(path: str) -> LiveParams:
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return LiveParams(**json.load(f))


def save_params(params: LiveParams, path: str = PARAMS_JSON_FILENAME):
    with open(path, "w") as f:
        json.dump(params.model_dump(), f, indent=2)


def delete_params(path: str = PARAMS_JSON_FILENAME):
    """설정 파라미터 JSON 파일 삭제"""
    if os.path.exists(path):
        os.remove(path)
