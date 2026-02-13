"""
매수/매도 조건 검증 로직
"""
import logging

logger = logging.getLogger(__name__)


def validate_ema_sell_conditions(conditions: dict) -> dict:
    """
    EMA SELL 조건 검증 및 기본값 보정

    Args:
        conditions: sell 조건 딕셔너리

    Returns:
        dict: 검증된 조건 (기본값 적용)
    """
    validated = conditions.copy()

    # Stale Position Check 파라미터 검증
    if validated.get("stale_position_check", False):
        # stale_hours: 0.5 ~ 24.0
        hours = validated.get("stale_hours", 1.0)
        try:
            hours = float(hours)
            if hours < 0.5:
                logger.warning(f"stale_hours ({hours}) < 0.5, 보정: 0.5")
                hours = 0.5
            elif hours > 24.0:
                logger.warning(f"stale_hours ({hours}) > 24.0, 보정: 24.0")
                hours = 24.0
            validated["stale_hours"] = hours
        except (TypeError, ValueError):
            logger.warning(f"Invalid stale_hours ({hours}), 기본값 1.0 적용")
            validated["stale_hours"] = 1.0

        # stale_threshold_pct: 0.001 ~ 0.1 (0.1% ~ 10%)
        threshold = validated.get("stale_threshold_pct", 0.01)
        try:
            threshold = float(threshold)
            if threshold < 0.001:
                logger.warning(f"stale_threshold_pct ({threshold:.2%}) < 0.1%, 보정: 0.1%")
                threshold = 0.001
            elif threshold > 0.1:
                logger.warning(f"stale_threshold_pct ({threshold:.2%}) > 10%, 보정: 10%")
                threshold = 0.1
            validated["stale_threshold_pct"] = threshold
        except (TypeError, ValueError):
            logger.warning(f"Invalid stale_threshold_pct ({threshold}), 기본값 0.01 (1%) 적용")
            validated["stale_threshold_pct"] = 0.01

    return validated


def validate_macd_sell_conditions(conditions: dict) -> dict:
    """
    MACD SELL 조건 검증 및 기본값 보정 (향후 확장용)

    Args:
        conditions: sell 조건 딕셔너리

    Returns:
        dict: 검증된 조건 (기본값 적용)
    """
    # 현재는 특별한 검증 없음
    return conditions.copy()
