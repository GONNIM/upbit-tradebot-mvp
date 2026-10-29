"""신버전 서버의 업비트 공개 시세(캔들) 중계·보관 (결정 1026-23 2 가).

- 업비트 호출은 이 파일 한 곳, 주소 UPBIT_URL 하나뿐이다. 계좌·주문 API 와 인증 머리는 쓰지 않는다.
- 엔진·구버전과 같은 서버 IP 의 candle 그룹 한도(초당 10회)를 나눠 쓰고, 엔진에는 429·418 처리가 없다.
  그래서 엔진 보호 규칙을 지킨다: 수집은 서버 전체에서 동시에 1건, 초당 4회(미리 받기 1회) 상한
  (관측된 엔진 묶음 5회와 합쳐 9 ≤ 10 — 코드 상한 아님, 겹침을 줄이는 장치), 응답 Remaining-Req 의 sec 가 4 이하이면 다음 요청 전 1초 쉼,
  엔진 봉 경계 창 [경계−2초, 경계+20초) 안에서는 부르지 않고 창 끝까지 기다림(Task 4-0b),
  첫 429 → 600초 멈춤, 24시간 안 두 번째 429 → 418 과 같은 정지, 418 → 정지 파일(운영자가 지울 때까지,
  재시작 뒤에도 유지), 엔진 pid 가 바뀌면 그 자리에서 멈추고 300초 쉼.
  429 멈춤 끝 시각·마지막 429 시각은 .cooldown.json 에 남겨 재시작 뒤에도 이어 간다.
- 보관: <db.DATA_DIR>/v2_candles/<market>_<unit>.json (600). 경로는 호출 때마다 db.DATA_DIR 로 만든다.
- 보관 구간(covered = [처음, 끝) 밀리초)은 늘 한 덩어리다. 새 봉은 보관 끝에서 앞으로, 옛 봉은 보관 처음에서
  뒤로 받으므로 중간에 멈춰도 빈 곳이 생기지 않는다(체결 없는 분은 업비트가 봉을 만들지 않아,
  봉 사이 간격만으로는 「받지 않은 곳」을 가릴 수 없기 때문).
- 시각: candle_date_time_utc 에 Z 를 붙여 UTC 로 읽는다(Issue #2). 봉 t 는 UTC 밀리초.
"""
import asyncio
import json
import logging
import math
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

import tornado.httpclient

from utils import v2_entry_token as et
from v2 import db
from v2.status import engine_alive_running

UPBIT_URL = "https://api.upbit.com/v1/candles/minutes/{unit}"
UNITS = (1, 3, 5, 15, 60, 240)
MAX_DAYS = 30
PER_REQ = 200               # 업비트 1회 최대 개수
INLINE_MAX_REQ = 2          # 이 횟수 안이면 처리기 안에서 바로 받는다
OVERLAP = 2                 # 새 봉을 받을 때 겹쳐 다시 받는 보관 마지막 봉 수(Issue #8)
USER_RATE = 4.0             # 회/초 — 관측 엔진 묶음 5회와 합쳐 9 ≤ 10, 보장 아님 (Task 4-0b)
PREFETCH_RATE = 1.0
LOW_SEC = 4                 # Remaining-Req sec 가 이 값 이하이면 1초 쉼
COOLDOWN_429 = 600          # 첫 429 → 10분 멈춤
HALT_429_WITHIN = 86_400    # 이 초 안에 두 번째 429 → 418 과 같은 정지
COOLDOWN_PID = 300
ENGINE_WINDOW_BEFORE = 2    # 엔진 봉 경계 앞 이 초부터
ENGINE_WINDOW_AFTER = 20    # 경계 뒤 이 초까지 업비트를 부르지 않는다(엔진 확정 조회·재판정 묶음)
PREFETCH_DELAY = 300        # v2 기동 뒤 미리 받기 시작까지
PREFETCH_EVERY = 600       # 처리기 안 2회 요청(1분봉 약 6시간치)이 그 사이 빈 곳을 덮는다
KEEP_RECENT = 3             # 미리 받기 대상 밖 보관 파일 수
MAX_TOTAL_BYTES = 30 * 1024 * 1024
STORE_DIR = "v2_candles"
HALT_FILE = ".halt.json"
COOLDOWN_FILE = ".cooldown.json"
ALIVE_FILE = ".engine_alive.json"
REST_MARK_FILE = ".engine_restart.json"   # 2차 T11: 엔진 재시작 쉼 표식(엔진 감시 스레드가 stop 전에 씀)
MIN_MS = 60_000
DAY_MS = 86_400_000

