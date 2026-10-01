# WO-8 강제 매수 지정가 이식 · 배포 후 검증 가이드

**작성일**: 2026-09-12
**최신 배포 (WO-8b 원자화 포함)**: 2026-09-18
**대상 커밋 (WO-8b 라운드)**:
- WO-8b: `8982d27f9edbc2078145df08395f4f4e0cbe679c` (short `8982d27`)
- WO-7:  `ad093773fe1f0e099ab0815c75607bf79cbed679` (short `ad09377`)
**초기 배포 커밋**: `de28fea` (2026-09-12, WO-8 초기, 원자화 이전)
**대상 대시보드 버전**: **`v1.2026.09.18.1600`** (WO-8b 배포본, 이전 `v1.2026.09.12.1715` → 이후 `v1.2026.09.18.1600`)
**배포 시각**: 2026-09-18 16:40:32 KST (ExecMainStartTimestamp)

**상태**: **완결 (2026-09-18)** · 상세는 `docs/plans/2026-09-12-wo8-force-buy-limit/plan.md` 상단 완결 선언 절 참조.

---

## 롤백 절차 (기한 없이 유효 · 각 커밋 독립 revert)

```bash
git revert 8982d27f9edbc2078145df08395f4f4e0cbe679c   # WO-8b 단독 (강제 매수 uuid 등록 + 원자화)
git revert ad093773fe1f0e099ab0815c75607bf79cbed679   # WO-7 단독 (진입가 배지 + 안내)
```

파일 겹침 없어 독립 revert 가능. force push 금지, hook 우회 금지.

---

## 확인 0 · 배포 정합 (재개 전 필수)

**서버 반영 상태가 아래와 일치할 때만 검증을 진행한다. 불일치 시 즉시 사용자에게 보고하고 대기.**

| 항목 | 기준값 |
|---|---|
| 서버 HEAD | `de28fea5b3eb8caf0d571f8436a47b6b0dd4ae48` |
| 서버 `pages/dashboard.py` 버전 | **`v1.2026.09.12.1715`** |
| 로컬 HEAD | `de28fea5b3eb8caf0d571f8436a47b6b0dd4ae48` (일치) |
| 로컬 `pages/dashboard.py` 버전 | **`v1.2026.09.12.1715`** (일치) |
| `[SKIP-BAR]` 로그 (배포 후) | 0건 |
| ExecMainStartTimestamp | 2026-09-12 17:24:07 KST |

**검증 명령**:
```bash
# 로컬
git rev-parse HEAD
grep -oE 'v1\.2026\.09\.[0-9]+\.[0-9]+' pages/dashboard.py | head -1

# 서버 (SSH 읽기 전용)
ssh root@orionhunter7.cafe24.com \
  "git -C /root/upbit-tradebot-mvp rev-parse HEAD && \
   grep -oE 'v1\.2026\.09\.[0-9]+\.[0-9]+' /root/upbit-tradebot-mvp/pages/dashboard.py | head -1 && \
   systemctl show tradebot -p ExecMainStartTimestamp"
```

---

## 확인 1 · 30분 무결성

배포 시각으로부터 30분 창(2026-09-12 17:24:07 ~ 17:54:07) 결함 태그 부재.

| 태그 | 대상 | 목표 |
|---|---|---|
| `⏸ [SKIP-BAR]` | live_loop | **0건** |
| `POLLUTED` | strategy_engine (state_polluted) | **0건** |
| `[POS-DESYNC] class=integrity_gap` | 진짜 결손 (hts_buy=False) — 엔진 결함 태그 | **0건** |
| `[POS-DESYNC] class=pos_desync_promoted` | 승격 가드 CRITICAL 승격 발화 | **0건** (자동 복구 실패 사례) |
| `[POS-DESYNC] class=first_bar_guard` | 외부 매수 첫 봉 방어 (설계된 1봉 차단) | 카운트만 — 결함 아님 |

> 2026-09-30 WO-10 정정: 예전 명령은 `core.strategy_incremental` 줄에서 'CRITICAL' 단어를 셌습니다. 이 단어는 첫 봉 방어(정상)와 진짜 결손에 같이 찍혀 오탐이 났습니다(09-30 16:50:05). 또 `pos_desync_promoted`는 알림 dedupe 키에만 있고 로그에는 찍히지 않아 항상 0이었습니다. WO-10 부터 세 경우를 `[POS-DESYNC] class=…` 로그로 구분합니다. WO-10 배포 전 구간을 볼 때는 `데이터 무결성 결손` 줄 수와 바로 다음 봉의 `[POS-DESYNC] streak 리셋` 여부로 판단합니다.
| `Traceback` (엔진 계열) | core/engine/services/ 계열 | **0건** |
| `Traceback` (Streamlit UI) | `issue-18-streamlit-ui-tracebacks.md`로 분리 집계 | 카운트만 |

