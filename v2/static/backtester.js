let tradeRows=[], weeklyRows=[], monthlyRows=[], sweepRows=[];
let lastBars=null, lastMaTrend=null, lastMa200=null, lastSlope60=null, lastMaPullback=null, lastCfgBase=null, lastResults=null;
let dataCache=null; // {symbol,interval,days,bars,fetchedAt} — 같은 심볼·원본 봉이면 재조회 없이 재사용(기간이 짧아지면 잘라서 사용)
let sweepRunning=false;
let chartState=null;
let chartViewStart=null; // 휠 줌으로 특정 시점(커서 위치)에 고정해서 본 경우의 시작 인덱스. null이면 항상 최신 봉 기준(전체 화면).
const $=id=>document.getElementById(id);
const sleep=ms=>new Promise(r=>setTimeout(r,ms));

function fmt(n,d=3){
  return Number(n).toLocaleString(undefined,{maximumFractionDigits:d,minimumFractionDigits:d});
}

// 한 번의 klines 요청을 여러 미러/엔드포인트로 순서대로 시도하고, 요청수 제한(429/418) 등 일시적 오류는
// 자동으로 잠시 대기 후 재시도합니다. 모든 시도가 실패하면 "마지막으로 무엇을 시도했는지"를 알 수 있는
// 구체적인 에러 메시지를 던져서, 화면에 뜨는 "Failed to fetch"만으로는 알 수 없는 원인 파악을 돕습니다.
async function fetchOneKlinesPage(symbol, interval, cursor, end){
  const endpoints=[
    "https://data-api.binance.vision/api/v3/klines",
    "https://api.binance.com/api/v3/klines",
    "https://api1.binance.com/api/v3/klines"
  ];
  const qs="?symbol="+encodeURIComponent(symbol)+"&interval="+interval+
    "&startTime="+cursor+"&endTime="+end+"&limit=1000";
  let lastErr=null;
  for(const base of endpoints){
    for(let attempt=0; attempt<3; attempt++){
      try{
        const r=await fetch(base+qs);
        if(r.status===429 || r.status===418){
          // 요청수 제한(레이트리밋)에 걸림 — 짧게 쉬었다가 같은 엔드포인트로 재시도
          const retryAfter=Number(r.headers.get("Retry-After"))||0;
          await sleep(Math.max(1500,retryAfter*1000)*(attempt+1));
          lastErr=new Error(base+" 요청수 제한(HTTP "+r.status+")");
          continue;
        }
        if(!r.ok){ lastErr=new Error(base+" 응답 오류(HTTP "+r.status+")"); break; } // 4xx/5xx(제한 외)는 이 엔드포인트를 더 재시도하지 않고 다음 엔드포인트로
        return await r.json();
      }catch(e){
        // fetch 자체가 실패(네트워크 끊김, CORS, 방화벽/VPN 차단, DNS 실패 등) — 브라우저 콘솔에는 보통
        // "TypeError: Failed to fetch"로만 표시되어 원인을 구분하기 어려우므로, 어느 주소에서 실패했는지를 남깁니다.
        lastErr=new Error(base+" 연결 실패(네트워크/방화벽/VPN/CORS 등 — 원본 메시지: "+e.message+")");
        if(attempt<2) await sleep(800*(attempt+1));
      }
    }
  }
  throw lastErr||new Error("알 수 없는 오류");
}

async function fetchKlinesRaw(symbol, interval, days){
  const msPer={"1m":60000,"3m":180000,"5m":300000,"15m":900000,"30m":1800000,"1h":3600000}[interval]||300000;
  const end=Date.now(), start=end-days*86400000;
  let cursor=start,out=[],req=0;

  while(cursor<end){
    const data=await fetchOneKlinesPage(symbol,interval,cursor,end);
    if(!Array.isArray(data)||!data.length)break;
    for(const x of data)out.push({t:+x[0],o:+x[1],h:+x[2],l:+x[3],c:+x[4]});
    const next=+data[data.length-1][0]+msPer;
    if(next<=cursor)break;
    cursor=next;req++;
    $("status").textContent=`데이터 수집 중... ${req}회 / ${out.length.toLocaleString()}개 봉`;
    await sleep(200);
  }
  return [...new Map(out.map(x=>[x.t,x])).values()].sort((a,b)=>a.t-b.t);
}

// 바이낸스는 10분봉을 제공하지 않으므로 5분봉 2개를 실제 시계 기준 10분 경계(0,10,20...분)로 묶어 합성합니다.
// 아직 2번째 5분봉이 없는 마지막 그룹(미완성)은 버립니다.
function aggregateBars(bars, groupMs, sourceMs){
  const map=new Map();
  for(const b of bars){
    const key=Math.floor(b.t/groupMs)*groupMs;
    if(!map.has(key)) map.set(key,[]);
    map.get(key).push(b);
  }
  const expected=Math.round(groupMs/sourceMs);
  const out=[];
  for(const k of [...map.keys()].sort((a,b)=>a-b)){
    const g=map.get(k).sort((a,b)=>a.t-b.t);
    if(g.length<expected) continue;
    out.push({t:k,o:g[0].o,h:Math.max(...g.map(x=>x.h)),l:Math.min(...g.map(x=>x.l)),c:g[g.length-1].c});
  }
  return out;
}

async function fetchKlines(symbol, interval, days){
  if(interval==="10m") return aggregateBars(await fetchKlinesRaw(symbol,"5m",days),600000,300000);
  return fetchKlinesRaw(symbol,interval,days);
}

// 같은 심볼·원본 봉으로 이미 받아둔 데이터가 요청 기간을 덮으면 재조회 없이 재사용합니다.
async function getBars(symbol, interval, days, forceRefresh){
  if(!forceRefresh && dataCache && dataCache.symbol===symbol && dataCache.interval===interval && dataCache.days>=days){
    const cutoff=dataCache.fetchedAt-days*86400000;
    const bars=dataCache.days===days?dataCache.bars:dataCache.bars.filter(b=>b.t>=cutoff);
    return {bars,cached:true,ageMin:(Date.now()-dataCache.fetchedAt)/60000};
  }
  const bars=await fetchKlines(symbol,interval,days);
  dataCache={symbol,interval,days,bars,fetchedAt:Date.now()};
  return {bars,cached:false,ageMin:0};
}

function computeSMA(bars,period){
  const out=new Array(bars.length).fill(null);
  let sum=0;
  for(let i=0;i<bars.length;i++){
    sum+=bars[i].c;
    if(i>=period) sum-=bars[i-period].c;
    if(i>=period-1) out[i]=sum/period;
  }
  return out;
}

// EMA: 첫 period개 종가의 단순평균으로 시드를 만든 뒤(index period-1),
// 이후 매 봉마다 k=2/(period+1) 가중치로 재귀 계산. SMA와 동일하게 첫 period-1개는 null.
function computeEMA(bars,period){
  const out=new Array(bars.length).fill(null);
  if(bars.length<period) return out;
  const k=2/(period+1);
  let sum=0;
  for(let i=0;i<period;i++) sum+=bars[i].c;
  let prev=sum/period;
  out[period-1]=prev;
  for(let i=period;i<bars.length;i++){
    prev=bars[i].c*k+prev*(1-k);
    out[i]=prev;
  }
  return out;
}

function computeMA(bars,period,type){
  return type==="sma" ? computeSMA(bars,period) : computeEMA(bars,period);
}

function computeSlope(ma,lookback){
  const out=new Array(ma.length).fill(null);
  for(let i=0;i<ma.length;i++){
    const j=i-lookback;
    if(j>=0 && ma[j]!=null && ma[i]!=null && ma[j]!==0){
      out[i]=(ma[i]-ma[j])/Math.abs(ma[j])*100;
    }
  }
  return out;
}

function isFilterActive(i,maTrend,ma200,slope60,cfg){
  if(maTrend[i]==null||ma200[i]==null) return false;
  if(!(maTrend[i]>ma200[i])) return false;             // 골든크로스 상태(MA60 vs MA200, 고정)
  // 60선 기울기 필터: MA60이 MA200 위에 있어도(골든크로스) MA60 자체가 평평/하락이면 매수 감시를 끔
  if(slope60[i]==null) return false;
  if(slope60[i]<cfg.ma60MinSlope) return false;
  if(cfg.ma60SlopeDrop>0){
    const j2=i-cfg.slopeLB;
    if(j2>=0 && slope60[j2]!=null){
      if((slope60[j2]-slope60[i])>cfg.ma60SlopeDrop) return false;
    }
  }
  return true;
}

