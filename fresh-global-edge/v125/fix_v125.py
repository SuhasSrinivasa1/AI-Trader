#!/usr/bin/env python3
from pathlib import Path
import re, sys

root=Path(sys.argv[1]).resolve()

def read(rel): return (root/rel).read_text(encoding="utf-8")
def write(rel,s): (root/rel).write_text(s,encoding="utf-8")
def rep(s,old,new,label):
    n=s.count(old)
    if n!=1: raise SystemExit(label+": expected 1 found "+str(n))
    return s.replace(old,new,1)

# version
p="app/build.gradle.kts"; s=read(p)
s=rep(s,"versionCode = 124","versionCode = 125","version code")
s=rep(s,'versionName = "1.2.4"','versionName = "1.2.5"',"version name")
write(p,s)

# DiagnosticLog: ZIP bundle writer
p="app/src/main/java/com/suhas/ucsentinel/diagnostics/DiagnosticLog.kt"; s=read(p)
s=s.replace("import java.io.File\n","import java.io.File\nimport java.io.OutputStream\nimport java.util.zip.ZipEntry\nimport java.util.zip.ZipOutputStream\n",1)
if "writeEndOfDayBundle" in s: raise SystemExit("bundle writer already present")
method = r'''
    fun writeEndOfDayBundle(
        context: Context,
        output: OutputStream,
        appVersion: String,
        stateReport: String,
        learningReport: String
    ) {
        val now=ZonedDateTime.now(ZoneId.of("Asia/Kolkata"))
        ZipOutputStream(output.buffered()).use { zip ->
            fun add(name:String,text:String){
                zip.putNextEntry(ZipEntry(name))
                zip.write(text.toByteArray(Charsets.UTF_8))
                zip.closeEntry()
            }
            add("README.txt", buildString {
                appendLine("Global Edge AI Trader end-of-day diagnostic bundle")
                appendLine("Version: "+appVersion)
                appendLine("Generated IST: "+now)
                appendLine("Purpose: reproduce scanner/scheduler/learning behaviour for debugging.")
                appendLine("SECURITY: Groww credentials, TOTP secret and access token are intentionally NOT exported.")
                appendLine()
                appendLine("state-report.txt = persisted engine/scheduler/call/learning state")
                appendLine("learning-report.txt = accuracy/calibration/walk-forward/autopsy/shadow summary")
                appendLine("global-edge-diagnostics.log = current runtime timeline")
                appendLine("global-edge-diagnostics.previous.log = previous rotated runtime timeline when present")
            })
            add("state-report.txt",stateReport)
            add("learning-report.txt",learningReport)
            val old=File(context.filesDir,"global-edge-diagnostics.previous.log")
            val current=file(context)
            if(old.exists()) add("global-edge-diagnostics.previous.log",old.readText())
            if(current.exists()) add("global-edge-diagnostics.log",current.readText())
        }
    }
'''
i=s.rfind("\n}")
if i<0: raise SystemExit("DiagnosticLog closing brace missing")
s=s[:i]+method+s[i:]
write(p,s)

