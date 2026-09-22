package com.ps.shadowtrader;

import android.content.*;
import org.json.*;
import java.util.*;
import static com.ps.shadowtrader.Models.*;

public final class MomentumLabEngine {
    private static final int BATCH=36;
    private static final long DAY=86400000L;
    private final Context c; private final GrowwClient api; private final EventStore events;
    public MomentumLabEngine(Context c,GrowwClient api){this.c=c.getApplicationContext();this.api=api;this.events=new EventStore(c);}

    public String scanNextBatch(String token)throws Exception{
        List<String> universe=UniverseRepository.load(c,api);
        if(universe.isEmpty())return "30-Day Lab universe unavailable";

        android.content.SharedPreferences p=c.getSharedPreferences("momentum",Context.MODE_PRIVATE);
        int cursor=p.getInt("cursor",0);if(cursor>=universe.size())cursor=0;
        int cycle=p.getInt("cycle",0);

        long end=System.currentTimeMillis()/1000L,start=end-1000L*86400L;
        List<Candle> nifty=api.candles(token,"NIFTY",start,end,"1day");
        double nifty20=ret(nifty,Math.min(20,Math.max(1,nifty.size()-1)));
        String marketRegime=regime(nifty20);

        Map<String,String> sectors;
        try{sectors=InstrumentMetadataRepository.sectors(c,api);}catch(Exception e){sectors=new HashMap<>();}
        SectorContextStore sectorStore=new SectorContextStore(c);
        ThirtyDayDataset dataset=new ThirtyDayDataset(c);
        LongHorizonChampionStore.Profile champion=new LongHorizonChampionStore(c).current();

        int checked=0,added=0,controls=0,fetchErrors=0; String firstFetchError="";
        boolean wrapped=false;

        for(int k=0;k<BATCH&&k<universe.size();k++){
            int idx=(cursor+k)%universe.size();
            if(idx<cursor&&k>0)wrapped=true;
            String symbol=universe.get(idx);checked++;
            try{
                List<Candle>d=api.candles(token,symbol,start,end,"1day");
                if(d==null||d.size()<100)continue;
                String sector=sectors.containsKey(symbol)?sectors.get(symbol):"UNKNOWN";
                double r20=ret(d,20),sectorMean=sectorStore.mean(sector);
                double[] niftySeries=alignNifty20(d,nifty);
                dataset.addFromHistory(symbol,d,niftySeries,sector,sectorMean);

                Map<String,Double> f=LongHorizonFeatures.current(d,nifty20,sectorMean);
                ReplayEvidence replay=localReplay(d,f);
                double raw=LongHorizonFeatures.probability(f,champion);
                double blended=clamp(raw*.72+replay.hitRate*.18+Math.min(.10,replay.matches*.01),.01,.99);
                double confidence=calibrate(p,blended);
                double threshold=champion.threshold;

                double last=d.get(d.size()-1).c;
                if(last<=0)continue;

                updateExistingPrediction(p,symbol,d);
                if(confidence>=threshold&&replay.matches>=2){
                    Candidate x=new Candidate();
                    x.symbol=symbol;x.price=last;x.target=last*1.5;x.confidence=confidence;x.rawConfidence=raw;
                    x.created=System.currentTimeMillis();x.lastEvaluated=x.created;x.expiry=x.created+30L*DAY;x.maxSeen=last;
                    x.features=new LinkedHashMap<>(f);
                    x.sector=sector;x.generation=new LongHorizonChampionStore(c).generation();x.champion=champion.id;
                    x.matches=replay.matches;x.replayHitRate=replay.hitRate;x.replayMedianPeak=replay.medianPeak;
                    x.reason=reason(f,replay,nifty20,sector,sectorMean,champion);
                    if(upsertCurrentSnapshotLocked(p,x))added++;
                }else if(confidence>=.45&&confidence<threshold){
                    storeControl(p,symbol,last,confidence,sector,champion.id);
                    controls++;
                }

                sectorStore.observe(sector,r20);
            }catch(Exception ignored){}
        }

        int newCursor=(cursor+checked)%universe.size();
        if(newCursor<cursor||newCursor==0)wrapped=true;
        if(wrapped){cycle++;newCursor=0;}

        p.edit().putInt("cursor",newCursor).putInt("universe_size",universe.size()).putInt("cycle",cycle)
                .putLong("last_scan",System.currentTimeMillis()).putString("market_regime",marketRegime)
                .putInt("dataset_examples",dataset.size()).apply();

        closeExpired(token,p);
        closeExpiredControls(token,p,5);

        LongHorizonChampionStore store=new LongHorizonChampionStore(c);
        String tournament="";
        if(store.due(dataset.size())){
            tournament=new ThirtyDayTournamentEngine(c).run();
            champion=store.current();
            p.edit().putString("lab_champion_summary",store.summary()).putString("lab_tournament_status",tournament).apply();
            events.add("LAB-CHAMPION",tournament);
        }

        String msg="30-Day Lab bootstrap scanned "+checked+" NSE equities • "+added+" published • "+controls+" near-miss controls • coverage "+newCursor+"/"+universe.size()+" • cycle "+cycle+" • labeled examples "+dataset.size()+" • fetch errors "+fetchErrors; if(fetchErrors>0&&!firstFetchError.isEmpty())msg+=" • first error "+firstFetchError;
        if(!tournament.isEmpty())msg+=" • tournament updated";
        events.add("LAB",msg);
        return msg;
    }

