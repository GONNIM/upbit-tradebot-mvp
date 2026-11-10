# 질의: 1109-01(눌림목 실계좌 열기) + 1110-01(눌림목 추적 손절) 묶음 구현·내부 시험을 마쳤고, 커밋·배포 승인을 다시 요청하려 합니다

**지금 단계:** 구현·테스트 끝 · verifier 3회째 「사용자 보고 가능」(11/10). 1회째 막음 B1(백테스트 요약·메뉴얼 문장)·B2(되돌리기 DB 5칸), 2회째 막음 B3(절차 1번이 비율 키를 늘 지움) → 글·절차만 고침, 코드 무변경(diff 46 files +1678 −254 동일, 게이트 verifier 직접 실행 RC 0: 회귀 1472·v2 464·JS 199·바깥 연결 0). 남은 권고 R2~R6·R9(고정폭 폭 설명)는 다음 작업 후보 · 사용자 결정 「㉠ 꺼짐으로 넣음」(11/10)
**다음에 하려는 일:** 사용자에게 묶음 결과·백테스트 비교 숫자·메뉴얼을 보고하고 커밋·배포 승인을 요청. 승인되면 dashboard 버전 갱신 → 커밋 2개(1109-01 · 1110-01, Fable 권고 3) → push(게이트) → 표준 정지선 → 실행 직전 질의 → 미보유 때 tradebot·tradebot-v2 재시작.

사용자 결정(11/10): 「㉠ 한 묶음 · ㉡ 늘 팜 · ㉢ 막음」. 계획: /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/fable/2026-11-10-pullback-trailing-plan-1.md

## 1110-01 구현 요지
| # | 내용 | 파일 |
|---|---|---|
| 1 | 백테스터: Ver2 원문에 「1110-01」 차이 8곳(상태 칸·청산 초기화·판정·㉢ continue·통계·결과 행·이름·설정 3칸 읽기), 화면 3칸(끔/켬·비율/고정폭·폭 1~100, 기본 끔) | tests/v2/js/fixtures/ver2_patches.json, v2/static/backtester.js(재생성), v2/static/backtester.html |
| 2 | 판정: 이 거래가 켬으로 열렸을 때만(trade_ts_mode) — 익절가에서 팔지 않고 종가로 무장, 손절(저가) → 추적 손절(종가) 순, 사유 TRAILING_STOP. 시간 밖 「익절 막음」과 무관(㉡). 무장 중(막 무장한 봉 포함) buy_block TS_ARMED(㉢) | core/strategy_pullback.py (trailing_advance·_fix_trade_trailing·_step) |
| 3 | 설정 고정: 새 거래를 열 때 3키를 거래 칸에 고정(보유 중 변경은 다음 거래부터), 매수 되돌리기 칸에도 포함 | core/strategy_pullback.py _UNDO_KEYS·SPLIT_TRADE_KEYS |
| 4 | 설정 파일: TRAILING_KEYS(ts_on·ts_mode·ts_pct) 따로 묶음, 있을 때만 결과에, 일부·틀림 거부. 저장 API 선택 필드 trailing — 켬이면 3키 쓰기, 끔이면 지움, 없으면 보존 | engine/pullback_params.py, v2/params_schema.py, v2/api_write.py, v2/static/save.js, engine/pullback_apply.py ALL_KEYS |
| 5 | DB: pullback_state ADD COLUMN 5칸(trade_ts_mode·trade_ts_pct·ts_armed·ts_peak·ts_fixed), 저장·복원 사전, 청산 초기화 SQL, live_loop._PULLBACK_TRADE_KEYS | services/init_db.py, services/pullback_state.py, core/strategy_engine.py, engine/live_loop.py |
| 6 | 재시작 따라잡기: 저장 봉 뒤 ~ 워밍업 끝 확정 봉 종가로 무장·최고가만 전진(Fable 권고 2) | core/strategy_engine.py _pullback_trail_catchup |
| 7 | 사유·라벨: TRAILING_STOP「추적 손절」·TS_ARMED「추적 손절 대기 — 추가 매수 멈춤」·trigger_key | services/terminology.py, v2/api_read.py, v2/static/labels.js, core/strategy_engine.py, core/pullback_audit.py |
| 8 | 고정 시험: strategy_pullback AST 고정은 「지금 파일 − 1110-01 모양(정해진 규칙) = 기준 c0559e3」으로 바꿈, 줄 범위 상한 삭제, 변이 4건 추가. 백테스터 바이트 고정은 차이 목록에 1110-01 8곳 | tests/regressions/test_r_2026_10_30_1029_09_off_hours_tp.py, baseline_commits.py, tests/v2/js/parity.test.mjs |
| 9 | 메뉴얼 3절 「추적 손절」 추가, 1쪽 유지 | docs/new-version/pullback-live-manual-20261110.html/.pdf |

