from pathlib import Path

root=Path('delivery-momentum')

# Add independent trajectory math engine.
traj=root/'app/src/main/java/com/suhas/nsedeliverymomentum/TrajectoryMath.java'
traj.write_text(r'''package com.suhas.nsedeliverymomentum;

import java.util.*;

/**
 * Independent session-uptrend engine. It is intentionally separate from MomentumMath so the
 * existing continuation engine can remain unchanged. The objective is to detect a persistent
 * upward drift across the trading session, not a one-candle spike or a gap-only move.
 */
public final class TrajectoryMath {
    private TrajectoryMath(){}
    public static final class Metrics {
        public double sessionGain,gapPct,postOpenGain,hourlyPace,recentPace,r2,pathEfficiency,
                higherLows,higherHighs,positive15,positive30,vwap,vwapHold,vwapSlope,
                closeLocation,maxDrawdown,maxSpikeShare,followThrough,marketAlpha,sectorAlpha,
                flow,spread,turnoverCr,score,confidence;
        public boolean qualified; public String reason="";
    }
    public static Metrics calculate(List<GrowwClient.Candle> cs,double ltp,double dayOpen,double dayHigh,double dayLow,
                                    double dayChangePct,double sectorGain,double marketGain,double flow,double spread,
                                    double turnoverCr,double historicalHitRate,int elapsedMinutes){
        Metrics m=new Metrics();
        if(cs==null||cs.size()<6||dayOpen<=0||ltp<=0){m.reason="need at least six 3m candles";return m;}
        int n=cs.size();
        m.sessionGain=(ltp/dayOpen-1)*100;
        double prevClose=(dayChangePct>-95&&dayChangePct<95)?ltp/(1.0+dayChangePct/100.0):0;
        m.gapPct=prevClose>0?(dayOpen/prevClose-1)*100:0;
        double afterOpen=cs.get(Math.min(4,n-1)).close;
        m.postOpenGain=afterOpen>0?(ltp/afterOpen-1)*100:0;
        m.marketAlpha=m.sessionGain-marketGain;m.sectorAlpha=m.sessionGain-sectorGain;m.flow=flow;m.spread=spread;m.turnoverCr=turnoverCr;

        double[] full=regression(cs,3.0);m.hourlyPace=full[0];m.r2=full[1];
        List<GrowwClient.Candle> recent=cs.subList(Math.max(0,n-12),n);m.recentPace=regression(recent,3.0)[0];

        double path=0;for(int i=1;i<n;i++)path+=Math.abs(cs.get(i).close-cs.get(i-1).close);
        m.pathEfficiency=path>0?Math.abs(cs.get(n-1).close-cs.get(0).close)/path:0;

        double pv=0,vol=0,firstVwap=0,lastVwap=0;int above=0,aboveDen=0;
        for(int i=0;i<n;i++){
            GrowwClient.Candle c=cs.get(i);double tp=(c.high+c.low+c.close)/3.0;pv+=tp*c.volume;vol+=c.volume;
            double rv=vol>0?pv/vol:0;if(i==Math.min(3,n-1))firstVwap=rv;lastVwap=rv;
            if(i>=3){aboveDen++;if(c.close>=rv)above++;}
        }
        m.vwap=lastVwap;m.vwapHold=aboveDen>0?(double)above/aboveDen:0;
        double hours=Math.max(0.05,elapsedMinutes/60.0);m.vwapSlope=firstVwap>0?(lastVwap/firstVwap-1)*100/hours:0;

        int hl=0,hh=0,structDen=0;for(int i=1;i<n;i++){GrowwClient.Candle c=cs.get(i),p=cs.get(i-1);structDen++;if(c.low>=p.low)hl++;if(c.high>=p.high)hh++;}
        m.higherLows=structDen>0?(double)hl/structDen:0;m.higherHighs=structDen>0?(double)hh/structDen:0;

        int p15=0,d15=0,p30=0,d30=0;for(int i=5;i<n;i++){d15++;if(cs.get(i).close>cs.get(i-5).close)p15++;if(i>=10){d30++;if(cs.get(i).close>cs.get(i-10).close)p30++;}}
        m.positive15=d15>0?(double)p15/d15:0;m.positive30=d30>0?(double)p30/d30:m.positive15;

        double peak=cs.get(0).close,maxDd=0,posSum=0,maxPos=0;int spikeIdx=0;
        for(int i=1;i<n;i++){
            double c=cs.get(i).close;peak=Math.max(peak,c);if(peak>0)maxDd=Math.max(maxDd,(peak-c)/peak*100);
            double r=(c/cs.get(i-1).close-1)*100;if(r>0){posSum+=r;if(r>maxPos){maxPos=r;spikeIdx=i;}}
        }
        m.maxDrawdown=maxDd;m.maxSpikeShare=posSum>0?maxPos/posSum:1;
        double spikeClose=cs.get(Math.min(spikeIdx,n-1)).close;m.followThrough=spikeClose>0?(ltp/spikeClose-1)*100:0;
        double range=dayHigh-dayLow;m.closeLocation=range>0?clamp((ltp-dayLow)/range,0,1):0.5;

        double s=0;
        s+=15*scale(m.r2,0.45,0.90);
        s+=12*scale(m.hourlyPace,0.25,1.40);
        s+=10*scale(m.recentPace,0.20,1.50);
        s+=12*scale(m.positive15,0.55,0.90);
        s+=8*scale(m.positive30,0.55,0.90);
        s+=8*scale(m.higherLows,0.45,0.80);
        s+=6*scale(m.higherHighs,0.45,0.80);
        s+=8*scale(m.vwapHold,0.60,0.95);
        s+=7*scale(m.pathEfficiency,0.25,0.65);
        s+=5*scale(m.closeLocation,0.55,0.92);
        s+=4*scale(m.turnoverCr,8,180);
        s+=3*scale(Math.max(m.marketAlpha,m.sectorAlpha),-0.1,1.2);
        s+=2*scale(m.flow,-0.10,0.40);
        if(m.maxSpikeShare>0.50&&m.followThrough<0.35)s-=12;
        if(m.maxDrawdown>1.40)s-=12;
        if(Math.abs(m.gapPct)>1.80&&m.postOpenGain<0.70)s-=12;
        if(m.recentPace<0.10)s-=12;
        if(m.spread>0.20)s-=15;
        if(m.sessionGain>9.0)s-=8;
        if(m.closeLocation<0.50)s-=8;
        m.score=clamp(s,0,100);
        double prior=historicalHitRate>0?historicalHitRate:0.50;m.confidence=clamp(0.82*m.score+18*prior,0,99);

        double minTurn=Math.max(5,55.0*Math.max(1,elapsedMinutes)/375.0);
        List<String> fail=new ArrayList<>();
        if(m.sessionGain<0.65)fail.add("day rise <0.65%");
        if(m.hourlyPace<0.35)fail.add("session slope <0.35%/h");
        if(m.recentPace<0.20)fail.add("recent slope weakening");
        if(m.r2<0.52)fail.add("trajectory not smooth enough");
        if(m.positive15<0.62)fail.add("too few positive 15m windows");
        if(m.positive30<0.60)fail.add("30m persistence weak");
        if(m.higherLows<0.48)fail.add("higher-low structure weak");
        if(m.vwapHold<0.68||ltp<m.vwap)fail.add("VWAP not persistently held");
        if(m.pathEfficiency<0.30)fail.add("path too choppy");
        if(m.closeLocation<0.62)fail.add("too far from session high");
        if(m.maxDrawdown>1.50)fail.add("intraday drawdown too deep");
        if(m.maxSpikeShare>0.60&&m.followThrough<0.50)fail.add("move dominated by one spike");
        if(Math.abs(m.gapPct)>2.0&&m.postOpenGain<0.80)fail.add("gap-only move");
        if(m.spread>0.20)fail.add("spread too wide");
        if(m.turnoverCr<minTurn)fail.add("turnover below trajectory floor");
        if(m.score<72)fail.add("trajectory score <72");
        m.qualified=fail.isEmpty();
        m.reason=m.qualified?"PERSISTENT SESSION UPTREND":String.join(" • ",fail);
        return m;
    }
    private static double[] regression(List<GrowwClient.Candle> c,double stepMin){int n=c.size();double sx=0,sy=0,sxx=0,sxy=0;for(int i=0;i<n;i++){double x=i*stepMin,y=Math.log(Math.max(0.01,c.get(i).close));sx+=x;sy+=y;sxx+=x*x;sxy+=x*y;}double den=n*sxx-sx*sx;if(den==0)return new double[]{0,0};double b=(n*sxy-sx*sy)/den,a=(sy-b*sx)/n,ss=0,se=0,mean=sy/n;for(int i=0;i<n;i++){double y=Math.log(Math.max(0.01,c.get(i).close)),pred=a+b*i*stepMin;ss+=(y-mean)*(y-mean);se+=(y-pred)*(y-pred);}double r2=ss>0?1-se/ss:0;return new double[]{(Math.exp(b*60)-1)*100,clamp(r2,0,1)};}
    static double scale(double x,double lo,double hi){return clamp((x-lo)/(hi-lo),0,1);}static double clamp(double x,double a,double b){return Math.max(a,Math.min(b,x));}
}
''')

