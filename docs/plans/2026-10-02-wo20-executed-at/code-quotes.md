# WO-20 코드 인용 (HEAD e444114, 서버 HEAD 786b5cb 와 엔진 코드 동일)

## A1. orders.executed_at 를 쓰는 코드

### services/db.py:109-165 — insert_order: executed_at 인자 → INSERT (기본값 None)
```python
  109  def insert_order(
  110      user_id,
  111      ticker,
  112      side,
  113      price,
  114      volume,
  115      status,
  116      current_krw=None,
  117      current_coin=None,
  118      profit_krw=None,
  119      *,
  120      provider_uuid: str | None = None,
  121      state: str | None = None,
  122      requested_at: str | None = None,
  123      executed_at: str | None = None,
  124      canceled_at: str | None = None,
  125      executed_volume: float | None = None,
  126      avg_price: float | None = None,
  127      paid_fee: float | None = None,
  128      entry_bar: int | None = None,  # ✅ bars_held 추적용
  129      meta: str | None = None,  # ✅ 전략 컨텍스트 (JSON)
  130      settings_history_id: int | None = None,  # ✅ P1 — 거래 → 설정 라벨링
  131  ):
  132      ensure_schema(user_id)
  133      with get_db(user_id) as conn:
  134          cursor = conn.cursor()
  135          cursor.execute(
  136              """
  137              INSERT INTO orders (
  138                  user_id, timestamp, ticker, side, price, volume, status,
  139                  current_krw, current_coin, profit_krw,
  140                  provider_uuid, state, requested_at, executed_at, canceled_at,
  141                  executed_volume, avg_price, paid_fee, updated_at, entry_bar, meta,
  142                  settings_history_id
  143              )
  144              VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
  145              """,
  146              (
  147                  user_id,
  148                  now_kst(),
  149                  ticker,
  150                  side,
  151                  price,
  152                  volume,
  153                  status,
  154                  current_krw,
  155                  current_coin,
  156                  profit_krw,
  157                  provider_uuid,
  158                  state,
  159                  requested_at or (now_kst() if state == "REQUESTED" else None),
  160                  executed_at,
  161                  canceled_at,
  162                  executed_volume,
  163                  avg_price,
  164                  paid_fee,
  165                  now_kst(),
```

### services/db.py:2064-2100 — update_order_progress: executed_at = COALESCE(executed_at, ?) (기본값 None)
```python
 2064  def update_order_progress(
 2065      user_id: str,
 2066      provider_uuid: str,
 2067      *,
 2068      executed_volume: float,
 2069      avg_price: float | None,
 2070      paid_fee: float | None,
 2071      state: str,                # 'PARTIALLY_FILLED' 등
 2072      executed_at: str | None = None,
 2073  ):
 2074      """
 2075      부분체결 진행 상황 갱신. 누적 수량·평단·수수료·상태·시각 업데이트.
 2076      """
 2077      ensure_schema(user_id)
 2078      with get_db(user_id) as conn:
 2079          cur = conn.cursor()
 2080          cur.execute("""
 2081              UPDATE orders
 2082              SET executed_volume = ?,
 2083                  avg_price = ?,
 2084                  paid_fee = ?,
 2085                  state = ?,
 2086                  executed_at = COALESCE(executed_at, ?),
 2087                  updated_at = ?
 2088              WHERE user_id = ? AND provider_uuid = ?
 2089          """, (
 2090              executed_volume,
 2091              avg_price,
 2092              paid_fee,
 2093              state,
 2094              executed_at,
 2095              now_kst(),
 2096              user_id,
 2097              provider_uuid
 2098          ))
 2099          conn.commit()
 2100  
```

### services/db.py:2103-2146 — update_order_completed: executed_at = COALESCE(executed_at, ?) (기본값 None)
```python
 2103      user_id: str,
 2104      provider_uuid: str,
 2105      *,
 2106      final_state: str,       # 'FILLED' | 'CANCELED' | 'REJECTED'
 2107      executed_volume: float | None = None,
 2108      avg_price: float | None = None,
 2109      paid_fee: float | None = None,
 2110      executed_at: str | None = None,
 2111      canceled_at: str | None = None,
 2112      current_krw: float | None = None,  # ✅ 체결 후 잔고 (대시보드 표시용)
 2113      current_coin: float | None = None,  # ✅ 체결 후 코인 보유량 (대시보드 표시용)
 2114  ):
 2115      """
 2116      최종 완료/취소/거절로 전환. 필요 시 누적치도 함께 덮어씀.
 2117      """
 2118      ensure_schema(user_id)
 2119      with get_db(user_id) as conn:
 2120          cur = conn.cursor()
 2121          cur.execute("""
 2122              UPDATE orders
 2123              SET state = ?,
 2124                  executed_volume = COALESCE(?, executed_volume),
 2125                  avg_price       = COALESCE(?, avg_price),
 2126                  paid_fee        = COALESCE(?, paid_fee),
 2127                  executed_at     = COALESCE(executed_at, ?),
 2128                  canceled_at     = COALESCE(canceled_at, ?),
 2129                  current_krw     = COALESCE(?, current_krw),
 2130                  current_coin    = COALESCE(?, current_coin),
 2131                  updated_at      = ?
 2132              WHERE user_id = ? AND provider_uuid = ?
 2133          """, (
 2134              final_state,
 2135              executed_volume,
 2136              avg_price,
 2137              paid_fee,
 2138              executed_at,
 2139              canceled_at,
 2140              current_krw,
 2141              current_coin,
 2142              now_kst(),
 2143              user_id,
 2144              provider_uuid
 2145          ))
 2146          conn.commit()
```

