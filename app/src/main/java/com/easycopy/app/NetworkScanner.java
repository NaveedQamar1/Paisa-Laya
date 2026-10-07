package com.easycopy.app;

import android.content.Context;
import android.net.nsd.*;
import javax.net.ssl.*;
import java.io.*;
import java.net.*;
import java.security.SecureRandom;
import java.security.cert.X509Certificate;
import java.util.*;

public class NetworkScanner {
    public interface Listener { void onDevice(String name,String url); void onDone(); void onError(String msg); }
    private final Context ctx;
    private final NsdManager nsd;
    private final Set<String> seen=new HashSet<>();

    NetworkScanner(Context c){ctx=c;nsd=(NsdManager)c.getSystemService(Context.NSD_SERVICE);}

    public void discover(Listener l){
        seen.clear();
        discoverType("_uscan._tcp.",l);
        discoverType("_uscans._tcp.",l);
    }

    private void discoverType(String type,Listener l){
        try{
            nsd.discoverServices(type,NsdManager.PROTOCOL_DNS_SD,new NsdManager.DiscoveryListener(){
                public void onStartDiscoveryFailed(String s,int e){l.onError("Network discovery failed: "+s);}
                public void onStopDiscoveryFailed(String s,int e){}
                public void onDiscoveryStarted(String s){}
                public void onDiscoveryStopped(String s){l.onDone();}
                public void onServiceLost(NsdServiceInfo s){}
                public void onServiceFound(NsdServiceInfo s){
                    nsd.resolveService(s,new NsdManager.ResolveListener(){
                        public void onResolveFailed(NsdServiceInfo s,int e){}
                        public void onServiceResolved(NsdServiceInfo x){
                            String host=x.getHost()==null?null:x.getHost().getHostAddress();
                            if(host==null)return;
                            String scheme="_uscans._tcp.".equals(type)?"https":"http";
                            String rs="/eSCL/";
                            try{
                                if(x.getAttributes()!=null&&x.getAttributes().get("rs")!=null){
                                    rs=new String(x.getAttributes().get("rs"));
                                    if(!rs.startsWith("/"))rs="/"+rs;
                                    if(!rs.endsWith("/"))rs+="/";
                                }
                            }catch(Exception ignored){}
                            String url=scheme+"://"+host+":"+x.getPort()+rs;
                            if(seen.add(url))l.onDevice(x.getServiceName(),url);
                        }
                    });
                }
            });
        }catch(Exception e){l.onError(e.getMessage()==null?"Discovery unavailable":e.getMessage());}
    }

    public void close(){}

    /*
     * Network MFPs frequently expose eSCL over HTTPS with a device-generated
     * certificate. Android quite correctly rejects that certificate, but this
     * connection is only to the scanner on the user's local network. We use a
     * scanner-only TLS connection that accepts the device certificate and do
     * not change the app-wide Android trust store.
     */
    private static HttpsURLConnection openHttps(URL u) throws Exception {
        HttpsURLConnection c=(HttpsURLConnection)u.openConnection();
        TrustManager[] trustAll=new TrustManager[]{new X509TrustManager(){
            public void checkClientTrusted(X509Certificate[] chain,String authType){}
            public void checkServerTrusted(X509Certificate[] chain,String authType){}
            public X509Certificate[] getAcceptedIssuers(){return new X509Certificate[0];}
        }};
        SSLContext ssl=SSLContext.getInstance("TLS");
        ssl.init(null,trustAll,new SecureRandom());
        c.setSSLSocketFactory(ssl.getSocketFactory());
        c.setHostnameVerifier((hostname,session)->true);
        return c;
    }

    private static HttpURLConnection open(String address) throws Exception {
        URL u=new URL(address);
        if(u.getProtocol().equalsIgnoreCase("https")) return openHttps(u);
        return (HttpURLConnection)u.openConnection();
    }

    private static void configure(HttpURLConnection c,String method) throws Exception {
        c.setConnectTimeout(10000);
        c.setReadTimeout(30000);
        c.setUseCaches(false);
        c.setRequestMethod(method);
        c.setRequestProperty("Accept","*/*");
        c.setRequestProperty("User-Agent","EasyCopy/2.1 Android");
    }

    public static byte[] scan(String baseUrl,int dpi,String color,boolean duplex) throws Exception {
        if(!baseUrl.endsWith("/"))baseUrl+="/";
        Exception first=null;
        try{
            return scanOnce(baseUrl,dpi,color,duplex);
        }catch(Exception e){
            first=e;
        }

        // Some printers advertise the secure service but actually expose the
        // usable eSCL endpoint on plain HTTP as well. Try the conventional
        // HTTP eSCL endpoint before giving up.
        if(baseUrl.toLowerCase(Locale.US).startsWith("https://")){
            try{
                URL u=new URL(baseUrl);
                String fallback="http://"+u.getHost()+":80"+(u.getPath().isEmpty()?"/eSCL/":u.getPath());
                return scanOnce(fallback,dpi,color,duplex);
            }catch(Exception ignored){}
        }
        throw first;
    }

