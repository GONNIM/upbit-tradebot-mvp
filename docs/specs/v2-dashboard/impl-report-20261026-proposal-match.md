# 구현 보고 — 신버전 1차 화면을 승인 요청서 v2 그림과 같게 (계획 plan-proposal-match-20261026)

- 작성: 2026-10-27 (KST) · Task 9 (전체 검증·실측·보고·문서)
- 계획서: `docs/specs/v2-dashboard/plan-proposal-match-20261026.md` (사용자 「1026-24 승인」)
- 결정 근거: 1026-19(1 가·2 가·3 가·4 가·5 나), 1026-23(1 가·2 가). 기준 그림: `investor-approval-20261021-v2.pdf` 1·2·5절
- 상태: **구현·시험 완료, 커밋 없음**(작업 트리에만 있음). 커밋은 사용자 승인 뒤 한 번, `pages/dashboard.py` 버전 갱신 포함(이 보고 시점에는 `pages/dashboard.py` 를 바꾸지 않았다 — 「버전: 구 → 신」은 커밋 때 적는다).
- 서버 접속·배포 없음. 외부 호출은 Step 3 의 업비트 공개 캔들 실측(로컬 맥 IP, 로컬 개발 서버 경유)과 차트 탭의 브라우저 업비트 조회뿐.

## 0. 한눈에

| 항목 | 결과 |
|---|---|
| 자동 시험 (최종 검수·verifier 수정 뒤) | JS 115/115 통과 · Python v2 321 OK · 입장 버튼 4 OK · 회귀 게이트 350/350 (모두 0 실패). Task 9 때는 112·316 |
| 브라우저 실측 | 412×915 · 360×800 · 1440×900 에서 탭 5개 + 확인 창 2종: 가로 넘침 0, 콘솔 오류·경고 0, 4xx/5xx 0. 1440 에서 body·아래 메뉴 left 480 / width 480(가운데). main 은 index 화면(홈·차트·로그·운용) left 488 / width 464(body 안 좌우 8px 여백), 백테스터·확인 창 left 480 / width 480 (verifier 수정: 실측값대로 고침) |
| 업비트 1분·30일·KRW-BTC (빈 보관) | 최종 검수 수정 뒤 재측정: **단추 → 결과 요약 54.2초**(데이터 54.1초 · 계산 0.13초 · 마지막 전송 0.27초). 목표(데이터 ≤55초, 전체 ≤60초) 안. Task 9 때 54.0초. *(Task 4-0b 뒤 57.2~93.7초 — 14절)* |
| 같은 조건 다시 실행 | 0.30초, 응답 200 `requests: 0`, 42,888봉 (재측정도 같음) |
| 업비트 429 | 서버 0건(세 번의 실측 모두), 차트 창 2개의 브라우저 업비트 응답 5건 모두 200 |
| 최대 메모리 | 최종 검수 수정(A) 뒤 재측정: 프로세스 수명 전체 `ru_maxrss` **64,274,432 바이트 = 61.3 MiB** — 150M 의 절반(75 MiB) **아래**. 수집 중(ps RSS) 최대 47.5 MiB, 응답 직후 55.7 MiB, 다시 실행 직후 59.3 MiB. 수정 전(Task 9) 79.0 MiB(82,886,656 바이트). 6절 (f) |
| 보호 경로 | `v2/static/backtester.js` 바이트 불변(sha256 `4418dad6…2576`, parity 시험 통과), `core/ engine/ services/ config.py scripts/tradebot_boot.py pages/dashboard.py` diff 0 |

## 1. Step 1 — 자동 시험 (출력 원문: 번들 `evidence/*.txt`)

```
node --test tests/v2/js/*.test.mjs                 → # tests 112 / # pass 112 / # fail 0 (exit 0)
python3 -m unittest discover -s tests/v2 -t .      → Ran 316 tests — OK (exit 0)
python3 -m unittest -v tests.test_v2_entry_button  → Ran 4 tests — OK (exit 0)
bash scripts/regression_gate.sh                    → ✅ 회귀 테스트 350/350 통과 — 배포 진행 가능 (exit 0)
```

Step 5 문서 수정 뒤 다시 돌린 결과도 같다(위 숫자는 수정 뒤 마지막 실행). `tests.v2.test_deploy_files`(runbook 절 이름 시험) OK.

최종 검수 수정(12절)·verifier 수정 뒤 다시 돌린 결과(출력 원문: 번들 `evidence/final-*.txt`):

```
node --test tests/v2/js/*.test.mjs                 → # tests 115 / # pass 115 / # fail 0 (exit 0)
python3 -m unittest discover -s tests/v2 -t .      → Ran 321 tests — OK (exit 0)
python3 -m unittest -v tests.test_v2_entry_button  → Ran 4 tests — OK (exit 0)
bash scripts/regression_gate.sh                    → ✅ 회귀 테스트 350/350 통과 — 배포 진행 가능 (exit 0)
git diff --stat -- v2/static/backtester.js core engine services config.py scripts/tradebot_boot.py pages → (빈 출력)
```

## 2. Step 2 — 브라우저 실측

방법: `scripts/v2/dev_server.py`(임시 폴더·가짜 계정 `devuser`·TEST·엔진 종목 KRW-ZRO·`minute3`)를 띄우고 헤드리스 Chrome 155 를 CDP 로 조종했다. Chrome DevTools MCP 는 그 전용 프로필을 다른 세션의 Chrome(10/26 20:14 시작)이 잡고 있어(「browser is already running」) 쓰지 못했고, 그 Chrome 을 끄면 다른 세션을 깰 수 있어 건드리지 않았다. 대신 별도 프로필로 같은 Chrome 을 띄워 `Emulation.setDeviceMetricsOverride`(모바일은 mobile=true)·`Page.captureScreenshot`·`Runtime.evaluate` 로 쟀다(스크립트: 번들 `evidence/scripts/`).

가로 넘침 판정: `document.documentElement.scrollWidth > clientWidth` + 화면 오른쪽 끝을 넘는 요소(가로 스크롤 부모 안 제외) 목록.

| 화면 | 412×915 | 360×800 | 1440×900 (body left/width) | 콘솔 오류·경고 | 4xx·5xx |
|---|---|---|---|---|---|
| 홈 | 넘침 0 | 넘침 0 | 480 / 480 | 0 | 0 |
| 차트 | 넘침 0 | 넘침 0 | 480 / 480 | 0 | 0 |
| 로그 | 넘침 0 | 넘침 0 | 480 / 480 | 0 | 0 |
| 운용 | 넘침 0 | 넘침 0 | 480 / 480 | 0 | 0 |
| 백테스터 | 넘침 0 | 넘침 0 | 480 / 480 | 0 | 0 |
| 확인 창(업비트) | 넘침 0 | — | 480 / 480 | 0 | — |
| 확인 창(바이낸스) | 넘침 0 | — | 480 / 480 | 0 | — |

백테스터 첫 화면 기본값(세 폭 모두): 출처 업비트 · 종목 KRW-ZRO(엔진 종목) · 봉 3분(엔진 `minute3`) · 30일.

### 최종 화면 재측정 (verifier 수정 2026-10-27, 최종 검수 수정 C·F 와 verifier 수정 B·C 반영 뒤)

같은 방법(새 개발 서버, 별도 프로필 헤드리스 Chrome + CDP, 스크립트 `evidence/scripts/step2final.py`)으로 412×915·360×800 의 홈과 로그 탭을 다시 쟀다. 차트 탭은 브라우저가 업비트를 부르므로 열지 않았다(브라우저 업비트 호출 0). 원자료 `evidence/final-step2-measure.json`, 로그 `evidence/dev-server-final2.log`(토큰 가림).

| 화면 | 가로 넘침 | 넘는 요소 | main left/width | 콘솔 오류·경고 | 4xx·5xx | 머리 막대·기록 줄 |
|---|---|---|---|---|---|---|
| 412 홈 | 0 | 없음 | 8 / 396 | 0 | 0 | 「Dev User님 · 구버전으로 · 로그아웃」, 「기록 시각 04:45:33 · 현재가 410.0원 04:45 엔진 기록」, 평균 매수가 「400.0원」 |
| 412 로그 | 0 | 없음 | 8 / 396 | 0 | 0 | 제목 「로그」, 오른쪽 「TEST」 |
| 360 홈 | 0 | 없음 | 8 / 344 | 0 | 0 | 412 와 같음(머리 막대 한 줄 안에 들어감) |
| 360 로그 | 0 | 없음 | 8 / 344 | 0 | 0 | 412 와 같음 |

캡처 8개 추가: `shots/{412,360}-{home,logs}-final.png` 와 각 `-final-full.png`.

### 캡처 목록 (`.superpowers/sdd/plan-proposal-match-20261026/shots/`, 48개)

- 화면: `{412,360,1440}-{home,chart,logs,ops,backtester}.png` 와 같은 이름의 `-full.png`(전체 길이) — 30개
- 확인 창: `412-dialog-upbit.png`, `412-dialog-binance.png`, `1440-dialog-upbit.png`, `1440-dialog-binance.png`
- 업비트 실측 결과: `step3-run1.png`, `step3-run2.png`
- 승인 요청서 렌더(`pdftoppm -r 80`): `approval-01.png` … `approval-12.png` (그림 1 = 2쪽, 2-가·2-나 = 3쪽, 2-다·2-라 = 4쪽, 2-마 = 5쪽, 5-가·5-나 = 8쪽)

## 3. 그림 대조표 (그림 요소 → 412px 화면, 같음/다름)

그림 속 숫자·이름·종목·봉 단위는 승인 요청서 0절이 밝힌 「예시 값」이라 실제 값(KRW-ZRO·3분·TEST·Dev User)이 보이는 것은 「같음」으로 본다.

### 그림 2-가 홈 (`approval-03.png` ↔ `412-home-full.png`)

