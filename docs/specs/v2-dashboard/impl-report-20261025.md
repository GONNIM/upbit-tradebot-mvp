# 신버전 대시보드 1차 공개(P1·P2) 구현 완료 보고 (2026-10-25)

**범위:** `docs/specs/v2-dashboard/plan.md` Task 0~10. 서버 배포는 하지 않았다(배포 절은 별도 승인 요청서).
**버전:** 서버 `v1.2026.10.20.1711`(HEAD 156b351) → `v1.2026.10.25.1524`(이 보고를 넣는 Task 10 문서 커밋. 직전 코드 커밋 007ee7f 는 v1.2026.10.25.1429). 배포 diff 숫자(§2)는 156b351..007ee7f 기준이며, Task 10 문서 커밋이 docs·`.gitignore`·버전 줄을 더한다.
**단계:** verifier 1차 「수정 후 승인」 반영본 → verifier 재검증 → Fable 질의 → 사용자 보고 순서. Fable 번들 zip 은 이 보고와 근거 파일을 묶어 Fable 질의 때 만든다(위치·크기·`unzip -l` 은 사용자 보고에 적는다).
**결론:** 계획의 Task 0~9 구현과 Task 10 Step 1·2 통합 확인이 끝났다. 시험은 게이트 exit 0(tests/v2 187 OK, v2 JS 시험 통과, 회귀 350/350)이다. 로컬 실측에서 A4·A5·A13·A3(로컬)이 통과했다. 실매매 엔진 코드는 바꾸지 않았다. 엔진이 읽는 파일 중 바뀐 것은 `app.py` 3줄, 신규 `ui/v2_entry.py`·`utils/v2_entry_token.py`(동결 대상), `pages/dashboard.py` 버전 줄이다. 이 때문에 배포 때 `tradebot` 1회 재시작(E1)이 필요하다.

## 1. 커밋 (156b351 이후, 19개)
| 커밋 | 내용 |
|---|---|
| 0194d57·c212f42·bfeae37·2fa53a0·ee6efc4·0ae470c·0e72cf5 | 설계·승인 요청서·spec·목차·plan·검증 보고·HANDOFF (문서) |
| c47a16c·3060725 | WO-26 배포 기록 문서(서버 HEAD 156b351 이후 커밋, docs 만 — 코드 변경 없음) |
| 477c08b | Task 0 서버 실측(measure) |
| dec2774 | Task 1 v2/db.py |
| c6d4860 | Task 2 입장 토큰·허용 목록·세션 |
| 02c3e0e | Task 3 tornado 서버·입장 인증 |
| 9f6e2db | Task 4 읽기 API·엔진 상태 판정 |
| 194a134 | Task 5 구버전 입장 버튼 |
| 23569db | Task 6 정적 화면 |
| 3d985bb | Task 7 백테스터 이식(Binance) |
| cfbdc3f | Task 8 「저장만 하기」 |
| 007ee7f | Task 9 서비스 유닛·배포 자료 |

(c47a16c·3060725 는 156b351 뒤에 커밋됐지만 v2 작업 전의 문서 커밋이다 — 서버에는 아직 없고 배포 diff 에 포함된다.)

## 2. 배포 diff 범위 (`git diff --stat 156b351 007ee7f`: 135 files, +15,530 / −5)
| 경로 | 파일 수 | 엔진 프로세스가 읽음 | 비고 |
|---|---|---|---|
| `app.py` | 1 | 예 | 3줄 추가(import 1·주석 1·호출 1) — 삭제 0 |
| `pages/dashboard.py` | 1 | 예 | 버전 줄 1줄만 |
| `ui/v2_entry.py` | 1 | 예 | 신규, **배포 뒤 동결** |
| `utils/v2_entry_token.py` | 1 | 예 | 신규, 표준 라이브러리만, **배포 뒤 동결** |
| `v2/` | 9 + static 11 | 아니오 | 신버전 서버·화면·vendor 고정 파일 |
| `deploy/` | 3 | 아니오 | 유닛·nginx·cron 원본(설치는 배포 승인) |
| `scripts/v2/` | 5 | 아니오 | 개발 서버·서버 점검 스크립트 |
| `scripts/regression_gate.sh` | 1 | 아니오 | v2 시험·v2 JS 시험 단계 추가 |
| `tests/v2/`·`tests/regressions/` | 18 + 1 | 아니오 | 시험 |
| `docs/`·`CLAUDE.md`·`.claude/agents`·`.gitignore` | 80·1·1·1 | 아니오 | 문서·규칙·무시 규칙 |

