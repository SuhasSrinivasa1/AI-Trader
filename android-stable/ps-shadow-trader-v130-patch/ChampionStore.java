package com.ps.shadowtrader;

import android.content.*;
import org.json.*;
import java.util.*;

public final class ChampionStore {
    public static final String[] KEYS={"ema","rsi","vwap","macd","volume","candle","breakout","persistence","relative","micro","accel","reversion"};
    private final android.content.SharedPreferences p;

    public ChampionStore(Context c){p=c.getSharedPreferences("champion_store",Context.MODE_PRIVATE);}

    public static final class Profile {
        public final String id;
        public final Map<String,Double> weights;
        public final double confidenceFloor;
        public final double costFactor;
        public final double score;
        public final double validationNet;
        public final double validationDrawdown;
        public final int validationTrades;
        public final long promotedAt;
        Profile(String id,Map<String,Double>w,double floor,double cost,double score,double net,double dd,int trades,long promotedAt){
            this.id=id;this.weights=w;this.confidenceFloor=floor;this.costFactor=cost;this.score=score;this.validationNet=net;this.validationDrawdown=dd;this.validationTrades=trades;this.promotedAt=promotedAt;
        }
    }

    public synchronized Profile current(){
        String raw=p.getString("champion","");
        if(raw.isEmpty())return defaults();
        try{return fromJson(new JSONObject(raw));}catch(Exception e){return defaults();}
    }

    public synchronized void promote(Profile x,String symbol,int tested,String summary){
        try{
            JSONObject o=toJson(new Profile(x.id,x.weights,x.confidenceFloor,x.costFactor,x.score,x.validationNet,x.validationDrawdown,x.validationTrades,System.currentTimeMillis()));
            int gen=p.getInt("generation",0)+1;
            p.edit().putString("champion",o.toString()).putInt("generation",gen)
                    .putString("last_symbol",symbol).putInt("last_tested",tested).putString("last_summary",summary)
                    .putLong("last_tournament",System.currentTimeMillis()).apply();
        }catch(Exception ignored){}
    }

    public synchronized void recordTournament(String symbol,int tested,String summary){
        p.edit().putString("last_symbol",symbol).putInt("last_tested",tested).putString("last_summary",summary)
                .putLong("last_tournament",System.currentTimeMillis()).apply();
    }

    public int generation(){return p.getInt("generation",0);}
    public long lastTournament(){return p.getLong("last_tournament",0);}
    public String lastSummary(){return p.getString("last_summary","No champion tournament has completed yet.");}
    public int lastTested(){return p.getInt("last_tested",0);}

    public boolean needsTournament(String symbol){
        long age=System.currentTimeMillis()-lastTournament();
        String s=p.getString("last_symbol","");
        return age>4L*60L*60L*1000L || !symbol.equals(s);
    }

    public Map<String,Double> blend(Map<String,Double> online){
        Profile c=current();LinkedHashMap<String,Double> out=new LinkedHashMap<>();
        for(String k:KEYS){
            double cw=c.weights.containsKey(k)?c.weights.get(k):1.0;
            double ow=online!=null&&online.containsKey(k)?online.get(k):cw;
            out.put(k,clamp(cw*.72+ow*.28,.12,2.8));
        }
        return out;
    }

    public double confidenceFloor(){
        return clamp(current().confidenceFloor,.50,.86);
    }

    public double costFactor(){
        return clamp(current().costFactor,.65,2.5);
    }

    public String summary(){
        Profile c=current();
        ArrayList<Map.Entry<String,Double>> x=new ArrayList<>(c.weights.entrySet());
        Collections.sort(x,(a,b)->Double.compare(b.getValue(),a.getValue()));
        StringBuilder s=new StringBuilder();
        s.append("Champion ").append(c.id).append(" • generation ").append(generation());
        if(c.validationTrades>0){
            s.append(" • holdout net ").append(String.format(Locale.US,"%+.2f%%",c.validationNet*100));
            s.append(" • drawdown ").append(String.format(Locale.US,"%.2f%%",c.validationDrawdown*100));
            s.append(" • trades ").append(c.validationTrades);
        }
        s.append("\nTop features: ");
        for(int i=0;i<Math.min(5,x.size());i++){
            if(i>0)s.append(" • ");
            s.append(x.get(i).getKey()).append(" ").append(String.format(Locale.US,"%.2f",x.get(i).getValue()));
        }
        return s.toString();
    }

    public Profile make(String id,Map<String,Double>w,double floor,double cost,double score,double net,double dd,int trades){
        return new Profile(id,new LinkedHashMap<>(w),floor,cost,score,net,dd,trades,System.currentTimeMillis());
    }

    private Profile defaults(){
        LinkedHashMap<String,Double>w=new LinkedHashMap<>();
        w.put("ema",1.0);w.put("rsi",.55);w.put("vwap",.7);w.put("macd",.55);w.put("volume",.75);
        w.put("candle",.7);w.put("breakout",.9);w.put("persistence",.65);w.put("relative",.7);
        w.put("micro",1.05);w.put("accel",.75);w.put("reversion",.45);
        return new Profile("BASE",w,.66,1.0,0,0,0,0,0);
    }

    private JSONObject toJson(Profile x)throws Exception{
        JSONObject w=new JSONObject();for(Map.Entry<String,Double>e:x.weights.entrySet())w.put(e.getKey(),e.getValue());
        return new JSONObject().put("id",x.id).put("weights",w).put("floor",x.confidenceFloor).put("cost",x.costFactor)
                .put("score",x.score).put("net",x.validationNet).put("dd",x.validationDrawdown).put("trades",x.validationTrades).put("promoted",x.promotedAt);
    }

    private Profile fromJson(JSONObject o)throws Exception{
        Profile d=defaults();LinkedHashMap<String,Double>w=new LinkedHashMap<>(d.weights);JSONObject j=o.optJSONObject("weights");
        if(j!=null)for(String k:KEYS)if(j.has(k))w.put(k,clamp(j.optDouble(k,w.get(k)),.12,2.8));
        return new Profile(o.optString("id","BASE"),w,o.optDouble("floor",.66),o.optDouble("cost",1.0),
                o.optDouble("score",0),o.optDouble("net",0),o.optDouble("dd",0),o.optInt("trades",0),o.optLong("promoted",0));
    }

    private static double clamp(double x,double a,double b){return Math.max(a,Math.min(b,x));}
}
