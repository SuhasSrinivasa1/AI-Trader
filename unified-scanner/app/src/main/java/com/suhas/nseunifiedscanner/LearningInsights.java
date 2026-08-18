package com.suhas.nseunifiedscanner;

import android.content.ContentValues;
import android.content.Context;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;

import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;

/**
 * Fast-learning companion store.
 *
 * Primary recommendations keep their original meaning and headline hit-rate.
 * Additional ranked-but-not-displayed candidates are tracked as lower-weight
 * "shadow" observations so the model can learn faster without pretending they
 * were live recommendations or trades.
 */
final class LearningInsights {
    private static final String DB="nse_scanner_learning.db";
    private final Context context;

    LearningInsights(Context c){
        context=c.getApplicationContext();
        try(SQLiteDatabase db=open()){
            db.execSQL("CREATE TABLE IF NOT EXISTS shadow_samples(id INTEGER PRIMARY KEY AUTOINCREMENT, scan_ms INTEGER NOT NULL, symbol TEXT NOT NULL, groww_symbol TEXT NOT NULL, entry REAL NOT NULL, target REAL NOT NULL, stop REAL NOT NULL, score REAL NOT NULL, probability REAL NOT NULL, features TEXT NOT NULL, deadline_ms INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'PENDING', resolved_ms INTEGER NOT NULL DEFAULT 0)");
            db.execSQL("CREATE INDEX IF NOT EXISTS idx_shadow_status ON shadow_samples(status,deadline_ms)");
            db.execSQL("CREATE INDEX IF NOT EXISTS idx_shadow_symbol ON shadow_samples(symbol,scan_ms)");
        }catch(Exception ignore){}
    }

    private SQLiteDatabase open(){return context.openOrCreateDatabase(DB,Context.MODE_PRIVATE,null);}

    synchronized long recordShadowIfNew(ScannerEngine.Recommendation r){
        try(SQLiteDatabase db=open()){
            try(Cursor c=db.rawQuery("SELECT scan_ms,entry FROM shadow_samples WHERE symbol=? ORDER BY id DESC LIMIT 1",new String[]{r.symbol})){
                if(c.moveToFirst()){
                    long last=c.getLong(0);double old=c.getDouble(1);
                    if(System.currentTimeMillis()-last<10*60_000L && Math.abs(r.entry-old)/Math.max(0.01,old)<0.003)return -1;
                }
            }
            ContentValues v=new ContentValues();v.put("scan_ms",r.scanMs);v.put("symbol",r.symbol);v.put("groww_symbol",r.growwSymbol);v.put("entry",r.entry);v.put("target",r.target);v.put("stop",r.stop);v.put("score",r.score);v.put("probability",r.probability);v.put("features",r.features.toString());v.put("deadline_ms",r.deadlineMs);v.put("status","PENDING");
            return db.insert("shadow_samples",null,v);
        }catch(Exception e){return -1;}
    }

    synchronized List<ShadowRec> openShadow(){
        List<ShadowRec> out=new ArrayList<>();
        try(SQLiteDatabase db=open();Cursor c=db.rawQuery("SELECT id,scan_ms,symbol,groww_symbol,entry,target,stop,deadline_ms,features FROM shadow_samples WHERE status='PENDING' ORDER BY scan_ms",null)){
            while(c.moveToNext()){ShadowRec r=new ShadowRec();r.id=c.getLong(0);r.scanMs=c.getLong(1);r.symbol=c.getString(2);r.growwSymbol=c.getString(3);r.entry=c.getDouble(4);r.target=c.getDouble(5);r.stop=c.getDouble(6);r.deadlineMs=c.getLong(7);r.features=c.getString(8);out.add(r);}
        }catch(Exception ignore){}
        return out;
    }

