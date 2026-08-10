#!/usr/bin/env python3
from pathlib import Path
import runpy

runpy.run_path('hotfix/run_v243.py', run_name='__main__')
ROOT = Path('android-stable')


def read(p): return Path(p).read_text(encoding='utf-8')
def write(p, s):
    p = Path(p); p.parent.mkdir(parents=True, exist_ok=True); p.write_text(s, encoding='utf-8')
def patch(p, old, new, expected=1):
    p = Path(p); text = read(p); n = text.count(old)
    if n != expected:
        raise RuntimeError(f'Expected {expected} matches in {p}, found {n}: {old[:160]}')
    write(p, text.replace(old, new, expected))

PRIORITY_EXECUTORS = r'''package com.suhas.multyfiautobuy.stable;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * Keeps broker-facing notification work above local relay/UI/background work.
 * Android/Linux uses lower numeric nice values for more favorable scheduling.
 */
final class PriorityExecutors {
    static final int EARLY_EXIT_PRIORITY = -4; // android.os.Process.THREAD_PRIORITY_DISPLAY
    static final int ENTRY_PRIORITY = -2;      // android.os.Process.THREAD_PRIORITY_FOREGROUND
    static final int RELAY_PRIORITY = 10;      // android.os.Process.THREAD_PRIORITY_BACKGROUND

    private PriorityExecutors() { }

    static ExecutorService earlyExitSingle(String name) {
        return Executors.newSingleThreadExecutor(factory(name, EARLY_EXIT_PRIORITY));
    }

    static ExecutorService entrySingle(String name) {
        return Executors.newSingleThreadExecutor(factory(name, ENTRY_PRIORITY));
    }

    static ExecutorService backgroundSingle(String name) {
        return Executors.newSingleThreadExecutor(factory(name, RELAY_PRIORITY));
    }

    static ExecutorService backgroundCached(String name) {
        return Executors.newCachedThreadPool(factory(name, RELAY_PRIORITY));
    }

    static ScheduledExecutorService backgroundScheduled(String name) {
        return Executors.newSingleThreadScheduledExecutor(factory(name, RELAY_PRIORITY));
    }

    static boolean primaryBeatsRelayContract() {
        return EARLY_EXIT_PRIORITY < ENTRY_PRIORITY && ENTRY_PRIORITY < RELAY_PRIORITY;
    }

    private static ThreadFactory factory(String prefix, int priority) {
        AtomicInteger ids = new AtomicInteger();
        return task -> new Thread(() -> {
            try { android.os.Process.setThreadPriority(priority); }
            catch (Exception ignored) { }
            task.run();
        }, prefix + '-' + ids.incrementAndGet());
    }
}
'''

RELAY_LOG = r'''package com.suhas.multyfiautobuy.stable;

import android.util.Log;

/**
 * Relay diagnostics intentionally bypass AppPrefs.log's synchronized audit lock.
 * A LAN retry/broadcast must never hold a lock needed by BUY/SELL dispatch.
 */
final class RelayLog {
    private static final String TAG = "MultyfiRelay";
    private RelayLog() { }
    static void info(String event, String message) {
        Log.i(TAG, event + " | " + (message == null ? "" : message));
    }
    static void warn(String event, String message) {
        Log.w(TAG, event + " | " + (message == null ? "" : message));
    }
}
'''