**검증 명령**:
```bash
ssh root@orionhunter7.cafe24.com "
  START='2026-09-12 17:24:07'
  END='2026-09-12 17:54:07'
  echo 'SKIP-BAR:  ' \$(journalctl -u tradebot --since \"\$START\" --until \"\$END\" --no-pager 2>/dev/null | grep -c 'SKIP-BAR')
  echo 'POLLUTED:  ' \$(journalctl -u tradebot --since \"\$START\" --until \"\$END\" --no-pager 2>/dev/null | grep -c 'POLLUTED')
  echo 'gap:       ' \$(journalctl -u tradebot --since \"\$START\" --until \"\$END\" --no-pager 2>/dev/null | grep -c 'POS-DESYNC\] class=integrity_gap')
  echo 'promoted:  ' \$(journalctl -u tradebot --since \"\$START\" --until \"\$END\" --no-pager 2>/dev/null | grep -c 'POS-DESYNC\] class=pos_desync_promoted')
  echo 'guard(참고):' \$(journalctl -u tradebot --since \"\$START\" --until \"\$END\" --no-pager 2>/dev/null | grep -c 'POS-DESYNC\] class=first_bar_guard')
  echo 'TB 엔진:   ' \$(journalctl -u tradebot --since \"\$START\" --until \"\$END\" --no-pager 2>/dev/null | grep 'Traceback' | grep -cvE 'streamlit/web|streamlit/runtime|memory_media_file|media_file_handler|bootstrap\.py')
  echo 'TB Stlit:  ' \$(journalctl -u tradebot --since \"\$START\" --until \"\$END\" --no-pager 2>/dev/null | grep 'Traceback' | grep -cE 'streamlit')
"
```

---

## 확인 2 · Bar# 정상 진행

첫 5분봉 확정 이후 매 5분 봉 경계마다 `Bar#N | ts=... | close=... | action=(HOLD|BUY|SELL)` 로그가 순번 증가로 이어짐.

**검증 명령**:
```bash
ssh root@orionhunter7.cafe24.com "
  journalctl -u tradebot --since '2026-09-12 17:24:07' --no-pager 2>/dev/null \
  | grep -E 'core\.strategy_engine.*Bar#[0-9]+ \| ts=.*' \
  | grep -oE 'Bar#[0-9]+ \| ts=[0-9:+ -]+' | sort -u | tail -10
"
```

---

## 확인 3 · 크로스 매수 흐름 회귀 여부 (기존 기능)

WO-8은 강제 매수 경로만 변경. 정상 크로스 매수(EMA_GC)·매도(SL/TS)는 회귀 없어야 함.

- 크로스 발생 시 `EMA Golden Cross detected` → `action=BUY` → `LIMIT-FILL apply_entry 완료` (현재가 매수 활성일 때) 또는 `BUY 체결` (시장가 매수일 때) 로그 관측
- 30분 창 내 크로스 미발생은 정상 (자연 발생 없음), 회귀 아님

---

## 확인 4 · WO-8 완결 기준 (재정의) + 사후 확증

**완결 기준 재정의 (WO-8b 라운드 승인)**: 사용자의 강제 매수는 HTS 경유가 대부분이라 봇 버튼 사용 시점을 예측할 수 없다. 따라서 완결 조건을 다음과 같이 재정의한다.

**WO-8 완결 조건** = 다음 3항목 모두 통과:
1. **WO-8b 구현 (uuid 등록)** — `services/trading_control.py`가 `trader.buy_limit()` 반환 uuid를 `StrategyEngine._pending_buy_uuid`에 등록.
2. **왕복 TEST 통과** — 발주 → 등록 → 모의 체결 → `_on_limit_fill` 콜백 → `apply_entry` 발화 → `[POSITION-SYNC] 자동 복구` 미발화.
3. **배포 후 30분 무결성** — 결함 태그 6종 부재.

### 사후 확증 (기한 없이 정기 점검 편입)

**다음 실발주 1건의 로그 확증**은 "사후 확증" 항목으로 격하되며 **세션 개시 정기 점검에 편입**된다. 강제 실행 요구·마감 없음.

