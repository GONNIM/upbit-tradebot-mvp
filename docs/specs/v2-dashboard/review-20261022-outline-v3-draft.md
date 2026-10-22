# 검증 보고 — v2 P1·P2 계획 목차 3판 초안 (2026-10-22)

- 대상: 당시 scratchpad `plan-outline-v3-draft.md` (이후 `docs/specs/v2-dashboard/plan-outline-v3.md` 로 기록)
- 검증: `verifier` 역할(읽기 전용, 서버 SSH 읽기 전용)
- 판정: **수정 후 승인**. F1~F13 과 코드 인용은 대부분 확인됨. 반박 2건(V1 기대값, Global 「예외 2개·쓰기 1문장」), 설계 전제 오류 3건(E8 CHECK 제약, E3 출처 공백, import 표 누락).
- 메인 세션 재확인: `services/init_db.py:583-588` CHECK 원문, `services/settings_history.py:418-428` 최신 행 추정, 서버 `services/data/` 파일 목록(mcmax33 `-wal`·`-shm` 은 엔진이 닫아 사라짐).

## 1. 주장별 판정 (요약)
| # | 주장 | 판정 | 근거 |
|---|---|---|---|
| F1 | WAL, ro 연결도 -shm 필요 | 확인됨(보강) | 서버 4개 `wal`. verifier 의 `sqlite3 -readonly` 조회로 mcmax33 `-wal`(0B)·`-shm` 이 16:49:25 생성(root 644, 이후 엔진이 정리). busy_timeout 없을 때 `database is locked` 1회 |
| F2~F9, F11, F12 | (초안 그대로) | 확인됨 | nginx 1.18·CSP 0, available 1382MB·RSS 204MB·cgroup 237MB, tornado 6.5.1, `expiry_days: 0`·`environment="local"`, OHLC 0, engine_status 기동 시각 고정, 429·418 0건, `order_reconciler.py:23,27`·`db.py:2327-2335`, `params.py:301-319`·`config.py:1-21`, `config.toml:2`·`tradebot_boot.py:44-67` |
| F10 | 허용 목록 `settings_history.py:39-44`·`:95-99` | 확인됨(불충분) | **서버 DB `settings_history` 에 `CHECK (source_page IN (...))`·`CHECK (strategy_type IN ('MACD','EMA'))`** (`init_db.py:583-588`, 서버 default·gon1972·mcmax33 `sqlite_master.sql`) |
| F13 | 늦은 import `live_loop.py:775`, `trader.py:314` | 확인됨(표 불완전) | pages 3곳 추가 |
| V1 기대값 | 「1분봉 기준 audit_buy_eval 1~2분 이내」 | **반박됨** | 서버 interval `minute3`. 24시간 312행 중 6분 초과 간격 35회, 최대 282분(10-21 20:27:12→10-22 01:09:11) = 보유 기간(BUY 20:27:14 ~ SELL 01:06:13) |
| Global | 「엔진 코드 무변경 예외 2개」「DB 쓰기 INSERT 1문장」 | **반박됨** | CHECK 때문에 E8 은 스키마 변경 또는 별도 테이블 필요. `ensure_schema` 는 DB 호출마다(`init_db.py:402` 주석) |
| T8 복원 시험 | 복원이 EMA·MACD 파일을 덮지 않는지 | 일부 | 복원은 `_scoped_params_path(user,"PULLBACK")` 만 씀(`:487-494`). 그러나 `_resolve_active_strategy`(`:418-428`)가 최신 행으로 현재 전략 추정 |
| import 표 「v2/* 엔진 import 없음」 | | 미확인(조건부) | `app.py` 가 토큰 생성에 `v2/*` 를 import 하면 거짓. 금지 문구 없음 |
| S1 (a) | root + ProtectSystem·ReadWritePaths·NoNewPrivileges | 일부 반박 | ProtectSystem 은 읽기를 막지 않음 → `.env`·`secrets.toml`·`/proc/<엔진>/environ` 읽기 가능(`tradebot.service.d/override.conf` `EnvironmentFile=.env`). 없는 경로를 ReadWritePaths 에 넣으면 기동 실패(`-` 접두사 필요). 파일 단위 바인드는 rename 원자 쓰기 불가. systemd 249: `ProtectProc`·`InaccessiblePaths` 사용 가능 |
| S1 (b) | 전용 계정은 엔진에 영향 | **반박됨(방향 오류)** | 엔진은 root 라 무관. 부담은 v2 쪽(`/root` 700 ACL, data 폴더 쓰기, 비밀 파일 600·root 와 충돌) |
| S2 | +20% | 확인됨 | 수신 시간과 계산 시간을 나눠 재기 권고 |
| C1-14 | 지적 14 해결 | 일부 반박 | spec 4.5:140 「`record_snapshot` 으로 이력」 잔존 — `record_snapshot` 은 config import(`settings_history.py:18`) → E2 와 충돌 |

## 2. 지적 (심각도 순)
| # | 심각도 | 지적 | 권고 |
|---|---|---|---|
| 1 | 실매매·데이터 | E8 은 스키마 변경 없이 불가. `init_db.py` 마이그레이션에 넣으면 엔진의 잦은 `ensure_schema` 경로에서 948MB 실DB 에 `writable_schema`·`integrity_check` | 사용자 결정(결정 1). 시점·백업·integrity_check 시간·되돌리기 명시 |
| 2 | 실매매(표시 오도) | E3 출처 `audit_buy_eval` 은 보유 중 기록 없음(282분 공백). TEST 는 `accounts.updated_at` 도 멈춤 | `audit_sell_eval` 병용(최신값), 임계 = 봉 단위 × N. V1 기대값 정정, spec E3 개정은 승인(결정 2) |
| 3 | 보안 | S1 (a) 에 키 차단 수단 없음 | `InaccessiblePaths=`(.env·secrets.toml·credentials.yaml), `ProtectProc=invisible`, `-` 접두사 또는 빈 PULLBACK 파일 선생성, 제자리 쓰기. 시험: v2 안에서 `.env` 열기·`/proc/<pid>/environ` 읽기 실패 |
| 4 | 데이터·회귀(A1) | PULLBACK 행이 최신이면 구버전 EMA 복원 차단·틀린 경고, PULLBACK 복원 시 텔레그램 CRITICAL, 스냅샷 손익에 라벨 NULL EMA 거래 섞임(`settings_history.py:418-428,457-464,513-529,601-620`, `pages/settings_history.py:485-490`) | T8 회귀 시험 3경로 명시. 판정 함수 수정은 결정 3 |
| 5 | spec·설계 불일치 | 경량 INSERT 와 `record_snapshot` 불일치 가능(saved_at KST ISO, app_version 정규식, params_json 원문, conditions_json·applied_at NULL). spec 4.5:140 잔존 | 컬럼 비교 시험, spec 4.5 정정 |
| 6 | 누락(import 표) | `pages/dashboard.py`(버전, `settings_history.py:46,81-92` 가 실행 중 읽음), `services/init_db.py`(결정 1 경로), `pages/settings_history.py`(고칠 경우), `app.py` 가 import 할 토큰 모듈. 배포 diff 허용 목록에 `.gitignore`·`.claude/`·`CLAUDE.md` 누락 | 표 행 추가. 「`app.py` 는 `v2/*` import 금지(hmac 표준 라이브러리만)」 제약·lint |
| 7 | 누락(되돌리기) | 엔진 쪽 변경(`app.py`, `settings_history.py`, 스키마) 되돌리기 절 없음. 되돌려도 PULLBACK 행 잔존 | 되돌리기 절: git revert, tradebot 재시작 점검, 스키마·잔존 행 방침 |
| 8 | 누락(수명주기) | `app.py` 가 서명 키·허용 목록을 읽다 예외 → 구버전 전체 중단 가능 | try/except 로 버튼 숨김, 키 값 비기록. 시험: 없음·권한 오류·손상 |
| 9 | 보안 | 차트 JS 의 업비트 호출 Referer 에 `?t=` 토큰 노출 가능. 쓰기 API CSRF 대책 없음 | 토큰 수신 직후 302 로 주소에서 제거, `Referrer-Policy: no-referrer`, 쓰기 API Origin 검사 또는 CSRF 토큰 |
| 10 | 누락(spec 4.3·4.4·8) | 카드 5~10초 갱신·숨김 탭 정지(차트만 있음), 상태 글자 표시, 4.4 기능 목록, A6 CSV 4종, 4.7 대응(P4 범위, A11 일부 「v2 에 engine.* 없음」) | T6·T7 체크리스트, C 절에 4.4·4.7 행 |
| 11 | 누락(E1 절차) | 「놓친 확정 봉 0건」 판정 기준 없음, 3분봉 경계 미명시, 착수 전 표준 정지선 없음 | WO-12 판정표 인용, 3분봉 경계, 1단계 앞에 정지선 |
| 12 | 개선 | 쓰기 연결 `mode=rw` URI·`journal_mode` PRAGMA 미송신, 인덱스 확인 누락 | T2 에 명시 |
| 기타 | 규칙 | 배포 전 체크리스트 「감사 로그(*.db) 백업」 누락 — 스키마 변경 시 필수 | 배포 절 추가 |

## 3. 영향 범위 (요약 — 2판 표 대비 바뀐 축)
| 축 | 변화 |
|---|---|
| 자격증명 | root 실행 시 `.env`·`/proc/<엔진>/environ` 읽기 가능 → InaccessiblePaths·ProtectProc 필요 |
| DB | ro 연결도 -wal/-shm 생성(관측). E8 스키마 변경 시 실DB 손상 위험 → 백업·리허설·integrity_check |
| 수명주기 | 되돌리기에도 tradebot 재시작 필요 |
| 설정 이력 의미 | 최신 행을 구버전이 현재 전략으로 씀 → EMA 복원 차단·오경고·CRITICAL 알림 |
| 설정 파일 | 엔진 미참조 확인(`live_loop.py:531-550` 자기 전략 조건 파일만 감시) |

## 4. 결정 대기 (사용자)
| # | 결정 | 선택지 | verifier 권고 |
|---|---|---|---|
| 1 | E8 실현 방식 | (a) 1차 배포 tradebot 정지 구간에 수동 1회 마이그레이션(백업·integrity_check·별도 승인) (b) `init_db.py` 자동 마이그레이션 (c) v2 전용 이력 테이블 신설, E8 개정 | (a) 또는 (c). (b) 피함 |
| 2 | E3 출처 보완 | (a) buy·sell eval 최신값 + LIVE accounts, 임계 봉 단위×N (b) 현행 + 보유 중 「판단 불가」 | (a) |
| 3 | PULLBACK 행의 구버전 현재 전략 추정 영향 | (a) 회귀 시험 + 문구 안내 (b) `_resolve_active_strategy` 에서 PULLBACK 제외 (c) 결정 1-(c) 로 회피 | 결정 1과 함께 |
| 4 | S1 실행 계정 | (a) root + InaccessiblePaths·ProtectProc·ReadWritePaths(`-`/선생성) (b) 전용 계정 + ACL·그룹 권한 | (a) 보강안 |
