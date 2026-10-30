import csv, sqlite3, threading
from datetime import datetime, date, timedelta
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

BASE = Path.home() / "K50AttendanceManager"
BASE.mkdir(exist_ok=True)
DB = BASE / "attendance.db"
BG = "#f3f6fb"
NAVY = "#172554"
BLUE = "#2563eb"
TEAL = "#0f766e"
MUTED = "#64748b"

def init_db():
    with sqlite3.connect(DB) as c:
        c.execute("""CREATE TABLE IF NOT EXISTS punches (
            user_id TEXT NOT NULL, punch_time TEXT NOT NULL, status TEXT DEFAULT '',
            UNIQUE(user_id,punch_time,status))""")

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("K50 Attendance Manager")
        self.geometry("1180x780")
        self.minsize(960, 650)
        self.configure(bg=BG)
        init_db()
        self.ip=tk.StringVar(value="192.168.1.201")
        self.port=tk.StringVar(value="4370")
        self.key=tk.StringVar(value="0")
        self.status=tk.StringVar(value="Ready")
        self.start_date=tk.StringVar(value=date.today().replace(day=1).isoformat())
        self.end_date=tk.StringVar(value=date.today().isoformat())
        self.report_user=tk.StringVar(value="All staff")
        self._style()
        self._ui()
        self.refresh()

    def _style(self):
        s=ttk.Style(self)
        try: s.theme_use("clam")
        except Exception: pass
        s.configure("TFrame", background=BG)
        s.configure("TLabel", background=BG, foreground=NAVY, font=("Segoe UI",10))
        s.configure("Title.TLabel", font=("Segoe UI",22,"bold"), foreground=NAVY)
        s.configure("Sub.TLabel", font=("Segoe UI",10), foreground=MUTED)
        s.configure("Card.TFrame", background="white", relief="flat")
        s.configure("CardTitle.TLabel", background="white", foreground=MUTED, font=("Segoe UI",10))
        s.configure("CardValue.TLabel", background="white", foreground=NAVY, font=("Segoe UI",22,"bold"))
        s.configure("Accent.TButton", font=("Segoe UI",10,"bold"), padding=(12,8), background=BLUE, foreground="white")
        s.map("Accent.TButton", background=[("active","#1d4ed8")])
        s.configure("Treeview", rowheight=28, font=("Segoe UI",9), background="white", fieldbackground="white")
        s.configure("Treeview.Heading", font=("Segoe UI",9,"bold"), background="#e8eef8", foreground=NAVY)
        s.configure("TNotebook", background=BG, borderwidth=0)
        s.configure("TNotebook.Tab", padding=(18,9), font=("Segoe UI",10,"bold"))

    def _ui(self):
        header=tk.Frame(self,bg=NAVY,height=94); header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header,text="▦  K50 ATTENDANCE MANAGER",bg=NAVY,fg="white",font=("Segoe UI",21,"bold")).pack(anchor="w",padx=24,pady=(15,2))
        tk.Label(header,text="Device sync  •  Attendance dashboard  •  PDF reporting",bg=NAVY,fg="#cbd5e1",font=("Segoe UI",10)).pack(anchor="w",padx=26)
        conn=ttk.Frame(self,padding=(18,14,18,10)); conn.pack(fill="x")
        ttk.Label(conn,text="DEVICE CONNECTION",font=("Segoe UI",9,"bold")).grid(row=0,column=0,columnspan=8,sticky="w",pady=(0,6))
        for col,label,var,width in [(0,"Device IP",self.ip,17),(2,"Port",self.port,7),(4,"Comm key",self.key,7)]:
            ttk.Label(conn,text=label).grid(row=1,column=col,sticky="w",padx=(0,5))
            ttk.Entry(conn,textvariable=var,width=width).grid(row=1,column=col+1,sticky="w",padx=(0,16))
        ttk.Button(conn,text="⟳  Fetch from K50",style="Accent.TButton",command=self.fetch).grid(row=1,column=6,padx=(0,8))
        ttk.Button(conn,text="＋  Import CSV",command=self.import_csv).grid(row=1,column=7)
        filters=ttk.Frame(self,padding=(18,0,18,10)); filters.pack(fill="x")
        ttk.Label(filters,text="From").pack(side="left")
        ttk.Entry(filters,textvariable=self.start_date,width=12).pack(side="left",padx=(6,14))
        ttk.Label(filters,text="To").pack(side="left")
        ttk.Entry(filters,textvariable=self.end_date,width=12).pack(side="left",padx=(6,14))
        ttk.Button(filters,text="Apply dates",command=self.refresh).pack(side="left")
        ttk.Label(filters,text="PDF scope").pack(side="left",padx=(22,6))
        self.user_combo=ttk.Combobox(filters,textvariable=self.report_user,width=18,state="readonly",values=["All staff"])
        self.user_combo.pack(side="left")
        ttk.Button(filters,text="Export PDF report",style="Accent.TButton",command=self.export_pdf).pack(side="right")
        ttk.Button(filters,text="Export CSV",command=self.export_csv).pack(side="right",padx=8)
        self.tabs=ttk.Notebook(self); self.tabs.pack(fill="both",expand=True,padx=18,pady=(0,8))
        self.dashboard=ttk.Frame(self.tabs,padding=12); self.records=ttk.Frame(self.tabs,padding=12)
        self.tabs.add(self.dashboard,text="  ◈ Dashboard  "); self.tabs.add(self.records,text="  ☷ Punch records  ")
        self._dashboard_ui(); self._records_ui()
        footer=tk.Frame(self,bg="#e8eef8",height=30); footer.pack(fill="x",side="bottom")
        tk.Label(footer,textvariable=self.status,bg="#e8eef8",fg=MUTED,font=("Segoe UI",9),anchor="w").pack(fill="x",padx=18,pady=6)

    def _dashboard_ui(self):
        self.cards=ttk.Frame(self.dashboard); self.cards.pack(fill="x",pady=(0,12))
        self.card_values=[]
        for i,(title,icon) in enumerate([("TOTAL PUNCHES","↗"),("UNIQUE STAFF","♙"),("ACTIVE DAYS","▦"),("AVG. PUNCHES / DAY","◷")]):
            card=ttk.Frame(self.cards,style="Card.TFrame",padding=14); card.grid(row=0,column=i,sticky="nsew",padx=5)
            self.cards.columnconfigure(i,weight=1)
            ttk.Label(card,text=icon+"  "+title,style="CardTitle.TLabel").pack(anchor="w")
            val=ttk.Label(card,text="0",style="CardValue.TLabel"); val.pack(anchor="w",pady=(8,0))
            self.card_values.append(val)
        chartrow=ttk.Frame(self.dashboard); chartrow.pack(fill="both",expand=True)
        self.daily_box=ttk.Frame(chartrow,style="Card.TFrame",padding=12); self.daily_box.pack(side="left",fill="both",expand=True,padx=5)
        self.staff_box=ttk.Frame(chartrow,style="Card.TFrame",padding=12); self.staff_box.pack(side="left",fill="both",expand=True,padx=5)
        ttk.Label(self.daily_box,text="PUNCH ACTIVITY BY DAY",font=("Segoe UI",11,"bold"),background="white").pack(anchor="w")
        ttk.Label(self.staff_box,text="PUNCHES BY STAFF ID",font=("Segoe UI",11,"bold"),background="white").pack(anchor="w")
        self.daily_canvas=tk.Canvas(self.daily_box,bg="white",highlightthickness=0,height=310); self.daily_canvas.pack(fill="both",expand=True,pady=(8,0))
        self.staff_canvas=tk.Canvas(self.staff_box,bg="white",highlightthickness=0,height=310); self.staff_canvas.pack(fill="both",expand=True,pady=(8,0))
        ttk.Label(self.dashboard,text="Charts and statistics reflect imported/fetched punch records in the selected date range. Staff are identified by device ID.",style="Sub.TLabel").pack(anchor="w",pady=(10,0))

    def _records_ui(self):
        cols=("uid","time","status")
        self.tree=ttk.Treeview(self.records,columns=cols,show="headings")
        for col,title,width in [("uid","Device User ID",180),("time","Attendance date & time",280),("status","Punch status",180)]:
            self.tree.heading(col,text=title); self.tree.column(col,width=width,anchor="w")
        self.tree.pack(fill="both",expand=True)
        self.tree.tag_configure("odd",background="#f8fafc")

    def _date_filter(self):
        try:
            start=datetime.strptime(self.start_date.get().strip(),"%Y-%m-%d").date()
            end=datetime.strptime(self.end_date.get().strip(),"%Y-%m-%d").date()
            if end < start: raise ValueError("End date must not be before start date.")
            return start.isoformat()+" 00:00:00",end.isoformat()+" 23:59:59"
        except ValueError as e:
            messagebox.showerror("Check date range",str(e) or "Use YYYY-MM-DD date format.")
            return None

    def _rows(self, filtered=True):
        with sqlite3.connect(DB) as c:
            if filtered:
                bounds=self._date_filter()
                if not bounds: return []
                return c.execute("SELECT user_id,punch_time,status FROM punches WHERE punch_time BETWEEN ? AND ? ORDER BY punch_time",(bounds[0],bounds[1])).fetchall()
            return c.execute("SELECT user_id,punch_time,status FROM punches ORDER BY punch_time").fetchall()

    def refresh(self):
        rows=self._rows()
        if rows is None: return
        for i in self.tree.get_children(): self.tree.delete(i)
        for idx,row in enumerate(reversed(rows[-5000:])):
            self.tree.insert("","end",values=row,tags=("odd",) if idx%2 else ())
        users=sorted(set(str(r[0]) for r in rows),key=lambda x:(not x.isdigit(),int(x) if x.isdigit() else x.lower()))
        choices=["All staff"]+users
        self.user_combo["values"]=choices
        if self.report_user.get() not in choices: self.report_user.set("All staff")
        days=len(set(r[1][:10] for r in rows))
        staff=len(users)
        avg=(len(rows)/days) if days else 0
        for label,value in zip(self.card_values,[f"{len(rows):,}",f"{staff:,}",f"{days:,}",f"{avg:.1f}"]): label.configure(text=value)
        self._draw_charts(rows)
        self.status.set(f"{len(rows):,} punches • {staff} staff IDs • {self.start_date.get()} to {self.end_date.get()}")

    def _draw_charts(self,rows):
        daily={}
        staff={}
        for uid,stamp,state in rows:
            daily[stamp[:10]]=daily.get(stamp[:10],0)+1
            staff[str(uid)]=staff.get(str(uid),0)+1
        self._bar_chart(self.daily_canvas,sorted(daily.items())[-14:], "#2563eb", date_labels=True)
        self._bar_chart(self.staff_canvas,sorted(staff.items(),key=lambda x:x[1],reverse=True)[:10], "#0f766e", date_labels=False)

    def _bar_chart(self,canvas,items,color,date_labels=False):
        canvas.delete("all")
        w=max(canvas.winfo_width(),360); h=max(canvas.winfo_height(),260)
        if not items:
            canvas.create_text(w/2,h/2,text="No records in this date range",fill=MUTED,font=("Segoe UI",11))
            return
        left,right,top,bottom=42,16,18,48
        cw=w-left-right; ch=h-top-bottom
        maxv=max(v for _,v in items) or 1
        for n in range(4):
            y=top+ch-(ch*n/3)
            canvas.create_line(left,y,w-right,y,fill="#e2e8f0")
            canvas.create_text(left-8,y,text=str(round(maxv*n/3)),anchor="e",fill=MUTED,font=("Segoe UI",8))
        gap=cw/len(items); bw=max(8,gap*.58)
        for i,(label,val) in enumerate(items):
            x=left+gap*i+(gap-bw)/2
            bh=ch*val/maxv
            canvas.create_rectangle(x,top+ch-bh,x+bw,top+ch,fill=color,outline="")
            short=label[5:] if date_labels and len(label)>5 else label
            if len(short)>8: short=short[:8]
            canvas.create_text(x+bw/2,top+ch+9,text=short,anchor="n",fill=MUTED,font=("Segoe UI",8))
            canvas.create_text(x+bw/2,top+ch-bh-9,text=str(val),fill=NAVY,font=("Segoe UI",8,"bold"))

    def fetch(self):
        ip=self.ip.get().strip()
        try: port=int(self.port.get()); key=int(self.key.get() or "0")
        except ValueError:
            messagebox.showerror("Invalid settings","Port and communication key must be numbers."); return
        self.status.set("Connecting to device…")
        threading.Thread(target=self._fetch_worker,args=(ip,port,key),daemon=True).start()

    def _fetch_worker(self,ip,port,key):
        conn=None
        try:
            from zk import ZK
            conn=ZK(ip,port=port,timeout=12,password=key,force_udp=False, ommit_ping=False).connect()
            conn.disable_device()
            rows=conn.get_attendance()
            inserted=0
            with sqlite3.connect(DB) as c:
                for row in rows:
                    stamp=row.timestamp.strftime("%Y-%m-%d %H:%M:%S")
                    cur=c.execute("INSERT OR IGNORE INTO punches(user_id,punch_time,status) VALUES(?,?,?)",(str(row.user_id),stamp,str(getattr(row,"status",""))))
                    inserted+=cur.rowcount
            self.after(0,lambda:self._fetch_done(len(rows),inserted))
        except Exception as e:
            msg=str(e); self.after(0,lambda m=msg:self._fetch_error(m))
        finally:
            if conn:
                try: conn.enable_device()
                except Exception: pass
                try: conn.disconnect()
                except Exception: pass

    def _fetch_done(self,total,inserted):
        self.refresh()
        self.status.set(f"Sync complete • {total} device records read • {inserted} new records saved")
        messagebox.showinfo("Sync complete",f"Read {total} device records.\nSaved {inserted} new records.")

    def _fetch_error(self,msg):
        self.status.set("Device connection failed.")
        messagebox.showerror("Could not fetch attendance",f"{msg}\n\nCheck the K50 IP, LAN connection, port, and communication key.")

    def import_csv(self):
        path=filedialog.askopenfilename(title="Import attendance CSV",filetypes=[("CSV files","*.csv"),("All files","*.*")])
        if not path: return
        count=0
        try:
            with open(path,"r",newline="",encoding="utf-8-sig") as f:
                sample=f.read(4096); f.seek(0)
                try: dialect=csv.Sniffer().sniff(sample) if sample.strip() else csv.excel
                except csv.Error: dialect=csv.excel
                reader=csv.DictReader(f,dialect=dialect)
                fields={x.strip().lower():x for x in (reader.fieldnames or [])}
                uidcol=next((fields[x] for x in ("user id","userid","pin","employee id","device user id") if x in fields),None)
                timecol=next((fields[x] for x in ("date/time","datetime","timestamp","punch time","date time","time") if x in fields),None)
                statecol=next((fields[x] for x in ("status","state","punch status") if x in fields),None)
                if not uidcol or not timecol: raise ValueError("CSV needs User ID/PIN and Date/Time/Timestamp columns.")
                with sqlite3.connect(DB) as c:
                    for row in reader:
                        uid=(row.get(uidcol) or "").strip(); stamp=(row.get(timecol) or "").strip(); state=(row.get(statecol) or "").strip() if statecol else ""
                        if uid and stamp:
                            try: stamp=datetime.fromisoformat(stamp).strftime("%Y-%m-%d %H:%M:%S")
                            except ValueError: pass
                            count+=c.execute("INSERT OR IGNORE INTO punches(user_id,punch_time,status) VALUES(?,?,?)",(uid,stamp,state)).rowcount
            self.refresh()
            messagebox.showinfo("Import complete",f"Imported {count} new records.")
        except Exception as e: messagebox.showerror("Import failed",str(e))

    def export_csv(self):
        rows=self._rows()
        if rows is None: return
        path=filedialog.asksaveasfilename(title="Save punch report",defaultextension=".csv",filetypes=[("CSV report","*.csv")],initialfile=f"K50_Attendance_{date.today().isoformat()}.csv")
        if not path: return
        with open(path,"w",newline="",encoding="utf-8-sig") as f:
            w=csv.writer(f); w.writerow(["Device User ID","Attendance date & time","Punch status"]); w.writerows(rows)
        messagebox.showinfo("CSV exported",f"Exported {len(rows)} records.")

    def export_pdf(self):
        rows=self._rows()
        if rows is None: return
        if not rows:
            messagebox.showwarning("No data","There are no attendance records in the selected date range."); return
        scope=self.report_user.get()
        if scope!="All staff": rows=[r for r in rows if str(r[0])==scope]
        if not rows:
            messagebox.showwarning("No data","No records found for the selected staff ID."); return
        suffix="All_Staff" if scope=="All staff" else "Staff_"+scope
        path=filedialog.asksaveasfilename(title="Save PDF attendance report",defaultextension=".pdf",filetypes=[("PDF report","*.pdf")],initialfile=f"K50_Attendance_{suffix}_{date.today().isoformat()}.pdf")
        if not path: return
        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4, landscape
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.enums import TA_CENTER
            from reportlab.lib.units import mm
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Image
            from reportlab.graphics.shapes import Drawing, String
            from reportlab.graphics.charts.barcharts import VerticalBarChart
            self._make_pdf(path,rows,scope,colors,A4,landscape,getSampleStyleSheet,ParagraphStyle,TA_CENTER,mm,SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,PageBreak,Image,Drawing,String,VerticalBarChart)
            messagebox.showinfo("PDF report created",f"Saved report to:\n{path}")
        except Exception as e:
            messagebox.showerror("PDF export failed",f"{e}\n\nIf this persists, reinstall/update the app build.")

    def _make_pdf(self,path,rows,scope,colors,A4,landscape,getStyles,ParagraphStyle,TA_CENTER,mm,Doc,Paragraph,Spacer,Table,TableStyle,PageBreak,Image,Drawing,String,VerticalBarChart):
        styles=getStyles()
        styles.add(ParagraphStyle(name="ReportTitle",parent=styles["Title"],textColor=colors.HexColor("#172554"),fontSize=20,leading=24,alignment=0,spaceAfter=5))
        styles.add(ParagraphStyle(name="SmallNote",parent=styles["BodyText"],fontSize=8,textColor=colors.HexColor("#64748b"),leading=11))
        start=self.start_date.get(); end=self.end_date.get()
        by_day={}; by_user={}; by_user_day={}
        for uid,stamp,state in rows:
            day=stamp[:10]; uid=str(uid)
            by_day[day]=by_day.get(day,0)+1
            by_user[uid]=by_user.get(uid,0)+1
            by_user_day.setdefault((uid,day),[]).append(stamp)
        days=len(by_day); users=len(by_user)
        story=[Paragraph("K50 Attendance Report",styles["ReportTitle"]),Paragraph(f"Scope: {scope}  |  Period: {start} to {end}  |  Generated: {datetime.now().strftime('%d %b %Y, %H:%M')}",styles["BodyText"]),Spacer(1,7*mm)]
        stats=[["TOTAL PUNCHES",str(len(rows)),"STAFF IDs",str(users),"ACTIVE DAYS",str(days)]]
        t=Table(stats,colWidths=[28*mm,18*mm,22*mm,18*mm,23*mm,18*mm])
        t.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),colors.HexColor("#eaf1ff")),("TEXTCOLOR",(0,0),(-1,-1),colors.HexColor("#172554")),("FONTNAME",(0,0),(-1,-1),"Helvetica-Bold"),("FONTSIZE",(0,0),(-1,-1),8),("BOX",(0,0),(-1,-1),.5,colors.HexColor("#cbd5e1")),("INNERGRID",(0,0),(-1,-1),.4,colors.HexColor("#cbd5e1")),("TOPPADDING",(0,0),(-1,-1),9),("BOTTOMPADDING",(0,0),(-1,-1),9)]))
        story.extend([t,Spacer(1,5*mm),Paragraph("Attendance activity",styles["Heading2"])])
        chart=Drawing(175*mm,58*mm)
        bc=VerticalBarChart(); bc.x=24; bc.y=16; bc.height=38*mm; bc.width=160*mm
        ordered=sorted(by_day.items())
        # Keep the graph readable for longer periods by showing up to 31 day buckets.
        ordered=ordered[-31:]
        bc.data=[tuple(v for _,v in ordered)]
        bc.categoryAxis.categoryNames=[d[5:] for d,_ in ordered]
        bc.categoryAxis.labels.fontSize=7; bc.categoryAxis.labels.angle=45; bc.categoryAxis.labels.boxAnchor="ne"
        bc.valueAxis.valueMin=0; bc.valueAxis.valueMax=max(1,max(v for _,v in ordered)*1.15); bc.valueAxis.valueStep=max(1,int(bc.valueAxis.valueMax/4))
        bc.bars[0].fillColor=colors.HexColor("#2563eb")
        chart.add(bc); story.extend([chart,Spacer(1,4*mm)])
        if scope=="All staff":
            story.append(Paragraph("Summary by staff ID",styles["Heading2"]))
            user_data=[["Device User ID","Total punches","Active days","First punch","Last punch"]]
            for uid,count in sorted(by_user.items(),key=lambda x:(-x[1],x[0])):
                u_days=sorted(d for (u,d) in by_user_day if u==uid)
                stamps=[r[1] for r in rows if str(r[0])==uid]
                user_data.append([uid,str(count),str(len(u_days)),min(stamps)[0:16],max(stamps)[0:16]])
            tab=Table(user_data,repeatRows=1,colWidths=[30*mm,25*mm,25*mm,42*mm,42*mm])
            tab.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#172554")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("FONTSIZE",(0,0),(-1,-1),8),("GRID",(0,0),(-1,-1),.35,colors.HexColor("#cbd5e1")),("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#f8fafc")]),("VALIGN",(0,0),(-1,-1),"MIDDLE"),("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5)]))
            story.extend([tab,Spacer(1,4*mm)])
        story.append(Paragraph("Detailed daily records",styles["Heading2"]))
        detail=[["Staff ID","Date","Punch count","First punch","Last punch"]]
        for (uid,day),stamps in sorted(by_user_day.items(),key=lambda x:(x[0][1],x[0][0])):
            if scope!="All staff" and uid!=scope: continue
            stamps.sort()
            detail.append([uid,day,str(len(stamps)),stamps[0][11:16],stamps[-1][11:16]])
        tab=Table(detail,repeatRows=1,colWidths=[25*mm,30*mm,25*mm,25*mm,25*mm])
        tab.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#172554")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("FONTSIZE",(0,0),(-1,-1),8),("GRID",(0,0),(-1,-1),.35,colors.HexColor("#cbd5e1")),("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#f8fafc")]),("VALIGN",(0,0),(-1,-1),"MIDDLE"),("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),4)]))
        story.extend([tab,Spacer(1,4*mm),Paragraph("Methodology: This report summarizes recorded device punches only. First/last punch is not necessarily official shift start/end. Late arrivals, absences, overtime, and paid hours require confirmed employee names, work schedules, holidays, and punch rules.",styles["SmallNote"])])
        def footer(canvas,doc):
            canvas.saveState(); canvas.setStrokeColor(colors.HexColor("#cbd5e1")); canvas.line(15*mm,13*mm,landscape(A4)[0]-15*mm if scope=="All staff" else A4[0]-15*mm,13*mm)
            canvas.setFont("Helvetica",8); canvas.setFillColor(colors.HexColor("#64748b")); canvas.drawString(15*mm,8*mm,"K50 Attendance Manager • Generated from local attendance database")
            canvas.drawRightString((landscape(A4)[0] if scope=="All staff" else A4[0])-15*mm,8*mm,f"Page {doc.page}")
            canvas.restoreState()
        # Use landscape pages for combined reports; portrait pages for individual reports.
        pagesize=landscape(A4) if scope=="All staff" else A4
        doc=Doc(path,pagesize=pagesize,rightMargin=15*mm,leftMargin=15*mm,topMargin=14*mm,bottomMargin=19*mm,title="K50 Attendance Report")
        doc.build(story,onFirstPage=footer,onLaterPages=footer)

if __name__=="__main__":
    App().mainloop()
