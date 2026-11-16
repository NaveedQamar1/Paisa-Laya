import sqlite3
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import monitor


class MonitorStateTests(unittest.TestCase):
    def test_device_sync_initializes_employment_history_from_punch_or_sync_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            database = Path(tmp) / "attendance.db"
            with sqlite3.connect(database) as db:
                db.execute(
                    """CREATE TABLE staff(
                       user_id TEXT PRIMARY KEY,name TEXT NOT NULL DEFAULT '',
                       joining_date TEXT NOT NULL DEFAULT '',active INTEGER NOT NULL DEFAULT 1)"""
                )
                db.execute(
                    """CREATE TABLE punches(
                       user_id TEXT NOT NULL,punch_time TEXT NOT NULL,status TEXT DEFAULT '',
                       UNIQUE(user_id,punch_time,status))"""
                )
                db.execute(
                    """CREATE TABLE staff_status_history(
                       id INTEGER PRIMARY KEY AUTOINCREMENT,user_id TEXT NOT NULL,
                       active INTEGER NOT NULL,effective_date TEXT NOT NULL,
                       source TEXT NOT NULL,UNIQUE(user_id,effective_date))"""
                )
                users = [
                    SimpleNamespace(user_id=101, name="Ayesha"),
                    SimpleNamespace(user_id=102, name="Bilal"),
                ]
                records = [
                    SimpleNamespace(
                        user_id=101,
                        timestamp=datetime(2026, 11, 15, 9, 0, 0),
                        status=0,
                    )
                ]

                inserted = monitor.sync_device_records(db, users, records)
                today = monitor.datetime.now().date().isoformat()
                history_101 = db.execute(
                    """SELECT active,effective_date,source FROM staff_status_history
                       WHERE user_id='101' ORDER BY effective_date,id"""
                ).fetchall()
                history_102 = db.execute(
                    """SELECT active,effective_date,source FROM staff_status_history
                       WHERE user_id='102' ORDER BY effective_date,id"""
                ).fetchall()

            self.assertEqual(inserted, [("2026-11-15 09:00:00", "101", "0", "Ayesha")])
            self.assertEqual(
                history_101,
                [
                    (0, "0001-01-01", "device-sync-baseline"),
                    (1, "2026-11-15", "device-sync"),
                ],
            )
            self.assertEqual(
                history_102,
                [
                    (0, "0001-01-01", "device-sync-baseline"),
                    (1, today, "device-sync"),
                ],
            )


    def test_seen_punches_persist_across_restarts(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "monitor-state.json"
            seen = {
                ("2026-11-11 09:00:00", "101", "0"),
                ("2026-11-11 17:00:00", "101", "1"),
            }
            with patch.object(monitor, "STATE", state):
                monitor.save_state("192.168.1.50:4370", seen)
                self.assertEqual(monitor.load_state("192.168.1.50:4370"), seen)

    def test_state_is_not_reused_for_a_different_device(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "monitor-state.json"
            with patch.object(monitor, "STATE", state):
                monitor.save_state("192.168.1.50:4370", {
                    ("2026-11-11 09:00:00", "101", "0")
                })
                self.assertIsNone(monitor.load_state("192.168.1.51:4370"))



class MonitorNotificationTests(unittest.TestCase):
    def sample_event(self):
        return [("2026-11-15 09:00:00", "101", "0", "Ayesha")]

    def test_first_poll_establishes_baseline_without_historical_notifications(self):
        inserted = self.sample_event()
        with patch.object(monitor, "notify") as notify:
            seen = monitor.notify_new_punches(inserted, None)
        self.assertEqual(seen, {("2026-11-15 09:00:00", "101", "0")})
        notify.assert_not_called()

    def test_failed_notification_remains_unseen_and_is_retried(self):
        inserted = self.sample_event()
        key = ("2026-11-15 09:00:00", "101", "0")
        with patch.object(
            monitor, "notify", side_effect=[RuntimeError("notification permission denied"), None]
        ) as notify, patch.object(monitor, "log_error") as log_error:
            seen = monitor.notify_new_punches(inserted, set())
            self.assertNotIn(key, seen)
            seen = monitor.notify_new_punches(inserted, seen)
        self.assertIn(key, seen)
        self.assertEqual(notify.call_count, 2)
        log_error.assert_called_once()

    def test_successfully_notified_punch_is_not_repeated(self):
        inserted = self.sample_event()
        with patch.object(monitor, "notify") as notify:
            seen = monitor.notify_new_punches(inserted, set())
            seen = monitor.notify_new_punches(inserted, seen)
        self.assertEqual(seen, {("2026-11-15 09:00:00", "101", "0")})
        notify.assert_called_once()

    def test_empty_first_poll_is_persisted_so_first_later_punch_notifies(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "monitor-state.json"
            device = "192.168.1.50:4370"
            with patch.object(monitor, "STATE", state):
                baseline = monitor.initial_seen_punches([])
                monitor.save_state(device, baseline)
                loaded = monitor.load_state(device)
                self.assertEqual(loaded, set())
                with patch.object(monitor, "notify") as notify:
                    seen = monitor.notify_new_punches(self.sample_event(), loaded)
            self.assertIn(("2026-11-15 09:00:00", "101", "0"), seen)
            notify.assert_called_once()


if __name__ == "__main__":
    unittest.main()
