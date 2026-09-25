package com.paisalaya.app;

import android.app.*;
import android.content.*;
import android.content.res.Configuration;
import android.graphics.*;
import android.graphics.drawable.GradientDrawable;
import android.graphics.pdf.PdfDocument;
import android.print.pdf.PrintedPdfDocument;
import android.print.PrintAttributes;
import android.os.Bundle;
import android.view.*;
import android.view.inputmethod.InputMethodManager;
import android.provider.ContactsContract;
import android.media.AudioManager;
import android.media.ToneGenerator;
import android.os.Build;
import android.hardware.biometrics.BiometricPrompt;
import android.os.CancellationSignal;
import android.content.IntentSender;
import android.security.keystore.KeyProperties;
import android.view.Window;
import android.widget.*;
import org.json.*;
import java.io.*;
import java.text.SimpleDateFormat;
import java.util.*;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import com.google.android.gms.auth.api.identity.AuthorizationClient;
import com.google.android.gms.auth.api.identity.AuthorizationRequest;
import com.google.android.gms.auth.api.identity.AuthorizationResult;
import com.google.android.gms.auth.api.identity.Identity;
import com.google.android.gms.common.api.Scope;

public class MainActivity extends Activity {
    static final String PREF="paisa_laya", TX="transactions";
    static final String SYNC_FILE="paisa_laya_sync.json";
    static final String DRIVE_APPDATA_SCOPE="https://www.googleapis.com/auth/drive.appdata";
    static final String SCREEN_HOME="home", SCREEN_ADD="add", SCREEN_PEOPLE="people", SCREEN_TOOLS="tools", SCREEN_REPORTS="reports", SCREEN_SETTINGS="settings", SCREEN_NOTIFICATIONS="notifications", SCREEN_CURRENCIES="currencies";

    LinearLayout root, content;
    SharedPreferences prefs;
    String currentScreen=SCREEN_HOME;
    String pendingType="Expense";
    final ArrayDeque<String> screenHistory=new ArrayDeque<>();
    boolean renderingScreen=false;
    boolean unlockedThisLaunch=false;
    boolean syncBusy=false;
    JSONObject pendingInvoice=null;
    final SimpleDateFormat dueFormat=new SimpleDateFormat("yyyy-MM-dd",Locale.US);

    int BG=Color.rgb(246,248,244), INK=Color.rgb(25,35,29), GREEN=Color.rgb(36,132,83);
    int GREEN_DARK=Color.rgb(18,92,57), MINT=Color.rgb(224,246,232), RED=Color.rgb(216,76,76);
    int GOLD=Color.rgb(238,174,65), MUTED=Color.rgb(92,105,96), WHITE=Color.WHITE;

    int dp(float v){return (int)(v*getResources().getDisplayMetrics().density+0.5f);}

    @Override public void onCreate(Bundle state){
        super.onCreate(state);
        prefs=getSharedPreferences(PREF,0);
        createNotificationChannel();
        if(getIntent().getBooleanExtra("open_notifications",false)) currentScreen=SCREEN_NOTIFICATIONS;
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
            if(prefs.getBoolean("google_sync_enabled",false)){
                new android.os.Handler().postDelayed(()->googleSync(),1200);
            }
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
        if(Build.VERSION.SDK_INT>=28 && prefs.getBoolean("biometric_lock",false)){ lock.addView(biometric,new LinearLayout.LayoutParams(-1,dp(52))); biometric.setOnClickListener(v->authenticateBiometric()); } else biometric.setVisibility(View.GONE);
        TextView error=tv("",13,RED,false); error.setGravity(Gravity.CENTER); lock.addView(error);
        setContentView(lock);
        unlock.setOnClickListener(v->{ if(verifyPin(pin.getText().toString())){ unlockedThisLaunch=true; feedback("Unlocked",ToneGenerator.TONE_PROP_ACK); renderCurrent(); } else error.setText("Incorrect PIN. Please try again."); });
        pin.requestFocus();
    }

