import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import app


class AttendanceStatusTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_db = app.DB
        app.DB = Path(self.temp.name) / "attendance.db"
        app.init_db()
        self.ctx = SimpleNamespace()
        self.ctx._rules = lambda: app.App._rules(self.ctx)

    def tearDown(self):
        app.DB = self.old_db
        self.temp.cleanup()

    def status(self, uid, day, stamps):
        return app.App._attendance_day_status(self.ctx, uid, day, stamps)[0]

    def test_scheduled_workday_without_punches_is_absent(self):
        self.assertEqual(self.status("1", "2026-10-26", []), "Absent")  # Monday

    def test_sunday_defaults_to_day_off(self):
        self.assertEqual(self.status("1", "2026-11-01", []), "Day off")  # Sunday

    def test_late_single_punch_is_flagged_incomplete_and_late(self):
        status = self.status("1", "2026-10-26", ["2026-10-26 10:10:00"])
        self.assertEqual(status, "Incomplete punch — Late")

    def test_single_punch_within_grace_is_incomplete_not_late(self):
        status = self.status("1", "2026-10-26", ["2026-10-26 09:55:00"])
        self.assertEqual(status, "Incomplete punch")

    def test_holiday_takes_precedence_over_missing_punches(self):
        with __import__("sqlite3").connect(app.DB) as c:
            c.execute("INSERT INTO holidays(holiday_date,label) VALUES(?,?)", ("2026-10-26", "Test holiday"))
        self.assertEqual(self.status("1", "2026-10-26", []), "Holiday")

    def test_explicit_staff_day_off_overrides_global_workweek(self):
        with __import__("sqlite3").connect(app.DB) as c:
            c.execute(
                "INSERT INTO staff_day_rules(user_id,weekday,start_time,end_time,grace_minutes,shift_type) VALUES(?,?,?,?,?,?)",
                ("1", 0, "09:45", "20:00", 15, "Off"),
            )
        self.assertEqual(self.status("1", "2026-10-26", []), "Day off")


if __name__ == "__main__":
    unittest.main()
