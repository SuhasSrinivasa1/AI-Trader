#!/usr/bin/env python3
from pathlib import Path
import re
import runpy

# Build on the validated v2.1.0 image-import release, including v2.0.1 recovery
# and v2.0.2 FREE recommendation detection.
runpy.run_path("hotfix/run_v210.py", run_name="__main__")

ROOT = Path("android-stable")
JAVA = ROOT / "app/src/main/java/com/suhas/multyfiautobuy/stable"
TEST = ROOT / "app/src/test/java/com/suhas/multyfiautobuy/stable"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def replace_once(path: Path, old: str, new: str) -> None:
    text = read(path)
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected exactly one match in {path}: found {count}\n{old[:220]}")
    write(path, text.replace(old, new, 1))


# Release identity.
gradle = ROOT / "app/build.gradle"
replace_once(gradle, "versionCode 210", "versionCode 211")
replace_once(gradle, "versionName '2.1.0'", "versionName '2.1.1'")

# Persist a separate FREE recommendation amount cap, default ₹5,000.
prefs = JAVA / "AppPrefs.java"
text = read(prefs)
text = text.replace(
    "    static final double DEFAULT_WINDOW_3_BUDGET = 5_000d;",
    "    static final double DEFAULT_WINDOW_3_BUDGET = 5_000d;\n"
    "    static final double DEFAULT_FREE_RECOMMENDATION_BUDGET = 5_000d;",
    1,
)
text = text.replace(
    '    private static final String K_WINDOW_3_BUDGET = "window_3_budget";',
    '    private static final String K_WINDOW_3_BUDGET = "window_3_budget";\n'
    '    private static final String K_FREE_RECOMMENDATION_BUDGET = "free_recommendation_budget";',
    1,
)
marker = '''    static double window3Budget(Context context) {
        return readBudget(context, K_WINDOW_3_BUDGET, DEFAULT_WINDOW_3_BUDGET);
    }

'''
insert = marker + '''    static double freeRecommendationBudget(Context context) {
        return readBudget(context, K_FREE_RECOMMENDATION_BUDGET,
                DEFAULT_FREE_RECOMMENDATION_BUDGET);
    }

    static void setFreeRecommendationBudget(Context context, double value) {
        if (!isValidTradeBudget(value)) {
            throw new IllegalArgumentException(
                    "FREE recommendation amount must be between ₹1,000 and ₹5,00,000.");
        }
        prefs(context).edit().putLong(K_FREE_RECOMMENDATION_BUDGET,
                Double.doubleToRawLongBits(value)).apply();
    }

'''
if marker not in text:
    raise RuntimeError("Could not insert FREE recommendation budget preferences")
text = text.replace(marker, insert, 1)
write(prefs, text)

# FREE recommendations now use floor(configured FREE amount / maximum permitted buy price).
policy = JAVA / "OrderPolicy.java"
text = read(policy)
old_policy = '''    static int quantity(boolean freeRecommendation, double budget, double maximumBuyPrice) {
        return freeRecommendation ? 10 : AppPrefs.quantityForBudget(budget, maximumBuyPrice);
    }

    static boolean usesWindowBudget(boolean freeRecommendation) {
        return !freeRecommendation;
    }
'''
new_policy = '''    static int quantity(boolean freeRecommendation, double effectiveBudget,
                        double maximumBuyPrice) {
        return AppPrefs.quantityForBudget(effectiveBudget, maximumBuyPrice);
    }

    static boolean usesWindowBudget(boolean freeRecommendation) {
        return true;
    }
'''
if old_policy not in text:
    raise RuntimeError("Could not replace FREE fixed-quantity policy")
text = text.replace(old_policy, new_policy, 1)
write(policy, text)

# Notification execution selects the configurable FREE budget instead of 10 shares.
listener = JAVA / "ProductionNotificationService.java"
text = read(listener)
old_quantity = '''            boolean freeRecommendation = SignalParser.isFreeRecommendation(rawText);
            int quantity = OrderPolicy.quantity(freeRecommendation, window.budget, signal.maxBuyPrice);
            String summary = summary(signal, window, entryMode, productType, quantity,
                    freeRecommendation);'''
new_quantity = '''            boolean freeRecommendation = SignalParser.isFreeRecommendation(rawText);
            double effectiveBudget = freeRecommendation
                    ? AppPrefs.freeRecommendationBudget(this) : window.budget;
            int quantity = OrderPolicy.quantity(freeRecommendation, effectiveBudget,
                    signal.maxBuyPrice);
            String summary = summary(signal, window, entryMode, productType, quantity,
                    freeRecommendation, effectiveBudget);'''
