# 질의: 투자자 Ver8 확인 질문 PDF(1111-01)를 만들었고, 사용자 발송과 1111-02·1111-03 기록 커밋·push 를 요청하려 한다

**지금 단계:** 리뷰
**다음에 하려는 일:** (1) 사용자에게 PDF 발송을 요청한다(외부 발송은 사용자가 함). (2) 사용자 승인 뒤 한 커밋으로 묶어 커밋·push 한다: 시험 경로 고침 3파일(1111-02), 사용자가 옮긴 docs/new-version 파일 18개(이름 바꿈) + 새 파일(ver8 4개·claim/ver2 그림 1개), 질문 HTML·PDF, investor-notice-log #13(1111-03), HANDOFF 3행, 이 질의 파일, `pages/dashboard.py` 버전 갱신. 서버 배포 없음(문서·시험만). 작은 문서 변경은 이 질의서에 묶었다.

## 지금까지 확인한 사실
| # | 사실 | 확인/추정 | 근거 |
|---|---|---|---|
| 1 | Ver8 의 현물 `simulate()` 함수는 Ver2 와 글자 단위로 같다 | 확인 | 두 파일에서 `function simulate(`~함수 끝을 잘라 diff → 차이 없음 |
| 2 | Ver8 새 기능: 바이낸스 선물 롱+숏 백테스트(방식 A·B·C, 펀딩비, 레버리지 1, 강제청산 미계산), 스윕 둔화 허용치 축·값별 분석표·최대 5000조합, 차트 전체화면·드래그·라벨 밀도 | 확인 | diff 1,112줄 |
| 3 | Ver8 기본값: maxSplits 5→1, tp 1.0→3, sl 1.5→3, 스윕 범위 변경 | 확인 | diff 92·94·95행 |
| 4 | 60선 최소 기울기·둔화 허용치 필터는 Ver2 에 이미 있고 엔진·앱에 들어가 있다 | 확인 | core/strategy_pullback.py:949-959, v2/params_schema.py:27 |
| 5 | Ver8 에는 추적 손절(1110-01)이 없다. 앱 백테스터는 Ver2 원문 + 패치 3곳으로 생성된다 | 확인 | grep 0건 / v2/static/backtester.js 14건, tests/v2/js/ver2_source.mjs |
| 6 | (2회째 고침) 업비트에는 코인을 빌려서 파는 「코인빌리기」가 있다. 선물이 없다는 공식 문구는 찾지 못했다. 봇이 연결된 업비트 계좌는 현물 매매만 한다 | 확인(코인빌리기) / 미확인(선물 없음 공식 문구) | https://www.upbit.com/lending (11/11 18시대 직접 읽음). 처음 적은 「선물·공매도 미지원」 2차 출처 단정은 Fable 1회째 막음으로 고침 |
| 7 | 수익률 그림에는 종목·기간·봉 단위·현물/선물이 없다. 파일 이름은 20261105 | 확인 | docs/new-version/ver8/20261105-ver8-수익률.jpeg |
| 8 | PDF 1쪽, 나눔고딕 3종 emb=yes sub=yes, 150dpi 아닌 110dpi 렌더에서 글자 모두 보임 | 확인 | pdfinfo Pages 1, pdffonts, pdftoppm 그림 직접 열어 봄 |
| 9 | 시험 경로 3곳 고친 뒤 게이트 rc=0: 회귀 1472/1472, JS 199/199, 바깥 연결 0 | 확인 | scratchpad gate-1111.log |
| 10 | 사용자가 Ver2 원문 등 18개를 하위 폴더로 옮겼고 내용은 같다(해시 18/18 일치). 옮긴 것을 커밋하지 않으면 깨끗한 저장소에서 시험이 새 경로 파일을 못 찾는다 | 확인(앞) / 추정(뒤) | git hash-object 대조 |
| 11 | 저장소는 공개(PUBLIC)이다. Ver2 원문·이전 질문 PDF 도 이미 공개 커밋돼 있다 | 확인 | gh repo view, git log |
| 12 | `v2/params_schema.py:4` 주석의 옛 경로는 실행 파일이라 고치지 않았다 | 확인 | 결정: 배포 대상 diff 를 만들지 않으려 함 |
| 13 | 투자자 연락 원칙: 클레임 답변·체감 변경 통보만. 이번 질문은 투자자 요청 자료에 대한 범위 확인(11/05 #9 와 같은 유형) | 확인 | project-rules 「투자자 연락 원칙」, notice-log #9 |
| 14 | 1111-03 투자자 답변(로그 자동 갱신 없음, 단추로 다시 불러옴)은 사용자가 보냈고 notice-log #13 에 적었다 | 확인 | 사용자 「1111-03 보냄」 |

## 물어볼 것
| # | 질문 | PO의 생각 |
|---|---|---|
| 1 | PDF 내용에 사실 오류·과장·약속(승인 안 된 일)이 있는가? | 「업비트 선물 없음」은 2차 출처라 단정 표현이 걱정이다. 숏 실매매는 「먼저 검토 결과를 알려 드림」으로만 약속했다 |
| 2 | 질문 1 선택지 ②(숏 실매매)를 넣는 것이 맞는가, 아니면 빼고 「업비트로 불가」만 알리는 것이 맞는가? | 투자자 뜻을 듣는 것이 목적이라 넣되 검토가 먼저라고 적었다 |
| 3 | 사용자가 옮긴 파일과 투자자 Ver8 자료를 공개 저장소에 커밋하는 것이 맞는가? | Ver2 선례가 있어 넣는다. 개인정보·키는 없다(그림은 백테스트 표뿐) |
| 4 | 커밋에 dashboard 버전 갱신을 넣는 것이 맞는가? (메모리는 문서 전용 커밋 생략, HANDOFF 는 10/26 Fable 정정으로 문서도 갱신) | HANDOFF 규칙을 따라 갱신한다 |

## 참고 파일
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/new-version/ver8/investor-questions-20261111.html
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/new-version/ver8/investor-questions-20261111.pdf
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/new-version/ver8/MA_GC_Pullback_Backtester_2611111144(Ver8).html
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/new-version/ver2/MA_GC_Pullback_Backtester_2611051030(Ver2).html
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/new-version/ver8/20261105-ver8-수익률.jpeg
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/operations/investor-notice-log.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/docs/specs/v2-dashboard/HANDOFF.md (0-1 표 맨 위 3행)
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/.claude/context/project-rules.md
- /Users/gonnim/Project-MVP/Source/upbit-tradebot-mvp/CLAUDE.md
- 시험 경로 변경: tests/v2/js/fixtures/ver2_patches.json, tests/v2/test_api_write.py, tests/fixtures/pullback/cfgs.json (`git diff tests`)

---

## Fable 답변서 전문 (1회째)

**판정:** 수정 후 진행
**이유:** PDF 의 「업비트에는 선물과 공매도가 없습니다. 숏 매매는 지금의 업비트 계좌로는 할 수 없습니다」는 업비트 공식 페이지와 맞지 않습니다. 업비트는 코인을 빌려서 파는 「코인빌리기」를 지금 운영합니다. 커밋 쪽에도 옮긴 파일 1개가 `.gitignore` 에 걸려 빠지는 문제와 새 그림 개수 차이가 있습니다. 모두 po가 고칠 수 있습니다.

질문별 답(요지): 1 사실 오류 1곳(질문 1 첫 두 문장, https://www.upbit.com/lending · https://support.upbit.com/hc/ko/articles/47895894857881), 나머지 사실은 직접 확인함, 과장·승인 안 된 약속 없음(높음). 2 선택지 ② 넣는 것이 맞음, 「바이낸스 선물 계좌를 새로 연결해야」는 「Ver8 과 같은 방식으로 하려면」으로 좁힘(높음). 3 공개 커밋 방향은 맞으나 `ver2/20261105-ver2.txt` 가 `.gitignore:38 *.txt` 에 걸림, claim/ver2 새 그림은 2개, 그중 1장은 투자자 실계좌 로그 화면(높음). 4 dashboard 버전 갱신은 넣지 않는 것이 맞음 — 메모리 규칙(문서·시험은 생략)과 최근 문서·시험 커밋 018d207·968c05d·5376e4c 관행, 「10/26 Fable 정정」 줄은 HANDOFF 에서 찾지 못함(보통).

고쳐야 할 것: 1 막음 질문 1 문장 고침 + HANDOFF 1111-01·사실 6 고침 · 2 막음 코인빌리기에 대해 확인 못 한 것(JTO 가능 여부·Open API)을 사실처럼 쓰지 않음 · 3 막음 `git add -f` 로 txt 넣고 18개가 이름 바꿈(R)으로 잡히는지 확인 · 4 막음 새 그림 2개와 그중 실계좌 로그 화면을 승인 요청에 적음 · 5 막음 dashboard 버전 갱신 뺌 · 6 권고 backtester.js trail 8건, PDF 에 AppleSDGothicNeo 2종도 있음 · 7 권고 발송 뒤 notice-log #14, 커밋에는 「발송 전」 · 8 권고 사실 10 뒷부분은 추정 유지.
사용자에게 물어야 할 것: 커밋 승인 요청에 「투자자 휴대폰 로그 화면 1장과 버튼 크기 화면 1장이 공개 저장소에 올라감」을 적고 함께 승인받음.

## 고친 것 (2회째 질의)

| # | 지적 | 고친 것 | 확인 |
|---|---|---|---|
| 1·2 | 질문 1 문장 | 「Ver8 의 숏은 바이낸스 선물 기준입니다. 지금 봇이 연결된 업비트 계좌는 현물 매매만 합니다. 그래서 Ver8 과 같은 방식의 숏은 지금 계좌로는 할 수 없습니다. Ver8 과 같은 방식으로 하려면 바이낸스 선물 계좌를 새로 연결해야 하고, 거래소·자금(USDT)·이용 조건을 먼저 검토해야 합니다. 업비트에도 코인을 빌려서 파는 「코인빌리기」가 있지만, 이용 기간(최대 30일)·수수료·자격 요건 등 방식과 조건이 달라 따로 검토해야 합니다.」 JTO 가능 여부·API 는 쓰지 않음. HANDOFF 1111-01 행도 같은 뜻으로 고침 | PO 가 https://www.upbit.com/lending 을 직접 읽음(11/11 18시대, 최대 30일·일 0.05%·자격 요건 확인). PDF 다시 만듦: 1쪽, 글꼴 5종 모두 emb·sub yes, 렌더 그림 직접 봄, sha256 앞 16자 b8c8e71c20191736 |
| 3 | txt 무시됨 | 커밋 때 `git add -f docs/new-version/ver2/20261105-ver2.txt`, 커밋 전 `git status` 로 18개 R 확인 | `git check-ignore -v` → `.gitignore:38:*.txt` 확인 |
| 4 | 새 그림 | 사용자가 세션 중 claim/ver2 를 20261106/·20261111/ 하위 폴더로 다시 나눔. 새 그림 2개(20261106-01-Button-Size-Character.jpeg, 20261111-01-로그-Check.jpeg = 투자자 실계좌 로그 화면)를 승인 요청에 적음 | `git status --short --untracked-files=all docs/new-version` |
| 5 | 버전 | dashboard.py 버전 갱신 뺌 | — |
| 6 | 숫자 | 사실 5 의 14건 → `grep -ci trail` 8건(앞 숫자는 다른 낱말 묶음), 사실 8 글꼴 5종 | 다시 실행 |
| 7 | notice-log | 발송 뒤 #14 기록, 이번 커밋에는 넣지 않음 | — |

다음에 하려는 일(바뀐 것): 사용자에게 PDF 발송 요청 + 커밋 승인 요청(공개 저장소에 투자자 로그 화면·버튼 크기 화면 올라감 명시, 버전 갱신 없음, 배포 없음).


## Fable 답변서 요지 (2회째)

**판정:** 진행
**이유:** 1회째 막음 5건이 모두 반영된 것을 직접 확인했습니다. 남은 것은 권고뿐입니다.
- 질문 1~4: 사실 오류·과장·승인 안 된 약속 없음, PDF 1쪽·글꼴 5종 포함·렌더 확인·sha256 b8c8e71c20191736 일치, 선택지 ② 유지 맞음, 공개 커밋 맞음(커밋 직전 확인 필요), 버전 갱신 뺀 것 맞음(모두 높음).
- 권고 1: 커밋 직전 git status 에서 R 18줄·새 파일을 세고 git diff --staged 를 자격증명 시그니처로 검사, 명령을 ; 로 묶지 않음. 권고 2: 사실 6 줄 고침(반영함). 권고 3: 발송 뒤 notice-log #14 에 sha256 과 수정 여부 기록.
- 사용자에게 물어야 할 것: 없음(커밋 승인 요청에 투자자 로그 화면·버튼 크기 화면 공개 사실 적기 유지).
