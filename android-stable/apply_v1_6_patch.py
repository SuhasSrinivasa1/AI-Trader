from pathlib import Path

ROOT = Path(__file__).resolve().parent
JAVA = ROOT / "app/src/main/java/com/suhas/multyfiautobuy/stable"
RES = ROOT / "app/src/main/res"
TEST = ROOT / "app/src/test/java/com/suhas/multyfiautobuy/stable"


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected exactly one match in {path}: found {count}\n---\n{old[:240]}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def insert_before(path: Path, marker: str, content: str) -> None:
    replace_once(path, marker, content + marker)


# -----------------------------------------------------------------------------
# Pure policy helper (also unit-testable without Android Context)
# -----------------------------------------------------------------------------
entry_policy = r'''package com.suhas.multyfiautobuy.stable;

import java.util.Calendar;
import java.util.Locale;
import java.util.TimeZone;

final class EntryPolicy {
    private static final TimeZone IST = TimeZone.getTimeZone("Asia/Kolkata");

    private EntryPolicy() { }

    static boolean isInWindow(long epochMillis, int startMinute, int endMinute) {
        if (!isValidWindow(startMinute, endMinute)) return false;
        Calendar calendar = Calendar.getInstance(IST, Locale.US);
        calendar.setTimeInMillis(epochMillis);
        int day = calendar.get(Calendar.DAY_OF_WEEK);
        if (day == Calendar.SATURDAY || day == Calendar.SUNDAY) return false;
        int minute = calendar.get(Calendar.HOUR_OF_DAY) * 60
                + calendar.get(Calendar.MINUTE);
        return minute >= startMinute && minute < endMinute;
    }

    static boolean isValidWindow(int startMinute, int endMinute) {
        return startMinute >= 0 && startMinute < 24 * 60
                && endMinute > 0 && endMinute <= 24 * 60
                && startMinute < endMinute;
    }

    static int quantity(double maximumBuyPrice, boolean earlyWindow,
                        double earlyBudget, int lateQuantity, int maximumQuantity) {
        if (maximumBuyPrice <= 0d || maximumQuantity < 1) return 0;
        if (!earlyWindow) return Math.max(0, Math.min(maximumQuantity, lateQuantity));
        int quantity = (int) Math.floor(earlyBudget / maximumBuyPrice);
        return Math.max(0, Math.min(maximumQuantity, quantity));
    }

    static int parseMinuteOfDay(String value) {
        if (value == null) return -1;
        String clean = value.trim();
        String[] parts = clean.split(":", -1);
        if (parts.length != 2) return -1;
        try {
            int hour = Integer.parseInt(parts[0]);
            int minute = Integer.parseInt(parts[1]);
            if (hour < 0 || hour > 23 || minute < 0 || minute > 59) return -1;
            return hour * 60 + minute;
        } catch (NumberFormatException e) {
            return -1;
        }
    }

    static String formatMinuteOfDay(int minuteOfDay) {
        int value = Math.max(0, Math.min(24 * 60 - 1, minuteOfDay));
        return String.format(Locale.US, "%02d:%02d", value / 60, value % 60);
    }
}
'''
(JAVA / "EntryPolicy.java").write_text(entry_policy, encoding="utf-8")

