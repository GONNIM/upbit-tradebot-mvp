버전: v1.2026.10.06.1440 → v1.2026.10.20.1711

# WO-26 배포 완료 보고 — 약매수 차단 필터

- 작성: 2026-10-20 18:2x KST
- 배포 대상: `156b351` (코드 `035a552`, 문서 `8d75b57`·`156b351`)
- 서버 HEAD: `33a5d9e` → `156b351`
- 재시작: 명령 2026-10-20 17:40:51, `ExecMainStartTimestamp=Tue 2026-10-20 17:40:51 KST`, NRestarts=0
- 관찰 로그 출처: `journalctl -u tradebot`
- 서버에서는 pull 과 restart 만 했고 나머지는 읽기만 했다. 투자자 포지션·주문·설정은 건드리지 않았다.
- **배포 직전 실측 설정: 3분봉, EMA 60/200, 익절 2%, 손절 3%**
- 투자자 설정 변경 (기록만): 17:21:09 `set_buy_sell_conditions` id 212, 17:25:21 `set_buy_sell_conditions` id 213 (익절 2%·손절 3%), 17:27:41 `set_config` id 214 (EMA 20/200 → 60/200), 17:28:07 `strategy_init` id 215 (엔진 재기동, 적용)
- **판정: 0~3 전 항목 통과. 되돌리기 없음.** 체감 변경 있음 → `docs/operations/investor-notice-log.md` #4 (통보 예정, 운영자 발송)

## 3점 일치

| | HEAD | dashboard.py 버전 | 기동 |
|---|---|---|---|
| 로컬 (origin/main) | `156b351` | v1.2026.10.20.1711 | — |
| 서버 | `156b351` | v1.2026.10.20.1711 | 2026-10-20 17:40:51 KST |
| 화면 (운영자 육안) | — | v1.2026.10.20.1711 | — |

## 0. 배포 전 확인 (`deploy/pre-check.txt`, 17:40:27 조회)

| 항목 | 결과 | 판정 |
|---|---|---|
| KRW-JTO 포지션: account_positions | virtual_coin 0.0, locked 0.0, meta `{}` | 통과 |
| KRW-JTO 포지션: Upbit /v1/accounts | http 200, JTO 행 없음 = 0 | 통과 |
| origin/main / 서버 HEAD | `156b351` / `33a5d9e` | 통과 |
| 조건 파일 | `mcmax33_EMA_buy_sell_conditions.json` weak_entry 키 **없음**, sha256 `a63fc692a570113b2731063e986acf62d877326c91a97e7296578f1db27cb5af`, mtime 2026-10-20 17:25:21 | 기록 |
| settings_history | 215행, 마지막 id 215 (`strategy_init` 17:28:07) | 기록 |
| 봉 간격·EMA | minute3, fast/slow buy=sell 60/200 (settings_history id 215, params JSON 일치). 지시 전제(20/200)와 다름 → 실측으로 검증 (Fable 승인) | 기록 |
| 매수 가능 KRW | Upbit KRW balance 1,990,143.96, locked 0, order_ratio 0.1 | 기록 |
| 진행 중 주문 | 없음. 마지막 orders id 614 (10-20 11:00 SELL FILLED) | 기록 |

## 1. 서버 배포 (`deploy/deploy.txt`)

| 항목 | 결과 |
|---|---|
| `git pull --ff-only` 뒤 HEAD | `156b351`, `035a552` 포함 (merge-base 확인) |
| 재시작 | 17:40:51 명령 → active (running) |
| 서버 버전 | `v1.2026.10.20.1711` (pages/dashboard.py:495) |

## 2. 30분 무접속 관찰 (17:40:50 ~ 18:10:51, `deploy/observation-30min.txt`)

