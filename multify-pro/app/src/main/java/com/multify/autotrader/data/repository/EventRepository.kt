package com.multify.autotrader.data.repository
import android.content.Context
import androidx.work.*
import com.multify.autotrader.data.local.*
import com.multify.autotrader.domain.*
import com.multify.autotrader.worker.DispatchNotificationWorker
import kotlinx.coroutines.flow.Flow
import java.security.MessageDigest
import java.util.concurrent.TimeUnit

class EventRepository(private val context:Context,private val dao:CapturedEventDao){
 fun observeRecent(limit:Int=100):Flow<List<CapturedEventEntity>> = dao.observeRecent(limit)
 fun observePendingCount():Flow<Int> = dao.observePendingCount()
 suspend fun capture(pkg:String,label:String,title:String,text:String,big:String,posted:Long,s:ParsedSignal):CapturedEventEntity{
  val id=stable(pkg,title,big.ifBlank{text},posted);val e=CapturedEventEntity(id,posted,System.currentTimeMillis(),pkg,label,title,text,big,s.type.name,s.symbol,s.target,s.entryLow,s.entryHigh,s.stopLoss,s.exitPrice,s.quantity,s.confidence,if(s.isRelevant)DeliveryStatus.PENDING.name else DeliveryStatus.IGNORED.name)
  dao.insert(e);return dao.byId(id)?:e
 }
 fun enqueue(id:String){
  val r=OneTimeWorkRequestBuilder<DispatchNotificationWorker>().setInputData(workDataOf(DispatchNotificationWorker.KEY_EVENT_ID to id))
   .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build()).setBackoffCriteria(BackoffPolicy.EXPONENTIAL,15,TimeUnit.SECONDS).build()
  WorkManager.getInstance(context).enqueueUniqueWork("dispatch-"+id,ExistingWorkPolicy.KEEP,r)
 }
 suspend fun byId(id:String)=dao.byId(id)
 suspend fun sent(id:String,a:String?,r:String?,m:String?)=dao.markDelivery(id,DeliveryStatus.SENT.name,a,r,m,null)
 suspend fun failed(id:String,e:String)=dao.markDelivery(id,DeliveryStatus.FAILED.name,null,null,null,e)
 private fun stable(s:String,t:String,b:String,p:Long):String{val raw=s+"|"+t+"|"+b+"|"+(if(p>0)p/5000 else 0);return MessageDigest.getInstance("SHA-256").digest(raw.toByteArray()).joinToString(""){"%02x".format(it)}.take(32)}
}