# -----------------------------------------------------------------------------
# Preferences: configurable 09:00-10:00 budget mode + post-window fixed quantity
# -----------------------------------------------------------------------------
prefs = JAVA / "AppPrefs.java"
replace_once(prefs,
'''    static final double DEFAULT_TRADE_BUDGET = 10_000d;
    static final double MIN_TRADE_BUDGET = 1_000d;
    static final double MAX_TRADE_BUDGET = 500_000d;
    static final int MAX_COMPUTED_QUANTITY = 10_000;
''',
'''    // The historical workbook supplied by the user showed a materially stronger
    // result cluster during 09:00-09:59 IST. This remains configurable in-app.
    static final double DEFAULT_TRADE_BUDGET = 10_000d;
    static final double MIN_TRADE_BUDGET = 1_000d;
    static final double MAX_TRADE_BUDGET = 500_000d;
    static final int MAX_COMPUTED_QUANTITY = 10_000;
    static final int DEFAULT_EARLY_START_MINUTE = 9 * 60;
    static final int DEFAULT_EARLY_END_MINUTE = 10 * 60;
    static final int DEFAULT_LATE_QUANTITY = 10;
    static final int MIN_LATE_QUANTITY = 1;
    static final int MAX_LATE_QUANTITY = 10_000;
    // Data-driven safety default: post-window calls are available but initially OFF.
    static final boolean DEFAULT_LATE_CALLS_ENABLED = false;
''')
replace_once(prefs,
'''    private static final String K_TRADE_BUDGET = "trade_budget";
    private static final String K_ENTRY_BUFFER = "entry_buffer_percent";
''',
'''    private static final String K_TRADE_BUDGET = "trade_budget";
    private static final String K_EARLY_START = "early_start_minute";
    private static final String K_EARLY_END = "early_end_minute";
    private static final String K_LATE_QUANTITY = "late_quantity";
    private static final String K_LATE_ENABLED = "late_calls_enabled";
    private static final String K_ENTRY_BUFFER = "entry_buffer_percent";
''')
insert_before(prefs,
'''    static double entryBufferPercent(Context context) {
''',
'''    static int earlyStartMinute(Context context) {
        return prefs(context).getInt(K_EARLY_START, DEFAULT_EARLY_START_MINUTE);
    }

    static int earlyEndMinute(Context context) {
        return prefs(context).getInt(K_EARLY_END, DEFAULT_EARLY_END_MINUTE);
    }

    static void setEntryWindow(Context context, int startMinute, int endMinute) {
        if (!EntryPolicy.isValidWindow(startMinute, endMinute)) {
            throw new IllegalArgumentException("Entry window must be a valid start/end time.");
        }
        prefs(context).edit()
                .putInt(K_EARLY_START, startMinute)
                .putInt(K_EARLY_END, endMinute)
                .apply();
    }

    static boolean isEarlyWindow(Context context, long epochMillis) {
        return EntryPolicy.isInWindow(epochMillis,
                earlyStartMinute(context), earlyEndMinute(context));
    }

    static int lateQuantity(Context context) {
        int value = prefs(context).getInt(K_LATE_QUANTITY, DEFAULT_LATE_QUANTITY);
        return isValidLateQuantity(value) ? value : DEFAULT_LATE_QUANTITY;
    }

    static boolean isValidLateQuantity(int value) {
        return value >= MIN_LATE_QUANTITY && value <= MAX_LATE_QUANTITY;
    }

    static void setLateQuantity(Context context, int value) {
        if (!isValidLateQuantity(value)) {
            throw new IllegalArgumentException("Post-window quantity must be between 1 and 10,000.");
        }
        prefs(context).edit().putInt(K_LATE_QUANTITY, value).apply();
    }

    static boolean lateCallsEnabled(Context context) {
        return prefs(context).getBoolean(K_LATE_ENABLED, DEFAULT_LATE_CALLS_ENABLED);
    }

    static void setLateCallsEnabled(Context context, boolean value) {
        prefs(context).edit().putBoolean(K_LATE_ENABLED, value).apply();
    }

    static int quantityForSignal(Context context, double maximumBuyPrice,
                                 long notificationTimeMillis) {
        return EntryPolicy.quantity(maximumBuyPrice,
                isEarlyWindow(context, notificationTimeMillis),
                tradeBudget(context), lateQuantity(context), MAX_COMPUTED_QUANTITY);
    }

''')

