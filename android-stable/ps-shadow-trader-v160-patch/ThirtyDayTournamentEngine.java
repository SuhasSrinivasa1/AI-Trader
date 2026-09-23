package com.ps.shadowtrader;

import android.content.*;
import java.util.*;

public final class ThirtyDayTournamentEngine {
    private static final int POPULATION=72;
    private final LongHorizonChampionStore store;
    private final ThirtyDayDataset dataset;

    private static final class Genome {
        String id;Map<String,Double>w;double threshold;
        Genome(String id,Map<String,Double>w,double threshold){this.id=id;this.w=w;this.threshold=threshold;}
    }
    private static final class Metrics {
        double precision,recall,fpr,score;int signals,tp,fp,fn;
    }

    public ThirtyDayTournamentEngine(Context c){store=new LongHorizonChampionStore(c);dataset=new ThirtyDayDataset(c);}

    public synchronized String run(){
        List<ThirtyDayDataset.Example> all=dataset.all();
        if(all.size()<120){String s="30-day tournament waiting for more labeled examples ("+all.size()+"/120)";store.record(s,0,all.size());return s;}
        Collections.sort(all,(a,b)->Long.compare(a.ts,b.ts));
        int split=Math.max(80,(int)(all.size()*.70));
        List<ThirtyDayDataset.Example> train=all.subList(0,split),hold=all.subList(split,all.size());

        LongHorizonChampionStore.Profile incumbent=store.current();
        List<Genome> genomes=generate(incumbent);
        Genome best=null;Metrics bestM=null;double bestCombined=-999;

        for(Genome g:genomes){
            Metrics tr=evaluate(g,train),va=evaluate(g,hold);
            double overfit=Math.max(0,tr.precision-va.precision-.10);
            double combined=.15*tr.score+.85*va.score-.60*overfit;
            if(va.signals<6)combined-=.30;
            if(combined>bestCombined){bestCombined=combined;best=g;bestM=va;}
        }

        Genome base=new Genome(incumbent.id,incumbent.w,incumbent.threshold);
        Metrics baseVal=evaluate(base,hold);
        Metrics baseTrain=evaluate(base,train);
        double baseOverfit=Math.max(0,baseTrain.precision-baseVal.precision-.10);
        double baseScore=.15*baseTrain.score+.85*baseVal.score-.60*baseOverfit;

        boolean promote=best!=null&&!best.id.equals(incumbent.id)
                &&bestM.signals>=6&&bestM.precision>=.30
                &&bestCombined>baseScore+.05
                &&(baseVal.signals<3||bestM.precision>=baseVal.precision+.03);
        String summary;
        if(promote){
            LongHorizonChampionStore.Profile p=store.make(best.id,best.w,best.threshold,bestM.precision,bestM.recall,bestCombined,bestM.signals);
            summary="PROMOTED "+best.id+" • stricter holdout precision "+pct(bestM.precision)+" • recall "+pct(bestM.recall)+" • signals "+bestM.signals+" • examples "+all.size();
            store.promote(p,summary,genomes.size(),all.size());
        }else{
            summary="30-day champion retained ("+incumbent.id+") after "+genomes.size()+" challengers • holdout precision "+pct(baseVal.precision)+" • recall "+pct(baseVal.recall)+" • examples "+all.size();
            store.record(summary,genomes.size(),all.size());
        }
        return summary;
    }

    private Metrics evaluate(Genome g,List<ThirtyDayDataset.Example>x){
        Metrics m=new Metrics();int positives=0,negatives=0;
        for(ThirtyDayDataset.Example e:x){
            double p=prob(e.f,g.w);boolean signal=p>=g.threshold;
            if(e.hit50)positives++;else negatives++;
            if(signal){m.signals++;if(e.hit50)m.tp++;else m.fp++;}
            else if(e.hit50)m.fn++;
        }
        m.precision=m.signals==0?0:(double)m.tp/m.signals;
        m.recall=positives==0?0:(double)m.tp/positives;
        m.fpr=negatives==0?0:(double)m.fp/negatives;
        m.score=1.35*m.precision+.45*m.recall-.75*m.fpr-.002*Math.max(0,m.signals-x.size()*.18);
        return m;
    }

    private List<Genome> generate(LongHorizonChampionStore.Profile current){
        ArrayList<Genome> out=new ArrayList<>();
        out.add(new Genome(current.id,new LinkedHashMap<>(current.w),current.threshold));

        LinkedHashMap<String,Double> momentum=new LinkedHashMap<>(current.w);
        momentum.put("r20",1.35);momentum.put("r60",.9);momentum.put("breakout",1.45);momentum.put("volume",1.1);momentum.put("relative",1.0);momentum.put("volatility",-.35);
        out.add(new Genome("LAB_MOMENTUM",momentum,.70));

        LinkedHashMap<String,Double> explosive=new LinkedHashMap<>(current.w);
        explosive.put("r5",.9);explosive.put("r20",1.15);explosive.put("volume",1.45);explosive.put("breakout",1.7);explosive.put("acceleration",1.2);explosive.put("relative",1.0);
        out.add(new Genome("LAB_EXPLOSIVE",explosive,.72));

        LinkedHashMap<String,Double> quality=new LinkedHashMap<>(current.w);
        quality.put("r20",.85);quality.put("r60",1.0);quality.put("relative",1.2);quality.put("weekly",1.0);quality.put("volatility",-.9);quality.put("breakout",.8);
        out.add(new Genome("LAB_STABLE_RS",quality,.73));

        long seed=20260921L+store.generation()*1009L+(System.currentTimeMillis()/86400000L);
        Random r=new Random(seed);
        while(out.size()<POPULATION){
            LinkedHashMap<String,Double>w=new LinkedHashMap<>();
            for(String k:LongHorizonChampionStore.KEYS){
                double base=current.w.containsKey(k)?current.w.get(k):0;
                double scale=.55+r.nextDouble()*1.05;
                double v=base*scale;
                if(r.nextDouble()<.15)v+=(r.nextDouble()-.5)*1.1;
                w.put(k,clamp(v,-2.5,2.8));
            }
            double threshold=.60+r.nextDouble()*.24;
            out.add(new Genome("L"+store.generation()+"-"+String.format(Locale.US,"%02d",out.size()),w,threshold));
        }
        return out;
    }

    private double prob(Map<String,Double>f,Map<String,Double>w){
        double z=LongHorizonFeatures.raw(f,w);return 1.0/(1.0+Math.exp(-z));
    }
    private String pct(double x){return String.format(Locale.US,"%.0f%%",x*100);}
    private double clamp(double x,double a,double b){return Math.max(a,Math.min(b,x));}
}
