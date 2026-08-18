package com.suhas.nseunifiedscanner;

import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.EditText;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.Space;
import android.widget.Switch;
import android.widget.TextView;
import android.widget.Toast;

import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;

public class MainActivity extends Activity {
    private static final int BG=Color.rgb(7,17,27), CARD=Color.rgb(14,29,42), CARD2=Color.rgb(18,38,53), TEXT=Color.rgb(237,246,247), MUTED=Color.rgb(151,170,181), ACCENT=Color.rgb(34,211,167), GREEN=Color.rgb(59,220,145), AMBER=Color.rgb(255,193,78), RED=Color.rgb(255,103,103);
    private final Handler ui=new Handler(Looper.getMainLooper());
    private LinearLayout body,recs,hits;private TextView successRate,successSub,market,status,scanMeta,active,connectivity,historySummary,learningMeta;private Switch liveSwitch;
    private LearningStore learning;private LearningInsights insights;

    @Override protected void onCreate(Bundle b){super.onCreate(b);getWindow().setStatusBarColor(BG);getWindow().setNavigationBarColor(BG);learning=new LearningStore(this);insights=new LearningInsights(this);setContentView(buildUi());requestNotificationPermission();startScanner();ui.post(refreshLoop);}
    @Override protected void onDestroy(){ui.removeCallbacksAndMessages(null);super.onDestroy();}

    private View buildUi(){
        ScrollView scroll=new ScrollView(this);scroll.setFillViewport(true);scroll.setBackgroundColor(BG);body=new LinearLayout(this);body.setOrientation(LinearLayout.VERTICAL);body.setPadding(dp(16),dp(16),dp(16),dp(36));scroll.addView(body,new ScrollView.LayoutParams(-1,-2));
        LinearLayout header=new LinearLayout(this);header.setGravity(Gravity.CENTER_VERTICAL);ImageView icon=new ImageView(this);icon.setImageResource(com.suhas.nseunifiedscanner.R.drawable.ic_launcher);header.addView(icon,new LinearLayout.LayoutParams(dp(54),dp(54)));LinearLayout titleBox=new LinearLayout(this);titleBox.setOrientation(LinearLayout.VERTICAL);titleBox.setPadding(dp(10),0,0,0);TextView title=txt("NSE UNIFIED SCANNER",23,TEXT,true);TextView sub=txt("5-minute adaptive intraday engine • 30-minute horizon",12,MUTED,false);titleBox.addView(title);titleBox.addView(sub);header.addView(titleBox,new LinearLayout.LayoutParams(0,-2,1));Button settings=button("⚙",CARD2,TEXT);settings.setOnClickListener(v->settingsDialog());header.addView(settings,new LinearLayout.LayoutParams(dp(52),dp(48)));body.addView(header);
        body.addView(space(14));

        LinearLayout perf=card();TextView cap=txt("30-MIN TARGET HIT RATE",11,MUTED,true);successRate=txt("—",38,TEXT,true);successSub=txt("No resolved scanner recommendations yet • goal ≥80%, never guaranteed",12,MUTED,false);perf.addView(cap);perf.addView(successRate);perf.addView(successSub);body.addView(perf);
        body.addView(space(10));

        LinearLayout hc=card();hc.addView(txt("TARGET HITS TODAY",12,GREEN,true));historySummary=txt("Waiting for resolved recommendations…",12,MUTED,false);hc.addView(historySummary);hc.addView(space(7));hits=new LinearLayout(this);hits.setOrientation(LinearLayout.VERTICAL);hc.addView(hits);body.addView(hc);
        body.addView(space(10));

        LinearLayout m=card();market=txt("MARKET • waiting for scan",16,TEXT,true);status=txt("Service starting…",12,MUTED,false);scanMeta=txt("",11,MUTED,false);m.addView(market);m.addView(status);m.addView(scanMeta);body.addView(m);
        body.addView(space(10));

        LinearLayout conn=card();conn.addView(txt("CONNECTION HEALTH",12,ACCENT,true));connectivity=txt("Groww API  ○ CHECKING\nStatic IP  ○ CHECKING\nNSE feed  ○ CHECKING",12,TEXT,true);conn.addView(connectivity);body.addView(conn);
        body.addView(space(10));

        LinearLayout controls=new LinearLayout(this);controls.setGravity(Gravity.CENTER_VERTICAL);controls.setPadding(dp(2),0,dp(2),0);Button refresh=button("REFRESH NOW",ACCENT,BG);refresh.setOnClickListener(v->send(UnifiedService.ACTION_SCAN,null));controls.addView(refresh,new LinearLayout.LayoutParams(0,dp(50),1));controls.addView(spaceH(8));liveSwitch=new Switch(this);liveSwitch.setText("LIVE");liveSwitch.setTextColor(TEXT);liveSwitch.setChecked(prefs().getBoolean("live_armed",false));liveSwitch.setOnCheckedChangeListener((btt,on)->{if(on&&!prefs().getBoolean("live_armed",false)){btt.setChecked(false);armConfirm();}else if(!on){prefs().edit().putBoolean("live_armed",false).apply();}});controls.addView(liveSwitch,new LinearLayout.LayoutParams(dp(104),dp(50)));body.addView(controls);
        body.addView(space(10));

        LinearLayout a=card();TextView at=txt("ACTIVE TRADE",11,MUTED,true);active=txt("No active position",14,TEXT,true);Button exit=button("EXIT ACTIVE POSITION",Color.rgb(82,35,40),Color.rgb(255,190,190));exit.setOnClickListener(v->send(UnifiedService.ACTION_EXIT,null));a.addView(at);a.addView(active);a.addView(space(8));a.addView(exit,new LinearLayout.LayoutParams(-1,dp(44)));body.addView(a);
        body.addView(space(16));
        TextView h=txt("TOP 3 • NEXT 30 MINUTES",18,TEXT,true);body.addView(h);TextView note=txt("A ranked Top 3 is shown whenever the discovery scan has enough data. BUY appears only when strict hard gates + learned quality threshold pass. Same stock may remain ranked on consecutive scans.",12,MUTED,false);body.addView(note);body.addView(space(8));recs=new LinearLayout(this);recs.setOrientation(LinearLayout.VERTICAL);body.addView(recs);
        body.addView(space(14));
        LinearLayout learn=card();learn.addView(txt("FAST SELF-LEARNING",12,ACCENT,true));learn.addView(txt("Displayed recommendations keep the official hit-rate. Ranks 4–10 are replayed separately as lower-weight shadow observations so the model learns faster without inflating the success metric. Live BUY gates remain strict; learning cannot override the +0.50% net objective, 30-minute time stop, liquidity, spread, R:R or protection rules.",12,MUTED,false));learningMeta=txt("Shadow learning starting…",11,MUTED,false);learn.addView(space(6));learn.addView(learningMeta);body.addView(learn);
        body.addView(space(8));TextView footer=txt("v1.1.0 • standalone package com.suhas.nseunifiedscanner • Multyfi AutoBuy is untouched",10,MUTED,false);footer.setGravity(Gravity.CENTER);body.addView(footer);
        return scroll;
    }

