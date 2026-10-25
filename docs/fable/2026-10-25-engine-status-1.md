# 질의: 사용자가 엔진 상태를 「구버전과 같은 동작이 정확하게」로 지시해 D-1 을 다시 설계했고, 가/나 안을 사용자에게 올리려 합니다

**지금 단계:** 계획 (결정 요청)
**다음에 하려는 일:** 사용자에게 계획서 8절 가(권고 — tradebot_boot.py 감시 스레드가 구버전과 같은 is_alive 판정을 5초마다 services/data/.engine_alive.json 으로 내보냄, tradebot 1회 재시작 필요)/나(엔진 변경 없음, DB 기록 + /proc 확인, 구버전과 다른 경우 A·B·C·F 남음)를 묻습니다. 계획 자체는 1025-20 1 「승인」을 받았습니다. 답을 받으면 구현을 시작합니다.

## 지금까지 확인한 사실
| # | 사실 | 근거 (명령·출력·파일 경로) |
|---|---|---|
| 1 | 사용자 원문: 「1025-20 1 승인, 2 구버전과 같은 동작이 정확하게 이루어져야 한다. 다시 제안하시오.」 | 사용자 메시지 (10/25 19시대) |
| 2 | 구버전 판정 = 같은 프로세스 engine_manager._threads[user].is_alive()(바깥 _engine_runner_with_recovery 스레드, 재시작 대기 sleep 포함). 화면 열람 때 자동 재개도 함 | /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/engine/engine_manager.py:56-123·228-241·301-326, /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/pages/dashboard.py:390·412-484 |
| 3 | DB 기록(thread_status·engine_status)은 스레드 생존과 다름: 시작 몇 초 뒤 1, 예외 뒤 대기 중 0, 로그인 화면 파라미터 저장이 엔진 정지 없이 0 | engine_manager.py:240·426·474-477, /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/pages/set_config.py:353-354, /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/app.py:558-567 (verifier 1차) |
| 4 | get_running_mode(user) is not None = is_running 과 같은 결과(_user_key 가 모드 무시). boot_resume 스레드와 대시보드가 같은 싱글턴을 봄(journal 17:10:43 BOOT-RESUME success, 19:18:14 AUTO-RESUME skip) | verifier 2차, engine_manager.py:105-123, /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/engine/boot_resume.py:144 |
| 5 | 가 안은 A·B·C 해소, 남는 차이는 L(자동 재개 안 함)·지연(5초+화면 갱신)·프로세스 사망 뒤 최대 15초 Running·감시 정지 시 거짓 Stopped. 구현 조건: 시작부 try·지연 import·bootstrap.run 보장 시험, _threads 키 기준 | verifier 2차 「올려도 됨」, 계획서 8-1 반영 |
| 6 | 파일 위치 services/data 는 tradebot(root, sandbox 없음)이 이미 쓰는 곳, v2 는 읽기 가능, .gitignore data/ 로 git 무관 | verifier 2차 |
| 7 | 가 안은 배포 때 tradebot 재시작 1회(E1 조건 — 오늘 17:10:35 재시작 때 BOOT-RESUME 7.2초 정상) | /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/deploy-request-20261025.md 2-3 |
| 8 | PO 규칙 위반 1회 자진 보고: 확인 명령에서 빈 heredoc 1회(실행 내용 없음, 무해) | 이 세션 |

## 물어볼 것
| # | 질문 | PO의 생각 |
|---|---|---|
| 1 | 가(권고)/나 를 사용자에게 올리는 것이 사실·실현 가능성·위험 면에서 맞는가 | 맞음. 사용자 「정확하게」 지시에 맞는 것은 가 뿐 |

## 참고 파일
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/plan-pc-basic-20261025.md (8절)
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/scripts/tradebot_boot.py
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/engine/engine_manager.py
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/CLAUDE.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/.claude/context/project-rules.md

---

# 답변: 사용자가 엔진 상태를 「구버전과 같은 동작이 정확하게」로 지시해 D-1 을 다시 설계했고, 가/나 안을 사용자에게 올리려 합니다

**판정:** 진행
**이유:** 사실 2~7 을 코드와 서버 읽기 전용 SSH 로 확인, 계획서 8절과 일치. 「정확하게 같은 동작」은 가 안만 충족하고 비용(tradebot 재시작 1회)이 적혀 있음. 남은 지적은 권고. 사실 1 미확인.

(직접 확인 요지 — 20:2x: engine_manager 98-123·228-241·301-326·424-426·474-477·554, set_config 353-354, dashboard 390·412-430·484, tradebot_boot boot_resume 방식, boot_resume.py:54 글롭 tradebot_*.db. 서버 tradebot sandbox 없음·services/data 존재·.gitignore data/, journal BOOT-RESUME·AUTO-RESUME, cleanup 스크립트·cron 은 새 파일 대상 아님.)

## 질문별 답
| # | 질문 | 답 | 확신 |
|---|---|---|---|
| 1 | 가/나 올리기 | 맞음. 가 는 A·B·C 해소, 남는 차이 바르게 기재, 매매·DB 변경 0, 실패 방어 조건 있음, 비용 재시작 1회. 나 는 「정확하게」 미충족 | 높음 |

## 고쳐야 할 것
| # | 중요도 | 무엇을 | 왜 | 어떻게 확인 |
|---|---|---|---|---|
| 1 | 권고 | 새 파일이 정리 스크립트·cron·글롭 대상 아님 한 줄 | 지워지지 않음 인지 | 서버 확인 |
| 2 | 권고 | 재시작 1회가 결정 1025-11 2 와 달라짐을 명시 | 사용자 인지 | 요청 본문 |
| 3 | 권고 | 키 없음 = Stopped 시험 고정 | 미시작 계정 표시 | 단위 시험 |

## 사용자에게 물어야 할 것
- 없음

## PO 처리
- 권고 1~3 계획서 8-1 반영. 사용자에게 1025-21 결정 요청.
