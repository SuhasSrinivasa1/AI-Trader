#!/usr/bin/env python3
from pathlib import Path
import re
import runpy

# Build on the validated v2.1.0 OCR batch release, including v2.0.2 FREE routing
# and v2.0.1 persistent-arm / stop-loss recovery.
runpy.run_path("hotfix/run_v210.py", run_name="__main__")

ROOT = Path("android-stable")
JAVA = ROOT / "app/src/main/java/com/suhas/multyfiautobuy/stable"
TEST = ROOT / "app/src/test/java/com/suhas/multyfiautobuy/stable"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def replace_once(path: Path, old: str, new: str) -> None:
    text = read(path)
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected exactly one match in {path}: found {count}\n{old[:240]}")
    write(path, text.replace(old, new, 1))


# Release identity.
gradle = ROOT / "app/build.gradle"
replace_once(gradle, "versionCode 210", "versionCode 220")
replace_once(gradle, "versionName '2.1.0'", "versionName '2.2.0'")


# Exact NSE equity-delivery charge model used for the image-import 6% NET target.
write(JAVA / "DeliveryChargeCalculator.java", r'''package com.suhas.multyfiautobuy.stable;

final class DeliveryChargeCalculator {
    static final double DEFAULT_NET_PROFIT_PERCENT = 6.0d;

    private static final double BROKERAGE_RATE = 0.001d;
    private static final double BROKERAGE_MIN = 5.0d;
    private static final double BROKERAGE_MAX = 20.0d;
    private static final double STT_RATE = 0.001d;
    private static final double STAMP_BUY_RATE = 0.00015d;
    private static final double EXCHANGE_RATE = 0.0000297d;
    private static final double SEBI_RATE = 0.000001d;
    private static final double IPFT_RATE = 0.000001d;
    private static final double GST_RATE = 0.18d;
    private static final double DP_SELL_CHARGE = 20.0d;

    private DeliveryChargeCalculator() { }

    static double requiredSellPrice(double maximumBuyPrice, int quantity,
                                    double desiredNetProfitPercent) {
        if (maximumBuyPrice <= 0d || quantity <= 0
                || desiredNetProfitPercent <= 0d || desiredNetProfitPercent > 100d) return -1d;
        double purchaseValue = maximumBuyPrice * quantity;
        double targetNetProfit = purchaseValue * desiredNetProfitPercent / 100d;
        double acquisitionCost = purchaseValue + buyCharges(purchaseValue);
        double low = maximumBuyPrice;
        double high = Math.max(maximumBuyPrice + 1d, maximumBuyPrice * 1.25d);
        int guard = 0;
        while (netSaleProceeds(high * quantity) - acquisitionCost < targetNetProfit
                && guard++ < 80) high *= 1.35d;
        for (int i = 0; i < 100; i++) {
            double mid = (low + high) / 2d;
            if (netSaleProceeds(mid * quantity) - acquisitionCost >= targetNetProfit) high = mid;
            else low = mid;
        }
        double tick = Math.ceil((high - 1e-9d) / 0.05d) * 0.05d;
        while (estimatedNetProfit(maximumBuyPrice, tick, quantity) + 1e-7d < targetNetProfit) {
            tick += 0.05d;
        }
        return Math.round(tick * 100d) / 100d;
    }

    static double estimatedNetProfit(double buyPrice, double sellPrice, int quantity) {
        if (buyPrice <= 0d || sellPrice <= 0d || quantity <= 0) return -1d;
        double buyValue = buyPrice * quantity;
        return netSaleProceeds(sellPrice * quantity) - (buyValue + buyCharges(buyValue));
    }

    static double buyCharges(double buyValue) {
        if (buyValue <= 0d) return 0d;
        double brokerage = brokerage(buyValue);
        double exchange = buyValue * EXCHANGE_RATE;
        double sebi = buyValue * SEBI_RATE;
        double ipft = buyValue * IPFT_RATE;
        double gst = GST_RATE * (brokerage + exchange + sebi + ipft);
        return brokerage + buyValue * STT_RATE + buyValue * STAMP_BUY_RATE
                + exchange + sebi + ipft + gst;
    }

    static double sellCharges(double sellValue) {
        if (sellValue <= 0d) return 0d;
        double brokerage = brokerage(sellValue);
        double exchange = sellValue * EXCHANGE_RATE;
        double sebi = sellValue * SEBI_RATE;
        double ipft = sellValue * IPFT_RATE;
        double dp = sellValue < 100d ? 0d : DP_SELL_CHARGE;
        double gst = GST_RATE * (brokerage + exchange + sebi + ipft + dp);
        return brokerage + sellValue * STT_RATE + exchange + sebi + ipft + dp + gst;
    }

    private static double netSaleProceeds(double sellValue) {
        return sellValue - sellCharges(sellValue);
    }

    private static double brokerage(double turnover) {
        return Math.min(BROKERAGE_MAX, Math.max(BROKERAGE_MIN, turnover * BROKERAGE_RATE));
    }
}
''')

write(TEST / "DeliveryChargeCalculatorTest.java", r'''package com.suhas.multyfiautobuy.stable;

import org.junit.Test;
import static org.junit.Assert.*;

public class DeliveryChargeCalculatorTest {
    @Test public void targetProvidesAtLeastSixPercentNet() {
        double target = DeliveryChargeCalculator.requiredSellPrice(100d, 1, 6d);
        assertTrue(target > 106d);
        assertTrue(DeliveryChargeCalculator.estimatedNetProfit(100d, target, 1) >= 6d - 1e-6d);
        assertTrue(Math.abs(target * 20d - Math.rint(target * 20d)) < 1e-6d);
    }

    @Test public void largerQuantityStillMeetsTarget() {
        double target = DeliveryChargeCalculator.requiredSellPrice(500d, 20, 6d);
        assertTrue(DeliveryChargeCalculator.estimatedNetProfit(500d, target, 20) >= 600d - 1e-6d);
    }
}
''')


