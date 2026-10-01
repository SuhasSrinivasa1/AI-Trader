package com.multify.autotrader
import android.app.Application
import android.provider.Settings
import androidx.room.Room
import com.multify.autotrader.data.local.TraderDatabase
import com.multify.autotrader.data.network.BackendClient
import com.multify.autotrader.data.repository.*

class MultifyApplication:Application(){
 lateinit var container:AppContainer;private set
 override fun onCreate(){super.onCreate();container=AppContainer(this)}
}
class AppContainer(app:Application){
 val database=Room.databaseBuilder(app,TraderDatabase::class.java,"multify-autotrader-v2.db").fallbackToDestructiveMigration().build()
 val settingsRepository=SettingsRepository(app);val secretStore=SecretStore(app);val backendClient=BackendClient()
 val eventRepository=EventRepository(app,database.capturedEventDao())
 private val deviceId=Settings.Secure.getString(app.contentResolver,Settings.Secure.ANDROID_ID)?:"unknown-device"
 val engineRepository=EngineRepository(deviceId,settingsRepository,secretStore,backendClient)
 fun deviceId()=deviceId
}
