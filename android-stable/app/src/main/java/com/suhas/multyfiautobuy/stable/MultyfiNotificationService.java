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
                "Android connected the Multyfi entry and early-exit listener.");
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
                        getPackageName() + ":multyfi-notification");
                wakeLock.acquire(45_000L);
            }

            List<Strategy> active = StrategyStore.active(this);
            SignalParser.EarlyExitSignal earlyExit = SignalParser.parseEarlyExit(
                    rawText, postTime, active);
            if (earlyExit != null) {
                queueEarlyExit(earlyExit);
                return;
            }
            if (SignalParser.containsEarlyExitPhrase(rawText)) {
                AppPrefs.log(this, "EARLY EXIT IGNORED — SYMBOL NOT UNIQUE",
                        "An exit phrase was detected, but it did not identify exactly one active strategy. No sell was submitted.\n"
                                + compact(rawText));
                return;
            }

            double buffer = AppPrefs.entryBufferPercent(this);
            SignalParser.ParsedSignal signal = SignalParser.parse(
                    rawText, postTime, buffer);
            if (signal == null) return;

            double budget = AppPrefs.tradeBudget(this);
            int quantity = AppPrefs.quantityForBudget(this, signal.maxBuyPrice);
            if (quantity < 1) {
                AppPrefs.log(this, "REJECTED — BUDGET BELOW ONE SHARE",
                        signal.symbol + " • maximum buy price ₹"
                                + String.format(Locale.US, "%.2f", signal.maxBuyPrice)
                                + " exceeds the configured ₹"
                                + String.format(Locale.US, "%.2f", budget)
                                + " trade budget.");
                return;
            }
            String summary = signal.summary(quantity, budget);

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
            if (!NetworkUtil.isVpnActive(this)) {
                rejectAndDisarm("Surfshark Dedicated IP VPN is not active.", summary);
                return;
            }
            if (!ensureStaticPublicIp()) {
                rejectAndDisarm(
                        "Current public IP does not match the Groww-whitelisted Surfshark Dedicated IP.",
                        summary);
                return;
            }
            if (AppPrefs.isProcessed(this, signal.eventId)
                    || StrategyStore.find(this, signal.eventId) != null) {
                AppPrefs.log(this, "DUPLICATE BLOCKED", summary);
                return;
            }
            if (StrategyStore.hasActiveSymbol(this, signal.symbol)) {
                AppPrefs.log(this, "REJECTED — SYMBOL ALREADY ACTIVE",
                        summary + " • an existing strategy for " + signal.symbol
                                + " is still active, preventing overlapping position accounting.");
                return;
            }
            if (AppPrefs.dailyBuyCount(this) >= AppPrefs.MAX_BUYS_PER_DAY) {
                rejectAndDisarm(
                        "Maximum four automatic entry GTTs reached for today.",
                        summary);
                return;
            }
            if (signal.maximumOrderValue(quantity) > budget + 0.01d
                    || signal.maximumOrderValue(quantity) > AppPrefs.MAX_ORDER_VALUE) {
                AppPrefs.log(this, "REJECTED — VALUE LIMIT", summary);
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

    private void queueEarlyExit(SignalParser.EarlyExitSignal signal) {
        long age = System.currentTimeMillis() - signal.notificationTimeMillis;
        if (age > AppPrefs.MAX_EARLY_EXIT_AGE_MS || age < -60_000L) {
            AppPrefs.log(this, "EARLY EXIT REJECTED — STALE",
                    signal.symbol + " • age " + age + " ms");
            return;
        }
        Strategy strategy = StrategyStore.find(this, signal.eventId);
        if (strategy == null || !strategy.isActive()) {
            AppPrefs.log(this, "EARLY EXIT IGNORED — NO ACTIVE STRATEGY",
                    signal.symbol + " • " + signal.phrase);
            return;
        }
        if (!NetworkUtil.isNetworkAvailable(this) || !NetworkUtil.isVpnActive(this)
                || !ensureStaticPublicIp()) {
            AppPrefs.log(this, "EARLY EXIT BLOCKED — SURFSHARK/IP NOT READY",
                    signal.symbol + " • the existing broker-side stop-loss remains active.");
            return;
        }
        String token = TokenManager.validToken(this);
        if (token.isEmpty()) {
            AppPrefs.log(this, "EARLY EXIT BLOCKED — GROWW AUTH UNAVAILABLE",
                    signal.symbol + " • the existing broker-side stop-loss remains active.");
            return;
        }
        if (!prepareEntryForEarlyExit(token, strategy)) {
            AppPrefs.log(this, "EARLY EXIT SAFETY PRECHECK FAILED",
                    signal.symbol + " • entry GTT/order remainder was not confirmed cancelled or terminal. No sell was queued to avoid a later duplicate buy.");
            return;
        }

        strategy.requestEarlyExit("Multyfi: " + signal.phrase,
                signal.notificationTimeMillis);
        StrategyStore.upsert(this, strategy);
        AppPrefs.log(this, "MULTYFI EARLY EXIT QUEUED",
                signal.symbol + " • " + signal.phrase
                        + " • entry remainder safe; immediate broker reconciliation requested.");
        StrategyMonitorService.requestImmediateTick(this, signal.eventId);
    }

    private boolean prepareEntryForEarlyExit(String token, Strategy strategy) {
        if (strategy.entrySmartOrderId == null || strategy.entrySmartOrderId.isEmpty()) {
            return true;
        }
        GrowwClient.SmartStatus smart = GrowwClient.getGtt(token,
                strategy.entrySmartOrderId);
        if (!smart.success) return false;

        if (isActiveSmartStatus(smart.status)) {
            GrowwClient.ApiResult cancel = GrowwClient.cancelGtt(token,
                    strategy.entrySmartOrderId);
            if (!cancel.success) return false;
            for (int i = 0; i < 5; i++) {
                GrowwClient.SmartStatus verified = GrowwClient.getGtt(token,
                        strategy.entrySmartOrderId);
                if (verified.success
                        && "CANCELLED".equalsIgnoreCase(verified.status)) {
                    strategy.entrySmartOrderId = "";
                    StrategyStore.upsert(this, strategy);
                    return true;
                }
                sleep(250L);
            }
            return false;
        }

        if ("CANCELLED".equalsIgnoreCase(smart.status)) {
            strategy.entrySmartOrderId = "";
            StrategyStore.upsert(this, strategy);
            return true;
        }

        if (isTriggeredSmartStatus(smart.status)) {
            GrowwClient.OrderStatus order = GrowwClient.getOrderByReference(
                    token, strategy.entryReferenceId);
            if (!order.success) return false;
            if (isOpenRegularOrderStatus(order.status)) {
                if (order.orderId == null || order.orderId.isEmpty()) return false;
                RegularOrderSafety.Result cancelled =
                        RegularOrderSafety.cancelOpenCashOrder(token, order.orderId);
                if (!cancelled.success) return false;
                for (int i = 0; i < 8; i++) {
                    order = GrowwClient.getOrderByReference(token,
                            strategy.entryReferenceId);
                    if (order.success && isTerminalRegularOrderStatus(order.status)) {
                        strategy.entrySmartOrderId = "";
                        StrategyStore.upsert(this, strategy);
                        return true;
                    }
                    sleep(300L);
                }
                return false;
            }
            if (isTerminalRegularOrderStatus(order.status)) {
                strategy.entrySmartOrderId = "";
                StrategyStore.upsert(this, strategy);
                return true;
            }
        }
        return false;
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
        if (!NetworkUtil.isVpnActive(this)) return false;
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

    private static boolean isActiveSmartStatus(String status) {
        return "ACTIVE".equalsIgnoreCase(status)
                || "OPEN".equalsIgnoreCase(status)
                || "PENDING".equalsIgnoreCase(status);
    }

    private static boolean isTriggeredSmartStatus(String status) {
        return "TRIGGERED".equalsIgnoreCase(status)
                || "COMPLETED".equalsIgnoreCase(status)
                || "COMPLETE".equalsIgnoreCase(status)
                || "EXECUTED".equalsIgnoreCase(status);
    }

    private static boolean isOpenRegularOrderStatus(String status) {
        return "NEW".equalsIgnoreCase(status)
                || "ACKED".equalsIgnoreCase(status)
                || "TRIGGER_PENDING".equalsIgnoreCase(status)
                || "APPROVED".equalsIgnoreCase(status)
                || "OPEN".equalsIgnoreCase(status)
                || "PENDING".equalsIgnoreCase(status)
                || "PARTIALLY_FILLED".equalsIgnoreCase(status)
                || "PARTIAL".equalsIgnoreCase(status)
                || "CANCELLATION_REQUESTED".equalsIgnoreCase(status);
    }

    private static boolean isTerminalRegularOrderStatus(String status) {
        return "EXECUTED".equalsIgnoreCase(status)
                || "DELIVERY_AWAITED".equalsIgnoreCase(status)
                || "CANCELLED".equalsIgnoreCase(status)
                || "CANCELED".equalsIgnoreCase(status)
                || "COMPLETED".equalsIgnoreCase(status)
                || "COMPLETE".equalsIgnoreCase(status)
                || "REJECTED".equalsIgnoreCase(status)
                || "FAILED".equalsIgnoreCase(status);
    }

    private static void sleep(long millis) {
        try { Thread.sleep(millis); }
        catch (InterruptedException e) { Thread.currentThread().interrupt(); }
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

    private static String compact(String text) {
        if (text == null) return "";
        String value = text.replace('\n', ' ').replace('\r', ' ').trim();
        return value.length() <= 300 ? value : value.substring(0, 300) + "…";
    }
}
