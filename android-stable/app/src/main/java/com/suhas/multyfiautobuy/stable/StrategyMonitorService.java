package com.suhas.multyfiautobuy.stable;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.os.IBinder;

import java.util.Calendar;
import java.util.List;
import java.util.Locale;
import java.util.TimeZone;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

public final class StrategyMonitorService extends Service {
    private static final String CHANNEL_ID = "staged_trade_monitor";
    private static final int NOTIFICATION_ID = 1601;
    private static final String ACTION_IMMEDIATE_TICK = "multyfi.action.IMMEDIATE_TICK";
    private static final String EXTRA_EVENT_ID = "event_id";

    private static final String EXIT_TARGET = "TARGET";
    private static final String EXIT_INTRADAY_TIME = "INTRADAY_TIME";
    private static final String EXIT_MULTYFI_EARLY = "MULTYFI_EARLY";

    private static final TimeZone IST = TimeZone.getTimeZone("Asia/Kolkata");
    private static final int MARKET_START = 9 * 60 + 15;
    private static final int MARKET_END = 15 * 60 + 30;
    private static final int CNC_ENTRY_CUTOFF = 15 * 60 + 25;
    private static final int MIS_ENTRY_CUTOFF = 14 * 60 + 45;
    private static final int MIS_FORCE_EXIT = 15 * 60 + 10;
    private static final long IP_CHECK_INTERVAL_MS = 60_000L;
    private static final long AUTH_CHECK_INTERVAL_MS = 5L * 60L * 1000L;

    private ScheduledExecutorService executor;
    private long lastIpCheckAt;
    private long lastAuthCheckAt;

    static void ensureRunning(Context context) {
        if (!AppPrefs.isArmed(context) && StrategyStore.activeCount(context) <= 0) return;
        start(context, null);
    }

    static void requestImmediateTick(Context context, String eventId) {
        Intent intent = new Intent(context, StrategyMonitorService.class);
        intent.setAction(ACTION_IMMEDIATE_TICK);
        intent.putExtra(EXTRA_EVENT_ID, eventId == null ? "" : eventId);
        try {
            context.startForegroundService(intent);
        } catch (Exception e) {
            AppPrefs.log(context, "IMMEDIATE MONITOR START FAILED",
                    e.getClass().getSimpleName() + ": " + e.getMessage());
        }
    }

    private static void start(Context context, Intent supplied) {
        Intent intent = supplied == null
                ? new Intent(context, StrategyMonitorService.class) : supplied;
        try {
            context.startForegroundService(intent);
        } catch (Exception e) {
            AppPrefs.log(context, "MONITOR START FAILED",
                    e.getClass().getSimpleName() + ": " + e.getMessage());
        }
    }

    @Override
    public void onCreate() {
        super.onCreate();
        createChannel();
        startForeground(NOTIFICATION_ID,
                buildNotification("Starting S24 Ultra autonomous monitor…"));
        executor = Executors.newSingleThreadScheduledExecutor();
        executor.scheduleWithFixedDelay(this::safeTick, 0, 2, TimeUnit.SECONDS);
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        updateNotification();
        if (intent != null && ACTION_IMMEDIATE_TICK.equals(intent.getAction())
                && executor != null) {
            executor.execute(this::safeTick);
        }
        return START_STICKY;
    }

    @Override
    public void onDestroy() {
        if (executor != null) executor.shutdownNow();
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) { return null; }

