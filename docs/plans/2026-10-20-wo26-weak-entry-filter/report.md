# WO-26 약매수 차단 필터 — 1단계 측정 보고 (읽기 전용, 코드 무변경)

- 작성: 2026-10-20 16:xx KST
- 범위: KRW-JTO, 측정 창 2026-09-20 00:00 ~ 2026-10-20 16:00 (형성 중 봉 제외)
- 서버: journal·DB(`mode=ro`)만 읽음. 코드·DB·설정 변경 없음. 로컬 실행은 `env -i` + 더미 키 + `python3 -I`.
- 근거 파일: `wo26_events.csv`(D/C·G/C 사건 88건), `wo26_gc_outcomes.csv`(G/C 44건 결과), `wo26_measure_out.txt`(측정 표준 출력), 스크립트 3개(`wo26m1_fetch.py`·`wo26m1_export.sh`·`wo26m1_measure.py`), `commands.txt`

---

## 0. 정지선과 지시 전제 대조

| 항목 | 로컬 | 서버 |
|---|---|---|
| HEAD | `97c5c1c` (docs 커밋 2건이 서버보다 앞섬, 코드 차이 없음) | `33a5d9e` |
| dashboard 버전 | v1.2026.10.06.1440 | v1.2026.10.06.1440 (pages/dashboard.py:495) |
| ExecMainStartTimestamp | — | 2026-10-06 14:45:06 KST |

**지시 전제와 실제 운영이 다름 (측정 구간을 실제 운영 기준으로 나눔)**

지시는 "EMA 60/200, 봉 간격 변경 10-03 21:03 전후 2구간"이었다. 그런데 `settings_history` 의 `strategy_init` 행을 보면 측정 창 안에서 설정이 4번 바뀌었다.

| 구간 | 봉 간격 | EMA (매수=매도) | 기간 (KST) | 근거 |
|---|---|---|---|---|
| S1 | minute5 | 60/200 | ~ 10-03 21:03:47 | settings_history id 167~186 |
| S2 | minute1 | 60/200 | 10-03 21:03:47 ~ 10-14 18:31:28 | id 188 (strategy_init) |
| S3 | minute3 | 60/200 | 10-14 18:31:28 ~ 10-20 02:46:15 | id 201·203 |
| S4 | minute3 | **20/200** | 10-20 02:46:15 ~ | id 209·211 |

또 손절 % 는 조건 저장 시각(saved_at)에 hot reload 로 바로 반영된다. applied_at(재기동 시각)과 다르다. 09-30 11:15 매수는 −2.73% 에서 손절됐고(09-28 저장값 3%), 10-19 매수 2건은 −1.2%·−1.5% 에서 손절됐다(10-17 저장값 1%). 그래서 단순 모의의 손절 % 는 saved_at 기준으로 넣었다.

서버 루트의 `mcmax33_latest_params_EMA.json` 은 minute3·20/200 이고 ticker 가 `JTO` 로 적혀 있다. 이 보고는 이 파일 대신 settings_history 를 기준으로 삼았다.

---

## A. 측정

### A-1. 방법

- **봉**: Upbit 공개 캔들 API(키 불필요). 5분봉 5,216개, 3분봉 3,390개, 1분봉 32,198개. 무거래 봉은 Upbit 가 만들지 않으며 봇도 합성하지 않는다(core/rest_reconcile.py:28-32). 그래서 받은 봉을 그대로 썼다.
- **지표**: `core.indicator_state.IndicatorState` 를 live_loop 와 같은 인자로 만든다(engine/live_loop.py:730-743). 그 뒤 `seed_from_closes(처음 200봉, quiet=True)` 와 `update_incremental(봉마다)` 를 차례로 호출한다. 이 순서는 `seed_long_history` 내부와 같다(core/indicator_state.py:185-213). 각 구간은 시작 전 1,000봉으로 워밍업했다(200봉 SMA 시작 + 800봉 증분). 구간 시작 시점의 상태를 `seed_long_history(800봉)` 결과와 대조했고 차이는 0.01원 이내였다.
- **교차 판정**: `EmaStrategy.on_bar` 의 식을 그대로 썼다(core/strategy_incremental.py:917-930). G/C 는 매수 스냅샷(`get_snapshot(True)`)으로 판정한다(`prev_fast <= prev_slow and fast > slow`). D/C 는 매도 스냅샷(`get_snapshot(False)`)으로 판정한다(`prev_fast >= prev_slow and fast < slow`).
- **경과 시간**: G/C 봉 시각 − 직전 D/C 봉 시각(봉 시작 시각 기준). 직전 D/C 는 워밍업 구간에 있어도 인정한다. 구현안 B3 의 "워밍업 800봉에서 찾기"와 같은 범위다.
- **"매수했다면"**: 진입가는 G/C 봉 종가다.
  - 2시간 최고 수익률: 종가 기준(같은 봉 간격의 종가, 봇의 익절·수익 추적 판정과 같은 기준)과 고가 기준(1분봉 고가)을 모두 구했다.
  - 0.5%·1.5% 도달 여부: 2시간 안에 닿았는지를 위 두 기준으로 따졌다.
  - 다음 D/C 시점 수익률: 다음 D/C 봉 종가 기준이다. 같은 구간 안에 다음 D/C 가 없으면 공란이다.
  - **단순 모의**(익절 축소 효과를 보려고 추가): 봉 종가마다 손절(그 시각 손절 %), 익절 x%, D/C 순으로 확인하고 먼저 걸린 것으로 청산한다. 수익 추적 매도·정체 포지션 매도·수수료(왕복 0.1%)는 넣지 않았다.
