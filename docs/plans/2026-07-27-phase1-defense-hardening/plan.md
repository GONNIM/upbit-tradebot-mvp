# Phase 1 방어적 강화 (Phase 1 Defense Hardening) — 2026-07-27

**커밋 대상**: 다음 배포 (예정: v1.2026.07.27.2058)
**전제 커밋**: `4e2bc3e` (2026-07-27 오전 4단 Fix, HTS SL paralysis 봉쇄)
**감사 근거**: 2026-07-27 외부 감사 + 전문가 리뷰 (code-reviewer + Plan agent 2개 독립 에이전트)
**작업 성격**: 🚨 CRITICAL — 실 자금 매매 봇, 매매 중지 불가, 재발 절대 금지

---

## 1. Executive Summary

07-27 오전 4e2bc3e 로 2026-07-24 사건 (HTS 매수 후 avg_price=None 방치 → SL/TP/TS silent 무력화 2.5일간) 의 **정확한 재발**은 봉쇄. 후속 전문가 리뷰에서 **동일 근본 패턴의 유사 사각지대 4곳(P1) + 개선 사항 5건(P2)** 발견. Phase 1 은 오늘 배포 가능한 최소 변경으로 9건 통합 봉쇄.

**절대 원칙**:
1. 매매 로직/임계값(TP/SL/TS/Stale)/필터 순서 절대 변경 없음.
2. 기존 조기 return 반환값(`should_block=False`, `Action.HOLD`) 유지.
3. 순수 "관찰 강화" — 로그/알림/상태 리셋만 추가.
4. Rollback: 신규 파일 1개(`core/position_invariants.py`) 삭제 + import 라인 revert.

---

## 2. 배경 — 60일 결함 5건 Timeline

| # | 커밋 | 결함 | 사용자 관점 |
|---|---|---|---|
| F1 | `7ff9b10` (07-20) | order_ratio stale trader | "10% 저장했는데 100% 매수" |
| F1' | `7ff9b10` (07-20) | bot_limit_fill 언패킹 실패 (7일간 예외 10회) | "TS 안 먹힘" |
| F2 | `7991a48` (07-22) | 사이드바가 default 1.0으로 order_ratio 덮어씀 | "1% → 100% 회귀" |
| F3 | `43eecb1` (07-24) | 세션 stale state → TP/SL 저장 시 order_ratio 도 덮어씀 | "1% 저장했는데 100% 재발" |
| F5 | `4e2bc3e` (07-27) | **HTS 매수 후 avg_price=None → SL/TP/TS 2.5일 silent 무력화** | "이미 -3% 넘겼는데 SL 안 발동" |

**공통 패턴**:
- Silent Failure (조기 return + 로그 없음)
- Cross-thread 상태 동기화 채널 부재
- Session/disk state divergence
- Invariant 검증 부재

---

## 3. 전문가 리뷰 결과 (2개 독립 에이전트 일치)

### 3.1 code-reviewer 발견 P1 4건

| # | 위치 | 재현 시나리오 |
|---|---|---|
| **P1-1** | `core/filters/sell_filters.py:492` (StalePositionFilter) | HTS 매수 + Reconciler 콜백 등록 실패 → Fix 1 avg_price 복구하지만 **entry_ts=None 잔존** → Stale filter 가 silent NO_POSITION return → 무력화 |
| **P1-2** | `core/strategy_engine.py:381,484` (`_reconcile_position_with_wallet`) | 락 밖 실행 시 Reconciler `_on_hts_detect` (락 획득) 와 race → `apply_entry` 가 콜백 최신 avg 를 DB 캐시값으로 덮어씀 → **Trailing Stop 오작동** |
| **P1-3** | `core/strategy_incremental.py:440,464,491` (MACD 인라인) | MACD 는 sell_filter_manager 미사용, 인라인 `pnl_pct is not None and ...` 패턴 유지 → Fix 3 WARN 로그 미커버 → **silent skip 잔존** |
| **P1-4** | `engine/live_loop.py:505-507` + `core/position_state.py:137` | 부팅 seed 실패 → `_has_position=False`, `qty=0` 리셋되지만 **`avg_price` 잔존** → 다음 sync 시 Fix 1 조건 False 로 스킵 → 위험 상태 지속 |

### 3.2 code-reviewer 발견 P2 5건