    private void safeTick() {
        try {
            List<Strategy> active = StrategyStore.active(this);
            if (active.isEmpty() && !AppPrefs.isArmed(this)) {
                stopSelf();
                return;
            }

            boolean networkReady = NetworkUtil.isNetworkAvailable(this);
            boolean vpnReady = networkReady && NetworkUtil.isVpnActive(this);
            boolean staticIpReady = vpnReady && refreshPublicIpIfDue();
            if (!vpnReady && AppPrefs.isArmed(this)) {
                AppPrefs.setArmed(this, false);
                AppPrefs.log(this, "SURFSHARK VPN LOST — AUTO-DISARMED",
                        "New entries are disabled because Android no longer reports an active VPN. Existing broker-side stop-loss GTTs remain active.");
            }
            preflightAuthenticationIfDue(networkReady);
            updateNotification();

            if (active.isEmpty() || !networkReady) return;
            String token = TokenManager.validToken(this);
            if (token.isEmpty()) {
                AppPrefs.clearAuthVerified(this);
                if (AppPrefs.isArmed(this)) {
                    AppPrefs.setArmed(this, false);
                    AppPrefs.log(this, "AUTH LOST — AUTO-DISARMED",
                            "Groww access token is unavailable. Daily approval may be required.");
                }
                return;
            }

            for (Strategy strategy : active) {
                try {
                    processStrategy(token, strategy, staticIpReady);
                } catch (Exception e) {
                    strategy.lastMessage = "Monitor error: "
                            + e.getClass().getSimpleName() + ": " + e.getMessage();
                    save(strategy);
                    AppPrefs.log(this, "STRATEGY MONITOR ERROR",
                            strategy.symbol + " • " + strategy.lastMessage);
                }
            }
        } catch (Exception e) {
            AppPrefs.log(this, "MONITOR LOOP ERROR",
                    e.getClass().getSimpleName() + ": " + e.getMessage());
        }
    }

    private boolean refreshPublicIpIfDue() {
        String expected = AppPrefs.expectedIp(this);
        if (!AppPrefs.isStaticConfirmed(this) || expected.isEmpty()) return false;
        long now = System.currentTimeMillis();
        if (now - lastIpCheckAt < IP_CHECK_INTERVAL_MS
                && AppPrefs.isIpRecentlyVerified(this)) return true;
        lastIpCheckAt = now;
        try {
            String actual = NetworkUtil.fetchPublicIp();
            boolean match = expected.equals(actual);
            AppPrefs.setIpVerification(this, actual, match);
            if (!match && AppPrefs.isArmed(this)) {
                AppPrefs.setArmed(this, false);
                AppPrefs.log(this, "PUBLIC IP CHANGED — AUTO-DISARMED",
                        "Expected Groww-whitelisted Surfshark Dedicated IP "
                                + expected + " but detected " + actual
                                + ". Existing broker-side stop-loss GTTs remain active.");
            }
            return match;
        } catch (Exception e) {
            AppPrefs.setIpVerifiedAt(this, 0L);
            AppPrefs.log(this, "PUBLIC IP CHECK FAILED", e.getMessage());
            return false;
        }
    }

    private void preflightAuthenticationIfDue(boolean networkReady) {
        if (!networkReady || !isPreflightWindow()) return;
        long now = System.currentTimeMillis();
        if (AppPrefs.isAuthVerifiedToday(this)
                || now - lastAuthCheckAt < AUTH_CHECK_INTERVAL_MS) return;
        lastAuthCheckAt = now;
        String token = TokenManager.validToken(this);
        if (token.isEmpty()) {
            if (isAfterNine() && AppPrefs.isArmed(this)) {
                AppPrefs.setArmed(this, false);
                AppPrefs.log(this, "DAILY APPROVAL REQUIRED — AUTO-DISARMED",
                        "Groww token could not be generated automatically. Complete any broker-required approval.");
            }
            return;
        }
        GrowwClient.ApiResult profile = GrowwClient.verifyProfile(token);
        if (profile.success) {
            AppPrefs.setAuthVerified(this, profile.id);
            AppPrefs.log(this, "AUTOMATIC PREFLIGHT READY", profile.message);
        } else if (isAfterNine() && AppPrefs.isArmed(this)) {
            AppPrefs.setArmed(this, false);
            AppPrefs.log(this, "BROKER PREFLIGHT FAILED — AUTO-DISARMED",
                    profile.message);
        }
    }

