# 서버 점검 조치 — 2026-11-08 (1108-01 · 1108-02)

사용자 지시(11/08): 「권하는 조치 실행하기. 앞으로 문제가 될 점 패치하기.」
앞선 점검: 11/07 00:21~00:40 읽기 전용 점검 5회, 11/08 11:43 준비 점검 2회(이 문서 「점검 값」).

## 1. 무엇을 바꾸는가

| # | 바꾸는 것 | 서버 위치 | 저장소 원본 | 엔진 영향 |
|---|---|---|---|---|
| 1 | 기존 화면을 서버 안(127.0.0.1)에서만 받기 | /etc/systemd/system/tradebot.service.d/bind-local.conf | deploy/server-hardening/tradebot-bind-local.conf | 바깥 8501 은 A단계 방화벽에서 바로 막힘. 서버 안 묶기는 재부팅 때 적용 |
| 1 | nginx 가 127.0.0.1:8501 로 부르기 · 판 번호 숨김 | /etc/nginx/sites-available/tradebot · nginx.conf | (sed 두 줄, harden-a 5단계) | 없음 |
| 2 | 방화벽: 22 · 80 · 443 만 엶 | ufw | — | 없음 |
| 3 | SSH 비밀번호 로그인 · 화면 전달 끔 (키 로그인 유지) | /etc/ssh/sshd_config.d/10-hardening.conf | deploy/server-hardening/sshd-10-hardening.conf | 없음 |
| 3 | fail2ban: 5번 실패 1시간 → 1일 차단, 재범 1주 | /etc/fail2ban/jail.local | deploy/server-hardening/fail2ban-jail.local | 없음 |
| 4 | 배포 DB 백업: 사용자 DB 마다 새 2개만 | /root/prune_deploy_backups.sh (주간 정리가 부름) | scripts/server/prune_deploy_backups.sh | 없음 |
| 5 | 옛 커널 3벌 지움 · 대기 중인 갱신 전체(보안 + 일반 갱신 259개) · 재부팅 1번 | apt | — | 재부팅 1번(자동 재개) |
| 5 | 자동 보안 갱신 켜기(자동 재부팅 없음) | /etc/apt/apt.conf.d/20auto-upgrades · 52unattended-local | deploy/server-hardening/apt-* | 없음 |
| 6 | 정체 감시가 「[CLOCK-CLOSE] 봉 확정 감지」 줄도 봄 | /root/watchdog_tradebot_engine.sh | scripts/server/watchdog_tradebot_engine.sh | 없음 |
| 7 | 보유 기록 표(position_history) 30일만 남김(2,000줄 묶음) | /root/prune_position_history.sh (주간 정리가 부름) | scripts/server/prune_position_history.sh | 없음 |
| 8 | 주간 백업을 빈 칸 뺀 사본(VACUUM INTO)으로 | /root/cleanup_tradebot_db.sh | scripts/server/cleanup_tradebot_db.sh | 없음 |
| 9 | tradebot 줄을 /var/log/syslog 에 겹쳐 쓰지 않음 | /etc/rsyslog.d/30-tradebot.conf | deploy/server-hardening/rsyslog-30-tradebot.conf | 없음 |

- 알림 글(텔레그램)은 바꾸지 않는다. 화면도 바뀌지 않는다(버전 줄만 v1.2026.11.06.2050 → v1.2026.11.08.1151). 투자자 체감 변경이 아니라 통보하지 않는다.
- 보유 기록 표는 엔진이 쓰기만 하고 어디에서도 읽지 않는다(services/db.py insert_position_history · core/trader.py). 지우기 전 사본은 11/08 11:00 주간 백업(전체 줄 포함)에 있다.
- 남는 위험: 정체 감시는 이제 「루프는 도는데 평가가 매 봉 실패하는」 경우를 STALE 로 잡지 못한다(엔진 ERROR 줄은 journal 에 남는다). 새 커널(5.15.0-202)로 처음 부팅하다 실패하면 저절로 옛 커널로 돌아가지 않는다 — 그때는 cafe24 콘솔에서 옛 커널(5.15.0-143)을 고른다.
- 바꾸지 않은 것: audit_settings(하루 약 2,100줄 · 1.2MB, 감사 화면이 읽음), journal 보관 기간(약 20일), 저장소 폴더의 0바이트 DB 5개 · 미추적 파일 5개(운영자 파일).

## 2. 실행 순서와 되돌리기

1. harden-a.sh — 저장소 받기 · 스크립트 설치 · 옛 백업 정리(배포 백업 4개 + 4월 백업 1개 144MB) · 보유 기록 표 첫 정리(묶음, 한 묶음 1초 넘으면 멈춤 — 결과는 4절) · SSH·방화벽(15분 뒤 자동 되돌림) · nginx · fail2ban(운영자 주소는 서버 파일에만 제외로 넣음) · syslog. 엔진 재시작 없음.
2. harden-confirm.sh — 맥에서 새 연결로 실행. 연결이 되면 그것이 확인이고, 자동 되돌림을 푼다.
3. harden-c.sh — 옛 커널 지움 · 보안 갱신 · 자동 갱신 켬 · 8501 설정 · 재부팅 직전 확인(미체결 0 · 예약 0 · 백테스터 받기 없음 · 3분 봉 안 20~100초) · 재부팅.
4. harden-verify.sh — 엔진 재개 판정 · 포트 · 보안 설정 · 비밀 파일 600 · 막힌 8501 시도 확인. 1시간 뒤 한 번 더 본다.

