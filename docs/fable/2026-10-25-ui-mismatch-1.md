# 질의: 운영자가 신버전 화면이 제공 화면과 전혀 다르다고 지적해 원인을 조사했고, 사용자에게 처리 결정을 올리려 합니다

**지금 단계:** 요구 정리 (배포 뒤 UI 불일치 지적 → 결정 요청)
**다음에 하려는 일:** 사용자에게 세 가지를 묻습니다. (1) 고칠 때까지 입장 버튼을 숨길지(`: > /root/upbit-tradebot-mvp/.v2_allowlist`, 재시작 없음, 승인 뒤 실행 직전 따로 질의). (2) 기준 화면이 투자자 승인 문서 그림 2-가~2-마(홈·차트·백테스터·로그·운용)인지. (3) PC 배치를 어떻게 할지. 답을 받으면 UI 재작업 설계(브레인스토밍 → 계획)부터 시작합니다. 이 질의서는 다음 문서 커밋에 넣습니다.

## 지금까지 확인한 사실
| # | 사실 | 근거 (명령·출력·파일 경로) |
|---|---|---|
| 1 | 사용자 원문: 「https://orionhunter7.cafe24.com/v2/ 화면을 PC에서 확인했다. 전혀 제공한 페이지에 맞지 않게 구현되어 있으며... PC, Mobile 모두 정확하게 맞게 구현하시오. 먼저 완전히 어긋나버려서 다른 확인은 진행하지 않았다.」 | 사용자 메시지 (10/25 18시대) |
| 2 | 운영자는 18:26~18:27 Mac Chrome 으로 정상 입장해 홈·차트 표시(markers)·로그·백테스터를 열었다. API 모두 200 | 서버 nginx access.log `/v2/` 줄 (토큰 가림) |
| 3 | 투자자 승인 문서 2절 「신버전 화면 미리보기」 그림 2-가 홈·2-나 차트·2-다 백테스터·2-라 로그·2-마 운용(휴대폰 틀). 짙은 남색 머리 띠(제목·사용자·구버전으로 / 모드), 채운 알약 배지(LIVE 빨강·엔진 동작 중 초록·전략 파랑·일시정지 회색), 카드(자산: 평가 합계 큰 굵은 글씨·원화/코인·평가손익, 보유: 분할 회차·평균 매수가·익절/손절 가격, 최신 신호 문장, 최근 거래 표 시각·구분·사유·금액), 아래 탭 막대(선택 탭 위 파란 줄), 차트 위 구간 선택 막대(1분·최근 200봉·확대+·축소-)·범례·설명 카드, 백테스터 데이터 출처 선택 막대(업비트·바이낸스)·2열 입력 카드·「그 밖의 입력 18개(접힘)」, 로그 선택 막대(감사 로그·엔진·오류)·표 | /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/investor-approval-20261021-v2.html (2절), 렌더 확인 |
| 4 | 승인 문서 문구: 「그림은 모두 개략 화면(예시)입니다… 실제 화면은 모양이 조금 다를 수 있습니다」 | 같은 파일 0절 |
| 5 | spec 4.3 디자인 기준: 「원본 백테스터의 밀도와 반응형 기준을 따른다(640px·420px 구간, 입력창 글자 16px)」. 원본 백테스터 = 사용자가 준 `docs/specs/MA60_200_GoldenCross_Pullback_Backtester_2610201820.html`(흰 배경 Arial, max-width 1250px, 4열 그리드) | /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/spec.md:5,118 |
| 6 | 현재 구현 v2/static/style.css(55줄): 머리 띠 없음, 테두리만 있는 배지, dl 목록형 카드, 평가 합계 없음, 거래·신호는 목록(표 아님), 차트 구간 선택 막대 없음, 로그 선택 막대 없음, body 폭 제한 없음(PC 에서 화면 전체 폭으로 늘어남), 백테스터는 아래 탭이 아닌 별도 페이지(backtester.html, 자체 style) | /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/v2/static/style.css, index.html, backtester.html |
| 7 | 현재 서버: 허용 목록에 mcmax33 → 투자자 화면에 입장 버튼이 보임. 투자자 통보(D9)는 아직 보내지 않음. 버튼 숨김은 `: > .v2_allowlist`(재시작 없음, 이때부터 v2 API 403, 되돌리기는 다시 한 줄 쓰기) | 요청서 2-10 1항 |
| 8 | 엔진·매매 영향 없음(v2 는 읽기 전용, 30분 관찰 통과) | 이전 보고 |

