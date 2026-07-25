package com.suhas.multyfiautobuy.stable;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
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
            HttpResult http = request("POST", API_BASE + "/token/api/access", apiKey.trim(), body);
            if (!http.isSuccess()) return AuthResult.failure(http.message());

            JSONObject json = new JSONObject(http.body);
            String token = json.optString("token", "");
            if (token.isEmpty()) {
                JSONObject payload = json.optJSONObject("payload");
                if (payload != null) token = payload.optString("token", "");
            }
            if (token.isEmpty()) {
                return AuthResult.failure("Groww authentication succeeded but returned no access token.");
            }
            return AuthResult.success(token);
        } catch (Exception e) {
            return AuthResult.failure("Authentication error: " + safeMessage(e));
        }
    }

    static ApiResult verifyProfile(String accessToken) {
        if (accessToken == null || accessToken.trim().isEmpty()) {
            return ApiResult.failure("", "Access token is missing.", 0);
        }
        try {
            HttpResult http = request("GET", API_BASE + "/user/detail", accessToken.trim(), null);
            if (!http.isSuccess()) return apiFailure(http);
            JSONObject json = new JSONObject(http.body);
            JSONObject payload = json.optJSONObject("payload");
            if (payload == null) {
                return ApiResult.failure("", "Groww profile response had no payload.", http.code);
            }
            boolean nseEnabled = payload.optBoolean("nse_enabled", false);
            String ucc = payload.optString("ucc", "");
            if (!nseEnabled) {
                return ApiResult.failure("", "NSE trading is not enabled for this Groww account.", http.code);
            }
            return ApiResult.success(ucc,
                    "Groww account verified" + (ucc.isEmpty() ? "." : " (UCC " + ucc + ")."),
                    http.code);
        } catch (Exception e) {
            return ApiResult.failure("", "Profile verification error: " + safeMessage(e), 0);
        }
    }

    static ApiResult createProtectedGtt(String accessToken, SignalParser.ParsedSignal signal, int quantity) {
        if (accessToken == null || accessToken.trim().isEmpty()) {
            return ApiResult.failure("", "Access token is missing.", 0);
        }
        if (signal == null) return ApiResult.failure("", "Signal is missing.", 0);
        if (!AppPrefs.isValidQuantity(quantity)) {
            return ApiResult.failure("", "Configured quantity is invalid.", 0);
        }
        try {
            JSONObject order = new JSONObject();
            order.put("order_type", "LIMIT");
            order.put("price", price(signal.maxBuyPrice));
            order.put("transaction_type", "BUY");

            JSONObject target = new JSONObject();
            target.put("trigger_price", price(signal.targetPrice));
            target.put("order_type", "LIMIT");
            target.put("price", price(signal.targetPrice));

            JSONObject stopLoss = new JSONObject();
            stopLoss.put("trigger_price", price(signal.stopLossPrice));
            stopLoss.put("order_type", "SL_M");
            stopLoss.put("price", JSONObject.NULL);

            JSONObject childLegs = new JSONObject();
            childLegs.put("target", target);
            childLegs.put("stop_loss", stopLoss);

            JSONObject body = new JSONObject();
            body.put("reference_id", signal.referenceId);
            body.put("smart_order_type", "GTT");
            body.put("segment", "CASH");
            body.put("trading_symbol", signal.symbol);
            body.put("quantity", quantity);
            body.put("trigger_price", price(signal.triggerPrice));
            body.put("trigger_direction", "UP");
            body.put("order", order);
            body.put("child_legs", childLegs);
            body.put("product_type", "CNC");
            body.put("exchange", "NSE");
            body.put("duration", "DAY");

            HttpResult http = request("POST", API_BASE + "/order-advance/create",
                    accessToken.trim(), body);
            if (!http.isSuccess()) return apiFailure(http);

            JSONObject json = new JSONObject(http.body);
            JSONObject payload = json.optJSONObject("payload");
            String smartOrderId = payload == null ? "" : payload.optString("smart_order_id", "");
            String status = payload == null ? "" : payload.optString("status", "");
            JSONObject confirmedChildLegs = payload == null ? null : payload.optJSONObject("child_legs");

            // Never leave an entry-only GTT active when Groww did not confirm target/SL child legs.
            if (confirmedChildLegs == null) {
                if (!smartOrderId.isEmpty()) {
                    ApiResult cancellation = cancelGtt(accessToken.trim(), smartOrderId);
                    String detail = cancellation.success
                            ? "Groww did not confirm target/stop-loss child legs; the GTT was cancelled automatically."
                            : "CRITICAL: Groww did not confirm child legs and automatic cancellation failed: "
                                    + cancellation.message;
                    return ApiResult.failure("PROTECTION_NOT_CONFIRMED", detail, http.code);
                }
                return ApiResult.failure("PROTECTION_NOT_CONFIRMED",
                        "Groww accepted the request but did not confirm target/stop-loss child legs.",
                        http.code);
            }

            String message = "Groww accepted protected GTT BUY"
                    + (smartOrderId.isEmpty() ? "" : " " + smartOrderId)
                    + (status.isEmpty() ? "." : " — " + status + ".")
                    + " Target and stop-loss child legs confirmed.";
            return ApiResult.success(smartOrderId, message, http.code);
        } catch (Exception e) {
            return ApiResult.failure("", "Protected GTT request error: " + safeMessage(e), 0);
        }
    }

    private static ApiResult cancelGtt(String accessToken, String smartOrderId) {
        try {
            HttpResult http = request("POST",
                    API_BASE + "/order-advance/cancel/CASH/GTT/" + smartOrderId,
                    accessToken, null);
            if (!http.isSuccess()) return apiFailure(http);
            return ApiResult.success(smartOrderId, "GTT cancelled.", http.code);
        } catch (Exception e) {
            return ApiResult.failure("", "Cancellation error: " + safeMessage(e), 0);
        }
    }

    private static ApiResult apiFailure(HttpResult http) {
        String code = "";
        String message = http.message();
        try {
            JSONObject json = new JSONObject(http.body);
            JSONObject error = json.optJSONObject("error");
            if (error != null) {
                code = error.optString("code", "");
                String apiMessage = error.optString("message", "");
                if (!apiMessage.isEmpty()) message = apiMessage;
            }
        } catch (Exception ignored) { }
        return ApiResult.failure(code, message, http.code);
    }

    private static HttpResult request(String method, String url, String bearer, JSONObject body)
            throws Exception {
        HttpURLConnection connection = (HttpURLConnection) new URL(url).openConnection();
        connection.setRequestMethod(method);
        connection.setConnectTimeout(7_000);
        connection.setReadTimeout(10_000);
        connection.setUseCaches(false);
        connection.setRequestProperty("Accept", "application/json");
        connection.setRequestProperty("X-API-VERSION", "1.0");
        connection.setRequestProperty("Authorization", "Bearer " + bearer);
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
            while ((line = reader.readLine()) != null && out.length() < 20_000) out.append(line);
            return out.toString();
        } catch (Exception ignored) {
            return "";
        }
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
        final String errorCode;
        final String message;
        final int httpCode;

        private ApiResult(boolean success, String id, String errorCode,
                          String message, int httpCode) {
            this.success = success;
            this.id = id;
            this.errorCode = errorCode;
            this.message = message;
            this.httpCode = httpCode;
        }

        static ApiResult success(String id, String message, int httpCode) {
            return new ApiResult(true, id, "", message, httpCode);
        }

        static ApiResult failure(String errorCode, String message, int httpCode) {
            return new ApiResult(false, "", errorCode, message, httpCode);
        }
    }

    private static final class HttpResult {
        final int code;
        final String body;

        HttpResult(int code, String body) {
            this.code = code;
            this.body = body == null ? "" : body;
        }

        boolean isSuccess() {
            return code >= 200 && code < 300;
        }

        String message() {
            String clean = body.replace('\n', ' ').replace('\r', ' ').trim();
            if (clean.isEmpty()) return "HTTP " + code;
            if (clean.length() > 300) clean = clean.substring(0, 300) + "…";
            return "HTTP " + code + ": " + clean;
        }
    }
}
