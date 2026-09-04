# 설정 변경 알림 (후속 작업 · 구현은 종결 후)

**작성일**: 2026-09-04
**상태**: 계획서, 구현 대기 (WO-2 옵션 C 배포 종결 후 착수)

---

## 배경 · 근거

`settings_history` 테이블에 신규 행이 저장되어도 운영자에게 별도 통지가
가지 않는 구조다. 최근 두 차례 무통지 변경 사례가 있었다.

- **2026-08-21**: 매매 방식이 지정가에서 시장가로 변경됨. 통지 없음.
- **2026-09-02 19:03**: 조건 파일 변경 반영(`[PARAMS-RELOAD]`) 뒤 19:04:25
  에 `[EMA Strategy] Interval set to 5 minutes` 로 봉 간격이 minute1 → minute5
  로 재초기화됨. 통지 없음. 이 변경으로 24시간 실측 산식이 두 세그먼트로
  갈라졌다.

이 두 사례가 반복되면 감사·실측 자체가 오해 소지를 남긴다. 설정 변경 시점을
운영자에게 즉시 알리고, 재시작이 필요한 변경인지 명시하는 알림을 발송한다.

## 목적

- `settings_history` 에 신규 행이 저장되는 순간 notifier 로 1줄 요약 전송.
- 재시작이 필요한 필드 목록을 코드 주석과 상수로 정의해 이후 판단 근거로
  활용.

## 대상 파일 (구현 시)

- `services/db.py` 또는 `services/settings_history.py`: 신규 행 저장 훅 지점.
  기존 `settings_history` 기록 함수 (예: `record_settings_snapshot`)에 발송
  경로 추가. 발송 실패 시 봉 처리 흐름 무영향.
- `services/notifier.py`: 기존 `send` 함수 재사용. `LEVEL_WARNING` 등급.
- 신설 상수 파일: `core/settings_change_policy.py` — 재시작 필요 필드 목록과
  판정 함수. 예:

```python
# core/settings_change_policy.py (신설 예시)
"""설정 변경 시 재시작 필요 여부 판정.

재시작 필요 필드는 CandleClock, IndicatorState, 지표 warmup 등
프로세스 상태 재초기화가 있어야 안전한 파라미터다. 새 필드를 추가할 때는
반드시 이 목록을 갱신한다.
"""
RESTART_REQUIRED_FIELDS: frozenset[str] = frozenset({
    "interval",          # 봉 간격 변경 → CandleClock, IndicatorState 재초기화 필요
    "fast_period",       # EMA 기간 변경 → warmup 재시드 필요
    "slow_period",
    "fast_buy", "slow_buy", "fast_sell", "slow_sell",
    "base_ema_period",
    "use_separate_ema",
    "strategy_type",     # 전략 자체 교체
    "ma_type",           # EMA/SMA 교체
})

def restart_required(old: dict, new: dict) -> list[str]:
    """두 스냅샷 비교하여 재시작 필요 필드 목록 반환."""
    return [f for f in RESTART_REQUIRED_FIELDS if old.get(f) != new.get(f)]
```

## 흐름 (구현 시)

1. `settings_history` 에 신규 행 INSERT 직후 훅에서 직전 행과 비교.
2. 변경된 필드 목록을 산출.
3. `restart_required` 로 재시작 필요 여부 판정.
4. `notifier.send(LEVEL_WARNING, 제목, 본문)` 발송. 본문에 다음 포함:
   - 변경 시각, 변경자(user_id), 소스 페이지.
   - 변경된 필드 목록과 (before → after) 표시.
   - "재시작 필요: YES/NO" 라벨과 필요한 경우 재시작 명령 안내.
5. 발송 실패는 무해 처리. 봉 처리 흐름과 완전 분리.

## 회귀 테스트 (구현 시)

- `test_r_YYYY_MM_DD_settings_change_restart_required.py`: interval 필드
  변경 시 `restart_required` 가 `['interval']` 반환하는지.
- `test_r_YYYY_MM_DD_settings_change_notifier_call.py`: 신규 행 저장 시
  notifier `send` 가 호출되는지 (mock).
- `test_r_YYYY_MM_DD_settings_change_no_restart_field.py`: `take_profit`
  같은 비재시작 필드만 변경 시 재시작 필요 목록이 빈 리스트인지.

## 배포 조건

- WO-2 옵션 C 배포 종결 후.
- 별도 배포 승인 요청.

## 참고

- 이번 24시간 실측 결함(minute1 → minute5 무통지 전환)이 이 알림이 있었다면
  즉시 인지 가능했을 사례다.
