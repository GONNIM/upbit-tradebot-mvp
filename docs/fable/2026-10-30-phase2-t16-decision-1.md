# 질의: 2차 T16(신버전 화면 새 전략 표시 — 홈·로그·차트·자산) 착수 전 정지선 — PO 결정 13건과 사용자 결정 4건

**지금 단계:** T16 착수 전 정지선입니다(기준 HEAD 4e86afb, 파일 무변경). 실행 에이전트 대조 결과는 다음과 같습니다.
- 고정 파일 9개는 하나도 건드리지 않습니다.
- 엔진 코드가 바뀌지 않으므로 실계좌 EMA 매매 경로 영향은 0입니다.
- v2 는 별도 프로세스이고 DB 를 읽기만 합니다.

**다음에 하려는 일:**
1. 아래 PO 결정을 확정합니다.
2. 사용자 결정 U1~U4 를 올립니다(HANDOFF 1030-02).
3. 결정을 받으면 실행 에이전트가 v2/*·v2/static/*·tests/v2/* 를 구현합니다.
4. 그 뒤 verifier → Fable → 커밋 승인 순서로 진행합니다.

## 실행 에이전트 정지선 사실(요지, 번호는 실행 에이전트 표)
| # | 사실 | 근거 |
|---|---|---|
| 1-4 | 홈 배지·FORCE 라벨·저장 확인 창 2줄·매도 체결 사유 라벨은 이미 있다 | v2/static/app.js:54,77, v2/api_read.py:29,459-460, save.js:92-99 |
| 5-6 | assets round 는 null 로 고정이다(시험 test_assets_round_null_in_phase1). 최대 회차 계산은 v2/control.py:234-242 에 있다 | api_read.py:319 |
| 7 | 익절·손절 가격은 지금 audit_sell_eval 값이다. 엔진 식은 평단×(1±%) | api_read.py:296-305, core/strategy_pullback.py:707-708 |
| 8-10,19 | 회차(meta.split_round), 눌림 상태(checks.armed·round·golden_event), 건너뜀 코드(meta.error_name)가 있지만 v2 SQL 은 meta·checks 를 읽지 않는다. 보유 중 armed 는 audit_sell_eval.checks 에만 있고, v2 는 triggered=1 행만 읽는다 | api_read.py:57-90, core/pullback_audit.py:33, core/trader.py:460-465,585-611, core/strategy_engine.py:1656 |
| 11 | strategy_switch 는 전환 1건이 행 1개이고 상태가 갱신된다. 바로 전환과 예약 완료를 구분하는 칸이 없다(requested_at·done_at 차이로만 구분) | engine/strategy_switch.py:657,785,810 |
| 12 | 인덱스는 (user_id, mode, state) 뿐이다. ORDER BY id DESC 에 WHERE user_id 가 붙으면 TEMP B-TREE 가 생겨 test_queries_use_index 에 걸린다 | services/init_db.py:1072, tests/v2/test_api_read.py:973 |
| 13 | 서버(1747fcc) DB 에는 pullback_state·strategy_switch 표가 없다(엔진 재시작 때 생김). 지금 _guard 는 sqlite3.Error 가 나면 응답 전체를 503 으로 만든다 → EMA 사용자 홈·로그도 막힌다 | api_read.py:216-217, init_db.py:1274 |
| 14 | 차트는 SMA 만 그린다. 선 색은 60·200 으로 고정이고, 봉은 400개로 고정이며, 가장 긴 선은 봉이 기간의 2배일 때만 그린다. ma200p 가 200을 넘으면 선이 그려지지 않는다 | chart.js:166-176,236, app.js:4 |
| 15 | 눌림 판정선은 pullbackP 이다(ma60p 가 아님) | core/strategy_pullback.py:110,449 |
| 16 | 비활성 사유 용어는 사용자 결정 1028-10 의 terminology 와 계획 문구가 다르다 | docs/operations/terminology.md:82, services/terminology.py:140 |
| 17 | 실제 apply 값은 next_bar·immediate·reseed·switch·restart 이다(reserved 는 쓰지 않음) | plan-phase2.md:1178,1181,1237 |
| 18 | REVERT 예약도 있다. T14 는 「복귀 예약 중」으로 구분해 표시한다 | v2/static/ops.js:201-202 |
| 20 | 차트 표시(SQL_MARKERS·toMarkers)는 거래 유형을 거르지 않는다. 그래서 BUY_REJECTED(건너뜀·예약 차단)가 가짜 ▼「매도」로 보인다. 1차부터 있었고 EMA 화면에도 있다 | api_read.py:109-110, chart.js:117-127 |

## PO 결정(사실·위험만 확인 요청)
1. 1~4 는 손대지 않는다. 저장 확인 창 안내 글자는 T13 문장을 그대로 둔다.
2. 새 표(pullback_state·strategy_switch) 읽기는 따로 감싼다. sqlite3.Error 가 나면 그 부분만 「모름」으로 두고 응답 200 을 유지한다. 서버 표가 없어도 EMA 화면은 그대로다.
3. strategy_switch 는 WHERE 없이 `ORDER BY id DESC LIMIT 200` 으로 읽고, 사용자·모드는 파이썬에서 거른다(DB 는 사용자별 파일). 인덱스는 추가하지 않는다. 시험 고정용 표에 두 표를 넣고 CREATE 개수 단언을 9 → 11 로 바꾼다.
4. 익절·손절 가격은 pullback_state.avg_price × (1 ± 적용본 tp/sl%) 로 계산한다. 어긋남이거나 평단이 없으면 지금처럼 audit_sell_eval 값을 쓴다.
5. 회차·예약·어긋남은 입장 모드 행을 읽는다. T14 ops_info·reservation(v2/control.py:186,245)을 재사용한다.
6. 거래·로그 SQL 에 meta·checks 를 더한다. checks 를 읽는 매도 판단 조회는 활성 전략이 PULLBACK 일 때만 돈다. EMA 사용자의 조회는 그대로 둔다.
7. 홈 최신 신호의 우선순위는 예약 > 어긋남 > 회차 다 참 > armed > 감시 구간 안 > 밖이다. 계획에 없는 상태는 확정 용어 PULLBACK_STATE_LABEL 로 「매수 대기 — <라벨>」 이라고 쓴다.
8. 눌림 문장의 「N선」은 pullbackP, 골든크로스 문장은 ma60p/ma200p 로 쓴다. 비활성 사유는 terminology(1028-10)를 따른다.
9. 전환 로그는 행마다 상태 줄 1개를 그린다. DONE 이고 done_at−requested_at 이 1봉을 넘으면 requested_at 에 「전환 예약」 줄을 더한다. REVERT 문구는 T14 와 맞추고, mode_conflict 취소 문구는 따로 둔다.
10. PARAMS 문구는 실제 apply 5종에 맞추고 「예약 전환」은 뺀다. 키 이름 한글은 백테스터 입력 라벨과 같은 표로 만든다.
11. FORCE 회차 행은 「매수 체결 n회차 · 강제 매수」로 쓴다. 회차 meta 가 없는 행은 「매수 체결 · 강제 매수」로 쓴다.
12. 서버·화면 라벨 표에 PULLBACK 키를 양쪽 같이 더한다.
13. Files 에 v2/control.py(재사용)와 tests/v2/test_static_lint.py 를 보강한다.

## 사용자에게 올릴 결정(초안)
| # | 결정 | 선택지 | PO 권고 |
|---|---|---|---|
| U1 | 차트에서 긴 이동평균선(200선 기간을 200보다 크게 둔 경우) 그리기 | (가) 받을 봉 수를 2×가장 긴 기간, 최대 2000 으로 늘린다. 투자자 브라우저의 업비트 호출이 최대 10회(약 90초)로 늘고, 기본값이면 지금과 같다 / (나) 400 그대로 두고 「봉이 모자라 N선은 그리지 않습니다」 한 줄을 띄운다 / 그대로 둠(선이 말없이 빠짐) | (가). 기본값 사용자는 변화가 0이고, 서버 업비트 한도와도 무관하다 |
| U2 | 차트의 가짜 ▼「매도」 표시(건너뜀·예약 차단 행) | (가) 모든 사용자에게 BUY·SELL 행만 표시한다(EMA 화면도 바뀜) / (나) 새 전략 화면에서만 거른다 / 그대로 둠 | (가). 「봇이 실제로 사고판 자리」 문구와 맞는다 |
| U3 | 눌림 기준선이 60선과 다를 때 차트 | (가) 다를 때만 기준선을 점선으로 하나 더 그리고 범례 「N선(기준선)」을 단다 / (나) 문장만 N선으로 쓴다 | (가). 기본값이면 승인 요청서 그림과 같다 |
| U4 | 로그의 「다시 시드」 글자(1027-17 승인 문구) | (가) 「지표 다시 계산(그동안 매수 없음)」으로 바꾼다 / 그대로 둠 | (가) |

## 물어볼 것
| # | 질문 | PO의 생각 |
|---|---|---|
| 1 | 사실 1~20 이 맞는가 | 맞다고 본다 |
| 2 | PO 결정 2·3(새 표 읽기를 따로 감싸기, WHERE 없는 LIMIT 200)이 EMA 사용자 화면을 바꾸지 않는가. LIMIT 200 으로 사용자 행이 잘리는 경우는 없는가 | DB 가 사용자별 파일이라 다른 사용자 행이 없어서 안 잘린다 |
| 3 | PO 결정 4(평단 기반 익절·손절 가격)가 엔진의 실제 판정과 같은가. 분할 체결 직후처럼 어긋나는 때가 있는가 | 엔진 식과 같다. 어긋남이면 audit 값을 쓴다 |
| 4 | PO 결정 6 에서 EMA 사용자의 조회가 정말 그대로인가(SQL 칸 추가 때문에 응답 모양이 바뀌는가) | 칸만 더하고 EMA 응답 글자는 바뀌지 않는다 |
| 5 | U1~U4 로 사용자 결정을 요청해도 되는가. U2 (가)는 EMA 화면을 바꾸는데 1-A 상 문제가 없는가 | 된다. 가짜 표시를 없애는 것이라 사라짐이 아니라 정정이다 |

## 참고 파일
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/plan-phase2.md §T16, T12~T15 구현 메모
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/plan-outline-phase2.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/v2/api_read.py, v2/control.py, v2/static/app.js, chart.js, ops.js, labels.js
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/core/strategy_pullback.py, core/pullback_audit.py, core/trader.py, engine/strategy_switch.py, services/init_db.py, services/terminology.py, docs/operations/terminology.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/CLAUDE.md, .claude/context/project-rules.md

---

# 답변(1회째) 요지 (Fable)

**판정:** 멈춤. 남은 것이 사용자 결정 U1~U4 뿐이라서 내린 판정입니다. 막음 지적은 없습니다.

- 사실 1~20 과 PO 결정 1~13 은 코드로 확인했습니다. 다만 사실 13 의 서버 HEAD 는 커밋 메시지로만 확인했습니다.
- 표가 없을 때 새 표 읽기를 따로 감싸면 EMA 화면은 바뀌지 않습니다.
- LIMIT 200 으로 잘리는 것은 다른 사용자 행 때문이 아니라 같은 사용자 안의 TEST·LIVE·PARAMS 행 때문입니다. 이것은 오류가 아니라 보여 주는 깊이의 차이입니다.
- 평단 기반 익절·손절 가격은 엔진 식과 같습니다. 상태 표가 감사 표보다 같거나 더 새롭습니다.
- `/v2/api/trades` 는 SQL 행을 그대로 내보내므로, meta 를 더하면 EMA 행에도 `"meta": null` 키가 생깁니다. 이 키를 고정한 시험은 test_api_read.py:537 입니다.
- U2 (가)로 사라지는 것은 거절·취소 표식뿐입니다. 외부 매도 표식은 지금도 없고, 외부 매수는 그대로 ▲ 입니다. 따라서 이것은 사라짐이 아니라 정정입니다.

**권고:**
1. 결정 6 에 trades 응답에 meta 키가 생기는 것과 시험 537 갱신을 적습니다. 또는 파생 칸만 넣습니다.
2. 결정 9 의 「1봉 넘으면 예약 줄」에 하한을 둡니다. 즉시 전환이라도 재시작이 1분을 넘을 수 있기 때문입니다.
3. assets 는 ops_info 전체가 아니라 _eff_max_splits·SQL_PULLBACK_STATE·reservation 만 씁니다.
4. LIMIT 는 감사 표와 같이 1200 으로 하거나, 200 의 이유를 적습니다.
5. 서버 HEAD 는 배포 전 정지선에서 SSH 로 다시 확인합니다.

## PO 반영 (10/30)
- 권고 1: trades 응답에 meta 키가 생기는 대신 파생 칸만 넣습니다(round·skip_reason 등). 응답 키는 하나도 늘지 않게 하고, 시험 537 은 그대로 둡니다. 실행 에이전트가 이렇게 구현하기 어려우면 키를 더하고 시험을 고친 뒤 보고합니다.
- 권고 2: 하한을 max(1봉, 300초)로 합니다. 즉시 전환인데 완료까지 90초 걸린 경우를 시험에 넣습니다.
- 권고 3·5: 받아들입니다.
- 권고 4: LIMIT 1200(감사 표와 같음)으로 합니다.
- 남은 일은 사용자 결정 U1~U4 뿐이므로, 다시 묻지 않고 사용자에게 바로 묻습니다(HANDOFF 1030-02).

## 사용자 결정 (10/30 · 1030-02 「권고대로」)
- U1 (가): 차트가 받는 봉 수를 2 × 가장 긴 기간(최대 2000)으로 한다. 기본값이면 지금과 같다. EMA 방식 선은 화면에 보이는 봉으로 계산하므로 엔진 값과 조금 다를 수 있다는 안내를 한 줄 붙인다.
- U2 (가): 모든 사용자 차트에 실제 BUY·SELL 행만 표식으로 그린다. 거절·취소 행은 그리지 않는다.
- U3 (가): pullbackP 와 ma60p 가 다를 때만 기준선을 점선 1개로 더 그리고, 범례에 「N선(기준선)」을 단다.
- U4 (가): 로그의 「다시 시드」를 「지표 다시 계산(그동안 매수 없음)」으로 바꾼다.