    synchronized void resolveShadow(long id,String outcome,long resolvedMs,String features){
        if(!("SUCCESS".equals(outcome)||"FAIL".equals(outcome)||"TIMEOUT".equals(outcome)||"AMBIGUOUS".equals(outcome)))return;
        try(SQLiteDatabase db=open()){
            ContentValues v=new ContentValues();v.put("status",outcome);v.put("resolved_ms",resolvedMs);
            int n=db.update("shadow_samples",v,"id=? AND status='PENDING'",new String[]{String.valueOf(id)});
            if(n==1 && !"AMBIGUOUS".equals(outcome)) AdaptiveModel.update(context,features,"SUCCESS".equals(outcome)?1.0:0.0,0.25);
        }catch(Exception ignore){}
    }

    synchronized TodaySummary todaySummary(){
        TodaySummary s=new TodaySummary();long[] b=todayBounds();
        try(SQLiteDatabase db=open();Cursor c=db.rawQuery("SELECT status,COUNT(*) FROM recommendations WHERE resolved_ms>=? AND resolved_ms<? AND status IN ('SUCCESS','FAIL','TIMEOUT') GROUP BY status",new String[]{String.valueOf(b[0]),String.valueOf(b[1])})){
            while(c.moveToNext()){String st=c.getString(0);int n=c.getInt(1);s.resolved+=n;if("SUCCESS".equals(st))s.hits+=n;else if("FAIL".equals(st))s.stops+=n;else if("TIMEOUT".equals(st))s.timeouts+=n;}
        }catch(Exception ignore){}
        return s;
    }

    synchronized List<HistoryRow> todayHits(int limit){
        List<HistoryRow> out=new ArrayList<>();long[] b=todayBounds();
        try(SQLiteDatabase db=open();Cursor c=db.rawQuery("SELECT symbol,entry,target,stop,score,probability,scan_ms,resolved_ms,bought FROM recommendations WHERE resolved_ms>=? AND resolved_ms<? AND status='SUCCESS' ORDER BY resolved_ms DESC LIMIT "+Math.max(1,Math.min(20,limit)),new String[]{String.valueOf(b[0]),String.valueOf(b[1])})){
            while(c.moveToNext()){HistoryRow r=new HistoryRow();r.symbol=c.getString(0);r.entry=c.getDouble(1);r.target=c.getDouble(2);r.stop=c.getDouble(3);r.score=c.getDouble(4);r.probability=c.getDouble(5);r.scanMs=c.getLong(6);r.resolvedMs=c.getLong(7);r.bought=c.getInt(8)==1;out.add(r);}
        }catch(Exception ignore){}
        return out;
    }

    synchronized ShadowStats shadowStats(){
        ShadowStats s=new ShadowStats();long[] b=todayBounds();
        try(SQLiteDatabase db=open();Cursor c=db.rawQuery("SELECT status,COUNT(*) FROM shadow_samples WHERE resolved_ms>=? AND resolved_ms<? AND status IN ('SUCCESS','FAIL','TIMEOUT') GROUP BY status",new String[]{String.valueOf(b[0]),String.valueOf(b[1])})){
            while(c.moveToNext()){String st=c.getString(0);int n=c.getInt(1);s.resolvedToday+=n;if("SUCCESS".equals(st))s.hitsToday+=n;}
        }catch(Exception ignore){}
        try(SQLiteDatabase db=open();Cursor c=db.rawQuery("SELECT COUNT(*) FROM shadow_samples WHERE status='PENDING'",null)){if(c.moveToFirst())s.pending=c.getInt(0);}catch(Exception ignore){}
        return s;
    }

    private long[] todayBounds(){LocalDate d=LocalDate.now(ScannerEngine.IST);long a=d.atStartOfDay(ScannerEngine.IST).toInstant().toEpochMilli();long z=d.plusDays(1).atStartOfDay(ScannerEngine.IST).toInstant().toEpochMilli();return new long[]{a,z};}

    static final class ShadowRec{long id,scanMs,deadlineMs;String symbol,growwSymbol,features;double entry,target,stop;}
    static final class HistoryRow{String symbol;double entry,target,stop,score,probability;long scanMs,resolvedMs;boolean bought;}
    static final class TodaySummary{int resolved,hits,stops,timeouts;}
    static final class ShadowStats{int resolvedToday,hitsToday,pending;}
}
