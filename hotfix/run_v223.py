#!/usr/bin/env python3
from pathlib import Path
import re
import runpy

# Build on the validated v2.2.2 automatic daily-auth candidate.
runpy.run_path("hotfix/run_v222.py", run_name="__main__")

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
        raise RuntimeError(f"Expected exactly one match in {path}: found {count}\n{old[:240]}")
    write(path, text.replace(old, new, 1))


def replace_regex_once(path: Path, pattern: str, replacement: str) -> None:
    text = read(path)
    updated, count = re.subn(pattern, lambda _match: replacement,
                             text, count=1, flags=re.S)
    if count != 1:
        raise RuntimeError(f"Expected exactly one regex match in {path}: found {count}")
    write(path, updated)


# Release identity.
gradle = ROOT / "app/build.gradle"
replace_once(gradle, "versionCode 222", "versionCode 223")
replace_once(gradle, "versionName '2.2.2'", "versionName '2.2.3'")

# One explicit protection policy. Groww rejected the GTT path for a real CASH
# MIS fill with "Product other than CNC/NRML are not allowed". Therefore:
# MIS -> regular DAY SL-M SELL using product MIS.
# CNC -> existing broker-side GTT stop-loss.
write(JAVA / "ProtectionOrderPolicy.java", r'''package com.suhas.multyfiautobuy.stable;

final class ProtectionOrderPolicy {
    static final String REGULAR_MIS_SL_M = "REGULAR_MIS_SL_M";
    static final String CNC_GTT = "CNC_GTT";

    private ProtectionOrderPolicy() { }

    static boolean usesRegularMisStop(String productType) {
        return "MIS".equalsIgnoreCase(productType);
    }

    static String mode(String productType) {
        return usesRegularMisStop(productType) ? REGULAR_MIS_SL_M : CNC_GTT;
    }
}
''')

# Persist whether a protection leg is a regular MIS order or a CNC GTT. Existing
# saved GTT legs migrate safely because missing mode defaults to CNC_GTT.
strategy = JAVA / "Strategy.java"
new_stop_leg = r'''    static final class StopLeg {
        // Historical field name retained for on-device JSON compatibility. For
        // REGULAR_MIS_SL_M it contains a Groww regular-order ID.
        final String smartOrderId;
        final int quantity;
        String status;
        final String protectionMode;
        final String referenceId;

        StopLeg(String brokerOrderId, int quantity, String status) {
            this(brokerOrderId, quantity, status,
                    ProtectionOrderPolicy.CNC_GTT, "");
        }

        StopLeg(String brokerOrderId, int quantity, String status,
                String protectionMode, String referenceId) {
            this.smartOrderId = brokerOrderId == null ? "" : brokerOrderId;
            this.quantity = quantity;
            this.status = status == null ? "" : status;
            this.protectionMode = protectionMode == null || protectionMode.isEmpty()
                    ? ProtectionOrderPolicy.CNC_GTT : protectionMode;
            this.referenceId = referenceId == null ? "" : referenceId;
        }

        boolean isRegularMisStop() {
            return ProtectionOrderPolicy.REGULAR_MIS_SL_M.equals(protectionMode);
        }

        JSONObject toJson() throws Exception {
            JSONObject json = new JSONObject();
            json.put("smart_order_id", smartOrderId);
            json.put("quantity", quantity);
            json.put("status", status);
            json.put("protection_mode", protectionMode);
            json.put("reference_id", referenceId);
            return json;
        }

        static StopLeg fromJson(JSONObject json) {
            return new StopLeg(json.optString("smart_order_id", ""),
                    json.optInt("quantity", 0), json.optString("status", "ACTIVE"),
                    json.optString("protection_mode", ProtectionOrderPolicy.CNC_GTT),
                    json.optString("reference_id", ""));
        }
    }
}'''
replace_regex_once(strategy,
                   r"    static final class StopLeg \{.*?\n    \}\n\}",
                   new_stop_leg)

