# 배포 ① 완료 보고 — 1102-01 정체 시계 + 1102-02 재시작 정체 최고가 + 1101-08 백업 권한 (2026-11-03)

- 요청서: `deploy-request-20261103-bundle1.md` (승인: 11/03 15:39 사용자 업로드·드라이런, 15:40 본 띄우기 — 사용자 실행)
- 결과 원문: 서버 `/root/deploy-1103/result.log` (11/03 사용자 `!` 읽기, 아래 2절에 옮김)
- **버전: v1.2026.11.01.1849 → v1.2026.11.03.1532**

## 1. 결과

| 항목 | 값 | 판정 |
|---|---|---|
| 3점 일치 | 서버 HEAD 46e2864 · 서버 dashboard v1.2026.11.03.1532 · tradebot 기동 Tue 2026-11-03 15:45:10 KST (로컬 HEAD 46e2864 · 로컬 dashboard 1532) | 일치 |
| 기동 확인 | BOOT OK warmup=1 boot_resume_live=1 fail_lines=0 error=0 active nrestarts=0 | 통과 |
| 첫 봉 | Bar#201(15:45 봉)·Bar#202(15:48 봉) HOLD, pos=False | 통과 |
| check_v2_unit | rc=0 pass=19 fail=0 | 통과 |
| 새 코드 표식 | stale_clock=2 · stale_peak=4 · 엔진 스레드 1 · 엔진 시작 표지 2 | 새 코드로 돎 |
| 1시간 관찰 (15:45~16:45) | fail_markers=0 error=0 engine_exit=0 http429_418=0 bars_unique=19 auto_resume=0 v2_err=0 v2_429=0 | 통과 |
| 1101-08 백업 권한 | `/root/cleanup_tradebot_db.sh` 2번째 줄 `umask 077`(스크립트 자체 755 그대로) · `services/data/backups/tradebot_mcmax33.db.backup_*` 600 아닌 파일 0(바꾼 파일 0) | 통과 |
| 배포 전 DB 백업 | /root/backup/tradebot_mcmax33_20261103_1542.db · 무결성 ok · 600 | 통과 |
| 되돌리기 | 없음 | — |

보유 0 상태에서 배포했다(15:40~15:45 보유·묶임·미체결 0, 마지막 매수 id 1487 그대로). 정체 매도는 꺼져 있어(11/01 19:55 사용자 설정) 배포 직후 매매 판정이 달라진 경로는 없다. 표식 stale_clock·stale_peak 는 보유가 없어 「건너뜀」 줄로 찍힌 것으로 본다(추정 — 줄 원문은 결과 파일에 없음, journal `[STALE-CLOCK]`·`[STALE-PEAK]` 줄을 보면 확인된다).

## 2. 결과 파일 원문 (요지)

```
15:40:05 START main · 15:40:08 stopline OK · 15:40:09 대기 시작 notify=True
15:43:56 backup /root/backup/tradebot_mcmax33_20261103_1542.db size=1085902848 ic=ok took=102s perm=600
15:45:10 merge_at sec_to_boundary=170 pos=0 locked=0 inflight=0 last_buy_id=1487 · restart_at=15:45:10
15:45:22 BOOT OK ... nrestarts=0 start=Tue 2026-11-03 15:45:10 KST
15:51:14 first_bars bar_done=2 · 3point head=46e2864 dashboard=v1.2026.11.03.1532
15:51:14 check_v2_unit rc=0 pass=19 fail=0 · markers stale_clock=2 stale_peak=4
15:51:15 배포 완료 — 1시간 관찰 시작 notify=True
16:45:16 1h fail_markers=0 error=0 engine_exit=0 http429_418=0 bars_unique=19 auto_resume=0 v2_err=0 v2_429=0
16:45:16 cleanup umask added line2=umask 077 perm=755 · backups chmod600 count=0 left_non600=0
16:45:17 1시간 관찰 통과 — 배포 ① 끝 notify=True · END
```

## 3. 남은 것

- 배포 ② 1029-12(모의 지갑 덮어쓰기) — 자리표시자 갱신의 「실시간 재판정」 문구 정리 함께.
- 운영자 입회 마지막 확인: 2-5 브라우저(버전 표시·정지 뒤 바로 시작 「정리 중」 문구), 첫 모의 전환·check_v2_unit 2회째. 그 뒤 임시 규칙 「정지 뒤 3분 이상, 시작은 신버전 단추」 끝냄.
- 1101-04 투자자 통보 한 번(요청서 5절 정체 시계 줄 포함).
- 문서 커밋은 서버에 pull 하지 않는다 — GitHub HEAD 가 서버 46e2864 보다 앞서는 것은 의도된 불일치.