# Extend quote only with day-change percentage; this is additive and leaves the existing engine untouched.
g=root/'app/src/main/java/com/suhas/nsedeliverymomentum/GrowwClient.java'
s=g.read_text()
s=s.replace('double ltp,volume,marketCap,bidPrice,offerPrice,buyQty,sellQty;', 'double ltp,volume,marketCap,bidPrice,offerPrice,buyQty,sellQty,dayChangePct;')
s=s.replace('q.ltp=p.optDouble("last_price",0); q.volume=', 'q.ltp=p.optDouble("last_price",0); q.dayChangePct=p.optDouble("day_change_perc",0); q.volume=')
g.write_text(s)

svc=root/'app/src/main/java/com/suhas/nsedeliverymomentum/DeliveryMomentumService.java'
s=svc.read_text()
s=s.replace('private final Map<String,Double> baselineVol=new ConcurrentHashMap<>(),lastFlow=new ConcurrentHashMap<>();private volatile String lastStatus="Starting";private volatile List<Candidate> lastCandidates=new ArrayList<>();private long lastDeep=0;',
'''private final Map<String,Double> baselineVol=new ConcurrentHashMap<>(),lastFlow=new ConcurrentHashMap<>(),trajectoryFlow=new ConcurrentHashMap<>();private volatile String lastStatus="Starting";private volatile List<Candidate> lastCandidates=new ArrayList<>();private volatile List<TrajectoryCandidate> lastTrajectoryCandidates=new ArrayList<>();private long lastDeep=0;''')
s=s.replace('static final class Candidate {String symbol,sector,state,reason;double price,sessionGain,score,confidence,pace,rvol,vwapHold,path,expected,turnover,flow;MomentumMath.Metrics m;}',
'''static final class Candidate {String symbol,sector,state,reason;double price,sessionGain,score,confidence,pace,rvol,vwapHold,path,expected,turnover,flow;MomentumMath.Metrics m;}
    static final class TrajectoryCandidate {String symbol,sector,state,reason;double price,sessionGain,score,confidence,pace,recent,r2,pos15,pos30,vwapHold,higherLows,path,closeLocation,maxDrawdown,gap,postOpen,turnover,flow;TrajectoryMath.Metrics m;}''')
