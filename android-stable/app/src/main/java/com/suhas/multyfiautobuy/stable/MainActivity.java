package com.suhas.multyfiautobuy.stable;

import android.app.Activity;
import android.app.NotificationManager;
import android.content.ComponentName;
import android.content.Intent;
import android.os.Bundle;
import android.provider.Settings;
import android.service.notification.NotificationListenerService;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.EditText;
import android.widget.Switch;
import android.widget.TextView;
import android.widget.Toast;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class MainActivity extends Activity {
    private final ExecutorService executor = Executors.newSingleThreadExecutor();

    private TextView systemStatus;
    private TextView statusDetail;
    private TextView notificationStatus;
    private TextView authStatus;
    private TextView ipStatus;
    private TextView auditLog;
    private Switch armedSwitch;
    private EditText apiKeyInput;
    private EditText totpSecretInput;
    private EditText accessTokenInput;
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
        refreshStatus();
    }

    @Override
    protected void onResume() {
        super.onResume();
        try {
            NotificationListenerService.requestRebind(
                    new ComponentName(this, MultyfiNotificationService.class));
        } catch (Exception ignored) { }
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
        auditLog = findViewById(R.id.auditLog);
        armedSwitch = findViewById(R.id.armedSwitch);
        apiKeyInput = findViewById(R.id.apiKeyInput);
        totpSecretInput = findViewById(R.id.totpSecretInput);
        accessTokenInput = findViewById(R.id.accessTokenInput);
        expectedIpInput = findViewById(R.id.expectedIpInput);
        staticIpConfirm = findViewById(R.id.staticIpConfirm);
    }

    private void loadSavedState() {
        expectedIpInput.setText(AppPrefs.expectedIp(this));
        staticIpConfirm.setChecked(AppPrefs.isStaticConfirmed(this));
        if (SecureStore.has(this, SecureStore.API_KEY)) apiKeyInput.setHint("API key saved securely");
        if (SecureStore.has(this, SecureStore.TOTP_SECRET)) totpSecretInput.setHint("TOTP secret saved securely");
        if (SecureStore.has(this, SecureStore.ACCESS_TOKEN)) accessTokenInput.setHint("Access token saved for today");
        suppressSwitch = true;
        armedSwitch.setChecked(AppPrefs.isArmed(this));
        suppressSwitch = false;
    }

    private void wireActions() {
        Button openAccess = findViewById(R.id.openNotificationAccess);
        Button save = findViewById(R.id.saveCredentials);
        Button authenticate = findViewById(R.id.authenticateToday);
        Button verifyGroww = findViewById(R.id.verifyGroww);
        Button verifyIp = findViewById(R.id.verifyIp);
        Button parserTest = findViewById(R.id.parserTest);
        Button clearLog = findViewById(R.id.clearLog);

        openAccess.setOnClickListener(v -> {
            try {
                startActivity(new Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS));
            } catch (Exception e) {
                startActivity(new Intent(Settings.ACTION_SETTINGS));
            }
        });

        save.setOnClickListener(v -> saveConfiguration());
        authenticate.setOnClickListener(v -> authenticateToday(authenticate));
        verifyGroww.setOnClickListener(v -> verifyGrowwAccount(verifyGroww));
        verifyIp.setOnClickListener(v -> verifyPublicIp(verifyIp));
        parserTest.setOnClickListener(v -> runParserTest());
        clearLog.setOnClickListener(v -> {
            AppPrefs.clearLog(this);
            refreshStatus();
        });

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
                    AppPrefs.log(this, "ARMED", "Live Multyfi notification-to-Groww GTT buying enabled.");
                }
            } else {
                AppPrefs.setArmed(this, false);
                AppPrefs.log(this, "DISARMED", "Live automatic buying disabled.");
            }
            refreshStatus();
        });
    }

    private void saveConfiguration() {
        try {
            String apiKey = text(apiKeyInput);
            String secret = text(totpSecretInput);
            String accessToken = text(accessTokenInput);
            if (!apiKey.isEmpty()) SecureStore.put(this, SecureStore.API_KEY, apiKey);
            if (!secret.isEmpty()) SecureStore.put(this, SecureStore.TOTP_SECRET, secret);
            if (!accessToken.isEmpty()) {
                SecureStore.put(this, SecureStore.ACCESS_TOKEN, accessToken);
                SecureStore.put(this, SecureStore.ACCESS_TOKEN_DATE, AppPrefs.istDate());
            }
            AppPrefs.setExpectedIp(this, text(expectedIpInput));
            AppPrefs.setStaticConfirmed(this, staticIpConfirm.isChecked());

            boolean hasToken = SecureStore.has(this, SecureStore.ACCESS_TOKEN);
            boolean hasTotp = SecureStore.has(this, SecureStore.API_KEY)
                    && SecureStore.has(this, SecureStore.TOTP_SECRET);
            if (!hasToken && !hasTotp) {
                toast("Enter today’s access token or the Groww API key and TOTP secret.");
                return;
            }
            apiKeyInput.setText("");
            totpSecretInput.setText("");
            accessTokenInput.setText("");
            loadSavedState();
            AppPrefs.log(this, "CONFIG SAVED", "Credentials encrypted with Android Keystore. Static IP: "
                    + (AppPrefs.expectedIp(this).isEmpty() ? "not entered" : AppPrefs.expectedIp(this)) + ".");
            toast("Configuration saved securely.");
            refreshStatus();
        } catch (Exception e) {
            toast("Could not save credentials: " + safeMessage(e));
        }
    }

    private void authenticateToday(Button button) {
        setBusy(button, true, "Authenticating…", getString(R.string.authenticate_today));
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
                    AppPrefs.log(this, "AUTH FAILED", "Token was generated but could not be stored: " + safeMessage(e));
                }
            } else {
                AppPrefs.log(this, "AUTH FAILED", result.message);
            }
            runOnUiThread(() -> {
                setBusy(button, false, "", getString(R.string.authenticate_today));
                toast(result.message);
                refreshStatus();
            });
        });
    }

    private void verifyGrowwAccount(Button button) {
        setBusy(button, true, "Verifying…", getString(R.string.verify_groww));
        executor.execute(() -> {
            String token = currentTokenOrAuthenticate();
            GrowwClient.ApiResult result = token.isEmpty()
                    ? GrowwClient.ApiResult.failure("", "No valid Groww access token is available.", 0)
                    : GrowwClient.verifyProfile(token);
            if (result.success) {
                AppPrefs.setAuthVerified(this, result.id);
                AppPrefs.log(this, "GROWW VERIFIED", result.message);
            } else {
                AppPrefs.log(this, "GROWW VERIFY FAILED", result.message);
            }
            runOnUiThread(() -> {
                setBusy(button, false, "", getString(R.string.verify_groww));
                toast(result.message);
                refreshStatus();
            });
        });
    }

    private void verifyPublicIp(Button button) {
        String expected = text(expectedIpInput);
        if (expected.isEmpty()) expected = AppPrefs.expectedIp(this);
        if (expected.isEmpty()) {
            toast("Enter the static public IP whitelisted in Groww.");
            return;
        }
        if (!staticIpConfirm.isChecked()) {
            toast("Confirm that the Turbo VPN dedicated IP is active and whitelisted.");
            return;
        }
        final String expectedIp = expected;
        AppPrefs.setExpectedIp(this, expectedIp);
        AppPrefs.setStaticConfirmed(this, true);
        setBusy(button, true, "Checking…", getString(R.string.verify_ip));
        executor.execute(() -> {
            String message;
            boolean success = false;
            try {
                if (!NetworkUtil.isVpnActive(this)) {
                    message = "Android does not currently report an active VPN connection.";
                } else {
                    String actual = NetworkUtil.fetchPublicIp();
                    success = expectedIp.equals(actual);
                    message = success
                            ? "VPN IP verified: " + actual
                            : "IP mismatch. Expected " + expectedIp + " but found " + actual + ".";
                }
            } catch (Exception e) {
                message = "IP verification failed: " + safeMessage(e);
            }
            if (success) {
                AppPrefs.setIpVerifiedAt(this, System.currentTimeMillis());
                AppPrefs.log(this, "VPN IP VERIFIED", message);
            } else {
                AppPrefs.setIpVerifiedAt(this, 0L);
                AppPrefs.log(this, "VPN IP FAILED", message);
            }
            final String resultMessage = message;
            runOnUiThread(() -> {
                setBusy(button, false, "", getString(R.string.verify_ip));
                toast(resultMessage);
                refreshStatus();
            });
        });
    }

    private void runParserTest() {
        String sample = "Today’s Free Equity Recommendation\n"
                + "Stock Name : SGFIN\nTarget: ₹700\nEntry Range: ₹681-684\nStop Loss: ₹676";
        SignalParser.ParsedSignal signal = SignalParser.parse(sample, System.currentTimeMillis());
        if (signal == null) {
            AppPrefs.setParserTestPassed(this, false);
            AppPrefs.log(this, "PARSER TEST FAILED", "SGFIN sample was not parsed.");
            toast("Parser test failed.");
        } else {
            AppPrefs.setParserTestPassed(this, true);
            AppPrefs.log(this, "PARSER TEST PASSED", signal.summary() + " • no order submitted.");
            toast("Parsed: " + signal.summary());
        }
        refreshStatus();
    }

    private String currentTokenOrAuthenticate() {
        String tokenDate = SecureStore.get(this, SecureStore.ACCESS_TOKEN_DATE);
        String token = SecureStore.get(this, SecureStore.ACCESS_TOKEN);
        if (!token.isEmpty() && AppPrefs.istDate().equals(tokenDate)) return token;

        String apiKey = SecureStore.get(this, SecureStore.API_KEY);
        String secret = SecureStore.get(this, SecureStore.TOTP_SECRET);
        GrowwClient.AuthResult auth = GrowwClient.authenticate(apiKey, secret);
        if (!auth.success) return "";
        try {
            SecureStore.put(this, SecureStore.ACCESS_TOKEN, auth.accessToken);
            SecureStore.put(this, SecureStore.ACCESS_TOKEN_DATE, AppPrefs.istDate());
            return auth.accessToken;
        } catch (Exception e) {
            return "";
        }
    }

    private void refreshStatus() {
        boolean notificationReady = hasNotificationAccess();
        boolean authReady = AppPrefs.isAuthVerifiedToday(this);
        boolean vpnReady = AppPrefs.isStaticConfirmed(this)
                && AppPrefs.isIpRecentlyVerified(this)
                && NetworkUtil.isVpnActive(this);
        boolean parserReady = AppPrefs.parserTestPassed(this);

        notificationStatus.setText(notificationReady
                ? "● Notification access: granted"
                : "● Notification access: not granted");
        notificationStatus.setTextColor(getColor(notificationReady ? R.color.success : R.color.danger));

        String ucc = AppPrefs.ucc(this);
        authStatus.setText(authReady
                ? "● Groww authentication: verified today" + (ucc.isEmpty() ? "" : " • UCC " + ucc)
                : "● Groww authentication: not verified today");
        authStatus.setTextColor(getColor(authReady ? R.color.success : R.color.danger));

        ipStatus.setText(vpnReady
                ? "● VPN / static IP: verified"
                : "● VPN / static IP: not verified");
        ipStatus.setTextColor(getColor(vpnReady ? R.color.success : R.color.danger));

        String issue = readinessIssue();
        boolean ready = issue == null;
        systemStatus.setText(ready ? getString(R.string.status_ready) : getString(R.string.status_not_ready));
        systemStatus.setTextColor(getColor(ready ? R.color.success : R.color.warning));
        statusDetail.setText(ready
                ? "All gates passed. Turn on Live automatic buying when you are ready."
                : issue + (parserReady ? "" : " Run the local parser test."));

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
        if (!AppPrefs.parserTestPassed(this)) return "Local parser test has not passed.";
        boolean hasToken = SecureStore.has(this, SecureStore.ACCESS_TOKEN);
        boolean hasTotp = SecureStore.has(this, SecureStore.API_KEY)
                && SecureStore.has(this, SecureStore.TOTP_SECRET);
        if (!hasToken && !hasTotp) return "Save Groww authentication credentials.";
        if (!AppPrefs.isAuthVerifiedToday(this)) return "Verify the Groww account for today.";
        if (!AppPrefs.isStaticConfirmed(this)) return "Confirm the whitelisted static VPN IP.";
        if (AppPrefs.expectedIp(this).isEmpty()) return "Enter the whitelisted static public IP.";
        if (!NetworkUtil.isVpnActive(this)) return "Connect Turbo VPN using the dedicated static IP.";
        if (!AppPrefs.isIpRecentlyVerified(this)) return "Verify the current VPN public IP.";
        return null;
    }

    private boolean hasNotificationAccess() {
        NotificationManager manager = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        if (manager == null) return false;
        return manager.isNotificationListenerAccessGranted(
                new ComponentName(this, MultyfiNotificationService.class));
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
        return message == null || message.trim().isEmpty() ? e.getClass().getSimpleName() : message;
    }

    private void toast(String message) {
        Toast.makeText(this, message, Toast.LENGTH_LONG).show();
    }
}