# Two user-facing event alerts only. The mandatory foreground monitor stays silent.
write(JAVA / "TradeEventNotifier.java", r'''package com.suhas.multyfiautobuy.stable;

import android.Manifest;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.os.Build;

final class TradeEventNotifier {
    private static final String CHANNEL = "multyfi_trade_events_v220";
    private static final String PREFS = "trade_event_alerts_v220";
    private static final String LAST_PAUSE = "last_pause";
    private static final String BUY_PREFIX = "buy_";

    private TradeEventNotifier() { }

    static void notifyBuyFilled(Context context, Strategy strategy, int quantity) {
        if (strategy == null || quantity <= 0) return;
        SharedPreferences prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        String key = BUY_PREFIX + strategy.eventId;
        if (prefs.getBoolean(key, false)) return;
        prefs.edit().putBoolean(key, true).apply();
        notify(context, 4200 + Math.abs(strategy.eventId.hashCode() % 800),
                "BUY completed", strategy.symbol + " • " + quantity + " share"
                        + (quantity == 1 ? "" : "s") + " confirmed by Groww.");
    }

    static void notifyTradingPaused(Context context, String reason) {
        if (!AppPrefs.isArmed(context)) return;
        String clean = reason == null ? "A required trading gate is unavailable." : reason.trim();
        SharedPreferences prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        if (clean.equals(prefs.getString(LAST_PAUSE, ""))) return;
        prefs.edit().putString(LAST_PAUSE, clean).apply();
        notify(context, 4101, "Auto trading paused", clean + " Open Multyfi AutoBuy Pro.");
    }

    static void notifyTradingOff(Context context, String reason) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
                .edit().putString(LAST_PAUSE, reason == null ? "off" : reason).apply();
        notify(context, 4101, "Auto trading turned off",
                reason == null ? "New automatic entries are disabled." : reason);
    }

    static void clearPause(Context context) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
                .edit().remove(LAST_PAUSE).apply();
    }

    private static void notify(Context context, int id, String title, String text) {
        if (Build.VERSION.SDK_INT >= 33
                && context.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)
                != PackageManager.PERMISSION_GRANTED) return;
        NotificationManager manager = context.getSystemService(NotificationManager.class);
        if (manager == null) return;
        NotificationChannel channel = new NotificationChannel(CHANNEL,
                "Trade events", NotificationManager.IMPORTANCE_DEFAULT);
        channel.setDescription("Only successful BUY confirmations and auto-trading pause/off alerts.");
        manager.createNotificationChannel(channel);
        Intent open = new Intent(context, MainActivity.class);
        PendingIntent pending = PendingIntent.getActivity(context, 220, open,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        Notification notification = new Notification.Builder(context, CHANNEL)
                .setSmallIcon(R.drawable.ic_launcher)
                .setContentTitle(title)
                .setContentText(text)
                .setStyle(new Notification.BigTextStyle().bigText(text))
                .setAutoCancel(true)
                .setContentIntent(pending)
                .setCategory(Notification.CATEGORY_STATUS)
                .build();
        manager.notify(id, notification);
    }
}
''')


# Configurable FREE recommendation amount, default ₹5,000.
prefs = JAVA / "AppPrefs.java"
text = read(prefs)
text = text.replace(
    "    static final double DEFAULT_WINDOW_3_BUDGET = 5_000d;",
    "    static final double DEFAULT_WINDOW_3_BUDGET = 5_000d;\n"
    "    static final double DEFAULT_FREE_RECOMMENDATION_BUDGET = 5_000d;",
    1,
)
text = text.replace(
    "    private static final String K_WINDOW_3_BUDGET = \"window_3_budget\";",
    "    private static final String K_WINDOW_3_BUDGET = \"window_3_budget\";\n"
    "    private static final String K_FREE_RECOMMENDATION_BUDGET = \"free_recommendation_budget\";",
    1,
)
marker = '''    static double window3Budget(Context context) {
        return readBudget(context, K_WINDOW_3_BUDGET, DEFAULT_WINDOW_3_BUDGET);
    }

'''
insert = marker + '''    static double freeRecommendationBudget(Context context) {
        return readBudget(context, K_FREE_RECOMMENDATION_BUDGET,
                DEFAULT_FREE_RECOMMENDATION_BUDGET);
    }

    static void setFreeRecommendationBudget(Context context, double value) {
        if (!isValidTradeBudget(value)) {
            throw new IllegalArgumentException("FREE recommendation amount must be between ₹1,000 and ₹5,00,000.");
        }
        prefs(context).edit().putLong(K_FREE_RECOMMENDATION_BUDGET,
                Double.doubleToRawLongBits(value)).apply();
    }

'''
if marker not in text:
    raise RuntimeError("Could not insert FREE budget preferences")
text = text.replace(marker, insert, 1)
write(prefs, text)


# Quantity policy now uses a configurable amount instead of fixed 10 shares.
policy = JAVA / "OrderPolicy.java"
text = read(policy)
old = '''    static int quantity(boolean freeRecommendation, double budget, double maximumBuyPrice) {
        return freeRecommendation ? 10 : AppPrefs.quantityForBudget(budget, maximumBuyPrice);
    }

    static boolean usesWindowBudget(boolean freeRecommendation) {
        return !freeRecommendation;
    }

'''
new = '''    static int quantity(boolean freeRecommendation, double windowBudget,
                        double freeRecommendationBudget, double maximumBuyPrice) {
        double budget = freeRecommendation ? freeRecommendationBudget : windowBudget;
        return AppPrefs.quantityForBudget(budget, maximumBuyPrice);
    }

    static double activeBudget(boolean freeRecommendation, double windowBudget,
                               double freeRecommendationBudget) {
        return freeRecommendation ? freeRecommendationBudget : windowBudget;
    }

    static boolean usesWindowBudget(boolean freeRecommendation) {
        return !freeRecommendation;
    }

'''
if old not in text:
    raise RuntimeError("Could not replace fixed FREE quantity policy")
text = text.replace(old, new, 1)
write(policy, text)

listener = JAVA / "ProductionNotificationService.java"
text = read(listener)
old = '''            boolean freeRecommendation = SignalParser.isFreeRecommendation(rawText);
            int quantity = OrderPolicy.quantity(freeRecommendation, window.budget, signal.maxBuyPrice);
            String summary = summary(signal, window, entryMode, productType, quantity,
                    freeRecommendation);'''
new = '''            boolean freeRecommendation = SignalParser.isFreeRecommendation(rawText);
            double freeBudget = AppPrefs.freeRecommendationBudget(this);
            int quantity = OrderPolicy.quantity(freeRecommendation, window.budget,
                    freeBudget, signal.maxBuyPrice);
            String summary = summary(signal, window, entryMode, productType, quantity,
                    freeRecommendation, freeBudget);'''
if old not in text:
    raise RuntimeError("Could not update FREE quantity execution")
text = text.replace(old, new, 1)
old = '''            if ((OrderPolicy.usesWindowBudget(freeRecommendation)
                    && maximumOrderValue > window.budget + 0.01d)
                    || maximumOrderValue > AppPrefs.MAX_ORDER_VALUE) {'''
new = '''            double activeBudget = OrderPolicy.activeBudget(freeRecommendation,
                    window.budget, freeBudget);
            if (maximumOrderValue > activeBudget + 0.01d
                    || maximumOrderValue > AppPrefs.MAX_ORDER_VALUE) {'''
if old not in text:
    raise RuntimeError("Could not update FREE value cap")
text = text.replace(old, new, 1)
old = '''                                   String productType, int quantity,
                                   boolean freeRecommendation) {'''
new = '''                                   String productType, int quantity,
                                   boolean freeRecommendation, double freeBudget) {'''
if old not in text:
    raise RuntimeError("Could not update summary signature")
text = text.replace(old, new, 1)
text = text.replace(
    '? " | FREE OVERRIDE: fixed 10 shares; window budget ignored"',
    '? " | FREE amount ₹" + money(freeBudget) + "; qty=floor(amount/cap)"',
    1,
)
write(listener, text)


