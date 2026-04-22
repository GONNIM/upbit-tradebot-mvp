### 🔴 Issue #10: Enum 속성 접근 오류 (action.action → AttributeError)

**발생일**: 2026-03-24
**심각도**: 🔴 Critical (엔진 중단 100% 재현)

#### 문제

봇이 bar=201 평가 후 반복적으로 중단됨:

```
2026-03-24 09:09:36 | bar=201 평가 완료
❌ 예외: AttributeError: 'Action' object has no attribute 'action'
🛑 엔진 종료
```

**발생 이력**:
- 2026-03-21 19:09:15 (bar=201)
- 2026-03-21 19:36:44 (bar=201)
- 2026-03-21 19:38:54 (bar=201)
- 2026-03-22 16:30:36 (bar=201)
- 2026-03-24 09:09:36 (bar=201) ← 가장 최근

#### 근본 원인

**`strategy_engine.py:274, 415` Enum 속성 오접근**:

```python
# ❌ 잘못된 코드
logger.debug(
    f"action={action.action if action else 'NONE'}"
)
```

**왜 문제인가?**

- `Action`은 Python Enum 클래스:
  ```python
  class Action(Enum):
      BUY = "BUY"
      SELL = "SELL"
      HOLD = "HOLD"
  ```
- Enum 객체의 속성:
  - `.value`: Enum 값 (`"BUY"`, `"SELL"` 등)
  - `.name`: Enum 이름 (`"BUY"`, `"SELL"` 등)
  - ❌ `.action`: **존재하지 않음** → AttributeError

- `action.action` 접근 시도:
  - `Action.BUY.action` → ❌ AttributeError
  - 디버그 로그 실행 시점에 예외 발생
  - 엔진 전체 중단

#### 왜 놓쳤나?

1. **Python Enum 표준 속성 이해 부족**
   - `.value`, `.name` 대신 `.action` 사용
   - 존재하지 않는 속성 접근

2. **테스트 부족**
   - 해당 디버그 로그가 실행되는 경로 미테스트
   - bar=201 도달 시에만 발생하는 경로
   - 초기 bar < 201일 때는 실행 안 됨

3. **복사-붙여넣기 오류**
   - 2곳에서 동일 패턴 반복 (274, 415번 라인)
   - Mass Replace 없이 개별 작성 시 발생

#### 교훈

1. **Python 기본 타입 속성 명확히 이해**
   ```python
   # ✅ 올바른 Enum 사용
   action = Action.BUY
   action.value  # "BUY" ✅
   action.name   # "BUY" ✅
   str(action)   # "BUY" ✅ (__str__ 메서드 활용)

   # ❌ 잘못된 접근
   action.action  # AttributeError ❌
   ```

2. **디버그 코드도 테스트 필수**
   - 디버그 로그라도 런타임 에러 발생 가능
   - 모든 코드 경로 테스트 필요

3. **Early Warning 시스템 부족**
   - bar=201 이전에는 발견 안 됨
   - 초기화 단계에서 기본 검증 필요

#### 수정

**Before (잘못됨)**:
```python
# core/strategy_engine.py:274, 415
logger.debug(
    f"[ENGINE] 평가/실행 완료 | bar={self.bar_count} | "
    f"final_has_position={self.position.has_position} | "
    f"action={action.action if action else 'NONE'}"  # ❌
)
```

**After (올바름)**:
```python
# core/strategy_engine.py:274, 415
logger.debug(
    f"[ENGINE] 평가/실행 완료 | bar={self.bar_count} | "
    f"final_has_position={self.position.has_position} | "
    f"action={action.value if action else 'NONE'}"  # ✅
)
```

#### 영향 범위

- **파일**: `core/strategy_engine.py`
- **라인**: 274, 415 (2곳)
- **수정 방법**: `action.action` → `action.value`

#### 검증 방법

```bash
# 1. 구문 검증
python3 -m py_compile core/strategy_engine.py

# 2. 동일 패턴 검색
grep -rn "action\.action" --include="*.py"
# 결과: 패턴 없음 (수정 완료)

# 3. 봇 재시작 후 bar=201 이후 정상 동작 확인
tail -f mcmax33_engine_debug.log | grep "평가/실행 완료"
```

**파일**: `core/strategy_engine.py`
**문서**: `CLAUDE.md` (Issue #10)

---

