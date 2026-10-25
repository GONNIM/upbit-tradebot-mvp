# 신버전 대시보드 1차 공개(P1·P2) 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **실행 에이전트 금지 행위:** 서버 SSH, `pip install`, 외부 내려받기(jsdelivr·Binance), `git commit`·`push`, 서버 설정 변경은 직접 하지 않는다. 「사용자 확인 후」가 붙은 Step 과 모든 커밋은 PO 에게 돌려보내고, PO 가 사용자 승인을 받아 실행한다.

**Goal:** 엔진(`tradebot`)과 분리된 별도 서비스 `tradebot-v2`로 모바일용 읽기 화면(홈·차트·로그·운용 표시)과 원본 백테스터(Binance, 「저장만 하기」)를 제공한다. 실매매 규칙·실매매 DB는 바꾸지 않는다.

**Architecture:** tornado 서버(127.0.0.1:8502)가 JSON API와 정적 파일을 낸다. 실매매 DB는 읽기 전용 URI로만 열고, 신버전 쓰기는 `services/data/v2hist_<user>.db`와 `{user}_latest_params_PULLBACK.json` 두 곳뿐이다. 구버전 입장 화면이 버튼을 누를 때 60초 1회용 서명 토큰을 만들어 넘기고, 신버전은 자체 세션 쿠키로 바꾼다.

**Tech Stack:** 서버 Python 3.12.8(`/root/upbit-tradebot-mvp/venv`)·로컬 3.11.9, tornado 6.5.1(서버 기설치, 로컬 6.4.2 → Task 1 Step 0 에서 맞춤), sqlite3, 표준 라이브러리 `hmac`·`hashlib`·`secrets`; 화면은 정적 HTML + Alpine.js 3.14.1 + Lightweight Charts 4.2.0(Apache-2.0, `v2/static/vendor/`에 파일로 고정); 시험은 `unittest`(프로젝트 관례), Streamlit `AppTest`(1.46.0), 백테스터·차트 JS는 로컬 Node 22 `node:test`.

**Spec:** `docs/specs/v2-dashboard/spec.md`(3.1 E1~E14, 3.2 E15~E19), 목차 `docs/specs/v2-dashboard/plan-outline-v3.md`, 검증 보고 `review-20261022-outline-v2.md`·`review-20261022-outline-v3-draft.md`·`review-20261022-outline-v3-recheck.md`·`review-20261022-plan-draft.md`

## Global Constraints

- D8: 신버전 서버 Python 코드와 그 import 그래프에 `pyupbit`·`config`·`streamlit`·`services.`·`engine.` 없음, 서버 코드에 `api.upbit.com` 문자열 없음. 업비트 호출은 투자자 브라우저의 차트 JS만.
- 엔진 프로세스가 읽는 파일 중 바꾸는 것: `app.py`(입장 블록 3줄: import 1, 호출 1, 주석 1), 신규 `ui/v2_entry.py`, 신규 `utils/v2_entry_token.py`, `pages/dashboard.py` 버전 문자열. `services/settings_history.py`·`services/init_db.py`·`pages/settings_history.py`는 바꾸지 않는다(E15·E16).
- `ui/v2_entry.py`·`utils/v2_entry_token.py`는 1차 배포 뒤 **동결**한다. 엔진 프로세스는 파일 감시가 꺼져 있어(`fileWatcherType = "none"`) 이 파일을 바꾸면 `tradebot` 재시작이 필요하다. 이후 v2 배포 diff에 이 두 파일이 있으면 배포를 멈추고 따로 승인받는다. 토큰에는 형식 버전 `"v": 1`을 넣는다.
- `app.py`·`ui/v2_entry.py`는 `v2/*`를 import 하지 않는다. `utils/v2_entry_token.py`는 표준 라이브러리만 쓴다(app 쪽과 v2 쪽이 함께 import).
- 실매매 DB: `file:{path}?mode=ro` URI, `busy_timeout=3000`, `journal_mode` PRAGMA 보내지 않음, 파일 없으면 거부, 모든 조회 `LIMIT`, 조회 시간 상한 2초(`set_progress_handler`), 조회마다 인덱스 사용 확인 시험.
- DB 경로: `services/data/tradebot_{user_id}.db`(`services/init_db.py:19-21`). 신버전 이력: `services/data/v2hist_{user_id}.db`(접두사 `tradebot_` 금지 — `engine/boot_resume.py:54`).
- user_id: 정규식 `^[A-Za-z0-9_]{1,32}$` + 허용 목록(기존 코드에 검증 없음 — 신설).
- 저장소 루트: 서버 `/root/upbit-tradebot-mvp`, 코드에서는 `Path(__file__).resolve().parents[1]`. PULLBACK 설정 파일은 루트의 `{user_id}_latest_params_PULLBACK.json`. EMA·MACD 파일은 쓰지 않는다.
- 현재 전략: 루트의 `{user_id}_active_strategy.txt`(값 + 파일 수정 시각). 종목·봉 단위는 그 전략의 `{user_id}_latest_params_{STRATEGY}.json`의 `ticker`·`interval`(`"minute3"` 형식).
- 시각: `timestamp` 열은 ISO(`+09:00`)와 `YYYY-MM-DD HH:MM:SS`(기본값 `DATETIME('now','localtime')`) 두 형식이 섞여 있다. 모두 KST로 파싱한다. 화면 표시는 KST.
- 「엔진 동작」(E17): 정상·지연·판단 불가 3단계, 「정지」라는 글자를 쓰지 않는다. 경계는 Task 0 실측으로 Task 4 상수에 기입.
- TEST/LIVE는 같은 DB(테이블에 mode 열 없음). 모드 배지는 `engine_status.last_mode`, 입장 모드와 다르면 경고.
- 412px 폭 가로 스크롤 없음, 입력창 글자 16px, 상태는 색과 글자를 함께.
- 정적 파일 외부 호스트 허용 목록: 차트 `api.upbit.com`, 백테스터 `data-api.binance.vision`·`api.binance.com`. 그 밖 0.
- 원본 백테스터 스크립트(원본 HTML 142~939행 `<script>` 본문)는 바이트 그대로 옮긴다.
- 규칙: 코드 커밋마다 `pages/dashboard.py` 버전 갱신·보고 「버전: 구 → 신」 · 여러 줄 텍스트는 파일 도구로만(heredoc 금지) · 키·서명 키 값은 화면·로그·문서·대화에 내지 않음(생성도 파일로 직접) · 새 비밀 파일 600·root · Fable 보고 번들 zip · push 전 `git status` · 커밋·push·배포·서버 설정 변경·서버 점검 스크립트 실행·외부 발송 각각 승인.

