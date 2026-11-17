# 1111-01 투자자 Ver9 반영 계획 (초안 · 11/17 · 저장소 기록 전)

## 0. 정해진 것
- 투자자 답(11/17, 사용자 전달): ㉠ ① 선물 백테스트(롱+숏)를 넣되 화면 계산만. 실제 매매는 업비트 현물 그대로. ㉡ ① 백테스터 첫 기본값을 Ver9 값(분할 1 · 익절 3 · 손절 3)으로.
- 11/16 PDF 요청 2가 「새로 들어갈 것」으로 안내한 기능도 범위에 넣는다: 월·주별 1등 조합과 「다음 기간에 그대로 쓰면」, 둔화 허용치 축, 조합 상한 20,000, CSV 추가, 차트(전체화면 · 끌어 이동 · 표시 밀도).
- 지킬 것: 업비트 시세 선택, 정해진 차이 10곳(1105-06 2곳 · 1110-01 추적 손절 8곳), −/+ 단추, 요약 카드, 저장 창.
- PDF 약속: 「대시보드가 바뀌기 전에 바뀌는 점을 다시 안내드리겠습니다」 → 배포 전에 투자자 안내(체감 변경 통보)가 필요하다.

## 1. 방식 — 「Ver9 원문 + 정해진 차이」로 기준 원문만 바꾼다
- 지금 backtester.js 는 「Ver2 인라인 스크립트(168~1212줄) + 차이 10곳」을 scripts/build_backtester_js.mjs 로 만든 것이고, parity 시험이 바이트 동일을 고정한다(tests/v2/js/ver2_source.mjs, parity.test.mjs:27-36).
- 같은 틀을 그대로 쓰고 기준 원문만 Ver9 로 바꾼다. Ver9 스크립트 = docs/new-version/ver9/MA_GC_Pullback_Backtester_2611161307(Ver9).html 196~1902줄(196줄 `let tradeRows=[]…`, 1902줄 `attachSteppers();`, 확인함).
- 차이 10곳의 find 문자열을 Ver9 에 대 본 결과(scratchpad chk_v9patch.py, 11/17): 0~8번은 Ver9 에 정확히 1번, **9번(설정 3칸 읽기)은 0번**. Ver9 readCfg 끝이 `compounding` 뒤에 `futMode · cUseSl · useFunding` 3줄을 더해서다(Ver9:742-766). → 9번 find 를 `useFunding:$("useFunding").value==="yes"\n  };` 로 바꾸고 replace 도 같은 자리에 추적 손절 3칸을 붙인다.
- 덮어쓰기 안(Ver9 html 통째로)은 쓰지 않는다. 잃는 것이 많다(ver9-gap.md 2-2: 업비트 출처, 차이 10곳, 요약 카드, −/+ 36px, 저장 창, 아래 메뉴).
- 따로 모듈을 만드는 안도 쓰지 않는다. 다음 판(Ver10)을 받을 때 다시 원문 비교가 어려워진다.

## 2. 단계별 바꿀 것

### 단계 1. 기준 원문 전환 (backtester.js 다시 만들기)
| 파일 | 바꿀 것 |
|---|---|
| tests/v2/js/fixtures/ver2_patches.json | source → Ver9 경로, script_lines → [196, 1902], 9번 find·replace 고침, note 문구 |
| tests/v2/js/ver2_source.mjs | 주석만(Ver2 → 기준 원문). 함수 이름은 그대로(시험 import 많음) |
| v2/static/backtester.js | `node scripts/build_backtester_js.mjs` 로 다시 만듦(손으로 고치지 않음). 1066줄 → 1729줄(verifier 사본 실행 98,444바이트) |
| scripts/build_backtester_js.mjs | 주석만 |
- 결과: 현물 simulate·stats 는 Ver2 와 줄 단위로 같으므로(ver9-gap.md 1-1, md5 3adb0f6e) 현물 결과는 바뀌지 않아야 한다 → 단계 4의 기준값 재생성 diff 로 확인.

