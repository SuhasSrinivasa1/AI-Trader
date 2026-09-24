#!/usr/bin/env python3
from pathlib import Path
import sys
root=Path(sys.argv[1]).resolve()
p=root/"app/src/main/java/com/suhas/ucsentinel/ui/CompactMarketScreens.kt"
s=p.read_text(encoding="utf-8")
old='vm.placeManualOrder(symbol,side,product,qty){ok,message->'
new='vm.placeManualOrder(symbol,side,product,qty,plan.entry){ok,message->'
if s.count(old)!=1: raise SystemExit(f"manual order UI anchor expected 1 found {s.count(old)}")
s=s.replace(old,new,1)
p.write_text(s,encoding="utf-8")
print("PLACE ORDER now passes expected entry for execution reconciliation")
