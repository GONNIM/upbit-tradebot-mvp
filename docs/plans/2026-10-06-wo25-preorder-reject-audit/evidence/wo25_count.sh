#!/bin/bash
# WO-25 조사 A (서버, 읽기 전용): BUY 평가 통과 뒤 발주 전 차단 분기의 실제 발생 건수 (journal, 10-02 이후)
S0="${1:-2026-10-02 00:00:00}"
R=/root/upbit-tradebot-mvp
D="file:$R/services/data/tradebot_mcmax33.db?mode=ro"
JF=$(mktemp -p /dev/shm)
journalctl -u tradebot --since "$S0" --no-pager -o short-iso | grep -vF "fragment with id" | sed -E 's/^.*(python|streamlit)\[[0-9]+\]: //' > "$JF"
C() { grep -cF -- "$1" "$JF"; }
echo "== 창: $S0 ~ $(date '+%F %T') | journal 첫 줄: $(head -1 "$JF" | cut -c1-19) | 줄 수 $(wc -l < "$JF")"
echo "== 코드 존재 확인 (서버 파일)"
for s in "[PAUSE] 실주문 스킵" "주문 진행 중 → 매수 액션 대기" "[POLLUTED] 지표 오염 상태" "이미 포지션 보유 중 → BUY 무시" "[PENDING-REGISTER] 매수 지연 등록" "[PENDING-EXPIRE]" "[PENDING-RESOLVE] 유효성 불성립"; do
  echo "   '$s' core/strategy_engine.py: $(grep -cF -- "$s" $R/core/strategy_engine.py)"
done
for s in "호가 라운딩 실패" "호가 라운딩 비정상" "활성 KRW 잔고 0" "[BUY-LIMIT] {err}" "계산된 수량 0" "[BUY] 주문 불가: 잔고=" "[BUY] 실거래 최소 주문금액 미만" "잔고 부족 중단"; do
  echo "   '$s' core/trader.py: $(grep -cF -- "$s" $R/core/trader.py)"
done
echo "== journal 건수"
for s in "EMA Buy Signal" "action=BUY" "[PAUSE] 실주문 스킵 (감사로그·지표는 유지) | action=BUY" "주문 진행 중 → 매수 액션 대기" "[POLLUTED] 지표 오염 상태" "이미 포지션 보유 중 → BUY 무시" "[PENDING-REGISTER] 매수 지연 등록" "[PENDING-EXPIRE]" "[PENDING-RESOLVE] 유효성 불성립" "[BUY-LIMIT] 호가 라운딩 실패" "[BUY-LIMIT] 호가 라운딩 비정상" "[BUY-LIMIT] 활성 KRW 잔고 0" "[BUY-LIMIT] 활성 KRW 부족" "[BUY-LIMIT] 계산된 수량 0" "[BUY] 주문 불가: 잔고=" "[BUY] 실거래 최소 주문금액 미만" "잔고 부족 중단" "[BUY-LIMIT] plan" "[BUY] plan" "❌ BUY 실패" "[DRY-RUN] buy_"; do
  echo "   '$s': $(C "$s")"
done
echo "== 발생 줄 (차단 분기)"
grep -E "실주문 스킵 .*action=BUY|주문 진행 중 → 매수 액션 대기|POLLUTED\] 지표 오염|이미 포지션 보유 중 → BUY 무시|PENDING-EXPIRE|유효성 불성립|호가 라운딩|활성 KRW 잔고 0|BUY-LIMIT\] 활성 KRW 부족|계산된 수량 0|\[BUY\] 주문 불가|최소 주문금액 미만|잔고 부족 중단|❌ BUY 실패" "$JF" | cut -c1-230 | head -40
echo "== audit_buy_eval 통과 행 (KRW-JTO, 실시간, $S0 이후)"
sqlite3 "$D" "SELECT COUNT(*) FROM audit_buy_eval WHERE ticker='KRW-JTO' AND overall_ok=1 AND timestamp >= '${S0/ /T}';"
sqlite3 "$D" "SELECT id, bar_time, timestamp FROM audit_buy_eval WHERE ticker='KRW-JTO' AND overall_ok=1 AND timestamp >= '${S0/ /T}' ORDER BY id;"
echo "== audit_trades BUY_REJECTED ($S0 이후)"
sqlite3 "$D" "SELECT id, timestamp, ticker, reason FROM audit_trades WHERE type='BUY_REJECTED' AND timestamp >= '${S0/ /T}' ORDER BY id;"
echo "== audit_buy_eval blocked 주석 (state_polluted 등)"
sqlite3 "$D" "PRAGMA table_info(audit_buy_eval);" | grep -iE 'block|wo2|validation' | head
rm -f "$JF"