## 지금까지 확인한 사실
| # | 사실 | 확인/추정 | 근거 |
|---|---|---|---|
| 1 | 게이트 종료 코드 0: 회귀 1472/1472, v2 464, JS 199, 바깥 연결 0 | 확인(11/10 13:47, 포크 실행) | scratchpad gate-1110.log |
| 2 | 엔진 = 백테스터: 업비트 공개 봉 3세트(JTO 3분 30일·BTC 1분 7일·ETH 3분 30일) × 15조합(추적 손절 비율 50%·고정폭 30% 포함) 매수·매도 봉·사유 완전 일치 | 확인 | test_r_2026_10_28_p3_t10_parity, tests/fixtures/pullback/expected (기존 39개는 sha 줄만 바뀜) |
| 3 | 추적 손절 식 = 구버전 TrailingStopFilter: 무작위 400경우 × 2방식 같은 매도 봉 | 확인 | test_r_2026_11_10_trailing.TestFormulaSameAsOldFilter |
| 4 | 꺼짐이면 기준(Ver2 + 1105-06) simulate 와 거래·손익 같음(무작위 25종) | 확인 | tests/v2/js/trailing.test.mjs |
| 5 | 켬/끔 비교(자료 3종 × TP 1·2% = 6경우): 자료와 폭에 따라 나아지기도 나빠지기도 함, 일관된 개선 없음. 끔보다 나은 경우: JTO TP1 비율 30%(−16.62%)·고정폭 30%(−15.05%) vs 끔 −19.25%, BTC TP1 비율 50%(−3.19%) vs −3.70%, ETH TP2 비율 30%(−16.97%) vs −17.01%, JTO TP1 고정폭 50%(−17.27%) vs −19.25%. BTC TP2 는 모든 켬 조합이 끔과 같음(−6.40%). 폭 90%(투자자 EMA 설정과 같은 값)는 5경우 끔보다 나쁘고 BTC TP2 1경우 같음(−6.40%) | 확인(백테스터, Ver2 화면 기본값 — 투자자 실제 눌림목 값은 모름 · verifier 지적 B1 로 정정) | scratchpad ts_compare.md |
| 6 | 화면 412·360·1440 LIVE·TEST: 3칸 보임, 가로 스크롤 없음, 저장 창 「추적 손절: 켬 · 고정폭 90% (다음 거래부터 적용)」, 저장 요청 본문 trailing 실림(코드 save.js:67·74-76). 콘솔 오류 0 은 구현 보고뿐 | 그림 확인 · 콘솔 오류는 미확인(verifier) | scratchpad ui-check/ts_*.png |
| 7 | 메뉴얼 1쪽, 나눔고딕 3종 emb yes, 렌더 확인. B1·R1 반영해 3절 고침(종가 기준 무장 · 장중 고가만 닿으면 따라가지 않음 · 「일관된 개선 없음, 폭 90% 는 같거나 나쁨」), 본문 글자 9.9→9.7pt 로 1쪽 유지 | 확인(11/10 PO 재렌더 · 그림 직접 봄) | pdfinfo·pdffonts·pdftoppm |
| 8 | EMA 경로: sell_filters·strategy_incremental 무변경, strategy_engine 은 모듈 PULLBACK 상수·pullback 이름 함수만 | 확인(게이트의 ema_path_compare·ema_trace 통과) | 게이트 |
| 9 | 되돌리기: 옛 코드는 ts 키가 든 설정 파일을 거부하고, 옛 pullback_state 저장은 ts 5칸을 건드리지 않아 옛 값이 남음 → 다시 새 코드를 올리고 보유 중 재시작하면 남은 칸을 그 거래에 씀(verifier B2). 아래 「되돌리기 절차」로 막음(사용자 승인 필요한 쓰기, 코드 변경 없음) | 확인(HEAD:services/pullback_state.py:147,175-176,205 · core/strategy_engine.py:72-84) | engine/pullback_params.py validate |
| 10 | 남은 한계: BACKFILL 이 과거 종가를 고쳐도 보유 중 최고가는 고치지 않음(V8). 실계좌 체결가와 종가 차이 미측정(V10). 저장 이력(v2_settings_history)에는 추적 손절 값이 남지 않음(적용본·변경 기록 PARAMS 행에는 남음). 무장 중 앱 추가 매수로 평단이 바뀌어도 추적 상태는 그대로(R3, 손절·데드크로스는 유지). 추적 손절 매도 감사 행에 정리 전 최고 종가가 안 보임(R2) | 확인(설계·verifier) | — |
| 11 | 구현 8 정정: 변이는 3건이 아니라 4건(ts_off_tp_body·buy_block_other·ts_block_if_extra·reset_trade_other) | 확인(verifier) | test_r_2026_10_30_1029_09_off_hours_tp.py |
| 12 | 권고 미반영(다음 작업 후보로 기록): R2 감사 칸, R3 평단 변경 때 초기화, R4 BACKFILL·연속 손절 전용 시험, R5 걷어 내기의 ts_wait 이름(커밋 뒤 기준 올리며 걷어 내기 삭제 때 함께 사라짐), R6 따라잡기 예외 때 되돌림 | PO 판단 — 기본 꺼짐이라 켬 사용 전까지 영향 없음 | verifier 11/10 |

