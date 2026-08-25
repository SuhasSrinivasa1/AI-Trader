from pathlib import Path

# NSE Delivery Momentum v1.2.0
# Broad discovery scans the official NSE CASH/EQ master, while deep analysis remains
# liquidity/quality controlled so thin names cannot dominate final recommendations.

universe = Path('delivery-momentum/app/src/main/java/com/suhas/nsedeliverymomentum/UniverseStore.java')
universe.write_text(r'''package com.suhas.nsedeliverymomentum;

import java.io.*;import java.net.*;import java.nio.charset.StandardCharsets;import java.util.*;

final class UniverseStore {
    static final String ALL_EQ_URL="https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv";
    static final String NIFTY500_URL="https://nsearchives.nseindia.com/content/indices/ind_nifty500list.csv";
    static final class Universe {
        final List<String> symbols=new ArrayList<>();
        final Map<String,String> sector=new HashMap<>();
        boolean allNse=false;
        String source="FALLBACK";
    }
    Universe load(){
        Universe u=new Universe();
        // Sector enrichment is deliberately independent from discovery. NIFTY500 membership
        // is useful as a quality signal, but it must not limit the broad NSE search.
        loadNifty500Sectors(u.sector);
        List<String> all=loadAllEq();
        LinkedHashSet<String> set=new LinkedHashSet<>();
        if(all.size()>=800){set.addAll(all);u.allNse=true;u.source="NSE EQUITY_L";}
        else {set.addAll(u.sector.keySet());u.source="NIFTY500 FALLBACK";}
        for(String s:FALLBACK)set.add(s);
        set.add("GROWW");
        u.symbols.addAll(set);
        return u;
    }
    private static List<String> loadAllEq(){
        List<String> out=new ArrayList<>();
        try{
            HttpURLConnection c=open(ALL_EQ_URL);
            try(BufferedReader b=new BufferedReader(new InputStreamReader(c.getInputStream(),StandardCharsets.UTF_8))){
                String head=b.readLine();if(head==null)throw new IOException("empty equity master");
                String[] h=parse(head);int si=index(h,"SYMBOL"),seri=index(h,"SERIES");
                String l;while((l=b.readLine())!=null){String[] x=parse(l);if(si<0||si>=x.length)continue;String series=seri>=0&&seri<x.length?clean(x[seri]):"EQ";if(!"EQ".equalsIgnoreCase(series))continue;String s=clean(x[si]);if(!s.isEmpty())out.add(s);}
            }
        }catch(Exception ignored){}
        return out;
    }
    private static void loadNifty500Sectors(Map<String,String> sector){
        try{
            HttpURLConnection c=open(NIFTY500_URL);
            try(BufferedReader b=new BufferedReader(new InputStreamReader(c.getInputStream(),StandardCharsets.UTF_8))){
                String head=b.readLine();if(head==null)return;String[] h=parse(head);int si=index(h,"Symbol"),ii=index(h,"Industry");String l;
                while((l=b.readLine())!=null){String[] x=parse(l);if(si>=0&&si<x.length){String s=clean(x[si]);if(!s.isEmpty())sector.put(s,ii>=0&&ii<x.length?clean(x[ii]):"UNKNOWN");}}
            }
        }catch(Exception ignored){}
    }
    private static HttpURLConnection open(String url)throws Exception{HttpURLConnection c=(HttpURLConnection)new URL(url).openConnection();c.setConnectTimeout(8000);c.setReadTimeout(12000);c.setRequestProperty("User-Agent","Mozilla/5.0 (Android) NSEDeliveryMomentum/1.2");c.setRequestProperty("Accept","text/csv,*/*");return c;}
    private static int index(String[] h,String n){for(int i=0;i<h.length;i++)if(clean(h[i]).equalsIgnoreCase(n))return i;return -1;}
    private static String clean(String s){return s==null?"":s.replace("\"","").trim();}
    private static String[] parse(String l){List<String>a=new ArrayList<>();StringBuilder s=new StringBuilder();boolean q=false;for(char c:l.toCharArray()){if(c=='\"')q=!q;else if(c==','&&!q){a.add(s.toString());s.setLength(0);}else s.append(c);}a.add(s.toString());return a.toArray(new String[0]);}
    static final String[] FALLBACK={"RELIANCE","HDFCBANK","ICICIBANK","SBIN","BHARTIARTL","INFY","TCS","LT","AXISBANK","KOTAKBANK","MARUTI","M&M","SUNPHARMA","BAJFINANCE","TITAN","HINDUNILVR","ITC","NTPC","ONGC","POWERGRID","ADANIENT","ADANIPORTS","TATASTEEL","JSWSTEEL","HINDALCO","COALINDIA","BEL","HAL","TRENT","ETERNAL","GROWW","BSE","CDSL","ANGELONE","DMART","DLF","LODHA","INDIGO","JIOFIN","PFC","RECLTD","IRFC","IRCTC","VEDL","HCLTECH","TECHM","WIPRO","CIPLA","DRREDDY","DIVISLAB","APOLLOHOSP","MAXHEALTH","FORTIS","ASTRAL","POLYCAB","DIXON","KAYNES","CGPOWER","ABB","SIEMENS","BHEL","TATAPOWER","ADANIPOWER","TORNTPOWER","JSWENERGY","NHPC","IOC","BPCL","HINDPETRO","GAIL","BANKBARODA","CANBK","PNB","IDFCFIRSTB","FEDERALBNK","INDUSINDBK","BAJAJFINSV","SBILIFE","HDFCLIFE","ICICIPRULI","NAUKRI","PAYTM","NYKAA","SWIGGY","DELHIVERY","INDHOTEL","EICHERMOT","TVSMOTOR","BAJAJ-AUTO","HEROMOTOCO","ASHOKLEY","TATACONSUM","BRITANNIA","NESTLEIND","VBL","UNITDSPR","PIDILITIND","ASIANPAINT","BERGEPAINT","SRF","UPL","PIIND","DEEPAKNTR","SOLARINDS","CUMMINSIND","THERMAX","SUPREMEIND","APLAPOLLO","JINDALSTEL","SAIL","NMDC","HINDZINC","GRASIM","ULTRACEMCO","AMBUJACEM","SHREECEM"};
}
''')

