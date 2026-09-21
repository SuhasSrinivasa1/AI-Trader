package com.ps.shadowtrader;

import android.content.*;
import java.util.*;
import static com.ps.shadowtrader.Models.*;

public final class StrategyTournamentEngine {
    private static final int POPULATION=96;
    private static final double ORDER_COST=.0012;
    private final ChampionStore store;

    public StrategyTournamentEngine(Context c){store=new ChampionStore(c);}

    private static final class Candidate {
        final String id; final Map<String,Double>w; final double floor,cost;
        Candidate(String id,Map<String,Double>w,double floor,double cost){this.id=id;this.w=w;this.floor=floor;this.cost=cost;}
    }
    private static final class Stats {
        double net,dd,score;int trades;double peak;
        Stats(){peak=0;}
    }
    private static final class Eval {
        Candidate c;Stats train,val;double combined;
    }

    public synchronized String run(String symbol,List<Candle> candles){
        LinkedHashMap<String,List<Candle>> m=new LinkedHashMap<>();m.put(symbol,candles);return runBatch(m);
    }

    public synchronized String runBatch(Map<String,List<Candle>> histories){
        LinkedHashMap<String,List<Candle>> clean=new LinkedHashMap<>();
        for(Map.Entry<String,List<Candle>>e:histories.entrySet())if(e.getValue()!=null&&e.getValue().size()>=180)clean.put(e.getKey(),e.getValue());
        if(clean.isEmpty()){String s="Tournament skipped — insufficient 1-minute replay history";store.recordTournament("none",0,s);return s;}

        ChampionStore.Profile current=store.current();
        List<Candidate> candidates=generate(current);
        ArrayList<Eval> evals=new ArrayList<>();
        for(Candidate c:candidates){
            Eval e=evaluate(c,clean);if(e!=null)evals.add(e);
        }
        if(evals.isEmpty()){String s="Tournament produced no valid strategies";store.recordTournament(join(clean.keySet()),candidates.size(),s);return s;}

        Collections.sort(evals,(a,b)->Double.compare(b.combined,a.combined));
        Eval best=evals.get(0);
        Candidate incumbent=new Candidate(current.id,current.weights,current.confidenceFloor,current.costFactor);
        Eval base=evaluate(incumbent,clean);
        double incumbentScore=base==null?-999:base.combined;

        boolean stable=best.val.trades>=2&&best.val.net>0&&best.val.dd<.08;
        boolean beats=best.combined>incumbentScore+.0008;
        boolean notOverfit=best.train.net<=0 || best.val.net>=Math.min(best.train.net*.35,.012) || best.val.net>=.004;
        boolean promote=stable&&beats&&notOverfit&&!best.c.id.equals(current.id);

        StringBuilder top=new StringBuilder();
        for(int i=0;i<Math.min(3,evals.size());i++){
            Eval e=evals.get(i);if(i>0)top.append(" | ");
            top.append(e.c.id).append(" val ").append(String.format(Locale.US,"%+.2f%%",e.val.net*100))
                    .append(" DD ").append(String.format(Locale.US,"%.2f%%",e.val.dd*100))
                    .append(" T").append(e.val.trades);
        }

        String universe=join(clean.keySet());
        String summary;
        if(promote){
            ChampionStore.Profile p=store.make(best.c.id,best.c.w,best.c.floor,best.c.cost,best.combined,best.val.net,best.val.dd,best.val.trades);
            summary="PROMOTED "+best.c.id+" after chronological train/holdout replay on "+universe+
                    " • holdout "+String.format(Locale.US,"%+.2f%%",best.val.net*100)+
                    " • drawdown "+String.format(Locale.US,"%.2f%%",best.val.dd*100)+
                    " • trades "+best.val.trades+" • top: "+top;
            store.promote(p,universe,candidates.size(),summary);
        }else{
            summary="Champion retained ("+current.id+") after testing "+candidates.size()+" strategy genomes on "+universe+
                    " • best challenger "+best.c.id+" holdout "+String.format(Locale.US,"%+.2f%%",best.val.net*100)+
                    " • incumbent score "+String.format(Locale.US,"%.3f",incumbentScore)+
                    " • challenger score "+String.format(Locale.US,"%.3f",best.combined)+" • top: "+top;
            store.recordTournament(universe,candidates.size(),summary);
        }
        return summary;
    }

    private Eval evaluate(Candidate c,Map<String,List<Candle>> histories){
        double trainNet=0,trainDd=0,valNet=0,valDd=0;int trainTrades=0,valTrades=0,n=0;
        for(List<Candle>x:histories.values()){
            int warm=45;int usable=x.size()-warm;if(usable<100)continue;
            int split=warm+(int)(usable*.70);
            Stats a=simulate(x,warm,split,c);
            Stats b=simulate(x,split,x.size(),c);
            trainNet+=a.net;trainDd+=a.dd;trainTrades+=a.trades;
            valNet+=b.net;valDd+=b.dd;valTrades+=b.trades;n++;
        }
        if(n==0)return null;
        Stats tr=new Stats(),va=new Stats();
        tr.net=trainNet/n;tr.dd=trainDd/n;tr.trades=trainTrades;
        va.net=valNet/n;va.dd=valDd/n;va.trades=valTrades;

        double overfit=Math.max(0,tr.net-va.net);
        double turnoverPenalty=Math.max(0,va.trades-12*n)*.00008;
        double combined=.30*tr.net+.70*va.net-1.15*va.dd-.20*overfit-turnoverPenalty;
        Eval e=new Eval();e.c=c;e.train=tr;e.val=va;e.combined=combined;return e;
    }

