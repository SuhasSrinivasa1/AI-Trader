#!/usr/bin/env python3
from pathlib import Path
import sys
root=Path(sys.argv[1]).resolve()
p=root/"app/src/main/java/com/suhas/ucsentinel/ui/MainViewModel.kt"
s=p.read_text(encoding="utf-8")
def one(old,new,label):
    global s
    n=s.count(old)
    if n!=1: raise SystemExit(f"{label}: expected 1 found {n}")
    s=s.replace(old,new,1)

one('''    val strategyLive:List<StrategyRecommendation> = emptyList(),val strategyClosed:List<StrategyRecommendation> = emptyList(),
    val globalClosed:List<GlobalLeadClosedRecord> = emptyList(),val tradeCalls:List<TradeCallRecord> = emptyList(),val tradeAutopsies:List<TradeAutopsyRecord> = emptyList()
)''',
'''    val strategyLive:List<StrategyRecommendation> = emptyList(),val strategyClosed:List<StrategyRecommendation> = emptyList(),
    val globalClosed:List<GlobalLeadClosedRecord> = emptyList(),val tradeCalls:List<TradeCallRecord> = emptyList(),val tradeAutopsies:List<TradeAutopsyRecord> = emptyList(),
    val challengerShadows:List<ChallengerShadowRecord> = emptyList(),val brokerOrders:List<BrokerOrderRecord> = emptyList(),
    val evidenceFabric:EvidenceFabricSummary = EvidenceFabricSummary()
)''',"UiState evidence fields")

one('''            runCatching{repo.closeExpiredStrategyCalls()}
            runCatching{repo.reconcileTradeCallLedger()}
''',
'''            runCatching{repo.closeExpiredStrategyCalls()}
            runCatching{repo.reconcileTradeCallLedger()}
            runCatching{repo.resolveChallengerShadows()}
            runCatching{repo.reconcileBrokerOrders()}
''',"foreground governance")

one('''            strategyLive=repo.strategyLiveRecommendations(),strategyClosed=repo.strategyClosedRecommendations(),globalClosed=repo.globalLeadClosedRecommendations(),tradeCalls=repo.tradeCalls(),tradeAutopsies=repo.tradeAutopsies())
''',
'''            strategyLive=repo.strategyLiveRecommendations(),strategyClosed=repo.strategyClosedRecommendations(),globalClosed=repo.globalLeadClosedRecommendations(),tradeCalls=repo.tradeCalls(),tradeAutopsies=repo.tradeAutopsies(),
            challengerShadows=repo.challengerShadows(),brokerOrders=repo.brokerOrders(),evidenceFabric=repo.evidenceFabricSummary())
''',"initial evidence state")

one('''            strategyLive=repo.strategyLiveRecommendations(),strategyClosed=repo.strategyClosedRecommendations(),globalClosed=repo.globalLeadClosedRecommendations(),tradeCalls=repo.tradeCalls(),tradeAutopsies=repo.tradeAutopsies())
''',
'''            strategyLive=repo.strategyLiveRecommendations(),strategyClosed=repo.strategyClosedRecommendations(),globalClosed=repo.globalLeadClosedRecommendations(),tradeCalls=repo.tradeCalls(),tradeAutopsies=repo.tradeAutopsies(),
            challengerShadows=repo.challengerShadows(),brokerOrders=repo.brokerOrders(),evidenceFabric=repo.evidenceFabricSummary())
''',"refresh evidence state")

one('''            .onSuccess{message->
                _state.value=_state.value.copy(status=message,error=null)
                onResult(true,message)
''',
'''            .onSuccess{message->
                _state.value=_state.value.copy(status=message,error=null,brokerOrders=repo.brokerOrders(),evidenceFabric=repo.evidenceFabricSummary())
                onResult(true,message)
''',"order reconciliation state")

anchor='''    fun refreshStrategyCatalog()=viewModelScope.launch{
'''
insert=r'''    fun runChallengerShadowPass()=viewModelScope.launch{
        _state.value=_state.value.copy(busy=true,status="Running non-executable Challenger shadow pass…",error=null)
        runCatching{repo.runChallengerShadowPass()}.onSuccess{added->
            reliabilityRefresh(status="Shadow Run complete • $added new Challenger signal(s)",error=null)
            _state.value=_state.value.copy(busy=false)
        }.onFailure{_state.value=_state.value.copy(busy=false,status="Shadow Run failed",error=it.message)}
    }

    fun resolveChallengerShadows()=viewModelScope.launch{
        _state.value=_state.value.copy(busy=true,status="Resolving due Challenger horizons from historical candles…",error=null)
        runCatching{repo.resolveChallengerShadows()}.onSuccess{resolved->
            reliabilityRefresh(status="Shadow Resolve complete • $resolved resolved",error=null)
            _state.value=_state.value.copy(busy=false)
        }.onFailure{_state.value=_state.value.copy(busy=false,status="Shadow Resolve failed",error=it.message)}
    }

    fun reconcileBrokerOrders()=viewModelScope.launch{
        _state.value=_state.value.copy(busy=true,status="Reconciling Groww orders and fills…",error=null)
        runCatching{repo.reconcileBrokerOrders()}.onSuccess{count->
            reliabilityRefresh(status="Groww reconciliation complete • $count order(s) checked",error=null)
            _state.value=_state.value.copy(busy=false)
        }.onFailure{_state.value=_state.value.copy(busy=false,status="Broker reconciliation failed",error=it.message)}
    }

    fun refreshEvidenceFabric()=viewModelScope.launch{
        _state.value=_state.value.copy(busy=true,status="Refreshing point-in-time evidence + NIFTY 500 industries…",error=null)
        runCatching{repo.refreshNews();repo.refreshSectorIntelligence()}.onSuccess{
            reliabilityRefresh(status="Evidence Fabric refreshed",error=null);_state.value=_state.value.copy(busy=false)
        }.onFailure{_state.value=_state.value.copy(busy=false,status="Evidence Fabric refresh failed",error=it.message)}
    }

'''.replace("$","$")+anchor
one(anchor,insert,"new v150 VM actions")

p.write_text(s,encoding="utf-8")
print("v1.5 MainViewModel evidence/challenger/broker UI state applied")
