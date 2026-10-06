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

> **배포 관찰 상설 항목 (2026-10-05 추가)**: 모든 배포의 30분 관찰에 "BUY/SELL 평가 통과 행 대 실제 체결 1:1 대조(통과·체결·취소·미요청 수)" 표를 넣는다 (`wo22d_match.py '<시작>' '<끝>'`).
>
> **설정 불변 기준 (2026-10-06 WO-24 배포 판정으로 정정)**: `settings_history` 행 수와 운영 설정 파일(`{user}_{EMA}_buy_sell_conditions.json`)의 sha256·수정 시각은 **운영자 접속 전후로 불변**이어야 한다. 이것으로 "페이지 열기만으로는 저장되지 않음" 을 확인한다. 기동 때마다 `strategy_init` 1행이 기록되는 것은 기존 동작이다. 투자자가 저장 버튼으로 바꾼 설정(`source_page=set_buy_sell_conditions`·`set_config`)은 어긋남이 아니다. 저장 시각, id, 바뀐 키를 별도로 기록한다 (2026-10-06 07:49·07:52 id 194·195 사례).

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

> **세션 개시 정기 점검 목록 (2026-10-04 추가, 10-05 10~12번·10-06 13번 편입)**: 사후 확인 1~13, 1분봉 거래 없는 봉 비율과 매매 건수(`[CONFIRMED-NO-TRADE]`·`Bar#`·`[CLOCK-CLOSE] 봉 확정 감지` 집계, `audit_trades`), 비밀 파일 권한(`.env`·`.streamlit/secrets.toml` 600, 백업 파일 없음 — `docs/operations/server-optimization.md` "비밀 파일 권한 점검 2026-10-04" 명령), **BUY/SELL 평가 통과 행 대 실제 체결 1:1 대조**(상설, 2026-10-05 추가 — 점검 창 안 `audit_buy_eval.overall_ok=1`·`audit_sell_eval.triggered=1` 행마다 봉 시작 ~ 뒤 2봉 안 orders 를 "체결·취소·미요청" 으로 분류해 수를 표로 적는다. 대조 스크립트: `docs/plans/2026-10-05-wo22-wallet-sync-entry/deploy/wo22d_match.py`).
>
> **이전 미체결 취소 확인 (WO-24 배포 전 구간)**: WO-24 배포 전의 현재가 매수 미체결 취소는 audit_trades 에 기록이 없다. `orders.state='CANCELED'` 이고 `executed_volume=0` 인 BUY 행(봇 주문)으로 확인한다 (예: 2026-10-04 14:16 orders 559 — `docs/plans/2026-10-05-urgent-buy-not-executed/report.md`). WO-24 배포 뒤부터는 감사 로그 페이지 "⏱ 매수 미체결 취소" 행으로 보인다.

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
# 각 기동의 [WARMUP] 시각·ema_fast·ema_slow 로 (로컬, Upbit 공개 API). 봉 간격은 그 기동의 운영 간격으로 지정:
python3 scripts/wo17s_verify_seed.py "<기동 [WARMUP] 시각 KST>" <ema_fast> <ema_slow> 1200 --interval <minute1|minute5|…>
```

- **봉 간격 인자 (2026-10-04)**: 검증 스크립트는 `--interval` 로 봉 간격을 받는다(`minute1`·`minute5` 또는 분 숫자). 인자가 없으면 params JSON(기본 `mcmax33_latest_params_EMA.json`, `--params` 로 변경)의 `interval` 을 읽는다. 출력 첫 줄 `봉 간격: minuteN (출처: …)` 이 **그 기동의 journal `[CLOCK] Initialized | timeframe=minuteN`** 과 같은지 먼저 확인한다. 지난 기동을 검증할 때는 지금 설정이 아니라 그 기동의 간격을 `--interval` 로 넣는다(2026-10-03 21:03:47 부터 minute1, 그 전은 minute5). 간격이 다르면 차이가 수 원 이상 나와 오판한다(10-04 실측: 5분봉 대조 +3.64 / −12.59, 1분봉 대조 +0.0000 / +0.0052).

### 사후 확증 8번 (2026-10-04 WO-20 완결 시 편입)

기준 시각은 WO-20 재시작 시각 `2026-10-04 10:22:33` 이다. 그 뒤 봇이 산 포지션을 보유한 채 재시작(배포·서비스 재시작)이 있었던 경우에만 본다. 기한은 없다. 로그 출처는 `journalctl -u tradebot` 이다. 배포 기동(10-04 10:22:33)은 포지션 없음이라 해당 없음(`[SEED] raw_last_open`·`[POSITION-APPLY] source=boot_seed`·`[BOOT-SEED]` 0건).

| 번호 | 항목 | 확인 내용 |
|---|---|---|
| 8 | WO-20 boot_seed 복원 | 그 기동에서 ① `[POSITION-APPLY] source=boot_seed … ts=<시각>` 1줄과 `🔁 Position recovered \| avg_price=… (출처: wallet) …` 1줄 ② `[BOOT-SEED] 봇 주문의 체결 시각 없음` WARNING 0건, `P3 boot seed 시각 복원 실패` 0건 ③ ① 의 `ts` 가 그 포지션 매수 주문의 체결 시각(`orders.executed_at`, WO-20 이전 주문은 `updated_at`)과 같음 ④ ① 의 `avg_price` 가 지갑 값(직전 `[POS-SYNC] avg_price 복구 성공 … avg_price=…`)과 같음 ⑤ 첫 SELL 평가가 정상 진행(`[MIN_HOLDING_CHECK] bars_held=` 양수, audit 보정 시 `audit fallback=` 줄) ⑥ **(WO-21, 2026-10-05 10:54:59 배포 뒤 기동부터 적용)** 보유 중 재시작 시 `[TRAILING-RESTORE] armed=… peak=… fixed=… activation=… 기준 봉 n개 시작=…` 1줄이 있고(또는 `재계산 불가 → 초기화 \| 사유=…` 1줄), 그 armed·peak 가 재시작 직전 `invariant_snapshots` 의 `trailing_armed`·`highest_price` 와 일치 (스냅샷은 봉 평가 직전 기록 — 재시작 전 마지막 행) |

- 같은 기동의 `[POS-SYNC] entry_ts 도 함께 복구 (sync 시각)` · `[POS-SYNC] avg_price 복구 성공` 은 WARNING 수준이지만 지갑 동기화의 정상 기록이다(이어서 boot_seed 가 entry_ts 를 주문 시각으로 덮는다). ② 의 "WARNING 0건" 대상이 아니다.
- 정체 포지션 판정의 `entry_time=` 은 보유 시간이 기준 시간을 넘은 봉에서만 `[STALE_POSITION_CHECK]` 줄에 찍힌다. 그 전에는 ① 의 `ts` 로 판정한다.
- ⑥ 대조 명령: `sqlite3 'file:/root/upbit-tradebot-mvp/services/data/tradebot_mcmax33.db?mode=ro' "SELECT timestamp, trailing_armed, highest_price FROM invariant_snapshots WHERE ticker='KRW-JTO' AND timestamp < '<재시작 시각>' ORDER BY id DESC LIMIT 1;"` 와 journal `grep -F '[TRAILING-RESTORE]'`. 단, 재시작 직전 무장이 BACKFILL 오염(매수 전 봉 재평가)으로 생긴 것이면 일치하지 않는 것이 맞다 (WO-21 조사 보고 B2 정정 사례).

```bash
ssh root@orionhunter7.cafe24.com "
  START='<재시작 시각 KST>'
  J(){ journalctl -u tradebot --since \"\$START\" --no-pager 2>/dev/null | sed -E 's/^.*\]: //'; }
  echo '-- (8) boot_seed 적용 / 지갑 동기화 --'
  J | grep -E 'POSITION-APPLY\] source=boot_seed|Position recovered|POS-SYNC\] (avg_price 복구 성공|entry_ts 도 함께)' | head -6
  echo \"[BOOT-SEED] WARNING: \$(J | grep -cF '[BOOT-SEED] 봇 주문의 체결 시각 없음')  P3 문구: \$(J | grep -cF 'P3 boot seed 시각 복원 실패')\"
  J | grep -E 'MIN_HOLDING_CHECK|audit fallback' | head -3
  sqlite3 'file:/root/upbit-tradebot-mvp/services/data/tradebot_mcmax33.db?mode=ro' \"SELECT id, executed_at, updated_at, avg_price, entry_bar FROM orders WHERE side='BUY' AND state='FILLED' ORDER BY COALESCE(executed_at, updated_at, timestamp) DESC LIMIT 1;\"
"
```

### 사후 확증 9번 (2026-10-04 WO-20 완결 시 편입)

기준 시각은 WO-20 재시작 시각 `2026-10-04 10:22:33` 이다. 배포 뒤 첫 체결 확정 주문 1건을 본다(이후 정기 점검에서는 표본 확인). 로그 출처는 `journalctl -u tradebot` 이다.

| 번호 | 항목 | 확인 내용 |
|---|---|---|
| 9 | WO-20 체결 시각 기록 | 배포 뒤 첫 확정 주문에서 ① `[OR] final FILLED … executed_at=<시각> canceled_at=None` (취소 확정이면 `final CANCELED … canceled_at=<시각>`) ② 그 `orders` 행의 `executed_at` 이 ① 과 같고, Upbit `GET /v1/order?uuid=` 의 `trades[].created_at` 마지막 값과 **수 초 이내** ③ 취소 확정이면 `canceled_at` 이 있음 ④ `[OR] executed_at 대체`(trades 없음) 0건 |

```bash
ssh root@orionhunter7.cafe24.com "
  START='2026-10-04 10:22:33'
  J(){ journalctl -u tradebot --since \"\$START\" --no-pager 2>/dev/null | sed -E 's/^.*\]: //'; }
  echo '-- (9) 확정 로그 --'
  J | grep -F '[OR] final' | head -3
  echo \"executed_at 대체: \$(J | grep -cF '[OR] executed_at 대체')\"
  sqlite3 'file:/root/upbit-tradebot-mvp/services/data/tradebot_mcmax33.db?mode=ro' \"SELECT id, side, state, executed_at, canceled_at, updated_at, provider_uuid FROM orders WHERE id > 558 ORDER BY id LIMIT 3;\"
"
# ② Upbit 대조는 조회 전용 스크립트(docs/plans/2026-10-02-wo20-executed-at/results/wo20_b3.py 와 같은 GET /v1/order)로 uuid 를 넣어 확인한다.
```

- 2026-10-05 확인 (WO-21 배포 0단계): 10-04 10:22:33 이후 확정 주문 6건 — 첫 확정 id 559 `CANCELED`(canceled_at 2026-10-04T14:21:12, trades 0, executed_at 없음 — 정상), FILLED 5건(id 560~564) 모두 `executed_at` 이 Upbit `trades[].created_at` 마지막 값과 **0.0초** 차이. `[OR] executed_at 대체` 0건. **사후 확증 9번 통과.**

### 사후 확증 10번 (2026-10-05 WO-21 완결 시 편입)

기준 시각은 WO-21 재시작 시각 `2026-10-05 10:54:58` 이다. 배포 뒤 첫 봇 포지션 1개를 본다. 로그 출처는 `journalctl -u tradebot` 이다.

| 번호 | 항목 | 확인 내용 |
|---|---|---|
| 10 | WO-21 무장 로그·ts_armed | 배포 뒤 첫 봇 포지션에서 ① 무장 로그가 이전 형태로 1회 남음: `🔓 Trailing Stop ACTIVATED \| entry=₩… initial_highest=₩…` · `🔒 고정 금액 폭 설정 \| 활성화 수익=₩… × 30% = ₩…` · `🔄 AUTO-SWITCH: Take Profit 도달 (…%) → Trailing Stop 활성화 (고정폭) …` (재생은 로그를 남기지 않으므로 실시간 무장에서만) ② 무장 뒤 봉의 `audit_sell_eval.ts_armed` 가 1, 무장 전 봉은 0 |

```bash
ssh root@orionhunter7.cafe24.com "
  START='2026-10-05 10:54:58'
  J(){ journalctl -u tradebot --since \"\$START\" --no-pager 2>/dev/null | sed -E 's/^.*\]: //'; }
  echo '-- (10) 무장 로그 --'
  J | grep -E 'Trailing Stop ACTIVATED|고정 금액 폭|AUTO-SWITCH' | head -6
  sqlite3 'file:/root/upbit-tradebot-mvp/services/data/tradebot_mcmax33.db?mode=ro' \"SELECT bar_time, price, highest, ts_armed, triggered, trigger_key FROM audit_sell_eval WHERE ticker='KRW-JTO' AND timestamp >= '2026-10-05T10:54:58' ORDER BY id LIMIT 40;\"
"
```

### 사후 확증 11·12번 (2026-10-05 WO-24 배포 시 편입)

기준 시각은 WO-22 재시작 `2026-10-05 15:18:44` (11번)과 WO-24 재시작 `2026-10-05 16:44:46` (12번)이다. 로그 출처는 `journalctl -u tradebot` 이다. 해당 사건이 처음 생겼을 때 1회 본다.

| 번호 | 항목 | 확인 내용 |
|---|---|---|
| 11 | WO-22 진입가 출처·외부 매도 기록 | ① KRW-JTO 포지션이 지갑 동기화로 생기면 `[POSITION-SYNC] entry_price=… (출처: …)` 1줄. 출처는 `upbit_avg` 가 먼저다. 없을 때만 `account_positions`, 수량이 맞을 때만 `orders` 를 쓴다. ② 앱 전량 매도로 지갑이 0 이 되면 `[POSITION-SYNC] 외부 매도 기록 (audit_trades HTS_SELL)` 1줄과 audit_trades `type='HTS_SELL'` 1행. price 는 비어 있고 손익 집계에서 빠진다. 감사 로그 페이지에 "외부 매도" 로 보인다. |
| 12 | WO-24 미체결 취소 기록 | 첫 현재가 매수 미체결 취소 때 ① `⏱ [OR] LIMIT BUY timeout 도달 → cancel 시도` 다음 `[OR] 매수 미체결 취소 기록 (audit_trades BUY_CANCELED)` 1줄 ② audit_trades `type='BUY_CANCELED'` 1행. price 는 주문가, qty 는 주문 수량, note 는 "대기 N봉 내 체결 없음" + 전환 결과다. 옵션이 꺼져 있으면 "→ 취소 (미체결 시 시장가 전환 꺼짐)". ③ 감사 로그 페이지 유형 필터 "미체결 취소" 에서 옅은 노란 행 "⏱ 매수 미체결 취소" 로 보인다. ④ 같은 uuid 의 orders 행이 `state=CANCELED`. |

```bash
ssh root@orionhunter7.cafe24.com "
  J(){ journalctl -u tradebot --since \"\$1\" --no-pager 2>/dev/null | sed -E 's/^.*\]: //'; }
  echo '-- (11) 진입가 출처·외부 매도 --'
  J '2026-10-05 15:18:44' | grep -E '\[POSITION-SYNC\] (entry_price=|외부 매도 기록|orders 마지막 봇 BUY 수량 불일치)' | head -6
  sqlite3 'file:/root/upbit-tradebot-mvp/services/data/tradebot_mcmax33.db?mode=ro' \"SELECT id, timestamp, ticker, type, price, qty FROM audit_trades WHERE type='HTS_SELL' AND timestamp >= '2026-10-05T15:18:44' ORDER BY id;\"
  echo '-- (12) 미체결 취소 --'
  J '2026-10-05 16:44:46' | grep -E 'LIMIT BUY timeout|매수 미체결 취소 기록|UNFILLED-CONVERT' | head -6
  sqlite3 'file:/root/upbit-tradebot-mvp/services/data/tradebot_mcmax33.db?mode=ro' \"SELECT id, timestamp, ticker, price, qty, note FROM audit_trades WHERE type='BUY_CANCELED' ORDER BY id;\"
"
```

### 사후 확증 13번 (2026-10-06 WO-24 완결 시 편입)

투자자가 2026-10-06 07:49:19 설정 저장(settings_history id 194)으로 "미체결 시 시장가 전환" 을 켰다 (허용 0.3%). 기준 시각은 이 시각이다.

| 번호 | 항목 | 확인 내용 |
|---|---|---|
| 13 | 미체결 시 시장가 전환 (켜짐) | 켜진 상태에서 첫 현재가 매수가 timeout 될 때 아래를 본다. ① `⏱ [OR] LIMIT BUY timeout 도달 → cancel 시도` 다음 `[UNFILLED-CONVERT]` 로그. 전환됐으면 `✅ [UNFILLED-CONVERT] 시장가 전환 \| from=… to=…`, 가격 차이가 허용을 넘었으면 `[UNFILLED-CONVERT] 전환 안 함 \| … 가격 차이 x% > 허용 y%`. ② 전환됐으면 시장가 매수 orders 1행(meta `unfilled_convert`·`converted_from`)과 `[POSITION-APPLY]` 등록 (`source=bot_market_convert`). ③ audit_trades `BUY_CANCELED` 행의 note 에 "→ 시장가 전환 (현재가 …, 차이 x% ≤ 허용 y%)" 또는 "→ 전환 안 함 (…)". |

```bash
ssh root@orionhunter7.cafe24.com "
  journalctl -u tradebot --since '2026-10-06 07:49:19' --no-pager | sed -E 's/^.*\]: //' | grep -E 'LIMIT BUY timeout|UNFILLED-CONVERT|POSITION-APPLY|매수 미체결 취소 기록' | head -8
  sqlite3 'file:/root/upbit-tradebot-mvp/services/data/tradebot_mcmax33.db?mode=ro' \"SELECT id, timestamp, price, qty, note FROM audit_trades WHERE type='BUY_CANCELED' AND timestamp >= '2026-10-06T07:49:19' ORDER BY id;\"
"
```

### 기동 이전 봉의 BUY 평가 근거 찾기 (2026-10-02 WO-19 편입)

WO-19 배포 전까지는 엔진이 기동할 때마다 워밍업이 직전 약 200봉(5분봉 기준 약 16.7시간)의 `audit_buy_eval` 실제 판정 행을 "⏳ WARMUP 진행 중"(`checks.status=WARMUP`, `overall_ok=0`) 자리표시자로 덮어썼다(최근 7일 KRW-JTO 539행, 예: 2026-10-01 14:10 봉 id 74864). 이미 덮인 행은 복원하지 않으므로, 감사 로그 페이지의 BUY 평가가 WARMUP 으로 보이는 기동 이전 봉의 판정 근거는 **journal(`journalctl -u tradebot`)의 `🔔 EMA Buy Signal | fast=… slow=…` 줄과 `📊 Bar#… | action=…` 줄**, 그리고 **`mcmax33_engine_debug.log` 의 봉 요약 `cross=Golden/Dead | ema_fast=… | ema_slow=…` 줄**(보조 출처)에서 찾는다. 실제 매매 여부는 `audit_trades`(덮이지 않음)로 확인한다. WO-19 배포 뒤 기동부터는 워밍업이 실제 판정 행을 건드리지 않으며, 기동마다 `[WARMUP] 감사 행 보존 | kept=N inserted=M updated_placeholder=K` 1줄이 남는다.

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
