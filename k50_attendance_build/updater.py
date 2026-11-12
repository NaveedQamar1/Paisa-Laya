"""Small external helper that applies a verified SCAFA Workforce update after the app exits."""
import argparse
import os
import shlex
import stat
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import PurePosixPath
from pathlib import Path


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


def apply_windows(package,target):
    installer=Path(package)
    if not installer.is_file():
        raise FileNotFoundError("The downloaded Windows installer is missing.")
    result=subprocess.run([str(installer),"/VERYSILENT","/SUPPRESSMSGBOXES","/NORESTART","/CLOSEAPPLICATIONS"],check=False)
    if result.returncode:
        raise RuntimeError(f"The Windows installer returned exit code {result.returncode}.")
    installed_app=Path(target)/"SCAFA_Workforce.exe"
    if not installed_app.is_file():
        raise RuntimeError("The installer completed, but SCAFA_Workforce.exe was not found at the expected installation path.")
    subprocess.Popen([str(installed_app)],cwd=str(Path(target)))


def safe_extract_zip(archive, destination):
    """Extract regular files and safe, relative macOS bundle symlinks."""
    destination=Path(destination).resolve()
    with zipfile.ZipFile(archive) as zf:
        members=[]
        symlinks={}
        for member in zf.infolist():
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
                try:
                    link_target=zf.read(member).decode("utf-8")
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
        for member,member_path,mode in members:
            output=destination.joinpath(*member_path.parts)
            if member.is_dir():
                output.mkdir(parents=True,exist_ok=True)
                continue
            output.parent.mkdir(parents=True,exist_ok=True)
            with zf.open(member) as source, output.open("wb") as target:
                shutil.copyfileobj(source,target)
            permissions=mode & 0o777
            if permissions:
                output.chmod(permissions)

        for member_path,link_target in symlinks.items():
            output=destination.joinpath(*member_path.parts)
            output.parent.mkdir(parents=True,exist_ok=True)
            os.symlink(link_target,output)


def apply_macos(package,target,user_uid=None):
    archive=Path(package); app_target=Path(target)
    if not archive.is_file() or app_target.suffix!=".app":
        raise RuntimeError("The macOS update package or installed application path is invalid.")
    work=Path(tempfile.mkdtemp(prefix="scafa-update-"))
    backup=app_target.with_name(app_target.name+".previous")
    try:
        safe_extract_zip(archive,work)
        candidates=list(work.rglob("SCAFA_Workforce.app"))
        if not candidates:
            raise RuntimeError("The downloaded archive does not contain SCAFA_Workforce.app.")
        new_app=candidates[0]
        executable=new_app/"Contents"/"MacOS"/"SCAFA_Workforce"
        if not executable.exists():
            raise RuntimeError("The downloaded macOS app is missing its executable.")
        if backup.exists():
            shutil.rmtree(backup)
        app_target.rename(backup)
        try:
            shutil.copytree(new_app,app_target,symlinks=True)
        except Exception:
            if app_target.exists(): shutil.rmtree(app_target)
            backup.rename(app_target)
            raise
        try:
            if user_uid is not None and hasattr(os, "geteuid") and os.geteuid() == 0:
                subprocess.run(["/bin/launchctl", "asuser", str(user_uid),
                                "/usr/bin/open", str(app_target)],check=True)
            else:
                subprocess.run(["/usr/bin/open", str(app_target)],check=True)
        except Exception:
            shutil.rmtree(app_target,ignore_errors=True)
            backup.rename(app_target)
            raise
        shutil.rmtree(backup,ignore_errors=True)
    finally:
        shutil.rmtree(work,ignore_errors=True)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--pid",type=int,required=True)
    parser.add_argument("--package",required=True)
    parser.add_argument("--target",required=True)
    parser.add_argument("--platform",choices=("windows","macos"),required=True)
    parser.add_argument("--user-uid",type=int,default=None)
    args=parser.parse_args()
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


if __name__=="__main__":
    main()
