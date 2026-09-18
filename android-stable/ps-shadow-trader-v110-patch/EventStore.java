package com.ps.shadowtrader;

import android.content.*;
import org.json.*;
import java.text.*;
import java.util.*;

public final class EventStore {
    private final android.content.SharedPreferences p;
    public EventStore(Context c){p=c.getSharedPreferences("state",Context.MODE_PRIVATE);}
    public synchronized void add(String type,String text){
        try{
            JSONArray a=new JSONArray(p.getString("events","[]"));
            JSONObject o=new JSONObject().put("ts",System.currentTimeMillis()).put("type",type).put("text",text);
            JSONArray b=new JSONArray(); b.put(o); for(int i=0;i<a.length()&&i<39;i++) b.put(a.getJSONObject(i));
            p.edit().putString("events",b.toString()).putString("last_action",text).apply();
        }catch(Exception ignored){}
    }
    public String recentText(int max){
        try{
            JSONArray a=new JSONArray(p.getString("events","[]")); StringBuilder s=new StringBuilder();
            SimpleDateFormat f=new SimpleDateFormat("HH:mm",Locale.getDefault());
            for(int i=0;i<a.length()&&i<max;i++){JSONObject o=a.getJSONObject(i);s.append(f.format(new Date(o.optLong("ts")))).append("  ").append(o.optString("text")).append("\n");}
            return s.length()==0?"Automation events will appear here.":s.toString().trim();
        }catch(Exception e){return "Automation events will appear here.";}
    }
}
