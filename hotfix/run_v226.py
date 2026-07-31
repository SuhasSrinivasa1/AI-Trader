#!/usr/bin/env python3
from pathlib import Path
import re
import runpy

# Build only on the fully validated v2.2.5 durable-MIS-stop release chain.
runpy.run_path("hotfix/run_v225_safe.py", run_name="__main__")

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
        raise RuntimeError(f"Expected one match in {path}, found {count}: {old[:220]}")
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
replace_once(gradle, "versionCode 225", "versionCode 226")
replace_once(gradle, "versionName '2.2.5'", "versionName '2.2.6'")


# NEW/ACKED is merely broker acknowledgement. This policy also recognises the
# live LASERPOWER RMS assigned-basket rejection and creates a distinct, valid
# reference for the one permitted full-cash CNC fallback attempt.
write(JAVA / "EntryOrderPolicy.java", r'''package com.suhas.multyfiautobuy.stable;

import java.util.Locale;

final class EntryOrderPolicy {
    static final String DURABLE = "DURABLE";
    static final String REJECTED = "REJECTED";
    static final String PENDING = "PENDING";
    static final String ERROR = "ERROR";

    private EntryOrderPolicy() { }

    static boolean isDurable(String status, int filledQuantity) {
        if (filledQuantity > 0) return true;
        return "OPEN".equalsIgnoreCase(status)
                || "APPROVED".equalsIgnoreCase(status)
                || "PARTIALLY_FILLED".equalsIgnoreCase(status)
                || "PARTIAL".equalsIgnoreCase(status)
                || "EXECUTED".equalsIgnoreCase(status)
                || "FILLED".equalsIgnoreCase(status)
                || "COMPLETE".equalsIgnoreCase(status)
                || "COMPLETED".equalsIgnoreCase(status)
                || "TRADED".equalsIgnoreCase(status);
    }

    static boolean isTransient(String status) {
        return status == null || status.trim().isEmpty()
                || "NEW".equalsIgnoreCase(status)
                || "ACKED".equalsIgnoreCase(status)
                || "PENDING".equalsIgnoreCase(status)
                || "VALIDATION_PENDING".equalsIgnoreCase(status)
                || "MODIFICATION_REQUESTED".equalsIgnoreCase(status);
    }

    static boolean isTerminalFailure(String status) {
        return "REJECTED".equalsIgnoreCase(status)
                || "FAILED".equalsIgnoreCase(status)
                || "CANCELLED".equalsIgnoreCase(status)
                || "CANCELED".equalsIgnoreCase(status);
    }

    static boolean isMisBasketRestriction(String message) {
        String lower = message == null ? "" : message.toLowerCase(Locale.US);
        return lower.contains("assigned basket")
                || lower.contains("intraday not allowed")
                || lower.contains("mis not allowed")
                || (lower.contains("rms:rule") && lower.contains("across product"));
    }

    static String cncFallbackReference(String originalReference) {
        String clean = originalReference == null ? ""
                : originalReference.replaceAll("[^A-Za-z0-9]", "")
                        .toUpperCase(Locale.US);
        String combined = "FC" + clean;
        if (combined.length() < 8) combined = combined + "00000000";
        return combined.substring(0, Math.min(20, combined.length()));
    }
}
''')


