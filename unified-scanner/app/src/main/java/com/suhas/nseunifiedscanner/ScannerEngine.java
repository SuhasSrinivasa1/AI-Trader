package com.suhas.nseunifiedscanner;

import android.content.Context;
import android.content.SharedPreferences;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.time.DayOfWeek;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

final class ScannerEngine {
    static final ZoneId IST=ZoneId.of("Asia/Kolkata");
    static final DateTimeFormatter API_TIME=DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss", Locale.US);
    private static final int TOP_PREFILTER=32;
    private static final int TOP_QUOTE=18;
    private final Context context;
    private final LearningStore learning;
    private final LearningInsights insights;

    ScannerEngine(Context c) { context=c.getApplicationContext(); learning=new LearningStore(context); insights=new LearningInsights(context); }

    ScanResult scan(String token) {
        ScanResult result=new ScanResult(); result.scanMs=System.currentTimeMillis();
        if(token==null||token.isEmpty()){result.error="Groww authentication is required";return result;}
        try {
            resolvePending(token);
            resolveShadowPending(token);
            List<Instrument> universe=loadUniverse();
            if(universe.isEmpty()){result.error="NSE instrument universe is empty";return result;}

            Map<String,Double> ltps=new HashMap<>(); Map<String,GrowwApi.Ohlc> ohlcs=new HashMap<>();
            int positive=0, valid=0;
            for(int i=0;i<universe.size();i+=50){
                List<Instrument> chunk=universe.subList(i,Math.min(i+50,universe.size())); List<String> symbols=new ArrayList<>(); for(Instrument x:chunk)symbols.add(x.symbol);
                GrowwApi.Result<Map<String,Double>> lr=GrowwApi.ltpBatch(token,symbols); if(lr.ok)ltps.putAll(lr.value);
                GrowwApi.Result<Map<String,GrowwApi.Ohlc>> or=GrowwApi.ohlcBatch(token,symbols); if(or.ok)ohlcs.putAll(or.value);
            }

            List<PreCandidate> pre=new ArrayList<>();
            for(Instrument ins:universe){
                Double l=ltps.get(ins.symbol); GrowwApi.Ohlc o=ohlcs.get(ins.symbol); if(l==null||o==null||!(l>0)||!(o.close>0)||!(o.open>0))continue;
                double day=(l/o.close-1.0)*100.0; valid++; if(day>0)positive++;
                // Discovery is deliberately wider than the live-entry gate. In a weak market we still want three ranked WATCH names instead of an empty screen.
                if(l<20||l>10000||day<-0.15||day>9.0)continue;
                double fromOpen=(l/o.open-1.0)*100.0; double nearHigh=o.high>0?(o.high-l)/l*100.0:9;
                if(fromOpen<-0.35||nearHigh>3.00)continue;
                PreCandidate p=new PreCandidate();p.instrument=ins;p.ltp=l;p.ohlc=o;p.dayPct=day;
                p.preScore=day*4.0+Math.max(0,2.50-nearHigh)*2.5+Math.max(0,fromOpen)*1.5;
                pre.add(p);
            }
            pre.sort(Comparator.comparingDouble((PreCandidate p)->p.preScore).reversed());
            if(pre.size()>TOP_PREFILTER)pre=new ArrayList<>(pre.subList(0,TOP_PREFILTER));
            result.breadth=valid==0?0:(100.0*positive/valid);

            LocalDateTime now=LocalDateTime.now(IST);
            int completedMinute=(now.getMinute()/5)*5;
            LocalDateTime candleEnd=now.withMinute(completedMinute).withSecond(0).withNano(0).minusSeconds(1);
            LocalDateTime start=candleEnd.minusDays(4).withHour(9).withMinute(15).withSecond(0).withNano(0);
            List<FeatureCandidate> technical=new ArrayList<>();
            for(PreCandidate p:pre){
                GrowwApi.Result<List<GrowwApi.Candle>> hr=GrowwApi.candles(token,p.instrument.growwSymbol,start.format(API_TIME),candleEnd.format(API_TIME),"5minute");
                if(!hr.ok||hr.value.size()<35)continue;
                FeatureCandidate fc=features(p,hr.value,result.breadth); if(fc!=null)technical.add(fc);
            }
            technical.sort(Comparator.comparingDouble((FeatureCandidate x)->x.baseScore).reversed());
            if(technical.size()>TOP_QUOTE)technical=new ArrayList<>(technical.subList(0,TOP_QUOTE));

            List<Recommendation> recs=new ArrayList<>();
            int minScore=context.getSharedPreferences("scanner_prefs",Context.MODE_PRIVATE).getInt("min_score",82);
            LearningStore.Stats stats=learning.stats();
            for(FeatureCandidate fc:technical){
                GrowwApi.Result<GrowwApi.Quote> qr=GrowwApi.quote(token,fc.instrument.symbol);
                if(!qr.ok)continue; fc.quote=qr.value;
                Recommendation r=score(fc,result.breadth,minScore,stats.n); if(r!=null)recs.add(r);
            }
            recs.sort(Comparator.comparingDouble((Recommendation r)->r.rankScore).reversed());
            // Ranks 4–10 are shadow observations: never shown as official recommendations, never enable BUY, and never inflate the headline hit-rate.
            for(int i=3;i<Math.min(10,recs.size());i++) insights.recordShadowIfNew(recs.get(i));
            if(recs.size()>3)recs=new ArrayList<>(recs.subList(0,3));
            for(Recommendation r:recs) learning.recordIfNew(r);
            result.recommendations=recs; result.success=stats; result.minScore=minScore; result.scanned=universe.size(); result.prefiltered=pre.size();
            result.marketLabel=marketLabel(result.breadth,recs);
            saveState(result);
            learning.audit("SCAN","Scanned "+universe.size()+" NSE EQ • top "+recs.size()+" • breadth "+fmt(result.breadth)+"%");
            return result;
        } catch(Exception e){result.error=e.getMessage()==null?e.getClass().getSimpleName():e.getMessage();learning.audit("ERROR","Scan: "+result.error);saveState(result);return result;}
    }

