#!/usr/bin/env python3
from pathlib import Path
import runpy

runpy.run_path("hotfix/run_v240_fix.py", run_name="__main__")
ROOT = Path("android-stable")


def patch(path: Path, old: str, new: str, expected: int = 1) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != expected:
        raise RuntimeError(f"Expected {expected} matches in {path}, found {count}: {old[:180]}")
    path.write_text(text.replace(old, new, expected), encoding="utf-8")

# Keep signed timestamp fields as canonical decimal strings inside JSON. This
# avoids any org.json/JVM numeric representation differences during unit tests
# while still authenticating event id, post time, send time and exact raw body.
for module in ("app", "child"):
    p = ROOT / module / "src/main/java/com/suhas/multyfiautobuy/stable/LanRelayProtocol.java"
    patch(p,
          'o.put("v", 1); o.put("id", id); o.put("post", sourcePostTime);\n        o.put("sent", sentAt); o.put("raw", b64); o.put("sig", hmac(core));',
          'o.put("v", 1); o.put("id", id); o.put("post", Long.toString(sourcePostTime));\n        o.put("sent", Long.toString(sentAt)); o.put("raw", b64); o.put("sig", hmac(core));')
    patch(p,
          'String id = o.getString("id"); long post = o.getLong("post");\n        long sent = o.getLong("sent"); String b64 = o.getString("raw");',
          'String id = o.getString("id"); long post = Long.parseLong(o.getString("post"));\n        long sent = Long.parseLong(o.getString("sent")); String b64 = o.getString("raw");')

for module in ("app", "child"):
    text = (ROOT / module / "src/main/java/com/suhas/multyfiautobuy/stable/LanRelayProtocol.java").read_text(encoding="utf-8")
    assert 'o.put("post", Long.toString(sourcePostTime))' in text
    assert 'Long.parseLong(o.getString("post"))' in text

print("Applied v2.4.0 canonical signed timestamp relay fix")