MASTER_RELAY = r'''package com.suhas.multyfiautobuy.stable;

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
    private static final long RETRY_MS=500L;
    private static final ExecutorService FALLBACK =
            PriorityExecutors.backgroundSingle("multyfi-relay-fallback");
    private static volatile LanMasterRelayService live;

    private final Set<Client> clients=ConcurrentHashMap.newKeySet();
    private ExecutorService io;
    private ExecutorService broadcasts;
    private volatile boolean running;
    private volatile ServerSocket server;
    private volatile long lastTcpErrorLogAt;
    private volatile long lastDiscoveryErrorLogAt;

    static void ensureRunning(Context c) {
        if (AppRole.isChild(c) || !AppPrefs.isArmed(c)) return;
        Intent i=new Intent(c, LanMasterRelayService.class);
        try { c.startForegroundService(i); }
        catch(Exception e) { RelayLog.warn("MASTER LAN RELAY START FAILED", String.valueOf(e.getMessage())); }
    }

    static void publishAsync(Context c,String raw,long post) {
        if (AppRole.isChild(c) || !AppPrefs.isArmed(c) || raw==null || raw.trim().isEmpty()) return;
        Intent i=new Intent(c,LanMasterRelayService.class).setAction(ACTION_PUBLISH)
                .putExtra(EXTRA_RAW,raw).putExtra(EXTRA_POST,post);
        try { c.startForegroundService(i); }
        catch(Exception e) { RelayLog.warn("MASTER LAN RELAY PUBLISH FAILED", String.valueOf(e.getMessage())); }
    }

    /**
     * Non-blocking from the notification callback. If the service is not live, even the service-start
     * fallback is moved onto a background-priority thread; MASTER broker work has already been queued.
     */
    static void publishFast(Context c,String raw,long post) {
        if (AppRole.isChild(c) || !AppPrefs.isArmed(c) || raw==null || raw.trim().isEmpty()) return;
        LanMasterRelayService s=live;
        if(s!=null && s.running && s.broadcasts!=null){
            try { s.broadcasts.execute(() -> s.broadcast(raw,post)); return; }
            catch(Exception ignored) { }
        }
        Context app=c.getApplicationContext();
        try { FALLBACK.execute(() -> publishAsync(app,raw,post)); }
        catch(Exception ignored) { }
    }

    @Override public void onCreate(){
        super.onCreate();
        live=this;
        createChannel();
        startForeground(ID,note("Master LAN relay starting"));
        io=PriorityExecutors.backgroundCached("multyfi-relay-io");
        broadcasts=PriorityExecutors.backgroundSingle("multyfi-relay-broadcast");
        running=true;
        io.execute(this::serverLoop);
        io.execute(this::discoveryLoop);
    }

    @Override public int onStartCommand(Intent i,int f,int id){
        if(!AppPrefs.isArmed(this)){stopSelf();return START_NOT_STICKY;}
        if(i!=null&&ACTION_PUBLISH.equals(i.getAction())){
            final String raw=i.getStringExtra(EXTRA_RAW);
            final long post=i.getLongExtra(EXTRA_POST,System.currentTimeMillis());
            if (broadcasts != null) broadcasts.execute(() -> broadcast(raw,post));
        }
        return START_STICKY;
    }

    @Override public void onDestroy(){
        if(live==this)live=null;
        RelayState.masterChildren(this,0);
        running=false;
        closeServer();
        for(Client c:clients)c.close();
        clients.clear();
        if(broadcasts!=null)broadcasts.shutdownNow();
        if(io!=null)io.shutdownNow();
        super.onDestroy();
    }
    @Override public IBinder onBind(Intent i){return null;}

    /** A transient bind/interface error no longer kills the relay until the user re-arms it. */
    private void serverLoop(){
        while(running){
            ServerSocket local=null;
            try{
                local=new ServerSocket();
                local.setReuseAddress(true);
                local.bind(new InetSocketAddress(LanRelayProtocol.TCP_PORT));
                server=local;
                while(running){
                    Socket s=local.accept();
                    s.setTcpNoDelay(true);
                    s.setKeepAlive(true);
                    io.execute(() -> acceptClient(s));
                }
            }catch(Exception e){
                if(running) logRetryLimited(true,e);
            }finally{
                if(server==local)server=null;
                try{if(local!=null)local.close();}catch(Exception ignored){}
            }
            if(running)sleep(RETRY_MS);
        }
    }

    private void acceptClient(Socket s){
        Client c=null;
        try{
            s.setSoTimeout(5000);
            BufferedReader r=new BufferedReader(new InputStreamReader(s.getInputStream(),StandardCharsets.UTF_8));
            PrintWriter w=new PrintWriter(new OutputStreamWriter(s.getOutputStream(),StandardCharsets.UTF_8),true);
            String hello=r.readLine();
            if(!LanRelayProtocol.validHello(hello)){s.close();return;}
            // CHILD emits a lightweight PING every 3 seconds. Fifteen seconds without one is stale.
            s.setSoTimeout(15000);
            c=new Client(s,w);
            clients.add(c);
            RelayState.masterChildren(this,clients.size());
            update();
            RelayLog.info("CHILD PHONE CONNECTED",s.getInetAddress().getHostAddress()+" • connected children "+clients.size());
            while(running){
                String line=r.readLine();
                if(line==null)break;
                // ACK and PING are deliberately consumed off the trading path.
            }
        }catch(Exception ignored){}
        finally{
            if(c!=null){
                clients.remove(c);c.close();RelayState.masterChildren(this,clients.size());update();
            }else try{s.close();}catch(Exception ignored){}
        }
    }

    /** UDP discovery also self-heals forever while the app is armed. */
    private void discoveryLoop(){
        while(running){
            try(DatagramSocket d=new DatagramSocket(null)){
                d.setReuseAddress(true);
                d.bind(new InetSocketAddress(LanRelayProtocol.UDP_PORT));
                byte[] buf=new byte[512];
                while(running){
                    DatagramPacket p=new DatagramPacket(buf,buf.length);
                    d.receive(p);
                    String m=new String(p.getData(),p.getOffset(),p.getLength(),StandardCharsets.UTF_8);
                    if(!LanRelayProtocol.validDiscover(m))continue;
                    String[] x=m.split("\\|",-1);
                    byte[] out=LanRelayProtocol.masterReply(x[1]).getBytes(StandardCharsets.UTF_8);
                    d.send(new DatagramPacket(out,out.length,p.getAddress(),p.getPort()));
                }
            }catch(Exception e){
                if(running)logRetryLimited(false,e);
            }
            if(running)sleep(RETRY_MS);
        }
    }

    private void broadcast(String raw,long post){
        try{
            long sent=System.currentTimeMillis();
            String line=LanRelayProtocol.envelope(raw,post,sent);
            int ok=0;
            for(Client c:clients){
                if(c.send(line))ok++;
                else{clients.remove(c);c.close();}
            }
            RelayState.masterChildren(this,clients.size());
            update();
            RelayLog.info("MULTYFI LAN BROADCAST","Children "+ok+"/"+clients.size()+" • source age "+Math.max(0,sent-post)+" ms • MASTER broker work was queued first.");
        }catch(Exception e){RelayLog.warn("MASTER LAN BROADCAST ERROR",String.valueOf(e.getMessage()));}
    }

    private void logRetryLimited(boolean tcp,Exception e){
        long now=System.currentTimeMillis();
        long last=tcp?lastTcpErrorLogAt:lastDiscoveryErrorLogAt;
        if(now-last<5000L)return;
        if(tcp)lastTcpErrorLogAt=now;else lastDiscoveryErrorLogAt=now;
        RelayLog.warn(tcp?"MASTER LAN TCP RETRY":"MASTER LAN DISCOVERY RETRY",
                e.getClass().getSimpleName()+": "+String.valueOf(e.getMessage()));
    }

    private void closeServer(){try{ServerSocket s=server;if(s!=null)s.close();}catch(Exception ignored){}}
    private static void sleep(long ms){try{Thread.sleep(ms);}catch(InterruptedException e){Thread.currentThread().interrupt();}}
    private void createChannel(){NotificationManager n=(NotificationManager)getSystemService(NOTIFICATION_SERVICE);if(n!=null)n.createNotificationChannel(new NotificationChannel(CH,"Master LAN relay",NotificationManager.IMPORTANCE_LOW));}
    private Notification note(String t){return new Notification.Builder(this,CH).setSmallIcon(android.R.drawable.stat_notify_sync).setContentTitle("Multyfi MASTER relay").setContentText(t).setOngoing(true).build();}
    private void update(){NotificationManager n=(NotificationManager)getSystemService(NOTIFICATION_SERVICE);if(n!=null)n.notify(ID,note("Connected child phones: "+clients.size()));}

    static final class Client{
        final Socket s;final PrintWriter w;
        Client(Socket s,PrintWriter w){this.s=s;this.w=w;}
        synchronized boolean send(String x){try{w.println(x);return !w.checkError();}catch(Exception e){return false;}}
        void close(){try{s.close();}catch(Exception ignored){}}
    }
}
'''

