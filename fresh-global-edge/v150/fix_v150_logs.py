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

idx=s.find("suspend fun runLearningCycle")
if idx<0: raise SystemExit("runLearningCycle not found")
brace=s.find("{",idx)
if brace<0: raise SystemExit("runLearningCycle body not found")
s=s[:brace+1]+r'''
        runCatching{resolveChallengerShadows()}.onFailure{DiagnosticLog.log(appContext,"CHALLENGER","Scheduled-horizon resolver failed",it)}
        runCatching{reconcileBrokerOrders()}.onFailure{DiagnosticLog.log(appContext,"BROKER-RECON","Learning-cycle reconciliation failed",it)}
'''+s[brace+1:]

needle='''        appendLine("--- REJECTED-CANDIDATE SHADOW / MISSED OPPORTUNITIES ---")
'''
extra=r'''        appendLine("--- EVIDENCE FABRIC / POINT-IN-TIME ---")
        val ev=evidenceStore.loadEvidence(5000)
        appendLine("PIT evidence total=${ev.size} fundamentals=${ev.count{it.type==EvidenceType.FUNDAMENTAL}} analyst=${ev.count{it.type==EvidenceType.ANALYST_REVISION}} earnings=${ev.count{it.type==EvidenceType.EARNINGS_DATE}}")
        appendLine("Calendar="+NseTradingCalendar2026.VERSION+" • "+NseTradingCalendar2026.sessionLabel(LocalDate.now(ist)))
        MacroEventRegistry.next(LocalDate.now(ist))?.let{appendLine("Next macro event: ${it.label} • ${it.start}..${it.end}")}
        appendLine("Sector contexts cached=${latestSectorContext.size}")
        val cs=evidenceStore.loadChallengers(3000)
        appendLine("Challenger shadows total=${cs.size} open=${cs.count{it.status==ChallengerShadowStatus.OPEN}} win=${cs.count{it.status==ChallengerShadowStatus.WIN}} loss=${cs.count{it.status==ChallengerShadowStatus.LOSS}} unresolved=${cs.count{it.status==ChallengerShadowStatus.UNRESOLVED_DATA}}")
        val bo=evidenceStore.loadBrokerOrders(500)
        appendLine("Broker orders=${bo.size} unreconciled/remaining=${bo.count{it.lastReconciledAt==0L||it.remainingQuantity>0}}")
        appendLine("Decision snapshots=${evidenceStore.loadDecisions(1500).size}")
'''+needle
s=one(s,needle,extra,"weekly evidence logs")

needle='''        val calls=prefs.loadTradeCalls(1500)
        appendLine("--- TRADE CALL LEDGER ("+calls.size+") ---")
'''
extra=r'''        val pit=evidenceStore.loadEvidence(5000)
        appendLine("--- POINT-IN-TIME EVIDENCE ("+pit.size+") ---")
        pit.sortedBy{it.observedAt}.forEach{appendLine(it.toString())}
        appendLine()
        val challengers=evidenceStore.loadChallengers(3000)
        appendLine("--- CHALLENGER SHADOW LEDGER ("+challengers.size+") ---")
        challengers.sortedBy{it.openedAt}.forEach{appendLine(it.toString())}
        appendLine()
        val broker=evidenceStore.loadBrokerOrders(500)
        appendLine("--- BROKER ORDER/FILL RECONCILIATION ("+broker.size+") ---")
        broker.sortedBy{it.submittedAt}.forEach{appendLine(it.toString())}
        appendLine()
        val decisions=evidenceStore.loadDecisions(1500)
        appendLine("--- DECISION SNAPSHOTS ("+decisions.size+") ---")
        decisions.sortedBy{it.decisionAt}.forEach{appendLine(it.toString())}
        appendLine()
        val calls=prefs.loadTradeCalls(1500)
        appendLine("--- TRADE CALL LEDGER ("+calls.size+") ---")
'''
s=one(s,needle,extra,"EOD evidence logs")

wr(p,s)
print('v1.5 learning + evidence logs applied')