## 되돌리기 절차 (verifier B2 반영 · 실행은 사용자 승인 뒤)
1. 서버 세 파일(적용본·저장본·직전 정상 사본)에서 키를 지운다(verifier B3 반영 · 경우를 나눔).
   - 1110-01 커밋만 되돌릴 때: ts_on·ts_mode·ts_pct 3키만 지운다. 비율 키 2개는 남긴다(1109-01 실계좌 기동이 invest_ratio_pct_live 를 요구 — engine/engine_manager.py:102 → to_live_params).
   - 1109-01 이전 코드까지 되돌릴 때만: ts 3키와 비율 키 2개를 모두 지운다.
2. 미보유 확인 뒤 pullback_state 의 모든 모드 행에서 trade_ts_mode·trade_ts_pct·ts_peak·ts_fixed 를 NULL, ts_armed 를 0 으로 되돌린다(칸은 남겨 둠).
3. 그다음 코드를 되돌리고 재시작한다. 나중에 새 코드를 다시 올릴 때도 2번을 먼저 한다.

## 물어볼 것
| # | 질문 | PO의 생각 |
|---|---|---|
| 1 | 묶음이 실제 돈 경로에 새 빈틈(이중 매도·매도 누락·재시작 뒤 무장 소실·무장 중 매수)을 만드는가 | 없다고 봄 |
| 2 | 사실 5(일관된 개선 없음)를 사용자에게 그대로 알리고, 기본 꺼짐 그대로 배포가 맞는가 | 맞다고 봄 |
| 3 | 고정 시험을 「걷어 내기 비교」로 바꾼 것이 규칙(baseline_commits 6)에 맞는가 | 커밋 뒤 기준을 올리고 걷어 내기를 지움 |

## 참고 파일
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/core/strategy_pullback.py
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/core/strategy_engine.py
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/engine/pullback_params.py
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/v2/api_write.py
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/tests/regressions/test_r_2026_11_10_trailing.py
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/tests/regressions/test_r_2026_10_30_1029_09_off_hours_tp.py
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/fable/2026-11-10-live-open-impl-1.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/CLAUDE.md

---

# 답변 요지 (Fable, 원문의 판정·지적을 PO 가 옮겨 적음)

**판정:** 진행
**이유:** 실제 돈 경로(판정 순서·매도 사유 네 곳·저장 5칸·복원·따라잡기·되돌리기)를 코드로 대조해 새 빈틈 없음. 게이트·백테스트 비교 표를 다시 돌려 같은 결과. 고칠 것은 모두 권고.

- 질문 1(새 빈틈): 없음(높음). 단 강제 매수는 ts_armed 를 보지 않아 무장 중에도 삼 → 권고 3.
- 질문 2(사실 5·기본 꺼짐): 맞음(높음). 보고에 「Ver2 화면 기본값(tp 1·2, sl 1.5, 5회차), 투자자 값 아님」과 V10(백테스트는 종가, 실거래는 체결가) 함께 적기.
- 질문 3(걷어 내기 비교): 규칙에 맞음(보통). 다만 걷어 내는 추적 손절 가지 안 손절 `<=`→`<` 변이를 잡는 시험이 없음.
- 권고 1 (반영 11/10): test_r_2026_11_10_trailing 에 test_sl_boundary_equal_low_sells_in_trailing_branch 추가(비율·고정폭). 원본 통과·변이(`<`) 실패 확인(scratchpad mut_sl_lt.py). 게이트 재실행.
- 권고 2 (반영 예정): push 뒤 후속 커밋 — PULLBACK_RULES_BASE_COMMIT 을 1110-01 커밋으로 올리고 _Strip1110·ts_wait 규칙 삭제, 줄 범위 시험을 되살릴지 커밋 메시지에 적음.
- 권고 3 (사용자 결정으로 올림): 무장 중 강제 매수 허용(안내만) / 막음.
- 권고 4 (반영): 변경 규모는 지금 트리 기준 `git diff --stat` 89개 파일 +1784 −299, 새 파일 31개.
- 권고 5 (반영): 되돌리기 절차 1~3 을 배포 요청서·HANDOFF 에 싣고 「새 코드를 다시 올릴 때도 2번 먼저」를 굵게.
- 권고 6 (반영 예정): 커밋 직전 dashboard 버전 v1.2026.11.08.1151 → 새 시각.
