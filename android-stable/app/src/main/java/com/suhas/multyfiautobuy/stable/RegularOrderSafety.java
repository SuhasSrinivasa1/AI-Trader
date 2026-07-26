package com.suhas.multyfiautobuy.stable;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

final class RegularOrderSafety {
    private static final String CANCEL_URL = "https://api.groww.in/v1/order/cancel";

    private RegularOrderSafety() { }

    static Result cancelOpenCashOrder(String accessToken, String growwOrderId) {
        if (accessToken == null || accessToken.trim().isEmpty()) {
            return Result.failure("Access token is missing.");
        }
        if (growwOrderId == null || growwOrderId.trim().isEmpty()) {
            return Result.failure("Groww order ID is missing.");
        }
        HttpURLConnection connection = null;
        try {
            JSONObject body = new JSONObject();
            body.put("segment", "CASH");
            body.put("groww_order_id", growwOrderId.trim());
            byte[] bytes = body.toString().getBytes(StandardCharsets.UTF_8);

            connection = (HttpURLConnection) new URL(CANCEL_URL).openConnection();
            connection.setRequestMethod("POST");
            connection.setConnectTimeout(7_000);
            connection.setReadTimeout(10_000);
            connection.setUseCaches(false);
            connection.setDoOutput(true);
            connection.setRequestProperty("Accept", "application/json");
            connection.setRequestProperty("Content-Type", "application/json; charset=utf-8");
            connection.setRequestProperty("X-API-VERSION", "1.0");
            connection.setRequestProperty("Authorization", "Bearer " + accessToken.trim());
            connection.setFixedLengthStreamingMode(bytes.length);
            try (OutputStream output = connection.getOutputStream()) {
                output.write(bytes);
            }

            int code = connection.getResponseCode();
            InputStream stream = code >= 200 && code < 400
                    ? connection.getInputStream() : connection.getErrorStream();
            String response = read(stream);
            if (code < 200 || code >= 300) {
                return Result.failure("HTTP " + code + ": " + compact(response));
            }
            JSONObject payload = new JSONObject(response).optJSONObject("payload");
            String status = payload == null ? "" : payload.optString("order_status", "");
            return Result.success(status.isEmpty() ? "Cancellation accepted." : status);
        } catch (Exception e) {
            String message = e.getMessage();
            return Result.failure(message == null ? e.getClass().getSimpleName() : message);
        } finally {
            if (connection != null) connection.disconnect();
        }
    }

    private static String read(InputStream stream) {
        if (stream == null) return "";
        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(stream, StandardCharsets.UTF_8))) {
            StringBuilder out = new StringBuilder();
            String line;
            while ((line = reader.readLine()) != null && out.length() < 10_000) {
                out.append(line);
            }
            return out.toString();
        } catch (Exception ignored) {
            return "";
        }
    }

    private static String compact(String text) {
        String value = text == null ? "" : text.replace('\n', ' ').replace('\r', ' ').trim();
        return value.length() <= 300 ? value : value.substring(0, 300) + "…";
    }

    static final class Result {
        final boolean success;
        final String message;

        private Result(boolean success, String message) {
            this.success = success;
            this.message = message;
        }

        static Result success(String message) { return new Result(true, message); }
        static Result failure(String message) { return new Result(false, message); }
    }
}