# Add a regular-entry result that preserves the final broker status and never
# converts NEW/ACKED into a false success. The official status-by-reference API
# is polled before returning a durable, rejected or still-pending result.
client = JAVA / "GrowwClient.java"
entry_method = r'''    static EntryResult placeConfirmedEntryLimit(String accessToken,
                                                SignalParser.ParsedSignal signal,
                                                int quantity,
                                                String productType,
                                                String referenceId) {
        if (signal == null || quantity <= 0) {
            return EntryResult.error("", "A valid signal and positive quantity are required.", 0);
        }
        try {
            JSONObject body = new JSONObject();
            body.put("trading_symbol", signal.symbol);
            body.put("quantity", quantity);
            body.put("price", price(signal.maxBuyPrice));
            body.put("trigger_price", 0);
            body.put("validity", "DAY");
            body.put("exchange", "NSE");
            body.put("segment", "CASH");
            body.put("product", productType);
            body.put("order_type", "LIMIT");
            body.put("transaction_type", "BUY");
            body.put("order_reference_id", referenceId);

            HttpResult http = request("POST", API_BASE + "/order/create",
                    accessToken, body);
            if (!http.isSuccess()) {
                ApiResult failure = apiFailure(http);
                String message = failure.message;
                if (EntryOrderPolicy.isMisBasketRestriction(message)) {
                    return EntryResult.rejected("", referenceId, "REJECTED", 0,
                            failure.errorCode, message, failure.httpCode);
                }
                return EntryResult.error(failure.errorCode, message, failure.httpCode);
            }

            JSONObject payload = new JSONObject(http.body).optJSONObject("payload");
            if (payload == null) {
                return EntryResult.error("ENTRY_NO_PAYLOAD",
                        "Groww returned no entry payload.", http.code);
            }
            String id = payload.optString("groww_order_id", "");
            String status = payload.optString("order_status", "");
            String reference = payload.optString("order_reference_id", referenceId);
            int filled = payload.optInt("filled_quantity", 0);
            String remark = payload.optString("remark", "");
            if (id.isEmpty()) {
                return EntryResult.error("ENTRY_NO_ORDER_ID",
                        "Groww returned no entry order ID.", http.code);
            }
            if (EntryOrderPolicy.isDurable(status, filled)) {
                return EntryResult.durable(id, reference, status, filled,
                        "Broker-confirmed " + productType + " LIMIT BUY " + id
                                + " • status " + status + " • cap ₹"
                                + price(signal.maxBuyPrice) + ".", http.code);
            }
            if (EntryOrderPolicy.isTerminalFailure(status)) {
                return EntryResult.rejected(id, reference, status, filled,
                        "ENTRY_REJECTED",
                        "Groww rejected the " + productType + " entry: "
                                + status + " " + remark, http.code);
            }

            OrderStatus confirmed = OrderStatus.failure(0, "Not checked.");
            for (int i = 0; i < 40; i++) {
                confirmed = getOrderByReference(accessToken, reference);
                if (confirmed.success
                        && EntryOrderPolicy.isDurable(
                                confirmed.status, confirmed.filledQuantity)) {
                    return EntryResult.durable(
                            confirmed.orderId.isEmpty() ? id : confirmed.orderId,
                            reference, confirmed.status, confirmed.filledQuantity,
                            "Broker-confirmed " + productType + " LIMIT BUY "
                                    + (confirmed.orderId.isEmpty() ? id : confirmed.orderId)
                                    + " • status " + confirmed.status + " • cap ₹"
                                    + price(signal.maxBuyPrice) + ".",
                            confirmed.httpCode);
                }
                if (confirmed.success
                        && EntryOrderPolicy.isTerminalFailure(confirmed.status)) {
                    return EntryResult.rejected(
                            confirmed.orderId.isEmpty() ? id : confirmed.orderId,
                            reference, confirmed.status, confirmed.filledQuantity,
                            "ENTRY_REJECTED",
                            "Groww rejected the " + productType + " entry: "
                                    + confirmed.status + " " + confirmed.message,
                            confirmed.httpCode);
                }
                try { Thread.sleep(250L); }
                catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    break;
                }
            }

            String pendingStatus = confirmed.success && !confirmed.status.isEmpty()
                    ? confirmed.status : status;
            String pendingMessage = confirmed.success && !confirmed.message.isEmpty()
                    ? confirmed.message : remark;
            return EntryResult.pending(id, reference, pendingStatus, filled,
                    "Groww entry is still "
                            + (pendingStatus.isEmpty() ? "PENDING" : pendingStatus)
                            + "; it is stored for background confirmation, not logged as accepted. "
                            + pendingMessage,
                    http.code);
        } catch (Exception e) {
            return EntryResult.error("", "Entry confirmation error: "
                    + safeMessage(e), 0);
        }
    }

'''
# Keep the old method for compatibility tests and image flows; production uses
# the confirmed method above.
text = read(client)
marker = "    static ApiResult placeImmediateEntryLimit(String accessToken,\n"
if marker not in text:
    raise RuntimeError("Could not locate placeImmediateEntryLimit marker")
