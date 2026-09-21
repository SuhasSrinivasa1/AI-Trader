package com.ps.shadowtrader;

import java.util.*;
import static com.ps.shadowtrader.Models.*;

public final class AdaptiveTradeController {
    public static final double BUDGET=100000.0;
    public static final double COST_RATE_PER_ORDER=.0012;
    private final AdaptiveModel model;

    public AdaptiveTradeController(AdaptiveModel model){this.model=model;}

    public String act(TradeState s,AdaptiveBrain.Decision best,double price){
        if(best==null){s.last=price;return "WAIT — no adaptive decision";}
        s.last=price;
        if(s.side==Side.FLAT){
            if(best.side==Side.FLAT)return "WAIT — expected edge does not clear dynamic cost/noise hurdle";
            open(s,best,price);return "SIMULATED "+best.side+" "+best.symbol+" @ "+fmt(price)+" • adaptive entry";
        }

        if(!s.symbol.equals(best.symbol)){
            double currentUnrealPct=s.entry<=0?0:(s.side==Side.LONG?(price-s.entry)/s.entry:(s.entry-price)/s.entry);
            double switchHurdle=best.requiredEdgePct*(1.0+Math.max(0,-currentUnrealPct)*8);
            if(best.side!=Side.FLAT&&best.opportunity()>switchHurdle&&best.confidence>=.78){
                String old=s.symbol+" "+s.side;closeAndLearn(s,price,"capital rotation");
                open(s,best,price);return "ROTATE "+old+" → "+best.symbol+" "+best.side+" • stronger net edge";
            }
            return "HOLD "+s.symbol+" — current position retained; alternate edge insufficient";
        }

        if(best.side==s.side){
            return "HOLD "+s.side+" "+s.symbol+" — adaptive edge remains aligned";
        }

        double pnlPct=currentPnlPct(s,price);
        double exitPressure=Math.max(0,best.expectedMovePct-best.requiredEdgePct)*best.confidence;
        double dynamicExit=Math.max(.0006,best.requiredEdgePct*.35);
        if(best.side==Side.FLAT){
            if(Math.abs(pnlPct)>Math.max(.004,best.volatilityPct*.75)&&best.confidence<.52){
                String old=s.symbol+" "+s.side;closeAndLearn(s,price,"edge decayed");return "SIMULATED EXIT "+old+" • adaptive edge decayed";
            }
            return "HOLD "+s.side+" "+s.symbol+" — no superior opposite edge";
        }

        if(exitPressure>=dynamicExit){
            String old=s.symbol+" "+s.side;closeAndLearn(s,price,"adaptive reversal");
            open(s,best,price);return "SIMULATED REVERSAL "+old+" → "+best.side+" • no fixed cooldown";
        }
        return "HOLD "+s.side+" "+s.symbol+" — reversal does not clear cost-adjusted hurdle";
    }

    public String forceExit(TradeState s,double price,String why){
        if(s.side==Side.FLAT)return "Already flat";
        String old=s.symbol+" "+s.side;closeAndLearn(s,price,why);return "SIMULATED EXIT "+old+" @ "+fmt(price)+" • "+why;
    }

    private void open(TradeState s,AdaptiveBrain.Decision d,double price){
        s.qty=Math.max(1,(int)Math.floor(BUDGET/Math.max(.01,price)));s.entry=price;s.last=price;s.side=d.side;s.symbol=d.symbol;s.openedAtMs=System.currentTimeMillis();s.lastSwitchAtMs=s.openedAtMs;s.estimatedCosts+=price*s.qty*COST_RATE_PER_ORDER;
        model.rememberEntry(d.symbol,d.side.name(),price,d.features,d.confidence,d.expectedMovePct);
    }

    private void closeAndLearn(TradeState s,double price,String why){
        double before=s.realized;
        if(s.side==Side.LONG)s.realized+=(price-s.entry)*s.qty;else if(s.side==Side.SHORT)s.realized+=(s.entry-price)*s.qty;
        s.estimatedCosts+=price*s.qty*COST_RATE_PER_ORDER;
        double gross=s.realized-before;
        double approxCosts=(s.entry+price)*s.qty*COST_RATE_PER_ORDER;
        double net=gross-approxCosts;
        double netPct=s.entry<=0?0:net/(s.entry*s.qty);
        model.learnOnClose(s.symbol,s.side.name(),s.entry,price,netPct,why);
        s.side=Side.FLAT;s.symbol="";s.entry=0;s.qty=0;s.pendingSide=Side.FLAT;s.pendingCount=0;s.lastSwitchAtMs=System.currentTimeMillis();
    }

    private double currentPnlPct(TradeState s,double p){if(s.entry<=0)return 0;return s.side==Side.LONG?(p-s.entry)/s.entry:(s.entry-p)/s.entry;}
    private String fmt(double x){return String.format(Locale.US,"%.2f",x);}
}