| 그림 요소 | 화면 | 판정 |
|---|---|---|
| 머리 막대 짙은 남색 「신버전 대시보드」 / 「투자자님 · 구버전으로」 | 「신버전 대시보드」 / 「Dev User님 구버전으로 로그아웃」 | 다름(작음): 「·」 구분자가 없고 로그아웃이 더 있음(로그아웃은 결정 1026-23 1 가) |
| 배지 줄 LIVE(빨강)·엔진 동작 중(초록)·전략(파랑)·일시정지 아님(회색) | TEST(빨강)·엔진 동작 중(초록)·전략: EMA (기존)(파랑)·일시정지 아님(회색) | 같음(1차에는 새 전략이 없어 「EMA (기존)」) |
| (그림에 없음) | 배지 줄 아래 「⏸️ 매매 중지」 큰 회색 단추 | 다름 — 결정 1026-23 1 가로 남김 |
| 자산: 평가 합계(굵게)·원화/코인·평가손익(빨강) | 같은 3줄 + 「원화 잠김 / 코인 잠김」·「기록 시각 · 현재가 엔진 기록」 2줄 | 같음 + 추가 2줄(결정 1026-23 1 가) |
| 보유 · 종목: 분할 회차 2/5회·평균 매수가·익절 가격(빨강)·손절 가격(파랑) | 분할 회차 「—」, 나머지 같음 | 같음(1차에는 분할 회차 없음 → 「—」) |
| 최신 신호 · 시각 봉 + 문장 | 「최신 신호 · 03:44 봉」 + 「보유 유지 — 익절·손절 가격 안」 | 같음 |
| 최근 거래 표(시각·구분·사유·금액, 매수 빨강·매도 파랑) | 같은 4열, 매도 파랑·매수 빨강 | 같음(구분은 「매수 2회」 대신 「매수」 — 1차 회차 없음) |
| 아래 메뉴 홈·차트·백테스터·로그·운용, 선택 탭 파란 밑줄 | 같음 | 같음 |

### 그림 2-나 차트 (`approval-03.png` ↔ `412-chart.png`)

| 그림 요소 | 화면 | 판정 |
|---|---|---|
| 머리 막대 「차트 · KRW-XXX · 1분」 / LIVE | 「차트 · KRW-ZRO · **minute3**」 / TEST | **다름**: 봉 단위가 원문(`minute3`)으로 보임 — 단추 줄은 「3분」. Task 1 이월 minor 「tabTitle 봉 원문」이 실측으로 확인됨(10절 걱정거리 2) |
| 단추 줄 「1분 · 최근 200봉(선택) · 확대 + · 축소 -」 | 「3분 · 최근 200봉(선택) · 확대 + · 축소 −」 | 같음 |
| 캔들 상승 빨강·하락 파랑, 60선 주황·200선 보라, 매수▲·매도▼ | 같음(200선까지 그려짐, 매수·매도 표시 있음) | 같음 |
| 범례 「— 60선 · — 200선 · ▲ 매수 · ▼ 매도」 | 같음 | 같음 |
| 「이 화면에서 보는 것」 카드 문장 | 같은 문장 | 같음 |

### 그림 2-다 백테스터 (`approval-04.png` ↔ `412-backtester.png`)

| 그림 요소 | 화면 | 판정 |
|---|---|---|
| 머리 막대 「백테스터」 / LIVE | 「백테스터」 / TEST | 같음 |
| 데이터 출처 2칸(업비트 선택 = 파랑 채움) | 2칸, 선택 칸은 연파랑 바탕·파란 글자 | 다름(작음): 선택 표시 색 농도 |
| 종목 / 봉 단위·기간 / 60선·200선 / 분할 최대 / 익절 TP / 손절 SL — 2열 6칸 | 같은 6칸(봉 단위는 선택 칸 + 기간 숫자 칸, 60선·200선은 숫자 칸 2개) | 같음(입력 칸이 둘로 나뉜 것은 원본 입력 id 보존) |
| 「… 그 밖의 입력 18개(접힘)」 | 「… 그 밖의 입력 11개(접힘)」 | 같음(개수는 예시 값 — 실제 11개) |
| 빨간 「데이터 가져오기 + 백테스트」 | 같음 | 같음 |
| (그림에 없음) | 단추 아래 검은 진행 줄 「준비되었습니다.」 | 다름 — 원본 백테스터의 `#status` 를 진행 표시로 그대로 씀 |
| 결과 요약(총 수익률·거래 수/승률·최대 낙폭) | 실행 전 「결과 없음」, 실행 뒤 같은 3줄(`step3-run1.png`) | 같음 |
| 여러 설정 비교(파라미터 스윕) 표 | 같은 카드 + 「스윕 범위(접힘)」·빨간 「스윕 실행」 단추 | 다름(추가): 스윕을 돌릴 단추가 필요해 둠. 실행 뒤 상위 5개 표 |
| (그림에 없음) | 「자세한 결과」·「전략 로직 설명」 접힘 | 다름 — 원본 결과 표·차트·설명 보존(사라지는 것 표 참조) |
| CSV 받기(흰색)·설정 저장(파랑) | 같음 | 같음 |

### 그림 2-라 로그 (`approval-04.png` ↔ `412-logs.png`)

| 그림 요소 | 화면 | 판정 |
|---|---|---|
| 토글 감사 로그(선택)·엔진·오류 | 같음 | 같음 |
| 시각·내용 표, 매수 체결 빨강·매도 체결 파랑·대기 회색 | 같음(「매수 대기 — 대기 시간 (6회, 03:25~03:40)」, 「매도 조건 발동 · Stop Loss」 파랑, 「매도 체결 · 익절」, 「매수 체결 · 골든크로스 · 평단 400」 빨강) | 같음 |
| 「‹ 이전 · 1 / 12 · 다음 ›」 글자 줄 | 단추 2개 사이 「1 / 1」 | 다름(작음): 이전·다음이 테두리 단추 |
| 「이 화면에서 보는 것」 카드 | 같은 문장 | 같음 |

### 그림 2-마 운용 (`approval-05.png` ↔ `412-ops-full.png`)

| 그림 요소 | 화면 | 판정 |
|---|---|---|
| 카드 매매 전략(지금 전략 EMA (기존), 파란 「백테스터 규칙으로 전환」, 회색 「기존 전략으로 복귀 (지금은 해당 없음)」) | 같음(단추 비활성이라 옅은 색) | 같음 |
| 엔진(일시정지·엔진 정지) / 긴급 개입(강제 매수·강제 매도 빨강 테두리) / 운용 설정 글 카드 | 같음, 모두 비활성 | 같음 |
| (그림에 없음) | 맨 위 한 줄 「운용 단추는 2차 공개 때 열립니다. 매매 중지/재개는 홈 화면 위 단추로 합니다.」 | 다름 — 결정 1026-19 5 나(표시만) |

### 그림 5-가·5-나 저장 확인 창 (`approval-08.png` ↔ `412-dialog-upbit.png`·`412-dialog-binance.png`)

| 그림 요소 | 화면 | 판정 |
|---|---|---|
| 제목 「설정 저장 확인」, 「시험한 데이터: 업비트 · 종목 · 1분」 | 「시험한 데이터: 업비트 · KRW-ZRO · 3분」(바이낸스: 「바이낸스 · JTOUSDT · 3분」) | 같음 |
| 「지금 상태」 카드: 모드(LIVE 빨간 알약)·동작 중인 전략·엔진·보유 | 모드는 굵은 글자 「TEST」(알약 아님), 나머지 같음 + 「저장될 종목 / 저장될 봉 / 마지막 저장」 작은 글씨 3줄 | 다름(작음): 모드 알약 모양 없음. 추가 3줄은 계획 Task 5 |
| 「저장만 하기」(흰 테두리) | 파란 채움 단추 | 다름(작음): 1차에 누를 수 있는 유일한 단추라 강조 |
| 5-가 「이 설정으로 동작」(파랑, 누를 수 있음) + 「전환 확인(6절)으로 넘어갑니다」 | 비활성 「이 설정으로 동작」 + 「『이 설정으로 동작』은 2차 공개 때 열립니다.」 | **다름 — 근거**: 승인 요청서 5절 표 「1차 공개 기간: 『저장만 하기』만 열립니다. 『이 설정으로 동작』은 2차 공개 때 엽니다(9절)」 |
| 5-나 「🔒 이 설정으로 동작 (사용 불가)」 + 노란 상자 안내 | 「이 설정으로 동작 (사용 불가)」(자물쇠 그림 없음) + 같은 문장을 보통 글씨로 | 다름(작음): 자물쇠·노란 상자 모양 없음, 문장은 같음 |
| 「취소」 | 같음 | 같음 |

### 그림 1-나 구버전 입장 버튼 (`approval-02.png`)

| 그림 요소 | 확인 | 판정 |
|---|---|---|
| 「신버전 대시보드 입장 (LIVE)」 버튼, 「입장하기」 아래·「파라미터 설정하기」 위, 폭 전체 | `ui/v2_entry.py` 버튼 글자 `신버전 대시보드 입장 ({mode})`·`use_container_width=True`, `app.py:558` 이 입장하기 단추(477~529행) 뒤·파라미터 설정 단추(559행) 앞에서 부름 | 같음(코드·mock 시험 기준, 브라우저 실측 못 함 — 5절) |
| 누르면 다시 로그인 없이 신버전 | 누르면 토큰 생성 → `<meta http-equiv="refresh" content="0; url=/v2/?t=…">` → `st.stop()` (mock 시험 4건 + 회귀 11건) | 같음(시험 기준) |

### PC 1440 (`1440-*.png`)

모든 화면이 휴대폰 화면 그대로 가운데 480px(결정 1026-19 3 가). 확인 창 포함.

## 4. 사용자에게 사라지거나 옮겨지는 것 (project-rules 1-A 2)

