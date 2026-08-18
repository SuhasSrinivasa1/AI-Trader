package com.suhas.nseunifiedscanner;

import android.content.Context;
import android.content.SharedPreferences;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.KeyStore;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.atomic.AtomicLong;

import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.Mac;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;

final class GrowwApi {
    static final String API_BASE = "https://api.groww.in/v1";
    static final String INSTRUMENT_URL = "https://growwapi-assets.groww.in/instruments/instrument.csv";
    private static final AtomicLong LAST_LIVE_CALL = new AtomicLong(0L);

    private GrowwApi() { }

    static Result<String> authenticate(String apiKey, String base32Secret) {
        try {
            if (blank(apiKey) || blank(base32Secret)) return Result.fail("API key / TOTP secret missing");
            JSONObject body = new JSONObject();
            body.put("key_type", "totp");
            body.put("totp", Totp.generate(base32Secret));
            HttpResult r = request("POST", API_BASE + "/token/api/access", apiKey.trim(), body, false);
            if (!r.ok) return Result.fail(r.message);
            JSONObject json = new JSONObject(r.body);
            String token = json.optString("token", "");
            JSONObject payload = json.optJSONObject("payload");
            if (token.isEmpty() && payload != null) token = payload.optString("token", "");
            return token.isEmpty() ? Result.fail("Groww returned no access token") : Result.ok(token);
        } catch (Exception e) { return Result.fail("Authentication: " + safe(e)); }
    }

    static Result<String> verifyProfile(String token) {
        try {
            HttpResult r = request("GET", API_BASE + "/user/detail", token, null, false);
            if (!r.ok) return Result.fail(r.message);
            JSONObject p = new JSONObject(r.body).optJSONObject("payload");
            if (p == null) return Result.fail("Profile payload missing");
            if (!p.optBoolean("nse_enabled", true)) return Result.fail("NSE trading is not enabled");
            return Result.ok(p.optString("ucc", "READY"));
        } catch (Exception e) { return Result.fail("Profile: " + safe(e)); }
    }

    static Result<String> downloadInstrumentCsv() {
        try {
            HttpResult r = requestRaw("GET", INSTRUMENT_URL, null, null, false);
            return r.ok ? Result.ok(r.body) : Result.fail(r.message);
        } catch (Exception e) { return Result.fail("Instruments: " + safe(e)); }
    }

    static Result<Map<String, Double>> ltpBatch(String token, List<String> tradingSymbols) {
        try {
            if (tradingSymbols.isEmpty() || tradingSymbols.size() > 50) return Result.fail("LTP batch must be 1..50");
            StringBuilder q = new StringBuilder();
            for (String s : tradingSymbols) {
                if (q.length() > 0) q.append(',');
                q.append("NSE_").append(s);
            }
            paceLive();
            HttpResult r = request("GET", API_BASE + "/live-data/ltp?segment=CASH&exchange_symbols=" + enc(q.toString()), token, null, true);
            if (!r.ok) return Result.fail(r.message);
            JSONObject p = new JSONObject(r.body).optJSONObject("payload");
            if (p == null) return Result.fail("LTP payload missing");
            Map<String, Double> out = new HashMap<>();
            for (String s : tradingSymbols) {
                String key = "NSE_" + s;
                if (p.has(key)) out.put(s, p.optDouble(key, Double.NaN));
            }
            return Result.ok(out);
        } catch (Exception e) { return Result.fail("LTP: " + safe(e)); }
    }

    static Result<Map<String, Ohlc>> ohlcBatch(String token, List<String> tradingSymbols) {
        try {
            if (tradingSymbols.isEmpty() || tradingSymbols.size() > 50) return Result.fail("OHLC batch must be 1..50");
            StringBuilder q = new StringBuilder();
            for (String s : tradingSymbols) {
                if (q.length() > 0) q.append(',');
                q.append("NSE_").append(s);
            }
            paceLive();
            HttpResult r = request("GET", API_BASE + "/live-data/ohlc?segment=CASH&exchange_symbols=" + enc(q.toString()), token, null, true);
            if (!r.ok) return Result.fail(r.message);
            JSONObject p = new JSONObject(r.body).optJSONObject("payload");
            if (p == null) return Result.fail("OHLC payload missing");
            Map<String, Ohlc> out = new HashMap<>();
            for (String s : tradingSymbols) {
                Object raw = p.opt("NSE_" + s);
                Ohlc o = parseOhlc(raw);
                if (o != null) out.put(s, o);
            }
            return Result.ok(out);
        } catch (Exception e) { return Result.fail("OHLC: " + safe(e)); }
    }

