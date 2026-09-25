package com.paisalaya.app;

import android.app.*;
import android.content.*;
import android.content.res.Configuration;
import android.graphics.*;
import android.graphics.drawable.GradientDrawable;
import android.os.Bundle;
import android.view.*;
import android.view.inputmethod.InputMethodManager;
import android.provider.ContactsContract;
import android.media.AudioManager;
import android.media.ToneGenerator;
import android.os.Build;
import android.hardware.biometrics.BiometricPrompt;
import android.security.keystore.KeyProperties;
import android.view.Window;
import android.widget.*;
import org.json.*;
import java.io.*;
import java.text.SimpleDateFormat;
import java.util.*;

public class MainActivity extends Activity {
    static final String PREF="paisa_laya", TX="transactions";
    static final String SCREEN_HOME="home", SCREEN_ADD="add", SCREEN_PEOPLE="people", SCREEN_TOOLS="tools", SCREEN_REPORTS="reports", SCREEN_SETTINGS="settings";

    LinearLayout root, content;
    SharedPreferences prefs;
    String currentScreen=SCREEN_HOME;
    String pendingType="Expense";
    final ArrayDeque<String> screenHistory=new ArrayDeque<>();
    boolean renderingScreen=false;
    boolean unlockedThisLaunch=false;

    int BG=Color.rgb(246,248,244), INK=Color.rgb(25,35,29), GREEN=Color.rgb(36,132,83);
    int GREEN_DARK=Color.rgb(18,92,57), MINT=Color.rgb(224,246,232), RED=Color.rgb(216,76,76);
    int GOLD=Color.rgb(238,174,65), MUTED=Color.rgb(92,105,96), WHITE=Color.WHITE;

    int dp(float v){return (int)(v*getResources().getDisplayMetrics().density+0.5f);}

    @Override public void onCreate(Bundle state){
        super.onCreate(state);
        prefs=getSharedPreferences(PREF,0);
        applyPreferencesTheme();
        getWindow().setStatusBarColor(GREEN_DARK);
        getWindow().setNavigationBarColor(BG);
        getWindow().getDecorView().setSystemUiVisibility(isDarkMode()?0:View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR);
        if(state!=null){
            currentScreen=state.getString("screen",SCREEN_HOME);
            pendingType=state.getString("type","Expense");
        }
        showWelcomeScreen(state);
    }

    void showWelcomeScreen(Bundle state){
        LinearLayout welcome=new LinearLayout(this);
        welcome.setOrientation(LinearLayout.VERTICAL);
        welcome.setGravity(Gravity.CENTER);
        welcome.setBackgroundColor(BG);
        welcome.setPadding(dp(30),dp(30),dp(30),dp(30));

        TextView mark=tv("₨",52,WHITE,true);
        mark.setGravity(Gravity.CENTER);
        mark.setBackground(bg(GREEN,40));
        welcome.addView(mark,new LinearLayout.LayoutParams(dp(94),dp(94)));

        TextView title=tv("Paisa Laya",34,INK,true);
        title.setGravity(Gravity.CENTER);
        LinearLayout.LayoutParams tp=new LinearLayout.LayoutParams(-1,-2);
        tp.setMargins(0,dp(22),0,dp(2)); welcome.addView(title,tp);

        TextView sub=tv("Your money, beautifully organized.",15,MUTED,false);
        sub.setGravity(Gravity.CENTER); welcome.addView(sub);
        setContentView(welcome);

        mark.setScaleX(.65f); mark.setScaleY(.65f); mark.setAlpha(.15f);
        title.setAlpha(0f); sub.setAlpha(0f);
        mark.animate().scaleX(1f).scaleY(1f).alpha(1f).setDuration(520).start();
        title.animate().alpha(1f).setStartDelay(260).setDuration(420).start();
        sub.animate().alpha(1f).setStartDelay(420).setDuration(420).start();

        welcome.postDelayed(()->{
            if(state==null && isLockEnabled() && !unlockedThisLaunch) showLockScreen();
            else renderCurrent();
            if(state!=null && SCREEN_ADD.equals(currentScreen)){
                final String amount=state.getString("amount","");
                final String category=state.getString("category","");
                final String note=state.getString("note","");
                content.postDelayed(()->restoreAddFields(amount,category,note),80);
            }
        },900);
    }

    @Override protected void onSaveInstanceState(Bundle out){
        out.putString("screen",currentScreen);
        out.putString("type",pendingType);
        if(SCREEN_ADD.equals(currentScreen)){
            View v=content.findViewWithTag("amount");
            if(v instanceof EditText) out.putString("amount",((EditText)v).getText().toString());
            v=content.findViewWithTag("category");
            if(v instanceof EditText) out.putString("category",((EditText)v).getText().toString());
            v=content.findViewWithTag("note");
            if(v instanceof EditText) out.putString("note",((EditText)v).getText().toString());
        }
        super.onSaveInstanceState(out);
    }

    boolean isLockEnabled(){ return prefs.getBoolean("app_lock",false) && !prefs.getString("lock_pin_hash","").isEmpty(); }

    String hashPin(String pin){
        try{
            java.security.MessageDigest md=java.security.MessageDigest.getInstance("SHA-256");
            byte[] b=md.digest(pin.getBytes("UTF-8")); StringBuilder s=new StringBuilder();
            for(byte x:b)s.append(String.format(Locale.US,"%02x",x)); return s.toString();
        }catch(Exception e){return "";}
    }

    boolean verifyPin(String pin){ return hashPin(pin).equals(prefs.getString("lock_pin_hash","")); }

    void setupPin(boolean enabling){
        final EditText p1=new EditText(this); fieldStyle(p1,"Enter 4–8 digit PIN",17); p1.setInputType(2|16);
        final EditText p2=new EditText(this); fieldStyle(p2,"Confirm PIN",17); p2.setInputType(2|16);
        LinearLayout box=new LinearLayout(this); box.setOrientation(LinearLayout.VERTICAL); box.setPadding(dp(4),dp(4),dp(4),0); box.addView(p1); box.addView(p2,new LinearLayout.LayoutParams(-1,dp(56)));
        dialogBuilder().setTitle(enabling?"Set app lock PIN":"Change app lock PIN").setView(box)
            .setNegativeButton("Cancel",null).setPositiveButton("Save",null).create();
        final AlertDialog d=dialogBuilder().setTitle(enabling?"Set app lock PIN":"Change app lock PIN").setView(box).setNegativeButton("Cancel",null).setPositiveButton("Save",null).create();
        d.setOnShowListener(x->d.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(v->{
            String a=p1.getText().toString().trim(), b=p2.getText().toString().trim();
            if(!a.matches("\\d{4,8}") || !a.equals(b)){ Toast.makeText(this,"Enter matching 4–8 digit PINs.",Toast.LENGTH_SHORT).show(); return; }
            prefs.edit().putBoolean("app_lock",true).putString("lock_pin_hash",hashPin(a)).apply();
            feedback("App lock enabled",ToneGenerator.TONE_PROP_ACK); d.dismiss(); renderCurrent();
        })); d.show();
    }