    void authenticateBiometric(){
        if(Build.VERSION.SDK_INT<28)return;
        try{
            BiometricPrompt prompt=new BiometricPrompt.Builder(this).setTitle("Unlock Paisa Laya").setSubtitle("Use your biometric or device screen lock").setDescription("Your financial data stays protected on this device.").setNegativeButton("Use PIN",getMainExecutor(),(d,w)->{}).build();
            CancellationSignal cancellationSignal=new CancellationSignal();
            prompt.authenticate(cancellationSignal,getMainExecutor(),new BiometricPrompt.AuthenticationCallback(){
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
        else if(SCREEN_NOTIFICATIONS.equals(currentScreen)) showNotifications();
        else if(SCREEN_CURRENCIES.equals(currentScreen)) showCurrenciesMore();
        else showHome();
        renderingScreen=false;
    }

    void recordNavigation(String target){
        if(target.equals(SCREEN_HOME)){
            screenHistory.clear();
            currentScreen=SCREEN_HOME;
            return;
        }
        if(!target.equals(currentScreen) && !renderingScreen){
            if(screenHistory.isEmpty() && !SCREEN_HOME.equals(currentScreen)){
                screenHistory.push(SCREEN_HOME);
            }else if(!screenHistory.isEmpty() && screenHistory.peek().equals(target)){
                screenHistory.pop();
            }else{
                screenHistory.push(currentScreen);
            }
        }
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
        if(!SCREEN_HOME.equals(currentScreen)){
            if(!screenHistory.isEmpty()){
                currentScreen=screenHistory.pop();
            }else{
                currentScreen=SCREEN_HOME;
            }
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
        head.setOrientation(LinearLayout.HORIZONTAL);
        head.setGravity(Gravity.CENTER_VERTICAL);
        int top=getResources().getConfiguration().orientation==Configuration.ORIENTATION_LANDSCAPE?10:18;
        head.setPadding(dp(18),dp(top),dp(12),dp(4));
        LinearLayout headText=new LinearLayout(this);
        headText.setOrientation(LinearLayout.VERTICAL);
        TextView titleView=tv(title,28,INK,true);
        TextView subView=tv(subtitle,15,MUTED,false);
        headText.addView(titleView,new LinearLayout.LayoutParams(-1,-2));
        headText.addView(subView,new LinearLayout.LayoutParams(-1,-2));
        head.addView(headText,new LinearLayout.LayoutParams(0,-2,1));
        Button bell=action("🔔"); bell.setTextSize(16); bell.setContentDescription("Notifications"); bell.setBackground(bg(WHITE,18));
        LinearLayout.LayoutParams bellP=new LinearLayout.LayoutParams(dp(42),dp(42)); bellP.setMargins(dp(6),0,0,0); head.addView(bell,bellP);
        bell.setOnClickListener(v->showNotifications());
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

        items[0].setOnClickListener(v->{screenHistory.clear();showHome();});
        items[1].setOnClickListener(v->{screenHistory.clear();showAdd();});
        items[2].setOnClickListener(v->{screenHistory.clear();showPeople();});
        items[3].setOnClickListener(v->{screenHistory.clear();showTools();});
        items[4].setOnClickListener(v->{screenHistory.clear();showSettings();});
        // Android 15+ uses edge-to-edge, so the system navigation area can overlap this
        // custom bottom navigation bar. Keep the tabs above both gesture and 3-button
        // navigation areas by applying the current navigation-bar inset.
        LinearLayout.LayoutParams navParams=new LinearLayout.LayoutParams(-1,dp(72));
        n.setPadding(dp(6),dp(5),dp(6),dp(7));
        n.setOnApplyWindowInsetsListener((v,insets)->{
            int bottomInset;
            if(Build.VERSION.SDK_INT>=30){
                bottomInset=insets.getInsets(WindowInsets.Type.navigationBars()).bottom;
            }else{
                bottomInset=insets.getSystemWindowInsetBottom();
            }
            n.setPadding(dp(6),dp(5),dp(6),dp(7)+bottomInset);
            LinearLayout.LayoutParams lp=(LinearLayout.LayoutParams)n.getLayoutParams();
            if(lp!=null){
                lp.height=dp(72)+bottomInset;
                n.setLayoutParams(lp);
            }
            return insets;
        });
        root.addView(n,navParams);
        n.requestApplyInsets();
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

    void save(JSONArray a){
        prefs.edit().putString(TX,a.toString()).putLong("local_data_updated",System.currentTimeMillis()).apply();
        autoSyncIfEnabled();
    }
    void autoSyncIfEnabled(){
        if(prefs.getBoolean("google_sync_enabled",false) && !syncBusy){
            new android.os.Handler().postDelayed(this::googleSync,700);
        }
    }

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
        inc.addView(tv("↘  INCOME",11,Color.rgb(210,244,222),true));
        inc.addView(tv(money(t[0]),17,WHITE,true));
        LinearLayout exp=box(Color.rgb(194,70,70),13);
        exp.addView(tv("↗  EXPENSE",11,Color.rgb(255,220,220),true));
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
                String icon="Income".equals(o.getString("type"))?"↘":"↗";
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

        TextView dueLabel=tv("Due date (optional)",13,INK,true); addWrapMargin(dueLabel,0,5);
        LinearLayout dueRow=row();
        EditText dueDate=new EditText(this); fieldStyle(dueDate,"Select due date",16); dueDate.setFocusable(false); dueDate.setClickable(true);
        Button pickDue=action("📅"); pickDue.setTextColor(WHITE); pickDue.setBackground(bg(GREEN,22));
        dueRow.addView(dueDate,new LinearLayout.LayoutParams(0,dp(56),1));
        LinearLayout.LayoutParams dueBtnP=new LinearLayout.LayoutParams(dp(58),dp(56)); dueBtnP.setMargins(dp(8),0,0,0); dueRow.addView(pickDue,dueBtnP);
        addWrapMargin(dueRow,0,10);
        View.OnClickListener duePicker=v->showDueDatePicker(dueDate); dueDate.setOnClickListener(duePicker); pickDue.setOnClickListener(duePicker);
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
                String due=dueDate.getText().toString().trim(); if(!due.isEmpty()) o.put("due_date",due);
                o.put("settled",false); a.put(o); if(!due.isEmpty()){scheduleDueNotification(o);ensureNotificationPermission();}
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
        String due=o.optString("due_date","");
        if(!due.isEmpty()) info.addView(tv(dueStatus(due),12,dueIsOverdue(due)?RED:GREEN,true));
        top.addView(info,new LinearLayout.LayoutParams(0,-2,1));

        Button mark=action(settled?"Settled":"Mark");
        mark.setTextSize(12); mark.setTextColor(settled?MUTED:col);
        top.addView(mark,new LinearLayout.LayoutParams(dp(72),dp(44)));
        Button del=action("Delete"); del.setTextSize(12); del.setTextColor(RED);
        LinearLayout.LayoutParams delp=new LinearLayout.LayoutParams(dp(72),dp(44)); delp.setMargins(dp(6),0,0,0); top.addView(del,delp);
        card.addView(top);

        Button invoice=action("PDF invoice");
        invoice.setTextColor(GREEN); invoice.setBackground(bg(WHITE,20));
        LinearLayout.LayoutParams invp=new LinearLayout.LayoutParams(-1,dp(44)); invp.setMargins(0,dp(9),0,0);
        card.addView(invoice,invp);
        invoice.setOnClickListener(v->requestInvoicePdf(o));
        
        if(!settled){
            Button dueEdit=action("📅 Due date"); dueEdit.setTextColor(GREEN); dueEdit.setBackground(bg(WHITE,20));
            LinearLayout.LayoutParams dep=new LinearLayout.LayoutParams(-1,dp(44)); dep.setMargins(0,dp(9),0,0); card.addView(dueEdit,dep);
            dueEdit.setOnClickListener(v->editPersonDueDate(index));
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

    void updatePeople(JSONArray people){
        prefs.edit().putString("dues_json",people.toString()).putLong("local_data_updated",System.currentTimeMillis()).apply();
        autoSyncIfEnabled();
    }

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

    void createNotificationChannel(){
        if(Build.VERSION.SDK_INT>=26){
            NotificationChannel c=new NotificationChannel("due_reminders","Payment & Receiving reminders",NotificationManager.IMPORTANCE_HIGH);
            c.setDescription("Reminders for Paisa Laya due dates.");
            NotificationManager nm=(NotificationManager)getSystemService(NOTIFICATION_SERVICE); if(nm!=null)nm.createNotificationChannel(c);
        }
    }
    void ensureNotificationPermission(){
        if(Build.VERSION.SDK_INT>=33 && checkSelfPermission("android.permission.POST_NOTIFICATIONS")!=android.content.pm.PackageManager.PERMISSION_GRANTED) requestPermissions(new String[]{"android.permission.POST_NOTIFICATIONS"},44);
    }
    void showDueDatePicker(EditText target){
        Calendar c=Calendar.getInstance(); String existing=target.getText().toString().trim();
        try{if(!existing.isEmpty()){Date d=dueFormat.parse(existing);if(d!=null)c.setTime(d);}}catch(Exception ignored){}
        new DatePickerDialog(this,(view,y,m,day)->{Calendar picked=Calendar.getInstance();picked.set(y,m,day);target.setText(dueFormat.format(picked.getTime()));},c.get(Calendar.YEAR),c.get(Calendar.MONTH),c.get(Calendar.DAY_OF_MONTH)).show();
    }
    boolean dueIsOverdue(String due){
        try{Date d=dueFormat.parse(due);if(d==null)return false;Calendar t=Calendar.getInstance();t.set(Calendar.HOUR_OF_DAY,0);t.set(Calendar.MINUTE,0);t.set(Calendar.SECOND,0);t.set(Calendar.MILLISECOND,0);return d.before(t.getTime());}catch(Exception e){return false;}
    }
    String dueStatus(String due){
        try{Date d=dueFormat.parse(due);Calendar t=Calendar.getInstance();Calendar x=Calendar.getInstance();x.setTime(d);if(t.get(Calendar.YEAR)==x.get(Calendar.YEAR)&&t.get(Calendar.DAY_OF_YEAR)==x.get(Calendar.DAY_OF_YEAR))return "Due today • "+due;return (d.before(new Date())?"Overdue • ":"Due • ")+due;}catch(Exception e){return "Due • "+due;}
    }
    void scheduleDueNotification(JSONObject o){
        try{String due=o.optString("due_date","");if(due.isEmpty()||o.optBoolean("settled",false))return;Date date=dueFormat.parse(due);if(date==null)return;Calendar w=Calendar.getInstance();w.setTime(date);w.set(Calendar.HOUR_OF_DAY,9);w.set(Calendar.MINUTE,0);w.set(Calendar.SECOND,0);w.set(Calendar.MILLISECOND,0);if(w.getTimeInMillis()<=System.currentTimeMillis())return;
            int id=Math.abs((o.optString("name","")+"|"+due).hashCode());Intent in=new Intent(this,DueNotificationReceiver.class);in.putExtra("name",o.optString("name","there"));in.putExtra("amount",o.optDouble("amount",0));in.putExtra("kind",o.optString("kind","They owe me"));
            PendingIntent pi=PendingIntent.getBroadcast(this,id,in,PendingIntent.FLAG_UPDATE_CURRENT|(Build.VERSION.SDK_INT>=23?PendingIntent.FLAG_IMMUTABLE:0));AlarmManager am=(AlarmManager)getSystemService(ALARM_SERVICE);if(am!=null)am.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP,w.getTimeInMillis(),pi);
        }catch(Exception ignored){}
    }
    void editPersonDueDate(int index){
        EditText date=new EditText(this);fieldStyle(date,"Select due date",16);date.setFocusable(false);
        try{JSONArray a=new JSONArray(prefs.getString("dues_json","[]"));date.setText(a.getJSONObject(index).optString("due_date",""));}catch(Exception ignored){}
        date.setOnClickListener(v->showDueDatePicker(date));
        dialogBuilder().setTitle("Payment / receiving due date").setView(date).setNegativeButton("Cancel",null).setPositiveButton("Save",(d,w)->{try{JSONArray a=new JSONArray(prefs.getString("dues_json","[]"));JSONObject o=a.getJSONObject(index);String due=date.getText().toString().trim();if(due.isEmpty())o.remove("due_date");else{o.put("due_date",due);scheduleDueNotification(o);ensureNotificationPermission();}updatePeople(a);showPeople();}catch(Exception e){Toast.makeText(this,"Could not update the due date.",Toast.LENGTH_SHORT).show();}}).show();
    }
    void showNotifications(){
        recordNavigation(SCREEN_NOTIFICATIONS);currentScreen=SCREEN_NOTIFICATIONS;base("Notifications","Payment and receiving reminders.");
        addWrapMargin(tv("Upcoming & overdue",19,INK,true),0,8);LinearLayout list=box(WHITE,14);
        try{JSONArray a=new JSONArray(prefs.getString("dues_json","[]"));boolean any=false;for(int i=0;i<a.length();i++){JSONObject o=a.getJSONObject(i);if(o.optBoolean("settled",false))continue;String due=o.optString("due_date","");if(due.isEmpty())continue;any=true;boolean receive=o.optString("kind","").startsWith("They");LinearLayout card=box(dueIsOverdue(due)?Color.rgb(255,238,238):MINT,12);card.addView(tv(o.optString("name","Person"),16,INK,true));card.addView(tv((receive?"Receive ":"Pay ")+money(o.optDouble("amount")),14,receive?GREEN:RED,true));card.addView(tv(dueStatus(due),12,MUTED,false));Button people=action("Open People & Dues");people.setTextColor(GREEN);LinearLayout.LayoutParams pp=new LinearLayout.LayoutParams(-1,dp(42));pp.setMargins(0,dp(8),0,0);card.addView(people,pp);people.setOnClickListener(v->{currentScreen=SCREEN_PEOPLE;screenHistory.clear();showPeople();});list.addView(card,new LinearLayout.LayoutParams(-1,-2));}if(!any)list.addView(tv("No active due-date reminders yet. Add a due date to a person and Paisa Laya will remind you automatically.",13,MUTED,false));}catch(Exception e){list.addView(tv("Could not load reminders.",13,RED,false));}
        addWrapMargin(list,0,12);Button add=action("＋  Add a due date");add.setTextColor(WHITE);add.setBackground(bg(GREEN,22));addWrapMargin(add,0,8);add.setOnClickListener(v->showPeople());Button permission=action("Enable notifications");permission.setTextColor(GREEN);addWrapMargin(permission,0,8);permission.setOnClickListener(v->ensureNotificationPermission());addWrap(tv("Reminder time: 9:00 AM on the selected due date. Notifications are generated on this device.",11,MUTED,false));nav();
    }
    public static class DueNotificationReceiver extends BroadcastReceiver{
        @Override public void onReceive(Context context,Intent intent){
            String name=intent.getStringExtra("name");double amount=intent.getDoubleExtra("amount",0);String kind=intent.getStringExtra("kind");boolean receive=kind!=null&&kind.startsWith("They");String title=receive?"Payment due to be received":"Payment due";String text=(receive?"Receive ":"Pay ")+String.format(Locale.US,"PKR %,.0f",amount)+(receive?" from ":" to ")+(name==null?"person":name);
            Intent open=new Intent(context,MainActivity.class);open.putExtra("open_notifications",true);open.addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP|Intent.FLAG_ACTIVITY_SINGLE_TOP);PendingIntent pi=PendingIntent.getActivity(context,9001,open,PendingIntent.FLAG_UPDATE_CURRENT|(Build.VERSION.SDK_INT>=23?PendingIntent.FLAG_IMMUTABLE:0));
            Notification.Builder b=Build.VERSION.SDK_INT>=26?new Notification.Builder(context,"due_reminders"):new Notification.Builder(context);b.setSmallIcon(android.R.drawable.ic_dialog_info).setContentTitle(title).setContentText(text).setAutoCancel(true).setContentIntent(pi).setPriority(Notification.PRIORITY_HIGH);NotificationManager nm=(NotificationManager)context.getSystemService(Context.NOTIFICATION_SERVICE);if(nm!=null)nm.notify(Math.abs((name==null?"":name).hashCode()),b.build());
        }
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
                result.setText("Loading FOREX.com.pk rate…");
                new Thread(()->{
                    try{
                        String html=httpGet("https://www.forex.com.pk/");
                        double fPkr=parseForexMid(html,f), tPkr=parseForexMid(html,t);
                        if(Double.isNaN(fPkr)||Double.isNaN(tPkr)) throw new Exception("Currency unavailable");
                        double value=a*(fPkr/tPkr);
                        runOnUiThread(()->result.setText(String.format(Locale.US,"%.2f %s = %.2f %s",a,f,value,t)));
                    }catch(Exception e){runOnUiThread(()->result.setText("Could not load the FOREX.com.pk rate. Check your internet connection."));}
                }).start();
            }catch(Exception e){result.setText("Please enter a valid amount.");}
        });

        addWrap(sectionTitle("Pakistan open-market currency rates"));
        LinearLayout rateTable=box(WHITE,12);
        addRateRow(rateTable,"Currency","Buying (PKR)","Selling (PKR)",true);
        TextView ratesStatus=tv("Loading FOREX.com.pk rates…",13,MUTED,false); rateTable.addView(ratesStatus);
        addWrapMargin(rateTable,0,8); loadCurrencyRates(rateTable,ratesStatus,true);

        Button more=action("View more currencies"); more.setTextColor(WHITE); more.setBackground(bg(GREEN,22));
        addWrapMargin(more,0,14); more.setOnClickListener(v->showCurrenciesMore());

        addWrap(sectionTitle("Gold rate in Pakistan"));
        LinearLayout goldCard=box(WHITE,16);
        TextView goldTitle=tv("24K GOLD",13,GOLD,true);
        goldCard.addView(goldTitle);
        TextView goldStatus=tv("Loading latest gold rate…",27,INK,true);
        goldCard.addView(goldStatus,new LinearLayout.LayoutParams(-1,-2));
        TextView goldMeta=tv("Per tola • latest available",12,MUTED,false);
        goldCard.addView(goldMeta);
        LinearLayout goldStats=row();
        LinearLayout g10=box(MINT,11); g10.addView(tv("10 GRAMS",10,GREEN,true)); TextView g10v=tv("—",16,INK,true); g10.addView(g10v);
        LinearLayout g1=box(MINT,11); g1.addView(tv("1 GRAM",10,GREEN,true)); TextView g1v=tv("—",16,INK,true); g1.addView(g1v);
        goldStats.addView(g10,new LinearLayout.LayoutParams(0,-2,1)); LinearLayout.LayoutParams g1p=new LinearLayout.LayoutParams(0,-2,1);g1p.setMargins(dp(8),0,0,0);goldStats.addView(g1,g1p);
        goldCard.addView(goldStats,new LinearLayout.LayoutParams(-1,-2));
        TextView goldSource=tv("Source: GoldRateInPakistan • 24K only",11,MUTED,false);
        goldCard.addView(goldSource);
        addWrapMargin(goldCard,0,10); loadGoldRates(goldStatus,g10v,g1v,goldMeta);

        Button refresh=action("Refresh rates"); refresh.setTextColor(WHITE); refresh.setBackground(bg(GREEN,22));
        addWrapMargin(refresh,0,10); refresh.setOnClickListener(v->{loadCurrencyRates(rateTable,ratesStatus,true);loadGoldRates(goldStatus,g10v,g1v,goldMeta);});
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

    void showCurrenciesMore(){
        recordNavigation(SCREEN_CURRENCIES);
        currentScreen=SCREEN_CURRENCIES;
        base("More currencies","FOREX.com.pk Pakistan open-market rates.");
        LinearLayout table=box(WHITE,12);
        addRateRow(table,"Currency","Buying (PKR)","Selling (PKR)",true);
        TextView status=tv("Loading FOREX.com.pk rates…",13,MUTED,false);
        table.addView(status);
        addWrapMargin(table,0,10);
        loadCurrencyRates(table,status,false);

        TextView source=tv("Source: FOREX.com.pk • Rates are provided for public reference and may vary by dealer.",11,MUTED,false);
        addWrapMargin(source,0,10);

        Button refresh=action("Refresh rates"); refresh.setTextColor(WHITE); refresh.setBackground(bg(GREEN,22));
        addWrapMargin(refresh,0,8); refresh.setOnClickListener(v->loadCurrencyRates(table,status,false));
        nav();
    }

    void addCurrencyRateRow(LinearLayout table,String code,String buying,String selling){
        LinearLayout r=row();
        r.addView(tv("1 "+code,13,INK,true),new LinearLayout.LayoutParams(0,-2,1));
        r.addView(tv("Rs "+buying,13,INK,false),new LinearLayout.LayoutParams(0,-2,1));
        r.addView(tv("Rs "+selling,13,INK,false),new LinearLayout.LayoutParams(0,-2,1));
        table.addView(r);
        table.addView(new Space(this),new LinearLayout.LayoutParams(1,dp(5)));
    }

    double parseForexMid(String html,String code) throws Exception{
        if("PKR".equals(code)) return 1.0;
        String[] names={"USD:US Dollar","GBP:UK Pound Sterling","EUR:Euro","AED:U.A.E Dirham","SAR:Saudi Riyal","AUD:Australian Dollar","CAD:Canadian Dollar","CNY:China Yuan","JPY:Japanese Yen"};
        String name=null;
        for(String item:names){String[] p=item.split(":");if(p[0].equals(code)){name=p[1];break;}}
        if(name==null) throw new Exception("Unsupported currency");
        String text=html.replaceAll("(?s)<script.*?</script>"," ").replaceAll("(?s)<style.*?</style>"," ").replaceAll("<[^>]+>"," ").replace("&nbsp;"," ").replaceAll("\\s+"," ").trim();
        java.util.regex.Matcher m=java.util.regex.Pattern.compile(java.util.regex.Pattern.quote(name)+"\\s+([0-9.,]+)\\s+([0-9.,]+)",java.util.regex.Pattern.CASE_INSENSITIVE).matcher(text);
        if(!m.find()) throw new Exception("Rate not found");
        double buy=Double.parseDouble(m.group(1).replace(",","")), sell=Double.parseDouble(m.group(2).replace(",",""));
        return (buy+sell)/2.0;
    }

    void loadCurrencyRates(LinearLayout table,TextView status,boolean topOnly){
        while(table.getChildCount()>2)table.removeViewAt(2);
        status.setVisibility(View.VISIBLE);
        table.addView(status);
        new Thread(()->{
            try{
                String html=httpGet("https://www.forex.com.pk/");
                String text=html.replaceAll("(?s)<script.*?</script>"," ").replaceAll("(?s)<style.*?</style>"," ")
                    .replaceAll("<[^>]+>"," ").replace("&nbsp;"," ").replaceAll("\\s+"," ").trim();
                String[] codes={"USD","GBP","EUR","AED","SAR","AUD","CAD","CNY","JPY"};
                String[] names={"US Dollar","UK Pound Sterling","Euro","U.A.E Dirham","Saudi Riyal","Australian Dollar","Canadian Dollar","China Yuan","Japanese Yen"};
                ArrayList<String[]> rows=new ArrayList<>();
                final String[] updatedBox={""};
                java.util.regex.Matcher um=java.util.regex.Pattern.compile("Updated at\\s*:\\s*([^C]+?)\\s+Currency\\s+Buying\\s+Selling",java.util.regex.Pattern.CASE_INSENSITIVE).matcher(text);
                if(um.find()) updatedBox[0]=um.group(1).trim();
                for(int i=0;i<names.length;i++){
                    java.util.regex.Matcher m=java.util.regex.Pattern.compile(java.util.regex.Pattern.quote(names[i])+"\\s+([0-9.,]+)\\s+([0-9.,]+)",java.util.regex.Pattern.CASE_INSENSITIVE).matcher(text);
                    if(m.find()) rows.add(new String[]{codes[i],m.group(1),m.group(2)});
                }
                runOnUiThread(()->{
                    table.removeView(status);
                    int count=0;
                    for(String[] r:rows){
                        if(topOnly && count>=5)break;
                        addCurrencyRateRow(table,r[0],r[1],r[2]); count++;
                    }
                    if(rows.isEmpty()){
                        status.setText("FOREX.com.pk rates unavailable. Tap Refresh to try again.");
                        table.addView(status);
                    }else{
                        String u=updatedBox[0];
                        if(u.isEmpty()) u="Latest available";
                        table.addView(tv("Updated: "+u+" • 1 foreign currency = PKR",11,MUTED,false));
                    }
                });
            }catch(Exception e){
                runOnUiThread(()->status.setText("FOREX.com.pk rates unavailable. Tap Refresh to try again."));
            }
        }).start();
    }

    void loadGoldRates(TextView target,TextView tenGram,TextView oneGram,TextView meta){
        target.setContentDescription("24K gold only");
        target.setText("Loading…"); tenGram.setText("—"); oneGram.setText("—"); meta.setText("Per tola • latest available");
        new Thread(()->{try{
            String json=httpGet("https://goldrateinpakistan.org/api/rates.json");
            JSONObject j=new JSONObject(json), gold=j.optJSONObject("gold"), rate=gold==null?null:gold.optJSONObject("24k");
            if(rate==null)throw new Exception("24K data missing");
            double tola=rate.optDouble("per_tola",Double.NaN); if(Double.isNaN(tola))throw new Exception("24K rate missing");
            double perGram=tola/11.6638125, per10=perGram*10;
            String updated=j.optString("updated_at","");
            String main="Rs "+String.format(Locale.US,"%,.0f",tola);
            String ten="Rs "+String.format(Locale.US,"%,.0f",per10);
            String one="Rs "+String.format(Locale.US,"%,.0f",perGram);
            String detail=updated.isEmpty()?"Per tola • latest available":"Per tola • Updated "+updated;
            runOnUiThread(()->{target.setText(main);tenGram.setText(ten);oneGram.setText(one);meta.setText(detail);});
        }catch(Exception e){runOnUiThread(()->{target.setText("Rate unavailable");meta.setText("Tap Refresh to try again");});}}).start();
    }

    void requestInvoicePdf(JSONObject person){
        pendingInvoice=person;
        String safe=person.optString("name","person").replaceAll("[^a-zA-Z0-9_-]+","_");
        Intent in=new Intent(Intent.ACTION_CREATE_DOCUMENT);
        in.addCategory(Intent.CATEGORY_OPENABLE);
        in.setType("application/pdf");
        in.putExtra(Intent.EXTRA_TITLE,"Paisa-Laya-Invoice-"+safe+".pdf");
        startActivityForResult(in,31);
    }

    void writeInvoicePdf(android.net.Uri uri,JSONObject person){
        try{
            PdfDocument doc=new PdfDocument();
            PdfDocument.PageInfo info=new PdfDocument.PageInfo.Builder(595,842,1).create();
            PdfDocument.Page page=doc.startPage(info);
            Canvas c=page.getCanvas();
            Paint p=new Paint(Paint.ANTI_ALIAS_FLAG);
            p.setTypeface(Typeface.create(Typeface.DEFAULT,Typeface.NORMAL));
            p.setColor(Color.rgb(25,35,29));
            p.setTextSize(12);
            
            p.setTypeface(Typeface.create(Typeface.DEFAULT,Typeface.BOLD));
            p.setTextSize(30); p.setColor(GREEN);
            c.drawText("Paisa Laya",42,58,p);
            p.setTypeface(Typeface.create(Typeface.DEFAULT,Typeface.NORMAL));
            p.setTextSize(11); p.setColor(Color.rgb(92,105,96));
            c.drawText("Payment / Due Statement",42,80,p);
            
            p.setTypeface(Typeface.create(Typeface.DEFAULT,Typeface.BOLD));
            p.setTextSize(18); p.setColor(Color.rgb(25,35,29));
            c.drawText("INVOICE / STATEMENT",42,125,p);
            p.setTypeface(Typeface.create(Typeface.DEFAULT,Typeface.NORMAL));
            p.setTextSize(11); p.setColor(Color.rgb(92,105,96));
            String invoiceNo="PL-"+new SimpleDateFormat("yyyyMMdd-HHmmss",Locale.US).format(new Date());
            c.drawText("Invoice No: "+invoiceNo,42,146,p);
            c.drawText("Issue date: "+new SimpleDateFormat("dd MMM yyyy",Locale.US).format(new Date()),42,163,p);
            
            p.setColor(Color.rgb(224,246,232));
            c.drawRoundRect(35,190,560,330,18,18,p);
            p.setColor(Color.rgb(25,35,29));
            p.setTypeface(Typeface.create(Typeface.DEFAULT,Typeface.BOLD)); p.setTextSize(18);
            c.drawText(person.optString("name","Person"),55,225,p);
            p.setTypeface(Typeface.create(Typeface.DEFAULT,Typeface.NORMAL)); p.setTextSize(12);
            String phone=person.optString("phone","");
            if(!phone.isEmpty())c.drawText("Phone: "+phone,55,246,p);
            c.drawText(person.optString("kind","They owe me"),55,267,p);
            String due=person.optString("due_date","");
            c.drawText("Due date: "+(due.isEmpty()?"Not specified":due),55,288,p);
            String status=person.optBoolean("settled",false)?"SETTLED":(due.isEmpty()?"OUTSTANDING":(dueIsOverdue(due)?"OVERDUE":"DUE"));
            p.setColor(person.optBoolean("settled",false)?GREEN:(dueIsOverdue(due)?RED:GREEN));
            p.setTypeface(Typeface.create(Typeface.DEFAULT,Typeface.BOLD)); p.setTextSize(12);
            c.drawText("STATUS: "+status,55,310,p);
            
            double amount=person.optDouble("amount",0);
            double remaining=person.optBoolean("settled",false)?0:amount;
            p.setColor(Color.rgb(25,35,29)); p.setTextSize(13); p.setTypeface(Typeface.DEFAULT);
            c.drawText("Original amount",55,370,p);
            c.drawText("Amount remaining",55,410,p);
            p.setTypeface(Typeface.create(Typeface.DEFAULT,Typeface.BOLD)); p.setTextSize(20);
            c.drawText(money(amount),385,370,p);
            p.setColor(GREEN); c.drawText(money(remaining),385,410,p);
            
            p.setColor(Color.rgb(220,225,220)); c.drawRect(45,435,550,436,p);
            p.setColor(Color.rgb(92,105,96)); p.setTypeface(Typeface.DEFAULT); p.setTextSize(12);
            c.drawText("Note",45,468,p);
            p.setColor(Color.rgb(25,35,29)); p.setTextSize(13);
            String note=person.optString("note","");
            c.drawText(note.isEmpty()?"No note provided.":note,45,491,p);
            
            p.setColor(Color.rgb(92,105,96)); p.setTextSize(10);
            c.drawText("Prepared with Paisa Laya • Personal money tracking",45,785,p);
            c.drawText("This is a personal statement of the recorded amount and due date.",45,802,p);
            
            doc.finishPage(page);
            OutputStream out=getContentResolver().openOutputStream(uri);
            doc.writeTo(out); out.close(); doc.close();
            
            Intent share=new Intent(Intent.ACTION_SEND);
            share.setType("application/pdf");
            share.putExtra(Intent.EXTRA_STREAM,uri);
            share.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
            startActivity(Intent.createChooser(share,"Send Paisa Laya invoice"));
            Toast.makeText(this,"PDF invoice created",Toast.LENGTH_SHORT).show();
        }catch(Exception e){
            Toast.makeText(this,"Could not create the PDF invoice.",Toast.LENGTH_SHORT).show();
        }finally{pendingInvoice=null;}
    }

    void googleSync(){
        if(syncBusy)return;
        AuthorizationRequest request=AuthorizationRequest.builder()
            .setRequestedScopes(Collections.singletonList(new Scope(DRIVE_APPDATA_SCOPE)))
            .build();
        Identity.getAuthorizationClient(this).authorize(request)
            .addOnSuccessListener(result->{
                if(result.hasResolution()){
                    try{
                        startIntentSenderForResult(result.getPendingIntent().getIntentSender(),42,null,0,0,0,null);
                    }catch(IntentSender.SendIntentException e){
                        Toast.makeText(this,"Google authorization could not be opened.",Toast.LENGTH_SHORT).show();
                    }
                }else{
                    syncWithDriveToken(result.getAccessToken());
                }
            })
            .addOnFailureListener(e->Toast.makeText(this,"Google sync authorization failed. Check Google/Drive setup.",Toast.LENGTH_LONG).show());
    }

    JSONObject buildSyncPayload() throws Exception{
        JSONObject data=new JSONObject();
        data.put("schema",1);
        data.put("updated_at",prefs.getLong("local_data_updated",System.currentTimeMillis()));
        data.put("transactions",transactions());
        data.put("dues",new JSONArray(prefs.getString("dues_json","[]")));
        return data;
    }

    void syncWithDriveToken(String token){
        if(token==null||token.isEmpty()){Toast.makeText(this,"Google authorization did not return an access token.",Toast.LENGTH_SHORT).show();return;}
        syncBusy=true;
        new Thread(()->{
            try{
                JSONObject local=buildSyncPayload();
                JSONObject cloud=findDriveSyncFile(token);
                if(cloud==null){
                    createDriveSyncFile(token,local);
                    prefs.edit().putBoolean("google_sync_enabled",true).apply();
                    runOnUiThread(()->{syncBusy=false;Toast.makeText(this,"Google sync connected • data uploaded",Toast.LENGTH_SHORT).show();renderCurrent();});
                    return;
                }
                String id=cloud.optString("id","");
                JSONObject remote=downloadDriveSyncFile(token,id);
                long lt=local.optLong("updated_at",0), rt=remote.optLong("updated_at",0);
                if(rt>lt){
                    JSONArray tx=remote.optJSONArray("transactions");
                    JSONArray dues=remote.optJSONArray("dues");
                    prefs.edit()
                        .putString(TX,tx==null?"[]":tx.toString())
                        .putString("dues_json",dues==null?"[]":dues.toString())
                        .putLong("local_data_updated",rt)
                        .putBoolean("google_sync_enabled",true).apply();
                }else if(lt>rt){
                    updateDriveSyncFile(token,id,local);
                    prefs.edit().putBoolean("google_sync_enabled",true).apply();
                }else{
                    prefs.edit().putBoolean("google_sync_enabled",true).apply();
                }
                runOnUiThread(()->{syncBusy=false;Toast.makeText(this,"Google sync complete",Toast.LENGTH_SHORT).show();renderCurrent();});
            }catch(Exception e){
                syncBusy=false;
                runOnUiThread(()->Toast.makeText(this,"Google sync failed: "+e.getMessage(),Toast.LENGTH_LONG).show());
            }
        }).start();
    }

    JSONObject findDriveSyncFile(String token) throws Exception{
        String q=URLEncoder.encode("name='"+SYNC_FILE+"' and 'appDataFolder' in parents and trashed=false","UTF-8");
        String url="https://www.googleapis.com/drive/v3/files?spaces=appDataFolder&q="+q+"&fields=files(id,name,modifiedTime)";
        String body=driveHttp("GET",url,token,null,null);
        JSONObject r=new JSONObject(body); JSONArray files=r.optJSONArray("files");
        return files!=null&&files.length()>0?files.getJSONObject(0):null;
    }

    JSONObject downloadDriveSyncFile(String token,String id) throws Exception{
        String body=driveHttp("GET","https://www.googleapis.com/drive/v3/files/"+URLEncoder.encode(id,"UTF-8")+"?alt=media",token,null,null);
        return new JSONObject(body);
    }

    void createDriveSyncFile(String token,JSONObject data) throws Exception{
        String boundary="PaisalayaanBoundary"+System.currentTimeMillis();
        JSONObject meta=new JSONObject();meta.put("name",SYNC_FILE);meta.put("parents",new JSONArray().put("appDataFolder"));
        String body="--"+boundary+"\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n"+meta.toString()+"\r\n"
            +"--"+boundary+"\r\nContent-Type: application/json\r\n\r\n"+data.toString()+"\r\n--"+boundary+"--";
        driveHttp("POST","https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart",token,body,"multipart/related; boundary="+boundary);
    }

    void updateDriveSyncFile(String token,String id,JSONObject data) throws Exception{
        driveHttp("PATCH","https://www.googleapis.com/upload/drive/v3/files/"+URLEncoder.encode(id,"UTF-8")+"?uploadType=media",token,data.toString(),"application/json");
    }

    String driveHttp(String method,String url,String token,String body,String contentType) throws Exception{
        HttpURLConnection c=(HttpURLConnection)new URL(url).openConnection();
        c.setRequestMethod(method); c.setConnectTimeout(12000); c.setReadTimeout(15000);
        c.setRequestProperty("Authorization","Bearer "+token);
        c.setRequestProperty("Accept","application/json");
        if(body!=null){
            c.setDoOutput(true); c.setRequestProperty("Content-Type",contentType==null?"application/json":contentType);
            OutputStream out=c.getOutputStream();out.write(body.getBytes(StandardCharsets.UTF_8));out.close();
        }
        int code=c.getResponseCode();
        InputStream stream=code>=200&&code<300?c.getInputStream():c.getErrorStream();
        BufferedReader br=new BufferedReader(new InputStreamReader(stream,StandardCharsets.UTF_8));
        StringBuilder sb=new StringBuilder();String line;while((line=br.readLine())!=null)sb.append(line);br.close();c.disconnect();
        if(code<200||code>=300)throw new IOException("Drive HTTP "+code);
        return sb.toString();
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
        LinearLayout syncCard=box(MINT,16);
        syncCard.addView(tv("Google account sync",17,GREEN,true));
        syncCard.addView(tv("Sync your people, dues and transactions across phones using your Google account. Paisa Laya uses Google's private app data area, which is only accessible to this app for your account.",12,INK,false));
        Button syncNow=action("☁  Connect / sync Google account");
        syncNow.setTextColor(WHITE); syncNow.setBackground(bg(GREEN,22));
        LinearLayout.LayoutParams sp1=new LinearLayout.LayoutParams(-1,dp(50)); sp1.setMargins(0,dp(10),0,dp(7)); syncCard.addView(syncNow,sp1);
        Button syncOff=action("Disable Google sync on this device");
        syncOff.setTextColor(GREEN); syncOff.setBackground(bg(WHITE,20));
        syncCard.addView(syncOff,new LinearLayout.LayoutParams(-1,dp(46)));
        TextView syncStatus=tv(prefs.getBoolean("google_sync_enabled",false)?"Google sync is enabled on this device.":"Google sync is not connected.",11,MUTED,false);
        LinearLayout.LayoutParams ssp=new LinearLayout.LayoutParams(-1,-2); ssp.setMargins(0,dp(7),0,0); syncCard.addView(syncStatus,ssp);
        syncNow.setOnClickListener(v->googleSync());
        syncOff.setOnClickListener(v->{prefs.edit().putBoolean("google_sync_enabled",false).apply();Toast.makeText(this,"Google sync disabled on this device.",Toast.LENGTH_SHORT).show();renderCurrent();});
        addWrapMargin(syncCard,0,12);

        addWrap(sectionTitle("Data & reminders"));

        Button reports=action("Reports & Backup"); addWrapMargin(reports,0,8); reports.setOnClickListener(v->showReports());
        Button wa=action("WhatsApp reminders"); addWrapMargin(wa,0,8); wa.setOnClickListener(v->new AlertDialog.Builder(this,isDarkMode()?AlertDialog.THEME_DEVICE_DEFAULT_DARK:AlertDialog.THEME_DEVICE_DEFAULT_LIGHT).setTitle("WhatsApp reminders").setMessage("In People & Dues, choose a person from your phone contacts and tap WhatsApp to prepare a ready-made reminder. Paisa Laya never sends messages automatically.").setPositiveButton("OK",null).show());
        Button about=action("About Paisa Laya"); addWrapMargin(about,0,8); about.setOnClickListener(v->new AlertDialog.Builder(this).setTitle("Paisa Laya").setMessage("Simple personal money tracking, dues, currency conversion and gold-rate tools. Your transaction data is stored locally on this device unless you enable Google account sync. When enabled, Paisa Laya stores its sync data in Google Drive's private app-data area for the authorized Google account. PDF invoices are created on your device and are only shared when you choose to share them.").setPositiveButton("OK",null).show());
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
        info.addView(tv("Use JSON backup to move your Paisa Laya data to another phone. PDF invoices can be created from each person's record.",12,INK,false));
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

    String httpGet(String url) throws Exception{
        java.net.HttpURLConnection conn=null;
        try{
            conn=(java.net.HttpURLConnection)new java.net.URL(url).openConnection();
            conn.setRequestMethod("GET");
            conn.setConnectTimeout(8000);
            conn.setReadTimeout(10000);
            conn.setRequestProperty("User-Agent","Paisa-Laya/1.1");
            int code=conn.getResponseCode();
            if(code<200 || code>=300) throw new IOException("HTTP "+code);
            BufferedReader br=new BufferedReader(new InputStreamReader(conn.getInputStream()));
            StringBuilder s=new StringBuilder(); String line;
            while((line=br.readLine())!=null)s.append(line).append('\n');
            br.close();
            return s.toString();
        }finally{ if(conn!=null) conn.disconnect(); }
    }

    @Override protected void onActivityResult(int req,int res,Intent data){
        super.onActivityResult(req,res,data);
        if(res!=RESULT_OK||data==null)return;
        try{
            if(req==31){
                if(pendingInvoice!=null) writeInvoicePdf(data.getData(),pendingInvoice);
                return;
            }
            if(req==42){
                try{
                    AuthorizationResult ar=Identity.getAuthorizationClient(this).getAuthorizationResultFromIntent(data);
                    if(ar!=null && ar.getAccessToken()!=null) syncWithDriveToken(ar.getAccessToken());
                    else Toast.makeText(this,"Google authorization was cancelled.",Toast.LENGTH_SHORT).show();
                }catch(Exception e){Toast.makeText(this,"Google authorization failed.",Toast.LENGTH_LONG).show();}
                return;
            }
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