    private FeatureCandidate features(PreCandidate p,List<GrowwApi.Candle> candles,double breadth){
        int n=candles.size(); if(n<35)return null;
        double[] close=new double[n],high=new double[n],low=new double[n],vol=new double[n];
        for(int i=0;i<n;i++){GrowwApi.Candle c=candles.get(i);close[i]=c.close;high[i]=c.high;low[i]=c.low;vol[i]=c.volume;}
        double rsi=Indicators.rsi(close,14); Indicators.Macd macd=Indicators.macd(close); double atr=Indicators.atr(high,low,close,14);
        double oneHour=n>12?(close[n-1]/close[n-13]-1.0)*100.0:0;
        double avgVol=0;int vc=0;for(int i=Math.max(0,n-13);i<n-1;i++){avgVol+=vol[i];vc++;}avgVol=vc==0?0:avgVol/vc;
        double relVol=avgVol>0?vol[n-1]/avgVol:0;
        DayLevels levels=previousDayLevels(candles); double vwap=todayVwap(candles);
        if(!(vwap>0)||!(levels.r1>0)||!(levels.r2>0))return null;
        double entry=p.ltp; double distR1=(entry/levels.r1-1.0)*100.0; double roomR2=(levels.r2/entry-1.0)*100.0;
        double body=Math.abs(candles.get(n-1).close-candles.get(n-1).open); double upper=Math.max(0,candles.get(n-1).high-Math.max(candles.get(n-1).close,candles.get(n-1).open));
        double wickRatio=body>0?upper/body:2.0;
        // WATCH/discovery gate only. Actual BUY remains governed by the much stricter hard gate in score().
        if(entry<vwap*0.998||rsi<46||rsi>79||oneHour<-0.15||relVol<0.75||roomR2<0.20||distR1>0.80||distR1<-1.20||wickRatio>2.6)return null;
        FeatureCandidate f=new FeatureCandidate();f.instrument=p.instrument;f.entry=entry;f.rsi=rsi;f.relVol=relVol;f.macd=macd;f.atr=atr;f.oneHour=oneHour;f.vwap=vwap;f.r1=levels.r1;f.r2=levels.r2;f.distR1=distR1;f.roomR2=roomR2;f.wickRatio=wickRatio;f.dayPct=p.dayPct;
        f.baseScore=35 + Math.min(14,Math.max(0,oneHour*5)) + Math.min(12,Math.max(0,(relVol-1)*8)) + (entry>vwap?9:0) + (macd.hist>0&&macd.hist>macd.prevHist?10:4) + Math.max(0,8-Math.abs(rsi-62)*0.7) + Math.max(0,8-Math.abs(distR1)*8) + Math.min(8,Math.max(0,roomR2*5));
        return f;
    }

