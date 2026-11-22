# 질의: 투자자 결정 질의 PDF(1쪽)를 만들었고, 사용자에게 발송용으로 넘기려 함

**지금 단계:** 리뷰
**다음에 하려는 일:** PDF 를 사용자에게 넘긴다. 발송은 사용자가 한다. 발송 뒤 투자자 연락 기록에 한 줄 적는다(사용자 「보냄」 뒤).

## 지금까지 확인한 사실
| # | 사실 | 확인/추정 | 근거 |
|---|---|---|---|
| 1 | 사용자 지시(11/21): 「투자자에게 정해야 하는 결정에 대해 질의 내용을 pdf 문서로 제공하시오」 | 확인 | 대화 |
| 2 | 질문 4개는 계획 2판 2절 ㉠~㉣ 과 같다(verifier 1회·Fable 2회 거친 계획) | 확인 | /private/tmp/claude-501/-Users-gonnim-Project-MVP-Source-upbit-tradebot-mvp/c37bfe27-a876-4cd2-9521-ec445719cefb/scratchpad/fullback-plan-draft.md, /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/fable/2026-11-21-fullback-plan-1.md |
| 3 | 보유 중 익절·손절 변경은 진행 중 거래에 바로 쓰이고(IMMEDIATE_KEYS tp·sl·deadcross, trade_tp_pct 재계산), 추적 손절은 연 때 값 그대로다 | 확인 | engine/pullback_apply.py:41·43·362~368 |
| 4 | 추적 손절 폭은 1~100, 기본 50 | 확인 | engine/pullback_params.py:88, v2/static/backtester.html:154 |
| 5 | 「1.50 은 익절로 보인다」 | 추정(문서에 「보입니다」로 적음) | PDF 3쪽 예시, 투자자 목록에 TP 없음 |
| 6 | PDF 1쪽 · 110,498바이트 · sha256 b3c07f5b9267fc4c… · 글꼴 6종 emb=yes sub=yes · pdftotext 「질문」 4건 · 110dpi 렌더 직접 열어 글자 모두 보임 | 확인 | pdfinfo·pdffonts·pdftotext·pdftoppm |
| 7 | 내부 이름·키 값·비밀 없음 | 확인 | HTML 원본 |

## 물어볼 것
| # | 질문 | PO의 생각 |
|---|---|---|
| 1 | 투자자 문장에 사실 오류나 오해할 곳이 있는가(특히 ㉡ 설명, 「모두 화면만 바뀝니다」) | 감사 로그·운용 줄도 화면 표시라 맞다 |
| 2 | 투자자 연락 원칙(클레임 답변·체감 변경 통보만)과 맞는가 | 사용자가 직접 PDF 로 물으라고 지시했으므로 사용자 결정 |

## 참고 파일
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/new-version/claim/ver9/investor-questions-20261121.html
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/new-version/claim/ver9/investor-questions-20261121.pdf
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/new-version/claim/ver9/Fullback_수정사항_261121.pdf


---

# 답변 1회째 요지 (Fable · 11/21)

- 판정: 수정 후 진행. 막음 3: ㉣ 근거 문장 논리(1.50 도 1~100 안) · ㉠ 줄이 약 60시간 뒤 사라짐을 밝힘 · 고친 뒤 PDF 재검증. 권고: ㉡ 구간 초과 TP 감소 예외, ㉠ 평단 바뀌면 다시 셈, 계획 ㉡ 문장 고침, 휴대폰 미리보기 미확인 보고, ㉢② 실측 전, 답 없을 때 처리 한 줄(사용자 결정).
- 반영: 막음 3·권고 4~6 반영, 마지막 줄 「11월 24일까지 답이 없으면 권장(①)대로 고치겠습니다」(프로젝트 「회신을 기다리지 않는다」 원칙과 맞춤, 사용자에게 알림). 새 PDF 1쪽 · 116,501바이트 · sha256 2d18023aa048e67e… · 글꼴 7종 emb/sub yes · pdftotext 고친 문장 4곳 확인 · 110dpi 렌더 직접 열어 글자 모두 보임(원 숫자 ①은 pdftotext 에서 빠지나 렌더에는 보임). 2회째 질의로 확인받음(아래).


# 답변 2회째 요지 (Fable · 11/21)

- 판정: 진행. 막음 3 반영 확인, 새 사실 오류 없음. 권고: ㉡ 칸 이름을 「구간 내 눌림목 돌파 횟수」로(반영), 보고에 휴대폰 미리보기 미확인·㉢② 실측 전·봉 단위 3분 전제 적기, 발송 뒤 연락 기록에 sha 그대로. 사용자에게: 기한 11/24 그대로 둘지, 답 없을 때 권장대로 고치는 약속 동의.
- 최종 PDF: 1쪽 · 116,486바이트 · sha256 3ce5072b911ed692… · 글꼴 모두 emb/sub yes · pdftotext 고친 문장 확인 · 110dpi 렌더 직접 열어 글자 모두 보임.
