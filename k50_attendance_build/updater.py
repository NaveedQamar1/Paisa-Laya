"""Small external helper that applies a verified SCAFA Workforce update after the app exits."""
import argparse
import os
import shlex
import signal
import stat
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import PurePosixPath
from pathlib import Path


MAX_UPDATE_ARCHIVE_BYTES = 512 * 1024 * 1024
MAX_UPDATE_FILE_BYTES = 512 * 1024 * 1024
MAX_UPDATE_TOTAL_BYTES = 1024 * 1024 * 1024
MAX_UPDATE_SYMLINK_BYTES = 4096
MAX_UPDATE_FILES = 10000


def wait_for_process(pid, timeout=180):
    deadline=time.time()+timeout
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        kernel32=ctypes.WinDLL("kernel32",use_last_error=True)
        kernel32.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
        kernel32.OpenProcess.restype=wintypes.HANDLE
        kernel32.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD]
        kernel32.WaitForSingleObject.restype=wintypes.DWORD
        kernel32.CloseHandle.argtypes=[wintypes.HANDLE]
        kernel32.CloseHandle.restype=wintypes.BOOL
        SYNCHRONIZE=0x00100000
        handle=kernel32.OpenProcess(SYNCHRONIZE,False,pid)
        if not handle:
            error=ctypes.get_last_error()
            if error==87:  # ERROR_INVALID_PARAMETER: PID no longer exists.
                return
            raise OSError(error,"Could not wait for the SCAFA Workforce process to close.")
        try:
            remaining=max(0,int((deadline-time.time())*1000))
            result=kernel32.WaitForSingleObject(handle,remaining)
            if result==0:
                return
            if result==0x102:
                raise TimeoutError("SCAFA Workforce did not close in time. No files were replaced.")
            raise OSError("Windows could not confirm that SCAFA Workforce had closed.")
        finally:
            kernel32.CloseHandle(handle)
    while time.time()<deadline:
        try:
            os.kill(pid,0)
        except ProcessLookupError:
            return
        except PermissionError:
            # The process exists but belongs to another user; do not mistake it for exited.
            time.sleep(0.5)
            continue
        except OSError:
            return
        time.sleep(0.5)
    raise TimeoutError("SCAFA Workforce did not close in time. No files were replaced.")


def show_error(message):
    try:
        import tkinter as tk
        from tkinter import messagebox
        root=tk.Tk(); root.withdraw()
        messagebox.showerror("SCAFA Workforce update failed",message)
        root.destroy()
    except Exception:
        pass


WINDOWS_MONITOR_TASK_NAME = "SCAFA Workforce Attendance Monitor"

WINDOWS_MONITOR_STATE_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$taskName = 'SCAFA Workforce Attendance Monitor'
try {
    $task = Get-ScheduledTask -TaskName $taskName -ErrorAction Stop
} catch {
    if (
    $_.FullyQualifiedErrorId -like 'CmdletizationQuery_NotFound*' -or
    $_.FullyQualifiedErrorId -like 'NoMatchingCimInstance*' -or
    $_.FullyQualifiedErrorId -like 'NoMatchingTasksFound*'
) {
        Write-Output 'MISSING'
        exit 0
    }
    throw
}
$state = [string]$task.State
switch ($state) {
    'Running' { Write-Output 'RUNNING' }
    'Disabled' { Write-Output 'DISABLED' }
    'Ready' { Write-Output 'NOT_RUNNING' }
    'Queued' { Write-Output 'QUEUED' }
    default { Write-Output 'UNKNOWN' }
}
"""

WINDOWS_MONITOR_STOP_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$taskName = 'SCAFA Workforce Attendance Monitor'
try {
    $task = Get-ScheduledTask -TaskName $taskName -ErrorAction Stop
} catch {
    # Only a genuine missing task is safe to treat as "monitor not configured".
    # Access, service, or permission errors must abort the update before files change.
    if (
    $_.FullyQualifiedErrorId -like 'CmdletizationQuery_NotFound*' -or
    $_.FullyQualifiedErrorId -like 'NoMatchingCimInstance*' -or
    $_.FullyQualifiedErrorId -like 'NoMatchingTasksFound*'
) {
        Write-Output 'MISSING'
        exit 0
    }
    throw
}
$state = [string]$task.State
if ($state -eq 'Disabled') { Write-Output 'DISABLED'; exit 0 }
if ($state -eq 'Ready') { Write-Output 'NOT_RUNNING'; exit 0 }
if ($state -eq 'Queued') { Write-Output 'QUEUED'; exit 0 }
if ($state -ne 'Running') { Write-Output 'UNKNOWN'; exit 0 }
Stop-ScheduledTask -InputObject $task -ErrorAction Stop
$deadline = (Get-Date).AddSeconds(30)
do {
    Start-Sleep -Milliseconds 200
    $task = Get-ScheduledTask -TaskName $taskName -ErrorAction Stop
    $state = [string]$task.State
} while ($state -eq 'Running' -and (Get-Date) -lt $deadline)
if ($state -ne 'Ready') {
    throw "The attendance monitor task did not reach Ready state within 30 seconds; observed '$state'."
}
Write-Output 'STOPPED'
"""

