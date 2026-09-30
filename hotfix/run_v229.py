#!/usr/bin/env python3
from pathlib import Path
import runpy

# Build only on the validated v2.2.8 durable early-exit release chain.
runpy.run_path("hotfix/run_v228_safe.py", run_name="__main__")

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
replace_once(gradle, "versionCode 228", "versionCode 229")
replace_once(gradle, "versionName '2.2.8'", "versionName '2.2.9'")


# A regular CASH MIS SL-M request was broker-acknowledged and then rejected with
# Groww error 16448 even though the optional price field was omitted. Use a
# regular DAY stop-limit SELL instead: trigger at the Multyfi stop and place the
# limit exactly one retained ₹0.10 grid tick below it. This is a valid SELL SL
# relationship and avoids an implicit/default zero limit.
write(JAVA / "MisStopLimitPolicy.java", r'''package com.suhas.multyfiautobuy.stable;

import java.util.Locale;

final class MisStopLimitPolicy {
    static final double GRID = 0.10d;

    private MisStopLimitPolicy() { }

    static double limitPrice(double triggerPrice) {
        if (triggerPrice <= GRID) return GRID;
        double triggerOnGrid = Math.floor((triggerPrice + 1e-9d) / GRID) * GRID;
        double limit = Math.max(GRID, triggerOnGrid - GRID);
        return Math.round(limit / GRID) * GRID;
    }

    static boolean isPriceTriggerRejection(String errorCode, String message) {
        String code = errorCode == null ? "" : errorCode.trim();
        String lower = message == null ? "" : message.toLowerCase(Locale.US);
        return "16448".equals(code)
                || lower.contains("difference between limit price and trigger price")
                || lower.contains("limit price and trigger price is beyond");
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
            // Recover any already-live matching regular MIS protection first.
            ApiResult existing = findDurableMisStop(accessToken, strategy, quantity);
            if (existing.success) return existing;

            String reference = MisStopOrderPolicy.freshReference(
                    strategy.eventId, System.currentTimeMillis());
            double limitPrice = MisStopLimitPolicy.limitPrice(strategy.stopLossPrice);

            JSONObject body = new JSONObject();
            body.put("trading_symbol", strategy.symbol);
            body.put("quantity", quantity);
            body.put("price", price(limitPrice));
            body.put("trigger_price", price(strategy.stopLossPrice));
            body.put("validity", "DAY");
            body.put("exchange", "NSE");
            body.put("segment", "CASH");
            body.put("product", "MIS");
            body.put("order_type", "SL");
            body.put("transaction_type", "SELL");
            body.put("order_reference_id", reference);

            HttpResult http = request("POST", API_BASE + "/order/create",
                    accessToken, body);
            if (!http.isSuccess()) {
                ApiResult failure = apiFailure(http);
                OrderStatus recovered = getOrderByReference(accessToken, reference);
                if (recovered.success && MisStopOrderPolicy.isDurable(recovered.status)) {
                    return ApiResult.success(recovered.orderId, reference,
                            "Recovered durable MIS DAY SL order " + recovered.orderId
                                    + " • status " + recovered.status + ".",
                            recovered.httpCode);
                }
                if (recovered.success
                        && MisStopOrderPolicy.isTerminalFailure(recovered.status)) {
                    return ApiResult.failure("MIS_STOP_REJECTED",
                            "MIS DAY SL reference " + reference + " became "
                                    + recovered.status + ": " + recovered.message
                                    + ". No identical retry will be submitted.",
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
            String remark = payload == null ? "" : payload.optString("remark", "");
            if (id.isEmpty()) {
                return ApiResult.failure("MIS_STOP_NO_ID",
                        "Groww accepted the MIS stop-loss request but returned no order ID.",
                        http.code);
            }
            if (MisStopOrderPolicy.isTerminalFailure(status)) {
                return ApiResult.failure("MIS_STOP_REJECTED",
                        "Groww rejected the MIS DAY SL order: " + status + " "
                                + remark + ". No identical retry will be submitted.",
                        http.code);
            }
            if (MisStopOrderPolicy.isDurable(status)) {
                return ApiResult.success(id, returnedReference,
                        "MIS DAY SL stop confirmed " + status + " for " + quantity
                                + " shares • trigger ₹" + price(strategy.stopLossPrice)
                                + " • limit ₹" + price(limitPrice) + ": " + id + ".",
                        http.code);
            }

            // NEW/ACKED is submission acknowledgement, not confirmed protection.
            OrderStatus confirmed = OrderStatus.failure(0, "Not checked.");
            for (int i = 0; i < 24; i++) {
                confirmed = getOrderByReference(accessToken, returnedReference);
                if (confirmed.success
                        && MisStopOrderPolicy.isDurable(confirmed.status)) {
                    return ApiResult.success(
                            confirmed.orderId.isEmpty() ? id : confirmed.orderId,
                            returnedReference,
                            "MIS DAY SL stop confirmed " + confirmed.status + " for "
                                    + quantity + " shares • trigger ₹"
                                    + price(strategy.stopLossPrice) + " • limit ₹"
                                    + price(limitPrice) + ".",
                            confirmed.httpCode);
                }
                if (confirmed.success
                        && MisStopOrderPolicy.isTerminalFailure(confirmed.status)) {
                    return ApiResult.failure("MIS_STOP_REJECTED",
                            "MIS DAY SL order " + id + " became " + confirmed.status
                                    + ": " + confirmed.message
                                    + ". No identical retry will be submitted.",
                            confirmed.httpCode);
                }
                try { Thread.sleep(250L); }
                catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    break;
                }
            }

            existing = findDurableMisStop(accessToken, strategy, quantity);
            if (existing.success) return existing;
            return ApiResult.failure("MIS_STOP_NOT_DURABLE",
                    "MIS DAY SL order " + id + " remains "
                            + (confirmed.status.isEmpty() ? status : confirmed.status)
                            + "; NEW/ACKED is not counted as protection.",
                    http.code);
        } catch (Exception e) {
            return ApiResult.failure("", "MIS stop-loss order error: "
                    + safeMessage(e), 0);
        }
    }
'''
replace_java_method(client, "    static ApiResult createMisStopLossOrder(", mis_method)


recovery_method = r'''    private static ApiResult findDurableMisStop(String accessToken,
                                                     Strategy strategy,
                                                     int expectedQuantity) {
        try {
            HttpResult http = request("GET",
                    API_BASE + "/order/list?segment=CASH&page=0&page_size=100",
                    accessToken, null);
            if (!http.isSuccess()) {
                return ApiResult.failure("", http.message(), http.code);
            }
            JSONObject payload = new JSONObject(http.body).optJSONObject("payload");
            JSONArray orders = payload == null ? null : payload.optJSONArray("order_list");
            if (orders == null) {
                return ApiResult.failure("", "Order list had no entries.", http.code);
            }
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
                boolean supportedStop = "SL".equalsIgnoreCase(orderType)
                        || "SL_M".equalsIgnoreCase(orderType)
                        || "SL-M".equalsIgnoreCase(orderType);
                if (!strategy.symbol.equalsIgnoreCase(symbol)
                        || !"MIS".equalsIgnoreCase(product)
                        || !"SELL".equalsIgnoreCase(transaction)
                        || !supportedStop
                        || !MisStopOrderPolicy.isDurable(status)
                        || quantity < expectedQuantity
                        || Math.abs(trigger - strategy.stopLossPrice) > 0.101d) {
                    continue;
                }
                String id = order.optString("groww_order_id", "");
                String reference = order.optString("order_reference_id", "");
                if (!id.isEmpty()) {
                    return ApiResult.success(id, reference,
                            "Recovered existing durable MIS " + orderType
                                    + " protection " + id + " • status " + status
                                    + " • trigger ₹" + price(trigger) + ".",
                            http.code);
                }
            }
            return ApiResult.failure("",
                    "No matching durable MIS stop protection is visible.",
                    http.code);
        } catch (Exception e) {
            return ApiResult.failure("", "MIS stop recovery error: "
                    + safeMessage(e), 0);
        }
    }
'''
replace_java_method(client, "    private static ApiResult findDurableMisStop(", recovery_method)


# Fail closed after a broker rejection: do not submit the same invalid stop every
# 15-20 seconds. Persist an emergency exit request, retain the user's armed
# preference, block new entries, and let the existing durable early-exit path
# cancel any live order remainder and market-exit the broker-confirmed position.
monitor = JAVA / "StrategyMonitorService.java"
protect_method = r'''    private boolean protectNewFill(String token, Strategy strategy) {
        int delta = strategy.observedFilledQuantity - strategy.protectedQuantity;
        if (delta <= 0) return true;
        if (strategy.lastMessage != null
                && strategy.lastMessage.startsWith("CRITICAL: ")
                && System.currentTimeMillis() - strategy.updatedAt < 15_000L) {
            return false;
        }

        int legNumber = strategy.stopLegs.size() + 1;
        boolean regularMis =
                ProtectionOrderPolicy.usesRegularMisStop(strategy.productType);
        GrowwClient.ApiResult stop = regularMis
                ? GrowwClient.createMisStopLossOrder(
                        token, strategy, delta, legNumber)
                : GrowwClient.createStopLossGtt(
                        token, strategy, delta, legNumber);

        if (!stop.success) {
            if (regularMis) {
                String reason = "Safety: MIS stop protection failed. " + stop.message;
                boolean newlyQueued = !strategy.earlyExitRequested;
                strategy.requestEarlyExit(reason, System.currentTimeMillis());
                strategy.lastMessage = "CRITICAL: " + delta
                        + " newly filled MIS shares could not obtain broker-confirmed "
                        + "DAY SL protection. Emergency market exit is queued; "
                        + "no identical stop retry will be submitted. " + stop.message;
                save(strategy);
                if (newlyQueued) {
                    AppPrefs.log(this,
                            "MIS STOP REJECTED — EMERGENCY EXIT QUEUED",
                            strategy.symbol + " • " + strategy.lastMessage
                                    + " New entries are paused and the 24×7 armed "
                                    + "preference remains ON.");
                }
                requestImmediateTick(this, strategy.eventId);
                return false;
            }

            String failure = "CRITICAL: " + delta
                    + " newly filled shares are awaiting confirmed protection. "
                    + stop.message;
            boolean changed = !failure.equals(strategy.lastMessage);
            strategy.lastMessage = failure;
            save(strategy);
            if (changed) {
                AppPrefs.log(this,
                        "STOP-LOSS RETRY PENDING — ARMED RETAINED",
                        strategy.symbol + " • " + strategy.lastMessage
                                + " New entries are paused, but the 24×7 armed "
                                + "preference remains ON.");
            }
            return false;
        }

        String mode = regularMis
                ? ProtectionOrderPolicy.REGULAR_MIS_SL_M
                : ProtectionOrderPolicy.CNC_GTT;
        strategy.stopLegs.add(new Strategy.StopLeg(
                stop.id, delta, "ACTIVE", mode, stop.secondaryId));
        strategy.protectedQuantity += delta;
        strategy.state = Strategy.PROTECTED;
        strategy.lastMessage = (regularMis
                ? "MIS regular DAY SL stop confirmed for "
                : "CNC stop-loss GTT confirmed for ")
                + strategy.protectedQuantity + " filled shares.";
        save(strategy);
        AppPrefs.log(this, regularMis
                        ? "MIS STOP-LIMIT ORDER CONFIRMED"
                        : "CNC STOP-LOSS GTT CONFIRMED ACTIVE",
                strategy.symbol + " • " + stop.message);
        return true;
    }
'''
replace_java_method(monitor, "    private boolean protectNewFill(", protect_method)


# Visible version wording.
activity = JAVA / "ProductionActivity.java"
write(activity, read(activity).replace("2.2.8", "2.2.9"))


write(TEST / "MisStopLimitPolicyTest.java", r'''package com.suhas.multyfiautobuy.stable;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

public class MisStopLimitPolicyTest {
    @Test public void bluestoneTriggerUsesOneTickLowerSellLimit() {
        assertEquals(778.90d, MisStopLimitPolicy.limitPrice(779.00d), 0.0001d);
    }

    @Test public void limitNeverExceedsTriggerAndUsesTenPaiseGrid() {
        double trigger = 304.00d;
        double limit = MisStopLimitPolicy.limitPrice(trigger);
        assertTrue(limit <= trigger);
        assertTrue(trigger - limit <= 0.1001d);
        assertEquals(0.0d, Math.IEEEremainder(limit, 0.10d), 0.0001d);
    }

    @Test public void groww16448IsRecognised() {
        assertTrue(MisStopLimitPolicy.isPriceTriggerRejection(
                "16448",
                "Difference between limit price and trigger price is beyond permissible range"));
        assertFalse(MisStopLimitPolicy.isPriceTriggerRejection(
                "GA007", "Duplicate order reference"));
    }
}
''')


# Build-time contracts lock the live BLUESTONE failure out of future releases.
client_text = read(client)
monitor_text = read(monitor)
assert "versionName '2.2.9'" in read(gradle)
assert 'body.put("order_type", "SL")' in client_text
assert 'body.put("price", price(limitPrice))' in client_text
assert 'body.put("trigger_price", price(strategy.stopLossPrice))' in client_text
assert '"SL_M".equalsIgnoreCase(orderType)' in client_text
assert "MisStopLimitPolicy.limitPrice" in client_text
assert "MIS STOP REJECTED — EMERGENCY EXIT QUEUED" in monitor_text
assert "requestEarlyExit(reason" in monitor_text
assert "no identical stop retry will be submitted" in monitor_text.lower()
assert "MULTYFI EARLY EXIT PERSISTED" in read(
        JAVA / "ProductionNotificationService.java")
print("Applied v2.2.9 MIS stop-limit and emergency-exit safety fix")