/*
  분할마다 동일 비중(1→1)으로 매수합니다. 자본은 분할 횟수(sumW=maxSplits)로 균등 배분되므로
  모든 분할이 체결되면 총 투입액은 기준 자본(sizingBase)과 같아집니다(그리드 자본 배분 방식과 동일).
*/
function simulate(bars,maTrend,ma200,slope60,maPullback,cfg){
  // 분할매수 최대 횟수가 0이면서 "골든크로스 시 1차 매수"가 켜져 있으면, 골든크로스 즉시진입 1회만
  // 허용하고 눌림목 추가매수는 전부 차단하는 특수 모드입니다(실제 분할 수는 내부적으로 1로 취급).
  const goldenOnlyMode = cfg.buyOnGoldenCross && cfg.maxSplits===0;
  const effMaxSplits = goldenOnlyMode ? 1 : cfg.maxSplits;
  const weights=Array.from({length:effMaxSplits},()=>1);
  const sumW=weights.reduce((a,b)=>a+b,0);

  let equity=cfg.capital, peak=equity, maxDD=0;
  const trades=[];
  const entries=[]; // 분할매수 1회 체결마다 기록 (주간/월간 투자금액·투자횟수 집계용)
  const depth=Array.from({length:effMaxSplits},()=>({n:0,w:0,pnl:0}));

  let qty=0,cost=0,entryFees=0,entryCount=0,firstEntryTime=null,firstEntryTrigger=null,pullbackEntryCount=0;
  let firstEntrySlope60=null,firstEntryGap200=null; // 최초 진입 시점의 60선 기울기% / 장기선 대비 이격도%(거래로그 CSV 기록용)
  let gcGapBlocked=0; // G/C 매수제한 상승폭 때문에 골든크로스 즉시진입을 건너뛴 횟수
  const gapPct=i=>(ma200[i]!=null&&ma200[i]!==0)?(bars[i].c-ma200[i])/ma200[i]*100:null;
  let currentTradeTpPct=null,firstEntryEpisodeIdx=null; // (신규) 이번 거래에 실제 적용되는 TP%와, 진입 시점의 "구간 내 눌림목 돌파 순번"
  let pullbackArmed=false;
  let prevGolden=false; // 직전 봉이 골든크로스 상태였는지(이번 봉에서 "막 골든크로스로 전환"됐는지 판정용)
  let consecutiveSl=0,pauseUntil=null,pauseTriggers=0; // (신규) 연속 SL 자동 매수 중단용 상태
  let episodePullbackCount=0; // (신규) 지금 골든크로스 구간(데드크로스 없이 이어진 구간) 안에서 누적된 눌림목 돌파 체결 횟수
  let tsArmed=false,tsPeak=null,tsFixed=null; // 기준 파일과 다름 — 1110-01: 추적 손절(트레일링 스톱) 무장·최고 종가·고정 금액

  function updateDD(){
    if(equity>peak) peak=equity;
    if(peak>0) maxDD=Math.max(maxDD,(peak-equity)/peak*100);
  }

  function closePosition(i,price,type){
    const gross=qty*price;
    const exitFee=gross*cfg.fee/100;
    const pnl=gross-cost-entryFees-exitFee;
    equity+=pnl;
    updateDD();
    trades.push({
      exitType:type,
      entries:entryCount,
      firstEntryTrigger:firstEntryTrigger,
      entryMa60SlopePct:firstEntrySlope60,
      entryGapToMa200Pct:firstEntryGap200,
      episodeBreakoutIndex:firstEntryEpisodeIdx,
      tpUsedPct:currentTradeTpPct,
      avg:cost/qty,
      exit:price,
      entryTime:new Date(firstEntryTime).toISOString(),
      exitTime:new Date(bars[i].t).toISOString(),
      holdHours:(bars[i].t-firstEntryTime)/3600000,
      pnl:pnl,
      returnPct:cost?pnl/cost*100:0,
      fees:entryFees+exitFee
    });
    for(let k=0;k<entryCount;k++){
      depth[k].n++;
      if(pnl>0)depth[k].w++;
      depth[k].pnl+=pnl;
    }
    qty=0;cost=0;entryFees=0;entryCount=0;firstEntryTime=null;firstEntryTrigger=null;pullbackEntryCount=0;
    firstEntrySlope60=null;firstEntryGap200=null;
    currentTradeTpPct=null;firstEntryEpisodeIdx=null;
    pullbackArmed=false;
    tsArmed=false;tsPeak=null;tsFixed=null; // 기준 파일과 다름 — 1110-01: 청산 때 추적 손절 상태 초기화
    // (신규) 연속 SL 자동 매수 중단: SL이 아닌 청산(TP/DEADCROSS)이 나오면 연속 카운트를 리셋하고,
    // SL이면 카운트를 올려 임계값에 도달하는 순간 중단 시작 시각을 기록합니다.
    if(type==="SL"){
      consecutiveSl++;
      if(cfg.slStreakPause>0 && consecutiveSl>=cfg.slStreakPause && pauseUntil==null){
        pauseUntil=bars[i].t+cfg.slStreakCooldownHours*3600000;
        pauseTriggers++;
      }
    }else{
      consecutiveSl=0;
    }
  }

  for(let i=0;i<bars.length;i++){
    const b=bars[i];
    if(pauseUntil!=null && b.t>=pauseUntil){ pauseUntil=null; consecutiveSl=0; } // 중단 지속시간 만료 -> 연속 SL 카운트 리셋 후 재개
    const streakPaused = pauseUntil!=null;
    const active=isFilterActive(i,maTrend,ma200,slope60,cfg);
    const wasGolden=prevGolden;
    const golden=maTrend[i]!=null&&ma200[i]!=null&&maTrend[i]>ma200[i];
    prevGolden=golden; // continue로 빠지는 경로가 있어도 누락 없이 항상 갱신
    const justCrossedGolden=golden && !wasGolden;
    if(justCrossedGolden) episodePullbackCount=0; // (신규) 새 골든크로스 구간 시작 -> 구간 내 눌림목 돌파 카운트 리셋

    // 데드크로스 발생 시 강제청산
    if(qty>0 && cfg.deadcross==="yes" && maTrend[i]!=null && ma200[i]!=null && !(maTrend[i]>ma200[i])){
      closePosition(i,b.c,"DEADCROSS");
      continue;
    }

    // TP / SL 체크 (진입 당일 봉은 평가하지 않음 — 그리드 백테스터와 동일 규칙)
    if(qty>0 && firstEntryTime!=null && b.t>firstEntryTime){
      const avg=cost/qty;
      const tpPrice=avg*(1+(currentTradeTpPct!=null?currentTradeTpPct:cfg.tp)/100);
      const slPrice=avg*(1-cfg.sl/100);
      if(cfg.trailingStop!=="yes"){ // 기준 파일과 다름 — 1110-01: 추적 손절 꺼짐이면 원래 규칙 그대로
      if(b.h>=tpPrice){ closePosition(i,tpPrice,"TP"); continue; }
      if(b.l<=slPrice){ closePosition(i,slPrice,"SL"); continue; }
      }else{ // 기준 파일과 다름 — 1110-01: 켜짐 — 손절(저가) 먼저, 그다음 추적 손절(종가). 구버전 EMA 와 같은 식
        if(b.l<=slPrice){ closePosition(i,slPrice,"SL"); continue; }
        const tsPct=cfg.trailingPct/100, tpPctNow=(currentTradeTpPct!=null?currentTradeTpPct:cfg.tp)/100;
        if(!tsArmed && (b.c-avg)/avg>=tpPctNow){ tsArmed=true; tsPeak=b.c; tsFixed=cfg.trailingMode==="fixed"?(b.c-avg)*tsPct:null; }
        if(tsArmed){
          if(b.c>tsPeak) tsPeak=b.c;
          const tsHit=cfg.trailingMode==="fixed" ? b.c<=tsPeak-tsFixed : ((tsPeak-avg)>0?(tsPeak-b.c)/(tsPeak-avg):0)>=tsPct;
          if(tsHit){ closePosition(i,b.c,"TS"); continue; }
        }
      }
    }

    const sizingBase=cfg.compounding==="yes"?equity:cfg.capital;

    // (신규) 골든크로스 시 1차 매수: 눌림목을 기다리지 않고, 골든크로스로 막 전환된(또는 조회 시작 시점에
    // 이미 골든크로스인) 바로 다음 캔들 시가에 1회차 분할매수를 즉시 체결합니다. 포지션이 없을 때만(entryCount===0) 적용되며,
    // 체결 후에는 같은 봉에서 눌림목 조건을 다시 평가하지 않고 다음 봉으로 넘어갑니다(2회차부터는 기존 눌림목 재돌파 로직 사용).
    // G/C 매수제한 상승폭: 골든크로스 봉 종가가 장기선(MA200)보다 설정% 이상 위면 즉시진입을 건너뜀(0=무제한)
    let gcGapOk=true;
    if(cfg.gcMaxGapPct>0 && cfg.buyOnGoldenCross && justCrossedGolden && entryCount===0){
      const g=gapPct(i);
      if(g!=null && g>=cfg.gcMaxGapPct){ gcGapOk=false; if(active && !streakPaused && entryCount<effMaxSplits && (cfg.compounding!=="yes" || sizingBase>0) && i+1<bars.length) gcGapBlocked++; } // 기준 파일과 다름 — 1105-06 결정 ③: 실제로 살 수 있었던 골든크로스만 셈
    }
    if(cfg.buyOnGoldenCross && justCrossedGolden && gcGapOk && entryCount===0 && active && !streakPaused && entryCount<effMaxSplits &&
       (cfg.compounding!=="yes" || sizingBase>0) && i+1<bars.length){
      const nb=bars[i+1];
      const notional=(sizingBase/sumW)*weights[entryCount];
      const px=nb.o;
      const q=notional/px;
      const fee=notional*cfg.fee/100;
      qty+=q; cost+=notional; entryFees+=fee;
      firstEntryTrigger="GOLDEN";
      entryCount++;
      entries.push({time:nb.t,splitIndex:entryCount,price:px,qty:q,notional:notional,trigger:"GOLDEN"});
      if(firstEntryTime===null){ firstEntryTime=nb.t; firstEntrySlope60=slope60[i]; firstEntryGap200=gapPct(i); currentTradeTpPct=cfg.tp; }
      pullbackArmed=false;
      continue;
    }

    // 눌림목 → 재돌파 → 분할매수 (기준선은 maPullback: 기본 MA60이지만 별도 설정 가능)
    // 복리 모드: 새 거래(entryCount===0)가 시작되는 시점의 equity를 배분 기준 자본으로 사용.
    // 포지션 보유 중에는 equity가 realize 전까지 변하지 않으므로, 같은 거래의 2차 이후 분할도 동일 기준으로 계산됨.
    // goldenOnlyMode(분할매수 최대 횟수=0 + 골든크로스 시 1차 매수=예)에서는 눌림목 추가매수를 완전히 차단합니다.
    // 눌림목 매수는 전체 분할 한도(effMaxSplits)와 별개로, 눌림목 전용 횟수 한도(maxPullbackBuys)도 함께 적용됩니다.
    if(tsArmed) continue; // 기준 파일과 다름 — 1110-01 ㉢: 추적 손절 무장 중에는 추가 매수 안 함(눌림목 대기 상태도 그대로)
    const pullbackCapped = pullbackEntryCount>=cfg.maxPullbackBuys;
    if(!goldenOnlyMode && !pullbackCapped && !streakPaused && active && entryCount<effMaxSplits && (cfg.compounding!=="yes" || sizingBase>0)){
      if(maPullback[i]!=null && b.l<maPullback[i]) pullbackArmed=true;
      if(pullbackArmed && maPullback[i]!=null && b.c>maPullback[i] && i+1<bars.length){
        const nb=bars[i+1];
        const notional=(sizingBase/sumW)*weights[entryCount];
        const px=nb.o;
        const q=notional/px;
        const fee=notional*cfg.fee/100;
        qty+=q; cost+=notional; entryFees+=fee;
        if(entryCount===0) episodePullbackCount++; // 기준 파일과 다름 — 1105-06 Q3 ②: 새 거래를 연 눌림목 매수만 구간 순번에 셈
        if(entryCount===0) firstEntryTrigger="PULLBACK";
        entryCount++; pullbackEntryCount++;
        entries.push({time:nb.t,splitIndex:entryCount,price:px,qty:q,notional:notional,trigger:"PULLBACK"});
        if(firstEntryTime===null){
          firstEntryTime=nb.t; firstEntrySlope60=slope60[i]; firstEntryGap200=gapPct(i);
          firstEntryEpisodeIdx=episodePullbackCount;
          // (신규) "구간 내 눌림목 돌파 횟수" 설정을 초과한 순번의 재진입은 TP를 설정한 비율만큼 단계적으로 줄입니다
          // (예: 상한 2회, 감소율 50%일 때 3번째=TP*0.5, 4번째=TP*0.25, ...). 0(기본값)이면 이 기능은 꺼져 있고 항상 기본 TP를 씁니다.
          // 하한(episodeTpFloorPct)을 반드시 적용합니다 — 돌파가 수십 회 이어지면 지수적으로 감소한 TP가 수수료보다도
          // 작아져서(예: TP 0.0006%인데 왕복 수수료는 0.1%) 체결될 때마다 사실상 손실이 확정되는 상태가 되므로,
          // 아무리 돌파 횟수가 많아져도 TP가 이 값 밑으로는 더 줄어들지 않게 막아줍니다.
          if(cfg.episodePullbackCap>0 && episodePullbackCount>cfg.episodePullbackCap){
            const excess=episodePullbackCount-cfg.episodePullbackCap;
            currentTradeTpPct=Math.max(cfg.episodeTpFloorPct,cfg.tp*Math.pow(1-cfg.episodeTpDecayPct/100,excess));
          }else{
            currentTradeTpPct=cfg.tp;
          }
        }
        pullbackArmed=false;
      }
    }else if(!active || goldenOnlyMode || pullbackCapped || streakPaused){
      pullbackArmed=false;
    }
  }

  let mark=null;
  if(qty>0){
    const last=bars[bars.length-1];
    const gross=qty*last.c;
    const exitFee=gross*cfg.fee/100;
    const unrealized=gross-cost-entryFees-exitFee;
    mark={
      avg:cost/qty,
      mark:last.c,
      entries:entryCount,
      holdHours:firstEntryTime!=null?(last.t-firstEntryTime)/3600000:0,
      unrealizedPnl:unrealized,
      unrealizedReturnPct:cost?unrealized/cost*100:0
    };
  }

  return {trades,equity,maxDD,depth,mark,entries,pauseTriggers,gcGapBlocked};
}

