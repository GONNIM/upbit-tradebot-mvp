# 투자자 수정 요청(11/21 「Fullback_수정사항_261121.pdf」) 구현·수정 계획 (3판 보완 3 (Fable 2회 진행·권고 반영))

- **승인: 사용자 11/24 「1121-03 ㉠㉡ 권고대로」 — 이 3판 보완 3 그대로 구현.** 구현은 worktree(가지 fix/1121-03, 12be97c 위). 구현 메모는 맨 아래 7절.

- 3판 보완 3(11/24): Fable 2회 「진행」 · 권고 4개 반영 — 구현부터 12be97c 새 가지 임시 worktree·`git push origin HEAD:main`·작업 폴더 pull 금지와 stash 순서 · L1 매도 판단 행 1200 미만이면 창 조건 통과 · L1 첫 매수 체결을 못 찾으면 줄 0개 · 3단계 구현 목록에 v2/db.py.

- 3판 보완 2(11/24): Fable 1회 「수정 후 진행」 반영 — 막음 2개: 5-1(PARAMS 기록 실패 로그 규칙) 삭제(그 로그는 journal 에만 남아 v2 가 못 읽음 → 4절 남는 위험·엔진 고침은 뒤 일감) · L1 은 매도 판단 창의 가장 옛 행이 보유 첫 매수 체결보다 이를 때만. 권고 7개: L1 via_tentative 건너뜀·같은 봉 중복 제거·서버 건수 읽기 · 배포 전 검사는 정확한 파일 목록과 한 줄씩 대조 · 커밋·push 는 임시 worktree 에서(--no-verify 금지) · A1 이력으로 채우면 status 종목 덮어쓰기도 건너뜀 · differs 의 적용본 없음/깨짐 = null·투자비율 비교 제외 · 기록 없이 적용본을 바꾸는 다른 길(사각, 추정) · F5 근거 줄 고침.

- 3판 보완(11/24): verifier 1회 「고친 뒤 승인」 반영 — 배포 전 바뀐 파일 검사·1122-01 과의 커밋·배포 순서(가) · last-saved SQL 은 db.py(ALL_SQL 밖) + 따로 LIMIT·사용자 조건 시험 · differs 에 추적 손절 3키 · A1 실패 길(allSettled·시간 제한·손댄 칸·busy·source 없는 행) · 사슬 검사 사각·PARAMS 기록 실패 규칙 권고 · switch 행 설명 고침 · F9·F13·F14 고침 · bt_ui_ver9 시험 · saved_at 표시 함수 · 배포 뒤 메모리 확인.

- 3판(11/24): 투자자 답(11/23, ㉠~㉣ 모두 ① · ㉠ 간격 0.5% · ㉣ 추적 손절 켬/방식/폭) + 운영자 결정 「1121-03 권고대로」(① 추가 1 백테스터 시작값만 이번에, 추가 2 차트는 「가능, 길 가」 답 뒤 따로 ② 0.5% 줄 상한 보유 1건당 40줄 ③ 시작값 = 저장 이력 마지막 화면 값 + 추적 손절은 저장본, 이력 없으면 화면 기본값, 이력 saved_at 표시 ④ 차트 답은 배포 전 체감 변경 안내에 묶음) + 서버 읽기(11/24 21시대 fullback_read.sh) 반영. L2 역추적 멈춤 조건 고침(아래 1-1 ④ — 서버 6번 행이 2판 규칙에 걸림), 사슬 검사 추가.
- (이전) 2판: verifier 1회·Fable 1회 반영.
- 원본: docs/new-version/claim/ver9/Fullback_수정사항_261121.pdf (3쪽) · 투자자 답 docs/new-version/claim/ver9/investor-answer-20261123.md · 분석 investor-answer-analysis-20261123.md (Fable 2회째 진행 docs/fable/2026-11-23-investor-answer-analysis-1.md)
- 비교 기준: docs/new-version/ver9/MA_GC_Pullback_Backtester_2611161307(Ver9).html, v2/static/backtester.html·bt_ui.js·save.js·index.html, v2/api_read.py, v2/api_write.py, v2/control.py
- 범위 원칙: 신버전 화면 서비스(tradebot-v2)만 고친다. 엔진(tradebot)·매매 규칙·DB 스키마·파라미터 파일 쓰기 길은 고치지 않는다. 엔진 재시작 없음.

