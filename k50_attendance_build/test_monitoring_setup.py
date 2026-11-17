import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import app


class BackgroundMonitorSetupTests(unittest.TestCase):
    def test_windows_monitor_reports_when_task_is_scheduled_but_cannot_start(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scafa-monitor.exe").write_text("monitor helper")
            ctx = SimpleNamespace(
                ip=SimpleNamespace(get=lambda: "192.168.1.50"),
                port=SimpleNamespace(get=lambda: "4370"),
                key=SimpleNamespace(get=lambda: "0"),
                status=SimpleNamespace(set=Mock()),
            )
            results = [
                SimpleNamespace(returncode=0, stderr="", stdout=""),
                SimpleNamespace(returncode=1, stderr="Access is denied.", stdout=""),
            ]
            with patch.object(app.sys, "platform", "win32"), \
                 patch.object(app.sys, "executable", str(root / "SCAFA_Workforce.exe")), \
                 patch.object(app.Path, "home", return_value=root), \
                 patch.object(app.messagebox, "askyesno", return_value=True), \
                 patch.object(app.subprocess, "run", side_effect=results) as run, \
                 patch.object(app.messagebox, "showwarning") as showwarning, \
                 patch.object(app.messagebox, "showinfo") as showinfo, \
                 patch.object(app.messagebox, "showerror") as showerror:
                app.App.configure_background_monitoring(ctx)

        self.assertEqual(run.call_count, 2)
        self.assertEqual(
            run.call_args_list[1].args[0],
            ["schtasks", "/Run", "/TN", "SCAFA Workforce Attendance Monitor"],
        )
        self.assertEqual(
            ctx.status.set.call_args.args[0],
            "Background monitoring scheduled • current start failed",
        )
        showwarning.assert_called_once()
        self.assertIn("Access is denied.", showwarning.call_args.args[1])
        showinfo.assert_not_called()
        showerror.assert_not_called()


    def test_windows_monitor_disable_does_not_claim_stopped_when_end_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scafa-monitor.exe").write_text("monitor helper")
            ctx = SimpleNamespace(
                ip=SimpleNamespace(get=lambda: "192.168.1.50"),
                port=SimpleNamespace(get=lambda: "4370"),
                key=SimpleNamespace(get=lambda: "0"),
                status=SimpleNamespace(set=Mock()),
            )
            results = [
                SimpleNamespace(returncode=1, stderr="Task is not running.", stdout=""),
                SimpleNamespace(returncode=0, stderr="", stdout=""),
            ]
            with patch.object(app.sys, "platform", "win32"), \
                 patch.object(app.sys, "executable", str(root / "SCAFA_Workforce.exe")), \
                 patch.object(app.Path, "home", return_value=root), \
                 patch.object(app.messagebox, "askyesno", return_value=False), \
                 patch.object(app.subprocess, "run", side_effect=results) as run, \
                 patch.object(app.messagebox, "showwarning") as showwarning, \
                 patch.object(app.messagebox, "showinfo") as showinfo:
                app.App.configure_background_monitoring(ctx)

        self.assertEqual(run.call_count, 2)
        self.assertEqual(run.call_args_list[0].args[0][:2], ["schtasks", "/End"])
        self.assertEqual(run.call_args_list[1].args[0][:2], ["schtasks", "/Delete"])
        self.assertIn("stop not confirmed", ctx.status.set.call_args.args[0])
        showwarning.assert_called_once()
        showinfo.assert_not_called()

    def test_windows_monitor_disable_reports_task_deletion_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scafa-monitor.exe").write_text("monitor helper")
            ctx = SimpleNamespace(
                ip=SimpleNamespace(get=lambda: "192.168.1.50"),
                port=SimpleNamespace(get=lambda: "4370"),
                key=SimpleNamespace(get=lambda: "0"),
                status=SimpleNamespace(set=Mock()),
            )
            results = [
                SimpleNamespace(returncode=0, stderr="", stdout=""),
                SimpleNamespace(returncode=1, stderr="Access is denied.", stdout=""),
            ]
            with patch.object(app.sys, "platform", "win32"), \
                 patch.object(app.sys, "executable", str(root / "SCAFA_Workforce.exe")), \
                 patch.object(app.Path, "home", return_value=root), \
                 patch.object(app.messagebox, "askyesno", return_value=False), \
                 patch.object(app.subprocess, "run", side_effect=results), \
                 patch.object(app.messagebox, "showwarning") as showwarning, \
                 patch.object(app.messagebox, "showinfo") as showinfo:
                app.App.configure_background_monitoring(ctx)

        self.assertIn("could not be disabled", ctx.status.set.call_args.args[0])
        showwarning.assert_called_once()
        self.assertIn("Access is denied.", showwarning.call_args.args[1])
        showinfo.assert_not_called()

    def test_macos_monitor_disable_keeps_login_item_when_bootout_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scafa-monitor").write_text("monitor helper")
            agent_dir = root / "Library" / "LaunchAgents"
            agent_dir.mkdir(parents=True)
            plist = agent_dir / "pk.scafa.workforce.monitor.plist"
            plist.write_text("existing launch agent")
            ctx = SimpleNamespace(
                ip=SimpleNamespace(get=lambda: "192.168.1.50"),
                port=SimpleNamespace(get=lambda: "4370"),
                key=SimpleNamespace(get=lambda: "0"),
                status=SimpleNamespace(set=Mock()),
            )
            with patch.object(app.sys, "platform", "darwin"), \
                 patch.object(app.sys, "executable", str(root / "SCAFA_Workforce")), \
                 patch.object(app.Path, "home", return_value=root), \
                 patch.object(app.os, "getuid", return_value=501, create=True), \
                 patch.object(app.messagebox, "askyesno", return_value=False), \
                 patch.object(app.subprocess, "run", return_value=SimpleNamespace(
                     returncode=1, stderr="Operation not permitted.", stdout=""
                 )), \
                 patch.object(app.messagebox, "showwarning") as showwarning, \
                 patch.object(app.messagebox, "showinfo") as showinfo:
                app.App.configure_background_monitoring(ctx)
                self.assertTrue(plist.exists())

        self.assertIn("not confirmed", ctx.status.set.call_args.args[0])
        showwarning.assert_called_once()
        self.assertIn("Operation not permitted.", showwarning.call_args.args[1])
        showinfo.assert_not_called()

    def test_macos_monitor_disable_removes_login_item_after_successful_bootout(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scafa-monitor").write_text("monitor helper")
            agent_dir = root / "Library" / "LaunchAgents"
            agent_dir.mkdir(parents=True)
            plist = agent_dir / "pk.scafa.workforce.monitor.plist"
            plist.write_text("existing launch agent")
            ctx = SimpleNamespace(
                ip=SimpleNamespace(get=lambda: "192.168.1.50"),
                port=SimpleNamespace(get=lambda: "4370"),
                key=SimpleNamespace(get=lambda: "0"),
                status=SimpleNamespace(set=Mock()),
            )
            with patch.object(app.sys, "platform", "darwin"), \
                 patch.object(app.sys, "executable", str(root / "SCAFA_Workforce")), \
                 patch.object(app.Path, "home", return_value=root), \
                 patch.object(app.os, "getuid", return_value=501, create=True), \
                 patch.object(app.messagebox, "askyesno", return_value=False), \
                 patch.object(app.subprocess, "run", return_value=SimpleNamespace(
                     returncode=0, stderr="", stdout=""
                 )), \
                 patch.object(app.messagebox, "showwarning") as showwarning, \
                 patch.object(app.messagebox, "showinfo") as showinfo:
                app.App.configure_background_monitoring(ctx)

        self.assertFalse(plist.exists())
        self.assertEqual(ctx.status.set.call_args.args[0], "Background device monitoring disabled")
        showinfo.assert_called_once()
        showwarning.assert_not_called()

    def test_windows_monitor_disable_reports_success_only_after_stop_and_delete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scafa-monitor.exe").write_text("monitor helper")
            ctx = SimpleNamespace(
                ip=SimpleNamespace(get=lambda: "192.168.1.50"),
                port=SimpleNamespace(get=lambda: "4370"),
                key=SimpleNamespace(get=lambda: "0"),
                status=SimpleNamespace(set=Mock()),
            )
            results = [
                SimpleNamespace(returncode=0, stderr="", stdout=""),
                SimpleNamespace(returncode=0, stderr="", stdout=""),
            ]
            with patch.object(app.sys, "platform", "win32"), \
                 patch.object(app.sys, "executable", str(root / "SCAFA_Workforce.exe")), \
                 patch.object(app.Path, "home", return_value=root), \
                 patch.object(app.messagebox, "askyesno", return_value=False), \
                 patch.object(app.subprocess, "run", side_effect=results), \
                 patch.object(app.messagebox, "showwarning") as showwarning, \
                 patch.object(app.messagebox, "showinfo") as showinfo:
                app.App.configure_background_monitoring(ctx)

        self.assertEqual(ctx.status.set.call_args.args[0], "Background device monitoring disabled")
        self.assertTrue(all(
            call.kwargs["timeout"] == app.MONITOR_COMMAND_TIMEOUT_SECONDS
            for call in run.call_args_list
        ))
        showinfo.assert_called_once()
        showwarning.assert_not_called()

    def test_windows_monitor_command_timeout_reports_unknown_state_without_claiming_enabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scafa-monitor.exe").write_text("monitor helper")
            ctx = SimpleNamespace(
                ip=SimpleNamespace(get=lambda: "192.168.1.50"),
                port=SimpleNamespace(get=lambda: "4370"),
                key=SimpleNamespace(get=lambda: "0"),
                status=SimpleNamespace(set=Mock()),
            )
            timeout = app.subprocess.TimeoutExpired(
                cmd=["schtasks", "/Create"],
                timeout=app.MONITOR_COMMAND_TIMEOUT_SECONDS,
            )
            with (
                patch.object(app.sys, "platform", "win32"),
                patch.object(app.sys, "executable", str(root / "SCAFA_Workforce.exe")),
                patch.object(app.Path, "home", return_value=root),
                patch.object(app.messagebox, "askyesno", return_value=True),
                patch.object(app.subprocess, "run", side_effect=timeout) as run,
                patch.object(app.messagebox, "showwarning") as showwarning,
                patch.object(app.messagebox, "showinfo") as showinfo,
                patch.object(app.messagebox, "showerror") as showerror,
            ):
                app.App.configure_background_monitoring(ctx)

        run.assert_called_once()
        self.assertEqual(run.call_args.kwargs["timeout"], app.MONITOR_COMMAND_TIMEOUT_SECONDS)
        self.assertEqual(ctx.status.set.call_args.args[0], "Background monitoring state could not be confirmed")
        showwarning.assert_called_once()
        self.assertIn("Timed out after", showwarning.call_args.args[1])
        showinfo.assert_not_called()
        showerror.assert_not_called()

    def test_macos_monitor_stop_timeout_preserves_login_item_for_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scafa-monitor").write_text("monitor helper")
            agent_dir = root / "Library" / "LaunchAgents"
            agent_dir.mkdir(parents=True)
            plist = agent_dir / "pk.scafa.workforce.monitor.plist"
            plist.write_text("existing launch agent")
            ctx = SimpleNamespace(
                ip=SimpleNamespace(get=lambda: "192.168.1.50"),
                port=SimpleNamespace(get=lambda: "4370"),
                key=SimpleNamespace(get=lambda: "0"),
                status=SimpleNamespace(set=Mock()),
            )
            timeout = app.subprocess.TimeoutExpired(
                cmd=["launchctl", "bootout"],
                timeout=app.MONITOR_COMMAND_TIMEOUT_SECONDS,
            )
            with (
                patch.object(app.sys, "platform", "darwin"),
                patch.object(app.sys, "executable", str(root / "SCAFA_Workforce")),
                patch.object(app.Path, "home", return_value=root),
                patch.object(app.os, "getuid", return_value=501, create=True),
                patch.object(app.messagebox, "askyesno", return_value=False),
                patch.object(app.subprocess, "run", side_effect=timeout) as run,
                patch.object(app.messagebox, "showwarning") as showwarning,
                patch.object(app.messagebox, "showinfo") as showinfo,
            ):
                app.App.configure_background_monitoring(ctx)
                self.assertTrue(plist.exists())

        run.assert_called_once()
        self.assertEqual(run.call_args.kwargs["timeout"], app.MONITOR_COMMAND_TIMEOUT_SECONDS)
        self.assertEqual(ctx.status.set.call_args.args[0], "Background monitoring state could not be confirmed")
        showwarning.assert_called_once()
        self.assertIn("Timed out after", showwarning.call_args.args[1])
        showinfo.assert_not_called()


if __name__ == "__main__":
    unittest.main()
