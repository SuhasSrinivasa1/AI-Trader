package com.suhas.nseunifiedscanner;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;

public class UnifiedService extends Service {
    static final String ACTION_START="scanner.START", ACTION_STOP="scanner.STOP", ACTION_SCAN="scanner.SCAN", ACTION_BUY="scanner.BUY", ACTION_EXIT="scanner.EXIT", ACTION_AUTH="scanner.AUTH";
    static final String EXTRA_SYMBOL="symbol";
    private static final int NOTIFY_ID=27101; private static final String CHANNEL="nse_scanner_live";
    private final ExecutorService scanWork=Executors.newSingleThreadExecutor();
    private final ExecutorService tradeWork=Executors.newSingleThreadExecutor();
    private final Handler handler=new Handler(Looper.getMainLooper());
    private final AtomicBoolean scanning=new AtomicBoolean(false), trading=new AtomicBoolean(false), monitoring=new AtomicBoolean(false);
    private ScannerEngine scanner; private LearningStore learning;

    @Override public void onCreate(){super.onCreate();scanner=new ScannerEngine(this);learning=new LearningStore(this);createChannel();startForeground(NOTIFY_ID,notification("Scanner ready • live trading off until armed"));handler.post(monitorLoop);}
    @Override public IBinder onBind(Intent intent){return null;}

    @Override public int onStartCommand(Intent intent,int flags,int startId){
        String a=intent==null?ACTION_START:intent.getAction(); if(a==null)a=ACTION_START;
        if(ACTION_STOP.equals(a)){prefs().edit().putBoolean("scanner_enabled",false).apply();stopSelf();return START_NOT_STICKY;}
        if(ACTION_AUTH.equals(a)){scanWork.execute(()->authenticate(true));return START_STICKY;}
        if(ACTION_SCAN.equals(a)){requestScan(true);return START_STICKY;}
        if(ACTION_BUY.equals(a)){String s=intent.getStringExtra(EXTRA_SYMBOL);if(s!=null)tradeWork.execute(()->buy(s));return START_STICKY;}
        if(ACTION_EXIT.equals(a)){tradeWork.execute(()->exitActive("MANUAL"));return START_STICKY;}
        prefs().edit().putBoolean("scanner_enabled",true).apply(); requestScan(true); scheduleNextScan(); return START_STICKY;
    }

    private void requestScan(boolean manual){
        if(!scanning.compareAndSet(false,true))return;
        scanWork.execute(()->{try{
            if(!manual && !ScannerEngine.marketHoursNow()) { setStatus("Market closed • next scan during NSE hours"); return; }
            String token=ensureToken(false); if(token.isEmpty()){setStatus("Groww authentication required • scanner paused");return;}
            setStatus("Scanning NSE…"); ScannerEngine.ScanResult r=scanner.scan(token); if(r.error==null||r.error.isEmpty())setStatus("Scan complete • "+r.marketLabel+" • "+r.recommendations.size()+" candidates");else setStatus("Scan error • "+r.error);
        }finally{scanning.set(false);}});
    }

    private void scheduleNextScan(){
        handler.removeCallbacks(scanLoop); if(!prefs().getBoolean("scanner_enabled",true))return;
        long now=System.currentTimeMillis(); long five=5*60_000L; long next=((now/five)+1)*five+7_000L; handler.postDelayed(scanLoop,Math.max(10_000L,next-now));
    }
    private final Runnable scanLoop=new Runnable(){@Override public void run(){if(prefs().getBoolean("scanner_enabled",true))requestScan(false);scheduleNextScan();}};

    private synchronized String ensureToken(boolean force){
        String today=LocalDate.now(ScannerEngine.IST).toString(); String token=SecureStore.get(this,SecureStore.ACCESS_TOKEN);String day=SecureStore.get(this,SecureStore.ACCESS_DAY);
        if(today.equals(day)&&!token.isEmpty())return token;
        long last=prefs().getLong("last_auth_attempt",0);if(!force&&System.currentTimeMillis()-last<30*60_000L)return "";
        return authenticate(force);
    }