### 단계 2. 화면(backtester.html)
| 자리 | 바꿀 것 |
|---|---|
| 111-113줄 | maxSplits 5→1, tp 1.0→3, sl 1.5→3 (㉡ ①) |
| 스윕 칸 169-177줄 | Fable 권고 「스윕 기본 범위 3개」: Ver9 값을 따른다 — SL 0.5~2 → 1~5, 분할 3~8 → 1~1, 기울기 끝 0 → 1 (㉡ ① 과 같은 뜻으로 봄 · 사용자 확인 항목 1) |
| 스윕 칸 뒤 | 둔화 허용치 3칸 sw_dropFrom 0 · sw_dropTo 0.4 · sw_dropStep 0.1 (Ver9:154-156) |
| 실행 단추 줄 | 「선물 백테스트(롱+숏)」 단추 추가(onclick runFutures). 업비트 출처면 막힘 + 안내 「선물은 바이낸스 출처에서만 됩니다」 |
| 새 접힘 「선물 설정」 | futMode(A·B·C) · cUseSl · useFunding 3칸(Ver9:117-121 그대로) + 안내 「선물은 바이낸스 USDT 무기한 선물 시세와 펀딩비로 계산합니다. 업비트 원화 시세가 아닙니다. 추적 손절은 현물에만 적용됩니다.」(Fable 권고 「USDT 기준 안내」) |
| 199줄 | 「스윕 결과 (상위 20)」 → 「(상위 10)」, 안내문 「최대 1000개」 → 「최대 20,000개」 |
| 차트 영역(바꿈) | chartBox · fsBtn 추가, 「전체 봉」 단추(showAllBars). chartWrap(지금 :214)은 이미 있으므로 바꿈: overflow:hidden, chartInner inline-block→block, canvas touch-action pan-x→pan-y, chart_barCount 문구 · chartInfo 안내문(Ver9:204-221). 지금의 가로 스크롤은 없어진다 → 1-A 「사라지는 것」 보고 대상 |
| 차트 비우기 뜻 | 출처 바꿀 때 「차트를 처음 상태로」 = 캔버스를 지우고 chartHint 를 처음 문구로 돌림(Ver9 에는 차트 비우는 함수가 없음 · Fable 2회째 권고) |
| style(추가) | 전체화면 CSS Ver9:32-39(`#chartBox.fs{position:fixed…}`, `body.chart-fs{overflow:hidden}`, 전체화면 안 canvas touch-action:none). setChartFs 는 클래스만 바꾸므로 이 CSS 가 없으면 전체화면이 안 됨 |
| 지키는 것 | 머리 막대·아래 메뉴·요약 카드·「설정 20개 더 보기」 접힘·「자세한 결과」 접힘·−/+ 단추 CSS(36px)·saveArea·스크립트 순서(backtester.js → bt_ui.js → save.js) |
- 칸 이름 확인(chk_ids.py): Ver9 스크립트가 쓰는데 지금 html 에 없는 id 는 cUseSl · chartBox · fsBtn · futMode · useFunding(+ chartWrap, sw_drop 3칸) 이 전부다.

