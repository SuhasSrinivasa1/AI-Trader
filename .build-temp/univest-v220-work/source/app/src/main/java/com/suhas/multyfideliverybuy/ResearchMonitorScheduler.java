package com.suhas.multyfideliverybuy;

import android.app.job.JobInfo;
import android.app.job.JobScheduler;
import android.content.ComponentName;
import android.content.Context;
import android.os.Build;

final class ResearchMonitorScheduler {
    static final int JOB_ID = 23031;
    private static final long PERIOD_MS = 15L * 60L * 1000L;

    private ResearchMonitorScheduler() {}

    static void ensureScheduled(Context context) {
        Context c = context.getApplicationContext();
        try {
            JobScheduler js = (JobScheduler)c.getSystemService(Context.JOB_SCHEDULER_SERVICE);
            if (js == null) return;
            if (Build.VERSION.SDK_INT >= 24 && js.getPendingJob(JOB_ID) != null) return;
            JobInfo.Builder b = new JobInfo.Builder(JOB_ID, new ComponentName(c, ResearchMonitorJobService.class))
                    .setRequiredNetworkType(JobInfo.NETWORK_TYPE_ANY)
                    .setPersisted(true)
                    .setPeriodic(PERIOD_MS);
            js.schedule(b.build());
        } catch (Throwable t) {
            DiagnosticsStore.error(c, "RESEARCH_MONITOR_SCHEDULE_FAILED", "",
                    "Unable to schedule Research live monitor.", t);
        }
    }
}
