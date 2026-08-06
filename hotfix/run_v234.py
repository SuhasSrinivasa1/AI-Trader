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


# Release identity.
gradle = ROOT / "app/build.gradle"
replace_once(gradle, "versionCode 233", "versionCode 234")
replace_once(gradle, "versionName '2.3.3'", "versionName '2.3.4'")


# The one-request path is deliberately strict. It is available only when the
# persisted broker-confirmed state proves that one regular MIS stop protects the
# complete requested/fill quantity. All other states use the v2.3.3 verified
# cancellation fallback.
write(JAVA / "FastEarlyExitPolicy.java", r'''package com.suhas.multyfiautobuy.stable;

final class FastEarlyExitPolicy {
    private FastEarlyExitPolicy() { }

    static boolean canConvertTrackedSingleStop(int activeRegularStopCount,
                                               int stopQuantity,
                                               int requestedQuantity,
                                               int observedFilledQuantity,
                                               int protectedQuantity) {
        return activeRegularStopCount == 1
                && requestedQuantity > 0
                && observedFilledQuantity == requestedQuantity
                && protectedQuantity == requestedQuantity
                && stopQuantity == requestedQuantity;
    }

    static boolean modificationAccepted(String status) {
        return status == null || status.isEmpty()
                || "NEW".equalsIgnoreCase(status)
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
            // Groww's official MARKET modify example requires only quantity,
            // order_type, segment and groww_order_id. Do not carry the old SL
            // price or trigger into the MARKET conversion request.
            JSONObject body = new JSONObject();
            body.put("quantity", quantity);
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
            if (!FastEarlyExitPolicy.modificationAccepted(status)) {
                return ApiResult.failure("FAST_EXIT_MODIFY_REJECTED",
                        "Groww did not accept the protective-order conversion. Status: "
                                + status + ".", http.code);
            }
            return ApiResult.success(id,
                    orderReferenceId == null ? "" : orderReferenceId,
                    "Existing full-quantity MIS stop converted directly to MARKET SELL "
                            + "in one broker request • order " + id + " • status "
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
helper_anchor = "\n    private void processEarlyExit(String token, Strategy strategy, int remaining,"
if helper_anchor not in read(monitor):
    raise RuntimeError("Could not locate early-exit helper insertion point")
fast_helper = r'''
    private boolean tryImmediateTrackedEarlyExit(String token,
                                                 Strategy strategy,
                                                 boolean staticIpReady) {
        if (!isMarketSession() || !staticIpReady || !strategy.isIntraday()) {
            return false;
        }

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
                || !FastEarlyExitPolicy.canConvertTrackedSingleStop(
                        activeRegularStops,
                        candidate.quantity,
                        strategy.requestedQuantity,
                        strategy.observedFilledQuantity,
                        strategy.protectedQuantity)) {
            return false;
        }

        String orderId = candidate.smartOrderId == null
                ? "" : candidate.smartOrderId.trim();
        if (orderId.isEmpty()) return false;

        // No pre-status, cancel, position, quote or second order-create request
        // is made here. The known full-quantity stop itself becomes the MARKET
        // exit. A rejected/ambiguous response falls through to the v2.3.3
        // broker-reconciliation path in the same monitor tick.
        GrowwClient.ApiResult modified =
                GrowwClient.convertOpenMisStopToMarketSell(
                        token, orderId, candidate.referenceId,
                        strategy.requestedQuantity);
        if (!modified.success) {
            AppPrefs.log(this, "MULTYFI FAST EXIT FALLBACK",
                    strategy.symbol + " • direct one-request stop-to-market conversion "
                            + "was not broker-accepted; running verified fallback now. "
                            + modified.message);
            return false;
        }

        candidate.status = "MODIFICATION_REQUESTED";
        strategy.targetOrderId = modified.id;
        strategy.targetOrderReferenceId = modified.secondaryId;
        strategy.targetFilledQuantity = 0;
        strategy.pendingExitLabel = "Multyfi early exit";
        // Retain authoritative intent until Groww confirms the position is zero.
        strategy.earlyExitRequested = true;
        strategy.state = Strategy.TARGET_SELL_PENDING;
        strategy.lastMessage = "Multyfi early exit fast path submitted immediately: "
                + "the existing complete MIS stop became the MARKET sell.";
        save(strategy);
        AppPrefs.log(this, "MULTYFI EARLY EXIT FAST SUBMITTED",
                strategy.symbol + " • full quantity " + strategy.requestedQuantity
                        + " • " + modified.message);
        requestImmediateTick(this, strategy.eventId);
        return true;
    }