### 단계 3. bt_ui.js (업비트 출처 · 요약 카드 연결)
| 자리 | 바꿀 것 |
|---|---|
| fetchKlines 감싸기(bt_ui.js:195-215) | 인자에 market 추가. `market==="futures"` 이고 출처가 업비트면 오류 「선물은 바이낸스 출처에서만 됩니다」를 던진다(업비트 현물 봉이 선물 계산에 들어가는 것 막기 — ver9-gap.md 3-3). 바이낸스면 원래 함수에 그대로 넘김 |
| 출처 바꿀 때(bt_ui.js:252-254 clearDataCache, 호출 :271) | dataCache 와 함께 futCache 도 비움. 직전 결과 변수 lastBars · lastResults · sweepRows 를 비우고 lastMode 를 처음 상태로 돌림(Ver9:1193 lastMode="futures"). **화면에 보이는 결과도 처음 상태로**: btBrief · sweepBrief · summary · depth · weekly · monthly · sweepResult · 차트(Fable 1회째 막음 1). 까닭: 저장 창은 「마지막으로 돌린 출처」가 아니라 「창을 열 때 고른 출처」를 쓴다(save.js:75-77 makeSnapshot, 103-107 「시험한 데이터」). 바이낸스 선물을 돌린 뒤 업비트로 바꾸면 화면에 선물 결과가 남은 채 저장 창이 「업비트」로 열리고, 저장하면 서버 검사(api_write.py:246-250)도 통과한다. 보내지는 것은 설정 값뿐이라 엔진은 현물 그대로지만, 선물 결과를 보고 실계좌 설정을 바꾸는 오해를 막는다. 이 비우기는 현물에도 적용된다(지금의 「업비트로 돌린 뒤 바이낸스로 바꿔 스윕」이 없어짐 → 1-A 사라지는 것) |
| 출처 전환 | 업비트면 선물 단추 disabled + 안내, 바이낸스면 풂(Fable 권고 「업비트 출처일 때 선물 단추 막기」) |
| runFutures 감싸기 | run 과 같은 겹침 막기(running) · **await 로 끝난 뒤** 요약 카드 갱신(현물/선물 표시) |
| runSweep 감싸기(bt_ui.js:244-248) 고침 | 지금은 비동기 runSweep 을 기다리지 않고 바로 sweepRows 를 읽는다. Ver2·Ver9 모두 첫 await 전에 `sweepRows=[]` 를 두므로(backtester.js:625-627, Ver9:1223-1225) 스윕 요약 카드는 늘 빈 목록으로 그려지는 것으로 보인다(코드 읽기 · 브라우저 미확인). 「요약 카드 지킬 것」의 전제라 이번에 await 로 고친다. 구현 전에 지금 화면에서 한 번 보고 사실을 확정한다 |
| sweepBrief · sweepHtml(bt_ui.js:148-183) 고침 | 지금 카드는 TP · SL · 분할 · 수익률만 보인다. Ver9 기본 스윕은 분할 1개 × 기울기 11 × 둔화 5 라 같은 TP · SL 이 55줄씩 생겨 줄을 구분할 수 없다 → 「60선 기울기」 · 「둔화 허용치」 칸을 더한다(Fable 1회째 막음 2). 선물 스윕이면 카드 제목에 「선물」과 출처 |
- 저장 창: save.js 는 고치지 않는다. save.js 는 정해진 25칸 + 추적 손절 3칸만 보내므로 선물 3칸은 서버로 가지 않는다. 바이낸스 출처면 「이 설정으로 동작」이 막힌다(save.js:153-154). 저장 창은 창을 열 때 고른 출처를 쓰므로, 선물 결과가 화면에 남은 채 업비트로 바꿔 저장하는 틈은 위 「출처 바꿀 때 화면 결과 비우기」로 막는다.

