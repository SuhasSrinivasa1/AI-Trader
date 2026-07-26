package com.suhas.multyfiautobuy.stable;

import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
import android.app.NotificationManager;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.Build;
import android.os.Bundle;
import android.os.PowerManager;
import android.provider.Settings;
import android.service.notification.NotificationListenerService;
import android.text.InputType;
import android.text.TextUtils;
import android.text.TextWatcher;
import android.text.Editable;
import android.view.Gravity;
import android.view.View;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.Switch;
import android.widget.TextView;
import android.widget.Toast;

import java.util.Calendar;
import java.util.Collections;
import java.util.Locale;
import java.util.TimeZone;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Source-built production dashboard for the S24 Ultra / Android 16 release. */
public class ProductionActivity extends Activity {
    private static final int BG = Color.rgb(6, 14, 27);
    private static final int CARD = Color.rgb(16, 29, 49);
    private static final int CARD_ALT = Color.rgb(21, 37, 61);
    private static final int FIELD = Color.rgb(10, 23, 42);
    private static final int TEXT = Color.rgb(238, 244, 255);
    private static final int MUTED = Color.rgb(162, 178, 205);
    private static final int GREEN = Color.rgb(100, 238, 190);
    private static final int AMBER = Color.rgb(255, 199, 102);
    private static final int RED = Color.rgb(255, 119, 137);
    private static final int PURPLE = Color.rgb(126, 92, 255);
    private static final int CYAN = Color.rgb(91, 224, 228);
    private static final String RUNTIME_PREFS = "production_runtime";
    private static final String LAST_TEST_GTT = "last_test_gtt";
    private static final String LAST_TEST_SYMBOL = "last_test_symbol";

    private final ExecutorService executor = Executors.newSingleThreadExecutor();

