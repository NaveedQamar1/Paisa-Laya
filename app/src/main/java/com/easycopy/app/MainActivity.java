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

public class MainActivity extends Activity { // EasyCopy colorful UI build
    private ImageView frontPreview, backPreview;
    private Uri frontUri, backUri;
    private EditText copiesEdit;
    private Spinner cardCountSpinner;
    private final Uri[] frontUris=new Uri[4], backUris=new Uri[4];
    private final ImageView[] frontPreviews=new ImageView[4], backPreviews=new ImageView[4];
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
    Button btn(String s){return actionBtn(s,Color.WHITE,Color.rgb(55,48,163));}
    Button actionBtn(String s,int bg,int fg){Button b=new Button(this);b.setText(s);b.setTextSize(14);b.setAllCaps(false);b.setTextColor(fg);b.setTypeface(null,Typeface.BOLD);b.setPadding(dp(8),0,dp(8),0);GradientDrawable g=new GradientDrawable();g.setColor(bg);g.setCornerRadius(dp(14));g.setStroke(dp(1),Color.argb(35,0,0,0));b.setBackground(g);b.setStateListAnimator(null);return b;}
    LinearLayout card(){LinearLayout l=new LinearLayout(this);l.setOrientation(LinearLayout.VERTICAL);l.setPadding(dp(16),dp(12),dp(16),dp(12));GradientDrawable g=new GradientDrawable();g.setColor(Color.WHITE);g.setCornerRadius(dp(18));g.setStroke(dp(1),Color.rgb(229,231,240));l.setBackground(g);return l;}
    @Override public void onCreate(Bundle b){super.onCreate(b);getWindow().setStatusBarColor(Color.rgb(247,248,252));build();}