    private void processStrategy(String token, Strategy strategy,
                                 boolean staticIpReady) {
        if (Strategy.CLOSED.equals(strategy.state)
                || Strategy.ERROR.equals(strategy.state)) return;

        GrowwClient.IntResult position = GrowwClient.getNetPositionQuantity(
                token, strategy.symbol, strategy.productType);
        if (!position.success) return;
        int remaining = strategy.remainingStrategyQuantity(position.value);

        if (Strategy.TARGET_SELL_PENDING.equals(strategy.state)) {
            processExitPending(token, strategy, remaining, staticIpReady);
            return;
        }

        int filled = detectFilledQuantity(token, strategy, remaining);
        if (filled > strategy.observedFilledQuantity) {
            strategy.observedFilledQuantity = Math.min(strategy.requestedQuantity, filled);
            strategy.lastMessage = "Observed " + strategy.productType + " fill: "
                    + strategy.observedFilledQuantity + " of "
                    + strategy.requestedQuantity + ".";
            AppPrefs.log(this, "ENTRY FILL OBSERVED",
                    strategy.symbol + " • " + strategy.lastMessage);
        }

        if (strategy.earlyExitRequested) {
            processEarlyExit(token, strategy, remaining, staticIpReady);
            return;
        }

        if (strategy.observedFilledQuantity > strategy.protectedQuantity) {
            if (!staticIpReady) {
                AppPrefs.setArmed(this, false);
                strategy.lastMessage = "CRITICAL: Newly filled shares require stop-loss protection, but Surfshark/IP readiness is invalid.";
                save(strategy);
                AppPrefs.log(this, "UNPROTECTED FILL — NETWORK GATE FAILED",
                        strategy.symbol + " • " + strategy.lastMessage);
                return;
            }
            if (!protectNewFill(token, strategy)) return;
        }

        if (remaining <= 0 && strategy.observedFilledQuantity > 0) {
            closeStrategy(strategy,
                    "Position is no longer held; stop-loss, target, timed, early or manual exit completed.");
            return;
        }

        if (isEntryCutoffReached(strategy)
                && strategy.observedFilledQuantity < strategy.requestedQuantity
                && strategy.hasPendingEntryHandle()) {
            if (staticIpReady) cancelEntryRemainder(token, strategy);
            else strategy.lastMessage = "Entry cutoff reached, but entry cancellation is blocked by Surfshark/IP mismatch.";
        }

        if (strategy.observedFilledQuantity <= 0) {
            if (isEntryCutoffReached(strategy) && !strategy.hasPendingEntryHandle()) {
                closeStrategy(strategy, "Entry order expired/cancelled without a fill.");
            } else {
                strategy.state = Strategy.ENTRY_ACTIVE;
                save(strategy);
            }
            return;
        }

        if (strategy.protectedQuantity < strategy.observedFilledQuantity) {
            strategy.state = Strategy.ENTRY_ACTIVE;
            save(strategy);
            return;
        }

        strategy.state = Strategy.PROTECTED;
        if (anyStopLegTriggered(token, strategy)) {
            strategy.lastMessage = "Stop-loss GTT has triggered; waiting for position settlement.";
            save(strategy);
            return;
        }

        if (!isMarketSession()) return;
        if (strategy.isIntraday() && isIntradayForceExitTime()) {
            executeExit(token, strategy, staticIpReady, EXIT_INTRADAY_TIME);
            return;
        }

        GrowwClient.DoubleResult ltp = GrowwClient.getLtp(token, strategy.symbol);
        if (!ltp.success) {
            save(strategy);
            return;
        }
        if (ltp.value >= strategy.targetPrice) {
            executeExit(token, strategy, staticIpReady, EXIT_TARGET);
        } else {
            strategy.lastMessage = "Protected " + strategy.protectedQuantity + " "
                    + strategy.productType + " shares • LTP ₹" + money(ltp.value)
                    + " • target ₹" + money(strategy.targetPrice) + ".";
            save(strategy);
        }
    }

    private void processEarlyExit(String token, Strategy strategy, int remaining,
                                  boolean staticIpReady) {
        if (!isMarketSession()) {
            strategy.lastMessage = "Multyfi early exit is queued for the next market session; broker-side protection remains active.";
            save(strategy);
            return;
        }
        if (!staticIpReady) {
            strategy.lastMessage = "Multyfi early exit requested, but Surfshark Dedicated IP is not verified. Protection remains active; no sell submitted.";
            save(strategy);
            return;
        }

        if (!cancelEntryAndVerify(token, strategy)) {
            strategy.lastMessage = "Early exit requested, but the entry order/remainder could not be confirmed cancelled. No sell submitted to avoid a later duplicate buy.";
            save(strategy);
            return;
        }

        GrowwClient.IntResult refreshed = GrowwClient.getNetPositionQuantity(
                token, strategy.symbol, strategy.productType);
        if (!refreshed.success) {
            strategy.lastMessage = "Entry order cancelled, but position could not be verified for early exit.";
            save(strategy);
            return;
        }
        remaining = strategy.remainingStrategyQuantity(refreshed.value);
        int filled = detectFilledQuantity(token, strategy, remaining);
        strategy.observedFilledQuantity = Math.max(strategy.observedFilledQuantity,
                Math.min(strategy.requestedQuantity, filled));
        if (remaining <= 0) {
            closeStrategy(strategy,
                    "Multyfi early exit cancelled the unfilled entry; no position existed.");
            return;
        }
        executeExit(token, strategy, true, EXIT_MULTYFI_EARLY);
    }

