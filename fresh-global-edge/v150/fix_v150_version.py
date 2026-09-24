#!/usr/bin/env python3
from pathlib import Path
import sys
root=Path(sys.argv[1]).resolve()
p=root/"app/build.gradle.kts"
s=p.read_text(encoding="utf-8")
if s.count("versionCode = 140")!=1: raise SystemExit("versionCode 140 not found exactly once")
if s.count('versionName = "1.4.0"')!=1: raise SystemExit("versionName 1.4.0 not found exactly once")
s=s.replace("versionCode = 140","versionCode = 150",1).replace('versionName = "1.4.0"','versionName = "1.5.0"',1)
p.write_text(s,encoding="utf-8")
print("Global Edge version set to 1.5.0 / 150")
