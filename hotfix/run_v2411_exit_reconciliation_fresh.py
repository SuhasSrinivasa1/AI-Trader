#!/usr/bin/env python3
from pathlib import Path
import runpy

# Start from the exact validated v2.4.10 listener-stable fresh-install source.
runpy.run_path('hotfix/run_v2410_listener_stable_fresh.py', run_name='__main__')

ROOT = Path('android-stable')
APP = ROOT / 'app'
J = APP / 'src/main/java/com/suhas/multyfiautobuy/stable'
T = APP / 'src/test/java/com/suhas/multyfiautobuy/stable'


def read(p): return Path(p).read_text(encoding='utf-8')
def write(p, s): Path(p).write_text(s, encoding='utf-8')
def replace_once(p, old, new):
    p = Path(p); text = read(p); n = text.count(old)
    if n != 1:
        raise RuntimeError(f'{p}: expected exactly one match, found {n}: {old[:180]}')
    write(p, text.replace(old, new, 1))
def replace_method(p, signature, replacement):
    p = Path(p); text = read(p); start = text.find(signature)
    if start < 0: raise RuntimeError(f'Method not found: {signature} in {p}')
    brace = text.find('{', start); depth = 0; end = -1
    for i in range(brace, len(text)):
        if text[i] == '{': depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                end = i + 1; break
    if end < 0: raise RuntimeError(f'Method end not found: {signature}')
    write(p, text[:start] + replacement.rstrip() + text[end:])

# Version + separate fresh-install identity.  The prior fresh signing keys were
# deliberately ephemeral, so this APK is intentionally a distinct app package.
replace_once(APP/'build.gradle', 'versionCode 250', 'versionCode 251')
replace_once(APP/'build.gradle', "versionName '2.4.10'", "versionName '2.4.11'")
replace_once(APP/'build.gradle',
             "applicationId 'com.suhas.multyfiautobuy.v2410fresh'",
             "applicationId 'com.suhas.multyfiautobuy.v2411fresh'")
replace_once(APP/'src/main/res/values/strings.xml',
             '<string name="app_name">Multyfi AutoBuy 2.4.10</string>',
             '<string name="app_name">Multyfi AutoBuy 2.4.11</string>')

# 1) Primary Multyfi target/SL arming must never depend on secondary Groww P&L
# reads.  The target and Multyfi SL are already known from the notification.
# Average-entry/P&L data only enriches the independent gross -₹2,000 guard.
monitor = J/'StrategyMonitorService.java'
replace_method(monitor, '    private boolean ensureFastProfitTargetArmed', r'''    private boolean ensureFastProfitTargetArmed(String token, Strategy strategy) {
        if (!strategy.isIntraday()) return true;

        // Primary protection is notification-derived and can arm immediately.
        strategy.fastExitPrice = strategy.targetPrice;
        strategy.fastProfitArmed = strategy.fastExitPrice > 0d
                && strategy.multyfiStopLossPrice > 0d;
        if (!strategy.fastProfitArmed) return false;

        // Secondary enrichment for the gross -₹2,000 guard.  Failure here must
        // NEVER prevent target/stop protection from becoming active.
        if (strategy.entryAveragePrice <= 0d
                || strategy.protectedQuantity != strategy.observedFilledQuantity) {
            GrowwClient.PositionSnapshot position = GrowwClient.getPositionSnapshot(
                    token, strategy.symbol, strategy.productType);
            if (position.success && position.quantity > 0 && position.netPrice > 0d) {
                strategy.entryAveragePrice = position.netPrice;
                GrowwClient.PnlResult brokerGross = GrowwClient.getDailyRealisedMisPnl(token);
                if (brokerGross.success) strategy.realisedPnlAtProfitArm = brokerGross.value;
                strategy.dailyNetBeforeTrade = DailyNetPnlLedger.netRealised(this);
                double dailyGrossBefore = DailyGrossPnlLedger.grossRealised(this);
                strategy.dailyProfitNeeded = 0d;
                strategy.dailyTargetPrice = 0d;
                strategy.dynamicLossStopPrice = DailyRiskPolicy.grossLossDisplayPrice(
                        strategy.entryAveragePrice, strategy.observedFilledQuantity, dailyGrossBefore);
            }
        }
        save(strategy);
        AppPrefs.log(this, "MULTYFI TARGET + STOP WATCH ARMED",
                strategy.symbol + " • qty " + strategy.observedFilledQuantity
                        + " • target ₹" + money(strategy.targetPrice)
                        + " • stop-loss ₹" + money(strategy.multyfiStopLossPrice)
                        + (strategy.entryAveragePrice > 0d
                        ? " • gross -₹2,000 guard reference ₹" + money(strategy.dynamicLossStopPrice)
                        : " • gross -₹2,000 enrichment will retry when Groww average-price data is available")
                        + " • app-side 250 ms watcher active.");
        return true;
    }''')

