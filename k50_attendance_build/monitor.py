"""Background K50 monitor with persistent new-punch detection and desktop alerts."""
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
STATE = BASE / "monitor-state.json"


def notify(title, message):
    """Send a native desktop notification and return any delivery error."""
    if sys.platform == "darwin":
        result = subprocess.run(
            ["/usr/bin/osascript", "-e",
             f'display notification {json.dumps(message)} with title {json.dumps(title)}'],
            capture_output=True, text=True, check=False
        )
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or "macOS notification delivery failed")
    elif sys.platform == "win32":
        from winotify import Notification, audio
        toast = Notification(app_id="SCAFA Workforce", title=title, msg=message,
                             duration="short")
        toast.set_audio(audio.Default, loop=False)
        toast.show()


def record_key(row):
    stamp = row.timestamp.strftime("%Y-%m-%d %H:%M:%S")
    uid = str(row.user_id)
    status = str(getattr(row, "status", ""))
    return stamp, uid, status


def load_state(device_key):
    try:
        state = json.loads(STATE.read_text(encoding="utf-8"))
        if state.get("device") == device_key and isinstance(state.get("last_seen"), list):
            return tuple(str(x) for x in state["last_seen"])
    except (OSError, ValueError, TypeError):
        pass
    return None


def save_state(device_key, last_seen):
    temporary = STATE.with_suffix(".tmp")
    temporary.write_text(json.dumps({"device": device_key, "last_seen": list(last_seen)}),
                         encoding="utf-8")
    temporary.replace(STATE)


def log_error(message):
    try:
        with open(BASE / "monitor-error.log", "a", encoding="utf-8") as log:
            log.write(f"{datetime.now().isoformat()} {message!r}\n")
    except OSError:
        pass


def main():
    BASE.mkdir(parents=True, exist_ok=True)
    last_device = None
    last_seen = None
    while True:
        conn = None
        try:
            cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
            ip = str(cfg["ip"]).strip()
            port = int(cfg.get("port", 4370))
            key = int(cfg.get("key", 0))
            interval = max(10, min(300, int(cfg.get("interval", 10))))
            device_key = f"{ip}:{port}"
            if device_key != last_device:
                last_seen = load_state(device_key)
                last_device = device_key
            from zk import ZK
            conn = ZK(ip, port=port, timeout=12, password=key,
                      force_udp=False, ommit_ping=False).connect()
            users = conn.get_users()
            records = sorted(conn.get_attendance(), key=record_key)
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
                    stamp, uid, status = record_key(row)
                    db.execute(
                        """INSERT OR IGNORE INTO punches(user_id,punch_time,status)
                           VALUES(?,?,?)""", (uid, stamp, status)
                    )
                    name_row = db.execute(
                        "SELECT name FROM staff WHERE user_id=?", (uid,)
                    ).fetchone()
                    name = name_row[0] if name_row and name_row[0] else f"User {uid}"
                    inserted.append((stamp, uid, status, name))
            if records:
                newest = record_key(records[-1])
                # First run for a device establishes a baseline. It does not alert
                # for the device's historical attendance backlog.
                if last_seen is None:
                    last_seen = newest
                    save_state(device_key, last_seen)
                else:
                    new_events = [item for item in inserted
                                  if (item[0], item[1], item[2]) > last_seen]
                    for stamp, uid, status, name in new_events:
                        punch_dt = datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S")
                        when = punch_dt.strftime("%I:%M:%S %p")
                        same_day_count = sum(
                            1 for item in inserted
                            if item[1] == uid and item[0][:10] == stamp[:10]
                            and item[0] <= stamp
                        )
                        if same_day_count == 1:
                            title, detail = "Employee arrived", f"{name} arrived • {when}"
                        elif same_day_count == 2:
                            title, detail = "Employee checked out", f"{name} checked out • {when}"
                        else:
                            title, detail = "New attendance punch", f"{name} • {when}"
                        try:
                            notify(title, detail)
                        except Exception as exc:
                            log_error(f"Notification failed for {name} ({uid}) at {stamp}: {exc}")
                    if newest > last_seen:
                        last_seen = newest
                        save_state(device_key, last_seen)
        except Exception as exc:
            log_error(exc)
        finally:
            if conn:
                try:
                    conn.disconnect()
                except Exception:
                    pass
        time.sleep(interval)


if __name__ == "__main__":
    main()
