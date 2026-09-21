package com.ps.shadowtrader;

import java.util.*;
import static com.ps.shadowtrader.Models.*;

public final class AdaptiveBrain {
    public static final class Decision {
        public final String symbol;
        public final Side side;
        public final double score;
        public final double confidence;
        public final double expectedMovePct;
        public final double requiredEdgePct;
        public final double volatilityPct;
        public final Map<String,Double> features;
        public final List<String> reasons;
        Decision(String symbol,Side side,double score,double confidence,double expectedMovePct,double requiredEdgePct,double volatilityPct,Map<String,Double>features,List<String>reasons){
            this.symbol=symbol;this.side=side;this.score=score;this.confidence=confidence;this.expectedMovePct=expectedMovePct;this.requiredEdgePct=requiredEdgePct;this.volatilityPct=volatilityPct;this.features=features;this.reasons=reasons;
        }
        public double opportunity(){return confidence*Math.max(0,expectedMovePct-requiredEdgePct);}
    }

    private final AdaptiveModel model;
    public AdaptiveBrain(AdaptiveModel model){this.model=model;}

    public Decision evaluate(String symbol,List<Candle> c,List<Double> micro,double niftyMicroReturn){
        if(c==null||c.size()<35)return flat(symbol,"Waiting for 1-minute candle history");
        Map<String,Double>f=new LinkedHashMap<>();ArrayList<String>reasons=new ArrayList<>();
        Candle x=c.get(c.size()-1),p=c.get(c.size()-2);
        double price=x.c,atr=atr(c,14),volPct=price<=0?0:atr/price;
        double ema9=ema(c,9),ema21=ema(c,21),rsi=rsi(c,14),vwap=vwap(c,20),macd=ema(c,12)-ema(c,26);
        double volRatio=x.v/Math.max(1,avgVol(c,20));
        double r3=ret(c,3),r10=ret(c,10),r20=ret(c,20);
        double microRet=microReturn(micro,Math.min(12,micro==null?0:micro.size()));
        double microShort=microReturn(micro,Math.min(4,micro==null?0:micro.size()));
        double accel=microShort-microRet;
        double relative=microRet-niftyMicroReturn;
        double breakout=breakoutStrength(c);
        double candle=candleSignal(p,x);
        double reversion=(rsi<28?1:(rsi>72?-1:0))*Math.min(1,Math.abs(50-rsi)/30.0);

        f.put("ema",signed(ema9-ema21,Math.max(.0001,atr)));
        f.put("rsi",clamp((50-rsi)/25.0,-1,1));
        f.put("vwap",signed(price-vwap,Math.max(.0001,atr)));
        f.put("macd",signed(macd,Math.max(.0001,atr*.5)));
        f.put("volume",clamp((volRatio-1.0)*Math.signum(x.c-x.o),-1.5,1.5));
        f.put("candle",candle);
        f.put("breakout",breakout);
        f.put("persistence",clamp((r3*90+r10*35),-1.5,1.5));
        f.put("relative",clamp(relative*120,-1.5,1.5));
        f.put("micro",clamp(microRet*150,-2,2));
        f.put("accel",clamp(accel*220,-2,2));
        f.put("reversion",reversion);

        Map<String,Double>w=model.weights();double raw=0,abs=0;int pos=0,neg=0;
        for(Map.Entry<String,Double>e:f.entrySet()){
            double v=e.getValue(),ww=w.get(e.getKey());raw+=v*ww;abs+=Math.abs(v*ww);if(v>.12)pos++;if(v<-.12)neg++;
        }

        Side side=raw>0?Side.LONG:raw<0?Side.SHORT:Side.FLAT;
        double agreement=side==Side.LONG?(double)pos/Math.max(1,pos+neg):(double)neg/Math.max(1,pos+neg);
        double strength=Math.tanh(Math.abs(raw)/3.1);
        double confidence=clamp(.42+.38*strength+.20*agreement,0,0.99);

        double observed=Math.max(Math.abs(microRet),Math.max(Math.abs(r3),volPct*.8));
        double expected=clamp(observed*(.65+.55*confidence),.0002,.06);
        double roundTripCost=.0024;
        double noise=Math.max(.0005,volPct*.20);
        double required=(roundTripCost*model.turnoverPenalty())+noise;
        double floor=model.dynamicConfidenceFloor(volPct);

        if(side==Side.LONG){if(f.get("micro")>.2)reasons.add("micro momentum rising");if(breakout>.25)reasons.add("breakout pressure");if(relative>.002)reasons.add("outperforming NIFTY");}
        else if(side==Side.SHORT){if(f.get("micro")<-.2)reasons.add("micro momentum falling");if(breakout<-.25)reasons.add("breakdown pressure");if(relative<-.002)reasons.add("underperforming NIFTY");}
        if(volRatio>1.5)reasons.add("volume expansion "+String.format(Locale.US,"%.1fx",volRatio));
        reasons.add("adaptive confidence "+String.format(Locale.US,"%.0f%%",confidence*100));
        reasons.add("expected move "+String.format(Locale.US,"%.2f%%",expected*100)+" vs hurdle "+String.format(Locale.US,"%.2f%%",required*100));

        if(confidence<floor||expected<=required||Math.abs(raw)<.55)return new Decision(symbol,Side.FLAT,Math.abs(raw),confidence,expected,required,volPct,f,reasons);
        return new Decision(symbol,side,Math.abs(raw),confidence,expected,required,volPct,f,reasons);
    }

