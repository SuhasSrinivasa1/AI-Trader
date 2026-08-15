from pathlib import Path

ROOT = Path('android-stable')
JAVA = ROOT / 'app/src/main/java/com/suhas/multyfiautobuy/stable'
TEST = ROOT / 'app/src/test/java/com/suhas/multyfiautobuy/stable'

# Restore the controlled one-share acceptance test to the old 0.05 tick semantics.
p = JAVA / 'ProductionActivity.java'
s = p.read_text()
s = s.replace('double testPrice = SignalParser.floorToTick(ltp.value * 0.90d, 0.10d);',
              'double testPrice = SignalParser.floorToTick(ltp.value * 0.90d, GrowwClient.CONTROLLED_TEST_TICK);', 1)
s = s.replace('double target = SignalParser.ceilToTick(testPrice * 1.10d, 0.10d);',
              'double target = SignalParser.ceilToTick(testPrice * 1.10d, GrowwClient.CONTROLLED_TEST_TICK);', 1)
s = s.replace('double stop = SignalParser.floorToTick(testPrice * 0.90d, 0.10d);',
              'double stop = SignalParser.floorToTick(testPrice * 0.90d, GrowwClient.CONTROLLED_TEST_TICK);', 1)
old_call = '''                        GrowwClient.ApiResult create = GrowwClient.createEntryGtt(
                                token, signal, 1, ltp.value);'''
new_call = '''                        GrowwClient.ApiResult create = GrowwClient.createControlledTestGtt(
                                token, signal, 1, ltp.value);'''
assert old_call in s, 'controlled test create call not found'
s = s.replace(old_call, new_call, 1)
p.write_text(s)

p = JAVA / 'GrowwClient.java'
s = p.read_text()
needle = 'final class GrowwClient {\n'
assert needle in s, 'GrowwClient class declaration not found'
s = s.replace(needle, needle + '    static final double CONTROLLED_TEST_TICK = 0.05d;\n', 1)

marker = '''    static ApiResult createEntryGtt(String accessToken, SignalParser.ParsedSignal signal,
                                    int quantity, double currentLtp) {'''
assert marker in s, 'createEntryGtt marker not found'

