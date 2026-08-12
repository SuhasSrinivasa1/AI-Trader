#!/usr/bin/env python3
from pathlib import Path
import runpy

# v2.4.9 is deliberately built on the exact v2.4.8 release generator.
# The proven direct Multyfi early-exit MARKET SELL path is not redesigned.
runpy.run_path('hotfix/run_v248_final.py', run_name='__main__')

ROOT = Path('android-stable')
J = ROOT / 'app/src/main/java/com/suhas/multyfiautobuy/stable'
T = ROOT / 'app/src/test/java/com/suhas/multyfiautobuy/stable'


def read(p): return Path(p).read_text(encoding='utf-8')
def write(p, s): Path(p).write_text(s, encoding='utf-8')
def repl(p, old, new):
    p = Path(p); text = read(p); count = text.count(old)
    if count != 1:
        raise RuntimeError(f'{p}: expected exactly one match, found {count}: {old[:180]}')
    write(p, text.replace(old, new, 1))

# Version.
repl(ROOT/'app/build.gradle', 'versionCode 248', 'versionCode 249')
repl(ROOT/'app/build.gradle', "versionName '2.4.8'", "versionName '2.4.9'")

# Actual listener binding health, independent of the Android permission toggle.
write(J/'NotificationListenerHealth.java', r'''package com.suhas.multyfiautobuy.stable;

import android.content.ComponentName;
import android.content.Context;
import android.service.notification.NotificationListenerService;

/** Tracks the real NotificationListenerService binding and self-heals a dropped listener. */
final class NotificationListenerHealth {
    private static final long REBIND_RETRY_MS = 5_000L;
    private static final long REBIND_LOG_MS = 30_000L;
    private static volatile boolean connected;
    private static volatile long lastConnectedAt;
    private static volatile long lastCallbackAt;
    private static volatile long lastRebindAttemptAt;
    private static volatile long lastRebindLogAt;

    private NotificationListenerHealth() { }

    static void markConnected(Context context) {
        connected = true;
        long now = System.currentTimeMillis();
        lastConnectedAt = now;
        lastCallbackAt = now;
    }

    static void markCallback(Context context) {
        if (!connected) markConnected(context);
        else lastCallbackAt = System.currentTimeMillis();
    }

    static void markDisconnected() { connected = false; }

    static boolean isConnected() { return connected; }
    static long lastConnectedAt() { return lastConnectedAt; }
    static long lastCallbackAt() { return lastCallbackAt; }

    static void requestRebindNow(Context context) {
        connected = false;
        lastRebindAttemptAt = 0L;
        ensureBound(context);
    }

    static boolean ensureBound(Context context) {
        if (context == null || !AppPrefs.isArmed(context)) return false;
        if (connected) return true;
        long now = System.currentTimeMillis();
        if (now - lastRebindAttemptAt < REBIND_RETRY_MS) return false;
        lastRebindAttemptAt = now;
        try {
            NotificationListenerService.requestRebind(new ComponentName(
                    context, MultyfiNotificationService.class));
            if (now - lastRebindLogAt >= REBIND_LOG_MS) {
                lastRebindLogAt = now;
                AppPrefs.log(context, "LISTENER REBIND REQUESTED",
                        "Android notification-listener binding is not active; automatic recovery requested a rebind.");
            }
        } catch (Exception e) {
            if (now - lastRebindLogAt >= REBIND_LOG_MS) {
                lastRebindLogAt = now;
                AppPrefs.log(context, "LISTENER REBIND FAILED",
                        e.getClass().getSimpleName() + ": " + e.getMessage());
            }
        }
        return connected;
    }
}
''')

# Pure contracts used by production code and unit tests.
write(J/'BrokerFlatCleanupPolicy.java', r'''package com.suhas.multyfiautobuy.stable;

final class BrokerFlatCleanupPolicy {
    private BrokerFlatCleanupPolicy() { }
    static boolean canClear(boolean positionReadSucceeded, int remainingStrategyQuantity,
                            boolean entryCannotFillLater) {
        return positionReadSucceeded && remainingStrategyQuantity <= 0 && entryCannotFillLater;
    }
}
''')