text = text.replace(marker, entry_method + marker, 1)
write(client, text)

entry_result_class = r'''    static final class EntryResult {
        final String outcome;
        final String id;
        final String referenceId;
        final String status;
        final int filledQuantity;
        final String errorCode;
        final String message;
        final int httpCode;

        private EntryResult(String outcome, String id, String referenceId,
                            String status, int filledQuantity, String errorCode,
                            String message, int httpCode) {
            this.outcome = outcome;
            this.id = id == null ? "" : id;
            this.referenceId = referenceId == null ? "" : referenceId;
            this.status = status == null ? "" : status;
            this.filledQuantity = Math.max(0, filledQuantity);
            this.errorCode = errorCode == null ? "" : errorCode;
            this.message = message == null ? "" : message;
            this.httpCode = httpCode;
        }

        static EntryResult durable(String id, String reference, String status,
                                   int filled, String message, int code) {
            return new EntryResult(EntryOrderPolicy.DURABLE, id, reference,
                    status, filled, "", message, code);
        }

        static EntryResult rejected(String id, String reference, String status,
                                    int filled, String errorCode,
                                    String message, int code) {
            return new EntryResult(EntryOrderPolicy.REJECTED, id, reference,
                    status, filled, errorCode, message, code);
        }

        static EntryResult pending(String id, String reference, String status,
                                   int filled, String message, int code) {
            return new EntryResult(EntryOrderPolicy.PENDING, id, reference,
                    status, filled, "", message, code);
        }

        static EntryResult error(String errorCode, String message, int code) {
            return new EntryResult(EntryOrderPolicy.ERROR, "", "", "",
                    0, errorCode, message, code);
        }

        boolean isDurable() { return EntryOrderPolicy.DURABLE.equals(outcome); }
        boolean isRejected() { return EntryOrderPolicy.REJECTED.equals(outcome); }
        boolean isPending() { return EntryOrderPolicy.PENDING.equals(outcome); }
    }

'''
text = read(client)
marker = "    static final class ApiResult {\n"
if marker not in text:
    raise RuntimeError("Could not locate ApiResult class marker")
text = text.replace(marker, entry_result_class + marker, 1)
write(client, text)


