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

# Guard the exact problems this patch fixes.
assert 'universe=null' in s
assert 'if(universe==null)universe=new UniverseStore().load()' in s
assert 'minusDays(12)' in s
assert 'baselineBucket' in s
assert 'flowKey=GrowwClient.sessionDay()+"_"+s' in s
assert 'c.score<82' not in s

print('Delivery Momentum v1 runtime reliability fixes applied')