WINDOWS_MONITOR_START_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$taskName = 'SCAFA Workforce Attendance Monitor'
$task = Get-ScheduledTask -TaskName $taskName -ErrorAction Stop
if ([string]$task.State -eq 'Disabled') {
    throw 'The attendance monitor task is disabled and was not restarted.'
}
Start-ScheduledTask -InputObject $task -ErrorAction Stop
$deadline = (Get-Date).AddSeconds(30)
do {
    Start-Sleep -Milliseconds 200
    $task = Get-ScheduledTask -TaskName $taskName -ErrorAction Stop
    $state = [string]$task.State
} while ($state -ne 'Running' -and (Get-Date) -lt $deadline)
if ($state -ne 'Running') {
    throw 'The attendance monitor task did not restart within 30 seconds.'
}
Write-Output 'STARTED'
"""


WINDOWS_MONITOR_COMMAND_TIMEOUT_SECONDS = 45
WINDOWS_INSTALLER_TIMEOUT_SECONDS = 15 * 60


def _terminate_installer_process_tree(process):
    """Terminate PowerShell and any descendants started by an installer command."""
    if process.poll() is not None:
        return

    if os.name == "nt":
        taskkill = os.path.join(
            os.environ.get("SystemRoot", r"C:\Windows"),
            "System32",
            "taskkill.exe",
        )
        try:
            subprocess.run(
                [taskkill, "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass

        if process.poll() is None:
            try:
                process.kill()
            except OSError:
                pass
        return

    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except OSError:
        try:
            process.kill()
        except OSError:
            pass


def run_installer_powershell_script(script):
    """Run installer Task Scheduler commands with a bounded process-tree timeout.

    Inno Setup's ExecAndCaptureOutput has no timeout parameter, so this bundled
    helper owns the PowerShell process. On timeout, terminate its entire process
    tree, reap the process, and preserve captured output for the installer log.
    """
    command = [
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        script,
    ]
    popen_options = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
    }
    if os.name == "nt":
        popen_options["creationflags"] = getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0
        )
    else:
        popen_options["start_new_session"] = True

    process = subprocess.Popen(command, **popen_options)
    try:
        stdout, stderr = process.communicate(
            timeout=WINDOWS_MONITOR_COMMAND_TIMEOUT_SECONDS
        )
    except subprocess.TimeoutExpired as timeout_error:
        _terminate_installer_process_tree(process)
        try:
            stdout, stderr = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                process.kill()
            except OSError:
                pass
            try:
                stdout, stderr = process.communicate(timeout=5)
            except subprocess.TimeoutExpired as cleanup_error:
                raise RuntimeError(
                    "The Windows installer Task Scheduler process tree could not "
                    "be terminated and reaped after its timeout."
                ) from cleanup_error

        raise subprocess.TimeoutExpired(
            command,
            WINDOWS_MONITOR_COMMAND_TIMEOUT_SECONDS,
            output=stdout if stdout else timeout_error.output,
            stderr=stderr if stderr else timeout_error.stderr,
        )

    return subprocess.CompletedProcess(
        command, process.returncode, stdout, stderr
    )


def _run_windows_monitor_command(script, operation):
    try:
        result = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                script,
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=WINDOWS_MONITOR_COMMAND_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"Timed out while trying to {operation} the Windows attendance monitor "
            f"after {WINDOWS_MONITOR_COMMAND_TIMEOUT_SECONDS} seconds."
        ) from exc
    except OSError as exc:
        raise RuntimeError(
            f"Could not execute the Windows attendance monitor {operation} command: {exc}"
        ) from exc
    if result.returncode:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(
            f"Could not {operation} the Windows attendance monitor"
            + (f": {detail}" if detail else ".")
        )
    output = [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]
    return output[-1].upper() if output else ""


def _windows_monitor_state():
    """Return a positively observed state for the per-user scheduled monitor."""
    state = _run_windows_monitor_command(
        WINDOWS_MONITOR_STATE_SCRIPT, "inspect"
    )
    if state not in {"RUNNING", "NOT_RUNNING", "DISABLED", "MISSING", "QUEUED", "UNKNOWN"}:
        raise RuntimeError(
            f"Could not confirm the Windows attendance monitor state: {state or 'no response'}."
        )
    return state


def stop_windows_monitor():
    """Stop a running scheduled monitor and verify ambiguous command outcomes."""
    initial_state = _windows_monitor_state()
    if initial_state in {"MISSING", "NOT_RUNNING", "DISABLED"}:
        return False
    if initial_state != "RUNNING":
        raise RuntimeError(
            f"Could not confirm the Windows attendance monitor state: {initial_state or 'no response'}."
        )

    try:
        state = _run_windows_monitor_command(
            WINDOWS_MONITOR_STOP_SCRIPT, "stop"
        )
    except RuntimeError as stop_error:
        try:
            post_state = _windows_monitor_state()
        except Exception as probe_error:
            raise RuntimeError(
                f"{stop_error} Could not verify whether the attendance monitor stopped: {probe_error}"
            ) from stop_error
        if post_state == "NOT_RUNNING":
            # The monitor was confirmed running before stop was attempted. Preserve
            # that fact so apply_windows() restarts it after the installer completes.
            return True
        if post_state == "RUNNING":
            raise RuntimeError(
                f"{stop_error} The attendance monitor is still running; the update was aborted."
            ) from stop_error
        raise RuntimeError(
            f"{stop_error} The attendance monitor state changed to {post_state}; the update was aborted."
        ) from stop_error

    if state in {"STOPPED", "NOT_RUNNING"}:
        return True
    raise RuntimeError(
        f"Could not confirm that the Windows attendance monitor stopped: {state or 'no response'}."
    )


def start_windows_monitor():
    """Restart a monitor that was running before an update."""
    state = _run_windows_monitor_command(
        WINDOWS_MONITOR_START_SCRIPT, "restart"
    )
    if state != "STARTED":
        raise RuntimeError(
            f"Could not confirm that the Windows attendance monitor restarted: {state or 'no response'}."
        )


def apply_windows(package,target):
    installer=Path(package)
    if not installer.is_file():
        raise FileNotFoundError("The downloaded Windows installer is missing.")

    # The scheduled monitor is a separate process and is not covered reliably by
    # closing the GUI application. Stop it before replacing scafa-monitor.exe.
    monitor_was_running = stop_windows_monitor()
    try:
        try:
            result=subprocess.run(
                [str(installer),"/VERYSILENT","/SUPPRESSMSGBOXES","/NORESTART","/CLOSEAPPLICATIONS"],
                check=False,
                timeout=WINDOWS_INSTALLER_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"The Windows installer did not finish within {WINDOWS_INSTALLER_TIMEOUT_SECONDS} "
                "seconds; the installer process was terminated."
            ) from exc
        if result.returncode:
            raise RuntimeError(f"The Windows installer returned exit code {result.returncode}.")
        installed_app=Path(target)/"SCAFA_Workforce.exe"
        if not installed_app.is_file():
            raise RuntimeError("The installer completed, but SCAFA_Workforce.exe was not found at the expected installation path.")
    except Exception as update_error:
        if monitor_was_running:
            try:
                start_windows_monitor()
            except Exception as restart_error:
                raise RuntimeError(
                    f"{update_error} The attendance monitor was running before the update, "
                    f"but could not be restarted: {restart_error}"
                ) from update_error
        raise

    if monitor_was_running:
        start_windows_monitor()
    subprocess.Popen([str(installed_app)],cwd=str(Path(target)))


def safe_extract_zip(archive, destination):
    """Extract regular files and safe, relative macOS bundle symlinks."""
    destination=Path(destination).resolve()
    archive_path = Path(archive)
    if archive_path.stat().st_size > MAX_UPDATE_ARCHIVE_BYTES:
        raise RuntimeError("The update archive exceeds the maximum compressed size.")
    with zipfile.ZipFile(archive_path) as zf:
        members=[]
        symlinks={}
        infos = zf.infolist()
        if len(infos) > MAX_UPDATE_FILES:
            raise RuntimeError("The update archive contains too many files.")
        declared_total = 0
        for member in infos:
            if member.file_size > MAX_UPDATE_FILE_BYTES:
                raise RuntimeError("An update archive file exceeds the maximum allowed size.")
            declared_total += member.file_size
            if declared_total > MAX_UPDATE_TOTAL_BYTES:
                raise RuntimeError("The expanded update archive exceeds the maximum allowed size.")
            normalized=member.filename.replace("\\","/")
            member_path=PurePosixPath(normalized)
            if member_path.is_absolute() or ".." in member_path.parts or (member_path.parts and ":" in member_path.parts[0]):
                raise RuntimeError("The update archive contains an unsafe file path.")
            output=destination.joinpath(*member_path.parts)
            resolved=output.resolve()
            if resolved!=destination and destination not in resolved.parents:
                raise RuntimeError("The update archive attempts to write outside its extraction folder.")
            mode=(member.external_attr >> 16) & 0xFFFF
            if stat.S_IFMT(mode)==stat.S_IFLNK:
                if member.file_size > MAX_UPDATE_SYMLINK_BYTES:
                    raise RuntimeError("The update archive contains an oversized symbolic link.")
                try:
                    with zf.open(member) as link_stream:
                        link_data = link_stream.read(MAX_UPDATE_SYMLINK_BYTES + 1)
                        if len(link_data) > MAX_UPDATE_SYMLINK_BYTES or link_stream.read(1):
                            raise RuntimeError("The update archive contains an oversized symbolic link.")
                    link_target=link_data.decode("utf-8")
                except RuntimeError:
                    raise
                except Exception as exc:
                    raise RuntimeError("The update archive contains an invalid symbolic link.") from exc
                if not link_target or os.path.isabs(link_target):
                    raise RuntimeError("The update archive contains an unsafe symbolic link.")
                target_path=Path(os.path.normpath(str(output.parent / link_target)))
                if target_path!=destination and destination not in target_path.parents:
                    raise RuntimeError("The update archive contains a symbolic link outside its extraction folder.")
                symlinks[member_path]=link_target
            else:
                members.append((member,member_path,mode))

        # Never allow a regular file to be written through an archive-created symlink.
        for _,member_path,_ in members:
            if any(parent in symlinks for parent in member_path.parents):
                raise RuntimeError("The update archive contains a file nested inside a symbolic link.")

        # Write directories and regular files first; create links only after all writes finish.
        extracted_total = 0
        for member,member_path,mode in members:
            output=destination.joinpath(*member_path.parts)
            if member.is_dir():
                output.mkdir(parents=True,exist_ok=True)
                continue
            output.parent.mkdir(parents=True,exist_ok=True)
            member_written = 0
            with zf.open(member) as source, output.open("wb") as target:
                while True:
                    chunk = source.read(1024 * 1024)
                    if not chunk:
                        break
                    member_written += len(chunk)
                    if member_written > MAX_UPDATE_FILE_BYTES:
                        raise RuntimeError("An update archive file exceeds the maximum allowed size.")
                    if member_written + extracted_total > MAX_UPDATE_TOTAL_BYTES:
                        raise RuntimeError("The expanded update archive exceeds the maximum allowed size.")
                    target.write(chunk)
                if member_written != member.file_size:
                    raise RuntimeError("An update archive file has an inconsistent expanded size.")
            extracted_total += member_written
            permissions=mode & 0o777
            if permissions:
                output.chmod(permissions)

        for member_path,link_target in symlinks.items():
            output=destination.joinpath(*member_path.parts)
            output.parent.mkdir(parents=True,exist_ok=True)
            os.symlink(link_target,output)



MACOS_MONITOR_LABEL = "pk.scafa.workforce.monitor"


def _macos_user_context(user_uid=None):
    """Resolve the original login user's home and LaunchAgent plist safely."""
    if not hasattr(os, "getuid"):
        raise RuntimeError("The macOS monitor identity cannot be resolved on this platform.")
    current_uid = os.getuid()
    try:
        uid = current_uid if user_uid is None else int(user_uid)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("The original macOS user ID is invalid.") from exc
    if uid <= 0:
        raise RuntimeError("A valid non-root macOS login user ID is required for monitor management.")
    if uid != current_uid and (not hasattr(os, "geteuid") or os.geteuid() != 0):
        raise RuntimeError("The updater cannot manage a LaunchAgent belonging to another user.")
    try:
        import pwd
        home = Path(pwd.getpwuid(uid).pw_dir)
    except (ImportError, KeyError, OSError) as exc:
        raise RuntimeError("Could not resolve the original user's macOS home directory.") from exc
    plist = home / "Library" / "LaunchAgents" / (MACOS_MONITOR_LABEL + ".plist")
    return uid, plist