# 2) Early exit reconciliation: broker position is authoritative.  A fully filled
# MIS position must not be held hostage by a stale NEW status on the original BUY.
# Partial fills still cancel the unfilled BUY remainder before selling.
replace_method(monitor, '    private void processEarlyExit', r'''    private void processEarlyExit(String token, Strategy strategy, int remaining,
                                  boolean staticIpReady) {
        if (!isMarketSession()) {
            strategy.lastMessage = "Multyfi early exit is queued for the next market session.";
            save(strategy);
            return;
        }
        if (!staticIpReady) {
            strategy.lastMessage = "Multyfi early exit requested, but Surfshark Dedicated IP is not verified. No sell submitted.";
            save(strategy);
            return;
        }

        // Read the broker position FIRST.  This is the authoritative exposure.
        GrowwClient.IntResult first = GrowwClient.getNetPositionQuantity(
                token, strategy.symbol, strategy.productType);
        if (!first.success) {
            strategy.lastMessage = "Multyfi early exit is persisted; Groww position read failed and will retry.";
            save(strategy);
            requestImmediateTick(this, strategy.eventId);
            return;
        }
        remaining = strategy.remainingStrategyQuantity(first.value);
        int detected = detectFilledQuantity(token, strategy, remaining);
        strategy.observedFilledQuantity = Math.max(strategy.observedFilledQuantity,
                Math.min(strategy.requestedQuantity, detected));

        boolean fullFillKnown = remaining >= strategy.requestedQuantity
                || strategy.observedFilledQuantity >= strategy.requestedQuantity
                || strategy.protectedQuantity >= strategy.requestedQuantity;

        // If the broker currently holds the complete requested quantity, there is
        // no unfilled remainder capable of creating a later duplicate BUY.  Sell now.
        if (remaining >= strategy.requestedQuantity && strategy.requestedQuantity > 0) {
            strategy.entryOrderId = "";
            strategy.entrySmartOrderId = "";
            save(strategy);
            AppPrefs.log(this, "EARLY EXIT FULL POSITION CONFIRMED",
                    strategy.symbol + " • Groww confirms full MIS quantity " + remaining
                            + "; stale entry status will not delay MARKET SELL.");
            executeExit(token, strategy, true, EXIT_MULTYFI_EARLY);
            return;
        }

        // Flat after a known full fill means an automatic/manual exit already
        // completed.  Release stale local state instead of remaining ACTIVE forever.
        if (remaining <= 0 && fullFillKnown) {
            strategy.entryOrderId = "";
            strategy.entrySmartOrderId = "";
            closeStrategy(strategy,
                    "Groww position is zero; automatic or manual early exit completed and stale local state was cleared.");
            return;
        }

        // Partial/uncertain fill: cancel only the still-unfilled BUY remainder.
        if (!cancelEntryAndVerify(token, strategy)) {
            strategy.lastMessage = "Multyfi early exit is persisted; cancelling the BUY remainder before selling the broker-confirmed filled quantity.";
            save(strategy);
            AppPrefs.log(this, "EARLY EXIT WAITING — WILL RETRY",
                    strategy.symbol + " • BUY remainder cancellation is not terminal yet; retry scheduled.");
            requestImmediateTick(this, strategy.eventId);
            return;
        }

        GrowwClient.IntResult refreshed = GrowwClient.getNetPositionQuantity(
                token, strategy.symbol, strategy.productType);
        if (!refreshed.success) {
            strategy.lastMessage = "BUY remainder is terminal, but position refresh failed; early exit will retry.";
            save(strategy);
            requestImmediateTick(this, strategy.eventId);
            return;
        }
        remaining = strategy.remainingStrategyQuantity(refreshed.value);
        detected = detectFilledQuantity(token, strategy, remaining);
        strategy.observedFilledQuantity = Math.max(strategy.observedFilledQuantity,
                Math.min(strategy.requestedQuantity, detected));
        if (remaining <= 0) {
            closeStrategy(strategy,
                    "Groww position is zero after entry-remainder reconciliation; no SELL quantity remains.");
            return;
        }

        // Sell exactly the broker-confirmed strategy quantity after cancellation.
        executeExit(token, strategy, true, EXIT_MULTYFI_EARLY);
    }''')

