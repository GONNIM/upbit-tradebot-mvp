# v2 신버전 대시보드 운영 런북

**대상**: `tradebot-v2` 서비스(신버전 대시보드). 엔진(`tradebot`)과 별도 프로세스다.
**원칙**: 서버 설정 변경(유닛 설치, nginx, 비밀 파일 생성, cron)은 배포 승인 뒤에만 한다. 키 값·토큰·`.env` 내용은 어떤 명령으로도 화면·문서에 내지 않는다.

---

## 서비스 개요

| 항목 | 값 |
|---|---|
| 서비스 | `tradebot-v2` (유닛 원본 `deploy/tradebot-v2.service`) |
| 포트 | 8502 (127.0.0.1 만) |
| 공개 경로 | nginx `location /v2/` → `http://127.0.0.1:8502` (원본 `deploy/nginx-v2-location.conf`) |
| 엔진과의 관계 | 별도 프로세스. 실매매 DB 는 읽기 전용, 쓰기는 `v2hist_<user>.db` 와 `<user>_latest_params_PULLBACK.json` 뿐 |
| 자원 상한 | `MemoryMax=150M`, `MemorySwapMax=0`, `OOMScoreAdjust=500` (OOM 때 v2 가 먼저 죽는다) |
| 재시작 한도 | 300초 안에 5회까지(`StartLimitBurst=5`) — 넘으면 v2 만 멈추고 엔진은 영향 없음 |
| 이력 백업 | `deploy/v2hist-backup.cron` (매주 일 11:30, `services/data/backups/v2hist_<user>_YYYYMMDD.db`) |

## 설치

각 단계는 모두 서버 설정 변경이므로 **배포 승인 대상**이다(승인 없이 하지 않는다). 순서:

1. `git pull`.
2. 비밀·허용 파일을 **유닛 기동 전에** 만든다: `.v2_secret`(32바이트 이상, 600), `.v2_allowlist`(600), 0바이트 `mcmax33_latest_params_PULLBACK.json`(600). 값은 출력하지 않고 `ls -l`·`wc -c` 만 쓴다.
3. 유닛 설치: `deploy/tradebot-v2.service` 를 `/etc/systemd/system/tradebot-v2.service` 로 복사 → `systemctl daemon-reload` → `systemctl enable tradebot-v2` (`--now` 없이).
4. (별도 조건) `tradebot` 1회 재시작 — plan 배포 절 4 의 조건을 따른다.
5. `systemctl start tradebot-v2`.
6. `bash scripts/v2/check_v2_unit.sh` → `bash scripts/v2/a3_memory_probe.sh` (출력 읽는 법 절 참조).
7. nginx: `deploy/nginx-v2-location.conf` 의 블록을 `/etc/nginx/sites-enabled/tradebot` 443 블록 안 `location /` 앞에 넣기 → `nginx -t` → `systemctl reload nginx`.
8. cron: `crontab -e` 로 `deploy/v2hist-backup.cron` 의 실행 줄(주석 아닌 한 줄)을 추가.

PULLBACK 파일보다 v2 를 먼저 띄우면 `-` 접두 때문에 그 파일이 쓰기 허용에서 빠진다 — 그랬으면 `systemctl restart tradebot-v2`.

## 즉시 닫기

신버전 화면을 바로 닫아야 할 때. 실매매에는 영향 없다(엔진·실매매 DB 를 건드리지 않음).

```bash
systemctl disable --now tradebot-v2
# nginx: /etc/nginx/sites-enabled/tradebot 의 443 블록에서 `location /v2/ { ... }` 블록만 삭제
nginx -t
systemctl reload nginx
# cron: crontab -e 로 v2hist 백업 줄(v2hist_mcmax33 이 들어 있는 한 줄) 제거
```

확인: `systemctl is-active tradebot-v2` 가 `inactive`, `systemctl is-active tradebot` 는 `active` 그대로.

## 계정 추가

새 계정 `<user>` 에게 신버전을 열어 줄 때. 순서를 지킨다.

