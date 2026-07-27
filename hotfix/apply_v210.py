#!/usr/bin/env python3
from pathlib import Path
import runpy

# Build on the validated 2.0.2 production rules (which include 2.0.1 protection recovery).
runpy.run_path("hotfix/apply_v202.py", run_name="__main__")

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
        raise RuntimeError(f"Expected exactly one match in {path}: found {count}\n{old[:200]}")
    write(path, text.replace(old, new, 1))


# Release identity and bundled on-device OCR model.
gradle = ROOT / "app/build.gradle"
replace_once(gradle, "versionCode 202", "versionCode 210")
replace_once(gradle, "versionName '2.0.2'", "versionName '2.1.0'")
replace_once(
    gradle,
    "dependencies {\n    testImplementation 'junit:junit:4.13.2'\n}",
    "dependencies {\n    implementation 'com.google.mlkit:text-recognition:16.0.1'\n    testImplementation 'junit:junit:4.13.2'\n}",
)

# Generic, fail-closed parser for labelled recommendation blocks and compact table rows.
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
    private static final Pattern TARGET = Pattern.compile(
            "(?i)(?:target(?:\\s*\\d+)?(?:\\s*price)?|sell\\s*(?:price|point)|exit\\s*(?:price|point))\\s*[:\\-]\\s*(?:₹|rs\\.?|inr)?\\s*([0-9,]+(?:\\.[0-9]+)?)");
    private static final Pattern STOP = Pattern.compile(
            "(?i)(?:stop\\s*loss|stoploss|s\\.?l\\.?)\\s*[:\\-]\\s*(?:₹|rs\\.?|inr)?\\s*([0-9,]+(?:\\.[0-9]+)?)");
    private static final Pattern QTY = Pattern.compile(
            "(?i)(?:qty|quantity|units?|shares?)\\s*[:\\-]?\\s*([0-9]{1,5})");
    private static final Pattern TABLE_ROW = Pattern.compile(
            "(?i)^\\s*([A-Z][A-Z0-9&._\\-]{0,24})\\s+(?:₹|rs\\.?|inr)?\\s*([0-9,]+(?:\\.[0-9]+)?(?:\\s*(?:-|–|—|to)\\s*[0-9,]+(?:\\.[0-9]+)?)?)\\s+(?:₹|rs\\.?|inr)?\\s*([0-9,]+(?:\\.[0-9]+)?)\\s+(?:₹|rs\\.?|inr)?\\s*([0-9,]+(?:\\.[0-9]+)?)(?:\\s+(?:qty\\s*)?([0-9]{1,5}))?\\s*$");
    private static final Pattern RANGE_VALUE = Pattern.compile(
            "([0-9,]+(?:\\.[0-9]+)?)\\s*(?:-|–|—|to)\\s*([0-9,]+(?:\\.[0-9]+)?)", Pattern.CASE_INSENSITIVE);

    private ImageOrderParser() { }

    static ParseResult parse(String rawText, int defaultQuantity) {
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

        String text = normalise(rawText);
        Matcher stockMatcher = STOCK.matcher(text);
        List<Integer> starts = new ArrayList<>();
        while (stockMatcher.find()) starts.add(stockMatcher.start());
        if (!starts.isEmpty()) {
            for (int i = 0; i < starts.size() && orders.size() < MAX_ORDERS; i++) {
                int end = i + 1 < starts.size() ? starts.get(i + 1) : text.length();
                parseLabelledBlock(text.substring(starts.get(i), end), defaultQuantity,
                        i + 1, orders, errors);
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
                Matcher matcher = TABLE_ROW.matcher(value);
                if (!matcher.matches()) continue;
                String symbol = matcher.group(1).toUpperCase(Locale.US);
                double[] entry = parseEntryValue(matcher.group(2));
                double target = price(matcher.group(3));
                double stop = price(matcher.group(4));
                int quantity = matcher.group(5) == null ? defaultQuantity : integer(matcher.group(5));
                boolean defaulted = matcher.group(5) == null;
                addValidated(symbol, entry, target, stop, quantity, defaulted,
                        "table row " + row, orders, errors);
            }
        }

        Set<String> symbols = new HashSet<>();
        List<OrderDraft> unique = new ArrayList<>();
        for (OrderDraft order : orders) {
            if (!symbols.add(order.symbol)) {
                errors.add(order.symbol + ": duplicate symbol in the image; only the first row is retained.");
            } else {
                unique.add(order);
            }
        }
        if (unique.size() >= MAX_ORDERS) {
            errors.add("Only the first " + MAX_ORDERS + " valid orders are accepted per image.");
        }
        return new ParseResult(unique, errors);
    }

    private static void parseLabelledBlock(String block, int defaultQuantity, int index,
                                           List<OrderDraft> orders, List<String> errors) {
        Matcher stock = STOCK.matcher(block);
        if (!stock.find()) return;
        String symbol = stock.group(1).toUpperCase(Locale.US).trim();
        double[] entry = parseLabelledEntry(block);
        double target = first(TARGET, block);
        double stop = first(STOP, block);
        Matcher qty = QTY.matcher(block);
        int quantity = qty.find() ? integer(qty.group(1)) : defaultQuantity;
        addValidated(symbol, entry, target, stop, quantity, !qty.find(),
                "recommendation " + index, orders, errors);
    }

    private static void addValidated(String symbol, double[] entry, double target, double stop,
                                     int quantity, boolean quantityDefaulted, String source,
                                     List<OrderDraft> orders, List<String> errors) {
        if (symbol == null || symbol.isEmpty() || entry == null || target <= 0d || stop <= 0d) {
            errors.add(source + ": missing symbol, entry, target or stop-loss.");
            return;
        }
        double low = Math.min(entry[0], entry[1]);
        double high = Math.max(entry[0], entry[1]);
        if (quantity < 1 || quantity > 10_000) {
            errors.add(symbol + ": quantity must be between 1 and 10,000.");
            return;
        }
        if (low <= 0d || high <= 0d || target <= high || stop >= low) {
            errors.add(symbol + ": expected stop-loss < entry and target > entry; row rejected.");
            return;
        }
        orders.add(new OrderDraft(symbol,
                SignalParser.floorToTick(low, 0.05d),
                SignalParser.floorToTick(high, 0.05d),
                SignalParser.floorToTick(target, 0.05d),
                SignalParser.floorToTick(stop, 0.05d),
                quantity, quantityDefaulted));
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
        return lower.contains("stock") && lower.contains("entry")
                && lower.contains("target") && (lower.contains("stop") || lower.contains("sl"));
    }

    private static double first(Pattern pattern, String text) {
        Matcher matcher = pattern.matcher(text);
        return matcher.find() ? price(matcher.group(1)) : -1d;
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
        return value.replace('\r', '\n')
                .replace('—', '-')
                .replace('–', '-')
                .replaceAll("(?i)\\bR[S5]\\.?\\s*", "₹")
                .replaceAll("[ \\t]+", " ")
                .replaceAll("\\n{3,}", "\\n\\n")
                .trim();
    }

    static final class OrderDraft {
        final String symbol;
        final double entryLow;
        final double entryHigh;
        final double target;
        final double stopLoss;
        final int quantity;
        final boolean quantityDefaulted;

        OrderDraft(String symbol, double entryLow, double entryHigh, double target,
                   double stopLoss, int quantity, boolean quantityDefaulted) {
            this.symbol = symbol;
            this.entryLow = entryLow;
            this.entryHigh = entryHigh;
            this.target = target;
            this.stopLoss = stopLoss;
            this.quantity = quantity;
            this.quantityDefaulted = quantityDefaulted;
        }

        double maximumValue() { return entryHigh * quantity; }

        String summary() {
            return symbol + " • qty " + quantity + (quantityDefaulted ? " (default)" : "")
                    + " • entry ₹" + money(entryLow) + "–₹" + money(entryHigh)
                    + " • target ₹" + money(target) + " • SL ₹" + money(stopLoss)
                    + " • max ₹" + money(maximumValue());
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
        return Math.rint(value) == value
                ? String.format(Locale.US, "%.0f", value)
                : String.format(Locale.US, "%.2f", value);
    }
}
''')

write(JAVA / "ImageBatchExecutor.java", r'''package com.suhas.multyfiautobuy.stable;

