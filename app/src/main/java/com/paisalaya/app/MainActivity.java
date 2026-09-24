package com.paisalaya.app;

import android.app.*;
import android.content.*;
import android.graphics.*;
import android.graphics.drawable.GradientDrawable;
import android.os.Bundle;
import android.view.*;
import android.widget.*;
import org.json.*;
import java.io.*;
import java.text.SimpleDateFormat;
import java.util.*;

public class MainActivity extends Activity {
    static final String PREF="paisa_laya", TX="transactions";
    LinearLayout root, content;
    SharedPreferences prefs;
    final int BG=Color.rgb(246,248,244), INK=Color.rgb(25,35,29), GREEN=Color.rgb(36,132,83);
    final int MINT=Color.rgb(224,246,232), RED=Color.rgb(216,76,76), GOLD=Color.rgb(238,174,65), WHITE=Color.WHITE;

    int dp(float v){return (int)(v*getResources().getDisplayMetrics().density+0.5f);}

    @Override public void onCreate(Bundle b){
        super.onCreate(b);
        prefs=getSharedPreferences(PREF,0);
        getWindow().setStatusBarColor(Color.rgb(18,92,57));
        getWindow().setNavigationBarColor(BG);
        getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR);
        showHome();
    }

    TextView tv(String s,float z,int c,boolean bold){
        TextView t=new TextView(this);
        t.setText(s); t.setTextSize(z); t.setTextColor(c);
        t.setPadding(dp(4),dp(2),dp(4),dp(2));
        if(bold)t.setTypeface(Typeface.DEFAULT,Typeface.BOLD);
        return t;
    }

    GradientDrawable bg(int color,float radius){
        GradientDrawable g=new GradientDrawable(); g.setColor(color); g.setCornerRadius(dp(radius)); return g;
    }

    LinearLayout box(int color,int pad){
        LinearLayout l=new LinearLayout(this); l.setOrientation(LinearLayout.VERTICAL);
        l.setPadding(dp(pad),dp(pad),dp(pad),dp(pad)); l.setBackground(bg(color,32)); return l;
    }

    Button action(String s){
        Button b=new Button(this);
        b.setText(s); b.setTextSize(14); b.setAllCaps(false); b.setTextColor(INK);
        b.setBackground(bg(WHITE,28)); b.setPadding(dp(12),0,dp(12),0);
        b.setMinHeight(0); b.setMinWidth(0); b.setStateListAnimator(null);
        return b;
    }

    void fieldStyle(EditText e,String hint,float size){
        e.setHint(hint); e.setTextSize(size); e.setSingleLine(true);
        e.setPadding(dp(18),0,dp(18),0); e.setBackground(bg(WHITE,24));
        e.setGravity(Gravity.CENTER_VERTICAL); e.setMinHeight(dp(56));
    }

    void base(String title,String subtitle){
        root=new LinearLayout(this); root.setOrientation(LinearLayout.VERTICAL); root.setBackgroundColor(BG);
        LinearLayout head=new LinearLayout(this); head.setOrientation(LinearLayout.VERTICAL);
        head.setPadding(dp(18),dp(18),dp(18),dp(6));
        head.addView(tv(title,28,INK,true),new LinearLayout.LayoutParams(-1,dp(58)));
        head.addView(tv(subtitle,15,Color.rgb(92,105,96),false),new LinearLayout.LayoutParams(-1,dp(34)));
        root.addView(head,new LinearLayout.LayoutParams(-1,dp(100)));

        content=new LinearLayout(this); content.setOrientation(LinearLayout.VERTICAL);
        content.setPadding(dp(16),dp(4),dp(16),dp(18));
        ScrollView sv=new ScrollView(this); sv.setFillViewport(true); sv.setClipToPadding(false); sv.addView(content);
        root.addView(sv,new LinearLayout.LayoutParams(-1,0,1));
        setContentView(root);
        content.setAlpha(0f); content.animate().alpha(1f).setDuration(380).start();
    }

    void add(LinearLayout l,View v,int h){l.addView(v,new LinearLayout.LayoutParams(-1,dp(h)));}

    void nav(){
        LinearLayout n=new LinearLayout(this);
        n.setGravity(Gravity.CENTER); n.setPadding(dp(6),dp(6),dp(6),dp(8));
        n.setBackground(bg(WHITE,30));
        String[] icons={"⌂","+","♙","▣"};
        String[] labels={"Home","Add","People","Reports"};
        TextView[] items=new TextView[4];

        for(int i=0;i<4;i++){
            TextView item=new TextView(this);
            item.setText(icons[i]+"\n"+labels[i]);
            item.setTextSize(12); item.setTextColor(INK); item.setGravity(Gravity.CENTER);
            item.setLineSpacing(0,0.9f); item.setBackground(bg(WHITE,24));
            item.setPadding(0,0,0,0);
            items[i]=item;
            LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(0,dp(64),1);
            if(i>0)p.setMargins(dp(4),0,0,0);
            n.addView(item,p);
        }

        items[0].setOnClickListener(v->showHome());
        items[1].setOnClickListener(v->showAdd());
        items[2].setOnClickListener(v->showPeople());
        items[3].setOnClickListener(v->showReports());
        root.addView(n,new LinearLayout.LayoutParams(-1,dp(76)));
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
        base("Paisa Laya","Your money, beautifully organized.");
        double[] t=totals(); double balance=t[0]-t[1];

        LinearLayout hero=box(GREEN,22);
        hero.addView(tv("TOTAL BALANCE",12,Color.rgb(207,240,218),true),new LinearLayout.LayoutParams(-1,dp(28)));
        hero.addView(tv(money(balance),32,WHITE,true),new LinearLayout.LayoutParams(-1,dp(60)));

        LinearLayout row=new LinearLayout(this); row.setPadding(0,dp(8),0,0);
        LinearLayout inc=box(Color.rgb(53,151,99),14);
        inc.addView(tv("↗  INCOME",11,Color.rgb(210,244,222),true),new LinearLayout.LayoutParams(-1,dp(28)));
        inc.addView(tv(money(t[0]),17,WHITE,true),new LinearLayout.LayoutParams(-1,dp(40)));

        LinearLayout exp=box(Color.rgb(194,70,70),14);
        exp.addView(tv("↘  EXPENSE",11,Color.rgb(255,220,220),true),new LinearLayout.LayoutParams(-1,dp(28)));
        exp.addView(tv(money(t[1]),17,WHITE,true),new LinearLayout.LayoutParams(-1,dp(40)));

        row.addView(inc,new LinearLayout.LayoutParams(0,dp(104),1));
        LinearLayout.LayoutParams ep=new LinearLayout.LayoutParams(0,dp(104),1); ep.setMargins(dp(10),0,0,0); row.addView(exp,ep);
        hero.addView(row);
        add(content,hero,174);

        LinearLayout quick=new LinearLayout(this); quick.setPadding(0,dp(12),0,dp(6));
        Button add=action("＋  Add expense"), income=action("＋  Add income");
        quick.addView(add,new LinearLayout.LayoutParams(0,dp(52),1));
        LinearLayout.LayoutParams ip=new LinearLayout.LayoutParams(0,dp(52),1); ip.setMargins(dp(10),0,0,0); quick.addView(income,ip);
        add.setOnClickListener(v->showAddWithType("Expense")); income.setOnClickListener(v->showAddWithType("Income"));
        content.addView(quick,new LinearLayout.LayoutParams(-1,dp(70)));

        content.addView(tv("Spending overview",19,INK,true),new LinearLayout.LayoutParams(-1,dp(42)));
        LinearLayout chart=box(WHITE,18);
        double total=t[0]+t[1]; float er=total==0?0:(float)(t[1]/total);
        chart.addView(tv("Expenses",13,Color.DKGRAY,false),new LinearLayout.LayoutParams(-1,dp(30)));
        ProgressBar pb=new ProgressBar(this,null,android.R.attr.progressBarStyleHorizontal);
        pb.setMax(100); pb.setProgress((int)(er*100)); pb.setProgressDrawable(bg(RED,20));
        chart.addView(pb,new LinearLayout.LayoutParams(-1,dp(16)));
        chart.addView(tv(total==0?"No transactions yet":String.format(Locale.US,"%.0f%% of recorded cash flow is expenses",er*100),13,Color.DKGRAY,false),new LinearLayout.LayoutParams(-1,dp(30)));
        add(content,chart,108);

        content.addView(tv("Recent transactions",19,INK,true),new LinearLayout.LayoutParams(-1,dp(42)));
        JSONArray a=transactions(); int start=Math.max(0,a.length()-5);
        if(a.length()==0)content.addView(tv("No transactions yet. Tap Add to get started.",14,Color.DKGRAY,false),new LinearLayout.LayoutParams(-1,dp(38)));

        for(int i=a.length()-1;i>=start;i--)try{
            JSONObject o=a.getJSONObject(i);
            LinearLayout card=box(WHITE,14);
            String icon="Income".equals(o.getString("type"))?"↗":"↘";
            int c="Income".equals(o.getString("type"))?GREEN:RED;
            LinearLayout rr=new LinearLayout(this); rr.setGravity(Gravity.CENTER_VERTICAL);
            rr.addView(tv(icon,24,c,true),new LinearLayout.LayoutParams(dp(48),dp(62)));
            LinearLayout info=new LinearLayout(this); info.setOrientation(LinearLayout.VERTICAL);
            info.addView(tv(o.optString("category","Other"),15,INK,true));
            info.addView(tv(o.optString("note","No note")+"  •  "+o.optString("date",""),12,Color.DKGRAY,false));
            rr.addView(info,new LinearLayout.LayoutParams(0,dp(62),1));
            rr.addView(tv(money(o.optDouble("amount")),14,c,true),new LinearLayout.LayoutParams(-2,dp(62)));
            card.addView(rr); add(content,card,90);
            Space sp=new Space(this); content.addView(sp,new LinearLayout.LayoutParams(1,dp(7)));
        }catch(Exception e){}
        nav();
    }

    void showAdd(){showAddWithType("Expense");}

    void showAddWithType(String defaultType){
        base("New transaction","Record money in seconds.");
        EditText amount=new EditText(this); fieldStyle(amount,"Amount in PKR",18); amount.setInputType(2|8192); add(content,amount,60);

        Spinner type=new Spinner(this);
        type.setAdapter(new ArrayAdapter<String>(this,android.R.layout.simple_spinner_dropdown_item,new String[]{"Expense","Income"}));
        type.setSelection("Income".equals(defaultType)?1:0);
        add(content,type,56);

        EditText cat=new EditText(this); fieldStyle(cat,"Category  •  Food, Salary, Bills...",17); add(content,cat,60);
        EditText note=new EditText(this); fieldStyle(note,"Short note",17); add(content,note,60);

        Button saveB=action("Save transaction  →"); saveB.setTextSize(16); saveB.setTextColor(WHITE); saveB.setBackground(bg(GREEN,26)); add(content,saveB,58);
        saveB.setOnClickListener(v->{
            try{
                double x=Double.parseDouble(amount.getText().toString().trim()); if(x<=0)throw new Exception();
                JSONArray a=transactions(); JSONObject o=new JSONObject();
                o.put("amount",x); o.put("type",type.getSelectedItem().toString());
                o.put("category",cat.getText().toString().trim().isEmpty()?"Other":cat.getText().toString().trim());
                o.put("note",note.getText().toString().trim());
                o.put("date",new SimpleDateFormat("dd MMM, HH:mm",Locale.US).format(new Date()));
                a.put(o); save(a); showHome();
            }catch(Exception e){Toast.makeText(this,"Please enter a valid amount.",Toast.LENGTH_SHORT).show();}
        });
        nav();
    }

    void showPeople(){
        base("People & Dues","Keep track of borrowed and owed money.");
        EditText name=new EditText(this); fieldStyle(name,"Person's name",17); add(content,name,60);
        EditText amount=new EditText(this); fieldStyle(amount,"Amount in PKR",17); amount.setInputType(2|8192); add(content,amount,60);
        Spinner kind=new Spinner(this); kind.setAdapter(new ArrayAdapter<String>(this,android.R.layout.simple_spinner_dropdown_item,new String[]{"They owe me","I owe them"})); add(content,kind,56);
        EditText note=new EditText(this); fieldStyle(note,"Note",17); add(content,note,60);
        Button add=action("Add person  ＋"); add(content,add,56);
        TextView list=tv("",14,INK,false); content.addView(list); list.setText(prefs.getString("dues",""));
        add.setOnClickListener(v->{
            if(name.getText().toString().trim().isEmpty())return;
            String line="• "+name.getText()+"  —  "+kind.getSelectedItem()+"  —  PKR "+amount.getText()+"  —  "+note.getText()+"\n";
            String all=prefs.getString("dues","")+line; prefs.edit().putString("dues",all).apply();
            list.setText(all); name.setText(""); amount.setText(""); note.setText("");
        });
        nav();
    }

    void showReports(){
        base("Reports & Backup","Export or protect your Paisa Laya data.");
        LinearLayout c=box(WHITE,18); c.addView(tv("Data tools",18,INK,true));
        Button csv=action("⇩  Export transactions as CSV"), backup=action("☁  Create JSON backup"), restore=action("↥  Restore JSON backup");
        c.addView(csv,new LinearLayout.LayoutParams(-1,dp(54))); c.addView(backup,new LinearLayout.LayoutParams(-1,dp(54))); c.addView(restore,new LinearLayout.LayoutParams(-1,dp(54)));
        add(content,c,210);
        Button clear=action("Clear all transactions"); clear.setTextColor(RED); add(content,clear,56);
        csv.setOnClickListener(v->exportCsv()); backup.setOnClickListener(v->backup()); restore.setOnClickListener(v->restore());
        clear.setOnClickListener(v->new AlertDialog.Builder(this).setTitle("Clear transactions?").setMessage("This cannot be undone.").setNegativeButton("Cancel",null).setPositiveButton("Clear",(d,w)->{prefs.edit().remove(TX).apply();showReports();}).show());
        nav();
    }

    void exportCsv(){
        StringBuilder s=new StringBuilder("Date,Type,Category,Amount,Note\n"); JSONArray a=transactions();
        try{for(int i=0;i<a.length();i++){JSONObject o=a.getJSONObject(i);s.append(o.optString("date")).append(",").append(o.optString("type")).append(",").append(o.optString("category")).append(",").append(o.optDouble("amount")).append(",").append(o.optString("note").replace(","," ")).append("\n");}}catch(Exception e){}
        Intent in=new Intent(Intent.ACTION_SEND); in.setType("text/csv"); in.putExtra(Intent.EXTRA_TEXT,s.toString()); startActivity(Intent.createChooser(in,"Share CSV"));
    }

    void backup(){Intent in=new Intent(Intent.ACTION_CREATE_DOCUMENT); in.setType("application/json"); in.putExtra(Intent.EXTRA_TITLE,"paisa-laya-backup.json"); startActivityForResult(in,10);}
    void restore(){Intent in=new Intent(Intent.ACTION_OPEN_DOCUMENT); in.setType("application/json"); in.addCategory(Intent.CATEGORY_OPENABLE); startActivityForResult(in,11);}

    @Override protected void onActivityResult(int req,int res,Intent data){
        super.onActivityResult(req,res,data); if(res!=RESULT_OK||data==null)return;
        try{
            if(req==10){
                OutputStream out=getContentResolver().openOutputStream(data.getData());
                JSONObject r=new JSONObject(); r.put("transactions",transactions()); r.put("dues",prefs.getString("dues",""));
                out.write(r.toString().getBytes()); out.close(); Toast.makeText(this,"Backup saved",Toast.LENGTH_SHORT).show();
            }else if(req==11){
                InputStream in=getContentResolver().openInputStream(data.getData()); BufferedReader br=new BufferedReader(new InputStreamReader(in));
                StringBuilder s=new StringBuilder(); String line; while((line=br.readLine())!=null)s.append(line); br.close();
                JSONObject r=new JSONObject(s.toString()); JSONArray restored=r.optJSONArray("transactions");
                prefs.edit().putString(TX,restored==null?"[]":restored.toString()).putString("dues",r.optString("dues","")).apply(); showHome();
            }
        }catch(Exception e){Toast.makeText(this,"Could not process the file.",Toast.LENGTH_SHORT).show();}
    }
}
