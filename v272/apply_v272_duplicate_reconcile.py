from pathlib import Path

ROOT = Path('android-stable')
JAVA = ROOT / 'app/src/main/java/com/suhas/multyfiautobuy/stable'
TEST = ROOT / 'app/src/test/java/com/suhas/multyfiautobuy/stable'

p = JAVA / 'GrowwClient.java'
s = p.read_text()

old = '''    private static HttpResult createSmartOrderWithRetry(String accessToken,
                                                         JSONObject body) throws Exception {
        HttpResult last = null;
        long[] backoffMs = new long[]{0L, 250L, 750L};
        for (int attempt = 0; attempt < SMART_CREATE_MAX_ATTEMPTS; attempt++) {
            if (backoffMs[attempt] > 0L) {
                try {
                    Thread.sleep(backoffMs[attempt]);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    break;
                }
            }
            // Retry only transient Smart Order create failures and reuse the exact
            // same JSON body/reference_id for every attempt.
            last = request("POST", API_BASE + "/order-advance/create", accessToken, body);
            if (!isTransientSmartCreateHttpCode(last.code)) return last;
        }
        return last == null
                ? new HttpResult(0, "Smart-order create was not attempted.") : last;
    }

    private static ApiResult smartCreateFailure(HttpResult http) {
        ApiResult baseFailure = apiFailure(http);
        if (!isTransientSmartCreateHttpCode(http.code)) return baseFailure;
        return ApiResult.failure(baseFailure.errorCode,
                "Groww Smart Order service remained unavailable after "
                        + SMART_CREATE_MAX_ATTEMPTS
                        + " safe same-reference attempts (HTTP " + http.code + "). "
                        + baseFailure.message,
                http.code);
    }

'''
assert old in s, 'v2.7.1 smart-create retry helper not found'