| 항목 | 기대 | 실측 | 판정 |
|---|---|---|---|
| (a) 기동 줄 | BOOT-RESUME success, long_history, 감사 행 보존 | 17:40:59 `[BOOT-RESUME] success` (7.5s), 17:41:00 `run_live_loop start` 1회, `[CLOCK] Initialized \| timeframe=minute3`, 17:41:01 `시드 방식=long_history bars=800`, `감사 행 보존 \| kept=182 inserted=0 updated_placeholder=18`. sma200·긴 이력 시드 실패 0 | 통과 |
| (a) `[CONFIG] 적용값` | weak_entry False·2.0·block·0.005 | `weak_entry_filter_enabled=False* weak_entry_mode=block* weak_entry_tp_pct=0.005* weak_entry_window_hours=2.0*` (* = 파일에 없어 기본값). sell `ema_dc=False … stop_loss_pct=3.0 take_profit=False take_profit_pct=2.0 trailing_stop=True` | 통과 |
| (a) `[WARMUP]` 직전 D/C | 값 있음, "알 수 없음" 아님 | `… 마지막 봉=2026-10-20 17:36:00 KST \| 직전 D/C=2026-10-20 05:48:00 KST`. "직전 D/C 알 수 없음" 0 | 통과 |
| (a) `[WEAK-ENTRY] 기동 정합 검사` | cleared=0 | `[WEAK-ENTRY] 기동 정합 검사 완료 \| user_id=mcmax33 cleared=0` (HTS-FLAG 정합 검사도 cleared=0) | 통과 |
| (b) 직전 D/C 독립 검증 | 측정 계산과 같음 | Upbit 공개 3분봉, EMA 60/200 (`deploy/wo26d_dc_verify.py`, `deploy/dc-verify.txt`). A 봇 재현(800봉 `seed_long_history`) **05:48**, ema 611.9870 / 608.4354 (로그와 같음). B 장기 기준(2,000봉 증분, 전략 식) 마지막 D/C **05:48**. 800봉 창 안 D/C 10-19 20:06·10-20 05:48, G/C 10-19 10:12·21:36·10-20 07:09 | 통과 |
| (c) settings_history·조건 파일 | strategy_init 1행만, 파일 불변 | 216행 (id 216 `strategy_init` 17:41:00 1행 증가). sha256 `a63fc692…`, mtime 17:25:21 그대로 | 통과 |
| (d) 매수 판정 불변 | 필터 꺼짐 → 이전과 같은 평가 | 창 안 G/C 없음 (fast > slow 유지, 마지막 G/C 07:09). BUY 평가 10건 전부 `NO_SIGNAL`, 워밍업 18건. 1:1 대조 표: 평가 통과 0 / 체결 0 · 취소 0 · 거절 0, SELL 발동 0, orders 0, audit_trades 0 (`deploy/match-1to1.txt`) | 통과 |
| (d) 약매수 판정 로그 | 0건 (코드 존재 먼저 확인) | 서버 코드: `strategy_incremental.py:1100·1108·1110`, `weak_entry.py:97·125·129`, `position_state.py:345`. `[WEAK-ENTRY]` 전체 1줄 = 기동 정합 검사. 차단·축소·일반 판정, recorded, restored, cleared, 불일치 모두 0 | 통과 |
| (e) 결함 태그 | 0 | ` ERROR `, Traceback, `[POS-DESYNC] class=`, `Upbit에 없는 timestamp`, `불일치 발견`, `과거 봉 검증 실패`, `database is locked`, `[LOCKED-QTY]`, CRITICAL, `[POLLUTED]`, `지표 상태 복원 실패`, VERIFY WARNING 모두 0. 외부 스캐너 0 | 통과 |
| (e) Bar# / 조정 / BACKFILL | 5 이상 / 400 / 0 | Bar#201 (17:42:11) → Bar#210 (18:09:10), 10봉(3분봉 30분 = 10). 조정 400봉 수신 10회. BACKFILL 0, 미확정 봉 제외 0 | 통과 |
| (e) 사후 확인 7 | minute3, 0.1원 이내 | `scripts/wo17s_verify_seed.py "2026-10-20 17:41:01" 611.9870 608.4354 1200 --interval minute3`: 800봉 재현 −0.0000 / +0.0000, 1,200봉 기준 −0.0000 / **+0.0038**, 부호 같음 (`deploy/seed-verify.txt`) | 통과 |
| (f) BACKFILL 시 last_dead_cross_ts 백업·복원 | 있으면 인용 | **해당 사건 없음** (`누락 봉 평가 시작`·`지표 상태 백업`·`지표 상태 복원 완료` 0). 참고: 이 값은 기존 `[BACKFILL] 지표 상태 백업/복원 완료` 로그와 같은 dict 로 처리되며 별도 로그 줄은 없다 | — |
| 참고 | — | `[NOTIFY] sent` 1줄 (boot_resume). `[POSITION-SYNC]`·boot_seed 0 (포지션 없음) | — |