write(J/'IntradayProtectionPolicy.java', r'''package com.suhas.multyfiautobuy.stable;

final class IntradayProtectionPolicy {
    private IntradayProtectionPolicy() { }
    static boolean multyfiStopHit(double ltp, double stopLossPrice) {
        return ltp > 0d && stopLossPrice > 0d && ltp <= stopLossPrice + 1e-9d;
    }
    static boolean targetHit(double ltp, double targetPrice) {
        return DailyRiskPolicy.profitThresholdHit(ltp, targetPrice);
    }
}
''')

# Notification listener lifecycle: record actual connection, heartbeat every callback,
# and use the watchdog rather than trusting Notification Access alone.
p = J/'ProductionNotificationService.java'
repl(p,
'''        if (!AppPrefs.isArmed(this)) {\n            try { requestUnbind(); }\n            catch (Exception ignored) { }\n            return;\n        }\n        StrategyStore.warm(this);\n''',
'''        if (!AppPrefs.isArmed(this)) {\n            NotificationListenerHealth.markDisconnected();\n            try { requestUnbind(); }\n            catch (Exception ignored) { }\n            return;\n        }\n        NotificationListenerHealth.markConnected(this);\n        StrategyStore.warm(this);\n''')
repl(p,
'''    public void onListenerDisconnected() {\n        if (AppPrefs.isArmed(this)) {\n            AppPrefs.log(this, "LISTENER DISCONNECTED", "Android disconnected the listener; standalone runtime requested an immediate rebind.");\n            try { requestRebind(new android.content.ComponentName(this, MultyfiNotificationService.class)); }\n            catch (Exception ignored) { }\n        }\n        super.onListenerDisconnected();\n    }\n''',
'''    public void onListenerDisconnected() {\n        NotificationListenerHealth.markDisconnected();\n        if (AppPrefs.isArmed(this)) {\n            AppPrefs.log(this, "LISTENER DISCONNECTED", "Android disconnected the listener; automatic recovery requested an immediate rebind.");\n            NotificationListenerHealth.requestRebindNow(this);\n        }\n        super.onListenerDisconnected();\n    }\n''')
repl(p,
'''    public void onNotificationPosted(StatusBarNotification sbn) {\n        if (sbn == null || sbn.getNotification() == null) return;\n        final String sourcePackage = sbn.getPackageName();\n''',
'''    public void onNotificationPosted(StatusBarNotification sbn) {\n        if (sbn == null || sbn.getNotification() == null) return;\n        NotificationListenerHealth.markCallback(this);\n        final String sourcePackage = sbn.getPackageName();\n''')
repl(p,
'''    public void onDestroy() {\n        entryExecutor.shutdownNow();\n''',
'''    public void onDestroy() {\n        NotificationListenerHealth.markDisconnected();\n        entryExecutor.shutdownNow();\n''')