    private synchronized String authenticate(boolean force){
        prefs().edit().putLong("last_auth_attempt",System.currentTimeMillis()).apply(); String api=SecureStore.get(this,SecureStore.API_KEY),secret=SecureStore.get(this,SecureStore.TOTP_SECRET);
        GrowwApi.Result<String> a=GrowwApi.authenticate(api,secret);if(!a.ok){setStatus("Groww auth failed • "+a.error);learning.audit("AUTH",a.error);return "";}
        GrowwApi.Result<String> v=GrowwApi.verifyProfile(a.value);if(!v.ok){setStatus("Groww profile check failed • "+v.error);learning.audit("AUTH",v.error);return "";}
        try{SecureStore.put(this,SecureStore.ACCESS_TOKEN,a.value);SecureStore.put(this,SecureStore.ACCESS_DAY,LocalDate.now(ScannerEngine.IST).toString());}catch(Exception e){setStatus("Could not securely save Groww token");return "";}
        setStatus("Groww authenticated • NSE ready");learning.audit("AUTH","Groww authenticated");return a.value;
    }

    private void buy(String symbol){
        if(!trading.compareAndSet(false,true))return;try{
            if(!prefs().getBoolean("live_armed",false)){setStatus("BUY blocked • Live Trading is OFF");return;}
            LocalDateTime now=LocalDateTime.now(ScannerEngine.IST);if(now.toLocalTime().isAfter(LocalTime.of(14,40))||now.toLocalTime().isBefore(LocalTime.of(9,15))){setStatus("BUY blocked • entries allowed 09:15–14:40 IST");return;}
            if(ActiveTrade.load(this)!=null){setStatus("BUY blocked • one active position at a time");return;}
            ScannerEngine.ScanResult state=ScannerEngine.state(this);ScannerEngine.Recommendation rec=null;for(ScannerEngine.Recommendation r:state.recommendations)if(symbol.equals(r.symbol)){rec=r;break;}
            if(rec==null||!rec.qualified){setStatus("BUY blocked • recommendation is not qualified");return;}
            if(System.currentTimeMillis()-rec.scanMs>150_000L){setStatus("BUY blocked • recommendation is stale; refresh scan");return;}
            String token=ensureToken(false);if(token.isEmpty()){setStatus("BUY blocked • Groww authentication required");return;}
            String configured=SecureStore.get(this,SecureStore.DEDICATED_IP);if(configured.isEmpty()){setStatus("BUY blocked • save your Groww-whitelisted Dedicated IP");return;}
            String publicIp=publicIp();if(publicIp.isEmpty()||!configured.equals(publicIp)){setStatus("BUY blocked • public IP does not match Groww-whitelisted IP");return;}

            GrowwApi.Result<GrowwApi.Quote> qr=GrowwApi.quote(token,rec.symbol);if(!qr.ok){setStatus("BUY blocked • "+qr.error);return;}double ltp=qr.value.ltp;
            if(!(ltp>0)||ltp>rec.entry*1.0020){setStatus("BUY blocked • price moved >0.20% above scanner entry; no chasing");return;}
            double limit=GrowwApi.roundToTick(Math.min(rec.entry*1.0020,ltp*1.0006),rec.tick,true);
            GrowwApi.Result<GrowwApi.Margin> mr=GrowwApi.availableMargin(token);if(!mr.ok){setStatus("BUY blocked • "+mr.error);return;}
            double use=Math.max(0.50,Math.min(1.00,prefs().getFloat("capital_use",0.98f)));double budget=mr.value.misAvailable*use;
            int qty=maxQuantity(token,rec.symbol,limit,budget);if(qty<1){setStatus("BUY blocked • insufficient MIS margin");return;}
            String ref=GrowwApi.reference("UB",rec.symbol);GrowwApi.Result<GrowwApi.Order> br=GrowwApi.placeLimitBuy(token,rec.symbol,qty,limit,ref);if(!br.ok){setStatus("BUY failed • "+br.error);learning.audit("ORDER",rec.symbol+" BUY failed: "+br.error);return;}
            setStatus(rec.symbol+" BUY sent • reconciling fill");GrowwApi.Order fill=null;
            for(int i=0;i<18;i++){sleep(220);GrowwApi.Result<GrowwApi.Order> d=GrowwApi.orderDetail(token,br.value.id);if(!d.ok)continue;if(d.value.filledQuantity>0){fill=d.value;if(d.value.remainingQuantity>0)GrowwApi.cancelOrder(token,br.value.id);break;}if(isTerminal(d.value.status))break;}
            if(fill==null||fill.filledQuantity<=0){GrowwApi.cancelOrder(token,br.value.id);setStatus(rec.symbol+" not filled • order cancelled; no position opened");learning.audit("ORDER",rec.symbol+" no fill");return;}
            sleep(300);GrowwApi.Result<GrowwApi.Order> finalD=GrowwApi.orderDetail(token,br.value.id);if(finalD.ok&&finalD.value.filledQuantity>0)fill=finalD.value;
            int filled=fill.filledQuantity;double fillPrice=fill.averageFillPrice>0?fill.averageFillPrice:limit;
            double target=ChargeModel.requiredSellPrice(fillPrice,filled,0.005,0.0007,rec.tick);double structural=Math.max(rec.stop,fillPrice*(1-0.0045));double stop=GrowwApi.roundToTick(Math.min(fillPrice-rec.tick,structural),rec.tick,false);
            if((target-fillPrice)/Math.max(rec.tick,fillPrice-stop)<1.35){stop=GrowwApi.roundToTick(fillPrice-(target-fillPrice)/1.45,rec.tick,false);}
            long deadline=Math.min(System.currentTimeMillis()+30*60_000L,todayAt(15,10));
            ActiveTrade t=new ActiveTrade();t.symbol=rec.symbol;t.qty=filled;t.fillPrice=fillPrice;t.target=target;t.stop=stop;t.startedMs=System.currentTimeMillis();t.deadlineMs=deadline;t.buyOrderId=br.value.id;t.tick=rec.tick;t.mode="PENDING_PROTECTION";
            t.save(this); learning.audit("ORDER",rec.symbol+" filled; protection pending");
            GrowwApi.Result<GrowwApi.SmartOrder> oco=GrowwApi.placeCashMisOco(token,rec.symbol,filled,target,stop,GrowwApi.reference("UO",rec.symbol));
            if(oco.ok){t.mode="OCO";t.protectionId=oco.value.id;setStatus(rec.symbol+" LIVE • OCO target/SL ACTIVE • target ₹"+money(target));}
            else {GrowwApi.Result<GrowwApi.Order> sl=GrowwApi.placeSlM(token,rec.symbol,filled,stop,GrowwApi.reference("US",rec.symbol));if(!sl.ok){
                GrowwApi.Result<GrowwApi.Order> emergency=GrowwApi.placeMarketSell(token,rec.symbol,filled,GrowwApi.reference("UE",rec.symbol));
                setStatus("PROTECTION FAILED • emergency exit "+(emergency.ok?"submitted":"FAILED: "+emergency.error));
                learning.audit("CRITICAL",rec.symbol+" protection failed; emergency exit");
                if(emergency.ok){for(int i=0;i<8;i++){sleep(250);GrowwApi.Result<Integer> z=GrowwApi.positionQuantity(token,rec.symbol);if(z.ok&&z.value<=0){t.clear(this);break;}}}
                return;
            }t.mode="SLM";t.protectionId=sl.value.id;setStatus(rec.symbol+" LIVE • SL-M protected • app target ₹"+money(target));}
            t.save(this);learning.markBought(rec.symbol);learning.audit("ORDER",rec.symbol+" fill "+filled+" @ ₹"+money(fillPrice)+" • target ₹"+money(target)+" • stop ₹"+money(stop)+" • "+t.mode);updateNotification();
        }finally{trading.set(false);}}

