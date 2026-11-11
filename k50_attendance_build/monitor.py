import json
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from datetime import datetime

BASE = Path.home() / "SCAFAWorkforce"
LEGACY_BASE = Path.home() / "K50AttendanceManager"
DB_BASE = BASE if (BASE / "attendance.db").exists() or not (LEGACY_BASE / "attendance.db").exists() else LEGACY_BASE
DB = DB_BASE / "attendance.db"
CONFIG = BASE / "device.json"


def notify(title, message):
    if sys.platform == "darwin":
        # osascript is built into macOS.
        subprocess.run(
            ["/usr/bin/osascript", "-e",
             f'display notification {json.dumps(message)} with title {json.dumps(title)}'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False
        )
    elif sys.platform == "win32":
        try:
            from winotify import Notification, audio
            toast = Notification(app_id="SCAFA Workforce", title=title, msg=message,
                                 duration="short")
            toast.set_audio(audio.Default, loop=False)
            toast.show()
        except Exception as exc:
            with open(BASE / "monitor-error.log", "a", encoding="utf-8") as log:
                log.write(f"{datetime.now().isoformat()} notification error: {exc!r}\n")


def main():
    BASE.mkdir(parents=True, exist_ok=True)
    while True:
        try:
            cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
            ip = str(cfg["ip"]).strip()
            port = int(cfg.get("port", 4370))
            key = int(cfg.get("key", 0))
            interval = max(10, min(300, int(cfg.get("interval", 10))))
            from zk import ZK
            conn = None
            try:
                conn = ZK(ip, port=port, timeout=12, password=key,
                          force_udp=False, ommit_ping=False).connect()
                users = conn.get_users()
                records = conn.get_attendance()
                inserted = []
                with sqlite3.connect(DB, timeout=20) as db:
                    for user in users:
                        uid = str(getattr(user, "user_id", None) or getattr(user, "uid", "")).strip()
                        name = str(getattr(user, "name", "") or "").strip()
                        if uid and name:
                            db.execute(
                                """INSERT INTO staff(user_id,name) VALUES(?,?)
                                   ON CONFLICT(user_id) DO UPDATE SET name=excluded.name""",
                                (uid, name)
                            )
                    for row in records:
                        stamp = row.timestamp.strftime("%Y-%m-%d %H:%M:%S")
                        uid = str(row.user_id)
                        cur = db.execute(
                            """INSERT OR IGNORE INTO punches(user_id,punch_time,status)
                               VALUES(?,?,?)""",
                            (uid, stamp, str(getattr(row, "status", "")))
                        )
                        if cur.rowcount:
                            name_row = db.execute(
                                "SELECT name FROM staff WHERE user_id=?", (uid,)
                            ).fetchone()
                            name = name_row[0] if name_row and name_row[0] else f"Staff ID {uid}"
                            inserted.append((uid, name, stamp))
                # Ignore old records on first startup to avoid a burst of historical alerts.
                recent_cutoff = datetime.now().timestamp() - 180
                for uid, name, stamp in inserted:
                    punch_dt = datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S")
                    if punch_dt.timestamp() < recent_cutoff:
                        continue
                    with sqlite3.connect(DB, timeout=20) as db:
                        count = db.execute(
                            "SELECT COUNT(*) FROM punches WHERE user_id=? AND substr(punch_time,1,10)=?",
                            (uid, punch_dt.strftime("%Y-%m-%d"))
                        ).fetchone()[0]
                    when = punch_dt.strftime("%I:%M %p")
                    if count == 1:
                        notify("Employee arrived", f"{name} Arrived • {when}")
                    elif count == 2:
                        notify("Employee checked out", f"{name} Departed • {when}")
                    else:
                        notify("Additional attendance punch", f"{name} • {when}")
            finally:
                if conn:
                    try:
                        conn.disconnect()
                    except Exception:
                        pass
            time.sleep(interval)
        except Exception as exc:
            try:
                with open(BASE / "monitor-error.log", "a", encoding="utf-8") as log:
                    log.write(f"{datetime.now().isoformat()} {exc!r}\n")
            except Exception:
                pass
            time.sleep(30)


if __name__ == "__main__":
    main()
