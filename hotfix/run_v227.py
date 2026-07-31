#!/usr/bin/env python3
from pathlib import Path
import re
import runpy

# Build on the fully validated v2.2.6 release chain.
runpy.run_path("hotfix/run_v226.py", run_name="__main__")

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
replace_once(gradle, "versionCode 226", "versionCode 227")
replace_once(gradle, "versionName '2.2.6'", "versionName '2.2.7'")

# Add the official Google Play package ID for Research 360.
prefs = JAVA / "AppPrefs.java"
replace_once(prefs,
             '    static final String MULTYFI_PACKAGE = "com.multyfi.invest";\n',
             '    static final String MULTYFI_PACKAGE = "com.multyfi.invest";\n'
             '    static final String RESEARCH360_PACKAGE = "com.mosl.research360app";\n')

# Strict parser: only MOST Overnight-Profit stock notifications are actionable.
# All loss, option, FNO, index and every other Research 360 notification is ignored.
write(JAVA / "Research360Parser.java", r'''package com.suhas.multyfiautobuy.stable;

import java.util.Locale;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

final class Research360Parser {
    private static final Pattern STOCK = Pattern.compile(
            "(?i)our\\s+buy\\s+call\\s+of\\s+([A-Z0-9&.\\-]+)\\s+on\\s+"
                    + "\\d{1,2}\\s+[A-Z]{3,9}\\s+\\d{4}\\s+at\\s+(?:RS\\.?|₹)?\\s*"
                    + "[0-9,.]+.*?call\\s+closed");
    private static final Pattern OPTION_CONTRACT = Pattern.compile(
            "(?i)\\b(?:BANKNIFTY|NIFTY|FINNIFTY|MIDCPNIFTY)[A-Z0-9]*\\b|"
                    + "\\b\\d{4,6}\\s*(?:CE|PE)\\b|\\b[A-Z0-9&.\\-]+(?:CE|PE|FUT)\\b");

    private Research360Parser() { }

    static ExitSignal parse(String rawText, long notificationTimeMillis) {
        String raw = rawText == null ? "" : rawText.trim();
        String normalized = raw.toUpperCase(Locale.US)
                .replace('–', '-')
                .replace('—', '-')
                .replaceAll("[^A-Z0-9&.\\-₹]+", " ")
                .replaceAll("\\s+", " ")
                .trim();
        String phrase = normalized.replace('-', ' ')
                .replaceAll("\\s+", " ").trim();

        if (!phrase.contains("MOST OVERNIGHT PROFIT")) return null;
        if (phrase.contains("MOST OVERNIGHT LOSS")) return null;
        if (phrase.contains("OPTION WRITER") || phrase.contains(" OPTIONS ")
                || phrase.contains(" FUTURE ") || phrase.contains(" FUTURES ")
                || OPTION_CONTRACT.matcher(normalized).find()) return null;
        if (!phrase.contains("ADVISABLE TO BOOK PROFIT")
                || !phrase.contains("CALL CLOSED")) return null;

        Matcher matcher = STOCK.matcher(normalized);
        if (!matcher.find()) return null;
        String symbol = matcher.group(1).toUpperCase(Locale.US).trim();
        if (!symbol.matches("[A-Z0-9&.\\-]{1,30}")) return null;
        String eventId = eventId(normalized);
        return new ExitSignal(eventId, reference(eventId), symbol,
                notificationTimeMillis, raw);
    }

    private static String eventId(String normalized) {
        long unsigned = Integer.toUnsignedLong(normalized.hashCode());
        return "R360P" + Long.toString(unsigned, 36).toUpperCase(Locale.US);
    }

    private static String reference(String eventId) {
        String clean = ("R3S" + eventId).replaceAll("[^A-Za-z0-9]", "")
                .toUpperCase(Locale.US);
        if (clean.length() < 8) clean += "00000000";
        return clean.substring(0, Math.min(20, clean.length()));
    }

    static final class ExitSignal {
        final String eventId;
        final String referenceId;
        final String symbol;
        final long notificationTimeMillis;
        final String rawText;

        ExitSignal(String eventId, String referenceId, String symbol,
                   long notificationTimeMillis, String rawText) {
            this.eventId = eventId;
            this.referenceId = referenceId;
            this.symbol = symbol;
            this.notificationTimeMillis = notificationTimeMillis;
            this.rawText = rawText;
        }
    }
}
''')

