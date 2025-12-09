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
import logging


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


class LiveParams(BaseModel):
    ticker: str = Field(..., description="KRW-BTC 형식 혹은 BTC")
    interval: str = Field(..., description="Upbit candle interval id")

    # fast_period 는 기존 제약 유지 (1 ~ 50)
    fast_period: int = Field(12, ge=1, le=50)
    # 🔴 전략별로 다르게 쓰고 싶으므로, 여기서는 상한을 넉넉히 열어둔다.
    # MACD 에서만 <= 100 제약을 걸고, EMA 에서는 200 같은 값도 허용할 것.
    slow_period: int = Field(26, ge=1, le=500)
    # signal_period 도 UI 에서 1~20 범위 쓰고 있으면 그대로 둬도 OK
    signal_period: int = Field(7, ge=1, le=20)
    
    macd_threshold: float = 0.0
    take_profit: float = Field(0.05, gt=0)
    stop_loss: float = Field(0.01, gt=0)

    cash: int = Field(MIN_CASH, ge=MIN_CASH)
    commission: float = Field(MIN_FEE_RATIO, ge=MIN_FEE_RATIO)

    min_holding_period: int = Field(default=1, ge=1)
    macd_crossover_threshold: float = Field(default=0.0)

    macd_exit_enabled: bool = True
    signal_confirm_enabled: bool = False

    order_ratio: float = Field(default=1.0, gt=0)

    # EMA 전용 (Base EMA)
    base_ema_period: int = Field(
        200,
        ge=1,
        le=500,
        description="EMA 전략에서 Base EMA 기간 (예: 200)",
    )

    strategy_type: str = Field(
        DEFAULT_STRATEGY_TYPE,
        description="전략 타입 (예: MACD, EMA)",
    )
    engine_exec_mode: str = Field(
        default="REPLAY",  # "BACKTEST" | "REPLAY"
        description="엔진 실행 모드",
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
        - 기존 JSON에 이상한 값이 들어있어도 엔진이 깨지지 않도록
          기본값으로 폴백 + WARN 로그 남김
        """
        if not v:
            return DEFAULT_STRATEGY_TYPE
        
        v_norm = v.upper().strip()
        allowed = [s.upper() for s in STRATEGY_TYPES]

        if v_norm not in allowed:
            # ❗ 여기서 바로 예외를 던지면 오래된/깨진 JSON 때문에
            #    엔진 전체가 로드 단계에서 죽어버릴 수 있어서
            #    경고만 남기고 안전하게 기본값으로 폴백한다.
            logger.warning(
                f"[LiveParams] invalid strategy_type={v!r} → fallback to {DEFAULT_STRATEGY_TYPE!r} "
                f"(allowed={allowed})"
            )
            return DEFAULT_STRATEGY_TYPE
        
        return v_norm
    
    @field_validator("engine_exec_mode")
    def _validate_engine_exec_mode(cls, v: str) -> str:  # noqa: N805
        """
        - BACKTEST / REPLAY 두 값만 허용
        - 대소문자/공백 정리
        - 이상한 값이면 기본값("REPLAY")으로 폴백 + WARN 로그
        """
        if not v:
            return "REPLAY"
        
        v_norm = v.upper().strip()
        allowed = ["BACKTEST", "REPLAY"]

        if v_norm not in allowed:
            logger.warning(
                f"[LiveParams] invalid engine_exec_mode={v!r} → fallback to 'REPLAY' "
                f"(allowed={allowed})"
            )
            return "REPLAY"
        return v_norm
    
    # --------------------
    # Convenience
    # --------------------
    @property
    def upbit_ticker(self) -> str:
        """
        내부에서는 항상 KRW-XXX 형태로 쓰기 위해 변환 헬퍼 제공.
        JSON에는 'BTC' / 'ETH'처럼만 저장되어 있어도 무방.
        """
        return self.ticker if "-" in self.ticker else f"KRW-{self.ticker}"

    @property
    def is_macd(self) -> bool:
        """현재 선택된 전략이 MACD인지 여부."""
        return self.strategy_type == "MACD"

    @property
    def is_ema(self) -> bool:
        """현재 선택된 전략이 EMA인지 여부."""
        return self.strategy_type == "EMA"
    

def load_params(path: str) -> LiveParams | None:
    """
    latest_params.json → LiveParams 로드

    - 기존 파일에 strategy_type이 없어도 기본값(DEFAULT_STRATEGY_TYPE)으로 채워짐
    - 파일이 없거나, JSON/검증 오류가 나면 None을 반환해서
      상위 레벨에서 "초기값 생성" 로직을 태울 수 있게 함.
    """
    if not os.path.exists(path):
        logger.info(f"[LiveParams] params file not found: {path}")
        return None
    
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.warning(f"[LiveParams] failed to read json from {path}: {e}")
        return None

    # 🔽 여기서 누락 필드들에 대해 안전한 기본값을 강제로 채워 준다.
    #    (옛날 JSON과의 백워드 호환용)
    data.setdefault("commission", MIN_FEE_RATIO)
    data.setdefault("min_holding_period", 1)
    data.setdefault("macd_crossover_threshold", 0.0)
    data.setdefault("strategy_type", DEFAULT_STRATEGY_TYPE)
    data.setdefault("engine_exec_mode", "REPLAY")
    data.setdefault("base_ema_period", 200)

    try:
        return LiveParams(**data)
    except Exception as e:
        # 여기서 바로 예외를 올려버리면 엔진 스타트가 막히므로
        # 안전하게 None 리턴 → 상위에서 새 파라미터를 생성하도록 유도
        logger.warning(f"[LiveParams] validation error for {path}: {e}")
        return None


def save_params(params: LiveParams, path: str = PARAMS_JSON_FILENAME):
    """
    LiveParams → JSON 저장

    - 기본 path는 PARAMS_JSON_FILENAME 이지만,
      실제 운용에서는 보통 f"{user_id}_{PARAMS_JSON_FILENAME}" 형태로
      사용자별로 구분해서 넘겨주는 것을 추천.
    """
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

    # BaseModel 인스턴스 → __dict__ 로부터 순수 필드만 추출
    if isinstance(params, BaseModel):
        raw = params.__dict__.copy()
        # pydantic 내부 메타 필드 제거 (있으면)
        raw.pop("__pydantic_private__", None)
        raw.pop("__pydantic_fields_set__", None)
        raw.pop("__pydantic_extra__", None)
        raw.pop("__pydantic_initialised__", None)
    else:
        # 혹시 dict 로 들어와도 방어
        raw = dict(params)

    with open(path, "w") as f:
        json.dump(params.model_dump(), f, indent=2, ensure_ascii=False)
        
    logger.info(f"[LiveParams] saved params to {path}")


def delete_params(path: str = PARAMS_JSON_FILENAME):
    """설정 파라미터 JSON 파일 삭제"""
    if os.path.exists(path):
        os.remove(path)
        logger.info(f"[LiveParams] deleted params file: {path}")
    else:
        logger.info(f"[LiveParams] delete_params called but file not found: {path}")