anchor='movers=new ArrayList<>(shortlist.values());\n        monitorActive(snap);'
replace='''movers=new ArrayList<>(shortlist.values());
        List<Map.Entry<String,GrowwClient.Ohlc>> trajectoryPool=buildTrajectoryPool(snap);
        monitorActive(snap);'''
if anchor not in s: raise SystemExit('trajectory pool insertion anchor missing')
s=s.replace(anchor,replace)
old='''lastDeep=System.currentTimeMillis();List<Candidate> out=new ArrayList<>();int max=Math.min(90,movers.size());for(int i=0;i<max;i++){String s=movers.get(i).getKey();GrowwClient.Ohlc o=movers.get(i).getValue();Candidate c=evaluate(s,o,now,marketGain,sectorVals);if(c!=null)out.add(c);sleep(80);}out.sort((a,b)->Double.compare(b.score,a.score));lastCandidates=out.subList(0,Math.min(10,out.size()));int q=0;for(Candidate c:out)if("BUY".equals(c.state))q++;lastStatus=String.format(Locale.US,"ALL-NSE COMPLETE • %d/%d valid • breadth %.0f%% • broad movers %d • deep %d/%d • BUY %d • %s",valid,syms.size(),breadth*100,broadMoverCount,out.size(),max,q,now.toLocalTime().withNano(0));recordRecommendations(out);maybeAutoBuy(out);broadcast();}'''
new='''lastDeep=System.currentTimeMillis();List<Candidate> out=new ArrayList<>();int max=Math.min(90,movers.size());for(int i=0;i<max;i++){String s=movers.get(i).getKey();GrowwClient.Ohlc o=movers.get(i).getValue();Candidate c=evaluate(s,o,now,marketGain,sectorVals);if(c!=null)out.add(c);sleep(80);}out.sort((a,b)->Double.compare(b.score,a.score));lastCandidates=out.subList(0,Math.min(5,out.size()));int q=0;for(Candidate c:out)if("BUY".equals(c.state))q++;
        List<TrajectoryCandidate> trajOut=new ArrayList<>();int trajMax=Math.min(40,trajectoryPool.size());for(int i=0;i<trajMax;i++){String ts=trajectoryPool.get(i).getKey();GrowwClient.Ohlc to=trajectoryPool.get(i).getValue();TrajectoryCandidate tc=evaluateTrajectory(ts,to,now,marketGain,sectorVals);if(tc!=null)trajOut.add(tc);sleep(70);}trajOut.sort((a,b)->Double.compare(b.score,a.score));lastTrajectoryCandidates=trajOut.subList(0,Math.min(5,trajOut.size()));int tq=0;for(TrajectoryCandidate c:trajOut)if("UPTREND".equals(c.state))tq++;
        lastStatus=String.format(Locale.US,"ALL-NSE COMPLETE • %d/%d valid • breadth %.0f%% • movers %d • deep %d/%d • BUY %d • trajectory %d/%d • UPTREND %d • %s",valid,syms.size(),breadth*100,broadMoverCount,out.size(),max,q,trajOut.size(),trajMax,tq,now.toLocalTime().withNano(0));recordRecommendations(out);recordTrajectoryRecommendations(trajOut);maybeAutoBuy(out);maybeAutoBuyTrajectory(trajOut);broadcast();}'''