# The notification service first tries MIS. Only the assigned-basket family of
# rejections receives one full-cash CNC LIMIT fallback. The same Intraday budget
# and cap are retained, and the strategy category remains INTRADAY so the normal
# same-day force-exit rule still applies.
service = JAVA / "ProductionNotificationService.java"
submit_method = r'''    private void submitImmediateMis(String token, SignalParser.ParsedSignal signal,
                                    AppPrefs.TradeWindow window, int quantity,
                                    int baselineQuantity, String summary) {
        AppPrefs.log(this, "SUBMITTING MULTYFI INTRADAY MIS ENTRY",
                summary + " • baseline MIS position " + baselineQuantity + ".");
        GrowwClient.EntryResult mis = GrowwClient.placeConfirmedEntryLimit(
                token, signal, quantity, "MIS", signal.referenceId);
        if (mis.isDurable()) {
            Strategy strategy = new Strategy(signal.eventId, signal.symbol,
                    signal.category, "MIS", quantity,
                    signal.targetPrice, signal.stopLossPrice, baselineQuantity,
                    mis.referenceId, "", mis.id, "REGULAR_LIMIT",
                    signal.notificationTimeMillis, window.entryCancelAt);
            strategy.observedFilledQuantity = Math.min(quantity, mis.filledQuantity);
            acceptStrategy(strategy, signal, summary, mis.message,
                    "MIS entry is broker-confirmed; protection follows actual fills.");
            return;
        }

        if (mis.isRejected() && EntryOrderPolicy.isMisBasketRestriction(mis.message)) {
            AppPrefs.log(this, "MIS BLOCKED BY GROWW — TRYING CNC SAME-DAY FALLBACK",
                    signal.symbol + " • " + mis.message
                            + " • retrying once as a full-cash CNC LIMIT using the same Intraday budget and cap.");
            GrowwClient.IntResult cncBaseline = GrowwClient.getNetPositionQuantity(
                    token, signal.symbol, "CNC");
            if (!cncBaseline.success) {
                AppPrefs.markProcessed(this, signal.eventId);
                AppPrefs.log(this, "CNC FALLBACK FAILED — BASELINE UNAVAILABLE",
                        summary + "\n" + cncBaseline.message);
                return;
            }
            String fallbackReference = EntryOrderPolicy.cncFallbackReference(
                    signal.referenceId);
            GrowwClient.EntryResult cnc = GrowwClient.placeConfirmedEntryLimit(
                    token, signal, quantity, "CNC", fallbackReference);
            if (cnc.isDurable()) {
                Strategy strategy = new Strategy(signal.eventId, signal.symbol,
                        signal.category, "CNC", quantity,
                        signal.targetPrice, signal.stopLossPrice, cncBaseline.value,
                        cnc.referenceId, "", cnc.id, "CNC_FALLBACK_LIMIT",
                        signal.notificationTimeMillis, window.entryCancelAt);
                strategy.observedFilledQuantity = Math.min(quantity, cnc.filledQuantity);
                acceptStrategy(strategy, signal,
                        summary + " • fallback product CNC",
                        cnc.message,
                        "Groww blocked MIS; CNC fallback is broker-confirmed, uses CNC GTT protection, and remains a same-day Intraday strategy.");
                return;
            }
            if (cnc.isPending()) {
                Strategy strategy = new Strategy(signal.eventId, signal.symbol,
                        signal.category, "CNC", quantity,
                        signal.targetPrice, signal.stopLossPrice, cncBaseline.value,
                        cnc.referenceId, "", cnc.id,
                        "PENDING_CNC_FALLBACK_LIMIT",
                        signal.notificationTimeMillis, window.entryCancelAt);
                queuePendingEntry(strategy, signal,
                        summary + " • fallback product CNC", cnc);
                return;
            }
            AppPrefs.markProcessed(this, signal.eventId);
            AppPrefs.log(this, "CNC FALLBACK REJECTED — NO POSITION",
                    summary + "\nMIS: " + mis.message + "\nCNC: " + cnc.message);
            return;
        }

        if (mis.isPending()) {
            Strategy strategy = new Strategy(signal.eventId, signal.symbol,
                    signal.category, "MIS", quantity,
                    signal.targetPrice, signal.stopLossPrice, baselineQuantity,
                    mis.referenceId, "", mis.id, "PENDING_MIS_LIMIT",
                    signal.notificationTimeMillis, window.entryCancelAt);
            queuePendingEntry(strategy, signal, summary, mis);
            return;
        }

        AppPrefs.markProcessed(this, signal.eventId);
        AppPrefs.log(this, "MIS ENTRY REJECTED — NO POSITION",
                summary + "\n" + mis.message);
    }
'''
replace_java_method(service, "    private void submitImmediateMis(", submit_method)