    static Result<Quote> quote(String token, String symbol) {
        try {
            paceLive();
            String u = API_BASE + "/live-data/quote?exchange=NSE&segment=CASH&trading_symbol=" + enc(symbol);
            HttpResult r = request("GET", u, token, null, true);
            if (!r.ok) return Result.fail(r.message);
            JSONObject p = new JSONObject(r.body).optJSONObject("payload");
            if (p == null) return Result.fail("Quote payload missing");
            Quote q = new Quote();
            q.symbol = symbol;
            q.ltp = p.optDouble("last_price", Double.NaN);
            q.dayChangePct = p.optDouble("day_change_perc", 0);
            q.volume = p.optLong("volume", 0);
            q.marketCap = p.optDouble("market_cap", 0);
            q.bid = p.optDouble("bid_price", 0);
            q.ask = p.optDouble("offer_price", 0);
            q.totalBuy = p.optDouble("total_buy_quantity", 0);
            q.totalSell = p.optDouble("total_sell_quantity", 0);
            q.week52High = p.optDouble("week_52_high", 0);
            q.week52Low = p.optDouble("week_52_low", 0);
            q.upperCircuit = p.optDouble("upper_circuit_limit", 0);
            q.lowerCircuit = p.optDouble("lower_circuit_limit", 0);
            return Result.ok(q);
        } catch (Exception e) { return Result.fail("Quote: " + safe(e)); }
    }

    static Result<List<Candle>> candles(String token, String growwSymbol, String start, String end, String interval) {
        try {
            String u = API_BASE + "/historical/candles?exchange=NSE&segment=CASH&groww_symbol=" + enc(growwSymbol)
                    + "&start_time=" + enc(start) + "&end_time=" + enc(end) + "&candle_interval=" + enc(interval);
            HttpResult r = request("GET", u, token, null, false);
            if (!r.ok) return Result.fail(r.message);
            JSONObject p = new JSONObject(r.body).optJSONObject("payload");
            JSONArray a = p == null ? null : p.optJSONArray("candles");
            if (a == null) return Result.fail("Historical candle payload missing");
            List<Candle> out = new ArrayList<>();
            for (int i = 0; i < a.length(); i++) {
                JSONArray c = a.optJSONArray(i);
                if (c == null || c.length() < 6) continue;
                Candle x = new Candle();
                Object ts = c.opt(0);
                x.time = ts == null ? "" : String.valueOf(ts);
                x.open = c.optDouble(1, 0); x.high = c.optDouble(2, 0); x.low = c.optDouble(3, 0);
                x.close = c.optDouble(4, 0); x.volume = c.optDouble(5, 0);
                if (x.close > 0) out.add(x);
            }
            return Result.ok(out);
        } catch (Exception e) { return Result.fail("Candles: " + safe(e)); }
    }

    static Result<Margin> availableMargin(String token) {
        try {
            HttpResult r = request("GET", API_BASE + "/margins/detail/user", token, null, false);
            if (!r.ok) return Result.fail(r.message);
            JSONObject p = new JSONObject(r.body).optJSONObject("payload");
            if (p == null) return Result.fail("Margin payload missing");
            Margin m = new Margin();
            m.clearCash = p.optDouble("clear_cash", 0);
            JSONObject e = p.optJSONObject("equity_margin_details");
            if (e != null) {
                m.misAvailable = e.optDouble("mis_balance_available", m.clearCash);
                m.cncAvailable = e.optDouble("cnc_balance_available", m.clearCash);
            } else { m.misAvailable = m.clearCash; m.cncAvailable = m.clearCash; }
            return Result.ok(m);
        } catch (Exception e) { return Result.fail("Margin: " + safe(e)); }
    }

