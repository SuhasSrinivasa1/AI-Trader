package com.ps.shadowtrader;

import android.content.*;

public final class ModelConfig {
    private final android.content.SharedPreferences p;
    public ModelConfig(Context c){p=c.getSharedPreferences("model_config",Context.MODE_PRIVATE);}
    public double entryThreshold(){return clamp(p.getFloat("entry_threshold",1.20f),1.10,1.65);}
    public double reversalThreshold(){return clamp(p.getFloat("reversal_threshold",2.20f),2.00,2.90);}
    public int trainingSessions(){return p.getInt("training_sessions",0);}
    public String trainingSummary(){return p.getString("training_summary","Learning has not run yet. Stability guard is active.");}
    public long lastTraining(){return p.getLong("last_training",0);}
    public void save(double entry,double reversal,int sessions,String summary){
        p.edit().putFloat("entry_threshold",(float)clamp(entry,1.10,1.65))
                .putFloat("reversal_threshold",(float)clamp(reversal,2.00,2.90))
                .putInt("training_sessions",sessions).putString("training_summary",summary)
                .putLong("last_training",System.currentTimeMillis()).apply();
    }
    private static double clamp(double x,double a,double b){return Math.max(a,Math.min(b,x));}
}
