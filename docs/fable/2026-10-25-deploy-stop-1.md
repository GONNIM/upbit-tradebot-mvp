# 질의: D5 점검에서 FAIL 1건(root-writable)으로 배포를 멈췄고, 사용자에게 처리 방법 결정을 올리려 합니다

**지금 단계:** 리뷰 (배포 중 멈춤 → 사용자 결정 요청)
**다음에 하려는 일:** 사용자에게 아래 권고안(가)의 승인을 묻습니다. 승인 전에는 서버에서 아무것도 더 바꾸지 않습니다. 현재 서버 상태(D1~D4 완료, tradebot-v2 는 127.0.0.1:8502 에서만 대기, nginx·허용 목록·cron 미적용)를 그대로 둡니다.

## 지금까지 확인한 사실
| # | 사실 | 근거 (명령·출력·파일 경로) |
|---|---|---|
| 1 | D1 완료: 서버 HEAD 12ddb4f, dashboard.py:495 v1.2026.10.25.1611, .gitignore 89·90행 .v2_secret·.v2_allowlist | SSH 출력 (17:08) |
| 2 | D2 완료: .v2_secret 32바이트 600, PULLBACK 0바이트 600, git status 에 안 보임 | SSH 출력 (17:09) |
| 3 | D3 완료: 17:10:35 재시작(경계 17:09 확정 17:09:10 뒤, 미체결 0, 남은 85초). BOOT-RESUME success 7.2s, run_live_loop start 1회, 17:09 봉 CONFIRMED-NO-TRADE 17:12:55, 17:12 봉 CONFIRMED 17:15:11 Bar#201, 결함 태그·Traceback·ERROR·CRITICAL·locked 0, NRestarts 0 | journalctl -u tradebot (17:10:52, 17:15:44) |
| 4 | D4 완료: tradebot-v2 active 17:11:15, 127.0.0.1:8502 LISTEN, MemoryMax 157286400, CapabilityBoundingSet= (빈 값), ReadWritePaths `-` 접두 유지 | systemctl show |
| 5 | D5 `check_v2_unit.sh mcmax33`: 12항목 중 FAIL 1 = `root-writable`, 나머지 PASS (env·secrets·credentials 차단, proc-environ 차단, live-db-ro 등) | /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/scripts/v2/check_v2_unit_probe.py:145-161 |
| 6 | 원인: 실행 중 tradebot-v2 의 mountinfo 에서 `/` 는 ro 이지만 `/root` 가 rw 로 따로 마운트됨(581행). 유닛은 ProtectSystem=strict·ProtectHome=no. systemd 249 의 strict 는 /home·/root·/run/user 를 ProtectHome 몫으로 남겨 rw 로 둔다(systemd namespace.c 의 strict 표, READWRITE_IMPLICIT) | `grep /proc/<v2 pid>/mountinfo`, `systemctl show -p ProtectHome` = no, /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/deploy/tradebot-v2.service:21-22 |
| 7 | 뜻: v2 프로세스(root)가 저장소 루트의 EMA·MACD 설정 파일 등 /root 아래 파일을 쓸 수 있는 상태. v2 코드는 v2hist·PULLBACK 만 쓴다. services/data(실매매 DB)는 원래 설계상 쓰기 가능(요청서 4절 데이터 축 남는 위험) | 요청서 4절 |
| 8 | 외부 노출 없음: nginx /v2/ 미적용, 허용 목록 없음 → 투자자 화면 변화 없음, 8502 는 127.0.0.1 | ss -ltn |
| 9 | probe 잔재 없음 (.v2probe_* 없음) | ls |
| 10 | 요청서 2-5: 「FAIL 이 0 이어야 한다」, 2-0 「하나라도 다르면 멈추고 보고」 | /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/deploy-request-20261025.md |

## 물어볼 것
| # | 질문 | PO의 생각 |
|---|---|---|
| 1 | 권고안 (가)가 사실·실현 가능성·위험 면에서 맞는가: 유닛에 `ProtectHome=read-only` 1줄 추가 → 로컬 커밋(버전 갱신)·verifier·Fable → 사용자 승인 → 서버 pull·유닛 재복사·daemon-reload·tradebot-v2 재시작 → D5 다시(FAIL 0) → D6~D8 계속. ReadWritePaths(services/data·PULLBACK)와 InaccessiblePaths 는 더 구체적인 경로라 read-only /root 위에서도 그대로 적용될 것으로 봄 | 맞다고 봄. 다만 ReadWritePaths 가 ProtectHome=read-only 를 이기는지는 서버 첫 실행(D5 의 v2hist-write·pullback-open·live-db-ro-read PASS)으로 확인해야 함 |
| 2 | 이 수정은 엔진 코드를 건드리지 않지만 git pull 로 dashboard.py 버전 줄이 바뀐다. tradebot 을 다시 재시작하지 않으면 화면 버전은 1611 로 남는다. 재시작 없이 진행하고 3점 일치 보고에 「화면 버전 1611(다음 재시작 때 반영)」로 적는 것이 맞는가, 아니면 E1 조건으로 한 번 더 재시작해야 하는가 | 재시작 없이 진행 권고(재매매 영향 최소). 사용자 선택지로 둠 |
| 3 | 선택지 나(FAIL 을 알려진 틈으로 기록하고 그대로 D6~D8 계속)·다(v2 정지·배포 중단)를 함께 보이는 것이 맞는가 | 맞다고 봄 |
| 4 | 결정 대기 동안 tradebot-v2 를 켠 채로 두어도 되는가 | 외부 노출이 없어 그대로 둠 권고 |