function stats(res,cfg){
  const t=res.trades;
  const wins=t.filter(x=>x.pnl>0),loss=t.filter(x=>x.pnl<0);
  const gw=wins.reduce((s,x)=>s+x.pnl,0),gl=-loss.reduce((s,x)=>s+x.pnl,0);
  return {
    trades:t.length,wins:wins.length,losses:loss.length,
    winRate:t.length?wins.length/t.length*100:0,
    net:res.equity-cfg.capital,ret:(res.equity/cfg.capital-1)*100,
    avg:t.length?(res.equity-cfg.capital)/t.length:0,
    pf:gl?gw/gl:(gw?Infinity:0),mdd:res.maxDD,
    tp:t.filter(x=>x.exitType==="TP").length,
    sl:t.filter(x=>x.exitType==="SL").length,
    deadcross:t.filter(x=>x.exitType==="DEADCROSS").length,
    ts:t.filter(x=>x.exitType==="TS").length, // 기준 파일과 다름 — 1110-01
    maxSplit:t.reduce((m,x)=>Math.max(m,x.entries),0),
    avgSplit:t.length?t.reduce((s,x)=>s+x.entries,0)/t.length:0,
    goldenStart:t.filter(x=>x.firstEntryTrigger==="GOLDEN").length,
    pullbackStart:t.filter(x=>x.firstEntryTrigger==="PULLBACK").length,
    pullbackFills:res.entries.filter(e=>e.trigger==="PULLBACK").length,
    slStreakPauses:res.pauseTriggers||0,
    gcGapBlocked:res.gcGapBlocked||0,
    mark:res.mark
  };
}

