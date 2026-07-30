#!/usr/bin/env python3
from pathlib import Path
import re
import runpy

# Build only on the fully validated v2.2.4 trade-type-budget release chain.
runpy.run_path("hotfix/run_v224.py", run_name="__main__")

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
        raise RuntimeError(f"Expected one match in {path}, found {count}: {old[:180]}")
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
replace_once(gradle, "versionCode 224", "versionCode 225")
replace_once(gradle, "versionName '2.2.4'", "versionName '2.2.5'")

# Groww may initially return NEW/ACKED and reject the order moments later. Only
# TRIGGER_PENDING/OPEN/APPROVED is durable protection. References are 20-char
# alphanumeric values and change after a rejected attempt.
write(JAVA / "MisStopOrderPolicy.java", r'''package com.suhas.multyfiautobuy.stable;

import java.util.Locale;

final class MisStopOrderPolicy {
    private MisStopOrderPolicy() { }

    static boolean isDurable(String status) {
        return "TRIGGER_PENDING".equalsIgnoreCase(status)
                || "OPEN".equalsIgnoreCase(status)
                || "APPROVED".equalsIgnoreCase(status);
    }

    static boolean isTransient(String status) {
        return status == null || status.trim().isEmpty()
                || "NEW".equalsIgnoreCase(status)
                || "ACKED".equalsIgnoreCase(status)
                || "PENDING".equalsIgnoreCase(status)
                || "MODIFICATION_REQUESTED".equalsIgnoreCase(status);
    }

    static boolean isTerminalFailure(String status) {
        return "REJECTED".equalsIgnoreCase(status)
                || "FAILED".equalsIgnoreCase(status)
                || "CANCELLED".equalsIgnoreCase(status)
                || "CANCELED".equalsIgnoreCase(status);
    }

    static String freshReference(String eventId, long nowMillis) {
        String clean = eventId == null ? "EVENT00000"
                : eventId.replaceAll("[^A-Za-z0-9]", "").toUpperCase(Locale.US);
        if (clean.length() < 10) clean = (clean + "0000000000").substring(0, 10);
        else clean = clean.substring(0, 10);
        String nonce = Long.toString(Math.abs(nowMillis), 36).toUpperCase(Locale.US);
        if (nonce.length() < 8) nonce = ("00000000" + nonce).substring(nonce.length());
        else nonce = nonce.substring(nonce.length() - 8);
        return "MS" + clean + nonce;
    }
}
''')

client = JAVA / "GrowwClient.java"

