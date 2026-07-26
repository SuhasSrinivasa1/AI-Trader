package com.suhas.multyfiautobuy.stable;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.Locale;

final class GrowwClient {
    private static final String API_BASE = "https://api.groww.in/v1";

    private GrowwClient() { }

    static AuthResult authenticate(String apiKey, String base32Secret) {
        if (apiKey == null || apiKey.trim().isEmpty()) {
            return AuthResult.failure("Groww API key is missing.");
        }
        if (base32Secret == null || base32Secret.trim().isEmpty()) {
            return AuthResult.failure("Groww TOTP secret is missing.");
        }
        try {
            JSONObject body = new JSONObject();
            body.put("key_type", "totp");
            body.put("totp", Totp.generate(base32Secret));
            HttpResult http = request("POST", API_BASE + "/token/api/access",
                    apiKey.trim(), body);
            if (!http.isSuccess()) return AuthResult.failure(http.message());
            JSONObject json = new JSONObject(http.body);
            String token = json.optString("token", "");
            JSONObject payload = json.optJSONObject("payload");
            if (token.isEmpty() && payload != null) token = payload.optString("token", "");
            if (token.isEmpty()) {
                return AuthResult.failure("Groww authentication returned no access token.");
            }
            return AuthResult.success(token);
        } catch (Exception e) {
            return AuthResult.failure("Authentication error: " + safeMessage(e));
        }
    }

    static ApiResult verifyProfile(String accessToken) {
        try {
            HttpResult http = request("GET", API_BASE + "/user/detail", accessToken, null);
            if (!http.isSuccess()) return apiFailure(http);
            JSONObject payload = new JSONObject(http.body).optJSONObject("payload");
            if (payload == null) {
                return ApiResult.failure("", "Groww profile response had no payload.", http.code);
            }
            if (!payload.optBoolean("nse_enabled", false)) {
                return ApiResult.failure("", "NSE trading is not enabled.", http.code);
            }
            if (!payload.optBoolean("ddpi_enabled", false)) {
                return ApiResult.failure("DDPI_REQUIRED",
                        "DDPI is not enabled. Autonomous CNC exits may require TPIN/OTP, so the app cannot arm.",
                        http.code);
            }
            String ucc = payload.optString("ucc", "");
            return ApiResult.success(ucc,
                    "Groww account and DDPI verified" + (ucc.isEmpty() ? "." : " (UCC " + ucc + ")."),
                    http.code);
        } catch (Exception e) {
            return ApiResult.failure("", "Profile verification error: " + safeMessage(e), 0);
        }
    }

    static ApiResult placeImmediateEntryLimit(String accessToken,
                                              SignalParser.ParsedSignal signal,
                                              int quantity,
                                              String productType) {
        if (signal == null || quantity <= 0) {
            return ApiResult.failure("", "A valid signal and positive quantity are required.", 0);
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
            body.put("order_reference_id", signal.referenceId);
            HttpResult http = request("POST", API_BASE + "/order/create", accessToken, body);
            if (!http.isSuccess()) return apiFailure(http);
            JSONObject payload = new JSONObject(http.body).optJSONObject("payload");
            if (payload == null) {
                return ApiResult.failure("ENTRY_NO_PAYLOAD",
                        "Groww accepted the entry request but returned no payload.", http.code);
            }
            String id = payload.optString("groww_order_id", "");
            String status = payload.optString("order_status", "");
            String reference = payload.optString("order_reference_id", signal.referenceId);
            if (id.isEmpty()) {
                return ApiResult.failure("ENTRY_NO_ORDER_ID",
                        "Groww accepted the entry request but returned no order ID.", http.code);
            }
            if (isRejectedRegularStatus(status)) {
                return ApiResult.failure("ENTRY_REJECTED",
                        "Groww rejected the entry order: " + status + " "
                                + payload.optString("remark", ""), http.code);
            }
            return ApiResult.success(id, reference,
                    "Immediate " + productType + " LIMIT BUY accepted: " + id
                            + " • status " + (status.isEmpty() ? "submitted" : status)
                            + " • cap ₹" + price(signal.maxBuyPrice) + ".",
                    http.code);
        } catch (Exception e) {
            return ApiResult.failure("", "Immediate entry error: " + safeMessage(e), 0);
        }
    }