function render(res,cfg,bars){
  const s=stats(res,cfg);
  const rows=[
    ["데이터 봉 수",bars.length.toLocaleString()],
    ["완료 거래",s.trades],
    ["승률",fmt(s.winRate)+"%"],
    ["순손익 (USDT)",fmt(s.net)],
    ["수익률",fmt(s.ret)+"%"],
    ["평균 거래손익",fmt(s.avg)],
    ["Profit Factor",isFinite(s.pf)?fmt(s.pf):"∞"],
    ["MDD",fmt(s.mdd)+"%"],
    ["TP 청산",s.tp],
    ["SL 청산",s.sl],
    ["데드크로스 강제청산",s.deadcross],
    ...(cfg.trailingStop==="yes"?[["추적 손절 청산",s.ts]]:[]), // 기준 파일과 다름 — 1110-01
    ["최대 분할 도달",s.maxSplit],
    ["평균 분할 횟수",fmt(s.avgSplit)],
    ["골든크로스 즉시진입으로 시작한 거래",s.goldenStart],
    ["눌림목 재돌파로 시작한 거래",s.pullbackStart],
    ["눌림목 매수 체결 횟수(전체, 캡="+cfg.maxPullbackBuys+")",s.pullbackFills],
    ["연속 SL 중단 발생 횟수(임계값="+cfg.slStreakPause+")",s.slStreakPauses],
    ["G/C 상승폭 제한으로 건너뛴 즉시진입("+(cfg.gcMaxGapPct>0?cfg.gcMaxGapPct+"% 이상":"무제한")+")",s.gcGapBlocked]
  ];
  let h="<h2>백테스트 결과</h2><table><tr><th>항목</th><th>동일수량 분할(1→1)</th></tr>";
  rows.forEach(r=>h+=`<tr><td>${r[0]}</td><td>${r[1]}</td></tr>`);
  h+="</table>";

  function markText(m){
    if(!m)return "없음";
    return `미청산 1건 / 분할 ${m.entries}회 / 평균 ${fmt(m.avg)} / 현재가 ${fmt(m.mark)} / 미실현 ${fmt(m.unrealizedPnl)} USDT / 보유 ${fmt(m.holdHours)}시간`;
  }
  h+=`<p class="note"><b>MARK(미청산)</b> — ${markText(s.mark)}<br>
  MARK는 완료 거래·실현손익·수익률에 포함하지 않습니다.</p>`;
  $("summary").innerHTML=h;

  let d="<h2>분할 단계별 누적 통계</h2><table><tr><th>최소 도달 단계</th><th>거래수</th><th>승률</th><th>손익</th></tr>";
  const effMaxSplitsForTable=(cfg.buyOnGoldenCross && cfg.maxSplits===0)?1:cfg.maxSplits;
  for(let i=0;i<effMaxSplitsForTable;i++){
    const a=res.depth[i];
    if(a.n)d+=`<tr><td>${i+1}차 분할</td><td>${a.n}</td><td>${a.n?fmt(a.w/a.n*100):"0.0"}%</td><td>${fmt(a.pnl)}</td></tr>`;
  }
  d+="</table>";
  $("depth").innerHTML=d;
  $("status").textContent=`완료: ${bars.length.toLocaleString()}개 봉. MA=${cfg.maType==="sma"?"SMA":"EMA"}, 골든크로스 즉시진입=${cfg.buyOnGoldenCross?"예":"아니오"}, 데드크로스 강제청산=${cfg.deadcross==="yes"?"예":"아니오"}, 복리=${cfg.compounding==="yes"?"예":"아니오"}.`;
}

// ---- 한국시간(KST=UTC+9) 기준 주간/월간 집계 ----
// 트릭: utcMs에 9시간을 더한 뒤 UTC getter로 읽으면 KST 달력상의 연/월/일이 그대로 나온다.
const KST_OFFSET=9*3600000;
function kstParts(utcMs){
  const d=new Date(utcMs+KST_OFFSET);
  return {y:d.getUTCFullYear(),mo:d.getUTCMonth(),da:d.getUTCDate(),isoDow:(d.getUTCDay()===0?7:d.getUTCDay())};
}
function kstWeekStartUtc(utcMs){
  const p=kstParts(utcMs);
  const mondayShifted=Date.UTC(p.y,p.mo,p.da)-(p.isoDow-1)*86400000;
  return mondayShifted-KST_OFFSET;
}
function kstMonthStartUtc(utcMs){
  const p=kstParts(utcMs);
  return Date.UTC(p.y,p.mo,1)-KST_OFFSET;
}
function kstDateLabel(utcMs){
  const p=kstParts(utcMs);
  return `${p.y}-${String(p.mo+1).padStart(2,"0")}-${String(p.da).padStart(2,"0")}`;
}
function kstMonthLabel(utcMs){
  const p=kstParts(utcMs);
  return `${p.y}-${String(p.mo+1).padStart(2,"0")}`;
}
// CSV 등 사람이 읽는 타임스탬프용 — 한국시간(KST) "YYYY-MM-DD HH:MM:SS"
function kstStamp(utcMs){
  const d=new Date(utcMs+KST_OFFSET);
  const p=n=>String(n).padStart(2,"0");
  return `${d.getUTCFullYear()}-${p(d.getUTCMonth()+1)}-${p(d.getUTCDate())} ${p(d.getUTCHours())}:${p(d.getUTCMinutes())}:${p(d.getUTCSeconds())}`;
}

// entries(분할매수 체결 시각 기준)로 투자횟수·투자금액을, trades(청산 시각 기준)로 손익을 같은 기간 버킷에 모은다.
function aggregateByPeriod(entries,trades,keyFn){
  const map=new Map();
  const get=k=>{ if(!map.has(k)) map.set(k,{investCount:0,investAmount:0,pnl:0}); return map.get(k); };
  for(const e of entries){ const b=get(keyFn(e.time)); b.investCount++; b.investAmount+=e.notional; }
  for(const t of trades){ const b=get(keyFn(new Date(t.exitTime).getTime())); b.pnl+=t.pnl; }
  return map;
}
// returnPct는 그 기간 손익이 "초기자본" 대비 전체 수익률에 기여한 비율입니다(그 기간 투자금액이 아님).
// 이렇게 해야 모든 기간의 returnPct를 합치면 상단 요약의 전체 수익률과 정확히 일치합니다.
function withReturn(d,baseCapital){ return {...d, returnPct: baseCapital? d.pnl/baseCapital*100 : 0}; }

function buildTimeframeRows(res,keyFn,labelFn,endLabelFn,baseCapital){
  const map=aggregateByPeriod(res.entries,res.trades,keyFn);
  const keys=[...map.keys()].sort((a,b)=>a-b);
  return keys.map(k=>({
    periodStart:k,
    periodLabel:labelFn(k),
    periodEndLabel:endLabelFn?endLabelFn(k):null,
    ...withReturn(map.get(k),baseCapital)
  }));
}

function periodRowHtml(label,d,highlight,showInvest){
  const cls=highlight?" class=\"highlight\"":"";
  const ret=d.returnPct===null?"-":fmt(d.returnPct,2)+"%";
  if(showInvest){
    return `<tr${cls}><td>${label}</td><td>${d.investCount}</td><td>${fmt(d.investAmount)}</td><td>${fmt(d.pnl)}</td><td>${ret}</td></tr>`;
  }
  return `<tr${cls}><td>${label}</td><td>${fmt(d.pnl)}</td><td>${ret}</td></tr>`;
}
function sumRows(rows,baseCapital){
  const t={investCount:0,investAmount:0,pnl:0};
  rows.forEach(d=>{ t.investCount+=d.investCount; t.investAmount+=d.investAmount; t.pnl+=d.pnl; });
  return withReturn(t,baseCapital);
}

function renderWeekly(rows,baseCapital){
  if(!rows.length){ $("weekly").innerHTML="<h2>주간 성과 (한국시간, 월~일)</h2><p class=\"small\">표시할 거래가 없습니다.</p>"; return; }
  let h="<h2>주간 성과 (한국시간, 월~일)</h2><table><tr><th>주</th><th>투자횟수</th><th>투자금액</th><th>수익금액</th><th>수익률</th></tr>";
  rows.forEach(r=>{
    const label=`${r.periodLabel} ~ ${r.periodEndLabel}`;
    h+=periodRowHtml(label,r,false,true);
  });
  h+=periodRowHtml("합계",sumRows(rows,baseCapital),true,true);
  h+="</table><p class=\"small\">투자금액=그 주에 새로 체결된 분할매수 원금 합계, 수익금액=그 주에 청산(TP/SL/DEADCROSS)된 거래의 손익 합계. <b>수익률=그 주 수익금액÷초기자본×100</b>(그 주 투자금액이 아닌 전체 초기자본 기준 — 이렇게 해야 모든 주의 수익률을 더하면 상단 요약의 전체 수익률과 정확히 일치합니다). 포지션이 여러 주에 걸쳐 있다가 나중에 청산되면 그 주는 투자금액 없이 수익금액·수익률만 잡힐 수 있습니다(미청산 MARK 제외).</p>";
  $("weekly").innerHTML=h;
}

function renderMonthly(rows,baseCapital){
  if(!rows.length){ $("monthly").innerHTML="<h2>월간 성과 (한국시간)</h2><p class=\"small\">표시할 거래가 없습니다.</p>"; return; }
  let h="<h2>월간 성과 (한국시간)</h2><table><tr><th>월</th><th>순수익금</th><th>수익률</th></tr>";
  rows.forEach(r=>{
    h+=periodRowHtml(r.periodLabel,r,false,false);
  });
  h+=periodRowHtml("합계",sumRows(rows,baseCapital),true,false);
  h+="</table><p class=\"small\">순수익금=그 달에 청산된 거래의 손익 합계. <b>수익률=그 달 순수익금÷초기자본×100</b>(전체 초기자본 기준 — 모든 달의 수익률을 더하면 상단 요약의 전체 수익률과 정확히 일치합니다).</p>";
  $("monthly").innerHTML=h;
}