mis_method = r'''    static ApiResult createMisStopLossOrder(String accessToken,
                                                  Strategy strategy,
                                                  int quantity,
                                                  int legNumber) {
        if (strategy == null || quantity <= 0) {
            return ApiResult.failure("", "A valid strategy and positive quantity are required.", 0);
        }
        try {
            // Recover a previously accepted protection order before creating a new one.
            ApiResult existing = findDurableMisStop(accessToken, strategy, quantity);
            if (existing.success) return existing;

            String reference = MisStopOrderPolicy.freshReference(
                    strategy.eventId, System.currentTimeMillis());
            JSONObject body = new JSONObject();
            body.put("trading_symbol", strategy.symbol);
            body.put("quantity", quantity);
            // Groww documents price as a LIMIT-order field. Do not send price=0 for SL_M.
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
                OrderStatus recovered = getOrderByReference(accessToken, reference);
                if (recovered.success && MisStopOrderPolicy.isDurable(recovered.status)) {
                    return ApiResult.success(recovered.orderId, reference,
                            "Recovered durable MIS SL-M order " + recovered.orderId
                                    + " • status " + recovered.status + ".", recovered.httpCode);
                }
                if (recovered.success && MisStopOrderPolicy.isTerminalFailure(recovered.status)) {
                    return ApiResult.failure("MIS_STOP_REJECTED",
                            "MIS SL-M reference " + reference + " became "
                                    + recovered.status + ": " + recovered.message
                                    + ". A fresh reference will be used on the next retry.",
                            recovered.httpCode);
                }
                return ApiResult.failure(failure.errorCode,
                        failure.message + " Reference recovery: " + recovered.message,
                        failure.httpCode);
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
            if (MisStopOrderPolicy.isTerminalFailure(status)) {
                return ApiResult.failure("MIS_STOP_REJECTED",
                        "Groww rejected the MIS SL-M order: " + status + " "
                                + (payload == null ? "" : payload.optString("remark", ""))
                                + ". A fresh reference will be used on the next retry.",
                        http.code);
            }
            if (MisStopOrderPolicy.isDurable(status)) {
                return ApiResult.success(id, returnedReference,
                        "MIS DAY SL-M stop confirmed " + status + " for " + quantity
                                + " shares at trigger ₹" + price(strategy.stopLossPrice)
                                + ": " + id + ".", http.code);
            }

            // NEW/ACKED is submission acknowledgement, not confirmed protection.
            OrderStatus confirmed = OrderStatus.failure(0, "Not checked.");
            for (int i = 0; i < 24; i++) {
                confirmed = getOrderByReference(accessToken, returnedReference);
                if (confirmed.success && MisStopOrderPolicy.isDurable(confirmed.status)) {
                    return ApiResult.success(confirmed.orderId.isEmpty() ? id : confirmed.orderId,
                            returnedReference,
                            "MIS DAY SL-M stop confirmed " + confirmed.status + " for "
                                    + quantity + " shares at trigger ₹"
                                    + price(strategy.stopLossPrice) + ".", confirmed.httpCode);
                }
                if (confirmed.success
                        && MisStopOrderPolicy.isTerminalFailure(confirmed.status)) {
                    return ApiResult.failure("MIS_STOP_REJECTED",
                            "MIS SL-M order " + id + " became " + confirmed.status
                                    + ": " + confirmed.message
                                    + ". A fresh reference will be used on the next retry.",
                            confirmed.httpCode);
                }
                try { Thread.sleep(250L); }
                catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    break;
                }
            }

            // A delayed broker acknowledgement may have become durable after the
            // reference polling window. Recover by order list before failing safe.
            existing = findDurableMisStop(accessToken, strategy, quantity);
            if (existing.success) return existing;
            return ApiResult.failure("MIS_STOP_NOT_DURABLE",
                    "MIS SL-M order " + id + " remains "
                            + (confirmed.status.isEmpty() ? status : confirmed.status)
                            + "; NEW/ACKED is not counted as protection. New entries remain paused.",
                    http.code);
        } catch (Exception e) {
            return ApiResult.failure("", "MIS stop-loss order error: " + safeMessage(e), 0);
        }
    }
'''
replace_java_method(client, "    static ApiResult createMisStopLossOrder(", mis_method)

# Add recovery of an already-live MIS stop. This prevents duplicate protection
# if the create response was lost or delayed.
recovery_method = r'''    private static ApiResult findDurableMisStop(String accessToken,
                                                     Strategy strategy,
                                                     int expectedQuantity) {
        try {
            HttpResult http = request("GET",
                    API_BASE + "/order/list?segment=CASH&page=0&page_size=100",
                    accessToken, null);
            if (!http.isSuccess()) return ApiResult.failure("", http.message(), http.code);
            JSONObject payload = new JSONObject(http.body).optJSONObject("payload");
            JSONArray orders = payload == null ? null : payload.optJSONArray("order_list");
            if (orders == null) return ApiResult.failure("", "Order list had no entries.", http.code);
            for (int i = 0; i < orders.length(); i++) {
                JSONObject order = orders.optJSONObject(i);
                if (order == null) continue;
                String symbol = order.optString("trading_symbol", "");
                String product = order.optString("product", "");
                String transaction = order.optString("transaction_type", "");
                String orderType = order.optString("order_type", "");
                String status = order.optString("order_status", "");
                int quantity = order.optInt("quantity", 0);
                double trigger = order.optDouble("trigger_price", -1d);
                if (!strategy.symbol.equalsIgnoreCase(symbol)
                        || !"MIS".equalsIgnoreCase(product)
                        || !"SELL".equalsIgnoreCase(transaction)
                        || !("SL_M".equalsIgnoreCase(orderType)
                            || "SL-M".equalsIgnoreCase(orderType))
                        || !MisStopOrderPolicy.isDurable(status)
                        || quantity < expectedQuantity
                        || Math.abs(trigger - strategy.stopLossPrice) > 0.051d) {
                    continue;
                }
                String id = order.optString("groww_order_id", "");
                String reference = order.optString("order_reference_id", "");
                if (!id.isEmpty()) {
                    return ApiResult.success(id, reference,
                            "Recovered existing durable MIS SL-M protection " + id
                                    + " • status " + status + " • trigger ₹"
                                    + price(trigger) + ".", http.code);
                }
            }
            return ApiResult.failure("", "No matching durable MIS SL-M protection is visible.",
                    http.code);
        } catch (Exception e) {
            return ApiResult.failure("", "MIS stop recovery error: " + safeMessage(e), 0);
        }
    }

'''
text = read(client)
marker = "    static ApiResult createStopLossGtt(String accessToken, Strategy strategy,\n"
if text.count(marker) != 1:
    raise RuntimeError("Could not locate createStopLossGtt insertion point")