_MARKET_RE = re.compile(r"^KRW-[A-Z0-9]{1,15}$")
_STORE_RE = re.compile(r"^(KRW-[A-Z0-9]{1,15})_([0-9]+)\.json$")
_DIGITS = re.compile(r"[0-9]{1,4}")
_SEC_RE = re.compile(r"\bsec=([0-9]+)")
_MINUTE_RE = re.compile(r"minute([0-9]+)")

log = logging.getLogger("v2.candles")


class BadRequest(Exception):
    def __init__(self, field):
        super().__init__(field)
        self.field = field


class UpbitLimit(Exception):
    """429 뒤 600초 멈춤 또는 엔진 재시작 쉼 중."""

    def __init__(self, retry_after):
        super().__init__(retry_after)
        self.retry_after = retry_after


class UpbitBlocked(Exception):
    """418 또는 24시간 안 두 번째 429 정지 중(정지 파일이 있는 동안)."""


class UpbitError(Exception):
    """그 밖의 업비트 응답 코드."""


class Busy(Exception):
    """다른 종목·봉 단위의 사용자 작업이 진행 중."""

    def __init__(self, progress):
        super().__init__("busy")
        self.progress = progress


def validate(market, unit, days):
    """(market, unit, days) 문자열 검사 → ("KRW-XXX", int, int). 어긋나면 BadRequest(field)."""
    m = market.strip().upper() if isinstance(market, str) else ""
    if not _MARKET_RE.fullmatch(m):
        raise BadRequest("market")
    u = str(unit).strip() if unit is not None else ""
    if not _DIGITS.fullmatch(u) or int(u) not in UNITS:
        raise BadRequest("unit")
    d = str(days).strip() if days is not None else ""
    if not _DIGITS.fullmatch(d) or not 1 <= int(d) <= MAX_DAYS:
        raise BadRequest("days")
    return m, int(u), int(d)


def _http_fetch(url, **kw):
    return tornado.httpclient.AsyncHTTPClient().fetch(url, **kw)


def _parse(body) -> list:
    """업비트 응답 JSON → [[t,o,h,l,c], …]. 원래 dict 는 바로 버린다. 깨지면 ValueError."""
    rows = json.loads(body)
    if not isinstance(rows, list):
        raise ValueError("bad candles")
    out = []
    for r in rows:
        try:
            dt = datetime.strptime(r["candle_date_time_utc"] + "Z", "%Y-%m-%dT%H:%M:%S%z")
            out.append([int(round(dt.timestamp() * 1000)), float(r["opening_price"]),
                        float(r["high_price"]), float(r["low_price"]), float(r["trade_price"])])
        except (KeyError, TypeError):
            raise ValueError("bad candle row") from None
    return out


def _remaining_sec(headers):
    m = _SEC_RE.search((headers.get("Remaining-Req") if headers else None) or "")
    return int(m.group(1)) if m else None


def _atomic_write(path: Path, raw: bytes) -> None:
    """임시 파일(.tmp, 600)에 쓴 뒤 os.replace."""
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(raw)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


class Job:
    """배경 수집 작업 1건. 단위는 모두 「요청 횟수」."""

    def __init__(self, market, unit, days, kind, rate):
        self.market, self.unit, self.days = market, unit, days
        self.kind, self.rate = kind, rate
        self.done = 0
        self.total = 0
        self.stop = False
        self.task = None
        self.error = None
        self.retry_after = None

    def brief(self) -> dict:
        return {"market": self.market, "unit": self.unit, "done": self.done, "total": self.total}