# Repository: comprehensive safe persisted state report
p="app/src/main/java/com/suhas/ucsentinel/data/repository/UCSentinelRepository.kt"; s=read(p)
if "endOfDayDiagnosticReport" in s: raise SystemExit("report already present")
marker="    fun trimMemory(){newListingsCache=prefs.loadNewListings();instruments.clearCache();globalMarket.clearCache()}"
if marker not in s: raise SystemExit("trimMemory marker missing")
report=r'''
    fun endOfDayDiagnosticReport():String=buildString{
        val now=ZonedDateTime.now(ist)
        fun ts(ms:Long):String=if(ms<=0L)"never" else runCatching{Instant.ofEpochMilli(ms).atZone(ist).toString()}.getOrDefault(ms.toString())
        appendLine("=== GLOBAL EDGE END-OF-DAY STATE REPORT ===")
        appendLine("Generated IST: "+now)
        appendLine("Security: credentials/TOTP secret/access token omitted by design")
        appendLine("Authenticated token present: "+accessToken().isNotBlank()+" • expiry="+tokenExpiry())
        appendLine("Market session: "+marketSessionInfo(now))
        appendLine("Settings: "+prefs.loadSettings())
        appendLine()
        appendLine("--- SCHEDULER / DATA HEALTH ---")
        appendLine("lastMarketDataSuccessAt="+ts(prefs.lastMarketDataSuccessAt()))
        appendLine("lastPressureScanAt="+ts(prefs.lastPressureScanAt()))
        appendLine("lastNearCloseAutoScanAt="+ts(prefs.lastNearCloseAutoScanAt()))
        appendLine("lastLearningAt="+ts(prefs.lastLearningAt()))
        appendLine("lastAutonomousLearningAt="+ts(prefs.lastAutonomousLearningAt()))
        appendLine("lastGlobalLeadScanAt="+ts(prefs.lastGlobalLeadScanAt()))
        appendLine("lastGlobalMappingRefreshAt="+ts(prefs.lastGlobalMappingRefreshAt())+" • mappingVersion="+prefs.globalMappingVersion())
        appendLine("lastStrategyAttemptAt="+ts(prefs.lastStrategyAttemptAt()))
        appendLine("lastStrategyScanAt="+ts(prefs.lastStrategyScanAt()))
        appendLine("lastStrategyErrorAt="+ts(prefs.lastStrategyErrorAt())+" • lastStrategyError="+prefs.lastStrategyError())
        appendLine("lastStrategyCatalogRefreshAt="+ts(prefs.lastStrategyCatalogRefreshAt())+" • catalogVersion="+prefs.strategyCatalogVersion())
        appendLine("listingFeedHealth="+prefs.listingFeedHealth())
        appendLine()
        appendLine("--- CURRENT SCAN SUMMARIES ---")
        appendLine("DUAL_SCAN="+(lastSavedDualSummary()?.toString()?:"NONE"))
        appendLine("GLOBAL="+(prefs.loadGlobalLeadSummary()?.toString()?:"NONE"))
        appendLine("STRATEGY="+(prefs.loadStrategySummary()?.toString()?:"NONE"))
        appendLine()
        appendLine("--- MODEL ACCURACY / SIGNAL METRICS ---")
        appendLine("UC="+prefs.sectionAccuracy(ScannerSection.UC_CONTINUATION,SignalEngine.MODEL_VERSION))
        appendLine("PRESSURE="+prefs.sectionAccuracy(ScannerSection.DEMAND_SQUEEZE,DemandSignalEngine.MODEL_VERSION))
        prefs.signalMetrics().forEach{appendLine(it.toString())}
        appendLine()
        appendLine("--- FREEZE HISTORY ---")
        for(section in ScannerSection.entries){
            appendLine("SECTION="+section)
            prefs.freezeHistory(section,100).forEach{appendLine(it.toString())}
        }
        appendLine()
        val calls=prefs.loadTradeCalls(1500)
        appendLine("--- TRADE CALL LEDGER ("+calls.size+") ---")
        calls.sortedBy{it.openedAt}.forEach{appendLine(it.toString())}
        appendLine()
        val rejected=prefs.loadRejectedShadows(2500)
        appendLine("--- REJECTED / SHADOW CANDIDATES ("+rejected.size+") ---")
        rejected.sortedBy{it.capturedAt}.forEach{appendLine(it.toString())}
        appendLine()
        val autopsies=prefs.loadAutopsies(800)
        appendLine("--- POST-TRADE AUTOPSIES ("+autopsies.size+") ---")
        autopsies.forEach{appendLine(it.toString())}
        appendLine()
        val liveStrategy=prefs.loadStrategyLive()
        val closedStrategy=prefs.loadStrategyClosed(2000)
        appendLine("--- STRATEGY LIVE ("+liveStrategy.size+") ---")
        liveStrategy.forEach{appendLine(it.toString())}
        appendLine("--- STRATEGY CLOSED ("+closedStrategy.size+") ---")
        closedStrategy.forEach{appendLine(it.toString())}
        appendLine()
        val globalClosed=prefs.loadGlobalLeadClosed(2000)
        appendLine("--- GLOBAL CLOSED ("+globalClosed.size+") ---")
        globalClosed.forEach{appendLine(it.toString())}
        appendLine()
        appendLine("--- NEW LISTINGS CACHE ("+newListingsCache.size+") ---")
        newListingsCache.forEach{appendLine(it.toString())}
    }

'''
s=s.replace(marker,report+marker,1)
write(p,s)

