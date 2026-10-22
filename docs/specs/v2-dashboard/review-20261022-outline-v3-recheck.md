# 재검증 보고 — 목차 3판 수정본·spec 3.2 개정안 (2026-10-22)

- 검증: `verifier` (읽기 전용, 서버 DB 미열람 — 코드·journal·cron·ls 만)
- 대상: scratchpad `plan-outline-v3-draft.md`, `spec-new.md`(원본 `docs/specs/v2-dashboard/spec.md` 대비 diff)

## 1회째 — 판정: 수정 후 승인
- 앞 보고 지적 1~12: 10건 해소, 2건(2 보유 중 공백, 11 E1 판정 기준) 일부 해소.
- 반박: (6) E17 「판단 기록은 봉마다 남는다」 — 무거래 봉은 평가 생략(`engine/live_loop.py:1371-1376` `[CONFIRMED-NO-TRADE]`, journal 2026-10-22 06:06~06:07 실례, 미보유 중 `audit_buy_eval` 24분 공백). `strategy_engine.py:819` 는 분기, 기록 지점은 `:1881,1945,1986`(매수)·`:2111,2192`(매도). (17) 재시작 「경계 뒤 10~40초」는 봉 처리 재시도(최대 약 91초)와 겹침. (22) D 절 「결정 없음」 — E17 결정 필요.
- 일부 반박: (11) v2hist 600 수단 없음(umask 022), 「사본 금지」 오적용·백업 방침 없음. (18) Bar 누락 판정이 무거래 봉을 실패로 셈. (19) diff 허용 목록에 `scripts/regression_gate.sh` 없음.
- 확인: E16 P3 영향(`live_loop.py:776` `seed_initial_snapshot` ValueError → `:779` 경고, `settings_history.py:257` PULLBACK 이면 None → `trader.py:436` 이력 id NULL), E18 systemd 의미, v2hist rw/rwc 규칙, WO-12 `plan.md:285`, `ProtectProc=invisible` 은 같은 uid 에 무효(앞 권고 정정).
- 지적 N1~N8: N1 무거래 봉 오표시(결정), N2 조건부 재시작·NO-TRADE 제외, N3 `UMask=0077`·백업 방침(결정), N4 `CapabilityBoundingSet=` 후보(미확인, A17 실측), N5 계정 추가 절차·`InaccessiblePaths=-`, N6 `scripts/`, N7 인용 줄, N8 세 곳 불일치.

## 2회째 — 판정: 승인 가능 (결정 A·B 만 남음)
- N2~N8 해소. 결정 대기 표시 V1·T5·spec E17·E15 일치. 새 문구 사실 오류 없음.
- 개선 5건(메인 세션 반영 완료): 결정 B (a) 를 「별도 cron 줄, 기존 `/root/cleanup_tradebot_db.sh`(매주 일 11:00, 실매매 DB DELETE·`wal_checkpoint(TRUNCATE)`) 는 고치지 않음, 백업본 600 맞춤」으로, 결정 A (b) 에 오표시 결과, 「대기 중 주문 0」 확인 수단은 계획서 본문, `UMask=0077` 로 실매매 DB `-wal`·`-shm` 600 은 정상(V4), spec 9절 무거래 봉 언급.