    private Recommendation score(FeatureCandidate f,double breadth,int minScore,int modelN){
        GrowwApi.Quote q=f.quote; if(q==null||!(q.ltp>0))return null; double entry=q.ltp;
        double spreadPct=(q.bid>0&&q.ask>0&&q.ask>=q.bid)?((q.ask-q.bid)/entry*100.0):0.25;
        double turnover=entry*q.volume; double depthRatio=(q.totalBuy+q.totalSell)>0?q.totalBuy/(q.totalBuy+q.totalSell):0.5;
        double circuitRoom=q.upperCircuit>entry?(q.upperCircuit/entry-1)*100:99;
        double roomR2=f.r2/entry*100-100; double distR1=entry/f.r1*100-100;
        // LIVE BUY hard gate: intentionally unchanged by the wider discovery universe.
        boolean hard=entry>f.vwap && f.rsi>=55 && f.rsi<=72 && f.relVol>=1.30 && f.macd.hist>0 && f.macd.hist>=f.macd.prevHist && f.oneHour>=0.45 && f.oneHour<=4.0 && spreadPct<=0.22 && turnover>=50_000_000d && roomR2>=0.68 && distR1>=-0.55 && distR1<=0.38 && circuitRoom>=0.80;
        double liquidity=Math.min(1.0,turnover/300_000_000d); double market=AdaptiveModel.clamp((breadth-40)/35.0,0,1);
        double rsiQuality=AdaptiveModel.clamp(1-Math.abs(f.rsi-62)/14.0,0,1); double rel=AdaptiveModel.clamp((f.relVol-1.0)/2.0,0,1);
        double mom=AdaptiveModel.clamp((f.oneHour-0.3)/2.3,0,1); double breakout=AdaptiveModel.clamp(1-Math.abs(distR1)/0.7,0,1); double range=AdaptiveModel.clamp(roomR2/1.3,0,1);
        JSONObject features=new JSONObject(); try{features.put("vwap",entry>f.vwap?1:0);features.put("rsi",rsiQuality);features.put("relvol",rel);features.put("macd",f.macd.hist>=f.macd.prevHist?1:0);features.put("momentum",mom);features.put("breakout",breakout);features.put("liquidity",liquidity);features.put("market",market);features.put("depth",depthRatio);features.put("range",range);
            LocalTime scanTime=LocalDateTime.now(IST).toLocalTime(); double timeQuality=scanTime.isBefore(LocalTime.of(10,30))?1.0:scanTime.isBefore(LocalTime.of(12,0))?0.85:scanTime.isBefore(LocalTime.of(14,0))?0.70:0.45;features.put("time",timeQuality);}catch(Exception ignore){}
        double probability=AdaptiveModel.predict(context,features);
        double score=f.baseScore + Math.min(8,liquidity*8) + Math.max(-4,Math.min(5,(depthRatio-0.5)*12)) - Math.max(0,(spreadPct-0.08)*20) - Math.max(0,(f.rsi-68)*1.6) - Math.max(0,(f.wickRatio-0.7)*3);
        score=Math.max(0,Math.min(99,score));
        double grossPct=0.70; double target=GrowwApi.roundToTick(entry*(1+grossPct/100.0),f.instrument.tick,true);
        double atrPct=f.atr>0?f.atr/entry:0.006; double stopPct=Math.max(0.0025,Math.min(0.0045,atrPct*0.55)); double stop=GrowwApi.roundToTick(entry*(1-stopPct),f.instrument.tick,false);
        double rr=(target-entry)/Math.max(0.01,entry-stop); if(rr<1.35)hard=false;
        boolean qualified=hard && score>=minScore && (modelN<30?probability>=0.70:probability>=0.80);
        Recommendation r=new Recommendation();r.symbol=f.instrument.symbol;r.growwSymbol=f.instrument.growwSymbol;r.tick=f.instrument.tick;r.scanMs=System.currentTimeMillis();r.deadlineMs=r.scanMs+30*60_000L;r.entry=entry;r.target=target;r.stop=stop;r.score=score;r.probability=probability;r.qualified=qualified;r.rankScore=score+(qualified?15:0)+probability*5;r.features=features;
        r.rsi=f.rsi;r.relVol=f.relVol;r.vwap=f.vwap;r.macdHist=f.macd.hist;r.oneHour=f.oneHour;r.r1=f.r1;r.r2=f.r2;r.roomR2=roomR2;r.spreadPct=spreadPct;r.turnover=turnover;r.breadth=breadth;r.depthBuyPct=depthRatio*100;r.marketCap=q.marketCap;
        r.reason=reason(r,hard,minScore,modelN); return r;
    }

