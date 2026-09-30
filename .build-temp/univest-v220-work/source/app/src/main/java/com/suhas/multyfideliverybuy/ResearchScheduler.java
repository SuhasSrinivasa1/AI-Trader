package com.suhas.multyfideliverybuy;

import android.app.job.JobInfo;
import android.app.job.JobScheduler;
import android.content.ComponentName;
import android.content.Context;
import java.util.Calendar;
import java.util.TimeZone;

final class ResearchScheduler {
    static final int JOB_ID=23030;
    private ResearchScheduler(){}

    static void ensureScheduled(Context c){
        try{
            JobScheduler js=(JobScheduler)c.getSystemService(Context.JOB_SCHEDULER_SERVICE);
            if(js==null)return;
            for(JobInfo j:js.getAllPendingJobs())if(j.getId()==JOB_ID)return;
            scheduleNext(c);
        }catch(Throwable ignored){}
    }

    static void scheduleNext(Context c){
        try{
            JobScheduler js=(JobScheduler)c.getSystemService(Context.JOB_SCHEDULER_SERVICE);if(js==null)return;
            long delay=nextDelay();
            JobInfo info=new JobInfo.Builder(JOB_ID,new ComponentName(c,ResearchJobService.class))
                    .setRequiredNetworkType(JobInfo.NETWORK_TYPE_ANY)
                    .setMinimumLatency(delay)
                    .setOverrideDeadline(delay+60L*60L*1000L)
                    .setPersisted(true)
                    .build();
            js.schedule(info);
        }catch(Throwable t){DiagnosticsStore.error(c,"RESEARCH_SCHEDULE_FAILED","","Unable to schedule Research Lab.",t);}
    }

    private static long nextDelay(){
        TimeZone tz=TimeZone.getTimeZone("Asia/Kolkata");
        Calendar now=Calendar.getInstance(tz);
        Calendar run=(Calendar)now.clone();
        run.set(Calendar.HOUR_OF_DAY,17);run.set(Calendar.MINUTE,30);run.set(Calendar.SECOND,0);run.set(Calendar.MILLISECOND,0);
        if(!run.after(now))run.add(Calendar.DAY_OF_MONTH,1);
        while(run.get(Calendar.DAY_OF_WEEK)==Calendar.SATURDAY||run.get(Calendar.DAY_OF_WEEK)==Calendar.SUNDAY)run.add(Calendar.DAY_OF_MONTH,1);
        return Math.max(60_000L,run.getTimeInMillis()-now.getTimeInMillis());
    }
}
