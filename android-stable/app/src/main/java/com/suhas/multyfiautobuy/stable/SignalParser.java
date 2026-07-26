package com.suhas.multyfiautobuy.stable;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Calendar;
import java.util.Locale;
import java.util.TimeZone;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

final class SignalParser {
    private static final Pattern STOCK_PATTERN = Pattern.compile(
            "(?i)(?:stock\\s*name|stock|symbol|scrip)\\s*[:\\-]\\s*([A-Z][A-Z0-9&._\\-]{0,24})");
    private static final Pattern ENTRY_RANGE_PATTERN = Pattern.compile(
            "(?i)(?:entry|buy)\\s*(?:range|price|zone|at)?\\s*[:\\-]\\s*(?:₹|rs\\.?|inr)?\\s*([0-9,]+(?:\\.[0-9]+)?)\\s*(?:-|–|—|to)\\s*(?:₹|rs\\.?|inr)?\\s*([0-9,]+(?:\\.[0-9]+)?)");
    private static final Pattern ENTRY_SINGLE_PATTERN = Pattern.compile(
            "(?i)(?:entry|buy)\\s*(?:price|at)?\\s*[:\\-]\\s*(?:₹|rs\\.?|inr)?\\s*([0-9,]+(?:\\.[0-9]+)?)");
    private static final Pattern TARGET_PATTERN = Pattern.compile(
            "(?i)(?:target(?:\\s*\\d+)?(?:\\s*price)?|sell\\s*(?:price|point)|exit\\s*(?:price|point))\\s*[:\\-]\\s*(?:₹|rs\\.?|inr)?\\s*([0-9,]+(?:\\.[0-9]+)?)");
    private static final Pattern STOP_LOSS_PATTERN = Pattern.compile(
            "(?i)(?:stop\\s*loss|stoploss|s\\.?l\\.?)\\s*[:\\-]\\s*(?:₹|rs\\.?|inr)?\\s*([0-9,]+(?:\\.[0-9]+)?)");
    private static final Pattern REJECT_ACTION_PATTERN = Pattern.compile(
            "(?im)^\\s*(?:sell(?!\\s*(?:price|point))|exit(?!\\s*(?:price|point))|book\\s+profit|target\\s+hit|stop\\s+loss\\s+hit)\\b|\\bfutures?\\b|\\boptions?\\b|commodity|\\bmcx\\b|f\\s*&\\s*o");
    private static final Pattern INTRADAY_PATTERN = Pattern.compile("(?i)\\b(?:intraday|intra\\s*day|mis)\\b");
    private static final Pattern SWING_PATTERN = Pattern.compile("(?i)\\bswing\\b");
    private static final Pattern MULTIBAGGER_PATTERN = Pattern.compile("(?i)\\bmulti[- ]?bagger\\b");
    private static final Pattern FREE_PATTERN = Pattern.compile("(?i)\\bfree\\s+(?:equity\\s+)?recommendation\\b");

    private static final TimeZone IST = TimeZone.getTimeZone("Asia/Kolkata");
    private static final int WINDOW_START_MINUTE = 8 * 60 + 45;
    private static final int WINDOW_END_MINUTE = 15 * 60 + 25;
    private static final int INTRADAY_ENTRY_END_MINUTE = 14 * 60 + 45;

    private SignalParser() { }

    static ParsedSignal parse(String rawText, long notificationTimeMillis) {
        return parse(rawText, notificationTimeMillis, AppPrefs.DEFAULT_ENTRY_BUFFER_PERCENT);
    }

    static ParsedSignal parse(String rawText, long notificationTimeMillis, double bufferPercent) {
        if (rawText == null || rawText.trim().isEmpty()) return null;
        if (!AppPrefs.isValidEntryBuffer(bufferPercent)) return null;
        if (REJECT_ACTION_PATTERN.matcher(rawText).find()) return null;

        Matcher stockMatcher = STOCK_PATTERN.matcher(rawText);
        if (!stockMatcher.find()) return null;

        double[] entry = parseEntry(rawText);
        double target = parseFirst(TARGET_PATTERN, rawText);
        double stopLoss = parseFirst(STOP_LOSS_PATTERN, rawText);
        if (entry == null || target <= 0d || stopLoss <= 0d) return null;

        String symbol = stockMatcher.group(1).toUpperCase(Locale.US).trim();
        double low = Math.min(entry[0], entry[1]);
        double high = Math.max(entry[0], entry[1]);
        if (symbol.isEmpty() || low <= 0d || high <= 0d) return null;

        String category = category(rawText);
        String productType = "INTRADAY".equals(category) ? "MIS" : "CNC";
        if (!isAllowedSignalTime(notificationTimeMillis)) return null;
        if ("MIS".equals(productType) && !isAllowedIntradayEntryTime(notificationTimeMillis)) return null;

        double recommendedTrigger = floorToTick(low, 0.05d);
        double maxBuy = floorToTick(high * (1d + bufferPercent / 100d), 0.05d);
        double targetPrice = floorToTick(target, 0.05d);
        double stopLossPrice = floorToTick(stopLoss, 0.05d);

        // Fail closed when the recommendation is internally inconsistent.
        if (targetPrice <= maxBuy || stopLossPrice >= low) return null;

        String digest = sha256(symbol + "|" + low + "|" + high + "|" + targetPrice
                + "|" + stopLossPrice + "|" + productType + "|" + bufferPercent
                + "|" + AppPrefs.istDate());
        String eventId = digest.substring(0, Math.min(24, digest.length()));
        String referenceId = "MF" + AppPrefs.compactIstDate()
                + digest.substring(0, 8).toUpperCase(Locale.US);
        return new ParsedSignal(eventId, referenceId, symbol, category, productType,
                low, high, recommendedTrigger, maxBuy, bufferPercent,
                targetPrice, stopLossPrice, notificationTimeMillis, rawText);
    }