# Add an idempotent regular MIS SL-M order. A distinct MS reference prefix avoids
# collisions with the invalid SL GTT references created by v2.2.1.
client = JAVA / "GrowwClient.java"
mis_stop_method = r'''    static ApiResult createMisStopLossOrder(String accessToken,
                                                  Strategy strategy,
                                                  int quantity,
                                                  int legNumber) {
        if (strategy == null || quantity <= 0) {
            return ApiResult.failure("", "A valid strategy and positive quantity are required.", 0);
        }
        try {
            String reference = reference("MS", strategy.eventId, legNumber);
            JSONObject body = new JSONObject();
            body.put("trading_symbol", strategy.symbol);
            body.put("quantity", quantity);
            body.put("price", 0);
            body.put("trigger_price", price(strategy.stopLossPrice));
            body.put("validity", "DAY");
            body.put("exchange", "NSE");
            body.put("segment", "CASH");
            body.put("product", "MIS");
            body.put("order_type", "SL_M");
            body.put("transaction_type", "SELL");
            body.put("order_reference_id", reference);

            HttpResult http = request("POST", API_BASE + "/order/create",
                    accessToken, body);
            if (!http.isSuccess()) {
                ApiResult failure = apiFailure(http);
                if ("GA007".equalsIgnoreCase(failure.errorCode)
                        || failure.message.toLowerCase(Locale.US).contains("duplicate")) {
                    OrderStatus recovered = getOrderByReference(accessToken, reference);
                    if (recovered.success && !recovered.orderId.isEmpty()
                            && isLiveRegularStopStatus(recovered.status)) {
                        return ApiResult.success(recovered.orderId, reference,
                                "Recovered existing MIS SL-M order " + recovered.orderId
                                        + " • status " + recovered.status + ".", recovered.httpCode);
                    }
                    return ApiResult.failure(failure.errorCode,
                            failure.message + " Existing MIS stop recovery: "
                                    + recovered.message, failure.httpCode);
                }
                return failure;
            }

            JSONObject payload = new JSONObject(http.body).optJSONObject("payload");
            String id = payload == null ? "" : payload.optString("groww_order_id", "");
            String status = payload == null ? "" : payload.optString("order_status", "");
            String returnedReference = payload == null ? reference
                    : payload.optString("order_reference_id", reference);
            if (id.isEmpty()) {
                return ApiResult.failure("MIS_STOP_NO_ID",
                        "Groww accepted the MIS stop-loss request but returned no order ID.",
                        http.code);
            }
            if (isRejectedRegularStatus(status)) {
                return ApiResult.failure("MIS_STOP_REJECTED",
                        "Groww rejected the MIS SL-M order: " + status + " "
                                + (payload == null ? "" : payload.optString("remark", "")),
                        http.code);
            }
            if (isLiveRegularStopStatus(status)) {
                return ApiResult.success(id, returnedReference,
                        "MIS DAY SL-M stop confirmed " + status + " for " + quantity
                                + " shares at trigger ₹" + price(strategy.stopLossPrice)
                                + ": " + id + ".", http.code);
            }

            OrderStatus confirmed = OrderStatus.failure(0, "Not checked.");
            for (int i = 0; i < 8; i++) {
                confirmed = getOrderByReference(accessToken, returnedReference);
                if (confirmed.success && isLiveRegularStopStatus(confirmed.status)) {
                    return ApiResult.success(confirmed.orderId.isEmpty() ? id : confirmed.orderId,
                            returnedReference,
                            "MIS DAY SL-M stop confirmed " + confirmed.status + " for "
                                    + quantity + " shares at trigger ₹"
                                    + price(strategy.stopLossPrice) + ".", confirmed.httpCode);
                }
                if (confirmed.success && isRejectedRegularStatus(confirmed.status)) break;
                try { Thread.sleep(250L); }
                catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    break;
                }
            }
            return ApiResult.failure("MIS_STOP_NOT_CONFIRMED",
                    "MIS SL-M order ID " + id
                            + " was returned, but OPEN/TRIGGER_PENDING status was not confirmed. "
                            + confirmed.message, http.code);
        } catch (Exception e) {
            return ApiResult.failure("", "MIS stop-loss order error: " + safeMessage(e), 0);
        }
    }

'''
replace_once(client,
             "    static ApiResult createStopLossGtt(String accessToken, Strategy strategy,\n",
             mis_stop_method + "    static ApiResult createStopLossGtt(String accessToken, Strategy strategy,\n")

