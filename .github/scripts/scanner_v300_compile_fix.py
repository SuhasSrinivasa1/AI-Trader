from pathlib import Path
p=Path('unified-scanner/app/src/main/java/com/suhas/nseunifiedscanner/ScannerEngine.java')
s=p.read_text()
old='''        String setup=sweep.bullishSweep?"LIQUIDITY SWEEP RECLAIM":(sweep.realBreakout?"REAL BREAKOUT HOLD":(bullishHodBreakout?"BULLISH HOD BREAKOUT":(rsHard?"RELATIVE STRENGTH ACCEL":(PulseDiscoveryLogic.precursor(f.pulse1mPct,f.pulseAccel,f.dayPct)?"PULSE PRECURSOR":(f.crossedGreen&&recoveryHard?"EARLY RECOVERY":(f.microBreakoutPct>=-0.05&&f.microBreakoutPct<=0.25?"MICRO BREAKOUT":(volumeBuildHard?"VOLUME BUILD":"PRE-SPIKE"))))));\n'''
new='''        String setup;\n        if(sweep.bullishSweep)setup="LIQUIDITY SWEEP RECLAIM";\n        else if(sweep.realBreakout)setup="REAL BREAKOUT HOLD";\n        else if(bullishHodBreakout)setup="BULLISH HOD BREAKOUT";\n        else if(rsHard)setup="RELATIVE STRENGTH ACCEL";\n        else if(PulseDiscoveryLogic.precursor(f.pulse1mPct,f.pulseAccel,f.dayPct))setup="PULSE PRECURSOR";\n        else if(f.crossedGreen&&recoveryHard)setup="EARLY RECOVERY";\n        else if(f.microBreakoutPct>=-0.05&&f.microBreakoutPct<=0.25)setup="MICRO BREAKOUT";\n        else if(volumeBuildHard)setup="VOLUME BUILD";\n        else setup="PRE-SPIKE";\n'''
if old not in s: raise SystemExit('v3 compile-fix anchor missing')
p.write_text(s.replace(old,new,1))
print('v3 compile fix applied')
