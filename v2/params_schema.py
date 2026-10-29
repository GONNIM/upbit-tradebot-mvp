"""백테스터 화면 입력 19개의 검증과 PULLBACK 파라미터 파일 변환 (표준 라이브러리만 사용).

1차 규칙: 19개 키 정확히 · 모르는 키 400 · 파일 전체 덮어쓰기 (P4 에서 거래 시간 키를 추가할 때 바뀐다).
2차 T13: 화면 입력은 그대로 19개, 파일은 18키 + 이전 저장본에 있던 선택 4키(거래 시간)를 보존(keep_optional).
PARAM_FIELDS 는 원본 백테스터 HTML 의 id 속성(min/max/step/options)을 그대로 옮긴 것이며,
시험(test_param_fields_match_original_html)이 원본 HTML 과 대조한다.
결정 1024-03 가(2026-10-24): 원본 화면엔 하한이 없으나 엔진 입력 안전을 위해 서버에서만 추가(SERVER_EXTRA_LIMITS).
"""
import math
import re

PARAM_FIELDS = {
    "symbol": {"type": "text"},
    "maType": {"type": "select", "options": ["ema", "sma"]},
    "src": {"type": "select", "options": ["1m", "3m", "5m", "1h"]},
    "days": {"type": "number", "min": 5, "max": 365},
    "ma60p": {"type": "number", "min": 2, "max": 500},
    "ma200p": {"type": "number", "min": 10, "max": 1000},
    "pullbackP": {"type": "number", "min": 2, "max": 500},
    "slopeLB": {"type": "number", "min": 1, "max": 500},
    "minSlope": {"type": "number", "step": 0.05},
    "slopeDrop": {"type": "number", "min": 0, "step": 0.05},
    "buyOnGoldenCross": {"type": "select", "options": ["yes", "no"]},
    "maxSplits": {"type": "number", "min": 0, "max": 10},
    "maxPullbackBuys": {"type": "number", "min": 1, "max": 5},
    "tp": {"type": "number", "step": 0.1},
    "sl": {"type": "number", "step": 0.1},
    "capital": {"type": "number", "step": 100},
    "fee": {"type": "number", "step": 0.01},
    "deadcross": {"type": "select", "options": ["yes", "no"]},
    "compounding": {"type": "select", "options": ["no", "yes"]},
}

# 서버만 쓰는 추가 하한: "gt" = 초과, "ge" = 이상 (PARAM_FIELDS 와 별개, 원본 HTML 과 대조하지 않음)
SERVER_EXTRA_LIMITS = {
    "tp": ("gt", 0),
    "sl": ("gt", 0),
    "capital": ("gt", 0),
    "fee": ("ge", 0),
}

# HTML 에 step 이 없는 number 칸(브라우저 기본 step 1) — 정수만 받는다.
INTEGER_FIELDS = ("days", "ma60p", "ma200p", "pullbackP", "slopeLB",
                  "maxSplits", "maxPullbackBuys")

_SYMBOL_RE = re.compile(r"^[A-Za-z0-9]{2,20}$")
# 2차 T13: 엔진 로더(engine/pullback_params._TICKER_RE)와 같게 영문 대문자만(숫자 든 종목은 엔진이 받지 않음)
_UPBIT_SYMBOL_RE = re.compile(r"^KRW-[A-Z]{1,15}$")
# 2차 T13: 저장 때 지우지 않고 보존하는 선택 4키(거래 시간 — engine/pullback_params.OPTIONAL_KEYS 와 같은 이름·형식)
OPTIONAL_KEYS = ("enable_trading_hours", "trading_start_time", "trading_end_time", "allow_sell_during_off_hours")
_HHMM_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_INTERVAL = {"1m": "minute1", "3m": "minute3", "5m": "minute5", "1h": "minute60"}
_YES_NO = {"yes": True, "no": False}


def validate_params(d, source="binance"):
    """검증된 19개 dict(정해진 순서)를 돌려준다. 실패 시 ValueError(필드 이름 또는 "keys").

    symbol 규칙은 시험한 데이터 출처로 나눈다: binance 영숫자 2~20자, upbit KRW-XXX."""
    if source not in ("binance", "upbit"):
        raise ValueError("source")
    if not isinstance(d, dict) or set(d.keys()) != set(PARAM_FIELDS):
        raise ValueError("keys")
    out = {}
    for name, spec in PARAM_FIELDS.items():
        v = d[name]
        t = spec["type"]
        if t == "number":
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                raise ValueError(name)
            try:
                if not math.isfinite(v):
                    raise ValueError(name)
                if "min" in spec and v < spec["min"]:
                    raise ValueError(name)
                if "max" in spec and v > spec["max"]:
                    raise ValueError(name)
                lim = SERVER_EXTRA_LIMITS.get(name)
                if lim is not None:
                    op, bound = lim
                    if (op == "gt" and not v > bound) or (op == "ge" and not v >= bound):
                        raise ValueError(name)
                if name in INTEGER_FIELDS:
                    if v != int(v):
                        raise ValueError(name)
                    v = int(v)
            except OverflowError:
                raise ValueError(name)
        elif t == "select":
            if not isinstance(v, str) or v not in spec["options"]:
                raise ValueError(name)
        else:  # symbol
            if not isinstance(v, str):
                raise ValueError(name)
            if source == "upbit":
                v = v.strip().upper()
                if not _UPBIT_SYMBOL_RE.fullmatch(v):
                    raise ValueError(name)
            else:
                if not _SYMBOL_RE.fullmatch(v):
                    raise ValueError(name)
                v = v.upper()
        out[name] = v
    return out


def keep_optional(file_dict, old):
    """2차 T13: 이전 저장본(old dict)에 있던 선택 4키(거래 시간)를 형식이 맞을 때만 그대로 뒤에 붙인다.
    1차 「18키 전체 덮어쓰기」의 바뀐 부분 — 「이 설정으로 동작」 때 운용 설정(거래 시간)이 지워지지 않게."""
    out = dict(file_dict)
    if not isinstance(old, dict):
        return out
    for k in OPTIONAL_KEYS:
        if k not in old:
            continue
        v = old[k]
        if k in ("enable_trading_hours", "allow_sell_during_off_hours"):
            if isinstance(v, bool):
                out[k] = v
        elif isinstance(v, str) and _HHMM_RE.fullmatch(v):
            out[k] = v
    return out


def to_engine_file(p, ticker):
    """검증된 19개 → P3 4.2 키 18개(순서 유지). days·Binance symbol 은 넣지 않는다."""
    return {
        "ticker": ticker,
        "interval": _INTERVAL[p["src"]],
        "maType": p["maType"],
        "ma60p": p["ma60p"],
        "ma200p": p["ma200p"],
        "pullbackP": p["pullbackP"],
        "slopeLB": p["slopeLB"],
        "minSlope": p["minSlope"],
        "slopeDrop": p["slopeDrop"],
        "buyOnGoldenCross": _YES_NO[p["buyOnGoldenCross"]],
        "maxSplits": p["maxSplits"],
        "maxPullbackBuys": p["maxPullbackBuys"],
        "tp": p["tp"],
        "sl": p["sl"],
        "deadcross": _YES_NO[p["deadcross"]],
        "compounding": _YES_NO[p["compounding"]],
        "capital": p["capital"],
        "fee": p["fee"],
    }
