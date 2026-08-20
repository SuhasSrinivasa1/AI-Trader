from pathlib import Path
import re

ROOT=Path('unified-scanner/app/src/main/java/com/suhas/nseunifiedscanner')
TEST=Path('unified-scanner/app/src/test/java/com/suhas/nseunifiedscanner')
sp=ROOT/'UnifiedService.java'; mp=ROOT/'MainActivity.java'; gp=Path('unified-scanner/app/build.gradle')

def must(path, old, new):
    p=Path(path); s=p.read_text()
    if old not in s: raise SystemExit(f'v1.6.2 anchor missing in {p}: {old[:180]!r}')
    p.write_text(s.replace(old,new,1))

def opt(path, old, new):
    p=Path(path); s=p.read_text()
    if old in s: p.write_text(s.replace(old,new,1))

# Pure deterministic fixed-capital helper and tests.
(ROOT/'FixedCapitalLogic.java').write_text('''package com.suhas.nseunifiedscanner;\n\nfinal class FixedCapitalLogic {\n    static final double TRADE_CAPITAL=10000.0;\n    static final double NET_TARGET_PCT=0.003;\n    static final double SLIPPAGE_RESERVE_PCT=0.0006;\n    private FixedCapitalLogic(){}\n    static int quantity(double price){if(!(price>0))return 0;return Math.max(0,(int)Math.floor(TRADE_CAPITAL/price));}\n    static double deployed(int qty,double price){return Math.max(0,qty)*Math.max(0,price);}\n    static double targetNetRupees(int qty,double price){return deployed(qty,price)*NET_TARGET_PCT;}\n}\n''')
(TEST/'FixedCapitalLogicTest.java').write_text('''package com.suhas.nseunifiedscanner;\nimport org.junit.Test;\nimport static org.junit.Assert.*;\npublic class FixedCapitalLogicTest {\n @Test public void capsNotionalAtTenThousand(){int q=FixedCapitalLogic.quantity(269.60);assertEquals(37,q);assertTrue(FixedCapitalLogic.deployed(q,269.60)<=10000.0);assertTrue(FixedCapitalLogic.deployed(q+1,269.60)>10000.0);}\n @Test public void targetIsPointThreePercentOfDeployed(){int q=FixedCapitalLogic.quantity(100.0);assertEquals(100,q);assertEquals(30.0,FixedCapitalLogic.targetNetRupees(q,100.0),0.0001);}\n @Test public void expensiveStockCanStillBuyOneIfWithinCap(){assertEquals(1,FixedCapitalLogic.quantity(9999.0));assertEquals(0,FixedCapitalLogic.quantity(10001.0));}\n}\n''')

# Fixed test-capital execution. This deliberately caps TRADE VALUE, not merely MIS margin,
# so leverage can never turn the ₹10k test budget into a larger market exposure.
must(sp,
'''    private static final int NOTIFY_ID=27101; private static final String CHANNEL="nse_scanner_live";\n''',
'''    private static final int NOTIFY_ID=27101; private static final String CHANNEL="nse_scanner_live";\n    private static final double FIXED_TRADE_CAPITAL=FixedCapitalLogic.TRADE_CAPITAL;\n''')

must(sp,
'''            double limit=GrowwApi.roundToTick(Math.min(rec.entry*1.0020,ltp*1.0006),rec.tick,true);\n            GrowwApi.Result<GrowwApi.Margin> mr=GrowwApi.availableMargin(token);if(!mr.ok){setStatus("BUY blocked • "+mr.error);return;}\n            double use=Math.max(0.50,Math.min(1.00,prefs().getFloat("capital_use",0.98f)));double budget=mr.value.misAvailable*use;\n            int qty=maxQuantity(token,rec.symbol,limit,budget);if(qty<1){setStatus("BUY blocked • insufficient MIS margin");return;}\n            String ref=GrowwApi.reference("UB",rec.symbol);GrowwApi.Result<GrowwApi.Order> br=GrowwApi.placeLimitBuy(token,rec.symbol,qty,limit,ref);if(!br.ok){setStatus("BUY failed • "+br.error);learning.audit("ORDER",rec.symbol+" BUY failed: "+br.error);return;}\n            setStatus(rec.symbol+" BUY sent • reconciling fill");GrowwApi.Order fill=null;\n''',
'''            double limit=GrowwApi.roundToTick(Math.min(rec.entry*1.0020,ltp*1.0006),rec.tick,true);\n            GrowwApi.Result<GrowwApi.Margin> mr=GrowwApi.availableMargin(token);if(!mr.ok){setStatus("BUY blocked • "+mr.error);return;}\n            int qty=FixedCapitalLogic.quantity(limit);if(qty<1){setStatus("BUY blocked • stock price exceeds fixed ₹10,000 test capital");return;}\n            double plannedNotional=FixedCapitalLogic.deployed(qty,limit);\n            GrowwApi.Result<Double> req=GrowwApi.requiredMisMargin(token,rec.symbol,qty,limit);if(!req.ok){setStatus("BUY blocked • margin check failed: "+req.error);return;}\n            if(req.value>mr.value.misAvailable){setStatus("BUY blocked • available MIS margin is below requirement for ₹10,000 test trade");return;}\n            String ref=GrowwApi.reference("UB",rec.symbol);GrowwApi.Result<GrowwApi.Order> br=GrowwApi.placeLimitBuy(token,rec.symbol,qty,limit,ref);if(!br.ok){setStatus("BUY failed • "+br.error);learning.audit("ORDER",rec.symbol+" BUY failed: "+br.error);return;}\n            setStatus(rec.symbol+" BUY sent • "+qty+" shares • planned ₹"+money(plannedNotional)+" • reconciling fill");GrowwApi.Order fill=null;\n''')

