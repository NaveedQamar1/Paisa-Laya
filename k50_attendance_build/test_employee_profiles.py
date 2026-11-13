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