def _run_macos_launchctl(*arguments):
    """Run launchctl without a shell and return its checked status for diagnosis."""
    try:
        return subprocess.run(
            ["/bin/launchctl", *arguments],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"Could not execute macOS launchctl: {exc}") from exc


def _macos_launchctl_detail(result):
    return (result.stderr or result.stdout or f"exit code {result.returncode}").strip()


def _macos_service_is_missing(result):
    detail = _macos_launchctl_detail(result).lower()
    return any(
        marker in detail
        for marker in ("could not find service", "service not found", "no such process")
    )


def _validate_macos_agent_plist(plist, user_uid):
    plist = Path(plist)
    try:
        metadata = plist.lstat()
    except OSError as exc:
        raise RuntimeError(f"The original user's LaunchAgent plist is unavailable: {exc}") from exc
    if plist.is_symlink() or not stat.S_ISREG(metadata.st_mode):
        raise RuntimeError("The original user's LaunchAgent plist is not a regular file.")
    if hasattr(metadata, "st_uid") and metadata.st_uid != user_uid:
        raise RuntimeError("The original user's LaunchAgent plist is not owned by that user.")
    return plist


def _confirm_macos_monitor_unloaded_after_failed_bootout(service, failure_detail):
    """Accept an ambiguous bootout only when launchctl positively confirms absence."""
    try:
        confirmation = _run_macos_launchctl("print", service)
    except RuntimeError as probe_error:
        raise RuntimeError(
            "Could not determine whether the original user's attendance monitor stopped "
            "after the bootout command failed: "
            + failure_detail
            + "; postcondition probe failed: "
            + str(probe_error)
        ) from probe_error

    if confirmation.returncode and _macos_service_is_missing(confirmation):
        return
    if confirmation.returncode:
        raise RuntimeError(
            "Could not determine whether the original user's attendance monitor stopped "
            "after the bootout command failed: "
            + failure_detail
            + "; "
            + _macos_launchctl_detail(confirmation)
        )
    raise RuntimeError(
        "Could not stop the original user's macOS attendance monitor; it remains loaded "
        "after the bootout command failed: "
        + failure_detail
    )