1. 빈 PULLBACK 파일을 만든다. **0바이트 빈 파일**로 만든다(`{}` 가 아님 — 빈 파일이면 확인 창이 「저장 기록 없음」을 보이고, `{}` 이면 생성 시각을 「마지막 저장」으로 오인한다).
   ```bash
   cd /root/upbit-tradebot-mvp
   umask 077; : > <user>_latest_params_PULLBACK.json
   ls -l <user>_latest_params_PULLBACK.json
   ```
2. `.v2_allowlist` 에 한 줄(`<user>`)을 더한다. 권한은 600 으로 유지한다.
3. `/etc/systemd/system/tradebot-v2.service` 의 `ReadWritePaths` 끝에 `-/root/upbit-tradebot-mvp/<user>_latest_params_PULLBACK.json` 을 더한다(원본 `deploy/tradebot-v2.service` 도 같이 고친다).
4. `systemctl daemon-reload` → `systemctl restart tradebot-v2`.
5. `bash scripts/v2/check_v2_unit.sh <user>` — FAIL 이 없어야 한다(`pullback-inode-mismatch` 면 `systemctl restart tradebot-v2`).

**주의**: `tradebot-v2` 가 켜져 있는 동안 PULLBACK 파일을 지우거나 새로 만들지 말 것(`rm` 뒤 생성, 새 inode 를 만드는 편집기 저장 포함). 비우려면 `: > 파일` 만 쓴다. 새로 만들었으면 `systemctl restart tradebot-v2` 가 필요하다. `ReadWritePaths` 의 파일 항목은 inode 에 bind mount 되므로 새 파일에는 쓰기가 닿지 않는다.

`-` 접두는 「없으면 무시」라서, 파일이 없는 채로 두면 저장 API 가 500 「배포 설정 누락」을 낸다.

## 비밀·권한 점검

`ls -l` 로 권한만 본다. 내용을 화면에 내는 명령은 쓰지 않는다.

```bash
cd /root/upbit-tradebot-mvp
ls -l .v2_secret .v2_allowlist
ls -l services/data/v2hist_*.db services/data/v2hist_*.db-journal
ls -l services/data/tradebot_*.db services/data/tradebot_*.db-wal services/data/tradebot_*.db-shm
ls -l *_latest_params_PULLBACK.json
ls -l services/data/backups/v2hist_*
wc -c .v2_secret
```

- 비밀·허용·PULLBACK·`v2hist_*.db`·백업은 `-rw-------`(600), 소유자 root 여야 한다.
- 실매매 DB 의 `-wal`·`-shm` 은 본 DB 와 같은 권한(644 또는 600), 소유자 root 면 정상이다(읽기 전용 연결이 만들 수 있고 엔진이 정리한다).
- v2hist 는 WAL 이 아니므로 `-wal`·`-shm` 이 없다. `-journal` 은 저장하는 동안만 잠깐 보인다.
- `.v2_secret` 은 32바이트 이상(`wc -c` 결과 확인; `utils/v2_entry_token.py` 의 `MIN_SECRET_BYTES`)이면 정상이다. 값은 보지 않는다.
- 비밀 파일을 바꿀 때 `.bak` 같은 사본을 남기지 않는다.

## 동결 파일 2개

`ui/v2_entry.py` 와 `utils/v2_entry_token.py` 는 동결 파일이다. 배포 diff 에 이 두 파일이 보이면 **멈추고 별도 승인**을 받는다. 이 파일들이 바뀌면 구버전 화면(Streamlit)을 담은 `tradebot` 재시작이 필요하다.

## 점검 스크립트 출력 읽는 법

서버에서 배포 승인 뒤에 실행한다. 둘 다 서비스를 재시작·중지하지 않는다.

- `bash scripts/v2/check_v2_unit.sh` — 유닛 보호 속성 점검(탐침 9항목 + 호스트 항목: 유닛 속성·UPBIT 환경 변수·PULLBACK inode).
- `bash scripts/v2/a3_memory_probe.sh` — 메모리 상한 격리 점검(300MB 할당 탐침이 임시 유닛에서만 OOM 으로 죽는지).

출력은 `PASS|FAIL|RESIDUAL <항목>` 줄뿐이다.

| 표기 | 뜻 |
|---|---|
| PASS | 기대대로 |
| FAIL | 기대와 다름 — 배포 중단하고 원인 확인. 종료 코드 1 |
| RESIDUAL | 막지 못하는 남는 위험(spec E18 위험 1: tradebot 프로세스의 환경 변수 파일 읽기 가능). 알려진 항목이면 수용 |