### services/init_db.py:485-490 — 열 추가 마이그레이션
```python
  485      _safe_alter(conn, "ALTER TABLE orders ADD COLUMN avg_price REAL")
  486      _safe_alter(conn, "ALTER TABLE orders ADD COLUMN paid_fee REAL")
  487      _safe_alter(conn, "ALTER TABLE orders ADD COLUMN requested_at TEXT")
  488      _safe_alter(conn, "ALTER TABLE orders ADD COLUMN executed_at TEXT")
  489      _safe_alter(conn, "ALTER TABLE orders ADD COLUMN canceled_at TEXT")
  490      _safe_alter(conn, "ALTER TABLE orders ADD COLUMN updated_at TEXT")
```

## A2. 체결 확인 경로

### core/trader.py:566-580 — TEST 시장가 매수: insert_order(status='completed'), state·executed_at 없음
```python
  566              entry_bar = (meta or {}).get("bar") if meta else None
  567  
  568              insert_order(
  569                  self.user_id,
  570                  ticker,
  571                  "BUY",
  572                  price,
  573                  qty,
  574                  "completed",
  575                  current_krw=new_krw,
  576                  current_coin=new_coin,
  577                  profit_krw=0,
  578                  entry_bar=entry_bar,  # ✅ bars_held 추적용
  579                  settings_history_id=self._get_settings_history_id(),  # ✅ P1
  580              )
```

### core/trader.py:779-792 — LIVE 시장가 매수: insert_order(state='REQUESTED', requested_at=now), executed_at 없음
```python
  779              insert_order(
  780                  self.user_id,
  781                  ticker,
  782                  "BUY",
  783                  price,
  784                  0,
  785                  "requested",
  786                  provider_uuid=uuid,
  787                  state="REQUESTED",
  788                  requested_at=now_kst(),
  789                  entry_bar=entry_bar,  # ✅ bars_held 추적용
  790                  meta=meta_json,  # ✅ 전략 컨텍스트 저장
  791                  settings_history_id=self._get_settings_history_id(),  # ✅ P1
  792              )
```

### core/trader.py:1082-1092 — LIVE 지정가(현재가) 매수: insert_order(state='REQUESTED'), executed_at 없음
```python
 1082              insert_order(
 1083                  self.user_id, ticker, "BUY",
 1084                  rounded_price, 0, "requested",
 1085                  provider_uuid=uuid,
 1086                  state="REQUESTED",
 1087                  requested_at=now_kst(),
 1088                  entry_bar=enriched_meta.get("bar"),
 1089                  meta=meta_json,
 1090                  settings_history_id=self._get_settings_history_id(),  # ✅ P1
 1091              )
 1092  
```

### core/trader.py:1201-1213 — TEST 시장가 매도: insert_order(status='completed')
```python
 1201              insert_order(
 1202                  self.user_id,
 1203                  ticker,
 1204                  "SELL",
 1205                  price,
 1206                  qty,
 1207                  "completed",
 1208                  current_krw=new_krw,
 1209                  current_coin=new_coin,
 1210                  profit_krw=total_gain,
 1211                  settings_history_id=self._get_settings_history_id(),  # ✅ P1
 1212              )
 1213  
```

### core/trader.py:1335-1348 — LIVE 시장가 매도: insert_order(state='REQUESTED')
```python
 1335              insert_order(
 1336                  self.user_id,
 1337                  ticker,
 1338                  "SELL",
 1339                  price,
 1340                  qty,
 1341                  "requested",
 1342                  provider_uuid=uuid,
 1343                  state="REQUESTED",
 1344                  requested_at=now_kst(),
 1345                  meta=meta_json,  # ✅ 전략 컨텍스트 저장
 1346                  settings_history_id=self._get_settings_history_id(),  # ✅ P1
 1347              )
 1348  
```

