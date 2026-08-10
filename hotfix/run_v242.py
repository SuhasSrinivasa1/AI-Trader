#!/usr/bin/env python3
from pathlib import Path
import runpy

runpy.run_path("hotfix/run_v241_fix2.py", run_name="__main__")

ROOT = Path("android-stable")


def read(p):
    return Path(p).read_text(encoding="utf-8")


def write(p, text):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def rep(p, old, new, expected=1):
    p = Path(p)
    text = read(p)
    count = text.count(old)
    if count != expected:
        raise RuntimeError(f"Expected {expected} matches in {p}, found {count}: {old[:180]}")
    write(p, text.replace(old, new, expected))

# v2.4.2: keep all trading/risk behavior unchanged. Only improve the local
# MASTER<->CHILD transport when CHILD is connected to MASTER's Android hotspot
# while Surfshark/VPN is active. The relay is explicitly pinned to the physical
# Wi-Fi network; Groww traffic is untouched and continues to use the VPN route.

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
    private ExecutorService net;
    private volatile boolean running;
    private volatile Socket socket;
    private volatile String lastRoute="";

    static void ensureRunning(Context c){
        if(!AppRole.isChild(c) || !AppPrefs.isArmed(c)) return;
        try{c.startForegroundService(new Intent(c,LanChildRelayService.class));}
        catch(Exception e){AppPrefs.log(c,"CHILD LAN RELAY START FAILED",String.valueOf(e.getMessage()));}
    }

    @Override public void onCreate(){
        super.onCreate();
        if(!AppPrefs.isArmed(this)){ stopSelf(); return; }
        createChannel();
        startForeground(ID,note("Finding MASTER through physical Wi-Fi/hotspot"));
        running=true;
        net=Executors.newSingleThreadExecutor();
        net.execute(this::loop);
    }

    @Override public int onStartCommand(Intent i,int f,int id){
        if(!AppPrefs.isArmed(this)){ stopSelf(); return START_NOT_STICKY; }
        return START_STICKY;
    }

    @Override public void onDestroy(){
        running=false;
        RelayState.childDisconnected(this);
        try{if(socket!=null)socket.close();}catch(Exception ignored){}
        if(net!=null)net.shutdownNow();
        super.onDestroy();
    }

    private void loop(){
        while(running && AppPrefs.isArmed(this)){
            try{
                Network wifi=physicalWifiNetwork();
                if(wifi==null){
                    RelayState.childDisconnected(this);
                    update("No physical Wi-Fi/hotspot route — retrying");
                    sleep(750);
                    continue;
                }
                InetAddress gateway=wifiGateway(wifi);
                String route=gateway==null?"Wi-Fi gateway unknown":("Wi-Fi gateway "+gateway.getHostAddress());
                if(!route.equals(lastRoute)){
                    lastRoute=route;
                    AppPrefs.log(this,"CHILD LOCAL RELAY ROUTE",
                            route+" • relay sockets bypass VPN only for local MASTER connectivity; Groww remains on VPN.");
                }
                Host h=discover(wifi,gateway);
                if(h==null){
                    RelayState.childDisconnected(this);
                    update((gateway==null?"MASTER not found on Wi-Fi":
                            "MASTER not found at hotspot gateway "+gateway.getHostAddress())+" — retrying");
                    sleep(650);
                    continue;
                }
                connect(wifi,h);
            }catch(Exception e){
                RelayState.childDisconnected(this);
                update("Disconnected — local Wi-Fi retrying");
                sleep(500);
            }
        }
    }

    private Network physicalWifiNetwork(){
        try{
            ConnectivityManager cm=(ConnectivityManager)getSystemService(CONNECTIVITY_SERVICE);
            if(cm==null) return null;
            for(Network n:cm.getAllNetworks()){
                NetworkCapabilities caps=cm.getNetworkCapabilities(n);
                if(caps!=null && caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI)) return n;
            }
        }catch(Exception ignored){}
        return null;
    }

    private InetAddress wifiGateway(Network wifi){
        try{
            ConnectivityManager cm=(ConnectivityManager)getSystemService(CONNECTIVITY_SERVICE);
            LinkProperties lp=cm==null?null:cm.getLinkProperties(wifi);
            InetAddress fallback=null;
            if(lp!=null){
                for(RouteInfo route:lp.getRoutes()){
                    InetAddress g=route.getGateway();
                    if(!(g instanceof Inet4Address)) continue;
                    if(route.isDefaultRoute()) return g;
                    if(fallback==null) fallback=g;
                }
            }
            if(fallback!=null) return fallback;
        }catch(Exception ignored){}
        // API-26+ compatibility fallback for older LG Android Wi-Fi stacks.
        try{
            WifiManager wm=(WifiManager)getApplicationContext().getSystemService(WIFI_SERVICE);
            android.net.DhcpInfo d=wm==null?null:wm.getDhcpInfo();
            if(d!=null && d.gateway!=0){
                byte[] a=new byte[]{
                        (byte)(d.gateway & 0xff),
                        (byte)((d.gateway >> 8) & 0xff),
                        (byte)((d.gateway >> 16) & 0xff),
                        (byte)((d.gateway >> 24) & 0xff)};
                return InetAddress.getByAddress(a);
            }
        }catch(Exception ignored){}
        return null;
    }

    private Host discover(Network wifi, InetAddress gateway){
        String nonce=Long.toHexString(System.nanoTime());
        byte[] q=LanRelayProtocol.discover(nonce).getBytes(StandardCharsets.UTF_8);
        try(DatagramSocket d=new DatagramSocket(null)){
            d.setReuseAddress(true);
            d.bind(new InetSocketAddress(0));
            wifi.bindSocket(d);
            d.setBroadcast(true);
            d.setSoTimeout(700);
            LinkedHashSet<InetAddress> targets=new LinkedHashSet<>();
            // Highest priority: the Android hotspot's DHCP gateway is the MASTER phone.
            if(gateway!=null) targets.add(gateway);
            // Fallbacks retain compatibility with ordinary Wi-Fi/LAN use.
            targets.add(InetAddress.getByName("255.255.255.255"));
            try{
                Enumeration<NetworkInterface> en=NetworkInterface.getNetworkInterfaces();
                while(en.hasMoreElements()){
                    NetworkInterface ni=en.nextElement();
                    for(InterfaceAddress a:Collections.list(ni.getInterfaceAddresses()))
                        if(a.getBroadcast()!=null) targets.add(a.getBroadcast());
                }
            }catch(Exception ignored){}
            for(InetAddress a:targets){
                try{d.send(new DatagramPacket(q,q.length,a,LanRelayProtocol.UDP_PORT));}
                catch(Exception ignored){}
            }
            long end=System.currentTimeMillis()+700;
            byte[] buf=new byte[512];
            while(System.currentTimeMillis()<end){
                DatagramPacket p=new DatagramPacket(buf,buf.length);
                try{d.receive(p);}catch(SocketTimeoutException e){break;}
                String r=new String(p.getData(),p.getOffset(),p.getLength(),StandardCharsets.UTF_8);
                int port=LanRelayProtocol.validMasterReplyPort(r,nonce);
                if(port>0) return new Host(p.getAddress(),port);
            }
        }catch(Exception ignored){}
        return null;
    }

    private void connect(Network wifi,Host h)throws Exception{
        Socket s=new Socket();
        socket=s;
        wifi.bindSocket(s);
        s.connect(new InetSocketAddress(h.a,h.p),1500);
        s.setTcpNoDelay(true);
        s.setKeepAlive(true);
        PrintWriter w=new PrintWriter(new OutputStreamWriter(s.getOutputStream(),StandardCharsets.UTF_8),true);
        BufferedReader r=new BufferedReader(new InputStreamReader(s.getInputStream(),StandardCharsets.UTF_8));
        String device=Build.MANUFACTURER+"-"+Build.MODEL;
        w.println(LanRelayProtocol.hello(device,Long.toHexString(System.nanoTime())));
        RelayState.childConnected(this,h.a.getHostAddress(),-1);
        update("Connected to MASTER "+h.a.getHostAddress()+" via hotspot/Wi-Fi");
        AppPrefs.log(this,"CHILD CONNECTED TO MASTER",
                h.a.getHostAddress()+":"+h.p+" • physical Wi-Fi route pinned; VPN remains reserved for Groww.");
        String line;
        while(running && AppPrefs.isArmed(this) && (line=r.readLine())!=null){
            long recv=System.currentTimeMillis();
            try{
                LanRelayProtocol.Signal sig=LanRelayProtocol.parse(line);
                long latency=Math.max(0,recv-sig.masterSentAt);
                RelayState.childConnected(this,h.a.getHostAddress(),latency);
                update("MASTER connected • last relay "+latency+" ms");
                w.println(LanRelayProtocol.ack(sig.eventId,recv));
                AppPrefs.log(this,"MULTYFI SIGNAL RECEIVED FROM MASTER",
                        "LAN latency "+latency+" ms • event "+sig.eventId.substring(0,12));
                enqueueRelayedMultyfi(sig.rawText,sig.sourcePostTime);
            }catch(Exception e){
                AppPrefs.log(this,"CHILD RELAY PACKET REJECTED",String.valueOf(e.getMessage()));
            }
        }
        try{s.close();}catch(Exception ignored){}
    }

    private void createChannel(){
        NotificationManager n=(NotificationManager)getSystemService(NOTIFICATION_SERVICE);
        if(n!=null)n.createNotificationChannel(new NotificationChannel(CH,"Child LAN relay",NotificationManager.IMPORTANCE_LOW));
    }
    private Notification note(String t){
        return new Notification.Builder(this,CH).setSmallIcon(android.R.drawable.stat_notify_sync)
                .setContentTitle("Multyfi CHILD relay").setContentText(t).setOngoing(true).build();
    }
    private void update(String t){
        NotificationManager n=(NotificationManager)getSystemService(NOTIFICATION_SERVICE);
        if(n!=null)n.notify(ID,note(t));
    }
    private static void sleep(long ms){
        try{Thread.sleep(ms);}catch(InterruptedException e){Thread.currentThread().interrupt();}
    }
    static final class Host{
        final InetAddress a;final int p;
        Host(InetAddress a,int p){this.a=a;this.p=p;}
    }
}
'''

for module in ("app", "child"):
    gradle = ROOT / module / "build.gradle"
    rep(gradle, "versionCode 241", "versionCode 242")
    rep(gradle, "versionName '2.4.1'", "versionName '2.4.2'")
    java = ROOT / module / "src/main/java/com/suhas/multyfiautobuy/stable"
    write(java / "LanChildRelayService.java", CHILD_RELAY)
    activity = java / "ProductionActivity.java"
    write(activity, read(activity).replace("2.4.1", "2.4.2"))

# Make the disconnected CHILD status describe the actual recovery path.
for module in ("app", "child"):
    pa = ROOT / module / "src/main/java/com/suhas/multyfiautobuy/stable/ProductionActivity.java"
    text = read(pa)
    text = text.replace("● Master LAN relay: disconnected — auto-retrying",
                        "● Master LAN relay: disconnected — hotspot/Wi-Fi gateway auto-retrying")
    write(pa, text)

# Contract checks: the local relay is Wi-Fi pinned even while Surfshark is active.
for module in ("app", "child"):
    java = ROOT / module / "src/main/java/com/suhas/multyfiautobuy/stable/LanChildRelayService.java"
    text = read(java)
    assert "NetworkCapabilities.TRANSPORT_WIFI" in text
    assert "wifi.bindSocket(d)" in text
    assert "wifi.bindSocket(s)" in text
    assert "wifiGateway(wifi)" in text
    assert "targets.add(gateway)" in text
    assert "Groww remains on VPN" in text
    assert "!AppPrefs.isArmed(c)" in text

assert "versionCode 242" in read(ROOT / "app/build.gradle")
assert "versionCode 242" in read(ROOT / "child/build.gradle")
assert "GROSS_LOSS_LIMIT = 2000d" in read(ROOT / "app/src/main/java/com/suhas/multyfiautobuy/stable/DailyRiskPolicy.java")
assert "NET_PROFIT_TARGET = 5000d" in read(ROOT / "app/src/main/java/com/suhas/multyfiautobuy/stable/DailyRiskPolicy.java")
print("Applied Multyfi AutoBuy v2.4.2 physical-hotspot gateway relay fix")