## Review Focus

1. 투자자가 입장 화면에 오래 머문 뒤 들어가도 재로그인 없이 입장되어야 하고, 같은 토큰을 두 번 쓰거나 60초가 지나면 「구버전에서 다시 눌러 주세요」가 보여야 한다 → Task 2 `test_token_reuse_rejected`·`test_token_expired_rejected`, Task 3 `test_expired_token_page_has_guidance`, Task 5 `test_token_made_on_click_not_on_render`.
2. 서명 키·허용 목록 파일이 없거나 손상·권한 오류여도 구버전 입장 화면은 정상이고 버튼만 숨겨야 한다 → Task 5 `test_render_no_exception_on_missing_corrupt_unreadable`.
3. 브라우저 업비트 호출 실패·429 때 차트가 마지막 데이터를 유지하고 「갱신 실패 · 시각」을 보이며, 요청이 겹치지 않아야 한다 → Task 6 `keeps last data on 429`, `single in-flight request`.
4. 무거래 봉·보유 중 공백 때 「정지」가 아니라 「지연」으로 보여야 한다 → Task 4 `test_engine_state_no_trade_gap_is_delay`.
5. 입장 모드와 엔진 실제 모드가 다르면 경고가 보여야 한다 → Task 4 `test_mode_mismatch_warning`.
6. 토큰이 `/v2/?t=` 로 nginx 접근 로그에 남는다(spec 4.2) → 1회용·60초 만료라 로그에서 꺼내 다시 쓸 수 없어야 하고(Task 2 `test_token_reuse_rejected`·`test_token_expired_rejected`), 교환 직후 302 로 주소에서 지워져야 한다(Task 3 `test_token_exchange_sets_cookie_and_redirects`).

---

## Task 0: 사전 실측 (코드 무변경, 서버 읽기 전용)

**Files:** Create `docs/specs/v2-dashboard/measure-20261023.md`

- [ ] **Step 1: 세션 재개 표준 정지선** — 로컬 HEAD·`origin/main`, 서버 HEAD·`grep -n v1.2026 pages/dashboard.py`·`systemctl show tradebot -p ExecMainStartTimestamp`·`systemctl list-unit-files | grep -c tradebot-v2`(0)·`ls -l .env .streamlit/secrets.toml`(600). 다르면 멈춘다.
- [ ] **Step 2: V1 엔진 동작 출처 (사용자 확인 후 — 서버 점검 스크립트 실행)** — 서버에서 `venv/bin/python` 스크립트 1회로(실매매 DB ro URI) 최근 7일 `audit_buy_eval`·`audit_sell_eval` `timestamp` 연속 간격(중앙값·95%·최대)과 LIVE `accounts.updated_at`, journal `CONFIRMED-NO-TRADE`·`봉 처리 완료` 건수. 스크립트는 scratchpad에 파일로 쓰고 서버로 복사해 실행. 같은 스크립트로 `sqlite3.sqlite_version`과 `SELECT name FROM sqlite_master WHERE type='index' LIMIT 200`(ro)도 기록해 Task 4 픽스처 인덱스와 대조. Expected: 표 1개 → Task 4 `DELAY_FACTOR`·`UNKNOWN_SEC` 결정(제안: 지연 = 봉 초 × 3 초과, 판단 불가 = max(95% 간격 × 2, 1800초) 초과).
- [ ] **Step 3: V3 메모리** — `/usr/bin/time -v /root/upbit-tradebot-mvp/venv/bin/python -c "import tornado.web, sqlite3, hmac"` 의 Maximum resident set size. `MemoryMax` 확정(기본 150M).
- [ ] **Step 4: V4 권한** — `stat -c '%a %U %n'` `/root`, `services/data`, DB·`-wal`·`-shm`, `*_latest_params_*.json`, `*_active_strategy.txt`.
- [ ] **Step 5: V2 휴대폰 브라우저 업비트 직접 호출** — 실측 수단 없음. 기록에 「미확인 — 공개 후 투자자 화면 확인」을 남기고 백로그 유지.
- [ ] **Step 6: cron 원문** — `crontab -l` 의 `cleanup_tradebot_db.sh` 줄만 기록.
- [ ] **Step 7: 커밋**(문서만, 버전 유지).

## Task 1: 경량 DB·설정 모듈 `v2/db.py`

**Files:** Create `v2/__init__.py`, `v2/db.py`; Test `tests/v2/__init__.py`, `tests/v2/test_db.py`

**Interfaces — Produces:**
- `REPO_ROOT: Path`, `DATA_DIR: Path = REPO_ROOT / "services" / "data"`
- `valid_user_id(user_id: str) -> bool`
- `live_db_path(user_id) -> Path`, `v2hist_path(user_id) -> Path`
- `open_live_ro(user_id) -> sqlite3.Connection` — 없으면 `FileNotFoundError`, 실행 2초 상한(`set_progress_handler(cb, 1000)`, 기한 넘으면 `cb`가 1 반환 → `sqlite3.OperationalError: interrupted`). busy 대기 3초는 별도라 최악 약 5초.
- `query(user_id, sql: str, params: tuple = ()) -> list[dict]` — `sql`에 `LIMIT` 없으면 `ValueError`
- `open_v2hist(user_id) -> sqlite3.Connection` — 파일이 없으면 실매매 DB가 있을 때만 `mode=rwc`, 있으면 `mode=rw`; 매번 `CREATE TABLE IF NOT EXISTS v2_settings_history(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL, saved_at TEXT NOT NULL, source_page TEXT NOT NULL, strategy_type TEXT NOT NULL, params_json TEXT, conditions_json TEXT, app_version TEXT, note TEXT, applied_at TEXT)`와 `os.chmod(p, 0o600)`
- `insert_history(user_id, params_json: str, note: str | None) -> int` — `source_page="v2_backtester"`, `strategy_type="PULLBACK"`, `app_version=app_version()`
- `app_version() -> str | None` — `pages/dashboard.py`에서 `v1\.\d{4}\.\d{2}\.\d{2}\.\d{4}` 첫 일치(`services/settings_history.py:46,81-92`와 같은 규칙)
- `parse_ts(s: str) -> datetime` — ISO(+09:00)와 `YYYY-MM-DD HH:MM:SS`(KST로 간주) 둘 다
- `now_kst_iso() -> str`
- `active_strategy(user_id) -> tuple[str | None, str | None]`(값, 수정 시각 ISO), `strategy_params(user_id, strategy: str) -> dict`(읽기 전용), `pullback_params_path(user_id) -> Path`

