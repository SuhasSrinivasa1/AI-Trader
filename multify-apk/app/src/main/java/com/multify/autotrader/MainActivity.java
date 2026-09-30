package com.multify.autotrader;

import android.Manifest;
import android.app.Activity;
import android.app.NotificationManager;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.os.Build;
import android.os.Bundle;
import android.provider.Settings;
import android.text.InputType;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONObject;

public class MainActivity extends Activity {
    private SharedPreferences prefs;
    private EditText backend, key, packageFilter;
    private TextView status, log, lastDecision;
    private Button arm;
    private TradeDb db;

    @Override protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        prefs = getSharedPreferences(MultifyNotificationListener.PREFS, MODE_PRIVATE);
        db = new TradeDb(this);
        requestNotificationPermission();
        buildUi();
        refresh();
    }

    private void buildUi() {
        ScrollView scroll = new ScrollView(this);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(36, 32, 36, 48);
        root.setBackgroundColor(Color.rgb(245,245,245));
        scroll.addView(root);

        TextView title = text("Multify NSE Intraday AutoTrader", 25, true);
        root.addView(title);
        TextView sub = text("NSE CASH only • notification capture • paper/live backend • net-position risk control", 14, false);
        sub.setPadding(0,8,0,22);
        root.addView(sub);

        status = text("", 16, true);
        root.addView(status);

        root.addView(label("Backend URL"));
        backend = field(prefs.getString("backendUrl", "http://10.0.2.2:8000"));
        root.addView(backend);

        root.addView(label("Device shared key"));
        key = field(prefs.getString("deviceKey", "change-me"));
        key.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        root.addView(key);

        root.addView(label("Optional Multify package substring (leave blank to parse by text)"));
        packageFilter = field(prefs.getString("allowedPackage", ""));
        root.addView(packageFilter);

        Button save = button("Save settings");
        save.setOnClickListener(v -> {
            saveNow();
            toast("Saved");
            refresh();
        });
        root.addView(save);

        Button access = button("Open Notification Access settings");
        access.setOnClickListener(v -> startActivity(new Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS)));
        root.addView(access);

        arm = button("");
        arm.setOnClickListener(v -> {
            boolean next = !prefs.getBoolean("armed", false);
            prefs.edit().putBoolean("armed", next).apply();
            refresh();
        });
        root.addView(arm);

        Button test = button("Send VIJAYA sample to backend");
        test.setOnClickListener(v -> sendSample());
        root.addView(test);

        Button refreshBtn = button("Refresh captured log");
        refreshBtn.setOnClickListener(v -> refresh());
        root.addView(refreshBtn);

        root.addView(label("Latest backend response"));
        lastDecision = text("", 13, false);
        lastDecision.setPadding(16,12,16,20);
        root.addView(lastDecision);

        root.addView(label("Recent captured events"));
        log = text("", 13, false);
        log.setPadding(16,12,16,20);
        root.addView(log);

        TextView foot = text(
            "Live orders are controlled by the static-IP backend. The phone never stores your Groww access token. " +
            "Keep the backend in paper mode until notification parsing, fills, charges, stops and reconciliation have been verified.",
            12, false);
        foot.setPadding(0, 20, 0, 20);
        root.addView(foot);

        setContentView(scroll);
    }

    private void sendSample() {
        saveNow();
        String b = prefs.getString("backendUrl", "");
        String k = prefs.getString("deviceKey", "");
        String big = "✅ Released: Equity Intraday Trade\n🔶 Stock Name: VIJAYA\n🔶 Target: 1540\n🔶 Entry Range: 1487.2-1489.2\n🔶 Stop Loss: 1470";
        TradeSignal s = SignalParser.parse("Multyfi", "Released: Equity Intraday Trade", big);
        long row = db.insert("sample.multify", "Multyfi", big, s);
        BackendClient.postNotification(
            b, k, "sample.multify", "Multyfi", "Multyfi",
            "Released: Equity Intraday Trade", big, System.currentTimeMillis(),
            (ok, response) -> {
                db.updateResponse(row, response);
                prefs.edit().putString("lastBackendResponse", response).apply();
                toast(ok ? "Backend accepted sample" : "Backend returned an error");
                refresh();
            });
    }

    private void saveNow() {
        prefs.edit()
            .putString("backendUrl", backend.getText().toString().trim())
            .putString("deviceKey", key.getText().toString().trim())
            .putString("allowedPackage", packageFilter.getText().toString().trim())
            .apply();
    }

    private void refresh() {
        boolean enabled = isNotificationAccessEnabled();
        boolean armed = prefs.getBoolean("armed", false);
        status.setText("Notification access: " + (enabled ? "ON" : "OFF") +
                "\nForwarding: " + (armed ? "ARMED" : "DISARMED"));
        arm.setText(armed ? "DISARM forwarding" : "ARM forwarding");
        lastDecision.setText(pretty(prefs.getString("lastBackendResponse", "No backend response yet.")));
        log.setText(db.recent(30));
    }

    private boolean isNotificationAccessEnabled() {
        NotificationManager nm = (NotificationManager)getSystemService(NOTIFICATION_SERVICE);
        return nm.isNotificationListenerAccessGranted(
            new android.content.ComponentName(this, MultifyNotificationListener.class));
    }

    private String pretty(String x) {
        try { return new JSONObject(x).toString(2); }
        catch (Exception e) { return x; }
    }

    private TextView label(String s) {
        TextView t = text(s,13,true);
        t.setPadding(0,18,0,6);
        return t;
    }

    private TextView text(String s, int sp, boolean bold) {
        TextView t = new TextView(this);
        t.setText(s);
        t.setTextSize(sp);
        t.setTextColor(Color.rgb(25,25,25));
        if (bold) t.setTypeface(android.graphics.Typeface.DEFAULT_BOLD);
        return t;
    }

    private EditText field(String s) {
        EditText e = new EditText(this);
        e.setText(s);
        e.setSingleLine(true);
        e.setPadding(18,12,18,12);
        return e;
    }

    private Button button(String s) {
        Button b = new Button(this);
        b.setText(s);
        b.setAllCaps(false);
        return b;
    }

    private void toast(String s) {
        Toast.makeText(this,s,Toast.LENGTH_SHORT).show();
    }

    private void requestNotificationPermission() {
        if (Build.VERSION.SDK_INT >= 33 &&
                checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, 101);
        }
    }
}
