# 질의: 눌림목 전략에 구버전 트레일링 스톱을 넣는 계획을 사용자에게 제안하려 합니다

**지금 단계:** 계획(제안)
**다음에 하려는 일:** 아래 안을 사용자에게 제안합니다. 승인되면 1109-01(눌림목 실계좌 열기, 미커밋)과 같은 묶음으로 구현·시험·검증한 뒤 한 번에 커밋·배포 승인을 다시 요청합니다. 이번 단계의 코드·서버 변경은 없습니다.

사용자 지시(11/10 원문): 「㉠ 커밋·배포 승인 전 마지막 추가 구현사항. 구버전 Trailing Stop 전략을 확인 후 신버전 적용 계획을 제안하시오. 수익 극대화를 위해 중요한 사안이다.」

## 구버전(EMA) 트레일링 스톱 — 코드로 확인한 규칙
| # | 규칙 | 근거 |
|---|---|---|
| 1 | 판정 가격 = 확정 봉 종가(bar.close) | core/strategy_incremental.py:376,1149 |
| 2 | 무장: 수익률(종가 기준) ≥ 익절 기준(take_profit, 약매수는 축소 기준)이면 무장. 무장 뒤 익절 필터는 팔지 않음(TP_SKIPPED_TS_ARMED) | core/filters/sell_filters.py:173-178,262-305 |
| 3 | 최고가: 무장 뒤 종가 최댓값 | core/position_state.py:435-452, sell_filters.py:307-309 |
| 4 | 비율 방식: (최고가 − 현재가) / (최고가 − 평단) ≥ 폭% 이면 매도 (TRAILING_STOP_RATIO) | sell_filters.py:375-404 |
| 5 | 고정폭 방식: 무장 순간 (종가 − 평단) × 폭% 를 고정 금액으로, 현재가 ≤ 최고가 − 고정 금액이면 매도 (TRAILING_STOP_FIXED) | sell_filters.py:284-294,348-373 |
| 6 | 재시작: 마지막 BUY 뒤 확정 봉 종가로 무장·최고가를 다시 계산 | core/trailing_restore.py:1-25 |
| 7 | 설정 칸: trailing_stop(켬/끔) · trailing_stop_threshold_pct · use_fixed_trailing | pages/set_buy_sell_conditions.py:259-280 |

## 지금 눌림목 매도 규칙
- 데드크로스 → TP(봉 고가 ≥ 평단×(1+거래 TP%)) → SL(봉 저가 ≤ 평단×(1−SL%)) 순. 트레일링 없음(`trailing_stop_pct = None`). core/strategy_pullback.py:531,756-785
- 백테스터 simulate() 도 같은 순서, TP 체결가 = TP 가격. v2/static/backtester.js:251-262
- 거래 TP% 는 구간 순번에 따라 줄 수 있음(episode_tp). strategy_pullback.py:668-675