    private int maxQuantity(String token,String symbol,double price,double budget){
        if(!(budget>price*0.1))return 0;int high=(int)Math.max(1,Math.min(100000,Math.floor((budget*5.0)/price)));int lo=0,hi=high;
        for(int i=0;i<16&&lo<hi;i++){int mid=(lo+hi+1)/2;GrowwApi.Result<Double> r=GrowwApi.requiredMisMargin(token,symbol,mid,price);if(!r.ok){hi=mid-1;continue;}if(r.value<=budget)lo=mid;else hi=mid-1;}return lo;
    }

    private final Runnable monitorLoop=new Runnable(){@Override public void run(){
        if(monitoring.compareAndSet(false,true)) tradeWork.execute(()->{try{monitorActive();}finally{monitoring.set(false);}});
        handler.postDelayed(this,2000);
    }};
    private void monitorActive(){
        ActiveTrade t=ActiveTrade.load(this);if(t==null)return;String token=ensureToken(false);if(token.isEmpty())return;
        GrowwApi.Result<Integer> pq=GrowwApi.positionQuantity(token,t.symbol);if(pq.ok&&pq.value<=0){t.clear(this);setStatus(t.symbol+" position closed • learning engine will resolve outcome");learning.audit("EXIT",t.symbol+" position zero");return;}
        long now=System.currentTimeMillis();if(now>=t.deadlineMs){exitActive("30-MIN TIME EXIT");return;}
        if("PENDING_PROTECTION".equals(t.mode)){
            int qty=pq.ok?Math.max(0,pq.value):t.qty;
            if(qty<=0){t.clear(this);return;}
            GrowwApi.Result<GrowwApi.Order> sl=GrowwApi.placeSlM(token,t.symbol,qty,t.stop,GrowwApi.reference("UR",t.symbol));
            if(sl.ok){t.mode="SLM";t.protectionId=sl.value.id;t.qty=qty;t.save(this);setStatus(t.symbol+" protection recovered • SL-M ACTIVE");}
            else {setStatus("CRITICAL • "+t.symbol+" protection recovery failed; exiting");exitActive("UNPROTECTED RECOVERY");}
            return;
        }
        if("OCO".equals(t.mode)){GrowwApi.Result<GrowwApi.SmartOrder>s=GrowwApi.smartStatus(token,"OCO",t.protectionId);if(s.ok&&("COMPLETED".equalsIgnoreCase(s.value.status)||"TRIGGERED".equalsIgnoreCase(s.value.status))){sleep(250);GrowwApi.Result<Integer> q=GrowwApi.positionQuantity(token,t.symbol);if(q.ok&&q.value<=0){t.clear(this);setStatus(t.symbol+" OCO exit completed");learning.audit("EXIT",t.symbol+" OCO completed");}}}
        else if("SLM".equals(t.mode)){GrowwApi.Result<java.util.Map<String,Double>> lr=GrowwApi.ltpBatch(token,java.util.Collections.singletonList(t.symbol));if(lr.ok){Double l=lr.value.get(t.symbol);if(l!=null&&l>=t.target)exitActive("TARGET");}}
    }