async function run(){
  tradeRows=[];weeklyRows=[];monthlyRows=[];$("summary").innerHTML="";$("depth").innerHTML="";$("weekly").innerHTML="";$("monthly").innerHTML="";
  const cfg={
    maType:$("maType").value,
    ma60p:+$("ma60p").value, ma200p:+$("ma200p").value,
    pullbackP:+$("pullbackP").value||+$("ma60p").value,
    slopeLB:+$("slopeLB").value,
    gcMaxGapPct:Math.max(0,+$("gcMaxGapPct").value||0),
    ma60MinSlope:+$("ma60MinSlope").value, ma60SlopeDrop:+$("ma60SlopeDrop").value,
    slStreakPause:Math.max(0,Math.round(+$("slStreakPause").value||0)),
    slStreakCooldownHours:Math.max(0,+$("slStreakCooldownHours").value||0),
    episodePullbackCap:Math.max(0,Math.round(+$("episodePullbackCap").value||0)),
    episodeTpDecayPct:Math.max(0,Math.min(99,+$("episodeTpDecayPct").value||0)),
    episodeTpFloorPct:Math.max(0,+$("episodeTpFloorPct").value||0),
    buyOnGoldenCross:$("buyOnGoldenCross").value==="yes",
    maxSplits:Math.max(0,Math.min(10,+$("maxSplits").value)),
    maxPullbackBuys:Math.max(1,Math.min(5,+$("maxPullbackBuys").value||5)),
    tp:+$("tp").value, sl:+$("sl").value,
    capital:+$("capital").value, fee:+$("fee").value,
    deadcross:$("deadcross").value,
    compounding:$("compounding").value,
    // 기준 파일과 다름 — 1110-01: 추적 손절 3칸(없으면 꺼짐)
    trailingStop:$("trailingStop")?$("trailingStop").value:"no",
    trailingMode:$("trailingMode")?$("trailingMode").value:"ratio",
    trailingPct:$("trailingPct")?+$("trailingPct").value:50
  };
  try{
    const forceRefresh=$("forceRefresh").checked;
    const got=await getBars($("symbol").value.trim().toUpperCase(),$("src").value,+$("days").value,forceRefresh);
    if(forceRefresh) $("forceRefresh").checked=false; // 강제 새로고침은 1회만 적용
    const bars=got.bars;
    const needBars=Math.max(cfg.ma200p,cfg.pullbackP)+10;
    if(bars.length<needBars)throw new Error(`가져온 데이터가 너무 적습니다. 최소 ${needBars}개 봉이 필요합니다(조회 기간을 늘려주세요).`);

    const ma60=computeMA(bars,cfg.ma60p,cfg.maType);       // 골든크로스 판정용(MA60 vs MA200)
    const ma200=computeMA(bars,cfg.ma200p,cfg.maType);
    const maPullback=computeMA(bars,cfg.pullbackP,cfg.maType); // 눌림목 재진입 기준선(20/60 등 선택)
    const slope60=computeSlope(ma60,cfg.slopeLB); // 60선 자체 기울기

    const res=simulate(bars,ma60,ma200,slope60,maPullback,cfg);
    // 거래로그 CSV는 내부 계산(ISO/UTC 기준 시각)과 별개로, 차트·주간/월간표와 동일한 한국시간(KST)으로 보이도록 변환해서 내보냅니다.
    tradeRows=res.trades.map(t=>({
      ...t,
      entryMa60SlopePct:t.entryMa60SlopePct!=null?+t.entryMa60SlopePct.toFixed(4):null,
      entryGapToMa200Pct:t.entryGapToMa200Pct!=null?+t.entryGapToMa200Pct.toFixed(4):null,
      tpUsedPct:t.tpUsedPct!=null?+t.tpUsedPct.toFixed(4):null,
      entryTime:kstStamp(new Date(t.entryTime).getTime())+" KST",
      exitTime:kstStamp(new Date(t.exitTime).getTime())+" KST"
    }));
    render(res,cfg,bars);
    $("status").textContent+=got.cached
      ? ` [데이터 재사용: ${got.ageMin.toFixed(1)}분 전에 받아온 데이터, 재조회 없음]`
      : ` [바이낸스에서 새로 조회함]`;

    const weekly=buildTimeframeRows(res,kstWeekStartUtc,kstDateLabel,k=>kstDateLabel(k+6*86400000),cfg.capital);
    renderWeekly(weekly,cfg.capital);
    weeklyRows=weekly.map(r=>({
      period:`${r.periodLabel} ~ ${r.periodEndLabel}`,
      investCount:r.investCount,investAmount:r.investAmount,pnl:r.pnl,returnPct:r.returnPct
    }));

    const monthly=buildTimeframeRows(res,kstMonthStartUtc,kstMonthLabel,undefined,cfg.capital);
    renderMonthly(monthly,cfg.capital);
    monthlyRows=monthly.map(r=>({period:r.periodLabel,pnl:r.pnl,returnPct:r.returnPct}));

    // 파라미터 스윕이 재사용할 수 있도록 이번 실행의 원본 데이터/이동평균/설정을 캐시
    lastBars=bars; lastMaTrend=ma60; lastMa200=ma200; lastSlope60=slope60; lastMaPullback=maPullback;
    lastCfgBase={...cfg};
    lastResults=res;
    $("sweepHint").textContent=`이번 조회 데이터(${bars.length.toLocaleString()}개 봉) 기준으로 스윕 가능합니다.`;
    chartViewStart=null; // 새 백테스트 결과는 항상 최신 봉 기준(전체 화면)으로 시작
    try{ renderChart(); }catch(chartErr){ $("chartHint").textContent="차트 렌더링 오류: "+chartErr.message; }
  }catch(e){$("status").textContent="오류: "+e.message;}
}

function csv(rows){
  if(!rows.length)return "";
  const keys=[...new Set(rows.flatMap(r=>Object.keys(r)))];
  return [keys.join(","),...rows.map(r=>keys.map(k=>`"${String(r[k]??"").replaceAll('"','""')}"`).join(","))].join("\n");
}
function dl(name,text){
  const a=document.createElement("a");
  a.href=URL.createObjectURL(new Blob(["﻿"+text],{type:"text/csv;charset=utf-8"}));
  a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);
}
function downloadTrades(){dl("ma_gc_pullback_trades.csv",csv(tradeRows))}
function downloadWeekly(){dl("ma_gc_pullback_weekly.csv",csv(weeklyRows))}
function downloadMonthly(){dl("ma_gc_pullback_monthly.csv",csv(monthlyRows))}
function downloadSweep(){dl("ma_gc_pullback_sweep.csv",csv(sweepRows))}

function frange(from,to,step){
  const out=[];
  if(!(step>0)||!(to>=from)) return out;
  for(let v=from; v<=to+1e-9; v=+(v+step).toFixed(6)) out.push(+v.toFixed(6));
  return out;
}

