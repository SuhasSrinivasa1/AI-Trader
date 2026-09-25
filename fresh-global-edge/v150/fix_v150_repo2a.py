#!/usr/bin/env python3
from pathlib import Path
import sys
root=Path(sys.argv[1]).resolve()
def rw(rel): return (root/rel).read_text(encoding="utf-8")
def wr(rel,s): (root/rel).write_text(s,encoding="utf-8")
def one(s,old,new,label):
    n=s.count(old)
    if n!=1: raise SystemExit(f"{label}: expected 1, found {n}")
    return s.replace(old,new,1)
p="app/src/main/java/com/suhas/ucsentinel/data/repository/UCSentinelRepository.kt";s=rw(p)

anchor='''    private data class CallPlan(val entry:Double,val stop:Double,val target:Double,val target2:Double?=null)

'''
insert=anchor+r'''    private fun recordDecisionSnapshot(
        symbol:String,direction:String,engine:String,strategyId:String,action:String,score:Double,
        reason:String,hardGate:Boolean=false,nowMs:Long=System.currentTimeMillis()
    ){
        val sector=latestSectorContext[symbol]
        val evidence=evidenceStore.evidenceAt(symbol,nowMs).take(20)
        val raw=listOf(symbol,direction,engine,strategyId,action,"%.4f".format(score),nowMs.toString(),
            NseTradingCalendar2026.VERSION,sector?.industry.orEmpty(),"%.4f".format(sector?.breadthPct?:0.0),
            "%.4f".format(sector?.stockVsSectorPct?:0.0),reason,evidence.joinToString(","){it.id}).joinToString("|")
        val hash=evidenceStore.decisionHash(raw)
        val rec=DecisionSnapshot(
            id="DEC-"+hash.take(20),symbol=symbol,direction=direction,engine=engine,strategyId=strategyId,action=action,
            score=score,decisionAt=nowMs,calendarVersion=NseTradingCalendar2026.VERSION,industry=sector?.industry.orEmpty(),
            sectorBreadthPct=sector?.breadthPct?:0.0,stockVsSectorPct=sector?.stockVsSectorPct?:0.0,
            evidenceIds=evidence.map{it.id},hardGate=hardGate,reason=reason.take(500),decisionHash=hash
        )
        evidenceStore.saveDecision(rec)
        DiagnosticLog.log(appContext,"DECISION","$action • $engine • $symbol • $direction • $strategyId • score=${"%.1f".format(score)} • ${reason.take(180)} • hash=${hash.take(12)}")
    }

'''
s=one(s,anchor,insert,"decision helper")

needle='''        prefs.appendRejectedShadow(RejectedCandidateRecord(
            id="REJECT|STRATEGY|${s.direction.name}|${s.symbol}|$nowMs",engineLabel="STRATEGY",symbol=s.symbol,direction=s.direction,
            score=s.score,entryPrice=plan.entry,stopPrice=plan.stop,targetPrice=plan.target,capturedAt=nowMs,
            targetSessionDate=targetSessionFor(TradeCallBucket.LIVE,nowMs).toString(),
            reason=reason+" • STRAT="+s.strategyId+(if(s.researchSignature.isBlank())"" else " • SIG="+s.researchSignature.take(140))
        ))
'''
replacement=needle+'''        recordDecisionSnapshot(s.symbol,s.direction.name,"STRATEGY",s.strategyId,"REJECTED",s.score,reason,true,nowMs)
'''
s=one(s,needle,replacement,"rejected strategy decision")