# -----------------------------------------------------------------------------
# UI settings
# -----------------------------------------------------------------------------
main = JAVA / "MainActivity.java"
replace_once(main,
'''    private EditText budgetInput;
    private EditText bufferInput;
''',
'''    private EditText budgetInput;
    private EditText earlyStartInput;
    private EditText earlyEndInput;
    private EditText lateQuantityInput;
    private CheckBox lateCallsEnabled;
    private EditText bufferInput;
''')
replace_once(main,
'''        budgetInput = findViewById(R.id.budgetInput);
        bufferInput = findViewById(R.id.bufferInput);
''',
'''        budgetInput = findViewById(R.id.budgetInput);
        earlyStartInput = findViewById(R.id.earlyStartInput);
        earlyEndInput = findViewById(R.id.earlyEndInput);
        lateQuantityInput = findViewById(R.id.lateQuantityInput);
        lateCallsEnabled = findViewById(R.id.lateCallsEnabled);
        bufferInput = findViewById(R.id.bufferInput);
''')
replace_once(main,
'''        budgetInput.setText(String.format(Locale.US, "%.0f",
                AppPrefs.tradeBudget(this)));
        bufferInput.setText(String.format(Locale.US, "%.2f",
                AppPrefs.entryBufferPercent(this)));
''',
'''        budgetInput.setText(String.format(Locale.US, "%.0f",
                AppPrefs.tradeBudget(this)));
        earlyStartInput.setText(EntryPolicy.formatMinuteOfDay(
                AppPrefs.earlyStartMinute(this)));
        earlyEndInput.setText(EntryPolicy.formatMinuteOfDay(
                AppPrefs.earlyEndMinute(this)));
        lateQuantityInput.setText(String.valueOf(AppPrefs.lateQuantity(this)));
        lateCallsEnabled.setChecked(AppPrefs.lateCallsEnabled(this));
        bufferInput.setText(String.format(Locale.US, "%.2f",
                AppPrefs.entryBufferPercent(this)));
''')
replace_once(main,
'''                            "S24 Ultra automation enabled: target notional ₹"
                                    + money(AppPrefs.tradeBudget(this))
                                    + ", buffer "
                                    + String.format(Locale.US, "%.2f",
                                    AppPrefs.entryBufferPercent(this))
                                    + "%, strict Multyfi early exits enabled.");
''',
'''                            "S24 Ultra automation enabled: ₹"
                                    + money(AppPrefs.tradeBudget(this)) + " during "
                                    + EntryPolicy.formatMinuteOfDay(AppPrefs.earlyStartMinute(this))
                                    + "–" + EntryPolicy.formatMinuteOfDay(AppPrefs.earlyEndMinute(this))
                                    + "; post-window "
                                    + (AppPrefs.lateCallsEnabled(this)
                                    ? AppPrefs.lateQuantity(this) + " shares" : "disabled")
                                    + "; buffer "
                                    + String.format(Locale.US, "%.2f",
                                    AppPrefs.entryBufferPercent(this))
                                    + "%; strict Multyfi early exits enabled.");
''')
replace_once(main,
'''            double budget = readBudgetInput();
            double buffer = readBufferInput();
            if (!AppPrefs.isValidTradeBudget(budget)) {
''',
'''            double budget = readBudgetInput();
            int startMinute = readTimeInput(earlyStartInput);
            int endMinute = readTimeInput(earlyEndInput);
            int lateQuantity = readLateQuantityInput();
            boolean enableLate = lateCallsEnabled.isChecked();
            double buffer = readBufferInput();
            if (!AppPrefs.isValidTradeBudget(budget)) {
''')
replace_once(main,
'''            if (!AppPrefs.isValidEntryBuffer(buffer)) {
                toast("Entry buffer must be between 0% and 2%.");
                return;
            }
''',
'''            if (!EntryPolicy.isValidWindow(startMinute, endMinute)) {
                toast("Enter a valid time window, for example 09:00 to 10:00.");
                return;
            }
            if (!AppPrefs.isValidLateQuantity(lateQuantity)) {
                toast("Post-window quantity must be between 1 and 10,000.");
                return;
            }
            if (!AppPrefs.isValidEntryBuffer(buffer)) {
                toast("Entry buffer must be between 0% and 2%.");
                return;
            }
''')
replace_once(main,
'''            AppPrefs.setTradeBudget(this, budget);
            AppPrefs.setEntryBufferPercent(this, buffer);
''',
'''            AppPrefs.setTradeBudget(this, budget);
            AppPrefs.setEntryWindow(this, startMinute, endMinute);
            AppPrefs.setLateQuantity(this, lateQuantity);
            AppPrefs.setLateCallsEnabled(this, enableLate);
            AppPrefs.setEntryBufferPercent(this, buffer);
''')
replace_once(main,
'''                    "Target trade budget ₹" + money(budget)
                            + " • entry buffer "
                            + String.format(Locale.US, "%.2f", buffer)
''',
'''                    "Early-window budget ₹" + money(budget)
                            + " • window " + EntryPolicy.formatMinuteOfDay(startMinute)
                            + "–" + EntryPolicy.formatMinuteOfDay(endMinute)
                            + " • post-window "
                            + (enableLate ? lateQuantity + " shares" : "disabled")
                            + " • entry buffer "
                            + String.format(Locale.US, "%.2f", buffer)
''')
replace_once(main,
'''            toast("Configuration saved. Target notional ₹" + money(budget)
                    + ", buffer " + String.format(Locale.US, "%.2f", buffer) + "%.");
''',
'''            toast("Configuration saved: ₹" + money(budget) + " during "
                    + EntryPolicy.formatMinuteOfDay(startMinute) + "–"
                    + EntryPolicy.formatMinuteOfDay(endMinute) + "; post-window "
                    + (enableLate ? lateQuantity + " shares" : "disabled") + ".");
''')
replace_once(main,
'''            int quantity = AppPrefs.quantityForBudget(this, signal.maxBuyPrice);
''',
'''            int quantity = AppPrefs.quantityForSignal(this, signal.maxBuyPrice,
                    validTradingTime);
''')
replace_once(main,
'''                ? "S24 Ultra is ready. Target notional ₹"
                + money(AppPrefs.tradeBudget(this)) + ", buffer "
                + String.format(Locale.US, "%.2f", AppPrefs.entryBufferPercent(this))
                + "% • strict early exit active • strategies " + activeStrategies + "."
''',
'''                ? "S24 Ultra ready. ₹" + money(AppPrefs.tradeBudget(this))
                + " during " + EntryPolicy.formatMinuteOfDay(AppPrefs.earlyStartMinute(this))
                + "–" + EntryPolicy.formatMinuteOfDay(AppPrefs.earlyEndMinute(this))
                + "; post-window " + (AppPrefs.lateCallsEnabled(this)
                ? AppPrefs.lateQuantity(this) + " shares" : "disabled")
                + "; buffer " + String.format(Locale.US, "%.2f",
                AppPrefs.entryBufferPercent(this))
                + "% • strategies " + activeStrategies + "."
''')
insert_before(main,
'''    private double readBufferInput() {
''',
'''    private int readTimeInput(EditText input) {
        return EntryPolicy.parseMinuteOfDay(text(input));
    }

    private int readLateQuantityInput() {
        String value = text(lateQuantityInput);
        if (value.isEmpty()) return AppPrefs.lateQuantity(this);
        try { return Integer.parseInt(value); }
        catch (NumberFormatException e) { return -1; }
    }

''')
replace_once(main,
'''        rulesSummary.setText("COMPLETE MULTYFI CALLS • Equity, swing, multibagger, free-equity and intraday"
                + " • Target notional ₹" + money(AppPrefs.tradeBudget(this))
                + " • Quantity = floor(budget ÷ maximum permitted buy price)"
                + " • Entry buffer "
                + String.format(Locale.US, "%.2f", AppPrefs.entryBufferPercent(this)) + "%"
                + " • Actual-fill stop-loss GTT"
                + " • Target: cancel/verify SL, then market sell"
                + " • Symbol-matched 'exiting early' alert: cancel entry/SL, verify position, market exit immediately"
                + " • No early exit without one unique active symbol"
                + " • Surfshark Dedicated IP + DDPI required");
''',
'''        rulesSummary.setText("TIME-WINDOW POLICY • "
                + EntryPolicy.formatMinuteOfDay(AppPrefs.earlyStartMinute(this))
                + "–" + EntryPolicy.formatMinuteOfDay(AppPrefs.earlyEndMinute(this))
                + ": direct marketable LIMIT BUY, target notional ₹"
                + money(AppPrefs.tradeBudget(this))
                + " • Post-window: " + (AppPrefs.lateCallsEnabled(this)
                ? AppPrefs.lateQuantity(this) + " shares with GTT/limit fallback"
                : "disabled (recommended by uploaded history)")
                + " • Product follows the signal: MIS only for explicit intraday, otherwise CNC"
                + " • Entry buffer "
                + String.format(Locale.US, "%.2f", AppPrefs.entryBufferPercent(this)) + "%"
                + " • Actual-fill stop-loss GTT"
                + " • Target or symbol-matched early exit: cancel/verify protection, reconcile position, market sell"
                + " • Surfshark Dedicated IP + DDPI required");
''')