live_regular_helper = r'''    private static boolean isLiveRegularStopStatus(String status) {
        return "NEW".equalsIgnoreCase(status)
                || "ACKED".equalsIgnoreCase(status)
                || "TRIGGER_PENDING".equalsIgnoreCase(status)
                || "APPROVED".equalsIgnoreCase(status)
                || "OPEN".equalsIgnoreCase(status)
                || "PENDING".equalsIgnoreCase(status)
                || "PARTIALLY_FILLED".equalsIgnoreCase(status)
                || "PARTIAL".equalsIgnoreCase(status);
    }

'''
replace_once(client,
             "    private static boolean isRejectedRegularStatus(String status) {\n",
             live_regular_helper + "    private static boolean isRejectedRegularStatus(String status) {\n")

# Monitor chooses the correct broker protection type, tracks both types, and
# cancels/verifies the correct leg before target, timed, or Multyfi early exits.
monitor = JAVA / "StrategyMonitorService.java"
replace_once(monitor, "import java.util.List;", "import java.util.Iterator;\nimport java.util.List;")

new_protect = r'''    private boolean protectNewFill(String token, Strategy strategy) {
        int delta = strategy.observedFilledQuantity - strategy.protectedQuantity;
        if (delta <= 0) return true;
        if (strategy.lastMessage != null
                && strategy.lastMessage.startsWith("CRITICAL: ")
                && System.currentTimeMillis() - strategy.updatedAt < 15_000L) {
            return false;
        }
        int legNumber = strategy.stopLegs.size() + 1;
        boolean regularMis = ProtectionOrderPolicy.usesRegularMisStop(strategy.productType);
        GrowwClient.ApiResult stop = regularMis
                ? GrowwClient.createMisStopLossOrder(token, strategy, delta, legNumber)
                : GrowwClient.createStopLossGtt(token, strategy, delta, legNumber);
        if (!stop.success) {
            String failure = "CRITICAL: " + delta
                    + " newly filled shares are awaiting confirmed protection. " + stop.message;
            boolean changed = !failure.equals(strategy.lastMessage);
            strategy.lastMessage = failure;
            save(strategy);
            if (changed) {
                AppPrefs.log(this, "STOP-LOSS RETRY PENDING — ARMED RETAINED",
                        strategy.symbol + " • " + strategy.lastMessage
                                + " New entries are paused, but the 24×7 armed preference remains ON.");
            }
            return false;
        }
        String mode = regularMis ? ProtectionOrderPolicy.REGULAR_MIS_SL_M
                : ProtectionOrderPolicy.CNC_GTT;
        strategy.stopLegs.add(new Strategy.StopLeg(stop.id, delta, "ACTIVE",
                mode, stop.secondaryId));
        strategy.protectedQuantity += delta;
        strategy.state = Strategy.PROTECTED;
        strategy.lastMessage = (regularMis
                ? "MIS regular DAY SL-M stop confirmed for "
                : "CNC stop-loss GTT confirmed for ")
                + strategy.protectedQuantity + " filled shares.";
        save(strategy);
        AppPrefs.log(this, regularMis
                        ? "MIS STOP-LOSS ORDER CONFIRMED"
                        : "CNC STOP-LOSS GTT CONFIRMED ACTIVE",
                strategy.symbol + " • " + stop.message);
        return true;
    }

'''
replace_regex_once(monitor,
                   r"    private boolean protectNewFill\(String token, Strategy strategy\) \{.*?(?=    private boolean anyStopLegTriggered)",
                   new_protect)