needle='''            ledger+=TradeCallRecord(id,engine,bucket,c.symbol,c.companyName,TradeDirection.LONG,c.score,plan.entry,plan.stop,plan.target,plan.target2,nowMs,targetSessionFor(bucket,nowMs).toString(),source,detail)
            added++
'''
replacement='''            ledger+=TradeCallRecord(id,engine,bucket,c.symbol,c.companyName,TradeDirection.LONG,c.score,plan.entry,plan.stop,plan.target,plan.target2,nowMs,targetSessionFor(bucket,nowMs).toString(),source,detail)
            recordDecisionSnapshot(c.symbol,TradeDirection.LONG.name,engine.name,"",bucket.name+"_PUBLISHED",c.score,source,false,nowMs)
            added++
'''
s=one(s,needle,replacement,"candidate published decision")

needle='''        prefs.appendRejectedShadow(RejectedCandidateRecord(
            id="REJECT|${engine.name}|${bucket.name}|${c.symbol}|$nowMs",engineLabel=engine.name,symbol=c.symbol,direction=TradeDirection.LONG,
            score=c.score,entryPrice=plan.entry,stopPrice=plan.stop,targetPrice=plan.target,capturedAt=nowMs,
            targetSessionDate=targetSessionFor(bucket,nowMs).toString(),reason=reason
        ))
'''
replacement=needle+'''        recordDecisionSnapshot(c.symbol,TradeDirection.LONG.name,engine.name,"","REJECTED",c.score,reason,true,nowMs)
'''
s=one(s,needle,replacement,"candidate rejected decision")

needle='''            ledger+=TradeCallRecord(id,TradeCallEngine.GLOBAL,bucket,c.indianSymbol,c.indianCompany,direction,c.score,plan.entry,plan.stop,plan.target,plan.target2,nowMs,targetSessionFor(bucket,nowMs).toString(),"Global ${bucket.name}",detail,globalLearningKey(c))
            added++
'''
replacement='''            ledger+=TradeCallRecord(id,TradeCallEngine.GLOBAL,bucket,c.indianSymbol,c.indianCompany,direction,c.score,plan.entry,plan.stop,plan.target,plan.target2,nowMs,targetSessionFor(bucket,nowMs).toString(),"Global ${bucket.name}",detail,globalLearningKey(c))
            recordDecisionSnapshot(c.indianSymbol,direction.name,TradeCallEngine.GLOBAL.name,"",bucket.name+"_PUBLISHED",c.score,detail,false,nowMs)
            added++
'''
s=one(s,needle,replacement,"global published decision")

needle='''        prefs.appendRejectedShadow(RejectedCandidateRecord(
            id="REJECT|GLOBAL|${direction.name}|${c.indianSymbol}|$nowMs",engineLabel=TradeCallEngine.GLOBAL.name,symbol=c.indianSymbol,direction=direction,
            score=c.score,entryPrice=plan.entry,stopPrice=plan.stop,targetPrice=plan.target,capturedAt=nowMs,
            targetSessionDate=targetSessionFor(bucket,nowMs).toString(),reason=reason
        ))
'''
replacement=needle+'''        recordDecisionSnapshot(c.indianSymbol,direction.name,TradeCallEngine.GLOBAL.name,"","REJECTED",c.score,reason,true,nowMs)
'''
s=one(s,needle,replacement,"global rejected decision")

