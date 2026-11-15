from contextlib import nullcontext
from datetime import datetime
import ipaddress
import sqlite3
import sys
import tempfile
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import app


class DeviceIOTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.old_db = app.DB
        self.old_base = app.BASE
        app.BASE = Path(self.temp.name)
        app.DB = app.BASE / "attendance.db"
        app.init_db()

    def tearDown(self):
        app.DB = self.old_db
        app.BASE = self.old_base
        self.temp.cleanup()

    def context(self):
        ctx = SimpleNamespace(_names_cache=None)
        ctx._store_device_users = lambda users: app.App._store_device_users(ctx, users)
        ctx.after = lambda _delay, callback: callback()
        return ctx

    def test_fetch_worker_syncs_staff_and_deduplicates_raw_punches(self):
        users = [
            SimpleNamespace(user_id=101, name="Ayesha"),
            SimpleNamespace(user_id=102, name=""),
        ]
        punches = [
            SimpleNamespace(
                user_id=101,
                timestamp=datetime(2026, 11, 15, 9, 0, 0),
                status=0,
            ),
            SimpleNamespace(
                user_id=101,
                timestamp=datetime(2026, 11, 15, 17, 0, 0),
                status=1,
            ),
        ]

        class FakeConnection:
            def __init__(self):
                self.disabled = 0
                self.enabled = 0
                self.disconnected = 0

            def disable_device(self):
                self.disabled += 1

            def enable_device(self):
                self.enabled += 1

            def disconnect(self):
                self.disconnected += 1

            def get_users(self):
                return users

            def get_attendance(self):
                return punches

        connection = FakeConnection()
        zk_calls = []

        class FakeZK:
            def __init__(self, *args, **kwargs):
                zk_calls.append((args, kwargs))

            def connect(self):
                return connection

        fake_module = types.ModuleType("zk")
        fake_module.ZK = FakeZK
        ctx = self.context()
        completed = []
        errors = []
        ctx._fetch_done = lambda total, inserted, saved: completed.append(
            (total, inserted, saved)
        )
        ctx._fetch_error = errors.append

        with patch.dict(sys.modules, {"zk": fake_module}):
            app.App._fetch_worker(ctx, "192.168.1.50", 4370, 0)
            app.App._fetch_worker(ctx, "192.168.1.50", 4370, 0)

        self.assertEqual(completed, [(2, 2, 1), (2, 0, 1)])
        self.assertEqual(errors, [])
        self.assertEqual(connection.disabled, 2)
        self.assertEqual(connection.enabled, 2)
        self.assertEqual(connection.disconnected, 2)
        self.assertEqual(len(zk_calls), 2)
        self.assertEqual(zk_calls[0][0][0], "192.168.1.50")
        self.assertEqual(zk_calls[0][1]["port"], 4370)

        with sqlite3.connect(app.DB) as db:
            staff = db.execute(
                "SELECT user_id,name FROM staff ORDER BY user_id"
            ).fetchall()
            saved_punches = db.execute(
                "SELECT user_id,punch_time,status FROM punches ORDER BY punch_time"
            ).fetchall()
        self.assertEqual(staff, [("101", "Ayesha")])
        self.assertEqual(
            saved_punches,
            [
                ("101", "2026-11-15 09:00:00", "0"),
                ("101", "2026-11-15 17:00:00", "1"),
            ],
        )

    def test_discovery_reports_only_after_protocol_handshake(self):
        address = ipaddress.ip_address("192.168.1.25")
        network = SimpleNamespace(hosts=lambda: [address])
        connection = SimpleNamespace(disconnect=Mock())
        zk_calls = []

        class FakeZK:
            def __init__(self, *args, **kwargs):
                zk_calls.append((args, kwargs))

            def connect(self):
                return connection

        fake_module = types.ModuleType("zk")
        fake_module.ZK = FakeZK
        discovered = []
        failed = []
        errors = []
        ctx = SimpleNamespace(
            after=lambda _delay, callback: callback(),
            _discovery_done=lambda ip, count: discovered.append((ip, count)),
            _discovery_failed=failed.append,
            _discovery_error=errors.append,
        )

        with patch.object(app.socket, "create_connection", return_value=nullcontext()):
            with patch.dict(sys.modules, {"zk": fake_module}):
                app.App._discover_worker(ctx, network, 4370, 123)

        self.assertEqual(discovered, [("192.168.1.25", 1)])
        self.assertEqual(failed, [])
        self.assertEqual(errors, [])
        connection.disconnect.assert_called_once()
        self.assertEqual(zk_calls[0][0][0], "192.168.1.25")
        self.assertEqual(zk_calls[0][1]["password"], 123)


if __name__ == "__main__":
    unittest.main()
