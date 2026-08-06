#!/usr/bin/env python3
from pathlib import Path
import runpy

# Preserve the validated v2.3.2 blocklist-based Intraday MIS release.
runpy.run_path("hotfix/run_v232_fixed.py", run_name="__main__")

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
        raise RuntimeError(
            f"Expected one match in {path}, found {count}: {old[:220]}"
        )
    write(path, text.replace(old, new, 1))


def replace_java_method(path: Path, signature: str, replacement: str) -> None:
    text = read(path)
    start = text.find(signature)
    if start < 0:
        raise RuntimeError(f"Could not locate Java method in {path}: {signature}")
    open_brace = text.find("{", start)
    if open_brace < 0:
        raise RuntimeError(f"Could not locate method brace in {path}: {signature}")
    depth = 0
    end = -1
    for index in range(open_brace, len(text)):
        char = text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                end = index + 1
                break
    if end < 0:
        raise RuntimeError(f"Could not locate method end in {path}: {signature}")
    write(path, text[:start] + replacement.rstrip() + text[end:])


# Release identity.
gradle = ROOT / "app/build.gradle"
replace_once(gradle, "versionCode 232", "versionCode 233")
replace_once(gradle, "versionName '2.3.2'", "versionName '2.3.3'")


# Pure policy used by the cancellation path and unit tests.
write(JAVA / "EarlyExitProtectionPolicy.java", r'''package com.suhas.multyfiautobuy.stable;

final class EarlyExitProtectionPolicy {
    private EarlyExitProtectionPolicy() { }

    static boolean isCancelled(String status) {
        return "CANCELLED".equalsIgnoreCase(status)
                || "CANCELED".equalsIgnoreCase(status);
    }

    static boolean isCancellationPending(String status) {
        return "CANCELLATION_REQUESTED".equalsIgnoreCase(status);
    }

    static boolean isTriggeredOrExecuted(String status) {
        return "TRIGGERED".equalsIgnoreCase(status)
                || "EXECUTED".equalsIgnoreCase(status)
                || "COMPLETED".equalsIgnoreCase(status)
                || "COMPLETE".equalsIgnoreCase(status)
                || "DELIVERY_AWAITED".equalsIgnoreCase(status);
    }

    static boolean isOpen(String status) {
        return "NEW".equalsIgnoreCase(status)
                || "ACKED".equalsIgnoreCase(status)
                || "TRIGGER_PENDING".equalsIgnoreCase(status)
                || "APPROVED".equalsIgnoreCase(status)
                || "OPEN".equalsIgnoreCase(status)
                || "PENDING".equalsIgnoreCase(status)
                || "PARTIALLY_FILLED".equalsIgnoreCase(status)
                || "PARTIAL".equalsIgnoreCase(status)
                || isCancellationPending(status);
    }

    static boolean shouldSendCancel(String status) {
        return isOpen(status) && !isCancellationPending(status);
    }
}
''')


# Add direct order-id status lookup. Groww exposes both order-id and reference-id
# status endpoints. For a cancellation, the order-id endpoint is the primary
# source because the reference endpoint can lag behind the cancellation response.
client = JAVA / "GrowwClient.java"
insert_anchor = "\n    static IntResult getNetPositionQuantity(String accessToken, String symbol,"
if insert_anchor not in read(client):
    raise RuntimeError("Could not locate GrowwClient position method insertion point")
get_by_id = r'''
    static OrderStatus getOrderById(String accessToken, String growwOrderId) {
        if (growwOrderId == null || growwOrderId.trim().isEmpty()) {
            return OrderStatus.failure(0, "Groww order ID is missing.");
        }
        try {
            HttpResult http = request("GET",
                    API_BASE + "/order/status/" + enc(growwOrderId.trim())
                            + "?segment=CASH",
                    accessToken, null);
            if (!http.isSuccess()) return OrderStatus.failure(http.code, http.message());
            JSONObject payload = new JSONObject(http.body).optJSONObject("payload");
            if (payload == null) return OrderStatus.failure(http.code,
                    "Order-id response had no payload.");
            return OrderStatus.success(payload.optString("groww_order_id", growwOrderId),
                    payload.optString("order_status", ""),
                    payload.optInt("filled_quantity", 0),
                    payload.optString("remark", ""));
        } catch (Exception e) {
            return OrderStatus.failure(0,
                    "Order-id status error: " + safeMessage(e));
        }
    }
'''
replace_once(client, insert_anchor, "\n" + get_by_id.rstrip() + insert_anchor)


