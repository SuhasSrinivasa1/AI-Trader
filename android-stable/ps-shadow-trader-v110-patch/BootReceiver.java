package com.ps.shadowtrader;
import android.content.*;import android.os.Build;
public class BootReceiver extends BroadcastReceiver {public void onReceive(Context c,Intent i){Scheduler.schedule(c);if(!new SecureStore(c).get("token").isEmpty()){Intent x=new Intent(c,AutomationService.class);if(Build.VERSION.SDK_INT>=26)c.startForegroundService(x);else c.startService(x);}}}