async function runSweep(){
  if(sweepRunning) return;
  sweepRows=[]; $("sweepResult").innerHTML=""; $("sweepStatus").textContent="";
  if(!lastBars){
    $("sweepStatus").textContent="먼저 \"데이터 가져오기 + 백테스트\"를 실행하세요.";
    return;
  }
  const tpList=frange(+$("sw_tpFrom").value,+$("sw_tpTo").value,+$("sw_tpStep").value);
  const slList=frange(+$("sw_slFrom").value,+$("sw_slTo").value,+$("sw_slStep").value);
  const spList=[]; {
    const a=+$("sw_spFrom").value,b=+$("sw_spTo").value,st=Math.max(1,Math.round(+$("sw_spStep").value)||1);
    for(let v=a; v<=b; v+=st) spList.push(Math.max(1,Math.min(10,Math.round(v))));
  }
  // (신규) 60선 최소 기울기 % 스윕 범위. 시작=끝(기본값)이면 현재 설정값 1가지만 쓰므로 기존 스윕 동작/조합수는 그대로 유지됩니다.
  const ma60List=frange(+$("sw_ma60From").value,+$("sw_ma60To").value,+$("sw_ma60Step").value);
  if(!tpList.length||!slList.length||!spList.length||!ma60List.length){
    $("sweepStatus").textContent="TP/SL/분할횟수/60선 기울기 범위를 확인하세요(시작 ≤ 끝, 간격 > 0).";
    return;
  }
  const total=tpList.length*slList.length*spList.length*ma60List.length;
  const MAX_COMBOS=1000;
  if(total>MAX_COMBOS){
    $("sweepStatus").textContent=`조합이 ${total}개로 너무 많습니다. 범위나 간격을 조정해 ${MAX_COMBOS}개 이하로 줄여주세요.`;
    return;
  }

  const metric=$("sw_metric").value;
  const results=[];
  const combos=[];
  for(const tp of tpList) for(const sl of slList) for(const maxSplits of spList) for(const ma60MinSlope of ma60List)
    combos.push({tp,sl,maxSplits,ma60MinSlope});
  sweepRunning=true;
  try{
    for(let ci=0; ci<combos.length; ci++){
      const c=combos[ci];
      const cfg2={...lastCfgBase,...c};
      const res=simulate(lastBars,lastMaTrend,lastMa200,lastSlope60,lastMaPullback,cfg2);
      const s=stats(res,cfg2);
      results.push({...c,trades:s.trades,winRate:s.winRate,net:s.net,ret:s.ret,mdd:s.mdd,pf:s.pf,avg:s.avg});
      if(ci%20===19){ // 화면이 멈추지 않도록 주기적으로 양보 + 진행률 표시
        $("sweepStatus").textContent=`스윕 진행 중... ${ci+1} / ${total}`;
        await sleep(0);
      }
    }
  }finally{ sweepRunning=false; }

  function score(r){
    switch(metric){
      case "mdd": return r.mdd;
      case "pf": return -(isFinite(r.pf)?r.pf:1e9);
      case "avg": return -r.avg;
      default: return -r.ret;
    }
  }
  results.sort((a,b)=>score(a)-score(b));
  sweepRows=results.map(r=>({tp:r.tp,sl:r.sl,maxSplits:r.maxSplits,ma60MinSlope:r.ma60MinSlope,trades:r.trades,winRate:r.winRate,net:r.net,returnPct:r.ret,mdd:r.mdd,pf:isFinite(r.pf)?r.pf:"Infinity",avgPerTrade:r.avg}));

  const showSlopeCol = ma60List.length>1;
  const top=results.slice(0,20);
  let h=`<table><tr><th>TP%</th><th>SL%</th><th>분할</th>${showSlopeCol?"<th>60선 기울기%</th>":""}<th>거래수</th><th>승률</th><th>순손익</th><th>수익률</th><th>MDD</th><th>PF</th><th>거래당 평균손익</th></tr>`;
  top.forEach((r,idx)=>{
    h+=`<tr${idx===0?' class="highlight"':""}><td>${fmt(r.tp,2)}</td><td>${fmt(r.sl,2)}</td><td>${r.maxSplits}</td>${showSlopeCol?`<td>${fmt(r.ma60MinSlope,2)}</td>`:""}<td>${r.trades}</td><td>${fmt(r.winRate,1)}%</td><td>${fmt(r.net)}</td><td>${fmt(r.ret)}%</td><td>${fmt(r.mdd)}%</td><td>${isFinite(r.pf)?fmt(r.pf):"∞"}</td><td>${fmt(r.avg)}</td></tr>`;
  });
  h+="</table>";
  $("sweepResult").innerHTML=h;
  $("sweepStatus").textContent=`총 ${total}개 조합 중 상위 ${top.length}개 표시 (정렬: ${$("sw_metric").selectedOptions[0].textContent}).`+(showSlopeCol?" 60선 기울기 열이 추가됐습니다 — 상위 결과에 자주 등장하는 값이 이번 데이터에서의 최적값입니다.":"");
}

// ---- 차트: 캔들 + MA + 매수/매도 마커 (외부 라이브러리 없이 canvas로 직접 렌더링) ----
function fmtDate(ms){
  const d=new Date(ms+9*3600000); // KST(UTC+9)로 보정 후 UTC getter로 읽는 트릭
  const p=n=>String(n).padStart(2,"0");
  return `${d.getUTCFullYear()}-${p(d.getUTCMonth()+1)}-${p(d.getUTCDate())} ${p(d.getUTCHours())}:${p(d.getUTCMinutes())} KST`;
}

// 차트 마커 라벨용: 한국시간 "YYMMDD_HHMM" (예: 261105_2307)
function fmtShortStamp(ms){
  const d=new Date(ms+9*3600000);
  const p=n=>String(n).padStart(2,"0");
  return `${String(d.getUTCFullYear()).slice(2)}${p(d.getUTCMonth()+1)}${p(d.getUTCDate())}_${p(d.getUTCHours())}${p(d.getUTCMinutes())}`;
}
// 가격 크기에 맞춰 소수 자릿수 자동 조절
function fmtPx(p){
  const a=Math.abs(p);
  const d=a>=1000?2:a>=100?3:a>=1?4:a>=0.01?5:8;
  return Number(p).toFixed(d);
}

function exitColor(type){
  if(type==="SL") return "#38bdf8"; // 손절: 하늘색
  if(type==="DEADCROSS") return "#f59e0b"; // 데드크로스 강제청산: 주황색
  return "#22c55e"; // 익절(TP): 녹색
}
function exitLabel(type){
  if(type==="TP") return "익절";
  if(type==="SL") return "손절";
  if(type==="DEADCROSS") return "데드크로스 청산";
  if(type==="TS") return "추적 손절"; // 기준 파일과 다름 — 1110-01
  return type;
}

// factor<1: 확대(표시 봉 수 감소), factor>1: 축소(표시 봉 수 증가). 휠·핀치·버튼이 모두 이 함수를 공유합니다.
function zoomChart(factor){
  // "확대 +"/"축소 −" 버튼: 화면 전체(최신 봉 기준) 배율 조절. 이전에 휠로 특정 시점을 확대해 둔 상태였다면 리셋합니다.
  if(!lastBars) return;
  const cur=Math.max(30,Math.min(lastBars.length,Math.round(+$("chart_barCount").value)||1500));
  const next=Math.max(30,Math.min(lastBars.length,Math.round(cur*factor)));
  const wasPanned=chartViewStart!=null;
  chartViewStart=null;
  if(next!==cur || wasPanned){ $("chart_barCount").value=next; renderChart(); }
}

// 마우스 휠 전용: 커서가 가리키는 시점(시간대)을 그대로 유지한 채 그 주변만 확대/축소합니다(세부 구간 확인용).
// factor<1=확대(봉 수 감소), factor>1=축소(봉 수 증가).
function zoomChartAtCursor(factor,clientX){
  if(!lastBars || !chartState) return;
  const n=lastBars.length;
  const canvas=$("chartCanvas");
  const rect=canvas.getBoundingClientRect();
  const mx=clientX-rect.left;
  const curBarCount=chartState.bars.length;
  const hoverLocalIdx=Math.max(0,Math.min(curBarCount-1,Math.floor(mx/chartState.barW)));
  const globalHoverIdx=chartState.start+hoverLocalIdx; // 전체 데이터 기준 인덱스
  const frac=curBarCount>1?hoverLocalIdx/(curBarCount-1):0.5; // 현재 화면에서 커서가 위치한 상대 위치(0=왼쪽 끝,1=오른쪽 끝)
  const newBarCount=Math.max(30,Math.min(n,Math.round(curBarCount*factor)));
  let newStart=Math.round(globalHoverIdx-frac*(newBarCount-1));
  newStart=Math.max(0,Math.min(Math.max(0,n-newBarCount),newStart));
  if(newBarCount===curBarCount && newStart===chartState.start) return; // 더 이상 변화 없음(배율 한계 등)
  chartViewStart=newStart;
  $("chart_barCount").value=newBarCount;
  renderChart();
}

