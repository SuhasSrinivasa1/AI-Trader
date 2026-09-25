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

one(
'''    val strategyLive:List<StrategyRecommendation> = emptyList(),val strategyClosed:List<StrategyRecommendation> = emptyList(),
    val globalClosed:List<GlobalLeadClosedRecord> = emptyList(),val tradeCalls:List<TradeCallRecord> = emptyList(),val tradeAutopsies:List<TradeAutopsyRecord> = emptyList()
)''',
'''    val strategyLive:List<StrategyRecommendation> = emptyList(),val strategyClosed:List<StrategyRecommendation> = emptyList(),
    val globalClosed:List<GlobalLeadClosedRecord> = emptyList(),val tradeCalls:List<TradeCallRecord> = emptyList(),val tradeAutopsies:List<TradeAutopsyRecord> = emptyList(),
    val challengerShadows:List<ChallengerShadowRecord> = emptyList(),val brokerOrders:List<BrokerOrderRecord> = emptyList(),
    val decisionSnapshots:List<DecisionSnapshot> = emptyList(),val pointInTimeEvidence:List<PointInTimeEvidence> = emptyList(),
    val evidenceFabric:EvidenceFabricSummary?=null
)''',"UiState")

one(
'''    private var lastForegroundGovernanceAt=0L
''',
'''    private var lastForegroundGovernanceAt=0L
    private var lastBrokerReconcileAt=0L
''',"broker clock")

# Foreground governance.
one(
'''        if(now-lastForegroundGovernanceAt>=5L*60_000L){
            lastForegroundGovernanceAt=now
            runCatching{repo.closeExpiredStrategyCalls()}
            runCatching{repo.reconcileTradeCallLedger()}
        }
''',
'''        if(now-lastForegroundGovernanceAt>=5L*60_000L){
            lastForegroundGovernanceAt=now
            runCatching{repo.closeExpiredStrategyCalls()}
            runCatching{repo.reconcileTradeCallLedger()}
            runCatching{repo.resolveChallengerShadows()}
        }
        if(now-lastBrokerReconcileAt>=60_000L){
            lastBrokerReconcileAt=now
            runCatching{repo.reconcileBrokerOrders()}
        }
''',"governance")

# Initial state.
state_tail='''            strategyLive=repo.strategyLiveRecommendations(),strategyClosed=repo.strategyClosedRecommendations(),globalClosed=repo.globalLeadClosedRecommendations(),tradeCalls=repo.tradeCalls(),tradeAutopsies=repo.tradeAutopsies())
'''
state_tail_new='''            strategyLive=repo.strategyLiveRecommendations(),strategyClosed=repo.strategyClosedRecommendations(),globalClosed=repo.globalLeadClosedRecommendations(),tradeCalls=repo.tradeCalls(),tradeAutopsies=repo.tradeAutopsies(),
            challengerShadows=repo.challengerShadows(),brokerOrders=repo.brokerOrders(),decisionSnapshots=repo.decisionSnapshots(),pointInTimeEvidence=repo.pointInTimeEvidence(),evidenceFabric=repo.evidenceFabricSummary())
'''
if s.count(state_tail)!=2: raise SystemExit(f"state tail expected 2 found {s.count(state_tail)}")
s=s.replace(state_tail,state_tail_new,2)

# Manual order now carries the model entry price and refreshes broker reconciliation.
start=s.index("    fun placeManualOrder(")
end=s.index("\n    fun authenticate()",start)
s=s[:start]+'''    fun placeManualOrder(symbol:String,side:String,product:String,quantity:Int,entryPrice:Double,onResult:(Boolean,String)->Unit)=viewModelScope.launch{
        _state.value=_state.value.copy(status="Submitting manual $side $quantity $symbol ($product)…",error=null)
        runCatching{repo.placeManualMarketOrder(symbol,side,product,quantity,entryPrice)}
            .onSuccess{message->
                runCatching{repo.reconcileBrokerOrders()}
                _state.value=_state.value.copy(status=message,error=null,brokerOrders=repo.brokerOrders(),evidenceFabric=repo.evidenceFabricSummary())
                onResult(true,message)
            }
            .onFailure{t->
                val message=t.message.orEmpty().ifBlank{"Order submission failed"}
                _state.value=_state.value.copy(status="Order not placed / reconcile required",error=message,brokerOrders=repo.brokerOrders(),evidenceFabric=repo.evidenceFabricSummary())
                onResult(false,message)
            }
    }

    fun reconcileBrokerNow()=viewModelScope.launch{
        _state.value=_state.value.copy(busy=true,status="Reconciling Groww orders and fills…",error=null)
        runCatching{repo.reconcileBrokerOrders()}.onSuccess{n->
            _state.value=_state.value.copy(busy=false,status="Broker reconciliation complete • $n updated",brokerOrders=repo.brokerOrders(),evidenceFabric=repo.evidenceFabricSummary(),error=null)
        }.onFailure{t->_state.value=_state.value.copy(busy=false,status="Broker reconciliation failed",error=t.message,brokerOrders=repo.brokerOrders())}
    }

    fun runChallengerShadowNow()=viewModelScope.launch{
        _state.value=_state.value.copy(busy=true,status="Running non-executable Challenger shadow scan…",error=null)
        repo.markStrategyScanAttempt()
        runCatching{repo.scanTradingStrategies(progress={m->_state.value=_state.value.copy(status=m)},challengerOnly=true)}.onSuccess{summary->
            _state.value=_state.value.copy(busy=false,strategyTournamentSummary=summary,status=summary.message,error=null,
                challengerShadows=repo.challengerShadows(),decisionSnapshots=repo.decisionSnapshots(),pointInTimeEvidence=repo.pointInTimeEvidence(),evidenceFabric=repo.evidenceFabricSummary())
        }.onFailure{t->repo.markStrategyScanError(t);_state.value=_state.value.copy(busy=false,status="Shadow Run failed",error=t.message)}
    }

    fun resolveChallengerShadowsNow()=viewModelScope.launch{
        _state.value=_state.value.copy(busy=true,status="Resolving scheduled Challenger horizons…",error=null)
        runCatching{repo.resolveChallengerShadows()}.onSuccess{n->
            _state.value=_state.value.copy(busy=false,status="Challenger resolution complete • $n resolved",challengerShadows=repo.challengerShadows(),evidenceFabric=repo.evidenceFabricSummary(),error=null)
        }.onFailure{t->_state.value=_state.value.copy(busy=false,status="Challenger resolution failed",error=t.message)}
    }
'''+s[end:]

p.write_text(s,encoding="utf-8")
print("Global Edge v1.5 ViewModel finalization applied")