    static Result<Double> requiredMisMargin(String token, String symbol, int quantity, double price) {
        try {
            JSONArray arr = new JSONArray();
            JSONObject o = new JSONObject();
            o.put("trading_symbol", symbol); o.put("transaction_type", "BUY"); o.put("quantity", quantity);
            o.put("price", price(price)); o.put("order_type", "LIMIT"); o.put("product", "MIS"); o.put("exchange", "NSE");
            arr.put(o);
            HttpResult r = requestArray("POST", API_BASE + "/margins/detail/orders?segment=CASH", token, arr);
            if (!r.ok) return Result.fail(r.message);
            JSONObject p = new JSONObject(r.body).optJSONObject("payload");
            if (p == null) return Result.fail("Required margin payload missing");
            double v = p.optDouble("cash_mis_margin_required", p.optDouble("total_requirement", Double.NaN));
            return Double.isFinite(v) && v >= 0 ? Result.ok(v) : Result.fail("Invalid required margin");
        } catch (Exception e) { return Result.fail("Required margin: " + safe(e)); }
    }


    static Result<Integer> positionQuantity(String token, String symbol) {
        try {
            HttpResult r = request("GET", API_BASE + "/positions/trading-symbol?trading_symbol=" + enc(symbol) + "&segment=CASH", token, null, false);
            if (!r.ok) return Result.fail(r.message);
            JSONObject p = new JSONObject(r.body).optJSONObject("payload");
            if (p == null) return Result.ok(0);
            JSONArray a = p.optJSONArray("positions");
            if (a == null) return Result.ok(p.optInt("quantity", 0));
            int qty = 0;
            for (int i=0;i<a.length();i++) {
                JSONObject x=a.optJSONObject(i); if(x==null)continue;
                if (symbol.equalsIgnoreCase(x.optString("trading_symbol", "")) && "MIS".equalsIgnoreCase(x.optString("product", x.optString("product_type", "MIS")))) qty += x.optInt("quantity",0);
            }
            return Result.ok(qty);
        } catch (Exception e) { return Result.fail("Position: " + safe(e)); }
    }

    static Result<Order> placeLimitBuy(String token, String symbol, int quantity, double price, String reference) {
        return placeOrder(token, symbol, quantity, price, 0, "LIMIT", "BUY", "MIS", reference);
    }

    static Result<Order> placeSlM(String token, String symbol, int quantity, double trigger, String reference) {
        return placeOrder(token, symbol, quantity, 0, trigger, "SL_M", "SELL", "MIS", reference);
    }

    static Result<Order> placeMarketSell(String token, String symbol, int quantity, String reference) {
        return placeOrder(token, symbol, quantity, 0, 0, "MARKET", "SELL", "MIS", reference);
    }

    private static Result<Order> placeOrder(String token, String symbol, int quantity, double price, double trigger,
                                            String orderType, String side, String product, String reference) {
        try {
            JSONObject b = new JSONObject();
            b.put("trading_symbol", symbol); b.put("quantity", quantity); b.put("price", price(price));
            b.put("trigger_price", price(trigger)); b.put("validity", "DAY"); b.put("exchange", "NSE");
            b.put("segment", "CASH"); b.put("product", product); b.put("order_type", orderType);
            b.put("transaction_type", side); b.put("order_reference_id", reference);
            HttpResult r = request("POST", API_BASE + "/order/create", token, b, false);
            if (!r.ok) return Result.fail(r.message);
            JSONObject p = new JSONObject(r.body).optJSONObject("payload");
            if (p == null) return Result.fail("Order payload missing");
            Order o = new Order();
            o.id = p.optString("groww_order_id", ""); o.status = p.optString("order_status", "");
            o.reference = p.optString("order_reference_id", reference); o.remark = p.optString("remark", "");
            return o.id.isEmpty() ? Result.fail("Groww returned no order ID") : Result.ok(o);
        } catch (Exception e) { return Result.fail("Order: " + safe(e)); }
    }

    static Result<Order> orderDetail(String token, String orderId) {
        try {
            HttpResult r = request("GET", API_BASE + "/order/detail/" + enc(orderId) + "?segment=CASH", token, null, false);
            if (!r.ok) return Result.fail(r.message);
            JSONObject p = new JSONObject(r.body).optJSONObject("payload");
            if (p == null) return Result.fail("Order detail payload missing");
            Order o = new Order();
            o.id = p.optString("groww_order_id", orderId); o.status = p.optString("order_status", "");
            o.reference = p.optString("order_reference_id", ""); o.remark = p.optString("remark", "");
            o.filledQuantity = p.optInt("filled_quantity", 0); o.remainingQuantity = p.optInt("remaining_quantity", 0);
            o.averageFillPrice = p.optDouble("average_fill_price", 0);
            return Result.ok(o);
        } catch (Exception e) { return Result.fail("Order detail: " + safe(e)); }
    }

