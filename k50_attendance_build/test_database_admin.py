import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import app


class DatabaseAdministrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self.temp.name)
        self.old_db = app.DB
        self.old_base = app.BASE
        app.BASE = self.root
        app.DB = self.root / "attendance.db"
        app.init_db()
        self.ctx = SimpleNamespace(
            status=SimpleNamespace(set=lambda value: None),
            _names_cache=None,
            refresh=lambda: None,
        )

    def tearDown(self):
        app.DB = self.old_db
        app.BASE = self.old_base
        self.temp.cleanup()

    def create_hardlink_or_skip(self, source, destination):
        try:
            os.link(source, destination)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"Hard links are unavailable on this filesystem: {exc}")

    def add_current_record(self, user_id, name, stamp):
        with sqlite3.connect(app.DB) as db:
            db.execute(
                "INSERT INTO staff(user_id,name) VALUES(?,?)",
                (user_id, name),
            )
            db.execute(
                "INSERT INTO punches(user_id,punch_time,status) VALUES(?,?,?)",
                (user_id, stamp, ""),
            )

    def test_backup_contains_consistent_staff_and_punch_data(self):
        self.add_current_record("101", "Current Staff", "2026-11-15 09:00:00")
        destination = self.root / "attendance-backup.db"
        with patch.object(app.filedialog, "asksaveasfilename", return_value=str(destination)), \
             patch.object(app.messagebox, "showinfo") as showinfo:
            app.App.backup_database(self.ctx)

        with sqlite3.connect(destination) as backup:
            self.assertEqual(
                backup.execute("PRAGMA integrity_check").fetchone()[0], "ok"
            )
            self.assertEqual(
                backup.execute("SELECT name FROM staff WHERE user_id='101'").fetchone()[0],
                "Current Staff",
            )
            self.assertEqual(
                backup.execute("SELECT COUNT(*) FROM punches WHERE user_id='101'").fetchone()[0],
                1,
            )
        showinfo.assert_called_once()

    def test_failed_backup_keeps_previous_destination_and_removes_temporary_file(self):
        corrupt_source = self.root / "corrupt-source.db"
        corrupt_source.write_bytes(b"not a SQLite database")
        destination = self.root / "existing-backup.db"
        destination.write_bytes(b"previous verified backup")

        with self.assertRaises(sqlite3.DatabaseError):
            app.write_database_backup(corrupt_source, destination)

        self.assertEqual(destination.read_bytes(), b"previous verified backup")
        self.assertEqual(list(self.root.glob(".existing-backup.db.*.tmp")), [])

    def test_backup_rejects_live_database_as_destination_without_modifying_data(self):
        self.add_current_record("101", "Keep Live Staff", "2026-11-16 09:00:00")

        with (
            patch.object(app.filedialog, "asksaveasfilename", return_value=str(app.DB)),
            patch.object(app.messagebox, "showerror") as showerror,
            patch.object(app.messagebox, "showinfo") as showinfo,
        ):
            app.App.backup_database(self.ctx)

        showerror.assert_called_once()
        self.assertIn("live attendance database", str(showerror.call_args).lower())
        showinfo.assert_not_called()
        with sqlite3.connect(app.DB) as current:
            self.assertEqual(current.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(
                current.execute("SELECT name FROM staff WHERE user_id='101'").fetchone()[0],
                "Keep Live Staff",
            )
            self.assertEqual(
                current.execute("SELECT COUNT(*) FROM punches WHERE user_id='101'").fetchone()[0],
                1,
            )

    def test_backup_rejects_hardlink_alias_to_live_database(self):
        self.add_current_record("101", "Keep Live Staff", "2026-11-16 09:00:00")
        alias = self.root / "attendance-hardlink.db"
        self.create_hardlink_or_skip(app.DB, alias)

        with (
            patch.object(app.filedialog, "asksaveasfilename", return_value=str(alias)),
            patch.object(app.messagebox, "showerror") as showerror,
            patch.object(app.messagebox, "showinfo") as showinfo,
        ):
            app.App.backup_database(self.ctx)

        showerror.assert_called_once()
        self.assertIn("live attendance database", str(showerror.call_args).lower())
        showinfo.assert_not_called()
        self.assertTrue(os.path.samefile(alias, app.DB))
        with sqlite3.connect(app.DB) as current:
            self.assertEqual(current.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(
                current.execute("SELECT name FROM staff WHERE user_id='101'").fetchone()[0],
                "Keep Live Staff",
            )
            self.assertEqual(
                current.execute("SELECT COUNT(*) FROM punches WHERE user_id='101'").fetchone()[0],
                1,
            )

    def test_restore_rejects_hardlink_alias_to_live_database_before_confirmation(self):
        self.add_current_record("101", "Keep Live Staff", "2026-11-16 09:00:00")
        alias = self.root / "attendance-restore-hardlink.db"
        self.create_hardlink_or_skip(app.DB, alias)

        with (
            patch.object(app.filedialog, "askopenfilename", return_value=str(alias)),
            patch.object(app.messagebox, "askyesno") as confirm,
            patch.object(app.messagebox, "showerror") as showerror,
        ):
            app.App.restore_database(self.ctx)

        confirm.assert_not_called()
        showerror.assert_called_once()
        self.assertIn("database currently in use", str(showerror.call_args).lower())
        self.assertTrue(os.path.samefile(alias, app.DB))
        with sqlite3.connect(app.DB) as current:
            self.assertEqual(current.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(
                current.execute("SELECT name FROM staff WHERE user_id='101'").fetchone()[0],
                "Keep Live Staff",
            )
            self.assertEqual(
                current.execute("SELECT COUNT(*) FROM punches WHERE user_id='101'").fetchone()[0],
                1,
            )

    def test_restore_aborts_if_atomic_safety_backup_cannot_be_created(self):
        self.add_current_record("old", "Keep Existing Staff", "2026-11-15 09:00:00")
        backup_path = self.root / "restore-source.db"
        with sqlite3.connect(backup_path) as backup:
            backup.execute(
                "CREATE TABLE staff(user_id TEXT PRIMARY KEY, name TEXT NOT NULL DEFAULT '')"
            )
            backup.execute(
                "CREATE TABLE punches(user_id TEXT NOT NULL, punch_time TEXT NOT NULL, status TEXT DEFAULT '', UNIQUE(user_id,punch_time,status))"
            )
            backup.execute("INSERT INTO staff(user_id,name) VALUES('new','Must Not Restore')")
            backup.execute(
                "INSERT INTO punches(user_id,punch_time,status) VALUES('new','2026-11-16 10:00:00','')"
            )

        with (
            patch.object(app.filedialog, "askopenfilename", return_value=str(backup_path)),
            patch.object(app.messagebox, "askyesno", return_value=True),
            patch.object(
                app,
                "write_database_backup",
                side_effect=OSError("simulated disk-full safety-backup failure"),
            ) as create_safety_backup,
            patch.object(app.messagebox, "showerror") as showerror,
            patch.object(app.messagebox, "showinfo") as showinfo,
        ):
            app.App.restore_database(self.ctx)

        create_safety_backup.assert_called_once()
        showerror.assert_called_once()
        showinfo.assert_not_called()
        self.assertIn("simulated disk-full", str(showerror.call_args))
        self.assertEqual(list(self.root.glob("Pre_Restore_Backup_*.db")), [])
        with sqlite3.connect(app.DB) as current:
            self.assertEqual(current.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(
                current.execute("SELECT name FROM staff WHERE user_id='old'").fetchone()[0],
                "Keep Existing Staff",
            )
            self.assertIsNone(
                current.execute("SELECT name FROM staff WHERE user_id='new'").fetchone()
            )
            self.assertEqual(current.execute("SELECT COUNT(*) FROM punches").fetchone()[0], 1)

    def test_restore_replaces_data_and_retains_pre_restore_safety_backup(self):
        self.add_current_record("old", "Old Staff", "2026-11-14 09:00:00")
        backup_path = self.root / "restore-source.db"
        with sqlite3.connect(backup_path) as backup:
            backup.execute(
                "CREATE TABLE staff(user_id TEXT PRIMARY KEY, name TEXT NOT NULL DEFAULT '')"
            )
            backup.execute(
                "CREATE TABLE punches(user_id TEXT NOT NULL, punch_time TEXT NOT NULL, status TEXT DEFAULT '', UNIQUE(user_id,punch_time,status))"
            )
            backup.execute(
                "INSERT INTO staff(user_id,name) VALUES('new','Restored Staff')"
            )
            backup.execute(
                "INSERT INTO punches(user_id,punch_time,status) VALUES('new','2026-11-15 10:00:00','')"
            )
            backup.execute("""CREATE TABLE staff_rules (
                user_id TEXT PRIMARY KEY, start_time TEXT NOT NULL DEFAULT '10:00',
                end_time TEXT NOT NULL DEFAULT '18:00', grace_minutes INTEGER NOT NULL DEFAULT 10,
                half_day_after TEXT NOT NULL DEFAULT '12:00', min_hours REAL NOT NULL DEFAULT 4.0
            )""")
            backup.execute("INSERT INTO staff_rules VALUES('new','08:30','17:30',5,'12:30',4.5)")
            backup.execute("CREATE TABLE app_settings(setting TEXT PRIMARY KEY,value TEXT NOT NULL)")
            backup.executemany(
                "INSERT INTO app_settings(setting,value) VALUES(?,?)",
                [("weekday_window_start","08:30"),("custom_theme","forest")],
            )
            backup.execute("CREATE TABLE holidays(holiday_date TEXT PRIMARY KEY,label TEXT NOT NULL DEFAULT '')")
            backup.execute("INSERT INTO holidays VALUES('2026-12-25','School Closure')")
            backup.execute("""CREATE TABLE staff_day_rules (
                user_id TEXT NOT NULL, weekday INTEGER NOT NULL, start_time TEXT NOT NULL,
                end_time TEXT NOT NULL, grace_minutes INTEGER NOT NULL DEFAULT 15,
                shift_type TEXT NOT NULL DEFAULT 'Full day', PRIMARY KEY(user_id,weekday)
            )""")
            backup.execute("INSERT INTO staff_day_rules VALUES('new',5,'09:00','14:00',10,'Half day')")
            backup.execute("""CREATE TABLE staff_leave (
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL,
                start_date TEXT NOT NULL, end_date TEXT NOT NULL,
                label TEXT NOT NULL DEFAULT 'Annual Leave'
            )""")
            backup.execute(
                "INSERT INTO staff_leave(user_id,start_date,end_date,label) VALUES('new','2026-12-28','2026-12-30','Annual Leave')"
            )

        with patch.object(app.filedialog, "askopenfilename", return_value=str(backup_path)), \
             patch.object(app.messagebox, "askyesno", return_value=True), \
             patch.object(app.messagebox, "showinfo") as showinfo, \
             patch.object(app.messagebox, "showerror") as showerror:
            app.App.restore_database(self.ctx)

        with sqlite3.connect(app.DB) as restored:
            self.assertEqual(
                restored.execute("SELECT name FROM staff WHERE user_id='new'").fetchone()[0],
                "Restored Staff",
            )
            self.assertIsNone(
                restored.execute("SELECT name FROM staff WHERE user_id='old'").fetchone()
            )
            self.assertEqual(restored.execute("SELECT COUNT(*) FROM punches").fetchone()[0], 1)
            self.assertEqual(
                restored.execute("SELECT * FROM staff_rules WHERE user_id='new'").fetchone(),
                ("new", "08:30", "17:30", 5, "12:30", 4.5),
            )
            self.assertEqual(
                restored.execute("SELECT value FROM app_settings WHERE setting='weekday_window_start'").fetchone(),
                ("08:30",),
            )
            self.assertEqual(
                restored.execute("SELECT value FROM app_settings WHERE setting='custom_theme'").fetchone(),
                ("forest",),
            )
            self.assertEqual(
                restored.execute("SELECT * FROM holidays WHERE holiday_date='2026-12-25'").fetchone(),
                ("2026-12-25", "School Closure"),
            )
            self.assertEqual(
                restored.execute("SELECT * FROM staff_day_rules WHERE user_id='new' AND weekday=5").fetchone(),
                ("new", 5, "09:00", "14:00", 10, "Half day"),
            )
            self.assertEqual(
                restored.execute("SELECT user_id,start_date,end_date,label FROM staff_leave WHERE user_id='new'").fetchone(),
                ("new", "2026-12-28", "2026-12-30", "Annual Leave"),
            )
        safety_backups = list(self.root.glob("Pre_Restore_Backup_*.db"))
        self.assertEqual(len(safety_backups), 1)
        with sqlite3.connect(safety_backups[0]) as safety:
            self.assertEqual(
                safety.execute("SELECT name FROM staff WHERE user_id='old'").fetchone()[0],
                "Old Staff",
            )
        showinfo.assert_called_once()
        showerror.assert_not_called()

    def test_restore_uses_the_validated_snapshot_if_selected_file_changes_after_confirmation(self):
        self.add_current_record("old", "Old Staff", "2026-11-14 09:00:00")
        backup_path = self.root / "restore-source.db"
        replacement_path = self.root / "replacement.db"

        def create_backup(path, user_id, name, stamp):
            with sqlite3.connect(path) as backup:
                backup.execute(
                    "CREATE TABLE staff(user_id TEXT PRIMARY KEY, name TEXT NOT NULL DEFAULT '')"
                )
                backup.execute(
                    "CREATE TABLE punches(user_id TEXT NOT NULL, punch_time TEXT NOT NULL, status TEXT DEFAULT '', UNIQUE(user_id,punch_time,status))"
                )
                backup.execute("INSERT INTO staff(user_id,name) VALUES(?,?)", (user_id, name))
                backup.execute(
                    "INSERT INTO punches(user_id,punch_time,status) VALUES(?,?,?)",
                    (user_id, stamp, ""),
                )

        create_backup(backup_path, "new", "Original Backup", "2026-11-15 10:00:00")
        create_backup(replacement_path, "injected", "Replacement File", "2026-11-16 10:00:00")

        def replace_selected_file_after_validation(*_args, **_kwargs):
            os.replace(replacement_path, backup_path)
            return True

        with (
            patch.object(app.filedialog, "askopenfilename", return_value=str(backup_path)),
            patch.object(app.messagebox, "askyesno", side_effect=replace_selected_file_after_validation),
            patch.object(app.messagebox, "showinfo") as showinfo,
            patch.object(app.messagebox, "showerror") as showerror,
        ):
            app.App.restore_database(self.ctx)

        with sqlite3.connect(app.DB) as restored:
            self.assertEqual(
                restored.execute("SELECT user_id,name FROM staff").fetchall(),
                [("new", "Original Backup")],
            )
            self.assertEqual(
                restored.execute("SELECT user_id,punch_time,status FROM punches").fetchall(),
                [("new", "2026-11-15 10:00:00", "")],
            )
        self.assertEqual(list(self.root.glob("scafa-restore-*")), [])
        self.assertEqual(list(self.root.glob("Pre_Restore_Backup_*.db"))[0].exists(), True)
        showinfo.assert_called_once()
        showerror.assert_not_called()

    def test_restore_rejects_database_without_required_tables(self):
        self.add_current_record("101", "Keep This Staff", "2026-11-15 09:00:00")
        invalid_path = self.root / "not-an-attendance-backup.db"
        with sqlite3.connect(invalid_path) as invalid:
            invalid.execute("CREATE TABLE unrelated(value TEXT)")

        with (
            patch.object(app.filedialog, "askopenfilename", return_value=str(invalid_path)),
            patch.object(app.messagebox, "askyesno") as confirm,
            patch.object(app.messagebox, "showerror") as showerror,
        ):
            app.App.restore_database(self.ctx)

        confirm.assert_not_called()
        showerror.assert_called_once()
        with sqlite3.connect(app.DB) as current:
            self.assertEqual(
                current.execute("SELECT name FROM staff WHERE user_id='101'").fetchone()[0],
                "Keep This Staff",
            )
            self.assertEqual(current.execute("SELECT COUNT(*) FROM punches").fetchone()[0], 1)


    def test_restore_rejects_incompatible_columns_before_confirmation(self):
        self.add_current_record("101", "Keep This Staff", "2026-11-15 09:00:00")
        invalid_path = self.root / "incompatible-schema.db"
        with sqlite3.connect(invalid_path) as invalid:
            invalid.execute("CREATE TABLE staff(user_id TEXT PRIMARY KEY, display_name TEXT)")
            invalid.execute("CREATE TABLE punches(user_id TEXT, recorded_at TEXT, state TEXT)")

        with (
            patch.object(app.filedialog, "askopenfilename", return_value=str(invalid_path)),
            patch.object(app.messagebox, "askyesno") as confirm,
            patch.object(app.messagebox, "showerror") as showerror,
        ):
            app.App.restore_database(self.ctx)

        confirm.assert_not_called()
        showerror.assert_called_once()
        with sqlite3.connect(app.DB) as current:
            self.assertEqual(
                current.execute("SELECT name FROM staff WHERE user_id='101'").fetchone()[0],
                "Keep This Staff",
            )
            self.assertEqual(current.execute("SELECT COUNT(*) FROM punches").fetchone()[0], 1)

    def test_restore_rejects_missing_punch_uniqueness_before_confirmation(self):
        self.add_current_record("101", "Keep This Staff", "2026-11-15 09:00:00")
        invalid_path = self.root / "duplicate-prone-schema.db"
        with sqlite3.connect(invalid_path) as invalid:
            invalid.execute("CREATE TABLE staff(user_id TEXT PRIMARY KEY, name TEXT NOT NULL)")
            invalid.execute("CREATE TABLE punches(user_id TEXT NOT NULL, punch_time TEXT NOT NULL, status TEXT DEFAULT '')")

        with (
            patch.object(app.filedialog, "askopenfilename", return_value=str(invalid_path)),
            patch.object(app.messagebox, "askyesno") as confirm,
            patch.object(app.messagebox, "showerror") as showerror,
        ):
            app.App.restore_database(self.ctx)

        confirm.assert_not_called()
        showerror.assert_called_once()
        self.assertIn("duplicate attendance punch", str(showerror.call_args))
        with sqlite3.connect(app.DB) as current:
            self.assertEqual(
                current.execute("SELECT name FROM staff WHERE user_id='101'").fetchone()[0],
                "Keep This Staff",
            )
            self.assertEqual(current.execute("SELECT COUNT(*) FROM punches").fetchone()[0], 1)

    def test_restore_rejects_incomplete_optional_schedule_schema_before_confirmation(self):
        self.add_current_record("101", "Keep This Staff", "2026-11-15 09:00:00")
        invalid_path = self.root / "incomplete-schedule.db"
        with sqlite3.connect(invalid_path) as invalid:
            invalid.execute("CREATE TABLE staff(user_id TEXT PRIMARY KEY, name TEXT NOT NULL)")
            invalid.execute("CREATE TABLE punches(user_id TEXT NOT NULL, punch_time TEXT NOT NULL, status TEXT DEFAULT '', UNIQUE(user_id,punch_time,status))")
            invalid.execute("CREATE TABLE staff_rules(user_id TEXT PRIMARY KEY, start_time TEXT)")

        with (
            patch.object(app.filedialog, "askopenfilename", return_value=str(invalid_path)),
            patch.object(app.messagebox, "askyesno") as confirm,
            patch.object(app.messagebox, "showerror") as showerror,
        ):
            app.App.restore_database(self.ctx)

        confirm.assert_not_called()
        showerror.assert_called_once()
        self.assertIn("incomplete staff_rules table", str(showerror.call_args))
        with sqlite3.connect(app.DB) as current:
            self.assertEqual(
                current.execute("SELECT name FROM staff WHERE user_id='101'").fetchone()[0],
                "Keep This Staff",
            )
            self.assertEqual(current.execute("SELECT COUNT(*) FROM punches").fetchone()[0], 1)


    def test_restore_rejects_non_unique_optional_schedule_records_before_confirmation(self):
        self.add_current_record("101", "Keep This Staff", "2026-11-15 09:00:00")
        invalid_path = self.root / "non-unique-schedule.db"
        with sqlite3.connect(invalid_path) as invalid:
            invalid.execute("CREATE TABLE staff(user_id TEXT PRIMARY KEY, name TEXT NOT NULL)")
            invalid.execute("CREATE TABLE punches(user_id TEXT NOT NULL, punch_time TEXT NOT NULL, status TEXT DEFAULT '', UNIQUE(user_id,punch_time,status))")
            invalid.execute("""CREATE TABLE staff_day_rules (
                user_id TEXT NOT NULL, weekday INTEGER NOT NULL, start_time TEXT NOT NULL,
                end_time TEXT NOT NULL, grace_minutes INTEGER NOT NULL DEFAULT 15,
                shift_type TEXT NOT NULL DEFAULT 'Full day'
            )""")

        with (
            patch.object(app.filedialog, "askopenfilename", return_value=str(invalid_path)),
            patch.object(app.messagebox, "askyesno") as confirm,
            patch.object(app.messagebox, "showerror") as showerror,
        ):
            app.App.restore_database(self.ctx)

        confirm.assert_not_called()
        showerror.assert_called_once()
        self.assertIn("unique staff_day_rules records", str(showerror.call_args))
        with sqlite3.connect(app.DB) as current:
            self.assertEqual(
                current.execute("SELECT name FROM staff WHERE user_id='101'").fetchone()[0],
                "Keep This Staff",
            )
            self.assertEqual(current.execute("SELECT COUNT(*) FROM punches").fetchone()[0], 1)



if __name__ == "__main__":
    unittest.main()