harden-c 는 SSH 연결과 떨어진 작업(systemd-run)으로 돌린다. 재부팅 바로 앞에 미체결 · 예약 · 실계좌 엔진 켜짐 · 엔진 오류 · 백테스터 받기(8초 8번) · 봉 창을 다시 본다. 재부팅 전 DB 사본은 11/08 11:00 주간 백업이다.

되돌리기: 설정 사본은 /root/backup/config-20261108/. 각 설정 파일 머리에 되돌리는 명령을 적었다. 지운 백업 5개(약 4.5GB)와 보유 기록 줄은 되돌릴 수 없다. 지운 보유 기록 줄은 11/08 11:00 주간 백업에만 남고, 그 백업은 「7일 넘은 파일 지움」 규칙을 따른다. 11/15(일) 11:00 정리 때는 꼭 7일이라 남을 가능성이 크고, 늦어도 11/22(일) 정리 때 지워진다(추정 — 11/15 정리 뒤 백업 폴더에 11/08 파일이 남았는지 보면 확인된다).

## 3. 점검 값 (11/08 11:43 KST)

- 8501 바깥 연결 0개, nginx 접속 기록 36,563줄 — 사용자는 443 으로 들어온다. 저장소 문서에 「:8501」 바깥 주소 안내 없음.
- SSH 키 1개(authorized_keys), 다른 사용자 계정 없음. fail2ban sshd: maxretry 20 · findtime 600 · bantime 1800, 현재 기록 차단 2번, 24시간 시도 주소 28개.
- 실계좌 보유 있음. 미체결 · 예약은 재부팅 바로 앞에 다시 본다.
- 배포 백업 지울 것 4개 4,321,869,824 바이트(11/01 · 11/03 두 개 · 11/04). 남김: 11/06 00:36 · 11/06 21:35.
- 보유 기록 표: 15,430,832번까지, 지울 줄 10,438,611(10/09 이전).
- 갱신 대기 259개(모의). 엔진 파이썬은 /usr/local/bin/python3.12(apt 밖)라 갱신이 엔진 파이썬을 바꾸지 않는다.

## 4. 결과 (11/08 실행)

- 커밋 6a23bd2 push(게이트 3번째 1318/1318 통과 — 앞 2번은 t11 시험 하나의 간헐 실패, Fable 「진행」 뒤 다시 돌림, --no-verify 안 씀).
- A단계 12:24:43~12:28:08. 엔진 재시작 없음(기동 11/06 21:37:41 · NRestarts 0 그대로).
  - 배포 백업 4개 4,321,869,824 바이트 + 4월 백업 지움 → 디스크 21G → 16G(61% → 49%).
  - 보유 기록 표: 5,000줄 묶음 546번(2,730,000줄) 뒤 한 묶음이 4,367ms 걸려 스스로 멈춤. 12:28:47~12:49:02 2,000줄 묶음 3,855번으로 나머지 7,708,611줄 지움(가장 긴 묶음 108ms). 두 번 모두 엔진 ERROR·잠김 줄 0. 남은 줄 4,999,466(10/09부터).
  - 「Running timer as unit: harden-rollback.timer」 출력 확인. 운영자 주소 제외 개수=2.
  - sshd: permitrootlogin without-password · passwordauthentication no · x11forwarding no. 새 연결(harden-confirm 12:28:19)로 되돌림 예약 풂.
  - ufw 에 예전부터 있던 「8501 ALLOW」 규칙(v4·v6)이 남아 있어 12:28:47 지움. 맥에서 http://…:8501 → 응답 없음, https → 200.
  - nginx: proxy_pass 127.0.0.1:8501, 머리글 `Server: nginx`. fail2ban: sshd 5회·1시간·1일, recidive 3회·1일·1주.
- C단계 12:49:35~12:57:35(systemd-run). 옛 커널 9꾸러미 지움(/boot 140M → 348M 남음), 갱신 apt 결과 0 · 남은 갱신 0, 새 커널 5.15.0-203. 재부팅 직전 미체결 0 · 예약 0 · 오류 0 · 백테스터 받기 없음 · 봉 안 35초.
- 재부팅 12:57:35 → 12:58:07 두 서비스 기동, 12:58:21 「[BOOT-RESUME] success user=mcmax33 mode=LIVE elapsed=12.5s」. 보유 5종 그대로. 13:00:00 첫 봉 확정 줄, 엔진 오류 0.
- 재부팅 뒤: 8501 은 127.0.0.1 에서만 받음, streamlit health ok, 비밀 파일 3개 600 · 사본 0, /boot 250M 남음, / 50%, 자동 보안 갱신 켜짐, syslog 에 python 줄 없음.
- 보충: 주간 정리의 보유 기록 묶음을 2,000줄로 낮춤(첫 정리 실측).
- 1시간 관찰(13:58:18, 재부팅 뒤 1시간): tradebot · tradebot-v2 · nginx · fail2ban · ufw 모두 active, NRestarts 0. 봉 확정 줄 20(3분 봉 1시간 = 20), 엔진 ERROR·CRITICAL·Traceback 0, 429 0, 잠김 0, v2 오류 0, 재부팅 뒤 정체 경보 0. 메모리 177MB / 1400MB. engine_status mcmax33 is_running=1 LIVE. nginx 오류 0, https 200. fail2ban 지금 차단 7개, 1시간 SSH 실패 줄 2. 막힌 8501 시도 1번. syslog 15,968,707 바이트, / 50%. 판정: 통과.