    static Result<Boolean> cancelOrder(String token, String orderId) {
        try {
            JSONObject b = new JSONObject(); b.put("segment", "CASH"); b.put("groww_order_id", orderId);
            HttpResult r = request("POST", API_BASE + "/order/cancel", token, b, false);
            return r.ok ? Result.ok(true) : Result.fail(r.message);
        } catch (Exception e) { return Result.fail("Cancel: " + safe(e)); }
    }

    static Result<SmartOrder> placeCashMisOco(String token, String symbol, int quantity, double target, double stop, String reference) {
        try {
            JSONObject b = new JSONObject();
            b.put("reference_id", reference); b.put("smart_order_type", "OCO"); b.put("segment", "CASH");
            b.put("trading_symbol", symbol); b.put("quantity", quantity); b.put("net_position_quantity", quantity);
            b.put("transaction_type", "SELL"); b.put("product_type", "MIS"); b.put("exchange", "NSE"); b.put("duration", "DAY");
            JSONObject t = new JSONObject(); t.put("trigger_price", price(target)); t.put("order_type", "LIMIT"); t.put("price", price(target));
            JSONObject s = new JSONObject(); s.put("trigger_price", price(stop)); s.put("order_type", "SL_M"); s.put("price", JSONObject.NULL);
            b.put("target", t); b.put("stop_loss", s);
            HttpResult r = request("POST", API_BASE + "/order-advance/create", token, b, false);
            if (!r.ok) return Result.fail(r.message);
            JSONObject p = new JSONObject(r.body).optJSONObject("payload");
            if (p == null) return Result.fail("OCO payload missing");
            SmartOrder o = new SmartOrder(); o.id = p.optString("smart_order_id", ""); o.status = p.optString("status", "");
            return o.id.isEmpty() ? Result.fail("Groww returned no OCO ID") : Result.ok(o);
        } catch (Exception e) { return Result.fail("OCO: " + safe(e)); }
    }

    static Result<SmartOrder> smartStatus(String token, String type, String id) {
        try {
            HttpResult r = request("GET", API_BASE + "/order-advance/status/CASH/" + enc(type) + "/internal/" + enc(id), token, null, false);
            if (!r.ok) return Result.fail(r.message);
            JSONObject p = new JSONObject(r.body).optJSONObject("payload");
            if (p == null) return Result.fail("Smart-order payload missing");
            SmartOrder o = new SmartOrder(); o.id = p.optString("smart_order_id", id); o.status = p.optString("status", "");
            return Result.ok(o);
        } catch (Exception e) { return Result.fail("Smart status: " + safe(e)); }
    }

    static Result<Boolean> cancelSmart(String token, String type, String id) {
        try {
            HttpResult r = request("POST", API_BASE + "/order-advance/cancel/CASH/" + enc(type) + "/" + enc(id), token, null, false);
            return r.ok ? Result.ok(true) : Result.fail(r.message);
        } catch (Exception e) { return Result.fail("Cancel smart: " + safe(e)); }
    }

    static String reference(String prefix, String symbol) {
        long n = Math.abs((symbol + System.nanoTime()).hashCode());
        String p = (prefix + symbol.replaceAll("[^A-Za-z0-9]", "")).toUpperCase(Locale.ROOT);
        if (p.length() > 8) p = p.substring(0, 8);
        String r = p + String.format(Locale.US, "%010d", n % 10_000_000_000L);
        if (r.length() < 8) r += "12345678";
        return r.substring(0, Math.min(20, r.length()));
    }

    static double roundToTick(double v, double tick, boolean up) {
        if (!(v > 0) || !(tick > 0)) return v;
        double q = v / tick;
        return (up ? Math.ceil(q - 1e-9) : Math.floor(q + 1e-9)) * tick;
    }

    private static String price(double v) { return String.format(Locale.US, "%.2f", Math.max(0, v)); }
    private static String enc(String s) throws Exception { return URLEncoder.encode(s, StandardCharsets.UTF_8.name()); }
    private static boolean blank(String s) { return s == null || s.trim().isEmpty(); }
    private static String safe(Exception e) { return e.getMessage() == null ? e.getClass().getSimpleName() : e.getMessage(); }

