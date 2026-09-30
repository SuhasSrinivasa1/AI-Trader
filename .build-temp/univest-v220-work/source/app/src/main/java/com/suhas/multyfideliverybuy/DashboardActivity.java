package com.suhas.multyfideliverybuy;

import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.provider.Settings;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.Switch;
import android.widget.TextView;
import android.widget.Toast;

import java.io.File;
import java.io.FileInputStream;
import java.io.OutputStream;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.List;
import java.util.Locale;

public class DashboardActivity extends Activity {
    private static final int BG = Color.rgb(7, 13, 24);
    private static final int SURFACE = Color.rgb(14, 25, 40);
    private static final int SURFACE_2 = Color.rgb(18, 32, 50);
    private static final int BORDER = Color.rgb(35, 57, 78);
    private static final int TEXT = Color.rgb(244, 249, 252);
    private static final int SUBTEXT = Color.rgb(166, 190, 207);
    private static final int TEAL = Color.rgb(22, 199, 183);
    private static final int BLUE = Color.rgb(76, 141, 255);
    private static final int GREEN = Color.rgb(61, 220, 151);
    private static final int AMBER = Color.rgb(255, 180, 84);
    private static final int RED = Color.rgb(255, 105, 120);
    private static final int REQUEST_EXPORT = 8232;

    private FrameLayout contentHost;
    private LinearLayout bottomNav;
    private int selectedTab = 0;
    private File pendingExport;
    private final Handler handler = new Handler(Looper.getMainLooper());
    private boolean resumed;

    private final Runnable refresher = new Runnable() {
        @Override public void run() {
            if (!resumed) return;
            render();
            handler.postDelayed(this, 5000L);
        }
    };

    @Override protected void onCreate(Bundle b) {
        super.onCreate(b);
        getWindow().setStatusBarColor(BG);
        getWindow().setNavigationBarColor(BG);
        ResearchScheduler.ensureScheduled(getApplicationContext());
        requestNotificationPermissionIfNeeded();
        new Thread(() -> {
            ResearchDiagnosticsImporter.importOfficialSignals(getApplicationContext());
            try { UnivestManager.migrateLegacyRules(getApplicationContext()); } catch (Throwable ignored) {}
        }, "dashboard-init").start();
        setContentView(buildShell());
        render();
    }

    @Override protected void onResume() {
        super.onResume();
        resumed = true;
        handler.removeCallbacks(refresher);
        refresher.run();
        if (selectedTab == 0) reconcileBroker();
    }

    @Override protected void onPause() {
        resumed = false;
        handler.removeCallbacks(refresher);
        super.onPause();
    }

    private View buildShell() {
        LinearLayout shell = new LinearLayout(this);
        shell.setOrientation(LinearLayout.VERTICAL);
        shell.setBackgroundColor(BG);

        contentHost = new FrameLayout(this);
        shell.addView(contentHost, new LinearLayout.LayoutParams(-1, 0, 1f));

        bottomNav = new LinearLayout(this);
        bottomNav.setOrientation(LinearLayout.HORIZONTAL);
        bottomNav.setGravity(Gravity.CENTER);
        bottomNav.setPadding(dp(8), dp(8), dp(8), dp(8));
        bottomNav.setBackgroundColor(Color.rgb(9, 17, 29));
        shell.addView(bottomNav, new LinearLayout.LayoutParams(-1, dp(82)));
        return shell;
    }

    private void render() {
        if (contentHost == null) return;
        contentHost.removeAllViews();
        if (selectedTab == 0) contentHost.addView(buildUnivestTab());
        else if (selectedTab == 1) contentHost.addView(buildStrategyTab());
        else if (selectedTab == 2) contentHost.addView(buildForecastTab());
        else contentHost.addView(buildSettingsTab());
        renderBottomNav();
    }