## 0. 근거 사실 (11/24 확인)
| # | 사실 | 확인/추정 | 근거 |
|---|---|---|---|
| F1 | 서버 HEAD c3e5d80 · v1.2026.11.22.1721 · 엔진 11/19 13:06:12 · v2 11/22 17:38:21 · 활성 전략 PULLBACK · 봉 단위 minute3 · KRW-JTO | 확인 | 서버 읽기 11/24 21시대 |
| F2 | 저장 이력(v2_settings_history) params_json = 검증된 화면 값 25칸 그대로(symbol·src·days 포함, gcMaxGapPct 는 글 "0"), note 「source=upbit/binance」. 추적 손절·투자비율·거래 시간 칸은 없음 | 확인 | v2/api_write.py:54~55·129~131, v2/params_schema.py:133~181, v2/db.py:183~195 |
| F3 | 저장본 파일 = to_engine_file(화면 25칸, **엔진 종목**) + 이전 파일의 거래 시간 4키·비율·추적 손절 보존 + 요청의 비율·추적 손절. 저장과 이력 쓰기는 한 요청 안(파일 6단계 → 이력 7단계) | 확인 | api_write.py:91~130·148~156, params_schema.py:184~244 |
| F4 | 「이 설정으로 동작」은 저장본을 해시로 확인해 적용본으로 복사(apply_saved)하고 PARAMS 행(note.changed [구,신])을 남기며, 마지막 이력 행에 applied_at 을 1번 적는다 | 확인 | engine/pullback_apply.py:328~380, v2/db.py:271~273·291~299 |
| F5 | **의심했던 어긋남은 어긋남이 아님**: 이력 12행(11/24 05:08:27 저장, applied_at 05:08:31.950) = PARAMS 8행(05:08:31.944, sha 0fdb1ca…) = 지금 적용본 sha(0fdb1ca…), 저장본·적용본 다른 키 0. 그러므로 지금 운용 값의 화면 25칸 = 이력 12행 값(ma200p 200 · pullbackP 60 · gcMaxGapPct 0 · episodeTpDecayPct 50 · slStreakCooldownHours 6). 11/20 PARAMS 4행의 201·61·2.0·60 은 그 뒤(5행 추정, 11/21 15:54 이력 8행 적용) 되돌려졌다 | 확인(해시 사슬) / 5행 내용은 추정 | 서버 읽기 + F3·F4 · 바뀐 키 계산 diff = engine/pullback_apply.py:94~101 · 저장본→적용본 복사 apply_saved = engine/pullback_params.py:474~503. 5행 원문은 fullback_read2.sh 로 확인 가능(필수 아님) |
| F6 | 백테스터 시작: choose("upbit") 뒤 /v2/api/status 응답이 종목(기본값일 때만)과 **봉 단위(src)를 무조건** 덮어씀 | 확인 | v2/static/bt_ui.js:380~414 (src 413줄) |
| F7 | 백테스터 칸 id = PARAM_FIELDS 이름 25개 + 추적 손절 trailingStop·trailingMode·trailingPct, 출처 dataSource(숨김 select)·btSrcUpbit/btSrcBinance 단추 | 확인 | backtester.html:104·125~155, save.js:13~21·85~89 |
| F8 | 이력 화면 값을 돌려주는 읽기 길은 없음(마지막 행 id·note 만: db.last_history). 이력 DB 가 없으면 만들지 않는 읽기 규칙이 이미 있음 | 확인 | v2/db.py:269~289 |
| F9 | 기존 LIMIT 시험(test_queries_all_have_limit)은 **api_read.ALL_SQL 만** 검사한다. db.py 의 SQL 은 그 시험 밖 → 새 SQL 은 따로 시험한다(1-4) | 확인 | v2/db.py:26~27, tests/v2/test_api_read.py:1029~ (verifier) |
| F10 | PARAMS 7행: apply 종류 next_bar 3 · reseed 3 · switch 1, 상태 모두 DONE, 옛 키(minSlope·slopeDrop) 행 0, 기록 실패 로그 0(11/01 뒤). 가장 새 행 sha = 적용본 sha | 확인 | 서버 읽기 |
| F11 | **「구 값 모두 None」 행 = 2(전체 기록, apply=switch)와 6(11/21 16:09 추적 손절만 켬 — 키가 없다가 생겨 구 값이 None)**. 2판 1-1 ④ 규칙(구 값 모두 None = 전체 기록 → 그보다 옛 행 「—」)이면 6행에서 잘못 멈춰 2~5행 6값이 빠진다 | 확인 | 서버 읽기 note |
| F12 | 투자비율: 3행(11/11)에서 10→100, 7행(11/24)에서 10→100 → 그 사이 어느 행에서 100→10(5행 추정). 기록 없이 바뀐 길이면 역추적이 틀린다 → 사슬 검사(1-1 ⑤)로 막음 | 확인(값) / 추정(어느 행) | 서버 읽기 |
| F13 | PARAMS 기록 길 **5곳**: engine/pullback_apply.py:376·464·486·565 + 전략 전환 engine/strategy_switch.py:622(apply="switch", changed = diff(전환 전 적용본, 새 적용본) — 전체 기록이 아닐 수 있음, 617~623). 기록 실패는 로그만 남기고 적용은 됨(pullback_apply.py:304~306 「변경 기록(PARAMS) 실패(적용은 됨)」). 이 줄은 logger.error 로 journal 에만 간다(pullback_apply.py:36·305, 처리기는 services/audit_logger.py:57~66 하나) → v2 는 읽을 수 없다 | 확인 | 해당 줄 (verifier · Fable) |
| F14 | 감사 창: PULLBACK 매도 판단은 SQL_LOGS_AUDIT_SELL_EVAL_PB 최근 1200행(미발동 행 포함, checks 칸)(3분봉 약 60시간). checks 에 price·avg 가 있고, 잠정 봉 평가 행은 checks.via_tentative=true. 체결 창(SQL_LOGS_AUDIT_TRADES 1200행)과 매도 판단 창은 **서로 다른 창**이다 | 확인 | v2/api_read.py:127~129·181~183, core/strategy_engine.py:2085~2086, core/strategy_pullback.py:910·1018, F1 |
| F15 | 「설정 적용」 줄은 바뀐 키 3개까지 + 「외 n개」 | 확인 | v2/api_read.py:881~901 |
| F16 | 운용 「지금 전략」 한 줄, ops 응답의 적용본 읽기·모드별 비율 키·실제 분할 한도 함수 | 확인 | index.html:151, control.py:241~289 |
| F17 | 결과 요약·스윕 요약·「자세한 결과」 접힘·sweepResult 위치, 저장 창 「취소」 | 확인 | backtester.html:181~229·296 |

