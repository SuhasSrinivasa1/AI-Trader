package com.ps.shadowtrader;

import android.app.*;import android.content.*;import java.util.*;
public class Scheduler {
    public static void schedule(Context c){Calendar t=Calendar.getInstance();t.set(Calendar.HOUR_OF_DAY,15);t.set(Calendar.MINUTE,45);t.set(Calendar.SECOND,0);if(t.getTimeInMillis()<=System.currentTimeMillis())t.add(Calendar.DATE,1);PendingIntent pi=PendingIntent.getBroadcast(c,44,new Intent(c,EodReceiver.class),PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE);((AlarmManager)c.getSystemService(Context.ALARM_SERVICE)).setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP,t.getTimeInMillis(),pi);}
}
