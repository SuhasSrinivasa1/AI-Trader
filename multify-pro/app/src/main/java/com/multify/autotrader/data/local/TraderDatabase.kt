package com.multify.autotrader.data.local
import androidx.room.Database
import androidx.room.RoomDatabase

@Database(entities=[CapturedEventEntity::class],version=1,exportSchema=false)
abstract class TraderDatabase:RoomDatabase(){ abstract fun capturedEventDao():CapturedEventDao }
