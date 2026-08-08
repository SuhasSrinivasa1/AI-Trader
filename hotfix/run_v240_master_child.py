#!/usr/bin/env python3
from pathlib import Path
import runpy, shutil, re

runpy.run_path('hotfix/run_v235.py', run_name='__main__')

ROOT = Path('android-stable')
APP = ROOT / 'app'
JAVA = APP / 'src/main/java/com/suhas/multyfiautobuy/stable'
TEST = APP / 'src/test/java/com/suhas/multyfiautobuy/stable'


def read(p):
    return Path(p).read_text(encoding='utf-8')

def write(p, s):
    p = Path(p); p.parent.mkdir(parents=True, exist_ok=True); p.write_text(s, encoding='utf-8')

def rep(p, old, new, count=1):
    p = Path(p); text = read(p); n = text.count(old)
    if n != count:
        raise RuntimeError(f'Expected {count} matches in {p}, found {n}: {old[:180]}')
    write(p, text.replace(old, new, count))

def insert_before(p, anchor, block):
    rep(p, anchor, block + anchor)

# -----------------------------------------------------------------------------
# Release identity — master remains an in-place update of com.suhas...stable.
# -----------------------------------------------------------------------------
gradle = APP / 'build.gradle'
rep(gradle, 'versionCode 235', 'versionCode 240')
rep(gradle, "versionName '2.3.5'", "versionName '2.4.0'")

# -----------------------------------------------------------------------------
# Current Groww NSE equity-intraday charge model (official pricing page rates).
# Used to target NET +₹5,000 and NET daily floor -₹2,000.
# -----------------------------------------------------------------------------
write(JAVA / 'IntradayChargeCalculator.java', r'''package com.suhas.multyfiautobuy.stable;

final class IntradayChargeCalculator {
    private static final double BROKERAGE_RATE = 0.001d;
    private static final double BROKERAGE_CAP = 20d;
    private static final double BROKERAGE_MIN = 5d;
    private static final double BROKERAGE_REG_CAP = 0.025d;
    private static final double STT_SELL = 0.00025d;
    private static final double STAMP_BUY = 0.00003d;
    private static final double NSE_EXCHANGE = 0.0000297d;
    private static final double SEBI = 0.000001d;
    private static final double NSE_IPFT = 0.000001d;
    private static final double GST = 0.18d;

    private IntradayChargeCalculator() { }

    static double brokerage(double orderValue) {
        double value = Math.max(0d, orderValue);
        double raw = Math.min(BROKERAGE_CAP, value * BROKERAGE_RATE);
        if (raw >= BROKERAGE_MIN) return raw;
        return Math.min(BROKERAGE_MIN, value * BROKERAGE_REG_CAP);
    }

    static double estimatedRoundTripCharges(double buyValue, double sellValue) {
        double buy = Math.max(0d, buyValue);
        double sell = Math.max(0d, sellValue);
        double turnover = buy + sell;
        double brokerage = brokerage(buy) + brokerage(sell);
        double stt = sell * STT_SELL;
        double stamp = buy * STAMP_BUY;
        double exchange = turnover * NSE_EXCHANGE;
        double sebi = turnover * SEBI;
        double ipft = turnover * NSE_IPFT;
        double gst = GST * (brokerage + exchange + sebi + ipft);
        return brokerage + stt + stamp + exchange + sebi + ipft + gst;
    }

    static double estimatedNetPnl(double entryPrice, double sellPrice, int quantity) {
        if (entryPrice <= 0d || sellPrice <= 0d || quantity <= 0) return 0d;
        double buyValue = entryPrice * quantity;
        double sellValue = sellPrice * quantity;
        return (sellValue - buyValue)
                - estimatedRoundTripCharges(buyValue, sellValue);
    }
}
''')

write(JAVA / 'DailyRiskPolicy.java', r'''package com.suhas.multyfiautobuy.stable;

final class DailyRiskPolicy {
    static final double NET_PROFIT_TARGET = 5000d;
    static final double NET_LOSS_FLOOR = -2000d;
    static final long WATCH_INTERVAL_MS = 250L;
    private static final double TICK = 0.10d;

    private DailyRiskPolicy() { }

    static boolean profitComplete(double dailyNet) {
        return dailyNet + 1e-9d >= NET_PROFIT_TARGET;
    }

    static boolean lossComplete(double dailyNet) {
        return dailyNet <= NET_LOSS_FLOOR + 1e-9d;
    }

    static double remainingNetProfit(double dailyNetBeforeTrade) {
        return Math.max(0d, NET_PROFIT_TARGET - dailyNetBeforeTrade);
    }

    static double remainingLossRoom(double dailyNetBeforeTrade) {
        return Math.max(0d, dailyNetBeforeTrade - NET_LOSS_FLOOR);
    }

    static double netProfitExitPrice(double entryPrice, int quantity,
                                     double dailyNetBeforeTrade) {
        double required = remainingNetProfit(dailyNetBeforeTrade);
        if (entryPrice <= 0d || quantity <= 0) return 0d;
        if (required <= 0d) return ceilTick(entryPrice);
        double lo = entryPrice;
        double hi = entryPrice + Math.max(10d, (required + 2000d) / quantity + 10d);
        while (IntradayChargeCalculator.estimatedNetPnl(entryPrice, hi, quantity)
                < required) hi = hi * 1.01d + 1d;
        for (int i = 0; i < 80; i++) {
            double mid = (lo + hi) / 2d;
            if (IntradayChargeCalculator.estimatedNetPnl(entryPrice, mid, quantity)
                    >= required) hi = mid;
            else lo = mid;
        }
        return ceilTick(hi);
    }

    static double netLossStopPrice(double entryPrice, int quantity,
                                   double dailyNetBeforeTrade) {
        if (entryPrice <= 0d || quantity <= 0) return 0d;
        double room = remainingLossRoom(dailyNetBeforeTrade);
        if (room <= 0d) return ceilTick(entryPrice);
        double requiredTradeNet = -room;
        double lo = Math.max(TICK, entryPrice * 0.01d);
        double hi = entryPrice;
        for (int i = 0; i < 80; i++) {
            double mid = (lo + hi) / 2d;
            double net = IntradayChargeCalculator.estimatedNetPnl(
                    entryPrice, mid, quantity);
            if (net <= requiredTradeNet) lo = mid;
            else hi = mid;
        }
        return ceilTick(hi);
    }

    static double firstProfitExitPrice(double multyfiTarget,
                                       double netDailyTarget) {
        if (multyfiTarget <= 0d) return netDailyTarget;
        if (netDailyTarget <= 0d) return multyfiTarget;
        return Math.min(multyfiTarget, netDailyTarget);
    }

    static boolean profitThresholdHit(double ltp, double threshold) {
        return ltp > 0d && threshold > 0d && ltp + 1e-9d >= threshold;
    }

    static boolean lossThresholdHit(double ltp, double stop) {
        return ltp > 0d && stop > 0d && ltp <= stop + 1e-9d;
    }

    static double ceilTick(double value) {
        return Math.ceil((value - 1e-9d) / TICK) * TICK;
    }
}
''')

