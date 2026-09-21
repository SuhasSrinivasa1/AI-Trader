package com.ps.shadowtrader;

import java.util.*;
import static com.ps.shadowtrader.Models.*;

public final class LongHorizonFeatures {
    private LongHorizonFeatures(){}

    public static Map<String,Double> current(List<Candle>d,double nifty20,double sectorMean){return at(d,d.size()-1,nifty20,sectorMean);}

    public static Map<String,Double> at(List<Candle>d,int i,double nifty20,double sectorMean){
        LinkedHashMap<String,Double>f=new LinkedHashMap<>();
        double r5=ret(d,i,5),r20=ret(d,i,20),r60=ret(d,i,60);
        double vr=avgVol(d,i-4,i+1)/Math.max(1,avgVol(d,i-29,i-4));
        double hi60=0;for(int j=Math.max(0,i-60);j<i;j++)hi60=Math.max(hi60,d.get(j).h);
        double breakout=d.get(i).c/Math.max(.01,hi60)-1;
        double rsi=rsi(d,i,14),vol=volatility(d,i,20),relative=r20-nifty20;
        double weekly=(ret(d,i,5)+ret(d,i,10)+ret(d,i,15))/3.0;
        double accel=r5-r20/4.0;
        double sectorRel=sectorMean==0?0:r20-sectorMean;
        f.put("r5",clip(r5*8));f.put("r20",clip(r20*4));f.put("r60",clip(r60*2));
        f.put("volume",clip((vr-1)*.8));f.put("breakout",clip(breakout*12));
        f.put("rsi",clip((rsi-50)/25));f.put("volatility",clip(vol*12));
        f.put("relative",clip(relative*6));f.put("weekly",clip(weekly*6));f.put("acceleration",clip(accel*10));f.put("sector_relative",clip(sectorRel*6));
        return f;
    }

    public static double raw(Map<String,Double>f,Map<String,Double>w){
        double s=0,n=0;for(String k:LongHorizonChampionStore.KEYS){double ww=w.containsKey(k)?w.get(k):0;s+=f.get(k)*ww;n+=Math.abs(ww);}return n==0?0:s/Math.sqrt(n);
    }
    public static double probability(Map<String,Double>f,LongHorizonChampionStore.Profile p){
        double z=raw(f,p.w);return 1.0/(1.0+Math.exp(-z));
    }

    private static double ret(List<Candle>d,int i,int n){if(i-n<0)return 0;double a=d.get(i-n).c,b=d.get(i).c;return a==0?0:b/a-1;}
    private static double avgVol(List<Candle>d,int a,int b){a=Math.max(0,a);b=Math.min(d.size(),b);double s=0;int n=0;for(int i=a;i<b;i++){s+=d.get(i).v;n++;}return n==0?0:s/n;}
    private static double rsi(List<Candle>d,int i,int n){if(i<n)return 50;double g=0,l=0;for(int j=i-n+1;j<=i;j++){double x=d.get(j).c-d.get(j-1).c;if(x>=0)g+=x;else l-=x;}return l==0?100:100-100/(1+g/l);}
    private static double volatility(List<Candle>d,int i,int n){if(i<n)return 0;double m=0;double[]r=new double[n];for(int j=0;j<n;j++){int x=i-n+1+j;r[j]=d.get(x).c/d.get(x-1).c-1;m+=r[j];}m/=n;double s=0;for(double x:r)s+=(x-m)*(x-m);return Math.sqrt(s/n);}
    private static double clip(double x){return Math.max(-2,Math.min(2,x));}
}
