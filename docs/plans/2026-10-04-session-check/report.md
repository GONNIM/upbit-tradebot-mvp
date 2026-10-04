# 세션 시작 정기 점검 (2026-10-04, 읽기 전용)

- 점검 창: 2026-10-04 10:22:33 (WO-20 기동) ~ 12:23:53
- 서버는 읽기만 했다. 포지션·주문·설정·파일 무변경. 투자자 안내 없음. 로그 출처 `journalctl -u tradebot`.
- 저장소 변경은 7번 백로그 한 칸뿐이다 (문서 커밋 1건, 서버 pull 없음).

## 결론

결함 없음. 창 동안 봇 매매 신호·주문은 0건이다. 1분봉 거래 없는 봉 비율은 38.0%. 사후 확인 9 는 확정 주문이 없어 "해당 사건 없음". 사후 확인 6 은 이번에 처음으로 `reason=bot_sell` 해제 경로가 관측됐다(10-03 20:05 KRW-JTO).

## 1. 서버 상태

| 항목 | 기대 | 실측 | 판정 |
|---|---|---|---|
| systemctl | active | active (running) since 2026-10-04 10:22:33, MainPID 2313925, NRestarts 0 | 통과 |
| HEAD | e97dec6 | e97dec6 | 통과 |
| 화면 버전(파일) | v1.2026.10.02.2241 | v1.2026.10.02.2241 | 통과 |
| 10:22:33 이후 재기동 | — | 서비스 재기동 0, 엔진 `run_live_loop start` 1 (기동 때) · `run_live_loop 종료` 0. `[AUTO-RESUME] skip` 2 (대시보드 접속 2회, 엔진 추가 기동 없음) | 재기동 0 |

## 2. 기동 이력

재기동이 없어 기동은 10:22:33 1회뿐이다 (WO-20 배포 기동).

| 항목 | 실측 |
|---|---|
| `[WARMUP] 시드 방식=long_history bars=800` | 1줄 (ema_fast=764.0099 ema_slow=767.5907, 마지막 봉 10:21) |
| 폴백 (`시드 방식=sma200`, `긴 이력 시드 실패`) | 0 / 0 |
| `[WARMUP] 감사 행 보존` | 1줄 `kept=200 inserted=0 updated_placeholder=0` |
| 포지션 보유 중 재기동 | 없음 → 사후 확인 8 해당 사건 없음 (`[POSITION-APPLY] source=boot_seed` 0, `[BOOT-SEED]` 0) |

## 3. 운영 상태 (10:22:33 ~ 12:23:53)