write(JAVA / 'ProfitTargetPolicy.java', r'''package com.suhas.multyfiautobuy.stable;

final class ProfitTargetPolicy {
    static final double DAILY_TARGET_RUPEES = DailyRiskPolicy.NET_PROFIT_TARGET;
    static final long POLL_INTERVAL_MS = DailyRiskPolicy.WATCH_INTERVAL_MS;
    private ProfitTargetPolicy() { }

    static double remainingDailyProfit(double dailyNetBeforeTrade) {
        return DailyRiskPolicy.remainingNetProfit(dailyNetBeforeTrade);
    }
    static double dailyTargetPrice(double averageEntryPrice, int quantity,
                                   double remainingProfitIgnored) {
        return DailyRiskPolicy.netProfitExitPrice(averageEntryPrice, quantity, 0d);
    }
    static double effectiveExitPrice(double multyfiTargetPrice,
                                     double dailyTargetPrice) {
        return DailyRiskPolicy.firstProfitExitPrice(multyfiTargetPrice, dailyTargetPrice);
    }
    static double openGrossProfit(double ltp, double averageEntryPrice, int quantity) {
        return (ltp - averageEntryPrice) * Math.max(0, quantity);
    }
    static boolean shouldExit(double ltp, double effectiveExitPrice) {
        return DailyRiskPolicy.profitThresholdHit(ltp, effectiveExitPrice);
    }
    static boolean dailyGoalIsFirst(double multyfiTargetPrice, double dailyTargetPrice) {
        return dailyTargetPrice > 0d && (multyfiTargetPrice <= 0d
                || dailyTargetPrice <= multyfiTargetPrice + 1e-9d);
    }
}
''')

write(JAVA / 'DailyNetPnlLedger.java', r'''package com.suhas.multyfiautobuy.stable;

import android.content.Context;
import android.content.SharedPreferences;
import org.json.JSONArray;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.HashSet;
import java.util.Locale;
import java.util.Set;
import java.util.TimeZone;

final class DailyNetPnlLedger {
    private static final String PREF = "daily_net_pnl_v240";
    private static final String DATE = "date";
    private static final String NET = "net";
    private static final String EVENTS = "events";
    private static final TimeZone IST = TimeZone.getTimeZone("Asia/Kolkata");

    private DailyNetPnlLedger() { }

    private static String today() {
        SimpleDateFormat f = new SimpleDateFormat("yyyy-MM-dd", Locale.US);
        f.setTimeZone(IST);
        return f.format(new Date());
    }

    private static SharedPreferences p(Context c) {
        SharedPreferences p = c.getSharedPreferences(PREF, Context.MODE_PRIVATE);
        String d = today();
        if (!d.equals(p.getString(DATE, ""))) {
            p.edit().clear().putString(DATE, d).putLong(NET,
                    Double.doubleToLongBits(0d)).putString(EVENTS, "[]").apply();
        }
        return p;
    }

    static synchronized double netRealised(Context c) {
        return Double.longBitsToDouble(p(c).getLong(NET,
                Double.doubleToLongBits(0d)));
    }

    static synchronized boolean record(Context c, String eventId, double tradeNet) {
        SharedPreferences p = p(c);
        Set<String> seen = new HashSet<>();
        try {
            JSONArray a = new JSONArray(p.getString(EVENTS, "[]"));
            for (int i = 0; i < a.length(); i++) seen.add(a.optString(i, ""));
        } catch (Exception ignored) { }
        if (seen.contains(eventId)) return false;
        seen.add(eventId);
        JSONArray out = new JSONArray();
        for (String id : seen) out.put(id);
        double next = netRealised(c) + tradeNet;
        p.edit().putLong(NET, Double.doubleToLongBits(next))
                .putString(EVENTS, out.toString()).apply();
        return true;
    }
}
''')

write(JAVA / 'AppRole.java', r'''package com.suhas.multyfiautobuy.stable;

import android.content.Context;

final class AppRole {
    private AppRole() { }
    static boolean isChild(Context c) {
        return c != null && c.getPackageName().endsWith(".child");
    }
    static String label(Context c) { return isChild(c) ? "CHILD" : "MASTER"; }
    static void ensureRelay(Context c) {
        if (isChild(c)) LanChildRelayService.ensureRunning(c);
        else LanMasterRelayService.ensureRunning(c);
    }
}
''')

write(JAVA / 'RelayState.java', r'''package com.suhas.multyfiautobuy.stable;

import android.content.Context;
import android.content.SharedPreferences;

final class RelayState {
    private static final String PREF = "lan_relay_state";
    private RelayState() { }
    private static SharedPreferences p(Context c) {
        return c.getSharedPreferences(PREF, Context.MODE_PRIVATE);
    }
    static void childConnected(Context c, String masterIp, long latencyMs) {
        p(c).edit().putBoolean("connected", true).putString("master_ip", masterIp)
                .putLong("latency", latencyMs).putLong("at", System.currentTimeMillis()).apply();
    }
    static void childDisconnected(Context c) { p(c).edit().putBoolean("connected", false).apply(); }
    static boolean childConnected(Context c) { return p(c).getBoolean("connected", false); }
    static String masterIp(Context c) { return p(c).getString("master_ip", ""); }
    static long latency(Context c) { return p(c).getLong("latency", -1L); }
    static void masterChildren(Context c, int count) { p(c).edit().putInt("children", count).apply(); }
    static int masterChildren(Context c) { return p(c).getInt("children", 0); }
}
''')

write(JAVA / 'LanRelayProtocol.java', r'''package com.suhas.multyfiautobuy.stable;

import org.json.JSONObject;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Base64;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

final class LanRelayProtocol {
    static final int TCP_PORT = 38385;
    static final int UDP_PORT = 38384;
    static final String SECRET = "56dcbe1f608926970b69627b86aaeea3835f582333950c01e6020aeaea018dca";

    static final class Signal {
        final String eventId; final long sourcePostTime; final long masterSentAt;
        final String rawText;
        Signal(String id, long post, long sent, String raw) {
            eventId=id; sourcePostTime=post; masterSentAt=sent; rawText=raw;
        }
    }
    private LanRelayProtocol() { }

    static String discover(String nonce) {
        String core = "DISCOVER|" + nonce;
        return core + "|" + hmac(core);
    }
    static boolean validDiscover(String line) {
        String[] p = line == null ? new String[0] : line.split("\\|", -1);
        return p.length == 3 && "DISCOVER".equals(p[0])
                && constantTime(p[2], hmac(p[0] + "|" + p[1]));
    }
    static String masterReply(String nonce) {
        String core = "MASTER|" + nonce + "|" + TCP_PORT;
        return core + "|" + hmac(core);
    }
    static int validMasterReplyPort(String line, String nonce) {
        try {
            String[] p = line.split("\\|", -1);
            String core = p[0] + "|" + p[1] + "|" + p[2];
            if (p.length != 4 || !"MASTER".equals(p[0]) || !nonce.equals(p[1])
                    || !constantTime(p[3], hmac(core))) return -1;
            return Integer.parseInt(p[2]);
        } catch (Exception e) { return -1; }
    }
    static String hello(String device, String nonce) {
        String core = "HELLO|" + device + "|" + nonce;
        return core + "|" + hmac(core);
    }
    static boolean validHello(String line) {
        String[] p = line == null ? new String[0] : line.split("\\|", -1);
        if (p.length != 4 || !"HELLO".equals(p[0])) return false;
        String core = p[0] + "|" + p[1] + "|" + p[2];
        return constantTime(p[3], hmac(core));
    }
    static String envelope(String raw, long sourcePostTime, long sentAt) throws Exception {
        String b64 = Base64.getEncoder().encodeToString(raw.getBytes(StandardCharsets.UTF_8));
        String id = sha256(sourcePostTime + "|" + raw);
        String core = id + "|" + sourcePostTime + "|" + sentAt + "|" + b64;
        JSONObject o = new JSONObject();
        o.put("v", 1); o.put("id", id); o.put("post", sourcePostTime);
        o.put("sent", sentAt); o.put("raw", b64); o.put("sig", hmac(core));
        return o.toString();
    }
    static Signal parse(String line) throws Exception {
        JSONObject o = new JSONObject(line);
        String id = o.getString("id"); long post = o.getLong("post");
        long sent = o.getLong("sent"); String b64 = o.getString("raw");
        String sig = o.getString("sig");
        String core = id + "|" + post + "|" + sent + "|" + b64;
        if (!constantTime(sig, hmac(core))) throw new SecurityException("bad relay signature");
        String raw = new String(Base64.getDecoder().decode(b64), StandardCharsets.UTF_8);
        if (!id.equals(sha256(post + "|" + raw))) throw new SecurityException("bad relay id");
        return new Signal(id, post, sent, raw);
    }
    static String ack(String id, long receivedAt) {
        String core = "ACK|" + id + "|" + receivedAt;
        return core + "|" + hmac(core);
    }

    private static String hmac(String s) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(SECRET.getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
            return hex(mac.doFinal(s.getBytes(StandardCharsets.UTF_8)));
        } catch (Exception e) { throw new IllegalStateException(e); }
    }
    private static String sha256(String s) {
        try { return hex(MessageDigest.getInstance("SHA-256").digest(s.getBytes(StandardCharsets.UTF_8))); }
        catch (Exception e) { throw new IllegalStateException(e); }
    }
    private static String hex(byte[] b) {
        StringBuilder s = new StringBuilder();
        for (byte x : b) s.append(String.format(java.util.Locale.US, "%02x", x & 0xff));
        return s.toString();
    }
    private static boolean constantTime(String a, String b) {
        if (a == null || b == null) return false;
        return MessageDigest.isEqual(a.getBytes(StandardCharsets.UTF_8), b.getBytes(StandardCharsets.UTF_8));
    }
}
''')

