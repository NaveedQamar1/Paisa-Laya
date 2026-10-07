package com.easycopy.app;

import android.app.*;
import android.content.*;
import android.graphics.*;
import android.graphics.pdf.PdfDocument;
import android.graphics.drawable.GradientDrawable;
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

    private static final float CARD_W_MM=85.60f;
    private static final float CARD_H_MM=53.98f;
    private static final float CARD_RATIO=CARD_W_MM/CARD_H_MM;

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
        TextView hint=tv("Place the card anywhere on the scanner glass. EasyCopy auto-crops, corrects orientation and prints it at real ID-card size.",13);hint.setTextColor(Color.rgb(102,112,133));id.addView(hint);
        LinearLayout sides=new LinearLayout(this);sides.setOrientation(LinearLayout.HORIZONTAL);
        LinearLayout f=side("FRONT",true), b=side("BACK",false);sides.addView(f,new LinearLayout.LayoutParams(0,dp(180),1));sides.addView(b,new LinearLayout.LayoutParams(0,dp(180),1));id.addView(sides);
        LinearLayout copies=new LinearLayout(this);copies.setGravity(Gravity.CENTER_VERTICAL);copies.addView(tv("Complete copies (front + back)",15),new LinearLayout.LayoutParams(0,dp(50),1));copiesEdit=new EditText(this);copiesEdit.setText("1");copiesEdit.setInputType(2);copiesEdit.setSelectAllOnFocus(true);copies.addView(copiesEdit,new LinearLayout.LayoutParams(dp(90),dp(52)));id.addView(copies);
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
    void manualAdd(){String ip=ipEdit.getText().toString().trim();if(ip.isEmpty()){toast("Enter the scanner IP address.");return;}selectedScanner=(ip.startsWith("http")?ip:"https://"+ip+":443/eSCL/");scannerStatus.setText("Manual scanner selected: "+selectedScanner);}
    void pick(boolean front){Intent i=new Intent(Intent.ACTION_OPEN_DOCUMENT);i.addCategory(Intent.CATEGORY_OPENABLE);i.setType("image/*");startActivityForResult(i,front?101:102);}
    @Override protected void onActivityResult(int r,int c,Intent d){
        super.onActivityResult(r,c,d);
        if(c!=RESULT_OK||d==null||d.getData()==null)return;
        Uri u=d.getData();
        if(r==101)processImported(u,true);
        else if(r==102)processImported(u,false);
        else if(r==105&&pendingCopy!=null){
            try(OutputStream o=getContentResolver().openOutputStream(d.getData());InputStream in=new FileInputStream(pendingCopy)){
                byte[] b=new byte[8192];int n;while((n=in.read(b))>0)o.write(b,0,n);status.setText("PDF saved.");
            }catch(Exception e){toast(e.getMessage());}
        }
    }
    void processImported(Uri u,boolean front){
        status.setText("Preparing "+(front?"front":"back")+"…");
        pool.execute(()->{
            try{
                Bitmap raw=load(u),card=prepareCard(raw);
                File f=new File(getCacheDir(),"imported_card_"+System.currentTimeMillis()+".jpg");
                try(FileOutputStream o=new FileOutputStream(f)){card.compress(Bitmap.CompressFormat.JPEG,98,o);}
                Uri cu=Uri.fromFile(f);
                if(raw!=card)raw.recycle();
                runOnUiThread(()->{
                    if(front){frontUri=cu;frontPreview.setImageURI(cu);status.setText("Front ready.");}
                    else{backUri=cu;backPreview.setImageURI(cu);status.setText("Back ready.");}
                });
            }catch(Exception e){runOnUiThread(()->toast("Could not prepare image: "+e.getMessage()));}
        });
    }

    void scanSide(boolean front){
        if(selectedScanner==null){toast("Connect to a network scanner first.");return;}
        status.setText("Scanning "+(front?"front":"back")+"… Place the card anywhere on the glass.");
        int dpi=new int[]{150,200,300,600}[dpiSpinner.getSelectedItemPosition()];
        String color=new String[]{"RGB24","Grayscale8","BlackAndWhite1"}[colorSpinner.getSelectedItemPosition()];
        boolean duplex=sourceSpinner.getSelectedItemPosition()==2;
        pool.execute(()->{
            try{
                byte[] data=NetworkScanner.scan(selectedScanner,dpi,color,duplex);
                Bitmap raw=BitmapFactory.decodeByteArray(data,0,data.length);
                Bitmap card=prepareCard(raw);
                File f=new File(getCacheDir(),"scanned_card_"+System.currentTimeMillis()+".jpg");
                try(FileOutputStream o=new FileOutputStream(f)){card.compress(Bitmap.CompressFormat.JPEG,98,o);}
                Uri u=Uri.fromFile(f);
                if(raw!=card)raw.recycle();
                runOnUiThread(()->{
                    if(front){frontUri=u;frontPreview.setImageURI(u);}else{backUri=u;backPreview.setImageURI(u);}
                    status.setText((front?"Front":"Back")+" ready — auto-cropped, oriented and sized for ID-card printing.");
                });
            }catch(Exception e){runOnUiThread(()->toast("Scan failed: "+e.getMessage()));}
        });
    }

    Bitmap load(Uri u)throws Exception{return MediaStore.Images.Media.getBitmap(getContentResolver(),u);}

    Bitmap prepareCard(Bitmap source){
        if(source==null)throw new IllegalArgumentException("The scanner returned no image.");
        int max=1400;
        float scale=Math.min(1f,max/(float)Math.max(source.getWidth(),source.getHeight()));
        Bitmap work=scale<1f?Bitmap.createScaledBitmap(source,Math.max(1,(int)(source.getWidth()*scale)),Math.max(1,(int)(source.getHeight()*scale)),true):source;
        int w=work.getWidth(),h=work.getHeight();

        // Estimate the scanner-bed background from the four corners only.
        int[][] pts={{0,0},{w-1,0},{0,h-1},{w-1,h-1}};
        long rs=0,gs=0,bs=0;
        for(int[] pt:pts){int col=work.getPixel(pt[0],pt[1]);rs+=Color.red(col);gs+=Color.green(col);bs+=Color.blue(col);}
        int br=(int)(rs/4),bg=(int)(gs/4),bb=(int)(bs/4);

        int left=w,top=h,right=-1,bottom=-1;
        for(int y=0;y<h;y++){
            for(int x=0;x<w;x++){
                int col=work.getPixel(x,y);
                int diff=Math.abs(Color.red(col)-br)+Math.abs(Color.green(col)-bg)+Math.abs(Color.blue(col)-bb);
                if(diff>55){
                    if(x<left)left=x;if(x>right)right=x;if(y<top)top=y;if(y>bottom)bottom=y;
                }
            }
        }
        if(right<0 || right-left<80 || bottom-top<50)throw new IllegalArgumentException("Could not detect the ID card. Make sure the whole card is on the scanner glass.");

        float bw=right-left+1,bh=bottom-top+1;
        float cx=(left+right)/2f,cy=(top+bottom)/2f;
        // Add enough margin to recover white card edges, then enforce exact card ratio.
        float ew=bw*1.10f,eh=bh*1.10f;
        if(ew/eh>CARD_RATIO)eh=ew/CARD_RATIO;else ew=eh*CARD_RATIO;
        if(ew>w){ew=w;eh=ew/CARD_RATIO;}
        if(eh>h){eh=h;ew=eh*CARD_RATIO;}
        float l=Math.max(0,Math.min(cx-ew/2f,w-ew));
        float t=Math.max(0,Math.min(cy-eh/2f,h-eh));
        Bitmap cropped=Bitmap.createBitmap(work,(int)l,(int)t,Math.max(1,(int)ew),Math.max(1,(int)eh));
        if(work!=source)work.recycle();

        if(cropped.getWidth()<cropped.getHeight()){
            Matrix m=new Matrix();m.postRotate(90);
            Bitmap r=Bitmap.createBitmap(cropped,0,0,cropped.getWidth(),cropped.getHeight(),m,true);
            cropped.recycle();cropped=r;
        }
        return cropped;
    }

    int copies(){try{return Math.max(1,Math.min(9999,Integer.parseInt(copiesEdit.getText().toString().trim())));}catch(Exception e){return 1;}}

    File makePdf()throws Exception{
        if(frontUri==null||backUri==null)throw new Exception("Please load both FRONT and BACK first.");
        Bitmap f=load(frontUri),b=load(backUri);
        PdfDocument d=new PdfDocument();int total=copies();
        for(int s=0;s<(total+7)/8;s++){
            PdfDocument.Page fp=d.startPage(new PdfDocument.PageInfo.Builder(595,842,s*2+1).create());
            draw(fp.getCanvas(),f,total,s*8,false);d.finishPage(fp);
            PdfDocument.Page bp=d.startPage(new PdfDocument.PageInfo.Builder(595,842,s*2+2).create());
            draw(bp.getCanvas(),b,total,s*8,true);d.finishPage(bp);
        }
        File out=new File(getCacheDir(),"EasyCopy_"+new SimpleDateFormat("yyyyMMdd_HHmmss",Locale.US).format(new Date())+".pdf");
        try(FileOutputStream o=new FileOutputStream(out)){d.writeTo(o);}d.close();
        f.recycle();b.recycle();
        return out;
    }

    // Front page uses normal coordinates. Back page is mirrored horizontally so that\n    // an A4 sheet printed duplex on the long edge places each back directly\n    // behind its corresponding front when the physical sheet is flipped.\n    void draw(Canvas c,Bitmap im,int total,int start,boolean backSide){\n        c.drawColor(Color.WHITE);\n        Paint border=new Paint(Paint.ANTI_ALIAS_FLAG);border.setStyle(Paint.Style.STROKE);border.setStrokeWidth(0.7f);border.setColor(Color.LTGRAY);\n        final float cardW=595f*CARD_W_MM/210f;\n        final float cardH=842f*CARD_H_MM/297f;\n        final float gapX=20f,gapY=18f;\n        final float marginX=(595f-(2*cardW+gapX))/2f;\n        final float marginY=(842f-(4*cardH+3*gapY))/2f;\n        Paint imagePaint=new Paint(Paint.ANTI_ALIAS_FLAG|Paint.FILTER_BITMAP_FLAG|Paint.DITHER_FLAG);\n        for(int k=0;k<8;k++){\n            int n=start+k;if(n>=total)break;\n            float normalX=marginX+(k%2)*(cardW+gapX);\n            float x=backSide?595f-normalX-cardW:normalX;\n            float y=marginY+(k/2)*(cardH+gapY);\n            c.drawRect(x,y,x+cardW,y+cardH,border);\n            c.drawBitmap(im,null,new RectF(x,y,x+cardW,y+cardH),imagePaint);\n        }\n    }\n
    File lastPdf;
    void safePdf(){try{lastPdf=makePdf();status.setText("PDF preview ready: "+lastPdf.getName());}catch(Exception e){toast(e.getMessage());}}
    void savePdf(){try{lastPdf=makePdf();pendingCopy=lastPdf;Intent i=new Intent(Intent.ACTION_CREATE_DOCUMENT);i.setType("application/pdf");i.putExtra(Intent.EXTRA_TITLE,lastPdf.getName());startActivityForResult(i,105);}catch(Exception e){toast(e.getMessage());}}
    void sharePdf(){try{lastPdf=makePdf();Intent i=new Intent(Intent.ACTION_SEND);i.setType("application/pdf");i.putExtra(Intent.EXTRA_STREAM,androidx.core.content.FileProvider.getUriForFile(this,"com.easycopy.app.fileprovider",lastPdf));startActivity(Intent.createChooser(i,"Share EasyCopy PDF"));}catch(Exception e){toast(e.getMessage());}}
    void printPdf(){try{lastPdf=makePdf();PrintManager pm=(PrintManager)getSystemService(PRINT_SERVICE);pm.print("EasyCopy",new PrintDocumentAdapter(){public void onLayout(PrintAttributes a,PrintAttributes b,CancellationSignal c,LayoutResultCallback x,Bundle z){x.onLayoutFinished(new PrintDocumentInfo.Builder("EasyCopy.pdf").setContentType(PrintDocumentInfo.CONTENT_TYPE_DOCUMENT).setPageCount((copies()+7)/8*2).build(),true);}public void onWrite(PageRange[] p,ParcelFileDescriptor d,CancellationSignal c,WriteResultCallback x){try(InputStream in=new FileInputStream(lastPdf);OutputStream o=new FileOutputStream(d.getFileDescriptor())){byte[] b=new byte[8192];int n;while((n=in.read(b))>0)o.write(b,0,n);o.flush();x.onWriteFinished(new PageRange[]{PageRange.ALL_PAGES});}catch(Exception e){x.onWriteFailed(e.getMessage());}}},new PrintAttributes.Builder().setMediaSize(PrintAttributes.MediaSize.ISO_A4).build());}catch(Exception e){toast(e.getMessage());}}
    void toast(String s){Toast.makeText(this,s,Toast.LENGTH_LONG).show();}
}