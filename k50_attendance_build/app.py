import csv, sqlite3, threading
from datetime import datetime, date
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

BASE = Path.home() / "K50AttendanceManager"
BASE.mkdir(exist_ok=True)
DB = BASE / "attendance.db"

def init_db():
    with sqlite3.connect(DB) as c:
        c.execute("""CREATE TABLE IF NOT EXISTS punches (
            user_id TEXT NOT NULL, punch_time TEXT NOT NULL, status TEXT DEFAULT '',
            UNIQUE(user_id,punch_time,status))""")

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("K50 Attendance Manager")
        self.geometry("980x650")
        self.minsize(800, 520)
        init_db()
        self.ip=tk.StringVar(value="192.168.1.201")
        self.port=tk.StringVar(value="4370")
        self.key=tk.StringVar(value="0")
        self.status=tk.StringVar(value="Ready")
        self._ui()
        self.refresh()

    def _ui(self):
        top=ttk.Frame(self,padding=12); top.pack(fill="x")
        ttk.Label(top,text="ZKTeco K50 Attendance Manager",font=("Segoe UI",17,"bold")).grid(row=0,column=0,columnspan=8,sticky="w",pady=(0,10))
        ttk.Label(top,text="Device IP").grid(row=1,column=0,sticky="w")
        ttk.Entry(top,textvariable=self.ip,width=18).grid(row=1,column=1,padx=5)
        ttk.Label(top,text="Port").grid(row=1,column=2)
        ttk.Entry(top,textvariable=self.port,width=8).grid(row=1,column=3,padx=5)
        ttk.Label(top,text="Comm key").grid(row=1,column=4)
        ttk.Entry(top,textvariable=self.key,width=8).grid(row=1,column=5,padx=5)
        ttk.Button(top,text="Fetch attendance",command=self.fetch).grid(row=1,column=6,padx=8)
        ttk.Button(top,text="Import CSV",command=self.import_csv).grid(row=1,column=7)
        bar=ttk.Frame(self,padding=(12,0,12,8)); bar.pack(fill="x")
        ttk.Label(bar,textvariable=self.status).pack(side="left")
        ttk.Button(bar,text="Refresh",command=self.refresh).pack(side="right")
        ttk.Button(bar,text="Export report CSV",command=self.export).pack(side="right",padx=6)
        self.tree=ttk.Treeview(self,columns=("uid","time","status"),show="headings")
        for col,title,width in [("uid","Device User ID",180),("time","Attendance date & time",280),("status","Punch status",160)]:
            self.tree.heading(col,text=title); self.tree.column(col,width=width,anchor="w")
        self.tree.pack(fill="both",expand=True,padx=12,pady=(0,8))
        foot=ttk.Label(self,padding=12,text=f"Local database: {DB}\nReports can be opened in Excel. Device access requires the PC and K50 to be on the same LAN and the correct IP/communication key.")
        foot.pack(anchor="w")

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
                    uid=str(row.user_id)
                    stamp=row.timestamp.strftime("%Y-%m-%d %H:%M:%S")
                    state=str(getattr(row,"status",""))
                    cur=c.execute("INSERT OR IGNORE INTO punches(user_id,punch_time,status) VALUES(?,?,?)",(uid,stamp,state))
                    inserted += cur.rowcount
            self.after(0,lambda:self._fetch_done(len(rows),inserted))
        except Exception as e:
            msg=str(e)
            self.after(0,lambda m=msg:self._fetch_error(m))
        finally:
            if conn:
                try: conn.enable_device()
                except Exception: pass
                try: conn.disconnect()
                except Exception: pass

    def _fetch_done(self,total,inserted):
        self.status.set(f"Fetch complete: {total} device records; {inserted} new records saved.")
        self.refresh()
        messagebox.showinfo("Attendance fetched",f"Read {total} records from the device.\nSaved {inserted} new records.")

    def _fetch_error(self,msg):
        self.status.set("Device connection failed.")
        messagebox.showerror("Could not fetch attendance",f"{msg}\n\nCheck the K50 IP, LAN connection, port, and communication key.")

    def refresh(self):
        for i in self.tree.get_children(): self.tree.delete(i)
        with sqlite3.connect(DB) as c:
            rows=c.execute("SELECT user_id,punch_time,status FROM punches ORDER BY punch_time DESC LIMIT 5000").fetchall()
        for row in rows: self.tree.insert("", "end", values=row)
        self.status.set(f"{len(rows)} records shown. Database stores attendance locally.")

    def export(self):
        path=filedialog.asksaveasfilename(title="Save attendance report",defaultextension=".csv",filetypes=[("CSV report","*.csv")],initialfile=f"K50_Attendance_{date.today().isoformat()}.csv")
        if not path: return
        with sqlite3.connect(DB) as c:
            rows=c.execute("SELECT user_id,punch_time,status FROM punches ORDER BY punch_time").fetchall()
        with open(path,"w",newline="",encoding="utf-8-sig") as f:
            w=csv.writer(f); w.writerow(["Device User ID","Attendance date & time","Punch status"]); w.writerows(rows)
        messagebox.showinfo("Report exported",f"Exported {len(rows)} records to:\n{path}")

    def import_csv(self):
        path=filedialog.askopenfilename(title="Import attendance CSV",filetypes=[("CSV files","*.csv"),("All files","*.*")])
        if not path: return
        count=0
        try:
            with open(path,"r",newline="",encoding="utf-8-sig") as f:
                sample=f.read(4096); f.seek(0)
                dialect=csv.Sniffer().sniff(sample) if sample.strip() else csv.excel
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
                            cur=c.execute("INSERT OR IGNORE INTO punches(user_id,punch_time,status) VALUES(?,?,?)",(uid,stamp,state)); count+=cur.rowcount
            self.refresh()
            messagebox.showinfo("Import complete",f"Imported {count} new records.")
        except Exception as e: messagebox.showerror("Import failed",str(e))

if __name__=="__main__":
    App().mainloop()
