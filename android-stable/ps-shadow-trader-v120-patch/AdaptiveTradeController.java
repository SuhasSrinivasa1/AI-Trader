package com.ps.shadowtrader;

import java.util.*;
import static com.ps.shadowtrader.Models.*;

public final class AdaptiveTradeController {
    public static final double BUDGET=100000.0;
    public static final double COST_RATE_PER_ORDER=.0012;
    private final AdaptiveModel model;

    public AdaptiveTradeController(AdaptiveModel model){this.model=model;}

    public String act(TradeState s,AdaptiveBrain.Decision best,Map<String,Double> prices){
        if(best==null)return "WAIT — no adaptive decision";
        double bestPrice=priceOf(prices,best.symbol);
        double currentPrice=s.side==Side.FLAT?bestPrice:priceOf(prices,s.symbol);
        if(s.side!=Side.FLAT && !Double.isNaN(currentPrice))s.last=currentPrice;

        if(s.side==Side.FLAT){
            if(best.side==Side.FLAT||Double.isNaN(bestPrice))return "WAIT — expected edge does not clear dynamic cost/noise hurdle";
            open(s,best,bestPrice);return "SIMULATED "+best.side+" "+best.symbol+" @ "+fmt(bestPrice)+" • adaptive entry";
        }

        if(s.symbol.equals(best.symbol)){
            if(best.side==s.side)return "HOLD "+s.side+" "+s.symbol+" — adaptive edge remains aligned";

            double pnlPct=currentPnlPct(s,currentPrice);
            if(best.side==Side.FLAT){
                double fadeThreshold=Math.max(.0035,best.volatilityPct*.65);
                if(Math.abs(pnlPct)>=fadeThreshold && best.confidence<.52){
                    String old=s.symbol+" "+s.side;closeAndLearn(s,currentPrice,"edge decayed");
                    return "SIMULATED EXIT "+old+" • adaptive edge decayed";
                }
                return "HOLD "+s.side+" "+s.symbol+" — no superior opposite edge";
            }

            double exitPressure=Math.max(0,best.expectedMovePct-best.requiredEdgePct)*best.confidence;
            double dynamicExit=Math.max(.00055,best.requiredEdgePct*.30);
            if(exitPressure>=dynamicExit){
                String old=s.symbol+" "+s.side;closeAndLearn(s,currentPrice,"adaptive reversal");
                open(s,best,bestPrice);
                return "SIMULATED REVERSAL "+old+" → "+best.side+" • no fixed hold/cooldown";
            }
            return "HOLD "+s.side+" "+s.symbol+" — reversal does not clear cost-adjusted hurdle";
        }

        if(best.side==Side.FLAT||Double.isNaN(bestPrice)||Double.isNaN(currentPrice))
            return "HOLD "+s.symbol+" — alternate candidate not actionable";

        AdaptiveBrain.Decision currentProxy=best;
        double altNet=Math.max(0,best.expectedMovePct-best.requiredEdgePct)*best.confidence;
        double rotationHurdle=Math.max(.0008,best.requiredEdgePct*.45);
        double currentPnl=currentPnlPct(s,currentPrice);
        if(currentPnl<0)rotationHurdle*=1.0+Math.min(1.0,Math.abs(currentPnl)*10);

        if(altNet>=rotationHurdle && best.confidence>=.74){
            String old=s.symbol+" "+s.side;
            closeAndLearn(s,currentPrice,"capital rotation");
            open(s,best,bestPrice);
            return "ROTATE "+old+" → "+best.symbol+" "+best.side+" • stronger cost-adjusted edge";
        }
        return "HOLD "+s.symbol+" — alternate edge insufficient after costs";
    }

    public String forceExit(TradeState s,double price,String why){
        if(s.side==Side.FLAT)return "Already flat";
        String old=s.symbol+" "+s.side;closeAndLearn(s,price,why);return "SIMULATED EXIT "+old+" @ "+fmt(price)+" • "+why;
    }

    private void open(TradeState s,AdaptiveBrain.Decision d,double price){
        s.qty=Math.max(1,(int)Math.floor(BUDGET/Math.max(.01,price)));
        s.entry=price;s.last=price;s.side=d.side;s.symbol=d.symbol;s.openedAtMs=System.currentTimeMillis();s.lastSwitchAtMs=s.openedAtMs;
        s.estimatedCosts+=price*s.qty*COST_RATE_PER_ORDER;
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

    private double priceOf(Map<String,Double> prices,String symbol){
        if(prices==null||symbol==null)return Double.NaN;
        Double x=prices.get(symbol);return x==null?Double.NaN:x;
    }
    private double currentPnlPct(TradeState s,double p){if(s.entry<=0||Double.isNaN(p))return 0;return s.side==Side.LONG?(p-s.entry)/s.entry:(s.entry-p)/s.entry;}
    private String fmt(double x){return String.format(Locale.US,"%.2f",x);}
}
