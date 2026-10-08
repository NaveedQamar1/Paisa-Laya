using OpenCvSharp;
using OpenCvSharp.Extensions;
using CvPoint = OpenCvSharp.Point;
using CvSize = OpenCvSharp.Size;

namespace EasyCopy.Desktop;

static class CardDetector
{
    const double Ratio=85.60/53.98;

    public static List<Bitmap> Detect(Bitmap source,int wanted,Action<int,string> progress)
    {
        using var src=BitmapConverter.ToMat(source);
        using var gray=new Mat();using var blur=new Mat();using var edges=new Mat();using var closed=new Mat();
        Cv2.CvtColor(src,gray,ColorConversionCodes.BGRA2GRAY);
        Cv2.GaussianBlur(gray,blur,new CvSize(5,5),0);Cv2.Canny(blur,edges,30,110);
        using var k=Cv2.GetStructuringElement(MorphShapes.Rect,new CvSize(7,7));
        Cv2.MorphologyEx(edges,closed,MorphTypes.Close,k);
        using var d=Cv2.GetStructuringElement(MorphShapes.Rect,new CvSize(3,3));Cv2.Dilate(closed,closed,d);
        Cv2.FindContours(closed,out CvPoint[][] contours,out _,RetrievalModes.External,ContourApproximationModes.ApproxSimple);
        double total=src.Width*src.Height;
        var candidates=new List<(CvPoint[] q,double score)>();
        for(int i=0;i<contours.Length;i++)
        {
            progress?.Invoke(10+(int)(i*48.0/Math.Max(1,contours.Length)),"Detecting complete card boundaries…");
            double area=Math.Abs(Cv2.ContourArea(contours[i])), af=area/total;
            if(af<.035||af>.20)continue;

            var bb=Cv2.BoundingRect(contours[i]);
            if(bb.Width<source.Width*.12||bb.Height<source.Height*.055)continue;

            double peri=Cv2.ArcLength(contours[i],true);
            var approx=Cv2.ApproxPolyDP(contours[i],Math.Max(2.0,.018*peri),true);
            // Do not replace a non-quadrilateral contour with MinAreaRect:
            // a line or small fragment can otherwise become a convincing fake card.
            if(approx.Length!=4||!Cv2.IsContourConvex(approx))continue;

            double fill=area/Math.Max(1,bb.Width*bb.Height),ratio=SideRatio(approx);
            double angle=AngleScore(approx);
            if(ratio<1.30||ratio>1.90||fill<.62||angle<.72)continue;

            double rs=Math.Max(0,1-Math.Abs(ratio-Ratio)/Ratio);
            double ascore=Math.Max(0,1-Math.Abs(af-.0741)/.065);
            double size=Math.Min(1,Math.Max(0,(af-.035)/.045));
            double fillScore=Math.Min(1,Math.Max(0,(fill-.62)/.30));
            candidates.Add((approx,rs*.40+ascore*.28+fillScore*.17+size*.08+angle*.07));
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
        var fp=p.Select(x=>new Point2f(x.X,x.Y)).ToArray();var tp=new[]{new Point2f(0,0),new Point2f(w-1,0),new Point2f(w-1,h-1),new Point2f(0,h-1)};using var from=InputArray.Create(fp);using var to=InputArray.Create(tp);
        using var M=Cv2.GetPerspectiveTransform(from,to);Cv2.WarpPerspective(src,dst,M,new CvSize(w,h),InterpolationFlags.Linear,BorderTypes.Replicate);
        return dst.Clone();
    }

    static CvPoint[] OrderStable(CvPoint[] pts)
    {
        double cx=pts.Average(p=>p.X),cy=pts.Average(p=>p.Y);
        var q=pts.OrderBy(p=>Math.Atan2(p.Y-cy,p.X-cx)).ToArray();
        int start=Array.IndexOf(q,q.OrderBy(p=>p.X+p.Y).First());
        return Enumerable.Range(0,4).Select(i=>q[(start+i)%4]).ToArray();
    }

    static double AngleScore(CvPoint[] p)
    {
        double score=1;
        for(int i=0;i<4;i++)
        {
            var a=p[(i+3)%4];var c=p[i];var b=p[(i+1)%4];
            double ax=a.X-c.X,ay=a.Y-c.Y,bx=b.X-c.X,by=b.Y-c.Y;
            double den=Math.Sqrt((ax*ax+ay*ay)*(bx*bx+by*by));if(den<1)return 0;
            double cos=Math.Abs((ax*bx+ay*by)/den);
            score*=Math.Max(0,1-cos/.72);
        }
        return Math.Pow(score,.25);
    }

    static double Dist(CvPoint a,CvPoint b)=>Math.Sqrt((a.X-b.X)*(a.X-b.X)+(a.Y-b.Y)*(a.Y-b.Y));
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
        using var h=new Mat();Cv2.Reduce(bw,h,ReduceDimension.Row,ReduceTypes.Sum,MatType.CV_32S);
        int score=0;
        for(int y=0;y<h.Rows;y++){double v=h.At<int>(y,0);if(v>b.Width*.06)score+=2;}
        return score;
    }
}
