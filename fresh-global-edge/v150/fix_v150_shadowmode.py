#!/usr/bin/env python3
from pathlib import Path
import sys
root=Path(sys.argv[1]).resolve()
p=root/"app/src/main/java/com/suhas/ucsentinel/data/repository/UCSentinelRepository.kt"
s=p.read_text(encoding="utf-8")
old='''    suspend fun scanTradingStrategies(progress:suspend(String)->Unit={}):StrategyTournamentSummary=strategyMutex.withLock{'''
new='''    suspend fun scanTradingStrategies(progress:suspend(String)->Unit={},challengerOnly:Boolean=false):StrategyTournamentSummary=strategyMutex.withLock{'''
if s.count(old)!=1: raise SystemExit("scan signature mismatch")
s=s.replace(old,new,1)
old='''            for(def in active){
                val e=strategyEngine.evaluate(def,candles)?:continue;rulesMatched++'''
new='''            for(def in active){
                if(challengerOnly && governance[def.id]?.status!=StrategyStatus.CHALLENGER)continue
                val e=strategyEngine.evaluate(def,candles)?:continue;rulesMatched++'''
if s.count(old)!=1: raise SystemExit("challenger loop anchor mismatch")
s=s.replace(old,new,1)
# Mark summary explicitly.
s=s.replace('''val summary=StrategyTournamentSummary(System.currentTimeMillis(),cash.size,active.size,enriched,top.map{it.first},active,perfs,bundle.version,
            "${active.size} active • HB 100/50/50''',
'''val summary=StrategyTournamentSummary(System.currentTimeMillis(),cash.size,active.size,enriched,top.map{it.first},active,perfs,bundle.version,
            (if(challengerOnly)"SHADOW RUN • " else "")+"${active.size} active • HB 100/50/50''',1)
p.write_text(s,encoding="utf-8")
print("v1.5 challenger-only scan mode applied")