- [ ] **Step 0: 로컬 tornado 버전 맞춤** — 로컬은 6.4.2(서버 6.5.1). `python3 -m pip install tornado==6.5.1`(로컬 환경만, 사용자 확인 후) 뒤 `python3 -c "import tornado; print(tornado.version)"` → `6.5.1`.
- [ ] **Step 1: 실패 시험** — 임시 폴더로 `REPO_ROOT`·`DATA_DIR` 패치:
  - `test_valid_user_id`: `"mcmax33"` True; `""`, `"../x"`, `"a"*33`, `"a-b"` False
  - `test_open_live_ro_missing_creates_nothing`(호출 뒤 폴더 목록 불변, A16)
  - `test_live_ro_insert_rejected`(`sqlite3.OperationalError`, A16)
  - `test_query_requires_limit`, `test_query_time_limit_interrupts`(재귀 CTE로 2초 초과 → OperationalError)
  - `test_open_v2hist_not_created_without_live_db`
  - `test_open_v2hist_existing_empty_file_gets_table_and_600`(0바이트 644 파일 → 테이블 생성, 600)
  - `test_insert_history_columns`(`saved_at` 정규식 `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?\+09:00$`, `source_page`·`strategy_type`·`params_json` 원문·`conditions_json`·`applied_at` None·`app_version` 형식)
  - `test_parse_ts_both_formats`
  - `test_active_strategy_and_params`
  - `test_db_module_stdlib_only`(ast, 허용 `{"sqlite3","os","re","stat","json","time","pathlib","datetime","zoneinfo","typing"}`)
- [ ] **Step 2: 실패 확인** — `python3 -m unittest tests.v2.test_db -v` → `ModuleNotFoundError`
- [ ] **Step 3: 구현**
- [ ] **Step 4: 통과 확인**
- [ ] **Step 5: 회귀 게이트에 v2 단계 추가** — `scripts/regression_gate.sh`는 회귀 단계(150-159행)가 통과하면 그 자리에서 `exit 0` 하므로, v2 단계 `python3 -m unittest discover -s tests/v2 -t . -v`를 **회귀 단계 앞**에 넣고 실패하면 `exit 1`. `tee`·`tail` 파이프로 감싸지 않고 종료 코드로 판정한다(게이트에 `pipefail` 없음). 출력에 `✅ v2 시험 통과` 줄을 찍는다. 확인: 일부러 실패하는 시험 1개를 임시로 두고 게이트가 exit 1 인지 본 뒤 되돌림, 정상 때 `✅ v2 시험 통과`와 `✅ 회귀 테스트 N/N 통과` 두 줄.
- [ ] **Step 6: 커밋** — `v2/`, `tests/v2/`, `scripts/regression_gate.sh`, `pages/dashboard.py`(버전).

## Task 2: 입장 토큰·허용 목록·세션

**Files:** Create `utils/v2_entry_token.py`, `v2/auth.py`; Test `tests/v2/test_auth.py`

**Interfaces — Produces:**
- `utils/v2_entry_token.py`(표준 라이브러리만): `REPO_ROOT`, `SECRET_PATH = REPO_ROOT / ".v2_secret"`(32바이트 이상 원시 바이트), `ALLOWLIST_PATH = REPO_ROOT / ".v2_allowlist"`(한 줄 한 user_id, `#` 주석), `TOKEN_TTL_SEC = 60`, `FORMAT_VERSION = 1`, 예외 `TokenUnavailable`·`TokenInvalid`, `load_allowlist(path=ALLOWLIST_PATH) -> frozenset[str]`(없거나 읽기 실패면 빈 집합), `is_allowed(user_id) -> bool`, `make_token(user_id, mode, now: float | None = None) -> str`, `verify_token(token, now=None) -> dict`(`{"v","user_id","mode","nonce","exp"}`). 형식 `base64url(json) + "." + base64url(hmac_sha256)`. 예외 메시지에 키·토큰 본문을 넣지 않는다.
- `v2/auth.py`: `NonceStore.consume(nonce, exp) -> bool`, `SESSION_COOKIE = "v2s"`, `SESSION_TTL_SEC = 43200`, `make_session(user_id, mode) -> str`, `read_session(value) -> dict | None`

- [ ] **Step 1: 실패 시험** — `test_roundtrip`, `test_token_expired_rejected`(now+61), `test_token_tampered_rejected`, `test_token_wrong_version_rejected`, `test_token_reuse_rejected`(두 번째 `consume` False), `test_missing_secret_unavailable`, `test_short_secret_unavailable`(31바이트), `test_unreadable_secret_unavailable`(0o000), `test_allowlist_missing_or_unreadable_empty`, `test_allowlist_comments`, `test_entry_token_stdlib_only`(허용 `{"hmac","hashlib","secrets","base64","json","time","pathlib","os","typing"}`)
- [ ] **Step 2: 실패 확인** — `python3 -m unittest tests.v2.test_auth -v`
- [ ] **Step 3: 구현** — `.gitignore`에 `.v2_secret`·`.v2_allowlist` 추가.
- [ ] **Step 4: 통과 확인**
- [ ] **Step 5: 커밋**(버전 갱신)

## Task 3: tornado 서버 골격·인증 흐름

**Files:** Create `v2/server.py`; Test `tests/v2/test_server.py`(`tornado.testing.AsyncHTTPTestCase`)

**Interfaces:**
- Consumes: Task 1 `valid_user_id`, Task 2 `verify_token`·`NonceStore`·`make_session`·`read_session`·`is_allowed`
- Produces: `make_app(static_dir: Path | None = None, allowed_origin: str = "https://orionhunter7.cafe24.com") -> tornado.web.Application`, `main()`(127.0.0.1:8502). 기반 `ApiHandler.current_user -> {"user_id","mode"} | None`(세션 + 허용 목록 재확인). 공통 헤더 `Referrer-Policy: no-referrer`, `X-Content-Type-Options: nosniff`, API `Cache-Control: no-store`. 라우트: `GET /v2/?t=` → 검증·소비 → 쿠키(`HttpOnly; Secure; SameSite=Lax; Path=/v2/`) → `302 /v2/`; 실패 시 401 안내 페이지(「구버전 입장 화면에서 『신버전 대시보드』를 다시 눌러 주세요」); `GET /v2/` 세션 있으면 `index.html`, 없으면 같은 안내 401; `/v2/api/*`(Task 4·8); `/v2/static/*`. POST는 `Origin != allowed_origin`이면 403.