# Add holdings lookup, existing-sell checks (regular + active GTT), and a
# broker-confirmed CNC market sell. Every endpoint is CASH-only, so Research 360
# can never create an option/FNO order.
client = JAVA / "GrowwClient.java"
research_methods = r'''    static HoldingResult getSellableHolding(String accessToken, String symbol) {
        try {
            HttpResult http = request("GET", API_BASE + "/holdings/user",
                    accessToken, null);
            if (!http.isSuccess()) return HoldingResult.failure(http.message());
            JSONObject payload = new JSONObject(http.body).optJSONObject("payload");
            JSONArray holdings = payload == null ? null : payload.optJSONArray("holdings");
            if (holdings == null) return HoldingResult.success(0, 0, "No holdings returned.");
            for (int i = 0; i < holdings.length(); i++) {
                JSONObject holding = holdings.optJSONObject(i);
                if (holding == null || !symbol.equalsIgnoreCase(
                        holding.optString("trading_symbol", ""))) continue;
                int total = Math.max(0, holding.optInt("quantity", 0));
                double explicit = Math.max(0d, holding.optDouble("demat_free_quantity", 0d))
                        + Math.max(0d, holding.optDouble("t1_quantity", 0d))
                        + Math.max(0d, holding.optDouble(
                                "corporate_action_additional_quantity", 0d));
                double blocked = Math.max(0d, holding.optDouble("pledge_quantity", 0d))
                        + Math.max(0d, holding.optDouble("demat_locked_quantity", 0d))
                        + Math.max(0d, holding.optDouble("groww_locked_quantity", 0d))
                        + Math.max(0d, holding.optDouble(
                                "active_demat_transfer_quantity", 0d));
                int calculated = explicit > 0d
                        ? (int) Math.floor(explicit + 1e-9d)
                        : (int) Math.floor(Math.max(0d, total - blocked) + 1e-9d);
                int sellable = Math.max(0, Math.min(total, calculated));
                return HoldingResult.success(total, sellable,
                        "Holding " + symbol + ": total " + total
                                + ", safely sellable " + sellable + ".");
            }
            return HoldingResult.success(0, 0, symbol + " is not present in holdings.");
        } catch (Exception e) {
            return HoldingResult.failure("Holdings lookup error: " + safeMessage(e));
        }
    }

    static SellOrderCheck hasExistingSellOrder(String accessToken, String symbol) {
        try {
            HttpResult regular = request("GET",
                    API_BASE + "/order/list?segment=CASH&page=0&page_size=100",
                    accessToken, null);
            if (!regular.isSuccess()) return SellOrderCheck.failure(regular.message());
            JSONObject regularPayload = new JSONObject(regular.body).optJSONObject("payload");
            JSONArray orders = regularPayload == null ? null
                    : regularPayload.optJSONArray("order_list");
            if (orders != null) {
                for (int i = 0; i < orders.length(); i++) {
                    JSONObject order = orders.optJSONObject(i);
                    if (order == null) continue;
                    if (!symbol.equalsIgnoreCase(order.optString("trading_symbol", ""))) continue;
                    if (!"SELL".equalsIgnoreCase(order.optString("transaction_type", ""))) continue;
                    if (!"CASH".equalsIgnoreCase(order.optString("segment", "CASH"))) continue;
                    if (isLiveExitOrderStatus(order.optString("order_status", ""))) {
                        return SellOrderCheck.existing("Existing regular SELL order "
                                + order.optString("groww_order_id", "") + " is "
                                + order.optString("order_status", "") + ".");
                    }
                }
            }

            HttpResult smart = request("GET",
                    API_BASE + "/order-advance/list?segment=CASH&smart_order_type=GTT"
                            + "&status=ACTIVE&page=0&page_size=50",
                    accessToken, null);
            if (!smart.isSuccess()) return SellOrderCheck.failure(smart.message());
            JSONObject smartPayload = new JSONObject(smart.body).optJSONObject("payload");
            JSONArray smartOrders = smartPayload == null ? null
                    : smartPayload.optJSONArray("orders");
            if (smartOrders != null) {
                for (int i = 0; i < smartOrders.length(); i++) {
                    JSONObject order = smartOrders.optJSONObject(i);
                    if (order == null) continue;
                    if (!symbol.equalsIgnoreCase(order.optString("trading_symbol", ""))) continue;
                    JSONObject child = order.optJSONObject("order");
                    String transaction = child == null ? ""
                            : child.optString("transaction_type", "");
                    if ("SELL".equalsIgnoreCase(transaction)
                            && "ACTIVE".equalsIgnoreCase(order.optString("status", ""))) {
                        return SellOrderCheck.existing("Existing active SELL GTT "
                                + order.optString("smart_order_id", "") + ".");
                    }
                }
            }
            return SellOrderCheck.none();
        } catch (Exception e) {
            return SellOrderCheck.failure("Existing-sell check error: " + safeMessage(e));
        }
    }

    static ExitSellResult placeConfirmedResearch360Sell(String accessToken,
                                                         String symbol,
                                                         int quantity,
                                                         String referenceId) {
        if (quantity <= 0) {
            return ExitSellResult.failure("SELL_QTY_ZERO", "Sell quantity is zero.", 0);
        }
        try {
            JSONObject body = new JSONObject();
            body.put("trading_symbol", symbol);
            body.put("quantity", quantity);
            body.put("price", 0);
            body.put("trigger_price", 0);
            body.put("validity", "DAY");
            body.put("exchange", "NSE");
            body.put("segment", "CASH");
            body.put("product", "CNC");
            body.put("order_type", "MARKET");
            body.put("transaction_type", "SELL");
            body.put("order_reference_id", referenceId);
            HttpResult http = request("POST", API_BASE + "/order/create",
                    accessToken, body);
            if (!http.isSuccess()) {
                ApiResult failure = apiFailure(http);
                if ("GA007".equalsIgnoreCase(failure.errorCode)) {
                    OrderStatus existing = getOrderByReference(accessToken, referenceId);
                    if (existing.success && !existing.orderId.isEmpty()) {
                        return ExitSellResult.submitted(existing.orderId,
                                existing.status, existing.filledQuantity,
                                "Recovered existing Research 360 sell order "
                                        + existing.orderId + " • " + existing.status + ".",
                                existing.httpCode);
                    }
                }
                return ExitSellResult.failure(failure.errorCode,
                        failure.message, failure.httpCode);
            }
            JSONObject payload = new JSONObject(http.body).optJSONObject("payload");
            String id = payload == null ? "" : payload.optString("groww_order_id", "");
            String status = payload == null ? "" : payload.optString("order_status", "");
            int filled = payload == null ? 0 : payload.optInt("filled_quantity", 0);
            String remark = payload == null ? "" : payload.optString("remark", "");
            if (id.isEmpty()) {
                return ExitSellResult.failure("SELL_NO_ORDER_ID",
                        "Groww returned no sell order ID.", http.code);
            }
            if (EntryOrderPolicy.isTerminalFailure(status)) {
                return ExitSellResult.failure("SELL_REJECTED",
                        "Groww rejected the Research 360 sell: " + status
                                + " " + remark, http.code);
            }
            if (EntryOrderPolicy.isDurable(status, filled)) {
                return ExitSellResult.submitted(id, status, filled,
                        "Research 360 CNC MARKET sell confirmed " + status
                                + " for " + quantity + " shares: " + id + ".",
                        http.code);
            }
            OrderStatus confirmed = OrderStatus.failure(0, "Not checked.");
            for (int i = 0; i < 40; i++) {
                confirmed = getOrderByReference(accessToken, referenceId);
                if (confirmed.success && EntryOrderPolicy.isDurable(
                        confirmed.status, confirmed.filledQuantity)) {
                    return ExitSellResult.submitted(
                            confirmed.orderId.isEmpty() ? id : confirmed.orderId,
                            confirmed.status, confirmed.filledQuantity,
                            "Research 360 CNC MARKET sell confirmed "
                                    + confirmed.status + " for " + quantity
                                    + " shares: "
                                    + (confirmed.orderId.isEmpty() ? id : confirmed.orderId)
                                    + ".", confirmed.httpCode);
                }
                if (confirmed.success
                        && EntryOrderPolicy.isTerminalFailure(confirmed.status)) {
                    return ExitSellResult.failure("SELL_REJECTED",
                            "Groww rejected the Research 360 sell: "
                                    + confirmed.status + " " + confirmed.message,
                            confirmed.httpCode);
                }
                try { Thread.sleep(250L); }
                catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    break;
                }
            }
            return ExitSellResult.submitted(id,
                    confirmed.success ? confirmed.status : status,
                    confirmed.success ? confirmed.filledQuantity : filled,
                    "Research 360 sell was submitted but broker confirmation is still pending: "
                            + id + ". Existing-order checks prevent a duplicate sell.",
                    http.code);
        } catch (Exception e) {
            return ExitSellResult.failure("", "Research 360 sell error: "
                    + safeMessage(e), 0);
        }
    }

    private static boolean isLiveExitOrderStatus(String status) {
        return "NEW".equalsIgnoreCase(status)
                || "ACKED".equalsIgnoreCase(status)
                || "OPEN".equalsIgnoreCase(status)
                || "APPROVED".equalsIgnoreCase(status)
                || "PENDING".equalsIgnoreCase(status)
                || "VALIDATION_PENDING".equalsIgnoreCase(status)
                || "TRIGGER_PENDING".equalsIgnoreCase(status)
                || "PARTIALLY_FILLED".equalsIgnoreCase(status)
                || "PARTIAL".equalsIgnoreCase(status)
                || "MODIFICATION_REQUESTED".equalsIgnoreCase(status)
                || "CANCELLATION_REQUESTED".equalsIgnoreCase(status);
    }

'''
text = read(client)
marker = "    static ApiResult verifyProfile(String accessToken) {\n"
if marker not in text:
    raise RuntimeError("Could not locate GrowwClient insertion marker")