import android.content.Context;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

final class ImageBatchExecutor {
    static final double MAX_BATCH_VALUE = 500_000d;
    static final long ENTRY_EXPIRY_MS = 35L * 24L * 60L * 60L * 1000L;

    private ImageBatchExecutor() { }

    static BatchResult submit(Context context, List<ImageOrderParser.OrderDraft> orders) {
        List<String> accepted = new ArrayList<>();
        List<String> failed = new ArrayList<>();
        if (orders == null || orders.isEmpty()) {
            failed.add("No validated image orders were supplied.");
            return new BatchResult(accepted, failed);
        }
        if (orders.size() > ImageOrderParser.MAX_ORDERS) {
            failed.add("Batch exceeds the " + ImageOrderParser.MAX_ORDERS + "-order limit.");
            return new BatchResult(accepted, failed);
        }
        double total = 0d;
        for (ImageOrderParser.OrderDraft order : orders) total += order.maximumValue();
        if (total > MAX_BATCH_VALUE + 0.01d) {
            failed.add("Batch maximum value ₹" + money(total)
                    + " exceeds the ₹5,00,000 image-import safety cap.");
            return new BatchResult(accepted, failed);
        }
        if (!NetworkUtil.isNetworkAvailable(context) || !NetworkUtil.isVpnActive(context)) {
            failed.add("Network and Surfshark Dedicated IP VPN must be active.");
            return new BatchResult(accepted, failed);
        }
        if (!verifyStaticIp(context)) {
            failed.add("Current public IP does not match the Groww-whitelisted Dedicated IP.");
            return new BatchResult(accepted, failed);
        }
        String token = TokenManager.validToken(context);
        if (token.isEmpty()) {
            failed.add("No valid Groww access token is available.");
            return new BatchResult(accepted, failed);
        }
        GrowwClient.ApiResult profile = GrowwClient.verifyProfile(token);
        if (!profile.success) {
            failed.add("Groww profile/DDPI verification failed: " + profile.message);
            return new BatchResult(accepted, failed);
        }
        AppPrefs.setAuthVerified(context, profile.id);

        long batchNow = System.currentTimeMillis();
        for (int i = 0; i < orders.size(); i++) {
            ImageOrderParser.OrderDraft order = orders.get(i);
            try {
                if (StrategyStore.hasActiveSymbol(context, order.symbol)) {
                    failed.add(order.symbol + ": an active app-managed strategy already exists.");
                    continue;
                }
                if (order.maximumValue() > AppPrefs.MAX_ORDER_VALUE + 0.01d) {
                    failed.add(order.symbol + ": order value exceeds ₹5,00,000.");
                    continue;
                }
                GrowwClient.DoubleResult ltp = GrowwClient.getLtp(token, order.symbol);
                if (!ltp.success || ltp.value <= 0d) {
                    failed.add(order.symbol + ": LTP unavailable — " + ltp.message);
                    continue;
                }
                GrowwClient.IntResult baseline = GrowwClient.getNetPositionQuantity(
                        token, order.symbol, "CNC");
                if (!baseline.success) {
                    failed.add(order.symbol + ": position baseline failed — " + baseline.message);
                    continue;
                }
                String digest = digest(order.symbol + "|" + order.entryLow + "|"
                        + order.entryHigh + "|" + order.target + "|" + order.stopLoss
                        + "|" + order.quantity + "|" + batchNow + "|" + i);
                String eventId = "img-" + digest.substring(0, 20);
                String reference = "IMG" + AppPrefs.compactIstDate()
                        + digest.substring(0, 6).toUpperCase(Locale.US);
                double maxBuy = SignalParser.floorToTick(order.entryHigh, 0.05d);
                SignalParser.ParsedSignal signal = new SignalParser.ParsedSignal(
                        eventId, reference, order.symbol, "IMAGE_BATCH", "CNC",
                        order.entryLow, order.entryHigh, order.entryLow, maxBuy,
                        0d, order.target, order.stopLoss, batchNow,
                        "User-confirmed OCR image batch");
                GrowwClient.ApiResult created = GrowwClient.createEntryGtt(
                        token, signal, order.quantity, ltp.value);
                if (!created.success) {
                    failed.add(order.symbol + ": entry GTT failed — " + created.message);
                    continue;
                }
                Strategy strategy = new Strategy(eventId, order.symbol, "IMAGE_BATCH", "CNC",
                        order.quantity, order.target, order.stopLoss, baseline.value,
                        reference, created.id, "", "GTT", batchNow,
                        batchNow + ENTRY_EXPIRY_MS);
                StrategyStore.upsert(context, strategy);
                AppPrefs.markProcessed(context, eventId);
                accepted.add(order.symbol + " • qty " + order.quantity
                        + " • GTT " + created.id);
                AppPrefs.log(context, "IMAGE BATCH ENTRY GTT ACTIVE",
                        order.summary() + " • smart order " + created.id
                                + " • expires locally after 35 days if never filled."
                                + " Stop-loss and target monitoring start automatically after the actual fill.");
                StrategyMonitorService.requestImmediateTick(context, eventId);
                sleep(300L);
            } catch (Exception e) {
                failed.add(order.symbol + ": " + e.getClass().getSimpleName()
                        + " — " + safeMessage(e));
            }
        }
        StrategyMonitorService.ensureRunning(context);
        return new BatchResult(accepted, failed);
    }

