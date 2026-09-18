package com.ps.shadowtrader;

import android.content.*;
import static com.ps.shadowtrader.Models.*;

public final class TradeStateStore {
    private final android.content.SharedPreferences p;
    public TradeStateStore(Context c){p=c.getSharedPreferences("trade_state",Context.MODE_PRIVATE);}
    public TradeState load(){
        TradeState s=new TradeState();
        try{s.side=Side.valueOf(p.getString("side","FLAT"));}catch(Exception e){s.side=Side.FLAT;}
        s.symbol=p.getString("symbol",""); s.entry=d("entry"); s.qty=p.getInt("qty",0); s.realized=d("realized");
        s.last=d("last"); s.estimatedCosts=d("costs"); s.openedAtMs=p.getLong("opened",0); s.lastSwitchAtMs=p.getLong("switch",0);
        try{s.pendingSide=Side.valueOf(p.getString("pending","FLAT"));}catch(Exception e){s.pendingSide=Side.FLAT;}
        s.pendingCount=p.getInt("pending_count",0); s.reversalsToday=p.getInt("reversals",0); s.dayOfYear=p.getInt("doy",-1);
        return s;
    }
    public void save(TradeState s){
        p.edit().putString("side",s.side.name()).putString("symbol",s.symbol).putString("entry",Double.toString(s.entry))
                .putInt("qty",s.qty).putString("realized",Double.toString(s.realized)).putString("last",Double.toString(s.last))
                .putString("costs",Double.toString(s.estimatedCosts)).putLong("opened",s.openedAtMs).putLong("switch",s.lastSwitchAtMs)
                .putString("pending",s.pendingSide.name()).putInt("pending_count",s.pendingCount).putInt("reversals",s.reversalsToday)
                .putInt("doy",s.dayOfYear).apply();
    }
    private double d(String k){try{return Double.parseDouble(p.getString(k,"0"));}catch(Exception e){return 0;}}
}