    static boolean isAllowedSignalTime(long epochMillis) {
        Calendar calendar = Calendar.getInstance(IST, Locale.US);
        calendar.setTimeInMillis(epochMillis);
        int day = calendar.get(Calendar.DAY_OF_WEEK);
        if (day == Calendar.SATURDAY || day == Calendar.SUNDAY) return false;
        int minute = calendar.get(Calendar.HOUR_OF_DAY) * 60 + calendar.get(Calendar.MINUTE);
        return minute >= WINDOW_START_MINUTE && minute <= WINDOW_END_MINUTE;
    }

    static boolean isAllowedIntradayEntryTime(long epochMillis) {
        Calendar calendar = Calendar.getInstance(IST, Locale.US);
        calendar.setTimeInMillis(epochMillis);
        int minute = calendar.get(Calendar.HOUR_OF_DAY) * 60 + calendar.get(Calendar.MINUTE);
        return minute <= INTRADAY_ENTRY_END_MINUTE;
    }

    static double floorToTick(double price, double tick) {
        BigDecimal p = BigDecimal.valueOf(price);
        BigDecimal t = BigDecimal.valueOf(tick);
        return p.divide(t, 0, RoundingMode.FLOOR)
                .multiply(t).setScale(2, RoundingMode.UNNECESSARY).doubleValue();
    }

    static double ceilToTick(double price, double tick) {
        BigDecimal p = BigDecimal.valueOf(price);
        BigDecimal t = BigDecimal.valueOf(tick);
        return p.divide(t, 0, RoundingMode.CEILING)
                .multiply(t).setScale(2, RoundingMode.UNNECESSARY).doubleValue();
    }

    private static String category(String rawText) {
        if (INTRADAY_PATTERN.matcher(rawText).find()) return "INTRADAY";
        if (MULTIBAGGER_PATTERN.matcher(rawText).find()) return "MULTIBAGGER";
        if (SWING_PATTERN.matcher(rawText).find()) return "SWING";
        if (FREE_PATTERN.matcher(rawText).find()) return "FREE_EQUITY";
        return "EQUITY";
    }

    private static double[] parseEntry(String rawText) {
        Matcher range = ENTRY_RANGE_PATTERN.matcher(rawText);
        if (range.find()) {
            double first = parsePrice(range.group(1));
            double second = parsePrice(range.group(2));
            return first > 0d && second > 0d ? new double[]{first, second} : null;
        }
        Matcher single = ENTRY_SINGLE_PATTERN.matcher(rawText);
        if (single.find()) {
            double value = parsePrice(single.group(1));
            return value > 0d ? new double[]{value, value} : null;
        }
        return null;
    }

    private static double parseFirst(Pattern pattern, String rawText) {
        Matcher matcher = pattern.matcher(rawText);
        return matcher.find() ? parsePrice(matcher.group(1)) : -1d;
    }

    private static double parsePrice(String value) {
        try { return Double.parseDouble(value.replace(",", "")); }
        catch (Exception ignored) { return -1d; }
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
        final String category;
        final String productType;
        final double entryLow;
        final double entryHigh;
        final double triggerPrice;
        final double maxBuyPrice;
        final double bufferPercent;
        final double targetPrice;
        final double stopLossPrice;
        final long notificationTimeMillis;
        final String rawText;

        ParsedSignal(String eventId, String referenceId, String symbol, String category,
                     String productType, double entryLow, double entryHigh,
                     double triggerPrice, double maxBuyPrice, double bufferPercent,
                     double targetPrice, double stopLossPrice,
                     long notificationTimeMillis, String rawText) {
            this.eventId = eventId;
            this.referenceId = referenceId;
            this.symbol = symbol;
            this.category = category;
            this.productType = productType;
            this.entryLow = entryLow;
            this.entryHigh = entryHigh;
            this.triggerPrice = triggerPrice;
            this.maxBuyPrice = maxBuyPrice;
            this.bufferPercent = bufferPercent;
            this.targetPrice = targetPrice;
            this.stopLossPrice = stopLossPrice;
            this.notificationTimeMillis = notificationTimeMillis;
            this.rawText = rawText;
        }

        boolean isIntraday() { return "MIS".equals(productType); }

        double maximumOrderValue(int quantity) { return maxBuyPrice * quantity; }

        String summary(int quantity) {
            return symbol + " | " + category + "/" + productType
                    + " | entry ₹" + money(entryLow) + "–₹" + money(entryHigh)
                    + " | buy cap ₹" + money(maxBuyPrice)
                    + " (buffer " + String.format(Locale.US, "%.2f", bufferPercent) + "%)"
                    + " | target ₹" + money(targetPrice)
                    + " | SL ₹" + money(stopLossPrice)
                    + " | qty " + quantity;
        }

        private static String money(double value) {
            return Math.rint(value) == value
                    ? String.format(Locale.US, "%.0f", value)
                    : String.format(Locale.US, "%.2f", value);
        }
    }
}