new = '''    private static HttpResult createSmartOrderWithRetry(String accessToken,
                                                         JSONObject body) throws Exception {
        HttpResult last = null;
        long[] backoffMs = new long[]{0L, 250L, 750L};
        for (int attempt = 0; attempt < SMART_CREATE_MAX_ATTEMPTS; attempt++) {
            if (backoffMs[attempt] > 0L) {
                try {
                    Thread.sleep(backoffMs[attempt]);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    break;
                }
            }

            last = request("POST", API_BASE + "/order-advance/create", accessToken, body);
            if (last.isSuccess()) return last;

            boolean transientFailure = isTransientSmartCreateHttpCode(last.code);
            boolean duplicate = isDuplicateSmartCreateBody(last.body);

            // A Smart Order create may be committed by Groww even when the caller sees
            // an HTTP 5xx. Before POSTing again, reconcile against Groww's Smart Order
            // list. If a retry receives "duplicate reference id", reconcile again and
            // NEVER create a fresh reference: the duplicate is evidence that the
            // original idempotent request already exists at the broker.
            if (transientFailure || duplicate) {
                HttpResult reconciled = reconcileSmartCreate(accessToken, body);
                if (reconciled != null) return reconciled;
            }

            if (duplicate) return last;
            if (!transientFailure) return last;
        }
        return last == null
                ? new HttpResult(0, "Smart-order create was not attempted.") : last;
    }

    static boolean isDuplicateSmartCreateBody(String body) {
        String lower = body == null ? "" : body.toLowerCase(Locale.US);
        return lower.contains("duplicate smart order")
                || lower.contains("reference id already exists")
                || lower.contains("duplicate order reference id")
                || lower.contains("ga007");
    }

    static boolean matchesSmartCreate(JSONObject requested, JSONObject candidate) {
        if (requested == null || candidate == null) return false;
        if (!sameText(requested, candidate, "smart_order_type")) return false;
        if (!sameText(requested, candidate, "trading_symbol")) return false;
        if (!sameText(requested, candidate, "exchange")) return false;
        if (!sameText(requested, candidate, "product_type")) return false;
        if (requested.optInt("quantity", -1) != candidate.optInt("quantity", -2)) return false;
        if (!sameText(requested, candidate, "trigger_direction")) return false;
        if (!sameDecimal(requested.opt("trigger_price"), candidate.opt("trigger_price"))) return false;

        String requestedReference = requested.optString("reference_id", "");
        String candidateReference = candidate.optString("reference_id", "");
        if (!requestedReference.isEmpty() && !candidateReference.isEmpty()
                && !requestedReference.equals(candidateReference)) return false;

        JSONObject requestedOrder = requested.optJSONObject("order");
        JSONObject candidateOrder = candidate.optJSONObject("order");
        if (requestedOrder != null && candidateOrder != null) {
            if (!sameText(requestedOrder, candidateOrder, "order_type")) return false;
            if (!sameText(requestedOrder, candidateOrder, "transaction_type")) return false;
            Object requestedPrice = requestedOrder.opt("price");
            Object candidatePrice = candidateOrder.opt("price");
            if (requestedPrice != null && requestedPrice != JSONObject.NULL
                    && candidatePrice != null && candidatePrice != JSONObject.NULL
                    && !sameDecimal(requestedPrice, candidatePrice)) return false;
        }
        return true;
    }

    private static boolean sameText(JSONObject left, JSONObject right, String key) {
        String a = left.optString(key, "").trim();
        String b = right.optString(key, "").trim();
        return !a.isEmpty() && !b.isEmpty() && a.equalsIgnoreCase(b);
    }

    private static boolean sameDecimal(Object left, Object right) {
        if (left == null || right == null || left == JSONObject.NULL || right == JSONObject.NULL) {
            return left == right;
        }
        try {
            double a = Double.parseDouble(String.valueOf(left));
            double b = Double.parseDouble(String.valueOf(right));
            return Math.abs(a - b) < 0.0001d;
        } catch (Exception ignored) {
            return String.valueOf(left).equals(String.valueOf(right));
        }
    }

    private static HttpResult reconcileSmartCreate(String accessToken,
                                                    JSONObject requested) throws Exception {
        for (int poll = 0; poll < 5; poll++) {
            if (poll > 0) {
                try {
                    Thread.sleep(250L);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    return null;
                }
            }
            JSONObject found = findMatchingSmartOrder(accessToken, requested);
            if (found != null) {
                JSONObject root = new JSONObject();
                root.put("status", "SUCCESS");
                root.put("payload", found);
                return new HttpResult(200, root.toString());
            }
        }
        return null;
    }

    private static JSONObject findMatchingSmartOrder(String accessToken,
                                                     JSONObject requested) throws Exception {
        String[] statuses = new String[]{"ACTIVE", "TRIGGERED", "COMPLETED"};
        JSONObject newest = null;
        String newestTime = "";
        String requestedReference = requested.optString("reference_id", "");

        for (String status : statuses) {
            String url = API_BASE + "/order-advance/list?segment=CASH"
                    + "&smart_order_type=GTT&status=" + enc(status)
                    + "&page=0&page_size=20";
            HttpResult list = request("GET", url, accessToken, null);
            if (!list.isSuccess()) continue;
            JSONObject payload = new JSONObject(list.body).optJSONObject("payload");
            JSONArray orders = payload == null ? null : payload.optJSONArray("orders");
            if (orders == null) continue;

            for (int i = 0; i < orders.length(); i++) {
                JSONObject item = orders.optJSONObject(i);
                if (item == null) continue;
                String id = item.optString("smart_order_id", "");
                JSONObject full = item;

                // Groww's list response may be compact. Resolve the full object when
                // needed so matching uses the exact symbol/quantity/trigger/order.
                if (!hasSmartCreateShape(full) && !id.isEmpty()) {
                    HttpResult detail = request("GET",
                            API_BASE + "/order-advance/status/CASH/GTT/internal/" + enc(id),
                            accessToken, null);
                    if (detail.isSuccess()) {
                        JSONObject detailPayload = new JSONObject(detail.body).optJSONObject("payload");
                        if (detailPayload != null) full = detailPayload;
                    }
                }

                if (!matchesSmartCreate(requested, full)) continue;
                if (full.optString("smart_order_id", "").isEmpty() && !id.isEmpty()) {
                    full.put("smart_order_id", id);
                }

                String candidateReference = full.optString("reference_id", "");
                if (!requestedReference.isEmpty()
                        && requestedReference.equals(candidateReference)) return full;

                String created = full.optString("created_at",
                        full.optString("updated_at", ""));
                if (newest == null || created.compareTo(newestTime) >= 0) {
                    newest = full;
                    newestTime = created;
                }
            }
        }
        return newest;
    }

    private static boolean hasSmartCreateShape(JSONObject item) {
        return item != null
                && !item.optString("trading_symbol", "").isEmpty()
                && item.has("quantity")
                && item.has("trigger_price")
                && !item.optString("trigger_direction", "").isEmpty();
    }

    private static ApiResult smartCreateFailure(HttpResult http) {
        ApiResult baseFailure = apiFailure(http);
        if (isDuplicateSmartCreateBody(http.body)) {
            return ApiResult.failure("SMART_CREATE_DUPLICATE_UNRESOLVED",
                    "Groww reports this Smart Order reference already exists, but the app could not safely reconcile its broker ID. Do not create a new reference automatically; inspect Smart Orders in Groww and cancel any unintended duplicate/test order.",
                    http.code);
        }
        if (!isTransientSmartCreateHttpCode(http.code)) return baseFailure;
        return ApiResult.failure(baseFailure.errorCode,
                "Groww Smart Order service remained unavailable after "
                        + SMART_CREATE_MAX_ATTEMPTS
                        + " same-reference attempts and broker reconciliation (HTTP "
                        + http.code + "). " + baseFailure.message,
                http.code);
    }

'''

