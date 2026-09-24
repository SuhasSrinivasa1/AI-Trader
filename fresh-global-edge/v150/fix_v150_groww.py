#!/usr/bin/env python3
from pathlib import Path
import sys
root=Path(sys.argv[1]).resolve()
p=root/"app/src/main/java/com/suhas/ucsentinel/data/remote/GrowwClient.kt"
s=p.read_text(encoding="utf-8")
start=s.index("    suspend fun placeMarketOrder(")
end=s.index("\n    suspend fun getOhlcBatch",start)
block=r'''    suspend fun placeMarketOrderDetailed(
        accessToken:String,
        tradingSymbol:String,
        quantity:Int,
        product:String,
        transactionType:String,
        expectedEntryPrice:Double=0.0
    ):BrokerOrderRecord=withContext(Dispatchers.IO){
        val symbol=tradingSymbol.trim().uppercase()
        val prod=product.trim().uppercase()
        val side=transactionType.trim().uppercase()
        require(symbol.matches(Regex("""^[A-Z0-9&._-]{1,40}$"""))){"Invalid trading symbol"}
        require(quantity>0){"Quantity must be greater than zero"}
        require(prod in setOf("CNC","MIS")){"Unsupported product: $prod"}
        require(side in setOf("BUY","SELL")){"Unsupported transaction type: $side"}
        require((side=="BUY"&&prod=="CNC")||(side=="SELL"&&prod=="MIS")){
            "Manual mapping rejected: LONG must be BUY/CNC and SHORT must be SELL/MIS"
        }
        val referenceId="GE-"+System.currentTimeMillis().toString().takeLast(13)
        val body=JSONObject()
            .put("trading_symbol",symbol)
            .put("quantity",quantity)
            .put("validity","DAY")
            .put("exchange","NSE")
            .put("segment","CASH")
            .put("product",prod)
            .put("order_type","MARKET")
            .put("transaction_type",side)
            .put("order_reference_id",referenceId)

        val request=Request.Builder()
            .url("$API_BASE/v1/order/create")
            .header("Authorization","Bearer $accessToken")
            .header("Accept","application/json")
            .header("Content-Type","application/json")
            .header("X-API-VERSION","1.0")
            .post(body.toString().toRequestBody("application/json".toMediaType()))
            .build()

        val raw=client.newCall(request).execute().use{response->
            val text=response.body?.string().orEmpty()
            if(!response.isSuccessful)throw IOException("Groww order failed (${response.code}): ${safeMessage(text)}")
            text
        }
        val json=runCatching{JSONObject(raw)}.getOrElse{throw IOException("Groww returned an unreadable order response")}
        if(!json.optString("status").equals("SUCCESS",true))throw IOException("Groww order rejected: ${safeMessage(raw)}")
        val payload=json.optJSONObject("payload")?:JSONObject()
        val orderId=payload.optString("groww_order_id")
        require(orderId.isNotBlank()){"Groww accepted the request but returned no order id"}
        val status=payload.optString("order_status").ifBlank{"ACCEPTED"}
        val remark=payload.optString("remark")
        BrokerOrderRecord(
            localId=referenceId,growwOrderId=orderId,orderReferenceId=payload.optString("order_reference_id").ifBlank{referenceId},
            symbol=symbol,side=side,product=prod,requestedQty=quantity,expectedEntryPrice=expectedEntryPrice,
            orderStatus=status,remainingQty=quantity,placedAt=System.currentTimeMillis(),syncState=BrokerSyncState.NEW,remark=remark
        )
    }

    suspend fun placeMarketOrder(
        accessToken:String,
        tradingSymbol:String,
        quantity:Int,
        product:String,
        transactionType:String
    ):String{
        val x=placeMarketOrderDetailed(accessToken,tradingSymbol,quantity,product,transactionType,0.0)
        return "Groww order ${x.growwOrderId} • ${x.orderStatus}"+if(x.remark.isBlank())"" else " • ${x.remark}"
    }

    suspend fun getOrderDetail(accessToken:String,base:BrokerOrderRecord):BrokerOrderRecord=withContext(Dispatchers.IO){
        val url=HttpUrl.Builder().scheme("https").host("api.groww.in")
            .addPathSegments("v1/order/detail/${base.growwOrderId}")
            .addQueryParameter("segment","CASH").build()
        val raw=executeWithRetry(authedGet(url,accessToken),authLimiter,"Order detail",maxAttempts=2)
        val payload=JSONObject(raw).optJSONObject("payload")?:throw IOException("Missing order detail payload")
        val filled=payload.optInt("filled_quantity",base.filledQty)
        val remaining=payload.optInt("remaining_quantity",(base.requestedQty-filled).coerceAtLeast(0))
        val avg=jsonDouble(payload,"average_fill_price",base.averageFillPrice)
        val status=payload.optString("order_status").ifBlank{base.orderStatus}
        val sync=when{
            status.equals("REJECTED",true)->BrokerSyncState.REJECTED
            status.equals("CANCELLED",true)->BrokerSyncState.CANCELLED
            filled>=base.requestedQty&&base.requestedQty>0->BrokerSyncState.COMPLETE
            filled>0->BrokerSyncState.PARTIAL
            else->BrokerSyncState.SYNCED
        }
        base.copy(
            orderStatus=status,filledQty=filled,remainingQty=remaining,averageFillPrice=avg,
            lastReconciledAt=System.currentTimeMillis(),syncState=sync,remark=payload.optString("remark").ifBlank{base.remark},lastError=""
        )
    }

    suspend fun getTradesForOrder(accessToken:String,growwOrderId:String):List<BrokerFill>=withContext(Dispatchers.IO){
        val url=HttpUrl.Builder().scheme("https").host("api.groww.in")
            .addPathSegments("v1/order/trades/$growwOrderId")
            .addQueryParameter("segment","CASH").addQueryParameter("page","0").addQueryParameter("page_size","50").build()
        val raw=executeWithRetry(authedGet(url,accessToken),authLimiter,"Order trades",maxAttempts=2)
        val a=JSONObject(raw).optJSONObject("payload")?.optJSONArray("trade_list")?:JSONArray()
        buildList{
            for(i in 0 until a.length()){
                val j=a.optJSONObject(i)?:continue
                add(BrokerFill(
                    growwTradeId=j.optString("groww_trade_id"),exchangeTradeId=j.optString("exchange_trade_id"),exchangeOrderId=j.optString("exchange_order_id"),
                    quantity=j.optInt("quantity"),price=jsonDouble(j,"price"),tradeStatus=j.optString("trade_status"),tradeDateTime=j.optString("trade_date_time"),
                    settlementNumber=j.optString("settlement_number")
                ))
            }
        }
    }

    suspend fun getHoldings(accessToken:String):List<BrokerHolding>=withContext(Dispatchers.IO){
        val url=HttpUrl.Builder().scheme("https").host("api.groww.in").addPathSegments("v1/holdings/user").build()
        val raw=executeWithRetry(authedGet(url,accessToken),authLimiter,"Holdings",maxAttempts=2)
        val a=JSONObject(raw).optJSONObject("payload")?.optJSONArray("holdings")?:JSONArray()
        buildList{
            for(i in 0 until a.length()){
                val j=a.optJSONObject(i)?:continue
                val qty=j.optInt("quantity");val avg=jsonDouble(j,"average_price")
                add(BrokerHolding(j.optString("trading_symbol"),qty,avg,0.0,avg*qty,0.0))
            }
        }
    }

    suspend fun getCashPositions(accessToken:String):List<BrokerPosition>=withContext(Dispatchers.IO){
        val url=HttpUrl.Builder().scheme("https").host("api.groww.in").addPathSegments("v1/positions/user").addQueryParameter("segment","CASH").build()
        val raw=executeWithRetry(authedGet(url,accessToken),authLimiter,"Positions",maxAttempts=2)
        val a=JSONObject(raw).optJSONObject("payload")?.optJSONArray("positions")?:JSONArray()
        buildList{
            for(i in 0 until a.length()){
                val j=a.optJSONObject(i)?:continue
                add(BrokerPosition(
                    symbol=j.optString("trading_symbol"),product=j.optString("product"),netQuantity=j.optInt("quantity"),
                    averagePrice=jsonDouble(j,"net_price"),lastPrice=0.0,pnl=jsonDouble(j,"realised_pnl")
                ))
            }
        }
    }

'''
s=s[:start]+block+s[end:]
p.write_text(s,encoding="utf-8")
print("Groww broker reconciliation and portfolio APIs added")
