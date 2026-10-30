"""
회귀 시험이 `git show <커밋>:<파일>` 로 읽는 기준 커밋을 한 곳에 모은다 (2차 T10, T9 넘김 · Fable 권고).

1) EMA_BASELINE_COMMIT — 「EMA·MACD 경로 무변경」 대조 기준.
   쓰는 시험: T6 `test_apply_entry_unchanged`·HTS 매수 손절 시험(core/position_state.py·core/strategy_incremental.py),
   T8 원본 비교 5건(core/trader.py·engine/order_reconciler.py·pages/audit_viewer.py 원본을 불러 같은 호출·같은 화면),
   T9 `test_ema_ignores_trading_hours`(엔진·전략·params 의 PULLBACK 밖 함수 AST).
   뜻: 「기준 커밋 이후 EMA·MACD 가 타는 공용 코드가 바뀌지 않았다」. 각 Task 가 처음 고정한 커밋은
   T6=0b04570, T8=2749080, T9=ebe4605 다. 그 사이 T7(2749080)은 EMA 거래·주문 행에 strategy_type='EMA' 를
   더했다(의도된 변경 — T7 시험·사용자 승인). 그 밖의 커밋은 PULLBACK 분기만 고쳤다.
   10/28(T10 수정 1회차) 확인: 세 시험 파일을 각자 원래 기준(0b04570·2749080·ebe4605)으로 돌려도 지금 트리에서
   통과한다(T6 47·T8 47·T9 16건, 실패 0).

   ── 기준을 올리는 규칙 ──
   공용 함수를 정당하게 고쳐 위 시험이 실패하면(EMA·MACD 동작을 일부러 바꾸는 작업):
     (1) 바뀐 내용을 사용자 승인 대상 보고에 「EMA 경로 변경」으로 적고, EMA·MACD 회귀 시험 전부를 통과시킨다.
     (2) 그 변경 커밋이 들어간 뒤 이 상수를 그 커밋 해시로 올린다(올리는 커밋은 따로 두거나 같은 커밋).
     (3) 올리는 커밋 메시지에 「EMA 기준 커밋 <옛> → <새>: <사유>」를 적는다.
   사유 없이 시험을 통과시키려고 기준만 올리지 않는다. 올린 이력은 git log 로 본다
   (`git log -p -- tests/regressions/baseline_commits.py`).
   기준 커밋은 origin 에 push 된 커밋이어야 한다(서버 게이트도 같은 이력을 읽는다).

2) REVERT_OLD_CODE_COMMIT — 「되돌리기 무해성」 시험(T10, 계획 8절)의 옛 코드.
   = 지금 서버에서 돌고 있는 커밋(2차 배포 전). 근거: 12ec5a4 「1차 화면 배포 완료 보고 — 서버 실행본 1747fcc」.
   services/ 는 1747fcc 와 2차 스키마 변경 직전 커밋 0b04570(T5) 사이에 바뀐 줄이 없다
   (`git diff --stat 1747fcc 0b04570 -- services/` 빈 출력). 2차 스키마 변경은 T6 51c62f5(pullback_state)·
   T7 2749080(strategy_type 칸·schema_marks)부터다.
   2차를 배포한 뒤에는 되돌리기 대상이 바뀌므로, 다음 배포 때 그 배포 직전 서버 실행본으로 바꾼다
   (커밋 메시지에 사유).
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent.parent

EMA_BASELINE_COMMIT = "f4aac1f"     # 2차 T9 커밋 (push 됨) — 2026-10-28 T10 에서 0b04570·2749080·ebe4605 를 하나로
# 3) FIXED_FILES_COMMIT — 「실계좌 EMA 경로 바이트 고정 8개」(T12 커밋 메시지) 대조 기준 = 2차 T12 커밋(push 됨).
#    쓰는 시험: T13 test_fixed_files_unchanged_since_t12. 올리는 규칙은 1) 과 같다(8개 중 하나를 일부러 바꾸는 작업만).
FIXED_FILES_COMMIT = "6b6f0b5"
# 4) OLD_UI_BASE_COMMIT — 「구버전 화면(EMA 사용자) 무변경」 대조 기준 = 2차 T14 커밋(push 됨, T15 직전).
#    쓰는 시험: T15 test_r_2026_10_29_p4_t15_old_ui (dashboard·set_config·조건 화면 AppTest 비교, 고정 파일 9개).
#    올리는 규칙은 1) 과 같다(구버전 EMA 화면을 일부러 바꾸는 작업만).
OLD_UI_BASE_COMMIT = "8464b58"
# 5) V2_READ_BASE_COMMIT — 「신버전 읽기 API(EMA 사용자) 무변경」 대조 기준 = 2차 T15 커밋(push 됨, T16 직전).
#    쓰는 시험: T16 tests/v2/test_api_read_pullback.TestEmaUnchangedVsBase(새 표 없는 DB 에서 홈·로그·자산·차트 응답이 같음).
#    올리는 규칙은 1) 과 같다(EMA 사용자 신버전 응답을 일부러 바꾸는 작업만 — T16 의 U2 표식 정정은 이 시험에서 따로 다룬다).
V2_READ_BASE_COMMIT = "4e86afb"
# 6) PULLBACK_RULES_BASE_COMMIT — 「새 전략 판정 파일 core/strategy_pullback.py 고정」 대조 기준 = 2차 T14 커밋(push 됨).
#    1029-09(결정 1029-08 「시간 밖에도 익절」 꺼짐 = 익절만 막고 손절·데드크로스는 늘 매도)로 이 파일을 일부러 바꿨다.
#    그래서 바이트 비교(T14 FIXED_FILES_COMMIT·T15 OLD_UI_BASE_COMMIT 목록)에서 빼고 AST 비교로 옮겼다:
#    모듈 전체 AST(docstring 제외, IncrementalPullbackStrategy._step 몸통만 가림) = 기준,
#    _step 은 시간 밖 막음 If 문·[PULLBACK-HOURS] 로그 If 문 둘을 뺀 문장 목록 = 기준, git diff hunk 는 정해진 줄 범위 안.
#    쓰는 시험: test_r_2026_10_30_1029_09_off_hours_tp.TestPullbackRulesFixed. 올리는 규칙은 1) 과 같다.
#    막음 블록을 다시 고칠 때는 이 기준 커밋·ALLOWED_OLD_RANGES·NEW_LINES_CAP·EXPECTED_*_IF 네 곳을 함께 올린다
#    (새 줄 수 상한은 여유가 없어 주석 한 줄만 바꿔도 시험이 깨진다).
PULLBACK_RULES_BASE_COMMIT = "8464b58"
REVERT_OLD_CODE_COMMIT = "1747fcc"  # 서버 실행본(2차 배포 전) — 되돌리기 무해성 시험의 옛 코드


def git_show(rel: str, commit: str = EMA_BASELINE_COMMIT) -> Optional[str]:
    """<commit>:<rel> 원문. 읽지 못하면 None(빈 원문도 None)."""
    try:
        out = subprocess.run(["git", "-C", str(ROOT), "show", f"{commit}:{rel}"],
                             capture_output=True, check=True, text=True).stdout
    except Exception:
        return None
    return out if out.strip() else None