# Broker-flat stale-state recovery before the one-stock/early-exit BUY gate.
repl(p,
'''            if (hasPendingEarlyExit(active)) {\n                AppPrefs.log(this, "NEW ENTRY BLOCKED — EARLY EXIT PENDING",\n                        "A previous Multyfi exit is still awaiting broker-confirmed zero position.\\n"\n                                + compact(rawText));\n                return;\n            }\n''',
'''            if (hasPendingEarlyExit(active) && clearStalePendingExitIfBrokerFlat(active)) {\n                active = StrategyStore.activeFast(this);\n                liveTradeHint = !active.isEmpty();\n            }\n            if (hasPendingEarlyExit(active)) {\n                AppPrefs.log(this, "NEW ENTRY BLOCKED — EARLY EXIT PENDING",\n                        "A previous Multyfi exit is still awaiting broker-confirmed zero position or a terminal entry order.\\n"\n                                + compact(rawText));\n                return;\n            }\n''')
repl(p,
'''    private static boolean hasPendingEarlyExit(List<Strategy> strategies) {\n''',
'''    private boolean clearStalePendingExitIfBrokerFlat(List<Strategy> strategies) {\n        if (strategies == null || strategies.size() != 1) return false;\n        Strategy strategy = strategies.get(0);\n        if (strategy == null || !strategy.isActive() || !strategy.earlyExitRequested) return false;\n        if (!NetworkUtil.isNetworkAvailable(this) || !NetworkUtil.isVpnActive(this)\n                || !AppPrefs.isIpRecentlyVerified(this) || !AppPrefs.isAuthVerifiedToday(this)) return false;\n        String token = TokenManager.hotTokenOrEmpty();\n        if (token.isEmpty()) token = TokenManager.validToken(this);\n        if (token.isEmpty()) return false;\n        GrowwClient.IntResult position = GrowwClient.getNetPositionQuantity(\n                token, strategy.symbol, strategy.productType);\n        if (!position.success) return false;\n        int remaining = strategy.remainingStrategyQuantity(position.value);\n        boolean entryTerminal = entryCannotFillLater(token, strategy);\n        if (!BrokerFlatCleanupPolicy.canClear(true, remaining, entryTerminal)) return false;\n        strategy.state = Strategy.CLOSED;\n        strategy.earlyExitRequested = false;\n        strategy.earlyExitAttempt = 0;\n        strategy.targetOrderId = "";\n        strategy.targetOrderReferenceId = "";\n        strategy.pendingExitLabel = "";\n        strategy.lastMessage = "Groww position is zero and the entry cannot fill later; stale early-exit state cleared before the new BUY.";\n        strategy.updatedAt = System.currentTimeMillis();\n        StrategyStore.upsert(this, strategy);\n        AppPrefs.log(this, "STALE EARLY EXIT CLEARED — GROWW FLAT",\n                strategy.symbol + " • broker position is zero; local one-stock lock released safely.");\n        return true;\n    }\n\n    private boolean entryCannotFillLater(String token, Strategy strategy) {\n        if (strategy.entryOrderId != null && !strategy.entryOrderId.isEmpty()) {\n            GrowwClient.OrderStatus order = GrowwClient.getOrderByReference(\n                    token, strategy.entryReferenceId);\n            return order.success && isTerminalRegularOrderStatus(order.status);\n        }\n        if (strategy.entrySmartOrderId != null && !strategy.entrySmartOrderId.isEmpty()) {\n            GrowwClient.SmartStatus smart = GrowwClient.getGtt(token, strategy.entrySmartOrderId);\n            return smart.success && ("CANCELLED".equalsIgnoreCase(smart.status)\n                    || "CANCELED".equalsIgnoreCase(smart.status));\n        }\n        return true;\n    }\n\n    private static boolean hasPendingEarlyExit(List<Strategy> strategies) {\n''')

# Runtime activation and foreground watchdog both recover a lost listener.
p = J/'AppRuntimeControl.java'
repl(p,
'''        try { NotificationListenerService.requestRebind(new ComponentName(c, MultyfiNotificationService.class)); }\n        catch (Exception ignored) { }\n''',
'''        NotificationListenerHealth.requestRebindNow(c);\n''')

p = J/'StrategyMonitorService.java'
repl(p,
'''    private static final String EXIT_MULTYFI_EARLY = "MULTYFI_EARLY";\n''',
'''    private static final String EXIT_MULTYFI_EARLY = "MULTYFI_EARLY";\n    private static final String EXIT_MULTYFI_STOP = "MULTYFI_STOP";\n''')
repl(p,
'''    private void safeTick() {\n        try {\n            List<Strategy> active = StrategyStore.active(this);\n''',
'''    private void safeTick() {\n        try {\n            if (AppPrefs.isArmed(this)) NotificationListenerHealth.ensureBound(this);\n            List<Strategy> active = StrategyStore.active(this);\n''')

# The fast 250 ms watcher now honours both the Multyfi target and Multyfi stop,
# while retaining the independent gross -₹2,000 emergency rule.
repl(p,
'''            boolean lossHit = DailyRiskPolicy.grossLossThresholdHit(currentGross, realisedGrossBefore);\n            boolean profitHit = DailyRiskPolicy.profitThresholdHit(ltp.value, strategy.fastExitPrice);\n            if (!lossHit && !profitHit) return;\n\n            fastProfitSubmitting = true;\n            String label;\n            if (lossHit) {\n''',
'''            boolean lossHit = DailyRiskPolicy.grossLossThresholdHit(currentGross, realisedGrossBefore);\n            boolean stopHit = IntradayProtectionPolicy.multyfiStopHit(\n                    ltp.value, strategy.multyfiStopLossPrice);\n            boolean profitHit = IntradayProtectionPolicy.targetHit(ltp.value, strategy.fastExitPrice);\n            if (!lossHit && !stopHit && !profitHit) return;\n\n            fastProfitSubmitting = true;\n            String label;\n            String exitType;\n            if (lossHit) {\n                exitType = EXIT_MULTYFI_STOP;\n''')
repl(p,
'''            } else {\n                label = "Multyfi target";\n                strategy.dailyProfitExitTriggered = false;\n                strategy.dailyLossExitTriggered = false;\n            }\n            save(strategy);\n            if (!tryImmediateTrackedTargetExit(token, strategy, label, ltp.value)) {\n''',
'''            } else if (stopHit) {\n                label = "Multyfi stop-loss";\n                exitType = EXIT_MULTYFI_STOP;\n                strategy.dailyProfitExitTriggered = false;\n                strategy.dailyLossExitTriggered = false;\n            } else {\n                label = "Multyfi target";\n                exitType = EXIT_TARGET;\n                strategy.dailyProfitExitTriggered = false;\n                strategy.dailyLossExitTriggered = false;\n            }\n            save(strategy);\n            if (!tryImmediateTrackedTargetExit(token, strategy, label, ltp.value, exitType)) {\n''')
repl(p,
'''                executeExit(token, strategy, true, EXIT_TARGET);\n''',
'''                executeExit(token, strategy, true, exitType);\n''')