    private static byte[] scanOnce(String baseUrl,int dpi,String color,boolean duplex) throws Exception {
        if(!baseUrl.endsWith("/"))baseUrl+="/";

        String caps=get(baseUrl+"ScannerCapabilities");
        if(caps==null||caps.length()<20)throw new IOException("Scanner capabilities are unavailable.");

        String source=duplex?"Feeder":"Platen";
        if(duplex && !containsIgnoreCase(caps,"Duplex")) source="Feeder";
        if(!containsIgnoreCase(caps,source)){
            if(containsIgnoreCase(caps,"Platen"))source="Platen";
            else if(containsIgnoreCase(caps,"Feeder"))source="Feeder";
        }

        // eSCL ScanRegions use ThreeHundredthsOfInches, not raw pixels.
        // A4 is 8.27 x 11.69 inches = 827 x 1169 hundredths.
        String xml="<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
                +"<scan:ScanSettings xmlns:scan=\"http://schemas.hp.com/imaging/escl/2011/05/03\" xmlns:pwg=\"http://www.pwg.org/schemas/2010/12/sm\" xmlns:escl=\"http://schemas.hp.com/imaging/escl/2011/05/03\" "
                +"xmlns:pwg=\"http://www.pwg.org/schemas/2010/12/sm\">"
                +"<pwg:Version>2.0</pwg:Version>"
                +"<scan:Intent>Document</scan:Intent>"
                +"<pwg:ScanRegions><pwg:ScanRegion>"
                +"<pwg:ContentRegionUnits>escl:ThreeHundredthsOfInches</pwg:ContentRegionUnits>"
                +"<pwg:XOffset>0</pwg:XOffset><pwg:YOffset>0</pwg:YOffset>"
                +"<pwg:Width>827</pwg:Width><pwg:Height>1169</pwg:Height>"
                +"</pwg:ScanRegion></pwg:ScanRegions>"
                +"<pwg:InputSource>"+source+"</pwg:InputSource>"
                +"<pwg:DocumentFormat>image/jpeg</pwg:DocumentFormat>"
                +"<scan:XResolution>"+dpi+"</scan:XResolution>"
                +"<scan:YResolution>"+dpi+"</scan:YResolution>"
                +"<scan:ColorMode>"+color+"</scan:ColorMode>"
                +(duplex&&"Feeder".equals(source)?"<scan:Duplex>true</scan:Duplex>":"")
                +"</scan:ScanSettings>";

        HttpURLConnection c=open(baseUrl+"ScanJobs");
        configure(c,"POST");
        c.setDoOutput(true);
        c.setRequestProperty("Content-Type","text/xml; charset=UTF-8");
        byte[] body=xml.getBytes("UTF-8");
        c.setFixedLengthStreamingMode(body.length);
        try(OutputStream out=c.getOutputStream()){out.write(body);out.flush();}
        int code=c.getResponseCode();
        String loc=c.getHeaderField("Location");
        if(code<200||code>=300){
            String detail=readError(c);
            throw new IOException("Scanner rejected scan ("+code+")"+(detail.isEmpty()?"":": "+detail));
        }
        if(loc==null||loc.trim().isEmpty())throw new IOException("Scanner did not return a scan job.");
        loc=resolve(baseUrl,loc);

        for(int i=0;i<90;i++){
            Thread.sleep(500);
            byte[] b=getBytes(loc.endsWith("/")?loc+"NextDocument":loc+"/NextDocument");
            if(b!=null&&b.length>1000)return b;
        }
        throw new IOException("Timed out waiting for scanner.");
    }

    private static String resolve(String base,String location)throws Exception{
        return new URL(new URL(base),location).toString();
    }

    private static boolean containsIgnoreCase(String s,String needle){
        return s!=null&&needle!=null&&s.toLowerCase(Locale.US).contains(needle.toLowerCase(Locale.US));
    }

    private static String get(String u)throws Exception{return new String(getBytes(u),"UTF-8");}

    private static byte[] getBytes(String address)throws Exception{
        HttpURLConnection c=open(address);
        configure(c,"GET");
        int code=c.getResponseCode();
        if(code==404||code==204)return null;
        if(code<200||code>=300){
            String detail=readError(c);
            throw new IOException("Scanner returned HTTP "+code+(detail.isEmpty()?"":": "+detail));
        }
        try(InputStream in=c.getInputStream()){
            ByteArrayOutputStream o=new ByteArrayOutputStream();
            byte[] b=new byte[8192];int n;
            while((n=in.read(b))>0)o.write(b,0,n);
            return o.toByteArray();
        }finally{c.disconnect();}
    }

    private static String readError(HttpURLConnection c){
        try{
            InputStream in=c.getErrorStream();
            if(in==null)return "";
            try(InputStream x=in){
                ByteArrayOutputStream o=new ByteArrayOutputStream();
                byte[] b=new byte[2048];int n;
                while((n=x.read(b))>0&&o.size()<8192)o.write(b,0,n);
                return new String(o.toByteArray(),"UTF-8").replaceAll("\\s+"," ").trim();
            }
        }catch(Exception ignored){return "";}
    }
}
