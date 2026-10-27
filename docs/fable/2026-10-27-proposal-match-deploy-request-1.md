# 질의: 1차 화면 배포 요청서(1027-02)를 썼고(verifier 2회째 「승인 요청 가능」), 사용자에게 배포 승인을 요청하려 함

**지금 단계:** 계획 (배포 승인 요청 — 사실·실현 가능성·위험 확인)
**다음에 하려는 일:** 사용자에게 요청서 6절 결정 1~4 와 문서 커밋을 묻는다. 승인되면 (1) 요청서·이 질의 파일·HANDOFF 갱신을 문서 커밋 1개로 커밋·push(`pages/dashboard.py` 버전 갱신 포함 — 이 커밋이 배포 대상 HEAD 가 되며 1d0466a 와의 차이는 docs·버전 줄뿐), (2) 배포는 사용자가 고르는 세션에서 2-0 재측정 → 실행 직전 Fable 질의 → 2-1~2-6. 이 단계에서 서버 쓰기는 없다.

## 지금까지 확인한 사실
| # | 사실 | 근거 (명령·출력·파일 경로) |
|---|---|---|
| 1 | 사용자 「1027-02 시작, 1027-03 그대로」(10/27) | 이 세션 사용자 메시지 |
| 2 | 대상 1d0466a(v1.2026.10.27.0918) = origin/main, 서버 627b136(1209), diff 49개, v2/tests/docs 밖은 pages/dashboard.py·ui/v2_entry.py, 엔진 경로 0 | `git diff --name-only 627b136 1d0466a`, verifier SSH |
| 3 | 서버 정지선: tradebot 기동 10/26 00:25:22·NRestarts 0, tradebot-v2 17:34:30, allowlist 8B, 미추적 5, tornado 6.5.1, fileWatcherType none, 디스크 여유 20G, v2_candles 없음, 비밀 파일 600 | verifier SSH 읽기 전용 |
| 4 | 구버전 화면 버전은 2058(엔진 기동 뒤 627b136 pull 미반영) | 서버 reflog, HANDOFF:20 |
| 5 | 서버 엔진 KRW-JTO 3분봉 → 미리 받기 72회 약 1.2분, 파일 KRW-JTO_3.json | 서버 EMA params `interval: minute3`, journal [CONFIRMED] 3분 간격 |
| 6 | 서버 TLS api.upbit.com 확인(HTTP 요청 없이 핸드셰이크만, TLSv1.3) | PO SSH 09:4x |
| 7 | 기준선: 엔진 시세 실패 표지 8종 24h 0(10/07 이후 0), 처리한 봉 24h 486(고유 480), 1h ERROR류 0 | PO·verifier journalctl |
| 8 | memory.stat 경로 존재(cgroup2), anon 약 20 MiB(지금) | verifier SSH |
| 9 | tradebot-v2 stop 은 엔진과 의존 없음, allowlist 비우면 버튼·API·미리 받기 멈춤, 418 해제 절차 runbook 과 같음 | verifier systemctl show·코드 |
| 10 | 주간 자동 DB 백업 10/25 존재 | 서버 ls services/data/backups |
| 11 | verifier 1회 「수정 후 승인」 9건(반박 2: 화면 버전·미리 받기 횟수) → 반영 → 2회 「승인 요청 가능」, 경미 2건 반영 | 이 세션 verifier 보고 |
| 12 | 직전 구현 단계 Fable 「진행」 | docs/fable/2026-10-27-proposal-match-impl-1.md |