    private boolean upsertCurrentSnapshotLocked(android.content.SharedPreferences p,Candidate x){
        try{
            JSONArray a=new JSONArray(p.getString("current","[]"));
            JSONArray b=new JSONArray();boolean found=false;
            for(int i=0;i<a.length();i++){
                JSONObject o=a.getJSONObject(i);
                if(o.optString("symbol").equals(x.symbol)){
                    found=true;
                    o.put("lastObserved",x.price)
                            .put("lastEvaluated",x.lastEvaluated)
                            .put("latestModelScore",x.confidence)
                            .put("latestRawScore",x.rawConfidence)
                            .put("latestReason",x.reason)
                            .put("maxSeen",Math.max(o.optDouble("maxSeen",o.optDouble("price")),x.price));
                }
                b.put(o);
            }
            if(!found)b.put(toJson(x));
            p.edit().putString("current",b.toString()).apply();
            return !found;
        }catch(Exception e){return false;}
    }

    private void updateExistingPrediction(android.content.SharedPreferences p,String symbol,List<Candle>d){
        try{
            JSONArray a=new JSONArray(p.getString("current","[]"));boolean changed=false;JSONArray out=new JSONArray();
            for(int i=0;i<a.length();i++){
                JSONObject o=a.getJSONObject(i);
                if(o.optString("symbol").equals(symbol)){
                    double max=o.optDouble("maxSeen",o.optDouble("price"));
                    for(Candle z:d)if(z.ts*1000L>=o.optLong("created"))max=Math.max(max,z.h);
                    o.put("maxSeen",max).put("lastObserved",d.get(d.size()-1).c).put("lastEvaluated",System.currentTimeMillis());
                    if(max>=o.optDouble("target"))o.put("hit50Early",true);
                    changed=true;
                }
                out.put(o);
            }
            if(changed)p.edit().putString("current",out.toString()).apply();
        }catch(Exception ignored){}
    }

    private void closeExpired(String token,android.content.SharedPreferences p){
        try{
            JSONArray a=new JSONArray(p.getString("current","[]")),keep=new JSONArray(),closed=new JSONArray(p.getString("closed","[]"));
            long now=System.currentTimeMillis();
            for(int i=0;i<a.length();i++){
                JSONObject o=a.getJSONObject(i);
                boolean hitEarly=o.optBoolean("hit50Early",false);
                if(now<o.optLong("expiry")&&!hitEarly){keep.put(o);continue;}
                Outcome out=outcome(token,o.optString("symbol"),o.optLong("created"),now,o.optDouble("price"));
                boolean win=out.maxGain>=.50;
                o.put("maxSeen",out.maxPrice).put("minSeen",out.minPrice).put("closed",now)
                        .put("success",win).put("result",win?"WIN":"LOSS")
                        .put("closeReason",win?"50% TARGET HIT":"30-DAY WINDOW EXPIRED")
                        .put("hit30",out.maxGain>=.30)
                        .put("maxGain",out.maxGain).put("maxDrawdown",out.maxDrawdown)
                        .put("daysToPeak",out.daysToPeak).put("closeReturn",out.closeReturn);
                new ThirtyDayDataset(c).addLiveOutcome(o);
                closed.put(o);
            }
            while(closed.length()>120){JSONArray z=new JSONArray();for(int i=closed.length()-120;i<closed.length();i++)z.put(closed.get(i));closed=z;}
            p.edit().putString("current",keep.toString()).putString("closed",closed.toString()).apply();
        }catch(Exception ignored){}
    }