    private String reason(Recommendation r,boolean hard,int minScore,int n){
        if(r.qualified)return "QUALIFIED • VWAP + momentum + volume + R1/R2 room + liquidity aligned";
        List<String>x=new ArrayList<>();if(!hard)x.add("hard gates not fully aligned");if(r.score<minScore)x.add("score < "+minScore);if(n>=30&&r.probability<0.80)x.add("learned probability < 80%");if(n<30)x.add("model still calibrating");return "WATCH • "+String.join(" • ",x);
    }

    private void resolvePending(String token){
        long now=System.currentTimeMillis(); for(LearningStore.OpenRec r:learning.openRecommendations()){
            try{
                LocalDateTime st=LocalDateTime.ofInstant(java.time.Instant.ofEpochMilli(r.scanMs),IST).minusMinutes(1); LocalDateTime en=LocalDateTime.ofInstant(java.time.Instant.ofEpochMilli(Math.min(now,r.deadlineMs)),IST).plusMinutes(1);
                GrowwApi.Result<List<GrowwApi.Candle>> hr=GrowwApi.candles(token,r.growwSymbol,st.format(API_TIME),en.format(API_TIME),"5minute"); if(!hr.ok)continue;
                String outcome=null; for(GrowwApi.Candle c:hr.value){boolean hitT=c.high>=r.target;boolean hitS=c.low<=r.stop;if(hitT&&hitS){outcome="AMBIGUOUS";break;}if(hitT){outcome="SUCCESS";break;}if(hitS){outcome="FAIL";break;}}
                if(outcome==null&&now>=r.deadlineMs)outcome="TIMEOUT"; if(outcome!=null){learning.resolve(r.id,outcome,now,r.features);learning.audit("LEARN",r.symbol+" → "+outcome);}
            }catch(Exception ignore){}
        }
    }

    private void resolveShadowPending(String token){
        long now=System.currentTimeMillis();
        for(LearningInsights.ShadowRec r:insights.openShadow()){
            try{
                LocalDateTime st=LocalDateTime.ofInstant(java.time.Instant.ofEpochMilli(r.scanMs),IST).minusMinutes(1); LocalDateTime en=LocalDateTime.ofInstant(java.time.Instant.ofEpochMilli(Math.min(now,r.deadlineMs)),IST).plusMinutes(1);
                GrowwApi.Result<List<GrowwApi.Candle>> hr=GrowwApi.candles(token,r.growwSymbol,st.format(API_TIME),en.format(API_TIME),"5minute"); if(!hr.ok)continue;
                String outcome=null;for(GrowwApi.Candle c:hr.value){boolean hitT=c.high>=r.target;boolean hitS=c.low<=r.stop;if(hitT&&hitS){outcome="AMBIGUOUS";break;}if(hitT){outcome="SUCCESS";break;}if(hitS){outcome="FAIL";break;}}
                if(outcome==null&&now>=r.deadlineMs)outcome="TIMEOUT";if(outcome!=null){insights.resolveShadow(r.id,outcome,now,r.features);learning.audit("SHADOW",r.symbol+" → "+outcome);}
            }catch(Exception ignore){}
        }
    }

