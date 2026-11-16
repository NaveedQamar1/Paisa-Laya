"""Background attendance-device monitor with persistent new-punch detection and desktop alerts."""
import json
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from datetime import datetime
from employee_history import ensure_device_employee_status_history, get_device_user_id

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
    """Return a normalized punch identity, or None for malformed device rows."""
    uid = get_device_user_id(row)
    timestamp = getattr(row, "timestamp", None)
    if not uid:
        return None
    try:
        if isinstance(timestamp, datetime):
            parsed = timestamp
        elif isinstance(timestamp, str):
            parsed = datetime.fromisoformat(timestamp.strip())
        else:
            return None
        if parsed.tzinfo is not None:
            return None
    except (TypeError, ValueError):
        return None
    status_value = getattr(row, "status", None)
    status = str("" if status_value is None else status_value)
    return parsed.strftime("%Y-%m-%d %H:%M:%S"), uid, status


def valid_device_records(records):
    """Filter malformed punch rows before sorting so one bad row cannot abort a sync."""
    valid = []
    skipped = 0
    for row in records:
        if record_key(row) is None:
            skipped += 1
        else:
            valid.append(row)
    valid.sort(key=record_key)
    return valid, skipped


def load_state(device_key):
    try:
        state = json.loads(STATE.read_text(encoding="utf-8"))
        # Valid JSON can still have the wrong root type (for example, a list or
        # null). Treat an unusable state document as a fresh baseline instead of
        # letting AttributeError abort every monitor poll.
        if not isinstance(state, dict):
            return None
        seen = state.get("seen")
        if state.get("device") == device_key and isinstance(seen, list):
            return {
                tuple(str(part) for part in item)
                for item in seen
                if isinstance(item, (list, tuple)) and len(item) == 3
            }
    except (OSError, ValueError, TypeError):
        pass
    return None


def save_state(device_key, seen):
    temporary = STATE.with_suffix(".tmp")
    # Persist all known punch identities so older delayed device timestamps
    # cannot be mistaken for new punches after a monitor restart.
    payload = {"device": device_key, "seen": sorted(seen)}
    temporary.write_text(json.dumps(payload), encoding="utf-8")
    temporary.replace(STATE)

def log_error(message):
    try:
        with open(BASE / "monitor-error.log", "a", encoding="utf-8") as log:
            log.write(f"{datetime.now().isoformat()} {message!r}\n")
    except OSError:
        pass


def notify_new_punches(inserted, last_seen):
    """Notify newly observed punches and retain failed deliveries for retry."""
    current_keys = {(stamp, uid, status) for stamp, uid, status, name in inserted}
    if last_seen is None:
        # First poll establishes a baseline; historical punches are not new alerts.
        return current_keys

    seen = set(last_seen)
    for stamp, uid, status, name in sorted(inserted, key=lambda item: item[0]):
        key = (stamp, uid, status)
        if key in seen:
            continue
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
            # Leave the identity unseen so the next poll can retry delivery.
            log_error(f"Notification failed for {name} ({uid}) at {stamp}: {exc}")
        else:
            seen.add(key)
    return seen


def initial_seen_punches(inserted):
    """Return the initial device baseline, including a valid empty baseline."""
    return {(stamp, uid, status) for stamp, uid, status, name in inserted}


def sync_device_records(db, users, records):
    """Synchronize device users and punches, then establish missing employment history."""
    synced_ids = set()
    for user in users:
        uid = get_device_user_id(user)
        name = str(getattr(user, "name", "") or "").strip()
        if uid and name:
            db.execute(
                """INSERT INTO staff(user_id,name) VALUES(?,?)
                   ON CONFLICT(user_id) DO UPDATE SET name=excluded.name""",
                (uid, name),
            )
            synced_ids.add(uid)

    inserted = []
    for row in records:
        key = record_key(row)
        if key is None:
            continue
        stamp, uid, status = key
        db.execute(
            """INSERT OR IGNORE INTO punches(user_id,punch_time,status)
               VALUES(?,?,?)""",
            (uid, stamp, status),
        )
        name_row = db.execute(
            "SELECT name FROM staff WHERE user_id=?", (uid,)
        ).fetchone()
        name = name_row[0] if name_row and name_row[0] else f"User {uid}"
        inserted.append((stamp, uid, status, name))
        synced_ids.add(uid)

    for uid in synced_ids:
        first_punch = db.execute(
            "SELECT MIN(substr(punch_time,1,10)) FROM punches WHERE user_id=?",
            (uid,),
        ).fetchone()[0]
        ensure_device_employee_status_history(db, uid, first_punch)
    return inserted


def main():
    BASE.mkdir(parents=True, exist_ok=True)
    last_device = None
    last_seen = None
    last_invalid_count = 0
    while True:
        conn = None
        # Keep the worker alive when its configuration is temporarily unavailable.
        # Without a default, an early read/parse/key error leaves interval undefined
        # and the retry sleep raises UnboundLocalError, terminating the monitor.
        interval = 10
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
            records, skipped = valid_device_records(conn.get_attendance())
            if skipped and skipped != last_invalid_count:
                log_error(
                    f"Skipped {skipped} malformed attendance records from device {device_key}"
                )
            last_invalid_count = skipped
            with sqlite3.connect(DB, timeout=20) as db:
                inserted = sync_device_records(db, users, records)
            if last_seen is None:
                # Persist an empty baseline too. Otherwise the first later punch
                # would be mistaken for historical data and never notify.
                last_seen = initial_seen_punches(inserted)
                save_state(device_key, last_seen)
            elif records:
                # Exact punch identities catch delayed/out-of-order device records.
                # Failed desktop notifications remain unseen and are retried next poll.
                last_seen = notify_new_punches(inserted, last_seen)
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