- `core/`·`engine/`·`services/`·`config.py` 변경 0 → 매매 규칙·주문·DB 쓰기 경로 변경 없음.
- plan 배포 절 1 의 허용 목록에 `scripts/v2/` 가 빠져 있다(Task 9 가 그곳에 점검 스크립트를 두도록 정함) — 배포 승인 요청서에서 목록에 더한다.

## 3. UI diff 브리핑 (project-rules 1-A)
- 구버전 입장 화면(`app.py`): 허용 목록 사용자에게만 「📱 신버전 대시보드 (베타)」 버튼이 **추가**된다. 누르면 「신버전 열기 (60초 안에 눌러 주세요)」 링크가 나온다. 링크는 다음 rerun 에서 사라진다. **삭제·접힘은 없다.** 버튼은 「파라미터 설정하기」 바로 위(`app.py:558`)에 들어가므로 허용 계정에게는 그 아래 버튼들이 한 줄 내려간다(expander 밖 — `test_not_inside_expander`). 키 파일이 없거나 깨지면 **화면 변화 없이** 버튼만 숨겨지고 서버 로그에 `[V2-ENTRY] hidden` 경고가 rerun 마다 남는다(`ui/v2_entry.py:16-25`).
- `pages/dashboard.py`: 화면 변화는 버전 문자열뿐이다.
- 신버전(`/v2/`)은 새 화면이다: 홈·차트·로그·운용 표시, 백테스터와 「저장만 하기」.

## 4. 수용 기준 현황
| 기준 | 상태 | 근거 |
|---|---|---|
| A1 구버전 회귀 없음 | 통과(로컬) | 게이트 350/350, AppTest(Task 5) |
| A2 v2 재시작이 tradebot 기동 시각 불변 | 배포 5단계에서 실측 | a3·check 스크립트, 배포 절 5 |
| A3 v2 실패·메모리 초과 시 v2만 종료 | 로컬 통과(kill -9 뒤 구버전 정상) · 서버 미측정 · spec 의 「기동 예외 주입」 시험은 없음(이월) | measure Task 10 절, a3_memory_probe.sh |
| A4 재로그인 없이 입장·「구버전으로」 안내 | 로컬 통과 | measure Task 10 절(재사용 거절·2분 뒤 재입장 포함) |
| A5 412px | 로컬 통과(에뮬레이션, 가로 넘침 0) · 「글자 확대 없음」은 코드 근거(입력칸 16px — `v2/static/style.css:10`, `backtester.html:27`)이고 실기기 확인은 배포 뒤 | measure Task 7·8·10 절, Task 6 실측은 `.superpowers/sdd/plan/progress.md`(111·129행) |
| A6 백테스터 결과·속도 | 통과 | parity 시험, measure Task 7 절(결정 1023-09 가) |
| A7 저장·이력·확인 창 | 통과 | test_api_write, measure Task 8 절 |
| A8 입장만으로 전략 불변 | 통과(코드 근거) — plan 표는 「P3·P4 해당 없음」 | v2 의 쓰기 경로는 PULLBACK 파일과 v2hist 뿐(`v2/api_write.py`, `v2/db.py:98`), 저장 경로에서도 active_strategy sha 불변 시험. 입장 경로를 직접 보는 시험은 없음 |
| A9·A10 | P3·P4 — 해당 없음 | spec 범위 |
| A11 | 1차 부분: v2 서버 import 그래프에 `engine.*` 0(시험) — 나머지는 P4 | `test_server_import_graph_clean`, plan 수용 기준 표 |
| A12 상주 메모리 100MB 이하 | 배포 5단계에서 측정 | import 만 28.6MB(measure Step 3) |
| A13 허용 목록 밖 버튼 없음·403 | 통과(시험+로컬) | test_api_read·test_server, measure Task 10 절 |
| A14 업비트 호출 경로 없음 | 통과(시험) · 서버 환경변수 이름은 배포 때 | import 그래프 시험, check_v2_unit.sh |
| A15 429·418·누락 0 | 배포 뒤 관찰 | journalctl -u tradebot |
| A16 DB 미생성·EMA/MACD 불변·ro INSERT 거부 | 통과 | test_db·test_api_write |
| A17 유닛 보호 실측 | 배포 5단계에서 실측 | check_v2_unit.sh(9항목+호스트 3) |
| A18 구버전 이력 불변 | 부분 통과: 신버전 저장이 settings_history 를 바꾸지 않음(행 수·DB mtime·크기·sha) · 이력 화면·복원·현재 전략 추정의 별도 회귀 시험은 없음(구버전 코드 변경 0 으로 갈음) | test_save_does_not_touch_live_db |

