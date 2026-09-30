package com.multify.autotrader;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.content.Context;
import android.content.SharedPreferences;
import android.os.Bundle;
import android.service.notification.NotificationListenerService;
import android.service.notification.StatusBarNotification;

import org.json.JSONObject;

public class MultifyNotificationListener extends NotificationListenerService {
    public static final String PREFS = "multify_prefs";
    private TradeDb db;

    @Override public void onCreate() {
        super.onCreate();
        db = new TradeDb(this);
        ensureChannel();
    }

    @Override public void onListenerConnected() {
        super.onListenerConnected();
        postStatus("Collector connected", "Listening for Multify equity intraday notifications");
    }

    @Override public void onNotificationPosted(StatusBarNotification sbn) {
        if (sbn == null || sbn.getNotification() == null) return;
        if (getPackageName().equals(sbn.getPackageName())) return;

        SharedPreferences p = getSharedPreferences(PREFS, MODE_PRIVATE);
        String allowed = p.getString("allowedPackage", "").trim().toLowerCase();
        if (!allowed.isEmpty() && !sbn.getPackageName().toLowerCase().contains(allowed)) return;

        Bundle e = sbn.getNotification().extras;
        String title = asString(e.get(Notification.EXTRA_TITLE));
        String text = asString(e.get(Notification.EXTRA_TEXT));
        String big = asString(e.get(Notification.EXTRA_BIG_TEXT));
        if (big.isEmpty()) big = text;

        TradeSignal signal = SignalParser.parse(title, text, big);
        if (signal.type == TradeSignal.Type.UNKNOWN) return;

        long rowId = db.insert(sbn.getPackageName(), title, big, signal);
        if (signal.type == TradeSignal.Type.AUTO_PAUSED) {
            p.edit().putBoolean("armed", false).apply();
            postStatus("AUTO TRADING PAUSED", "Protection/pause event detected; forwarding disarmed until reviewed.");
        }

        if (!p.getBoolean("armed", false)) return;
        String backend = p.getString("backendUrl", "").trim();
        String key = p.getString("deviceKey", "").trim();
        if (backend.isEmpty() || key.isEmpty()) {
            db.updateResponse(rowId, "Not forwarded: backend URL or device key missing");
            postStatus("Captured, not forwarded", signal.summary());
            return;
        }

        BackendClient.postNotification(backend, key, sbn.getPackageName(), appLabel(sbn.getPackageName()),
                title, text, big, sbn.getPostTime(), (ok, response) -> {
                    db.updateResponse(rowId, response);
                    p.edit().putString("lastBackendResponse", response).apply();
                    String action = extractAction(response);
                    postStatus(ok ? "Engine: " + action : "Backend error", signal.summary());
                });
    }

    private String appLabel(String pkg) {
        try { return getPackageManager().getApplicationLabel(getPackageManager().getApplicationInfo(pkg, 0)).toString(); }
        catch (Exception e) { return pkg; }
    }

    private static String asString(Object o) { return o == null ? "" : o.toString(); }

    private String extractAction(String json) {
        try { return new JSONObject(json).optString("action", "response received"); }
        catch (Exception ignored) { return "response received"; }
    }

    private void ensureChannel() {
        NotificationManager nm = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
        NotificationChannel ch = new NotificationChannel("engine", "Trading engine status", NotificationManager.IMPORTANCE_DEFAULT);
        ch.setDescription("Multify capture and engine decisions");
        nm.createNotificationChannel(ch);
    }

    private void postStatus(String title, String body) {
        NotificationManager nm = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
        Notification n = new Notification.Builder(this, "engine")
                .setSmallIcon(android.R.drawable.stat_notify_sync)
                .setContentTitle(title)
                .setContentText(body)
                .setStyle(new Notification.BigTextStyle().bigText(body))
                .setAutoCancel(true)
                .build();
        nm.notify((int)(System.currentTimeMillis() % 100000), n);
    }
}