write(JAVA / 'LanMasterRelayService.java', r'''package com.suhas.multyfiautobuy.stable;

import android.app.*;
import android.content.*;
import android.os.IBinder;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.Set;
import java.util.concurrent.*;

public final class LanMasterRelayService extends Service {
    private static final String CH="multyfi_master_lan";
    private static final int ID=2401;
    private static final String ACTION_PUBLISH="lan.master.PUBLISH";
    private static final String EXTRA_RAW="raw", EXTRA_POST="post";
    private final Set<Client> clients=ConcurrentHashMap.newKeySet();
    private ExecutorService io; private volatile boolean running; private ServerSocket server;

    static void ensureRunning(Context c) {
        if (AppRole.isChild(c)) return;
        Intent i=new Intent(c, LanMasterRelayService.class);
        try { c.startForegroundService(i); } catch(Exception e) { AppPrefs.log(c,"MASTER LAN RELAY START FAILED",String.valueOf(e.getMessage())); }
    }
    static void publishAsync(Context c,String raw,long post) {
        if (AppRole.isChild(c) || raw==null || raw.trim().isEmpty()) return;
        Intent i=new Intent(c,LanMasterRelayService.class).setAction(ACTION_PUBLISH)
                .putExtra(EXTRA_RAW,raw).putExtra(EXTRA_POST,post);
        try { c.startForegroundService(i); } catch(Exception e) { AppPrefs.log(c,"MASTER LAN RELAY PUBLISH FAILED",String.valueOf(e.getMessage())); }
    }
    @Override public void onCreate(){ super.onCreate(); createChannel(); startForeground(ID,note("Master LAN relay starting")); io=Executors.newCachedThreadPool(); running=true; io.execute(this::serverLoop); io.execute(this::discoveryLoop); }
    @Override public int onStartCommand(Intent i,int f,int id){ if(i!=null&&ACTION_PUBLISH.equals(i.getAction())){ final String raw=i.getStringExtra(EXTRA_RAW); final long post=i.getLongExtra(EXTRA_POST,System.currentTimeMillis()); io.execute(()->broadcast(raw,post)); } return START_STICKY; }
    @Override public void onDestroy(){ running=false; try{if(server!=null)server.close();}catch(Exception ignored){} for(Client c:clients)c.close(); if(io!=null)io.shutdownNow(); super.onDestroy(); }
    @Override public IBinder onBind(Intent i){return null;}

    private void serverLoop(){
        try{ server=new ServerSocket(); server.setReuseAddress(true); server.bind(new InetSocketAddress(LanRelayProtocol.TCP_PORT));
            while(running){ Socket s=server.accept(); s.setTcpNoDelay(true); s.setKeepAlive(true); io.execute(()->acceptClient(s)); }
        }catch(Exception e){ if(running)AppPrefs.log(this,"MASTER LAN TCP ERROR",String.valueOf(e.getMessage())); }
    }
    private void acceptClient(Socket s){ Client c=null; try{
        s.setSoTimeout(5000); BufferedReader r=new BufferedReader(new InputStreamReader(s.getInputStream(),StandardCharsets.UTF_8)); PrintWriter w=new PrintWriter(new OutputStreamWriter(s.getOutputStream(),StandardCharsets.UTF_8),true);
        String hello=r.readLine(); if(!LanRelayProtocol.validHello(hello)){s.close();return;} s.setSoTimeout(0); c=new Client(s,w); clients.add(c); RelayState.masterChildren(this,clients.size()); update();
        AppPrefs.log(this,"CHILD PHONE CONNECTED",s.getInetAddress().getHostAddress()+" • connected children "+clients.size());
        while(running&&r.readLine()!=null){};
        }catch(Exception ignored){} finally{ if(c!=null){clients.remove(c);c.close();RelayState.masterChildren(this,clients.size());update();} else try{s.close();}catch(Exception ignored){} }
    }
    private void discoveryLoop(){
        try(DatagramSocket d=new DatagramSocket(null)){ d.setReuseAddress(true); d.bind(new InetSocketAddress(LanRelayProtocol.UDP_PORT)); byte[] buf=new byte[512];
            while(running){ DatagramPacket p=new DatagramPacket(buf,buf.length); d.receive(p); String m=new String(p.getData(),p.getOffset(),p.getLength(),StandardCharsets.UTF_8); if(!LanRelayProtocol.validDiscover(m))continue; String[] x=m.split("\\|",-1); byte[] out=LanRelayProtocol.masterReply(x[1]).getBytes(StandardCharsets.UTF_8); d.send(new DatagramPacket(out,out.length,p.getAddress(),p.getPort())); }
        }catch(Exception e){if(running)AppPrefs.log(this,"MASTER LAN DISCOVERY ERROR",String.valueOf(e.getMessage()));}
    }
    private void broadcast(String raw,long post){
        try{ long sent=System.currentTimeMillis(); String line=LanRelayProtocol.envelope(raw,post,sent); int ok=0; for(Client c:clients){ if(c.send(line))ok++; else{clients.remove(c);c.close();} } RelayState.masterChildren(this,clients.size()); update();
            AppPrefs.log(this,"MULTYFI LAN BROADCAST", "Children "+ok+"/"+clients.size()+" • source age "+Math.max(0,sent-post)+" ms • master trading path was scheduled independently first.");
        }catch(Exception e){AppPrefs.log(this,"MASTER LAN BROADCAST ERROR",String.valueOf(e.getMessage()));}
    }
    private void createChannel(){ NotificationManager n=(NotificationManager)getSystemService(NOTIFICATION_SERVICE); if(n!=null)n.createNotificationChannel(new NotificationChannel(CH,"Master LAN relay",NotificationManager.IMPORTANCE_LOW)); }
    private Notification note(String t){ return new Notification.Builder(this,CH).setSmallIcon(android.R.drawable.stat_notify_sync).setContentTitle("Multyfi MASTER relay").setContentText(t).setOngoing(true).build(); }
    private void update(){ NotificationManager n=(NotificationManager)getSystemService(NOTIFICATION_SERVICE); if(n!=null)n.notify(ID,note("Connected child phones: "+clients.size())); }
    static final class Client{ final Socket s; final PrintWriter w; Client(Socket s,PrintWriter w){this.s=s;this.w=w;} synchronized boolean send(String x){try{w.println(x);return !w.checkError();}catch(Exception e){return false;}} void close(){try{s.close();}catch(Exception ignored){}} }
}
''')