    private static void paceLive() {
        synchronized (LAST_LIVE_CALL) {
            long now = System.currentTimeMillis(); long wait = 120L - (now - LAST_LIVE_CALL.get());
            if (wait > 0) try { Thread.sleep(wait); } catch (InterruptedException e) { Thread.currentThread().interrupt(); }
            LAST_LIVE_CALL.set(System.currentTimeMillis());
        }
    }

    private static Ohlc parseOhlc(Object raw) {
        try {
            JSONObject o;
            if (raw instanceof JSONObject) o = (JSONObject) raw;
            else {
                String s = String.valueOf(raw).trim();
                if (s.startsWith("{") && !s.contains("\"")) {
                    s = s.replaceAll("([A-Za-z_]+)\\s*:", "\"$1\":");
                }
                o = new JSONObject(s);
            }
            Ohlc x = new Ohlc(); x.open = o.optDouble("open", 0); x.high = o.optDouble("high", 0);
            x.low = o.optDouble("low", 0); x.close = o.optDouble("close", 0); return x;
        } catch (Exception ignore) { return null; }
    }

    private static HttpResult request(String method, String url, String token, JSONObject body, boolean live) {
        return requestRaw(method, url, token, body == null ? null : body.toString(), live);
    }
    private static HttpResult requestArray(String method, String url, String token, JSONArray body) {
        return requestRaw(method, url, token, body == null ? null : body.toString(), false);
    }
    private static HttpResult requestRaw(String method, String url, String token, String body, boolean live) {
        HttpURLConnection c = null;
        try {
            c = (HttpURLConnection) new URL(url).openConnection(); c.setConnectTimeout(7000); c.setReadTimeout(12000);
            c.setRequestMethod(method); c.setRequestProperty("Accept", "application/json"); c.setRequestProperty("X-API-VERSION", "1.0");
            c.setRequestProperty("User-Agent", "NSEUnifiedScanner/1.0 Android");
            if (!blank(token)) c.setRequestProperty("Authorization", "Bearer " + token.trim());
            if (body != null) {
                c.setDoOutput(true); c.setRequestProperty("Content-Type", "application/json");
                try (OutputStream os = c.getOutputStream()) { os.write(body.getBytes(StandardCharsets.UTF_8)); }
            }
            int code = c.getResponseCode(); InputStream in = code >= 200 && code < 300 ? c.getInputStream() : c.getErrorStream();
            String text = readAll(in); boolean ok = code >= 200 && code < 300;
            if (ok && text != null && text.trim().startsWith("{")) {
                JSONObject j = new JSONObject(text); if ("FAILURE".equalsIgnoreCase(j.optString("status"))) ok = false;
            }
            return new HttpResult(ok, code, text, ok ? "OK" : errorMessage(code, text));
        } catch (Exception e) { return new HttpResult(false, 0, "", safe(e)); }
        finally { if (c != null) c.disconnect(); }
    }
    private static String errorMessage(int code, String text) {
        try {
            JSONObject j = new JSONObject(text == null ? "{}" : text); JSONObject e = j.optJSONObject("error");
            if (e != null) return "Groww " + code + ": " + e.optString("code", "") + " " + e.optString("message", "");
        } catch (Exception ignore) { }
        return "HTTP " + code + (blank(text) ? "" : ": " + text.substring(0, Math.min(180, text.length())));
    }
    private static String readAll(InputStream in) throws Exception {
        if (in == null) return ""; try (BufferedReader br = new BufferedReader(new InputStreamReader(in, StandardCharsets.UTF_8))) {
            StringBuilder sb = new StringBuilder(); String line; while ((line = br.readLine()) != null) sb.append(line).append('\n'); return sb.toString();
        }
    }

    static final class Result<T> {
        final boolean ok; final T value; final String error;
        private Result(boolean ok, T value, String error) { this.ok = ok; this.value = value; this.error = error; }
        static <T> Result<T> ok(T v) { return new Result<>(true, v, ""); }
        static <T> Result<T> fail(String e) { return new Result<>(false, null, e == null ? "Unknown error" : e); }
    }
    static final class Ohlc { double open, high, low, close; }
    static final class Candle { String time; double open, high, low, close, volume; }
    static final class Quote { String symbol; double ltp, dayChangePct, marketCap, bid, ask, totalBuy, totalSell, week52High, week52Low, upperCircuit, lowerCircuit; long volume; }
    static final class Margin { double clearCash, misAvailable, cncAvailable; }
    static final class Order { String id, status, reference, remark; int filledQuantity, remainingQuantity; double averageFillPrice; }
    static final class SmartOrder { String id, status; }
    private static final class HttpResult {
        final boolean ok; final int code; final String body; final String message;
        HttpResult(boolean ok,int code,String body,String message){this.ok=ok;this.code=code;this.body=body;this.message=message;}
    }
}