### engine/order_reconciler.py:239-323 — 체결 처리: wait → progress, done/cancel → finalize. exec_ts_iso 는 fill callback 에만 전달
```python
  239          state = info.get("state") # 'wait', 'done', 'cancel'
  240          trades = info.get("trades") or []
  241          avg_price = float(info.get("avg_price") or 0.0)
  242          exec_volume = float(info.get("executed_volume") or 0.0)
  243          paid_fee = float(info.get("paid_fee") or 0.0)
  244  
  245          logger.debug(
  246              f"[OR] handle uuid={uuid} state={state} exec_vol={exec_volume} "
  247              f"avg={avg_price} fee={paid_fee}"
  248          )
  249  
  250          if (not avg_price or not exec_volume) and trades:
  251              total_funds = sum(float(t.get("funds") or 0.0) for t in trades)
  252              total_vol = sum(float(t.get("volume") or 0.0) for t in trades)
  253              avg_price = (total_funds / total_vol) if total_vol > 0 else 0.0
  254              paid_fee = sum(float(t.get("fee") or 0.0) for t in trades)
  255              exec_volume = total_vol
  256  
  257          with self._lock:
  258              meta = self._pending.get(uuid)
  259  
  260          if not meta:
  261              return
  262  
  263          user_id = meta["user_id"]
  264          ticker = meta["ticker"]
  265          side = meta["side"]
  266  
  267          # 🔹 진행 중 (부분체결 포함)
  268          if state in ("wait",):
  269              # exec_volume > 0이면 PARTIALLY_FILLED, 0이면 REQUESTED 유지
  270              db_state = "PARTIALLY_FILLED" if exec_volume > 0 else "REQUESTED"
  271              self._update_order_progress(
  272                  uuid=uuid,
  273                  user_id=user_id,
  274                  ticker=ticker,
  275                  side=side,
  276                  exec_vol=exec_volume,
  277                  avg_px=avg_price,
  278                  fee=paid_fee,
  279                  state=db_state
  280              )
  281              # ✅ 고정가 매수 timeout 체크 — 봉 간격 초과 미체결 자동 cancel
  282              self._maybe_cancel_fixed_price_buy(uuid)
  283              return
  284  
  285          # 🔹 최종 상태
  286          if state in ("done", "cancel"):
  287              if state == "done":
  288                  db_state = "FILLED" if exec_volume > 0 else "CANCELED"
  289              else:  # 'cancel'
  290                  db_state = "CANCELED"
  291  
  292              self._finalize_order(
  293                  uuid=uuid,
  294                  user_id=user_id,
  295                  ticker=ticker,
  296                  side=side,
  297                  exec_vol=exec_volume,
  298                  avg_px=avg_price,
  299                  fee=paid_fee,
  300                  state=db_state
  301              )
  302  
  303              # ✅ SP-PI-2: LIMIT BUY 전량 체결(FILLED) 감지 시 fill callback 발화
  304              # D6 결정: 부분 체결(CANCELED + exec_vol > 0)은 처리하지 않음. FILLED 만 대상.
  305              if db_state == "FILLED" and side == "BUY" and exec_volume > 0 and avg_price > 0:
  306                  # 최종 체결 시각: trades 최상단(가장 최근) 또는 order created_at fallback
  307                  exec_ts_iso = None
  308                  if trades:
  309                      try:
  310                          exec_ts_iso = trades[-1].get("created_at") or trades[0].get("created_at")
  311                      except Exception:
  312                          exec_ts_iso = None
  313                  if not exec_ts_iso:
  314                      exec_ts_iso = info.get("created_at")
  315                  self._fire_fill_callback(
  316                      user_id=user_id, ticker=ticker, uuid=uuid,
  317                      exec_price=avg_price, exec_qty=exec_volume,
  318                      exec_ts_iso=exec_ts_iso,
  319                  )
  320  
  321              with self._lock:
  322                  self._pending.pop(uuid, None)
  323  
```

### engine/order_reconciler.py:324-345 — _update_order_progress: executed_at 미전달
```python
  324      def _update_order_progress(self, uuid, user_id, ticker, side, exec_vol, avg_px, fee, state):
  325          """
  326          부분체결 진행 상황을 orders 테이블에 반영.
  327          - state: 'REQUESTED' | 'PARTIALLY_FILLED'
  328          """
  329          try:
  330              update_order_progress(
  331                  user_id,
  332                  uuid,
  333                  executed_volume=exec_vol,
  334                  avg_price=avg_px or None,
  335                  paid_fee=fee or None,
  336                  state=state
  337              )
  338              logger.info(
  339                  f"[OR] progress uuid={uuid} user={user_id} side={side} "
  340                  f"vol={exec_vol} avg={avg_px} fee={fee} state={state}"
  341              )
  342          except Exception as e:
  343              logger.warning(f"[OR] progress update failed uuid={uuid}: {e}")
  344  
  345      def _finalize_order(self, uuid, user_id, ticker, side, exec_vol, avg_px, fee, state):
```

### engine/order_reconciler.py:346-385 — _finalize_order: update_order_completed 에 executed_at 미전달
```python
  346          """
  347          최종 체결/취소 결과를 orders 테이블에 반영.
  348          - state: 'FILLED' | 'CANCELED' | (필요 시 'REJECTED' 등 확장)
  349          """
  350          try:
  351              # ✅ 잔고 조회 (대시보드 표시용 current_krw, current_coin 저장)
  352              balances = self.upbit.get_balances()
  353  
  354              # ✅ KRW 잔고 추출
  355              current_krw = None
  356              for bal in balances:
  357                  if bal.get("currency", "").upper() == "KRW":
  358                      current_krw = float(bal.get("balance", 0.0))
  359                      break
  360  
  361              # ✅ 해당 ticker의 코인 보유량 추출 (예: KRW-BTC → BTC)
  362              current_coin = None
  363              coin_currency = ticker.split("-")[-1].upper() if "-" in ticker else None
  364              if coin_currency:
  365                  for bal in balances:
  366                      if bal.get("currency", "").upper() == coin_currency:
  367                          current_coin = float(bal.get("balance", 0.0))
  368                          break
  369  
  370              update_order_completed(
  371                  user_id,
  372                  uuid,
  373                  final_state=state,
  374                  executed_volume=exec_vol,
  375                  avg_price=avg_px or None,
  376                  paid_fee=fee or None,
  377                  current_krw=current_krw,  # ✅ 체결 후 KRW 잔고
  378                  current_coin=current_coin,  # ✅ 체결 후 코인 보유량
  379              )
  380              logger.info(
  381                  f"[OR] final {state} uuid={uuid} user={user_id} side={side} "
  382                  f"vol={exec_vol} avg={avg_px} fee={fee} krw={current_krw} coin={current_coin}"
  383              )
  384  
  385              # ✅ LIVE 모드 체결 로그 기록
```

