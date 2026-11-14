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


    def test_migration_with_existing_joining_date_creates_active_event_after_baseline(self):
        with sqlite3.connect(app.DB) as db:
            db.execute("CREATE TABLE staff(user_id TEXT PRIMARY KEY, name TEXT NOT NULL DEFAULT '')")
            db.execute("CREATE TABLE punches(user_id TEXT NOT NULL, punch_time TEXT NOT NULL, status TEXT DEFAULT '', UNIQUE(user_id,punch_time,status))")
            db.execute("ALTER TABLE staff ADD COLUMN joining_date TEXT NOT NULL DEFAULT ''")
            db.execute("ALTER TABLE staff ADD COLUMN active INTEGER NOT NULL DEFAULT 1")
            db.execute("INSERT INTO staff(user_id,name,joining_date,active) VALUES('41','Existing Hire','2024-05-10',1)")
        app.init_db()
        with sqlite3.connect(app.DB) as db:
            events = db.execute(
                "SELECT active,effective_date,source FROM staff_status_history WHERE user_id='41' ORDER BY effective_date"
            ).fetchall()
            self.assertFalse(app.employee_active_on(db, "41", "2024-05-09"))
            self.assertTrue(app.employee_active_on(db, "41", "2024-05-10"))
        self.assertEqual(events, [
            (0, "0001-01-01", "migration-baseline"),
            (1, "2024-05-10", "migration")
        ])

    def test_migration_with_existing_baseline_only_repairs_missing_active_event(self):
        app.init_db()
        with sqlite3.connect(app.DB) as db:
            db.execute("INSERT INTO staff(user_id,name,joining_date,active) VALUES('42','Existing Hire','2024-05-10',1)")
            db.execute(
                "INSERT INTO staff_status_history(user_id,active,effective_date,source) VALUES('42',0,'0001-01-01','migration-baseline')"
            )
        app.init_db()
        with sqlite3.connect(app.DB) as db:
            self.assertFalse(app.employee_active_on(db, "42", "2024-05-09"))
            self.assertTrue(app.employee_active_on(db, "42", "2024-05-10"))
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM staff_status_history WHERE user_id='42' AND active=1"
            ).fetchone()[0], 1)

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


    def test_new_employee_with_future_joining_date_is_inactive_until_start(self):
        app.init_db()
        with sqlite3.connect(app.DB) as db:
            db.execute("INSERT INTO staff(user_id,name,joining_date,active) VALUES('31','Future Hire','2026-12-01',1)")
            app.save_profile_status_history(db, "31", "2026-12-01", True, is_new=True, effective_today="2026-11-14")
            self.assertFalse(app.employee_active_on(db, "31", "2026-11-30"))
            self.assertTrue(app.employee_active_on(db, "31", "2026-12-01"))
            events = db.execute(
                "SELECT active,effective_date FROM staff_status_history WHERE user_id='31' ORDER BY effective_date"
            ).fetchall()
        self.assertEqual(events, [(0, "0001-01-01"), (1, "2026-12-01")])

    def test_editing_joining_date_moves_only_initial_start_event(self):
        app.init_db()
        with sqlite3.connect(app.DB) as db:
            db.execute("INSERT INTO staff(user_id,name,joining_date,active) VALUES('32','Sara','2024-01-01',1)")
            app.save_profile_status_history(db, "32", "2024-01-01", True, is_new=True, effective_today="2026-11-14")
            db.execute(
                "INSERT INTO staff_status_history(user_id,active,effective_date,source) VALUES('32',0,'2026-06-01','profile')"
            )
            app.save_profile_status_history(
                db, "32", "2024-02-01", True,
                previous_joining_date="2024-01-01", effective_today="2026-11-14"
            )
            self.assertFalse(app.employee_active_on(db, "32", "2024-01-31"))
            self.assertTrue(app.employee_active_on(db, "32", "2024-02-01"))
            self.assertFalse(app.employee_active_on(db, "32", "2026-06-01"))
            events = db.execute(
                "SELECT active,effective_date FROM staff_status_history WHERE user_id='32' ORDER BY effective_date"
            ).fetchall()
        self.assertEqual(events, [(0, "0001-01-01"), (1, "2024-02-01"), (0, "2026-06-01")])

    def test_joining_date_edit_rejects_collision_without_losing_history(self):
        app.init_db()
        with sqlite3.connect(app.DB) as db:
            db.execute("INSERT INTO staff(user_id,name,joining_date,active) VALUES('33','Ali','2024-01-01',1)")
            app.save_profile_status_history(db, "33", "2024-01-01", True, is_new=True)
            db.execute(
                "INSERT INTO staff_status_history(user_id,active,effective_date,source) VALUES('33',0,'2024-02-01','profile')"
            )
            with self.assertRaises(ValueError):
                app.save_profile_status_history(
                    db, "33", "2024-02-01", True, previous_joining_date="2024-01-01"
                )
            self.assertTrue(app.employee_active_on(db, "33", "2024-01-15"))
            self.assertFalse(app.employee_active_on(db, "33", "2024-02-01"))


    def test_active_toggle_records_effective_date_without_changing_joining_date(self):
        app.init_db()
        with sqlite3.connect(app.DB) as db:
            db.execute("INSERT INTO staff(user_id,name,joining_date,active) VALUES('34','Mina','2024-01-01',1)")
            app.save_profile_status_history(db, "34", "2024-01-01", True, is_new=True)
            app.save_profile_status_history(
                db, "34", "2024-01-01", False,
                previous_joining_date="2024-01-01", status_changed=True,
                effective_today="2026-11-14"
            )
            self.assertTrue(app.employee_active_on(db, "34", "2026-11-13"))
            self.assertFalse(app.employee_active_on(db, "34", "2026-11-14"))

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
