package com.suhas.nsedeliverymomentum;

import java.util.*;

/** Detects large intraday V/U recovery structures. The engine looks for a meaningful decline,
 * a recognisable basin/trough, and a confirmed upward recovery leg. It is deliberately separate
 * from both the continuation and persistent-uptrend engines. */
public final class ReversalMath {
    private ReversalMath(){}
    public static final class Metrics {
        public double dropPct,reboundPct,recoveryRatio,basinMinutes,recentLegPct,recentPace,
                closeLocation,vwap,vwapDistancePct,volumeImpulse,rangePct,turnoverCr,spread,
                flow,score,confidence,lastSwingPct;
        public int swingCount,troughIndex; public String shape=""; public String reason=""; public boolean qualified;
    }

    public static Metrics calculate(List<GrowwClient.Candle> cs,double ltp,double dayHigh,double dayLow,
                                    double flow,double spread,double turnoverCr,double historicalHitRate){
        Metrics m=new Metrics();
        if(cs==null||cs.size()<12||ltp<=0){m.reason="need at least 12 three-minute candles";return m;}
        int n=cs.size();
        int searchStart=Math.max(2,n-70),searchEnd=n-3;
        double best=0;int bestT=-1,bestL=-1;
        for(int t=searchStart+2;t<=searchEnd;t++){
            double trough=cs.get(t).low;if(trough<=0)continue;
            int leftStart=Math.max(searchStart,t-28);double leftPeak=0;int li=-1;
            for(int i=leftStart;i<t;i++){if(cs.get(i).high>leftPeak){leftPeak=cs.get(i).high;li=i;}}
            if(leftPeak<=trough||li<0)continue;
            double drop=(leftPeak/trough-1)*100;double rebound=(ltp/trough-1)*100;
            double rec=drop>0?rebound/drop:0;double score=drop*Math.min(1.2,rec);
            if(drop>=0.8&&rebound>=0.45&&score>best){best=score;bestT=t;bestL=li;}
        }
        if(bestT<0){m.reason="no large V/U basin yet";return m;}
        m.troughIndex=bestT;double trough=cs.get(bestT).low,leftPeak=cs.get(bestL).high;
        m.dropPct=(leftPeak/trough-1)*100;m.reboundPct=(ltp/trough-1)*100;m.recoveryRatio=m.dropPct>0?m.reboundPct/m.dropPct:0;
        int basin=0;double band=trough*1.0045;for(int i=Math.max(bestL,bestT-12);i<=Math.min(n-1,bestT+12);i++)if(cs.get(i).low<=band)basin++;
        m.basinMinutes=basin*3.0;m.shape=basin>=5?"U":"V";
        int recentStart=Math.max(bestT, n-6);double recentBase=cs.get(recentStart).close;m.recentLegPct=recentBase>0?(ltp/recentBase-1)*100:0;
        m.recentPace=regressionPace(cs.subList(Math.max(bestT,n-12),n));
        double range=Math.max(0.01,dayHigh-dayLow);m.closeLocation=Math.max(0,Math.min(1,(ltp-dayLow)/range));m.rangePct=dayLow>0?(dayHigh/dayLow-1)*100:0;
        double pv=0,vol=0;for(GrowwClient.Candle c:cs){double tp=(c.high+c.low+c.close)/3.0;pv+=tp*c.volume;vol+=c.volume;}m.vwap=vol>0?pv/vol:0;m.vwapDistancePct=m.vwap>0?(ltp/m.vwap-1)*100:0;
        double baseVol=0,recentVol=0;int baseN=0,recentN=0;for(int i=0;i<n;i++){if(i>=n-4){recentVol+=cs.get(i).volume;recentN++;}else if(i>=Math.max(0,n-20)){baseVol+=cs.get(i).volume;baseN++;}}
        double b=baseN>0?baseVol/baseN:0,r=recentN>0?recentVol/recentN:0;m.volumeImpulse=b>0?r/b:1;
        m.turnoverCr=turnoverCr;m.spread=spread;m.flow=flow;
        List<Integer> piv=new ArrayList<>();int dir=0;double pivot=cs.get(Math.max(0,n-50)).close;for(int i=Math.max(1,n-49);i<n;i++){double c=cs.get(i).close;double ch=(c/pivot-1)*100;if(dir<=0&&ch>=0.65){piv.add(i);dir=1;pivot=c;}else if(dir>=0&&ch<=-0.65){piv.add(i);dir=-1;pivot=c;}else if((dir>=0&&c>pivot)||(dir<=0&&c<pivot))pivot=c;}m.swingCount=piv.size();
        m.lastSwingPct=Math.abs((ltp/trough-1)*100);
        double s=0;
        s+=18*scale(m.dropPct,0.9,3.5);
        s+=22*scale(m.recoveryRatio,0.45,1.05);
        s+=14*scale(m.recentLegPct,0.25,1.50);
        s+=10*scale(m.recentPace,0.10,1.80);
        s+=8*scale(m.closeLocation,0.45,0.90);
        s+=7*scale(m.volumeImpulse,0.9,2.0);
        s+=6*scale(m.swingCount,1,6);
        s+=5*scale(m.rangePct,1.0,5.0);
        s+=4*scale(m.vwapDistancePct,-0.40,1.0);
        s+=3*scale(m.turnoverCr,5,150);
        s+=3*scale(m.flow,-0.2,0.4);
        if(m.recentPace<0)s-=15;if(m.recoveryRatio<0.35)s-=12;if(m.spread>0.28)s-=12;
        if(m.closeLocation<0.35)s-=8;if(m.volumeImpulse<0.65)s-=6;
        m.score=clamp(s,0,100);double prior=historicalHitRate>0?historicalHitRate:0.50;m.confidence=clamp(0.84*m.score+16*prior,0,99);
        double minTurn=4.0;
        List<String> fail=new ArrayList<>();
        if(m.dropPct<0.9)fail.add("drop <0.9%");
        if(m.reboundPct<0.65)fail.add("rebound <0.65%");
        if(m.recoveryRatio<0.50)fail.add("recovery <50%");
        if(m.recentLegPct<0.20)fail.add("recovery leg not rising");
        if(m.recentPace<0.05)fail.add("recent slope not positive");
        if(m.closeLocation<0.45)fail.add("still too low in day range");
        if(m.spread>0.28)fail.add("spread too wide");
        if(m.turnoverCr<minTurn)fail.add("turnover too low");
        if(m.score<64)fail.add(String.format(Locale.US,"pattern score %.0f <64",m.score));
        m.qualified=fail.isEmpty();
        m.reason=m.qualified?m.shape+" REVERSAL CONFIRMED • recovery leg active":String.join(" • ",fail);
        return m;
    }
    private static double regressionPace(List<GrowwClient.Candle> c){int n=c.size();if(n<2)return 0;double sx=0,sy=0,sxx=0,sxy=0;for(int i=0;i<n;i++){double x=i*3.0,y=Math.log(Math.max(0.01,c.get(i).close));sx+=x;sy+=y;sxx+=x*x;sxy+=x*y;}double den=n*sxx-sx*sx;if(den==0)return 0;double b=(n*sxy-sx*sy)/den;return (Math.exp(b*60)-1)*100;}
    private static double scale(double x,double lo,double hi){return clamp((x-lo)/(hi-lo),0,1);}private static double clamp(double x,double lo,double hi){return Math.max(lo,Math.min(hi,x));}
}
