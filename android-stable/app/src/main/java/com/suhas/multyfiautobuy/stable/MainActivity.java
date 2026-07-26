package com.suhas.multyfiautobuy.stable;

import android.Manifest;
import android.app.Activity;
import android.app.NotificationManager;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.Bundle;
import android.os.PowerManager;
import android.provider.Settings;
import android.service.notification.NotificationListenerService;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.EditText;
import android.widget.Switch;
import android.widget.TextView;
import android.widget.Toast;

import java.util.Calendar;
import java.util.Collections;
import java.util.Locale;
import java.util.TimeZone;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class MainActivity extends Activity {
    private final ExecutorService executor = Executors.newSingleThreadExecutor();

    private TextView systemStatus;
    private TextView statusDetail;
    private TextView notificationStatus;
    private TextView authStatus;
    private TextView ipStatus;
    private TextView currentIpStatus;
    private TextView rulesSummary;
    private TextView auditLog;
    private Switch armedSwitch;
    private EditText apiKeyInput;
    private EditText totpSecretInput;
    private EditText accessTokenInput;
    private EditText window1BudgetInput;
    private EditText window2BudgetInput;
    private EditText window3BudgetInput;
    private EditText bufferInput;
    private EditText expectedIpInput;
    private CheckBox staticIpConfirm;
    private boolean suppressSwitch;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_SECURE);
        setContentView(R.layout.activity_main);
        bindViews();
        loadSavedState();
        wireActions();
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

    private void bindViews() {
        systemStatus = findViewById(R.id.systemStatus);
        statusDetail = findViewById(R.id.statusDetail);
        notificationStatus = findViewById(R.id.notificationStatus);
        authStatus = findViewById(R.id.authStatus);
        ipStatus = findViewById(R.id.ipStatus);
        currentIpStatus = findViewById(R.id.currentIpStatus);
        rulesSummary = findViewById(R.id.rulesSummary);
        auditLog = findViewById(R.id.auditLog);
        armedSwitch = findViewById(R.id.armedSwitch);
        apiKeyInput = findViewById(R.id.apiKeyInput);
        totpSecretInput = findViewById(R.id.totpSecretInput);
        accessTokenInput = findViewById(R.id.accessTokenInput);
        window1BudgetInput = findViewById(R.id.window1BudgetInput);
        window2BudgetInput = findViewById(R.id.window2BudgetInput);
        window3BudgetInput = findViewById(R.id.window3BudgetInput);
        bufferInput = findViewById(R.id.bufferInput);
        expectedIpInput = findViewById(R.id.expectedIpInput);
        staticIpConfirm = findViewById(R.id.staticIpConfirm);
    }

    private void loadSavedState() {
        window1BudgetInput.setText(String.format(Locale.US, "%.0f",
                AppPrefs.window1Budget(this)));
        window2BudgetInput.setText(String.format(Locale.US, "%.0f",
                AppPrefs.window2Budget(this)));
        window3BudgetInput.setText(String.format(Locale.US, "%.0f",
                AppPrefs.window3Budget(this)));
        bufferInput.setText(String.format(Locale.US, "%.2f",
                AppPrefs.entryBufferPercent(this)));
        expectedIpInput.setText(AppPrefs.expectedIp(this));
        staticIpConfirm.setChecked(AppPrefs.isStaticConfirmed(this));
        String currentIp = AppPrefs.lastPublicIp(this);
        currentIpStatus.setText(currentIp.isEmpty()
                ? "Surfshark public IP: not checked"
                : "Surfshark public IP: " + currentIp + " • "
                + NetworkUtil.connectionLabel(this));
        if (SecureStore.has(this, SecureStore.API_KEY)) apiKeyInput.setHint("API key saved securely");
        if (SecureStore.has(this, SecureStore.TOTP_SECRET)) totpSecretInput.setHint("TOTP secret saved securely");
        if (SecureStore.has(this, SecureStore.ACCESS_TOKEN)) accessTokenInput.setHint("Access token saved for today");
        suppressSwitch = true;
        armedSwitch.setChecked(AppPrefs.isArmed(this));
        suppressSwitch = false;
        updateRulesSummary();
    }

    private void wireActions() {
        Button openAccess = findViewById(R.id.openNotificationAccess);
        Button openBattery = findViewById(R.id.openBatterySettings);
        Button openVpn = findViewById(R.id.openVpnSettings);
        Button detectCopyIp = findViewById(R.id.detectCopyIp);
        Button save = findViewById(R.id.saveCredentials);
        Button authenticate = findViewById(R.id.authenticateToday);
        Button verifyGroww = findViewById(R.id.verifyGroww);
        Button verifyIp = findViewById(R.id.verifyIp);
        Button parserTest = findViewById(R.id.parserTest);
        Button clearLog = findViewById(R.id.clearLog);

        openAccess.setOnClickListener(v -> {
            try { startActivity(new Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS)); }
            catch (Exception e) { startActivity(new Intent(Settings.ACTION_SETTINGS)); }
        });
        openBattery.setOnClickListener(v -> {
            try { startActivity(new Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS)); }
            catch (Exception e) { startActivity(new Intent(Settings.ACTION_SETTINGS)); }
        });
        openVpn.setOnClickListener(v -> {
            try { startActivity(new Intent(Settings.ACTION_VPN_SETTINGS)); }
            catch (Exception e) { startActivity(new Intent(Settings.ACTION_SETTINGS)); }
        });
        detectCopyIp.setOnClickListener(v -> detectAndCopyPublicIp(detectCopyIp));
        save.setOnClickListener(v -> saveConfiguration());
        authenticate.setOnClickListener(v -> authenticateToday(authenticate));
        verifyGroww.setOnClickListener(v -> verifyGrowwAccount(verifyGroww));
        verifyIp.setOnClickListener(v -> verifyPublicIp(verifyIp));
        parserTest.setOnClickListener(v -> runParserTest());
        clearLog.setOnClickListener(v -> { AppPrefs.clearLog(this); refreshStatus(); });

        armedSwitch.setOnCheckedChangeListener((buttonView, checked) -> {
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
                    AppPrefs.log(this, "ARMED",
                            "S24 Ultra automation enabled: 09:00–09:30 ₹"
                                    + money(AppPrefs.window1Budget(this))
                                    + " MIS; 09:30–10:00 ₹"
                                    + money(AppPrefs.window2Budget(this))
                                    + "; 10:00–15:30 ₹"
                                    + money(AppPrefs.window3Budget(this))
                                    + "; buffer "
                                    + String.format(Locale.US, "%.2f",
                                    AppPrefs.entryBufferPercent(this))
                                    + "%; immediate LIMIT entries and strict early exits enabled.");
                    StrategyMonitorService.ensureRunning(this);
                }
            } else {
                AppPrefs.setArmed(this, false);
                AppPrefs.log(this, "DISARMED",
                        "New automatic entries disabled. Existing strategies and queued early exits remain monitored.");
            }
            refreshStatus();
        });
    }

    private void saveConfiguration() {
        try {
            double first = readBudget(window1BudgetInput, AppPrefs.window1Budget(this));
            double second = readBudget(window2BudgetInput, AppPrefs.window2Budget(this));
            double third = readBudget(window3BudgetInput, AppPrefs.window3Budget(this));
            double buffer = readBufferInput();
            if (!AppPrefs.isValidTradeBudget(first)
                    || !AppPrefs.isValidTradeBudget(second)
                    || !AppPrefs.isValidTradeBudget(third)) {
                toast("Each window amount must be between ₹1,000 and ₹5,00,000.");
                return;
            }
            if (!AppPrefs.isValidEntryBuffer(buffer)) {
                toast("Entry buffer must be between 0% and 2%.");
                return;
            }
            String apiKey = text(apiKeyInput);
            String secret = text(totpSecretInput);
            String accessToken = text(accessTokenInput);
            if (!apiKey.isEmpty()) SecureStore.put(this, SecureStore.API_KEY, apiKey);
            if (!secret.isEmpty()) SecureStore.put(this, SecureStore.TOTP_SECRET, secret);
            if (!accessToken.isEmpty()) {
                SecureStore.put(this, SecureStore.ACCESS_TOKEN, accessToken);
                SecureStore.put(this, SecureStore.ACCESS_TOKEN_DATE, AppPrefs.istDate());
            }
            AppPrefs.setWindowBudgets(this, first, second, third);
            AppPrefs.setEntryBufferPercent(this, buffer);
            AppPrefs.setExpectedIp(this, text(expectedIpInput));
            AppPrefs.setStaticConfirmed(this, staticIpConfirm.isChecked());
            boolean hasToken = SecureStore.has(this, SecureStore.ACCESS_TOKEN);
            boolean hasTotp = SecureStore.has(this, SecureStore.API_KEY)
                    && SecureStore.has(this, SecureStore.TOTP_SECRET);
            apiKeyInput.setText("");
            totpSecretInput.setText("");
            accessTokenInput.setText("");
            loadSavedState();
            AppPrefs.log(this, "CONFIG SAVED",
                    "09:00–09:30 ₹" + money(first)
                            + " • 09:30–10:00 ₹" + money(second)
                            + " • 10:00–15:30 ₹" + money(third)
                            + " • entry buffer "
                            + String.format(Locale.US, "%.2f", buffer)
                            + "% • Surfshark Dedicated IP "
                            + (AppPrefs.expectedIp(this).isEmpty()
                            ? "not entered" : AppPrefs.expectedIp(this))
                            + " • authentication "
                            + (hasToken || hasTotp ? "configured" : "not configured") + ".");
            toast("Configuration saved for all three windows.");
            StrategyMonitorService.ensureRunning(this);
            refreshStatus();
        } catch (Exception e) {
            toast("Could not save configuration: " + safeMessage(e));
        }
    }

    private void detectAndCopyPublicIp(Button button) {
        if (!NetworkUtil.isVpnActive(this)) {
            toast("Connect Surfshark to your Dedicated IP before copying the public IP.");
            return;
        }
        setBusy(button, true, "Detecting…", "Detect and copy Surfshark Dedicated IP");
        executor.execute(() -> {
            String message;
            try {
                String actual = NetworkUtil.fetchPublicIp();
                String expected = text(expectedIpInput);
                if (expected.isEmpty()) expected = AppPrefs.expectedIp(this);
                boolean matched = !expected.isEmpty() && expected.equals(actual);
                AppPrefs.setIpVerification(this, actual, matched);
                final String ip = actual;
                runOnUiThread(() -> {
                    ClipboardManager clipboard = (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
                    if (clipboard != null) clipboard.setPrimaryClip(ClipData.newPlainText("Surfshark Dedicated IP", ip));
                    if (text(expectedIpInput).isEmpty()) expectedIpInput.setText(ip);
                    currentIpStatus.setText("Surfshark public IP: " + ip + " • copied");
                });
                message = "Copied Surfshark public IP " + actual
                        + ". Add this exact Dedicated IP in Groww Trading APIs.";
                AppPrefs.log(this, "SURFSHARK IP COPIED", message);
            } catch (Exception e) {
                message = "Public IP detection failed: " + safeMessage(e);
            }
            final String result = message;
            runOnUiThread(() -> {
                setBusy(button, false, "", "Detect and copy Surfshark Dedicated IP");
                toast(result);
                refreshStatus();
            });
        });
    }

    private void authenticateToday(Button button) {
        setBusy(button, true, "Authenticating…", "Authenticate today");
        executor.execute(() -> {
            String apiKey = SecureStore.get(this, SecureStore.API_KEY);
            String secret = SecureStore.get(this, SecureStore.TOTP_SECRET);
            GrowwClient.AuthResult result = GrowwClient.authenticate(apiKey, secret);
            if (result.success) {
                try {
                    SecureStore.put(this, SecureStore.ACCESS_TOKEN, result.accessToken);
                    SecureStore.put(this, SecureStore.ACCESS_TOKEN_DATE, AppPrefs.istDate());
                    AppPrefs.log(this, "AUTH TOKEN READY", result.message);
                } catch (Exception e) {
                    AppPrefs.log(this, "AUTH FAILED",
                            "Token generated but could not be stored: " + safeMessage(e));
                }
            } else {
                AppPrefs.clearAuthVerified(this);
                AppPrefs.log(this, "AUTH FAILED", result.message);
            }
            runOnUiThread(() -> {
                setBusy(button, false, "", "Authenticate today");
                toast(result.message);
                refreshStatus();
            });
        });
    }

    private void verifyGrowwAccount(Button button) {
        setBusy(button, true, "Verifying…", "Verify Groww account and DDPI");
        executor.execute(() -> {
            String token = TokenManager.validToken(this);
            GrowwClient.ApiResult result = token.isEmpty()
                    ? GrowwClient.ApiResult.failure("", "No valid Groww access token is available.", 0)
                    : GrowwClient.verifyProfile(token);
            if (result.success) {
                AppPrefs.setAuthVerified(this, result.id);
                AppPrefs.log(this, "GROWW + DDPI VERIFIED", result.message);
            } else {
                AppPrefs.clearAuthVerified(this);
                AppPrefs.log(this, "GROWW VERIFY FAILED", result.message);
            }
            runOnUiThread(() -> {
                setBusy(button, false, "", "Verify Groww account and DDPI");
                toast(result.message);
                refreshStatus();
            });
        });
    }

    private void verifyPublicIp(Button button) {
        if (!NetworkUtil.isVpnActive(this)) {
            toast("Surfshark Dedicated IP VPN is not active.");
            return;
        }
        String expected = text(expectedIpInput);
        if (expected.isEmpty()) expected = AppPrefs.expectedIp(this);
        if (expected.isEmpty()) {
            toast("Detect the Surfshark Dedicated IP, add it in Groww, then enter it here.");
            return;
        }
        if (!staticIpConfirm.isChecked()) {
            toast("Confirm that this exact Surfshark Dedicated IP is configured in Groww.");
            return;
        }
        final String expectedIp = expected;
        AppPrefs.setExpectedIp(this, expectedIp);
        AppPrefs.setStaticConfirmed(this, true);
        setBusy(button, true, "Checking…", "Verify Surfshark IP against Groww");
        executor.execute(() -> {
            String message;
            try {
                String actual = NetworkUtil.fetchPublicIp();
                boolean success = expectedIp.equals(actual)
                        && NetworkUtil.isVpnActive(this);
                AppPrefs.setIpVerification(this, actual, success);
                message = success
                        ? "Surfshark Dedicated IP verified: " + actual + "."
                        : "IP mismatch. Groww expects " + expectedIp
                        + " but this phone currently uses " + actual + ".";
                AppPrefs.log(this, success ? "SURFSHARK IP VERIFIED" : "SURFSHARK IP FAILED", message);
            } catch (Exception e) {
                AppPrefs.setIpVerifiedAt(this, 0L);
                message = "IP verification failed: " + safeMessage(e);
            }
            final String resultMessage = message;
            runOnUiThread(() -> {
                setBusy(button, false, "", "Verify Surfshark IP against Groww");
                toast(resultMessage);
                loadSavedState();
                refreshStatus();
            });
        });
    }

    private void runParserTest() {
        long firstTime = atIst(2026, 7, 24, 9, 10);
        long secondTime = atIst(2026, 7, 24, 9, 40);
        long thirdTime = atIst(2026, 7, 24, 10, 30);
        String sample = "Equity Recommendation\nStock Name: TCS\nEntry Range: 3200-3220\nTarget: 3300\nStop Loss: 3150";
        SignalParser.ParsedSignal signal = SignalParser.parse(sample, firstTime,
                AppPrefs.entryBufferPercent(this));
        boolean passed = signal != null;
        AppPrefs.TradeWindow first = AppPrefs.tradeWindow(this, firstTime);
        AppPrefs.TradeWindow second = AppPrefs.tradeWindow(this, secondTime);
        AppPrefs.TradeWindow third = AppPrefs.tradeWindow(this, thirdTime);
        passed = passed && first != null && first.forceMis
                && second != null && !second.forceMis
                && third != null && !third.forceMis
                && AppPrefs.quantityForBudget(first.budget, signal.maxBuyPrice) >= 1;

        Strategy dummy = new Strategy("test-event", "TCS", "EQUITY", "CNC",
                3, 3300d, 3150d, 0, "TESTREF", "TESTGTT", firstTime);
        SignalParser.EarlyExitSignal exit = SignalParser.parseEarlyExit(
                "Exiting early\nStock Name: TCS", firstTime,
                Collections.singletonList(dummy));
        passed = passed && exit != null && "TCS".equals(exit.symbol);

        AppPrefs.setParserTestPassed(this, passed);
        if (passed) {
            String message = "Parsed Multyfi entry, three sizing windows, forced 09:00–09:30 MIS, and strict symbol-matched early exit • no order submitted.";
            AppPrefs.log(this, "WINDOW + EXIT PARSER PASSED", message);
            toast(message);
        } else {
            AppPrefs.log(this, "PARSER TEST FAILED",
                    "Entry, window routing or early-exit parsing failed.");
            toast("Parser test failed.");
        }
        refreshStatus();
    }

    private void refreshStatus() {
        boolean notificationReady = hasNotificationAccess();
        boolean authReady = AppPrefs.isAuthVerifiedToday(this);
        boolean vpnReady = NetworkUtil.isVpnActive(this);
        boolean ipReady = vpnReady && AppPrefs.isStaticConfirmed(this)
                && AppPrefs.isIpRecentlyVerified(this);
        boolean parserReady = AppPrefs.parserTestPassed(this);
        boolean batteryReady = isBatteryOptimisationExcluded();
        int activeStrategies = StrategyStore.activeCount(this);

        updateRulesSummary();
        notificationStatus.setText(notificationReady ? "● Notification access: granted"
                : "● Notification access: not granted");
        notificationStatus.setTextColor(getColor(notificationReady ? R.color.success : R.color.danger));
        String ucc = AppPrefs.ucc(this);
        authStatus.setText(authReady ? "● Groww + DDPI: verified today" + (ucc.isEmpty() ? "" : " • UCC " + ucc)
                : "● Groww + DDPI: not verified today");
        authStatus.setTextColor(getColor(authReady ? R.color.success : R.color.danger));
        ipStatus.setText(ipReady ? "● Surfshark Dedicated IP: verified • " + AppPrefs.lastPublicIp(this)
                : "● Surfshark Dedicated IP: not verified • VPN " + (vpnReady ? "connected" : "disconnected"));
        ipStatus.setTextColor(getColor(ipReady ? R.color.success : R.color.danger));
        String currentIp = AppPrefs.lastPublicIp(this);
        currentIpStatus.setText(currentIp.isEmpty() ? "Surfshark public IP: not checked"
                : "Surfshark public IP: " + currentIp + " • " + NetworkUtil.connectionLabel(this));

        String issue = readinessIssue();
        boolean ready = issue == null;
        systemStatus.setText(ready ? "READY" : "SETUP REQUIRED");
        systemStatus.setTextColor(getColor(ready ? R.color.success : R.color.warning));
        statusDetail.setText(ready
                ? "S24 Ultra is ready. 09:00–09:30 ₹"
                + money(AppPrefs.window1Budget(this)) + " MIS • 09:30–10:00 ₹"
                + money(AppPrefs.window2Budget(this)) + " • 10:00–15:30 ₹"
                + money(AppPrefs.window3Budget(this)) + " • strategies "
                + activeStrategies + "."
                : issue + (parserReady ? "" : " Run the window and early-exit parser test.")
                + (batteryReady ? "" : " Set battery use to Unrestricted.")
                + (activeStrategies > 0 ? " Existing active strategies: " + activeStrategies + "." : ""));

        if (AppPrefs.isArmed(this) && !ready) {
            AppPrefs.setArmed(this, false);
            suppressSwitch = true;
            armedSwitch.setChecked(false);
            suppressSwitch = false;
            AppPrefs.log(this, "AUTO-DISARMED",
                    "A required readiness gate is no longer valid: " + issue);
        } else {
            suppressSwitch = true;
            armedSwitch.setChecked(AppPrefs.isArmed(this));
            suppressSwitch = false;
        }
        auditLog.setText(AppPrefs.auditLog(this));
    }

    private String readinessIssue() {
        if (!hasNotificationAccess()) return "Grant notification access.";
        if (Build.VERSION.SDK_INT >= 33
                && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)
                != PackageManager.PERMISSION_GRANTED) {
            return "Grant app notifications for the persistent monitor.";
        }
        if (!isBatteryOptimisationExcluded()) {
            return "Set Multyfi AutoBuy battery use to Unrestricted.";
        }
        if (!AppPrefs.parserTestPassed(this)) return "Window and early-exit parser test has not passed.";
        boolean hasToken = SecureStore.has(this, SecureStore.ACCESS_TOKEN);
        boolean hasTotp = SecureStore.has(this, SecureStore.API_KEY)
                && SecureStore.has(this, SecureStore.TOTP_SECRET);
        if (!hasToken && !hasTotp) return "Save Groww authentication credentials.";
        if (!AppPrefs.isAuthVerifiedToday(this)) return "Verify the Groww account and DDPI for today.";
        if (!NetworkUtil.isVpnActive(this)) return "Connect Surfshark to the Dedicated IP.";
        if (!AppPrefs.isStaticConfirmed(this)) return "Confirm the Surfshark Dedicated IP configured in Groww.";
        if (AppPrefs.expectedIp(this).isEmpty()) return "Enter the Groww-whitelisted Dedicated IP.";
        if (!AppPrefs.isIpRecentlyVerified(this)) return "Verify the current Surfshark IP against Groww.";
        return null;
    }

    private void requestMonitoringNotificationPermission() {
        if (Build.VERSION.SDK_INT >= 33
                && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)
                != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, 160);
        }
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

    private double readBudget(EditText field, double fallback) {
        String value = text(field).replace(",", "");
        if (value.isEmpty()) return fallback;
        try { return Double.parseDouble(value); }
        catch (NumberFormatException e) { return -1d; }
    }

    private double readBufferInput() {
        String value = text(bufferInput);
        if (value.isEmpty()) return AppPrefs.entryBufferPercent(this);
        try { return Double.parseDouble(value); }
        catch (NumberFormatException e) { return -1d; }
    }

    private void updateRulesSummary() {
        if (rulesSummary == null) return;
        rulesSummary.setText("THREE CONFIGURABLE WINDOWS"
                + " • 09:00–09:30 ₹" + money(AppPrefs.window1Budget(this)) + " and forced MIS"
                + " • 09:30–10:00 ₹" + money(AppPrefs.window2Budget(this))
                + " • 10:00–15:30 ₹" + money(AppPrefs.window3Budget(this))
                + " • Quantity = floor(window amount ÷ maximum permitted buy price)"
                + " • Immediate marketable LIMIT BUY at the price cap; no near-LTP entry GTT"
                + " • Entry buffer "
                + String.format(Locale.US, "%.2f", AppPrefs.entryBufferPercent(this)) + "%"
                + " • Actual-fill stop-loss GTT"
                + " • Target: cancel/verify SL, then market sell"
                + " • Symbol-matched early exit: cancel entry/SL, verify position, market exit"
                + " • Surfshark Dedicated IP + DDPI required");
    }

    private void setBusy(Button button, boolean busy, String busyText, String normalText) {
        runOnUiThread(() -> {
            button.setEnabled(!busy);
            button.setText(busy ? busyText : normalText);
        });
    }

    private static String text(EditText editText) {
        return editText.getText() == null ? "" : editText.getText().toString().trim();
    }

    private static String safeMessage(Exception e) {
        String message = e.getMessage();
        return message == null || message.trim().isEmpty()
                ? e.getClass().getSimpleName() : message;
    }

    private static String money(double value) {
        return Math.rint(value) == value
                ? String.format(Locale.US, "%.0f", value)
                : String.format(Locale.US, "%.2f", value);
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