# WO-21 코드 인용 (HEAD 129c6df, 서버 e97dec6 과 엔진 코드 동일)
## A1. 상태 변수와 변경 지점

### core/position_state.py:40-55 — 초기값: highest_price None, trailing_armed False, trailing_fixed_amount None, trailing_activation_price None, highest_since_entry None
```python
   40          self.pending_order: bool = False           # 주문 진행 중 여부
   41          self.last_action_ts = None                 # 마지막 액션 타임스탬프
   42  
   43          # 추가: Trailing Stop / Highest Price 추적용
   44          self.highest_price: Optional[float] = None
   45          self.trailing_armed: bool = False
   46  
   47          # ✅ 고정폭 Trailing Stop용 (활성화 시점 고정 금액)
   48          self.trailing_fixed_amount: Optional[float] = None
   49          self.trailing_activation_price: Optional[float] = None
   50  
   51          # ✅ Stale Position Check용 (진입 이후 최고가)
   52          self.highest_since_entry: Optional[float] = None
   53  
   54          # ✅ Issue #17: HTS 매수 감지용 메타데이터
   55          self.metadata: dict = {}  # {"hts_buy": True, "src": "manual", ...}
```

### core/position_state.py:250-261 — apply_entry: highest_price=avg, armed False, fixed·activation None, highest_since_entry=avg
```python
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
```

### core/position_state.py:304-313 — close_position: 모두 초기화
```python
  304          self.pending_order = False
  305  
  306          # Trailing Stop 초기화
  307          self.highest_price = None
  308          self.trailing_armed = False
  309          self.trailing_fixed_amount = None
  310          self.trailing_activation_price = None
  311  
  312          # ✅ Stale Position Check 초기화
  313          self.highest_since_entry = None
```

### core/position_state.py:351-368 — update_highest_price: armed 일 때만 최고가 갱신
```python
  351      def update_highest_price(self, current_price: float):
  352          """
  353          Trailing Stop용 최고가 갱신
  354  
  355          ✅ 변경: trailing_armed == True일 때만 갱신
  356  
  357          Args:
  358              current_price: 현재 가격
  359          """
  360          if not self.has_position:
  361              return
  362  
  363          # ✅ trailing_armed 상태일 때만 최고가 추적
  364          if not self.trailing_armed:
  365              return
  366  
  367          if self.highest_price is None or current_price > self.highest_price:
  368              self.highest_price = current_price
```

### core/position_state.py:410-428 — activate_trailing_stop: armed=True, highest=현재가
```python
  410          return False
  411  
  412      def activate_trailing_stop(self, current_price: float):
  413          """
  414          ✅ NEW: Trailing Stop 활성화 (Take Profit 도달 시 호출)
  415  
  416          Args:
  417              current_price: 현재 가격 (최고가 초기값으로 사용)
  418          """
  419          if not self.has_position:
  420              return
  421  
  422          self.trailing_armed = True
  423          self.highest_price = current_price  # 현재가를 최고가 초기값으로
  424  
  425          logger.info(
  426              f"🔓 Trailing Stop ACTIVATED | "
  427              f"entry=₩{self.avg_price:,.0f} initial_highest=₩{current_price:,.0f}"
  428          )
```

### core/position_state.py:460-471 — update_highest_since_entry (정체 포지션용)
```python
  460      def update_highest_since_entry(self, current_price: float):
  461          """
  462          진입 이후 최고가 갱신 (Stale Position Check용)
  463  
  464          Args:
  465              current_price: 현재 가격
  466          """
  467          if not self.has_position:
  468              return
  469  
  470          if self.highest_since_entry is None or current_price > self.highest_since_entry:
  471              self.highest_since_entry = current_price
```

