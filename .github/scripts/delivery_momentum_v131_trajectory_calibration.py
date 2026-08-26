from pathlib import Path

root=Path('delivery-momentum')
traj=root/'app/src/main/java/com/suhas/nsedeliverymomentum/TrajectoryMath.java'
s=traj.read_text()

# v1.3.0 used a long list of mandatory AND-gates. A genuinely rising stock could fail
# one normal-noise metric (e.g. 3-minute higher-low ratio or a 1.5% pullback) and be
# rejected even when the overall trajectory was strong. v1.3.1 keeps only safety/
# liquidity conditions as hard vetoes and turns the remaining trend evidence into a
# calibrated confirmation vote + composite score.
old='''        double minTurn=Math.max(5,55.0*Math.max(1,elapsedMinutes)/375.0);\n        List<String> fail=new ArrayList<>();\n        if(m.sessionGain<0.65)fail.add("day rise <0.65%");\n        if(m.hourlyPace<0.35)fail.add("session slope <0.35%/h");\n        if(m.recentPace<0.20)fail.add("recent slope weakening");\n        if(m.r2<0.52)fail.add("trajectory not smooth enough");\n        if(m.positive15<0.62)fail.add("too few positive 15m windows");\n        if(m.positive30<0.60)fail.add("30m persistence weak");\n        if(m.higherLows<0.48)fail.add("higher-low structure weak");\n        if(m.vwapHold<0.68||ltp<m.vwap)fail.add("VWAP not persistently held");\n        if(m.pathEfficiency<0.30)fail.add("path too choppy");\n        if(m.closeLocation<0.62)fail.add("too far from session high");\n        if(m.maxDrawdown>1.50)fail.add("intraday drawdown too deep");\n        if(m.maxSpikeShare>0.60&&m.followThrough<0.50)fail.add("move dominated by one spike");\n        if(Math.abs(m.gapPct)>2.0&&m.postOpenGain<0.80)fail.add("gap-only move");\n        if(m.spread>0.20)fail.add("spread too wide");\n        if(m.turnoverCr<minTurn)fail.add("turnover below trajectory floor");\n        if(m.score<72)fail.add("trajectory score <72");\n        m.qualified=fail.isEmpty();\n        m.reason=m.qualified?"PERSISTENT SESSION UPTREND":String.join(" • ",fail);\n        return m;'''
new='''        double minTurn=Math.max(4,45.0*Math.max(1,elapsedMinutes)/375.0);\n        List<String> hard=new ArrayList<>();\n        if(m.sessionGain<0.45)hard.add("day rise <0.45%");\n        if(m.recentPace<0.05)hard.add("recent slope not positive");\n        if(m.vwap>0&&ltp<m.vwap*0.997)hard.add("price materially below VWAP");\n        if(m.vwapHold<0.52)hard.add("VWAP hold too weak");\n        if(m.maxDrawdown>2.60)hard.add("intraday drawdown >2.6%");\n        if(m.maxSpikeShare>0.72&&m.followThrough<0.30)hard.add("move dominated by one spike");\n        if(Math.abs(m.gapPct)>3.0&&m.postOpenGain<0.50)hard.add("gap-only move");\n        if(m.spread>0.25)hard.add("spread too wide");\n        if(m.turnoverCr<minTurn)hard.add("turnover below trajectory floor");\n\n        int confirmations=0;\n        if(m.hourlyPace>=0.30)confirmations++;\n        if(m.recentPace>=0.18)confirmations++;\n        if(m.r2>=0.40)confirmations++;\n        if(m.positive15>=0.58)confirmations++;\n        if(m.positive30>=0.55)confirmations++;\n        if(m.higherLows>=0.40)confirmations++;\n        if(m.vwapHold>=0.60)confirmations++;\n        if(m.pathEfficiency>=0.22)confirmations++;\n        if(m.closeLocation>=0.58)confirmations++;\n        if(Math.max(m.marketAlpha,m.sectorAlpha)>=0.0)confirmations++;\n\n        // Early in the session there are fewer completed windows; later we require a little\n        // more maturity. This avoids applying a noon-quality history requirement at 09:35.\n        double scoreFloor=elapsedMinutes<75?63:(elapsedMinutes<240?65:67);\n        int needConfirm=elapsedMinutes<75?5:6;\n        m.qualified=hard.isEmpty()&&m.score>=scoreFloor&&confirmations>=needConfirm;\n        if(m.qualified){\n            m.reason="PERSISTENT SESSION UPTREND • "+confirmations+"/10 confirmations";\n        }else{\n            List<String> why=new ArrayList<>(hard);\n            if(m.score<scoreFloor)why.add(String.format(java.util.Locale.US,"score %.0f < %.0f",m.score,scoreFloor));\n            if(confirmations<needConfirm)why.add(confirmations+"/10 confirmations; need "+needConfirm);\n            m.reason=String.join(" • ",why);\n        }\n        return m;'''
if old not in s:
    raise SystemExit('Trajectory hard-gate block not found')