## 1. 고칠 것
| # | 요청 | 고칠 것 |
|---|---|---|
| B1 | 결과 요약 아래 백테스터 결과(월간까지) | 결과 요약 바로 아래 summary→depth→weekly→monthly 펼침(Ver9:132~136 순서), 주간·월간 CSV 는 monthly 아래, 스윕 칸은 그 아래. 「자세한 결과」 접힘 없앰, 차트는 따로 카드 |
| B2 | 스윕 단추 아래 스윕 결과 | sweepResult 를 스윕 단추·sweepStatus 바로 아래로, sweepBrief 는 그 위 한 줄, 「스윕 결과 CSV」 옆 |
| B3 | 트레일링 스톱 확인 | 없음 |
| B4 | 접힘 안 5칸 밖으로 | ma60MinSlope·ma60SlopeDrop·trailingStop·trailingMode·trailingPct 를 주요 칸으로. 접힘 제목 「설정 15개」. id 그대로 |
| B5 | 저장 창 취소 → 닫기 | 글자만 |
| L1 | 평단 대비 0.5% 단계 로그 (㉠ ①, 간격 0.5%) | 아래 1-2 |
| L2 | 「설정 적용」 줄에 6값 (㉢ ①) | 아래 1-1 · 표시 모양 1-3 |
| O1 | 운용 「지금 전략」 아래 설정 한 줄 | ops 응답에 6값 요약 칸, 표시 1-3 |
| O2 | 홈 「보유」 아래 같은 한 줄 (㉡ ①) | 홈 보유 카드 아래 같은 칸 + 「지금 설정」 안내(보유 중 추적 손절은 연 때 값, TP 감소 켬이면 이번 거래 익절이 다를 수 있음) |
| A1 | 추가 1: 백테스터를 마지막 저장값으로 열기 | 아래 1-4 |

### 1-1. L2 역추적 (2판에서 고친 곳 ④⑤)
1. 그 사용자의 PARAMS 행을 모드와 상관없이 id 역순으로 따라간다(적용본은 사용자당 1개). 화면에는 입장 모드 행만. 투자비율은 각 행 모드의 키.
2. 시작 조건: 가장 새 PARAMS 행 params_sha256 = 지금 적용본 파일 sha256 일 때만(SQL_LOGS_SWITCH 에 params_sha256 칸 추가). 다르면 어느 행에도 6값을 붙이지 않는다.
3. 각 행의 적용 뒤 값 = 지금 값에서 더 새 행들의 changed 를 구 값으로 되돌린 값. 구 값 None = 키 없음(추적 손절 끔·비율 없음).
4. **멈춤 조건(고침)**: apply 가 「switch」인 행(전략 전환)에서 멈춘다. 그 행은 신 값을 쓰고, 더 옛 행은 6값 「—」. switch 행이 늘 전체 기록인 것은 아니다(전환 전 적용본과의 diff, strategy_switch.py:617~623 — 서버 2행은 첫 전환이라 전체였음). 그래도 switch 에서 멈추는 까닭은 **보수적으로** 이전 전략 기간으로 역추적이 넘어가지 않게 하기 위해서다. 「구 값이 모두 None」만으로는 멈추지 않는다(F11: 추적 손절만 켠 6행).
5. **사슬 검사(새로)**: 한 행을 되돌리기 전에 그 행 changed 의 각 키에 대해 「지금까지 되돌린 값 == 신 값」인지 본다. 하나라도 다르면 기록 없는 변경이 사이에 있었던 것이므로 그 행부터 옛 행은 6값 「—」(틀린 값보다 빈 값).
6. 옛 키(minSlope·slopeDrop) 행은 기울기·둔화 「—」(서버에는 0행, F10).
7. 조회는 이미 읽는 strategy_switch 최근 1200행 + 적용본 파일 한 번. 새 SQL 없음(칸 추가만, ALL_SQL LIMIT 검사 통과).