CHILD_RELAY = r'''package com.suhas.multyfiautobuy.stable;

import android.app.*;
import android.content.*;
import android.net.*;
import android.net.wifi.WifiManager;
import android.os.*;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.*;

public final class LanChildRelayService extends ProductionNotificationService {
    private static final String CH="multyfi_child_lan";
    private static final int ID=2402;
    private final Object routeWake=new Object();
    private ExecutorService net;
    private ScheduledExecutorService heartbeats;
    private volatile boolean running;
    private volatile Socket socket;
    private volatile String lastRoute="";
    private volatile Network wifiNetwork;
    private ConnectivityManager connectivity;
    private ConnectivityManager.NetworkCallback wifiCallback;

    static void ensureRunning(Context c){
        if(!AppRole.isChild(c) || !AppPrefs.isArmed(c)) return;
        try{c.startForegroundService(new Intent(c,LanChildRelayService.class));}
        catch(Exception e){RelayLog.warn("CHILD LAN RELAY START FAILED",String.valueOf(e.getMessage()));}
    }

    @Override public void onCreate(){
        super.onCreate();
        if(!AppPrefs.isArmed(this)){stopSelf();return;}
        createChannel();
        startForeground(ID,note("Finding MASTER through physical Wi-Fi/hotspot"));
        running=true;
        connectivity=(ConnectivityManager)getSystemService(CONNECTIVITY_SERVICE);
        registerWifiCallback();
        net=PriorityExecutors.backgroundSingle("multyfi-child-relay");
        heartbeats=PriorityExecutors.backgroundScheduled("multyfi-child-heartbeat");
        net.execute(this::loop);
    }

    @Override public int onStartCommand(Intent i,int f,int id){
        if(!AppPrefs.isArmed(this)){stopSelf();return START_NOT_STICKY;}
        wakeRelay();
        return START_STICKY;
    }

    @Override public void onDestroy(){
        running=false;
        RelayState.childDisconnected(this);
        unregisterWifiCallback();
        closeCurrentSocket();
        wakeRelay();
        if(heartbeats!=null)heartbeats.shutdownNow();
        if(net!=null)net.shutdownNow();
        super.onDestroy();
    }

    private void registerWifiCallback(){
        if(connectivity==null)return;
        try{
            NetworkRequest request=new NetworkRequest.Builder()
                    .addTransportType(NetworkCapabilities.TRANSPORT_WIFI).build();
            wifiCallback=new ConnectivityManager.NetworkCallback(){
                @Override public void onAvailable(Network n){setWifiNetwork(n,false);}
                @Override public void onCapabilitiesChanged(Network n,NetworkCapabilities c){
                    if(c!=null&&c.hasTransport(NetworkCapabilities.TRANSPORT_WIFI))setWifiNetwork(n,false);
                }
                @Override public void onLinkPropertiesChanged(Network n,LinkProperties lp){
                    setWifiNetwork(n,true);
                }
                @Override public void onLost(Network n){
                    Network current=wifiNetwork;
                    if(current!=null&&current.equals(n)){
                        wifiNetwork=null;
                        closeCurrentSocket();
                        RelayState.childDisconnected(LanChildRelayService.this);
                        update("Wi-Fi/hotspot changed — rediscovering MASTER");
                        wakeRelay();
                    }
                }
            };
            connectivity.registerNetworkCallback(request,wifiCallback);
        }catch(Exception e){RelayLog.warn("CHILD WIFI CALLBACK",String.valueOf(e.getMessage()));}
    }

    private void unregisterWifiCallback(){
        try{if(connectivity!=null&&wifiCallback!=null)connectivity.unregisterNetworkCallback(wifiCallback);}
        catch(Exception ignored){}
    }

    private void setWifiNetwork(Network n,boolean linkChanged){
        if(!running||n==null)return;
        try{
            NetworkCapabilities caps=connectivity==null?null:connectivity.getNetworkCapabilities(n);
            if(caps==null||!caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI))return;
        }catch(Exception ignored){return;}
        Network old=wifiNetwork;
        wifiNetwork=n;
        if(linkChanged || (old!=null&&!old.equals(n)))closeCurrentSocket();
        wakeRelay();
    }

    private void loop(){
        while(running && AppPrefs.isArmed(this)){
            try{
                Network wifi=physicalWifiNetwork();
                if(wifi==null){
                    RelayState.childDisconnected(this);
                    update("No physical Wi-Fi/hotspot route — retrying");
                    pause(750);
                    continue;
                }
                InetAddress gateway=wifiGateway(wifi);
                String route=gateway==null?"Wi-Fi gateway unknown":("Wi-Fi gateway "+gateway.getHostAddress());
                if(!route.equals(lastRoute)){
                    lastRoute=route;
                    RelayLog.info("CHILD LOCAL RELAY ROUTE",route+" • only relay sockets bypass VPN; Groww remains on VPN.");
                }
                Host h=discover(wifi,gateway);
                if(h==null){
                    RelayState.childDisconnected(this);
                    update((gateway==null?"MASTER not found on Wi-Fi":"MASTER not found at hotspot gateway "+gateway.getHostAddress())+" — retrying");
                    pause(650);
                    continue;
                }
                connect(wifi,h);
            }catch(Exception e){
                RelayState.childDisconnected(this);
                update("Disconnected — local Wi-Fi retrying");
                pause(350);
            }
        }
    }

    private Network physicalWifiNetwork(){
        try{
            Network cached=wifiNetwork;
            if(cached!=null&&connectivity!=null){
                NetworkCapabilities caps=connectivity.getNetworkCapabilities(cached);
                if(caps!=null&&caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI))return cached;
            }
            ConnectivityManager cm=connectivity!=null?connectivity:(ConnectivityManager)getSystemService(CONNECTIVITY_SERVICE);
            if(cm==null)return null;
            for(Network n:cm.getAllNetworks()){
                NetworkCapabilities caps=cm.getNetworkCapabilities(n);
                if(caps!=null&&caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI)){
                    wifiNetwork=n;
                    return n;
                }
            }
        }catch(Exception ignored){}
        return null;
    }

    private InetAddress wifiGateway(Network wifi){
        try{
            ConnectivityManager cm=connectivity!=null?connectivity:(ConnectivityManager)getSystemService(CONNECTIVITY_SERVICE);
            LinkProperties lp=cm==null?null:cm.getLinkProperties(wifi);
            InetAddress fallback=null;
            if(lp!=null){
                for(RouteInfo route:lp.getRoutes()){
                    InetAddress g=route.getGateway();
                    if(!(g instanceof Inet4Address))continue;
                    if(route.isDefaultRoute())return g;
                    if(fallback==null)fallback=g;
                }
            }
            if(fallback!=null)return fallback;
        }catch(Exception ignored){}
        try{
            WifiManager wm=(WifiManager)getApplicationContext().getSystemService(WIFI_SERVICE);
            android.net.DhcpInfo d=wm==null?null:wm.getDhcpInfo();
            if(d!=null&&d.gateway!=0){
                byte[] a=new byte[]{(byte)(d.gateway&0xff),(byte)((d.gateway>>8)&0xff),(byte)((d.gateway>>16)&0xff),(byte)((d.gateway>>24)&0xff)};
                return InetAddress.getByAddress(a);
            }
        }catch(Exception ignored){}
        return null;
    }

    private Host discover(Network wifi,InetAddress gateway){
        String nonce=Long.toHexString(System.nanoTime());
        byte[] q=LanRelayProtocol.discover(nonce).getBytes(StandardCharsets.UTF_8);
        try(DatagramSocket d=new DatagramSocket(null)){
            d.setReuseAddress(true);d.bind(new InetSocketAddress(0));wifi.bindSocket(d);d.setBroadcast(true);d.setSoTimeout(600);
            LinkedHashSet<InetAddress> targets=new LinkedHashSet<>();
            if(gateway!=null)targets.add(gateway);
            targets.add(InetAddress.getByName("255.255.255.255"));
            try{
                Enumeration<NetworkInterface> en=NetworkInterface.getNetworkInterfaces();
                while(en.hasMoreElements()){
                    NetworkInterface ni=en.nextElement();
                    for(InterfaceAddress a:ni.getInterfaceAddresses())if(a.getBroadcast()!=null)targets.add(a.getBroadcast());
                }
            }catch(Exception ignored){}
            for(InetAddress a:targets)try{d.send(new DatagramPacket(q,q.length,a,LanRelayProtocol.UDP_PORT));}catch(Exception ignored){}
            long end=System.currentTimeMillis()+600;
            byte[] buf=new byte[512];
            while(System.currentTimeMillis()<end){
                DatagramPacket p=new DatagramPacket(buf,buf.length);
                try{d.receive(p);}catch(SocketTimeoutException e){break;}
                String r=new String(p.getData(),p.getOffset(),p.getLength(),StandardCharsets.UTF_8);
                int port=LanRelayProtocol.validMasterReplyPort(r,nonce);
                if(port>0)return new Host(p.getAddress(),port);
            }
        }catch(Exception ignored){}
        return null;
    }

    private void connect(Network wifi,Host h)throws Exception{
        Socket s=new Socket();
        socket=s;
        wifi.bindSocket(s);
        s.connect(new InetSocketAddress(h.a,h.p),1200);
        s.setTcpNoDelay(true);s.setKeepAlive(true);
        final Object writeLock=new Object();
        PrintWriter w=new PrintWriter(new OutputStreamWriter(s.getOutputStream(),StandardCharsets.UTF_8),true);
        BufferedReader r=new BufferedReader(new InputStreamReader(s.getInputStream(),StandardCharsets.UTF_8));
        String device=Build.MANUFACTURER+"-"+Build.MODEL;
        synchronized(writeLock){w.println(LanRelayProtocol.hello(device,Long.toHexString(System.nanoTime())));}
        RelayState.childConnected(this,h.a.getHostAddress(),-1);
        update("Connected to MASTER "+h.a.getHostAddress()+" via hotspot/Wi-Fi");
        RelayLog.info("CHILD CONNECTED TO MASTER",h.a.getHostAddress()+":"+h.p+" • physical Wi-Fi pinned; VPN remains for Groww.");

        ScheduledFuture<?> beat=heartbeats==null?null:heartbeats.scheduleAtFixedRate(() -> {
            try{
                synchronized(writeLock){
                    w.println("PING|"+System.currentTimeMillis());
                    if(w.checkError())closeSocket(s);
                }
            }catch(Exception e){closeSocket(s);}
        },1,3,TimeUnit.SECONDS);

        try{
            String line;
            while(running&&AppPrefs.isArmed(this)&&(line=r.readLine())!=null){
                long recv=System.currentTimeMillis();
                try{
                    LanRelayProtocol.Signal sig=LanRelayProtocol.parse(line);
                    enqueueRelayedMultyfi(sig.rawText,sig.sourcePostTime);
                    long latency=Math.max(0,recv-sig.masterSentAt);
                    synchronized(writeLock){w.println(LanRelayProtocol.ack(sig.eventId,recv));}
                    RelayState.childConnected(this,h.a.getHostAddress(),latency);
                    update("MASTER connected • last relay "+latency+" ms");
                    RelayLog.info("MULTYFI SIGNAL RECEIVED FROM MASTER","LAN latency "+latency+" ms • event "+sig.eventId.substring(0,12));
                }catch(Exception e){RelayLog.warn("CHILD RELAY PACKET REJECTED",String.valueOf(e.getMessage()));}
            }
        }finally{
            if(beat!=null)beat.cancel(true);
            closeSocket(s);
            RelayState.childDisconnected(this);
        }
    }

    private void closeCurrentSocket(){Socket s=socket;if(s!=null)closeSocket(s);}
    private void closeSocket(Socket s){
        if(s==null)return;
        try{s.close();}catch(Exception ignored){}
        if(socket==s)socket=null;
    }
    private void wakeRelay(){synchronized(routeWake){routeWake.notifyAll();}}
    private void pause(long ms){
        synchronized(routeWake){try{routeWake.wait(ms);}catch(InterruptedException e){Thread.currentThread().interrupt();}}
    }
    private void createChannel(){NotificationManager n=(NotificationManager)getSystemService(NOTIFICATION_SERVICE);if(n!=null)n.createNotificationChannel(new NotificationChannel(CH,"Child LAN relay",NotificationManager.IMPORTANCE_LOW));}
    private Notification note(String t){return new Notification.Builder(this,CH).setSmallIcon(android.R.drawable.stat_notify_sync).setContentTitle("Multyfi CHILD relay").setContentText(t).setOngoing(true).build();}
    private void update(String t){NotificationManager n=(NotificationManager)getSystemService(NOTIFICATION_SERVICE);if(n!=null)n.notify(ID,note(t));}
    static final class Host{final InetAddress a;final int p;Host(InetAddress a,int p){this.a=a;this.p=p;}}
}
'''