- [ ] **Step 1: 실패 시험** — `test_token_exchange_sets_cookie_and_redirects`(302, Location, 쿠키 속성 4개), `test_token_reuse_rejected`, `test_expired_token_page_has_guidance`, `test_api_without_session_401`, `test_api_not_allowlisted_403`, `test_referrer_policy_header`, `test_post_bad_origin_403`, `test_server_import_graph_clean`(서브프로세스에서 `import v2.server, v2.api_read, v2.api_write` 뒤 `sys.modules`에 `config`·`streamlit`·`pyupbit`·`services`·`engine` 접두 0, A14), `test_server_code_has_no_upbit_host`(`v2/*.py`에 `api.upbit.com` 0)
- [ ] **Step 2: 실패 확인** — `python3 -m unittest tests.v2.test_server -v`
- [ ] **Step 3: 구현**
- [ ] **Step 4: 통과 확인**
- [ ] **Step 5: 커밋**(버전 갱신)

## Task 4: 읽기 API

**Files:** Create `v2/status.py`, `v2/api_read.py`; Test `tests/v2/test_status.py`, `tests/v2/test_api_read.py`(픽스처: 임시 DB에 필요한 테이블만 SQL로 생성 — 엔진 모듈 import 없음, 인덱스는 `services/init_db.py:259,294-295,323-324,369-370,827-828,843-844`와 같게. `CREATE TABLE`은 `services/init_db.py:134-240`(users·logs·accounts·account_positions·engine_status)과 `:274-368`(audit_buy_eval·audit_trades·audit_sell_eval)의 해당 원문을 그대로 옮기고(PK·UNIQUE 포함), API가 읽는 열을 더하는 ALTER 문 원문(`:737,826,842,928,942,955,968,981,996-998`)도 같은 순서로 적용한다. 원문과 같은지 CREATE·ALTER 모두 대조하는 lint `test_fixture_ddl_matches_init_db`를 둔다)

**Interfaces:**
- Consumes: Task 1 `query`·`parse_ts`·`active_strategy`·`strategy_params`, Task 3 `ApiHandler`
- Produces:
  - `DELAY_FACTOR = 3`, `UNKNOWN_SEC = 1800`(Task 0 결과로 갱신)
  - `interval_sec(interval: str) -> int`(`"minute3"` → 180)
  - `engine_state(last_eval_ts: datetime | None, accounts_ts: datetime | None, mode: str, bar_sec: int, now: datetime) -> dict` → `{"level": "ok"|"delay"|"unknown", "ago_sec": int | None, "basis": "eval"|"accounts"|"none"}`
  - `GET /v2/api/status` → `{"engine", "mode_engine", "mode_entry", "mode_mismatch", "strategy": {"value","mtime"}, "ticker", "interval", "paused"}` — `paused`는 `SELECT trading_paused FROM users WHERE username = ? LIMIT 1`(`services/db.py:913-926`과 같은 의미)
  - `GET /v2/api/assets` → `{"krw","krw_locked","coin","coin_locked","entry_price","price","price_at","pnl","tp_price","sl_price","round","updated_at"}` — `price`·`price_at`은 현재 `ticker`의 `audit_sell_eval`/`audit_buy_eval` 최신 행(E5). `tp_price`·`sl_price`는 보유 중일 때 엔진이 기록한 현재 `ticker`의 `audit_sell_eval` 최신 행 값(`core/strategy_engine.py:2020` 부근에서 계산·기록), 0 또는 NULL 이면 `null`(화면 「—」). `round`(회차)는 PULLBACK(P3) 개념이라 1차는 항상 `null`(spec 4.3 홈 「회차」는 P3 에서 채움)
  - `GET /v2/api/trades?limit=10`(최대 50), `GET /v2/api/signals?limit=20`(최대 50), `GET /v2/api/logs?page=N`(`SELECT … FROM logs WHERE user_id=? ORDER BY timestamp DESC LIMIT 50 OFFSET ?` — `idx_logs_user_ts` 사용), `GET /v2/api/markers`(현재 `ticker`의 `audit_trades` `type,price,bar_time`, `WHERE ticker=? ORDER BY timestamp DESC LIMIT 200` — `bar_time` 정렬은 인덱스가 없어 쓰지 않음)

- [ ] **Step 1: 실패 시험** — `test_status.py`: `test_engine_state_ok`(60초, 180초 봉), `test_engine_state_no_trade_gap_is_delay`(24분 → "delay"), `test_engine_state_unknown_when_none`, `test_engine_state_unknown_after_unknown_sec`, `test_live_uses_accounts_ts_as_secondary`, `test_test_mode_ignores_accounts`, `test_mode_mismatch_warning`, `test_interval_sec`. `test_api_read.py`: `test_assets_price_from_latest_eval_for_ticker`, `test_assets_tp_sl_from_latest_sell_eval`(0·NULL → null), `test_assets_round_null_in_phase1`, `test_logs_paginated_50`, `test_queries_all_have_limit`, `test_queries_use_index`(각 SQL의 `EXPLAIN QUERY PLAN`: `USE TEMP B-TREE` 금지; `USING` 없는 맨 `SCAN`(정규식 `^SCAN \w+$`)은 `ORDER BY id DESC LIMIT n` 조회에만 허용; 그 밖의 줄은 `USING INDEX`·`USING COVERING INDEX`·`USING INTEGER PRIMARY KEY`·`USING PRIMARY KEY`·autoindex 중 하나 포함), `test_mixed_timestamp_formats`.
- [ ] **Step 2: 실패 확인** — `python3 -m unittest tests.v2.test_status tests.v2.test_api_read -v`
- [ ] **Step 3: 구현**
- [ ] **Step 4: 통과 확인**
- [ ] **Step 5: 커밋**(버전 갱신)

## Task 5: 구버전 입장 버튼

**Files:**
- Create: `ui/v2_entry.py`
- Modify: `app.py` — 「파라미터 설정하기」 블록(556행 `btn_start_setting`) 바로 위에 `render_v2_entry(username, st.session_state.get("mode", "TEST"))` 한 줄과 import 한 줄. `st.session_state.user_id`는 `setdefault`(297행)라 계정 전환 때 옛 값이 남으므로 쓰지 않는다(기존 541·569행과 같은 이유로 `username` 직접 사용).
- Test: `tests/regressions/test_r_2026_10_23_v2_entry_button.py`