write(JAVA / 'LanChildRelayService.java', r'''package com.suhas.multyfiautobuy.stable;

import android.app.*;
import android.content.*;
import android.os.*;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.*;

public final class LanChildRelayService extends ProductionNotificationService {
    private static final String CH="multyfi_child_lan"; private static final int ID=2402;
    private ExecutorService net; private volatile boolean running; private volatile Socket socket;

    static void ensureRunning(Context c){ if(!AppRole.isChild(c))return; try{c.startForegroundService(new Intent(c,LanChildRelayService.class));}catch(Exception e){AppPrefs.log(c,"CHILD LAN RELAY START FAILED",String.valueOf(e.getMessage()));} }
    @Override public void onCreate(){ super.onCreate(); createChannel(); startForeground(ID,note("Discovering master on local Wi-Fi/hotspot")); running=true; net=Executors.newSingleThreadExecutor(); net.execute(this::loop); }
    @Override public int onStartCommand(Intent i,int f,int id){return START_STICKY;}
    @Override public void onDestroy(){running=false;RelayState.childDisconnected(this);try{if(socket!=null)socket.close();}catch(Exception ignored){} if(net!=null)net.shutdownNow();super.onDestroy();}

    private void loop(){ while(running){ try{ Host h=discover(); if(h==null){ RelayState.childDisconnected(this); update("Master not found — retrying"); sleep(750); continue; } connect(h); }catch(Exception e){RelayState.childDisconnected(this);update("Disconnected — retrying");sleep(500);} } }
    private Host discover(){ String nonce=Long.toHexString(System.nanoTime()); byte[] q=LanRelayProtocol.discover(nonce).getBytes(StandardCharsets.UTF_8);
        try(DatagramSocket d=new DatagramSocket()){d.setBroadcast(true);d.setSoTimeout(700); Set<InetAddress> targets=new HashSet<>(); targets.add(InetAddress.getByName("255.255.255.255"));
            try{Enumeration<NetworkInterface> en=NetworkInterface.getNetworkInterfaces();while(en.hasMoreElements()){for(InterfaceAddress a:Collections.list(en.nextElement().getInterfaceAddresses()))if(a.getBroadcast()!=null)targets.add(a.getBroadcast());}}catch(Exception ignored){}
            for(InetAddress a:targets)try{d.send(new DatagramPacket(q,q.length,a,LanRelayProtocol.UDP_PORT));}catch(Exception ignored){}
            long end=System.currentTimeMillis()+700; byte[] buf=new byte[512]; while(System.currentTimeMillis()<end){DatagramPacket p=new DatagramPacket(buf,buf.length);try{d.receive(p);}catch(SocketTimeoutException e){break;}String r=new String(p.getData(),p.getOffset(),p.getLength(),StandardCharsets.UTF_8);int port=LanRelayProtocol.validMasterReplyPort(r,nonce);if(port>0)return new Host(p.getAddress(),port);} }
        catch(Exception ignored){} return null; }
    private void connect(Host h)throws Exception{ Socket s=new Socket(); socket=s;s.connect(new InetSocketAddress(h.a,h.p),1200);s.setTcpNoDelay(true);s.setKeepAlive(true); PrintWriter w=new PrintWriter(new OutputStreamWriter(s.getOutputStream(),StandardCharsets.UTF_8),true);BufferedReader r=new BufferedReader(new InputStreamReader(s.getInputStream(),StandardCharsets.UTF_8));String device=Build.MANUFACTURER+"-"+Build.MODEL;w.println(LanRelayProtocol.hello(device,Long.toHexString(System.nanoTime())));RelayState.childConnected(this,h.a.getHostAddress(),-1);update("Connected to master "+h.a.getHostAddress());AppPrefs.log(this,"CHILD CONNECTED TO MASTER",h.a.getHostAddress()+":"+h.p);
        String line;while(running&&(line=r.readLine())!=null){long recv=System.currentTimeMillis();try{LanRelayProtocol.Signal sig=LanRelayProtocol.parse(line);long latency=Math.max(0,recv-sig.masterSentAt);RelayState.childConnected(this,h.a.getHostAddress(),latency);update("Master connected • last relay "+latency+" ms");w.println(LanRelayProtocol.ack(sig.eventId,recv));AppPrefs.log(this,"MULTYFI SIGNAL RECEIVED FROM MASTER","LAN latency "+latency+" ms • event "+sig.eventId.substring(0,12));enqueueRelayedMultyfi(sig.rawText,sig.sourcePostTime);}catch(Exception e){AppPrefs.log(this,"CHILD RELAY PACKET REJECTED",String.valueOf(e.getMessage()));}}
        try{s.close();}catch(Exception ignored){} }
    private void createChannel(){NotificationManager n=(NotificationManager)getSystemService(NOTIFICATION_SERVICE);if(n!=null)n.createNotificationChannel(new NotificationChannel(CH,"Child LAN relay",NotificationManager.IMPORTANCE_LOW));}
    private Notification note(String t){return new Notification.Builder(this,CH).setSmallIcon(android.R.drawable.stat_notify_sync).setContentTitle("Multyfi CHILD relay").setContentText(t).setOngoing(true).build();}
    private void update(String t){NotificationManager n=(NotificationManager)getSystemService(NOTIFICATION_SERVICE);if(n!=null)n.notify(ID,note(t));}
    private static void sleep(long ms){try{Thread.sleep(ms);}catch(InterruptedException e){Thread.currentThread().interrupt();}}
    static final class Host{final InetAddress a;final int p;Host(InetAddress a,int p){this.a=a;this.p=p;}}
}
''')

app = JAVA / 'AppPrefs.java'
rep(app, '    private static final String K_DAILY_PROFIT_LOCK_DATE = "daily_profit_lock_date";\n',
    '    private static final String K_DAILY_PROFIT_LOCK_DATE = "daily_profit_lock_date";\n'
    '    private static final String K_DAILY_LOSS_LOCK_DATE = "daily_loss_lock_date";\n')
rep(app, r'''    static synchronized boolean isProcessed(Context context, String eventId) {
''', r'''    static boolean isDailyLossLocked(Context context) {
        return istDate().equals(prefs(context).getString(K_DAILY_LOSS_LOCK_DATE, ""));
    }

    static void lockDailyLossLimit(Context context) {
        prefs(context).edit().putString(K_DAILY_LOSS_LOCK_DATE, istDate()).apply();
    }

    static synchronized boolean isProcessed(Context context, String eventId) {
''')

