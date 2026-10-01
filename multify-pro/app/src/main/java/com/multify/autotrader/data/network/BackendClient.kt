package com.multify.autotrader.data.network
import com.google.gson.Gson
import com.google.gson.reflect.TypeToken
import com.multify.autotrader.BuildConfig
import kotlinx.coroutines.*
import okhttp3.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import java.net.URI
import java.security.MessageDigest
import java.util.UUID
import java.util.concurrent.TimeUnit
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec

class BackendException(message:String,val retryable:Boolean=false):RuntimeException(message)
class BackendClient(private val http:OkHttpClient=OkHttpClient.Builder().connectTimeout(5,TimeUnit.SECONDS).readTimeout(10,TimeUnit.SECONDS).retryOnConnectionFailure(true).build(),private val gson:Gson=Gson()){
 suspend fun health(base:String)=withContext(Dispatchers.IO){execute(Request.Builder().url(norm(base)+"/api/v2/health").get().build(),HealthResponse::class.java)}
 suspend fun dashboard(base:String,id:String,secret:String)=signedGet(base,"/api/v2/dashboard",id,secret,DashboardResponse::class.java)
 suspend fun positions(base:String,id:String,secret:String):List<PositionResponse>=withContext(Dispatchers.IO){
  val req=signed(norm(base),"/api/v2/positions","GET","",id,secret);http.newCall(req).execute().use{r->val b=r.body?.string().orEmpty();if(!r.isSuccessful)throw err(r.code,b);val t=object:TypeToken<List<PositionResponse>>(){}.type;gson.fromJson<List<PositionResponse>>(b,t)?:emptyList()}
 }
 suspend fun sendNotification(base:String,id:String,secret:String,p:NotificationPayload):DecisionResponse=withContext(Dispatchers.IO){
  val path="/api/v2/notifications";val json=gson.toJson(p);val req=signed(norm(base),path,"POST",json,id,secret).newBuilder().header("Idempotency-Key",p.eventId).build()
  http.newCall(req).execute().use{r->val b=r.body?.string().orEmpty();if(!r.isSuccessful)throw err(r.code,b);gson.fromJson(b,DecisionResponse::class.java)?:throw BackendException("Empty decision response")}
 }
 suspend fun setKillSwitch(base:String,id:String,secret:String,enabled:Boolean)=withContext(Dispatchers.IO){
  val path="/api/v2/control/kill-switch";val j="{\"enabled\":$enabled}";http.newCall(signed(norm(base),path,"POST",j,id,secret)).execute().use{r->if(!r.isSuccessful)throw err(r.code,r.body?.string().orEmpty());true}
 }
 private suspend fun<T> signedGet(base:String,path:String,id:String,secret:String,c:Class<T>)=withContext(Dispatchers.IO){execute(signed(norm(base),path,"GET","",id,secret),c)}
 private fun signed(base:String,path:String,method:String,body:String,id:String,secret:String):Request{
  transport(base);val ts=(System.currentTimeMillis()/1000).toString();val nonce=UUID.randomUUID().toString().replace("-","");val canonical=ts+"\n"+nonce+"\n"+method+"\n"+path+"\n"+sha(body);val sig=hmac(secret,canonical)
  val b=Request.Builder().url(base+path).header("Accept","application/json").header("X-Device-Id",id).header("X-Timestamp",ts).header("X-Nonce",nonce).header("X-Signature",sig)
  return if(method=="POST")b.post(body.toRequestBody(JSON)).build() else b.get().build()
 }
 private fun<T> execute(req:Request,c:Class<T>):T{http.newCall(req).execute().use{r->val b=r.body?.string().orEmpty();if(!r.isSuccessful)throw err(r.code,b);return gson.fromJson(b,c)?:throw BackendException("Empty response")}}
 private fun err(code:Int,b:String)=BackendException("HTTP "+code+": "+b.take(180),code==408||code==429||code>=500)
 private fun norm(v:String):String{val x=v.trim().trimEnd('/');transport(x);return x}
 private fun transport(v:String){val s=runCatching{URI(v).scheme?.lowercase()}.getOrNull();if(s!="https"&&!(BuildConfig.ALLOW_HTTP_BACKEND&&s=="http"))throw BackendException("HTTPS is required for this build")}
 private fun sha(v:String)=MessageDigest.getInstance("SHA-256").digest(v.toByteArray()).joinToString(""){"%02x".format(it)}
 private fun hmac(k:String,v:String):String{val m=Mac.getInstance("HmacSHA256");m.init(SecretKeySpec(k.toByteArray(),"HmacSHA256"));return m.doFinal(v.toByteArray()).joinToString(""){"%02x".format(it)}}
 companion object{private val JSON="application/json; charset=utf-8".toMediaType()}
}
