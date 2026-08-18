package com.suhas.nseunifiedscanner;

import android.content.ContentValues;
import android.content.Context;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;
import android.database.sqlite.SQLiteOpenHelper;
import android.content.SharedPreferences;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.List;

final class LearningStore extends SQLiteOpenHelper {
    private static final String DB="nse_scanner_learning.db";
    private static final int VERSION=1;
    private final Context context;

    LearningStore(Context c) { super(c,DB,null,VERSION); context=c.getApplicationContext(); }

    @Override public void onCreate(SQLiteDatabase db) {
        db.execSQL("CREATE TABLE recommendations(id INTEGER PRIMARY KEY AUTOINCREMENT, scan_ms INTEGER NOT NULL, symbol TEXT NOT NULL, groww_symbol TEXT NOT NULL, entry REAL NOT NULL, target REAL NOT NULL, stop REAL NOT NULL, score REAL NOT NULL, probability REAL NOT NULL, features TEXT NOT NULL, deadline_ms INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'PENDING', bought INTEGER NOT NULL DEFAULT 0, resolved_ms INTEGER NOT NULL DEFAULT 0)");
        db.execSQL("CREATE INDEX idx_rec_status ON recommendations(status,deadline_ms)");
        db.execSQL("CREATE INDEX idx_rec_symbol ON recommendations(symbol,status)");
        db.execSQL("CREATE TABLE audit(id INTEGER PRIMARY KEY AUTOINCREMENT, ts_ms INTEGER NOT NULL, level TEXT NOT NULL, message TEXT NOT NULL)");
    }
    @Override public void onUpgrade(SQLiteDatabase db,int oldV,int newV) { }

    synchronized long recordIfNew(ScannerEngine.Recommendation r) {
        SQLiteDatabase db=getWritableDatabase();
        try(Cursor c=db.rawQuery("SELECT id,entry,deadline_ms FROM recommendations WHERE symbol=? AND status='PENDING' ORDER BY id DESC LIMIT 1",new String[]{r.symbol})) {
            if(c.moveToFirst()) {
                double old=c.getDouble(1); long deadline=c.getLong(2);
                if(System.currentTimeMillis()<deadline && Math.abs(r.entry-old)/Math.max(0.01,old)<0.002) return c.getLong(0);
            }
        }
        ContentValues v=new ContentValues(); v.put("scan_ms",r.scanMs); v.put("symbol",r.symbol); v.put("groww_symbol",r.growwSymbol);
        v.put("entry",r.entry); v.put("target",r.target); v.put("stop",r.stop); v.put("score",r.score); v.put("probability",r.probability);
        v.put("features",r.features.toString()); v.put("deadline_ms",r.deadlineMs); v.put("status","PENDING");
        return db.insertOrThrow("recommendations",null,v);
    }

    synchronized List<OpenRec> openRecommendations() {
        List<OpenRec> out=new ArrayList<>();
        try(Cursor c=getReadableDatabase().rawQuery("SELECT id,scan_ms,symbol,groww_symbol,entry,target,stop,deadline_ms,features FROM recommendations WHERE status='PENDING' ORDER BY scan_ms",null)) {
            while(c.moveToNext()) { OpenRec r=new OpenRec(); r.id=c.getLong(0); r.scanMs=c.getLong(1); r.symbol=c.getString(2); r.growwSymbol=c.getString(3); r.entry=c.getDouble(4); r.target=c.getDouble(5); r.stop=c.getDouble(6); r.deadlineMs=c.getLong(7); r.features=c.getString(8); out.add(r); }
        }
        return out;
    }

    synchronized void resolve(long id,String outcome,long resolvedMs,String features) {
        ContentValues v=new ContentValues(); v.put("status",outcome); v.put("resolved_ms",resolvedMs);
        int n=getWritableDatabase().update("recommendations",v,"id=? AND status='PENDING'",new String[]{String.valueOf(id)});
        if(n==1 && ("SUCCESS".equals(outcome)||"FAIL".equals(outcome)||"TIMEOUT".equals(outcome))) {
            AdaptiveModel.update(context,features,"SUCCESS".equals(outcome)?1.0:0.0);
            retuneThreshold();
        }
    }

    synchronized void markBought(String symbol) {
        ContentValues v=new ContentValues(); v.put("bought",1);
        getWritableDatabase().update("recommendations",v,"id=(SELECT id FROM recommendations WHERE symbol=? ORDER BY id DESC LIMIT 1)",new String[]{symbol});
    }