    private Stats simulate(List<Candle>x,int start,int end,Candidate c){
        Stats s=new Stats();int pos=0;double entry=0,cum=0,peak=0;
        for(int i=Math.max(45,start);i<end;i++){
            Map<String,Double>f=features(x,i);
            double raw=0,abs=0;int posVotes=0,negVotes=0;
            for(String k:ChampionStore.KEYS){
                double v=f.containsKey(k)?f.get(k):0, w=c.w.containsKey(k)?c.w.get(k):1.0;
                raw+=v*w;abs+=Math.abs(v*w);if(v>.12)posVotes++;if(v<-.12)negVotes++;
            }
            int side=raw>0?1:raw<0?-1:0;
            double agreement=side>0?(double)posVotes/Math.max(1,posVotes+negVotes):(double)negVotes/Math.max(1,posVotes+negVotes);
            double strength=Math.tanh(Math.abs(raw)/3.1);
            double conf=clamp(.42+.38*strength+.20*agreement,0,.99);

            Candle z=x.get(i);double atr=atr(x,i,14),vol=z.c<=0?0:atr/z.c;
            double r3=returnAt(x,i,3),r10=returnAt(x,i,10);
            double observed=Math.max(Math.abs(r3),Math.max(Math.abs(r10)*.45,vol*.8));
            double expected=clamp(observed*(.65+.55*conf),.0002,.06);
            double required=ORDER_COST*2*c.cost+Math.max(.0005,vol*.20);
            boolean actionable=side!=0&&conf>=c.floor&&expected>required&&Math.abs(raw)>=.55;

            if(pos==0){
                if(actionable){pos=side;entry=z.c;cum-=ORDER_COST;s.trades++;}
            }else if(actionable&&side!=pos){
                cum+=pos*(z.c-entry)/entry-ORDER_COST;
                pos=side;entry=z.c;cum-=ORDER_COST;s.trades++;
            }else if(!actionable&&Math.abs(raw)<.18){
                cum+=pos*(z.c-entry)/entry-ORDER_COST;
                pos=0;entry=0;
            }

            peak=Math.max(peak,cum);
            s.dd=Math.max(s.dd,peak-cum);
        }
        if(pos!=0&&end>0){
            double p=x.get(end-1).c;cum+=pos*(p-entry)/entry-ORDER_COST;
        }
        s.net=cum;s.peak=peak;return s;
    }

    private List<Candidate> generate(ChampionStore.Profile current){
        ArrayList<Candidate> out=new ArrayList<>();
        out.add(new Candidate(current.id,new LinkedHashMap<>(current.weights),current.confidenceFloor,current.costFactor));

        LinkedHashMap<String,Double> momentum=new LinkedHashMap<>(current.weights);
        momentum.put("ema",1.35);momentum.put("vwap",1.05);momentum.put("macd",1.0);momentum.put("breakout",1.4);momentum.put("micro",1.45);momentum.put("accel",1.2);momentum.put("reversion",.25);
        out.add(new Candidate("MOMENTUM",momentum,.62,.95));

        LinkedHashMap<String,Double> breakout=new LinkedHashMap<>(current.weights);
        breakout.put("volume",1.25);breakout.put("breakout",1.65);breakout.put("persistence",1.1);breakout.put("micro",1.15);breakout.put("candle",.8);
        out.add(new Candidate("BREAKOUT",breakout,.64,1.0));

        LinkedHashMap<String,Double> reversion=new LinkedHashMap<>(current.weights);
        reversion.put("rsi",1.35);reversion.put("reversion",1.55);reversion.put("vwap",1.0);reversion.put("breakout",.35);reversion.put("micro",.65);
        out.add(new Candidate("REVERSION",reversion,.68,1.05));

        LinkedHashMap<String,Double> micro=new LinkedHashMap<>(current.weights);
        micro.put("micro",1.8);micro.put("accel",1.55);micro.put("volume",1.1);micro.put("persistence",.9);micro.put("rsi",.3);
        out.add(new Candidate("MICRO_TREND",micro,.60,.90));

        long seed=20260921L+store.generation()*10007L+(System.currentTimeMillis()/86400000L);
        Random r=new Random(seed);
        while(out.size()<POPULATION){
            LinkedHashMap<String,Double>w=new LinkedHashMap<>();
            for(String k:ChampionStore.KEYS){
                double base=current.weights.containsKey(k)?current.weights.get(k):1.0;
                double scale=.55+r.nextDouble()*.95;
                if(r.nextDouble()<.18)scale=.25+r.nextDouble()*.45;
                if(r.nextDouble()<.12)scale=1.45+r.nextDouble()*.65;
                w.put(k,clamp(base*scale,.12,2.8));
            }
            double floor=.54+r.nextDouble()*.24;
            double cost=.75+r.nextDouble()*.75;
            out.add(new Candidate("G"+store.generation()+"-"+String.format(Locale.US,"%02d",out.size()),w,floor,cost));
        }
        return out;
    }