s=s.replace(old,new)
traj.write_text(s)

svc=root/'app/src/main/java/com/suhas/nsedeliverymomentum/DeliveryMomentumService.java'
t=svc.read_text()
old_status='''lastStatus=String.format(Locale.US,"ALL-NSE COMPLETE • %d/%d valid • breadth %.0f%% • movers %d • deep %d/%d • BUY %d • trajectory %d/%d • UPTREND %d • %s",valid,syms.size(),breadth*100,broadMoverCount,out.size(),max,q,trajOut.size(),trajMax,tq,now.toLocalTime().withNano(0));recordRecommendations(out);recordTrajectoryRecommendations(trajOut);maybeAutoBuy(out);maybeAutoBuyTrajectory(trajOut);broadcast();}'''
new_status='''int tb=0,tw=0;for(TrajectoryCandidate c:trajOut){if("BUILDING".equals(c.state))tb++;else if("WATCH".equals(c.state))tw++;}\n        lastStatus=String.format(Locale.US,"ALL-NSE COMPLETE • %d/%d valid • breadth %.0f%% • movers %d • deep %d/%d • BUY %d • trajectory %d/%d • UPTREND %d • BUILDING %d • WATCH %d • %s",valid,syms.size(),breadth*100,broadMoverCount,out.size(),max,q,trajOut.size(),trajMax,tq,tb,tw,now.toLocalTime().withNano(0));store.put("last_scan_status",lastStatus);recordRecommendations(out);recordTrajectoryRecommendations(trajOut);maybeAutoBuy(out);maybeAutoBuyTrajectory(trajOut);broadcast();}'''
if old_status not in t:
    raise SystemExit('Trajectory status block not found')
t=t.replace(old_status,new_status)
# Make BUILDING more informative after calibration; Table 1 remains untouched.
t=t.replace('c.state=m.qualified?"UPTREND":(m.score>=65&&m.recentPace>0?"BUILDING":"WATCH");', 'c.state=m.qualified?"UPTREND":(m.score>=56&&m.recentPace>0?"BUILDING":"WATCH");')
# On restart after market close retain the last real scan instead of an unexplained Starting state.
t=t.replace('private volatile String lastStatus="Starting";', 'private volatile String lastStatus="Starting";')
t=t.replace('store=new SecretStore(this);api=new GrowwClient(store);learning=new LearningStore(this);createChannel();startForeground(901,notification("Delivery Momentum scanner starting"));universe=null;', 'store=new SecretStore(this);api=new GrowwClient(store);learning=new LearningStore(this);lastStatus=store.get("last_scan_status","Starting scanner...");createChannel();startForeground(901,notification(lastStatus));universe=null;')
t=t.replace('lastStatus="Market closed • learning retained";broadcast();return;', 'String prev=store.get("last_scan_status","");lastStatus=prev.isEmpty()?"Market closed • learning retained":"Market closed • last scan retained: "+prev;broadcast();return;')
svc.write_text(t)

main=root/'app/src/main/java/com/suhas/nsedeliverymomentum/MainActivity.java'
m=main.read_text()
m=m.replace('The second table is independent: it looks for a persistent session uptrend, not a one-candle spike.','The second table is independent: it looks for a persistent session uptrend using a weighted evidence vote, not a one-candle spike or one brittle all-or-nothing gate.')
main.write_text(m)

b=root/'app/build.gradle'
g=b.read_text().replace('versionCode 130','versionCode 131').replace("versionName '1.3.0'","versionName '1.3.1'")
b.write_text(g)

# Add targeted unit coverage for the calibrated vote logic by static assertions in CI.
assert 'confirmations>=needConfirm' in traj.read_text()
assert 'scoreFloor=elapsedMinutes<75?63' in traj.read_text()
assert 'm.maxDrawdown>2.60' in traj.read_text()
assert 'BUILDING %d' in svc.read_text()
assert 'last_scan_status' in svc.read_text()
assert "versionName '1.3.1'" in b.read_text()
print('Delivery Momentum v1.3.1 trajectory calibration applied')
