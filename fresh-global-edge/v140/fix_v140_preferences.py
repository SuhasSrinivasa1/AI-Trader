#!/usr/bin/env python3
from pathlib import Path
import re,sys
root=Path(sys.argv[1]).resolve()
p=root/"app/src/main/java/com/suhas/ucsentinel/data/local/AppPreferences.kt"
s=p.read_text(encoding="utf-8")

# Persist handbook research metadata on each strategy setup.
old='''.put("listingAgeDays",x.listingAgeDays?:-1).put("generatedAt",x.generatedAt)'''
new='''.put("listingAgeDays",x.listingAgeDays?:-1).put("generatedAt",x.generatedAt)
        .put("researchSignature",x.researchSignature).put("handbookQualityPct",finite(x.handbookQualityPct))
        .put("handbookPattern",x.handbookPattern).put("handbookCombination",x.handbookCombination)'''
if s.count(old)!=1: raise SystemExit("strategySetupToJson anchor mismatch")
s=s.replace(old,new,1)

old='''        x.optDouble("score"),x.optDouble("entryPrice"),x.optDouble("targetPct"),x.optDouble("stopPct"),x.optString("evidence"),
        x.optLong("listingAgeDays",-1).takeIf{it>=0},x.optLong("generatedAt")
    )'''
new='''        x.optDouble("score"),x.optDouble("entryPrice"),x.optDouble("targetPct"),x.optDouble("stopPct"),x.optString("evidence"),
        x.optLong("listingAgeDays",-1).takeIf{it>=0},x.optLong("generatedAt"),
        x.optString("researchSignature"),x.optDouble("handbookQualityPct"),x.optString("handbookPattern"),x.optString("handbookCombination")
    )'''
if s.count(old)!=1: raise SystemExit("strategySetupFromJson anchor mismatch")
s=s.replace(old,new,1)

