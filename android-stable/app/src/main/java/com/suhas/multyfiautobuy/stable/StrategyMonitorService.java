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
    private static final int NOTIFICATION_ID = 1301;
    private static final TimeZone IST = TimeZone.getTimeZone("Asia/Kolkata");
    private static final int MARKET_START = 9 * 60 + 15;
    private static final int MARKET_END = 15 * 60 + 30;
    private static final int ENTRY_CUTOFF = 15 * 60 + 25;

    private ScheduledExecutorService executor;

    static void ensureRunning(Context context) {
        if (StrategyStore.activeCount(context) <= 0) return;
        Intent intent = new Intent(context, StrategyMonitorService.class);
        try {
            context.startForegroundService(intent);
        } catch (Exception e) {
            AppPrefs.log(context, "MONITOR START FAILED", e.getClass().getSimpleName() + ": " + e.getMessage());
        }
    }

    @Override
    public void onCreate() {
        super.onCreate();
        createChannel();
        startForeground(NOTIFICATION_ID, buildNotification("Starting staged trade monitor…"));
        executor = Executors.newSingleThreadScheduledExecutor();
        executor.scheduleWithFixedDelay(this::safeTick, 1, 5, TimeUnit.SECONDS);
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        updateNotification();
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
            if (active.isEmpty()) {
                stopSelf();
                return;
            }
            updateNotification();
            if (!isMarketSession()) return;
            if (!NetworkUtil.isNetworkAvailable(this) || !NetworkUtil.isVpnActive(this)) return;
            String token = TokenManager.validToken(this);
            if (token.isEmpty()) return;
            for (Strategy strategy : active) {
                try { processStrategy(token, strategy); }
                catch (Exception e) {
                    strategy.lastMessage = "Monitor error: " + e.getClass().getSimpleName() + ": " + e.getMessage();
                    strategy.updatedAt = System.currentTimeMillis();
                    StrategyStore.upsert(this, strategy);
                    AppPrefs.log(this, "STRATEGY MONITOR ERROR", strategy.symbol + " • " + strategy.lastMessage);
                }
            }
        } catch (Exception e) {
            AppPrefs.log(this, "MONITOR LOOP ERROR", e.getClass().getSimpleName() + ": " + e.getMessage());
        }
    }

    private void processStrategy(String token, Strategy strategy) {
        if (Strategy.CLOSED.equals(strategy.state) || Strategy.ERROR.equals(strategy.state)) return;

        GrowwClient.IntResult position = GrowwClient.getNetPositionQuantity(token, strategy.symbol);
        if (!position.success) return;
        int remaining = strategy.remainingStrategyQuantity(position.value);

        if (Strategy.TARGET_SELL_PENDING.equals(strategy.state)) {
            processTargetPending(token, strategy, remaining);
            return;
        }

        int filled = detectFilledQuantity(token, strategy, remaining);
        if (filled > strategy.observedFilledQuantity) {
            strategy.observedFilledQuantity = Math.min(strategy.requestedQuantity, filled);
            strategy.lastMessage = "Observed fill: " + strategy.observedFilledQuantity + " of " + strategy.requestedQuantity + ".";
            AppPrefs.log(this, "ENTRY FILL OBSERVED", strategy.symbol + " • " + strategy.lastMessage);
        }

        if (strategy.observedFilledQuantity > strategy.protectedQuantity) {
            if (!protectNewFill(token, strategy)) return;
        }

        if (remaining <= 0 && strategy.observedFilledQuantity > 0) {
            closeStrategy(strategy, "Position is no longer held; stop-loss or manual exit completed.");
            return;
        }

        if (isEntryCutoffReached(strategy.createdAt)
                && strategy.observedFilledQuantity < strategy.requestedQuantity
                && !strategy.entrySmartOrderId.isEmpty()) {
            GrowwClient.SmartStatus entry = GrowwClient.getGtt(token, strategy.entrySmartOrderId);
            if (entry.success && isActiveStatus(entry.status)) {
                GrowwClient.ApiResult cancelled = GrowwClient.cancelGtt(token, strategy.entrySmartOrderId);
                if (cancelled.success) {
                    strategy.lastMessage = "Unfilled entry remainder cancelled at the daily cutoff.";
                    strategy.entrySmartOrderId = "";
                    AppPrefs.log(this, "ENTRY REMAINDER CANCELLED", strategy.symbol + " • " + strategy.lastMessage);
                }
            }
        }

        if (strategy.observedFilledQuantity <= 0 || strategy.protectedQuantity < strategy.observedFilledQuantity) {
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

        GrowwClient.DoubleResult ltp = GrowwClient.getLtp(token, strategy.symbol);
        if (!ltp.success) {
            save(strategy);
            return;
        }
        if (ltp.value >= strategy.targetPrice) executeTarget(token, strategy);
        else {
            strategy.lastMessage = "Protected " + strategy.protectedQuantity + " shares • LTP ₹"
                    + money(ltp.value) + " • target ₹" + money(strategy.targetPrice) + ".";
            save(strategy);
        }
    }

    private int detectFilledQuantity(String token, Strategy strategy, int positionDelta) {
        int filled = Math.max(0, positionDelta);
        GrowwClient.OrderStatus order = GrowwClient.getOrderByReference(token, strategy.entryReferenceId);
        if (order.success) filled = Math.max(filled, order.filledQuantity);
        return Math.min(strategy.requestedQuantity, filled);
    }

    private boolean protectNewFill(String token, Strategy strategy) {
        int delta = strategy.observedFilledQuantity - strategy.protectedQuantity;
        if (delta <= 0) return true;
        int legNumber = strategy.stopLegs.size() + 1;
        GrowwClient.ApiResult stop = GrowwClient.createStopLossGtt(token, strategy, delta, legNumber);
        if (!stop.success) {
            AppPrefs.setArmed(this, false);
            strategy.lastMessage = "CRITICAL: " + delta + " newly filled shares could not be protected. " + stop.message;
            save(strategy);
            AppPrefs.log(this, "STOP-LOSS CREATION FAILED — AUTO-DISARMED", strategy.symbol + " • " + strategy.lastMessage);
            return false;
        }
        strategy.stopLegs.add(new Strategy.StopLeg(stop.id, delta, "ACTIVE"));
        strategy.protectedQuantity += delta;
        strategy.state = Strategy.PROTECTED;
        strategy.lastMessage = "Stop-loss GTT active for " + strategy.protectedQuantity + " filled shares.";
        save(strategy);
        AppPrefs.log(this, "STOP-LOSS ACTIVE", strategy.symbol + " • " + stop.message);
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

    private void executeTarget(String token, Strategy strategy) {
        for (Strategy.StopLeg leg : strategy.stopLegs) {
            GrowwClient.SmartStatus before = GrowwClient.getGtt(token, leg.smartOrderId);
            if (!before.success) {
                strategy.lastMessage = "Target reached, but stop-loss state could not be verified. No sell submitted.";
                save(strategy);
                return;
            }
            leg.status = before.status;
            if (isTriggeredStatus(before.status)) {
                strategy.lastMessage = "Target reached while a stop-loss was already triggered. Waiting; no duplicate sell.";
                save(strategy);
                return;
            }
            if ("CANCELLED".equalsIgnoreCase(before.status)) continue;
            if (!isActiveStatus(before.status)) {
                strategy.lastMessage = "Target reached, but stop-loss state is " + before.status + ". No sell submitted.";
                save(strategy);
                return;
            }
            GrowwClient.ApiResult cancel = GrowwClient.cancelGtt(token, leg.smartOrderId);
            if (!cancel.success) {
                strategy.lastMessage = "Target reached, but stop-loss cancellation failed. No sell submitted.";
                save(strategy);
                return;
            }
            GrowwClient.SmartStatus verified = GrowwClient.getGtt(token, leg.smartOrderId);
            if (!verified.success || !"CANCELLED".equalsIgnoreCase(verified.status)) {
                strategy.lastMessage = "Target reached, but stop-loss cancellation was not confirmed. No sell submitted.";
                save(strategy);
                return;
            }
            leg.status = "CANCELLED";
        }

        GrowwClient.IntResult position = GrowwClient.getNetPositionQuantity(token, strategy.symbol);
        if (!position.success) {
            strategy.lastMessage = "Stop-loss cancelled, but remaining position could not be verified. No sell submitted.";
            save(strategy);
            return;
        }
        int remaining = strategy.remainingStrategyQuantity(position.value);
        if (remaining <= 0) {
            closeStrategy(strategy, "Position was already closed before target sell submission.");
            return;
        }

        GrowwClient.ApiResult sell = GrowwClient.placeTargetMarketSell(token, strategy,
                Math.min(remaining, strategy.observedFilledQuantity));
        if (!sell.success) {
            strategy.protectedQuantity = 0;
            strategy.stopLegs.clear();
            strategy.state = Strategy.PROTECTED;
            strategy.lastMessage = "Target sell failed after stop-loss cancellation. Re-creating stop-loss protection. " + sell.message;
            save(strategy);
            AppPrefs.log(this, "TARGET SELL FAILED", strategy.symbol + " • " + strategy.lastMessage);
            protectNewFill(token, strategy);
            return;
        }
        strategy.targetOrderId = sell.id;
        strategy.targetOrderReferenceId = sell.secondaryId;
        strategy.state = Strategy.TARGET_SELL_PENDING;
        strategy.lastMessage = "Target reached. Stop-loss cancellation confirmed and CNC MARKET sell submitted.";
        save(strategy);
        AppPrefs.log(this, "TARGET SELL SUBMITTED", strategy.symbol + " • " + sell.message);
    }

    private void processTargetPending(String token, Strategy strategy, int remaining) {
        if (remaining <= 0) {
            closeStrategy(strategy, "Target-triggered sell completed.");
            return;
        }
        GrowwClient.OrderStatus status = GrowwClient.getOrderByReference(token, strategy.targetOrderReferenceId);
        if (!status.success) {
            strategy.lastMessage = "Target sell status unavailable; waiting to avoid duplicate selling.";
            save(strategy);
            return;
        }
        strategy.targetFilledQuantity = status.filledQuantity;
        if (isRejectedOrCancelled(status.status)) {
            strategy.observedFilledQuantity = remaining;
            strategy.protectedQuantity = 0;
            strategy.stopLegs.clear();
            strategy.targetOrderId = "";
            strategy.targetOrderReferenceId = "";
            strategy.state = Strategy.PROTECTED;
            strategy.lastMessage = "Target sell did not complete. Re-establishing stop-loss for " + remaining + " shares.";
            save(strategy);
            protectNewFill(token, strategy);
        } else {
            strategy.lastMessage = "Target sell pending • filled " + status.filledQuantity + " • remaining position " + remaining + ".";
            save(strategy);
        }
    }

    private void closeStrategy(Strategy strategy, String reason) {
        strategy.state = Strategy.CLOSED;
        strategy.lastMessage = reason;
        strategy.updatedAt = System.currentTimeMillis();
        StrategyStore.upsert(this, strategy);
        AppPrefs.log(this, "STRATEGY CLOSED", strategy.symbol + " • " + reason);
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

    private boolean isEntryCutoffReached(long createdAt) {
        Calendar now = Calendar.getInstance(IST, Locale.US);
        Calendar created = Calendar.getInstance(IST, Locale.US);
        created.setTimeInMillis(createdAt);
        boolean laterDay = now.get(Calendar.YEAR) != created.get(Calendar.YEAR)
                || now.get(Calendar.DAY_OF_YEAR) != created.get(Calendar.DAY_OF_YEAR);
        int minute = now.get(Calendar.HOUR_OF_DAY) * 60 + now.get(Calendar.MINUTE);
        return laterDay || minute >= ENTRY_CUTOFF;
    }

    private static boolean isActiveStatus(String status) {
        return "ACTIVE".equalsIgnoreCase(status) || "OPEN".equalsIgnoreCase(status)
                || "PENDING".equalsIgnoreCase(status);
    }

    private static boolean isTriggeredStatus(String status) {
        return "TRIGGERED".equalsIgnoreCase(status) || "COMPLETED".equalsIgnoreCase(status)
                || "COMPLETE".equalsIgnoreCase(status) || "EXECUTED".equalsIgnoreCase(status);
    }

    private static boolean isRejectedOrCancelled(String status) {
        return "REJECTED".equalsIgnoreCase(status) || "CANCELLED".equalsIgnoreCase(status)
                || "CANCELED".equalsIgnoreCase(status) || "FAILED".equalsIgnoreCase(status);
    }

    private void createChannel() {
        NotificationManager manager = getSystemService(NotificationManager.class);
        if (manager == null) return;
        NotificationChannel channel = new NotificationChannel(CHANNEL_ID,
                "Protected trade monitoring", NotificationManager.IMPORTANCE_LOW);
        channel.setDescription("Monitors entry fills, stop-loss GTT protection and target exits.");
        manager.createNotificationChannel(channel);
    }

    private Notification buildNotification(String text) {
        Intent open = new Intent(this, MainActivity.class);
        PendingIntent pending = PendingIntent.getActivity(this, 0, open,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        return new Notification.Builder(this, CHANNEL_ID)
                .setSmallIcon(R.drawable.ic_launcher)
                .setContentTitle("Multyfi AutoBuy monitoring")
                .setContentText(text)
                .setContentIntent(pending)
                .setOngoing(true)
                .setCategory(Notification.CATEGORY_SERVICE)
                .build();
    }

    private void updateNotification() {
        int active = StrategyStore.activeCount(this);
        String text = active + " active staged strateg" + (active == 1 ? "y" : "ies")
                + " • entry → stop-loss → target";
        NotificationManager manager = getSystemService(NotificationManager.class);
        if (manager != null) manager.notify(NOTIFICATION_ID, buildNotification(text));
    }

    private static String money(double value) {
        return Math.rint(value) == value ? String.format(Locale.US, "%.0f", value)
                : String.format(Locale.US, "%.2f", value);
    }
}