    private View buildUnivestTab() {
        ScrollView scroll = baseScroll();
        LinearLayout root = scrollRoot(scroll);
        root.addView(header("UNIVEST", "Broker-truth execution"));

        root.addView(healthCard(), margins(0, 18, 0, 14));
        root.addView(executionCard(), margins(0, 0, 0, 14));

        LinearLayout campaigns = card();
        campaigns.addView(sectionRow("BROKER STATUS", "Today"));
        campaigns.addView(text(activeCampaignSummary(), 13, TEXT, false), margins(0, 12, 0, 0));
        root.addView(campaigns, margins(0, 0, 0, 14));

        LinearLayout signals = card();
        signals.addView(sectionRow("TODAY'S SIGNALS", String.valueOf(DiagnosticsStore.todayNotificationCount(this))));
        signals.addView(text(DiagnosticsStore.todayTradingSignals(this, 6), 13, TEXT, false), margins(0, 12, 0, 0));
        root.addView(signals, margins(0, 0, 0, 14));

        LinearLayout trades = card();
        trades.addView(sectionRow("TRADE JOURNAL", AppPrefs.getExecutionMode(this)));
        trades.addView(text(DiagnosticsStore.todayTrades(this, 6), 13, TEXT, false), margins(0, 12, 0, 0));
        root.addView(trades, margins(0, 0, 0, 20));
        return scroll;
    }

    private View buildStrategyTab() {
        ScrollView scroll = baseScroll();
        LinearLayout root = scrollRoot(scroll);
        root.addView(header("STRATEGY", "Univest recommendation DNA"));

        LinearLayout status = card();
        status.addView(sectionRow("RESEARCH STATUS", lastResearchTime()));
        status.addView(text(AppPrefs.getResearchStatus(this), 13, TEXT, false), margins(0, 12, 0, 0));
        status.addView(text("Runs only outside NSE market hours • scheduled around 17:30 IST", 12, SUBTEXT, false), margins(0, 8, 0, 0));
        root.addView(status, margins(0, 18, 0, 14));

        Button scan = primaryButton("RUN OFF-MARKET SCAN");
        scan.setOnClickListener(v -> runResearchNow(scan));
        root.addView(scan, fixedMargins(-1, 54, 0, 0, 0, 14));

        LinearLayout champions = card();
        champions.addView(sectionRow("STRATEGY CHAMPIONS", "5 families"));
        champions.addView(text(ResearchEngine.strategiesText(this), 13, TEXT, false), margins(0, 12, 0, 0));
        root.addView(champions, margins(0, 0, 0, 14));

        LinearLayout archive = card();
        archive.addView(sectionRow("RECOMMENDATION ARCHIVE", "1–3 month"));
        archive.addView(text(ResearchStore.recentRecommendationsText(this, 10), 13, TEXT, false), margins(0, 12, 0, 0));
        root.addView(archive, margins(0, 0, 0, 14));

        LinearLayout dna = card();
        dna.addView(sectionRow("BUY → SELL DNA", "Pattern learning"));
        dna.addView(text("Compares candle structure, trend, ATR, volume, momentum and later official exit behaviour. Provisional volatility-normalized ranges are replaced as completed campaigns accumulate.", 13, TEXT, false), margins(0, 12, 0, 0));
        root.addView(dna, margins(0, 0, 0, 14));

        LinearLayout intel = card();
        intel.addView(sectionRow("MARKET INTELLIGENCE", "India + Global"));
        intel.addView(text(ResearchEngine.intelligenceText(this), 13, TEXT, false), margins(0, 12, 0, 0));
        root.addView(intel, margins(0, 0, 0, 20));
        return scroll;
    }

    private View buildForecastTab() {
        ScrollView scroll = baseScroll();
        LinearLayout root = scrollRoot(scroll);
        root.addView(header("FORECAST", "Next expected Univest-like picks"));

        LinearLayout intro = card();
        intro.addView(sectionRow("FORECAST ENGINE", lastResearchTime()));
        intro.addView(text("Ranks NSE candidates by similarity to historically observed Univest 1–3 month recommendations.", 13, TEXT, false), margins(0, 12, 0, 0));
        intro.addView(text("Forecasts are research-only. Only an official com.univest.capp signal can enter the broker execution lane.", 12, SUBTEXT, false), margins(0, 8, 0, 0));
        root.addView(intro, margins(0, 18, 0, 14));

        LinearLayout expected = card();
        expected.addView(sectionRow("NEXT EXPECTED", "Top 10"));
        expected.addView(text(ResearchEngine.predictionsText(this, 10), 13, TEXT, false), margins(0, 12, 0, 0));
        root.addView(expected, margins(0, 0, 0, 14));

        LinearLayout ranges = card();
        ranges.addView(sectionRow("ENTRY / EXIT RANGE", "Model"));
        ranges.addView(text("Each candidate includes a buy-pattern zone, chase ceiling and sell-pattern zone normalized by volatility. Learned strategy-specific ranges take over as evidence improves.", 13, TEXT, false), margins(0, 12, 0, 0));
        root.addView(ranges, margins(0, 0, 0, 14));

        Button scan = primaryButton("REFRESH FORECAST OFF-MARKET");
        scan.setOnClickListener(v -> runResearchNow(scan));
        root.addView(scan, fixedMargins(-1, 54, 0, 0, 0, 20));
        return scroll;
    }

