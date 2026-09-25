#!/usr/bin/env python3
from pathlib import Path
import sys
root=Path(sys.argv[1]).resolve()
p=root/"app/src/main/java/com/suhas/ucsentinel/data/remote/GrowwClient.kt"
s=p.read_text(encoding="utf-8")
start=s.index("    suspend fun placeMarketOrder(")
end=s.index("\n    suspend fun getOhlcBatch",start)
new=r'''    suspend fun placeMarketOrder(
        accessToken:String,
        tradingSymbol:String,
        quantity:Int,
        product:String,
        transactionType:String,
        orderReferenceId:String
    ):BrokerOrderPlacement=withContext(Dispatchers.IO){
        val symbol=tradingSymbol.trim().uppercase();val prod=product.trim().uppercase();val side=transactionType.trim().uppercase();val referenceId=orderReferenceId.trim()
        require(symbol.matches(Regex("""^[A-Z0-9&._-]{1,40}$"""))){"Invalid trading symbol"};require(quantity>0){"Quantity must be greater than zero"}
        require(prod in setOf("CNC","MIS")){"Unsupported product: "+prod};require(side in setOf("BUY","SELL")){"Unsupported transaction type: "+side}
        require(referenceId.matches(Regex("""^[A-Za-z0-9._-]{4,64}$"""))){"Invalid order reference id"}
        require((side=="BUY"&&prod=="CNC")||(side=="SELL"&&prod=="MIS")){"Manual mapping rejected: LONG must be BUY/CNC and SHORT must be SELL/MIS"}
        val body=JSONObject().put("trading_symbol",symbol).put("quantity",quantity).put("validity","DAY").put("exchange","NSE").put("segment","CASH")
            .put("product",prod).put("order_type","MARKET").put("transaction_type",side).put("order_reference_id",referenceId)
        val request=Request.Builder().url(API_BASE+"/v1/order/create").header("Authorization","Bearer "+accessToken).header("Accept","application/json")
            .header("Content-Type","application/json").header("X-API-VERSION","1.0").post(body.toString().toRequestBody("application/json".toMediaType())).build()
        val raw=client.newCall(request).execute().use{response->val text=response.body?.string().orEmpty();if(!response.isSuccessful)throw IOException("Groww order failed ("+response.code+"): "+safeMessage(text));text}
        val json=runCatching{JSONObject(raw)}.getOrElse{throw IOException("Groww returned an unreadable order response")}
        if(!json.optString("status").equals("SUCCESS",true))throw IOException("Groww order rejected: "+safeMessage(raw))
        val x=json.optJSONObject("payload")?:JSONObject()
        BrokerOrderPlacement(x.optString("groww_order_id"),x.optString("order_reference_id").ifBlank{referenceId},x.optString("order_status").ifBlank{"ACCEPTED"},x.optString("remark"))
    }

    suspend fun getOrderStatusByReference(accessToken:String,referenceId:String):BrokerOrderPlacement=withContext(Dispatchers.IO){
        val url=HttpUrl.Builder().scheme("https").host("api.groww.in").addPathSegments("v1/order/status/reference").addPathSegment(referenceId).addQueryParameter("segment","CASH").build()
        val raw=executeWithRetry(authedGet(url,accessToken),liveLimiter,"Order status by reference",maxAttempts=3);val j=JSONObject(raw)
        require(j.optString("status").equals("SUCCESS",true)){"Groww reference status failed"};val x=j.optJSONObject("payload")?:JSONObject()
        BrokerOrderPlacement(x.optString("groww_order_id"),x.optString("order_reference_id").ifBlank{referenceId},x.optString("order_status"),x.optString("remark"))
    }

    suspend fun getOrderDetail(accessToken:String,growwOrderId:String):BrokerOrderDetail=withContext(Dispatchers.IO){
        val url=HttpUrl.Builder().scheme("https").host("api.groww.in").addPathSegments("v1/order/detail").addPathSegment(growwOrderId).addQueryParameter("segment","CASH").build()
        val raw=executeWithRetry(authedGet(url,accessToken),liveLimiter,"Order detail",maxAttempts=3);val j=JSONObject(raw)
        require(j.optString("status").equals("SUCCESS",true)){"Groww order detail failed"};val x=j.optJSONObject("payload")?:JSONObject()
        BrokerOrderDetail(x.optString("groww_order_id").ifBlank{growwOrderId},x.optString("order_status"),x.optString("remark"),x.optInt("quantity"),x.optInt("filled_quantity"),x.optInt("remaining_quantity"),jsonDouble(x,"average_fill_price"),x.optString("order_reference_id"))
    }

    suspend fun getOrderTrades(accessToken:String,growwOrderId:String):List<BrokerFillRecord>=withContext(Dispatchers.IO){
        val url=HttpUrl.Builder().scheme("https").host("api.groww.in").addPathSegments("v1/order/trades").addPathSegment(growwOrderId).addQueryParameter("segment","CASH").addQueryParameter("page","0").addQueryParameter("page_size","50").build()
        val raw=executeWithRetry(authedGet(url,accessToken),liveLimiter,"Order trades",maxAttempts=3);val j=JSONObject(raw)
        require(j.optString("status").equals("SUCCESS",true)){"Groww order trades failed"};val a=j.optJSONObject("payload")?.optJSONArray("trade_list")?:JSONArray()
        buildList{for(i in 0 until a.length()){val x=a.optJSONObject(i)?:continue;add(BrokerFillRecord(x.optString("groww_trade_id"),x.optString("exchange_trade_id"),x.optString("exchange_order_id"),x.optInt("quantity").coerceAtLeast(0),jsonDouble(x,"price"),x.optString("trade_status"),x.optString("trade_date_time"),x.optString("remark")))}}
    }
'''
s=s[:start]+new+s[end:]
p.write_text(s,encoding="utf-8")
print("Groww v1.5 safe order reconciliation API applied")