if old_quantity not in text:
    raise RuntimeError("Could not replace FREE quantity calculation")
text = text.replace(old_quantity, new_quantity, 1)
old_limit = '''            if ((OrderPolicy.usesWindowBudget(freeRecommendation)
                    && maximumOrderValue > window.budget + 0.01d)
                    || maximumOrderValue > AppPrefs.MAX_ORDER_VALUE) {'''
new_limit = '''            if (maximumOrderValue > effectiveBudget + 0.01d
                    || maximumOrderValue > AppPrefs.MAX_ORDER_VALUE) {'''
if old_limit not in text:
    raise RuntimeError("Could not replace FREE value limit")
text = text.replace(old_limit, new_limit, 1)
text = text.replace(
    '''                                   String productType, int quantity,
                                   boolean freeRecommendation) {''',
    '''                                   String productType, int quantity,
                                   boolean freeRecommendation, double effectiveBudget) {''',
    1,
)
text = text.replace(
    '''                + (freeRecommendation
                ? " | FREE OVERRIDE: fixed 10 shares; window budget ignored"
                : " | budget ₹" + money(window.budget))''',
    '''                + (freeRecommendation
                ? " | FREE AMOUNT CAP ₹" + money(effectiveBudget)
                : " | budget ₹" + money(effectiveBudget))''',
    1,
)
# Listener disconnect and order-processing failures create a single deduplicated attention alert.
text = text.replace(
    '''        AppPrefs.log(this, "LISTENER DISCONNECTED",
                "Android disconnected the notification listener; an immediate rebind was requested.");''',
    '''        AppPrefs.log(this, "LISTENER DISCONNECTED",
                "Android disconnected the notification listener; an immediate rebind was requested.");
        if (AppPrefs.isArmed(this)) {
            UserAlertNotifier.notifyAutoBuyUnavailable(this, "listener_disconnected",
                    "Notification access disconnected. New Multyfi entries are paused until Android reconnects the listener.");
        }''',
    1,
)
text = text.replace(
    '''        } catch (Exception e) {
            AppPrefs.log(this, "PROCESSING ERROR",
                    e.getClass().getSimpleName() + ": " + e.getMessage());
        } finally {''',
    '''        } catch (Exception e) {
            String message = e.getClass().getSimpleName() + ": " + e.getMessage();
            AppPrefs.log(this, "PROCESSING ERROR", message);
            if (AppPrefs.isArmed(this)) {
                UserAlertNotifier.notifyAutoBuyUnavailable(this, "processing_error", message);
            }
        } finally {''',
    1,
)
old_reject = '''    private void rejectAndDisarm(String reason, String summary) {
        AppPrefs.log(this, "REJECTED — ARMED, WAITING FOR GATE",
                summary + "\n" + reason
                        + " Armed state remains ON; this notification was not submitted.");
    }'''
new_reject = '''    private void rejectAndDisarm(String reason, String summary) {
        AppPrefs.log(this, "REJECTED — ARMED, WAITING FOR GATE",
                summary + "\n" + reason
                        + " Armed state remains ON; this notification was not submitted.");
        UserAlertNotifier.notifyAutoBuyUnavailable(this,
                "entry_gate_" + Integer.toHexString(reason.hashCode()), reason);
    }'''
if old_reject not in text:
    raise RuntimeError("Could not add gate alert to ProductionNotificationService")
text = text.replace(old_reject, new_reject, 1)
write(listener, text)

