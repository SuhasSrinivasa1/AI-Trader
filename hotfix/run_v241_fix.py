#!/usr/bin/env python3
from pathlib import Path
import runpy

source_path = Path("hotfix/run_v241.py")
source = source_path.read_text(encoding="utf-8")

# Correct the obsolete notification-routing patch anchor in the generated
# v2.4.0 source. Use repr() so the temporary Python script is always valid.
old_python = '    patch(ns, "        if (!AppPrefs.MULTYFI_PACKAGE.equals(sbn.getPackageName())) return;\\n", "        if (!AppPrefs.MULTYFI_PACKAGE.equals(sbn.getPackageName())) return;\\n        if (!AppPrefs.isArmed(this)) return;\\n")\n'
old_java = """        if (AppPrefs.MULTYFI_PACKAGE.equals(sourcePackage)) {
            executor.execute(() -> process(rawText, postTime));
            if (!AppRole.isChild(this)) {
                LanMasterRelayService.publishAsync(this, rawText, postTime);
            }
        } else if (AppPrefs.RESEARCH360_PACKAGE.equals(sourcePackage)) {
"""
new_java = """        if (AppPrefs.MULTYFI_PACKAGE.equals(sourcePackage)) {
            if (!AppPrefs.isArmed(this)) return;
            executor.execute(() -> process(rawText, postTime));
            if (!AppRole.isChild(this)) {
                LanMasterRelayService.publishAsync(this, rawText, postTime);
            }
        } else if (AppPrefs.RESEARCH360_PACKAGE.equals(sourcePackage)) {
"""
new_python = f"    patch(ns, {old_java!r}, {new_java!r})\n"
if old_python not in source:
    raise RuntimeError("v2.4.1 obsolete notification patch line not found")
source = source.replace(old_python, new_python, 1)

# The v2.4.0 final refreshStatus wording differs from the older source wording
# used by run_v241.py. Replace the two brittle substring edits with one complete
# method replacement that explicitly models HARD OFF vs ARMED/PAUSED.
old_ui_start = '''    # OFF status must not look like a broken/disconnected system.
    patch(pa, ''' + "'''" + '''        boolean persistentlyArmed = AppPrefs.isArmed(this);
        systemStatus.setText(ready ? "READY" : (persistentlyArmed ? "ARMED • ENTRY PAUSED" : "SETUP REQUIRED"));
        systemStatus.setTextColor(ready ? GREEN : AMBER);
        statusDetail.setText(ready
''' + "'''" + ''', ''' + "'''" + '''        boolean persistentlyArmed = AppPrefs.isArmed(this);
        if (!persistentlyArmed) {
            systemStatus.setText("OFF");
            systemStatus.setTextColor(MUTED);
            statusDetail.setText("Hard OFF • trading monitor stopped • local MASTER/CHILD relay stopped • no Multyfi background processing.");
            notificationStatus.setText("● Runtime OFF: local LAN relay is stopped");
            notificationStatus.setTextColor(MUTED);
        } else {
            systemStatus.setText(ready ? "READY" : "ARMED • ENTRY PAUSED");
            systemStatus.setTextColor(ready ? GREEN : AMBER);
            statusDetail.setText(ready
''' + "'''" + ''')
    patch(pa, ''' + "'''" + '''                : issue + (persistentlyArmed
                ? " • Armed state is retained 24×7; new entries automatically wait for this gate."
                : " • Turn on the switch to retain the armed state while gates recover."));

        suppressSwitch = true;
''' + "'''" + ''', ''' + "'''" + '''                : issue + " • Armed state remains ON; new entries wait for this gate.");
        }

        suppressSwitch = true;
''' + "'''" + ''')
'''

