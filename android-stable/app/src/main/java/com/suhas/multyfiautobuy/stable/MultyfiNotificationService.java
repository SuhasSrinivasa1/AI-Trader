package com.suhas.multyfiautobuy.stable;

import android.app.Notification;
import android.os.Bundle;
import android.os.PowerManager;
import android.service.notification.NotificationListenerService;
import android.service.notification.StatusBarNotification;
import android.text.TextUtils;

import java.util.ArrayList;
import java.util.Calendar;
import java.util.List;
import java.util.Locale;
import java.util.TimeZone;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class MultyfiNotificationService extends NotificationListenerService {
    private static final TimeZone IST = TimeZone.getTimeZone("Asia/Kolkata");
    private final ExecutorService executor = Executors.newSingleThreadExecutor();

    @Override
    public void onListenerConnected() {
        super.onListenerConnected();
        AppPrefs.log(this, "LISTENER READY",
                "Android connected the Multyfi complete-recommendation listener.");
        StrategyMonitorService.ensureRunning(this);
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
                        getPackageName() + ":multyfi-entry-gtt");
                wakeLock.acquire(35_000L);
            }

            double buffer = AppPrefs.entryBufferPercent(this);
            SignalParser.ParsedSignal signal = SignalParser.parse(
                    rawText, postTime, buffer);
            if (signal == null) return;
            int quantity = AppPrefs.quantity(this);
            String summary = signal.summary(quantity);

            if (!AppPrefs.isArmed(this)) {
                AppPrefs.log(this, "COMPLETE SIGNAL — DISARMED", summary);
                return;
            }
            long age = System.currentTimeMillis() - signal.notificationTimeMillis;
            if (age > AppPrefs.MAX_SIGNAL_AGE_MS || age < -60_000L) {
                AppPrefs.log(this, "REJECTED — STALE",
                        summary + " • age " + age + " ms");
                return;
            }
            if (!AppPrefs.parserTestPassed(this)) {
                rejectAndDisarm("Parser acceptance test is not valid.", summary);
                return;
            }
            if (!AppPrefs.isAuthVerifiedToday(this)) {
                rejectAndDisarm(
                        "Groww account and DDPI were not verified today.", summary);
                return;
            }
            if (!NetworkUtil.isNetworkAvailable(this)) {
                AppPrefs.log(this, "REJECTED — OFFLINE", summary);
                return;
            }
            if (!ensureStaticPublicIp()) {
                rejectAndDisarm(
                        "Current public IP does not match the Groww-whitelisted IP.",
                        summary);
                return;
            }
            if (AppPrefs.isProcessed(this, signal.eventId)
                    || StrategyStore.find(this, signal.eventId) != null) {
                AppPrefs.log(this, "DUPLICATE BLOCKED", summary);
                return;
            }
            if (AppPrefs.dailyBuyCount(this) >= AppPrefs.MAX_BUYS_PER_DAY) {
                rejectAndDisarm(
                        "Maximum four automatic entry GTTs reached for today.",
                        summary);
                return;
            }
            if (signal.maximumOrderValue(quantity) > AppPrefs.MAX_ORDER_VALUE) {
                AppPrefs.log(this, "REJECTED — VALUE LIMIT", summary
                        + " • maximum value ₹"
                        + String.format(Locale.US, "%.2f",
                        signal.maximumOrderValue(quantity)));
                return;
            }

            String token = TokenManager.validToken(this);
            if (token.isEmpty()) {
                AppPrefs.clearAuthVerified(this);
                rejectAndDisarm(
                        "Groww token unavailable. The broker's daily approval may be required.",
                        summary);
                return;
            }

            GrowwClient.DoubleResult ltp = GrowwClient.getLtp(
                    token, signal.symbol);
            if (!ltp.success) {
                AppPrefs.log(this, "ENTRY DEFERRED — LTP UNAVAILABLE",
                        summary + " • " + ltp.message);
                return;
            }

            GrowwClient.IntResult baseline = GrowwClient.getNetPositionQuantity(
                    token, signal.symbol, signal.productType);
            if (!baseline.success) {
                rejectAndDisarm("Could not establish the pre-trade "
                        + signal.productType + " position baseline: "
                        + baseline.message, summary);
                return;
            }

            AppPrefs.log(this, "SUBMITTING ENTRY GTT", summary
                    + " • LTP ₹" + String.format(Locale.US, "%.2f", ltp.value)
                    + " • baseline " + signal.productType + " position "
                    + baseline.value + ".");
            GrowwClient.ApiResult result = GrowwClient.createEntryGtt(
                    token, signal, quantity, ltp.value);
            if (result.success) {
                long lifecycleAnchor = lifecycleAnchor(signal);
                Strategy strategy = new Strategy(signal.eventId, signal.symbol,
                        signal.category, signal.productType, quantity,
                        signal.targetPrice, signal.stopLossPrice, baseline.value,
                        signal.referenceId, result.id, lifecycleAnchor);
                StrategyStore.upsert(this, strategy);
                AppPrefs.markProcessed(this, signal.eventId);
                AppPrefs.incrementDailyBuyCount(this);
                AppPrefs.log(this, "ENTRY GTT CONFIRMED", summary + "\n"
                        + result.message
                        + " Stop-loss will be created only for actual filled quantity."
                        + (lifecycleAnchor > System.currentTimeMillis() + 60_000L
                        ? " Off-hours CNC call is scheduled through the next trading session."
                        : ""));
                StrategyMonitorService.ensureRunning(this);
            } else if ("GA007".equals(result.errorCode)) {
                AppPrefs.markProcessed(this, signal.eventId);
                AppPrefs.log(this, "DUPLICATE CONFIRMED", summary
                        + " • Groww rejected the repeated reference ID.");
            } else {
                AppPrefs.log(this, "ENTRY GTT FAILED", summary + "\n"
                        + result.message + (result.errorCode.isEmpty()
                        ? "" : " [" + result.errorCode + "]"));
            }
        } catch (Exception e) {
            AppPrefs.log(this, "PROCESSING ERROR",
                    e.getClass().getSimpleName() + ": " + e.getMessage());
        } finally {
            if (wakeLock != null && wakeLock.isHeld()) wakeLock.release();
        }
    }

    private long lifecycleAnchor(SignalParser.ParsedSignal signal) {
        if (signal.isIntraday()) return signal.notificationTimeMillis;
        Calendar calendar = Calendar.getInstance(IST, Locale.US);
        calendar.setTimeInMillis(signal.notificationTimeMillis);
        int day = calendar.get(Calendar.DAY_OF_WEEK);
        int minute = calendar.get(Calendar.HOUR_OF_DAY) * 60
                + calendar.get(Calendar.MINUTE);
        boolean weekend = day == Calendar.SATURDAY || day == Calendar.SUNDAY;
        if (!weekend && minute < 15 * 60 + 25) {
            return signal.notificationTimeMillis;
        }
        do {
            calendar.add(Calendar.DAY_OF_MONTH, 1);
            day = calendar.get(Calendar.DAY_OF_WEEK);
        } while (day == Calendar.SATURDAY || day == Calendar.SUNDAY);
        calendar.set(Calendar.HOUR_OF_DAY, 9);
        calendar.set(Calendar.MINUTE, 0);
        calendar.set(Calendar.SECOND, 0);
        calendar.set(Calendar.MILLISECOND, 0);
        return calendar.getTimeInMillis();
    }

    private boolean ensureStaticPublicIp() {
        String expected = AppPrefs.expectedIp(this);
        if (!AppPrefs.isStaticConfirmed(this) || expected.isEmpty()) return false;
        if (AppPrefs.isIpRecentlyVerified(this)) return true;
        try {
            String actual = NetworkUtil.fetchPublicIp();
            boolean match = expected.equals(actual);
            AppPrefs.setIpVerification(this, actual, match);
            if (!match) {
                AppPrefs.log(this, "PUBLIC IP CHANGED",
                        "Expected " + expected + " but detected " + actual
                                + " over " + NetworkUtil.connectionLabel(this) + ".");
            }
            return match;
        } catch (Exception e) {
            AppPrefs.log(this, "PUBLIC IP CHECK FAILED", e.getMessage());
            return false;
        }
    }

    private void rejectAndDisarm(String reason, String summary) {
        AppPrefs.setArmed(this, false);
        AppPrefs.log(this, "REJECTED — AUTO-DISARMED",
                summary + "\n" + reason);
    }

    private static String extractText(Notification notification) {
        Bundle extras = notification.extras;
        if (extras == null) return "";
        List<String> parts = new ArrayList<>();
        add(parts, extras.getCharSequence(Notification.EXTRA_TITLE));
        add(parts, extras.getCharSequence(Notification.EXTRA_TEXT));
        add(parts, extras.getCharSequence(Notification.EXTRA_BIG_TEXT));
        add(parts, extras.getCharSequence(Notification.EXTRA_SUB_TEXT));
        CharSequence[] lines = extras.getCharSequenceArray(
                Notification.EXTRA_TEXT_LINES);
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
