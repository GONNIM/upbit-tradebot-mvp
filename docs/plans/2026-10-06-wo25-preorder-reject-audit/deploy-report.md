버전: v1.2026.10.05.1526 → v1.2026.10.06.1440  (구현 커밋 9dd9bd7 은 v1.2026.10.06.1326, 문구 수정 커밋 33a5d9e 로 1326 → 1440)

# WO-25 배포 완료 보고 — 주문 전 봇 안 차단 감사 기록 + 감사 로그 "주문 전 차단" 구분 표시

- 작성: 2026-10-06 (KST)
- 배포 대상: `33a5d9e`. 포함 커밋은 코드 `9dd9bd7`, 문서 `7141d77`, 문구 수정 `33a5d9e` 이다.
- 서버 HEAD: `4ad8bf3` → `33a5d9e`
- 재시작: 명령 2026-10-06 14:45:05. `ExecMainStartTimestamp=Tue 2026-10-06 14:45:06 KST`, NRestarts=0
- 관찰 로그 출처: `journalctl -u tradebot`
- 서버에서는 pull 과 restart 만 했고 나머지는 읽기만 했다. 투자자 포지션·주문·설정은 건드리지 않았다.
- **판정: 0~3 전 항목 통과. 되돌리기 없음.**

## Fable 결정 반영 (배포 전)

| 결정 | 반영 |
|---|---|
| 1. 급등 차단은 행을 남기지 않는다 | 구현 그대로 두었다. 시험 (2) 는 "행 없음" 을 확인한다. |
| 2. 감사 로그 문구는 배포 전에 고친다 (B) | `33a5d9e` (아래) |
| A. 투자자 통보 문안 원문 | `docs/operations/investor-notice-log.md` #3 에 그대로 적었다 (이 문서 커밋) |

### B. 문구 수정 (`33a5d9e`, 엔진 판정·발주 무변경)

1. **단계 표시**: 주문 전 차단 행은 이미 `9dd9bd7` 에서 meta `stage='pre_order'` 를 갖는다. 거래소 거절 행(WO-9)은 stage 가 없다.
2. **`pages/audit_viewer.py`**
   - 행마다 meta 를 읽어 분류한다 (`services/db.py` 의 새 함수 `is_preorder_reject` / `trade_kind_row` / `trade_type_display_row`).
   - 주문 전 차단 행:
     - 유형 "⛔ 주문 전 차단", 필터 "주문 전 차단"
     - 경고 "⛔ 주문 전 차단 N건 — 봇이 주문 전에 매수를 중단했습니다. 사유 열을 확인하세요."
     - 배경은 붉은색
   - 거래소 거절 행은 기존 그대로다: "⛔ 매수/매도 거절", 필터 "거절", 경고 "⛔ 발주 거절 N건 — 거래소가 봇 주문을 받지 않았습니다 (체결 아님). '거절 사유' 열을 확인하세요."
   - 필터 도움말은 "거절 = …", "주문 전 차단 = …", "미체결 취소 = …" 를 한 줄씩 나눴다.
   - 화면 변경은 추가만 있다. 삭제·이동·접힘은 없다.
   - 기존 함수 `trade_kind` / `trade_type_display` / `is_reject_type` 는 바꾸지 않았다. 그래서 대시보드 최근 거래 표시는 주문 전 차단 행도 "⛔ 매수 거절" 로 보인다.
3. **`docs/operations/terminology.md`**: "주문 전 차단" 행과 거래소 거절 행을 구분해 적었다.
4. **시험**
   - WO-25 시험 19건. (4) 를 갱신하고, (a) pre_order 행 → 새 문구, (b) 거래소 거절 행 → 기존 문구를 추가했다.
   - WO-24 시험 (6) 이 `_kind_options` 원문을 대조하므로 새 목록으로 고쳤다.
   - 결과 (`deploy/b-gate-oldcode-revert.txt`):
     - [A] `33a5d9e` 게이트 **321/321 통과**
     - [B] WO-25·WO-9·WO-24 시험 37건 OK
     - [C] B 전 코드(`7141d77`) 에서 새 시험: (4) ERROR `ImportError: trade_kind_row`, (a) FAIL (경고가 "거래소가 봇 주문을 받지 않았습니다" 로 나옴). (b) 는 통과한다 (기존 문구 유지 가드).
     - [D] `33a5d9e` + `7141d77` + `9dd9bd7` 을 함께 revert: 충돌 없음, 20개 파일. 되돌린 뒤 버전 v1.2026.10.05.1526, py_compile OK, 게이트 **302/302 통과**.

## 3점 일치

| | HEAD | dashboard.py 버전 | 기동 |
|---|---|---|---|
| 로컬 (배포 시점 origin/main) | `33a5d9e` | v1.2026.10.06.1440 | — |
| 서버 | `33a5d9e` | v1.2026.10.06.1440 | 2026-10-06 14:45:06 KST |
| 화면 (운영자 육안, 15:16) | — | v1.2026.10.06.1440 | — |

