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

## 확인 4 · 강제 매수 1회 실 발주 (운영자 협조 필요)

**대시보드 → 🛑 강제매수하기 클릭 1회**로 다음을 순차 실측한다.

### 4-1. 발주 로그
```
[FIXED-PRICE][FORCE] 고정가 강제 매수 진입 | price=... ticker=KRW-JTO wait_bars=5 effective_timeout≈1495s
[UPBIT-ORDER] → POST /v1/orders payload={..., 'ord_type': 'limit', ...}
```
- `wait_bars=5`, `effective_interval_sec = 300 * 5 = 1500`, `timeout = max(5, 1500-5) = 1495`초
- 대시보드에 `ℹ️ 지정가 매수 활성 상태. 강제 매수도 지정가로 발주되며 최대 5봉 내 미체결 시 자동 취소됩니다.` 안내 caption 표시

### 4-2. 체결 케이스 (지정가 즉시 체결)
```
[LIMIT-FILL] apply_entry 완료 | uuid=... qty=... price=... entry_bar=N ts=...
```
- 이후 첫 봉 SELL 평가에서 **`[POSITION-SYNC] 자동 복구` 로그 부재** = WO-8 정상 (`apply_entry` 정상 관문 경유)
- `[POSITION-SYNC] 자동 복구` 발화 시 = **즉시 롤백** (강제 매수 지정가가 `apply_entry` 우회)

### 4-3. 미체결 취소 케이스 (지정가 미체결로 봉 경계 취소)
```
⏱ [OR] LIMIT BUY timeout 도달 → cancel 시도 | uuid=... elapsed=... timeout=1495s
[OR] cancel_order resp uuid=...
```
- 텔레그램/대시보드 알림: **`⏱ [FORCE] 강제 매수 지정가 미체결 → 자동 취소 — KRW-JTO`** (`meta.reason=force_buy` 감지로 [FORCE] prefix 붙음)
- 안내 문구: `→ 사용자 강제 매수 요청 취소됨. 필요 시 재발주`

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