# Replace the sizing card's inner controls.
layout = RES / "layout/activity_main.xml"
replace_once(layout,
'''            <TextView style="@style/SectionTitle" android:text="TRADE SIZING" />

            <EditText
                android:id="@+id/budgetInput"
                android:layout_width="match_parent"
                android:layout_height="54dp"
                android:background="@drawable/bg_field"
                android:digits="0123456789."
                android:hint="Target trade value in ₹ — default 10000"
                android:inputType="numberDecimal"
                android:maxLength="9"
                android:singleLine="true"
                android:textColor="@color/text_primary"
                android:textColorHint="@color/text_secondary"
                android:textSize="14sp" />

            <EditText
                android:id="@+id/bufferInput"
                android:layout_width="match_parent"
                android:layout_height="54dp"
                android:layout_marginTop="10dp"
                android:background="@drawable/bg_field"
                android:digits="0123456789."
                android:hint="Entry buffer % — default 1.5, maximum 2.0"
                android:inputType="numberDecimal"
                android:maxLength="4"
                android:singleLine="true"
                android:textColor="@color/text_primary"
                android:textColorHint="@color/text_secondary"
                android:textSize="14sp" />

            <TextView
                android:layout_width="match_parent"
                android:layout_height="wrap_content"
                android:layout_marginTop="8dp"
                android:text="Quantity is calculated automatically as floor(target value ÷ maximum permitted buy price), so the order does not exceed the configured budget."
                android:textColor="@color/text_secondary"
                android:textSize="12sp" />
''',
'''            <TextView style="@style/SectionTitle" android:text="TIME-WINDOW SIZING & ENTRY" />

            <EditText
                android:id="@+id/budgetInput"
                android:layout_width="match_parent"
                android:layout_height="54dp"
                android:background="@drawable/bg_field"
                android:digits="0123456789."
                android:hint="Early-window target value in ₹ — default 10000"
                android:inputType="numberDecimal"
                android:maxLength="9"
                android:singleLine="true"
                android:textColor="@color/text_primary"
                android:textColorHint="@color/text_secondary"
                android:textSize="14sp" />

            <LinearLayout
                android:layout_width="match_parent"
                android:layout_height="wrap_content"
                android:layout_marginTop="10dp"
                android:orientation="horizontal">

                <EditText
                    android:id="@+id/earlyStartInput"
                    android:layout_width="0dp"
                    android:layout_height="54dp"
                    android:layout_weight="1"
                    android:background="@drawable/bg_field"
                    android:digits="0123456789:"
                    android:hint="Start 09:00"
                    android:inputType="text"
                    android:maxLength="5"
                    android:singleLine="true"
                    android:textColor="@color/text_primary"
                    android:textColorHint="@color/text_secondary"
                    android:textSize="14sp" />

                <EditText
                    android:id="@+id/earlyEndInput"
                    android:layout_width="0dp"
                    android:layout_height="54dp"
                    android:layout_marginStart="10dp"
                    android:layout_weight="1"
                    android:background="@drawable/bg_field"
                    android:digits="0123456789:"
                    android:hint="End 10:00"
                    android:inputType="text"
                    android:maxLength="5"
                    android:singleLine="true"
                    android:textColor="@color/text_primary"
                    android:textColorHint="@color/text_secondary"
                    android:textSize="14sp" />
            </LinearLayout>

            <CheckBox
                android:id="@+id/lateCallsEnabled"
                android:layout_width="match_parent"
                android:layout_height="wrap_content"
                android:layout_marginTop="10dp"
                android:text="Enable calls outside the early window"
                android:textColor="@color/text_primary"
                android:textSize="13sp" />

            <EditText
                android:id="@+id/lateQuantityInput"
                android:layout_width="match_parent"
                android:layout_height="54dp"
                android:layout_marginTop="8dp"
                android:background="@drawable/bg_field"
                android:digits="0123456789"
                android:hint="Post-window fixed quantity — default 10"
                android:inputType="number"
                android:maxLength="5"
                android:singleLine="true"
                android:textColor="@color/text_primary"
                android:textColorHint="@color/text_secondary"
                android:textSize="14sp" />

            <EditText
                android:id="@+id/bufferInput"
                android:layout_width="match_parent"
                android:layout_height="54dp"
                android:layout_marginTop="10dp"
                android:background="@drawable/bg_field"
                android:digits="0123456789."
                android:hint="Entry buffer % — default 1.5, maximum 2.0"
                android:inputType="numberDecimal"
                android:maxLength="4"
                android:singleLine="true"
                android:textColor="@color/text_primary"
                android:textColorHint="@color/text_secondary"
                android:textSize="14sp" />

            <TextView
                android:layout_width="match_parent"
                android:layout_height="wrap_content"
                android:layout_marginTop="8dp"
                android:text="Early-window calls use a direct marketable LIMIT order capped by the configured buffer. Post-window calls are disabled by default; when enabled, the fixed quantity and GTT/limit fallback are used."
                android:textColor="@color/text_secondary"
                android:textSize="12sp" />
''')

