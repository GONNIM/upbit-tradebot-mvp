# Issue #18 — Streamlit UI 미디어 파일 핸들러 Traceback (엔진 무관)

**등록일**: 2026-09-12
**우선순위**: **낮음** (매매 로직·엔진 상태·감사 로그에 영향 없음)
**상태**: 관측 중, 조치 대기 (별도 사용자 지시 시 대응)

---

## 1. 현상

Streamlit 대시보드 세션이 오래 열려 있거나 재로드되는 과정에서 프론트엔드 media file handler가 미디어 파일 id를 찾지 못해 Traceback을 출력한다. 로그는 stderr가 streamlit 로거를 통해 `journalctl -u tradebot`에 함께 남아 매매 로직 Traceback과 섞여 보인다.

**최근 7일 실측(2026-09-05~09-12, KRW-JTO)**: Traceback 총 75건. **전부 아래 3종 스택 조합.**

---

## 2. 대표 스택 3종 (원문 인용)

### 스택 A — asyncio 이벤트 루프 확인
```
Traceback (most recent call last):
  File "/root/upbit-tradebot-mvp/venv/lib/python3.12/site-packages/streamlit/web/bootstrap.py", line 348, in run
    if asyncio.get_running_loop().is_running():
       ^^^^^^^^^^^^^^^^^^^^^^^^^^
```
- 세션 재시작 시 이벤트 루프 참조 실패로 판단됨.

### 스택 B — 메모리 미디어 파일 저장소 KeyError
```
Traceback (most recent call last):
  File "/root/upbit-tradebot-mvp/venv/lib/python3.12/site-packages/streamlit/runtime/memory_media_file_storage.py", line 140, in get_file
    return self._files_by_id[file_id]
           ~~~~~~~~~~~~~~~~~^^^^^^^^^
```
- 이미 만료된 file_id 조회로 KeyError 발생 후 상위 핸들러에서 캡처.

### 스택 C — 미디어 파일 검증 실패 위임
```
Traceback (most recent call last):
  File "/root/upbit-tradebot-mvp/venv/lib/python3.12/site-packages/streamlit/web/server/media_file_handler.py", line 95, in validate_absolute_path
    self._storage.get_file(absolute_path)
  File "/root/upbit-tradebot-mvp/venv/lib/python3.12/site-packages/streamlit/runtime/memory_media_file_storage.py", line 142, in get_file
```
- 상위 tornado 핸들러(validate_absolute_path)가 하위(get_file)의 예외를 그대로 위임.

---

## 3. 엔진 무관 근거

1. **경로**: 세 스택 모두 `streamlit/` 패키지 내부. `core/`·`engine/`·`services/` 코드 진입 없음.
2. **트리거**: 대시보드 세션 재로드·미디어 파일 만료 시점에 발생. 봉 처리·매매 판단·API 발주 사이클과 무관.
3. **영향 없음 실측** (동일 7일):
   - 봉당 매매 판단 위반 = 0건
   - POLLUTED = 0건
   - 매매 사고 = 0건
   - `[SKIP-BAR]` = 0건
   - 실시간 audit 커버리지 = 100% (`docs/plans/2026-09-12-post-check/` 참조)
4. **Streamlit 서비스 재시작 없이도 대시보드 재접속으로 해소** — 엔진 loop는 별개 스레드에서 무중단 실행.

---

## 4. 조치 우선순위 (낮음)

- **현 상태**: 매매·감사 무영향. 즉시 조치 불요.
- **대안**:
  1. `streamlit` 버전 업그레이드 시 회귀 여부 확인 (media_file_storage 개선 이력).
  2. `nginx` 리버스 프록시에 미디어 캐시 TTL 별도 설정으로 file_id 만료 전 조회 유도.
  3. `journalctl` grep 시 UI Traceback을 분리 표기하는 필터 스크립트 (`scripts/journal_engine_only.sh` 등) 신설 — 관측 편의성만 개선.
- **비목표**: 봇 프로세스 (`tradebot.service`) 재시작·재배포로 UI Traceback 잡으려 하지 않는다. 매매 로직에 무영향인 로그를 방지하려고 봇을 흔들 이유가 없다.

---

## 5. 관련 문서

- `docs/plans/2026-09-12-fv1-fv3-and-v-a-v-b-investigation/report.md` — FV 조사 시점 UI Traceback 관측
- 사용자 판정 규칙(2026-09-12): "매매 사고 없음 → revert 하지 않음, 별도 이슈로 관리"