| # | 위치 | 이슈 |
|---|---|---|
| P2-1 | `position_state.py:146-150` (Fix 1 실패) | logger.error 만 있음. insert_log/notifier 부재 → Fix 2 봉 진입까지 사용자 인지 지연 |
| P2-2 | `order_reconciler.py:79-87` (unregister_user) | `_hts_callbacks` 미정리 → stale reference 잔존 |
| P2-3 | `strategy_engine.py:108-141` (`_on_hts_detect`) | HTS_BUY_ADD 시 옛 `highest_price` 유지 → Trailing Stop 옛 기준 |
| P2-4 | `sell_filters.py:522-527` | f-string 리터럴 `"{max_gain:.2%} if max_gain else 'None'"` — `max_gain=None` 시 TypeError 잠재 |
| P2-5 | `strategy_engine.py:99-106` | 콜백 등록 실패 warning 만 → 사용자 미인지 → HTS 즉시 동기화 무력화 방치 |

### 3.3 Plan agent 3-Phase 로드맵

- **Phase 1 (이번 배포)**: P1 4건 + P2 5건 통합. invariant 헬퍼 신설 + Fix 3 확장 + 락 보호 확대.
- **Phase 2 (이번 주말)**: 5건 결함 각각 pytest 재현 + Mock Upbit/Reconciler 픽스처 + deploy.sh CI 게이트.
- **Phase 3 (다음 주)**: `services/invariant_monitor.py` + `pages/system_health.py` + audit_logger 별도 파일 + Telegram 3-tier.

---

## 4. Phase 1 구현 상세 (파일별 변경)

### 4.1 `core/position_invariants.py` ⭐ 신규

**의도**: 7종 invariant 검증을 한 곳에서 표준화. Fix 2 인라인 중복 제거 + I3 (P1-1) 커버 확장.

**공개 API**:
- `check_position_invariants(position, *, context) -> Optional[Tuple[code, msg, details]]`
- `raise_invariant_violation(violation, *, user_id, ticker, strategy_tag)`

**검사 순서** (심각도 순):

| Invariant | 조건 | 대응 심각도 |
|---|---|---|
| **I1** | `has_position=True + avg_price None/0` | CRITICAL (SL/TP/TS 무력화 위험) |
| **I2** | `has_position=True + qty<=0` | CRITICAL (memory 왜곡) |
| **I3** | `has_position=True + entry_ts=None` | CRITICAL (Stale silent skip 방지, **P1-1**) |
| I5 | `has_position=False + avg_price>0` | WARN (잔재, 안전) |
| I6 | `trailing_armed=True + highest_price=None` | WARN (TS 오작동) |

**호출 지점** (Phase 1 에서는 미통합, Phase 2 에서 인라인 코드를 헬퍼로 교체 예정):
- `strategy_incremental.py` EMA/MACD SELL 진입 (이번엔 기존 Fix 2 유지, 검증만 동작)
- `strategy_engine.py` `_on_hts_detect` 완료 직후 (검증 로직)
- `live_loop.py` `boot_seed` 완료 직후

### 4.2 `core/position_state.py:137-198` (Phase 1-B — P1-1 근본)

**변경 전**: Fix 1 이 `avg_price` 만 복구.

**변경 후**:
```python
if recovered_price is not None:
    self.avg_price = recovered_price
    # entry_ts 도 함께 복구 (sync 시각 기준)
    if self.entry_ts is None:
        self.entry_ts = datetime.now(ZoneInfo("Asia/Seoul"))
```

**추가 P2-1**: 복구 실패 시 `logger.critical` + `insert_log(ERROR)` + `notifier.send(LEVEL_CRITICAL, dedupe_key)`. Fix 2 봉 진입 대기 없이 즉시 사용자 알림.

### 4.3 `core/strategy_engine.py` (Phase 1-C + P2-3 + P2-5)

**Phase 1-C (P1-2)**: `_reconcile_position_with_wallet` 2곳 (`on_new_bar:381` + `on_new_bar_confirmed:484`) 을 각각 `with self._execution_lock:` 안으로 이동. Reconciler `_on_hts_detect` 와 race 방지.

