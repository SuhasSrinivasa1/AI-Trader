package com.multify.autotrader.worker
import android.content.Context
import androidx.work.*
import com.multify.autotrader.MultifyApplication
import com.multify.autotrader.data.network.*
import kotlinx.coroutines.flow.first

class DispatchNotificationWorker(ctx:Context,p:WorkerParameters):CoroutineWorker(ctx,p){
 override suspend fun doWork():Result{
  val id=inputData.getString(KEY_EVENT_ID)?:return Result.failure();val app=applicationContext as? MultifyApplication?:return Result.failure();val c=app.container
  val e=c.eventRepository.byId(id)?:return Result.success();val s=c.settingsRepository.settings.first()
  if(!s.forwardingEnabled&&e.eventType!="AUTO_PAUSED")return Result.success()
  val secret=c.secretStore.getDeviceSecret();if(secret.isNullOrBlank()){c.eventRepository.failed(id,"Device secret is not configured");return Result.failure()}
  return try{val r=c.backendClient.sendNotification(s.backendUrl,c.deviceId(),secret,NotificationPayload(e.id,e.sourcePackage,e.appLabel,e.title,e.text,e.bigText,e.postedAtMs));c.eventRepository.sent(id,r.action,r.reason,r.mode);Result.success()}
  catch(x:BackendException){c.eventRepository.failed(id,x.message?:"Backend error");if(x.retryable&&runAttemptCount<5)Result.retry() else Result.failure()}
  catch(x:Exception){c.eventRepository.failed(id,x.message?:x.javaClass.simpleName);if(runAttemptCount<5)Result.retry() else Result.failure()}
 }
 companion object{const val KEY_EVENT_ID="event_id"}
}