    private void storeControl(android.content.SharedPreferences p,String symbol,double price,double confidence,String sector,String champion){
        try{
            JSONArray a=new JSONArray(p.getString("controls","[]"));long now=System.currentTimeMillis();
            JSONArray b=new JSONArray();boolean found=false;
            for(int i=0;i<a.length();i++){
                JSONObject o=a.getJSONObject(i);
                if(o.optString("symbol").equals(symbol)&&now<o.optLong("expiry"))found=true;
                b.put(o);
            }
            if(!found)b.put(new JSONObject().put("symbol",symbol).put("price",price).put("confidence",confidence)
                    .put("sector",sector).put("champion",champion).put("created",now).put("expiry",now+30L*DAY));
            while(b.length()>100){JSONArray z=new JSONArray();for(int i=b.length()-100;i<b.length();i++)z.put(b.get(i));b=z;}
            p.edit().putString("controls",b.toString()).apply();
        }catch(Exception ignored){}
    }

    private void closeExpiredControls(String token,android.content.SharedPreferences p,int maxChecks){
        try{
            JSONArray a=new JSONArray(p.getString("controls","[]")),keep=new JSONArray(),done=new JSONArray(p.getString("control_outcomes","[]"));
            long now=System.currentTimeMillis();int checks=0;
            for(int i=0;i<a.length();i++){
                JSONObject o=a.getJSONObject(i);
                if(now<o.optLong("expiry")||checks>=maxChecks){keep.put(o);continue;}
                checks++;
                Outcome out=outcome(token,o.optString("symbol"),o.optLong("created"),now,o.optDouble("price"));
                o.put("closed",now).put("wouldHit50",out.maxGain>=.50).put("maxGain",out.maxGain).put("maxDrawdown",out.maxDrawdown);
                done.put(o);
            }
            while(done.length()>120){JSONArray z=new JSONArray();for(int i=done.length()-120;i<done.length();i++)z.put(done.get(i));done=z;}
            p.edit().putString("controls",keep.toString()).putString("control_outcomes",done.toString()).apply();
        }catch(Exception ignored){}
    }

    private Outcome outcome(String token,String symbol,long created,long now,double ref){
        Outcome o=new Outcome();o.maxPrice=ref;o.minPrice=ref;
        try{
            List<Candle>d=api.candles(token,symbol,created/1000L,now/1000L,"1day");
            int peakDay=0;
            for(int i=0;i<d.size();i++){
                Candle z=d.get(i);if(z.h>o.maxPrice){o.maxPrice=z.h;peakDay=i+1;}o.minPrice=Math.min(o.minPrice,z.l);
            }
            o.daysToPeak=peakDay;o.maxGain=ref<=0?0:o.maxPrice/ref-1;o.maxDrawdown=ref<=0?0:Math.max(0,1-o.minPrice/ref);
            if(!d.isEmpty())o.closeReturn=ref<=0?0:d.get(d.size()-1).c/ref-1;
        }catch(Exception ignored){}
        return o;
    }

    private ReplayEvidence localReplay(List<Candle>d,Map<String,Double>current){
        ArrayList<double[]> neighbors=new ArrayList<>();
        int n=d.size();
        for(int i=70;i<n-31;i+=2){
            Map<String,Double>f=LongHorizonFeatures.at(d,i,0,0);
            double dist=0;
            for(String k:LongHorizonChampionStore.KEYS){
                if("relative".equals(k)||"sector_relative".equals(k))continue;
                double q=f.get(k)-current.get(k);dist+=q*q;
            }
            double base=d.get(i).c,peak=0;
            for(int j=i+1;j<=Math.min(n-1,i+30);j++)peak=Math.max(peak,d.get(j).h/base-1);
            neighbors.add(new double[]{dist,peak});
        }
        Collections.sort(neighbors,(a,b)->Double.compare(a[0],b[0]));
        int take=Math.min(10,neighbors.size()),hits=0;double[] peaks=new double[take];
        for(int i=0;i<take;i++){peaks[i]=neighbors.get(i)[1];if(peaks[i]>=.50)hits++;}
        Arrays.sort(peaks);
        ReplayEvidence r=new ReplayEvidence();r.matches=take;r.hitRate=take==0?0:(double)hits/take;r.medianPeak=take==0?0:peaks[take/2];return r;
    }

    private double calibrate(android.content.SharedPreferences p,double raw){
        try{
            JSONArray a=new JSONArray(p.getString("closed","[]"));
            int band=(int)Math.floor(raw*10);int n=0,h=0;
            for(int i=0;i<a.length();i++){
                JSONObject o=a.getJSONObject(i);
                double c=o.optDouble("confidence",-1);
                if(c>=0&&(int)Math.floor(c*10)==band){n++;if(o.optBoolean("success"))h++;}
            }
            if(n>=5){double empirical=(double)h/n;return clamp(raw*.60+empirical*.40,.01,.99);}
        }catch(Exception ignored){}
        return raw;
    }

