# 질의: 서버 점검 조치(1108-01 보안 막기 · 1108-02 디스크·DB 늘어남 막기) 스크립트를 마쳤고, 커밋·push 뒤 서버에 실행하려 합니다

**지금 단계:** 구현 (서버 변경 실행 직전)
**다음에 하려는 일:** 저장소 변경(스크립트 4개 · 설정 원본 6개 · 버전 줄 · 기록 문서 · HANDOFF)을 커밋·push 하고, 서버에 harden-a → harden-confirm(새 연결) → harden-c(갱신·재부팅) → harden-verify 순서로 실행합니다. 문서 변경은 이 질의에 묶었습니다.

## 지금까지 확인한 사실
| # | 사실 | 확인/추정 | 근거 |
|---|---|---|---|
| 1 | 사용자가 조치 실행과 위험 패치를 승인했다(11/08 「권하는 조치 실행하기. 앞으로 문제가 될 점 패치하기.」) | 확인 | 대화 |
| 2 | 8501 바깥 연결 0개, 사용자는 nginx 443 으로 들어온다(접속 기록 36,563줄) | 확인 (11/08 11:43) | scratchpad/audit-6.out 8501-peers · nginx |
| 3 | tradebot_boot.py 가 TRADEBOT_ADDRESS 를 읽는다(기본 0.0.0.0) — 코드 변경 없이 drop-in 으로 바꿀 수 있다 | 확인 | scripts/tradebot_boot.py:171-172 |
| 4 | SSH 키 1개, 다른 계정 없음, 7일 로그인 모두 키 방식 | 확인 | audit-6.out authorized_keys · 11/07 점검 |
| 5 | sshd_config 12행 Include 가 본문 PermitRootLogin(38행)보다 먼저 → drop-in 값이 이긴다 | 확인 | audit-6.out sshd-files |
| 6 | fail2ban sshd 현재 maxretry 20 · findtime 600 · bantime 1800, 차단 2번 | 확인 | audit-7.out f2b |
| 7 | position_history 는 코드에서 쓰기만 하고 읽지 않는다 | 확인 (grep, verifier 판정은 아래) | services/db.py:908 · core/trader.py:1626,1647 |
| 8 | 지울 보유 기록 줄 10,438,611(10/09 이전), 지울 배포 백업 4개 4,321,869,824 바이트 | 확인 (서버 dry-run 11/08) | 대화 dry-run 출력 · 기록 문서 3절 |
| 9 | 엔진 파이썬은 /usr/local/bin/python3.12(apt 밖) | 확인 | audit-7.out venv-python |
| 10 | sshd_config · nginx 꾸러미 설정 파일은 손댄 것이 없다고 dpkg 가 본다. 갱신은 confold 로 지금 설정 유지 | 확인 | audit-7.out conffiles-changed(빈 출력) |
| 11 | 보유 PYUSD · USDT · HYPER 약 6.2만 원어치, 재부팅 때 엔진이 1~2분 멈춘 뒤 BOOT-RESUME 으로 재개 | 확인(보유) · 추정(멈춤 시간 — 이전 배포 재시작 기록) | audit-7.out positions-value · deploy-1104-1106.sh wait_resume |
| 12 | 회귀 게이트 1318/1318 통과 | 확인 | scratchpad/gate-1108.log |
| 13 | 알림 글 · 화면은 그대로이고 버전 줄만 바뀐다 → 투자자 통보 대상 아님 | 확인 | git diff |
| 14 | verifier 판정 | (아래에 붙임) | 이 파일 「verifier」 절 |

## 물어볼 것
| # | 질문 | PO의 생각 |
|---|---|---|
| 1 | 보유가 있는 채로 재부팅해도 되는가 | 미체결 0 · 예약 0 · 3분 봉 안 20~100초 조건은 이전 배포 재시작과 같다. 보유는 재개 뒤 그대로 관리된다. 진행 |
| 2 | SSH·방화벽 10분 자동 되돌림(새 연결로 풀기)이 잠김을 충분히 막는가 | cafe24 콘솔이 마지막 수단이다. 진행 |
| 3 | 보유 기록 표 첫 정리를 엔진이 도는 중에 5,000줄 묶음으로 해도 되는가 | 엔진 연결 timeout 30초 · busy 3초, 묶음 사이 0.3초. 진행 |
| 4 | 자동 보안 갱신을 켜는 것이 실매매에 위험한가 | 자동 재부팅은 끔. nginx·ssh 는 갱신 때 잠깐 재시작될 수 있다. 엔진 파이썬은 apt 밖. 진행 |