final class SecureStore {
    static final String API_KEY="api_key", TOTP_SECRET="totp_secret", ACCESS_TOKEN="access_token", ACCESS_DAY="access_day", DEDICATED_IP="dedicated_ip";
    private static final String ALIAS="nse_unified_scanner_key", PREFS="nse_secure";
    private SecureStore() { }
    static void put(Context c, String key, String value) throws Exception {
        if (value == null || value.trim().isEmpty()) { remove(c,key); return; }
        Cipher cp=Cipher.getInstance("AES/GCM/NoPadding"); cp.init(Cipher.ENCRYPT_MODE,key()); byte[] iv=cp.getIV(); byte[] enc=cp.doFinal(value.getBytes(StandardCharsets.UTF_8));
        ByteBuffer b=ByteBuffer.allocate(4+iv.length+enc.length); b.putInt(iv.length).put(iv).put(enc);
        prefs(c).edit().putString(key, Base64.encodeToString(b.array(),Base64.NO_WRAP)).apply();
    }
    static String get(Context c, String key) {
        try { String s=prefs(c).getString(key,""); if(s==null||s.isEmpty())return ""; ByteBuffer b=ByteBuffer.wrap(Base64.decode(s,Base64.NO_WRAP)); int n=b.getInt();
            if(n<12||n>16||b.remaining()<=n)return ""; byte[] iv=new byte[n]; b.get(iv); byte[] enc=new byte[b.remaining()]; b.get(enc);
            Cipher cp=Cipher.getInstance("AES/GCM/NoPadding"); cp.init(Cipher.DECRYPT_MODE,key(),new GCMParameterSpec(128,iv)); return new String(cp.doFinal(enc),StandardCharsets.UTF_8);
        } catch(Exception e){ return ""; }
    }
    static void remove(Context c,String key){prefs(c).edit().remove(key).apply();}
    private static SharedPreferences prefs(Context c){return c.getSharedPreferences(PREFS,Context.MODE_PRIVATE);}
    private static SecretKey key() throws Exception { KeyStore ks=KeyStore.getInstance("AndroidKeyStore"); ks.load(null); KeyStore.Entry e=ks.getEntry(ALIAS,null); if(e instanceof KeyStore.SecretKeyEntry)return ((KeyStore.SecretKeyEntry)e).getSecretKey();
        KeyGenerator g=KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES,"AndroidKeyStore"); g.init(new KeyGenParameterSpec.Builder(ALIAS,KeyProperties.PURPOSE_ENCRYPT|KeyProperties.PURPOSE_DECRYPT).setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).setRandomizedEncryptionRequired(true).build()); return g.generateKey(); }
}

final class Totp {
    private Totp() { }
    static String generate(String base32) throws Exception {
        byte[] key=decode(base32); long counter=System.currentTimeMillis()/1000L/30L; ByteBuffer b=ByteBuffer.allocate(8).putLong(counter);
        Mac m=Mac.getInstance("HmacSHA1"); m.init(new SecretKeySpec(key,"HmacSHA1")); byte[] h=m.doFinal(b.array()); int off=h[h.length-1]&0xf;
        int bin=((h[off]&0x7f)<<24)|((h[off+1]&0xff)<<16)|((h[off+2]&0xff)<<8)|(h[off+3]&0xff); return String.format(Locale.US,"%06d",bin%1_000_000);
    }
    private static byte[] decode(String s) throws Exception { String a=s.replace("=","").replaceAll("\\s+","").toUpperCase(Locale.ROOT); String alpha="ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"; ByteArrayOutputStream out=new ByteArrayOutputStream(); int buffer=0,bits=0;
        for(char ch:a.toCharArray()){int v=alpha.indexOf(ch); if(v<0)throw new Exception("Invalid Base32 secret"); buffer=(buffer<<5)|v; bits+=5; if(bits>=8){bits-=8; out.write((buffer>>bits)&0xff);}} return out.toByteArray(); }
}
