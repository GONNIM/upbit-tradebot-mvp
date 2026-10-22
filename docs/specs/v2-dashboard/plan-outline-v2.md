# 검증 대상: v2 P1·P2 계획서(plan.md) 목차·요지 — 개정 2판 (2026-10-22)

작성자: 메인 세션. plan.md 는 아직 쓰지 않았다. 이 목차의 사용자 승인을 받으려는 단계다.
작업 지시: docs/specs/v2-dashboard/HANDOFF.md 「[3]」
spec: docs/specs/v2-dashboard/spec.md (2026-10-22 개정 반영, 작업 트리 미커밋), docs/specs/pullback-strategy/spec.md
투자자 승인 문서: docs/specs/v2-dashboard/investor-approval-20261021-v2.pdf

## 0. 2026-10-22 운영자 결정 (spec 반영 완료)
- R4: 신버전은 별도 systemd 서비스 `tradebot-v2`. 엔진(`tradebot`)과 시작·정지·재시작이 묶이지 않는다.
- R7: 1차(P1·P2) 백테스터 데이터는 Binance만. Upbit 출처는 P3에서 엔진 기록 확정 봉으로.
- D8: 신버전은 서버에서 업비트 API(시세·계좌)를 부르지 않는다. 근거: 업비트 시세 한도 IP 단위 공유, 429 누적 → IP 단위 418.
- 차트: 투자자 브라우저가 업비트 공개 시세를 직접 호출(200봉, 30초 갱신, 실패 시 마지막 데이터 + 글자 표시, 형성 중 봉 구분). 매매 표시는 DB.
- 잔고·포지션: DB 기록 + 기록 시각 표시. 업비트 계좌 API 호출 없음.
- 1차 공개 통보 문안 A에 「업비트 데이터 준비 중」 포함(재승인 없음).

## A. 작성자가 확인했다고 주장한 사실
F1. 서버 DB는 WAL(services/data/tradebot_mcmax33.db 등).
F2. 서버 nginx 1.18, sites-enabled/tradebot 에 location / → localhost:8501 하나만 있다.
F3. 서버 메모리 available 약 1.39GB, 현재 tradebot RSS 약 240MB.
F4. tornado 6.5.1 이 서버 venv 에 설치돼 있다(Streamlit 의존). starlette/uvicorn 없음.
F5. 구버전 인증 쿠키는 서버 설정(expiry_days: 0, environment="local")상 발급되지 않아 재사용 불가.
F6. candle_cache 테이블은 서버 DB 4개 모두에 없다.
F7. engine_status(user_id, is_running, last_heartbeat) 테이블이 있다(services/init_db.py:221). engine_manager.get_running_mode 는 프로세스 메모리(self._threads)만 본다.
F8. 엔진(core·engine·services)에 429/418 처리 코드가 없다.
F9. 잔고·포지션은 엔진이 DB(accounts, account_positions 등)에 기록한다 — 기록 주기·LIVE 정확도는 미확인.
F10. services/settings_history.py:39-44 의 _SOURCE_PAGES·_STRATEGY_TYPES 화이트리스트에 v2_backtester·PULLBACK 이 없다.
F11. engine/params.py:301-319 scoped_params_path 는 {user}_latest_params_{STRATEGY}.json 을 만든다.

## B. 목차·요지
머리말: 목표·구조(별도 서비스)·스택·spec 경로, Global Constraints(D8 업비트 호출 0, 엔진 무변경, DB 읽기 전용, 허용 목록 밖 403, 412px, 원본 일치, KST), Review Focus.

1단계(코드 무변경) 확인: V1 engine_status heartbeat·잔고 기록의 갱신 주기와 정확도(서버 읽기 전용), V2 휴대폰 브라우저 업비트 직접 호출, V3 tradebot-v2 기동 시 메모리(로컬 측정).

P1 (엔진 무변경)
- T1 v2 서버 골격 + systemd 유닛 초안: tornado, 127.0.0.1:8502, 독립 프로세스. v2/server.py, deploy/tradebot-v2.service. A2·A3·A12
- T2 인증(1회용 토큰: 구버전 입장 화면이 서명 토큰 발급 → v2 세션 쿠키)·허용 목록(서버 전용 파일, 없거나 손상 시 전부 거부). v2/auth.py, v2/allowlist.py. A13
- T3 입장 화면 버튼(허용 계정만, 접힘 금지, UI 1-A·1-B, 회귀 lint). app.py, tests/regressions/. A1·A4
- T4 읽기 API: 상태(engine_status)·자산·포지션(DB + 기록 시각)·신호·거래·로그. 업비트 호출 0 lint(A14). v2/api_read.py
- T5 정적 화면: 홈·차트(브라우저 직접 업비트, 30초)·로그 + 하단 메뉴, 운용 메뉴 1차 숨김, 구버전 링크, 상태 글자 표시, Alpine·Lightweight Charts vendor 고정. v2/static/*. A4·A5

P2 (엔진 무변경)
- T6 백테스터 이식: 원본 JS 그대로, Binance 전용, 업비트 칸 「준비 중」 비활성. Node 로 원본 vs 이식본 3세트 거래 로그 CSV 비교. A6
- T7 「저장만 하기」: 범위 검증, {user}_latest_params_PULLBACK.json(엔진이 읽지 않음 시험), settings_history 화이트리스트 확장(v2_backtester·PULLBACK), 확인 창. A7

배포 절: P1+P2 한 번에. tradebot-v2 유닛 추가·enable, nginx /v2/ 추가는 배포 승인 범위. tradebot 재시작 없음(A2 실측). 3점 일치(로컬·서버 HEAD/버전, ExecMainStartTimestamp). 즉시 닫기 = systemctl stop tradebot-v2 또는 허용 목록 비움. 관찰 A15(엔진 429·418·놓친 봉 0, journalctl -u tradebot). 투자자 통보 문안 A + 기록.
역할·수용 기준 표: 구현 sonnet, 설계·리뷰 opus, 검증 verifier.
Review Focus 후보: 세션 만료·토큰 재사용, 같은 브라우저 계정 전환, DB 기록 지연으로 오래된 잔고 표시, 브라우저 업비트 호출 실패·제한, TEST/LIVE 표시 혼동.

## C. 미결 권고 (사용자 결정 대기)
Q1 인증: 1회용 서명 토큰. Q2 빈 봉 규칙 spec 정정(엔진은 채우지 않고 건너뜀) — P3 범위. Q3 파일 이름 {user}_latest_params_PULLBACK.json. Q4 settings_history 화이트리스트 확장. Q5 P2에 TEST/LIVE 구분 없음. Q6 1차 운용 메뉴 숨김. Q7 tornado.
