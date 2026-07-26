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

import java.util.Locale;
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
    private EditText quantityInput;
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
        quantityInput = findViewById(R.id.quantityInput);
        bufferInput = findViewById(R.id.bufferInput);
        expectedIpInput = findViewById(R.id.expectedIpInput);
        staticIpConfirm = findViewById(R.id.staticIpConfirm);
    }

    private void loadSavedState() {
        quantityInput.setText(String.valueOf(AppPrefs.quantity(this)));
        bufferInput.setText(String.format(Locale.US, "%.2f",
                AppPrefs.entryBufferPercent(this)));
        expectedIpInput.setText(AppPrefs.expectedIp(this));
        staticIpConfirm.setChecked(AppPrefs.isStaticConfirmed(this));
        String currentIp = AppPrefs.lastPublicIp(this);
        currentIpStatus.setText(currentIp.isEmpty()
                ? "Current public IP: not checked"
                : "Current public IP: " + currentIp + " • "
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
                            "Android 10 home-phone automation enabled: complete Multyfi equity/swing/multibagger/free/intraday signals, quantity "
                                    + AppPrefs.quantity(this) + ", buffer "
                                    + String.format(Locale.US, "%.2f", AppPrefs.entryBufferPercent(this)) + "%.");
                    StrategyMonitorService.ensureRunning(this);
                }
            } else {
                AppPrefs.setArmed(this, false);
                AppPrefs.log(this, "DISARMED",
                        "New automatic entries disabled. Existing strategies remain monitored and protected.");
            }
            refreshStatus();
        });
    }

    private void saveConfiguration() {
        try {
            int quantity = readQuantityInput();
            double buffer = readBufferInput();
            if (!AppPrefs.isValidQuantity(quantity)) {
                toast("Quantity must be between " + AppPrefs.MIN_QUANTITY + " and " + AppPrefs.MAX_QUANTITY + ".");
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
            AppPrefs.setQuantity(this, quantity);
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
                    "Quantity " + quantity + " • entry buffer "
                            + String.format(Locale.US, "%.2f", buffer) + "% • expected IP "
                            + (AppPrefs.expectedIp(this).isEmpty() ? "not entered" : AppPrefs.expectedIp(this))
                            + " • authentication " + (hasToken || hasTotp ? "configured" : "not configured") + ".");
            toast("Configuration saved. Quantity " + quantity + ", buffer "
                    + String.format(Locale.US, "%.2f", buffer) + "%.");
            StrategyMonitorService.ensureRunning(this);
            refreshStatus();
        } catch (Exception e) {
            toast("Could not save configuration: " + safeMessage(e));
        }
    }

    private void detectAndCopyPublicIp(Button button) {
        setBusy(button, true, "Detecting…", "Detect and copy current public IP");
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
                    if (clipboard != null) clipboard.setPrimaryClip(ClipData.newPlainText("Public IP", ip));
                    if (text(expectedIpInput).isEmpty()) expectedIpInput.setText(ip);
                    currentIpStatus.setText("Current public IP: " + ip + " • "
                            + NetworkUtil.connectionLabel(this) + " • copied");
                });
                message = "Copied public IP " + actual
                        + ". Add it in Groww only if your ISP/VPN guarantees it remains fixed.";
                AppPrefs.log(this, "PUBLIC IP COPIED", message);
            } catch (Exception e) {
                message = "Public IP detection failed: " + safeMessage(e);
            }
            final String result = message;
            runOnUiThread(() -> {
                setBusy(button, false, "", "Detect and copy current public IP");
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
        String expected = text(expectedIpInput);
        if (expected.isEmpty()) expected = AppPrefs.expectedIp(this);
        if (expected.isEmpty()) {
            toast("Detect the current public IP, add it in Groww, then enter it here.");
            return;
        }
        if (!staticIpConfirm.isChecked()) {
            toast("Confirm that this exact public IP is configured in Groww.");
            return;
        }
        final String expectedIp = expected;
        AppPrefs.setExpectedIp(this, expectedIp);
        AppPrefs.setStaticConfirmed(this, true);
        setBusy(button, true, "Checking…", "Verify current IP against Groww whitelist");
        executor.execute(() -> {
            String message;
            try {
                String actual = NetworkUtil.fetchPublicIp();
                boolean success = expectedIp.equals(actual);
                AppPrefs.setIpVerification(this, actual, success);
                message = success
                        ? "Public IP verified: " + actual + " over " + NetworkUtil.connectionLabel(this) + "."
                        : "IP mismatch. Groww expects " + expectedIp + " but this phone currently uses " + actual + ".";
                AppPrefs.log(this, success ? "PUBLIC IP VERIFIED" : "PUBLIC IP FAILED", message);
            } catch (Exception e) {
                AppPrefs.setIpVerifiedAt(this, 0L);
                message = "IP verification failed: " + safeMessage(e);
            }
            final String resultMessage = message;
            runOnUiThread(() -> {
                setBusy(button, false, "", "Verify current IP against Groww whitelist");
                toast(resultMessage);
                loadSavedState();
                refreshStatus();
            });
        });
    }

    private void runParserTest() {
        long validTradingTime = 1_785_124_200_000L;
        String[] samples = {
                "Equity Recommendation\nStock Name: TCS\nEntry Range: 3200-3220\nTarget: 3300\nStop Loss: 3150",
                "Swing Call\nStock: INFY\nBuy Range: 1600-1610\nTarget Price: 1680\nSL: 1570",
                "Multibagger Recommendation\nSymbol: ABCAPITAL\nEntry: 310-315\nTarget: 340\nStoploss: 298",
                "Today's Free Equity Recommendation\nStock Name: SGFIN\nEntry Range: 681-684\nTarget: 720\nStop Loss: 676",
                "Equity Intraday\nStock Name: SBIN\nBuy Price: 810\nTarget: 825\nStop Loss: 802"
        };
        boolean passed = true;
        StringBuilder parsed = new StringBuilder();
        for (String sample : samples) {
            SignalParser.ParsedSignal signal = SignalParser.parse(sample,
                    validTradingTime, AppPrefs.entryBufferPercent(this));
            if (signal == null) { passed = false; break; }
            if (parsed.length() > 0) parsed.append(", ");
            parsed.append(signal.category).append("/").append(signal.productType);
        }
        AppPrefs.setParserTestPassed(this, passed);
        if (passed) {
            String message = "Parsed all supported categories: " + parsed + " • no order submitted.";
            AppPrefs.log(this, "MULTI-CATEGORY PARSER PASSED", message);
            toast(message);
        } else {
            AppPrefs.log(this, "PARSER TEST FAILED", "One or more complete sample formats were not parsed.");
            toast("Parser test failed.");
        }
        refreshStatus();
    }

    private void refreshStatus() {
        boolean notificationReady = hasNotificationAccess();
        boolean authReady = AppPrefs.isAuthVerifiedToday(this);
        boolean ipReady = AppPrefs.isStaticConfirmed(this) && AppPrefs.isIpRecentlyVerified(this);
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
        ipStatus.setText(ipReady ? "● Public/static IP: verified • " + AppPrefs.lastPublicIp(this)
                : "● Public/static IP: not verified • " + NetworkUtil.connectionLabel(this));
        ipStatus.setTextColor(getColor(ipReady ? R.color.success : R.color.danger));
        String currentIp = AppPrefs.lastPublicIp(this);
        currentIpStatus.setText(currentIp.isEmpty() ? "Current public IP: not checked"
                : "Current public IP: " + currentIp + " • " + NetworkUtil.connectionLabel(this));

        String issue = readinessIssue();
        boolean ready = issue == null;
        systemStatus.setText(ready ? "READY" : "SETUP REQUIRED");
        systemStatus.setTextColor(getColor(ready ? R.color.success : R.color.warning));
        statusDetail.setText(ready
                ? "LG G7 is ready. Complete Multyfi signals will be handled autonomously. Quantity "
                + AppPrefs.quantity(this) + ", buffer "
                + String.format(Locale.US, "%.2f", AppPrefs.entryBufferPercent(this))
                + "% • active strategies " + activeStrategies + "."
                : issue + (parserReady ? "" : " Run the multi-category parser test.")
                + (batteryReady ? "" : " Exclude the app from battery optimisation.")
                + (activeStrategies > 0 ? " Existing active strategies: " + activeStrategies + "." : ""));

        if (AppPrefs.isArmed(this) && !ready) {
            AppPrefs.setArmed(this, false);
            suppressSwitch = true;
            armedSwitch.setChecked(false);
            suppressSwitch = false;
            AppPrefs.log(this, "AUTO-DISARMED", "A required readiness gate is no longer valid: " + issue);
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
                && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            return "Grant app notifications for the persistent monitor.";
        }
        if (!isBatteryOptimisationExcluded()) return "Exclude Multyfi AutoBuy from Android battery optimisation.";
        if (!AppPrefs.parserTestPassed(this)) return "Multi-category parser test has not passed.";
        boolean hasToken = SecureStore.has(this, SecureStore.ACCESS_TOKEN);
        boolean hasTotp = SecureStore.has(this, SecureStore.API_KEY)
                && SecureStore.has(this, SecureStore.TOTP_SECRET);
        if (!hasToken && !hasTotp) return "Save Groww authentication credentials.";
        if (!AppPrefs.isAuthVerifiedToday(this)) return "Verify the Groww account and DDPI for today.";
        if (!AppPrefs.isStaticConfirmed(this)) return "Confirm the public IP configured in Groww.";
        if (AppPrefs.expectedIp(this).isEmpty()) return "Enter the Groww-whitelisted public IP.";
        if (!AppPrefs.isIpRecentlyVerified(this)) return "Verify that this phone's current public IP matches Groww.";
        return null;
    }

    private void requestMonitoringNotificationPermission() {
        if (Build.VERSION.SDK_INT >= 33
                && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, 140);
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

    private int readQuantityInput() {
        String value = text(quantityInput);
        if (value.isEmpty()) return AppPrefs.quantity(this);
        try { return Integer.parseInt(value); }
        catch (NumberFormatException e) { return -1; }
    }

    private double readBufferInput() {
        String value = text(bufferInput);
        if (value.isEmpty()) return AppPrefs.entryBufferPercent(this);
        try { return Double.parseDouble(value); }
        catch (NumberFormatException e) { return -1d; }
    }

    private void updateRulesSummary() {
        if (rulesSummary == null) return;
        rulesSummary.setText("ALL COMPLETE MULTYFI CALLS • Equity, swing, multibagger, free-equity and intraday"
                + " • Quantity " + AppPrefs.quantity(this)
                + " • Entry buffer " + String.format(Locale.US, "%.2f", AppPrefs.entryBufferPercent(this)) + "%"
                + " • Adaptive GTT: rapid catch inside cap, pullback GTT above cap"
                + " • CNC for delivery/swing/multibagger/free calls; MIS for explicit intraday"
                + " • Actual-fill stop-loss GTT"
                + " • Target: cancel/verify SL, then market sell"
                + " • MIS forced exit at 15:10 IST"
                + " • DDPI and exact public-IP match required"
                + " • Noise/incomplete/derivative notifications ignored");
    }

    private void setBusy(Button button, boolean busy, String busyText, String normalText) {
        runOnUiThread(() -> { button.setEnabled(!busy); button.setText(busy ? busyText : normalText); });
    }

    private static String text(EditText editText) {
        return editText.getText() == null ? "" : editText.getText().toString().trim();
    }

    private static String safeMessage(Exception e) {
        String message = e.getMessage();
        return message == null || message.trim().isEmpty() ? e.getClass().getSimpleName() : message;
    }

    private void toast(String message) { Toast.makeText(this, message, Toast.LENGTH_LONG).show(); }
}