    private List<Instrument> loadUniverse() throws Exception {
        File f=new File(context.getFilesDir(),"groww-instruments.csv"); SharedPreferences p=context.getSharedPreferences("scanner_prefs",Context.MODE_PRIVATE);String day=LocalDate.now(IST).toString();
        if(!f.exists()||!day.equals(p.getString("instrument_day",""))){GrowwApi.Result<String> r=GrowwApi.downloadInstrumentCsv();if(r.ok&&r.value.length()>1000){Files.writeString(f.toPath(),r.value,StandardCharsets.UTF_8);p.edit().putString("instrument_day",day).apply();}else if(!f.exists())throw new Exception(r.error);}
        List<String> lines=Files.readAllLines(f.toPath(),StandardCharsets.UTF_8);if(lines.isEmpty())return Collections.emptyList();List<String> h=csv(lines.get(0));Map<String,Integer> idx=new HashMap<>();for(int i=0;i<h.size();i++)idx.put(h.get(i).trim(),i);
        List<Instrument> out=new ArrayList<>();for(int li=1;li<lines.size();li++){List<String> row=csv(lines.get(li));String ex=get(row,idx,"exchange"),seg=get(row,idx,"segment"),series=get(row,idx,"series"),sym=get(row,idx,"trading_symbol"),gs=get(row,idx,"groww_symbol");if(!"NSE".equalsIgnoreCase(ex)||!"CASH".equalsIgnoreCase(seg)||!"EQ".equalsIgnoreCase(series)||sym.isEmpty()||gs.isEmpty())continue;String ba=get(row,idx,"buy_allowed"),sa=get(row,idx,"sell_allowed");if((!ba.isEmpty()&&!"1".equals(ba))||(!sa.isEmpty()&&!"1".equals(sa)))continue;Instrument x=new Instrument();x.symbol=sym;x.growwSymbol=gs;try{x.tick=Double.parseDouble(get(row,idx,"tick_size"));}catch(Exception e){x.tick=0.05;}if(!(x.tick>0))x.tick=0.05;out.add(x);}return out;
    }

    private static List<String> csv(String line){List<String>o=new ArrayList<>();StringBuilder b=new StringBuilder();boolean q=false;for(int i=0;i<line.length();i++){char c=line.charAt(i);if(c=='\"'){if(q&&i+1<line.length()&&line.charAt(i+1)=='\"'){b.append('\"');i++;}else q=!q;}else if(c==','&&!q){o.add(b.toString());b.setLength(0);}else b.append(c);}o.add(b.toString());return o;}
    private static String get(List<String> row,Map<String,Integer> idx,String key){Integer i=idx.get(key);return i==null||i>=row.size()?"":row.get(i).trim();}

