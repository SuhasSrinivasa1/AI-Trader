package com.suhas.globaledgeai.data.local

import android.content.Context
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import com.suhas.globaledgeai.domain.model.AuthMode
import com.suhas.globaledgeai.domain.model.Credentials

class SecureCredentialStore(context: Context) {
    private val masterKey = MasterKey.Builder(context)
        .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
        .build()

    private val prefs = EncryptedSharedPreferences.create(
        context,
        "global_edge_ai_secure",
        masterKey,
        EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
        EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
    )

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
