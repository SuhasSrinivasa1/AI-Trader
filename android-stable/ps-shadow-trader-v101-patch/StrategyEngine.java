package com.ps.shadowtrader;

import java.util.*;
import static com.ps.shadowtrader.Models.*;

public class StrategyEngine {
    private static final double CONSENSUS_THRESHOLD=1.20;

    public Signal evaluate(List<Candle> c) {
        if(c.size()<30) return new Signal(Side.FLAT,0,Arrays.asList("Waiting for 30 candles","HOLD/WAIT until enough evidence exists"));
        List<String> bull=new ArrayList<>(), bear=new ArrayList<>();
        double bs=0, ss=0;
        Candle x=c.get(c.size()-1), p=c.get(c.size()-2);
        double ema9=ema(c,9), ema21=ema(c,21), rsi=rsi(c,14), vw=vwap(c,20), macd=ema(c,12)-ema(c,26), volAvg=avgVol(c,20), atr=atr(c,14);

        if(ema9>ema21){bs+=1.2;bull.add("EMA 9/21 trend-following: bullish");} else {ss+=1.2;bear.add("EMA 9/21 trend-following: bearish");}
        if(rsi<35){bs+=0.8;bull.add("RSI mean-reversion: oversold reversal zone");}
        if(rsi>65){ss+=0.8;bear.add("RSI mean-reversion: overbought reversal zone");}
        if(x.c>vw){bs+=0.7;bull.add("VWAP strategy: price above 20-candle VWAP");} else {ss+=0.7;bear.add("VWAP strategy: price below 20-candle VWAP");}
        if(macd>0){bs+=0.6;bull.add("MACD momentum: positive");} else {ss+=0.6;bear.add("MACD momentum: negative");}
        if(x.v>volAvg*1.5){
            if(x.c>x.o){bs+=0.8;bull.add("Volume expansion: bullish confirmation");}
            else {ss+=0.8;bear.add("Volume expansion: bearish confirmation");}
        }
        if(isBullEngulf(p,x)){bs+=1.0;bull.add("Candlestick: Bullish Engulfing");}
        if(isBearEngulf(p,x)){ss+=1.0;bear.add("Candlestick: Bearish Engulfing");}
        if(isHammer(x)){bs+=0.7;bull.add("Candlestick: Hammer / lower-price rejection");}
        if(isShootingStar(x)){ss+=0.7;bear.add("Candlestick: Shooting Star / upper-price rejection");}
        if(breakout(c,true)){bs+=1.0;bull.add("Price action: 20-candle resistance breakout");}
        if(breakout(c,false)){ss+=1.0;bear.add("Price action: 20-candle support breakdown");}
        if(last3Higher(c)){bs+=0.7;bull.add("Persistence filter: 3 rising closes");}
        if(last3Lower(c)){ss+=0.7;bear.add("Persistence filter: 3 falling closes");}

        double diff=bs-ss;
        boolean doji=isDoji(x);
        boolean compressed=(x.h-x.l)<atr*0.55;
        boolean conflict=bs>=2.0 && ss>=2.0 && Math.abs(diff)<1.6;

        if(doji && Math.abs(diff)<2.0)
            return new Signal(Side.FLAT,Math.abs(diff),Arrays.asList("Candlestick: Doji / indecision","HOLD/WAIT — reversal not confirmed",String.format(Locale.US,"Bull %.1f / Bear %.1f",bs,ss)));
        if(compressed && Math.abs(diff)<1.7)
            return new Signal(Side.FLAT,Math.abs(diff),Arrays.asList("ATR noise filter: compressed candle","HOLD/WAIT — insufficient movement quality",String.format(Locale.US,"Bull %.1f / Bear %.1f",bs,ss)));
        if(conflict || Math.abs(diff)<CONSENSUS_THRESHOLD)
            return new Signal(Side.FLAT,Math.abs(diff),Arrays.asList("No strong multi-strategy consensus","HOLD/WAIT — avoid churn",String.format(Locale.US,"Bull %.1f / Bear %.1f",bs,ss)));

        return diff>0 ? new Signal(Side.LONG,diff,bull) : new Signal(Side.SHORT,-diff,bear);
    }

    private double ema(List<Candle> c,int n){ double k=2.0/(n+1), e=c.get(Math.max(0,c.size()-n*3)).c; for(int i=Math.max(0,c.size()-n*3)+1;i<c.size();i++) e=c.get(i).c*k+e*(1-k); return e; }
    private double rsi(List<Candle> c,int n){double g=0,l=0; for(int i=c.size()-n;i<c.size();i++){double d=c.get(i).c-c.get(i-1).c;if(d>=0)g+=d;else l-=d;} if(l==0)return 100;double rs=g/l;return 100-(100/(1+rs));}
    private double vwap(List<Candle> c,int n){double pv=0,v=0; for(int i=c.size()-n;i<c.size();i++){Candle x=c.get(i);double tp=(x.h+x.l+x.c)/3;pv+=tp*x.v;v+=x.v;}return v==0?c.get(c.size()-1).c:pv/v;}
    private double avgVol(List<Candle> c,int n){double s=0;for(int i=c.size()-n;i<c.size();i++)s+=c.get(i).v;return s/n;}
    private double atr(List<Candle> c,int n){double s=0;for(int i=c.size()-n;i<c.size();i++){Candle x=c.get(i),p=c.get(i-1);double tr=Math.max(x.h-x.l,Math.max(Math.abs(x.h-p.c),Math.abs(x.l-p.c)));s+=tr;}return s/n;}
    private boolean isBullEngulf(Candle a,Candle b){return a.c<a.o&&b.c>b.o&&b.o<=a.c&&b.c>=a.o;}
    private boolean isBearEngulf(Candle a,Candle b){return a.c>a.o&&b.c<b.o&&b.o>=a.c&&b.c<=a.o;}
    private boolean isHammer(Candle x){double body=Math.max(0.0001,Math.abs(x.c-x.o)), lower=Math.min(x.o,x.c)-x.l, upper=x.h-Math.max(x.o,x.c);return lower>body*2&&upper<body*0.8;}
    private boolean isShootingStar(Candle x){double body=Math.max(0.0001,Math.abs(x.c-x.o)), upper=x.h-Math.max(x.o,x.c), lower=Math.min(x.o,x.c)-x.l;return upper>body*2&&lower<body*0.8;}
    private boolean isDoji(Candle x){double range=Math.max(0.0001,x.h-x.l);return Math.abs(x.c-x.o)/range<0.14;}
    private boolean breakout(List<Candle> c,boolean up){Candle x=c.get(c.size()-1); double level=up?-Double.MAX_VALUE:Double.MAX_VALUE;for(int i=c.size()-21;i<c.size()-1;i++)level=up?Math.max(level,c.get(i).h):Math.min(level,c.get(i).l);return up?x.c>level:x.c<level;}
    private boolean last3Higher(List<Candle> c){int n=c.size();return c.get(n-1).c>c.get(n-2).c&&c.get(n-2).c>c.get(n-3).c;}
    private boolean last3Lower(List<Candle> c){int n=c.size();return c.get(n-1).c<c.get(n-2).c&&c.get(n-2).c<c.get(n-3).c;}
}
