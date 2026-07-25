package com.suhas.multyfiautobuy.stable;

import android.content.Context;

final class TokenManager {
    private TokenManager() { }

    static synchronized String validToken(Context context) {
        String token = SecureStore.get(context, SecureStore.ACCESS_TOKEN);
        String date = SecureStore.get(context, SecureStore.ACCESS_TOKEN_DATE);
        if (!token.isEmpty() && AppPrefs.istDate().equals(date)) return token;

        String apiKey = SecureStore.get(context, SecureStore.API_KEY);
        String secret = SecureStore.get(context, SecureStore.TOTP_SECRET);
        GrowwClient.AuthResult result = GrowwClient.authenticate(apiKey, secret);
        if (!result.success) {
            AppPrefs.log(context, "TOKEN REFRESH FAILED", result.message);
            return "";
        }
        try {
            SecureStore.put(context, SecureStore.ACCESS_TOKEN, result.accessToken);
            SecureStore.put(context, SecureStore.ACCESS_TOKEN_DATE, AppPrefs.istDate());
            AppPrefs.log(context, "TOKEN REFRESHED", "Groww access token generated from TOTP.");
            return result.accessToken;
        } catch (Exception e) {
            AppPrefs.log(context, "TOKEN STORE FAILED", e.getMessage());
            return "";
        }
    }
}