    private void exitActive(String why){
        if(!trading.compareAndSet(false,true))return;try{ActiveTrade t=ActiveTrade.load(this);if(t==null)return;String token=ensureToken(false);if(token.isEmpty()){setStatus("EXIT pending • Groww auth unavailable; broker protection remains");return;}
            if("OCO".equals(t.mode)&&t.protectionId!=null&&!t.protectionId.isEmpty())GrowwApi.cancelSmart(token,"OCO",t.protectionId);else if("SLM".equals(t.mode)&&t.protectionId!=null&&!t.protectionId.isEmpty())GrowwApi.cancelOrder(token,t.protectionId);
            sleep(300);GrowwApi.Result<Integer> q=GrowwApi.positionQuantity(token,t.symbol);int qty=q.ok?Math.max(0,q.value):t.qty;if(qty>0){GrowwApi.Result<GrowwApi.Order> s=GrowwApi.placeMarketSell(token,t.symbol,qty,GrowwApi.reference("UX",t.symbol));if(!s.ok){setStatus("EXIT FAILED • "+t.symbol+" • "+s.error);learning.audit("CRITICAL",t.symbol+" exit failed: "+s.error);return;}setStatus(t.symbol+" market exit submitted • "+why);}else setStatus(t.symbol+" already flat • "+why);
            for(int i=0;i<8;i++){sleep(250);GrowwApi.Result<Integer> z=GrowwApi.positionQuantity(token,t.symbol);if(z.ok&&z.value<=0){t.clear(this);learning.audit("EXIT",t.symbol+" • "+why);break;}}updateNotification();
        }finally{trading.set(false);}}

    private static boolean isTerminal(String s){return "REJECTED".equalsIgnoreCase(s)||"FAILED".equalsIgnoreCase(s)||"CANCELLED".equalsIgnoreCase(s)||"EXECUTED".equalsIgnoreCase(s)||"COMPLETED".equalsIgnoreCase(s);}
    private long todayAt(int h,int m){return LocalDate.now(ScannerEngine.IST).atTime(h,m).atZone(ScannerEngine.IST).toInstant().toEpochMilli();}
    private void sleep(long ms){try{Thread.sleep(ms);}catch(InterruptedException e){Thread.currentThread().interrupt();}}