pending_method = r'''    private void queuePendingEntry(Strategy strategy,
                                   SignalParser.ParsedSignal signal,
                                   String summary,
                                   GrowwClient.EntryResult result) {
        StrategyStore.upsert(this, strategy);
        AppPrefs.markProcessed(this, signal.eventId);
        AppPrefs.log(this, "ENTRY SUBMITTED — BROKER CONFIRMATION PENDING",
                summary + "\n" + result.message
                        + " No successful-buy count or stop-loss is created until Groww confirms the order.");
        StrategyMonitorService.requestImmediateTick(this, signal.eventId);
    }

'''
text = read(service)
marker = "    private void acceptStrategy(Strategy strategy, SignalParser.ParsedSignal signal,\n"
if marker not in text:
    raise RuntimeError("Could not locate acceptStrategy marker")
text = text.replace(marker, pending_method + marker, 1)
write(service, text)


# A CNC fallback still represents an Intraday recommendation. This preserves the
# 15:10 same-day exit and prevents an unintended overnight position.
strategy = JAVA / "Strategy.java"
replace_once(strategy,
             '    boolean isIntraday() { return "MIS".equalsIgnoreCase(productType); }',
             '    boolean isIntraday() {\n        return "MIS".equalsIgnoreCase(productType)\n                || "INTRADAY".equalsIgnoreCase(category);\n    }')
text = read(strategy)
text = text.replace('this.lastMessage = "REGULAR_LIMIT".equalsIgnoreCase(this.entryMode)\n                ? "Immediate entry LIMIT submitted." : "Entry GTT active.";',
                    'this.lastMessage = this.entryMode.toUpperCase(java.util.Locale.US).contains("LIMIT")\n                ? "Entry LIMIT submitted." : "Entry GTT active.";')
write(strategy, text)


# Background reconciliation protects the rare case where Groww remains NEW for
# longer than the initial ten-second confirmation window. A later rejection is
# closed cleanly without a stop, false acceptance log, or successful-buy count.
monitor = JAVA / "StrategyMonitorService.java"
text = read(monitor)
old = '''        if (Strategy.CLOSED.equals(strategy.state)
                || Strategy.ERROR.equals(strategy.state)) return;

        GrowwClient.IntResult position = GrowwClient.getNetPositionQuantity('''
new = '''        if (Strategy.CLOSED.equals(strategy.state)
                || Strategy.ERROR.equals(strategy.state)) return;

        if (strategy.entryMode != null
                && strategy.entryMode.startsWith("PENDING_")) {
            if (!reconcilePendingEntry(token, strategy)) return;
        }

        GrowwClient.IntResult position = GrowwClient.getNetPositionQuantity('''
if old not in text:
    raise RuntimeError("Could not locate monitor pending-entry insertion point")
text = text.replace(old, new, 1)
write(monitor, text)

reconcile_method = r'''    private boolean reconcilePendingEntry(String token, Strategy strategy) {
        GrowwClient.OrderStatus status = GrowwClient.getOrderByReference(
                token, strategy.entryReferenceId);
        if (!status.success) {
            strategy.lastMessage = "Entry broker confirmation is temporarily unavailable: "
                    + status.message;
            save(strategy);
            return false;
        }
        if (EntryOrderPolicy.isDurable(status.status, status.filledQuantity)) {
            boolean fallback = strategy.entryMode.contains("CNC_FALLBACK");
            strategy.entryMode = fallback ? "CNC_FALLBACK_LIMIT" : "REGULAR_LIMIT";
            strategy.observedFilledQuantity = Math.max(strategy.observedFilledQuantity,
                    Math.min(strategy.requestedQuantity, status.filledQuantity));
            strategy.lastMessage = "Broker-confirmed entry " + status.status
                    + (fallback ? " • CNC same-day fallback." : ".");
            save(strategy);
            AppPrefs.incrementDailyBuyCount(this);
            AppPrefs.log(this, fallback
                            ? "CNC FALLBACK ENTRY ACCEPTED — BROKER CONFIRMED"
                            : "ENTRY ACCEPTED — BROKER CONFIRMED",
                    strategy.symbol + " • " + strategy.lastMessage);
            return true;
        }
        if (EntryOrderPolicy.isTerminalFailure(status.status)) {
            strategy.state = Strategy.CLOSED;
            strategy.lastMessage = "Entry became " + status.status
                    + "; no filled position and no stop-loss created. " + status.message;
            save(strategy);
            AppPrefs.log(this, "ENTRY REJECTED — NO POSITION",
                    strategy.symbol + " • " + strategy.lastMessage);
            return false;
        }
        strategy.lastMessage = "Entry remains "
                + (status.status.isEmpty() ? "PENDING" : status.status)
                + "; waiting for broker confirmation.";
        save(strategy);
        return false;
    }

'''
text = read(monitor)
marker = "    private boolean refreshPublicIpIfDue() {\n"
if marker not in text:
    raise RuntimeError("Could not locate monitor helper marker")
