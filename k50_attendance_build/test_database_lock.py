import errno
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import database_lock


class DatabaseLockWaitTests(unittest.TestCase):
    def test_lock_contention_retries_until_the_lock_is_acquired(self):
        attempts = 0

        def attempt():
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise BlockingIOError(errno.EAGAIN, "lock is currently held")

        deadline = database_lock.time.monotonic() + 2
        with patch.object(database_lock.time, "sleep") as sleep:
            database_lock._wait_for_lock(
                attempt, deadline, "attendance.db.maintenance.lock"
            )

        self.assertEqual(attempts, 2)
        sleep.assert_called_once_with(0.05)

    def test_permanent_os_error_is_propagated_without_waiting(self):
        failure = OSError(errno.EBADF, "invalid lock-file descriptor")

        def attempt():
            raise failure

        deadline = database_lock.time.monotonic() + 30
        with patch.object(database_lock.time, "sleep") as sleep:
            with self.assertRaises(OSError) as raised:
                database_lock._wait_for_lock(
                    attempt, deadline, "attendance.db.maintenance.lock"
                )

        self.assertIs(raised.exception, failure)
        sleep.assert_not_called()

    def test_windows_lock_violation_errno_is_only_contention_on_windows(self):
        failure = OSError(errno.EACCES, "lock violation")

        self.assertTrue(database_lock._is_lock_contention(failure, windows=True))
        self.assertFalse(database_lock._is_lock_contention(failure, windows=False))

        lock_violation = OSError(errno.EACCES, "Windows lock violation")
        lock_violation.winerror = 33
        self.assertTrue(
            database_lock._is_lock_contention(lock_violation, windows=True)
        )

        access_denied = OSError(errno.EACCES, "Windows access denied")
        access_denied.winerror = 5
        self.assertFalse(
            database_lock._is_lock_contention(access_denied, windows=True)
        )
        self.assertFalse(
            database_lock._is_lock_contention(
                OSError(errno.EIO, "filesystem I/O failure"), windows=True
            )
        )

    def test_interrupted_lock_attempt_is_retried(self):
        attempts = 0

        def attempt():
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise InterruptedError(errno.EINTR, "interrupted system call")

        deadline = database_lock.time.monotonic() + 2
        with patch.object(database_lock.time, "sleep"):
            database_lock._wait_for_lock(
                attempt, deadline, "attendance.db.instance.lock"
            )

        self.assertEqual(attempts, 2)

    def test_contention_timeout_preserves_underlying_os_error(self):
        failure = BlockingIOError(errno.EAGAIN, "lock is currently held")

        def attempt():
            raise failure

        with self.assertRaises(TimeoutError) as raised:
            database_lock._wait_for_lock(
                attempt, 0, "attendance.db.maintenance.lock"
            )

        self.assertIs(raised.exception.__cause__, failure)


    def test_non_finite_or_unrepresentable_timeouts_are_rejected(self):
        invalid_timeouts = (
            ("NaN", float("nan")),
            ("positive infinity", float("inf")),
            ("negative infinity", float("-inf")),
            ("NaN string", "nan"),
            ("float conversion overflow", 10 ** 10000),
        )

        for label, timeout in invalid_timeouts:
            with self.subTest(value=label):
                with self.assertRaisesRegex(
                    ValueError, "finite non-negative number"
                ):
                    database_lock._deadline(timeout)


    def test_invalid_timeout_is_rejected_before_lock_directory_is_created(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            parent = Path(temporary_directory) / "not-created"
            lock_path = parent / "attendance.db.lock"

            with self.assertRaisesRegex(ValueError, "finite non-negative number"):
                with database_lock._exclusive_file_lock(lock_path, float("nan")):
                    self.fail("An invalid timeout must not acquire a lock.")

            self.assertFalse(parent.exists())


if __name__ == "__main__":
    unittest.main()
