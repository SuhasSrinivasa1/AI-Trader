package com.suhas.globaledgeai.domain.model

enum class EvidenceType { FUNDAMENTAL, ANALYST_REVISION, EARNINGS_DATE, MACRO_EVENT, SECTOR_CONTEXT, EXECUTION }
enum class EvidenceSeverity { INFO, MEDIUM, HIGH }
enum class ChallengerShadowStatus { OPEN, WIN, LOSS, EXPIRED, UNRESOLVED_DATA }

data class PointInTimeEvidence(
    val id:String,
    val symbol:String="",
    val type:EvidenceType,
    val key:String,
    val value:String,
    val source:String,
    val observedAt:Long,
    val effectiveAtText:String="",
    val publishedAtText:String="",
    val severity:EvidenceSeverity=EvidenceSeverity.INFO,
    val hardBlock:Boolean=false
)

data class SectorIntelligence(
    val symbol:String,
    val industry:String,
    val peerCount:Int,
    val breadthPct:Double,
    val avgReturnPct:Double,
    val stockReturnPct:Double,
    val stockVsSectorPct:Double,
    val peerConfirmation:Boolean,
    val observedAt:Long,
    val source:String="NIFTY 500 industry constituent file"
)

data class ChallengerShadowRecord(
    val id:String,
    val strategyId:String,
    val strategyName:String,
    val symbol:String,
    val direction:TradeDirection,
    val entryPrice:Double,
    val score:Double,
    val openedAt:Long,
    val horizonAt:Long,
    val horizonMinutes:Int,
    val targetPct:Double,
    val stopPct:Double,
    val evidence:String,
    val status:ChallengerShadowStatus=ChallengerShadowStatus.OPEN,
    val resolvedAt:Long=0L,
    val horizonPrice:Double=0.0,
    val returnPct:Double=0.0,
    val resolutionNote:String="",
    val calendarVersion:String=""
)

data class BrokerFill(
    val growwTradeId:String,
    val exchangeTradeId:String,
    val price:Double,
    val quantity:Int,
    val tradeStatus:String,
    val tradeDateTime:String
)

data class BrokerOrderRecord(
    val growwOrderId:String,
    val orderReferenceId:String,
    val symbol:String,
    val transactionType:String,
    val product:String,
    val requestedQuantity:Int,
    val submittedAt:Long,
    val orderStatus:String,
    val filledQuantity:Int=0,
    val remainingQuantity:Int=requestedQuantity,
    val averageFillPrice:Double=0.0,
    val remark:String="",
    val lastReconciledAt:Long=0L,
    val fills:List<BrokerFill> = emptyList()
)

data class GrowwOrderSubmission(
    val growwOrderId:String,
    val orderReferenceId:String,
    val orderStatus:String,
    val remark:String
)

data class GrowwOrderDetail(
    val growwOrderId:String,
    val tradingSymbol:String,
    val orderStatus:String,
    val quantity:Int,
    val filledQuantity:Int,
    val remainingQuantity:Int,
    val averageFillPrice:Double,
    val remark:String,
    val orderReferenceId:String
)

data class DecisionSnapshot(
    val id:String,
    val symbol:String,
    val direction:String,
    val engine:String,
    val strategyId:String,
    val action:String,
    val score:Double,
    val decisionAt:Long,
    val calendarVersion:String,
    val industry:String,
    val sectorBreadthPct:Double,
    val stockVsSectorPct:Double,
    val evidenceIds:List<String>,
    val hardGate:Boolean,
    val reason:String,
    val decisionHash:String
)

data class EvidenceFabricSummary(
    val generatedAt:Long=0L,
    val pointInTimeEvidenceCount:Int=0,
    val fundamentalCount:Int=0,
    val analystCount:Int=0,
    val earningsEventCount:Int=0,
    val sectorMappedCount:Int=0,
    val challengerOpen:Int=0,
    val challengerResolved:Int=0,
    val brokerOrders:Int=0,
    val unreconciledBrokerOrders:Int=0,
    val decisionSnapshots:Int=0,
    val calendarLabel:String="",
    val nextMacroEvent:String=""
)
