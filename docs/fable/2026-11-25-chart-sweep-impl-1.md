# Fable 질의 — 1125-01 구현 완료, 커밋 승인 요청 전

## 질문
1125-01 구현(차트 탭 백테스터 모양 · 스윕 설명 접기)을 사용자에게 커밋 승인 요청해도 되는가?

## 다음에 하려는 일
사용자 승인 뒤: 버전 다시 갱신(커밋 시각) → main 커밋·push(코드 + 시험 + 계획 문서 + HANDOFF 1125-01 행 + Fable 질의 2개, 문서는 이 질의에 묶음). 배포는 이번이 아님 — 1122-01 관찰(11/26 14:40) 뒤 v2 화면 서비스만 재시작으로 따로 승인·질의.

## 지금까지 확인한 사실
| # | 사실 | 확인/추정 | 근거 |
|---|---|---|---|
| 1 | backtester.js 안 바뀜, 엔진·서버 API·DB 안 바뀜(.py 는 dashboard.py 버전 1줄) | 확인(verifier) | git diff |
| 2 | 계획 A1~A6·B1~B2·㉠(가)·㉡ 대응 | 확인(verifier 대응표) | docs/plans/2026-11-25-chart-sweep/plan.md |
| 3 | verifier 지적 1(그리는 봉 수가 고른 값으로만 잘려 전략 목표가 크면 예전보다 줄어듦) → limit = spec.target(= max(고른 값, 전략 목표)) 로 고침 | 확인 | v2/static/app.js:570 |
| 4 | 고친 뒤 regression_gate exit 0(v2 unittest OK · JS OK · 회귀 1529/1529 · NETGUARD 0), node 247/247 | 확인 | scratchpad/gate2.txt |
| 5 | 화면: headless Chrome + 로컬 dev 서버 + 실제 업비트 시세로 차트 탭 PC 폭 사진(어두운 바탕·옆 글·단추), 백테스터 정적 사진(경고 한 줄 + 접힌 설명) 확인. 표식(400·420)은 dev 서버 시험 자료 | 확인 | scratchpad/shots_1125/chart_pc.png · bt_crop.png |
| 6 | 390 폭 사진은 headless 창 최소 폭 때문에 판정 불가(홈 탭도 같이 잘림) → 휴대폰은 배포 뒤 Aside 실측 | 추정 | scratchpad/shots_1125/home_mobile.png |
| 7 | 전체화면은 아래 탭 줄을 덮음 → 나가는 길은 닫기 ✕·Esc. 투자자 안내에 적을 예정 | 확인(verifier) | style.css:82 · :114 |
| 8 | 사용자 관점 변화(UI 1-A ②): 「최근 200봉」 고정 글 → 실제 봉 수, 스윕 설명 접힘(경고 한 줄은 보임), 차트 바탕 어두움·선 색 밝아짐 | 확인 | git diff |
| 9 | 휴대폰 길게 누르기로 봉 정보 상자가 나오는지 | 추정 | 실측 전 |

## 근거 경로
- verifier 결과: 이 세션 보고(주장 8개 중 7 확인, 화면 1 일부)
- 바뀐 파일: v2/static/chart.js · app.js · index.html · style.css · bt_ui.js · backtester.html · pages/dashboard.py · tests/v2/js/chart.test.mjs · bt_ui.test.mjs · alpine_wiring.test.mjs · tests/v2/test_static_lint.py
- 사진: /private/tmp/claude-501/-Users-gonnim-Project-MVP-Source-upbit-tradebot-mvp/f030db45-bfaa-44d4-9fd0-ab15a99f24e0/scratchpad/shots_1125/

## 답
판정: 진행 (Fable, 11/25 19:01). 권고 5: ① main 바로 push 대신 가지(feat/1125-01) 고려 — 정적 파일은 pull 시점에 화면이 바뀜 ② 「휴대폰은 길게 눌러서」 글은 추정임을 밝힘 ③ 사진으로 못 본 것 4개(전체화면·봉 정보 글·1000/2000봉·390 폭) 따로 적기 ④ HANDOFF 행 상태·버전 구→신 ⑤ 「400봉」 단추와 「최근 800봉」 글이 달라 보일 수 있음을 투자자 안내에.
반영: ①은 사용자 커밋 승인 요청에 가지 권고로 · ②③⑤ 보고·투자자 안내에 · ④ HANDOFF 행 고침, 버전은 커밋 때 갱신.