refresh_method = r'''    private void refreshStatus() {
        boolean persistentlyArmed = AppPrefs.isArmed(this);
        boolean notificationReady = AppRole.isChild(this)
                ? RelayState.childConnected(this) : hasNotificationAccess();
        boolean authReady = AppPrefs.isAuthVerifiedToday(this);
        boolean vpn = NetworkUtil.isVpnActive(this);
        boolean ipReady = vpn && AppPrefs.isStaticConfirmed(this)
                && AppPrefs.isIpRecentlyVerified(this);
        boolean parserReady = AppPrefs.parserTestPassed(this);
        String issue = readinessIssue();
        boolean ready = issue == null;
        int active = StrategyStore.activeCount(this);

        if (!persistentlyArmed) {
            notificationStatus.setText("● Runtime OFF: local MASTER/CHILD relay stopped");
            notificationStatus.setTextColor(MUTED);
        } else {
            notificationStatus.setText(AppRole.isChild(this)
                    ? (notificationReady
                        ? "● Master LAN relay: connected • " + RelayState.masterIp(this)
                            + " • last " + Math.max(0, RelayState.latency(this)) + " ms"
                        : "● Master LAN relay: disconnected — auto-retrying")
                    : (notificationReady
                        ? "● Notification listener: connected • LAN children "
                            + RelayState.masterChildren(this)
                        : "● Notification listener: reconnecting"));
            notificationStatus.setTextColor(notificationReady ? GREEN : AMBER);
        }

        String ucc = AppPrefs.ucc(this);
        authStatus.setText(authReady
                ? "● Groww connection + DDPI: verified today" + (ucc.isEmpty() ? "" : " • UCC " + ucc)
                : "● Groww connection + DDPI: automatic verification pending");
        authStatus.setTextColor(authReady ? GREEN : RED);
        ipStatus.setText(ipReady
                ? "● Surfshark Dedicated IP: verified • " + AppPrefs.lastPublicIp(this)
                : "● Surfshark Dedicated IP: not ready • VPN " + (vpn ? "connected" : "disconnected"));
        ipStatus.setTextColor(ipReady ? GREEN : RED);
        policyStatus.setText(parserReady
                ? "● Intake: complete Multyfi calls → MIS • Free/Swing/Multibagger blocked • early sell retained"
                : "● Signal policy: offline acceptance test required");
        policyStatus.setTextColor(parserReady ? GREEN : AMBER);

        if (!persistentlyArmed) {
            systemStatus.setText("OFF");
            systemStatus.setTextColor(MUTED);
            statusDetail.setText("Hard OFF • trading monitor stopped • local MASTER/CHILD relay stopped • no Multyfi background processing.");
        } else {
            systemStatus.setText(ready ? "READY" : "ARMED • ENTRY PAUSED");
            systemStatus.setTextColor(ready ? GREEN : AMBER);
            statusDetail.setText(ready
                    ? "All production gates passed • active strategies " + active
                        + " • Intraday budget ₹" + money(AppPrefs.intradayBudget(this))
                        + " • NET profit goal +₹5,000 • GROSS loss emergency -₹2,000."
                    : issue + " • Armed state remains ON; new entries wait for this gate.");
            if (ready) TradeEventNotifier.clearPause(this);
            else TradeEventNotifier.notifyTradingPaused(this, issue);
        }

        suppressSwitch = true;
        armedSwitch.setChecked(persistentlyArmed);
        suppressSwitch = false;
        auditLog.setText(AppPrefs.auditLog(this));
    }'''

new_ui = "    # OFF status is a true power-state, not a failed readiness-state.\n" + \
        f"    replace_method(pa, \"    private void refreshStatus()\", {refresh_method!r})\n"
if old_ui_start not in source:
    raise RuntimeError("v2.4.1 brittle OFF-status patch block not found")
source = source.replace(old_ui_start, new_ui, 1)

temp = Path("hotfix/.run_v241_fixed_runtime.py")
temp.write_text(source, encoding="utf-8")
try:
    runpy.run_path(str(temp), run_name="__main__")
finally:
    try:
        temp.unlink()
    except Exception:
        pass

print("Applied v2.4.1 routing + robust hard-OFF UI corrective wrapper")