    void showLockScreen(){
        LinearLayout lock=new LinearLayout(this); lock.setOrientation(LinearLayout.VERTICAL); lock.setGravity(Gravity.CENTER); lock.setPadding(dp(28),dp(28),dp(28),dp(28)); lock.setBackgroundColor(BG);
        TextView mark=tv("₨",42,WHITE,true); mark.setGravity(Gravity.CENTER); mark.setBackground(bg(GREEN,34)); lock.addView(mark,new LinearLayout.LayoutParams(dp(78),dp(78)));
        TextView title=tv("Paisa Laya is locked",25,INK,true); title.setGravity(Gravity.CENTER); lock.addView(title,new LinearLayout.LayoutParams(-1,-2));
        TextView sub=tv("Enter your PIN to continue.",14,MUTED,false); sub.setGravity(Gravity.CENTER); lock.addView(sub);
        EditText pin=new EditText(this); fieldStyle(pin,"PIN",20); pin.setInputType(2|16); pin.setGravity(Gravity.CENTER); lock.addView(pin,new LinearLayout.LayoutParams(-1,dp(56)));
        Button unlock=action("Unlock"); unlock.setTextColor(WHITE); unlock.setBackground(bg(GREEN,22)); lock.addView(unlock,new LinearLayout.LayoutParams(-1,dp(52)));
        Button biometric=action("Use biometric / device security"); biometric.setTextColor(GREEN); biometric.setBackground(strokeBg(WHITE,GREEN,22));
        if(Build.VERSION.SDK_INT>=28){ lock.addView(biometric,new LinearLayout.LayoutParams(-1,dp(52))); biometric.setOnClickListener(v->authenticateBiometric()); } else biometric.setVisibility(View.GONE);
        TextView error=tv("",13,RED,false); error.setGravity(Gravity.CENTER); lock.addView(error);
        setContentView(lock);
        unlock.setOnClickListener(v->{ if(verifyPin(pin.getText().toString())){ unlockedThisLaunch=true; feedback("Unlocked",ToneGenerator.TONE_PROP_ACK); renderCurrent(); } else error.setText("Incorrect PIN. Please try again."); });
        pin.requestFocus();
    }

    void authenticateBiometric(){
        if(Build.VERSION.SDK_INT<28)return;
        try{
            BiometricPrompt prompt=new BiometricPrompt.Builder(this).setTitle("Unlock Paisa Laya").setSubtitle("Use your biometric or device screen lock").setDescription("Your financial data stays protected on this device.").setNegativeButton("Use PIN",getMainExecutor(),(d,w)->{}).build();
            prompt.authenticate(getMainExecutor(),new BiometricPrompt.AuthenticationCallback(){
                @Override public void onAuthenticationSucceeded(BiometricPrompt.AuthenticationResult result){ runOnUiThread(()->{unlockedThisLaunch=true; feedback("Unlocked",ToneGenerator.TONE_PROP_ACK); renderCurrent();}); }
                @Override public void onAuthenticationError(int code,CharSequence msg){ }
                @Override public void onAuthenticationFailed(){ Toast.makeText(MainActivity.this,"Biometric not recognized.",Toast.LENGTH_SHORT).show(); }
            });
        }catch(Exception e){ Toast.makeText(this,"Biometric security is not available. Use your PIN.",Toast.LENGTH_SHORT).show(); }
    }

    void renderCurrent(){
        renderingScreen=true;
        if(SCREEN_ADD.equals(currentScreen)) showAddWithType(pendingType);
        else if(SCREEN_PEOPLE.equals(currentScreen)) showPeople();
        else if(SCREEN_TOOLS.equals(currentScreen)) showTools();
        else if(SCREEN_SETTINGS.equals(currentScreen)) showSettings();
        else if(SCREEN_REPORTS.equals(currentScreen)) showReports();
        else showHome();
        renderingScreen=false;
    }

    void recordNavigation(String target){
        if(!target.equals(currentScreen) && !renderingScreen) screenHistory.push(currentScreen);
        currentScreen=target;
    }

    boolean isDarkMode(){
        String theme=prefs.getString("theme","System");
        if(theme.equals("Dark")) return true;
        if(theme.equals("Light")) return false;
        return (getResources().getConfiguration().uiMode&Configuration.UI_MODE_NIGHT_MASK)==Configuration.UI_MODE_NIGHT_YES;
    }

    ArrayAdapter<String> spinnerAdapter(String[] values){
        return new ArrayAdapter<String>(this,android.R.layout.simple_spinner_item,values){
            TextView style(TextView v){
                v.setTextColor(INK); v.setTextSize(15); v.setGravity(Gravity.CENTER_VERTICAL);
                v.setPadding(dp(12),0,dp(12),0); v.setBackgroundColor(WHITE); return v;
            }
            @Override public View getView(int position,View convertView,android.view.ViewGroup parent){
                TextView v=(TextView)super.getView(position,convertView,parent); return style(v);
            }
            @Override public View getDropDownView(int position,View convertView,android.view.ViewGroup parent){
                TextView v=(TextView)super.getDropDownView(position,convertView,parent); return style(v);
            }
        };
    }

    void spinnerStyle(Spinner s){
        s.setPopupBackgroundDrawable(bg(WHITE,18));
        s.setBackground(bg(WHITE,20));
        s.setPadding(dp(12),0,dp(8),0);
    }

    @Override public void onBackPressed(){
        if(isKeyboardVisible()){
            ((InputMethodManager)getSystemService(INPUT_METHOD_SERVICE)).hideSoftInputFromWindow(getWindow().getDecorView().getWindowToken(),0);
            View focused=getCurrentFocus(); if(focused!=null) focused.clearFocus();
            return;
        }
        if(!screenHistory.isEmpty()){
            currentScreen=screenHistory.pop();
            renderCurrent();
            return;
        }
        new AlertDialog.Builder(this,isDarkMode()?AlertDialog.THEME_DEVICE_DEFAULT_DARK:AlertDialog.THEME_DEVICE_DEFAULT_LIGHT)
            .setTitle("Exit Paisa Laya?")
            .setMessage("Are you sure you want to close the app?")
            .setNegativeButton("Stay",null)
            .setPositiveButton("Exit",(d,w)->finish())
            .show();
    }

    boolean isKeyboardVisible(){
        View decor=getWindow().getDecorView();
        Rect r=new Rect(); decor.getWindowVisibleDisplayFrame(r);
        return decor.getHeight()-r.bottom>dp(180);
    }

    @Override public void onConfigurationChanged(Configuration c){
        super.onConfigurationChanged(c);
        getWindow().setStatusBarColor(GREEN_DARK);
        renderCurrent();
    }

    TextView tv(String s,float z,int c,boolean bold){
        TextView t=new TextView(this);
        t.setText(s); t.setTextSize(z); t.setTextColor(c);
        t.setIncludeFontPadding(true);
        t.setPadding(dp(2),dp(3),dp(2),dp(3));
        if(bold)t.setTypeface(Typeface.DEFAULT,Typeface.BOLD);
        return t;
    }

    GradientDrawable bg(int color,float radius){
        GradientDrawable g=new GradientDrawable();
        g.setColor(color); g.setCornerRadius(dp(radius)); return g;
    }

    GradientDrawable strokeBg(int color,int stroke,float radius){
        GradientDrawable g=bg(color,radius); g.setStroke(dp(1),stroke); return g;
    }

    LinearLayout box(int color,int pad){
        LinearLayout l=new LinearLayout(this);
        l.setOrientation(LinearLayout.VERTICAL);
        l.setPadding(dp(pad),dp(pad),dp(pad),dp(pad));
        l.setBackground(bg(color,26));
        return l;
    }

    LinearLayout row(){
        LinearLayout l=new LinearLayout(this);
        l.setOrientation(LinearLayout.HORIZONTAL);
        l.setGravity(Gravity.CENTER_VERTICAL);
        return l;
    }