    private static boolean verifyStaticIp(Context context) {
        if (!AppPrefs.isStaticConfirmed(context) || AppPrefs.expectedIp(context).isEmpty()) {
            return false;
        }
        if (AppPrefs.isIpRecentlyVerified(context)) return true;
        try {
            String actual = NetworkUtil.fetchPublicIp();
            boolean matched = AppPrefs.expectedIp(context).equals(actual);
            AppPrefs.setIpVerification(context, actual, matched);
            return matched;
        } catch (Exception e) {
            AppPrefs.setIpVerifiedAt(context, 0L);
            return false;
        }
    }

    private static String digest(String value) throws Exception {
        byte[] bytes = MessageDigest.getInstance("SHA-256")
                .digest(value.getBytes(StandardCharsets.UTF_8));
        StringBuilder builder = new StringBuilder();
        for (byte b : bytes) builder.append(String.format(Locale.US, "%02x", b));
        return builder.toString();
    }

    private static void sleep(long millis) {
        try { Thread.sleep(millis); }
        catch (InterruptedException e) { Thread.currentThread().interrupt(); }
    }

    private static String safeMessage(Exception e) {
        return e.getMessage() == null ? e.toString() : e.getMessage();
    }

    private static String money(double value) {
        return Math.rint(value) == value
                ? String.format(Locale.US, "%.0f", value)
                : String.format(Locale.US, "%.2f", value);
    }

