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
    private LinearLayout page,content,tabRow;
    private EditText totpToken,totpSecret;
    private TextView authMeta;
    private TextView engineChip,notifyChip,tokenChip;
    private Button tabAuto,tabLab;
    private SecureStore secure;
    private int currentTab=0;
    private boolean showClosed=false;
    private final Handler ui=new Handler(Looper.getMainLooper());
    private final Runnable refresh=new Runnable(){public void run(){renderBody();ui.postDelayed(this,3000);}};

    @Override public void onCreate(Bundle b){
        super.onCreate(b);
        getWindow().setStatusBarColor(NAVY);getWindow().setNavigationBarColor(Color.WHITE);
        secure=new SecureStore(this);buildShell();renderBody();Scheduler.schedule(this);autoStart();ui.postDelayed(refresh,3000);
    }
    @Override protected void onResume(){super.onResume();renderBody();autoStart();}
    @Override protected void onDestroy(){ui.removeCallbacks(refresh);super.onDestroy();}

    private void buildShell(){
        ScrollView scroll=new ScrollView(this);scroll.setFillViewport(true);
        page=new LinearLayout(this);page.setOrientation(LinearLayout.VERTICAL);page.setPadding(dp(18),dp(18),dp(18),dp(34));page.setBackgroundColor(BG);
        scroll.addView(page);setContentView(scroll);

        page.addView(text("PS SHADOW TRADER",26,NAVY,true));
        TextView sub=text("v1.6.1 • Multify capture + guarded 30-day lab",13,MUTED,false);sub.setPadding(0,dp(2),0,dp(14));page.addView(sub);

        buildAuthCard();buildStatusRow();buildTabs();
        content=new LinearLayout(this);content.setOrientation(LinearLayout.VERTICAL);page.addView(content,new LinearLayout.LayoutParams(-1,-2));
    }

    private void buildAuthCard(){
        LinearLayout card=card();
        LinearLayout title=new LinearLayout(this);title.setOrientation(LinearLayout.HORIZONTAL);
        title.addView(text("BROKER AUTH",13,NAVY,true),new LinearLayout.LayoutParams(0,-2,1));
        TextView secureBadge=text("ENCRYPTED",10,GREEN,true);secureBadge.setGravity(Gravity.RIGHT);title.addView(secureBadge);
        card.addView(title);

        totpToken=secretField("Groww TOTP Token");totpToken.setText(secure.get("totp_token"));
        LinearLayout.LayoutParams p1=new LinearLayout.LayoutParams(-1,dp(48));p1.topMargin=dp(10);card.addView(totpToken,p1);

        totpSecret=secretField("Groww TOTP Secret");totpSecret.setText(secure.get("totp_secret"));
        LinearLayout.LayoutParams p2=new LinearLayout.LayoutParams(-1,dp(48));p2.topMargin=dp(7);card.addView(totpSecret,p2);

        LinearLayout buttons=new LinearLayout(this);buttons.setOrientation(LinearLayout.HORIZONTAL);buttons.setWeightSum(2);
        Button save=button("SAVE",Color.rgb(238,242,249),NAVY);save.setOnClickListener(v->saveAuthCredentials());
        Button auth=button("REFRESH / AUTHENTICATE",BLUE,Color.WHITE);auth.setOnClickListener(v->refreshAuthenticate());
        LinearLayout.LayoutParams a=new LinearLayout.LayoutParams(0,dp(46),1);a.rightMargin=dp(4);
        LinearLayout.LayoutParams b=new LinearLayout.LayoutParams(0,dp(46),1);b.leftMargin=dp(4);
        buttons.addView(save,a);buttons.addView(auth,b);
        LinearLayout.LayoutParams bp=new LinearLayout.LayoutParams(-1,-2);bp.topMargin=dp(9);card.addView(buttons,bp);

        authMeta=text("Daily authentication refresh enabled",10,MUTED,false);
        authMeta.setPadding(0,dp(8),0,0);card.addView(authMeta);
        page.addView(card,cardLp());
    }

    private EditText secretField(String hint){
        EditText e=new EditText(this);e.setHint(hint);e.setSingleLine(true);
        e.setInputType(InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_PASSWORD);
        e.setPadding(dp(14),dp(12),dp(14),dp(12));
        e.setBackground(round(Color.rgb(245,247,250),dp(12),Color.rgb(220,225,233),1));return e;
    }

    private void buildStatusRow(){
        LinearLayout r=new LinearLayout(this);r.setOrientation(LinearLayout.HORIZONTAL);r.setWeightSum(3);
        engineChip=chip("ENGINE");notifyChip=chip("MULTIFY");tokenChip=chip("AUTH");
        LinearLayout.LayoutParams p1=new LinearLayout.LayoutParams(0,dp(46),1);p1.rightMargin=dp(3);
        LinearLayout.LayoutParams p2=new LinearLayout.LayoutParams(0,dp(46),1);p2.leftMargin=dp(3);p2.rightMargin=dp(3);
        LinearLayout.LayoutParams p3=new LinearLayout.LayoutParams(0,dp(46),1);p3.leftMargin=dp(3);
        r.addView(engineChip,p1);r.addView(notifyChip,p2);r.addView(tokenChip,p3);
        LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-1,-2);lp.topMargin=dp(8);page.addView(r,lp);
    }

    private void buildTabs(){
        tabRow=new LinearLayout(this);tabRow.setOrientation(LinearLayout.HORIZONTAL);tabRow.setWeightSum(2);
        tabAuto=button("MULTIFY ADAPTIVE",NAVY,Color.WHITE);tabLab=button("30-DAY LAB",Color.TRANSPARENT,NAVY);
        tabAuto.setOnClickListener(v->{currentTab=0;styleTabs();renderBody();});
        tabLab.setOnClickListener(v->{currentTab=1;styleTabs();renderBody();});
        tabRow.addView(tabAuto,new LinearLayout.LayoutParams(0,dp(48),1));tabRow.addView(tabLab,new LinearLayout.LayoutParams(0,dp(48),1));
        LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-1,-2);lp.topMargin=dp(18);lp.bottomMargin=dp(10);page.addView(tabRow,lp);
    }

    private void styleTabs(){
        if(currentTab==0){
            tabAuto.setBackground(round(NAVY,dp(12),NAVY,0));tabAuto.setTextColor(Color.WHITE);
            tabLab.setBackground(round(Color.TRANSPARENT,dp(12),Color.rgb(215,220,229),1));tabLab.setTextColor(NAVY);
        }else{
            tabLab.setBackground(round(NAVY,dp(12),NAVY,0));tabLab.setTextColor(Color.WHITE);
            tabAuto.setBackground(round(Color.TRANSPARENT,dp(12),Color.rgb(215,220,229),1));tabAuto.setTextColor(NAVY);
        }
    }

    private void renderBody(){if(content==null)return;refreshChips();content.removeAllViews();if(currentTab==0)renderAuto();else renderLab();}

    private void renderAuto(){
        android.content.SharedPreferences st=getSharedPreferences("state",MODE_PRIVATE);
        android.content.SharedPreferences cfg=getSharedPreferences("trading_ui",MODE_PRIVATE);
        TradeState t=new TradeStateStore(this).load();
        AdaptiveModel model=new AdaptiveModel(this);
        TodayStats today=todayStats();
        int calls=todayMultifyCalls();

        LinearLayout hero=card();
        LinearLayout htop=new LinearLayout(this);htop.setOrientation(LinearLayout.HORIZONTAL);
        LinearLayout left=new LinearLayout(this);left.setOrientation(LinearLayout.VERTICAL);
        left.addView(text("SHADOW P&L",11,MUTED,true));
        TextView pnl=text("₹"+money(t.pnl()),30,t.pnl()>=0?GREEN:RED,true);left.addView(pnl);
        htop.addView(left,new LinearLayout.LayoutParams(0,-2,1));
        LinearLayout right=new LinearLayout(this);right.setOrientation(LinearLayout.VERTICAL);right.setGravity(Gravity.RIGHT);
        right.addView(text("FIXED TRADE SIZE",10,MUTED,true));
        TextView budget=text("₹10,000",18,NAVY,true);budget.setGravity(Gravity.RIGHT);right.addView(budget);
        htop.addView(right,new LinearLayout.LayoutParams(0,-2,1));
        hero.addView(htop);
        String pos=t.side==Side.FLAT?"FLAT":t.symbol+" • "+t.side+" • "+t.qty+" qty";
        hero.addView(text(pos,13,t.side==Side.FLAT?MUTED:NAVY,true));
        content.addView(hero,cardLp());

        LinearLayout kpis=card();
        kpis.addView(sectionTitle("TODAY","Multify shadow performance"));
        kpis.addView(kpiRow("CALLS",Integer.toString(calls),"TRADES",Integer.toString(today.trades)));
        kpis.addView(kpiRow("WINS",Integer.toString(today.wins),"LOSSES",Integer.toString(today.losses)));
        kpis.addView(kpiRow("CLOSED P&L","₹"+money(today.pnlRs),"HIT RATE",today.trades==0?"—":String.format(Locale.US,"%.0f%%",(double)today.wins/today.trades*100)));
        content.addView(kpis,cardLp());

        LinearLayout setup=card();
        setup.addView(sectionTitle("TRADING SETUP","Configuration"));
        String ip=cfg.getString("static_ip","");
        int liveBudget=cfg.getInt("live_budget",10000);
        setup.addView(kpiRow("STATIC IP",ip.isEmpty()?"NOT SET":ip,"LIVE BUDGET","₹"+String.format(Locale.US,"%,d",liveBudget)));
        setup.addView(kpiRow("SHADOW SIZE","₹10,000","LIVE EXECUTION","LOCKED"));
        Button edit=button("EDIT STATIC IP / BUDGET",Color.rgb(238,242,249),NAVY);
        edit.setOnClickListener(v->openLiveSetup());
        LinearLayout.LayoutParams ep=new LinearLayout.LayoutParams(-1,dp(44));ep.topMargin=dp(8);setup.addView(edit,ep);
        content.addView(setup,cardLp());

        LinearLayout position=card();
        position.addView(sectionTitle("OPEN POSITION",t.side==Side.FLAT?"No active shadow trade":"Live shadow position"));
        if(t.side==Side.FLAT){
            position.addView(text("Waiting for a valid Multify intraday call.",13,MUTED,false));
        }else{
            double openPnl=t.unrealized()-t.estimatedCosts;
            position.addView(kpiRow("SYMBOL",t.symbol,"SIDE",t.side.name()));
            position.addView(kpiRow("ENTRY","₹"+money(t.entry),"LTP","₹"+money(t.last)));
            position.addView(kpiRow("QTY",Integer.toString(t.qty),"OPEN P&L","₹"+money(openPnl)));
            position.addView(kpiRow("OPENED",clock(t.openedAtMs),"ACTION",st.getString("last_signal","WAIT")));
        }
        content.addView(position,cardLp());

        LinearLayout signal=card();
        signal.addView(sectionTitle("MULTIFY","Live decision state"));
        signal.addView(metric("Watchlist",new WatchlistStore(this).display()));
        signal.addView(metric("Last event",blankDash(st.getString("last_multify_event","Waiting"))));
        signal.addView(metric("Decision",st.getString("last_signal","WAIT")+" • "+String.format(Locale.US,"%.0f%%",st.getFloat("last_confidence",0)*100)+" • edge "+String.format(Locale.US,"%.2f%%",st.getFloat("last_edge",0)*100)));
        signal.addView(metric("Action",blankDash(st.getString("last_action","Waiting"))));
        signal.addView(metric("NIFTY",String.format(Locale.US,"%+.2f%%",st.getFloat("nifty_return",0)*100)));
        content.addView(signal,cardLp());

        LinearLayout learning=card();
        ChampionStore champion=new ChampionStore(this);
        learning.addView(sectionTitle("LEARNING","Champion + live outcomes"));
        learning.addView(kpiRow("CHAMPION","G"+champion.generation(),"CLOSED",Integer.toString(model.trades())));
        learning.addView(kpiRow("HIT RATE",model.trades()==0?"—":String.format(Locale.US,"%.0f%%",model.hitRate()*100),"TURNOVER",String.format(Locale.US,"%.2fx",model.turnoverPenalty())));
        learning.addView(metric("Tournament",blankDash(st.getString("tournament_status","Waiting for replay history"))));
        content.addView(learning,cardLp());

        LinearLayout closed=card();
        closed.addView(sectionTitle("RECENT CLOSED","Last shadow outcomes"));
        closed.addView(text(recentClosedTrades(5),12,NAVY,false));
        content.addView(closed,cardLp());

        LinearLayout log=card();
        log.addView(sectionTitle("EVENTS","Latest Multify / model activity"));
        log.addView(text(new EventStore(this).recentText(6),12,NAVY,false));
        content.addView(log,cardLp());
    }

    private void renderLab(){
        android.content.SharedPreferences p=getSharedPreferences("momentum",MODE_PRIVATE);
        LongHorizonChampionStore labChampion=new LongHorizonChampionStore(this);
        LinearLayout head=card();head.addView(sectionTitle("30-Day Champion Lab","Independent +50% within 30 calendar days"));
        LongHorizonChampionStore.Profile labProfile=labChampion.current();
        boolean labValidated=labChampion.generation()>0&&labProfile.holdoutSignals>=6&&labProfile.holdoutPrecision>=.25;
        head.addView(text(labValidated?"VALIDATED CHAMPION":"RESEARCH MODE • MODEL SCORES ARE NOT PROBABILITIES",11,labValidated?GREEN:BLUE,true));
        int cur=p.getInt("cursor",0),total=p.getInt("universe_size",0);
        head.addView(metric("Universe scan coverage",total==0?"Waiting for first automated scan":cur+" / "+total));
        String labStatus=getSharedPreferences("state",MODE_PRIVATE).getString("last_lab_status","Waiting for first automated scan");
        long labDone=getSharedPreferences("state",MODE_PRIVATE).getLong("last_lab_complete_ts",0);
        head.addView(metric("Last scan",labDone>0?dateTime(labDone)+" IST • "+labStatus:labStatus));
        head.addView(metric("Market regime",p.getString("market_regime","Pending")));
        head.addView(metric("Scanner","Autonomous full-universe rotating NSE scan • cached progress"));
        head.addView(metric("Validation","30-calendar-day labels • unseen holdout • exhaustion guard • rejected-stock controls"));
        head.addView(metric("30-day champion",labChampion.profileSummary()));
        head.addView(metric("Tournament",labChampion.summary()));
        head.addView(metric("Prediction scorecard",MomentumLabEngine.scorecard(this)));
        content.addView(head,cardLp());

        LinearLayout toggle=new LinearLayout(this);toggle.setOrientation(LinearLayout.HORIZONTAL);toggle.setWeightSum(2);
        Button current=button("CURRENT",showClosed?Color.TRANSPARENT:NAVY,showClosed?NAVY:Color.WHITE);
        Button closed=button("CLOSED",showClosed?NAVY:Color.TRANSPARENT,showClosed?Color.WHITE:NAVY);
        current.setOnClickListener(v->{showClosed=false;renderBody();});closed.setOnClickListener(v->{showClosed=true;renderBody();});
        toggle.addView(current,new LinearLayout.LayoutParams(0,dp(44),1));toggle.addView(closed,new LinearLayout.LayoutParams(0,dp(44),1));content.addView(toggle,new LinearLayout.LayoutParams(-1,-2));

        JSONArray a=showClosed?MomentumLabEngine.closed(this):MomentumLabEngine.current(this);
        if(a.length()==0){
            LinearLayout empty=card();
            empty.addView(text(showClosed?"No completed 30-day predictions yet.":"No candidate has cleared the model threshold yet. The scanner runs automatically.",14,MUTED,false));
            content.addView(empty,cardLp());return;
        }
        ArrayList<JSONObject> list=new ArrayList<>();for(int i=0;i<a.length();i++)try{list.add(a.getJSONObject(i));}catch(Exception ignored){}
        Collections.sort(list,(x,y)->Double.compare(
                y.has("confidence")?y.optDouble("confidence"):y.optDouble("score"),
                x.has("confidence")?x.optDouble("confidence"):x.optDouble("score")));
        for(JSONObject o:list)content.addView(candidateCard(o,showClosed),cardLp());
    }

    private View candidateCard(JSONObject o,boolean closed){
        LinearLayout c=card();
        LinearLayout top=new LinearLayout(this);top.setOrientation(LinearLayout.HORIZONTAL);
        TextView name=text(o.optString("symbol"),20,NAVY,true);top.addView(name,new LinearLayout.LayoutParams(0,-2,1));

        double originalScore=o.has("confidence")?o.optDouble("confidence"):o.optDouble("score");
        TextView score=text(String.format(Locale.US,"%.0f/100",originalScore*100),15,closed?(o.optBoolean("success")?GREEN:RED):BLUE,true);
        top.addView(score);c.addView(top);

        boolean validated=o.optBoolean("validated",o.optInt("generation",0)>0);
        if(closed){
            boolean win=o.optBoolean("success");
            c.addView(text(win?"WIN • +50% TARGET HIT":"LOSS • +50% TARGET MISSED",12,win?GREEN:RED,true));
        }else{
            c.addView(text(validated?"VALIDATED CANDIDATE • SNAPSHOT LOCKED":"RESEARCH CANDIDATE • UNVALIDATED • SNAPSHOT LOCKED",11,validated?GREEN:BLUE,true));
            c.addView(text("MODEL SCORE • NOT A PROBABILITY",10,MUTED,true));
        }

        long first=o.optLong("firstRecommended",o.optLong("created"));
        c.addView(metric("First recommended",dateTime(first)+" IST"));
        c.addView(metric("Original reference price","₹"+money(o.optDouble("price"))));
        c.addView(metric("Original +50% target","₹"+money(o.optDouble("target"))));

        if(o.has("champion")){
            c.addView(metric("Original model snapshot","Champion "+o.optString("champion")+" • generation "+o.optInt("generation")+" • model score "+String.format(Locale.US,"%.0f/100",originalScore*100)));
        }

        int matches=o.optInt("matches",0);
        double hitRate=o.optDouble("replayHitRate",0),medianPeak=o.optDouble("replayMedianPeak",0);
        String risk=o.optString("extensionRisk","UNKNOWN");
        int circuitLike=o.optInt("circuitLike",0);
        String sector=o.optString("sector","UNKNOWN");
        if(matches>0)c.addView(metric("Evidence",String.format(Locale.US,"Replay %.0f%% (%d/%d) • median peak %.1f%% • extension %s • circuit-like %d • sector %s",
                hitRate*100,(int)Math.round(hitRate*matches),matches,medianPeak*100,risk,circuitLike,sector)));

        if(closed){
            c.addView(metric("Closed",dateTime(o.optLong("closed"))+" IST"));
            c.addView(metric("Result",o.optString("result",o.optBoolean("success")?"WIN":"LOSS")+" • "+o.optString("closeReason",o.optBoolean("success")?"Target hit":"Window expired")));
            c.addView(metric("Highest observed","₹"+money(o.optDouble("maxSeen"))));
            c.addView(metric("Outcome",String.format(Locale.US,"Max gain %+.1f%% • drawdown %.1f%% • close return %+.1f%%",
                    o.optDouble("maxGain")*100,o.optDouble("maxDrawdown")*100,o.optDouble("closeReturn")*100)));
        }else{
            if(o.has("lastObserved"))c.addView(metric("Latest observed price","₹"+money(o.optDouble("lastObserved"))));
            if(o.has("lastEvaluated"))c.addView(metric("Last evaluated",dateTime(o.optLong("lastEvaluated"))+" IST"));
            if(o.has("latestModelScore"))c.addView(metric("Latest model score",String.format(Locale.US,"%.0f/100",o.optDouble("latestModelScore")*100)+" • original snapshot remains locked"));
            c.addView(metric("Expires",dateTime(o.optLong("expiry"))+" IST"));
        }

        c.addView(text(o.optString("reason","Pattern replay in progress"),12,MUTED,false));
        return c;
    }

    private static final class TodayStats{
        int trades,wins,losses; double pnlRs;
    }

    private TodayStats todayStats(){
        TodayStats out=new TodayStats();
        try{
            android.content.SharedPreferences p=getSharedPreferences("adaptive_model",MODE_PRIVATE);
            JSONArray a=new JSONArray(p.getString("trades","[]"));
            Calendar now=Calendar.getInstance();
            int y=now.get(Calendar.YEAR),d=now.get(Calendar.DAY_OF_YEAR);
            for(int i=0;i<a.length();i++){
                JSONObject o=a.getJSONObject(i);Calendar c=Calendar.getInstance();c.setTimeInMillis(o.optLong("ts",0));
                if(c.get(Calendar.YEAR)!=y||c.get(Calendar.DAY_OF_YEAR)!=d)continue;
                double net=o.optDouble("net_pct",0);out.trades++;if(net>0)out.wins++;else out.losses++;out.pnlRs+=net*10000.0;
            }
        }catch(Exception ignored){}
        return out;
    }

    private int todayMultifyCalls(){
        int n=0;
        try{
            JSONArray a=new JSONArray(getSharedPreferences("state",MODE_PRIVATE).getString("events","[]"));
            Calendar now=Calendar.getInstance();int y=now.get(Calendar.YEAR),d=now.get(Calendar.DAY_OF_YEAR);
            for(int i=0;i<a.length();i++){
                JSONObject o=a.getJSONObject(i);Calendar c=Calendar.getInstance();c.setTimeInMillis(o.optLong("ts",0));
                if(c.get(Calendar.YEAR)!=y||c.get(Calendar.DAY_OF_YEAR)!=d)continue;
                if("MULTIFY".equals(o.optString("type"))&&o.optString("text").startsWith("NEW "))n++;
            }
        }catch(Exception ignored){}
        return n;
    }

    private String recentClosedTrades(int max){
        try{
            JSONArray a=new JSONArray(getSharedPreferences("adaptive_model",MODE_PRIVATE).getString("trades","[]"));
            if(a.length()==0)return "No closed shadow trades yet.";
            StringBuilder b=new StringBuilder();int shown=0;
            for(int i=a.length()-1;i>=0&&shown<max;i--,shown++){
                JSONObject o=a.getJSONObject(i);double net=o.optDouble("net_pct",0);
                if(b.length()>0)b.append("\n");
                b.append(clock(o.optLong("ts"))).append("  ")
                        .append(o.optString("symbol")).append(" ").append(o.optString("side"))
                        .append("  ").append(net>0?"WIN ":"LOSS ")
                        .append(String.format(Locale.US,"%+.2f%%",net*100));
                if(o.has("capture"))b.append(" • cap ").append(String.format(Locale.US,"%.0f%%",o.optDouble("capture")*100));
                String pm=o.optString("postmortem","");
                if(!pm.isEmpty()&&!pm.equals("WIN"))b.append(" • ").append(pm);
            }
            return b.toString();
        }catch(Exception e){return "Closed-trade history unavailable.";}
    }

    private void openLiveSetup(){
        final android.content.SharedPreferences cfg=getSharedPreferences("trading_ui",MODE_PRIVATE);
        LinearLayout box=new LinearLayout(this);box.setOrientation(LinearLayout.VERTICAL);box.setPadding(dp(8),dp(4),dp(8),0);

        EditText ip=new EditText(this);ip.setSingleLine(true);ip.setHint("Registered static IPv4");
        ip.setInputType(InputType.TYPE_CLASS_PHONE);ip.setText(cfg.getString("static_ip",""));
        ip.setPadding(dp(12),dp(10),dp(12),dp(10));ip.setBackground(round(Color.rgb(245,247,250),dp(10),Color.rgb(220,225,233),1));
        box.addView(ip,new LinearLayout.LayoutParams(-1,dp(48)));

        TextView amount=text("",18,NAVY,true);amount.setPadding(0,dp(14),0,dp(4));box.addView(amount);
        SeekBar bar=new SeekBar(this);bar.setMax(100);
        int initial=Math.max(0,Math.min(100000,cfg.getInt("live_budget",10000)));bar.setProgress(initial/1000);
        amount.setText("Live budget  ₹"+String.format(Locale.US,"%,d",bar.getProgress()*1000));
        bar.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener(){
            public void onProgressChanged(SeekBar s,int progress,boolean fromUser){amount.setText("Live budget  ₹"+String.format(Locale.US,"%,d",progress*1000));}
            public void onStartTrackingTouch(SeekBar s){}
            public void onStopTrackingTouch(SeekBar s){}
        });
        box.addView(bar,new LinearLayout.LayoutParams(-1,dp(48)));
        TextView note=text("0 – ₹1,00,000 • live execution remains locked in this build",11,MUTED,false);box.addView(note);

        AlertDialog dlg=new AlertDialog.Builder(this).setTitle("Trading setup").setView(box)
                .setNegativeButton("CANCEL",null).setPositiveButton("SAVE",null).create();
        dlg.setOnShowListener(x->dlg.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(v->{
            String val=ip.getText().toString().trim();
            if(!val.isEmpty()&&!isValidIpv4(val)){ip.setError("Enter a valid IPv4 address");return;}
            cfg.edit().putString("static_ip",val).putInt("live_budget",bar.getProgress()*1000).apply();
            dlg.dismiss();renderBody();
        }));
        dlg.show();
    }

    private boolean isValidIpv4(String s){
        String[] p=s.split("\\.");if(p.length!=4)return false;
        try{for(String q:p){if(q.isEmpty()||q.length()>3)return false;int x=Integer.parseInt(q);if(x<0||x>255)return false;if(q.length()>1&&q.startsWith("0"))return false;}return true;}
        catch(Exception e){return false;}
    }

    private View kpiRow(String a,String av,String b,String bv){
        LinearLayout r=new LinearLayout(this);r.setOrientation(LinearLayout.HORIZONTAL);r.setWeightSum(2);
        r.addView(kpiCell(a,av),new LinearLayout.LayoutParams(0,-2,1));
        r.addView(kpiCell(b,bv),new LinearLayout.LayoutParams(0,-2,1));
        return r;
    }

    private View kpiCell(String label,String value){
        LinearLayout x=new LinearLayout(this);x.setOrientation(LinearLayout.VERTICAL);x.setPadding(0,dp(7),dp(8),dp(7));
        x.addView(text(label,10,MUTED,true));x.addView(text(value,15,NAVY,true));return x;
    }

    private String clock(long ts){
        if(ts<=0)return "—";SimpleDateFormat f=new SimpleDateFormat("HH:mm:ss",Locale.getDefault());f.setTimeZone(TimeZone.getTimeZone("Asia/Kolkata"));return f.format(new Date(ts));
    }

    private boolean validateTotpFields(){
        String tt=totpToken.getText().toString().trim().replace(" ","");
        String ts=totpSecret.getText().toString().trim().replace(" ","");
        if(tt.isEmpty()||ts.isEmpty()){
            new AlertDialog.Builder(this).setTitle("TOTP details required")
                    .setMessage("Enter both the Groww TOTP Token and TOTP Secret.")
                    .setPositiveButton("OK",null).show();
            return false;
        }
        return true;
    }

    private void saveAuthCredentials(){
        if(!validateTotpFields())return;
        String tt=totpToken.getText().toString().trim().replace(" ","");
        String ts=totpSecret.getText().toString().trim().replace(" ","");
        secure.put("totp_token",tt);secure.put("totp_secret",ts);
        getSharedPreferences("state",MODE_PRIVATE).edit()
                .putBoolean("token_ok",false).putLong("last_auth_check",0).apply();
        Toast.makeText(this,"TOTP credentials saved securely.",Toast.LENGTH_SHORT).show();
        startAuto();renderBody();
    }

    private void refreshAuthenticate(){
        if(!validateTotpFields())return;
        final String tt=totpToken.getText().toString().trim().replace(" ","");
        final String ts=totpSecret.getText().toString().trim().replace(" ","");
        secure.put("totp_token",tt);secure.put("totp_secret",ts);

        final android.content.SharedPreferences state=getSharedPreferences("state",MODE_PRIVATE);
        state.edit().putBoolean("token_ok",false).putLong("last_auth_check",0).apply();
        setChip(tokenChip,"AUTHENTICATING",false);
        if(authMeta!=null)authMeta.setText("Refreshing Groww authentication…");

        new Thread(()->{
            try{
                GrowwClient api=new GrowwClient();
                String code=TotpUtil.now(ts);
                String access=api.generateAccessTokenTotp(tt,code);
                api.user(access);secure.put("token",access);
                long now=System.currentTimeMillis();
                state.edit().putBoolean("token_ok",true).putLong("last_auth_check",now)
                        .putLong("last_daily_auth_day",localDayKey())
                        .putString("auth_mode","Automatic TOTP")
                        .putString("engine_status","Ready").apply();
                new EventStore(this).add("AUTH","Groww TOTP authentication refreshed successfully");
                runOnUiThread(()->{
                    Toast.makeText(this,"Authenticated successfully.",Toast.LENGTH_SHORT).show();
                    startAuto();
                    if(!notificationAccess())startActivity(new Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS));
                    refreshChips();renderBody();
                });
            }catch(Exception e){
                state.edit().putBoolean("token_ok",false).putString("engine_status","Authentication attention").apply();
                new EventStore(this).add("AUTH","Authentication failed: "+(e.getMessage()==null?e.getClass().getSimpleName():e.getMessage()));
                runOnUiThread(()->{
                    refreshChips();
                    new AlertDialog.Builder(this).setTitle("Groww authentication failed")
                            .setMessage(e.getMessage()==null?e.getClass().getSimpleName():e.getMessage())
                            .setPositiveButton("OK",null).show();
                });
            }
        }).start();
    }

    private long localDayKey(){
        Calendar c=Calendar.getInstance(TimeZone.getTimeZone("Asia/Kolkata"));
        return c.get(Calendar.YEAR)*1000L+c.get(Calendar.DAY_OF_YEAR);
    }

    private void autoStart(){if(!secure.get("token").isEmpty()||hasTotp())startAuto();}
    private void startAuto(){Intent i=new Intent(this,AutomationService.class);if(Build.VERSION.SDK_INT>=26)startForegroundService(i);else startService(i);}
    private boolean hasTotp(){return !secure.get("totp_token").isEmpty()&&!secure.get("totp_secret").isEmpty();}

    private void refreshChips(){
        android.content.SharedPreferences s=getSharedPreferences("state",MODE_PRIVATE);
        long now=System.currentTimeMillis(), heartbeat=s.getLong("service_heartbeat",0);
        boolean engineOk=heartbeat>0&&now-heartbeat<150000L;
        boolean notifyOk=notificationAccess(), authOk=s.getBoolean("token_ok",false);

        setChip(engineChip,engineOk?"ENGINE ON":"ENGINE START",engineOk);
        setChip(notifyChip,notifyOk?"MULTIFY ON":"MULTIFY SETUP",notifyOk);
        if(authOk)setChip(tokenChip,"AUTH OK",true);
        else if(hasTotp())setChip(tokenChip,"AUTH READY",false);
        else setChip(tokenChip,"AUTH SETUP",false);

        if(authMeta!=null){
            long last=s.getLong("last_auth_check",0);
            authMeta.setText(last>0?"Last authenticated "+clock(last)+" IST • daily refresh enabled":"Daily authentication refresh enabled");
        }
    }

    private boolean notificationAccess(){String flat=Settings.Secure.getString(getContentResolver(),"enabled_notification_listeners");return flat!=null&&flat.contains(getPackageName());}
    private String blankDash(String s){return s==null||s.trim().isEmpty()?"—":s;}
    private TextView metric(String a,String b){TextView t=text(a+"\n"+b,13,NAVY,false);t.setPadding(0,dp(8),0,dp(4));return t;}
    private LinearLayout sectionTitle(String title,String small){LinearLayout r=new LinearLayout(this);r.setOrientation(LinearLayout.VERTICAL);r.addView(text(title,17,NAVY,true));r.addView(text(small,11,MUTED,false));r.setPadding(0,0,0,dp(5));return r;}
    private LinearLayout card(){LinearLayout x=new LinearLayout(this);x.setOrientation(LinearLayout.VERTICAL);x.setPadding(dp(16),dp(15),dp(16),dp(15));x.setBackground(round(CARD,dp(16),Color.rgb(229,233,240),1));x.setElevation(dp(1));return x;}
    private LinearLayout.LayoutParams cardLp(){LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(-1,-2);p.topMargin=dp(10);return p;}
    private TextView chip(String s){TextView t=text(s,9,MUTED,true);t.setGravity(Gravity.CENTER);t.setSingleLine(true);t.setBackground(round(Color.WHITE,dp(12),Color.rgb(220,225,233),1));return t;}
    private void setChip(TextView t,String s,boolean ok){t.setText(s.toUpperCase(Locale.ROOT));t.setTextColor(ok?GREEN:MUTED);t.setBackground(round(ok?Color.rgb(234,248,241):Color.WHITE,dp(12),ok?Color.rgb(177,226,204):Color.rgb(220,225,233),1));}
    private TextView text(String s,int sp,int color,boolean bold){TextView t=new TextView(this);t.setText(s);t.setTextSize(sp);t.setTextColor(color);if(bold)t.setTypeface(Typeface.DEFAULT,Typeface.BOLD);t.setLineSpacing(0,1.08f);return t;}
    private Button button(String s,int bg,int fg){Button b=new Button(this);b.setText(s);b.setTextColor(fg);b.setTextSize(12);b.setTypeface(Typeface.DEFAULT,Typeface.BOLD);b.setAllCaps(false);b.setGravity(Gravity.CENTER);b.setBackground(round(bg,dp(12),bg==Color.TRANSPARENT?Color.rgb(215,220,229):bg,bg==Color.TRANSPARENT?1:0));return b;}
    private GradientDrawable round(int fill,int radius,int stroke,int sw){GradientDrawable g=new GradientDrawable();g.setColor(fill);g.setCornerRadius(radius);if(sw>0)g.setStroke(dp(sw),stroke);return g;}
    private int dp(int x){return (int)(x*getResources().getDisplayMetrics().density+.5f);}
    private String money(double x){return String.format(Locale.US,"%,.2f",x);}
    private String date(long x){return x<=0?"—":new SimpleDateFormat("dd MMM yyyy",Locale.getDefault()).format(new Date(x));}
    private String dateTime(long x){
        if(x<=0)return "—";
        SimpleDateFormat f=new SimpleDateFormat("dd MMM yyyy • HH:mm:ss",Locale.getDefault());
        f.setTimeZone(TimeZone.getTimeZone("Asia/Kolkata"));
        return f.format(new Date(x));
    }
}
