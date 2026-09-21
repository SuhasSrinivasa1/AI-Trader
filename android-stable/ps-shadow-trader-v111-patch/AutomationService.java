package com.ps.shadowtrader;

import android.app.*;
import android.content.*;
import android.os.*;
import java.text.*;
import java.util.*;
import static com.ps.shadowtrader.Models.*;

public class AutomationService extends Service {
    public static final String ACTION_PICK="com.ps.shadowtrader.PICK";
    public static final String ACTION_EOD="com.ps.shadowtrader.EOD";
    private static final String CH="ps_auto"; private static final int NID=1917;
    private final Handler h=new Handler(Looper.getMainLooper()); private volatile boolean busy=false;
    private final Runnable tick=new Runnable(){public void run(){if(!busy){busy=true;new Thread(()->{try{cycle();}finally{busy=false;}}).start();}h.postDelayed(this,60000);}};
    @Override public void onCreate(){super.onCreate();createChannel();startForeground(NID,notification("Automation starting…"));Scheduler.schedule(this);h.post(tick);}
    @Override public int onStartCommand(Intent i,int flags,int startId){if(i!=null&&ACTION_EOD.equals(i.getAction()))getSharedPreferences("state",MODE_PRIVATE).edit().putBoolean("force_eod",true).apply();h.removeCallbacks(tick);h.post(tick);return START_STICKY;}
    @Override public void onDestroy(){h.removeCallbacks(tick);super.onDestroy();}
    @Override public android.os.IBinder onBind(Intent i){return null;}

    private void cycle(){
        android.content.SharedPreferences state=getSharedPreferences("state",MODE_PRIVATE);
        String token=ensureToken(state);
        if(token==null||token.isEmpty()){notifyStatus("Groww authentication required");return;}
        long now=System.currentTimeMillis();int hm=hm();boolean weekday=weekday();boolean market=weekday&&hm>=915&&hm<=1520;
        if(market)runIntraday(token,state,now,hm);else runOffMarket(token,state,now,hm);
        TradeState ts=new TradeStateStore(this).load();notifyStatus("AUTO • "+(market?"Market monitoring":"Research/training")+" • "+(ts.side==Side.FLAT?"FLAT":ts.symbol+" "+ts.side)+" • Net ₹"+String.format(Locale.US,"%.0f",ts.pnl()));
    }

    private String ensureToken(android.content.SharedPreferences state){
        SecureStore secure=new SecureStore(this);GrowwClient api=new GrowwClient();long now=System.currentTimeMillis();
        String token=secure.get("token");long lastAuth=state.getLong("last_auth_check",0);boolean due=token.isEmpty()||now-lastAuth>45*60000L;
        if(!due)return token;
        if(!token.isEmpty()){
            try{api.user(token);state.edit().putLong("last_auth_check",now).putBoolean("token_ok",true).putString("engine_status","Automation running").putString("auth_mode",state.getString("auth_mode","Access token")).apply();return token;}
            catch(Exception ignored){}
        }
        String tt=secure.get("totp_token"),secret=secure.get("totp_secret");
        if(!tt.isEmpty()&&!secret.isEmpty()){
            try{
                String code=TotpUtil.now(secret);String fresh=api.generateAccessTokenTotp(tt,code);api.user(fresh);secure.put("token",fresh);
                state.edit().putLong("last_auth_check",now).putBoolean("token_ok",true).putString("engine_status","Automation running").putString("auth_mode","Automatic TOTP").apply();
                new EventStore(this).add("AUTH","Groww access token refreshed automatically using TOTP");
                return fresh;
            }catch(Exception e){state.edit().putBoolean("token_ok",false).putString("engine_status","TOTP authentication needs attention").apply();new EventStore(this).add("AUTH","TOTP authentication failed: "+shortMsg(e));return "";}
        }
        state.edit().putBoolean("token_ok",false).putString("engine_status","Groww authentication required").apply();
        return "";
    }

