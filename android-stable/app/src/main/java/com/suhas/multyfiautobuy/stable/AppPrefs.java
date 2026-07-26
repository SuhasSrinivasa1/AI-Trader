package com.suhas.multyfiautobuy.stable;

import android.content.Context;
import android.content.SharedPreferences;

import java.text.SimpleDateFormat;
import java.util.Calendar;
import java.util.Date;
import java.util.HashSet;
import java.util.Locale;
import java.util.Set;
import java.util.TimeZone;

final class AppPrefs {
    static final String MULTYFI_PACKAGE = "com.multyfi.invest";

    static final double DEFAULT_WINDOW_1_BUDGET = 10_000d;
    static final double DEFAULT_WINDOW_2_BUDGET = 10_000d;
    static final double DEFAULT_WINDOW_3_BUDGET = 5_000d;
    static final double MIN_TRADE_BUDGET = 1_000d;
    static final double MAX_TRADE_BUDGET = 500_000d;
    static final int MAX_COMPUTED_QUANTITY = 10_000;

    static final double DEFAULT_ENTRY_BUFFER_PERCENT = 1.5d;
    static final double MIN_ENTRY_BUFFER_PERCENT = 0d;
    static final double MAX_ENTRY_BUFFER_PERCENT = 2d;
    static final int MAX_BUYS_PER_DAY = 4;
    static final double MAX_ORDER_VALUE = 500_000d;
    static final long MAX_SIGNAL_AGE_MS = 180_000L;
    static final long MAX_EARLY_EXIT_AGE_MS = 300_000L;
    static final long IP_VERIFICATION_MAX_AGE_MS = 2L * 60L * 1000L;

    static final int WINDOW_1_START = 9 * 60;
    static final int WINDOW_1_END = 9 * 60 + 30;
    static final int WINDOW_2_END = 10 * 60;
    static final int WINDOW_3_END = 15 * 60 + 30;

    private static final TimeZone IST = TimeZone.getTimeZone("Asia/Kolkata");
    private static final String FILE = "stable_prefs";
    private static final String K_ARMED = "armed";
    private static final String K_WINDOW_1_BUDGET = "window_1_budget";
    private static final String K_WINDOW_2_BUDGET = "window_2_budget";
    private static final String K_WINDOW_3_BUDGET = "window_3_budget";
    private static final String K_ENTRY_BUFFER = "entry_buffer_percent";
    private static final String K_STATIC_CONFIRMED = "static_confirmed";
    private static final String K_EXPECTED_IP = "expected_ip";
    private static final String K_LAST_PUBLIC_IP = "last_public_ip";
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

    static double window1Budget(Context context) {
        return readBudget(context, K_WINDOW_1_BUDGET, DEFAULT_WINDOW_1_BUDGET);
    }

    static double window2Budget(Context context) {
        return readBudget(context, K_WINDOW_2_BUDGET, DEFAULT_WINDOW_2_BUDGET);
    }

    static double window3Budget(Context context) {
        return readBudget(context, K_WINDOW_3_BUDGET, DEFAULT_WINDOW_3_BUDGET);
    }

    // Compatibility helper used by older local tests and migration paths.
    static double tradeBudget(Context context) {
        return window1Budget(context);
    }

    private static double readBudget(Context context, String key, double fallback) {
        long bits = prefs(context).getLong(key, Double.doubleToRawLongBits(fallback));
        double value = Double.longBitsToDouble(bits);
        return isValidTradeBudget(value) ? value : fallback;
    }

    static boolean isValidTradeBudget(double value) {
        return !Double.isNaN(value) && !Double.isInfinite(value)
                && value >= MIN_TRADE_BUDGET && value <= MAX_TRADE_BUDGET;
    }

    static void setWindowBudgets(Context context, double first, double second, double third) {
        if (!isValidTradeBudget(first) || !isValidTradeBudget(second)
                || !isValidTradeBudget(third)) {
            throw new IllegalArgumentException("Each window amount must be between ₹1,000 and ₹5,00,000.");
        }
        prefs(context).edit()
                .putLong(K_WINDOW_1_BUDGET, Double.doubleToRawLongBits(first))
                .putLong(K_WINDOW_2_BUDGET, Double.doubleToRawLongBits(second))
                .putLong(K_WINDOW_3_BUDGET, Double.doubleToRawLongBits(third))
                .apply();
    }

    static void setTradeBudget(Context context, double value) {
        setWindowBudgets(context, value, window2Budget(context), window3Budget(context));
    }

    static int quantityForBudget(double budget, double maximumBuyPrice) {
        if (!isValidTradeBudget(budget) || maximumBuyPrice <= 0d) return 0;
        int quantity = (int) Math.floor(budget / maximumBuyPrice);
        return Math.max(0, Math.min(MAX_COMPUTED_QUANTITY, quantity));
    }

    static int quantityForBudget(Context context, double maximumBuyPrice) {
        return quantityForBudget(tradeBudget(context), maximumBuyPrice);
    }