**사후 확증 대상 2건**:

1. **자연 발생 강제 매수 로그**: `[FIXED-PRICE][FORCE]` 발주 이후:
   - `[LIMIT-FILL] apply_entry(source='bot_limit_fill')` 발화 ✓
   - 이후 첫 봉 SELL 평가에서 `[POSITION-SYNC] 자동 복구` 로그 부재 ✓
   - `audit_trades.reason='force_buy'` 행 `entry_price` 정상 기재 (기존 관례상 빈값 허용, WO-8b 이식과 별개)

2. **HTS 매수 후 승격 가드 실전 관측**: HTS_BUY 감지 후 첫 봉 방어 상황 발생 시:
   - `pos_desync_warn` (첫 봉) → 자동 복구 → 리셋 정상 흐름 확인
   - 2봉 연속 발생 시 `pos_desync_promoted` 승격 정확성 확인 (오탐 여부)

### 세션 개시 정기 점검 조회 명령

```bash
ssh root@orionhunter7.cafe24.com "
  START='2026-09-12 17:24:07'
  # (1) 자연 발생 강제 매수 로그
  echo '-- [LIMIT-FILL] apply_entry (WO-8b 이식 후 발화 예상) --'
  journalctl -u tradebot --since \"\$START\" --no-pager 2>/dev/null | grep '\[LIMIT-FILL\] apply_entry' | tail -3
  echo '-- 이후 [POSITION-SYNC] 자동 복구 (부재 예상) --'
  journalctl -u tradebot --since \"\$START\" --no-pager 2>/dev/null | grep 'POSITION-SYNC.*자동 복구' | wc -l
  # (2) 승격 가드
  # (WO-10 정정) pos_desync_warn/promoted 는 알림 dedupe 키라 로그에 없음 → class= 로그로 집계
  echo '-- 외부 매수 첫 봉 방어 (class=first_bar_guard) --'
  journalctl -u tradebot --since \"\$START\" --no-pager 2>/dev/null | grep 'POS-DESYNC\] class=first_bar_guard' | wc -l
  echo '-- 2봉 연속 승격 (class=pos_desync_promoted) --'
  journalctl -u tradebot --since \"\$START\" --no-pager 2>/dev/null | grep 'POS-DESYNC\] class=pos_desync_promoted' | wc -l
"
```

발생 시 §확인 4-a 이하의 항목별 상세 검증을 진행한다. 기한 없음.

### 세션 개시 점검 0번 (최우선) — 묶인 JTO 포지션의 봇 매도 신호 (WO-9 (e) 실전 확증)

2026-09-30 16:49 부터 KRW-JTO 1,340.436268개가 앱 지정가 매도 주문으로 전량 묶여 있습니다(가용 0). 손절 기준은 -0.7% 입니다. 세션을 시작하면 이 항목을 가장 먼저 봅니다.

**개입 금지**: 사용자는 매수·앱 지정가 매도·매매 일시정지 세 행동으로 "직접 팔겠다"는 의도를 보였습니다. 봇이 아무것도 하지 않는 현재 상태가 올바릅니다. 운영자는 `trading_paused` 해제·앱 주문 취소를 하지 않고 권고도 하지 않습니다. 검증 목적의 거절 유도도 금지합니다.

**확증 조건**: 이 항목은 **사용자가 스스로 일시정지를 풀었고, 앱 지정가 매도 주문이 남아 묶임이 유지된 상태에서, 봇 매도 신호가 났을 때만** WO-9 (e) 실전 확증으로 봅니다. 일시정지 중의 `⏸️ [PAUSE] 실주문 스킵 | action=SELL` 은 확증도 결함도 아닙니다(건수만 기록).

1. `users.trading_paused` 값과, 이 포지션에 봇 매도 신호(손절·트레일링·데드크로스)가 났는지 확인합니다.
2. 확증 조건이 충족됐다면 다음 세 가지를 확인합니다.
   - `audit_trades` 에 `type='SELL_REJECTED'` 행이 생겼고 `note` 에 "주문 가능 수량 부족 — 업비트 앱에서 직접 넣은 지정가 매도 주문이 있는지 확인하세요." 가 있는지
   - 감사 로그 페이지 체결 탭에 ⛔ 행과 거절 사유가 보이는지 (운영자 육안)
   - 텔레그램 "❌ 매도 거절 — KRW-JTO" 알림 (운영자 수신 확인)
