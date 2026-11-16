import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import monitor


class MonitorStateTests(unittest.TestCase):
    def test_device_sync_initializes_employment_history_from_punch_or_sync_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            database = Path(tmp) / "attendance.db"
            with closing(sqlite3.connect(database)) as db, db:
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


    def test_device_sync_preserves_zero_device_id_and_missing_id_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            database = Path(tmp) / "attendance.db"
            with closing(sqlite3.connect(database)) as db, db:
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
                    SimpleNamespace(user_id=0, uid=999, name="Zero ID"),
                    SimpleNamespace(user_id=None, uid=7, name="Fallback ID"),
                ]
                records = [
                    SimpleNamespace(
                        user_id=0,
                        timestamp=datetime(2026, 11, 15, 8, 0, 0),
                        status=0,
                    )
                ]

                inserted = monitor.sync_device_records(db, users, records)
                staff = db.execute(
                    "SELECT user_id,name FROM staff ORDER BY user_id"
                ).fetchall()
                history = db.execute(
                    """SELECT active,effective_date,source FROM staff_status_history
                       WHERE user_id='0' ORDER BY effective_date,id"""
                ).fetchall()

            self.assertEqual(
                inserted,
                [("2026-11-15 08:00:00", "0", "0", "Zero ID")],
            )
            self.assertEqual(staff, [("0", "Zero ID"), ("7", "Fallback ID")])
            self.assertEqual(
                history,
                [
                    (0, "0001-01-01", "device-sync-baseline"),
                    (1, "2026-11-15", "device-sync"),
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

    def test_malformed_state_document_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "monitor-state.json"
            invalid_documents = (
                "[]",
                "null",
                "42",
                '"not-an-object"',
                '{"device": "192.168.1.50:4370", "seen": "not-a-list"}',
            )
            with patch.object(monitor, "STATE", state):
                for document in invalid_documents:
                    with self.subTest(document=document):
                        state.write_text(document, encoding="utf-8")
                        self.assertIsNone(monitor.load_state("192.168.1.50:4370"))

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


    def test_record_key_rejects_missing_device_ids_and_invalid_timestamps(self):
        self.assertIsNone(monitor.record_key(SimpleNamespace(
            user_id=None, uid="", timestamp=datetime(2026, 11, 16, 9, 0, 0), status=0
        )))
        self.assertIsNone(monitor.record_key(SimpleNamespace(
            user_id=101, timestamp="not-a-timestamp", status=0
        )))
        self.assertEqual(
            monitor.record_key(SimpleNamespace(
                user_id=0,
                uid=999,
                timestamp="2026-11-16T09:00:00",
                status=0,
            )),
            ("2026-11-16 09:00:00", "0", "0"),
        )
        self.assertEqual(
            monitor.record_key(SimpleNamespace(
                user_id="   ",
                uid=8,
                timestamp="2026-11-16T09:30:00",
                status=0,
            )),
            ("2026-11-16 09:30:00", "8", "0"),
        )

    def test_valid_device_records_filters_bad_rows_and_sorts_valid_punches(self):
        valid_late = SimpleNamespace(
            user_id=101,
            timestamp=datetime(2026, 11, 16, 17, 0, 0),
            status=1,
        )
        valid_early = SimpleNamespace(
            user_id=0,
            uid=999,
            timestamp=datetime(2026, 11, 16, 9, 0, 0),
            status=0,
        )
        invalid_id = SimpleNamespace(
            user_id=None,
            uid="",
            timestamp=datetime(2026, 11, 16, 10, 0, 0),
            status=0,
        )
        invalid_time = SimpleNamespace(user_id=101, timestamp=None, status=1)

        valid, skipped = monitor.valid_device_records([
            valid_late, invalid_id, invalid_time, valid_early
        ])

        self.assertEqual(valid, [valid_early, valid_late])
        self.assertEqual(skipped, 2)

    def test_device_sync_skips_malformed_punch_rows_and_keeps_valid_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            database = Path(tmp) / "attendance.db"
            with closing(sqlite3.connect(database)) as db, db:
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
                users = [SimpleNamespace(user_id=0, name="Zero ID")]
                valid = SimpleNamespace(
                    user_id=0,
                    timestamp=datetime(2026, 11, 16, 9, 0, 0),
                    status=0,
                )
                invalid = SimpleNamespace(
                    user_id=None,
                    uid="",
                    timestamp=datetime(2026, 11, 16, 10, 0, 0),
                    status=0,
                )

                inserted = monitor.sync_device_records(db, users, [invalid, valid])
                punches = db.execute(
                    "SELECT user_id,punch_time,status FROM punches"
                ).fetchall()

            self.assertEqual(
                inserted,
                [("2026-11-16 09:00:00", "0", "0", "Zero ID")],
            )
            self.assertEqual(
                punches,
                [("0", "2026-11-16 09:00:00", "0")],
            )

    def test_monitor_retries_when_configuration_is_missing_or_invalid(self):
        cases = (
            ("missing file", FileNotFoundError("device configuration is not ready")),
            ("malformed JSON", "{"),
            ("missing device IP", "{}"),
        )
        for label, config_result in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmp:
                def read_config(*_args, **_kwargs):
                    if isinstance(config_result, BaseException):
                        raise config_result
                    return config_result

                stop_after_retry = RuntimeError("stop after retry sleep")
                with (
                    patch.object(monitor, "BASE", Path(tmp)),
                    patch.object(
                        monitor, "CONFIG",
                        SimpleNamespace(read_text=read_config),
                    ),
                    patch.object(monitor, "log_error") as log_error,
                    patch.object(
                        monitor.time, "sleep", side_effect=stop_after_retry
                    ) as sleep,
                ):
                    with self.assertRaisesRegex(
                        RuntimeError, "stop after retry sleep"
                    ):
                        monitor.main()

                log_error.assert_called_once()
                sleep.assert_called_once_with(10)


if __name__ == "__main__":
    unittest.main()