write(client, text.replace(marker, recovery_method + marker, 1))

# Keep the existing helper name for compatibility, but only durable statuses are live.
durable_helper = r'''    private static boolean isLiveRegularStopStatus(String status) {
        return MisStopOrderPolicy.isDurable(status);
    }
'''
replace_java_method(client, "    private static boolean isLiveRegularStopStatus(", durable_helper)

# A rejected leg must not reuse its old reference. The create method now generates
# a fresh 20-character reference and first recovers any durable order already present.
monitor = JAVA / "StrategyMonitorService.java"
text = read(monitor)
text = text.replace(
        "CRITICAL: broker protection leg became "
        , "CRITICAL: broker protection leg became ")
text = text.replace(
        'strategy.lastMessage = "CRITICAL: broker protection leg became "\n'
        '                        + status + "; automatic re-protection is required.";',
        'strategy.lastMessage = "CRITICAL: broker protection leg became "\n'
        '                        + status + "; automatic re-protection with a fresh reference is required.";')
write(monitor, text)

# Visible release wording; all trade-type budget labels remain unchanged.
activity = JAVA / "ProductionActivity.java"
text = read(activity).replace("2.2.4", "2.2.5")
text = text.replace("stable release 2.2.5", "stable release 2.2.5")
write(activity, text)

write(TEST / "MisStopOrderPolicyTest.java", r'''package com.suhas.multyfiautobuy.stable;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNotEquals;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

public class MisStopOrderPolicyTest {
    @Test public void onlyDurableStatusesCountAsProtection() {
        assertTrue(MisStopOrderPolicy.isDurable("TRIGGER_PENDING"));
        assertTrue(MisStopOrderPolicy.isDurable("OPEN"));
        assertTrue(MisStopOrderPolicy.isDurable("APPROVED"));
        assertFalse(MisStopOrderPolicy.isDurable("NEW"));
        assertFalse(MisStopOrderPolicy.isDurable("ACKED"));
        assertFalse(MisStopOrderPolicy.isDurable("REJECTED"));
    }

    @Test public void rejectedAttemptGetsFreshValidReference() {
        String first = MisStopOrderPolicy.freshReference("event-123456789", 1_000L);
        String second = MisStopOrderPolicy.freshReference("event-123456789", 2_000L);
        assertNotEquals(first, second);
        assertEquals(20, first.length());
        assertTrue(first.matches("[A-Z0-9]{20}"));
    }

    @Test public void newAndAckedRemainTransient() {
        assertTrue(MisStopOrderPolicy.isTransient("NEW"));
        assertTrue(MisStopOrderPolicy.isTransient("ACKED"));
        assertFalse(MisStopOrderPolicy.isTransient("TRIGGER_PENDING"));
    }
}
''')

# Build-time contract for the live KARURVYSYA failure.
client_text = read(client)
assert "versionName '2.2.5'" in read(gradle)
assert 'body.put("order_type", "SL_M")' in client_text
assert 'body.put("trigger_price", price(strategy.stopLossPrice))' in client_text
assert 'body.put("price", 0)' not in client_text
assert "MisStopOrderPolicy.isDurable" in client_text
assert "findDurableMisStop" in client_text
assert "NEW/ACKED is not counted as protection" in client_text
assert "freshReference" in client_text
assert "TradeTypeBudgetPolicy.budget" in read(JAVA / "ProductionNotificationService.java")
assert "createMisStopLossOrder" in client_text
assert "createStopLossGtt" in client_text
print("Applied v2.2.5 durable MIS stop-loss confirmation fix")