3. 묶임이 풀렸다면 `✅ [LOCKED-QTY] 묶임 해제` 로그와 HTS 오기록(HTS_BUY) 부재를 확인합니다.

```bash
ssh root@orionhunter7.cafe24.com "
  START='2026-09-30 16:49:10'
  journalctl -u tradebot --since \"\$START\" --no-pager 2>/dev/null | grep -E 'SELL-LIVE|AUDIT-REJECT|LOCKED-QTY|Sell triggered|action=SELL' | tail -10
  echo 'PAUSE 스킵(SELL):' \$(journalctl -u tradebot --since \"\$START\" --no-pager 2>/dev/null | grep -c 'PAUSE\] 실주문 스킵.*action=SELL')
  sqlite3 'file:/root/upbit-tradebot-mvp/services/data/tradebot_mcmax33.db?mode=ro' \"SELECT username, trading_paused FROM users;\"
  sqlite3 'file:/root/upbit-tradebot-mvp/services/data/tradebot_mcmax33.db?mode=ro' \"SELECT id,timestamp,type,reason,price,qty,note FROM audit_trades WHERE ticker='KRW-JTO' AND timestamp>='2026-09-30T16:49' ORDER BY id;\"
  sqlite3 'file:/root/upbit-tradebot-mvp/services/data/tradebot_mcmax33.db?mode=ro' \"SELECT virtual_coin, virtual_coin_locked, meta FROM account_positions WHERE ticker='KRW-JTO';\"
"
```

### 사후 확증 3건 (2026-09-30 WO-9·WO-11 완결 시 편입)

세션을 시작할 때마다 아래 세 항목을 봅니다. 기한은 없습니다. 기준 시각은 WO-9·WO-11 엔진 시작 시각 `2026-09-30 16:33:05` 입니다.

| 번호 | 항목 | 확인 내용 | 2026-09-30 관측 창 상태 |
|---|---|---|---|
| 1 | 강제 매수 원자 경로 (WO-8b) | `[FIXED-PRICE][FORCE]` 발주 → `[LIMIT-FILL] apply_entry` 발화 → 첫 봉 `[POSITION-SYNC] 자동 복구` 부재 | 미발생 (대기) |
| 2 | HTS 승격 가드 (WO-8) | 외부 매수 첫 봉 `bars_held=0 … SELL 차단` 1회 → 다음 봉 `[POS-DESYNC] streak 리셋` → `pos_desync_promoted` 부재. 2봉 연속이면 승격이 맞는지 확인 | 16:50:05 차단 1회 → 16:50:07 streak 리셋, 승격 0 (정상 흐름 1회 관측) |
| 3 | WO-9 (c)(b)(e) 실전 | ① 다음 HTS 매수가 `total(가용+묶임)` 기준으로 정상 감지 ② 다음 앱 지정가 매도 주문 묶임 시 `⛔ [LOCKED-QTY]` 경고 1회 + 대시보드 ⛔ 배지 ③ 묶인 상태에서 봇 매도 신호가 나면 `[AUDIT-REJECT] SELL_REJECTED` 기록 + 감사 로그 페이지 ⛔ 행 + 텔레그램 "매도 거절" 안내 | ① 16:47:09 KRW-JTO, 16:56:13 KRW-MON 정상 감지 ② 16:49:10 경고 발화 (배지는 운영자 육안 확인 대기) ③ 미발생 (대기) |

```bash
ssh root@orionhunter7.cafe24.com "
  START='2026-09-30 16:33:05'
  J(){ journalctl -u tradebot --since \"\$START\" --no-pager 2>/dev/null; }
  echo '-- (1) 강제 매수 원자 경로 --'
  J | grep -E '\[FIXED-PRICE\]\[FORCE\]|\[LIMIT-FILL\] apply_entry' | tail -3
  J | grep -c 'POSITION-SYNC.*자동 복구'
  echo '-- (2) 승격 가드 --'
  J | grep -E 'SELL 차단 \(HOLD 유지\)|POS-DESYNC\] (streak|class=)' | tail -5
  echo '-- (3) WO-9 실전 --'
  J | grep -E 'HTS-DETECT\] HTS_BUY|LOCKED-QTY|AUDIT-REJECT' | tail -8
  sqlite3 'file:/root/upbit-tradebot-mvp/services/data/tradebot_mcmax33.db?mode=ro' \"SELECT id,timestamp,ticker,type,reason,note FROM audit_trades WHERE type LIKE '%REJECTED' ORDER BY id DESC LIMIT 5;\"
"
```

