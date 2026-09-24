#!/usr/bin/env python3
from pathlib import Path
import sys
root=Path(sys.argv[1]).resolve()
p=root/"app/src/main/java/com/suhas/ucsentinel/ui/MainViewModel.kt"
s=p.read_text(encoding="utf-8")

def one(old,new,label):
    global s
    n=s.count(old)
    if n!=1: raise SystemExit(f"${label}: expected 1 found ${n}")
    s=s.replace(old,new,1)

one(
'''    val strategyLive:List<StrategyRecommendation> = emptyList(),val strategyClosed:List<StrategyRecommendation> = emptyList(),
    val globalClosed:List<GlobalLeadClosedRecord> = emptyList(),val tradeCalls:List<TradeCallRecord> = emptyList(),val tradeAutopsies:List<TradeAutopsyRecord> = emptyList()
)''',
'''    val strategyLive:List<StrategyRecommendation> = emptyList(),val strategyClosed:List<StrategyRecommendation> = emptyList(),
    val globalClosed:List<GlobalLeadClosedRecord> = emptyList(),val tradeCalls:List<TradeCallRecord> = emptyList(),val tradeAutopsies:List<TradeAutopsyRecord> = emptyList(),
    val evidenceFabric:EvidenceFabricSummary=EvidenceFabricSummary(),
    val pointInTimeEvidence:List<PointInTimeEvidence> = emptyList(),
    val challengerShadows:List<ChallengerShadowRecord> = emptyList(),
    val brokerOrders:List<BrokerOrderRecord> = emptyList(),
    val brokerPortfolio:BrokerPortfolioSnapshot=BrokerPortfolioSnapshot(),
    val decisionSnapshots:List<DecisionSnapshot> = emptyList()
)''',"UiState research fields")

one(
'''            runCatching{repo.closeExpiredStrategyCalls()}
            runCatching{repo.reconcileTradeCallLedger()}
''',
'''            runCatching{repo.closeExpiredStrategyCalls()}
            runCatching{repo.reconcileTradeCallLedger()}
            runCatching{repo.resolveChallengerShadows(false)}
            runCatching{repo.reconcileBrokerOrders()}
''',"foreground reconciliation")

state_anchor='''            strategyLive=repo.strategyLiveRecommendations(),strategyClosed=repo.strategyClosedRecommendations(),globalClosed=repo.globalLeadClosedRecommendations(),tradeCalls=repo.tradeCalls(),tradeAutopsies=repo.tradeAutopsies())
'''
state_replacement='''            strategyLive=repo.strategyLiveRecommendations(),strategyClosed=repo.strategyClosedRecommendations(),globalClosed=repo.globalLeadClosedRecommendations(),tradeCalls=repo.tradeCalls(),tradeAutopsies=repo.tradeAutopsies(),
            evidenceFabric=repo.evidenceFabricSummary(),pointInTimeEvidence=repo.pointInTimeEvidence(),challengerShadows=repo.challengerShadows(),
            brokerOrders=repo.brokerOrders(),brokerPortfolio=repo.brokerPortfolio(),decisionSnapshots=repo.decisionSnapshots())
'''
if s.count(state_anchor)!=2: raise SystemExit(f"research state anchors: expected 2 found {s.count(state_anchor)}")
s=s.replace(state_anchor,state_replacement,2)

old='''    fun placeManualOrder(symbol:String,side:String,product:String,quantity:Int,onResult:(Boolean,String)->Unit)=viewModelScope.launch{
        _state.value=_state.value.copy(status="Submitting manual $side $quantity $symbol ($product)…",error=null)
        runCatching{repo.placeManualMarketOrder(symbol,side,product,quantity)}
            .onSuccess{message->
                _state.value=_state.value.copy(status=message,error=null)
                onResult(true,message)
            }
'''
new='''    fun placeManualOrder(symbol:String,side:String,product:String,quantity:Int,expectedEntryPrice:Double,onResult:(Boolean,String)->Unit)=viewModelScope.launch{
        _state.value=_state.value.copy(status="Submitting manual $side $quantity $symbol ($product)…",error=null)
        runCatching{repo.placeManualMarketOrder(symbol,side,product,quantity,expectedEntryPrice)}
            .onSuccess{message->
                _state.value=_state.value.copy(status=message,error=null)
                reliabilityRefresh(status=message,error=null)
                onResult(true,message)
            }
'''
one(old,new,"manual order expected entry")

