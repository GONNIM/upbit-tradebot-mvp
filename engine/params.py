from pydantic import BaseModel, Field, field_validator, model_validator
from config import (
    MIN_CASH,
    MIN_FEE_RATIO,
    PARAMS_JSON_FILENAME,
    STRATEGY_TYPES,
    DEFAULT_STRATEGY_TYPE,
    ENGINE_EXEC_MODE,
)
import json
import os
import logging
from pathlib import Path


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


class LiveParams(BaseModel):
    ticker: str = Field(..., description="KRW-BTC 형식 혹은 BTC")
    interval: str = Field(..., description="Upbit candle interval id")

    # fast_period, slow_period: 전략별로 다양한 값 허용 (1 ~ 500)
    # 실제 제약: fast < slow는 validator에서 검증
    fast_period: int = Field(12, ge=1, le=500)
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

    # Base EMA GAP 전략 (EMA 전용)
    base_ema_gap_diff: float = Field(
        default=-0.005,
        ge=-0.02,
        le=0.0,
        description="Base EMA GAP 임계값 (종가가 Base EMA보다 이 값 이하일 때 매수, 예: -0.005 = -0.5%)"
    )

    # 이동평균 계산 방식 (EMA 전략 전용)
    ma_type: str = Field(
        default="SMA",
        description="이동평균 계산 방식: SMA (단순), EMA (지수), WMA (가중)"
    )

    # EMA 매수/매도 별도 설정
    use_separate_ema: bool = Field(
        default=True,
        description="매수/매도 EMA 별도 설정 여부 (True: 별도 설정, False: 공통 사용)",
    )
    fast_buy: int | None = Field(
        default=None,
        ge=1,
        le=500,
        description="매수용 단기 EMA (None이면 fast_period 사용)",
    )
    slow_buy: int | None = Field(
        default=None,
        ge=1,
        le=500,
        description="매수용 장기 EMA (None이면 slow_period 사용)",
    )
    fast_sell: int | None = Field(
        default=None,
        ge=1,
        le=500,
        description="매도용 단기 EMA (None이면 fast_period 사용)",
    )
    slow_sell: int | None = Field(
        default=None,
        ge=1,
        le=500,
        description="매도용 장기 EMA (None이면 slow_period 사용)",
    )

    strategy_type: str = Field(
        DEFAULT_STRATEGY_TYPE,
        description="전략 타입 (예: MACD, EMA)",
    )
    engine_exec_mode: str = Field(
        default=ENGINE_EXEC_MODE,  # "BACKTEST" | "REPLAY"
        description="엔진 실행 모드",
    )

    # 거래 시간 제한 (Trading Hours Restriction)
    enable_trading_hours: bool = Field(
        default=False,
        description="거래 시간 제한 활성화 여부 (새벽 슬리피지 방지용)"
    )
    trading_start_time: str = Field(
        default="09:00",
        description="거래 시작 시간 (HH:MM 형식, KST 기준)"
    )
    trading_end_time: str = Field(
        default="02:00",
        description="거래 종료 시간 (HH:MM 형식, KST 기준)"
    )
    allow_sell_during_off_hours: bool = Field(
        default=True,
        description="거래 쉬는시간에도 포지션 보유 시 매도 허용 (권장: True)"
    )

    # --------------------
    # Validators
    # --------------------
    @model_validator(mode='after')
    def _validate_fast_slow_periods(self):
        """
        fast_period는 slow_period보다 작아야 함 (모든 전략 공통)
        EMA 별도 설정 사용 시에도 동일 규칙 적용
        """
        # 기본 fast/slow 검증
        if self.fast_period >= self.slow_period:
            raise ValueError(
                f"fast_period ({self.fast_period})는 slow_period ({self.slow_period})보다 작아야 합니다."
            )

        # EMA 별도 설정 검증
        if self.use_separate_ema:
            # 매수용 EMA 검증
            if self.fast_buy is not None and self.slow_buy is not None:
                if self.fast_buy >= self.slow_buy:
                    raise ValueError(
                        f"fast_buy ({self.fast_buy})는 slow_buy ({self.slow_buy})보다 작아야 합니다."
                    )

            # 매도용 EMA 검증
            if self.fast_sell is not None and self.slow_sell is not None:
                if self.fast_sell >= self.slow_sell:
                    raise ValueError(
                        f"fast_sell ({self.fast_sell})는 slow_sell ({self.slow_sell})보다 작아야 합니다."
                    )

        return self

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
        - 이상한 값이면 기본값(ENGINE_EXEC_MODE)으로 폴백 + WARN 로그
        """
        if not v:
            return ENGINE_EXEC_MODE

        v_norm = v.upper().strip()
        allowed = ["BACKTEST", "REPLAY"]

        if v_norm not in allowed:
            logger.warning(
                f"[LiveParams] invalid engine_exec_mode={v!r} → fallback to '{ENGINE_EXEC_MODE}' "
                f"(allowed={allowed})"
            )
            return ENGINE_EXEC_MODE
        return v_norm

    @field_validator("ma_type")
    def _validate_ma_type(cls, v: str) -> str:  # noqa: N805
        """
        - SMA / EMA / WMA 3가지만 허용
        - 대소문자 무시
        - 이상한 값이면 SMA로 폴백 + WARN 로그
        """
        if not v:
            return "SMA"

        v_norm = v.upper().strip()
        allowed = ["SMA", "EMA", "WMA"]

        if v_norm not in allowed:
            logger.warning(
                f"[LiveParams] invalid ma_type={v!r} → fallback to 'SMA' "
                f"(allowed={allowed})"
            )
            return "SMA"

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
    def interval_sec(self) -> int:
        """
        interval 문자열을 초(sec) 단위로 변환.
        예: "minute1" -> 60, "minute3" -> 180, "minute5" -> 300
        """
        interval_map = {
            "minute1": 60,
            "minute3": 180,
            "minute5": 300,
            "minute10": 600,
            "minute15": 900,
            "minute30": 1800,
            "minute60": 3600,
            "day": 86400,
        }
        return interval_map.get(self.interval, 60)  # 기본값 60초

    @property
    def is_macd(self) -> bool:
        """현재 선택된 전략이 MACD인지 여부."""
        return self.strategy_type == "MACD"

    @property
    def is_ema(self) -> bool:
        """현재 선택된 전략이 EMA인지 여부."""
        return self.strategy_type == "EMA"


# ✅ 전략별 파일명으로 스코프를 나눠주는 헬퍼
def _scoped_path(path: str, strategy_type: str | None) -> str:
    """
    ✅ 핵심:
    - 같은 user_id라도 MACD/EMA 각각 별도 파일로 저장/로드되게 한다.
    - 예: "abc_latest_params.json" -> "abc_MACD_latest_params.json"
    """
    if not strategy_type:
        return path

    st = str(strategy_type).upper().strip()
    p = Path(path)
    # 파일명 앞에 "{STRATEGY}_"를 끼워 넣는다.
    return str(p.with_name(f"{p.stem}_{st}{p.suffix}"))


def load_params(path: str, strategy_type: str | None = None) -> LiveParams | None:
    """
    - strategy_type이 들어오면 해당 전략용 파일에서 로드한다.
    - 해당 전략 파일이 없으면 None (상위에서 초기값/UI 기본값 처리)
    """
    strategy_type = (strategy_type or DEFAULT_STRATEGY_TYPE)

    # ✅ 전략별 파일 경로로 스코핑
    path = _scoped_path(path, strategy_type)

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
    data.setdefault("engine_exec_mode", ENGINE_EXEC_MODE)
    data.setdefault("base_ema_period", 200)
    data.setdefault("base_ema_gap_diff", -0.005)
    # 거래 시간 제한 (백워드 호환)
    data.setdefault("enable_trading_hours", False)
    data.setdefault("trading_start_time", "09:00")
    data.setdefault("trading_end_time", "02:00")
    data.setdefault("allow_sell_during_off_hours", True)
    # EMA 매수/매도 별도 설정 (백워드 호환)
    data.setdefault("use_separate_ema", True)
    data.setdefault("fast_buy", None)
    data.setdefault("slow_buy", None)
    data.setdefault("fast_sell", None)
    data.setdefault("slow_sell", None)
    # 이동평균 계산 방식 (백워드 호환)
    data.setdefault("ma_type", "SMA")

    try:
        return LiveParams(**data)
    except Exception as e:
        # 여기서 바로 예외를 올려버리면 엔진 스타트가 막히므로
        # 안전하게 None 리턴 → 상위에서 새 파라미터를 생성하도록 유도
        logger.warning(f"[LiveParams] validation error for {path}: {e}")
        return None


def save_params(params: LiveParams, path: str = PARAMS_JSON_FILENAME, strategy_type: str | None = None):
    """
    - strategy_type이 들어오면 해당 전략용 파일로 저장한다.
    - 즉, MACD/EMA 각각 다른 파일에 저장되므로 전략 변경 시 값이 유지된다.
    """
    # ✅ 전략별 파일 경로로 스코핑
    path = _scoped_path(path, strategy_type)

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

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


# ============================================================
# 활성 전략 파일 관리 (로그아웃/로그인 시 전략 유지)
# ============================================================
def _get_active_strategy_path(user_id: str) -> str:
    """사용자별 활성 전략 파일 경로 반환"""
    return f"{user_id}_active_strategy.txt"


def save_active_strategy(user_id: str, strategy_type: str) -> None:
    """
    사용자의 현재 활성 전략을 파일에 저장.
    로그아웃 후 재로그인 시에도 전략이 유지되도록 함.
    """
    strategy_type = str(strategy_type).upper().strip()
    path = _get_active_strategy_path(user_id)

    try:
        with open(path, "w") as f:
            f.write(strategy_type)
        logger.info(f"[ActiveStrategy] Saved active strategy for {user_id}: {strategy_type}")
    except Exception as e:
        logger.error(f"[ActiveStrategy] Failed to save active strategy for {user_id}: {e}")


def load_active_strategy(user_id: str) -> str | None:
    """
    사용자의 활성 전략을 파일에서 로드.
    파일이 없거나 읽기 실패 시 None 반환.
    """
    path = _get_active_strategy_path(user_id)

    if not os.path.exists(path):
        logger.debug(f"[ActiveStrategy] No active strategy file for {user_id}")
        return None

    try:
        with open(path, "r") as f:
            strategy_type = f.read().strip().upper()

        if strategy_type in STRATEGY_TYPES:
            logger.info(f"[ActiveStrategy] Loaded active strategy for {user_id}: {strategy_type}")
            return strategy_type
        else:
            logger.warning(f"[ActiveStrategy] Invalid strategy in file for {user_id}: {strategy_type}")
            return None
    except Exception as e:
        logger.error(f"[ActiveStrategy] Failed to load active strategy for {user_id}: {e}")
        return None