# 3) Entry log must describe the actual v2.4.11 protection semantics.
service = J/'ProductionNotificationService.java'
s = read(service)
s = s.replace(' (audit only)', ' (active app-side protection)')
write(service, s)

# Small pure policy used by tests/documentation of the reconciliation decision.
write(J/'ExitReconciliationPolicy.java', r'''package com.suhas.multyfiautobuy.stable;

final class ExitReconciliationPolicy {
    private ExitReconciliationPolicy() { }
    static boolean fullBrokerPosition(int remaining, int requested) {
        return requested > 0 && remaining >= requested;
    }
    static boolean flatAfterKnownFullFill(int remaining, int requested,
                                          int observed, int protectedQuantity) {
        return remaining <= 0 && requested > 0
                && (observed >= requested || protectedQuantity >= requested);
    }
}''')

write(T/'V2411ExitReconciliationPolicyTest.java', r'''package com.suhas.multyfiautobuy.stable;

import org.junit.Test;
import static org.junit.Assert.*;

public class V2411ExitReconciliationPolicyTest {
    @Test public void fullPositionDoesNotWaitOnStaleBuyStatus() {
        assertTrue(ExitReconciliationPolicy.fullBrokerPosition(1180, 1180));
        assertFalse(ExitReconciliationPolicy.fullBrokerPosition(900, 1180));
    }
    @Test public void flatKnownFullFillCanReleaseStaleStrategy() {
        assertTrue(ExitReconciliationPolicy.flatAfterKnownFullFill(0, 1180, 1180, 0));
        assertTrue(ExitReconciliationPolicy.flatAfterKnownFullFill(0, 1180, 0, 1180));
        assertFalse(ExitReconciliationPolicy.flatAfterKnownFullFill(0, 1180, 500, 500));
    }
}''')

# Hard regression contracts.
service_text = read(service)
monitor_text = read(monitor)
assert 'GrowwClient.placeEarlyExitMarketSell' in service_text
assert 'Groww MARKET SELL was called before audit logging.' in service_text
assert 'EARLY EXIT FULL POSITION CONFIRMED' in monitor_text
assert 'Groww position is zero; automatic or manual early exit completed' in monitor_text
assert 'MULTYFI TARGET + STOP WATCH ARMED' in monitor_text
assert 'strategy.fastProfitArmed = strategy.fastExitPrice > 0d' in monitor_text
assert 'active app-side protection' in service_text
assert 'NotificationListenerHealth.ensureBound(this)' in monitor_text
assert 'versionCode 251' in read(APP/'build.gradle')
assert "versionName '2.4.11'" in read(APP/'build.gradle')
assert "applicationId 'com.suhas.multyfiautobuy.v2411fresh'" in read(APP/'build.gradle')

print('Applied v2.4.11 EXIT RECONCILIATION: broker-position-first early exit + stale-flat cleanup + target/SL primary arming')