repl(p,
'''        strategy.fastExitPrice = strategy.targetPrice;\n        strategy.fastProfitArmed = strategy.fastExitPrice > 0d && strategy.entryAveragePrice > 0d;\n''',
'''        strategy.fastExitPrice = strategy.targetPrice;\n        strategy.fastProfitArmed = strategy.fastExitPrice > 0d\n                && strategy.multyfiStopLossPrice > 0d && strategy.entryAveragePrice > 0d;\n''')
repl(p,
'''            AppPrefs.log(this, "MULTYFI TARGET / GROSS -₹2,000 WATCH ARMED",\n                    strategy.symbol + " • average entry ₹" + money(strategy.entryAveragePrice)\n                            + " • qty " + strategy.observedFilledQuantity\n                            + " • Multyfi target ₹" + money(strategy.targetPrice)\n                            + " • gross-loss reference price ₹" + money(strategy.dynamicLossStopPrice)\n                            + " • Multyfi stop ₹" + money(strategy.multyfiStopLossPrice)\n                            + " is ignored for execution • NO daily profit cap • NO broker-side MIS stop by design.");\n''',
'''            AppPrefs.log(this, "MULTYFI TARGET + STOP WATCH ARMED",\n                    strategy.symbol + " • average entry ₹" + money(strategy.entryAveragePrice)\n                            + " • qty " + strategy.observedFilledQuantity\n                            + " • target ₹" + money(strategy.targetPrice)\n                            + " • stop-loss ₹" + money(strategy.multyfiStopLossPrice)\n                            + " • gross -₹2,000 emergency reference ₹" + money(strategy.dynamicLossStopPrice)\n                            + " • app-side 250 ms watcher • no broker-side protection order, preserving direct early-exit speed.");\n''')

repl(p,
'''    private boolean tryImmediateTrackedTargetExit(String token, Strategy strategy,\n                                                  String label, double triggerLtp) {\n''',
'''    private boolean tryImmediateTrackedTargetExit(String token, Strategy strategy,\n                                                  String label, double triggerLtp, String exitType) {\n''')
repl(p,
'''        GrowwClient.ApiResult sell = strategy.dailyLossExitTriggered\n                ? GrowwClient.placeRiskMarketSell(token, strategy, strategy.requestedQuantity, strategy.earlyExitAttempt)\n                : GrowwClient.placeTargetMarketSell(token, strategy, strategy.requestedQuantity);\n''',
'''        GrowwClient.ApiResult sell = strategy.dailyLossExitTriggered\n                ? GrowwClient.placeRiskMarketSell(token, strategy, strategy.requestedQuantity, strategy.earlyExitAttempt)\n                : EXIT_MULTYFI_STOP.equals(exitType)\n                ? GrowwClient.placeMultyfiStopMarketSell(token, strategy, strategy.requestedQuantity)\n                : GrowwClient.placeTargetMarketSell(token, strategy, strategy.requestedQuantity);\n''')
repl(p,
'''        AppPrefs.log(this,\n                strategy.dailyLossExitTriggered ? "₹2,000 GROSS LOSS MARKET SELL SUBMITTED"\n                        : "MULTYFI TARGET EXIT SUBMITTED",\n''',
'''        AppPrefs.log(this,\n                strategy.dailyLossExitTriggered ? "₹2,000 GROSS LOSS MARKET SELL SUBMITTED"\n                        : EXIT_MULTYFI_STOP.equals(exitType) ? "MULTYFI STOP-LOSS EXIT SUBMITTED"\n                        : "MULTYFI TARGET EXIT SUBMITTED",\n''')