### services/trading_control.py:300-325 — 강제 매수: trader.buy_limit / buy_market 위임
```python
  300              f"🎯 [FIXED-PRICE][FORCE] 고정가 강제 매수 진입 | "
  301              f"price={price:.2f} ticker={ticker} "
  302              f"wait_bars={wait_bars} effective_timeout≈{effective_interval_sec-5}s"
  303          )
  304          # ✅ WO-8b 원자화 (2026-09-18): 발주-등록 경합 봉쇄.
  305          # buy_limit + _pending_buy_uuid 등록을 engine._execution_lock 아래에서 원자적으로 수행.
  306          # reconciler 순회의 fill callback 은 이 락 획득까지 대기 → uuid 매칭 성공 보장.
  307          try:
  308              from core.strategy_engine import execute_force_buy_limit_atomic
  309              result = execute_force_buy_limit_atomic(
  310                  user_id=user_id, ticker=ticker, trader=trader,
  311                  price=price, ts=ts, meta=meta,
  312                  interval_sec=effective_interval_sec, wait_bars=wait_bars,
  313              )
  314          except Exception as e:
  315              logger.warning(f"[FORCE-BUY-ATOMIC] 원자화 헬퍼 실패 → 폴백 buy_limit: {e}")
  316              result = trader.buy_limit(
  317                  price, ticker,
  318                  ts=ts, meta=meta,
  319                  interval_sec=effective_interval_sec,
  320              )
  321      else:
  322          result = trader.buy_market(price, ticker, ts=ts, meta=meta)
  323      if not result:
  324          reason = getattr(trader, "last_buy_error", None)
  325          if reason:
```

### services/trading_control.py:360-369 — 강제 매수: reconciler.enqueue → 위 OR 경로로 확정
```python
  360          "BUY",
  361          f"🚨 [LIVE] 강제매수 요청 전송: {ticker} 시장가, 예상가≈{price:,.2f} KRW "
  362          f"(사용 KRW ≈ {used_krw:,.0f}, uuid={uuid})",
  363      )
  364  
  365      try:
  366          get_reconciler().enqueue(uuid, user_id=user_id, ticker=ticker, side="BUY", meta=meta)
  367      except Exception as e:
  368          insert_log(user_id, "ERROR", f"⚠️ 강제매수 reconciler enqueue 실패: {e}")
  369  
```

### core/strategy_engine.py:326-363 — LIMIT 체결 callback: entry_ts=executed_ts 를 메모리 포지션에만 반영 (orders 미기록)
```python
  326          """
  327          ✅ SP-PI-2: OrderReconciler → StrategyEngine fill callback.
  328  
  329          LIMIT BUY 전량 체결(FILLED) 시 OrderReconciler 스레드에서 호출.
  330          _pending_buy_uuid 와 일치하는 경우에만 apply_entry(source="bot_limit_fill")
  331          발동. buy_market 등 다른 경로의 uuid 는 자동 스킵.
  332  
  333          Thread safety:
  334              - `_execution_lock` 사용으로 봉 처리 스레드와 원자성 보장
  335              - position.apply_entry 는 attribute set 만 수행 (부작용 없음)
  336          """
  337          with self._execution_lock:
  338              if self._pending_buy_uuid is None or uuid != self._pending_buy_uuid:
  339                  logger.debug(
  340                      f"[LIMIT-FILL] uuid mismatch → skip | pending={self._pending_buy_uuid} "
  341                      f"received={uuid}"
  342                  )
  343                  return
  344  
  345              try:
  346                  self.position.apply_entry(
  347                      qty=executed_qty,
  348                      avg_price=executed_price,
  349                      entry_bar=self.bar_count,
  350                      entry_ts=executed_ts,
  351                      source="bot_limit_fill",
  352                  )
  353                  ts_iso = (
  354                      executed_ts.isoformat()
  355                      if hasattr(executed_ts, "isoformat") else str(executed_ts)
  356                  )
  357                  logger.info(
  358                      f"✅ [LIMIT-FILL] apply_entry 완료 | uuid={uuid} qty={executed_qty:.6f} "
  359                      f"price={executed_price:.2f} entry_bar={self.bar_count} ts={ts_iso}"
  360                  )
  361              except Exception as e:
  362                  logger.error(f"[LIMIT-FILL] apply_entry 실패 uuid={uuid}: {e}", exc_info=True)
  363                  return
```

## A3. boot_seed 복원 경로

