#!/usr/bin/env python3
from pathlib import Path
import runpy

runpy.run_path("hotfix/run_v224.py", run_name="__main__")

activity = Path(
    "android-stable/app/src/main/java/com/suhas/multyfiautobuy/stable/ProductionActivity.java"
)
text = activity.read_text(encoding="utf-8")
stale = (
    "Any complete recommendation containing the word FREE uses exactly 10 shares "
    "in every active market window; the normal MIS/CNC time routing remains unchanged."
)
if stale not in text:
    raise RuntimeError("Could not locate stale fixed-10 FREE dashboard wording")
text = text.replace(
    stale,
    "Free recommendations use the saved Free budget; order routing still follows explicit Intraday/MIS wording.",
    1,
)
activity.write_text(text, encoding="utf-8")

if "exactly 10 shares" in text or "FREE fixed quantity 10" in text:
    raise RuntimeError("Obsolete fixed-10 FREE wording remains in the dashboard")

print("Removed stale fixed-10 FREE wording from v2.2.4 dashboard")