    private String publicIp(){HttpURLConnection c=null;try{c=(HttpURLConnection)new URL("https://api.ipify.org").openConnection();c.setConnectTimeout(4000);c.setReadTimeout(4000);c.setRequestProperty("User-Agent","NSEUnifiedScanner/1.0");try(BufferedReader b=new BufferedReader(new InputStreamReader(c.getInputStream()))){return b.readLine().trim();}}catch(Exception e){return "";}finally{if(c!=null)c.disconnect();}}
    private SharedPreferences prefs(){return getSharedPreferences("scanner_prefs",Context.MODE_PRIVATE);}
    private void setStatus(String s){prefs().edit().putString("service_status",s).putLong("service_status_ms",System.currentTimeMillis()).apply();learning.audit("STATUS",s);updateNotification();}
    private void updateNotification(){NotificationManager n=(NotificationManager)getSystemService(NOTIFICATION_SERVICE);n.notify(NOTIFY_ID,notification(prefs().getString("service_status","NSE Unified Scanner running")));}
    private Notification notification(String text){Intent open=new Intent(this,MainActivity.class);PendingIntent pi=PendingIntent.getActivity(this,0,open,PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE);Notification.Builder b=Build.VERSION.SDK_INT>=26?new Notification.Builder(this,CHANNEL):new Notification.Builder(this);return b.setContentTitle("NSE Unified Scanner").setContentText(text).setSmallIcon(android.R.drawable.ic_menu_sort_by_size).setContentIntent(pi).setOngoing(true).build();}
    private void createChannel(){if(Build.VERSION.SDK_INT>=26){NotificationChannel c=new NotificationChannel(CHANNEL,"NSE Unified Scanner",NotificationManager.IMPORTANCE_LOW);c.setDescription("5-minute NSE scans and active intraday protection");((NotificationManager)getSystemService(NOTIFICATION_SERVICE)).createNotificationChannel(c);}}
    @Override public void onDestroy(){handler.removeCallbacksAndMessages(null);scanWork.shutdownNow();tradeWork.shutdownNow();super.onDestroy();}

    private static String money(double d){return String.format(Locale.US,"%.2f",d);}
}

final class ActiveTrade {
    String symbol,mode,protectionId,buyOrderId;int qty;double fillPrice,target,stop,tick;long startedMs,deadlineMs;
    void save(Context c){c.getSharedPreferences("active_trade",Context.MODE_PRIVATE).edit().putString("json",toJson().toString()).apply();}
    void clear(Context c){c.getSharedPreferences("active_trade",Context.MODE_PRIVATE).edit().remove("json").apply();}
    static ActiveTrade load(Context c){String s=c.getSharedPreferences("active_trade",Context.MODE_PRIVATE).getString("json","");if(s.isEmpty())return null;try{return fromJson(new JSONObject(s));}catch(Exception e){return null;}}
    JSONObject toJson(){JSONObject o=new JSONObject();try{o.put("symbol",symbol);o.put("mode",mode);o.put("protectionId",protectionId);o.put("buyOrderId",buyOrderId);o.put("qty",qty);o.put("fillPrice",fillPrice);o.put("target",target);o.put("stop",stop);o.put("tick",tick);o.put("startedMs",startedMs);o.put("deadlineMs",deadlineMs);}catch(Exception ignore){}return o;}
    static ActiveTrade fromJson(JSONObject o){ActiveTrade t=new ActiveTrade();t.symbol=o.optString("symbol");t.mode=o.optString("mode");t.protectionId=o.optString("protectionId");t.buyOrderId=o.optString("buyOrderId");t.qty=o.optInt("qty");t.fillPrice=o.optDouble("fillPrice");t.target=o.optDouble("target");t.stop=o.optDouble("stop");t.tick=o.optDouble("tick",0.05);t.startedMs=o.optLong("startedMs");t.deadlineMs=o.optLong("deadlineMs");return t;}
}

final class ChargeModel {
    private ChargeModel(){}
    static double requiredSellPrice(double buy,int qty,double desiredNetPct,double slippageReservePct,double tick){double lo=buy,hi=buy*1.03;double goal=buy*qty*(desiredNetPct+slippageReservePct);for(int i=0;i<60;i++){double mid=(lo+hi)/2;double net=(mid-buy)*qty-charges(buy,mid,qty);if(net>=goal)hi=mid;else lo=mid;}return GrowwApi.roundToTick(hi,tick,true);}
    static double charges(double buy,double sell,int qty){double bt=buy*qty,st=sell*qty;double bb=brokerage(bt),sb=brokerage(st);double exch=(bt+st)*0.0000297;double sebi=(bt+st)*0.000001;double ipft=(bt+st)*0.000001;double stamp=bt*0.00003;double stt=st*0.00025;double gst=0.18*(bb+sb+exch+sebi+ipft);return bb+sb+exch+sebi+ipft+stamp+stt+gst;}
    static double brokerage(double turnover){double b=Math.min(20.0,turnover*0.001);double min=Math.min(5.0,turnover*0.025);return Math.max(b,min);}
}
