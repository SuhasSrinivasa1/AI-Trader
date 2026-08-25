from pathlib import Path

# Fix live OHLC parsing. Groww returns JSON objects; the prior parser converted each
# object to a string and then used a regex that did not tolerate quoted JSON keys,
# causing open/close to become 0 and market breadth to remain stuck at 0%.
g = Path('delivery-momentum/app/src/main/java/com/suhas/nsedeliverymomentum/GrowwClient.java')
s = g.read_text()
old_call = 'out.put(s,parseOhlc(String.valueOf(p.opt(k))));'
new_call = 'out.put(s,parseOhlc(p.opt(k)));'
if old_call not in s:
    raise SystemExit('OHLC parse call anchor not found')
s = s.replace(old_call, new_call)
old_parser = 'private static Ohlc parseOhlc(String s){double o=num(s,"open"),h=num(s,"high"),l=num(s,"low"),c=num(s,"close");return new Ohlc(o,h,l,c);}'
new_parser = '''private static Ohlc parseOhlc(Object raw){
        try{
            JSONObject x;
            if(raw instanceof JSONObject)x=(JSONObject)raw;
            else{x=new JSONObject(String.valueOf(raw));}
            double o=x.optDouble("open",0),h=x.optDouble("high",0),l=x.optDouble("low",0);
            double c=x.optDouble("close",x.optDouble("last_price",x.optDouble("ltp",0)));
            return new Ohlc(o,h,l,c);
        }catch(Exception e){
            String z=String.valueOf(raw);
            double o=num(z,"open"),h=num(z,"high"),l=num(z,"low"),c=num(z,"close");
            return new Ohlc(o,h,l,c);
        }
    }'''
if old_parser not in s:
    raise SystemExit('OHLC parser anchor not found')
s = s.replace(old_parser, new_parser)
g.write_text(s)

svc = Path('delivery-momentum/app/src/main/java/com/suhas/nsedeliverymomentum/DeliveryMomentumService.java')
t = svc.read_text()
old_breadth = 'double marketGain=median(allGains);double breadth=valid>0?(double)pos/valid:0;'
new_breadth = 'double marketGain=median(allGains);double breadth=valid>0?(double)pos/valid:0;if(valid<Math.max(20,snap.size()/4)){lastStatus=String.format(Locale.US,"OHLC DATA INVALID • %d/%d valid rows • scanner paused",valid,snap.size());broadcast();return;}'
if old_breadth not in t:
    raise SystemExit('breadth anchor not found')
t = t.replace(old_breadth, new_breadth)
old_fast = 'if(System.currentTimeMillis()-lastDeep<150000){lastStatus=String.format(Locale.US,"FAST SCAN %d stocks • breadth %.0f%% • deep momentum refresh in progress",snap.size(),breadth*100);broadcast();return;}lastDeep=System.currentTimeMillis();'
new_fast = 'long sinceDeep=System.currentTimeMillis()-lastDeep;if(sinceDeep<90000){long next=Math.max(0,(90000-sinceDeep)/1000);lastStatus=String.format(Locale.US,"FAST SCAN %d • valid %d • breadth %.0f%% • movers %d • next deep scan %ds",snap.size(),valid,breadth*100,movers.size(),next);broadcast();return;}lastDeep=System.currentTimeMillis();'
if old_fast not in t:
    raise SystemExit('fast scan anchor not found')
t = t.replace(old_fast, new_fast)
old_done = 'lastStatus=String.format(Locale.US,"NSE DELIVERY MOMENTUM • %d scanned • %d deep • %d BUY-qualified • breadth %.0f%%",snap.size(),out.size(),q,breadth*100);'
new_done = 'lastStatus=String.format(Locale.US,"SCAN COMPLETE • %d/%d valid • breadth %.0f%% • movers %d • deep %d • BUY %d • %s",valid,snap.size(),breadth*100,movers.size(),out.size(),q,now.toLocalTime().withNano(0));'
if old_done not in t:
    raise SystemExit('scan complete anchor not found')
t = t.replace(old_done, new_done)
svc.write_text(t)

# v1.1.1 bug-fix version.
b = Path('delivery-momentum/app/build.gradle')
u = b.read_text()
u = u.replace('versionCode 110','versionCode 111').replace("versionName '1.1.0'","versionName '1.1.1'")
b.write_text(u)

# Assertions make the CI fail if any key fix is not actually present.
assert 'parseOhlc(p.opt(k))' in g.read_text()
assert 'OHLC DATA INVALID' in svc.read_text()
assert 'valid %d' in svc.read_text()
assert 'next deep scan %ds' in svc.read_text()
assert "versionName '1.1.1'" in b.read_text()
print('Delivery Momentum v1.1.1 OHLC + scanner health fix applied')