## 제안 ㉠: 눌림목 트레일링 스톱 (선택 기능, 기본 꺼짐)
| # | 내용 |
|---|---|
| 1 | 적용본 선택 키 3개 추가(OPTIONAL_KEYS, 없으면 꺼짐): trailingStop(yes/no) · trailingMode(ratio/fixed) · trailingPct(1~100). 저장 창·백테스터에 같은 3칸 |
| 2 | 켜짐이면 TP 가격에서 팔지 않고 무장. 무장·최고가·매도 판정은 구버전 1~5 와 같은 식, 판정 가격은 확정 봉 종가. 익절 기준은 이 거래의 TP%(구간 감소 포함) |
| 3 | 순서: 데드크로스 → SL(봉 저가) → 트레일링(종가). 첫 체결 봉은 평가하지 않음(기존 규칙) |
| 4 | 무장·최고가·고정 금액을 SPLIT_TRADE_KEYS 에 넣어 분할 상태와 함께 저장·복원(재시작 뒤 이어짐). 청산 때 초기화 |
| 5 | 시간 밖 「익절 막음」(allow_sell_during_off_hours=false)이면 트레일링 매도도 막음(익절과 같은 무리). 손절·데드크로스는 늘 팜 — 사용자 결정 1029-08 의 「익절만 막음」을 넓혀 적용 |
| 6 | 백테스터 simulate() 에 같은 규칙, 청산 종류 「TS」(체결가 = 그 봉 종가) 집계·차트 표시. 실계좌 매도는 신호 봉 마감 뒤 시장가 → 종가와 가까움 |
| 7 | EMA 코드 무변경: TrailingStopFilter 를 부르지 않고 눌림목 안에 같은 식을 둠. 같은 입력에서 두 계산이 같은 매도 봉을 내는지 시험으로 대조. EMA 불변 시험(AST·호출 흔적) 유지 |
| 8 | 시험: 엔진·백테스터 같은 봉 자료 매도 봉 일치, 켬·끔, 고정폭·비율, 재시작 이어짐, 시간 밖, 옛 적용본(키 없음) = 지금과 같은 결과 |
| 9 | 구현 뒤 백테스터로 공개 업비트 봉 자료에서 켬/끔 결과(순손익·승률·MDD)를 숫자로 비교해 보고 |
| 10 | 메뉴얼에 한 단락 추가(1쪽 유지). 되돌릴 때 비율 키처럼 3키도 먼저 지움 |

## verifier 지적 반영 (11/10, 막음 6 · 권고 5)
| # | 고친 내용 |
|---|---|
| V1 | 제안 1 수정: OPTIONAL_KEYS 가 아니라 RATIO_KEYS 처럼 따로 묶음 TRAILING_KEYS(ts_on bool · ts_mode ratio/fixed · ts_pct 1~100). 키가 있을 때만 쓰고 형식 검사 따로, 운용 설정 「정확히 4키」 저장 무관. 꺼짐을 고르면 키를 쓰지 않음 → 되돌리기 쉬움. 백테스터 cfg 에서만 yes/no |
| V2 | 제안 4 수정: pullback_state 표에 ts_armed·ts_peak·ts_fixed 칸 추가(ALTER ADD COLUMN, 기본 NULL), 저장 사전·복원 사전·청산 초기화 SQL·_reset_trade·SPLIT_TRADE_KEYS·live_loop._PULLBACK_TRADE_KEYS 함께. 이름은 기존 armed(눌림목 무장)와 겹치지 않게 |
| V3 | 고정 시험 기준 갱신 단계 추가: strategy_pullback AST 허용 줄 범위·새 줄 상한(test_r_2026_10_30_1029_09_off_hours_tp, baseline_commits), backtester.js 는 ver2_patches.json 세 번째 차이로 넣고 build_backtester_js.mjs 로 다시 만듦, 칸 수 시험 갱신. 꺼짐일 때 원문 simulate 와 결과 같음 시험 |
| V4 | 무장 중 분할 추가매수: 무장 뒤 추가매수를 막음(엔진·백테스터 같은 규칙). 사용자 결정 항목 ㉢ |
| V5 | 보유 중 3키 변경: 거래 시작 때 값을 고정, 다음 거래부터 반영(trade_tp_pct 와 같은 방식) → 무장 중 모드 바꿈 예외 없음 |
| V6 | 시간 밖 규칙(제안 5) 변경: 「트레일링은 늘 팜」을 권고로, 결정 1029-08 은 트레일링 이전 결정이라 새 사용자 결정 ㉡ 으로 올림 |
| V7 | 매도 사유 「TS」 다섯 곳(terminology, PULLBACK_SELL_TRIGGER_KEY, api_read·labels.js, 백테스터 집계·라벨, audit checks). TS 매도에서 연속 손절 수 0 으로 시험 |
| V8 | 트레일링 칸은 거래 칸(재생 안 함). BACKFILL 이 과거 종가를 고쳐도 최고가는 안 고침 — 한계 기록 + BACKFILL 시험 1건 |
| V9 | 저장 창 25칸 밖 선택 필드로 받고 보존(투자 비율과 같은 방식). 브라우저 실측 3폭·UI diff 브리핑·regression_gate.sh 통과를 끝 기준에 넣음 |
| V10 | 실계좌 체결가와 종가 차이는 미측정 → 백테스트가 실거래보다 좋게 나올 수 있다고 고지 |
| V11 | 사실 8 정정: strategy_pullback.py·backtester.js 는 이번에 처음 고침 |