### 단계 4. 시험
**깨지는 기존 시험과 고칠 방법**
| 시험 | 깨지는 까닭 | 고칠 방법 |
|---|---|---|
| parity.test.mjs:15(VER2_SHA) · :20-24 | sha 고정 · 시작/끝 줄 | Ver9 sha 로 바꿈. 시작·끝 줄은 같음 |
| parity.test.mjs:26-36 | 바이트 동일(기준 원문 바뀜) | 다시 만든 backtester.js 로 통과(verifier 사본에서 통과). 차이 개수 2 · 8 그대로 |
| parity.test.mjs:38-61 | 칸 41개 · 기본값 = Ver2 | 기준 = Ver9 칸 47개(입력 37 · 선택 10) · 원문에 없는 칸은 추적 손절 3칸뿐 |
| parity.test.mjs 세트 a·b·c | 기본값·스윕 표가 바뀜 | 단계 1만으로는 실패(이식본 html 이 Ver2 기본값). 단계 2 에서 html 기본값을 Ver9 로 맞추면 통과 예상 |
| bt_ui.test.mjs:378-478 (특히 :465 칸 44개) | 기본값 · 칸 수 | 44 → 50(47 + 추적 손절 3). Ver9 기본값으로 고침 |
| 가짜 window·document 5곳: harness.mjs:118 · bt_cache_agg.test.mjs:47 · trailing.test.mjs:14-22 · ver2_diffs.test.mjs:17 · pullback_reference.mjs(생성기 ctx.window) | Ver9:1531-1542 가 맨 위에서 document · window 에 처리기를 붙여 `window.addEventListener is not a function` 으로 불러오기 단계에서 멈춤(verifier 사본 실행: 20개 실패, 보탠 뒤 예상한 6개만 실패) | 다섯 곳의 가짜 window · document 에 addEventListener(아무 일 안 함)를 더함 |
| save.test.mjs:180,233 · basic.test.mjs:278 | html 을 읽음 | 단계 2 뒤 다시 돌려 확인 |
| test_static_lint.py:34-37 | fapi.binance.com 이 허용 목록 밖 | backtester.html·backtester.js 허용 목록에 fapi.binance.com 한 줄 추가. bt_ui.js 는 바깥 주소 0개 그대로 |
| pullback_reference.test.mjs:15-18 | 원본 스크립트 sha | 생성기 가짜 window 고친 뒤 `node tests/v2/js/pullback_reference.mjs --write-expected` 로 45개 다시 만들고, **meta.script_sha256 줄 말고는 diff 0** 을 확인한 뒤 cfgs.json sha 갱신(verifier 사본에서 45줄 모두 script_sha256 줄뿐임을 확인). 다른 diff 가 나오면 멈추고 보고 |
| ver2_diffs.test.mjs · trailing.test.mjs | 가짜 window(위 줄) | 위 줄로 고친 뒤 차이 2곳 · 8곳 그대로면 통과 |
| 새 시험 추가 | runSweep 감싸기 await 고침 | 비동기 가짜 runSweep 으로 카드가 끝난 뒤 목록으로 그려짐을 확인(bt_ui.test:239 는 동기 가짜라 지금 결함을 못 잡음) |
- 엔진 일치(tests/regressions/test_r_2026_10_28_p3_t10_parity.py)는 expected 의 매수·매도 목록만 읽는다. 목록이 같으면 고칠 것이 없다.