# -----------------------------------------------------------------------------
# Groww client: direct normal LIMIT order for early window; GTT fallback thereafter
# -----------------------------------------------------------------------------
client = JAVA / "GrowwClient.java"
insert_before(client,
'''    static ApiResult createEntryGtt(String accessToken, SignalParser.ParsedSignal signal,
''',
r'''    static ApiResult createImmediateEntryLimit(String accessToken,
                                               SignalParser.ParsedSignal signal,
                                               int quantity, double currentLtp) {
        if (signal == null || quantity <= 0 || currentLtp <= 0d) {
            return ApiResult.failure("", "A valid signal, quantity and LTP are required.", 0);
        }
        try {
            JSONObject body = new JSONObject();
            body.put("trading_symbol", signal.symbol);
            body.put("quantity", quantity);
            // A buy LIMIT at the permitted cap is marketable whenever the ask is below
            // the cap, but it cannot chase beyond the user's configured buffer.
            body.put("price", price(signal.maxBuyPrice));
            body.put("trigger_price", 0);
            body.put("validity", "DAY");
            body.put("exchange", "NSE");
            body.put("segment", "CASH");
            body.put("product", signal.productType);
            body.put("order_type", "LIMIT");
            body.put("transaction_type", "BUY");
            body.put("order_reference_id", signal.referenceId);
            HttpResult http = request("POST", API_BASE + "/order/create",
                    accessToken, body);
            if (!http.isSuccess()) return apiFailure(http);
            JSONObject payload = new JSONObject(http.body).optJSONObject("payload");
            String id = payload == null ? "" : payload.optString("groww_order_id", "");
            if (id.isEmpty()) {
                return ApiResult.failure("",
                        "Groww accepted the direct entry but returned no order ID.", http.code);
            }
            OrderStatus confirmed = confirmOrderReference(accessToken,
                    signal.referenceId);
            if (!confirmed.success || isRejectedRegularStatus(confirmed.status)) {
                return ApiResult.failure("ENTRY_NOT_CONFIRMED",
                        "Direct LIMIT entry was not confirmed. Status: "
                                + confirmed.status + " " + confirmed.message, http.code);
            }
            String state = currentLtp <= signal.maxBuyPrice
                    ? "marketable LIMIT submitted immediately"
                    : "LIMIT resting at the configured cap for a pullback";
            return ApiResult.success(id, signal.referenceId,
                    "Direct " + signal.productType + " " + state
                            + " at maximum ₹" + price(signal.maxBuyPrice)
                            + "; Groww status " + confirmed.status + ".", http.code);
        } catch (Exception e) {
            return ApiResult.failure("", "Direct entry error: " + safeMessage(e), 0);
        }
    }

    static ApiResult createEntryGttWithLimitFallback(String accessToken,
                                                      SignalParser.ParsedSignal signal,
                                                      int quantity, double currentLtp) {
        double proposedTrigger;
        if (currentLtp > signal.maxBuyPrice) proposedTrigger = signal.maxBuyPrice;
        else if (currentLtp < signal.entryLow) proposedTrigger = signal.entryLow;
        else proposedTrigger = Math.min(signal.maxBuyPrice,
                SignalParser.ceilToTick(currentLtp + 0.05d, 0.05d));

        // The Groww app rejects GTT triggers too close to LTP. The public API docs do
        // not publish the precise band, so avoid the known close-trigger case and use
        // a normal capped LIMIT order instead.
        if (Math.abs(proposedTrigger - currentLtp) / currentLtp <= 0.0011d) {
            return createImmediateEntryLimit(accessToken, signal, quantity, currentLtp);
        }
        ApiResult gtt = createEntryGtt(accessToken, signal, quantity, currentLtp);
        if (gtt.success) return gtt;
        String message = gtt.message == null ? "" : gtt.message.toLowerCase(Locale.US);
        if (message.contains("trigger") && (message.contains("close")
                || message.contains("ltp"))) {
            return createImmediateEntryLimit(accessToken, signal, quantity, currentLtp);
        }
        return gtt;
    }

    private static OrderStatus confirmOrderReference(String accessToken,
                                                      String referenceId) {
        OrderStatus status = OrderStatus.failure(0, "Not checked.");
        for (int i = 0; i < 6; i++) {
            status = getOrderByReference(accessToken, referenceId);
            if (status.success && status.status != null
                    && !status.status.trim().isEmpty()) return status;
            try { Thread.sleep(250L); }
            catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                break;
            }
        }
        return status;
    }

    private static boolean isRejectedRegularStatus(String status) {
        return "REJECTED".equalsIgnoreCase(status)
                || "FAILED".equalsIgnoreCase(status)
                || "CANCELLED".equalsIgnoreCase(status)
                || "CANCELED".equalsIgnoreCase(status);
    }

''')

