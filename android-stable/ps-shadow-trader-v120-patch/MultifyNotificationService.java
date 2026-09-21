package com.ps.shadowtrader;

import android.app.Notification;
import android.content.*;
import android.os.Build;
import android.service.notification.NotificationListenerService;
import android.service.notification.StatusBarNotification;

public class MultifyNotificationService extends NotificationListenerService {
    @Override public void onNotificationPosted(StatusBarNotification sbn){
        Notification n=sbn.getNotification();
        CharSequence t=n.extras.getCharSequence(Notification.EXTRA_TITLE,"");
        CharSequence x=n.extras.getCharSequence(Notification.EXTRA_TEXT,"");
        CharSequence big=n.extras.getCharSequence(Notification.EXTRA_BIG_TEXT,"");
        String raw=(t+" "+x+" "+big).trim();

        NotificationParser.Pick p=new NotificationParser().parse(raw);
        if(p==null)return;

        new WatchlistStore(this).add(p.symbol,p.raw);
        getSharedPreferences("state",MODE_PRIVATE).edit()
                .putString("last_symbol",p.symbol)
                .putString("last_notification",p.raw)
                .putString("last_source",sbn.getPackageName())
                .putLong("last_pick_ts",System.currentTimeMillis()).apply();

        new EventStore(this).add("MULTIFY","Accepted EQUITY INTRADAY: "+p.symbol+" • adaptive watchlist updated");
        Intent i=new Intent(this,AutomationService.class).setAction(AutomationService.ACTION_PICK);
        if(Build.VERSION.SDK_INT>=26)startForegroundService(i);else startService(i);
    }
}