    private View buildSettingsTab() {
        ScrollView scroll = baseScroll();
        LinearLayout root = scrollRoot(scroll);
        root.addView(header("SETTINGS", "Connection, safety and diagnostics"));

        LinearLayout connection = card();
        connection.addView(sectionRow("GROWW CONNECTION", AppPrefs.isReadyForBuy(this) ? "READY" : "NOT READY"));

        EditText token = input("Groww TOTP token", true);
        token.setText(AppPrefs.getApiKey(this));
        connection.addView(token, margins(0, 12, 0, 0));

        EditText secret = input("TOTP Base32 secret", true);
        secret.setText(AppPrefs.getTotpSecret(this));
        connection.addView(secret, margins(0, 10, 0, 0));

        EditText ip = input("Whitelisted static public IP", false);
        ip.setText(AppPrefs.getExpectedStaticIp(this));
        connection.addView(ip, margins(0, 10, 0, 0));

        Button save = secondaryButton("SAVE CONNECTION SETTINGS");
        save.setOnClickListener(v -> saveSettings(token, secret, ip));
        connection.addView(save, fixedMargins(-1, 50, 0, 12, 0, 0));

        Button test = primaryButton("TEST CONNECTION & AUTH");
        test.setOnClickListener(v -> testConnection(test));
        connection.addView(test, fixedMargins(-1, 52, 0, 10, 0, 0));
        root.addView(connection, margins(0, 18, 0, 14));

        LinearLayout safety = card();
        safety.addView(sectionRow("EXECUTION SAFETY", AppPrefs.getExecutionMode(this)));

        Switch live = styledSwitch("LIVE MODE — REAL CNC ORDERS", AppPrefs.isLiveMode(this));
        live.setOnCheckedChangeListener((b, checked) -> {
            AppPrefs.setExecutionMode(this, checked ? AppPrefs.MODE_LIVE : AppPrefs.MODE_PAPER);
            AppPrefs.setUnivestEnabled(this, false);
            AppPrefs.setUnivestStatus(this, "Execution mode changed to " + (checked ? "LIVE" : "PAPER") + "; automation DISARMED.");
            DiagnosticsStore.runtime(this, "EXECUTION_MODE_CHANGED", "", AppPrefs.getUnivestStatus(this));
            render();
        });
        safety.addView(live, margins(0, 10, 0, 0));

        Switch avg = styledSwitch("CONTROLLED DOWNWARD AVERAGING", AppPrefs.isAveragingEnabled(this));
        avg.setOnCheckedChangeListener((b, checked) -> {
            AppPrefs.setAveragingEnabled(this, checked);
            AppPrefs.setUnivestEnabled(this, false);
            DiagnosticsStore.runtime(this, "AVERAGING_SETTING_CHANGED", "", "Averaging " + (checked ? "enabled" : "disabled") + "; automation disarmed.");
            render();
        });
        safety.addView(avg, margins(0, 4, 0, 0));

        Switch arm = styledSwitch("ARM UNIVEST AUTOTRADE", AppPrefs.isUnivestEnabled(this));
        arm.setOnCheckedChangeListener((b, checked) -> onArmRequested(checked));
        safety.addView(arm, margins(0, 4, 0, 0));

        safety.addView(text("Official source only • NSE CASH • CNC delivery • ₹20,000 initial • ₹5,000 re-entry/averaging", 12, SUBTEXT, false), margins(0, 10, 0, 0));
        root.addView(safety, margins(0, 0, 0, 14));

        LinearLayout permissions = card();
        permissions.addView(sectionRow("NOTIFICATION ACCESS", notificationAccessEnabled() ? "ENABLED" : "REQUIRED"));
        permissions.addView(text(notificationAccessEnabled() ? "Official Univest notifications can be received." : "Enable notification-listener access before arming.", 13, notificationAccessEnabled() ? GREEN : AMBER, false), margins(0, 10, 0, 0));
        Button access = secondaryButton("OPEN NOTIFICATION ACCESS");
        access.setOnClickListener(v -> startActivity(new Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS)));
        permissions.addView(access, fixedMargins(-1, 50, 0, 12, 0, 0));
        root.addView(permissions, margins(0, 0, 0, 14));

