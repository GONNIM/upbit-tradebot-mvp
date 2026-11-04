# 배포 ② 완료 보고 — 1029-12 모의 지갑 덮어쓰기 막기 + 자리표시자 로그 문구 (2026-11-04)

- 요청서: `deploy-request-20261104-bundle2.md` (승인: 11/03 「배포 ② push 승인」 → eff249a push, 11/04 00시대 사용자 업로드·드라이런, 11/04 10:38 본 띄우기 — 모두 사용자 실행)
- 결과 원문: 서버 `/root/deploy-1104/result.log` (11/04 사용자 `!` 읽기, 아래 2절에 옮김)
- **버전: v1.2026.11.03.1532 → v1.2026.11.03.2304**

## 1. 결과

| 항목 | 값 | 판정 |
|---|---|---|
| 3점 일치 | 서버 HEAD eff249a · 서버 dashboard v1.2026.11.03.2304 · tradebot 기동 Wed 2026-11-04 10:42:16 KST (로컬 HEAD eff249a · 로컬 dashboard 2304) | 일치 |
| 기동 확인 | BOOT OK warmup=1 boot_resume_live=1 fail_lines=0 error=0 active nrestarts=0 | 통과 |
| 첫 봉 | Bar#201(10:42 봉)·Bar#202(10:45 봉) HOLD, pos=False | 통과 |
| check_v2_unit | rc=0 pass=19 fail=0 | 통과 |
| 새 코드 표식 | keeps_wallet=1 · wallet_kept=3 · placeholder_log=4 · 엔진 스레드 1 · 엔진 시작 표지 2 | 새 코드로 돎 |
| 1시간 관찰 (10:42~11:42) | fail_markers=0 error=0 engine_exit=0 http429_418=0 bars_unique=19 auto_resume=0 v2_err=0 v2_429=0 | 통과 |
| 배포 전 DB 백업 | /root/backup/tradebot_mcmax33_20261104_1039.db · 무결성 ok · 600 | 통과 |
| 되돌리기 | 없음 | — |

보유 0 상태에서 배포했다(10:38~10:42 보유·묶임·미체결 0, 마지막 매수 id 1490 그대로 — 드라이런 때 1487 이었고 그 사이 밤에 사고판 3건은 배포 전에 끝남). 매매 판정·주문 경로는 바뀌지 않았다.

### R7 (같은 프로세스의 다른 실계좌 사용자)

- 서버 사용자 DB 는 4개(드라이런 user_db_count=4).
- 재시작 뒤 journal 의 1분 동기화 명단 등록은 `[OR] LIVE user registered for balance monitoring: mcmax33` 한 줄뿐(10:42:24). 다른 사용자는 실계좌 엔진으로 등록되지 않았다.
- 그래서 지금은 R7 이 생길 조건(다른 실계좌 사용자가 같은 프로세스에서 엔진을 돌림)이 없다. 다른 사용자가 나중에 실계좌 엔진을 켜면 조건이 다시 생긴다. 이 경우에도 영향은 모의 지갑, 그것도 mcmax33 이 모의 전환을 저장한 뒤 모의 엔진을 켜기 전까지의 짧은 틈뿐이고 실자산은 무관하다.

## 2. 결과 파일 원문 (요지)

```
10:38:05 START main · 10:38:09 stopline OK · 10:38:10 대기 시작 notify=True
10:38:10 first ready snapshot OK pos=0 locked=0 age=32s inflight=0 last_buy_id=1490
10:39:15 ready at bar
10:41:02 backup /root/backup/tradebot_mcmax33_20261104_1039.db size=1095299072 ic=ok took=107s perm=600
10:42:15 merge_at sec_to_boundary=165 pos=0 locked=0 inflight=0 last_buy_id=1490 · restart_at=10:42:15
10:42:28 BOOT OK ... nrestarts=0 start=Wed 2026-11-04 10:42:16 KST
10:48:15 first_bars bar_done=2 · 3point head=eff249a dashboard=v1.2026.11.03.2304
10:48:15 check_v2_unit rc=0 pass=19 fail=0 · markers keeps_wallet=1 wallet_kept=3 placeholder_log=4
10:48:16 배포 완료 — 1시간 관찰 시작 notify=True
11:42:17 1h fail_markers=0 error=0 engine_exit=0 http429_418=0 bars_unique=19 auto_resume=0 v2_err=0 v2_429=0
11:42:18 1시간 관찰 통과 — 배포 ② 끝 notify=True · END
```

## 3. 남은 것

- 운영자 입회 마지막 확인(요청서 4절):
  - 2-5 브라우저: 버전 v1.2026.11.03.2304 표시, 정지 뒤 바로 시작 「정리 중」 문구.
  - 실계좌 검증 문구와 운용자산 줄 문구를 바꿀지 결정.
  - 첫 모의 전환 운영자 절차(계획 6절), check_v2_unit 2회째.
  - 그 뒤 임시 규칙 「정지 뒤 3분 이상, 시작은 신버전 단추」 끝냄.
- 1101-04 투자자 통보 한 번(요청서 5절 지갑 줄 포함).
- 문서 커밋은 서버에 pull 하지 않는다 — GitHub HEAD 가 서버 eff249a 보다 앞서는 것은 의도된 불일치.
