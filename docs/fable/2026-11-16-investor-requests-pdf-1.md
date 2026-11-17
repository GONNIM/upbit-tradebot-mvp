# 질의: 투자자 요청 PDF(첫 눌림목 거래 앱 대조 · Ver9 반영 범위 ㉠㉡)를 만들었고, 사용자가 투자자에게 보내려 함

**지금 단계:** 요구 정리(투자자에게 보낼 요청서 — 외부 발송 직전)
**다음에 하려는 일:** 사용자가 PDF 를 투자자에게 보낸다(발송은 사용자). 보낸 뒤 investor-notice-log.md 에 한 줄 기록하고, 답이 오면 1109-01 을 닫고 1111-01 반영 계획을 쓴다. 이 질의는 PDF 내용의 사실·위험만 묻는다(문장 다듬기 제외).

## 지금까지 확인한 사실
| # | 사실 | 확인/추정 | 근거 |
|---|---|---|---|
| 1 | 사용자 지시(11/16): 「투자자에게 요청하는 내용은 pdf 문서로 제공하시오」 | 확인 | 대화 |
| 2 | 투자자 답(사용자 전달, 11/16): 「ver9로 적용은 해야할듯 8현재거로는 잘 분석이 안되네」. Ver8 질문 1(숏 실매매)·3(기본값)의 답은 없음 | 확인 | 대화, docs/new-version/ver8/investor-questions-20261111.html |
| 3 | 첫 눌림목 매수: 11/13 09:42:10 시장가 2,462,165원, [OR] final vol 5673.19124423 avg 434, fee=0.0 표기, audit_trades id 1526 BUY PULLBACK split_round 1 | 확인 | 서버 journal·DB 읽기(사용자 ! 실행 출력, 11/16 14시대) — 스크립트 scratchpad read-1116b.sh |
| 4 | 매도: 11/14 10:39:11 시장가 같은 수량, audit_trades id 1527 SELL reason SL judged_price 412.3 fill 412.0 bars_held 349, 이후 주문 0 | 확인 | 같은 출력 |
| 5 | PDF 매도 이유 칸은 「손절(손절 기준 가격 412.3원에 닿음)」 — audit reason SL·judged_price 412.3 그대로. 손절 비율(5% 로 보임)은 설정 파일을 보지 않아 PDF 에 쓰지 않음 | 확인 | 같은 출력 |
| 6 | 손실 (412−434)×5673.19124423 ≈ −124,810원, −5.07%(수수료 전) | 확인(계산) | 위 숫자 |
| 7 | Ver9 현물 simulate 는 Ver2(=지금 신버전 백테스터 원문)와 같음 | 확인 | awk simulate 구간 md5 둘 다 3adb0f6eedc29db16eb67eefba1965d5 |
| 8 | Ver9 새 기능: 월·주별 1등 조합+다음 기간 수익률, 둔화 축·조합 상한 20000·CSV, 차트 전체화면·끌어 이동·밀도, 선물 롱+숏(fapi.binance.com, 방식 A·B·C, 펀딩비) | 확인 | scratchpad ver9-gap.md, v8v9.diff |
| 9 | 기본값: 지금 신버전 분할 5·TP 1.0·SL 1.5 / Ver9 분할 1·TP 3·SL 3 | 확인 | v2/static/backtester.html:111-113, Ver9 html:106-109 |
| 10 | 신버전 고유(업비트 소스·트레일링 스톱 패치·−/+ 단추)는 유지 예정 | 확인(계획 의도) | ver9-gap.md 4절 |
| 11 | fapi 두 주소는 맥에서 200·ACAO * | 확인 | curl Origin 헤더 시험 11/16 |
| 12 | PDF 1쪽, 나눔고딕 3종 emb=yes sub=yes(그 밖에 Helvetica·AppleSDGothicNeo-Bold 도 임베드), pdftotext 핵심 숫자 일치, 110dpi 렌더 직접 열어 글자 모두 보임 | 확인 | pdfinfo·pdffonts·pdftoppm |
| 13 | 투자자 연락 원칙: 클레임 답변·체감 변경 통보만. 이번은 사용자 지시로 보내는 요청서 | 확인 | .claude/context/project-rules.md 「투자자 연락 원칙」 |

## 물어볼 것
| # | 질문 | PO의 생각 |
|---|---|---|
| 1 | PDF 의 사실(거래 숫자·손절 사유·Ver9 차이·기본값)에 틀리거나 오해를 부를 곳이 있는가 | 수수료 칸이 비어 있다는 표현(로그 fee=0.0)이 가장 약한 곳. 실제 수수료는 앱 대조로 받음 |
| 2 | ㉠ ① 「숏은 화면 계산만」 권장, ㉡ ① Ver9 기본값 권장이 투자자 답·이전 결정과 부딪히는가 | 「Ver9 로 적용」에 가장 가깝다고 봄. 실매매 영향 없음 |
| 3 | 투자자 연락 원칙과 부딪히는가, 발송 전에 더 막을 위험이 있는가 | 사용자 지시라 문제없다고 봄 |

## 참고 파일
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/new-version/ver9/investor-requests-20261116.html
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/new-version/ver9/investor-requests-20261116.pdf
- /private/tmp/claude-501/-Users-gonnim-Project-MVP-Source-upbit-tradebot-mvp/5f99e5be-afdb-4f97-97b6-59885092ddde/scratchpad/ver9-gap.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/new-version/ver8/investor-questions-20261111.html
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/v2/static/backtester.html
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/HANDOFF.md (0-1 표 1109-01·1111-01 행)

