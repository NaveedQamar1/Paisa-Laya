package com.easycopy.app;

import android.app.*;
import android.content.*;
import android.graphics.*;
import android.graphics.pdf.PdfDocument;
import android.net.Uri;
import android.os.*;
import android.provider.MediaStore;
import android.print.*;
import android.view.*;
import android.widget.*;
import java.io.*;
import java.text.SimpleDateFormat;
import java.util.*;
import java.util.concurrent.*;

public class MainActivity extends Activity {
    private ImageView frontPreview, backPreview;
    private Uri frontUri, backUri;
    private EditText copiesEdit, ipEdit;
    private Spinner dpiSpinner,colorSpinner,sourceSpinner;
    private TextView status,scannerStatus;
    private LinearLayout devices;
    private ExecutorService pool=Executors.newFixedThreadPool(2);
    private File pendingCopy;

    int dp(float x){return (int)(x*getResources().getDisplayMetrics().density+.5f);}
    TextView tv(String s,float z){TextView t=new TextView(this);t.setText(s);t.setTextSize(z);t.setTextColor(Color.rgb(24,32,51));t.setPadding(0,dp(5),0,dp(5));return t;}
    Button btn(String s){Button b=new Button(this);b.setText(s);b.setAllCaps(false);return b;}
    LinearLayout card(){LinearLayout l=new LinearLayout(this);l.setOrientation(LinearLayout.VERTICAL);l.setPadding(dp(16),dp(12),dp(16),dp(12));GradientDrawable g=new GradientDrawable();g.setColor(Color.WHITE);g.setCornerRadius(dp(18));l.setBackground(g);return l;}
    @Override public void onCreate(Bundle b){super.onCreate(b);getWindow().setStatusBarColor(Color.rgb(247,248,252));build();}