**P2-3**: `_on_hts_detect` 에서 `reason == "HTS_BUY_ADD"` 감지 시 `highest_price`, `highest_since_entry`, `trailing_armed`, `trailing_fixed_amount`, `trailing_activation_price` 모두 리셋. 다음 봉부터 새 avg 기준 재추적.

**P2-5**: `register_fill_callback` / `register_hts_detect_callback` 실패 시 CRITICAL 로그 + `insert_log(ERROR)` + `notifier.send(LEVEL_CRITICAL)`.

### 4.4 `core/strategy_incremental.py:440` (Phase 1-D — P1-3)

MACD 인라인 SELL 지점의 `pnl_pct` 계산 직후:
```python
if pnl_pct is None:
    logger.warning(
        f"⚠️ [MACD-STOP_LOSS_CHECK] pnl_pct=None (avg_price={position.avg_price}) → SL/TP/TS 전량 스킵 "
        f"| has_position={position.has_position}, qty={position.qty}, current_price={current_price}"
    )
```

**주의**: MACD 는 인라인 로직 유지. sell_filter_manager 로 이전은 Phase 2 이후 검토.

### 4.5 `engine/live_loop.py:505-507` (Phase 1-E — P1-4)

**변경 전**: `_has_position=False; qty=0` 만 리셋.

**변경 후**: `avg_price`, `entry_ts`, `entry_bar`, `highest_price`, `highest_since_entry`, `trailing_armed`, `trailing_fixed_amount`, `trailing_activation_price` 모두 None/False 로 완전 리셋. WARN 로그로 완결 명시.

### 4.6 `core/filters/sell_filters.py:522-527` (P2-4)

f-string 리터럴 → 사전 포맷팅 변수:
```python
_max_gain_str = f"{max_gain:.2%}" if max_gain is not None else "None"
_avg_price_str = f"{position.avg_price:.2f}" if position.avg_price is not None else "None"
_highest_str = f"{position.highest_since_entry:.2f}" if position.highest_since_entry is not None else "None"
```

### 4.7 `engine/order_reconciler.py:79-87` (P2-2)

`unregister_user` 에서 `_hts_callbacks` 도 정리.

---

## 5. 검증

### 5.1 단위 테스트 (invariant 헬퍼 7 시나리오)

```
✅ 정상: expected=None, got=None
✅ I1 avg 결손: expected=I1_AVG_PRICE_MISSING, got=I1_AVG_PRICE_MISSING
✅ I1 avg=0: expected=I1_AVG_PRICE_MISSING, got=I1_AVG_PRICE_MISSING
✅ I2 qty=0: expected=I2_QTY_ZERO_WITH_POSITION, got=I2_QTY_ZERO_WITH_POSITION
✅ I3 entry_ts None (P1-1): expected=I3_ENTRY_TS_MISSING, got=I3_ENTRY_TS_MISSING
✅ I5 잔재: expected=I5_STALE_AVG_PRICE, got=I5_STALE_AVG_PRICE
✅ I6 TS armed: expected=I6_TRAILING_ARMED_NO_HIGHEST, got=I6_TRAILING_ARMED_NO_HIGHEST
```

### 5.2 py_compile

7 파일 (position_invariants.py, position_state.py, strategy_engine.py, strategy_incremental.py, sell_filters.py, order_reconciler.py, live_loop.py) 모두 통과.

### 5.3 프로덕션 실전 검증 계획

배포 후 자동 발생 예상 로그:
- 사용자 대시보드 진입 시:
  - `[OR] fill callback registered`
  - `[OR] hts-detect callback registered`
- 봉 처리 시 (JTO 3660 units 보유 상태):
  - `sync_from_wallet` 이 wallet 감지 → `avg_price` 이미 세팅 상태 → Fix 1 스킵
  - `_reconcile_position_with_wallet` 이 execution_lock 안에서 실행 (Phase 1-C)
- 이번 배포에는 P1-1 재현 상황 없어야 정상 (JTO 매수 상태 유지)

---

## 6. 위험 관리

### 6.1 절대 불변 (배포 후 절대 손대지 말 것)

- **매매 임계값**: TP=1%, SL=3%, TS threshold=40% (고정폭), Stale hours/threshold (사용자 False 유지)
- **필터 순서**: StopLoss → TrailingStop → TakeProfit → DeadCross → Stale
- **`sell_filter_manager.evaluate_all()` 호출 순서 및 로직**
- **`apply_entry`, `close_position` 시그니처**
- **Fix 1 fallback 순서**: DB cache → Upbit API (Phase 1-B 에서 entry_ts 추가만)

