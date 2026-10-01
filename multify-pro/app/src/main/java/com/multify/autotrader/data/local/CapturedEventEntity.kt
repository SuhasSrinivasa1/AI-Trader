package com.multify.autotrader.data.local
import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName="captured_events")
data class CapturedEventEntity(
 @PrimaryKey val id:String,
 val postedAtMs:Long,val receivedAtMs:Long,val sourcePackage:String,val appLabel:String,
 val title:String,val text:String,val bigText:String,val eventType:String,val symbol:String?,
 val target:Double?,val entryLow:Double?,val entryHigh:Double?,val stopLoss:Double?,val exitPrice:Double?,
 val quantity:Int?,val confidence:Double,val deliveryStatus:String,val attemptCount:Int=0,
 val serverAction:String?=null,val serverReason:String?=null,val serverMode:String?=null,val lastError:String?=null
)