### 1-2. L1 0.5% 단계 줄
- 보유 중 봉마다 남는 매도 판단 기록(audit_sell_eval 종가·checks.avg)을 평단과 비교해 0.5% 단계(+0.5·+1.0… / −0.5·−1.0…)를 **처음** 넘은 봉에 한 줄 「평단 대비 +1.0% (종가 …)」. 봉 종가 기준.
- 쓰는 행: checks.via_tentative 가 참인 행(잠정 봉 평가, strategy_engine.py:2085~2086)은 건너뛴다. 같은 bar_time 행이 여럿이면 하나만 쓴다(가장 새 id). 서버의 via_tentative 행 수는 구현 첫 단계에서 읽기 전용으로 센다(사용자 `!` 실행 스크립트).
- 한 봉이 단계 2개 이상을 넘으면 **가장 먼 단계 한 줄**만(「+0.5%→+1.5%」처럼 건너뛴 폭 표시).
- 평단이 바뀌면(분할·HTS 매수) 「평단 변경」 한 줄 뒤 새 평단으로 다시 센다. 상한은 다시 세도 **보유 1건 합쳐 40줄**. 상한에 닿으면 **최근 40줄**을 남기고 맨 위에 「앞 n줄 생략」.
- **조건(고침)**: 매도 판단 창(SQL_LOGS_AUDIT_SELL_EVAL_PB 1200행, api_read.py:181~183)의 **가장 옛 행 시각이 그 보유의 첫 매수 체결 시각보다 이를 때만** 그 보유의 줄을 만든다. 아니면 그 보유는 줄 0개(첫 매수 체결이 체결 창(api_read.py:127~129) 안에 있어도 — 두 창은 다르다, F14). 시작 구간이 빠진 채 세면 「처음 넘은 단계」가 틀리기 때문.
- 예외(통과로 봄): 매도 판단 조회가 1200행보다 적게 돌려주면 표 전체를 읽은 것이므로 창 조건은 통과로 본다.
- 그 보유의 첫 매수 체결을 체결 창에서 찾지 못하면(예: 외부 HTS 매수로 시작한 보유) 그 보유는 줄 0개.
- avg 없는 행 건너뜀. 창이 밀리면 줄이 사라진다는 안내 문구.

### 1-3. 6값 표시 (㉣ ①, 운용·홈·감사 로그가 같은 함수 하나)
- 꺼짐: `익절 1.50 / 추적 손절 끔 / 손절 5.00 / 분할 1 / 기울기 0.60 / 둔화 0.20 / 투자비율 100%`
- 켬: `익절 1.50 / 추적 손절 켬 · 고정폭 · 손절폭 30% / 손절 1.50 / …` (방식 낱말 「비율」·「고정폭」 = save.js:96)
- 분할은 실제 한도(control._eff_max_splits), 투자비율 없으면 「—」.

### 1-4. A1 백테스터 시작값 (결정 ③)
- 새 읽기 API `GET /v2/api/params/last-saved`(api_write.py 의 CurrentHandler 옆, 로그인·Origin 은 ApiHandler): 그 사용자 이력 마지막 행 1개. SQL 은 **v2/db.py 에 상수로** 둔다(예: `SQL_LAST_HISTORY_FULL = "SELECT id, saved_at, params_json, note FROM v2_settings_history WHERE user_id=? ORDER BY id DESC LIMIT 1"`, 기존 SQL_LAST_HISTORY 옆). **api_read.ALL_SQL 에는 넣지 않는다**(그 EXPLAIN 시험은 실매매 DB 기준이라 v2_settings_history 표가 없어 실패). 대신 새 시험 2개: 이 상수가 db._LIMIT_RE 에 맞음 · `WHERE user_id=?` 조건이 있음(다른 사용자 행을 읽지 않음). 이력 DB 가 없으면 만들지 않고 `{"exists": false}`(db.last_history 와 같은 규칙). params_json 이 깨졌거나 25칸 검증(validate_params(…, source))에 실패하거나 **note 에 「source=」가 없으면** `{"exists": false, "broken": true}` → 화면 기본값.
- 응답: `{exists, saved_at, saved_at_text, source, params(25칸), trailing(저장본 파일에서 ts 3키, 없으면 끔), differs_from_applied}`. differs_from_applied = (to_engine_file(이력 25칸, 적용본 종목) 의 24키 중 종목 뺀 23키) **+ 추적 손절 3키(ts_on·ts_mode·ts_pct, 저장본 vs 적용본, 키 없음 = 끔)** 가운데 하나라도 적용본과 다른가(저장만 하고 적용 안 한 경우). **투자비율 키는 비교하지 않는다**(백테스터 칸이 아니라 저장 창 칸 — 모드별 키). **적용본 파일이 없거나 깨졌으면 differs_from_applied = null**, 화면에 「다름」 문구를 내지 않는다. saved_at_text 는 기존 db.kst_stamp(KST 「YY.MM.DD HH:MM」)로 만든다.
- 화면(bt_ui.js mountPage): status 와 last-saved 를 **Promise.allSettled + 시간 제한(예: 5초)** 으로 기다린 뒤 채운다.
  - last-saved 가 실패·시간 초과·broken·exists=false 면 **지금 동작과 똑같이**(status 의 종목·봉 단위 채움) 한다.
  - 기다리는 사이 사용자가 칸을 하나라도 고쳤거나(input/change 이벤트 표시) busyCount>0(실행 중)이면 **채우지 않는다**(「저장값 불러오기 건너뜀」 한 줄만).
  - 이력이 있으면 ① 출처 단추(choose(source)) ② 25칸(symbol·src·days 포함) ③ 추적 손절 3칸 — status 의 봉 단위 덮어쓰기(413줄)와 **종목 덮어쓰기(409~412줄)** 는 이력을 채우지 않았을 때만. 이력으로 채운 경우 status 응답으로는 engineTicker 변수만 정한다(나중에 출처 단추를 「업비트」로 다시 누르면 쓰임). 까닭: 이력 종목이 기본 업비트 종목과 같으면 지금 코드(409~412)가 엔진 종목으로 덮어쓴다.