strategy = JAVA / 'Strategy.java'
rep(strategy, '    final double stopLossPrice;\n',
    '    double stopLossPrice;\n    final double multyfiStopLossPrice;\n')
rep(strategy, '        this.stopLossPrice = stopLossPrice;\n',
    '        this.stopLossPrice = stopLossPrice;\n        this.multyfiStopLossPrice = stopLossPrice;\n')
rep(strategy, '    boolean dailyProfitExitTriggered;\n    String pendingExitLabel;\n',
    '    boolean dailyProfitExitTriggered;\n    boolean dailyLossExitTriggered;\n'
    '    double dailyNetBeforeTrade;\n    double dynamicLossStopPrice;\n    String pendingExitLabel;\n')
rep(strategy, '        this.dailyProfitExitTriggered = false;\n        this.pendingExitLabel = "";\n',
    '        this.dailyProfitExitTriggered = false;\n        this.dailyLossExitTriggered = false;\n'
    '        this.dailyNetBeforeTrade = 0d;\n        this.dynamicLossStopPrice = 0d;\n'
    '        this.pendingExitLabel = "";\n')
rep(strategy, '        json.put("stop_loss_price", stopLossPrice);\n',
    '        json.put("stop_loss_price", stopLossPrice);\n        json.put("multyfi_stop_loss_price", multyfiStopLossPrice);\n')
rep(strategy, '        json.put("daily_profit_exit_triggered", dailyProfitExitTriggered);\n',
    '        json.put("daily_profit_exit_triggered", dailyProfitExitTriggered);\n'
    '        json.put("daily_loss_exit_triggered", dailyLossExitTriggered);\n'
    '        json.put("daily_net_before_trade", dailyNetBeforeTrade);\n'
    '        json.put("dynamic_loss_stop_price", dynamicLossStopPrice);\n')
rep(strategy, '        strategy.dailyProfitExitTriggered =\n                json.optBoolean("daily_profit_exit_triggered", false);\n',
    '        strategy.dailyProfitExitTriggered =\n                json.optBoolean("daily_profit_exit_triggered", false);\n'
    '        strategy.dailyLossExitTriggered =\n                json.optBoolean("daily_loss_exit_triggered", false);\n'
    '        strategy.dailyNetBeforeTrade = json.optDouble("daily_net_before_trade", 0d);\n'
    '        strategy.dynamicLossStopPrice = json.optDouble("dynamic_loss_stop_price", 0d);\n')

service = JAVA / 'ProductionNotificationService.java'
rep(service, r'''        if (AppPrefs.MULTYFI_PACKAGE.equals(sourcePackage)) {
            executor.execute(() -> process(rawText, postTime));
        } else if (AppPrefs.RESEARCH360_PACKAGE.equals(sourcePackage)) {
''', r'''        if (AppPrefs.MULTYFI_PACKAGE.equals(sourcePackage)) {
            executor.execute(() -> process(rawText, postTime));
            if (!AppRole.isChild(this)) {
                LanMasterRelayService.publishAsync(this, rawText, postTime);
            }
        } else if (AppPrefs.RESEARCH360_PACKAGE.equals(sourcePackage)) {
''')
insert_before(service, '    private void processResearch360(String rawText, long postTime) {\n', r'''    protected final void enqueueRelayedMultyfi(String rawText, long postTime) {
        executor.execute(() -> process(rawText, postTime));
    }

''')
rep(service, r'''            if (AppPrefs.isDailyProfitLocked(this)) {
                AppPrefs.log(this, "NEW ENTRY BLOCKED — DAILY ₹5,000 TARGET DONE",
                        "The ₹5,000 daily profit target has already been completed. "
                                + "No further automatic entries will be created today.\n"
                                + compact(rawText));
                return;
            }


            double buffer = AppPrefs.entryBufferPercent(this);
''', r'''            if (AppPrefs.isDailyProfitLocked(this)) {
                AppPrefs.log(this, "NEW ENTRY BLOCKED — DAILY NET ₹5,000 TARGET DONE",
                        "The ₹5,000 NET daily profit target has already been completed. "
                                + "No further automatic entries will be created today.\n"
                                + compact(rawText));
                return;
            }
            if (AppPrefs.isDailyLossLocked(this)) {
                AppPrefs.log(this, "NEW ENTRY BLOCKED — DAILY NET LOSS LIMIT HIT",
                        "The daily NET loss floor of -₹2,000 has been reached. "
                                + "Trading is halted for the rest of today.\n"
                                + compact(rawText));
                return;
            }
            double dailyNet = DailyNetPnlLedger.netRealised(this);
            if (DailyRiskPolicy.profitComplete(dailyNet)) {
                AppPrefs.lockDailyProfitTarget(this);
                AppPrefs.log(this, "NEW ENTRY BLOCKED — DAILY NET ₹5,000 TARGET DONE",
                        "Local charge-adjusted realised NET P&L ₹" + money(dailyNet)
                                + " has reached the daily target.");
                return;
            }
            if (DailyRiskPolicy.lossComplete(dailyNet)) {
                AppPrefs.lockDailyLossLimit(this);
                AppPrefs.log(this, "NEW ENTRY BLOCKED — DAILY NET LOSS LIMIT HIT",
                        "Local charge-adjusted realised NET P&L ₹" + money(dailyNet)
                                + " has reached the -₹2,000 floor.");
                return;
            }

            double buffer = AppPrefs.entryBufferPercent(this);
''')
old = r'''            GrowwClient.PnlResult dailyPnl = GrowwClient.getDailyRealisedMisPnl(token);
            if (!dailyPnl.success) {
                AppPrefs.log(this, "ENTRY BLOCKED — DAILY P&L UNAVAILABLE",
                        signal.symbol + " • " + dailyPnl.message
                                + " The daily ₹5,000 cap could not be verified, so no new order was submitted.");
                return;
            }
            if (dailyPnl.value >= ProfitTargetPolicy.DAILY_TARGET_RUPEES) {
                AppPrefs.lockDailyProfitTarget(this);
                AppPrefs.log(this, "NEW ENTRY BLOCKED — DAILY ₹5,000 TARGET DONE",
                        signal.symbol + " • broker-reported realised MIS P&L ₹"
                                + money(dailyPnl.value) + " has already reached the daily target.");
                return;
            }

'''
rep(service, old, '')
rep(service, '                + " | SL ₹" + money(signal.stopLossPrice)\n',
    '                + " | Multyfi SL ₹" + money(signal.stopLossPrice) + " (audit only)"\n')

monitor = JAVA / 'StrategyMonitorService.java'
def replace_method(path, signature, replacement):
    text=read(path); start=text.find(signature)
    if start<0: raise RuntimeError('method not found '+signature)
    brace=text.find('{',start); depth=0; end=-1
    for i in range(brace,len(text)):
        if text[i]=='{': depth+=1
        elif text[i]=='}':
            depth-=1
            if depth==0: end=i+1; break
    if end<0: raise RuntimeError('method end not found '+signature)
    write(path,text[:start]+replacement.rstrip()+text[end:])