function renderChart(){
  if(!lastBars || !lastResults){
    $("chartHint").textContent="먼저 \"데이터 가져오기 + 백테스트\"를 실행하세요.";
    return;
  }
  const res = lastResults;
  const n=lastBars.length;
  const barCount=Math.max(30,Math.min(n,Math.round(+$("chart_barCount").value)||1500));

  // chartViewStart가 설정돼 있으면(휠로 특정 시점을 확대해 둔 상태) 그 위치를 유지하고,
  // 아니면 기존처럼 항상 최신 봉 기준(오른쪽 끝)으로 표시합니다.
  const start = chartViewStart!=null
    ? Math.max(0,Math.min(Math.max(0,n-barCount),chartViewStart))
    : Math.max(0,n-barCount);
  const end=Math.min(n,start+barCount);
  const bars=lastBars.slice(start,end);
  const maTrend=lastMaTrend.slice(start,end);
  const ma200=lastMa200.slice(start,end);
  const maPullback=lastMaPullback.slice(start,end);
  const samePullback = lastCfgBase.pullbackP===lastCfgBase.ma60p;

  const height=420;
  const canvas=$("chartCanvas");
  const dpr=window.devicePixelRatio||1;
  // 캔들 봉 수가 많아지면 canvas 실제 픽셀 폭(bars.length*barW*dpr)이 브라우저의 캔버스 최대 크기(크롬 기준 약
  // 3만2천~6만5천대 px, 디스플레이 배율(dpr)이 곱해지면 더 빨리 한계에 도달)를 넘어서 버려 아예 빈 화면이 됩니다.
  // (1~3만봉 조회 시 10000/20000개 표시가 안 되던 원인이 바로 이것입니다.) 안전하게 16000 실제픽셀로 상한을 두고,
  // 그 안에 들어오도록 봉 1개당 폭(barW)을 자동으로 줄여서 — 봉이 가늘어질 뿐 — 항상 차트가 그려지게 합니다.
  const SAFE_DEVICE_PX=16000;
  let barW=6;
  if(bars.length*barW*dpr>SAFE_DEVICE_PX){
    barW=Math.max(0.4, SAFE_DEVICE_PX/dpr/bars.length);
  }
  const width=Math.max(600,bars.length*barW+100); // +100: 최근 봉 마커 라벨이 오른쪽 끝에서 잘리지 않도록 여백
  canvas.width=Math.round(width*dpr);
  canvas.height=Math.round(height*dpr);
  canvas.style.width=width+"px";
  canvas.style.height=height+"px";
  const ctx=canvas.getContext("2d");
  ctx.setTransform(dpr,0,0,dpr,0,0);
  ctx.fillStyle="#0b1220";
  ctx.fillRect(0,0,width,height);

  // 마우스오버 시 세로 크로스헤어를 그릴 전용 오버레이 캔버스(메인 캔버스와 크기를 맞추고, 매번 비워서 시작).
  // 마우스를 움직일 때마다 전체 차트를 다시 그리지 않고 이 레이어만 지웠다가 선 하나만 그리면 되므로 가볍습니다.
  const overlay=$("chartOverlay");
  overlay.width=canvas.width; overlay.height=canvas.height;
  overlay.style.width=width+"px"; overlay.style.height=height+"px";
  const octx=overlay.getContext("2d");
  octx.setTransform(1,0,0,1,0,0);
  octx.clearRect(0,0,overlay.width,overlay.height);

  let lo=Infinity,hi=-Infinity;
  bars.forEach(b=>{ if(b.l<lo)lo=b.l; if(b.h>hi)hi=b.h; });
  [maTrend,ma200,maPullback].forEach(arr=>arr.forEach(v=>{ if(v!=null){ if(v<lo)lo=v; if(v>hi)hi=v; } }));
  if(!isFinite(lo)||!isFinite(hi)||lo===hi){ lo=(lo||0)-1; hi=(hi||1)+1; }
  const pad=(hi-lo)*0.06;
  lo-=pad; hi+=pad;
  const yOf=p=>height-((p-lo)/(hi-lo))*height;
  const xOf=i=>i*barW+barW/2;

  // 캔들 (국내 관행: 빨강=상승, 파랑=하락)
  bars.forEach((b,i)=>{
    const up=b.c>=b.o;
    ctx.strokeStyle=up?"#e05252":"#4d82e0";
    ctx.fillStyle=ctx.strokeStyle;
    const cx=xOf(i);
    ctx.lineWidth=1;
    ctx.beginPath(); ctx.moveTo(cx,yOf(b.h)); ctx.lineTo(cx,yOf(b.l)); ctx.stroke();
    const yO=yOf(b.o), yC=yOf(b.c);
    const top=Math.min(yO,yC), h=Math.max(1,Math.abs(yC-yO));
    ctx.fillRect(cx-barW*0.35,top,barW*0.7,h);
  });

  function drawLine(arr,color){
    ctx.strokeStyle=color; ctx.lineWidth=1.4; ctx.beginPath();
    let started=false;
    arr.forEach((v,i)=>{
      if(v==null){ started=false; return; }
      const px=xOf(i), py=yOf(v);
      if(!started){ ctx.moveTo(px,py); started=true; } else ctx.lineTo(px,py);
    });
    ctx.stroke();
  }
  drawLine(ma200,"#f2f2f2");
  drawLine(maTrend,"#2dd4bf");
  if(!samePullback) drawLine(maPullback,"#f5c518");

  // 시각-로컬인덱스 매핑 (매수/매도 마커 위치 찾기용)
  const idxByTime=new Map();
  bars.forEach((b,i)=>idxByTime.set(b.t,i));

  function triangleUp(cx,cy,size,color){
    ctx.fillStyle=color;
    ctx.beginPath(); ctx.moveTo(cx,cy); ctx.lineTo(cx-size,cy+size*1.6); ctx.lineTo(cx+size,cy+size*1.6); ctx.closePath(); ctx.fill();
  }
  function triangleDown(cx,cy,size,color){
    ctx.fillStyle=color;
    ctx.beginPath(); ctx.moveTo(cx,cy); ctx.lineTo(cx-size,cy-size*1.6); ctx.lineTo(cx+size,cy-size*1.6); ctx.closePath(); ctx.fill();
  }

  const buyAtIdx=new Map(), sellAtIdx=new Map();
  res.entries.forEach(e=>{
    const idx=idxByTime.get(e.time);
    if(idx==null) return;
    buyAtIdx.set(idx,(buyAtIdx.get(idx)||[]).concat([e]));
    triangleUp(xOf(idx),yOf(bars[idx].l)+14,6.4,e.trigger==="GOLDEN"?"#ec4899":"#facc15");
  });
  res.trades.forEach(tr=>{
    const et=new Date(tr.exitTime).getTime();
    const idx=idxByTime.get(et);
    if(idx==null) return;
    sellAtIdx.set(idx,(sellAtIdx.get(idx)||[]).concat([tr]));
    triangleDown(xOf(idx),yOf(bars[idx].h)-14,6.4,exitColor(tr.exitType));
  });
  // 마커 옆 라벨: 시간(YYMMDD_HHMM, KST) + 체결가격. 같은 봉에 여러 건이면 아래(매수)/위(매도)로 쌓아서 표시
  const showLabels=!$("chart_showLabels") || $("chart_showLabels").checked;
  if(showLabels){
    ctx.font="10px Arial, sans-serif";
    ctx.textBaseline="middle";
    ctx.lineJoin="round";
    const lineH=11;
    const clampY=y=>Math.max(7,Math.min(height-7,y));
    function label(x,y,text,color){
      ctx.lineWidth=3; ctx.strokeStyle="rgba(11,18,32,0.9)"; ctx.strokeText(text,x,y);
      ctx.fillStyle=color; ctx.fillText(text,x,y);
    }
    // 겹침 방지: 이미 그린 라벨 박스와 겹치면 매수는 아래로, 매도는 위로 한 칸씩 밀어서 그립니다
    const placed=[];
    const blockH=lineH*2+2;
    function place(x,y0,dir,w){
      let y=y0;
      for(let guard=0; guard<30; guard++){
        const top=dir>0?y-lineH/2:y-lineH*1.5, bot=top+blockH;
        if(!placed.some(r=>x<r.x2 && x+w>r.x1 && top<r.y2 && bot>r.y1)){ placed.push({x1:x,x2:x+w,y1:top,y2:bot}); return y; }
        y+=dir*blockH;
      }
      return y;
    }
    [...buyAtIdx.keys()].sort((a,b)=>a-b).forEach(idx=>{
      const x=xOf(idx)+8;
      let y=yOf(bars[idx].l)+14+5;
      buyAtIdx.get(idx).forEach(e=>{
        const col=e.trigger==="GOLDEN"?"#f9a8d4":"#fde68a";
        const t1="매수 "+fmtShortStamp(e.time), t2="@"+fmtPx(e.price);
        const w=Math.max(ctx.measureText(t1).width,ctx.measureText(t2).width)+4;
        const yy=place(x,y,1,w);
        label(x,clampY(yy),t1,col);
        label(x,clampY(yy+lineH),t2,col);
        y=yy+blockH;
      });
    });
    [...sellAtIdx.keys()].sort((a,b)=>a-b).forEach(idx=>{
      const x=xOf(idx)+8;
      let y=yOf(bars[idx].h)-14-5;
      sellAtIdx.get(idx).forEach(tr=>{
        const col=exitColor(tr.exitType);
        const t1=exitLabel(tr.exitType)+" "+fmtShortStamp(new Date(tr.exitTime).getTime()), t2="@"+fmtPx(tr.exit);
        const w=Math.max(ctx.measureText(t1).width,ctx.measureText(t2).width)+4;
        const yy=place(x,y,-1,w);
        label(x,clampY(yy-lineH),t1,col);
        label(x,clampY(yy),t2,col);
        y=yy-blockH;
      });
    });
    ctx.textBaseline="alphabetic";
  }

  if(res.mark){
    const idx=bars.length-1;
    ctx.fillStyle="#9ca3af";
    ctx.beginPath(); ctx.arc(xOf(idx),yOf(bars[idx].c),4,0,Math.PI*2); ctx.fill();
  }

  chartState={bars,maTrend,ma200,maPullback,barW,buyAtIdx,sellAtIdx,samePullback,start};

  function showInfoAtClientX(clientX){
    if(!chartState) return;
    const rect=canvas.getBoundingClientRect();
    const mx=clientX-rect.left;
    const idx=Math.max(0,Math.min(chartState.bars.length-1,Math.floor(mx/chartState.barW)));
    const b=chartState.bars[idx];
    let txt=`${fmtDate(b.t)} | O ${fmt(b.o)} H ${fmt(b.h)} L ${fmt(b.l)} C ${fmt(b.c)} | MA200 ${chartState.ma200[idx]!=null?fmt(chartState.ma200[idx]):"-"} / MA(추세) ${chartState.maTrend[idx]!=null?fmt(chartState.maTrend[idx]):"-"}`;
    if(!chartState.samePullback) txt+=` / MA(눌림목) ${chartState.maPullback[idx]!=null?fmt(chartState.maPullback[idx]):"-"}`;
    const buys=chartState.buyAtIdx.get(idx);
    const sells=chartState.sellAtIdx.get(idx);
    if(buys) txt+=` | 매수 ${buys.length}건 @${buys.map(e=>fmt(e.price)+(e.trigger==="GOLDEN"?"(골든크로스)":"")).join(",")}`;
    if(sells) txt+=` | ${sells.map(s=>exitLabel(s.exitType)+"@"+fmt(s.exit)).join(", ")}`;
    $("chartInfo").textContent=txt;

    // 세로 크로스헤어: 지금 가리키고 있는 봉이 어느 것인지 한눈에 보이도록 흰색 세로선을 그립니다.
    // 전체 차트를 다시 그리는 대신, 위에서 준비해 둔 오버레이 캔버스만 지웠다가 선 하나만 그려서 가볍게 처리합니다.
    const overlay=$("chartOverlay");
    const octx=overlay.getContext("2d");
    octx.setTransform(1,0,0,1,0,0);
    octx.clearRect(0,0,overlay.width,overlay.height);
    octx.setTransform(dpr,0,0,dpr,0,0);
    const cx=xOf(idx);
    octx.strokeStyle="rgba(255,255,255,0.75)";
    octx.lineWidth=1;
    octx.beginPath(); octx.moveTo(cx,0); octx.lineTo(cx,height); octx.stroke();
  }
  function clearCrosshair(){
    const overlay=$("chartOverlay");
    const octx=overlay.getContext("2d");
    octx.setTransform(1,0,0,1,0,0);
    octx.clearRect(0,0,overlay.width,overlay.height);
  }
  canvas.onmousemove=function(ev){ showInfoAtClientX(ev.clientX); };
  canvas.onmouseleave=function(){ clearCrosshair(); };

  // PC: 마우스 휠로 "커서가 가리키는 시점"을 기준으로 확대/축소(세부 구간 확인용), 모바일: 핀치(두 손가락 오므리기/펼치기)
  // 또는 "확대/축소" 버튼으로 화면 전체 배율 조절. 렌더링마다 리스너를 새로 추가하면 중복 바인딩되어 한 번의 조작에
  // 배율이 여러 번 겹쳐 적용되므로, 캔버스당 한 번만 바인딩합니다.
  function touchDist(touches){
    const dx=touches[0].clientX-touches[1].clientX, dy=touches[0].clientY-touches[1].clientY;
    return Math.sqrt(dx*dx+dy*dy);
  }
  if(!canvas._wheelBound){
    canvas.addEventListener("wheel",function(ev){
      if(!lastBars) return;
      ev.preventDefault();
      zoomChartAtCursor(ev.deltaY<0?(1/1.2):1.2,ev.clientX); // 위로 굴림=확대(봉 수 감소), 아래로 굴림=축소(봉 수 증가)
    },{passive:false});
    canvas._wheelBound=true;
  }
  if(!canvas._touchBound){
    let pinchStartDist=null, pinchStartBarCount=null;
    canvas.addEventListener("touchstart",function(ev){
      if(ev.touches.length===2){
        pinchStartDist=touchDist(ev.touches);
        pinchStartBarCount=Math.max(30,Math.min(lastBars?lastBars.length:200000,Math.round(+$("chart_barCount").value)||1500));
      }else if(ev.touches.length===1){
        showInfoAtClientX(ev.touches[0].clientX); // 탭: 가로 스크롤(패닝)은 막지 않도록 preventDefault 하지 않음
      }
    },{passive:true});
    canvas.addEventListener("touchmove",function(ev){
      if(ev.touches.length===2 && pinchStartDist && lastBars){
        ev.preventDefault(); // 핀치 중에는 브라우저 기본 페이지 확대 동작을 막음
        const d=touchDist(ev.touches);
        if(d>0){
          const scale=pinchStartDist/d; // 손가락을 벌리면(d 증가) scale<1 → 확대(봉 수 감소)
          const next=Math.max(30,Math.min(lastBars.length,Math.round(pinchStartBarCount*scale)));
          if(String(next)!==$("chart_barCount").value){ chartViewStart=null; $("chart_barCount").value=next; renderChart(); }
        }
      }else if(ev.touches.length===1){
        showInfoAtClientX(ev.touches[0].clientX); // 한 손가락 드래그: 가로 스크롤은 그대로 두고 정보만 갱신
      }
    },{passive:false});
    canvas.addEventListener("touchend",function(ev){
      if(ev.touches.length<2) pinchStartDist=null;
    },{passive:true});
    canvas._touchBound=true;
  }

  const compressedNote = barW<6 ? ` (봉 수가 많아 캔들 폭을 자동으로 줄여 표시 중)` : "";
  $("chartHint").textContent=`최근 ${bars.length.toLocaleString()}개 봉 표시 중 (전체 ${n.toLocaleString()}개 중)${compressedNote}. PC는 마우스 휠, 모바일은 핀치 또는 버튼으로 확대/축소할 수 있습니다.`;
  $("chartLegend").innerHTML=`<span style="color:#e05252">■</span> 상승캔들 &nbsp; <span style="color:#4d82e0">■</span> 하락캔들 &nbsp;
  <span style="color:#f2f2f2">━</span> MA200 &nbsp; <span style="color:#2dd4bf">━</span> MA(추세/골든크로스) &nbsp;
  ${samePullback?"":'<span style="color:#f5c518">━</span> MA(눌림목 기준) &nbsp;'}
  <span style="color:#facc15">▲</span> 매수(눌림목 재돌파) &nbsp;
  <span style="color:#ec4899">▲</span> 매수(골든크로스 즉시진입) &nbsp;
  <span style="color:#22c55e">▼</span> 익절 &nbsp;
  <span style="color:#38bdf8">▼</span> 손절 &nbsp;
  <span style="color:#f59e0b">▼</span> 데드크로스 강제청산 &nbsp;
  <span style="color:#9ca3af">●</span> 미청산(MARK)`;
}