if old not in s: raise SystemExit('deep block anchor missing')
s=s.replace(old,new)
anchor='    private double computeBaseline(String s,ZonedDateTime now)'
methods=r'''    private List<Map.Entry<String,GrowwClient.Ohlc>> buildTrajectoryPool(Map<String,GrowwClient.Ohlc> snap){
        List<Map.Entry<String,GrowwClient.Ohlc>> all=new ArrayList<>();
        for(Map.Entry<String,GrowwClient.Ohlc> e:snap.entrySet()){
            GrowwClient.Ohlc o=e.getValue();if(o.open<=0||o.last<20||o.high<=o.low)continue;
            double gain=(o.last/o.open-1)*100,loc=(o.last-o.low)/(o.high-o.low),pull=o.high>0?(o.high-o.last)/o.high*100:99;
            if(gain<0.45||gain>9.5||loc<0.55||pull>1.8)continue;all.add(e);
        }
        all.sort((a,b)->Double.compare(trajectoryPre(b.getValue()),trajectoryPre(a.getValue())));
        LinkedHashMap<String,Map.Entry<String,GrowwClient.Ohlc>> pick=new LinkedHashMap<>();
        for(int i=0;i<Math.min(25,all.size());i++)pick.put(all.get(i).getKey(),all.get(i));
        int mapped=0;for(Map.Entry<String,GrowwClient.Ohlc> e:all){if(mapped>=15||pick.size()>=40)break;if(!"UNKNOWN".equals(universe.sector.getOrDefault(e.getKey(),"UNKNOWN"))&&!pick.containsKey(e.getKey())){pick.put(e.getKey(),e);mapped++;}}
        return new ArrayList<>(pick.values());
    }
    private static double trajectoryPre(GrowwClient.Ohlc o){double gain=(o.last/o.open-1)*100,loc=(o.last-o.low)/Math.max(0.01,o.high-o.low),pull=(o.high-o.last)/Math.max(0.01,o.high)*100;return 52*loc+8*Math.min(4.5,gain)-9*pull;}
    private TrajectoryCandidate evaluateTrajectory(String s,GrowwClient.Ohlc o,ZonedDateTime now,double marketGain,Map<String,List<Double>> sectorVals){
        GrowwClient.ApiResult<GrowwClient.Quote> qr=api.quote(s);if(!qr.ok)return null;GrowwClient.Quote q=qr.value;if(q.ltp<=0)return null;
        int elapsed=(int)Duration.between(now.withHour(9).withMinute(15),now).toMinutes();boolean mapped=!"UNKNOWN".equals(universe.sector.getOrDefault(s,"UNKNOWN"));double probeTurn=Math.max(4,45.0*Math.max(1,elapsed)/375.0);if(q.turnoverCr()<probeTurn)return null;if(q.marketCap>0&&q.marketCap<20_000_000_000L&&!mapped)return null;if(q.spreadPct()<90&&q.spreadPct()>0.35)return null;
        ZonedDateTime open=now.withHour(9).withMinute(15).withSecond(0).withNano(0);GrowwClient.ApiResult<List<GrowwClient.Candle>> cr=api.candles(s,open,now,"3minute");if(!cr.ok||cr.value.size()<6)return null;
        String sector=universe.sector.getOrDefault(s,"UNKNOWN");double sectorGain=median(sectorVals.getOrDefault(sector,Collections.emptyList()));double raw=q.imbalance();String fk=GrowwClient.sessionDay()+"_"+s;double prev=trajectoryFlow.getOrDefault(fk,raw),flow=0.65*raw+0.35*prev;trajectoryFlow.put(fk,flow);
        TrajectoryMath.Metrics m=TrajectoryMath.calculate(cr.value,q.ltp,o.open,o.high,o.low,q.dayChangePct,sectorGain,marketGain,flow,q.spreadPct(),q.turnoverCr(),learning.hitRateForScore(80),elapsed);m.confidence=Math.max(0,Math.min(99,0.82*m.score+18*learning.hitRateForScore(m.score)));
        TrajectoryCandidate c=new TrajectoryCandidate();c.symbol=s;c.sector=sector;c.price=q.ltp;c.sessionGain=m.sessionGain;c.score=m.score;c.confidence=m.confidence;c.pace=m.hourlyPace;c.recent=m.recentPace;c.r2=m.r2;c.pos15=m.positive15;c.pos30=m.positive30;c.vwapHold=m.vwapHold;c.higherLows=m.higherLows;c.path=m.pathEfficiency;c.closeLocation=m.closeLocation;c.maxDrawdown=m.maxDrawdown;c.gap=m.gapPct;c.postOpen=m.postOpenGain;c.turnover=m.turnoverCr;c.flow=flow;c.m=m;c.state=m.qualified?"UPTREND":(m.score>=65&&m.recentPace>0?"BUILDING":"WATCH");c.reason=m.reason;return c;
    }
'''
if anchor not in s: raise SystemExit('method insertion anchor missing')
s=s.replace(anchor,methods+anchor)
anchor='    private void broadcast()'
methods=r'''    private void recordTrajectoryRecommendations(List<TrajectoryCandidate> out){for(TrajectoryCandidate c:out){if(!"UPTREND".equals(c.state))continue;String k="rec_"+GrowwClient.sessionDay()+"_"+c.symbol;if(store.getBool(k,false))continue;store.putBool(k,true);learning.add(new LearningStore.Call(c.symbol,c.price,c.score));learning.noteCall();notifyCall("UPWARD TRAJECTORY CALL: "+c.symbol,"₹"+fmt(c.price)+" • trajectory "+fmt(c.score)+" • confidence "+fmt(c.confidence)+" • pace "+fmt(c.pace)+"%/h");}}
    private void maybeAutoBuyTrajectory(List<TrajectoryCandidate> out){boolean live=store.getBool("live",false);if(!live)return;if(!store.getBool("authenticated",false)||!store.getBool("ip_match",false)){store.putBool("live",false);return;}int max=store.getInt("max_buys",10),done=store.getInt("live_buys_today",0);String d=store.get("live_buys_day","");if(!GrowwClient.sessionDay().equals(d)){done=0;store.put("live_buys_day",GrowwClient.sessionDay());store.putInt("live_buys_today",0);}for(TrajectoryCandidate c:out){if(done>=max)break;if(!"UPTREND".equals(c.state))continue;if(store.getBool("bought_"+GrowwClient.sessionDay()+"_"+c.symbol,false))continue;double capital=Double.parseDouble(store.get("capital","10000"));int qty=(int)Math.floor(capital/c.price);if(qty<1)continue;GrowwClient.ApiResult<String> r=api.buyCncMarket(c.symbol,qty);if(r.ok){done++;store.putInt("live_buys_today",done);store.putBool("bought_"+GrowwClient.sessionDay()+"_"+c.symbol,true);notifyCall("CNC UPTREND BUY SENT: "+c.symbol,"Qty "+qty+" • ₹"+fmt(c.price)+" • trajectory "+fmt(c.score));}else notifyCall("UPTREND BUY REJECTED: "+c.symbol,r.error);}}
'''
if anchor not in s: raise SystemExit('broadcast insertion anchor missing')
s=s.replace(anchor,methods+anchor)
s=s.replace('i.putExtra("cards",serialize(lastCandidates));sendBroadcast(i);', 'i.putExtra("cards",serialize(lastCandidates));i.putExtra("trajectory_cards",serializeTrajectory(lastTrajectoryCandidates));sendBroadcast(i);')
anchor='    private Notification notification(String text)'
method=r'''    private String serializeTrajectory(List<TrajectoryCandidate> cs){org.json.JSONArray a=new org.json.JSONArray();try{for(TrajectoryCandidate c:cs)a.put(new org.json.JSONObject().put("s",c.symbol).put("sector",c.sector).put("state",c.state).put("why",c.reason).put("p",c.price).put("g",c.sessionGain).put("sc",c.score).put("cf",c.confidence).put("pace",c.pace).put("recent",c.recent).put("r2",c.r2).put("p15",c.pos15).put("p30",c.pos30).put("vw",c.vwapHold).put("hl",c.higherLows).put("path",c.path).put("loc",c.closeLocation).put("dd",c.maxDrawdown).put("gap",c.gap).put("post",c.postOpen).put("turn",c.turnover).put("flow",c.flow));}catch(Exception ignored){}return a.toString();}
'''
if anchor not in s: raise SystemExit('serialize insertion anchor missing')
s=s.replace(anchor,method+anchor)
svc.write_text(s)

