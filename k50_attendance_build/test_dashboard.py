import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import app


class FakeTree:
    def __init__(self):
        self.deleted = []
        self.rows = []

    def get_children(self):
        return ("old-row",)

    def delete(self, item):
        self.deleted.append(item)

    def insert(self, parent, index, values, tags):
        self.rows.append((values, tags))


class FakeLabel:
    def __init__(self):
        self.text = None

    def configure(self, **kwargs):
        self.text = kwargs.get("text", self.text)


class DashboardRegressionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self.temp.name)
        self.old_db = app.DB
        self.old_base = app.BASE
        app.BASE = self.root
        app.DB = self.root / "attendance.db"
        app.init_db()
        with sqlite3.connect(app.DB) as db:
            db.execute(
                "INSERT INTO staff(user_id,name,active) VALUES('101','Ayesha',1)"
            )
            db.execute(
                "INSERT INTO staff(user_id,name,active) VALUES('102','Bilal',0)"
            )
            db.execute(
                "INSERT INTO staff_status_history(user_id,active,effective_date,source) VALUES('101',1,'2020-01-01','test')"
            )
            db.execute(
                "INSERT INTO staff_status_history(user_id,active,effective_date,source) VALUES('102',1,'2020-01-01','test')"
            )
            db.execute(
                "INSERT INTO staff_status_history(user_id,active,effective_date,source) VALUES('102',0,'2026-11-08','test')"
            )

    def tearDown(self):
        app.DB = self.old_db
        app.BASE = self.old_base
        self.temp.cleanup()

    def test_dashboard_does_not_count_device_employee_before_first_punch(self):
        with sqlite3.connect(app.DB) as db:
            db.execute(
                "INSERT INTO staff(user_id,name,active) VALUES('103','New Device Hire',1)"
            )
            app.ensure_device_employee_status_history(
                db, "103", "2026-11-09", effective_today="2026-11-16"
            )

        ctx = SimpleNamespace(
            comparison_tree=FakeTree(),
            dashboard_employee=SimpleNamespace(get=lambda: "All staff"),
            latest_punch_label=FakeLabel(),
            start_date=SimpleNamespace(get=lambda: "2026-11-08"),
            end_date=SimpleNamespace(get=lambda: "2026-11-09"),
            card_values=[FakeLabel() for _ in range(6)],
        )
        ctx._name = lambda uid: {"103": "New Device Hire"}.get(str(uid), f"User {uid}")
        ctx._rules = lambda: app.App._rules(ctx)
        ctx._attendance_day_status = lambda uid, day, stamps: app.App._attendance_day_status(
            ctx, uid, day, stamps
        )
        rows = [
            ("103", "2026-11-09 09:45:00", "0"),
            ("103", "2026-11-09 18:00:00", "1"),
        ]

        app.App._update_dashboard(ctx, rows)

        values_by_employee = {values[0]: values for values, tags in ctx.comparison_tree.rows}
        self.assertEqual(
            values_by_employee["New Device Hire"],
            ("New Device Hire", 1, 1, 0, 0, 0, 1, "100.0%", "09:45"),
        )
        self.assertEqual(ctx.card_values[0].text, "100.0%")

    def test_dashboard_excludes_inactive_employee_days_and_keeps_latest_punch(self):
        ctx = SimpleNamespace(
            comparison_tree=FakeTree(),
            dashboard_employee=SimpleNamespace(get=lambda: "All staff"),
            latest_punch_label=FakeLabel(),
            start_date=SimpleNamespace(get=lambda: "2026-11-09"),
            end_date=SimpleNamespace(get=lambda: "2026-11-09"),
            card_values=[FakeLabel() for _ in range(6)],
        )
        ctx._name = lambda uid: {"101": "Ayesha", "102": "Bilal"}.get(str(uid), f"User {uid}")
        ctx._rules = lambda: app.App._rules(ctx)
        ctx._attendance_day_status = lambda uid, day, stamps: app.App._attendance_day_status(
            ctx, uid, day, stamps
        )
        rows = [
            ("101", "2026-11-09 09:45:00", "0"),
            ("101", "2026-11-09 18:00:00", "1"),
        ]

        app.App._update_dashboard(ctx, rows)

        self.assertEqual(
            [label.text for label in ctx.card_values],
            ["100.0%", "0", "1", "0", "0", "09:45"],
        )
        self.assertIn("Ayesha  (ID 101)", ctx.latest_punch_label.text)
        values_by_employee = {values[0]: values for values, tags in ctx.comparison_tree.rows}
        self.assertEqual(
            values_by_employee["Ayesha"],
            ("Ayesha", 1, 1, 0, 1, 0, 1, "100.0%", "09:45"),
        )
        self.assertEqual(
            values_by_employee["Bilal"],
            ("Bilal", 0, 0, 0, 0, 0, 0, "0.0%", "—"),
        )


if __name__ == "__main__":
    unittest.main()