| 항목 | 실측 |
|---|---|
| 1분봉 확정 (고유) | 121 |
| Bar# 진행 | 75 (Bar#201 10:27:11 → Bar#275 12:19:11), Bar# 이중 0 |
| 거래 없는 봉 (`[CONFIRMED-NO-TRADE]`, 고유) | 46 → **38.0%** (봉 확정 중복 기록 0) |
| 매수 신호 `EMA Buy Signal` / `action=BUY` / `action=SELL` | 0 / 0 / 0 |
| 주문 (`[FIXED-PRICE]` 진입 / `[OR] enqueued` / `[OR] final`, orders id>558) | 0 / 0 / 0 / 0건 |
| SELL_REJECTED·BUY_REJECTED (로그 / audit_trades 전체) | 0 / 0 |
| 결함 태그 | ` ERROR ` 0, Traceback 0, `[POS-DESYNC] class=` 0, `Upbit에 없는 timestamp` 0, `불일치 발견` 0, `과거 봉 검증 실패` 0, VERIFY WARNING 0, `database is locked` 0, `[LOCKED-QTY]` 0, CRITICAL 0 |
| 외부 스캐너 (따로) | 창 안 0 (Missing file 0, MediaFileStorageError 0) |
| 참고 WARNING | `[RECONCILE] 봉 미반영` 193줄(1분봉 Progressive Retry 대기 — 거래 없는 봉 판정 전 단계), `[RECONCILE] 변경 감지!` 75줄(새 봉 반영, Bar# 75 와 같음), `[PageContext] 필수 컨텍스트 부재` 2, Redis 비활성 1 |
| audit_trades (창) | 0건. 창 직후 12:27:04 KRW-ANKR HTS_BUY 1건(봇 대상 아님) |

## 4. 사후 확인 9

10:22:33 이후 확정 주문 없음 (`[OR] final` 0, orders 마지막 id 558 = 10-03 20:05). **해당 사건 없음.** 다음 점검으로 넘긴다.

## 5. 사후 확인 1~7 (가이드 기준 시각)

| 번호 | 항목 | 실측 | 판정 |
|---|---|---|---|
| 1 | 강제 매수 원자 경로 (기준 09-30 16:33:05) | `[FIXED-PRICE][FORCE]` 0, force_buy 감사 행 0 (`[LIMIT-FILL] apply_entry` 3건은 일반 현재가 매수 체결) | 해당 사건 없음 |
| 2 | HTS 승격 가드 (KRW-JTO) | 기존 09-30 16:50:05 차단 1회 → 16:50:07 streak 리셋 외 새 사건 없음. 10-03 09:18:47 JTO 앱 매수는 첫 SELL 평가(09:20:11)에서 `bars_held=1` 로 정상 진행 — 첫 봉 방어가 필요 없었음, `class=` 0 | 새 사건 없음 (정상) |
| 3 | WO-9 (c)(b)(e) | ① HTS 매수 감지 18건 정상(`total(가용+묶임)` 기준, 예: 10-03 09:18:47 JTO Δ=2071.002113) ② `[LOCKED-QTY]` 2건은 09-30 묶임·해제(기존 기록) — 새 묶임 없음 ③ `[AUDIT-REJECT]` 0, REJECTED 감사 행 0 | ① 통과, ②③ 해당 사건 없음 |
| 4 | WO-14 (a) 미확정 봉 제외 (기준 10-01 11:42:01) | 누적 6건, 마지막 10-01 13:10:05 — WO-16(13:24:41) 이후 새 발생 없음 | 해당 사건 없음 |
| 5 | WO-14 E1 trailing 복원 | 복원 0, 건너뜀 0, 실패 0 (BACKFILL 시작 누적 1) | 해당 사건 없음 |
| 6 | WO-18 hts_buy 해제 사이클 (기준 10-01 18:10:24) | HTS 매수 감지 16, 해제 10 (`bot_sell` 2, `sync_all_positions_cleared` 8). **10-03 20:05:12 `[HTS-FLAG] cleared \| reason=bot_sell \| ticker=KRW-JTO memory=True db=True`** — 봇 매도 해제 경로 첫 관측. 잔존 SQL 0. 보유 중 hts_buy: KRW-PYUSD·KRW-USDT·KRW-ANKR(앱 보유, 봇 대상 아님) | ①② 통과, ③ "다음 봇 매수 `hts_buy=False`" 는 해제 뒤 봇 매수 없음 → 대기 |
| 7 | WO-17 (S) 시드 | 기동 1회: `timeframe=minute1`, `long_history bars=800`, 폴백 0. 1분봉 대조(10-04 WO-20 배포 시): 1,200봉 기준 +0.0000 / +0.0052 | 통과 |

## 6. 비밀 파일

| 항목 | 실측 | 판정 |
|---|---|---|
| `.env` | `-rw------- root 367` | 통과 |
| `.streamlit/secrets.toml` | `-rw------- root 590` | 통과 |
| `.bak`·`.old`·`.orig`·`~` (`/root`, 저장소 루트·하위 1단계, `ls -la` + awk 접미사 비교) | 0개 | 통과 |
| `enableStaticServing` | False | 통과 |
| 최근 7일 외부 스캐너 (09-27 12:31 ~) | 7건 (`.git/config` 5, `.env` 1, `secrets.toml` 경로 탐색 1), 모두 `MediaFileStorageError` 로 거부 (창 안 0) | 통과 |

## 7. 백로그

`docs/plans/backlog.md` 보류 항목 표 "교차 폭 하한" 근거 칸: "10-02 야간 세 교차 모두 fast−slow 0.2원 이내, 747 매수·739 손절 1회". 문서 커밋 1건, 서버 pull 없음.

## 묶음

- `report.md` (이 문서), `commands.txt`, `git-log.txt`
- `evidence/session-check-output.txt` (점검 스크립트 전체 출력), `evidence/posthoc-detail.txt` (LOCKED-QTY·JTO 앱 매수 첫 봉), `evidence/journal-1022-1223.txt`, `evidence/db-queries.txt`, `evidence/sc_main.sh`
