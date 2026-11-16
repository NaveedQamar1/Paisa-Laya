"""Cross-process maintenance lock for the live SQLite attendance database.

The GUI restore path and background monitor must cooperate on this lock.  The
lock file is intentionally persistent: unlinking a locked file can let a
second process lock a different inode and bypass the first process.
"""
from contextlib import contextmanager
import os
import time
from pathlib import Path


def _deadline(timeout):
    if timeout is None:
        return None
    try:
        seconds = float(timeout)
    except (TypeError, ValueError):
        raise ValueError("Lock timeout must be a non-negative number or None.") from None
    if seconds < 0:
        raise ValueError("Lock timeout must be a non-negative number or None.")
    return time.monotonic() + seconds


def _wait_for_lock(attempt, deadline, lock_path):
    while True:
        try:
            attempt()
            return
        except OSError as exc:
            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError(
                    f"Timed out waiting for the attendance database maintenance lock: {lock_path}"
                ) from exc
            time.sleep(0.05)


@contextmanager
def database_maintenance_lock(database_path, timeout=300):
    """Serialize monitor writes with backup/restore operations across processes.

    Uses an OS advisory file lock: flock on POSIX and a one-byte msvcrt lock on
    Windows.  All SCAFA processes accessing the same database must use this
    helper; SQLite remains responsible for transaction-level locking.
    """
    database = Path(database_path).expanduser().resolve()
    lock_path = database.with_name(database.name + ".maintenance.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    deadline = _deadline(timeout)

    with lock_path.open("a+b") as handle:
        if os.name == "nt":
            import msvcrt

            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()

            def acquire():
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)

            _wait_for_lock(acquire, deadline, lock_path)
            try:
                yield lock_path
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            def acquire():
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

            _wait_for_lock(acquire, deadline, lock_path)
            try:
                yield lock_path
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
