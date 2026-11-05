# Ver2 배포 승인 요청서 — 1105-09 백테스터(1단계) + 새 전략 엔진·저장(2단계) (2026-11-05 작성)

- 결정: 1105-08 「승인」(계획 4판), 1105-09 「①가 · ②가」(1단계 로컬 커밋 · push 는 2단계 끝 · 1분봉 90일 그대로·배포 뒤 서버 메모리 재측정), 「㉠ ① , ㉡ ②」(강제 매수 결과 문장 그대로 · 옛 설정 알림에 「다시 저장」 문장), 「배포 요청서 진행」(11/05).
- 계획: `docs/plans/2026-11-05-ver2-backtester/plan.md` 4절(단일 배포)·8절 A~D.
- 서버 지금(11/05 21시 읽기 전용 점검): HEAD `eff249a` (v1.2026.11.03.2304), tradebot active `Wed 2026-11-04 10:42:16 KST`·NRestarts 0, tradebot-v2 active `Sun 2026-11-01 14:21:31 KST`·NRestarts 0·메모리 28MB(상한 150MB), 미추적 5건(check_all_balances.py · check_balance.py · check_pepe.py · mcmax33.sqlite3 · sync_balances.py — 새 커밋에 같은 이름 없음), 활성 전략 파일 3개 모두 EMA, 비밀 파일 4개 600 root·사본 0, 디스크 여유 16G, 서버 메모리 사용 가능 1,411MB(free -m available). 엔진 기동 뒤 `ERROR|CRITICAL|Traceback|database is locked` 매치 1줄 — 11/04 14:38:05 `WARNING [SETTINGS-SNAPSHOT] ❌ Failed: database is locked`(경고 1회, 그 뒤 0).
- 배포 대상: 커밋 C(이 요청서·HANDOFF 를 넣는 문서 커밋). `eff249a` 위에 push 끝 9개와 로컬 2개(84ba2e1 · b9e91ed)·C 가 fast-forward 로 쌓인다(`git log eff249a..b9e91ed` 11개).
  - 런타임: f4a370f(1단계 백테스터) · c0559e3(2단계 엔진·저장) · b9e91ed(옛 설정 알림 문장).
  - 시험·저장소 정리: 8329271(시험 기준 커밋) · 35f14e5(.gitignore 13줄 · 시험 파일 3개 추가 — 서버 미추적 5건과 겹치는 이름·패턴 없음).
  - 문서만: 8fe87bb · 9b0fc1e · 4dee9dc · db94743 · 287f62f · 84ba2e1.
- 버전: v1.2026.11.03.2304 → v1.2026.11.05.2039 (b9e91ed. 2단계 c0559e3 의 2010 을 ㉡ 반영 때 2039 로 다시 올림).
- 방식: 지난 배포 ②와 같은 서버 안 대기 스크립트 `/root/deploy-1106/{run.sh,helper.py,notify.py}` — deploy-1104 run.sh 에서 값·단계만 바꿈. helper.py·notify.py 는 그대로.

## 1. 바뀌는 것
| # | 무엇 | 실매매 영향 |
|---|---|---|
| 1 | 신버전 백테스터 Ver2 계산(10·15·30분봉, 업비트 90일, CSV 4칸) | 없음 — 화면 계산만(tradebot-v2) |
| 2 | 새 전략(눌림목 분할매수) 판정: 60선 기울기 · 상승폭 제한(골든 1차만) · 연속 손절 매수 중단 · 구간 익절 줄이기 · 데드크로스 기본 「아니오」(새 설정만) | 모의만. 지금 서버의 새 전략은 꺼져 있음(활성 전략 3개 모두 EMA) |
| 3 | 저장 표 pullback_state 에 6칸 추가(엔진 기동 때) | 표가 있는 사용자 DB 3개(default · gon1972 · mcmax33, 행 0). EMA 는 이 표를 읽지 않음 |
| 4 | 설정 화면 25칸·저장 검사, 홈 배지「연속 손절로 매수 중단 중」, 이번 거래 익절 %, 감사 사유 2개 | 신버전 화면만 |
| 5 | 옛 18칸 설정 파일 → 읽을 때 새 칸으로 옮김 + 운영자 알림 1건 | 서버에 옛 파일 1개(mcmax33 저장본). 적용본은 없음 → 엔진 기동 때 알림 없음. 알림은 전환(적용) 때 1회 |
| 6 | 대시보드 버전 문자열 | 표시만 |

EMA 경로: core/strategy_engine.py · engine/live_loop.py 에서 이름에 pullback 이 없는 함수는 AST 가 eff249a 와 같다. 모듈 import 1줄 · 기존 상수 `_PULLBACK_TRADE_KEYS` 에 키 3개 · 클래스 기본값 3개만 더함(verifier · Fable 확인, `docs/fable/2026-11-05-ver2-stage2-1.md`). 매매 판정·주문 무변경.

