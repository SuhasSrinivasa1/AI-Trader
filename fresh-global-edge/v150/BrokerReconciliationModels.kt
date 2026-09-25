package com.suhas.globaledgeai.domain.model

data class BrokerFillRecord(
    val tradeId:String,
    val growwOrderId:String,
    val quantity:Int,
    val price:Double,
    val exchangeTime:String=""
)

data class BrokerOrderReconciliation(
    val growwOrderId:String,
    val orderReferenceId:String,
    val symbol:String,
    val side:String,
    val product:String,
    val requestedQuantity:Int,
    val status:String,
    val filledQuantity:Int,
    val remainingQuantity:Int,
    val averageFillPrice:Double,
    val submittedAt:Long,
    val reconciledAt:Long,
    val remark:String="",
    val fills:List<BrokerFillRecord> = emptyList()
)
