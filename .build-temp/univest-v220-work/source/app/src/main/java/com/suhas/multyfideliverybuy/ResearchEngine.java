package com.suhas.multyfideliverybuy;

import android.content.Context;
import org.json.JSONArray;
import org.json.JSONObject;
import java.util.*;
import java.util.concurrent.TimeUnit;

final class ResearchEngine {
    private static final long DAY=TimeUnit.DAYS.toMillis(1);
    private static final int SCAN_SIZE=60;
    private ResearchEngine(){}

    static boolean isOffMarketNowIst(){
        Calendar c=Calendar.getInstance(TimeZone.getTimeZone("Asia/Kolkata"));
        int d=c.get(Calendar.DAY_OF_WEEK);
        if(d==Calendar.SATURDAY||d==Calendar.SUNDAY)return true;
        int m=c.get(Calendar.HOUR_OF_DAY)*60+c.get(Calendar.MINUTE);
        return m<540||m>=960;
    }

    static void runNightly(Context c){
        if(!isOffMarketNowIst()){AppPrefs.setResearchStatus(c,"Research is locked during market hours.");return;}
        try{
            ResearchDiagnosticsImporter.importOfficialSignals(c);
            InstrumentRepository.refreshIfStale(c);
            List<InstrumentRepository.Instrument> all=InstrumentRepository.load(c);
            learn(c,all);
            JSONObject strategies=strategies(c);
            ResearchStore.saveStrategies(c,strategies);
            JSONArray predictions=scan(c,all,strategies);
            ResearchStore.savePredictions(c,predictions);
            AppPrefs.setResearchLastNightlyRun(c,System.currentTimeMillis());
            AppPrefs.setResearchStatus(c,"Research complete - "+predictions.length()+" next expected candidates.");
            DiagnosticsStore.runtime(c,"RESEARCH_COMPLETE","",AppPrefs.getResearchStatus(c));
        }catch(Throwable t){
            AppPrefs.setResearchStatus(c,"Research error: "+(t.getMessage()==null?t.getClass().getSimpleName():t.getMessage()));
            DiagnosticsStore.error(c,"RESEARCH_FAILED","","Research Lab failed.",t);
        }
    }

    private static void learn(Context c,List<InstrumentRepository.Instrument> instruments){
        Set<String> done=new HashSet<>();
        for(JSONObject j:ResearchStore.featureSnapshots(c))done.add(j.optString("symbol")+"|"+j.optLong("signalAt"));
        Map<String,InstrumentRepository.Instrument> map=new HashMap<>();
        for(InstrumentRepository.Instrument i:instruments)map.put(i.symbol.toUpperCase(Locale.US),i);
        int n=0;
        for(JSONObject sig:ResearchStore.signals(c)){
            if(n>=12)break;
            if(!"ENTRY".equals(sig.optString("type")))continue;
            String symbol=sig.optString("symbol","").toUpperCase(Locale.US);
            long at=sig.optLong("signalAt",0L);
            if(symbol.isEmpty()||at<=0||done.contains(symbol+"|"+at))continue;
            try{
                List<GrowwClient.Candle> candles=GrowwClient.getHistoricalCandles(c,symbol,at-140*DAY,at+DAY,"1day");
                ResearchMath.Features f=ResearchMath.fromCandles(candles);
                if(!(f.close>0))continue;
                ResearchMath.StrategyScores sc=ResearchMath.score(f,0,0,false);
                JSONObject j=feature(symbol,at,f,sc);
                InstrumentRepository.Instrument ins=map.get(symbol);
                j.put("companyName",ins==null?symbol:ins.name);
                j.put("source","OFFICIAL_UNIVEST_ENTRY");
                ResearchStore.appendFeature(c,j);
                n++;
            }catch(Throwable ignored){}
        }
    }

