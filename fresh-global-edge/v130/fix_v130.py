#!/usr/bin/env python3
from pathlib import Path
import sys

root=Path(sys.argv[1]).resolve()

def rw(p): return (root/p).read_text(encoding="utf-8")
def wr(p,s): (root/p).write_text(s,encoding="utf-8")
def rep(s,old,new,label,count=1):
    n=s.count(old)
    if n!=count:
        raise SystemExit(f"{label}: expected {count}, found {n}")
    return s.replace(old,new,count)

# Version.
p="app/build.gradle.kts"; s=rw(p)
s=rep(s,"versionCode = 129","versionCode = 130","versionCode")
s=rep(s,'versionName = "1.2.9"','versionName = "1.3.0"',"versionName")
wr(p,s)

# GrowwClient: add a one-shot manual market-order API. Deliberately no automatic POST retry:
# if the network response is ambiguous, the user sees an error instead of risking a duplicate trade.
p="app/src/main/java/com/suhas/ucsentinel/data/remote/GrowwClient.kt"; s=rw(p)
anchor='''    suspend fun downloadInstrumentCsv(): String = withContext(Dispatchers.IO) {
        val request = Request.Builder().url(INSTRUMENT_URL).get().build()
        client.newCall(request).execute().use { response ->
            if (!response.isSuccessful) {
                throw IOException("Instrument download failed: HTTP ${response.code}")
            }
            response.body?.string() ?: throw IOException("Empty instrument CSV")
        }
    }

'''
addition=anchor+'''    suspend fun placeMarketOrder(
        accessToken:String,
        tradingSymbol:String,
        quantity:Int,
        product:String,
        transactionType:String
    ):String=withContext(Dispatchers.IO){
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
        val orderId=payload.optString("groww_order_id")
        val orderStatus=payload.optString("order_status").ifBlank{"ACCEPTED"}
        val remark=payload.optString("remark")
        val idText=orderId.ifBlank{referenceId}
        "Groww order $idText • $orderStatus"+if(remark.isBlank())"" else " • $remark"
    }

'''
s=rep(s,anchor,addition,"Groww manual order API")
wr(p,s)

# Repository: gate every manual order on the current whitelisted public IP, current Groww auth,
# market hours, and the exact LONG/SHORT product mapping.
p="app/src/main/java/com/suhas/ucsentinel/data/repository/UCSentinelRepository.kt"; s=rw(p)
anchor='''    suspend fun authenticate():String{
        val(token,expiry)=groww.authenticate(secureStore.loadCredentials())
        secureStore.saveAccessToken(token,expiry)
        return expiry
    }

'''
addition=anchor+'''    suspend fun placeManualMarketOrder(symbol:String,side:String,product:String,quantity:Int):String{
        require(marketSessionInfo().isOpen){"Market is closed. Manual live orders are enabled only during the NSE 09:15–15:30 IST session."}
        require(quantity>0){"Quantity must be greater than zero"}
        val normalizedSide=side.trim().uppercase()
        val normalizedProduct=product.trim().uppercase()
        require((normalizedSide=="BUY"&&normalizedProduct=="CNC")||(normalizedSide=="SELL"&&normalizedProduct=="MIS")){
            "Order mapping rejected. LONG must be BUY/CNC; SHORT must be SELL/MIS."
        }
        val actualIp=currentPublicIpv4()
        require(actualIp==EXPECTED_TRADING_STATIC_IP){
            "Static IP mismatch. Expected $EXPECTED_TRADING_STATIC_IP but current public IPv4 is $actualIp."
        }
        if(!accessTokenIsCurrent()){
            require(ensureAutomationAuthentication()){"Groww authentication is required before placing an order."}
        }
        val token=accessToken()
        require(token.isNotBlank()){"Groww access token is unavailable. Authenticate again."}
        return groww.placeMarketOrder(token,symbol,quantity,normalizedProduct,normalizedSide)
    }

'''
s=rep(s,anchor,addition,"repository manual order")
wr(p,s)

# ViewModel: explicit user-action entry point with a callback for the order dialog.
p="app/src/main/java/com/suhas/ucsentinel/ui/MainViewModel.kt"; s=rw(p)
anchor='''    fun refreshTradingRoute()=viewModelScope.launch{checkTradingRoute()}
    fun saveTradingStaticIp(value:String){refreshTradingRoute()}
    fun authenticate()=viewModelScope.launch{
'''
addition='''    fun refreshTradingRoute()=viewModelScope.launch{checkTradingRoute()}
    fun saveTradingStaticIp(value:String){refreshTradingRoute()}
    fun placeManualOrder(symbol:String,side:String,product:String,quantity:Int,onResult:(Boolean,String)->Unit)=viewModelScope.launch{
        _state.value=_state.value.copy(status="Submitting manual $side $quantity $symbol ($product)…",error=null)
        runCatching{repo.placeManualMarketOrder(symbol,side,product,quantity)}
            .onSuccess{message->
                _state.value=_state.value.copy(status=message,error=null)
                onResult(true,message)
            }
            .onFailure{t->
                val message=t.message.orEmpty().ifBlank{"Order submission failed"}
                _state.value=_state.value.copy(status="Order not placed",error=message)
                onResult(false,message)
            }
    }
    fun authenticate()=viewModelScope.launch{
'''
s=rep(s,anchor,addition,"viewmodel manual order")
wr(p,s)