def stop_macos_monitor(user_uid=None):
    """Unload the original user's monitor and return its plist only if it was loaded."""
    if sys.platform != "darwin":
        return None
    uid, plist = _macos_user_context(user_uid)
    domain = f"gui/{uid}"
    service = f"{domain}/{MACOS_MONITOR_LABEL}"

    domain_result = _run_macos_launchctl("print", domain)
    if domain_result.returncode:
        if not plist.exists():
            # No configured monitor and no GUI session (as on a headless CI runner).
            return None
        raise RuntimeError(
            "Could not access the original user's macOS GUI session before updating: "
            + _macos_launchctl_detail(domain_result)
        )

    service_result = _run_macos_launchctl("print", service)
    if service_result.returncode:
        if _macos_service_is_missing(service_result):
            return None
        raise RuntimeError(
            "Could not determine whether the original user's attendance monitor is loaded: "
            + _macos_launchctl_detail(service_result)
        )

    if not plist.exists():
        raise RuntimeError(
            "The attendance monitor is loaded, but its LaunchAgent plist is missing. "
            "The update was stopped to avoid leaving an orphaned monitor."
        )
    _validate_macos_agent_plist(plist, uid)

    try:
        stopped = _run_macos_launchctl("bootout", service)
    except RuntimeError as stop_error:
        _confirm_macos_monitor_unloaded_after_failed_bootout(service, str(stop_error))
        return plist
    if stopped.returncode:
        _confirm_macos_monitor_unloaded_after_failed_bootout(
            service, _macos_launchctl_detail(stopped)
        )
        return plist

    confirmation = _run_macos_launchctl("print", service)
    if confirmation.returncode and _macos_service_is_missing(confirmation):
        return plist
    if confirmation.returncode:
        raise RuntimeError(
            "Could not confirm that the original user's attendance monitor stopped: "
            + _macos_launchctl_detail(confirmation)
        )
    raise RuntimeError("The original user's attendance monitor is still loaded after bootout.")


