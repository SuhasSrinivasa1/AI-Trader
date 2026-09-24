#!/usr/bin/env python3
from pathlib import Path
import sys
root=Path(sys.argv[1]).resolve()
p=root/"app/src/main/java/com/suhas/ucsentinel/domain/model/ResearchFabricModels.kt"
p.parent.mkdir(parents=True,exist_ok=True)
p.write_text(r'''package com.suhas.globaledgeai.domain.model

enum class EvidenceKind { FUNDAMENTAL, ANALYST_RATING, EARNINGS_EVENT, CORPORATE_EVENT, SECTOR, MACRO, NEWS }
enum class ChallengerShadowStatus { OPEN, WIN, LOSS, UNRESOLVED_DATA }
enum class DecisionAction { LIVE, WAIT, NO_TRADE, CHALLENGER_SHADOW, MANUAL_ORDER }
enum class BrokerSyncState { NEW, SYNCED, PARTIAL, COMPLETE, REJECTED, CANCELLED, ERROR }

data class PointInTimeEvidence(
    val id:String,
    val symbol:String,
    val kind:EvidenceKind,
    val label:String,
    val detail:String,
    val observedAt:Long,
    val effectiveAt:Long,
    val source:String,
    val sourceUrl:String="",
    val revisionId:String="",
    val scoreImpact:Double=0.0
)

data class MacroRiskEvent(
    val id:String,
    val title:String,
    val startDateIso:String,
    val endDateIso:String,
    val severity:String,
    val source:String,
    val sourceUrl:String="",
    val observedAt:Long=0L
)

data class SectorPeerState(
    val symbol:String,
    val industry:String,
    val peerCount:Int,
    val positivePeers:Int,
    val negativePeers:Int,
    val peerBreadthPct:Double,
    val peerAverageReturnPct:Double,
    val stockReturnPct:Double,
    val relativeStrengthPct:Double,
    val participationAligned:Boolean,
    val sourceVersion:String,
    val observedAt:Long
)

data class ChallengerShadowRecord(
    val id:String,
    val strategyId:String,
    val strategyName:String,
    val symbol:String,
    val direction:TradeDirection,
    val score:Double,
    val entryPrice:Double,
    val capturedAt:Long,
    val scheduledHorizonAt:Long,
    val horizonMinutes:Int,
    val researchSignature:String,
    val evidence:String,
    val status:ChallengerShadowStatus=ChallengerShadowStatus.OPEN,
    val resolvedAt:Long=0L,
    val horizonPrice:Double=0.0,
    val returnPct:Double=0.0,
    val sessionDate:String=""
)

data class BrokerFill(
    val growwTradeId:String,
    val exchangeTradeId:String,
    val exchangeOrderId:String,
    val quantity:Int,
    val price:Double,
    val tradeStatus:String,
    val tradeDateTime:String,
    val settlementNumber:String=""
)

data class BrokerOrderRecord(
    val localId:String,
    val growwOrderId:String,
    val orderReferenceId:String,
    val symbol:String,
    val side:String,
    val product:String,
    val requestedQty:Int,
    val expectedEntryPrice:Double,
    val orderStatus:String,
    val filledQty:Int=0,
    val remainingQty:Int=requestedQty,
    val averageFillPrice:Double=0.0,
    val placedAt:Long=System.currentTimeMillis(),
    val lastReconciledAt:Long=0L,
    val fills:List<BrokerFill> = emptyList(),
    val syncState:BrokerSyncState=BrokerSyncState.NEW,
    val remark:String="",
    val lastError:String=""
){
    val slippagePct:Double
        get()=if(expectedEntryPrice<=0.0||averageFillPrice<=0.0)0.0
        else if(side.equals("BUY",true))(averageFillPrice/expectedEntryPrice-1.0)*100.0
        else (expectedEntryPrice/averageFillPrice-1.0)*100.0
}

data class BrokerHolding(
    val symbol:String,
    val quantity:Int,
    val averagePrice:Double,
    val lastPrice:Double,
    val investedValue:Double,
    val currentValue:Double
)

data class BrokerPosition(
    val symbol:String,
    val product:String,
    val netQuantity:Int,
    val averagePrice:Double,
    val lastPrice:Double,
    val pnl:Double
)

data class BrokerPortfolioSnapshot(
    val capturedAt:Long=0L,
    val holdings:List<BrokerHolding> = emptyList(),
    val positions:List<BrokerPosition> = emptyList(),
    val message:String=""
)

data class DecisionSnapshot(
    val id:String,
    val decisionHash:String,
    val symbol:String,
    val engine:String,
    val strategyId:String,
    val direction:String,
    val score:Double,
    val action:DecisionAction,
    val reason:String,
    val decisionAt:Long,
    val marketDataAt:Long,
    val calendarVersion:String,
    val strategyCatalogVersion:String,
    val handbookVersion:String,
    val sectorEvidence:String="",
    val pointInTimeEvidenceIds:List<String> = emptyList(),
    val eventRisk:String="",
    val gates:List<String> = emptyList()
)

data class EvidenceFabricSummary(
    val generatedAt:Long=0L,
    val calendarVersion:String="",
    val weekSessionsRemaining:Int=0,
    val monthSessionsRemaining:Int=0,
    val macroRisk:List<MacroRiskEvent> = emptyList(),
    val evidenceCount:Int=0,
    val fundamentalCount:Int=0,
    val analystCount:Int=0,
    val earningsEventCount:Int=0,
    val challengerOpen:Int=0,
    val challengerResolved:Int=0,
    val brokerOrders:Int=0,
    val brokerOrdersPending:Int=0,
    val latestDecisions:List<DecisionSnapshot> = emptyList()
)
''',encoding="utf-8")
print("ResearchFabricModels.kt created")
