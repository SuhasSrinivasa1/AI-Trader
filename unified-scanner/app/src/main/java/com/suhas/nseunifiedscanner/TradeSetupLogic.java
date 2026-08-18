package com.suhas.nseunifiedscanner;

import java.util.List;

/**
 * Intraday path-quality logic kept separate from ScannerEngine so the critical
 * resistance/recovery rules are deterministic and unit-testable.
 */
final class TradeSetupLogic {
    private TradeSetupLogic() { }

    static final class Signals {
        double sessionHod;
        double breakoutBaseHod;
        double hodDistancePct;
        double hodDrawdownPct;
        double recoveryPct;
        double fromOpenPct;
        double dayPct;
        double lastRelVol;
        boolean crossedGreen;
        boolean breakoutConfirmed;
        boolean freshHodPressure;
        boolean hodRejected;
    }

    static Signals analyze(List<GrowwApi.Candle> candles, GrowwApi.Ohlc ohlc, double entry) {
        Signals s=new Signals();
        if(ohlc!=null && entry>0) {
            s.dayPct=ohlc.close>0?(entry/ohlc.close-1.0)*100.0:0;
            s.fromOpenPct=ohlc.open>0?(entry/ohlc.open-1.0)*100.0:0;
            s.recoveryPct=ohlc.low>0?(entry/ohlc.low-1.0)*100.0:0;
            s.crossedGreen=ohlc.close>0 && ohlc.low<ohlc.close*0.998 && entry>ohlc.close*1.0005;
        }
        if(candles==null || candles.size()<3 || !(entry>0)) return s;

        int n=candles.size();
        GrowwApi.Candle last=candles.get(n-1);
        String day=last.time!=null && last.time.length()>=10?last.time.substring(0,10):"";
        double hod=0, prior=0, postLow=Double.POSITIVE_INFINITY;
        int hodIndex=-1;
        double prevVol=0; int prevVolN=0;
        for(int i=0;i<n;i++) {
            GrowwApi.Candle c=candles.get(i);
            if(c.time==null || !c.time.startsWith(day)) continue;
            if(i<n-1 && c.high>prior) prior=c.high;
            if(c.high>hod) { hod=c.high; hodIndex=i; }
            if(i>=Math.max(0,n-7) && i<n-1) { prevVol+=Math.max(0,c.volume); prevVolN++; }
        }
        s.sessionHod=hod;
        s.breakoutBaseHod=prior;
        double avgPrevVol=prevVolN==0?0:prevVol/prevVolN;
        s.lastRelVol=avgPrevVol>0?last.volume/avgPrevVol:0;

        if(hodIndex>=0) {
            for(int i=hodIndex;i<n;i++) {
                GrowwApi.Candle c=candles.get(i);
                if(c.time!=null && c.time.startsWith(day)) postLow=Math.min(postLow,c.low);
            }
            postLow=Math.min(postLow,entry);
        }
        if(hod>0) {
            s.hodDistancePct=Math.max(0,(hod/entry-1.0)*100.0);
            if(postLow<Double.POSITIVE_INFINITY && postLow>0) s.hodDrawdownPct=Math.max(0,(hod/postLow-1.0)*100.0);
        }

        double body=Math.abs(last.close-last.open);
        double upper=Math.max(0,last.high-Math.max(last.close,last.open));
        double wickRatio=body>0?upper/body:2.0;
        boolean strongLast=last.close>last.open && s.lastRelVol>=1.30 && wickRatio<=0.85;
        s.breakoutConfirmed=prior>0 && last.close>=prior*1.0005 && strongLast;
        s.freshHodPressure=hod>0 && (hod/Math.max(0.01,last.close)-1.0)*100.0<=0.15 && strongLast;
        s.hodRejected=hod>0 && s.hodDistancePct>=0.45 && s.hodDrawdownPct>=0.65 && !s.breakoutConfirmed;
        return s;
    }

    /**
     * A target needs at least 0.15% of clean air before an already-established
     * HOD. A confirmed/fresh high breakout is allowed to trade through it.
     */
    static boolean clearPath(double entry,double target,double sessionHod,boolean hodRejected,boolean breakoutConfirmed,boolean freshHodPressure) {
        if(!(entry>0) || !(target>entry)) return false;
        if(!(sessionHod>0)) return true;
        if(breakoutConfirmed || freshHodPressure) return true;
        double roomBeyondTarget=(sessionHod/target-1.0)*100.0;
        if(hodRejected && roomBeyondTarget<0.20) return false;
        return roomBeyondTarget>=0.15;
    }

    static double roomBeyondTargetPct(double target,double sessionHod) {
        if(!(target>0) || !(sessionHod>0)) return 9.0;
        return (sessionHod/target-1.0)*100.0;
    }

    static boolean recoverySetup(boolean crossedGreen,double recoveryPct,double fromOpenPct,double rsi,double relVol,double macdHist,double prevMacdHist,double oneHour,double spreadPct,double turnover,double roomR2,double circuitRoom,double breadth,double depthRatio) {
        boolean momentumTurning=macdHist>0 || macdHist>=prevMacdHist;
        boolean marketSupport=breadth>=35.0 || depthRatio>=0.54;
        return crossedGreen && recoveryPct>=1.50 && recoveryPct<=8.0 && fromOpenPct>=0.35 &&
                rsi>=52 && rsi<=70 && relVol>=1.20 && momentumTurning && oneHour>=0.15 &&
                spreadPct<=0.20 && turnover>=50_000_000d && roomR2>=0.68 && circuitRoom>=0.80 && marketSupport;
    }

    static double clamp(double x,double lo,double hi){return Math.max(lo,Math.min(hi,x));}
}
