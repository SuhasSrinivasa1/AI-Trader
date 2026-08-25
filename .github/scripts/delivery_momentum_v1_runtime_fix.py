from pathlib import Path

svc = Path('delivery-momentum/app/src/main/java/com/suhas/nsedeliverymomentum/DeliveryMomentumService.java')
s = svc.read_text()

repls = [
    (
        'createChannel();startForeground(901,notification("Delivery Momentum scanner starting"));universe=new UniverseStore().load();scheduler.scheduleWithFixedDelay(this::safeScan,2,60,TimeUnit.SECONDS);',
        'createChannel();startForeground(901,notification("Delivery Momentum scanner starting"));universe=null;scheduler.scheduleWithFixedDelay(this::safeScan,2,60,TimeUnit.SECONDS);'
    ),
    (
        'List<String> syms=universe.symbols;Map<String,GrowwClient.Ohlc> snap=new HashMap<>();',
        'if(universe==null)universe=new UniverseStore().load();List<String> syms=universe.symbols;Map<String,GrowwClient.Ohlc> snap=new HashMap<>();'
    ),
    (
        'double base=baselineVol.computeIfAbsent(s,k->computeBaseline(k,now));String sector=universe.sector.getOrDefault(s,"UNKNOWN");double sectorGain=median(sectorVals.getOrDefault(sector,Collections.emptyList()));double raw=q.imbalance(),prev=lastFlow.getOrDefault(s,raw),flow=0.65*raw+0.35*prev;lastFlow.put(s,flow);',
        'int baselineElapsed=(int)Duration.between(now.withHour(9).withMinute(15),now).toMinutes();int baselineBucket=Math.max(0,baselineElapsed/15);String baselineKey=GrowwClient.sessionDay()+"_"+s+"_"+baselineBucket;double base=baselineVol.computeIfAbsent(baselineKey,k->computeBaseline(s,now));String sector=universe.sector.getOrDefault(s,"UNKNOWN");double sectorGain=median(sectorVals.getOrDefault(sector,Collections.emptyList()));double raw=q.imbalance();String flowKey=GrowwClient.sessionDay()+"_"+s;double prev=lastFlow.getOrDefault(flowKey,raw),flow=0.65*raw+0.35*prev;lastFlow.put(flowKey,flow);'
    ),
    (
        'ZonedDateTime start=now.minusDays(21).withHour(9).withMinute(15).withSecond(0).withNano(0);',
        'ZonedDateTime start=now.minusDays(12).withHour(9).withMinute(15).withSecond(0).withNano(0);'
    ),
    (
        'if(!"BUY".equals(c.state)||c.score<82||c.confidence<80||c.expected<1.10)continue;',
        'if(!"BUY".equals(c.state))continue;'
    ),
]

for old, new in repls:
    if old not in s:
        raise SystemExit('Missing DeliveryMomentumService patch anchor: '+old[:120])
    s = s.replace(old, new, 1)
svc.write_text(s)

boot = Path('delivery-momentum/app/src/main/java/com/suhas/nsedeliverymomentum/BootReceiver.java')
b = boot.read_text()
old = 'Intent s = new Intent(c, DeliveryMomentumService.class);'
new = 'new SecretStore(c).putBool("live", false);\n        Intent s = new Intent(c, DeliveryMomentumService.class);'
if old not in b:
    raise SystemExit('Missing BootReceiver anchor')
boot.write_text(b.replace(old, new, 1))

learn = Path('delivery-momentum/app/src/main/java/com/suhas/nsedeliverymomentum/LearningStore.java')
l = learn.read_text()
old = 'return n>=5?(h+2.0)/(n+4.0):0.65;'
new = 'return n>=5?(h+2.0)/(n+4.0):0.50;'
if old not in l:
    raise SystemExit('Missing LearningStore prior anchor')
learn.write_text(l.replace(old, new, 1))

math = Path('delivery-momentum/app/src/main/java/com/suhas/nsedeliverymomentum/MomentumMath.java')
m = math.read_text()
old = 'double prior=historicalHitRate>0?historicalHitRate:0.65;'
new = 'double prior=historicalHitRate>0?historicalHitRate:0.50;'
if old not in m:
    raise SystemExit('Missing MomentumMath prior anchor')
m = m.replace(old, new, 1)
old = '(Math.min(rem,180)/60.0)'
new = '(rem/60.0)'
if old not in m:
    raise SystemExit('Missing fixed 180-minute projection cap anchor')
m = m.replace(old, new, 1)
math.write_text(m)

# Guard the exact problems this patch fixes.
assert 'universe=null' in s
assert 'if(universe==null)universe=new UniverseStore().load()' in s
assert 'minusDays(12)' in s
assert 'baselineBucket' in s
assert 'flowKey=GrowwClient.sessionDay()+"_"+s' in s
assert 'c.score<82' not in s
assert 'putBool("live", false)' in boot.read_text()
assert ':0.50;' in learn.read_text()
assert 'Math.min(rem,180)' not in math.read_text()
assert '(rem/60.0)' in math.read_text()

print('Delivery Momentum v1 runtime reliability fixes applied')
