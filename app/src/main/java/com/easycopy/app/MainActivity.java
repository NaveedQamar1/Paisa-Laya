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
import org.opencv.android.OpenCVLoader;
import org.opencv.android.Utils;
import org.opencv.core.Core;
import org.opencv.core.CvType;
import org.opencv.core.Mat;
import org.opencv.core.MatOfPoint;
import org.opencv.core.MatOfPoint2f;
import org.opencv.core.Scalar;
import org.opencv.core.Size;
import org.opencv.imgproc.Imgproc;
import com.google.android.gms.tasks.Tasks;
import com.google.mlkit.vision.common.InputImage;
import com.google.mlkit.vision.text.Text;
import com.google.mlkit.vision.text.TextRecognition;
import com.google.mlkit.vision.text.TextRecognizer;
import com.google.mlkit.vision.text.latin.TextRecognizerOptions;

public class MainActivity extends Activity { // EasyCopy colorful UI build
    private EditText copiesEdit;
    private Spinner cardCountSpinner;
    private final Uri[] frontUris=new Uri[4], backUris=new Uri[4];
    private final ImageView[] frontPreviews=new ImageView[4], backPreviews=new ImageView[4];
    private final View[][] sideCells=new View[2][4];
    private Spinner dpiSpinner,colorSpinner,sourceSpinner;
    private TextView status,scannerStatus;
    private Spinner scannerSpinner;
    private final ArrayList<String> scannerUrls=new ArrayList<>();
    private final ArrayList<String> scannerNames=new ArrayList<>();
    private ExecutorService pool=Executors.newFixedThreadPool(2);
    private File pendingCopy;
    private final TextRecognizer textRecognizer=TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS);

    private static final float CARD_W_MM=85.60f;
    private static final float CARD_H_MM=53.98f;
    private static final float CARD_RATIO=CARD_W_MM/CARD_H_MM;

    int dp(float x){return (int)(x*getResources().getDisplayMetrics().density+.5f);}
    TextView tv(String s,float z){TextView t=new TextView(this);t.setText(s);t.setTextSize(z);t.setTextColor(Color.rgb(24,32,51));t.setPadding(0,dp(5),0,dp(5));return t;}
    Button btn(String s){return actionBtn(s,Color.WHITE,Color.rgb(55,48,163));}
    Button actionBtn(String s,int bg,int fg){Button b=new Button(this);b.setText(s);b.setTextSize(14);b.setAllCaps(false);b.setTextColor(fg);b.setTypeface(null,Typeface.BOLD);b.setPadding(dp(8),0,dp(8),0);GradientDrawable g=new GradientDrawable();g.setColor(bg);g.setCornerRadius(dp(14));g.setStroke(dp(1),Color.argb(35,0,0,0));b.setBackground(g);b.setStateListAnimator(null);return b;}
    LinearLayout card(){LinearLayout l=new LinearLayout(this);l.setOrientation(LinearLayout.VERTICAL);l.setPadding(dp(16),dp(12),dp(16),dp(12));GradientDrawable g=new GradientDrawable();g.setColor(Color.WHITE);g.setCornerRadius(dp(18));g.setStroke(dp(1),Color.rgb(229,231,240));l.setBackground(g);return l;}
    @Override public void onCreate(Bundle b){
        super.onCreate(b);
        getWindow().setStatusBarColor(Color.rgb(247,248,252));getWindow().setNavigationBarColor(Color.rgb(247,248,252));getWindow().setBackgroundDrawable(new android.graphics.drawable.ColorDrawable(Color.rgb(247,248,252)));
        if(!OpenCVLoader.initLocal()){
            Toast.makeText(this,"OpenCV could not be loaded; using basic card detection.",Toast.LENGTH_LONG).show();
        }
        build();
    }

    void build(){
        ScrollView sc=new ScrollView(this);sc.setBackgroundColor(Color.rgb(247,248,252));
        LinearLayout root=new LinearLayout(this);root.setOrientation(LinearLayout.VERTICAL);root.setPadding(dp(16),dp(10),dp(16),dp(24));
        LinearLayout hero=new LinearLayout(this);hero.setOrientation(LinearLayout.VERTICAL);hero.setPadding(dp(18),dp(16),dp(18),dp(16));GradientDrawable hg=new GradientDrawable(GradientDrawable.Orientation.TL_BR,new int[]{Color.rgb(55,48,163),Color.rgb(6,182,212)});hg.setCornerRadius(dp(22));hero.setBackground(hg);TextView title=tv("EasyCopy",32);title.setTypeface(null,Typeface.BOLD);title.setTextColor(Color.WHITE);hero.addView(title);TextView heroSub=tv("Scan • Copy • Print • Share",14);heroSub.setTextColor(Color.WHITE);heroSub.setAlpha(.92f);hero.addView(heroSub);root.addView(hero,new LinearLayout.LayoutParams(-1,dp(108)));
        TextView sub=tv("Smart network scanner • CNIC copier • PDF",14);sub.setTextColor(Color.rgb(102,112,133));root.addView(sub);

        LinearLayout net=card(); TextView nt=tv("Network scanner",20);nt.setTypeface(null,Typeface.BOLD);net.addView(nt);
        scannerStatus=tv("Searching for scanners on this Wi‑Fi network…",13);scannerStatus.setTextColor(Color.rgb(102,112,133));net.addView(scannerStatus);
        scannerSpinner=spinner(new String[]{"Searching for scanners…"});net.addView(scannerSpinner,new LinearLayout.LayoutParams(-1,dp(58)));scannerSpinner.setOnItemSelectedListener(new android.widget.AdapterView.OnItemSelectedListener(){public void onItemSelected(android.widget.AdapterView<?> p,View v,int pos,long id){if(pos>=0&&pos<scannerUrls.size()){selectedScanner=scannerUrls.get(pos);scannerStatus.setText("Selected: "+scannerNames.get(pos));}}public void onNothingSelected(android.widget.AdapterView<?> p){}});
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
        cardCountSpinner.setOnItemSelectedListener(new android.widget.AdapterView.OnItemSelectedListener(){public void onItemSelected(android.widget.AdapterView<?> p,View v,int pos,long id){updateSlotVisibility();}public void onNothingSelected(android.widget.AdapterView<?> p){updateSlotVisibility();}});
        id.addView(side("FRONT SIDE",true));id.addView(side("BACK SIDE",false));
        LinearLayout copies=new LinearLayout(this);copies.setGravity(Gravity.CENTER_VERTICAL);copies.addView(tv("Copies of each complete set",15),new LinearLayout.LayoutParams(0,dp(50),1));copiesEdit=new EditText(this);copiesEdit.setText("1");copiesEdit.setInputType(2);copiesEdit.setSelectAllOnFocus(true);copies.addView(copiesEdit,new LinearLayout.LayoutParams(dp(90),dp(52)));id.addView(copies);
        CheckBox gray=new CheckBox(this);gray.setText("Economical grayscale output");gray.setId(9001);id.addView(gray);
        root.addView(id,new LinearLayout.LayoutParams(-1,-2));

        LinearLayout imagePrinter=card();TextView ipt=tv("Image printer",20);ipt.setTypeface(null,Typeface.BOLD);imagePrinter.addView(ipt);TextView iph=tv("Print PNG, JPG or JPEG files with crop, zoom, pan and rotation controls.",13);iph.setTextColor(Color.rgb(102,112,133));imagePrinter.addView(iph);Button chooseImage=actionBtn("Choose image to print",Color.rgb(238,242,255),Color.rgb(55,48,163));imagePrinter.addView(chooseImage);chooseImage.setOnClickListener(v->pickForPrint());root.addView(imagePrinter,new LinearLayout.LayoutParams(-1,-2));

        LinearLayout actions=card();TextView at=tv("Output",20);at.setTypeface(null,Typeface.BOLD);actions.addView(at);
        Button pdf=actionBtn("▣  Preview PDF",Color.rgb(55,48,163),Color.WHITE),save=actionBtn("↓  Save PDF",Color.rgb(18,183,106),Color.WHITE),print=actionBtn("⎙  Print A4 Duplex",Color.rgb(245,158,11),Color.WHITE),share=actionBtn("↗  Share PDF",Color.rgb(6,182,212),Color.WHITE);
        actions.addView(pdf);actions.addView(save);actions.addView(print);actions.addView(share);root.addView(actions,new LinearLayout.LayoutParams(-1,-2));
        status=tv("Ready. Connect a network scanner or import images.",13);
        updateSlotVisibility();status.setTextColor(Color.rgb(102,112,133));root.addView(status);
        sc.addView(root);setContentView(sc);

        pdf.setOnClickListener(v->safePdf());save.setOnClickListener(v->savePdf());print.setOnClickListener(v->printPdf());share.setOnClickListener(v->sharePdf());
        rescan.setOnClickListener(v->discover());
        discover();
    }
    Spinner spinner(String[] a){Spinner s=new Spinner(this);ArrayAdapter<String>x=new ArrayAdapter<String>(this,android.R.layout.simple_spinner_dropdown_item,a);x.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item);s.setAdapter(x);return s;}
    LinearLayout side(String name,boolean front){
        LinearLayout l=card();l.setPadding(dp(8),dp(6),dp(8),dp(6));TextView t=tv(name,15);t.setTypeface(null,Typeface.BOLD);l.addView(t);
        GridLayout grid=new GridLayout(this);grid.setColumnCount(2);grid.setRowCount(2);
        for(int i=0;i<4;i++){ImageView p=new ImageView(this);p.setBackgroundColor(Color.rgb(239,241,246));p.setScaleType(ImageView.ScaleType.CENTER_INSIDE);if(front)frontPreviews[i]=p;else backPreviews[i]=p;LinearLayout cell=new LinearLayout(this);cell.setOrientation(LinearLayout.VERTICAL);cell.addView(tv(""+(i+1),12));cell.addView(p,new LinearLayout.LayoutParams(-1,dp(75)));GridLayout.LayoutParams gp=new GridLayout.LayoutParams();gp.width=0;gp.height=dp(100);gp.columnSpec=GridLayout.spec(i%2,1,1);gp.rowSpec=GridLayout.spec(i/2,1,1);grid.addView(cell,gp);sideCells[front?0:1][i]=cell;}
        l.addView(grid);
        Button scan=actionBtn(front?"Scan all fronts":"Scan all backs",Color.rgb(55,48,163),Color.WHITE),imp=actionBtn(front?"Import fronts":"Import backs",Color.rgb(238,242,255),Color.rgb(55,48,163));LinearLayout r=new LinearLayout(this);r.addView(scan,new LinearLayout.LayoutParams(0,dp(48),1));r.addView(imp,new LinearLayout.LayoutParams(0,dp(48),1));l.addView(r);
        scan.setOnClickListener(v->scanSide(front));imp.setOnClickListener(v->pick(front));return l;
    }
    void discover(){
        scannerUrls.clear();scannerNames.clear();scannerSpinner.setAdapter(new ArrayAdapter<String>(this,android.R.layout.simple_spinner_dropdown_item,new String[]{"Searching for scanners…"}));
        scannerStatus.setText("Searching…");
        NetworkScanner ns=new NetworkScanner(this);ns.discover(new NetworkScanner.Listener(){
            public void onDevice(String name,String url){runOnUiThread(()->addDevice(name,url));}
            public void onDone(){runOnUiThread(()->{if(scannerUrls.isEmpty())scannerStatus.setText("No compatible eSCL scanner found on this network.");else{ArrayAdapter<String>a=new ArrayAdapter<String>(MainActivity.this,android.R.layout.simple_spinner_dropdown_item,scannerNames);a.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item);scannerSpinner.setAdapter(a);scannerSpinner.setSelection(0);scannerStatus.setText("Scanner available");}});}
            public void onError(String m){runOnUiThread(()->scannerStatus.setText(m));}
        });
    }
    void addDevice(String name,String url){
        for(int i=0;i<scannerUrls.size();i++)if(scannerUrls.get(i).equals(url))return;
        scannerUrls.add(url);scannerNames.add(name);
        ArrayAdapter<String>a=new ArrayAdapter<String>(this,android.R.layout.simple_spinner_dropdown_item,scannerNames);a.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item);scannerSpinner.setAdapter(a);
    }
    String selectedScanner;
    void pick(boolean front){Intent i=new Intent(Intent.ACTION_OPEN_DOCUMENT);i.addCategory(Intent.CATEGORY_OPENABLE);i.setType("image/*");startActivityForResult(i,front?101:102);}
    void pickForPrint(){Intent i=new Intent(Intent.ACTION_OPEN_DOCUMENT);i.addCategory(Intent.CATEGORY_OPENABLE);i.setType("image/*");startActivityForResult(i,106);}
    void processImageForPrint(Uri u){status.setText("Opening image editor…");pool.execute(()->{try{Bitmap b=load(u);if(b==null)throw new Exception("Could not open image.");runOnUiThread(()->showImageEditor(b));}catch(Exception e){runOnUiThread(()->toast("Could not open image: "+e.getMessage()));}});}
    @Override protected void onActivityResult(int r,int c,Intent d){
        super.onActivityResult(r,c,d);
        if(c!=RESULT_OK||d==null||d.getData()==null)return;
        Uri u=d.getData();
        if(r==101)processImported(u,true);
        else if(r==102)processImported(u,false);
        else if(r==106)processImageForPrint(u);
        else if(r==105&&pendingCopy!=null){
            try(OutputStream o=getContentResolver().openOutputStream(d.getData());InputStream in=new FileInputStream(pendingCopy)){
                byte[] b=new byte[8192];int n;while((n=in.read(b))>0)o.write(b,0,n);
                status.setText("PDF saved.");
                openPdf(d.getData());
            }catch(Exception e){toast(e.getMessage());}
        }
    }
    void processImported(Uri u,boolean front){
        status.setText("Importing image…");
        pool.execute(()->{try{
            Bitmap raw=load(u);
            if(raw==null)throw new IllegalArgumentException("Could not read the selected image.");
            // Gallery images are treated as already-cropped card images. Do not run
            // scanner/card detection on them again, otherwise a perfectly cropped
            // NIC can be detected against its own background and cut in half.
            Bitmap card=raw;
            if(card.getWidth()<card.getHeight()){
                Matrix m=new Matrix();
                m.postRotate(90);
                Bitmap rotated=Bitmap.createBitmap(card,0,0,card.getWidth(),card.getHeight(),m,true);
                if(rotated!=card)card.recycle();
                card=rotated;
            }
            Bitmap oriented=autoOrientCard(card);
            if(oriented!=card)card.recycle();
            card=oriented;
            saveCard(card,front,0);
            if(card!=raw)card.recycle();
            else raw.recycle();
            runOnUiThread(()->status.setText((front?"Front":"Back")+" image imported."));
        }catch(Exception e){runOnUiThread(()->toast("Could not import image: "+e.getMessage()));}});
    }
    interface ProcessProgress{void update(int percent,String detail);}
    Dialog showProcessDialog(String title){
        final Dialog dialog=new Dialog(this);
        LinearLayout box=new LinearLayout(this);box.setOrientation(LinearLayout.VERTICAL);box.setPadding(dp(28),dp(22),dp(28),dp(22));box.setBackgroundColor(Color.WHITE);
        TextView t=tv(title,20);t.setTypeface(null,Typeface.BOLD);box.addView(t);
        TextView pct=tv("0%",18);pct.setGravity(Gravity.CENTER);box.addView(pct);
        ProgressBar bar=new ProgressBar(this,null,android.R.attr.progressBarStyleHorizontal);bar.setMax(100);bar.setProgress(0);box.addView(bar,new LinearLayout.LayoutParams(-1,dp(18)));
        TextView detail=tv("Starting…",13);detail.setTextColor(Color.rgb(102,112,133));box.addView(detail);
        dialog.setContentView(box);dialog.setCancelable(false);dialog.show();
        Window w=dialog.getWindow();if(w!=null){w.setBackgroundDrawableResource(android.R.color.white);w.setLayout(dp(310),-2);}
        if(dialog.getWindow()!=null)dialog.getWindow().getDecorView().setTag(new Object[]{bar,pct,detail});
        return dialog;
    }
    void updateProcessDialog(Dialog dialog,int percent,String detail){
        runOnUiThread(()->{
            Object[] v=(Object[])dialog.getWindow().getDecorView().getTag();
            int p=Math.max(0,Math.min(100,percent));
            ((ProgressBar)v[0]).setProgress(p);
            ((TextView)v[1]).setText(p+"%");
            ((TextView)v[2]).setText(detail);
        });
    }
    void scanSide(boolean front){
        if(selectedScanner==null){toast("Select a scanner first.");return;}
        status.setText("Scanning the full scanner area…");
        int dpi=new int[]{150,200,300,600}[dpiSpinner.getSelectedItemPosition()];
        String color=new String[]{"RGB24","Grayscale8","BlackAndWhite1"}[colorSpinner.getSelectedItemPosition()];
        boolean duplex=sourceSpinner.getSelectedItemPosition()==2;
        Dialog dialog=showProcessDialog(front?"Scanning fronts…":"Scanning backs…");
        pool.execute(()->{try{
            byte[] data=NetworkScanner.scan(selectedScanner,dpi,color,duplex);
            updateProcessDialog(dialog,10,"Scan received. Preparing image…");
            Bitmap raw=BitmapFactory.decodeByteArray(data,0,data.length);
            ArrayList<Bitmap> cards=prepareCards(raw,cardCount(),(p,d)->updateProcessDialog(dialog,10+Math.round(p*.80f),d));
            updateProcessDialog(dialog,93,"Saving detected cards…");
            for(int i=0;i<cards.size();i++){
                saveCard(cards.get(i),front,i);
                updateProcessDialog(dialog,93+Math.round((i+1)*7f/Math.max(1,cards.size())), "Saving card "+(i+1)+" of "+cards.size()+"…");
            }
            if(raw!=null)raw.recycle();
            updateProcessDialog(dialog,100,"Complete.");
            runOnUiThread(()->{dialog.dismiss();status.setText((front?"Fronts":"Backs")+" ready — "+cards.size()+" detected.");});
        }catch(Exception e){runOnUiThread(()->{dialog.dismiss();toast("Scan failed: "+e.getMessage());});}});
    }
    int cardCount(){return cardCountSpinner==null?1:Math.max(1,Math.min(4,cardCountSpinner.getSelectedItemPosition()+1));}
    void saveCard(Bitmap card,boolean front,int index)throws Exception{
        File f=new File(getCacheDir(),(front?"front_":"back_")+(index+1)+"_"+System.currentTimeMillis()+".jpg");try(FileOutputStream o=new FileOutputStream(f)){card.compress(Bitmap.CompressFormat.JPEG,98,o);}Uri u=Uri.fromFile(f);
        runOnUiThread(()->{if(front){frontUris[index]=u;frontPreviews[index].setImageURI(u);}else{backUris[index]=u;backPreviews[index].setImageURI(u);}});
    }

    Bitmap load(Uri u)throws Exception{return MediaStore.Images.Media.getBitmap(getContentResolver(),u);}

    void updateSlotVisibility(){
        int count=cardCount();
        for(int side=0;side<2;side++)for(int i=0;i<4;i++)if(sideCells[side][i]!=null)
            sideCells[side][i].setVisibility(i<count?View.VISIBLE:View.GONE);
    }

    ArrayList<Bitmap> prepareCards(Bitmap source,int wanted,ProcessProgress progress){
        if(source==null)throw new IllegalArgumentException("The scanner returned no image.");
        int max=2200;
        float scale=Math.min(1f,max/(float)Math.max(source.getWidth(),source.getHeight()));
        Bitmap work=scale<1f?Bitmap.createScaledBitmap(source,Math.max(1,(int)(source.getWidth()*scale)),Math.max(1,(int)(source.getHeight()*scale)),true):source;

        if(progress!=null)progress.update(2,"Preparing scan…");
        ArrayList<Bitmap> detected=null;
        try{
            detected=detectCardsWithOpenCV(work,wanted,progress);
        }catch(Exception ignored){
            detected=null;
        }

        if(detected!=null&&!detected.isEmpty()){
            if(work!=source)work.recycle();
            return detected;
        }

        // Keep the previous detector as a fallback for scanners/images where no
        // usable four-corner contour can be found.
        if(progress!=null)progress.update(72,"Using backup card detection…");
        ArrayList<Bitmap> fallback=prepareCardsLegacy(work,wanted,progress);
        if(work!=source)work.recycle();
        if(progress!=null)progress.update(90,"Finalizing card orientation…");
        return fallback;
    }

    ArrayList<Bitmap> prepareCardsLegacy(Bitmap work,int wanted,ProcessProgress progress){
        int w=work.getWidth(),h=work.getHeight(),n=w*h;
        int[] px=new int[n];work.getPixels(px,0,w,0,0,w,h);
        int[] bg=estimateBackground(px,w,h);
        boolean[] fg=buildForegroundMask(px,w,h,bg[0],bg[1],bg[2]);
        fg=morphClose(fg,w,h,3);
        boolean[] seen=new boolean[n];
        ArrayDeque<Integer> q=new ArrayDeque<>();
        ArrayList<Rect> boxes=new ArrayList<>();
        int minArea=Math.max(1200,n/9000);
        for(int y=0;y<h;y++)for(int x=0;x<w;x++){
            if(progress!=null&&x==0&&y%(Math.max(1,h/45))==0)progress.update(10+Math.round(y*45f/Math.max(1,h)),"Analyzing scanner image…");
            int idx=y*w+x;
            if(!fg[idx]||seen[idx])continue;
            q.clear();q.add(idx);seen[idx]=true;
            int l=x,r=x,t=y,b=y,area=0;
            while(!q.isEmpty()){
                int z=q.removeFirst(),zx=z%w,zy=z/w;area++;
                l=Math.min(l,zx);r=Math.max(r,zx);t=Math.min(t,zy);b=Math.max(b,zy);
                for(int dy=-1;dy<=1;dy++)for(int dx=-1;dx<=1;dx++){
                    if(dx==0&&dy==0)continue;
                    int xx=zx+dx,yy=zy+dy;
                    if(xx<0||xx>=w||yy<0||yy>=h)continue;
                    int ni=yy*w+xx;
                    if(!seen[ni]&&fg[ni]){seen[ni]=true;q.add(ni);}
                }
            }
            int bw=r-l+1,bh=b-t+1;
            float ratio=bw/(float)Math.max(1,bh);
            if(area>=minArea&&bw>80&&bh>50&&bw<.97f*w&&bh<.97f*h&&ratio>.30f&&ratio<4.5f)
                boxes.add(new Rect(l,t,r+1,b+1));
        }
        boxes.sort((a,b)->Integer.compare(b.width()*b.height(),a.width()*a.height()));
        ArrayList<Bitmap> out=new ArrayList<>();
        ArrayList<Rect> accepted=new ArrayList<>();
        for(Rect box:boxes){
            if(progress!=null)progress.update(56+Math.round(out.size()*24f/Math.max(1,wanted)),"Straightening detected cards…");
            if(out.size()>=wanted)break;
            if(overlapsTooMuch(box,accepted))continue;
            Bitmap card=normalizeDetectedCard(work,box,px,w,h,bg[0],bg[1],bg[2]);
            if(card!=null){out.add(card);accepted.add(box);}
        }
        if(out.isEmpty()){
            Rect fb=findFallbackRegion(px,w,h,bg[0],bg[1],bg[2]);
            if(fb!=null){
                Bitmap card=normalizeDetectedCard(work,fb,px,w,h,bg[0],bg[1],bg[2]);
                if(card!=null)out.add(card);
            }
        }
        if(out.isEmpty())throw new IllegalArgumentException("No ID card detected. The scan was received, but the card could not be separated from the scanner background.");
        return out;
    }

    ArrayList<Bitmap> detectCardsWithOpenCV(Bitmap source,int wanted,ProcessProgress progress){
        ArrayList<Bitmap> out=new ArrayList<>();
        Mat src=new Mat(),gray=new Mat(),blur=new Mat(),edges=new Mat(),kernel=new Mat();
        Utils.bitmapToMat(source,src);
        Imgproc.cvtColor(src,gray,Imgproc.COLOR_RGBA2GRAY);
        Imgproc.GaussianBlur(gray,blur,new Size(5,5),0);
        Imgproc.Canny(blur,edges,35,120);
        kernel=Imgproc.getStructuringElement(Imgproc.MORPH_RECT,new Size(3,3));
        Imgproc.dilate(edges,edges,kernel);
        ArrayList<MatOfPoint> contours=new ArrayList<>();
        Imgproc.findContours(edges,contours,new Mat(),Imgproc.RETR_LIST,Imgproc.CHAIN_APPROX_SIMPLE);

        ArrayList<CardQuad> candidates=new ArrayList<>();
        double total=src.cols()*src.rows();
        double target=CARD_RATIO;

        int contourIndex=0;
        for(MatOfPoint contour:contours){
            contourIndex++;
            if(progress!=null&&contourIndex%Math.max(1,contours.size()/45)==0)progress.update(12+Math.round(contourIndex*45f/Math.max(1,contours.size())),"Detecting card edges…");
            double area=Math.abs(Imgproc.contourArea(contour));
            if(area<total*.0015||area>total*.65) {contour.release();continue;}
            org.opencv.core.Rect bb=Imgproc.boundingRect(contour);
            if(bb.width<80||bb.height<50||bb.width>src.cols()*.97||bb.height>src.rows()*.97){contour.release();continue;}

            MatOfPoint2f c2=new MatOfPoint2f(contour.toArray());
            double peri=Imgproc.arcLength(c2,true);
            MatOfPoint2f approx=new MatOfPoint2f();
            Imgproc.approxPolyDP(c2,approx,0.025*peri,true);
            org.opencv.core.Point[] pts=approx.toArray();

            if(pts.length==4&&Imgproc.isContourConvex(new MatOfPoint(pts))){
                double ratio=quadRatio(pts);
                double ratioScore=Math.max(0,1.0-Math.abs(ratio-target)/target);
                double rectFill=area/(double)Math.max(1,bb.width*bb.height);
                if(ratio>=1.15&&ratio<=2.15&&rectFill>.50&&ratioScore>.62){
                    double score=ratioScore*.55+Math.min(1,rectFill)*.20+Math.min(1,Math.sqrt(area/total)*4)*.25;
                    candidates.add(new CardQuad(pts,score,area));
                }
            }
            approx.release();c2.release();contour.release();
        }

        candidates.sort((a,b)->Double.compare(b.score,a.score));
        ArrayList<org.opencv.core.Point[]> accepted=new ArrayList<>();
        for(CardQuad q:candidates){
            if(progress!=null)progress.update(58+Math.round(out.size()*28f/Math.max(1,wanted)),"Correcting card perspective…");
            if(out.size()>=wanted)break;
            boolean overlap=false;
            Rect qb=quadBounds(q.pts);
            for(org.opencv.core.Point[] old:accepted){
                Rect ob=quadBounds(old);
                int l=Math.max(qb.left,ob.left),t=Math.max(qb.top,ob.top),r=Math.min(qb.right,ob.right),b=Math.min(qb.bottom,ob.bottom);
                if(r>l&&b>t&&(r-l)*(b-t)>Math.min(qb.width()*qb.height(),ob.width()*ob.height())*.45f){overlap=true;break;}
            }
            if(overlap)continue;
            Bitmap card=warpCard(source,q.pts);
            if(card!=null){out.add(card);accepted.add(q.pts);}
        }

        src.release();gray.release();blur.release();edges.release();kernel.release();
        return out;
    }

    static class CardQuad{
        org.opencv.core.Point[] pts;double score,area;
        CardQuad(org.opencv.core.Point[] p,double s,double a){pts=p;score=s;area=a;}
    }

    double quadRatio(org.opencv.core.Point[] p){
        double a=dist(p[0],p[1]),b=dist(p[1],p[2]),c=dist(p[2],p[3]),d=dist(p[3],p[0]);
        double longSide=Math.max((a+c)/2.0,(b+d)/2.0);
        double shortSide=Math.min((a+c)/2.0,(b+d)/2.0);
        return longSide/Math.max(1,shortSide);
    }

    double dist(org.opencv.core.Point a,org.opencv.core.Point b){
        return Math.hypot(a.x-b.x,a.y-b.y);
    }

    Rect quadBounds(org.opencv.core.Point[] p){
        int l=(int)Math.floor(Math.min(Math.min(p[0].x,p[1].x),Math.min(p[2].x,p[3].x)));
        int t=(int)Math.floor(Math.min(Math.min(p[0].y,p[1].y),Math.min(p[2].y,p[3].y)));
        int r=(int)Math.ceil(Math.max(Math.max(p[0].x,p[1].x),Math.max(p[2].x,p[3].x)));
        int b=(int)Math.ceil(Math.max(Math.max(p[0].y,p[1].y),Math.max(p[2].y,p[3].y)));
        return new Rect(Math.max(0,l),Math.max(0,t),Math.max(1,r),Math.max(1,b));
    }

    Bitmap warpCard(Bitmap source,org.opencv.core.Point[] raw){
        org.opencv.core.Point[] p=orderQuad(raw);
        double top=dist(p[0],p[1]),bottom=dist(p[3],p[2]),left=dist(p[0],p[3]),right=dist(p[1],p[2]);
        double width=Math.max(top,bottom),height=Math.max(left,right);
        if(width<height){org.opencv.core.Point tmp=p[0];p[0]=p[3];p[3]=tmp;tmp=p[1];p[1]=p[2];p[2]=tmp;width=Math.max(left,right);height=Math.max(top,bottom);}
        int outW=1400,outH=Math.max(1,Math.round(outW/CARD_RATIO));

        Mat src=new Mat(),dst=new Mat(),from=new Mat(4,1,CvType.CV_32FC2),to=new Mat(4,1,CvType.CV_32FC2),M=new Mat();
        Utils.bitmapToMat(source,src);
        from.put(0,0,p[0].x,p[0].y,p[1].x,p[1].y,p[2].x,p[2].y,p[3].x,p[3].y);
        to.put(0,0,0,0,outW-1,0,outW-1,outH-1,0,outH-1);
        M=Imgproc.getPerspectiveTransform(from,to);
        Imgproc.warpPerspective(src,dst,M,new Size(outW,outH),Imgproc.INTER_LINEAR,Core.BORDER_REPLICATE,new Scalar(255,255,255,255));
        Bitmap out=Bitmap.createBitmap(outW,outH,Bitmap.Config.ARGB_8888);
        Utils.matToBitmap(dst,out);
        src.release();dst.release();from.release();to.release();M.release();
        return out;
    }

    org.opencv.core.Point[] orderQuad(org.opencv.core.Point[] pts){
        org.opencv.core.Point[] o=new org.opencv.core.Point[4];
        double minSum=Double.MAX_VALUE,maxSum=-Double.MAX_VALUE,minDiff=Double.MAX_VALUE,maxDiff=-Double.MAX_VALUE;
        for(org.opencv.core.Point p:pts){
            double sum=p.x+p.y,diff=p.x-p.y;
            if(sum<minSum){minSum=sum;o[0]=p;}
            if(sum>maxSum){maxSum=sum;o[2]=p;}
            if(diff>maxDiff){maxDiff=diff;o[1]=p;}
            if(diff<minDiff){minDiff=diff;o[3]=p;}
        }
        return o;
    }


    int[] estimateBackground(int[] px,int w,int h){
        // Use a quantized color histogram from the outer border instead of an average.
        // Scanner beds often have black rails/corners; averaging those with the white glass
        // makes the entire page look like foreground.
        int[] hist=new int[4096];
        int step=Math.max(1,Math.min(w,h)/180);
        for(int y=0;y<h;y+=step)for(int x=0;x<w;x+=step){
            if(x>=step*8&&y>=step*8&&x<w-step*9&&y<h-step*9)continue;
            int c=px[y*w+x];
            int qr=Color.red(c)>>4,qg=Color.green(c)>>4,qb=Color.blue(c)>>4;
            hist[(qr<<8)|(qg<<4)|qb]++;
        }
        int best=0;
        for(int i=1;i<hist.length;i++)if(hist[i]>hist[best])best=i;
        return new int[]{((best>>8)&15)*16+8,((best>>4)&15)*16+8,(best&15)*16+8};
    }

    boolean[] buildForegroundMask(int[] px,int w,int h,int br,int bg,int bb){
        boolean[] m=new boolean[px.length];
        for(int i=0;i<px.length;i++){
            int c=px[i];
            int r=Color.red(c),g=Color.green(c),b=Color.blue(c);
            int diff=Math.abs(r-br)+Math.abs(g-bg)+Math.abs(b-bb);
            int max=Math.max(r,Math.max(g,b)),min=Math.min(r,Math.min(g,b));
            int sat=max-min;
            m[i]=diff>30 || sat>38;
        }
        return m;
    }

    boolean[] morphClose(boolean[] src,int w,int h,int radius){
        boolean[] dil=new boolean[src.length],out=new boolean[src.length];
        for(int y=0;y<h;y++)for(int x=0;x<w;x++){
            boolean on=false;
            for(int dy=-radius;dy<=radius&&!on;dy++)for(int dx=-radius;dx<=radius;dx++){
                int xx=x+dx,yy=y+dy;
                if(xx>=0&&xx<w&&yy>=0&&yy<h&&src[yy*w+xx]){on=true;break;}
            }
            dil[y*w+x]=on;
        }
        for(int y=0;y<h;y++)for(int x=0;x<w;x++){
            boolean on=true;
            for(int dy=-radius;dy<=radius&&on;dy++)for(int dx=-radius;dx<=radius;dx++){
                int xx=x+dx,yy=y+dy;
                if(xx<0||xx>=w||yy<0||yy>=h||!dil[yy*w+xx]){on=false;break;}
            }
            out[y*w+x]=on;
        }
        return out;
    }

    boolean overlapsTooMuch(Rect a,ArrayList<Rect> accepted){
        for(Rect b:accepted){
            int l=Math.max(a.left,b.left),t=Math.max(a.top,b.top),r=Math.min(a.right,b.right),bt=Math.min(a.bottom,b.bottom);
            if(r>l&&bt>t){
                int inter=(r-l)*(bt-t);
                int smaller=Math.min(a.width()*a.height(),b.width()*b.height());
                if(inter>smaller*.45f)return true;
            }
        }
        return false;
    }

    Bitmap normalizeDetectedCard(Bitmap work,Rect box,int[] px,int w,int h,int br,int bg,int bb){
        int pad=(int)(Math.max(box.width(),box.height())*.05f);
        int l=Math.max(0,box.left-pad),t=Math.max(0,box.top-pad);
        int r=Math.min(w,box.right+pad),b=Math.min(h,box.bottom+pad);
        int bw=r-l,bh=b-t;
        if(bw<60||bh<40)return null;

        boolean[] local=buildLocalMask(work,l,t,r,b,br,bg,bb);
        local=morphClose(local,bw,bh,2);

        // Estimate the card's dominant axis from the foreground pixels.
        // Unlike the previous implementation, the rotation is rendered onto the
        // real scanner-background color, so rotated corners can never become black.
        double sx=0,sy=0,sum=0;
        for(int y=0;y<bh;y++)for(int x=0;x<bw;x++)if(local[y*bw+x]){
            sx+=x;sy+=y;sum++;
        }
        if(sum<80)return null;
        double mx=sx/sum,my=sy/sum,vx=0,vy=0,cov=0;
        for(int y=0;y<bh;y++)for(int x=0;x<bw;x++)if(local[y*bw+x]){
            double dx=x-mx,dy=y-my;vx+=dx*dx;vy+=dy*dy;cov+=dx*dy;
        }
        double angle=.5*Math.atan2(2*cov,vx-vy);
        double deg=Math.toDegrees(angle);
        while(deg>90)deg-=180;
        while(deg<=-90)deg+=180;

        Bitmap crop=rotateCropOnBackground(work,l,t,bw,bh,(float)-deg,Color.rgb(br,bg,bb));
        if(crop==null)return null;

        // Re-estimate the background after rotation. This is important because the
        // crop now contains only the selected card region and its real background.
        int[] cbg=estimateCropBackground(crop);
        Rect content=findForegroundBounds(crop,cbg[0],cbg[1],cbg[2]);
        if(content==null){
            crop.recycle();return null;
        }

        // Tight crop with only a tiny safety margin. Do not retain the old large
        // padding because that was responsible for scanner/background leaking into
        // the saved card.
        int margin=Math.max(1,(int)(Math.min(content.width(),content.height())*.012f));
        int cl=Math.max(0,content.left-margin),ct=Math.max(0,content.top-margin);
        int cr=Math.min(crop.getWidth(),content.right+margin),cb=Math.min(crop.getHeight(),content.bottom+margin);
        if(cr-cl<80||cb-ct<50){crop.recycle();return null;}

        Bitmap exact=Bitmap.createBitmap(crop,cl,ct,cr-cl,cb-ct);
        crop.recycle();

        // ID cards are always saved in landscape orientation.
        if(exact.getWidth()<exact.getHeight()){
            Matrix m=new Matrix();m.postRotate(90);
            Bitmap r2=Bitmap.createBitmap(exact,0,0,exact.getWidth(),exact.getHeight(),m,true);
            exact.recycle();exact=r2;
        }

        // Normalize to the ISO/IEC 7810 ID-1 aspect ratio by removing only excess
        // background. Never stretch the card and never add scanner pixels.
        float ar=exact.getWidth()/(float)Math.max(1,exact.getHeight());
        if(ar>1.05f){
            int targetH=Math.max(1,Math.round(exact.getWidth()/CARD_RATIO));
            if(targetH<exact.getHeight()){
                int y=(exact.getHeight()-targetH)/2;
                Bitmap r3=Bitmap.createBitmap(exact,0,y,exact.getWidth(),targetH);
                exact.recycle();exact=r3;
            }
        }else{
            int targetW=Math.max(1,Math.round(exact.getHeight()*CARD_RATIO));
            if(targetW<exact.getWidth()){
                int x=(exact.getWidth()-targetW)/2;
                Bitmap r3=Bitmap.createBitmap(exact,x,0,targetW,exact.getHeight());
                exact.recycle();exact=r3;
            }
        }
        return exact;
    }

    Bitmap autoOrientCard(Bitmap card){
        if(card==null)return null;
        try{
            int maxW=1000;
            float sc=Math.min(1f,maxW/(float)Math.max(1,card.getWidth()));
            Bitmap small=sc<1f?Bitmap.createScaledBitmap(card,Math.max(1,(int)(card.getWidth()*sc)),Math.max(1,(int)(card.getHeight()*sc)),true):card;
            Bitmap normal=small;
            Matrix rm=new Matrix();rm.postRotate(180);
            Bitmap upside=Bitmap.createBitmap(small,0,0,small.getWidth(),small.getHeight(),rm,true);
            Text a=Tasks.await(textRecognizer.process(InputImage.fromBitmap(normal,0)));
            Text b=Tasks.await(textRecognizer.process(InputImage.fromBitmap(upside,0)));
            int scoreA=orientationTextScore(a),scoreB=orientationTextScore(b);
            if(small!=card)small.recycle();
            if(scoreB>scoreA+3){
                upside=resizeOrientationResultIfNeeded(upside,card);
                return upside;
            }
            upside.recycle();
            return card;
        }catch(Exception e){
            return card;
        }
    }
    int orientationTextScore(Text text){
        if(text==null)return 0;
        int score=0;
        String all=text.getText();
        if(all!=null)score+=Math.min(80,all.trim().length());
        for(Text.TextBlock block:text.getTextBlocks()){
            String s=block.getText();
            if(s!=null)score+=Math.min(20,s.trim().length()/2);
        }
        return score;
    }
    Bitmap resizeOrientationResultIfNeeded(Bitmap rotated,Bitmap original){
        if(rotated.getWidth()==original.getWidth()&&rotated.getHeight()==original.getHeight())return rotated;
        Bitmap out=Bitmap.createScaledBitmap(rotated,original.getWidth(),original.getHeight(),true);
        rotated.recycle();
        return out;
    }

    Bitmap rotateCropOnBackground(Bitmap source,int l,int t,int bw,int bh,float degrees,int background){
        if(bw<=0||bh<=0)return null;
        double rad=Math.toRadians(degrees);
        int outW=Math.max(1,(int)Math.ceil(Math.abs(bw*Math.cos(rad))+Math.abs(bh*Math.sin(rad))));
        int outH=Math.max(1,(int)Math.ceil(Math.abs(bw*Math.sin(rad))+Math.abs(bh*Math.cos(rad))));
        Bitmap out=Bitmap.createBitmap(outW,outH,Bitmap.Config.ARGB_8888);
        Canvas c=new Canvas(out);
        c.drawColor(background);
        Paint p=new Paint(Paint.ANTI_ALIAS_FLAG|Paint.FILTER_BITMAP_FLAG|Paint.DITHER_FLAG);
        c.save();
        c.translate(outW/2f,outH/2f);
        c.rotate(degrees);
        c.drawBitmap(source,l,t,p);
        c.restore();
        return out;
    }


    boolean[] buildLocalMask(Bitmap b,int l,int t,int r,int bot,int br,int bg,int bb){
        int w=r-l,h=bot-t;boolean[] m=new boolean[w*h];
        int[] p=new int[w*h];b.getPixels(p,0,w,l,t,w,h);
        for(int i=0;i<p.length;i++){
            int c=p[i],rr=Color.red(c),gg=Color.green(c),bl=Color.blue(c);
            int diff=Math.abs(rr-br)+Math.abs(gg-bg)+Math.abs(bl-bb);
            int mx=Math.max(rr,Math.max(gg,bl)),mn=Math.min(rr,Math.min(gg,bl));
            m[i]=diff>28||(mx-mn)>35;
        }
        return m;
    }

    int[] estimateCropBackground(Bitmap b){
        int w=b.getWidth(),h=b.getHeight();
        int[] p=new int[Math.max(1,w*h)];b.getPixels(p,0,w,0,0,w,h);
        return estimateBackground(p,w,h);
    }

    Rect findForegroundBounds(Bitmap b,int br,int bg,int bb){
        int w=b.getWidth(),h=b.getHeight(),n=w*h;int[] p=new int[n];b.getPixels(p,0,w,0,0,w,h);
        int l=w,t=h,r=0,bot=0,count=0;
        for(int y=0;y<h;y++)for(int x=0;x<w;x++){
            int c=p[y*w+x],rr=Color.red(c),gg=Color.green(c),bl=Color.blue(c);
            int diff=Math.abs(rr-br)+Math.abs(gg-bg)+Math.abs(bl-bb);
            int sat=Math.max(rr,Math.max(gg,bl))-Math.min(rr,Math.min(gg,bl));
            if(diff>28||sat>35){l=Math.min(l,x);t=Math.min(t,y);r=Math.max(r,x+1);bot=Math.max(bot,y+1);count++;}
        }
        if(count<Math.max(100,w*h/20000)||r<=l||bot<=t)return null;
        return new Rect(l,t,r,bot);
    }

    Rect findFallbackRegion(int[] px,int w,int h,int br,int bg,int bb){
        boolean[] m=buildForegroundMask(px,w,h,br,bg,bb);
        m=morphClose(m,w,h,4);
        int l=w,t=h,r=0,b=0,count=0;
        for(int y=0;y<h;y++)for(int x=0;x<w;x++)if(m[y*w+x]){
            l=Math.min(l,x);t=Math.min(t,y);r=Math.max(r,x+1);b=Math.max(b,y+1);count++;
        }
        if(count<100)return null;
        int margin=(int)(Math.min(w,h)*.01f);
        l=Math.max(0,l-margin);t=Math.max(0,t-margin);r=Math.min(w,r+margin);b=Math.min(h,b+margin);
        if(r-l<w*.05f||b-t<h*.03f)return null;
        return new Rect(l,t,r,b);
    }

    int copies(){try{return Math.max(1,Math.min(9999,Integer.parseInt(copiesEdit.getText().toString().trim())));}catch(Exception e){return 1;}}

    File makePdf()throws Exception{return makePdf(null);}
    interface PdfProgress{void update(int percent,String detail);}
    File makePdf(PdfProgress progress)throws Exception{
        int n=cardCount(),reps=copies();
        for(int i=0;i<n;i++)if(frontUris[i]==null||backUris[i]==null)throw new Exception("Please scan/import both sides for card "+(i+1)+".");
        PdfDocument d=new PdfDocument();int total=n*reps,pages=Math.max(1,(total+7)/8),work=Math.max(1,total*2);
        int[] done=new int[]{0};
        if(progress!=null)progress.update(0,"Starting PDF…");
        for(int page=0;page<pages;page++){
            PdfDocument.Page fp=d.startPage(new PdfDocument.PageInfo.Builder(595,842,page*2+1).create());
            drawSet(fp.getCanvas(),true,page*8,n,reps,done,work,progress);d.finishPage(fp);
            PdfDocument.Page bp=d.startPage(new PdfDocument.PageInfo.Builder(595,842,page*2+2).create());
            drawSet(bp.getCanvas(),false,page*8,n,reps,done,work,progress);d.finishPage(bp);
        }
        if(progress!=null)progress.update(97,"Writing PDF file…");
        File out=new File(getCacheDir(),"EasyCopy_"+new SimpleDateFormat("yyyyMMdd_HHmmss",Locale.US).format(new Date())+".pdf");
        try(FileOutputStream o=new FileOutputStream(out)){d.writeTo(o);}d.close();
        if(progress!=null)progress.update(100,"PDF ready.");
        return out;
    }
    void runPdfJob(String action){
        final Dialog dialog=new Dialog(this);
        LinearLayout box=new LinearLayout(this);box.setOrientation(LinearLayout.VERTICAL);box.setPadding(dp(28),dp(22),dp(28),dp(22));box.setBackgroundColor(Color.WHITE);
        TextView title=tv("Preparing PDF…",20);title.setTypeface(null,Typeface.BOLD);box.addView(title);
        TextView pct=tv("0%",18);pct.setGravity(Gravity.CENTER);box.addView(pct);
        ProgressBar bar=new ProgressBar(this,null,android.R.attr.progressBarStyleHorizontal);bar.setMax(100);bar.setProgress(0);box.addView(bar,new LinearLayout.LayoutParams(-1,dp(18)));
        TextView detail=tv("Preparing pages…",13);detail.setTextColor(Color.rgb(102,112,133));box.addView(detail);
        dialog.setContentView(box);dialog.setCancelable(false);dialog.show();
        Window w=dialog.getWindow();if(w!=null){w.setBackgroundDrawableResource(android.R.color.white);w.setLayout(dp(310),-2);}
        pool.execute(()->{
            try{
                File pdf=makePdf((p,d)->runOnUiThread(()->{bar.setProgress(p);pct.setText(p+"%");detail.setText(d);}));
                runOnUiThread(()->{dialog.dismiss();lastPdf=pdf;performPdfAction(action,pdf);});
            }catch(Exception e){runOnUiThread(()->{dialog.dismiss();toast(e.getMessage());});}
        });
    }
    void performPdfAction(String action,File pdf){
        try{
            if("preview".equals(action))openPdf(pdf);
            else if("save".equals(action)){
                pendingCopy=pdf;Intent i=new Intent(Intent.ACTION_CREATE_DOCUMENT);i.addCategory(Intent.CATEGORY_OPENABLE);i.setType("application/pdf");i.putExtra(Intent.EXTRA_TITLE,pdf.getName());startActivityForResult(i,105);
            }else if("share".equals(action)){
                Intent i=new Intent(Intent.ACTION_SEND);i.setType("application/pdf");i.putExtra(Intent.EXTRA_STREAM,androidx.core.content.FileProvider.getUriForFile(this,"com.easycopy.app.fileprovider",pdf));startActivity(Intent.createChooser(i,"Share EasyCopy PDF"));
            }else if("print".equals(action))printPdfFile(pdf);
        }catch(Exception e){toast(e.getMessage());}
    }
    void printPdfFile(File pdf)throws Exception{
        int pages=((cardCount()*copies()+7)/8)*2;PrintManager pm=(PrintManager)getSystemService(PRINT_SERVICE);
        pm.print("EasyCopy",new PrintDocumentAdapter(){
            public void onLayout(PrintAttributes a,PrintAttributes b,CancellationSignal c,LayoutResultCallback x,Bundle z){x.onLayoutFinished(new PrintDocumentInfo.Builder("EasyCopy.pdf").setContentType(PrintDocumentInfo.CONTENT_TYPE_DOCUMENT).setPageCount(pages).build(),true);}
            public void onWrite(PageRange[] p,ParcelFileDescriptor d,CancellationSignal c,WriteResultCallback x){
                try(InputStream in=new FileInputStream(pdf);OutputStream o=new FileOutputStream(d.getFileDescriptor())){byte[] bb=new byte[8192];int nn;while((nn=in.read(bb))>0)o.write(bb,0,nn);o.flush();x.onWriteFinished(new PageRange[]{PageRange.ALL_PAGES});}catch(Exception e){x.onWriteFailed(e.getMessage());}
            }
        },new PrintAttributes.Builder().setMediaSize(PrintAttributes.MediaSize.ISO_A4).build());
    }
    void drawSet(Canvas c,boolean front,int start,int n,int reps,int[] done,int work,PdfProgress progress){
        c.drawColor(Color.WHITE);
        float cardW=595f*CARD_W_MM/210f;
        float cardH=842f*CARD_H_MM/297f;
        float gapX=24f;
        float gapY=10f;
        float marginX=(595f-(2f*cardW+gapX))/2f;
        float marginY=(842f-(4f*cardH+3f*gapY))/2f;
        Paint p=new Paint(Paint.ANTI_ALIAS_FLAG|Paint.FILTER_BITMAP_FLAG|Paint.DITHER_FLAG);
        for(int k=0;k<8;k++){
            int global=start+k;
            if(global>=n*reps)break;
            int ci=global%n;
            int slot=front?k:(k/2)*2+(1-(k%2));
            Uri u=front?frontUris[ci]:backUris[ci];
            try{
                Bitmap im=load(u);
                float nx=marginX+(slot%2)*(cardW+gapX);
                float x=nx;
                float y=marginY+(slot/2)*(cardH+gapY);
                float srcW=im.getWidth(),srcH=im.getHeight();
                float scale=Math.min(cardW/Math.max(1,srcW),cardH/Math.max(1,srcH));
                float dw=srcW*scale,dh=srcH*scale;
                float dx=x+(cardW-dw)/2f,dy=y+(cardH-dh)/2f;
                c.drawBitmap(im,null,new RectF(dx,dy,dx+dw,dy+dh),p);
                im.recycle();
            }catch(Exception ignored){}
            done[0]++;
            if(progress!=null)progress.update(Math.min(95,Math.round(done[0]*95f/work)),(front?"Front":"Back")+" cards: "+done[0]+"/"+work);
        }
    }


    void showImageEditor(Bitmap original){
        final Dialog dialog=new Dialog(this);
        LinearLayout root=new LinearLayout(this);root.setOrientation(LinearLayout.VERTICAL);root.setPadding(dp(12),dp(8),dp(12),dp(12));root.setBackgroundColor(Color.WHITE);
        TextView help=tv("Move • pinch to zoom • rotate • stretch • choose print frame",13);help.setTextColor(Color.rgb(90,100,120));root.addView(help);
        ImageEditorView editor=new ImageEditorView(this,original);root.addView(editor,new LinearLayout.LayoutParams(-1,0,1));

        TextView degreeText=tv("Rotation: 0°",14);degreeText.setGravity(Gravity.CENTER);root.addView(degreeText);
        SeekBar degrees=new SeekBar(this);degrees.setMax(360);degrees.setProgress(180);root.addView(degrees,new LinearLayout.LayoutParams(-1,dp(40)));

        LinearLayout orient=new LinearLayout(this);orient.setGravity(Gravity.CENTER_VERTICAL);
        TextView ot=tv("Print frame",14);ot.setTypeface(null,Typeface.BOLD);orient.addView(ot,new LinearLayout.LayoutParams(0,dp(46),1));
        Button portrait=actionBtn("Portrait",Color.rgb(238,242,255),Color.rgb(55,48,163));
        Button landscape=actionBtn("Landscape",Color.rgb(238,242,255),Color.rgb(55,48,163));
        orient.addView(portrait,new LinearLayout.LayoutParams(dp(108),dp(46)));orient.addView(landscape,new LinearLayout.LayoutParams(dp(108),dp(46)));root.addView(orient);

        TextView stretchText=tv("Stretch 100% W • 100% H",14);stretchText.setGravity(Gravity.CENTER);root.addView(stretchText);
        SeekBar stretchX=new SeekBar(this);stretchX.setMax(200);stretchX.setProgress(100);root.addView(stretchX,new LinearLayout.LayoutParams(-1,dp(32)));
        SeekBar stretchY=new SeekBar(this);stretchY.setMax(200);stretchY.setProgress(100);root.addView(stretchY,new LinearLayout.LayoutParams(-1,dp(32)));

        LinearLayout tools=new LinearLayout(this);tools.setGravity(Gravity.CENTER);
        Button fit=actionBtn("Fit",Color.rgb(238,242,255),Color.rgb(55,48,163));
        Button reset=actionBtn("Reset",Color.rgb(238,242,255),Color.rgb(55,48,163));
        tools.addView(fit,new LinearLayout.LayoutParams(0,dp(44),1));tools.addView(reset,new LinearLayout.LayoutParams(0,dp(44),1));root.addView(tools);
        Button print=actionBtn("Print edited image",Color.rgb(18,183,106),Color.WHITE);root.addView(print,new LinearLayout.LayoutParams(-1,dp(50)));

        degrees.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener(){public void onProgressChanged(SeekBar s,int p,boolean from){editor.rotation=p-180f;degreeText.setText("Rotation: "+Math.round(editor.rotation)+"°");editor.invalidate();}public void onStartTrackingTouch(SeekBar s){}public void onStopTrackingTouch(SeekBar s){}});
        stretchX.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener(){public void onProgressChanged(SeekBar s,int p,boolean from){editor.stretchX=Math.max(.5f,p/100f);stretchText.setText("Stretch "+Math.round(editor.stretchX*100)+"% W • "+Math.round(editor.stretchY*100)+"% H");editor.invalidate();}public void onStartTrackingTouch(SeekBar s){}public void onStopTrackingTouch(SeekBar s){}});
        stretchY.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener(){public void onProgressChanged(SeekBar s,int p,boolean from){editor.stretchY=Math.max(.5f,p/100f);stretchText.setText("Stretch "+Math.round(editor.stretchX*100)+"% W • "+Math.round(editor.stretchY*100)+"% H");editor.invalidate();}public void onStartTrackingTouch(SeekBar s){}public void onStopTrackingTouch(SeekBar s){}});
        portrait.setOnClickListener(v->{editor.landscape=false;editor.invalidate();});landscape.setOnClickListener(v->{editor.landscape=true;editor.invalidate();});
        fit.setOnClickListener(v->{editor.fit();degrees.setProgress(180);stretchX.setProgress(100);stretchY.setProgress(100);});
        reset.setOnClickListener(v->{editor.fit();degrees.setProgress(180);stretchX.setProgress(100);stretchY.setProgress(100);});
        print.setOnClickListener(v->{try{Bitmap out=editor.exportCrop();boolean land=editor.landscape;dialog.dismiss();printBitmap(out,land);}catch(Exception e){toast(e.getMessage());}});
        dialog.setContentView(root);dialog.show();Window w=dialog.getWindow();if(w!=null){w.setBackgroundDrawableResource(android.R.color.white);w.setLayout(-1,-1);}
    }

    void printBitmap(Bitmap bitmap,boolean landscape)throws Exception{
        if(bitmap==null)throw new Exception("Could not prepare the image.");
        int pw=landscape?842:595,ph=landscape?595:842;
        PdfDocument d=new PdfDocument();PdfDocument.Page page=d.startPage(new PdfDocument.PageInfo.Builder(pw,ph,1).create());
        Canvas cc=page.getCanvas();cc.drawColor(Color.WHITE);Paint p=new Paint(Paint.ANTI_ALIAS_FLAG|Paint.FILTER_BITMAP_FLAG|Paint.DITHER_FLAG);
        float margin=28f,aw=pw-margin*2,ah=ph-margin*2,scale=Math.min(aw/bitmap.getWidth(),ah/bitmap.getHeight()),dw=bitmap.getWidth()*scale,dh=bitmap.getHeight()*scale;
        cc.drawBitmap(bitmap,null,new RectF((pw-dw)/2f,(ph-dh)/2f,(pw+dw)/2f,(ph+dh)/2f),p);d.finishPage(page);
        File f=new File(getCacheDir(),"EasyCopy_image_"+System.currentTimeMillis()+".pdf");try(FileOutputStream o=new FileOutputStream(f)){d.writeTo(o);}d.close();bitmap.recycle();
        PrintManager pm=(PrintManager)getSystemService(PRINT_SERVICE);
        pm.print("EasyCopy Image",new PrintDocumentAdapter(){
            public void onLayout(PrintAttributes a,PrintAttributes b,CancellationSignal cs,LayoutResultCallback x,Bundle z){x.onLayoutFinished(new PrintDocumentInfo.Builder("EasyCopy_Image.pdf").setContentType(PrintDocumentInfo.CONTENT_TYPE_DOCUMENT).setPageCount(1).build(),true);}
            public void onWrite(PageRange[] pages,ParcelFileDescriptor fd,CancellationSignal cs,WriteResultCallback x){try(InputStream in=new FileInputStream(f);OutputStream o=new FileOutputStream(fd.getFileDescriptor())){byte[] buf=new byte[8192];int n;while((n=in.read(buf))>0)o.write(buf,0,n);o.flush();x.onWriteFinished(new PageRange[]{PageRange.ALL_PAGES});}catch(Exception e){x.onWriteFailed(e.getMessage());}}
        },new PrintAttributes.Builder().setMediaSize(landscape?PrintAttributes.MediaSize.ISO_A4.asLandscape():PrintAttributes.MediaSize.ISO_A4).build());
    }

    class ImageEditorView extends View{
        Bitmap image;Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG|Paint.FILTER_BITMAP_FLAG);float zoom=1f,rotation=0f,tx=0f,ty=0f,stretchX=1f,stretchY=1f,lastX,lastY;boolean dragging,landscape=false;ScaleGestureDetector scaleDetector;
        ImageEditorView(Context c,Bitmap b){super(c);image=b;setBackgroundColor(Color.rgb(35,38,45));scaleDetector=new ScaleGestureDetector(c,new ScaleGestureDetector.SimpleOnScaleGestureListener(){public boolean onScale(ScaleGestureDetector d){zoom=Math.max(.25f,Math.min(6f,zoom*d.getScaleFactor()));invalidate();return true;}});}
        protected void onDraw(Canvas c){
            super.onDraw(c);if(image==null)return;
            float fit=Math.min(getWidth()*.82f/image.getWidth(),getHeight()*.62f/image.getHeight());
            Matrix m=new Matrix();m.postScale(fit*zoom*stretchX,fit*zoom*stretchY,image.getWidth()/2f,image.getHeight()/2f);m.postRotate(rotation,image.getWidth()/2f,image.getHeight()/2f);m.postTranslate(getWidth()/2f-image.getWidth()/2f+tx,getHeight()/2f-image.getHeight()/2f+ty);
            c.drawBitmap(image,m,paint);
            RectF f=frameRect();Paint shade=new Paint();shade.setColor(Color.argb(150,0,0,0));c.drawRect(0,0,getWidth(),f.top,shade);c.drawRect(0,f.bottom,getWidth(),getHeight(),shade);c.drawRect(0,f.top,f.left,f.bottom,shade);c.drawRect(f.right,f.top,getWidth(),f.bottom,shade);
            Paint border=new Paint(Paint.ANTI_ALIAS_FLAG);border.setStyle(Paint.Style.STROKE);border.setStrokeWidth(dp(2));border.setColor(Color.WHITE);c.drawRect(f,border);
        }
        RectF frameRect(){float fw=getWidth()*.90f,ratio=landscape?(297f/210f):(210f/297f),fh=Math.min(getHeight()*.72f,fw/ratio),l=(getWidth()-fw)/2f,t=(getHeight()-fh)/2f;return new RectF(l,t,l+fw,t+fh);}
        public boolean onTouchEvent(MotionEvent e){
            scaleDetector.onTouchEvent(e);
            if(e.getPointerCount()==1){
                if(e.getAction()==MotionEvent.ACTION_DOWN){lastX=e.getX();lastY=e.getY();dragging=true;}
                else if(e.getAction()==MotionEvent.ACTION_MOVE&&dragging){tx+=e.getX()-lastX;ty+=e.getY()-lastY;lastX=e.getX();lastY=e.getY();invalidate();}
                else if(e.getAction()==MotionEvent.ACTION_UP)dragging=false;
            }return true;
        }
        void fit(){zoom=1f;tx=0f;ty=0f;rotation=0f;stretchX=1f;stretchY=1f;invalidate();}
        Bitmap exportCrop(){
            RectF f=frameRect();int ow=Math.max(1,(int)f.width()),oh=Math.max(1,(int)f.height());Bitmap out=Bitmap.createBitmap(ow,oh,Bitmap.Config.ARGB_8888);Canvas cc=new Canvas(out);cc.drawColor(Color.WHITE);
            float fit=Math.min(getWidth()*.82f/image.getWidth(),getHeight()*.62f/image.getHeight());Matrix m=new Matrix();m.postScale(fit*zoom*stretchX,fit*zoom*stretchY,image.getWidth()/2f,image.getHeight()/2f);m.postRotate(rotation,image.getWidth()/2f,image.getHeight()/2f);m.postTranslate(getWidth()/2f-image.getWidth()/2f+tx-f.left,getHeight()/2f-image.getHeight()/2f+ty-f.top);cc.drawBitmap(image,m,paint);return out;
        }
    }

    File lastPdf;
    void safePdf(){runPdfJob("preview");}
    void savePdf(){runPdfJob("save");}
    void openPdf(File f){
        try{Uri u=androidx.core.content.FileProvider.getUriForFile(this,"com.easycopy.app.fileprovider",f);Intent i=new Intent(Intent.ACTION_VIEW);i.setDataAndType(u,"application/pdf");i.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);startActivity(i);}catch(Exception e){toast("No PDF viewer is installed.");}
    }
    void openPdf(Uri u){
        try{Intent i=new Intent(Intent.ACTION_VIEW);i.setDataAndType(u,"application/pdf");i.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);startActivity(i);}catch(Exception e){toast("PDF saved, but no PDF viewer is installed.");}
    }
    void sharePdf(){runPdfJob("share");}
    void printPdf(){runPdfJob("print");}
    @Override protected void onDestroy(){try{textRecognizer.close();}catch(Exception ignored){}super.onDestroy();}
    void toast(String s){Toast.makeText(this,s,Toast.LENGTH_LONG).show();}
}