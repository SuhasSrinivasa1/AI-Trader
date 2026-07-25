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

    static String fetchPublicIp() throws Exception {
        HttpURLConnection connection = (HttpURLConnection) new URL("https://api.ipify.org").openConnection();
        connection.setRequestMethod("GET");
        connection.setConnectTimeout(6_000);
        connection.setReadTimeout(6_000);
        connection.setUseCaches(false);
        connection.setRequestProperty("Accept", "text/plain");
        int code = connection.getResponseCode();
        if (code < 200 || code >= 300) throw new IllegalStateException("IP service HTTP " + code);
        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(connection.getInputStream(), StandardCharsets.UTF_8))) {
            String value = reader.readLine();
            if (value == null || value.trim().isEmpty()) throw new IllegalStateException("Empty IP response");
            return value.trim();
        } finally {
            connection.disconnect();
        }
    }
}