## 물어볼 것
| # | 질문 | PO의 생각 |
|---|---|---|
| 1 | 요청서의 단계·멈춤 조건·되돌리기가 실매매(엔진) 보호에 충분한가. 특히 서버 IP 첫 업비트 호출(미리 받기 72회 1회/초, 최악 경우 메모리 측정 때 다른 종목 216회 5회/초) | 충분. 실패 표지 8종 1건이면 즉시 v2 정지, 최악 측정은 30분 관찰 뒤·[CONFIRMED] 직후 1회 |
| 2 | 4절 「418 시 엔진 시세 조회도 막힘」을 결정 4 로 사용자에게 묻는 방식이 맞는가 | 맞음 |
| 3 | 배포 전 요청서 문서를 커밋하고 그 커밋을 배포 대상으로 하는 것(차이 docs·버전 줄)이 규칙과 맞는가 | 맞음(직전 배포들과 같은 방식) |
| 4 | 실행 세션: 새 세션 권고가 맞는가 | 맞음(이 세션 맥락이 길어 압축 위험, 직전 배포들도 새 세션) |
| 5 | 투자자 통보 A″ 문안에 사실과 다른 곳이 있는가(「처음 받는 종목 1분 남짓」은 로컬 54초 근거) | 없음. 서버 체감은 2-4 에서 잰 뒤 보낸다 |

## 참고 파일
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/deploy-request-20261027-proposal-match.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/deploy-request-20261026-pc-chart.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/impl-report-20261026-proposal-match.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/operations/v2-runbook.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/HANDOFF.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/v2/candles.py
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/CLAUDE.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/.claude/context/project-rules.md

---

## Fable 답변서 전문 (2026-10-27, Agent model: fable)

**판정:** 진행
**이유:** 서버 정지선·코드 상한·미리 받기 전제(엔진 생존 파일·활성 전략 EMA·KRW-JTO 3분)를 직접 확인했고 요청서 값과 모두 맞음. 고칠 것은 모두 권고이며, 「직전 배포들과 같은 방식」 근거 하나는 사실과 다르지만 방식 자체는 규칙에 맞음.

### 사실 대조
- 2·3·4·5·7·8·9·10: 확인됨(서버 SSH 읽기 10:1x, reflog, EMA params minute3, 실패 표지 0, 봉 486, memory.stat anon 약 20 MiB, 유닛 의존 없음, 백업 존재). 6: 미확인(업비트 연결 안 함). 1·11·12: 미확인(세션 메시지·verifier 원문 미수령).
- 추가: .engine_alive.json 10:09:13 갱신·running mcmax33 true, candles.py 상한 상수와 요청서 4절 일치, 캔들 경로 세션 없으면 401.

### 질문별 답
| # | 답 | 확신 |
|---|---|---|
| 1 | 충분. 엔진은 3분 경계 +10초에 1초 안 캔들 약 4회를 보내 사용자 5회/초와 겹치면 한도에 닿음 — sec≤4 쉼이 막고, 최악 측정을 [CONFIRMED] 직후로 잡은 것이 맞음 | 높음 |
| 2 | 맞음. 엔진 경계 호출 수를 4절에 적으면 숫자로 비교 가능 | 높음 |
| 3 | 규칙에 맞음. 단 「직전 배포들과 같은 방식」은 사실과 다름(직전은 요청서 미커밋·문서 커밋 서버 미반영) — 새 방식으로 적을 것 | 높음 |
| 4 | 맞음(직전 두 배포도 새 세션) | 높음 |
| 5 | 매매 중지 문장 코드와 맞음. 「1분 남짓」은 로컬 54.2초보다 큼 — 측정 뒤 「약 1분」 등으로 | 높음 |

### 고쳐야 할 것 (모두 권고 — PO 반영)
1. 「직전 배포들과 같은 방식」 → 「이번부터 새 방식」 — 요청서 6절 5·사용자 보고에 반영.
2. 문서 커밋에 impl-report 정정 포함 명시 — 요청서 6절 5·사용자 보고에 반영.
3. 4절에 엔진 경계 호출 수 — 반영.
4. 24시간 봉 판정에 고유 ts= 수(기대 480) — 반영.
5. A″ 「1분 남짓」 → 「약 1분」, 서버 측정 뒤 조정 — 반영.

### 사용자에게 물어야 할 것
- 없음
