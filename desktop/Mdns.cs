using System.Net;
using System.Net.Sockets;
using System.Text;

namespace EasyCopy.Desktop;

static class Mdns
{
    public sealed record Scanner(string Name, string Url);

    public static List<Scanner> FindEsclScanners(TimeSpan timeout)
    {
        var all = new Dictionary<string, Scanner>(StringComparer.OrdinalIgnoreCase);
        Discover("_uscan._tcp.local", "http", all, timeout);
        Discover("_uscans._tcp.local", "https", all, timeout);
        return all.Values.ToList();
    }

    static void Discover(string service, string scheme, Dictionary<string, Scanner> all, TimeSpan timeout)
    {
        using var u = new UdpClient(AddressFamily.InterNetwork);
        u.Client.SetSocketOption(SocketOptionLevel.Socket, SocketOptionName.ReuseAddress, true);
        u.Client.Bind(new IPEndPoint(IPAddress.Any, 0));
        u.JoinMulticastGroup(IPAddress.Parse("224.0.0.251"));
        var q = Query(service);
        u.Send(q, q.Length, new IPEndPoint(IPAddress.Parse("224.0.0.251"), 5353));
        var end = DateTime.UtcNow + timeout;
        while (DateTime.UtcNow < end)
        {
            if (!u.Client.Poll(100000, SelectMode.SelectRead)) continue;
            try
            {
                var ep = new IPEndPoint(IPAddress.Any, 0);
                var b = u.Receive(ref ep);
                ParseResponse(b, service, scheme, all);
            }
            catch { }
        }
    }

    static byte[] Query(string name)
    {
        using var ms = new MemoryStream();
        using var w = new BinaryWriter(ms);
        w.Write((byte)0); w.Write((byte)0); w.Write((byte)0); w.Write((byte)0);
        w.Write((byte)0); w.Write((byte)1); w.Write((byte)0); w.Write((byte)0); w.Write((byte)0); w.Write((byte)0); w.Write((byte)0); w.Write((byte)0);
        foreach (var part in name.Split('.')) { w.Write((byte)part.Length); w.Write(Encoding.ASCII.GetBytes(part)); }
        w.Write((byte)0); w.Write((byte)0); w.Write((byte)12); w.Write((byte)0); w.Write((byte)1);
        return ms.ToArray();
    }

    static void ParseResponse(byte[] b, string service, string scheme, Dictionary<string, Scanner> all)
    {
        if (b.Length < 12) return;
        int an=(b[6]<<8)|b[7], ns=(b[8]<<8)|b[9], ar=(b[10]<<8)|b[11], p=12;
        if (!ReadName(b, ref p, out _)) return; p += 4;
        var rec = new List<(string name,int type,byte[] data)>();
        for (int i=0;i<an+ns+ar;i++)
        {
            if (!ReadName(b, ref p, out var name) || p+10>b.Length) return;
            int type=(b[p]<<8)|b[p+1], len=(b[p+8]<<8)|b[p+9]; p+=10;
            if(p+len>b.Length)return;
            rec.Add((name,type,b[p..(p+len)]));p+=len;
        }
        foreach(var ptr in rec.Where(x=>x.type==12 && x.name.Equals(service,StringComparison.OrdinalIgnoreCase)))
        {
            int po=0;if(!ReadName(ptr.data,ref po,out var instance))continue;
            var srv=rec.FirstOrDefault(x=>x.type==33 && x.name.Equals(instance,StringComparison.OrdinalIgnoreCase));
            if(srv.data==null)continue;
            int port=(srv.data[4]<<8)|srv.data[5],so=6;if(!ReadName(srv.data,ref so,out var host))continue;
            var a=rec.FirstOrDefault(x=>x.type==1 && x.name.Equals(host,StringComparison.OrdinalIgnoreCase));
            if(a.data==null || a.data.Length!=4)continue;
            var ip=new IPAddress(a.data).ToString();
            all[instance]=new Scanner(instance,$"{scheme}://{ip}:{port}/eSCL/");
        }
    }

    static bool ReadName(byte[] b, ref int p, out string name)
    {
        name=""; var parts=new List<string>(); int jumps=0;
        while(p<b.Length && jumps++<40)
        {
            int len=b[p++];
            if(len==0){name=string.Join(".",parts);return true;}
            if((len&0xC0)==0xC0)
            {
                if(p>=b.Length)return false;int off=((len&0x3F)<<8)|b[p++],save=p;p=off;
                if(!ReadName(b,ref p,out var tail))return false;p=save;if(tail.Length>0)parts.Add(tail);name=string.Join(".",parts);return true;
            }
            if(p+len>b.Length)return false;parts.Add(Encoding.UTF8.GetString(b,p,len));p+=len;
        }
        return false;
    }
}
