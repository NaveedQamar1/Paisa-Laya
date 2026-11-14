import sqlite3
import tempfile
import unittest
from pathlib import Path

import app


class EmployeeProfileMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.old_db = app.DB
        app.DB = Path(self.temp.name) / "attendance.db"

    def tearDown(self):
        app.DB = self.old_db
        self.temp.cleanup()

    def test_existing_database_migrates_without_losing_staff_or_punches(self):
        with sqlite3.connect(app.DB) as db:
            db.execute("CREATE TABLE staff(user_id TEXT PRIMARY KEY, name TEXT NOT NULL DEFAULT '')")
            db.execute("CREATE TABLE punches(user_id TEXT NOT NULL, punch_time TEXT NOT NULL, status TEXT DEFAULT '', UNIQUE(user_id,punch_time,status))")
            db.execute("INSERT INTO staff(user_id,name) VALUES('17','Ayesha')")
            db.execute("INSERT INTO punches(user_id,punch_time,status) VALUES('17','2026-11-01 09:45:00','')")
        app.init_db()
        with sqlite3.connect(app.DB) as db:
            staff = db.execute(
                "SELECT user_id,name,department,designation,joining_date,active FROM staff WHERE user_id='17'"
            ).fetchone()
            punches = db.execute("SELECT COUNT(*) FROM punches").fetchone()[0]
        self.assertEqual(staff, ("17", "Ayesha", "", "", "", 1))
        self.assertEqual(punches, 1)

    def test_new_database_has_employee_profile_fields(self):
        app.init_db()
        with sqlite3.connect(app.DB) as db:
            columns = {row[1] for row in db.execute("PRAGMA table_info(staff)")}
        self.assertTrue({"department", "designation", "joining_date", "active"}.issubset(columns))

    def test_status_history_migration_preserves_existing_employment_period(self):
        with sqlite3.connect(app.DB) as db:
            db.execute("CREATE TABLE staff(user_id TEXT PRIMARY KEY, name TEXT NOT NULL DEFAULT '')")
            db.execute("CREATE TABLE punches(user_id TEXT NOT NULL, punch_time TEXT NOT NULL, status TEXT DEFAULT '', UNIQUE(user_id,punch_time,status))")
            db.execute("INSERT INTO staff(user_id,name) VALUES('21','Bilal')")
            db.execute("INSERT INTO punches(user_id,punch_time,status) VALUES('21','2024-03-05 09:00:00','')")
        app.init_db()
        with sqlite3.connect(app.DB) as db:
            event = db.execute(
                "SELECT active,effective_date,source FROM staff_status_history WHERE user_id='21'"
            ).fetchone()
            self.assertEqual(event, (1, "2024-03-05", "migration"))
            self.assertTrue(app.employee_active_on(db, "21", "2024-03-05"))
            self.assertTrue(app.employee_active_on(db, "21", "2026-11-14"))

    def test_status_history_changes_only_future_effective_days(self):
        app.init_db()
        with sqlite3.connect(app.DB) as db:
            db.execute("INSERT INTO staff(user_id,name,active) VALUES('22','Sara',1)")
            db.execute(
                "INSERT INTO staff_status_history(user_id,active,effective_date,source) VALUES('22',1,'2024-01-01','test')"
            )
            db.execute(
                "INSERT INTO staff_status_history(user_id,active,effective_date,source) VALUES('22',0,'2026-11-14','test')"
            )
            self.assertTrue(app.employee_active_on(db, "22", "2026-11-13"))
            self.assertFalse(app.employee_active_on(db, "22", "2026-11-14"))
            self.assertFalse(app.employee_active_on(db, "22", "2026-12-01"))

    def test_preloaded_status_events_respect_effective_date(self):
        events = [("2024-01-01", True), ("2026-11-14", False)]
        self.assertTrue(app.employee_active_from_events(events, "2026-11-13"))
        self.assertFalse(app.employee_active_from_events(events, "2026-11-14"))
        self.assertFalse(app.employee_active_from_events(events, "2026-12-01"))

    def test_preloaded_status_events_use_fallback_before_first_event(self):
        events = [("2026-11-14", False)]
        self.assertTrue(app.employee_active_from_events(events, "2026-11-13", True))
        self.assertFalse(app.employee_active_from_events(events, "2026-11-14", True))

    def test_device_name_sync_does_not_overwrite_profile_metadata(self):
        app.init_db()
        with sqlite3.connect(app.DB) as db:
            db.execute(
                "INSERT INTO staff(user_id,name,department,designation,joining_date,active) VALUES(?,?,?,?,?,?)",
                ("17", "Ayesha", "Kitchen", "Chef", "2024-02-01", 1)
            )
        ctx = type("Context", (), {})()
        ctx._names_cache = None
        app.App._store_device_users(ctx, [type("DeviceUser", (), {"user_id": "17", "name": "Ayesha Updated"})()])
        with sqlite3.connect(app.DB) as db:
            row = db.execute(
                "SELECT name,department,designation,joining_date,active FROM staff WHERE user_id='17'"
            ).fetchone()
        self.assertEqual(row, ("Ayesha Updated", "Kitchen", "Chef", "2024-02-01", 1))


if __name__ == "__main__":
    unittest.main()
