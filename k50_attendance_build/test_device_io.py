from contextlib import nullcontext
from datetime import datetime, timedelta
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
        ctx._store_device_users = lambda users, db=None: app.App._store_device_users(ctx, users, db)
        ctx.after = lambda _delay, callback: callback()
        return ctx

    def test_fetch_worker_serializes_all_database_writes_with_restore(self):
        users = [SimpleNamespace(user_id=101, name="Ayesha")]
        punches = [
            SimpleNamespace(
                user_id=101,
                timestamp=datetime(2026, 11, 16, 9, 0, 0),
                status=0,
            )
        ]

        class FakeConnection:
            def disable_device(self):
                pass

            def enable_device(self):
                pass

            def disconnect(self):
                pass

            def get_users(self):
                return users

            def get_attendance(self):
                return punches

        class FakeZK:
            def __init__(self, *args, **kwargs):
                pass

            def connect(self):
                return FakeConnection()

        fake_module = types.ModuleType("zk")
        fake_module.ZK = FakeZK
        ctx = self.context()
        completed = []
        errors = []
        ctx._fetch_done = lambda total, inserted, saved: completed.append(
            (total, inserted, saved)
        )
        ctx._fetch_error = errors.append

        with (
            patch.dict(sys.modules, {"zk": fake_module}),
            patch.object(
                app,
                "database_maintenance_lock",
                wraps=app.database_maintenance_lock,
            ) as maintenance_lock,
        ):
            app.App._fetch_worker(ctx, "192.168.1.50", 4370, 0)

        maintenance_lock.assert_called_once_with(app.DB, timeout=300)
        self.assertEqual(completed, [(1, 1, 1)])
        self.assertEqual(errors, [])
        with sqlite3.connect(app.DB) as db:
            self.assertEqual(
                db.execute("SELECT name FROM staff WHERE user_id='101'").fetchone()[0],
                "Ayesha",
            )
            self.assertEqual(
                db.execute(
                    "SELECT punch_time FROM punches WHERE user_id='101'"
                ).fetchone()[0],
                "2026-11-16 09:00:00",
            )


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

    def test_fetch_worker_preserves_zero_device_id_and_uses_uid_only_when_missing(self):
        users = [
            SimpleNamespace(user_id=0, uid=999, name="Zero ID"),
            SimpleNamespace(user_id=None, uid=7, name="Fallback ID"),
            SimpleNamespace(user_id="   ", uid=8, name="Whitespace Primary"),
        ]
        punches = [
            SimpleNamespace(
                user_id=0,
                timestamp=datetime(2026, 11, 15, 8, 0, 0),
                status=0,
            ),
            SimpleNamespace(
                user_id="   ",
                uid=8,
                timestamp=datetime(2026, 11, 15, 8, 30, 0),
                status=0,
            ),
        ]

        class FakeConnection:
            def disable_device(self):
                pass

            def enable_device(self):
                pass

            def disconnect(self):
                pass

            def get_users(self):
                return users

            def get_attendance(self):
                return punches

        class FakeZK:
            def __init__(self, *args, **kwargs):
                pass

            def connect(self):
                return FakeConnection()

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

        self.assertEqual(completed, [(2, 2, 3)])
        self.assertEqual(errors, [])
        with sqlite3.connect(app.DB) as db:
            staff = db.execute(
                "SELECT user_id,name FROM staff ORDER BY user_id"
            ).fetchall()
            punch_rows = db.execute(
                "SELECT user_id,punch_time,status FROM punches"
            ).fetchall()
            history = db.execute(
                """SELECT active,effective_date,source FROM staff_status_history
                   WHERE user_id='0' ORDER BY effective_date,id"""
            ).fetchall()
        self.assertEqual(staff, [("0", "Zero ID"), ("7", "Fallback ID"), ("8", "Whitespace Primary")])
        self.assertEqual(
            punch_rows,
            [
                ("0", "2026-11-15 08:00:00", "0"),
                ("8", "2026-11-15 08:30:00", "0"),
            ],
        )
        self.assertEqual(
            history,
            [
                (0, "0001-01-01", "device-sync-baseline"),
                (1, "2026-11-15", "device-sync"),
            ],
        )

    def test_new_device_users_get_status_history_from_first_punch_or_sync_date(self):
        users = [
            SimpleNamespace(user_id=101, name="Ayesha"),
            SimpleNamespace(user_id=102, name="Bilal"),
        ]
        punches = [
            SimpleNamespace(
                user_id=101,
                timestamp=datetime(2026, 11, 15, 9, 0, 0),
                status=0,
            ),
        ]

        class FakeConnection:
            def disable_device(self):
                pass

            def enable_device(self):
                pass

            def disconnect(self):
                pass

            def get_users(self):
                return users

            def get_attendance(self):
                return punches

        connection = FakeConnection()

        class FakeZK:
            def __init__(self, *args, **kwargs):
                pass

            def connect(self):
                return connection

        fake_module = types.ModuleType("zk")
        fake_module.ZK = FakeZK
        ctx = self.context()
        ctx._fetch_done = Mock()
        ctx._fetch_error = Mock()

        with patch.dict(sys.modules, {"zk": fake_module}):
            app.App._fetch_worker(ctx, "192.168.1.50", 4370, 0)

        today = app.date.today().isoformat()
        previous_day = (app.date.fromisoformat(today) - timedelta(days=1)).isoformat()
        with sqlite3.connect(app.DB) as db:
            history_101 = db.execute(
                """SELECT active,effective_date,source FROM staff_status_history
                   WHERE user_id='101' ORDER BY effective_date,id"""
            ).fetchall()
            history_102 = db.execute(
                """SELECT active,effective_date,source FROM staff_status_history
                   WHERE user_id='102' ORDER BY effective_date,id"""
            ).fetchall()
            self.assertFalse(app.employee_active_on(db, "101", "2026-11-14"))
            self.assertTrue(app.employee_active_on(db, "101", "2026-11-15"))
            self.assertFalse(app.employee_active_on(db, "102", previous_day))
            self.assertTrue(app.employee_active_on(db, "102", today))

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

    def test_device_sync_falls_back_to_first_punch_for_malformed_joining_date(self):
        with sqlite3.connect(app.DB) as db:
            db.execute(
                """INSERT INTO staff(user_id,name,joining_date,active)
                   VALUES('103','Legacy Name','not-a-date',1)"""
            )

        users = [SimpleNamespace(user_id=103, name="Updated Device Name")]
        punches = [
            SimpleNamespace(
                user_id=103,
                timestamp=datetime(2024, 3, 5, 17, 0, 0),
                status=1,
            ),
            SimpleNamespace(
                user_id=103,
                timestamp=datetime(2024, 3, 3, 9, 0, 0),
                status=0,
            ),
        ]

        class FakeConnection:
            def disable_device(self):
                pass

            def enable_device(self):
                pass

            def disconnect(self):
                pass

            def get_users(self):
                return users

            def get_attendance(self):
                return punches

        class FakeZK:
            def __init__(self, *args, **kwargs):
                pass

            def connect(self):
                return FakeConnection()

        fake_module = types.ModuleType("zk")
        fake_module.ZK = FakeZK
        ctx = self.context()
        ctx._fetch_done = Mock()
        ctx._fetch_error = Mock()

        with patch.dict(sys.modules, {"zk": fake_module}):
            app.App._fetch_worker(ctx, "192.168.1.50", 4370, 0)

        with sqlite3.connect(app.DB) as db:
            profile = db.execute(
                "SELECT joining_date FROM staff WHERE user_id='103'"
            ).fetchone()
            history = db.execute(
                """SELECT active,effective_date,source FROM staff_status_history
                   WHERE user_id='103' ORDER BY effective_date,id"""
            ).fetchall()
            self.assertFalse(app.employee_active_on(db, "103", "2024-03-02"))
            self.assertTrue(app.employee_active_on(db, "103", "2024-03-03"))

        self.assertEqual(profile, ("not-a-date",))
        self.assertEqual(
            history,
            [
                (0, "0001-01-01", "device-sync-baseline"),
                (1, "2024-03-03", "device-sync"),
            ],
        )
        ctx._fetch_done.assert_called_once_with(2, 2, 1)
        ctx._fetch_error.assert_not_called()

    def test_device_name_sync_preserves_employee_profile_and_status_history(self):
        with sqlite3.connect(app.DB) as db:
            db.execute(
                """INSERT INTO staff(user_id,name,department,designation,joining_date,active)
                   VALUES('101','Old Device Name','Kitchen','Chef','2024-03-01',0)"""
            )
            db.execute(
                """INSERT INTO staff_status_history(user_id,active,effective_date,source)
                   VALUES('101',0,'2026-10-01','profile')"""
            )

        users = [SimpleNamespace(user_id=101, name="Updated Device Name")]

        class FakeConnection:
            def disable_device(self):
                pass

            def enable_device(self):
                pass

            def disconnect(self):
                pass

            def get_users(self):
                return users

            def get_attendance(self):
                return []

        connection = FakeConnection()

        class FakeZK:
            def __init__(self, *args, **kwargs):
                pass

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

        self.assertEqual(completed, [(0, 0, 1)])
        self.assertEqual(errors, [])
        with sqlite3.connect(app.DB) as db:
            profile = db.execute(
                """SELECT name,department,designation,joining_date,active
                   FROM staff WHERE user_id='101'"""
            ).fetchone()
            history = db.execute(
                """SELECT active,effective_date,source FROM staff_status_history
                   WHERE user_id='101' ORDER BY effective_date,id"""
            ).fetchall()
        self.assertEqual(
            profile,
            ("Updated Device Name", "Kitchen", "Chef", "2024-03-01", 0),
        )
        self.assertEqual(history, [(0, "2026-10-01", "profile")])

    def test_discovery_rejects_ipv6_fallback_before_scanning(self):
        class NoIPv4Route:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def connect(self, _destination):
                raise OSError("no IPv4 route")

        ctx = SimpleNamespace(
            port=SimpleNamespace(get=lambda: "4370"),
            key=SimpleNamespace(get=lambda: "0"),
            ip=SimpleNamespace(get=lambda: "2001:db8::25"),
            status=SimpleNamespace(set=Mock()),
        )
        with patch.object(app.socket, "socket", return_value=NoIPv4Route()), \
             patch.object(app.threading, "Thread") as worker, \
             patch.object(app.messagebox, "showerror") as showerror:
            app.App.discover_device(ctx)

        worker.assert_not_called()
        showerror.assert_called_once_with(
            "IPv4 required",
            "Automatic discovery scans a local IPv4 /24 network. Enter a valid IPv4 address or connect this computer to an IPv4 network.",
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


    def test_fetch_rejects_ports_outside_tcp_range_before_starting_worker(self):
        for port in ("0", "65536", "-1"):
            with self.subTest(port=port):
                ctx = SimpleNamespace(
                    ip=SimpleNamespace(get=lambda: "192.168.1.50"),
                    port=SimpleNamespace(get=lambda value=port: value),
                    key=SimpleNamespace(get=lambda: "0"),
                    status=SimpleNamespace(set=Mock()),
                )
                with patch.object(app.threading, "Thread") as worker, \
                     patch.object(app.messagebox, "showerror") as showerror:
                    app.App.fetch(ctx)
                worker.assert_not_called()
                showerror.assert_called_once_with(
                    "Invalid settings",
                    "Port must be between 1 and 65535.",
                )




    def test_fetch_prevents_overlapping_sync_workers(self):
        ctx = SimpleNamespace(
            ip=SimpleNamespace(get=lambda: "192.168.1.50"),
            port=SimpleNamespace(get=lambda: "4370"),
            key=SimpleNamespace(get=lambda: "0"),
            status=SimpleNamespace(set=Mock()),
            _fetch_in_progress=False,
        )
        # App.fetch is exercised with a lightweight context instead of a Tk App.
        # Supply its worker explicitly so a missing fixture cannot open a modal
        # error dialog and hang the headless Windows/macOS CI runner.
        ctx._fetch_worker = Mock()

        with patch.object(app.threading, "Thread") as worker, \
             patch.object(app.messagebox, "showwarning") as showwarning, \
             patch.object(app.messagebox, "showerror") as showerror:
            app.App.fetch(ctx)
            self.assertTrue(ctx._fetch_in_progress)
            app.App.fetch(ctx)

        worker.assert_called_once()
        worker.return_value.start.assert_called_once()
        showwarning.assert_called_once_with(
            "Attendance sync already running",
            "An attendance sync is already in progress. Wait for it to finish before starting another.",
        )
        showerror.assert_not_called()

    def test_fetch_completion_and_error_callbacks_clear_in_progress_guard(self):
        ctx = SimpleNamespace(
            _fetch_in_progress=True,
            refresh=Mock(),
            status=SimpleNamespace(set=Mock()),
        )
        with patch.object(app.messagebox, "showinfo"):
            app.App._fetch_done(ctx, 0, 0, 0)
        self.assertFalse(ctx._fetch_in_progress)

        ctx._fetch_in_progress=True
        with patch.object(app.messagebox, "showerror"):
            app.App._fetch_error(ctx, "simulated connection failure")
        self.assertFalse(ctx._fetch_in_progress)

    def test_fetch_thread_start_failure_releases_in_progress_guard(self):
        ctx = SimpleNamespace(
            ip=SimpleNamespace(get=lambda: "192.168.1.50"),
            port=SimpleNamespace(get=lambda: "4370"),
            key=SimpleNamespace(get=lambda: "0"),
            status=SimpleNamespace(set=Mock()),
            _fetch_in_progress=False,
        )
        ctx._fetch_worker = Mock()
        with patch.object(app.threading, "Thread", side_effect=RuntimeError("thread unavailable")), \
             patch.object(app.messagebox, "showerror") as showerror:
            app.App.fetch(ctx)

        self.assertFalse(ctx._fetch_in_progress)
        self.assertEqual(ctx.status.set.call_args.args[0], "Could not start attendance sync.")
        showerror.assert_called_once_with("Could not start attendance sync", "thread unavailable")

    def test_fetch_worker_reenables_and_disconnects_device_after_read_failures(self):
        for failure_stage in ("get_users", "get_attendance"):
            with self.subTest(failure_stage=failure_stage):
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
                        if failure_stage == "get_users":
                            raise RuntimeError("simulated user read failure")
                        return [SimpleNamespace(user_id=101, name="Ayesha")]

                    def get_attendance(self):
                        raise RuntimeError("simulated attendance read failure")

                connection = FakeConnection()

                class FakeZK:
                    def __init__(self, *args, **kwargs):
                        pass

                    def connect(self):
                        return connection

                fake_module = types.ModuleType("zk")
                fake_module.ZK = FakeZK
                ctx = self.context()
                errors = []
                ctx._fetch_error = errors.append
                ctx._fetch_done = Mock()

                with patch.dict(sys.modules, {"zk": fake_module}):
                    app.App._fetch_worker(ctx, "192.168.1.50", 4370, 0)

                self.assertEqual(connection.disabled, 1)
                self.assertEqual(connection.enabled, 1)
                self.assertEqual(connection.disconnected, 1)
                self.assertEqual(len(errors), 1)
                self.assertIn("simulated", errors[0])
                ctx._fetch_done.assert_not_called()
                with sqlite3.connect(app.DB) as db:
                    self.assertEqual(db.execute("SELECT COUNT(*) FROM punches").fetchone()[0], 0)
                    if failure_stage == "get_attendance":
                        today = app.date.today().isoformat()
                        history = db.execute(
                            """SELECT active,effective_date,source FROM staff_status_history
                               WHERE user_id='101' ORDER BY effective_date,id"""
                        ).fetchall()
                        self.assertEqual(
                            history,
                            [
                                (0, "0001-01-01", "device-sync-baseline"),
                                (1, today, "device-sync"),
                            ],
                        )
                        self.assertFalse(app.employee_active_on(db, "101", "0001-01-02"))
                        self.assertTrue(app.employee_active_on(db, "101", today))
                    else:
                        self.assertEqual(
                            db.execute("SELECT COUNT(*) FROM staff_status_history").fetchone()[0],
                            0,
                        )



    def test_fetch_worker_reports_device_reenable_failure_after_saving_punches(self):
        user = SimpleNamespace(user_id=101, name="Ayesha")
        punch = SimpleNamespace(
            user_id=101,
            timestamp=datetime(2026, 11, 16, 9, 0, 0),
            status=0,
        )

        class FakeConnection:
            def __init__(self):
                self.disabled = 0
                self.enabled = 0
                self.disconnected = 0

            def disable_device(self):
                self.disabled += 1

            def enable_device(self):
                self.enabled += 1
                raise RuntimeError("simulated re-enable failure")

            def disconnect(self):
                self.disconnected += 1

            def get_users(self):
                return [user]

            def get_attendance(self):
                return [punch]

        connection = FakeConnection()

        class FakeZK:
            def __init__(self, *args, **kwargs):
                pass

            def connect(self):
                return connection

        fake_module = types.ModuleType("zk")
        fake_module.ZK = FakeZK
        ctx = self.context()
        completed = []
        errors = []
        ctx._fetch_done = lambda total, inserted, saved, warning=None: completed.append(
            (total, inserted, saved, warning)
        )
        ctx._fetch_error = lambda message, warning=None: errors.append((message, warning))

        with patch.dict(sys.modules, {"zk": fake_module}):
            app.App._fetch_worker(ctx, "192.168.1.50", 4370, 0)

        self.assertEqual(connection.disabled, 1)
        self.assertEqual(connection.enabled, 1)
        self.assertEqual(connection.disconnected, 1)
        self.assertEqual(len(errors), 0)
        self.assertEqual(completed, [(
            1, 1, 1, "Could not re-enable attendance device: simulated re-enable failure"
        )])
        with sqlite3.connect(app.DB) as db:
            self.assertEqual(
                db.execute("SELECT user_id,punch_time,status FROM punches").fetchall(),
                [("101", "2026-11-16 09:00:00", "0")],
            )

        ui_ctx = SimpleNamespace(
            refresh=Mock(),
            status=SimpleNamespace(set=Mock()),
        )
        with patch.object(app.messagebox, "showwarning") as showwarning, \
             patch.object(app.messagebox, "showinfo") as showinfo:
            app.App._fetch_done(
                ui_ctx, 1, 1, 1,
                "Could not re-enable attendance device: simulated re-enable failure",
            )
        showwarning.assert_called_once()
        showinfo.assert_not_called()
        self.assertIn("DEVICE WARNING", ui_ctx.status.set.call_args.args[0])




    def test_fetch_worker_skips_malformed_device_rows_without_losing_valid_punches(self):
        users = [SimpleNamespace(user_id=0, name="Zero ID")]
        punches = [
            SimpleNamespace(
                user_id=0,
                timestamp=datetime(2026, 11, 16, 9, 0, 0),
                status=0,
            ),
            SimpleNamespace(
                user_id=None,
                uid="",
                timestamp=datetime(2026, 11, 16, 9, 1, 0),
                status=1,
            ),
            SimpleNamespace(user_id=101, timestamp=None, status=1),
        ]

        class FakeConnection:
            def disable_device(self):
                pass

            def enable_device(self):
                pass

            def disconnect(self):
                pass

            def get_users(self):
                return users

            def get_attendance(self):
                return punches

        class FakeZK:
            def __init__(self, *args, **kwargs):
                pass

            def connect(self):
                return FakeConnection()

        fake_module = types.ModuleType("zk")
        fake_module.ZK = FakeZK
        ctx = self.context()
        completed = []
        errors = []
        ctx._fetch_done = lambda total, inserted, saved, warning=None: completed.append(
            (total, inserted, saved, warning)
        )
        ctx._fetch_error = errors.append

        with patch.dict(sys.modules, {"zk": fake_module}):
            app.App._fetch_worker(ctx, "192.168.1.50", 4370, 0)

        self.assertEqual(errors, [])
        self.assertEqual(completed, [(
            3, 1, 1,
            "Skipped 2 malformed attendance records (missing device IDs or invalid timestamps).",
        )])
        with sqlite3.connect(app.DB) as db:
            punches_saved = db.execute(
                "SELECT user_id,punch_time,status FROM punches"
            ).fetchall()
        self.assertEqual(
            punches_saved,
            [("0", "2026-11-16 09:00:00", "0")],
        )


if __name__ == "__main__":
    unittest.main()
