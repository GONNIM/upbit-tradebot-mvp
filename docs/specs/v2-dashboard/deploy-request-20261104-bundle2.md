# 배포 ② 승인 요청서 — 1029-12 모의 지갑 덮어쓰기 막기 + 자리표시자 로그 문구 (2026-11-03 작성)

- 결정: 1103-01 「권고대로」(배포 ② = 1029-12), 1029-12 「권고대로」(계획 3판 D1~D8), 「1029-12 커밋 승인」(11/03 — 6175fbe·3f6f327 push).
- 서버 지금: 46e2864 (v1.2026.11.03.1532), tradebot 11/03 15:45:10, tradebot-v2 11/01 14:21:31 (배포 ① 보고 `deploy-report-20261103-bundle1.md`).
- 배포 대상: 커밋 C(이 요청서를 넣는 문서 커밋) — 46e2864 위에 b56cbec(문서)·6175fbe(코드)·3f6f327(시험 기준)·C 가 fast-forward 로 쌓임.
- 방식: 배포 ① 과 같은 서버 안 대기 스크립트(`/root/deploy-1104/{run.sh,helper.py,notify.py}`) — deploy-1103 run.sh 에서 값만 바꾸고, 정체 매도 꺼짐 대기 조건과 백업 권한 블록을 뺌(이번 범위 밖). helper.py·notify.py 는 배포 ① 과 같은 파일.

## 1. 바뀌는 것
| # | 무엇 | 파일 | 실매매 영향 |
|---|---|---|---|
| 1 | 판정 W: 새 전략 켜짐 또는 보유·예약이면 모의 지갑을 지킴 | ui/pullback_lock.py `keeps_wallet` | 없음 — 주문 경로 무변경. 새 전략 켜짐이면 실계좌 엔진은 시작할 수 없음(engine_manager.py:130·655). 활성 전략이 EMA 인데 모의 보유·예약만 남은 경우는 실계좌 화면 캐시 갱신만 건너뜀(엔진 1분 동기화가 따로 채움) |
| 2 | 로그인 검증 3곳이 W 참이면 지갑 표·운용자산을 쓰지 않음, 화면 문구 | services/auto_verify.py, app.py | 없음(실계좌 엔진은 1분 동기화로 캐시를 따로 채움) |
| 3 | 모의 엔진 시작 때 1분 동기화 명단에서 뺌 | engine/order_reconciler.py `register_user` TEST 분기 | 없음 — 실계좌 분기·미체결 추적 그대로 |
| 4 | 모의 대시보드 현금 덮어쓰기 조건에 W | pages/dashboard.py | 없음(모의 화면만) |
| 5 | 워밍업 자리표시자 갱신 로그 문구(BUY·SELL) | services/db.py | 없음(SQL·반환값 그대로) |
| 6 | 화면 버전 v1.2026.11.03.1532 → v1.2026.11.03.2304 | pages/dashboard.py | 표시만 |

core/trader.py·engine/live_loop.py·매매 판정·주문 무변경. 실계좌 화면에서 달라지는 것: 새 전략 켜짐·보유·예약 중일 때만 「DB 동기화: 새 전략 모의 지갑을 지키려고 건너뜀」. 지금 서버는 EMA 실계좌라(새 전략 꺼짐) 배포 직후 화면·동작 변화는 없을 것으로 본다(활성 전략 EMA 는 스크립트 정지선이 run.sh:67-69 에서 확인 — 11/04 정정: 처음 판의 「정지선 아닌 입회 때 확인」은 틀린 문구).