## 지금까지 확인한 사실
| # | 사실 | 확인/추정 | 근거 |
|---|---|---|---|
| 1 | 위 구버전 규칙 1~7 | 확인(코드) | 위 표 |
| 2 | 눌림목은 트레일링을 쓰지 않음 | 확인 | strategy_pullback.py:531 |
| 3 | 눌림목 규칙은 투자자 원본 백테스터 simulate() 와 같게 만든 것. 트레일링은 원본에 없음 | 확인(코드 주석·백테스터) | strategy_pullback.py:452-466, backtester.js:166 |
| 4 | 투자자 EMA 설정: 트레일링 켬·고정폭·90%·익절 필터 끔 | 추정(맥 사본 8/26). 서버 읽기는 자동 권한에서 막힘 | mcmax33_EMA_buy_sell_conditions.json |
| 5 | 켬이 수익을 늘리는지 | 미확인. 종가 판정이라 봉 고가로 익절되던 거래가 익절을 놓치고 손절까지 갈 수 있음 | 설계상 |
| 6 | 옛 코드는 모르는 키가 든 적용본을 거부 | 확인 | engine/pullback_params.py:228 |
| 7 | 작업량: 구현·시험 약 1일, 검증·Fable 뒤 배포 → 배포가 11/11~12 로 늦어짐 | 추정 | — |
| 8 | 1109-01 미커밋 변경 위에 얹음(같은 파일 strategy_pullback·pullback_params·save.js 등) | 확인 | git status |

## 물어볼 것
| # | 질문 | PO의 생각 |
|---|---|---|
| 1 | 이 안이 실제 돈 경로에 새 빈틈(이중 매도·매도 누락·재시작 뒤 무장 소실)을 만드는가 | 기본 꺼짐 + 상태 저장으로 막힘 |
| 2 | 판정 가격을 종가로 두는 것(구버전과 같음, 백테스트=실거래 유지)이 맞는가. TP 고가 무장이 낫는가 | 종가가 맞음 |
| 3 | 시간 밖 규칙 5번(트레일링도 익절처럼 막음)이 사용자 결정 1029-08 과 어긋나는가 | 같은 무리라 맞음, 사용자에게 명시 |
| 4 | 1109-01 과 한 묶음 배포가 맞는가, 따로가 맞는가 | 사용자 지시가 「배포 전 추가」라 한 묶음 |

## 참고 파일
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/core/filters/sell_filters.py
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/core/strategy_pullback.py
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/v2/static/backtester.js
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/engine/pullback_params.py
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/core/trailing_restore.py
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/CLAUDE.md

---

# 답변 요지 (Fable, 원문의 판정·지적을 PO 가 옮겨 적음)

**판정:** 진행
**이유:** 구버전 규칙·눌림목 매도 규칙·실계좌 매도 경로를 코드로 확인함. 남은 지적은 권고 5건, 사용자 결정 ㉡·㉢ 은 제안에 올라감.

- 권고 1 (반영): 수익 증가는 미측정으로 명시. 구현 첫 단계에서 백테스터로 켬/끔 숫자를 먼저 냄.
- 권고 2 (반영): 재시작 때 저장된 마지막 봉 뒤 확정 봉 종가만 트레일링 칸에 재생(구버전 규칙 6 과 같은 뜻).
- 권고 3 (반영): 묶음 전체 verifier·Fable 재검증, 1109-01 과 트레일링은 커밋 2개로 나누어 한 번에 배포.
- 권고 4 (반영): ㉢ 설명에 원본에 없던 상황을 닫는 것 · 거래 수가 줄 수 있음.
- 권고 5 (반영): 1109-01 먼저 배포 선택지를 함께 올림. 배포일 11/11~12 는 추정.