replace_method(monitor, '    private void safeProfitTick()', r'''    private void safeProfitTick() {
        if (fastProfitSubmitting || !isMarketSession()) return;
        try {
            List<Strategy> active = StrategyStore.active(this);
            if (active.size() != 1) return;
            Strategy strategy = active.get(0);
            if (!strategy.isIntraday() || !Strategy.PROTECTED.equals(strategy.state)
                    || strategy.earlyExitRequested || !strategy.fastProfitArmed
                    || strategy.protectedQuantity <= 0
                    || strategy.protectedQuantity != strategy.observedFilledQuantity) return;
            if (!NetworkUtil.isNetworkAvailable(this) || !NetworkUtil.isVpnActive(this)
                    || !AppPrefs.isIpRecentlyVerified(this)
                    || !AppPrefs.isAuthVerifiedToday(this)) return;
            String token = TokenManager.validToken(this);
            if (token.isEmpty()) return;
            GrowwClient.DoubleResult ltp = GrowwClient.getLtp(token, strategy.symbol);
            if (!ltp.success) return;

            boolean lossHit = DailyRiskPolicy.lossThresholdHit(
                    ltp.value, strategy.dynamicLossStopPrice);
            boolean profitHit = DailyRiskPolicy.profitThresholdHit(
                    ltp.value, strategy.fastExitPrice);
            if (!lossHit && !profitHit) return;

            fastProfitSubmitting = true;
            String label;
            if (lossHit) {
                label = "Daily NET ₹2,000 loss limit";
                strategy.dailyLossExitTriggered = true;
                strategy.dailyProfitExitTriggered = false;
            } else {
                boolean dailyFirst = strategy.dailyTargetPrice > 0d
                        && (strategy.targetPrice <= 0d
                        || strategy.dailyTargetPrice <= strategy.targetPrice + 1e-9d);
                boolean dailyHit = dailyFirst
                        && ltp.value + 1e-9d >= strategy.dailyTargetPrice;
                label = dailyHit ? "Daily NET ₹5,000 profit target" : "Multyfi target";
                strategy.dailyProfitExitTriggered = dailyHit;
                strategy.dailyLossExitTriggered = false;
            }
            save(strategy);

            if (!tryImmediateTrackedTargetExit(token, strategy, label, ltp.value)) {
                long now = System.currentTimeMillis();
                if (now - lastFastProfitFailureLogAt > 1000L) {
                    lastFastProfitFailureLogAt = now;
                    AppPrefs.log(this, "FAST RISK EXIT FALLBACK",
                            strategy.symbol + " • " + label + " reached at LTP ₹"
                                    + money(ltp.value)
                                    + "; direct stop-to-MARKET conversion unavailable. "
                                    + "Running protected fallback now.");
                }
                executeExit(token, strategy, true, EXIT_TARGET);
            }
        } catch (Exception e) {
            AppPrefs.log(this, "FAST NET RISK WATCH ERROR",
                    e.getClass().getSimpleName() + ": " + e.getMessage());
        } finally { fastProfitSubmitting = false; }
    }''')

replace_method(monitor, '    private boolean ensureFastProfitTargetArmed', r'''    private boolean ensureFastProfitTargetArmed(String token, Strategy strategy) {
        if (!strategy.isIntraday()) return true;
        if (strategy.fastProfitArmed && strategy.entryAveragePrice > 0d
                && strategy.fastExitPrice > 0d && strategy.dynamicLossStopPrice > 0d) return true;

        GrowwClient.PositionSnapshot position = GrowwClient.getPositionSnapshot(
                token, strategy.symbol, strategy.productType);
        if (!position.success || position.quantity <= 0 || position.netPrice <= 0d) return false;
        GrowwClient.PnlResult brokerGross = GrowwClient.getDailyRealisedMisPnl(token);
        if (!brokerGross.success) return false;

        strategy.entryAveragePrice = position.netPrice;
        strategy.realisedPnlAtProfitArm = brokerGross.value;
        strategy.dailyNetBeforeTrade = DailyNetPnlLedger.netRealised(this);
        strategy.dailyProfitNeeded = DailyRiskPolicy.remainingNetProfit(strategy.dailyNetBeforeTrade);
        strategy.dailyTargetPrice = DailyRiskPolicy.netProfitExitPrice(
                strategy.entryAveragePrice, strategy.observedFilledQuantity,
                strategy.dailyNetBeforeTrade);
        strategy.dynamicLossStopPrice = DailyRiskPolicy.netLossStopPrice(
                strategy.entryAveragePrice, strategy.observedFilledQuantity,
                strategy.dailyNetBeforeTrade);
        strategy.stopLossPrice = strategy.dynamicLossStopPrice;
        strategy.fastExitPrice = DailyRiskPolicy.firstProfitExitPrice(
                strategy.targetPrice, strategy.dailyTargetPrice);
        strategy.fastProfitArmed = strategy.fastExitPrice > 0d
                && strategy.dynamicLossStopPrice > 0d;
        save(strategy);

        if (strategy.fastProfitArmed) {
            AppPrefs.log(this, "NET ₹5,000 / -₹2,000 RISK TARGETS ARMED",
                    strategy.symbol + " • average entry ₹" + money(strategy.entryAveragePrice)
                            + " • qty " + strategy.observedFilledQuantity
                            + " • daily realised NET before trade ₹" + money(strategy.dailyNetBeforeTrade)
                            + " • calculated NET +₹5k price ₹" + money(strategy.dailyTargetPrice)
                            + " • calculated daily NET -₹2k stop ₹" + money(strategy.dynamicLossStopPrice)
                            + " • Multyfi target ₹" + money(strategy.targetPrice)
                            + " • Multyfi stop ₹" + money(strategy.multyfiStopLossPrice)
                            + " is audit-only • 250 ms watcher + broker-side stop active.");
        }
        return strategy.fastProfitArmed;
    }''')

rep(monitor, r'''        if (strategy.observedFilledQuantity > strategy.protectedQuantity) {
            if (!staticIpReady) {
''', r'''        if (strategy.observedFilledQuantity > 0 && !strategy.fastProfitArmed) {
            if (!ensureFastProfitTargetArmed(token, strategy)) {
                strategy.lastMessage = "Fill observed; calculating NET +₹5,000 / -₹2,000 thresholds before protection.";
                save(strategy);
                return;
            }
        }

        if (strategy.observedFilledQuantity > strategy.protectedQuantity) {
            if (!staticIpReady) {
''')
rep(monitor, '            strategy.lastMessage = "Stop-loss is active; fast ₹5,000/Multyfi target watch is waiting for Groww entry-price/P&L data.";\n',
    '            strategy.lastMessage = "Stop-loss is active; NET risk watcher is waiting for Groww entry/P&L data.";\n')