TEST = r'''package com.suhas.multyfiautobuy.stable;

import org.junit.Test;
import static org.junit.Assert.*;

public class PrimaryExecutionPriorityTest {
    @Test public void earlyExitBeatsEntryAndEntryBeatsRelay() {
        assertTrue(PriorityExecutors.primaryBeatsRelayContract());
        assertTrue(PriorityExecutors.EARLY_EXIT_PRIORITY < PriorityExecutors.ENTRY_PRIORITY);
        assertTrue(PriorityExecutors.ENTRY_PRIORITY < PriorityExecutors.RELAY_PRIORITY);
    }
}
'''

for module in ('app','child'):
    build=ROOT/module/'build.gradle'
    patch(build,'versionCode 243','versionCode 244')
    patch(build,"versionName '2.4.3'","versionName '2.4.4'")
    J=ROOT/module/'src/main/java/com/suhas/multyfiautobuy/stable'
    T=ROOT/module/'src/test/java/com/suhas/multyfiautobuy/stable'
    write(J/'PriorityExecutors.java',PRIORITY_EXECUTORS)
    write(J/'RelayLog.java',RELAY_LOG)
    write(J/'LanMasterRelayService.java',MASTER_RELAY)
    write(J/'LanChildRelayService.java',CHILD_RELAY)
    write(T/'PrimaryExecutionPriorityTest.java',TEST)

    ns=J/'ProductionNotificationService.java'
    text=read(ns)
    text=text.replace('import java.util.concurrent.Executors;\n','')
    text=text.replace('    private final ExecutorService executor = Executors.newSingleThreadExecutor();\n    private final ExecutorService earlyExitExecutor = Executors.newSingleThreadExecutor();',
'''    // P0/P1 broker work uses dedicated favorable-priority workers. Non-Multyfi work is background.\n    private final ExecutorService entryExecutor = PriorityExecutors.entrySingle("multyfi-entry");\n    private final ExecutorService earlyExitExecutor = PriorityExecutors.earlyExitSingle("multyfi-early-exit");\n    private final ExecutorService backgroundExecutor = PriorityExecutors.backgroundSingle("multyfi-background");''')
    text=text.replace('else executor.execute(work);','else entryExecutor.execute(work);')
    text=text.replace('executor.execute(() -> processResearch360(rawText, postTime));','backgroundExecutor.execute(() -> processResearch360(rawText, postTime));')
    text=text.replace('        executor.shutdownNow();','        entryExecutor.shutdownNow();\n        backgroundExecutor.shutdownNow();')
    marker='''            if (SignalParser.containsEarlyExitPhrase(rawText)) earlyExitExecutor.execute(work);\n            else entryExecutor.execute(work);\n            if (!AppRole.isChild(this)) {\n                LanMasterRelayService.publishFast(this, rawText, postTime);\n            }'''
    if marker not in text:
        raise RuntimeError('Primary-before-relay notification contract missing after patch')
    write(ns,text)

    sm=J/'StrategyMonitorService.java'
    text=read(sm)
    text=text.replace('prewarmExecutor = Executors.newSingleThreadScheduledExecutor();',
                      'prewarmExecutor = PriorityExecutors.backgroundScheduled("multyfi-position-prewarm");')
    write(sm,text)

    pa=J/'ProductionActivity.java'
    write(pa,read(pa).replace('2.4.3','2.4.4'))