    private final Runnable refreshLoop=new Runnable(){@Override public void run(){render();ui.postDelayed(this,1000);}};
    private void render(){
        LearningStore.Stats s=learning.stats();if(s.n==0){successRate.setText("—");successRate.setTextColor(TEXT);successSub.setText("No resolved scanner recommendations yet • goal ≥80%, never guaranteed");}else{successRate.setText(String.format(Locale.US,"%.1f%%",s.rate));successRate.setTextColor(s.rate>=80?GREEN:s.rate>=70?AMBER:RED);String confidence=s.n<20?"LOW CONFIDENCE":s.n<50?"BUILDING CONFIDENCE":"ROLLING EVIDENCE";successSub.setText(s.wins+"/"+s.n+" target hits • "+confidence+" • executed "+s.executedN+" • goal ≥80%, not guaranteed");}
        renderHistory();renderConnectivity();LearningInsights.ShadowStats sh=insights.shadowStats();learningMeta.setText("Shadow learning today: "+sh.resolvedToday+" resolved • "+sh.hitsToday+" target-first • "+sh.pending+" pending. Shadow outcomes update model weights at 25% strength and never alter the headline hit-rate.");
        ScannerEngine.ScanResult st=ScannerEngine.state(this);market.setText("MARKET • "+st.marketLabel+" • breadth "+String.format(Locale.US,"%.1f%%",st.breadth));String ss=prefs().getString("service_status","Scanner ready");status.setText(ss);long age=st.scanMs==0?0:System.currentTimeMillis()-st.scanMs;scanMeta.setText(st.scanMs==0?"No scan yet":"Last scan "+time(st.scanMs)+" • "+st.scanned+" NSE EQ scanned • quality floor "+st.minScore+"/100 • age "+(age/1000)+"s");
        ActiveTrade t=ActiveTrade.load(this);if(t==null)active.setText("No active position");else{long left=Math.max(0,t.deadlineMs-System.currentTimeMillis());active.setText(t.symbol+" • "+t.qty+" shares\nFill ₹"+money(t.fillPrice)+"   Target ₹"+money(t.target)+"   SL ₹"+money(t.stop)+"\nProtection "+t.mode+" • time left "+(left/60000)+":"+String.format(Locale.US,"%02d",(left/1000)%60));}
        boolean armed=prefs().getBoolean("live_armed",false);if(liveSwitch.isChecked()!=armed){liveSwitch.setOnCheckedChangeListener(null);liveSwitch.setChecked(armed);liveSwitch.setOnCheckedChangeListener((b,on)->{if(on&&!prefs().getBoolean("live_armed",false)){b.setChecked(false);armConfirm();}else if(!on)prefs().edit().putBoolean("live_armed",false).apply();});}
        renderRecommendations(st);
    }