    static ApiResult createEntryGtt(String accessToken, SignalParser.ParsedSignal signal,
                                    int quantity, double currentLtp) {
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
                mode = "Price is above the allowed cap; GTT waits for a pullback to ₹" + price(trigger) + ".";
            } else if (currentLtp < signal.entryLow) {
                trigger = signal.entryLow;
                direction = "UP";
                mode = "Price is below the recommendation; GTT triggers at ₹" + price(trigger) + ".";
            } else {
                trigger = Math.min(signal.maxBuyPrice,
                        SignalParser.ceilToTick(currentLtp + 0.05d, 0.05d));
                direction = "UP";
                mode = "Rapid-catch GTT one tick above LTP ₹" + price(currentLtp)
                        + " with maximum limit ₹" + price(signal.maxBuyPrice) + ".";
            }

            JSONObject order = new JSONObject();
            order.put("order_type", "LIMIT");
            order.put("price", price(signal.maxBuyPrice));
            order.put("transaction_type", "BUY");
            JSONObject body = gttBase(signal.referenceId, signal.symbol, quantity,
                    trigger, direction, order, signal.productType);
            HttpResult http = request("POST", API_BASE + "/order-advance/create",
                    accessToken, body);
            if (!http.isSuccess()) return apiFailure(http);
            JSONObject payload = new JSONObject(http.body).optJSONObject("payload");
            String id = payload == null ? "" : payload.optString("smart_order_id", "");
            if (id.isEmpty()) {
                return ApiResult.failure("",
                        "Groww accepted entry GTT but returned no smart-order ID.", http.code);
            }
            SmartStatus confirmed = confirmGtt(accessToken, id);
            if (!confirmed.success || !isLiveSmartStatus(confirmed.status)) {
                cancelGtt(accessToken, id);
                return ApiResult.failure("ENTRY_NOT_CONFIRMED",
                        "Entry GTT was not confirmed ACTIVE and was cancelled. Status: "
                                + confirmed.status + " " + confirmed.message, http.code);
            }
            return ApiResult.success(id, "Entry GTT confirmed ACTIVE: " + id + ". " + mode,
                    http.code);
        } catch (Exception e) {
            return ApiResult.failure("", "Entry GTT error: " + safeMessage(e), 0);
        }
    }

    static ApiResult createStopLossGtt(String accessToken, Strategy strategy,
                                       int quantity, int legNumber) {
        try {
            String reference = reference("SL", strategy.eventId, legNumber);
            JSONObject order = new JSONObject();
            order.put("order_type", "MARKET");
            order.put("price", JSONObject.NULL);
            order.put("transaction_type", "SELL");
            JSONObject body = gttBase(reference, strategy.symbol, quantity,
                    strategy.stopLossPrice, "DOWN", order, strategy.productType);
            HttpResult http = request("POST", API_BASE + "/order-advance/create",
                    accessToken, body);
            if (!http.isSuccess()) return apiFailure(http);
            JSONObject payload = new JSONObject(http.body).optJSONObject("payload");
            String id = payload == null ? "" : payload.optString("smart_order_id", "");
            if (id.isEmpty()) {
                return ApiResult.failure("",
                        "Groww accepted stop-loss GTT but returned no ID.", http.code);
            }
            SmartStatus confirmed = confirmGtt(accessToken, id);
            if (!confirmed.success || !isLiveSmartStatus(confirmed.status)) {
                cancelGtt(accessToken, id);
                return ApiResult.failure("STOP_NOT_CONFIRMED",
                        "Stop-loss GTT was not confirmed ACTIVE and was cancelled. Status: "
                                + confirmed.status, http.code);
            }
            return ApiResult.success(id, "Stop-loss GTT confirmed ACTIVE for " + quantity
                    + " " + strategy.productType + " shares: " + id + ".", http.code);
        } catch (Exception e) {
            return ApiResult.failure("", "Stop-loss GTT error: " + safeMessage(e), 0);
        }
    }

    static ApiResult cancelGtt(String accessToken, String smartOrderId) {
        try {
            HttpResult http = request("POST",
                    API_BASE + "/order-advance/cancel/CASH/GTT/" + enc(smartOrderId),
                    accessToken, null);
            if (!http.isSuccess()) return apiFailure(http);
            JSONObject payload = new JSONObject(http.body).optJSONObject("payload");
            String status = payload == null ? "" : payload.optString("status", "");
            return ApiResult.success(smartOrderId,
                    "GTT cancellation response: " + status + ".", http.code);
        } catch (Exception e) {
            return ApiResult.failure("", "GTT cancellation error: " + safeMessage(e), 0);
        }
    }

    static SmartStatus getGtt(String accessToken, String smartOrderId) {
        try {
            HttpResult http = request("GET",
                    API_BASE + "/order-advance/status/CASH/GTT/internal/" + enc(smartOrderId),
                    accessToken, null);
            if (!http.isSuccess()) return SmartStatus.failure(http.message());
            JSONObject payload = new JSONObject(http.body).optJSONObject("payload");
            if (payload == null) return SmartStatus.failure("Smart-order response had no payload.");
            return SmartStatus.success(payload.optString("status", ""),
                    payload.optString("triggered_at", ""),
                    payload.optString("remark", ""));
        } catch (Exception e) {
            return SmartStatus.failure("Smart-order status error: " + safeMessage(e));
        }
    }

    static OrderStatus getOrderByReference(String accessToken, String referenceId) {
        try {
            HttpResult http = request("GET",
                    API_BASE + "/order/status/reference/" + enc(referenceId) + "?segment=CASH",
                    accessToken, null);
            if (!http.isSuccess()) return OrderStatus.failure(http.code, http.message());
            JSONObject payload = new JSONObject(http.body).optJSONObject("payload");
            if (payload == null) return OrderStatus.failure(http.code,
                    "Order response had no payload.");
            return OrderStatus.success(payload.optString("groww_order_id", ""),
                    payload.optString("order_status", ""),
                    payload.optInt("filled_quantity", 0), payload.optString("remark", ""));
        } catch (Exception e) {
            return OrderStatus.failure(0,
                    "Order-reference status error: " + safeMessage(e));
        }
    }

    static IntResult getNetPositionQuantity(String accessToken, String symbol,
                                            String productType) {
        try {
            String url = API_BASE + "/positions/trading-symbol?trading_symbol="
                    + enc(symbol) + "&segment=CASH";
            HttpResult http = request("GET", url, accessToken, null);
            if (!http.isSuccess()) return IntResult.failure(http.message());
            JSONObject payload = new JSONObject(http.body).optJSONObject("payload");
            if (payload == null) return IntResult.success(0);
            JSONArray positions = payload.optJSONArray("positions");
            if (positions == null) return IntResult.success(0);
            int quantity = 0;
            for (int i = 0; i < positions.length(); i++) {
                JSONObject position = positions.optJSONObject(i);
                if (position == null) continue;
                String product = position.optString("product",
                        position.optString("product_type", ""));
                if (symbol.equalsIgnoreCase(position.optString("trading_symbol", ""))
                        && productType.equalsIgnoreCase(product)) {
                    quantity += position.optInt("quantity", 0);
                }
            }
            return IntResult.success(quantity);
        } catch (Exception e) {
            return IntResult.failure("Position error: " + safeMessage(e));
        }
    }

    static DoubleResult getLtp(String accessToken, String symbol) {
        try {
            String key = "NSE_" + symbol;
            String url = API_BASE + "/live-data/ltp?segment=CASH&exchange_symbols=" + enc(key);
            HttpResult http = request("GET", url, accessToken, null);
            if (!http.isSuccess()) return DoubleResult.failure(http.message());
            JSONObject payload = new JSONObject(http.body).optJSONObject("payload");
            if (payload == null || !payload.has(key)) {
                return DoubleResult.failure("LTP response did not contain " + key + ".");
            }
            return DoubleResult.success(payload.optDouble(key, -1d));
        } catch (Exception e) {
            return DoubleResult.failure("LTP error: " + safeMessage(e));
        }
    }

    static ApiResult placeTargetMarketSell(String accessToken, Strategy strategy,
                                           int quantity) {
        return placeMarketSell(accessToken, strategy, quantity, "TG",
                "Target-triggered");
    }

    static ApiResult placeTimedMarketSell(String accessToken, Strategy strategy,
                                          int quantity) {
        return placeMarketSell(accessToken, strategy, quantity, "TM",
                "Intraday time-exit");
    }

    static ApiResult placeEarlyExitMarketSell(String accessToken, Strategy strategy,
                                              int quantity) {
        return placeMarketSell(accessToken, strategy, quantity, "EX",
                "Multyfi early-exit");
    }

    private static ApiResult placeMarketSell(String accessToken, Strategy strategy,
                                             int quantity, String prefix, String label) {
        if (quantity <= 0) return ApiResult.failure("", "Sell quantity must be positive.", 0);
        try {
            String reference = reference(prefix, strategy.eventId, 0);
            JSONObject body = new JSONObject();
            body.put("trading_symbol", strategy.symbol);
            body.put("quantity", quantity);
            body.put("price", 0);
            body.put("trigger_price", 0);
            body.put("validity", "DAY");
            body.put("exchange", "NSE");
            body.put("segment", "CASH");
            body.put("product", strategy.productType);
            body.put("order_type", "MARKET");
            body.put("transaction_type", "SELL");
            body.put("order_reference_id", reference);
            HttpResult http = request("POST", API_BASE + "/order/create", accessToken, body);
            if (!http.isSuccess()) return apiFailure(http);
            JSONObject payload = new JSONObject(http.body).optJSONObject("payload");
            String id = payload == null ? "" : payload.optString("groww_order_id", "");
            if (id.isEmpty()) {
                return ApiResult.failure("",
                        "Groww accepted sell but returned no order ID.", http.code);
            }
            return ApiResult.success(id, reference, label + " " + strategy.productType
                    + " MARKET sell submitted: " + id + ".", http.code);
        } catch (Exception e) {
            return ApiResult.failure("", label + " sell error: " + safeMessage(e), 0);
        }
    }

    private static JSONObject gttBase(String reference, String symbol, int quantity,
                                      double triggerPrice, String direction,
                                      JSONObject order, String productType) throws Exception {
        JSONObject body = new JSONObject();
        body.put("reference_id", reference);
        body.put("smart_order_type", "GTT");
        body.put("segment", "CASH");
        body.put("trading_symbol", symbol);
        body.put("quantity", quantity);
        body.put("trigger_price", price(triggerPrice));
        body.put("trigger_direction", direction);
        body.put("order", order);
        body.put("product_type", productType);
        body.put("exchange", "NSE");
        body.put("duration", "DAY");
        return body;
    }

    private static SmartStatus confirmGtt(String accessToken, String smartOrderId) {
        SmartStatus status = SmartStatus.failure("Not checked.");
        for (int i = 0; i < 3; i++) {
            status = getGtt(accessToken, smartOrderId);
            if (status.success && !status.status.trim().isEmpty()) return status;
            try { Thread.sleep(250L); }
            catch (InterruptedException e) { Thread.currentThread().interrupt(); break; }
        }
        return status;
    }

    private static boolean isLiveSmartStatus(String status) {
        return "ACTIVE".equalsIgnoreCase(status) || "OPEN".equalsIgnoreCase(status)
                || "PENDING".equalsIgnoreCase(status) || "TRIGGERED".equalsIgnoreCase(status)
                || "COMPLETED".equalsIgnoreCase(status);
    }

    private static boolean isRejectedRegularStatus(String status) {
        return "REJECTED".equalsIgnoreCase(status)
                || "FAILED".equalsIgnoreCase(status)
                || "CANCELLED".equalsIgnoreCase(status)
                || "CANCELED".equalsIgnoreCase(status);
    }

    private static String reference(String prefix, String eventId, int suffix) {
        String clean = eventId == null ? "00000000000000"
                : eventId.replaceAll("[^A-Za-z0-9]", "");
        if (clean.length() > 14) clean = clean.substring(0, 14);
        return prefix + clean.toUpperCase(Locale.US) + suffix;
    }

    private static ApiResult apiFailure(HttpResult http) {
        String code = "";
        String message = http.message();
        try {
            JSONObject root = new JSONObject(http.body);
            JSONObject error = root.optJSONObject("error");
            if (error != null) {
                code = error.optString("code", "");
                String apiMessage = error.optString("message", "");
                if (!apiMessage.isEmpty()) message = apiMessage;
            } else {
                code = root.optString("error_code", root.optString("code", ""));
                String apiMessage = root.optString("message", "");
                if (!apiMessage.isEmpty()) message = apiMessage;
            }
        } catch (Exception ignored) { }
        return ApiResult.failure(code, message, http.code);
    }

    private static HttpResult request(String method, String url, String bearer,
                                      JSONObject body) throws Exception {
        if (bearer == null || bearer.trim().isEmpty()) {
            return new HttpResult(401, "Access token is missing.");
        }
        HttpURLConnection connection = (HttpURLConnection) new URL(url).openConnection();
        connection.setRequestMethod(method);
        connection.setConnectTimeout(7_000);
        connection.setReadTimeout(10_000);
        connection.setUseCaches(false);
        connection.setRequestProperty("Accept", "application/json");
        connection.setRequestProperty("X-API-VERSION", "1.0");
        connection.setRequestProperty("Authorization", "Bearer " + bearer.trim());
        if (body != null) {
            byte[] bytes = body.toString().getBytes(StandardCharsets.UTF_8);
            connection.setDoOutput(true);
            connection.setRequestProperty("Content-Type", "application/json; charset=utf-8");
            connection.setFixedLengthStreamingMode(bytes.length);
            try (OutputStream output = connection.getOutputStream()) {
                output.write(bytes);
            }
        }
        int code = connection.getResponseCode();
        InputStream stream = code >= 200 && code < 400
                ? connection.getInputStream() : connection.getErrorStream();
        String response = read(stream);
        connection.disconnect();
        return new HttpResult(code, response);
    }

    private static String read(InputStream stream) {
        if (stream == null) return "";
        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(stream, StandardCharsets.UTF_8))) {
            StringBuilder out = new StringBuilder();
            String line;
            while ((line = reader.readLine()) != null && out.length() < 40_000) {
                out.append(line);
            }
            return out.toString();
        } catch (Exception ignored) { return ""; }
    }

    private static String enc(String value) throws Exception {
        return URLEncoder.encode(value == null ? "" : value,
                StandardCharsets.UTF_8.name());
    }

    private static String price(double value) {
        return String.format(Locale.US, "%.2f", value);
    }

    private static String safeMessage(Exception e) {
        String message = e.getMessage();
        return message == null || message.trim().isEmpty()
                ? e.getClass().getSimpleName() : message;
    }

    static final class AuthResult {
        final boolean success;
        final String accessToken;
        final String message;

        private AuthResult(boolean success, String accessToken, String message) {
            this.success = success;
            this.accessToken = accessToken;
            this.message = message;
        }

        static AuthResult success(String token) {
            return new AuthResult(true, token, "Groww access token generated.");
        }

        static AuthResult failure(String message) {
            return new AuthResult(false, "", message);
        }
    }

    static final class ApiResult {
        final boolean success;
        final String id;
        final String secondaryId;
        final String errorCode;
        final String message;
        final int httpCode;

        private ApiResult(boolean success, String id, String secondaryId,
                          String errorCode, String message, int httpCode) {
            this.success = success;
            this.id = id;
            this.secondaryId = secondaryId;
            this.errorCode = errorCode;
            this.message = message;
            this.httpCode = httpCode;
        }

        static ApiResult success(String id, String message, int httpCode) {
            return new ApiResult(true, id, "", "", message, httpCode);
        }

        static ApiResult success(String id, String secondaryId,
                                 String message, int httpCode) {
            return new ApiResult(true, id, secondaryId, "", message, httpCode);
        }

        static ApiResult failure(String errorCode, String message, int httpCode) {
            return new ApiResult(false, "", "", errorCode, message, httpCode);
        }
    }

    static final class SmartStatus {
        final boolean success;
        final String status;
        final String triggeredAt;
        final String message;

        private SmartStatus(boolean success, String status,
                            String triggeredAt, String message) {
            this.success = success;
            this.status = status;
            this.triggeredAt = triggeredAt;
            this.message = message;
        }

        static SmartStatus success(String status, String triggeredAt, String message) {
            return new SmartStatus(true, status, triggeredAt, message);
        }

        static SmartStatus failure(String message) {
            return new SmartStatus(false, "", "", message);
        }
    }

    static final class OrderStatus {
        final boolean success;
        final String orderId;
        final String status;
        final int filledQuantity;
        final String message;
        final int httpCode;

        private OrderStatus(boolean success, String orderId, String status,
                            int filledQuantity, String message, int httpCode) {
            this.success = success;
            this.orderId = orderId;
            this.status = status;
            this.filledQuantity = filledQuantity;
            this.message = message;
            this.httpCode = httpCode;
        }

        static OrderStatus success(String id, String status,
                                   int filled, String message) {
            return new OrderStatus(true, id, status, filled, message, 200);
        }

        static OrderStatus failure(int code, String message) {
            return new OrderStatus(false, "", "", 0, message, code);
        }
    }

    static final class IntResult {
        final boolean success;
        final int value;
        final String message;

        private IntResult(boolean success, int value, String message) {
            this.success = success;
            this.value = value;
            this.message = message;
        }

        static IntResult success(int value) { return new IntResult(true, value, ""); }
        static IntResult failure(String message) { return new IntResult(false, 0, message); }
    }

    static final class DoubleResult {
        final boolean success;
        final double value;
        final String message;

        private DoubleResult(boolean success, double value, String message) {
            this.success = success;
            this.value = value;
            this.message = message;
        }

        static DoubleResult success(double value) {
            return new DoubleResult(value > 0d, value,
                    value > 0d ? "" : "Invalid LTP.");
        }

        static DoubleResult failure(String message) {
            return new DoubleResult(false, -1d, message);
        }
    }

    private static final class HttpResult {
        final int code;
        final String body;

        HttpResult(int code, String body) {
            this.code = code;
            this.body = body == null ? "" : body;
        }

        boolean isSuccess() { return code >= 200 && code < 300; }

        String message() {
            String clean = body.replace('\n', ' ').replace('\r', ' ').trim();
            if (clean.isEmpty()) return "HTTP " + code;
            return "HTTP " + code + ": "
                    + (clean.length() <= 300 ? clean : clean.substring(0, 300) + "…");
        }
    }
}