# Two focused notification types only: actual buy execution and Auto-Buy paused/off.
write(JAVA / "UserAlertNotifier.java", r'''package com.suhas.multyfiautobuy.stable;

import android.Manifest;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.os.Build;

final class UserAlertNotifier {
    private static final String CHANNEL_ID = "multyfi_trade_alerts_v211";
    private static final String PREFS = "multyfi_user_alerts_v211";
    private static final String LAST_PAUSE_KEY = "last_pause_key";
    private static final String BUY_PREFIX = "buy_notified_";
    private static final int PAUSE_NOTIFICATION_ID = 21101;

    private UserAlertNotifier() { }

    static void notifyBuyExecuted(Context context, Strategy strategy, int filledQuantity) {
        if (context == null || strategy == null || filledQuantity <= 0) return;
        SharedPreferences prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        String key = BUY_PREFIX + safeKey(strategy.eventId);
        if (prefs.getBoolean(key, false)) return;
        prefs.edit().putBoolean(key, true).apply();
        String body = strategy.symbol + " • " + filledQuantity + " of "
                + strategy.requestedQuantity + " " + strategy.productType
                + " shares filled. Stop-loss protection is being verified automatically.";
        int id = 22000 + Math.abs(safeKey(strategy.eventId).hashCode() % 7000);
        post(context, id, "BUY EXECUTED", body, false);
    }

    static void notifyAutoBuyUnavailable(Context context, String reasonKey, String message) {
        if (context == null || !AppPrefs.isArmed(context)) return;
        String key = safeKey(reasonKey);
        SharedPreferences prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        if (key.equals(prefs.getString(LAST_PAUSE_KEY, ""))) return;
        prefs.edit().putString(LAST_PAUSE_KEY, key).apply();
        post(context, PAUSE_NOTIFICATION_ID, "AUTO-BUY PAUSED",
                clean(message) + " Open Multyfi AutoBuy Pro to review.", true);
    }

    static void notifyAutoBuyOffByUser(Context context) {
        if (context == null) return;
        SharedPreferences prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        prefs.edit().putString(LAST_PAUSE_KEY, "user_off").apply();
        post(context, PAUSE_NOTIFICATION_ID, "AUTO-BUY OFF",
                "New automatic entries were turned off. Existing strategies remain monitored.", true);
    }

    static void clearAutoBuyUnavailable(Context context) {
        if (context == null) return;
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
                .edit().remove(LAST_PAUSE_KEY).apply();
    }

    private static void post(Context context, int id, String title, String body,
                             boolean attention) {
        if (Build.VERSION.SDK_INT >= 33
                && context.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)
                != PackageManager.PERMISSION_GRANTED) return;
        NotificationManager manager = (NotificationManager)
                context.getSystemService(Context.NOTIFICATION_SERVICE);
        if (manager == null) return;
        if (Build.VERSION.SDK_INT >= 26) {
            NotificationChannel channel = new NotificationChannel(CHANNEL_ID,
                    "Trade execution and Auto-Buy alerts",
                    NotificationManager.IMPORTANCE_DEFAULT);
            channel.setDescription("Only buy execution and Auto-Buy paused/off alerts.");
            manager.createNotificationChannel(channel);
        }
        Intent open = new Intent(context, MainActivity.class)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        PendingIntent pending = PendingIntent.getActivity(context, 211, open,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        Notification.Builder builder = Build.VERSION.SDK_INT >= 26
                ? new Notification.Builder(context, CHANNEL_ID)
                : new Notification.Builder(context);
        builder.setSmallIcon(attention
                        ? android.R.drawable.stat_notify_error
                        : android.R.drawable.stat_sys_download_done)
                .setContentTitle(title)
                .setContentText(body)
                .setStyle(new Notification.BigTextStyle().bigText(body))
                .setContentIntent(pending)
                .setAutoCancel(true)
                .setOnlyAlertOnce(false)
                .setCategory(attention ? Notification.CATEGORY_ERROR : Notification.CATEGORY_STATUS);
        manager.notify(id, builder.build());
    }

    private static String clean(String value) {
        if (value == null || value.trim().isEmpty()) return "A required trading gate is unavailable.";
        String clean = value.replace('\n', ' ').replace('\r', ' ').trim();
        return clean.length() <= 260 ? clean : clean.substring(0, 260) + "…";
    }

    private static String safeKey(String value) {
        String clean = value == null ? "unknown" : value.replaceAll("[^A-Za-z0-9_.-]", "_");
        return clean.length() <= 120 ? clean : clean.substring(0, 120);
    }
}
''')

# Monitor alerts once when entry intake becomes unavailable and once on the first actual fill.
monitor = JAVA / "StrategyMonitorService.java"
text = read(monitor)
old_tick = '''            preflightAuthenticationIfDue(networkReady);
            updateNotification();

            if (active.isEmpty() || !networkReady) return;'''
new_tick = '''            preflightAuthenticationIfDue(networkReady);
            updateNotification();
            updateEntryAvailabilityAlert(networkReady, vpnReady, staticIpReady, active);

            if (active.isEmpty() || !networkReady) return;'''
if old_tick not in text:
    raise RuntimeError("Could not insert monitor availability alert")