### engine/live_loop.py:688-745 — 기동 시 지갑 동기화 → DB seed → apply_entry 또는 ERROR 분기
```python
  688      # ✅ sync_from_wallet()로 실제 잔고 동기화
  689      position.sync_from_wallet()
  690      has_pos = position.has_position
  691      if has_pos:
  692          # ✅ 실제 지갑 잔고로 qty 설정 (Single Source of Truth)
  693          actual_qty = _wallet_balance(trader, params.upbit_ticker)
  694  
  695          db_result = _seed_entry_price_from_db(params.upbit_ticker, user_id)
  696          if db_result:
  697              entry_price = db_result.get("price")
  698              entry_bar = db_result.get("entry_bar")
  699              entry_ts_iso = db_result.get("entry_ts_iso")
  700  
  701              # ✅ SP-PI-1: entry_ts 원 시각 복원 (P3 boot_seed 경로)
  702              entry_ts = None
  703              if entry_ts_iso:
  704                  try:
  705                      from datetime import datetime
  706                      from zoneinfo import ZoneInfo
  707                      entry_ts = datetime.fromisoformat(str(entry_ts_iso))
  708                      if entry_ts.tzinfo is None:
  709                          entry_ts = entry_ts.replace(tzinfo=ZoneInfo("Asia/Seoul"))
  710                  except Exception as e:
  711                      logger.warning(f"[SEED] entry_ts parse 실패: {e} → seed 시각 부재")
  712                      entry_ts = None
  713  
  714              if entry_price is not None and entry_ts is not None:
  715                  position.apply_entry(
  716                      qty=actual_qty,
  717                      avg_price=float(entry_price),
  718                      entry_bar=int(entry_bar) if entry_bar is not None else 0,
  719                      entry_ts=entry_ts,
  720                      source="boot_seed",
  721                  )
  722                  logger.info(
  723                      f"🔁 Position recovered | entry={entry_price} qty={actual_qty:.6f} "
  724                      f"entry_bar={entry_bar} entry_ts={entry_ts.isoformat()}"
  725                  )
  726              else:
  727                  # entry_ts 복원 실패 — 신뢰 가능 데이터 부족 → SP-PI-5 방침에 따라 has_position=False 유지
  728                  logger.error(
  729                      f"❌ P3 boot seed 시각 복원 실패 → has_position=False 유지. "
  730                      f"entry_price={entry_price} entry_ts_iso={entry_ts_iso}. "
  731                      f"수동 정리 또는 force_liquidate 필요."
  732                  )
  733          else:
  734              # ✅ SP-PI-5: avg_price=None 비상 모드 완전 제거.
  735              #   진입가·시각이 신뢰 가능하지 않은 상태로 has_position=True 를 유지하면
  736              #   SL/TP/Stale 계산 불가 (avg_price None 시 division 실패)·잘못된 매도 위험.
  737              #   → has_position=False 유지 + Telegram CRITICAL. 사용자 수동 개입 요청.
  738              # ✅ WO-12 C7: 봇 주문이 없을 뿐(외부 매수)일 수 있으므로 CRITICAL 은 워밍업 뒤
  739              #   _boot_seed_recover_from_wallet() 이 지갑 기준 복원까지 실패했을 때만 낸다.
  740              boot_seed_recover_qty = actual_qty
  741              logger.warning(
  742                  f"[BOOT-SEED] 봇 주문 기준 진입가 없음 (외부 매수 가능) → 워밍업 뒤 지갑 기준 복원 시도 | "
  743                  f"wallet={actual_qty:.6f}"
  744              )
  745              # ✅ [Phase 1-E/P1-4] sync_from_wallet 가 이미 True 세팅했을 수 있으므로 명시적 False 리셋.
```

### services/db.py:1838-1853 — _fetch_one: 시각 열 값이 NULL 이면 entry_ts_iso 를 넣지 않음
```python
 1838  
 1839              result = {}
 1840              # SELECT 순서: price, [entry_bar], [entry_ts_iso]
 1841              idx = 0
 1842              if row[idx] is not None:
 1843                  result["price"] = float(row[idx])
 1844              idx += 1
 1845              if "entry_bar" in cols:
 1846                  if len(row) > idx and row[idx] is not None:
 1847                      result["entry_bar"] = int(row[idx])
 1848                  idx += 1
 1849              # ✅ SP-PI-1: 진입 시각 복원 — orders 테이블에서 timestamp 계열 컬럼 반환
 1850              if len(row) > idx and row[idx] is not None:
 1851                  result["entry_ts_iso"] = str(row[idx])
 1852  
 1853              return result if result else None
```

### services/db.py:1888-1913 — ORDER BY(executed_at 오름차순) · 시각 열 선택(executed_at 우선)
```python
 1888  
 1889          # --- ORDER BY 구성 ---
 1890          order_keys = [c for c in ("executed_at", "created_at", "ts", "timestamp") if c in cols]
 1891          if order_keys:
 1892              order_sql = " , ".join(order_keys) + " DESC, ROWID DESC"
 1893          else:
 1894              order_sql = "ROWID DESC"
 1895  
 1896          # ✅ avg_price (실제 체결가) 우선, 없으면 price (주문 가격)
 1897          # ✅ entry_bar 컬럼이 있으면 함께 조회
 1898          if "avg_price" in cols:
 1899              select_cols = "COALESCE(avg_price, price) as price"
 1900          else:
 1901              select_cols = "price"
 1902  
 1903          if "entry_bar" in cols:
 1904              select_cols += ", entry_bar"
 1905  
 1906          # ✅ SP-PI-1: 진입 시각 복원 — 우선순위 executed_at > created_at > ts > timestamp
 1907          ts_col_pick = None
 1908          for cand in ("executed_at", "created_at", "ts", "timestamp"):
 1909              if cand in cols:
 1910                  ts_col_pick = cand
 1911                  break
 1912          if ts_col_pick:
 1913              select_cols += f", {ts_col_pick}"
```

