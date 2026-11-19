# Fable 질의 — 업비트 키 만료 · 엔진 1회 재시작 (2026-11-19 12시대)

## 하려는 일
투자자 업비트 API 키가 만료되어 실계좌 손절 매도가 거절되고 있다. 운영자(사용자)가 별도 터미널에서 서버 키 파일 2개의 값만 새 키로 바꾸고, 읽기 전용 확인 스크립트로 새 키가 잔고·미체결 조회에 통과하면, 엔진 서비스 `tradebot` 만 1회 재시작한다(키는 import 때 한 번만 읽음). `tradebot-v2` 는 키를 쓰지 않아 건드리지 않는다. 코드 변경·커밋·배포 없음.

## 지금까지 확인한 사실
| # | 사실 | 확인/추정 | 근거 |
|---|---|---|---|
| 1 | 엔진은 `st.secrets["UPBIT_ACCESS"]` 를 먼저, KeyError 면 `.env` 를 읽는다. import 때 1회 | 확인 | config.py:9-18, core/trader.py:107,258 |
| 2 | 서버 `.streamlit/secrets.toml`(600, 2025-11-19 수정)과 `.env`(600, 2026-11-01)에 둘 다 UPBIT_ACCESS/SECRET 있음. systemd 는 EnvironmentFile=.env | 확인 | 11/19 12:45 서버 읽기 점검 |
| 3 | secrets.toml 날짜가 정확히 1년 전 → 업비트 키 1년 만료와 맞음. 엔진이 secrets.toml 키를 쓰는 중으로 봄 | 추정 | 파일 날짜 |
| 4 | 첫 거절 11/19 07:51:11, 24시간 `expired_access_key` 41줄. KRW-JTO SL 매도 qty 6468.1966759 price 342 거절, SELL_REJECTED 감사 기록·CRITICAL 알림 발송 | 확인 | journal |
| 5 | 12:18 뒤 매도 시도 줄 없음, 종가 345~346 회복. 최근 10분 ERROR·CRITICAL 18줄(내용 미확인 — 키 오류로 추정) | 확인/추정 | journal |
| 6 | 서버 HEAD 9f70dac, tradebot 기동 11/10 19:15:21 NRestarts 0, tradebot-v2 11/17 15:15:02 | 확인 | 점검 |
| 7 | 재시작 시 boot_resume 이 LIVE 엔진 자동 재개, 진입가는 봇 주문 기록 → 지갑 평단 → 실패 시 CRITICAL·그 종목 건너뜀. 재시작~첫 봉 1~3분 손절 공백 | 확인 | engine/boot_resume.py, deploy-request-20261106-1104-02-1106-03.md:45-49 |
| 8 | 운영 규칙 「눌림목 보유 중 재시작 안 함」(1109-01 위험 줄이기용). 지금 PULLBACK 실계좌 JTO 보유 중 | 확인 | deploy-request-20261110-1109-01-1110-01.md:46 |
| 9 | 재시작 안 하면 키 만료 상태가 계속되어 손절·모든 주문 불가 | 확인 | 1 |

## 다음에 하려는 일 (이번 질의 범위)
1. 사용자: 별도 터미널 `ssh` → `nano` 로 `.streamlit/secrets.toml` 과 `.env` 의 UPBIT_ACCESS/UPBIT_SECRET 값만 교체(사본 금지, 600 유지).
2. 사용자 `!` 실행: scratchpad `key1_verify.py`(두 파일 각각 GET /v1/accounts·/v1/orders/open, 키 값 미출력, 두 파일 같음 여부만).
3. 두 파일 모두 정상 + 미체결 0(또는 봇과 무관한 것만) 이면 사용자 `!` 실행: scratchpad `key2_restart.sh` — 사본 파일 있으면 멈춤, 확정 봉 처리 줄 25초 안 확인 뒤 `systemctl restart tradebot`, 첫 확정 봉까지 기다려 기동·복구·매도·키 오류·ERROR 줄 출력.
4. 재시작 뒤 SL 조건이 여전하면 엔진이 매도한다. 매도 결과·보유를 확인해 보고.

## 묻는 것
- 이 순서로 재시작해도 되는가(보유 중 재시작 규칙의 예외로). 빠진 위험·멈춤 조건이 있는가.
- 스크립트: /private/tmp/claude-501/-Users-gonnim-Project-MVP-Source-upbit-tradebot-mvp/52978ef7-adfa-4b7e-a131-0468fb080b32/scratchpad/key1_verify.py, key2_restart.sh

## 답

**판정:** 수정 후 진행 (Fable)