svc = Path('delivery-momentum/app/src/main/java/com/suhas/nsedeliverymomentum/DeliveryMomentumService.java')
s = svc.read_text()

# Slightly slower batching protects broker/API rate limits while still completing a 2k+ symbol
# broad scan quickly enough for session-momentum discovery.
s = s.replace('sleep(120);', 'sleep(220);')

old = '''List<Map.Entry<String,GrowwClient.Ohlc>> movers=new ArrayList<>(snap.entrySet());movers.removeIf(e->e.getValue().open<=0||e.getValue().last<=0||((e.getValue().last/e.getValue().open-1)*100)<0.35||((e.getValue().last/e.getValue().open-1)*100)>7.0);movers.sort((a,b)->Double.compare((b.getValue().last/b.getValue().open),(a.getValue().last/a.getValue().open)));LinkedHashMap<String,Map.Entry<String,GrowwClient.Ohlc>> shortlist=new LinkedHashMap<>();for(int i=0;i<Math.min(22,movers.size());i++)shortlist.put(movers.get(i).getKey(),movers.get(i));Set<String> core=new HashSet<>(Arrays.asList(UniverseStore.FALLBACK));for(Map.Entry<String,GrowwClient.Ohlc> e:movers){if(shortlist.size()>=34)break;if(core.contains(e.getKey()))shortlist.put(e.getKey(),e);}movers=new ArrayList<>(shortlist.values());'''
new = '''List<Map.Entry<String,GrowwClient.Ohlc>> movers=new ArrayList<>(snap.entrySet());movers.removeIf(e->e.getValue().open<=0||e.getValue().last<20||((e.getValue().last/e.getValue().open-1)*100)<0.20||((e.getValue().last/e.getValue().open-1)*100)>10.0);movers.sort((a,b)->Double.compare((b.getValue().last/b.getValue().open),(a.getValue().last/a.getValue().open)));int broadMoverCount=movers.size();LinkedHashMap<String,Map.Entry<String,GrowwClient.Ohlc>> shortlist=new LinkedHashMap<>();for(int i=0;i<Math.min(45,movers.size());i++)shortlist.put(movers.get(i).getKey(),movers.get(i));int mappedAdded=0;for(Map.Entry<String,GrowwClient.Ohlc> e:movers){if(mappedAdded>=35)break;if(!"UNKNOWN".equals(universe.sector.getOrDefault(e.getKey(),"UNKNOWN"))&&!shortlist.containsKey(e.getKey())){shortlist.put(e.getKey(),e);mappedAdded++;}}Set<String> core=new HashSet<>(Arrays.asList(UniverseStore.FALLBACK));for(Map.Entry<String,GrowwClient.Ohlc> e:movers){if(shortlist.size()>=90)break;if(core.contains(e.getKey()))shortlist.put(e.getKey(),e);}movers=new ArrayList<>(shortlist.values());'''
if old not in s: raise SystemExit('v1.2 mover block anchor not found')
s = s.replace(old,new)

