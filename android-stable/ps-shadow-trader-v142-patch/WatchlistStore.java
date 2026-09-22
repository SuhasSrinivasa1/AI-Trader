package com.ps.shadowtrader;

import android.content.*;
import org.json.*;
import java.util.*;

public final class WatchlistStore {
    private static final int MAX=3;
    private static final long STALE_MS=10L*60L*60L*1000L;
    private static final Set<String> INVALID=new HashSet<>(Arrays.asList(
            "RELEASED","RELEASE","TRADE","TRADES","RELEASING","SOON","NEW","UPDATE","BOOK","PROFIT","INTRADAY","EQUITY","BUY","SELL","CALL"
    ));
    private final android.content.SharedPreferences p;
    public WatchlistStore(Context c){p=c.getSharedPreferences("watchlist",Context.MODE_PRIVATE);}

    public synchronized void add(String symbol,String raw){
        if(symbol==null||symbol.trim().isEmpty())return;
        symbol=symbol.trim().toUpperCase(Locale.ROOT);
        long now=System.currentTimeMillis();
        try{
            JSONArray old=new JSONArray(p.getString("items","[]"));
            JSONArray out=new JSONArray();
            out.put(new JSONObject().put("symbol",symbol).put("ts",now).put("firstTs",firstTs(old,symbol,now)).put("raw",raw==null?"":raw));
            for(int i=0;i<old.length()&&out.length()<MAX;i++){
                JSONObject o=old.getJSONObject(i);String s=o.optString("symbol","");long ts=o.optLong("ts",0);
                if(!s.equals(symbol)&&now-ts<STALE_MS)out.put(o);
            }
            p.edit().putString("items",out.toString()).apply();
        }catch(Exception ignored){}
    }

    public synchronized void touch(String symbol,String raw){
        if(symbol==null)return;symbol=symbol.toUpperCase(Locale.ROOT);
        try{
            JSONArray a=new JSONArray(p.getString("items","[]"));JSONArray out=new JSONArray();boolean found=false;long now=System.currentTimeMillis();
            for(int i=0;i<a.length();i++){
                JSONObject o=a.getJSONObject(i);
                if(symbol.equals(o.optString("symbol"))){o.put("ts",now).put("lastUpdate",now).put("raw",raw==null?"":raw);found=true;}
                out.put(o);
            }
            if(found)p.edit().putString("items",out.toString()).apply();
        }catch(Exception ignored){}
    }

    public synchronized void remove(String symbol){
        if(symbol==null)return;symbol=symbol.toUpperCase(Locale.ROOT);
        try{
            JSONArray a=new JSONArray(p.getString("items","[]"));JSONArray out=new JSONArray();
            for(int i=0;i<a.length();i++){JSONObject o=a.getJSONObject(i);if(!symbol.equals(o.optString("symbol")))out.put(o);}
            p.edit().putString("items",out.toString()).apply();
        }catch(Exception ignored){}
    }

    public synchronized boolean contains(String symbol){return knownSymbols().contains(symbol==null?"":symbol.toUpperCase(Locale.ROOT));}

    public synchronized Set<String> knownSymbols(){return new LinkedHashSet<>(symbols());}

    public synchronized List<String> symbols(){
        ArrayList<String> out=new ArrayList<>();long now=System.currentTimeMillis();
        try{
            JSONArray a=new JSONArray(p.getString("items","[]"));JSONArray keep=new JSONArray();
            for(int i=0;i<a.length();i++){
                JSONObject o=a.getJSONObject(i);String s=o.optString("symbol","");long ts=o.optLong("ts",0);
                if(!s.isEmpty()&&!INVALID.contains(s)&&now-ts<STALE_MS&&out.size()<MAX){out.add(s);keep.put(o);}
            }
            p.edit().putString("items",keep.toString()).apply();
        }catch(Exception ignored){}
        return out;
    }

    public String display(){List<String>s=symbols();return s.isEmpty()?"None":android.text.TextUtils.join(" • ",s);}

    private long firstTs(JSONArray a,String symbol,long fallback){
        try{for(int i=0;i<a.length();i++){JSONObject o=a.getJSONObject(i);if(symbol.equals(o.optString("symbol")))return o.optLong("firstTs",o.optLong("ts",fallback));}}catch(Exception ignored){}
        return fallback;
    }
}
