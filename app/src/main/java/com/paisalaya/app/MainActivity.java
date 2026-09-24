package com.paisalaya.app;

import android.app.*;
import android.content.*;
import android.content.res.Configuration;
import android.graphics.*;
import android.graphics.drawable.GradientDrawable;
import android.os.Bundle;
import android.view.*;
import android.view.inputmethod.InputMethodManager;
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

    int BG=Color.rgb(246,248,244), INK=Color.rgb(25,35,29), GREEN=Color.rgb(36,132,83);
    int GREEN_DARK=Color.rgb(18,92,57), MINT=Color.rgb(224,246,232), RED=Color.rgb(216,76,76);
    int GOLD=Color.rgb(238,174,65), MUTED=Color.rgb(92,105,96), WHITE=Color.WHITE;

    int dp(float v){return (int)(v*getResources().getDisplayMetrics().density+0.5f);}

    @Override public void onCreate(Bundle state){
        super.onCreate(state);
        prefs=getSharedPreferences(PREF,0);
        getWindow().setStatusBarColor(GREEN_DARK);
        getWindow().setNavigationBarColor(BG);
        getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR);

        if(state!=null){
            currentScreen=state.getString("screen",SCREEN_HOME);
            pendingType=state.getString("type","Expense");
        }
        renderCurrent();
        if(state!=null && SCREEN_ADD.equals(currentScreen)){
            final String amount=state.getString("amount","");
            final String category=state.getString("category","");
            final String note=state.getString("note","");
            content.postDelayed(()->restoreAddFields(amount,category,note),80);
        }
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

    void renderCurrent(){
        if(SCREEN_ADD.equals(currentScreen)) showAddWithType(pendingType);
        else if(SCREEN_PEOPLE.equals(currentScreen)) showPeople();
        else if(SCREEN_REPORTS.equals(currentScreen)) showReports();
        else showHome();
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
        e.setHint(hint); e.setTextSize(size); e.setSingleLine(true);
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

        String[] icons={"⌂","+","♙","▣"};
        String[] labels={"Home","Add","People","Reports"};
        TextView[] items=new TextView[4];

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
        if(SCREEN_REPORTS.equals(currentScreen))return 3;
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

    void showHome(){
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
        currentScreen=SCREEN_ADD; pendingType=defaultType;
        base("New transaction","Record money in seconds.");
        TextView amountLabel=tv("Amount",13,INK,true); addWrapMargin(amountLabel,0,5);
        EditText amount=new EditText(this); fieldStyle(amount,"Amount in PKR",18); amount.setInputType(2|8192); amount.setTag("amount"); addWrapMargin(amount,0,10);

        TextView typeLabel=tv("Transaction type",13,INK,true); addWrapMargin(typeLabel,0,5);
        Spinner type=new Spinner(this);
        type.setPadding(dp(12),0,dp(8),0); type.setBackground(bg(WHITE,20));
        type.setAdapter(new ArrayAdapter<String>(this,android.R.layout.simple_spinner_dropdown_item,new String[]{"Expense","Income"}));
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
        currentScreen=SCREEN_PEOPLE;
        base("People & Dues","Keep track of borrowed and owed money.");
        addWrapMargin(tv("Add someone you owe or who owes you.",13,MUTED,false),0,10);
        EditText name=new EditText(this); fieldStyle(name,"Person's name",17); addWrapMargin(name,0,10);
        EditText amount=new EditText(this); fieldStyle(amount,"Amount in PKR",17); amount.setInputType(2|8192); addWrapMargin(amount,0,10);
        Spinner kind=new Spinner(this); kind.setPadding(dp(12),0,dp(8),0); kind.setBackground(bg(WHITE,20));
        kind.setAdapter(new ArrayAdapter<String>(this,android.R.layout.simple_spinner_dropdown_item,new String[]{"They owe me","I owe them"})); addWrapMargin(kind,0,10);
        EditText phone=new EditText(this); fieldStyle(phone,"WhatsApp number (e.g. +923001234567)",15); phone.setInputType(3); addWrapMargin(phone,0,10);
        EditText note=new EditText(this); fieldStyle(note,"Note (optional)",17); addWrapMargin(note,0,12);
        Button add=action("Add person  ＋"); addWrapMargin(add,0,12);
        addWrap(sectionTitle("Saved people"));
        LinearLayout listBox=box(WHITE,14); addWrapMargin(listBox,0,8);
        String saved=prefs.getString("dues_json","[]"); JSONArray people=new JSONArray(); try{people=new JSONArray(saved);}catch(Exception ignored){}
        if(people.length()==0) listBox.addView(tv("No people added yet.",13,MUTED,false));
        for(int i=0;i<people.length();i++) addPersonCard(listBox,people.optJSONObject(i),i);
        JSONArray initialPeople=people;
        add.setOnClickListener(v->{
            String n=name.getText().toString().trim(), am=amount.getText().toString().trim();
            if(n.isEmpty()||am.isEmpty()){Toast.makeText(this,"Enter a name and amount.",Toast.LENGTH_SHORT).show();return;}
            try{
                JSONArray a; try{a=new JSONArray(prefs.getString("dues_json","[]"));}catch(Exception e){a=new JSONArray();}
                JSONObject o=new JSONObject();o.put("name",n);o.put("amount",Double.parseDouble(am));o.put("kind",kind.getSelectedItem().toString());o.put("phone",phone.getText().toString().trim());o.put("note",note.getText().toString().trim());a.put(o);
                prefs.edit().putString("dues_json",a.toString()).apply(); showPeople();
            }catch(Exception e){Toast.makeText(this,"Please enter a valid amount.",Toast.LENGTH_SHORT).show();}
        });
        nav();
    }

    void addPersonCard(LinearLayout parent,JSONObject o,int index){
        LinearLayout card=box(MINT,12);
        LinearLayout r=row();
        LinearLayout info=new LinearLayout(this);info.setOrientation(LinearLayout.VERTICAL);
        String kind=o.optString("kind","They owe me"); int col=kind.startsWith("They")?GREEN:RED;
        info.addView(tv(o.optString("name","Person"),16,INK,true));
        info.addView(tv(kind+"  •  "+money(o.optDouble("amount"))+(o.optString("note").isEmpty()?"":"  •  "+o.optString("note")),12,MUTED,false));
        r.addView(info,new LinearLayout.LayoutParams(0,-2,1));
        Button wa=action("WhatsApp");wa.setTextSize(12);wa.setTextColor(GREEN);r.addView(wa,new LinearLayout.LayoutParams(dp(96),dp(44)));
        card.addView(r);
        wa.setOnClickListener(v->whatsappReminder(o));
        parent.addView(card,new LinearLayout.LayoutParams(-1,-2));
        if(index<999)parent.addView(new Space(this),new LinearLayout.LayoutParams(1,dp(7)));
    }

    void whatsappReminder(JSONObject o){
        String phone=o.optString("phone","").replaceAll("[^0-9+]","");
        if(phone.isEmpty()){Toast.makeText(this,"Add a WhatsApp number for this person first.",Toast.LENGTH_SHORT).show();return;}
        String name=o.optString("name","there"), amount=money(o.optDouble("amount")); boolean theyOwe=o.optString("kind","").startsWith("They");
        String msg=theyOwe?"Hi "+name+", just a friendly reminder about the "+amount+" pending amount. Please let me know when you expect to settle it. Thank you!":"Hi "+name+", just a friendly reminder regarding the "+amount+" I need to settle with you. Please let me know if anything is needed from my side. Thank you!";
        try{
            Intent i=new Intent(Intent.ACTION_VIEW,android.net.Uri.parse("https://wa.me/"+phone.replace("+","")+"?text="+java.net.URLEncoder.encode(msg,"UTF-8")));
            startActivity(i);
        }catch(Exception e){Toast.makeText(this,"WhatsApp could not be opened.",Toast.LENGTH_SHORT).show();}
    }

    void showReports(){
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
        clear.setOnClickListener(v->new AlertDialog.Builder(this)
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

    @Override protected void onActivityResult(int req,int res,Intent data){
        super.onActivityResult(req,res,data);
        if(res!=RESULT_OK||data==null)return;
        try{
            if(req==10){
                OutputStream out=getContentResolver().openOutputStream(data.getData());
                JSONObject r=new JSONObject(); r.put("transactions",transactions()); r.put("dues",prefs.getString("dues",""));
                out.write(r.toString().getBytes()); out.close();
                Toast.makeText(this,"Backup saved",Toast.LENGTH_SHORT).show();
            }else if(req==11){
                InputStream in=getContentResolver().openInputStream(data.getData());
                BufferedReader br=new BufferedReader(new InputStreamReader(in));
                StringBuilder s=new StringBuilder(); String line;
                while((line=br.readLine())!=null)s.append(line); br.close();
                JSONObject r=new JSONObject(s.toString()); JSONArray restored=r.optJSONArray("transactions");
                prefs.edit().putString(TX,restored==null?"[]":restored.toString()).putString("dues",r.optString("dues","")).apply();
                showHome();
            }
        }catch(Exception e){Toast.makeText(this,"Could not process the file.",Toast.LENGTH_SHORT).show();}
    }
}