### 사후 확증 2건 (2026-10-01 WO-14 완결 시 편입)

세션을 시작할 때마다 아래 두 항목을 봅니다. 기한은 없습니다. 기준 시각은 WO-14 재시작 시각 `2026-10-01 11:42:01` 입니다.

| 번호 | 항목 | 확인 내용 | 2026-10-01 관측 창 상태 |
|---|---|---|---|
| 4 | WO-14 (a) 미확정 봉 제외 | `[BACKFILL] 미확정 봉 제외 \| ts=T` 가 나오면, 봉 T 의 `audit_buy_eval`·`audit_sell_eval` 행이 다음 주기 실시간 평가 1행뿐이고 `backfill_type` 이 비어 있는지 확인 | 11:50:10 발화 1회 → 11:50 봉 `audit_buy_eval` id 74837 (11:55:11 실시간, 확정 종가 734, backfill 없음), `audit_sell_eval` 0행 (확증 1회, 재발 시 같은 방법으로 확인) |
| 5 | WO-14 E1 Trailing 상태 복원 | 포지션 보유 중 BACKFILL 이 나오면 `[BACKFILL] trailing 상태 복원 \| highest old→new 되돌림` 의 new 가 BACKFILL 직전 고점과 같은지 확인. `trailing 상태 복원 건너뜀` · `trailing 상태 복원 실패` 는 0 이어야 함 | 미발생 (관측 창 동안 포지션 없음, 대기) |

```bash
ssh root@orionhunter7.cafe24.com "
  START='2026-10-01 11:42:01'
  J(){ journalctl -u tradebot --since \"\$START\" --no-pager 2>/dev/null; }
  echo '-- (4) 미확정 봉 제외 --'
  J | grep -F '미확정 봉 제외' | tail -5
  echo '-- (5) trailing 복원 --'
  J | grep -F 'trailing 상태 복원' | tail -5
"
```

### 사후 확증 6번 (2026-10-01 WO-18 완결 시 편입)

세션을 시작할 때마다 봅니다. 기한은 없습니다. 기준 시각은 WO-18 재시작 시각 `2026-10-01 18:10:24` 입니다.

| 번호 | 항목 | 확인 내용 | 2026-10-01 관측 창 상태 |
|---|---|---|---|
| 6 | WO-18 hts_buy 해제 사이클 | 다음 HTS 매수 → 봇 매도 사이클에서 ① `[HTS-DETECT] HTS_BUY 감지` + `HTS 매수 플래그 설정` ② 그 포지션의 봇 매도 체결 직후 `[HTS-FLAG] cleared \| reason=bot_sell \| ticker=…` 1줄 ③ 다음 봇 매수의 `STOP_LOSS_CHECK … hts_buy=False`. 외부 매도로 끝나면 ② 대신 `reason=sync_all_positions_cleared` 또는 `position_sync_wallet_zero` | 미발생 (대기). 기동 정합 검사로 잔존 89행 해제 확인(18:10:31) |

```bash
ssh root@orionhunter7.cafe24.com "
  START='2026-10-01 18:10:24'
  J(){ journalctl -u tradebot --since \"\$START\" --no-pager 2>/dev/null; }
  echo '-- (6) HTS 매수 감지 / 플래그 설정 --'
  J | grep -E 'HTS-DETECT\] HTS_BUY|HTS 매수 플래그 설정' | tail -5
  echo '-- (6) 플래그 해제 (boot_reconcile 제외) --'
  J | grep -F '[HTS-FLAG] cleared' | grep -v boot_reconcile | tail -5
  echo '-- (6) 해제 뒤 SELL 평가 hts_buy 값 --'
  J | grep -F 'STOP_LOSS_CHECK' | grep -oE 'hts_buy=(True|False)' | sort | uniq -c
  sqlite3 'file:/root/upbit-tradebot-mvp/services/data/tradebot_mcmax33.db?mode=ro' \"SELECT COUNT(*) FROM account_positions WHERE meta LIKE '%\\\"hts_buy\\\": true%' AND COALESCE(virtual_coin,0)+COALESCE(virtual_coin_locked,0)=0;\"
"
```

- 2026-10-02 정기 점검 기록: 외부 매도 경로 2회 확인 — KRW-SNT(HTS_BUY_ADD 10-01 22:19·22:20 → `[HTS-FLAG] cleared | reason=sync_all_positions_cleared` 10-02 00:18:50), KRW-QKC(HTS_BUY 06:31:44 → 07:58:50 같은 사유). 봇 매수(KRW-JTO 10-02 03:40) SELL 평가 `hts_buy=False`. 봇 매도 해제 경로(`reason=bot_sell`)는 아직 미발생(JTO 외부 매수 없음).

