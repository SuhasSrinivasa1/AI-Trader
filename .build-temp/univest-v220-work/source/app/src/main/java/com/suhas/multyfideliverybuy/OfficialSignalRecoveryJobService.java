package com.suhas.multyfideliverybuy;

import android.app.job.JobParameters;
import android.app.job.JobService;

public class OfficialSignalRecoveryJobService extends JobService {
    @Override public boolean onStartJob(JobParameters params) {
        new Thread(() -> {
            try {
                DurableOfficialSignalQueue.recoverPending(getApplicationContext());
                DurableOfficialSignalQueue.awaitIdle(90_000L);
            } catch (Throwable t) {
                DiagnosticsStore.error(getApplicationContext(), "OFFICIAL_SIGNAL_RECOVERY_JOB_FAILED", "",
                        "Durable official-signal recovery job failed.", t);
            } finally {
                boolean pending = DurableOfficialSignalQueue.pendingCount(getApplicationContext()) > 0;
                jobFinished(params, pending);
                if (pending) OfficialSignalRecoveryScheduler.scheduleAfter(getApplicationContext(), 60_000L);
            }
        }, "official-signal-recovery-job").start();
        return true;
    }

    @Override public boolean onStopJob(JobParameters params) {
        return DurableOfficialSignalQueue.pendingCount(getApplicationContext()) > 0;
    }
}
