#!/usr/bin/env bash
set -euo pipefail
ROOT="${GITHUB_WORKSPACE:?}"
rm -rf /tmp/global-edge-v103
mkdir -p /tmp/global-edge-v103

cat "$ROOT"/android-stable/uc-sentinel-v131-build/source.b64.part00 \
    "$ROOT"/android-stable/uc-sentinel-v131-build/source.b64.part01 \
    "$ROOT"/android-stable/uc-sentinel-v131-build/source.b64.part02 \
    "$ROOT"/android-stable/uc-sentinel-v131-build/source.b64.part03 \
    "$ROOT"/android-stable/uc-sentinel-v131-build/source.b64.part04 \
    "$ROOT"/android-stable/uc-sentinel-v131-build/source.b64.part05 \
    "$ROOT"/android-stable/uc-sentinel-v131-build/source.b64.part06 \
    "$ROOT"/android-stable/uc-sentinel-v131-build/source.b64.part07 \
  | tr -d '\r\n ' | base64 -d > /tmp/UC-Sentinel-v1.3.1-full-source.zip
echo 'f6c0aabbf204896125e2a4c7521b997520b84589fb74c3ce8ef63ae26d5d5019  /tmp/UC-Sentinel-v1.3.1-full-source.zip' | sha256sum -c -
unzip -q /tmp/UC-Sentinel-v1.3.1-full-source.zip -d /tmp/global-edge-v103
mv /tmp/global-edge-v103/UC-Sentinel-v1.3.1-full-source /tmp/global-edge-v103/UC-Sentinel-v1.3.2-full-source
cd /tmp/global-edge-v103/UC-Sentinel-v1.3.2-full-source
patch -p1 --batch < "$ROOT/android-stable/uc-sentinel-v132-build/v131-to-v132.patch"

cat "$ROOT/android-stable/uc-sentinel-v140-build/v132-to-v140.patch.gz.b64.part00" \
    "$ROOT/android-stable/uc-sentinel-v140-build/v132-to-v140.patch.gz.b64.part01" \
    "$ROOT/android-stable/uc-sentinel-v140-build/v132-to-v140.patch.gz.b64.part02" \
  | tr -d '\r\n ' | base64 -d > /tmp/v132-to-v140.patch.gz
echo 'd4457813b26d0d01380360dca3ce0434d4aa8217e814870828d97ef13d131dcf  /tmp/v132-to-v140.patch.gz' | sha256sum -c -
gunzip -c /tmp/v132-to-v140.patch.gz > /tmp/v132-to-v140.patch
patch -p1 --batch < /tmp/v132-to-v140.patch

cd /tmp/global-edge-v103
mv UC-Sentinel-v1.3.2-full-source UC-Sentinel-v1.4.0-full-source
cd UC-Sentinel-v1.4.0-full-source
cat "$ROOT/android-stable/uc-sentinel-v141-build/v140-to-v141.patch.gz.b64" | tr -d '\r\n ' | base64 -d > /tmp/v140-to-v141.patch.gz
echo '36f4b163cb83b79b581652a7687cf169155a9433e1103ce9dca483907a6ed537  /tmp/v140-to-v141.patch.gz' | sha256sum -c -
gunzip -c /tmp/v140-to-v141.patch.gz > /tmp/v140-to-v141.patch
patch -p1 --batch < /tmp/v140-to-v141.patch

cd /tmp/global-edge-v103
mv UC-Sentinel-v1.4.0-full-source UC-Sentinel-v1.4.1-full-source
cd UC-Sentinel-v1.4.1-full-source
cat "$ROOT/android-stable/uc-sentinel-v142-build/v141-to-v142.patch.gz.b64" | tr -d '\r\n ' | base64 -d > /tmp/v141-to-v142.patch.gz
echo '3c65c34fd89ed1443b7b0460a57a342c7f2439760ef65b9d8fe88709014f0be3  /tmp/v141-to-v142.patch.gz' | sha256sum -c -
gunzip -c /tmp/v141-to-v142.patch.gz > /tmp/v141-to-v142.patch
echo 'bd8f631cd01a843a9635a028c9b5588b171b8602f25d3a863ce2793ade6e9242  /tmp/v141-to-v142.patch' | sha256sum -c -
patch -p3 --batch < /tmp/v141-to-v142.patch