## 5. 사용자 결정 기록 (이번 구현 중)
- 1023-01 가·나·나(개발 서버, signals 병합, UNKNOWN 기준), 1023-05 나(게이트 node 단계 — Task 9 에서 반영), 1023-09 가(속도 측정 방식).
- 1024-01 나(PULLBACK 파일은 P3 4.2 키 18개, 이력은 화면 입력 19개), 1024-03 가(서버만 tp·sl·capital>0, fee≥0).
- 1025-04 가(로컬 실측을 가짜 계정으로 PO 가 진행).

## 5-1. 로컬 실측 중 사건 (2026-10-25 14:40~14:56 실측 중 첫 로그인 시도 때)
- 첫 실측 탭(가짜 루트로 띄운 구버전 127.0.0.1:8501)의 로그인 칸에 **실제 계정 아이디·비밀번호가 채워지고 LIVE 토글이 켜졌으며, 그 뒤 탭이 닫혔다.** PO 가 입력한 값이 아니다. 원인(브라우저 저장 비밀번호 자동 완성 또는 외부 조작)은 확정하지 못했다. 값은 어디에도 기록하지 않았다.
- 관찰·추론·미확인 구분:
  - (관찰) 칸이 채워지기 전, PO 가 페이지를 연 직후 LIVE 체크박스는 꺼져 있었다(`checked:false`). PO 가 가짜 계정 값을 넣고 「로그인」을 누른 뒤 화면에 「아이디 또는 비밀번호가 올바르지 않습니다.」가 나왔다. 그 다음 스냅샷에서 칸에 실제 계정 값이 있었고 LIVE 가 켜져 있었다. 그 직후 탭이 닫혔다.
  - (관찰) 런처 `launch.py` 는 서버를 띄우기 전에 써 두었고, 처음부터 `st.session_state.setdefault("live_mode_toggle", False)` 줄이 있었다. LIVE 가 켜진 것은 런처 기본값 때문이 아니다. 누가 또는 무엇이 켰는지는 **미확인**이다.
  - (관찰) 8501 은 런처 프로세스가 직접 열었다. streamlit 이 「URL: http://127.0.0.1:8501」로 기동했다(포트가 이미 쓰이고 있었다면 기동에 실패한다). `lsof` 로 본 8501 의 PID 는 PO 가 띄운 프로세스다. 서버를 다시 띄우지 않은 같은 8501 에서 뒤에 가짜 계정 devuser 로그인이 성공했다(devuser 는 가짜 credentials.yaml 에만 있다).
  - (추론) 실제 계정 값이 들어간 것은 브라우저 저장 비밀번호 자동 완성이거나 외부 조작이다. 어느 쪽인지는 **미확인**이다.
  - (미확인) 「로그인」을 누른 순간 제출된 값이 가짜였는지 실제였는지는 모른다. 가짜 devuser 값이 제출됐다면 실패할 이유가 없다(뒤에 같은 서버에서 성공). 그러므로 실제 값이 제출됐을 가능성이 있다.
  - (코드 확인) 미인증 상태에서 LIVE 를 자동으로 켜는 경로는 없다. MODE-LOCK(`app.py:191-215`)은 엔진이 돌 때만 값을 바꾸며 이 실측에는 엔진이 없었다. 기본값 True(`app.py:221-222`)는 런처의 setdefault False 가 먼저 실행되어 적용되지 않는다. 그래서 LIVE 켜짐은 화면 조작으로 볼 수밖에 없다. 자동 완성은 입력 칸만 채운다.