**새 시험**
| # | 시험 | 내용 |
|---|---|---|
| N1 | 선물 동등성(parity) | Ver9 원문 스크립트와 이식본을 같은 가짜 fapi 봉·펀딩비로 돌려 방식 A·B·C × cUseSl 2 × useFunding 2 의 거래 CSV·요약이 같음 |
| N2 | 선물 스윕 동등성 | 선물 기준으로 스윕한 5개 CSV(스윕 · 기울기별 · 둔화별 · 월별 1위 · 주별 1위)가 원문과 같음 |
| N3 | 현물 스윕 5개 CSV 동등성 | 현물 기준 같은 시험 |
| N4 | 업비트 출처 선물 막기 | 업비트면 runFutures 가 바깥 요청 0건으로 오류 문구, 단추 disabled |
| N5 | 출처 바꿀 때 비우기 | 바이낸스 선물 실행 → 업비트 선택 → futCache = null, lastBars · lastResults · sweepRows 비움, btBrief 빈 안내 · sweepBrief 빈 목록 · summary 비어 있음, 스윕 안내 「먼저 실행」 |
| N9 | 카드 줄 구분 | TP · SL · 분할이 같고 기울기(또는 둔화)만 다른 sweepRows 2줄 → 카드 두 줄 글자가 서로 다름 |
| N10 | 선물 뒤 저장 창 | 바이낸스 선물 실행 → 업비트 선택 → 저장 창 열기: 화면 결과가 비워져 있고 창은 업비트 출처 현재 입력값만 보임 |
| N6 | 바깥 연결 0 | JS 시험은 vm 컨텍스트에 실제 fetch 가 없고 가짜 fetch 만 넣는다(harness.mjs:87-110 · tests/_netguard 는 Python 전용). 새 선물 시험에는 「가짜 fetch 만 불렸음 · 요청 주소 목록」 단언을 넣는다. 새 고정 자료 fixtures/fut_klines_a.json · fut_funding_a.json 은 기존 klines_a 를 바탕으로 만든 합성 자료(실제 바이낸스 호출 안 함) |
| N7 | 기본값 고정 | maxSplits 1 · tp 3 · sl 3 · 스윕 범위 Ver9 값 |
| N8 | 요약 카드 await | 비동기 runSweep · runFutures 뒤 카드가 실제 결과로 그려짐 |
- 한계: N1~N3 은 원문과 이식본이 같은 선물 코드를 쓰므로 「차이 10곳이 선물로 새지 않았다」만 확인한다. 선물 규칙 자체가 옳은지는 확인하지 않는다(투자자 원문 그대로).
- 멈춤 조건: 단계 2 뒤 parity 세트 a·b·c 가 통과하지 않으면(원인이 기본값 차이뿐이 아니면) 멈추고 보고한다.
- 시험 수: 기존 고침 11묶음(위 표) · 새 시험 10개(조합 포함 개별 단언 수는 구현 때 셈). 끝 기준: `bash scripts/regression_gate.sh` + `node --test tests/v2/js/*.test.mjs`(regression_gate.sh:208 과 같은 명령. 폴더 이름만 주면 Node 22 에서 MODULE_NOT_FOUND).

### 단계 5. 브라우저 실측 (project-rules 1-A)
- 로컬 v2 개발 서버에서 휴대폰 폭(390px)과 PC 폭으로: 현물 실행 · 선물 실행(바이낸스) · 업비트에서 선물 단추 막힘 · 스윕 기본값 실행 시간 · 전체화면이 머리 막대와 아래 메뉴를 덮는지 · 끌어 이동 · −/+ 단추 · 저장 창 열림 · 스윕 뒤 요약 카드에 결과가 보이는지.
- 실측 순서 추가: 바이낸스 선물 실행 → 업비트 선택 → 화면 결과가 비워지는지 → 저장 창 열기.
- 사용자 브리핑(1-A 2층): 없어지는 것 = 차트 가로 스크롤, 스윕 「상위 20」 → 「상위 10」, 출처를 바꾸면 직전 결과가 비워짐(현물 포함). 접힘에 들어가는 것 = 선물 3칸(새 「선물 설정」 접힘 · 선물 단추는 실행 줄에 드러남).
- 스윕 시간 기준: PC 와 휴대폰에서 기본값 스윕 시간을 초 단위로 잰다. 휴대폰 60초를 넘으면 7절 질문 1의 대안(기울기 · 둔화 축 기본을 「시작=끝」)으로 가자고 사용자에게 보고한다.
- 스윕 시간: 기본 조합이 168개(7×4×6×1)에서 3,465개(TP 7 × SL 9 × 분할 1 × 기울기 11 × 둔화 5)로 늘어난다. 상한 20,000 은 그대로.
- 실측 때만 바깥 연결(fapi.binance.com)을 쓴다. 시험에서는 쓰지 않는다.