### core/filters/sell_filters.py:273-345 — TrailingStopFilter: 익절 도달 → 무장·고정폭 계산, 신고가 갱신, 고정폭 판정
```python
  273          # ✅ STEP 1: Take Profit 도달 체크 (trailing_armed 활성화 트리거)
  274          if not position.trailing_armed:
  275              pnl_pct = position.get_pnl_pct(current_price)
  276  
  277              # ✅ [Fix 3] silent skip 방지 — avg_price 없으면 TS 활성화 자체 불가
  278              if pnl_pct is None:
  279                  logger.warning(
  280                      f"⚠️ [TRAILING_STOP_CHECK] pnl_pct=None (avg_price={position.avg_price}) → TS 활성화 스킵. "
  281                      f"has_position={position.has_position}, qty={position.qty}, current_price={current_price}"
  282                  )
  283                  return FilterResult(
  284                      should_block=False,
  285                      reason="NO_PNL",
  286                      details=f"PnL calculation failed (avg_price={position.avg_price})"
  287                  )
  288  
  289              if pnl_pct is not None and pnl_pct >= self.take_profit_pct:
  290                  # Take Profit 도달 → Trailing Stop 활성화
  291                  position.activate_trailing_stop(current_price)
  292  
  293                  # ✅ 고정폭 모드: 활성화 시점 1회 계산
  294                  if self.use_fixed_mode:
  295                      activation_profit = current_price - position.avg_price
  296                      position.trailing_fixed_amount = activation_profit * self.trailing_stop_pct
  297                      position.trailing_activation_price = current_price
  298                      logger.info(
  299                          f"🔒 고정 금액 폭 설정 | "
  300                          f"활성화 수익=₩{activation_profit:,.0f} × {self.trailing_stop_pct:.0%} "
  301                          f"= ₩{position.trailing_fixed_amount:,.0f}"
  302                      )
  303  
  304                  mode_str = "고정폭" if self.use_fixed_mode else "비율"
  305                  logger.info(
  306                      f"🔄 AUTO-SWITCH: Take Profit 도달 ({pnl_pct:.2%}) "
  307                      f"→ Trailing Stop 활성화 ({mode_str}) | "
  308                      f"진입가=₩{position.avg_price:,.0f} 현재가=₩{current_price:,.0f}"
  309                  )
  310              else:
  311                  # 아직 Take Profit 미도달 → Trailing Stop 미작동
  312                  return FilterResult(should_block=False, reason="TS_NOT_ARMED")
  313  
  314          # ✅ STEP 2: 신고가 갱신
  315          if current_price > position.highest_price:
  316              position.highest_price = current_price
  317  
  318          # ✅ STEP 3: Trailing Stop 체크 (모드별 분기)
  319          if self.use_fixed_mode:
  320              # ✅ 고정 금액 폭 방식
  321              stop_price = position.highest_price - position.trailing_fixed_amount
  322              triggered = current_price <= stop_price
  323  
  324              logger.info(
  325                  f"🔍 DEBUG [TRAILING_STOP_FIXED] "
  326                  f"highest=₩{position.highest_price:,.0f}, "
  327                  f"fixed_amount=₩{position.trailing_fixed_amount:,.0f}, "
  328                  f"stop_price=₩{stop_price:,.0f}, "
  329                  f"current=₩{current_price:,.0f}, "
  330                  f"triggered={triggered}"
  331              )
  332  
  333              if triggered:
  334                  return FilterResult(
  335                      should_block=True,
  336                      reason="TRAILING_STOP_FIXED",
  337                      details=f"Fixed-amount trailing stop: ₩{current_price:,.0f} <= ₩{stop_price:,.0f}",
  338                      metadata={
  339                          'mode': 'fixed',
  340                          'highest_price': position.highest_price,
  341                          'fixed_amount': position.trailing_fixed_amount,
  342                          'stop_price': stop_price,
  343                          'current_price': current_price
  344                      }
  345                  )
```

### core/strategy_incremental.py:1253-1256 — 매 봉 update_highest_price
```python
 1253  
 1254              # Highest Price 갱신
 1255              position.update_highest_price(current_price)
 1256  
```