text = text.replace(marker, research_methods + marker, 1)
write(client, text)

result_classes = r'''    static final class HoldingResult {
        final boolean success;
        final int totalQuantity;
        final int sellableQuantity;
        final String message;

        private HoldingResult(boolean success, int total, int sellable, String message) {
            this.success = success;
            this.totalQuantity = total;
            this.sellableQuantity = sellable;
            this.message = message == null ? "" : message;
        }

        static HoldingResult success(int total, int sellable, String message) {
            return new HoldingResult(true, total, sellable, message);
        }

        static HoldingResult failure(String message) {
            return new HoldingResult(false, 0, 0, message);
        }
    }

    static final class SellOrderCheck {
        final boolean success;
        final boolean exists;
        final String message;

        private SellOrderCheck(boolean success, boolean exists, String message) {
            this.success = success;
            this.exists = exists;
            this.message = message == null ? "" : message;
        }

        static SellOrderCheck existing(String message) {
            return new SellOrderCheck(true, true, message);
        }

        static SellOrderCheck none() {
            return new SellOrderCheck(true, false, "No existing regular or GTT sell order.");
        }

        static SellOrderCheck failure(String message) {
            return new SellOrderCheck(false, false, message);
        }
    }

    static final class ExitSellResult {
        final boolean success;
        final String orderId;
        final String status;
        final int filledQuantity;
        final String errorCode;
        final String message;
        final int httpCode;

        private ExitSellResult(boolean success, String orderId, String status,
                               int filledQuantity, String errorCode,
                               String message, int httpCode) {
            this.success = success;
            this.orderId = orderId == null ? "" : orderId;
            this.status = status == null ? "" : status;
            this.filledQuantity = Math.max(0, filledQuantity);
            this.errorCode = errorCode == null ? "" : errorCode;
            this.message = message == null ? "" : message;
            this.httpCode = httpCode;
        }

        static ExitSellResult submitted(String orderId, String status,
                                        int filled, String message, int code) {
            return new ExitSellResult(true, orderId, status, filled,
                    "", message, code);
        }

        static ExitSellResult failure(String errorCode, String message, int code) {
            return new ExitSellResult(false, "", "", 0,
                    errorCode, message, code);
        }
    }

'''
text = read(client)
marker = "    static final class AuthResult {\n"
if marker not in text:
    raise RuntimeError("Could not locate GrowwClient result-class marker")