repl(p,
'''            strategy.lastMessage = "Fast price watcher armed for " + strategy.protectedQuantity\n                    + " MIS shares • NO broker-side stop • GROSS -₹2,000 guard • no daily profit cap.";\n            save(strategy);\n            AppPrefs.log(this, "FAST RISK WATCH ARMED — NO BROKER STOP",\n''',
'''            strategy.lastMessage = "Fast target/stop watcher armed for " + strategy.protectedQuantity\n                    + " MIS shares • target ₹" + money(strategy.targetPrice)\n                    + " • stop ₹" + money(strategy.multyfiStopLossPrice)\n                    + " • GROSS -₹2,000 emergency guard.";\n            save(strategy);\n            AppPrefs.log(this, "MULTYFI TARGET + STOP PROTECTION ACTIVE",\n''')

repl(p,
'''        if (EXIT_INTRADAY_TIME.equals(exitType)) {\n            sell = GrowwClient.placeTimedMarketSell(token, strategy, sellQuantity);\n        } else if (authoritativeEarly) {\n''',
'''        if (EXIT_INTRADAY_TIME.equals(exitType)) {\n            sell = GrowwClient.placeTimedMarketSell(token, strategy, sellQuantity);\n        } else if (EXIT_MULTYFI_STOP.equals(exitType)) {\n            sell = GrowwClient.placeMultyfiStopMarketSell(token, strategy, sellQuantity);\n        } else if (authoritativeEarly) {\n''')
repl(p,
'''        if (EXIT_MULTYFI_EARLY.equals(type)) return "Multyfi early exit";\n        if (EXIT_INTRADAY_TIME.equals(type)) return "Intraday time exit";\n        return "Target exit";\n''',
'''        if (EXIT_MULTYFI_EARLY.equals(type)) return "Multyfi early exit";\n        if (EXIT_MULTYFI_STOP.equals(type)) return "Multyfi stop-loss";\n        if (EXIT_INTRADAY_TIME.equals(type)) return "Intraday time exit";\n        return "Target exit";\n''')

# Dedicated deterministic MARKET SELL reference for the Multyfi stop watcher.
p = J/'GrowwClient.java'
repl(p,
'''    static ApiResult placeTargetMarketSell(String accessToken, Strategy strategy,\n                                           int quantity) {\n        return placeMarketSell(accessToken, strategy, quantity,\n                reference("TG", strategy.eventId, 0), "Target-triggered");\n    }\n''',
'''    static ApiResult placeTargetMarketSell(String accessToken, Strategy strategy,\n                                           int quantity) {\n        return placeMarketSell(accessToken, strategy, quantity,\n                reference("TG", strategy.eventId, 0), "Target-triggered");\n    }\n\n    static ApiResult placeMultyfiStopMarketSell(String accessToken, Strategy strategy,\n                                                int quantity) {\n        return placeMarketSell(accessToken, strategy, quantity,\n                reference("MS", strategy.eventId, 0), "Multyfi stop-loss");\n    }\n''')

# Preserve original Multyfi stop across migrations even if legacy stopLossPrice was mutated.
p = J/'Strategy.java'
repl(p, '    final double multyfiStopLossPrice;\n', '    double multyfiStopLossPrice;\n')
repl(p,
'''        strategy.targetSmartOrderId = json.optString("target_smart_order_id", "");\n''',
'''        strategy.multyfiStopLossPrice = json.optDouble(\n                "multyfi_stop_loss_price", strategy.stopLossPrice);\n        strategy.targetSmartOrderId = json.optString("target_smart_order_id", "");\n''')