    Button action(String s){
        Button b=new Button(this);
        b.setText(s); b.setTextSize(14); b.setAllCaps(false); b.setTextColor(INK);
        b.setBackground(bg(WHITE,22)); b.setPadding(dp(10),0,dp(10),0);
        b.setMinHeight(dp(48)); b.setMinWidth(0); b.setStateListAnimator(null);
        return b;
    }

    void fieldStyle(EditText e,String hint,float size){
        e.setHint(hint); e.setTextSize(size); e.setSingleLine(true); e.setTextColor(INK); e.setHintTextColor(MUTED);
        e.setPadding(dp(18),0,dp(18),0); e.setBackground(bg(WHITE,20));
        e.setGravity(Gravity.CENTER_VERTICAL);
        e.setMinHeight(dp(56));
    }

    TextView sectionTitle(String text){
        TextView t=tv(text,19,INK,true);
        t.setPadding(dp(2),dp(12),dp(2),dp(8));
        return t;
    }

    void gap(int h){content.addView(new Space(this),new LinearLayout.LayoutParams(1,dp(h)));}

    void addWrap(View v){
        LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(-1,-2);
        content.addView(v,p);
    }

    void addWrapMargin(View v,int top,int bottom){
        LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(-1,-2);
        p.setMargins(0,dp(top),0,dp(bottom)); content.addView(v,p);
    }

    void base(String title,String subtitle){
        root=new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(BG);

        LinearLayout head=new LinearLayout(this);
        head.setOrientation(LinearLayout.VERTICAL);
        int top=getResources().getConfiguration().orientation==Configuration.ORIENTATION_LANDSCAPE?10:18;
        head.setPadding(dp(18),dp(top),dp(18),dp(4));
        TextView titleView=tv(title,28,INK,true);
        TextView subView=tv(subtitle,15,MUTED,false);
        head.addView(titleView,new LinearLayout.LayoutParams(-1,-2));
        head.addView(subView,new LinearLayout.LayoutParams(-1,-2));
        root.addView(head,new LinearLayout.LayoutParams(-1,-2));

        content=new LinearLayout(this);
        content.setOrientation(LinearLayout.VERTICAL);
        content.setPadding(dp(16),dp(4),dp(16),dp(20));

        ScrollView sv=new ScrollView(this);
        sv.setFillViewport(true);
        sv.setClipToPadding(false);
        sv.addView(content);
        root.addView(sv,new LinearLayout.LayoutParams(-1,0,1));
        setContentView(root);

        content.setAlpha(0f);
        content.animate().alpha(1f).setDuration(260).start();
    }

    void nav(){
        LinearLayout n=new LinearLayout(this);
        n.setOrientation(LinearLayout.HORIZONTAL);
        n.setGravity(Gravity.CENTER);
        n.setPadding(dp(6),dp(5),dp(6),dp(7));
        n.setBackground(bg(WHITE,28));

        String[] icons={"⌂","+","♙","↔","⚙"};
        String[] labels={"Home","Add","People","Tools","Settings"};
        TextView[] items=new TextView[5];

        for(int i=0;i<5;i++){
            TextView item=new TextView(this);
            item.setText(icons[i]+"\n"+labels[i]);
            item.setTextSize(12);
            item.setTextColor(i==screenIndex()?GREEN:INK);
            item.setGravity(Gravity.CENTER);
            item.setIncludeFontPadding(true);
            item.setLineSpacing(0,0.92f);
            item.setBackground(i==screenIndex()?bg(MINT,20):bg(WHITE,20));
            item.setPadding(0,dp(4),0,dp(4));
            items[i]=item;
            LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(0,dp(62),1);
            if(i>0)p.setMargins(dp(4),0,0,0);
            n.addView(item,p);
        }

        items[0].setOnClickListener(v->showHome());
        items[1].setOnClickListener(v->showAdd());
        items[2].setOnClickListener(v->showPeople());
        items[3].setOnClickListener(v->showTools());
        items[4].setOnClickListener(v->showSettings());
        root.addView(n,new LinearLayout.LayoutParams(-1,dp(72)));
    }

    int screenIndex(){
        if(SCREEN_ADD.equals(currentScreen))return 1;
        if(SCREEN_PEOPLE.equals(currentScreen))return 2;
        if(SCREEN_TOOLS.equals(currentScreen))return 3;
        if(SCREEN_SETTINGS.equals(currentScreen))return 4;
        return 0;
    }

    JSONArray transactions(){
        try{return new JSONArray(prefs.getString(TX,"[]"));}catch(Exception e){return new JSONArray();}
    }

    void save(JSONArray a){prefs.edit().putString(TX,a.toString()).apply();}

    double[] totals(){
        double in=0,out=0; JSONArray a=transactions();
        for(int i=0;i<a.length();i++)try{
            JSONObject o=a.getJSONObject(i); double x=o.getDouble("amount");
            if("Income".equals(o.getString("type")))in+=x; else out+=x;
        }catch(Exception e){}
        return new double[]{in,out};
    }

    String money(double x){return String.format(Locale.US,"PKR %,.0f",x);}

    void feedback(String message,int tone){
        Toast.makeText(this,"✓  "+message,Toast.LENGTH_SHORT).show();
        try{
            ToneGenerator tg=new ToneGenerator(AudioManager.STREAM_NOTIFICATION,75);
            tg.startTone(tone,120);
            new android.os.Handler().postDelayed(tg::release,180);
        }catch(Exception ignored){}
    }

    AlertDialog.Builder dialogBuilder(){
        return new AlertDialog.Builder(this,isDarkMode()?AlertDialog.THEME_DEVICE_DEFAULT_DARK:AlertDialog.THEME_DEVICE_DEFAULT_LIGHT);
    }

    void chooseContact(TextView selected,EditText hiddenPhone,EditText nameField){
        try{
            selected.setTag(new Object[]{hiddenPhone,nameField});
            Intent pick=new Intent(Intent.ACTION_PICK,ContactsContract.CommonDataKinds.Phone.CONTENT_URI);
            startActivityForResult(pick,21);
        }catch(Exception e){Toast.makeText(this,"Contacts could not be opened.",Toast.LENGTH_SHORT).show();}
    }

