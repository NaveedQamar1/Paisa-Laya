using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.RegularExpressions;

namespace EasyCopy.Desktop;

static class EscScanner
{
    static readonly HttpClientHandler Handler = new() {
        ServerCertificateCustomValidationCallback = HttpClientHandler.DangerousAcceptAnyServerCertificateValidator
    };
    static readonly HttpClient Client = new(Handler) { Timeout = TimeSpan.FromSeconds(35) };

    public static async Task<byte[]> ScanAsync(string baseUrl, int dpi, string color, bool duplex, CancellationToken ct)
    {
        if (!baseUrl.EndsWith("/")) baseUrl += "/";
        try { return await ScanOnce(baseUrl, dpi, color, duplex, ct); }
        catch when (baseUrl.StartsWith("https://", StringComparison.OrdinalIgnoreCase))
        {
            var u = new Uri(baseUrl);
            return await ScanOnce($"http://{u.Host}:80{u.AbsolutePath}", dpi, color, duplex, ct);
        }
    }

    static async Task<byte[]> ScanOnce(string baseUrl, int dpi, string color, bool duplex, CancellationToken ct)
    {
        var caps = await Client.GetStringAsync(baseUrl + "ScannerCapabilities", ct);
        string src = duplex && caps.Contains("Duplex", StringComparison.OrdinalIgnoreCase) ? "Feeder" :
                     caps.Contains("Platen", StringComparison.OrdinalIgnoreCase) ? "Platen" : "Feeder";
        int maxW = IntTag(caps, "MaxWidth", 2550), maxH = IntTag(caps, "MaxHeight", 4200);
        string duplexXml = duplex && src == "Feeder" ? "<scan:Duplex>true</scan:Duplex>" : "";
        string xml = "<?xml version="1.0" encoding="UTF-8"?>" +
            "<scan:ScanSettings xmlns:scan="http://schemas.hp.com/imaging/escl/2011/05/03" xmlns:pwg="http://www.pwg.org/schemas/2010/12/sm" xmlns:escl="http://schemas.hp.com/imaging/escl/2011/05/03">" +
            "<pwg:Version>2.0</pwg:Version><scan:Intent>Document</scan:Intent><pwg:ScanRegions><pwg:ScanRegion>" +
            "<pwg:ContentRegionUnits>escl:ThreeHundredthsOfInches</pwg:ContentRegionUnits><pwg:XOffset>0</pwg:XOffset><pwg:YOffset>0</pwg:YOffset>" +
            $"<pwg:Width>{maxW}</pwg:Width><pwg:Height>{maxH}</pwg:Height></pwg:ScanRegion></pwg:ScanRegions>" +
            $"<pwg:InputSource>{src}</pwg:InputSource><pwg:DocumentFormat>image/jpeg</pwg:DocumentFormat>" +
            $"<scan:XResolution>{dpi}</scan:XResolution><scan:YResolution>{dpi}</scan:YResolution><scan:ColorMode>{color}</scan:ColorMode>{duplexXml}</scan:ScanSettings>";

        using var resp = await Client.PostAsync(baseUrl + "ScanJobs", new StringContent(xml, Encoding.UTF8, "text/xml"), ct);
        if (!resp.IsSuccessStatusCode) throw new Exception($"Scanner rejected scan ({(int)resp.StatusCode}).");
        var loc = resp.Headers.Location?.ToString();
        if (string.IsNullOrWhiteSpace(loc)) throw new Exception("Scanner did not return a scan job.");
        var job = new Uri(new Uri(baseUrl), loc);
        for (int i = 0; i < 90; i++)
        {
            await Task.Delay(500, ct);
            using var r = await Client.GetAsync(new Uri(job, "NextDocument"), ct);
            if (r.StatusCode == HttpStatusCode.NotFound || r.StatusCode == HttpStatusCode.NoContent) continue;
            if (!r.IsSuccessStatusCode) continue;
            var bytes = await r.Content.ReadAsByteArrayAsync(ct);
            if (bytes.Length > 1000) return bytes;
        }
        throw new TimeoutException("Timed out waiting for scanner.");
    }

    static int IntTag(string xml, string tag, int fallback)
    {
        var m = Regex.Match(xml, "<(?:\\w+:)?" + tag + ">\\s*(\\d+)\\s*</(?:\\w+:)?" + tag + ">", RegexOptions.IgnoreCase);
        return m.Success && int.TryParse(m.Groups[1].Value, out var n) ? n : fallback;
    }
}