### 사후 확증 7번 (2026-10-02 WO-17 (S2) 편입)

세션을 시작할 때마다 봅니다. 기한은 없습니다. 기준 시각은 WO-17 (S) 재시작 시각 `2026-10-01 20:10:55` 입니다. **로그 출처는 `journalctl -u tradebot`** 입니다(`mcmax33_engine_debug.log` 는 `log_to_file` 이벤트만 기록 — 보조 출처).

| 번호 | 항목 | 확인 내용 | 2026-10-02 정기 점검 상태 |
|---|---|---|---|
| 7 | WO-17 (S) 긴 이력 시드 | 기동마다 `[WARMUP] 시드 방식=long_history bars=800` 1줄, `긴 이력 시드 실패`·`시드 방식=sma200` 0건, `scripts/wo17s_verify_seed.py` 로 로그 시드 값과 1,200봉 장기 기준 차이 EMA60·EMA200 모두 **0.1원 이내**, fast−slow 부호 같음 | 기동 1회(10-01 20:11:02) 확인 — 1줄·폴백 0, 차이 −0.0000 / −0.0002, 부호 같음(역배열) |

```bash
ssh root@orionhunter7.cafe24.com "
  START='2026-10-01 20:10:55'
  J(){ journalctl -u tradebot --since \"\$START\" --no-pager 2>/dev/null; }
  echo '-- (7) 기동별 시드 방식 --'
  J | grep -E 'BOOT-RESUME\] success|시드 방식=' | sed -E 's/^.*\]: //'
  echo \"긴 이력 시드 실패: \$(J | grep -cF '긴 이력 시드 실패')  sma200: \$(J | grep -cF '시드 방식=sma200')\"
"
# 각 기동의 [WARMUP] 시각·ema_fast·ema_slow 로 (로컬, Upbit 공개 API):
python3 scripts/wo17s_verify_seed.py "<기동 [WARMUP] 시각 KST>" <ema_fast> <ema_slow> 1200
```

```bash
ssh root@orionhunter7.cafe24.com "
  # 자연 발생 강제 매수 감지 (2026-09-12 17:24 배포 이후 전체 창)
  journalctl -u tradebot --since '2026-09-12 17:24:07' --no-pager 2>/dev/null \
  | grep -E '\[FIXED-PRICE\]\[FORCE\]|reason.*force_buy|force_buy_in' \
  | head -20
"
```

- **발생 0건**: WO-8 자연 발생 관측 대기 상태 유지. 검증 미완결. 다음 세션에서 다시 조회.
- **발생 1건 이상**: 아래 §4-a ~ §4-d 4항목을 그 이벤트의 uuid·시각으로 실측 후 완결 판정.

### 검증 항목 4종

#### (a) 발주 로그 확인
```
[FIXED-PRICE][FORCE] 고정가 강제 매수 진입 | price=... ticker=KRW-JTO wait_bars=5 effective_timeout≈1495s
[UPBIT-ORDER] → POST /v1/orders payload={..., 'ord_type': 'limit', ...}
```
- `wait_bars=5`, `effective_interval_sec = 300 × 5 = 1500`, `timeout = max(5, 1500-5) = 1495`초
- **`interval_sec=1500` 확인 필수** (이 값이 60·180·900 등 다른 값이면 봉 간격 출처 결함, 즉시 롤백)

#### (b) 체결 케이스: `[LIMIT-FILL] apply_entry` + 이후 첫 봉 `[POSITION-SYNC]` 부재
```
[LIMIT-FILL] apply_entry 완료 | uuid=... qty=... price=... entry_bar=N ts=...
```
- 이후 첫 봉 SELL 평가에서 **`[POSITION-SYNC] 자동 복구` 로그 부재** = WO-8 정상 (`apply_entry` 정상 관문 경유)
- `[POSITION-SYNC] 자동 복구` 1건 이상 발화 시 = **즉시 롤백** (강제 매수(현재가) 체결이 `apply_entry` 우회)