    private void runIntraday(String token,android.content.SharedPreferences state,long now,int hm){
        TradeStateStore store=new TradeStateStore(this);TradeState ts=store.load();GrowwClient api=new GrowwClient();EventStore events=new EventStore(this);
        if(hm>=1520&&ts.side!=Side.FLAT){try{double px=api.ltp(token,ts.symbol);String a=new TradeSimulator().forceExit(ts,px,"intraday time exit");store.save(ts);events.add("TRADE",a);}catch(Exception ignored){}return;}
        String symbol=ts.side!=Side.FLAT?ts.symbol:state.getString("last_symbol","");long pick=state.getLong("last_pick_ts",0);if(symbol.isEmpty()||(ts.side==Side.FLAT&&now-pick>8L*3600000L))return;
        long last=state.getLong("last_analysis_ts",0);long processed=state.getLong("processed_pick_ts",0);if(now-last<5*60000L&&pick<=processed)return;
        if(hm>=1500&&ts.side==Side.FLAT){events.add("GUARD","New entry blocked after 15:00; monitoring only");state.edit().putLong("last_analysis_ts",now).apply();return;}
        try{
            long end=now/1000L,start=end-3L*86400L;List<Candle> c=api.candles(token,symbol,start,end,"5minute");List<Candle> n=api.candles(token,"NIFTY",start,end,"5minute");double nr=seriesReturn(n);double px=api.ltp(token,symbol);ModelConfig cfg=new ModelConfig(this);Signal sig=new StrategyEngine().evaluate(c,nr,cfg.entryThreshold());String action=new TradeSimulator().apply(ts,symbol,sig,px,cfg.reversalThreshold());store.save(ts);
            StringBuilder reasons=new StringBuilder();for(String r:sig.reasons){if(reasons.length()>0)reasons.append(" • ");reasons.append(r);}
            state.edit().putLong("last_analysis_ts",now).putLong("processed_pick_ts",pick).putString("last_signal",sig.side.name()).putString("last_action",action).putString("last_reasons",reasons.toString()).putFloat("last_score",(float)sig.score).putFloat("nifty_return",(float)nr).apply();
            events.add("TRADE",symbol+" • "+action+" • score "+String.format(Locale.US,"%.2f",sig.score));
        }catch(Exception e){state.edit().putString("engine_status","Analysis retry scheduled").apply();events.add("ERROR","Analysis retry: "+shortMsg(e));}
    }

    private void runOffMarket(String token,android.content.SharedPreferences state,long now,int hm){
        TradeStateStore store=new TradeStateStore(this);TradeState ts=store.load();long day=dayKey();boolean force=state.getBoolean("force_eod",false);long eodDay=state.getLong("last_eod_day",-1);
        if((force||(hm>=1545&&hm<=2359))&&eodDay!=day){String s=TrainingEngine.run(this,ts.pnl());state.edit().putLong("last_eod_day",day).putBoolean("force_eod",false).putString("last_training_summary",s).apply();}
        long lastLab=state.getLong("last_lab_ts",0);if((hm>=1600||hm<600)&&now-lastLab>=30*60000L){
            try{String x=new MomentumLabEngine(this,new GrowwClient()).scanNextBatch(token);state.edit().putLong("last_lab_ts",now).putString("last_lab_status",x).apply();}catch(Exception e){new EventStore(this).add("LAB","Scan retry: "+shortMsg(e));state.edit().putLong("last_lab_ts",now).apply();}
        }
    }
    private double seriesReturn(List<Candle>x){if(x==null||x.size()<2)return 0;double a=x.get(Math.max(0,x.size()-20)).c,b=x.get(x.size()-1).c;return a==0?0:b/a-1;}
    private int hm(){Calendar c=Calendar.getInstance();return c.get(Calendar.HOUR_OF_DAY)*100+c.get(Calendar.MINUTE);}
    private boolean weekday(){int d=Calendar.getInstance().get(Calendar.DAY_OF_WEEK);return d!=Calendar.SATURDAY&&d!=Calendar.SUNDAY;}
    private long dayKey(){Calendar c=Calendar.getInstance();return c.get(Calendar.YEAR)*1000L+c.get(Calendar.DAY_OF_YEAR);}
    private String shortMsg(Exception e){String s=e.getMessage();if(s==null)s=e.getClass().getSimpleName();return s.length()>100?s.substring(0,100):s;}
    private void createChannel(){if(Build.VERSION.SDK_INT>=26){NotificationChannel c=new NotificationChannel(CH,"PS Automation",NotificationManager.IMPORTANCE_LOW);c.setDescription("Keeps shadow analysis and research automation active");((NotificationManager)getSystemService(NOTIFICATION_SERVICE)).createNotificationChannel(c);}}
    private Notification notification(String text){Intent i=new Intent(this,MainActivity.class);PendingIntent pi=PendingIntent.getActivity(this,0,i,PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE);return new Notification.Builder(this,Build.VERSION.SDK_INT>=26?CH:null).setSmallIcon(android.R.drawable.stat_notify_sync).setContentTitle("PS Shadow Trader").setContentText(text).setOngoing(true).setContentIntent(pi).build();}
    private void notifyStatus(String text){((NotificationManager)getSystemService(NOTIFICATION_SERVICE)).notify(NID,notification(text));}
}