    private void renderHistory(){
        LearningInsights.TodaySummary t=insights.todaySummary();historySummary.setText(t.hits+" hits • "+t.stops+" stops • "+t.timeouts+" timeouts • "+t.resolved+" resolved today");hits.removeAllViews();java.util.List<LearningInsights.HistoryRow> rows=insights.todayHits(6);if(rows.isEmpty()){hits.addView(txt("No target hits resolved today yet.",12,MUTED,false));return;}for(LearningInsights.HistoryRow r:rows){String line="✓ "+r.symbol+"   ₹"+money(r.entry)+" → ₹"+money(r.target)+"   • score "+String.format(Locale.US,"%.0f",r.score)+"   • "+time(r.scanMs)+" → "+time(r.resolvedMs)+(r.bought?"   • EXECUTED":"");hits.addView(txt(line,12,GREEN,true));hits.addView(space(4));}}

    private void renderConnectivity(){
        long now=System.currentTimeMillis();boolean api=prefs().getBoolean("groww_api_ok",false);long apiAge=now-prefs().getLong("groww_api_checked_ms",0);int ip=prefs().getInt("static_ip_state",0);long ipAge=now-prefs().getLong("static_ip_checked_ms",0);boolean feed=prefs().getBoolean("nse_feed_ok",false);long feedAge=now-prefs().getLong("nse_feed_checked_ms",0);
        String a=api&&apiAge<8*60*60_000L?"✅ CONNECTED":"⚠ AUTH / CHECK REQUIRED";String i=ip==1&&ipAge<30*60_000L?"✅ MATCHED":ip==-1?"❌ MISMATCH":"○ NOT VERIFIED";String f=feed&&feedAge<7*60_000L?"✅ LIVE":"⚠ STALE / WAITING";connectivity.setText("Groww API  "+a+"\nStatic IP  "+i+"\nNSE feed  "+f+"\nGreen is shown only after an actual API/feed check; the IP value itself is never displayed.");
    }

    private void renderRecommendations(ScannerEngine.ScanResult st){recs.removeAllViews();if(st.recommendations.isEmpty()){LinearLayout c=card();c.addView(txt(st.error==null||st.error.isEmpty()?"No ranked candidates yet. The scanner will retry on the next completed 5-minute cycle.":st.error,13,MUTED,false));recs.addView(c);return;}int rank=1;for(ScannerEngine.Recommendation r:st.recommendations){LinearLayout c=card();LinearLayout top=new LinearLayout(this);top.setGravity(Gravity.CENTER_VERTICAL);TextView n=txt("#"+rank+"  "+r.symbol,21,TEXT,true);top.addView(n,new LinearLayout.LayoutParams(0,-2,1));TextView badge=txt(r.qualified?"QUALIFIED":"WATCH",11,r.qualified?GREEN:AMBER,true);badge.setPadding(dp(9),dp(5),dp(9),dp(5));badge.setBackground(round(r.qualified?Color.rgb(20,63,52):Color.rgb(69,54,23),12));top.addView(badge);c.addView(top);
            c.addView(txt(String.format(Locale.US,"Score %.0f/100  •  model %.0f%%  •  max 30 min",r.score,r.probability*100),12,MUTED,false));c.addView(space(8));
            LinearLayout prices=new LinearLayout(this);prices.setGravity(Gravity.CENTER);prices.addView(metric("ENTRY","₹"+money(r.entry)),new LinearLayout.LayoutParams(0,-2,1));prices.addView(metric("TARGET","₹"+money(r.target)),new LinearLayout.LayoutParams(0,-2,1));prices.addView(metric("STOP","₹"+money(r.stop)),new LinearLayout.LayoutParams(0,-2,1));c.addView(prices);
            c.addView(space(8));c.addView(txt("NET OBJECTIVE +0.50% after estimated Groww/NSE charges • actual target recalculated from fill + quantity",11,ACCENT,true));
            c.addView(txt(String.format(Locale.US,"VWAP %.2f  • RSI %.1f  • RelVol %.2fx  • 1h %+,.2f%%\nR1 %.2f  • R2 %.2f  • room %.2f%%  • spread %.2f%%\nBuy depth %.0f%%  • turnover ₹%.1f Cr",r.vwap,r.rsi,r.relVol,r.oneHour,r.r1,r.r2,r.roomR2,r.spreadPct,r.depthBuyPct,r.turnover/10_000_000d),11,MUTED,false));
            c.addView(space(6));c.addView(txt(r.reason,11,r.qualified?GREEN:AMBER,false));c.addView(space(8));Button buy=button(r.qualified?"BUY • MAX SAFE MIS":"WATCH • BUY DISABLED",r.qualified?ACCENT:Color.rgb(39,51,59),r.qualified?BG:MUTED);buy.setEnabled(r.qualified);String symbol=r.symbol;buy.setOnClickListener(v->send(UnifiedService.ACTION_BUY,symbol));c.addView(buy,new LinearLayout.LayoutParams(-1,dp(50)));c.setOnClickListener(v->details(r));recs.addView(c);recs.addView(space(9));rank++;}}