# Image parser: target is always recalculated to at least 6% NET after standard
# Groww/NSE delivery charges. Stop-loss can come from the image or a configurable default %.
write(JAVA / "ImageOrderParser.java", r'''package com.suhas.multyfiautobuy.stable;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

final class ImageOrderParser {
    static final int MAX_ORDERS = 50;

    private static final Pattern STOCK = Pattern.compile(
            "(?i)(?:stock\\s*name|stock|symbol|scrip|trading\\s*symbol)\\s*[:\\-]\\s*([A-Z][A-Z0-9&._\\-]{0,24})");
    private static final Pattern ENTRY_RANGE = Pattern.compile(
            "(?i)(?:entry|buy)\\s*(?:range|price|zone|at)?\\s*[:\\-]\\s*(?:₹|rs\\.?|inr)?\\s*([0-9,]+(?:\\.[0-9]+)?)\\s*(?:-|–|—|to)\\s*(?:₹|rs\\.?|inr)?\\s*([0-9,]+(?:\\.[0-9]+)?)");
    private static final Pattern ENTRY_SINGLE = Pattern.compile(
            "(?i)(?:entry|buy)\\s*(?:price|at)?\\s*[:\\-]\\s*(?:₹|rs\\.?|inr)?\\s*([0-9,]+(?:\\.[0-9]+)?)");
    private static final Pattern STOP = Pattern.compile(
            "(?i)(?:stop\\s*loss|stoploss|s\\.?l\\.?)\\s*[:\\-]\\s*(?:₹|rs\\.?|inr)?\\s*([0-9,]+(?:\\.[0-9]+)?)");
    private static final Pattern QTY = Pattern.compile(
            "(?i)(?:qty|quantity|units?|shares?)\\s*[:\\-]?\\s*([0-9]{1,5})");
    private static final Pattern RANGE_VALUE = Pattern.compile(
            "([0-9,]+(?:\\.[0-9]+)?)\\s*(?:-|–|—|to)\\s*([0-9,]+(?:\\.[0-9]+)?)",
            Pattern.CASE_INSENSITIVE);

    private ImageOrderParser() { }

    static ParseResult parse(String rawText, int defaultQuantity,
                             double defaultStopLossPercent, double netProfitPercent) {
        List<OrderDraft> orders = new ArrayList<>();
        List<String> errors = new ArrayList<>();
        if (rawText == null || rawText.trim().isEmpty()) {
            errors.add("OCR returned no text.");
            return new ParseResult(orders, errors);
        }
        if (defaultQuantity < 1 || defaultQuantity > 10_000) {
            errors.add("Default quantity must be between 1 and 10,000.");
            return new ParseResult(orders, errors);
        }
        if (defaultStopLossPercent < 0.5d || defaultStopLossPercent > 30d) {
            errors.add("Default stop-loss must be between 0.5% and 30%.");
            return new ParseResult(orders, errors);
        }

        String text = normalise(rawText);
        Matcher stockMatcher = STOCK.matcher(text);
        List<Integer> starts = new ArrayList<>();
        while (stockMatcher.find()) starts.add(stockMatcher.start());
        if (!starts.isEmpty()) {
            for (int i = 0; i < starts.size() && orders.size() < MAX_ORDERS; i++) {
                int end = i + 1 < starts.size() ? starts.get(i + 1) : text.length();
                parseLabelledBlock(text.substring(starts.get(i), end), defaultQuantity,
                        defaultStopLossPercent, netProfitPercent, i + 1, orders, errors);
            }
        }
        if (orders.isEmpty()) {
            String[] lines = text.split("\\n");
            int row = 0;
            for (String line : lines) {
                if (orders.size() >= MAX_ORDERS) break;
                String value = line.trim();
                if (value.isEmpty() || isHeader(value)) continue;
                row++;
                parseCompactRow(value, defaultQuantity, defaultStopLossPercent,
                        netProfitPercent, row, orders, errors);
            }
        }

        Set<String> symbols = new HashSet<>();
        List<OrderDraft> unique = new ArrayList<>();
        for (OrderDraft order : orders) {
            if (!symbols.add(order.symbol)) {
                errors.add(order.symbol + ": duplicate symbol in the image; only the first row is retained.");
            } else unique.add(order);
        }
        return new ParseResult(unique, errors);
    }

    private static void parseLabelledBlock(String block, int defaultQuantity,
                                           double defaultStopLossPercent,
                                           double netProfitPercent, int index,
                                           List<OrderDraft> orders, List<String> errors) {
        Matcher stock = STOCK.matcher(block);
        if (!stock.find()) return;
        String symbol = stock.group(1).toUpperCase(Locale.US).trim();
        double[] entry = parseLabelledEntry(block);
        Matcher qtyMatcher = QTY.matcher(block);
        boolean quantityFound = qtyMatcher.find();
        int quantity = quantityFound ? integer(qtyMatcher.group(1)) : defaultQuantity;
        Matcher stopMatcher = STOP.matcher(block);
        boolean stopFound = stopMatcher.find();
        double stop = stopFound ? price(stopMatcher.group(1)) : -1d;
        addValidated(symbol, entry, stop, quantity, !quantityFound, !stopFound,
                defaultStopLossPercent, netProfitPercent,
                "recommendation " + index, orders, errors);
    }

    private static void parseCompactRow(String line, int defaultQuantity,
                                        double defaultStopLossPercent,
                                        double netProfitPercent, int row,
                                        List<OrderDraft> orders, List<String> errors) {
        String[] tokens = line.replace("₹", "").split("\\s+");
        if (tokens.length < 3) return;
        String symbol = tokens[0].toUpperCase(Locale.US);
        if (!symbol.matches("[A-Z][A-Z0-9&._\\-]{0,24}")) return;
        double[] entry = parseEntryValue(tokens[1]);
        List<Double> numbers = new ArrayList<>();
        for (int i = 2; i < tokens.length; i++) {
            double value = price(tokens[i]);
            if (value > 0d) numbers.add(value);
        }
        if (numbers.isEmpty()) return;
        int quantity = defaultQuantity;
        boolean quantityDefaulted = true;
        double stop = -1d;
        boolean stopDefaulted = true;
        double last = numbers.get(numbers.size() - 1);
        if (Math.rint(last) == last && last >= 1d && last <= 10_000d) {
            quantity = (int) last;
            quantityDefaulted = false;
            numbers.remove(numbers.size() - 1);
        }
        if (!numbers.isEmpty()) {
            // For legacy TARGET STOP QTY rows, the last remaining price is the stop.
            stop = numbers.get(numbers.size() - 1);
            stopDefaulted = false;
        }
        addValidated(symbol, entry, stop, quantity, quantityDefaulted, stopDefaulted,
                defaultStopLossPercent, netProfitPercent,
                "table row " + row, orders, errors);
    }

    private static void addValidated(String symbol, double[] entry, double explicitStop,
                                     int quantity, boolean quantityDefaulted,
                                     boolean stopDefaulted, double defaultStopLossPercent,
                                     double netProfitPercent, String source,
                                     List<OrderDraft> orders, List<String> errors) {
        if (symbol == null || symbol.isEmpty() || entry == null) {
            errors.add(source + ": missing symbol or entry price.");
            return;
        }
        double low = Math.min(entry[0], entry[1]);
        double high = Math.max(entry[0], entry[1]);
        if (quantity < 1 || quantity > 10_000 || low <= 0d || high <= 0d) {
            errors.add(symbol + ": invalid quantity or entry price.");
            return;
        }
        double stop = explicitStop > 0d ? explicitStop
                : low * (1d - defaultStopLossPercent / 100d);
        stop = SignalParser.floorToTick(stop, 0.05d);
        double target = DeliveryChargeCalculator.requiredSellPrice(high, quantity,
                netProfitPercent);
        if (target <= high || stop <= 0d || stop >= low) {
            errors.add(symbol + ": calculated target/stop relationship is unsafe; row rejected.");
            return;
        }
        orders.add(new OrderDraft(symbol,
                SignalParser.floorToTick(low, 0.05d),
                SignalParser.floorToTick(high, 0.05d),
                target, stop, quantity, quantityDefaulted, stopDefaulted));
    }

    private static double[] parseLabelledEntry(String block) {
        Matcher range = ENTRY_RANGE.matcher(block);
        if (range.find()) return new double[]{price(range.group(1)), price(range.group(2))};
        Matcher single = ENTRY_SINGLE.matcher(block);
        if (single.find()) {
            double value = price(single.group(1));
            return new double[]{value, value};
        }
        return null;
    }

    private static double[] parseEntryValue(String value) {
        Matcher range = RANGE_VALUE.matcher(value == null ? "" : value);
        if (range.find()) return new double[]{price(range.group(1)), price(range.group(2))};
        double single = price(value);
        return single > 0d ? new double[]{single, single} : null;
    }

    private static boolean isHeader(String line) {
        String lower = line.toLowerCase(Locale.US);
        return lower.contains("stock") || lower.contains("symbol")
                || (lower.contains("entry") && lower.contains("qty"));
    }

    private static double price(String value) {
        if (value == null) return -1d;
        try { return Double.parseDouble(value.replace(",", "").replace("₹", "").trim()); }
        catch (Exception ignored) { return -1d; }
    }

    private static int integer(String value) {
        try { return Integer.parseInt(value == null ? "" : value.replace(",", "").trim()); }
        catch (Exception ignored) { return 0; }
    }

    private static String normalise(String value) {
        return value.replace('\r', '\n').replace('—', '-').replace('–', '-')
                .replaceAll("(?i)\\bR[S5]\\.?\\s*", "₹")
                .replaceAll("[ \\t]+", " ")
                .replaceAll("\\n{3,}", "\\n\\n").trim();
    }

    static final class OrderDraft {
        final String symbol;
        final double entryLow;
        final double entryHigh;
        final double target;
        final double stopLoss;
        final int quantity;
        final boolean quantityDefaulted;
        final boolean stopLossDefaulted;

        OrderDraft(String symbol, double entryLow, double entryHigh, double target,
                   double stopLoss, int quantity, boolean quantityDefaulted,
                   boolean stopLossDefaulted) {
            this.symbol = symbol;
            this.entryLow = entryLow;
            this.entryHigh = entryHigh;
            this.target = target;
            this.stopLoss = stopLoss;
            this.quantity = quantity;
            this.quantityDefaulted = quantityDefaulted;
            this.stopLossDefaulted = stopLossDefaulted;
        }

        double maximumValue() { return entryHigh * quantity; }

        String summary() {
            double desired = maximumValue() * DeliveryChargeCalculator.DEFAULT_NET_PROFIT_PERCENT / 100d;
            return symbol + " • qty " + quantity + (quantityDefaulted ? " (default)" : "")
                    + " • entry ₹" + money(entryLow) + "–₹" + money(entryHigh)
                    + " • NET 6% target GTT ₹" + money(target)
                    + " • SL ₹" + money(stopLoss) + (stopLossDefaulted ? " (default %)" : "")
                    + " • minimum estimated net profit ₹" + money(desired)
                    + " • max buy ₹" + money(maximumValue());
        }
    }

    static final class ParseResult {
        final List<OrderDraft> orders;
        final List<String> errors;
        ParseResult(List<OrderDraft> orders, List<String> errors) {
            this.orders = orders;
            this.errors = errors;
        }
    }

    private static String money(double value) {
        return Math.rint(value) == value ? String.format(Locale.US, "%.0f", value)
                : String.format(Locale.US, "%.2f", value);
    }
}
''')