    static final class BatchResult {
        final List<String> accepted;
        final List<String> failed;
        BatchResult(List<String> accepted, List<String> failed) {
            this.accepted = accepted;
            this.failed = failed;
        }
        boolean anyAccepted() { return !accepted.isEmpty(); }
        String summary() {
            StringBuilder out = new StringBuilder();
            out.append("Accepted ").append(accepted.size())
                    .append(" • failed/skipped ").append(failed.size());
            for (String value : accepted) out.append("\n✓ ").append(value);
            for (String value : failed) out.append("\n✗ ").append(value);
            return out.toString();
        }
    }
}
''')

# Unit tests for labelled and table OCR formats.
write(TEST / "ImageOrderParserTest.java", r'''package com.suhas.multyfiautobuy.stable;

import org.junit.Test;

import static org.junit.Assert.*;

public class ImageOrderParserTest {
    @Test public void parsesMultipleLabelledRecommendations() {
        String text = "Stock Name: TCS\nEntry Range: 3200-3220\nTarget: 3350\nStop Loss: 3150\nQty: 2\n\n"
                + "Stock Name: ITC\nEntry: 410\nTarget: 450\nSL: 390";
        ImageOrderParser.ParseResult result = ImageOrderParser.parse(text, 5);
        assertEquals(2, result.orders.size());
        assertEquals(2, result.orders.get(0).quantity);
        assertEquals(5, result.orders.get(1).quantity);
        assertTrue(result.orders.get(1).quantityDefaulted);
    }