class Collector:
    """업비트 캔들 수집기·보관·미리 받기. 시험에서는 가짜 fetch·sleep·시계를 넣는다."""

    def __init__(self, fetch=None, sleep=None, now=None, data_dir_fn=None):
        self.fetch = fetch or _http_fetch
        self.sleep = sleep or asyncio.sleep
        self.now = now or time.time
        self.data_dir_fn = data_dir_fn or (lambda: db.DATA_DIR)   # import 때 고정하지 않는다
        self.started = self.now()
        self.cooldown_until = 0.0
        self.last_429 = None     # 마지막 429 시각(24시간 안 두 번째면 정지)
        self.prefetch_targets = set()     # 보관 정리 보호용(허용 목록 사용자의 엔진 종목·봉 단위)
        self.window_units = {1}           # 엔진 경계 창 기준 봉 단위(실행 중 엔진 전원) — 정리용과 분리
        self.job = None          # 진행 중 배경 작업
        self.last_job = None     # 끝난 마지막 작업(progress 용)
        self._lock = None
        self._pid = None
        self._gen = None         # 2차 T11: 엔진 재시작 세대 값(생존 파일 "gen") — 같은 pid 안 재시작 감지
        self._last_fetch = None
        self._low_sec = False
        self._blocked = False    # 418·429 메모리 정지(정지 파일 쓰기가 실패해도 이 프로세스는 멈춘다)
        self._load_cooldown()    # 재시작 뒤에도 429 멈춤·24시간 셈을 이어 간다

    # ---- 경로·상태 ----
    def _dir(self) -> Path:
        return Path(self.data_dir_fn()) / STORE_DIR

    def _path(self, market, unit) -> Path:
        # validate 를 통과한 market·unit 으로만 만든다(경로 탈출 차단)
        if not _MARKET_RE.fullmatch(market) or unit not in UNITS:
            raise BadRequest("market")
        return self._dir() / f"{market}_{unit}.json"

    def _get_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    def _halted(self) -> bool:
        return self._blocked or (self._dir() / HALT_FILE).exists()

    def _check_open(self) -> None:
        if self._halted():
            raise UpbitBlocked()
        left = self.cooldown_until - self.now()
        if left > 0:
            raise UpbitLimit(max(1, math.ceil(round(left, 3))))

    def _load_cooldown(self) -> None:
        """기동 때 .cooldown.json {"until","last_429"} 을 읽는다. 없음·깨짐은 무시."""
        try:
            data = json.loads((self._dir() / COOLDOWN_FILE).read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return
        if not isinstance(data, dict):
            return
        for key in ("until", "last_429"):
            v = data.get(key)
            if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v):
                if key == "until":
                    self.cooldown_until = max(self.cooldown_until, float(v))
                else:
                    self.last_429 = float(v)

    def _save_cooldown(self) -> None:
        d = self._dir()
        d.mkdir(mode=0o700, exist_ok=True)
        body = {"until": self.cooldown_until, "last_429": self.last_429}
        _atomic_write(d / COOLDOWN_FILE, json.dumps(body).encode("utf-8"))

    def _window_wait(self) -> float:
        """엔진 봉 경계 창 [b−2, b+20) 안이면 창 끝까지 남은 초, 밖이면 0.

        봉 단위는 window_units(실행 중 엔진 전원의 봉 단위 — _refresh_window_units 가 갱신, 요청마다
        DB·파일을 읽지 않는다). 비었으면 1분(가장 보수적). 경계 = UTC 에포크 초가 unit*60 의 배수인 시각.
        """
        now = self.now()
        units = {u for u in self.window_units if u in UNITS} or {1}
        wait = 0.0
        for u in units:
            p = u * 60
            r = now % p
            if r < ENGINE_WINDOW_AFTER:
                wait = max(wait, ENGINE_WINDOW_AFTER - r)
            elif r >= p - ENGINE_WINDOW_BEFORE:
                wait = max(wait, p - r + ENGINE_WINDOW_AFTER)
        return wait

    def _engine_units(self, alive) -> set:
        """엔진 생존 파일 running 이 True 인 모든 사용자(허용 목록과 무관)의 활성 전략 봉 단위 집합.

        파일 없음·깨짐·running 비었음 → {1}. 어느 사용자의 interval 을 못 읽으면 그 몫은 1분.
        """
        running = alive.get("running") if isinstance(alive, dict) else None
        if not isinstance(running, dict):
            return {1}
        units = set()
        for user, on in running.items():
            if on is not True:
                continue
            unit = 1
            try:
                value, _mtime = db.active_strategy(user)
                iv = db.active_params(user, value).get("interval") if value else None   # 2차 T13: PULLBACK = 적용본
                m = _MINUTE_RE.fullmatch(iv) if isinstance(iv, str) else None
                if m and int(m.group(1)) in UNITS:
                    unit = int(m.group(1))
            except Exception:
                unit = 1
            units.add(unit)
        return units or {1}

    def _refresh_window_units(self, alive=None) -> None:
        """창 기준 봉 단위 갱신(prefetch_loop 첫 반복 전·매 회, pid 변경 때). 예외면 {1}."""
        try:
            self.window_units = self._engine_units(self._read_alive() if alive is None else alive)
        except Exception:
            log.exception("[V2-CANDLES] window units failed — 1 minute")
            self.window_units = {1}

    def _read_alive(self):
        try:
            with open(Path(self.data_dir_fn()) / ALIVE_FILE, "rb") as f:
                return json.loads(f.read(65536).decode("utf-8"))
        except (OSError, ValueError):
            return None

    def _observe_pid(self, data=None) -> bool:
        """엔진 생존 파일의 pid. 처음 값은 기준만, 바뀌면 300초 쉼. 파일 없음·깨짐은 쉬지 않는다."""
        data = self._read_alive() if data is None else data
        pid = data.get("pid") if isinstance(data, dict) else None
        if not isinstance(pid, int) or isinstance(pid, bool):
            return False
        gen = self._gen_of(data)
        if self._pid is None or pid == self._pid:
            first = self._pid is None
            self._pid = pid
            # 2차 T11: 같은 pid 안 엔진 재시작(복구 래퍼 포함) — 이미 본 사용자의 세대 값이 바뀌면 pid 변경과 같은 규칙
            changed = (not first and self._gen is not None
                       and any(u in self._gen and self._gen[u] != n for u, n in gen.items()))
            self._gen = gen if self._gen is None else {**self._gen, **gen}
            if not changed:
                return False
            log.warning("[V2-CANDLES] engine generation changed — pause %ds", COOLDOWN_PID)
        else:
            self._gen = gen
            log.warning("[V2-CANDLES] engine pid changed — pause %ds", COOLDOWN_PID)
        self._pid = pid
        self.cooldown_until = max(self.cooldown_until, self.now() + COOLDOWN_PID)
        self._refresh_window_units(data)          # 엔진 재시작 — 봉 단위가 바뀌었을 수 있다
        return True

    @staticmethod
    def _gen_of(data) -> dict:
        """생존 파일 "gen" = {계정: 정수}. 칸 없음·깨짐은 빈 사전(쉬지 않음)."""
        g = data.get("gen") if isinstance(data, dict) else None
        if not isinstance(g, dict):
            return {}
        return {str(u): n for u, n in g.items() if isinstance(n, int) and not isinstance(n, bool)}

    def _observe_rest_mark(self) -> bool:
        """2차 T11 (F11): 엔진 재시작 쉼 표식 .engine_restart.json {"user","at","until"} — until 전이면 쉰다.
        상한은 min(at, 지금) + COOLDOWN_PID(300초). 없음·깨짐·지난 표식은 쉬지 않는다."""
        try:
            with open(Path(self.data_dir_fn()) / REST_MARK_FILE, "rb") as f:
                data = json.loads(f.read(4096).decode("utf-8"))
        except (OSError, ValueError):
            return False
        if not isinstance(data, dict):
            return False
        at, until = data.get("at"), data.get("until")
        nums = all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in (at, until))
        if not nums:
            return False
        now = self.now()
        until = min(float(until), float(at) + COOLDOWN_PID, now + COOLDOWN_PID)   # 미래 at 도 지금 + 300초까지
        if until <= now:
            return False
        if until > self.cooldown_until:
            self.cooldown_until = until
            log.warning("[V2-CANDLES] engine restart mark — pause until mark")
        return True

    # ---- 보관 ----
    def _load(self, market, unit):
        try:
            data = json.loads(self._path(market, unit).read_text(encoding="utf-8"))
            cov = data["covered"]
            # 읽은 행 목록을 그대로 값으로 쓴다(같은 크기 목록을 한 벌 더 만들지 않게 — 메모리 최대치)
            bars = {}
            for b in data["bars"]:
                if not isinstance(b, list) or len(b) < 5:
                    raise ValueError("bad bar")
                del b[5:]
                b[0] = int(b[0])
                for i in range(1, 5):
                    b[i] = float(b[i])
                bars[b[0]] = b
            del data
            if len(cov) != 2:
                raise ValueError("bad covered")
            return bars, [int(cov[0]), int(cov[1])]
        except (OSError, ValueError, KeyError, TypeError, IndexError):
            return {}, None

    def _touch(self, market, unit) -> None:
        t = self.now()
        try:
            os.utime(self._path(market, unit), (t, t))
        except OSError:
            pass

    def _save(self, market, unit, bars: dict, cov) -> None:
        now = self.now()
        cutoff = int(now * 1000) - MAX_DAYS * DAY_MS     # 30일보다 오래된 봉은 잘라낸다
        keep = [bars[t] for t in sorted(bars) if t >= cutoff]
        d = self._dir()
        d.mkdir(mode=0o700, exist_ok=True)
        path = self._path(market, unit)
        body = {"market": market, "unit": unit, "covered": [max(cov[0], cutoff), cov[1]],
                "bars": keep}
        _atomic_write(path, json.dumps(body, separators=(",", ":")).encode("utf-8"))
        os.utime(path, (now, now))
        self._evict(path)

    def _evict(self, keep_path: Path) -> None:
        """미리 받기 대상 + 최근 쓴 3개만 남긴다. 합계 30MB 초과면 오래된 것부터 지운다."""
        files = []
        for p in self._dir().iterdir():
            m = _STORE_RE.match(p.name)
            if not m:
                continue
            try:
                st = p.stat()
            except OSError:
                continue
            files.append((st.st_mtime, st.st_size, p, (m.group(1), int(m.group(2)))))
        # 방금 쓴 파일은 지우지 않는다(대상 밖이면 「최근 3개」 중 하나로 센다)
        others = sorted((f for f in files if f[3] not in self.prefetch_targets
                         and f[2] != keep_path), key=lambda f: -f[0])
        keep_n = KEEP_RECENT - (0 if any(f[2] == keep_path and f[3] in self.prefetch_targets
                                         for f in files) else 1)
        total = sum(f[1] for f in files)
        for f in others[keep_n:] + list(reversed(others[:keep_n])):
            if f in others[keep_n:] or total > MAX_TOTAL_BYTES:
                try:
                    f[2].unlink()
                    total -= f[1]
                except OSError:
                    pass

    def _halt(self, resp, status=418, reason=None) -> None:
        d = self._dir()
        d.mkdir(mode=0o700, exist_ok=True)
        info = {"at": datetime.fromtimestamp(self.now(), db.KST).isoformat(), "status": status}
        if reason is None:
            info["body"] = (resp.body or b"").decode("utf-8", "replace")[:200]
        else:
            info["reason"] = reason
        _atomic_write(d / HALT_FILE, json.dumps(info, ensure_ascii=False).encode("utf-8"))

    def _block(self, resp, status, reason, market, unit) -> None:
        """418·두 번째 429 정지: 메모리 정지·로그를 먼저 — 파일 쓰기가 실패해도 다시 부르지 않게."""
        self._blocked = True
        log.error("[V2-CANDLES] status=%d HALT market=%s unit=%s", status, market, unit)
        try:
            self._halt(resp, status, reason)
        except OSError as e:
            log.error("[V2-CANDLES] halt file write failed %s — memory halt only",
                      type(e).__name__)

    # ---- 수집 ----
    @staticmethod
    def _plan(cov, unit, days, now):
        """(start, end, cov, 필요한 요청 수). end = 형성 중 봉의 시작(그 봉은 제외)."""
        u = unit * MIN_MS
        now_ms = int(now * 1000)
        end = now_ms // u * u
        start = -(-(now_ms - days * DAY_MS) // u) * u
        if cov is None or cov[1] <= start:
            return start, end, None, math.ceil((end - start) / (PER_REQ * u))
        # 새 봉은 보관 마지막 OVERLAP 봉부터 겹쳐 받는다(collect 와 같은 셈)
        n = math.ceil((end - (cov[1] - OVERLAP * u)) / (PER_REQ * u)) if end > cov[1] else 0
        n += math.ceil((cov[0] - start) / (PER_REQ * u)) if cov[0] > start else 0
        return start, end, cov, n

    async def _request(self, market, unit, to_ms, rate, job):
        """업비트 1회. 매 요청 직전에 작업 중단·간격·정지 파일·쉼·엔진 pid·엔진 경계 창을 본다. 중단이면 None."""
        if job is not None and job.stop:
            return None
        r = job.rate if job is not None else rate
        if self._low_sec:
            await self.sleep(1.0)
        elif self._last_fetch is not None:
            wait = self._last_fetch + 1.0 / r - self.now()
            if wait > 0:
                await self.sleep(wait)
        self._low_sec = False
        if job is not None and job.stop:
            return None
        while True:
            self._observe_pid()
            self._observe_rest_mark()
            self._check_open()
            wait = self._window_wait()
            if wait <= 0:
                break
            # 엔진 경계 창 안 — 창 끝까지 기다린 뒤 pid·정지·쉼을 다시 본다
            await self.sleep(wait)
            if job is not None and job.stop:
                return None
        to = datetime.fromtimestamp(to_ms / 1000, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        url = UPBIT_URL.format(unit=unit) + "?" + urlencode(
            {"market": market, "to": to, "count": PER_REQ})
        self._last_fetch = self.now()
        resp = await self.fetch(url, headers={"Accept": "application/json"},
                                request_timeout=10, raise_error=False)
        if job is not None:
            job.done += 1
        if resp.code == 429:
            now = self.now()
            second = self.last_429 is not None and now - self.last_429 < HALT_429_WITHIN
            self.last_429 = now
            if second:
                self._block(resp, 429, "second 429 in 24h", market, unit)
            else:
                self.cooldown_until = max(self.cooldown_until, now + COOLDOWN_429)
                log.warning("[V2-CANDLES] status=429 market=%s unit=%s — pause %ds",
                            market, unit, COOLDOWN_429)
            try:
                self._save_cooldown()
            except OSError as e:
                log.error("[V2-CANDLES] cooldown file write failed %s — memory only",
                          type(e).__name__)
            if second:
                raise UpbitBlocked()
            raise UpbitLimit(COOLDOWN_429)
        if resp.code == 418:
            self._block(resp, 418, None, market, unit)
            raise UpbitBlocked()
        if resp.code != 200:
            raise UpbitError(resp.code)
        sec = _remaining_sec(resp.headers)
        self._low_sec = sec is not None and sec <= LOW_SEC
        return _parse(resp.body)

    async def collect(self, market, unit, days, rate=USER_RATE, kind="user", job=None):
        """(bars 오름차순·형성 중 봉 제외·요청 기간 안, 이번 업비트 요청 수). 받은 봉은 예외·중단에도 보관."""
        self._check_open()
        async with self._get_lock():
            self._check_open()
            bars, cov = self._load(market, unit)
            start, end, cov, total = self._plan(cov, unit, days, self.now())
            if cov is None:
                bars, cov = {}, [end, end]
            if job is not None:
                job.total, job.done = total, 0
            u = unit * MIN_MS
            n = 0
            try:
                # 새 봉: 보관 끝에서 앞으로 (to 는 제외 경계 → 형성 중 봉은 받지 않는다).
                # Issue #8: 봉 경계 직후 받은 마지막 봉은 종가가 미확정일 수 있어, 보관 마지막
                # OVERLAP 봉을 같은 요청 안에서 겹쳐 다시 받아 덮어쓴다(새 값이 이김).
                cur = cov[1] - OVERLAP * u if cov[1] < end else cov[1]
                while cur < end:
                    to = min(cur + PER_REQ * u, end)
                    got = await self._request(market, unit, to, rate, job)
                    if got is None:
                        break
                    n += 1
                    for b in got:
                        bars[b[0]] = b
                    cur = cov[1] = to
                # 옛 봉: 보관 처음에서 뒤로
                while cov[0] > start and not (job is not None and job.stop):
                    got = await self._request(market, unit, cov[0], rate, job)
                    if got is None:
                        break
                    n += 1
                    for b in got:
                        bars[b[0]] = b
                    if len(got) < PER_REQ:          # 상장 전 — 더 옛 봉 없음
                        cov[0] = min(cov[0], start)
                        break
                    oldest = min(b[0] for b in got)
                    if oldest >= cov[0]:
                        raise ValueError("candles not older than to")
                    cov[0] = oldest
            finally:
                if n:
                    self._save(market, unit, bars, cov)
                else:
                    self._touch(market, unit)
        return [bars[t] for t in sorted(bars) if start <= t < end], n

    # ---- 처리기용 ----
    def start_job(self, market, unit, days, kind="user", rate=USER_RATE) -> Job:
        job = Job(market, unit, days, kind, rate)
        bars, cov = self._load(market, unit)
        job.total = self._plan(cov, unit, days, self.now())[3]
        self.job = job
        job.task = asyncio.ensure_future(self._run(job))
        return job

    async def _run(self, job: Job) -> None:
        try:
            await self.collect(job.market, job.unit, job.days, rate=job.rate,
                               kind=job.kind, job=job)
        except UpbitLimit as e:
            job.error, job.retry_after = "upbit_limit", e.retry_after
        except UpbitBlocked:
            job.error = "upbit_blocked"
        except (UpbitError, tornado.httpclient.HTTPClientError, OSError, ValueError) as e:
            log.warning("[V2-CANDLES] error market=%s unit=%s %s", job.market, job.unit,
                        type(e).__name__)
            job.error = "upbit_error"
        except Exception:
            log.exception("[V2-CANDLES] job failed market=%s unit=%s", job.market, job.unit)
            job.error = "upbit_error"
        finally:
            if self.job is job:
                self.job = None
            self.last_job = job

    async def serve(self, market, unit, days):
        """("ok", 200 본문) 또는 ("running", 202 본문). Busy·UpbitLimit·UpbitBlocked 등은 올린다.

        418·429 정지 중에는 아무것도 내주지 않는다. 보관분이 기간을 덮어 업비트 요청이 0회면 쉼
        (429 600초·엔진 재시작 300초)·엔진 경계 창 중에도 보관분으로 바로 200 — 쉼·창은 업비트를
        부르는 경로에만 건다.
        """
        if self._halted():
            raise UpbitBlocked()
        bars, cov = self._load(market, unit)
        start, end, cov, total = self._plan(cov, unit, days, self.now())
        if cov is not None and total == 0:
            self._touch(market, unit)          # 읽은 것도 최근으로 친다(collect 의 0회와 같음)
            out = [bars[t] for t in sorted(bars) if start <= t < end]
            return "ok", {"market": market, "unit": unit, "days": days, "bars": out, "requests": 0}
        del bars                               # 아래 collect 가 다시 읽는다 — 두 벌을 들고 있지 않게
        self._check_open()
        while self.job is not None:
            job = self.job
            same = (job.market, job.unit) == (market, unit)
            running = ("running", {"job": "running", "progress": job.brief()})
            if job.kind == "user":
                if same:
                    return running
                raise Busy(job.brief())
            if same:                          # 미리 받기를 사용자 속도로 이어 받는다
                job.kind, job.rate = "user", USER_RATE
                return running
            job.stop = True                   # 받은 봉까지 보관하고 멈춘다
            await job.task
            self._check_open()
            _bars, cov = self._load(market, unit)   # 멈춘 작업이 보관을 바꿨을 수 있다
            del _bars                          # 구간만 쓴다(collect 동안 봉 사전을 들고 있지 않게)
            total = self._plan(cov, unit, days, self.now())[3]
        if total > INLINE_MAX_REQ:
            job = self.start_job(market, unit, days)
            return "running", {"job": "running", "progress": job.brief()}
        bars, n = await self.collect(market, unit, days)
        return "ok", {"market": market, "unit": unit, "days": days, "bars": bars, "requests": n}

    def progress(self) -> dict:
        job = self.job or self.last_job
        if job is None:
            return {"active": False, "kind": None, "market": None, "unit": None,
                    "done": 0, "total": 0, "error": None, "retry_after": None}
        return {"active": self.job is not None, "kind": job.kind, "market": job.market,
                "unit": job.unit, "done": job.done, "total": job.total,
                "error": job.error, "retry_after": job.retry_after}

    # ---- 미리 받기 ----
    def _targets(self) -> dict:
        """허용 목록 사용자들의 현재 전략 종목·봉 단위(ReadHandler._context 와 같은 규칙) → 사용자 목록."""
        out = {}
        for user in sorted(et.load_allowlist()):
            if not et.valid_user_id(user):
                continue
            value, _mtime = db.active_strategy(user)
            if not value:
                continue
            try:
                params = db.active_params(user, value)   # 2차 T13: PULLBACK 이면 적용본
            except ValueError:
                continue
            market = db.normalize_ticker(params.get("ticker"))
            iv = params.get("interval")
            m = _MINUTE_RE.fullmatch(iv) if isinstance(iv, str) else None
            if not market or not _MARKET_RE.fullmatch(market) or not m or int(m.group(1)) not in UNITS:
                continue
            out.setdefault((market, int(m.group(1))), []).append(user)
        return out

    async def prefetch_once(self) -> None:
        """미리 받기 1회: pid 확인 → (기동 300초 뒤·엔진 생존일 때만) 대상마다 1회/초로 30일치, 그 뒤 새 봉만."""
        alive = self._read_alive()
        self._observe_pid(alive)
        self._refresh_window_units(alive)
        targets = self._targets()
        self.prefetch_targets = set(targets)       # 기동 직후에도 대상 파일이 지워지지 않게 먼저 갱신
        if self.now() - self.started < PREFETCH_DELAY:
            return
        if self.job is not None or self._halted() or self.cooldown_until > self.now():
            return
        now_dt = datetime.fromtimestamp(self.now(), db.KST)
        for (market, unit), users in sorted(targets.items()):
            if not any(engine_alive_running(alive, u, now_dt) for u in users):
                continue
            if self.job is not None:
                return
            job = self.start_job(market, unit, MAX_DAYS, kind="prefetch", rate=PREFETCH_RATE)
            await job.task
            if job.stop or job.error:
                return

    async def prefetch_loop(self) -> None:
        """_serve() 가 시작한다. 기동 300초 뒤 첫 prefetch_once, 그 뒤 600초마다."""
        # 첫 반복 전에 대상을 채운다 — 기동 직후 사용자 수집의 정리가 엔진 종목 파일을 지우지 않게
        self._refresh_window_units()
        try:
            self.prefetch_targets = set(self._targets())
        except Exception:
            log.exception("[V2-CANDLES] prefetch targets failed")
        wait = PREFETCH_DELAY
        while True:
            await self.sleep(wait)
            wait = PREFETCH_EVERY
            try:
                await self.prefetch_once()
            except Exception:
                log.exception("[V2-CANDLES] prefetch failed")