text = text.replace(marker, result_classes + marker, 1)
write(client, text)

# Route notifications strictly by package. Multyfi retains all buy and active-
# strategy exit behaviour; Research 360 can only reach the holdings-sell path.
service = JAVA / "ProductionNotificationService.java"
on_notification = r'''    @Override
    public void onNotificationPosted(StatusBarNotification sbn) {
        if (sbn == null || sbn.getNotification() == null) return;
        final String sourcePackage = sbn.getPackageName();
        final long postTime = sbn.getPostTime();
        final String rawText = extractText(sbn.getNotification());
        if (AppPrefs.MULTYFI_PACKAGE.equals(sourcePackage)) {
            executor.execute(() -> process(rawText, postTime));
        } else if (AppPrefs.RESEARCH360_PACKAGE.equals(sourcePackage)) {
            executor.execute(() -> processResearch360(rawText, postTime));
        }
    }
'''
replace_java_method(service, "    @Override\n    public void onNotificationPosted", on_notification)

research_handler = r'''    private void processResearch360(String rawText, long postTime) {
        PowerManager.WakeLock wakeLock = null;
        Research360Parser.ExitSignal signal = Research360Parser.parse(rawText, postTime);
        if (signal == null) return;
        try {
            PowerManager manager = (PowerManager) getSystemService(POWER_SERVICE);
            if (manager != null) {
                wakeLock = manager.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK,
                        getPackageName() + ":research360-profit-exit");
                wakeLock.acquire(45_000L);
            }
            long age = System.currentTimeMillis() - signal.notificationTimeMillis;
            if (age > AppPrefs.MAX_EARLY_EXIT_AGE_MS || age < -60_000L) {
                AppPrefs.log(this, "RESEARCH 360 PROFIT EXIT IGNORED — STALE",
                        signal.symbol + " • age " + age + " ms");
                return;
            }
            if (AppPrefs.isProcessed(this, signal.eventId)) {
                AppPrefs.log(this, "RESEARCH 360 PROFIT EXIT DUPLICATE BLOCKED",
                        signal.symbol + " • notification already handled.");
                return;
            }
            if (!AppPrefs.isArmed(this)) {
                AppPrefs.log(this, "RESEARCH 360 PROFIT FOUND — APP DISARMED",
                        signal.symbol + " • no sell order submitted.");
                return;
            }
            if (!NetworkUtil.isNetworkAvailable(this) || !NetworkUtil.isVpnActive(this)
                    || !ensureStaticPublicIp()) {
                AppPrefs.log(this, "RESEARCH 360 PROFIT EXIT BLOCKED — SURFSHARK/IP",
                        signal.symbol + " • no sell order submitted.");
                return;
            }
            if (!AppPrefs.isAuthVerifiedToday(this)) {
                AppPrefs.log(this, "RESEARCH 360 PROFIT EXIT BLOCKED — GROWW NOT VERIFIED",
                        signal.symbol + " • no sell order submitted.");
                return;
            }
            String token = TokenManager.validToken(this);
            if (token.isEmpty()) {
                AppPrefs.clearAuthVerified(this);
                AppPrefs.log(this, "RESEARCH 360 PROFIT EXIT BLOCKED — AUTH UNAVAILABLE",
                        signal.symbol + " • no sell order submitted.");
                return;
            }

            GrowwClient.HoldingResult holding = GrowwClient.getSellableHolding(
                    token, signal.symbol);
            if (!holding.success) {
                AppPrefs.log(this, "RESEARCH 360 HOLDING CHECK FAILED",
                        signal.symbol + " • " + holding.message);
                return;
            }
            if (holding.sellableQuantity <= 0) {
                AppPrefs.markProcessed(this, signal.eventId);
                AppPrefs.log(this, "RESEARCH 360 PROFIT IGNORED — NOT IN SELLABLE HOLDINGS",
                        signal.symbol + " • " + holding.message);
                return;
            }

            GrowwClient.SellOrderCheck existing = GrowwClient.hasExistingSellOrder(
                    token, signal.symbol);
            if (!existing.success) {
                AppPrefs.log(this, "RESEARCH 360 SELL-ORDER CHECK FAILED",
                        signal.symbol + " • " + existing.message
                                + " • fail-safe: no sell submitted.");
                return;
            }
            if (existing.exists) {
                AppPrefs.markProcessed(this, signal.eventId);
                AppPrefs.log(this, "RESEARCH 360 PROFIT IGNORED — SELL ORDER EXISTS",
                        signal.symbol + " • " + existing.message
                                + " Existing order was not modified or cancelled.");
                return;
            }

            GrowwClient.ExitSellResult sell = GrowwClient.placeConfirmedResearch360Sell(
                    token, signal.symbol, holding.sellableQuantity,
                    signal.referenceId);
            AppPrefs.markProcessed(this, signal.eventId);
            if (sell.success) {
                AppPrefs.log(this, "RESEARCH 360 OVERNIGHT PROFIT SELL SUBMITTED",
                        signal.symbol + " • quantity " + holding.sellableQuantity
                                + " • " + sell.message);
            } else {
                AppPrefs.log(this, "RESEARCH 360 OVERNIGHT PROFIT SELL FAILED",
                        signal.symbol + " • quantity " + holding.sellableQuantity
                                + " • " + sell.message
                                + (sell.errorCode.isEmpty() ? ""
                                : " [" + sell.errorCode + "]"));
            }
        } catch (Exception e) {
            AppPrefs.log(this, "RESEARCH 360 PROCESSING ERROR",
                    e.getClass().getSimpleName() + ": " + e.getMessage());
        } finally {
            if (wakeLock != null && wakeLock.isHeld()) wakeLock.release();
        }
    }

'''
text = read(service)
marker = "    @Override\n    public void onDestroy() {\n"
if marker not in text:
    raise RuntimeError("Could not locate notification-service insertion marker")