    @Test public void parsesCompactTableRows() {
        String text = "STOCK ENTRY TARGET STOP QTY\nTCS 3200-3220 3350 3150 2\nITC 410 450 390 10";
        ImageOrderParser.ParseResult result = ImageOrderParser.parse(text, 1);
        assertEquals(2, result.orders.size());
        assertEquals("TCS", result.orders.get(0).symbol);
        assertEquals(10, result.orders.get(1).quantity);
    }

    @Test public void rejectsUnsafePriceRelationships() {
        String text = "Stock Name: TCS\nEntry: 3200\nTarget: 3100\nStop Loss: 3300\nQty: 2";
        ImageOrderParser.ParseResult result = ImageOrderParser.parse(text, 1);
        assertTrue(result.orders.isEmpty());
        assertFalse(result.errors.isEmpty());
    }
}
''')

# Dashboard: photo picker, OCR editor, preview and explicit real-order confirmation.
activity = JAVA / "ProductionActivity.java"
text = read(activity)
text = text.replace("release 2.0.2", "release 2.1.0")
text = text.replace("source-built v2.0.2", "source-built v2.1.0")
text = text.replace("import android.graphics.Color;", "import android.graphics.Color;\nimport android.net.Uri;")
text = text.replace("import java.util.Calendar;", "import java.util.ArrayList;\nimport java.util.Calendar;\nimport java.util.List;")
text = text.replace("import java.util.concurrent.Executors;", "import java.util.concurrent.Executors;\n\nimport com.google.mlkit.vision.common.InputImage;\nimport com.google.mlkit.vision.text.TextRecognition;\nimport com.google.mlkit.vision.text.TextRecognizer;\nimport com.google.mlkit.vision.text.latin.TextRecognizerOptions;")
text = text.replace("    private static final String LAST_TEST_SYMBOL = \"last_test_symbol\";",
                    "    private static final String LAST_TEST_SYMBOL = \"last_test_symbol\";\n"
                    "    private static final int PICK_ORDER_IMAGE = 2100;")
text = text.replace("    private TextView growwTestStatus;",
                    "    private TextView growwTestStatus;\n    private TextView imageImportStatus;")
text = text.replace("    private EditText testSymbolInput;",
                    "    private EditText testSymbolInput;\n    private EditText batchDefaultQuantityInput;\n    private Button imageImportButton;")

# Add onActivityResult after onDestroy.
old_destroy = '''    @Override
    protected void onDestroy() {
        executor.shutdownNow();
        super.onDestroy();
    }

'''
new_destroy = old_destroy + '''    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == PICK_ORDER_IMAGE && resultCode == RESULT_OK
                && data != null && data.getData() != null) {
            processOrderImage(data.getData());
        }
    }