    private Map<String,Double> features(List<Candle>x,int i){
        LinkedHashMap<String,Double>f=new LinkedHashMap<>();
        Candle z=x.get(i),p=x.get(i-1);
        double atr=atr(x,i,14),ema9=ema(x,i,9),ema21=ema(x,i,21),rsi=rsi(x,i,14),vw=vwap(x,i,20),macd=ema(x,i,12)-ema(x,i,26);
        double vol=z.v/Math.max(1,avgVol(x,i,20));
        double r3=returnAt(x,i,3),r10=returnAt(x,i,10),r20=returnAt(x,i,20);
        double microRet=r10,shortRet=r3,accel=shortRet-microRet;
        f.put("ema",signed(ema9-ema21,Math.max(.0001,atr)));
        f.put("rsi",clamp((50-rsi)/25.0,-1,1));
        f.put("vwap",signed(z.c-vw,Math.max(.0001,atr)));
        f.put("macd",signed(macd,Math.max(.0001,atr*.5)));
        f.put("volume",clamp((vol-1)*Math.signum(z.c-z.o),-1.5,1.5));
        f.put("candle",candleSignal(p,z));
        f.put("breakout",breakoutStrength(x,i));
        f.put("persistence",clamp(r3*90+r10*35,-1.5,1.5));
        f.put("relative",0.0);
        f.put("micro",clamp(microRet*150,-2,2));
        f.put("accel",clamp(accel*220,-2,2));
        f.put("reversion",(rsi<28?1:(rsi>72?-1:0))*Math.min(1,Math.abs(50-rsi)/30.0));
        return f;
    }

    private double ema(List<Candle>x,int i,int n){int start=Math.max(0,i-n*3);double k=2.0/(n+1),e=x.get(start).c;for(int j=start+1;j<=i;j++)e=x.get(j).c*k+e*(1-k);return e;}
    private double rsi(List<Candle>x,int i,int n){double g=0,l=0;for(int j=i-n+1;j<=i;j++){double d=x.get(j).c-x.get(j-1).c;if(d>=0)g+=d;else l-=d;}if(l==0)return 100;return 100-100/(1+g/l);}
    private double vwap(List<Candle>x,int i,int n){double pv=0,v=0;for(int j=i-n+1;j<=i;j++){Candle z=x.get(j);double tp=(z.h+z.l+z.c)/3;pv+=tp*z.v;v+=z.v;}return v==0?x.get(i).c:pv/v;}
    private double avgVol(List<Candle>x,int i,int n){double s=0;for(int j=i-n+1;j<=i;j++)s+=x.get(j).v;return s/n;}
    private double atr(List<Candle>x,int i,int n){double s=0;for(int j=i-n+1;j<=i;j++){Candle z=x.get(j),p=x.get(j-1);s+=Math.max(z.h-z.l,Math.max(Math.abs(z.h-p.c),Math.abs(z.l-p.c)));}return s/n;}
    private double returnAt(List<Candle>x,int i,int n){if(i-n<0)return 0;double a=x.get(i-n).c,b=x.get(i).c;return a==0?0:b/a-1;}
    private double breakoutStrength(List<Candle>x,int i){double hi=-1e99,lo=1e99;for(int j=i-20;j<i;j++){hi=Math.max(hi,x.get(j).h);lo=Math.min(lo,x.get(j).l);}double p=x.get(i).c,range=Math.max(.0001,hi-lo);if(p>hi)return clamp((p-hi)/range*4+.4,0,1.5);if(p<lo)return -clamp((lo-p)/range*4+.4,0,1.5);double mid=(hi+lo)/2;return clamp((p-mid)/(range/2),-1,1)*.3;}
    private double candleSignal(Candle a,Candle b){double body=Math.max(.0001,Math.abs(b.c-b.o)),range=Math.max(.0001,b.h-b.l),lower=Math.min(b.o,b.c)-b.l,upper=b.h-Math.max(b.o,b.c);if(a.c<a.o&&b.c>b.o&&b.o<=a.c&&b.c>=a.o)return 1;if(a.c>a.o&&b.c<b.o&&b.o>=a.c&&b.c<=a.o)return -1;if(lower>body*2&&upper<body)return .7;if(upper>body*2&&lower<body)return -.7;return clamp((b.c-b.o)/range,-.6,.6);}
    private double signed(double x,double scale){return clamp(x/scale,-1.5,1.5);}
    private double clamp(double x,double a,double b){return Math.max(a,Math.min(b,x));}
    private String join(Collection<String>x){StringBuilder s=new StringBuilder();for(String a:x){if(s.length()>0)s.append(",");s.append(a);}return s.toString();}
}
