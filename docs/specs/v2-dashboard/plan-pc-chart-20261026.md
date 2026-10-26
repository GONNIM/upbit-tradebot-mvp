# 계획서 — PC 를 모바일과 같은 화면으로 + 차트 탭만 넓게 (2026-10-26, 결정 1026-08)

**한 줄:** PC(창 폭 641px 이상)도 휴대폰과 같은 `index.html`(홈·차트·로그·운용 탭)을 연다. 홈·로그·운용은 가운데 480px 폭, 차트 탭에서만 화면 전체 폭·높이로 차트를 넓힌다. 정적 파일 캐시 방지(1025-17)를 같이 넣는다. 모바일(640px 이하)은 바뀌지 않는다.

## 0. 근거와 결정
| 결정 | 원문 | 뜻 |
|---|---|---|
| 1026-08 1 가 | 「1026-08 1 가」 | PC 는 모바일과 같은 화면, 차트 탭만 창 전체 폭·높이 |
| 1026-08 2 200 | 「2 200」 | 봉 수 200 그대로(업비트 호출 1회) |
| 1026-08 3 같이 | 「3 같이」 | 1025-17 정적 파일 Cache-Control 을 이번에 함께 |
| 1026-04 보류 | 「1026-04 보류」 | 통보 A′ 는 이 변경 배포 뒤 PC 문장을 고쳐 발송 |
- 제안 Fable: `docs/fable/2026-10-26-pc-chart-proposal-1.md`(2회째 「진행」).
- 사용자 원 요구: 「1. 모바일은 그대로 유지한다. 2. PC 화면을 모바일과 동일하게 유지한다. 단 차트를 PC 화면을 이용하여 넓게 확대하여 제공」.

## 1. 바뀌는 것 (파일별)
| # | 파일 | 바꾸는 것 |
|---|---|---|
| F1 | `v2/static/index.html` | 6행 PC 넘김 스크립트 삭제. `<body>` 에 `:class="{ 'tab-chart': tab === 'chart' }"` 추가 |
| F2 | `v2/static/app.js` | 20행 `__v2toPC` 가드 삭제. 차트 칸 높이 맞춤 `fitChart()` 추가: (1) 탭이 차트로 바뀐 뒤 `this.$nextTick()` + `requestAnimationFrame` 안에서 잼(바꾼 직후에는 칸이 숨어 있어 top 0), (2) 창 크기 변경, (3) `chartFail`·`chartNote` 가 바뀔 때(`$watch`) 다시 잼. 창 폭 641px 이상(`window.matchMedia("(min-width: 641px)").matches` — CSS 와 같은 기준)일 때만 inline 높이를 넣고, 641px 미만이 되면 `el.style.height = ""` 로 지워 모바일 CSS(360/300px)로 돌린다 |
| F3 | `v2/static/basic.js` | 327행 `__v2toPC` 가드 삭제 |
| F4 | `v2/static/chart.js` | 순수 함수 `fitChartHeight(viewportH, chartTop, reservedPx, minPx)` 추가 → `max(minPx, viewportH - chartTop - reservedPx)` (node 시험 대상) |
| F5 | `v2/static/style.css` | `@media (min-width: 641px)` 절 추가: body 와 `.bottom` 을 가운데 480px(`max-width:480px; margin:0 auto`, `.bottom` 은 `left:50%; right:auto; transform:translateX(-50%); width:100%; max-width:480px`), `body.tab-chart` 와 그 `.bottom` 은 `max-width:none`(창 전체 폭). 모바일 규칙(640px 이하)은 손대지 않음 |
| F6 | `v2/static/basic.css` | `@media (min-width: 641px)` 에서 `#basic[data-page="home"] .bx-grid { grid-template-columns: 1fr; }` — 480px 안 카드 폭 약 438px < 3칸 최소 470px 이라 넘침 방지. 백테스터 페이지 블록(3칸)은 그대로 |
| F7 | `v2/handlers.py` | `StaticHandler.set_default_headers` 에 `Cache-Control: no-cache` 1줄 + `get_cache_time` 이 0 을 돌려주게(나중에 `?v=` 를 붙여도 tornado 가 max-age 10년으로 덮어쓰지 않게 — tornado web.py:2869-2876·3122, PO 판단). 브라우저가 매번 ETag 로 확인해 바뀐 CSS·JS 를 바로 받음(안 바뀌면 304, Cache-Control 유지). backtester.html 도 이 경로. index.html 은 정적 경로에서 404(handlers.py:139-142)라 EntryHandler 의 no-store(handlers.py:105) 하나로만 나감 |
| F8 | `tests/v2/js/basic.test.mjs` | 「PC 넘김」 머리 주석·보조 함수 `redirectScript`·`runRedirect`(342~365행)와 367·375 행 시험 2개 삭제 → 「index.html 에 넘김 스크립트·`__v2toPC` 없음」 1개로 교체, 445 행 가드 시험 → 「app.js·basic.js 에 `__v2toPC` 없음」 |
| F9 | `tests/v2/js/chart.test.mjs` | `fitChartHeight` 시험(보통·작은 창 최소값·음수 방지) |
| F10 | `tests/v2/test_server.py` | `/v2/static/style.css` 응답에 `Cache-Control: no-cache`, `?v=1` 요청도 no-cache, 304 응답에도 남는지 시험(304 는 첫 응답의 ETag 를 `If-None-Match` 로 보내 얻음) |
| F11 | `docs/specs/v2-dashboard/spec.md` | 19행 G2·119행 4.3 PC 배치·242행 A21 을 결정 1026-08 로 개정(PC 홈 API·업비트 브라우저 호출 생김 명시) |
| F12 | `docs/specs/v2-dashboard/plan-pc-basic-20261025.md` | 114행 「PC 에 실시간 차트·로그 없음」 → 「1026-08 로 PC 도 차트·로그 있음(이 계획서 참조)」 주석 |
| F13 | `pages/dashboard.py:495` | 버전 갱신(커밋 규칙) |