write(TEST / "ImageOrderParserTest.java", r'''package com.suhas.multyfiautobuy.stable;

import org.junit.Test;
import static org.junit.Assert.*;

public class ImageOrderParserTest {
    @Test public void parsesBuyPriceAndQuantityAndComputesNetTarget() {
        String text = "Stock Name: TCS\nEntry Range: 3200-3220\nQty: 2\nStop Loss: 3150\n\n"
                + "Stock Name: ITC\nEntry: 410\nQty: 10";
        ImageOrderParser.ParseResult result = ImageOrderParser.parse(text, 1, 5d, 6d);
        assertEquals(2, result.orders.size());
        assertEquals(2, result.orders.get(0).quantity);
        assertTrue(result.orders.get(0).target > 3220d);
        assertTrue(result.orders.get(1).stopLossDefaulted);
        assertTrue(DeliveryChargeCalculator.estimatedNetProfit(
                result.orders.get(0).entryHigh, result.orders.get(0).target, 2) >= 3220d * 2d * 0.06d - 1e-6d);
    }

    @Test public void parsesCompactBuyPriceQuantityRows() {
        String text = "STOCK ENTRY QTY\nTCS 3200-3220 2\nITC 410 10";
        ImageOrderParser.ParseResult result = ImageOrderParser.parse(text, 1, 5d, 6d);
        assertEquals(2, result.orders.size());
        assertEquals(10, result.orders.get(1).quantity);
    }

    @Test public void rejectsUnsafeExplicitStop() {
        String text = "Stock Name: TCS\nEntry: 3200\nQty: 2\nStop Loss: 3300";
        ImageOrderParser.ParseResult result = ImageOrderParser.parse(text, 1, 5d, 6d);
        assertTrue(result.orders.isEmpty());
        assertFalse(result.errors.isEmpty());
    }
}
''')