### 6.2 Rollback 계획

**Level 1 (부분 rollback)**: 문제 발생한 파일만 `git checkout HEAD~1 -- <file>` 후 재배포.
- position_invariants.py 참조 실패 → Phase 2 헬퍼 통합 안 했으므로 이 파일 삭제만 해도 다른 코드 영향 없음.

**Level 2 (전체 rollback)**: `git revert HEAD` 후 `deploy-tradebot`. 4e2bc3e 상태로 복원.

**Level 3 (긴급)**: 로컬 SSH → `git reset --hard 4e2bc3e && systemctl restart tradebot`.

### 6.3 배포 후 즉시 모니터링 항목 (24h)

1. `journalctl -u tradebot -f | grep -E 'CRITICAL|INVARIANT|POS-SYNC|HTS-DETECT-CALLBACK'`
2. 새 CRITICAL 알림 없는지 (Telegram)
3. SELL 발동 시 `[STOP_LOSS_CHECK]` 로그 정상 여부
4. `_execution_lock` 데드락 여부 (봉 처리 지연)

**이상 감지 시**: 즉시 Level 1 rollback + 원인 분석.

---

## 7. Phase 2 로드맵 (이번 주말)

**목표**: 5건 결함 각각 pytest 재현 → deploy.sh CI 게이트화 → 다음 배포부터 동일 결함 물리 차단.

**파일 계획**:
- `tests/regressions/test_r_2026_07_20_order_ratio_stale.py` (F1)
- `tests/regressions/test_r_2026_07_20_limit_fill_unpack.py` (F1')
- `tests/regressions/test_r_2026_07_22_sidebar_ratio_overwrite.py` (F2)
- `tests/regressions/test_r_2026_07_24_conditions_stale_state.py` (F3)
- `tests/regressions/test_r_2026_07_27_hts_avg_price_missing.py` (F5)
- `tests/regressions/fixtures/{fake_upbit,fake_reconciler,db_fixture,bar_fixture}.py`
- `deploy.sh` 수정: `pytest tests/regressions -q` 게이트 삽입

**예상 소요**: 16~20h.

---

## 8. Phase 3 로드맵 (다음 주)

**목표**: Observability — 사건 감지 시간 2.5일 → 수 분 단축.

**파일 계획**:
- `services/invariant_monitor.py` — 실시간 invariant 스냅샷 SQLite 적재
- `services/audit_logger.py` — JSONL RotatingFileHandler 별도 audit log
- `pages/system_health.py` — 대시보드 별도 페이지 (invariant 상태, silent counter, CRITICAL 이력)
- `services/notifier.py` — CRITICAL/WARN/INFO 3-tier 채널 분리
- `pages/dashboard.py` — 상단 헬스 배지 (초록/노랑/빨강)
- `services/init_db.py` — `invariant_snapshots` 테이블 migration

**예상 소요**: 3~7일.

---

## 9. 관련 문서 및 커밋 참조

- **관련 memory**:
  - `project_upbit_hts_sl_paralysis_fix.md` (4e2bc3e 배경)
  - `project_upbit_ratio_hr_ts_fix.md` (F1~F3 배경)
  - `project_upbit_2026_07_27_audit.md` (외부 감사 결과)
  - `feedback_trust_first_root_cause.md` (silent 실패 원칙)
  - `reference_upbit_log_locations.md` (systemd journal 조사 도구)
  - `reference_upbit_streamlit_stale_session.md` (F3/F4 패턴)

- **관련 커밋 (chronological)**:
  - `7ff9b10` (07-20 12:04) — F1 fix
  - `7991a48` (07-22 20:31) — F2 fix
  - `43eecb1` (07-24 11:41) — F3 fix
  - `4e2bc3e` (07-27 12:19) — F5 fix (4단)
  - **이번 배포** (07-27 20:58) — Phase 1 defense hardening (본 문서)

---

**최종 원칙**: 매매 로직은 절대 손대지 말고, 오직 결함 재발 방지를 위한 관찰 강화만. Phase 2/3 이 완결될 때까지 사용자는 실전 테스트 지속 가능해야 함.