    private TextView systemStatus;
    private TextView statusDetail;
    private TextView notificationStatus;
    private TextView authStatus;
    private TextView ipStatus;
    private TextView policyStatus;
    private TextView windowSavedStatus;
    private TextView growwTestStatus;
    private TextView auditLog;
    private Switch armedSwitch;
    private EditText window1Input;
    private EditText window2Input;
    private EditText window3Input;
    private EditText bufferInput;
    private EditText apiKeyInput;
    private EditText totpInput;
    private EditText accessTokenInput;
    private EditText expectedIpInput;
    private EditText testSymbolInput;
    private CheckBox staticIpConfirm;
    private boolean suppressSwitch;
    private boolean suppressWindowWatch;
    private boolean windowsDirty;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_SECURE);
        getWindow().setStatusBarColor(BG);
        getWindow().setNavigationBarColor(BG);
        setContentView(buildDashboard());
        loadSavedState();
        requestMonitoringNotificationPermission();
        StrategyMonitorService.ensureRunning(this);
        refreshStatus();
    }

    @Override
    protected void onResume() {
        super.onResume();
        try {
            NotificationListenerService.requestRebind(
                    new ComponentName(this, MultyfiNotificationService.class));
        } catch (Exception ignored) { }
        StrategyMonitorService.ensureRunning(this);
        refreshStatus();
    }

    @Override
    protected void onDestroy() {
        executor.shutdownNow();
        super.onDestroy();
    }

    private View buildDashboard() {
        ScrollView scroll = new ScrollView(this);
        scroll.setFillViewport(true);
        scroll.setBackgroundColor(BG);
        LinearLayout root = column();
        root.setPadding(dp(18), dp(24), dp(18), dp(36));
        scroll.addView(root, matchWrap());

        TextView eyebrow = label("PRIVATE S24 EXECUTION CONSOLE", 12, GREEN, true);
        eyebrow.setLetterSpacing(0.12f);
        root.addView(eyebrow);
        TextView title = label("Multyfi AutoBuy Pro", 30, TEXT, true);
        root.addView(title, topMargin(4));
        TextView subtitle = label("Android 16 • source-built production release 2.0.0", 14, MUTED, false);
        root.addView(subtitle, topMargin(2));

        LinearLayout statusCard = card();
        LinearLayout statusTop = row();
        LinearLayout statusWords = column();
        statusWords.setLayoutParams(weightWrap(1f));
        statusWords.addView(label("SYSTEM STATUS", 12, MUTED, true));
        systemStatus = label("CHECKING", 28, AMBER, true);
        statusWords.addView(systemStatus, topMargin(4));
        statusTop.addView(statusWords);
        armedSwitch = new Switch(this);
        armedSwitch.setShowText(false);
        statusTop.addView(armedSwitch, wrapWrap());
        statusCard.addView(statusTop);
        statusDetail = label("Validating configuration…", 14, TEXT, false);
        statusDetail.setLineSpacing(0f, 1.18f);
        statusCard.addView(statusDetail, topMargin(12));
        notificationStatus = statusRow();
        authStatus = statusRow();
        ipStatus = statusRow();
        policyStatus = statusRow();
        statusCard.addView(notificationStatus, topMargin(12));
        statusCard.addView(authStatus, topMargin(7));
        statusCard.addView(ipStatus, topMargin(7));
        statusCard.addView(policyStatus, topMargin(7));
        root.addView(statusCard, sectionMargin());

        LinearLayout windowsCard = card();
        windowsCard.addView(sectionTitle("TRADING WINDOWS"));
        windowsCard.addView(label(
                "Amounts are saved only after pressing SAVE TRADING WINDOWS. Unsaved edits block arming.",
                13, MUTED, false), topMargin(6));
        window1Input = moneyField("09:00–09:30 • MIS intraday • immediate LIMIT");
        window2Input = moneyField("09:30–10:00 • CNC delivery • entry GTT");
        window3Input = moneyField("10:00–15:30 • CNC delivery • entry GTT");
        bufferInput = decimalField("Entry buffer % (0.00–2.00)");
        windowsCard.addView(window1Input, topMargin(14));
        windowsCard.addView(window2Input, topMargin(10));
        windowsCard.addView(window3Input, topMargin(10));
        windowsCard.addView(bufferInput, topMargin(10));
        Button saveWindows = primaryButton("SAVE TRADING WINDOWS");
        saveWindows.setOnClickListener(v -> saveTradingWindows());
        windowsCard.addView(saveWindows, topMargin(14));
        windowSavedStatus = label("Not checked", 12, MUTED, false);
        windowsCard.addView(windowSavedStatus, topMargin(8));
        root.addView(windowsCard, sectionMargin());

        LinearLayout growwCard = card();
        growwCard.addView(sectionTitle("GROWW CONNECTION & CONTROLLED TEST"));
        growwCard.addView(label(
                "Credentials remain encrypted by Android Keystore. The connection test is read-only. The one-share test creates a real CNC GTT approximately 10% below LTP and immediately cancels it.",
                13, MUTED, false), topMargin(6));
        apiKeyInput = secureField("Groww API key — leave blank to keep saved value");
        totpInput = secureField("Groww Base32 TOTP secret — leave blank to keep saved value");
        accessTokenInput = secureField("Today’s access token — optional");
        growwCard.addView(apiKeyInput, topMargin(14));
        growwCard.addView(totpInput, topMargin(10));
        growwCard.addView(accessTokenInput, topMargin(10));
        Button saveSecrets = secondaryButton("SAVE AUTHENTICATION SECURELY");
        saveSecrets.setOnClickListener(v -> saveAuthentication());
        growwCard.addView(saveSecrets, topMargin(12));
        Button authenticate = primaryButton("AUTHENTICATE TODAY");
        authenticate.setOnClickListener(v -> authenticateToday(authenticate));
        growwCard.addView(authenticate, topMargin(10));
        Button connectionTest = primaryButton("TEST GROWW CONNECTION (READ-ONLY)");
        connectionTest.setOnClickListener(v -> testGrowwConnection(connectionTest));
        growwCard.addView(connectionTest, topMargin(10));
        testSymbolInput = textField("Test GTT symbol", "ITC");
        growwCard.addView(testSymbolInput, topMargin(14));
        Button testGtt = warningButton("CREATE & CANCEL 1-SHARE TEST GTT");
        testGtt.setOnClickListener(v -> confirmOneShareGttTest(testGtt));
        growwCard.addView(testGtt, topMargin(10));
        Button cancelTest = destructiveButton("CANCEL LAST TEST GTT");
        cancelTest.setOnClickListener(v -> cancelLastTestGtt(cancelTest));
        growwCard.addView(cancelTest, topMargin(10));
        growwTestStatus = label("No test GTT created in this installation.", 12, MUTED, false);
        growwTestStatus.setTextIsSelectable(true);
        growwCard.addView(growwTestStatus, topMargin(9));
        root.addView(growwCard, sectionMargin());

        LinearLayout networkCard = card();
        networkCard.addView(sectionTitle("SURFSHARK DEDICATED IP"));
        expectedIpInput = textField("Groww-whitelisted Dedicated IP", "");
        networkCard.addView(expectedIpInput, topMargin(12));
        staticIpConfirm = new CheckBox(this);
        staticIpConfirm.setText("This exact Dedicated IP is whitelisted in Groww");
        staticIpConfirm.setTextColor(TEXT);
        staticIpConfirm.setTextSize(13f);
        networkCard.addView(staticIpConfirm, topMargin(8));
        Button detectIp = secondaryButton("DETECT, COPY & VERIFY CURRENT IP");
        detectIp.setOnClickListener(v -> detectAndVerifyIp(detectIp));
        networkCard.addView(detectIp, topMargin(10));
        Button openAccess = secondaryButton("OPEN NOTIFICATION ACCESS");
        openAccess.setOnClickListener(v -> openSetting(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS));
        networkCard.addView(openAccess, topMargin(10));
        Button openBattery = secondaryButton("OPEN BATTERY OPTIMISATION SETTINGS");
        openBattery.setOnClickListener(v -> openSetting(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS));
        networkCard.addView(openBattery, topMargin(10));
        Button openVpn = secondaryButton("OPEN VPN / ALWAYS-ON VPN SETTINGS");
        openVpn.setOnClickListener(v -> openSetting(Settings.ACTION_VPN_SETTINGS));
        networkCard.addView(openVpn, topMargin(10));
        root.addView(networkCard, sectionMargin());

        LinearLayout validationCard = card();
        validationCard.addView(sectionTitle("DEVICE ACCEPTANCE"));
        validationCard.addView(label(
                "This test validates notification parsing, all three time windows, MIS/GTT routing and strict symbol-matched early exit. It submits no broker order.",
                13, MUTED, false), topMargin(6));
        Button parserTest = primaryButton("RUN OFFLINE ROUTING TEST");
        parserTest.setOnClickListener(v -> runParserTest());
        validationCard.addView(parserTest, topMargin(12));
        root.addView(validationCard, sectionMargin());

        LinearLayout logCard = card();
        LinearLayout logTop = row();
        TextView logTitle = sectionTitle("LOCAL AUDIT LOG");
        logTitle.setLayoutParams(weightWrap(1f));
        logTop.addView(logTitle);
        Button clear = compactButton("CLEAR");
        clear.setOnClickListener(v -> {
            AppPrefs.clearLog(this);
            refreshStatus();
        });
        logTop.addView(clear);
        logCard.addView(logTop);
        auditLog = label("No events yet.", 12, TEXT, false);
        auditLog.setTypeface(Typeface.MONOSPACE);
        auditLog.setTextIsSelectable(true);
        auditLog.setLineSpacing(0f, 1.12f);
        logCard.addView(auditLog, topMargin(12));
        root.addView(logCard, sectionMargin());

        TextView footer = label(
                "Auto-Buy OFF by default • 09:00–09:30 MIS • 09:30 onward CNC GTT • source-built v2.0.0",
                11, MUTED, false);
        footer.setGravity(Gravity.CENTER);
        root.addView(footer, topMargin(18));

        armedSwitch.setOnCheckedChangeListener((button, checked) -> handleArmedChange(checked));
        attachWindowWatch(window1Input);
        attachWindowWatch(window2Input);
        attachWindowWatch(window3Input);
        attachWindowWatch(bufferInput);
        return scroll;
    }

    private void loadSavedState() {
        suppressWindowWatch = true;
        window1Input.setText(money(AppPrefs.window1Budget(this)));
        window2Input.setText(money(AppPrefs.window2Budget(this)));
        window3Input.setText(money(AppPrefs.window3Budget(this)));
        bufferInput.setText(String.format(Locale.US, "%.2f", AppPrefs.entryBufferPercent(this)));
        suppressWindowWatch = false;
        windowsDirty = false;
        windowSavedStatus.setText("Saved: ₹" + money(AppPrefs.window1Budget(this))
                + " / ₹" + money(AppPrefs.window2Budget(this))
                + " / ₹" + money(AppPrefs.window3Budget(this))
                + " • buffer " + String.format(Locale.US, "%.2f", AppPrefs.entryBufferPercent(this)) + "%");
        windowSavedStatus.setTextColor(GREEN);

        expectedIpInput.setText(AppPrefs.expectedIp(this));
        staticIpConfirm.setChecked(AppPrefs.isStaticConfirmed(this));
        apiKeyInput.setHint(SecureStore.has(this, SecureStore.API_KEY)
                ? "API key saved securely" : "Groww API key");
        totpInput.setHint(SecureStore.has(this, SecureStore.TOTP_SECRET)
                ? "TOTP secret saved securely" : "Groww Base32 TOTP secret");
        accessTokenInput.setHint(SecureStore.has(this, SecureStore.ACCESS_TOKEN)
                ? "Access token saved for today" : "Today’s access token (optional)");
        String last = runtimePrefs().getString(LAST_TEST_GTT, "");
        String symbol = runtimePrefs().getString(LAST_TEST_SYMBOL, "");
        growwTestStatus.setText(last.isEmpty()
                ? "No test GTT created in this installation."
                : "Last test GTT: " + last + (symbol.isEmpty() ? "" : " • " + symbol));
        suppressSwitch = true;
        armedSwitch.setChecked(AppPrefs.isArmed(this));
        suppressSwitch = false;
    }

    private void attachWindowWatch(EditText field) {
        field.addTextChangedListener(new TextWatcher() {
            @Override public void beforeTextChanged(CharSequence s, int start, int count, int after) { }
            @Override public void onTextChanged(CharSequence s, int start, int before, int count) {
                if (suppressWindowWatch) return;
                windowsDirty = true;
                windowSavedStatus.setText("UNSAVED CHANGES — press SAVE TRADING WINDOWS");
                windowSavedStatus.setTextColor(AMBER);
                refreshStatus();
            }
            @Override public void afterTextChanged(Editable s) { }
        });
    }

    private void saveTradingWindows() {
        try {
            double first = readDouble(window1Input);
            double second = readDouble(window2Input);
            double third = readDouble(window3Input);
            double buffer = readDouble(bufferInput);
            if (!AppPrefs.isValidTradeBudget(first)
                    || !AppPrefs.isValidTradeBudget(second)
                    || !AppPrefs.isValidTradeBudget(third)) {
                toast("Each amount must be between ₹1,000 and ₹5,00,000.");
                return;
            }
            if (!AppPrefs.isValidEntryBuffer(buffer)) {
                toast("Entry buffer must be between 0% and 2%.");
                return;
            }
            AppPrefs.setWindowBudgets(this, first, second, third);
            AppPrefs.setEntryBufferPercent(this, buffer);
            windowsDirty = false;
            windowSavedStatus.setText("SAVED NOW: ₹" + money(first) + " / ₹" + money(second)
                    + " / ₹" + money(third) + " • buffer "
                    + String.format(Locale.US, "%.2f", buffer) + "%");
            windowSavedStatus.setTextColor(GREEN);
            AppPrefs.log(this, "TRADING WINDOWS SAVED",
                    "09:00–09:30 ₹" + money(first) + " MIS immediate LIMIT"
                            + " • 09:30–10:00 ₹" + money(second) + " CNC entry GTT"
                            + " • 10:00–15:30 ₹" + money(third) + " CNC entry GTT"
                            + " • buffer " + String.format(Locale.US, "%.2f", buffer) + "%.");
            toast("All three trading windows were saved.");
            refreshStatus();
        } catch (Exception e) {
            toast("Could not save windows: " + safeMessage(e));
        }
    }

    private void saveAuthentication() {
        try {
            String api = text(apiKeyInput);
            String secret = text(totpInput);
            String token = text(accessTokenInput);
            if (!api.isEmpty()) SecureStore.put(this, SecureStore.API_KEY, api);
            if (!secret.isEmpty()) SecureStore.put(this, SecureStore.TOTP_SECRET, secret);
            if (!token.isEmpty()) {
                SecureStore.put(this, SecureStore.ACCESS_TOKEN, token);
                SecureStore.put(this, SecureStore.ACCESS_TOKEN_DATE, AppPrefs.istDate());
            }
            AppPrefs.setExpectedIp(this, text(expectedIpInput));
            AppPrefs.setStaticConfirmed(this, staticIpConfirm.isChecked());
            apiKeyInput.setText("");
            totpInput.setText("");
            accessTokenInput.setText("");
            AppPrefs.log(this, "SECURE SETTINGS SAVED",
                    "Groww credentials retained in Android Keystore; Dedicated IP "
                            + (AppPrefs.expectedIp(this).isEmpty() ? "not entered" : AppPrefs.expectedIp(this)) + ".");
            loadSavedState();
            toast("Authentication and network settings saved securely.");
            refreshStatus();
        } catch (Exception e) {
            toast("Could not save secure settings: " + safeMessage(e));
        }
    }

    private void authenticateToday(Button button) {
        setBusy(button, true, "AUTHENTICATING…", "AUTHENTICATE TODAY");
        executor.execute(() -> {
            GrowwClient.AuthResult result = GrowwClient.authenticate(
                    SecureStore.get(this, SecureStore.API_KEY),
                    SecureStore.get(this, SecureStore.TOTP_SECRET));
            if (result.success) {
                try {
                    SecureStore.put(this, SecureStore.ACCESS_TOKEN, result.accessToken);
                    SecureStore.put(this, SecureStore.ACCESS_TOKEN_DATE, AppPrefs.istDate());
                    AppPrefs.log(this, "AUTH TOKEN READY", result.message);
                } catch (Exception e) {
                    AppPrefs.log(this, "AUTH STORE FAILED", safeMessage(e));
                }
            } else {
                AppPrefs.clearAuthVerified(this);
                AppPrefs.log(this, "AUTH FAILED", result.message);
            }
            runOnUiThread(() -> {
                setBusy(button, false, "", "AUTHENTICATE TODAY");
                toast(result.message);
                refreshStatus();
            });
        });
    }

    private void testGrowwConnection(Button button) {
        setBusy(button, true, "TESTING…", "TEST GROWW CONNECTION (READ-ONLY)");
        executor.execute(() -> {
            String token = TokenManager.validToken(this);
            GrowwClient.ApiResult result = token.isEmpty()
                    ? GrowwClient.ApiResult.failure("", "No valid Groww access token is available.", 0)
                    : GrowwClient.verifyProfile(token);
            if (result.success) {
                AppPrefs.setAuthVerified(this, result.id);
                AppPrefs.log(this, "GROWW CONNECTION TEST PASSED",
                        result.message + " No order was submitted.");
            } else {
                AppPrefs.clearAuthVerified(this);
                AppPrefs.log(this, "GROWW CONNECTION TEST FAILED", result.message);
            }
            runOnUiThread(() -> {
                growwTestStatus.setText(result.success
                        ? "READ-ONLY CONNECTION PASSED • " + result.message
                        : "CONNECTION FAILED • " + result.message);
                growwTestStatus.setTextColor(result.success ? GREEN : RED);
                setBusy(button, false, "", "TEST GROWW CONNECTION (READ-ONLY)");
                toast(result.message);
                refreshStatus();
            });
        });
    }

    private void confirmOneShareGttTest(Button button) {
        String symbol = text(testSymbolInput).toUpperCase(Locale.US);
        if (symbol.isEmpty()) symbol = "ITC";
        final String finalSymbol = symbol;
        new AlertDialog.Builder(this)
                .setTitle("Create a real 1-share test GTT?")
                .setMessage("This will request current LTP for " + finalSymbol
                        + ", create one CNC share approximately 10% below LTP, verify the GTT is active, and immediately cancel it. A broker order is still real and carries a small execution risk if price gaps sharply. Auto-Buy is not required.")
                .setNegativeButton("CANCEL", null)
                .setPositiveButton("CREATE & CANCEL", (dialog, which) ->
                        executeOneShareGttTest(button, finalSymbol))
                .show();
    }

    private void executeOneShareGttTest(Button button, String symbol) {
        setBusy(button, true, "CREATING TEST…", "CREATE & CANCEL 1-SHARE TEST GTT");
        executor.execute(() -> {
            String finalMessage;
            boolean finalSuccess = false;
            String token = TokenManager.validToken(this);
            if (token.isEmpty()) {
                finalMessage = "No valid Groww access token is available.";
            } else {
                GrowwClient.ApiResult profile = GrowwClient.verifyProfile(token);
                if (!profile.success) {
                    finalMessage = "Groww profile verification failed: " + profile.message;
                } else {
                    AppPrefs.setAuthVerified(this, profile.id);
                    GrowwClient.DoubleResult ltp = GrowwClient.getLtp(token, symbol);
                    if (!ltp.success || ltp.value <= 0d) {
                        finalMessage = "Could not obtain " + symbol + " LTP: " + ltp.message;
                    } else {
                        double testPrice = SignalParser.floorToTick(ltp.value * 0.90d, 0.05d);
                        double target = SignalParser.ceilToTick(testPrice * 1.10d, 0.05d);
                        double stop = SignalParser.floorToTick(testPrice * 0.90d, 0.05d);
                        long now = System.currentTimeMillis();
                        String suffix = Long.toString(now);
                        suffix = suffix.substring(Math.max(0, suffix.length() - 8));
                        String event = "test-" + AppPrefs.compactIstDate() + "-" + suffix;
                        String reference = "TST" + AppPrefs.compactIstDate() + suffix;
                        SignalParser.ParsedSignal signal = new SignalParser.ParsedSignal(
                                event, reference, symbol, "TEST", "CNC",
                                testPrice, testPrice, testPrice, testPrice,
                                0d, target, stop, now, "Controlled one-share test GTT");
                        GrowwClient.ApiResult create = GrowwClient.createEntryGtt(
                                token, signal, 1, ltp.value);
                        if (!create.success) {
                            finalMessage = "Test GTT creation failed: " + create.message;
                            AppPrefs.log(this, "1-SHARE TEST GTT FAILED", finalMessage);
                        } else {
                            runtimePrefs().edit()
                                    .putString(LAST_TEST_GTT, create.id)
                                    .putString(LAST_TEST_SYMBOL, symbol)
                                    .apply();
                            AppPrefs.log(this, "1-SHARE TEST GTT ACTIVE",
                                    symbol + " • smart order " + create.id
                                            + " • LTP ₹" + money(ltp.value)
                                            + " • test trigger/limit ₹" + money(testPrice) + ".");
                            GrowwClient.ApiResult cancel = GrowwClient.cancelGtt(token, create.id);
                            boolean cancelled = cancel.success && waitForCancelled(token, create.id);
                            if (cancelled) {
                                runtimePrefs().edit().remove(LAST_TEST_GTT).apply();
                                AppPrefs.log(this, "1-SHARE TEST GTT CANCELLED",
                                        symbol + " • smart order " + create.id
                                                + " was created, confirmed and cancelled successfully.");
                                finalSuccess = true;
                                finalMessage = "PASS • Groww created and cancelled test GTT "
                                        + create.id + " for 1 " + symbol + " share.";
                            } else {
                                finalMessage = "URGENT: test GTT " + create.id
                                        + " was created but cancellation was not confirmed. Open Groww and cancel it immediately. "
                                        + cancel.message;
                                AppPrefs.log(this, "TEST GTT CANCELLATION NOT CONFIRMED", finalMessage);
                            }
                        }
                    }
                }
            }
            final String message = finalMessage;
            final boolean success = finalSuccess;
            runOnUiThread(() -> {
                setBusy(button, false, "", "CREATE & CANCEL 1-SHARE TEST GTT");
                growwTestStatus.setText(message);
                growwTestStatus.setTextColor(success ? GREEN : RED);
                toast(message);
                refreshStatus();
            });
        });
    }

    private void cancelLastTestGtt(Button button) {
        String id = runtimePrefs().getString(LAST_TEST_GTT, "");
        if (id.isEmpty()) {
            toast("No uncancelled test GTT is stored in this installation.");
            return;
        }
        setBusy(button, true, "CANCELLING…", "CANCEL LAST TEST GTT");
        executor.execute(() -> {
            String token = TokenManager.validToken(this);
            GrowwClient.ApiResult result = token.isEmpty()
                    ? GrowwClient.ApiResult.failure("", "No valid Groww token is available.", 0)
                    : GrowwClient.cancelGtt(token, id);
            boolean cancelled = result.success && waitForCancelled(token, id);
            if (cancelled) {
                runtimePrefs().edit().remove(LAST_TEST_GTT).apply();
                AppPrefs.log(this, "TEST GTT CANCELLED MANUALLY", id);
            }
            String message = cancelled ? "Test GTT " + id + " is confirmed CANCELLED."
                    : "Cancellation is not confirmed for " + id + ". Check Groww immediately. " + result.message;
            runOnUiThread(() -> {
                setBusy(button, false, "", "CANCEL LAST TEST GTT");
                growwTestStatus.setText(message);
                growwTestStatus.setTextColor(cancelled ? GREEN : RED);
                toast(message);
                refreshStatus();
            });
        });
    }

    private boolean waitForCancelled(String token, String id) {
        for (int i = 0; i < 10; i++) {
            GrowwClient.SmartStatus status = GrowwClient.getGtt(token, id);
            if (status.success && "CANCELLED".equalsIgnoreCase(status.status)) return true;
            try { Thread.sleep(300L); }
            catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return false;
            }
        }
        return false;
    }

    private void detectAndVerifyIp(Button button) {
        if (!NetworkUtil.isVpnActive(this)) {
            toast("Connect Surfshark Dedicated IP first.");
            return;
        }
        setBusy(button, true, "CHECKING…", "DETECT, COPY & VERIFY CURRENT IP");
        executor.execute(() -> {
            String message;
            boolean success = false;
            try {
                String actual = NetworkUtil.fetchPublicIp();
                String expected = text(expectedIpInput);
                if (expected.isEmpty()) expected = AppPrefs.expectedIp(this);
                if (expected.isEmpty()) expected = actual;
                success = staticIpConfirm.isChecked() && expected.equals(actual);
                AppPrefs.setExpectedIp(this, expected);
                AppPrefs.setStaticConfirmed(this, staticIpConfirm.isChecked());
                AppPrefs.setIpVerification(this, actual, success);
                ClipboardManager clipboard = (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
                if (clipboard != null) clipboard.setPrimaryClip(
                        ClipData.newPlainText("Surfshark Dedicated IP", actual));
                final String detected = actual;
                runOnUiThread(() -> expectedIpInput.setText(detected));
                message = success ? "Dedicated IP verified and copied: " + actual
                        : "Detected and copied " + actual
                        + ". Tick the whitelist confirmation and verify again.";
                AppPrefs.log(this, success ? "SURFSHARK IP VERIFIED" : "SURFSHARK IP DETECTED", message);
            } catch (Exception e) {
                message = "IP verification failed: " + safeMessage(e);
                AppPrefs.setIpVerifiedAt(this, 0L);
            }
            final String result = message;
            final boolean ok = success;
            runOnUiThread(() -> {
                setBusy(button, false, "", "DETECT, COPY & VERIFY CURRENT IP");
                toast(result);
                if (!ok) ipStatus.setTextColor(AMBER);
                refreshStatus();
            });
        });
    }

    private void runParserTest() {
        long firstTime = atIst(2026, 7, 27, 9, 10);
        long secondTime = atIst(2026, 7, 27, 9, 40);
        long thirdTime = atIst(2026, 7, 27, 10, 30);
        String sample = "Equity Recommendation\nStock Name: TCS\nEntry Range: 3200-3220\nTarget: 3300\nStop Loss: 3150";
        SignalParser.ParsedSignal signal = SignalParser.parse(sample, firstTime,
                AppPrefs.entryBufferPercent(this));
        AppPrefs.TradeWindow first = AppPrefs.tradeWindow(this, firstTime);
        AppPrefs.TradeWindow second = AppPrefs.tradeWindow(this, secondTime);
        AppPrefs.TradeWindow third = AppPrefs.tradeWindow(this, thirdTime);
        boolean passed = signal != null && first != null && second != null && third != null
                && OrderPolicy.entryMode(first) == OrderPolicy.EntryMode.IMMEDIATE_MIS_LIMIT
                && OrderPolicy.entryMode(second) == OrderPolicy.EntryMode.CNC_ENTRY_GTT
                && OrderPolicy.entryMode(third) == OrderPolicy.EntryMode.CNC_ENTRY_GTT
                && "MIS".equals(OrderPolicy.productType(first))
                && "CNC".equals(OrderPolicy.productType(second))
                && "CNC".equals(OrderPolicy.productType(third))
                && AppPrefs.quantityForBudget(first.budget, signal.maxBuyPrice) >= 1;
        Strategy dummy = new Strategy("test-event", "TCS", "EQUITY", "CNC",
                3, 3300d, 3150d, 0, "TESTREF", "TESTGTT", firstTime);
        SignalParser.EarlyExitSignal exit = SignalParser.parseEarlyExit(
                "Exiting early\nStock Name: TCS", firstTime,
                Collections.singletonList(dummy));
        passed = passed && exit != null && "TCS".equals(exit.symbol);
        AppPrefs.setParserTestPassed(this, passed);
        String message = passed
                ? "PASS: 09:00–09:30 MIS LIMIT; 09:30 onward CNC entry GTT; three budgets; early exit matched; no order submitted."
                : "Routing/parser acceptance failed. Auto-Buy remains blocked.";
        AppPrefs.log(this, passed ? "PRODUCTION ROUTING TEST PASSED" : "PRODUCTION ROUTING TEST FAILED", message);
        toast(message);
        refreshStatus();
    }

    private void handleArmedChange(boolean checked) {
        if (suppressSwitch) return;
        if (checked) {
            String issue = readinessIssue();
            if (issue != null) {
                suppressSwitch = true;
                armedSwitch.setChecked(false);
                suppressSwitch = false;
                AppPrefs.setArmed(this, false);
                toast(issue);
            } else {
                AppPrefs.setArmed(this, true);
                AppPrefs.log(this, "ARMED — PRODUCTION POLICY",
                        "09:00–09:30 MIS immediate LIMIT • 09:30–15:30 CNC entry GTT"
                                + " • budgets ₹" + money(AppPrefs.window1Budget(this))
                                + "/₹" + money(AppPrefs.window2Budget(this))
                                + "/₹" + money(AppPrefs.window3Budget(this)) + ".");
                StrategyMonitorService.ensureRunning(this);
            }
        } else {
            AppPrefs.setArmed(this, false);
            AppPrefs.log(this, "DISARMED", "New automatic entries disabled; existing strategies remain monitored.");
        }
        refreshStatus();
    }

    private void refreshStatus() {
        boolean notificationReady = hasNotificationAccess();
        boolean authReady = AppPrefs.isAuthVerifiedToday(this);
        boolean vpn = NetworkUtil.isVpnActive(this);
        boolean ipReady = vpn && AppPrefs.isStaticConfirmed(this)
                && AppPrefs.isIpRecentlyVerified(this);
        boolean parserReady = AppPrefs.parserTestPassed(this);
        String issue = readinessIssue();
        boolean ready = issue == null;
        int active = StrategyStore.activeCount(this);

        notificationStatus.setText(notificationReady
                ? "● Notification listener: connected permission granted"
                : "● Notification listener: access not granted");
        notificationStatus.setTextColor(notificationReady ? GREEN : RED);
        String ucc = AppPrefs.ucc(this);
        authStatus.setText(authReady
                ? "● Groww connection + DDPI: verified today" + (ucc.isEmpty() ? "" : " • UCC " + ucc)
                : "● Groww connection + DDPI: not verified today");
        authStatus.setTextColor(authReady ? GREEN : RED);
        ipStatus.setText(ipReady
                ? "● Surfshark Dedicated IP: verified • " + AppPrefs.lastPublicIp(this)
                : "● Surfshark Dedicated IP: not ready • VPN " + (vpn ? "connected" : "disconnected"));
        ipStatus.setTextColor(ipReady ? GREEN : RED);
        policyStatus.setText(parserReady
                ? "● Routing policy: MIS before 09:30 • CNC GTT after 09:30"
                : "● Routing policy: offline acceptance test required");
        policyStatus.setTextColor(parserReady ? GREEN : AMBER);

        systemStatus.setText(ready ? "READY" : "SETUP REQUIRED");
        systemStatus.setTextColor(ready ? GREEN : AMBER);
        statusDetail.setText(ready
                ? "All production gates passed • active strategies " + active
                + " • saved budgets ₹" + money(AppPrefs.window1Budget(this))
                + " / ₹" + money(AppPrefs.window2Budget(this))
                + " / ₹" + money(AppPrefs.window3Budget(this)) + "."
                : issue + " • Auto-Buy remains blocked.");

        if (AppPrefs.isArmed(this) && !ready) {
            AppPrefs.setArmed(this, false);
            AppPrefs.log(this, "AUTO-DISARMED", issue);
        }
        suppressSwitch = true;
        armedSwitch.setChecked(AppPrefs.isArmed(this) && ready);
        suppressSwitch = false;
        auditLog.setText(AppPrefs.auditLog(this));
    }

    private String readinessIssue() {
        if (windowsDirty) return "Save the edited trading windows";
        if (!hasNotificationAccess()) return "Grant Notification Access to Multyfi AutoBuy";
        if (Build.VERSION.SDK_INT >= 33
                && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)
                != PackageManager.PERMISSION_GRANTED) return "Grant application notifications";
        if (!isBatteryOptimisationExcluded()) return "Set battery use to Unrestricted";
        if (!AppPrefs.parserTestPassed(this)) return "Run the offline production routing test";
        boolean hasToken = SecureStore.has(this, SecureStore.ACCESS_TOKEN);
        boolean hasTotp = SecureStore.has(this, SecureStore.API_KEY)
                && SecureStore.has(this, SecureStore.TOTP_SECRET);
        if (!hasToken && !hasTotp) return "Save Groww authentication credentials";
        if (!AppPrefs.isAuthVerifiedToday(this)) return "Run the read-only Groww connection test today";
        if (!NetworkUtil.isVpnActive(this)) return "Connect Surfshark Dedicated IP";
        if (!AppPrefs.isStaticConfirmed(this)) return "Confirm the exact IP is whitelisted in Groww";
        if (AppPrefs.expectedIp(this).isEmpty()) return "Enter the Groww-whitelisted Dedicated IP";
        if (!AppPrefs.isIpRecentlyVerified(this)) return "Detect and verify the current Dedicated IP";
        return null;
    }

    private boolean hasNotificationAccess() {
        NotificationManager manager = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        return manager != null && manager.isNotificationListenerAccessGranted(
                new ComponentName(this, MultyfiNotificationService.class));
    }

    private boolean isBatteryOptimisationExcluded() {
        PowerManager manager = (PowerManager) getSystemService(POWER_SERVICE);
        return manager != null && manager.isIgnoringBatteryOptimizations(getPackageName());
    }

    private void requestMonitoringNotificationPermission() {
        if (Build.VERSION.SDK_INT >= 33
                && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)
                != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, 200);
        }
    }

    private void openSetting(String action) {
        try { startActivity(new Intent(action)); }
        catch (Exception e) { startActivity(new Intent(Settings.ACTION_SETTINGS)); }
    }

    private SharedPreferences runtimePrefs() {
        return getSharedPreferences(RUNTIME_PREFS, MODE_PRIVATE);
    }

    private double readDouble(EditText field) {
        String value = text(field).replace(",", "");
        if (value.isEmpty()) return -1d;
        return Double.parseDouble(value);
    }

    private void setBusy(Button button, boolean busy, String busyText, String normalText) {
        runOnUiThread(() -> {
            button.setEnabled(!busy);
            button.setText(busy ? busyText : normalText);
            button.setAlpha(busy ? 0.62f : 1f);
        });
    }

    private LinearLayout column() {
        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        return layout;
    }

    private LinearLayout row() {
        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.HORIZONTAL);
        layout.setGravity(Gravity.CENTER_VERTICAL);
        return layout;
    }

    private LinearLayout card() {
        LinearLayout layout = column();
        layout.setPadding(dp(16), dp(16), dp(16), dp(16));
        layout.setBackground(rounded(CARD, 18, Color.rgb(44, 65, 96), 1));
        layout.setElevation(dp(3));
        return layout;
    }

    private TextView sectionTitle(String value) {
        TextView view = label(value, 13, GREEN, true);
        view.setLetterSpacing(0.10f);
        return view;
    }

    private TextView statusRow() {
        TextView view = label("● Checking…", 13, MUTED, false);
        view.setLineSpacing(0f, 1.12f);
        return view;
    }

    private TextView label(String value, int sp, int color, boolean bold) {
        TextView view = new TextView(this);
        view.setText(value);
        view.setTextSize(sp);
        view.setTextColor(color);
        view.setTypeface(bold ? Typeface.DEFAULT_BOLD : Typeface.DEFAULT);
        return view;
    }

    private EditText moneyField(String hint) {
        EditText field = textField(hint, "");
        field.setInputType(InputType.TYPE_CLASS_NUMBER | InputType.TYPE_NUMBER_FLAG_DECIMAL);
        return field;
    }

    private EditText decimalField(String hint) {
        EditText field = textField(hint, "");
        field.setInputType(InputType.TYPE_CLASS_NUMBER | InputType.TYPE_NUMBER_FLAG_DECIMAL);
        return field;
    }

    private EditText secureField(String hint) {
        EditText field = textField(hint, "");
        field.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        field.setImportantForAutofill(View.IMPORTANT_FOR_AUTOFILL_NO_EXCLUDE_DESCENDANTS);
        return field;
    }

    private EditText textField(String hint, String value) {
        EditText field = new EditText(this);
        field.setHint(hint);
        field.setHintTextColor(Color.rgb(115, 134, 166));
        field.setTextColor(TEXT);
        field.setTextSize(15f);
        field.setSingleLine(true);
        field.setPadding(dp(14), dp(12), dp(14), dp(12));
        field.setBackground(rounded(FIELD, 13, Color.rgb(57, 79, 115), 1));
        if (!TextUtils.isEmpty(value)) field.setText(value);
        return field;
    }

    private Button primaryButton(String text) {
        return styledButton(text, PURPLE, Color.WHITE);
    }

    private Button secondaryButton(String text) {
        return styledButton(text, Color.rgb(31, 62, 92), TEXT);
    }

    private Button warningButton(String text) {
        return styledButton(text, Color.rgb(157, 104, 32), Color.WHITE);
    }

    private Button destructiveButton(String text) {
        return styledButton(text, Color.rgb(120, 42, 57), Color.WHITE);
    }

    private Button compactButton(String text) {
        Button button = styledButton(text, PURPLE, Color.WHITE);
        button.setTextSize(11f);
        button.setPadding(dp(14), dp(6), dp(14), dp(6));
        return button;
    }

    private Button styledButton(String text, int background, int foreground) {
        Button button = new Button(this);
        button.setText(text);
        button.setTextColor(foreground);
        button.setTextSize(13f);
        button.setTypeface(Typeface.DEFAULT_BOLD);
        button.setAllCaps(false);
        button.setGravity(Gravity.CENTER);
        button.setPadding(dp(14), dp(10), dp(14), dp(10));
        button.setBackground(rounded(background, 13, Color.TRANSPARENT, 0));
        return button;
    }

    private GradientDrawable rounded(int color, int radiusDp, int strokeColor, int strokeDp) {
        GradientDrawable drawable = new GradientDrawable();
        drawable.setColor(color);
        drawable.setCornerRadius(dp(radiusDp));
        if (strokeDp > 0) drawable.setStroke(dp(strokeDp), strokeColor);
        return drawable;
    }

    private LinearLayout.LayoutParams matchWrap() {
        return new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT);
    }

    private LinearLayout.LayoutParams wrapWrap() {
        return new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT,
                LinearLayout.LayoutParams.WRAP_CONTENT);
    }

    private LinearLayout.LayoutParams weightWrap(float weight) {
        return new LinearLayout.LayoutParams(0,
                LinearLayout.LayoutParams.WRAP_CONTENT, weight);
    }

    private LinearLayout.LayoutParams topMargin(int topDp) {
        LinearLayout.LayoutParams params = matchWrap();
        params.topMargin = dp(topDp);
        return params;
    }

    private LinearLayout.LayoutParams sectionMargin() {
        LinearLayout.LayoutParams params = matchWrap();
        params.topMargin = dp(16);
        return params;
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    private static String text(EditText field) {
        return field.getText() == null ? "" : field.getText().toString().trim();
    }

    private static String money(double value) {
        return Math.rint(value) == value
                ? String.format(Locale.US, "%.0f", value)
                : String.format(Locale.US, "%.2f", value);
    }

    private static String safeMessage(Exception e) {
        String value = e.getMessage();
        return value == null || value.trim().isEmpty()
                ? e.getClass().getSimpleName() : value;
    }

    private static long atIst(int year, int month, int day, int hour, int minute) {
        Calendar c = Calendar.getInstance(TimeZone.getTimeZone("Asia/Kolkata"), Locale.US);
        c.set(year, month - 1, day, hour, minute, 0);
        c.set(Calendar.MILLISECOND, 0);
        return c.getTimeInMillis();
    }

    private void toast(String message) {
        Toast.makeText(this, message, Toast.LENGTH_LONG).show();
    }
}