**Interfaces:**
- Consumes: Task 2 `is_allowed`·`make_token`·`TokenUnavailable`
- Produces: `render_v2_entry(user_id: str, mode: str) -> None` —
  1. 허용 목록에 없으면 아무것도 그리지 않음.
  2. `st.button("📱 신버전 대시보드 (베타)", key="btn_v2_entry")`. 눌리면 그때 `make_token`으로 토큰을 만들고 `st.link_button("신버전 열기 (60초 안에 눌러 주세요)", f"/v2/?t={token}")`와 「구버전으로 돌아올 때는 다시 로그인해야 합니다」 안내를 보인다(`link_button`에는 `key` 인자가 없다 — Streamlit 1.46 시그니처).
  3. 함수 전체를 `try/except Exception`으로 감싸 실패하면 아무것도 그리지 않고 `logger.warning("[V2-ENTRY] hidden: %s", type(e).__name__)`.
  4. `st.expander` 안에 넣지 않는다(1-B).

- [ ] **Step 1: 실패 시험** — `AppTest.from_function`으로 `render_v2_entry` 를 감싸 실행(함수 소스만 떼어 실행되므로 경로·user_id 는 `kwargs`로 넘기고 `utils.v2_entry_token` 경로는 모듈 패치; 링크는 `at.get("link_button")[0].proto.url`로 읽음):
  - `test_allowed_shows_button_no_exception`
  - `test_not_allowed_shows_nothing`(A13)
  - `test_render_no_exception_on_missing_corrupt_unreadable`(키 없음·31바이트·0o000 3종 → 예외 0, 버튼 없음 또는 클릭 뒤 링크 없음)
  - `test_token_made_on_click_not_on_render`(`make_token` 패치 호출 수: 렌더 0, 클릭 뒤 1)
  - `test_click_shows_link_with_token`
  - 문자열 lint: `test_app_calls_render_v2_entry_once`, `test_app_passes_username_not_session_user_id`(호출 첫 인자가 `username`), `test_app_and_ui_do_not_import_v2`(ast), `test_not_inside_expander`
- [ ] **Step 2: 실패 확인** — `python3 -m unittest tests.regressions.test_r_2026_10_23_v2_entry_button -v`
- [ ] **Step 3: 구현**
- [ ] **Step 4: 게이트** — `bash scripts/regression_gate.sh` → `✅ 회귀 테스트 N/N 통과` + v2 단계 OK. 게이트는 `app.py`를 import 하지 않으므로 Step 1의 AppTest 시험이 이 파일의 유일한 렌더 검증이다.
- [ ] **Step 5: UI diff 브리핑 준비**(1-A 2층) — 추가: 버튼 1·링크 1·안내 1. 삭제·이동·접힘 0.
- [ ] **Step 6: 커밋**(버전 갱신)

## Task 6: 정적 화면 (홈·차트·로그·운용 표시)

**Files:** Create `v2/static/index.html`, `v2/static/app.js`, `v2/static/chart.js`, `v2/static/style.css`, `v2/static/vendor/alpine-3.14.1.min.js`, `v2/static/vendor/lightweight-charts-4.2.0.standalone.production.js`, `v2/static/vendor/VERSIONS.txt`(출처 URL·sha256·라이선스 고지), `v2/static/vendor/LICENSE-lightweight-charts.txt`; Test `tests/v2/js/chart.test.mjs`, `tests/v2/test_static_lint.py`

**Interfaces:**
- Consumes: Task 4 API 경로·키
- Produces (`chart.js`, ES 모듈):
  - `upbitCandlesUrl(market: string, unitMin: number) -> string` — `https://api.upbit.com/v1/candles/minutes/{unit}?market={market}&count=200`
  - `toAscending(candles) -> candles`(업비트 응답은 최신순 → 오래된 순)
  - `createPoller({fetchFn, intervalMs = 30000, onData, onError, isHidden}) -> {start(), stop()}` — 진행 중이면 새 요청 없음, 숨김이면 건너뜀, 실패면 마지막 데이터 유지하고 `onError(time)`
  - `markFormingCandle(candles, nowMs, unitSec) -> candles`
  - `sma(values, period) -> (number|null)[]`(MA60·눌림목 MA; MA200 없음)
- 화면: 카드 7초 갱신(숨김이면 멈춤). 엔진 배지 `ok/delay/unknown` → 「정상」·「지연 · 마지막 판단 N분 전」·「판단 불가」. 운용 탭 버튼 전부 `disabled` + 「2차 공개 때 열림」, 전략·모드·일시정지 읽기. 「구버전으로」 + 「다시 로그인해야 합니다」. 차트 실패 「갱신 실패 · HH:MM:SS」.

- [ ] **Step 1: 실패 시험** — `chart.test.mjs`: `keeps last data on 429`, `single in-flight request`, `skips when hidden`, `orders oldest first`, `marks last candle forming`, `sma60 matches reference`. `test_static_lint.py`: `test_external_hosts_allowlisted`(index·app·chart는 `api.upbit.com`만, backtester는 `data-api.binance.vision`·`api.binance.com`만), `test_vendor_sha256_matches_versions_txt`, `test_operation_buttons_disabled`, `test_no_ma200`, `test_no_stop_word_in_engine_badge`(「정지」 없음).
- [ ] **Step 2: 실패 확인** — `node --test tests/v2/js/` , `python3 -m unittest tests.v2.test_static_lint -v`
- [ ] **Step 3: vendor 받기 (사용자 확인 후 — 외부 내려받기)** — `https://cdn.jsdelivr.net/npm/alpinejs@3.14.1/dist/cdn.min.js`, `https://cdn.jsdelivr.net/npm/lightweight-charts@4.2.0/dist/lightweight-charts.standalone.production.js`, sha256 기록. `.gitignore`(38행 `*.txt`)에 `!v2/static/vendor/*.txt` 예외 추가.
- [ ] **Step 4: 구현**
- [ ] **Step 5: 통과 확인**
- [ ] **Step 6: 412px 실측(A5)** — 로컬 `python3 -m v2.server`(시험 DB) + chrome-devtools 412×915 → `document.documentElement.scrollWidth <= 412`, 스크린샷.
- [ ] **Step 7: 커밋**(버전 갱신) — 커밋 전 `git check-ignore v2/static/vendor/VERSIONS.txt v2/static/vendor/LICENSE-lightweight-charts.txt` 출력 없음·종료 코드 1, `git status`로 두 파일 스테이징 확인.

## Task 7: 백테스터 이식 (Binance 전용)

**Files:** Create `v2/static/backtester.html`, `v2/static/backtester.js`, `tests/v2/js/harness.mjs`, `tests/v2/js/parity.test.mjs`, `tests/v2/js/fixtures/klines_{a,b,c}.json`

