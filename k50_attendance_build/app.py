import csv, sqlite3, threading, calendar, ipaddress, socket, json, os, subprocess, sys, urllib.request, webbrowser, ssl
import certifi
from html import escape
from datetime import datetime, date, timedelta
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

NEW_BASE = Path.home() / "SCAFAWorkforce"
LEGACY_BASE = Path.home() / "K50AttendanceManager"
# Keep using the legacy database when it exists, so upgrades do not silently start
# with an empty database. If a SCAFA Workforce database already exists, prefer it.
if (NEW_BASE / "attendance.db").exists() or not (LEGACY_BASE / "attendance.db").exists():
    BASE = NEW_BASE
else:
    BASE = LEGACY_BASE
BASE.mkdir(parents=True, exist_ok=True)
DB = BASE / "attendance.db"
BG = "#f5f7f4"
NAVY = "#17251d"
BLUE = "#2f6b45"
TEAL = "#477c57"
MUTED = "#68756b"
APP_VERSION = "1.2.9"
SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
RELEASE_PREFIX = "scafa-v"
TIME_VALUES = [f"{h:02d}:{m:02d}" for h in range(24) for m in (0, 15, 30, 45)]

def format_worked_time(hours):
    total_minutes=max(0,int(round(float(hours)*60)))
    whole_hours,minutes=divmod(total_minutes,60)
    return f"{whole_hours} hours {minutes} minutes"

