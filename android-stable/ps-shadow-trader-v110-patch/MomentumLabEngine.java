package com.ps.shadowtrader;

import android.content.*;
import org.json.*;
import java.util.*;
import static com.ps.shadowtrader.Models.*;

public final class MomentumLabEngine {
    private static final int BATCH=25;
    private static final long DAY=86400000L;
    private final Context c; private final GrowwClient api; private final EventStore events;
    public MomentumLabEngine(Context c,GrowwClient api){this.c=c;this.api=api;this.events=new EventStore(c);}

    public String scanNextBatch(String token)throws Exception{
        List<String> universe=UniverseRepository.load(c,api);if(universe.isEmpty())return "Universe unavailable";
        android.content.SharedPreferences p=c.getSharedPreferences("momentum",Context.MODE_PRIVATE);int cursor=p.getInt("cursor",0);if(cursor>=universe.size())cursor=0;
        double nifty30=niftyReturn(token);int checked=0,added=0;long end=System.currentTimeMillis()/1000L,start=end-180L*86400L;
        for(int k=0;k<BATCH&&k<universe.size();k++){
            int idx=(cursor+k)%universe.size();String s=universe.get(idx);checked++;
            try{List<Candle> d=api.candles(token,s,start,end,"1day");Candidate x=score(s,d,nifty30);if(x!=null&&x.score>=72){upsertCurrent(p,x);added++;}}catch(Exception ignored){}
        }
        cursor=(cursor+checked)%universe.size();p.edit().putInt("cursor",cursor).putInt("universe_size",universe.size()).putLong("last_scan",System.currentTimeMillis()).putString("market_regime",regime(nifty30)).apply();
        closeExpired(token,p);String msg="Momentum Lab scanned "+checked+" NSE equities • "+added+" candidates • coverage "+cursor+"/"+universe.size();events.add("LAB",msg);return msg;
    }

