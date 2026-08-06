#!/usr/bin/env python3
from pathlib import Path
import runpy

# Preserve the validated v2.3.3 blocklist intake, MIS stop protection and
# authoritative early-exit reconciliation chain.
runpy.run_path("hotfix/run_v233.py", run_name="__main__")

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
replace_once(gradle, "versionCode 233", "versionCode 234")
replace_once(gradle, "versionName '2.3.3'", "versionName '2.3.4'")


# Fast path policy is intentionally strict. It is safe to convert the existing
# protective order into the exit only when one regular MIS stop exactly covers
# the live remaining position. This avoids a separate cancel + create sequence
# without risking an account-wide exit or an accidental short position.
write(JAVA / "FastEarlyExitPolicy.java", r'''package com.suhas.multyfiautobuy.stable;

final class FastEarlyExitPolicy {
    private FastEarlyExitPolicy() { }

    static boolean canConvertSingleStop(int activeRegularStopCount,
                                        int stopQuantity,
                                        int remainingPosition) {
        return activeRegularStopCount == 1
                && remainingPosition > 0
                && stopQuantity == remainingPosition;
    }

    static boolean modificationAccepted(String status) {
        return "NEW".equalsIgnoreCase(status)
                || "ACKED".equalsIgnoreCase(status)
                || "APPROVED".equalsIgnoreCase(status)
                || "OPEN".equalsIgnoreCase(status)
                || "PENDING".equalsIgnoreCase(status)
                || "MODIFICATION_REQUESTED".equalsIgnoreCase(status)
                || "EXECUTED".equalsIgnoreCase(status)
                || "COMPLETED".equalsIgnoreCase(status)
                || "COMPLETE".equalsIgnoreCase(status)
                || "DELIVERY_AWAITED".equalsIgnoreCase(status);
    }
}
''')


client = JAVA / "GrowwClient.java"
insert_anchor = "\n    static ApiResult placeTargetMarketSell(String accessToken, Strategy strategy,"
if insert_anchor not in read(client):
    raise RuntimeError("Could not locate market-sell insertion point")
modify_method = r'''
    static ApiResult convertOpenMisStopToMarketSell(String accessToken,
                                                     String growwOrderId,
                                                     String orderReferenceId,
                                                     int quantity) {
        if (growwOrderId == null || growwOrderId.trim().isEmpty()) {
            return ApiResult.failure("FAST_EXIT_NO_ORDER_ID",
                    "The protective Groww order ID is unavailable.", 0);
        }
        if (quantity <= 0) {
            return ApiResult.failure("FAST_EXIT_BAD_QUANTITY",
                    "The fast-exit quantity must be positive.", 0);
        }
        try {
            JSONObject body = new JSONObject();
            body.put("quantity", quantity);
            body.put("price", 0);
            body.put("trigger_price", 0);
            body.put("order_type", "MARKET");
            body.put("segment", "CASH");
            body.put("groww_order_id", growwOrderId.trim());

            HttpResult http = request("POST", API_BASE + "/order/modify",
                    accessToken, body);
            if (!http.isSuccess()) return apiFailure(http);

            JSONObject payload = new JSONObject(http.body).optJSONObject("payload");
            String id = payload == null ? growwOrderId.trim()
                    : payload.optString("groww_order_id", growwOrderId.trim());
            String status = payload == null ? ""
                    : payload.optString("order_status", "");
            if (!status.isEmpty() && !FastEarlyExitPolicy.modificationAccepted(status)) {
                return ApiResult.failure("FAST_EXIT_MODIFY_REJECTED",
                        "Groww did not accept the protective-order conversion. Status: "
                                + status + ".", http.code);
            }
            return ApiResult.success(id,
                    orderReferenceId == null ? "" : orderReferenceId,
                    "Existing MIS stop converted to full-quantity MARKET SELL in one "
                            + "broker request • order " + id + " • status "
                            + (status.isEmpty() ? "submitted" : status) + ".",
                    http.code);
        } catch (Exception e) {
            return ApiResult.failure("FAST_EXIT_ERROR",
                    "Fast early-exit modification error: " + safeMessage(e), 0);
        }
    }
'''
replace_once(client, insert_anchor, "\n" + modify_method.rstrip() + insert_anchor)


monitor = JAVA / "StrategyMonitorService.java"

# Insert the fast conversion helper before executeExit.
helper_anchor = "\n    private void executeExit(String token, Strategy strategy,"
if helper_anchor not in read(monitor):
    raise RuntimeError("Could not locate executeExit insertion point")
