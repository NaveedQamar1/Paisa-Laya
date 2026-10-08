using System.Drawing;
using System.Drawing.Printing;
using System.Diagnostics;

namespace EasyCopy.Desktop;

public sealed class MainForm : Form
{
    readonly PictureBox[] front=new PictureBox[4], back=new PictureBox[4];
    readonly string[] frontFiles=new string[4], backFiles=new string[4];
    readonly ComboBox count=new(), dpi=new(), color=new(), source=new(), scanners=new();
    readonly NumericUpDown copies=new();
    readonly ProgressBar progress=new();
    readonly Label status=new(), scannerStatus=new();
    readonly Button scanF=new(), scanB=new();
    string selectedScanner;

    public MainForm()
    {
        Text="EasyCopy — ID Card Copier"; Width=1100; Height=850; MinimumSize=new Size(900,700);
        StartPosition=FormStartPosition.CenterScreen; BackColor=Color.FromArgb(247,248,252);
        BuildUi(); Shown+=async(_,__)=>await DiscoverAsync();
    }

    Button Btn(string text,bool primary=false){var b=new Button{Text=text,Height=42,FlatStyle=FlatStyle.Flat,BackColor=primary?Color.FromArgb(55,48,163):Color.FromArgb(238,242,255),ForeColor=primary?Color.White:Color.FromArgb(55,48,163),Font=new Font("Segoe UI",10,FontStyle.Bold)};b.FlatAppearance.BorderSize=0;return b;}
    GroupBox Box(string title,int h){return new GroupBox{Text=title,Font=new Font("Segoe UI",12,FontStyle.Bold),ForeColor=Color.FromArgb(24,32,51),Padding=new Padding(12),Dock=DockStyle.Top,Height=h};}
    PictureBox Preview()=>new PictureBox{Dock=DockStyle.Fill,BackColor=Color.FromArgb(239,241,246),SizeMode=PictureBoxSizeMode.Zoom};

