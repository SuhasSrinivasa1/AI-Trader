#!/usr/bin/env python3
from pathlib import Path
import sys
root=Path(sys.argv[1]).resolve()

def rw(rel): return (root/rel).read_text(encoding="utf-8")
def wr(rel,s): (root/rel).write_text(s,encoding="utf-8")
def one(s,old,new,label):
    n=s.count(old)
    if n!=1: raise SystemExit(f"{label}: expected 1 found {n}")
    return s.replace(old,new,1)

p="app/build.gradle.kts"; s=rw(p)
s=one(s,"versionCode = 156","versionCode = 157","versionCode")
s=one(s,'versionName = "1.5.6"','versionName = "1.5.7"',"versionName")
wr(p,s)

p="app/src/main/java/com/suhas/ucsentinel/domain/engine/ScannerEngine.kt"; s=rw(p)

old='''        // Actionable UC candidates are NSE EQ only. BE/BZ/SM/ST can be visible on exchanges but
        // are frequently non-intraday / trade-to-trade / illiquid, so they are research-only and
        // must never occupy a LIVE/WATCH execution slot.
        val cash = universe
            .filter { ExecutionQuality.eligibleInstrument(it) }
            .filterNot { looksLikeEtf(it) }

        progress("Batch OHLC screening __D__{cash.size} NSE cash instruments")
'''.replace("__D__","$")
new='''        // Full-universe discovery: every buy-allowed NSE CASH equity from Groww's instrument
        // master is Stage-1 screened. Series is not used as a sampling shortcut; execution
        // suitability is decided later from live quote/liquidity and broker permissions.
        val cash = universe
            .filter { it.exchange=="NSE" && it.segment=="CASH" && it.instrumentType=="EQ" && it.buyAllowed }
            .filterNot { looksLikeEtf(it) }
            .distinctBy { it.tradingSymbol }

        progress("UC: FULL NSE equity Stage-1 __D__{cash.size} stocks • OHLC batches of 50")
'''.replace("__D__","$")
s=one(s,old,new,"UC full universe")

old='''        val rankedPrelim=prelim.sortedByDescending{(_,o)->
            if(o.close<=0.0||o.open<=0.0)-999.0 else ((o.close/o.open-1.0)*150.0-(o.high/o.close-1.0)*100.0)
        }.take(settings.maxQuotesPerScan)

        progress("Confirming __D__{rankedPrelim.size} shortlisted stocks with full quote/depth")
'''.replace("__D__","$")
new='''        val rankedAll=prelim.sortedByDescending{(_,o)->
            if(o.close<=0.0||o.open<=0.0)-999.0 else ((o.close/o.open-1.0)*150.0-(o.high/o.close-1.0)*100.0)
        }

        // No fixed/random sample: top names are always rechecked and the remaining qualifying
        // names are partitioned by the 5-minute cycle so every Stage-1 candidate is exhaustively
        // covered across successive passes without violating Groww Live Data limits.
        val quoteBudget=220
        val alwaysTop=rankedAll.take(40)
        val rest=rankedAll.drop(40)
        val partitions=if(rest.isEmpty())1 else kotlin.math.ceil(rest.size.toDouble()/(quoteBudget-alwaysTop.size).coerceAtLeast(1)).toInt().coerceAtLeast(1)
        val cycle=(System.currentTimeMillis()/(5L*60_000L)).toInt()
        val phase=((cycle%partitions)+partitions)%partitions
        val rotatingBudget=(quoteBudget-alwaysTop.size).coerceAtLeast(0)
        val startIndex=(phase*rotatingBudget).coerceAtMost(rest.size)
        val rotating=if(startIndex>=rest.size)emptyList() else rest.drop(startIndex).take(rotatingBudget)
        val rankedPrelim=(alwaysTop+rotating).distinctBy{it.first.tradingSymbol}
        val deferred=(rankedAll.size-rankedPrelim.size).coerceAtLeast(0)

        progress("UC: quote/depth __D__{rankedPrelim.size}/__D__{rankedAll.size} qualifying stocks • queued __D__deferred • exhaustive rolling coverage")
'''.replace("__D__","$")
s=one(s,old,new,"UC exhaustive quote queue")

old='''        val funnel="funnel raw __D__{candidates.size} • score __D__{scoreQualifiedCount} • UC-ready __D__{liveReadyCount} • execution-ready __D__{executionReadyCount} • LIVE __D__{qualified.size}"
'''.replace("__D__","$")
new='''        val funnel="FULL NSE __D__{cash.size} • Stage1 __D__{rankedAll.size} • quoted __D__{rankedPrelim.size} • queued __D__{deferred} • raw __D__{candidates.size} • score __D__{scoreQualifiedCount} • UC-ready __D__{liveReadyCount} • execution-ready __D__{executionReadyCount} • LIVE __D__{qualified.size}"
'''.replace("__D__","$")
s=one(s,old,new,"UC funnel full universe")

wr(p,s)
print("Global Edge v1.5.7 UC full-universe exhaustive rolling scanner applied")