text = text.replace(marker, research_handler + marker, 1)
text = text.replace(
    "Production listener connected.",
    "Production listener connected for Multyfi buys/exits and Research 360 overnight-profit holding exits.",
    1)
write(service, text)

# Visible release wording.
activity = JAVA / "ProductionActivity.java"
text = read(activity)
text = text.replace("2.2.6", "2.2.7")
text = text.replace("stable release 2.2.7", "stable release 2.2.7")
# Add source-policy wording wherever the existing routing policy appears.
text = text.replace(
    "● Routing + budget policy: notification-owned • amount follows trade type",
    "● Sources: Multyfi buys/exits • Research 360 MOST Overnight-Profit sells holdings only • options ignored")
text = text.replace(
    "Auto-Buy OFF by default • budget follows Intraday/Swing/Multibagger/Free • source-built v2.2.7",
    "Auto-Buy OFF by default • Multyfi buys only • Research 360 profit exits only • source-built v2.2.7")
write(activity, text)

# Unit tests for the exact screenshot patterns and all negative paths.
write(TEST / "Research360ParserTest.java", r'''package com.suhas.multyfiautobuy.stable;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertNull;

import org.junit.Test;

public class Research360ParserTest {
    @Test public void parsesMostOvernightProfitStock() {
        Research360Parser.ExitSignal signal = Research360Parser.parse(
                "MOST Overnight-Profit\nOur Buy Call of MAZDOCK on 30 Jul 2026 at Rs.2338.60 has now reached Rs.2339.30. It's advisable to book Profit. Call Closed",
                123L);
        assertNotNull(signal);
        assertEquals("MAZDOCK", signal.symbol);
    }

    @Test public void parsesAmpersandNseSymbol() {
        Research360Parser.ExitSignal signal = Research360Parser.parse(
                "MOST Overnight-Profit Our Buy Call of M&M on 30 Jul 2026 at Rs.3269.40 has now reached Rs.3371.00. It's advisable to book Profit. Call Closed",
                123L);
        assertNotNull(signal);
        assertEquals("M&M", signal.symbol);
    }

    @Test public void ignoresOvernightLoss() {
        assertNull(Research360Parser.parse(
                "MOST Overnight-Loss Our Buy Call of MAZDOCK on 30 Jul 2026 at Rs.2338.60. Call Closed",
                123L));
    }

    @Test public void ignoresOptionsAndOptionWriter() {
        assertNull(Research360Parser.parse(
                "MOST Option Writer-Profit Our Sell Call of BANKNIFTYNSE 25 Aug PE 53500 on 31 Jul 2026 at Rs.48.70 has now reached Rs.48.45. It's advisable to book Profit. Call Closed",
                123L));
        assertNull(Research360Parser.parse(
                "MOST Overnight-Profit Our Buy Call of NIFTY31JUL25000CE on 30 Jul 2026 at Rs.100 has now reached Rs.110. It's advisable to book Profit. Call Closed",
                123L));
    }

    @Test public void ignoresResearch360BuyRecommendation() {
        assertNull(Research360Parser.parse(
                "MOST Overnight Our Buy Call of EXIDEIND on 30 Jul 2026 at Rs.453.00 Target Rs.470",
                123L));
    }
}
''')

# Source contracts: Research 360 never reaches BUY/FNO paths.
client_text = read(client)
service_text = read(service)
parser_text = read(JAVA / "Research360Parser.java")
assert 'RESEARCH360_PACKAGE = "com.mosl.research360app"' in read(prefs)
assert 'body.put("transaction_type", "SELL")' in client_text
assert 'body.put("product", "CNC")' in client_text
assert 'body.put("segment", "CASH")' in client_text
assert 'placeConfirmedResearch360Sell' in service_text
assert 'placeImmediateEntryLimit' not in research_handler
assert 'createEntryGtt' not in research_handler
assert 'MOST OVERNIGHT PROFIT' in parser_text
assert 'MOST OVERNIGHT LOSS' in parser_text
assert 'OPTION WRITER' in parser_text
assert "hasExistingSellOrder" in client_text
assert "order-advance/list?segment=CASH" in client_text
print("Applied v2.2.7 Research 360 overnight-profit holdings exit integration")
