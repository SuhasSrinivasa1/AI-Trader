package com.ps.shadowtrader;

import java.util.Calendar;
import java.util.Locale;
import static com.ps.shadowtrader.Models.*;

public class TradeSimulator {
    public static final double BUDGET=100000.0;
    public static final long MIN_HOLD_MS=15L*60L*1000L;
    public static final long COOLDOWN_MS=10L*60L*1000L;
    public static final double ENTRY_SCORE_MIN=1.20;
    public static final double REVERSAL_SCORE_MIN=2.20;
    public static final int OPPOSITE_CONFIRMATIONS=2;
    public static final int MAX_REVERSALS_PER_DAY=3;
    public static final double EMERGENCY_ADVERSE_PCT=0.018;
    // Conservative shadow reserve for brokerage/taxes/spread/slippage. Not an exact Groww fee calculation.
    public static final double ESTIMATED_COST_RATE_PER_ORDER=0.0012;

    public void onPrice(TradeState s,double price){s.last=price;}

    public String apply(TradeState s, Signal sig, double price){
        final long now=System.currentTimeMillis();
        s.last=price;
        resetDailyCounterIfNeeded(s);

        if(sig.side==Side.FLAT){
            s.pendingSide=Side.FLAT; s.pendingCount=0;
            return "HOLD/WAIT — no confirmed edge; churn guard active";
        }

        if(s.side==Side.FLAT){
            if(sig.score<ENTRY_SCORE_MIN) return "WAIT — entry score below quality threshold";
            open(s,sig.side,price,now,false);
            return "SIMULATED "+sig.side+" @ "+fmt(price)+" x "+s.qty+" • initial entry";
        }

        if(s.side==sig.side){
            s.pendingSide=Side.FLAT; s.pendingCount=0;
            return "HOLD "+s.side+" — current thesis remains supported";
        }

        if(sig.score<REVERSAL_SCORE_MIN){
            s.pendingSide=Side.FLAT; s.pendingCount=0;
            return "HOLD "+s.side+" — opposite signal too weak to justify costs";
        }

        if(s.pendingSide==sig.side) s.pendingCount++; else {s.pendingSide=sig.side;s.pendingCount=1;}

        long heldMs=now-s.openedAtMs;
        long sinceSwitch=now-s.lastSwitchAtMs;
        double adversePct=adversePct(s,price);
        boolean emergency=adversePct>=EMERGENCY_ADVERSE_PCT && sig.score>=1.80;

        if(s.reversalsToday>=MAX_REVERSALS_PER_DAY)
            return "HOLD "+s.side+" — daily reversal cap reached ("+MAX_REVERSALS_PER_DAY+")";
        if(!emergency && heldMs<MIN_HOLD_MS)
            return "HOLD "+s.side+" — minimum hold filter ("+minutesLeft(MIN_HOLD_MS-heldMs)+" min remaining)";
        if(!emergency && sinceSwitch<COOLDOWN_MS)
            return "HOLD "+s.side+" — cooldown filter ("+minutesLeft(COOLDOWN_MS-sinceSwitch)+" min remaining)";
        if(!emergency && s.pendingCount<OPPOSITE_CONFIRMATIONS)
            return "HOLD "+s.side+" — opposite signal detected; waiting confirmation "+s.pendingCount+"/"+OPPOSITE_CONFIRMATIONS;

        closeCurrent(s,price);
        s.reversalsToday++;
        open(s,sig.side,price,now,true);
        s.pendingSide=Side.FLAT; s.pendingCount=0;
        return "SIMULATED REVERSAL → "+sig.side+" @ "+fmt(price)+" x "+s.qty+(emergency?" • hard invalidation":" • confirmed multi-signal reversal");
    }

    private void open(TradeState s,Side side,double price,long now,boolean reversal){
        s.qty=Math.max(1,(int)Math.floor(BUDGET/price));
        s.entry=price; s.side=side; s.openedAtMs=now;
        if(s.lastSwitchAtMs==0 || reversal) s.lastSwitchAtMs=now;
        s.estimatedCosts+=price*s.qty*ESTIMATED_COST_RATE_PER_ORDER;
    }

    private void closeCurrent(TradeState s,double price){
        if(s.side==Side.LONG) s.realized+=(price-s.entry)*s.qty;
        else if(s.side==Side.SHORT) s.realized+=(s.entry-price)*s.qty;
        s.estimatedCosts+=price*s.qty*ESTIMATED_COST_RATE_PER_ORDER;
    }

    private double adversePct(TradeState s,double price){
        if(s.entry<=0) return 0;
        if(s.side==Side.LONG) return Math.max(0,(s.entry-price)/s.entry);
        if(s.side==Side.SHORT) return Math.max(0,(price-s.entry)/s.entry);
        return 0;
    }

    private void resetDailyCounterIfNeeded(TradeState s){
        Calendar cal=Calendar.getInstance(); int d=cal.get(Calendar.DAY_OF_YEAR);
        if(s.dayOfYear!=d){s.dayOfYear=d;s.reversalsToday=0;}
    }
    private long minutesLeft(long ms){return Math.max(1,(long)Math.ceil(ms/60000.0));}
    private String fmt(double v){return String.format(Locale.US,"%.2f",v);}
}