**Interfaces:**
- `backtester.js` = 원본 HTML `<script>`(142행 다음 줄 ~ 939행 앞 줄) 본문 **바이트 그대로**. 수정 없음.
- `backtester.html` = 원본 HTML의 마크업·스타일을 그대로 두고 다음만 바꾼다: 인라인 스크립트 → `<script src="backtester.js">`, 데이터 출처 선택(「Binance」 / 「업비트 (KRW) — 준비 중」 `disabled`), 저장 버튼·확인 창 자리(Task 8). 입력 30개(input 24 + select 6)의 id·기본값·min/max/step 은 원본과 같다.
- `harness.mjs`: `runInHarness(scriptText, htmlText, klinesBySymbol) -> {trades, weekly, monthly, sweep, fetchCalls, barCount}` — `vm` 컨텍스트에 가짜 `document`(HTML에서 id별 기본값을 읽은 요소, `innerHTML`·`textContent`·`style` 기록, canvas 는 아래 Proxy), 가짜 `fetch`(고정 klines, 호출 기록), 고정 `Date.now`, 즉시 실행 `setTimeout`/`sleep`을 넣고 `run()`·`runSweep()`을 호출한 뒤 전역 `tradeRows`·`weeklyRows`·`monthlyRows`·`sweepRows`(원본 143행 최상위 `let`)를 `vm.runInContext("csv(tradeRows)", ctx)` 식으로 꺼낸다(`let` 은 컨텍스트 객체 속성이 아님). 가짜 DOM 은 원본이 쓰는 API 를 모두 받는다: `getElementById`·`value`·`innerHTML`·`textContent`·`style`·`addEventListener`·`createElement`·`getBoundingClientRect`(고정 {width:800,height:400,left:0,top:0}), canvas `getContext`는 모든 메서드·속성을 받는 Proxy, `window` 는 컨텍스트 자신(원본 748행 `window.devicePixelRatio||1`), `devicePixelRatio = 1`, `Blob`·`URL.createObjectURL` 은 기록만. `renderChart()`는 592행 try/catch 안이라 오류가 삼켜지므로 실행 뒤 `chartHint` 텍스트에 「차트 렌더링 오류」가 없음을 단언한다(`chart path no error` 시험).

- [ ] **Step 1: 고정 입력 3세트 (사용자 확인 후 — 외부 내려받기)** — Binance klines를 한 번 받아 저장(원본 기본값 1세트 + 심볼·기간 다른 2세트, 받은 시각 기록). `.gitignore`(34행 `*.json`)에 `!tests/v2/js/fixtures/*.json` 예외 추가.
- [ ] **Step 2: 실패 시험** — `parity.test.mjs`: `script body byte-identical to original`(sha256), `defaults identical`(30개 id·기본값·min/max/step), 3세트 × `trades/weekly/monthly/sweep CSV identical`(원본 HTML+스크립트 vs 이식 HTML+backtester.js 를 같은 harness로), `request count and bar count identical`(E19), `chart path no error`(원본·이식 모두 `chartHint`에 「차트 렌더링 오류」 없음).
- [ ] **Step 3: 실패 확인** — `node --test tests/v2/js/parity.test.mjs`
- [ ] **Step 4: 이식** — 화면 체크리스트(spec 4.4): 「데이터 가져오기 + 백테스트」, 스윕(정렬 4종), CSV 4종, 차트(확대·축소·다시 그리기·표시 봉 수), 결과 요약·분할 단계별 누적 통계·주간·월간(KST), 전략 설명 접기.
- [ ] **Step 5: 통과 확인**
- [ ] **Step 6: 속도 측정(E19·A6)** — chrome-devtools performance trace로 원본·이식본 각 3회, 「백테스트」·「스윕」 계산 구간 중앙값 비교(+20% 이내). `measure-20261023.md`에 추가.
- [ ] **Step 7: 커밋**(버전 갱신) — 커밋 전 `git check-ignore tests/v2/js/fixtures/klines_a.json` 출력 없음·종료 코드 1, `git status`로 fixtures 3개 스테이징 확인.

## Task 8: 「저장만 하기」

**Files:** Create `v2/params_schema.py`, `v2/api_write.py`; Modify `v2/static/backtester.html`(저장 버튼·확인 창); Test `tests/v2/test_api_write.py`

**Interfaces:**
- Consumes: Task 1 `pullback_params_path`·`insert_history`, Task 3 Origin 검사, Task 4 status 응답(확인 창 표시용)
- Produces:
  - `PARAM_FIELDS: dict[str, dict]` — 메인 19개 id → `{"type": "number"|"select", "min","max","step" | "options"}`, 값은 원본 HTML 속성 그대로
  - `validate_params(d: dict) -> dict` — 19개 키 정확히, 범위 밖·모르는 키 → `ValueError(field)`
  - `to_engine_file(p, ticker) -> dict` — *(2026-10-24 결정 1024-01 나, spec 4.5·P3 spec 4.2 에 맞춤)* 파일에는 P3 4.2 키 18개만 쓴다: `ticker`(엔진 현재 전략 파일의 업비트 종목, 모르면 409·무변경), `interval`(`1m/3m/5m/1h → minute1/3/5/60`), yes/no 3칸 → bool, `days`·Binance `symbol` 은 파일에 넣지 않음. 이력 `params_json` 은 화면 입력 19개 원본. 정수 칸(HTML step 없음)은 정수만. 「19개 키 정확히·전체 덮어쓰기」는 1차 규칙(P4 거래 시간 키 추가 때 바뀜)
  - `POST /v2/api/params/save` `{"params": {...}, "source": "binance"}` → 검증 → 파일 제자리 쓰기(`open(p, "r+")`, `seek(0)`, `write`, `truncate`, `flush`, `os.fsync`; 파일이 없으면 500 「배포 설정 누락」) → `insert_history`(실패하면 파일을 쓰기 전 내용으로 제자리 되쓰기 후 500) → `{"ok": true, "history_id": n, "saved_at": ...}`
  - `GET /v2/api/params/current` → 파일 내용 + 수정 시각
- 확인 창: 현재 전략·모드(크게)·엔진 상태·보유 포지션 → 「저장만 하기」 버튼 1개(「이 설정으로 동작」은 P4). TEST/LIVE 구분 없음(E9).

