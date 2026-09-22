package com.ps.shadowtrader;

import android.app.Notification;
import android.content.*;
import android.content.pm.ApplicationInfo;
import android.os.Build;
import android.service.notification.NotificationListenerService;
import android.service.notification.StatusBarNotification;
import java.text.*;
import java.util.*;

public class MultifyNotificationService extends NotificationListenerService {
    @Override public void onNotificationPosted(StatusBarNotification sbn){
        if(!isMultifyNotification(sbn))return;

        Notification n=sbn.getNotification();
        CharSequence title=n.extras.getCharSequence(Notification.EXTRA_TITLE,"");
        CharSequence text=n.extras.getCharSequence(Notification.EXTRA_TEXT,"");
        CharSequence big=n.extras.getCharSequence(Notification.EXTRA_BIG_TEXT,"");
        String body=((text==null?"":text.toString())+" "+(big==null?"":big.toString())).trim();

        WatchlistStore wl=new WatchlistStore(this);
        NotificationParser.Pick p=new NotificationParser().parse(
                title==null?"":title.toString(),body,wl.knownSymbols());
        if(p==null)return;

        long now=System.currentTimeMillis();
        android.content.SharedPreferences state=getSharedPreferences("state",MODE_PRIVATE);
        String stamp=new SimpleDateFormat("HH:mm:ss",Locale.getDefault()).format(new Date(now));

        if(p.kind==NotificationParser.Kind.NEW_CALL){
            wl.add(p.symbol,p.raw);
            new EventStore(this).add("MULTIFY","NEW "+p.symbol+" • eligible intraday call captured at "+stamp);
        }else if(p.kind==NotificationParser.Kind.UPDATE){
            if(wl.contains(p.symbol))wl.touch(p.symbol,p.raw);else wl.add(p.symbol,p.raw);
            new EventStore(this).add("MULTIFY","UPDATE "+p.symbol+" captured at "+stamp);
        }else{
            wl.remove(p.symbol);
            state.edit().putString("pending_multify_exit_symbol",p.symbol)
                    .putLong("pending_multify_exit_ts",now)
                    .putString("pending_multify_exit_raw",p.raw).apply();
            new EventStore(this).add("MULTIFY","EXIT "+p.symbol+" captured at "+stamp+" • shadow exit requested");
        }

        state.edit()
                .putString("last_symbol",p.symbol)
                .putString("last_notification",p.raw)
                .putString("last_source",sbn.getPackageName())
                .putString("last_multify_event",p.kind.name()+" "+p.symbol+" @ "+stamp)
                .putLong("last_pick_ts",now).apply();

        Intent i=new Intent(this,AutomationService.class)
                .setAction(p.kind==NotificationParser.Kind.EXIT?AutomationService.ACTION_MULTIFY_EXIT:AutomationService.ACTION_PICK)
                .putExtra("symbol",p.symbol);
        if(Build.VERSION.SDK_INT>=26)startForegroundService(i);else startService(i);
    }

    private boolean isMultifyNotification(StatusBarNotification sbn){
        String pkg=sbn.getPackageName();
        android.content.SharedPreferences state=getSharedPreferences("state",MODE_PRIVATE);
        String known=state.getString("multify_package","");
        if(!known.isEmpty()&&known.equals(pkg))return true;

        try{
            ApplicationInfo info=getPackageManager().getApplicationInfo(pkg,0);
            CharSequence label=getPackageManager().getApplicationLabel(info);
            String name=label==null?"":label.toString().toUpperCase(Locale.ROOT);
            if(name.contains("MULTIFY")){
                state.edit().putString("multify_package",pkg).apply();
                return true;
            }
        }catch(Exception ignored){}
        return false;
    }
}