'''
replace_once(monitor, helper_anchor, "\n" + fast_helper.rstrip() + helper_anchor)


# The authoritative notification already has an immediate foreground-service
# tick. Attempt the one-request broker conversion before any position lookup,
# entry-status lookup, cancellation polling or quote request.
old_early_branch = r'''        if (strategy.earlyExitRequested) {
            processEarlyExit(token, strategy, -1, staticIpReady);
            return;
        }
'''
new_early_branch = r'''        if (strategy.earlyExitRequested) {
            if (tryImmediateTrackedEarlyExit(token, strategy, staticIpReady)) {
                return;
            }
            processEarlyExit(token, strategy, -1, staticIpReady);
            return;
        }
'''
replace_once(monitor, old_early_branch, new_early_branch)


# The fast path modifies the existing protective order, so reconcile by Groww
# order ID first. The original reference remains only as a fallback.
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


activity = JAVA / "ProductionActivity.java"
write(activity, read(activity).replace("2.3.3", "2.3.4"))


write(TEST / "FastEarlyExitPolicyTest.java", r'''package com.suhas.multyfiautobuy.stable;

import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

public class FastEarlyExitPolicyTest {
    @Test public void gspcropCompleteProtectedTradeUsesImmediateOneRequestPath() {
        assertTrue(FastEarlyExitPolicy.canConvertTrackedSingleStop(
                1, 520, 520, 520, 520));
    }

    @Test public void partialMultipleOrUnprotectedTradeUsesVerifiedFallback() {
        assertFalse(FastEarlyExitPolicy.canConvertTrackedSingleStop(
                1, 500, 520, 520, 500));
        assertFalse(FastEarlyExitPolicy.canConvertTrackedSingleStop(
                2, 520, 520, 520, 520));
        assertFalse(FastEarlyExitPolicy.canConvertTrackedSingleStop(
                1, 520, 520, 500, 500));
    }

    @Test public void modificationRequestedAndExecutedAreAccepted() {
        assertTrue(FastEarlyExitPolicy.modificationAccepted(
                "MODIFICATION_REQUESTED"));
        assertTrue(FastEarlyExitPolicy.modificationAccepted("EXECUTED"));
        assertFalse(FastEarlyExitPolicy.modificationAccepted("REJECTED"));
    }
}
''')


assert "versionCode 234" in read(gradle)
assert "versionName '2.3.4'" in read(gradle)
assert "convertOpenMisStopToMarketSell" in read(client)
assert 'API_BASE + "/order/modify"' in read(client)
assert 'body.put("order_type", "MARKET")' in read(client)
assert 'body.put("groww_order_id"' in read(client)
assert 'body.put("price"' not in modify_method
assert 'body.put("trigger_price"' not in modify_method
assert "MULTYFI EARLY EXIT FAST SUBMITTED" in read(monitor)
assert "MULTYFI FAST EXIT FALLBACK" in read(monitor)
assert "tryImmediateTrackedEarlyExit(token, strategy, staticIpReady)" in read(monitor)
assert "GrowwClient.getOrderById(token, strategy.targetOrderId)" in read(monitor)
assert "MULTYFI EARLY EXIT WAITING — STOP CANCEL NOT CONFIRMED" in read(monitor)
assert "queueEarlyExit(earlyExit)" in read(
        JAVA / "ProductionNotificationService.java")
assert "acceptsUnlabelledNewEquityTradeAsMis" in read(
        TEST / "IntradayOnlyPolicyTest.java")
print("Applied Multyfi AutoBuy Pro v2.3.4 immediate one-request early-exit update")