// ---- 모바일용 숫자 입력 −/+ 버튼 ----
// 모바일 브라우저는 type=number의 상하 화살표(스피너)를 보여주지 않으므로, 모든 숫자 입력칸 양옆에 −/+ 버튼을 붙입니다
// (PC에서는 CSS로 숨겨져 기본 스피너를 그대로 씀). input을 DOM상 첫 번째로 두고 CSS order로 −를 왼쪽에 배치해서,
// 라벨 글자를 눌러도 −버튼이 눌리지 않고 입력칸에 포커스가 가도록 했습니다. 길게 누르면 연속으로 증감됩니다.
function stepDecimals(s){ const t=String(s); return t.includes(".")?t.split(".")[1].length:0; }
function applyStep(inp,dir){
  const step=parseFloat(inp.step)>0?parseFloat(inp.step):1;
  const dec=Math.max(stepDecimals(inp.step||"1"),stepDecimals(inp.value||"0"));
  let v=(parseFloat(inp.value)||0)+dir*step;
  if(inp.min!=="" && v<parseFloat(inp.min)) v=parseFloat(inp.min);
  if(inp.max!=="" && v>parseFloat(inp.max)) v=parseFloat(inp.max);
  inp.value=+v.toFixed(Math.min(dec,8));
  inp.dispatchEvent(new Event("input",{bubbles:true}));
  inp.dispatchEvent(new Event("change",{bubbles:true}));
}
function attachSteppers(){
  document.querySelectorAll('input[type="number"]').forEach(inp=>{
    if(inp.parentElement && inp.parentElement.classList.contains("stepper")) return;
    const wrap=document.createElement("div");
    wrap.className="stepper";
    inp.parentNode.insertBefore(wrap,inp);
    wrap.appendChild(inp);
    inp.style.order="1";
    [["−",-1,"0"],["+",1,"2"]].forEach(([txt,dir,ord])=>{
      const b=document.createElement("button");
      b.type="button"; b.className="stepBtn"; b.textContent=txt; b.style.order=ord;
      b.setAttribute("aria-label",dir<0?"감소":"증가");
      let holdT=null, repT=null;
      const stop=()=>{ clearTimeout(holdT); clearInterval(repT); holdT=repT=null; };
      b.addEventListener("pointerdown",ev=>{
        ev.preventDefault(); applyStep(inp,dir);
        holdT=setTimeout(()=>{ repT=setInterval(()=>applyStep(inp,dir),90); },450);
      });
      ["pointerup","pointerleave","pointercancel"].forEach(t=>b.addEventListener(t,stop));
      b.addEventListener("click",ev=>ev.preventDefault()); // pointerdown에서 이미 처리
      b.addEventListener("contextmenu",ev=>ev.preventDefault());
      wrap.appendChild(b);
    });
  });
}
attachSteppers();
