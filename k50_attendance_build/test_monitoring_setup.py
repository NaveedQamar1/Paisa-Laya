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


if __name__ == "__main__":
    unittest.main()
