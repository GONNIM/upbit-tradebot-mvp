# .env.bak 삭제 + 세션 마감 기록 (2026-10-04)

- 범위: 서버 `.env.bak` 1개 삭제, 문서 기록(운영 문서·백로그·점검 목록).
- 엔진 코드·설정·포지션·주문 무변경. 재시작 없음. 투자자 안내 없음. 키 값 미출력.
- 근거: 운영자 판단 — 옛 텔레그램 값 2개는 보존할 이유가 없다. 업비트 키는 `.env` 와 같았다 (`secret-report.md` 1절).

## 1. .env.bak 삭제 (`evidence/secret-close-rm.txt`)

| 시점 | 결과 |
|---|---|
| 삭제 전 | `-rw------- 1 root root 367 May 31 14:24 .env` / `-rw------- 1 root root 355 May 31 14:23 .env.bak` |
| 실행 | `test -f /root/upbit-tradebot-mvp/.env.bak && rm /root/upbit-tradebot-mvp/.env.bak` (경로 확인 뒤 그 파일 하나만) |
| 삭제 후 | `-rw------- 1 root root 367 May 31 14:24 .env` (무변경) / `ls: cannot access '.env.bak': No such file or directory` → **부재 확인** |
| 서비스 | `systemctl is-active tradebot` = **active**, `Active: active (running) since Sun 2026-10-04 10:22:33 KST; 1h 42min ago`, `ExecMainStartTimestamp` 10:22:33 그대로, MainPID 2313925 → 재시작 없음, 실행 중 프로세스 영향 없음 |

## 2. 기록 (`secret-close-docs.diff`)

| 문서 | 변경 |
|---|---|
| `docs/operations/server-optimization.md` | "비밀 파일 권한 점검 2026-10-04" 표에 한 줄: **".env.bak 삭제 완료(옛 텔레그램 값 2개 폐기, 업비트 키는 .env 와 동일했음)"**, `.env` 무변경·서비스 active 유지 |
| `docs/plans/backlog.md` | WO-17 (S2) `27d83f2` 완결 표기, WO-19·WO-20·1분봉 전환 점검·비밀 파일 점검 완결 행 추가. "보류 항목" 표 신설: 거래 없는 봉 확정 기록 중복(낮은 순위), trailing 무장 상태 재시작 지속(WO-21 후보), executed_at 과거 보정(운영자 결정), 보유 구간 WARMUP BUY 자리표시자(표시), 교차 폭 하한(투자자 요청 시), C안 |
| `docs/operations/wo8-force-buy-verification-guide.md` | "세션 개시 정기 점검 조회 명령" 머리에 점검 목록 한 줄: 사후 확인 1~9, 1분봉 거래 없는 봉 비율과 매매 건수, 비밀 파일 권한(.env·secrets.toml 600, 백업 파일 없음) |

문서 커밋 1건, 버전 변경 없음, 서버 pull 없음 (`secret-close-commands.txt`).

## 3. 묶음

- `report.md` (이 문서)
- `evidence/secret-close-rm.txt` (ls 전·후, systemctl status 발췌)
- `docs.diff`, `commands.txt`, `git-log.txt`
