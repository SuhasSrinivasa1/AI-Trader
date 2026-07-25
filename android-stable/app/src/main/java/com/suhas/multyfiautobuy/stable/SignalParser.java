package com.suhas.multyfiautobuy.stable;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Locale;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

final class SignalParser {
    private static final Pattern STOCK_PATTERN = Pattern.compile(
            "(?i)stock\\s*name\\s*[:\\-]\\s*([A-Z][A-Z0-9&._\\-]{0,24})");
    private static final Pattern ENTRY_PATTERN = Pattern.compile(
            "(?i)entry\\s*range\\s*[:\\-]\\s*(?:₹|rs\\.?|inr)?\\s*([0-9,]+(?:\\.[0-9]+)?)\\s*(?:-|–|—|to)\\s*(?:₹|rs\\.?|inr)?\\s*([0-9,]+(?:\\.[0-9]+)?)");
    private static final Pattern REJECT_PATTERN = Pattern.compile(
            "(?i)(\\bsell\\b|\\bexit\\b|book\\s+profit|target\\s+hit|stop\\s+loss\\s+hit|\\bfutures?\\b|\\boptions?\\b|commodity|\\bmcx\\b|f\\s*&\\s*o)");

    private SignalParser() { }

    static ParsedSignal parse(String rawText, long notificationTimeMillis) {
        if (rawText == null || rawText.trim().isEmpty()) return null;
        if (REJECT_PATTERN.matcher(rawText).find()) return null;

        Matcher stockMatcher = STOCK_PATTERN.matcher(rawText);
        Matcher entryMatcher = ENTRY_PATTERN.matcher(rawText);
        if (!stockMatcher.find() || !entryMatcher.find()) return null;

        String symbol = stockMatcher.group(1).toUpperCase(Locale.US).trim();
        double first = parsePrice(entryMatcher.group(1));
        double second = parsePrice(entryMatcher.group(2));
        if (symbol.isEmpty() || first <= 0d || second <= 0d) return null;

        double low = Math.min(first, second);
        double high = Math.max(first, second);
        double trigger = floorToTick(low, 0.05d);
        double maxBuy = floorToTick(high * 1.01d, 0.05d);
        String digest = sha256(symbol + "|" + low + "|" + high + "|" + AppPrefs.istDate());
        String eventId = digest.substring(0, Math.min(24, digest.length()));
        String referenceId = "MF" + AppPrefs.compactIstDate() + digest.substring(0, 8).toUpperCase(Locale.US);
        return new ParsedSignal(eventId, referenceId, symbol, low, high, trigger, maxBuy,
                notificationTimeMillis, rawText);
    }

    static double floorToTick(double price, double tick) {
        BigDecimal p = BigDecimal.valueOf(price);
        BigDecimal t = BigDecimal.valueOf(tick);
        return p.divide(t, 0, RoundingMode.FLOOR).multiply(t).setScale(2, RoundingMode.UNNECESSARY).doubleValue();
    }

    private static double parsePrice(String value) {
        try {
            return Double.parseDouble(value.replace(",", ""));
        } catch (Exception ignored) {
            return -1d;
        }
    }

    private static String sha256(String text) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] bytes = digest.digest(text.getBytes(StandardCharsets.UTF_8));
            StringBuilder builder = new StringBuilder();
            for (byte b : bytes) builder.append(String.format(Locale.US, "%02x", b));
            return builder.toString();
        } catch (Exception e) {
            return Integer.toHexString(text.hashCode()) + "00000000000000000000000000000000";
        }
    }

    static final class ParsedSignal {
        final String eventId;
        final String referenceId;
        final String symbol;
        final double entryLow;
        final double entryHigh;
        final double triggerPrice;
        final double maxBuyPrice;
        final long notificationTimeMillis;
        final String rawText;

        ParsedSignal(String eventId, String referenceId, String symbol, double entryLow,
                     double entryHigh, double triggerPrice, double maxBuyPrice,
                     long notificationTimeMillis, String rawText) {
            this.eventId = eventId;
            this.referenceId = referenceId;
            this.symbol = symbol;
            this.entryLow = entryLow;
            this.entryHigh = entryHigh;
            this.triggerPrice = triggerPrice;
            this.maxBuyPrice = maxBuyPrice;
            this.notificationTimeMillis = notificationTimeMillis;
            this.rawText = rawText;
        }

        double maximumOrderValue() {
            return maxBuyPrice * AppPrefs.QUANTITY;
        }

        String summary() {
            return symbol + " | entry ₹" + money(entryLow) + "–₹" + money(entryHigh)
                    + " | trigger ₹" + money(triggerPrice) + " UP | limit ₹" + money(maxBuyPrice)
                    + " | qty " + AppPrefs.QUANTITY;
        }

        private static String money(double value) {
            return Math.rint(value) == value
                    ? String.format(Locale.US, "%.0f", value)
                    : String.format(Locale.US, "%.2f", value);
        }
    }
}