    private void details(ScannerEngine.Recommendation r){String m=String.format(Locale.US,"%s\n\nEntry ₹%.2f\nIndicative target ₹%.2f\nStop ₹%.2f\n\nRSI %.1f\nRelative volume %.2fx\n1-hour momentum %.2f%%\nVWAP ₹%.2f\nR1 ₹%.2f\nR2 ₹%.2f\nRoom to R2 %.2f%%\nSpread %.3f%%\nMarket breadth %.1f%%\n\n%s",r.symbol,r.entry,r.target,r.stop,r.rsi,r.relVol,r.oneHour,r.vwap,r.r1,r.r2,r.roomR2,r.spreadPct,r.breadth,r.reason);new AlertDialog.Builder(this).setTitle("Scanner evidence").setMessage(m).setPositiveButton("OK",null).show();}

    private void settingsDialog(){
        LinearLayout box=new LinearLayout(this);box.setOrientation(LinearLayout.VERTICAL);box.setPadding(dp(20),dp(8),dp(20),0);EditText api=field("Groww API key",SecureStore.get(this,SecureStore.API_KEY),false);EditText secret=field("Groww TOTP secret",SecureStore.get(this,SecureStore.TOTP_SECRET),true);EditText ip=field("Groww-whitelisted Dedicated IP",SecureStore.get(this,SecureStore.DEDICATED_IP),false);EditText capital=field("Capital use % (50–100)",String.format(Locale.US,"%.0f",prefs().getFloat("capital_use",0.98f)*100),false);capital.setInputType(InputType.TYPE_CLASS_NUMBER|InputType.TYPE_NUMBER_FLAG_DECIMAL);box.addView(api);box.addView(secret);box.addView(ip);box.addView(capital);TextView info=txt("Credentials are encrypted with Android Keystore. Scanner can run read-only when LIVE is off. BUY requires the configured public IP to match exactly. Connection Health turns green only after actual API/feed/IP checks.",11,MUTED,false);box.addView(info);
        AlertDialog d=new AlertDialog.Builder(this).setTitle("Secure Groww settings").setView(box).setNegativeButton("Cancel",null).setNeutralButton("AUTHENTICATE",null).setPositiveButton("SAVE",null).create();d.setOnShowListener(x->{d.getWindow().addFlags(WindowManager.LayoutParams.FLAG_SECURE);d.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(v->{try{SecureStore.put(this,SecureStore.API_KEY,api.getText().toString().trim());SecureStore.put(this,SecureStore.TOTP_SECRET,secret.getText().toString().trim());SecureStore.put(this,SecureStore.DEDICATED_IP,ip.getText().toString().trim());float pct=Float.parseFloat(capital.getText().toString().trim());pct=Math.max(50,Math.min(100,pct));prefs().edit().putFloat("capital_use",pct/100f).putInt("static_ip_state",0).apply();Toast.makeText(this,"Settings saved",Toast.LENGTH_SHORT).show();d.dismiss();}catch(Exception e){Toast.makeText(this,"Save failed: "+e.getMessage(),Toast.LENGTH_LONG).show();}});d.getButton(AlertDialog.BUTTON_NEUTRAL).setOnClickListener(v->{try{SecureStore.put(this,SecureStore.API_KEY,api.getText().toString().trim());SecureStore.put(this,SecureStore.TOTP_SECRET,secret.getText().toString().trim());SecureStore.put(this,SecureStore.DEDICATED_IP,ip.getText().toString().trim());prefs().edit().putInt("static_ip_state",0).apply();send(UnifiedService.ACTION_AUTH,null);Toast.makeText(this,"Authentication requested",Toast.LENGTH_SHORT).show();}catch(Exception e){Toast.makeText(this,"Could not save credentials",Toast.LENGTH_LONG).show();}});});d.show();}

