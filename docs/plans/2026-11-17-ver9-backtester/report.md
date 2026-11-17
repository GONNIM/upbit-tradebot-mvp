# 1111-01 투자자 Ver9 반영 — 구현 보고 (2026-11-17 · 커밋 전)

## 1. 정해진 것
- 투자자 답(11/17): ㉠ ① 선물 백테스트(롱+숏) 화면 계산만 · ㉡ ① 기본값 Ver9(분할 1 · 익절 3 · 손절 3).
- 사용자 승인(11/17): 「1111-01 승인 단, Ver2 화면 및 소스는 백업해 두시오」. 계획 7절 질문 6개는 답이 없어 권고대로 가정(구현 보고 때 다시 알림).
- 계획: plan.md(같은 폴더). verifier(계획) 「고친 뒤 승인 권함」 → 반영. Fable 계획 질의 docs/fable/2026-11-17-ver9-plan-1.md 1회째 수정 후 진행 → 2회째 진행.

## 2. 백업
- docs/new-version/ver2-backup-20261117/ — 57e3d56 기준 v2/static backtester.html · backtester.js · bt_ui.js · save.js + ver2_patches.json, sha256 README 에 기록. 원본과 5쌍 sha 같음 확인. 투자자 Ver2 원본(docs/new-version/ver2/)은 그대로.

## 3. 바꾼 것
- 단계 1: tests/v2/js/fixtures/ver2_patches.json(source Ver9, script_lines [196,1902], 9번 find 를 Ver9 readCfg 끝 `useFunding … };` 로) → `node scripts/build_backtester_js.mjs` 로 v2/static/backtester.js 다시 만듦(1728줄 · 98,443바이트, 손으로 고치지 않음).
- 단계 2 v2/static/backtester.html: 기본값 1/3/3 · 스윕 범위 Ver9(SL 1~5 · 분할 1~1 · 기울기 끝 1) · 둔화 3칸 · 선물 단추 btFutBtn · 안내 btFutNote · 「선물 설정」 접힘 btFut(futMode · cUseSl · useFunding + USDT 안내) · 상위 10 · 최대 20,000 · chartBox · fsBtn · 전체 봉 보기 · 전체화면 CSS · 가로 스크롤 없앰 · btBriefMode · sweepBriefMode.
- 단계 3 v2/static/bt_ui.js: fetchKlines 감싸기 market(업비트+선물 오류) · runFutures 감싸기(업비트면 요청 없이 막음 · 겹침 막기 · await 뒤 카드) · runSweep await 고침 · 카드 기울기 · 둔화 칸 · 출처 바꿀 때 futCache · 직전 결과 변수(거래 · 주 · 월 · 스윕 보조 표 포함) · 화면 결과 · 차트 캔버스 · chartInfo 비우고 chartHint 처음 문구 · 업비트면 선물 단추 막기 · **실행 · 선물 · 스윕 중에는 출처 바꾸기 막기(busyCount, 안내 「실행 중에는 출처를 바꿀 수 없습니다. 끝난 뒤 바꿔 주세요」)** · **스윕 중에는 실행 · 선물을 시작하지 않고, 실행 · 선물 중에는 스윕을 시작하지 않음**(현물 · 선물 결과가 한 표에 섞이는 틈 — Fable 구현 1회째 권고 3).
- 바꾸지 않은 것: core/ · engine/ · v2/api_write.py · v2/handlers.py · v2/params_schema.py · v2/static/save.js · pages/dashboard.py(버전은 커밋 때) · docs/new-version/ver2 · 백업 폴더 · ver9 폴더.

