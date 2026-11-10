"""백테스터 화면 입력 25개의 검증과 PULLBACK 파라미터 파일 변환 (표준 라이브러리만 사용).

1105-09 (Ver2): 입력 19 − 2(minSlope·slopeDrop) + 8 = 25, 파일 18 − 2 + 8 = 24키. PARAM_FIELDS 는 Ver2 화면
(docs/new-version/MA_GC_Pullback_Backtester_2611051030(Ver2).html)의 id 속성을 옮긴 것이다.

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
    "src": {"type": "select", "options": ["1m", "3m", "5m", "10m", "15m", "30m", "1h"]},
    "days": {"type": "number", "min": 5, "max": 365},
    "ma60p": {"type": "number", "min": 2, "max": 500},
    "ma200p": {"type": "number", "min": 10, "max": 1000},
    "pullbackP": {"type": "number", "min": 2, "max": 500},
    "slopeLB": {"type": "number", "min": 1, "max": 500},
    "gcMaxGapPct": {"type": "select",
                    "options": ["0", "0.5", "1", "1.5", "2", "2.5", "3", "3.5", "4", "4.5", "5"]},
    "ma60MinSlope": {"type": "number", "step": 0.05},
    "ma60SlopeDrop": {"type": "number", "min": 0, "step": 0.05},
    "slStreakPause": {"type": "number", "min": 0, "max": 20},
    "slStreakCooldownHours": {"type": "number", "min": 0, "step": 0.5},
    "episodePullbackCap": {"type": "number", "min": 0, "max": 20},
    "episodeTpDecayPct": {"type": "number", "min": 0, "max": 99, "step": 5},
    "episodeTpFloorPct": {"type": "number", "min": 0, "step": 0.05},
    "buyOnGoldenCross": {"type": "select", "options": ["yes", "no"]},
    "maxSplits": {"type": "number", "min": 0, "max": 10},
    "maxPullbackBuys": {"type": "number", "min": 1, "max": 5},
    "tp": {"type": "number", "step": 0.1},
    "sl": {"type": "number", "step": 0.1},
    "capital": {"type": "number", "step": 100},
    "fee": {"type": "number", "step": 0.01},
    "deadcross": {"type": "select", "options": ["yes", "no"]},   # Ver2 기본 선택 no(R6) — 옵션 순서는 화면 그대로
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
INTEGER_FIELDS = ("days", "ma60p", "ma200p", "pullbackP", "slopeLB", "slStreakPause", "episodePullbackCap",
                  "maxSplits", "maxPullbackBuys")

_SYMBOL_RE = re.compile(r"^[A-Za-z0-9]{2,20}$")
# 2차 T13: 엔진 로더(engine/pullback_params._TICKER_RE)와 같게 영문 대문자만(숫자 든 종목은 엔진이 받지 않음)
_UPBIT_SYMBOL_RE = re.compile(r"^KRW-[A-Z]{1,15}$")
# 2차 T13: 저장 때 지우지 않고 보존하는 선택 4키(거래 시간 — engine/pullback_params.OPTIONAL_KEYS 와 같은 이름·형식)
OPTIONAL_KEYS = ("enable_trading_hours", "trading_start_time", "trading_end_time", "allow_sell_during_off_hours")
_HHMM_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
# 1109 작업 C: 눌림목 전용 투자 비율(%) 선택 키 — engine/pullback_params.RATIO_KEYS 와 같은 이름(시험이 비교).
# 요청의 최상위 선택 필드 investRatioPct 로 받아 입장 모드의 키에만 쓴다. 25칸(PARAM_FIELDS)에는 넣지 않는다.
RATIO_KEYS = ("invest_ratio_pct_live", "invest_ratio_pct_test")
RATIO_MIN, RATIO_MAX = 0.1, 100.0


def ratio_key(mode):
    return "invest_ratio_pct_live" if mode == "LIVE" else "invest_ratio_pct_test"


def valid_ratio(v):
    """None → None. 0.1~100, 소수 첫째 자리 이하의 수 → float. 그 밖은 ValueError("invest_ratio_pct")
    (engine/pullback_params.valid_ratio 와 같은 규칙 — 시험이 같은 입력으로 비교)."""
    if v is None:
        return None
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ValueError("invest_ratio_pct")
    try:
        f = float(v)
    except (OverflowError, ValueError):
        raise ValueError("invest_ratio_pct")
    if not math.isfinite(f) or f < RATIO_MIN or f > RATIO_MAX or abs(f * 10 - round(f * 10)) > 1e-9:
        raise ValueError("invest_ratio_pct")
    return round(f, 1)


# 1110-01: 추적 손절 선택 3키 — engine/pullback_params.TRAILING_KEYS·valid_trailing 과 같은 이름·규칙(시험이 비교).
# 요청의 최상위 선택 필드 trailing({ts_on, ts_mode, ts_pct})로 받는다. 꺼짐이면 파일에 키를 쓰지 않는다(되돌리기 쉬움).
TRAILING_KEYS = ("ts_on", "ts_mode", "ts_pct")
TS_MODES = ("ratio", "fixed")
TS_PCT_MIN, TS_PCT_MAX = 1.0, 100.0


def valid_trailing(d):
    """d(dict) 안의 3키 → 정규화 dict, 셋 다 없으면 None. 틀리거나 일부만 있으면 ValueError("trailing")."""
    if not isinstance(d, dict):
        raise ValueError("trailing")
    if not any(k in d for k in TRAILING_KEYS):
        return None
    if not all(k in d for k in TRAILING_KEYS):
        raise ValueError("trailing")
    on, mode, pct = d["ts_on"], d["ts_mode"], d["ts_pct"]
    if not isinstance(on, bool) or not isinstance(mode, str) or mode not in TS_MODES:
        raise ValueError("trailing")
    if isinstance(pct, bool) or not isinstance(pct, (int, float)):
        raise ValueError("trailing")
    try:
        f = float(pct)
    except (OverflowError, ValueError):
        raise ValueError("trailing")
    if not math.isfinite(f) or f < TS_PCT_MIN or f > TS_PCT_MAX or abs(f * 10 - round(f * 10)) > 1e-9:
        raise ValueError("trailing")
    return {"ts_on": on, "ts_mode": mode, "ts_pct": round(f, 1)}


def apply_trailing(file_dict, ts):
    """1110-01: 요청의 추적 손절 값(ts = valid_trailing 결과 또는 None)을 파일 dict 에 반영.
    켬이면 3키를 쓰고, 끔·None 이면 3키를 지운다."""
    out = dict(file_dict)
    for k in TRAILING_KEYS:
        out.pop(k, None)
    if ts is not None and ts["ts_on"]:
        out.update(ts)
    return out


_INTERVAL = {"1m": "minute1", "3m": "minute3", "5m": "minute5", "10m": "minute10", "15m": "minute15",
             "30m": "minute30", "1h": "minute60"}
_YES_NO = {"yes": True, "no": False}


def validate_params(d, source="binance"):
    """검증된 25개 dict(정해진 순서)를 돌려준다. 실패 시 ValueError(필드 이름 또는 "keys").

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
    for k in RATIO_KEYS:     # 1109 작업 C: 투자 비율(모의·실계좌 따로)도 저장 때 지우지 않고 보존(형식이 맞을 때만)
        if k in old:
            try:
                r = valid_ratio(old[k])
            except ValueError:
                continue
            if r is not None:
                out[k] = r
    try:                     # 1110-01: 요청에 trailing 이 없을 때(옛 화면) 추적 손절 3키도 지우지 않는다(형식이 맞을 때만)
        ts = valid_trailing(old)
    except ValueError:
        ts = None
    if ts is not None and ts["ts_on"]:
        out.update(ts)
    return out


def to_engine_file(p, ticker):
    """검증된 25개 → 파일 24키(engine/pullback_params.PULLBACK_KEYS 순서). days·Binance symbol 은 넣지 않는다."""
    return {
        "ticker": ticker,
        "interval": _INTERVAL[p["src"]],
        "maType": p["maType"],
        "ma60p": p["ma60p"],
        "ma200p": p["ma200p"],
        "pullbackP": p["pullbackP"],
        "slopeLB": p["slopeLB"],
        "gcMaxGapPct": float(p["gcMaxGapPct"]),
        "ma60MinSlope": p["ma60MinSlope"],
        "ma60SlopeDrop": p["ma60SlopeDrop"],
        "slStreakPause": p["slStreakPause"],
        "slStreakCooldownHours": p["slStreakCooldownHours"],
        "episodePullbackCap": p["episodePullbackCap"],
        "episodeTpDecayPct": p["episodeTpDecayPct"],
        "episodeTpFloorPct": p["episodeTpFloorPct"],
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
