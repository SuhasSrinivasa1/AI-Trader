package com.multify.autotrader;

import android.content.ContentValues;
import android.content.Context;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;
import android.database.sqlite.SQLiteOpenHelper;

public class TradeDb extends SQLiteOpenHelper {
    private static final String NAME = "multify_autotrader.db";

    public TradeDb(Context context) {
        super(context, NAME, null, 1);
    }

    @Override public void onCreate(SQLiteDatabase db) {
        db.execSQL("CREATE TABLE events(id INTEGER PRIMARY KEY AUTOINCREMENT, received_at INTEGER NOT NULL, source_package TEXT, title TEXT, body TEXT, type TEXT, symbol TEXT, summary TEXT, backend_response TEXT)");
    }

    @Override public void onUpgrade(SQLiteDatabase db, int oldVersion, int newVersion) { }

    public long insert(String pkg, String title, String body, TradeSignal signal) {
        ContentValues v = new ContentValues();
        v.put("received_at", System.currentTimeMillis());
        v.put("source_package", pkg);
        v.put("title", title);
        v.put("body", body);
        v.put("type", signal.type.name());
        v.put("symbol", signal.symbol);
        v.put("summary", signal.summary());
        return getWritableDatabase().insert("events", null, v);
    }

    public void updateResponse(long id, String response) {
        ContentValues v = new ContentValues();
        v.put("backend_response", response);
        getWritableDatabase().update("events", v, "id=?", new String[]{String.valueOf(id)});
    }

    public String recent(int limit) {
        StringBuilder out = new StringBuilder();
        try (Cursor c = getReadableDatabase().rawQuery(
                "SELECT received_at,type,symbol,summary,backend_response FROM events ORDER BY id DESC LIMIT ?",
                new String[]{String.valueOf(limit)})) {
            while (c.moveToNext()) {
                out.append(new java.text.SimpleDateFormat("HH:mm:ss", java.util.Locale.getDefault()).format(new java.util.Date(c.getLong(0))))
                        .append("  ").append(c.getString(1));
                String sym = c.getString(2);
                if (sym != null) out.append("  ").append(sym);
                out.append("\n").append(c.getString(3)).append("\n");
                String r = c.getString(4);
                if (r != null && !r.isEmpty()) out.append("↳ ").append(r.length() > 260 ? r.substring(0,260)+"…" : r).append("\n");
                out.append("\n");
            }
        }
        return out.length() == 0 ? "No Multify-style notifications captured yet." : out.toString();
    }
}
