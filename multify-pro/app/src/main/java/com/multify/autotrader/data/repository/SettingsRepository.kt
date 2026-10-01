package com.multify.autotrader.data.repository
import android.content.Context
import androidx.datastore.preferences.core.*
import androidx.datastore.preferences.preferencesDataStore
import com.multify.autotrader.BuildConfig
import kotlinx.coroutines.flow.*

private val Context.settingsDataStore by preferencesDataStore("multify_settings")
data class AppSettings(val backendUrl:String=BuildConfig.DEFAULT_BACKEND_URL,val packageFilter:String="multify",val forwardingEnabled:Boolean=false)

class SettingsRepository(private val context:Context){
 private object Keys{val backendUrl=stringPreferencesKey("backend_url");val packageFilter=stringPreferencesKey("package_filter");val forwarding=booleanPreferencesKey("forwarding_enabled")}
 val settings:Flow<AppSettings> = context.settingsDataStore.data.map{p->AppSettings(p[Keys.backendUrl]?:BuildConfig.DEFAULT_BACKEND_URL,p[Keys.packageFilter]?:"multify",p[Keys.forwarding]?:false)}
 suspend fun updateBackendUrl(v:String)=context.settingsDataStore.edit{it[Keys.backendUrl]=v.trim()}
 suspend fun updatePackageFilter(v:String)=context.settingsDataStore.edit{it[Keys.packageFilter]=v.trim()}
 suspend fun setForwardingEnabled(v:Boolean)=context.settingsDataStore.edit{it[Keys.forwarding]=v}
}