# Persist a broker target GTT for image-import fills.
strategy = JAVA / "Strategy.java"
text = read(strategy)
text = text.replace(
    "    final double targetPrice;",
    "    final double targetPrice;\n    String targetSmartOrderId;\n    int targetGttQuantity;\n    String targetGttStatus;",
    1,
)
text = text.replace(
    "        this.targetPrice = targetPrice;",
    "        this.targetPrice = targetPrice;\n        this.targetSmartOrderId = \"\";\n"
    "        this.targetGttQuantity = 0;\n        this.targetGttStatus = \"\";",
    1,
)
text = text.replace(
    "    boolean isIntraday() { return \"MIS\".equalsIgnoreCase(productType); }",
    "    boolean isIntraday() { return \"MIS\".equalsIgnoreCase(productType); }\n\n"
    "    boolean isImageBatch() { return \"IMAGE_BATCH\".equalsIgnoreCase(category); }",
    1,
)
text = text.replace(
    '        json.put("target_price", targetPrice);',
    '        json.put("target_price", targetPrice);\n'
    '        json.put("target_smart_order_id", targetSmartOrderId);\n'
    '        json.put("target_gtt_quantity", targetGttQuantity);\n'
    '        json.put("target_gtt_status", targetGttStatus);',
    1,
)
text = text.replace(
    "        strategy.observedFilledQuantity = json.optInt(\"observed_filled_quantity\", 0);",
    "        strategy.targetSmartOrderId = json.optString(\"target_smart_order_id\", \"\");\n"
    "        strategy.targetGttQuantity = json.optInt(\"target_gtt_quantity\", 0);\n"
    "        strategy.targetGttStatus = json.optString(\"target_gtt_status\", \"\");\n"
    "        strategy.observedFilledQuantity = json.optInt(\"observed_filled_quantity\", 0);",
    1,
)
write(strategy, text)

client = JAVA / "GrowwClient.java"
text = read(client)
insert_marker = '''    static ApiResult cancelGtt(String accessToken, String smartOrderId) {'''
target_method = r'''    static ApiResult createTargetGtt(String accessToken, Strategy strategy, int quantity) {
        try {
            String reference = reference("TP", strategy.eventId, 1);
            JSONObject order = new JSONObject();
            order.put("order_type", "LIMIT");
            order.put("price", price(strategy.targetPrice));
            order.put("transaction_type", "SELL");
            JSONObject body = gttBase(reference, strategy.symbol, quantity,
                    strategy.targetPrice, "UP", order, strategy.productType);
            HttpResult http = request("POST", API_BASE + "/order-advance/create",
                    accessToken, body);
            if (!http.isSuccess()) {
                ApiResult failure = apiFailure(http);
                if (isDuplicateSmartReference(failure)) {
                    return recoverActiveTargetGtt(accessToken, reference, strategy, quantity);
                }
                return failure;
            }
            JSONObject payload = new JSONObject(http.body).optJSONObject("payload");
            String id = payload == null ? "" : payload.optString("smart_order_id", "");
            String status = payload == null ? "" : payload.optString("status", "");
            if (id.isEmpty()) return ApiResult.failure("TARGET_NO_ID",
                    "Groww accepted target GTT but returned no ID.", http.code);
            if (!isLiveSmartStatus(status)) {
                SmartStatus confirmed = confirmGtt(accessToken, id);
                status = confirmed.status;
            }
            if (!isLiveSmartStatus(status)) {
                cancelGtt(accessToken, id);
                return ApiResult.failure("TARGET_NOT_CONFIRMED",
                        "Target GTT was not confirmed ACTIVE and was cancelled.", http.code);
            }
            return ApiResult.success(id, "NET target GTT confirmed " + status
                    + " for " + quantity + " shares at ₹" + price(strategy.targetPrice)
                    + ": " + id + ".", http.code);
        } catch (Exception e) {
            return ApiResult.failure("", "Target GTT error: " + safeMessage(e), 0);
        }
    }

    private static ApiResult recoverActiveTargetGtt(String accessToken, String reference,
                                                      Strategy strategy, int quantity) {
        try {
            String url = API_BASE + "/order-advance/list?segment=CASH"
                    + "&smart_order_type=GTT&status=ACTIVE&page=0&page_size=50";
            HttpResult http = request("GET", url, accessToken, null);
            if (!http.isSuccess()) return apiFailure(http);
            JSONObject root = new JSONObject(http.body);
            JSONObject payload = root.optJSONObject("payload");
            JSONArray orders = payload == null ? null : payload.optJSONArray("orders");
            if (orders == null) orders = root.optJSONArray("orders");
            if (orders == null) return ApiResult.failure("TARGET_RECOVERY_NO_LIST",
                    "Groww smart-order list returned no orders array.", http.code);
            String matchId = "";
            int matches = 0;
            for (int i = 0; i < orders.length(); i++) {
                JSONObject item = orders.optJSONObject(i);
                if (item == null) continue;
                String listedReference = item.optString("reference_id", "");
                if (!listedReference.isEmpty() && !reference.equalsIgnoreCase(listedReference)) continue;
                if (!isLiveSmartStatus(item.optString("status", ""))) continue;
                if (!strategy.symbol.equalsIgnoreCase(item.optString("trading_symbol", ""))) continue;
                if (quantity != item.optInt("quantity", -1)) continue;
                if (!"UP".equalsIgnoreCase(item.optString("trigger_direction", ""))) continue;
                double trigger = item.optDouble("trigger_price", Double.NaN);
                if (Double.isNaN(trigger) || Math.abs(trigger - strategy.targetPrice) > 0.011d) continue;
                JSONObject listedOrder = item.optJSONObject("order");
                if (listedOrder == null
                        || !"SELL".equalsIgnoreCase(listedOrder.optString("transaction_type", ""))) continue;
                String id = item.optString("smart_order_id", "");
                if (id.isEmpty()) continue;
                matchId = id;
                matches++;
            }
            if (matches == 1) return ApiResult.success(matchId,
                    "Recovered the already-active NET target GTT: " + matchId + ".", http.code);
            if (matches > 1) return ApiResult.failure("TARGET_RECOVERY_AMBIGUOUS",
                    "Multiple matching target GTTs exist for " + strategy.symbol + ".", http.code);
            return ApiResult.failure("TARGET_RECOVERY_NOT_FOUND",
                    "No matching ACTIVE target GTT is visible yet.", http.code);
        } catch (Exception e) {
            return ApiResult.failure("TARGET_RECOVERY_ERROR",
                    "Target GTT recovery error: " + safeMessage(e), 0);
        }
    }

'''
if insert_marker not in text:
    raise RuntimeError("Could not insert target GTT methods")
text = text.replace(insert_marker, target_method + insert_marker, 1)
write(client, text)


# Image batch logs now describe the computed broker target GTT.
executor = JAVA / "ImageBatchExecutor.java"
text = read(executor)
text = text.replace(
    "Stop-loss and target monitoring start automatically after the actual fill.",
    "After the actual fill, the app creates the broker stop-loss GTT and the computed 6% NET target GTT automatically.",
)
write(executor, text)


