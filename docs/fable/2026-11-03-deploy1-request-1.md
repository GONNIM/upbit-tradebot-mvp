# 질의: 배포 ① 커밋 C·push 와 배포 승인 요청을 진행해도 됩니까 (배포 승인 요청 직전)

**지금 단계:** 1102-02 구현·1101-08 조사 끝, 배포 ① 요청서·서버 스크립트 작성, verifier 「배포 승인 요청 가능」
**다음에 하려는 일:**
1. 커밋 C: `pages/dashboard.py` 버전 1441 → 지금 시각, `core/trailing_restore.py`, `tests/regressions/test_r_2026_11_03_stale_peak_restore.py`, 요청서, HANDOFF, Fable 질의 2개(closeout-plan-1, 이 파일) — 파일 하나씩 add, 게이트 통과 뒤 push(pre-push 게이트). 공개 저장소.
2. run.sh 의 `__NEW_FULL_HASH__`·`__NEW_VER__` 를 C 값으로 채움, 3행 승인 문구는 승인 뒤 채움.
3. 사용자에게 배포 ① 승인 요청(요청서 6절). 승인 뒤: 사용자 `!` 로 서버 업로드(scp, 파일 600·폴더 700) → 드라이런 → 본 띄우기. Claude SSH 는 자동 모드가 막음.
4. C push 뒤 배포 끝까지 origin/main push 없음.

## 지금까지 확인한 사실
| # | 사실 | 확인/추정 | 근거 |
|---|---|---|---|
| 1 | 사용자 결정 1103-01 「권고대로」: 배포 ① = 1102-01+1102-02+1101-08, 1029-12 는 배포 ②, 통보는 마지막 한 번 | 확인 | 이 세션, HANDOFF 1103-01 행 |
| 2 | 1102-02 는 core/trailing_restore.py 한 파일, `restore_stale_peak_on_boot` 를 restore_trailing_on_boot 맨 앞에서 try 로 부름. 정체 최고가 = max(평단, 진입 뒤 확정 봉 종가), 워밍업 봉만 | 확인 | `git diff -- core/trailing_restore.py`, verifier A3~A9 |
| 3 | 정체 매도는 같거나 덜 남(늘지 않음). 손절·익절·트레일링·데드크로스 무관 | 확인 | verifier A4·A5 |
| 4 | 게이트 1205/1205·NETGUARD 0 (작업 트리) | 확인 | verifier 실행 로그 scratchpad/verify_gate_1103.log |
| 5 | 148줄 원인: 워밍업 자리표시자 갱신이 실시간 UPDATE 경로를 타 문구만 찍힘, 감사·매매 영향 없음 | 확인 | 서버 읽기 bbvs0rk6q.txt:37·89·158, services/db.py:1141-1143·1201-1208·1251-1252, verifier D1~D3 |
| 6 | REVERT_OLD_CODE_COMMIT 은 올리지 않음(2차 스키마 되돌리기 전용 시험) | 확인(PO 실행 2건 실패, verifier 는 재현 안 함) | 이 세션 |
| 7 | 서버 audit_trades 모두 ISO 형식 | 확인 | bbvs0rk6q.txt |
| 8 | run.sh 는 1101-13 에서 실행·통과한 스크립트에 값·문구·표식 로그·관찰 통과 뒤 백업 권한 블록만 더함 | 확인 | verifier C1~C6 diff |
| 9 | 정지선 기대값(tb 기동 11/03 01:42:07, v2 11/01 14:21:31, 미추적 5)은 HANDOFF·13:33 result.log 읽기 근거 — 드라이런으로 실측 | 추정(드라이런 전) | verifier 지적 1. 어긋나면 쓰기 없이 끝남 |
| 10 | 서버 정체 매도 꺼짐(11/01 19:55) — 켜져 있으면 run.sh 가 배포하지 않고 대기 | 확인(11/02 journal), 지금 값은 드라이런으로 | plan F9, run.sh ready |
| 11 | cleanup 스크립트 1번째 줄·services/data/backups 권한은 아직 못 봄 — 결과 로그 line2·left_non600 으로 사후 확인 | 추정 | verifier 지적 2 |

## 물어볼 것
| # | 질문 | PO의 생각 |
|---|---|---|
| 1 | 커밋 C·push 를 해도 됩니까? | 됩니다 |
| 2 | 이 요청서·스크립트로 사용자에게 배포 승인을 요청해도 됩니까? 막을 위험이 있습니까? | 됩니다. 정지선 어긋남은 안전하게 끝남 |

## 참고 파일
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/deploy-request-20261103-bundle1.md
- /private/tmp/claude-501/-Users-gonnim-Project-MVP-Source-upbit-tradebot-mvp/98f63d2d-b8df-4e31-8e0c-2c80d63b11d2/scratchpad/deploy-1103/run.sh (원본 비교: 같은 scratchpad deploy-1101-13/run.sh)
- `git diff` (core/trailing_restore.py), tests/regressions/test_r_2026_11_03_stale_peak_restore.py
- /Users/gonnim/.claude-thetak/projects/-Users-gonnim-Project-MVP-Source-upbit-tradebot-mvp/98f63d2d-b8df-4e31-8e0c-2c80d63b11d2/tool-results/bbvs0rk6q.txt
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/CLAUDE.md, .claude/context/project-rules.md

---

# 답변 (1회)

**판정:** 진행
**이유:** 결론을 좌우하는 사실(변경 범위·시험·게이트 1205/1205·스크립트 차이·148줄 원인·ISO 형식)을 원 출처로 확인. 미확인 2건(정지선 기대값·cleanup 1번째 줄)은 드라이런·결과 로그로 실측되고 어긋나면 쓰기 없이 끝남. 고칠 것은 모두 권고.

## 고쳐야 할 것
| # | 중요도 | 무엇을 |
|---|---|---|
| 1 | 권고 | HANDOFF 1101-08·1102-02·1102-01 행을 지금 상태로 |
| 2 | 권고 | run.sh 5행 원본 이름 deploy-1101-13 으로 |
| 3 | 권고 | 커밋 C 메시지에 1205/1205 와 버전 구 → 신 |
| 4 | 권고 | 통보 문구에 「재시작 전 약 40시간 안의 최고가」 범위 |

## 사용자에게 물어야 할 것
- 없음(배포 ① 실행 승인은 요청서 6절대로 PO 가 올림)

## PO 반영 기록 (11/03)
- 1~4 모두 반영(3 은 커밋 메시지). 권고뿐이라 다시 묻지 않음.
