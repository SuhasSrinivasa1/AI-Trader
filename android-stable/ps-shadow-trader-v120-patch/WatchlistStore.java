package com.ps.shadowtrader;

import android.content.*;
import org.json.*;
import java.util.*;

public final class WatchlistStore {
    private static final int MAX=3;
    private static final long STALE_MS=10L*60L*60L*1000L;
    private final android.content.SharedPreferences p;
    public WatchlistStore(Context c){p=c.getSharedPreferences("watchlist",Context.MODE_PRIVATE);}

    public synchronized void add(String symbol,String raw){
        if(symbol==null||symbol.trim().isEmpty())return;
        symbol=symbol.trim().toUpperCase(Locale.ROOT);
        long now=System.currentTimeMillis();
        try{
            JSONArray old=new JSONArray(p.getString("items","[]"));
            JSONArray out=new JSONArray();
            out.put(new JSONObject().put("symbol",symbol).put("ts",now).put("raw",raw==null?"":raw));
            for(int i=0;i<old.length()&&out.length()<MAX;i++){
                JSONObject o=old.getJSONObject(i);
                String s=o.optString("symbol","");
                long ts=o.optLong("ts",0);
                if(!s.equals(symbol)&&now-ts<STALE_MS)out.put(o);
            }
            p.edit().putString("items",out.toString()).apply();
        }catch(Exception ignored){}
    }

    public synchronized List<String> symbols(){
        ArrayList<String> out=new ArrayList<>();
        long now=System.currentTimeMillis();
        try{
            JSONArray a=new JSONArray(p.getString("items","[]"));
            JSONArray keep=new JSONArray();
            for(int i=0;i<a.length();i++){
                JSONObject o=a.getJSONObject(i);
                String s=o.optString("symbol","");
                long ts=o.optLong("ts",0);
                if(!s.isEmpty()&&now-ts<STALE_MS&&out.size()<MAX){out.add(s);keep.put(o);}
            }
            p.edit().putString("items",keep.toString()).apply();
        }catch(Exception ignored){}
        return out;
    }

    public String display(){
        List<String>s=symbols();return s.isEmpty()?"None":android.text.TextUtils.join(" • ",s);
    }
}