# Dashboard now reports actual listener binding, and the routing test is correctly shown
# as a persistent setup test rather than a daily task.
p = J/'ProductionActivity.java'
repl(p,
'''        try {\n            NotificationListenerService.requestRebind(\n                    new ComponentName(this, MultyfiNotificationService.class));\n        } catch (Exception ignored) { }\n        AppRuntimeControl.sync(this);\n''',
'''        NotificationListenerHealth.requestRebindNow(this);\n        AppRuntimeControl.sync(this);\n''')
repl(p,
'''        boolean notificationReady = hasNotificationAccess();\n''',
'''        boolean notificationReady = hasNotificationAccess()\n                && NotificationListenerHealth.isConnected();\n''')
repl(p,
'''        if (!hasNotificationAccess()) return "Grant Notification Access to Multyfi AutoBuy";\n''',
'''        if (!hasNotificationAccess()) return "Grant Notification Access to Multyfi AutoBuy";\n        if (!NotificationListenerHealth.isConnected()) {\n            NotificationListenerHealth.ensureBound(this);\n            return "Notification listener is reconnecting; automatic rebind is active";\n        }\n''')
repl(p,
'''                : "● Signal policy: offline acceptance test required");\n''',
'''                : "● Signal policy: run the offline acceptance test once");\n''')
repl(p,
'''        if (!AppPrefs.parserTestPassed(this)) return "Run the offline production routing test";\n''',
'''        if (!AppPrefs.parserTestPassed(this)) return "Run the offline production routing test once";\n''')

# Unit tests for the new safety contracts.
write(T/'V249BrokerFlatCleanupPolicyTest.java', r'''package com.suhas.multyfiautobuy.stable;

import org.junit.Test;
import static org.junit.Assert.*;

public class V249BrokerFlatCleanupPolicyTest {
    @Test public void clearsOnlyWhenGrowwIsFlatAndEntryTerminal() {
        assertTrue(BrokerFlatCleanupPolicy.canClear(true, 0, true));
        assertFalse(BrokerFlatCleanupPolicy.canClear(false, 0, true));
        assertFalse(BrokerFlatCleanupPolicy.canClear(true, 1, true));
        assertFalse(BrokerFlatCleanupPolicy.canClear(true, 0, false));
    }
}
''')
write(T/'V249IntradayProtectionPolicyTest.java', r'''package com.suhas.multyfiautobuy.stable;

import org.junit.Test;
import static org.junit.Assert.*;

public class V249IntradayProtectionPolicyTest {
    @Test public void multyfiStopTriggersAtOrBelowStop() {
        assertTrue(IntradayProtectionPolicy.multyfiStopHit(670d, 670d));
        assertTrue(IntradayProtectionPolicy.multyfiStopHit(669.95d, 670d));
        assertFalse(IntradayProtectionPolicy.multyfiStopHit(670.05d, 670d));
    }
    @Test public void targetTriggersAtOrAboveTarget() {
        assertTrue(IntradayProtectionPolicy.targetHit(715d, 715d));
        assertTrue(IntradayProtectionPolicy.targetHit(715.05d, 715d));
        assertFalse(IntradayProtectionPolicy.targetHit(714.95d, 715d));
    }
}
''')

# Hard source contracts: SELL path remains direct and first; new reliability/protection exists.
service = read(J/'ProductionNotificationService.java')
monitor = read(J/'StrategyMonitorService.java')
groww = read(J/'GrowwClient.java')
activity = read(J/'ProductionActivity.java')
assert 'GrowwClient.placeEarlyExitMarketSell(' in service
assert 'Groww MARKET SELL was called before audit logging.' in service
assert service.index('GrowwClient.ApiResult sell = GrowwClient.placeEarlyExitMarketSell(') < service.index('logBackground("MULTYFI EARLY EXIT API DISPATCH"')
assert 'NotificationListenerHealth.markConnected(this)' in service
assert 'NotificationListenerHealth.ensureBound(this)' in monitor
assert 'STALE EARLY EXIT CLEARED — GROWW FLAT' in service
assert 'BrokerFlatCleanupPolicy.canClear' in service
assert 'MULTYFI TARGET + STOP WATCH ARMED' in monitor
assert 'IntradayProtectionPolicy.multyfiStopHit' in monitor
assert 'GrowwClient.placeMultyfiStopMarketSell' in monitor
assert 'placeMultyfiStopMarketSell' in groww
assert 'NotificationListenerHealth.isConnected()' in activity
assert 'versionCode 249' in read(ROOT/'app/build.gradle')
assert "versionName '2.4.9'" in read(ROOT/'app/build.gradle')
print('Applied v2.4.9 reliability + target/stop protection without redesigning direct early SELL')