s = s.replace(old, new, 1)
p.write_text(s)

# Expand focused tests for the ambiguous 5xx -> duplicate/idempotency scenario.
t = TEST / 'GrowwSmartOrderRetryPolicyTest.java'
t.write_text('''package com.suhas.multyfiautobuy.stable;

import org.json.JSONObject;
import org.junit.Test;
import static org.junit.Assert.*;

public class GrowwSmartOrderRetryPolicyTest {
    @Test public void server5xxCodesAreTransient() {
        assertTrue(GrowwClient.isTransientSmartCreateHttpCode(500));
        assertTrue(GrowwClient.isTransientSmartCreateHttpCode(502));
        assertTrue(GrowwClient.isTransientSmartCreateHttpCode(503));
        assertTrue(GrowwClient.isTransientSmartCreateHttpCode(504));
    }

    @Test public void rateLimitIsTransient() {
        assertTrue(GrowwClient.isTransientSmartCreateHttpCode(429));
    }

    @Test public void clientAndAuthErrorsAreNotBlindlyRetried() {
        assertFalse(GrowwClient.isTransientSmartCreateHttpCode(400));
        assertFalse(GrowwClient.isTransientSmartCreateHttpCode(401));
        assertFalse(GrowwClient.isTransientSmartCreateHttpCode(403));
        assertFalse(GrowwClient.isTransientSmartCreateHttpCode(422));
    }

    @Test public void duplicateSmartOrderMessageIsRecognised() {
        assertTrue(GrowwClient.isDuplicateSmartCreateBody(
                "Duplicate smart order. Order with this reference id already exists."));
        assertTrue(GrowwClient.isDuplicateSmartCreateBody(
                "{\\\"error\\\":{\\\"code\\\":\\\"GA007\\\"}}"));
    }

    @Test public void exactSmartOrderShapeMatchesForReconciliation() throws Exception {
        JSONObject request = gtt("TST2026081599999999", "ITC", 1, "100.00", "DOWN");
        JSONObject candidate = gtt("", "ITC", 1, "100.00", "DOWN");
        candidate.put("smart_order_id", "gtt_abc123");
        assertTrue(GrowwClient.matchesSmartCreate(request, candidate));
    }

    @Test public void differentTriggerDoesNotReconcile() throws Exception {
        JSONObject request = gtt("TST2026081599999999", "ITC", 1, "100.00", "DOWN");
        JSONObject candidate = gtt("", "ITC", 1, "99.95", "DOWN");
        candidate.put("smart_order_id", "gtt_other");
        assertFalse(GrowwClient.matchesSmartCreate(request, candidate));
    }

    private static JSONObject gtt(String reference, String symbol, int qty,
                                  String trigger, String direction) throws Exception {
        JSONObject order = new JSONObject();
        order.put("order_type", "LIMIT");
        order.put("price", trigger);
        order.put("transaction_type", "BUY");
        JSONObject body = new JSONObject();
        if (!reference.isEmpty()) body.put("reference_id", reference);
        body.put("smart_order_type", "GTT");
        body.put("segment", "CASH");
        body.put("trading_symbol", symbol);
        body.put("quantity", qty);
        body.put("trigger_price", trigger);
        body.put("trigger_direction", direction);
        body.put("order", order);
        body.put("product_type", "CNC");
        body.put("exchange", "NSE");
        body.put("duration", "DAY");
        return body;
    }
}
''')

print('Applied v2.7.2 Smart Order ambiguous-5xx duplicate reconciliation')