text = text.replace(marker, reconcile_method + marker, 1)
write(monitor, text)


# Visible release disclosure. The fallback is explicit rather than silent.
activity = JAVA / "ProductionActivity.java"
text = read(activity)
text = text.replace("2.2.5", "2.2.6")
text = text.replace(
    "budget follows Intraday/Swing/Multibagger/Free",
    "trade-type budgets • MIS basket rejection => CNC same-day fallback")
text = text.replace(
    "● Routing + budget policy: notification-owned • amount follows trade type",
    "● Routing: Intraday tries MIS first • assigned-basket rejection retries CNC same-day")
write(activity, text)


write(TEST / "EntryOrderPolicyTest.java", r'''package com.suhas.multyfiautobuy.stable;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

public class EntryOrderPolicyTest {
    @Test public void newAndAckedAreNotAccepted() {
        assertTrue(EntryOrderPolicy.isTransient("NEW"));
        assertTrue(EntryOrderPolicy.isTransient("ACKED"));
        assertFalse(EntryOrderPolicy.isDurable("NEW", 0));
        assertFalse(EntryOrderPolicy.isDurable("ACKED", 0));
    }

    @Test public void openOrActualFillIsDurable() {
        assertTrue(EntryOrderPolicy.isDurable("OPEN", 0));
        assertTrue(EntryOrderPolicy.isDurable("NEW", 1));
        assertTrue(EntryOrderPolicy.isDurable("PARTIALLY_FILLED", 1));
    }

    @Test public void assignedBasketTriggersOnlyTheCncFallbackFamily() {
        assertTrue(EntryOrderPolicy.isMisBasketRestriction(
                "RMS:Rule: Assigned basket for entity across exchange across segment across product"));
        assertFalse(EntryOrderPolicy.isMisBasketRestriction(
                "Insufficient funds"));
    }

    @Test public void fallbackReferenceIsValidAndDistinct() {
        String reference = EntryOrderPolicy.cncFallbackReference(
                "MF260731ABCDEF12");
        assertTrue(reference.matches("[A-Z0-9]{8,20}"));
        assertTrue(reference.startsWith("FC"));
        assertEquals(reference, EntryOrderPolicy.cncFallbackReference(
                "MF260731ABCDEF12"));
    }
}
''')


# Fail the source build if any live-contract item silently regresses.
client_text = read(client)
service_text = read(service)
monitor_text = read(monitor)
strategy_text = read(strategy)
assert "versionName '2.2.6'" in read(gradle)
assert "placeConfirmedEntryLimit" in client_text
assert "ENTRY SUBMITTED — BROKER CONFIRMATION PENDING" in service_text
assert "MIS BLOCKED BY GROWW — TRYING CNC SAME-DAY FALLBACK" in service_text
assert "CNC_FALLBACK_LIMIT" in service_text
assert "EntryOrderPolicy.isMisBasketRestriction" in service_text
assert "reconcilePendingEntry" in monitor_text
assert '"INTRADAY".equalsIgnoreCase(category)' in strategy_text
assert "NEW" in read(JAVA / "EntryOrderPolicy.java")
assert "assigned basket" in read(JAVA / "EntryOrderPolicy.java")
print("Applied v2.2.6 confirmed-entry and CNC same-day fallback fix")