main=root/'app/src/main/java/com/suhas/nsedeliverymomentum/MainActivity.java'
m=main.read_text()
m=m.replace('private LinearLayout root,cards,connectionRow;', 'private LinearLayout root,cards,trajectoryCards,connectionRow;')
m=m.replace('private TextView status,hitValue,rateValue,callsValue,benchValue,growwChip,ipChip,scannerChip,candidateHeader,liveState,liveSub;', 'private TextView status,hitValue,rateValue,callsValue,benchValue,growwChip,ipChip,scannerChip,candidateHeader,trajectoryHeader,liveState,liveSub;')
old='''        cards=column();root.addView(cards);
        renderEmpty();

        TextView foot=label("DELIVERY ONLY  •  ALL NSE CASH EQ DISCOVERY  •  NO MIS / F&O  •  NO AUTO-SELL",10,muted,true);'''
new='''        cards=column();root.addView(cards);
        renderEmpty();

        TextView divider=label("",1,muted,false);divider.setBackgroundColor(Color.rgb(9,31,44));LinearLayout.LayoutParams divp=new LinearLayout.LayoutParams(-1,dp(3));divp.setMargins(0,dp(22),0,dp(22));root.addView(divider,divp);
        LinearLayout th=row(Gravity.CENTER_VERTICAL);trajectoryHeader=label("UPWARD TRAJECTORY • TOP 5",16,text,true);th.addView(trajectoryHeader,new LinearLayout.LayoutParams(0,-2,1));TextView trendTag=label("SESSION TREND",10,blue,true);trendTag.setGravity(Gravity.CENTER);trendTag.setBackground(round(blueDim,dp(12),0,0));trendTag.setPadding(dp(10),dp(6),dp(10),dp(6));th.addView(trendTag);root.addView(th);
        TextView trendExplain=label("Independent all-NSE engine for stocks climbing through the day: positive session + recent slope, smooth regression, repeated positive 15/30m windows, higher lows, VWAP hold, controlled drawdown and near-high location. Gap-only and one-spike moves are penalized.",12,muted,false);trendExplain.setPadding(0,dp(4),0,dp(10));root.addView(trendExplain);
        trajectoryCards=column();root.addView(trajectoryCards);renderTrajectoryEmpty();

        TextView foot=label("DELIVERY ONLY  •  ALL NSE CASH EQ DISCOVERY  •  TWO INDEPENDENT ENGINES  •  NO MIS / F&O  •  NO AUTO-SELL",10,muted,true);'''