    void build(){
        ScrollView sc=new ScrollView(this);sc.setBackgroundColor(Color.rgb(247,248,252));
        LinearLayout root=new LinearLayout(this);root.setOrientation(LinearLayout.VERTICAL);root.setPadding(dp(16),dp(10),dp(16),dp(24));
        LinearLayout hero=new LinearLayout(this);hero.setOrientation(LinearLayout.VERTICAL);hero.setPadding(dp(18),dp(16),dp(18),dp(16));GradientDrawable hg=new GradientDrawable(GradientDrawable.Orientation.TL_BR,new int[]{Color.rgb(55,48,163),Color.rgb(6,182,212)});hg.setCornerRadius(dp(22));hero.setBackground(hg);TextView title=tv("EasyCopy",32);title.setTypeface(null,Typeface.BOLD);title.setTextColor(Color.WHITE);hero.addView(title);TextView heroSub=tv("Scan • Copy • Print • Share",14);heroSub.setTextColor(Color.WHITE);heroSub.setAlpha(.92f);hero.addView(heroSub);root.addView(hero,new LinearLayout.LayoutParams(-1,dp(108)));
        TextView sub=tv("Smart network scanner • CNIC copier • PDF",14);sub.setTextColor(Color.rgb(102,112,133));root.addView(sub);

        LinearLayout net=card(); TextView nt=tv("Network scanner",20);nt.setTypeface(null,Typeface.BOLD);net.addView(nt);
        scannerStatus=tv("Searching for scanners on this Wi‑Fi network…",13);scannerStatus.setTextColor(Color.rgb(102,112,133));net.addView(scannerStatus);
        devices=new LinearLayout(this);devices.setOrientation(LinearLayout.VERTICAL);net.addView(devices);
        Button rescan=actionBtn("↻  Find Scanners",Color.rgb(238,242,255),Color.rgb(55,48,163));net.addView(rescan);
        root.addView(net,new LinearLayout.LayoutParams(-1,-2));

        LinearLayout set=card(); TextView st=tv("Scan settings",20);st.setTypeface(null,Typeface.BOLD);set.addView(st);
        LinearLayout row1=new LinearLayout(this);dpiSpinner=spinner(new String[]{"150 DPI","200 DPI","300 DPI","600 DPI"});colorSpinner=spinner(new String[]{"Color","Grayscale","Black & White"});row1.addView(dpiSpinner,new LinearLayout.LayoutParams(0,dp(55),1));row1.addView(colorSpinner,new LinearLayout.LayoutParams(0,dp(55),1));set.addView(row1);
        sourceSpinner=spinner(new String[]{"Platen / Glass","Feeder","Duplex ADF"});set.addView(sourceSpinner,new LinearLayout.LayoutParams(-1,dp(55)));
        root.addView(set,new LinearLayout.LayoutParams(-1,-2));

        LinearLayout id=card();TextView it=tv("ID card copier",20);it.setTypeface(null,Typeface.BOLD);id.addView(it);
        TextView hint=tv("Place 1 to 4 cards anywhere on the scanner glass. EasyCopy scans the full area, finds the cards, straightens them and keeps each front paired with its own back.",13);hint.setTextColor(Color.rgb(102,112,133));id.addView(hint);
        LinearLayout countRow=new LinearLayout(this);countRow.setGravity(Gravity.CENTER_VERTICAL);countRow.addView(tv("Different ID cards",15),new LinearLayout.LayoutParams(0,dp(52),1));
        cardCountSpinner=spinner(new String[]{"1 card","2 cards","3 cards","4 cards"});countRow.addView(cardCountSpinner,new LinearLayout.LayoutParams(dp(130),dp(52)));id.addView(countRow);
        id.addView(side("FRONT SIDE",true));id.addView(side("BACK SIDE",false));
        LinearLayout copies=new LinearLayout(this);copies.setGravity(Gravity.CENTER_VERTICAL);copies.addView(tv("Copies of each complete set",15),new LinearLayout.LayoutParams(0,dp(50),1));copiesEdit=new EditText(this);copiesEdit.setText("1");copiesEdit.setInputType(2);copiesEdit.setSelectAllOnFocus(true);copies.addView(copiesEdit,new LinearLayout.LayoutParams(dp(90),dp(52)));id.addView(copies);
        CheckBox gray=new CheckBox(this);gray.setText("Economical grayscale output");gray.setId(9001);id.addView(gray);
        root.addView(id,new LinearLayout.LayoutParams(-1,-2));

        LinearLayout actions=card();TextView at=tv("Output",20);at.setTypeface(null,Typeface.BOLD);actions.addView(at);
        Button pdf=actionBtn("▣  Preview PDF",Color.rgb(55,48,163),Color.WHITE),save=actionBtn("↓  Save PDF",Color.rgb(18,183,106),Color.WHITE),print=actionBtn("⎙  Print A4 Duplex",Color.rgb(245,158,11),Color.WHITE),share=actionBtn("↗  Share PDF",Color.rgb(6,182,212),Color.WHITE);
        actions.addView(pdf);actions.addView(save);actions.addView(print);actions.addView(share);root.addView(actions,new LinearLayout.LayoutParams(-1,-2));
        status=tv("Ready. Connect a network scanner or import images.",13);status.setTextColor(Color.rgb(102,112,133));root.addView(status);
        sc.addView(root);setContentView(sc);

        pdf.setOnClickListener(v->safePdf());save.setOnClickListener(v->savePdf());print.setOnClickListener(v->printPdf());share.setOnClickListener(v->sharePdf());
        rescan.setOnClickListener(v->discover());
        discover();
    }
    Spinner spinner(String[] a){Spinner s=new Spinner(this);ArrayAdapter<String>x=new ArrayAdapter<String>(this,android.R.layout.simple_spinner_dropdown_item,a);x.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item);s.setAdapter(x);return s;}
    LinearLayout side(String name,boolean front){
        LinearLayout l=card();l.setPadding(dp(8),dp(6),dp(8),dp(6));TextView t=tv(name,15);t.setTypeface(null,Typeface.BOLD);l.addView(t);
        GridLayout grid=new GridLayout(this);grid.setColumnCount(2);grid.setRowCount(2);
        for(int i=0;i<4;i++){ImageView p=new ImageView(this);p.setBackgroundColor(Color.rgb(239,241,246));p.setScaleType(ImageView.ScaleType.CENTER_INSIDE);if(front)frontPreviews[i]=p;else backPreviews[i]=p;LinearLayout cell=new LinearLayout(this);cell.setOrientation(LinearLayout.VERTICAL);cell.addView(tv(""+(i+1),12));cell.addView(p,new LinearLayout.LayoutParams(-1,dp(75)));GridLayout.LayoutParams gp=new GridLayout.LayoutParams();gp.width=0;gp.height=dp(100);gp.columnSpec=GridLayout.spec(i%2,1,1);gp.rowSpec=GridLayout.spec(i/2,1,1);grid.addView(cell,gp);}
        l.addView(grid);
        Button scan=actionBtn(front?"Scan all fronts":"Scan all backs",Color.rgb(55,48,163),Color.WHITE),imp=actionBtn(front?"Import fronts":"Import backs",Color.rgb(238,242,255),Color.rgb(55,48,163));LinearLayout r=new LinearLayout(this);r.addView(scan,new LinearLayout.LayoutParams(0,dp(48),1));r.addView(imp,new LinearLayout.LayoutParams(0,dp(48),1));l.addView(r);
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
        scannerStatus.setText("Scanner available");Button b=actionBtn("●  "+name+"\n"+url,Color.rgb(236,253,245),Color.rgb(6,95,70));b.setGravity(Gravity.LEFT|Gravity.CENTER_VERTICAL);b.setOnClickListener(v->{selectedScanner=url;scannerStatus.setText("Connected: "+name);});
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
        status.setText("Finding ID cards…");
        pool.execute(()->{try{Bitmap raw=load(u);ArrayList<Bitmap> cards=prepareCards(raw,cardCount());for(int i=0;i<cards.size();i++)saveCard(cards.get(i),front,i);if(raw!=null)raw.recycle();runOnUiThread(()->status.setText((front?"Fronts":"Backs")+" ready."));}catch(Exception e){runOnUiThread(()->toast("Could not prepare image: "+e.getMessage()));}});
    }
    void scanSide(boolean front){
        if(selectedScanner==null){toast("Select a scanner first.");return;}
        status.setText("Scanning the full scanner area…");
        int dpi=new int[]{150,200,300,600}[dpiSpinner.getSelectedItemPosition()];
        String color=new String[]{"RGB24","Grayscale8","BlackAndWhite1"}[colorSpinner.getSelectedItemPosition()];
        boolean duplex=sourceSpinner.getSelectedItemPosition()==2;
        pool.execute(()->{try{byte[] data=NetworkScanner.scan(selectedScanner,dpi,color,duplex);Bitmap raw=BitmapFactory.decodeByteArray(data,0,data.length);ArrayList<Bitmap> cards=prepareCards(raw,cardCount());for(int i=0;i<cards.size();i++)saveCard(cards.get(i),front,i);if(raw!=null)raw.recycle();runOnUiThread(()->status.setText((front?"Fronts":"Backs")+" ready — "+cards.size()+" detected."));}catch(Exception e){runOnUiThread(()->toast("Scan failed: "+e.getMessage()));}});
    }
    int cardCount(){return cardCountSpinner==null?1:Math.max(1,Math.min(4,cardCountSpinner.getSelectedItemPosition()+1));}
    void saveCard(Bitmap card,boolean front,int index)throws Exception{
        File f=new File(getCacheDir(),(front?"front_":"back_")+(index+1)+"_"+System.currentTimeMillis()+".jpg");try(FileOutputStream o=new FileOutputStream(f)){card.compress(Bitmap.CompressFormat.JPEG,98,o);}Uri u=Uri.fromFile(f);
        runOnUiThread(()->{if(front){frontUris[index]=u;frontPreviews[index].setImageURI(u);}else{backUris[index]=u;backPreviews[index].setImageURI(u);}});
    }

    Bitmap load(Uri u)throws Exception{return MediaStore.Images.Media.getBitmap(getContentResolver(),u);}

    ArrayList<Bitmap> prepareCards(Bitmap source,int wanted){
        if(source==null)throw new IllegalArgumentException("The scanner returned no image.");
        int max=1800;float scale=Math.min(1f,max/(float)Math.max(source.getWidth(),source.getHeight()));
        Bitmap work=scale<1f?Bitmap.createScaledBitmap(source,Math.max(1,(int)(source.getWidth()*scale)),Math.max(1,(int)(source.getHeight()*scale)),true):source;
        int w=work.getWidth(),h=work.getHeight(),n=w*h;int[] px=new int[n];work.getPixels(px,0,w,0,0,w,h);
        int br=0,bg=0,bb=0,cnt=0,step=Math.max(1,Math.min(w,h)/100);
        for(int y=0;y<h;y+=step)for(int x=0;x<w;x+=step)if(x<step*4||y<step*4||x>w-step*5||y>h-step*5){int c=px[y*w+x];br+=Color.red(c);bg+=Color.green(c);bb+=Color.blue(c);cnt++;}
        br/=Math.max(1,cnt);bg/=Math.max(1,cnt);bb/=Math.max(1,cnt);
        boolean[] fg=new boolean[n];for(int i=0;i<n;i++){int c=px[i];fg[i]=Math.abs(Color.red(c)-br)+Math.abs(Color.green(c)-bg)+Math.abs(Color.blue(c)-bb)>42;}
        boolean[] seen=new boolean[n];ArrayDeque<Integer> q=new ArrayDeque<>();ArrayList<Rect> boxes=new ArrayList<>();int minArea=Math.max(2500,n/1500);
        for(int y=0;y<h;y++)for(int x=0;x<w;x++){int idx=y*w+x;if(!fg[idx]||seen[idx])continue;q.clear();q.add(idx);seen[idx]=true;int l=x,r=x,t=y,b=y,area=0;
            while(!q.isEmpty()){int z=q.removeFirst(),zx=z%w,zy=z/w;area++;l=Math.min(l,zx);r=Math.max(r,zx);t=Math.min(t,zy);b=Math.max(b,zy);
                if(zx>0&&!seen[z-1]&&fg[z-1]){seen[z-1]=true;q.add(z-1);}if(zx<w-1&&!seen[z+1]&&fg[z+1]){seen[z+1]=true;q.add(z+1);}
                if(zy>0&&!seen[z-w]&&fg[z-w]){seen[z-w]=true;q.add(z-w);}if(zy<h-1&&!seen[z+w]&&fg[z+w]){seen[z+w]=true;q.add(z+w);}
            }
            int bw=r-l+1,bh=b-t+1;float ratio=bw/(float)bh;if(area>=minArea&&bw>80&&bh>50&&bw<.95f*w&&bh<.95f*h&&ratio>1.15f&&ratio<2.2f)boxes.add(new Rect(l,t,r+1,b+1));
        }
        boxes.sort((a,b)->a.top==b.top?Integer.compare(a.left,b.left):Integer.compare(a.top,b.top));
        ArrayList<Bitmap> out=new ArrayList<>();
        for(Rect box:boxes){if(out.size()>=wanted)break;float ew=box.width()*1.10f,eh=ew/CARD_RATIO;if(eh>box.height()*1.35f){eh=box.height()*1.10f;ew=eh*CARD_RATIO;}int l=Math.max(0,Math.min(w-(int)ew,(int)(box.centerX()-ew/2)));int t=Math.max(0,Math.min(h-(int)eh,(int)(box.centerY()-eh/2)));Bitmap c=Bitmap.createBitmap(work,l,t,Math.max(1,Math.min(w-l,(int)ew)),Math.max(1,Math.min(h-t,(int)eh)));if(c.getWidth()<c.getHeight()){Matrix m=new Matrix();m.postRotate(90);Bitmap r=Bitmap.createBitmap(c,0,0,c.getWidth(),c.getHeight(),m,true);c.recycle();c=r;}out.add(c);}
        if(out.isEmpty())throw new IllegalArgumentException("No ID card detected. Place the entire card on the glass with some scanner-bed area around it.");
        if(work!=source)work.recycle();return out;
    }

    int copies(){try{return Math.max(1,Math.min(9999,Integer.parseInt(copiesEdit.getText().toString().trim())));}catch(Exception e){return 1;}}

    File makePdf()throws Exception{
        int n=cardCount(),reps=copies();for(int i=0;i<n;i++)if(frontUris[i]==null||backUris[i]==null)throw new Exception("Please scan/import both sides for card "+(i+1)+".");
        PdfDocument d=new PdfDocument();int total=n*reps;
        for(int page=0;page<(total+3)/4;page++){PdfDocument.Page fp=d.startPage(new PdfDocument.PageInfo.Builder(595,842,page*2+1).create());drawSet(fp.getCanvas(),true,page*4,n,reps);d.finishPage(fp);PdfDocument.Page bp=d.startPage(new PdfDocument.PageInfo.Builder(595,842,page*2+2).create());drawSet(bp.getCanvas(),false,page*4,n,reps);d.finishPage(bp);}
        File out=new File(getCacheDir(),"EasyCopy_"+new SimpleDateFormat("yyyyMMdd_HHmmss",Locale.US).format(new Date())+".pdf");try(FileOutputStream o=new FileOutputStream(out)){d.writeTo(o);}d.close();return out;
    }
    void drawSet(Canvas c,boolean front,int start,int n,int reps){
        c.drawColor(Color.WHITE);float cardW=595f*CARD_W_MM/210f,cardH=842f*CARD_H_MM/297f,gapX=24f,gapY=24f,marginX=(595f-(2*cardW+gapX))/2f,marginY=(842f-(2*cardH+gapY))/2f);Paint p=new Paint(Paint.ANTI_ALIAS_FLAG|Paint.FILTER_BITMAP_FLAG|Paint.DITHER_FLAG);
        for(int k=0;k<4;k++){int global=start+k;if(global>=n*reps)break;int ci=global%n;Uri u=front?frontUris[ci]:backUris[ci];try{Bitmap im=load(u);float nx=marginX+(k%2)*(cardW+gapX),x=front?nx:595f-nx-cardW,y=marginY+(k/2)*(cardH+gapY);c.drawBitmap(im,null,new RectF(x,y,x+cardW,y+cardH),p);im.recycle();}catch(Exception ignored){}}
    }

    File lastPdf;
    void safePdf(){try{lastPdf=makePdf();status.setText("PDF preview ready: "+lastPdf.getName());}catch(Exception e){toast(e.getMessage());}}
    void savePdf(){try{lastPdf=makePdf();pendingCopy=lastPdf;Intent i=new Intent(Intent.ACTION_CREATE_DOCUMENT);i.setType("application/pdf");i.putExtra(Intent.EXTRA_TITLE,lastPdf.getName());startActivityForResult(i,105);}catch(Exception e){toast(e.getMessage());}}
    void sharePdf(){try{lastPdf=makePdf();Intent i=new Intent(Intent.ACTION_SEND);i.setType("application/pdf");i.putExtra(Intent.EXTRA_STREAM,androidx.core.content.FileProvider.getUriForFile(this,"com.easycopy.app.fileprovider",lastPdf));startActivity(Intent.createChooser(i,"Share EasyCopy PDF"));}catch(Exception e){toast(e.getMessage());}}
    void printPdf(){try{lastPdf=makePdf();PrintManager pm=(PrintManager)getSystemService(PRINT_SERVICE);pm.print("EasyCopy",new PrintDocumentAdapter(){public void onLayout(PrintAttributes a,PrintAttributes b,CancellationSignal c,LayoutResultCallback x,Bundle z){x.onLayoutFinished(new PrintDocumentInfo.Builder("EasyCopy.pdf").setContentType(PrintDocumentInfo.CONTENT_TYPE_DOCUMENT).setPageCount((copies()+7)/8*2).build(),true);}public void onWrite(PageRange[] p,ParcelFileDescriptor d,CancellationSignal c,WriteResultCallback x){try(InputStream in=new FileInputStream(lastPdf);OutputStream o=new FileOutputStream(d.getFileDescriptor())){byte[] b=new byte[8192];int n;while((n=in.read(b))>0)o.write(b,0,n);o.flush();x.onWriteFinished(new PageRange[]{PageRange.ALL_PAGES});}catch(Exception e){x.onWriteFailed(e.getMessage());}}},new PrintAttributes.Builder().setMediaSize(PrintAttributes.MediaSize.ISO_A4).build());}catch(Exception e){toast(e.getMessage());}}
    void toast(String s){Toast.makeText(this,s,Toast.LENGTH_LONG).show();}
}