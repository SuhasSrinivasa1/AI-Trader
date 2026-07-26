package com.suhas.multyfiautobuy.stable;

import android.content.Context;
import android.content.SharedPreferences;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;

import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.KeyStore;

import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

final class SecureStore {
    static final String API_KEY = "api_key";
    static final String TOTP_SECRET = "totp_secret";
    static final String ACCESS_TOKEN = "access_token";
    static final String ACCESS_TOKEN_DATE = "access_token_date";

    private static final String KEY_ALIAS = "multyfi_autobuy_stable_key";
    private static final String PREFS = "secure_values";
    private static final String ANDROID_KEY_STORE = "AndroidKeyStore";

    private SecureStore() { }

    static void put(Context context, String key, String value) throws Exception {
        if (value == null || value.trim().isEmpty()) {
            remove(context, key);
            return;
        }
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, getOrCreateKey());
        byte[] encrypted = cipher.doFinal(value.getBytes(StandardCharsets.UTF_8));
        byte[] iv = cipher.getIV();
        ByteBuffer buffer = ByteBuffer.allocate(4 + iv.length + encrypted.length);
        buffer.putInt(iv.length);
        buffer.put(iv);
        buffer.put(encrypted);
        String encoded = Base64.encodeToString(buffer.array(), Base64.NO_WRAP);
        prefs(context).edit().putString(key, encoded).apply();
    }

    static String get(Context context, String key) {
        String encoded = prefs(context).getString(key, "");
        if (encoded == null || encoded.isEmpty()) return "";
        try {
            byte[] payload = Base64.decode(encoded, Base64.NO_WRAP);
            ByteBuffer buffer = ByteBuffer.wrap(payload);
            int ivLength = buffer.getInt();
            if (ivLength < 12 || ivLength > 16 || buffer.remaining() <= ivLength) return "";
            byte[] iv = new byte[ivLength];
            buffer.get(iv);
            byte[] encrypted = new byte[buffer.remaining()];
            buffer.get(encrypted);
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.DECRYPT_MODE, getOrCreateKey(), new GCMParameterSpec(128, iv));
            return new String(cipher.doFinal(encrypted), StandardCharsets.UTF_8);
        } catch (Exception e) {
            return "";
        }
    }

    static boolean has(Context context, String key) {
        return !get(context, key).isEmpty();
    }

    static void remove(Context context, String key) {
        prefs(context).edit().remove(key).apply();
    }

    private static SharedPreferences prefs(Context context) {
        return context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    private static SecretKey getOrCreateKey() throws Exception {
        KeyStore keyStore = KeyStore.getInstance(ANDROID_KEY_STORE);
        keyStore.load(null);
        KeyStore.Entry existing = keyStore.getEntry(KEY_ALIAS, null);
        if (existing instanceof KeyStore.SecretKeyEntry) {
            return ((KeyStore.SecretKeyEntry) existing).getSecretKey();
        }
        KeyGenerator generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, ANDROID_KEY_STORE);
        KeyGenParameterSpec spec = new KeyGenParameterSpec.Builder(
                KEY_ALIAS,
                KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setRandomizedEncryptionRequired(true)
                .setUserAuthenticationRequired(false)
                .build();
        generator.init(spec);
        return generator.generateKey();
    }
}
