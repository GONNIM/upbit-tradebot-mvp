# Fable 질의 — 투자자 추가 요청(차트 탭 백테스터 모양 · 스윕 설명 접기) 구현 계획 2판, 사용자 보고 전

## 질문
계획 2판이 사실과 맞고, 실제로 만들 수 있으며, 빠진 위험이 없어 사용자에게 계획 승인을 올려도 되는가?

## 다음에 하려는 일
계획 2판을 사용자에게 보고(정할 것 ㉠ 차트 색 · ㉡ 월·주 설명 접기 여부). 이번 단계에는 파일 쓰기·커밋·배포 없음. 승인을 받으면 docs/plans/ 에 계획 문서로 기록한 뒤 구현.

## 지금까지 확인한 사실
| # | 사실 | 확인/추정 | 근거 |
|---|---|---|---|
| 1 | 투자자 11/25 요청 원문과 11/23 원 질문, 우리 답(연락 기록 #21)이 「실제 매수·매도만 표시 + 백테스터 기능 더하기」 | 확인 | docs/new-version/claim/ver9/investor-answer-20261123.md:16 · investor-answer-analysis-20261123.md:65~83 |
| 2 | 계획 F1~F7 | 확인(verifier, 11/25) | 계획 파일 |
| 3 | verifier 지적 8건을 2판에 반영(시험 3곳 · 버전 갱신 · app.js 공용 · p.note · 휴대폰 · 업비트 한도 · 캐시 · 글자 수) | 확인 | 1판·2판 대조 |
| 4 | LW 4.2.0 표식 글은 표식 위·아래 한 줄이라 백테스터와 똑같지 않음, 휴대폰 십자선은 길게 누름 | 추정 | vendor 코드 읽기만, 기기 실측 전 |
| 5 | 업비트 시세 요청 한도가 사용자 브라우저 IP 단위 | 추정 | 공식 문서 미확인 |
| 6 | 1122-01 24시간 관찰이 11/26 14:40까지 — 배포는 그 뒤 | 확인 | docs/specs/v2-dashboard/HANDOFF.md |

## 근거 경로
- 계획 2판: /private/tmp/claude-501/-Users-gonnim-Project-MVP-Source-upbit-tradebot-mvp/f030db45-bfaa-44d4-9fd0-ab15a99f24e0/scratchpad/plan_chart_sweep_v2.md
- 1판: 같은 폴더 plan_chart_sweep_draft.md
- 코드: v2/static/chart.js · app.js · index.html · style.css · backtester.html · backtester.js · bt_ui.js · tests/v2/

## 답
판정: 수정 후 진행 (Fable, 11/25). 막음 1: ㉠ 색 범위를 실제 차이대로(캔들 같음·선 다름). 권고 6: B2 두 번 감싸기 막기 · A3 뒤로 가기 대신 닫기 단추·Esc·탭 이동 · alpine_wiring.test.mjs:123 inline 높이 금지 · 업비트 한도 확인됨(IP 단위, 브라우저 10초당 1회) · A4 봉 수 기억·줄일 때 동작 · A1 다시 그리기 좁힘.
반영: 계획 2판 끝 「Fable 1회 반영」 절. 막음은 계획 글 고치기뿐이라 다시 묻지 않고 사용자에게 올림.
