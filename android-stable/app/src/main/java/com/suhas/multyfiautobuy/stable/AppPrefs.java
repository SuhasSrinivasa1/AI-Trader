package com.suhas.multyfiautobuy.stable;

import android.content.Context;
import android.content.SharedPreferences;

import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.HashSet;
import java.util.Locale;
import java.util.Set;
import java.util.TimeZone;

final class AppPrefs {
    static final String MULTYFI_PACKAGE = "com.multyfi.invest";
    static final int QUANTITY = 100;
    static final int MAX_BUYS_PER_DAY = 3;
    static final double MAX_ORDER_VALUE = 500_000d;
    static final long MAX_SIGNAL_AGE_MS = 180_000L;
    static final long IP_VERIFICATION_MAX_AGE_MS = 24L * 60L * 60L * 1000L;

    private static final String FILE = "stable_prefs";
    private static final String K_ARMED = "armed";
    private static final String K_STATIC_CONFIRMED = "static_confirmed";
    private static final String K_EXPECTED_IP = "expected_ip";
    private static final String K_IP_VERIFIED_AT = "ip_verified_at";
    private static final String K_AUTH_VERIFIED_DATE = "auth_verified_date";
    private static final String K_UCC = "ucc";
    private static final String K_PARSER_TEST = "parser_test";
    private static final String K_LOG = "audit_log";
    private static final String K_PROCESSED_PREFIX = "processed_";
    private static final String K_COUNT_PREFIX = "count_";

    private AppPrefs() { }

    private static SharedPreferences prefs(Context context) {
        return context.getSharedPreferences(FILE, Context.MODE_PRIVATE);
    }

    static boolean isArmed(Context context) {
        return prefs(context).getBoolean(K_ARMED, false);
    }

    static void setArmed(Context context, boolean value) {
        prefs(context).edit().putBoolean(K_ARMED, value).apply();
    }

    static boolean isStaticConfirmed(Context context) {
        return prefs(context).getBoolean(K_STATIC_CONFIRMED, false);
    }

    static void setStaticConfirmed(Context context, boolean value) {
        prefs(context).edit().putBoolean(K_STATIC_CONFIRMED, value).apply();
    }

    static String expectedIp(Context context) {
        return prefs(context).getString(K_EXPECTED_IP, "").trim();
    }

    static void setExpectedIp(Context context, String value) {
        prefs(context).edit().putString(K_EXPECTED_IP, value == null ? "" : value.trim()).apply();
    }

    static long ipVerifiedAt(Context context) {
        return prefs(context).getLong(K_IP_VERIFIED_AT, 0L);
    }

    static void setIpVerifiedAt(Context context, long value) {
        prefs(context).edit().putLong(K_IP_VERIFIED_AT, value).apply();
    }

    static boolean isIpRecentlyVerified(Context context) {
        long at = ipVerifiedAt(context);
        return at > 0L && System.currentTimeMillis() - at <= IP_VERIFICATION_MAX_AGE_MS;
    }

    static String authVerifiedDate(Context context) {
        return prefs(context).getString(K_AUTH_VERIFIED_DATE, "");
    }

    static void setAuthVerified(Context context, String ucc) {
        prefs(context).edit()
                .putString(K_AUTH_VERIFIED_DATE, istDate())
                .putString(K_UCC, ucc == null ? "" : ucc)
                .apply();
    }

    static String ucc(Context context) {
        return prefs(context).getString(K_UCC, "");
    }

    static boolean isAuthVerifiedToday(Context context) {
        return istDate().equals(authVerifiedDate(context));
    }

    static boolean parserTestPassed(Context context) {
        return prefs(context).getBoolean(K_PARSER_TEST, false);
    }

    static void setParserTestPassed(Context context, boolean value) {
        prefs(context).edit().putBoolean(K_PARSER_TEST, value).apply();
    }

    static synchronized boolean isProcessed(Context context, String eventId) {
        Set<String> values = prefs(context).getStringSet(K_PROCESSED_PREFIX + istDate(), new HashSet<>());
        return values.contains(eventId);
    }

    static synchronized void markProcessed(Context context, String eventId) {
        String key = K_PROCESSED_PREFIX + istDate();
        Set<String> values = new HashSet<>(prefs(context).getStringSet(key, new HashSet<>()));
        values.add(eventId);
        prefs(context).edit().putStringSet(key, values).apply();
    }

    static int dailyBuyCount(Context context) {
        return prefs(context).getInt(K_COUNT_PREFIX + istDate(), 0);
    }

    static void incrementDailyBuyCount(Context context) {
        String key = K_COUNT_PREFIX + istDate();
        prefs(context).edit().putInt(key, dailyBuyCount(context) + 1).apply();
    }

    static synchronized void log(Context context, String status, String message) {
        String existing = prefs(context).getString(K_LOG, "");
        String row = nowIst() + "  •  " + status + "\n" + clean(message) + "\n\n";
        String combined = row + existing;
        if (combined.length() > 14_000) combined = combined.substring(0, 14_000);
        prefs(context).edit().putString(K_LOG, combined).apply();
    }

    static String auditLog(Context context) {
        String value = prefs(context).getString(K_LOG, "").trim();
        return value.isEmpty() ? "No events yet." : value;
    }

    static void clearLog(Context context) {
        prefs(context).edit().putString(K_LOG, "").apply();
    }

    static String istDate() {
        SimpleDateFormat format = new SimpleDateFormat("yyyy-MM-dd", Locale.US);
        format.setTimeZone(TimeZone.getTimeZone("Asia/Kolkata"));
        return format.format(new Date());
    }

    static String compactIstDate() {
        SimpleDateFormat format = new SimpleDateFormat("yyMMdd", Locale.US);
        format.setTimeZone(TimeZone.getTimeZone("Asia/Kolkata"));
        return format.format(new Date());
    }

    private static String nowIst() {
        SimpleDateFormat format = new SimpleDateFormat("dd MMM, HH:mm:ss", Locale.US);
        format.setTimeZone(TimeZone.getTimeZone("Asia/Kolkata"));
        return format.format(new Date()) + " IST";
    }

    private static String clean(String message) {
        if (message == null) return "";
        String value = message.replace('\r', ' ').trim();
        return value.length() <= 700 ? value : value.substring(0, 700) + "…";
    }
}
