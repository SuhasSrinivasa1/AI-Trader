package com.ps.shadowtrader;

import android.app.*;
import android.content.*;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.*;
import android.provider.Settings;
import android.text.InputType;
import android.view.*;
import android.widget.*;
import org.json.*;
import java.text.*;
import java.util.*;
import static com.ps.shadowtrader.Models.*;

public class MainActivity extends Activity {
    private static final int BG=Color.rgb(245,247,251),NAVY=Color.rgb(18,31,52),BLUE=Color.rgb(39,97,245),GREEN=Color.rgb(24,151,96),RED=Color.rgb(208,64,77),MUTED=Color.rgb(99,110,128),CARD=Color.WHITE;
    private LinearLayout page,content,tabRow;private EditText token;private TextView engineChip,notifyChip,tokenChip;private Button tabAuto,tabLab;private SecureStore secure;private int currentTab=0;private boolean showClosed=false;
    private final Handler ui=new Handler(Looper.getMainLooper());private final Runnable refresh=new Runnable(){public void run(){renderBody();ui.postDelayed(this,5000);}};

    @Override public void onCreate(Bundle b){super.onCreate(b);getWindow().setStatusBarColor(NAVY);getWindow().setNavigationBarColor(Color.WHITE);secure=new SecureStore(this);buildShell();renderBody();Scheduler.schedule(this);autoStart();ui.postDelayed(refresh,5000);}
    @Override protected void onResume(){super.onResume();renderBody();autoStart();}
    @Override protected void onDestroy(){ui.removeCallbacks(refresh);super.onDestroy();}