new_any_triggered = r'''    private boolean anyStopLegTriggered(String token, Strategy strategy) {
        Iterator<Strategy.StopLeg> iterator = strategy.stopLegs.iterator();
        while (iterator.hasNext()) {
            Strategy.StopLeg leg = iterator.next();
            String status = protectionStatus(token, leg);
            if (status.isEmpty()) continue;
            leg.status = status;
            if (isTriggeredStatus(status)) {
                save(strategy);
                return true;
            }
            if (isProtectionCancelledOrRejected(status)) {
                strategy.protectedQuantity = Math.max(0,
                        strategy.protectedQuantity - leg.quantity);
                iterator.remove();
                strategy.state = Strategy.ENTRY_ACTIVE;
                strategy.lastMessage = "CRITICAL: broker protection leg became "
                        + status + "; automatic re-protection is required.";
                save(strategy);
                AppPrefs.log(this, "PROTECTION LOST — RECREATE REQUIRED",
                        strategy.symbol + " • " + strategy.lastMessage);
                return false;
            }
        }
        return false;
    }

    private String protectionStatus(String token, Strategy.StopLeg leg) {
        if (leg.isRegularMisStop()) {
            if (leg.referenceId.isEmpty()) return "";
            GrowwClient.OrderStatus order = GrowwClient.getOrderByReference(
                    token, leg.referenceId);
            return order.success ? order.status : "";
        }
        GrowwClient.SmartStatus smart = GrowwClient.getGtt(token, leg.smartOrderId);
        return smart.success ? smart.status : "";
    }

    private boolean cancelProtectionAndVerify(String token, Strategy.StopLeg leg) {
        if (leg.isRegularMisStop()) {
            GrowwClient.OrderStatus before = GrowwClient.getOrderByReference(
                    token, leg.referenceId);
            if (!before.success) return false;
            if ("CANCELLED".equalsIgnoreCase(before.status)
                    || "CANCELED".equalsIgnoreCase(before.status)) return true;
            if (!isOpenRegularOrderStatus(before.status)) return false;
            String orderId = before.orderId.isEmpty() ? leg.smartOrderId : before.orderId;
            RegularOrderSafety.Result cancelled =
                    RegularOrderSafety.cancelOpenCashOrder(token, orderId);
            if (!cancelled.success) return false;
            for (int i = 0; i < 8; i++) {
                GrowwClient.OrderStatus verified = GrowwClient.getOrderByReference(
                        token, leg.referenceId);
                if (verified.success && ("CANCELLED".equalsIgnoreCase(verified.status)
                        || "CANCELED".equalsIgnoreCase(verified.status))) return true;
                sleep(250L);
            }
            return false;
        }
        GrowwClient.ApiResult cancelled = GrowwClient.cancelGtt(token, leg.smartOrderId);
        if (!cancelled.success) return false;
        for (int i = 0; i < 5; i++) {
            GrowwClient.SmartStatus verified = GrowwClient.getGtt(token, leg.smartOrderId);
            if (verified.success && "CANCELLED".equalsIgnoreCase(verified.status)) return true;
            sleep(250L);
        }
        return false;
    }

'''
replace_regex_once(monitor,
                   r"    private boolean anyStopLegTriggered\(String token, Strategy strategy\) \{.*?(?=    private void cancelEntryRemainder)",
                   new_any_triggered)

# If a cancelled/rejected protection leg was discovered, re-protect before any
# target logic can run.
replace_once(monitor,
             '''        if (anyStopLegTriggered(token, strategy)) {
            strategy.lastMessage = "Stop-loss GTT has triggered; waiting for position settlement.";
            save(strategy);
            return;
        }

        if (!isMarketSession()) return;''',
             '''        if (anyStopLegTriggered(token, strategy)) {
            strategy.lastMessage = "Stop-loss protection has triggered; waiting for position settlement.";
            save(strategy);
            return;
        }
        if (strategy.protectedQuantity < strategy.observedFilledQuantity) {
            protectNewFill(token, strategy);
            return;
        }

        if (!isMarketSession()) return;''')