    private static JSONObject strategies(Context c){
        String[] names={"VOLUME_BREAKOUT","TREND_PULLBACK","MOMENTUM_CONTINUATION","QUALITY_RERATING","CATALYST_SECTOR"};
        Map<String,Integer> count=new LinkedHashMap<>();Map<String,Double> sum=new LinkedHashMap<>();
        for(String n:names){count.put(n,0);sum.put(n,0.0);}
        for(JSONObject j:ResearchStore.featureSnapshots(c)){
            String n=j.optString("bestStrategy","");
            if(!count.containsKey(n))continue;
            count.put(n,count.get(n)+1);sum.put(n,sum.get(n)+j.optInt("bestScore",0));
        }
        JSONArray a=new JSONArray();String champion="";double best=-1;
        for(String n:names){
            int e=count.get(n);double avg=e==0?0:sum.get(n)/e;double rank=e*avg;
            if(rank>best){best=rank;champion=n;}
            JSONObject j=new JSONObject();
            try{j.put("name",n);j.put("evidence",e);j.put("avgMatch",avg);j.put("status",e>=8?"CHALLENGER":e>=3?"DEVELOPING":"EXPERIMENTAL");a.put(j);}catch(Exception ignored){}
        }
        if(count.get(champion)>=5)for(int i=0;i<a.length();i++){JSONObject j=a.optJSONObject(i);if(j!=null&&champion.equals(j.optString("name")))try{j.put("status","CHAMPION");}catch(Exception ignored){}}
        JSONObject out=new JSONObject();try{out.put("updatedAt",System.currentTimeMillis());out.put("champion",champion);out.put("strategies",a);}catch(Exception ignored){}return out;
    }

    private static JSONArray scan(Context c,List<InstrumentRepository.Instrument> all,JSONObject strategies){
        List<InstrumentRepository.Instrument> e=new ArrayList<>();
        for(InstrumentRepository.Instrument i:all)if(i.buyAllowed)e.add(i);
        e.sort(Comparator.comparing(x->x.symbol));
        if(e.isEmpty())return new JSONArray();
        int cursor=AppPrefs.getResearchScanCursor(c)%e.size();
        int take=Math.min(SCAN_SIZE,e.size());
        ArrayList<JSONObject> list=new ArrayList<>();
        long now=System.currentTimeMillis();
        for(int k=0;k<take;k++){
            InstrumentRepository.Instrument ins=e.get((cursor+k)%e.size());
            try{
                List<GrowwClient.Candle> candles=GrowwClient.getHistoricalCandles(c,ins.symbol,now-140*DAY,now,"1day");
                ResearchMath.Features f=ResearchMath.fromCandles(candles);
                if(!(f.close>0)||f.dataPoints<20)continue;
                ResearchMath.StrategyScores sc=ResearchMath.score(f,0,0,false);
                if(sc.bestScore<60)continue;
                double[] z=ResearchMath.learnedZones(f,0);
                JSONObject j=feature(ins.symbol,now,f,sc);
                j.put("companyName",ins.name);j.put("strategy",sc.bestStrategy);j.put("similarity",sc.bestScore);j.put("consensus",sc.consensus);
                j.put("buyLow",z[0]);j.put("buyHigh",z[1]);j.put("chaseLimit",z[2]);j.put("sellLow",z[3]);j.put("sellHigh",z[4]);
                j.put("reasons",reasons(f));j.put("counterSignals",counter(f));j.put("scannedAt",now);list.add(j);
            }catch(Throwable ignored){}
        }
        AppPrefs.setResearchScanCursor(c,(cursor+take)%e.size());
        list.sort((a,b)->Integer.compare(b.optInt("similarity"),a.optInt("similarity")));
        if(list.size()>10)list=new ArrayList<>(list.subList(0,10));
        JSONArray intel=new JSONArray();
        for(JSONObject j:list){
            try{
                ResearchNewsClient.Summary n=ResearchNewsClient.fetch(j.optString("companyName"),j.optString("symbol"));
                j.put("nationalNews",n.nationalCount);j.put("internationalNews",n.internationalCount);j.put("newsSignal",n.catalystLabel);
                JSONObject x=new JSONObject();x.put("symbol",j.optString("symbol"));x.put("national",n.nationalCount);x.put("international",n.internationalCount);
                x.put("signal",n.catalystLabel);x.put("headlines",n.topHeadlines);x.put("at",now);intel.put(x);
            }catch(Throwable ignored){}
        }
        ResearchStore.saveIntelligence(c,intel);
        JSONArray out=new JSONArray();for(JSONObject j:list)out.put(j);return out;
    }

