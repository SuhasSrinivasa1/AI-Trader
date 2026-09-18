package com.ps.shadowtrader;
import android.content.*;import android.os.Build;
public class EodReceiver extends BroadcastReceiver {public void onReceive(Context c,Intent i){Intent x=new Intent(c,AutomationService.class).setAction(AutomationService.ACTION_EOD);if(Build.VERSION.SDK_INT>=26)c.startForegroundService(x);else c.startService(x);Scheduler.schedule(c);}}