    void showHome(){
        recordNavigation(SCREEN_HOME);
        currentScreen=SCREEN_HOME;
        base("Paisa Laya","Your money, beautifully organized.");
        double[] t=totals(); double balance=t[0]-t[1];

        LinearLayout hero=box(GREEN,20);
        hero.addView(tv("TOTAL BALANCE",12,Color.rgb(207,240,218),true));
        TextView bal=tv(money(balance),32,WHITE,true);
        hero.addView(bal,new LinearLayout.LayoutParams(-1,-2));

        LinearLayout row=row();
        LinearLayout inc=box(Color.rgb(53,151,99),13);
        inc.addView(tv("↗  INCOME",11,Color.rgb(210,244,222),true));
        inc.addView(tv(money(t[0]),17,WHITE,true));
        LinearLayout exp=box(Color.rgb(194,70,70),13);
        exp.addView(tv("↘  EXPENSE",11,Color.rgb(255,220,220),true));
        exp.addView(tv(money(t[1]),17,WHITE,true));
        row.addView(inc,new LinearLayout.LayoutParams(0,-2,1));
        LinearLayout.LayoutParams ep=new LinearLayout.LayoutParams(0,-2,1);
        ep.setMargins(dp(10),0,0,0); row.addView(exp,ep);
        hero.addView(row);
        addWrapMargin(hero,0,10);

        LinearLayout quick=row();
        Button add=action("＋  Add expense"), income=action("＋  Add income");
        quick.addView(add,new LinearLayout.LayoutParams(0,dp(50),1));
        LinearLayout.LayoutParams ip=new LinearLayout.LayoutParams(0,dp(50),1);
        ip.setMargins(dp(10),0,0,0); quick.addView(income,ip);
        add.setOnClickListener(v->showAddWithType("Expense"));
        income.setOnClickListener(v->showAddWithType("Income"));
        addWrapMargin(quick,0,2);

        addWrap(sectionTitle("Spending overview"));
        LinearLayout chart=box(WHITE,17);
        double total=t[0]+t[1]; float er=total==0?0:(float)(t[1]/total);
        LinearLayout chartTop=row();
        chartTop.addView(tv("Expenses",13,INK,false),new LinearLayout.LayoutParams(0,-2,1));
        chartTop.addView(tv(String.format(Locale.US,"%.0f%%",er*100),13,RED,true),new LinearLayout.LayoutParams(-2,-2));
        chart.addView(chartTop);
        ProgressBar pb=new ProgressBar(this,null,android.R.attr.progressBarStyleHorizontal);
        pb.setMax(100); pb.setProgress((int)(er*100)); pb.setProgressDrawable(bg(RED,20));
        LinearLayout.LayoutParams pp=new LinearLayout.LayoutParams(-1,dp(14)); pp.setMargins(0,dp(8),0,dp(8)); chart.addView(pb,pp);
        chart.addView(tv(total==0?"No transactions yet — your spending bar will appear here.":"Expenses compared with your recorded cash flow.",12,MUTED,false));
        addWrapMargin(chart,0,4);

        addWrap(sectionTitle("Recent transactions"));
        JSONArray a=transactions();
        int start=Math.max(0,a.length()-5);
        if(a.length()==0){
            LinearLayout empty=box(WHITE,18);
            TextView icon=tv("＋",28,GREEN,true); icon.setGravity(Gravity.CENTER);
            empty.addView(icon,new LinearLayout.LayoutParams(-1,dp(40)));
            TextView eTitle=tv("Start tracking your money",17,INK,true); eTitle.setGravity(Gravity.CENTER);
            empty.addView(eTitle);
            TextView eText=tv("Add your first income or expense and Paisa Laya will build your dashboard automatically.",13,MUTED,false);
            eText.setGravity(Gravity.CENTER); eText.setGravity(Gravity.CENTER_HORIZONTAL);
            empty.addView(eText);
            Button first=action("Add my first transaction");
            first.setTextColor(WHITE); first.setBackground(bg(GREEN,22)); first.setOnClickListener(v->showAdd());
            LinearLayout.LayoutParams fp=new LinearLayout.LayoutParams(-1,dp(50)); fp.setMargins(0,dp(12),0,0); empty.addView(first,fp);
            addWrapMargin(empty,0,8);

            LinearLayout tips=row();
            tips.addView(tipCard("1","Record","Income & expenses"),new LinearLayout.LayoutParams(0,-2,1));
            LinearLayout.LayoutParams tp=new LinearLayout.LayoutParams(0,-2,1); tp.setMargins(dp(8),0,0,0);
            tips.addView(tipCard("2","Review","Your spending"),tp);
            addWrap(tips);
        } else {
            for(int i=a.length()-1;i>=start;i--)try{
                JSONObject o=a.getJSONObject(i);
                LinearLayout card=box(WHITE,13);
                LinearLayout rr=row();
                String icon="Income".equals(o.getString("type"))?"↗":"↘";
                int c="Income".equals(o.getString("type"))?GREEN:RED;
                TextView ico=tv(icon,22,c,true); ico.setGravity(Gravity.CENTER);
                rr.addView(ico,new LinearLayout.LayoutParams(dp(42),dp(62)));
                LinearLayout info=new LinearLayout(this); info.setOrientation(LinearLayout.VERTICAL);
                info.addView(tv(o.optString("category","Other"),15,INK,true));
                info.addView(tv(o.optString("note","No note")+"  •  "+o.optString("date",""),12,MUTED,false));
                rr.addView(info,new LinearLayout.LayoutParams(0,-2,1));
                rr.addView(tv(money(o.optDouble("amount")),14,c,true),new LinearLayout.LayoutParams(-2,-2));
                card.addView(rr); addWrapMargin(card,0,7);
            }catch(Exception e){}
        }

        if(a.length()>0){
            LinearLayout insight=box(MINT,16);
            insight.addView(tv("Quick insight",13,GREEN,true));
            String msg;
            if(t[0]==0) msg="You have recorded expenses but no income yet.";
            else if(t[1]==0) msg="No expenses recorded yet. Nice and simple.";
            else if(balance<0) msg="Recorded expenses are currently higher than recorded income.";
            else msg="You are currently keeping a positive recorded balance.";
            insight.addView(tv(msg,13,INK,false));
            addWrapMargin(insight,2,8);
        }

        nav();
    }

    LinearLayout tipCard(String number,String title,String text){
        LinearLayout c=box(WHITE,12);
        TextView n=tv(number,16,GREEN,true); n.setGravity(Gravity.CENTER);
        n.setBackground(bg(MINT,18)); c.addView(n,new LinearLayout.LayoutParams(dp(34),dp(34)));
        c.addView(tv(title,13,INK,true));
        c.addView(tv(text,11,MUTED,false));
        return c;
    }

    void showAdd(){showAddWithType("Expense");}

    void showAddWithType(String defaultType){
        recordNavigation(SCREEN_ADD);
        currentScreen=SCREEN_ADD; pendingType=defaultType;
        base("New transaction","Record money in seconds.");
        TextView amountLabel=tv("Amount",13,INK,true); addWrapMargin(amountLabel,0,5);
        EditText amount=new EditText(this); fieldStyle(amount,"Amount in PKR",18); amount.setInputType(2|8192); amount.setTag("amount"); addWrapMargin(amount,0,10);

        TextView typeLabel=tv("Transaction type",13,INK,true); addWrapMargin(typeLabel,0,5);
        Spinner type=new Spinner(this); spinnerStyle(type);
        type.setAdapter(spinnerAdapter(new String[]{"Expense","Income"}));
        type.setSelection("Income".equals(defaultType)?1:0); addWrapMargin(type,0,10);

        TextView catLabel=tv("Category",13,INK,true); addWrapMargin(catLabel,0,5);
        EditText cat=new EditText(this); fieldStyle(cat,"Food, Salary, Bills...",17); cat.setTag("category"); addWrapMargin(cat,0,10);

        TextView noteLabel=tv("Note (optional)",13,INK,true); addWrapMargin(noteLabel,0,5);
        EditText note=new EditText(this); fieldStyle(note,"Add a short note",17); note.setTag("note"); addWrapMargin(note,0,14);

        Button saveB=action("Save transaction  →");
        saveB.setTextSize(16); saveB.setTextColor(WHITE); saveB.setBackground(bg(GREEN,24));
        addWrapMargin(saveB,0,10);
        saveB.setOnClickListener(v->{
            try{
                double x=Double.parseDouble(amount.getText().toString().trim());
                if(x<=0)throw new Exception();
                JSONArray a=transactions(); JSONObject o=new JSONObject();
                o.put("amount",x); o.put("type",type.getSelectedItem().toString());
                o.put("category",cat.getText().toString().trim().isEmpty()?"Other":cat.getText().toString().trim());
                o.put("note",note.getText().toString().trim());
                o.put("date",new SimpleDateFormat("dd MMM, HH:mm",Locale.US).format(new Date()));
                a.put(o); save(a);
                feedback("Transaction saved",ToneGenerator.TONE_PROP_ACK);
                ((InputMethodManager)getSystemService(INPUT_METHOD_SERVICE)).hideSoftInputFromWindow(amount.getWindowToken(),0);
                showHome();
            }catch(Exception e){Toast.makeText(this,"Please enter a valid amount.",Toast.LENGTH_SHORT).show();}
        });

        nav();
    }

