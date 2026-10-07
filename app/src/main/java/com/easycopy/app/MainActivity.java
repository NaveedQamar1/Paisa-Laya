package com.easycopy.app;

import android.app.*;
import android.content.*;
import android.graphics.*;
import android.net.Uri;
import android.os.*;
import android.provider.MediaStore;
import android.print.*;
import android.view.*;
import android.widget.*;
import java.io.*;
import java.text.SimpleDateFormat;
import java.util.*;

public class MainActivity extends Activity {
    private static final int REQ_FRONT = 101, REQ_BACK = 102, REQ_IMPORT_FRONT = 103, REQ_IMPORT_BACK = 104, REQ_CREATE_PDF = 105;
    private ImageView frontPreview, backPreview;
    private Uri frontUri, backUri, cameraUri;
    private EditText copiesEdit;
    private CheckBox grayscaleBox;
    private TextView status;

    @Override public void onCreate(Bundle b) { super.onCreate(b); buildUi(); }
    private int dp(float v){ return (int)(v*getResources().getDisplayMetrics().density+0.5f); }
    private TextView label(String s, int size){ TextView t=new TextView(this); t.setText(s); t.setTextSize(size); t.setTextColor(Color.DKGRAY); t.setPadding(0,dp(6),0,dp(6)); return t; }
    private Button button(String s){ Button b=new Button(this); b.setText(s); return b; }

    private void buildUi(){
        ScrollView scroll=new ScrollView(this);
        LinearLayout root=new LinearLayout(this); root.setOrientation(LinearLayout.VERTICAL); root.setPadding(dp(18),dp(12),dp(18),dp(18));
        TextView title=label("EasyCopy",30); title.setTextColor(Color.rgb(45,45,100)); title.setTypeface(null,Typeface.BOLD); root.addView(title);
        root.addView(label("CNIC copier • A4 Portrait • 2 × 4 • Duplex",14));
        LinearLayout steps=new LinearLayout(this); steps.setOrientation(LinearLayout.VERTICAL);
        Button scanF=button("1. Scan FRONT (F)"); Button importF=button("Import FRONT from device / SD");
        frontPreview=preview(); steps.addView(scanF); steps.addView(importF); steps.addView(frontPreview,new LinearLayout.LayoutParams(-1,dp(90)));
        Button scanB=button("2. Scan BACK (B)"); Button importB=button("Import BACK from device / SD");
        backPreview=preview(); steps.addView(scanB); steps.addView(importB); steps.addView(backPreview,new LinearLayout.LayoutParams(-1,dp(90))); root.addView(steps);
        root.addView(label("3. Number of complete CNIC copies",16));
        copiesEdit=new EditText(this); copiesEdit.setInputType(2); copiesEdit.setText("1"); copiesEdit.setSelectAllOnFocus(true); root.addView(copiesEdit,new LinearLayout.LayoutParams(-1,dp(55)));
        grayscaleBox=new CheckBox(this); grayscaleBox.setText("Grayscale / economical copy"); root.addView(grayscaleBox);
        root.addView(label("Fixed layout: A4 Portrait • 2 columns × 4 rows\n1  2\n3  4\n5  6\n7  8\nFront and Back use identical positions for duplex printing.",14));
        Button pdf=button("Create PDF / Preview"); Button print=button("PRINT — Duplex A4"); Button save=button("Save PDF to device");
        root.addView(pdf); root.addView(print); root.addView(save);
        status=label("Ready. Start with the FRONT side.",13); status.setTextColor(Color.GRAY); root.addView(status);
        scanF.setOnClickListener(v->capture(true)); importF.setOnClickListener(v->pick(true)); scanB.setOnClickListener(v->capture(false)); importB.setOnClickListener(v->pick(false));
        pdf.setOnClickListener(v->createPdf()); print.setOnClickListener(v->printPdf()); save.setOnClickListener(v->savePdf());
        scroll.addView(root); setContentView(scroll);
    }
    private ImageView preview(){ ImageView v=new ImageView(this); v.setBackgroundColor(Color.LTGRAY); v.setScaleType(ImageView.ScaleType.CENTER_INSIDE); return v; }

