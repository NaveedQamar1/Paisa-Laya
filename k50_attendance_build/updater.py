"""Small external helper that applies a verified SCAFA Workforce update after the app exits."""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path


def wait_for_process(pid, timeout=180):
    deadline=time.time()+timeout
    while time.time()<deadline:
        try:
            os.kill(pid,0)
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
    # Inno Setup launches the new app through its [Run] entry, including silent updates.


def apply_macos(package,target):
    archive=Path(package); app_target=Path(target)
    if not archive.is_file() or app_target.suffix!=".app":
        raise RuntimeError("The macOS update package or installed application path is invalid.")
    work=Path(tempfile.mkdtemp(prefix="scafa-update-"))
    backup=app_target.with_name(app_target.name+".previous")
    try:
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(work)
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
        subprocess.Popen(["/usr/bin/open",str(app_target)])
        shutil.rmtree(backup,ignore_errors=True)
    finally:
        shutil.rmtree(work,ignore_errors=True)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--pid",type=int,required=True)
    parser.add_argument("--package",required=True)
    parser.add_argument("--target",required=True)
    parser.add_argument("--platform",choices=("windows","macos"),required=True)
    args=parser.parse_args()
    try:
        wait_for_process(args.pid)
        if args.platform=="windows": apply_windows(args.package,args.target)
        else: apply_macos(args.package,args.target)
    except Exception as exc:
        show_error(str(exc))
        raise


if __name__=="__main__":
    main()