| 지금(배포된 627b136) | 바뀐 뒤 | 실측 확인 |
|---|---|---|
| 홈 위 기본 블록(제목·안내 문장 「Upbit Trade Bot v1 상태 모니터링 페이지입니다.」·모드 안내·현재 시각·상태 로그·「트레이딩 엔진 상태 Running」 줄·자산 3칸) | 삭제. 엔진 상태·모드·일시정지는 홈 배지로, 자산은 자산 카드로 | `412-home-full.png` |
| 기본 블록의 「⏸️ 매매 중지/▶️ 매매 재개」·「로그아웃」 | 남김(결정 1026-23 1 가). 매매 중지는 배지 줄 바로 아래, 로그아웃은 머리 막대 오른쪽 | 같은 캡처 |
| 홈 「상태」·「자산」·「포지션」·최신 신호 20건 | 그림 2-가 카드(자산·보유·최신 신호 1건). 원화 잠김·코인 잠김·기록 시각·현재가 엔진 기록 시각은 자산 카드 아래 2줄로 남김 | 같은 캡처 |
| PC 차트 탭 창 전체 크기(1026-08) | 휴대폰과 같은 크기(480px, 차트 칸 300px) | `1440-chart.png` |
| 백테스터 결과 표(요약·분할 단계·주간·월간)·스윕 설정·차트·전략 설명 | 「자세한 결과」·「스윕 범위」·「전략 로직 설명」 접힘 안으로 이동(내용 보존) | `412-backtester-full.png` |
| 백테스터 위 기본 블록(PC) | 삭제 | `1440-backtester.png` |
| 운용 탭 「엔진 시작」·「운용 설정」 단추, 「전략·모드·일시정지」 3줄 표, 「구버전」 카드(링크 + 재로그인 안내) | 그림 2-마 배치(엔진 시작 단추 없음, 운용 설정은 글 카드, 단추 6개 비활성). 구버전 링크는 홈 머리 막대가 대신 | `412-ops-full.png` |
| 「구버전으로 돌아가면 다시 로그인해야 합니다」 안내 | 머리 막대·운용 탭에서 지움(그림에 없음). 「구버전으로」는 지금처럼 구버전 로그인 화면으로 간다(Streamlit 세션이 따로라서) | 홈 캡처 |
| 백테스터 기본값 3분·바이낸스 | 업비트·엔진 봉 단위·30일(로컬 가짜 계정은 3분, 서버 엔진도 KRW-JTO 3분 — 2026-10-27 배포 요청서 verifier 확인). 엔진 종목은 서버가 미리 받아 둬 수 초, 다른 종목은 첫 실행 데이터 약 57~94초(Task 4-0b 뒤 로컬 실측, 이전 54초) + 계산. 다시 실행하면 새 봉만 | 6절 |
| 구버전 입장 화면: 버튼 → 「신버전 열기」 링크 단추 두 단계 + 「다시 로그인」 캡션 | 버튼 한 번 누르면 바로 신버전(링크 단추·캡션 삭제). **구버전 화면은 엔진 재시작 때만 바뀜** | 시험(5절) |
| 차트 탭 제목 h2·형성 중 안내 문구·30초 안내 문구 | 삭제(머리 막대가 제목, 회색 봉 표시는 유지) | `412-chart.png` |
| 홈 거래 10건 목록 | 「최근 거래」 표(최근 기록) | 홈 캡처 |
| 모든 탭 머리의 엔진·일시정지 배지 *(verifier 수정 추가)* | 홈 배지 줄에만 남음. 다른 탭(차트·로그·운용) 머리 막대는 오른쪽에 모드(LIVE/TEST)만 | `412-chart.png`·`412-logs.png` |
| 홈의 코인 보유 수량 값, 상태 카드의 종목·봉·전환 예약 줄 *(verifier 수정 추가)* | 사라짐(자산 카드는 원화/코인 평가액, 종목은 보유 카드 제목에만). 현재가 값은 기록 시각 줄 「현재가 …원 HH:MM 엔진 기록」으로 남김(verifier 수정 C) | `412-home-final.png` |
| 최근 거래 「가격 × 수량」 *(verifier 수정 추가)* | 금액만(가격·수량 칸 없음) | 홈 캡처 |
| 백테스터 입력 11개·주간·월간 표·스윕 CSV·차트 다시 그리기 *(verifier 수정 추가)* | 접힘(「자세한 설정」·「자세한 결과」·「스윕 범위」) 안으로 이동, 펼치면 그대로 있음 | `412-backtester-full.png` |
| 로그 탭 기본 화면 엔진 로그 50행 *(verifier 수정 추가)* | 기본이 감사 로그 12행(쪽 넘김). 엔진 로그는 「엔진」 칸을 눌러 봄 | `412-logs.png` |

## 5. Step 3-2 — 구버전 입장 버튼 로컬 실측: **하지 못함**

`app.py` 는 시작할 때 `config`(ACCESS·SECRET — `.env` 의 실제 업비트 키), `.streamlit/secrets.toml`·`credentials.yaml`(로그인 계정), 실 DB(`services/init_db`), 헬스 모니터·엔진 관리자를 불러온다(`app.py:8-17,135-175`). 가짜 TEST 계정만으로 띄울 방법이 없고, 띄우면 실제 키·계정 파일을 프로세스가 읽게 된다(규칙: `.env`·secrets 를 읽지 않음). 그래서 브라우저 실측은 하지 않았다. 대신:

- 버튼 글자·폭·한 번 누름 이동·허용 밖 계정 버튼 0: `tests/test_v2_entry_button.py` 4건 OK, `tests/regressions/test_r_2026_10_23_v2_entry_button.py` 11건 OK.
- 위치: `app.py` 호출 순서(입장하기 477~529행 → `render_v2_entry` 558행 → 파라미터 설정 559행 → 로그아웃 586행)로 그림 1-나와 같음을 코드로 확인.
- **배포 뒤 관찰 (e) 에서 운영자 브라우저로 확인받는다**(엔진 재시작 뒤에만 보임).

## 6. Step 3 — 업비트 백테스트 실측 (로컬 맥 IP, 로컬 개발 서버)

조건: 개발 서버를 새로 띄워 보관 폴더가 빈 상태, 백테스터 412px, 출처 업비트 · KRW-BTC · 1분 · 30일 · 나머지 기본값. 시간은 페이지 안 `Date.now()`(단추 click 순간 = 0)와 `MutationObserver`(진행 줄·단추·요약 칸)·`fetch` 감싸기·Resource Timing 으로 쟀다. 원자료: 번들 `evidence/step3-measure.json`, 요약 `step3-summary.txt`.

### (a) 첫 실행 — 빈 보관

| 구간 | 시각(단추 기준) |
|---|---|
| 첫 GET `/v2/api/candles` → **202** `{"job":"running","progress":{"done":0,"total":216}}` | 0.01초 |
| 진행 표시 「업비트 데이터 받는 중… 113 / 216회」 | 29.7초 |
| 마지막 진행 읽기에서 작업 끝(`active:false`) 확인 | 약 53.6초 |
| 다시 GET → **200**, 42,888봉, 응답 2,959,341바이트(gzip 447,797바이트 전송) | 53.9초 (요청 199ms: 서버 대기 195ms·내려받기 3ms) |
| 「계산 중…」 → 「완료: 42,888개 봉…」, 결과 요약 칸 채워짐 | **54.0초** |

- 데이터 53.9초(목표 ≤55초) · 계산 0.07초 · 마지막 전송 0.2초 · **전체 54.0초(목표 60초 이내)**. 60초를 넘지 않아 분해 보고 조건에는 해당하지 않으나 참고로 나눴다.
- 수집 자체는 약 51~53초(진행 199/216 을 50.5초에 읽음). 216회 ÷ 약 52초 ≈ 초당 4.2회(상한 5회 아래).
- 화면은 2초 간격 진행 읽기라 끝을 아는 데 최대 약 3초 늦을 수 있다(읽기 간격 2초 + 응답).
- 결과 요약: 총 수익률 −19.3% · 거래 140회 / 승률 13% · 최대 낙폭 −19.4% (`step3-run1.png`).

### (b) 같은 조건 다시 실행

- GET 바로 **200**, `requests: 0`(보관분만으로 답함, 새 봉 0~2개면 요청 0~1), 응답까지 0.33초, 요약까지 **0.30초**(진행 줄 기준) — 목표 「바로 200, requests ≤2, 데이터 수 초」 충족.

### (c) 업비트 429 · progress

- 개발 서버 로그 `status=429` **0건**(이 실측과 1회째 시도 모두). `[V2-CANDLES]` 줄 0건(이상 없음).
- progress 첫 값 `total 216`. 끝난 뒤 값 `done 215 / total 216` — **계획의 「done 216」과 1 차이**. 원인: KRW-BTC 30일에 체결 없는 분이 있어(보관 봉 42,888 = 30일 43,198분보다 310분 적음, 1분 넘는 빈 곳 9군데) 업비트의 200봉 묶음이 시간상 200분보다 넓게 덮어, 옛 봉 쪽 요청이 계획 수(시간 길이 ÷ 200분)보다 1회 적게 끝났다. 받은 봉은 오름차순·중복 0, 기간 처음(09-26 19:03 UTC)부터 형성 중 봉 직전(10-26 19:01 UTC)까지. 결함이 아니라 「요청 수가 계획보다 적을 수 있음」으로 본다(화면 진행 표시는 215 / 216 에서 끝남).

### (d) 최대 메모리 (macOS `ru_maxrss` 는 바이트)

| 측정 | 값 |
|---|---|
| 기동 직후 RSS(ps) | 35.1~36.9 MiB (35,936~37,808 KiB) |
| 수집 중 최대 RSS(ps, 0.5초 간격, 응답 직전까지) | 46.4 MiB (47,504 KiB, 52.1초) |
| 42,888봉 응답을 만든 직후 RSS(ps) | 66.1 MiB (67,648 KiB, 54.1초) |
| 프로세스 수명 최대 `ru_maxrss`(`/usr/bin/time -l`, 첫 실행 + 다시 실행 + 차트 창 포함 119초) | **82,886,656 바이트 = 79.0 MiB** |
| 같은 측정 `peak memory footprint` | 75,334,304 바이트 = 71.8 MiB |
| 1회째 시도(같은 조건, 640초) `ru_maxrss` | 83,378,176 바이트 = 79.5 MiB |

