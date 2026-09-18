package com.ps.shadowtrader;

import android.app.*; import android.os.*; import android.content.*; import android.graphics.Color; import android.provider.Settings; import android.view.*; import android.widget.*; import java.text.*; import java.util.*;
import static com.ps.shadowtrader.Models.*;

public class MainActivity extends Activity {
    LinearLayout root; TextView status,log,pnl; EditText token,key,secret,totp,symbol; SecureStore store; final TradeState trade=new TradeState(); final StrategyEngine engine=new StrategyEngine(); final GrowwClient api=new GrowwClient();
    @Override public void onCreate(Bundle b){super.onCreate(b);store=new SecureStore(this);build();Scheduler.schedule(this);refreshUi();}
    TextView tv(String s,int sp){TextView v=new TextView(this);v.setText(s);v.setTextSize(sp);v.setTextColor(Color.rgb(25,25,25));v.setPadding(12,8,12,8);return v;}
    EditText field(String hint){EditText e=new EditText(this);e.setHint(hint);e.setSingleLine(true);root.addView(e,new LinearLayout.LayoutParams(-1,-2));return e;}
    Button btn(String t,View.OnClickListener x){Button b=new Button(this);b.setText(t);b.setOnClickListener(x);root.addView(b,new LinearLayout.LayoutParams(-1,-2));return b;}
    void build(){ScrollView sv=new ScrollView(this);root=new LinearLayout(this);root.setOrientation(LinearLayout.VERTICAL);root.setPadding(22,22,22,30);sv.addView(root);setContentView(sv);
        TextView h=tv("PS Shadow Trader",26);h.setTypeface(null,1);root.addView(h);root.addView(tv("Paper/shadow engine — no real order placement",14));
        status=tv("Status",14);root.addView(status); pnl=tv("Shadow P&L: ₹0.00",22);pnl.setTypeface(null,1);root.addView(pnl);
        btn("Enable Notification Access",v->startActivity(new Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS)));
        token=field("Groww Access Token (optional)"); key=field("Groww API Key (optional)"); secret=field("Groww API Secret (optional)"); totp=field("TOTP code (manual field / reserved)");
        btn("Save Credentials Securely",v->{store.put("token",token.getText().toString().trim());store.put("key",key.getText().toString().trim());store.put("secret",secret.getText().toString().trim());Toast.makeText(this,"Saved in Android Keystore-backed storage",Toast.LENGTH_SHORT).show();});
        btn("Connect / Test Groww",v->connect());
        symbol=field("NSE symbol e.g. RELIANCE"); btn("Run Live Shadow Analysis",v->analyze()); btn("Run End-of-Day Replay Now",v->analyze());
        log=tv("Strategy log",14);root.addView(log);
    }
    void refreshUi(){token.setText(store.get("token"));key.setText(store.get("key"));secret.setText(store.get("secret"));String s=getSharedPreferences("state",MODE_PRIVATE).getString("last_symbol","");if(!s.isEmpty())symbol.setText(s);status.setText("Budget ₹1,00,000 • Equity/CASH only • Anti-churn ON • 15m min hold • 2× reversal confirmation • Max 3 reversals/day • Last Multify symbol: "+(s.isEmpty()?"none":s));}
    void connect(){final String t=token.getText().toString().trim(); if(t.isEmpty()){Toast.makeText(this,"Enter an access token for test connection",Toast.LENGTH_SHORT).show();return;} new Thread(()->{try{String r=api.user(t).toString();runOnUiThread(()->log.setText("Groww connected. User endpoint responded successfully.\n"+r));}catch(Exception e){runOnUiThread(()->log.setText("Connect failed: "+e.getMessage()));}}).start();}
    void analyze(){final String sym=symbol.getText().toString().trim().toUpperCase(Locale.ROOT);final String t=token.getText().toString().trim();if(sym.isEmpty()||t.isEmpty()){Toast.makeText(this,"Enter symbol + access token",Toast.LENGTH_SHORT).show();return;}log.setText("Fetching 5-minute candles for "+sym+"…");new Thread(()->{try{long end=System.currentTimeMillis()/1000L,start=end-3*24*3600;List<Candle> c=api.candles(t,sym,start,end,5);double px=api.ltp(t,sym);Signal sig=engine.evaluate(c);String act=new TradeSimulator().apply(trade,sig,px);StringBuilder b=new StringBuilder();b.append("Symbol: ").append(sym).append("\nLTP: ₹").append(String.format(Locale.US,"%.2f",px)).append("\nSignal: ").append(sig.side).append(" | score ").append(String.format(Locale.US,"%.2f",sig.score)).append("\nAction: ").append(act).append("\n\nStrategies / candle evidence:\n");for(String r:sig.reasons)b.append("• ").append(r).append("\n");b.append("\nChampion logic: weighted consensus across EMA, RSI, VWAP, MACD, volume expansion, candlestick patterns, persistence and breakout/breakdown. Anti-churn gate requires stronger, persistent evidence before any reversal.");runOnUiThread(()->{log.setText(b.toString());pnl.setText("Net Shadow P&L: ₹"+String.format(Locale.US,"%.2f",trade.pnl())+"  •  Cost reserve: ₹"+String.format(Locale.US,"%.2f",trade.estimatedCosts));});}catch(Exception e){runOnUiThread(()->log.setText("Analysis failed: "+e.getMessage()));}}).start();}
}