    private void armConfirm(){new AlertDialog.Builder(this).setTitle("Arm one-click live trading?").setMessage("BUY will use up to the configured share of available MIS margin (default 98%), open only one position at a time, create broker protection, target an estimated +0.50% net after current published charges, and force a time exit by 30 minutes or 15:10 IST. Profit and an 80% hit rate cannot be guaranteed.").setNegativeButton("Keep OFF",null).setPositiveButton("ARM LIVE",(d,w)->{prefs().edit().putBoolean("live_armed",true).apply();liveSwitch.setChecked(true);}).show();}

    private void startScanner(){Intent i=new Intent(this,UnifiedService.class).setAction(UnifiedService.ACTION_START);if(Build.VERSION.SDK_INT>=26)startForegroundService(i);else startService(i);}
    private void send(String action,String symbol){Intent i=new Intent(this,UnifiedService.class).setAction(action);if(symbol!=null)i.putExtra(UnifiedService.EXTRA_SYMBOL,symbol);if(Build.VERSION.SDK_INT>=26)startForegroundService(i);else startService(i);}
    private void requestNotificationPermission(){if(Build.VERSION.SDK_INT>=33&&checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)!=PackageManager.PERMISSION_GRANTED)requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS},400);}
    private android.content.SharedPreferences prefs(){return getSharedPreferences("scanner_prefs",Context.MODE_PRIVATE);}

    private LinearLayout card(){LinearLayout l=new LinearLayout(this);l.setOrientation(LinearLayout.VERTICAL);l.setPadding(dp(15),dp(14),dp(15),dp(14));l.setBackground(round(CARD,18));return l;}
    private LinearLayout metric(String label,String value){LinearLayout l=new LinearLayout(this);l.setOrientation(LinearLayout.VERTICAL);l.setGravity(Gravity.CENTER);l.addView(txt(label,10,MUTED,true));l.addView(txt(value,16,TEXT,true));return l;}
    private TextView txt(String s,int sp,int color,boolean bold){TextView t=new TextView(this);t.setText(s);t.setTextSize(sp);t.setTextColor(color);t.setLineSpacing(0,1.1f);if(bold)t.setTypeface(Typeface.DEFAULT,Typeface.BOLD);return t;}
    private Button button(String s,int bg,int fg){Button b=new Button(this);b.setText(s);b.setTextColor(fg);b.setTextSize(12);b.setTypeface(Typeface.DEFAULT,Typeface.BOLD);b.setAllCaps(false);b.setGravity(Gravity.CENTER);b.setBackground(round(bg,14));return b;}
    private EditText field(String hint,String value,boolean secret){EditText e=new EditText(this);e.setHint(hint);e.setHintTextColor(MUTED);e.setTextColor(TEXT);e.setText(value);e.setSingleLine(true);e.setBackgroundColor(Color.TRANSPARENT);e.setPadding(0,dp(10),0,dp(10));if(secret)e.setInputType(InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_PASSWORD);return e;}
    private GradientDrawable round(int color,int radius){GradientDrawable g=new GradientDrawable();g.setColor(color);g.setCornerRadius(dp(radius));g.setStroke(dp(1),Color.rgb(28,53,69));return g;}
    private View space(int h){Space s=new Space(this);s.setLayoutParams(new LinearLayout.LayoutParams(1,dp(h)));return s;}
    private View spaceH(int w){Space s=new Space(this);s.setLayoutParams(new LinearLayout.LayoutParams(dp(w),1));return s;}
    private int dp(int v){return Math.round(v*getResources().getDisplayMetrics().density);}
    private String money(double d){return String.format(Locale.US,"%.2f",d);}
    private String time(long ms){return new SimpleDateFormat("HH:mm:ss",Locale.US).format(new Date(ms));}
}