## 4. 시험
- 고친 기존 시험: parity(sha · 칸 47/50 · 주석) · bt_ui(칸 50 · 스윕 await) · save(기본 익절 3) · 가짜 window/document addEventListener 5곳(harness · bt_cache_agg · trailing · ver2_diffs · pullback_reference 생성기) · test_static_lint(fapi.binance.com 허용) · 기준값 45개 + cfgs.json.
- 새 시험 13개: parity_futures.test.mjs 5(N1 방식 A·B·C × cUseSl × useFunding 12가지 원문 대조 · 펀딩비 영향 · N2 선물 스윕 5 CSV · N3 현물 스윕 5 CSV · N6 바깥 연결 0) · bt_ui_ver9.test.mjs 8(N7 기본값 · N4 업비트 선물 막기 · N8 카드 await · N5 출처 비우기 · N10 선물 뒤 저장 창 · N9 카드 줄 구분 · N11 실행 중 출처 바꾸기 막기 + chartInfo · N12 스윕 · 실행 겹침 막기). 고정 자료 fut_klines_a.json · fut_funding_a.json 은 합성.
- 결과(11/17 PO 실행, evidence/): `node --test tests/v2/js/*.test.mjs` 219/219 · `bash scripts/regression_gate.sh` 1472/1472 · NETGUARD 0 · `python3 -m unittest tests.v2.test_static_lint` 13 OK · 기준값 diff 는 script_sha256 줄만(그 밖 +/− 0줄).
- 한계: N1~N3 은 「차이 10곳이 선물로 새지 않음」만 확인. 선물 규칙 자체의 옳음은 확인하지 않음(투자자 원문).

## 5. 검증
- verifier 1회째(구현): 「수정 후 승인 권함」, 주장 19개 확인 · 반박 0. 지적: 실행 중 · 스윕 중 출처 전환 틈(재현) · 1-A 바뀌는 것 3가지 누락 · 실측 남음 · 낡은 주석 · 버전 갱신 남음.
- 처리: busyCount 막기 + N11, chartInfo 되돌림, 낡은 주석.
- verifier 2회째: 「승인할 수 있음」, 주장 확인 · 반박 0. 고치기 전 사본(busyCount 줄 지움)에서 N11 실패 확인, 감싸기 하나씩 뺀 사본 3개도 실패. 1회째 probe 재실행으로 틈 닫힘. 권고 3(chartInfo 시험 · 주석 2줄 · busyCount++ 를 try 바로 앞으로) → 모두 반영, 218/218.
- Fable 구현 1회째 뒤 고친 것(스윕 · 실행 겹침 막기 + 안내 문구 · N12)은 verifier 가 다시 보지 않았다. Fable 2회째가 코드 · N12 를 직접 확인했다(진행).
- Fable 2회째 뒤 권고 반영(겹침 막을 때 안내 문구 2개)에서 N12 가 약했음을 찾음: 호출 사이 await 때문에 가짜 타이머 환경에서 스윕이 먼저 끝나 막기를 실제로 시험하지 않았다(Fable 2회째가 확인한 N12 도 이 약한 판). 같은 순간에 부르도록 고치고 lastResults 그대로 단언을 더함. 막기 줄을 지운 사본에서 N12 가 실패함을 확인(scratchpad n12chk). 219/219 · 게이트 1472/1472 · NETGUARD 0.