    private int detectFilledQuantity(String token, Strategy strategy,
                                     int positionDelta) {
        int filled = Math.max(0, positionDelta);
        GrowwClient.OrderStatus order = GrowwClient.getOrderByReference(
                token, strategy.entryReferenceId);
        if (order.success) filled = Math.max(filled, order.filledQuantity);
        return Math.min(strategy.requestedQuantity, filled);
    }

    private boolean protectNewFill(String token, Strategy strategy) {
        int delta = strategy.observedFilledQuantity - strategy.protectedQuantity;
        if (delta <= 0) return true;
        int legNumber = strategy.stopLegs.size() + 1;
        GrowwClient.ApiResult stop = GrowwClient.createStopLossGtt(
                token, strategy, delta, legNumber);
        if (!stop.success) {
            AppPrefs.setArmed(this, false);
            strategy.lastMessage = "CRITICAL: " + delta
                    + " newly filled shares could not be protected. " + stop.message;
            save(strategy);
            AppPrefs.log(this, "STOP-LOSS CREATION FAILED — AUTO-DISARMED",
                    strategy.symbol + " • " + strategy.lastMessage);
            return false;
        }
        strategy.stopLegs.add(new Strategy.StopLeg(stop.id, delta, "ACTIVE"));
        strategy.protectedQuantity += delta;
        strategy.state = Strategy.PROTECTED;
        strategy.lastMessage = "Stop-loss GTT confirmed for "
                + strategy.protectedQuantity + " filled "
                + strategy.productType + " shares.";
        save(strategy);
        AppPrefs.log(this, "STOP-LOSS CONFIRMED ACTIVE",
                strategy.symbol + " • " + stop.message);
        return true;
    }

    private boolean anyStopLegTriggered(String token, Strategy strategy) {
        for (Strategy.StopLeg leg : strategy.stopLegs) {
            GrowwClient.SmartStatus status = GrowwClient.getGtt(token, leg.smartOrderId);
            if (!status.success) continue;
            leg.status = status.status;
            if (isTriggeredStatus(status.status)) {
                save(strategy);
                return true;
            }
        }
        return false;
    }

    private void cancelEntryRemainder(String token, Strategy strategy) {
        if (cancelEntryAndVerify(token, strategy)) {
            strategy.lastMessage = "Unfilled entry remainder cancelled and verified at the configured window cutoff.";
            AppPrefs.log(this, "ENTRY REMAINDER CANCELLED",
                    strategy.symbol + " • " + strategy.lastMessage);
        }
        save(strategy);
    }

    private boolean cancelEntryAndVerify(String token, Strategy strategy) {
        if (strategy.entryOrderId != null && !strategy.entryOrderId.isEmpty()) {
            GrowwClient.OrderStatus order = GrowwClient.getOrderByReference(
                    token, strategy.entryReferenceId);
            if (!order.success) return false;
            if (isTerminalRegularOrderStatus(order.status)) {
                strategy.entryOrderId = "";
                save(strategy);
                return true;
            }
            if (!isOpenRegularOrderStatus(order.status)) return false;
            String orderId = order.orderId.isEmpty()
                    ? strategy.entryOrderId : order.orderId;
            RegularOrderSafety.Result cancelled =
                    RegularOrderSafety.cancelOpenCashOrder(token, orderId);
            if (!cancelled.success) return false;
            for (int i = 0; i < 8; i++) {
                order = GrowwClient.getOrderByReference(token,
                        strategy.entryReferenceId);
                if (order.success && isTerminalRegularOrderStatus(order.status)) {
                    strategy.entryOrderId = "";
                    save(strategy);
                    return true;
                }
                sleep(250L);
            }
            return false;
        }

        if (strategy.entrySmartOrderId == null || strategy.entrySmartOrderId.isEmpty()) {
            return true;
        }
        GrowwClient.SmartStatus entry = GrowwClient.getGtt(token,
                strategy.entrySmartOrderId);
        if (!entry.success) return false;
        if (isTriggeredStatus(entry.status) || "CANCELLED".equalsIgnoreCase(entry.status)) {
            strategy.entrySmartOrderId = "";
            save(strategy);
            return true;
        }
        if (!isActiveStatus(entry.status)) return false;
        GrowwClient.ApiResult cancelled = GrowwClient.cancelGtt(
                token, strategy.entrySmartOrderId);
        if (!cancelled.success) return false;
        for (int i = 0; i < 5; i++) {
            GrowwClient.SmartStatus verified = GrowwClient.getGtt(token,
                    strategy.entrySmartOrderId);
            if (verified.success && "CANCELLED".equalsIgnoreCase(verified.status)) {
                strategy.entrySmartOrderId = "";
                save(strategy);
                return true;
            }
            sleep(250L);
        }
        return false;
    }