- 화면 위 한 줄: 「불러온 설정: 마지막 저장 25.11.24 05:08」(saved_at_text) · differs 면 「(지금 운용 값과 다름 — 저장만 하고 적용하지 않음)」. 이력 없으면 「기본 설정」.
- 스윕·선물·차트 칸은 지금처럼 기본값. 투자비율은 저장 창이 이미 저장본에서 읽음(save.js:124·290~293).
- 지금 서버에서 열면: 이력 12행 = 운용 값(F5)이라 「다름」 표시는 안 나온다(추정 아님, 해시 사슬로 확인).

## 2. 시험 (바깥 연결 없음 · unittest + JS 시험)
- JS: bt_ui.test.mjs 배치 순서(B1·B2·B4) 다시 씀 · **bt_ui_ver9.test.mjs 173줄 id 목록 검사(summary·depth·weekly·monthly·sweepResult) — 배치를 옮겨도 id 가 남는지 함께 고침** · save.test.mjs 「닫기」 · 시작값: 이력 있음(upbit/binance) · 없음 · 깨짐 · status 가 늦게/먼저 와도 src 가 이력 값 · differs 문구 · **실패 길 3개: last-saved 실패·시간 초과 → 지금 동작과 같음 / 기다리는 사이 칸을 고쳤거나 busyCount>0 → 채우지 않음 / source 없는 행(broken) → 기본값** · **이력 종목 = 기본 업비트 종목, 엔진 종목은 다름 → 종목 칸은 이력 값 그대로, engineTicker 만 엔진 값**.
- Python: test_api_read_pullback.py 「설정 적용」 문자열 고침 + L2 — 모드 섞임(TEST→LIVE→TEST) · sha 불일치 6값 없음 · switch 행 멈춤(부분 diff 인 switch 행도 멈춤) · **서버 모양 재현(2·3·4·(5)·6·7·8행: 6행에서 안 멈춤)** · 사슬 검사 끊김(신 값 ≠ 되돌린 값) → 그 행부터 「—」 · 옛 키 행 · L1 0.5% 단계·한 봉 여러 단계·평단 변경·40줄 상한(최근 40줄)·창 경계 · **L1 보유 시작이 체결 창 안인데 매도 판단 창이 그보다 늦게 시작 → 그 보유 줄 0개** · **L1 표에 30행뿐·보유 1건 → 줄이 나옴(1200 미만 = 전체 읽음)** · **L1 첫 매수 체결을 체결 창에서 못 찾음(HTS 시작 보유) → 줄 0개** · L1 via_tentative 행 건너뜀·같은 bar_time 중복 1개 · ops 6값·실제 분할 한도 · 새 API: 이력 DB 없음(파일 안 생김) · 다른 사용자 행 안 읽음 · 깨진 행 · source 없는 행 → broken · **추적 손절만 저장하고 적용 안 함 → differs 참** · **적용본 없음/깨짐 → differs null** · **투자비율만 다름 → differs 거짓(비교 제외)** · 새 SQL 상수 LIMIT 정규식·user 조건(ALL_SQL 밖 따로).
- 게이트: scripts/regression_gate.sh · JS 시험 · [NETGUARD] 0.

