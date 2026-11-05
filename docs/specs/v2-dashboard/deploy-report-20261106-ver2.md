# Ver2 배포 보고 (1105-09) — 2026-11-06

**결과:** 배포 끝 · 1시간 관찰 통과 (01:39:16). 되돌리기 없음.
**버전:** v1.2026.11.03.2304 → v1.2026.11.05.2039 (fixup 없음)
**판:** eff249a → dc95432 (fast-forward, 런타임 커밋 f4a370f · c0559e3 · b9e91ed)
**요청서:** docs/specs/v2-dashboard/deploy-request-20261106-ver2.md · Fable docs/fable/2026-11-05-ver2-deploy-request-1.md (진행)
**승인:** 사용자 「1105-09 가 승인, 1105-09 나 승인」(11/05) · 드라이런·본 띄우기는 사용자가 직접 실행

## 1. 3점 일치
| 항목 | 값 |
|---|---|
| 로컬 HEAD · 버전 | dc95432 · v1.2026.11.05.2039 |
| 서버 HEAD · 버전 | dc95432 · v1.2026.11.05.2039 |
| tradebot ExecMainStartTimestamp | Fri 2026-11-06 00:39:08 KST |
| tradebot-v2 ExecMainStartTimestamp | Fri 2026-11-06 00:39:20 KST |

## 2. 경과
| 시각 | 일 |
|---|---|
| 11/05 21:00 | 읽기 전용 사전 점검 (precheck.sh) |
| 11/06 00:22:06 | cafe24 정기 점검 재부팅(「Power key pressed」, 안내 00:00~03:00 「시스템 설정 변경 및 서버 재부팅」). 사용자 조작 아님(사용자 확인). 엔진 BOOT-RESUME 00:22:29 자동 복구, ERROR 0 |
| 00:23:14 | 드라이런 1회째: 정지선 불일치(두 서비스 기동 시각이 재부팅으로 바뀜) — 아무것도 바꾸지 않고 끝남 |
| 00:32:43 | run.sh 기준 시각 3개(EXP_TB_START · EXP_V2_START = 00:22:22, T_BASE = 00:22:19) 고친 뒤 드라이런 2회째: stopline OK · ready OK |
| 00:34:35 | 본 띄우기(사용자) · stopline OK · 대기 시작 알림 |
| 00:37:46 | DB 백업 /root/backup/tradebot_mcmax33_20261106_0036.db (1,114,193,920B · ic=ok · 93초 · 600) |
| 00:39:08 | merge(ff) · tradebot 재시작 (보유 0 · 미체결 0 · 경계까지 172초) |
| 00:39:20 | BOOT OK (warmup 1 · boot_resume_live 1 · 실패 줄 0 · ERROR 0 · NRestarts 0) → tradebot-v2 재시작 |
| 00:39:51 | v2 active · ERROR 0 |
| 00:45:12 | 첫 봉 2개 처리 · check_v2_unit 19/19 · 표식 4개 존재 · `[migrate] added pullback_state.*` 18줄 · 칸 수 default·gon1972·mcmax33 = 30, tradebot_.db = 0(표 없음, 정상) · 「배포 완료」 알림 |
| 01:39:14 | 1시간 관찰: fail_markers 0 · error 0 · engine_exit 0 · 429/418 0 · 봉 20개(3분봉 1시간과 같음) · auto_resume 0 · v2_err 0 · v2_429 0 · v2 메모리 최대 28,213,248B(약 27MB) |
| 01:39:16 | 「1시간 관찰 통과」 알림 · 스크립트 끝 |

## 3. 남은 것
1. 운영자 화면 확인(1-A): 두 화면 새로고침 → 신버전 버전 표시 2039 · 새 전략 설정의 새 칸(60선 기울기 · 상승폭 제한 · 연속 손절 중단 · 구간 익절 · 10/15/30분) · 백테스터 90일 선택.
2. 1분봉 90일 백테스트 1회 → v2 메모리 재측정(로컬 최악 96.7MB, 상한 150MB).
3. 투자자 통보: 화면이 notice-log #10(Ver2 비교 PDF)과 다를 때만.
4. 백로그: `_ensure_column` 칸 중복 예외 흡수(docs/plans/backlog.md) · 1104-02.

## 4. 참고
- 서버는 dc95432 (main) 에 있음 — detached 아님.
- 배포 스크립트 원본: 세션 scratchpad deploy-1106/run.sh (deploy-1104 run.sh 를 patch_run.py 로 고침 + 기준 시각 3개 수정).