method = r'''    /**
     * Controlled broker acceptance test.
     *
     * This deliberately preserves the original source-built v2.0.0 request semantics:
     * one Smart Order POST only, 0.05 price tick, then broker-ID verification/cancel.
     * It does NOT use the v2.7.1/v2.7.2 create retry loop. If the one POST is ambiguous,
     * it performs read-only reconciliation across every documented Smart Order status.
     */
    static ApiResult createControlledTestGtt(String accessToken,
                                             SignalParser.ParsedSignal signal,
                                             int quantity,
                                             double currentLtp) {
        if (signal == null || currentLtp <= 0d || quantity <= 0) {
            return ApiResult.failure("", "A valid signal, quantity and current LTP are required.", 0);
        }
        try {
            double trigger;
            String direction;
            String mode;
            if (currentLtp > signal.maxBuyPrice) {
                trigger = signal.maxBuyPrice;
                direction = "DOWN";
                mode = "Legacy controlled test waits for pullback to ₹" + price(trigger) + ".";
            } else if (currentLtp < signal.entryLow) {
                trigger = signal.entryLow;
                direction = "UP";
                mode = "Legacy controlled test triggers at ₹" + price(trigger) + ".";
            } else {
                trigger = Math.min(signal.maxBuyPrice,
                        SignalParser.ceilToTick(currentLtp + CONTROLLED_TEST_TICK,
                                CONTROLLED_TEST_TICK));
                direction = "UP";
                mode = "Legacy controlled test one tick above LTP ₹" + price(currentLtp) + ".";
            }

            JSONObject order = new JSONObject();
            order.put("order_type", "LIMIT");
            order.put("price", price(signal.maxBuyPrice));
            order.put("transaction_type", "BUY");
            JSONObject body = gttBase(signal.referenceId, signal.symbol, quantity,
                    trigger, direction, order, signal.productType);

            // EXACTLY ONE create request. Never blindly POST the same reference again.
            HttpResult http = request("POST", API_BASE + "/order-advance/create",
                    accessToken, body);
            if (!http.isSuccess()) {
                ApiResult failure = apiFailure(http);
                JSONObject brokerRecord = findMatchingControlledTestGtt(accessToken, body);
                if (brokerRecord != null) {
                    String brokerId = brokerRecord.optString("smart_order_id", "");
                    String brokerStatus = brokerRecord.optString("status", "");
                    if (!brokerId.isEmpty() && isLiveSmartStatus(brokerStatus)) {
                        return ApiResult.success(brokerId,
                                "Recovered the one legacy test POST as " + brokerStatus
                                        + " • smart order " + brokerId + ". " + mode,
                                http.code);
                    }
                    return ApiResult.failure("TEST_GTT_BROKER_" +
                                    (brokerStatus.isEmpty() ? "UNKNOWN" : brokerStatus),
                            "The single legacy test POST returned HTTP " + http.code
                                    + " / " + failure.errorCode
                                    + ", and Groww recorded a matching Smart Order as "
                                    + (brokerStatus.isEmpty() ? "UNKNOWN" : brokerStatus)
                                    + (brokerId.isEmpty() ? "." : " • " + brokerId + ".")
                                    + " No second create was submitted. Broker message: "
                                    + failure.message,
                            http.code);
                }
                return ApiResult.failure(failure.errorCode,
                        "The single legacy v2.0-style GTT create returned HTTP " + http.code
                                + ". No retry/create was submitted. Reference "
                                + signal.referenceId + " • " + signal.symbol
                                + " • trigger ₹" + price(trigger)
                                + " • limit ₹" + price(signal.maxBuyPrice)
                                + ". Broker message: " + failure.message,
                        http.code);
            }

            JSONObject payload = new JSONObject(http.body).optJSONObject("payload");
            String id = payload == null ? "" : payload.optString("smart_order_id", "");
            String status = payload == null ? "" : payload.optString("status", "");
            if (id.isEmpty()) {
                return ApiResult.failure("TEST_GTT_NO_ID",
                        "Groww returned success for the single legacy create but no smart-order ID.",
                        http.code);
            }
            if (isLiveSmartStatus(status)) {
                return ApiResult.success(id,
                        "Legacy controlled GTT confirmed " + status + ": " + id + ". " + mode,
                        http.code);
            }
            SmartStatus confirmed = confirmGtt(accessToken, id);
            if (confirmed.success && isLiveSmartStatus(confirmed.status)) {
                return ApiResult.success(id,
                        "Legacy controlled GTT confirmed " + confirmed.status + ": " + id
                                + ". " + mode,
                        http.code);
            }
            cancelGtt(accessToken, id);
            return ApiResult.failure("TEST_GTT_NOT_ACTIVE",
                    "Groww returned smart-order ID " + id
                            + " but it did not become ACTIVE. Status: "
                            + confirmed.status + " " + confirmed.message,
                    http.code);
        } catch (Exception e) {
            return ApiResult.failure("TEST_GTT_ERROR",
                    "Legacy controlled GTT error: " + safeMessage(e), 0);
        }
    }

    private static JSONObject findMatchingControlledTestGtt(String accessToken,
                                                             JSONObject requested) {
        String[] statuses = new String[]{
                "ACTIVE", "TRIGGERED", "COMPLETED", "FAILED", "CANCELLED", "EXPIRED"
        };
        try {
            for (String status : statuses) {
                for (int page = 0; page < 3; page++) {
                    String url = API_BASE + "/order-advance/list?segment=CASH"
                            + "&smart_order_type=GTT&status=" + enc(status)
                            + "&page=" + page + "&page_size=50";
                    HttpResult list = request("GET", url, accessToken, null);
                    if (!list.isSuccess()) break;
                    JSONObject payload = new JSONObject(list.body).optJSONObject("payload");
                    JSONArray orders = payload == null ? null : payload.optJSONArray("orders");
                    if (orders == null || orders.length() == 0) break;
                    for (int i = 0; i < orders.length(); i++) {
                        JSONObject compact = orders.optJSONObject(i);
                        if (compact == null) continue;
                        String id = compact.optString("smart_order_id", "");
                        JSONObject full = compact;
                        if (!id.isEmpty()) {
                            HttpResult detail = request("GET",
                                    API_BASE + "/order-advance/status/CASH/GTT/internal/"
                                            + enc(id), accessToken, null);
                            if (detail.isSuccess()) {
                                JSONObject detailPayload = new JSONObject(detail.body)
                                        .optJSONObject("payload");
                                if (detailPayload != null) full = detailPayload;
                            }
                        }
                        if (matchesSmartCreate(requested, full)) {
                            if (full.optString("smart_order_id", "").isEmpty() && !id.isEmpty()) {
                                full.put("smart_order_id", id);
                            }
                            if (full.optString("status", "").isEmpty()) full.put("status", status);
                            return full;
                        }
                    }
                    if (orders.length() < 50) break;
                }
            }
        } catch (Exception ignored) {
            // The original create response remains authoritative; reconciliation is read-only.
        }
        return null;
    }

'''
s = s.replace(marker, method + marker, 1)
p.write_text(s)

(TEST / 'ControlledTestGttRegressionTest.java').write_text('''package com.suhas.multyfiautobuy.stable;\n\nimport org.junit.Test;\nimport static org.junit.Assert.*;\n\npublic class ControlledTestGttRegressionTest {\n    @Test public void controlledBrokerTestUsesLegacyFivePaiseTick() {\n        assertEquals(0.05d, GrowwClient.CONTROLLED_TEST_TICK, 0.000001d);\n    }\n}\n''')

print('Applied v2.7.3 legacy single-POST controlled GTT regression restore')