text = text.replace(old_tick, new_tick, 1)
marker = '''    private boolean refreshPublicIpIfDue() {'''
helper = '''    private void updateEntryAvailabilityAlert(boolean networkReady, boolean vpnReady,
                                              boolean staticIpReady, List<Strategy> active) {
        if (!AppPrefs.isArmed(this)) return;
        if (!networkReady) {
            UserAlertNotifier.notifyAutoBuyUnavailable(this, "network_offline",
                    "Internet connectivity is unavailable; new entries are paused.");
            return;
        }
        if (!vpnReady) {
            UserAlertNotifier.notifyAutoBuyUnavailable(this, "vpn_lost",
                    "Surfshark VPN is not active; new entries are paused.");
            return;
        }
        if (!staticIpReady) {
            UserAlertNotifier.notifyAutoBuyUnavailable(this, "ip_not_verified",
                    "The current public IP is not the verified Groww-whitelisted Dedicated IP; new entries are paused.");
            return;
        }
        if (!AppPrefs.isAuthVerifiedToday(this)) {
            UserAlertNotifier.notifyAutoBuyUnavailable(this, "groww_auth_not_verified",
                    "Groww authentication is not verified for today; new entries are paused.");
            return;
        }
        for (Strategy strategy : active) {
            if (strategy.observedFilledQuantity > strategy.protectedQuantity) {
                UserAlertNotifier.notifyAutoBuyUnavailable(this,
                        "unprotected_" + strategy.symbol,
                        strategy.symbol + " has filled shares awaiting confirmed stop-loss protection; new entries are paused.");
                return;
            }
        }
        UserAlertNotifier.clearAutoBuyUnavailable(this);
    }

'''
if marker not in text:
    raise RuntimeError("Could not add monitor alert helper")
text = text.replace(marker, helper + marker, 1)
old_fill = '''        int filled = detectFilledQuantity(token, strategy, remaining);
        if (filled > strategy.observedFilledQuantity) {
            strategy.observedFilledQuantity = Math.min(strategy.requestedQuantity, filled);
            strategy.lastMessage = "Observed " + strategy.productType + " fill: "
                    + strategy.observedFilledQuantity + " of "
                    + strategy.requestedQuantity + ".";
            AppPrefs.log(this, "ENTRY FILL OBSERVED",
                    strategy.symbol + " • " + strategy.lastMessage);
        }'''
new_fill = '''        int filled = detectFilledQuantity(token, strategy, remaining);
        if (filled > strategy.observedFilledQuantity) {
            int previousObserved = strategy.observedFilledQuantity;
            strategy.observedFilledQuantity = Math.min(strategy.requestedQuantity, filled);
            strategy.lastMessage = "Observed " + strategy.productType + " fill: "
                    + strategy.observedFilledQuantity + " of "
                    + strategy.requestedQuantity + ".";
            AppPrefs.log(this, "ENTRY FILL OBSERVED",
                    strategy.symbol + " • " + strategy.lastMessage);
            if (previousObserved <= 0 && strategy.observedFilledQuantity > 0) {
                UserAlertNotifier.notifyBuyExecuted(this, strategy,
                        strategy.observedFilledQuantity);
            }
        }'''
if old_fill not in text:
    raise RuntimeError("Could not add buy-executed alert")
text = text.replace(old_fill, new_fill, 1)
# A protection failure pauses entries; alert once while the retry loop continues silently.
text = text.replace(
    '''                AppPrefs.log(this, "STOP-LOSS RETRY PENDING — ARMED RETAINED",
                        strategy.symbol + " • " + strategy.lastMessage
                                + " New entries are paused, but the 24×7 armed preference remains ON.");''',
    '''                AppPrefs.log(this, "STOP-LOSS RETRY PENDING — ARMED RETAINED",
                        strategy.symbol + " • " + strategy.lastMessage
                                + " New entries are paused, but the 24×7 armed preference remains ON.");
                UserAlertNotifier.notifyAutoBuyUnavailable(this,
                        "stop_loss_pending_" + strategy.symbol,
                        strategy.symbol + " has filled shares awaiting confirmed stop-loss protection; new entries are paused.");''',
    1,
)
write(monitor, text)