# Replace strategy performance classification with chronological holdout, walk-forward,
# multiple-testing penalty and recent-decay suspension.
pattern=r'''    fun strategyPerformances\(defs:List<TradingStrategyDefinition>,settings:AppSettings\):List<StrategyPerformance>\{.*?\n    private fun wilsonLower'''
m=re.search(pattern,s,re.S)
if not m: raise SystemExit("strategyPerformances block not found")
replacement=r'''    fun strategyPerformances(defs:List<TradingStrategyDefinition>,settings:AppSettings):List<StrategyPerformance>{
        val legacy=runCatching{JSONObject(prefs.getString("strategy_stats","{}")?:"{}")}.getOrElse{JSONObject()}
        val durable=loadStrategyClosed(2000).filter{it.status==StrategyRecommendationStatus.WIN||it.status==StrategyRecommendationStatus.LOSS}
            .sortedBy{it.closedAt}
        fun winRate(rows:List<StrategyRecommendation>)=if(rows.isEmpty())0.0 else rows.count{it.status==StrategyRecommendationStatus.WIN}*100.0/rows.size
        fun avgReturn(rows:List<StrategyRecommendation>)=if(rows.isEmpty())0.0 else rows.map{finite(it.returnPct)}.average()
        fun maxDrawdown(rows:List<StrategyRecommendation>):Double{
            var equity=0.0;var peak=0.0;var trough=0.0
            rows.forEach{equity+=finite(it.returnPct);peak=maxOf(peak,equity);trough=minOf(trough,equity-peak)}
            return kotlin.math.abs(trough)
        }
        return defs.map{d->
            val rows=durable.filter{it.setup.strategyId==d.id}
            val x=legacy.optJSONObject(d.id)?:JSONObject()
            val n=if(rows.isNotEmpty())rows.size else x.optInt("observations").coerceAtLeast(0)
            val w=if(rows.isNotEmpty())rows.count{it.status==StrategyRecommendationStatus.WIN} else x.optInt("wins").coerceIn(0,n)
            val acc=if(n==0)0.0 else w*100.0/n
            val avg=if(rows.isNotEmpty())avgReturn(rows) else if(n==0)0.0 else finite(storedFinite(x,"sumReturn")/n)
            val floor=wilsonLower(w,n)*100.0
            val maxDd=if(rows.isNotEmpty())maxDrawdown(rows) else kotlin.math.abs(storedFinite(x,"maxDrawdown"))
            val holdoutSize=if(rows.isEmpty())0 else kotlin.math.ceil(rows.size*0.20).toInt().coerceAtLeast(4).coerceAtMost(rows.size)
            val holdout=if(holdoutSize>0)rows.takeLast(holdoutSize) else emptyList()
            val holdoutAcc=winRate(holdout);val holdoutAvg=avgReturn(holdout)
            val wfStable=rows.size>=18&&strategyWalkForwardStable(rows)
            val mtPenalty=multipleTestingPenaltyPct(n)
            val adjustedAcc=(acc-mtPenalty).coerceAtLeast(0.0)
            val recent=rows.takeLast(minOf(10,rows.size));val baseline=rows.dropLast(recent.size).takeLast(20)
            val recentAcc=winRate(recent);val recentAvg=avgReturn(recent);val baseAcc=winRate(baseline)
            val decayed=recent.size>=8&&(
                (recentAvg<=0.0&&recentAcc<40.0) ||
                (baseline.size>=8&&baseAcc-recentAcc>=25.0&&recentAvg<0.0)
            )
            val status=when{
                decayed->StrategyStatus.SUSPENDED
                n>=settings.strategyMinChampionSamples.coerceAtLeast(30)&&acc>=settings.strategyMinChampionAccuracy&&avg>0.0&&floor>=50.0&&
                    holdout.size>=6&&holdoutAcc>=50.0&&holdoutAvg>0.0&&wfStable&&adjustedAcc>=55.0->StrategyStatus.CHAMPION
                n>=18&&!wfStable->StrategyStatus.PROBATION
                n>=10&&avg<=0.0->StrategyStatus.PROBATION
                n>=5->StrategyStatus.ACTIVE
                else->StrategyStatus.CHALLENGER
            }
            StrategyPerformance(d.id,d.name,n,w,finite(acc),finite(avg),finite(avg),finite(maxDd),finite(floor),status)
        }.sortedWith(compareBy<StrategyPerformance>{it.status.ordinal}.thenByDescending{it.expectancyPct}.thenByDescending{it.accuracyPct})
    }

    private fun strategyWalkForwardStable(rows:List<StrategyRecommendation>):Boolean{
        val sorted=rows.sortedBy{it.closedAt}
        if(sorted.size<18)return false
        val firstTrain=(sorted.size*0.50).toInt().coerceAtLeast(8)
        val remaining=sorted.size-firstTrain
        val fold=(remaining/3).coerceAtLeast(3)
        var start=firstTrain;var stableFolds=0;var totalFolds=0
        while(start<sorted.size){
            val validation=sorted.subList(start,minOf(sorted.size,start+fold))
            if(validation.size<3)break
            val train=sorted.subList(0,start)
            val trainWin=train.count{it.status==StrategyRecommendationStatus.WIN}*100.0/train.size
            val valWin=validation.count{it.status==StrategyRecommendationStatus.WIN}*100.0/validation.size
            val valAvg=validation.map{finite(it.returnPct)}.average()
            totalFolds++
            if(valAvg>0.0&&valWin>=40.0&&kotlin.math.abs(trainWin-valWin)<=25.0)stableFolds++
            start+=fold
        }
        return totalFolds>=2&&stableFolds==totalFolds
    }

    private fun multipleTestingPenaltyPct(n:Int):Double{
        if(n<=0)return 100.0
        val variants=500.0
        return (kotlin.math.sqrt(2.0*kotlin.math.ln(variants)/n.toDouble())*10.0).coerceIn(2.0,18.0)
    }

    fun championResearchInsights(defs:List<TradingStrategyDefinition>,limit:Int=6):List<String>{
        val closed=loadStrategyClosed(2000).filter{it.status==StrategyRecommendationStatus.WIN||it.status==StrategyRecommendationStatus.LOSS}.sortedBy{it.closedAt}
        fun winRate(rows:List<StrategyRecommendation>)=if(rows.isEmpty())0.0 else rows.count{it.status==StrategyRecommendationStatus.WIN}*100.0/rows.size
        fun avg(rows:List<StrategyRecommendation>)=if(rows.isEmpty())0.0 else rows.map{finite(it.returnPct)}.average()
        data class Row(val text:String,val rank:Double)
        val rows=closed.filter{it.setup.researchSignature.isNotBlank()}.groupBy{it.setup.researchSignature}.mapNotNull{(sig,x)->
            if(x.size<5)return@mapNotNull null
            val hs=kotlin.math.ceil(x.size*0.25).toInt().coerceAtLeast(2).coerceAtMost(x.size);val h=x.takeLast(hs)
            val wr=winRate(x);val hw=winRate(h);val av=avg(x);val hav=avg(h);val penalty=multipleTestingPenaltyPct(x.size);val adj=wr-penalty
            val recent=x.takeLast(minOf(8,x.size));val decayed=recent.size>=6&&avg(recent)<=0.0&&winRate(recent)<40.0
            val label=if(decayed)"DECAY" else if(adj>=55.0&&hav>0.0&&hw>=50.0)"CHAMPION" else "WATCH"
            val display=sig.split("|").drop(1).joinToString(" • ").replace("_"," ").take(78)
            Row(label+" • "+display+" • n="+x.size+" • holdout "+"%.0f".format(hw)+"% • avg "+"%+.2f".format(av)+"% • MT-adj "+"%.1f".format(adj),adj+hav*10.0)
        }.sortedByDescending{it.rank}.take(limit).map{it.text}.toMutableList()

        val resolved=loadRejectedShadows(2500).filter{it.outcome!=RejectedShadowOutcome.PENDING}
        if(resolved.isNotEmpty()){
            val avoided=resolved.count{it.outcome==RejectedShadowOutcome.WOULD_LOSE};val missed=resolved.count{it.outcome==RejectedShadowOutcome.WOULD_WIN}
            rows.add(0,"REJECT JOURNAL • resolved "+resolved.size+" • avoided losses "+avoided+" • missed wins "+missed)
            val bestGate=resolved.groupBy{it.reason.substringBefore(" ").take(42)}.filterValues{it.size>=3}.maxByOrNull{(_,g)->g.count{it.outcome==RejectedShadowOutcome.WOULD_LOSE}-g.count{it.outcome==RejectedShadowOutcome.WOULD_WIN}}
            if(bestGate!=null){
                val g=bestGate.value
                rows.add(1,"GATE LEARNING • "+bestGate.key+" • "+g.count{it.outcome==RejectedShadowOutcome.WOULD_LOSE}+" losses avoided / "+g.count{it.outcome==RejectedShadowOutcome.WOULD_WIN}+" winners missed")
            }
        }
        return rows.take(limit+2)
    }

    private fun wilsonLower'''