new_exit_loop = r'''        for (Strategy.StopLeg leg : strategy.stopLegs) {
            String before = protectionStatus(token, leg);
            if (before.isEmpty()) {
                strategy.lastMessage = label
                        + " requested, but stop-loss state could not be verified. No sell submitted.";
                save(strategy);
                return;
            }
            leg.status = before;
            if (isTriggeredStatus(before)) {
                strategy.lastMessage = label
                        + " requested while stop-loss was already triggered. Waiting; no duplicate sell.";
                save(strategy);
                return;
            }
            if ("CANCELLED".equalsIgnoreCase(before)
                    || "CANCELED".equalsIgnoreCase(before)) continue;
            if (!isProtectionActiveStatus(before)) {
                strategy.lastMessage = label + " requested, but stop-loss state is "
                        + before + ". No sell submitted.";
                save(strategy);
                return;
            }
            if (!cancelProtectionAndVerify(token, leg)) {
                strategy.lastMessage = label
                        + " requested, but stop-loss cancellation was not confirmed. No sell submitted.";
                save(strategy);
                return;
            }
            leg.status = "CANCELLED";
        }

'''
replace_regex_once(monitor,
                   r"        for \(Strategy\.StopLeg leg : strategy\.stopLegs\) \{.*?(?=        GrowwClient\.IntResult position = GrowwClient\.getNetPositionQuantity)",
                   new_exit_loop)

replace_once(monitor,
             "    private static boolean isTriggeredStatus(String status) {\n",
             '''    private static boolean isProtectionActiveStatus(String status) {
        return isActiveStatus(status) || isOpenRegularOrderStatus(status);
    }

    private static boolean isProtectionCancelledOrRejected(String status) {
        return "CANCELLED".equalsIgnoreCase(status)
                || "CANCELED".equalsIgnoreCase(status)
                || "REJECTED".equalsIgnoreCase(status)
                || "FAILED".equalsIgnoreCase(status);
    }

    private static boolean isTriggeredStatus(String status) {
''')
replace_once(monitor,
             "Monitors immediate Multyfi entries, early exits, Groww fills, stop-loss GTTs, targets, authentication and Surfshark Dedicated IP.",
             "Monitors Multyfi entries, MIS regular SL-M orders, CNC stop-loss GTTs, early exits, targets, authentication and Surfshark Dedicated IP.")

# Visible release wording.
activity = JAVA / "ProductionActivity.java"
replace_once(activity,
             '"Android 16 • source-built candidate release 2.2.2"',
             '"Android 16 • source-built candidate release 2.2.3"')
replace_once(activity,
             '"Auto-Buy OFF by default • automatic daily Groww verification • source-built v2.2.2"',
             '"Auto-Buy OFF by default • MIS SL-M + CNC GTT protection • source-built v2.2.3"')

write(TEST / "ProtectionOrderPolicyTest.java", r'''package com.suhas.multyfiautobuy.stable;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

public class ProtectionOrderPolicyTest {
    @Test public void misFillUsesRegularSlmNotGtt() {
        assertTrue(ProtectionOrderPolicy.usesRegularMisStop("MIS"));
        assertEquals(ProtectionOrderPolicy.REGULAR_MIS_SL_M,
                ProtectionOrderPolicy.mode("MIS"));
    }

    @Test public void cncFillRetainsGttProtection() {
        assertFalse(ProtectionOrderPolicy.usesRegularMisStop("CNC"));
        assertEquals(ProtectionOrderPolicy.CNC_GTT,
                ProtectionOrderPolicy.mode("CNC"));
    }
}
''')

# Build-time source contract for the live NELCO failure.
assert "versionName '2.2.3'" in read(gradle)
assert "createMisStopLossOrder" in read(client)
assert 'body.put("product", "MIS")' in read(client)
assert 'body.put("order_type", "SL_M")' in read(client)
assert 'reference("MS"' in read(client)
assert "ProtectionOrderPolicy.usesRegularMisStop" in read(monitor)
assert "createStopLossGtt(token, strategy, delta, legNumber)" in read(monitor)
assert "REGULAR_MIS_SL_M" in read(strategy)
assert "MIS regular DAY SL-M stop confirmed" in read(monitor)
print("Applied v2.2.3 MIS regular stop-loss protection fix")