### core/position_state.py:104-156 — sync_from_wallet: avg_price 복구 + entry_ts 를 동기화 시각으로
```python
  104              # ✅ [Fix 1] avg_price 복구 (HTS 매수 미인식 결함 근본 방지)
  105              # wallet 잔고는 있는데 avg_price 가 None/0 이면 다음 매도 필터가 pnl=None
  106              # 조기 return 으로 SL/TP/TS/Stale 전량 무력화됨 (2026-07-24 사건).
  107              # 우선순위: 1) DB 캐시(Reconciler HTS-DETECT 반영) → 2) Upbit avg_buy_price 직접 조회.
  108              if actual_has_position and (self.avg_price is None or self.avg_price <= 0):
  109                  recovered_price = None
  110                  recovery_src = None
  111  
  112                  # 1순위: DB 캐시 (account_positions.entry_price, Reconciler 업데이트)
  113                  try:
  114                      if hasattr(self.trader, 'user_id'):
  115                          from services.db import get_position_entry_price
  116                          cached = get_position_entry_price(self.trader.user_id, self.ticker)
  117                          if cached is not None and cached > 0:
  118                              recovered_price = float(cached)
  119                              recovery_src = "db_cache"
  120                  except Exception as _e:
  121                      logger.debug(f"[POS-SYNC] DB 캐시 조회 실패: {_e}")
  122  
  123                  # 2순위: Upbit API 직접 조회 (LIVE 모드만, DB 캐시 미반영 시 즉시 실측)
  124                  if recovered_price is None and not getattr(self.trader, "test_mode", True):
  125                      try:
  126                          symbol = self.ticker.split("-")[-1].strip().upper() if self.ticker else self.ticker
  127                          for b in (self.trader.upbit.get_balances() or []):
  128                              if str(b.get("currency", "")).upper() == symbol:
  129                                  api_avg = float(b.get("avg_buy_price") or 0.0)
  130                                  if api_avg > 0:
  131                                      recovered_price = api_avg
  132                                      recovery_src = "upbit_api"
  133                                  break
  134                      except Exception as _e:
  135                          logger.warning(f"[POS-SYNC] Upbit avg_buy_price 조회 실패: {_e}")
  136  
  137                  if recovered_price is not None:
  138                      self.avg_price = recovered_price
  139                      # ✅ [Phase 1-B] entry_ts / entry_bar 도 함께 복구 (P1-1 근본 봉쇄)
  140                      # 감사 결과: avg_price 만 복구하면 Stale filter 가 entry_ts=None 으로
  141                      # silent NO_POSITION return → SELL 무력화.
  142                      # 실제 HTS 매수 시각을 봇이 알 수 없으므로 sync 시각으로 세팅 (Stale timer
  143                      # 는 봇이 인식한 시점부터 카운트, 사용자 관점에서는 방어 보수적).
  144                      if self.entry_ts is None:
  145                          try:
  146                              from datetime import datetime
  147                              from zoneinfo import ZoneInfo
  148                              self.entry_ts = datetime.now(ZoneInfo("Asia/Seoul"))
  149                              logger.warning(
  150                                  f"✅ [POS-SYNC] entry_ts 도 함께 복구 (sync 시각) | "
  151                                  f"entry_ts={self.entry_ts.isoformat()} | ticker={self.ticker}"
  152                              )
  153                          except Exception as _e:
  154                              logger.error(f"[POS-SYNC] entry_ts 복구 실패: {_e}")
  155                      logger.warning(
  156                          f"✅ [POS-SYNC] avg_price 복구 성공 | source={recovery_src} | "
```

### core/position_state.py:218-266 — apply_entry
```python
  218      def apply_entry(
  219          self,
  220          qty: float,
  221          avg_price: float,
  222          entry_bar: int,
  223          entry_ts,
  224          source: str,
  225          highest_since_entry: Optional[float] = None,
  226      ) -> None:
  227          """
  228          ✅ SP-PI-1: 통합 진입 API — 모든 P1/P2/P3/HTS 경로가 반드시 이 API 호출.
  229          entry_ts 는 필수 (None 이면 예외) — Stale filter 결함 재발 물리적 차단.
  230  
  231          Args:
  232              qty: 보유 수량
  233              avg_price: 평균 매수가
  234              entry_bar: 진입 시점 bar_count
  235              entry_ts: 진입 시점 timezone-aware datetime (필수)
  236              source: 진입 경로 라벨 — "bot_market" / "bot_limit_fill" /
  237                      "wallet_sync" / "boot_seed" / "hts_detect"
  238              highest_since_entry: Stale Check 초기값 (None 이면 avg_price)
  239          """
  240          if entry_ts is None:
  241              raise ValueError(f"entry_ts is required (source={source})")
  242  
  243          self.has_position = True
  244          self.qty = qty
  245          self.avg_price = avg_price
  246          self.entry_bar = entry_bar
  247          self.entry_ts = entry_ts
  248          self.last_action_ts = entry_ts
  249          self.pending_order = False
  250  
  251          # Trailing Stop 초기화
  252          self.highest_price = avg_price
  253          self.trailing_armed = False
  254          self.trailing_fixed_amount = None
  255          self.trailing_activation_price = None
  256  
  257          # ✅ Stale Position Check 초기화
  258          self.highest_since_entry = (
  259              highest_since_entry if highest_since_entry is not None else avg_price
  260          )
  261  
  262          ts_iso = entry_ts.isoformat() if hasattr(entry_ts, "isoformat") else str(entry_ts)
  263          logger.info(
  264              f"✅ [POSITION-APPLY] source={source} qty={qty:.6f} "
  265              f"entry={avg_price:.2f} bar={entry_bar} ts={ts_iso}"
  266          )
```

