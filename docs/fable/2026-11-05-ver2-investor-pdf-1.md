# 질의: 투자자에게 보낼 「Ver2 업비트 결과와 반영 때 바뀌는 점」 PDF 를 만들었고, 사용자에게 발송 승인을 요청하려 합니다

**지금 단계:** 외부 발송 직전 (계획서 5절 · 8-C)
**다음에 하려는 일:** 사용자에게 PDF 를 보여 드리고 발송 승인을 받습니다. 발송은 운영자(사용자)가 직접 합니다. 보낸 뒤 `docs/operations/investor-notice-log.md` 에 #10 「체감 변경 통보 (PDF) — 연락 원칙 예외: 질문 PDF 약속 이행」을 적고, PDF·html·이 질의 파일·HANDOFF 를 한 문서 커밋으로 남깁니다(문서만 — 버전 갱신 없음, 커밋 전 비밀값 검사, push 는 2단계 끝까지 하지 않음 — push 전 자동 검사가 막음).

**배경:** 사용자 「1105-09 비교 확인, PDF 진행 · ①가 · ②가」(11/05). 1단계는 로컬 커밋 f4a370f(push 안 함). 비교 근거: `docs/plans/2026-11-05-ver2-backtester/compare/report.md`. 이 PDF 는 질문 PDF(`docs/new-version/investor-questions-20261105.html` 78줄 끝 문단)의 두 약속(업비트 결과 알림 · 반영 전 바뀌는 점 안내)을 지키는 것입니다. 2절의 「바뀌는 점」은 아직 구현하지 않은 2단계 계획(plan.md 1절 · 2-5 · 2-6 · 8-D)을 근거로 적었습니다.

## 지금까지 확인한 사실
| # | 사실 | 확인/추정 | 근거 |
|---|---|---|---|
| 1 | PDF 2쪽, 나눔고딕 넣음(emb yes), 렌더 그림으로 두 쪽 모두 글자가 보임 | 확인 | `pdffonts`, `pdftoppm` 렌더 확인. sha256 앞 16자 5063d34051c0e3bb |
| 2 | 1절 표 수치 = compare_table.csv | 확인 | compare/compare_table.csv |
| 3 | 이전 안내의 「60선이 200선 위 + 200선 상승」 문구 | 확인 | investor-approval-20261021-v2.html 396줄, investor-notice-20261104.html 40줄 |
| 4 | 건너뛴 즉시진입 업비트 7 · 바이낸스 5 | 확인 | compare_table.csv gcGapBlocked |
| 5 | JTO 1분봉 90일 약 2분 20초(137.1초) | 확인(로컬 맥 1회) / 서버는 추정 | compare/measure_1m_90d.json |
| 6 | 서버 사용자 3명 모두 EMA, 새 전략은 모의에서만 | 확인(11/05 14시대 SSH, plan.md 2-5) / 모의만은 운영 규칙 | plan.md 0절·2-5 |
| 7 | 강제 매수 중단 중 허용·표시, 감사 사유 2개, 옛 2칸 버림·새 칸 기본값, 데드크로스 기존 설정 유지 | 계획(아직 구현 전) | plan.md 2-5 · 2-6 · 8-D |
| 8 | 기본값: ma60MinSlope 0 · gcMaxGapPct 0 · slStreakPause 0 · episodePullbackCap 0 · deadcross no | 확인 | plan.md 1절, Ver2 html 입력 기본값 |

## 물어볼 것
| # | 질문 | PO의 생각 |
|---|---|---|
| 1 | 사실 오류나 투자자가 오해할 문장이 있는가(특히 1절 추정 표시, −10.5%·+6.6% 상자) | 추정은 모두 「추정」으로 적음 |
| 2 | 아직 구현 전인 2단계 동작을 「바뀝니다」로 단정해도 되는가 | 계획서가 승인되었고, 배포 뒤 화면이 다르면 다시 알린다고 맺음 |
| 3 | 「원하시면 설정을 알려 주세요」가 투자자 연락 원칙(회신 대기 금지)에 어긋나는가 | 선택 문장이고 백로그에 회신 대기를 두지 않음 |
| 4 | 빠진 바뀌는 점이 있는가(계획서 1절 R1~R7, Q3 ②, 결정 ③, 8-D) | 다 넣었다고 봄 |

## 참고 파일
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/new-version/investor-ver2-result-20261105.html
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/new-version/investor-ver2-result-20261105.pdf
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/new-version/investor-questions-20261105.html
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/plans/2026-11-05-ver2-backtester/plan.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/plans/2026-11-05-ver2-backtester/compare/report.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/plans/2026-11-05-ver2-backtester/compare/compare_table.csv
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/operations/investor-notice-log.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/investor-approval-20261021-v2.html
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/investor-notice-20261104.html
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/new-version/MA_GC_Pullback_Backtester_2611051030(Ver2).html

# 답변 (Fable 1회째, 11/05)

**판정:** 진행
**이유:** PDF 의 숫자·인용·기본값·약속 문장을 원 출처(compare_table.csv · run_log.txt · 투자자 시험 그림 2장 · Ver2 html 입력 칸 · 승인 요청서 396줄 · 11/04 안내 41줄 · 질문 PDF 78줄 · measure_1m_90d.json)와 대조한 결과 사실 오류가 없고, 글꼴 임베드와 렌더 확인도 통과했습니다. 남은 지적은 모두 권고입니다.

| # | 질문 | 답 | 확신 |
|---|---|---|---|
| 1 | 사실 오류·오해 문장 | 사실 오류 없음. 오해 소지는 「거래 기록」 행 하나(권고 2) | 높음 |
| 2 | 구현 전 2단계 동작을 단정해도 되는가 | 됨. 다만 2단계에서 표 11행 가운데 하나라도 달라지면 한 번 더 보내야 하므로 배포 보고서에 「PDF 표와 달라진 곳」 확인 줄을 넣기 권고 | 높음 |
| 3 | 연락 원칙 | 어긋나지 않음. 요청형 어미를 피하면 더 안전(권고 1) | 보통 |
| 4 | 빠진 바뀌는 점 | slopeLB 값 그대로·뜻만 60선(권고 3) 하나 | 높음 |

고쳐야 할 것(모두 권고) → 모두 반영: 1 「보내 주시면 … 확인해 드리겠습니다」 · 2 「백테스터 거래 기록(CSV)」 · 3 lookback 문장 추가 · 4 참고(대체 글꼴도 emb yes, 렌더 또렷). 다시 만든 PDF: 2쪽, 글꼴 모두 emb yes, 렌더 확인, sha256 앞 16자 4f22ac02d797a3b8 (처음 5063d34051c0e3bb).