    void restoreAddFields(String amount,String category,String note){
        View v=content.findViewWithTag("amount"); if(v instanceof EditText)((EditText)v).setText(amount);
        v=content.findViewWithTag("category"); if(v instanceof EditText)((EditText)v).setText(category);
        v=content.findViewWithTag("note"); if(v instanceof EditText)((EditText)v).setText(note);
    }


    void showPeople(){
        recordNavigation(SCREEN_PEOPLE);
        currentScreen=SCREEN_PEOPLE;
        base("People & Dues","Keep track of borrowed and owed money.");

        addWrapMargin(tv("Add someone you owe or who owes you.",13,MUTED,false),0,10);
        EditText name=new EditText(this); fieldStyle(name,"Person's name",17); addWrapMargin(name,0,10);
        EditText amount=new EditText(this); fieldStyle(amount,"Amount in PKR",17); amount.setInputType(2|8192); addWrapMargin(amount,0,10);

        Spinner kind=new Spinner(this); spinnerStyle(kind);
        kind.setAdapter(spinnerAdapter(new String[]{"They owe me","I owe them"})); addWrapMargin(kind,0,10);

        TextView contact=tv("No contact selected",14,MUTED,false);
        Button choose=action("Choose from contacts");
        choose.setTextColor(WHITE); choose.setBackground(bg(GREEN,22));
        LinearLayout contactRow=row();
        contactRow.addView(contact,new LinearLayout.LayoutParams(0,dp(50),1));
        LinearLayout.LayoutParams cp=new LinearLayout.LayoutParams(dp(175),dp(50)); cp.setMargins(dp(8),0,0,0);
        contactRow.addView(choose,cp); addWrapMargin(contactRow,0,10);

        EditText hiddenPhone=new EditText(this); hiddenPhone.setVisibility(View.GONE);
        addWrap(hiddenPhone);
        choose.setOnClickListener(v->chooseContact(contact,hiddenPhone,name));

        EditText note=new EditText(this); fieldStyle(note,"Note (optional)",17); addWrapMargin(note,0,12);
        Button add=action("＋  Add person");
        add.setTextColor(WHITE); add.setTextSize(16); add.setBackground(bg(GREEN,24));
        addWrapMargin(add,0,16);

        addWrap(sectionTitle("Saved people"));
        LinearLayout listBox=box(WHITE,14); addWrapMargin(listBox,0,8);
        JSONArray people=new JSONArray();
        try{people=new JSONArray(prefs.getString("dues_json","[]"));}catch(Exception ignored){}
        if(people.length()==0) listBox.addView(tv("No people added yet.",13,MUTED,false));
        for(int i=0;i<people.length();i++) addPersonCard(listBox,people.optJSONObject(i),i);

        add.setOnClickListener(v->{
            String n=name.getText().toString().trim(), am=amount.getText().toString().trim();
            if(n.isEmpty()||am.isEmpty()){Toast.makeText(this,"Enter a name and amount.",Toast.LENGTH_SHORT).show();return;}
            try{
                double value=Double.parseDouble(am); if(value<=0)throw new Exception();
                JSONArray a; try{a=new JSONArray(prefs.getString("dues_json","[]"));}catch(Exception e){a=new JSONArray();}
                JSONObject o=new JSONObject();
                o.put("name",n); o.put("amount",value); o.put("kind",kind.getSelectedItem().toString());
                o.put("phone",hiddenPhone.getText().toString().trim()); o.put("note",note.getText().toString().trim());
                o.put("settled",false); a.put(o);
                prefs.edit().putString("dues_json",a.toString()).apply();
                feedback("Person added",ToneGenerator.TONE_PROP_ACK);
                showPeople();
            }catch(Exception e){Toast.makeText(this,"Please enter a valid amount.",Toast.LENGTH_SHORT).show();}
        });
        nav();
    }

    void addPersonCard(LinearLayout parent,JSONObject o,int index){
        if(o==null)return;
        boolean settled=o.optBoolean("settled",false);
        LinearLayout card=box(settled?WHITE:MINT,12);
        LinearLayout top=row();
        LinearLayout info=new LinearLayout(this); info.setOrientation(LinearLayout.VERTICAL);
        String kind=o.optString("kind","They owe me");
        int col=kind.startsWith("They")?GREEN:RED;
        info.addView(tv(o.optString("name","Person"),16,INK,true));
        String status=settled?"  •  SETTLED":"";
        info.addView(tv(kind+"  •  "+money(o.optDouble("amount"))+status+(o.optString("note").isEmpty()?"":"  •  "+o.optString("note")),12,MUTED,false));
        top.addView(info,new LinearLayout.LayoutParams(0,-2,1));

        Button mark=action(settled?"Settled":"Mark");
        mark.setTextSize(12); mark.setTextColor(settled?MUTED:col);
        top.addView(mark,new LinearLayout.LayoutParams(dp(72),dp(44)));
        Button del=action("Delete"); del.setTextSize(12); del.setTextColor(RED);
        LinearLayout.LayoutParams delp=new LinearLayout.LayoutParams(dp(72),dp(44)); delp.setMargins(dp(6),0,0,0); top.addView(del,delp);
        card.addView(top);

        if(!settled){
            Button wa=action("Prepare WhatsApp reminder");
            wa.setTextColor(GREEN); wa.setBackground(bg(WHITE,20));
            LinearLayout.LayoutParams wp=new LinearLayout.LayoutParams(-1,dp(44)); wp.setMargins(0,dp(9),0,0);
            card.addView(wa,wp);
            wa.setOnClickListener(v->whatsappReminder(o));

            Button settle=action(kind.startsWith("They")?"Received amount  ✓":"Returned amount  ✓");
            settle.setTextColor(WHITE); settle.setBackground(bg(kind.startsWith("They")?GREEN:RED,20));
            LinearLayout.LayoutParams sp=new LinearLayout.LayoutParams(-1,dp(46)); sp.setMargins(0,dp(9),0,0);
            card.addView(settle,sp);
            settle.setOnClickListener(v->settlePerson(index));
        }
        parent.addView(card,new LinearLayout.LayoutParams(-1,-2));
        mark.setOnClickListener(v->togglePerson(index));
        del.setOnClickListener(v->confirmDeletePerson(index));
    }

    void updatePeople(JSONArray people){prefs.edit().putString("dues_json",people.toString()).apply();}

    void togglePerson(int index){
        try{
            JSONArray a=new JSONArray(prefs.getString("dues_json","[]"));
            JSONObject o=a.getJSONObject(index); o.put("settled",!o.optBoolean("settled",false));
            updatePeople(a); feedback(o.optBoolean("settled")?"Marked settled":"Marked active",ToneGenerator.TONE_PROP_ACK); showPeople();
        }catch(Exception e){Toast.makeText(this,"Could not update this person.",Toast.LENGTH_SHORT).show();}
    }