old_fast = 'long sinceDeep=System.currentTimeMillis()-lastDeep;if(sinceDeep<90000){long next=Math.max(0,(90000-sinceDeep)/1000);lastStatus=String.format(Locale.US,"FAST SCAN %d • valid %d • breadth %.0f%% • movers %d • next deep scan %ds",snap.size(),valid,breadth*100,movers.size(),next);broadcast();return;}lastDeep=System.currentTimeMillis();List<Candidate> out=new ArrayList<>();int max=Math.min(34,movers.size());'
new_fast = 'long sinceDeep=System.currentTimeMillis()-lastDeep;if(sinceDeep<90000){long next=Math.max(0,(90000-sinceDeep)/1000);lastStatus=String.format(Locale.US,"ALL-NSE SCAN • %d/%d valid • breadth %.0f%% • broad movers %d • deep pool %d • next %ds",valid,syms.size(),breadth*100,broadMoverCount,movers.size(),next);broadcast();return;}lastDeep=System.currentTimeMillis();List<Candidate> out=new ArrayList<>();int max=Math.min(90,movers.size());'
if old_fast not in s: raise SystemExit('v1.2 fast-status anchor not found')
s = s.replace(old_fast,new_fast)

s = s.replace('lastCandidates=out.subList(0,Math.min(7,out.size()));','lastCandidates=out.subList(0,Math.min(10,out.size()));')
old_done = 'lastStatus=String.format(Locale.US,"SCAN COMPLETE • %d/%d valid • breadth %.0f%% • movers %d • deep %d • BUY %d • %s",valid,snap.size(),breadth*100,movers.size(),out.size(),q,now.toLocalTime().withNano(0));'
new_done = 'lastStatus=String.format(Locale.US,"ALL-NSE COMPLETE • %d/%d valid • breadth %.0f%% • broad movers %d • deep %d/%d • BUY %d • %s",valid,syms.size(),breadth*100,broadMoverCount,out.size(),max,q,now.toLocalTime().withNano(0));'
if old_done not in s: raise SystemExit('v1.2 completion anchor not found')
s = s.replace(old_done,new_done)