# UI: replace the Groww-app handoff with a manual confirmation button that submits only after tap.
p="app/src/main/java/com/suhas/ucsentinel/ui/CompactMarketScreens.kt"; s=rw(p)
s=rep(s,
'''private fun TradeCard(symbol:String,direction:String,score:Double,plan:SimplePlan?,detail:String,status:String?=null,orderable:Boolean=false){
    val ctx=LocalContext.current
    var showOrder by remember(symbol,direction,plan?.entry){mutableStateOf(false)}
''',
'''private fun TradeCard(symbol:String,direction:String,score:Double,plan:SimplePlan?,detail:String,status:String?=null,orderable:Boolean=false,vm:MainViewModel?=null){
    val ctx=LocalContext.current
    var showOrder by remember(symbol,direction,plan?.entry){mutableStateOf(false)}
    var submitting by remember(symbol,direction,plan?.entry){mutableStateOf(false)}
''',
"TradeCard vm + state")

old='''                Text("Global Edge does not transmit the securities order. Open Groww below to review and submit this exact ticket.",style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
            }},
            dismissButton={TextButton(onClick={showOrder=false}){Text("Cancel")}},
            confirmButton={
                Button(onClick={
                    showOrder=false
                    if(qty<=0){
                        Toast.makeText(ctx,"Budget insufficient for one share",Toast.LENGTH_LONG).show()
                    }else{
                        AppNotifier.notifyPreparedOrder(ctx,symbol,side,product,qty,plan.entry,plan.stop,plan.target1)
                        Toast.makeText(ctx,"Opening Groww — order is NOT submitted yet",Toast.LENGTH_LONG).show()
                        val launch=ctx.packageManager.getLaunchIntentForPackage("com.nextbillion.groww")
                        if(launch!=null){
                            launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                            ctx.startActivity(launch)
                        }else{
                            runCatching{
                                ctx.startActivity(Intent(Intent.ACTION_VIEW,Uri.parse("https://groww.in/")).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                            }.onFailure{
                                Toast.makeText(ctx,"Groww app not found",Toast.LENGTH_LONG).show()
                            }
                        }
                    }
                },enabled=qty>0){Text("Open Groww")}
            }
'''
new='''                Text("Manual order • NSE CASH MARKET. Nothing is sent until you tap PLACE ORDER. The displayed stop and target are strategy references; this version submits the entry order only.",style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
            }},
            dismissButton={TextButton(onClick={if(!submitting){showOrder=false}},enabled=!submitting){Text("Cancel")}},
            confirmButton={
                Button(onClick={
                    if(qty<=0){
                        Toast.makeText(ctx,"Budget insufficient for one share",Toast.LENGTH_LONG).show()
                    }else if(vm==null){
                        Toast.makeText(ctx,"Order service unavailable",Toast.LENGTH_LONG).show()
                    }else{
                        submitting=true
                        vm.placeManualOrder(symbol,side,product,qty){ok,message->
                            submitting=false
                            if(ok){
                                showOrder=false
                                AppNotifier.notifyPreparedOrder(ctx,symbol,side,product,qty,plan.entry,plan.stop,plan.target1)
                                Toast.makeText(ctx,message,Toast.LENGTH_LONG).show()
                            }else{
                                Toast.makeText(ctx,"Order not placed: "+message,Toast.LENGTH_LONG).show()
                            }
                        }
                    }
                },enabled=qty>0&&!submitting&&vm!=null){Text(if(submitting)"PLACING…" else "PLACE ORDER")}
            }
'''
s=rep(s,old,new,"replace Groww handoff with manual submission")
if s.count("orderable=true)")!=3:
    raise SystemExit(f"expected 3 orderable cards, found {s.count('orderable=true)')}")
s=s.replace("orderable=true)","orderable=true,vm=vm)")
s=s.replace("CNC broker handoff","CNC manual order")
s=s.replace("tap MODEL score to prepare order","tap MODEL score to place manually")
# Remove now-unused handoff imports.
s=s.replace("import android.content.Intent\n","").replace("import android.net.Uri\n","")
wr(p,s)

# Notification wording must reflect an actually accepted manual order.
p="app/src/main/java/com/suhas/ucsentinel/notifications/AppNotifier.kt"; s=rw(p)
s=rep(s,'.setContentTitle("Order ready — NOT submitted")','.setContentTitle("Manual order submitted")',"notification title")
s=rep(s,'text+"\\nNo broker order has been sent. Open Groww to review and submit."','text+"\\nSubmitted to Groww after your explicit PLACE ORDER confirmation."',"notification detail")
wr(p,s)

print("Global Edge v1.3.0 manual Groww order submission applied")