- **봇 실매수**: `audit_trades` 의 `BUY EMA_GC` 중 `bar_time` 이 G/C 봉과 같은 행이다. 매도는 그 뒤 첫 `SELL`/`HTS_SELL` 행이다. 수익률은 `price / entry_price − 1` 이고, entry_price 는 앱 추가 매수가 섞이면 섞인 평균가다. 보유 시간은 매도 시각 − 매수 시각이다.
- **봇이 사지 않은 이유**: 해당 봉의 `audit_buy_eval` 과 audit_trades 기준 보유 구간으로 판정했다.

### A-2. 재현 검증

| 대조 | 결과 |
|---|---|
| journal `Bar#` 로그(ema_fast·ema_slow 소수 2자리, 허용 0.03원) S2 1분봉 | **10,695 / 10,695 일치** |
| S4 3분봉 20/200 | **193 / 193 일치** |
| S3 3분봉 60/200 | 1,947 / 1,971 (불일치 24봉은 10-17 09:03~10:24 에 몰려 있고 10:27 부터 다시 일치. 그 사이 교차 없음. 원인 미조사) |
| S1 5분봉 (journal 은 09-30 20:29 부터만 남아 있음) | 554 / 928 (불일치는 전부 09-30 09:00~10-01 20:05. **10-01 20:11 WO-17 (S) 배포 뒤 불일치 0**. 배포 전에는 200봉 SMA 시드라 봇 값이 장기 기준과 달랐던 것으로 WO-17 G4 측정과 같다) |
| 봇 실매수 G/C 봉 (측정 창 24건 + BUY_REJECTED 3건) | 26 / 27 같은 봉. 남은 1건(#1165, 10-01)은 봇 교차가 14:10 봉, 장기 기준 교차가 13:45 봉이다(200봉 SMA 시드 시절, 위와 같은 원인). 결과 표에는 "BUY(시드 차이)"로 붙였다 |

### A-3. 경과 시간 구간별 G/C 건수

| 구간 | ≤0.5h | 0.5~1h | 1~2h | 2~3h | 3~6h | >6h | 계 |
|---|---|---|---|---|---|---|---|
| S1 5분봉 60/200 | 1 | 1 | 0 | 0 | 3 | 7 | 12 |
| S2 1분봉 60/200 | 2 | 1 | 3 | 4 | 6 | 8 | 24 |
| S3 3분봉 60/200 | 1 | 0 | 1 | 0 | 0 | 3 | 5 |
| S4 3분봉 20/200 | 0 | 1 | 1 | 1 | 0 | 0 | 3 |
| **전체** | **4** | **3** | **5** | **5** | **9** | **18** | **44** |

**2시간 이내 G/C 는 44건 중 12건(27%)이다.** 1분봉 구간은 하루 2.2건으로 5분봉 구간(하루 0.9건)보다 교차가 잦았다.

### A-4. G/C 별 결과 (44건)

표기: 경과 h = 직전 D/C 로부터의 시간. 2h최고 = 2시간 안 최고 수익률 %(종가 / 고가). 도달 = 2시간 안 종가 기준 0.5% / 1.5% 도달(1=도달). 다음DC = 다음 D/C 봉 종가 수익률 %. 모의 = 단순 모의(익절 0.5%)의 청산 사유와 수익률 %. 봇 = 실매수 결과 또는 사지 않은 이유.

| 구간 | G/C | 직전 D/C | 경과 h | 2h최고 종가/고가 | 도달 .5/1.5 | 다음DC | 모의(TP0.5) | 봇 |
|---|---|---|---|---|---|---|---|---|
| S1 | 09-21 17:55 | 09-21 13:25 | 4.50 | 1.445 / 1.590 | 1/0 | −1.734 | TP +0.578 | 급등 차단 필터 |
| S1 | 09-23 02:55 | 09-22 15:25 | 11.50 | 0.710 / 0.994 | 1/0 | −2.557 | TP +0.710 | 급등 차단 필터 |
| S1 | 09-24 23:10 | 09-23 14:35 | 32.58 | 2.905 / 3.211 | 1/1 | +25.076 | TP +0.917 | 봇 미가동(워밍업 재생 평가) |
| S1 | 09-29 19:20 | 09-28 00:40 | 42.67 | 0.913 / 0.913 | 1/0 | −2.086 | TP +0.522 | #1156 EMA_DC −1.434% · 713분 |
| S1 | 09-30 05:45 | 09-30 01:05 | 4.67 | 0.394 / 0.394 | 0/0 | −0.788 | DC −0.788 | 포지션 보유 |
| S1 | 09-30 11:15 | 09-30 07:15 | 4.00 | 0.260 / 0.260 | 0/0 | −3.117 | SL −3.117 | #1160 STOP_LOSS −2.731% · 260분 |
| S1 | 09-30 21:55 | 09-30 15:45 | 6.17 | 0.259 / 0.388 | 0/0 | −3.881 | SL −0.906 | 포지션 보유 |
| S1 | 10-01 13:45 | 09-30 23:35 | 14.17 | −0.133 / 0.000 | 0/0 | −3.050 | SL −1.061 | #1165(시드 차이, 14:10) STOP_LOSS −0.935% · 78분 |
| S1 | **10-01 18:30** | 10-01 17:40 | **0.83** | −0.405 / −0.270 | 0/0 | −1.080 | SL −1.080 | 봇 미가동(워밍업 재생 평가) |
| S1 | 10-02 03:35 | 10-01 18:55 | 8.67 | −0.535 / 0.000 | 0/0 | −2.276 | SL −1.205 | #1171 STOP_LOSS −1.071% · 15분 |
| S1 | **10-02 07:55** | 10-02 07:45 | **0.17** | 1.771 / 1.771 | 1/1 | +0.817 | TP +0.545 | #1174 TRAILING_STOP_FIXED +0.817% · 90분 |
| S1 | 10-03 19:25 | 10-03 01:20 | 18.08 | 0.410 / 0.821 | 0/0 | — | 구간 끝 | 포지션 보유 |
| S2 | 10-04 14:15 | 10-04 06:43 | 7.53 | 1.704 / 1.835 | 1/1 | 0.000 | TP +0.524 | 평가 통과·주문 기록 없음(WO-25 전) |
| S2 | **10-04 17:01** | 10-04 17:00 | **0.02** | 0.391 / 0.651 | 0/0 | −1.042 | SL −1.042 | #1192 STOP_LOSS −1.172% · 55분 |
| S2 | 10-04 23:04 | 10-04 17:56 | 5.13 | 1.445 / 1.577 | 1/0 | +0.526 | TP +0.526 | #1196 TRAILING_STOP_FIXED +1.051% · 40분 |
| S2 | **10-05 08:24** | 10-05 06:39 | **1.75** | 0.644 / 0.772 | 1/0 | −1.544 | TP +0.515 | #1198 STOP_LOSS −1.544% · 152분 |
| S2 | 10-05 15:04 | 10-05 10:36 | 4.47 | 0.896 / 1.024 | 1/0 | +0.256 | TP +0.896 | 급등 차단 필터 |
| S2 | 10-06 05:36 | 10-05 21:40 | 7.93 | 1.284 / 1.284 | 1/0 | −0.642 | TP +0.899 | 평가 통과·주문 기록 없음(WO-25 전) |
| S2 | 10-06 17:09 | 10-06 10:11 | 6.97 | 0.641 / 0.641 | 1/0 | −1.795 | TP +0.641 | #1217 BUY_REJECTED(KRW 부족) |
| S2 | 10-06 20:39 | 10-06 18:23 | 2.27 | 2.972 / 2.972 | 1/1 | +0.775 | TP +0.517 | #1218 BUY_REJECTED(KRW 부족) |
| S2 | 10-07 15:40 | 10-07 01:10 | 14.50 | 0.551 / 0.551 | 1/0 | −1.791 | TP +0.551 | #1233 BUY_REJECTED(KRW 부족) |
| S2 | 10-08 03:26 | 10-07 17:28 | 9.97 | 2.882 / 2.882 | 1/1 | +9.222 | TP +0.720 | 급등 차단 필터 |
| S2 | **10-08 15:54** | 10-08 15:31 | **0.38** | 2.320 / 2.320 | 1/1 | −0.644 | SL −1.031 | 급등 차단 필터 |
| S2 | 10-09 07:18 | 10-08 19:26 | 11.87 | −0.140 / −0.140 | 0/0 | −1.404 | SL −1.124 | #1237 STOP_LOSS −1.125% · 12분 |
| S2 | 10-09 10:26 | 10-09 08:01 | 2.42 | 3.536 / 3.536 | 1/1 | +0.990 | TP +1.132 | #1239 TRAILING_STOP_FIXED +0.424% · 18분 |
| S2 | 10-10 06:34 | 10-09 17:40 | 12.90 | 0.853 / 0.853 | 1/0 | +0.284 | TP +0.569 | #1243 STALE_POSITION +0.569% · 63분 |
| S2 | **10-10 13:40** | 10-10 12:37 | **1.05** | 1.257 / 1.257 | 1/0 | −0.698 | TP +0.698 | #1256 STALE_POSITION +0.838% · 62분 |
| S2 | 10-10 21:02 | 10-10 17:06 | 3.93 | 2.235 / 2.235 | 1/1 | +3.631 | TP +0.698 | #1260 TRAILING_STOP_FIXED +0.698% · 59분 |
| S2 | 10-11 15:03 | 10-11 12:37 | 2.43 | 1.198 / 1.198 | 1/0 | −0.533 | TP +0.533 | #1266 TRAILING_STOP_FIXED +0.800% · 44분 (앱 추가 1) |
| S2 | 10-11 22:12 | 10-11 19:00 | 3.20 | 0.532 / 0.532 | 1/0 | +0.532 | TP +0.532 | #1269 STALE_POSITION −0.454% · 62분 |
| S2 | **10-12 06:53** | 10-12 06:21 | **0.53** | 0.000 / 0.000 | 0/0 | −0.907 | SL −1.036 | #1271 STOP_LOSS −0.907% · 9분 |
| S2 | 10-12 12:07 | 10-12 09:50 | 2.28 | 2.338 / 2.338 | 1/1 | 0.000 | TP +0.649 | #1273 TRAILING_STOP_FIXED +1.688% · 46분 |
| S2 | **10-12 16:37** | 10-12 15:13 | **1.40** | −0.129 / −0.129 | 0/0 | −1.414 | SL −1.028 | 포지션 보유 |
| S2 | 10-13 11:20 | 10-12 17:22 | 17.97 | 3.438 / 3.438 | 1/1 | +2.436 | TP +0.573 | #1279 STALE_POSITION +0.858% · 62분 (앱 추가 1) |
| S2 | 10-13 22:20 | 10-13 18:56 | 3.40 | 2.770 / 2.770 | 1/1 | +0.554 | TP +0.693 | 급등 차단 필터 |
| S2 | 10-14 11:45 | 10-14 07:28 | 4.28 | 0.409 / 0.409 | 0/0 | −1.226 | SL −1.090 | #1291 STALE_POSITION −0.681% · 61분 (앱 추가 1) |
| S3 | 10-16 00:54 | 10-14 14:18 | 34.60 | 1.570 / 1.727 | 1/1 | +0.157 | TP +0.785 | 급등 차단 필터 |
| S3 | 10-17 13:15 | 10-17 00:33 | 12.70 | 1.258 / 1.258 | 1/0 | −0.314 | DC −0.314 | 포지션 보유 |
| S3 | **10-17 13:24** | 10-17 13:21 | **0.05** | 1.099 / 1.099 | 1/0 | −0.785 | TP +0.785 | 포지션 보유 |
| S3 | 10-19 10:12 | 10-17 16:54 | 41.30 | 0.667 / 0.667 | 1/0 | −1.167 | TP +0.500 | #1323 STOP_LOSS −1.167% · 228분 |
| S3 | **10-19 21:36** | 10-19 20:06 | **1.50** | 0.499 / 0.499 | 0/0 | — | SL −1.165 | #1325 STOP_LOSS −1.498% · 84분 |
| S4 | **10-20 04:36** | 10-20 03:06 | **1.50** | 0.000 / 0.000 | 0/0 | −0.998 | SL −1.165 | #1327 STOP_LOSS −0.998% · 14분 |
| S4 | 10-20 07:09 | 10-20 04:57 | 2.20 | 0.165 / 0.331 | 0/0 | −1.818 | SL −0.826 | #1329 STOP_LOSS −0.828% · 57분 |
| S4 | **10-20 10:45** | 10-20 10:09 | **0.60** | 2.156 / 2.156 | 1/1 | — | SL −0.829 | #1331 STOP_LOSS −0.663% · 12분 |

굵은 글씨는 2시간 이내 G/C(12건)다. 봇이 사지 않은 G/C 의 사유는 급등 차단 필터 7건, 포지션 보유 6건(워밍업 재생 평가가 겹친 3건 포함), 봇 미가동(워밍업 재생 평가) 2건, 평가 통과 후 주문 기록 없음 2건(WO-25 전), BUY_REJECTED 3건이다.

### A-5. 결론 표 — 2시간 안 G/C vs 2시간 밖 G/C

수익률은 %다. "매수했다면" 지표는 44건 모두에 대해 같은 기준으로 계산했다(봇이 실제로 산 G/C 포함, 비교의 일관성을 위해).

| 지표 | **≤2h (12건)** | >2h (32건) |
|---|---|---|
| 2시간 최고 수익률(종가) 평균 / 중앙 | **+0.80 / +0.57** | +1.25 / +0.91 |
| 2시간 최고 수익률(고가) 평균 / 중앙 | +0.84 / +0.71 | +1.33 / +1.01 |
| 0.5% 도달 비율 (종가 / 고가) | **50% (6/12) / 58% (7/12)** | 72% (23/32) / 75% (24/32) |
| 1.5% 도달 비율 (종가 / 고가) | **25% (3/12) / 25% (3/12)** | 31% (10/32) / 38% (12/32) |
| 다음 D/C 시점 수익률 평균 / 중앙 | **−0.83 / −0.95** (10건) | +0.46 / −0.53 (31건) |
| 단순 모의 익절 0.5% 평균 / 중앙 · 이익 건수 | **−0.49 / −1.03 · 4/12** | +0.14 / +0.53 · 22/31 |
| 봇 실매수 평균 / 중앙 · 이익 건수 | **−0.64 / −0.95 · 2/8** (합 −5.13%p) | −0.27 / −0.57 · 6/16 |

**익절 % 별 단순 모의 (손절 → 익절 → D/C, 봉 종가, 수수료 제외). "매수 안 함" = 0**

| | TP 0.3% | TP 0.5% | TP 1.0% | TP 1.5% |
|---|---|---|---|---|
| ≤2h 평균 (합, 이익 건수) | −0.31 (−3.76, 6/12) | −0.49 (−5.83, 4/12) | −0.45 (−5.41, 3/12) | −0.80 (−9.56, 1/12) |
| >2h 평균 (합, 이익 건수) | +0.12 (+3.83, 25/32) | +0.14 (+4.23, 22/31) | −0.06 (−1.69, 15/31) | +0.14 (+4.28, 14/31) |

**기준 시간 민감도 (이내 그룹 / 밖 그룹, 단순 모의 TP0.5 평균 · 봇 실매수 평균)**

| 기준 | 이내 건수 | 이내 모의 / 봇 | 밖 모의 / 봇 |
|---|---|---|---|
| 0.5h | 4 | −0.19 / −0.18 | −0.02 / −0.41 |
| 1h | 7 | −0.53 / −0.48 | +0.06 / −0.38 |
| **2h** | **12** | **−0.49 / −0.64** | **+0.14 / −0.27** |
| 3h | 17 | −0.23 / −0.25 | +0.09 / −0.54 |
| 6h | 26 | −0.19 / −0.30 | +0.19 / −0.62 |

경과 구간별로 보면 0.5~1h(3건)와 1~2h(5건)가 가장 나쁘다(모의 평균 −0.98·−0.43, 봇 −0.79·−0.80). 2~3h(5건)는 오히려 가장 좋다(모의 +0.40, 봇 +0.52, 1.5% 도달 3/5). ≤0.5h(4건)는 2시간 최고가 크지만(종가 평균 +1.40) 손절에 먼저 걸리는 경우가 섞여 모의 −0.19 다.

### A-6. 판단 — 기본값 2시간·0.5% 가 적절한가

**2시간은 기준으로 적절하다. 0.5% 익절 축소는 약매수를 이익으로 바꾸지 못했다. 이 표본에서는 "매수 안 함"이 가장 나았다.**

근거는 다음과 같다.
- 2시간 안 G/C 12건은 모든 지표에서 2시간 밖 32건보다 약했다. 0.5% 도달 50% 대 72%, 다음 D/C 수익률 −0.83 대 +0.46, 봇 실매수 −0.64(2/8 이익) 대 −0.27이다.
- 기준을 3시간으로 늘리면 가장 좋았던 2~3h 묶음(5건)까지 막는다. 1시간으로 줄이면 나빴던 1~2h 묶음(5건, 봇 4건 중 3건 손절)을 놓친다. 그래서 2시간이 경계로 가장 맞았다.
- 익절을 0.5%로 줄여도 약매수 12건 중 손절이 먼저 온 경우가 8건이었다. 모의 평균은 −0.49% 다. 0.3~1.5% 어느 값도 평균이 음수였고(0.3% 가 −0.31 로 가장 덜 나쁨), 수수료 0.1% 를 빼면 더 나빠진다.
- 손절 폭(0.5~3%, 측정 기간 대부분 1%)이 익절 0.5% 보다 커서 본전에 필요한 승률은 약 67% 다. 실제 0.5% 선도달 승률은 33% 였다.

권고는 두 가지다.
1. 기본 시간 2시간은 그대로 둔다.
2. 처리 방식의 기본값은 PRD 안("익절 기준 축소")보다 **"매수 안 함"을 권한다.** 익절 축소는 선택지로 두고 기본 0.5% 를 유지한다. 0.3% 는 600원대 가격에서 약 2원이며 수수료를 빼면 순익 0.2% 라 기본값으로 권하지 않는다.

다만 표본이 12건(봇 실매수 8건)뿐이다. 그 사이 봉 간격이 세 번, 손절 %가 여러 번 바뀌었고, 모의는 수익 추적 매도·정체 포지션 매도를 뺀 단순화다. 그래서 위 결론은 "방향"으로 보고 배포 뒤 감사 로그(약매수 차단·약매수 진입 표시)로 계속 집계하기를 권한다.

---

## B. 설계 확인 (코드 인용)

### B-1. 매수 필터 호출부와 BaseFilter

**호출부** core/strategy_incremental.py:936-952

```python
            # ✅ 매수 필터 체크 (Surge Filter 등)
            # ⚠️ 중요: Base EMA GAP 전략은 급락 매수 전략이므로 필터 미적용
            if not self.enable_base_ema_gap:
                filter_result = self.buy_filter_manager.evaluate_all(
                    bar=bar,
                    ema_slow=ema_slow
                )
                # ✅ 필터 결과 저장 (감사로그에서 사용)
                self.last_buy_filter_result = filter_result

                if filter_result is not None and filter_result.should_block:
                    # 필터가 매수 차단
                    return Action.HOLD
```

- 교차 판정(core/strategy_incremental.py:917-930)보다 뒤에 있다. 하지만 **G/C 확인(core/strategy_incremental.py:1021-1024)보다 앞에서 매 봉** 실행된다. 그래서 급등 차단은 G/C 가 없는 봉에도 `SURGE_FILTER` 를 남긴다(측정 기간 audit_buy_eval 1,682행).
- 필터 등록: core/strategy_incremental.py:718-722 `_register_buy_filters` (SlowEmaSurgeFilter 하나).
- 관리자: core/filters/__init__.py:28-52 `BuyFilterManager.evaluate_all(**kwargs)`. 차단 필터가 있으면 그 FilterResult 를, 모두 통과하면 `None` 을 반환한다. **통과 결과의 metadata 는 버려진다.**
- 감사 로그 연결: core/strategy_engine.py:1882-1883·1919-1920 에서 `strategy.last_buy_filter_result` 를 읽는다.

**BaseFilter** core/filters/base.py:17-65

```python
@dataclass
class FilterResult:
    should_block: bool           # True면 매수/매도 차단
    reason: str                  # 차단 사유 (예: "STALE_POSITION", "SURGE_FILTER")
    details: Optional[str] = None  # 상세 정보 (로깅용)
    metadata: Optional[Dict[str, Any]] = None  # 추가 메타데이터

class BaseFilter(ABC):
    def __init__(self, category: FilterCategory):
        self.category = category
        self.enabled = False
    @abstractmethod
    def evaluate(self, **kwargs) -> FilterResult: ...
    @abstractmethod
    def get_name(self) -> str: ...
```

예시 구현: core/filters/buy_filters.py:13-84 `SlowEmaSurgeFilter` (`FilterCategory.BUY_FILTER`, kwargs `bar`·`ema_slow`).

**새 필터 `WeakEntryFilter` 가 받아야 할 인자**

| kwargs | 값 | 출처 |
|---|---|---|
| `bar_ts` | 현재 봉 시각 (`bar.ts`, UTC tz-aware) | on_bar 의 `bar` |
| `last_dead_cross_ts` | 마지막 D/C 봉 시각 (UTC tz-aware 또는 None) | 지표 스냅샷의 새 키 (B-3) |
| `golden_cross` | 이 봉의 G/C 여부 | core/strategy_incremental.py:917 `ema_golden_cross` |
| (생성자) `window_hours`, `mode` ("block" / "reduce_tp"), `weak_tp_pct` | 설정값 | buy_conditions (B-5) |

반환은 다음과 같이 제안한다.
- 약매수가 아니면 `should_block=False, reason="WEAK_OK"` 다.
- 약매수이고 mode=block 이면 `should_block=True, reason="WEAK_ENTRY_BLOCK"` 다. details 는 "약매수 차단 (D/C 뒤 n분, 기준 2시간)", metadata 는 `{elapsed_min, window_h}` 다.
- 약매수이고 mode=reduce_tp 이면 `should_block=False, reason="WEAK_ENTRY"` 다. metadata 는 `{elapsed_min, weak_tp_pct}` 다.

**배치 제안 (최소 변경)**: 급등 차단과 같이 `BuyFilterManager` 에 넣으면 두 가지 문제가 생긴다. (1) G/C 가 없는 봉에도 D/C 뒤 2시간 내내 차단 기록이 남는다. (2) 익절 축소 모드의 metadata 가 `evaluate_all` 에서 버려진다. 그래서 `WeakEntryFilter` 클래스는 core/filters/buy_filters.py 에 두되, **호출은 G/C 를 포함한 모든 매수 조건을 통과한 직후, `return Action.BUY` 직전(core/strategy_incremental.py:1048 "모든 조건 통과 시 매수" 앞)에서 직접** 한다.
- block 이면 `self.last_buy_filter_result = result` 로 두고 `return Action.HOLD` 한다. 감사 로그 경로는 급등 차단과 같다.
- reduce_tp 이면 `self.last_weak_entry = result.metadata` 를 남기고 BUY 한다. 엔진이 B-4 에서 주문 meta 에 옮긴다.
- 약매수가 아니면 `self.last_weak_entry = None` 이다.

이렇게 하면 `BuyFilterManager` 의미는 바뀌지 않고, 급등 차단이 먼저 막는 순서도 그대로다.

### B-2. 익절·수익 추적 매도의 take_profit_pct 읽는 곳과 덮어쓰기 지점

| 위치 | 코드 |
|---|---|
| TakeProfitFilter 생성 | core/filters/sell_filters.py:133-139 `self.take_profit_pct = take_profit_pct` |
| TakeProfitFilter 판정 | core/filters/sell_filters.py:187 `take_profit_triggered = pnl_pct >= self.take_profit_pct` (로그·metadata 194·200·205·208) |
| TrailingStopFilter 생성 | core/filters/sell_filters.py:227·237 `self.take_profit_pct = take_profit_pct` |
| TrailingStopFilter 무장 | core/filters/sell_filters.py:271 `if pnl_pct is not None and pnl_pct >= self.take_profit_pct:` (`advance_state`, 실시간 evaluate 와 재시작 재계산 공용) |
| 재시작 재계산 | core/trailing_restore.py:95 `ts_filter.advance_state(position, close, log=False)` — 같은 함수를 쓴다 |
| 값 주입 | core/strategy_incremental.py:741-747 (TS `take_profit_pct=self.trailing_stop_activation_pct`), 749-751 (TP `take_profit_pct=self.take_profit`). hot reload 는 core/strategy_incremental.py:879-883 에서 필터를 다시 만든다 |
| 판정 호출 | core/strategy_incremental.py:1261-1269 `sell_filter_manager.evaluate_all(position=position, current_price=..., ...)` |

**최소 변경 제안**: 필터 인스턴스는 전략에 하나뿐이고 hot reload 때 다시 만들어진다. 그래서 덮어쓰기 값은 필터가 아니라 **포지션에 둔다.**

1. `PositionState` 에 `take_profit_override: Optional[float] = None` 을 추가한다(core/position_state.py:44-55 근처, `trailing_*` 옆). `close_position` 에서 None 으로 지운다(core/position_state.py:286-312, `_clear_hts_flag` 와 같은 자리).
2. 두 판정 지점에서 실효 기준을 구하는 한 줄을 넣는다.
   ```python
   tp = position.take_profit_override if position.take_profit_override is not None else self.take_profit_pct
   ```
   - core/filters/sell_filters.py:187 (TP) → `pnl_pct >= tp`, 로그·metadata 도 `tp` 로 바꾼다.
   - core/filters/sell_filters.py:271 (TS 무장) → `pnl_pct >= tp`.
   - `advance_state` 한 곳만 바꾸면 실시간과 재시작 재계산(core/trailing_restore.py:95)이 함께 따라간다.
3. **주의: `apply_entry` 는 덮어쓰기 값을 건드리지 않는다.** 대신 진입 경로마다 apply_entry 뒤에 값을 설정하거나 복원한다(B-4). apply_entry 가 지우게 하면 boot_seed·wallet_sync 복원 순서가 꼬인다.
4. PRD 4.3 대로 고정폭은 그대로 둔다. 고정폭은 core/filters/sell_filters.py:277-279 의 `(현재가 − 평균가) × 30%` 로 계산되므로 0.5% 에서 무장하면 약 1호가가 된다.

### B-3. 워밍업 재생에서 마지막 D/C 시각을 함께 구하는 지점

**워밍업 시드** engine/live_loop.py:203-221 `_seed_warmup_indicators`

```python
    closes = initial_df["Close"].tolist()
    if len(closes) >= long_bars:
        if indicators.seed_long_history(closes[-long_bars:], base_len=min_hist):
            return True, "long_history", "", initial_df.iloc[-min_hist:]
```
호출부: engine/live_loop.py:1146-1148. 그 뒤 버퍼 채우기 루프(engine/live_loop.py:1186-1199)는 최근 min_hist(200)봉만 돌고 지표를 갱신하지 않는다(`record_warmup_log` 만 한다). **따라서 800봉 재생은 `seed_long_history` 안에서만 일어난다.**

**긴 이력 시드** core/indicator_state.py:185-213

```python
        if not self.seed_from_closes(closes[:base_len], quiet=True):
            return False
        for c in closes[base_len:]:
            self.update_incremental(c)
        self.prev_macd = None
        ...
```

**실시간 증분 지점** core/strategy_engine.py:776 (일반 봉), 913·925·930 (REST 실패·Reconcile 변경·변경 없음), 모두 `self.indicators.update_incremental(bar.close)`.

**제안 (한 곳에서 처리)**
1. `IndicatorState.update_incremental(close, ts=None)` 에 선택 인자 `ts` 를 추가한다. 갱신 뒤 **매도 쌍** 기준 D/C(`prev_ema_fast_sell >= prev_ema_slow_sell and ema_fast_sell < ema_slow_sell`, use_separate_ema=False 면 공통 쌍)이면 `self.last_dead_cross_ts = ts` 로 둔다. 매도 쌍인 이유는 봇이 D/C 로 매도할 때 쓰는 쌍이기 때문이다(get_snapshot(False), core/indicator_state.py:281-284). 매수·매도 기간이 다르게 설정되면 어느 쌍을 쓸지 확인이 필요하다(현재는 같음).
2. `seed_long_history(closes, base_len=200, timestamps=None)` 에도 선택 인자를 추가해 루프에서 `update_incremental(c, ts)` 로 넘긴다. 마지막의 `prev_* = None` 초기화는 그대로 두되 **`last_dead_cross_ts` 는 지우지 않는다.** `_seed_warmup_indicators` 는 `initial_df.index[-long_bars:]` 를 넘긴다. 200봉 SMA 폴백이면 `last_dead_cross_ts=None` 이 되고 "직전 D/C 알 수 없음 = 일반 매수"로 처리한다. 이 사실을 `[WARMUP]` 로그 1줄에 함께 남긴다.
3. 엔진 4곳은 `update_incremental(bar.close, bar.ts)` 로 바꾼다.
4. `get_snapshot` 반환에 `"last_dead_cross_ts"` 를 추가하면 on_bar 의 `indicators` 로 전달된다(core/strategy_incremental.py:910-914 에서 읽음).
5. **BACKFILL(Issue #11)**: 지표 백업 dict(engine/live_loop.py:1383~)와 복원(engine/live_loop.py:1488-1509)에 `last_dead_cross_ts` 를 함께 넣는다. 그렇지 않으면 재평가 중 D/C 가 기록돼 약매수 판정이 오염된다.

측정 근거로 800봉의 시간 길이를 보면 1분봉 13.3시간, 3분봉 40시간, 5분봉 66.7시간으로 모두 최대 설정 6시간보다 길다. 구간 시작 시점 800봉 시드는 1,000봉 시드와 0.01원 이내로 같았다(A-2).

### B-4. 약매수 표식·익절 덮어쓰기의 기록과 복원 경로

**쓰기**
- 주문 기록 `orders.meta`: 봇 매수 meta 를 만드는 곳은 core/strategy_engine.py:1413-1421 `_execute_buy` 의 `meta = {"bar", "reason", "bar_time", ...}` 다. 여기에 `meta["weak_entry"] = {"tp": 0.005, "elapsed_min": n, "window_h": 2}` 를 더한다(`strategy.last_weak_entry` 가 있을 때만). 이 meta 는 trader 에서 `insert_order(..., meta=meta_json)` 으로 저장된다(core/trader.py:831 "전략 컨텍스트 저장"). 고정가(지정가) 매수와 미체결 시장가 전환(core/strategy_engine.py:197 `conv_meta = {**(meta or {}), ...}`)도 같은 meta 를 물려받는다.
- 포지션 기록 `account_positions.meta`: `services/db.py:2793 update_position_meta` 로 쓴다. 기존 hts_buy 처럼 read-modify-write 로 `weak_entry` 키만 더하고 지운다(services/db.py:2837-2843·2858-2862 패턴).
- 포지션 메모리: 체결 확정 지점 3곳에서 `apply_entry` 뒤에 `position.take_profit_override = tp` 를 설정하고 account_positions.meta 를 쓴다.
  - 시장가: core/strategy_engine.py:1474 `open_position`
  - 지정가 체결: core/strategy_engine.py:430 `apply_entry(source="bot_limit_fill")`. uuid 로 orders.meta 를 읽는다(services/db.py:2131-2154 가 meta 반환).
  - 미체결 시장가 전환: core/strategy_engine.py:213 `apply_entry(... "bot_market_convert")`

**복원 (재시작·동기화)**
- 매 동기화마다 메타가 다시 읽힌다: core/position_state.py:193-195 `self.metadata = get_position_meta(self.trader.user_id, self.ticker)`.
- boot_seed: engine/live_loop.py:391-450 `_apply_boot_seed` 의 `apply_entry(source="boot_seed")`(431) 직후에 `position.metadata.get("weak_entry")` 를 읽어 `take_profit_override` 를 복원한다. 이 지점이 `restore_trailing_on_boot`(engine/live_loop.py:1217)보다 앞이므로 재시작 재계산도 축소 기준으로 무장한다.
- wallet_sync: core/strategy_engine.py:709-715 `apply_entry(source="wallet_sync")` 직후에 같은 복원을 한다.
- **유효성 확인**: 메타의 표식이 지금 포지션의 것인지 확인한다. `weak_entry.order_uuid`(또는 `bar_time`)가 `get_last_open_buy_order` 의 마지막 봇 BUY 와 같을 때만 복원한다(services/db.py:1835~). 맞지 않으면 표식을 지우고 WARNING 1줄을 남긴다.

**초기화 정책 (앱 추가 매수와 맞춤)**
- 현행 정책: 앱 추가 매수(HTS_BUY_ADD)로 평균가가 바뀌면 수익 추적 상태 전부를 리셋한다(core/strategy_engine.py:386-399, "HTS_BUY_ADD 로 avg 변경 → Trailing 상태 리셋").
- 같은 자리에서 `take_profit_override = None` 으로 하고 `account_positions.meta.weak_entry` 를 지운다. 섞인 평균가 포지션에는 축소 익절을 적용하지 않고 일반 기준으로 돌아간다. PRD 4.3 "앱에서 직접 사신 코인에는 적용되지 않습니다"와도 맞는다.
- 청산 시: `close_position`(core/position_state.py:286-312) → `_clear_hts_flag` 와 함께 `weak_entry` 도 지운다. 기동 정합 검사(services/db.py:2896~ "보유 0 인데 meta.hts_buy=true 인 행 정리")에 `weak_entry` 도 포함한다.
- 측정 기간 봇 G/C 매수 24건 중 3건(#1266·#1279·#1291)은 보유 중 앱 추가 매수가 있었다. 이 정책이 실제로 쓰이는 경우다.

### B-5. 설정 페이지 배치 (급등 차단 블록을 본뜸)

**본뜰 블록** pages/set_buy_sell_conditions.py:625-641

```python
        if strategy_tag == "EMA" and st.session_state.get("surge_filter_enabled", False):
            st.markdown("#### ⚙️ 급등 차단 필터 파라미터")
            st.caption("Slow EMA 대비 설정한 비율 이상 급등 시 매수를 차단합니다")
            surge_threshold_pct = st.number_input("급등 임계값 (%)", min_value=0.1, max_value=10.0, step=0.1, ...)
            st.session_state["surge_threshold_pct"] = surge_threshold_pct / 100.0
            st.info(f"🚫 현재 설정: Slow EMA 대비 **{surge_threshold_pct:.1f}%** 이상 상승 시 매수 차단")
```

**연결 지점 (같은 모양으로 추가)**

| 단계 | 기존 급등 차단 위치 | 약매수 추가 |
|---|---|---|
| 토글 목록 | pages/set_buy_sell_conditions.py:146-149 `EMA_BUY_FILTERS` | `"weak_entry_filter_enabled": "🐢 약매수 차단 필터 (D/C 직후 G/C 매수 제한)"` — 기존 토글 루프(607-612)가 그린다 |
| 불러오기 | 218 `surge_threshold_pct` 로드 | `weak_entry_window_hours`(2.0) · `weak_entry_mode`("block") · `weak_entry_tp_pct`(0.005) |
| 기본값 | 254 `setdefault("surge_threshold_pct", 0.01)` | 같은 3개 setdefault |
| 저장 | 276-277 (EMA + 켬일 때만 저장) | 같은 조건으로 3개 저장 |
| 요약 | 914-916 임계값 caption | "└─ 2시간 · 매수 안 함" / "└─ 2시간 · 익절 0.5%" |
| 엔진 반영 | core/strategy_incremental.py:648-654 (생성), 863-871 (hot reload) | 같은 2곳에 3개 키 |

**입력 배치 제안** (급등 차단 블록 바로 아래, `weak_entry_filter_enabled` 켬일 때만 표시)

```
#### ⚙️ 약매수 차단 필터 파라미터
캡션: 데드크로스 뒤 설정 시간 안에 난 골든크로스를 약매수로 봅니다
[ D/C 뒤 G/C 허용 시간 (시간) ]  number_input 0.0~6.0, step 0.5, 기본 2.0
( ) 매수 안 함   ( ) 익절 기준 축소           st.radio(horizontal=True)
[ 축소 익절 기준 (%) ]  number_input 0.3~1.5, step 0.1, 기본 0.5
                         — "익절 기준 축소"일 때만 표시(또는 disabled)
st.info: "🐢 현재 설정: D/C 뒤 2시간 안의 G/C → 매수 안 함"
         또는 "… → 익절 0.5% (수익 추적 매도도 0.5%에서 무장, 고정폭 약 1호가)"
시간 0 일 때 st.warning: "0시간은 필터를 끈 것과 같습니다"
```

UI 규칙(1-A·1-B단계)에 따라 이 블록은 기존 "🔍 매수 필터" expander(expanded=True, 605행) 안에 두고 새 접힘은 만들지 않는다. 화이트리스트 항목 이동도 없다. 처리 방식 기본값은 A-6 권고에 따라 "매수 안 함"을 제안하며, 투자자 확인 대상이다(PRD 8절 1번).

---

## C. 확인이 필요한 결정 (운영자)

1. 처리 방식 기본값: PRD 는 "익절 기준 축소", 측정 권고는 "매수 안 함"(A-6).
2. 매수·매도 EMA 기간이 다를 때 D/C 를 어느 쌍으로 볼지 (제안: 매도 쌍, B-3).
3. 200봉 SMA 폴백 기동처럼 직전 D/C 를 모를 때 일반 매수로 볼지 (제안: 일반 매수 + 로그).
4. 지시 전제(60/200, 2구간)와 실제 운영(4구간, 10-20 부터 20/200)이 달랐던 점. 20/200 구간은 3건뿐이라 별도 판단 근거가 되지 않는다.

## D. 이 보고의 한계

- 표본: 2시간 안 G/C 12건(봇 실매수 8건). 30일 안에 봉 간격 3종·손절 0.5~3% 가 섞여 있다.
- 단순 모의는 봉 종가 기준이고 수익 추적 매도·정체 포지션 매도·현재가 매수 미체결·수수료를 넣지 않았다.
- 구간 안 재기동(800봉 재시드)은 연속 계산으로 근사했다. 10-01 20:11 이전 기동은 200봉 SMA 시드라 봇의 실제 교차가 1건 25분 달랐다(#1165).
- S3 Bar# 불일치 24봉(10-17 09:03~10:24)의 원인은 조사하지 않았다. 교차 판정에는 영향이 없었다.
- 작업 중 셸 heredoc 1회 사용(빈 no-op, 무해) — 규칙 위반으로 commands.txt 에 기록.
