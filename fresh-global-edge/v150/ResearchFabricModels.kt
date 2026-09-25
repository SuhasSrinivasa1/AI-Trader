package com.suhas.globaledgeai.domain.model

enum class EvidenceKind { FUNDAMENTAL, ANALYST, EARNINGS_EVENT, SECTOR_CLASSIFICATION, MACRO_EVENT }
enum class ChallengerOutcome { PENDING, WIN, LOSS, FLAT, UNRESOLVED_DATA }

data class PointInTimeEvidence(
    val id:String,
    val symbol:String,
    val kind:EvidenceKind,
    val field:String,
    val value:String,
    val source:String,
    val effectiveAt:Long,
    val observedAt:Long,
    val retrievedAt:Long=System.currentTimeMillis(),
    val revisionId:String=""
)

data class MacroEvent(
    val id:String,
    val label:String,
    val startAt:Long,
    val decisionAt:Long,
    val observedAt:Long,
    val source:String,
    val riskWindowMinutes:Int=120,
    val symbol:String=""
)

data class SectorClassification(
    val symbol:String,
    val companyName:String,
    val industry:String,
    val observedAt:Long,
    val source:String="NIFTY 500 Index Constituent"
)

data class ChallengerShadowRecord(
    val id:String,
    val strategyId:String,
    val strategyName:String,
    val symbol:String,
    val direction:TradeDirection,
    val score:Double,
    val entryPrice:Double,
    val targetPct:Double,
    val stopPct:Double,
    val openedAt:Long,
    val horizonAt:Long,
    val calendarVersion:String,
    val researchSignature:String="",
    val outcome:ChallengerOutcome=ChallengerOutcome.PENDING,
    val resolvedAt:Long=0L,
    val horizonPrice:Double=0.0,
    val returnPct:Double=0.0,
    val resolutionNote:String=""
)

data class ResearchFabricSummary(
    val calendarVersion:String="NSE-EQ-2026-v1",
    val regularSessionToday:Boolean=false,
    val nextRegularSession:String="",
    val pointInTimeEvidenceCount:Int=0,
    val sectorClassifications:Int=0,
    val sectorSnapshotAt:Long=0L,
    val macroEventsAhead:Int=0,
    val macroRiskNow:Boolean=false,
    val challengerPending:Int=0,
    val challengerResolved:Int=0,
    val decisionSnapshots:Int=0,
    val message:String=""
)