## 6. 브라우저 실측 (11/17, 정적 서버 127.0.0.1 + playwright headless Chromium, 390x844 터치 · 1280x900)
- v2 서버는 띄우지 않음(실계좌 키 · 엔진에 닿을 수 있어). chrome-devtools MCP 는 다른 세션이 프로필을 쥐어 못 씀.
- 보임: 기본값 · 스윕 범위(3,465조합) · −/+ 단추(휴대폰 36x38, 터치로 3→3.1→2.9) · 선물 설정 접힘과 USDT 안내 · 바이낸스 현물 실행 카드 · 차트 · 확대 · 끌기 · 전체 봉 · 전체화면(fixed · z-index 9999, 정적 페이지 머리 막대 · 아래 메뉴 덮음) · 바이낸스 선물 실행(fapi klines · fundingRate 200, 451 없음, 「선물(롱+숏) · 바이낸스 USDT …」) · 선물 뒤 업비트로 바꾸면 카드 · 요약 · 차트 비워짐과 선물 단추 막힘 · 저장 창 「시험한 데이터: 업비트 …」.
- 스윕 시간(3분봉 30일 14,400봉, 3,465조합): PC 1.5초 · 휴대폰 모의 CPU 4배 4.2초(기준 60초 안).
- 지금 배포본(백업 파일)은 스윕 뒤에도 요약 카드가 비어 있음 — 이번에 고쳐짐.
- 콘솔: 코드 오류 0. 정적 서버라 /v2/api/* 404 · style.css 경로 실패(예상).
- 확인 못 함: 실제 앱 머리 막대 · 아래 메뉴, 업비트 조회 · 저장 동작(서버 API 없음), style.css 적용 모양, 실제 휴대폰 · 핀치. → 배포 뒤 사용자 화면 확인.
- 첫 실측은 busyCount 고치기 전 파일. **고친 파일로 한 길 재실측(11/17, recheck.js)**: 휴대폰 · PC 모두 선물 실행 중 업비트 누름 → 출처 binance 그대로 · 「실행 중에는 출처를 바꿀 수 없습니다…」 → 끝난 뒤 카드 「선물(롱+숏) · 바이낸스 USDT …」 → 업비트로 바꿈 → 선물 단추 막힘 · 안내 · 카드 「결과 없음」 · 차트 정보 줄 처음 문구로 돌아옴 · 코드 오류 0(evidence/recheck_*.png · 값 비교 결과 evidence/recheck-result.txt — 스크린샷은 화면 위쪽만이라 차트 정보 줄은 값 비교로 확인). 배포 뒤 사용자 화면 확인 목록에도 넣는다.

## 7. 사용자에게 보고할 바뀌는 것 (1-A 2층)
- 없어지는 것: 차트 가로 스크롤 · 스윕 「상위 20」(→ 10) · 출처 바꿀 때 직전 결과가 남던 동작(현물 포함) · 실행 중 출처 바꾸기.
- 바뀌는 것: 스윕이 도는 동안 실행 · 선물 단추는 눌러도 시작하지 않고 「스윕이 끝난 뒤 실행해 주세요」, 실행 중 스윕은 「실행이 끝난 뒤 스윕해 주세요」(전에는 겹쳐 돌 수 있었음) · 기본값 1/3/3 · 스윕 범위 · 차트 확대 단계 1.2 → 1.25 · 백테스트 직후 차트가 최근 1,500봉이 아니라 전체 봉 · 차트 안내 문구 · 현물 실행 중 선물 단추는 눌러도 아무 일 없음 · 스윕 카드에 기울기 · 둔화 칸.
- 접힘에 들어가는 것: 선물 3칸(「선물 설정」). 선물 단추는 실행 줄에 드러남.

## 8. 남은 것 (순서)
커밋 · push 승인(pages/dashboard.py 버전 v1.2026.11.12.1728 → v1.2026.11.17.HHMM · 스테이징은 파일 이름으로: evidence/*.txt 7개는 .gitignore:38 `*.txt` 에 걸리므로 `git add -f`, 스크린샷 *.png 는 넣지 않음(zip 에만 · 이 맥에만 있음) · 커밋 전 `git status` 로 evidence/ 아래 png 0개 · txt 7개 확인 · `git diff --staged` 비밀값 검사 · 저장소는 공개 — 투자자 요청 PDF · HTML(거래 금액) · Ver9 원문이 함께 올라감) → 투자자 안내(배포 전, PDF 약속 · 메신저 글 · 분할 1 저장 확인 한 줄) → 배포 승인 → 표준 정지선(서버 HEAD · 기동 시각 · tradebot-v2 unit · nginx add_header/CSP, 사용자 `!`) → git pull + tradebot-v2 만 재시작 → 1시간 관찰 → 보고. 되돌리기: git revert → pull → tradebot-v2 재시작 → 엔진 기동 시각 그대로 확인.

## 9. 근거 파일 (evidence/)
diff-stat.txt · git-status.txt · node-test.txt · regression-gate.txt · static-lint.txt · commands.txt(커밋) · 스크린샷 new_pc_* · new_mobile_* · old_pc_5_sweep_card.png · recheck_*.png(zip 에만)
