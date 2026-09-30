package com.multify.autotrader;

import android.os.Handler;
import android.os.Looper;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

public class BackendClient {
    public interface Callback { void done(boolean ok, String response); }

    public static void postNotification(String baseUrl, String deviceKey, String sourcePackage, String appLabel,
                                        String title, String text, String bigText, long postedAtMs, Callback cb) {
        new Thread(() -> {
            boolean ok = false;
            String response;
            HttpURLConnection conn = null;
            try {
                URL url = new URL(baseUrl.replaceAll("/$", "") + "/api/v1/notifications");
                conn = (HttpURLConnection) url.openConnection();
                conn.setConnectTimeout(5000);
                conn.setReadTimeout(10000);
                conn.setRequestMethod("POST");
                conn.setDoOutput(true);
                conn.setRequestProperty("Content-Type", "application/json");
                conn.setRequestProperty("Accept", "application/json");
                conn.setRequestProperty("X-Device-Key", deviceKey);
                JSONObject j = new JSONObject();
                j.put("source_package", sourcePackage == null ? "" : sourcePackage);
                j.put("app_label", appLabel == null ? "" : appLabel);
                j.put("title", title == null ? "" : title);
                j.put("text", text == null ? "" : text);
                j.put("big_text", bigText == null ? "" : bigText);
                j.put("posted_at_ms", Math.max(0, postedAtMs));
                byte[] bytes = j.toString().getBytes(StandardCharsets.UTF_8);
                try (OutputStream os = conn.getOutputStream()) { os.write(bytes); }
                int code = conn.getResponseCode();
                ok = code >= 200 && code < 300;
                InputStream is = ok ? conn.getInputStream() : conn.getErrorStream();
                response = readAll(is);
            } catch (Exception e) {
                response = e.getClass().getSimpleName() + ": " + e.getMessage();
            } finally {
                if (conn != null) conn.disconnect();
            }
            boolean finalOk = ok;
            String finalResponse = response;
            new Handler(Looper.getMainLooper()).post(() -> cb.done(finalOk, finalResponse));
        }).start();
    }

    private static String readAll(InputStream in) throws Exception {
        if (in == null) return "";
        StringBuilder s = new StringBuilder();
        try (BufferedReader r = new BufferedReader(new InputStreamReader(in, StandardCharsets.UTF_8))) {
            String line;
            while ((line = r.readLine()) != null) s.append(line);
        }
        return s.toString();
    }
}
