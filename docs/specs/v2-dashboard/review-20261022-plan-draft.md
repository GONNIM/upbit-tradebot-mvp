# 검증 보고 — v2 P1·P2 구현 계획서 초안 (2026-10-22)

- 대상: scratchpad `plan-draft.md` 1차본 (이후 `docs/specs/v2-dashboard/plan.md`)
- 검증: `verifier` (읽기 전용, 서버 DB 미열람 — venv 소스·파일 목록·버전만)
- 판정: **수정 후 승인**. 코드 사실 대부분 확인. 구버전 화면 결함 1, 서명 키 노출 절차 1, 실매매 설정 파일을 덮을 수 있는 점검 절차 1, 실행 불가 parity 시험 1.

## 1. 주장별 판정 (요약)
| # | 주장 | 판정 | 근거 |
|---|---|---|---|
| 1~5 | DB 경로 `init_db.py:19-21`, `trading_paused` `db.py:913-926`, `live_loop.py:1710`, `orders.state` 미체결, `app.py` 476-579 버튼 위치 | 확인됨 | 해당 줄. 세션 키 `st.session_state.user_id`(521), `get("mode","TEST")`(543) |
| 6 | `st.link_button(..., key=)` | **반박됨** | Streamlit 1.46 `button.py:546-556` 시그니처에 `key` 없음 → TypeError |
| 7 | 게이트가 `app.py` import 검사, 성공 마지막 줄 `OK` | **반박됨** | 게이트 3단계(pages import, typing, `tests/regressions`). `app.py`·`tests/v2` 대상 아님. 성공 문구 `✅ 회귀 테스트 N/N 통과` |
| 8 | 입력 30개 | 확인됨 | input 24 + select 6 |
| 9 | 스크립트 142~939, 함수 이름 | 확인됨 | 154·246·385·482·618·596행 |
| 10 | 「본문 그대로 + export」로 Node vm 비교 | **반박됨** | `run()`·`runSweep()`이 DOM 에서 설정을 읽고 결과는 전역 변수, `fetchKlines` 는 `$("status")`·`sleep`·`Date.now` 사용 → 가짜 DOM·fetch·Date·timer 필요 |
| 11 | 외부 호스트 api.upbit.com 만 | 반박(lint) | 백테스터는 `data-api.binance.vision`(155)·`api.binance.com`(169) |
| 12~15 | unittest 관례, venv 3.12.8(시스템 3.10.12), tornado `AsyncHTTPTestCase`, Alpine 3.14.1·LWC 4.2.0 실재 | 확인됨 | LWC Apache-2.0 고지 권고, 로컬 tornado 6.4.2 → 6.5.1 맞춤 권고 |
| 16 | 테이블·열 | 확인됨 | `timestamp` 두 형식 혼재, 가격·마커 조회에 ticker 조건 필요 |
| 17 | spec `_dry_` 규칙 없음 | 확인됨 | grep 0 |
| 18 | SameSite=Lax + 302 | 문제 없음 | — |
| 19 | 렌더 때 60초 토큰 생성 | 위험 | 대기 중 만료 → A4 실패 |

## 2. 지적
| # | 심각도 | 지적 | 권고 |
|---|---|---|---|
| 1 | 실매매 프로세스·회귀 | `link_button` `key` TypeError, 게이트 미검출 | `key` 제거, AppTest 렌더 시험 |
| 2 | 보안 | 서명 키 생성 명령이 표준 출력으로 키 출력 | `umask 077` + 파일로 직접, `ls -l`·`wc -c` 만 |
| 3 | 실매매 설정 파일 | `check_v2_unit.sh` 가 EMA params 쓰기 시도·실제 v2hist 행 삽입·속성 수기 복사 | 새 탐침 파일, 롤백 트랜잭션, `systemctl show` 에서 속성 읽기, 실행을 승인 목록에 |
| 4 | 수명주기 | `utils/v2_entry_token.py` 는 엔진 프로세스에 올라감 → 변경 시 엔진 재시작 필요 | 형식 버전, 동결, diff 점검 정지 |
| 5 | A4 | 렌더 시점 토큰 만료 | 누를 때 발급 |
| 6 | A6·A14 | parity 가짜 DOM 등 없음, Binance 호스트 누락 | vm 가짜 document·fetch·Date·timer, 허용 호스트 추가 |
| 7 | 데이터 | cron 이 빈 v2hist(644) 생성 가능, 보존 규칙 없음 | `[ -f ] &&`, `open_v2hist` 항상 CREATE IF NOT EXISTS·chmod 600 |
| 8 | 게이트 | v2 시험이 게이트·pre-push 에 없음, 기대 출력 오기 | 게이트에 v2 단계 |
| 9 | 누락 | V2, A2 절차, A3 시험, A13 버튼 없음 시험, A14 `UPBIT_*`, 조회 시간 제한·인덱스, `app_version` 함수, A7 확인 창 실측 | 각 Task 에 추가 |
| 10 | 개선 | interval 출처(활성 전략 params), 업비트 응답 최신순, Task 0 은 venv python | 명시 |

