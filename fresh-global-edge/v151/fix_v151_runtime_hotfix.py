#!/usr/bin/env python3
from pathlib import Path
import sys

root=Path(sys.argv[1]).resolve()

def rw(p):
    return (root/p).read_text(encoding="utf-8")

def wr(p,s):
    (root/p).write_text(s,encoding="utf-8")

def one(s,old,new,label):
    n=s.count(old)
    if n!=1:
        raise SystemExit(f"{label}: expected 1 found {n}")
    return s.replace(old,new,1)

# Version hotfix.
p="app/build.gradle.kts"
s=rw(p)
s=one(s,"versionCode = 150","versionCode = 151","versionCode")
s=one(s,'versionName = "1.5.0"','versionName = "1.5.1"',"versionName")
wr(p,s)

# Research store init must never terminate app startup.
p="app/src/main/java/com/suhas/ucsentinel/data/local/ResearchFabricStore.kt"
s=rw(p)
old='''    init{
        if(!prefs.getBoolean("macro_registry_v150_seeded",false)){
            saveMacroEvents(EvidenceFabricEngine.seedMacroEvents())
            prefs.edit().putBoolean("macro_registry_v150_seeded",true).apply()
        }
    }
'''
new='''    init{
        runCatching{
            if(!prefs.getBoolean("macro_registry_v150_seeded",false)){
                saveMacroEvents(EvidenceFabricEngine.seedMacroEvents())
                prefs.edit().putBoolean("macro_registry_v150_seeded",true).apply()
            }
        }
    }
'''
s=one(s,old,new,"research store safe init")
wr(p,s)

# Make new research storage lazy and accessor-safe.
p="app/src/main/java/com/suhas/ucsentinel/data/repository/UCSentinelRepository.kt"
s=rw(p)
old='''    private val fabricStore=ResearchFabricStore(context)
'''
new='''    private val fabricStore by lazy(LazyThreadSafetyMode.SYNCHRONIZED){ResearchFabricStore(appContext)}
'''
s=one(s,old,new,"lazy fabric store")

old='''    fun evidenceFabricSummary():EvidenceFabricSummary = fabricStore.summary()
    fun pointInTimeEvidence():List<PointInTimeEvidence> = fabricStore.evidence(3000)
    fun challengerShadows():List<ChallengerShadowRecord> = fabricStore.challengerShadows(2500)
    fun brokerOrders():List<BrokerOrderRecord> = fabricStore.brokerOrders(500)
    fun brokerPortfolio():BrokerPortfolioSnapshot = fabricStore.portfolio()
    fun decisionSnapshots():List<DecisionSnapshot> = fabricStore.decisions(1500)
'''
new='''    fun evidenceFabricSummary():EvidenceFabricSummary = runCatching{fabricStore.summary()}.getOrDefault(EvidenceFabricSummary())
    fun pointInTimeEvidence():List<PointInTimeEvidence> = runCatching{fabricStore.evidence(3000)}.getOrDefault(emptyList())
    fun challengerShadows():List<ChallengerShadowRecord> = runCatching{fabricStore.challengerShadows(2500)}.getOrDefault(emptyList())
    fun brokerOrders():List<BrokerOrderRecord> = runCatching{fabricStore.brokerOrders(500)}.getOrDefault(emptyList())
    fun brokerPortfolio():BrokerPortfolioSnapshot = runCatching{fabricStore.portfolio()}.getOrDefault(BrokerPortfolioSnapshot())
    fun decisionSnapshots():List<DecisionSnapshot> = runCatching{fabricStore.decisions(1500)}.getOrDefault(emptyList())
'''
s=one(s,old,new,"safe fabric accessors")
wr(p,s)

# Keep v1.5 stores out of synchronous MainViewModel construction.
p="app/src/main/java/com/suhas/ucsentinel/ui/MainViewModel.kt"
s=rw(p)
old='''            strategyLive=repo.strategyLiveRecommendations(),strategyClosed=repo.strategyClosedRecommendations(),globalClosed=repo.globalLeadClosedRecommendations(),tradeCalls=repo.tradeCalls(),tradeAutopsies=repo.tradeAutopsies(),
            evidenceFabric=repo.evidenceFabricSummary(),pointInTimeEvidence=repo.pointInTimeEvidence(),challengerShadows=repo.challengerShadows(),
            brokerOrders=repo.brokerOrders(),brokerPortfolio=repo.brokerPortfolio(),decisionSnapshots=repo.decisionSnapshots())
'''
new='''            strategyLive=repo.strategyLiveRecommendations(),strategyClosed=repo.strategyClosedRecommendations(),globalClosed=repo.globalLeadClosedRecommendations(),tradeCalls=repo.tradeCalls(),tradeAutopsies=repo.tradeAutopsies(),
            evidenceFabric=EvidenceFabricSummary(),pointInTimeEvidence=emptyList(),challengerShadows=emptyList(),
            brokerOrders=emptyList(),brokerPortfolio=BrokerPortfolioSnapshot(),decisionSnapshots=emptyList())
'''
if s.count(old)!=2:
    raise SystemExit(f"MainViewModel state block expected twice found {s.count(old)}")
s=s.replace(old,new,1)

old='''    init{
        repo.ensureTodayFreezeAudit()
'''
new='''    init{
        runCatching{repo.ensureTodayFreezeAudit()}
'''
s=one(s,old,new,"safe boot audit")
wr(p,s)

print("Global Edge v1.5.1 runtime crash-safety hotfix applied")