# Guarantee the live target uses +0.30% NET plus the existing slippage reserve.
for old in [
    'ChargeModel.requiredSellPrice(fillPrice,filled,0.005,0.0007,rec.tick)',
    'ChargeModel.requiredSellPrice(fillPrice,filled,0.003,0.0006,rec.tick)']:
    opt(sp,old,'ChargeModel.requiredSellPrice(fillPrice,filled,FixedCapitalLogic.NET_TARGET_PCT,FixedCapitalLogic.SLIPPAGE_RESERVE_PCT,rec.tick)')

opt(sp,
'''learning.audit("ORDER",rec.symbol+" fill "+filled+" @ ₹"+money(fillPrice)+" • target ₹"+money(target)+" • stop ₹"+money(stop)+" • "+t.mode);''',
'''learning.audit("ORDER",rec.symbol+" fill "+filled+" @ ₹"+money(fillPrice)+" • deployed ₹"+money(filled*fillPrice)+" • target ₹"+money(target)+" • stop ₹"+money(stop)+" • expected net ≥₹"+money(FixedCapitalLogic.targetNetRupees(filled,fillPrice))+" • "+t.mode);''')

# UI: remove percentage-of-wallet capital control and make ₹10k test mode explicit.
s=mp.read_text()
s=re.sub(r'EditText capital=field\("Capital use % \(50–100\)".*?box\.addView\(capital\);', '', s, count=1)
s=s.replace('Credentials are encrypted with Android Keystore. Scanner can run read-only when LIVE is off. BUY requires the configured public IP to match exactly. Connection Health turns green only after actual API/feed/IP checks.', 'Credentials are encrypted with Android Keystore. TEST MODE is fixed at ₹10,000 trade value per BUY-qualified prediction, regardless of wallet balance. BUY requires the configured public IP to match exactly. Connection Health turns green only after actual API/feed/IP checks.')
s=re.sub(r'double c=Double\.parseDouble\(capital\.getText\(\)\.toString\(\)\);if\(c<50\|\|c>100\)throw new Exception\(\);prefs\(\)\.edit\(\)\.putFloat\("capital_use",\(float\)\(c/100\.0\)\)\.apply\(\);', '', s, count=1)
s=s.replace('BUY • MAX SAFE MIS','BUY • ₹10K TEST')
s=s.replace('Capital use % must be between 50 and 100','Settings saved')
# Add planned quantity/net information immediately below the net-objective line.
needle='c.addView(space(8));c.addView(txt("NET OBJECTIVE +0.30% after estimated Groww/NSE charges • actual target recalculated from fill + quantity",11,ACCENT,true));'
if needle in s:
    repl=needle+'int plannedQty=FixedCapitalLogic.quantity(r.entry);double plannedCapital=FixedCapitalLogic.deployed(plannedQty,r.entry);double plannedNet=FixedCapitalLogic.targetNetRupees(plannedQty,r.entry);c.addView(txt("FIXED TEST CAPITAL ₹10,000 • planned qty "+plannedQty+" • deploy ~₹"+money(plannedCapital)+" • net objective ≥₹"+money(plannedNet),11,GREEN,true));'
    s=s.replace(needle,repl,1)
else:
    # tolerate minor v1.6 wording changes
    anchor='c.addView(space(8));'
    idx=s.find('NET OBJECTIVE +0.30%')
    if idx<0: raise SystemExit('v1.6.2 MainActivity net objective anchor missing')
    # insert after the containing c.addView line
    end=s.find('\n',idx)
    if end<0:end=len(s)
    s=s[:end+1]+'            int plannedQty=FixedCapitalLogic.quantity(r.entry);double plannedCapital=FixedCapitalLogic.deployed(plannedQty,r.entry);double plannedNet=FixedCapitalLogic.targetNetRupees(plannedQty,r.entry);c.addView(txt("FIXED TEST CAPITAL ₹10,000 • planned qty "+plannedQty+" • deploy ~₹"+money(plannedCapital)+" • net objective ≥₹"+money(plannedNet),11,GREEN,true));\n'+s[end+1:]

s=s.replace('v1.6.1 • standalone package com.suhas.nseunifiedscanner','v1.6.2 • ₹10K fixed test capital • standalone package com.suhas.nseunifiedscanner')
mp.write_text(s)

# Version bump.
s=gp.read_text()
s=s.replace("versionCode 161\n        versionName '1.6.1'","versionCode 162\n        versionName '1.6.2'")
gp.write_text(s)

print('v1.6.2 fixed ₹10,000 notional test-capital patch applied')