anchor='''    suspend fun reconcileRejectedShadows():Int{
'''
challenger=r'''    private fun recordChallengerShadow(setup:StrategySetup,now:ZonedDateTime,horizonMinutes:Int=30){
        val end=now.toLocalDate().atTime(15,30).atZone(ist)
        val desired=now.plusMinutes(horizonMinutes.toLong())
        val horizon=if(desired.isAfter(end))end else desired
        if(!horizon.isAfter(now.plusMinutes(4)))return
        val existing=evidenceStore.loadChallengers(3000).any{
            it.status==ChallengerShadowStatus.OPEN&&it.strategyId==setup.strategyId&&it.symbol==setup.symbol&&it.direction==setup.direction&&
                System.currentTimeMillis()-it.openedAt<45L*60_000L
        }
        if(existing)return
        val id="CHAL|${setup.strategyId}|${setup.direction.name}|${setup.symbol}|${System.currentTimeMillis()}"
        val rec=ChallengerShadowRecord(
            id=id,strategyId=setup.strategyId,strategyName=setup.strategyName,symbol=setup.symbol,direction=setup.direction,
            entryPrice=setup.entryPrice,score=setup.score,openedAt=System.currentTimeMillis(),horizonAt=horizon.toInstant().toEpochMilli(),
            horizonMinutes=horizonMinutes,targetPct=setup.targetPct,stopPct=setup.stopPct,evidence=setup.evidence.take(900),
            calendarVersion=NseTradingCalendar2026.VERSION
        )
        evidenceStore.saveChallenger(rec)
        recordDecisionSnapshot(setup.symbol,setup.direction.name,"STRATEGY",setup.strategyId,"CHALLENGER_SHADOW",setup.score,"Non-executable prospective shadow • scheduled horizon $horizon",false,rec.openedAt)
        DiagnosticLog.log(appContext,"CHALLENGER","OPEN ${setup.strategyId} ${setup.symbol} ${setup.direction} entry=${"%.2f".format(setup.entryPrice)} horizon=$horizon")
    }

    suspend fun runChallengerShadowPass():Int{
        val before=evidenceStore.loadChallengers(3000).size
        scanTradingStrategies()
        val after=evidenceStore.loadChallengers(3000).size
        return (after-before).coerceAtLeast(0)
    }

    suspend fun resolveChallengerShadows():Int{
        val all=evidenceStore.loadChallengers(3000)
        val due=all.filter{it.status==ChallengerShadowStatus.OPEN&&System.currentTimeMillis()>=it.horizonAt+90_000L}
        if(due.isEmpty())return 0
        if(!ensureAutomationAuthentication())return 0
        val token=accessToken();var changed=0
        for(r in due.take(80)){
            val horizon=Instant.ofEpochMilli(r.horizonAt).atZone(ist)
            val start=horizon.minusMinutes(7).format(dateTimeFmt)
            val end=horizon.plusMinutes(12).format(dateTimeFmt)
            val candles=runCatching{groww.getHistoricalCandles(token,r.symbol,start,end,"5minute")}.getOrNull()
            if(candles.isNullOrEmpty()){
                val age=System.currentTimeMillis()-r.horizonAt
                if(age>24L*60*60*1000L){
                    evidenceStore.saveChallenger(r.copy(status=ChallengerShadowStatus.UNRESOLVED_DATA,resolvedAt=System.currentTimeMillis(),resolutionNote="No historical candle available around scheduled horizon"))
                    changed++
                }
                continue
            }
            val targetSec=r.horizonAt/1000L
            val candle=candles.filter{it.epochSeconds>=targetSec-60L}.minByOrNull{kotlin.math.abs(it.epochSeconds-targetSec)}
            if(candle==null)continue
            val px=candle.close.takeIf{it.isFinite()&&it>0.0}?:continue
            val ret=if(r.direction==TradeDirection.LONG)(px/r.entryPrice-1.0)*100.0 else (r.entryPrice/px-1.0)*100.0
            val win=ret>0.0
            val resolved=r.copy(
                status=if(win)ChallengerShadowStatus.WIN else ChallengerShadowStatus.LOSS,
                resolvedAt=System.currentTimeMillis(),horizonPrice=px,returnPct=ret,
                resolutionNote="Scheduled-horizon 5-minute historical close • target ${horizon.toLocalTime()}"
            )
            evidenceStore.saveChallenger(resolved);changed++
            DiagnosticLog.log(appContext,"CHALLENGER","RESOLVE ${r.strategyId} ${r.symbol} ${resolved.status} horizonPx=${"%.2f".format(px)} return=${"%+.2f".format(ret)}%")
        }
        return changed
    }

'''+anchor
s=one(s,anchor,challenger,"challenger resolver")


wr(p,s)
print('v1.5 decisions and challenger lane applied')
