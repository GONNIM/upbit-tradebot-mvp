# 구현 보고 — PC 차트 확대 (1026-11, 계획 docs/specs/v2-dashboard/plan-pc-chart-20261026.md, 승인 1026-10)

## 바뀐 파일 (추적 15 + 새 파일 3)
- 화면: v2/static/index.html(넘김 삭제·body :class), app.js(가드 삭제·fitChart·resize·$watch 5개·go 뒤 nextTick+rAF), basic.js(가드 삭제), chart.js(fitChartHeight), style.css(641px 절), basic.css(641px 절: 홈 블록 1열·버튼 휴대폰과 같게)
- 서버: v2/handlers.py StaticHandler Cache-Control no-cache + get_cache_time 0
- 시험: tests/v2/js/basic.test.mjs(넘김 시험 3개 → 2개로 교체), chart.test.mjs(fitChartHeight), alpine_wiring.test.mjs(창 API 대체물·$watch/$nextTick 대체·좁은 창 inline 높이 없음 단언), tests/v2/test_server.py(Cache-Control·?v=1·304)
- 문서: spec.md 19·119·242, plan-pc-basic-20261025.md:114, HANDOFF.md, 새 plan-pc-chart-20261026.md, docs/fable/2026-10-26-pc-chart-proposal-1.md·-pc-chart-plan-1.md
- 버전: pages/dashboard.py:495 v1.2026.10.26.0122 → v1.2026.10.26.1209
- 계획과 다른 점(PO 판단): basic.css 641px 절에 홈 블록 버튼도 휴대폰 모양(flex 1·16px)으로 — 「PC 를 모바일과 동일하게」 맞춤. $watch 대상에 netError·authError·status 추가(머리 문구가 차트 위치를 바꾸므로). $watch 콜백도 nextTick 뒤 한 프레임 기다림(실측에서 nextTick 만으로는 x-show 반영 전이라 높이가 안 바뀜 — 고침).

## 시험
- node --test tests/v2/js/*.test.mjs: pass 66 fail 0
- python3 -m unittest discover -s tests/v2: Ran 260 OK
- scripts/regression_gate.sh exit 0, 350/350

## 브라우저 실측 (dev_server 가짜 계정 devuser, Chrome DevTools 에뮬레이션, 강력 새로고침 뒤)
| 항목 | 결과 |
|---|---|
| 모바일 412×915 4탭 | 바꾸기 전 수치와 같음(body 412, nav [0,869,412,46], 차트 370×300, 홈 카드 6개 위치, scrollW 412) |
| 모바일 360×800 4탭 | 바꾸기 전과 같음(차트 318×300, scrollW 360) |
| PC 1440×900 홈·로그·운용 | body [480,0,480], nav 480 가운데, 자산 칸 1열(438px), scrollW 1440 |
| PC 1440×900 차트 | body 1440, nav 1440, 차트 1398×662, 안내 아래 끝 807 < 탭 막대 854, scrollH 900 = 창 |
| 홈 끝까지 내린 뒤(scrollY 873) 차트 | 차트 662, scrollH 900 |
| PC 1280×800 차트 | 1238×562, scrollH 800, 안내 707 < 탭 754 |
| 641×800 | 차트 inline 562px(PC 배치) / 640×800: inline 지움, 360px(모바일 CSS) |
| 1440×500 → 900 | 500 에서 최소 360(스크롤 허용 598) → 900 에서 662·scrollH 900 |
| 차트 실패 문구 표시/해제 | 662 → 637 → 662, scrollH 900 유지 |
| 백테스터 PC | 블록 보임, 3칸, body max 1250, scrollW 1440 / 모바일 412: 블록 숨김, scrollW 412 |
| 정적 머리 | style.css·?v=1·backtester.html Cache-Control no-cache, If-None-Match → 304 + no-cache |
- 관찰: 실측 중 브라우저에 남아 있던 옛 style.css(Cache-Control 없던 때 받은 것)가 한 번 쓰였다. 이번 배포 직후 운영자·투자자 브라우저도 같을 수 있어 강력 새로고침 안내가 필요하다(다음 배포부터는 no-cache 로 해소).

## UI 변경 브리핑 (project-rules 1-A 2항 — 사라지거나 옮겨지거나 바뀐 것)
1. PC 에서 `/v2/` 로 들어오면 더 이상 백테스터 한 페이지로 넘어가지 않는다. 백테스터는 아래 탭 막대 「백테스터」 링크로 옮겨졌다(휴대폰과 같음). 백테스터 페이지에서 홈으로 돌아오는 단추는 없다(뒤로가기).
2. PC 홈 맨 위 기본 블록: 자산 3칸이 세로 1열이 되고, 「매매 중지」·「로그아웃」 단추가 휴대폰처럼 넓어졌다. 단추는 그대로 맨 위에 있다(접힘 없음).
3. PC 차트 탭에서는 머리말도 창 전체 폭이 되어 「구버전으로」가 오른쪽 끝으로 간다.
- 1-B 화이트리스트(감사로그·설정 이동·헬스 배지·강제 매수/매도) 해당 항목 접힘·삭제 0. 접힘(expander) 변경 0. 모바일 화면 변경 0.

## verifier (구현) 반영
- 결론 「코드 수정 없음, UI 브리핑 보태면 커밋 승인 요청 가능」. 지적 2 HANDOFF 1025-17 끝남 처리, 지적 3 넓은 창 fitChart·$watch 등록 자동 시험을 alpine_wiring 에 추가(659px 계산·탭 이탈·좁은 창 지움·5개 키). node 66/66, 게이트 exit 0·350/350 다시 통과.
- 지적 4(status 7초마다 fitChart 한 번 — 무해)·5(640~641 소수 폭, 기존 방식과 같음)·6(리스너 중복 없음)은 기록만.

## 영향
- 엔진 파일 0, 배포는 tradebot-v2 재시작만. dashboard.py 버전 줄은 다음 tradebot 재시작 때 화면 반영.