## 3. 대시보드 1회 접속 (운영자, 18:15~18:19, `deploy/access.txt`)

| 항목 | 기대 | 실측 | 판정 |
|---|---|---|---|
| 화면 버전 | v1.2026.10.20.1711 | 운영자 육안 "v1.2026.10.20.1711" | 통과 |
| 설정 페이지 | 토글 꺼짐, (켜면) 2.0·매수 안 함·익절 % 비활성·안내 문구, 저장 안 함 | 운영자 확인: 토글 꺼짐, 켰을 때 기대대로, 저장하지 않고 다시 끔 | 통과 |
| 감사 로그 페이지 | 체결 표 "비고", BUY 평가 "약매수", 기존 칸 유지 | 운영자 확인: 비고 있음, 약매수 있음, 기존 칸 유지. journal `[AuditViewer] Strategy detection` 3회 (18:17:18·18:17:25·18:18:41) | 통과 |
| `[AUTO-RESUME] skip` · 엔진 | 1줄 · 재기동 없음 | 18:15:58 1줄 (boot_resume_at 17:40:59). 접속 구간 `run_live_loop start` 0, HOT-RELOAD·PARAMS-RELOAD 0, NRestarts=0 | 통과 |
| settings_history·조건 파일 (접속 전후) | 불변 | 접속 전 18:11:54 / 접속 뒤 18:19:45 모두 216행, sha256 `a63fc692…`, mtime 17:25:21 | 통과 |
| 접속 구간 결함 태그 | 0 | ERROR·Traceback·CRITICAL·POS-DESYNC·database is locked·StreamlitAPIException 0, `[WEAK-ENTRY]` 0 | 통과 |

## 4. 실패 시 조치

해당 없음. `035a552` 는 되돌리지 않았다.

## 5. 문서

- 운영 가이드 `docs/operations/wo8-force-buy-verification-guide.md`: **사후 확인 15** 추가 — 약매수 필터가 켜진 뒤 첫 약매수 차단 행(`WEAK_ENTRY_FILTER`), 첫 약매수 진입 행(비고 "약매수 진입 · 익절 x%", `[WEAK-ENTRY] recorded … order_uuid`), 그 포지션의 매도가 축소 기준에서 난 것(TP 또는 TS 무장), 정기 점검에서 2시간 안 G/C 의 차단·진입·결과를 경과 구간별로 집계. 정기 점검 목록 1~15.
- `docs/operations/investor-notice-log.md` #4: Fable 문안 원문을 "통보 예정 (운영자 발송)" 으로 기록.

## 6. 규칙 준수

| # | 내용 | 영향 |
|---|---|---|
| 1 | heredoc 미사용. 서버 쓰기는 `git pull --ff-only` 와 `systemctl restart tradebot` 뿐. Upbit 은 `GET /v1/accounts` 만, DB 는 `mode=ro`. 키 값 미출력 | — |
| 2 | 관찰 결과를 거르는 로컬 `cut`·`sed` 가 다국어 바이트에서 `Illegal byte sequence` 로 멈췄다(중간 점검 1회, 결과 확인 1회). 서버 출력은 파일로 정상 저장됐고 다시 읽었다 | 없음 |
| 3 | 대기 중 `sleep` 이 도구 규칙으로 막혀 배경 대기 명령(until 루프)으로 바꿨다 | 없음 |
| 4 | **와일드카드 패턴 1회 위반.** 근거 파일 키 노출 검사 `grep -ciE … deploy/*.txt` 를 로컬에서 실행했다(읽기 전용, 결과 전부 0). | 없음 |

## 7. 묶음

`wo26-deploy-20261020.zip`: `report.md`(이 문서), `deploy/` 근거(pre-check·deploy·boot-lines·dc-verify·seed-verify·observation-30min·match-1to1·access, 스크립트 3개), `commands.txt`, `git-log.txt`