## 3. 순서
1. 계획 3판 → verifier → Fable → 사용자 계획 승인(이번이 단계 끝)
2. 승인 뒤 docs/plans/2026-11-21-fullback-requests/plan.md 로 기록
3. 구현(처음부터 임시 worktree — 5단계 첫 줄): v2/static/backtester.html·bt_ui.js·save.js·index.html·app.js, v2/api_read.py, v2/api_write.py, v2/control.py, v2/db.py (엔진 파일 0 · 1-4·7단계 목록과 같음)
4. 시험·게이트 → 브라우저 실측(PC·412px: 결과 순서·스윕 결과·5칸·닫기·운용/홈 한 줄·감사 로그 0.5% 줄과 설정 적용 6값·시작값 문구)
5. verifier → Fable → 커밋 승인 요청(pages/dashboard.py 버전 갱신 — v2 런타임 변경)
   - **처음부터 따로 일한다**: 구현 시작 때 지금 main HEAD 12be97c 에서 새 가지로 임시 worktree 를 만든다(예: `git worktree add -b fix/1121-03 <scratchpad 폴더>/wt-1121-03 12be97c`). 구현·시험·게이트·커밋을 모두 그 worktree 에서 한다. 작업 폴더(1122-01 의 커밋 안 된 고침이 있음)는 건드리지 않는다.
   - 커밋은 `git add <경로>` 를 파일마다 하나씩(묶음 add·`-A` 금지), `git diff --staged --name-only` 를 7단계 파일 목록과 대조.
   - push 는 그 worktree 에서 `git push origin HEAD:main`. pre-push 게이트(.githooks/pre-push)는 그 worktree 에서 돌아 1122-01 고침이 섞이지 않는다. `--no-verify` 는 쓰지 않는다. push 전에 원격 main 이 아직 12be97c 인지 확인(아니면 멈추고 보고).
   - 공통 문서(HANDOFF.md · investor-notice-log.md)는 worktree 에서 **1121-03 줄만** 고친다. 작업 폴더의 같은 파일에 있는 1122-01 줄은 그대로 둔다.
   - **push 뒤 작업 폴더**: 1122-01 의 고침이 커밋되지 않은 동안에는 작업 폴더에서 `git pull` 하지 않는다. git 은 로컬 고침을 덮어쓰게 되는 pull 을 거절할 것이다(추정 — 실행해 보지 않음). 안전한 순서: 1122-01 커밋 때 ① `git stash`(커밋 안 된 고침 보관) ② `git pull --ff-only`(새 main) ③ `git stash pop` ④ 충돌 파일(HANDOFF·연락 기록·pages/dashboard.py 버전 줄)을 손으로 합침 ⑤ **잃은 것이 없는지 확인**: stash 전에 남긴 `git diff --stat`·`git status --short` 목록과 pop 뒤 목록을 비교하고, `git stash list` 가 비었는지 본다. 그 뒤 1122-01 을 새 main 위에서 커밋. 끝나면 worktree 를 지운다(`git worktree remove`).
   - 게이트는 그 worktree(커밋된 트리)에서 돌린다 — scripts/regression_gate.sh · JS 시험.
6. 투자자 체감 변경 안내 초안(화면 변경 + 20줄→40줄·0.5% + 시작값 + 추가 2 「가능, 길 가 — 따로 진행, 다르면 알려 달라」) → 배포 승인
7. 배포: 배포 전 서버 읽기(HEAD·기동 시각·적용본 sha) → **바뀐 파일 검사: `git diff --name-only <서버 HEAD>..<배포 대상 커밋>` 목록을 커밋 승인 때 확정한 1121-03 파일 목록과 한 줄씩 대조해, 목록에 없는 파일이 하나라도 있으면 멈춤**(폴더 단위로 보지 않는다 — v2/key_expiry.py·tests/v2/test_key_expiry.py 처럼 v2/·tests/ 안에도 1122-01 파일이 있다. 엔진이 읽는 파일이 섞이면 v2 만 재시작으로는 반쪽 배포가 됨). 목록 초안: v2/static/backtester.html·bt_ui.js·save.js·index.html·app.js · v2/api_read.py·api_write.py·control.py·db.py · tests/v2/test_api_read_pullback.py·(새 v2 시험 파일)·tests/v2/js/bt_ui.test.mjs·bt_ui_ver9.test.mjs·save.test.mjs · pages/dashboard.py · docs/plans/2026-11-21-fullback-requests/plan.md · 1121-03 문서(HANDOFF·연락 기록·Fable 질의) → git pull → **tradebot-v2 만 재시작**, 엔진 기동 시각 11/19 13:06:12 그대로 확인(엔진 파일을 안 고쳤으므로 엔진 재시작 없음 — 눌림목 보유와 상관없음) → 배포 뒤 확인에 `systemctl show tradebot-v2 -p MemoryCurrent` 추가 → 안내 발송·연락 기록 → 1시간 관찰

### 3-1. 1122-01(알림 사본)과의 커밋·배포 순서 — 기본 (가)
- (가, 기본): **1121-03 을 먼저 커밋 → v2 만 배포 → 그 뒤에 1122-01 커밋**(1122-01 배포는 엔진 재시작·끄는 파일 순서가 따로 있음). 까닭: 1122-01 커밋이 먼저 들어가면 서버 HEAD..1121-03 diff 에 services/·scripts/ 가 섞여 7단계 검사에 걸리고, v2 만 재시작하면 1122-01 코드가 엔진에 반쯤 걸린 상태가 된다.
- 1122-01 이 먼저 끝나 커밋해야 하면: 1122-01 을 먼저 서버에 배포(자기 순서대로)한 뒤 1121-03 을 커밋·배포한다. 어느 쪽이든 서버 HEAD 에서 배포 대상까지의 diff 가 한 일감의 파일만 담게 한다.
- 둘이 같이 고치는 파일: **pages/dashboard.py 버전 줄**(커밋마다 갱신 — 뒤 커밋이 앞 커밋 버전에서 올림) · **docs/operations/investor-notice-log.md**(두 일감 모두 안내 한 줄 — 커밋 때 그 일감 줄만 들어가게 `git add -p` 대신 줄이 섞이면 사용자에게 보고) · HANDOFF.md(문서).