## 3. 실제 매매 영향
- 바꾸는 파일은 v2/static/backtester.html · backtester.js · bt_ui.js 와 시험·고정 자료뿐이다. 엔진(core/ · engine/) · 주문(core/trader.py) · 저장 API(v2/handlers.py · params_schema.py) · save.js 는 건드리지 않는다.
- 선물은 브라우저 안 계산뿐이고 서버에 아무것도 보내지 않는다. 바이낸스 출처면 「이 설정으로 동작」이 이미 막혀 있다. 다만 저장 창은 창을 열 때 고른 출처를 쓰므로, 선물 결과가 화면에 남은 채 업비트로 바꿔 저장하는 틈이 있었다 → 단계 3 「출처 바꿀 때 화면 결과 비우기」로 막는다(보내지는 것은 설정 값뿐이라 엔진 동작은 현물 그대로).
- 저장 경로 근거(verifier 확인): 화면은 save.js:153-154 가 업비트 출처가 아니면 「이 설정으로 동작」을 막고, 서버도 api_write.py:246-250 에서 마지막 이력 출처가 upbit 가 아니면 400 을 돌려준다. 「저장만 하기」는 저장본 파일에만 쓰고 엔진은 적용 요청 때만 읽는다(engine/pullback_params.py:5).
- 남는 위험 1가지: 기본값이 분할 1 · 익절 3 · 손절 3 으로 바뀌므로, 투자자가 업비트 출처에서 값을 그대로 둔 채 저장·적용하면 그 값이 실계좌 설정이 된다(분할 1 이면 한 번에 투자 비율 전체, save.js:264). 저장 확인 창이 값을 보여 주고 투자자가 누르는 일이라 막지 않는다. 투자자 안내에 한 줄 넣는다.
- 현물 스윕 뜻 변화: Ver9 rangeOrBase(Ver9:1236-1242)는 스윕 칸 「시작=끝」이면 위쪽 설정값을 쓴다(Ver2 는 스윕 칸 값). 60선 최소 기울기 설정이 0 이 아니면 현물 스윕 결과가 달라질 수 있다. 화면 계산만이고 실매매는 바뀌지 않는다(안내 여부는 7절 질문 4).

## 4. 바깥 연결(CSP · 허용 주소)
- 저장소 안 v2 서버와 nginx 설정에는 CSP 가 없다(ver9-gap.md 3-2). 맥에서 fapi 두 주소가 200 · `Access-Control-Allow-Origin: *` 를 돌려줌(11/16 curl).
- 확인하지 못한 것: 서버의 실제 nginx(저장소 밖)에 11/08 보안 작업 때 헤더가 더해졌는지 → 구현 전에 사용자 `!` 읽기 1번(`nginx -T | grep -iE "add_header|content-security"`). 휴대폰 망·지역에서 바이낸스 선물이 막히는지(HTTP 451) → 실측 때 확인. 막히면 선물 단추에 Ver9 오류 문구가 뜬다(계산 없음, 매매 영향 없음).
- 시험 허용 목록에 fapi.binance.com 이 들어가면 「백테스터가 부를 수 있는 바깥 주소」가 4곳이 된다. 키가 필요 없는 공개 시세다.

## 5. 배포
- 커밋 전 pages/dashboard.py 버전 갱신(v2/static 은 실행 소스다 — 메모 feedback_version_bump_scope).
- 배포: 서버 git pull + **tradebot-v2 만 재시작**(1112-01 과 같은 방식). 엔진(tradebot)은 재시작하지 않는다. 정적 파일은 Cache-Control no-cache(v2/handlers.py:140)라 새로고침이면 새 파일을 받는다.
- 배포 전 표준 정지선: 서버 HEAD · dashboard.py 버전 · tradebot · tradebot-v2 기동 시각 · tradebot-v2 unit(PartOf/BindsTo 없음) · `nginx -T | grep -iE "add_header|content-security"` 를 읽기 전용 스크립트로(사용자 `!` 실행).
- 1시간 관찰: v2 오류 0 · 엔진 그대로(기동 시각 같음) · 주문 줄 변화 없음.
- 되돌리기: `git revert <커밋>` → push → 서버 pull → tradebot-v2 만 재시작 → 엔진 기동 시각이 그대로인지 확인.
- 순서: 구현 → verifier → Fable(project-rules 「Fable 검산용 보고 번들 zip」 규칙대로 report.md · 근거 파일 zip) → 사용자에게 구현 보고 → 커밋·push 승인 → **투자자 안내(배포 전, PDF 약속)** → 배포 승인 → 표준 정지선 → 배포 → 관찰 → 보고.

