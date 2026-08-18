from pathlib import Path
ROOT=Path('unified-scanner/app/src/main/java/com/suhas/nseunifiedscanner')

def rep(path,old,new):
    p=Path(path);s=p.read_text()
    if old not in s: raise SystemExit(f'missing v1.3 tail anchor in {p}: {old[:120]!r}')
    p.write_text(s.replace(old,new,1))

def opt(path,old,new):
    p=Path(path);s=p.read_text()
    if old in s:p.write_text(s.replace(old,new,1))

mp=ROOT/'MainActivity.java';up=ROOT/'UnifiedService.java';gp=Path('unified-scanner/app/build.gradle')

rep(mp,
'''String setup=r.features.optString("setupType","MOMENTUM");double hod=r.features.optDouble("sessionHod",0);double hodRoom=r.features.optDouble("hodRoomAfterTargetPct",9);double recov=r.features.optDouble("recoveryPct",0);\n            c.addView(txt(String.format(Locale.US,"Score %.0f/100  •  model %.0f%%  •  max 30 min",r.score,r.probability*100),12,MUTED,false));\n            c.addView(txt("Setup "+setup+" • prior HOD "+(hod>0?("₹"+money(hod)):"—")+" • target-clearance "+String.format(Locale.US,"%+.2f%%",hodRoom)+" • recovery "+String.format(Locale.US,"%.2f%%",recov),11,r.features.optBoolean("clearPath",true)?MUTED:RED,false));c.addView(space(8));''',
'''String setup=r.features.optString("setupType","MOMENTUM");double hod=r.features.optDouble("sessionHod",0);double hodRoom=r.features.optDouble("hodRoomAfterTargetPct",9);double recov=r.features.optDouble("recoveryPct",0);\n            LearningStore.Stats ms=learning.stats();String modelLabel=ms.n<30?("calibration "+ms.n+"/30"):(String.format(Locale.US,"model %.0f%%",r.probability*100));\n            c.addView(txt(String.format(Locale.US,"Score %.0f/100  •  %s  •  max 30 min",r.score,modelLabel),12,MUTED,false));\n            c.addView(txt("Setup "+setup+" • prior HOD "+(hod>0?("₹"+money(hod)):"—")+" • target-clearance "+String.format(Locale.US,"%+.2f%%",hodRoom)+" • recovery "+String.format(Locale.US,"%.2f%%",recov),11,r.features.optBoolean("clearPath",true)?MUTED:RED,false));c.addView(space(8));''')

rep(mp,
'''c.addView(space(6));c.addView(txt(r.reason,11,r.qualified?GREEN:AMBER,false));c.addView(space(8));''',
'''c.addView(space(6));if(!r.qualified)c.addView(txt(gateChecklist(r,st.minScore),11,MUTED,false));c.addView(txt(r.reason,11,r.qualified?GREEN:AMBER,false));c.addView(space(8));''')

method='''\n    private String gateChecklist(ScannerEngine.Recommendation r,int minScore){\n        StringBuilder b=new StringBuilder("WHY "+(r.qualified?"QUALIFIED":"WATCH")+" • ");\n        b.append(r.entry>=r.vwap?"✓VWAP ":"✗VWAP ");\n        b.append(r.relVol>=1.20?"✓VOL ":"✗VOL ");\n        b.append(r.rsi>=52&&r.rsi<=73?"✓RSI ":"✗RSI ");\n        b.append(r.features.optBoolean("clearPath",true)?"✓PATH ":"✗PATH ");\n        b.append(r.features.optBoolean("hodRejected",false)?"✗HOD-REJECT ":"✓HOD ");\n        b.append(r.score>=minScore?"✓SCORE":"✗SCORE");\n        if(!r.qualified)b.append(" • indicative entry/target/SL only");\n        return b.toString();\n    }\n\n'''
rep(mp,'\n    private void details(ScannerEngine.Recommendation r){',method+'    private void details(ScannerEngine.Recommendation r){')

opt(mp,'v1.2.0 • standalone package com.suhas.nseunifiedscanner','v1.3.0 • standalone package com.suhas.nseunifiedscanner')
opt(mp,'Live mode only enables the BUY button for scanner-qualified setups. Entry is still blocked outside 09:15–14:40 IST,','Live mode only enables the BUY button for scanner-qualified setups. LIVE automatically disarms when the market closes and after a reboot. Entry is still blocked outside 09:15–14:40 IST,')

rep(up,
'''String setup=rec.features.optString("setupType","MOMENTUM");String body=String.format(Locale.US,"%s • Entry ₹%.2f • Target ₹%.2f • SL ₹%.2f • Score %.0f/100 • model %.0f%% • max 30 min. Tap to review and BUY.",setup,rec.entry,rec.target,rec.stop,rec.score,rec.probability*100);''',
'''String setup=rec.features.optString("setupType","MOMENTUM");LearningStore.Stats ms=learning.stats();String confidence=ms.n<30?("calibration "+ms.n+"/30"):(String.format(Locale.US,"model %.0f%%",rec.probability*100));String body=String.format(Locale.US,"%s • Entry ₹%.2f • Target ₹%.2f • SL ₹%.2f • Score %.0f/100 • %s • max 30 min. Tap to review and BUY.",setup,rec.entry,rec.target,rec.stop,rec.score,confidence);''')

rep(gp,"versionCode 110\n        versionName '1.1.0'","versionCode 130\n        versionName '1.3.0'")
print('v1.3 tail patch applied successfully')