## 2. 실행 순서 (서버 스크립트)
0. 사용자 push 승인(6절 1) → Claude 가 커밋 C push → origin/main = C 확인. 스크립트 정지선이 origin/main = C 를 보므로 push 가 드라이런보다 먼저다.
1. 사용자 `!` 업로드·드라이런(6절 2 의 첫 명령 — 보고서 본문에 전체 명령을 적음). 드라이런 결과의 `untracked=`·`ready`·`user_db_count` 를 Claude 가 읽고 본 띄우기를 권한다. 드라이런은 정지선·대기 조건·키 있음/없음·사용자 DB 수(R7)·운영자 채널 DRY 알림 1건만(작업 트리·DB·설정 쓰기 0 — git fetch·결과 로그·잠금 파일만).
2. 사용자 `!` 본 띄우기.
3. 스크립트: 정지선(HEAD=46e2864, git status 줄 5, tradebot 기동 11/03 15:45:10·NRestarts 0, v2 기동 11/01 14:21:31, 비밀 파일 600·사본 0, 전략 EMA, journal 실패 표지 0, origin/main = 커밋 C) → 봉마다 보유 0·묶임 0·미체결 0·잔고 갱신 120초 안·새 audit BUY 없음·minute3·최근 5분 ERROR 0 → DB 백업(무결성 ok·600) → 다음 봉 재확인·경계까지 60초 이상 → `git merge --ff-only C` → `systemctl restart tradebot` → 기동 확인 → 첫 봉 2개·check_v2_unit, 3점 일치·새 코드 표식(keeps_wallet·wallet_kept·placeholder_log) 기록 → 「배포 완료」 알림 → 1시간 관찰 → 「1시간 관찰 통과 — 배포 ② 끝」 알림.
4. 되돌리기(승인 범위): 기동 확인 실패·10분 봉 줄 0·Bar# 형식 변화·기동 뒤 ERROR·관찰 중 비활성/재시작 → `git checkout 46e2864` + 재시작 1회 → 알림. 되돌린 뒤 서버는 detached HEAD — 다음 배포 전 `git checkout main`.
5. 마감: 재시작 명령 11/07 23:59 까지. 취소: `systemctl stop deploy-1104`.
6. 스크립트가 도는 동안 origin/main 에 push 하지 않는다(정지선이 origin/main = C 를 봄).
7. 「배포 완료」 알림 뒤 1시간 동안 화면에서 엔진 정지·시작을 누르지 않는다.

## 3. 시험
- 커밋 B 기준 게이트 `scripts/regression_gate.sh`: 회귀 1232/1232 · v2 433 OK · JS 통과 · NETGUARD 0 (11/03 23시).
- 새 회귀 `tests/regressions/test_r_2026_11_03_mock_wallet.py` 26건. verifier 「사용자 보고 가능」, Fable `docs/fable/2026-11-03-1029-12-impl-1.md` 「진행」.
- 백테스팅 해당 없음(매매 판정 무변경).

## 4. 배포 뒤 (운영자 입회 — 마지막 확인)
- 2-5 브라우저: 버전 v1.2026.11.03.2304 표시, 정지 뒤 바로 시작 「정리 중」 문구.
- 실계좌 검증 문구(새 전략 켜짐일 때만 보임)와 운용자산 줄 「새 전략 거래 중이라 그대로 둡니다」 문구를 바꿀지 결정(구현 Fable 권고 4).
- 첫 모의 전환 운영자 절차(계획 6절): 로그인 화면 로그아웃·새로고침 → 모의 로그인 → 설정 값 그대로 저장 → 두 값·코인 0 확인 → 모의 EMA 시작 → 새 전략 전환. check_v2_unit 2회째.
- 그 뒤 임시 규칙 「정지 뒤 3분 이상, 시작은 신버전 단추」 끝.
- 로그 집계는 「실시간 재판정」과 「워밍업 자리표시자 갱신」을 함께 찾는다.

## 5. 투자자 통보
입회 확인 뒤 한 번(1101-04). 넣을 줄: 「새 전략을 켜 두신 동안에는 실계좌 화면을 열거나 계좌를 다시 확인해도 모의 현금·코인과 새 전략 운용자산이 실계좌 값으로 바뀌지 않습니다.」

## 6. 정해 주실 것
1. 커밋 C(이 요청서·HANDOFF) push 승인 — 문서만. push 뒤 배포가 끝날 때까지 다른 push 없음.
2. 배포 ② 실행 승인(위 2절 범위: 재시작 1회 + 되돌리기 1회, 커밋 C 만, 11/07 23:59 까지). 승인은 push 뒤 Claude 가 드리는 업로드·드라이런 한 줄을 직접 실행하시는 것으로 갈음하고, 드라이런 결과를 본 뒤 본 띄우기 한 줄도 직접 실행하신다(배포 ① 과 같음).
   - 업로드·드라이런: 서버에 `/root/deploy-1104`(700) 를 만들고 run.sh·helper.py·notify.py 를 올려 600 으로 둔 뒤 sha256 앞 16자를 보이고, `systemd-run --unit=deploy-1104-dry --collect --wait -p User=root --setenv=HOME=/root /bin/bash /root/deploy-1104/run.sh --dry` 뒤 `dry-result.log` 를 읽는다.
   - 본 띄우기: `systemd-run --unit=deploy-1104 --collect -p User=root --setenv=HOME=/root /bin/bash /root/deploy-1104/run.sh` 뒤 `result.log` 를 읽는다.
   - 명령에 비밀 값은 없다.