### core/strategy_engine.py:300-316 — HTS_BUY_ADD 로 평균가가 바뀌면 trailing 상태 리셋 (기존 정책)
```python
  300                  if self.position.entry_bar is None:
  301                      self.position.entry_bar = self.bar_count
  302                  # ✅ [Phase 1-F/P2-3] HTS_BUY_ADD 시 highest 재계산 (avg 변경으로 옛 highest 무의미)
  303                  if str(reason).upper() == "HTS_BUY_ADD":
  304                      old_highest = self.position.highest_price
  305                      old_since_entry = self.position.highest_since_entry
  306                      self.position.highest_price = None
  307                      self.position.highest_since_entry = None
  308                      self.position.trailing_armed = False
  309                      self.position.trailing_fixed_amount = None
  310                      self.position.trailing_activation_price = None
  311                      logger.warning(
  312                          f"🔄 [HTS-DETECT-CALLBACK] HTS_BUY_ADD 로 avg 변경 → Trailing 상태 리셋 | "
  313                          f"old_highest={old_highest} old_since_entry={old_since_entry} "
  314                          f"→ 모두 None. 다음 봉부터 새 avg 기준 추적 재개."
  315                      )
  316                  logger.warning(
```
## A2. 저장 여부

### core/strategy_engine.py:1843-1863 — audit_sell_eval: highest=position.highest_price, ts_armed=False 고정 (HOLD 경로)
```python
 1843                      insert_sell_eval(
 1844                          user_id=self.user_id,
 1845                          ticker=self.ticker,
 1846                          interval_sec=self.interval_sec,
 1847                          bar=self.bar_count,
 1848                          price=current_price,
 1849                          macd=macd,
 1850                          signal=signal,
 1851                          tp_price=tp_price,
 1852                          sl_price=sl_price,
 1853                          highest=self.position.highest_price,
 1854                          ts_pct=self.trailing_stop_pct,
 1855                          ts_armed=False,
 1856                          bars_held=bars_held,
 1857                          checks=sell_checks,
 1858                          triggered=False,
 1859                          trigger_key=None,
 1860                          notes=f"{cross_status} | PNL={pnl_pct:.2%} | bar={self.bar_count}",
 1861                          bar_time=bar_ts_kst.isoformat(),
 1862                          is_backfill=is_backfill,  # ✅ WO-1: BACKFILL 경로 시 backfill_* 컬럼만 UPDATE
 1863                      )
```

### core/strategy_engine.py:1924-1944 — audit_sell_eval: ts_armed=False 고정 (SELL 경로)
```python
 1924                      insert_sell_eval(
 1925                          user_id=self.user_id,
 1926                          ticker=self.ticker,
 1927                          interval_sec=self.interval_sec,
 1928                          bar=self.bar_count,
 1929                          price=current_price,
 1930                          macd=macd,
 1931                          signal=signal,
 1932                          tp_price=tp_price,
 1933                          sl_price=sl_price,
 1934                          highest=self.position.highest_price,
 1935                          ts_pct=self.trailing_stop_pct,
 1936                          ts_armed=False,
 1937                          bars_held=bars_held,
 1938                          checks=sell_checks,
 1939                          triggered=True,
 1940                          trigger_key=trigger_reason,
 1941                          notes=f"🔴 SELL | {trigger_reason} | {cross_status} | PNL={pnl_pct:.2%} | bar={self.bar_count}",
 1942                          bar_time=bar_ts_kst.isoformat(),
 1943                          is_backfill=is_backfill,  # ✅ WO-1: BACKFILL 경로 시 backfill_* 컬럼만 UPDATE
 1944                      )
```