# Dashboard additions: configurable FREE amount, default image stop-loss %, and focused alert disclosure.
activity = JAVA / "ProductionActivity.java"
text = read(activity)
text = text.replace("release 2.1.0", "release 2.2.0")
text = text.replace("source-built v2.1.0", "source-built v2.2.0")
text = text.replace(
    "    private EditText window3Input;",
    "    private EditText window3Input;\n    private EditText freeBudgetInput;",
    1,
)
text = text.replace(
    "    private EditText batchDefaultQuantityInput;",
    "    private EditText batchDefaultQuantityInput;\n    private EditText batchStopLossPercentInput;",
    1,
)
text = text.replace(
    '        bufferInput = decimalField("Entry buffer % (0.00–2.00)");',
    '        freeBudgetInput = moneyField("FREE recommendation amount • default ₹5,000");\n'
    '        bufferInput = decimalField("Entry buffer % (0.00–2.00)");',
    1,
)
text = text.replace(
    "        windowsCard.addView(window3Input, topMargin(10));\n        windowsCard.addView(bufferInput, topMargin(10));",
    "        windowsCard.addView(window3Input, topMargin(10));\n"
    "        windowsCard.addView(freeBudgetInput, topMargin(10));\n"
    "        windowsCard.addView(bufferInput, topMargin(10));",
    1,
)
text = text.replace(
    "        attachWindowWatch(window3Input);\n        attachWindowWatch(bufferInput);",
    "        attachWindowWatch(window3Input);\n        attachWindowWatch(freeBudgetInput);\n"
    "        attachWindowWatch(bufferInput);",
    1,
)
text = text.replace(
    "        window3Input.setText(money(AppPrefs.window3Budget(this)));\n        bufferInput.setText",
    "        window3Input.setText(money(AppPrefs.window3Budget(this)));\n"
    "        freeBudgetInput.setText(money(AppPrefs.freeRecommendationBudget(this)));\n"
    "        bufferInput.setText",
    1,
)
text = text.replace(
    '                + " / ₹" + money(AppPrefs.window3Budget(this))\n                + " • buffer "',
    '                + " / ₹" + money(AppPrefs.window3Budget(this))\n'
    '                + " • FREE ₹" + money(AppPrefs.freeRecommendationBudget(this))\n'
    '                + " • buffer "',
    1,
)
text = text.replace(
    "            double third = readDouble(window3Input);\n            double buffer = readDouble(bufferInput);",
    "            double third = readDouble(window3Input);\n"
    "            double freeBudget = readDouble(freeBudgetInput);\n"
    "            double buffer = readDouble(bufferInput);",
    1,
)
text = text.replace(
    "                    || !AppPrefs.isValidTradeBudget(third)) {",
    "                    || !AppPrefs.isValidTradeBudget(third)\n"
    "                    || !AppPrefs.isValidTradeBudget(freeBudget)) {",
    1,
)
text = text.replace(
    "            AppPrefs.setWindowBudgets(this, first, second, third);\n            AppPrefs.setEntryBufferPercent(this, buffer);",
    "            AppPrefs.setWindowBudgets(this, first, second, third);\n"
    "            AppPrefs.setFreeRecommendationBudget(this, freeBudget);\n"
    "            AppPrefs.setEntryBufferPercent(this, buffer);",
    1,
)
text = text.replace(
    '                    + " / ₹" + money(third) + " • buffer "',
    '                    + " / ₹" + money(third) + " • FREE ₹" + money(freeBudget) + " • buffer "',
    1,
)
text = text.replace(
    '                            + " • 10:00–15:30 ₹" + money(third) + " CNC entry GTT"\n                            + " • buffer "',
    '                            + " • 10:00–15:30 ₹" + money(third) + " CNC entry GTT"\n'
    '                            + " • FREE recommendation amount ₹" + money(freeBudget)\n'
    '                            + " • buffer "',
    1,
)
text = text.replace(
    '        batchDefaultQuantityInput = textField("Default quantity when the image has no Qty", "1");\n'
    '        batchDefaultQuantityInput.setInputType(InputType.TYPE_CLASS_NUMBER);\n'
    '        imageCard.addView(batchDefaultQuantityInput, topMargin(12));',
    '        batchDefaultQuantityInput = textField("Default quantity when the image has no Qty", "1");\n'
    '        batchDefaultQuantityInput.setInputType(InputType.TYPE_CLASS_NUMBER);\n'
    '        imageCard.addView(batchDefaultQuantityInput, topMargin(12));\n'
    '        batchStopLossPercentInput = decimalField("Default stop-loss % when image has no SL (0.5–30)");\n'
    '        batchStopLossPercentInput.setText("5.00");\n'
    '        imageCard.addView(batchStopLossPercentInput, topMargin(10));\n'
    '        imageCard.addView(label("Image targets are ignored/recalculated. The app uses a fixed 6% NET-profit target after standard Groww/NSE delivery charges and rounds the sell trigger upward to ₹0.05.", 12, MUTED, false), topMargin(8));',
    1,
)
text = text.replace(
    "        ImageOrderParser.ParseResult parsed = ImageOrderParser.parse(correctedText, defaultQuantity);",
    "        double defaultStopLossPercent;\n"
    "        try { defaultStopLossPercent = readDouble(batchStopLossPercentInput); }\n"
    "        catch (Exception e) { toast(\"Enter a default stop-loss between 0.5% and 30%.\"); return; }\n"
    "        ImageOrderParser.ParseResult parsed = ImageOrderParser.parse(correctedText, defaultQuantity,\n"
    "                defaultStopLossPercent, DeliveryChargeCalculator.DEFAULT_NET_PROFIT_PERCENT);",
    1,
)
text = text.replace(
    "This creates real CNC entry GTTs. CASH OCO is not used. After each actual fill, the app creates/verifies the stop-loss GTT and monitors the target for automatic exit.",
    "This creates real CNC entry GTTs. After a confirmed fill, the app creates a broker stop-loss GTT and a broker target GTT calculated for at least 6% NET profit after standard Groww/NSE delivery charges. CASH OCO is unavailable, so the app actively cancels the opposite GTT after a trigger.",
    1,
)
text = text.replace(
    '                && OrderPolicy.quantity(true, first.budget, 6975d) == 10\n'
    '                && OrderPolicy.quantity(false, first.budget, signal.maxBuyPrice)',
    '                && OrderPolicy.quantity(true, first.budget,\n'
    '                AppPrefs.DEFAULT_FREE_RECOMMENDATION_BUDGET, 1000d) == 5\n'
    '                && OrderPolicy.quantity(false, first.budget,\n'
    '                AppPrefs.DEFAULT_FREE_RECOMMENDATION_BUDGET, signal.maxBuyPrice)',
    1,
)
text = text.replace(
    "FREE fixed quantity 10 in every active window",
    "FREE uses configurable amount (default ₹5,000)",
)
# Manual off and readiness pause notifications.
text = text.replace(
    '            AppPrefs.log(this, "DISARMED BY USER",\n'
    '                    "New automatic entries disabled; existing strategies remain monitored and protected.");',
    '            AppPrefs.log(this, "DISARMED BY USER",\n'
    '                    "New automatic entries disabled; existing strategies remain monitored and protected.");\n'
    '            TradeEventNotifier.notifyTradingOff(this,\n'
    '                    "New automatic entries were turned off manually.");',
    1,
)
status_marker = '''        suppressSwitch = true;
        armedSwitch.setChecked(persistentlyArmed);
        suppressSwitch = false;'''
