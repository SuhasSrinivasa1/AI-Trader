package com.multify.autotrader.service
import android.app.Notification
import android.service.notification.*
import com.multify.autotrader.MultifyApplication
import com.multify.autotrader.domain.*
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.first

class MultifyNotificationListenerService:NotificationListenerService(){
 private val scope=CoroutineScope(SupervisorJob()+Dispatchers.IO);private var connected=false
 override fun onListenerConnected(){super.onListenerConnected();connected=true}
 override fun onListenerDisconnected(){connected=false;super.onListenerDisconnected()}
 override fun onDestroy(){scope.cancel();super.onDestroy()}
 override fun onNotificationPosted(sbn:StatusBarNotification?){
  if(!connected||sbn==null||sbn.packageName==packageName)return;val e=sbn.notification?.extras?:return
  val title=e.getCharSequence(Notification.EXTRA_TITLE)?.toString().orEmpty();val text=e.getCharSequence(Notification.EXTRA_TEXT)?.toString().orEmpty();val big=e.getCharSequence(Notification.EXTRA_BIG_TEXT)?.toString().orEmpty().ifBlank{text}
  scope.launch{val app=application as? MultifyApplication?:return@launch;val c=app.container;val settings=c.settingsRepository.settings.first();val filter=settings.packageFilter.trim().lowercase()
   val label=runCatching{packageManager.getApplicationLabel(packageManager.getApplicationInfo(sbn.packageName,0)).toString()}.getOrElse{sbn.packageName}
   if(filter.isNotBlank()&&!sbn.packageName.lowercase().contains(filter)&&!label.lowercase().contains(filter))return@launch
   val p=SignalParser.parse(title,text,big);if(!p.isRelevant)return@launch
   val ev=c.eventRepository.capture(sbn.packageName,label,title,text,big,sbn.postTime,p)
   if(p.type==EventType.AUTO_PAUSED)c.settingsRepository.setForwardingEnabled(false)
   if(settings.forwardingEnabled||p.type==EventType.AUTO_PAUSED)c.eventRepository.enqueue(ev.id)
  }
 }
}
