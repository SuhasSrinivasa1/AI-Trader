package com.suhas.globaledgeai.data.local

import android.content.Context
import com.suhas.globaledgeai.domain.model.BrokerFillRecord
import com.suhas.globaledgeai.domain.model.BrokerOrderReconciliation
import org.json.JSONArray
import org.json.JSONObject

class BrokerReconciliationStore(context:Context){
    private val prefs=context.getSharedPreferences("broker_reconciliation_v150",Context.MODE_PRIVATE)

    fun upsert(row:BrokerOrderReconciliation){
        val all=load(500).filterNot{it.growwOrderId==row.growwOrderId}.toMutableList()
        all+=row
        save(all)
    }

    fun save(rows:List<BrokerOrderReconciliation>){
        val a=JSONArray()
        rows.sortedByDescending{it.submittedAt}.take(500).forEach{x->
            val fills=JSONArray()
            x.fills.forEach{f->
                fills.put(JSONObject().put("tradeId",f.tradeId).put("growwOrderId",f.growwOrderId)
                    .put("quantity",f.quantity).put("price",f.price).put("exchangeTime",f.exchangeTime))
            }
            a.put(JSONObject().put("growwOrderId",x.growwOrderId).put("orderReferenceId",x.orderReferenceId)
                .put("symbol",x.symbol).put("side",x.side).put("product",x.product)
                .put("requestedQuantity",x.requestedQuantity).put("status",x.status)
                .put("filledQuantity",x.filledQuantity).put("remainingQuantity",x.remainingQuantity)
                .put("averageFillPrice",x.averageFillPrice).put("submittedAt",x.submittedAt)
                .put("reconciledAt",x.reconciledAt).put("remark",x.remark).put("fills",fills))
        }
        prefs.edit().putString("rows",a.toString()).putLong("last_reconcile",rows.maxOfOrNull{it.reconciledAt}?:0L).apply()
    }

    fun load(limit:Int=500):List<BrokerOrderReconciliation>{
        val a=runCatching{JSONArray(prefs.getString("rows","[]"))}.getOrElse{JSONArray()}
        return buildList{
            for(i in 0 until a.length()){
                val j=a.optJSONObject(i)?:continue
                val fa=j.optJSONArray("fills")?:JSONArray()
                val fills=buildList{
                    for(k in 0 until fa.length()){
                        val f=fa.optJSONObject(k)?:continue
                        add(BrokerFillRecord(f.optString("tradeId"),f.optString("growwOrderId"),
                            f.optInt("quantity"),f.optDouble("price"),f.optString("exchangeTime")))
                    }
                }
                add(BrokerOrderReconciliation(
                    j.optString("growwOrderId"),j.optString("orderReferenceId"),j.optString("symbol"),
                    j.optString("side"),j.optString("product"),j.optInt("requestedQuantity"),
                    j.optString("status"),j.optInt("filledQuantity"),j.optInt("remainingQuantity"),
                    j.optDouble("averageFillPrice"),j.optLong("submittedAt"),j.optLong("reconciledAt"),
                    j.optString("remark"),fills
                ))
            }
        }.sortedByDescending{it.submittedAt}.take(limit)
    }

    fun lastReconcileAt():Long=prefs.getLong("last_reconcile",0L)
}