# Early quality screening occurs immediately after the quote call. This lets the app discover
# every EQ stock without spending candle/history requests on illiquid names.
old_eval = 'GrowwClient.ApiResult<GrowwClient.Quote> qr=api.quote(s);if(!qr.ok)return null;GrowwClient.Quote q=qr.value;if(q.ltp<=0)return null;ZonedDateTime open=now.withHour(9).withMinute(15).withSecond(0).withNano(0);'
new_eval = 'GrowwClient.ApiResult<GrowwClient.Quote> qr=api.quote(s);if(!qr.ok)return null;GrowwClient.Quote q=qr.value;if(q.ltp<=0)return null;int elapsedNow=(int)Duration.between(now.withHour(9).withMinute(15),now).toMinutes();double probeTurn=Math.max(3,45.0*Math.max(1,elapsedNow)/375.0);boolean mapped=!"UNKNOWN".equals(universe.sector.getOrDefault(s,"UNKNOWN"));if(q.turnoverCr()<probeTurn)return null;if(q.marketCap>0&&q.marketCap<20_000_000_000L&&!mapped)return null;if(q.spreadPct()<90&&q.spreadPct()>0.40)return null;ZonedDateTime open=now.withHour(9).withMinute(15).withSecond(0).withNano(0);'
if old_eval not in s: raise SystemExit('v1.2 evaluate anchor not found')
s = s.replace(old_eval,new_eval)

# Keep the final recommendation gate stricter than the discovery probe.
s = s.replace('double minTurn=Math.max(8,80.0*Math.max(1,elapsed)/375.0);','double minTurn=Math.max(6,65.0*Math.max(1,elapsed)/375.0);')
s = s.replace('if(q.marketCap>0&&q.marketCap<50_000_000_000L){','if(q.marketCap>0&&q.marketCap<50_000_000_000L&&!mapped){')
svc.write_text(s)

main = Path('delivery-momentum/app/src/main/java/com/suhas/nsedeliverymomentum/MainActivity.java')
m = main.read_text()
m = m.replace('Sustained cash-equity continuation','All-NSE sustained cash-equity continuation')
m = m.replace('Find liquid NSE stocks that are already proving strength and still have room to continue through the session.','Scan the full NSE CASH/EQ universe, then promote only liquid stocks that are proving sustained strength and still have room to continue.')
m = m.replace('STRATEGY  •  SUSTAINED CONTINUATION','STRATEGY  •  ALL-NSE DISCOVERY → QUALITY CONTINUATION')
m = m.replace('The strongest candidates stay visible even while they are still confirming. BUY means the full continuation test has passed.','Every NSE CASH/EQ stock enters broad discovery. Only liquid, quality-controlled names reach deep ranking; BUY means the full continuation test has passed.')
m = m.replace('DELIVERY ONLY  •  NSE CASH EQ  •  NO MIS / F&O  •  NO AUTO-SELL','DELIVERY ONLY  •  ALL NSE CASH EQ DISCOVERY  •  NO MIS / F&O  •  NO AUTO-SELL')
m = m.replace('SCANNING THE NSE','SCANNING ALL NSE CASH/EQ')
m = m.replace('No deep candidate has cleared the ranking stage yet. This does not mean the scanner is idle — it is continuously comparing trend quality, volume, VWAP, relative strength and order flow.','Broad discovery is scanning the full NSE EQ master. Liquid movers are promoted into deeper trend, volume, VWAP, relative-strength and order-flow analysis.')
main.write_text(m)

b = Path('delivery-momentum/app/build.gradle')
g = b.read_text()
g = g.replace('versionCode 111','versionCode 120').replace("versionName '1.1.1'","versionName '1.2.0'")
b.write_text(g)

assert 'ALL_EQ_URL' in universe.read_text()
assert 'all.size()>=800' in universe.read_text()
assert 'broadMoverCount' in svc.read_text()
assert 'Math.min(90,movers.size())' in svc.read_text()
assert 'Math.min(10,out.size())' in svc.read_text()
assert 'ALL-NSE COMPLETE' in svc.read_text()
assert 'ALL-NSE DISCOVERY' in main.read_text()
assert "versionName '1.2.0'" in b.read_text()
print('Delivery Momentum v1.2.0 ALL-NSE discovery patch applied')