    synchronized Stats stats() {
        Stats s=new Stats();
        try(Cursor c=getReadableDatabase().rawQuery("SELECT status,COUNT(*) FROM (SELECT status FROM recommendations WHERE status IN ('SUCCESS','FAIL','TIMEOUT') ORDER BY resolved_ms DESC LIMIT 100) GROUP BY status",null)) {
            while(c.moveToNext()){String st=c.getString(0);int n=c.getInt(1);s.n+=n;if("SUCCESS".equals(st))s.wins+=n;}
        }
        s.rate=s.n==0?Double.NaN:(100.0*s.wins/s.n);
        try(Cursor c=getReadableDatabase().rawQuery("SELECT COUNT(*),SUM(CASE WHEN status='SUCCESS' THEN 1 ELSE 0 END) FROM recommendations WHERE bought=1 AND status IN ('SUCCESS','FAIL','TIMEOUT')",null)) {
            if(c.moveToFirst()){s.executedN=c.getInt(0);s.executedWins=c.isNull(1)?0:c.getInt(1);}
        }
        return s;
    }

    synchronized void audit(String level,String message) {
        ContentValues v=new ContentValues();v.put("ts_ms",System.currentTimeMillis());v.put("level",level);v.put("message",message==null?"":message);
        getWritableDatabase().insert("audit",null,v);
        getWritableDatabase().execSQL("DELETE FROM audit WHERE id NOT IN (SELECT id FROM audit ORDER BY id DESC LIMIT 500)");
    }

    synchronized String recentAudit() {
        StringBuilder b=new StringBuilder();
        try(Cursor c=getReadableDatabase().rawQuery("SELECT ts_ms,level,message FROM audit ORDER BY id DESC LIMIT 12",null)) {
            while(c.moveToNext()) b.append(c.getString(1)).append(" • ").append(c.getString(2)).append('\n');
        }
        return b.toString();
    }

    private void retuneThreshold() {
        Stats s=stats(); if(s.n<30)return;
        SharedPreferences p=context.getSharedPreferences("scanner_prefs",Context.MODE_PRIVATE);
        int minScore=p.getInt("min_score",82);
        if(s.rate<80.0) minScore=Math.min(92,minScore+2);
        else if(s.rate>=86.0 && s.n>=50) minScore=Math.max(80,minScore-1);
        p.edit().putInt("min_score",minScore).apply();
    }

    static final class OpenRec { long id,scanMs,deadlineMs; String symbol,growwSymbol,features; double entry,target,stop; }
    static final class Stats { int n,wins,executedN,executedWins; double rate; }
}

final class AdaptiveModel {
    static final String[] NAMES={"vwap","rsi","relvol","macd","momentum","breakout","liquidity","market","depth","range","time"};
    private static final double[] DEFAULT={0.92,0.55,0.78,0.72,0.62,0.58,0.68,0.55,0.35,0.35,0.45};
    private static final double DEFAULT_BIAS=-2.55;
    private AdaptiveModel() { }

    static double predict(Context c, JSONObject f) {
        SharedPreferences p=c.getSharedPreferences("model_weights",Context.MODE_PRIVATE);
        double z=Double.longBitsToDouble(p.getLong("bias",Double.doubleToLongBits(DEFAULT_BIAS)));
        for(int i=0;i<NAMES.length;i++) {
            double w=Double.longBitsToDouble(p.getLong("w"+i,Double.doubleToLongBits(DEFAULT[i])));
            z+=w*clamp(f.optDouble(NAMES[i],0.5),0,1);
        }
        double prob=1.0/(1.0+Math.exp(-z));
        return clamp(prob,0.05,0.98);
    }

    static void update(Context c,String featuresJson,double y) {
        try {
            JSONObject f=new JSONObject(featuresJson); SharedPreferences p=c.getSharedPreferences("model_weights",Context.MODE_PRIVATE);
            double bias=Double.longBitsToDouble(p.getLong("bias",Double.doubleToLongBits(DEFAULT_BIAS)));
            double[] w=new double[NAMES.length]; for(int i=0;i<w.length;i++)w[i]=Double.longBitsToDouble(p.getLong("w"+i,Double.doubleToLongBits(DEFAULT[i])));
            double z=bias; for(int i=0;i<w.length;i++)z+=w[i]*clamp(f.optDouble(NAMES[i],0.5),0,1);
            double pred=1.0/(1.0+Math.exp(-z)); double err=y-pred; double lr=0.015;
            bias=clamp(bias+lr*err,-4.5,-0.5); SharedPreferences.Editor e=p.edit().putLong("bias",Double.doubleToLongBits(bias));
            for(int i=0;i<w.length;i++){double x=clamp(f.optDouble(NAMES[i],0.5),0,1);w[i]=clamp(w[i]+lr*(err*x-0.003*w[i]),-1.2,2.2);e.putLong("w"+i,Double.doubleToLongBits(w[i]));}
            e.apply();
        } catch(Exception ignore) { }
    }
    static double clamp(double x,double a,double b){return Math.max(a,Math.min(b,x));}
}