def start_macos_monitor(plist, user_uid=None):
    """Restore a previously loaded LaunchAgent and confirm it is registered."""
    if plist is None or sys.platform != "darwin":
        return
    uid, expected_plist = _macos_user_context(user_uid)
    plist = Path(plist)
    if plist != expected_plist:
        raise RuntimeError("Refusing to bootstrap a LaunchAgent outside the original user's home.")
    _validate_macos_agent_plist(plist, uid)
    domain = f"gui/{uid}"
    service = f"{domain}/{MACOS_MONITOR_LABEL}"

    domain_result = _run_macos_launchctl("print", domain)
    if domain_result.returncode:
        raise RuntimeError(
            "Could not access the original user's macOS GUI session to restore monitoring: "
            + _macos_launchctl_detail(domain_result)
        )
    started = _run_macos_launchctl("bootstrap", domain, str(plist))
    if started.returncode:
        raise RuntimeError(
            "Could not restart the original user's macOS attendance monitor: "
            + _macos_launchctl_detail(started)
        )
    confirmation = _run_macos_launchctl("print", service)
    if confirmation.returncode:
        raise RuntimeError(
            "The macOS attendance monitor bootstrap returned success, but its loaded state "
            "could not be confirmed: " + _macos_launchctl_detail(confirmation)
        )


