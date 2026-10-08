using PdfSharpCore.Drawing;
using PdfSharpCore.Pdf;

namespace EasyCopy.Desktop;

static class PdfMaker
{
    public static string Make(string[] fronts,string[] backs,int n,int copies,Action<int,string> progress)
    {
        var doc=new PdfDocument();int total=n*copies,pages=Math.Max(1,(total+7)/8),done=0,work=Math.Max(1,total*2);
        for(int page=0;page<pages;page++)
        {
            var fp=doc.AddPage();fp.Size=PageSize.A4;fp.Orientation=PageOrientation.Portrait;Draw(fp,fronts,n,copies,page*8,true,ref done,work,progress);
            var bp=doc.AddPage();bp.Size=PageSize.A4;bp.Orientation=PageOrientation.Portrait;Draw(bp,backs,n,copies,page*8,false,ref done,work,progress);
        }
        var file=Path.Combine(Path.GetTempPath(),$"EasyCopy_{DateTime.Now:yyyyMMdd_HHmmss}.pdf");doc.Save(file);progress(100,"PDF ready.");return file;
    }

    static void Draw(PdfPage page,string[] files,int n,int copies,int start,bool front,ref int done,int work,Action<int,string> progress)
    {
        using var g=XGraphics.FromPdfPage(page);double pw=page.Width.Point,ph=page.Height.Point,cw=pw/2-22,ch=ph/4-22;
        for(int k=0;k<8;k++)
        {
            int global=start+k;if(global>=n*copies)break;int card=global%n;int slot=front?k:(k/2)*2+(1-k%2);int col=slot%2,row=slot/2;
            double x=col*(pw/2)+11,y=row*(ph/4)+11;using var img=XImage.FromFile(files[card]);double sc=Math.Min(cw/img.PixelWidth,ch/img.PixelHeight),w=img.PixelWidth*sc,h=img.PixelHeight*sc;
            g.DrawImage(img,x+(pw/2-w)/2,y+(ph/4-h)/2,w,h);done++;progress(Math.Min(95,done*95/Math.Max(1,work)),(front?"Front":"Back")+" cards: "+done+"/"+work);
        }
    }
}