판정: 계획의 「150MB 의 절반 아래」(유닛 `MemoryMax=150M` = 150 MiB → 절반 75 MiB)를 **수집 중에는 지킨다(최대 46.4 MiB)**. 그러나 프로세스 최대값은 **79.0 MiB 로 4 MiB 넘는다.** 넘는 순간은 수집이 아니라 42,888봉(약 2.96MB JSON)을 한 번에 직렬화·gzip 해 보내는 때다. 유닛 상한 150 MiB 에는 여유가 있고(OOM 위험 낮음), spec A12(상주 100MB 이하)는 지킨다. 서버(Linux, cgroup `MemoryCurrent`)에서는 값이 다를 수 있어 Step 6 (d) 로 다시 잰다. 코드는 고치지 않았다(규칙) — 10절 걱정거리 1. **→ 최종 검수 수정 A 로 고쳐 61.3 MiB 로 내려감((f), 12절).**

### (e) 차트 탭 다른 창과 함께

차트 탭 창 2개를 같은 브라우저에 열어 둔 채 위 두 실행을 했다. 두 창의 브라우저 업비트 응답 1건·4건, 모두 200, **429 0건**. 세 창 모두 콘솔 오류 0.

### (f) 최종 검수 수정 뒤 재측정 (2026-10-27, 12절 A 반영 뒤)

같은 방법(새 개발 서버 = 빈 보관, `/usr/bin/time -l`, `evidence/scripts/step3.py` 그대로, 차트 창 2개 함께)으로 다시 쟀다. 원자료: 번들 `evidence/final-step3-measure.json`·`final-step3-summary.txt`·`dev-server-final.log`. 캡처 `step3-run1.png`·`step3-run2.png` 는 이 재측정으로 덮어썼다.

| 측정 | 수정 전(Task 9) | 수정 뒤 |
|---|---|---|
| 첫 실행 단추 → 결과 요약 | 54.0초 | **54.2초** (데이터 54.1 · 계산 0.13 · 마지막 전송 0.27초 — 마지막 GET 200 은 분 경계를 넘겨 `requests: 1`, 265ms) |
| 다시 실행 | 0.30초, 200 `requests: 0` | **0.30초**, 200 `requests: 0`, 42,888봉 |
| 응답 본문 크기(풀린 크기 / gzip 전송) | 2,959,341 / 447,797 바이트 | **2,744,893 / 432,884 바이트** (빈칸 없는 구분자) |
| 수집 중 최대 RSS(ps, 2초 간격 표본) | 46.4 MiB | 47.5 MiB (48,656 KiB, 50.1초) |
| 첫 실행 응답 직후 RSS(ps) | 66.1 MiB | **55.7 MiB** |
| 다시 실행 직후 RSS(ps) | 62.8 MiB | 59.3 MiB |
| 프로세스 수명 최대 `ru_maxrss` | 82,886,656 바이트 = 79.0 MiB | **64,274,432 바이트 = 61.3 MiB** (85.6초 수명) |
| `peak memory footprint` | 75,334,304 바이트 = 71.8 MiB | 56,492,680 바이트 = 53.9 MiB |
| 서버 로그 `status=429` | 0 | 0 |
| 차트 창 2개 브라우저 업비트 응답 | 1건·4건 모두 200 | 1건·4건 모두 200, 콘솔 오류 0 |

판정: 「150MB 의 절반 아래」(75 MiB)를 **프로세스 최대값으로도 지킨다(61.3 MiB, 여유 13.7 MiB)**. 서버(Linux cgroup)에서는 Step 6 (d) 로 다시 잰다 — `MemoryCurrent` 는 페이지 캐시를 포함하므로 `memory.stat` 의 `anon`·`file` 을 따로 적는다.

## 7. 바꾼 기존 시험과 이유 (새 시험 포함)

| 파일 | 바꾼 Task | 이유 |
|---|---|---|
| `tests/v2/js/basic.test.mjs` | 1·2·7 | basic.js 가 매매 중지/재개·로그아웃만 남아 다시 씀, 그리는 곳 `#pause-row`, 운용 탭 안내 문구 새 한 줄 |
| `tests/v2/js/alpine_wiring.test.mjs` | 1·3·7 | `tabFromHash`·메뉴 순서(홈·차트·백테스터·로그·운용)·`#basic` 삭제, 두 번째 업비트 호출 `to=`, 운용 탭 카드 4개·단추 6개 비활성 |
| `tests/v2/js/chart.test.mjs` | 1·3 | `fitChartHeight` 삭제, `createRateGate` → `createSharedRateGate`, `maLines(periods)`·`mergeCandles`·`visiblePeriods`·`zoom` |
| `tests/v2/js/parity.test.mjs` | 4 | `#dataSource` 단언 2줄(업비트 선택 가능, 정적 기본 binance selected). backtester.js sha 시험은 그대로 |
| `tests/v2/js/save.test.mjs` | 5 | 저장 `source`(업비트/바이낸스)·창 문구·종목 불일치 경고 |
| `tests/v2/test_api_read.py` | 6 | 옛 logs 시험 3곳을 새 응답 키(kind/page/pages/rows/more)로, `TestLogsKinds` 신설, 인덱스 시험에 서브쿼리 틀 허용 |
| `tests/v2/test_api_write.py` | 5 | `source=upbit` 허용·그 밖 400 |
| `tests/v2/test_basic_pause.py` | 1·4-0 | basic 응답 `display_name`, 금지어 시험에서 `api.upbit.com` 은 `v2/candles.py` 만 예외 + 그 파일 `Authorization`·`jwt`·계좌·주문·`access_key` 0 |
| `tests/v2/test_server.py` | 4-0 | 서버 코드 업비트 주소 금지 시험의 candles.py 예외(1회만), import 그래프에 `v2.candles` |
| `tests/v2/test_static_lint.py` | 1·2·3·4·7 | OWN 목록(labels.js·bt_ui.js), 엔진 배지 시험을 `engineBadge` 기준으로, 신호 키 시험 → 단일 카드 시험, **`test_no_ma200` 삭제 → `test_chart_matches_figure_2_na`**(E4 폐기), 운용 단추 6개 비활성 |
| `tests/regressions/test_r_2026_10_23_v2_entry_button.py` | 8 | 버튼 글자 새 문구, **`test_click_shows_link_with_token` → `test_click_redirects_with_token`**(링크 단추 대신 meta refresh 토큰). 허용 밖 버튼 0 시험은 그대로 |
| 새 시험 | — | `tests/v2/js/home.test.mjs`(2), `tests/v2/js/bt_ui.test.mjs`(4·5), `tests/v2/js/logs.test.mjs`(6), `tests/v2/test_candles.py`(4-0, 38건 → 최종 검수 수정 뒤 42건 → verifier 수정 뒤 43건), `tests/test_v2_entry_button.py`(8, mock 4건) |

## 8. 컨트롤러 판정(Ruling)과 미뤄 둔 작은 문제 (원장 `progress.md` 전부)

