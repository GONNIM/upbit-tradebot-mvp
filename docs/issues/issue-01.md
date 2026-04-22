### 🔴 Issue #1: pyupbit 컬럼명 대소문자 불일치

**발생일**: 2026-03-03 20:08
**심각도**: 🔴 Critical (100% 실패)

#### 문제

```python
df = pyupbit.get_ohlcv(...)
df = df[['Open', 'High', 'Low', 'Close', 'Volume']]  # ❌ KeyError!
```

**에러 메시지**:
```
KeyError: "None of [Index(['Open', 'High', 'Low', 'Close', 'Volume'], dtype='object')] are in the [columns]"
```

#### 근본 원인

- **가정**: pyupbit가 대문자 컬럼명을 반환할 것으로 가정
- **실제**: pyupbit는 **소문자 컬럼명** 반환 (`open`, `high`, `low`, `close`, `volume`, `value`)
- **왜 놓쳤나**: API 문서를 확인하지 않고 관례적으로 대문자를 가정함

#### 교훈

1. **외부 라이브러리의 반환값은 반드시 문서 또는 실제 테스트로 확인**
   ```python
   # ✅ 올바른 접근
   import pyupbit
   df = pyupbit.get_ohlcv('KRW-BTC', interval='minute1', count=1)
   print(df.columns.tolist())  # 실제 컬럼명 확인
   ```

2. **가정하지 말고, 검증하라** (REST Reconcile의 핵심 원칙과 동일)

#### 수정

```python
# ✅ 컬럼명 표준화 추가
df.columns = [col.capitalize() for col in df.columns]
df = df[['Open', 'High', 'Low', 'Close', 'Volume']]
```

**파일**: `core/rest_reconcile.py:98`
**문서**: `thoughts/20260303-REST-Reconcile-Hotfix-Column-Names.md`

---

