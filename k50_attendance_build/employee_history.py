"""Shared employment-history initialization for attendance-device synchronization."""
from datetime import date, datetime


def normalize_device_user_id(value):
    """Normalize a device ID without treating numeric zero as a missing value."""
    return str("" if value is None else value).strip()


def get_device_user_id(user):
    """Read the primary device ID, falling back when it is absent or blank."""
    uid = normalize_device_user_id(getattr(user, "user_id", None))
    if not uid:
        uid = normalize_device_user_id(getattr(user, "uid", ""))
    return uid


def ensure_device_employee_status_history(db, user_id, first_punch_date=None, effective_today=None):
    """Give a device-synced employee a dated status baseline without inventing prior attendance."""
    uid = normalize_device_user_id(user_id)
    if not uid:
        return False
    profile = db.execute(
        "SELECT active,joining_date FROM staff WHERE user_id=?", (uid,)
    ).fetchone()
    if profile is None:
        return False
    if db.execute(
        """SELECT 1 FROM staff_status_history
           WHERE user_id=? AND source NOT LIKE '%-baseline' LIMIT 1""",
        (uid,)
    ).fetchone():
        return False

    today = effective_today or date.today().isoformat()
    active = bool(profile[0])
    effective = today
    joining = str(profile[1] or "").strip()
    joining_is_valid = False
    if active and joining:
        try:
            effective = datetime.strptime(
                joining, "%Y-%m-%d"
            ).date().isoformat()
        except ValueError:
            pass
        else:
            joining_is_valid = True
    if active and not joining_is_valid and first_punch_date:
        try:
            effective = datetime.strptime(
                str(first_punch_date), "%Y-%m-%d"
            ).date().isoformat()
        except ValueError:
            pass

    if active:
        db.execute(
            """INSERT OR IGNORE INTO staff_status_history
               (user_id,active,effective_date,source)
               VALUES(?,0,'0001-01-01','device-sync-baseline')""",
            (uid,)
        )
    else:
        # A legacy inactive profile has no known deactivation date. Remove only
        # synthetic baselines so earlier attendance is not retroactively excluded.
        db.execute(
            "DELETE FROM staff_status_history WHERE user_id=? AND source LIKE '%-baseline'",
            (uid,),
        )
    db.execute(
        """INSERT INTO staff_status_history(user_id,active,effective_date,source)
           VALUES(?,?,?,'device-sync')
           ON CONFLICT(user_id,effective_date) DO NOTHING""",
        (uid, int(bool(profile[0])), effective)
    )
    return True