status_insert = '''        if (ready) TradeEventNotifier.clearPause(this);
        else if (persistentlyArmed) TradeEventNotifier.notifyTradingPaused(this, issue);
        suppressSwitch = true;
        armedSwitch.setChecked(persistentlyArmed);
        suppressSwitch = false;'''
if status_marker not in text:
    raise RuntimeError("Could not add readiness notifications")
text = text.replace(status_marker, status_insert, 1)
write(activity, text)


# Monitor: silent ongoing notification, one BUY alert, one deduplicated pause alert,
# and broker target-GTT lifecycle for image imports.
monitor = JAVA / "StrategyMonitorService.java"
text = read(monitor)
text = text.replace(
    '    private static final String CHANNEL_ID = "staged_trade_monitor";',
    '    private static final String CHANNEL_ID = "staged_trade_monitor_silent_v220";',
    1,
)
text = text.replace(
    '        NotificationChannel channel = new NotificationChannel(CHANNEL_ID,\n'
    '                "Autonomous trade protection", NotificationManager.IMPORTANCE_LOW);',
    '        NotificationChannel channel = new NotificationChannel(CHANNEL_ID,\n'
    '                "Autonomous trade protection (silent)", NotificationManager.IMPORTANCE_MIN);\n'
    '        channel.setSound(null, null);\n        channel.enableVibration(false);',
    1,
)
fill_marker = '''            AppPrefs.log(this, "ENTRY FILL OBSERVED",
                    strategy.symbol + " • " + strategy.lastMessage);'''
fill_insert = fill_marker + '''
            TradeEventNotifier.notifyBuyFilled(this, strategy,
                    strategy.observedFilledQuantity);'''
if fill_marker not in text:
    raise RuntimeError("Could not add BUY fill notification")
text = text.replace(fill_marker, fill_insert, 1)
# Add target GTT creation after stop protection.
protect_gate = '''        if (strategy.observedFilledQuantity > strategy.protectedQuantity) {
            if (!staticIpReady) {'''
# Existing v2.0.1 text still has this marker after removing setArmed line.
if protect_gate not in text:
    raise RuntimeError("Could not locate protection gate")
# Insert image-target block after the whole stop-protection block using stable trailing marker.
trail = '''            if (!protectNewFill(token, strategy)) return;
        }

        if (remaining <= 0 && strategy.observedFilledQuantity > 0) {'''
replacement = '''            if (!protectNewFill(token, strategy)) return;
        }

        if (strategy.isImageBatch() && strategy.observedFilledQuantity > 0
                && strategy.targetSmartOrderId.isEmpty()
                && imageEntryIsFinal(strategy)) {
            if (!createImageTargetGtt(token, strategy)) return;
        }

        if (remaining <= 0 && strategy.observedFilledQuantity > 0) {'''
if trail not in text:
    raise RuntimeError("Could not insert image target GTT gate")
text = text.replace(trail, replacement, 1)
# Target GTT status is checked before app-managed LTP target logic.
state_marker = '''        strategy.state = Strategy.PROTECTED;
        if (anyStopLegTriggered(token, strategy)) {'''
state_insert = '''        strategy.state = Strategy.PROTECTED;
        if (strategy.isImageBatch() && !strategy.targetSmartOrderId.isEmpty()) {
            GrowwClient.SmartStatus target = GrowwClient.getGtt(token,
                    strategy.targetSmartOrderId);
            if (target.success) {
                strategy.targetGttStatus = target.status;
                if (isTriggeredStatus(target.status)) {
                    cancelAllStopLegsAfterTarget(token, strategy);
                    strategy.lastMessage = "NET target GTT triggered; waiting for the CNC position to settle.";
                    save(strategy);
                    return;
                }
                if ("CANCELLED".equalsIgnoreCase(target.status)
                        || "REJECTED".equalsIgnoreCase(target.status)
                        || "FAILED".equalsIgnoreCase(target.status)) {
                    strategy.targetSmartOrderId = "";
                    strategy.targetGttQuantity = 0;
                    strategy.lastMessage = "NET target GTT is no longer active; automatic recreation is pending.";
                    save(strategy);
                    TradeEventNotifier.notifyTradingPaused(this,
                            strategy.symbol + " target GTT needs recreation.");
                    return;
                }
            }
        }
        if (anyStopLegTriggered(token, strategy)) {'''
if state_marker not in text:
    raise RuntimeError("Could not insert target status handling")
text = text.replace(state_marker, state_insert, 1)
# If stop triggers, cancel the independent target GTT.
trigger_marker = '''            if (isTriggeredStatus(status.status)) {
                save(strategy);
                return true;
            }'''
trigger_insert = '''            if (isTriggeredStatus(status.status)) {
                cancelImageTargetGtt(token, strategy);
                save(strategy);
                return true;
            }'''
if trigger_marker not in text:
    raise RuntimeError("Could not link stop trigger to target cancellation")
text = text.replace(trigger_marker, trigger_insert, 1)
# Early/timed exit must cancel target GTT before cancelling stops and market selling.
exit_marker = '''        for (Strategy.StopLeg leg : strategy.stopLegs) {'''
exit_insert = '''        if (!cancelImageTargetGtt(token, strategy)) {
            strategy.lastMessage = label + " requested, but target GTT cancellation was not confirmed. No duplicate sell was submitted.";
            save(strategy);
            return;
        }

        for (Strategy.StopLeg leg : strategy.stopLegs) {'''
# Replace the first occurrence within executeExit, not anyStopLegTriggered. Use index after executeExit.
idx = text.find("    private void executeExit(")
if idx < 0:
    raise RuntimeError("Could not find executeExit")
sub = text[idx:]
if exit_marker not in sub:
    raise RuntimeError("Could not add target cancellation to executeExit")