## 3. 결정 (PO 결정 — spec 범위 안의 구현 선택)
- 토큰 발급 시점: (a) 누를 때 발급(2단계 버튼). spec E6(60초)은 그대로.
- v2 시험 게이트: (a) `scripts/regression_gate.sh` 에 Python v2 단계 추가(Node 시험은 별도 — 서버에 node 없음).

## 4. 재검증 1회째 (수정본) — 판정: 수정 후 승인
- 앞 지적 10건 반영(3·6 보완 남음). 확인: AppTest 로 클릭·`link_button` 실측 가능(`at.get("link_button")[0].proto.url`), 원본 전역 143행 `let tradeRows…`·596행 `csv(rows)`, `systemctl show`→`systemd-run -p` 가능(systemd 249, cgroup2), rw/rwc·제자리 쓰기·서명 키 생성 방식·허용 호스트·spec 정정 3건.
- 반박·지적: (1) 서버 스왑 4,067MB — `MemoryMax`만으로 상한 안 됨 → `MemorySwapMax=0` (2) 게이트 150-159행이 통과 시 `exit 0` → v2 단계는 회귀 단계 앞에 (3) `st.session_state.user_id`(setdefault, 297행)는 계정 전환 때 옛 값 → `username` (4) 점검 7번이 점검 프로세스 자기 environ → 호스트에서 v2 MainPID environ 이름만 (5) 인덱스 시험 규칙이 `ORDER BY id DESC LIMIT` 을 실패로 판정, `audit_trades` `bar_time` 정렬은 TEMP B-TREE → 규칙 변경·마커는 `timestamp` 정렬 (6) 하네스: `let` 전역은 `vm.runInContext`, canvas Proxy, `getBoundingClientRect`·`devicePixelRatio` (7) 기록: 버튼 클릭 시 `app.py` 재실행으로 `get_server_public_ip()`(362행) 호출.
- 메인 세션: 1~7 모두 계획서에 반영.

## 5. 재검증 2회째 (새 verifier, 좁은 범위) — 판정: 수정 후 승인
- (1)~(4) 해소, (6)·(7) 해소(보완), (5) 일부. 새 지적: logs 인덱스(259) 픽스처 누락·로그 SQL 미정, 규칙 「SCAN」 문구 모호(`SCAN t USING INDEX` 와 구분), 픽스처 DDL 원문 일치, 서버 sqlite 버전·실제 인덱스 Task 0 확인, 하네스 `window`·`chartHint` 단언, 참고 절 정밀도(LIVE 때만, `[APP-FLOW]` logs INSERT, `start_health_monitoring`), 게이트 파이프 금지, 로컬 tornado 6.4.2.
- PO 결정: 로그 API 는 `WHERE user_id=? ORDER BY timestamp DESC LIMIT 50 OFFSET ?`(인덱스 사용).
- 메인 세션: 8건 모두 반영.

## 6. 재검증 3회째 — 판정: 수정 후 승인 → 반영 완료
- 지적 1~8·결정 (a) 반영 확인. 새 지적: 픽스처 DDL 범위가 감사 테이블 CREATE(276-368)·ALTER 열(928·942·955·968·981 등)을 빠뜨림(중), Task 7 Step 2 목록에 `chart path no error` 누락(하), canvas 「no-op」·「Proxy」 이중 서술(하).
- 메인 세션: 3건 반영(DDL 범위 134-240·274-368 + ALTER 원문, 시험 목록 추가, Proxy 로 통일).

## 7. 메인 세션 확인
- 로컬 streamlit 1.46.0, `streamlit.testing.v1.AppTest` import 성공, `inspect.signature(st.link_button)` 에 `key` 없음.
