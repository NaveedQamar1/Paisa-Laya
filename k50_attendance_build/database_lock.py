""""Cross-process locks for the live SQLite attendance database.

The maintenance lock coordinates restore, foreground sync and the background
monitor. The application-instance lock prevents a second GUI process from
writing to the same database while the first GUI is open. Lock files are
intentionally persistent: unlinking a locked file can let another process
lock a different inode and bypass the first process.
"""
from contextlib import contextmanager
import errno
import math
import os
import time
from pathlib import Path


class ApplicationAlreadyRunningError(TimeoutError):
    """Raised when another SCAFA GUI process already owns the database."""


def _deadline(timeout):
    if timeout is None:
        return None
    try:
        seconds = float(timeout)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(
            "Lock timeout must be a finite non-negative number or None."
        ) from None
    if not math.isfinite(seconds) or seconds < 0:
        raise ValueError(
            "Lock timeout must be a finite non-negative number or None."
        )
    return time.monotonic() + seconds


def _is_lock_contention(exc, *, windows=None):
    """Return whether an OS error means the lock is currently held.

    Do not retry permanent errors such as an invalid descriptor or filesystem
    I/O failure: waiting cannot make those operations succeed. Windows'
    msvcrt.locking reports a conflicting LK_NBLCK request as EACCES, whereas
    POSIX flock reports non-blocking contention as EAGAIN/EWOULDBLOCK.
    """
    if windows is None:
        windows = os.name == "nt"

    if isinstance(exc, BlockingIOError) or exc.errno in {
        errno.EAGAIN,
        errno.EWOULDBLOCK,
        errno.EINTR,
    }:
        return True

    if windows:
        winerror = getattr(exc, "winerror", None)
        if winerror is not None:
            return winerror == 33
        return exc.errno == errno.EACCES

    return False


def _wait_for_lock(attempt, deadline, lock_path, timeout_error=TimeoutError):
    while True:
        try:
            attempt()
            return
        except OSError as exc:
            if not _is_lock_contention(exc):
                raise
            if deadline is not None and time.monotonic() >= deadline:
                raise timeout_error(
                    f"Timed out waiting for the attendance database lock: {lock_path}"
                ) from exc
            time.sleep(0.05)


@contextmanager
def _exclusive_file_lock(lock_path, timeout, timeout_error=TimeoutError):
    lock_path = Path(lock_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    deadline = _deadline(timeout)

    with lock_path.open("a+b") as handle:
        if os.name == "nt":
            import msvcrt

            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"\\0")
                handle.flush()

            def acquire():
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)

            _wait_for_lock(acquire, deadline, lock_path, timeout_error)
            try:
                yield lock_path
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            def acquire():
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

            _wait_for_lock(acquire, deadline, lock_path, timeout_error)
            try:
                yield lock_path
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def database_maintenance_lock(database_path, timeout=300):
    """Serialize monitor writes with backup/restore operations across processes.

    Uses an OS advisory file lock: flock on POSIX and a one-byte msvcrt lock on
    Windows. All SCAFA processes accessing the live database must use this
    helper for maintenance-sensitive transactions; SQLite remains responsible
    for transaction-level locking.
    """
    database = Path(database_path).expanduser().resolve()
    lock_path = database.with_name(database.name + ".maintenance.lock")
    with _exclusive_file_lock(lock_path, timeout):
        yield lock_path


@contextmanager
def application_instance_lock(database_path):
    """Allow only one GUI process to use a database at a time.

    This lock is deliberately separate from the maintenance lock so the
    background monitor can continue synchronizing while the GUI is open.
    """
    database = Path(database_path).expanduser().resolve()
    lock_path = database.with_name(database.name + ".instance.lock")
    with _exclusive_file_lock(
        lock_path,
        timeout=0,
        timeout_error=ApplicationAlreadyRunningError,
    ):
        yield lock_path
