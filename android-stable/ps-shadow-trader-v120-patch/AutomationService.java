package com.ps.shadowtrader;

import android.app.*;
import android.content.*;
import android.os.*;
import java.util.*;
import static com.ps.shadowtrader.Models.*;

public class AutomationService extends Service {
    public static final String ACTION_PICK="com.ps.shadowtrader.PICK";
    public static final String ACTION_EOD="com.ps.shadowtrader.EOD";
    private static final String CH="ps_auto"; private static final int NID=1917;
    private final Handler h=new Handler(Looper.getMainLooper());
    private volatile boolean busy=false;
    private final Map<String,ArrayList<Double>> micro=new HashMap<>();
    private final Map<String,List<Candle>> candleCache=new HashMap<>();
    private final Map<String,Long> candleTs=new HashMap<>();
    private Map<String,Double> lastPrices=new HashMap<>();

    private final Runnable tick=new Runnable(){
        public void run(){
            if(!busy){busy=true;new Thread(()->{try{cycle();}finally{busy=false;}}).start();}
            h.postDelayed(this,nextDelay());
        }
    };

    @Override public void onCreate(){
        super.onCreate();createChannel();startForeground(NID,notification("Adaptive engine starting…"));Scheduler.schedule(this);h.post(tick);
    }
    @Override public int onStartCommand(Intent i,int flags,int startId){
        if(i!=null&&ACTION_EOD.equals(i.getAction()))getSharedPreferences("state",MODE_PRIVATE).edit().putBoolean("force_eod",true).apply();
        h.removeCallbacks(tick);h.post(tick);return START_STICKY;
    }
    @Override public void onDestroy(){h.removeCallbacks(tick);super.onDestroy();}
    @Override public android.os.IBinder onBind(Intent i){return null;}

    private long nextDelay(){int hm=hm();return weekday()&&hm>=915&&hm<=1520?2000L:60000L;}

    private void cycle(){
        android.content.SharedPreferences state=getSharedPreferences("state",MODE_PRIVATE);
        String token=ensureToken(state);
        if(token==null||token.isEmpty()){notifyStatus("Groww authentication required");return;}

        long now=System.currentTimeMillis();int hm=hm();boolean market=weekday()&&hm>=915&&hm<=1520;
        if(market)runAdaptiveMarket(token,state,now,hm); else runOffMarket(token,state,now,hm);

        TradeState ts=new TradeStateStore(this).load();
        AdaptiveModel model=new AdaptiveModel(this);
        notifyStatus("ADAPTIVE • "+(market?"2s market loop":"Research/training")+" • "+(ts.side==Side.FLAT?"FLAT":ts.symbol+" "+ts.side)+" • Net ₹"+String.format(Locale.US,"%.0f",ts.pnl())+" • learned "+model.trades());
    }

    private String ensureToken(android.content.SharedPreferences state){
        SecureStore secure=new SecureStore(this);GrowwClient api=new GrowwClient();long now=System.currentTimeMillis();
        String token=secure.get("token");long lastAuth=state.getLong("last_auth_check",0);boolean due=token.isEmpty()||now-lastAuth>45*60000L;
        if(!due)return token;

        if(!token.isEmpty()){
            try{
                api.user(token);
                state.edit().putLong("last_auth_check",now).putBoolean("token_ok",true).putString("engine_status","Adaptive automation running").putString("auth_mode",state.getString("auth_mode","Access token")).apply();
                return token;
            }catch(Exception ignored){}
        }

        String tt=secure.get("totp_token"),secret=secure.get("totp_secret");
        if(!tt.isEmpty()&&!secret.isEmpty()){
            try{
                String code=TotpUtil.now(secret);String fresh=api.generateAccessTokenTotp(tt,code);api.user(fresh);secure.put("token",fresh);
                state.edit().putLong("last_auth_check",now).putBoolean("token_ok",true).putString("engine_status","Adaptive automation running").putString("auth_mode","Automatic TOTP").apply();
                new EventStore(this).add("AUTH","Groww token refreshed automatically using TOTP");
                return fresh;
            }catch(Exception e){
                state.edit().putBoolean("token_ok",false).putString("engine_status","TOTP authentication needs attention").apply();
                new EventStore(this).add("AUTH","TOTP authentication failed: "+shortMsg(e));return "";
            }
        }
        state.edit().putBoolean("token_ok",false).putString("engine_status","Groww authentication required").apply();return "";
    }

