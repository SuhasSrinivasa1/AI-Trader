from pathlib import Path
ROOT=Path('unified-scanner/app/src/main/java/com/suhas/nseunifiedscanner')

def rep(path,old,new):
    p=Path(path);s=p.read_text()
    if old not in s: raise SystemExit(f'missing tail anchor in {p}: {old[:100]!r}')
    p.write_text(s.replace(old,new,1))

def require(path,needle):
    if needle not in Path(path).read_text(): raise SystemExit(f'v1.2 prerequisite missing in {path}: {needle}')

sp=ROOT/'ScannerEngine.java';lp=ROOT/'LearningStore.java';mp=ROOT/'MainActivity.java';up=ROOT/'UnifiedService.java'
require(sp,'TradeSetupLogic.Signals path=')
require(sp,'HOD/resistance blocks target')
require(lp,'"hodroom"')
require(mp,'ACCURACY SCORE')

rep(mp,
'Displayed recommendations keep the official hit-rate. Ranks 4–10 are replayed separately as lower-weight shadow observations so the model learns faster without inflating the success metric. Live BUY gates remain strict; learning cannot override the +0.50% net objective, 30-minute time stop, liquidity, spread, R:R or protection rules.',
'BUY-qualified calls keep the official accuracy score. Ranks 4–10 remain lower-weight shadow learning. v1.2 additionally learns recovery-from-negative, HOD rejection, breakout confirmation and clear-path-to-target behaviour. Learning cannot override the +0.50% net objective, 30-minute time stop, liquidity, spread, R:R or protection rules.')
rep(mp,'v1.1.0 • standalone package com.suhas.nseunifiedscanner','v1.2.0 • standalone package com.suhas.nseunifiedscanner')

rep(up,'private static final int NOTIFY_ID=27101; private static final String CHANNEL="nse_scanner_live";','private static final int NOTIFY_ID=27101; private static final String CHANNEL="nse_scanner_live"; private static final String ALERT_CHANNEL="nse_scanner_buy_alerts_v12";')
rep(up,'checkStaticIp(false);\n                setStatus("Scan complete • "+r.marketLabel+" • "+r.recommendations.size()+" candidates");','checkStaticIp(false);\n                notifyQualifiedSetups(r);\n                setStatus("Scan complete • "+r.marketLabel+" • "+r.recommendations.size()+" candidates");')

insert='''    private void notifyQualifiedSetups(ScannerEngine.ScanResult r){\n        if(r==null||r.recommendations==null||r.recommendations.isEmpty()||ActiveTrade.load(this)!=null)return;\n        LocalTime t=LocalDateTime.now(ScannerEngine.IST).toLocalTime();if(t.isBefore(LocalTime.of(9,15))||t.isAfter(LocalTime.of(14,40)))return;\n        if(prefs().getInt("static_ip_state",0)!=1)return;\n        NotificationManager nm=(NotificationManager)getSystemService(NOTIFICATION_SERVICE);long now=System.currentTimeMillis();int emitted=0;\n        for(ScannerEngine.Recommendation rec:r.recommendations){\n            if(!rec.qualified)continue;String key="buy_alert_"+rec.symbol;long last=prefs().getLong(key,0);if(now-last<25*60_000L)continue;\n            prefs().edit().putLong(key,now).apply();Intent open=new Intent(this,MainActivity.class);open.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_CLEAR_TOP);\n            PendingIntent pi=PendingIntent.getActivity(this,Math.abs(rec.symbol.hashCode()),open,PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE);\n            String setup=rec.features.optString("setupType","MOMENTUM");String body=String.format(Locale.US,"%s • Entry ₹%.2f • Target ₹%.2f • SL ₹%.2f • Score %.0f/100 • model %.0f%% • max 30 min. Tap to review and BUY.",setup,rec.entry,rec.target,rec.stop,rec.score,rec.probability*100);\n            Notification.Builder b=Build.VERSION.SDK_INT>=26?new Notification.Builder(this,ALERT_CHANNEL):new Notification.Builder(this);\n            b.setContentTitle("BUY SETUP • "+rec.symbol).setContentText(String.format(Locale.US,"Entry ₹%.2f • Target ₹%.2f • SL ₹%.2f",rec.entry,rec.target,rec.stop)).setStyle(new Notification.BigTextStyle().bigText(body)).setSmallIcon(android.R.drawable.ic_input_add).setContentIntent(pi).setAutoCancel(true).setCategory(Notification.CATEGORY_RECOMMENDATION).setWhen(now);\n            if(Build.VERSION.SDK_INT<26)b.setPriority(Notification.PRIORITY_HIGH).setDefaults(Notification.DEFAULT_ALL);\n            nm.notify(33000+Math.abs(rec.symbol.hashCode()%5000),b.build());learning.audit("ALERT",rec.symbol+" BUY-qualified notification sent");if(++emitted>=3)break;\n        }\n    }\n\n'''
rep(up,'    private void checkStaticIp(boolean force){',insert+'    private void checkStaticIp(boolean force){')
rep(up,'NSEUnifiedScanner/1.1','NSEUnifiedScanner/1.2')
rep(up,'private void createChannel(){if(Build.VERSION.SDK_INT>=26){NotificationChannel c=new NotificationChannel(CHANNEL,"NSE Unified Scanner",NotificationManager.IMPORTANCE_LOW);c.setDescription("5-minute NSE scans and active intraday protection");((NotificationManager)getSystemService(NOTIFICATION_SERVICE)).createNotificationChannel(c);}}','private void createChannel(){if(Build.VERSION.SDK_INT>=26){NotificationManager nm=(NotificationManager)getSystemService(NOTIFICATION_SERVICE);NotificationChannel c=new NotificationChannel(CHANNEL,"NSE Unified Scanner",NotificationManager.IMPORTANCE_LOW);c.setDescription("5-minute NSE scans and active intraday protection");nm.createNotificationChannel(c);NotificationChannel a=new NotificationChannel(ALERT_CHANNEL,"NSE BUY-qualified alerts",NotificationManager.IMPORTANCE_HIGH);a.setDescription("Heads-up alerts only for newly BUY-qualified scanner setups");a.enableVibration(true);nm.createNotificationChannel(a);}}')
print('v1.2 tail patch applied successfully')