def _remove_macos_bundle(path):
    path = Path(path)
    if path.is_symlink() or not path.is_dir():
        path.unlink(missing_ok=True)
    elif path.exists():
        shutil.rmtree(path)


def _macos_bundle_is_valid(path):
    path = Path(path)
    return (
        not path.is_symlink()
        and path.is_dir()
        and (path / "Contents" / "MacOS" / "SCAFA_Workforce").is_file()
    )


def _macos_update_state_path(app_target):
    app_target = Path(app_target)
    return app_target.with_name(app_target.name + ".update-state")


def _read_macos_update_state(path):
    path = Path(path)
    if not path.exists() and not path.is_symlink():
        return None
    if path.is_symlink() or not path.is_file():
        raise RuntimeError("The macOS update state marker is not a regular file.")
    try:
        state = path.read_text(encoding="ascii").strip()
    except (OSError, UnicodeError) as exc:
        raise RuntimeError(f"Could not read the macOS update state marker: {exc}") from exc
    if state not in {
        "in_progress:loaded",
        "in_progress:unloaded",
        "complete:loaded",
        "complete:unloaded",
    }:
        raise RuntimeError("The macOS update state marker is invalid; manual recovery is required.")
    return state


def _write_macos_update_state(path, state):
    if state not in {
        "in_progress:loaded",
        "in_progress:unloaded",
        "complete:loaded",
        "complete:unloaded",
    }:
        raise ValueError("Invalid macOS update state.")
    path = Path(path)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(descriptor, "w", encoding="ascii") as temporary:
            temporary.write(state + "\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, path)
    finally:
        Path(temporary_name).unlink(missing_ok=True)


def _restore_macos_previous_bundle(app_target, backup, state_path, user_uid, monitor_state=None):
    # Stop any monitor that may still reference the bundle being replaced.
    currently_loaded = stop_macos_monitor(user_uid)
    if monitor_state == "loaded":
        uid, restore_plist = _macos_user_context(user_uid)
        _validate_macos_agent_plist(restore_plist, uid)
    elif monitor_state == "unloaded":
        restore_plist = None
    else:
        # Legacy backups have no transaction marker; preserve the state observed now.
        restore_plist = currently_loaded

    _remove_macos_bundle(app_target)
    backup.rename(app_target)
    if restore_plist is not None:
        start_macos_monitor(restore_plist, user_uid)
    Path(state_path).unlink(missing_ok=True)


def apply_macos(package,target,user_uid=None):
    archive=Path(package); app_target=Path(target)
    if not archive.is_file() or app_target.suffix!=".app":
        raise RuntimeError("The macOS update package or installed application path is invalid.")
    work=Path(tempfile.mkdtemp(prefix="scafa-update-"))
    backup=app_target.with_name(app_target.name+".previous")
    state_path=_macos_update_state_path(app_target)
    try:
        safe_extract_zip(archive,work)
        candidates=list(work.rglob("SCAFA_Workforce.app"))
        if not candidates:
            raise RuntimeError("The downloaded archive does not contain SCAFA_Workforce.app.")
        new_app=candidates[0]
        executable=new_app/"Contents"/"MacOS"/"SCAFA_Workforce"
        if not executable.is_file():
            raise RuntimeError("The downloaded macOS app is missing its executable.")

        state = _read_macos_update_state(state_path)
        backup_present = backup.exists() or backup.is_symlink()
        if state is not None:
            phase, monitor_state = state.split(":", 1)
            if phase == "complete" and _macos_bundle_is_valid(app_target):
                if backup_present:
                    if not _macos_bundle_is_valid(backup):
                        raise RuntimeError(
                            "The completed macOS update has an invalid leftover backup; "
                            "the backup was preserved for manual recovery."
                        )
                    # A completed update may leave its old bundle behind if cleanup
                    # was interrupted. Retire it; never roll back a completed update.
                    _remove_macos_bundle(backup)
                state_path.unlink(missing_ok=True)
            elif backup_present and _macos_bundle_is_valid(backup):
                _restore_macos_previous_bundle(
                    app_target, backup, state_path, user_uid, monitor_state
                )
                raise RuntimeError(
                    "A previous macOS update was interrupted. The previous application "
                    "has been restored; retry the update."
                )
            else:
                raise RuntimeError(
                    "The macOS update was interrupted but its recovery backup is unavailable. "
                    "The installed files were preserved; manual recovery is required."
                )
        elif backup_present:
            if not _macos_bundle_is_valid(backup):
                raise RuntimeError(
                    "An incomplete macOS recovery backup exists and was preserved. "
                    "Manual recovery is required before another update."
                )
            if _macos_bundle_is_valid(app_target):
                # Older updater versions did not record whether a leftover .previous
                # bundle came from a completed update or an interrupted replacement.
                # Do not guess and risk silently downgrading a working installation.
                raise RuntimeError(
                    "A legacy macOS recovery backup exists beside a valid application "
                    "without an update-state marker. Both bundles were preserved; "
                    "manual recovery is required before another update."
                )
            _restore_macos_previous_bundle(
                app_target, backup, state_path, user_uid
            )
            raise RuntimeError(
                "A previous macOS update was interrupted. The previous application "
                "has been restored; retry the update."
            )

        # Stop only a monitor that is actually loaded. A previously unloaded or
        # disabled LaunchAgent must remain unloaded after the update.
        monitor_plist = stop_macos_monitor(user_uid)
        monitor_state = "loaded" if monitor_plist is not None else "unloaded"
        try:
            _write_macos_update_state(
                state_path, "in_progress:" + monitor_state
            )
        except Exception:
            if monitor_plist is not None:
                try:
                    start_macos_monitor(monitor_plist, user_uid)
                except Exception as restart_error:
                    raise RuntimeError(
                        "Could not record the macOS update state or restore the "
                        f"attendance monitor: {restart_error}"
                    )
            raise

        backup_created = False
        try:
            app_target.rename(backup)
            backup_created = True
            shutil.copytree(new_app,app_target,symlinks=True)
            if monitor_plist is not None:
                start_macos_monitor(monitor_plist, user_uid)
            if user_uid is not None and hasattr(os, "geteuid") and os.geteuid() == 0:
                subprocess.run(["/bin/launchctl", "asuser", str(user_uid),
                                "/usr/bin/open", str(app_target)],check=True)
            else:
                subprocess.run(["/usr/bin/open", str(app_target)],check=True)
            # Mark completion only after the new bundle, monitor and app launch all
            # succeed. If backup deletion later fails, the next update can safely
            # distinguish that stale backup from an interrupted replacement.
            _write_macos_update_state(
                state_path, "complete:" + monitor_state
            )
        except Exception as update_error:
            try:
                # If the new agent was partially or fully bootstrapped, unload it
                # before restoring the old bundle it references.
                if monitor_plist is not None:
                    stop_macos_monitor(user_uid)
                if backup_created and (backup.exists() or backup.is_symlink()):
                    _remove_macos_bundle(app_target)
                    backup.rename(app_target)
                if monitor_plist is not None:
                    start_macos_monitor(monitor_plist, user_uid)
                state_path.unlink(missing_ok=True)
            except Exception as recovery_error:
                raise RuntimeError(
                    f"{update_error} The previous application bundle is preserved at "
                    f"{backup}; automatic rollback or monitor recovery also failed: "
                    f"{recovery_error}"
                ) from update_error
            raise

        try:
            _remove_macos_bundle(backup)
        except OSError:
            # Keep the "complete" marker. The next updater invocation will retry
            # cleanup instead of mistaking this backup for an interrupted update.
            pass
        else:
            try:
                state_path.unlink(missing_ok=True)
            except OSError:
                # A leftover complete marker is safe and is removed on the next run.
                pass
    finally:
        shutil.rmtree(work,ignore_errors=True)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--pid",type=int)
    parser.add_argument("--package")
    parser.add_argument("--target")
    parser.add_argument("--platform",choices=("windows","macos"))
    parser.add_argument("--user-uid",type=int,default=None)
    parser.add_argument("--installer-powershell-script")
    args=parser.parse_args()

    if args.installer_powershell_script is not None:
        try:
            result = run_installer_powershell_script(args.installer_powershell_script)
        except subprocess.TimeoutExpired as exc:
            for stream, output in (
                (sys.stdout, exc.stdout),
                (sys.stderr, exc.stderr),
            ):
                if output:
                    if isinstance(output, bytes):
                        output = output.decode("utf-8", errors="replace")
                    stream.write(output)
            sys.stderr.write(
                "Timed out while running the Windows installer Task Scheduler command "
                f"after {WINDOWS_MONITOR_COMMAND_TIMEOUT_SECONDS} seconds; "
                "the PowerShell process was terminated.\n"
            )
            return 124
        except OSError as exc:
            sys.stderr.write(f"Could not execute the Windows installer Task Scheduler command: {exc}\n")
            return 1

        sys.stdout.write(result.stdout or "")
        sys.stderr.write(result.stderr or "")
        return result.returncode

    if args.pid is None or not args.package or not args.target or not args.platform:
        parser.error("--pid, --package, --target, and --platform are required for update mode")

    try:
        wait_for_process(args.pid)
        if args.platform=="windows":
            apply_windows(args.package,args.target)
        else:
            target=Path(args.target)
            # /Applications is commonly administrator-owned. Request macOS authorization
            # before replacing anything, then run the helper with the user's GUI identity.
            if os.access(target.parent, os.W_OK):
                apply_macos(args.package,args.target,args.user_uid)
            else:
                command=[sys.executable,*sys.argv[1:]]
                shell_command=shlex.join(command)
                escaped=shell_command.replace("\\","\\\\").replace('"','\\"')
                apple_script='do shell script "'+escaped+'" with administrator privileges'
                subprocess.run(["/usr/bin/osascript","-e",apple_script],check=True)
    except Exception as exc:
        show_error(str(exc))
        raise
    return 0


if __name__=="__main__":
    raise SystemExit(main())