fast_helper = r'''
    private boolean tryFastAuthoritativeEarlyExit(String token,
                                                   Strategy strategy,
                                                   int remaining) {
        if (!strategy.isIntraday() || remaining <= 0) return false;

        Strategy.StopLeg candidate = null;
        int activeRegularStops = 0;
        for (Strategy.StopLeg leg : strategy.stopLegs) {
            if (!leg.isRegularMisStop()) continue;
            if (EarlyExitProtectionPolicy.isCancelled(leg.status)
                    || EarlyExitProtectionPolicy.isTriggeredOrExecuted(leg.status)) {
                continue;
            }
            activeRegularStops++;
            candidate = leg;
        }
        if (candidate == null
                || !FastEarlyExitPolicy.canConvertSingleStop(
                        activeRegularStops, candidate.quantity, remaining)) {
            return false;
        }

        String orderId = candidate.smartOrderId == null
                ? "" : candidate.smartOrderId.trim();
        GrowwClient.OrderStatus status = !orderId.isEmpty()
                ? GrowwClient.getOrderById(token, orderId)
                : GrowwClient.OrderStatus.failure(0, "Order ID unavailable.");
        if (!status.success && candidate.referenceId != null
                && !candidate.referenceId.isEmpty()) {
            status = GrowwClient.getOrderByReference(token, candidate.referenceId);
        }
        if (!status.success) return false;
        if (EarlyExitProtectionPolicy.isTriggeredOrExecuted(status.status)) {
            candidate.status = status.status;
            strategy.lastMessage = "Multyfi early exit arrived while the protective "
                    + "order was already " + status.status
                    + "; waiting for the position to settle to avoid a duplicate sell.";
            save(strategy);
            return true;
        }
        if (!EarlyExitProtectionPolicy.isOpen(status.status)
                || EarlyExitProtectionPolicy.isCancellationPending(status.status)) {
            return false;
        }
        if (orderId.isEmpty()) orderId = status.orderId;
        if (orderId == null || orderId.isEmpty()) return false;

        GrowwClient.ApiResult modified =
                GrowwClient.convertOpenMisStopToMarketSell(
                        token, orderId, candidate.referenceId, remaining);
        if (!modified.success) {
            AppPrefs.log(this, "MULTYFI FAST EXIT FALLBACK",
                    strategy.symbol + " • one-request stop-to-market conversion failed; "
                            + "using verified cancel-and-market fallback. "
                            + modified.message);
            return false;
        }

        candidate.status = "MODIFICATION_REQUESTED";
        strategy.targetOrderId = modified.id;
        strategy.targetOrderReferenceId = modified.secondaryId;
        strategy.pendingExitLabel = "Multyfi early exit";
        strategy.earlyExitRequested = false;
        strategy.state = Strategy.TARGET_SELL_PENDING;
        strategy.lastMessage = "Multyfi early exit fast path: the existing full-quantity "
                + "MIS stop was converted directly into a MARKET sell.";
        save(strategy);
        AppPrefs.log(this, "MULTYFI EARLY EXIT FAST SUBMITTED",
                strategy.symbol + " • " + modified.message);
        return true;
    }
'''
replace_once(monitor, helper_anchor, "\n" + fast_helper.rstrip() + helper_anchor)


# Use the one-request conversion before the slower cancel-and-create path. The
# matching position quantity has already been fetched by processEarlyExit.
old_execute_start = r'''        boolean authoritativeEarly = EXIT_MULTYFI_EARLY.equals(exitType);
        for (Strategy.StopLeg leg : strategy.stopLegs) {
'''
new_execute_start = r'''        boolean authoritativeEarly = EXIT_MULTYFI_EARLY.equals(exitType);
        if (authoritativeEarly
                && tryFastAuthoritativeEarlyExit(token, strategy,
                        strategy.remainingStrategyQuantity(
                                GrowwClient.getNetPositionQuantity(
                                        token, strategy.symbol,
                                        strategy.productType).value))) {
            return;
        }
        for (Strategy.StopLeg leg : strategy.stopLegs) {
'''
replace_once(monitor, old_execute_start, new_execute_start)


