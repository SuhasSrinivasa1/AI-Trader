package com.ps.shadowtrader;

import android.content.*;
import org.json.*;
import java.util.*;

public final class AdaptiveModel {
    private static final String[] KEYS={"ema","rsi","vwap","macd","volume","candle","breakout","persistence","relative","micro","accel","reversion"};
    private final android.content.SharedPreferences p;
    private final Context context;

    public AdaptiveModel(Context c){
        context=c.getApplicationContext();
        p=context.getSharedPreferences("adaptive_model",Context.MODE_PRIVATE);
        if(!p.contains("weights"))saveWeights(defaults());
    }

    private Map<String,Double> defaults(){
        LinkedHashMap<String,Double>w=new LinkedHashMap<>();
        w.put("ema",1.0);w.put("rsi",0.55);w.put("vwap",0.7);w.put("macd",0.55);w.put("volume",0.75);
        w.put("candle",0.7);w.put("breakout",0.9);w.put("persistence",0.65);w.put("relative",0.7);
        w.put("micro",1.05);w.put("accel",0.75);w.put("reversion",0.45);
        return w;
    }

    private synchronized Map<String,Double> onlineWeights(){
        Map<String,Double>w=defaults();
        try{
            JSONObject o=new JSONObject(p.getString("weights","{}"));
            for(String k:KEYS)if(o.has(k))w.put(k,clamp(o.optDouble(k,w.get(k)),0.15,2.5));
        }catch(Exception ignored){}
        return w;
    }

    public synchronized Map<String,Double> weights(){
        return new ChampionStore(context).blend(onlineWeights());
    }

    private synchronized void saveWeights(Map<String,Double>w){
        try{
            JSONObject o=new JSONObject();for(Map.Entry<String,Double>e:w.entrySet())o.put(e.getKey(),e.getValue());
            p.edit().putString("weights",o.toString()).apply();
        }catch(Exception ignored){}
    }

    public synchronized void rememberEntry(String symbol,String side,double price,Map<String,Double>features,double confidence,double edgePct){
        try{
            JSONObject o=new JSONObject().put("symbol",symbol).put("side",side).put("price",price).put("ts",System.currentTimeMillis()).put("confidence",confidence).put("edge",edgePct);
            JSONObject f=new JSONObject();for(Map.Entry<String,Double>e:features.entrySet())f.put(e.getKey(),e.getValue());o.put("features",f);
            p.edit().putString("open_context",o.toString()).apply();
        }catch(Exception ignored){}
    }

    public synchronized void learnOnClose(String symbol,String side,double entry,double exit,double netPnlPct,String reason){
        JSONObject ctx=null;
        try{ctx=new JSONObject(p.getString("open_context","{}"));}catch(Exception ignored){}
        try{
            Map<String,Double>w=onlineWeights();
            JSONObject f=ctx==null?null:ctx.optJSONObject("features");
            double reward=clamp(netPnlPct*35.0,-1.0,1.0);
            double lr=0.025;
            if(f!=null){
                for(String k:KEYS){
                    double x=f.optDouble(k,0);
                    double nw=w.get(k)+lr*reward*Math.abs(x);
                    w.put(k,clamp(nw,0.15,2.5));
                }
                saveWeights(w);
            }

            JSONArray trades=new JSONArray(p.getString("trades","[]"));
            JSONObject t=new JSONObject().put("ts",System.currentTimeMillis()).put("symbol",symbol).put("side",side).put("entry",entry).put("exit",exit).put("net_pct",netPnlPct).put("reason",reason);
            if(ctx!=null)t.put("entry_context",ctx);
            trades.put(t);
            if(trades.length()>250){JSONArray b=new JSONArray();for(int i=trades.length()-250;i<trades.length();i++)b.put(trades.get(i));trades=b;}

            int total=p.getInt("trades_total",0)+1;
            int wins=p.getInt("wins",0)+(netPnlPct>0?1:0);
            double ema=p.getFloat("reward_ema",0);ema=ema*0.92+netPnlPct*0.08;
            double turnover=p.getFloat("turnover_penalty",1.0f);
            if(netPnlPct<0)turnover=Math.min(2.5,turnover+0.04);else turnover=Math.max(0.65,turnover-0.015);

            p.edit().putString("trades",trades.toString()).putInt("trades_total",total).putInt("wins",wins)
                    .putFloat("reward_ema",(float)ema).putFloat("turnover_penalty",(float)turnover).remove("open_context").apply();
        }catch(Exception ignored){}
    }

    public double turnoverPenalty(){
        return clamp(p.getFloat("turnover_penalty",1.0f)*new ChampionStore(context).costFactor(),0.55,3.0);
    }

    public double recentReward(){return p.getFloat("reward_ema",0);}
    public int trades(){return p.getInt("trades_total",0);}
    public int wins(){return p.getInt("wins",0);}
    public double hitRate(){int t=trades();return t==0?0:(double)wins()/t;}

    public double dynamicConfidenceFloor(double volatilityPct){
        double learned=trades()<8?0.68:0.60;
        if(hitRate()>0&&hitRate()<0.45)learned+=0.08;
        if(recentReward()<-.002)learned+=0.05;
        if(volatilityPct>.018)learned+=0.03;
        double champion=new ChampionStore(context).confidenceFloor();
        return clamp(champion*.72+learned*.28,0.50,0.86);
    }

    public String summary(){
        Map<String,Double>w=weights();ArrayList<Map.Entry<String,Double>>x=new ArrayList<>(w.entrySet());
        Collections.sort(x,(a,b)->Double.compare(b.getValue(),a.getValue()));
        StringBuilder s=new StringBuilder();
        s.append("Live-learned trades ").append(trades()).append(" • hit ");
        s.append(trades()==0?"—":String.format(Locale.US,"%.0f%%",hitRate()*100));
        s.append(" • adaptive turnover ").append(String.format(Locale.US,"%.2fx",turnoverPenalty()));
        s.append("\nEffective features: ");
        for(int i=0;i<Math.min(4,x.size());i++){if(i>0)s.append(" • ");s.append(x.get(i).getKey()).append(" ").append(String.format(Locale.US,"%.2f",x.get(i).getValue()));}
        s.append("\n").append(new ChampionStore(context).summary());
        return s.toString();
    }

    private static double clamp(double x,double a,double b){return Math.max(a,Math.min(b,x));}
}