## 4. 위험
- 휴대폰에서 스윕 칸까지 스크롤이 길어짐 — 412px 실측.
- L1 은 봉 종가·창 안 보유만·읽을 때마다 만듦.
- L2 는 시작 조건·사슬 검사가 깨지면 6값이 빠진다(틀린 값보다 빈 값).
- **L2 남는 위험(사슬 검사의 사각)**: PARAMS 기록이 실패한 변경(pullback_apply.py:304~306 — 적용은 됨)이 있었다면, 그보다 옛 「설정 적용」 행에 틀린 6값이 보일 수 있다(그 변경이 바꾼 키를 더 옛 행이 건드릴 때까지 사슬 검사가 못 알아챔). 실패 로그는 journal 에만 있어 v2 가 볼 수 없다(F13). 서버 기록 실패 로그는 11/01 뒤 0건(F10)이라 지금 화면에는 해당 없음. 없애려면 엔진이 실패를 DB 에 남기거나 PARAMS note 에 적용 뒤 값 전체를 남겨야 한다 → **엔진 고침이라 뒤 일감**(이번 범위 밖).
- 같은 사각(추정, 끝까지 따라가지 않음): PARAMS 행 없이 적용본을 바꾸는 다른 길 — 기동 때 last_good 으로 되돌리기, 재시작 실패 뒤 파일 되돌리기(engine/pullback_params.py:352~, engine/pullback_apply.py:69·498·521). 시작 조건(가장 새 행 sha = 지금 적용본 sha)은 가장 최근 것만 잡고, 중간의 이런 변경은 사슬 검사에 걸리는 키일 때만 잡힌다.
- switch 행 멈춤은 보수적이다: 부분 diff switch 행 앞의 같은 전략 기간 값도 「—」가 된다(값을 잃는 쪽, 틀린 값은 아님).
- A1: 이력은 「마지막 저장」이지 「운용 중」이 아님 → differs 문구로 구분. 바이낸스로 저장한 마지막 행이면 바이낸스 출처·종목으로 열린다(투자자가 마지막으로 시험한 값 그대로 — 결정 ③).
- 뒤 일감(범위 밖): 엔진 배포 때 PARAMS note 에 적용 뒤 6값 전체를 남기면 역추적 불필요.
- (11/25 verifier 3회 · 남는 위험 · 화면만) 엔진이 매도 행 없이 보유를 닫으면(PULLBACK_SYNC wallet_zero 경로) 다음 봇 매수가 같은 보유로 이어져 단계 줄이 틀릴 수 있다. 서버 행 수는 fullback_read3.sh 6줄로 세고, 0 이 아니면 배포 승인 요청에 수와 영향을 적는다.

## 5. 사용자 결정
- 새로 정할 것 없음. 의심했던 이력·운용 값 어긋남은 해시 사슬로 「어긋남 아님」 확인(F5). 1-1 ④⑤·1-2 상한 규칙은 결정 ②·Fable 권고를 구현 규칙으로 옮긴 것.

## 6. 확인하지 못한 것
- PARAMS 5행 내용(F5·F12 의 되돌림이 기록된 행인지) — scratchpad fullback_read2.sh(읽기 전용)로 확인 가능, 계획 승인에는 필요 없음. 구현 시험의 서버 모양 재현에 실제 note 를 쓰려면 실행.
- 서버 audit_sell_eval 의 via_tentative 행 수(L1 건너뜀 규칙의 영향) — 구현 첫 단계 읽기 전용 실측.
- 기록 없이 적용본을 바꾸는 다른 길(4절, 추정) — 끝까지 따라가지 않음.
- 홈 「보유」 카드의 정확한 자리(index.html 홈 탭) — 구현 때 확인.