### services/invariant_monitor.py:115-148 — invariant_snapshots: trailing_armed·highest_price 기록 (system_health 표시용)
```python
  115      """
  116      try:
  117          _ensure_snapshot_schema(user_id)
  118          from services.db import get_db
  119          with get_db(user_id) as conn:
  120              cursor = conn.cursor()
  121              entry_ts_str = (
  122                  position.entry_ts.isoformat()
  123                  if position.entry_ts is not None else None
  124              )
  125              cursor.execute("""
  126                  INSERT INTO invariant_snapshots
  127                  (user_id, ticker, has_position, qty, avg_price, entry_ts, entry_bar,
  128                   wallet_qty, wallet_avg, trailing_armed, highest_price,
  129                   violation_code, violation_msg)
  130                  VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
  131              """, (
  132                  user_id, ticker,
  133                  int(bool(position.has_position)),
  134                  float(position.qty) if position.qty is not None else None,
  135                  float(position.avg_price) if position.avg_price is not None else None,
  136                  entry_ts_str,
  137                  position.entry_bar,
  138                  wallet_qty,
  139                  wallet_avg,
  140                  int(bool(getattr(position, "trailing_armed", False))),
  141                  (
  142                      float(position.highest_price)
  143                      if getattr(position, "highest_price", None) is not None else None
  144                  ),
  145                  violation_code,
  146                  violation_msg,
  147              ))
  148              conn.commit()
```

### services/invariant_monitor.py:154-180 — get_latest_snapshot: 읽는 곳은 pages/system_health.py 뿐
```python
  154  def get_latest_snapshot(user_id: str, ticker: str) -> Optional[dict]:
  155      """가장 최근 스냅샷 1건 조회. system_health 페이지용."""
  156      try:
  157          _ensure_snapshot_schema(user_id)
  158          from services.db import get_db
  159          with get_db(user_id) as conn:
  160              cursor = conn.cursor()
  161              cursor.execute("""
  162                  SELECT timestamp, has_position, qty, avg_price, entry_ts, entry_bar,
  163                         wallet_qty, wallet_avg, trailing_armed, highest_price,
  164                         violation_code, violation_msg
  165                  FROM invariant_snapshots
  166                  WHERE user_id=? AND ticker=?
  167                  ORDER BY id DESC LIMIT 1
  168              """, (user_id, ticker))
  169              row = cursor.fetchone()
  170              if not row:
  171                  return None
  172              cols = ["timestamp", "has_position", "qty", "avg_price", "entry_ts", "entry_bar",
  173                      "wallet_qty", "wallet_avg", "trailing_armed", "highest_price",
  174                      "violation_code", "violation_msg"]
  175              return dict(zip(cols, row))
  176      except Exception as e:
  177          logger.warning(f"[INVARIANT_MONITOR] 조회 실패: {e}")
  178          return None
  179  
  180  
```

### services/db.py:2703-2730 — update_position_meta: meta JSON 통째 UPSERT
```python
 2703  def update_position_meta(user_id: str, ticker: str, meta: Dict[str, Any]):
 2704      """
 2705      특정 ticker의 포지션 메타데이터 업데이트
 2706  
 2707      Args:
 2708          meta: 메타데이터 dict (예: {"hts_buy": True})
 2709  
 2710      Usage:
 2711          update_position_meta(user_id, "KRW-ZRO", {"hts_buy": True})
 2712      """
 2713      try:
 2714          with get_db(user_id) as conn:
 2715              cur = conn.cursor()
 2716              meta_json = json.dumps(meta, ensure_ascii=False)
 2717  
 2718              # UPSERT: 레코드 없으면 INSERT, 있으면 UPDATE
 2719              cur.execute(
 2720                  """
 2721                  INSERT INTO account_positions (user_id, ticker, virtual_coin, meta, updated_at)
 2722                  VALUES (?, ?, 0, ?, ?)
 2723                  ON CONFLICT(user_id, ticker) DO UPDATE SET
 2724                      meta = excluded.meta,
 2725                      updated_at = excluded.updated_at
 2726                  """,
 2727                  (user_id, ticker, meta_json, now_kst())
 2728              )
 2729              conn.commit()
 2730      except Exception as e:
```