rep(monitor, r'''        AppPrefs.log(this,
                strategy.dailyProfitExitTriggered
                        ? "₹5,000 DAILY PROFIT EXIT FAST SUBMITTED"
                        : "MULTYFI TARGET EXIT FAST SUBMITTED",
''', r'''        AppPrefs.log(this,
                strategy.dailyLossExitTriggered
                        ? "₹2,000 DAILY NET LOSS EXIT FAST SUBMITTED"
                        : strategy.dailyProfitExitTriggered
                        ? "₹5,000 DAILY NET PROFIT EXIT FAST SUBMITTED"
                        : "MULTYFI TARGET EXIT FAST SUBMITTED",
''')
rep(monitor, r'''            strategy.lastMessage = "Protected " + strategy.protectedQuantity + " "
                    + strategy.productType + " shares • fast exit threshold ₹"
                    + money(strategy.fastExitPrice) + " • Multyfi target ₹"
                    + money(strategy.targetPrice) + " • daily goal ₹5,000.";
''', r'''            strategy.lastMessage = "Protected " + strategy.protectedQuantity + " "
                    + strategy.productType + " shares • first profit exit ₹"
                    + money(strategy.fastExitPrice) + " • daily NET stop ₹"
                    + money(strategy.dynamicLossStopPrice) + " • daily band -₹2,000 / +₹5,000.";
''')
insert_before(monitor, '    private void processExitPending(String token, Strategy strategy,\n', r'''    private void reconcileClosedTradeNet(String token, Strategy strategy) {
        if (!strategy.isIntraday() || strategy.observedFilledQuantity <= 0
                || strategy.entryAveragePrice <= 0d) return;
        GrowwClient.PnlResult grossNow = GrowwClient.getDailyRealisedMisPnl(token);
        if (!grossNow.success) return;
        double tradeGross = grossNow.value - strategy.realisedPnlAtProfitArm;
        int qty = Math.max(1, strategy.observedFilledQuantity);
        double inferredSell = strategy.entryAveragePrice + (tradeGross / qty);
        if (inferredSell <= 0d) return;
        double charges = IntradayChargeCalculator.estimatedRoundTripCharges(
                strategy.entryAveragePrice * qty, inferredSell * qty);
        double tradeNet = tradeGross - charges;
        if (!DailyNetPnlLedger.record(this, strategy.eventId, tradeNet)) return;
        double dailyNet = DailyNetPnlLedger.netRealised(this);
        AppPrefs.log(this, "CLOSED TRADE NET P&L RECORDED",
                strategy.symbol + " • gross ₹" + money(tradeGross)
                        + " • estimated intraday charges ₹" + money(charges)
                        + " • trade NET ₹" + money(tradeNet)
                        + " • daily realised NET ₹" + money(dailyNet) + ".");
        if (DailyRiskPolicy.profitComplete(dailyNet)) {
            AppPrefs.lockDailyProfitTarget(this);
            AppPrefs.log(this, "DAILY NET ₹5,000 TARGET COMPLETE — ENTRIES LOCKED",
                    "Charge-adjusted daily realised NET P&L ₹" + money(dailyNet)
                            + ". No more trades today.");
        } else if (DailyRiskPolicy.lossComplete(dailyNet)) {
            AppPrefs.lockDailyLossLimit(this);
            AppPrefs.log(this, "DAILY NET -₹2,000 LIMIT REACHED — TRADING HALTED",
                    "Charge-adjusted daily realised NET P&L ₹" + money(dailyNet)
                            + ". No more trades today.");
        }
    }

''')
rep(monitor, r'''        if (remaining <= 0 && strategy.observedFilledQuantity > 0) {
            closeStrategy(strategy,
                    "Groww position is zero; automatic or manual exit completed.");
            return;
        }
''', r'''        if (remaining <= 0 && strategy.observedFilledQuantity > 0) {
            reconcileClosedTradeNet(token, strategy);
            closeStrategy(strategy,
                    "Groww position is zero; automatic or manual exit completed.");
            return;
        }
''')
start_block = r'''        if (remaining <= 0) {
            if (strategy.dailyProfitExitTriggered) {
                GrowwClient.PnlResult realised = GrowwClient.getDailyRealisedMisPnl(token);
                if (realised.success && realised.value >= ProfitTargetPolicy.DAILY_TARGET_RUPEES) {
                    AppPrefs.lockDailyProfitTarget(this);
                    AppPrefs.log(this, "DAILY ₹5,000 TARGET COMPLETE — ENTRIES LOCKED",
                            strategy.symbol + " • broker-reported realised MIS P&L ₹"
                                    + money(realised.value)
                                    + ". No further automatic entries will be created today.");
                } else if (realised.success) {
                    AppPrefs.log(this, "₹5,000 EXIT FILLED — DAILY TARGET NOT YET NETTED",
                            strategy.symbol + " • realised MIS P&L is ₹"
                                    + money(realised.value)
                                    + " after execution/slippage. Future calls remain eligible until broker-reported realised P&L reaches ₹5,000.");
                }
            }
            closeStrategy(strategy, strategy.pendingExitLabel.isEmpty()
                    ? "Exit sell completed." : strategy.pendingExitLabel + " completed.");
            return;
        }
'''
rep(monitor, start_block, r'''        if (remaining <= 0) {
            reconcileClosedTradeNet(token, strategy);
            closeStrategy(strategy, strategy.pendingExitLabel.isEmpty()
                    ? "Exit sell completed." : strategy.pendingExitLabel + " completed.");
            return;
        }
''')
rep(monitor, '                + " • ₹5k " + (AppPrefs.isDailyProfitLocked(this) ? "done" : "goal");\n',
    '                + " • NET band " + (AppPrefs.isDailyProfitLocked(this) ? "+₹5k DONE"\n'
    '                : AppPrefs.isDailyLossLocked(this) ? "-₹2k HALT" : "ACTIVE");\n')

activity = JAVA / 'ProductionActivity.java'
write(activity, read(activity).replace('2.3.5', '2.4.0'))
rep(activity, '        TextView title = label("Multyfi AutoBuy Pro", 30, TEXT, true);\n',
    '        TextView title = label(AppRole.isChild(this) ? "Multyfi AutoBuy CHILD" : "Multyfi AutoBuy MASTER", 30, TEXT, true);\n')
rep(activity, '        TextView subtitle = label("Android 16 • source-built stable release 2.4.0", 14, MUTED, false);\n',
    '        TextView subtitle = label(AppRole.isChild(this) ? "LG G7 ThinQ • local-LAN child • release 2.4.0" : "Galaxy S24 Ultra • local-LAN master • release 2.4.0", 14, MUTED, false);\n')
rep(activity, '        StrategyMonitorService.ensureRunning(this);\n        refreshAuthenticationAutomatically();\n',
    '        StrategyMonitorService.ensureRunning(this);\n        AppRole.ensureRelay(this);\n        refreshAuthenticationAutomatically();\n', count=2)
rep(activity, r'''        try {
            NotificationListenerService.requestRebind(
                    new ComponentName(this, MultyfiNotificationService.class));
        } catch (Exception ignored) { }
''', r'''        if (!AppRole.isChild(this)) {
            try {
                NotificationListenerService.requestRebind(
                        new ComponentName(this, MultyfiNotificationService.class));
            } catch (Exception ignored) { }
        }
''')
rep(activity, '        boolean notificationReady = hasNotificationAccess();\n',
    '        boolean notificationReady = AppRole.isChild(this) ? RelayState.childConnected(this) : hasNotificationAccess();\n')
rep(activity, r'''        notificationStatus.setText(notificationReady
                ? "● Notification listener: connected permission granted"
                : "● Notification listener: access not granted");
''', r'''        notificationStatus.setText(AppRole.isChild(this)
                ? (notificationReady
                    ? "● Master LAN relay: connected • " + RelayState.masterIp(this)
                        + " • last " + Math.max(0, RelayState.latency(this)) + " ms"
                    : "● Master LAN relay: disconnected — auto-retrying")
                : (notificationReady
                    ? "● Notification listener: connected permission granted • LAN children "
                        + RelayState.masterChildren(this)
                    : "● Notification listener: access not granted"));
''')
rep(activity, '        if (!hasNotificationAccess()) return "Grant Notification Access to Multyfi AutoBuy";\n',
    '        if (AppRole.isChild(this) && !RelayState.childConnected(this)) return "Waiting for local-LAN connection to MASTER";\n'
    '        if (!AppRole.isChild(this) && !hasNotificationAccess()) return "Grant Notification Access to Multyfi AutoBuy MASTER";\n')