    private static JSONObject feature(String symbol,long at,ResearchMath.Features f,ResearchMath.StrategyScores sc){
        JSONObject j=new JSONObject();
        try{
            j.put("symbol",symbol);j.put("signalAt",at);j.put("close",f.close);j.put("sma20",f.sma20);j.put("sma50",f.sma50);
            j.put("rsi14",f.rsi14);j.put("atr14",f.atr14);j.put("relativeVolume20",f.relativeVolume20);
            j.put("return5Pct",f.return5Pct);j.put("return20Pct",f.return20Pct);j.put("return60Pct",f.return60Pct);
            j.put("prior20High",f.prior20High);j.put("volatility20Pct",f.volatility20Pct);j.put("dataPoints",f.dataPoints);
            j.put("bestStrategy",sc.bestStrategy);j.put("bestScore",sc.bestScore);j.put("consensus",sc.consensus);
        }catch(Exception ignored){}
        return j;
    }

    private static String reasons(ResearchMath.Features f){
        ArrayList<String> r=new ArrayList<>();
        if(f.relativeVolume20>=1.15)r.add(String.format(Locale.US,"Volume %.2fx average",f.relativeVolume20));
        if(f.prior20High>0&&f.close>=f.prior20High*.985)r.add("Near or above 20-session resistance");
        if(f.sma20>f.sma50&&f.sma50>0)r.add("20-day trend above 50-day");
        if(f.rsi14>=50&&f.rsi14<=75)r.add(String.format(Locale.US,"RSI %.1f constructive",f.rsi14));
        if(f.return20Pct>0)r.add(String.format(Locale.US,"20-session momentum +%.1f%%",f.return20Pct));
        return join(r);
    }
    private static String counter(ResearchMath.Features f){
        ArrayList<String> r=new ArrayList<>();
        if(f.rsi14>76)r.add("RSI extended");if(f.relativeVolume20<.75)r.add("weak volume");if(f.return5Pct<-2)r.add("negative 5-session momentum");
        if(f.sma50>0&&f.close<f.sma50)r.add("below 50-day trend");if(r.isEmpty())r.add("No major technical counter-signal");return join(r);
    }
    private static String join(List<String> a){StringBuilder b=new StringBuilder();for(String x:a){if(b.length()>0)b.append(" | ");b.append(x);}return b.toString();}

    static String predictionsText(Context c,int limit){
        JSONArray a=ResearchStore.predictions(c);if(a.length()==0)return "No off-market scan completed yet.";StringBuilder b=new StringBuilder();
        for(int i=0;i<a.length()&&i<limit;i++){JSONObject j=a.optJSONObject(i);if(j==null)continue;if(b.length()>0)b.append("\n\n");
            b.append(i+1).append(". ").append(j.optString("symbol")).append(" - ").append(j.optInt("similarity")).append("/100 - ").append(j.optString("strategy"))
             .append("\nConsensus ").append(j.optInt("consensus")).append("/5 - RESEARCH PREDICTION")
             .append(String.format(Locale.US,"\nBuy-pattern zone %.2f-%.2f | chase ceiling %.2f\nSell-pattern zone %.2f-%.2f",j.optDouble("buyLow"),j.optDouble("buyHigh"),j.optDouble("chaseLimit"),j.optDouble("sellLow"),j.optDouble("sellHigh")))
             .append("\n").append(j.optString("reasons")).append("\nCounter: ").append(j.optString("counterSignals"));
        }
        return b.toString();
    }

    static String strategiesText(Context c){
        JSONObject o=ResearchStore.strategies(c);JSONArray a=o.optJSONArray("strategies");if(a==null||a.length()==0)return "No strategy fingerprints learned yet.";StringBuilder b=new StringBuilder();
        for(int i=0;i<a.length();i++){JSONObject j=a.optJSONObject(i);if(j==null)continue;if(b.length()>0)b.append("\n\n");
            b.append(j.optString("name")).append(" - ").append(j.optString("status")).append("\nEvidence ").append(j.optInt("evidence"))
             .append(" official recommendations - avg match ").append(String.format(Locale.US,"%.0f",j.optDouble("avgMatch"))).append("/100");
        }
        return b.toString();
    }

    static String intelligenceText(Context c){
        JSONArray a=ResearchStore.intelligence(c);if(a.length()==0)return "News intelligence will populate after the next off-market scan.";StringBuilder b=new StringBuilder();
        for(int i=0;i<a.length()&&i<5;i++){JSONObject j=a.optJSONObject(i);if(j==null)continue;if(b.length()>0)b.append("\n\n");
            b.append(j.optString("symbol")).append(" - India ").append(j.optInt("national")).append(" - International ").append(j.optInt("international")).append("\n").append(j.optString("signal"));
        }
        return b.toString();
    }
}