# Avoid trusting a failed position read in the inline fast path. Replace the
# inline expression with a small guarded lookup inside executeExit.
unsafe = r'''        boolean authoritativeEarly = EXIT_MULTYFI_EARLY.equals(exitType);
        if (authoritativeEarly
                && tryFastAuthoritativeEarlyExit(token, strategy,
                        strategy.remainingStrategyQuantity(
                                GrowwClient.getNetPositionQuantity(
                                        token, strategy.symbol,
                                        strategy.productType).value))) {
            return;
        }
'''
safe = r'''        boolean authoritativeEarly = EXIT_MULTYFI_EARLY.equals(exitType);
        if (authoritativeEarly) {
            GrowwClient.IntResult fastPosition = GrowwClient.getNetPositionQuantity(
                    token, strategy.symbol, strategy.productType);
            if (fastPosition.success) {
                int fastRemaining = strategy.remainingStrategyQuantity(
                        fastPosition.value);
                if (tryFastAuthoritativeEarlyExit(
                        token, strategy, fastRemaining)) return;
            }
        }
'''
replace_once(monitor, unsafe, safe)


# Pending status should use order-id first because the fast path modifies the
# existing stop order and keeps its original reference ID.
old_pending = r'''        GrowwClient.OrderStatus status = GrowwClient.getOrderByReference(
                token, strategy.targetOrderReferenceId);
        if (!status.success) {
            strategy.lastMessage = "Exit sell status unavailable; waiting to avoid duplicate selling.";
            save(strategy);
            return;
        }
'''
new_pending = r'''        GrowwClient.OrderStatus status = strategy.targetOrderId == null
                || strategy.targetOrderId.isEmpty()
                ? GrowwClient.OrderStatus.failure(0, "Exit order ID unavailable.")
                : GrowwClient.getOrderById(token, strategy.targetOrderId);
        if (!status.success && strategy.targetOrderReferenceId != null
                && !strategy.targetOrderReferenceId.isEmpty()) {
            status = GrowwClient.getOrderByReference(
                    token, strategy.targetOrderReferenceId);
        }
        if (!status.success) {
            strategy.lastMessage = "Exit sell status unavailable; waiting to avoid duplicate selling.";
            save(strategy);
            return;
        }
'''
replace_once(monitor, old_pending, new_pending)


# Visible version text only.
activity = JAVA / "ProductionActivity.java"
write(activity, read(activity).replace("2.3.3", "2.3.4"))


write(TEST / "FastEarlyExitPolicyTest.java", r'''package com.suhas.multyfiautobuy.stable;

import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

public class FastEarlyExitPolicyTest {
    @Test public void gspcropSingleFullStopUsesOneRequestFastPath() {
        assertTrue(FastEarlyExitPolicy.canConvertSingleStop(1, 520, 520));
    }

    @Test public void partialOrMultipleStopsUseSafeFallback() {
        assertFalse(FastEarlyExitPolicy.canConvertSingleStop(1, 500, 520));
        assertFalse(FastEarlyExitPolicy.canConvertSingleStop(2, 520, 520));
    }

    @Test public void modificationRequestedAndExecutedAreAccepted() {
        assertTrue(FastEarlyExitPolicy.modificationAccepted(
                "MODIFICATION_REQUESTED"));
        assertTrue(FastEarlyExitPolicy.modificationAccepted("EXECUTED"));
        assertFalse(FastEarlyExitPolicy.modificationAccepted("REJECTED"));
    }
}
''')


# Build-time contracts.
assert "versionCode 234" in read(gradle)
assert "versionName '2.3.4'" in read(gradle)
assert "convertOpenMisStopToMarketSell" in read(client)
assert 'API_BASE + "/order/modify"' in read(client)
assert 'body.put("order_type", "MARKET")' in read(client)
assert 'body.put("groww_order_id"' in read(client)
assert "MULTYFI EARLY EXIT FAST SUBMITTED" in read(monitor)
assert "MULTYFI FAST EXIT FALLBACK" in read(monitor)
assert "tryFastAuthoritativeEarlyExit" in read(monitor)
assert "GrowwClient.getOrderById(token, strategy.targetOrderId)" in read(monitor)
assert "MULTYFI EARLY EXIT WAITING — STOP CANCEL NOT CONFIRMED" in read(monitor)
assert "queueEarlyExit(earlyExit)" in read(
        JAVA / "ProductionNotificationService.java")
assert "acceptsUnlabelledNewEquityTradeAsMis" in read(
        TEST / "IntradayOnlyPolicyTest.java")
print("Applied Multyfi AutoBuy Pro v2.3.4 one-request fast early-exit update")
