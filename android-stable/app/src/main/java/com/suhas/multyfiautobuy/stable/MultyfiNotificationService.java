package com.suhas.multyfiautobuy.stable;

import android.app.Notification;
import android.os.Bundle;
import android.os.PowerManager;
import android.service.notification.NotificationListenerService;
import android.service.notification.StatusBarNotification;
import android.text.TextUtils;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class MultyfiNotificationService extends NotificationListenerService {
    private final ExecutorService executor = Executors.newSingleThreadExecutor();

    @Override
    public void onListenerConnected() {
        super.onListenerConnected();
        AppPrefs.log(this, "LISTENER READY",
                "Android connected the strict Multyfi recommendation listener.");
    }

    @Override
    public void onListenerDisconnected() {
        AppPrefs.log(this, "LISTENER DISCONNECTED",
                "Android disconnected the notification listener.");
        try {
            requestRebind(new android.content.ComponentName(this,
                    MultyfiNotificationService.class));
        } catch (Exception ignored) { }
        super.onListenerDisconnected();
    }

    @Override
    public void onNotificationPosted(StatusBarNotification sbn) {
        if (sbn == null || sbn.getNotification() == null) return;
        if (!AppPrefs.MULTYFI_PACKAGE.equals(sbn.getPackageName())) return;

        final long postTime = sbn.getPostTime();
        // Ignore promotional/pre-market/post-market noise before parsing anything.
        if (!SignalParser.isAllowedSignalTime(postTime)) return;

        final String rawText = extractText(sbn.getNotification());
        executor.execute(() -> process(rawText, postTime));
    }

    @Override
    public void onDestroy() {
        executor.shutdownNow();
        super.onDestroy();
    }

    private void process(String rawText, long postTime) {
        PowerManager.WakeLock wakeLock = null;
        try {
            PowerManager manager = (PowerManager) getSystemService(POWER_SERVICE);
            if (manager != null) {
                wakeLock = manager.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK,
                        getPackageName() + ":multyfi-protected-order");
                wakeLock.acquire(30_000L);
            }

            // Only a complete, internally valid recommendation is returned.
            SignalParser.ParsedSignal signal = SignalParser.parse(rawText, postTime);
            if (signal == null) return;

            final int quantity = AppPrefs.quantity(this);
            final String summary = signal.summary(quantity);

            if (!AppPrefs.isArmed(this)) {
                AppPrefs.log(this, "COMPLETE SIGNAL — DISARMED", summary);
                return;
            }

            long age = System.currentTimeMillis() - signal.notificationTimeMillis;
            if (age > AppPrefs.MAX_SIGNAL_AGE_MS || age < -60_000L) {
                AppPrefs.log(this, "REJECTED — STALE", summary + " • age " + age + " ms");
                return;
            }

            if (!AppPrefs.parserTestPassed(this)) {
                rejectAndDisarm("Parser acceptance test is not valid.", summary);
                return;
            }

            if (!AppPrefs.isAuthVerifiedToday(this)) {
                rejectAndDisarm("Groww account was not verified today.", summary);
                return;
            }

            if (!AppPrefs.isStaticConfirmed(this)
                    || AppPrefs.expectedIp(this).isEmpty()
                    || !AppPrefs.isIpRecentlyVerified(this)
                    || !NetworkUtil.isVpnActive(this)) {
                rejectAndDisarm("Turbo VPN/static-IP readiness is not valid.", summary);
                return;
            }

            if (!NetworkUtil.isNetworkAvailable(this)) {
                AppPrefs.log(this, "REJECTED — OFFLINE", summary);
                return;
            }

            if (AppPrefs.isProcessed(this, signal.eventId)) {
                AppPrefs.log(this, "DUPLICATE BLOCKED", summary);
                return;
            }

            if (AppPrefs.dailyBuyCount(this) >= AppPrefs.MAX_BUYS_PER_DAY) {
                rejectAndDisarm("Maximum three automatic buys reached for today.", summary);
                return;
            }

            if (signal.maximumOrderValue(quantity) > AppPrefs.MAX_ORDER_VALUE) {
                AppPrefs.log(this, "REJECTED — VALUE LIMIT", summary
                        + " • maximum value ₹"
                        + String.format(java.util.Locale.US, "%.2f",
                        signal.maximumOrderValue(quantity)));
                return;
            }

            String token = validAccessToken();
            if (token.isEmpty()) {
                AppPrefs.log(this, "REJECTED — AUTH", summary
                        + " • Groww token unavailable. Daily broker approval may be required.");
                return;
            }

            AppPrefs.log(this, "SUBMITTING PROTECTED GTT", summary);
            GrowwClient.ApiResult result = GrowwClient.createProtectedGtt(
                    token, signal, quantity);
            if (result.success) {
                AppPrefs.markProcessed(this, signal.eventId);
                AppPrefs.incrementDailyBuyCount(this);
                AppPrefs.log(this, "PROTECTED GTT ACCEPTED",
                        summary + "\n" + result.message);
            } else if ("GA007".equals(result.errorCode)) {
                AppPrefs.markProcessed(this, signal.eventId);
                AppPrefs.log(this, "DUPLICATE CONFIRMED", summary
                        + " • Groww rejected the repeated reference ID.");
            } else if ("PROTECTION_NOT_CONFIRMED".equals(result.errorCode)) {
                rejectAndDisarm(result.message, summary);
            } else {
                AppPrefs.log(this, "PROTECTED GTT FAILED",
                        summary + "\n" + result.message
                                + (result.errorCode.isEmpty()
                                ? "" : " [" + result.errorCode + "]"));
            }
        } catch (Exception e) {
            AppPrefs.log(this, "PROCESSING ERROR",
                    e.getClass().getSimpleName() + ": " + e.getMessage());
        } finally {
            if (wakeLock != null && wakeLock.isHeld()) wakeLock.release();
        }
    }

    private String validAccessToken() {
        String token = SecureStore.get(this, SecureStore.ACCESS_TOKEN);
        String tokenDate = SecureStore.get(this, SecureStore.ACCESS_TOKEN_DATE);
        if (!token.isEmpty() && AppPrefs.istDate().equals(tokenDate)) return token;

        String apiKey = SecureStore.get(this, SecureStore.API_KEY);
        String secret = SecureStore.get(this, SecureStore.TOTP_SECRET);
        GrowwClient.AuthResult auth = GrowwClient.authenticate(apiKey, secret);
        if (!auth.success) {
            AppPrefs.log(this, "TOKEN REFRESH FAILED", auth.message);
            return "";
        }
        try {
            SecureStore.put(this, SecureStore.ACCESS_TOKEN, auth.accessToken);
            SecureStore.put(this, SecureStore.ACCESS_TOKEN_DATE, AppPrefs.istDate());
            AppPrefs.log(this, "TOKEN REFRESHED",
                    "Groww access token generated from TOTP.");
            return auth.accessToken;
        } catch (Exception e) {
            AppPrefs.log(this, "TOKEN STORE FAILED", e.getMessage());
            return "";
        }
    }

    private void rejectAndDisarm(String reason, String summary) {
        AppPrefs.setArmed(this, false);
        AppPrefs.log(this, "REJECTED — AUTO-DISARMED", summary + "\n" + reason);
    }

    private static String extractText(Notification notification) {
        Bundle extras = notification.extras;
        if (extras == null) return "";
        List<String> parts = new ArrayList<>();
        add(parts, extras.getCharSequence(Notification.EXTRA_TITLE));
        add(parts, extras.getCharSequence(Notification.EXTRA_TEXT));
        add(parts, extras.getCharSequence(Notification.EXTRA_BIG_TEXT));
        add(parts, extras.getCharSequence(Notification.EXTRA_SUB_TEXT));
        CharSequence[] lines = extras.getCharSequenceArray(Notification.EXTRA_TEXT_LINES);
        if (lines != null) {
            for (CharSequence line : lines) add(parts, line);
        }
        return TextUtils.join("\n", parts);
    }

    private static void add(List<String> values, CharSequence value) {
        if (value == null) return;
        String text = value.toString().trim();
        if (!text.isEmpty() && !values.contains(text)) values.add(text);
    }
}