s=s[:m.start()]+replacement+s[m.end():]

# Persist tournament research summary.
old='''        val perfs=JSONArray();summary.performances.forEach{x->perfs.put(JSONObject().put("strategyId",x.strategyId).put("name",x.name).put("observations",x.observations).put("wins",x.wins).put("accuracyPct",finite(x.accuracyPct)).put("avgReturnPct",finite(x.avgReturnPct)).put("expectancyPct",finite(x.expectancyPct)).put("maxDrawdownPct",finite(x.maxDrawdownPct)).put("confidenceFloorPct",finite(x.confidenceFloorPct)).put("status",x.status.name))}
        val root=JSONObject().put("generatedAt",summary.generatedAt).put("universeCount",summary.universeCount).put("strategiesRun",summary.strategiesRun).put("symbolsEnriched",summary.symbolsEnriched).put("catalogVersion",summary.catalogVersion).put("message",summary.message).put("topSetups",setups).put("activeStrategies",active).put("performances",perfs)'''
new='''        val perfs=JSONArray();summary.performances.forEach{x->perfs.put(JSONObject().put("strategyId",x.strategyId).put("name",x.name).put("observations",x.observations).put("wins",x.wins).put("accuracyPct",finite(x.accuracyPct)).put("avgReturnPct",finite(x.avgReturnPct)).put("expectancyPct",finite(x.expectancyPct)).put("maxDrawdownPct",finite(x.maxDrawdownPct)).put("confidenceFloorPct",finite(x.confidenceFloorPct)).put("status",x.status.name))}
        val insights=JSONArray();summary.championInsights.forEach{insights.put(it)}
        val root=JSONObject().put("generatedAt",summary.generatedAt).put("universeCount",summary.universeCount).put("strategiesRun",summary.strategiesRun).put("symbolsEnriched",summary.symbolsEnriched).put("catalogVersion",summary.catalogVersion).put("message",summary.message).put("topSetups",setups).put("activeStrategies",active).put("performances",perfs)
            .put("championInsights",insights).put("rejectedJournalCount",summary.rejectedJournalCount).put("handbookVersion",summary.handbookVersion)'''
if s.count(old)!=1: raise SystemExit("saveStrategySummary anchor mismatch")
s=s.replace(old,new,1)

# Replace compact one-line loader with a readable loader including new fields.
pattern=r'''    fun loadStrategySummary\(\):StrategyTournamentSummary\?\{.*?\n    fun loadStrategyLive'''
m=re.search(pattern,s,re.S)
if not m: raise SystemExit("loadStrategySummary block not found")
replacement=r'''    fun loadStrategySummary():StrategyTournamentSummary?{
        val raw=prefs.getString("strategy_tournament_summary",null)?:return null
        return runCatching{
            val j=JSONObject(raw);val setups=jsonToSetups(j.optJSONArray("topSetups")?:JSONArray());val defs=jsonToDefs(j.optJSONArray("activeStrategies")?:JSONArray())
            val pfs=j.optJSONArray("performances")?:JSONArray()
            val perfs=buildList{for(i in 0 until pfs.length()){val x=pfs.optJSONObject(i)?:continue;add(StrategyPerformance(x.optString("strategyId"),x.optString("name"),x.optInt("observations"),x.optInt("wins"),x.optDouble("accuracyPct"),x.optDouble("avgReturnPct"),x.optDouble("expectancyPct"),x.optDouble("maxDrawdownPct"),x.optDouble("confidenceFloorPct"),runCatching{StrategyStatus.valueOf(x.optString("status"))}.getOrDefault(StrategyStatus.CHALLENGER)))}}
            val ia=j.optJSONArray("championInsights")?:JSONArray();val insights=buildList{for(i in 0 until ia.length()){val v=ia.optString(i);if(v.isNotBlank())add(v)}}
            StrategyTournamentSummary(j.optLong("generatedAt"),j.optInt("universeCount"),j.optInt("strategiesRun"),j.optInt("symbolsEnriched"),setups,defs,perfs,j.optString("catalogVersion"),j.optString("message"),insights,j.optInt("rejectedJournalCount"),j.optString("handbookVersion"))
        }.getOrNull()
    }

    fun loadStrategyLive'''
s=s[:m.start()]+replacement+s[m.end():]

p.write_text(s,encoding="utf-8")
print("v1.4.0 champion governance + rejected-gate learning persistence applied")