    void BuildUi()
    {
        var root=new TableLayoutPanel{Dock=DockStyle.Fill,ColumnCount=1,RowCount=6,Padding=new Padding(18),AutoScroll=true};
        root.RowStyles.Add(new RowStyle(SizeType.Absolute,95));root.RowStyles.Add(new RowStyle(SizeType.Absolute,135));root.RowStyles.Add(new RowStyle(SizeType.Absolute,90));root.RowStyles.Add(new RowStyle(SizeType.Absolute,365));root.RowStyles.Add(new RowStyle(SizeType.Absolute,105));root.RowStyles.Add(new RowStyle(SizeType.Percent,100));

        var hero=new Panel{Dock=DockStyle.Fill,BackColor=Color.FromArgb(55,48,163),Padding=new Padding(20)};
        hero.Controls.Add(new Label{Text="EasyCopy",Dock=DockStyle.Top,Height=44,ForeColor=Color.White,Font=new Font("Segoe UI",24,FontStyle.Bold)});
        hero.Controls.Add(new Label{Text="Scan • Copy • Print • Share — Windows edition",Dock=DockStyle.Fill,ForeColor=Color.White});
        root.Controls.Add(hero,0,0);

        var net=Box("Network scanner",125);
        scannerStatus.Text="Searching for compatible eSCL scanners…";scannerStatus.Dock=DockStyle.Top;scannerStatus.Height=25;scannerStatus.ForeColor=Color.DimGray;
        scanners.DropDownStyle=ComboBoxStyle.DropDownList;scanners.Dock=DockStyle.Top;scanners.Height=30;
        scanners.SelectedIndexChanged+=(_,__)=>{if(scanners.SelectedIndex>=0)selectedScanner=scanners.SelectedItem.ToString().Split(" | ").Last();};
        var find=Btn("Find Scanners");find.Dock=DockStyle.Right;find.Width=150;find.Click+=async(_,__)=>await DiscoverAsync();
        net.Controls.Add(find);net.Controls.Add(scanners);net.Controls.Add(scannerStatus);root.Controls.Add(net,0,1);

        var set=Box("Scan settings",80);
        dpi.Items.AddRange(new object[]{"150 DPI","200 DPI","300 DPI","600 DPI"});dpi.SelectedIndex=2;dpi.Location=new Point(15,30);dpi.Width=150;
        color.Items.AddRange(new object[]{"Color","Grayscale","Black & White"});color.SelectedIndex=0;color.Location=new Point(180,30);color.Width=150;
        source.Items.AddRange(new object[]{"Platen / Glass","Feeder","Duplex ADF"});source.SelectedIndex=0;source.Location=new Point(345,30);source.Width=170;
        set.Controls.AddRange(new Control[]{dpi,color,source});root.Controls.Add(set,0,2);

        var id=Box("ID card copier",350);
        id.Controls.Add(new Label{Text="Place 1 to 4 cards anywhere on the scanner glass. EasyCopy scans the full area, finds complete cards, straightens them and pairs each front with its own back.",Dock=DockStyle.Top,Height=45,ForeColor=Color.DimGray});
        id.Controls.Add(new Label{Text="Different ID cards",Location=new Point(15,60),AutoSize=true});
        count.Items.AddRange(new object[]{"1 card","2 cards","3 cards","4 cards"});count.SelectedIndex=0;count.Location=new Point(180,55);count.Width=130;count.SelectedIndexChanged+=(_,__)=>Slots();
        id.Controls.Add(count);
        var tabs=new TabControl{Dock=DockStyle.Fill,Top=95};
        var tf=new TabPage("FRONT SIDE"); var tb=new TabPage("BACK SIDE");
        for(int i=0;i<4;i++){front[i]=Preview();back[i]=Preview();tf.Controls.Add(MakeCell(front[i],i));tb.Controls.Add(MakeCell(back[i],i));}
        id.Controls.Add(tabs);tabs.Controls.Add(tf);tabs.Controls.Add(tb);
        scanF.Text="Scan all fronts";scanF.Width=170;scanF.Height=42;scanF.Location=new Point(15,265);scanF.BackColor=Color.FromArgb(55,48,163);scanF.ForeColor=Color.White;scanF.FlatStyle=FlatStyle.Flat;scanF.Click+=async(_,__)=>await ScanAsync(true);
        scanB.Text="Scan all backs";scanB.Width=170;scanB.Height=42;scanB.Location=new Point(195,265);scanB.BackColor=Color.FromArgb(55,48,163);scanB.ForeColor=Color.White;scanB.FlatStyle=FlatStyle.Flat;scanB.Click+=async(_,__)=>await ScanAsync(false);
        var impF=Btn("Import fronts");impF.Location=new Point(375,265);impF.Width=150;impF.Click+=(_,__)=>Import(true);
        var impB=Btn("Import backs");impB.Location=new Point(535,265);impB.Width=150;impB.Click+=(_,__)=>Import(false);
        id.Controls.AddRange(new Control[]{scanF,scanB,impF,impB});root.Controls.Add(id,0,3);

        var outBox=Box("Output",95);
        outBox.Controls.Add(new Label{Text="Copies of each complete set",Location=new Point(15,35),AutoSize=true});
        copies.Minimum=1;copies.Maximum=9999;copies.Value=1;copies.Width=80;copies.Location=new Point(210,30);outBox.Controls.Add(copies);
        var prev=Btn("Preview PDF",true);prev.Location=new Point(330,27);prev.Width=130;prev.Click+=(_,__)=>RunPdf("preview");
        var save=Btn("Save PDF");save.Location=new Point(470,27);save.Width=120;save.Click+=(_,__)=>RunPdf("save");
        var print=Btn("Print A4 Duplex");print.Location=new Point(600,27);print.Width=145;print.Click+=(_,__)=>PrintSets();
        var image=Btn("Image printer");image.Location=new Point(755,27);image.Width=130;image.Click+=(_,__)=>ImagePrinter();
        outBox.Controls.AddRange(new Control[]{prev,save,print,image});root.Controls.Add(outBox,0,4);

        var foot=new Panel{Dock=DockStyle.Fill};progress.Dock=DockStyle.Top;progress.Height=18;status.Text="Ready. Connect a network scanner or import images.";status.Dock=DockStyle.Top;status.Height=30;status.ForeColor=Color.DimGray;foot.Controls.Add(status);foot.Controls.Add(progress);root.Controls.Add(foot,0,5);
        Controls.Add(root);Slots();
    }