- [ ] **Step 1: 실패 시험** — `test_save_writes_only_pullback_file`(EMA·MACD 파일 sha256 불변, A16), `test_save_inserts_v2hist_row`, `test_invalid_param_400_and_file_unchanged`, `test_unknown_key_400`, `test_save_bad_origin_403`, `test_missing_pullback_file_500_no_create`, `test_save_does_not_touch_live_db`(실매매 DB mtime·크기·`settings_history` 행 수 불변, A16·A18)
- [ ] **Step 2: 실패 확인 → Step 3: 구현 → Step 4: 통과 확인**(`bash scripts/regression_gate.sh` 포함)
- [ ] **Step 5: 확인 창 실측(A7)** — 로컬 서버에서 저장 → 확인 창 내용·파일·이력 행 확인, 스크린샷.
- [ ] **Step 6: 커밋**(버전 갱신)

## Task 9: 서비스 유닛·배포 자료

**Files:** Create `deploy/tradebot-v2.service`, `deploy/nginx-v2-location.conf`, `deploy/v2hist-backup.cron`, `scripts/v2/check_v2_unit.sh`, `scripts/v2/a3_memory_probe.sh`, `docs/operations/v2-runbook.md`; Test `tests/v2/test_deploy_files.py`

**Interfaces — 고정값:**
- 유닛: `User=root`, `WorkingDirectory=/root/upbit-tradebot-mvp`, `ExecStart=/root/upbit-tradebot-mvp/venv/bin/python -m v2.server`, `ProtectSystem=strict`, `ReadWritePaths=-/root/upbit-tradebot-mvp/services/data -/root/upbit-tradebot-mvp/mcmax33_latest_params_PULLBACK.json`, `InaccessiblePaths=-/root/upbit-tradebot-mvp/.env -/root/upbit-tradebot-mvp/.streamlit/secrets.toml -/root/upbit-tradebot-mvp/credentials.yaml`, `NoNewPrivileges=yes`, `UMask=0077`, `CapabilityBoundingSet=`, `AmbientCapabilities=`, `MemoryMax=150M`(Task 0), `MemorySwapMax=0`(서버 스왑 4GB — 없으면 상한을 넘겨도 스왑으로 넘어가 엔진까지 느려짐), `OOMScoreAdjust=500`, `Nice=10`, `CPUWeight=50`, `Restart=on-failure`, `RestartSec=5`, `EnvironmentFile` 없음. *(2026-10-25 추가: `PrivateTmp=yes`(strict 에서 /tmp 읽기 전용 — sqlite 임시 파일), `[Unit] StartLimitIntervalSec=300`·`StartLimitBurst=5`(OOM 반복 시 무한 재시작 방지))*
- nginx: `location /v2/ { proxy_pass http://127.0.0.1:8502; proxy_set_header Host $host; proxy_set_header X-Forwarded-Proto $scheme; }` *(2026-10-25 추가: `client_max_body_size 64k;` — v2 저장 API 본문 상한을 앞단에서)*
- cron(매주 일 11:30): `[ -f /root/upbit-tradebot-mvp/services/data/v2hist_mcmax33.db ] && sqlite3 … ".backup …/services/data/backups/v2hist_mcmax33_$(date +\%Y\%m\%d).db" && chmod 600 …`. 오래된 백업은 지우지 않고 정기 점검에서 용량 확인.
- `check_v2_unit.sh`: 실행 중인 `tradebot-v2`의 `systemctl show -p ProtectSystem,ReadWritePaths,InaccessiblePaths,NoNewPrivileges,UMask,CapabilityBoundingSet` 값을 그대로 `systemd-run --wait --pipe -p …`에 넘겨 `venv/bin/python -c`로 7종 검사, 각 줄 `PASS|FAIL|RESIDUAL <항목>`만 출력:
  1. 실매매 DB ro 조회 성공 2. v2hist 쓰기는 `BEGIN; INSERT …; ROLLBACK`으로 성공 여부만(행 남지 않음) 3. `active_strategy.txt` 읽기 성공 4. `.env` 열기 실패 5. 저장소 루트에 새 탐침 파일 만들기 실패(EROFS 기대; 기존 EMA·MACD 파일은 열지 않음) 6. `/proc/<tradebot pid>/environ` 읽기 결과(성공이면 RESIDUAL). 7번은 `systemd-run` 밖 호스트에서: `/proc/$(systemctl show -p MainPID --value tradebot-v2)/environ`의 변수 **이름**만 세어 `UPBIT_` 접두 0개(A14, 값 미출력). 여러 경로 값은 인자 하나로 따옴표 처리.
- `a3_memory_probe.sh`: 같은 속성 + `MemoryMax=150M`·`MemorySwapMax=0`으로 `systemd-run`해 300MB 할당 → 프로브만 OOM 종료, `free -m` 스왑 사용량 증가 없음, 전후 `tradebot` `ExecMainStartTimestamp` 같음(A3).

- [ ] **Step 1: 실패 시험** — `test_unit_has_required_directives`, `test_unit_has_no_environmentfile`, `test_nginx_location_only_v2`, `test_cron_guards_missing_file`, `test_check_script_outputs_status_only`(값 출력 경로 없음: `cat`·`print(open(` 0, 출력 형식 정규식), `test_check_script_never_opens_strategy_params_for_write`
- [ ] **Step 2: 실패 확인 → Step 3: 작성 → Step 4: 통과 확인**
- [ ] **Step 5: 운영 문서** — 즉시 닫기, 계정 추가 절차(빈 PULLBACK 파일 → 유닛 `ReadWritePaths` → `daemon-reload` → 재시작 → `check_v2_unit.sh`), 비밀 파일 점검(`.v2_secret`·`.v2_allowlist`·`v2hist_*.db` 600), `-wal`·`-shm` 600 정상, 동결 파일 2개.
- [ ] **Step 6: 커밋**(버전 갱신) — 점검 스크립트는 `scripts/v2/`(`.gitignore`의 `!scripts/**/*.sh`로 추적)에 둔다. 커밋 전 `git check-ignore scripts/v2/check_v2_unit.sh scripts/v2/a3_memory_probe.sh deploy/tradebot-v2.service deploy/nginx-v2-location.conf deploy/v2hist-backup.cron` 출력 없음·종료 코드 1, `git status`로 스테이징 확인.

## Task 10: 통합 확인과 구현 완료 보고