cd /tmp/global-edge-v103
mv UC-Sentinel-v1.4.1-full-source UC-Sentinel-v1.4.2-full-source
cd UC-Sentinel-v1.4.2-full-source
cat "$ROOT/android-stable/uc-sentinel-v143-build/v142-to-v143.patch.gz.b64" | tr -d '\r\n ' | base64 -d > /tmp/v142-to-v143.patch.gz
echo '51a25c3ef6a92e231317c1a4b48dcf4ba5ebd7b455c2caf881dab98251953fc6  /tmp/v142-to-v143.patch.gz' | sha256sum -c -
gunzip -c /tmp/v142-to-v143.patch.gz > /tmp/v142-to-v143.patch
echo '4cc3426b9ce4a3ae0eff3277d40101b633801eb9ab40b1186c6b1ecad9370a1f  /tmp/v142-to-v143.patch' | sha256sum -c -
patch -p1 --batch < /tmp/v142-to-v143.patch

cd /tmp/global-edge-v103
mv UC-Sentinel-v1.4.2-full-source UC-Sentinel-v1.4.3-full-source
python "$ROOT/android-stable/uc-sentinel-v144-build/upgrade_v144.py" \
  /tmp/global-edge-v103/UC-Sentinel-v1.4.3-full-source \
  "$ROOT/android-stable/global-lead-mappings-v2.json"
mv UC-Sentinel-v1.4.3-full-source UC-Sentinel-v1.4.4-full-source
cd UC-Sentinel-v1.4.4-full-source

cat "$ROOT/fresh-global-edge/v100/fresh-rel.patch.gz.b64.part00" \
    "$ROOT/fresh-global-edge/v100/fresh-rel.patch.gz.b64.part01" \
  | tr -d '\r\n ' | base64 -d > /tmp/fresh-rel.patch.gz
echo 'f9c9ff37f828b7d11307ac8d3f7fc497aa5d19e4313cea306da78f4454284f72  /tmp/fresh-rel.patch.gz' | sha256sum -c -
gunzip -c /tmp/fresh-rel.patch.gz > /tmp/fresh-rel.patch
echo 'df6b22b62e5416a8f907c2f9bdc388cfb4714e44205e5f47341ead7ff29ad72d  /tmp/fresh-rel.patch' | sha256sum -c -
patch -p1 --batch < /tmp/fresh-rel.patch
bash "$ROOT/fresh-global-edge/v100/post_patch_fixes.sh"

cd /tmp/global-edge-v103
mv UC-Sentinel-v1.4.4-full-source Global-Edge-AI-Trader-v1.0.0-source
SRC=/tmp/global-edge-v103/Global-Edge-AI-Trader-v1.0.0-source
python "$ROOT/fresh-global-edge/v101/upgrade_v101.py" "$SRC"
python "$ROOT/fresh-global-edge/v102/upgrade_v102.py" "$SRC"
python "$ROOT/fresh-global-edge/v103/upgrade_v103.py" "$SRC"
mv "$SRC" /tmp/global-edge-v103/Global-Edge-AI-Trader-v1.0.3-source
SRC=/tmp/global-edge-v103/Global-Edge-AI-Trader-v1.0.3-source

grep -q 'versionCode = 103' "$SRC/app/build.gradle.kts"
grep -q 'versionName = "1.0.3"' "$SRC/app/build.gradle.kts"
grep -q 'Global Lead: 9:15 entry signal' "$SRC/app/src/main/java/com/suhas/ucsentinel/notifications/AppNotifier.kt"
grep -q 'notifyStrategySetups' "$SRC/app/src/main/java/com/suhas/ucsentinel/worker/ScanWorker.kt"
grep -q 'notifyGlobalLead' "$SRC/app/src/main/java/com/suhas/ucsentinel/worker/ScanWorker.kt"
grep -q '09:15 entry window' "$SRC/app/src/main/java/com/suhas/ucsentinel/ui/GlobalLeadScreen.kt"
echo 'v1.0.3 source reconstructed and verified'