    Control MakeCell(PictureBox p,int i){var panel=new Panel{Dock=DockStyle.Left,Width=210,Padding=new Padding(4)};panel.Controls.Add(p);panel.Controls.Add(new Label{Text=(i+1).ToString(),Dock=DockStyle.Top,Height=20});return panel;}
    void Slots(){int n=count.SelectedIndex+1;for(int i=0;i<4;i++){front[i].Parent.Visible=i<n;back[i].Parent.Visible=i<n;}}
    async Task DiscoverAsync()
    {
        scanners.Items.Clear();selectedScanner=null;scannerStatus.Text="Searching…";
        var found=await Task.Run(()=>Mdns.FindEsclScanners(TimeSpan.FromSeconds(3)));
        foreach(var s in found)scanners.Items.Add(s.Name+" | "+s.Url);
        if(scanners.Items.Count>0){scanners.SelectedIndex=0;scannerStatus.Text="Scanner available";}else scannerStatus.Text="No compatible eSCL scanner found on this network.";
    }
    int Dpi()=>new[]{150,200,300,600}[Math.Max(0,dpi.SelectedIndex)];
    string Mode()=>new[]{"RGB24","Grayscale8","BlackAndWhite1"}[Math.Max(0,color.SelectedIndex)];
    bool IsDuplex()=>source.SelectedIndex==2;

    async Task ScanAsync(bool isFront)
    {
        if(string.IsNullOrWhiteSpace(selectedScanner)){MessageBox.Show("Select a scanner first.");return;}
        Busy(true,isFront?"Scanning fronts…":"Scanning backs…");
        try
        {
            var bytes=await EscScanner.ScanAsync(selectedScanner,Dpi(),Mode(),IsDuplex(),CancellationToken.None);
            using var ms=new MemoryStream(bytes);using var image=Image.FromStream(ms);using var bmp=new Bitmap(image);
            var cards=await Task.Run(()=>CardDetector.Detect(bmp,count.SelectedIndex+1,SetProgress));
            for(int i=0;i<cards.Count;i++){var f=Save(cards[i],isFront,i);SetFile(isFront,i,f);}
            status.Text=(isFront?"Fronts":"Backs")+" ready — "+cards.Count+" detected.";
        }
        catch(Exception ex){MessageBox.Show(ex.Message,"EasyCopy");}
        finally{Busy(false,"");}
    }

    void Import(bool isFront)
    {
        using var d=new OpenFileDialog{Filter="Images|*.jpg;*.jpeg;*.png;*.bmp|All files|*.*"};
        if(d.ShowDialog()!=DialogResult.OK)return;
        try{using var b=new Bitmap(d.FileName);var card=CardDetector.Import(b);var f=Save(card,isFront,0);SetFile(isFront,0,f);status.Text=(isFront?"Front":"Back")+" imported.";}
        catch(Exception ex){MessageBox.Show(ex.Message,"EasyCopy");}
    }

    string Save(Bitmap b,bool isFront,int i){var f=Path.Combine(Path.GetTempPath(),$"EasyCopy_{(isFront?"front":"back")}_{i+1}_{Guid.NewGuid():N}.jpg");b.Save(f,System.Drawing.Imaging.ImageFormat.Jpeg);b.Dispose();return f;}
    void SetFile(bool isFront,int i,string f){if(isFront){frontFiles[i]=f;front[i].Image?.Dispose();front[i].Image=Image.FromFile(f);}else{backFiles[i]=f;back[i].Image?.Dispose();back[i].Image=Image.FromFile(f);}}
    void Busy(bool busy,string text){scanF.Enabled=scanB.Enabled=!busy;status.Text=text;progress.Value=busy?5:0;}
    void SetProgress(int p,string text){if(IsDisposed)return;BeginInvoke(()=>{progress.Value=Math.Clamp(p,0,100);status.Text=text;});}