- [ ] **Step 1: 전체 시험** — `bash scripts/regression_gate.sh`(v2 단계 포함), `node --test tests/v2/js/`.
- [ ] **Step 2: 로컬 실측** — 시험 DB로 `python3 -m v2.server`와 `streamlit run app.py`: 버튼 → 「신버전 열기」 → 입장(A4), 2분 대기 뒤 다시 눌러도 입장, 412px(A5), 비허용 계정 버튼 없음·API 403(A13), v2 프로세스 강제 종료 뒤 구버전 정상(A3 로컬).
- [ ] **Step 3: verifier 검증 → Fable 질의 → 사용자 구현 완료 보고**(배포 diff 범위 표, 「버전: 구 → 신」, UI diff 브리핑, Fable 번들 zip).

## 배포 절 (별도 승인 요청서의 순서 — 이 계획의 Task 아님)

1. 착수 전 정지선. `git diff --stat 156b351 <배포 HEAD>`가 `v2/`·`deploy/`·`ui/v2_entry.py`·`utils/v2_entry_token.py`·`app.py`·`pages/dashboard.py`(버전)·`scripts/regression_gate.sh`·`tests/`·`docs/`·`.gitignore`·`.claude/`·`CLAUDE.md`뿐인지.
2. 감사 로그(*.db) 백업 존재 확인.
*(2026-10-25 순서 정리 — Task 9 verifier: 3 은 선행 파일 생성만, 유닛 설치·기동·점검·nginx·cron 은 4 의 `git pull` 뒤(deploy/ 파일은 pull 뒤에야 서버에 생김). 세부 순서는 `docs/operations/v2-runbook.md` 「설치」. 선행 파일 생성과 `git pull` 은 어느 쪽이 먼저여도 되며, 둘 다 유닛 기동 전이면 된다.)*
3. 서버 설정 변경(승인 대상 목록) — **3 에서 하는 것은 선행 파일 생성뿐**: `.v2_secret` 생성 — `umask 077; venv/bin/python -c "import secrets; open('.v2_secret','wb').write(secrets.token_bytes(32))"` 후 `ls -l .v2_secret; wc -c .v2_secret`만 확인(값 출력 금지), `.v2_allowlist`(`mcmax33`, 600), 빈 `mcmax33_latest_params_PULLBACK.json`(0바이트, 600 — *(2026-10-25 정정: `{}` 이면 확인 창이 생성 시각을 「마지막 저장」으로 보임, 빈 파일이면 「저장 기록 없음」)*). (승인 목록에는 유닛 설치·enable, nginx `location /v2/`, cron 줄, 점검 스크립트 실행도 들어가지만 실행은 4·5 에서.)
4. `git pull` → **`tradebot` 1회 재시작(E1)**: 조건 — 현재 봉 `✅ [CONFIRMED] 봉 처리 완료`(`engine/live_loop.py:1710`) 또는 `[CONFIRMED-NO-TRADE]` 확인, `orders`의 `state IN ('REQUESTED','PARTIALLY_FILLED')` 0건, 다음 봉 경계까지 60초 이상. 재시작 뒤 `[BOOT-RESUME]`, WO-12 결함 태그 0(`docs/plans/2026-09-30-wo12-boot-auto-resume/plan.md:285`), 확정 봉 누락 0(NO-TRADE 제외).
5. 유닛 복사·`daemon-reload`·`enable` → `tradebot-v2` 기동 → `check_v2_unit.sh mcmax33`(A17·A14), RSS(A12), `a3_memory_probe.sh`(A3), `systemctl restart tradebot-v2` 뒤 `tradebot` `ExecMainStartTimestamp` 불변(A2) → nginx `location /v2/`(`nginx -t` → reload) → cron 줄.
6. 3점 일치(로컬·서버 HEAD/버전, `ExecMainStartTimestamp`).
7. 되돌리기: `systemctl disable --now tradebot-v2`, nginx 블록 제거, `git revert` + `tradebot` 재시작(4와 같은 조건·점검). 실매매 DB 변경 없음.
8. 관찰 A15(`journalctl -u tradebot` 429·418·누락 0), 투자자 통보 문안 A(별도 승인)·`investor-notice-log.md`, Fable 번들 zip.

## 수용 기준 ↔ Task

| 기준 | Task |
|---|---|
| A1 구버전 회귀 | 5(AppTest), 8, 10, 게이트 |
| A2 v2 재시작이 tradebot 기동 시각 불변 | 배포 5 |
| A3 v2 실패·메모리 초과 시 v2만 종료 | 9(`a3_memory_probe.sh`), 10 Step 2, 배포 5 |
| A4 재로그인 없이 입장, 「구버전으로」 안내 | 2, 3, 5, 6, 10 |
| A5 412px | 6 |
| A6 결과 동일·속도 | 7 |
| A7 저장·이력·확인 창 | 8 |
| A8~A10 | P3·P4 — 해당 없음 |
| A11 | P4 — 1차는 A14 로 `engine.*` 없음만 |
| A12 상주 메모리 | 0, 배포 5 |
| A13 허용 목록 밖 버튼 없음·403 | 3, 5 |
| A14 업비트·config 경로·환경변수 없음 | 1, 2, 3, 9 |
| A15 429·418·누락 0 | 배포 4·8 |
| A16 DB 파일 미생성·EMA/MACD 불변·ro INSERT 거부 | 1, 8 |
| A17 유닛 보호 실측 | 9, 배포 5 |
| A18 구버전 이력 불변 | 8 |

## spec 정정이 필요한 곳 (사용자 승인 후 spec 반영)

- spec 4.4 「입력 24개」 → 원본은 30개(`<input>` 24 + `<select>` 6; 메인 19, 스윕 10, 차트 1). 「24」는 `<select>` 6개를 빼고 센 값.
- spec 4.5 「TEST 모드 … 기존 `_dry_` 접두사 규칙」 → 코드에 그런 규칙 없음(`scripts/live_dry_run.py`의 별도 user 이름 관례뿐, TEST/LIVE 는 같은 DB). P4 범위라 1차 영향 없음, P4 계획에서 다시 정한다.
- 목차 3판 엔진 import 표에 `ui/v2_entry.py`·`utils/v2_entry_token.py`(동결) 추가.

## 참고 — 기록만 하는 영향
- 「신버전 대시보드」 버튼을 누르면 Streamlit 이 `app.py` 전체를 다시 실행한다. 이때 (1) `[APP-FLOW]` 로그 1행이 실매매 DB `logs`에 기록되고(`app.py:283-291`), (2) `start_health_monitoring`이 불리며(`:294`), (3) LIVE 모드일 때만 접힌 「서버 정보」의 `get_server_public_ip()`(외부 IP 조회 — ipify 등, 업비트 아님, `app.py:349,362`)가 불린다. 구버전의 다른 버튼과 같은 동작이다.