monitor = JAVA / "StrategyMonitorService.java"

# The live GSPCROP failure happened after a regular MIS DAY SL was confirmed.
# The early-exit path did not reach MARKET SELL submission because cancellation
# confirmation was not obtained. Poll the official order-id endpoint first,
# avoid resending cancel while CANCELLATION_REQUESTED, and retain the reference
# endpoint only as a fallback.
cancel_method = r'''    private boolean cancelProtectionAndVerify(String token, Strategy.StopLeg leg) {
        if (leg.isRegularMisStop()) {
            String orderId = leg.smartOrderId == null ? "" : leg.smartOrderId.trim();
            GrowwClient.OrderStatus before = !orderId.isEmpty()
                    ? GrowwClient.getOrderById(token, orderId)
                    : GrowwClient.OrderStatus.failure(0, "Order ID unavailable.");
            if (!before.success && leg.referenceId != null
                    && !leg.referenceId.isEmpty()) {
                before = GrowwClient.getOrderByReference(token, leg.referenceId);
            }
            if (!before.success) return false;
            if (EarlyExitProtectionPolicy.isCancelled(before.status)) return true;
            if (EarlyExitProtectionPolicy.isTriggeredOrExecuted(before.status)) {
                return false;
            }
            if (!EarlyExitProtectionPolicy.isOpen(before.status)) return false;

            if (orderId.isEmpty()) orderId = before.orderId;
            if (orderId == null || orderId.isEmpty()) return false;

            if (EarlyExitProtectionPolicy.shouldSendCancel(before.status)) {
                RegularOrderSafety.Result cancelled =
                        RegularOrderSafety.cancelOpenCashOrder(token, orderId);
                if (!cancelled.success) return false;
                if (EarlyExitProtectionPolicy.isCancelled(cancelled.message)) {
                    leg.status = "CANCELLED";
                    return true;
                }
            }

            // Cancellation can briefly remain CANCELLATION_REQUESTED. Poll by
            // Groww order ID for up to 10 seconds, with reference-id fallback.
            for (int i = 0; i < 50; i++) {
                GrowwClient.OrderStatus verified = GrowwClient.getOrderById(
                        token, orderId);
                if (!verified.success && leg.referenceId != null
                        && !leg.referenceId.isEmpty()) {
                    verified = GrowwClient.getOrderByReference(
                            token, leg.referenceId);
                }
                if (verified.success
                        && EarlyExitProtectionPolicy.isCancelled(verified.status)) {
                    leg.status = "CANCELLED";
                    return true;
                }
                if (verified.success
                        && EarlyExitProtectionPolicy.isTriggeredOrExecuted(
                                verified.status)) {
                    leg.status = verified.status;
                    return false;
                }
                sleep(200L);
            }
            return false;
        }

        GrowwClient.ApiResult cancelled = GrowwClient.cancelGtt(
                token, leg.smartOrderId);
        if (!cancelled.success) return false;
        for (int i = 0; i < 30; i++) {
            GrowwClient.SmartStatus verified = GrowwClient.getGtt(
                    token, leg.smartOrderId);
            if (verified.success
                    && EarlyExitProtectionPolicy.isCancelled(verified.status)) {
                leg.status = "CANCELLED";
                return true;
            }
            if (verified.success
                    && EarlyExitProtectionPolicy.isTriggeredOrExecuted(
                            verified.status)) {
                leg.status = verified.status;
                return false;
            }
            sleep(200L);
        }
        return false;
    }
'''
replace_java_method(monitor, "    private boolean cancelProtectionAndVerify(", cancel_method)