## 참고 파일
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/deploy/tradebot-v2.service
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/scripts/v2/check_v2_unit.sh
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/scripts/v2/check_v2_unit_probe.py
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/deploy-request-20261025.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/fable/2026-10-25-deploy-exec-1.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/CLAUDE.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/.claude/context/project-rules.md

---

# 답변 1: D5 점검에서 FAIL 1건(root-writable)으로 배포를 멈췄고, 사용자에게 처리 방법 결정을 올리려 합니다

**판정:** 수정 후 진행
**이유:** 사실 1~4·6~10 은 서버 읽기 전용 SSH 와 systemd 249 원본으로 확인했고 기재와 일치. 다만 권고안 (가)는 그대로면 D5 가 다시 root-writable FAIL — check_v2_unit.sh 가 임시 유닛에 ProtectHome 을 넘기지 않음.

(직접 확인 요지: 서버 12ddb4f·1611, tradebot 17:10:35 NRestarts 0, 17:10 이후 BOOT-RESUME success·start 1회·NO-TRADE 17:12:55/17:19:05·CONFIRMED 17:15:11, 오류 0. v2 mountinfo `/` ro·`/root` rw. 외부 노출 0. v2 가 17:11 에 v2/__pycache__/*.pyc 를 실제로 씀 — /root 쓰기 가능 실증.)

## 질문별 답
| # | 질문 | 답 | 확신 |
|---|---|---|---|
| 1 | 권고안 (가) | 진단 맞음. systemd v249 namespace.c: strict 표 /root READWRITE_IMPLICIT(211행), protect_home_read_only 표 /root READONLY(148행), READONLY 가 우선(61·68·648행). 더 깊은 ReadWritePaths 는 make_read_only deny_list(1661~1670행)로 rw 유지. 단 check_v2_unit.sh 45~51·64~73행이 ProtectHome 을 넘기지 않아 스크립트·시험도 같은 커밋에 고쳐야 함. v2 쓰기는 api_write.py PULLBACK·db.py v2hist 뿐, 그 밖은 __pycache__(실패해도 오류 없음) | 높음 |
| 2 | tradebot 재시작 여부 | 둘 다 규칙 안. 재시작 없이 가면 보고에 「파일 버전 신 / 화면·실행 1611 / 다음 재시작 때 반영」 필수. 선택은 사용자 | 보통 |
| 3 | 선택지 나·다 | 맞음. (나)는 2-5 「FAIL 0」·spec A17(spec.md:233) 미충족이며, v2 가 EMA 파라미터 파일을 쓸 수 있는 채로 /v2/ 를 여는 것 | 높음 |
| 4 | 대기 중 v2 켜 둠 | 됨. 외부 노출 0 | 높음 |

## 고쳐야 할 것
| # | 중요도 | 무엇을 | 왜 | 어떻게 확인 |
|---|---|---|---|---|
| 1 | 막음 | (가)에 check_v2_unit.sh 수정 포함(ProtectHome 읽어 systemd-run 에 넘기고 unit-props 에 read-only 판정), tests/v2/test_deploy_files.py 두 시험 갱신 | 유닛만 고치면 D5 FAIL 반복 | 로컬 unittest 통과, 서버 PASS root-readonly·unit-props, FAIL 0 |
| 2 | 권고 | (나) 옆에 「2-5·A17 미충족」 | 사용자가 spec 이탈을 알고 고르게 | 결정 요청 본문 |
| 3 | 권고 | spec E18(spec.md:78)·runbook·유닛 머리 주석에 ProtectHome=read-only 기재 | 문서·유닛 어긋남 방지 | grep 각 1건 이상 |
| 4 | 권고 | 「미확인」 표현을 「systemd 249 원본으로 확인, 서버 D5 로 재확증」으로 | 위험 과대평가 방지 | 본문 |
| 5 | 권고 | 재시작 없는 경로의 보고 문구 고정 | 2026-09-12 배포 보고 규칙 | 보고 본문 |
| 6 | 권고 | __pycache__ 갱신 안 됨(메모리 재컴파일, 오류 없음) 한 줄 | 바뀌는 동작 고지 | ls v2/__pycache__ |

## 사용자에게 물어야 할 것
- 처리 방법 (가)/(나)/(다), (가) 시 tradebot 재시작 여부.

---

# 다시 묻기 (막음 1 처리)

**고친 권고안 (가):** 한 커밋에 다음을 넣는다 — ① `deploy/tradebot-v2.service` 에 `ProtectHome=read-only` 1줄과 머리 주석, ② `scripts/v2/check_v2_unit.sh` 가 `PROP_PROTECT_HOME` 을 읽어 systemd-run 에 `-p "ProtectHome=$PROP_PROTECT_HOME"` 으로 넘기고 unit-props 판정에 `read-only` 를 더함, ③ `tests/v2/test_deploy_files.py` 두 시험에 ProtectHome 추가, ④ spec E18·runbook 기재(권고 3), ⑤ dashboard.py 버전 갱신. 로컬 게이트(`scripts/regression_gate.sh`, tests/v2) → verifier → Fable → 사용자 커밋·push·서버 반영 승인 → 서버 pull(ff)·유닛 재복사·daemon-reload·`systemctl restart tradebot-v2` → D5 전체 다시(FAIL 0, PASS root-readonly·unit-props, a3, RSS, A2, EXPLAIN 8) → D6~D8. 쓰기 경로 유지 근거는 systemd 249 원본으로 확인했고 서버 D5 의 v2hist-write·pullback-open·live-db-ro-read 로 재확증한다(권고 4). ProtectHome=read-only 뒤에는 v2/__pycache__ 갱신이 안 되어 기동 때 메모리에서 재컴파일한다(오류 없음, 권고 6).
**선택지 (나):** 알려진 틈으로 기록하고 D5 나머지·D6~D8 계속 — 요청서 2-5 「FAIL 0」·spec A17 미충족, v2 가 EMA 파라미터 파일을 쓸 수 있는 채로 /v2/ 공개(권고 2).
**선택지 (다):** `systemctl disable --now tradebot-v2`, 배포 중단(D1~D3 는 남음 — 엔진은 새 app.py 로 정상, 버튼은 허용 목록이 없어 안 보임).
**(가) 의 tradebot 재시작:** 권고 = 재시작 없음. 보고에 「파일 v1.2026.10.25.HHMM / 화면·실행 코드 1611(12ddb4f) / 다음 재시작 때 반영」으로 고정(권고 5). 다른 선택지 = E1 조건으로 1회 더 재시작.

물어볼 것: 막음 1 이 해소됐고, 이 내용으로 사용자에게 결정을 올려도 되는가

---

# 답변 2: (다시 묻기 — 막음 1 처리)

**판정:** 진행
**이유:** 막음 1 은 고친 권고안 (가) ②·③ 에 들어 있어 해소. 권고 2~6 반영. 남은 것은 사용자 선택지(가·나·다, 재시작 여부)뿐이며 이것이 결정 요청 내용 자체.

(직접 확인: 로컬 deploy/·scripts/v2/·tests/v2/·spec·runbook·dashboard.py 변경 없음 — 승인 전 선행 수정 없음. regression_gate.sh 150~151행이 tests/v2 를 돌리므로 ③ 은 게이트에 걸림.)

## 질문별 답
| # | 질문 | 답 | 확신 |
|---|---|---|---|
| 1 | 막음 1 해소 | 해소. 임시 유닛도 /root ro 가 되어 root-readonly PASS 가능, ③ 이 회귀 방지. 실증은 서버 D5 재실행에서만 | 높음 |
| 2 | 결정 올려도 되는가 | 됨. 절차가 CLAUDE.md 워크플로우·배포 보고 규칙에 맞고, (나)·(다)의 위험이 적혀 있음 | 높음 |

## 고쳐야 할 것
| # | 중요도 | 무엇을 | 왜 | 어떻게 확인 |
|---|---|---|---|---|
| 1 | 권고 | v2 재시작 직후에도 tradebot ExecMainStartTimestamp 17:10:35·NRestarts 0 확인(A2) | v2 재시작이 D5 앞에 따로 있음 | systemctl show |
| 2 | 권고 | v2 재시작으로 nonce 저장소가 비어도 지금은 발급 토큰 0(허용 목록·nginx 미적용)이라 영향 없음을 한 줄 | 사용자가 물을 수 있음 | 요청 본문 |

## 사용자에게 물어야 할 것
- 처리 방법 (가)/(나)/(다), (가) 시 tradebot 재시작 여부.

## PO 처리
- 권고 1·2 를 결정 요청 본문과 (가) 실행 단계에 반영. 사용자에게 1025-11 로 결정 요청.
