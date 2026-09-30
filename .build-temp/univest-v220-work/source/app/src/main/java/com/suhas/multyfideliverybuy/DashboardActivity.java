package com.suhas.multyfideliverybuy;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.provider.Settings;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
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
    private static final int BG = Color.rgb(18, 15, 23);
    private static final int NAV_BG = Color.rgb(30, 29, 37);
    private static final int CARD = Color.rgb(56, 55, 61);
    private static final int TEXT = Color.rgb(245, 242, 248);
    private static final int MUTED = Color.rgb(205, 199, 211);
    private static final int DIM = Color.rgb(167, 161, 175);
    private static final int PURPLE = Color.rgb(193, 166, 255);
    private static final int PURPLE_DARK = Color.rgb(78, 66, 107);
    private static final int REQUEST_EXPORT = 8231;

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

    @Override protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        getWindow().setStatusBarColor(BG);
        getWindow().setNavigationBarColor(NAV_BG);
        ResearchScheduler.ensureScheduled(getApplicationContext());
        new Thread(() -> ResearchDiagnosticsImporter.importOfficialSignals(getApplicationContext()), "research-import-ui").start();
        setContentView(buildShell());
        render();
    }

    @Override protected void onResume() {
        super.onResume();
        resumed = true;
        handler.removeCallbacks(refresher);
        refresher.run();
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
        bottomNav.setBackgroundColor(NAV_BG);
        shell.addView(bottomNav, new LinearLayout.LayoutParams(-1, dp(88)));
        return shell;
    }

    private void render() {
        if (contentHost == null) return;
        contentHost.removeAllViews();
        if (selectedTab == 0) contentHost.addView(buildUnivestTab());
        else if (selectedTab == 1) contentHost.addView(buildStrategyTab());
        else contentHost.addView(buildForecastTab());
        renderBottomNav();
    }

    private View buildUnivestTab() {
        ScrollView scroll = baseScroll();
        LinearLayout root = scrollRoot(scroll);
        root.addView(header("UNIVEST TRADER\nAI"));
        root.addView(systemHealthCard(), margins(0, 16, 0, 14));

        Button export = button("⇩   EXPORT COMPLETE LOG", PURPLE, Color.rgb(52, 38, 82), 16, true);
        export.setOnClickListener(v -> createExport());
        root.addView(export, fixedMargins(-1, 60, 0, 0, 0, 16));

        root.addView(text("UNIVEST EXECUTION", 15, TEXT, true), margins(0, 2, 0, 4));
        root.addView(text("Official Univest signals • NSE CASH • CNC delivery", 12, DIM, false), margins(0, 0, 0, 12));
        root.addView(liveControlCard(), margins(0, 0, 0, 14));

        LinearLayout campaigns = card();
        campaigns.addView(sectionRow("BROKER-RECONCILED STATUS", "Today"));
        campaigns.addView(text(activeCampaignSummary(), 13, TEXT, false), margins(0, 12, 0, 0));
        root.addView(campaigns, margins(0, 0, 0, 14));

        LinearLayout signals = card();
        signals.addView(sectionRow("TODAY'S UNIVEST SIGNALS", String.valueOf(DiagnosticsStore.todayNotificationCount(this))));
        signals.addView(text(DiagnosticsStore.todayTradingSignals(this, 6), 13, TEXT, false), margins(0, 12, 0, 0));
        root.addView(signals, margins(0, 0, 0, 14));

        LinearLayout journal = card();
        journal.addView(sectionRow("TRADE JOURNAL", "LIVE / PAPER"));
        journal.addView(text(DiagnosticsStore.todayTrades(this, 5), 13, TEXT, false), margins(0, 12, 0, 0));
        root.addView(journal, margins(0, 0, 0, 18));
        return scroll;
    }

    private View buildStrategyTab() {
        ScrollView scroll = baseScroll();
        LinearLayout root = scrollRoot(scroll);
        root.addView(header("STRATEGY DNA"));

        LinearLayout status = card();
        status.addView(sectionRow("RESEARCH STATUS", lastResearchTime()));
        status.addView(text(AppPrefs.getResearchStatus(this), 13, TEXT, false), margins(0, 12, 0, 0));
        status.addView(text("Off-market only • scheduled around 17:30 IST on trading days", 12, DIM, false), margins(0, 8, 0, 0));
        root.addView(status, margins(0, 16, 0, 14));

        Button scan = button("↻   RUN OFF-MARKET SCAN", PURPLE, Color.rgb(52, 38, 82), 15, true);
        scan.setOnClickListener(v -> runResearchNow(scan));
        root.addView(scan, fixedMargins(-1, 58, 0, 0, 0, 16));

        LinearLayout champions = card();
        champions.addView(sectionRow("STRATEGY CHAMPIONS", "5 families"));
        champions.addView(text(ResearchEngine.strategiesText(this), 13, TEXT, false), margins(0, 12, 0, 0));
        root.addView(champions, margins(0, 0, 0, 14));

        LinearLayout archive = card();
        archive.addView(sectionRow("RECOMMENDATION ARCHIVE", "1–3 month"));
        archive.addView(text(ResearchStore.recentRecommendationsText(this, 8), 13, TEXT, false), margins(0, 12, 0, 0));
        root.addView(archive, margins(0, 0, 0, 14));

        LinearLayout dna = card();
        dna.addView(sectionRow("BUY → SELL DNA", "Pattern learning"));
        dna.addView(text("The lab compares recommendation-time trend, candle structure, ATR, volume, momentum and later exit behaviour. Until enough completed official campaigns exist, sell ranges remain provisional.", 13, TEXT, false), margins(0, 12, 0, 0));
        root.addView(dna, margins(0, 0, 0, 14));

        LinearLayout news = card();
        news.addView(sectionRow("NATIONAL + GLOBAL INTELLIGENCE", "News"));
        news.addView(text(ResearchEngine.intelligenceText(this), 13, TEXT, false), margins(0, 12, 0, 0));
        root.addView(news, margins(0, 0, 0, 18));
        return scroll;
    }

    private View buildForecastTab() {
        ScrollView scroll = baseScroll();
        LinearLayout root = scrollRoot(scroll);
        root.addView(header("NEXT EXPECTED\nRECOMMENDATIONS"));

        LinearLayout summary = card();
        summary.addView(sectionRow("FORECAST ENGINE", lastResearchTime()));
        summary.addView(text("Ranks NSE candidates by similarity to historically observed Univest 1–3 month recommendation fingerprints.", 13, TEXT, false), margins(0, 12, 0, 0));
        summary.addView(text("Prediction output is research-only and never substitutes for an official com.univest.capp signal in the broker execution engine.", 12, DIM, false), margins(0, 8, 0, 0));
        root.addView(summary, margins(0, 16, 0, 14));

        LinearLayout expected = card();
        expected.addView(sectionRow("TOP EXPECTED", "Up to 10"));
        expected.addView(text(ResearchEngine.predictionsText(this, 10), 13, TEXT, false), margins(0, 12, 0, 0));
        root.addView(expected, margins(0, 0, 0, 14));

        LinearLayout range = card();
        range.addView(sectionRow("RANGE PATTERN", "Buy / Sell"));
        range.addView(text("Each candidate displays a buy-pattern zone, chase ceiling and sell-pattern zone normalized by volatility. Strategy-specific ranges will replace provisional ATR ranges as completed Univest campaigns accumulate.", 13, TEXT, false), margins(0, 12, 0, 0));
        root.addView(range, margins(0, 0, 0, 14));

        Button scan = button("↻   REFRESH FORECAST OFF-MARKET", PURPLE, Color.rgb(52, 38, 82), 15, true);
        scan.setOnClickListener(v -> runResearchNow(scan));
        root.addView(scan, fixedMargins(-1, 58, 0, 0, 0, 18));
        return scroll;
    }

    private View header(String title) {
        LinearLayout header = new LinearLayout(this);
        header.setOrientation(LinearLayout.HORIZONTAL);
        header.setGravity(Gravity.TOP);

        LinearLayout left = new LinearLayout(this);
        left.setOrientation(LinearLayout.VERTICAL);
        left.addView(text(title, 27, TEXT, true));
        left.addView(text("v2.3.1", 12, DIM, true), margins(0, 3, 0, 0));
        header.addView(left, new LinearLayout.LayoutParams(0, -2, 1f));

        TextView refresh = iconButton("↻");
        refresh.setOnClickListener(v -> manualRefresh());
        header.addView(refresh, new LinearLayout.LayoutParams(dp(52), dp(52)));

        TextView settings = iconButton("⚙");
        settings.setOnClickListener(v -> startActivity(new Intent(this, MainActivity.class)));
        header.addView(settings, new LinearLayout.LayoutParams(dp(52), dp(52)));
        return header;
    }

    private View systemHealthCard() {
        LinearLayout card = card();
        card.addView(sectionRow("SYSTEM HEALTH", "Last scan " + currentClock()));
        boolean ready = AppPrefs.isReadyForBuy(this);
        boolean listener = notificationAccessEnabled();
        boolean research = AppPrefs.getResearchLastNightlyRun(this) > 0L;
        card.addView(text("Groww " + mark(ready) + "   Univest " + mark(listener) + "   Research " + mark(research), 13, MUTED, false), margins(0, 12, 0, 0));
        card.addView(text("Data quality ✓ • official notifications today " + DiagnosticsStore.todayNotificationCount(this) + " • active campaigns " + activeCampaignCount(), 12, MUTED, false), margins(0, 12, 0, 0));
        card.addView(text("Static-IP route: " + (AppPrefs.isStaticIpMatch(this) ? "acknowledged ✓" : "not acknowledged"), 12, MUTED, false), margins(0, 12, 0, 0));
        card.addView(text("LIVE: " + (AppPrefs.isLiveMode(this) && AppPrefs.isUnivestEnabled(this) ? "ON" : "OFF") + " • AVERAGING " + (AppPrefs.isAveragingEnabled(this) ? "ON" : "OFF") + " • SOURCE LOCKED", 12, MUTED, false), margins(0, 12, 0, 0));
        return card;
    }

    private View liveControlCard() {
        LinearLayout card = card();
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setGravity(Gravity.CENTER_VERTICAL);

        LinearLayout labels = new LinearLayout(this);
        labels.setOrientation(LinearLayout.VERTICAL);
        labels.addView(text("UNIVEST LIVE", 18, TEXT, true));
        boolean live = AppPrefs.isLiveMode(this);
        boolean armed = AppPrefs.isUnivestEnabled(this);
        labels.addView(text(live && armed ? "ON • real CNC orders" : "OFF • monitoring / paper-safe", 12, MUTED, false), margins(0, 5, 0, 0));
        row.addView(labels, new LinearLayout.LayoutParams(0, -2, 1f));

        Switch sw = new Switch(this);
        sw.setChecked(live && armed);
        sw.setScaleX(1.15f);
        sw.setScaleY(1.15f);
        sw.setOnCheckedChangeListener((button, checked) -> {
            if (checked) requestLiveEnable();
            else {
                AppPrefs.setUnivestEnabled(this, false);
                AppPrefs.setUnivestStatus(this, "UNIVEST AUTOTRADE DISARMED from simplified dashboard.");
                DiagnosticsStore.runtime(this, "DISARMED", "", "Dashboard LIVE toggle switched OFF.");
                render();
            }
        });
        row.addView(sw, new LinearLayout.LayoutParams(dp(78), dp(56)));
        card.addView(row);

        card.addView(text("Mode " + AppPrefs.getExecutionMode(this) + " • Groww " + (AppPrefs.isReadyForBuy(this) ? "READY ✓" : "NOT READY") + " • Static IP " + (AppPrefs.isStaticIpMatch(this) ? "MATCH ✓" : "not confirmed"), 12, MUTED, false), margins(0, 10, 0, 0));
        card.addView(text("₹20,000 initial • ₹5,000 back-in-range/averaging • -2% / -4% / -6% ladder", 12, MUTED, false), margins(0, 8, 0, 0));
        return card;
    }

    private void requestLiveEnable() {
        if (!AppPrefs.isReadyForBuy(this)) {
            Toast.makeText(this, "LIVE blocked. Open Settings and run TEST CONNECTION first.", Toast.LENGTH_LONG).show();
            render();
            return;
        }
        new AlertDialog.Builder(this)
                .setTitle("Enable LIVE Univest orders?")
                .setMessage("This enables real-money NSE CASH / CNC orders for official Univest signals. Research forecasts remain non-executing.")
                .setNegativeButton("Cancel", (d, w) -> render())
                .setPositiveButton("Enable LIVE", (d, w) -> {
                    AppPrefs.setExecutionMode(this, AppPrefs.MODE_LIVE);
                    AppPrefs.setUnivestEnabled(this, true);
                    AppPrefs.setUnivestStatus(this, "UNIVEST AUTOTRADE ARMED • LIVE mode • source + CNC locks active.");
                    DiagnosticsStore.runtime(this, "ARMED", "", "Dashboard LIVE toggle enabled real CNC execution.");
                    render();
                }).show();
    }

    private void manualRefresh() {
        Toast.makeText(this, "Refreshing…", Toast.LENGTH_SHORT).show();
        new Thread(() -> {
            try {
                ResearchDiagnosticsImporter.importOfficialSignals(getApplicationContext());
                if (selectedTab == 0) UnivestManager.reconcileAll(getApplicationContext());
            } catch (Throwable t) {
                DiagnosticsStore.error(getApplicationContext(), "DASHBOARD_REFRESH_FAILED", "", "Dashboard refresh failed.", t);
            }
            runOnUiThread(this::render);
        }, "univest-dashboard-refresh").start();
    }

    private void runResearchNow(Button button) {
        if (!ResearchEngine.isOffMarketNowIst()) {
            Toast.makeText(this, "Research scan is locked during NSE market hours.", Toast.LENGTH_LONG).show();
            return;
        }
        button.setEnabled(false);
        button.setText("RUNNING…");
        new Thread(() -> {
            ResearchEngine.runNightly(getApplicationContext());
            runOnUiThread(this::render);
        }, "research-dashboard-manual").start();
    }

    private void renderBottomNav() {
        bottomNav.removeAllViews();
        bottomNav.addView(navItem("◆", "Univest", 0), navParams());
        bottomNav.addView(navItem("◉", "Strategy", 1), navParams());
        bottomNav.addView(navItem("↗", "Forecast", 2), navParams());
    }

    private View navItem(String icon, String label, int tab) {
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setGravity(Gravity.CENTER);
        box.setPadding(dp(4), dp(2), dp(4), dp(2));
        boolean selected = selectedTab == tab;

        TextView iconView = text(icon, 22, selected ? TEXT : MUTED, true);
        iconView.setGravity(Gravity.CENTER);
        if (selected) {
            GradientDrawable pill = new GradientDrawable();
            pill.setColor(PURPLE_DARK);
            pill.setCornerRadius(dp(24));
            iconView.setBackground(pill);
        }
        box.addView(iconView, new LinearLayout.LayoutParams(dp(88), dp(44)));
        TextView labelView = text(label, 12, selected ? TEXT : MUTED, selected);
        labelView.setGravity(Gravity.CENTER);
        box.addView(labelView);
        box.setOnClickListener(v -> {
            selectedTab = tab;
            render();
        });
        return box;
    }

    private LinearLayout.LayoutParams navParams() { return new LinearLayout.LayoutParams(0, -1, 1f); }

    private String activeCampaignSummary() {
        List<UnivestStateStore.State> states = UnivestStateStore.all(this);
        StringBuilder b = new StringBuilder();
        for (UnivestStateStore.State s : states) {
            if (s == null || s.symbol == null || s.symbol.isEmpty() || UnivestStateStore.EXITED.equals(s.phase)) continue;
            if (b.length() > 0) b.append("\n\n");
            b.append(s.symbol).append(" • ").append(s.phase).append(" • qty ").append(s.quantity);
            if (s.anchorPrice > 0) b.append(String.format(Locale.US, " • anchor ₹%.2f", s.anchorPrice));
        }
        if (b.length() == 0) b.append("No active tracked Univest campaigns. Broker holdings/open orders remain execution truth.");
        return b.toString();
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

    private String mark(boolean ok) { return ok ? "✓" : "—"; }
    private String currentClock() { return new SimpleDateFormat("HH:mm:ss", Locale.US).format(new Date()); }
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
            byte[] b = new byte[8192]; int n;
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
        root.setPadding(dp(22), dp(22), dp(22), dp(22));
        scroll.addView(root, new ScrollView.LayoutParams(-1, -2));
        return root;
    }

    private LinearLayout card() {
        LinearLayout l = new LinearLayout(this);
        l.setOrientation(LinearLayout.VERTICAL);
        l.setPadding(dp(18), dp(18), dp(18), dp(18));
        GradientDrawable g = new GradientDrawable();
        g.setColor(CARD);
        g.setCornerRadius(dp(18));
        l.setBackground(g);
        return l;
    }

    private View sectionRow(String title, String right) {
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setGravity(Gravity.CENTER_VERTICAL);
        TextView t = text(title, 15, TEXT, true);
        row.addView(t, new LinearLayout.LayoutParams(0, -2, 1f));
        TextView r = text(right, 11, MUTED, false);
        r.setGravity(Gravity.END);
        row.addView(r, new LinearLayout.LayoutParams(-2, -2));
        return row;
    }

    private TextView iconButton(String symbol) {
        TextView v = text(symbol, 28, MUTED, true);
        v.setGravity(Gravity.CENTER);
        v.setClickable(true);
        return v;
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

    private Button button(String label, int bg, int fg, int sp, boolean bold) {
        Button b = new Button(this);
        b.setText(label);
        b.setAllCaps(false);
        b.setTextSize(sp);
        b.setTextColor(fg);
        if (bold) b.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        GradientDrawable g = new GradientDrawable();
        g.setColor(bg);
        g.setCornerRadius(dp(30));
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

    private int dp(int v) { return Math.round(v * getResources().getDisplayMetrics().density); }
}
