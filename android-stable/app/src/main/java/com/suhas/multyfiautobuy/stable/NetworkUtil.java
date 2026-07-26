package com.suhas.multyfiautobuy.stable;

import android.content.Context;
import android.net.ConnectivityManager;
import android.net.Network;
import android.net.NetworkCapabilities;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

final class NetworkUtil {
    private static final String[] IP_ENDPOINTS = {
            "https://api.ipify.org",
            "https://checkip.amazonaws.com"
    };

    private NetworkUtil() { }

    static boolean isNetworkAvailable(Context context) {
        ConnectivityManager manager = (ConnectivityManager) context.getSystemService(Context.CONNECTIVITY_SERVICE);
        if (manager == null) return false;
        Network network = manager.getActiveNetwork();
        if (network == null) return false;
        NetworkCapabilities capabilities = manager.getNetworkCapabilities(network);
        return capabilities != null
                && capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
                && capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED);
    }

    static boolean isWifiActive(Context context) {
        ConnectivityManager manager = (ConnectivityManager) context.getSystemService(Context.CONNECTIVITY_SERVICE);
        if (manager == null) return false;
        Network network = manager.getActiveNetwork();
        if (network == null) return false;
        NetworkCapabilities capabilities = manager.getNetworkCapabilities(network);
        return capabilities != null
                && capabilities.hasTransport(NetworkCapabilities.TRANSPORT_WIFI)
                && capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET);
    }

    static boolean isVpnActive(Context context) {
        ConnectivityManager manager = (ConnectivityManager) context.getSystemService(Context.CONNECTIVITY_SERVICE);
        if (manager == null) return false;
        Network network = manager.getActiveNetwork();
        if (network == null) return false;
        NetworkCapabilities capabilities = manager.getNetworkCapabilities(network);
        return capabilities != null
                && capabilities.hasTransport(NetworkCapabilities.TRANSPORT_VPN)
                && capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET);
    }

    static String connectionLabel(Context context) {
        if (isVpnActive(context)) return "VPN";
        if (isWifiActive(context)) return "Wi-Fi";
        return isNetworkAvailable(context) ? "mobile/other network" : "offline";
    }

    static String fetchPublicIp() throws Exception {
        Exception last = null;
        for (String endpoint : IP_ENDPOINTS) {
            try {
                String value = fetchText(endpoint);
                if (isPlausibleIp(value)) return value;
                last = new IllegalStateException("Invalid IP response from " + endpoint);
            } catch (Exception e) {
                last = e;
            }
        }
        throw last == null ? new IllegalStateException("Public IP could not be detected") : last;
    }

    private static String fetchText(String endpoint) throws Exception {
        HttpURLConnection connection = (HttpURLConnection) new URL(endpoint).openConnection();
        connection.setRequestMethod("GET");
        connection.setConnectTimeout(5_000);
        connection.setReadTimeout(5_000);
        connection.setUseCaches(false);
        connection.setRequestProperty("Accept", "text/plain");
        int code = connection.getResponseCode();
        if (code < 200 || code >= 300) {
            connection.disconnect();
            throw new IllegalStateException("IP service HTTP " + code);
        }
        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(connection.getInputStream(), StandardCharsets.UTF_8))) {
            String value = reader.readLine();
            if (value == null || value.trim().isEmpty()) {
                throw new IllegalStateException("Empty IP response");
            }
            return value.trim();
        } finally {
            connection.disconnect();
        }
    }

    private static boolean isPlausibleIp(String value) {
        if (value == null) return false;
        String clean = value.trim();
        return clean.matches("[0-9a-fA-F:.]{3,64}");
    }
}