## 0. 배포 전 확인 (`deploy/pre-check.txt`, 14:44:55 조회)

| 항목 | 결과 | 판정 |
|---|---|---|
| KRW-JTO 포지션: account_positions | virtual_coin 0.0, locked 0.0 | 통과 |
| KRW-JTO 포지션: Upbit /v1/accounts | http 200, JTO 행 없음 = 0 | 통과 |
| origin/main / 서버 HEAD | `33a5d9e` / `4ad8bf3` | 통과 |
| **매수 가능 KRW** | Upbit KRW `balance 0.59003382`, `locked 0`. params `order_ratio 0.5` | 기록 |
| 예상 | 지정가 주문액 = floor(0.59 × 0.5 / 1.0005) = 0원 < 5,000원. 따라서 **KRW 가 채워지기 전 첫 매수 신호에서는 주문 대신 `BUY_REJECTED krw_below_min` 행이 생길 것**이다 (note "매수 가능 KRW 부족 (가용 1원, 주문 비율 적용 주문액 0원 < 최소 5,000원) — 현재가 매수 주문 전 차단"; 가용은 반올림해 표시된다). | 기록 |
| settings_history / 설정 파일 | 195행 (마지막 id 195). `mcmax33_EMA_buy_sell_conditions.json` sha256 `286db8b9…`, mtime 2026-10-06 07:52:22 | 기록 |
| 10-05 16:44:46 이후 매매 | orders 0건. audit_trades 는 다른 종목 앱 매수 감지 11건 (BLEND, TOKAMAK, BIRB) | 기록 |

## 1. 서버 배포 (`deploy/deploy.txt`)

| 항목 | 결과 |
|---|---|
| `git pull` 뒤 HEAD | `33a5d9e`, `9dd9bd7·33a5d9e 포함` (merge-base 확인) |
| 재시작 | 14:45:05 명령, 14:45:06 active (running) |
| 서버 버전 | `v1.2026.10.06.1440` |

## 2. 30분 무접속 관찰 (14:45:05 ~ 15:15:06, `deploy/observation-30min.txt`)

| 항목 | 기대 | 실측 | 판정 |
|---|---|---|---|
| 기동 줄 3종 | BOOT-RESUME success, 시드 1줄, 감사 행 보존 1줄 | 14:45:12 `[BOOT-RESUME] success` (6.3s), `timeframe=minute1`. 14:45:13 `시드 방식=long_history bars=800 ema_fast=769.0666 ema_slow=772.8641` 1줄. `감사 행 보존 \| kept=200 inserted=0 updated_placeholder=0` 1줄 | 통과 |
| 결함 태그 | 0 | ` ERROR `, Traceback, `[POS-DESYNC] class=`, `Upbit에 없는 timestamp`, `불일치 발견`, `과거 봉 검증 실패`, `database is locked`, `[LOCKED-QTY]`, CRITICAL, VERIFY WARNING 모두 0. 외부 스캐너 0 | 통과 |
| Bar# / 조정 / BACKFILL | 5 이상 / 400 / 0 | Bar#201 (14:47:11) → Bar#217 (15:14:10), 17봉. 1분봉 30개 중 거래 없는 봉 13. 조정 400봉 수신 31회. BACKFILL 0, 미확정 봉 제외 0 | 통과 |
| 사후 확인 7 | 1,200봉 기준 0.1원 이내 | 800봉 재현 +0.0000 / +0.0000, 1200봉 기준 +0.0000 / **+0.0007** (`deploy/boot-settings-and-seed.txt`) | 통과 |
| 1:1 대조 | 표 | BUY 평가 통과 0, SELL 평가 발동 0, 창 안 orders 0 (`deploy/match-1to1.txt`) | 통과 |
| 매수 신호 결과 | 있으면 인용 | `EMA Buy Signal` 0, `action=BUY` 0 → **해당 사건 없음**. 코드 존재 확인: 서버 `core/trader.py` 의 `_audit_preorder_reject(` 7곳(566·585·945·976·1009·1043·1054), `core/strategy_engine.py` 의 `_audit_buy_blocked(` 5곳(1063·1073·1100·1360·1394), `trader.py:507` `[AUDIT-REJECT] {side.upper()}_REJECTED 기록`. `[AUDIT-REJECT] BUY_REJECTED 기록` 0, `[AUDIT-REJECT] 기록 실패` 0, `엔진 주문 전 차단 기록 예외` 0. BUY_CANCELED 0 | — |
| 참고 | — | `[NOTIFY] sent` 1줄 (14:45:14 boot_resume). `[POSITION-SYNC]` 0. 엔진 기동 1회 | — |

기동 뒤 settings_history 는 196 이다 (id 196 `strategy_init` 14:45:12 1행, 기존 동작). 설정 파일 해시와 mtime 은 그대로다 (`deploy/boot-settings-and-seed.txt`).