    private Decision flat(String s,String why){Map<String,Double>f=new LinkedHashMap<>();return new Decision(s,Side.FLAT,0,0,0,.0024,0,f,Arrays.asList(why));}
    private double ema(List<Candle>c,int n){double k=2.0/(n+1),e=c.get(Math.max(0,c.size()-n*3)).c;for(int i=Math.max(0,c.size()-n*3)+1;i<c.size();i++)e=c.get(i).c*k+e*(1-k);return e;}
    private double rsi(List<Candle>c,int n){double g=0,l=0;for(int i=c.size()-n;i<c.size();i++){double d=c.get(i).c-c.get(i-1).c;if(d>=0)g+=d;else l-=d;}if(l==0)return 100;return 100-100/(1+g/l);}
    private double vwap(List<Candle>c,int n){double pv=0,v=0;for(int i=c.size()-n;i<c.size();i++){Candle x=c.get(i);double tp=(x.h+x.l+x.c)/3;pv+=tp*x.v;v+=x.v;}return v==0?c.get(c.size()-1).c:pv/v;}
    private double avgVol(List<Candle>c,int n){double s=0;for(int i=c.size()-n;i<c.size();i++)s+=c.get(i).v;return s/n;}
    private double atr(List<Candle>c,int n){double s=0;for(int i=c.size()-n;i<c.size();i++){Candle x=c.get(i),p=c.get(i-1);s+=Math.max(x.h-x.l,Math.max(Math.abs(x.h-p.c),Math.abs(x.l-p.c)));}return s/n;}
    private double ret(List<Candle>c,int n){int z=c.size();if(z<=n)return 0;return c.get(z-1).c/c.get(z-1-n).c-1;}
    private double microReturn(List<Double>x,int n){if(x==null||x.size()<2||n<2)return 0;int z=x.size();double a=x.get(Math.max(0,z-n)),b=x.get(z-1);return a==0?0:b/a-1;}
    private double breakoutStrength(List<Candle>c){int z=c.size();double hi=-1e99,lo=1e99;for(int i=z-21;i<z-1;i++){hi=Math.max(hi,c.get(i).h);lo=Math.min(lo,c.get(i).l);}double p=c.get(z-1).c,range=Math.max(.0001,hi-lo);if(p>hi)return clamp((p-hi)/range*4+.4,0,1.5);if(p<lo)return -clamp((lo-p)/range*4+.4,0,1.5);double mid=(hi+lo)/2;return clamp((p-mid)/(range/2),-1,1)*.3;}
    private double candleSignal(Candle a,Candle b){double body=Math.max(.0001,Math.abs(b.c-b.o)),range=Math.max(.0001,b.h-b.l),lower=Math.min(b.o,b.c)-b.l,upper=b.h-Math.max(b.o,b.c);if(a.c<a.o&&b.c>b.o&&b.o<=a.c&&b.c>=a.o)return 1;if(a.c>a.o&&b.c<b.o&&b.o>=a.c&&b.c<=a.o)return -1;if(lower>body*2&&upper<body)return .7;if(upper>body*2&&lower<body)return -.7;return clamp((b.c-b.o)/range,-.6,.6);}
    private double signed(double x,double scale){return clamp(x/scale,-1.5,1.5);}
    private double clamp(double x,double a,double b){return Math.max(a,Math.min(b,x));}
}