if old not in m: raise SystemExit('UI second table insertion anchor missing')
m=m.replace(old,new)
old='''        String js=i.getStringExtra("cards");cards.removeAllViews();int count=0;
        try{JSONArray a=new JSONArray(js==null?"[]":js);count=a.length();if(count==0)renderEmpty();else for(int n=0;n<a.length();n++)candidateCard(a.getJSONObject(n),n+1);}catch(Exception e){renderError();}
        candidateHeader.setText("TOP CONTINUATION CANDIDATES"+(count>0?"  •  "+count:""));updateHeaderState();updateLiveCard();'''
new='''        String js=i.getStringExtra("cards");cards.removeAllViews();int count=0;
        try{JSONArray a=new JSONArray(js==null?"[]":js);count=a.length();if(count==0)renderEmpty();else for(int n=0;n<a.length();n++)candidateCard(a.getJSONObject(n),n+1);}catch(Exception e){renderError();}
        candidateHeader.setText("TOP CONTINUATION CANDIDATES"+(count>0?"  •  "+count:""));
        String tj=i.getStringExtra("trajectory_cards");trajectoryCards.removeAllViews();int tcount=0;try{JSONArray a=new JSONArray(tj==null?"[]":tj);tcount=a.length();if(tcount==0)renderTrajectoryEmpty();else for(int n=0;n<a.length();n++)trajectoryCard(a.getJSONObject(n),n+1);}catch(Exception e){renderTrajectoryError();}trajectoryHeader.setText("UPWARD TRAJECTORY • TOP 5"+(tcount>0?"  •  "+tcount:""));updateHeaderState();updateLiveCard();'''