- **Python 변경: v2 서비스의 `v2/handlers.py` 몇 줄(F7)뿐.** 엔진(`core/`·`engine/`·`services/`)·API·DB 는 바뀌지 않는다. (제안 때 「Python 변경 0」이라 적었으나 3 「같이」를 고르시면서 F7 이 생김 — 보고에 정정 기재.)
- 백테스터 페이지(`backtester.html`·`backtester.js`)는 바꾸지 않는다. 백테스터에서 홈으로 돌아오는 단추는 넣지 않는다(모바일과 같이 브라우저 뒤로가기 — PO 판단, 원하시면 계획 승인 때 말씀).
- 차트 높이 기준(PO 판단): **PC 차트 탭에서 문서 세로 스크롤 0** — 차트 아래 안내 2줄까지 아래 탭 막대 위에 보인다. 차트 칸 위치는 머리 경고·차트 실패 문구 유무로 달라지므로 고정 계산 대신 JS 로 잰다. 위치는 **문서 기준(`rect.top + window.scrollY`)** 으로 잰다(`go()` 는 스크롤을 되돌리지 않아, 화면 기준 `top` 을 쓰면 스크롤된 상태에서 높이가 커지고 그 높이가 다시 스크롤을 만듦). 예약 높이도 고정값(CSS 계산상 약 111~137px)이 아니라 DOM 에서 잰다: 차트 아래 안내 요소 높이 + 카드 아래 패딩·여백 + max(body 아래 패딩, `.bottom` 높이)(탭 막대를 두 번 빼지 않게). 최소 360px — 최소값이 적용되는 낮은 창(높이 약 600px 미만)에서는 세로 스크롤을 허용한다. 차트 라이브러리는 `autoSize: true`(ResizeObserver 포함) 라 칸 높이만 바꾸면 다시 그린다.
- 차트 탭에서는 body 가 창 전체 폭이 되므로 머리말(모드·엔진 배지·「구버전으로」)도 창 폭으로 넓어진다(「구버전으로」 는 오른쪽 끝). 의도한 배치이며 실측 항목에 넣는다.

## 2. 바뀌지 않는 것 (지킬 것)
- 모바일 640px 이하 화면: CSS 는 `min-width: 641px` 절에만 넣는다. 412·360 실측으로 지금과 같음을 확인(가로 스크롤 0, 블록 3칸이 1열인 지금 모양 그대로).
- 봉 수 200, 업비트 요청 간격(30초·10초 문).
- 엔진·DB·매매 중지/재개 쓰기 경로.
- 원본 백테스터 구역(parity 시험 그대로 통과).