# Dashboard: configurable FREE amount in the same atomic save flow and alert state integration.
activity = JAVA / "ProductionActivity.java"
text = read(activity)
text = text.replace("release 2.1.0", "release 2.1.1")
text = text.replace("source-built v2.1.0", "source-built v2.1.1")
text = text.replace(
    "    private EditText window3Input;",
    "    private EditText window3Input;\n    private EditText freeBudgetInput;",
    1,
)
text = text.replace(
    '''                "Amounts are saved only after pressing SAVE TRADING WINDOWS. Unsaved edits block arming. Any complete recommendation containing the word FREE uses exactly 10 shares in every active market window; the normal MIS/CNC time routing remains unchanged.",''',
    '''                "Amounts are saved only after pressing SAVE TRADING WINDOWS. Unsaved edits block arming. FREE recommendations use a separate configurable amount cap; quantity = floor(FREE amount ÷ maximum permitted buy price). Normal MIS/CNC time routing remains unchanged.",''',
    1,
)
text = text.replace(
    '''        window3Input = moneyField("10:00–15:30 • CNC delivery • entry GTT");
        bufferInput = decimalField("Entry buffer % (0.00–2.00)");''',
    '''        window3Input = moneyField("10:00–15:30 • CNC delivery • entry GTT");
        freeBudgetInput = moneyField("FREE RECOMMENDATION AMOUNT CAP • default ₹5,000");
        bufferInput = decimalField("Entry buffer % (0.00–2.00)");''',
    1,
)
text = text.replace(
    '''        windowsCard.addView(window3Input, topMargin(10));
        windowsCard.addView(bufferInput, topMargin(10));''',
    '''        windowsCard.addView(window3Input, topMargin(10));
        windowsCard.addView(freeBudgetInput, topMargin(10));
        windowsCard.addView(bufferInput, topMargin(10));''',
    1,
)
text = text.replace(
    '''        attachWindowWatch(window3Input);
        attachWindowWatch(bufferInput);''',
    '''        attachWindowWatch(window3Input);
        attachWindowWatch(freeBudgetInput);
        attachWindowWatch(bufferInput);''',
    1,
)
text = text.replace(
    '''        window3Input.setText(money(AppPrefs.window3Budget(this)));
        bufferInput.setText(String.format(Locale.US, "%.2f", AppPrefs.entryBufferPercent(this)));''',
    '''        window3Input.setText(money(AppPrefs.window3Budget(this)));
        freeBudgetInput.setText(money(AppPrefs.freeRecommendationBudget(this)));
        bufferInput.setText(String.format(Locale.US, "%.2f", AppPrefs.entryBufferPercent(this)));''',
    1,
)
text = text.replace(
    '''                + " / ₹" + money(AppPrefs.window3Budget(this))
                + " • buffer "''',
    '''                + " / ₹" + money(AppPrefs.window3Budget(this))
                + " • FREE ₹" + money(AppPrefs.freeRecommendationBudget(this))
                + " • buffer "''',
    1,
)
text = text.replace(
    '''            double third = readDouble(window3Input);
            double buffer = readDouble(bufferInput);''',
    '''            double third = readDouble(window3Input);
            double freeBudget = readDouble(freeBudgetInput);
            double buffer = readDouble(bufferInput);''',
    1,
)
text = text.replace(
    '''                    || !AppPrefs.isValidTradeBudget(third)) {''',
    '''                    || !AppPrefs.isValidTradeBudget(third)
                    || !AppPrefs.isValidTradeBudget(freeBudget)) {''',
    1,
)
text = text.replace(
    '''            AppPrefs.setWindowBudgets(this, first, second, third);
            AppPrefs.setEntryBufferPercent(this, buffer);''',
    '''            AppPrefs.setWindowBudgets(this, first, second, third);
            AppPrefs.setFreeRecommendationBudget(this, freeBudget);
            AppPrefs.setEntryBufferPercent(this, buffer);''',
    1,
)
text = text.replace(
    '''                    + " / ₹" + money(third) + " • buffer "''',
    '''                    + " / ₹" + money(third) + " • FREE ₹" + money(freeBudget)
                    + " • buffer "''',
    1,
)
text = text.replace(
    '''                            + " • 10:00–15:30 ₹" + money(third) + " CNC entry GTT"
                            + " • buffer "''',
    '''                            + " • 10:00–15:30 ₹" + money(third) + " CNC entry GTT"
                            + " • FREE recommendation amount ₹" + money(freeBudget)
                            + " • buffer "''',
    1,
)
text = text.replace(
    '            toast("All three trading windows were saved.");',
    '            toast("Trading windows and FREE recommendation amount were saved.");',
    1,
)
text = text.replace(
    '                ? "● Routing policy: MIS before 09:30 • CNC GTT after 09:30 • FREE = fixed 10 shares"',
    '                ? "● Routing policy: MIS before 09:30 • CNC GTT after 09:30 • FREE uses configurable amount cap"',
    1,
)
text = text.replace(
    '''                && OrderPolicy.quantity(true, first.budget, 6975d) == 10
                && OrderPolicy.quantity(false, first.budget, signal.maxBuyPrice)''',
    '''                && OrderPolicy.quantity(true,
                        AppPrefs.DEFAULT_FREE_RECOMMENDATION_BUDGET, 5_000d) == 1
                && OrderPolicy.quantity(true,
                        AppPrefs.DEFAULT_FREE_RECOMMENDATION_BUDGET, 5_001d) == 0
                && OrderPolicy.quantity(false, first.budget, signal.maxBuyPrice)''',
    1,
)
text = text.replace(
    'PASS: 09:00–09:30 MIS LIMIT; 09:30 onward CNC entry GTT; FREE fixed quantity 10 in every active window; three budgets; early exit matched; no order submitted.',
    'PASS: 09:00–09:30 MIS LIMIT; 09:30 onward CNC entry GTT; FREE uses configurable amount cap; three windows; early exit matched; no order submitted.',
    1,
)
# Manual OFF produces the second permitted alert type.
text = text.replace(
    '''            AppPrefs.setArmed(this, false);
            AppPrefs.log(this, "DISARMED BY USER",
                    "New automatic entries disabled; existing strategies remain monitored and protected.");''',
    '''            AppPrefs.setArmed(this, false);
            AppPrefs.log(this, "DISARMED BY USER",
                    "New automatic entries disabled; existing strategies remain monitored and protected.");
            UserAlertNotifier.notifyAutoBuyOffByUser(this);''',
    1,
)
# While the dashboard is open, immediately alert once when a readiness gate pauses intake.
status_anchor = '''        suppressSwitch = true;
        armedSwitch.setChecked(persistentlyArmed);
        suppressSwitch = false;
        auditLog.setText(AppPrefs.auditLog(this));'''