## 7. 구현 메모 (11/24, 계획과 다르거나 더 정한 곳)
- A1 기다리는 사이 사용자가 칸을 고쳤거나 출처 단추를 눌렀으면(input·change·출처 click) 저장값으로도, 엔진 상태(봉 단위·종목)로도 덮어쓰지 않는다. 계획은 「저장값을 채우지 않음」만 적었다. 사용자가 고친 칸을 늦게 온 상태 응답이 바꾸지 않게 한 것이다.
- A1 이력이 없거나 깨졌으면 화면 위 한 줄은 「기본 설정」. 건너뛰면 「저장값 불러오기 건너뜀 — 그사이 칸을 고쳤거나 실행 중입니다」.
- L1 보유 구간은 감사 체결 행으로 정한다: 보유 없음에서 봇 매수(BUY)가 나오면 시작(분할 회차 2 이상이면 첫 매수가 창 밖이라 건너뜀), 매도(SELL·HTS_SELL)에서 끝. 외부 매수로 시작한 보유는 줄 0개.
- L1 단계는 0 쪽으로 자른다(+1.2% → +1.0% 단계, -0.7% → -0.5% 단계). 오른 쪽과 내린 쪽을 따로 「처음 넘은」 단계로 센다.
- L1 40줄을 넘으면 최근 40줄을 남기고, 버린 줄 가운데 가장 새 줄 시각에 「평단 대비 단계 줄 앞 n줄 생략」 한 줄.
- L1 안내 문구(창이 밀리면 줄이 사라짐)는 로그 탭 감사 로그 위 한 줄.
- L2 6값은 「설정 적용 …」 줄 뒤에 「 — 적용 뒤: 익절 …」으로 붙인다. 못 정한 행은 지금 글 그대로(6값 없음).
- O1·O2 서버 칸: 운용 GET /v2/api/ops 의 settings_text, 홈 GET /v2/api/status 의 pullback_settings(새 전략일 때만). 둘 다 control.settings_summary_text 한 함수.
- 새 시험: tests/v2/test_fullback_1121.py(37개) · tests/v2/js/bt_start.test.mjs(11개). 고친 시험: bt_ui.test.mjs 배치 시험 · bt_ui_ver9.test.mjs 바깥 요청 셈(last-saved 뺌) · save.test.mjs 「닫기」.
- (verifier 1회 「고친 뒤 승인」 반영, 11/24) L1: 보유 없음에서 외부 매수(HTS_BUY·HTS_BUY_ADD)가 먼저 나오면 다음 매도까지 그 구간은 시작을 모르는 것으로 보고 줄 0개(그 뒤 봇 매수 회차 1·회차 없음이 와도). 같은 봉에 「평단 변경」 줄과 단계 줄이 함께 나면 최신순 화면에서 단계 줄이 위(평단 변경 순서 값 4, 단계 2). A1: 머리 막대 모드(btMode)는 상태 응답이 5초 뒤에 와도 채운다(예전 동작) — 종목·봉 단위 자동 채움만 5초 규칙. v2/db.py 주석의 시험 파일 이름 고침.
- **실제 바뀐 파일 목록(3단계·7단계의 초안 목록을 대신한다 — 배포 전 diff 대조는 이 목록으로)**:
  - v2 8개: v2/api_read.py · v2/api_write.py · v2/control.py · v2/db.py · v2/static/backtester.html · v2/static/bt_ui.js · v2/static/app.js · v2/static/index.html (초안의 save.js 는 고치지 않음 — 「닫기」는 backtester.html 글자만)
  - 시험 6개: tests/v2/test_fullback_1121.py(새) · tests/v2/js/bt_start.test.mjs(새) · tests/v2/js/bt_ui.test.mjs · tests/v2/js/bt_ui_ver9.test.mjs · tests/v2/js/save.test.mjs · tests/v2/test_api_read_pullback.py(㉠ 11/25 — 이름표 목록 고정 시험에 새 키 5개)
  - 문서 2개: docs/plans/2026-11-21-fullback-requests/plan.md(새) · docs/specs/v2-dashboard/HANDOFF.md(1121-03 줄만)
  - 커밋 때 더함: pages/dashboard.py(버전 줄) · Fable 질의 파일 · 연락 기록(안내 보낼 때)
- (Fable 1회 「수정 후 진행」 막음 1개 반영, 11/24) L1 외부 매수는 type 이 아니라 reason 으로 가린다 — 엔진은 외부 매수를 type='BUY' · reason='HTS_BUY'|'HTS_BUY_ADD' 로 남긴다(engine/order_reconciler.py 957~973, services/db.py 2810·2835·3035). SQL_LOGS_AUDIT_TRADES 가 reason 칸을 이미 읽는다. 옛 type 검사도 함께 둔다(해 없음). 시험은 실제 행 모양으로 다시 씀 + 창이 보유 중간(HTS_BUY_ADD · meta 없음)에서 시작하면 줄 0개.
- (PO 결정 11/24) 강제 매수(reason force_buy, 분할 회차 없음)는 봇이 낸 매수라 보유 시작으로 본다(시험 test_force_buy_starts_holding).
- A1 늦은 상태 응답: 상태 응답이 5초를 넘고 이력도 없으면 종목·봉 단위 자동 채움은 하지 않는다(화면 기본값 그대로 · 머리 막대 모드만 늦게라도 채움). 예전에는 늦게 와도 봉 단위를 덮어썼다.
- 사실 8(저장본·적용본 시각이 다를 수 있음)의 까닭: 운용 탭 거래 시간 4키를 바꾸면 _sync_saved_ops_keys(v2/api_write.py)가 저장본 파일만 다시 쓰고(적용본은 엔진이 따로 합침), 그래서 두 파일의 수정 시각은 달라도 값은 같을 수 있다.
- (㉠ 11/25 사용자 승인 「1121-03 커밋 승인 · ㉠ 적용」) 감사 로그 「설정 적용」 줄의 추적 손절 3키를 한국어로 씀: 「추적 손절 끔→켬 · 추적 손절 방식 고정폭 · 손절폭 30%」. 방식 낱말은 control.TS_MODE_WORDS 한 곳(6값 줄과 같이 씀). 엔진 변경 기록 키를 모두 대조해 이름 없던 투자 비율 2키(invest_ratio_pct_live·_test)도 「투자비율(실계좌)·(모의)」로 더함.


- (11/25 서버 읽기 정정) F14 의 「3분봉 약 60시간」은 틀렸다. 매도 판단 행은 보유 중에만 쌓여 서버 1200행 창이 11/07~11/24(약 17일)였다. 잠정 봉 행 0 · wallet_zero 행 0 · 같은 봉 여러 행 0. 화면 안내 문구를 「보유 중에 쌓이는 최근 매도 판단 기록 1200건」으로 고침.