'''
if old_destroy not in text:
    raise RuntimeError("Could not insert image picker result handler")
text = text.replace(old_destroy, new_destroy, 1)

card_marker = '''        root.addView(growwCard, sectionMargin());

        LinearLayout networkCard = card();'''
card_insert = '''        root.addView(growwCard, sectionMargin());

        LinearLayout imageCard = card();
        imageCard.addView(sectionTitle("MONTHLY IMAGE GTT IMPORT"));
        imageCard.addView(label(
                "Choose a screenshot or photo containing stock, entry, target, stop-loss and optional quantity. OCR runs on-device. You can correct the recognised text, then review every order before any real Groww request. Confirmed rows create CNC entry GTTs at any time; unfilled entries expire locally after 35 days. After a fill, stop-loss and target handling are automatic.",
                13, MUTED, false), topMargin(6));
        batchDefaultQuantityInput = textField("Default quantity when the image has no Qty", "1");
        batchDefaultQuantityInput.setInputType(InputType.TYPE_CLASS_NUMBER);
        imageCard.addView(batchDefaultQuantityInput, topMargin(12));
        imageImportButton = warningButton("UPLOAD ORDER-LIST IMAGE");
        imageImportButton.setOnClickListener(v -> chooseOrderImage());
        imageCard.addView(imageImportButton, topMargin(10));
        imageImportStatus = label("No image imported in this installation.", 12, MUTED, false);
        imageImportStatus.setTextIsSelectable(true);
        imageCard.addView(imageImportStatus, topMargin(9));
        root.addView(imageCard, sectionMargin());

        LinearLayout networkCard = card();'''
if card_marker not in text:
    raise RuntimeError("Could not insert image import card")
text = text.replace(card_marker, card_insert, 1)

methods_marker = '''    private void detectAndVerifyIp(Button button) {'''
methods = r'''    private void chooseOrderImage() {
        Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT);
        intent.addCategory(Intent.CATEGORY_OPENABLE);
        intent.setType("image/*");
        try { startActivityForResult(intent, PICK_ORDER_IMAGE); }
        catch (Exception e) { toast("Could not open image picker: " + safeMessage(e)); }
    }

    private void processOrderImage(Uri uri) {
        imageImportButton.setEnabled(false);
        imageImportStatus.setText("Reading image on-device…");
        imageImportStatus.setTextColor(AMBER);
        try {
            InputImage image = InputImage.fromFilePath(this, uri);
            TextRecognizer recognizer = TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS);
            recognizer.process(image)
                    .addOnSuccessListener(result -> showOcrEditor(result.getText()))
                    .addOnFailureListener(error -> {
                        imageImportStatus.setText("OCR failed: " + safeMessage(error));
                        imageImportStatus.setTextColor(RED);
                        imageImportButton.setEnabled(true);
                    })
                    .addOnCompleteListener(task -> recognizer.close());
        } catch (Exception e) {
            imageImportStatus.setText("Could not read image: " + safeMessage(e));
            imageImportStatus.setTextColor(RED);
            imageImportButton.setEnabled(true);
        }
    }

    private void showOcrEditor(String recognisedText) {
        imageImportButton.setEnabled(true);
        if (recognisedText == null || recognisedText.trim().isEmpty()) {
            imageImportStatus.setText("No readable text was found. Use a sharper screenshot.");
            imageImportStatus.setTextColor(RED);
            return;
        }
        EditText editor = new EditText(this);
        editor.setText(recognisedText);
        editor.setTextColor(TEXT);
        editor.setHintTextColor(MUTED);
        editor.setTextSize(13f);
        editor.setGravity(Gravity.TOP | Gravity.START);
        editor.setMinLines(10);
        editor.setInputType(InputType.TYPE_CLASS_TEXT
                | InputType.TYPE_TEXT_FLAG_MULTI_LINE
                | InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS);
        editor.setBackground(rounded(FIELD, 12, Color.rgb(54, 75, 108), 1));
        editor.setPadding(dp(12), dp(12), dp(12), dp(12));
        LinearLayout wrapper = column();
        wrapper.setPadding(dp(16), dp(8), dp(16), 0);
        wrapper.addView(editor, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, dp(360)));
        new AlertDialog.Builder(this)
                .setTitle("Review OCR text")
                .setMessage("Correct any OCR mistakes before parsing. Supported labels include Stock Name/Symbol, Entry/Entry Range, Target, Stop Loss/SL and Qty/Quantity. Compact rows are also supported as: SYMBOL ENTRY TARGET STOP QTY.")
                .setView(wrapper)
                .setNegativeButton("CANCEL", null)
                .setPositiveButton("PARSE & REVIEW", (dialog, which) ->
                        reviewImageOrders(editor.getText().toString()))
                .show();
    }

    private void reviewImageOrders(String correctedText) {
        int defaultQuantity;
        try {
            defaultQuantity = Integer.parseInt(text(batchDefaultQuantityInput));
        } catch (Exception e) {
            toast("Enter a default quantity between 1 and 10,000.");
            return;
        }
        ImageOrderParser.ParseResult parsed = ImageOrderParser.parse(correctedText, defaultQuantity);
        if (parsed.orders.isEmpty()) {
            String message = parsed.errors.isEmpty()
                    ? "No complete orders were detected."
                    : TextUtils.join("\n", parsed.errors);
            imageImportStatus.setText("No valid rows. " + message);
            imageImportStatus.setTextColor(RED);
            new AlertDialog.Builder(this).setTitle("No valid orders")
                    .setMessage(message).setPositiveButton("OK", null).show();
            return;
        }
        double total = 0d;
        StringBuilder summary = new StringBuilder();
        for (int i = 0; i < parsed.orders.size(); i++) {
            ImageOrderParser.OrderDraft order = parsed.orders.get(i);
            total += order.maximumValue();
            summary.append(i + 1).append(". ").append(order.summary()).append("\n");
        }
        if (!parsed.errors.isEmpty()) {
            summary.append("\nRejected/notes:\n");
            for (String error : parsed.errors) summary.append("• ").append(error).append("\n");
        }
        summary.append("\nMaximum planned batch value: ₹").append(money(total))
                .append("\nSafety cap: ₹5,00,000")
                .append("\n\nThis creates real CNC entry GTTs. CASH OCO is not used. After each actual fill, the app creates/verifies the stop-loss GTT and monitors the target for automatic exit.");
        if (total > ImageBatchExecutor.MAX_BATCH_VALUE + 0.01d) {
            imageImportStatus.setText("Batch blocked: maximum value exceeds ₹5,00,000.");
            imageImportStatus.setTextColor(RED);
            new AlertDialog.Builder(this).setTitle("Batch value blocked")
                    .setMessage(summary.toString()).setPositiveButton("OK", null).show();
            return;
        }
        List<ImageOrderParser.OrderDraft> confirmed = new ArrayList<>(parsed.orders);
        new AlertDialog.Builder(this)
                .setTitle("Create " + confirmed.size() + " real entry GTTs?")
                .setMessage(summary.toString())
                .setNegativeButton("CANCEL", null)
                .setPositiveButton("CREATE GTTs", (dialog, which) -> submitImageOrders(confirmed))
                .show();
    }

    private void submitImageOrders(List<ImageOrderParser.OrderDraft> orders) {
        setBusy(imageImportButton, true, "CREATING GTTs…", "UPLOAD ORDER-LIST IMAGE");
        imageImportStatus.setText("Submitting validated rows sequentially…");
        imageImportStatus.setTextColor(AMBER);
        executor.execute(() -> {
            ImageBatchExecutor.BatchResult result = ImageBatchExecutor.submit(this, orders);
            String message = result.summary();
            AppPrefs.log(this, result.anyAccepted()
                    ? "IMAGE BATCH SUBMISSION COMPLETE" : "IMAGE BATCH SUBMISSION FAILED", message);
            runOnUiThread(() -> {
                setBusy(imageImportButton, false, "", "UPLOAD ORDER-LIST IMAGE");
                imageImportStatus.setText(message);
                imageImportStatus.setTextColor(result.anyAccepted() ? GREEN : RED);
                new AlertDialog.Builder(this)
                        .setTitle(result.anyAccepted() ? "Batch submitted" : "No GTT created")
                        .setMessage(message)
                        .setPositiveButton("OK", null)
                        .show();
                refreshStatus();
            });
        });
    }

'''
if methods_marker not in text:
    raise RuntimeError("Could not insert image import methods")
text = text.replace(methods_marker, methods + methods_marker, 1)
write(activity, text)

print("Applied Multyfi AutoBuy Pro v2.1.0 on-device image OCR batch GTT flow")
