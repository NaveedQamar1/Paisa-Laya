package com.paisalaya.app;

import android.app.*;
import android.content.*;
import android.graphics.Color;
import android.graphics.Typeface;
import android.net.Uri;
import android.os.Bundle;
import android.provider.Settings;
import android.view.*;
import android.widget.*;
import org.json.*;

import java.io.*;
import java.text.SimpleDateFormat;
import java.util.*;

public class MainActivity extends Activity {
    static final String PREF = "paisa_laya";
    static final String TX = "transactions";
    LinearLayout root, content;
    SharedPreferences prefs;
    int green = Color.rgb(47,125,80), cream = Color.rgb(247,245,239), dark = Color.rgb(35,45,38);

    @Override public void onCreate(Bundle b) {
        super.onCreate(b);
        prefs = getSharedPreferences(PREF, MODE_PRIVATE);
        showHome();
    }

    TextView tv(String s, float size, int color, boolean bold) {
        TextView t = new TextView(this); t.setText(s); t.setTextSize(size); t.setTextColor(color);
        t.setPadding(18,12,18,12); if(bold)t.setTypeface(Typeface.DEFAULT,Typeface.BOLD); return t;
    }
    Button btn(String s) {
        Button b = new Button(this); b.setText(s); b.setAllCaps(false); b.setTextColor(dark);
        return b;
    }
    void base(String title) {
        root = new LinearLayout(this); root.setOrientation(LinearLayout.VERTICAL); root.setBackgroundColor(cream);
        TextView head=tv(title,24,dark,true); head.setPadding(20,28,20,18); root.addView(head);
        content=new LinearLayout(this); content.setOrientation(LinearLayout.VERTICAL);
        ScrollView sv=new ScrollView(this); sv.addView(content); root.addView(sv,new LinearLayout.LayoutParams(-1,0,1));
        setContentView(root);
    }
    void nav() {
        LinearLayout n=new LinearLayout(this); n.setPadding(6,4,6,6);
        Button h=btn("Home"), a=btn("Add"), p=btn("People"), r=btn("Reports");
        n.addView(h,new LinearLayout.LayoutParams(0,-2,1)); n.addView(a,new LinearLayout.LayoutParams(0,-2,1));
        n.addView(p,new LinearLayout.LayoutParams(0,-2,1)); n.addView(r,new LinearLayout.LayoutParams(0,-2,1));
        h.setOnClickListener(v->showHome()); a.setOnClickListener(v->showAdd()); p.setOnClickListener(v->showPeople()); r.setOnClickListener(v->showReports());
        root.addView(n);
    }

    JSONArray transactions() {
        try { return new JSONArray(prefs.getString(TX,"[]")); } catch(Exception e){return new JSONArray();}
    }
    void save(JSONArray a){prefs.edit().putString(TX,a.toString()).apply();}

    void showHome() {
        base("Paisa Laya");
        JSONArray a=transactions(); double income=0,expense=0;
        for(int i=0;i<a.length();i++) try{JSONObject o=a.getJSONObject(i); double x=o.getDouble("amount"); if(o.getString("type").equals("Income"))income+=x;else expense+=x;}catch(Exception ignored){}
        content.addView(tv("Your money, simply managed.",15,Color.DKGRAY,false));
        LinearLayout card=new LinearLayout(this); card.setOrientation(LinearLayout.VERTICAL); card.setPadding(22,18,22,18);
        card.setBackgroundColor(Color.WHITE);
        card.addView(tv("Balance",14,Color.DKGRAY,false)); card.addView(tv(String.format(Locale.US,"PKR %,.0f",income-expense),30,dark,true));
        card.addView(tv(String.format(Locale.US,"Income  PKR %,.0f    •    Expense  PKR %,.0f",income,expense),14,Color.DKGRAY,false));
        content.addView(card,new LinearLayout.LayoutParams(-1,-2));
        content.addView(tv("Recent transactions",19,dark,true));
        int start=Math.max(0,a.length()-6);
        for(int i=a.length()-1;i>=start;i--) try{
            JSONObject o=a.getJSONObject(i);
            content.addView(tv(o.getString("category")+"  •  "+o.getString("note")+"\n"+o.getString("type")+"  PKR "+String.format(Locale.US,"%,.0f",o.getDouble("amount"))+"  •  "+o.getString("date"),15,dark,false));
        }catch(Exception ignored){}
        nav();
    }

