package com.suhas.globaledgeai.worker

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import com.suhas.globaledgeai.diagnostics.DiagnosticLog

class BootReceiver: BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent?) {
        DiagnosticLog.log(context,"BOOT","Received ${intent?.action.orEmpty()}; starting market scanner")
        runCatching { MarketScanService.start(context) }
            .onFailure { DiagnosticLog.log(context,"BOOT","Unable to start market scanner",it) }
    }
}
