#!/usr/bin/env python3
from pathlib import Path
import shutil, sys

src=Path(sys.argv[1])
def edit(rel, pairs):
    p=src/rel; s=p.read_text()
    for old,new in pairs:
        if old not in s: raise SystemExit(f'missing expected text in {rel}: {old[:80]}')
        s=s.replace(old,new)
    p.write_text(s)

edit('app/build.gradle.kts',[
    ('versionCode = 143','versionCode = 144'),('versionName = "1.4.3"','versionName = "1.4.4"')])
edit('app/src/main/java/com/suhas/ucsentinel/data/remote/GlobalMarketClient.kt',[
    ('global-lead-mappings-v1.json','global-lead-mappings-v2.json'),
    ('UC-Sentinel/1.4 Android','UC-Sentinel/1.4.4 Android'),
    ('UC-Sentinel/1.4")','UC-Sentinel/1.4.4")')])
edit('app/src/main/java/com/suhas/ucsentinel/data/repository/UCSentinelRepository.kt',[
    ('mapped foreign counters for LONG + SHORT','global links for LONG + SHORT'),
    ('.score}.take(limit)','.score}.distinctBy{it.first.indianSymbol}.take(limit)')])
edit('app/src/main/java/com/suhas/ucsentinel/ui/GlobalLeadScreen.kt',[
    ('A gap alone is not enough: catch-up moves, benchmark excess return, abnormal volume and post-open follow-through are checked.',
     'A gap alone is not enough: catch-up moves, benchmark excess return, abnormal volume and post-open follow-through are checked. The weekly catalogue combines direct ADR/parent relationships with broad Nifty 500 sector/global proxies. Proxy links are lower-weight research signals, not claims that two companies are the same.'),
    (' • weekly refresh',' • weekly rebuilt coverage'),
    ('MetricCard("Mapped",summary.mappingsScanned.toString()','MetricCard("Global links",summary.mappingsScanned.toString()')])

asset=src/'app/src/main/assets/global_lead_mappings.json'
remote=Path(sys.argv[2]) if len(sys.argv)>2 else None
if not remote or not remote.exists(): raise SystemExit('generated Global Lead v2 catalogue is required')
shutil.copyfile(remote,asset)

for rel in ['README.md','SOURCE-VALIDATION.json']:
    p=src/rel
    if p.exists():
        s=p.read_text().replace('1.4.3','1.4.4').replace('"versionCode": 143','"versionCode": 144')
        p.write_text(s)

print('UC Sentinel v1.4.4 source upgrade applied')