- 무해 판단 근거: 어느 값이 제출됐더라도 이 서버의 credentials.yaml 에는 devuser·viewer 만 있다(`setup_root.py` 가 씀). 그래서 실제 계정 로그인은 성공할 수 없고, 화면에 실패 문구가 나왔다. 런처가 `validate_upbit_keys`·`get_server_public_ip` 를 가짜로 바꿔 두어 실제 키 호출·외부 호출 경로가 없었다. 더미 secrets 때문에 실제 `.env` 를 읽지 않는다(`config.py:9-18`). 실측 뒤 가짜 루트를 지웠다. 런처와 로그 사본(더미 값만, 실제 계정 이름 없음)은 scratchpad `t10/` 에 남아 있고 번들 zip 의 launchers/ 에도 들어 있다. 로컬 실매매 DB·.env·secrets.toml·credentials.yaml·전략 파일의 수정 시각은 모두 오늘 이전이다(verifier 확인).
- 처리: 사용자 결정 1025-05 「기록만 하시오. 해당 사안은 크리티컬하지 않다」(2026-10-25) — 이 기록으로 종결, 비밀번호 변경·점검은 하지 않는다.
- 실측 뒤 저장소: 실측이 만든 파일·변경은 0이다. `git status` 에는 Task 10 문서(이 보고·measure 절·Fable 질의서·번들 zip)와 기존 미추적 13개만 있다. 정확한 수는 커밋 직전에 다시 센다.

## 6. 배포 첫 실행에서 확인할 것 (로컬 확정 불가)
- `systemctl show` 의 ReadWritePaths `-` 접두 유지, 빈 CapabilityBoundingSet 표기, systemd-run OOM 문구 — 어긋나면 FAIL 로 드러난다(거짓 통과 없음).
- 서버 SQLite 3.37.2 에서 -wal·-shm 이 없는 WAL DB 를 ro 로 열기(check 의 live-db-ro-read).
- 운영 DB 에서 v2 SQL 7개의 EXPLAIN QUERY PLAN(USE TEMP B-TREE 없음).
- nginx 같은 출처에서 링크 그대로 클릭, https Secure 쿠키·실제 Origin, 실제 계정·LIVE, 실기기 412px.
- 배포 diff 에 동결 파일 2개가 있으므로 `tradebot` 1회 재시작(E1) 조건을 확인한다(배포 절 4).

## 7. 알려진 틈·이월
- v2 는 root 라 권한 비트로 /etc/shadow·/root/.ssh 를 읽을 수 있다(InaccessiblePaths 추가는 다음 판에서 검토). `/proc/<tradebot>/environ` 은 권한 집합을 비워 막힐 것으로 본다(배포 때 RESIDUAL 여부 실측).
- P3: PULLBACK 로더의 깨진 JSON 처리·flock, 저장 6·7단계 사이 프로세스 종료 틈, pullback spec 107행 「원본 run() 과 같게」 정정, spec 4.2 100행 문구.
- 백테스터 Binance 실호출과 확인 창은 배포 뒤 실기기에서 1회 확인한다. 날짜 눈금 UTC 자정, lint 범위, `.gitignore:80` 이 __pycache__ 무시를 되돌리는 문제.
- 구버전 「로그아웃하기」 뒤 쿠키로 다시 로그인되는 기존 동작(이번 변경과 무관, 기록만).
- 입장 토큰이 URL 쿼리(`/v2/?t=`)로 전달돼 nginx 접근 로그·브라우저 기록에 남는다(spec 4.2). 60초·1회용이고 교환 직후 302 로 주소에서 지워지며, 재사용 거절을 실측했다.
- A3 「기동 예외 주입」 시험, A18 이력 화면·복원 회귀 시험은 없다.
- plan 배포 절 1 의 허용 목록에 `scripts/v2/` 추가(배포 승인 요청서에서).
- 실행 에이전트 규칙 위반 누적: 빈 heredoc 10회(Task 8 까지), Bash 파일 수정 2회(Task 8) — 모두 무해·자진 고지, Task 9 이후 0.

## 8. 근거 파일
- 진행 기록 `.superpowers/sdd/plan/progress.md`(git 무시), Task 별 지시서·보고서·verifier 요약 같은 폴더
- 실측 `docs/specs/v2-dashboard/measure-20261023.md`
- Fable 질의 `docs/fable/2026-10-2[2-5]-*.md`
- 운영 문서 `docs/operations/v2-runbook.md`
