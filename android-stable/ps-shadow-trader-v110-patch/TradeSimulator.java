package com.ps.shadowtrader;

import java.util.*;
import static com.ps.shadowtrader.Models.*;

public class TradeSimulator {
    public static final double BUDGET=100000.0;
    public static final long MIN_HOLD_MS=15L*60L*1000L;
    public static final long COOLDOWN_MS=10L*60L*1000L;
    public static final int OPPOSITE_CONFIRMATIONS=2;
    public static final int MAX_REVERSALS_PER_DAY=3;
    public static final double EMERGENCY_ADVERSE_PCT=.018;
    public static final double ESTIMATED_COST_RATE_PER_ORDER=.0012;

    public String apply(TradeState s,String symbol,Signal sig,double price,double reversalThreshold){
        long now=System.currentTimeMillis();s.last=price;resetDaily(s);
        if(s.side!=Side.FLAT && !s.symbol.equals(symbol)) return "HOLD "+s.symbol+" — one-stock-at-a-time guard; new "+symbol+" signal ignored";
        if(sig.side==Side.FLAT){s.pendingSide=Side.FLAT;s.pendingCount=0;return "HOLD/WAIT — no confirmed edge";}
        if(s.side==Side.FLAT){open(s,symbol,sig.side,price,now,false);return "SIMULATED "+sig.side+" @ "+fmt(price)+" × "+s.qty;}
        if(s.side==sig.side){s.pendingSide=Side.FLAT;s.pendingCount=0;return "HOLD "+s.side+" — thesis remains supported";}
        if(sig.score<reversalThreshold){s.pendingSide=Side.FLAT;s.pendingCount=0;return "HOLD "+s.side+" — opposite signal too weak after costs";}
        if(s.pendingSide==sig.side)s.pendingCount++;else{s.pendingSide=sig.side;s.pendingCount=1;}
        long held=now-s.openedAtMs,since=now-s.lastSwitchAtMs;double adverse=adversePct(s,price);boolean emergency=adverse>=EMERGENCY_ADVERSE_PCT&&sig.score>=1.8;
        if(s.reversalsToday>=MAX_REVERSALS_PER_DAY)return "HOLD "+s.side+" — daily reversal cap reached";
        if(!emergency&&held<MIN_HOLD_MS)return "HOLD "+s.side+" — minimum hold filter";
        if(!emergency&&since<COOLDOWN_MS)return "HOLD "+s.side+" — cooldown filter";
        if(!emergency&&s.pendingCount<OPPOSITE_CONFIRMATIONS)return "HOLD "+s.side+" — waiting opposite confirmation "+s.pendingCount+"/"+OPPOSITE_CONFIRMATIONS;
        close(s,price);s.reversalsToday++;open(s,symbol,sig.side,price,now,true);s.pendingSide=Side.FLAT;s.pendingCount=0;
        return "SIMULATED REVERSAL → "+sig.side+(emergency?" • hard invalidation":" • confirmed reversal");
    }
    public String forceExit(TradeState s,double price,String reason){if(s.side==Side.FLAT)return "Already flat";close(s,price);String old=s.side+" "+s.symbol;s.side=Side.FLAT;s.symbol="";s.entry=0;s.qty=0;s.pendingSide=Side.FLAT;s.pendingCount=0;return "SIMULATED EXIT "+old+" @ "+fmt(price)+" • "+reason;}
    private void open(TradeState s,String symbol,Side side,double price,long now,boolean reversal){s.qty=Math.max(1,(int)Math.floor(BUDGET/price));s.entry=price;s.side=side;s.symbol=symbol;s.openedAtMs=now;s.lastSwitchAtMs=now;s.estimatedCosts+=price*s.qty*ESTIMATED_COST_RATE_PER_ORDER;}
    private void close(TradeState s,double price){if(s.side==Side.LONG)s.realized+=(price-s.entry)*s.qty;else if(s.side==Side.SHORT)s.realized+=(s.entry-price)*s.qty;s.estimatedCosts+=price*s.qty*ESTIMATED_COST_RATE_PER_ORDER;}
    private double adversePct(TradeState s,double price){if(s.entry<=0)return 0;if(s.side==Side.LONG)return Math.max(0,(s.entry-price)/s.entry);if(s.side==Side.SHORT)return Math.max(0,(price-s.entry)/s.entry);return 0;}
    private void resetDaily(TradeState s){Calendar c=Calendar.getInstance();int d=c.get(Calendar.DAY_OF_YEAR);if(s.dayOfYear!=d){s.dayOfYear=d;s.reversalsToday=0;}}
    private String fmt(double x){return String.format(Locale.US,"%.2f",x);}
}