## 6. 투자자 안내(체감 변경 통보)
- 필요하다. 백테스터 화면 · 기본값 · 단추가 바뀐다. PDF 에서 「바뀌기 전에 안내」를 약속했다.
- 넣을 것: 선물 단추와 「바이낸스 USDT 시세 · 화면 계산만」, 업비트 출처면 선물 막힘, 기본값 분할 1 · 익절 3 · 손절 3, 스윕 범위·둔화 축·상위 10·월주 1등, 차트 전체화면·끌어 이동, 「설정 저장 때 값 확인」 한 줄. 투자자 연락 기록에 남긴다.

## 7. 사용자에게 물을 것
1. 스윕 기본 범위(SL 1~5 · 분할 1~1 · 기울기 끝 1 · 둔화 0~0.4)도 Ver9 값으로 바꿀까요? 권고: 바꿈(㉡ ① 과 같은 뜻). 비용: 기본 조합이 168개 → 3,465개(약 20배)로 늘어 휴대폰에서 오래 걸릴 수 있다(화면은 엔진 봉 단위를 기본으로 씀 · bt_ui.js:302 · 1분봉 30일이면 43,200봉 · 엔진 봉 단위는 추정). 분할 1~1 이면 스윕이 분할 횟수를 바꿔 보지 않는다. 대안: 휴대폰 60초를 넘으면 기울기 · 둔화 축 기본을 「시작=끝」으로 둠.
2. 차트를 Ver9 방식(끌어 이동)으로 바꾸면 지금의 가로 스크롤은 없어집니다. 권고: Ver9 방식(PDF 에 안내함).
3. 투자자 안내는 메신저 글로 할지 PDF 로 할지. 권고: 짧은 메신저 글.
4. 현물 스윕 「시작=끝」 뜻 변화(3절)를 투자자 안내에 넣을지. 권고: 넣지 않음(투자자가 만든 Ver9 동작이고 Ver9 주석이 설명함).
5. 기본값 위험: 새 기본값(분할 1)을 그대로 두고 업비트 출처에서 저장·적용하면 한 번에 투자 비율 전체로 산다(투자자는 11/11부터 실계좌 눌림목). PDF 질문 ㉡ 은 「실제 매매 설정과 상관없습니다」라고 적었다. 권고: 막지 않고 투자자 안내에 「설정 저장 때 분할 · 익절 · 손절 값을 꼭 확인」 한 줄(저장 확인 창이 값을 보여 줌).
6. 선물 계산 규칙은 투자자 Ver9 원문 그대로라 현물 보정 2곳(구간 순번 · 건너뜀 횟수)이 들어가지 않는다. 권고: 고치지 않고 안내에도 넣지 않음(화면 계산만 · 투자자가 만든 규칙).

## 8. 틀릴 수 있는 곳
- 9번 차이 find 고침과 다시 만들기는 verifier 가 scratchpad 사본에서 실행해 바이트 동일 시험 통과를 봤다. 저장소에서는 구현 때 다시 돌린다.
- 기준값 45개가 meta 말고 같다는 것은 사본에서 확인했다(생성기 가짜 window 보탠 뒤). 저장소에서 다시 확인한다.
- 스윕 요약 카드가 지금 늘 비어 보인다는 것은 코드 읽기로만 확인했다. 구현 전에 지금 화면에서 본다.
- 선물 코드는 투자자 원문을 그대로 쓴다. 선물 규칙 자체가 현물 보정 2곳과 다르다(ver9-gap.md 1-1) → 7절 질문 6.
- 휴대폰에서 3,465개 스윕 시간을 재 보지 않았다(사본 parity 세트 하나가 약 7초로 늘었다).
- 서버 nginx 헤더 · 서버 unit · 서버 HEAD 는 이번에 보지 못했다(배포 전 표준 정지선에서 본다).
