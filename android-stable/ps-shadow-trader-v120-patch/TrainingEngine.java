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
            if(a.length()==0 || a.getJSONObject(a.length()-1).optLong("day")!=day)
                a.put(new JSONObject().put("day",day).put("pnl",netPnl));
            while(a.length()>60){JSONArray b=new JSONArray();for(int i=1;i<a.length();i++)b.put(a.get(i));a=b;}
            p.edit().putString("daily",a.toString()).apply();
        }catch(Exception ignored){}

        int n=a.length();double avg=0;int wins=0;int start=Math.max(0,n-20),count=0;
        for(int i=start;i<n;i++){
            try{double x=a.getJSONObject(i).optDouble("pnl",0);avg+=x;if(x>0)wins++;count++;}catch(Exception ignored){}
        }
        avg/=Math.max(1,count);
        String summary=String.format(Locale.US,
                "EOD replay window %d sessions • profitable days %s • average shadow net ₹%.0f. Strategy weights are updated from individual closed trades; no fixed hold/cooldown/reversal parameters are tuned.",
                count,count==0?"—":String.format(Locale.US,"%.0f%%",(double)wins/count*100),avg);
        p.edit().putString("summary",summary).putLong("last_training",System.currentTimeMillis()).apply();
        return summary;
    }
}
