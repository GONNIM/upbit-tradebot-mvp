# 질의: 투자자 답(Q1 ①·Q2 ①·Q3 ②)을 받았고, Ver2 반영 계획 목차(2판)를 사용자에게 올리려 합니다

**지금 단계:** 계획 (목차 승인 요청 직전)
**다음에 하려는 일:** 아래 목차와 결정 3건을 사용자에게 올립니다. 승인되면 계획서 본문을 `docs/plans/2026-11-05-ver2-backtester/plan.md` 에 씁니다(새 폴더 — 승인 범위에 포함해 묻습니다). 이번 단계의 작은 문서 변경(HANDOFF·investor-notice-log #9·질문 PDF/html·이 질의 파일)은 묶어서 계획서 커밋 때 함께 올립니다.

**검증 이력:** verifier 1회째(11/05) 「고친 뒤 재검증」 — 사실 7·8 반박, 누락 12건, 지적 8건. 2판에서 모두 반영(아래 「1판 대비 고친 것」).

## 지금까지 확인한 사실
| # | 사실 | 확인/추정 | 근거 |
|---|---|---|---|
| 1 | 투자자 답(11/05 운영자 전달): Q1 ① 받은 파일이 최종판·설명 글에 없던 3가지 모두 넣음, Q2 ① 상승폭 제한은 골든크로스 1차 매수에만, Q3 ② 「새 거래를 시작한 눌림목 매수만 셉니다」 | 확인 | 사용자 메시지, docs/operations/investor-notice-log.md #9, docs/new-version/investor-questions-20261105.html:74 |
| 2 | Q3 ② 는 받은 파일과 다름. Ver2 는 눌림목 체결마다 episodePullbackCount++(474줄, 478줄 firstEntryTime 검사보다 앞) 하고 새 거래 첫 진입 때만 순번을 읽음(480·486줄). Q3 ② 는 `firstEntryTime===null` 인 눌림목 체결 때만 ++ | 확인(코드·verifier) | Ver2 html:354·415·474·478·480·486 |
| 3 | Q2 ① 은 받은 파일 그대로(gcGapOk 는 골든크로스 즉시진입에만, 눌림목 경로 465줄엔 없음) | 확인 | Ver2 html:438-443·465 |
| 4 | 원본 대비 매매 변경 7: 200선 기울기 제거·60선 기울기 필터·G/C 상승폭 제한·연속 SL 중단·구간 눌림목 TP 체감(하한)·데드크로스 기본 no·봉 10/15/30분 | 확인 | diff 원본 2610201820 ↔ Ver2 (512줄) |
| 5 | 원본 규칙에 묶인 곳(verifier grep): 엔진 core/strategy_pullback.py(5·100-157 지표 이력 _h_ma200·_h_slope·621-629·789·817-826), core/strategy_engine.py:1639, engine/live_loop.py:338, engine/pullback_params.py(35·51·56·63 INTERVALS), v2/params_schema.py:12-32·52, v2/control.py:176 SAVED_KEYS, v2/api_read.py:51-57·63, services/terminology.py:140, v2/static/{backtester.html,backtester.js,save.js,bt_ui.js,app.js}, pages/audit_viewer.py(사유 문구 표시), 시험 자료 tests/fixtures/pullback/cfgs.json·tests/v2/js/fixtures/pullback_cfg_base.json, 회귀 시험 16개(tests/regressions 10 · tests/v2 6) | 확인(verifier) | verifier 보고 근거 1~8 |
| 6 | pullback_state 는 24칸, 새로 필요한 4칸이 아직 없음(연속 SL·중단 끝 시각·구간 순번·이번 거래 TP%) | 확인 | services/init_db.py:1016-1039 |
| 7′ | 봉 단위 10/15/30분: live_loop·data_feed·candle_clock·engine/params 는 이미 받음. 막는 곳 = engine/pullback_params.py:63, v2/params_schema.py(src·_INTERVAL), **v2/candles.py:35 UNITS=(1,3,5,15,60,240)(10·30 없음)·105 거절·277 엔진 단위를 1분으로 되돌림**, v2/static/save.js:191-192, bt_ui.js:7·17, backtester.js:14, backtester.html:78 | 확인(PO 재확인 candles.py:35·105·277) | verifier 사실 7. 정정(Fable): 277줄은 캔들 서버의 미리 받기 창 봉 단위(window_units)를 1분으로 되돌리는 곳 — 엔진 매매 봉 단위는 영향 없음(core/candle_clock.py:22·24, engine/params.py:284·286 이미 10·30분 받음) |
| 8′ | 업비트 API 주소 형식 minutes/{unit} 은 10·30 도 받는 것으로 알려져 있으나 우리 v2/candles.py UNITS 가 막음 → 1-3·2-4 에서 UNITS 넓힘. 업비트 공식 문서는 처음엔 못 봤고 Fable 이 확인 | 확인(2026-11-05 Fable 이 업비트 공식 문서에서 unit 1·3·5·10·15·30·60·240, 1회 최대 200개 확인) | v2/candles.py:34-35, https://docs.upbit.com/kr/reference/list-candles-minutes |
| 9 | 우리 백테스터 업비트 경로 = 원본 규칙 backtester.js + 업비트 봉, **최대 30일**(bt_ui.js:196). 투자자 시험 화면은 바이낸스 90일 → 「업비트 −10.5% · 바이낸스 +6.6%」는 규칙·기간이 다를 수 있음 | 코드 확인 / 투자자 사용 조건 추정 | v2/static/backtester.js:87-94, bt_ui.js:193·196, docs/new-version/20261105-ver2-test-01.png·-02.png(조회 기간 90·43,200봉) |
| 10 | 서버 3개 사용자 모두 active_strategy=EMA — 11/05 14시대 PO 가 SSH 읽기(`cat *_active_strategy.txt`)로 확인. 서버 PULLBACK 설정 파일 수는 확인 못 함(자동 모드가 서버 DB·파일 추가 읽기를 막음) | 확인(PO) / 파일 수 추정 | PO SSH 출력: _active_strategy.txt·gon1972·mcmax33 모두 EMA |
| 11 | 메모 규칙: 여러 단계 작업은 모든 단계 로컬 완료 뒤 단일 배포 | 확인 | 메모 feedback_deploy_only_when_complete |
| 12 | 승인 요청서 396줄 「200선이 오르는 중」, 11/04 통보 html 41줄 「200선 상승」 → 체감 변경 통보 필요 | 확인 | investor-approval-20261021-v2.html:396, investor-notice-20261104.html:41 |
| 13 | 질문 PDF 78줄에서 「업비트 결과를 시험 결과와 함께 알려 드리겠다」고 투자자에게 약속함 | 확인 | investor-questions-20261105.html:78 |
| 14 | 설정 칸 수: 19 − 2(minSlope·slopeDrop) + 8 = 25칸(forceRefresh 는 화면 전용) | 확인(verifier) | Ver2 html:685-699 |

## 계획 목차 (2판)
0. 확정 사항 — 기준 파일 Ver2 html + 투자자 답 Q1 ①·Q2 ①·Q3 ②. 실계좌 개방은 범위 밖.
1. 1단계 백테스터(로컬, 실매매 무관)
   1-1 계산(backtester.js)을 Ver2 규칙으로 — 매매 변경 7가지, Q3 ②, 결정 2
   1-2 화면(backtester.html·bt_ui.js·save.js) — 입력 25칸·스윕 60선 축·1000조합·진행률·차트 라벨·휴대폰 −/+·캐시 키에 데이터 출처 포함·결과표 2줄·CSV 칸·이름
   1-3 봉 10/15/30분 — v2/candles.py UNITS 넓힘(업비트 직접 받기), 바이낸스 10분만 합성, 화면 봉 표(bt_ui·save·backtester)
   1-4 시험 — 기준 html 을 Ver2 로(parity.test.mjs·pullback_reference.mjs·test_api_write.py·cfgs.json·pullback_cfg_base.json), 회귀 시험 16개 갱신, 참고 구현에 Q3 ②·결정 2 차이를 명시
   1-5 로컬 실측 보고 — 투자자 시험 조건(3분봉·90일·43,200봉, 연속 SL 중단 0·구간 눌림목 횟수 0·상승폭 제한 2.0%·분할 1회·익절 2.5·손절 3·눌림목 기준선 60 / 120)으로, 같은 Ver2 규칙·같은 기간(기간은 결정 3-1 에 따름 — 늘리면 bt_ui.js:196 과 v2/candles.py:36 MAX_DAYS 두 곳)으로 업비트 KRW-JTO ↔ 바이낸스 jtoUSDT, 투자자 설정 2개. 업비트 요청 수 기록. 결과를 투자자에게 보낼지는 결정 3
2. 2단계 엔진·저장(로컬)
   2-1 입력 검증·설정 파일·저장본 판정 — params_schema 25칸, pullback_params 키·INTERVALS, control.SAVED_KEYS, 하한값 검증(TP 하한 등)
   2-2 엔진 판정 Ver2 규칙 + JS 와 결과 같음 시험. Q3 ② 순번은 **entry_count 를 올리는 자리(strategy_pullback.py:767-770)에서 entry_count==0 인 눌림목 매수일 때만 함께 올리고, `_UNDO_KEYS`(633줄)에 넣어 주문 실패·3봉 쉼 때 rollback_last_buy(513-524)로 되돌림** — 모의 모드(체결 콜백 없음)와 실계좌가 같게 동작하고 JS 대조 시험이 엔진 없이 가능. 강제 매수(회차 밖)로 연 거래의 눌림목은 entry_count>0 이라 세지 않음. 골든크로스 1차는 순번을 올리지도 읽지도 않고 기본 TP. 대조 항목: 상승폭 제한으로 막힌 골든크로스 봉은 같은 봉에서 눌림목 판정을 이어 감(Ver2 438-466)
   2-3 상태 — pullback_state 칸 추가(연속 SL 수·중단 끝 시각·구간 순번·이번 거래 TP%, 기동 때 _safe_alter 방식). 중단 해제는 「봉 시각(KST 명시) ≥ 끝 시각」에서 연속 SL 수 0 과 함께 저장. **지표 증분 상태에 60선 기울기 이력 추가·재시작 되살리기**(strategy_pullback.py:100-157). **재생(워밍업·BACKFILL)과의 관계(칸별 소속):** 연속 SL 수·중단 끝 시각·구간 순번·이번 거래 TP% 를 `_SPLIT_DEFAULTS` 에 넣고(링 버퍼 스냅샷 자동 포함), 연속 SL 수·중단 끝 시각·구간 순번은 `SPLIT_TRADE_KEYS`(strategy_pullback.py:388)와 `live_loop._PULLBACK_TRADE_KEYS`(371)에 넣어 재생의 가상 손절(trade_origin="replay")이 실매수를 막거나 실거래 중단 상태를 지우지 못하게 함. 구간 순번·이번 거래 TP% 는 `_UNDO_KEYS` 에도 넣음. 중단 끝 시각은 `_TS_KEYS`(386)에 넣어 KST 문자열로 저장·복원. **연속 SL 은 봇 매도가 체결(또는 접수)된 뒤 셈, 매도 거절이면 세지 않음**(09-30 JTO 거절 사례 — strategy_pullback.py:736-738 은 신호 봉에서 거래를 정리). **이번 거래 TP%** 는 익절 판정(708줄 c["tp"])과 전략 take_profit 속성(503) → 감사 행 TP(strategy_engine.py:3077-3086, position.take_profit_override 와 같은 자리)가 같은 값을 읽게 함
   2-4 엔진 봉 단위 10/15/30분 허용(pullback_params INTERVALS, v2/candles.py UNITS 를 넓혀 10·30분이 277줄 검사를 통과하게 함 — 1분 안전 기본값은 유지) + 확정 봉 재시도(Issue #8) 확인
   2-5 옛 설정(200선 기울기 값) 처리 — 결정 1. 옛 파일 읽기 시험
   2-6 화면·로그·감사 문구 — 감시 밖 사유 새 이름(예: ma60_slope_low·ma60_slope_drop), 옛 감사 행(200선 기준)은 옛 문구 유지, api_read·terminology·app.js·audit_viewer·strategy_engine:1639·live_loop:338 감사 칸
3. 검증·배포(단일 배포, 별도 승인) — scripts/regression_gate.sh, pages/dashboard.py 버전 갱신(v2/static 도 런타임 파일), UI 1-A·1-B 브라우저 실측·접힘 화이트리스트, verifier → Fable → 배포 요청서
4. 투자자 체감 변경 통보 — 「200선 상승」 문구 정정, 새 기능 설명, 통보 기록

## 1판 대비 고친 것
- 사실 7·8 정정(v2/candles.py UNITS), 사실 5 누락 12건 반영, 사실 9 에 30일 한도, 사실 13·14 추가.
- 지적 1(10·30분 거절) → 1-3·2-4. 지적 2(60선 이력) → 2-3. 지적 3(중단 해제 조건) → 2-3. 지적 4(체결 뒤 셈·강제 매수) → 2-2. 지적 5(버전·게이트) → 3. 지적 6(사유 이름) → 2-6. 지적 7(투자자에게 업비트 결과 발송) → 결정 3. 지적 8(기간 조건) → 1-5.

## 사용자 결정 (안)
- 결정 1 옛 설정의 200선 기울기 값(minSlope·slopeDrop): 버림(권고) / 60선 값으로 옮김 / 200선 조건을 선택 칸으로 남김 / 그대로 둠
- 결정 2 결과표 「상승폭 때문에 건너뛴 횟수」가 실제로는 사지 않았을 골든크로스도 셈(감시 밖·중단 중·마지막 봉): 실제로 건너뛴 것만 세도록 고침(권고) / Ver2 그대로
- 결정 3-1 업비트 백테스트 최대 기간 30일 → 90일로 늘릴지: 늘림(권고 — 투자자 시험과 같은 90일 비교. 3분봉 90일 216회 요청·약 54초, 1분봉 90일 648회·약 3분, 초당 4회 한도 그대로) / 그대로 둠(30일끼리 비교)
- 결정 3 1-5 업비트 비교 결과를 투자자에게 보낼지: 보냄(권고 — 질문 PDF 에서 약속, 연락 원칙 예외로 기록) / 보내지 않음. 실패할 이유: 업비트 30일·바이낸스 90일처럼 조건이 다르면 같은 조건 비교로 오해받을 수 있음 → 보고에 기간·결정 2 적용 여부를 함께 적음

**verifier 2회째(11/05):** 「사용자 보고 가능」. 권고 문구 1·2·4·5 와 누락 3(MAX_DAYS)·참고 6 을 위에 반영함.

## 물어볼 것
| # | 질문 | PO의 생각 |
|---|---|---|
| 1 | Q3 ② 해석과 2-2 의 엔진 셈 규칙(체결 뒤·entry_count==0·강제 매수 제외)이 맞는가 | 맞음 |
| 2 | 1단계 결과를 엔진 작업 전에 보고하고 단일 배포로 묶는 순서가 맞는가 | 메모 규칙과 맞고, 업비트 결과가 나쁘면 2단계 전에 멈출 수 있음 |
| 3 | 2판에서도 빠진 영향 범위가 있는가 | — |
| 4 | 결정 1~3 권고가 타당한가 | 결정 1: 지금 PULLBACK 운용자 없음(사실 10) |

## 참고 파일
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/new-version/MA_GC_Pullback_Backtester_2611051030(Ver2).html
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/new-version/investor-questions-20261105.html
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/MA60_200_GoldenCross_Pullback_Backtester_2610201820.html
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/core/strategy_pullback.py
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/engine/pullback_params.py
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/v2/params_schema.py
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/v2/candles.py
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/services/init_db.py
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/CLAUDE.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/.claude/context/project-rules.md

---

# 답변 (Fable 1회째, 11/05)

**판정:** 수정 후 진행
**이유:** 사실 1~14 결론을 뒤집는 오류 없음. 2-3 의 새 상태 4칸과 재생(워밍업·BACKFILL)의 관계가 없어 실매수가 재생 때문에 막히거나 중단 상태가 사라질 수 있음(막음 1).
- 질문 1 맞음(높음) — 단 순번은 체결 콜백이 아니라 entry_count 올리는 자리 + _UNDO_KEYS. 질문 2 맞음(높음) — 1단계만 먼저 배포하면 화면 25칸·엔진 18키 불일치. 질문 3 빠진 것 4가지(재생 관계·이번 거래 TP% 읽는 곳·연속 SL 셈 시점·상승폭 막힌 봉의 눌림목 판정). 질문 4 결정 1~3 타당(보통), 30일 → 90일 요청 수 계산.
- 막음 1: 2-3 칸별 소속. 권고 2~8: 순번 위치, 연속 SL 셈 시점, take_profit 읽는 곳, 대조 항목, 사실 8′ 확인 처리, 사실 7′ 277줄 뜻 정정, 1-5 조건·요청 수.
- 사용자에게: 결정 3 에 30일 → 90일 선택지, 결정 1 에 「11/05 14시대 SSH 읽기 기준」 날짜.

**PO 반영(같은 파일 위쪽 고침):** 막음 1 → 2-3 칸별 소속·_TS_KEYS·_UNDO_KEYS. 권고 2 → 2-2. 권고 3·4 → 2-3. 권고 5 → 2-2 대조 항목. 권고 6 → 사실 8′. 권고 7 → 사실 7′. 권고 8 → 1-5 조건, 결정 3-1(90일). PO 가 strategy_pullback.py:380-389·633·565-568, live_loop.py:371·421·437 을 직접 읽어 인용이 맞음을 확인.

# 다시 묻기 (2회째)
**물어볼 것:** 막음 1 과 권고 2~8 을 위와 같이 반영했습니다. 사용자에게 올려도 되는가.

# 답변 (Fable 2회째, 11/05)

**판정:** 진행
**이유:** 막음 1·권고 2~8 이 인용 줄 그대로 반영됨. 1-5 기준선 60/120 이 투자자 그림 두 장과 맞음. 권고 2건(사실 8′ 칸 어긋남·1-5 중복 문구)은 PO 가 반영함.
- 사용자에게 물어야 할 것: 없음(결정 1·2·3-1·3 은 질의서대로 올림).