sub = sub.replace(exit_marker, exit_insert, 1)
text = text[:idx] + sub
# Insert helper methods before anyStopLegTriggered.
helper_marker = '''    private boolean anyStopLegTriggered(String token, Strategy strategy) {'''
helpers = r'''    private boolean imageEntryIsFinal(Strategy strategy) {
        return strategy.observedFilledQuantity >= strategy.requestedQuantity
                || !strategy.hasPendingEntryHandle()
                || isEntryCutoffReached(strategy);
    }

    private boolean createImageTargetGtt(String token, Strategy strategy) {
        GrowwClient.ApiResult target = GrowwClient.createTargetGtt(token, strategy,
                strategy.observedFilledQuantity);
        if (!target.success) {
            strategy.lastMessage = "Target GTT retry pending. Stop-loss protection remains active. "
                    + target.message;
            save(strategy);
            AppPrefs.log(this, "NET TARGET GTT RETRY PENDING",
                    strategy.symbol + " • " + strategy.lastMessage);
            TradeEventNotifier.notifyTradingPaused(this,
                    strategy.symbol + " target GTT could not be confirmed.");
            return false;
        }
        strategy.targetSmartOrderId = target.id;
        strategy.targetGttQuantity = strategy.observedFilledQuantity;
        strategy.targetGttStatus = "ACTIVE";
        strategy.lastMessage = "Stop-loss and 6% NET target GTTs are active for "
                + strategy.observedFilledQuantity + " shares.";
        save(strategy);
        AppPrefs.log(this, "NET 6% TARGET GTT CONFIRMED ACTIVE",
                strategy.symbol + " • " + target.message);
        return true;
    }

    private boolean cancelImageTargetGtt(String token, Strategy strategy) {
        if (!strategy.isImageBatch() || strategy.targetSmartOrderId == null
                || strategy.targetSmartOrderId.isEmpty()) return true;
        GrowwClient.SmartStatus before = GrowwClient.getGtt(token,
                strategy.targetSmartOrderId);
        if (before.success && ("CANCELLED".equalsIgnoreCase(before.status)
                || isTriggeredStatus(before.status))) {
            if ("CANCELLED".equalsIgnoreCase(before.status)) {
                strategy.targetSmartOrderId = "";
                strategy.targetGttQuantity = 0;
            }
            return true;
        }
        GrowwClient.ApiResult cancel = GrowwClient.cancelGtt(token,
                strategy.targetSmartOrderId);
        if (!cancel.success) return false;
        for (int i = 0; i < 6; i++) {
            GrowwClient.SmartStatus status = GrowwClient.getGtt(token,
                    strategy.targetSmartOrderId);
            if (status.success && "CANCELLED".equalsIgnoreCase(status.status)) {
                strategy.targetGttStatus = "CANCELLED";
                strategy.targetSmartOrderId = "";
                strategy.targetGttQuantity = 0;
                return true;
            }
            sleep(250L);
        }
        return false;
    }

    private void cancelAllStopLegsAfterTarget(String token, Strategy strategy) {
        boolean allCancelled = true;
        for (Strategy.StopLeg leg : strategy.stopLegs) {
            GrowwClient.SmartStatus status = GrowwClient.getGtt(token, leg.smartOrderId);
            if (status.success && "CANCELLED".equalsIgnoreCase(status.status)) continue;
            if (status.success && isTriggeredStatus(status.status)) {
                allCancelled = false;
                continue;
            }
            GrowwClient.ApiResult cancel = GrowwClient.cancelGtt(token, leg.smartOrderId);
            if (!cancel.success) allCancelled = false;
            else leg.status = "CANCELLED";
        }
        if (!allCancelled) TradeEventNotifier.notifyTradingPaused(this,
                strategy.symbol + " target triggered but stop-loss cancellation needs verification.");
    }

'''
if helper_marker not in text:
    raise RuntimeError("Could not insert target helpers")
text = text.replace(helper_marker, helpers + helper_marker, 1)
# Pause alert after stop-loss retry failure.
text = text.replace(
    '                AppPrefs.log(this, "STOP-LOSS RETRY PENDING — ARMED RETAINED",\n'
    '                        strategy.symbol + " • " + strategy.lastMessage\n'
    '                                + " New entries are paused, but the 24×7 armed preference remains ON.");',
    '                AppPrefs.log(this, "STOP-LOSS RETRY PENDING — ARMED RETAINED",\n'
    '                        strategy.symbol + " • " + strategy.lastMessage\n'
    '                                + " New entries are paused, but the 24×7 armed preference remains ON.");\n'
    '                TradeEventNotifier.notifyTradingPaused(this,\n'
    '                        strategy.symbol + " has filled shares awaiting stop-loss protection.");',
    1,
)
# General pause/recovery evaluation each tick, deduplicated.
update_marker = '''            preflightAuthenticationIfDue(networkReady);
            updateNotification();'''
update_insert = '''            preflightAuthenticationIfDue(networkReady);
            updateTradingPauseAlert(active, networkReady, vpnReady, staticIpReady);
            updateNotification();'''
if update_marker not in text:
    raise RuntimeError("Could not insert pause evaluation")
text = text.replace(update_marker, update_insert, 1)
pause_helper_marker = '''    private boolean refreshPublicIpIfDue() {'''
pause_helper = r'''    private void updateTradingPauseAlert(List<Strategy> active, boolean networkReady,
                                         boolean vpnReady, boolean staticIpReady) {
        if (!AppPrefs.isArmed(this)) return;
        String reason = null;
        if (!networkReady) reason = "Network is unavailable.";
        else if (!vpnReady) reason = "Surfshark Dedicated IP VPN is disconnected.";
        else if (!staticIpReady) reason = "The current public IP is not the verified Groww-whitelisted IP.";
        else if (!AppPrefs.isAuthVerifiedToday(this)) reason = "Groww authentication is not verified for today.";
        if (reason == null) {
            for (Strategy strategy : active) {
                if (strategy.observedFilledQuantity > strategy.protectedQuantity) {
                    reason = strategy.symbol + " has an unprotected filled quantity.";
                    break;
                }
                if (strategy.isImageBatch() && strategy.observedFilledQuantity > 0
                        && imageEntryIsFinal(strategy) && strategy.targetSmartOrderId.isEmpty()) {
                    reason = strategy.symbol + " is waiting for its automatic 6% NET target GTT.";
                    break;
                }
            }
        }
        if (reason == null) TradeEventNotifier.clearPause(this);
        else TradeEventNotifier.notifyTradingPaused(this, reason);
    }

'''
if pause_helper_marker not in text:
    raise RuntimeError("Could not insert pause helper")
text = text.replace(pause_helper_marker, pause_helper + pause_helper_marker, 1)
write(monitor, text)


# Notification intake also surfaces a single pause alert when a broker gate rejects a signal.
listener = JAVA / "ProductionNotificationService.java"
text = read(listener)
old = '''    private void rejectAndDisarm(String reason, String summary) {
        AppPrefs.log(this, "REJECTED — ARMED, WAITING FOR GATE",
                summary + "\n" + reason
                        + " Armed state remains ON; this notification was not submitted.");
    }'''
new = '''    private void rejectAndDisarm(String reason, String summary) {
        AppPrefs.log(this, "REJECTED — ARMED, WAITING FOR GATE",
                summary + "\n" + reason
                        + " Armed state remains ON; this notification was not submitted.");
        TradeEventNotifier.notifyTradingPaused(this, reason);
    }'''
if old not in text:
    raise RuntimeError("Could not add intake pause notification")
text = text.replace(old, new, 1)
write(listener, text)


# Build-time assertions.
assert "versionName '2.2.0'" in read(gradle)
assert "DEFAULT_FREE_RECOMMENDATION_BUDGET = 5_000d" in read(prefs)
assert "FREE amount ₹" in read(listener)
assert "requiredSellPrice" in read(JAVA / "DeliveryChargeCalculator.java")
assert "NET 6% TARGET GTT CONFIRMED ACTIVE" in read(monitor)
assert "BUY completed" in read(JAVA / "TradeEventNotifier.java")
assert "source-built v2.2.0" in read(activity)
print("Applied Multyfi AutoBuy Pro v2.2.0 configurable FREE budget, focused alerts and image NET-target GTT flow")
