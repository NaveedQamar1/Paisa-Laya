import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import app


class ScheduleLeaveRegressionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self.temp.name)
        self.old_db = app.DB
        self.old_base = app.BASE
        app.BASE = self.root
        app.DB = self.root / "attendance.db"
        app.init_db()
        with sqlite3.connect(app.DB) as db:
            db.executemany(
                "INSERT INTO staff(user_id,name,active) VALUES(?,?,1)",
                [("701", "Mariam"), ("702", "Bilal")],
            )

    def tearDown(self):
        app.DB = self.old_db
        app.BASE = self.old_base
        self.temp.cleanup()

    def add_leave(self, uid="701", first="2026-11-16", last="2026-11-16", label="Annual Leave"):
        with sqlite3.connect(app.DB) as db:
            return app.add_employee_leave(db, uid, first, last, label)

    def attendance_context(self):
        ctx = SimpleNamespace()
        ctx._rules = lambda: app.App._rules(ctx)
        return ctx

    def status(self, uid, day, stamps=None):
        ctx = self.attendance_context()
        return app.App._attendance_day_status(ctx, uid, day, stamps or [])

    def test_add_leave_saves_normalized_employee_date_range_and_reason(self):
        record_id = self.add_leave(first="2026-11-16", last="2026-11-18", label="Sick Leave")
        with sqlite3.connect(app.DB) as db:
            record = db.execute(
                "SELECT id,user_id,start_date,end_date,label FROM staff_leave WHERE id=?",
                (record_id,),
            ).fetchone()
        self.assertEqual(record, (record_id, "701", "2026-11-16", "2026-11-18", "Sick Leave"))

    def test_overlapping_leave_period_is_rejected_without_adding_a_second_record(self):
        self.add_leave(first="2026-11-16", last="2026-11-18", label="Annual Leave")
        with self.assertRaisesRegex(ValueError, "overlaps an existing Annual Leave period"):
            self.add_leave(first="2026-11-18", last="2026-11-20", label="Sick Leave")
        with sqlite3.connect(app.DB) as db:
            self.assertEqual(
                db.execute("SELECT COUNT(*) FROM staff_leave WHERE user_id='701'").fetchone()[0],
                1,
            )

    def test_adjacent_non_overlapping_leave_periods_are_allowed(self):
        self.add_leave(first="2026-11-16", last="2026-11-18")
        self.add_leave(first="2026-11-19", last="2026-11-20", label="Training")
        with sqlite3.connect(app.DB) as db:
            periods = db.execute(
                "SELECT start_date,end_date,label FROM staff_leave WHERE user_id='701' ORDER BY start_date"
            ).fetchall()
        self.assertEqual(periods, [
            ("2026-11-16", "2026-11-18", "Annual Leave"),
            ("2026-11-19", "2026-11-20", "Training"),
        ])

    def test_invalid_or_reversed_leave_dates_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "YYYY-MM-DD"):
            self.add_leave(first="16/11/2026", last="2026-11-18")
        with self.assertRaisesRegex(ValueError, "must not be before"):
            self.add_leave(first="2026-11-20", last="2026-11-19")
        with sqlite3.connect(app.DB) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM staff_leave").fetchone()[0], 0)

    def test_leave_period_longer_than_367_days_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "cannot exceed 367 days"):
            self.add_leave(first="2026-01-01", last="2027-01-02")

    def test_leave_requires_a_registered_employee(self):
        with self.assertRaisesRegex(ValueError, "no longer registered"):
            self.add_leave(uid="999")
        with sqlite3.connect(app.DB) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM staff_leave").fetchone()[0], 0)

    def test_leave_excludes_only_the_selected_employee_from_absence(self):
        self.add_leave(uid="701", first="2026-11-16", last="2026-11-16")
        self.assertEqual(
            self.status("701", "2026-11-16")[0],
            "On leave — Annual Leave",
        )
        self.assertEqual(self.status("702", "2026-11-16")[0], "Absent")

    def test_public_holiday_overrides_scheduled_absence(self):
        with sqlite3.connect(app.DB) as db:
            db.execute(
                "INSERT INTO holidays(holiday_date,label) VALUES('2026-11-16','School Closure')"
            )
        self.assertEqual(self.status("701", "2026-11-16")[0], "Holiday")
        self.assertEqual(self.status("702", "2026-11-16")[0], "Holiday")

    def test_employee_day_off_override_takes_precedence_over_global_workweek(self):
        with sqlite3.connect(app.DB) as db:
            db.execute(
                """INSERT INTO staff_day_rules(user_id,weekday,start_time,end_time,grace_minutes,shift_type)
                   VALUES('701',0,'09:00','18:00',10,'Off')"""
            )
        self.assertEqual(self.status("701", "2026-11-16")[0], "Day off")
        self.assertEqual(self.status("702", "2026-11-16")[0], "Absent")

    def test_employee_half_day_override_is_applied_to_actual_punches(self):
        with sqlite3.connect(app.DB) as db:
            db.execute(
                """INSERT INTO staff_day_rules(user_id,weekday,start_time,end_time,grace_minutes,shift_type)
                   VALUES('701',1,'09:00','13:00',5,'Half day')"""
            )
        status, first, last, worked = self.status(
            "701", "2026-11-17",
            ["2026-11-17 09:00:00", "2026-11-17 13:00:00"],
        )
        self.assertEqual((status, first, last, worked), ("Half-day", "09:00", "13:00", 4.0))


if __name__ == "__main__":
    unittest.main()