## 참고 파일
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/operations/server-hardening-20261108.md
- /private/tmp/claude-501/-Users-gonnim-Project-MVP-Source-upbit-tradebot-mvp/88cffd39-a81d-45f6-b588-c3b1fe0c80cb/scratchpad/harden-a.sh
- /private/tmp/claude-501/-Users-gonnim-Project-MVP-Source-upbit-tradebot-mvp/88cffd39-a81d-45f6-b588-c3b1fe0c80cb/scratchpad/harden-confirm.sh
- /private/tmp/claude-501/-Users-gonnim-Project-MVP-Source-upbit-tradebot-mvp/88cffd39-a81d-45f6-b588-c3b1fe0c80cb/scratchpad/harden-c.sh
- /private/tmp/claude-501/-Users-gonnim-Project-MVP-Source-upbit-tradebot-mvp/88cffd39-a81d-45f6-b588-c3b1fe0c80cb/scratchpad/harden-verify.sh
- /private/tmp/claude-501/-Users-gonnim-Project-MVP-Source-upbit-tradebot-mvp/88cffd39-a81d-45f6-b588-c3b1fe0c80cb/scratchpad/audit-6.out
- /private/tmp/claude-501/-Users-gonnim-Project-MVP-Source-upbit-tradebot-mvp/88cffd39-a81d-45f6-b588-c3b1fe0c80cb/scratchpad/audit-7.out
- 저장소 변경: `git -C /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp diff` · scripts/server/prune_*.sh · deploy/server-hardening/*
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/CLAUDE.md · /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/.claude/context/project-rules.md

## verifier
1회 판정(11/08 11:58): 10개 주장 중 확인 5 · 일부 반박 4 · 미확인 1, 지적 N1~N13. 반영한 것:
- N1 apt 를 SSH 세션 안에서 돌림 → harden-c 를 서버 파일로 올려 `systemd-run --unit=harden-c` 로 돌림.
- N2 미체결 확인과 재부팅 사이 빈틈 → 재부팅 바로 앞에 미체결·예약·실계좌 엔진 켜짐(LIVE_OK)·엔진 오류·443 8초 8번·봉 창을 다시 보고, 하나라도 다르면 재부팅 안 함.
- N4 묶음 시간 미측정 → 5,000줄 묶음, 묶음마다 시간 재고 1초 넘으면 멈춤.
- N5 되돌림 10분 안에 긴 단계 → 백업·보유 기록 정리를 SSH 변경 앞으로 옮기고, 되돌림 15분.
- N6 운영자 주소 → 7일 키 로그인 10번 이상 주소를 서버 jail.local 에만 ignoreip 로 넣음(저장소에는 안 올림).
- N7·N10·N12 문서 → 보관 기한(11/16), 갱신 전체 259개, 4월 백업 삭제, 8501 은 A단계에서 바로 막힘, 보유 금액 지움.
- N8 → verify 에 BOOT-RESUME 판정·비밀 파일 600·사본 확인, 1시간 뒤 한 번 더. 게이트 1318/1318 통과(gate-1108.log, 판정 뒤 끝남). 재부팅 전 DB 사본은 11/08 11:00 주간 백업.
- N11 → verify 에 ufw 로그의 막힌 8501 시도 수.
남긴 것: N3 새 커널 부팅 실패 시 자동 되돌림 없음(콘솔로 옛 커널 선택 — 문서 「남는 위험」), N9 정체 감시가 평가 실패는 못 잡음(문서 「남는 위험」), N13 rsyslog python 전체(그대로).


---

# 답변 1 (Fable, 11/08)

**판정:** 수정 후 진행
**이유:** harden-a.sh 자동 되돌림 예약 명령에 띄어쓰기가 빠져(`--on-active=900--unit=…`) systemd-run 이 실패하고, 1단계 HEAD 검사 때문에 다시 돌릴 수도 없다. 이 한 곳을 고치면 나머지 설계는 파일과 점검 출력으로 확인했다.

질문별 답(요지): 1 보유 62,380원(움직이는 것은 HYPER 25,182원)으로 재부팅 가능, 재개 판정 문자열은 boot_resume.py 173·185행과 일치(높음). 2 고친 뒤에는 잠김을 막음, fail2ban 은 되돌림 대상이 아님(높음). 3 엔진 연결 timeout 30·busy 3000ms·WAL, 5,000줄 묶음·1초 멈춤 확인, 최소 10분 30초(높음). 4 허용 출처가 jammy·security·ESM 뿐이라 보안 갱신만, 자동 재부팅 끔(높음).

고쳐야 할 것:
1. (막음) harden-a.sh 59행 띄어쓰기.
2. (권고) 1단계를 「HEAD 가 EXPECT_OLD 또는 EXPECT_NEW」로 — 다시 돌릴 수 있게.
3. (권고) 머리말 실행 명령에 `EXPECT_NEW=<해시> bash -s`, 「10분」→「15분」.
4. (권고) watchdog 에 `export LC_ALL=C.UTF-8` 또는 한글 없는 패턴.
5. (권고) 운영자 주소 0개면 jail.local 넣지 않기, Found 주소와 Accepted 주소 겹침 확인.
6. (권고) 평소 24시간 엔진 오류 줄 수 확인.
7. (권고) 질의서 「2만 줄」→「5,000줄」.
사용자에게 물어야 할 것: 없음(운영자 주소가 Found 에 있으면 그때 묻기).

---

# 질의 2: 답변 1 의 고칠 것을 반영했고, 커밋·push 뒤 서버 실행하려 합니다

**지금 단계:** 구현 (서버 변경 실행 직전, 다시 묻기)
**다음에 하려는 일:** 질의 1 과 같습니다.

## 지금까지 확인한 사실
| # | 사실 | 확인/추정 | 근거 |
|---|---|---|---|
| 1 | 59행(지금 60행) `--on-active=900 --unit=harden-rollback` 으로 고침. 같은 이름 예약이 남아 있으면 먼저 멈추고 지움 | 확인 | `grep -n 'on-active=900 --unit' harden-a.sh` 1줄 |
| 2 | 1단계: HEAD 가 1d3922f 또는 새 해시면 통과, 새 해시면 병합 건너뜀. 설정 사본은 `cp -pn`(다시 돌려도 원본 사본을 덮지 않음), nginx 되돌림만 `cp -p` | 확인 | harden-a.sh 18·27·33·41·74행 |
| 3 | 머리말 실행 명령·15분 문구 고침 | 확인 | harden-a.sh 3~6행 |
| 4 | watchdog 에 `export LC_ALL=C.UTF-8` 넣음 | 확인 | scripts/server/watchdog_tradebot_engine.sh 9행 |
| 5 | 운영자 주소 0개면 jail.local 지우고 경고. 7일 Accepted 주소와 fail2ban Found 주소(오늘·어제 로그) 겹침 0개 | 확인 (11/08 서버 읽기) | 대화 출력 overlap=0 |
| 6 | 엔진 24시간 ERROR·CRITICAL·Traceback 줄 4개 — 30분 창에 걸리면 harden-c 가 재부팅 없이 멈추고 다시 돌리면 됨 | 확인 (11/08 서버 읽기) | 대화 출력 4 |
| 7 | 질의서 3번 질문 5,000줄로 고침 | 확인 | 이 파일 |
| 8 | 4개 서버 스크립트 `bash -n` 통과 | 확인 | 대화 출력 syntax-ok |

## 물어볼 것
| # | 질문 | PO의 생각 |
|---|---|---|
| 1 | 반영이 맞고 진행해도 되는가 | 진행 |

## 참고 파일
- 질의 1 과 같음


---

# 답변 2 (Fable, 11/08)

**판정:** 진행
**이유:** 답변 1 의 막음 1건과 권고 6건이 모두 파일에 반영된 것을 직접 확인했다(harden-a.sh 3~6·18·27·33·41~42·59~60·74·85~88행, watchdog 9행, 질의서 29행, `bash -n` 통과). 다시 돌리는 경우도 3-1·3-2·5·6·7 단계는 같은 결과이고 4단계는 예약을 새로 건다.
고쳐야 할 것: (권고) 실행 뒤 기록 문서 4절에 「운영자 주소 제외 개수」와 「Running timer as unit: harden-rollback.timer」 줄을 옮겨 적는다.
사용자에게 물어야 할 것: 없음