막음 3건:
1. 재시작 전에 새 키 권한을 사용자에게 확인받는다 — 자산조회·주문조회·주문하기 켜짐, 출금하기 꺼짐, 허용 IP 에 서버 IP. key1 은 조회만 하므로 주문 권한 없는 키도 「정상」으로 나온다(재시작 뒤 `out_of_scope` 거절 → 보유 중 재시작 2회 위험).
2. key2 재시작 뒤 출력에 판정 추가 — `PULLBACK-`(RESTORE·PARAMS·WARMUP)·`기동 거부` 검색, `[BOOT-RESUME] success user=mcmax33` 유무, 300초 안 확정 봉 0이면 경고, `[PULLBACK-RESTORE] 결과` 줄. `[BOOT-RESUME] success` 는 스레드 시작만 뜻한다.
3. 「재개됨」 기준 — BOOT-RESUME success + PULLBACK-RESTORE restored=True + 확정 봉 1개 이상 + 키 오류 0. 복원 평단은 key1 지갑 평단과 대조. 어긋나면 다시 재시작하지 않고 멈춰 보고.

권고 7건: key1 종료 코드·「판정: 재시작 가능/불가」 줄 · venv 파이썬 실행 · 사본 검사에 `.save` 추가 · 봉 간격 확인 후 대기 시간 맞춤 · 최근 ERROR·CRITICAL 18줄 내용 확인 · 확정 봉 검색어 `CONFIRMED\] .*봉 처리 완료` 로 넓힘 · 끝난 뒤 투자자 기록·키 만료일(2027-11-19 무렵) 사전 점검을 남은 일로.

사용자에게 물을 것: 새 키 권한·IP(막음 1, 답 전 key2 실행 금지) · 「눌림목 보유 중 재시작 안 함」 예외 1회 승인(1~3분 손절 공백, 첫 봉에서 손절 조건이면 약 6,468개 시장가 매도) · 앱에서 직접 팔았으면 바로 알려 줄 것.

다루지 못한 것(Fable): 봉 간격 서버 확인, 키 만료 동안 pullback_state 변화, ERROR 18줄 내용, engine_status·last_mode 현재 값, 키 유효 기간 1년 공식 문서.

---

## 다시 묻기 (2회째 · 실행 직전 · 11/19 13시대)

방안을 바꿨다(사용자 「㉠ 적용 · 권한 확인함」 — 새 키 권한: 자산조회·주문조회·주문하기 켜짐, 출금 꺼짐, 서버 IP 허용 확인함 · 보유 중 재시작 예외 1회 승인 포함): 사용자가 맥 ~/.upbit-newkey(600)에 새 키를 넣고 `! bash key_auto.sh` 한 줄 실행 → 키는 ssh 표준 입력으로만 서버 key_srv.py 에 전달.

막음 반영: 1) 권한·IP·재시작 예외는 사용자 답으로 받음(위). 2) 재시작 뒤 BOOT-RESUME·PULLBACK-(RESTORE|PARAMS|WARMUP)·기동 거부·확정 봉·키 오류·ERROR 줄 출력, 첫 확정 봉 없으면 경고. 3) 재개됨 = `success user=mcmax33` + `restored=True reason=restored`(strategy_engine.py:2023-2024 실제 문구) + 확정 봉 ≥1 + 키 오류 0 + 기동 거부 0, 아니면 종료 17·다시 재시작 안 함. 평단은 출력해 사람이 대조.

verifier(수정 후 승인) 지적 반영: 판정 문구 고침 · 두 파일 이미 새 키면 재시작 안 함(19, --restart-only 로만 재시작) · 옛 프로세스 로그 표식 줄 제외 · 사본·JTO 미체결 검사를 교체 앞으로(14·15 무변경) · 두 번째 조회·잠금 try · strptime · .env 정규식 [ \t]*$ · SIGHUP 무시·출력 /root/.key_srv_1119.log(600, 키 없음) 병행 · 맥 키 파일은 0·17·19 에서만 삭제.

스크립트: scratchpad key_auto.sh · key_srv.py (bash -n·py_compile·교체 시험 통과). 맥 키 파일 모양 검사 통과(40자·40자).

묻는 것: 지금 실행해도 되는가.

## 답 (2회째)

**판정:** 진행 (Fable, 2회째)

권고 8건(막음 없음): 1 서버 사본 파일 유무(12:45 점검 — .env·secrets 관련 사본 없음 확인) · 2 서버 시간대 KST(점검의 KST 표기로 확인) · 3 끊김·255 면 다시 실행 말고 /root/.key_srv_1119.log 읽기 · 4 종료 16 이면 --restart-only 1회, 또 16 이면 사용자에게 묻기 · 5 JTO 가용 약 6,468개 확인 · 6 끝난 뒤 지갑·매도 줄 다시 확인 · 7 restart 반환 코드·ActiveState 확인 · 8 맥 키 파일 삭제 확인.

다루지 못한 것: 서버 PyJWT 판, ! 실행 시간 제한, 만료 동안 pullback_state 변화, ERROR 18줄 내용, 주문하기 권한(주문 전에는 시험 불가).