        LinearLayout data = card();
        data.addView(sectionRow("DATA & DIAGNOSTICS", "Maintenance"));
        Button instruments = secondaryButton("REFRESH NSE INSTRUMENT MAP");
        instruments.setOnClickListener(v -> refreshInstruments(instruments));
        data.addView(instruments, fixedMargins(-1, 50, 0, 10, 0, 0));

        Button export = secondaryButton("EXPORT COMPLETE DEBUG ZIP");
        export.setOnClickListener(v -> createExport());
        data.addView(export, fixedMargins(-1, 50, 0, 10, 0, 0));

        data.addView(text("Today's errors", 12, SUBTEXT, true), margins(0, 14, 0, 6));
        data.addView(text(DiagnosticsStore.todayErrors(this, 5), 12, TEXT, false));
        root.addView(data, margins(0, 0, 0, 20));

        return scroll;
    }

    private View header(String title, String subtitle) {
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setGravity(Gravity.CENTER_VERTICAL);

        LinearLayout left = new LinearLayout(this);
        left.setOrientation(LinearLayout.VERTICAL);
        left.addView(text(title, 29, TEXT, true));
        left.addView(text(subtitle, 12, SUBTEXT, false), margins(0, 2, 0, 0));
        row.addView(left, new LinearLayout.LayoutParams(0, -2, 1f));

        TextView refresh = iconButton("↻");
        refresh.setOnClickListener(v -> manualRefresh());
        row.addView(refresh, new LinearLayout.LayoutParams(dp(48), dp(48)));

        TextView gear = iconButton("⚙");
        gear.setOnClickListener(v -> {
            selectedTab = 3;
            render();
        });
        row.addView(gear, new LinearLayout.LayoutParams(dp(48), dp(48)));
        return row;
    }

    private View healthCard() {
        LinearLayout c = card();
        c.addView(sectionRow("SYSTEM HEALTH", currentClock()));

        LinearLayout badges = new LinearLayout(this);
        badges.setOrientation(LinearLayout.HORIZONTAL);
        badges.addView(badge("Groww", AppPrefs.isReadyForBuy(this)));
        badges.addView(badge("Univest", notificationAccessEnabled()), badgeLp());
        badges.addView(badge("Research", AppPrefs.getResearchLastNightlyRun(this) > 0L), badgeLp());
        c.addView(badges, margins(0, 12, 0, 0));

        c.addView(text("Static IP " + (AppPrefs.isStaticIpMatch(this) ? "matched" : "not confirmed") + " • " + activeCampaignCount() + " active campaigns • " + DiagnosticsStore.todayNotificationCount(this) + " notifications today", 12, SUBTEXT, false), margins(0, 12, 0, 0));

        String mode = AppPrefs.isLiveMode(this) && AppPrefs.isUnivestEnabled(this) ? "LIVE ORDERS ENABLED" : "SAFE / DISARMED";
        c.addView(statusPill(mode, AppPrefs.isLiveMode(this) && AppPrefs.isUnivestEnabled(this) ? GREEN : BLUE), margins(0, 12, 0, 0));
        return c;
    }

    private View executionCard() {
        LinearLayout c = card();
        c.addView(sectionRow("UNIVEST EXECUTION", AppPrefs.getExecutionMode(this)));

        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setGravity(Gravity.CENTER_VERTICAL);
        LinearLayout labels = new LinearLayout(this);
        labels.setOrientation(LinearLayout.VERTICAL);
        labels.addView(text(AppPrefs.isUnivestEnabled(this) ? "ARMED" : "DISARMED", 20, TEXT, true));
        labels.addView(text(AppPrefs.isLiveMode(this) ? "Real CNC order mode" : "Paper / monitor mode", 12, SUBTEXT, false), margins(0, 4, 0, 0));
        row.addView(labels, new LinearLayout.LayoutParams(0, -2, 1f));

        Switch arm = new Switch(this);
        arm.setChecked(AppPrefs.isUnivestEnabled(this));
        arm.setScaleX(1.15f);
        arm.setScaleY(1.15f);
        arm.setOnCheckedChangeListener((b, checked) -> onArmRequested(checked));
        row.addView(arm, new LinearLayout.LayoutParams(dp(82), dp(56)));
        c.addView(row, margins(0, 10, 0, 0));

        c.addView(text("₹20,000 initial • ₹5,000 back-in-range • ₹5,000 averaging at -2% / -4% / -6%", 12, SUBTEXT, false), margins(0, 10, 0, 0));
        c.addView(text("Official book-profit/exit cancels tracked averaging orders and sells actual broker CNC holding.", 12, SUBTEXT, false), margins(0, 8, 0, 0));
        return c;
    }

    private void onArmRequested(boolean checked) {
        if (checked && AppPrefs.isLiveMode(this) && !AppPrefs.isReadyForBuy(this)) {
            AppPrefs.setUnivestEnabled(this, false);
            DiagnosticsStore.error(this, "LIVE_ARM_READINESS_BLOCK", "", "LIVE ARM blocked. Test Groww connection and static IP first.", null);
            Toast.makeText(this, "LIVE blocked: test Groww connection and static IP first.", Toast.LENGTH_LONG).show();
            render();
            return;
        }
        if (checked && AppPrefs.isLiveMode(this)) {
            new AlertDialog.Builder(this)
                    .setTitle("Arm LIVE Univest AutoTrade?")
                    .setMessage("This permits real-money NSE CASH / CNC orders from official Univest notifications. Research forecasts remain non-executing.")
                    .setNegativeButton("Cancel", (d,w) -> render())
                    .setPositiveButton("Arm LIVE", (d,w) -> {
                        AppPrefs.setUnivestEnabled(this, true);
                        AppPrefs.setUnivestStatus(this, "UNIVEST AUTOTRADE ARMED • LIVE mode • source + CNC locks active.");
                        DiagnosticsStore.runtime(this, "ARMED", "", AppPrefs.getUnivestStatus(this));
                        render();
                    }).show();
            return;
        }
        AppPrefs.setUnivestEnabled(this, checked);
        AppPrefs.setUnivestStatus(this, checked ? "UNIVEST AUTOTRADE ARMED • PAPER mode." : "UNIVEST AUTOTRADE DISARMED.");
        DiagnosticsStore.runtime(this, checked ? "ARMED" : "DISARMED", "", AppPrefs.getUnivestStatus(this));
        render();
    }

    private void saveSettings(EditText token, EditText secret, EditText ip) {
        AppPrefs.setApiKey(this, token.getText().toString());
        AppPrefs.setTotpSecret(this, secret.getText().toString());
        AppPrefs.setExpectedStaticIp(this, ip.getText().toString());
        AppPrefs.invalidateConnectionReadiness(this);
        AppPrefs.setUnivestEnabled(this, false);
        DiagnosticsStore.runtime(this, "CONNECTION_SETTINGS_CHANGED", "", "Connection settings changed; readiness invalidated and automation disarmed.");
        Toast.makeText(this, "Saved. Run connection test before LIVE arming.", Toast.LENGTH_LONG).show();
        render();
    }

    private void testConnection(Button button) {
        long cooldown = AppPrefs.getAuthCooldownUntil(this);
        if (cooldown > System.currentTimeMillis()) {
            long secs = Math.max(1L, (cooldown - System.currentTimeMillis() + 999L) / 1000L);
            Toast.makeText(this, "Groww auth cooldown active. Retry in about " + secs + " seconds.", Toast.LENGTH_LONG).show();
            return;
        }
        button.setEnabled(false);
        button.setText("TESTING…");
        new Thread(() -> {
            NetworkCheck.Result ip = NetworkCheck.detectAndCompare(getApplicationContext());
            GrowwClient.Result auth = ip.match
                    ? GrowwClient.refreshAndTestAuthentication(getApplicationContext())
                    : new GrowwClient.Result(false, false, 0, "Authentication not tested because static IP does not match.");
            DiagnosticsStore.broker(getApplicationContext(), "STATIC_IP_TEST", "", ip.match, ip.message);
            DiagnosticsStore.broker(getApplicationContext(), "GROWW_AUTH_TEST", "", auth.success, auth.message);
            runOnUiThread(() -> {
                Toast.makeText(this, ip.message + "\n" + auth.message, Toast.LENGTH_LONG).show();
                render();
            });
        }, "dashboard-connection-test").start();
    }

    private void refreshInstruments(Button button) {
        button.setEnabled(false);
        button.setText("REFRESHING…");
        new Thread(() -> {
            boolean changed = InstrumentRepository.refreshIfStale(getApplicationContext());
            List<InstrumentRepository.Instrument> list = InstrumentRepository.load(getApplicationContext());
            DiagnosticsStore.runtime(getApplicationContext(), "INSTRUMENT_MAP_REFRESH", "", "NSE CASH instruments available: " + list.size() + (changed ? " • fresh download" : " • cache/asset"));
            runOnUiThread(() -> {
                Toast.makeText(this, "Instrument map ready: " + list.size() + " NSE CASH symbols.", Toast.LENGTH_LONG).show();
                render();
            });
        }, "dashboard-instrument-refresh").start();
    }

    private void reconcileBroker() {
        new Thread(() -> {
            try { UnivestManager.reconcileAll(getApplicationContext()); }
            catch (Throwable t) { DiagnosticsStore.error(getApplicationContext(), "DASHBOARD_RECONCILE_FAILED", "", "Broker reconciliation failed.", t); }
            runOnUiThread(this::render);
        }, "dashboard-reconcile").start();
    }

    private void manualRefresh() {
        Toast.makeText(this, "Refreshing…", Toast.LENGTH_SHORT).show();
        new Thread(() -> {
            ResearchDiagnosticsImporter.importOfficialSignals(getApplicationContext());
            if (selectedTab == 0) {
                try { UnivestManager.reconcileAll(getApplicationContext()); } catch (Throwable ignored) {}
            }
            runOnUiThread(this::render);
        }, "dashboard-refresh").start();
    }

    private void runResearchNow(Button button) {
        if (!ResearchEngine.isOffMarketNowIst()) {
            Toast.makeText(this, "Research is locked during NSE market hours.", Toast.LENGTH_LONG).show();
            return;
        }
        button.setEnabled(false);
        button.setText("RUNNING…");
        new Thread(() -> {
            ResearchEngine.runNightly(getApplicationContext());
            runOnUiThread(this::render);
        }, "research-manual").start();
    }

    private void renderBottomNav() {
        bottomNav.removeAllViews();
        bottomNav.addView(navItem("◆", "Univest", 0), navParams());
        bottomNav.addView(navItem("◎", "Strategy", 1), navParams());
        bottomNav.addView(navItem("↗", "Forecast", 2), navParams());
        bottomNav.addView(navItem("⚙", "Settings", 3), navParams());
    }

    private View navItem(String icon, String label, int tab) {
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setGravity(Gravity.CENTER);
        boolean selected = selectedTab == tab;

        TextView iconView = text(icon, 20, selected ? Color.rgb(5, 18, 22) : SUBTEXT, true);
        iconView.setGravity(Gravity.CENTER);
        if (selected) {
            GradientDrawable pill = new GradientDrawable();
            pill.setColor(TEAL);
            pill.setCornerRadius(dp(22));
            iconView.setBackground(pill);
        }
        box.addView(iconView, new LinearLayout.LayoutParams(dp(70), dp(40)));

        TextView labelView = text(label, 11, selected ? TEXT : SUBTEXT, selected);
        labelView.setGravity(Gravity.CENTER);
        box.addView(labelView);

        box.setOnClickListener(v -> {
            selectedTab = tab;
            render();
        });
        return box;
    }

    private LinearLayout.LayoutParams navParams() {
        return new LinearLayout.LayoutParams(0, -1, 1f);
    }

    private View badge(String label, boolean ok) {
        TextView v = text(label + " " + (ok ? "✓" : "—"), 11, ok ? Color.rgb(4, 24, 22) : SUBTEXT, true);
        v.setGravity(Gravity.CENTER);
        v.setPadding(dp(10), dp(7), dp(10), dp(7));
        GradientDrawable g = new GradientDrawable();
        g.setColor(ok ? Color.rgb(92, 226, 192) : SURFACE_2);
        g.setCornerRadius(dp(16));
        g.setStroke(dp(1), ok ? Color.rgb(92, 226, 192) : BORDER);
        v.setBackground(g);
        return v;
    }

    private LinearLayout.LayoutParams badgeLp() {
        LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(-2, -2);
        p.setMargins(dp(8), 0, 0, 0);
        return p;
    }

    private View statusPill(String label, int color) {
        TextView v = text(label, 12, TEXT, true);
        v.setGravity(Gravity.CENTER);
        v.setPadding(dp(12), dp(9), dp(12), dp(9));
        GradientDrawable g = new GradientDrawable();
        g.setColor(color == GREEN ? Color.rgb(19, 75, 62) : Color.rgb(24, 58, 97));
        g.setCornerRadius(dp(14));
        g.setStroke(dp(1), color);
        v.setBackground(g);
        return v;
    }

    private String activeCampaignSummary() {
        List<UnivestStateStore.State> states = UnivestStateStore.all(this);
        StringBuilder b = new StringBuilder();
        for (UnivestStateStore.State s : states) {
            if (s == null || s.symbol == null || s.symbol.isEmpty() || UnivestStateStore.EXITED.equals(s.phase)) continue;
            if (b.length() > 0) b.append("\n\n");
            b.append(s.symbol).append(" • ").append(s.phase).append(" • qty ").append(s.quantity);
            if (s.anchorPrice > 0) b.append(String.format(Locale.US, " • anchor ₹%.2f", s.anchorPrice));
        }
        return b.length() == 0 ? "No active tracked campaigns. Groww holdings and open orders remain execution truth." : b.toString();
    }

    private int activeCampaignCount() {
        int n = 0;
        for (UnivestStateStore.State s : UnivestStateStore.all(this))
            if (s != null && s.symbol != null && !s.symbol.isEmpty() && !UnivestStateStore.EXITED.equals(s.phase)) n++;
        return n;
    }

    private boolean notificationAccessEnabled() {
        String enabled = Settings.Secure.getString(getContentResolver(), "enabled_notification_listeners");
        return enabled != null && enabled.contains(getPackageName());
    }

    private void requestNotificationPermissionIfNeeded() {
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED)
            requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, 4310);
    }

    private String currentClock() {
        return new SimpleDateFormat("HH:mm:ss", Locale.US).format(new Date());
    }

    private String lastResearchTime() {
        long t = AppPrefs.getResearchLastNightlyRun(this);
        return t > 0 ? new SimpleDateFormat("dd MMM • HH:mm", Locale.US).format(new Date(t)) : "Not run";
    }

    private void createExport() {
        Toast.makeText(this, "Preparing diagnostic ZIP…", Toast.LENGTH_SHORT).show();
        new Thread(() -> {
            try {
                pendingExport = DiagnosticsStore.createExport(getApplicationContext());
                runOnUiThread(() -> {
                    Intent i = new Intent(Intent.ACTION_CREATE_DOCUMENT);
                    i.addCategory(Intent.CATEGORY_OPENABLE);
                    i.setType("application/zip");
                    i.putExtra(Intent.EXTRA_TITLE, pendingExport.getName());
                    startActivityForResult(i, REQUEST_EXPORT);
                });
            } catch (Exception e) {
                runOnUiThread(() -> Toast.makeText(this, "Export failed: " + e.getMessage(), Toast.LENGTH_LONG).show());
            }
        }, "dashboard-export").start();
    }

    @Override protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode != REQUEST_EXPORT || resultCode != RESULT_OK || data == null || data.getData() == null || pendingExport == null) return;
        Uri uri = data.getData();
        try (FileInputStream in = new FileInputStream(pendingExport); OutputStream out = getContentResolver().openOutputStream(uri, "w")) {
            if (out == null) throw new IllegalStateException("Cannot open selected export destination.");
            byte[] b = new byte[8192];
            int n;
            while ((n = in.read(b)) > 0) out.write(b, 0, n);
            out.flush();
            Toast.makeText(this, "Diagnostic ZIP exported.", Toast.LENGTH_LONG).show();
        } catch (Exception e) {
            Toast.makeText(this, "Unable to save export: " + e.getMessage(), Toast.LENGTH_LONG).show();
        }
    }

    private ScrollView baseScroll() {
        ScrollView s = new ScrollView(this);
        s.setFillViewport(true);
        s.setBackgroundColor(BG);
        return s;
    }

    private LinearLayout scrollRoot(ScrollView scroll) {
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(18), dp(22), dp(18), dp(22));
        scroll.addView(root, new ScrollView.LayoutParams(-1, -2));
        return root;
    }

    private LinearLayout card() {
        LinearLayout l = new LinearLayout(this);
        l.setOrientation(LinearLayout.VERTICAL);
        l.setPadding(dp(16), dp(16), dp(16), dp(16));
        GradientDrawable g = new GradientDrawable();
        g.setColor(SURFACE);
        g.setCornerRadius(dp(18));
        g.setStroke(dp(1), BORDER);
        l.setBackground(g);
        return l;
    }

    private View sectionRow(String title, String right) {
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setGravity(Gravity.CENTER_VERTICAL);
        row.addView(text(title, 14, TEXT, true), new LinearLayout.LayoutParams(0, -2, 1f));
        TextView r = text(right, 11, SUBTEXT, false);
        r.setGravity(Gravity.END);
        row.addView(r, new LinearLayout.LayoutParams(-2, -2));
        return row;
    }

    private TextView iconButton(String symbol) {
        TextView v = text(symbol, 25, SUBTEXT, true);
        v.setGravity(Gravity.CENTER);
        v.setClickable(true);
        return v;
    }

    private Switch styledSwitch(String label, boolean checked) {
        Switch s = new Switch(this);
        s.setText(label);
        s.setTextSize(14);
        s.setTextColor(TEXT);
        s.setChecked(checked);
        s.setPadding(0, dp(7), 0, dp(7));
        return s;
    }

    private EditText input(String hint, boolean secret) {
        EditText e = new EditText(this);
        e.setHint(hint);
        e.setHintTextColor(Color.rgb(111, 139, 160));
        e.setTextColor(TEXT);
        e.setTextSize(14);
        e.setSingleLine(true);
        e.setPadding(dp(14), dp(12), dp(14), dp(12));
        e.setInputType(secret ? InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD : InputType.TYPE_CLASS_TEXT);
        GradientDrawable g = new GradientDrawable();
        g.setColor(SURFACE_2);
        g.setCornerRadius(dp(12));
        g.setStroke(dp(1), BORDER);
        e.setBackground(g);
        return e;
    }

    private TextView text(String s, int sp, int color, boolean bold) {
        TextView v = new TextView(this);
        v.setText(s);
        v.setTextSize(sp);
        v.setTextColor(color);
        v.setLineSpacing(0, 1.16f);
        if (bold) v.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        return v;
    }

    private Button primaryButton(String label) {
        Button b = new Button(this);
        b.setText(label);
        b.setAllCaps(false);
        b.setTextSize(14);
        b.setTextColor(Color.rgb(4, 22, 24));
        b.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        GradientDrawable g = new GradientDrawable();
        g.setColor(TEAL);
        g.setCornerRadius(dp(14));
        b.setBackground(g);
        return b;
    }

    private Button secondaryButton(String label) {
        Button b = new Button(this);
        b.setText(label);
        b.setAllCaps(false);
        b.setTextSize(13);
        b.setTextColor(TEXT);
        b.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        GradientDrawable g = new GradientDrawable();
        g.setColor(SURFACE_2);
        g.setCornerRadius(dp(14));
        g.setStroke(dp(1), BLUE);
        b.setBackground(g);
        return b;
    }

    private LinearLayout.LayoutParams margins(int l, int t, int r, int b) {
        LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(-1, -2);
        p.setMargins(dp(l), dp(t), dp(r), dp(b));
        return p;
    }

    private LinearLayout.LayoutParams fixedMargins(int width, int height, int l, int t, int r, int b) {
        LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(width < 0 ? -1 : dp(width), dp(height));
        p.setMargins(dp(l), dp(t), dp(r), dp(b));
        return p;
    }

    private int dp(int v) {
        return Math.round(v * getResources().getDisplayMetrics().density);
    }
}