# Settings: add EOD exporter before the first settings slider state
p="app/src/main/java/com/suhas/ucsentinel/ui/MoreScreen.kt"; s=read(p)
marker='    var uc by remember(state.settings.minScore){mutableFloatStateOf(state.settings.minScore.toFloat())}'
if marker not in s: raise SystemExit("Settings state marker missing")
exporter=r'''    val eodExporter=rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("application/zip")){uri->
        if(uri!=null){
            runCatching{
                val repo=(ctx.applicationContext as GlobalEdgeApplication).repository
                val out=ctx.contentResolver.openOutputStream(uri)?:error("Unable to open selected file")
                DiagnosticLog.writeEndOfDayBundle(
                    context=ctx,
                    output=out,
                    appVersion=BuildConfig.VERSION_NAME,
                    stateReport=repo.endOfDayDiagnosticReport(),
                    learningReport=repo.weeklyLearningReport()
                )
            }.onSuccess{
                DiagnosticLog.log(ctx,"EXPORT","End-of-day diagnostic bundle exported")
                logExportStatus="Full diagnostic ZIP saved • upload this file here for review"
            }.onFailure{logExportStatus="Diagnostic export failed: "+it.message}
        }
    }
'''
s=s.replace(marker,exporter+marker,1)
status='        if(!logExportStatus.isNullOrBlank())item{Text(logExportStatus!!,style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)}'
if status not in s: raise SystemExit("log status marker missing")
card=r'''        item{
            ElevatedCard(Modifier.fillMaxWidth()){
                Column(Modifier.padding(14.dp),verticalArrangement=Arrangement.spacedBy(8.dp)){
                    Text("End-of-day diagnostics",style=MaterialTheme.typography.titleMedium)
                    Text(
                        "Exports the complete retained runtime timeline plus scheduler timestamps, scan summaries, NEXT/LIVE/3PM/DONE calls, strategy/global ledgers, rejected-candidate shadows, calibration, walk-forward state and autopsies. Groww secrets/tokens are excluded.",
                        color=MaterialTheme.colorScheme.onSurfaceVariant,
                        style=MaterialTheme.typography.bodySmall
                    )
                    Button(
                        onClick={
                            val day=java.time.LocalDate.now(java.time.ZoneId.of("Asia/Kolkata"))
                            eodExporter.launch("Global-Edge-EOD-"+day+"-v"+BuildConfig.VERSION_NAME+".zip")
                        },
                        modifier=Modifier.fillMaxWidth()
                    ){Text("Export full EOD diagnostic ZIP")}
                }
            }
        }
'''
s=s.replace(status,card+status,1)
write(p,s)

# ScanWorker: log WorkManager fallback path
p="app/src/main/java/com/suhas/ucsentinel/worker/ScanWorker.kt"; s=read(p)
if "diagnostics.DiagnosticLog" not in s:
    s=s.replace("import com.suhas.globaledgeai.GlobalEdgeApplication\n","import com.suhas.globaledgeai.GlobalEdgeApplication\nimport com.suhas.globaledgeai.diagnostics.DiagnosticLog\n",1)
needle='        val forceMarketPass=inputData.getBoolean("force_market_pass",false)\n'
s=rep(s,needle,needle+'        DiagnosticLog.log(applicationContext,"WORKER","ScanWorker start • phase="+session.phase+" • force="+forceMarketPass)\n',"ScanWorker start")
s=rep(s,'            repo.ensureTodayFreezeAudit(nowZ);return Result.success()\n','            repo.ensureTodayFreezeAudit(nowZ)\n            DiagnosticLog.log(applicationContext,"WORKER","off-hours safety-net pass complete")\n            return Result.success()\n',"offhours worker log")
s=rep(s,'            automatedPass();Result.success()\n        }catch(t:Throwable){\n','            automatedPass()\n            DiagnosticLog.log(applicationContext,"WORKER","market safety-net pass complete")\n            Result.success()\n        }catch(t:Throwable){\n            DiagnosticLog.log(applicationContext,"WORKER","ScanWorker failed",t)\n',"worker failure log")
write(p,s)

# LearningWorker logging
p="app/src/main/java/com/suhas/ucsentinel/worker/LearningWorker.kt"; s=read(p)
if "diagnostics.DiagnosticLog" not in s:
    s=s.replace("import com.suhas.globaledgeai.GlobalEdgeApplication\n","import com.suhas.globaledgeai.GlobalEdgeApplication\nimport com.suhas.globaledgeai.diagnostics.DiagnosticLog\n",1)
old='''        if(!repo.settings().learningEnabled)return Result.success()

        return try{
            repo.runAutonomousLearningPass()
            Result.success()
        }catch(t:Throwable){
'''
new='''        if(!repo.settings().learningEnabled)return Result.success()
        DiagnosticLog.log(applicationContext,"LEARNING-WORKER","learning worker start")

        return try{
            val msg=repo.runAutonomousLearningPass()
            DiagnosticLog.log(applicationContext,"LEARNING-WORKER","learning worker success • "+msg)
            Result.success()
        }catch(t:Throwable){
            DiagnosticLog.log(applicationContext,"LEARNING-WORKER","learning worker failed",t)
'''
s=rep(s,old,new,"LearningWorker logging")
write(p,s)

print("Global Edge v1.2.5 EOD diagnostic export applied")
