# 질의: 결정 1026-23 을 1차 계획서에 반영(verifier 3회 「승인 요청 가능」)했고, 사용자에게 계획 재승인을 요청하려 함

**지금 단계:** 계획
**다음에 하려는 일:** 고친 계획서 `plan-proposal-match-20261026.md` 의 승인을 사용자에게 요청한다(새 번호 1026-24). 묶은 작은 문서 변경: HANDOFF 0절·0-1 표에 1026-21(재제안 지시로 대체)·1026-23(사용자 「1 가, 2 가」)·1026-24 를 적는다 — 매매·서비스 영향 없음, 커밋 없음. 승인되면 Task 1~9(+4-0)를 subagent-driven 으로 구현한다(코드 커밋·배포는 각각 따로 승인).

## 지금까지 확인한 사실
| # | 사실 | 근거 (명령·출력·파일 경로) |
|---|---|---|
| 1 | 사용자 결정 1026-23 「1 가, 2 가」(10/27) — 홈 그림 배치 + 잠김·기록 시각·매매 중지·로그아웃 유지, 백테스터 업비트 데이터는 서버 중계·보관 | 이 세션 사용자 메시지, 재제안서 scratchpad proposal-home-backtester-20261026.md |
| 2 | 직전 Fable 「진행」(재제안) | docs/fable/2026-10-26-home-backtester-reproposal-1.md |
| 3 | 계획서 고침: 머리말 결정 1026-23·D8 개정, 사라지는 것 표, Review Focus 1, Task 1·2(basic.js 는 매매 중지·로그아웃만 남김, 자산 카드 잠김·기록 시각 2줄), 새 Task 4-0(서버 중계·보관), Task 4(서버 경로·202 폴링), Task 7 안내, Task 9 Step 3·5·6 | `git diff -- docs/specs/v2-dashboard/plan-proposal-match-20261026.md` |
| 4 | verifier 1회 「고칠 것 있음」 13건(실매매 3: 수집 중 pid, 418 지속, 배포 관찰) → 반영 | 이 세션 verifier 보고 |
| 5 | verifier 2회 「고칠 것 있음」 6건(경미, 반박 2) → 반영 | 같음 |
| 6 | verifier 3회 「사용자 승인 요청 가능」, 새 어긋남 0 | 같음 |
| 7 | PO 구현 선택 2건: 긴 수집은 배경 작업 + 202·진행률(nginx 기본 60초, 서버 설정 무변경) / 418 은 `.halt.json` 으로 운영자 해제 전까지 정지 | 계획서 Task 4-0 Interfaces, 서버 nginx `/v2/` 블록 timeout 없음(verifier SSH) |
| 8 | 서버 systemd 249 — MemoryPeak 없음, MemoryCurrent 폴링으로 측정 | verifier SSH |
| 9 | 미확인 1건: 418 이 같은 IP 의 주문 API 까지 막는지 | 업비트 rate-limits 문서에 명시 없음 |

## 물어볼 것
| # | 질문 | PO의 생각 |
|---|---|---|
| 1 | 고친 계획서가 결정 1026-23 과 재제안서 안전장치를 빠짐없이, 서로 어긋남 없이 담았는가 | 담았다(verifier 3회) |
| 2 | Task 4-0 의 엔진 보호(5회/초·sec≤4·429 60초·418 정지 파일·매 요청 pid·동시 1건·미리 받기 지연·배포 뒤 「응답 없음」 4종 전후 비교)가 실매매 위험을 충분히 낮추는가 | 충분하다 |
| 3 | PO 구현 선택 2건(202 방식, 418 수동 해제)이 사용자 결정 범위 안인가, 사용자에게 따로 물어야 하는가 | 결정 범위 안의 구현 세부. 승인 요청서에 적어 알린다 |
| 4 | 사용자 지시 「1분 이내」를 계획이 보장하는 범위(엔진 종목 수 초, 다른 종목 데이터 약 44~55초 + 계산)와 확인 방법(Task 9 Step 3 로컬, Step 6 배포 뒤)이 적절한가 | 적절. 조건부임을 승인 요청에 적는다 |

## 참고 파일
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/plan-proposal-match-20261026.md
- /private/tmp/claude-501/-Users-gonnim-Project-MVP-Source-upbit-tradebot-mvp/e1c17aff-d11f-4e52-bd3f-aedba9d389d8/scratchpad/proposal-home-backtester-20261026.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/fable/2026-10-26-home-backtester-reproposal-1.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/spec.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/HANDOFF.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/CLAUDE.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/.claude/context/project-rules.md

---

## Fable 답변서 전문 (2026-10-27, Agent model: fable)

**판정:** 진행
**이유:** 계획서 본문·diff·코드 줄·서버 실측(SSH 읽기 전용)으로 대조한 사실 가운데 반박된 것이 없습니다. 고쳐야 할 것은 모두 권고이고, 다음 단계(사용자 승인 요청)는 되돌리기 어려운 동작이 아닙니다.

### 사실 대조
- 1: 사용자 메시지는 볼 수 없어 미확인, 계획서 12행·재제안서와 내용 일치 확인. 2·3·7·8: 확인됨(nginx `/v2/` 에 proxy_read_timeout 없음, systemd 249.11·MemoryCurrent 만). 4·5·6: verifier 원문을 받지 못해 미확인. 9: 미확인 그대로.
- 인용 줄 확인: v2/status.py:46·56, v2/api_read.py:260, services/db.py:1659-1664, engine/boot_resume.py:54, core/rest_reconcile.py:280-284, core/data_feed.py:284·1068·1239, tests/v2/test_basic_pause.py:525-532, tests/v2/test_server.py:230-244, scripts/v2/dev_server.py:128-141, backtester.js fetchKlines `{t,o,h,l,c}`, 서버 유닛·.engine_alive.json pid·HEAD 627b136.

### 질문별 답
| # | 답 | 확신 |
|---|---|---|
| 1 | 빠짐·어긋남 없음. 재제안서와 다른 구현 세부 2건(basic.js 유지, 거래량 미보관)은 결정 범위 밖 세부 | 높음 |
| 2 | 충분히 낮음. 남는 위험: 같은 1초 겹침 429 1회(Step 6(a)로 가시화), 같은 pid 스레드 재시작 미감지(알려진 한계), 418 주문 API 범위 미확인 | 보통 |
| 3 | 결정 범위 안. 418 수동 해제는 승인 요청에 한 줄로 알리면 충분(운영자 = 사용자) | 높음 |
| 4 | 적절. 조건을 그대로 적으면 됨 | 높음 |

### 고쳐야 할 것 (모두 권고 — PO 반영)
1. Step 5 spec 갱신 목록에 A14(234행) 추가 — 반영.
2. 요청 머리 「만」 → Origin·Authorization 미부착, Tornado 기본 머리 유지 — 반영.
3. 미리 받기 대상 파일은 지우지 않음 명시 + 시험 단언 — 반영.
4. ru_maxrss 단위(macOS 바이트, Linux KB) — 반영.
5. 승인 요청에 구현 세부 2건·418 수동 해제·202 폴링 한 줄씩 — 승인 요청 본문에 반영.
6. HANDOFF 13행과 0-1 표의 1026-21 함께 갱신 — 반영.

### 사용자에게 물어야 할 것
- 없음