    void showAdd() {
        base("Add transaction");
        EditText amount=new EditText(this); amount.setHint("Amount (PKR)"); amount.setInputType(2|8192); content.addView(amount);
        Spinner type=new Spinner(this); type.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,new String[]{"Expense","Income"})); content.addView(type);
        EditText cat=new EditText(this); cat.setHint("Category (Food, Salary, Bills...)"); content.addView(cat);
        EditText note=new EditText(this); note.setHint("Note / description"); content.addView(note);
        Button saveB=btn("Save transaction"); content.addView(saveB);
        saveB.setOnClickListener(v->{
            try {
                double x=Double.parseDouble(amount.getText().toString().trim());
                if(x<=0)throw new Exception();
                JSONArray a=transactions(); JSONObject o=new JSONObject();
                o.put("amount",x); o.put("type",type.getSelectedItem().toString());
                o.put("category",cat.getText().toString().trim().isEmpty()?"Other":cat.getText().toString().trim());
                o.put("note",note.getText().toString().trim());
                o.put("date",new SimpleDateFormat("yyyy-MM-dd HH:mm",Locale.US).format(new Date()));
                a.put(o); save(a); Toast.makeText(this,"Saved",Toast.LENGTH_SHORT).show(); showHome();
            } catch(Exception e){Toast.makeText(this,"Please enter a valid amount.",Toast.LENGTH_SHORT).show();}
        });
        nav();
    }

    void showPeople() {
        base("People & Dues");
        content.addView(tv("Track who owes you and who you owe.",15,Color.DKGRAY,false));
        EditText name=new EditText(this); name.setHint("Person"); content.addView(name);
        EditText amount=new EditText(this); amount.setHint("Amount (PKR)"); amount.setInputType(2|8192); content.addView(amount);
        Spinner kind=new Spinner(this); kind.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,new String[]{"They owe me","I owe them"})); content.addView(kind);
        EditText note=new EditText(this); note.setHint("Note"); content.addView(note);
        Button add=btn("Add due"); content.addView(add);
        TextView list=tv("",15,dark,false); content.addView(list);
        String saved=prefs.getString("dues",""); list.setText(saved);
        add.setOnClickListener(v->{
            if(name.getText().toString().trim().isEmpty())return;
            String line=name.getText()+" — "+kind.getSelectedItem()+" — PKR "+amount.getText()+" — "+note.getText()+"\n";
            String all=prefs.getString("dues","")+line; prefs.edit().putString("dues",all).apply(); list.setText(all);
            name.setText(""); amount.setText(""); note.setText("");
        });
        nav();
    }

    void showReports() {
        base("Reports & Backup");
        Button csv=btn("Export transactions as CSV"); content.addView(csv);
        Button backup=btn("Backup data (JSON)"); content.addView(backup);
        Button restore=btn("Restore data (JSON)"); content.addView(restore);
        Button clear=btn("Clear all transaction data"); content.addView(clear);
        csv.setOnClickListener(v->exportCsv());
        backup.setOnClickListener(v->backup());
        restore.setOnClickListener(v->restore());
        clear.setOnClickListener(v->{new AlertDialog.Builder(this).setTitle("Clear transactions?").setMessage("This cannot be undone.").setNegativeButton("Cancel",null).setPositiveButton("Clear",(d,w)->{prefs.edit().remove(TX).apply();showReports();}).show();});
        nav();
    }

    void exportCsv(){
        StringBuilder s=new StringBuilder("Date,Type,Category,Amount,Note\n"); JSONArray a=transactions();
        try{for(int i=0;i<a.length();i++){JSONObject o=a.getJSONObject(i);s.append(o.optString("date")).append(",").append(o.optString("type")).append(",").append(o.optString("category")).append(",").append(o.optDouble("amount")).append(",").append(o.optString("note").replace(","," ")).append("\n");}}catch(Exception ignored){}
        Intent in=new Intent(Intent.ACTION_SEND); in.setType("text/csv"); in.putExtra(Intent.EXTRA_TEXT,s.toString()); startActivity(Intent.createChooser(in,"Share CSV"));
    }
    void backup(){
        Intent in=new Intent(Intent.ACTION_CREATE_DOCUMENT); in.setType("application/json"); in.putExtra(Intent.EXTRA_TITLE,"paisa-laya-backup.json"); startActivityForResult(in,10);
    }
    void restore(){
        Intent in=new Intent(Intent.ACTION_OPEN_DOCUMENT); in.setType("application/json"); in.addCategory(Intent.CATEGORY_OPENABLE); startActivityForResult(in,11);
    }
    @Override protected void onActivityResult(int req,int res,Intent data){
        super.onActivityResult(req,res,data); if(res!=RESULT_OK||data==null)return;
        try{
            if(req==10){OutputStream out=getContentResolver().openOutputStream(data.getData()); JSONObject root=new JSONObject();root.put("transactions",transactions());root.put("dues",prefs.getString("dues",""));out.write(root.toString().getBytes());out.close();Toast.makeText(this,"Backup saved",Toast.LENGTH_SHORT).show();}
            if(req==11){InputStream in=getContentResolver().openInputStream(data.getData());BufferedReader br=new BufferedReader(new InputStreamReader(in));StringBuilder s=new StringBuilder();String line;while((line=br.readLine())!=null)s.append(line);br.close();JSONObject root=new JSONObject(s.toString());prefs.edit().putString(TX,root.optJSONArray("transactions").toString()).putString("dues",root.optString("dues","")).apply();Toast.makeText(this,"Backup restored",Toast.LENGTH_SHORT).show();showHome();}
        }catch(Exception e){Toast.makeText(this,"Could not process the file.",Toast.LENGTH_SHORT).show();}
    }
}
