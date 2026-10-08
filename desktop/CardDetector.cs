using OpenCvSharp;
using OpenCvSharp.Extensions;
using CvPoint = OpenCvSharp.Point;

namespace EasyCopy.Desktop;

static class CardDetector
{
    const double Ratio=85.60/53.98;

    public static List<Bitmap> Detect(Bitmap source,int wanted,Action<int,string> progress)
    {
        using var src=BitmapConverter.ToMat(source);
        using var gray=new Mat();using var blur=new Mat();using var edges=new Mat();using var closed=new Mat();
        Cv2.CvtColor(src,gray,ColorConversionCodes.BGRA2GRAY);
        Cv2.GaussianBlur(gray,blur,new Size(5,5),0);Cv2.Canny(blur,edges,30,110);
        using var k=Cv2.GetStructuringElement(MorphShapes.Rect,new Size(7,7));
        Cv2.MorphologyEx(edges,closed,MorphTypes.Close,k);
        using var d=Cv2.GetStructuringElement(MorphShapes.Rect,new Size(3,3));Cv2.Dilate(closed,closed,d);
        Cv2.FindContours(closed,out CvPoint[][] contours,out _,RetrievalModes.External,ContourApproximationModes.ApproxSimple);
        double total=src.Width*src.Height;
        var candidates=new List<(CvPoint[] q,double score)>();
        for(int i=0;i<contours.Length;i++)
        {
            progress?.Invoke(10+(int)(i*48.0/Math.Max(1,contours.Length)),"Detecting complete card boundaries…");
            double area=Math.Abs(Cv2.ContourArea(contours[i])), af=area/total;if(af<.035||af>.24)continue;
            var rr=Cv2.MinAreaRect(contours[i]);var q=rr.Points();double ratio=SideRatio(q),fill=area/Math.Max(1,rr.Size.Width*rr.Size.Height);
            if(ratio<1.30||ratio>1.90||fill<.60)continue;
            double rs=Math.Max(0,1-Math.Abs(ratio-Ratio)/Ratio), ascore=Math.Max(0,1-Math.Abs(af-.0741)/.065);
            candidates.Add((q,rs*.50+ascore*.30+Math.Min(1,(fill-.60)/.30)*.20));
        }
        candidates=candidates.OrderByDescending(x=>x.score).ToList();
        var result=new List<Bitmap>();
        foreach(var c in candidates)
        {
            if(result.Count>=wanted)break;
            progress?.Invoke(60+result.Count*25/Math.Max(1,wanted),"Straightening and validating card…");
            using var warped=Warp(source,c.q);
            if(!Validate(warped))continue;
            var b=BitmapConverter.ToBitmap(warped);
            result.Add(OrientFourWays(b));
        }
        progress?.Invoke(95,"Finalizing cards…");
        if(result.Count==0)throw new InvalidOperationException("No complete ID card detected.");
        return result;
    }

    public static Bitmap Import(Bitmap source)
    {
        double ar=source.Width/(double)source.Height;
        if(ar>Ratio*.90&&ar<Ratio*1.10&&source.Width>=500)return OrientFourWays(new Bitmap(source));
        return Detect(source,1,(_,__)=>{ }).First();
    }

    static Mat Warp(Bitmap source,CvPoint[] raw)
    {
        var p=OrderStable(raw);
        double a=Dist(p[0],p[1]),b=Dist(p[1],p[2]),c=Dist(p[2],p[3]),d=Dist(p[3],p[0]);
        if((b+d)/2>(a+c)/2)p=new[]{p[1],p[2],p[3],p[0]};
        if(p[1].X-p[0].X<0){(p[0],p[1])=(p[1],p[0]);(p[2],p[3])=(p[3],p[2]);}
        int w=1400,h=(int)Math.Round(w/Ratio);
        using var src=BitmapConverter.ToMat(source);using var dst=new Mat();
        using var from=InputArray.Create(p);using var to=InputArray.Create(new[]{new Point2f(0,0),new Point2f(w-1,0),new Point2f(w-1,h-1),new Point2f(0,h-1)});
        using var M=Cv2.GetPerspectiveTransform(from,to);Cv2.WarpPerspective(src,dst,M,new Size(w,h),InterpolationFlags.Linear,BorderTypes.Replicate);
        return dst.Clone();
    }

    static CvPoint[] OrderStable(CvPoint[] pts)
    {
        double cx=pts.Average(p=>p.X),cy=pts.Average(p=>p.Y);
        var q=pts.OrderBy(p=>Math.Atan2(p.Y-cy,p.X-cx)).ToArray();
        int start=Array.IndexOf(q,q.OrderBy(p=>p.X+p.Y).First());
        return Enumerable.Range(0,4).Select(i=>q[(start+i)%4]).ToArray();
    }

    static double Dist(CvPoint a,CvPoint b)=>Math.Hypot(a.X-b.X,a.Y-b.Y);
    static double SideRatio(CvPoint[] p){double a=Dist(p[0],p[1]),b=Dist(p[1],p[2]),c=Dist(p[2],p[3]),d=Dist(p[3],p[0]);return Math.Max((a+c)/2,(b+d)/2)/Math.Max(1,Math.Min((a+c)/2,(b+d)/2));}

    static bool Validate(Mat m){using var g=new Mat();Cv2.CvtColor(m,g,ColorConversionCodes.BGRA2GRAY);using var e=new Mat();Cv2.Canny(g,e,50,140);return Cv2.CountNonZero(e)>m.Width*m.Height*.02;}

    static Bitmap OrientFourWays(Bitmap card)
    {
        var c=new[]{card,(Bitmap)card.Clone(),(Bitmap)card.Clone(),(Bitmap)card.Clone()};
        c[1].RotateFlip(RotateFlipType.Rotate90FlipNone);c[2].RotateFlip(RotateFlipType.Rotate180FlipNone);c[3].RotateFlip(RotateFlipType.Rotate270FlipNone);
        int best=0,bs=int.MinValue;
        for(int i=0;i<4;i++){int s=TextOrientationScore(c[i]);if(c[i].Width>=c[i].Height)s+=2;if(s>bs){bs=s;best=i;}}
        for(int i=0;i<4;i++)if(i!=best)c[i].Dispose();
        return c[best];
    }

    static int TextOrientationScore(Bitmap b)
    {
        using var m=BitmapConverter.ToMat(b);using var g=new Mat();Cv2.CvtColor(m,g,ColorConversionCodes.BGRA2GRAY);
        using var bw=new Mat();Cv2.Threshold(g,bw,190,255,ThresholdTypes.BinaryInv);
        using var h=new Mat();Cv2.Reduce(bw,h,ReduceDimension.Row,ReduceTypes.Sum,CvType.CV_32S);
        int score=0;
        for(int y=0;y<h.Rows;y++){double v=h.At<int>(y,0);if(v>b.Width*.06)score+=2;}
        return score;
    }
}