    private double niftyReturn(String token){try{long end=System.currentTimeMillis()/1000L,start=end-80L*86400L;List<Candle>d=api.candles(token,"NIFTY",start,end,"1day");return ret(d,Math.min(20,d.size()-1));}catch(Exception e){return 0;}}
    private Candidate score(String symbol,List<Candle>d,double nifty30){
        if(d==null||d.size()<90)return null;int n=d.size();double last=d.get(n-1).c;if(last<=0)return null;
        double r20=ret(d,20),r60=ret(d,60),vol=avgVol(d,n-5,n)/Math.max(1,avgVol(d,n-30,n-5));double hi60=0;for(int i=n-61;i<n-1;i++)hi60=Math.max(hi60,d.get(i).h);double breakout=last/Math.max(.01,hi60)-1;double rsi=rsi(d,14);double volatility=volatility(d,20);double relative=r20-nifty30;
        Replay rp=replay(d,r20,r60,vol,breakout,relative);
        double score=50;score+=clamp(r20*100*1.1,-15,20);score+=clamp(r60*100*.35,-12,15);score+=clamp((vol-1)*12,-8,18);score+=clamp(breakout*100*1.5,-8,15);score+=clamp(relative*100*.7,-8,12);
        if(rsi>55&&rsi<78)score+=6; if(rsi>=85)score-=10; if(volatility>.07)score-=8;score+=rp.similarity*12;score=clamp(score,0,99);
        if(score<72)return null;Candidate x=new Candidate();x.symbol=symbol;x.price=last;x.target=last*1.5;x.score=score;x.created=System.currentTimeMillis();x.expiry=x.created+30L*DAY;x.maxSeen=last;x.matches=rp.matches;x.reason=reason(r20,r60,vol,breakout,relative,rp);return x;
    }
    private Replay replay(List<Candle>d,double cr20,double cr60,double cv,double cb,double crel){
        int n=d.size(),matches=0;double best=0;for(int i=65;i<n-31;i++){
            double futureMax=0,base=d.get(i).c;for(int j=i+1;j<=Math.min(n-1,i+30);j++)futureMax=Math.max(futureMax,d.get(j).h/base-1);if(futureMax<.50)continue;matches++;
            double r20=d.get(i).c/d.get(i-20).c-1,r60=d.get(i).c/d.get(i-60).c-1;double v=avgVol(d,i-4,i+1)/Math.max(1,avgVol(d,i-29,i-4));double hi=0;for(int j=i-60;j<i;j++)hi=Math.max(hi,d.get(j).h);double b=d.get(i).c/Math.max(.01,hi)-1;
            double dist=Math.abs(r20-cr20)*4+Math.abs(r60-cr60)*2+Math.abs(v-cv)*.25+Math.abs(b-cb)*3+Math.abs(crel)*.2;best=Math.max(best,Math.exp(-dist));
        }Replay r=new Replay();r.matches=matches;r.similarity=matches==0?0:best;return r;
    }
    private String reason(double r20,double r60,double v,double b,double rel,Replay rp){return String.format(Locale.US,"20d %+,.1f%% • 60d %+,.1f%% • volume %.1fx • breakout %+,.1f%% • relative strength %+,.1f%% • replay matches %d",r20*100,r60*100,v,b*100,rel*100,rp.matches);}
    private void upsertCurrent(android.content.SharedPreferences p,Candidate x){try{JSONArray a=new JSONArray(p.getString("current","[]"));JSONArray b=new JSONArray();boolean found=false;for(int i=0;i<a.length();i++){JSONObject o=a.getJSONObject(i);if(o.optString("symbol").equals(x.symbol)){long created=o.optLong("created",x.created);double max=Math.max(o.optDouble("maxSeen",x.price),x.price);o=toJson(x).put("created",created).put("expiry",created+30L*DAY).put("maxSeen",max);found=true;}b.put(o);}if(!found)b.put(toJson(x));p.edit().putString("current",b.toString()).apply();}catch(Exception ignored){}}
    private void closeExpired(String token,android.content.SharedPreferences p){try{JSONArray a=new JSONArray(p.getString("current","[]")),keep=new JSONArray(),closed=new JSONArray(p.getString("closed","[]"));long now=System.currentTimeMillis();for(int i=0;i<a.length();i++){JSONObject o=a.getJSONObject(i);if(now<o.optLong("expiry")){keep.put(o);continue;}double max=o.optDouble("maxSeen",o.optDouble("price"));try{long st=o.optLong("created")/1000L,en=now/1000L;List<Candle>d=api.candles(token,o.optString("symbol"),st,en,"1day");for(Candle z:d)max=Math.max(max,z.h);}catch(Exception ignored){}o.put("maxSeen",max).put("closed",now).put("success",max>=o.optDouble("target"));closed.put(o);}while(closed.length()>60){JSONArray z=new JSONArray();for(int i=closed.length()-60;i<closed.length();i++)z.put(closed.get(i));closed=z;}p.edit().putString("current",keep.toString()).putString("closed",closed.toString()).apply();}catch(Exception ignored){}}
    private JSONObject toJson(Candidate x)throws Exception{return new JSONObject().put("symbol",x.symbol).put("price",x.price).put("target",x.target).put("score",x.score).put("created",x.created).put("expiry",x.expiry).put("maxSeen",x.maxSeen).put("matches",x.matches).put("reason",x.reason);}
    public static JSONArray current(Context c){try{return new JSONArray(c.getSharedPreferences("momentum",Context.MODE_PRIVATE).getString("current","[]"));}catch(Exception e){return new JSONArray();}}
    public static JSONArray closed(Context c){try{return new JSONArray(c.getSharedPreferences("momentum",Context.MODE_PRIVATE).getString("closed","[]"));}catch(Exception e){return new JSONArray();}}
    private double ret(List<Candle>d,int days){if(d==null||d.size()<days+1)return 0;return d.get(d.size()-1).c/d.get(d.size()-1-days).c-1;}
    private double avgVol(List<Candle>d,int a,int b){a=Math.max(0,a);b=Math.min(d.size(),b);double s=0;int n=0;for(int i=a;i<b;i++){s+=d.get(i).v;n++;}return n==0?0:s/n;}
    private double rsi(List<Candle>d,int p){double g=0,l=0;for(int i=d.size()-p;i<d.size();i++){double x=d.get(i).c-d.get(i-1).c;if(x>=0)g+=x;else l-=x;}return l==0?100:100-100/(1+g/l);}
    private double volatility(List<Candle>d,int p){double m=0;double[]r=new double[p];for(int i=0;i<p;i++){int x=d.size()-p+i;r[i]=d.get(x).c/d.get(x-1).c-1;m+=r[i];}m/=p;double s=0;for(double x:r)s+=(x-m)*(x-m);return Math.sqrt(s/p);}
    private String regime(double x){if(x>.04)return "Strong market";if(x<-.04)return "Weak market";return "Neutral market";}
    private double clamp(double x,double a,double b){return Math.max(a,Math.min(b,x));}
    private static class Candidate{String symbol,reason;double price,target,score,maxSeen;long created,expiry;int matches;}
    private static class Replay{int matches;double similarity;}
}