# -----------------------------------------------------------------------------
# Notification policy and entry mode selection
# -----------------------------------------------------------------------------
listener = JAVA / "MultyfiNotificationService.java"
replace_once(listener,
'''            double budget = AppPrefs.tradeBudget(this);
            int quantity = AppPrefs.quantityForBudget(this, signal.maxBuyPrice);
            if (quantity < 1) {
                AppPrefs.log(this, "REJECTED — BUDGET BELOW ONE SHARE",
                        signal.symbol + " • maximum buy price ₹"
                                + String.format(Locale.US, "%.2f", signal.maxBuyPrice)
                                + " exceeds the configured ₹"
                                + String.format(Locale.US, "%.2f", budget)
                                + " trade budget.");
                return;
            }
            String summary = signal.summary(quantity, budget);
''',
'''            boolean earlyWindow = AppPrefs.isEarlyWindow(this, postTime);
            if (!earlyWindow && !AppPrefs.lateCallsEnabled(this)) {
                AppPrefs.log(this, "POST-WINDOW SIGNAL SKIPPED",
                        signal.symbol + " • outside "
                                + EntryPolicy.formatMinuteOfDay(AppPrefs.earlyStartMinute(this))
                                + "–" + EntryPolicy.formatMinuteOfDay(AppPrefs.earlyEndMinute(this))
                                + " • post-window calls are disabled by configuration.");
                return;
            }
            double budget = AppPrefs.tradeBudget(this);
            int quantity = AppPrefs.quantityForSignal(this, signal.maxBuyPrice,
                    postTime);
            if (quantity < 1) {
                AppPrefs.log(this, "REJECTED — SIZING BELOW ONE SHARE",
                        signal.symbol + " • maximum buy price ₹"
                                + String.format(Locale.US, "%.2f", signal.maxBuyPrice)
                                + " exceeds the active sizing rule.");
                return;
            }
            double sizingReference = earlyWindow ? budget
                    : signal.maximumOrderValue(quantity);
            String summary = signal.summary(quantity, sizingReference)
                    + " • policy " + (earlyWindow
                    ? "EARLY_WINDOW_DIRECT_LIMIT" : "POST_WINDOW_FIXED_QUANTITY");
''')
replace_once(listener,
'''            if (signal.maximumOrderValue(quantity) > budget + 0.01d
                    || signal.maximumOrderValue(quantity) > AppPrefs.MAX_ORDER_VALUE) {
                AppPrefs.log(this, "REJECTED — VALUE LIMIT", summary);
                return;
            }
''',
'''            double activeValueLimit = earlyWindow ? budget : AppPrefs.MAX_ORDER_VALUE;
            if (signal.maximumOrderValue(quantity) > activeValueLimit + 0.01d
                    || signal.maximumOrderValue(quantity) > AppPrefs.MAX_ORDER_VALUE) {
                AppPrefs.log(this, "REJECTED — VALUE LIMIT", summary);
                return;
            }
''')
replace_once(listener,
'''            AppPrefs.log(this, "SUBMITTING ENTRY GTT", summary
                    + " • LTP ₹" + String.format(Locale.US, "%.2f", ltp.value)
                    + " • baseline " + signal.productType + " position "
                    + baseline.value + ".");
            GrowwClient.ApiResult result = GrowwClient.createEntryGtt(
                    token, signal, quantity, ltp.value);
            if (result.success) {
                long lifecycleAnchor = lifecycleAnchor(signal);
                Strategy strategy = new Strategy(signal.eventId, signal.symbol,
                        signal.category, signal.productType, quantity,
                        signal.targetPrice, signal.stopLossPrice, baseline.value,
                        signal.referenceId, result.id, lifecycleAnchor);
                StrategyStore.upsert(this, strategy);
                AppPrefs.markProcessed(this, signal.eventId);
                AppPrefs.incrementDailyBuyCount(this);
                AppPrefs.log(this, "ENTRY GTT CONFIRMED", summary + "\n"
                        + result.message
                        + " Stop-loss will be created only for actual filled quantity."
                        + (lifecycleAnchor > System.currentTimeMillis() + 60_000L
                        ? " Off-hours CNC call is scheduled through the next trading session."
                        : ""));
                StrategyMonitorService.ensureRunning(this);
            } else if ("GA007".equals(result.errorCode)) {
                AppPrefs.markProcessed(this, signal.eventId);
                AppPrefs.log(this, "DUPLICATE CONFIRMED", summary
                        + " • Groww rejected the repeated reference ID.");
            } else {
                AppPrefs.log(this, "ENTRY GTT FAILED", summary + "\n"
                        + result.message + (result.errorCode.isEmpty()
                        ? "" : " [" + result.errorCode + "]"));
            }
''',
'''            String requestedMode = earlyWindow
                    ? "DIRECT CAPPED LIMIT" : "GTT / CAPPED LIMIT FALLBACK";
            AppPrefs.log(this, "SUBMITTING ENTRY", summary
                    + " • mode " + requestedMode
                    + " • LTP ₹" + String.format(Locale.US, "%.2f", ltp.value)
                    + " • baseline " + signal.productType + " position "
                    + baseline.value + ".");
            GrowwClient.ApiResult result = earlyWindow
                    ? GrowwClient.createImmediateEntryLimit(token, signal,
                    quantity, ltp.value)
                    : GrowwClient.createEntryGttWithLimitFallback(token, signal,
                    quantity, ltp.value);
            if (result.success) {
                long lifecycleAnchor = lifecycleAnchor(signal);
                // Direct regular orders return their reference as secondaryId;
                // true GTTs leave secondaryId empty and retain a smart-order ID.
                String smartOrderId = result.secondaryId == null
                        || result.secondaryId.isEmpty() ? result.id : "";
                Strategy strategy = new Strategy(signal.eventId, signal.symbol,
                        signal.category, signal.productType, quantity,
                        signal.targetPrice, signal.stopLossPrice, baseline.value,
                        signal.referenceId, smartOrderId, lifecycleAnchor);
                StrategyStore.upsert(this, strategy);
                AppPrefs.markProcessed(this, signal.eventId);
                AppPrefs.incrementDailyBuyCount(this);
                AppPrefs.log(this, "ENTRY CONFIRMED", summary + "\n"
                        + result.message
                        + " Stop-loss will be created only for actual filled quantity."
                        + (lifecycleAnchor > System.currentTimeMillis() + 60_000L
                        ? " Off-hours CNC call is scheduled through the next trading session."
                        : ""));
                StrategyMonitorService.ensureRunning(this);
            } else if ("GA007".equals(result.errorCode)) {
                AppPrefs.markProcessed(this, signal.eventId);
                AppPrefs.log(this, "DUPLICATE CONFIRMED", summary
                        + " • Groww rejected the repeated reference ID.");
            } else {
                AppPrefs.log(this, "ENTRY FAILED", summary + "\n"
                        + result.message + (result.errorCode.isEmpty()
                        ? "" : " [" + result.errorCode + "]"));
            }
''')
replace_once(listener,
'''                        "Maximum four automatic entry GTTs reached for today.",
''',
'''                        "Maximum four automatic entries reached for today.",
''')
replace_once(listener,
'''        if (strategy.entrySmartOrderId == null || strategy.entrySmartOrderId.isEmpty()) {
            return true;
        }
''',
'''        if (strategy.entrySmartOrderId == null || strategy.entrySmartOrderId.isEmpty()) {
            GrowwClient.OrderStatus order = GrowwClient.getOrderByReference(
                    token, strategy.entryReferenceId);
            if (!order.success) return false;
            if (isTerminalRegularOrderStatus(order.status)) return true;
            if (!isOpenRegularOrderStatus(order.status)
                    || order.orderId == null || order.orderId.isEmpty()) return false;
            RegularOrderSafety.Result cancelled =
                    RegularOrderSafety.cancelOpenCashOrder(token, order.orderId);
            if (!cancelled.success) return false;
            for (int i = 0; i < 8; i++) {
                order = GrowwClient.getOrderByReference(token,
                        strategy.entryReferenceId);
                if (order.success && isTerminalRegularOrderStatus(order.status)) {
                    StrategyStore.upsert(this, strategy);
                    return true;
                }
                sleep(300L);
            }
            return false;
        }
''')