    private void runAdaptiveMarket(String token,android.content.SharedPreferences state,long now,int hm){
        GrowwClient api=new GrowwClient();
        WatchlistStore wl=new WatchlistStore(this);
        List<String> symbols=wl.symbols();
        TradeStateStore store=new TradeStateStore(this);TradeState ts=store.load();
        if(ts.side!=Side.FLAT&&!symbols.contains(ts.symbol))symbols.add(0,ts.symbol);
        while(symbols.size()>3)symbols.remove(symbols.size()-1);

        if(symbols.isEmpty()){
            state.edit().putString("engine_status","Adaptive engine ready • waiting for Multify").apply();
            return;
        }

        if(hm>=1520){
            if(ts.side!=Side.FLAT){
                try{
                    Map<String,Double> p=api.ltps(token,Collections.singletonList(ts.symbol));Double px=p.get(ts.symbol);
                    if(px!=null&&!Double.isNaN(px)){
                        String a=new AdaptiveTradeController(new AdaptiveModel(this)).forceExit(ts,px,"intraday market-close guard");
                        store.save(ts);new EventStore(this).add("TRADE",a);
                    }
                }catch(Exception ignored){}
            }
            return;
        }

        try{
            ArrayList<String> request=new ArrayList<>(symbols);if(!request.contains("NIFTY"))request.add("NIFTY");
            Map<String,Double> prices=api.ltps(token,request);lastPrices=prices;
            for(Map.Entry<String,Double>e:prices.entrySet())if(e.getValue()!=null&&!Double.isNaN(e.getValue()))appendMicro(e.getKey(),e.getValue());

            if(now-state.getLong("last_candle_refresh",0)>30000L || missingCandles(symbols)){
                long end=now/1000L,start=end-2L*86400L;
                for(String s:symbols){
                    try{List<Candle>c=api.candles(token,s,start,end,"1minute");if(c!=null&&!c.isEmpty()){candleCache.put(s,c);candleTs.put(s,now);}}catch(Exception ignored){}
                }
                state.edit().putLong("last_candle_refresh",now).apply();
            }

            double niftyMicro=microReturn(micro.get("NIFTY"),30);
            AdaptiveModel model=new AdaptiveModel(this);AdaptiveBrain brain=new AdaptiveBrain(model);
            ArrayList<AdaptiveBrain.Decision> decisions=new ArrayList<>();
            for(String s:symbols){
                List<Candle> c=candleCache.get(s);
                AdaptiveBrain.Decision d=brain.evaluate(s,c,micro.get(s),niftyMicro);
                decisions.add(d);
            }
            Collections.sort(decisions,(a,b)->Double.compare(b.opportunity(),a.opportunity()));
            AdaptiveBrain.Decision best=decisions.isEmpty()?null:decisions.get(0);

            if(hm>=1515 && ts.side==Side.FLAT){
                state.edit().putString("last_action","Late-session guard: no new intraday position").putLong("last_analysis_ts",now).apply();
                return;
            }

            String action=new AdaptiveTradeController(model).act(ts,best,prices);
            store.save(ts);

            StringBuilder board=new StringBuilder();
            for(int i=0;i<decisions.size();i++){
                AdaptiveBrain.Decision d=decisions.get(i);
                if(i>0)board.append(" | ");
                board.append(d.symbol).append(" ").append(d.side).append(" ").append(String.format(Locale.US,"%.0f%%",d.confidence*100))
                        .append(" edge ").append(String.format(Locale.US,"%.2f%%",Math.max(0,d.expectedMovePct-d.requiredEdgePct)*100));
            }
            StringBuilder reasons=new StringBuilder();
            if(best!=null)for(String r:best.reasons){if(reasons.length()>0)reasons.append(" • ");reasons.append(r);}
            state.edit().putString("engine_status","Adaptive 2-second decision loop")
                    .putString("adaptive_watchlist",wl.display())
                    .putString("adaptive_board",board.toString())
                    .putString("last_signal",best==null?"WAIT":best.side.name())
                    .putFloat("last_score",(float)(best==null?0:best.score))
                    .putFloat("last_confidence",(float)(best==null?0:best.confidence))
                    .putFloat("last_edge",(float)(best==null?0:Math.max(0,best.expectedMovePct-best.requiredEdgePct)))
                    .putString("last_action",action).putString("last_reasons",reasons.toString())
                    .putFloat("nifty_return",(float)niftyMicro).putLong("last_analysis_ts",now).apply();

            long lastLog=state.getLong("last_adaptive_log",0);
            if(now-lastLog>15000L || action.startsWith("SIMULATED") || action.startsWith("ROTATE")){
                new EventStore(this).add("ADAPT",action+" • "+(best==null?"no candidate":best.symbol+" conf "+String.format(Locale.US,"%.0f%%",best.confidence*100)));
                state.edit().putLong("last_adaptive_log",now).apply();
            }
        }catch(Exception e){
            state.edit().putString("engine_status","Adaptive loop retry scheduled").apply();
            long last=state.getLong("last_error_log",0);
            if(now-last>30000L){new EventStore(this).add("ERROR","Adaptive loop: "+shortMsg(e));state.edit().putLong("last_error_log",now).apply();}
        }
    }