    private static DayLevels previousDayLevels(List<GrowwApi.Candle> c){Map<String,double[]>days=new LinkedHashMap<>();for(GrowwApi.Candle x:c){String d=x.time.length()>=10?x.time.substring(0,10):"";double[]v=days.get(d);if(v==null){v=new double[]{x.high,x.low,x.close};days.put(d,v);}else{v[0]=Math.max(v[0],x.high);v[1]=Math.min(v[1],x.low);v[2]=x.close;}}
        List<double[]>vals=new ArrayList<>(days.values());DayLevels l=new DayLevels();if(vals.size()<2)return l;double[]p=vals.get(vals.size()-2);double pivot=(p[0]+p[1]+p[2])/3.0;l.r1=2*pivot-p[1];l.r2=pivot+(p[0]-p[1]);l.r3=p[0]+2*(pivot-p[1]);return l;}
    private static double todayVwap(List<GrowwApi.Candle> c){if(c.isEmpty())return 0;String d=c.get(c.size()-1).time.length()>=10?c.get(c.size()-1).time.substring(0,10):"";double pv=0,v=0;for(GrowwApi.Candle x:c){if(!x.time.startsWith(d))continue;double t=(x.high+x.low+x.close)/3.0;pv+=t*x.volume;v+=x.volume;}return v>0?pv/v:c.get(c.size()-1).close;}
    private static String marketLabel(double breadth,List<Recommendation> recs){if(breadth>=60)return "BULLISH breadth";if(breadth<=40)return "WEAK / selective";return "MIXED / selective";}
    private void saveState(ScanResult r){context.getSharedPreferences("scanner_state",Context.MODE_PRIVATE).edit().putString("last_scan",r.toJson().toString()).apply();}
    static ScanResult state(Context c){String s=c.getSharedPreferences("scanner_state",Context.MODE_PRIVATE).getString("last_scan","");if(s.isEmpty())return new ScanResult();try{return ScanResult.fromJson(new JSONObject(s));}catch(Exception e){return new ScanResult();}}
    private static String fmt(double d){return String.format(Locale.US,"%.1f",d);}

    static boolean marketHoursNow(){LocalDateTime n=LocalDateTime.now(IST);DayOfWeek d=n.getDayOfWeek();if(d==DayOfWeek.SATURDAY||d==DayOfWeek.SUNDAY)return false;LocalTime t=n.toLocalTime();return !t.isBefore(LocalTime.of(9,15))&&t.isBefore(LocalTime.of(15,11));}

    static final class Instrument { String symbol,growwSymbol;double tick; }
    static final class PreCandidate { Instrument instrument;GrowwApi.Ohlc ohlc;double ltp,dayPct,preScore; }
    static final class FeatureCandidate { Instrument instrument;GrowwApi.Quote quote;Indicators.Macd macd;double entry,rsi,relVol,atr,oneHour,vwap,r1,r2,distR1,roomR2,wickRatio,dayPct,baseScore; }
    static final class DayLevels { double r1,r2,r3; }

    static final class Recommendation {
        String symbol,growwSymbol,reason;long scanMs,deadlineMs;double tick,entry,target,stop,score,probability,rankScore,rsi,relVol,vwap,macdHist,oneHour,r1,r2,roomR2,spreadPct,turnover,breadth,depthBuyPct,marketCap;boolean qualified;JSONObject features=new JSONObject();
        JSONObject toJson(){JSONObject o=new JSONObject();try{o.put("symbol",symbol);o.put("growwSymbol",growwSymbol);o.put("reason",reason);o.put("scanMs",scanMs);o.put("deadlineMs",deadlineMs);o.put("tick",tick);o.put("entry",entry);o.put("target",target);o.put("stop",stop);o.put("score",score);o.put("probability",probability);o.put("qualified",qualified);o.put("rsi",rsi);o.put("relVol",relVol);o.put("vwap",vwap);o.put("macdHist",macdHist);o.put("oneHour",oneHour);o.put("r1",r1);o.put("r2",r2);o.put("roomR2",roomR2);o.put("spreadPct",spreadPct);o.put("turnover",turnover);o.put("breadth",breadth);o.put("depthBuyPct",depthBuyPct);o.put("marketCap",marketCap);o.put("features",features);}catch(Exception ignore){}return o;}
        static Recommendation fromJson(JSONObject o){Recommendation r=new Recommendation();r.symbol=o.optString("symbol");r.growwSymbol=o.optString("growwSymbol");r.reason=o.optString("reason");r.scanMs=o.optLong("scanMs");r.deadlineMs=o.optLong("deadlineMs");r.tick=o.optDouble("tick",0.05);r.entry=o.optDouble("entry");r.target=o.optDouble("target");r.stop=o.optDouble("stop");r.score=o.optDouble("score");r.probability=o.optDouble("probability");r.qualified=o.optBoolean("qualified");r.rsi=o.optDouble("rsi");r.relVol=o.optDouble("relVol");r.vwap=o.optDouble("vwap");r.macdHist=o.optDouble("macdHist");r.oneHour=o.optDouble("oneHour");r.r1=o.optDouble("r1");r.r2=o.optDouble("r2");r.roomR2=o.optDouble("roomR2");r.spreadPct=o.optDouble("spreadPct");r.turnover=o.optDouble("turnover");r.breadth=o.optDouble("breadth");r.depthBuyPct=o.optDouble("depthBuyPct");r.marketCap=o.optDouble("marketCap");r.features=o.optJSONObject("features");if(r.features==null)r.features=new JSONObject();return r;}
    }

