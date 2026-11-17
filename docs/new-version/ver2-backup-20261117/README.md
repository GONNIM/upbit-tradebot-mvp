# Ver2 백테스터 화면 · 소스 백업 (2026-11-17)

사용자 지시(11/17): 「1111-01 승인 단, Ver2 화면 및 소스는 백업해 두시오.」

1111-01(투자자 Ver9 반영)으로 대시보드 백테스터의 기준 원문을 Ver2 → Ver9 로 바꾸기 **직전** 상태다.
기준 커밋: `57e3d56` (서버 배포본 `4ad9a68` · v1.2026.11.12.1728 과 v2/static 이 같음 — 그 뒤 커밋은 문서만).

## 들어 있는 것
| 파일 | 원래 자리 | sha256 |
|---|---|---|
| v2-static/backtester.html | v2/static/backtester.html | 443fe40f04bb1b4a30817ebbad5ce9dbcbfce8c9f4b0fbc145f03a82ccb021cd |
| v2-static/backtester.js | v2/static/backtester.js | e6e96aa09f41b2eec45c59eb6a05e11445495492b8dd22ae2961bcd7f23e0bb4 |
| v2-static/bt_ui.js | v2/static/bt_ui.js | 77f8d2db7dc4afb5634a7191e1ed202d5612f151621d0d472c8f132027d34ad2 |
| v2-static/save.js | v2/static/save.js | 2dd50860a6594c3f63ab2be7cdcc862573191a3151e6745eeebf216c70cdfd11 |
| fixtures/ver2_patches.json | tests/v2/js/fixtures/ver2_patches.json | e16c401416ff3b5e0475b50779003c82741952b4350e4168e98c4d8635155e1d |

- 투자자 Ver2 원본은 그대로 `docs/new-version/ver2/MA_GC_Pullback_Backtester_2611051030(Ver2).html` 에 있다(sha256 dbe285f8…ae8, 이번에 바꾸지 않음).
- 나머지 v2/static 파일(app.js · style.css · chart.js 등)은 이번 변경 대상이 아니라 넣지 않았다. 전체가 필요하면 `git show 57e3d56:<경로>`.

## 되돌리는 방법
1. 이 폴더의 v2-static 4개를 v2/static/ 에, fixtures/ver2_patches.json 을 tests/v2/js/fixtures/ 에 복사한다(또는 1111-01 구현 커밋을 `git revert`).
2. 시험 기준값까지 되돌리려면 `git revert` 를 쓴다(tests/v2/js 의 기준값 45개 · 시험 고침이 함께 돌아감).
3. 서버: pull → tradebot-v2 만 재시작 → 엔진(tradebot) 기동 시각 그대로인지 확인.