    private void runOffMarket(String token,android.content.SharedPreferences state,long now,int hm){
        TradeState ts=new TradeStateStore(this).load();long day=dayKey();boolean force=state.getBoolean("force_eod",false);long eodDay=state.getLong("last_eod_day",-1);
        if((force||(hm>=1545&&hm<=2359))&&eodDay!=day){
            String base=TrainingEngine.run(this,ts.pnl());
            AdaptiveModel m=new AdaptiveModel(this);
            String summary=base+"\nAdaptive brain: "+m.summary();
            state.edit().putLong("last_eod_day",day).putBoolean("force_eod",false).putString("last_training_summary",summary).apply();
            new EventStore(this).add("TRAIN","EOD adaptive calibration complete • "+m.summary().replace("\n"," "));
        }
        long lastLab=state.getLong("last_lab_ts",0);
        if((hm>=1600||hm<600)&&now-lastLab>=30*60000L){
            try{
                String x=new MomentumLabEngine(this,new GrowwClient()).scanNextBatch(token);
                state.edit().putLong("last_lab_ts",now).putString("last_lab_status",x).apply();
            }catch(Exception e){new EventStore(this).add("LAB","Scan retry: "+shortMsg(e));state.edit().putLong("last_lab_ts",now).apply();}
        }
    }

    private boolean missingCandles(List<String>s){for(String x:s)if(!candleCache.containsKey(x)||candleCache.get(x)==null||candleCache.get(x).size()<35)return true;return false;}
    private void appendMicro(String s,double p){ArrayList<Double>x=micro.get(s);if(x==null){x=new ArrayList<>();micro.put(s,x);}x.add(p);while(x.size()>180)x.remove(0);}
    private double microReturn(List<Double>x,int n){if(x==null||x.size()<2)return 0;int z=x.size();int a=Math.max(0,z-Math.max(2,n));double p=x.get(a),q=x.get(z-1);return p==0?0:q/p-1;}
    private int hm(){Calendar c=Calendar.getInstance();return c.get(Calendar.HOUR_OF_DAY)*100+c.get(Calendar.MINUTE);}
    private boolean weekday(){int d=Calendar.getInstance().get(Calendar.DAY_OF_WEEK);return d!=Calendar.SATURDAY&&d!=Calendar.SUNDAY;}
    private long dayKey(){Calendar c=Calendar.getInstance();return c.get(Calendar.YEAR)*1000L+c.get(Calendar.DAY_OF_YEAR);}
    private String shortMsg(Exception e){String s=e.getMessage();if(s==null)s=e.getClass().getSimpleName();return s.length()>100?s.substring(0,100):s;}
    private void createChannel(){if(Build.VERSION.SDK_INT>=26){NotificationChannel c=new NotificationChannel(CH,"PS Adaptive Automation",NotificationManager.IMPORTANCE_LOW);c.setDescription("Keeps adaptive shadow analysis and research active");((NotificationManager)getSystemService(NOTIFICATION_SERVICE)).createNotificationChannel(c);}}
    private Notification notification(String text){Intent i=new Intent(this,MainActivity.class);PendingIntent pi=PendingIntent.getActivity(this,0,i,PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE);return new Notification.Builder(this,Build.VERSION.SDK_INT>=26?CH:null).setSmallIcon(android.R.drawable.stat_notify_sync).setContentTitle("PS Shadow Trader").setContentText(text).setOngoing(true).setContentIntent(pi).build();}
    private void notifyStatus(String text){((NotificationManager)getSystemService(NOTIFICATION_SERVICE)).notify(NID,notification(text));}
}