## 3. 대시보드 1회 접속 (운영자 접속, 15:16)

| 항목 | 기대 | 실측 | 판정 |
|---|---|---|---|
| `[AUTO-RESUME] skip` | 1줄 | 15:16:29 1줄 (boot_resume_at 14:45:12) | 통과 |
| 엔진 스레드 | 1개 | 14:45:05 이후 `run_live_loop start` 1회 (기동 때). NRestarts=0, 기동 시각 그대로 | 통과 |
| 화면 버전 | v1.2026.10.06.1440 | 운영자 육안 확인 "v1.2026.10.06.1440" | 통과 |
| 감사 로그 페이지 | "주문 전 차단" 필터, 새 문구(행이 있으면), 거래소 거절 기존 문구 | 15:16:41 ~ 15:19:51 감사 로그 페이지 접속 9회 (`[AuditViewer] Strategy detection`). **DB 의 거절 행은 BUY/SELL_REJECTED 모두 0건**이라, 화면에 새 경고나 기존 거절 경고가 나올 행이 없다. 필터 선택지·도움말·두 문구의 표시는 AppTest 실제 렌더 시험 (4)(a)(b) 로 확인했다. 운영자 회신은 화면 버전만이었고, 필터를 육안으로 확인한 기록은 없다 | 통과 (행 없음) |
| settings_history·설정 파일 (운영자 접속 전후 불변) | 접속 뒤 그대로 | 15:20:31 조회: 196행, sha256 `286db8b9…`, mtime 2026-10-06 07:52:22. 접속 전(14:45:35)과 같다 (`deploy/access.txt`) | 통과 |
| 접속 구간 결함 태그 | 0 | 15:15:06 이후 0. 14:45:05 이후 `AUDIT-REJECT`·`EMA Buy Signal` 0 | 통과 |

## 4. 실패 시 조치

해당 없음. WO-25 커밋은 되돌리지 않았다.

## 5. 문서

- 운영 가이드 `docs/operations/wo8-force-buy-verification-guide.md`
  - 사후 확인 14 추가: 첫 주문 전 차단 때 `[AUDIT-REJECT] BUY_REJECTED 기록 … code=…`, BUY_REJECTED 행(stage=pre_order·error_name·note·bar_time), 감사 로그의 "⛔ 주문 전 차단" 과 새 경고, 거래소 거절 기존 문구 유지, 1:1 대조의 "미요청" 행마다 같은 봉의 pre_order 행.
  - 정기 점검 목록을 1~14 로 바꿨다.
- `docs/operations/investor-notice-log.md` #3: Fable 통보 문안 원문을 그대로 적었다.
  - **확인 요청**: 문안의 "약 −13원" 은 가격 차이(₩9,999.99 − ₩9,986.95 = −₩13.05)다. 사건 기록 `docs/plans/2026-10-05-wo22-wallet-sync-entry/incident.md` 2절에는 "수수료 포함 약 −₩23" 으로 적혀 있다. 지시대로 문안은 바꾸지 않았다.

## 6. 규칙 준수와 정정

| # | 내용 | 영향 |
|---|---|---|
| 1 | **와일드카드 패턴 1회 위반.** B 작업 중 `grep -rn … --include=*.py .` 를 썼다. zsh 가 `no matches found` 로 실행 전에 막아 실행되지 않았다. | 없음 |
| 2 | B 의 audit_viewer 수정을 python 문자열 치환으로 하면서 `\n` 이 실제 줄바꿈으로 들어가 py_compile 이 실패했다. 커밋 전에 파일 도구로 고쳤다. | 없음 (커밋 전) |
| 3 | 관찰 결과를 거르는 로컬 grep 에서 정규식 오류(`mismatched ( )`)가 났다. 서버 출력 파일은 정상 저장됐고 다시 읽었다. | 없음 |
| 4 | heredoc 은 쓰지 않았다. 서버 쓰기는 pull 과 restart 뿐이다. 키 값은 출력하지 않았다. | — |

## 7. 묶음

- `report.md` (이 문서), `commands.txt`, `git-log.txt`
- `deploy/pre-check.txt` (0단계: HEAD, 포지션, 매수 가능 KRW, settings_history, 설정 파일 해시), `deploy/deploy.txt`
- `deploy/boot-snapshot.txt`, `deploy/boot-settings-and-seed.txt`, `deploy/observation-30min.txt`, `deploy/match-1to1.txt`, `deploy/access.txt`, `deploy/journal-excerpt.txt`
- `deploy/b-gate-oldcode-revert.txt`, `deploy/wo25b_check.sh` (B 관문, B 전 코드 시험, 3커밋 함께 revert)
- 스크립트: `deploy/wo25d_pre.py`, `deploy/wo25d_obs.sh`, `deploy/wo22d_match.py`