if old not in m: raise SystemExit('render anchor missing')
m=m.replace(old,new)
anchor='    private void smallStat('
methods=r'''    private void renderTrajectoryEmpty(){LinearLayout e=column();e.setGravity(Gravity.CENTER);e.setPadding(dp(22),dp(24),dp(22),dp(24));e.setBackground(round(surface,dp(20),stroke,1));TextView dot=label("↗",27,blue,true);dot.setGravity(Gravity.CENTER);e.addView(dot);TextView a=label("SEARCHING FOR SESSION UPTRENDS",16,text,true);a.setGravity(Gravity.CENTER);e.addView(a);TextView b=label("The trajectory engine is separate from the continuation table and looks for persistent upward drift rather than isolated spikes.",12,muted,false);b.setGravity(Gravity.CENTER);b.setPadding(dp(8),dp(7),dp(8),0);e.addView(b);trajectoryCards.addView(e,new LinearLayout.LayoutParams(-1,-2));}
    private void renderTrajectoryError(){TextView x=label("Trajectory display error — scanner continues in background.",13,red,false);x.setPadding(dp(16),dp(16),dp(16),dp(16));x.setBackground(round(redDim,dp(16),0,0));trajectoryCards.addView(x);}
    private void trajectoryCard(JSONObject j,int rank){String state=j.optString("state","WATCH");int col="UPTREND".equals(state)?green:"BUILDING".equals(state)?blue:muted;int dim="UPTREND".equals(state)?greenDim:"BUILDING".equals(state)?blueDim:surface2;LinearLayout c=column();c.setPadding(dp(18),dp(17),dp(18),dp(17));c.setBackground(round(surface,dp(22),stroke,1));LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-1,-2);lp.setMargins(0,dp(7),0,dp(9));trajectoryCards.addView(c,lp);
        LinearLayout top=row(Gravity.CENTER_VERTICAL);TextView rb=label("#"+rank,12,bg,true);rb.setGravity(Gravity.CENTER);rb.setBackground(round(col,dp(11),0,0));top.addView(rb,new LinearLayout.LayoutParams(dp(40),dp(32)));LinearLayout nm=column();LinearLayout.LayoutParams np=new LinearLayout.LayoutParams(0,-2,1);np.setMargins(dp(11),0,dp(8),0);nm.addView(label(j.optString("s","—"),21,text,true));nm.addView(label(j.optString("sector","UNKNOWN"),11,muted,false));top.addView(nm,np);TextView pill=label(state,11,col,true);pill.setGravity(Gravity.CENTER);pill.setBackground(round(dim,dp(12),col,1));pill.setPadding(dp(12),dp(7),dp(12),dp(7));top.addView(pill);c.addView(top);
        LinearLayout priceRow=row(Gravity.BOTTOM);LinearLayout pc=column();pc.addView(label("CURRENT PRICE",9,muted,true));pc.addView(label(String.format(Locale.US,"₹%.2f",j.optDouble("p")),25,text,true));priceRow.addView(pc,new LinearLayout.LayoutParams(0,-2,1));double gain=j.optDouble("g");LinearLayout dc=column();TextView dl=label("DAY MOVE",9,muted,true);dl.setGravity(Gravity.RIGHT);TextView dv=label(String.format(Locale.US,"%+.2f%%",gain),20,gain>=0?green:red,true);dv.setGravity(Gravity.RIGHT);dc.addView(dl);dc.addView(dv);priceRow.addView(dc);LinearLayout.LayoutParams prp=new LinearLayout.LayoutParams(-1,-2);prp.setMargins(0,dp(15),0,dp(10));c.addView(priceRow,prp);
        LinearLayout sr=row(Gravity.CENTER_VERTICAL);TextView cf=label(String.format(Locale.US,"TRAJECTORY %.0f/100",j.optDouble("sc")),12,col,true);cf.setBackground(round(dim,dp(10),0,0));cf.setPadding(dp(10),dp(7),dp(10),dp(7));sr.addView(cf);sr.addView(label(String.format(Locale.US,"  CONFIDENCE %.0f",j.optDouble("cf")),12,muted,true));c.addView(sr);
        LinearLayout g1=row(Gravity.CENTER_VERTICAL);smallStat(g1,"SESSION SLOPE",String.format(Locale.US,"%+.2f%%/h",j.optDouble("pace")),j.optDouble("pace")>=0.35?green:text);smallStat(g1,"RECENT SLOPE",String.format(Locale.US,"%+.2f%%/h",j.optDouble("recent")),j.optDouble("recent")>=0.2?green:amber);c.addView(g1);
        LinearLayout g2=row(Gravity.CENTER_VERTICAL);smallStat(g2,"SMOOTHNESS R²",String.format(Locale.US,"%.2f",j.optDouble("r2")),j.optDouble("r2")>=0.52?green:text);smallStat(g2,"15M UP WINDOWS",String.format(Locale.US,"%.0f%%",100*j.optDouble("p15")),j.optDouble("p15")>=0.62?green:text);c.addView(g2);
        LinearLayout g3=row(Gravity.CENTER_VERTICAL);smallStat(g3,"VWAP HOLD",String.format(Locale.US,"%.0f%%",100*j.optDouble("vw")),j.optDouble("vw")>=0.68?green:text);smallStat(g3,"HIGHER LOWS",String.format(Locale.US,"%.0f%%",100*j.optDouble("hl")),j.optDouble("hl")>=0.48?green:text);c.addView(g3);
        LinearLayout g4=row(Gravity.CENTER_VERTICAL);smallStat(g4,"PATH QUALITY",String.format(Locale.US,"%.0f%%",100*j.optDouble("path")),j.optDouble("path")>=0.30?green:text);smallStat(g4,"MAX DRAWDOWN",String.format(Locale.US,"%.2f%%",j.optDouble("dd")),j.optDouble("dd")<=1.5?green:amber);c.addView(g4);
        LinearLayout g5=row(Gravity.CENTER_VERTICAL);smallStat(g5,"OPEN GAP",String.format(Locale.US,"%+.2f%%",j.optDouble("gap")),Math.abs(j.optDouble("gap"))<=1?green:text);smallStat(g5,"POST-OPEN RISE",String.format(Locale.US,"%+.2f%%",j.optDouble("post")),j.optDouble("post")>=0.8?green:text);c.addView(g5);
        String why=j.optString("why","Waiting for more trajectory evidence");LinearLayout reason=column();reason.setPadding(dp(12),dp(10),dp(12),dp(10));reason.setBackground(round(dim,dp(13),0,0));reason.addView(label("UPTREND".equals(state)?"WHY UPTREND IS CONFIRMED":"WHAT THE TRAJECTORY STILL NEEDS",9,col,true));reason.addView(label(why,12,text,false));LinearLayout.LayoutParams rp=new LinearLayout.LayoutParams(-1,-2);rp.setMargins(0,dp(10),0,0);c.addView(reason,rp);TextView action=label("UPTREND".equals(state)?(store.getBool("live",false)?"LIVE CNC BUY ELIGIBLE":"UPTREND CALL — PAPER MODE"):"MONITORING TRAJECTORY",11,col,true);action.setGravity(Gravity.CENTER);action.setPadding(0,dp(12),0,0);c.addView(action);
    }

'''
if anchor not in m: raise SystemExit('trajectory UI methods anchor missing')
m=m.replace(anchor,methods+anchor)
main.write_text(m)

