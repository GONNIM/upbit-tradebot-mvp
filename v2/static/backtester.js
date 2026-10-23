let tradeRows=[], weeklyRows=[], monthlyRows=[], sweepRows=[];
let lastBars=null, lastMaTrend=null, lastMa200=null, lastSlope200=null, lastMaPullback=null, lastCfgBase=null, lastResults=null;
let chartState=null;
let chartViewStart=null; // 휠 줌으로 특정 시점(커서 위치)에 고정해서 본 경우의 시작 인덱스. null이면 항상 최신 봉 기준(전체 화면).
const $=id=>document.getElementById(id);
const sleep=ms=>new Promise(r=>setTimeout(r,ms));

function fmt(n,d=3){
  return Number(n).toLocaleString(undefined,{maximumFractionDigits:d,minimumFractionDigits:d});
}

async function fetchKlines(symbol, interval, days){
  const base="https://data-api.binance.vision/api/v3/klines";
  const msPer={"1m":60000,"3m":180000,"5m":300000,"1h":3600000}[interval]||300000;
  const end=Date.now(), start=end-days*86400000;
  let cursor=start,out=[],req=0;

  while(cursor<end){
    const u=base+"?symbol="+encodeURIComponent(symbol)+"&interval="+interval+
      "&startTime="+cursor+"&endTime="+end+"&limit=1000";
    let data;
    try{
      const r=await fetch(u);
      if(!r.ok) throw new Error("HTTP "+r.status);
      data=await r.json();
    }catch(e){
      const u2="https://api.binance.com/api/v3/klines?symbol="+encodeURIComponent(symbol)+
        "&interval="+interval+"&startTime="+cursor+"&endTime="+end+"&limit=1000";
      const r2=await fetch(u2);
      if(!r2.ok) throw new Error("Binance API 오류: "+r2.status);
      data=await r2.json();
    }
    if(!Array.isArray(data)||!data.length)break;
    for(const x of data)out.push({t:+x[0],o:+x[1],h:+x[2],l:+x[3],c:+x[4]});
    const next=+data[data.length-1][0]+msPer;
    if(next<=cursor)break;
    cursor=next;req++;
    $("status").textContent=`데이터 수집 중... ${req}회 / ${out.length.toLocaleString()}개 봉`;
    await sleep(120);
  }
  return [...new Map(out.map(x=>[x.t,x])).values()].sort((a,b)=>a.t-b.t);
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

function isFilterActive(i,maTrend,ma200,slope200,cfg){
  if(maTrend[i]==null||ma200[i]==null||slope200[i]==null) return false;
  if(!(maTrend[i]>ma200[i])) return false;             // 골든크로스 상태(MA60 vs MA200, 고정)
  if(slope200[i]<cfg.minSlope) return false;           // 최소 기울기
  if(cfg.slopeDrop>0){                                  // 기울기 둔화(각도 붕괴) 체크
    const j=i-cfg.slopeLB;
    if(j>=0 && slope200[j]!=null){
      if((slope200[j]-slope200[i])>cfg.slopeDrop) return false;
    }
  }
  return true;
}

/*
  분할마다 동일 비중(1→1)으로 매수합니다. 자본은 분할 횟수(sumW=maxSplits)로 균등 배분되므로
  모든 분할이 체결되면 총 투입액은 기준 자본(sizingBase)과 같아집니다(그리드 자본 배분 방식과 동일).
*/
function simulate(bars,maTrend,ma200,slope200,maPullback,cfg){
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
  let pullbackArmed=false;
  let prevGolden=false; // 직전 봉이 골든크로스 상태였는지(이번 봉에서 "막 골든크로스로 전환"됐는지 판정용)

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
    pullbackArmed=false;
  }

  for(let i=0;i<bars.length;i++){
    const b=bars[i];
    const active=isFilterActive(i,maTrend,ma200,slope200,cfg);
    const wasGolden=prevGolden;
    const golden=maTrend[i]!=null&&ma200[i]!=null&&maTrend[i]>ma200[i];
    prevGolden=golden; // continue로 빠지는 경로가 있어도 누락 없이 항상 갱신
    const justCrossedGolden=golden && !wasGolden;

    // 데드크로스 발생 시 강제청산
    if(qty>0 && cfg.deadcross==="yes" && maTrend[i]!=null && ma200[i]!=null && !(maTrend[i]>ma200[i])){
      closePosition(i,b.c,"DEADCROSS");
      continue;
    }

    // TP / SL 체크 (진입 당일 봉은 평가하지 않음 — 그리드 백테스터와 동일 규칙)
    if(qty>0 && firstEntryTime!=null && b.t>firstEntryTime){
      const avg=cost/qty;
      const tpPrice=avg*(1+cfg.tp/100);
      const slPrice=avg*(1-cfg.sl/100);
      if(b.h>=tpPrice){ closePosition(i,tpPrice,"TP"); continue; }
      if(b.l<=slPrice){ closePosition(i,slPrice,"SL"); continue; }
    }

    const sizingBase=cfg.compounding==="yes"?equity:cfg.capital;

    // (신규) 골든크로스 시 1차 매수: 눌림목을 기다리지 않고, 골든크로스로 막 전환된(또는 조회 시작 시점에
    // 이미 골든크로스인) 바로 다음 캔들 시가에 1회차 분할매수를 즉시 체결합니다. 포지션이 없을 때만(entryCount===0) 적용되며,
    // 체결 후에는 같은 봉에서 눌림목 조건을 다시 평가하지 않고 다음 봉으로 넘어갑니다(2회차부터는 기존 눌림목 재돌파 로직 사용).
    if(cfg.buyOnGoldenCross && justCrossedGolden && entryCount===0 && active && entryCount<effMaxSplits &&
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
      if(firstEntryTime===null) firstEntryTime=nb.t;
      pullbackArmed=false;
      continue;
    }

    // 눌림목 → 재돌파 → 분할매수 (기준선은 maPullback: 기본 MA60이지만 별도 설정 가능)
    // 복리 모드: 새 거래(entryCount===0)가 시작되는 시점의 equity를 배분 기준 자본으로 사용.
    // 포지션 보유 중에는 equity가 realize 전까지 변하지 않으므로, 같은 거래의 2차 이후 분할도 동일 기준으로 계산됨.
    // goldenOnlyMode(분할매수 최대 횟수=0 + 골든크로스 시 1차 매수=예)에서는 눌림목 추가매수를 완전히 차단합니다.
    // 눌림목 매수는 전체 분할 한도(effMaxSplits)와 별개로, 눌림목 전용 횟수 한도(maxPullbackBuys)도 함께 적용됩니다.
    const pullbackCapped = pullbackEntryCount>=cfg.maxPullbackBuys;
    if(!goldenOnlyMode && !pullbackCapped && active && entryCount<effMaxSplits && (cfg.compounding!=="yes" || sizingBase>0)){
      if(maPullback[i]!=null && b.l<maPullback[i]) pullbackArmed=true;
      if(pullbackArmed && maPullback[i]!=null && b.c>maPullback[i] && i+1<bars.length){
        const nb=bars[i+1];
        const notional=(sizingBase/sumW)*weights[entryCount];
        const px=nb.o;
        const q=notional/px;
        const fee=notional*cfg.fee/100;
        qty+=q; cost+=notional; entryFees+=fee;
        if(entryCount===0) firstEntryTrigger="PULLBACK";
        entryCount++; pullbackEntryCount++;
        entries.push({time:nb.t,splitIndex:entryCount,price:px,qty:q,notional:notional,trigger:"PULLBACK"});
        if(firstEntryTime===null) firstEntryTime=nb.t;
        pullbackArmed=false;
      }
    }else if(!active || goldenOnlyMode || pullbackCapped){
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

  return {trades,equity,maxDD,depth,mark,entries};
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
    maxSplit:t.reduce((m,x)=>Math.max(m,x.entries),0),
    avgSplit:t.length?t.reduce((s,x)=>s+x.entries,0)/t.length:0,
    goldenStart:t.filter(x=>x.firstEntryTrigger==="GOLDEN").length,
    pullbackStart:t.filter(x=>x.firstEntryTrigger==="PULLBACK").length,
    pullbackFills:res.entries.filter(e=>e.trigger==="PULLBACK").length,
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
    ["최대 분할 도달",s.maxSplit],
    ["평균 분할 횟수",fmt(s.avgSplit)],
    ["골든크로스 즉시진입으로 시작한 거래",s.goldenStart],
    ["눌림목 재돌파로 시작한 거래",s.pullbackStart],
    ["눌림목 매수 체결 횟수(전체, 캡="+cfg.maxPullbackBuys+")",s.pullbackFills]
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
    slopeLB:+$("slopeLB").value, minSlope:+$("minSlope").value, slopeDrop:+$("slopeDrop").value,
    buyOnGoldenCross:$("buyOnGoldenCross").value==="yes",
    maxSplits:Math.max(0,Math.min(10,+$("maxSplits").value)),
    maxPullbackBuys:Math.max(1,Math.min(5,+$("maxPullbackBuys").value||5)),
    tp:+$("tp").value, sl:+$("sl").value,
    capital:+$("capital").value, fee:+$("fee").value,
    deadcross:$("deadcross").value,
    compounding:$("compounding").value
  };
  try{
    const bars=await fetchKlines($("symbol").value.toUpperCase(),$("src").value,+$("days").value);
    const needBars=Math.max(cfg.ma200p,cfg.pullbackP)+10;
    if(bars.length<needBars)throw new Error(`가져온 데이터가 너무 적습니다. 최소 ${needBars}개 봉이 필요합니다(조회 기간을 늘려주세요).`);

    const ma60=computeMA(bars,cfg.ma60p,cfg.maType);       // 골든크로스 판정용(MA60 vs MA200)
    const ma200=computeMA(bars,cfg.ma200p,cfg.maType);
    const maPullback=computeMA(bars,cfg.pullbackP,cfg.maType); // 눌림목 재진입 기준선(20/60 등 선택)
    const slope200=computeSlope(ma200,cfg.slopeLB);

    const res=simulate(bars,ma60,ma200,slope200,maPullback,cfg);
    // 거래로그 CSV는 내부 계산(ISO/UTC 기준 시각)과 별개로, 차트·주간/월간표와 동일한 한국시간(KST)으로 보이도록 변환해서 내보냅니다.
    tradeRows=res.trades.map(t=>({
      ...t,
      entryTime:kstStamp(new Date(t.entryTime).getTime())+" KST",
      exitTime:kstStamp(new Date(t.exitTime).getTime())+" KST"
    }));
    render(res,cfg,bars);

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
    lastBars=bars; lastMaTrend=ma60; lastMa200=ma200; lastSlope200=slope200; lastMaPullback=maPullback;
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
function downloadTrades(){dl("ma60_200_pullback_trades.csv",csv(tradeRows))}
function downloadWeekly(){dl("ma60_200_pullback_weekly.csv",csv(weeklyRows))}
function downloadMonthly(){dl("ma60_200_pullback_monthly.csv",csv(monthlyRows))}
function downloadSweep(){dl("ma60_200_pullback_sweep.csv",csv(sweepRows))}

function frange(from,to,step){
  const out=[];
  if(!(step>0)||!(to>=from)) return out;
  for(let v=from; v<=to+1e-9; v=+(v+step).toFixed(6)) out.push(+v.toFixed(6));
  return out;
}

function runSweep(){
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
  if(!tpList.length||!slList.length||!spList.length){
    $("sweepStatus").textContent="TP/SL/분할횟수 범위를 확인하세요(시작 ≤ 끝, 간격 > 0).";
    return;
  }
  const total=tpList.length*slList.length*spList.length;
  if(total>400){
    $("sweepStatus").textContent=`조합이 ${total}개로 너무 많습니다. 범위나 간격을 조정해 400개 이하로 줄여주세요.`;
    return;
  }

  const metric=$("sw_metric").value;
  const results=[];
  for(const tp of tpList){
    for(const sl of slList){
      for(const maxSplits of spList){
        const cfg2={...lastCfgBase,tp,sl,maxSplits};
        const res=simulate(lastBars,lastMaTrend,lastMa200,lastSlope200,lastMaPullback,cfg2);
        const s=stats(res,cfg2);
        results.push({tp,sl,maxSplits,trades:s.trades,winRate:s.winRate,net:s.net,ret:s.ret,mdd:s.mdd,pf:s.pf,avg:s.avg});
      }
    }
  }

  function score(r){
    switch(metric){
      case "mdd": return r.mdd;
      case "pf": return -(isFinite(r.pf)?r.pf:1e9);
      case "avg": return -r.avg;
      default: return -r.ret;
    }
  }
  results.sort((a,b)=>score(a)-score(b));
  sweepRows=results.map(r=>({tp:r.tp,sl:r.sl,maxSplits:r.maxSplits,trades:r.trades,winRate:r.winRate,net:r.net,returnPct:r.ret,mdd:r.mdd,pf:isFinite(r.pf)?r.pf:"Infinity",avgPerTrade:r.avg}));

  const top=results.slice(0,20);
  let h=`<table><tr><th>TP%</th><th>SL%</th><th>분할</th><th>거래수</th><th>승률</th><th>순손익</th><th>수익률</th><th>MDD</th><th>PF</th><th>거래당 평균손익</th></tr>`;
  top.forEach((r,idx)=>{
    h+=`<tr${idx===0?' class="highlight"':""}><td>${fmt(r.tp,2)}</td><td>${fmt(r.sl,2)}</td><td>${r.maxSplits}</td><td>${r.trades}</td><td>${fmt(r.winRate,1)}%</td><td>${fmt(r.net)}</td><td>${fmt(r.ret)}%</td><td>${fmt(r.mdd)}%</td><td>${isFinite(r.pf)?fmt(r.pf):"∞"}</td><td>${fmt(r.avg)}</td></tr>`;
  });
  h+="</table>";
  $("sweepResult").innerHTML=h;
  $("sweepStatus").textContent=`총 ${total}개 조합 중 상위 ${top.length}개 표시 (정렬: ${$("sw_metric").selectedOptions[0].textContent}).`;
}

// ---- 차트: 캔들 + MA + 매수/매도 마커 (외부 라이브러리 없이 canvas로 직접 렌더링) ----
function fmtDate(ms){
  const d=new Date(ms+9*3600000); // KST(UTC+9)로 보정 후 UTC getter로 읽는 트릭
  const p=n=>String(n).padStart(2,"0");
  return `${d.getUTCFullYear()}-${p(d.getUTCMonth()+1)}-${p(d.getUTCDate())} ${p(d.getUTCHours())}:${p(d.getUTCMinutes())} KST`;
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
  const width=Math.max(600,bars.length*barW);
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
