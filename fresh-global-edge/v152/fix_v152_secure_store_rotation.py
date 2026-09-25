#!/usr/bin/env python3
from pathlib import Path
import sys
root=Path(sys.argv[1]).resolve()

p=root/"app/src/main/java/com/suhas/ucsentinel/data/local/SecureCredentialStore.kt"
p.write_text(r'''package com.suhas.globaledgeai.data.local

import android.content.Context
import android.content.SharedPreferences
import android.util.Log
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import com.suhas.globaledgeai.domain.model.AuthMode
import com.suhas.globaledgeai.domain.model.Credentials

/**
 * Secure credential storage with crash-proof Android Keystore recovery.
 *
 * Older installs used AndroidX's default master-key alias. Some device/OS upgrade or restore
 * paths can leave that alias unable to authenticate the encrypted Tink keyset and
 * EncryptedSharedPreferences.create() throws AEADBadTagException before Application startup.
 *
 * We never allow that condition to terminate the app:
 *  1) Try the legacy encrypted store so healthy installs retain credentials.
 *  2) If legacy decryption fails, move to a brand-new encrypted preference file AND a
 *     brand-new Android Keystore alias. The unreadable legacy material is left untouched.
 *  3) If a previous recovery alias also became unreadable, rotate to the next recovery alias.
 *  4) If Android Keystore itself is unavailable, start with credentials disabled rather than crash.
 *
 * No secret is ever written to normal/plain SharedPreferences.
 */
class SecureCredentialStore(context: Context) {
    companion object {
        private const val TAG="GlobalEdge/SecureStore"
        private const val LEGACY_FILE="global_edge_ai_secure"
        private const val RECOVERY_FILE_V2="global_edge_ai_secure_recovery_v2"
        private const val RECOVERY_FILE_V3="global_edge_ai_secure_recovery_v3"
        private const val RECOVERY_ALIAS_V2="global_edge_ai_master_recovery_v2"
        private const val RECOVERY_ALIAS_V3="global_edge_ai_master_recovery_v3"
    }

    private val appContext=context.applicationContext

    private fun encryptedPrefs(fileName:String, alias:String?=null):SharedPreferences{
        val builder=if(alias==null) MasterKey.Builder(appContext) else MasterKey.Builder(appContext,alias)
        val masterKey=builder.setKeyScheme(MasterKey.KeyScheme.AES256_GCM).build()
        return EncryptedSharedPreferences.create(
            appContext,
            fileName,
            masterKey,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
        )
    }

    private val prefs:SharedPreferences?
    private val secureStoreLabel:String

    init{
        var opened:SharedPreferences?=null
        var label="UNAVAILABLE"

        try{
            opened=encryptedPrefs(LEGACY_FILE)
            label="LEGACY"
            Log.i(TAG,"Secure credential store opened normally.")
        }catch(first:Throwable){
            Log.e(TAG,"Legacy encrypted credential store is unreadable; rotating to a fresh Android Keystore alias. Existing Groww credentials/token will require re-entry.",first)

            try{
                opened=encryptedPrefs(RECOVERY_FILE_V2,RECOVERY_ALIAS_V2)
                label="RECOVERY_V2"
                Log.w(TAG,"Secure credential recovery succeeded with fresh alias v2. Non-secret app data was preserved.")
            }catch(second:Throwable){
                Log.e(TAG,"Recovery alias v2 could not be opened; rotating once more.",second)
                try{
                    // Use a second independent alias/file. This also handles a damaged prior recovery attempt.
                    opened=encryptedPrefs(RECOVERY_FILE_V3,RECOVERY_ALIAS_V3)
                    label="RECOVERY_V3"
                    Log.w(TAG,"Secure credential recovery succeeded with fresh alias v3. Non-secret app data was preserved.")
                }catch(third:Throwable){
                    Log.e(TAG,"Android Keystore encrypted credential storage is unavailable. App will start without credentials instead of crashing.",third)
                }
            }
        }
        prefs=opened
        secureStoreLabel=label
    }

    fun isSecureStoreAvailable():Boolean=prefs!=null
    fun secureStoreState():String=secureStoreLabel

    fun saveCredentials(credentials: Credentials) {
        val p=prefs
        if(p==null){
            Log.e(TAG,"Credentials were not saved because Android Keystore is unavailable.")
            return
        }
        p.edit()
            .putString("auth_mode", credentials.mode.name)
            .putString("api_key", credentials.apiKeyOrTotpToken)
            .putString("secret", credentials.secret)
            .apply()
    }

    fun loadCredentials(): Credentials {
        val p=prefs ?: return Credentials()
        return try{
            val mode=runCatching{
                AuthMode.valueOf(p.getString("auth_mode",AuthMode.TOTP.name)?:AuthMode.TOTP.name)
            }.getOrDefault(AuthMode.TOTP)
            Credentials(
                mode=mode,
                apiKeyOrTotpToken=p.getString("api_key","")?:"",
                secret=p.getString("secret","")?:""
            )
        }catch(t:Throwable){
            Log.e(TAG,"Credential read failed; returning an empty credential state.",t)
            Credentials()
        }
    }

    fun saveAccessToken(token:String,expiry:String){
        val p=prefs ?: return
        runCatching{
            p.edit()
                .putString("access_token",token)
                .putString("access_token_expiry",expiry)
                .putLong("access_token_saved_at",System.currentTimeMillis())
                .apply()
        }.onFailure{Log.e(TAG,"Access token could not be persisted.",it)}
    }

    fun accessToken():String=runCatching{prefs?.getString("access_token","")?:""}.getOrDefault("")
    fun accessTokenExpiry():String=runCatching{prefs?.getString("access_token_expiry","")?:""}.getOrDefault("")
    fun accessTokenSavedAt():Long=runCatching{prefs?.getLong("access_token_saved_at",0L)?:0L}.getOrDefault(0L)

    fun clearAccessToken(){
        val p=prefs ?: return
        runCatching{
            p.edit().remove("access_token").remove("access_token_expiry").remove("access_token_saved_at").apply()
        }.onFailure{Log.e(TAG,"Access token clear failed.",it)}
    }
}
''',encoding="utf-8")

g=root/"app/build.gradle.kts"
s=g.read_text(encoding="utf-8")
if 'versionCode = 151' not in s or 'versionName = "1.5.1"' not in s:
    raise SystemExit("Expected v1.5.1 version anchors not found")
s=s.replace('versionCode = 151','versionCode = 152',1)
s=s.replace('versionName = "1.5.1"','versionName = "1.5.2"',1)
g.write_text(s,encoding="utf-8")
print("v1.5.2 fresh-keystore-alias recovery patch applied")