## 물어볼 것
| # | 질문 | PO의 생각 |
|---|---|---|
| 1 | 고칠 때까지 버튼 숨김을 권고안으로 올리는 것이 사실·위험 면에서 맞는가 | 맞음. 투자자가 승인 화면과 다른 화면을 보지 않게 함. 재시작 없음·즉시 되돌림 가능 |
| 2 | 기준 화면 질문을 「승인 문서 그림 2-가~2-마를 기준(권고)」 / 「원본 백테스터 스타일」 / 「다른 자료」로 올리는 것이 맞는가. 백테스터 메뉴는 그림 2-다 틀(머리 띠·출처 선택·입력 카드) 안에 원본 기능 전부를 넣는 안 | 맞음. 「제공한 페이지」가 어느 것인지 사용자만 확정 가능 |
| 3 | PC 배치 질문: 「휴대폰 시안을 가운데 폭 제한(약 480px)으로 그대로(권고)」 / 「PC 는 같은 디자인으로 2열 카드 넓은 배치」 | 시안은 휴대폰만 있음. 사용자 결정 필요 |
| 4 | 재작업은 spec 4.3 디자인 기준 문구 변경·계획·verifier·Fable·브라우저 실측(PC·412px)·사용자 실기기 확인을 거쳐 다시 배포 승인을 받는 순서가 맞는가 | 맞음 |

## 참고 파일
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/investor-approval-20261021-v2.html
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/spec.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/MA60_200_GoldenCross_Pullback_Backtester_2610201820.html
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/v2/static/style.css
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/v2/static/index.html
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/v2/static/backtester.html
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/deploy-request-20261025.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/CLAUDE.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/.claude/context/project-rules.md

---

# 답변: 운영자가 신버전 화면이 제공 화면과 전혀 다르다고 지적해 원인을 조사했고, 사용자에게 처리 결정을 올리려 합니다

**판정:** 진행
**이유:** 사실 2~8 을 승인 문서 원문·spec·정적 파일·서버 읽기 전용 SSH 로 확인했고 기재와 일치. 세 질문은 모두 사용자만 정할 일이고 결정 요청 자체가 다음 단계.

(직접 확인 요지: 승인 문서 2절 208~390행 요소 일치, 0절 「개략 화면(예시)」. spec 에 그림 2-가~마를 기준으로 삼는 문장 없음(:5·:118 은 원본 백테스터). style.css·index.html·backtester.html 구조 사실 6 과 일치. 서버 HEAD 5692998·허용 목록 8바이트·tradebot 정상. access.log 18:26:48~18:27:35 302 → 200 반복. 숨김 수단 코드 확인: v2_entry_token.py:93-108 매 호출 재읽기, handlers.py:66-80 403.)

## 질문별 답
| # | 질문 | 답 | 확신 |
|---|---|---|---|
| 1 | 버튼 숨김 권고 | 맞음. 단 운영자도 mcmax33 이라 서버 화면을 못 봄 → 확인은 로컬·실기기, 재배포 때 다시 한 줄 | 높음 |
| 2 | 기준 화면 질문 | 맞음. 승인 문서가 투자자 승인한 유일한 화면 자료, spec 4.3 과 어긋남 | 높음 |
| 3 | PC 배치 질문 | 맞음. 시안은 휴대폰만, PC 는 미정 | 높음 |
| 4 | 재작업 순서 | 맞음. A5·E19 재측정 필요 | 높음 |

## 고쳐야 할 것
| # | 중요도 | 무엇을 | 왜 | 어떻게 확인 |
|---|---|---|---|---|
| 1 | 권고 | 원인 한 줄(spec 4.3 기준이 원본 백테스터, 그림은 기준에 안 들어감, 구현은 spec 을 따름) | 사용자가 어긋난 곳을 알고 고르게 | 본문 |
| 2 | 권고 | 숨김 시 운영자도 못 봄 명시 | 허용 목록 1계정 | .v2_allowlist |
| 3 | 권고 | UA 세부 확인 뒤 기재 | Fable 출력엔 세부 없음 | access.log UA |
| 4 | 권고 | 백테스터 통합·A5·E19 재측정·통보 문안 A 를 계획 항목에 | 구조 변경 영향 | 계획 목차 |
| 5 | 권고 | 숨김 실행 시 따로 실행 질의, wc -c = 0·api 403 확인 | 2-10 절차 | 출력 |

## 사용자에게 물어야 할 것
- 없음

## PO 처리
- 권고 1·2 는 결정 요청 본문에. 권고 3: access.log UA 전체 `Macintosh; Intel Mac OS X 10_15_7 … Chrome/155.0.0.0` 를 PO 가 직접 봤음(18:26:49 줄) — 사실 2 그대로 유지. 권고 4·5 는 계획·실행 단계에.
