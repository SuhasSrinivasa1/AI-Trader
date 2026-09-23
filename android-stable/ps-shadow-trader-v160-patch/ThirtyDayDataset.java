package com.ps.shadowtrader;

import android.content.*;
import org.json.*;
import java.util.*;

public final class ThirtyDayDataset {
    private static final int MAX=1800;
    private static final long HORIZON_SEC=30L*86400L;
    private final android.content.SharedPreferences p;
    public ThirtyDayDataset(Context c){p=c.getSharedPreferences("lab30_dataset",Context.MODE_PRIVATE);}

    public static final class Example {
        public String symbol; public long ts; public boolean hit50,hit30; public double futurePeak,futureDrawdown; public final Map<String,Double>f=new LinkedHashMap<>();
    }

    public synchronized int size(){try{return new JSONArray(p.getString("examples","[]")).length();}catch(Exception e){return 0;}}

    public synchronized void addFromHistory(String symbol,List<Models.Candle>d,double[] nifty20,String sector,double sectorMean){
        if(d==null||d.size()<130)return;
        ArrayList<JSONObject> positives=new ArrayList<>(),negatives=new ArrayList<>();
        int n=d.size();
        for(int i=70;i<n-1;i+=3){
            long horizon=d.get(i).ts+HORIZON_SEC;
            if(d.get(n-1).ts<horizon)break;
            Map<String,Double>f=LongHorizonFeatures.at(d,i,nifty20==null?0:(i<nifty20.length?nifty20[i]:0),sectorMean);
            double base=d.get(i).c;if(base<=0)continue;
            double peak=0,dd=0,low=base;
            for(int j=i+1;j<n&&d.get(j).ts<=horizon;j++){
                peak=Math.max(peak,d.get(j).h/base-1);
                low=Math.min(low,d.get(j).l);
                dd=Math.max(dd,1-low/base);
            }
            try{
                JSONObject o=new JSONObject().put("id",symbol+"@"+d.get(i).ts).put("symbol",symbol).put("ts",d.get(i).ts)
                        .put("hit50",peak>=.50).put("hit30",peak>=.30).put("peak",peak).put("dd",dd).put("horizon","30_calendar_days");
                JSONObject fj=new JSONObject();for(Map.Entry<String,Double>e:f.entrySet())fj.put(e.getKey(),e.getValue());o.put("f",fj);
                if(peak>=.50)positives.add(o);else negatives.add(o);
            }catch(Exception ignored){}
        }
        Collections.sort(positives,(a,b)->Long.compare(b.optLong("ts"),a.optLong("ts")));
        Collections.sort(negatives,(a,b)->Long.compare(b.optLong("ts"),a.optLong("ts")));
        ArrayList<JSONObject> selected=new ArrayList<>();
        for(int i=0;i<Math.min(6,positives.size());i++)selected.add(positives.get(i));
        for(int i=0;i<Math.min(6,negatives.size());i++)selected.add(negatives.get(i));
        append(selected);
    }


    public synchronized void addLiveOutcome(JSONObject prediction){
        if(prediction==null)return;
        try{
            JSONObject fj=prediction.optJSONObject("features");
            if(fj==null)return;
            String symbol=prediction.optString("symbol","");
            long created=prediction.optLong("created",0);
            if(symbol.isEmpty()||created<=0)return;

            JSONObject o=new JSONObject()
                    .put("id","LIVE:"+symbol+"@"+created)
                    .put("symbol",symbol)
                    .put("ts",created/1000L)
                    .put("hit50",prediction.optBoolean("success",false))
                    .put("hit30",prediction.optBoolean("hit30",false))
                    .put("peak",prediction.optDouble("maxGain",0))
                    .put("dd",prediction.optDouble("maxDrawdown",0))
                    .put("f",new JSONObject(fj.toString()))
                    .put("source","live_prediction");
            append(java.util.Collections.singletonList(o));
        }catch(Exception ignored){}
    }

    private synchronized void append(List<JSONObject> add){
        try{
            JSONArray old=new JSONArray(p.getString("examples","[]"));
            LinkedHashMap<String,JSONObject> uniq=new LinkedHashMap<>();
            for(int i=0;i<old.length();i++){JSONObject o=old.getJSONObject(i);uniq.put(o.optString("id",o.optString("symbol")+"@"+o.optLong("ts")),o);}
            for(JSONObject o:add)uniq.put(o.optString("id",o.optString("symbol")+"@"+o.optLong("ts")),o);
            ArrayList<JSONObject> all=new ArrayList<>(uniq.values());
            Collections.sort(all,(a,b)->Long.compare(a.optLong("ts"),b.optLong("ts")));
            if(all.size()>MAX)all=new ArrayList<>(all.subList(all.size()-MAX,all.size()));
            JSONArray out=new JSONArray();for(JSONObject o:all)out.put(o);
            p.edit().putString("examples",out.toString()).apply();
        }catch(Exception ignored){}
    }

    public synchronized List<Example> all(){
        ArrayList<Example> out=new ArrayList<>();
        try{
            JSONArray a=new JSONArray(p.getString("examples","[]"));
            for(int i=0;i<a.length();i++){
                JSONObject o=a.getJSONObject(i);Example e=new Example();e.symbol=o.optString("symbol");e.ts=o.optLong("ts");e.hit50=o.optBoolean("hit50");e.hit30=o.optBoolean("hit30");e.futurePeak=o.optDouble("peak");e.futureDrawdown=o.optDouble("dd");
                JSONObject f=o.optJSONObject("f");if(f!=null)for(String k:LongHorizonChampionStore.KEYS)e.f.put(k,f.optDouble(k,0));out.add(e);
            }
        }catch(Exception ignored){}
        return out;
    }
}