    private void buildShell(){
        ScrollView scroll=new ScrollView(this);scroll.setFillViewport(true);page=new LinearLayout(this);page.setOrientation(LinearLayout.VERTICAL);page.setPadding(dp(18),dp(18),dp(18),dp(34));page.setBackgroundColor(BG);scroll.addView(page);setContentView(scroll);
        TextView brand=text("PS SHADOW TRADER",26,NAVY,true);page.addView(brand);
        TextView sub=text("Autonomous shadow execution + 30-day momentum research",14,MUTED,false);sub.setPadding(0,dp(2),0,dp(14));page.addView(sub);
        buildAuthCard();buildStatusRow();buildTabs();content=new LinearLayout(this);content.setOrientation(LinearLayout.VERTICAL);page.addView(content,new LinearLayout.LayoutParams(-1,-2));
    }
    private void buildAuthCard(){
        LinearLayout card=card();card.addView(text("Daily Groww authentication",17,NAVY,true));card.addView(text("Paste the access token once. The engine starts automatically and will ask again when Groww expires the token.",12,MUTED,false));
        token=new EditText(this);token.setHint("Groww access token");token.setText(secure.get("token"));token.setSingleLine(true);token.setInputType(InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_PASSWORD);token.setPadding(dp(14),dp(12),dp(14),dp(12));token.setBackground(round(Color.rgb(245,247,250),dp(12),Color.rgb(220,225,233),1));LinearLayout.LayoutParams ep=new LinearLayout.LayoutParams(-1,dp(52));ep.topMargin=dp(12);card.addView(token,ep);
        Button auth=button("AUTHENTICATE & START AUTOMATION",BLUE,Color.WHITE);auth.setOnClickListener(v->authenticate());LinearLayout.LayoutParams bp=new LinearLayout.LayoutParams(-1,dp(50));bp.topMargin=dp(10);card.addView(auth,bp);page.addView(card,cardLp());
    }
    private void buildStatusRow(){LinearLayout r=new LinearLayout(this);r.setOrientation(LinearLayout.HORIZONTAL);r.setWeightSum(3);engineChip=chip("ENGINE");notifyChip=chip("MULTIFY");tokenChip=chip("TOKEN");r.addView(engineChip,new LinearLayout.LayoutParams(0,dp(50),1));r.addView(notifyChip,new LinearLayout.LayoutParams(0,dp(50),1));r.addView(tokenChip,new LinearLayout.LayoutParams(0,dp(50),1));LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-1,-2);lp.topMargin=dp(8);page.addView(r,lp);}
    private void buildTabs(){tabRow=new LinearLayout(this);tabRow.setOrientation(LinearLayout.HORIZONTAL);tabRow.setWeightSum(2);tabAuto=button("MULTIFY AUTO",NAVY,Color.WHITE);tabLab=button("30-DAY LAB",Color.TRANSPARENT,NAVY);tabAuto.setOnClickListener(v->{currentTab=0;styleTabs();renderBody();});tabLab.setOnClickListener(v->{currentTab=1;styleTabs();renderBody();});tabRow.addView(tabAuto,new LinearLayout.LayoutParams(0,dp(48),1));tabRow.addView(tabLab,new LinearLayout.LayoutParams(0,dp(48),1));LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-1,-2);lp.topMargin=dp(18);lp.bottomMargin=dp(10);page.addView(tabRow,lp);}
    private void styleTabs(){if(currentTab==0){tabAuto.setBackground(round(NAVY,dp(12),NAVY,0));tabAuto.setTextColor(Color.WHITE);tabLab.setBackground(round(Color.TRANSPARENT,dp(12),Color.rgb(215,220,229),1));tabLab.setTextColor(NAVY);}else{tabLab.setBackground(round(NAVY,dp(12),NAVY,0));tabLab.setTextColor(Color.WHITE);tabAuto.setBackground(round(Color.TRANSPARENT,dp(12),Color.rgb(215,220,229),1));tabAuto.setTextColor(NAVY);}}
    private void renderBody(){if(content==null)return;refreshChips();content.removeAllViews();if(currentTab==0)renderAuto();else renderLab();}

    private void renderAuto(){
        android.content.SharedPreferences s=getSharedPreferences("state",MODE_PRIVATE);TradeState t=new TradeStateStore(this).load();
        LinearLayout hero=card();TextView p=text("NET SHADOW P&L",12,MUTED,true);hero.addView(p);TextView value=text("₹"+money(t.pnl()),30,t.pnl()>=0?GREEN:RED,true);value.setPadding(0,dp(2),0,dp(4));hero.addView(value);hero.addView(text(t.side==Side.FLAT?"No open shadow position":t.symbol+"  •  "+t.side+"  •  Qty "+t.qty+"  •  Entry ₹"+money(t.entry),14,NAVY,true));hero.addView(text("Cost/slippage reserve ₹"+money(t.estimatedCosts)+"  •  Reversals today "+t.reversalsToday+"/3",12,MUTED,false));content.addView(hero,cardLp());

        LinearLayout live=card();live.addView(sectionTitle("Automation status","No run buttons required"));live.addView(metric("Last Multify equity intraday",s.getString("last_symbol","None")));live.addView(metric("Latest model signal",s.getString("last_signal","WAIT")+"  •  score "+String.format(Locale.US,"%.2f",s.getFloat("last_score",0))));live.addView(metric("Latest action",s.getString("last_action","Waiting for an eligible Multify notification")));live.addView(metric("NIFTY context",String.format(Locale.US,"%+.2f%%",s.getFloat("nifty_return",0)*100)));live.addView(metric("Evaluation frequency","On new Multify alert + every 5 min while active"));live.addView(metric("Intraday controls","No new entry after 15:00 • forced shadow exit 15:20"));content.addView(live,cardLp());

        LinearLayout rules=card();rules.addView(sectionTitle("Decision engine","HOLD-first, cost-aware"));rules.addView(text("EMA 9/21 • RSI • VWAP • MACD • volume expansion • engulfing • hammer/shooting star • breakout/breakdown • candle persistence • NIFTY relative strength",13,NAVY,false));TextView guard=text("ANTI-CHURN  •  15m minimum hold  •  2× reversal confirmation  •  10m cooldown  •  max 3 reversals/day",12,GREEN,true);guard.setPadding(0,dp(12),0,0);rules.addView(guard);content.addView(rules,cardLp());

        LinearLayout training=card();ModelConfig cfg=new ModelConfig(this);training.addView(sectionTitle("Automated end-of-day training","Runs after market close"));training.addView(text(cfg.trainingSummary(),13,NAVY,false));training.addView(text("Anti-overfit rule: no tuning before 10 sessions; then only a small capped threshold change from a rolling 20-session window.",12,MUTED,false));content.addView(training,cardLp());

        LinearLayout gate=card();gate.addView(sectionTitle("Live trading","Future execution gate"));gate.addView(text("Shadow monitoring is fully automated. Real-money order submission is intentionally locked in this build. Your static IP will matter only when an approved live execution path is added and the order traffic actually exits through that whitelisted IP.",13,NAVY,false));Button b=button("LIVE TRADING — LOCKED",Color.rgb(232,235,241),Color.rgb(92,99,112));b.setOnClickListener(v->new AlertDialog.Builder(this).setTitle("Live trading is locked").setMessage("This build does not send Groww order/create requests. Continue collecting shadow results first; a live mode should remain explicitly gated rather than silently switching to unattended real-money orders.").setPositiveButton("OK",null).show());LinearLayout.LayoutParams bl=new LinearLayout.LayoutParams(-1,dp(48));bl.topMargin=dp(12);gate.addView(b,bl);content.addView(gate,cardLp());

        LinearLayout log=card();log.addView(sectionTitle("Automation activity","Latest events"));log.addView(text(new EventStore(this).recentText(10),12,NAVY,false));content.addView(log,cardLp());
    }

    private void renderLab(){
        android.content.SharedPreferences p=getSharedPreferences("momentum",MODE_PRIVATE);LinearLayout head=card();head.addView(sectionTitle("30-Day Momentum Lab","Experimental +50% target candidates"));head.addView(text("The model continuously replays price/volume patterns and ranks NSE CASH/EQ stocks. A 50% target is a research target, not a guarantee.",13,NAVY,false));
        int cur=p.getInt("cursor",0),total=p.getInt("universe_size",0);head.addView(metric("Universe scan coverage",total==0?"Waiting for first automated scan":cur+" / "+total));head.addView(metric("Market regime",p.getString("market_regime","Pending")));head.addView(metric("Scan cadence","25 NSE equities per batch • every 30 min off-market"));head.addView(metric("Overfit control","Relative-strength context + rolling replay; model tuning uses multi-session windows"));content.addView(head,cardLp());

        LinearLayout toggle=new LinearLayout(this);toggle.setOrientation(LinearLayout.HORIZONTAL);toggle.setWeightSum(2);Button current=button("CURRENT",showClosed?Color.TRANSPARENT:NAVY,showClosed?NAVY:Color.WHITE);Button closed=button("CLOSED",showClosed?NAVY:Color.TRANSPARENT,showClosed?Color.WHITE:NAVY);current.setOnClickListener(v->{showClosed=false;renderBody();});closed.setOnClickListener(v->{showClosed=true;renderBody();});toggle.addView(current,new LinearLayout.LayoutParams(0,dp(44),1));toggle.addView(closed,new LinearLayout.LayoutParams(0,dp(44),1));content.addView(toggle,new LinearLayout.LayoutParams(-1,-2));

        JSONArray a=showClosed?MomentumLabEngine.closed(this):MomentumLabEngine.current(this);if(a.length()==0){LinearLayout empty=card();empty.addView(text(showClosed?"No completed 30-day predictions yet.":"No candidate has cleared the model threshold yet. The scanner runs automatically after market hours.",14,MUTED,false));content.addView(empty,cardLp());return;}
        ArrayList<JSONObject> list=new ArrayList<>();for(int i=0;i<a.length();i++)try{list.add(a.getJSONObject(i));}catch(Exception ignored){}Collections.sort(list,(x,y)->Double.compare(y.optDouble("score"),x.optDouble("score")));
        for(JSONObject o:list)content.addView(candidateCard(o,showClosed),cardLp());
    }
    private View candidateCard(JSONObject o,boolean closed){LinearLayout c=card();LinearLayout top=new LinearLayout(this);top.setOrientation(LinearLayout.HORIZONTAL);TextView name=text(o.optString("symbol"),20,NAVY,true);top.addView(name,new LinearLayout.LayoutParams(0,-2,1));TextView score=text(String.format(Locale.US,"%.0f/100",o.optDouble("score")),15,closed?(o.optBoolean("success")?GREEN:RED):BLUE,true);top.addView(score);c.addView(top);c.addView(text(closed?(o.optBoolean("success")?"TARGET HIT":"TARGET NOT HIT"):"50% TARGET CANDIDATE",11,closed?(o.optBoolean("success")?GREEN:RED):GREEN,true));c.addView(metric("Reference price","₹"+money(o.optDouble("price"))));c.addView(metric("+50% target","₹"+money(o.optDouble("target"))));if(closed)c.addView(metric("Highest observed","₹"+money(o.optDouble("maxSeen"))));else c.addView(metric("Expires",date(o.optLong("expiry"))));c.addView(text(o.optString("reason","Pattern replay in progress"),12,MUTED,false));return c;}

    private void authenticate(){String t=token.getText().toString().trim();if(t.isEmpty()){Toast.makeText(this,"Paste a Groww token",Toast.LENGTH_SHORT).show();return;}secure.put("token",t);getSharedPreferences("state",MODE_PRIVATE).edit().putLong("last_auth_check",0).apply();startAuto();new Thread(()->{try{new GrowwClient().user(t);runOnUiThread(()->{Toast.makeText(this,"Groww authenticated. Automation started.",Toast.LENGTH_SHORT).show();if(!notificationAccess())startActivity(new Intent("android.settings.ACTION_NOTIFICATION_LISTENER_SETTINGS"));renderBody();});}catch(Exception e){runOnUiThread(()->new AlertDialog.Builder(this).setTitle("Authentication failed").setMessage(e.getMessage()).setPositiveButton("OK",null).show());}}).start();}
    private void autoStart(){if(!secure.get("token").isEmpty())startAuto();}
    private void startAuto(){Intent i=new Intent(this,AutomationService.class);if(Build.VERSION.SDK_INT>=26)startForegroundService(i);else startService(i);}
    private void refreshChips(){android.content.SharedPreferences s=getSharedPreferences("state",MODE_PRIVATE);setChip(engineChip,s.getString("engine_status","Starting"),!secure.get("token").isEmpty());setChip(notifyChip,notificationAccess()?"MULTIFY ON":"SETUP NEEDED",notificationAccess());setChip(tokenChip,s.getBoolean("token_ok",false)?"TOKEN OK":"TOKEN",s.getBoolean("token_ok",false));}
    private boolean notificationAccess(){String flat=Settings.Secure.getString(getContentResolver(),"enabled_notification_listeners");return flat!=null&&flat.contains(getPackageName());}

    private TextView metric(String a,String b){TextView t=text(a+"\n"+b,13,NAVY,false);t.setPadding(0,dp(8),0,dp(4));return t;}
    private LinearLayout sectionTitle(String title,String small){LinearLayout r=new LinearLayout(this);r.setOrientation(LinearLayout.VERTICAL);r.addView(text(title,17,NAVY,true));r.addView(text(small,11,MUTED,false));r.setPadding(0,0,0,dp(5));return r;}
    private LinearLayout card(){LinearLayout x=new LinearLayout(this);x.setOrientation(LinearLayout.VERTICAL);x.setPadding(dp(16),dp(15),dp(16),dp(15));x.setBackground(round(CARD,dp(16),Color.rgb(229,233,240),1));x.setElevation(dp(1));return x;}
    private LinearLayout.LayoutParams cardLp(){LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(-1,-2);p.topMargin=dp(10);return p;}
    private TextView chip(String s){TextView t=text(s,10,MUTED,true);t.setGravity(Gravity.CENTER);t.setBackground(round(Color.WHITE,dp(12),Color.rgb(220,225,233),1));LinearLayout.LayoutParams p=(LinearLayout.LayoutParams)t.getLayoutParams();return t;}
    private void setChip(TextView t,String s,boolean ok){t.setText(s.toUpperCase(Locale.ROOT));t.setTextColor(ok?GREEN:MUTED);t.setBackground(round(ok?Color.rgb(234,248,241):Color.WHITE,dp(12),ok?Color.rgb(177,226,204):Color.rgb(220,225,233),1));}
    private TextView text(String s,int sp,int color,boolean bold){TextView t=new TextView(this);t.setText(s);t.setTextSize(sp);t.setTextColor(color);if(bold)t.setTypeface(Typeface.DEFAULT,Typeface.BOLD);t.setLineSpacing(0,1.08f);return t;}
    private Button button(String s,int bg,int fg){Button b=new Button(this);b.setText(s);b.setTextColor(fg);b.setTextSize(12);b.setTypeface(Typeface.DEFAULT,Typeface.BOLD);b.setAllCaps(false);b.setGravity(Gravity.CENTER);b.setBackground(round(bg,dp(12),bg==Color.TRANSPARENT?Color.rgb(215,220,229):bg,bg==Color.TRANSPARENT?1:0));return b;}
    private GradientDrawable round(int fill,int radius,int stroke,int sw){GradientDrawable g=new GradientDrawable();g.setColor(fill);g.setCornerRadius(radius);if(sw>0)g.setStroke(dp(sw),stroke);return g;}
    private int dp(int x){return (int)(x*getResources().getDisplayMetrics().density+.5f);}
    private String money(double x){return String.format(Locale.US,"%,.2f",x);}
    private String date(long x){return x<=0?"—":new SimpleDateFormat("dd MMM yyyy",Locale.getDefault()).format(new Date(x));}
}
