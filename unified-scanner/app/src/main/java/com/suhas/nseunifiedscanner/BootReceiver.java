package com.suhas.nseunifiedscanner;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.os.Build;

public class BootReceiver extends BroadcastReceiver {
    @Override public void onReceive(Context context, Intent intent) {
        boolean needsRecovery=ActiveTrade.load(context)!=null;
        boolean scannerEnabled=context.getSharedPreferences("scanner_prefs",Context.MODE_PRIVATE).getBoolean("scanner_enabled",false);
        if(!needsRecovery&&!scannerEnabled)return;
        Intent s=new Intent(context,UnifiedService.class).setAction(UnifiedService.ACTION_START);
        if(Build.VERSION.SDK_INT>=26)context.startForegroundService(s);else context.startService(s);
    }
}
