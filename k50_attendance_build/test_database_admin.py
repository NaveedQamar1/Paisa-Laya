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
        safety_backups = list(self.root.glob("Pre_Restore_Backup_*.db"))
        self.assertEqual(len(safety_backups), 1)
        with sqlite3.connect(safety_backups[0]) as safety:
            self.assertEqual(
                safety.execute("SELECT name FROM staff WHERE user_id='old'").fetchone()[0],
                "Old Staff",
            )
        showinfo.assert_called_once()
        showerror.assert_not_called()

    def test_restore_rejects_database_without_required_tables(self):
        self.add_current_record("101", "Keep This Staff", "2026-11-15 09:00:00")
        invalid_path = self.root / "not-an-attendance-backup.db"
        with sqlite3.connect(invalid_path) as invalid:
            invalid.execute("CREATE TABLE unrelated(value TEXT)")

        with patch.object(app.filedialog, "askopenfilename", return_value=str(invalid_path)), \
             patch.object(app.messagebox, "askyesno") as confirm, \
             patch.object(app.messagebox, "showerror") as showerror:
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

        with patch.object(app.filedialog, "askopenfilename", return_value=str(invalid_path)), \\
             patch.object(app.messagebox, "askyesno") as confirm, \\
             patch.object(app.messagebox, "showerror") as showerror:
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

        with patch.object(app.filedialog, "askopenfilename", return_value=str(invalid_path)), \\
             patch.object(app.messagebox, "askyesno") as confirm, \\
             patch.object(app.messagebox, "showerror") as showerror:
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


if __name__ == "__main__":
    unittest.main()