    void settlePerson(int index){
        try{
            JSONArray a=new JSONArray(prefs.getString("dues_json","[]"));
            JSONObject o=a.getJSONObject(index); o.put("settled",true);
            updatePeople(a);
            boolean received=o.optString("kind","").startsWith("They");
            feedback(received?"Amount received":"Amount returned",received?ToneGenerator.TONE_PROP_ACK:ToneGenerator.TONE_PROP_BEEP);
            showPeople();
        }catch(Exception e){Toast.makeText(this,"Could not update this person.",Toast.LENGTH_SHORT).show();}
    }

    void confirmDeletePerson(int index){
        dialogBuilder().setTitle("Delete person?")
            .setMessage("This will remove the saved person and their due from Paisa Laya.")
            .setNegativeButton("Cancel",null)
            .setPositiveButton("Delete",(d,w)->{
                try{
                    JSONArray a=new JSONArray(prefs.getString("dues_json","[]"));
                    if(index>=0&&index<a.length())a.remove(index);
                    updatePeople(a); feedback("Person deleted",ToneGenerator.TONE_PROP_NACK); showPeople();
                }catch(Exception e){Toast.makeText(this,"Could not delete this person.",Toast.LENGTH_SHORT).show();}
            }).show();
    }

    void whatsappReminder(JSONObject o){
        String name=o.optString("name","there"), amount=money(o.optDouble("amount"));
        boolean theyOwe=o.optString("kind","").startsWith("They");
        String msg=theyOwe
            ?"Hi "+name+", just a friendly reminder about the "+amount+" pending amount. Please let me know when you expect to settle it. Thank you!"
            :"Hi "+name+", just a friendly reminder regarding the "+amount+" I need to settle with you. Please let me know if anything is needed from my side. Thank you!";
        try{
            Intent i=new Intent(Intent.ACTION_SEND); i.setType("text/plain"); i.putExtra(Intent.EXTRA_TEXT,msg);
            startActivity(Intent.createChooser(i,"Send reminder with"));
        }catch(Exception e){Toast.makeText(this,"No messaging app is available.",Toast.LENGTH_SHORT).show();}
    }

    void showTools(){
        recordNavigation(SCREEN_TOOLS);
        currentScreen=SCREEN_TOOLS;
        base("Tools","Currency conversion, live rates and gold.");

        addWrap(sectionTitle("Currency converter"));
        EditText amount=new EditText(this); fieldStyle(amount,"Amount",17); amount.setInputType(2|8192); addWrapMargin(amount,0,8);
        Spinner from=new Spinner(this), to=new Spinner(this);
        spinnerStyle(from); spinnerStyle(to);
        String[] currencies={"PKR","USD","AED","SAR","GBP","EUR","CAD","AUD","INR","JPY"};
        from.setAdapter(spinnerAdapter(currencies)); to.setAdapter(spinnerAdapter(currencies));
        from.setSelection(0); to.setSelection(1);

        Button swap=action("↔"); swap.setTextColor(WHITE); swap.setTextSize(20); swap.setBackground(bg(GREEN,22));
        LinearLayout rr=row();
        rr.addView(from,new LinearLayout.LayoutParams(0,dp(52),1));
        LinearLayout.LayoutParams swp=new LinearLayout.LayoutParams(dp(58),dp(52)); swp.setMargins(dp(7),0,dp(7),0); rr.addView(swap,swp);
        rr.addView(to,new LinearLayout.LayoutParams(0,dp(52),1)); addWrapMargin(rr,0,8);
        swap.setOnClickListener(v->{int a=from.getSelectedItemPosition(),b=to.getSelectedItemPosition();from.setSelection(b);to.setSelection(a);});

        TextView result=tv("Enter an amount and tap Convert.",15,MUTED,false); addWrapMargin(result,4,8);
        Button convert=action("Convert"); convert.setTextColor(WHITE); convert.setBackground(bg(GREEN,22)); addWrapMargin(convert,0,16);
        convert.setOnClickListener(v->{
            try{
                double a=Double.parseDouble(amount.getText().toString().trim());
                String f=from.getSelectedItem().toString(), t=to.getSelectedItem().toString();
                if(f.equals(t)){result.setText(String.format(Locale.US,"%.2f %s",a,t));return;}
                result.setText("Loading live rate…");
                new Thread(()->{
                    try{
                        String json=httpGet("https://open.er-api.com/v6/latest/"+f);
                        JSONObject rootJ=new JSONObject(json); double rate=rootJ.getJSONObject("rates").getDouble(t); double value=a*rate;
                        runOnUiThread(()->result.setText(String.format(Locale.US,"%.2f %s = %.2f %s",a,f,value,t)));
                    }catch(Exception e){runOnUiThread(()->result.setText("Could not load the live rate. Check your internet connection."));}
                }).start();
            }catch(Exception e){result.setText("Please enter a valid amount.");}
        });

        addWrap(sectionTitle("Currency rates"));
        LinearLayout rateTable=box(WHITE,12);
        addRateRow(rateTable,"Currency","1 PKR =","Rate",true);
        TextView ratesStatus=tv("Loading live currency rates…",13,MUTED,false); rateTable.addView(ratesStatus);
        addWrapMargin(rateTable,0,12); loadCurrencyRates(rateTable,ratesStatus);

        addWrap(sectionTitle("Gold rate in Pakistan"));
        LinearLayout goldTable=box(WHITE,12);
        addRateRow(goldTable,"Gold","Purity","Per tola",true);
        TextView goldStatus=tv("Loading 24K gold rate…",13,MUTED,false); goldTable.addView(goldStatus);
        addWrapMargin(goldTable,0,8); loadGoldRates(goldStatus);
        addWrapMargin(tv("24K gold only • per tola • Source: goldrateinpakistan.org",12,MUTED,false),0,8);

        Button refresh=action("Refresh rates"); refresh.setTextColor(WHITE); refresh.setBackground(bg(GREEN,22));
        addWrapMargin(refresh,0,10); refresh.setOnClickListener(v->{loadCurrencyRates(rateTable,ratesStatus);loadGoldRates(goldStatus);});
        nav();
    }

    void addRateRow(LinearLayout parent,String a,String b,String c,boolean header){
        LinearLayout r=row();
        int color=header?GREEN:INK;
        r.addView(tv(a,header?12:13,color,header),new LinearLayout.LayoutParams(0,-2,1));
        r.addView(tv(b,header?12:13,color,header),new LinearLayout.LayoutParams(0,-2,1));
        r.addView(tv(c,header?12:13,color,header),new LinearLayout.LayoutParams(0,-2,1));
        parent.addView(r);
        if(header)parent.addView(new Space(this),new LinearLayout.LayoutParams(1,dp(7)));
    }

    void loadCurrencyRates(LinearLayout table,TextView status){
        while(table.getChildCount()>2)table.removeViewAt(2);
        status.setVisibility(View.VISIBLE);
        table.addView(status);
        new Thread(()->{
            try{
                String json=httpGet("https://open.er-api.com/v6/latest/PKR");
                JSONObject rates=new JSONObject(json).getJSONObject("rates");
                String[] cs={"USD","AED","SAR","GBP","EUR","CAD","AUD","INR","JPY"};
                runOnUiThread(()->{
                    table.removeView(status);
                    for(String c:cs){
                        double one=rates.optDouble(c,Double.NaN);
                        if(!Double.isNaN(one)) addRateRow(table,c,"1 PKR",String.format(Locale.US,"%.6f %s",one,c),false);
                    }
                    table.addView(tv("Base: PKR • live exchange rates",11,MUTED,false));
                });
            }catch(Exception e){runOnUiThread(()->status.setText("Currency rates unavailable. Tap Refresh to try again."));}
        }).start();
    }