anchor='''    fun runLearningNow()=viewModelScope.launch{_state.value=_state.value.copy(busy=true,status="Running autonomous learning pass…",error=null);runCatching{repo.runAutonomousLearningPass(force=true)}.onSuccess{msg->_state.value=_state.value.copy(busy=false,accuracies=repo.accuracies(),strategyMetrics=repo.strategyMetrics(),status=msg);reliabilityRefresh(error=null)}.onFailure{_state.value=_state.value.copy(busy=false,error=it.message)}}
    fun updateSettings(s:AppSettings){repo.saveSettings(s);_state.value=_state.value.copy(settings=s,status="Settings saved");reliabilityRefresh(error=null)}
'''
replacement='''    fun runLearningNow()=viewModelScope.launch{_state.value=_state.value.copy(busy=true,status="Running autonomous learning pass…",error=null);runCatching{repo.runAutonomousLearningPass(force=true)}.onSuccess{msg->_state.value=_state.value.copy(busy=false,accuracies=repo.accuracies(),strategyMetrics=repo.strategyMetrics(),status=msg);reliabilityRefresh(error=null)}.onFailure{_state.value=_state.value.copy(busy=false,error=it.message)}}

    fun runChallengerShadowNow()=viewModelScope.launch{
        _state.value=_state.value.copy(busy=true,status="Running non-executable Challenger shadow scan…",error=null)
        runCatching{repo.scanTradingStrategies{m->_state.value=_state.value.copy(status=m)}}.onSuccess{summary->
            _state.value=_state.value.copy(busy=false,status="Shadow Run complete • "+summary.message,error=null)
            reliabilityRefresh(error=null)
        }.onFailure{t->_state.value=_state.value.copy(busy=false,status="Shadow Run failed",error=t.message)}
    }

    fun resolveChallengerShadows()=viewModelScope.launch{
        _state.value=_state.value.copy(busy=true,status="Resolving due Challenger horizons from historical bars…",error=null)
        runCatching{repo.resolveChallengerShadows(true)}.onSuccess{n->
            _state.value=_state.value.copy(busy=false,status="Resolved $n Challenger shadow observations",error=null)
            reliabilityRefresh(error=null)
        }.onFailure{t->_state.value=_state.value.copy(busy=false,status="Shadow resolution failed",error=t.message)}
    }

    fun refreshBrokerReconciliation()=viewModelScope.launch{
        _state.value=_state.value.copy(busy=true,status="Reconciling Groww orders, fills, holdings and positions…",error=null)
        runCatching{
            val orders=repo.reconcileBrokerOrders()
            val portfolio=repo.refreshBrokerPortfolio()
            orders to portfolio
        }.onSuccess{(orders,portfolio)->
            _state.value=_state.value.copy(busy=false,status="Broker reconciliation complete • $orders orders checked • ${portfolio.holdings.size} holdings • ${portfolio.positions.size} positions",error=null)
            reliabilityRefresh(error=null)
        }.onFailure{t->_state.value=_state.value.copy(busy=false,status="Broker reconciliation failed",error=t.message)}
    }

    fun refreshEvidenceFabric()=viewModelScope.launch{
        _state.value=_state.value.copy(busy=true,status="Refreshing prospective evidence fabric…",error=null)
        runCatching{repo.refreshNews()}.onSuccess{items->
            _state.value=_state.value.copy(busy=false,newsItems=items,status="Evidence Fabric refreshed • ${items.size} exchange updates",error=null)
            reliabilityRefresh(error=null)
        }.onFailure{t->_state.value=_state.value.copy(busy=false,status="Evidence refresh failed",error=t.message)}
    }

    fun updateSettings(s:AppSettings){repo.saveSettings(s);_state.value=_state.value.copy(settings=s,status="Settings saved");reliabilityRefresh(error=null)}
'''
one(anchor,replacement,"new VM actions")

p.write_text(s,encoding="utf-8")
print("MainViewModel v1.5.0 research and broker state applied")