### Ruling
- Ruling: 실행 에이전트는 커밋하지 않는다. Task 별 검수는 tree 스냅샷 차이로 한다 — 계획서 Global Constraints·project-rules 「커밋은 마지막에 한 번, 사용자 승인 뒤」가 스킬 기본(Task 마다 커밋)보다 우선 — 틀리면: Task 경계 diff 가 섞일 수 있음(스냅샷으로 막음).
- Ruling: main 작업 트리에서 진행(워크트리 없음) — 이 프로젝트 지금까지의 방식, 커밋이 없으므로 main 이력은 바뀌지 않음 — 틀리면: 미추적 파일 13건과 섞일 위험(스냅샷 diff 에서 기준과 같아 제외됨).
- Ruling: Task 1 의 test_static_lint OWN 목록에는 그 시점에 있는 파일만 넣는다. labels.js 는 Task 2, bt_ui.js 는 Task 4 가 넣는다 — 없는 파일을 OWN 에 넣으면 Task 1 시험이 실패 — 틀리면: 없음.
- Ruling: Task 4 브리프에는 Task 4-0 절도 들어 있다(추출기가 「Task 4」 로 4-0 도 잡음). 4-0 은 이미 구현된 것으로 참고만 — 틀리면: 없음.
- Task 2: Ruling: 보유 카드를 coin>0 또는 coin_locked>0 이면 보임(브리프는 coin 0 이면 보유 없음) — 서버 assets 의 holding 정의(api_read.py:232)와 같고 매도 주문에 잠긴 보유를 숨기면 사용자가 보유를 놓침 — 틀리면: 잠김만 있을 때 평가손익 「—」 와 카드가 같이 보임(표시 차이뿐)
- Task 4-0: Ruling: 보관 파일에 covered [from,to) 칸 추가 허용 — 거래 없는 분은 업비트가 봉을 만들지 않아 빈 곳과 '안 받음'을 구분해야 반복 요청을 막음 — 틀리면: 파일 형식 1칸 차이(시험으로 고정)
- Task 4-0: Ruling: 새 봉을 보관분 끝에서 앞으로 받음(브리프는 지금부터 뒤로) — 요청 수 같고 중단돼도 구멍이 생기지 않음 — 틀리면: 없음(요청 수 동일)
- Task 4-0: Ruling: candles.py 503줄(지침 ~400) 그대로 — 수집기·보관·미리 받기가 한 책임, 나누면 잠금·상태 공유가 흩어짐 — 틀리면: 읽기 부담
- Task 4-0: Ruling: Minor 3(마지막 확정 봉 다시 받기 — Issue #8 미확정 종가)을 Important 로 올림 — project-rules CRITICAL 규칙 — 틀리면: 요청 1회분 증가뿐
- Task 4-0: Ruling: Minor 1(기동 직후 미리 받기 대상 보호)을 Important 로 올림 — 지워지면 216회 재수집으로 엔진과 한도 공유 증가 — 틀리면: 없음
- Task 4: Ruling: 업비트 기간 1~30 외 거절(브리프 밖 추가) 유지 — 서버 400 을 화면에서 먼저 막아 알기 쉬운 문구 — 틀리면: 없음
- Task 6: Ruling: 응답에 more(bool) 칸을 더하고 상한 도달 시 화면 「p / 100+」 — 브리프 「1201 이면 100+」 를 지키려면 신호가 필요 — 틀리면: 응답 키 1개 추가뿐
- Task 6: Ruling: sell_eval 은 최근 1200행을 안쪽 서브쿼리로 자른 뒤 triggered=1 거르기(브리프 원안). 인덱스 추가 안 함 — 엔진 DB 구조 변경 금지 — 틀리면: 최근 1200 판단 밖의 오래된 발동은 감사 로그에 안 보임(보고에 명시)
- Task 6: Ruling: error 종류(목록·COUNT)는 그 사용자 logs 최근 20000행을 안쪽 서브쿼리로 자른 뒤 level 거르기 — 오류가 드문 사용자의 전체 스캔 방지 — 틀리면: 최근 20000행보다 오래된 오류는 안 보임(엔진 탭에서는 보임)
- Ruling: Task 7·8 을 한 실행 에이전트·한 검수로 묶음 — 둘 다 작고 파일이 겹치지 않음(index.html 운용 탭 / ui/v2_entry.py) — 틀리면: 검수 범위가 넓어질 뿐
- Ruling: 최종 수정에 Minor 1(쉼 중 보관분만으로 답할 수 있으면 200)·「·」 구분자·미리 받기 주기 60→600초 포함 — 엔진 재시작마다 5분 백테스트 막힘은 사용자 기대와 다르고, 매분 3MB 다시 쓰기는 하루 3~4GB 쓰기, 600초여도 처리기 안 2회 요청(1분봉 약 6시간)으로 「수 초」 유지 — 틀리면: 미리 받기 최신성 10분 늦음(요청 시 채움)
- Ruling: verifier 결정 1 = 나(prefetch_loop 첫 대기를 PREFETCH_DELAY 300초로) — 계획서·문서·관찰 (c) 가 5분 뒤를 전제, 첫 10분 엔진 종목 216회 수집 구간 줄임 — 틀리면: 없음
- Ruling: verifier 결정 2 — 기록 시각 줄에 현재가 값을 다시 넣음(「현재가 1,000원 · HH:MM 엔진 기록」), 코인 보유 수량 제거는 사라짐 표에 적어 보고 — 결정 1026-23 1 가 「기록 시각」 줄 안의 값이라 배치 변화 없음 — 틀리면: 문구 한 줄. *(구현은 컨트롤러 지시문 「현재가 <가격>원 HH:MM 엔진 기록」 대로 가격과 시각 사이에 「·」 없이 넣었다 — 원장 문구와 「·」 1개 차이)*
- Ruling: 보유 카드 가격 정수 반올림을 가격 크기별 소수 표기로 고침 — PEPE 등 100원 미만 종목이 서버 설정에 있어 실제로 틀린 값이 보임 — 틀리면: 없음

### 미뤄 둔 작은 문제 (minor deferred) — Task 9 실측 결과 덧붙임
- Task 1: minor (deferred): api_read.py:721 SQL_PAUSED '=' 뒤 공백 — Task 2 에 되돌리기 지시 → **Task 2 에서 고침**
- Task 1: minor (deferred): engineClass/engineIcon 이 engine_running false 를 반영 안 함 — Task 2 배지에서 맞춤 → **Task 2 `engineBadge` 로 대체**
- Task 1: minor (deferred): tabTitle 봉 원문(minute1), 머리 막대 「·」 구분자 렌더 없음 — Task 9 실측 → **실측으로 둘 다 확인됨**(차트 머리 「KRW-ZRO · minute3」, 홈 머리 「Dev User님 구버전으로 로그아웃」에 「·」 없음). 10절 걱정거리 2 → **최종 검수 수정 C·F 로 고침**
- Task 1: minor (deferred): display_name 시험이 test_basic_pause.py 에 있음(영향 없음)
- Task 2: minor (deferred): home.test 에 coin_locked 소수 표기·holding locked 분기 시험 없음
- Task 3: minor (deferred): 공유 문 allow() 읽기·쓰기 경쟁(창 둘 같은 ms), 재시도 +50ms 고정 — 지터 권고 → 실측(창 3개)에서 429 0건
- Task 3: minor (deferred): 범례 글자 ━ (명세 —)
- Task 3: minor (deferred): 400봉 수집 중 숨김 탭이면 다음 30초까지 늦어짐
- Task 4-0: minor (deferred): progress 작업 구분(Task 4 가 kind·market·unit 대조 — 계획서에 이미 있음), alive 오래된 값(대상 1명이라 영향 없음), .tmp 찌꺼기, 503줄
- Task 4-0: minor (deferred): 418 뒤 _blocked 는 프로세스 안에서 안 풀림 → runbook 「.halt.json 삭제 + tradebot-v2 재시작」 (Task 9 Step 5 에 반영 지시) → **runbook 반영함**
- Task 4-0: minor (deferred): 새 봉 수 mod 200 ∈ {0,199} 이면 요청 1회 추가(겹침)
- Task 4: minor (deferred): status 응답이 #src 를 무조건 덮음(bt_ui.js:1079)
- Task 4: minor → Task 5 로 넘김: days 정수 검사(Number.isInteger) → **Task 5 에서 고침**
- Task 4: minor (deferred): get() 타임아웃 없음(nginx 60초가 끊음), .bottom a.on 스타일 위치, 새 run 때 #sweepBrief 안 지움
- Task 5: minor (deferred, 최종 수정 후보): save.js /v2/api/basic 실패가 Promise.all 로 저장 전체를 막음 — 실패해도 저장 가능, 엔진 행 「확인 불가」 → **최종 검수 수정 B 로 고침**
- Task 5: minor (deferred): 보유 행 coin+coin_locked 부동소수 표시, engineLabel 미사용
- Task 6: minor → 함께 고침: 종류 전환 때 logRows 비우기 → **Task 6 fix round 에서 고침**
- Task 6: minor (deferred): 종류 전환 뒤 요청 실패 시 빈 목록(머리말 오류 표시는 있음); audit more 는 합계 기준; 쪽 넘김마다 세 표 다시 읽음(캐시 없음); 다른 종목 같은 failed_keys 연속이면 한 구간으로 묶임
- Task 7+8: minor (deferred): .ops-grid small 죽은 CSS, strategyLabel 직접 시험 없음, mock st.stop
- Final fix wave: re-review Minor (deferred): `_load` 는 깨진 행이 하나라도 있으면 파일 전체를 깨진 것으로 보아 전체 재수집 — 예전과 같음
- deferred (out of scope): `start_job` 이 total 계산에 `_load` 전체 읽음(봉 사전을 만들었다 버림); 엔진 재시작 쉼 300초 동안 1분봉 백테스트는 새 봉 1개 필요로 429

### 규칙 위반 기록 (원장 그대로)
- Task 1 실행 에이전트: 빈 heredoc 3회(무해)
- PO: 진행 기록 갱신 중 빈 heredoc 1회(내용 없음, 무해)
- Task 2 실행 에이전트: 빈 heredoc 3회(무해)
- Task 3 실행 에이전트: 빈 heredoc 4회(무해, scratchpad 빈 파일 2개)
- Task 4 실행 에이전트: 빈 heredoc 1회(무해)
- Task 5 실행 에이전트: 빈 heredoc 3회(무해)
- Task 6 실행 에이전트: 빈 heredoc 1회(무해)
- Task 7+8 실행 에이전트: 빈 heredoc 3회(무해); Task 8 mock 시험은 구현 뒤 작성(RED 는 옛 회귀 단언 실패뿐)
- **빈 heredoc 합계 19회**(실행 에이전트 18 + PO 1). Task 4-0·Task 9 는 기록 없음.
- 최종 검수 수정(Final fix wave): 여러 줄 `python3 -c "…"`(여러 줄 문자열 인자)로 소스·시험·문서 치환 — heredoc 은 아니나 규칙 5 「여러 줄 파이썬은 파일로」 위반. 그 밖에 인자 없는 `cat > /dev/null` 1회(빈 입력, 무해). verifier 수정 회차에서는 쓰지 않음(Edit 도구·한 줄 sed·printf 만).

## 9. Step 5 — 문서 갱신

| 파일 | 고친 곳 |
|---|---|
| `docs/specs/v2-dashboard/spec.md` | 머리 상태 줄, G2(PC 도 480px, 1026-08 폐기), R7 폐기 표시, **D8**(공개 캔들만·상한·멈춤 조건, 계좌·주문 0), E4 폐기 표시, 새 3.3절(결정 1026-19·1026-23 표 + 폐기 목록 R7·E4·1025-18·1025-19 홈 블록 배치·1026-08), 4.1 업비트 호출 줄(`UPBIT_URL` 1곳), 4.3 배치·기본 기능 블록(폐기, basic.js 는 매매 중지·로그아웃만), 차트 줄(60선·200선·공유 문·400봉), 운용 줄(그림 2-마·5 나), 구버전으로 줄, 4.4 출처(업비트 = 서버 중계·보관), 투자자 통보 문안 A 의 R7 문장 미사용 표시, 수용 기준 A4·**A14**(`v2/candles.py` 의 `UPBIT_URL` 1곳만 예외, `pyupbit`·계좌·주문 경로 0)·A21 |
| `docs/operations/v2-runbook.md` | 「동결 파일 2개」 절에 이번 `ui/v2_entry.py` 변경과 「구버전 화면은 엔진 재시작 때만 바뀜」, 새 절 「업비트 캔들 보관」: `services/data/v2_candles/`(폴더 700·파일 600, 지워도 다시 받음), `[V2-CANDLES]` 로그 확인 줄, **418 정지 해제(원인 확인 → 엔진 시세 조회 정상 확인 → `.halt.json` 삭제 → `systemctl restart tradebot-v2` — 프로세스 안 정지는 재시작해야 풀림)**, 끄는 방법(`systemctl stop tradebot-v2` — 엔진 영향 없음 / 보관 폴더 유지한 채 이전 커밋으로 되돌림) |
| `ui/v2_entry.py` | docstring 「1차 배포 뒤 동결 파일」 → 이번 변경 사실(한 번 누르기 이동, 엔진 재시작 때만 반영). 코드 변경 없음(`py_compile`·시험 15건 OK) |

`pages/dashboard.py` 는 고치지 않았다(버전 갱신은 사용자 승인 뒤 커밋 때).

## 10. 걱정거리 (DONE_WITH_CONCERNS)

1. ~~메모리 75 MiB 기준 4 MiB 초과(로컬 macOS) — `ru_maxrss` 79.0 MiB~~ → **최종 검수 수정 A 로 해소: 재측정 `ru_maxrss` 64,274,432 바이트 = 61.3 MiB**(6절 (f)). 남은 일: 서버 값은 Step 6 (d) 로 잰다(`MemoryCurrent` 와 함께 `memory.stat` 의 `anon`·`file` 따로).
2. ~~차트 머리 막대 봉 단위 원문 표시, 홈 머리 막대 「·」 구분자 없음~~ → **최종 검수 수정 C·F 로 해소**(「차트 · KRW-ZRO · 3분」, 「이름님 · 구버전으로 · 로그아웃」). 브라우저 캡처는 다시 찍지 않았다 — 시험(문자열·마크업)으로 확인, 배포 뒤 (e) 에서 눈으로 확인.
7. **(최종 검수 수정 D 의 범위)** 「보관분으로 바로 200」은 `_plan` 이 업비트 요청 0회라고 할 때만이다. 1분봉은 다음 분이 되면 새 봉 1개가 생겨 요청 1회가 필요해지므로, 엔진 재시작 300초 쉼 동안 1분봉 백테스트는 대부분 여전히 429 다(같은 분 안에 다시 누른 경우만 200). 쉼 중에 「조금 오래된 보관분」을 내줄지는 이번 판정 밖이라 하지 않았다.
3. **progress done 215 / total 216** — 체결 없는 분 때문에 요청이 계획보다 1회 적게 끝남(6절 (c)). 결함 아님, 계획의 「done 216」 문구와만 다름.
4. **Step 3-2 브라우저 실측 못 함** — 구버전 app.py 가 실제 키·계정 파일 없이는 뜨지 않음(5절). 배포 뒤 (e) 로 확인.
5. 그림과 작은 모양 차이(확인 창 모드 알약·노란 상자·자물쇠, 출처 선택 칸 색 농도, 로그 쪽 이동 단추 모양, 백테스터 검은 진행 줄) — 3절 표.
6. 측정 방법: Chrome DevTools MCP 를 쓰지 못해 별도 헤드리스 Chrome + CDP 스크립트로 쟀다(2절). 1회째 업비트 실측은 측정 스크립트 결함으로 결과 JSON 을 못 남겨(2회째 실행 끝 감지 실패, 600초 대기) 새 서버로 다시 쟀다 — 업비트 호출은 두 번(1분·30일 216회씩) 나갔다(로컬 맥 IP, 429 0건).

## 11. Step 6 — 배포 뒤 관찰 (배포 요청서에 그대로 옮김, 배포는 따로 승인)

배포 요청서 머리에 적을 것:
- **구버전 화면은 엔진(`tradebot`) 재시작 때만 바뀐다.** `ui/v2_entry.py` 는 구버전 프로세스 안 코드라, `tradebot-v2` 만 재시작하면 입장 버튼은 예전 두 단계(버튼 → 링크) 그대로다. 한 번 누르기 이동은 다음 엔진 재시작 뒤에 보인다.
- **418 정지가 걸리면 `services/data/v2_candles/.halt.json` 삭제 + `systemctl restart tradebot-v2`** 로 푼다(원인 확인·엔진 시세 조회 정상 확인 뒤, runbook 「418 정지 해제」). 파일만 지우면 프로세스 안 정지가 남는다.
- 버전: `pages/dashboard.py` `v1.2026.10.26.1927 → (커밋 시각)` — 커밋 때 채운다.

관찰 항목(출처는 `journalctl -u tradebot`(엔진)·`journalctl -u tradebot-v2`(v2)):

- [ ] (a) 배포 전 24시간과 배포 뒤 24시간의 엔진 「응답 없음」 4종 건수 비교: `[REST] Batch … 응답 없음`(core/rest_reconcile.py:280-284), `[실시간 API] 응답 없음`(core/data_feed.py:1068), `[백필] API 응답 없음`(:1239), `[SYNC-FILL] API 응답 없음`(:284). 배포 뒤가 배포 전보다 늘면 tradebot-v2 를 멈추고 보고한다.
- [ ] (b) `[V2-CANDLES]` 건수·status 별 수(429·418 은 0 이어야 함).
- [ ] (c) 미리 받기 확인: 기동 약 5분 뒤 수집 시작, 1회/초로 엔진 종목 30일(서버는 3분봉 72회 약 1.2~1.6분(창 1회 대기 포함), 1분봉이면 216회 약 4분)이라 `services/data/v2_candles/` 의 엔진 종목 파일(600)은 기동 약 7분(1분봉이면 9분) 뒤 생김(verifier 수정 2026-10-27), 그 뒤 운영자 계정으로 엔진 종목·엔진 봉 단위·30일 백테스트를 눌러 데이터가 수 초 안에 오는지(브라우저 네트워크 기록의 `/v2/api/candles` 응답 시간).
- [ ] (d) 엔진 종목이 아닌 종목으로 1분·30일 수집을 하는 동안 `systemctl show tradebot-v2 -p MemoryCurrent` 를 1초마다 읽어 최대값을 기록(서버 systemd 249 에는 MemoryPeak·memory.peak 가 없음, 150M 의 절반 아래여야 함). 같은 때 `/sys/fs/cgroup/system.slice/tradebot-v2.service/memory.stat` 의 `anon` 과 `file` 을 따로 기록한다(MemoryCurrent 에는 페이지 캐시가 들어 있다 — 보관 파일 읽기·쓰기가 `file` 로 잡힌다). **수집 끝·응답 순간까지 이어서 읽는다**(로컬 최대값은 응답을 만드는 순간: 수정 전 79.0 MiB, 최종 검수 수정 뒤 61.3 MiB). 또 그 다른 종목 수집이 도는 동안 엔진 종목 보관분 1분·30일 백테스트를 동시에 1회 눌러(보관분만으로 답할 수 있으면 200 이 나가 수집과 큰 응답이 겹친다. 새 봉이 필요하면 409 busy — 응답 코드도 함께 적는다) 같은 방법으로 최대값과 `anon`·`file` 을 기록한다 (verifier 수정 2026-10-27).
- [ ] (e) project-rules 1-A 3층: 운영자에게 브라우저 새로고침을 요청해 홈 화면 문구·단추 위치를 확인받는다(엔진 재시작이 있었다면 구버전 입장 버튼 한 번 누르기도 — Step 3-2 대신).
- [ ] (f) 배포 완료 보고에 3점(로컬·서버 HEAD·버전, ExecMainStartTimestamp)과 「버전: 구 → 신」.

## 12. 최종 검수 수정 (2026-10-27, 브랜치 전체 검수 뒤)

커밋 없음(작업 트리). 엔진 경로·`backtester.js`·`pages/` diff 0. 수정별 TDD 증거는 `.superpowers/sdd/plan-proposal-match-20261026/final-fix-report.md`.

| # | 등급 | 바꾼 것 | 파일 | 시험 |
|---|---|---|---|---|
| A | Important | 메모리 최대치 79.0 MiB > 75 MiB: (a) `serve` 가 `collect` 를 기다리는 동안 `_load` 의 봉 사전을 들고 있지 않음(구간만 쓰고 `del`, 미리 받기를 멈춘 경우에만 다시 읽음), (b) `_load` 가 읽은 행 목록을 검사·제자리 형 변환 뒤 그대로 값으로 씀(같은 크기 목록을 한 벌 더 만들지 않음, 5칸 미만 행은 깨진 파일로 봄), (c) 캔들 응답을 빈칸 없는 구분자로 직렬화(`send_json(..., compact=True)`). 동작 변화 없음. 재측정 `ru_maxrss` **61.3 MiB** | `v2/candles.py`, `v2/handlers.py`, `v2/api_read.py` | `test_load_reuses_parsed_rows`, `test_202_then_200_gzip`(본문에 `", "`·`": "` 없음), 6절 (f) |
| B | Important | 저장 확인 창 미리 읽기: `/v2/api/basic` 실패만 `null` 로 받아 저장을 막지 않음(`preloadAll`), 엔진 행 「확인 불가」(「멈춤」 아님). status·assets·params 실패는 이전처럼 전체 실패 | `v2/static/save.js` | `save.test.mjs` 「preloadAll: basic 실패만 null…」 |
| C | Important | 차트 머리 막대 「차트 · KRW-ZRO · minute3」 → 「차트 · KRW-ZRO · 3분」(단추 줄 첫 칸 `chartUnitLabel` 재사용, 60 은 「60분」) | `v2/static/app.js` | `alpine_wiring.test.mjs` 차트 시험에 `tabTitle` 단언 |
| D | 컨트롤러 판정 | `serve`: 418 정지 확인 → 보관분이 기간을 덮어 업비트 요청 0회면 **쉼 확인보다 먼저** 200 `requests: 0`(엔진 재시작 300초·429 60초 쉼 중에도). 업비트를 불러야 하는 요청은 여전히 429. 418 정지 중에는 보관분도 내주지 않음(503). 다른 종목 사용자 작업이 진행 중이어도 보관분만으로 답하는 요청은 409 없이 200(업비트 호출 없음) | `v2/candles.py` | `test_cached_only_served_during_cooldown`, `test_cached_only_after_pid_change_but_not_during_halt`. 기존 (g)·`test_prefetch_loop_detects_pid_change`·`test_429_and_503` 은 빈 보관(업비트 필요)이라 429 그대로 통과 |
| E | 컨트롤러 판정 | 미리 받기 간격 `PREFETCH_EVERY` 60 → **600초**(기동 300초 지연은 그대로). 처리기 안 2회 요청이 1분봉 약 6시간치 빈 곳을 덮어 「엔진 종목 수 초」 유지 | `v2/candles.py`, `v2/server.py`(주석) | `test_prefetch_every_600` |
| F | Polish | 홈 머리 막대 「이름님 · 구버전으로 · 로그아웃」 — `<span class="bar-sep" aria-hidden="true">·</span>` 2개(이름이 없으면 첫 「·」 숨김), 간격 10px → 6px, 회색 | `v2/static/index.html`, `v2/static/style.css` | `alpine_wiring.test.mjs` index 시험 |

동작 변화(사용자·운영자에게 보이는 것):
- **쉼과 보관분**: 이전에는 429·엔진 재시작 쉼 중이면 보관분이 있어도 429 였다. 이제 업비트 요청 0회로 답할 수 있으면 200. 다만 1분봉은 다음 분에 새 봉 1개가 생겨 요청 1회가 필요하므로, 쉼 중 1분봉 백테스트는 같은 분 안이 아니면 여전히 429 다(10절 걱정거리 7).
- **미리 받기 600초**: 엔진 종목 보관이 최대 10분(+수집 시간) 늦을 수 있고, 그 사이 백테스트 요청은 처리기 안에서 새 봉(1~2회 요청)을 받아 바로 200.
- 문서: 계획서 Task 4-0(미리 받기 600초·보관분 먼저 줄)·Task 9 Step 6 (d)(`memory.stat` `anon`·`file`), runbook 미리 받기 줄, spec 4.4 출처 줄을 고쳤다.

### verifier 수정 (2026-10-27, verifier 「수정 후 승인」 뒤 컨트롤러 판정)

| # | 바꾼 것 | 파일 | 시험 |
|---|---|---|---|
| A | `prefetch_loop` 첫 대기가 `PREFETCH_EVERY`(600초)여서 첫 미리 받기가 기동 600초 뒤였다(문서는 5분 뒤). 첫 대기 `PREFETCH_DELAY` 300초, 그 뒤 600초마다. 이로써 spec·runbook·server.py 주석의 「기동 5분(300초) 뒤부터」가 실제와 맞는다. 관찰 (c) 를 「기동 약 5분 뒤 수집 시작, 216회라 파일은 약 9분 뒤」로 고침(계획서·이 보고 11절) | `v2/candles.py`, `tests/v2/test_candles.py` | `test_prefetch_loop_first_at_300_then_every_600`(가짜 시계: 300·900·1500초), `test_prefetch_loop_fills_targets_before_first_sleep` 의 멈춤 조건을 첫 대기(300초) 기준으로 |
| B | 보유 카드 평균 매수가·익절·손절 가격을 정수 원 반올림 → 크기별 고정 소수(≥1000: 0, ≥100: 1, ≥10: 2, ≥1: 3, <1: 4자리, 천 단위 쉼표, `priceText`). 평가 합계·원화/코인·평가손익·잠김 원화는 정수 그대로. **화면 변화: 965.7원 종목의 평단이 「966원」 → 「965.7원」, 손절 930 → 「930.0원」** | `v2/static/app.js` | `home.test.mjs` 「priceText…」(0.001234 → 「0.0012」, 1,234.5 → 「1,235」, PEPE 형 보유 카드), 기존 보유 카드 시험 기대값 2개 고침 |
| C | 기록 시각 줄에 현재가 값을 다시 넣음: 「기록 시각 HH:MM:SS · 현재가 <B 표기>원 HH:MM 엔진 기록」(오늘이 아니면 MM-DD HH:MM, 값 없으면 「—」, 시각 없으면 시각 생략) | `v2/static/app.js` | `home.test.mjs` 「기록 시각 줄…」, 기존 (g) 기대값 2개 고침 |
| D·E·F·H | 보고서: 4절 사라짐 표 5행, 8절 Ruling·deferred·위반 전부, 6절 ps RSS 를 KiB÷1024 로 다시 환산(수정 전 수집 중 46.4·응답 직후 66.1·기동 35.1~36.9 MiB), 0절 1440 main 폭 실측값, 11절 (d) 동시 백테스트 메모리 | 이 문서 | — |
| G | 최종 화면 재측정(2절 「최종 화면 재측정」): 412·360 홈·로그 가로 넘침 0·콘솔 0·4xx 0, 캡처 8개 | `shots/*-final*.png` | — |

## 13. Fable 번들

- 경로: `/Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/v2-proposal-match-report-20261027.zip`
- 크기: **1,642,942 바이트**, 64개 항목 (verifier 수정 뒤 다시 묶음, 2026-10-27. 이전 판: 최종 검수 수정 1,303,359 · Task 9 1,269,490 바이트)
- 최종 검수 수정으로 더한 것: `final-fix-report.md`, `evidence/final-*`(시험 출력 4개·Step 3 재측정 JSON·요약·stderr), `evidence/dev-server-final.log`, 고친 `evidence/commands.txt`, 재측정으로 바뀐 `shots/step3-run1.png`·`step3-run2.png`. 옛 Task 9 증거는 그대로 둠. verifier 수정으로 더한 것: `evidence/final-step2-measure.json`·`final-step2-stderr.txt`·`dev-server-final2.log`·`scripts/step2final.py`, 캡처 8개 `shots/*-final*.png`, 다시 돌린 `final-*` 시험 출력.
- `.gitignore:92` `docs/specs/*/*.zip` 로 커밋 제외(`git check-ignore` 확인). 번들 안 `report.md` 는 이 문서에서 13절(이 절)의 크기·목록만 채우기 전 판이다. 개발 서버 로그의 입장 토큰은 가렸다(`?t=***(redacted)`). 전체 캡처 48개는 `.superpowers/sdd/plan-proposal-match-20261026/shots/` 에 있고 번들에는 대조에 쓴 21개만 넣었다.

```
Archive:  /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/v2-proposal-match-report-20261027.zip
  Length      Date    Time    Name
---------  ---------- -----   ----
    55329  10-27-2026 04:49   report.md
    11069  10-27-2026 04:49   final-fix-report.md
        0  10-27-2026 04:49   evidence/
    13319  10-27-2026 04:11   evidence/py-v2.txt
    10212  10-27-2026 04:49   evidence/final-step3-measure.json
     2147  10-27-2026 04:49   evidence/final-step2-measure.json
    22400  10-27-2026 04:49   evidence/final-node-test.txt
        0  10-27-2026 04:49   evidence/final-step2-stderr.txt
    73626  10-27-2026 04:49   evidence/final-regression-gate.txt
     6740  10-27-2026 04:49   evidence/final-step3-summary.txt
    13765  10-27-2026 04:49   evidence/final-py-v2.txt
     2572  10-27-2026 04:11   evidence/step2-summary.txt
      366  10-27-2026 04:11   evidence/dev-server-2.log
     1103  10-27-2026 04:11   evidence/dev-server-step3-attempt1.log
     1103  10-27-2026 04:11   evidence/dev-server-1.log
     1103  10-27-2026 04:11   evidence/dev-server-step3.log
      630  10-27-2026 04:49   evidence/final-py-entry.txt
        0  10-27-2026 04:49   evidence/scripts/
     2686  10-27-2026 04:11   evidence/scripts/step2.py
     6097  10-27-2026 04:11   evidence/scripts/step3.py
      492  10-27-2026 04:11   evidence/scripts/sum2.py
     6073  10-27-2026 04:11   evidence/scripts/cdplib.py
     2039  10-27-2026 04:49   evidence/scripts/step2final.py
      927  10-27-2026 04:11   evidence/scripts/sum3.py
     1143  10-27-2026 04:29   evidence/dev-server-final.log
      366  10-27-2026 04:49   evidence/dev-server-final2.log
     7113  10-27-2026 04:11   evidence/step2-measure.json
     6740  10-27-2026 04:11   evidence/step3-summary.txt
     3594  10-27-2026 04:49   evidence/commands.txt
      637  10-27-2026 04:11   evidence/py-entry.txt
    10212  10-27-2026 04:11   evidence/step3-measure.json
    73031  10-27-2026 04:11   evidence/regression-gate.txt
    21629  10-27-2026 04:11   evidence/node-test.txt
       39  10-27-2026 04:49   evidence/final-step3-stderr.txt
        0  10-27-2026 04:49   shots/
    47024  10-27-2026 04:11   shots/360-backtester.png
    55664  10-27-2026 04:49   shots/412-home-final.png
    59042  10-27-2026 04:11   shots/412-dialog-upbit.png
    64113  10-27-2026 04:11   shots/1440-backtester.png
    56209  10-27-2026 04:11   shots/412-backtester-full.png
   129026  10-27-2026 04:11   shots/approval-02.png
    80119  10-27-2026 04:11   shots/approval-03.png
    34557  10-27-2026 04:11   shots/412-logs.png
    62683  10-27-2026 04:11   shots/approval-04.png
    55647  10-27-2026 04:11   shots/approval-05.png
    34560  10-27-2026 04:49   shots/412-logs-final.png
    55027  10-27-2026 04:11   shots/412-home-full.png
    32195  10-27-2026 04:49   shots/360-logs-final-full.png
    55664  10-27-2026 04:49   shots/412-home-final-full.png
   101753  10-27-2026 04:11   shots/approval-08.png
    41126  10-27-2026 04:11   shots/412-chart.png
    45792  10-27-2026 04:11   shots/1440-chart.png
    34643  10-27-2026 04:11   shots/412-ops-full.png
    55965  10-27-2026 04:11   shots/412-backtester.png
    54037  10-27-2026 04:49   shots/360-home-final.png
    69013  10-27-2026 04:11   shots/1440-dialog-upbit.png
    60978  10-27-2026 04:11   shots/412-dialog-binance.png
    65281  10-27-2026 04:11   shots/1440-home.png
    32195  10-27-2026 04:49   shots/360-logs-final.png
    54037  10-27-2026 04:49   shots/360-home-final-full.png
    53487  10-27-2026 04:11   shots/360-home.png
    34560  10-27-2026 04:49   shots/412-logs-final-full.png
    60288  10-27-2026 04:29   shots/step3-run1.png
    60348  10-27-2026 04:29   shots/step3-run2.png
---------                     -------
  2003335                     64 files
```

## 14. Task 4-0b — IP 차단(418) 방지 (2026-10-27, 사용자 결정 1027-05 4 「IP 차단 발생하지 않는 방법으로 진행」)

바꾼 것 (`v2/candles.py`, 커밋 없음):
- (0) `USER_RATE` 5.0 → **4.0**(요청 간격 ≥ 0.25초). `PREFETCH_RATE` 1.0 그대로. v2 4 + 관측된 엔진 묶음 5 = 9 ≤ 10 (관측값 기준이며 코드 상한이 아니다 — 구버전 화면 새로고침(캔들 3회)·엔진 기동(801봉, 5회 이상)·여러 엔진 동시 묶음이 같은 1초에 겹치면 10 을 넘을 수 있어, 보장이 아니라 창·쉼·429 멈춤으로 겹침을 줄이는 장치다. verifier 2026-10-27).
- (가) 엔진 봉 경계 창: `_request` 가 업비트를 부르기 직전(pid·쉼 확인 자리) 지금이 어느 엔진 봉 경계 b 의 `[b−2초, b+20초)` 안이면 창 끝까지 `sleep` 한 뒤 작업 중단·pid·정지·쉼을 다시 보고 부른다. 봉 단위 = `self.prefetch_targets`(prefetch_loop 가 갱신)의 단위들, 비었으면 1분. 경계 = UTC 에포크 초가 `unit*60` 의 배수. 사용자 수집·미리 받기 모두 적용. 보관분만으로 답하는 경로(업비트 0회)는 창과 무관하게 바로 200. *(Task 4-0b fix round 1 로 대체: 창 기준 = `.engine_alive.json` running 사용자 전원의 봉 단위(`self.window_units`), 못 읽으면 1분. `prefetch_targets` 는 정리 보호용)*
- (나) 429: 첫 429 → `COOLDOWN_429 = 600`(10분), `WARNING [V2-CANDLES] status=429 … — pause 600s`. 24시간 안 두 번째 429 → 418 과 같은 정지(메모리 정지 + `.halt.json` `{"at","status":429,"reason":"second 429 in 24h"}` 600, `ERROR [V2-CANDLES] status=429 HALT`) → 화면 503 `upbit_blocked`(「운영자 확인이 필요합니다」). `{"until","last_429"}` 을 `services/data/v2_candles/.cooldown.json`(600, 원자적 쓰기)에 남기고 기동 때 읽어 재시작 뒤에도 10분 멈춤·24시간 셈을 잇는다. 두 번째 429 정지 때도 `last_429` 를 그 시각으로 고쳐 쓴다(해제 뒤 24시간 안 다음 429 도 바로 정지 — 보수적).
- 그 밖의 장치(PREFETCH_RATE 1, sec≤4 쉼, 동시 1건, pid 변경 300초, 418 정지, 쉼 중 보관분 200)는 그대로.

시험: `tests/v2/test_candles.py` 새 `TestIpBlockGuard` 15개 + 처리기 `test_second_429_halt_shows_503`. 상수 때문에 바꾼 기존 시험(동작 회귀 아님): `test_rate_spacing`(5.0·≤0.2 → `USER_RATE`·≤0.25), `test_same_market_prefetch_switches_to_user_rate`(5.0 → `USER_RATE`), `test_429_cooldown_60` → `test_429_cooldown_600`(60·30·31 → 600·570·571), `test_job_429_into_progress`(60 → 600), `HandlerTests.test_429_and_503`(60·+61 → 600·+601), `test_cached_only_served_during_cooldown`(주석만, `COOLDOWN_429` 를 그대로 써 600 에서도 뜻 유지). 결과: test_candles 59 OK, v2 전체 337 OK, JS 115/115, test_v2_entry_button 4 OK, regression_gate 350/350. (fix round 1 뒤: test_candles 68, v2 346)

### Step 5 재측정 (로컬 맥 IP, 개발 서버, KRW-BTC 1분·30일, 빈 보관, 차트 창 2개)

가짜 계정 엔진 봉 단위 3분(KRW-ZRO minute3). 개발 서버는 `_serve()` 를 쓰지 않아 `prefetch_loop` 가 돌지 않으므로(그대로면 `prefetch_targets` 가 비어 1분 폴백) 저장소 밖 감싸기 스크립트로 `make_app` 뒤 `prefetch_targets = _targets()` 를 채워 3분 조건을 만들었다(서버 `prefetch_loop` 첫 줄과 같음). 1분 폴백은 개발 서버 그대로(Task 9 와 같은 방식).

| 조건 | 1회째 단추→요약 | 2회째 | 업비트 429 | 비고 |
|---|---|---|---|---|
| 3분 단위, 창 안 만남 (10:55:27~10:56:24) | **57.2초**(데이터 56.8·계산 0.14) | 0.51초, requests 0 | 0 | 운 좋게 3분 경계를 안 지남 |
| 3분 단위, 창 1번 만남 (위상 맞춰 시작, 경계 약 40초 전 누름) | **81.3초**(데이터 81.2·계산 0.10) | 0.51초, requests 0 | 0 | 146회 뒤 약 22초 멈춤(진행률 146/216 에서 그대로) |
| 1분 폴백 (대상 없음) | **93.7초**(데이터 93.3) | 0.51초, requests 0 | 0 | 60초마다 22초 막힘 |

- 이전(Task 9·최종 검수 수정, 5회/초 상한·창 없음): 54.0초·54.2초. 상한 4회/초만으로는 +3초(응답 지연에 이미 묶여 있었음), 늘어난 대부분은 창 대기다.
- **3분 단위에서 1회째가 창을 만날 확률 ≈ (57+22)/180 ≈ 44% — 그때 약 81초로 75초(결정 1027-05 때 사용자가 본 숫자)를 넘는다.** 1분 폴백이면 늘 약 90초대다.
- 차트 창 2개의 브라우저 업비트 조회 모두 200, 429 0. 콘솔 오류 0. 개발 서버 로그 `[V2-CANDLES]` 0줄.
- 증거: `.superpowers/sdd/plan-proposal-match-20261026/evidence/t40b-*`(측정 JSON·요약·stderr·개발 서버 로그 3개 — 입장 토큰 가림, 시험 출력), 스크립트 `evidence/scripts/t40b-*`, 캡처 `shots/t40b-step5-run1.png`·`run2.png`(마지막 측정으로 덮임).

### 체감 (투자자·운영자)
- 1분 폴백(미리 받기 대상 없음·params 못 읽음 — `_targets()` 조건)은 60초마다 22초를 막아, 다른 종목 첫 실행이 늘 창을 만난다(로컬 93.7초). *(Task 4-0b fix round 1 로 대체: 창 기준 = `.engine_alive.json` running 사용자 전원의 봉 단위(`self.window_units`), 못 읽으면 1분. `prefetch_targets` 는 정리 보호용)* 실측(57.2·81.3·93.7초)은 fix round 1 전 코드로 쟀다 — 창 계산식은 같아 수치 차이는 없다고 본다(측정 때 대상 집합을 감싸기로 채움).
- 처리기 안 2회 요청 경로(엔진 종목 보관분 + 새 봉)도 창 대기에 걸리면 응답이 최대 약 22초 늦어질 수 있다(nginx 60초 안). 보관분만으로 답하는 경우(업비트 0회)는 바로 200.
- 미리 받기가 창에서 기다리는 동안 사용자 요청이 오면 미리 받기를 멈추고 끝나기를 기다리므로(`serve` 의 `job.stop`·`await job.task`), 그 응답도 최대 약 22초 + 요청 1회(최대 10초) 늦어질 수 있다(nginx 60초 안, verifier 2026-10-27).
- 알려진 한계: 창 경계는 UTC 에포크 기준이라 240분봉 엔진이면 엔진 경계(KST, `_IV_MIN` 에 minute240 없음)와 맞지 않는다. 1·3·5·15·60분은 맞는다. 지금 서버 엔진은 3분(verifier 2026-10-27).
- 5절 투자자 통보 문안 A″ 는 1027-10 뒤 배포 요청서에서 「1분~1분 30초 정도」로 고쳤다. 서버 엔진이 3분봉이면 57~81초라 범위 안이고, 1분 폴백(93.7초)이면 조금 넘는다 — 요청서 2-4 서버 체감 측정값으로 다시 맞춘다.

### fix round 1 (리뷰 뒤)
- 창 기준 봉 단위를 정리용 `prefetch_targets` 와 분리해 `window_units` 로 둔다: 엔진 생존 파일 `running` 이 True 인 **실행 중 엔진 전원**(허용 목록과 무관)의 활성 전략 봉 단위. 파일 없음·깨짐·비었음·어느 사용자 몫을 못 읽음 → 그 몫 1분, 갱신 예외 → {1}. prefetch_loop 첫 반복 전·매 회·엔진 pid 변경 때만 갱신(요청마다 읽지 않음). 이전에는 `_targets()` 가 실패하면 직전 값이 남아 1분 폴백이 안 됐다.
- 운영자 해제(정지 파일 삭제 + 재시작) 뒤에도 `.cooldown.json` 의 24시간 셈은 유지된다(해제 뒤 24시간 안 429 1회면 바로 다시 정지) — spec D8 에 적고 시험으로 고정. 처리기 안 ≤2회 요청이 창 안에서 창 끝까지 기다린 뒤 부르는 시험 추가.
