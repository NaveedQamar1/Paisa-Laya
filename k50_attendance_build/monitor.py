import json
import sqlite3
import subprocess
import time
from pathlib import Path
from datetime import datetime

BASE = Path.home() / "SCAFAWorkforce"
LEGACY_BASE = Path.home() / "K50AttendanceManager"
DB_BASE = BASE if (BASE / "attendance.db").exists() or not (LEGACY_BASE / "attendance.db").exists() else LEGACY_BASE
DB = DB_BASE / "attendance.db"
CONFIG = BASE / "device.json"


def notify(title, message):
    title = title.replace("\\", "\\\\").replace('"', '\\"')
    message = message.replace("\\", "\\\\").replace('"', '\\"')
    script = f'display notification "{message}" with title "{title}"'
    subprocess.run(["/usr/bin/osascript", "-e", script],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main():
    BASE.mkdir(parents=True, exist_ok=True)
    while True:
        try:
            cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
            ip = str(cfg["ip"])
            port = int(cfg.get("port", 4370))
            key = int(cfg.get("key", 0))
            interval = max(30, min(300, int(cfg.get("interval", 60))))
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
                            db.execute("""INSERT INTO staff(user_id,name) VALUES(?,?)
                                          ON CONFLICT(user_id) DO UPDATE SET name=excluded.name""",
                                       (uid, name))
                    for row in records:
                        stamp = row.timestamp.strftime("%Y-%m-%d %H:%M:%S")
                        uid = str(row.user_id)
                        cur = db.execute("""INSERT OR IGNORE INTO punches(user_id,punch_time,status)
                                            VALUES(?,?,?)""",
                                         (uid, stamp, str(getattr(row, "status", ""))))
                        if cur.rowcount:
                            name_row = db.execute("SELECT name FROM staff WHERE user_id=?", (uid,)).fetchone()
                            name = name_row[0] if name_row and name_row[0] else f"Staff ID {uid}"
                            inserted.append((name, stamp))
                if inserted:
                    # Notify each newly detected punch; cap burst notifications to avoid flooding.
                    for name, stamp in inserted[-10:]:
                        when = datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S").strftime("%I:%M %p")
                        notify("New SCAFA attendance punch", f"{name} • {when}")
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
                    log.write(f"{datetime.now().isoformat()} {exc!r}\\n")
            except Exception:
                pass
            time.sleep(30)


if __name__ == "__main__":
    main()
