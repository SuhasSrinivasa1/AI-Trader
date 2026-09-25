#!/usr/bin/env python3
from pathlib import Path
import sys
root=Path(sys.argv[1]).resolve()

# Patch secure credential storage to self-heal when Android Keystore and the encrypted
# Tink keyset no longer match. Only the encrypted credential store is reset.
p=root/"app/src/main/java/com/suhas/ucsentinel/data/local/SecureCredentialStore.kt"
s=p.read_text(encoding="utf-8")
s='''package com.suhas.globaledgeai.data.local

import android.content.Context
import android.content.SharedPreferences
import android.util.Log
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import com.suhas.globaledgeai.domain.model.AuthMode
import com.suhas.globaledgeai.domain.model.Credentials
import java.security.KeyStore

class SecureCredentialStore(context: Context) {
    companion object {
        private const val TAG="GlobalEdge/SecureStore"
        private const val PREF_FILE="global_edge_ai_secure"
        // androidx.security MasterKey default alias used by earlier Global Edge versions.
        private const val MASTER_KEY_ALIAS="_androidx_security_master_key_"
    }

    private val appContext=context.applicationContext

    private fun createEncryptedPrefs():SharedPreferences{
        val masterKey=MasterKey.Builder(appContext)
            .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
            .build()
        return EncryptedSharedPreferences.create(
            appContext,
            PREF_FILE,
            masterKey,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
        )
    }

    private fun recoverEncryptedPrefs(firstFailure:Throwable):SharedPreferences{
        Log.e(TAG,"Encrypted credential store could not be opened; attempting secure-store recovery. Non-secret app data is preserved.",firstFailure)

        // Most AEADBadTag failures are a stale encrypted Tink keyset paired with a valid
        // Android Keystore master key. Remove only the encrypted credential preference file first.
        runCatching{appContext.deleteSharedPreferences(PREF_FILE)}
            .onFailure{Log.w(TAG,"Unable to delete damaged encrypted preferences on first recovery pass",it)}

        runCatching{return createEncryptedPrefs()}.onFailure{second->
            Log.w(TAG,"Secure-store recovery with existing master key failed; regenerating the app master key.",second)
        }

        // If the master key itself was restored/invalidation-corrupted, remove only this
        // app's AndroidX Security master-key alias and recreate both key and encrypted store.
        runCatching{
            val ks=KeyStore.getInstance("AndroidKeyStore")
            ks.load(null)
            if(ks.containsAlias(MASTER_KEY_ALIAS))ks.deleteEntry(MASTER_KEY_ALIAS)
        }.onFailure{Log.e(TAG,"Unable to reset Android Keystore master key",it)}

        runCatching{appContext.deleteSharedPreferences(PREF_FILE)}
        return createEncryptedPrefs().also{
            Log.w(TAG,"Secure credential store was reset successfully. Groww credentials/token must be entered again.")
        }
    }

    private val prefs:SharedPreferences=try{
        createEncryptedPrefs()
    }catch(t:Throwable){
        recoverEncryptedPrefs(t)
    }

    fun saveCredentials(credentials: Credentials) {
        prefs.edit()
            .putString("auth_mode", credentials.mode.name)
            .putString("api_key", credentials.apiKeyOrTotpToken)
            .putString("secret", credentials.secret)
            .apply()
    }

    fun loadCredentials(): Credentials {
        val mode = runCatching {
            AuthMode.valueOf(prefs.getString("auth_mode", AuthMode.TOTP.name) ?: AuthMode.TOTP.name)
        }.getOrDefault(AuthMode.TOTP)

        return Credentials(
            mode = mode,
            apiKeyOrTotpToken = prefs.getString("api_key", "") ?: "",
            secret = prefs.getString("secret", "") ?: ""
        )
    }

    fun saveAccessToken(token: String, expiry: String) {
        prefs.edit()
            .putString("access_token", token)
            .putString("access_token_expiry", expiry)
            .putLong("access_token_saved_at", System.currentTimeMillis())
            .apply()
    }

    fun accessToken(): String = prefs.getString("access_token", "") ?: ""
    fun accessTokenExpiry(): String = prefs.getString("access_token_expiry", "") ?: ""
    fun accessTokenSavedAt(): Long = prefs.getLong("access_token_saved_at", 0L)

    fun clearAccessToken() {
        prefs.edit()
            .remove("access_token")
            .remove("access_token_expiry")
            .remove("access_token_saved_at")
            .apply()
    }
}
'''
p.write_text(s,encoding="utf-8")

# Version bump.
p=root/"app/build.gradle.kts"
s=p.read_text(encoding="utf-8")
if 'versionCode = 150' not in s or 'versionName = "1.5.0"' not in s:
    raise SystemExit("Expected v1.5.0 version anchors not found")
s=s.replace('versionCode = 150','versionCode = 151',1).replace('versionName = "1.5.0"','versionName = "1.5.1"',1)
p.write_text(s,encoding="utf-8")

print("v1.5.1 secure credential self-recovery patch applied")
