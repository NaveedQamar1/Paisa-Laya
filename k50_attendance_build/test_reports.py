import csv
import re
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import app


class ReportExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self.temp.name)
        self.old_db = app.DB
        self.old_base = app.BASE
        app.BASE = self.root
        app.DB = self.root / "attendance.db"
        app.init_db()
        with sqlite3.connect(app.DB) as db:
            for uid, name in (("101", "Ayesha"), ("102", "Bilal")):
                db.execute(
                    "INSERT INTO staff(user_id,name,active) VALUES(?,?,1)",
                    (uid, name),
                )
                db.execute(
                    "INSERT INTO staff_status_history(user_id,active,effective_date,source) VALUES(?,1,'2020-01-01','test')",
                    (uid,),
                )
        self.rows = [
            ("101", "2026-11-09 09:45:00", "0"),
            ("101", "2026-11-09 18:00:00", "1"),
        ]

    def tearDown(self):
        app.DB = self.old_db
        app.BASE = self.old_base
        self.temp.cleanup()

    def context(self, rows=None):
        ctx = SimpleNamespace(
            _rows=lambda: list(self.rows if rows is None else rows),
            _names_cache=None,
            report_user=SimpleNamespace(get=lambda: "All staff"),
            start_date=SimpleNamespace(get=lambda: "2026-11-09"),
            end_date=SimpleNamespace(get=lambda: "2026-11-09"),
        )
        ctx._name = lambda uid: {"101": "Ayesha", "102": "Bilal"}.get(str(uid), f"User {uid}")
        ctx._rules = lambda: app.App._rules(ctx)
        ctx._attendance_day_status = lambda uid, day, stamps: app.App._attendance_day_status(
            ctx, uid, day, stamps
        )
        ctx._report_scope_rows = lambda: app.App._report_scope_rows(ctx)
        ctx._make_pdf = lambda *args: app.App._make_pdf(ctx, *args)
        return ctx

    def test_csv_export_keeps_device_ids_names_and_raw_punches(self):
        destination = self.root / "attendance.csv"
        ctx = self.context()
        with patch.object(app.filedialog, "asksaveasfilename", return_value=str(destination)), \
             patch.object(app.messagebox, "showinfo") as showinfo:
            app.App.export_csv(ctx)

        with destination.open("r", encoding="utf-8-sig", newline="") as handle:
            exported = list(csv.reader(handle))
        self.assertEqual(
            exported[0],
            ["Device User ID", "Staff Name", "Attendance date & time", "Punch status"],
        )
        self.assertEqual(exported[1], ["101", "Ayesha", "2026-11-09 09:45:00", "0"])
        self.assertEqual(exported[2], ["101", "Ayesha", "2026-11-09 18:00:00", "1"])
        showinfo.assert_called_once()

    def test_excel_export_contains_summary_raw_punches_and_employee_comparison(self):
        from openpyxl import load_workbook

        destination = self.root / "attendance.xlsx"
        ctx = self.context()
        with patch.object(app.filedialog, "asksaveasfilename", return_value=str(destination)), \
             patch.object(app.messagebox, "showinfo") as showinfo, \
             patch.object(app.messagebox, "showerror") as showerror:
            app.App.export_excel(ctx)

        showinfo.assert_called_once()
        showerror.assert_not_called()
        workbook = load_workbook(destination, data_only=True)
        self.assertEqual(
            workbook.sheetnames,
            ["Overview", "Attendance Summary", "Raw Punches", "Employee Comparison"],
        )
        raw = workbook["Raw Punches"]
        self.assertEqual(raw.max_row, 3)
        self.assertEqual([raw.cell(2, col).value for col in range(1, 5)],
                         ["101", "Ayesha", "2026-11-09 09:45:00", "0"])
        comparison = workbook["Employee Comparison"]
        employees = {
            str(row[1].value): row
            for row in comparison.iter_rows(min_row=2)
        }
        self.assertEqual(employees["101"][2].value, 1)
        self.assertEqual(employees["101"][3].value, 1)
        self.assertEqual(employees["102"][2].value, 1)
        self.assertEqual(employees["102"][6].value, 1)
        workbook.close()

    def test_collective_pdf_creates_summary_and_individual_employee_pages(self):
        destination = self.root / "attendance.pdf"
        ctx = self.context()
        with patch.object(app.filedialog, "asksaveasfilename", return_value=str(destination)), \
             patch.object(app.messagebox, "showinfo") as showinfo, \
             patch.object(app.messagebox, "showerror") as showerror:
            app.App.export_pdf(ctx)

        showinfo.assert_called_once()
        showerror.assert_not_called()
        pdf = destination.read_bytes()
        self.assertTrue(pdf.startswith(b"%PDF-"))
        page_count = len(re.findall(rb"/Type\s*/Page\b", pdf))
        self.assertGreaterEqual(page_count, 3)


if __name__ == "__main__":
    unittest.main()