def init_db():
    with sqlite3.connect(DB) as c:
        c.execute("""CREATE TABLE IF NOT EXISTS punches (
            user_id TEXT NOT NULL, punch_time TEXT NOT NULL, status TEXT DEFAULT '',
            UNIQUE(user_id,punch_time,status))""")
        c.execute("""CREATE TABLE IF NOT EXISTS staff (
            user_id TEXT PRIMARY KEY, name TEXT NOT NULL DEFAULT '')""")
        c.execute("""CREATE TABLE IF NOT EXISTS staff_rules (
            user_id TEXT PRIMARY KEY, start_time TEXT NOT NULL DEFAULT '10:00',
            end_time TEXT NOT NULL DEFAULT '18:00', grace_minutes INTEGER NOT NULL DEFAULT 10,
            half_day_after TEXT NOT NULL DEFAULT '12:00', min_hours REAL NOT NULL DEFAULT 4.0)""")
        c.execute("""CREATE TABLE IF NOT EXISTS app_settings (
            setting TEXT PRIMARY KEY, value TEXT NOT NULL)""")
        c.execute("""CREATE TABLE IF NOT EXISTS holidays (
            holiday_date TEXT PRIMARY KEY, label TEXT NOT NULL DEFAULT '')""")
        c.execute("""CREATE TABLE IF NOT EXISTS staff_day_rules (
            user_id TEXT NOT NULL, weekday INTEGER NOT NULL, start_time TEXT NOT NULL,
            end_time TEXT NOT NULL, grace_minutes INTEGER NOT NULL DEFAULT 15,
            shift_type TEXT NOT NULL DEFAULT 'Full day', PRIMARY KEY(user_id,weekday))""")
        c.execute("""CREATE TABLE IF NOT EXISTS staff_leave (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL,
            start_date TEXT NOT NULL, end_date TEXT NOT NULL,
            label TEXT NOT NULL DEFAULT 'Annual Leave')""")
        seed = {"weekday_window_start":"09:00","weekday_window_end":"20:00",
                "saturday_window_start":"09:00","saturday_window_end":"17:00"}
        for k,v in seed.items():
            c.execute("INSERT OR IGNORE INTO app_settings(setting,value) VALUES(?,?)",(k,v))

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("SCAFA Workforce")
        self.geometry("1280x840")
        self.minsize(1040, 700)
        self.configure(bg=BG)
        init_db()
        self.ip=tk.StringVar(value="192.168.1.201")
        self.port=tk.StringVar(value="4370")
        self.key=tk.StringVar(value="0")
        self.status=tk.StringVar(value="Ready")
        self.sort_by=tk.StringVar(value="Date (newest first)")
        self.start_date=tk.StringVar(value=date.today().replace(day=1).isoformat())
        self.end_date=tk.StringVar(value=date.today().isoformat())
        self.report_user=tk.StringVar(value="All staff")
        self._style()
        self._ui()
        self.refresh()
        self.after(30000,self._live_refresh)

    def check_for_updates(self):
        """Check GitHub Releases and offer a verified in-app update."""
        self.status.set(f"Checking for updates… (installed version {APP_VERSION})")
        def worker():
            try:
                request=urllib.request.Request(
                    "https://api.github.com/repos/NaveedQamar1/Paisa-Laya/releases/latest",
                    headers={"Accept":"application/vnd.github+json","User-Agent":"SCAFA-Workforce-Updater"})
                with urllib.request.urlopen(request,timeout=20,context=SSL_CONTEXT) as response:
                    release=json.loads(response.read().decode("utf-8"))
                tag=str(release.get("tag_name") or "")
                latest=tag.removeprefix(RELEASE_PREFIX).lstrip("v")
                current_parts=tuple(int(x) for x in APP_VERSION.split("."))
                latest_parts=tuple(int(x) for x in latest.split("."))
                if latest_parts<=current_parts:
                    self.after(0,lambda:self._update_no_update(latest or tag))
                    return
                assets={str(a.get("name")):a for a in (release.get("assets") or [])}
                if sys.platform=="win32":
                    platform="windows"; asset_name="SCAFA_Workforce_Setup.exe"
                elif sys.platform=="darwin":
                    machine=os.uname().machine.lower()
                    platform="macos"
                    asset_name=("SCAFA_Workforce_macOS_apple-silicon.zip"
                                if machine in ("arm64","aarch64") else "SCAFA_Workforce_macOS_intel.zip")
                else:
                    raise RuntimeError("In-app updates are currently supported on Windows and macOS only.")
                if asset_name not in assets or "checksums.txt" not in assets:
                    raise RuntimeError(f"Release {tag} is missing {asset_name} or checksums.txt.")
                # Store the release before scheduling the UI callback to avoid a worker/UI race.
                self._pending_release=(release,asset_name,platform)
                self.after(0,lambda t=latest:self._update_offer(t))
            except Exception as exc:
                message=str(exc)
                self.after(0,lambda m=message:self._update_check_failed(m))
        threading.Thread(target=worker,daemon=True).start()

    def _update_no_update(self,latest):
        self.status.set(f"Up to date • version {APP_VERSION}")
        messagebox.showinfo("SCAFA Workforce updates",
            f"You are using version {APP_VERSION}. The latest published version is {latest or APP_VERSION}. No update is required.")

    def _update_offer(self,latest):
        self.status.set(f"Update available • version {latest}")
        if messagebox.askyesno("SCAFA Workforce update available",
                f"Installed version: {APP_VERSION}\nLatest version: {latest}\n\nDownload and prepare this update now? Your attendance database and settings are stored separately and will be preserved."):
            threading.Thread(target=self._download_and_prepare_update,daemon=True).start()

    def _download_and_prepare_update(self):
        try:
            pending=getattr(self,"_pending_release",None)
            if not pending:
                raise RuntimeError("Update details are no longer available. Please check again.")
            release,asset_name,platform=pending
            assets={str(a.get("name")):a for a in (release.get("assets") or [])}
            base=Path.home()/"SCAFAWorkforce"/"updates"
            base.mkdir(parents=True,exist_ok=True)
            package=base/asset_name
            checksum_file=base/"checksums.txt"
            for name,destination in ((asset_name,package),("checksums.txt",checksum_file)):
                url=assets[name].get("browser_download_url")
                if not url: raise RuntimeError(f"Release asset {name} has no download URL.")
                req=urllib.request.Request(url,headers={"User-Agent":"SCAFA-Workforce-Updater"})
                with urllib.request.urlopen(req,timeout=90,context=SSL_CONTEXT) as response, open(destination,"wb") as out:
                    while True:
                        chunk=response.read(1024*1024)
                        if not chunk: break
                        out.write(chunk)
            expected=None
            for line in checksum_file.read_text(encoding="utf-8").splitlines():
                parts=line.strip().split(None,1)
                if len(parts)==2 and parts[1].lstrip("*").strip()==asset_name:
                    expected=parts[0].lower(); break
            if not expected or len(expected)!=64:
                raise RuntimeError(f"No valid SHA-256 entry was published for {asset_name}.")
            import hashlib
            digest=hashlib.sha256()
            with open(package,"rb") as stream:
                for chunk in iter(lambda:stream.read(1024*1024),b""): digest.update(chunk)
            if digest.hexdigest().lower()!=expected:
                package.unlink(missing_ok=True)
                raise RuntimeError("The downloaded update failed SHA-256 verification. The installed application has not been changed.")
            helper_name="scafa-updater.exe" if platform=="windows" else "scafa-updater"
            helper_source=Path(sys.executable).resolve().parent/helper_name
            if platform=="macos":
                helper_source=Path(sys.executable).resolve().parent/helper_name
                app_target=Path(sys.executable).resolve().parents[2]
            else:
                app_target=Path(sys.executable).resolve().parent
            if not helper_source.exists():
                raise RuntimeError("The update helper is missing from this installation. Install the latest full setup package first.")
            import shutil
            helper_copy=base/("scafa-updater-run.exe" if platform=="windows" else "scafa-updater-run")
            shutil.copy2(helper_source,helper_copy)
            command=[str(helper_copy),"--pid",str(os.getpid()),"--package",str(package),
                     "--target",str(app_target),"--platform",platform]
            if platform=="macos":
                command.extend(["--user-uid",str(os.getuid())])
            self.after(0,lambda:self._launch_update_helper(command))
        except Exception as exc:
            message=str(exc)
            self.after(0,lambda m=message:self._update_check_failed(m))

    def _launch_update_helper(self,command):
        if not messagebox.askyesno("Ready to install update",
                "The update has been downloaded and verified. SCAFA Workforce will close, install the update and reopen. Continue?"):
            self.status.set("Update downloaded; installation cancelled.")
            return
        try:
            subprocess.Popen(command,close_fds=True)
            self.destroy()
        except Exception as exc:
            messagebox.showerror("Could not start update",str(exc))

    def _update_check_failed(self,message):
        self.status.set("Could not complete update check.")
        messagebox.showwarning("SCAFA Workforce update unavailable",
            f"Could not check or prepare the update. Your installed application has not been changed.\n\n{message}")

    def configure_background_monitoring(self):
        """Enable or disable the per-user attendance-device background monitor on macOS or Windows."""
        try:
            port = int(self.port.get())
            key = int(self.key.get() or "0")
            ip = self.ip.get().strip()
            if not ip or not 1 <= port <= 65535:
                raise ValueError()
        except ValueError:
            messagebox.showerror("Invalid device settings", "Enter a valid device IP, port and numeric communication key first.")
            return

        base = Path.home() / "SCAFAWorkforce"
        base.mkdir(parents=True, exist_ok=True)
        config = base / "device.json"
        config.write_text(json.dumps({"ip": ip, "port": port, "key": key, "interval": 10}), encoding="utf-8")

        if sys.platform == "win32":
            task_name = "SCAFA Workforce Attendance Monitor"
            executable = Path(sys.executable).resolve().parent / "scafa-monitor.exe"
            if not executable.exists():
                messagebox.showerror("Monitor helper missing", "The Windows background monitor is not included in this installer. Please install the latest Windows setup.")
                return
            if messagebox.askyesno(
                "Background monitoring",
                "Enable attendance-device monitoring every 10 seconds and start automatically whenever you sign in to Windows?\n\nWindows notifications will appear when new punches are detected. Your PC must be awake and connected to the same network as the device."
            ):
                command = f'"{executable}"'
                result = subprocess.run(
                    ["schtasks", "/Create", "/SC", "ONLOGON", "/TN", task_name,
                     "/TR", command, "/RL", "LIMITED", "/F"],
                    capture_output=True, text=True
                )
                if result.returncode:
                    messagebox.showerror("Could not enable monitoring", result.stderr or result.stdout or "Task Scheduler failed.")
                    return
                subprocess.run(["schtasks", "/Run", "/TN", task_name], capture_output=True, text=True)
                self.status.set("Background device monitoring enabled • checks every 10 seconds")
                messagebox.showinfo("Monitoring enabled", "SCAFA Workforce will now monitor the device in the background and start automatically when you sign in.")
            else:
                subprocess.run(["schtasks", "/End", "/TN", task_name], capture_output=True, text=True)
                subprocess.run(["schtasks", "/Delete", "/TN", task_name, "/F"], capture_output=True, text=True)
                self.status.set("Background device monitoring disabled")
                messagebox.showinfo("Monitoring disabled", "The background attendance-device monitor has been stopped and removed from Windows startup.")
            return

        if sys.platform == "darwin":
            label = "pk.scafa.workforce.monitor"
            agent_dir = Path.home() / "Library" / "LaunchAgents"
            agent_dir.mkdir(parents=True, exist_ok=True)
            plist = agent_dir / (label + ".plist")
            executable = Path(sys.executable).resolve().parent / "scafa-monitor"
            if not executable.exists():
                messagebox.showerror("Monitor helper missing", "The background monitor is not included in this app build. Please install the latest macOS package.")
                return
            if messagebox.askyesno(
                "Background monitoring",
                "Enable attendance-device monitoring every 10 seconds and start automatically whenever you log in?\n\nmacOS notifications will appear when new punches are detected. Your Mac must be awake and connected to the same network as the device."
            ):
                import plistlib
                payload = {
                    "Label": label,
                    "ProgramArguments": [str(executable)],
                    "RunAtLoad": True,
                    "KeepAlive": True,
                    "StandardOutPath": str(base / "monitor.log"),
                    "StandardErrorPath": str(base / "monitor-error.log")
                }
                plist.write_bytes(plistlib.dumps(payload))
                uid = os.getuid()
                subprocess.run(["launchctl", "bootout", f"gui/{uid}", str(plist)], capture_output=True, text=True)
                result = subprocess.run(["launchctl", "bootstrap", f"gui/{uid}", str(plist)], capture_output=True, text=True)
                if result.returncode:
                    messagebox.showerror("Could not start monitoring", result.stderr or result.stdout or "launchctl failed")
                    return
                self.status.set("Background device monitoring enabled • checks every 10 seconds")
                messagebox.showinfo("Monitoring enabled", "SCAFA Workforce will now check the device in the background and start automatically when you log in.")
            else:
                uid = os.getuid()
                subprocess.run(["launchctl", "bootout", f"gui/{uid}", str(plist)], capture_output=True, text=True)
                if plist.exists():
                    plist.unlink()
                self.status.set("Background device monitoring disabled")
                messagebox.showinfo("Monitoring disabled", "The background K50 monitor has been stopped and removed from login startup.")
            return

        messagebox.showinfo("Background monitoring", "Automatic background monitoring is supported by the Windows and macOS desktop builds.")

    def _date_field(self, parent, variable, width=12):
        wrap=ttk.Frame(parent)
        ttk.Entry(wrap,textvariable=variable,width=width).pack(side="left")
        ttk.Button(wrap,text="▦",width=3,command=lambda:self._open_calendar(variable)).pack(side="left",padx=(3,0))
        return wrap

    def _open_calendar(self, variable):
        try:
            selected=datetime.strptime(variable.get().strip(),"%Y-%m-%d").date()
        except ValueError:
            selected=date.today()
        popup=tk.Toplevel(self); popup.title("Select date"); popup.resizable(False,False); popup.transient(self); popup.grab_set()
        state={"year":selected.year,"month":selected.month}
        head=ttk.Frame(popup,padding=8); head.pack(fill="x")
        grid=ttk.Frame(popup,padding=(8,0,8,8)); grid.pack()
        def draw():
            for child in grid.winfo_children(): child.destroy()
            for child in head.winfo_children(): child.destroy()
            ttk.Button(head,text="‹",width=3,command=lambda:move(-1)).pack(side="left")
            ttk.Label(head,text=f"{calendar.month_name[state['month']]} {state['year']}",font=("Segoe UI",11,"bold")).pack(side="left",expand=True,padx=12)
            ttk.Button(head,text="›",width=3,command=lambda:move(1)).pack(side="right")
            for col,name in enumerate(("Mo","Tu","We","Th","Fr","Sa","Su")):
                ttk.Label(grid,text=name,width=4,anchor="center").grid(row=0,column=col,padx=1,pady=3)
            for row,week in enumerate(calendar.monthcalendar(state["year"],state["month"]),1):
                for col,daynum in enumerate(week):
                    if daynum:
                        ttk.Button(grid,text=str(daynum),width=4,command=lambda d=daynum:choose(d)).grid(row=row,column=col,padx=1,pady=1)
            ttk.Button(popup,text="Today",command=choose_today).pack(pady=(0,8))
        def move(delta):
            month=state["month"]+delta
            if month<1: state["year"]-=1; month=12
            elif month>12: state["year"]+=1; month=1
            state["month"]=month; draw()
        def choose(daynum):
            variable.set(date(state["year"],state["month"],daynum).isoformat()); popup.destroy()
        def choose_today():
            variable.set(date.today().isoformat()); popup.destroy()
        draw()

    def _valid_ip_edit(self, proposed):
        return len(proposed)<=15 and all(ch in "0123456789." for ch in proposed)

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
        s.configure("Treeview", rowheight=34, font=("Segoe UI",9), background="white", fieldbackground="white", borderwidth=0)
        s.configure("Treeview.Heading", font=("Segoe UI",9,"bold"), background="#e5eee7", foreground=NAVY, padding=(8,9))
        s.configure("TNotebook", background=BG, borderwidth=0)
        s.configure("TNotebook.Tab", padding=(20,11), font=("Segoe UI",10,"bold"))
        s.configure("TEntry", padding=6)
        s.configure("TCombobox", padding=6)
        s.configure("TButton", padding=(10,7), font=("Segoe UI",9))

    def _ui(self):
        # Brand-led header: script lettering echoes the original SCAFA wordmark.
        header=tk.Frame(self,bg="#496849",height=108); header.pack(fill="x")
        header.pack_propagate(False)
        brand_font = "Apple Chancery" if sys.platform == "darwin" else "Segoe Script"
        tk.Label(header,text="Scafa",bg="#496849",fg="#f7f8ec",
                 font=(brand_font,31),anchor="w").pack(anchor="w",padx=25,pady=(7,0))
        tk.Label(header,text="Workforce",bg="#496849",fg="#f7f8ec",
                 font=(brand_font,17,"italic"),anchor="w").pack(anchor="w",padx=28,pady=(0,5))
        conn=ttk.Frame(self,padding=(18,14,18,10)); conn.pack(fill="x")
        ttk.Label(conn,text="DEVICE CONNECTION",font=("Segoe UI",9,"bold")).grid(row=0,column=0,columnspan=8,sticky="w",pady=(0,6))
        for col,label,var,width in [(0,"Device IP",self.ip,17),(2,"Port",self.port,7),(4,"Comm key",self.key,7)]:
            ttk.Label(conn,text=label).grid(row=1,column=col,sticky="w",padx=(0,5))
            if label=="Device IP":
                vcmd=(self.register(self._valid_ip_edit),"%P")
                ttk.Entry(conn,textvariable=var,width=18,validate="key",validatecommand=vcmd).grid(row=1,column=col+1,sticky="w",padx=(0,16))
            else:
                ttk.Entry(conn,textvariable=var,width=width).grid(row=1,column=col+1,sticky="w",padx=(0,16))
        ttk.Button(conn,text="⟳  Fetch Attendance",style="Accent.TButton",command=self.fetch).grid(row=1,column=6,padx=(0,8))
        ttk.Button(conn,text="＋  Import CSV",command=self.import_csv).grid(row=1,column=7)
        ttk.Button(conn,text="⚙  Custom Rules",command=self.open_rules).grid(row=1,column=8,padx=(8,0))
        ttk.Button(conn,text="Staff Schedules",command=self.open_staff_schedules).grid(row=1,column=9,padx=(8,0))
        ttk.Button(conn,text="Backup Database",command=self.backup_database).grid(row=2,column=6,sticky="w",pady=(8,0))
        ttk.Button(conn,text="Restore Database",command=self.restore_database).grid(row=2,column=7,sticky="w",pady=(8,0))
        ttk.Button(conn,text="Discover Compatible Devices",command=self.discover_device).grid(row=2,column=8,sticky="w",padx=(8,0),pady=(8,0))
        ttk.Button(conn,text="Background Monitoring",command=self.configure_background_monitoring).grid(row=2,column=9,sticky="w",padx=(8,0),pady=(8,0))
        ttk.Button(conn,text="Check for Updates",command=self.check_for_updates).grid(row=2,column=10,sticky="w",padx=(8,0),pady=(8,0))
        filters=ttk.Frame(self,padding=(18,0,18,10)); filters.pack(fill="x")
        ttk.Label(filters,text="From").pack(side="left")
        self._date_field(filters,self.start_date).pack(side="left",padx=(6,14))
        ttk.Label(filters,text="To").pack(side="left")
        self._date_field(filters,self.end_date).pack(side="left",padx=(6,14))
        ttk.Button(filters,text="Apply dates",command=self.refresh).pack(side="left")
        ttk.Label(filters,text="PDF scope").pack(side="left",padx=(22,6))
        self.user_combo=ttk.Combobox(filters,textvariable=self.report_user,width=18,state="readonly",values=["All staff"])
        self.user_combo.pack(side="left")
        ttk.Button(filters,text="Export PDF report",style="Accent.TButton",command=self.export_pdf).pack(side="right")
        ttk.Button(filters,text="Export Excel",command=self.export_excel).pack(side="right",padx=8)
        ttk.Button(filters,text="Export CSV",command=self.export_csv).pack(side="right",padx=8)
        self.tabs=ttk.Notebook(self); self.tabs.pack(fill="both",expand=True,padx=18,pady=(0,8))
        self.dashboard=ttk.Frame(self.tabs,padding=12); self.records=ttk.Frame(self.tabs,padding=12)
        self.tabs.add(self.dashboard,text="  ◈ Dashboard  "); self.tabs.add(self.records,text="  ☷ Punch records  ")
        self._dashboard_ui(); self._records_ui()
        footer=tk.Frame(self,bg="#e8eef8",height=30); footer.pack(fill="x",side="bottom")
        tk.Label(footer,textvariable=self.status,bg="#e8eef8",fg=MUTED,font=("Segoe UI",9),anchor="w").pack(fill="x",padx=18,pady=6)

    def _dashboard_ui(self):
        toolbar=ttk.Frame(self.dashboard)
        toolbar.pack(fill="x",pady=(0,8))
        ttk.Label(toolbar,text="Dashboard view").pack(side="left")
        self.dashboard_employee=tk.StringVar(value="All staff")
        self.dashboard_employee_combo=ttk.Combobox(toolbar,textvariable=self.dashboard_employee,
            state="readonly",width=28,values=["All staff"])
        self.dashboard_employee_combo.pack(side="left",padx=8)
        self.dashboard_employee_combo.bind("<<ComboboxSelected>>",lambda _e:self._update_dashboard(self._rows()))
        self.latest_punch_label=ttk.Label(self.dashboard,text="LATEST PUNCH  •  No punch records in this date range",
            font=("Segoe UI",11,"bold"),background="#e8f1eb",foreground=NAVY,padding=12)
        self.latest_punch_label.pack(fill="x",pady=(0,10))
        self.cards=ttk.Frame(self.dashboard); self.cards.pack(fill="x",pady=(0,10))
        self.card_values=[]
        labels=["ON-TIME RATE","LATE ARRIVALS","EARLY DEPARTURES","ABSENCES","INCOMPLETE PUNCHES","AVG. ARRIVAL"]
        for i,title in enumerate(labels):
            card=ttk.Frame(self.cards,style="Card.TFrame",padding=11); card.grid(row=0,column=i,sticky="nsew",padx=3)
            self.cards.columnconfigure(i,weight=1)
            ttk.Label(card,text=title,style="CardTitle.TLabel").pack(anchor="w")
            val=ttk.Label(card,text="—",style="CardValue.TLabel",font=("Segoe UI",17,"bold")); val.pack(anchor="w",pady=(7,0))
            self.card_values.append(val)

        # Dashboard charts must exist before the initial refresh calls _draw_charts().
        charts=ttk.Frame(self.dashboard)
        charts.pack(fill="both",expand=False,pady=(0,8))
        daily_panel=ttk.Frame(charts,style="Card.TFrame",padding=8)
        daily_panel.pack(side="left",fill="both",expand=True,padx=(0,4))
        ttk.Label(daily_panel,text="DAILY PUNCH ACTIVITY",font=("Segoe UI",10,"bold"),background="white").pack(anchor="w")
        self.daily_canvas=tk.Canvas(daily_panel,height=190,bg="white",highlightthickness=0)
        self.daily_canvas.pack(fill="both",expand=True)
        staff_panel=ttk.Frame(charts,style="Card.TFrame",padding=8)
        staff_panel.pack(side="left",fill="both",expand=True,padx=(4,0))
        ttk.Label(staff_panel,text="PUNCHES BY EMPLOYEE",font=("Segoe UI",10,"bold"),background="white").pack(anchor="w")
        self.staff_canvas=tk.Canvas(staff_panel,height=190,bg="white",highlightthickness=0)
        self.staff_canvas.pack(fill="both",expand=True)

        comparison=ttk.Frame(self.dashboard,style="Card.TFrame",padding=10)
        comparison.pack(fill="both",expand=True,pady=(0,8))
        ttk.Label(comparison,text="EMPLOYEE ATTENDANCE COMPARISON",
            font=("Segoe UI",11,"bold"),background="white").pack(anchor="w",pady=(0,7))
        cols=("name","expected","present","late","early","absent","ontime","rate","average")
        self.comparison_tree=ttk.Treeview(comparison,columns=cols,show="headings",height=8)
        specs=[("name","Employee",180),("expected","Expected days",95),("present","Present",75),
               ("late","Late",65),("early","Early leave",85),("absent","Absent",70),
               ("ontime","On time",75),("rate","On-time %",85),("average","Avg arrival",95)]
        for col,title,width in specs:
            self.comparison_tree.heading(col,text=title)
            self.comparison_tree.column(col,width=width,minwidth=55,anchor="center" if col!="name" else "w")
        self.comparison_tree.pack(fill="both",expand=True)
        self.comparison_tree.tag_configure("good",foreground="#166534")
        self.comparison_tree.tag_configure("attention",foreground="#b45309")
        ttk.Label(self.dashboard,text="Figures use the selected date range and each employee’s saved schedule, grace period and holiday rules.",
            style="Sub.TLabel").pack(anchor="w",pady=(3,0))

    def _records_ui(self):
        toolbar=ttk.Frame(self.records); toolbar.pack(fill="x",pady=(0,8))
        ttk.Label(toolbar,text="Sort by").pack(side="left",padx=(2,6))
        self.sort_by=tk.StringVar(value="Date (newest first)")
        self.sort_combo=ttk.Combobox(toolbar,textvariable=self.sort_by,state="readonly",width=27,values=[
            "Date (newest first)","Date (oldest first)","Employee (A–Z)","Employee (Z–A)",
            "Punch time (earliest first)","Punch time (latest first)","Punch count (highest first)",
            "Punch count (lowest first)","Active hours (highest first)","Active hours (lowest first)",
            "Attendance status (A–Z)","Employee ID (ascending)","Employee ID (descending)"])
        self.sort_combo.pack(side="left")
        ttk.Button(toolbar,text="Apply sort",command=self.refresh).pack(side="left",padx=8)
        cols=("uid","name","date","checkin","checkout","active","attendance")
        self.tree=ttk.Treeview(self.records,columns=cols,show="headings")
        specs=[("uid","Assigned ID",82),("name","Staff name",175),
               ("date","Date",105),("checkin","Check-in",105),
               ("checkout","Check-out",105),("active","Active hours",135),
               ("attendance","Attendance status",170)]
        for col,title,width in specs:
            self.tree.heading(col,text=title,anchor="w")
            self.tree.column(col,width=width,minwidth=75,stretch=True,anchor="w")
        self.tree.pack(fill="both",expand=True,padx=2,pady=2)
        self.tree.tag_configure("odd",background="#f4f7f5")
        self.tree.tag_configure("even",background="#ffffff")
        self.tree.tag_configure("late",foreground="#b45309")
        self.tree.tag_configure("early",foreground="#b91c1c")
        self.tree.tag_configure("open",foreground="#166534")

    def _rules(self):
        defaults={"default_start":"09:45","default_end":"20:00","default_grace":"15",
                  "half_day_after":"12:00","min_hours":"4.0","workdays":"0,1,2,3,4,5",
                  "weekday_window_start":"09:00","weekday_window_end":"20:00",
                  "saturday_window_start":"09:00","saturday_window_end":"17:00"}
        with sqlite3.connect(DB) as c:
            saved=dict(c.execute("SELECT setting,value FROM app_settings"))
            rules={k:saved.get(k,v) for k,v in defaults.items()}
            staff_rules={str(r[0]):{"start":r[1],"end":r[2],"grace":int(r[3]),"half":r[4],"min_hours":float(r[5])}
                         for r in c.execute("SELECT user_id,start_time,end_time,grace_minutes,half_day_after,min_hours FROM staff_rules")}
            holidays=dict(c.execute("SELECT holiday_date,label FROM holidays"))
        return rules,staff_rules,holidays

    def open_rules(self):
        rules,staff_rules,holidays=self._rules()
        win=tk.Toplevel(self); win.title("Custom Attendance Rules"); win.geometry("900x680"); win.minsize(780,560); win.transient(self)
        outer=ttk.Frame(win,padding=16); outer.pack(fill="both",expand=True)
        ttk.Label(outer,text="CUSTOM ATTENDANCE RULES",font=("Segoe UI",16,"bold")).pack(anchor="w")
        ttk.Label(outer,text="Set defaults, then override schedules for individual staff. Rules apply to attendance reports.",style="Sub.TLabel").pack(anchor="w",pady=(2,12))
        defaults=ttk.LabelFrame(outer,text="Default schedule and thresholds",padding=10); defaults.pack(fill="x")
        vars={}
        fields=[("default_start","Default shift start"),("default_end","Default shift end"),("default_grace","Default grace (minutes)"),("half_day_after","Half-day cutoff"),("min_hours","Minimum hours for full day"),("workdays","Working weekdays (0=Mon, 6=Sun)"),("weekday_window_start","Weekday punch window start"),("weekday_window_end","Weekday punch window end"),("saturday_window_start","Saturday punch window start"),("saturday_window_end","Saturday punch window end")]
        time_keys={"default_start","default_end","half_day_after","weekday_window_start","weekday_window_end","saturday_window_start","saturday_window_end"}
        def time_values_for(value): return sorted(set(TIME_VALUES+[value]))
        for i,(key,label) in enumerate(fields):
            row=i//3; col=(i%3)*2
            ttk.Label(defaults,text=label).grid(row=row,column=col,sticky="w",padx=(0,5),pady=5)
            vars[key]=tk.StringVar(value=rules[key])
            if key in time_keys:
                ttk.Combobox(defaults,textvariable=vars[key],values=time_values_for(rules[key]),state="readonly",width=17).grid(row=row,column=col+1,sticky="ew",padx=(0,12),pady=5)
            else:
                ttk.Entry(defaults,textvariable=vars[key],width=20).grid(row=row,column=col+1,sticky="ew",padx=(0,12),pady=5)
        for col in range(6): defaults.columnconfigure(col,weight=1)
        staffbox=ttk.LabelFrame(outer,text="Per-staff schedule overrides",padding=8); staffbox.pack(fill="both",expand=True,pady=(12,0))
        ttk.Label(staffbox,text="Select an employee, then set their shift, grace period, half-day cutoff and minimum hours.").pack(anchor="w")
        available=sorted(set(self._staff_names())|set(staff_rules),key=lambda x:(not x.isdigit(),int(x) if x.isdigit() else x.lower()))
        choices=[f"{self._name(uid)} ({uid})" for uid in available]
        selected=tk.StringVar(value=choices[0] if choices else "")
        top=ttk.Frame(staffbox); top.pack(fill="x",pady=8)
        ttk.Label(top,text="Staff").pack(side="left")
        combo=ttk.Combobox(top,textvariable=selected,values=choices,state="readonly",width=34); combo.pack(side="left",padx=8)
        ov={}
        for i,(key,label) in enumerate([("start","Shift start"),("end","Shift end"),("grace","Grace minutes"),("half","Half-day cutoff"),("min_hours","Minimum hours")]):
            ttk.Label(top,text=label).pack(side="left",padx=(6,2))
            ov[key]=tk.StringVar(value="")
            if key in ("start","end","half"):
                ttk.Combobox(top,textvariable=ov[key],values=TIME_VALUES,state="readonly",width=8).pack(side="left",padx=(0,3))
            else:
                ttk.Entry(top,textvariable=ov[key],width=8).pack(side="left",padx=(0,3))
        def load_staff(*_):
            uid=selected.get().rsplit(" (",1)[-1].rstrip(")") if selected.get() else ""
            r=staff_rules.get(uid,{})
            for k,default_key in [("start","default_start"),("end","default_end"),("grace","default_grace"),("half","half_day_after"),("min_hours","min_hours")]:
                ov[k].set(str(r.get(k,vars[default_key].get())))
        combo.bind("<<ComboboxSelected>>",load_staff)
        def save_override():
            label=selected.get()
            if not label: messagebox.showwarning("Select staff","Fetch staff from the connected device first or select a staff member."); return
            uid=label.rsplit(" (",1)[-1].rstrip(")")
            try:
                datetime.strptime(ov["start"].get(),"%H:%M"); datetime.strptime(ov["end"].get(),"%H:%M"); datetime.strptime(ov["half"].get(),"%H:%M")
                grace=int(ov["grace"].get()); hours=float(ov["min_hours"].get())
                if grace<0 or hours<0 or hours>24: raise ValueError()
            except ValueError:
                messagebox.showerror("Invalid rule","Use HH:MM times, non-negative grace minutes, and minimum hours from 0 to 24."); return
            staff_rules[uid]={"start":ov["start"].get(),"end":ov["end"].get(),"grace":grace,"half":ov["half"].get(),"min_hours":hours}
            messagebox.showinfo("Schedule override","Override prepared. Click Save all rules to save changes.")
        ttk.Button(staffbox,text="Save selected staff override",command=save_override).pack(anchor="e",pady=(0,8))
        holidaysbox=ttk.LabelFrame(outer,text="Public holidays / closed dates",padding=8); holidaysbox.pack(fill="x",pady=(12,0))
        hrow=ttk.Frame(holidaysbox); hrow.pack(fill="x")
        hstart=tk.StringVar(); hend=tk.StringVar(); hlabel=tk.StringVar()
        ttk.Label(hrow,text="From").pack(side="left"); self._date_field(hrow,hstart,width=12).pack(side="left",padx=4)
        ttk.Label(hrow,text="To").pack(side="left"); self._date_field(hrow,hend,width=12).pack(side="left",padx=4)
        ttk.Label(hrow,text="Label").pack(side="left"); ttk.Entry(hrow,textvariable=hlabel,width=20).pack(side="left",padx=4)
        holiday_list=tk.Listbox(holidaysbox,height=4); holiday_list.pack(fill="x",pady=6)
        def refresh_holidays():
            holiday_list.delete(0,"end")
            for d,l in sorted(holidays.items()): holiday_list.insert("end",f"{d} — {l}")
        def add_holiday():
            try:
                first=datetime.strptime(hstart.get().strip(),"%Y-%m-%d").date()
                last=datetime.strptime(hend.get().strip(),"%Y-%m-%d").date()
                if last<first: raise ValueError()
            except ValueError:
                messagebox.showerror("Invalid date range","Enter valid dates in YYYY-MM-DD format. The To date must not be earlier than the From date."); return
            label=hlabel.get().strip() or "Holiday"
            cursor=first
            while cursor<=last:
                holidays[cursor.isoformat()]=label
                cursor+=timedelta(days=1)
            refresh_holidays()
        def remove_holiday():
            sel=holiday_list.curselection()
            if not sel: return
            d=holiday_list.get(sel[0]).split(" — ",1)[0]; holidays.pop(d,None); refresh_holidays()
        hb=ttk.Frame(holidaysbox); hb.pack(fill="x")
        ttk.Button(hb,text="Add holiday",command=add_holiday).pack(side="left")
        ttk.Button(hb,text="Remove selected",command=remove_holiday).pack(side="left",padx=8)
        refresh_holidays(); load_staff()
        def save_all():
            try:
                datetime.strptime(vars["default_start"].get(),"%H:%M"); datetime.strptime(vars["default_end"].get(),"%H:%M"); datetime.strptime(vars["half_day_after"].get(),"%H:%M")
                grace=int(vars["default_grace"].get()); hours=float(vars["min_hours"].get())
                days=[int(x.strip()) for x in vars["workdays"].get().split(",") if x.strip()]
                if grace<0 or hours<0 or hours>24 or not days or any(x<0 or x>6 for x in days): raise ValueError()
            except ValueError:
                messagebox.showerror("Invalid defaults","Check HH:MM times, grace, hours, and weekdays (0–6)."); return
            with sqlite3.connect(DB) as c:
                for k,v in vars.items(): c.execute("INSERT INTO app_settings(setting,value) VALUES(?,?) ON CONFLICT(setting) DO UPDATE SET value=excluded.value",(k,v.get().strip()))
                for uid,r in staff_rules.items():
                    c.execute("""INSERT INTO staff_rules(user_id,start_time,end_time,grace_minutes,half_day_after,min_hours) VALUES(?,?,?,?,?,?)
                                 ON CONFLICT(user_id) DO UPDATE SET start_time=excluded.start_time,end_time=excluded.end_time,grace_minutes=excluded.grace_minutes,half_day_after=excluded.half_day_after,min_hours=excluded.min_hours""",
                              (uid,r["start"],r["end"],r["grace"],r["half"],r["min_hours"]))
                c.execute("DELETE FROM holidays")
                c.executemany("INSERT INTO holidays(holiday_date,label) VALUES(?,?)",sorted(holidays.items()))
            messagebox.showinfo("Rules saved","Custom attendance rules saved on this computer.")
            win.destroy()
        buttons=ttk.Frame(outer); buttons.pack(fill="x",pady=(12,0))
        ttk.Button(buttons,text="Save all rules",style="Accent.TButton",command=save_all).pack(side="right")
        ttk.Button(buttons,text="Close",command=win.destroy).pack(side="right",padx=8)

    def open_staff_schedules(self):
        """Set individual schedules for each employee and weekday."""
        with sqlite3.connect(DB) as c:
            staff = dict(c.execute("SELECT user_id,name FROM staff"))
            existing = {(str(uid),int(wd)):(st,en,int(gr),typ) for uid,wd,st,en,gr,typ in
                c.execute("SELECT user_id,weekday,start_time,end_time,grace_minutes,shift_type FROM staff_day_rules")}
        staff.update({uid:self._name(uid) for uid in self._staff_names()})
        if not staff:
            messagebox.showinfo("No employees","Fetch employee names from the connected device first.")
            return
        win=tk.Toplevel(self); win.title("SCAFA Workforce — Staff Schedules & Leave"); win.geometry("980x760"); win.minsize(900,680); win.transient(self)
        outer=ttk.Frame(win,padding=16); outer.pack(fill="both",expand=True)
        ttk.Label(outer,text="EMPLOYEE SCHEDULES & LEAVE",font=("Segoe UI",16,"bold")).pack(anchor="w")
        ttk.Label(outer,text="Set each employee's weekly shift, then record multiple approved leave periods. Leave dates are excluded from absence calculations.",style="Sub.TLabel").pack(anchor="w",pady=(3,12))
        choices=[f"{staff[uid]} ({uid})" for uid in sorted(staff,key=lambda x:staff[x].lower())]
        selected=tk.StringVar(value=choices[0]); top=ttk.Frame(outer); top.pack(fill="x")
        ttk.Label(top,text="Employee").pack(side="left")
        combo=ttk.Combobox(top,textvariable=selected,values=choices,state="readonly",width=40); combo.pack(side="left",padx=8)
        grid=ttk.Frame(outer); grid.pack(fill="both",expand=True,pady=12)
        for j,title in enumerate(("Day","Start (HH:MM)","End (HH:MM)","Grace minutes","Shift type")):
            ttk.Label(grid,text=title,font=("Segoe UI",9,"bold")).grid(row=0,column=j,sticky="w",padx=5,pady=5)
        days=("Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday")
        cells={}
        for wd,name in enumerate(days):
            ttk.Label(grid,text=name).grid(row=wd+1,column=0,sticky="w",padx=5,pady=4)
            vals=existing.get((selected.get().rsplit(" (",1)[-1].rstrip(")"),wd),("09:45","20:00" if wd<5 else "17:00",15,"Off" if wd==6 else "Full day"))
            sv,ev,gv,tv=tk.StringVar(value=vals[0]),tk.StringVar(value=vals[1]),tk.StringVar(value=str(vals[2])),tk.StringVar(value=vals[3])
            cells[wd]=(sv,ev,gv,tv)
            ttk.Combobox(grid,textvariable=sv,values=sorted(set(TIME_VALUES+[vals[0]])),state="readonly",width=12).grid(row=wd+1,column=1,padx=5,pady=3)
            ttk.Combobox(grid,textvariable=ev,values=sorted(set(TIME_VALUES+[vals[1]])),state="readonly",width=12).grid(row=wd+1,column=2,padx=5,pady=3)
            ttk.Entry(grid,textvariable=gv,width=14).grid(row=wd+1,column=3,padx=5,pady=3)
            ttk.Combobox(grid,textvariable=tv,values=("Full day","Half day","Custom","Off"),state="readonly",width=13).grid(row=wd+1,column=4,padx=5,pady=3)
        def load_employee(*_):
            uid=selected.get().rsplit(" (",1)[-1].rstrip(")")
            for wd in range(7):
                vals=existing.get((uid,wd),("09:45","20:00" if wd<5 else "17:00",15,"Off" if wd==6 else "Full day"))
                for var,val in zip(cells[wd],vals): var.set(str(val))
        leavebox=ttk.LabelFrame(outer,text="Individual employee leave / planned days off",padding=10)
        leavebox.pack(fill="both",expand=True,pady=(2,10))
        ttk.Label(leavebox,text="Add one day or a date range. Examples: Annual Leave, Sick Leave, Personal Leave, Training or Other approved leave.",style="Sub.TLabel").pack(anchor="w")
        leave_form=ttk.Frame(leavebox); leave_form.pack(fill="x",pady=(8,4))
        leave_start=tk.StringVar(value=date.today().isoformat())
        leave_end=tk.StringVar(value=date.today().isoformat())
        leave_reason=tk.StringVar(value="Annual Leave")
        ttk.Label(leave_form,text="From").pack(side="left")
        self._date_field(leave_form,leave_start,width=12).pack(side="left",padx=(4,10))
        ttk.Label(leave_form,text="To").pack(side="left")
        self._date_field(leave_form,leave_end,width=12).pack(side="left",padx=(4,10))
        ttk.Label(leave_form,text="Reason").pack(side="left")
        ttk.Combobox(leave_form,textvariable=leave_reason,
            values=("Annual Leave","Sick Leave","Personal Leave","Training","Other approved leave"),
            width=22).pack(side="left",padx=4)
        leave_list=tk.Listbox(leavebox,height=5,exportselection=False)
        leave_list.pack(fill="both",expand=True,pady=6)
        leave_records=[]
        def refresh_leave():
            leave_list.delete(0,"end")
            uid=selected.get().rsplit(" (",1)[-1].rstrip(")") if selected.get() else ""
            with sqlite3.connect(DB) as c:
                records=c.execute("SELECT id,start_date,end_date,label FROM staff_leave WHERE user_id=? ORDER BY start_date,end_date,id",(uid,)).fetchall()
            leave_records.clear(); leave_records.extend(records)
            for rid,first,last,label in records:
                span=first if first==last else f"{first} to {last}"
                leave_list.insert("end",f"{span} — {label}")
        def add_leave():
            uid=selected.get().rsplit(" (",1)[-1].rstrip(")") if selected.get() else ""
            try:
                first=datetime.strptime(leave_start.get().strip(),"%Y-%m-%d").date()
                last=datetime.strptime(leave_end.get().strip(),"%Y-%m-%d").date()
                if last<first or (last-first).days>366: raise ValueError()
                reason=leave_reason.get().strip() or "Approved Leave"
            except ValueError:
                messagebox.showerror("Invalid leave dates","Enter valid YYYY-MM-DD dates. The end date must not be before the start date, and a leave period cannot exceed 367 days."); return
            with sqlite3.connect(DB) as c:
                c.execute("INSERT INTO staff_leave(user_id,start_date,end_date,label) VALUES(?,?,?,?)",
                          (uid,first.isoformat(),last.isoformat(),reason))
            refresh_leave()
            self.status.set(f"Leave added for {self._name(uid)}")
        def remove_leave():
            sel=leave_list.curselection()
            if not sel: return
            record=leave_records[sel[0]]
            if not messagebox.askyesno("Remove leave","Remove this employee leave period? Attendance calculations will be recalculated on refresh."): return
            with sqlite3.connect(DB) as c: c.execute("DELETE FROM staff_leave WHERE id=?",(record[0],))
            refresh_leave()
        leave_buttons=ttk.Frame(leavebox); leave_buttons.pack(fill="x")
        ttk.Button(leave_buttons,text="Add leave period",command=add_leave).pack(side="left")
        ttk.Button(leave_buttons,text="Remove selected leave",command=remove_leave).pack(side="left",padx=8)
        combo.bind("<<ComboboxSelected>>",lambda _e:(load_employee(),refresh_leave()))
        def save():
            uid=selected.get().rsplit(" (",1)[-1].rstrip(")")
            try:
                rows=[]
                for wd,vs in cells.items():
                    st,en,gr,typ=[v.get().strip() for v in vs]
                    datetime.strptime(st,"%H:%M"); datetime.strptime(en,"%H:%M")
                    if int(gr)<0 or typ not in ("Full day","Half day","Custom","Off"): raise ValueError()
                    rows.append((uid,wd,st,en,int(gr),typ))
            except ValueError:
                messagebox.showerror("Invalid schedule","Use HH:MM times, a non-negative grace period, and a valid shift type."); return
            with sqlite3.connect(DB) as c:
                c.executemany("""INSERT INTO staff_day_rules(user_id,weekday,start_time,end_time,grace_minutes,shift_type)
                    VALUES(?,?,?,?,?,?) ON CONFLICT(user_id,weekday) DO UPDATE SET start_time=excluded.start_time,
                    end_time=excluded.end_time,grace_minutes=excluded.grace_minutes,shift_type=excluded.shift_type""",rows)
            for uid0,wd,st,en,gr,typ in rows: existing[(uid0,wd)]=(st,en,gr,typ)
            messagebox.showinfo("Saved","Individual schedules saved.")
        ttk.Label(outer,text="School-wide planned holidays and sudden closures are managed separately in Custom Rules → Public holidays / closed dates.",style="Sub.TLabel").pack(anchor="w",pady=(0,5))
        footer=ttk.Frame(outer); footer.pack(fill="x")
        ttk.Label(footer,text="Default windows: Mon–Fri 9:00 AM–8:00 PM; Saturday 9:00 AM–5:00 PM.",style="Sub.TLabel").pack(side="left")
        ttk.Button(footer,text="Save employee schedule",style="Accent.TButton",command=save).pack(side="right")
        refresh_leave()

    def _attendance_day_status(self,uid,day,stamps):
        rules,overrides,holidays=self._rules()
        if day in holidays: return "Holiday", "", "", 0.0
        with sqlite3.connect(DB) as c:
            leave=c.execute("SELECT label FROM staff_leave WHERE user_id=? AND start_date<=? AND end_date>=? ORDER BY id LIMIT 1",
                            (str(uid),day,day)).fetchone()
        if leave: return f"On leave — {leave[0]}", "", "", 0.0
        try: workdays={int(x.strip()) for x in rules["workdays"].split(",") if x.strip()}
        except ValueError: workdays={0,1,2,3,4}
        d=datetime.strptime(day,"%Y-%m-%d").date()
        r=overrides.get(str(uid),{})
        with sqlite3.connect(DB) as c:
            day_rule=c.execute("SELECT start_time,end_time,grace_minutes,shift_type FROM staff_day_rules WHERE user_id=? AND weekday=?",(str(uid),d.weekday())).fetchone()
        # An explicit employee/day schedule takes precedence over the global workweek.
        if day_rule:
            start,end,grace,shift_type=day_rule[0],day_rule[1],int(day_rule[2]),day_rule[3]
            if shift_type=="Off": return "Day off", "", "", 0.0
        else:
            if d.weekday() not in workdays: return "Day off", "", "", 0.0
            start=r.get("start",rules["default_start"]); end=r.get("end",rules["default_end"])
            grace=int(r.get("grace",rules["default_grace"])); shift_type="Full day"
        half=r.get("half",rules["half_day_after"])
        min_hours=float(r.get("min_hours",rules["min_hours"]))
        stamps=sorted(stamps)
        if not stamps: return "Absent", "", "", 0.0
        first=datetime.strptime(stamps[0],"%Y-%m-%d %H:%M:%S")
        last=datetime.strptime(stamps[-1],"%Y-%m-%d %H:%M:%S")
        scheduled=datetime.strptime(day+" "+start,"%Y-%m-%d %H:%M")
        late=(first-scheduled).total_seconds()/60
        worked=max(0,(last-first).total_seconds()/3600)
        if len(stamps)<2:
            status="Incomplete punch"
            if late>grace: status+=" — Late"
            # A single punch cannot establish a worked duration or a valid
            # checkout time. Keep the day explicitly incomplete.
            return status,"","",0.0
        if shift_type=="Half day":
            status="Half-day"
        elif shift_type=="Custom":
            status="Present" if worked>=min_hours else "Half-day"
        elif first.strftime("%H:%M")>=half or worked<min_hours:
            status="Half-day"
        else:
            status="Present"
        if late>grace:
            status = "Late" if status=="Present" else status+" — Late"
        if end and last.strftime("%H:%M") < end:
            status += " (early departure)"
        return status,first.strftime("%H:%M"),last.strftime("%H:%M"),worked

    def _staff_names(self):
        if not hasattr(self,"_names_cache") or self._names_cache is None:
            with sqlite3.connect(DB) as c:
                self._names_cache={str(uid): str(name or "").strip() for uid,name in c.execute("SELECT user_id,name FROM staff")}
        return self._names_cache

    def _name(self, uid):
        name=self._staff_names().get(str(uid), "")
        return name if name else f"User {uid}"

    def _store_device_users(self, users):
        saved=0
        with sqlite3.connect(DB) as c:
            for user in users:
                uid=str(getattr(user,"user_id",None) or getattr(user,"uid","")).strip()
                name=str(getattr(user,"name","") or "").strip()
                if not uid or not name:
                    continue
                c.execute("""INSERT INTO staff(user_id,name) VALUES(?,?)
                             ON CONFLICT(user_id) DO UPDATE SET name=excluded.name""",(uid,name))
                saved+=1
        self._names_cache=None
        return saved

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

    def _daily_attendance_rows(self, rows):
        """Collapse raw device punches into one live attendance row per staff/day."""
        grouped={}
        for uid,stamp,state in rows:
            try:
                parsed=datetime.fromisoformat(str(stamp))
            except ValueError:
                continue
            grouped.setdefault((str(uid),parsed.date()),[]).append(parsed)
        with sqlite3.connect(DB) as c:
            general=dict(c.execute("SELECT setting,value FROM app_settings"))
            staff_rules={str(r[0]):(r[1],r[2],int(r[3])) for r in c.execute(
                "SELECT user_id,start_time,end_time,grace_minutes FROM staff_rules")}
            day_rules={(str(r[0]),int(r[1])):(r[2],r[3],int(r[4]),r[5]) for r in c.execute(
                "SELECT user_id,weekday,start_time,end_time,grace_minutes,shift_type FROM staff_day_rules")}
        now=datetime.now()
        output=[]
        for (uid,day),punches in grouped.items():
            punches.sort()
            first,last=punches[0],punches[-1]
            checked_out=len(punches)>1
            check_out=last.strftime("%H:%M:%S") if checked_out else "—"
            historical_incomplete=(not checked_out and day < now.date())
            if historical_incomplete:
                # Do not turn a forgotten checkout into hundreds of hours by
                # measuring from the old punch until the current date.
                first_display="—"
                active="—"
            else:
                first_display=first.strftime("%H:%M:%S")
                end_point=last if checked_out else now
                elapsed=max(0,int((end_point-first).total_seconds()//60))
                hours,minutes=divmod(elapsed,60)
                active=f"{hours} hours {minutes} minutes"
            weekday=day.weekday()
            start=general.get("default_start","09:45")
            end=general.get("default_end","20:00")
            grace=int(general.get("default_grace","15"))
            if uid in staff_rules:
                start,end,grace=staff_rules[uid]
            if (uid,weekday) in day_rules:
                start,end,grace,shift_type=day_rules[(uid,weekday)]
            try:
                scheduled_start=datetime.combine(day,datetime.strptime(start,"%H:%M").time())
                scheduled_end=datetime.combine(day,datetime.strptime(end,"%H:%M").time())
            except ValueError:
                scheduled_start=datetime.combine(day,datetime.strptime("09:45","%H:%M").time())
                scheduled_end=datetime.combine(day,datetime.strptime("20:00","%H:%M").time())
            late=first>scheduled_start+timedelta(minutes=grace)
            early=checked_out and last<scheduled_end
            labels=[]
            if historical_incomplete:
                labels.append("Incomplete punch")
            if late: labels.append("Late")
            if early: labels.append("Early departure")
            if not labels:
                if checked_out:
                    labels.append("Completed")
                else:
                    labels.append("In progress")
            status=" • ".join(labels)
            tag="early" if early else ("late" if late else ("open" if not checked_out else ""))
            output.append((uid,day.isoformat(),first_display,("—" if historical_incomplete else check_out),active,status,tag))
        # Assigned device IDs ascend numerically; dates descend within each ID.
        output.sort(key=lambda r:r[1],reverse=True)
        output.sort(key=lambda r:(0,int(r[0])) if r[0].isdigit() else (1,r[0].lower()))
        return output

    def refresh(self):
        rows=self._rows()
        if rows is None: return
        for i in self.tree.get_children(): self.tree.delete(i)
        daily=self._daily_attendance_rows(rows)
        punch_counts={}
        for uid0,stamp0,state0 in rows:
            key=(str(uid0),str(stamp0)[:10]); punch_counts[key]=punch_counts.get(key,0)+1
        mode=self.sort_by.get() if hasattr(self,"sort_by") else "Date (newest first)"
        names=self._staff_names()
        def sort_key(r):
            uid0,day0,ci,co,active0,status0,tag0=r
            name0=names.get(str(uid0),"").lower()
            count0=punch_counts.get((str(uid0),day0),0)
            try: mins0=int(active0.split(" hours ")[0])*60+int(active0.split(" hours ")[1].split(" minutes")[0])
            except Exception: mins0=0
            if mode.startswith("Date"): return (day0,uid0)
            if mode.startswith("Employee ("): return (name0,day0)
            if mode.startswith("Punch time"): return (ci,day0,uid0)
            if mode.startswith("Punch count"): return (count0,day0,uid0)
            if mode.startswith("Active hours"): return (mins0,day0,uid0)
            if mode.startswith("Attendance status"): return (status0.lower(),day0,uid0)
            if mode=="Employee ID (ascending)" or mode=="Employee ID (descending)":
                return ((0,int(uid0)) if str(uid0).isdigit() else (1,str(uid0).lower()),day0)
            return (day0,uid0)
        reverse=mode in ("Date (newest first)","Employee (Z–A)","Punch time (latest first)","Punch count (highest first)","Active hours (highest first)","Employee ID (descending)")
        daily.sort(key=sort_key,reverse=reverse)
        for idx,row in enumerate(daily):
            uid,day,checkin,checkout,active,status,tag=row
            tags=["odd" if idx%2 else "even"]
            if tag: tags.append(tag)
            self.tree.insert("","end",values=(uid,self._name(uid),day,checkin,checkout,active,status),tags=tuple(tags))
        with sqlite3.connect(DB) as c:
            registered={str(r[0]) for r in c.execute("SELECT user_id FROM staff")}
        users=sorted(registered | set(str(r[0]) for r in rows),key=lambda x:(not x.isdigit(),int(x) if x.isdigit() else x.lower()))
        choices=["All staff"]+[f"{self._name(uid)} ({uid})" for uid in users]
        self.user_combo["values"]=choices
        if self.report_user.get() not in choices: self.report_user.set("All staff")
        days=len(set(r[1][:10] for r in rows))
        staff=len(users)
        avg=(len(rows)/days) if days else 0
        for label,value in zip(self.card_values,[f"{len(rows):,}",f"{staff:,}",f"{days:,}",f"{avg:.1f}"]): label.configure(text=value)
        self._draw_charts(rows)
        if hasattr(self,"dashboard_employee_combo"):
            selected=self.dashboard_employee.get()
            dashboard_choices=["All staff"]+[f"{self._name(uid)} ({uid})" for uid in users]
            self.dashboard_employee_combo["values"]=dashboard_choices
            if selected not in dashboard_choices: self.dashboard_employee.set("All staff")
        self._update_dashboard(rows)
        self.status.set(f"{len(daily):,} staff/day records • {len(rows):,} punches • sorted by {mode}")

    def _update_dashboard(self, rows):
        if rows is None or not hasattr(self,"comparison_tree"):
            return
        for item in self.comparison_tree.get_children():
            self.comparison_tree.delete(item)
        selected=self.dashboard_employee.get() if hasattr(self,"dashboard_employee") else "All staff"
        selected_uid=None if selected=="All staff" else selected.rsplit(" (",1)[-1].rstrip(")")
        latest=max(rows,key=lambda r:str(r[1])) if rows else None
        if latest:
            uid,stamp,state=latest
            self.latest_punch_label.configure(text=f"LATEST PUNCH  •  {self._name(uid)}  (ID {uid})  •  {datetime.strptime(stamp,'%Y-%m-%d %H:%M:%S').strftime('%d %b %Y, %I:%M:%S %p')}")
        else:
            self.latest_punch_label.configure(text="LATEST PUNCH  •  No punch records in this date range")
        grouped={}
        for uid,stamp,state in rows:
            grouped.setdefault((str(uid),str(stamp)[:10]),[]).append(str(stamp))
        first=datetime.strptime(self.start_date.get(),"%Y-%m-%d").date()
        last=datetime.strptime(self.end_date.get(),"%Y-%m-%d").date()
        with sqlite3.connect(DB) as c:
            registered={str(r[0]) for r in c.execute("SELECT user_id FROM staff")}
        staff_ids=sorted(registered|{uid for uid,day in grouped},
            key=lambda x:(not x.isdigit(),int(x) if x.isdigit() else x.lower()))
        if selected_uid:
            staff_ids=[uid for uid in staff_ids if uid==selected_uid]
        totals={"expected":0,"present":0,"late":0,"early":0,"absent":0,"incomplete":0,"ontime":0}
        averages=[]
        for uid in staff_ids:
            stats={"expected":0,"present":0,"late":0,"early":0,"absent":0,"incomplete":0,"ontime":0}
            arrivals=[]
            cursor=first
            while cursor<=last:
                day=cursor.isoformat()
                stamps=sorted(grouped.get((uid,day),[]))
                status,first_p,last_p,worked=self._attendance_day_status(uid,day,stamps)
                if status not in ("Day off","Holiday") and not status.startswith("On leave"):
                    stats["expected"]+=1
                if status=="Absent":
                    stats["absent"]+=1
                elif status.startswith("Incomplete punch"):
                    stats["incomplete"]+=1
                    stats["present"]+=1
                    if "Late" in status: stats["late"]+=1
                elif stamps:
                    stats["present"]+=1
                    if "Late" in status: stats["late"]+=1
                    else: stats["ontime"]+=1
                    if "early departure" in status: stats["early"]+=1
                    try: arrivals.append(datetime.strptime(stamps[0],"%Y-%m-%d %H:%M:%S").hour*60+datetime.strptime(stamps[0],"%Y-%m-%d %H:%M:%S").minute)
                    except ValueError: pass
                cursor+=timedelta(days=1)
            rate=(stats["ontime"]/stats["expected"]*100) if stats["expected"] else 0
            avg=""
            if arrivals:
                mean=round(sum(arrivals)/len(arrivals))
                avg=f"{mean//60:02d}:{mean%60:02d}"
                averages.extend(arrivals)
            values=(self._name(uid),stats["expected"],stats["present"],stats["late"],stats["early"],
                    stats["absent"],stats["ontime"],f"{rate:.1f}%",avg or "—")
            tag="good" if rate>=90 and stats["late"]==0 and stats["early"]==0 else "attention"
            self.comparison_tree.insert("","end",values=values,tags=(tag,))
            for key in totals: totals[key]+=stats[key]
        rate=(totals["ontime"]/totals["expected"]*100) if totals["expected"] else 0
        avg_text="—"
        if averages:
            mean=round(sum(averages)/len(averages)); avg_text=f"{mean//60:02d}:{mean%60:02d}"
        values=[f"{rate:.1f}%",f"{totals['late']:,}",f"{totals['early']:,}",
                f"{totals['absent']:,}",f"{totals['incomplete']:,}",avg_text]
        for label,value in zip(self.card_values,values):
            label.configure(text=value)

    def _live_refresh(self):
        try:
            if self.winfo_exists():
                self.refresh()
                self.after(30000,self._live_refresh)
        except tk.TclError:
            pass

    def _draw_charts(self,rows):
        daily={}
        staff={}
        for uid,stamp,state in rows:
            daily[stamp[:10]]=daily.get(stamp[:10],0)+1
            staff[str(uid)]=staff.get(str(uid),0)+1
        self._bar_chart(self.daily_canvas,sorted(daily.items())[-14:], "#2f6b45", date_labels=True)
        named_staff={}
        for uid,count in staff.items():
            label=self._name(uid)
            named_staff[label]=named_staff.get(label,0)+count
        self._bar_chart(self.staff_canvas,sorted(named_staff.items(),key=lambda x:x[1],reverse=True)[:10], "#477c57", date_labels=False)

    def _bar_chart(self,canvas,items,color,date_labels=False):
        canvas.delete("all")
        w=max(canvas.winfo_width(),360); h=max(canvas.winfo_height(),260)
        if not items:
            canvas.create_text(w/2,h/2,text="No records in this date range",fill=MUTED,font=("Segoe UI",11))
            return
        maxv=max(v for _,v in items) or 1
        if not date_labels:
            # Horizontal bars give each staff member a dedicated label row.
            # This prevents long employee names from colliding on the x-axis.
            left,right,top,bottom=118,34,18,22
            cw=max(80,w-left-right); ch=max(80,h-top-bottom)
            row_h=ch/max(1,len(items)); bar_h=min(20,row_h*.56)
            for n in range(4):
                x=left+cw*n/3
                canvas.create_line(x,top,x,top+ch,fill="#e2e8f0")
                canvas.create_text(x,top-7,text=str(round(maxv*n/3)),anchor="s",
                                   fill=MUTED,font=("Segoe UI",8))
            for i,(label,val) in enumerate(items):
                cy=top+row_h*(i+.5)
                shown=label if len(label)<=17 else label[:16]+"…"
                canvas.create_text(left-10,cy,text=shown,anchor="e",
                                   fill=MUTED,font=("Segoe UI",8))
                bw=cw*val/maxv
                canvas.create_rectangle(left,cy-bar_h/2,left+bw,cy+bar_h/2,
                                        fill=color,outline="")
                canvas.create_text(min(left+bw+7,w-right),cy,text=str(val),
                                   anchor="w",fill=NAVY,font=("Segoe UI",8,"bold"))
            return
        left,right,top,bottom=42,16,18,48
        cw=w-left-right; ch=h-top-bottom
        for n in range(4):
            y=top+ch-(ch*n/3)
            canvas.create_line(left,y,w-right,y,fill="#e2e8f0")
            canvas.create_text(left-8,y,text=str(round(maxv*n/3)),anchor="e",
                               fill=MUTED,font=("Segoe UI",8))
        gap=cw/len(items); bw=max(8,min(34,gap*.58))
        for i,(label,val) in enumerate(items):
            x=left+gap*i+(gap-bw)/2
            bh=ch*val/maxv
            canvas.create_rectangle(x,top+ch-bh,x+bw,top+ch,fill=color,outline="")
            short=label[5:] if len(label)>5 else label
            canvas.create_text(x+bw/2,top+ch+9,text=short,anchor="n",
                               fill=MUTED,font=("Segoe UI",8))
            canvas.create_text(x+bw/2,top+ch-bh-9,text=str(val),
                               fill=NAVY,font=("Segoe UI",8,"bold"))

    def discover_device(self):
        """Find ZKTeco-compatible attendance devices on the local IPv4 /24 subnet and verify their protocol handshake."""
        try:
            port=int(self.port.get()); key=int(self.key.get() or "0")
            if not 1<=port<=65535: raise ValueError()
        except ValueError:
            messagebox.showerror("Invalid settings","Port must be between 1 and 65535 and communication key must be numeric.")
            return
        current=self.ip.get().strip()
        try:
            with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as route:
                route.connect(("192.0.2.1",80))
                local_ip=route.getsockname()[0]
            if not local_ip or local_ip.startswith("127."): raise OSError()
        except OSError:
            try: local_ip=str(ipaddress.ip_address(current))
            except ValueError:
                messagebox.showerror("Network unavailable","Could not determine this computer's local network. Enter the device IP manually and try again.")
                return
        network=ipaddress.ip_network(f"{local_ip}/24",strict=False)
        self.status.set(f"Searching {network} for compatible attendance devices on port {port}…")
        threading.Thread(target=self._discover_worker,args=(network,port,key),daemon=True).start()

    def _discover_worker(self,network,port,key):
        candidates=[]
        def port_open(address):
            try:
                with socket.create_connection((str(address),port),timeout=0.25): return str(address)
            except OSError: return None
        try:
            from concurrent.futures import ThreadPoolExecutor, as_completed
            with ThreadPoolExecutor(max_workers=48) as pool:
                futures=[pool.submit(port_open,address) for address in network.hosts()]
                for future in as_completed(futures):
                    found=future.result()
                    if found: candidates.append(found)
            from zk import ZK
            for address in sorted(candidates,key=lambda x:(x.rsplit(".",1)[0],int(x.rsplit(".",1)[1]))):
                conn=None
                try:
                    conn=ZK(address,port=port,timeout=4,password=key,force_udp=False,ommit_ping=False).connect()
                    conn.disconnect(); conn=None
                    self.after(0,lambda ip=address:self._discovery_done(ip,len(candidates)))
                    return
                except Exception:
                    if conn:
                        try: conn.disconnect()
                        except Exception: pass
            self.after(0,lambda n=len(candidates):self._discovery_failed(n))
        except Exception as e:
            msg=str(e); self.after(0,lambda m=msg:self._discovery_error(m))

    def _discovery_done(self,address,open_ports):
        self.ip.set(address)
        self.status.set(f"Compatible device found at {address} • {open_ports} responsive device port(s) checked")
        messagebox.showinfo("Compatible device found",f"A ZKTeco-compatible attendance device responded at {address}.\n\nThe IP has been filled in. Click Fetch Attendance to synchronise attendance.")

    def _discovery_failed(self,open_ports):
        self.status.set("No compatible attendance device found on the local network.")
        detail=f"\n\n{open_ports} device(s) had the selected port open but did not complete the ZKTeco protocol handshake." if open_ports else ""
        messagebox.showwarning("No compatible device found","No ZKTeco-compatible attendance device was detected on this computer's local /24 network."+detail+"\n\nCheck that the computer and device are on the same LAN/VLAN, or enter the IP manually.")

    def _discovery_error(self,msg):
        self.status.set("Automatic discovery failed.")
        messagebox.showerror("Discovery failed",msg)

    def fetch(self):
        ip=self.ip.get().strip()
        try:
            parsed_ip=ipaddress.ip_address(ip)
            if parsed_ip.version != 4: raise ValueError()
        except ValueError:
            messagebox.showerror("Invalid device IP","Enter a valid IPv4 address, for example 192.168.1.201.")
            return
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
            device_users=conn.get_users()
            saved_users=self._store_device_users(device_users)
            rows=conn.get_attendance()
            inserted=0
            with sqlite3.connect(DB) as c:
                for row in rows:
                    stamp=row.timestamp.strftime("%Y-%m-%d %H:%M:%S")
                    cur=c.execute("INSERT OR IGNORE INTO punches(user_id,punch_time,status) VALUES(?,?,?)",(str(row.user_id),stamp,str(getattr(row,"status",""))))
                    inserted+=cur.rowcount
            self.after(0,lambda:self._fetch_done(len(rows),inserted,saved_users))
        except Exception as e:
            msg=str(e); self.after(0,lambda m=msg:self._fetch_error(m))
        finally:
            if conn:
                try: conn.enable_device()
                except Exception: pass
                try: conn.disconnect()
                except Exception: pass

    def _fetch_done(self,total,inserted,saved_users=0):
        self.refresh()
        self.status.set(f"Sync complete • {saved_users} staff names synced • {total} punches read • {inserted} new")
        messagebox.showinfo("Sync complete",f"Staff names fetched: {saved_users}\nAttendance records read: {total}\nNew attendance records saved: {inserted}")

    def _fetch_error(self,msg):
        self.status.set("Device connection failed.")
        messagebox.showerror("Could not fetch attendance",f"{msg}\n\nCheck the device IP, LAN connection, port, and communication key.")

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

    def backup_database(self):
        """Export a consistent SQLite backup without copying a live database file."""
        path=filedialog.asksaveasfilename(
            title="Back up SCAFA Workforce database",
            defaultextension=".db",
            filetypes=[("SQLite database","*.db"),("All files","*.*")],
            initialfile=f"SCAFA_Workforce_Backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db")
        if not path:
            return
        try:
            with sqlite3.connect(DB) as source, sqlite3.connect(path) as target:
                source.backup(target)
            messagebox.showinfo("Backup complete",f"Database backup saved to:\n{path}")
            self.status.set(f"Database backup saved • {path}")
        except Exception as e:
            messagebox.showerror("Backup failed",f"Could not back up the database:\n{e}")

    def restore_database(self):
        """Validate a backup, preserve the current database, then restore safely."""
        path=filedialog.askopenfilename(
            title="Select SCAFA Workforce database backup",
            filetypes=[("SQLite database","*.db *.sqlite *.sqlite3"),("All files","*.*")])
        if not path:
            return
        try:
            if Path(path).resolve()==DB.resolve():
                messagebox.showerror("Invalid backup","Choose a backup file, not the database currently in use.")
                return
            with sqlite3.connect(f"file:{Path(path).resolve().as_posix()}?mode=ro",uri=True) as check:
                integrity=check.execute("PRAGMA integrity_check").fetchone()
                tables={r[0] for r in check.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if not integrity or integrity[0]!="ok":
                    raise ValueError("The selected file failed SQLite's integrity check.")
                if not {"punches","staff"}.issubset(tables):
                    raise ValueError("This file does not look like a SCAFA Workforce attendance database.")
            if not messagebox.askyesno(
                "Confirm database restore",
                "Restoring replaces the current attendance data and settings. "
                "A safety backup of the current database will be created first. Continue?"):
                return
            safety=BASE / f"Pre_Restore_Backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
            with sqlite3.connect(DB) as current, sqlite3.connect(safety) as backup:
                current.backup(backup)
            with sqlite3.connect(f"file:{Path(path).resolve().as_posix()}?mode=ro",uri=True) as source, sqlite3.connect(DB) as target:
                source.backup(target)
            self._names_cache=None
            init_db()
            self.refresh()
            messagebox.showinfo("Restore complete",f"Database restored successfully.\nSafety backup: {safety}")
            self.status.set("Database restored • current database safety backup retained")
        except Exception as e:
            messagebox.showerror("Restore failed",f"Could not restore this database:\n{e}")

    def export_csv(self):
        rows=self._rows()
        if rows is None: return
        path=filedialog.asksaveasfilename(title="Save punch report",defaultextension=".csv",filetypes=[("CSV report","*.csv")],initialfile=f"SCAFA_Workforce_Punches_{date.today().isoformat()}.csv")
        if not path: return
        with open(path,"w",newline="",encoding="utf-8-sig") as f:
            w=csv.writer(f); w.writerow(["Device User ID","Staff Name","Attendance date & time","Punch status"])
            w.writerows((uid,self._name(uid),stamp,state) for uid,stamp,state in rows)
        messagebox.showinfo("CSV exported",f"Exported {len(rows)} records.")

    def _report_scope_rows(self):
        rows=self._rows()
        if rows is None: return None,None
        label=self.report_user.get()
        scope="All staff" if label=="All staff" else label.rsplit(" (",1)[-1].rstrip(")")
        if scope!="All staff": rows=[r for r in rows if str(r[0])==scope]
        with sqlite3.connect(DB) as c:
            registered={str(r[0]) for r in c.execute("SELECT user_id FROM staff")}
        if scope=="All staff" and not (rows or registered):
            messagebox.showwarning("No staff","No attendance punches or registered staff were found. Fetch staff from the connected device first."); return None,None
        if scope!="All staff" and scope not in (registered | {str(r[0]) for r in rows}):
            messagebox.showwarning("Unknown staff","This staff ID is not registered and has no punches in the selected period."); return None,None
        return rows,scope

    def export_excel(self):
        rows,scope=self._report_scope_rows()
        if rows is None: return
        suffix="All_Staff" if scope=="All staff" else f"Staff_{scope}"
        path=filedialog.asksaveasfilename(title="Export editable Excel attendance report",defaultextension=".xlsx",
            filetypes=[("Excel workbook","*.xlsx")],initialfile=f"SCAFA_Workforce_Attendance_{suffix}_{date.today().isoformat()}.xlsx")
        if not path: return
        try:
            from openpyxl import Workbook
            from openpyxl.styles import Font, PatternFill, Alignment
            from openpyxl.utils import get_column_letter
            from openpyxl.worksheet.table import Table as ExcelTable, TableStyleInfo
            wb=Workbook()
            overview=wb.active; overview.title="Overview"
            summary=wb.create_sheet("Attendance Summary")
            raw=wb.create_sheet("Raw Punches")
            performance=wb.create_sheet("Employee Comparison")
            performance.append(["Employee","Device User ID","Expected Days","Present Days","Late Arrivals","Early Departures","Absences","Incomplete Punches","On-time Days","On-time Rate","Average Arrival"])
            summary.append(["SCAFA WORKFORCE | ATTENDANCE REPORT"])
            summary.merge_cells("A1:H1")
            summary["A1"].font=Font(name="Aptos Display",size=18,bold=True,color="FFFFFF")
            summary["A1"].fill=PatternFill("solid",fgColor="173D2B")
            summary["A1"].alignment=Alignment(vertical="center")
            summary.row_dimensions[1].height=34
            summary.append(["Report scope",scope,"From",self.start_date.get(),"To",self.end_date.get(),"Generated",datetime.now().strftime("%d %b %Y %H:%M")])
            summary.append([])
            summary.append(["Device User ID","Staff Name","Date / Day","Punches","First Punch","Last Punch","Worked Time","Attendance Status"])
            raw.append(["Device User ID","Staff Name","Attendance Date & Time","Punch Status"])
            for uid,stamp,state in rows: raw.append([str(uid),self._name(uid),stamp,state or ""])
            by_user_day={}
            for uid,stamp,state in rows: by_user_day.setdefault((str(uid),stamp[:10]),[]).append(stamp)
            with sqlite3.connect(DB) as c:
                known=sorted({str(r[0]) for r in c.execute("SELECT user_id FROM staff")} | {str(r[0]) for r in rows},
                    key=lambda x:(not x.isdigit(),int(x) if x.isdigit() else x.lower()))
            first=datetime.strptime(self.start_date.get(),"%Y-%m-%d").date()
            last=datetime.strptime(self.end_date.get(),"%Y-%m-%d").date()
            if last<first: raise ValueError("End date must not precede start date.")
            users=known if scope=="All staff" else [str(scope)]
            status_values=[]
            employee_performance=[]
            punch_totals={uid:0 for uid in users}
            active_days={uid:0 for uid in users}
            for uid in users:
                perf={"expected":0,"present":0,"late":0,"early":0,"absent":0,"incomplete":0,"ontime":0,"arrivals":[]}
                cursor=first
                while cursor<=last:
                    day=cursor.isoformat(); stamps=sorted(by_user_day.get((uid,day),[]))
                    status,first_p,last_p,hours=self._attendance_day_status(uid,day,stamps)
                    weekday=datetime.strptime(day,"%Y-%m-%d").strftime("%A")
                    worked_display="—" if status.startswith("Incomplete punch") else format_worked_time(hours)
                    summary.append([uid,self._name(uid),f"{day} ({weekday})",len(stamps),first_p or "—",last_p or "—",worked_display,status])
                    status_values.append(status)
                    if status not in ("Day off","Holiday") and not status.startswith("On leave"): perf["expected"]+=1
                    if status=="Absent": perf["absent"]+=1
                    elif status.startswith("Incomplete punch"):
                        perf["incomplete"]+=1; perf["present"]+=1
                        if "Late" in status: perf["late"]+=1
                    elif stamps:
                        perf["present"]+=1
                        if "Late" in status: perf["late"]+=1
                        else: perf["ontime"]+=1
                        if "early departure" in status: perf["early"]+=1
                        try:
                            arrival=datetime.strptime(stamps[0],"%Y-%m-%d %H:%M:%S")
                            perf["arrivals"].append(arrival.hour*60+arrival.minute)
                        except ValueError: pass
                    punch_totals[uid]+=len(stamps)
                    if stamps: active_days[uid]+=1
                    cursor+=timedelta(days=1)
                rate=(perf["ontime"]/perf["expected"]) if perf["expected"] else 0
                avg_minutes=round(sum(perf["arrivals"])/len(perf["arrivals"])) if perf["arrivals"] else None
                avg_arrival=f"{avg_minutes//60:02d}:{avg_minutes%60:02d}" if avg_minutes is not None else "—"
                performance.append([self._name(uid),uid,perf["expected"],perf["present"],perf["late"],
                    perf["early"],perf["absent"],perf["incomplete"],perf["ontime"],rate,avg_arrival])
                employee_performance.append((uid,perf))
            overview.merge_cells("A1:F1")
            overview["A1"]="SCAFA WORKFORCE | ATTENDANCE OVERVIEW"
            overview["A1"].font=Font(name="Aptos Display",size=18,bold=True,color="FFFFFF")
            overview["A1"].fill=PatternFill("solid",fgColor="173D2B")
            overview["A1"].alignment=Alignment(vertical="center")
            overview.row_dimensions[1].height=36
            overview.append([])
            overview.append(["Report scope",scope,"From",self.start_date.get(),"To",self.end_date.get()])
            overview.append(["Generated",datetime.now().strftime("%d %b %Y %H:%M")])
            overview.append([])
            overview.append(["KEY METRICS","Value",None,None,"ATTENDANCE STATUS","Days"])
            endrow=summary.max_row
            # Store calculated values rather than formulas so the dashboard is populated
            # immediately in Excel, LibreOffice, and macOS preview applications.
            overview.append(["Total punches",sum(punch_totals.values())])
            overview.append(["Staff included",len(users)])
            overview.append(["Active attendance days",sum(active_days.values())])
            overview.append(["Present / late days",sum(1 for s in status_values if "present" in s.casefold() or "late" in s.casefold())])
            overview.append(["Late arrivals",sum(p["late"] for _,p in employee_performance)])
            overview.append(["Early departures",sum(p["early"] for _,p in employee_performance)])
            overview.append(["Absences",sum(p["absent"] for _,p in employee_performance)])
            overview.append(["Incomplete punches",sum(p["incomplete"] for _,p in employee_performance)])
            latest_record=max(rows,key=lambda r:str(r[1])) if rows else None
            latest_text=(f"{self._name(latest_record[0])} • {latest_record[1]}" if latest_record else "No punches")
            overview.append(["Latest punch",latest_text])
            status_start=7
            status_counts={
                "Present":sum(1 for s in status_values if s.casefold().startswith("present")),
                "Late":sum(1 for s in status_values if "late" in s.casefold()),
                "Half Day":sum(1 for s in status_values if s.casefold().startswith(("half-day","half day"))),
                "Absent":sum(1 for s in status_values if s.casefold()=="absent"),
                "Day off":sum(1 for s in status_values if s.casefold()=="day off"),
                "Holiday":sum(1 for s in status_values if s.casefold()=="holiday"),
                "On leave":sum(1 for s in status_values if s.casefold().startswith("on leave")),
                "Incomplete punch":sum(1 for s in status_values if s.casefold().startswith("incomplete punch"))
            }
            for offset,(status_name,count) in enumerate(status_counts.items()):
                rr=status_start+offset
                overview.cell(rr,5,status_name)
                overview.cell(rr,6,count)
            staff_start=17
            overview.cell(staff_start,1,"STAFF PUNCH TOTALS")
            for j,h in enumerate(["Device User ID","Staff Name","Punches","Active Days"],1):
                overview.cell(staff_start+1,j,h)
            for idx,uid in enumerate(users,staff_start+2):
                overview.cell(idx,1,uid)
                overview.cell(idx,2,self._name(uid))
                overview.cell(idx,3,punch_totals[uid])
                overview.cell(idx,4,active_days[uid])
            note_row=staff_start+2+len(users)
            overview.merge_cells(start_row=note_row,start_column=1,end_row=note_row,end_column=6)
            overview.cell(note_row,1,"Note: Status indicators can overlap for combined statuses (for example, Half-day — Late or Incomplete punch — Late).")
            overview.cell(note_row,1).font=Font(italic=True,color="64748B",size=9)
            overview.cell(note_row,1).alignment=Alignment(wrap_text=True,vertical="center")
            overview.row_dimensions[note_row].height=28
            overview.sheet_view.showGridLines=False
            for col,width in {"A":24,"B":25,"C":16,"D":16,"E":23,"F":14}.items():
                overview.column_dimensions[col].width=width
            for row in overview.iter_rows():
                for cell in row: cell.alignment=Alignment(vertical="center",horizontal="left")
            for rowno in (6,18):
                for cell in overview[rowno]:
                    cell.font=Font(bold=True,color="FFFFFF")
                    cell.fill=PatternFill("solid",fgColor="24563B")
                    cell.alignment=Alignment(horizontal="center",vertical="center")
            overview.freeze_panes="A7"
            overview.sheet_properties.pageSetUpPr.fitToPage=True
            overview.page_setup.orientation="portrait"
            overview.page_setup.paperSize=overview.PAPERSIZE_A4
            overview.page_setup.fitToWidth=1
            overview.page_setup.fitToHeight=1
            for ws,widths,header_row in [(summary,[16,28,25,11,21,21,24,28],4),(raw,[18,30,24,20],1),(performance,[28,16,15,14,15,17,12,18,14,14,18],1)]:
                ws.freeze_panes="A5" if ws is summary else "A2"
                ws.sheet_view.showGridLines=False
                for i,width in enumerate(widths,1): ws.column_dimensions[get_column_letter(i)].width=width
                for cell in ws[header_row]:
                    cell.font=Font(bold=True,color="FFFFFF")
                    cell.fill=PatternFill("solid",fgColor="24563B")
                    cell.alignment=Alignment(horizontal="center",vertical="center",wrap_text=True)
                ws.row_dimensions[header_row].height=30
                ws.auto_filter.ref=ws.dimensions
                for row in ws.iter_rows():
                    for cell in row:
                        cell.alignment=Alignment(vertical="center",horizontal="left",
                                                  wrap_text=(cell.row==header_row))
                for rr in range(header_row+1,ws.max_row+1):
                    ws.row_dimensions[rr].height=21
                if ws is summary:
                    pass
                else:
                    for rr in range(2,ws.max_row+1):
                        ws.cell(rr,3).number_format="yyyy-mm-dd hh:mm:ss"
            if performance.max_row>=2:
                perf_table=ExcelTable(displayName="EmployeeComparison",ref=f"A1:K{performance.max_row}")
                perf_table.tableStyleInfo=TableStyleInfo(name="TableStyleMedium4",showRowStripes=True,showColumnStripes=False)
                performance.add_table(perf_table)
                for rr in range(2,performance.max_row+1): performance.cell(rr,10).number_format="0.0%"
                from openpyxl.chart import BarChart, Reference
                chart=BarChart(); chart.type="bar"; chart.style=10; chart.title="Late arrivals and early departures"
                chart.y_axis.title="Employee"; chart.x_axis.title="Days"
                chart.add_data(Reference(performance,min_col=5,max_col=6,min_row=1,max_row=performance.max_row),titles_from_data=True)
                chart.set_categories(Reference(performance,min_col=1,min_row=2,max_row=performance.max_row))
                chart.height=8; chart.width=18
                performance.add_chart(chart,"M2")
                performance.freeze_panes="A2"; performance.sheet_view.showGridLines=False
            if summary.max_row>=5:
                tab=ExcelTable(displayName="AttendanceDetails",ref=f"A4:H{summary.max_row}")
                tab.tableStyleInfo=TableStyleInfo(name="TableStyleMedium4",showRowStripes=True,showColumnStripes=False)
                summary.add_table(tab)
            if raw.max_row>=2:
                tab=ExcelTable(displayName="RawPunchRecords",ref=f"A1:D{raw.max_row}")
                tab.tableStyleInfo=TableStyleInfo(name="TableStyleMedium4",showRowStripes=True,showColumnStripes=False)
                raw.add_table(tab)
            from openpyxl.formatting.rule import FormulaRule
            for prefix,fill in [("Present","E2F0E7"),("Late","FFF2CC"),("Half-day","FCE4D6"),
                                ("Absent","F4CCCC"),("Day off","E7E6E6"),("Holiday","DDEBF7"),
                                ("On leave","D9EAD3"),("Incomplete punch","FCE4D6")]:
                summary.conditional_formatting.add(f"H5:H{summary.max_row}",
                    FormulaRule(formula=[f'LEFT($H5,{len(prefix)})="{prefix}"'],fill=PatternFill("solid",fgColor=fill)))
            summary.sheet_properties.pageSetUpPr.fitToPage=True
            summary.page_setup.orientation="landscape"; summary.page_setup.paperSize=summary.PAPERSIZE_A4
            summary.page_setup.fitToWidth=1; summary.page_setup.fitToHeight=0
            raw.sheet_properties.pageSetUpPr.fitToPage=True
            raw.page_setup.orientation="landscape"; raw.page_setup.paperSize=raw.PAPERSIZE_A4
            raw.page_setup.fitToWidth=1; raw.page_setup.fitToHeight=0
            wb.active=0
            wb.save(path)
            messagebox.showinfo("Excel exported",f"Editable Excel workbook saved to:\n{path}\n\nIncludes daily attendance summary and raw punch records.")
        except Exception as e:
            messagebox.showerror("Excel export failed",f"{e}\n\nPlease reinstall/update the app build.")

    def export_pdf(self):
        rows,scope=self._report_scope_rows()
        if rows is None: return
        suffix="All_Staff" if scope=="All staff" else "Staff_"+scope
        path=filedialog.asksaveasfilename(title="Save PDF attendance report",defaultextension=".pdf",filetypes=[("PDF report","*.pdf")],initialfile=f"SCAFA_Workforce_Attendance_{suffix}_{date.today().isoformat()}.pdf")
        if not path: return
        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.enums import TA_LEFT
            from reportlab.lib.units import mm
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
            from reportlab.graphics.shapes import Drawing
            from reportlab.graphics.charts.barcharts import VerticalBarChart
            self._make_pdf(path,rows,scope,colors,A4,getSampleStyleSheet,ParagraphStyle,TA_LEFT,mm,SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,PageBreak,Drawing,VerticalBarChart)
            messagebox.showinfo("PDF report created",f"Saved report to:\n{path}")
        except Exception as e:
            messagebox.showerror("PDF export failed",f"{e}\n\nIf this persists, reinstall/update the app build.")

    def _make_pdf(self,path,rows,scope,colors,A4,getStyles,ParagraphStyle,TA_LEFT,mm,Doc,Paragraph,Spacer,Table,TableStyle,PageBreak,Drawing,VerticalBarChart):
        styles=getStyles()
        styles.add(ParagraphStyle(name="ReportTitle",parent=styles["Title"],textColor=colors.HexColor("#173D2B"),fontName="Helvetica-Bold",fontSize=18,leading=22,alignment=TA_LEFT,spaceAfter=4))
        styles.add(ParagraphStyle(name="EmployeeTitle",parent=styles["Title"],textColor=colors.HexColor("#173D2B"),fontName="Helvetica-Bold",fontSize=16,leading=20,alignment=TA_LEFT,spaceAfter=4,wordWrap="CJK"))
        styles.add(ParagraphStyle(name="SmallNote",parent=styles["BodyText"],fontSize=7,textColor=colors.HexColor("#64748b"),leading=9))
        styles.add(ParagraphStyle(name="Cell",parent=styles["BodyText"],fontSize=6.2,leading=6.8,wordWrap="CJK"))
        styles.add(ParagraphStyle(name="CellHead",parent=styles["BodyText"],fontName="Helvetica-Bold",fontSize=6.0,leading=6.5,textColor=colors.white,wordWrap="CJK"))
        styles.add(ParagraphStyle(name="Metric",parent=styles["BodyText"],fontSize=8,leading=11,textColor=colors.HexColor("#173D2B")))
        start_date=self.start_date.get(); end_date=self.end_date.get()
        by_user_day={}; all_by_day={}
        for uid,stamp,state in rows:
            uid=str(uid); day=stamp[:10]
            by_user_day.setdefault((uid,day),[]).append(stamp)
            all_by_day[day]=all_by_day.get(day,0)+1
        first_day=datetime.strptime(start_date,"%Y-%m-%d").date()
        last_day=datetime.strptime(end_date,"%Y-%m-%d").date()
        if last_day<first_day: raise ValueError("End date must not precede start date.")
        report_dates=[]; cursor=first_day
        while cursor<=last_day:
            report_dates.append(cursor.isoformat()); cursor+=timedelta(days=1)
        with sqlite3.connect(DB) as c: known_ids={str(r[0]) for r in c.execute("SELECT user_id FROM staff")}
        punch_ids={uid for uid,_ in by_user_day}
        staff_ids=sorted(known_ids|punch_ids,key=lambda x:(not x.isdigit(),int(x) if x.isdigit() else x.lower()))
        is_collective=(scope=="All staff"); pagesize=A4; story=[]

        def make_stats(items):
            cells=[]
            for label,value in items:
                cells.append(Paragraph(f"<b>{escape(str(label))}</b><br/>{escape(str(value))}",styles["Metric"]))
            while len(cells)%2: cells.append(Paragraph("",styles["Metric"]))
            data=[cells[i:i+2] for i in range(0,len(cells),2)]
            tab=Table(data,colWidths=[89*mm,89*mm],hAlign="LEFT")
            tab.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),colors.HexColor("#EDF4EF")),("BOX",(0,0),(-1,-1),.6,colors.HexColor("#C9D8CD")),("INNERGRID",(0,0),(-1,-1),.4,colors.HexColor("#D7E2DA")),("LEFTPADDING",(0,0),(-1,-1),8),("RIGHTPADDING",(0,0),(-1,-1),8),("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),4),("VALIGN",(0,0),(-1,-1),"MIDDLE")]))
            return tab

        def make_chart(day_counts):
            ordered=sorted(day_counts.items())[-24:]
            chart=Drawing(180*mm,24*mm)
            bc=VerticalBarChart(); bc.x=18; bc.y=8; bc.height=16*mm; bc.width=158*mm
            if ordered:
                bc.data=[tuple(v for _,v in ordered)]
                bc.categoryAxis.categoryNames=[d[5:] for d,_ in ordered]
                maxv=max(v for _,v in ordered) or 1
                bc.valueAxis.valueMin=0; bc.valueAxis.valueMax=maxv*1.15; bc.valueAxis.valueStep=max(1,int(maxv/4))
                bc.bars[0].fillColor=colors.HexColor("#477C57")
            else:
                bc.data=[(0,)]; bc.categoryAxis.categoryNames=["No records"]
                bc.valueAxis.valueMin=0; bc.valueAxis.valueMax=1; bc.valueAxis.valueStep=1
            bc.categoryAxis.labels.fontSize=5.5; bc.categoryAxis.labels.angle=45; bc.categoryAxis.labels.boxAnchor="ne"; bc.valueAxis.labels.fontSize=6
            chart.add(bc); return chart

        def make_detail(uid):
            widths=[34*mm,13*mm,25*mm,25*mm,28*mm,55*mm]
            detail=[[Paragraph(x,styles["CellHead"]) for x in ["Date / Day","Punches","First punch","Last punch","Worked time","Attendance status"]]]
            for day in report_dates:
                stamps=sorted(by_user_day.get((uid,day),[]))
                status,first,last,worked=self._attendance_day_status(uid,day,stamps)
                weekday=datetime.strptime(day,"%Y-%m-%d").strftime("%A")
                worked_display="—" if status.startswith("Incomplete punch") else format_worked_time(worked)
                vals=[f"{day} ({weekday})",str(len(stamps)),first or "—",last or "—",worked_display,status]
                detail.append([Paragraph(escape(str(v)),styles["Cell"]) for v in vals])
            tab=Table(detail,repeatRows=1,colWidths=widths,hAlign="LEFT")
            tab.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#24563B")),("GRID",(0,0),(-1,-1),.35,colors.HexColor("#CFD9D1")),("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#F4F7F5")]),("VALIGN",(0,0),(-1,-1),"MIDDLE"),("LEFTPADDING",(0,0),(-1,-1),4),("RIGHTPADDING",(0,0),(-1,-1),4),("TOPPADDING",(0,0),(-1,-1),1.5),("BOTTOMPADDING",(0,0),(-1,-1),1.5)]))
            return tab

        def employee_page(uid):
            entries=[(day,by_user_day.get((uid,day),[])) for day in report_dates]
            employee_rows=[r for r in rows if str(r[0])==uid]
            daily_counts={day:len(stamps) for day,stamps in entries if stamps}
            incomplete=sum(1 for day,stamps in entries if len(stamps)==1)
            active_days=sum(1 for day,stamps in entries if stamps)
            first_stamp=min((r[1] for r in employee_rows),default="—")
            last_stamp=max((r[1] for r in employee_rows),default="—")
            story.append(Paragraph(escape(self._name(uid)),styles["EmployeeTitle"]))
            story.append(Paragraph(f"Employee ID: {escape(uid)} &nbsp; | &nbsp; Period: {start_date} to {end_date}",styles["BodyText"]))
            story.append(Spacer(1,2*mm))
            story.append(make_stats([("TOTAL PUNCHES",len(employee_rows)),("ACTIVE DAYS",active_days),("INCOMPLETE DAYS",incomplete),("FIRST PUNCH",first_stamp[:16] if first_stamp!="—" else "—"),("LAST PUNCH",last_stamp[:16] if last_stamp!="—" else "—")]))
            story.extend([Spacer(1,1.5*mm),Paragraph("Attendance activity",styles["Heading2"]),make_chart(daily_counts),Spacer(1,0.5*mm),Paragraph("Daily attendance records",styles["Heading2"]),make_detail(uid),Spacer(1,1*mm),Paragraph("Status is calculated using saved schedules, grace periods, minimum hours, working weekdays and holidays.",styles["SmallNote"])])

        if is_collective:
            story.append(Paragraph("SCAFA Workforce — Collective Attendance Report",styles["ReportTitle"]))
            story.append(Paragraph(f"All staff &nbsp; | &nbsp; Period: {start_date} to {end_date} &nbsp; | &nbsp; Generated: {datetime.now().strftime('%d %b %Y, %H:%M')}",styles["BodyText"]))
            story.append(Spacer(1,4*mm))
            story.append(make_stats([("TOTAL PUNCHES",len(rows)),("STAFF",len(staff_ids)),("ACTIVE DAYS",len(all_by_day)),("AVERAGE PUNCHES / DAY",f"{len(rows)/max(1,len(all_by_day)):.1f}")]))
            story.extend([Spacer(1,3*mm),Paragraph("Collective attendance activity",styles["Heading2"]),make_chart(all_by_day)])
            for uid in staff_ids:
                story.append(PageBreak()); employee_page(uid)
        else: employee_page(str(scope))

        def footer(canvas,doc):
            canvas.saveState(); width=pagesize[0]
            canvas.setStrokeColor(colors.HexColor("#C9D8CD")); canvas.line(15*mm,12*mm,width-15*mm,12*mm)
            canvas.setFont("Helvetica",7); canvas.setFillColor(colors.HexColor("#64748b"))
            canvas.drawString(15*mm,7*mm,"SCAFA Workforce • Confidential attendance record")
            canvas.drawRightString(width-15*mm,7*mm,f"Page {doc.page}")
            canvas.restoreState()
        doc=Doc(path,pagesize=pagesize,rightMargin=15*mm,leftMargin=15*mm,topMargin=10*mm,bottomMargin=14*mm,title="SCAFA Workforce Attendance Report")
        doc.build(story,onFirstPage=footer,onLaterPages=footer)

if __name__=="__main__":
    App().mainloop()