#### (c) 미체결 취소 케이스: `[FORCE]` prefix 알림 발송
```
⏱ [OR] LIMIT BUY timeout 도달 → cancel 시도 | uuid=... elapsed=... timeout=1495s
[OR] cancel_order resp uuid=...
```
- 텔레그램/대시보드 알림: **`⏱ [FORCE] 강제 매수(현재가) 미체결 → 자동 취소 — KRW-JTO`** (WO-11 이전 배포본 문구: `강제 매수 지정가 미체결`) (`meta.reason=force_buy` 감지로 [FORCE] prefix 붙음)
- 안내 문구: `→ 사용자 강제 매수 요청 취소됨. 필요 시 재발주`

#### (d) audit_trades `reason=force_buy` 행 `entry_price` 정상 기재
```sql
-- SSH: sqlite3 /tmp/tradebot_ro_$(date +%s).db (사본 조회, 잠금 회피)
SELECT id, timestamp, ticker, type, reason, price, entry_price, bars_held
  FROM audit_trades
 WHERE reason = 'force_buy'
   AND timestamp >= '2026-09-12T17:24:07'
 ORDER BY timestamp DESC;
```
- `entry_price` 컬럼이 **NULL/0 아닌 정상 값** (체결가와 근접) 확인
- 체결 uuid의 `orders.avg_price`와 대조 검증

### 완결 판정

**(a) + (b 또는 c) + (d)** 3항목 모두 통과 시 WO-8 검증 완결. 하나라도 실패 시 결과 인용 후 §7.2 롤백 트리거 대상 여부 판단·사용자 재판정 대기.

---

## 확인 4-W12 · WO-12 2단계 — 기동 방식 전환 (운영자 지정 시각에만 실행)

> **실행 완료 (2026-10-01 09:55:59, 통과)** — 현재 기동 방식은 `scripts/tradebot_boot.py` 입니다. 이후 재시작에서는 대시보드 접속 없이 엔진이 자동 재개됩니다(`[BOOT-RESUME] success` 확인). 결과는 `docs/plans/2026-09-30-wo12-boot-auto-resume/plan.md` §11. 아래 절차는 재적용·되돌리기 참고용으로 둡니다.

2026-09-30 1단계에서 코드(`d12f47b` 계열)만 배포했습니다. 기동 방식은 기존 `streamlit run` 그대로입니다. 2단계는 **운영자가 시각을 따로 지정했을 때만** 실행합니다. 지시 전에는 실행하지 않습니다.

**사전 조건**: 1단계 백업이 `/root/backup/` 에 있어야 합니다 (`tradebot.service.20260930`, `tradebot.service.d.20260930/`, `tradebot.ExecStart.before.20260930`). 없으면 먼저 만듭니다.

**절차 (서버, 순서대로)**

1. drop-in 생성 — 파일 `/etc/systemd/system/tradebot.service.d/wo12-boot.conf`, 내용 3줄. 여러 줄 파일은 heredoc 을 쓰지 않고 `printf` 한 줄로 만듭니다(규칙 v2.9).
   - `printf '[Service]\nExecStart=\nExecStart=/root/upbit-tradebot-mvp/venv/bin/python /root/upbit-tradebot-mvp/scripts/tradebot_boot.py\n' > /etc/systemd/system/tradebot.service.d/wo12-boot.conf`
   - `cat /etc/systemd/system/tradebot.service.d/wo12-boot.conf` 로 3줄 확인
2. `systemctl daemon-reload`
3. `systemctl show tradebot -p ExecStart` — `argv[]=/root/upbit-tradebot-mvp/venv/bin/python /root/upbit-tradebot-mvp/scripts/tradebot_boot.py` 인지 인용
4. `systemctl restart tradebot` → `systemctl is-active tradebot` → `systemctl show tradebot -p ExecMainStartTimestamp` → `ss -ltnp | grep 8501`
5. **대시보드에 접속하지 않고** 관측합니다. 기준 시각 `S` = `systemctl show tradebot -p ExecMainStartTimestamp --value`, 조회는 `journalctl -u tradebot --since "$S" --no-pager` 에 `grep -F` 고정 문자열.

**통과 조건 (접속 없이)**

