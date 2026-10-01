package com.multify.autotrader.data.local
import androidx.room.*
import kotlinx.coroutines.flow.Flow

@Dao interface CapturedEventDao {
 @Insert(onConflict=OnConflictStrategy.IGNORE) suspend fun insert(event:CapturedEventEntity):Long
 @Query("SELECT * FROM captured_events WHERE id=:id LIMIT 1") suspend fun byId(id:String):CapturedEventEntity?
 @Query("SELECT * FROM captured_events ORDER BY receivedAtMs DESC LIMIT :limit") fun observeRecent(limit:Int=100):Flow<List<CapturedEventEntity>>
 @Query("SELECT COUNT(*) FROM captured_events WHERE deliveryStatus='PENDING'") fun observePendingCount():Flow<Int>
 @Query("""UPDATE captured_events SET deliveryStatus=:status,attemptCount=attemptCount+1,serverAction=:action,serverReason=:reason,serverMode=:mode,lastError=:error WHERE id=:id""")
 suspend fun markDelivery(id:String,status:String,action:String?,reason:String?,mode:String?,error:String?)
 @Query("DELETE FROM captured_events WHERE receivedAtMs < :beforeMs") suspend fun deleteOlderThan(beforeMs:Long):Int
}