    private void executeExit(String token, Strategy strategy,
                             boolean staticIpReady, String exitType) {
        String label = exitLabel(exitType);
        if (!staticIpReady) {
            strategy.lastMessage = label
                    + " requested, but Surfshark Dedicated IP is not verified. Stop-loss remains active; no sell submitted.";
            save(strategy);
            return;
        }

        for (Strategy.StopLeg leg : strategy.stopLegs) {
            GrowwClient.SmartStatus before = GrowwClient.getGtt(token,
                    leg.smartOrderId);
            if (!before.success) {
                strategy.lastMessage = label + " requested, but stop-loss state could not be verified. No sell submitted.";
                save(strategy);
                return;
            }
            leg.status = before.status;
            if (isTriggeredStatus(before.status)) {
                strategy.lastMessage = label + " requested while stop-loss was already triggered. Waiting; no duplicate sell.";
                save(strategy);
                return;
            }
            if ("CANCELLED".equalsIgnoreCase(before.status)) continue;
            if (!isActiveStatus(before.status)) {
                strategy.lastMessage = label + " requested, but stop-loss state is "
                        + before.status + ". No sell submitted.";
                save(strategy);
                return;
            }
            GrowwClient.ApiResult cancel = GrowwClient.cancelGtt(token,
                    leg.smartOrderId);
            if (!cancel.success) {
                strategy.lastMessage = label + " requested, but stop-loss cancellation failed. No sell submitted.";
                save(strategy);
                return;
            }
            GrowwClient.SmartStatus verified = GrowwClient.getGtt(token,
                    leg.smartOrderId);
            if (!verified.success
                    || !"CANCELLED".equalsIgnoreCase(verified.status)) {
                strategy.lastMessage = label + " requested, but stop-loss cancellation was not confirmed. No sell submitted.";
                save(strategy);
                return;
            }
            leg.status = "CANCELLED";
        }

        GrowwClient.IntResult position = GrowwClient.getNetPositionQuantity(
                token, strategy.symbol, strategy.productType);
        if (!position.success) {
            strategy.lastMessage = "Stop-loss cancelled, but remaining position could not be verified. No sell submitted.";
            save(strategy);
            return;
        }
        int remaining = strategy.remainingStrategyQuantity(position.value);
        if (remaining <= 0) {
            closeStrategy(strategy,
                    "Position was already closed before "
                            + label.toLowerCase(Locale.US) + " submission.");
            return;
        }

        int sellQuantity = Math.min(remaining,
                Math.max(strategy.observedFilledQuantity, remaining));
        GrowwClient.ApiResult sell;
        if (EXIT_INTRADAY_TIME.equals(exitType)) {
            sell = GrowwClient.placeTimedMarketSell(token, strategy, sellQuantity);
        } else if (EXIT_MULTYFI_EARLY.equals(exitType)) {
            sell = GrowwClient.placeEarlyExitMarketSell(token, strategy, sellQuantity);
        } else {
            sell = GrowwClient.placeTargetMarketSell(token, strategy, sellQuantity);
        }
        if (!sell.success) {
            strategy.protectedQuantity = 0;
            strategy.stopLegs.clear();
            strategy.state = Strategy.PROTECTED;
            strategy.lastMessage = label
                    + " sell failed after stop-loss cancellation. Re-creating protection. "
                    + sell.message;
            save(strategy);
            AppPrefs.log(this, "EXIT SELL FAILED",
                    strategy.symbol + " • " + strategy.lastMessage);
            protectNewFill(token, strategy);
            return;
        }
        strategy.targetOrderId = sell.id;
        strategy.targetOrderReferenceId = sell.secondaryId;
        strategy.pendingExitLabel = label;
        strategy.earlyExitRequested = false;
        strategy.state = Strategy.TARGET_SELL_PENDING;
        strategy.lastMessage = label
                + ": stop-loss cancellation confirmed and "
                + strategy.productType + " MARKET sell submitted.";
        save(strategy);
        AppPrefs.log(this, EXIT_MULTYFI_EARLY.equals(exitType)
                        ? "MULTYFI EARLY EXIT SUBMITTED"
                        : EXIT_INTRADAY_TIME.equals(exitType)
                        ? "INTRADAY EXIT SUBMITTED" : "TARGET SELL SUBMITTED",
                strategy.symbol + " • " + sell.message);
    }

