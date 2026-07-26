from pathlib import Path
import runpy

ROOT = Path(__file__).resolve().parent
JAVA = ROOT / "app/src/main/java/com/suhas/multyfiautobuy/stable"
TEST = ROOT / "app/src/test/java/com/suhas/multyfiautobuy/stable"


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected exactly one match in {path}: found {count}\n---\n{old[:300]}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


# The original patch intentionally performs all transformations before the large
# notification entry block. Its legacy non-raw replacement stops at that exact
# boundary; continue here with correctly escaped Java string literals.
try:
    runpy.run_path(str(ROOT / "apply_v1_6_patch.py"), run_name="__main__")
except RuntimeError as error:
    if "SUBMITTING ENTRY GTT" not in str(error):
        raise

listener = JAVA / "MultyfiNotificationService.java"
replace_once(listener,
r'''            AppPrefs.log(this, "SUBMITTING ENTRY GTT", summary
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
''',
r'''            String requestedMode = earlyWindow
                    ? "DIRECT CAPPED LIMIT" : "GTT / CAPPED LIMIT FALLBACK";
            AppPrefs.log(this, "SUBMITTING ENTRY", summary
                    + " • mode " + requestedMode
                    + " • LTP ₹" + String.format(Locale.US, "%.2f", ltp.value)
                    + " • baseline " + signal.productType + " position "
                    + baseline.value + ".");
            GrowwClient.ApiResult result = earlyWindow
                    ? GrowwClient.createImmediateEntryLimit(token, signal,
                    quantity, ltp.value)
                    : GrowwClient.createEntryGttWithLimitFallback(token, signal,
                    quantity, ltp.value);
            if (result.success) {
                long lifecycleAnchor = lifecycleAnchor(signal);
                String smartOrderId = result.secondaryId == null
                        || result.secondaryId.isEmpty() ? result.id : "";
                Strategy strategy = new Strategy(signal.eventId, signal.symbol,
                        signal.category, signal.productType, quantity,
                        signal.targetPrice, signal.stopLossPrice, baseline.value,
                        signal.referenceId, smartOrderId, lifecycleAnchor);
                StrategyStore.upsert(this, strategy);
                AppPrefs.markProcessed(this, signal.eventId);
                AppPrefs.incrementDailyBuyCount(this);
                AppPrefs.log(this, "ENTRY CONFIRMED", summary + "\n"
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
                AppPrefs.log(this, "ENTRY FAILED", summary + "\n"
                        + result.message + (result.errorCode.isEmpty()
                        ? "" : " [" + result.errorCode + "]"));
            }
''')
replace_once(listener,
'''                        "Maximum four automatic entry GTTs reached for today.",
''',
'''                        "Maximum four automatic entries reached for today.",
''')
replace_once(listener,
'''        if (strategy.entrySmartOrderId == null || strategy.entrySmartOrderId.isEmpty()) {
            return true;
        }
''',
'''        if (strategy.entrySmartOrderId == null || strategy.entrySmartOrderId.isEmpty()) {
            GrowwClient.OrderStatus order = GrowwClient.getOrderByReference(
                    token, strategy.entryReferenceId);
            if (!order.success) return false;
            if (isTerminalRegularOrderStatus(order.status)) return true;
            if (!isOpenRegularOrderStatus(order.status)
                    || order.orderId == null || order.orderId.isEmpty()) return false;
            RegularOrderSafety.Result cancelled =
                    RegularOrderSafety.cancelOpenCashOrder(token, order.orderId);
            if (!cancelled.success) return false;
            for (int i = 0; i < 8; i++) {
                order = GrowwClient.getOrderByReference(token,
                        strategy.entryReferenceId);
                if (order.success && isTerminalRegularOrderStatus(order.status)) {
                    StrategyStore.upsert(this, strategy);
                    return true;
                }
                sleep(300L);
            }
            return false;
        }
''')

monitor = JAVA / "StrategyMonitorService.java"
replace_once(monitor,
'''    private boolean cancelEntryAndVerify(String token, Strategy strategy) {
        if (strategy.entrySmartOrderId == null || strategy.entrySmartOrderId.isEmpty()) return true;
        GrowwClient.SmartStatus entry = GrowwClient.getGtt(token,
''',
'''    private boolean cancelEntryAndVerify(String token, Strategy strategy) {
        if (strategy.entrySmartOrderId == null || strategy.entrySmartOrderId.isEmpty()) {
            GrowwClient.OrderStatus order = GrowwClient.getOrderByReference(
                    token, strategy.entryReferenceId);
            if (!order.success) return false;
            if (isTerminalRegularOrderStatus(order.status)) return true;
            if (!isOpenRegularOrderStatus(order.status)
                    || order.orderId == null || order.orderId.isEmpty()) return false;
            RegularOrderSafety.Result cancel =
                    RegularOrderSafety.cancelOpenCashOrder(token, order.orderId);
            if (!cancel.success) return false;
            for (int i = 0; i < 8; i++) {
                order = GrowwClient.getOrderByReference(token,
                        strategy.entryReferenceId);
                if (order.success && isTerminalRegularOrderStatus(order.status)) {
                    return true;
                }
                try { Thread.sleep(300L); }
                catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    return false;
                }
            }
            return false;
        }
        GrowwClient.SmartStatus entry = GrowwClient.getGtt(token,
''')
replace_once(monitor,
'''    private static boolean isActiveStatus(String status) {
''',
'''    private static boolean isOpenRegularOrderStatus(String status) {
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

    private static boolean isActiveStatus(String status) {
''')

build = ROOT / "app/build.gradle"
replace_once(build, "        versionCode 150\n        versionName '1.5.0'\n",
             "        versionCode 160\n        versionName '1.6.0'\n")

entry_policy_test = r'''package com.suhas.multyfiautobuy.stable;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

import java.time.ZoneId;
import java.time.ZonedDateTime;

public class EntryPolicyTest {
    @Test
    public void earlyWindowIsStartInclusiveAndEndExclusive() {
        assertTrue(EntryPolicy.isInWindow(atIst(9, 0), 9 * 60, 10 * 60));
        assertTrue(EntryPolicy.isInWindow(atIst(9, 59), 9 * 60, 10 * 60));
        assertFalse(EntryPolicy.isInWindow(atIst(10, 0), 9 * 60, 10 * 60));
    }

    @Test
    public void sizesEarlyByBudgetAndLateByFixedQuantity() {
        assertEquals(14, EntryPolicy.quantity(694.25d, true,
                10_000d, 10, 10_000));
        assertEquals(10, EntryPolicy.quantity(694.25d, false,
                10_000d, 10, 10_000));
        assertEquals(0, EntryPolicy.quantity(12_000d, true,
                10_000d, 10, 10_000));
    }

    @Test
    public void parsesConfigurableWindowTimes() {
        assertEquals(540, EntryPolicy.parseMinuteOfDay("09:00"));
        assertEquals(600, EntryPolicy.parseMinuteOfDay("10:00"));
        assertEquals(-1, EntryPolicy.parseMinuteOfDay("25:00"));
        assertEquals("09:00", EntryPolicy.formatMinuteOfDay(540));
    }

    private static long atIst(int hour, int minute) {
        return ZonedDateTime.of(2026, 7, 24, hour, minute, 0, 0,
                ZoneId.of("Asia/Kolkata")).toInstant().toEpochMilli();
    }
}
'''
TEST.mkdir(parents=True, exist_ok=True)
(TEST / "EntryPolicyTest.java").write_text(entry_policy_test, encoding="utf-8")

print("Applied Multyfi AutoBuy S24 v1.6.0 time-window patch wrapper.")
