package com.suhas.multyfideliverybuy;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

public class ResearchBootReceiver extends BroadcastReceiver {
    @Override public void onReceive(Context context, Intent intent){ResearchScheduler.ensureScheduled(context.getApplicationContext());}
}