### engine/order_reconciler.py:619-630 — meta.locked_warned 읽기-수정-쓰기 (OR 스레드)
```python
  619                  except Exception:
  620                      pass
  621                  meta["locked_warned"] = True
  622                  update_position_meta(user_id, ticker, meta)
  623              elif meta.get("locked_warned") and avail > 1e-12:
  624                  logger.info(
  625                      f"✅ [LOCKED-QTY] 묶임 해제 — 가용 회복 | ticker={ticker} "
  626                      f"가용={avail:.6f} 묶임={locked:.6f}"
  627                  )
  628                  meta.pop("locked_warned", None)
  629                  update_position_meta(user_id, ticker, meta)
  630          except Exception as e:
```
## A3. 재시작 복원 경로

### engine/live_loop.py:631-667 — _BACKFILL_TRAILING_FIELDS 5개 + 백업·복원 함수 (BACKFILL 전용)
```python
  631  
  632  _BACKFILL_TRAILING_FIELDS = (
  633      "highest_price",
  634      "highest_since_entry",
  635      "trailing_armed",
  636      "trailing_fixed_amount",
  637      "trailing_activation_price",
  638  )
  639  
  640  
  641  def _backup_trailing_state(position) -> Dict[str, Any]:
  642      """
  643      ✅ WO-14 E1 (2026-10-01): BACKFILL 전 Trailing 상태 백업.
  644      정책: BACKFILL 재평가는 지표를 바로잡는 작업이며 포지션 상태를 바꾸지 않는다.
  645      과거 누락 봉의 가격은 실시간에 보지 못한 가격이므로 Trailing 고점에 반영하지 않는다.
  646      """
  647      saved = {f: getattr(position, f, None) for f in _BACKFILL_TRAILING_FIELDS}
  648      saved["has_position"] = getattr(position, "has_position", False)
  649      return saved
  650  
  651  
  652  def _restore_trailing_state(position, saved: Dict[str, Any]):
  653      """
  654      ✅ WO-14 E1: BACKFILL 뒤 Trailing 상태 복원. 바뀐 필드만 되돌린다.
  655      BACKFILL 중 보유 여부가 바뀌었으면(별도 스레드 체결 반영 등) 새 포지션 상태를 덮어쓰지 않도록 건너뛴다.
  656      반환: {필드: (BACKFILL 뒤 값, 되돌린 값)} — 건너뛰면 None
  657      """
  658      if getattr(position, "has_position", False) != saved.get("has_position"):
  659          return None
  660      changed = {}
  661      for f in _BACKFILL_TRAILING_FIELDS:
  662          cur = getattr(position, f, None)
  663          if cur != saved[f]:
  664              changed[f] = (cur, saved[f])
  665              setattr(position, f, saved[f])
  666      return changed
  667  
```

### engine/live_loop.py:1390-1396 — 백업 호출: BACKFILL 루프 안에서만
```python
 1390                                          'prev_ema_slow_sell': engine.indicators.prev_ema_slow_sell,
 1391                                      })
 1392  
 1393                                  # ✅ WO-14 E1: Trailing 상태 백업 (BACKFILL 은 포지션 상태를 바꾸지 않음)
 1394                                  saved_trailing = _backup_trailing_state(engine.position)
 1395  
 1396                                  # ✅ WO-1 추가 A: 백업 로그 debug → info 승격 (프로덕션 감시)
```