    void build(){
        ScrollView sc=new ScrollView(this);sc.setBackgroundColor(Color.rgb(247,248,252));
        LinearLayout root=new LinearLayout(this);root.setOrientation(LinearLayout.VERTICAL);root.setPadding(dp(16),dp(10),dp(16),dp(24));
        TextView title=tv("EasyCopy",32);title.setTypeface(null,Typeface.BOLD);title.setTextColor(Color.rgb(55,48,163));root.addView(title);
        TextView sub=tv("Smart network scanner • CNIC copier • PDF",14);sub.setTextColor(Color.rgb(102,112,133));root.addView(sub);

        LinearLayout net=card(); TextView nt=tv("Network scanner",20);nt.setTypeface(null,Typeface.BOLD);net.addView(nt);
        scannerStatus=tv("Searching for scanners on this Wi‑Fi network…",13);scannerStatus.setTextColor(Color.rgb(102,112,133));net.addView(scannerStatus);
        devices=new LinearLayout(this);devices.setOrientation(LinearLayout.VERTICAL);net.addView(devices);
        LinearLayout iprow=new LinearLayout(this);iprow.setGravity(Gravity.CENTER_VERTICAL);
        ipEdit=new EditText(this);ipEdit.setHint("Scanner IP address");ipEdit.setSingleLine(true);ipEdit.setInputType(33);iprow.addView(ipEdit,new LinearLayout.LayoutParams(0,dp(52),1));
        Button add=btn("Add");iprow.addView(add,new LinearLayout.LayoutParams(dp(80),dp(52)));net.addView(iprow);
        Button rescan=btn("↻  Find scanners again");net.addView(rescan);
        root.addView(net,new LinearLayout.LayoutParams(-1,-2));

        LinearLayout set=card(); TextView st=tv("Scan settings",20);st.setTypeface(null,Typeface.BOLD);set.addView(st);
        LinearLayout row1=new LinearLayout(this);dpiSpinner=spinner(new String[]{"150 DPI","200 DPI","300 DPI","600 DPI"});colorSpinner=spinner(new String[]{"Color","Grayscale","Black & White"});row1.addView(dpiSpinner,new LinearLayout.LayoutParams(0,dp(55),1));row1.addView(colorSpinner,new LinearLayout.LayoutParams(0,dp(55),1));set.addView(row1);
        sourceSpinner=spinner(new String[]{"Platen / Glass","Feeder","Duplex ADF"});set.addView(sourceSpinner,new LinearLayout.LayoutParams(-1,dp(55)));
        root.addView(set,new LinearLayout.LayoutParams(-1,-2));

        LinearLayout id=card();TextView it=tv("CNIC copy",20);it.setTypeface(null,Typeface.BOLD);id.addView(it);
        TextView hint=tv("Scan or import FRONT and BACK. EasyCopy places matching sides in an A4 2 × 4 layout.",13);hint.setTextColor(Color.rgb(102,112,133));id.addView(hint);
        LinearLayout sides=new LinearLayout(this);sides.setOrientation(LinearLayout.HORIZONTAL);
        LinearLayout f=side("FRONT",true), b=side("BACK",false);sides.addView(f,new LinearLayout.LayoutParams(0,dp(180),1));sides.addView(b,new LinearLayout.LayoutParams(0,dp(180),1));id.addView(sides);
        LinearLayout copies=new LinearLayout(this);copies.setGravity(Gravity.CENTER_VERTICAL);copies.addView(tv("Complete copies",15),new LinearLayout.LayoutParams(0,dp(50),1));copiesEdit=new EditText(this);copiesEdit.setText("1");copiesEdit.setInputType(2);copiesEdit.setSelectAllOnFocus(true);copies.addView(copiesEdit,new LinearLayout.LayoutParams(dp(90),dp(52)));id.addView(copies);
        CheckBox gray=new CheckBox(this);gray.setText("Economical grayscale output");gray.setId(9001);id.addView(gray);
        root.addView(id,new LinearLayout.LayoutParams(-1,-2));

        LinearLayout actions=card();TextView at=tv("Output",20);at.setTypeface(null,Typeface.BOLD);actions.addView(at);
        Button pdf=btn("Create PDF preview"),save=btn("Save PDF"),print=btn("Print • A4 Duplex"),share=btn("Share PDF");
        actions.addView(pdf);actions.addView(save);actions.addView(print);actions.addView(share);root.addView(actions,new LinearLayout.LayoutParams(-1,-2));
        status=tv("Ready. Connect a network scanner or import images.",13);status.setTextColor(Color.rgb(102,112,133));root.addView(status);
        sc.addView(root);setContentView(sc);

        pdf.setOnClickListener(v->safePdf());save.setOnClickListener(v->savePdf());print.setOnClickListener(v->printPdf());share.setOnClickListener(v->sharePdf());
        add.setOnClickListener(v->manualAdd());rescan.setOnClickListener(v->discover());
        discover();
    }
    Spinner spinner(String[] a){Spinner s=new Spinner(this);ArrayAdapter<String>x=new ArrayAdapter<String>(this,android.R.layout.simple_spinner_dropdown_item,a);s.setAdapter(x);return s;}
    LinearLayout side(String name,boolean front){
        LinearLayout l=card();l.setPadding(dp(8),dp(6),dp(8),dp(6));TextView t=tv(name,15);t.setTypeface(null,Typeface.BOLD);l.addView(t);
        ImageView p=new ImageView(this);p.setBackgroundColor(Color.rgb(239,241,246));p.setScaleType(ImageView.ScaleType.CENTER_INSIDE);if(front)frontPreview=p;else backPreview=p;l.addView(p,new LinearLayout.LayoutParams(-1,dp(70)));
        Button scan=btn("Scan"),imp=btn("Import");LinearLayout r=new LinearLayout(this);r.addView(scan,new LinearLayout.LayoutParams(0,dp(48),1));r.addView(imp,new LinearLayout.LayoutParams(0,dp(48),1));l.addView(r);
        scan.setOnClickListener(v->scanSide(front));imp.setOnClickListener(v->pick(front));return l;
    }
    void discover(){
        devices.removeAllViews();scannerStatus.setText("Searching…");
        NetworkScanner ns=new NetworkScanner(this);ns.discover(new NetworkScanner.Listener(){
            public void onDevice(String name,String url){runOnUiThread(()->addDevice(name,url));}
            public void onDone(){runOnUiThread(()->{if(devices.getChildCount()==0)scannerStatus.setText("No compatible eSCL scanner found. You can add its IP manually.");});}
            public void onError(String m){runOnUiThread(()->scannerStatus.setText(m));}
        });
    }
    void addDevice(String name,String url){
        scannerStatus.setText("Scanner available");Button b=btn("●  "+name+"   "+url);b.setGravity(Gravity.LEFT|Gravity.CENTER_VERTICAL);b.setOnClickListener(v->{selectedScanner=url;scannerStatus.setText("Connected: "+name);});
        devices.addView(b);
        if(selectedScanner==null)selectedScanner=url;
    }
    String selectedScanner;
    void manualAdd(){String ip=ipEdit.getText().toString().trim();if(ip.isEmpty()){toast("Enter the scanner IP address.");return;}selectedScanner=(ip.startsWith("http")?ip:"http://"+ip+":80/eSCL/");scannerStatus.setText("Manual scanner selected: "+selectedScanner);}
    void pick(boolean front){Intent i=new Intent(Intent.ACTION_OPEN_DOCUMENT);i.addCategory(Intent.CATEGORY_OPENABLE);i.setType("image/*");startActivityForResult(i,front?101:102);}
    @Override protected void onActivityResult(int r,int c,Intent d){super.onActivityResult(r,c,d);if(c!=RESULT_OK||d==null||d.getData()==null)return;Uri u=d.getData();if(r==101){frontUri=u;frontPreview.setImageURI(u);status.setText("Front loaded. Now scan/import the back.");}else if(r==102){backUri=u;backPreview.setImageURI(u);status.setText("Front and back loaded.");}else if(r==105&&pendingCopy!=null){try(OutputStream o=getContentResolver().openOutputStream(d.getData());InputStream in=new FileInputStream(pendingCopy)){byte[] b=new byte[8192];int n;while((n=in.read(b))>0)o.write(b,0,n);status.setText("PDF saved.");}catch(Exception e){toast(e.getMessage());}}}
    void scanSide(boolean front){
        if(selectedScanner==null){toast("Connect to a network scanner first.");return;}
        status.setText("Scanning "+(front?"front":"back")+" from network scanner…");
        int dpi=new int[]{150,200,300,600}[dpiSpinner.getSelectedItemPosition()];
        String color=new String[]{"RGB24","Grayscale8","BlackAndWhite1"}[colorSpinner.getSelectedItemPosition()];
        boolean duplex=sourceSpinner.getSelectedItemPosition()==2;
        pool.execute(()->{try{byte[] data=NetworkScanner.scan(selectedScanner,dpi,color,duplex);File f=new File(getCacheDir(),"scan_"+System.currentTimeMillis()+".jpg");try(FileOutputStream o=new FileOutputStream(f)){o.write(data);}Uri u=Uri.fromFile(f);runOnUiThread(()->{if(front){frontUri=u;frontPreview.setImageURI(u);}else{backUri=u;backPreview.setImageURI(u);}status.setText((front?"Front":"Back")+" scanned successfully.");});}catch(Exception e){runOnUiThread(()->toast("Scan failed: "+e.getMessage()));}});
    }
    int copies(){try{return Math.max(1,Math.min(9999,Integer.parseInt(copiesEdit.getText().toString().trim())));}catch(Exception e){return 1;}}
    Bitmap load(Uri u)throws Exception{return MediaStore.Images.Media.getBitmap(getContentResolver(),u);}
    File makePdf()throws Exception{
        if(frontUri==null||backUri==null)throw new Exception("Please load both FRONT and BACK first.");
        Bitmap f=load(frontUri),b=load(backUri);PdfDocument d=new PdfDocument();int total=copies();
        for(int s=0;s<(total+7)/8;s++){PdfDocument.Page fp=d.startPage(new PdfDocument.PageInfo.Builder(595,842,s*2+1).create());draw(fp.getCanvas(),f,total,s*8);d.finishPage(fp);PdfDocument.Page bp=d.startPage(new PdfDocument.PageInfo.Builder(595,842,s*2+2).create());draw(bp.getCanvas(),b,total,s*8);d.finishPage(bp);}
        File out=new File(getCacheDir(),"EasyCopy_"+new SimpleDateFormat("yyyyMMdd_HHmmss",Locale.US).format(new Date())+".pdf");try(FileOutputStream o=new FileOutputStream(out)){d.writeTo(o);}d.close();return out;
    }
    void draw(Canvas c,Bitmap im,int total,int start){c.drawColor(Color.WHITE);Paint p=new Paint(3);p.setStyle(Paint.Style.STROKE);p.setColor(Color.LTGRAY);float m=18,gx=8,gy=8,w=(595-2*m-gx)/2,h=(842-2*m-3*gy)/4;for(int k=0;k<8;k++){int n=start+k;if(n>=total)break;float x=m+(k%2)*(w+gx),y=m+(k/2)*(h+gy);c.drawRect(x,y,x+w,y+h,p);float q=Math.min((w-8)/im.getWidth(),(h-8)/im.getHeight()),iw=im.getWidth()*q,ih=im.getHeight()*q;c.drawBitmap(im,null,new RectF(x+(w-iw)/2,y+(h-ih)/2,x+(w+iw)/2,y+(h+ih)/2),new Paint(3));}}
    File lastPdf;
    void safePdf(){try{lastPdf=makePdf();status.setText("PDF preview ready: "+lastPdf.getName());}catch(Exception e){toast(e.getMessage());}}
    void savePdf(){try{lastPdf=makePdf();Intent i=new Intent(Intent.ACTION_CREATE_DOCUMENT);i.setType("application/pdf");i.putExtra(Intent.EXTRA_TITLE,lastPdf.getName());startActivityForResult(i,105);}catch(Exception e){toast(e.getMessage());}}
    void sharePdf(){try{lastPdf=makePdf();Intent i=new Intent(Intent.ACTION_SEND);i.setType("application/pdf");i.putExtra(Intent.EXTRA_STREAM,androidx.core.content.FileProvider.getUriForFile(this,"com.easycopy.app.fileprovider",lastPdf));startActivity(Intent.createChooser(i,"Share EasyCopy PDF"));}catch(Exception e){toast(e.getMessage());}}
    void printPdf(){try{lastPdf=makePdf();PrintManager pm=(PrintManager)getSystemService(PRINT_SERVICE);pm.print("EasyCopy",new PrintDocumentAdapter(){public void onLayout(PrintAttributes a,PrintAttributes b,CancellationSignal c,LayoutResultCallback x,Bundle z){x.onLayoutFinished(new PrintDocumentInfo.Builder("EasyCopy.pdf").setContentType(PrintDocumentInfo.CONTENT_TYPE_DOCUMENT).setPageCount((copies()+7)/8*2).build(),true);}public void onWrite(PageRange[] p,ParcelFileDescriptor d,CancellationSignal c,WriteResultCallback x){try(InputStream in=new FileInputStream(lastPdf);OutputStream o=new FileOutputStream(d.getFileDescriptor())){byte[] b=new byte[8192];int n;while((n=in.read(b))>0)o.write(b,0,n);o.flush();x.onWriteFinished(new PageRange[]{PageRange.ALL_PAGES});}catch(Exception e){x.onWriteFailed(e.getMessage());}}},new PrintAttributes.Builder().setMediaSize(PrintAttributes.MediaSize.ISO_A4).build());}catch(Exception e){toast(e.getMessage());}}
    void toast(String s){Toast.makeText(this,s,Toast.LENGTH_LONG).show();}
}