## 3. 영향 (축별)
| 축 | 영향 | 막는 것 |
|---|---|---|
| 매매·엔진 | 없음 | 엔진 파일 변경 0, 배포는 tradebot-v2 재시작만 |
| 업비트 한도 | 엔진·서버 IP 0 그대로. PC 브라우저가 차트 탭에서 투자자 IP 로 200봉·30초를 새로 부름 | 실패해도 화면 「갱신 실패」만 |
| v2 서버 | PC 가 홈 API(상태·자산·카드)를 7초마다 새로 부름(DB 읽기, 모바일과 같은 양) | 기존 읽기 경로·인덱스, RSS 관찰 |
| 캐시 | 정적 파일마다 304 확인 요청이 늘어남(작음) | ETag 304. 서버 tornado 버전(로컬 6.5.1 로 확인)은 배포 요청서에서 `venv/bin/python -c "import tornado;print(tornado.version)"` 로 확인 |
| 화면 경계 | 641px 이상 태블릿·휴대폰 가로도 PC 배치 | spec 개정에 명시 |
| 화면 버전 줄 | dashboard.py 버전 줄은 다음 tradebot 재시작 때 화면에 반영(이번 배포는 엔진 재시작 없음) | 보고에 「서버 파일 버전 / 화면 버전」 따로 기재 |

## 4. 작업 순서
1. F4·F9(시험 먼저) → F1~F3·F5·F6 → F8 → F7·F10 → F11·F12.
2. 로컬 확인
   - `node --test tests/v2/js/*.test.mjs` 전부 통과, `python3 -m unittest discover -s tests/v2 -t .` 전부 통과.
   - 브라우저 실측(`scripts/v2/dev_server.py`, 가짜 계정 — 실제 계정 값 넣지 않음): PC 1440×900·1280×800 에서 홈·로그·운용 가운데 480px, 차트 탭 창 전체 폭·높이(가로·세로 스크롤 0, 안내 2줄이 탭 막대 위에 보임), 차트 탭 머리말 배치, 탭 왕복·창 크기 변경 때 차트 다시 맞춤, 차트 실패 문구가 뜰 때(업비트 요청 막기) 다시 맞춤, **PC 폭 → 640px 이하로 창을 줄였을 때 모바일 높이(360/300px)로 돌아옴**, 1440×900 에서 홈 탭을 끝까지 내린 뒤 차트 탭으로 갔을 때와 창 높이 500→900 으로 키웠을 때 `document.documentElement.scrollHeight <= innerHeight`, 창 폭 640↔641px 경계에서 CSS 배치와 차트 높이가 함께 바뀜. 모바일 412×915·360×800 은 지금 화면과 같음(바꾸기 전 캡처와 비교). 백테스터 페이지 PC·모바일 그대로.
   - 응답 머리에 `Cache-Control: no-cache` 확인.
3. F13 버전 갱신 → `bash scripts/regression_gate.sh`(350/350 + v2 시험).
4. verifier(구현 보고) → Fable → 사용자에게 **커밋·push 승인** 요청(UI 변경 diff 브리핑 포함 — project-rules 1-A).
5. 배포 승인 요청서(짧게): 서버 `git pull --ff-only` → `systemctl restart tradebot-v2` → `check_v2_unit.sh`·RSS·API 401/403 확인 → 운영자 PC·휴대폰 강력 새로고침 확인 → 30분 관찰. **tradebot 재시작 없음.** 되돌리기: `git revert` → pull → tradebot-v2 재시작.
6. HANDOFF 갱신: 1025-17(정적 파일 Cache-Control) 을 이 작업으로 끝남 처리, 1026-09 진행 표.
7. 배포 뒤 A′ 문장 수정본 발송(1026-04): 「PC 에서는 기본 정보와 백테스터를 한 화면에서 볼 수 있습니다」 → 「PC 에서도 휴대폰과 같은 화면을 보며, 차트 탭에서는 차트를 화면 전체 크기로 볼 수 있습니다」.

## 5. 승인 단계 (각각 따로)
| 단계 | 승인 |
|---|---|
| 이 계획 | 사용자 「계획 승인」 |
| 커밋·push | 사용자(구현·verifier·Fable 뒤) |
| 배포 | 사용자(요청서 verifier·Fable 뒤) |
| A′ 발송 | 운영자 |

## 6. 멈춤 조건
- 모바일 412·360 실측에서 지금 화면과 다른 점이 하나라도 있으면 멈추고 보고.
- 회귀 게이트·v2 시험 실패, parity 시험 실패.
- 차트가 PC 에서 가로 스크롤을 만들거나 아래 탭 막대와 겹치면 고친 뒤 다시 실측.