## A4. ERROR 문구

### engine/live_loop.py:726-732 — 실제로는 has_position=True 유지
```python
  726              else:
  727                  # entry_ts 복원 실패 — 신뢰 가능 데이터 부족 → SP-PI-5 방침에 따라 has_position=False 유지
  728                  logger.error(
  729                      f"❌ P3 boot seed 시각 복원 실패 → has_position=False 유지. "
  730                      f"entry_price={entry_price} entry_ts_iso={entry_ts_iso}. "
  731                      f"수동 정리 또는 force_liquidate 필요."
  732                  )
```

## C. executed_at 을 읽는 기능

### core/strategy_engine.py:550-580 — POSITION-SYNC 자동 복구: price·entry_bar 만 사용, entry_ts=now
```python
  550                              source = "upbit_avg_buy_price"
  551  
  552                          # 2순위(폴백): 봇의 마지막 미청산 BUY (청산 검증 포함된 get_last_open_buy_order)
  553                          if entry_price is None:
  554                              db_result = get_last_open_buy_order(self.ticker, self.user_id)
  555                              if db_result:
  556                                  ep = db_result.get("avg_price") or db_result.get("price")
  557                                  if ep is not None:
  558                                      entry_price = float(ep)
  559                                      entry_bar = db_result.get("entry_bar")
  560                                      source = "last_open_buy"
  561  
  562                          if entry_price is not None and entry_price > 0:
  563                              # ✅ SP-PI-1: P2 자동 복구 — apply_entry 통합 API 사용
  564                              # D2 결정: wallet_sync 는 now_kst() 를 entry_ts 로 사용
  565                              # (매 봉 sync 이므로 실시각과 큰 차이 없음. P1 정상 매수 시엔 이 경로가
  566                              #  더 이상 상시 발동하지 않음 — SP-PI-2 fill callback 이 P1 상당 처리 수행)
  567                              from datetime import datetime
  568                              from zoneinfo import ZoneInfo
  569                              _p2_entry_ts = datetime.now(ZoneInfo("Asia/Seoul"))
  570                              self.position.apply_entry(
  571                                  qty=actual_balance,
  572                                  avg_price=float(entry_price),
  573                                  entry_bar=int(entry_bar) if entry_bar is not None else self.bar_count,
  574                                  entry_ts=_p2_entry_ts,
  575                                  source="wallet_sync",
  576                              )
  577                              logger.info(
  578                                  f"✅ [POSITION-SYNC] 자동 복구 성공 (source={source}, api=apply_entry): "
  579                                  f"qty={actual_balance:.6f}, entry_price={entry_price:.2f}, "
  580                                  f"entry_bar={self.position.entry_bar}, entry_ts={_p2_entry_ts.isoformat()}"
```

### pages/dashboard.py:862-868 — 대시보드 미실현 수익률: price 만 사용
```python
  862      # ✅ 포지션 보유 여부에 따라 분기
  863      if qty > 0:
  864          # === 미실현 수익률 (현재 포지션) ===
  865          last_buy = get_last_open_buy_order(_ticker, user_id)
  866          if last_buy and last_price:
  867              entry_price = last_buy["price"]
  868              unrealized_pnl_pct = ((last_price - entry_price) / entry_price) * 100.0
```

### pages/dashboard.py:2886-2890 — fetch_order_statuses: 표준출력 print 만 (화면 표시 아님)
```python
 2886  from services.db import fetch_order_statuses
 2887  
 2888  rows = fetch_order_statuses(user_id, limit=10, ticker=ticker)
 2889  for r in rows:
 2890      print(r)
```

### services/db.py:2149-2162 — fetch_recent_fills: 호출처 없음
```python
 2149  def fetch_recent_fills(user_id: str, limit: int = 20):
 2150      ensure_schema(user_id)
 2151      with get_db(user_id) as conn:
 2152          cur = conn.cursor()
 2153          cur.execute("""
 2154              SELECT timestamp, ticker, side, state, executed_volume, avg_price, paid_fee, requested_at, executed_at
 2155              FROM orders
 2156              WHERE user_id = ?
 2157                AND state IN ('FILLED','PARTIALLY_FILLED','CANCELED','REJECTED','REQUESTED')
 2158              ORDER BY id DESC
 2159              LIMIT ?
 2160          """, (user_id, limit))
 2161          return cur.fetchall()
 2162  
```