    static final class ScanResult {
        long scanMs;int scanned,prefiltered,minScore;double breadth;String marketLabel="No scan yet",error="";List<Recommendation> recommendations=new ArrayList<>();LearningStore.Stats success=new LearningStore.Stats();
        JSONObject toJson(){JSONObject o=new JSONObject();try{o.put("scanMs",scanMs);o.put("scanned",scanned);o.put("prefiltered",prefiltered);o.put("minScore",minScore);o.put("breadth",breadth);o.put("marketLabel",marketLabel);o.put("error",error);JSONArray a=new JSONArray();for(Recommendation r:recommendations)a.put(r.toJson());o.put("recommendations",a);}catch(Exception ignore){}return o;}
        static ScanResult fromJson(JSONObject o){ScanResult r=new ScanResult();r.scanMs=o.optLong("scanMs");r.scanned=o.optInt("scanned");r.prefiltered=o.optInt("prefiltered");r.minScore=o.optInt("minScore",82);r.breadth=o.optDouble("breadth");r.marketLabel=o.optString("marketLabel","No scan yet");r.error=o.optString("error","");JSONArray a=o.optJSONArray("recommendations");if(a!=null)for(int i=0;i<a.length();i++){JSONObject x=a.optJSONObject(i);if(x!=null)r.recommendations.add(Recommendation.fromJson(x));}return r;}
    }
}

final class Indicators {
    private Indicators(){}
    static double rsi(double[] c,int p){if(c.length<=p)return 50;double gain=0,loss=0;for(int i=1;i<=p;i++){double d=c[i]-c[i-1];if(d>=0)gain+=d;else loss-=d;}gain/=p;loss/=p;for(int i=p+1;i<c.length;i++){double d=c[i]-c[i-1];gain=(gain*(p-1)+Math.max(0,d))/p;loss=(loss*(p-1)+Math.max(0,-d))/p;}if(loss==0)return 100;double rs=gain/loss;return 100-100/(1+rs);}
    static double emaLast(double[] c,int p){if(c.length==0)return 0;double k=2.0/(p+1);double e=c[0];for(int i=1;i<c.length;i++)e=c[i]*k+e*(1-k);return e;}
    static Macd macd(double[] c){
        Macd m=new Macd(); if(c.length<35)return m;
        double k12=2.0/13.0,k26=2.0/27.0,k9=2.0/10.0;
        double e12=c[0],e26=c[0],signal=0,prevHist=0; boolean signalSeeded=false;
        for(int i=1;i<c.length;i++){
            e12=c[i]*k12+e12*(1-k12); e26=c[i]*k26+e26*(1-k26);
            double line=e12-e26;
            if(!signalSeeded){signal=line;signalSeeded=true;} else signal=line*k9+signal*(1-k9);
            if(i==c.length-2) prevHist=line-signal;
            if(i==c.length-1){m.line=line;m.signal=signal;m.hist=line-signal;}
        }
        m.prevHist=prevHist;m.bullish=m.line>m.signal;return m;
    }
    static double atr(double[] h,double[] l,double[] c,int p){if(c.length<2)return 0;double[]tr=new double[c.length-1];for(int i=1;i<c.length;i++)tr[i-1]=Math.max(h[i]-l[i],Math.max(Math.abs(h[i]-c[i-1]),Math.abs(l[i]-c[i-1])));int s=Math.max(0,tr.length-p);double sum=0;for(int i=s;i<tr.length;i++)sum+=tr[i];return sum/Math.max(1,tr.length-s);}
    static final class Macd{double line,signal,hist,prevHist;boolean bullish;}
}