    private void capture(boolean front){
        try{
            String name="EasyCopy_"+(front?"F":"B")+"_"+System.currentTimeMillis()+".jpg";
            ContentValues cv=new ContentValues(); cv.put(MediaStore.Images.Media.DISPLAY_NAME,name); cv.put(MediaStore.Images.Media.MIME_TYPE,"image/jpeg"); cv.put(MediaStore.Images.Media.RELATIVE_PATH,"Pictures/EasyCopy");
            cameraUri=getContentResolver().insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI,cv);
            Intent i=new Intent(MediaStore.ACTION_IMAGE_CAPTURE); i.putExtra(MediaStore.EXTRA_OUTPUT,cameraUri); startActivityForResult(i,front?REQ_FRONT:REQ_BACK);
        }catch(Exception e){toast("Camera could not be opened: "+e.getMessage());}
    }
    private void pick(boolean front){
        Intent i=new Intent(Intent.ACTION_OPEN_DOCUMENT); i.addCategory(Intent.CATEGORY_OPENABLE); i.setType("image/*"); i.putExtra(Intent.EXTRA_ALLOW_MULTIPLE,false); startActivityForResult(i,front?REQ_IMPORT_FRONT:REQ_IMPORT_BACK);
    }
    @Override protected void onActivityResult(int r,int c,Intent d){
        super.onActivityResult(r,c,d);
        if(r==REQ_CREATE_PDF){
            if(c==RESULT_OK && d!=null && d.getData()!=null && pendingCopy!=null){
                try(OutputStream out=getContentResolver().openOutputStream(d.getData()); InputStream in=new FileInputStream(pendingCopy)){
                    byte[] buf=new byte[8192]; int n; while((n=in.read(buf))>0) out.write(buf,0,n); status.setText("PDF saved successfully.");
                }catch(Exception e){toast("Could not save PDF: "+e.getMessage());}
            } return;
        }
        if(c!=RESULT_OK) return;
        Uri u=null; if(r==REQ_FRONT||r==REQ_BACK) u=cameraUri; else if(d!=null) u=d.getData();
        if(u==null)return;
        if(r==REQ_FRONT||r==REQ_IMPORT_FRONT){frontUri=u; frontPreview.setImageURI(u); status.setText("Front F loaded. Now scan/import the BACK B.");}
        else {backUri=u; backPreview.setImageURI(u); status.setText("Both F and B are loaded. Choose copies and print.");}
    }
    private int copies(){ try{return Math.max(1,Math.min(9999,Integer.parseInt(copiesEdit.getText().toString().trim())));}catch(Exception e){return 1;} }
    private Bitmap load(Uri u) throws IOException { return MediaStore.Images.Media.getBitmap(getContentResolver(),u); }
    private Bitmap prepare(Bitmap src){
        if(!grayscaleBox.isChecked()) return src;
        Bitmap g=Bitmap.createBitmap(src.getWidth(),src.getHeight(),Bitmap.Config.ARGB_8888); Canvas c=new Canvas(g); Paint p=new Paint(Paint.ANTI_ALIAS_FLAG);
        ColorMatrix m=new ColorMatrix(); m.setSaturation(0); p.setColorFilter(new ColorMatrixColorFilter(m)); c.drawBitmap(src,0,0,p); return g;
    }
    private File makePdf() throws Exception {
        if(frontUri==null||backUri==null) throw new IllegalStateException("Please load both FRONT (F) and BACK (B) first.");
        Bitmap f=prepare(load(frontUri)), b=prepare(load(backUri)); PdfDocument doc=new PdfDocument(); int total=copies(); int sheets=(total+7)/8;
        for(int s=0;s<sheets;s++){
            int start=s*8;
            PdfDocument.Page fp=doc.startPage(new PdfDocument.PageInfo.Builder(595,842,s*2+1).create()); drawA4(fp.getCanvas(),f,total,start); doc.finishPage(fp);
            PdfDocument.Page bp=doc.startPage(new PdfDocument.PageInfo.Builder(595,842,s*2+2).create()); drawA4(bp.getCanvas(),b,total,start); doc.finishPage(bp);
        }
        File out=new File(getCacheDir(),"EasyCopy_"+new SimpleDateFormat("yyyyMMdd_HHmmss",Locale.US).format(new Date())+".pdf");
        FileOutputStream os=new FileOutputStream(out); doc.writeTo(os); os.close(); doc.close(); return out;
    }
    private void drawA4(Canvas c, Bitmap image, int total, int start){
        c.drawColor(Color.WHITE); Paint p=new Paint(Paint.ANTI_ALIAS_FLAG|Paint.FILTER_BITMAP_FLAG); p.setStyle(Paint.Style.STROKE); p.setColor(Color.LTGRAY); p.setStrokeWidth(0.6f);
        float margin=18f,gapX=8f,gapY=8f,cellW=(595-2*margin-gapX)/2f,cellH=(842-2*margin-3*gapY)/4f;
        for(int slot=0;slot<8;slot++){
            int n=start+slot;if(n>=total)break;int col=slot%2,row=slot/2;float x=margin+col*(cellW+gapX),y=margin+row*(cellH+gapY);
            RectF cell=new RectF(x,y,x+cellW,y+cellH);c.drawRect(cell,p);
            float scale=Math.min((cellW-6)/image.getWidth(),(cellH-6)/image.getHeight());float w=image.getWidth()*scale,h=image.getHeight()*scale;
            c.drawBitmap(image,null,new RectF(x+(cellW-w)/2,y+(cellH-h)/2,x+(cellW+w)/2,y+(cellH+h)/2),new Paint(Paint.ANTI_ALIAS_FLAG|Paint.FILTER_BITMAP_FLAG));
        }
    }
    private void createPdf(){try{File f=makePdf();status.setText("PDF created: "+f.getName()+". Use Save PDF or Print.");}catch(Exception e){toast(e.getMessage());}}
    private void printPdf(){
        try{File f=makePdf();PrintManager pm=(PrintManager)getSystemService(PRINT_SERVICE);
            pm.print("EasyCopy",new PdfPrintAdapter(f,(copies()+7)/8*2),new PrintAttributes.Builder().setMediaSize(PrintAttributes.MediaSize.ISO_A4).setColorMode(PrintAttributes.COLOR_MODE_COLOR).build());
            status.setText("Print dialog opened. Select A4 and duplex/both sides in printer settings.");
        }catch(Exception e){toast(e.getMessage());}
    }
    private void savePdf(){try{File f=makePdf();Intent i=new Intent(Intent.ACTION_CREATE_DOCUMENT);i.setType("application/pdf");i.putExtra(Intent.EXTRA_TITLE,f.getName());pendingCopy=f;startActivityForResult(i,REQ_CREATE_PDF);}catch(Exception e){toast(e.getMessage());}}
    private File pendingCopy;
    private class PdfPrintAdapter extends PrintDocumentAdapter{
        File file;int pageCount;PdfPrintAdapter(File f,int count){file=f;pageCount=count;}
        public void onLayout(PrintAttributes oldA,PrintAttributes newA,CancellationSignal cs,LayoutResultCallback cb,Bundle extras){
            if(cs.isCanceled()){cb.onLayoutCancelled();return;}cb.onLayoutFinished(new PrintDocumentInfo.Builder(file.getName()).setContentType(PrintDocumentInfo.CONTENT_TYPE_DOCUMENT).setPageCount(pageCount).build(),!newA.equals(oldA));
        }
        public void onWrite(PageRange[] pages,ParcelFileDescriptor dest,CancellationSignal cs,WriteResultCallback cb){
            try{InputStream in=new FileInputStream(file);OutputStream out=new FileOutputStream(dest.getFileDescriptor());byte[] buf=new byte[8192];int n;
                while((n=in.read(buf))>0){if(cs.isCanceled()){in.close();cb.onWriteCancelled();return;}out.write(buf,0,n);}out.flush();in.close();cb.onWriteFinished(new PageRange[]{PageRange.ALL_PAGES});
            }catch(Exception e){cb.onWriteFailed(e.getMessage());}
        }
    }
    private void toast(String s){Toast.makeText(this,s,Toast.LENGTH_LONG).show();}
}