투자자 PDF(notice-log #10) 2절 표와 달라진 곳: 없음. 「강제 매수 — 화면과 기록에 매수 중단 중(몇 시까지)」은 홈 화면 배지와 엔진 기록으로 보인다(강제 매수 결과 문장에는 넣지 않음 — 사용자 결정 ㉠ ①). 안내문 끝 약속대로 배포 뒤 화면이 안내와 다를 때만 다시 알린다.

## 2. 실행 순서 (서버 스크립트)
0. 사용자 push 승인(6절 1) → Claude 가 84ba2e1 · b9e91ed · C push(push 전 자동 검사) → origin/main = C 확인 → run.sh 의 NEW 에 C 전체 해시를 넣는다.
1. 사용자 `!` 업로드·드라이런(6절 2 첫 명령). 결과의 정지선·대기 조건·`user_db_count`(4 = 기동 대상 3 + 이름 없는 tradebot_.db 1)·`pullback_params_files`(1) 를 Claude 가 읽고 본 띄우기를 권한다. 드라이런은 쓰기 0(git fetch·결과 로그·잠금 파일만) + 운영자 채널 DRY 알림 1건.
2. 사용자 `!` 본 띄우기.
3. 스크립트: 정지선(HEAD=eff249a, 미추적 5, tradebot 기동 11/04 10:42:16·NRestarts 0, v2 기동 11/01 14:21:31, 비밀 파일 600·사본 0, 전략 EMA, 11/05 21:00 뒤 journal 실패 표지·ERROR 0, origin/main = C) → 봉마다 보유 0·묶임 0·미체결 0·잔고 갱신 120초 안·새 audit BUY 없음·minute3·최근 5분 ERROR 0 → DB 백업(무결성 ok·600) → 다음 봉 재확인·경계까지 60초 이상 → `git merge --ff-only C` → `systemctl restart tradebot` → 기동 확인(`[BOOT-RESUME] success`·`[migrate] … 실패`·`[BOOT-RESUME] 마이그레이션 실패` 0) → `systemctl restart tradebot-v2` → 30초 뒤 active·ERROR 0 → 첫 봉 2개·check_v2_unit, 3점 일치·새 코드 표식·`[migrate] added pullback_state.*` 줄 수(기대 3 × 6 = 18)·DB 마다 칸 수(대상 3개 30, tradebot_.db 는 표가 없어 0 이 정상) 기록 → 「배포 완료」 알림 → 1시간 관찰(두 서비스 active, v2 메모리 최대값) → 「1시간 관찰 통과」 알림.
4. 되돌리기(승인 범위): 기동 확인 실패·v2 기동 실패·10분 봉 줄 0·Bar# 형식 변화·기동 뒤 ERROR·관찰 중 비활성/재시작 → `git checkout eff249a` + tradebot 재시작(+ v2 를 재시작했으면 v2 도) 1회 → 알림. 되돌린 뒤 서버는 detached HEAD — 다음 배포 전 `git checkout main`.
5. 마감: 재시작 명령 11/08 23:59 까지. 취소: `systemctl stop deploy-1106`.
6. 스크립트가 도는 동안 origin/main 에 push 하지 않는다.
7. 재시작 직후 5분 동안은 구버전·신버전 화면에 로그인하지 않는다(구버전 화면 로그인 경로(app.py:281 → init_db_if_needed → ensure_all_schemas)가 같은 표 칸 추가를 돌린다. 기동 마이그레이션과 겹치면 칸 중복 예외로 거짓 되돌리기가 날 수 있음 — init_db 칸 확인과 ALTER 사이 잠금 없음. 신버전(v2) 로그인은 마이그레이션을 부르지 않지만 규칙은 두 화면 모두 같게 둔다. 생겨도 DB 손실은 없음).
8. 「배포 완료」 알림 뒤 1시간 동안 화면에서 엔진 정지·시작·전환과 새 전략 설정 저장을 하지 않는다(관찰 중 되돌리면 옛 코드는 새 24칸 설정 파일을 읽지 못함 — EMA 실매매 영향 없음).
9. 마이그레이션 판정은 DB 마다 pullback_state 칸 수로 한다(대상 3개 30 · tradebot_.db 0). `[migrate] added` 18줄은 참고로만 적는다(줄 수가 0 이어도 칸 수가 30 이면 로그 전달 문제).
10. 정지선이 `database is locked` 1줄(11/04 과 같은 설정 기록 경고)로 끝나면 아무것도 바꾸지 않은 상태다. 그때는 T_BASE 를 그 시각 뒤로 옮겨 다시 띄울지 사용자에게 묻는다.

## 3. 위험과 막는 것
| # | 위험 | 막는 것 |
|---|---|---|
| 1 | 6칸 ALTER 가 어느 사용자 DB 에서 실패 | 그 사용자의 기동 마이그레이션이 예외로 멈추고 `[BOOT-RESUME] 마이그레이션 실패` 를 남김(다른 사용자는 계속) → 기동 확인이 이 줄을 보면 되돌림. EMA 사용자 DB(mcmax33)도 대상 |
| 2 | 되돌린 뒤 옛 코드 | 로컬 시험: 6칸이 붙은 DB 에서 eff249a 코드의 읽기·저장·청산 초기화 모두 됨, 무결성 ok. 옛 코드는 새 칸을 건드리지 않음 |
| 3 | 되돌림 → 옛 코드로 새 전략 거래 → 다시 배포 | 새 칸 6개(이번 거래 익절 % · 연속 손절 수 · 중단 시작·끝 · 구간 순번)가 남아, 다시 배포하면 그 거래 익절 %가 틀리거나 옛 매수 중단이 이어질 수 있음(모의 전용, 로컬 점검으로 값이 남는 것 확인). 다시 배포하기 전에 새 칸을 확인하고 필요하면 비운다(따로 승인) |
| 4 | 1분봉 90일 백테스트 메모리 | 로컬 최악 96.7MB < v2 상한 150MB. 1시간 관찰에서 v2 메모리 최대값을 기록하고, 배포 뒤 1분봉 90일을 한 번 돌려 다시 잰다 |
| 5 | 10·15·30분 확정 봉 재시도 호출 | 기존 공식 그대로(30분 봉 재시도 179회, 5초 간격, 약 15분). 지금 서버는 minute3 이라 이번 배포로 늘지 않음(스크립트도 minute3 이 아니면 배포하지 않음) |
| 5′ | 업비트 공용 IP 한도(백테스터 90일) | 1분봉 90일 백테스트 1회에 요청이 최대 약 648회로 30일의 3배. 초당 4회 상한 · 엔진 봉 경계 창 피함 · 429 를 받으면 600초 멈춤은 그대로(v2/candles.py). 사용자 요청 때만 늘어남 |
| 6 | 옛 설정 알림 | 받는 곳은 운영자 채팅(서버 .env: 기본 채팅 = 운영자 채팅, 등급별 채팅 키 없음). 투자자에게 가지 않음. 설정 화면에서 다시 저장하면 더 오지 않음 |
| 7 | 이름 없는 사용자 DB(tradebot_.db) | 지금도 pullback_state 표가 없음. 기동 사용자 목록은 이름이 비었거나 크기 0 인 DB 를 뺌(engine/boot_resume.py list_known_users — 확인). 이번 배포와 무관 |

## 4. 시험
- push 전 자동 검사(8329271): 회귀 1270/1270 · JS 181 · NETGUARD 0. b9e91ed 뒤 로컬: 회귀 1271 OK · tests/v2 450 OK. C push 때 자동 검사가 다시 돈다.
- 새 회귀 `tests/regressions/test_r_2026_11_05_ver2_stage2.py` 20건, 기준 비교 13조합 39파일.
- verifier 2단계 「고친 뒤 승인 권고」(지적 3 고침), Fable 2단계 「진행」. 이 요청서: verifier 1회째 「수정 후 승인」(지적 10 — 커밋 목록 등 반영) → 다시 검증 → Fable.
- 백테스팅: 1단계 비교(바이낸스 = 투자자 그림, 업비트 +39~45%). 엔진은 기준 비교 39건이 백테스터와 같음.

## 5. 배포 뒤
- 화면 확인(운영자, project-rules 1-A): 새 화면 버전 v1.2026.11.05.2039, 설정 화면 새 8칸·200선 기울기 2칸 없음, 봉 단위 7가지, 백테스터 업비트 90일. 구버전 화면 버전도 2039.
- 1분봉 90일 백테스트 1회 + v2 메모리 재측정(②가).
- 투자자 통보: 화면이 안내(#10)와 다를 때만.

## 6. 정해 주실 것
1. push 승인 — 84ba2e1(HANDOFF) · b9e91ed(옛 설정 알림 문장) · C(이 요청서·HANDOFF). push 뒤 배포가 끝날 때까지 다른 push 없음.
2. Ver2 배포 실행 승인(2절 범위: tradebot·tradebot-v2 재시작 각 1회 + 되돌리기 1회, 커밋 C 만, 11/08 23:59 까지). 승인은 push 뒤 Claude 가 드리는 업로드·드라이런 한 줄을 직접 실행하시는 것으로 갈음하고, 드라이런 결과를 본 뒤 본 띄우기 한 줄도 직접 실행하신다(배포 ②와 같음).
   - 업로드·드라이런: 서버에 `/root/deploy-1106`(700)을 만들고 run.sh·helper.py·notify.py 를 올려 600 으로 둔 뒤 sha256 앞 16자를 보이고, `systemd-run --unit=deploy-1106-dry --collect --wait -p User=root --setenv=HOME=/root /bin/bash /root/deploy-1106/run.sh --dry` 뒤 `dry-result.log` 를 읽는다.
   - 본 띄우기: `systemd-run --unit=deploy-1106 --collect -p User=root --setenv=HOME=/root /bin/bash /root/deploy-1106/run.sh` 뒤 `result.log` 를 읽는다.
   - 명령에 비밀 값은 없다.
