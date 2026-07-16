# PAUSE-1 · 매매 중지 버튼 및 기능

**작성일**: 2026-07-10
**상태**: 계획서 승인, 구현은 RATIO-1 완료 후 착수
**우선순위**: 2

---

## 배경

- 현재 `engine_manager.stop_engine()`은 엔진 스레드를 완전히 종료 → 지표·WebSocket·버퍼 유실 → 재시작 시 WARMUP(200봉) 재실행 필요.
- 사용자 요청: "봇 데이터는 유지하고 매매만 중지"할 수 있는 별도 스위치.
- 확정 사항: **BUY + SELL 모두 중지, DB에 상태 저장**.

## 목표

- 엔진은 계속 실행 (WebSocket 유지, 지표 갱신, 감사 로그 기록).
- `_execute_buy()` / `_execute_sell()` 진입만 스킵.
- 재개 시 다음 봉 신호부터 즉시 매매 정상화.
- 엔진 재기동 후에도 pause 상태 유지 (영속화).

## In-scope

### A. DB 스키마
- `services/init_db.py` — `users` 테이블에 `trading_paused INTEGER DEFAULT 0` 컬럼 추가.
- 마이그레이션: `PRAGMA table_info(users)`로 컬럼 존재 확인 후 없을 때만 `ALTER TABLE`.

### B. DB 액세스 함수
- `services/db.py`
  - `get_trading_paused(user_id: str) -> bool`
  - `set_trading_paused(user_id: str, paused: bool) -> None`

### C. 게이팅 로직
- `core/strategy_engine.py:557 execute()` 최상단:
  ```python
  if self._is_trading_paused():
      logger.info(f"⏸️  [PAUSE] {action.value} 스킵")
      return
  ```
- `_is_trading_paused()`는 매 봉마다 DB 재조회 (5분봉 기준 부담 없음).
- BUY / SELL / CLOSE 모두 스킵.

### D. UI
- `pages/dashboard.py`
  - 엔진 시작/중지 버튼 옆에 "⏸️ 매매 중지 / ▶️ 매매 재개" 토글 버튼.
  - 상단 배너: pause 상태 시 `st.warning("⏸️ 매매 중지 중 (감사로그·지표는 정상 작동)")`.
  - 버튼 클릭 → `set_trading_paused()` → `st.rerun()`.

## Out-of-scope

- LIMIT 미체결 주문 자동 취소 (이미 접수된 주문은 pause 무관하게 체결 진행).
- 감사 로그에 `checks.paused_by_user` 필드 삽입.
- Telegram / 이메일 알림.
- admin이 다른 사용자를 대신 pause 시키는 기능.
- BUY/SELL 각각 별도 토글.

## 변경 파일 (4개)

| 파일 | 변경 규모 |
|---|---|
| `services/init_db.py` | 스키마 컬럼 + 마이그레이션 (~10줄) |
| `services/db.py` | 함수 2개 신설 (~20줄) |
| `core/strategy_engine.py` | 게이트 4~5줄 |
| `pages/dashboard.py` | 토글 버튼 + 배너 (~30줄) |

## 리스크

- **마이그레이션**: 재실행 안전성 (`ALTER TABLE ... ADD COLUMN`은 컬럼 존재 시 에러) → `PRAGMA table_info` 조건부 실행.
- **진행 중 주문**: 게이트가 `execute()` 진입 시점에서만 작동. 이미 API에 접수된 주문은 그대로 진행.
- **캐시**: 매 봉마다 DB 조회이므로 성능 부담 낮음. 필요 시 in-memory 캐시(1분 TTL) 추가 가능하나 이번 out-of-scope.

## 테스트 체크리스트

- [ ] 마이그레이션: 컬럼 없는 기존 DB → 컬럼 추가 성공. 재실행 → 에러 없이 스킵.
- [ ] LIVE 모드 Golden Cross 발생 → pause ON → `audit_trades`에 BUY **없음**, `audit_buy_eval`에 `overall_ok=1` 남음.
- [ ] Dead Cross 발생 → pause ON → `audit_trades`에 SELL **없음**, 포지션 유지.
- [ ] pause OFF → 다음 봉 신호부터 정상 매매.
- [ ] 엔진 재기동 후에도 pause 상태 유지.
- [ ] `py_compile` 4개 파일 통과.

## 배포

- 로컬 구현 → py_compile → `pages/dashboard.py` 버전 갱신 → 커밋 → 사용자 승인 후 서버 배포.

## 롤백

- Git revert 1건.
- 이미 적용된 스키마 컬럼은 남지만 사용하지 않으므로 무해.
