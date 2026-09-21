package com.ps.shadowtrader;

import android.content.*;
import org.json.*;
import java.util.*;

public final class LongHorizonChampionStore {
    public static final String[] KEYS={"r5","r20","r60","volume","breakout","rsi","volatility","relative","weekly","acceleration","sector_relative"};
    private final android.content.SharedPreferences p;

    public static final class Profile {
        public final String id; public final Map<String,Double>w; public final double threshold;
        public final double holdoutPrecision,holdoutRecall,score; public final int holdoutSignals; public final long promotedAt;
        Profile(String id,Map<String,Double>w,double threshold,double precision,double recall,double score,int signals,long promotedAt){
            this.id=id;this.w=w;this.threshold=threshold;this.holdoutPrecision=precision;this.holdoutRecall=recall;this.score=score;this.holdoutSignals=signals;this.promotedAt=promotedAt;
        }
    }

    public LongHorizonChampionStore(Context c){p=c.getSharedPreferences("lab30_champion",Context.MODE_PRIVATE);}

    public synchronized Profile current(){
        String raw=p.getString("profile","");
        if(raw.isEmpty())return defaults();
        try{return fromJson(new JSONObject(raw));}catch(Exception e){return defaults();}
    }

    public synchronized void promote(Profile x,String summary,int tested,int examples){
        try{
            p.edit().putString("profile",toJson(new Profile(x.id,x.w,x.threshold,x.holdoutPrecision,x.holdoutRecall,x.score,x.holdoutSignals,System.currentTimeMillis())).toString())
                    .putInt("generation",generation()+1).putString("summary",summary).putInt("tested",tested).putInt("examples",examples)
                    .putLong("last_tournament",System.currentTimeMillis()).apply();
        }catch(Exception ignored){}
    }

    public synchronized void record(String summary,int tested,int examples){
        p.edit().putString("summary",summary).putInt("tested",tested).putInt("examples",examples)
                .putLong("last_tournament",System.currentTimeMillis()).apply();
    }

    public int generation(){return p.getInt("generation",0);}
    public long lastTournament(){return p.getLong("last_tournament",0);}
    public int examples(){return p.getInt("examples",0);}
    public String summary(){return p.getString("summary","30-day champion tournament is waiting for enough labeled replay examples.");}
    public String profileSummary(){
        Profile x=current();
        return x.id+" • generation "+generation()+" • threshold "+String.format(java.util.Locale.US,"%.0f%%",x.threshold*100)+
                (x.holdoutSignals>0?" • holdout precision "+String.format(java.util.Locale.US,"%.0f%%",x.holdoutPrecision*100)+" • recall "+String.format(java.util.Locale.US,"%.0f%%",x.holdoutRecall*100)+" • signals "+x.holdoutSignals:" • awaiting validated holdout history");
    }
    public boolean due(int exampleCount){return exampleCount>=120&&(System.currentTimeMillis()-lastTournament()>6L*3600000L||exampleCount>=examples()+120);}

    public Profile make(String id,Map<String,Double>w,double threshold,double precision,double recall,double score,int signals){
        return new Profile(id,new LinkedHashMap<>(w),threshold,precision,recall,score,signals,System.currentTimeMillis());
    }

    private Profile defaults(){
        LinkedHashMap<String,Double>w=new LinkedHashMap<>();
        w.put("r5",.55);w.put("r20",1.0);w.put("r60",.65);w.put("volume",.9);w.put("breakout",1.1);
        w.put("rsi",.55);w.put("volatility",-.45);w.put("relative",.85);w.put("weekly",.75);w.put("acceleration",.6);w.put("sector_relative",.55);
        return new Profile("LAB_BASE",w,.72,0,0,0,0,0);
    }

    private JSONObject toJson(Profile x)throws Exception{
        JSONObject w=new JSONObject();for(Map.Entry<String,Double>e:x.w.entrySet())w.put(e.getKey(),e.getValue());
        return new JSONObject().put("id",x.id).put("w",w).put("threshold",x.threshold).put("precision",x.holdoutPrecision)
                .put("recall",x.holdoutRecall).put("score",x.score).put("signals",x.holdoutSignals).put("promoted",x.promotedAt);
    }

    private Profile fromJson(JSONObject o){
        Profile d=defaults();LinkedHashMap<String,Double>w=new LinkedHashMap<>(d.w);JSONObject j=o.optJSONObject("w");
        if(j!=null)for(String k:KEYS)if(j.has(k))w.put(k,clamp(j.optDouble(k,w.get(k)),-2.5,2.8));
        return new Profile(o.optString("id","LAB_BASE"),w,clamp(o.optDouble("threshold",.72),.55,.90),
                o.optDouble("precision",0),o.optDouble("recall",0),o.optDouble("score",0),o.optInt("signals",0),o.optLong("promoted",0));
    }
    private static double clamp(double x,double a,double b){return Math.max(a,Math.min(b,x));}
}
