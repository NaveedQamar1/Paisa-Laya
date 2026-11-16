import sqlite3
import tempfile
import unittest
from datetime import date, timedelta
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


    def test_migration_is_idempotent_and_does_not_duplicate_status_events(self):
        with sqlite3.connect(app.DB) as db:
            db.execute("CREATE TABLE staff(user_id TEXT PRIMARY KEY, name TEXT NOT NULL DEFAULT '')")
            db.execute("CREATE TABLE punches(user_id TEXT NOT NULL, punch_time TEXT NOT NULL, status TEXT DEFAULT '', UNIQUE(user_id,punch_time,status))")
            db.execute("INSERT INTO staff(user_id,name) VALUES('44','Legacy Staff')")
            db.execute("INSERT INTO punches(user_id,punch_time,status) VALUES('44','2024-01-02 09:00:00','')")
        app.init_db()
        app.init_db()
        with sqlite3.connect(app.DB) as db:
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM staff_status_history WHERE user_id='44'"
            ).fetchone()[0], 2)
            self.assertTrue(app.employee_active_on(db, "44", "2024-01-02"))

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


    def test_employee_migration_preserves_existing_schedule_holiday_leave_and_settings(self):
        with sqlite3.connect(app.DB) as db:
            db.execute("CREATE TABLE staff(user_id TEXT PRIMARY KEY, name TEXT NOT NULL DEFAULT '')")
            db.execute("CREATE TABLE punches(user_id TEXT NOT NULL, punch_time TEXT NOT NULL, status TEXT DEFAULT '', UNIQUE(user_id,punch_time,status))")
            db.execute("INSERT INTO staff(user_id,name) VALUES('17','Ayesha')")
            db.execute("INSERT INTO punches(user_id,punch_time,status) VALUES('17','2026-11-01 09:45:00','')")

            db.execute("""CREATE TABLE staff_rules (
                user_id TEXT PRIMARY KEY, start_time TEXT NOT NULL DEFAULT '10:00',
                end_time TEXT NOT NULL DEFAULT '18:00', grace_minutes INTEGER NOT NULL DEFAULT 10,
                half_day_after TEXT NOT NULL DEFAULT '12:00', min_hours REAL NOT NULL DEFAULT 4.0
            )""")
            db.execute("""CREATE TABLE app_settings (
                setting TEXT PRIMARY KEY, value TEXT NOT NULL
            )""")
            db.execute("""CREATE TABLE holidays (
                holiday_date TEXT PRIMARY KEY, label TEXT NOT NULL DEFAULT ''
            )""")
            db.execute("""CREATE TABLE staff_day_rules (
                user_id TEXT NOT NULL, weekday INTEGER NOT NULL, start_time TEXT NOT NULL,
                end_time TEXT NOT NULL, grace_minutes INTEGER NOT NULL DEFAULT 15,
                shift_type TEXT NOT NULL DEFAULT 'Full day', PRIMARY KEY(user_id,weekday)
            )""")
            db.execute("""CREATE TABLE staff_leave (
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL,
                start_date TEXT NOT NULL, end_date TEXT NOT NULL,
                label TEXT NOT NULL DEFAULT 'Annual Leave'
            )""")

            db.execute(
                "INSERT INTO staff_rules VALUES(?,?,?,?,?,?)",
                ("17", "08:30", "17:30", 5, "12:30", 4.5),
            )
            db.executemany(
                "INSERT INTO app_settings(setting,value) VALUES(?,?)",
                [("weekday_window_start", "08:30"), ("custom_theme", "forest")],
            )
            db.execute(
                "INSERT INTO holidays(holiday_date,label) VALUES(?,?)",
                ("2026-12-25", "School Closure"),
            )
            db.execute(
                "INSERT INTO staff_day_rules VALUES(?,?,?,?,?,?)",
                ("17", 5, "09:00", "14:00", 10, "Half day"),
            )
            db.execute(
                "INSERT INTO staff_leave(user_id,start_date,end_date,label) VALUES(?,?,?,?)",
                ("17", "2026-12-28", "2026-12-30", "Annual Leave"),
            )

        app.init_db()

        with sqlite3.connect(app.DB) as db:
            self.assertEqual(
                db.execute("SELECT * FROM staff_rules WHERE user_id='17'").fetchone(),
                ("17", "08:30", "17:30", 5, "12:30", 4.5),
            )
            self.assertEqual(
                db.execute("SELECT value FROM app_settings WHERE setting='weekday_window_start'").fetchone(),
                ("08:30",),
            )
            self.assertEqual(
                db.execute("SELECT value FROM app_settings WHERE setting='custom_theme'").fetchone(),
                ("forest",),
            )
            self.assertEqual(
                db.execute("SELECT * FROM holidays WHERE holiday_date='2026-12-25'").fetchone(),
                ("2026-12-25", "School Closure"),
            )
            self.assertEqual(
                db.execute("SELECT * FROM staff_day_rules WHERE user_id='17' AND weekday=5").fetchone(),
                ("17", 5, "09:00", "14:00", 10, "Half day"),
            )
            self.assertEqual(
                db.execute("SELECT user_id,start_date,end_date,label FROM staff_leave WHERE user_id='17'").fetchone(),
                ("17", "2026-12-28", "2026-12-30", "Annual Leave"),
            )
            self.assertEqual(
                db.execute("SELECT user_id,punch_time,status FROM punches").fetchall(),
                [("17", "2026-11-01 09:45:00", "")],
            )

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

    def test_migration_repairs_profile_baseline_only_history(self):
        app.init_db()
        with sqlite3.connect(app.DB) as db:
            db.execute(
                "INSERT INTO staff(user_id,name,joining_date,active) VALUES('54','Existing Hire','2024-05-10',1)"
            )
            db.execute(
                "INSERT INTO staff_status_history(user_id,active,effective_date,source) VALUES('54',0,'0001-01-01','profile-baseline')"
            )

        app.init_db()
        with sqlite3.connect(app.DB) as db:
            self.assertFalse(app.employee_active_on(db, "54", "2024-05-09"))
            self.assertTrue(app.employee_active_on(db, "54", "2024-05-10"))
            history = db.execute(
                "SELECT active,effective_date,source FROM staff_status_history WHERE user_id='54' ORDER BY effective_date,id"
            ).fetchall()
        self.assertEqual(
            history,
            [
                (0, "0001-01-01", "profile-baseline"),
                (1, "2024-05-10", "migration"),
            ],
        )

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
                "SELECT active,effective_date,source FROM staff_status_history WHERE user_id='21' AND source='migration'"
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


    def test_legacy_inactive_employee_does_not_get_retroactive_baseline(self):
        with sqlite3.connect(app.DB) as db:
            db.execute("CREATE TABLE staff(user_id TEXT PRIMARY KEY, name TEXT NOT NULL DEFAULT '')")
            db.execute("CREATE TABLE punches(user_id TEXT NOT NULL, punch_time TEXT NOT NULL, status TEXT DEFAULT '', UNIQUE(user_id,punch_time,status))")
            db.execute("ALTER TABLE staff ADD COLUMN joining_date TEXT NOT NULL DEFAULT ''")
            db.execute("ALTER TABLE staff ADD COLUMN active INTEGER NOT NULL DEFAULT 1")
            db.execute("INSERT INTO staff(user_id,name,joining_date,active) VALUES('43','Former Staff','2020-01-01',0)")
        app.init_db()
        with sqlite3.connect(app.DB) as db:
            migration_day = db.execute(
                "SELECT effective_date FROM staff_status_history WHERE user_id='43' AND source='migration'"
            ).fetchone()[0]
            day_before_migration = (
                date.fromisoformat(migration_day) - timedelta(days=1)
            ).isoformat()
            self.assertTrue(app.employee_active_on(db, "43", day_before_migration))
            self.assertFalse(app.employee_active_on(db, "43", migration_day))
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM staff_status_history WHERE user_id='43' AND source LIKE '%baseline'"
            ).fetchone()[0], 0)


    def test_present_day_metric_uses_eligible_performance_totals(self):
        rows=[("17", {"present": 3}), ("18", {"present": 1})]
        self.assertEqual(app.count_expected_present_days(rows), 4)

    def test_only_active_scheduled_days_count_toward_performance(self):
        self.assertTrue(app.is_expected_attendance_day(True, "Present"))
        self.assertTrue(app.is_expected_attendance_day(True, "Absent"))
        self.assertFalse(app.is_expected_attendance_day(False, "Present"))
        self.assertFalse(app.is_expected_attendance_day(True, "Inactive"))
        self.assertFalse(app.is_expected_attendance_day(True, "Day off"))
        self.assertFalse(app.is_expected_attendance_day(True, "Holiday"))
        self.assertFalse(app.is_expected_attendance_day(True, "On leave — Annual Leave"))

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

    def test_editing_joining_date_moves_device_synced_employment_start(self):
        app.init_db()
        with sqlite3.connect(app.DB) as db:
            db.execute(
                "INSERT INTO staff(user_id,name,joining_date,active) VALUES('77','Ayesha','',1)"
            )
            app.ensure_device_employee_status_history(
                db, "77", "2026-11-15", effective_today="2026-11-16"
            )
            app.save_employee_profile(
                db, "77", "Ayesha", joining_date="2024-01-01",
                current_user_id="77", effective_today="2026-11-16"
            )
            events = db.execute(
                """SELECT active,effective_date,source FROM staff_status_history
                   WHERE user_id='77' ORDER BY effective_date,id"""
            ).fetchall()
            self.assertFalse(app.employee_active_on(db, "77", "2023-12-31"))
            self.assertTrue(app.employee_active_on(db, "77", "2024-01-01"))
        self.assertEqual(
            events,
            [
                (0, "0001-01-01", "device-sync-baseline"),
                (1, "2024-01-01", "profile"),
            ],
        )


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


    def test_future_employee_activation_takes_effect_on_joining_date(self):
        app.init_db()
        with sqlite3.connect(app.DB) as db:
            app.save_profile_status_history(
                db, "51", "2026-12-01", False, is_new=True, effective_today="2026-11-14"
            )
            app.save_profile_status_history(
                db, "51", "2026-12-01", True,
                previous_joining_date="2026-12-01", status_changed=True,
                effective_today="2026-11-14"
            )
            self.assertFalse(app.employee_active_on(db, "51", "2026-11-30"))
            self.assertTrue(app.employee_active_on(db, "51", "2026-12-01"))

    def test_joining_date_cannot_be_moved_after_a_later_status_change(self):
        app.init_db()
        with sqlite3.connect(app.DB) as db:
            app.save_profile_status_history(db, "52", "2024-01-01", True, is_new=True)
            db.execute(
                "INSERT INTO staff_status_history(user_id,active,effective_date,source) VALUES('52',0,'2025-01-01','profile')"
            )
            with self.assertRaises(ValueError):
                app.save_profile_status_history(
                    db, "52", "2025-06-01", True,
                    previous_joining_date="2024-01-01"
                )
            self.assertTrue(app.employee_active_on(db, "52", "2024-06-01"))
            self.assertFalse(app.employee_active_on(db, "52", "2025-01-01"))


    def test_profile_joining_date_creates_history_for_device_synced_employee(self):
        app.init_db()
        with sqlite3.connect(app.DB) as db:
            db.execute("INSERT INTO staff(user_id,name,active) VALUES('53','Device Synced',1)")
            app.save_profile_status_history(
                db, "53", "2024-04-01", True,
                previous_joining_date="", effective_today="2026-11-14"
            )
            self.assertFalse(app.employee_active_on(db, "53", "2024-03-31"))
            self.assertTrue(app.employee_active_on(db, "53", "2024-04-01"))
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM staff_status_history WHERE user_id='53' AND active=1"
            ).fetchone()[0], 1)

    def test_device_sync_repairs_baseline_only_history_without_duplicates(self):
        app.init_db()
        with sqlite3.connect(app.DB) as db:
            db.execute(
                "INSERT INTO staff(user_id,name,joining_date,active) VALUES('55','Device Hire','2024-04-01',1)"
            )
            db.execute(
                "INSERT INTO staff_status_history(user_id,active,effective_date,source) VALUES('55',0,'0001-01-01','profile-baseline')"
            )

            self.assertTrue(
                app.ensure_device_employee_status_history(
                    db, "55", "2024-04-05", effective_today="2026-11-16"
                )
            )
            self.assertFalse(
                app.ensure_device_employee_status_history(
                    db, "55", "2024-04-05", effective_today="2026-11-16"
                )
            )
            history = db.execute(
                "SELECT active,effective_date,source FROM staff_status_history WHERE user_id='55' ORDER BY effective_date,id"
            ).fetchall()

        self.assertEqual(
            history,
            [
                (0, "0001-01-01", "profile-baseline"),
                (1, "2024-04-01", "device-sync"),
            ],
        )

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



class EmployeeProfileSaveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self.temp.name)
        self.old_db = app.DB
        self.old_base = app.BASE
        app.BASE = self.root
        app.DB = self.root / "attendance.db"
        app.init_db()

    def tearDown(self):
        app.DB = self.old_db
        app.BASE = self.old_base
        self.temp.cleanup()

    def save_profile(self, user_id, name, **overrides):
        values = {
            "user_id": user_id,
            "name": name,
            "department": "Kitchen",
            "designation": "Chef",
            "joining_date": "2024-01-01",
            "active": True,
        }
        values.update(overrides)
        with sqlite3.connect(app.DB) as db:
            return app.save_employee_profile(db, **values)

    def test_create_profile_saves_metadata_and_effective_start(self):
        self.assertEqual(
            self.save_profile("701", "Mariam", effective_today="2026-11-15"),
            "701",
        )
        with sqlite3.connect(app.DB) as db:
            profile = db.execute(
                "SELECT user_id,name,department,designation,joining_date,active FROM staff WHERE user_id='701'"
            ).fetchone()
            history = db.execute(
                "SELECT active,effective_date,source FROM staff_status_history WHERE user_id='701' ORDER BY effective_date"
            ).fetchall()
        self.assertEqual(profile, ("701", "Mariam", "Kitchen", "Chef", "2024-01-01", 1))
        self.assertEqual(history, [
            (0, "0001-01-01", "profile-baseline"),
            (1, "2024-01-01", "profile"),
        ])

    def test_edit_profile_updates_metadata_without_rewriting_status_history(self):
        self.save_profile("701", "Mariam")
        with sqlite3.connect(app.DB) as db:
            before = db.execute(
                "SELECT active,effective_date,source FROM staff_status_history WHERE user_id='701' ORDER BY effective_date"
            ).fetchall()
        self.save_profile(
            "701", "Mariam Khan", department="Pastry", designation="Head Chef",
            current_user_id="701"
        )
        with sqlite3.connect(app.DB) as db:
            profile = db.execute(
                "SELECT name,department,designation FROM staff WHERE user_id='701'"
            ).fetchone()
            after = db.execute(
                "SELECT active,effective_date,source FROM staff_status_history WHERE user_id='701' ORDER BY effective_date"
            ).fetchall()
        self.assertEqual(profile, ("Mariam Khan", "Pastry", "Head Chef"))
        self.assertEqual(after, before)

    def test_new_profile_cannot_overwrite_an_existing_device_id(self):
        self.save_profile("701", "Original Employee")
        with self.assertRaisesRegex(ValueError, "already belongs to an employee"):
            self.save_profile("701", "Replacement Employee")
        with sqlite3.connect(app.DB) as db:
            self.assertEqual(
                db.execute("SELECT name FROM staff WHERE user_id='701'").fetchone()[0],
                "Original Employee",
            )

    def test_edit_cannot_change_device_assigned_id(self):
        self.save_profile("701", "Original Employee")
        with self.assertRaisesRegex(ValueError, "device-assigned employee ID cannot be changed"):
            self.save_profile("702", "Changed Employee", current_user_id="701")
        with sqlite3.connect(app.DB) as db:
            self.assertEqual(
                db.execute("SELECT user_id,name FROM staff").fetchall(),
                [("701", "Original Employee")],
            )

    def test_edit_of_deleted_profile_does_not_recreate_it(self):
        with self.assertRaisesRegex(ValueError, "profile no longer exists"):
            self.save_profile("701", "Stale Employee", current_user_id="701")
        with sqlite3.connect(app.DB) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM staff").fetchone()[0], 0)

    def test_invalid_joining_date_is_rejected_without_writes(self):
        with self.assertRaisesRegex(ValueError, "Use YYYY-MM-DD"):
            self.save_profile("701", "Invalid Date", joining_date="15-11-2026")
        with sqlite3.connect(app.DB) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM staff").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM staff_status_history").fetchone()[0], 0)

    def test_status_history_failure_rolls_back_profile_update(self):
        self.save_profile("701", "Original Employee")
        with sqlite3.connect(app.DB) as db:
            before = db.execute(
                "SELECT active,effective_date,source FROM staff_status_history WHERE user_id='701' ORDER BY effective_date"
            ).fetchall()
            db.execute(
                """CREATE TRIGGER reject_profile_history_update
                   BEFORE UPDATE ON staff_status_history
                   WHEN NEW.source='profile'
                   BEGIN SELECT RAISE(ABORT, 'simulated history failure'); END"""
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.save_profile(
                "701", "Changed Employee", joining_date="2024-02-01",
                current_user_id="701"
            )
        with sqlite3.connect(app.DB) as db:
            profile = db.execute(
                "SELECT name,joining_date FROM staff WHERE user_id='701'"
            ).fetchone()
            after = db.execute(
                "SELECT active,effective_date,source FROM staff_status_history WHERE user_id='701' ORDER BY effective_date"
            ).fetchall()
        self.assertEqual(profile, ("Original Employee", "2024-01-01"))
        self.assertEqual(after, before)


class EmployeeDirectoryFilterTests(unittest.TestCase):
    def setUp(self):
        self.rows = [
            ("701", "Ayesha Khan", "Pastry", "Chef", "2024-05-10", 1),
            ("702", "Bilal Ahmed", "Kitchen", "Commis", "2023-02-01", 0),
        ]

    def test_search_matches_id_name_department_designation_and_joining_date(self):
        for query in ("701", "AYESHA", "pastry", "chef", "2024-05"):
            with self.subTest(query=query):
                self.assertEqual(app.filter_employee_rows(self.rows, query), [self.rows[0]])

    def test_search_matches_the_displayed_active_status(self):
        self.assertEqual(app.filter_employee_rows(self.rows, "inactive"), [self.rows[1]])
        self.assertEqual(app.filter_employee_rows(self.rows, "active"), [self.rows[0]])

    def test_empty_search_preserves_all_rows_and_input_order(self):
        self.assertEqual(app.filter_employee_rows(self.rows, "  "), self.rows)

    def test_filtered_directory_clears_a_hidden_profile_selection(self):
        visible = app.filter_employee_rows(self.rows, "pastry")
        self.assertIsNone(app.retain_visible_employee_selection("702", visible))

    def test_filtered_directory_retains_a_visible_profile_selection(self):
        visible = app.filter_employee_rows(self.rows, "ayesha")
        self.assertEqual(app.retain_visible_employee_selection("701", visible), "701")
        self.assertIsNone(app.retain_visible_employee_selection(None, visible))

    def test_employee_selection_requires_a_matching_existing_row(self):
        row = self.rows[0]
        self.assertIsNone(app.employee_profile_selection_data(None, row))
        self.assertIsNone(app.employee_profile_selection_data("701", None))
        self.assertIsNone(app.employee_profile_selection_data("702", row))
        self.assertIsNone(app.employee_profile_selection_data("701", row[:5]))

    def test_employee_selection_normalizes_existing_profile_for_the_form(self):
        row = self.rows[1]
        self.assertEqual(
            app.employee_profile_selection_data("702", row),
            {
                "user_id": "702",
                "fields": ("702", "Bilal Ahmed", "Kitchen", "Commis", "2023-02-01"),
                "active": False,
            },
        )


if __name__ == "__main__":
    unittest.main()

    unittest.main()