status_replacement = '''        suppressSwitch = true;
        armedSwitch.setChecked(persistentlyArmed);
        suppressSwitch = false;
        if (persistentlyArmed && !ready) {
            UserAlertNotifier.notifyAutoBuyUnavailable(this,
                    "dashboard_" + Integer.toHexString(issue == null ? 0 : issue.hashCode()),
                    issue == null ? "A required trading gate is unavailable." : issue);
        } else if (persistentlyArmed) {
            UserAlertNotifier.clearAutoBuyUnavailable(this);
        }
        auditLog.setText(AppPrefs.auditLog(this));'''
if status_anchor not in text:
    raise RuntimeError("Could not integrate dashboard readiness alert")
text = text.replace(status_anchor, status_replacement, 1)
# Status text includes the FREE amount for easy visual verification.
text = text.replace(
    '''                + " / ₹" + money(AppPrefs.window3Budget(this)) + "."''',
    '''                + " / ₹" + money(AppPrefs.window3Budget(this))
                + " • FREE ₹" + money(AppPrefs.freeRecommendationBudget(this)) + "."''',
    1,
)
write(activity, text)

# Pure unit tests for the new amount-based FREE quantity policy.
write(TEST / "FreeRecommendationBudgetTest.java", r'''package com.suhas.multyfiautobuy.stable;

import org.junit.Test;

import static org.junit.Assert.assertEquals;

public class FreeRecommendationBudgetTest {
    @Test public void fiveThousandBudgetBuysOneFiveThousandRupeeShare() {
        assertEquals(1, OrderPolicy.quantity(true, 5_000d, 5_000d));
    }

    @Test public void priceAboveFreeBudgetProducesZeroQuantity() {
        assertEquals(0, OrderPolicy.quantity(true, 5_000d, 5_000.05d));
    }

    @Test public void lowerPriceUsesFloorOfConfiguredAmount() {
        assertEquals(14, OrderPolicy.quantity(true, 5_000d, 342.05d));
    }
}
''')

# Build-time assertions.
assert "versionName '2.1.1'" in read(gradle)
assert "DEFAULT_FREE_RECOMMENDATION_BUDGET = 5_000d" in read(prefs)
assert "FREE RECOMMENDATION AMOUNT CAP" in read(activity)
assert "FREE fixed quantity 10" not in read(activity)
assert "FREE OVERRIDE: fixed 10 shares" not in read(listener)
assert "UserAlertNotifier.notifyBuyExecuted" in read(monitor)
assert "Only buy execution and Auto-Buy paused/off alerts" in read(JAVA / "UserAlertNotifier.java")
assert "MONTHLY IMAGE GTT IMPORT" in read(activity)
print("Applied Multyfi AutoBuy Pro v2.1.1 configurable FREE budget and focused alerts")