# Make a blocked sell visible in the activity timeline instead of silently
# updating only the strategy record. This allows immediate manual intervention.
old_block = r'''            if (!cancelProtectionAndVerify(token, leg)) {
                strategy.lastMessage = label
                        + " requested, but stop-loss cancellation was not confirmed. Retrying before the market sell.";
                save(strategy);
                if (authoritativeEarly) requestImmediateTick(this, strategy.eventId);
                return;
            }
'''
new_block = r'''            if (!cancelProtectionAndVerify(token, leg)) {
                String waiting = label
                        + " requested, but stop-loss cancellation was not confirmed. "
                        + "The MARKET sell has NOT been submitted; retry remains queued.";
                boolean changed = !waiting.equals(strategy.lastMessage);
                strategy.lastMessage = waiting;
                save(strategy);
                if (authoritativeEarly && changed) {
                    AppPrefs.log(this,
                            "MULTYFI EARLY EXIT WAITING — STOP CANCEL NOT CONFIRMED",
                            strategy.symbol + " • " + waiting);
                }
                if (authoritativeEarly) requestImmediateTick(this, strategy.eventId);
                return;
            }
'''
replace_once(monitor, old_block, new_block)


# Record the exact hand-off point between protection cancellation and sell.
old_position = r'''        GrowwClient.IntResult position = GrowwClient.getNetPositionQuantity(
                token, strategy.symbol, strategy.productType);
'''
new_position = r'''        if (authoritativeEarly) {
            AppPrefs.log(this, "MULTYFI EARLY EXIT PROTECTION CANCELLED",
                    strategy.symbol
                            + " • all tracked protection is cancelled; verifying the live position before MARKET sell.");
        }

        GrowwClient.IntResult position = GrowwClient.getNetPositionQuantity(
                token, strategy.symbol, strategy.productType);
'''
# Only replace the occurrence inside executeExit. There may be another identical
# position lookup earlier, so locate it relative to executeExit.
text = read(monitor)
start = text.find("    private void executeExit(")
if start < 0:
    raise RuntimeError("executeExit method not found")
pos = text.find(old_position, start)
if pos < 0:
    raise RuntimeError("executeExit position lookup not found")
write(monitor, text[:pos] + new_position + text[pos + len(old_position):])


# Visible version text only; no entry, budget, stop-price or parser behaviour is changed.
activity = JAVA / "ProductionActivity.java"
write(activity, read(activity).replace("2.3.2", "2.3.3"))


write(TEST / "EarlyExitProtectionPolicyTest.java", r'''package com.suhas.multyfiautobuy.stable;

import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

public class EarlyExitProtectionPolicyTest {
    @Test public void cancellationRequestedWaitsWithoutSendingDuplicateCancel() {
        assertTrue(EarlyExitProtectionPolicy.isOpen("CANCELLATION_REQUESTED"));
        assertTrue(EarlyExitProtectionPolicy.isCancellationPending(
                "CANCELLATION_REQUESTED"));
        assertFalse(EarlyExitProtectionPolicy.shouldSendCancel(
                "CANCELLATION_REQUESTED"));
    }

    @Test public void triggerPendingNeedsOneCancelRequest() {
        assertTrue(EarlyExitProtectionPolicy.isOpen("TRIGGER_PENDING"));
        assertTrue(EarlyExitProtectionPolicy.shouldSendCancel("TRIGGER_PENDING"));
    }

    @Test public void cancelledAllowsMarketSellAndExecutedBlocksDuplicateSell() {
        assertTrue(EarlyExitProtectionPolicy.isCancelled("CANCELLED"));
        assertTrue(EarlyExitProtectionPolicy.isTriggeredOrExecuted("EXECUTED"));
        assertFalse(EarlyExitProtectionPolicy.isCancelled("EXECUTED"));
    }
}
''')


# Build-time safety contracts.
assert "versionCode 233" in read(gradle)
assert "versionName '2.3.3'" in read(gradle)
assert "static OrderStatus getOrderById" in read(client)
assert 'API_BASE + "/order/status/"' in read(client)
assert "CANCELLATION_REQUESTED" in read(JAVA / "EarlyExitProtectionPolicy.java")
assert "MULTYFI EARLY EXIT WAITING — STOP CANCEL NOT CONFIRMED" in read(monitor)
assert "MULTYFI EARLY EXIT PROTECTION CANCELLED" in read(monitor)
assert "GrowwClient.getOrderById" in read(monitor)
assert "queueEarlyExit(earlyExit)" in read(JAVA / "ProductionNotificationService.java")
assert "MULTYFI EARLY EXIT PERSISTED" in read(JAVA / "ProductionNotificationService.java")
assert "acceptsUnlabelledNewEquityTradeAsMis" in read(
        TEST / "IntradayOnlyPolicyTest.java")
print("Applied Multyfi AutoBuy Pro v2.3.3 early-exit stop-cancellation fix")
