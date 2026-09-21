package com.ps.shadowtrader;

import android.content.*;
import java.util.*;

public final class SectorContextStore {
    private final android.content.SharedPreferences p;
    public SectorContextStore(Context c){p=c.getSharedPreferences("lab30_sector",Context.MODE_PRIVATE);}
    public synchronized double mean(String sector){
        if(sector==null||sector.isEmpty()||"UNKNOWN".equalsIgnoreCase(sector))return 0;
        return p.getFloat("m_"+key(sector),0);
    }
    public synchronized void observe(String sector,double r20){
        if(sector==null||sector.isEmpty()||"UNKNOWN".equalsIgnoreCase(sector))return;
        String k=key(sector);float old=p.getFloat("m_"+k,0);int n=p.getInt("n_"+k,0);
        double a=n<20?1.0/(n+1):.08;double m=old*(1-a)+r20*a;
        p.edit().putFloat("m_"+k,(float)m).putInt("n_"+k,Math.min(1000,n+1)).apply();
    }
    private String key(String s){return Integer.toHexString(s.toUpperCase(Locale.ROOT).hashCode());}
}