    private void processExitPending(String token, Strategy strategy,
                                    int remaining, boolean staticIpReady) {
        if (remaining <= 0) {
            closeStrategy(strategy, strategy.pendingExitLabel.isEmpty()
                    ? "Exit sell completed." : strategy.pendingExitLabel + " completed.");
            return;
        }
        GrowwClient.OrderStatus status = GrowwClient.getOrderByReference(
                token, strategy.targetOrderReferenceId);
        if (!status.success) {
            strategy.lastMessage = "Exit sell status unavailable; waiting to avoid duplicate selling.";
            save(strategy);
            return;
        }
        strategy.targetFilledQuantity = status.filledQuantity;
        if (isRejectedOrCancelled(status.status)) {
            boolean retryEarly = strategy.pendingExitLabel.toLowerCase(Locale.US)
                    .contains("early");
            strategy.observedFilledQuantity = remaining;
            strategy.protectedQuantity = 0;
            strategy.stopLegs.clear();
            strategy.targetOrderId = "";
            strategy.targetOrderReferenceId = "";
            strategy.pendingExitLabel = "";
            strategy.state = Strategy.PROTECTED;
            strategy.earlyExitRequested = retryEarly;
            strategy.lastMessage = "Exit sell did not complete. Re-establishing stop-loss for "
                    + remaining + " shares.";
            save(strategy);
            if (staticIpReady) protectNewFill(token, strategy);
        } else {
            strategy.lastMessage = "Exit sell pending • filled "
                    + status.filledQuantity + " • remaining position "
                    + remaining + ".";
            save(strategy);
        }
    }

    private void closeStrategy(Strategy strategy, String reason) {
        strategy.state = Strategy.CLOSED;
        strategy.earlyExitRequested = false;
        strategy.lastMessage = reason;
        strategy.updatedAt = System.currentTimeMillis();
        StrategyStore.upsert(this, strategy);
        AppPrefs.log(this, "STRATEGY CLOSED",
                strategy.symbol + " • " + reason);
    }

    private void save(Strategy strategy) {
        strategy.updatedAt = System.currentTimeMillis();
        StrategyStore.upsert(this, strategy);
    }

    private boolean isMarketSession() {
        Calendar c = Calendar.getInstance(IST, Locale.US);
        int day = c.get(Calendar.DAY_OF_WEEK);
        if (day == Calendar.SATURDAY || day == Calendar.SUNDAY) return false;
        int minute = c.get(Calendar.HOUR_OF_DAY) * 60 + c.get(Calendar.MINUTE);
        return minute >= MARKET_START && minute <= MARKET_END;
    }

    private boolean isPreflightWindow() {
        Calendar c = Calendar.getInstance(IST, Locale.US);
        int day = c.get(Calendar.DAY_OF_WEEK);
        if (day == Calendar.SATURDAY || day == Calendar.SUNDAY) return false;
        int minute = c.get(Calendar.HOUR_OF_DAY) * 60 + c.get(Calendar.MINUTE);
        return minute >= 8 * 60 + 35 && minute <= MARKET_END;
    }