# -----------------------------------------------------------------------------
# Strategy monitor: cancel/verify regular direct entry at cut-off or early exit
# -----------------------------------------------------------------------------
monitor = JAVA / "StrategyMonitorService.java"
replace_once(monitor,
'''    private boolean cancelEntryAndVerify(String token, Strategy strategy) {
        if (strategy.entrySmartOrderId == null || strategy.entrySmartOrderId.isEmpty()) return true;
        GrowwClient.SmartStatus entry = GrowwClient.getGtt(token,
''',
'''    private boolean cancelEntryAndVerify(String token, Strategy strategy) {
        if (strategy.entrySmartOrderId == null || strategy.entrySmartOrderId.isEmpty()) {
            GrowwClient.OrderStatus order = GrowwClient.getOrderByReference(
                    token, strategy.entryReferenceId);
            if (!order.success) return false;
            if (isTerminalRegularOrderStatus(order.status)) return true;
            if (!isOpenRegularOrderStatus(order.status)
                    || order.orderId == null || order.orderId.isEmpty()) return false;
            RegularOrderSafety.Result cancel =
                    RegularOrderSafety.cancelOpenCashOrder(token, order.orderId);
            if (!cancel.success) return false;
            for (int i = 0; i < 8; i++) {
                order = GrowwClient.getOrderByReference(token,
                        strategy.entryReferenceId);
                if (order.success && isTerminalRegularOrderStatus(order.status)) {
                    return true;
                }
                try { Thread.sleep(300L); }
                catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    return false;
                }
            }
            return false;
        }
        GrowwClient.SmartStatus entry = GrowwClient.getGtt(token,
''')
insert_before(monitor,
'''    private static boolean isActiveStatus(String status) {
''',
'''    private static boolean isOpenRegularOrderStatus(String status) {
        return "NEW".equalsIgnoreCase(status)
                || "ACKED".equalsIgnoreCase(status)
                || "TRIGGER_PENDING".equalsIgnoreCase(status)
                || "APPROVED".equalsIgnoreCase(status)
                || "OPEN".equalsIgnoreCase(status)
                || "PENDING".equalsIgnoreCase(status)
                || "PARTIALLY_FILLED".equalsIgnoreCase(status)
                || "PARTIAL".equalsIgnoreCase(status)
                || "CANCELLATION_REQUESTED".equalsIgnoreCase(status);
    }

    private static boolean isTerminalRegularOrderStatus(String status) {
        return "EXECUTED".equalsIgnoreCase(status)
                || "DELIVERY_AWAITED".equalsIgnoreCase(status)
                || "CANCELLED".equalsIgnoreCase(status)
                || "CANCELED".equalsIgnoreCase(status)
                || "COMPLETED".equalsIgnoreCase(status)
                || "COMPLETE".equalsIgnoreCase(status)
                || "REJECTED".equalsIgnoreCase(status)
                || "FAILED".equalsIgnoreCase(status);
    }

''')