for name in ('PriorityExecutors.java','RelayLog.java','LanMasterRelayService.java','LanChildRelayService.java'):
    a=read(ROOT/'app/src/main/java/com/suhas/multyfiautobuy/stable'/name)
    c=read(ROOT/'child/src/main/java/com/suhas/multyfiautobuy/stable'/name)
    assert a==c,(name,'role drift')

for module in ('app','child'):
    J=ROOT/module/'src/main/java/com/suhas/multyfiautobuy/stable'
    ns=read(J/'ProductionNotificationService.java')
    lm=read(J/'LanMasterRelayService.java')
    lc=read(J/'LanChildRelayService.java')
    assert 'MULTYFI EARLY EXIT DIRECT SUBMITTED' in ns
    assert 'MULTYFI EARLY EXIT API DISPATCH' in ns
    assert 'BUY API DISPATCH' in ns
    assert 'FastPositionCache.lookup' in ns
    assert 'entryExecutor.execute(work)' in ns
    assert ns.index('entryExecutor.execute(work)') < ns.index('LanMasterRelayService.publishFast')
    assert 'PriorityExecutors.earlyExitSingle' in ns
    assert 'PriorityExecutors.entrySingle' in ns
    assert 'PriorityExecutors.backgroundSingle' in ns
    assert 'PriorityExecutors.backgroundCached' in lm
    assert 'PriorityExecutors.backgroundSingle("multyfi-relay-broadcast")' in lm
    assert 'FALLBACK.execute(() -> publishAsync' in lm
    assert 'while(running)' in lm and 'MASTER LAN DISCOVERY RETRY' in lm
    assert 'registerNetworkCallback' in lc and 'onLinkPropertiesChanged' in lc
    assert 'enqueueRelayedMultyfi(sig.rawText,sig.sourcePostTime);' in lc
    assert lc.index('enqueueRelayedMultyfi(sig.rawText,sig.sourcePostTime);') < lc.index('LanRelayProtocol.ack(sig.eventId,recv)')
    assert 'PING|' in lc
    assert 'AppPrefs.log' not in lm
    assert 'AppPrefs.log' not in lc
    assert 'NET_PROFIT_TARGET = 0d' in read(J/'DailyRiskPolicy.java')
    assert 'GROSS_LOSS_LIMIT = 2000d' in read(J/'DailyRiskPolicy.java')

print('Applied Multyfi AutoBuy v2.4.4 primary-execution-priority + self-healing LAN relay patch')
