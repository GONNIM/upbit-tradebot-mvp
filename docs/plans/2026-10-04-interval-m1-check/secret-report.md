# 서버 비밀 파일 정리 보고 (2026-10-04)

- 범위: `.env.bak` 처리, 다른 백업 파일 목록(읽기 전용), 문서 기록.
- 엔진 코드·설정·포지션·주문 무변경. 재시작 없음. 투자자 안내 없음.
- **키 값은 어떤 출력에도 적지 않았다.** 비교는 키 이름과 "같음/다름" 만.
- 서버에서 바꾼 것은 `chmod 600 /root/upbit-tradebot-mvp/.env.bak` 1건뿐이다.

## 1. .env.bak 처리 (`evidence/secret-env-compare.txt`, `evidence/secret-chmod.txt`)

### 키 비교 (값은 같음/다름만)

| 키 이름 | .env | .env.bak | 값 |
|---|---|---|---|
| CANDLE_CACHE_TTL | 있음 | 있음 | 같음 |
| REDIS_DB | 있음 | 있음 | 같음 |
| REDIS_ENABLED | 있음 | 있음 | 같음 |
| REDIS_HOST | 있음 | 있음 | 같음 |
| REDIS_PASSWORD | 있음 | 있음 | 같음 |
| REDIS_PORT | 있음 | 있음 | 같음 |
| **TELEGRAM_BOT_TOKEN** | 있음 | 있음 | **다름** |
| **TELEGRAM_CHAT_ID** | 있음 | 있음 | **다름** |
| UPBIT_ACCESS | 있음 | 있음 | 같음 |
| UPBIT_SECRET | 있음 | 있음 | 같음 |
| WEBSOCKET_ENABLED | 있음 | 있음 | 같음 |

키는 두 파일 모두 11개이고 이름과 순서가 같다. 값이 다른 키는 `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` 2개다.

### 조치

지시에 따라 **삭제하지 않고 `chmod 600` 만 했다.** `.env.bak` 의 텔레그램 값 2개는 지금 운영 값(`.env`)과 다르다(예전 봇·채팅방으로 보이나 확인하지 않음). 삭제 여부는 운영자가 정한다.

```
-- 전
-rw------- 1 root root 367 May 31 14:24 .env
-rw-r--r-- 1 root root 355 May 31 14:23 .env.bak
-- chmod 600 .env.bak 실행
-- 후
-rw------- 1 root root 367 May 31 14:24 .env
-rw------- 1 root root 355 May 31 14:23 .env.bak
```

## 2. 다른 백업 파일 점검 (읽기 전용, `evidence/secret-backup-scan.txt`)

- 훑은 디렉터리 17개: `/root`, `/root/upbit-tradebot-mvp`, 그 하위 1단계 디렉터리 15개(`.claude`·`core`·`docs`·`engine`·`.git`·`.githooks`·`pages`·`__pycache__`·`scripts`·`services`·`.streamlit`·`tests`·`ui`·`utils`·`venv`).
- 방법: 각 디렉터리의 `ls -la` 출력에서 이름이 `.bak`·`.old`·`.orig`·`~` 로 끝나는 줄을 awk 문자열 비교로 골랐다. 와일드카드 검색은 쓰지 않았다.

| 디렉터리 | 이름 | 권한 | 크기 | 수정 시각 |
|---|---|---|---|---|
| /root/upbit-tradebot-mvp | .env.bak | -rw------- (1단계 처리 뒤) | 355 | May 31 14:23 |

해당 항목은 `.env.bak` 1개뿐이다.

비밀 값 가능성 후보(이름에 env·secret·key·token·cred·pass 포함), 내용은 열지 않고 `grep -c` 만:

| 파일 | KEY 포함 줄 | TOKEN 포함 줄 |
|---|---|---|
| /root/upbit-tradebot-mvp/.env.bak | 0 | 1 |

참고: "KEY" 가 0 인 것은 업비트 키 이름이 `UPBIT_ACCESS`·`UPBIT_SECRET` 이라 "KEY" 문자열이 없기 때문이다. 키 값이 없다는 뜻이 아니다(1단계 비교에서 두 값이 들어 있음을 확인).

## 3. 기록

- `docs/operations/server-optimization.md`: "🔒 비밀 파일 권한 점검 2026-10-04" 절 추가 (.env 600, secrets.toml 600, enableStaticServing=False, 7일 스캐너 7건 전부 거부, .env.bak chmod 600·삭제 보류, 정기 점검 명령), 변경 이력 1.1.
- `.claude/context/project-rules.md`: v2.13 → **v2.14**. "🔐 서버 비밀 파일 권한 규칙" 절 추가 — "서버의 비밀 값이 든 파일은 600 이어야 하고, 백업 파일은 만들지 않는다. 정기 점검에 권한 확인을 포함한다." 와 적용 기준.
- 문서 커밋 1건, 버전 변경 없음, 서버 pull 없음 (`secret-commands.txt`).

## 4. 묶음

- `report.md` (이 문서)
- `evidence/secret-env-compare.txt` (키 이름·같음/다름), `evidence/secret-chmod.txt` (ls 전후), `evidence/secret-backup-scan.txt` (백업 파일 목록)
- `evidence/sec_cmp.py`, `evidence/sec_bak.sh`
- `docs.diff` (문서 diff), `commands.txt`, `git-log.txt`
