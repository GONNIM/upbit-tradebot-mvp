"""
1109 눌림목 실계좌 열기 — EMA 호출 흔적 기준값(GOLDEN).

기준 커밋 158c5fc 의 코드(`git archive 158c5fc` 추출본)로 tests/regressions/ema_trace_scenarios.py 를 돌려 뽑은 값이다.
지금 코드가 같은 흔적을 내야 EMA·MACD 실매매 경로가 그대로라고 본다(test_r_2026_11_09_ema_trace).
다시 뽑는 법: 기준 커밋 추출본을 sys.path 맨 앞에 두고 ema_trace_scenarios.run_all() 을 부른다.
"""
import json

BASE_COMMIT = "158c5fc"
GOLDEN = json.loads(r'''
{
 "reconcile": {
  "both_flat": {
   "audit": [],
   "avg": null,
   "calls": [
    [
     "coin_balance",
     "KRW-TRACE"
    ]
   ],
   "db": [],
   "has": false,
   "qty": 0.0,
   "ret": null
  },
  "both_holding": {
   "audit": [],
   "avg": 1000.0,
   "calls": [
    [
     "coin_balance",
     "KRW-TRACE"
    ]
   ],
   "db": [],
   "has": true,
   "qty": 4.0,
   "ret": null
  },
  "coin_wallet_no_memory_no_avg": {
   "audit": [],
   "avg": null,
   "calls": [
    [
     "coin_balance",
     "KRW-TRACE"
    ],
    "get_balances"
   ],
   "db": [
    "entry_price",
    "last_buy"
   ],
   "has": false,
   "qty": 0.0,
   "ret": null
  },
  "coin_wallet_no_memory_with_avg": {
   "audit": [],
   "avg": 1000.0,
   "calls": [
    [
     "coin_balance",
     "KRW-TRACE"
    ],
    "get_balances"
   ],
   "db": [],
   "has": true,
   "qty": 4.0,
   "ret": "upbit_avg"
  },
  "zero_wallet_memory_pos": {
   "audit": [
    [
     [
      "bar",
      "5"
     ],
     [
      "bars_held",
      "None"
     ],
     [
      "entry_bar",
      "2"
     ],
     [
      "entry_price",
      "1000.0"
     ],
     [
      "highest",
      "None"
     ],
     [
      "interval_sec",
      "60"
     ],
     [
      "kind",
      "'HTS_SELL'"
     ],
     [
      "macd",
      "None"
     ],
     [
      "note",
      "'외부 매도 — 지갑 잔고 0 감지 (앱 매도 등). 체결 가격은 알 수 없음'"
     ],
     [
      "price",
      "None"
     ],
     [
      "qty",
      "4.0"
     ],
     [
      "reason",
      "'HTS_SELL'"
     ],
     [
      "signal",
      "None"
     ],
     [
      "sl",
      "None"
     ],
     [
      "strategy_type",
      "'EMA'"
     ],
     [
      "ticker",
      "'KRW-TRACE'"
     ],
     [
      "tp",
      "None"
     ],
     [
      "ts_armed",
      "None"
     ],
     [
      "ts_pct",
      "None"
     ],
     [
      "user_id",
      "'tracer'"
     ]
    ]
   ],
   "avg": null,
   "calls": [
    [
     "coin_balance",
     "KRW-TRACE"
    ]
   ],
   "db": [],
   "has": false,
   "qty": 0.0,
   "ret": null
  }
 },
 "sync": {
  "raises": {
   "avg": null,
   "calls": [
    [
     "coin_balance",
     "KRW-TRACE"
    ]
   ],
   "has": false,
   "qty": 0.0,
   "ret": false
  },
  "test_mode_skips": {
   "calls": [],
   "ret": false
  },
  "wallet_has_coin_no_avg": {
   "avg": null,
   "calls": [
    [
     "coin_balance",
     "KRW-TRACE"
    ],
    "get_balances"
   ],
   "has": true,
   "qty": 2.5,
   "ret": true
  },
  "wallet_has_coin_with_avg": {
   "avg": 1000.0,
   "calls": [
    [
     "coin_balance",
     "KRW-TRACE"
    ],
    "get_balances"
   ],
   "has": true,
   "qty": 2.5,
   "ret": true
  },
  "wallet_zero_but_memory_pos": {
   "avg": 100.0,
   "calls": [
    [
     "coin_balance",
     "KRW-TRACE"
    ]
   ],
   "has": false,
   "qty": 0.0,
   "ret": false
  },
  "wallet_zero_flat": {
   "avg": null,
   "calls": [
    [
     "coin_balance",
     "KRW-TRACE"
    ]
   ],
   "has": false,
   "qty": 0.0,
   "ret": false
  }
 },
 "trader": {
  "5xx_then_success": {
   "buy_calls": [
    [
     "KRW-TRACE",
     4997501
    ],
    [
     "KRW-TRACE",
     4997501
    ]
   ],
   "krw_reads": 3,
   "last_buy_error": null,
   "logs": [
    [
     "INFO",
     "🚨 [LIVE] 시장가 매수 요청 전송: KRW-TRACE (예상가≈1,000.00 KRW, 사용 KRW ≈"
    ]
   ],
   "notify": [
    [
     "CRITICAL",
     "🟢 매수 요청 — KRW-TRACE"
    ]
   ],
   "orders": [
    [
     [
      "tracer",
      "KRW-TRACE",
      "BUY",
      1000.0,
      0,
      "requested"
     ],
     [
      [
       "entry_bar",
       7
      ],
      [
       "meta",
       "{\"reason\": \"EMA_GC\", \"bar\": 7}"
      ],
      [
       "provider_uuid",
       "u-1"
      ],
      [
       "settings_history_id",
       null
      ],
      [
       "state",
       "REQUESTED"
      ],
      [
       "strategy_type",
       "EMA"
      ]
     ]
    ]
   ],
   "result": {
    "price": 1000.0,
    "qty": 0.0,
    "side": "BUY",
    "time": "T",
    "used_krw": 4997501.0,
    "uuid": "u-1"
   },
   "sleeps": [
    1.0
   ]
  },
  "balance_shrinks_between_attempts": {
   "buy_calls": [
    [
     "KRW-TRACE",
     1499250
    ],
    [
     "KRW-TRACE",
     1499250
    ]
   ],
   "krw_reads": 3,
   "last_buy_error": null,
   "logs": [
    [
     "INFO",
     "🚨 [LIVE] 시장가 매수 요청 전송: KRW-TRACE (예상가≈1,000.00 KRW, 사용 KRW ≈"
    ]
   ],
   "notify": [
    [
     "CRITICAL",
     "🟢 매수 요청 — KRW-TRACE"
    ]
   ],
   "orders": [
    [
     [
      "tracer",
      "KRW-TRACE",
      "BUY",
      1000.0,
      0,
      "requested"
     ],
     [
      [
       "entry_bar",
       7
      ],
      [
       "meta",
       "{\"reason\": \"EMA_GC\", \"bar\": 7}"
      ],
      [
       "provider_uuid",
       "u-1"
      ],
      [
       "settings_history_id",
       null
      ],
      [
       "state",
       "REQUESTED"
      ],
      [
       "strategy_type",
       "EMA"
      ]
     ]
    ]
   ],
   "result": {
    "price": 1000.0,
    "qty": 0.0,
    "side": "BUY",
    "time": "T",
    "used_krw": 1499250.0,
    "uuid": "u-1"
   },
   "sleeps": [
    1.0
   ]
  },
  "network_all_fail": {
   "buy_calls": [
    [
     "KRW-TRACE",
     4997501
    ],
    [
     "KRW-TRACE",
     4997501
    ],
    [
     "KRW-TRACE",
     4997501
    ]
   ],
   "krw_reads": 4,
   "last_buy_error": "Upbit error [network_exception]: x",
   "logs": [
    [
     "ERROR",
     "❌ Upbit 시장가 매수 실패 (attempts=3, non_retriable=False): Upbit e"
    ]
   ],
   "notify": [
    [
     "CRITICAL",
     "❌ 매수 거절 — KRW-TRACE"
    ]
   ],
   "orders": [
    [
     [
      "tracer",
      "KRW-TRACE",
      "BUY",
      1000.0,
      0.0,
      "FAILED"
     ],
     [
      [
       "entry_bar",
       7
      ],
      [
       "settings_history_id",
       null
      ],
      [
       "state",
       "FAILED"
      ],
      [
       "strategy_type",
       "EMA"
      ]
     ]
    ]
   ],
   "result": {},
   "sleeps": [
    1.0,
    2.0
   ]
  },
  "network_then_success": {
   "buy_calls": [
    [
     "KRW-TRACE",
     4997501
    ],
    [
     "KRW-TRACE",
     4997501
    ]
   ],
   "krw_reads": 3,
   "last_buy_error": null,
   "logs": [
    [
     "INFO",
     "🚨 [LIVE] 시장가 매수 요청 전송: KRW-TRACE (예상가≈1,000.00 KRW, 사용 KRW ≈"
    ]
   ],
   "notify": [
    [
     "CRITICAL",
     "🟢 매수 요청 — KRW-TRACE"
    ]
   ],
   "orders": [
    [
     [
      "tracer",
      "KRW-TRACE",
      "BUY",
      1000.0,
      0,
      "requested"
     ],
     [
      [
       "entry_bar",
       7
      ],
      [
       "meta",
       "{\"reason\": \"EMA_GC\", \"bar\": 7}"
      ],
      [
       "provider_uuid",
       "u-1"
      ],
      [
       "settings_history_id",
       null
      ],
      [
       "state",
       "REQUESTED"
      ],
      [
       "strategy_type",
       "EMA"
      ]
     ]
    ]
   ],
   "result": {
    "price": 1000.0,
    "qty": 0.0,
    "side": "BUY",
    "time": "T",
    "used_krw": 4997501.0,
    "uuid": "u-1"
   },
   "sleeps": [
    1.0
   ]
  },
  "no_uuid_then_success": {
   "buy_calls": [
    [
     "KRW-TRACE",
     4997501
    ],
    [
     "KRW-TRACE",
     4997501
    ]
   ],
   "krw_reads": 3,
   "last_buy_error": null,
   "logs": [
    [
     "INFO",
     "🚨 [LIVE] 시장가 매수 요청 전송: KRW-TRACE (예상가≈1,000.00 KRW, 사용 KRW ≈"
    ]
   ],
   "notify": [
    [
     "CRITICAL",
     "🟢 매수 요청 — KRW-TRACE"
    ]
   ],
   "orders": [
    [
     [
      "tracer",
      "KRW-TRACE",
      "BUY",
      1000.0,
      0,
      "requested"
     ],
     [
      [
       "entry_bar",
       7
      ],
      [
       "meta",
       "{\"reason\": \"EMA_GC\", \"bar\": 7}"
      ],
      [
       "provider_uuid",
       "u-1"
      ],
      [
       "settings_history_id",
       null
      ],
      [
       "state",
       "REQUESTED"
      ],
      [
       "strategy_type",
       "EMA"
      ]
     ]
    ]
   ],
   "result": {
    "price": 1000.0,
    "qty": 0.0,
    "side": "BUY",
    "time": "T",
    "used_krw": 4997501.0,
    "uuid": "u-1"
   },
   "sleeps": [
    1.0
   ]
  },
  "non_retriable": {
   "buy_calls": [
    [
     "KRW-TRACE",
     4997501
    ]
   ],
   "krw_reads": 2,
   "last_buy_error": "Upbit error [insufficient_funds_bid]: m",
   "logs": [
    [
     "ERROR",
     "❌ Upbit 시장가 매수 실패 (attempts=1, non_retriable=True): Upbit er"
    ]
   ],
   "notify": [
    [
     "CRITICAL",
     "❌ 매수 거절 — KRW-TRACE"
    ]
   ],
   "orders": [
    [
     [
      "tracer",
      "KRW-TRACE",
      "BUY",
      1000.0,
      0.0,
      "FAILED"
     ],
     [
      [
       "entry_bar",
       7
      ],
      [
       "settings_history_id",
       null
      ],
      [
       "state",
       "FAILED"
      ],
      [
       "strategy_type",
       "EMA"
      ]
     ]
    ]
   ],
   "result": {},
   "sleeps": []
  },
  "retriable_all_fail": {
   "buy_calls": [
    [
     "KRW-TRACE",
     4997501
    ],
    [
     "KRW-TRACE",
     4997501
    ],
    [
     "KRW-TRACE",
     4997501
    ]
   ],
   "krw_reads": 4,
   "last_buy_error": "Upbit error [too_many_request]: m",
   "logs": [
    [
     "ERROR",
     "❌ Upbit 시장가 매수 실패 (attempts=3, non_retriable=False): Upbit e"
    ]
   ],
   "notify": [
    [
     "CRITICAL",
     "❌ 매수 거절 — KRW-TRACE"
    ]
   ],
   "orders": [
    [
     [
      "tracer",
      "KRW-TRACE",
      "BUY",
      1000.0,
      0.0,
      "FAILED"
     ],
     [
      [
       "entry_bar",
       7
      ],
      [
       "settings_history_id",
       null
      ],
      [
       "state",
       "FAILED"
      ],
      [
       "strategy_type",
       "EMA"
      ]
     ]
    ]
   ],
   "result": {},
   "sleeps": [
    1.0,
    2.0
   ]
  },
  "success": {
   "buy_calls": [
    [
     "KRW-TRACE",
     4997501
    ]
   ],
   "krw_reads": 2,
   "last_buy_error": null,
   "logs": [
    [
     "INFO",
     "🚨 [LIVE] 시장가 매수 요청 전송: KRW-TRACE (예상가≈1,000.00 KRW, 사용 KRW ≈"
    ]
   ],
   "notify": [
    [
     "CRITICAL",
     "🟢 매수 요청 — KRW-TRACE"
    ]
   ],
   "orders": [
    [
     [
      "tracer",
      "KRW-TRACE",
      "BUY",
      1000.0,
      0,
      "requested"
     ],
     [
      [
       "entry_bar",
       7
      ],
      [
       "meta",
       "{\"reason\": \"EMA_GC\", \"bar\": 7}"
      ],
      [
       "provider_uuid",
       "u-1"
      ],
      [
       "settings_history_id",
       null
      ],
      [
       "state",
       "REQUESTED"
      ],
      [
       "strategy_type",
       "EMA"
      ]
     ]
    ]
   ],
   "result": {
    "price": 1000.0,
    "qty": 0.0,
    "side": "BUY",
    "time": "T",
    "used_krw": 4997501.0,
    "uuid": "u-1"
   },
   "sleeps": []
  }
 }
}
''')
