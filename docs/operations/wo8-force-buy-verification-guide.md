# WO-8 강제 매수 지정가 이식 · 배포 후 검증 가이드

**작성일**: 2026-09-12
**대상 커밋**: `de28fea` (main, squash 결과 · 서버 반영 완료)
**대상 대시보드 버전**: **`v1.2026.09.12.1715`**
**배포 시각**: 2026-09-12 17:24:07 KST (ExecMainStartTimestamp)

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
| `core.strategy_incremental \| ❌ [EMA] ... CRITICAL` | 승격 가드 미포함 (진짜 결손) | **0건** |
| `pos_desync_promoted` | 승격 가드 CRITICAL 승격 발화 | **0건** (자동 복구 실패 사례) |
| `Traceback` (엔진 계열) | core/engine/services/ 계열 | **0건** |
| `Traceback` (Streamlit UI) | `issue-18-streamlit-ui-tracebacks.md`로 분리 집계 | 카운트만 |

**검증 명령**:
```bash
ssh root@orionhunter7.cafe24.com "
  START='2026-09-12 17:24:07'
  END='2026-09-12 17:54:07'
  echo 'SKIP-BAR:  ' \$(journalctl -u tradebot --since \"\$START\" --until \"\$END\" --no-pager 2>/dev/null | grep -c 'SKIP-BAR')
  echo 'POLLUTED:  ' \$(journalctl -u tradebot --since \"\$START\" --until \"\$END\" --no-pager 2>/dev/null | grep -c 'POLLUTED')
  echo 'CRITICAL:  ' \$(journalctl -u tradebot --since \"\$START\" --until \"\$END\" --no-pager 2>/dev/null | grep 'core\.strategy_incremental' | grep -c 'CRITICAL')
  echo 'promoted:  ' \$(journalctl -u tradebot --since \"\$START\" --until \"\$END\" --no-pager 2>/dev/null | grep -c 'pos_desync_promoted')
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

- 크로스 발생 시 `EMA Golden Cross detected` → `action=BUY` → `LIMIT-FILL apply_entry 완료` (지정가 활성일 때) 또는 `BUY 체결` (시장가일 때) 로그 관측
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
  echo '-- pos_desync_warn (외부 매수 첫 봉 방어) --'
  journalctl -u tradebot --since \"\$START\" --no-pager 2>/dev/null | grep 'pos_desync_warn' | wc -l
  echo '-- pos_desync_promoted (2봉 연속 승격) --'
  journalctl -u tradebot --since \"\$START\" --no-pager 2>/dev/null | grep 'pos_desync_promoted' | wc -l
"
```

발생 시 §확인 4-a 이하의 항목별 상세 검증을 진행한다. 기한 없음.

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
- `[POSITION-SYNC] 자동 복구` 1건 이상 발화 시 = **즉시 롤백** (강제 매수 지정가가 `apply_entry` 우회)

#### (c) 미체결 취소 케이스: `[FORCE]` prefix 알림 발송
```
⏱ [OR] LIMIT BUY timeout 도달 → cancel 시도 | uuid=... elapsed=... timeout=1495s
[OR] cancel_order resp uuid=...
```
- 텔레그램/대시보드 알림: **`⏱ [FORCE] 강제 매수 지정가 미체결 → 자동 취소 — KRW-JTO`** (`meta.reason=force_buy` 감지로 [FORCE] prefix 붙음)
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
2. 강제 매수 지정가 체결 직후 첫 봉 SELL 평가에서 `[POSITION-SYNC] 자동 복구` 로그 1건 이상
3. 강제 매수가 지정가 활성 상태인데 `buy_market` 발주 (분기 실패)
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