b=root/'app/build.gradle'
z=b.read_text().replace('versionCode 120','versionCode 130').replace("versionName '1.2.0'","versionName '1.3.0'")
b.write_text(z)

test=root/'app/src/test/java/com/suhas/nsedeliverymomentum/TrajectoryMathTest.java'
test.write_text(r'''package com.suhas.nsedeliverymomentum;
import org.junit.Test;import java.util.*;import static org.junit.Assert.*;
public class TrajectoryMathTest {
    private List<GrowwClient.Candle> smooth(double start,double step,int n){List<GrowwClient.Candle>x=new ArrayList<>();double p=start;for(int i=0;i<n;i++){double o=p;p*=1+step;x.add(new GrowwClient.Candle(1000+i*180,o,p*1.0008,o*0.9995,p,120000+i*3500));}return x;}
    @Test public void smoothAllDayDriftScoresHighly(){List<GrowwClient.Candle>x=smooth(100,0.0008,24);TrajectoryMath.Metrics m=TrajectoryMath.calculate(x,x.get(x.size()-1).close,100,102.2,99.9,1.8,0.3,0.1,0.2,0.04,120,0.6,72);assertTrue(m.r2>0.9);assertTrue(m.positive15>0.8);assertTrue(m.hourlyPace>0.5);assertTrue(m.score>70);}
    @Test public void oneSpikeThenFlatIsRejected(){List<GrowwClient.Candle>x=new ArrayList<>();double p=100;for(int i=0;i<24;i++){double next=i==7?102.4:p*(1+(i<7?0.0002:0.00002));x.add(new GrowwClient.Candle(1000+i*180,p,Math.max(p,next)*1.0004,Math.min(p,next)*0.9996,next,130000));p=next;}TrajectoryMath.Metrics m=TrajectoryMath.calculate(x,p,100,102.7,99.9,2.4,0.2,0,0.1,0.04,150,0.6,72);assertFalse(m.qualified);assertTrue(m.maxSpikeShare>0.5||m.recentPace<0.2);}
    @Test public void gapOnlyMoveIsRejected(){List<GrowwClient.Candle>x=smooth(103,0.00005,22);double l=x.get(x.size()-1).close;TrajectoryMath.Metrics m=TrajectoryMath.calculate(x,l,103,103.5,102.8,3.2,0.2,0,0.1,0.04,140,0.6,70);assertFalse(m.qualified);assertTrue(Math.abs(m.gapPct)>2.0);}
    @Test public void choppyRiseFailsPathOrSmoothness(){List<GrowwClient.Candle>x=new ArrayList<>();double[]p={100,100.8,100.1,101.0,100.3,101.2,100.5,101.4,100.7,101.6,100.9,101.8,101.0,102.0};for(int i=0;i<p.length;i++)x.add(new GrowwClient.Candle(1000+i*180,p[i],p[i]+.12,p[i]-.12,p[i],120000));TrajectoryMath.Metrics m=TrajectoryMath.calculate(x,102,100,102.2,99.8,2.0,0.2,0,0.1,0.05,110,0.6,90);assertFalse(m.qualified);assertTrue(m.pathEfficiency<0.5||m.r2<0.7);}
}
''')

assert 'TrajectoryMath' in svc.read_text()
assert 'Math.min(5,out.size())' in svc.read_text()
assert 'trajectory_cards' in svc.read_text()
assert 'UPWARD TRAJECTORY • TOP 5' in main.read_text()
assert "versionName '1.3.0'" in b.read_text()
print('Delivery Momentum v1.3.0 trajectory patch applied')