# -----------------------------------------------------------------------------
# Version and tests
# -----------------------------------------------------------------------------
build = ROOT / "app/build.gradle"
replace_once(build, "        versionCode 150\n        versionName '1.5.0'\n",
             "        versionCode 160\n        versionName '1.6.0'\n")

entry_policy_test = r'''package com.suhas.multyfiautobuy.stable;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

import java.time.ZoneId;
import java.time.ZonedDateTime;

public class EntryPolicyTest {
    @Test
    public void earlyWindowIsStartInclusiveAndEndExclusive() {
        assertTrue(EntryPolicy.isInWindow(atIst(9, 0), 9 * 60, 10 * 60));
        assertTrue(EntryPolicy.isInWindow(atIst(9, 59), 9 * 60, 10 * 60));
        assertFalse(EntryPolicy.isInWindow(atIst(10, 0), 9 * 60, 10 * 60));
    }

    @Test
    public void sizesEarlyByBudgetAndLateByFixedQuantity() {
        assertEquals(14, EntryPolicy.quantity(694.25d, true,
                10_000d, 10, 10_000));
        assertEquals(10, EntryPolicy.quantity(694.25d, false,
                10_000d, 10, 10_000));
        assertEquals(0, EntryPolicy.quantity(12_000d, true,
                10_000d, 10, 10_000));
    }

    @Test
    public void parsesConfigurableWindowTimes() {
        assertEquals(540, EntryPolicy.parseMinuteOfDay("09:00"));
        assertEquals(600, EntryPolicy.parseMinuteOfDay("10:00"));
        assertEquals(-1, EntryPolicy.parseMinuteOfDay("25:00"));
        assertEquals("09:00", EntryPolicy.formatMinuteOfDay(540));
    }

    private static long atIst(int hour, int minute) {
        return ZonedDateTime.of(2026, 7, 24, hour, minute, 0, 0,
                ZoneId.of("Asia/Kolkata")).toInstant().toEpochMilli();
    }
}
'''
TEST.mkdir(parents=True, exist_ok=True)
(TEST / "EntryPolicyTest.java").write_text(entry_policy_test, encoding="utf-8")

print("Applied Multyfi AutoBuy S24 v1.6.0 time-window sizing patch.")
