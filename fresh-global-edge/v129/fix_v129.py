#!/usr/bin/env python3
from pathlib import Path
import sys
root=Path(sys.argv[1]).resolve()

def rw(p): return (root/p).read_text(encoding="utf-8")
def wr(p,s): (root/p).write_text(s,encoding="utf-8")
def rep(s,old,new,label,count=1):
    n=s.count(old)
    if n!=count: raise SystemExit(f"{label}: expected {count}, found {n}")
    return s.replace(old,new,count)

# Version.
p="app/build.gradle.kts";s=rw(p)
s=rep(s,"versionCode = 128","versionCode = 129","versionCode")
s=rep(s,'versionName = "1.2.8"','versionName = "1.2.9"',"versionName")
wr(p,s)

# Allow reliable visibility/launch of the official Groww Android app.
p="app/src/main/AndroidManifest.xml";s=rw(p)
if 'com.nextbillion.groww' not in s:
    marker='<application'
    idx=s.find(marker)
    if idx<0: raise SystemExit("manifest application marker missing")
    q='''    <queries>
        <package android:name="com.nextbillion.groww" />
    </queries>

'''
    s=s[:idx]+q+s[idx:]
wr(p,s)

# Make notification language impossible to confuse with broker execution.
p="app/src/main/java/com/suhas/ucsentinel/notifications/AppNotifier.kt";s=rw(p)
s=s.replace('.setContentTitle("Order ticket prepared")','.setContentTitle("Order ready — NOT submitted")')
s=s.replace('text+"\\nReview and submit through your broker."','text+"\\nNo broker order has been sent. Open Groww to review and submit."')
wr(p,s)

# Change the model-score action into a broker handoff: calculate and freeze the exact ticket,
# then open the official Groww app after the user's explicit handoff confirmation.
# No securities order is transmitted by Global Edge itself.
p="app/src/main/java/com/suhas/ucsentinel/ui/CompactMarketScreens.kt";s=rw(p)
if "import android.content.Intent" not in s:
    s=s.replace("import android.widget.Toast\n","import android.widget.Toast\nimport android.content.Intent\nimport android.net.Uri\n")
old='''            confirmButton={
                Button(onClick={
                    showOrder=false
                    if(qty<=0){
                        Toast.makeText(ctx,"Budget insufficient for one share",Toast.LENGTH_LONG).show()
                    }else{
                        AppNotifier.notifyPreparedOrder(ctx,symbol,side,product,qty,plan.entry,plan.stop,plan.target1)
                        Toast.makeText(ctx,"Order ticket prepared: "+side+" "+qty+" "+symbol+" ("+product+")",Toast.LENGTH_LONG).show()
                    }
                },enabled=qty>0){Text("Prepare")}
            }
'''
new='''            confirmButton={
                Button(onClick={
                    showOrder=false
                    if(qty<=0){
                        Toast.makeText(ctx,"Budget insufficient for one share",Toast.LENGTH_LONG).show()
                    }else{
                        AppNotifier.notifyPreparedOrder(ctx,symbol,side,product,qty,plan.entry,plan.stop,plan.target1)
                        Toast.makeText(ctx,"Opening Groww — order is NOT submitted yet",Toast.LENGTH_LONG).show()
                        val launch=ctx.packageManager.getLaunchIntentForPackage("com.nextbillion.groww")
                        if(launch!=null){
                            launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                            ctx.startActivity(launch)
                        }else{
                            runCatching{
                                ctx.startActivity(Intent(Intent.ACTION_VIEW,Uri.parse("https://groww.in/")).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                            }.onFailure{
                                Toast.makeText(ctx,"Groww app not found",Toast.LENGTH_LONG).show()
                            }
                        }
                    }
                },enabled=qty>0){Text("Open Groww")}
            }
'''
s=rep(s,old,new,"broker handoff confirm")
s=s.replace('Text("This prepares the ticket locally; it does not transmit a live broker order.",style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)',
'''Text("Global Edge does not transmit the securities order. Open Groww below to review and submit this exact ticket.",style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)''')
s=s.replace('"LIVE • tap MODEL score to prepare ₹20,000 CNC ticket"','"LIVE • tap MODEL score for ₹20,000 CNC broker handoff"')
s=s.replace('" • tap MODEL score to prepare order"','" • tap MODEL score for broker handoff"')
wr(p,s)

print("Global Edge v1.2.9 broker-handoff clarity + Groww launch applied")
