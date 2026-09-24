#!/usr/bin/env python3
from pathlib import Path
import sys
root=Path(sys.argv[1]).resolve()
p=root/"app/src/main/java/com/suhas/ucsentinel/ui/AppNavigation.kt"
s=p.read_text(encoding="utf-8")
old='''private enum class MainTab(val label:String,val icon:ImageVector){
    UC("UC",Icons.Default.TrendingUp),
    STRATEGIES("Strategies",Icons.Default.ShowChart),
    GLOBAL("Global",Icons.Default.Public)
}'''
new='''private enum class MainTab(val label:String,val icon:ImageVector){
    UC("UC",Icons.Default.TrendingUp),
    STRATEGIES("Strategies",Icons.Default.ShowChart),
    INTEL("Intel",Icons.Default.Bolt),
    PORTFOLIO("Portfolio",Icons.Default.Settings),
    GLOBAL("Global",Icons.Default.Public)
}'''
if s.count(old)!=1: raise SystemExit("MainTab anchor mismatch")
s=s.replace(old,new,1)
old='''            MainTab.UC->UpperCircuitCompactScreen(state,vm,padding)
            MainTab.STRATEGIES->StrategiesCompactScreen(state,vm,padding)
            MainTab.GLOBAL->GlobalCompactScreen(state,vm,padding)
'''
new='''            MainTab.UC->UpperCircuitCompactScreen(state,vm,padding)
            MainTab.STRATEGIES->StrategiesCompactScreen(state,vm,padding)
            MainTab.INTEL->TradeIntelligenceScreen(state,vm,padding)
            MainTab.PORTFOLIO->PortfolioScreen(state,vm,padding)
            MainTab.GLOBAL->GlobalCompactScreen(state,vm,padding)
'''
if s.count(old)!=1: raise SystemExit("navigation branch anchor mismatch")
s=s.replace(old,new,1)
p.write_text(s,encoding="utf-8")
print("Trade Intelligence and Portfolio added to main navigation")
