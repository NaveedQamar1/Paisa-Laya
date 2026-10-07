package com.easycopy.app;

import android.content.Context;
import android.net.nsd.*;
import java.io.*;
import java.net.*;
import java.util.*;

public class NetworkScanner {
    public interface Listener { void onDevice(String name,String url); void onDone(); void onError(String msg); }
    private final Context ctx; private NsdManager nsd; private final Set<String> seen=new HashSet<>();
    NetworkScanner(Context c){ctx=c;nsd=(NsdManager)c.getSystemService(Context.NSD_SERVICE);}
    public void discover(Listener l){
        seen.clear();
        discoverType("_uscan._tcp.",l);
        discoverType("_uscans._tcp.",l);
    }
    private void discoverType(String type,Listener l){
        try{nsd.discoverServices(type,NsdManager.PROTOCOL_DNS_SD,new NsdManager.DiscoveryListener(){
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
                        try{if(x.getAttributes()!=null&&x.getAttributes().get("rs")!=null){rs=new String(x.getAttributes().get("rs"));if(!rs.startsWith("/"))rs="/"+rs;if(!rs.endsWith("/"))rs+="/";}}catch(Exception ignored){}
                        String url=scheme+"://"+host+":"+x.getPort()+rs;
                        if(seen.add(url))l.onDevice(x.getServiceName(),url);
                    }
                });
            }
        });}catch(Exception e){l.onError(e.getMessage()==null?"Discovery unavailable":e.getMessage());}
    }
    public void close(){}

    public static byte[] scan(String baseUrl, int dpi, String color, boolean duplex) throws Exception {
        if(!baseUrl.endsWith("/"))baseUrl+="/";
        String caps=get(baseUrl+"ScannerCapabilities");
        String source=duplex?"ADFDuplex":"Platen";
        if(!caps.contains(source)) source=caps.contains("Feeder")?"Feeder":"Platen";
        String xml="<?xml version=\"1.0\" encoding=\"UTF-8\"?><scan:ScanSettings xmlns:scan=\"http://schemas.hp.com/imaging/escl/2011/05/03\"><scan:Intent>Document</scan:Intent><scan:InputSource>"+source+"</scan:InputSource><scan:DocumentFormat>image/jpeg</scan:DocumentFormat><scan:XResolution>"+dpi+"</scan:XResolution><scan:YResolution>"+dpi+"</scan:YResolution><scan:ColorMode>"+color+"</scan:ColorMode><scan:Width>2480</scan:Width><scan:Height>3508</scan:Height></scan:ScanSettings>";
        URL u=new URL(baseUrl+"ScanJobs"); HttpURLConnection c=(HttpURLConnection)u.openConnection(); c.setConnectTimeout(10000);c.setReadTimeout(30000);c.setRequestMethod("POST");c.setDoOutput(true);c.setRequestProperty("Content-Type","text/xml");c.getOutputStream().write(xml.getBytes("UTF-8"));
        int code=c.getResponseCode(); String loc=c.getHeaderField("Location"); if(code<200||code>=300)throw new IOException("Scanner rejected scan ("+code+")");
        if(loc==null)throw new IOException("Scanner did not return a scan job.");
        if(loc.startsWith("/")){URL root=new URL(baseUrl);loc=root.getProtocol()+"://"+root.getAuthority()+loc;}
        for(int i=0;i<60;i++){try{Thread.sleep(700);}catch(InterruptedException ignored){} byte[] b=getBytes(loc.endsWith("/")?loc+"NextDocument":loc+"/NextDocument");if(b!=null&&b.length>1000)return b;}
        throw new IOException("Timed out waiting for scanner.");
    }
    private static String get(String u)throws Exception{return new String(getBytes(u),"UTF-8");}
    private static byte[] getBytes(String s)throws Exception{HttpURLConnection c=(HttpURLConnection)new URL(s).openConnection();c.setConnectTimeout(8000);c.setReadTimeout(15000);c.setRequestMethod("GET");int code=c.getResponseCode();if(code==404||code==204)return null;if(code<200||code>=300)throw new IOException("Scanner returned HTTP "+code);InputStream in=c.getInputStream();ByteArrayOutputStream o=new ByteArrayOutputStream();byte[] b=new byte[8192];int n;while((n=in.read(b))>0)o.write(b,0,n);in.close();return o.toByteArray();}
}