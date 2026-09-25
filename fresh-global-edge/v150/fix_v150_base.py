#!/usr/bin/env python3
from pathlib import Path
import re, shutil, sys

root=Path(sys.argv[1]).resolve()
here=Path(__file__).resolve().parent
generated=here/"generated"

def rw(rel):
    return (root/rel).read_text(encoding="utf-8")
def wr(rel,s):
    (root/rel).write_text(s,encoding="utf-8")
def one(s,old,new,label):
    n=s.count(old)
    if n!=1:
        raise SystemExit(f"{label}: expected 1, found {n}")
    return s.replace(old,new,1)

# Copy new v1.5.0 sources.
copies={
    "EvidenceModels.kt":"app/src/main/java/com/suhas/ucsentinel/domain/model/EvidenceModels.kt",
    "NseTradingCalendar2026.kt":"app/src/main/java/com/suhas/ucsentinel/domain/engine/NseTradingCalendar2026.kt",
    "MacroEventRegistry.kt":"app/src/main/java/com/suhas/ucsentinel/domain/engine/MacroEventRegistry.kt",
    "EvidenceLedgerStore.kt":"app/src/main/java/com/suhas/ucsentinel/data/local/EvidenceLedgerStore.kt",
    "SectorIndustryClient.kt":"app/src/main/java/com/suhas/ucsentinel/data/remote/SectorIndustryClient.kt",
}
for src,dst in copies.items():
    target=root/dst
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(generated/src,target)

# Version.
p="app/build.gradle.kts";s=rw(p)
s=one(s,"versionCode = 140","versionCode = 150","versionCode")
s=one(s,'versionName = "1.4.0"','versionName = "1.5.0"',"versionName")
wr(p,s)

# Groww client: detailed live order result + broker reconciliation APIs.
p="app/src/main/java/com/suhas/ucsentinel/data/remote/GrowwClient.kt";s=rw(p)
start=s.index("    suspend fun placeMarketOrder(")
end=s.index("\n    suspend fun getOhlcBatch",start)
new=r'''    suspend fun placeMarketOrderDetailed(
        accessToken:String,
        tradingSymbol:String,
        quantity:Int,
        product:String,
        transactionType:String
    ):GrowwOrderSubmission=withContext(Dispatchers.IO){
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
        if(!json.optString("status").equals("SUCCESS",true)){
            throw IOException("Groww order rejected: ${safeMessage(raw)}")
        }
        val payload=json.optJSONObject("payload")?:JSONObject()
        val orderId=payload.optString("groww_order_id").ifBlank{referenceId}
        val orderStatus=payload.optString("order_status").ifBlank{"ACCEPTED"}
        val remark=payload.optString("remark")
        GrowwOrderSubmission(orderId,referenceId,orderStatus,remark)
    }

    suspend fun placeMarketOrder(
        accessToken:String,
        tradingSymbol:String,
        quantity:Int,
        product:String,
        transactionType:String
    ):String{
        val x=placeMarketOrderDetailed(accessToken,tradingSymbol,quantity,product,transactionType)
        return "Groww order ${x.growwOrderId} • ${x.orderStatus}"+if(x.remark.isBlank())"" else " • ${x.remark}"
    }

    suspend fun getOrderDetail(accessToken:String,growwOrderId:String):GrowwOrderDetail=withContext(Dispatchers.IO){
        val id=growwOrderId.trim()
        require(id.isNotBlank()){"Groww order id is required"}
        val url=HttpUrl.Builder().scheme("https").host("api.groww.in")
            .addPathSegments("v1/order/detail/$id").addQueryParameter("segment","CASH").build()
        val request=Request.Builder().url(url)
            .header("Authorization","Bearer $accessToken")
            .header("Accept","application/json")
            .header("X-API-VERSION","1.0").get().build()
        val raw=client.newCall(request).execute().use{response->
            val text=response.body?.string().orEmpty()
            if(!response.isSuccessful)throw IOException("Groww order detail failed (${response.code}): ${safeMessage(text)}")
            text
        }
        val json=JSONObject(raw)
        if(!json.optString("status").equals("SUCCESS",true))throw IOException("Groww order detail rejected: ${safeMessage(raw)}")
        val p=json.optJSONObject("payload")?:JSONObject()
        GrowwOrderDetail(
            growwOrderId=p.optString("groww_order_id").ifBlank{id},
            tradingSymbol=p.optString("trading_symbol"),
            orderStatus=p.optString("order_status"),
            quantity=p.optInt("quantity"),
            filledQuantity=p.optInt("filled_quantity"),
            remainingQuantity=p.optInt("remaining_quantity"),
            averageFillPrice=jsonDouble(p,"average_fill_price"),
            remark=p.optString("remark"),
            orderReferenceId=p.optString("order_reference_id")
        )
    }

    suspend fun getOrderTrades(accessToken:String,growwOrderId:String):List<BrokerFill> = withContext(Dispatchers.IO){
        val id=growwOrderId.trim()
        require(id.isNotBlank()){"Groww order id is required"}
        val url=HttpUrl.Builder().scheme("https").host("api.groww.in")
            .addPathSegments("v1/order/trades/$id")
            .addQueryParameter("segment","CASH")
            .addQueryParameter("page","0")
            .addQueryParameter("page_size","50")
            .build()
        val request=Request.Builder().url(url)
            .header("Authorization","Bearer $accessToken")
            .header("Accept","application/json")
            .header("X-API-VERSION","1.0").get().build()
        val raw=client.newCall(request).execute().use{response->
            val text=response.body?.string().orEmpty()
            if(!response.isSuccessful)throw IOException("Groww trade reconciliation failed (${response.code}): ${safeMessage(text)}")
            text
        }
        val root=JSONObject(raw)
        if(!root.optString("status").equals("SUCCESS",true))throw IOException("Groww trades rejected: ${safeMessage(raw)}")
        val payload=root.opt("payload")
        val arr=when(payload){
            is JSONArray->payload
            is JSONObject->payload.optJSONArray("trades")?:payload.optJSONArray("data")?:JSONArray()
            else->JSONArray()
        }
        buildList{
            for(i in 0 until arr.length()){
                val t=arr.optJSONObject(i)?:continue
                add(BrokerFill(
                    growwTradeId=t.optString("groww_trade_id"),
                    exchangeTradeId=t.optString("exchange_trade_id"),
                    price=jsonDouble(t,"price"),
                    quantity=t.optInt("quantity"),
                    tradeStatus=t.optString("trade_status"),
                    tradeDateTime=t.optString("trade_date_time")
                ))
            }
        }
    }
'''
s=s[:start]+new+s[end:]
wr(p,s)


print('v1.5 base + Groww API integration applied')