    static TradeWindow tradeWindow(Context context, long epochMillis) {
        Calendar calendar = Calendar.getInstance(IST, Locale.US);
        calendar.setTimeInMillis(epochMillis);
        int day = calendar.get(Calendar.DAY_OF_WEEK);
        if (day == Calendar.SATURDAY || day == Calendar.SUNDAY) return null;
        int minute = calendar.get(Calendar.HOUR_OF_DAY) * 60 + calendar.get(Calendar.MINUTE);
        if (minute < WINDOW_1_START || minute > WINDOW_3_END) return null;

        if (minute < WINDOW_1_END) {
            return new TradeWindow(1, "09:00–09:30", window1Budget(context), true,
                    cutoffMillis(calendar, 10, 0));
        }
        if (minute < WINDOW_2_END) {
            return new TradeWindow(2, "09:30–10:00", window2Budget(context), false,
                    cutoffMillis(calendar, 10, 30));
        }
        return new TradeWindow(3, "10:00–15:30", window3Budget(context), false,
                cutoffMillis(calendar, 15, 25));
    }

    private static long cutoffMillis(Calendar source, int hour, int minute) {
        Calendar cutoff = (Calendar) source.clone();
        cutoff.set(Calendar.HOUR_OF_DAY, hour);
        cutoff.set(Calendar.MINUTE, minute);
        cutoff.set(Calendar.SECOND, 0);
        cutoff.set(Calendar.MILLISECOND, 0);
        return cutoff.getTimeInMillis();
    }

    static double entryBufferPercent(Context context) {
        long bits = prefs(context).getLong(K_ENTRY_BUFFER,
                Double.doubleToRawLongBits(DEFAULT_ENTRY_BUFFER_PERCENT));
        double value = Double.longBitsToDouble(bits);
        return isValidEntryBuffer(value) ? value : DEFAULT_ENTRY_BUFFER_PERCENT;
    }

    static boolean isValidEntryBuffer(double value) {
        return !Double.isNaN(value) && !Double.isInfinite(value)
                && value >= MIN_ENTRY_BUFFER_PERCENT && value <= MAX_ENTRY_BUFFER_PERCENT;
    }

    static void setEntryBufferPercent(Context context, double value) {
        if (!isValidEntryBuffer(value)) {
            throw new IllegalArgumentException("Entry buffer must be between 0% and 2%.");
        }
        prefs(context).edit().putLong(K_ENTRY_BUFFER,
                Double.doubleToRawLongBits(value)).apply();
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
        prefs(context).edit().putString(K_EXPECTED_IP,
                value == null ? "" : value.trim()).apply();
    }

    static String lastPublicIp(Context context) {
        return prefs(context).getString(K_LAST_PUBLIC_IP, "").trim();
    }

    static void setIpVerification(Context context, String actualIp, boolean matched) {
        prefs(context).edit()
                .putString(K_LAST_PUBLIC_IP, actualIp == null ? "" : actualIp.trim())
                .putLong(K_IP_VERIFIED_AT, matched ? System.currentTimeMillis() : 0L)
                .apply();
    }

    static long ipVerifiedAt(Context context) {
        return prefs(context).getLong(K_IP_VERIFIED_AT, 0L);
    }

    static void setIpVerifiedAt(Context context, long value) {
        prefs(context).edit().putLong(K_IP_VERIFIED_AT, value).apply();
    }

    static boolean isIpRecentlyVerified(Context context) {
        long at = ipVerifiedAt(context);
        return at > 0L && System.currentTimeMillis() - at <= IP_VERIFICATION_MAX_AGE_MS
                && !expectedIp(context).isEmpty()
                && expectedIp(context).equals(lastPublicIp(context));
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

    static void clearAuthVerified(Context context) {
        prefs(context).edit().putString(K_AUTH_VERIFIED_DATE, "").apply();
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
        Set<String> values = prefs(context).getStringSet(
                K_PROCESSED_PREFIX + istDate(), new HashSet<>());
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
        if (combined.length() > 20_000) combined = combined.substring(0, 20_000);
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
        format.setTimeZone(IST);
        return format.format(new Date());
    }

    static String compactIstDate() {
        SimpleDateFormat format = new SimpleDateFormat("yyMMdd", Locale.US);
        format.setTimeZone(IST);
        return format.format(new Date());
    }

    private static String nowIst() {
        SimpleDateFormat format = new SimpleDateFormat("dd MMM, HH:mm:ss", Locale.US);
        format.setTimeZone(IST);
        return format.format(new Date()) + " IST";
    }

    private static String clean(String message) {
        if (message == null) return "";
        String value = message.replace('\r', ' ').trim();
        return value.length() <= 1_100 ? value : value.substring(0, 1_100) + "…";
    }

    static final class TradeWindow {
        final int index;
        final String label;
        final double budget;
        final boolean forceMis;
        final long entryCancelAt;

        TradeWindow(int index, String label, double budget,
                    boolean forceMis, long entryCancelAt) {
            this.index = index;
            this.label = label;
            this.budget = budget;
            this.forceMis = forceMis;
            this.entryCancelAt = entryCancelAt;
        }
    }
}