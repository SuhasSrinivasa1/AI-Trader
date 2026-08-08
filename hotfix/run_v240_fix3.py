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

# Use a compact delimiter-safe signed wire format instead of org.json for the
# hot LAN path. Base64 never contains '|', so parsing is deterministic on both
# Android and host JVM tests and also avoids JSON allocation/number conversion.
old_envelope = r'''    static String envelope(String raw, long sourcePostTime, long sentAt) throws Exception {
        String b64 = Base64.getEncoder().encodeToString(raw.getBytes(StandardCharsets.UTF_8));
        String id = sha256(sourcePostTime + "|" + raw);
        String core = id + "|" + sourcePostTime + "|" + sentAt + "|" + b64;
        JSONObject o = new JSONObject();
        o.put("v", 1); o.put("id", id); o.put("post", sourcePostTime);
        o.put("sent", sentAt); o.put("raw", b64); o.put("sig", hmac(core));
        return o.toString();
    }
    static Signal parse(String line) throws Exception {
        JSONObject o = new JSONObject(line);
        String id = o.getString("id"); long post = o.getLong("post");
        long sent = o.getLong("sent"); String b64 = o.getString("raw");
        String sig = o.getString("sig");
        String core = id + "|" + post + "|" + sent + "|" + b64;
        if (!constantTime(sig, hmac(core))) throw new SecurityException("bad relay signature");
        String raw = new String(Base64.getDecoder().decode(b64), StandardCharsets.UTF_8);
        if (!id.equals(sha256(post + "|" + raw))) throw new SecurityException("bad relay id");
        return new Signal(id, post, sent, raw);
    }
'''
new_envelope = r'''    static String envelope(String raw, long sourcePostTime, long sentAt) throws Exception {
        String b64 = Base64.getEncoder().encodeToString(raw.getBytes(StandardCharsets.UTF_8));
        String id = sha256(sourcePostTime + "|" + raw);
        String core = "SIGNAL|" + id + "|" + sourcePostTime + "|" + sentAt + "|" + b64;
        return core + "|" + hmac(core);
    }
    static Signal parse(String line) throws Exception {
        String[] p = line == null ? new String[0] : line.split("\\|", -1);
        if (p.length != 6 || !"SIGNAL".equals(p[0])) {
            throw new SecurityException("bad relay envelope");
        }
        String core = p[0] + "|" + p[1] + "|" + p[2] + "|" + p[3] + "|" + p[4];
        if (!constantTime(p[5], hmac(core))) throw new SecurityException("bad relay signature");
        String id = p[1];
        long post = Long.parseLong(p[2]);
        long sent = Long.parseLong(p[3]);
        String raw = new String(Base64.getDecoder().decode(p[4]), StandardCharsets.UTF_8);
        if (!id.equals(sha256(post + "|" + raw))) throw new SecurityException("bad relay id");
        return new Signal(id, post, sent, raw);
    }
'''
for module in ("app", "child"):
    p = ROOT / module / "src/main/java/com/suhas/multyfiautobuy/stable/LanRelayProtocol.java"
    patch(p, old_envelope, new_envelope)
    text = p.read_text(encoding="utf-8")
    assert 'String core = "SIGNAL|" + id' in text
    assert 'line.split("\\\\|", -1)' in text
    assert 'new JSONObject(line)' not in text

print("Applied v2.4.0 compact signed LAN wire-format fix")