    void RunPdf(string action)
    {
        int n=count.SelectedIndex+1;for(int i=0;i<n;i++)if(frontFiles[i]==null||backFiles[i]==null){MessageBox.Show($"Please scan/import both sides for card {i+1}.");return;}
        var c=(int)copies.Value;Busy(true,"Preparing PDF…");
        Task.Run(()=>PdfMaker.Make(frontFiles,backFiles,n,c,SetProgress)).ContinueWith(t=>BeginInvoke(()=>{
            Busy(false,t.IsFaulted?"": "PDF ready.");
            if(t.IsFaulted){MessageBox.Show(t.Exception?.GetBaseException().Message);return;}
            var pdf=t.Result;
            if(action=="save"){using var d=new SaveFileDialog{Filter="PDF|*.pdf",FileName=Path.GetFileName(pdf)};if(d.ShowDialog()==DialogResult.OK)File.Copy(pdf,d.FileName,true);}
            else Process.Start(new System.Diagnostics.ProcessStartInfo(pdf){UseShellExecute=true});
        }));
    }

    void PrintSets()
    {
        int n=count.SelectedIndex+1;for(int i=0;i<n;i++)if(frontFiles[i]==null||backFiles[i]==null){MessageBox.Show($"Please scan/import both sides for card {i+1}.");return;}
        using var dlg=new PrintDialog();using var doc=new PrintDocument();dlg.Document=doc;doc.PrinterSettings.Duplex=Duplex.Vertical;int page=0,total=(int)Math.Ceiling(n*(double)copies.Value/8)*2;
        doc.PrintPage+=(s,e)=>{bool isFront=page%2==0;int logical=page/2;DrawPrintPage(e.Graphics,isFront,logical,n,(int)copies.Value,e.MarginBounds);page++;e.HasMorePages=page<total;};
        if(dlg.ShowDialog()==DialogResult.OK)doc.Print();
    }

    void DrawPrintPage(Graphics g,bool isFront,int page,int n,int reps,Rectangle area)
    {
        g.Clear(Color.White);int total=n*reps;for(int k=0;k<8;k++){int global=page*8+k;if(global>=total)break;int card=global%n;int slot=isFront?k:(k/2)*2+(1-k%2);int col=slot%2,row=slot/2;var r=new Rectangle(area.Left+col*area.Width/2,area.Top+row*area.Height/4,area.Width/2,area.Height/4);using var img=Image.FromFile(isFront?frontFiles[card]:backFiles[card]);float sc=Math.Min((float)(r.Width-12)/img.Width,(float)(r.Height-12)/img.Height);int w=(int)(img.Width*sc),h=(int)(img.Height*sc);g.DrawImage(img,r.Left+(r.Width-w)/2,r.Top+(r.Height-h)/2,w,h);}}
    
    void ImagePrinter()
    {
        using var d=new OpenFileDialog{Filter="Images|*.jpg;*.jpeg;*.png;*.bmp"};if(d.ShowDialog()!=DialogResult.OK)return;
        using var img=new Bitmap(d.FileName);using var pd=new PrintDialog();using var doc=new PrintDocument();pd.Document=doc;
        doc.PrintPage+=(s,e)=>{var r=e.MarginBounds;float sc=Math.Min((float)r.Width/img.Width,(float)r.Height/img.Height);int w=(int)(img.Width*sc),h=(int)(img.Height*sc);e.Graphics.DrawImage(img,r.Left+(r.Width-w)/2,r.Top+(r.Height-h)/2,w,h);};
        if(pd.ShowDialog()==DialogResult.OK)doc.Print();
    }
}