    public static String scorecard(Context c){
        android.content.SharedPreferences p=c.getSharedPreferences("momentum",Context.MODE_PRIVATE);
        try{
            JSONArray a=new JSONArray(p.getString("closed","[]"));
            if(a.length()==0)return "No completed 30-day predictions yet.";
            int hit50=0,hit30=0;double worstDd=0,avgPeakDays=0;ArrayList<Double>returns=new ArrayList<>();
            for(int i=0;i<a.length();i++){
                JSONObject o=a.getJSONObject(i);if(o.optBoolean("success"))hit50++;if(o.optBoolean("hit30"))hit30++;
                worstDd=Math.max(worstDd,o.optDouble("maxDrawdown",0));avgPeakDays+=o.optInt("daysToPeak",0);returns.add(o.optDouble("closeReturn",0));
            }
            Collections.sort(returns);double med=returns.get(returns.size()/2);avgPeakDays/=a.length();
            JSONArray controls=new JSONArray(p.getString("control_outcomes","[]"));int missed=0;for(int i=0;i<controls.length();i++)if(controls.getJSONObject(i).optBoolean("wouldHit50"))missed++;
            return String.format(Locale.US,"Closed %d • +50%% hits %d (%.0f%%) • +30%% hits %d • median 30d return %+.1f%% • worst drawdown %.1f%% • avg days-to-peak %.1f • rejected stocks later +50%%: %d/%d",
                    a.length(),hit50,(double)hit50/a.length()*100,hit30,med*100,worstDd*100,avgPeakDays,missed,controls.length());
        }catch(Exception e){return "30-day scorecard unavailable";}
    }

    public static JSONArray current(Context c){try{return new JSONArray(c.getSharedPreferences("momentum",Context.MODE_PRIVATE).getString("current","[]"));}catch(Exception e){return new JSONArray();}}
    public static JSONArray closed(Context c){try{return new JSONArray(c.getSharedPreferences("momentum",Context.MODE_PRIVATE).getString("closed","[]"));}catch(Exception e){return new JSONArray();}}

    private JSONObject toJson(Candidate x)throws Exception{
        JSONObject f=new JSONObject();
        if(x.features!=null)for(Map.Entry<String,Double>e:x.features.entrySet())f.put(e.getKey(),e.getValue());
        return new JSONObject().put("symbol",x.symbol).put("price",x.price).put("target",x.target)
                .put("confidence",x.confidence).put("rawConfidence",x.rawConfidence)
                .put("created",x.created).put("firstRecommended",x.created).put("lastEvaluated",x.lastEvaluated)
                .put("expiry",x.expiry).put("maxSeen",x.maxSeen).put("lastObserved",x.price)
                .put("matches",x.matches).put("replayHitRate",x.replayHitRate).put("replayMedianPeak",x.replayMedianPeak)
                .put("reason",x.reason).put("sector",x.sector).put("generation",x.generation).put("champion",x.champion)
                .put("features",f).put("snapshotLocked",true);
    }

    private String reason(Map<String,Double>f,ReplayEvidence r,double nifty20,String sector,double sectorMean,LongHorizonChampionStore.Profile p){
        return String.format(Locale.US,
                "30d champion %s • historical nearest-window +50%% rate %.0f%% (%d matches) • median future peak %.1f%% • 20d relative vs NIFTY %.1f%% • sector %s relative %.1f%% • breakout %.2f • volume %.2f",
                p.id,r.hitRate*100,r.matches,r.medianPeak*100,f.get("relative")/6*100,sector,f.get("sector_relative")/6*100,f.get("breakout"),f.get("volume"));
    }

    private double[] alignNifty20(List<Candle>stock,List<Candle>nifty){
        HashMap<Long,Double> map=new HashMap<>();
        for(int i=20;i<nifty.size();i++){double a=nifty.get(i-20).c,b=nifty.get(i).c;if(a>0)map.put(nifty.get(i).ts,b/a-1);}
        double[] out=new double[stock.size()];for(int i=0;i<stock.size();i++){Double x=map.get(stock.get(i).ts);out[i]=x==null?0:x;}return out;
    }

    private double ret(List<Candle>d,int days){if(d==null||d.size()<days+1)return 0;return d.get(d.size()-1).c/d.get(d.size()-1-days).c-1;}
    private String regime(double x){if(x>.04)return "Strong market";if(x<-.04)return "Weak market";return "Neutral market";}
    private double clamp(double x,double a,double b){return Math.max(a,Math.min(b,x));}

    private static class Candidate{String symbol,reason,sector,champion;double price,target,confidence,rawConfidence,maxSeen,replayHitRate,replayMedianPeak;long created,lastEvaluated,expiry;int matches,generation;Map<String,Double>features;}
    private static class ReplayEvidence{int matches;double hitRate,medianPeak;}
    private static class Outcome{double maxPrice,minPrice,maxGain,maxDrawdown,closeReturn;int daysToPeak;}
}