주요 항목:

- `unit-props` — 유닛의 보호 속성이 의도한 값으로 적용됨.
- `live-db-ro-read` — 실매매 DB 읽기 전용 조회. 이 연결이 `-wal`·`-shm` 을 만들 수 있다(본 DB 와 같은 권한, 소유자 root, 엔진이 정리).
- `v2hist-write` / `v2hist-write(folder)` — 이력 DB 쓰기 가능(행은 남지 않음). 파일이 아직 없으면(첫 저장 전) 폴더 쓰기만 본다.
- `env-inaccessible` — `.env` 열기 차단. `(placeholder)` 는 0바이트 자리표가 덧씌워진 경우.
- `root-readonly` — 저장소 루트에 새 파일을 만들 수 없음.
- `proc-environ-blocked` / `proc-environ-readable` — tradebot 환경 변수 파일 읽기 결과(후자는 RESIDUAL).
- `pullback-open` — PULLBACK 파일 열기 가능(쓰지 않음). `pullback-file-missing` 이면 계정 추가 1단계 누락.
- `secrets-inaccessible`·`credentials-inaccessible` — `.streamlit/secrets.toml`·`credentials.yaml` 열기 차단(`.env` 와 같은 규칙).
- `pullback-inode-match` / `pullback-inode-mismatch` — 실행 중 v2 가 보는 PULLBACK 파일이 호스트 파일과 같은 inode 인가. mismatch 면 `systemctl restart tradebot-v2`.
- `no-upbit-env` — v2 프로세스 환경 변수에 `UPBIT_` 로 시작하는 이름이 0개(이름만 센다).
- `probe-run-failed` — 임시 유닛 실행 실패. **배포 때 첫 실행에서 이게 나오면 `ReadWritePaths` 의 `-` 접두 처리부터 본다**(`systemctl show -p ReadWritePaths --value` 가 접두를 유지하는지는 로컬에서 확인하지 못했다).
- `probe-line-count=<n>` — 탐침 출력 줄 수가 9가 아님(탐침이 못 돌았거나 중간에 죽음).
- a3: `probe-oom-killed`(문자열 `oom-kill` 또는 `killed by the OOM killer` 로 판정), `swap-unchanged(+Nmb)`(스왑 증가 5MB 이내), `tradebot-not-restarted`.
- a3 의 `probe-not-oom`·`swap-grew` 가 나오면 한 번 다시 실행해 보고, 두 번 다 FAIL 이면 멈추고 보고한다.

## 로그 출처

관찰 판정의 로그 출처는 `journalctl -u tradebot-v2` 이다(엔진은 `journalctl -u tradebot`). `mcmax33_engine_debug.log` 는 보조 출처다.

```bash
journalctl -u tradebot-v2 --no-pager -n 100
```

## 알려진 틈

- Task 8 이월: 저장 6단계와 7단계 사이에 프로세스가 종료되면 파일과 이력이 어긋날 수 있다. 저장된 PULLBACK 파일이 로더(P3)에 깨진 JSON 으로 읽히는 경우의 처리는 별도 확인이 필요하다.
- v2 는 root 로 돌기 때문에 권한 비트로 `/etc/shadow`·`/root/.ssh` 를 읽을 수 있다. `InaccessiblePaths` 추가는 다음 판에서 검토한다.
- 서버 SQLite 3.37.2 에서 `-wal`·`-shm` 이 없는 WAL DB 를 ro 로 열 때의 동작은 배포 첫 실행의 `live-db-ro-read` 결과와 `-wal` 유무로 기록한다.
- 후보(미적용): 유닛에 `ProtectProc=invisible` 을 더하면 다른 프로세스의 `/proc` 을 가릴 수 있어 RESIDUAL `proc-environ-readable` 을 줄일 수 있다. plan 고정값 밖이라 넣지 않았다.
- 탐침 파일 잔존 가능: 점검 중 프로세스가 중간에 죽으면 `.v2probe_*`(0바이트)가 `services/data/` 에 남을 수 있다. 무해하며 지워도 된다.