    void loadGoldRates(TextView target){
        target.setText("Loading 24K gold rate…");
        new Thread(()->{try{
            String json=httpGet("https://goldrateinpakistan.org/api/rates.json");
            JSONObject j=new JSONObject(json), gold=j.optJSONObject("gold"), rate=gold==null?null:gold.optJSONObject("24k");
            if(rate==null)throw new Exception("24K data missing");
            double value=rate.optDouble("per_tola",Double.NaN); if(Double.isNaN(value))throw new Exception("24K rate missing");
            String amount="Rs "+String.format(Locale.US,"%,.0f",value);
            String updated=j.optString("updated_at","");
            if(!updated.isEmpty())amount+=" • "+updated;
            final String displayAmount=amount;
            runOnUiThread(()->target.setText(displayAmount));
        }catch(Exception e){runOnUiThread(()->target.setText("24K gold rate unavailable. Tap Refresh to try again."));}}).start();
    }

    String httpGet(String address) throws Exception{
        java.net.HttpURLConnection con=(java.net.HttpURLConnection)new java.net.URL(address).openConnection(); con.setConnectTimeout(8000); con.setReadTimeout(10000); con.setRequestMethod("GET"); con.setRequestProperty("User-Agent","PaisaLaya/1.0");
        InputStream in=con.getInputStream(); BufferedReader br=new BufferedReader(new InputStreamReader(in)); StringBuilder s=new StringBuilder(); String line; while((line=br.readLine())!=null)s.append(line); br.close(); con.disconnect(); return s.toString();
    }

    void showSettings(){
        recordNavigation(SCREEN_SETTINGS);
        currentScreen=SCREEN_SETTINGS;
        base("Settings","Make Paisa Laya feel right for you.");
        addWrap(sectionTitle("Appearance"));
        Spinner theme=new Spinner(this); spinnerStyle(theme); theme.setAdapter(spinnerAdapter(new String[]{"System","Light","Dark"}));
        String savedTheme=prefs.getString("theme","System"); theme.setSelection(savedTheme.equals("Light")?1:savedTheme.equals("Dark")?2:0); addWrapMargin(theme,0,10);
        theme.setOnItemSelectedListener(new android.widget.AdapterView.OnItemSelectedListener(){public void onNothingSelected(android.widget.AdapterView<?> p){} public void onItemSelected(android.widget.AdapterView<?> p,View v,int pos,long id){String val=pos==1?"Light":pos==2?"Dark":"System"; if(!prefs.getString("theme","System").equals(val)){prefs.edit().putString("theme",val).apply();applyPreferencesTheme();renderCurrent();}}});
        Spinner accent=new Spinner(this); spinnerStyle(accent); accent.setAdapter(spinnerAdapter(new String[]{"Green","Blue","Purple","Gold"})); String ac=prefs.getString("accent","Green"); accent.setSelection(ac.equals("Blue")?1:ac.equals("Purple")?2:ac.equals("Gold")?3:0); addWrapMargin(accent,0,10);
        accent.setOnItemSelectedListener(new android.widget.AdapterView.OnItemSelectedListener(){public void onNothingSelected(android.widget.AdapterView<?> p){} public void onItemSelected(android.widget.AdapterView<?> p,View v,int pos,long id){String val=new String[]{"Green","Blue","Purple","Gold"}[pos]; if(!prefs.getString("accent","Green").equals(val)){prefs.edit().putString("accent",val).apply();applyPreferencesTheme();renderCurrent();}}});
        addWrap(sectionTitle("Default currency"));
        Spinner currency=new Spinner(this); spinnerStyle(currency); String[] cs={"PKR","USD","AED","SAR","GBP","EUR"}; currency.setAdapter(spinnerAdapter(cs)); String dc=prefs.getString("currency","PKR"); for(int i=0;i<cs.length;i++)if(cs[i].equals(dc))currency.setSelection(i); addWrapMargin(currency,0,12);
        currency.setOnItemSelectedListener(new android.widget.AdapterView.OnItemSelectedListener(){public void onNothingSelected(android.widget.AdapterView<?> p){} public void onItemSelected(android.widget.AdapterView<?> p,View v,int pos,long id){prefs.edit().putString("currency",cs[pos]).apply();}});
        addWrap(sectionTitle("Security"));
        Switch lockSwitch=new Switch(this); lockSwitch.setText("App lock"); lockSwitch.setTextSize(16); lockSwitch.setTextColor(INK); lockSwitch.setChecked(isLockEnabled());
        lockSwitch.setPadding(dp(8),dp(6),dp(8),dp(6)); addWrapMargin(lockSwitch,0,6);
        Button pinButton=action("Set / change PIN"); addWrapMargin(pinButton,0,8); pinButton.setVisibility(lockSwitch.isChecked()?View.VISIBLE:View.GONE);
        Switch bioSwitch=new Switch(this); bioSwitch.setText("Biometric / device security"); bioSwitch.setTextSize(16); bioSwitch.setTextColor(INK); bioSwitch.setChecked(prefs.getBoolean("biometric_lock",false));
        bioSwitch.setEnabled(Build.VERSION.SDK_INT>=28 && lockSwitch.isChecked()); bioSwitch.setVisibility(lockSwitch.isChecked()?View.VISIBLE:View.GONE); addWrapMargin(bioSwitch,0,10);
        lockSwitch.setOnCheckedChangeListener((button,checked)->{ if(checked){ setupPin(true); } else { prefs.edit().putBoolean("app_lock",false).putBoolean("biometric_lock",false).apply(); bioSwitch.setChecked(false); bioSwitch.setEnabled(false); bioSwitch.setVisibility(View.GONE); pinButton.setVisibility(View.GONE); feedback("App lock disabled",ToneGenerator.TONE_PROP_ACK); } });
        pinButton.setOnClickListener(v->setupPin(false));
        bioSwitch.setOnCheckedChangeListener((button,checked)->prefs.edit().putBoolean("biometric_lock",checked).apply());
        addWrap(sectionTitle("Data & reminders"));

        Button reports=action("Reports & Backup"); addWrapMargin(reports,0,8); reports.setOnClickListener(v->showReports());
        Button wa=action("WhatsApp reminders"); addWrapMargin(wa,0,8); wa.setOnClickListener(v->new AlertDialog.Builder(this,isDarkMode()?AlertDialog.THEME_DEVICE_DEFAULT_DARK:AlertDialog.THEME_DEVICE_DEFAULT_LIGHT).setTitle("WhatsApp reminders").setMessage("In People & Dues, choose a person from your phone contacts and tap WhatsApp to prepare a ready-made reminder. Paisa Laya never sends messages automatically.").setPositiveButton("OK",null).show());
        Button about=action("About Paisa Laya"); addWrapMargin(about,0,8); about.setOnClickListener(v->new AlertDialog.Builder(this).setTitle("Paisa Laya").setMessage("Simple personal money tracking, dues, currency conversion and gold-rate tools. Your transaction data is stored locally on this device.").setPositiveButton("OK",null).show());
        addWrap(tv("Tip: create a JSON backup before changing phones.",12,MUTED,false)); nav();
    }