### services/settings_history.py:662-705 — 설정 이력 손익: executed_at 없으면 orders.timestamp 로 ±60초 매칭
```python
  662      # orders 와 시각 매칭으로 volume·paid_fee 보충 (best-effort)
  663      # SELL audit_trades 의 timestamp 와 가장 가까운 orders.executed_at (±60s) 매칭
  664      orders_by_id = {}
  665      if sells:
  666          with get_db(user_id) as conn:
  667              cur = conn.cursor()
  668              cur.execute(
  669                  "SELECT id, ticker, side, executed_volume, avg_price, paid_fee, "
  670                  "       executed_at, timestamp, state "
  671                  "FROM orders WHERE user_id=? AND side='SELL' "
  672                  "AND state IN ('FILLED','PARTIALLY_FILLED') "
  673                  "AND (executed_at >= ? OR timestamp >= ?)",
  674                  (user_id, start_ts, start_ts),
  675              )
  676              for r in cur.fetchall():
  677                  orders_by_id[r[0]] = {
  678                      "ticker": r[1], "side": r[2],
  679                      "executed_volume": r[3], "avg_price": r[4],
  680                      "paid_fee": r[5] or 0.0,
  681                      "executed_at": r[6], "timestamp": r[7],
  682                  }
  683  
  684      def _match_order(sell_trade):
  685          """가장 가까운 SELL order (같은 ticker, ±60s) 찾기."""
  686          from datetime import datetime as _dt
  687          try:
  688              t_ts = _dt.fromisoformat(sell_trade["timestamp"])
  689          except Exception:
  690              return None
  691          best = None
  692          best_delta = None
  693          for oid, o in orders_by_id.items():
  694              if o["ticker"] != sell_trade["ticker"]:
  695                  continue
  696              try:
  697                  o_ts = _dt.fromisoformat(o["executed_at"] or o["timestamp"])
  698              except Exception:
  699                  continue
  700              delta = abs((o_ts - t_ts).total_seconds())
  701              if delta > 60:
  702                  continue
  703              if best_delta is None or delta < best_delta:
  704                  best, best_delta = o, delta
  705          return best
```

### core/filters/sell_filters.py:488-512 — 정체 포지션: position.entry_ts 사용 (DB 직접 조회 아님)
```python
  488                  reason="NO_DATA",
  489                  details="Position or price data not provided"
  490              )
  491  
  492          if not position.has_position or position.entry_ts is None:
  493              return FilterResult(
  494                  should_block=False,
  495                  reason="NO_POSITION",
  496                  details="No active position"
  497              )
  498  
  499          if current_time is None:
  500              logger.warning("⚠️ [STALE_POSITION] current_time not provided, skipping check")
  501              return FilterResult(
  502                  should_block=False,
  503                  reason="NO_TIME",
  504                  details="Current time not provided"
  505              )
  506  
  507          # ✅ 실제 경과 시간 계산 (시간 기반)
  508          elapsed = current_time - position.entry_ts
  509          elapsed_hours = elapsed.total_seconds() / 3600
  510  
  511          # 진입 이후 최고가 갱신
  512          position.update_highest_since_entry(current_price)
```

### core/strategy_incremental.py:1125-1156 — bars_held ≤ 0 → audit fallback
```python
 1125              bars_held = position.get_bars_held(current_bar_idx)
 1126  
 1127              # ✅ WO-8 절충안 승격 가드: bars_held > 0 진입 정상 통과 시 streak 리셋
 1128              if bars_held > 0 and self._pos_desync_streak > 0:
 1129                  logger.info(
 1130                      f"[POS-DESYNC] streak 리셋: {self._pos_desync_streak} → 0 (bars_held={bars_held} 정상 통과)"
 1131                  )
 1132                  self._pos_desync_streak = 0
 1133  
 1134              # ✅ SP-PI-4: bars_held ≤ 0 감지 시 audit_trades 실측으로 fallback.
 1135              #   과거에는 이 지점에서 SELL 을 통째 차단해 SL/TP/Stale/Trailing 전부 무력화
 1136              #   되는 결함이 있었다 (F4). SP-PI-1 통합 진입 API 도입으로 근본이 봉쇄되었으나,
 1137              #   방어책으로 audit 실측 fallback 을 재도입한다. audit 도 없으면 CRITICAL.
 1138              if bars_held <= 0:
 1139                  from services.db import estimate_bars_held_from_audit
 1140                  audit_bh = 0
 1141                  try:
 1142                      audit_bh = int(estimate_bars_held_from_audit(self.user_id, self.ticker) or 0)
 1143                  except Exception as _e:
 1144                      logger.warning(f"[EMA] audit bars_held fallback 조회 실패: {_e}")
 1145  
 1146                  if audit_bh > 0:
 1147                      # entry_bar 즉시 복구 → 다음 봉부터는 in-memory 값으로 정상 계산
 1148                      new_entry_bar = current_bar_idx - audit_bh
 1149                      logger.warning(
 1150                          f"⚠️ [EMA] in-memory bars_held={bars_held} → audit fallback={audit_bh} 적용 "
 1151                          f"(entry_bar {position.entry_bar} → {new_entry_bar}). "
 1152                          f"근본: apply_entry 미경유 진입 or 재시작 seed 지연 의심"
 1153                      )
 1154                      position.entry_bar = new_entry_bar
 1155                      bars_held = audit_bh
 1156                      # ✅ WO-8 절충안 승격 가드: audit fallback 성공 → streak 리셋
```