| 순서 | 확인 | 기대 |
|---|---|---|
| 1 | 재시작 1분 안 `[BOOT-RESUME] success user=mcmax33 mode=LIVE` | 1줄 |
| 2 | `[migrate] … OK (user_id=mcmax33)` (`ensure_settings_history_schema` 제외) | 14줄 |
| 3 | `[BOOT] run_live_loop start` | 1줄 |
| 4 | JTO 포지션 보유 시 `[BOOT-SEED] source=upbit_avg_buy_price entry=… qty=…` · seed 실패 CRITICAL | 1줄 · 0건 |
| 5 | 사람 접속 없이 첫 `[CONFIRMED] 봉 처리 완료` · 그때까지 `[AUTO-RESUME]` | 발생 · 0건 |
| 6 | 30분: `[POS-DESYNC] class=pos_desync_promoted` · `class=integrity_gap` · `[SKIP-BAR]` · `POLLUTED` · 엔진 Traceback | 모두 0건 |
| 7 | 30분: Bar# | 5봉 이상 |
| 8 | 그 뒤 운영자 접속 1회: `[AUTO-RESUME] skip (boot-resume 로 이미 실행 중)` · 새 `[BOOT] run_live_loop start` | 1줄 · 추가 0건 (엔진 스레드 1개) |

**이상 시 되돌리기 (코드는 유지)**

1. `rm -f /etc/systemd/system/tradebot.service.d/wo12-boot.conf`
2. `systemctl daemon-reload`
3. `systemctl show tradebot -p ExecStart` — 원래 `argv[]=/root/upbit-tradebot-mvp/venv/bin/streamlit run app.py --server.port=8501 --server.address=0.0.0.0` 확인
4. `systemctl restart tradebot` → `systemctl is-active tradebot`
5. 기존 방식이므로 운영자 대시보드 접속으로 엔진을 시작합니다.

---

## 확인 5 · CRITICAL 알림 등급 재조정 (실전 관측)

**24시간 실측 창** (2026-09-12 17:24:07 ~ 2026-09-13 17:24:07) 관측 대상:

| 이벤트 | 예상 발화 |
|---|---|
| HTS 매수 감지 후 첫 봉 `bars_held=0` | **WARN 강등** (`pos_desync_warn`) |
| 자동 복구 성공 (다음 봉 `POSITION-SYNC`) | streak 리셋 → 이후 재발 시 WARN부터 재시작 |
| HTS 매수 후 2봉 연속 `bars_held=0` | **CRITICAL 승격** (`pos_desync_promoted`) |
| `hts_buy=False` + 진짜 결손 | **CRITICAL 유지** (기존 `pos_desync`) |

- WARN dedupe TTL 600초, CRITICAL dedupe TTL 300초. 두 흐름은 분리 관측.

---

## 롤백 트리거 (§7.2)

1. 배포 30분 내 엔진 계열 Traceback 1건 이상
2. 강제 매수(현재가) 체결 직후 첫 봉 SELL 평가에서 `[POSITION-SYNC] 자동 복구` 로그 1건 이상
3. 강제 매수가 현재가 매수 활성 상태인데 `buy_market` 발주 (분기 실패)
4. `#14 fixed_buy_timeout` 알림 발송 실패
5. 커버리지 회귀 (`docs/plans/2026-09-12-post-check/coverage-and-critical.md` 산식 <95%)
6. `pos_desync_promoted` 알림이 정상 매매 봉에 반복 발화 (승격 가드 오탐)

**롤백 절차**:
```bash
git revert de28fea
git push
ssh root@orionhunter7.cafe24.com "cd /root/upbit-tradebot-mvp && git pull && systemctl restart tradebot"
```

**대상 상태**: `0e6d37d` (직전 커밋 = docs 사후 문서, 그 다음이 이전 서버 HEAD `53fdbf3`)

---

## 부록 · 버전 이력 추적

| 버전 | 커밋 | 시각 (KST) | 목적 |
|---|---|---|---|
| `v1.2026.09.04.1931` | `53fdbf3` | 2026-09-04 19:43 | dashboard 손익 표시 (배포 전 서버 상태) |
| ~~`v1.2026.09.12.1659`~~ | ~~`7d75a10`~~ (fixup으로 사라짐) | 2026-09-12 16:59 | WO-8 본체 초기 커밋 |
| ~~중간 갱신~~ | ~~`1618030`~~ (fixup으로 사라짐) | 2026-09-12 17:15 | 후속 보완 (승격 가드 + 봉 간격 출처). **여기서 1659 → 1715로 갱신** |
| **`v1.2026.09.12.1715`** | **`de28fea`** (main HEAD) | 2026-09-12 17:01 (커밋 시각 · fixup 결과) | **WO-8 최종본** (본체 + 후속 보완 squash) |

**커밋 메시지 헤더의 `v1.2026.09.12.1659` 표기는 초기 `7d75a10` 시점 값이며 실제 코드 반영본은 `v1.2026.09.12.1715`** (fixup으로 후속 보완 흡수됨).
