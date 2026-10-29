"""
2차 T11 (결정 D3): 엔진 제어 요청 통로 — 엔진 프로세스 쪽 감시·실행.

신버전(tradebot-v2, 엔진 모듈 없음)이 `services/data/v2_control/<user>/req-<id>.json`(600)을 쓰면, 엔진 프로세스의
감시 스레드(scripts/tradebot_boot.py 가 데몬으로 띄움 — 엔진 스레드 밖)가 2초마다 읽어 실행하고
`res-<id>.json`(600)을 쓴다. 처리한 요청 파일은 지우고 결과는 사용자당 최근 50개만 남긴다.

규칙
- 한 번에 하나: 전역 잠금(_GLOBAL_LOCK). 모든 사용자 요청을 created_at 순으로 1건씩.
- 중복: 같은 id 결과 파일이 있으면 실행·알림 없이 요청 파일만 지움. 만료: now > min(expires_at, created_at+60초) → expired.
- 사용자 검사: 경로 폴더 이름 = 본문 user_id, 정규식 ^[A-Za-z0-9_]{1,32}$. 다르면 실행 0(user_mismatch).
- 예외 격리: 요청 하나의 예외는 error(code=exception) 결과, 루프는 계속. 루프 자체 예외는 로그 1줄 뒤 5초 쉬고 다시.
- 이 감시 스레드는 엔진 잠금(실행 잠금)을 잡지 않는다. 엔진이 돌면 core.engine_control 의 제어 큐에 넣고 기다린다
  (20초 안에 실행이 시작되지 않으면 취소 → engine_busy, 이미 시작됐으면 끝날 때까지 기다림).
- 요청 종류별 알림(S1): 모든 처리 결과를 텔레그램 1회(dedupe = 요청 id). 시도가 아닌 거절은
  (사용자, 종류, code) 60초에 1회(REJECT_NOTIFY_SEC). 주문·전환·정지 종류는 「직접 요청하지 않으셨다면
  운영자에게 알려 주세요」로 끝맺는다(신버전 침해 시 모르는 요청을 바로 알게).
- switch·revert·cancel_reservation·apply_params·ops_settings 는 T12~T14 가 register_handler 로 채운다(그 전에는 not_ready).
  2차 T12: engine/strategy_switch.install() 이 switch·revert·cancel_reservation 처리, 강제 매수 결과 뒤 처리
  (register_post_hook — 예약 중 사용자 강제 매수면 「예약 그대로」 안내), 훑기 뒤 tick(register_tick_hook — 예약 완료·
  기동 때 처리 중 행 복구)을 붙인다. install 은 scripts/tradebot_boot._control_thread 가 control_loop 앞에서 1회 부른다.
  결과 detail 의 note_text 는 결과 문구·알림 뒤에 붙이고, event_notified 면 요청 알림 대신 그 사건 알림 1회로 갈음한다.

재시작(restart_engine, F7·F11): 쉼 표식 → (엔진이 있으면) stop_engine → 옛 스레드 끝 대기(30초, 관리자 표에서 빠진
같은 이름 스레드 포함) → start_engine → 준비 신호 대기(180초). 실패면 _no_recover 표식을 남긴 뒤(1028-15 에서 자동
재시작을 지워 지금은 표식만 남음 — 1028-18 에서 다시 읽음) (엔진이 있으면) 정지. 알려진 한계는 계획 T11 절.

수정 1회차(검수 반영)
- 파일: 링크를 따라가지 않는다(core.safe_file — 임의 이름 임시 파일·O_NOFOLLOW 읽기·폴더 링크·권한 확인).
  형식 오류·사용자 불일치·링크·권한 이상은 운영자 CRITICAL 1회(폴더 단위, 1시간).
- 한 번 훑을 때 사용자마다 가장 오래된 1건만(나머지는 다음 회차). 강제 매수·강제 매도·엔진 정지는 같은 종류
  30초 간격 — 그 안의 요청은 too_frequent(알림 1회).
- 엔진 시작은 몇 초(START_CHECK_SEC) 스레드 생존을 확인한다. 엔진 안 실행은 시작 뒤 120초 상한(result_unknown).
- 이 감시 스레드는 엔진 폴더를 만들지 않는다(신버전이 첫 요청 때 700 으로 만든다 — 계획 메모).

수정 2회차(verifier 2차 N1~N7)
- 누적 상한: 강제 주문(매수·매도 합)·엔진 시작/정지(합) 각각 사용자당 1시간 HOURLY_CAP(6)건. 넘으면 그 묶음을 1시간
  멈춘다(control_suspended, 운영자 CRITICAL 1회). 엔진 정지는 멈춤 중에도 실행한다(매매를 멈추는 안전한 쪽).
  상태는 이 프로세스 메모리 — tradebot 재시작 때 비워진다(계획 메모).
- 폴더는 링크를 따라가지 않고 열어(fd) 소유자·700 을 확인하고, 다르면 고치지 않고 거부한다. 그 뒤 읽기·쓰기·지우기는
  모두 그 fd 기준 — 확인 뒤 경로를 링크로 바꿔치기해도 바깥을 건드리지 않는다.
- 30초 창·시간당 수는 실제로 주문(또는 시작·정지)을 시도한 결과에만 센다(ATTEMPTED). 잔고 없음 같은 사전 거절은 세지 않는다.

수정 3회차(verifier 3차)
- 실행 중 예외도 시도로 센 뒤 다시 던진다(결과는 exception).
- 사용자당 한 번 훑을 때 요청은 이름순 앞 MAX_REQ_FILES(10)개만, 넘치면 지우고 운영자 알림. 1개 8KB.
- 강제 매도도 멈춤 중 실행(30초 창은 유지). 모든 종류가 묶음에 든다(switch·revert = engine, 나머지 other).
- 멈춤 문구는 묶음별(control_suspended_order/engine/other).

수정 4회차(verifier 4차)
- 시도가 아닌 거절 결과 알림은 (사용자, 종류, code) 60초에 1회. 시도한 결과는 요청마다.
- 넘친·깨진·링크·id 오류 요청 경고 로그는 같은 폴더·같은 사유 60초에 1줄.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Optional
from zoneinfo import ZoneInfo

from collections import deque

from core.safe_file import (atomic_write_600 as _safe_write, check_dir_fd, is_symlink_at, open_dir_nofollow,
                            read_nofollow)

logger = logging.getLogger(__name__)

_KST = ZoneInfo("Asia/Seoul")
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "services" / "data"
CONTROL_DIRNAME = "v2_control"
REST_MARK_FILE = ".engine_restart.json"

POLL_SEC = 2.0
LOOP_ERROR_SLEEP_SEC = 5.0
REQUEST_TTL_SEC = 60
QUEUE_WAIT_SEC = 20.0
OLD_THREAD_WAIT_SEC = 30.0
READY_WAIT_SEC = 180.0      # 추정값(계획 12절 21번) — 1-2 실측으로 조정
REST_MARK_SEC = 300
KEEP_RESULTS = 50
WAIT_STEP_SEC = 0.05
MIN_INTERVAL_SEC = 30.0     # 강제 매수·강제 매도·엔진 정지: 같은 사용자·같은 종류 최소 간격
RATE_KINDS = ("force_buy", "force_sell", "engine_stop")
START_CHECK_SEC = 4.0       # 엔진 시작 뒤 스레드 생존 확인(그 안에 끝나면 start_failed)
EXEC_WAIT_SEC = 120.0       # 엔진이 실행을 시작한 뒤 결과를 기다리는 상한(넘으면 result_unknown)
MAX_REQ_BYTES = 8 * 1024     # 요청 1개 상한 — 신버전은 값(payload) 4096바이트 + 머리 약 300바이트까지만 쓴다
MAX_REQ_FILES = 10           # 사용자당 한 번 훑을 때 보는 요청 수(이름순 앞) — 넘치는 것은 지우고 운영자 알림
REJECT_NOTIFY_SEC = 60.0     # 시도가 아닌 거절 결과 알림: (사용자, 종류, code) 60초에 1회
WARN_LOG_SEC = 60.0          # 넘친·깨진·링크 요청 파일 경고 로그: 같은 폴더·같은 사유 60초에 1줄
BAD_ALERT_TTL_SEC = 3600   # 형식 오류 요청 운영자 알림: 폴더당 1시간에 1회
HOURLY_CAP = 6              # 묶음별 사용자당 1시간 실행(시도) 상한 — 운영 관찰 뒤 조정 가능
CAP_WINDOW_SEC = 3600.0
SUSPEND_SEC = 3600.0        # 상한을 넘으면 그 묶음을 멈추는 시간
CAP_GROUPS = {"force_buy": "order", "force_sell": "order",
              "engine_start": "engine", "engine_stop": "engine", "switch": "engine", "revert": "engine"}
DEFAULT_CAP_GROUP = "other"  # 위에 없는 종류(예약 취소·설정 적용·운용 설정 등)도 상한을 받는다
# 멈춤 중에도 실행(30초 창은 그대로): 엔진 정지·강제 매도 = 매매를 멈추거나 보유를 줄이는 쪽
ALWAYS_RUN_KINDS = ("engine_stop", "force_sell")
# 실제로 업비트 주문(또는 엔진 시작·정지)을 시도한 결과 code — 30초 창·시간당 수에 센다
ATTEMPTED_CODES = ("ok", "order_failed", "result_unknown", "exception", "started", "stopped", "start_failed",
                   "reserved", "switch_failed",   # 2차 T12: 예약·전환 실패도 엔진 상태를 바꾼 시도
                   "apply_failed")                # 2차 T13: 설정 적용 실패(재시작 시도 포함)

USER_RE = re.compile(r"^[A-Za-z0-9_]{1,32}$")
ID_RE = re.compile(r"^[0-9]{14}-[0-9a-f]{8}$")
MODES = ("TEST", "LIVE")

KINDS = ("engine_start", "engine_stop", "switch", "revert", "cancel_reservation",
         "apply_params", "force_buy", "force_sell", "ops_settings")
# 결과와 관계없이 「모르는 요청이면 알려 달라」를 붙이는 종류(S1)
SENSITIVE_KINDS = ("force_buy", "force_sell", "switch", "revert", "engine_stop")

KIND_LABEL = {
    "engine_start": "엔진 시작",
    "engine_stop": "엔진 정지",
    "switch": "백테스터 규칙으로 전환",
    "revert": "기존 전략으로 복귀",
    "cancel_reservation": "예약 취소",
    "apply_params": "설정 적용",
    "force_buy": "강제 매수",
    "force_sell": "강제 매도",
    "ops_settings": "운용 설정 저장",
}
STATUS_LABEL = {"done": "완료", "rejected": "처리 안 함", "expired": "시간 초과", "error": "실패"}
# 결과 code → 투자자용 한 줄(결과 파일 message·알림 본문). 내부 코드·영문 상태는 쓰지 않는다.
CODE_TEXT = {
    "ok": "요청대로 처리했습니다.",
    "started": "엔진을 시작했습니다.",
    "stopped": "엔진을 멈췄습니다.",
    "already_running": "엔진이 이미 돌고 있습니다.",
    "not_running": "엔진이 멈춰 있어 할 일이 없었습니다.",
    "mode_conflict": "다른 모드(모의/실계좌) 엔진이 돌고 있어 처리하지 않았습니다.",
    "start_failed": "엔진을 시작하지 못했습니다.",
    "engine_busy": "엔진이 바빠(시작 준비 중 등) 처리하지 않았습니다. 주문은 나가지 않았습니다.",
    "engine_required": "새 전략 강제 매수는 엔진이 돌 때만 할 수 있습니다.",
    "order_failed": "주문을 내지 못했습니다(잔고·보유 수량·거래소 응답을 확인해 주세요).",
    "params_missing": "설정 파일을 읽지 못해 처리하지 않았습니다.",
    "fill_pending": "앞 매수 주문의 체결을 기다리는 중이라 처리하지 않았습니다.",
    "desync": "보유 수량 맞춤 중이라 추가 매수를 하지 않았습니다.",
    "splits_full": "분할 매수 횟수를 모두 채워 더 사지 않았습니다.",
    "no_price": "기준 가격이 없어 처리하지 않았습니다.",
    "split_krw_short": "원화 잔고가 모자라 매수하지 않았습니다.",
    "split_krw_unknown": "원화 잔고를 읽지 못해 매수하지 않았습니다.",
    "split_below_min": "1회 매수 금액이 최소 주문금액보다 작아 매수하지 않았습니다.",
    "split_no_capital": "운용자산이 정해지지 않아 매수하지 않았습니다.",
    "split_order_cooldown": "직전 주문 실패 뒤 쉬는 중이라 매수하지 않았습니다.",
    "not_ready": "아직 열리지 않은 기능입니다.",
    "expired": "요청 뒤 1분이 지나 처리하지 않았습니다(시간이 지나 무효).",
    "user_mismatch": "요청한 계정이 맞지 않아 처리하지 않았습니다.",
    "bad_request": "요청 형식이 맞지 않아 처리하지 않았습니다.",
    "old_thread_alive": "엔진 정지가 끝나지 않아 재시작을 멈췄습니다.",
    "start_not_ready": "엔진이 매매 준비를 끝내지 못했습니다.",
    "old_engine_alive": "앞 엔진이 아직 멈추는 중이라 시작하지 않았습니다.",
    "too_frequent": "같은 요청이 30초 안에 다시 들어와 처리하지 않았습니다(겹친 주문 방지). 30초 뒤 다시 눌러 주세요.",
    "control_suspended": "요청이 1시간에 6번을 넘어 1시간 동안 받지 않습니다. "
                         "직접 요청하신 것이 아니라면 운영자에게 바로 알려 주세요.",
    "control_suspended_order": "강제 매수·강제 매도 요청이 합쳐서 1시간에 6번을 넘어 1시간 동안 강제 매수를 받지 않습니다. "
                               "강제 매도는 계속 할 수 있습니다. 직접 요청하신 것이 아니라면 운영자에게 바로 알려 주세요.",
    "control_suspended_engine": "엔진 시작·정지와 전략 전환·복귀 요청이 합쳐서 1시간에 6번을 넘어 1시간 동안 엔진 시작과 "
                                "전략 전환·복귀를 받지 않습니다. 엔진 정지는 계속 할 수 있습니다. "
                                "직접 요청하신 것이 아니라면 운영자에게 바로 알려 주세요.",
    "control_suspended_other": "예약 취소·설정 적용·운용 설정 저장 요청이 합쳐서 1시간에 6번을 넘어 1시간 동안 받지 않습니다. "
                               "직접 요청하신 것이 아니라면 운영자에게 바로 알려 주세요.",
    "no_balance": "보유 코인 또는 원화 잔고가 없어 주문하지 않았습니다.",
    "result_unknown": "엔진이 2분 안에 결과를 알려 주지 않아 처리 결과를 확인하지 못했습니다.",
    "exception": "처리 중 오류가 났습니다.",
    "unsupported_kind": "처리할 수 없는 요청입니다.",
    # 2차 T12 (전환·예약·복귀·예약 취소)
    "reserved": "예약했습니다. 지금 보유분(또는 체결 대기 매수)을 지금 전략이 매도까지 관리한 뒤 바뀝니다. "
                "예약 중에는 봇이 추가로 사지 않습니다.",
    "switch_failed": "전략을 바꾸지 못해 기존 전략으로 계속합니다. 운영자가 확인합니다.",
    "live_not_supported": "새 전략 전환·복귀는 아직 실계좌(LIVE)에서 할 수 없어 처리하지 않았습니다. 엔진은 그대로입니다.",
    "already_reserved": "이미 전환(또는 복귀) 예약이 있어 처리하지 않았습니다.",
    "already_pullback": "이미 새 전략으로 운용 중이라 처리하지 않았습니다.",
    "not_pullback": "지금은 새 전략 운용 중이 아니라 돌아갈 것이 없습니다.",
    "saved_invalid": "저장한 새 전략 설정을 읽지 못했거나 값이 맞지 않아 처리하지 않았습니다.",
    "sha_mismatch": "다른 저장이 끼어들었습니다. 다시 저장해 주세요.",
    "choose_strategy": "돌아갈 전략 기록이 없습니다. EMA 또는 MACD 를 골라 주세요.",
    "no_reservation": "취소할 예약이 없습니다.",
    "reservation_unknown": "예약 상태를 읽지 못해 처리하지 않았습니다.",
    "switch_table_missing": "전환 기록 표가 없어 처리하지 않았습니다(운영자 확인).",
    # 2차 T13 (설정 적용 — 사용자 결정 1029-05). 보유 중 거절 2개는 투자자 체감 변경(배포 때 통보).
    "holding_interval_change": "보유 중에는 봉 단위를 바꿀 수 없습니다 — 매도 뒤 다시 적용해 주세요",
    "holding_splits_increase": "보유 중에는 분할 매수 횟수를 늘릴 수 없습니다 — 매도 뒤 다시 적용해 주세요",
    "source_not_upbit": "바이낸스 데이터로 시험한 설정은 참고용이라 적용하지 않았습니다. "
                        "업비트 데이터로 다시 시험해 저장해 주세요.",
    "apply_not_pullback": "지금은 새 전략으로 운용 중이 아니라 적용하지 않았습니다. "
                          "먼저 백테스터 규칙으로 전환해 주세요.",
    "invalid_ticker": "종목 이름이 맞지 않아 적용하지 않았습니다.",
    "apply_live_not_supported": "새 전략 설정 적용은 아직 실계좌(LIVE)에서 할 수 없습니다. 모의(TEST)에서만 할 수 있습니다.",
    "apply_failed": "설정을 적용하지 못해 이전 설정으로 계속합니다. 운영자가 확인합니다.",
    # 2차 T14 fix 2: 「시간 밖에도 매도」는 시간 밖 손절 처리 결정 전까지 바꿀 수 없다
    "sell_off_locked": "「시간 밖에도 매도」는 아직 바꿀 수 없어 처리하지 않았습니다.",
}
NO_ACTION_TEXT = "투자자님이 따로 하실 일은 없습니다."   # core.strategy_engine.NO_ACTION_TEXT 와 같은 글
UNKNOWN_REQUEST_TEXT = "직접 요청하지 않으셨다면 운영자에게 바로 알려 주세요."
BAD_REQUEST_TITLE = "🚨 신버전 대시보드 요청 이상 — 운영자 확인"
BAD_REQUEST_BODY = ("신버전 대시보드 요청 폴더에서 형식이 맞지 않거나 계정이 다른 요청을 찾아 처리하지 않았습니다. "
                    "주문은 나가지 않았습니다.\n누군가 요청을 바꿨을 수 있어 운영자가 서버를 확인합니다.\n"
                    f"{NO_ACTION_TEXT}")
SUSPEND_TITLE = "🚨 신버전 대시보드 제어 요청 1시간 멈춤 — 운영자 확인"
# 묶음별 운영자 CRITICAL 본문(멈춤을 건 순간 1회) — 화면 결과 문구와 같은 글
SUSPEND_BODY = {g: "신버전 대시보드에서 " + CODE_TEXT[f"control_suspended_{g}"] for g in ("order", "engine", "other")}


def _group_of(kind) -> str:
    return CAP_GROUPS.get(kind, DEFAULT_CAP_GROUP)


def _kst_iso(t: float) -> str:
    return datetime.fromtimestamp(t, _KST).isoformat()


def _parse_ts(v) -> Optional[float]:
    try:
        dt = datetime.fromisoformat(str(v))
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        return None
    return dt.timestamp()


def _atomic_write_600(path, body: dict, dir_fd: Optional[int] = None) -> None:
    """같은 폴더 임의 이름 임시 파일(O_EXCL 0o600, fchmod 600 — 엔진 UMask 0022 대비, F21) → os.replace.
    고정 임시 이름을 쓰지 않아 미리 둔 링크를 따라가지 않는다(수정 1회차). dir_fd 면 열린 폴더 기준(수정 2회차)."""
    _safe_write(path, json.dumps(body, ensure_ascii=False), dir_fd=dir_fd)


class _UserDir:
    """열린 사용자 폴더(fd 기준). name 은 폴더 이름(= 사용자)."""

    def __init__(self, name: str, fd: int):
        self.name, self.fd = name, fd


def _result(status: str, code: str, detail: Optional[dict] = None) -> Dict[str, Any]:
    return {"status": status, "code": code, "detail": dict(detail or {})}


# ---------------------------------------------------------------- 엔진이 없을 때 쓰는 읽기 (시험에서 바꿈)
def _active_strategy(user_id: str) -> Optional[str]:
    """엔진이 없을 때 강제 매매 전략 — 엔진 기동과 같은 규칙(_decide_strategy_type, 세션 없음)."""
    from engine.engine_manager import _decide_strategy_type
    return _decide_strategy_type(user_id, None)


def _ticker_and_interval(user_id: str, strategy: str):
    """(종목, 봉 초) — PULLBACK 은 적용본만(엔진이 쓰는 값 — 저장본은 아직 적용 전), EMA·MACD 는 그 전략 설정 파일.
    못 읽으면 None(params_missing)."""
    if strategy == "PULLBACK":
        from engine import pullback_params as pbp
        try:
            with open(pbp.applied_path(user_id), "r", encoding="utf-8") as f:
                d = json.load(f)
            t, iv = d.get("ticker"), str(d.get("interval") or "")
            m = re.fullmatch(r"minute(\d+)", iv)
            if isinstance(t, str) and t and m:
                return t, int(m.group(1)) * 60
        except Exception:
            pass
        return None
    from config import PARAMS_JSON_FILENAME
    from engine.params import load_params
    p = load_params(f"{user_id}_{PARAMS_JSON_FILENAME}", strategy_type=strategy)
    if p is None:
        return None
    return p.upbit_ticker, int(getattr(p, "interval_sec", 60) or 60)


def _default_trader(user_id: str, mode: str, strategy: str):
    """구버전 강제 매매와 같은 새 trader(엔진 잠금 없음). EMA·MACD 는 그 전략 order_ratio."""
    from config import PARAMS_JSON_FILENAME
    from core.trader import UpbitTrader
    risk = 1.0
    if strategy != "PULLBACK":
        from engine.params import load_params
        p = load_params(f"{user_id}_{PARAMS_JSON_FILENAME}", strategy_type=strategy)
        if p is not None:
            risk = p.order_ratio
    return UpbitTrader(user_id, risk_pct=risk, test_mode=(mode != "LIVE"), strategy_type=strategy)


def _default_force_sell(user_id, trader, ticker, **kw):
    from services.trading_control import force_liquidate
    return force_liquidate(user_id, trader, ticker, **kw)


def _default_force_buy(user_id, trader, ticker, **kw):
    from services.trading_control import force_buy_in
    return force_buy_in(user_id, trader, ticker, **kw)


def _default_notify(level, title, body, *, dedupe_key=None, dedupe_ttl=3600):
    try:
        from services.notifier import send
        return send(level, title, body, dedupe_key=dedupe_key, dedupe_ttl=dedupe_ttl)
    except Exception as e:
        logger.warning(f"[CONTROL] 알림 실패(무해) | {type(e).__name__}")
        return False


def _default_manager():
    from engine.engine_manager import engine_manager
    return engine_manager


# 다음 Task(T12~T14)가 채우는 종류: kind → fn(controller, req) -> result dict
_EXTRA_HANDLERS: Dict[str, Callable] = {}


def register_handler(kind: str, fn: Callable) -> None:
    if kind not in KINDS:
        raise ValueError(kind)
    _EXTRA_HANDLERS[kind] = fn


# 2차 T12: 실행 결과 뒤 처리 fn(controller, req, result) -> result, 훑기 뒤 tick fn(controller)
_POST_HOOKS: list = []
_TICK_HOOKS: list = []


def register_post_hook(fn: Callable) -> None:
    if fn not in _POST_HOOKS:
        _POST_HOOKS.append(fn)


def register_tick_hook(fn: Callable) -> None:
    if fn not in _TICK_HOOKS:
        _TICK_HOOKS.append(fn)


def run_tick_hooks(controller) -> None:
    """control_loop 가 훑기 뒤 부른다. 갈고리 하나의 예외는 로그 1줄(다음 갈고리·다음 회차 계속)."""
    for fn in list(_TICK_HOOKS):
        try:
            fn(controller)
        except Exception as e:
            logger.error(f"[CONTROL] tick 예외(다음 회차) | {type(e).__name__}: {e}")


class Controller:
    _GLOBAL_LOCK = threading.Lock()   # 한 번에 하나(모든 Controller·사용자 공통)

    def __init__(self, base_dir=None, *, alive_dir=None, manager=None, notify=None, now=None, monotonic=None,
                 sleep=None, queue_wait=QUEUE_WAIT_SEC, old_thread_wait=OLD_THREAD_WAIT_SEC,
                 ready_wait=READY_WAIT_SEC, start_check=START_CHECK_SEC, exec_wait=EXEC_WAIT_SEC,
                 trader_factory=None, force_sell_fn=None, force_buy_fn=None):
        self.base_dir = Path(base_dir) if base_dir is not None else DATA_DIR / CONTROL_DIRNAME
        self.alive_dir = Path(alive_dir) if alive_dir is not None else DATA_DIR
        self._manager = manager
        self.notify = notify or _default_notify
        self.now = now or time.time
        self.mono = monotonic or time.monotonic
        self.sleep = sleep or time.sleep
        self.queue_wait = queue_wait
        self.old_thread_wait = old_thread_wait
        self.ready_wait = ready_wait
        self.start_check = start_check
        self.exec_wait = exec_wait
        self.trader_factory = trader_factory or _default_trader
        self.force_sell_fn = force_sell_fn or _default_force_sell
        self.force_buy_fn = force_buy_fn or _default_force_buy
        self._last_run: Dict[tuple, float] = {}       # (사용자, 종류) → 마지막 주문 시도 시각(mono) — RATE_KINDS
        self._reject_notified: Dict[tuple, float] = {}  # (사용자, 종류, code) → 거절 알림 시각(mono) — 수정 4회차
        self._warned: Dict[tuple, float] = {}           # (폴더, 사유) → 경고 로그 시각(mono) — 수정 4회차
        self._bad_alerted: Dict[str, float] = {}      # 폴더 dedupe 키 → 알림 시각(mono)
        # 수정 2회차(N1·N3): (사용자, 묶음) → 최근 1시간 시도 시각들 / 멈춤 끝 시각(mono). 프로세스 메모리(재시작 때 비움).
        self._cap_hist: Dict[tuple, deque] = {}
        self._suspended: Dict[tuple, float] = {}

    @property
    def manager(self):
        if self._manager is None:
            self._manager = _default_manager()
        return self._manager

    # ------------------------------------------------------------ 이상 요청 알림(운영자)
    def _bad(self, dirname: str, why: str) -> None:
        key = f"v2_control_bad:{dirname}"
        last = self._bad_alerted.get(key)
        if last is not None and self.mono() - last < BAD_ALERT_TTL_SEC:
            return
        self._bad_alerted[key] = self.mono()
        logger.critical(f"[CONTROL] 이상 요청 → 처리 안 함 | dir={dirname} why={why}")
        try:
            self.notify("CRITICAL", BAD_REQUEST_TITLE, BAD_REQUEST_BODY, dedupe_key=key, dedupe_ttl=BAD_ALERT_TTL_SEC)
        except Exception as e:
            logger.warning(f"[CONTROL] 알림 실패(무해) | {type(e).__name__}")

    def _warn(self, dirname: str, why: str, msg: str) -> None:
        """넘친·깨진·링크 요청 경고 로그 — 같은 폴더·같은 사유는 WARN_LOG_SEC 에 1줄(2초마다 훑어 저널이 차지 않게)."""
        k = (dirname, why)
        last = self._warned.get(k)
        if last is not None and self.mono() - last < WARN_LOG_SEC:
            return
        self._warned[k] = self.mono()
        logger.warning(msg)

    # ------------------------------------------------------------ 훑기 (모두 열린 폴더 fd 기준)
    def _open_checked(self, name, label: str, dir_fd: Optional[int] = None) -> Optional[int]:
        """폴더를 링크를 따라가지 않고 열고 소유자·700 확인. 없으면 None(조용히), 이상이면 알림 뒤 None."""
        try:
            fd = open_dir_nofollow(name, dir_fd=dir_fd)
        except FileNotFoundError:
            return None
        except OSError:
            self._bad(label, "symlink_or_not_dir")
            return None
        try:
            why = check_dir_fd(fd)
        except OSError:
            why = "stat_failed"
        if why:
            os.close(fd)
            self._bad(label, why)
            return None
        return fd

    def _user_dirs(self, base_fd: int):
        try:
            names = sorted(os.listdir(base_fd))
        except OSError:
            return []
        out = []
        for name in names:
            if not USER_RE.fullmatch(name):
                continue
            fd = self._open_checked(name, name, dir_fd=base_fd)
            if fd is not None:
                out.append(_UserDir(name, fd))
        return out

    def _load(self, name: str, dir_fd: int):
        """요청 dict 또는 None(깨짐·링크·일반 파일 아님·MAX_REQ_BYTES(8KB) 초과)."""
        raw = read_nofollow(name, MAX_REQ_BYTES, dir_fd=dir_fd)
        if raw is None:
            return None
        try:
            body = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError, RecursionError):
            return None
        return body if isinstance(body, dict) else None

    def _requests(self, d: _UserDir):
        """(파일 이름, 요청 dict) — 링크·깨진 파일은 지우고(링크는 링크 자체만) 운영자 알림."""
        try:
            names = sorted(os.listdir(d.fd))
        except OSError:
            return []
        reqs = [n for n in names if n.startswith("req-") and n.endswith(".json")]
        if len(reqs) > MAX_REQ_FILES:
            # 몰아 넣기 방지: 이름순 앞 MAX_REQ_FILES 개만 보고 나머지는 열지 않고 지운다(링크면 링크 자체만)
            self._warn(d.name, "too_many",
                       f"[CONTROL] 요청 파일 {len(reqs)}개 > {MAX_REQ_FILES} → 넘친 {len(reqs) - MAX_REQ_FILES}개 지움 "
                       f"| user_dir={d.name} (같은 사유 {WARN_LOG_SEC:.0f}초에 1줄)")
            for name in reqs[MAX_REQ_FILES:]:
                self._unlink(name, d)
            self._bad(d.name, "too_many")
            reqs = reqs[:MAX_REQ_FILES]
        out = []
        for name in reqs:
            if is_symlink_at(name, d.fd):
                self._warn(d.name, "symlink_req",
                           f"[CONTROL] 요청 파일이 링크 → 지움(따라가지 않음) | user_dir={d.name} file={name}")
                self._unlink(name, d)
                self._bad(d.name, "symlink_req")
                continue
            body = self._load(name, d.fd)
            if body is None:
                self._warn(d.name, "broken", f"[CONTROL] 요청 파일 형식 오류 → 지움 | user_dir={d.name} file={name}")
                self._unlink(name, d)
                self._bad(d.name, "broken")
                continue
            out.append((name, body))
        return out

    def scan_once(self) -> list:
        """요청을 created_at 순으로 1건씩 처리. 한 번에 사용자마다 1건(나머지는 다음 회차). 처리한 결과 목록."""
        out = []
        with self._GLOBAL_LOCK:
            base_fd = self._open_checked(self.base_dir, self.base_dir.name)
            if base_fd is None:
                return out
            dirs = []
            try:
                dirs = self._user_dirs(base_fd)
                pending = []
                for d in dirs:
                    for name, body in self._requests(d):
                        created = _parse_ts(body.get("created_at"))
                        pending.append((created if created is not None else 0.0, name, d, body))
                pending.sort(key=lambda x: (x[0], x[1]))
                done_users = set()
                for _, name, d, body in pending:
                    if d.name in done_users:
                        continue
                    r = self._process(d, name, body)
                    if r is not None:
                        out.append(r)
                        done_users.add(d.name)
            finally:
                for d in dirs:
                    os.close(d.fd)
                os.close(base_fd)
        return out

    @staticmethod
    def _unlink(name: str, d: _UserDir) -> None:
        try:
            os.unlink(name, dir_fd=d.fd)
        except FileNotFoundError:
            pass
        except OSError as e:
            logger.warning(f"[CONTROL] 요청 파일 지우기 실패 | {name} {type(e).__name__}")

    def _process(self, d: _UserDir, name: str, body: dict):
        rid = body.get("id")
        if not isinstance(rid, str) or not ID_RE.fullmatch(rid):
            self._warn(d.name, "bad_id", f"[CONTROL] 요청 id 형식 오류 → 지움 | user_dir={d.name} file={name}")
            self._unlink(name, d)
            self._bad(d.name, "bad_id")
            return None
        try:
            os.stat(f"res-{rid}.json", dir_fd=d.fd, follow_symlinks=False)
            exists = True
        except FileNotFoundError:
            exists = False
        except OSError:
            exists = True
        if exists:
            logger.info(f"[CONTROL] 같은 id 결과 있음 → 실행 안 함 | id={rid}")
            self._unlink(name, d)
            return None
        kind = body.get("kind")
        try:
            result = self._validate(d, body)
            if result is None:
                result = self._rate_checked(d.name, kind, body)
        except Exception as e:
            logger.error(f"[CONTROL] 요청 실행 예외 | id={rid} kind={kind} | {type(e).__name__}: {e}")
            result = _result("error", "exception", {"error": type(e).__name__})
        if result.get("code") == "user_mismatch":
            self._bad(d.name, "user_mismatch")
        self._finish(d, name, rid, kind, body, result)
        return result

    # ------------------------------------------------------------ 간격·누적 상한
    def _cap_count(self, k: tuple) -> int:
        h = self._cap_hist.get(k)
        if not h:
            return 0
        now = self.mono()
        while h and now - h[0] >= CAP_WINDOW_SEC:
            h.popleft()
        return len(h)

    def _suspend(self, user: str, group: str) -> None:
        k = (user, group)
        self._suspended[k] = self.mono() + SUSPEND_SEC
        logger.critical(f"[CONTROL] 누적 상한 {HOURLY_CAP}/시간 넘음 → {SUSPEND_SEC / 60:.0f}분 멈춤 | user={user} group={group}")
        try:
            self.notify("CRITICAL", SUSPEND_TITLE, SUSPEND_BODY.get(group, SUSPEND_BODY[DEFAULT_CAP_GROUP]),
                        dedupe_key=f"v2_control_suspend:{user}:{group}", dedupe_ttl=int(SUSPEND_SEC))
        except Exception as e:
            logger.warning(f"[CONTROL] 알림 실패(무해) | {type(e).__name__}")

    def _rate_checked(self, user: str, kind, body: dict):
        """(1) 묶음 누적 상한: 멈춤 중이거나 이번이 1시간 HOURLY_CAP 을 넘기면 control_suspended
        (엔진 정지·강제 매도는 실행). 모든 종류가 묶음에 든다(없으면 other).
        (2) 강제 매수·강제 매도·엔진 정지: 같은 사용자·같은 종류 MIN_INTERVAL_SEC 안이면 too_frequent.
        둘 다 실제로 시도한 결과(ATTEMPTED_CODES)만 센다. 실행 중 예외도 시도로 센 뒤 다시 던진다
        (엔진이 없을 때 강제 매도는 주문을 낸 뒤 기록 단계에서 실패할 수 있음 — 수정 3회차)."""
        group = _group_of(kind)
        gk = (user, group)
        until = self._suspended.get(gk)
        if until is not None and self.mono() >= until:
            self._suspended.pop(gk, None)
            until = None
        if until is None and self._cap_count(gk) >= HOURLY_CAP:
            self._suspend(user, group)
            until = self._suspended[gk]
        if until is not None and kind not in ALWAYS_RUN_KINDS:
            return _result("rejected", "control_suspended", {"group": group})
        if kind in RATE_KINDS:
            last = self._last_run.get((user, kind))
            if last is not None and self.mono() - last < MIN_INTERVAL_SEC:
                return _result("rejected", "too_frequent",
                               {"wait_sec": round(MIN_INTERVAL_SEC - (self.mono() - last), 1)})
        try:
            result = self.execute(body)
        except BaseException:
            self._count_attempt(user, kind, gk)
            raise
        if result.get("code") in ATTEMPTED_CODES:
            self._count_attempt(user, kind, gk)
        return result

    def _count_attempt(self, user: str, kind, gk: tuple) -> None:
        if kind in RATE_KINDS:
            self._last_run[(user, kind)] = self.mono()
        self._cap_hist.setdefault(gk, deque()).append(self.mono())

    def _validate(self, d: _UserDir, body: dict):
        user = body.get("user_id")
        if user != d.name or not USER_RE.fullmatch(d.name):
            logger.warning(f"[CONTROL] 사용자 불일치 → 실행 안 함 | dir={d.name} body={str(user)[:40]!r}")
            return _result("rejected", "user_mismatch")
        if body.get("kind") not in KINDS or body.get("mode") not in MODES \
                or not isinstance(body.get("payload", {}), dict) or body.get("v") != 1:
            return _result("rejected", "bad_request")
        created = _parse_ts(body.get("created_at"))
        expires = _parse_ts(body.get("expires_at"))
        if created is None or expires is None:
            return _result("rejected", "bad_request")
        if self.now() > min(expires, created + REQUEST_TTL_SEC):
            return _result("expired", "expired")
        return None

    def _finish(self, d: _UserDir, name: str, rid: str, kind, body: dict, result: dict) -> None:
        status, code = result.get("status"), result.get("code")
        text_key = code
        if code == "control_suspended":
            text_key = f"control_suspended_{(result.get('detail') or {}).get('group', DEFAULT_CAP_GROUP)}"
        detail = result.get("detail") or {}
        note_text = detail.get("note_text") if isinstance(detail.get("note_text"), str) else None
        message = CODE_TEXT.get(text_key, CODE_TEXT.get(code, CODE_TEXT["exception"]))
        if note_text:
            message = f"{message} {note_text}"      # 2차 T12: 예약 중 강제 매수 「예약 그대로」 안내 등
        res = {"id": rid, "status": status, "code": code, "message": message,
               "at": _kst_iso(self.now()), "detail": detail}
        try:
            _atomic_write_600(f"res-{rid}.json", res, dir_fd=d.fd)
        except Exception as e:
            logger.error(f"[CONTROL] 결과 파일 쓰기 실패 | id={rid} | {type(e).__name__}")
        self._unlink(name, d)
        self._prune(d)
        logger.info(f"[CONTROL] 처리 | id={rid} user={d.name} kind={kind} mode={body.get('mode')} "
                    f"status={status} code={code}")
        if kind not in KINDS or code in ("user_mismatch", "control_suspended"):
            return                           # 멈춤은 운영자 CRITICAL 1회로 갈음(요청마다 알리지 않음)
        if detail.get("event_notified"):
            return                           # 2차 T12: 전환·예약·복귀·취소 사건 알림 1회로 갈음(텔레그램 1회)
        if code not in ATTEMPTED_CODES:
            # 시도가 아닌 거절(잔고 없음·모드 다름·too_frequent 등)은 (사용자, 종류, code) 60초에 1회 — 수정 4회차.
            # 시도한 결과(ok·order_failed·exception·result_unknown·started·stopped·start_failed)는 요청마다.
            k = (d.name, kind, code)
            last = self._reject_notified.get(k)
            if last is not None and self.mono() - last < REJECT_NOTIFY_SEC:
                return
            self._reject_notified[k] = self.mono()
        self._notify(rid, kind, status, code, note_text)

    def _prune(self, d: _UserDir) -> None:
        try:
            files = []
            for name in os.listdir(d.fd):
                if name.startswith("res-") and name.endswith(".json"):
                    st = os.stat(name, dir_fd=d.fd, follow_symlinks=False)
                    files.append((st.st_mtime_ns, name))
        except OSError:
            return
        files.sort()
        for _, name in files[:-KEEP_RESULTS] if len(files) > KEEP_RESULTS else []:
            self._unlink(name, d)

    def _notify(self, rid: str, kind: str, status: str, code: str, note_text: Optional[str] = None) -> None:
        label = KIND_LABEL.get(kind, "요청")
        title = f"📨 신버전 대시보드 요청 — {label}: {STATUS_LABEL.get(status, '실패')}"
        lines = [f"신버전 대시보드에서 들어온 「{label}」 요청을 처리했습니다.",
                 CODE_TEXT.get(code, CODE_TEXT["exception"])]
        if note_text:
            lines.append(note_text)
        if status == "error":
            lines.append("운영자가 확인합니다.")
        lines.append(UNKNOWN_REQUEST_TEXT if kind in SENSITIVE_KINDS else NO_ACTION_TEXT)
        level = "WARNING" if (kind in SENSITIVE_KINDS or status == "error") else "INFO"
        try:
            self.notify(level, title, "\n".join(lines), dedupe_key=f"v2_control:{rid}", dedupe_ttl=86400)
        except Exception as e:
            logger.warning(f"[CONTROL] 알림 실패(무해) | {type(e).__name__}")

    # ------------------------------------------------------------ 실행
    def execute(self, req: dict) -> Dict[str, Any]:
        kind = req.get("kind")
        fn = {
            "engine_start": self._engine_start,
            "engine_stop": self._engine_stop,
            "force_buy": self._force,
            "force_sell": self._force,
        }.get(kind)
        if fn is not None:
            return self._post(req, fn(req))
        extra = _EXTRA_HANDLERS.get(kind)
        if extra is not None:
            return self._post(req, extra(self, req))
        if kind in KINDS:
            return _result("rejected", "not_ready")
        return _result("rejected", "unsupported_kind")

    def _post(self, req: dict, result: Dict[str, Any]) -> Dict[str, Any]:
        """2차 T12: 결과 뒤 처리 갈고리(없으면 그대로). 갈고리 예외는 결과를 바꾸지 않는다(주문은 이미 끝남)."""
        for fn in list(_POST_HOOKS):
            try:
                result = fn(self, req, result) or result
            except Exception as e:
                logger.warning(f"[CONTROL] 결과 뒤 처리 예외(결과 그대로) | {type(e).__name__}")
        return result

    @staticmethod
    def _stale_threads(user: str) -> list:
        """관리자 표와 상관없이 살아 있는 이 사용자의 엔진·매매 루프 스레드(이름이 정확히 같은 것만).
        stop_engine 의 join 시간 초과 뒤 표에서는 빠졌지만 아직 도는 옛 스레드를 놓치지 않게(품질 4)."""
        names = {f"{pre}_{user}_{m}" for pre in ("engine_runner", "run_live_loop") for m in MODES}
        return [t for t in threading.enumerate() if t.name in names and t.is_alive()]

    def _thread_of(self, user: str):
        return (getattr(self.manager, "_threads", None) or {}).get(user)

    def _running_code(self, running: str, mode: str) -> Dict[str, Any]:
        return _result("rejected", "already_running" if running == mode else "mode_conflict", {"running": running})

    def _engine_start(self, req):
        user, mode = req["user_id"], req["mode"]
        running = self.manager.get_running_mode(user)
        if running is not None:
            return self._running_code(running, mode)
        if self._stale_threads(user):
            return _result("rejected", "old_engine_alive")
        ok = self.manager.start_engine(user, mode=mode)
        if not ok:
            running = self.manager.get_running_mode(user)
            return self._running_code(running, mode) if running is not None else _result("rejected", "start_failed")
        th = self._thread_of(user)
        t0 = self.mono()
        while self.mono() - t0 < self.start_check:
            if th is None or not th.is_alive():
                break
            self.sleep(0.2)
        if th is None or not th.is_alive():
            logger.error(f"[CONTROL] 엔진 시작 뒤 {self.start_check:.0f}초 안에 엔진 스레드가 끝남 | user={user} mode={mode}")
            return _result("error", "start_failed")
        return _result("done", "started")

    def _engine_stop(self, req):
        user, mode = req["user_id"], req["mode"]
        running = self.manager.get_running_mode(user)
        if running is None:
            return _result("rejected", "not_running")
        if running != mode:
            return _result("rejected", "mode_conflict", {"running": running})
        self.manager.stop_engine(user, mode=mode)
        return _result("done", "stopped")

    def _force(self, req):
        from core import engine_control as ec
        user, mode, kind = req["user_id"], req["mode"], req["kind"]
        running = self.manager.get_running_mode(user)
        if running is not None:
            if running != mode:
                return _result("rejected", "mode_conflict", {"running": running})
            engine = ec.running_engine(user)
            if engine is None:
                return _result("error", "engine_busy")
            return self._through_engine(engine, kind, req)
        # 엔진 없음 — 구버전 강제 매매와 같은 새 trader(엔진 잠금 없음). 전략은 엔진 기동 규칙과 같다.
        strategy = _active_strategy(user)
        if strategy == "PULLBACK" and kind == "force_buy":
            return _result("rejected", "engine_required")
        ti = _ticker_and_interval(user, strategy)
        if ti is None:
            return _result("rejected", "params_missing")
        ticker, interval_sec = ti
        trader = self.trader_factory(user, mode, strategy)
        if kind == "force_sell":
            msg = self.force_sell_fn(user, trader, ticker, interval_sec=interval_sec)
        else:
            msg = self.force_buy_fn(user, trader, ticker, interval_sec=interval_sec, strategy_type=strategy)
        r = ec._msg_result(msg, "order_failed")
        r["detail"]["engine"] = "absent"
        return r

    def _through_engine(self, engine, kind, req, queue_wait: Optional[float] = None):
        """엔진 제어 큐에 넣고 기다린다. 이 스레드는 엔진 잠금을 잡지 않는다.
        실행이 시작되기 전 queue_wait 초 → 취소(engine_busy). 시작 뒤에는 exec_wait 초까지(넘으면 result_unknown).
        queue_wait 인자: T12 감시 tick 의 보유 확인처럼 전역 잠금을 쥔 채 짧게만 기다릴 때(없으면 self.queue_wait)."""
        from core import engine_control as ec
        qwait = self.queue_wait if queue_wait is None else float(queue_wait)
        item = ec.ControlItem(kind, req.get("payload") or {}, req.get("id"))
        engine.control_queue.put(item)
        t0 = self.mono()
        while not item.done.is_set() and not item.started:
            if self.mono() - t0 >= qwait:
                if item.try_cancel():
                    logger.warning(f"[CONTROL] 엔진 응답 없음 {qwait:.0f}초 → 취소(주문 없음) | id={item.req_id}")
                    return _result("error", "engine_busy")
                break                    # 막 시작됨 — 끝날 때까지(늦은 이중 주문 없음)
            self.sleep(WAIT_STEP_SEC)
        t1 = self.mono()
        while not item.done.is_set():
            if self.mono() - t1 >= self.exec_wait:
                logger.critical(f"[CONTROL] 엔진 안 실행이 {self.exec_wait:.0f}초 넘게 끝나지 않음 → 결과 미확인 | "
                                f"id={item.req_id} kind={kind}")
                return _result("error", "result_unknown")
            self.sleep(WAIT_STEP_SEC)
        return item.result or _result("error", "exception")

    # ------------------------------------------------------------ 재시작
    def write_rest_mark(self, user: str) -> None:
        at = self.now()
        self.alive_dir.mkdir(parents=True, exist_ok=True)
        _atomic_write_600(self.alive_dir / REST_MARK_FILE, {"user": user, "at": at, "until": at + REST_MARK_SEC})

    def _engine_present(self, user: str, th=None) -> bool:
        """정지가 필요한 엔진이 있는가(없는 엔진을 정지하면 공용 LIVE 수가 깎인다 — 품질 2)."""
        if self.manager.get_running_mode(user) is not None:
            return True
        th = th if th is not None else self._thread_of(user)
        return th is not None and th.is_alive()

    def restart_engine(self, user: str, mode: str, strategy: Optional[str],
                       before_start: Optional[Callable[[], Optional[Dict[str, Any]]]] = None) -> Dict[str, Any]:
        """(1) 쉼 표식 (2) 엔진이 있으면 stop (3) 옛 스레드 끝 대기 30초 (4) start (5) 준비 신호 대기 180초.
        실패면 복구 금지 뒤 (엔진이 있으면) 정지. 시작이 이미 실행·다른 모드로 거부되면 끄지 않고 그 코드.
        2차 T13: before_start — 옛 스레드가 모두 끝난 뒤·start 앞에서 1회 부른다(엔진이 없는 틈 — 봉 단위 변경의
        pullback_state 행 정리). 결과 dict 를 돌려주면 시작하지 않고 그 결과로 끝낸다(엔진은 멈춘 채, 호출자가 되돌림)."""
        m = self.manager
        try:
            self.write_rest_mark(user)
        except Exception as e:
            logger.error(f"[CONTROL] 쉼 표식 쓰기 실패 | {type(e).__name__}")
        old = self._thread_of(user)
        if self._engine_present(user, old):
            m.stop_engine(user, mode=mode)
        t0 = self.mono()
        while True:
            alive = ([old] if old is not None and old.is_alive() else []) + self._stale_threads(user)
            if not alive:
                break
            if self.mono() - t0 >= self.old_thread_wait:
                logger.critical(f"[CONTROL] 옛 엔진 스레드가 {self.old_thread_wait:.0f}초 넘게 살아 있음 → 재시작 멈춤 | user={user}")
                try:
                    self.notify("CRITICAL", "🚨 엔진 정지가 끝나지 않아 재시작을 멈췄습니다 — 운영자 확인",
                                ("전략을 바꾸려고 엔진을 다시 시작하던 중, 앞 엔진이 멈추지 않아 새 엔진을 띄우지 않았습니다"
                                 "(엔진이 두 개 뜨지 않게).\n지금 새 매수는 멈춰 있습니다. 운영자가 확인합니다.\n"
                                 f"{NO_ACTION_TEXT}"),
                                dedupe_key=f"v2_control_old_thread:{user}", dedupe_ttl=600)
                except Exception:
                    pass
                return _result("error", "old_thread_alive")
            self.sleep(0.2)
        if before_start is not None:
            try:
                stop_res = before_start()
            except Exception as e:
                logger.error(f"[CONTROL] 시작 전 처리 예외 → 시작 안 함 | user={user} | {type(e).__name__}: {e}")
                stop_res = _result("error", "exception", {"error": type(e).__name__})
            if stop_res is not None:
                logger.warning(f"[CONTROL] 시작 전 처리가 멈춤 → 시작 안 함 | user={user} code={stop_res.get('code')}")
                return stop_res
        ok = m.start_engine(user, mode=mode, strategy=strategy)   # start_engine 이 _no_recover 를 지운다
        if not ok:
            running = m.get_running_mode(user)
            if running is not None:
                return self._running_code(running, mode)
            return self._fail_start(user, mode, "start_failed")
        ev = m._ready.get(user)
        th = self._thread_of(user)
        t0 = self.mono()
        while True:
            if ev is not None and ev.is_set():
                logger.info(f"[CONTROL] 재시작 완료(준비 신호) | user={user} mode={mode} strategy={strategy}")
                return _result("done", "ok", {"strategy": strategy})
            reason = getattr(ev, "fail_reason", None) if ev is not None else None
            if ev is None or reason or th is None or not th.is_alive() or self.mono() - t0 >= self.ready_wait:
                return self._fail_start(user, mode, "start_not_ready", reason or "")
            self.sleep(0.2)

    def _fail_start(self, user, mode, code, why=""):
        m = self.manager
        m._no_recover.add(user)            # 복구 래퍼가 다시 띄우지 않게 먼저 표시
        if self._engine_present(user):
            try:
                m.stop_engine(user, mode=mode)
            except Exception as e:
                logger.error(f"[CONTROL] 실패 뒤 정지 예외 | {type(e).__name__}")
        logger.error(f"[CONTROL] 재시작 실패 | user={user} code={code} why={why}")
        return _result("error", code, {"why": why} if why else {})


def restart_engine(user: str, mode: str, strategy: Optional[str], **kw) -> Dict[str, Any]:
    """감시 스레드의 재시작 단일 통로(T12 전환·복귀가 쓴다)."""
    return Controller(**kw).restart_engine(user, mode, strategy)


def control_loop(stop: Optional[threading.Event] = None, controller: Optional[Controller] = None,
                 wait: Optional[Callable[[float], bool]] = None) -> None:
    """엔진 프로세스 감시 스레드 본문: 2초마다 scan_once. 루프 예외는 로그 1줄 뒤 5초 쉬고 다시."""
    stop = stop or threading.Event()
    ctl = controller or Controller()
    wait = wait or stop.wait
    logger.info("[CONTROL] 신버전 요청 감시 시작 (2초 주기)")
    while not stop.is_set():
        try:
            ctl.scan_once()
            run_tick_hooks(ctl)          # 2차 T12: 예약 완료·기동 복구(갈고리가 없으면 아무 일 없음)
            delay = POLL_SEC
        except Exception as e:
            logger.error(f"[CONTROL] 감시 루프 예외 → {LOOP_ERROR_SLEEP_SEC:.0f}초 뒤 다시 | {type(e).__name__}: {e}")
            delay = LOOP_ERROR_SLEEP_SEC
        if wait(delay):
            break