    void applyPreferencesTheme(){
        String theme=prefs.getString("theme","System"); boolean dark=theme.equals("Dark"); if(theme.equals("System")) dark=(getResources().getConfiguration().uiMode&Configuration.UI_MODE_NIGHT_MASK)==Configuration.UI_MODE_NIGHT_YES;
        BG=dark?Color.rgb(20,24,22):Color.rgb(246,248,244); INK=dark?Color.WHITE:Color.rgb(25,35,29); WHITE=dark?Color.rgb(38,44,41):Color.WHITE; MUTED=dark?Color.rgb(180,190,184):Color.rgb(92,105,96);
        String a=prefs.getString("accent","Green"); if(a.equals("Blue")){GREEN=Color.rgb(43,105,190);GREEN_DARK=Color.rgb(26,72,135);MINT=dark?Color.rgb(35,55,80):Color.rgb(226,238,255);} else if(a.equals("Purple")){GREEN=Color.rgb(117,76,170);GREEN_DARK=Color.rgb(78,48,115);MINT=dark?Color.rgb(61,47,77):Color.rgb(239,229,252);} else if(a.equals("Gold")){GREEN=Color.rgb(184,132,36);GREEN_DARK=Color.rgb(119,83,19);MINT=dark?Color.rgb(70,59,34):Color.rgb(250,241,215);} else {GREEN=Color.rgb(36,132,83);GREEN_DARK=Color.rgb(18,92,57);MINT=dark?Color.rgb(38,67,50):Color.rgb(224,246,232);}
        getWindow().setStatusBarColor(GREEN_DARK); getWindow().setNavigationBarColor(BG); getWindow().getDecorView().setSystemUiVisibility(dark?0:View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR);
    }

    void showReports(){
        recordNavigation(SCREEN_REPORTS);
        currentScreen=SCREEN_REPORTS;
        base("Reports & Backup","Export, back up, or manage your data.");
        LinearLayout c=box(WHITE,17);
        c.addView(tv("Data tools",18,INK,true));
        c.addView(tv("Keep a copy of your transactions before changing phones.",12,MUTED,false));
        Button csv=action("⇩  Export transactions as CSV");
        Button backup=action("☁  Create JSON backup");
        Button restore=action("↥  Restore JSON backup");
        LinearLayout.LayoutParams bp=new LinearLayout.LayoutParams(-1,dp(52)); bp.setMargins(0,dp(10),0,0); c.addView(csv,bp);
        LinearLayout.LayoutParams b2=new LinearLayout.LayoutParams(-1,dp(52)); b2.setMargins(0,dp(7),0,0); c.addView(backup,b2);
        LinearLayout.LayoutParams b3=new LinearLayout.LayoutParams(-1,dp(52)); b3.setMargins(0,dp(7),0,0); c.addView(restore,b3);
        addWrapMargin(c,0,12);

        LinearLayout info=box(MINT,16);
        info.addView(tv("Your data stays on this device",15,GREEN,true));
        info.addView(tv("Use JSON backup to move your Paisa Laya data to another phone.",12,INK,false));
        addWrapMargin(info,0,12);

        Button clear=action("Clear all transactions");
        clear.setTextColor(RED); addWrapMargin(clear,0,8);

        csv.setOnClickListener(v->exportCsv());
        backup.setOnClickListener(v->backup());
        restore.setOnClickListener(v->restore());
        clear.setOnClickListener(v->dialogBuilder()
            .setTitle("Clear transactions?")
            .setMessage("This cannot be undone.")
            .setNegativeButton("Cancel",null)
            .setPositiveButton("Clear",(d,w)->{prefs.edit().remove(TX).apply();showReports();})
            .show());
        nav();
    }

    void exportCsv(){
        StringBuilder s=new StringBuilder("Date,Type,Category,Amount,Note\n"); JSONArray a=transactions();
        try{for(int i=0;i<a.length();i++){
            JSONObject o=a.getJSONObject(i);
            s.append(o.optString("date")).append(",").append(o.optString("type")).append(",")
             .append(o.optString("category")).append(",").append(o.optDouble("amount")).append(",")
             .append(o.optString("note").replace(","," ")).append("\n");
        }}catch(Exception e){}
        Intent in=new Intent(Intent.ACTION_SEND); in.setType("text/csv"); in.putExtra(Intent.EXTRA_TEXT,s.toString());
        startActivity(Intent.createChooser(in,"Share CSV"));
    }

    void backup(){
        Intent in=new Intent(Intent.ACTION_CREATE_DOCUMENT); in.setType("application/json");
        in.putExtra(Intent.EXTRA_TITLE,"paisa-laya-backup.json"); startActivityForResult(in,10);
    }

    void restore(){
        Intent in=new Intent(Intent.ACTION_OPEN_DOCUMENT); in.setType("application/json");
        in.addCategory(Intent.CATEGORY_OPENABLE); startActivityForResult(in,11);
    }

    TextView findContactView(View rootView){
        if(rootView instanceof TextView && ((TextView)rootView).getTag() instanceof Object[]) return (TextView)rootView;
        if(rootView instanceof ViewGroup){
            ViewGroup g=(ViewGroup)rootView;
            for(int i=0;i<g.getChildCount();i++){
                TextView found=findContactView(g.getChildAt(i));
                if(found!=null)return found;
            }
        }
        return null;
    }

    @Override protected void onActivityResult(int req,int res,Intent data){
        super.onActivityResult(req,res,data);
        if(res!=RESULT_OK||data==null)return;
        try{
            if(req==21){
                android.net.Uri uri=data.getData();
                android.database.Cursor c=getContentResolver().query(uri,
                    new String[]{ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME,ContactsContract.CommonDataKinds.Phone.NUMBER},
                    null,null,null);
                if(c!=null && c.moveToFirst()){
                    String n=c.getString(0), p=c.getString(1);
                    View decor=getWindow().getDecorView();
                    // The current People screen owns the selected contact TextView through its tag.
                    TextView selected=findContactView(decor);
                    if(selected!=null){
                        selected.setText(n+"  •  "+p);
                        selected.setTextColor(INK);
                        Object tag=selected.getTag();
                        if(tag instanceof Object[]){
                            Object[] fields=(Object[])tag;
                            if(fields.length>0 && fields[0] instanceof EditText)((EditText)fields[0]).setText(p);
                            if(fields.length>1 && fields[1] instanceof EditText)((EditText)fields[1]).setText(n);
                        }
                    }
                }
                if(c!=null)c.close();
                return;
            }
            if(req==10){
                OutputStream out=getContentResolver().openOutputStream(data.getData());
                JSONObject r=new JSONObject(); r.put("transactions",transactions()); r.put("dues_json",prefs.getString("dues_json","[]"));
                out.write(r.toString().getBytes()); out.close();
                Toast.makeText(this,"Backup saved",Toast.LENGTH_SHORT).show();
            }else if(req==11){
                InputStream in=getContentResolver().openInputStream(data.getData());
                BufferedReader br=new BufferedReader(new InputStreamReader(in));
                StringBuilder s=new StringBuilder(); String line;
                while((line=br.readLine())!=null)s.append(line); br.close();
                JSONObject r=new JSONObject(s.toString()); JSONArray restored=r.optJSONArray("transactions");
                prefs.edit().putString(TX,restored==null?"[]":restored.toString()).putString("dues_json",r.optString("dues_json","[]")).apply();
                showHome();
            }
        }catch(Exception e){Toast.makeText(this,"Could not process the file.",Toast.LENGTH_SHORT).show();}
    }
}