### engine/live_loop.py:395-452 — _apply_boot_seed: apply_entry(source=boot_seed) → trailing 초기화
```python
  395      - 주문 기록에서는 entry_ts 와 entry_bar 만 가져온다.
  396        entry_ts 는 COALESCE(executed_at, updated_at) (services/db.py get_last_open_buy_order).
  397      - avg_price 는 직전 sync_from_wallet 이 정한 지갑 값(account_positions.entry_price 또는
  398        Upbit avg_buy_price)을 유지한다. 지갑 평균가를 구하지 못한 경우에만 주문 평균가를 쓴다.
  399        (봇 매수 뒤 앱 추가 매수가 섞인 포지션에서 단일 주문 평균가로 덮지 않기 위함)
  400      - entry_ts 가 없으면 apply_entry 를 부르지 않는다. 지갑 동기화 값(has_position=True,
  401        entry_ts=기동 시각)이 그대로 남으므로 WARNING 1줄로 사실대로 남긴다.
  402  
  403      Returns:
  404          bool: apply_entry(source="boot_seed") 를 불렀으면 True
  405      """
  406      order_price = db_result.get("price")
  407      entry_bar = db_result.get("entry_bar")
  408      entry_ts_iso = db_result.get("entry_ts_iso")
  409  
  410      entry_ts = None
  411      if entry_ts_iso:
  412          try:
  413              from datetime import datetime
  414              from zoneinfo import ZoneInfo
  415              entry_ts = datetime.fromisoformat(str(entry_ts_iso))
  416              if entry_ts.tzinfo is None:
  417                  entry_ts = entry_ts.replace(tzinfo=ZoneInfo("Asia/Seoul"))
  418          except Exception as e:
  419              logger.warning(f"[SEED] entry_ts parse 실패: {e} → seed 시각 부재")
  420              entry_ts = None
  421  
  422      wallet_avg = position.avg_price if (position.avg_price is not None and position.avg_price > 0) else None
  423      if wallet_avg is not None:
  424          avg_price, avg_src = float(wallet_avg), "wallet"
  425      elif order_price is not None:
  426          avg_price, avg_src = float(order_price), "order"
  427      else:
  428          avg_price, avg_src = None, None
  429  
  430      if entry_ts is not None and avg_price is not None:
  431          position.apply_entry(
  432              qty=actual_qty,
  433              avg_price=avg_price,
  434              entry_bar=int(entry_bar) if entry_bar is not None else 0,
  435              entry_ts=entry_ts,
  436              source="boot_seed",
  437          )
  438          logger.info(
  439              f"🔁 Position recovered | avg_price={avg_price} (출처: {avg_src}) order_price={order_price} "
  440              f"qty={actual_qty:.6f} entry_bar={entry_bar} entry_ts={entry_ts.isoformat()}"
  441          )
  442          return True
  443  
  444      # entry_ts(또는 평균가) 를 정하지 못함 — apply_entry 미호출, 지갑 동기화 값 유지
  445      _ts = position.entry_ts.isoformat() if hasattr(position.entry_ts, "isoformat") else position.entry_ts
  446      logger.warning(
  447          f"⚠️ [BOOT-SEED] 봇 주문의 체결 시각 없음 → boot_seed 미적용, 지갑 동기화 값 유지 | "
  448          f"has_position={position.has_position} qty={actual_qty:.6f} avg_price={position.avg_price} (출처: 지갑) "
  449          f"entry_ts={_ts} (기동 시각) | 정체 포지션 판정은 기동 시각부터 다시 센다 | "
  450          f"order_price={order_price} entry_ts_iso={entry_ts_iso}"
  451      )
  452      return False
```

### engine/live_loop.py:776-790 — 봇 주문 없음(앱 매수) 경로: trailing 필드 None 리셋 후 워밍업 뒤 지갑 기준 복원
```python
  776              # 다음 sync_from_wallet 이 wallet 감지 시 Fix 1 조건 (avg_price is None) False 로 스킵되어
  777              # 옛 값 그대로 사용 → 위험 상태 지속. avg_price 등 관련 필드 모두 완전 리셋.
  778              position._has_position = False
  779              position.qty = 0.0
  780              position.avg_price = None
  781              position.entry_ts = None
  782              position.entry_bar = None
  783              position.highest_price = None
  784              position.highest_since_entry = None
  785              position.trailing_armed = False
  786              position.trailing_fixed_amount = None
  787              position.trailing_activation_price = None
  788              logger.warning(
  789                  f"🔄 [BOOT-SEED] 완전 상태 리셋 완료 (avg_price/entry_ts/entry_bar/highest 모두 None). "
  790                  f"사용자 개입 대기 상태."
```

### core/strategy_engine.py:556-580 — _reconcile_position_with_wallet: apply_entry(source=wallet_sync, entry_ts=now)
```python
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