write(activity, read(activity).replace(
    'Auto-Buy OFF by default • Intraday MIS • ₹5,000 daily target • fast early sell • source-built v2.4.0',
    'Auto-Buy OFF by default • daily NET band -₹2,000 / +₹5,000 • local LAN relay • v2.4.0'))

boot = JAVA / 'BootReceiver.java'
rep(boot, '            StrategyMonitorService.ensureRunning(context);\n',
    '            StrategyMonitorService.ensureRunning(context);\n            AppRole.ensureRelay(context);\n')

manifest = APP / 'src/main/AndroidManifest.xml'
rep(manifest, '    <uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />\n',
    '    <uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />\n'
    '    <uses-permission android:name="android.permission.ACCESS_WIFI_STATE" />\n'
    '    <uses-permission android:name="android.permission.CHANGE_WIFI_MULTICAST_STATE" />\n')
insert_before(manifest, '        <receiver\n            android:name=".BootReceiver"', r'''        <service
            android:name=".LanMasterRelayService"
            android:exported="false"
            android:foregroundServiceType="specialUse"
            android:stopWithTask="false">
            <property
                android:name="android.app.PROPERTY_SPECIAL_USE_FGS_SUBTYPE"
                android:value="Local Wi-Fi/hotspot Multyfi signal relay to paired child phones" />
        </service>

''')

strings = APP / 'src/main/res/values/strings.xml'
write(strings, read(strings).replace('<string name="app_name">Multyfi AutoBuy S24</string>',
                                    '<string name="app_name">Multyfi AutoBuy MASTER</string>'))

child = ROOT / 'child'
if child.exists(): shutil.rmtree(child)
shutil.copytree(APP, child)
cg = child / 'build.gradle'
ct = read(cg)
ct = ct.replace("applicationId 'com.suhas.multyfiautobuy.stable'", "applicationId 'com.suhas.multyfiautobuy.child'")
ct = ct.replace('minSdk 28', 'minSdk 26')
write(cg, ct)
cs = child / 'src/main/res/values/strings.xml'
write(cs, read(cs).replace('<string name="app_name">Multyfi AutoBuy MASTER</string>',
                           '<string name="app_name">Multyfi AutoBuy CHILD</string>'))
cm = child / 'src/main/AndroidManifest.xml'
cmtext = read(cm)
pattern = re.compile(r'\n        <service\n            android:name="\.MultyfiNotificationService".*?</service>\n', re.S)
cmtext, n = pattern.subn('\n', cmtext, count=1)
if n != 1: raise RuntimeError('child notification-listener block not removed')
cmtext = cmtext.replace('android:name=".LanMasterRelayService"', 'android:name=".LanChildRelayService"')
cmtext = cmtext.replace('Local Wi-Fi/hotspot Multyfi signal relay to paired child phones',
                        'Local Wi-Fi/hotspot Multyfi signal receiver from the master phone')
write(cm, cmtext)

settings = ROOT / 'settings.gradle'
rep(settings, 'include(":app")\n', 'include(":app")\ninclude(":child")\n')

write(TEST / 'ProfitTargetPolicyTest.java', r'''package com.suhas.multyfiautobuy.stable;
import static org.junit.Assert.*;
import org.junit.Test;
public class ProfitTargetPolicyTest {
 @Test public void netFiveThousandNeedsMoreThanFiveThousandGross(){
   double p=DailyRiskPolicy.netProfitExitPrice(1000d,300,0d);
   assertTrue((p-1000d)*300d > 5000d);
   assertTrue(IntradayChargeCalculator.estimatedNetPnl(1000d,p,300)>=5000d);
 }
 @Test public void priorNetProfitReducesRemainingTarget(){
   double p=DailyRiskPolicy.netProfitExitPrice(1000d,300,3000d);
   assertTrue(IntradayChargeCalculator.estimatedNetPnl(1000d,p,300)>=2000d);
 }
 @Test public void dailyLossStopTargetsNetMinusTwoThousand(){
   double s=DailyRiskPolicy.netLossStopPrice(1000d,300,0d);
   double n=IntradayChargeCalculator.estimatedNetPnl(1000d,s,300);
   assertTrue(n <= -1900d && n >= -2050d);
 }
 @Test public void previousProfitExpandsRoomOnlyUntilDailyNetMinusTwoThousand(){
   double s=DailyRiskPolicy.netLossStopPrice(1000d,300,3000d);
   double n=IntradayChargeCalculator.estimatedNetPnl(1000d,s,300);
   assertTrue(n <= -4900d && n >= -5050d);
 }
}
''')
write(TEST / 'IntradayChargeCalculatorTest.java', r'''package com.suhas.multyfiautobuy.stable;
import static org.junit.Assert.*;
import org.junit.Test;
public class IntradayChargeCalculatorTest {
 @Test public void officialNseIntradayRatesProducePositiveCharges(){
   double c=IntradayChargeCalculator.estimatedRoundTripCharges(300000d,305000d);
   assertTrue(c>150d && c<160d);
 }
 @Test public void brokerageIsCappedAtTwentyPerLargeOrder(){
   assertEquals(20d,IntradayChargeCalculator.brokerage(300000d),0.0001d);
 }
}
''')
write(TEST / 'LanRelayProtocolTest.java', r'''package com.suhas.multyfiautobuy.stable;
import static org.junit.Assert.*;
import org.junit.Test;
public class LanRelayProtocolTest {
 @Test public void signedSignalRoundTrips() throws Exception {
   String raw="Stock Name: TCS\\nEntry Range: 100-101\\nTarget: 110\\nStop Loss: 95";
   String line=LanRelayProtocol.envelope(raw,1234L,2000L);
   LanRelayProtocol.Signal s=LanRelayProtocol.parse(line);
   assertEquals(raw,s.rawText); assertEquals(1234L,s.sourcePostTime);
 }
 @Test public void discoveryIsAuthenticated(){String d=LanRelayProtocol.discover("abc");assertTrue(LanRelayProtocol.validDiscover(d));assertFalse(LanRelayProtocol.validDiscover(d+"x"));}
}
''')

assert "versionCode 240" in read(gradle)
assert "versionName '2.4.0'" in read(gradle)
assert "NET_PROFIT_TARGET = 5000d" in read(JAVA/'DailyRiskPolicy.java')
assert "NET_LOSS_FLOOR = -2000d" in read(JAVA/'DailyRiskPolicy.java')
assert "strategy.stopLossPrice = strategy.dynamicLossStopPrice" in read(monitor)
assert "₹2,000 DAILY NET LOSS EXIT FAST SUBMITTED" in read(monitor)
assert "₹5,000 DAILY NET PROFIT EXIT FAST SUBMITTED" in read(monitor)
assert "LanMasterRelayService.publishAsync" in read(service)
assert "enqueueRelayedMultyfi" in read(service)
assert "applicationId 'com.suhas.multyfiautobuy.child'" in read(cg)
assert "minSdk 26" in read(cg)
assert 'android:name=".LanChildRelayService"' in read(cm)
assert 'android:name=".MultyfiNotificationService"' not in read(cm)
print('Applied Multyfi AutoBuy v2.4.0 MASTER + CHILD + daily NET risk band')