---

# 답변 (1회째): 투자자 요청 PDF(첫 눌림목 거래 앱 대조 · Ver9 반영 범위 ㉠㉡)를 만들었고, 사용자가 투자자에게 보내려 함

**판정:** 수정 후 진행
**이유:** 거래 숫자와 Ver9 차이 목록은 PDF 와 근거가 맞습니다. 다만 「현물 매매 규칙은 지금 봇과 똑같습니다」와 「수수료는 앱에서만 확인할 수 있습니다」 두 문장이 사실과 어긋나고, 산출물 규칙의 모바일 렌더 확인이 빠져 있습니다.

## 고쳐야 할 것 (요지)
| # | 중요도 | 무엇을 |
|---|---|---|
| 1 | 막음 | 「현물 매매 규칙은 지금 봇과 똑같습니다」 → Ver9 = Ver2 와 같고, 지금 봇은 Ver2 위에 패치 10곳(tests/v2/js/fixtures/ver2_patches.json) |
| 2 | 막음 | 「수수료 칸이 비어 있어 앱에서만」 → 로그는 fee=0.0 으로 적힘(engine/order_reconciler.py:384), 주문 조회 paid_fee 로도 읽을 수 있음 |
| 3 | 막음 | 모바일 PDF 뷰어 확인(project-rules 산출물 규칙 4번). 못 하면 사용자에게 휴대폰에서 열어 봐 달라고 요청 |
| 4 | 권고 | 발송 뒤 notice-log #16 「연락 원칙 예외(사용자 지시 11/16, #14 후속)」, 답 없을 때 1109-01 닫는 방법 HANDOFF 한 줄 |
| 5 | 권고 | 수수료를 서버 주문 조회로 미리 읽는 방법을 사용자에게 알림 |
| 6 | 권고 | 앱 메뉴가 다르면 화면 사진을 보내도 된다는 문장 추가 |
| 7 | 권고 | 반영 계획에 스윕 기본 범위 3개 처리 · 업비트 출처일 때 선물 단추 막기 · 선물은 바이낸스 USDT 기준 안내 |

사용자에게 물어야 할 것: 수수료를 서버 조회로 미리 채울지 · 11/17 까지 답이 없으면 1109-01 을 봇 기록만으로 닫을지.

---

# 다시 묻기 (2회째): 막음 3건 처리 결과

| # | 처리 | 확인 |
|---|---|---|
| 1 | 「Ver9 의 현물 매매 규칙은 지금 봇의 바탕인 Ver2 와 똑같습니다. 지금 봇과 대시보드에는 그 위에 보정 2가지(구간 순번 · 건너뜀 횟수)와 트레일링 스톱이 더 들어 있습니다. 그래서 Ver9 파일과 대시보드의 결과 숫자는 다를 수 있습니다. 실제 매매 방식은 바뀌지 않습니다.」로 고침 | ver2_patches.json patches 10개 확인, pdftotext 로 문장 확인 |
| 2 | 「봇 기록에는 수수료가 0원으로 적혀 있습니다. 실제 수수료를 앱에서 확인해 주세요.」로 고침 | order_reconciler.py:384 확인, pdftotext 확인 |
| 3 | po 는 모바일 뷰어를 열 수 없음 → 보고에 「보내기 전에 휴대폰(메신저 첨부 미리보기)에서 한 번 열어 봐 주십시오」를 사용자 할 일로 적음. PDF 재생성 뒤 3단계 다시 함: 1쪽 · 글꼴 6종 emb=yes sub=yes · pdftotext 문장 확인 · 110dpi 렌더 직접 열어 글자 모두 보임 · 118,175바이트 · sha256 c93554aca0ade160… | pdfinfo·pdffonts·pdftoppm |
| 6 | 권고 반영: 「화면이 다르면 거래내역 화면 사진을 보내 주셔도 됩니다.」 추가 | pdftotext |
| 4·5·7 | 4 는 발송 뒤 처리, 5 와 「답 없을 때」는 사용자 결정으로 보고, 7 은 반영 계획에 넣음 | — |

물어볼 것: 막음 3건이 처리됐는지, 발송해도 되는지.

# 답변 (2회째)

**판정:** 진행
**이유:** 1회째의 막음 3건이 고친 PDF 와 처리 방법에서 모두 풀렸습니다. 남은 것은 권고와 사용자가 정할 일뿐이고, 발송을 막는 사실 오류는 찾지 못했습니다.

- 확인: 고친 문장 3곳 pdftotext 로 확인 · ver2_patches.json 10곳 및 core/strategy_pullback.py:390-407 과 맞음 · 1쪽 · 118,175바이트 · sha256 c93554aca0ade160 · 글꼴 6종 emb/sub yes · 110dpi 렌더 글자 모두 보임.
- 발송 조건: 사용자가 보내기 전에 휴대폰 메신저 첨부 미리보기에서 한 번 열어 봄.
- 권고: (1) 휴대폰 확인을 발송보다 앞 순서로 적기 (2) 발송 뒤 notice-log #16 「연락 원칙 예외(사용자 지시 11/16, #14 후속)」+ sha256 (3) 반영 계획에 스윕 기본 범위 3개 · 업비트 출처 때 선물 단추 막기 · 선물은 바이낸스 USDT 기준 안내.
- 사용자에게 물어야 할 것: 수수료를 서버 주문 조회로 먼저 채울지(정하지 않으면 지금 PDF 그대로) · 11/17 까지 답이 없으면 1109-01 을 봇 기록만으로 닫을지.
