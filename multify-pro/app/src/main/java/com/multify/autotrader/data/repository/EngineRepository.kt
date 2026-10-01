package com.multify.autotrader.data.repository
import com.multify.autotrader.data.network.BackendClient
import kotlinx.coroutines.flow.first

class EngineRepository(private val deviceId:String,private val settings:SettingsRepository,private val secrets:SecretStore,private val client:BackendClient){
 suspend fun health()=client.health(settings.settings.first().backendUrl)
 suspend fun dashboard()=client.dashboard(settings.settings.first().backendUrl,deviceId,secret())
 suspend fun positions()=client.positions(settings.settings.first().backendUrl,deviceId,secret())
 suspend fun setKillSwitch(v:Boolean)=client.setKillSwitch(settings.settings.first().backendUrl,deviceId,secret(),v)
 fun hasSecret()=secrets.hasDeviceSecret()
 private fun secret()=secrets.getDeviceSecret()?:error("Device secret is not configured")
}
