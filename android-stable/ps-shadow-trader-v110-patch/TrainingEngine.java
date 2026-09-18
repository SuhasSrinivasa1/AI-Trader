package com.ps.shadowtrader;

import android.content.*;
import org.json.*;
import java.util.*;

public final class TrainingEngine {
    public static String run(Context c,double netPnl){
        android.content.SharedPreferences p=c.getSharedPreferences("training",Context.MODE_PRIVATE);
        JSONArray a;
        try{a=new JSONArray(p.getString("daily","[]"));}catch(Exception e){a=new JSONArray();}
        long day=System.currentTimeMillis()/86400000L;
        try{
            if(a.length()==0 || a.getJSONObject(a.length()-1).optLong("day")!=day) a.put(new JSONObject().put("day",day).put("pnl",netPnl));
            while(a.length()>30){JSONArray b=new JSONArray();for(int i=1;i<a.length();i++)b.put(a.get(i));a=b;}
            p.edit().putString("daily",a.toString()).apply();
        }catch(Exception ignored){}
        ModelConfig cfg=new ModelConfig(c); int n=a.length(); double entry=cfg.entryThreshold(), rev=cfg.reversalThreshold();
        String summary;
        if(n<10){
            summary="Stability guard: "+n+"/10 sessions observed. No parameter changes yet; one or two bad days will not retrain the model.";
        } else {
            int wins=0; double avg=0; int start=Math.max(0,n-20); int count=0;
            for(int i=start;i<n;i++){try{double x=a.getJSONObject(i).optDouble("pnl",0);if(x>0)wins++;avg+=x;count++;}catch(Exception ignored){}}
            avg/=Math.max(1,count); double win=(double)wins/Math.max(1,count);
            double oldE=entry, oldR=rev;
            if(win<0.45 || avg<0){entry=Math.min(1.65,entry+0.05);rev=Math.min(2.90,rev+0.05);}
            else if(win>0.65 && avg>0){entry=Math.max(1.10,entry-0.03);rev=Math.max(2.05,rev-0.02);}
            summary=String.format(Locale.US,"20-session stability window • win %.0f%% • avg net ₹%.0f • entry %.2f→%.2f • reversal %.2f→%.2f. Daily drift is capped to avoid overfitting.",win*100,avg,oldE,entry,oldR,rev);
        }
        cfg.save(entry,rev,n,summary); new EventStore(c).add("TRAIN",summary); return summary;
    }
}
