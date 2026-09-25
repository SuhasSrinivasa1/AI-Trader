#!/usr/bin/env python3
from pathlib import Path
import sys
root=Path(sys.argv[1]).resolve()
p=root/"app/src/main/java/com/suhas/ucsentinel/ui/AppNavigation.kt"
s=p.read_text(encoding="utf-8")
if "import androidx.compose.material.icons.filled.AccountBalanceWallet" not in s:
    s=s.replace("import androidx.compose.material.icons.filled.ArrowBack\n","import androidx.compose.material.icons.filled.ArrowBack\nimport androidx.compose.material.icons.filled.AccountBalanceWallet\n")
old='''    STRATEGIES("Strategies",Icons.Default.ShowChart),
    GLOBAL("Global",Icons.Default.Public)
'''
new='''    STRATEGIES("Strategies",Icons.Default.ShowChart),
    GLOBAL("Global",Icons.Default.Public),
    PORTFOLIO("Portfolio",Icons.Default.AccountBalanceWallet)
'''
if s.count(old)!=1: raise SystemExit("MainTab anchor mismatch")
s=s.replace(old,new,1)
old='''            MainTab.GLOBAL->GlobalCompactScreen(state,vm,padding)
'''
new='''            MainTab.GLOBAL->GlobalCompactScreen(state,vm,padding)
            MainTab.PORTFOLIO->PortfolioCompactScreen(state,vm,padding)
'''
if s.count(old)!=1: raise SystemExit("navigation branch anchor mismatch")
s=s.replace(old,new,1)
p.write_text(s,encoding="utf-8")
print("v1.5 Portfolio navigation applied")