    private boolean isAfterNine() {
        Calendar c = Calendar.getInstance(IST, Locale.US);
        return c.get(Calendar.HOUR_OF_DAY) * 60 + c.get(Calendar.MINUTE)
                >= 9 * 60;
    }

    private boolean isEntryCutoffReached(Strategy strategy) {
        if (strategy.entryCancelAt > 0L) {
            return System.currentTimeMillis() >= strategy.entryCancelAt;
        }
        Calendar now = Calendar.getInstance(IST, Locale.US);
        Calendar created = Calendar.getInstance(IST, Locale.US);
        created.setTimeInMillis(strategy.createdAt);
        boolean laterDay = now.get(Calendar.YEAR) != created.get(Calendar.YEAR)
                || now.get(Calendar.DAY_OF_YEAR) != created.get(Calendar.DAY_OF_YEAR);
        int minute = now.get(Calendar.HOUR_OF_DAY) * 60 + now.get(Calendar.MINUTE);
        int cutoff = strategy.isIntraday() ? MIS_ENTRY_CUTOFF : CNC_ENTRY_CUTOFF;
        return laterDay || minute >= cutoff;
    }

    private boolean isIntradayForceExitTime() {
        Calendar now = Calendar.getInstance(IST, Locale.US);
        int minute = now.get(Calendar.HOUR_OF_DAY) * 60 + now.get(Calendar.MINUTE);
        return minute >= MIS_FORCE_EXIT;
    }

    private static boolean isActiveStatus(String status) {
        return "ACTIVE".equalsIgnoreCase(status)
                || "OPEN".equalsIgnoreCase(status)
                || "PENDING".equalsIgnoreCase(status);
    }

    private static boolean isTriggeredStatus(String status) {
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

    private static boolean isRejectedOrCancelled(String status) {
        return "REJECTED".equalsIgnoreCase(status)
                || "CANCELLED".equalsIgnoreCase(status)
                || "CANCELED".equalsIgnoreCase(status)
                || "FAILED".equalsIgnoreCase(status);
    }

    private static String exitLabel(String type) {
        if (EXIT_MULTYFI_EARLY.equals(type)) return "Multyfi early exit";
        if (EXIT_INTRADAY_TIME.equals(type)) return "Intraday time exit";
        return "Target exit";
    }

    private static void sleep(long millis) {
        try { Thread.sleep(millis); }
        catch (InterruptedException e) { Thread.currentThread().interrupt(); }
    }

    private void createChannel() {
        NotificationManager manager = getSystemService(NotificationManager.class);
        if (manager == null) return;
        NotificationChannel channel = new NotificationChannel(CHANNEL_ID,
                "Autonomous trade protection", NotificationManager.IMPORTANCE_LOW);
        channel.setDescription("Monitors immediate Multyfi entries, early exits, Groww fills, stop-loss GTTs, targets, authentication and Surfshark Dedicated IP.");
        manager.createNotificationChannel(channel);
    }

    private Notification buildNotification(String text) {
        Intent open = new Intent(this, MainActivity.class);
        PendingIntent pending = PendingIntent.getActivity(this, 0, open,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        return new Notification.Builder(this, CHANNEL_ID)
                .setSmallIcon(R.drawable.ic_launcher)
                .setContentTitle("Multyfi AutoBuy S24 monitor")
                .setContentText(text)
                .setContentIntent(pending)
                .setOngoing(true)
                .setCategory(Notification.CATEGORY_SERVICE)
                .build();
    }

    private void updateNotification() {
        int active = StrategyStore.activeCount(this);
        String ip = AppPrefs.lastPublicIp(this);
        String text = (AppPrefs.isArmed(this) ? "Entries armed" : "New entries off")
                + " • " + active + " active strateg" + (active == 1 ? "y" : "ies")
                + " • Surfshark " + (NetworkUtil.isVpnActive(this) ? "on" : "off")
                + " • IP " + (ip.isEmpty() ? "unchecked" : ip);
        NotificationManager manager = getSystemService(NotificationManager.class);
        if (manager != null) manager.notify(NOTIFICATION_ID,
                buildNotification(text));
    }

    private static String money(double value) {
        return Math.rint(value) == value
                ? String.format(Locale.US, "%.0f", value)
                : String.format(Locale.US, "%.2f", value);
    }
}